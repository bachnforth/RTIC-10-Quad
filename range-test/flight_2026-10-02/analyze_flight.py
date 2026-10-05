"""Analyze the 2026-10-02 range-test flight (flight-controller log #17) and write charts + results.json.

Run from this folder with ..\\.venv\\Scripts\\python.exe analyze_flight.py
"""
import json, math, os, sys
from datetime import datetime, timezone, timedelta
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pymavlink import mavutil

sys.path.insert(0, "..")
LOG = "fc/log17.bin"
OUT = "charts"
os.makedirs(OUT, exist_ok=True)
PLAN = json.load(open("../route_B_north/mission_data.json"))
LAUNCH = tuple(PLAN["launch"])
CDT = timezone(timedelta(hours=-5))

# ---------------------------------------------------------------- read the log
m = mavutil.mavlink_connection(LOG)
D = {k: [] for k in ("POS", "GPS", "BAT", "RSSI", "MAV", "CTUN", "MODE", "MSG", "RTC", "PARM", "ATT")}
while True:
    x = m.recv_match(type=list(D))
    if x is None:
        break
    D[x.get_type()].append(x)

pos = np.array([(p.TimeUS / 1e6, p.Lat, p.Lng, p.RelHomeAlt, p.Alt) for p in D["POS"]])
t_pos, lat, lon, relalt = pos[:, 0], pos[:, 1], pos[:, 2], pos[:, 3]
home = (lat[0], lon[0])
dn = (lat - home[0]) * 111132.0
de = (lon - home[1]) * 111320.0 * math.cos(math.radians(home[0]))
hdist = np.hypot(dn, de)
dist3d = np.hypot(hdist, relalt)

air = np.where(relalt > 5)[0]
t_to, t_land = t_pos[air[0]], t_pos[air[-1]]
rel = t_pos - t_to

gps = np.array([(g.TimeUS / 1e6, g.Spd, g.NSats, g.HDop, g.GWk, g.GMS) for g in D["GPS"]])
rtc = D["RTC"][0]
utc_at = lambda t_log: datetime.fromtimestamp(rtc.Epoch / 1e6 + (t_log - rtc.TimeUS / 1e6), timezone.utc)

bat = np.array([(b.TimeUS / 1e6, b.Volt) for b in D["BAT"]])
rssi = np.array([(r.TimeUS / 1e6, r.RXRSSI, r.RXLQ) for r in D["RSSI"]])
mav1 = np.array([(x.TimeUS / 1e6, x.txp, x.rxp, x.rxdp) for x in D["MAV"] if x.chan == 1])
modes = [(x.TimeUS / 1e6, x.Mode) for x in D["MODE"]]
msgs = [(x.TimeUS / 1e6, x.Message) for x in D["MSG"]]
parm = {p.Name: p.Value for p in D["PARM"]}
MODE_NAMES = {0: "Stabilize", 3: "Auto", 5: "Loiter", 6: "RTL", 9: "Land"}

t_auto = next(t for t, md in modes if md == 3)
t_rtl = next(t for t, md in modes if md == 6)
t_fs = next(t for t, s in msgs if "Battery Failsafe" in s)
t_low = next(t for t, s in msgs if "is low" in s)
t_loiter = next(t for t, s in msgs if "LoitTime" in s)
t_wp17 = next(t for t, s in msgs if "Reached command #17" in s)
t_end = D["MSG"][-1].TimeUS / 1e6

i_far = int(np.argmax(hdist))
far_t = t_pos[i_far]

# speeds ------------------------------------------------------------------
gs_t, gs = gps[:, 0], gps[:, 1]
def gs_between(a, b):
    s = (gs_t >= a) & (gs_t <= b)
    return gs[s]
cruise = gs_between(t_auto + 20, t_loiter - 30)
ret_cruise = gs_between(far_t + 40, t_rtl - 10)

# path length flown ---------------------------------------------------------
step = np.hypot(np.diff(dn), np.diff(de))
def path_len(a, b):
    s = (t_pos[1:] >= a) & (t_pos[1:] <= b)
    return float(step[s].sum())
