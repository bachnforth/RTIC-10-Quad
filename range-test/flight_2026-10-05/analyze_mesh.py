"""Mesh-link analysis of the 2026-10-05 range flight from the Pi's mesh logger (v2). Writes charts/ and results.json."""
import collections, csv, json, math, os, sys
from datetime import datetime, timezone, timedelta
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, "..")
LOG = "data/mesh_log_flight_2026-10-05.csv"
OUT = "charts"
os.makedirs(OUT, exist_ok=True)
CDT = timezone(timedelta(hours=-5))

R = list(csv.DictReader(open(LOG, encoding="utf-8", errors="replace")))
m0 = float(R[0]["mono_s"])
T = lambda r: float(r["mono_s"]) - m0
fnum = lambda v: float(v) if v not in ("", None) else float("nan")

# ------------------------------------------------------------------ drone position (from the telemetry the Pi sent toward QGC)
fc = [r for r in R if r["node_id"] == "fc" and r.get("fc_lat")]
home = (float(fc[0]["fc_lat"]), float(fc[0]["fc_lon"]))
P = np.array([(T(r), float(r["fc_lat"]), float(r["fc_lon"]), float(r["fc_rel_alt_m"]), fnum(r["fc_gspeed_ms"])) for r in fc])
tP, latP, lonP, altP, gsP = P.T
hd = np.hypot((latP - home[0]) * 111132.0, (lonP - home[1]) * 111320.0 * math.cos(math.radians(home[0])))
d3 = np.hypot(hd, altP)
i_to = int(np.argmax(altP > 5)); t_to = tP[i_to]
i_far = int(np.argmax(d3)); t_far = tP[i_far]
t_last = tP[-1]
dist = lambda t: float(np.interp(t, tP, d3))
altat = lambda t: float(np.interp(t, tP, altP))

# absolute (GPS) time: fc_unix_s is the drone's GPS UTC carried in the telemetry
ut = [(T(r), float(r["fc_unix_s"])) for r in R if r["node_id"] == "fc" and r["fc_unix_s"]]
mono_to_unix = lambda t: float(np.interp(t, [a for a, _ in ut], [b for _, b in ut]))
local = lambda t: datetime.fromtimestamp(mono_to_unix(t), timezone.utc).astimezone(CDT).strftime("%H:%M:%S")


def series(node, field):
    out = [(T(r), fnum(r[field])) for r in R if r["node_id"] == node and r[field] not in ("", None)]
    return np.array(out) if out else np.empty((0, 2))


rad_rssi, rad_snr, rad_noise = series("radio", "rssi_dbm"), series("radio", "snr_db"), series("radio", "noise_dbm")
rn_rssi, rn_snr, rn_noise = series("radio_rn03", "rssi_dbm"), series("radio_rn03", "snr_db"), series("radio_rn03", "noise_dbm")
rad_txb, rad_rxb = series("radio", "tx_bitrate_mbps"), series("radio", "rx_bitrate_mbps")
rn_txb, rn_rxb = series("radio_rn03", "tx_bitrate_mbps"), series("radio_rn03", "rx_bitrate_mbps")
rad_retry, rad_fail = series("radio", "tx_retries"), series("radio", "tx_failed")
rad_ntx = series("radio", "tx_bytes")

def inflight(a, tmin=None, tmax=None):
    tmin = t_to if tmin is None else tmin
    tmax = t_last if tmax is None else tmax
    return a[(a[:, 0] >= tmin) & (a[:, 0] <= tmax)]

def with_dist(a):
    if len(a) == 0:
        return a
    return np.column_stack([a, [dist(t) for t in a[:, 0]], [altat(t) for t in a[:, 0]]])

rad_rssi_f, rad_snr_f, rad_noise_f = (with_dist(inflight(x)) for x in (rad_rssi, rad_snr, rad_noise))
rn_rssi_f, rn_snr_f, rn_noise_f = (with_dist(inflight(x)) for x in (rn_rssi, rn_snr, rn_noise))
out_mask = lambda a: a[:, 0] <= t_far

# ------------------------------------------------------------------ pings
def pings(node):
    rows = [(T(r), int(r["tx_count"]), int(r["rx_count"] or 0), fnum(r["latency_ms"])) for r in R if r["node_id"] == node and r["tx_count"]]
    return np.array(rows)
png = {n: inflight(pings(n)) for n in ("rn03_ground", "phone", "handheld_self")}

