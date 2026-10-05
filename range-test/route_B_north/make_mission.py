"""Build the 1.5 km range-test mission: waypoint file, tables, terrain check, battery estimate."""
import json, math, csv
import numpy as np
from route_def import LAUNCH, LAUNCH_ASL, dist, bearing
from build_route import build, truncate_at_straight, resample, cumulative
from elev import elevation

# ---------------------------------------------------------------- parameters
ALT_START, ALT_FAR = 30.0, 200.0
SPEED = 10.0
LOITER_S = 30

# ---------------------------------------------------------------- route
from build_route import build_north
path, keys, air, pelham, main = build_north()
path = truncate_at_straight(path)
wps, total = resample(path, keep=[keys["a_end"], keys["cross"], keys["turn"], keys["cross2"], keys["camp"]])
N = len(wps) - 1                         # outbound waypoints 1..N ; N = far point
leg = [0.0] + [dist(a, b) for a, b in zip(wps, wps[1:])]
cum = np.cumsum(leg)
straight = [dist(LAUNCH, w) for w in wps]
alt_out = [ALT_START + (ALT_FAR - ALT_START) * k / N for k in range(N + 1)]

# ---------------------------------------------------------------- crossings of other roads
roads = {e["id"]: [(g["lat"], g["lon"]) for g in e["geometry"]] for e in json.load(open("osm_roads.json"))["elements"]}
followed = {6249938, 6250654, 6254977}


def seg_intersect(p1, p2, q1, q2):
    def xy(p):
        return ((p[1] - LAUNCH[1]) * 92300.0, (p[0] - LAUNCH[0]) * 111000.0)
    a, b, c, d = map(xy, (p1, p2, q1, q2))
    r = (b[0] - a[0], b[1] - a[1]); s = (d[0] - c[0], d[1] - c[1])
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) < 1e-9:
        return None
    t = ((c[0] - a[0]) * s[1] - (c[1] - a[1]) * s[0]) / den
    u = ((c[0] - a[0]) * r[1] - (c[1] - a[1]) * r[0]) / den
    if 0 <= t <= 1 and 0 <= u <= 1:
        ang = abs(math.degrees(math.atan2(r[1], r[0]) - math.atan2(s[1], s[0]))) % 180
        ang = min(ang, 180 - ang)
        return (p1[0] + (p2[0] - p1[0]) * t, p1[1] + (p2[1] - p1[1]) * t), ang
    return None


crossings = []
for rid, pts in roads.items():
    for a, b in zip(path, path[1:]):
        for c, d in zip(pts, pts[1:]):
            x = seg_intersect(a, b, c, d)
            if x:
                crossings.append(dict(road=rid, lat=x[0][0], lon=x[0][1], angle=x[1],
                                      dist_from_launch=dist(LAUNCH, x[0]), followed=rid in followed))
crossings.sort(key=lambda c: c["dist_from_launch"])

# ---------------------------------------------------------------- terrain
launch_elev = elevation(*LAUNCH)
wp_elev = [elevation(*w) for w in wps]
ch = cumulative(path)
samples = []
s = 0.0
while s <= ch[-1] + 1e-6:
    j = max(i for i in range(len(path)) if ch[i] <= s + 1e-9)
    if j >= len(path) - 1:
        p = path[-1]
    else:
        f = (s - ch[j]) / (ch[j + 1] - ch[j])
        p = (path[j][0] + (path[j + 1][0] - path[j][0]) * f, path[j][1] + (path[j + 1][1] - path[j][1]) * f)
    samples.append((s, p))
    s += 25.0
prof = [(s, p, elevation(*p)) for s, p in samples]


def agl_planned(alt_rel, ground):
    return launch_elev + alt_rel - ground


def alt_at(s):
    return float(np.interp(s, cum, alt_out))


min_clear = min(agl_planned(alt_at(s), e) for s, p, e in prof)

# ---------------------------------------------------------------- mission file
lines = ["QGC WPL 110"]
seq = 0


def add(frame, cmd, p1, p2, p3, p4, lat, lon, alt, cur=0):
    global seq
    lines.append(f"{seq}\t{cur}\t{frame}\t{cmd}\t{p1}\t{p2}\t{p3}\t{p4}\t{lat:.8f}\t{lon:.8f}\t{alt:.6f}\t1")
    seq += 1


add(0, 16, 0, 0, 0, 0, LAUNCH[0], LAUNCH[1], launch_elev, cur=1)       # seq 0 = home
add(3, 22, 0, 0, 0, 0, 0.0, 0.0, ALT_START)                             # TAKEOFF to 30 m (relative frame)
add(3, 178, 1, SPEED, -1, 0, 0.0, 0.0, 0.0)                             # DO_CHANGE_SPEED 10 m/s ground speed
for k in range(1, N):                                                    # outbound waypoints
    add(3, 16, 0, 0, 0, 0, wps[k][0], wps[k][1], round(alt_out[k], 1))