out_len = path_len(t_to, far_t)
ret_len = path_len(far_t, t_land)

# planned route tracking error ---------------------------------------------------
wps = np.array(PLAN["wps"])
wn = (wps[:, 0] - home[0]) * 111132.0
we = (wps[:, 1] - home[1]) * 111320.0 * math.cos(math.radians(home[0]))
plan_alt = np.array(PLAN["alt_out"])
def xtrack(n, e):
    best, ch_best = 1e9, 0.0
    chain = 0.0
    for k in range(len(wn) - 1):
        a = np.array([wn[k], we[k]]); b = np.array([wn[k + 1], we[k + 1]]); p = np.array([n, e])
        ab = b - a; L2 = float(ab @ ab)
        f = 0.0 if L2 == 0 else max(0.0, min(1.0, float((p - a) @ ab) / L2))
        q = a + f * ab; d = float(np.linalg.norm(p - q))
        if d < best:
            best, ch_best = d, k + f
        chain += math.sqrt(L2)
    return best, ch_best
xt = np.array([xtrack(n, e) for n, e in zip(dn, de)])
xt_err, wp_index = xt[:, 0], xt[:, 1]
plan_alt_at = np.interp(wp_index, np.arange(len(plan_alt)), plan_alt)
alt_err = relalt - plan_alt_at
flying = (rel > 15) & (t_pos < t_rtl)

# battery ---------------------------------------------------------------------
v0 = float(bat[bat[:, 0] < t_to - 5, 1].mean()) if (bat[:, 0] < t_to - 5).any() else float(bat[0, 1])
v_hover = float(bat[(bat[:, 0] > t_to + 5) & (bat[:, 0] < t_to + 25), 1].mean())
vmin = float(bat[:, 1].min())
v_fs = float(bat[np.argmin(abs(bat[:, 0] - t_fs)), 1])
v_rest_end = float(bat[bat[:, 0] > bat[-1, 0] - 5, 1].mean())
v_at_far = float(bat[(bat[:, 0] > far_t - 10) & (bat[:, 0] < far_t + 10), 1].mean())

# link records ---------------------------------------------------------------------
mt = mav1[:, 0]
dtm = np.diff(mt)
rx_rate = np.diff(mav1[:, 2]) / dtm
tx_rate = np.diff(mav1[:, 1]) / dtm
rx_drop = np.diff(mav1[:, 3])
gap_t = mt[1:][rx_rate < 0.5]
gaps = []
for g in gap_t:
    j = int(np.argmin(abs(t_pos - g)))
    gaps.append(dict(t_log=float(g), t_since_takeoff=float(g - t_to), hdist=float(hdist[j]), dist3d=float(dist3d[j]), alt=float(relalt[j]),
                     utc=utc_at(g).astimezone(CDT).strftime("%H:%M:%S")))
dist_at = lambda t: float(np.interp(t, t_pos, dist3d))
rs_mask = (rssi[:, 0] > t_to) & (rssi[:, 0] < t_land)
lq = rssi[rs_mask, 2]; lq_t = rssi[rs_mask, 0]
lq_d = np.array([dist_at(t) for t in lq_t])
lq_out = lq_t < far_t
dips = []
cur = None
for t, q in zip(lq_t, lq):
    if q < 90:
        if cur is None:
            cur = [t, t, q]
        else:
            cur[1] = t; cur[2] = min(cur[2], q)
    elif cur is not None:
        dips.append(cur); cur = None
if cur: dips.append(cur)
dip_rows = [dict(start=d0 - t_to, dur=d1 - d0 + 0.1, minlq=mq, dist=dist_at(d0), alt=float(np.interp(d0, t_pos, relalt))) for d0, d1, mq in dips]

# free-space path loss at 907 MHz (theory only) -----------------------------------------
fspl = lambda d_m, f_mhz: 20 * math.log10(d_m / 1000.0) + 20 * math.log10(f_mhz) + 32.44