def windows(arr, width=30.0):
    """loss % and median/p95/max latency per time window, with distance at the window centre"""
    out = []
    t = t_to
    while t < t_last:
        s = arr[(arr[:, 0] >= t) & (arr[:, 0] < t + width)]
        if len(s) >= 5:
            tx, rx = s[:, 1].sum(), s[:, 2].sum()
            lat = s[:, 3][~np.isnan(s[:, 3])]
            out.append(dict(t=t + width / 2, dist=dist(t + width / 2), alt=altat(t + width / 2), loss=100 * (1 - rx / tx), n=int(tx),
                            med=float(np.median(lat)) if len(lat) else float("nan"), p95=float(np.percentile(lat, 95)) if len(lat) else float("nan"),
                            mx=float(lat.max()) if len(lat) else float("nan"), out=bool(t + width / 2 <= t_far)))
        t += width
    return out
W = {n: windows(a) for n, a in png.items()}

def blackouts(arr, min_s=3.0):
    """runs where every ping burst was lost, at least min_s long"""
    runs, start, last = [], None, None
    for t, tx, rx, _ in arr:
        if rx == 0:
            if start is None:
                start = t
            last = t
        else:
            if start is not None and last - start + 1 >= min_s:
                runs.append((start, last + 1))
            start = None
    if start is not None and last - start + 1 >= min_s:
        runs.append((start, last + 1))
    return [dict(start=a, dur=b - a, t_rel=a - t_to, local=local(a), dist=dist(a), alt=altat(a), out=a <= t_far) for a, b in runs]
BL = {n: blackouts(png[n]) for n in ("rn03_ground", "phone")}

# ------------------------------------------------------------------ events: SSH (reading the radios) dropouts in flight, telemetry, uplink
ssh_down = [(T(r), r["node_id"]) for r in R if "ssh_down" in r["event"] and t_to <= T(r) <= t_last]
gcs = np.array([(T(r), int(r["gcs_msgs_in"])) for r in R if r["node_id"] == "gcs_uplink" and r["gcs_msgs_in"] != ""])
gcs_f = gcs[(gcs[:, 0] >= t_to) & (gcs[:, 0] <= t_last)]
gcs_zero = gcs_f[gcs_f[:, 1] == 0]
fcr = np.array([(T(r), int(r["fc_rows_s"] or 0)) for r in R if r["node_id"] == "fc"])
fcr_f = fcr[(fcr[:, 0] >= t_to) & (fcr[:, 0] <= t_last)]
fc_low = fcr_f[fcr_f[:, 1] < 20]

# link-state changes seen by the drone radio (mesh peer link)
plink = [(T(r), r["plink"], r["neighbors"]) for r in R if r["node_id"] == "radio" and r["plink"] not in ("",)]
state_changes = []
prev = None
for t, p_, n in plink:
    if p_ != prev and t_to <= t <= t_last:
        state_changes.append(dict(t=t, local=local(t), plink=p_, neighbors=n, dist=dist(t)))
    prev = p_

# retry / failure rates (per second, from running totals)
def rate(a):
    if len(a) < 3:
        return np.empty((0, 2))
    dt = np.diff(a[:, 0]); dv = np.diff(a[:, 1]); ok = (dt > 0.5) & (dv >= 0)
    return np.column_stack([a[1:, 0][ok], dv[ok] / dt[ok]])
retry_rate, fail_rate, txb_rate = rate(rad_retry), rate(rad_fail), rate(rad_ntx)

# ------------------------------------------------------------------ binned statistics
bins = list(range(0, 3500, 500))
def binstats(a, col=1):
    rows = []
    for lo in bins:
        s = a[(a[:, 2] >= lo) & (a[:, 2] < lo + 500)]
        o, r_ = s[s[:, 0] <= t_far], s[s[:, 0] > t_far]
        rows.append(dict(lo=lo, n=int(len(s)), mean=float(s[:, col].mean()) if len(s) else None, mn=float(s[:, col].min()) if len(s) else None,
                         out=float(o[:, col].mean()) if len(o) else None, ret=float(r_[:, col].mean()) if len(r_) else None))
    return rows
BIN = dict(rad_rssi=binstats(rad_rssi_f), rn_rssi=binstats(rn_rssi_f), rad_snr=binstats(rad_snr_f), rn_snr=binstats(rn_snr_f),
           rad_noise=binstats(rad_noise_f))