add(3, 19, LOITER_S, 0, 0, 0, wps[N][0], wps[N][1], ALT_FAR)            # far point: LOITER_TIME 30 s
for k in range(N - 1, 0, -1):                                            # return leg, same coordinates, descending
    add(3, 16, 0, 0, 0, 0, wps[k][0], wps[k][1], round(alt_out[k], 1))
add(3, 20, 0, 0, 0, 0, 0.0, 0.0, 0.0)                                    # RTL, lands via RTL_ALT_FINAL_M = 0
open("range_test_1500m_north.waypoints", "w", newline="\n").write("\n".join(lines) + "\n")

# ---------------------------------------------------------------- table
rows = []
for k in range(0, N + 1):
    climb = 0.0 if k == 0 else math.degrees(math.atan2(alt_out[k] - alt_out[k - 1], leg[k]))
    agl = agl_planned(alt_out[k], wp_elev[k])
    rows.append(dict(wp=k, lat=wps[k][0], lon=wps[k][1], leg_m=leg[k], path_m=float(cum[k]), straight_m=straight[k],
                     alt_rel=alt_out[k], climb_deg=climb, ground_m=wp_elev[k], agl_m=agl,
                     warn_lt50=agl < 50, over_122=agl > 122))
with open("waypoint_table.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)


# ---------------------------------------------------------------- battery / time model
def time_energy(P_hover, mass_kg=1.7, overhead_w=10.0):
    t_total = 0.0
    e_total = 0.0

    def seg(dist_h, dalt, fwd=True):
        nonlocal t_total, e_total
        t = max(dist_h / SPEED, abs(dalt) / (2.5 if dalt > 0 else 1.5))
        p = P_hover * (1.05 if fwd else 1.0) + overhead_w
        if dalt > 0:
            p += mass_kg * 9.81 * (dalt / t) / 0.55
        if dalt < 0:
            p -= min(0.3 * P_hover, mass_kg * 9.81 * (-dalt / t) * 0.3)
        t_total += t
        e_total += p * t / 3600

    def hold(sec, fac=1.0):
        nonlocal t_total, e_total
        t_total += sec
        e_total += (P_hover * fac + overhead_w) * sec / 3600

    seg(0, ALT_START, fwd=False)
    for k in range(1, N + 1):
        seg(leg[k], alt_out[k] - alt_out[k - 1]); hold(3)        # 3 s per waypoint for slow-down / turn
    hold(LOITER_S)
    for k in range(N, 1, -1):
        seg(leg[k], alt_out[k - 1] - alt_out[k]); hold(3)
    seg(straight[1], 0)                                          # RTL from last return waypoint, direct
    hold(5)                                                      # RTL_LOIT_TIME 5 s
    h = alt_out[1]
    hold((h - 10) / 1.5 + 10 / 0.5, 0.95)                        # descend at WP_SPD_DN 1.5 to 10 m, then 0.5 m/s
    return t_total, e_total


BATT_WH = 5.2 * 14.8
scen = {}
for name, P in dict(low=170, nominal=220, high=280).items():
    t, e = time_energy(P)
    t_far = straight[N] / 10.0 + (ALT_FAR - 10) / 1.5 + 10 / 0.5 + 5
    e_far = ((P * 1.05 + 10) * straight[N] / 10.0 + (P * 0.95 + 10) * ((ALT_FAR - 10) / 1.5 + 20) + (P + 10) * 5) / 3600
    scen[name] = dict(P_hover=P, hover_A=P / 15.2, time_s=t, energy_Wh=e, used_pct=100 * e / BATT_WH,
                      reserve_pct=100 - 100 * e / BATT_WH, endurance_min_to_30pct=(0.7 * BATT_WH) / (P * 1.05 + 10) * 60,
                      rtl_far_s=t_far, rtl_far_Wh=e_far, rtl_far_pct=100 * e_far / BATT_WH)

out = dict(launch=LAUNCH, launch_elev_epqs=launch_elev, launch_asl_mp=LAUNCH_ASL, wps=wps, N=N, leg=leg, cum=cum.tolist(),
           straight=straight, alt_out=alt_out, wp_elev=wp_elev, rows=rows, path=path, total_path=float(cum[-1]),
           crossings=crossings, profile=[(s, p[0], p[1], e) for s, p, e in prof], scen=scen, min_clear=min_clear,
           batt_wh=BATT_WH, far_bearing=bearing(LAUNCH, wps[N]))
json.dump(out, open("mission_data.json", "w"), indent=1, default=float)

print("N outbound wps", N, "path", round(float(cum[-1])), "m; straight", round(straight[N], 1), "m; bearing", round(out["far_bearing"], 1))
for r in rows:
    print({k: (round(v, 6) if k in ("lat", "lon") else round(v, 1) if isinstance(v, float) else v) for k, v in r.items()})
print("launch elev EPQS", launch_elev, "min planned clearance along path", round(min_clear, 1))
for c in crossings:
    print("crossing", c["road"], round(c["lat"], 5), round(c["lon"], 5), round(c["angle"]), "deg", round(c["dist_from_launch"]), "m", "FOLLOWED" if c["followed"] else "")
for k, v in scen.items():
    print(k, {a: round(b, 1) for a, b in v.items()})