res = dict(
    log=LOG, date_local=utc_at(t_to).astimezone(CDT).strftime("%Y-%m-%d"), takeoff_local=utc_at(t_to).astimezone(CDT).strftime("%H:%M:%S"),
    land_local=utc_at(t_land).astimezone(CDT).strftime("%H:%M:%S"),
    armed_s=float(t_end - t_pos[0]), airborne_s=float(t_land - t_to), auto_s=float(t_rtl - t_auto), loiter_start_rel=float(t_loiter - t_to),
    max_h=float(hdist.max()), max_3d=float(dist3d.max()), max_alt=float(relalt.max()), max_alt_msl=float(pos[:, 4].max()),
    out_len=out_len, ret_len=ret_len, far_rel=float(far_t - t_to), t_rtl_rel=float(t_rtl - t_to), t_fs_rel=float(t_fs - t_to),
    cruise_mean=float(cruise.mean()), cruise_median=float(np.median(cruise)), cruise_max=float(gs.max()),
    ret_mean=float(ret_cruise.mean()), moving_avg_out=out_len / (far_t - t_to), moving_avg_all=(out_len + ret_len) / (t_land - t_to),
    xt_mean=float(xt_err[flying].mean()), xt_p95=float(np.percentile(xt_err[flying], 95)), xt_max=float(xt_err[flying].max()),
    alt_err_mean=float(np.abs(alt_err[flying]).mean()), alt_err_max=float(np.abs(alt_err[flying]).max()),
    v0=v0, v_hover=v_hover, vmin=vmin, v_fs=v_fs, v_rest_end=v_rest_end, v_at_far=v_at_far, cell_fs=v_fs / 4,
    nsats_min=int(gps[:, 2].min()), hdop_max=float(gps[:, 3].max()),
    uplink_gaps=gaps, rx_rate_mean=float(rx_rate.mean()), tx_rate_mean=float(tx_rate.mean()), rx_dropped=int(rx_drop.sum()),
    lq_min=float(lq.min()), lq_mean=float(lq.mean()), lq_out_mean=float(lq[lq_out].mean()), lq_ret_mean=float(lq[~lq_out].mean()),
    lq_below90_s=float((lq < 90).sum() * 0.1), lq_dips=dip_rows[:20], lq_n_dips=len(dip_rows),
    lq_by_bin=[dict(lo=lo, hi=lo + 250, n=int(((lq_d >= lo) & (lq_d < lo + 250)).sum()),
                    mean=float(lq[(lq_d >= lo) & (lq_d < lo + 250)].mean()) if ((lq_d >= lo) & (lq_d < lo + 250)).any() else None,
                    min=float(lq[(lq_d >= lo) & (lq_d < lo + 250)].min()) if ((lq_d >= lo) & (lq_d < lo + 250)).any() else None)
               for lo in range(0, 1750, 250)],
    fspl_1500=fspl(1500, 907), fspl_1520_3d=fspl(1520, 907),
    params={k: parm.get(k) for k in ("WP_SPD", "WP_SPD_DN", "RTL_ALT_M", "RTL_SPEED_MS", "BATT_LOW_VOLT", "BATT_CRT_VOLT", "BATT_FS_LOW_ACT",
                                    "BATT_FS_CRT_ACT", "BATT_VOLT_MULT", "FENCE_ENABLE", "FS_OPTIONS", "FS_THR_ENABLE")},
    msgs=[(round(t - t_to, 1), s) for t, s in msgs if t > t_to - 20][:40],
)
json.dump(res, open("results.json", "w"), indent=1, default=float)
print(json.dumps({k: v for k, v in res.items() if k not in ("msgs", "lq_dips", "lq_by_bin")}, indent=1, default=float))
print(res["lq_by_bin"])
print(res["lq_dips"][:8])

# ---------------------------------------------------------------- charts
plt.rcParams.update({"font.size": 9, "axes.grid": True, "grid.alpha": 0.3})
C_OUT, C_RET = "#1565c0", "#e65100"