def bitrate_bins(a, label):
    rows = []
    for lo in bins:
        s = [v for t, v in a if t_to <= t <= t_last and lo <= dist(t) < lo + 500]
        rows.append(dict(lo=lo, n=len(s), med=float(np.median(s)) if s else None))
    return rows
BR = dict(rad_tx=bitrate_bins(rad_txb, "tx"), rad_rx=bitrate_bins(rad_rxb, "rx"), rn_tx=bitrate_bins(rn_txb, "tx"), rn_rx=bitrate_bins(rn_rxb, "rx"))

def ping_bins(node):
    rows = []
    for lo in bins:
        s = png[node][[lo <= dist(t) < lo + 500 for t in png[node][:, 0]]]
        if len(s) == 0:
            rows.append(dict(lo=lo, n=0)); continue
        lat = s[:, 3][~np.isnan(s[:, 3])]
        rows.append(dict(lo=lo, n=int(s[:, 1].sum()), loss=100 * (1 - s[:, 2].sum() / s[:, 1].sum()),
                         med=float(np.median(lat)) if len(lat) else None, p95=float(np.percentile(lat, 95)) if len(lat) else None,
                         mx=float(lat.max()) if len(lat) else None))
    return rows
PB = {n: ping_bins(n) for n in ("rn03_ground", "phone")}

# free-space path loss (theory) and implied link budget
fspl = lambda d_m, f_mhz=907.0: 20 * math.log10(d_m / 1000.0) + 20 * math.log10(f_mhz) + 32.44
far = dict(dist=float(d3[i_far]), alt=float(altP[i_far]))
far_rssi = rad_rssi_f[np.abs(rad_rssi_f[:, 2] - far["dist"]) < 150]
far_rn = rn_rssi_f[np.abs(rn_rssi_f[:, 2] - far["dist"]) < 150]
far_snr = rad_snr_f[np.abs(rad_snr_f[:, 2] - far["dist"]) < 150]
far_noise = rad_noise_f[np.abs(rad_noise_f[:, 2] - far["dist"]) < 150]
# fit RSSI = a - 10*n*log10(d) on the outbound leg beyond 150 m (drone radio and RN03)
def fit(a):
    s = a[(a[:, 2] > 150) & (a[:, 0] <= t_far)]
    x = np.log10(s[:, 2]); A = np.vstack([x, np.ones(len(x))]).T
    k, c = np.linalg.lstsq(A, s[:, 1], rcond=None)[0]
    return dict(slope_per_decade=float(k), n_exp=float(-k / 10), at_1km=float(k * 3 + c), rmse=float(np.sqrt(np.mean((A @ [k, c] - s[:, 1]) ** 2))))
FIT = dict(drone=fit(rad_rssi_f), rn03=fit(rn_rssi_f))

