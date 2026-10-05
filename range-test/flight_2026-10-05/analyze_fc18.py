"""Flight-controller log #18 (2026-10-05): battery, failsafes, end of flight, GPS glitches lined up with the mesh dropouts."""
import json, math
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pymavlink import mavutil

LOG = "fc/log18.bin"
M = json.load(open("results_mesh.json"))
m = mavutil.mavlink_connection(LOG)
D = {k: [] for k in ("POS", "BAT", "GPS", "MSG", "MODE", "RCOU", "PARM", "ERR")}
while True:
    x = m.recv_match(type=list(D))
    if x is None:
        break
    D[x.get_type()].append(x)

pos = np.array([(p.TimeUS / 1e6, p.Lat, p.Lng, p.RelHomeAlt) for p in D["POS"]])
home = (pos[0, 1], pos[0, 2])
hd = np.hypot((pos[:, 1] - home[0]) * 111132.0, (pos[:, 2] - home[1]) * 111320.0 * math.cos(math.radians(home[0])))
d3 = np.hypot(hd, pos[:, 3])
bat = np.array([(b.TimeUS / 1e6, b.Volt) for b in D["BAT"]])
msgs = [(x.TimeUS / 1e6, x.Message) for x in D["MSG"]]
modes = [(x.TimeUS / 1e6, x.Mode) for x in D["MODE"]]
parm = {p.Name: p.Value for p in D["PARM"]}
t_to = float(pos[np.argmax(pos[:, 3] > 5), 0])
t_far = float(pos[np.argmax(d3), 0])
t_end = float(pos[-1, 0])
ev = lambda key: next((t for t, s in msgs if key in s), None)
t_low, t_crit, t_thrust = ev("is low"), ev("is critical"), ev("Thrust Loss")
t_rtl = next(t for t, md in modes if md == 6)
t_land = next(t for t, md in modes if md == 9)
glitches = [t for t, s in msgs if "GPS Glitch" in s]
cleared = [t for t, s in msgs if "Glitch cleared" in s]
OFF = M and 0  # placeholder to keep the offset explicit below
CLOCK_OFFSET = 24.0   # FC time = Pi time + 24.0 s, from matching the two distance records (mean mismatch 3.3 m)
pi_blackouts = [(b["t_rel"] + M["t_to"] + CLOCK_OFFSET, b["dur"], k) for k in ("rn03_ground", "phone") for b in M["blackouts"][k]]
j = lambda t: int(np.argmin(abs(pos[:, 0] - t)))
vat = lambda t: float(bat[np.argmin(abs(bat[:, 0] - t)), 1])

res = dict(
    log=LOG, t_to=t_to, t_far=t_far, t_end=t_end, auto_start=next(t for t, md in modes if md == 3),
    v_start=float(bat[bat[:, 0] < t_to - 5, 1].mean()), v_far=vat(t_far), v_min=float(bat[:, 1].min()), v_end=float(bat[-1, 1]),
    t_low_rel=t_low - t_to, t_rtl_rel=t_rtl - t_to, t_crit_rel=t_crit - t_to, t_land_rel=t_land - t_to, t_thrust_rel=t_thrust - t_to, t_end_rel=t_end - t_to,
    v_low=vat(t_low), v_crit=vat(t_crit), v_thrust=vat(t_thrust),
    dist_low=float(d3[j(t_low)]), dist_crit=float(d3[j(t_crit)]), dist_land_start=float(d3[j(t_land)]), alt_land_start=float(pos[j(t_land), 3]),
    end=dict(dist=float(d3[-1]), hdist=float(hd[-1]), alt=float(pos[-1, 3]), lat=float(pos[-1, 1]), lon=float(pos[-1, 2])),
    params={k: parm.get(k) for k in ("BATT_LOW_VOLT", "BATT_CRT_VOLT", "BATT_FS_LOW_ACT", "BATT_FS_CRT_ACT", "WP_SPD", "RTL_ALT_M", "RTL_SPEED_MS", "FENCE_ENABLE")},
    glitches=[dict(t_rel=g - t_to, dist=float(d3[j(g)])) for g in glitches],
    pi_blackouts_fc=[dict(t_rel=a - t_to, dur=d, node=k, dist=float(d3[j(a)])) for a, d, k in pi_blackouts],
    clock_offset=CLOCK_OFFSET,
    msgs=[(round(t - t_to, 1), s) for t, s in msgs if t >= t_to - 5],
)
rc = np.array([(x.TimeUS / 1e6, x.C1, x.C2, x.C3, x.C4) for x in D["RCOU"]])
res["motor_out_end_us"] = [float(v) for v in rc[-1, 1:]]
json.dump(res, open("results_fc.json", "w"), indent=1, default=float)
print(json.dumps({k: v for k, v in res.items() if k not in ("msgs",)}, indent=1, default=float)[:3000])

plt.rcParams.update({"font.size": 9, "axes.grid": True, "grid.alpha": 0.3})
rel = lambda t: t - t_to
fig, ax = plt.subplots(3, 1, figsize=(10.5, 8.6), sharex=True)
s = pos[:, 0] >= t_to - 10
ax[0].plot(rel(pos[s, 0]), d3[s], color="#222"); ax[0].set_ylabel("3D distance (m)")
ax2 = ax[0].twinx(); ax2.plot(rel(pos[s, 0]), pos[s, 3], color="#c2185b", alpha=0.5); ax2.set_ylabel("altitude (m)"); ax2.grid(False)
sb = bat[:, 0] >= t_to - 10
ax[1].plot(rel(bat[sb, 0]), bat[sb, 1], color="#6a1b9a")
ax[1].axhline(parm["BATT_LOW_VOLT"], color="#f9a825", ls="--", label=f"low-battery failsafe {parm['BATT_LOW_VOLT']:.1f} V")
ax[1].axhline(parm["BATT_CRT_VOLT"], color="#c62828", ls="--", label=f"critical failsafe {parm['BATT_CRT_VOLT']:.1f} V")
for t, lab, col in ((t_low, "low battery: RTL", "#f9a825"), (t_crit, "critical: Land", "#c62828"), (t_thrust, "thrust loss", "#000000")):
    for a in ax:
        a.axvline(rel(t), color=col, lw=0.9)
    ax[1].text(rel(t) - 4, 16.2, lab, rotation=90, va="top", ha="right", fontsize=8, color=col)
ax[1].set_ylabel("pack voltage (V)"); ax[1].legend(loc="lower left", fontsize=8); ax[1].set_ylim(5.5, 17)
for g, c in zip(glitches, cleared + [glitches[-1] + 5]):
    ax[2].axvspan(rel(g), rel(c), color="#00897b", alpha=0.5)
for a, d, k in pi_blackouts:
    ax[2].axvspan(rel(a), rel(a + d), ymin=0.0, ymax=0.45, color="#d81b60", alpha=0.8)
ax[2].set_yticks([]); ax[2].set_xlabel("seconds since takeoff")
ax[2].text(rel(glitches[0]) - 5, 0.8, "teal: GPS glitch / compass error", color="#00897b", fontsize=8, ha="right", transform=ax[2].get_xaxis_transform())
ax[2].text(rel(glitches[0]) - 5, 0.15, "pink: mesh ping blackouts (Pi clock lined up)", color="#d81b60", fontsize=8, ha="right", transform=ax[2].get_xaxis_transform())
ax[0].set_title("Flight controller log: battery, failsafes and the end of the flight")
fig.tight_layout(); fig.savefig("charts/m08_battery_failsafes_end.png", dpi=150)
print("chart written")