# 1. flight profile
fig, ax = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
sel = (rel > -10) & (t_pos < t_land + 20)
ax[0].plot(rel[sel], hdist[sel], color="#222"); ax[0].set_ylabel("distance from home (m)")
ax[0].axhline(1500, color="gray", ls="--", lw=0.8); ax[0].text(rel[sel][0], 1520, "planned far point 1500 m", fontsize=8)
ax[1].plot(rel[sel], relalt[sel], color="#c2185b", label="actual"); ax[1].set_ylabel("altitude above home (m)")
ta = np.linspace(0, PLAN["total_path"], 300)
ax[1].axhline(200, color="gray", ls="--", lw=0.8); ax[1].text(rel[sel][0], 203, "planned peak 200 m", fontsize=8)
ax[2].plot(gs_t[(gs_t > t_to - 10) & (gs_t < t_land + 20)] - t_to, gs[(gs_t > t_to - 10) & (gs_t < t_land + 20)], color="#2e7d32")
ax[2].axhline(10, color="gray", ls="--", lw=0.8); ax[2].text(5, 10.3, "planned 10 m/s", fontsize=8); ax[2].set_ylabel("ground speed (m/s)")
ax[2].set_xlabel("seconds since takeoff")
for a in ax:
    a.axvline(t_loiter - t_to, color="gray", lw=0.6); a.axvline(t_rtl - t_to, color="#b71c1c", lw=0.8)
ax[0].text(t_rtl - t_to + 3, 700, "RTL +\nbattery\nfailsafe", color="#b71c1c", fontsize=8)
ax[0].set_title("Flight profile (flight-controller log #17)")
fig.tight_layout(); fig.savefig(f"{OUT}/01_flight_profile.png", dpi=150); plt.close(fig)

# 2. battery
fig, ax = plt.subplots(figsize=(10, 4.2))
bs = (bat[:, 0] > t_to - 20)
ax.plot(bat[bs, 0] - t_to, bat[bs, 1], color="#6a1b9a", label="pack voltage (4S)")
ax.axhline(float(parm["BATT_LOW_VOLT"]), color="#f9a825", ls="--", label=f"low-battery failsafe {parm['BATT_LOW_VOLT']:.1f} V (saved)")
ax.axhline(float(parm["BATT_CRT_VOLT"]), color="#c62828", ls="--", label=f"critical failsafe {parm['BATT_CRT_VOLT']:.1f} V (saved)")
ax.axhline(14.8, color="#9e9e9e", ls=":", label="14.8 V (3.70 V/cell) recommended low-battery value")
ax2 = ax.twinx(); ax2.plot(rel[sel], relalt[sel], color="#c2185b", alpha=0.35, lw=1); ax2.set_ylabel("altitude (m)"); ax2.grid(False)
ax.set_ylabel("volts"); ax.set_xlabel("seconds since takeoff"); ax.legend(fontsize=8, loc="lower left"); ax.set_ylim(13.4, 17)
ax.set_title("Battery voltage (voltage only: this aircraft has no current sensor)")
fig.tight_layout(); fig.savefig(f"{OUT}/02_battery.png", dpi=150); plt.close(fig)

# 3. control link quality vs 3D distance
fig, ax = plt.subplots(1, 2, figsize=(10, 4))
ax[0].plot(lq_d[lq_out], lq[lq_out], ".", ms=2.5, color=C_OUT, label="outbound")
ax[0].plot(lq_d[~lq_out], lq[~lq_out], ".", ms=2.5, color=C_RET, label="return")
ax[0].set_xlabel("3D distance from home (m)"); ax[0].set_ylabel("ELRS control-link quality (%)"); ax[0].set_ylim(60, 102); ax[0].legend(markerscale=4)
ax[0].set_title("Control link (ELRS 2.4 GHz) vs distance")
la = np.array([float(np.interp(t, t_pos, relalt)) for t in lq_t])
ax[1].plot(la[lq_out], lq[lq_out], ".", ms=2.5, color=C_OUT); ax[1].plot(la[~lq_out], lq[~lq_out], ".", ms=2.5, color=C_RET)
ax[1].set_xlabel("altitude above home (m)"); ax[1].set_ylim(60, 102); ax[1].set_title("Control link vs altitude")
fig.tight_layout(); fig.savefig(f"{OUT}/03_control_link_vs_distance.png", dpi=150); plt.close(fig)