res = dict(
    log=LOG, takeoff_local=local(t_to), far_local=local(t_far), last_local=local(t_last), date_local=datetime.fromtimestamp(mono_to_unix(t_to), timezone.utc).astimezone(CDT).strftime("%Y-%m-%d"),
    t_to=float(t_to), t_far=float(t_far), t_last=float(t_last), log_len=float(T(R[-1])),
    max_h=float(hd.max()), max_3d=float(d3.max()), max_alt=float(altP.max()), max_speed=float(np.nanmax(gsP)),
    last_dist=float(d3[-1]), last_alt=float(altP[-1]), cruise_speed=float(np.nanmedian(gsP[(tP > t_to + 20) & (tP < t_far - 10) & (gsP > 5)])),
    out_s=float(t_far - t_to), logged_after_far_s=float(t_last - t_far),
    link_up_at=next((float(t) for t, p_, n in plink if p_ == "ESTAB"), None), radio_noif_at=next((float(t) for t, p_, n in plink if p_ == "no_interface"), None),
    far=far, far_rssi_drone=float(far_rssi[:, 1].mean()) if len(far_rssi) else None, far_rssi_rn03=float(far_rn[:, 1].mean()) if len(far_rn) else None,
    far_snr_drone=float(far_snr[:, 1].mean()) if len(far_snr) else None, far_noise_drone=float(far_noise[:, 1].mean()) if len(far_noise) else None,
    rssi_min_drone=float(rad_rssi_f[:, 1].min()), rssi_min_rn03=float(rn_rssi_f[:, 1].min()),
    snr_min_drone=float(rad_snr_f[:, 1].min()), snr_min_rn03=float(rn_snr_f[:, 1].min()),
    bins=BIN, bitrate=BR, ping_bins=PB, fit=FIT,
    fspl_far=fspl(far["dist"]), fspl_1500=fspl(1500), fspl_3000=fspl(3000),
    blackouts={k: v for k, v in BL.items()},
    ssh_down=[dict(t_rel=t - t_to, local=local(t), node=n, dist=dist(t), alt=altat(t)) for t, n in ssh_down],
    gcs_zero_inflight=[dict(t_rel=float(t - t_to), local=local(t), dist=dist(t)) for t, _ in gcs_zero],
    fc_low_inflight=[dict(t_rel=float(t - t_to), local=local(t), dist=dist(t), n=int(n)) for t, n in fc_low],
    state_changes=state_changes[:30],
    ping_totals={n: dict(sent=int(png[n][:, 1].sum()), recv=int(png[n][:, 2].sum()),
                         loss=float(100 * (1 - png[n][:, 2].sum() / png[n][:, 1].sum())),
                         med=float(np.nanmedian(png[n][:, 3])), p95=float(np.nanpercentile(png[n][:, 3], 95)), mx=float(np.nanmax(png[n][:, 3])))
                 for n in png},
    retries_total=float(rad_retry[-1, 1]), failed_total=float(rad_fail[-1, 1]),
)
json.dump(res, open("results_mesh.json", "w"), indent=1, default=float)

# ------------------------------------------------------------------ charts
plt.rcParams.update({"font.size": 9, "axes.grid": True, "grid.alpha": 0.3})
C_OUT, C_RET = "#1565c0", "#e65100"
rel = lambda t: t - t_to

# 1 profile
fig, ax = plt.subplots(3, 1, figsize=(10, 7.5), sharex=True)
s = (tP >= t_to - 20)
ax[0].plot(rel(tP[s]), d3[s], color="#222"); ax[0].set_ylabel("3D distance from home (m)")
ax[1].plot(rel(tP[s]), altP[s], color="#c2185b"); ax[1].set_ylabel("altitude (m)")
ax[2].plot(rel(tP[s]), gsP[s], color="#2e7d32"); ax[2].set_ylabel("ground speed (m/s)"); ax[2].set_xlabel("seconds since takeoff")
for a in ax:
    a.axvline(rel(t_far), color="gray", lw=0.7)
    a.axvline(rel(t_last), color="#b71c1c", lw=0.9)
ax[0].text(rel(t_last) - 5, d3.max() * 0.5, "Pi log ends\n(power lost)", color="#b71c1c", fontsize=8, ha="right")
ax[0].set_title("Flight profile from the telemetry the Pi forwarded (2 Hz)")
fig.tight_layout(); fig.savefig(f"{OUT}/m01_flight_profile.png", dpi=150); plt.close(fig)

# 2 RSSI + SNR vs distance
fig, ax = plt.subplots(2, 2, figsize=(11, 7.2), sharex=True)
for col, (name, rs, sn) in enumerate((("Drone-side radio (on the Pi)", rad_rssi_f, rad_snr_f), ("Ground radio RN03", rn_rssi_f, rn_snr_f))):
    for a, arr, lab in ((ax[0, col], rs, "signal strength (dBm)"), (ax[1, col], sn, "SNR (dB)")):
        o = arr[arr[:, 0] <= t_far]; r_ = arr[arr[:, 0] > t_far]
        a.plot(o[:, 2], o[:, 1], ".", ms=3, color=C_OUT, label="outbound"); a.plot(r_[:, 2], r_[:, 1], ".", ms=3, color=C_RET, label="return")
        a.set_ylabel(lab)
    ax[0, col].set_title(name)
    ax[1, col].set_xlabel("3D distance from home (m)")
ax[0, 0].legend(markerscale=3)
fig.suptitle("Mesh radio signal and SNR against distance", y=0.995)
fig.tight_layout(); fig.savefig(f"{OUT}/m02_rssi_snr_vs_distance.png", dpi=150); plt.close(fig)