# 4. telemetry uplink over time
fig, ax = plt.subplots(2, 1, figsize=(10, 5), sharex=True)
tt = mt[1:] - t_to
ax[0].step(tt, rx_rate, where="post", color="#00695c"); ax[0].set_ylabel("packets/s received\nfrom ground station"); ax[0].set_ylim(-0.1, 2.2)
for g in gaps:
    ax[0].axvline(g["t_since_takeoff"], color="red", lw=1)
    ax[0].text(g["t_since_takeoff"] + 3, 1.7, f"gap at {g['hdist']:.0f} m", color="red", fontsize=8)
ax[1].plot(tt, dist3d[[int(np.argmin(abs(t_pos - t))) for t in mt[1:]]], color="#222"); ax[1].set_ylabel("3D distance (m)"); ax[1].set_xlabel("seconds since takeoff")
ax[0].set_title("Ground-station-to-drone telemetry uplink (flight controller's MAVLink counters, telemetry port)")
fig.tight_layout(); fig.savefig(f"{OUT}/04_telemetry_uplink.png", dpi=150); plt.close(fig)

# 5. tracking
fig, ax = plt.subplots(2, 1, figsize=(10, 5), sharex=True)
ax[0].plot(rel[flying], xt_err[flying], color="#00838f"); ax[0].set_ylabel("distance from planned route (m)")
ax[1].plot(rel[flying], alt_err[flying], color="#ad1457"); ax[1].set_ylabel("altitude vs plan (m)"); ax[1].set_xlabel("seconds since takeoff")
ax[0].set_title("How closely the flight followed the planned route")
fig.tight_layout(); fig.savefig(f"{OUT}/05_route_tracking.png", dpi=150); plt.close(fig)

# 6. map
from tiles import mosaic, latlon_to_px
img, meta = mosaic(33.7215, -85.9140, 33.7405, -85.9020, 17)
xa, ya = latlon_to_px(33.7405, -85.9140, meta); xb, yb = latlon_to_px(33.7215, -85.9020, meta)
img = img.crop((int(xa), int(ya), int(xb), int(yb)))
px = lambda la, lo: tuple(np.array(latlon_to_px(la, lo, meta)) - np.array([int(xa), int(ya)]))
fig, ax = plt.subplots(figsize=(6.5, 9), dpi=150)
ax.imshow(img)
P = np.array([px(a, b) for a, b in zip(lat, lon)])
o = (t_pos <= far_t) & (rel > -5); r = (t_pos > far_t) & (t_pos < t_land + 5)
ax.plot(P[o, 0], P[o, 1], color="#40c4ff", lw=1.6, label="flown outbound")
ax.plot(P[r, 0], P[r, 1], color="#ffab40", lw=1.6, label="flown return")
W = np.array([px(a, b) for a, b in wps])
ax.plot(W[:, 0], W[:, 1], "o--", color="#ff2bd6", ms=4, lw=0.8, label="planned waypoints")
for g in gaps:
    j = int(np.argmin(abs(t_pos - g["t_log"]))); ax.plot(P[j, 0], P[j, 1], "x", color="red", ms=10, mew=2)
    ax.text(P[j, 0] + 10, P[j, 1], f"telemetry uplink gap\n{g['hdist']:.0f} m", color="red", fontsize=7, bbox=dict(fc="white", alpha=0.7, pad=1))
ax.set_xlim(0, img.size[0]); ax.set_ylim(img.size[1], 0); ax.axis("off"); ax.legend(loc="upper left", fontsize=7)
ax.set_title("Flown track on satellite imagery (Esri World Imagery)", fontsize=9)
fig.tight_layout(); fig.savefig(f"{OUT}/06_track_map.png"); plt.close(fig)
print("charts written")