# 3 noise, bitrate, retries
fig, ax = plt.subplots(2, 2, figsize=(11, 7.2))
ax[0, 0].plot(rad_noise_f[:, 2], rad_noise_f[:, 1], ".", ms=3, color="#6a1b9a", label="drone radio"); ax[0, 0].plot(rn_noise_f[:, 2], rn_noise_f[:, 1], ".", ms=3, color="#00897b", label="RN03")
ax[0, 0].set_ylabel("noise floor (dBm)"); ax[0, 0].set_xlabel("3D distance (m)"); ax[0, 0].legend(markerscale=3); ax[0, 0].set_title("Noise floor")
for arr, lab, c in ((rad_txb, "drone radio, sending", "#1565c0"), (rad_rxb, "drone radio, receiving", "#ef6c00")):
    a_ = inflight(arr); ax[0, 1].plot([dist(t) for t in a_[:, 0]], a_[:, 1], ".", ms=2.5, color=c, label=lab)
ax[0, 1].set_ylabel("link bit rate (Mbit/s)"); ax[0, 1].set_xlabel("3D distance (m)"); ax[0, 1].legend(markerscale=3); ax[0, 1].set_title("Bit rate the radio chose (drone radio)")
if len(retry_rate):
    rr = retry_rate[(retry_rate[:, 0] >= t_to) & (retry_rate[:, 0] <= t_last)]
    ax[1, 0].plot([dist(t) for t in rr[:, 0]], rr[:, 1], ".", ms=3, color="#d81b60")
ax[1, 0].set_ylabel("transmit retries per second"); ax[1, 0].set_xlabel("3D distance (m)"); ax[1, 0].set_title("Retries (drone radio)")
ax[1, 1].plot(d3[s], altP[s], color="#c2185b"); ax[1, 1].set_xlabel("3D distance (m)"); ax[1, 1].set_ylabel("altitude (m)"); ax[1, 1].set_title("Altitude against distance")
fig.tight_layout(); fig.savefig(f"{OUT}/m03_noise_bitrate_retries.png", dpi=150); plt.close(fig)

# 4 pings
fig, ax = plt.subplots(2, 2, figsize=(11, 7.2), sharex=True)
for col, node, title in ((0, "rn03_ground", "Pi to ground radio RN03 (through the mesh)"), (1, "phone", "Pi to the phone (through the mesh and RN03)")):
    w = W[node]
    ax[0, col].bar([x["dist"] for x in w], [x["loss"] for x in w], width=60, color=[C_OUT if x["out"] else C_RET for x in w])
    ax[0, col].set_ylabel("ping loss in 30 s windows (%)"); ax[0, col].set_title(title)
    ax[1, col].plot([x["dist"] for x in w], [x["med"] for x in w], "o-", ms=3, color="#2e7d32", label="median")
    ax[1, col].plot([x["dist"] for x in w], [x["p95"] for x in w], "s-", ms=3, color="#ef6c00", label="95th percentile")
    ax[1, col].set_yscale("log"); ax[1, col].set_ylabel("ping delay (ms)"); ax[1, col].set_xlabel("3D distance at window centre (m)")
ax[1, 0].legend()
fig.suptitle("Packet loss and delay against distance (blue = outbound, orange = return)", y=0.995)
fig.tight_layout(); fig.savefig(f"{OUT}/m04_ping_loss_latency.png", dpi=150); plt.close(fig)

# 5 timeline of events
fig, ax = plt.subplots(4, 1, figsize=(10.5, 8.2), sharex=True)
ax[0].plot(rel(tP), d3, color="#222"); ax[0].set_ylabel("distance (m)")
ax[1].plot(rel(rad_rssi[:, 0]), rad_rssi[:, 1], color="#1565c0", lw=0.8, label="drone radio"); ax[1].plot(rel(rn_rssi[:, 0]), rn_rssi[:, 1], color="#2e7d32", lw=0.8, label="RN03")
ax[1].set_ylabel("signal (dBm)"); ax[1].legend(loc="lower left")
for node, c, y in (("rn03_ground", "#d81b60", 1), ("phone", "#6a1b9a", 0)):
    for b in BL[node]:
        ax[2].barh(y, b["dur"], left=b["t_rel"], height=0.7, color=c)
ax[2].set_yticks([0, 1]); ax[2].set_yticklabels(["phone ping\nblackout", "RN03 ping\nblackout"]); ax[2].set_ylim(-0.6, 1.6)
ax[3].plot(gcs_f[:, 0] - t_to, gcs_f[:, 1], ".", ms=3, color="#00695c"); ax[3].set_ylabel("QGC messages\nper 2 s")
for t, n in ssh_down:
    ax[3].axvline(rel(t), color="#999999", lw=0.5)
ax[3].set_xlabel("seconds since takeoff (grey lines: radio login dropped)")
for a in ax:
    a.axvline(rel(t_far), color="gray", lw=0.7); a.set_xlim(-30, rel(t_last) + 10)
ax[0].set_title("Link timeline")
fig.tight_layout(); fig.savefig(f"{OUT}/m05_timeline.png", dpi=150); plt.close(fig)

# 6 signal vs altitude
fig, ax = plt.subplots(1, 2, figsize=(10, 4))
for a, arr, name in ((ax[0], rad_rssi_f, "drone radio"), (ax[1], rn_rssi_f, "RN03")):
    o = arr[arr[:, 0] <= t_far]; r_ = arr[arr[:, 0] > t_far]
    sc = a.scatter(arr[:, 3], arr[:, 1], c=arr[:, 2], s=6, cmap="viridis"); a.set_xlabel("altitude above home (m)"); a.set_title(f"{name}: signal vs altitude (colour = distance)")
    plt.colorbar(sc, ax=a, label="distance (m)")
ax[0].set_ylabel("signal strength (dBm)")
fig.tight_layout(); fig.savefig(f"{OUT}/m06_signal_vs_altitude.png", dpi=150); plt.close(fig)

# 7 map coloured by RN03 signal
from tiles import mosaic, latlon_to_px
lat0, lon0 = float(latP.min()) - 0.004, float(lonP.min()) - 0.012
lat1, lon1 = float(latP.max()) + 0.004, float(lonP.max()) + 0.012
img, meta = mosaic(lat0, lon0, lat1, lon1, 15)
xa, ya = latlon_to_px(lat1, lon0, meta); xb, yb = latlon_to_px(lat0, lon1, meta)
img = img.crop((int(xa), int(ya), int(xb), int(yb)))
pxy = np.array([np.array(latlon_to_px(a, b, meta)) - np.array([int(xa), int(ya)]) for a, b in zip(latP, lonP)])
fig, ax = plt.subplots(figsize=(6.6, 7.6), dpi=150)
ax.imshow(img)
col_t = np.interp(tP, rn_rssi[:, 0], rn_rssi[:, 1])
sc = ax.scatter(pxy[:, 0], pxy[:, 1], c=col_t, s=7, cmap="RdYlGn", vmin=-80, vmax=-25)
plt.colorbar(sc, ax=ax, fraction=0.04, label="RN03 signal strength (dBm)")
ax.plot(*pxy[0], "w*", ms=11, mec="k"); ax.text(pxy[0, 0] + 8, pxy[0, 1] + 8, "launch", color="white", fontsize=8, bbox=dict(fc="black", alpha=0.5, pad=1))
ax.plot(*pxy[i_far], "wo", ms=7, mec="k"); ax.text(pxy[i_far, 0] + 8, pxy[i_far, 1], f"far point {d3[i_far]:.0f} m", color="white", fontsize=8, bbox=dict(fc="black", alpha=0.5, pad=1))
ax.set_xlim(0, img.size[0]); ax.set_ylim(img.size[1], 0); ax.axis("off"); ax.set_title("Flown track coloured by ground-radio signal (Esri World Imagery)", fontsize=9)
fig.tight_layout(); fig.savefig(f"{OUT}/m07_track_map.png"); plt.close(fig)
print(json.dumps({k: v for k, v in res.items() if k not in ("bins", "bitrate", "ping_bins", "ssh_down", "gcs_zero_inflight", "fc_low_inflight", "state_changes", "blackouts")}, indent=1, default=float))
print("blackouts", {k: [(round(b['t_rel']), round(b['dur']), round(b['dist'])) for b in v] for k, v in BL.items()})
print("ssh_down in flight", [(round(x['t_rel']), x['node'], round(x['dist'])) for x in res['ssh_down']])
print("gcs zero in flight", [(round(x['t_rel']), round(x['dist'])) for x in res['gcs_zero_inflight']][:20])
print("fc low", [(round(x['t_rel']), round(x['dist']), x['n']) for x in res['fc_low_inflight']][:20])
print("state changes", [(round(x['t'] - t_to), x['plink'], x['neighbors'], round(x['dist'])) for x in state_changes][:20])
