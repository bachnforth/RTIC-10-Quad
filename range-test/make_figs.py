"""Satellite route map + side-view altitude chart + recovery table data."""
import json, math
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle
from route_def import LAUNCH, G, dist, bearing
from tiles import mosaic, latlon_to_px

D = json.load(open("mission_data.json"))
wps = [tuple(w) for w in D["wps"]]
N = D["N"]
alt = D["alt_out"]
rows = D["rows"]
prof = D["profile"]
launch_elev = D["launch_elev_epqs"]

# ---------------------------------------------------------------- access points chosen from access_points.py output
APS = [
    ("A", "Launch / hangar apron", 33.72339, -85.90631, 0),
    ("B", "Airfield road meets Pelham Range Rd (4-way)", 33.72726, -85.90846, 975),
    ("C", "Pelham Range Rd bend, north of airfield", 33.72802, -85.90939, 1098),
    ("D", "Pelham Range Rd meets the north-south road", 33.72911, -85.91129, 1312),
    ("E", "N-S road meets east-west dirt road", 33.73052, -85.91066, 1480),
    ("F", "N-S road meets west dirt road (pasture gate area)", 33.73289, -85.91056, 1744),
    ("G", "N-S road, north junction", 33.73826, -85.91046, 2339),
]
json.dump(APS, open("access_points_chosen.json", "w"))

# ---------------------------------------------------------------- landing-zone model (assumption, not a measurement)
def fall_zone(h_agl, v_h=10.0, wind=5.0, tau=3.0):
    t = 1.2 * math.sqrt(2 * max(h_agl, 1) / 9.81)                  # fall time, with drag and prop windmilling ~20% longer than vacuum
    carry = v_h * tau * (1 - math.exp(-t / tau))                    # distance carried by forward speed
    drift = wind * (t - tau * (1 - math.exp(-t / tau)))             # wind push
    return t, carry, drift
zones = []
for r in rows:
    if r["wp"] == 0:
        continue
    t, carry, d5 = fall_zone(r["agl_m"], wind=5.0)
    _, _, d10 = fall_zone(r["agl_m"], wind=10.0)
    zones.append(dict(wp=r["wp"], agl=r["agl_m"], fall_s=t, carry=carry, R5=carry + d5, R10=carry + d10))

# ---------------------------------------------------------------- imagery
lat0, lon0, lat1, lon1 = 33.7215, -85.9140, 33.7405, -85.9030
img, meta = mosaic(lat0, lon0, lat1, lon1, 17)
xa, ya = latlon_to_px(lat1, lon0, meta)
xb, yb = latlon_to_px(lat0, lon1, meta)
img = img.crop((int(xa), int(ya), int(xb), int(yb)))
def px(p):
    x, y = latlon_to_px(p[0], p[1], meta)
    return x - int(xa), y - int(ya)
mpp = dist((lat0, lon0), (lat0, lon1)) / img.size[0]        # metres per pixel

# classify the ground under each landing zone from the imagery (dark = trees, light = grass/field)
arr = np.asarray(img.convert("L"), dtype=float)
def cover(p, rad_m):
    x, y = px(p); r = rad_m / mpp
    yy, xx = np.ogrid[:arr.shape[0], :arr.shape[1]]
    m = (xx - x) ** 2 + (yy - y) ** 2 <= r * r
    return float(arr[m].mean()), float(arr[m].std())
for z in zones:
    z["lum"], z["sd"] = cover(wps[z["wp"]], max(10, z["R5"]))
    print("WP", z["wp"], "R5", round(z["R5"]), "lum", round(z["lum"]), "sd", round(z["sd"]))
json.dump(zones, open("landing_zones.json", "w"), indent=1)

# ---------------------------------------------------------------- map
fig, ax = plt.subplots(figsize=(8.2, 11.4), dpi=170)
ax.imshow(img)
roads = json.load(open("osm_roads.json"))["elements"]
for e in roads:
    pts = [px((g["lat"], g["lon"])) for g in e["geometry"]]
    ax.plot(*zip(*pts), color="#ffe94d", lw=0.7, alpha=0.8)
# corridor (+/-150 m)
path = [tuple(p) for p in D["path"]]
# direct RTL line from far point
ax.plot(*zip(px(wps[N]), px(LAUNCH)), color="#ff8c00", lw=1.2, ls="--")
ax.text(*px((33.7300, -85.9070)), "straight-line RTL / failsafe return\n(if mission is abandoned at far point)", color="#ff8c00", fontsize=6.5, ha="left")
# route
ax.plot(*zip(*[px(w) for w in wps]), color="#ff2bd6", lw=1.6)
# landing zones
for z in zones:
    cx, cy = px(wps[z["wp"]])
    ax.add_patch(Circle((cx, cy), z["R5"] / mpp, fill=False, ec="#00e5ff", lw=0.9, ls=":"))
# waypoints
for i, w in enumerate(wps):
    x, y = px(w)
    ax.plot(x, y, "o", ms=4.5, mfc="white", mec="#ff2bd6", mew=1.2)
    ax.text(x + 9, y - 6, "HOME/WP0" if i == 0 else (f"WP{i}  {alt[i]:.0f} m" + ("  FAR 1500 m" if i == N else "")), color="white", fontsize=6.5,
            bbox=dict(fc="black", alpha=0.55, pad=1.0, ec="none"))
# crossings
CROSS = [(33.72683, -85.90768, "X1 Pelham Range Rd (paved) - cross at ~90 deg"),
         (33.73057, -85.91017, "X2 dirt road"),
         (33.73290, -85.91007, "X3 dirt farm track (unmapped)")]
for la, lo, t in CROSS:
    x, y = px((la, lo))
    ax.plot(x, y, "x", color="red", ms=8, mew=2)
    if t.startswith("X1"):
        ax.text(x - 12, y + 3, t, color="red", fontsize=6.3, ha="right", bbox=dict(fc="white", alpha=0.75, pad=1.0, ec="none"))
    else:
        ax.text(x + 14, y + 22, t, color="red", fontsize=6.3, ha="left", bbox=dict(fc="white", alpha=0.75, pad=1.0, ec="none"))
# access points
for lab, name, la, lo, drv in APS:
    x, y = px((la, lo))
    ax.plot(x, y, "s", ms=7, mfc="#1f77ff", mec="white", mew=1)
    ax.text(x, y, lab, color="white", fontsize=5.5, ha="center", va="center", weight="bold")
# hazard: compound
cx, cy = px((33.7350, -85.9074))
ax.add_patch(Circle((cx, cy), 35 / mpp, fill=False, ec="red", lw=1.0))
ax.text(cx + 40, cy, "buildings / vehicles\n(not under route, ~280 m east)", color="white", fontsize=6, bbox=dict(fc="red", alpha=0.6, pad=1, ec="none"))
# scale bar + north arrow
ax.plot([40, 40 + 250 / mpp], [img.size[1] - 40] * 2, color="white", lw=3)
ax.text(40, img.size[1] - 55, "250 m", color="white", fontsize=7)
ax.annotate("N", xy=(img.size[0] - 50, 80), xytext=(img.size[0] - 50, 150), color="white", ha="center", fontsize=10,
            arrowprops=dict(arrowstyle="-|>", color="white"))
# legend
from matplotlib.lines import Line2D
h = [Line2D([], [], color="#ff2bd6", lw=1.6, label="planned route (45 m beside the road)"),
     Line2D([], [], color="#ffe94d", lw=0.8, label="roads (OpenStreetMap)"),
     Line2D([], [], color="#ff8c00", lw=1.2, ls="--", label="direct RTL line"),
     Line2D([], [], marker="x", color="red", ls="", ms=7, mew=2, label="road crossing"),
     Line2D([], [], marker="s", color="#1f77ff", ls="", ms=6, label="access point (A-G)"),
     Line2D([], [], color="#00e5ff", ls=":", lw=1, label="likely landing zone if power lost (5 m/s wind)")]
ax.legend(handles=h, loc="upper left", fontsize=6.3, framealpha=0.8)
ax.set_xlim(0, img.size[0]); ax.set_ylim(img.size[1], 0)
ax.set_title("Clark Range 1.5 km range-test route (satellite: Esri World Imagery; roads: OpenStreetMap)", fontsize=8)
ax.axis("off")
fig.tight_layout()
fig.savefig("route_map.png")
plt.close(fig)

# ---------------------------------------------------------------- side view
cum = D["cum"]
S = np.array([p[0] for p in prof]); E = np.array([p[3] for p in prof]) - launch_elev     # ground relative to launch
tot = D["total_path"]
sc = np.array(cum)
# profile path-distance is along the original polyline; rescale to the chord total so it lines up with waypoints
S = S * (tot / S[-1])
alt_s = np.interp(S, sc, alt)
fig, ax = plt.subplots(figsize=(11, 5), dpi=150)
x_out = S; x_ret = tot + (tot - S[::-1])
ground_x = np.concatenate([x_out, x_ret]); ground_y = np.concatenate([E, E[::-1]])
ax.fill_between(ground_x, ground_y - 40, ground_y, color="#8b7355", alpha=0.9, label="ground (USGS 3DEP)")
ax.fill_between(ground_x, ground_y, ground_y + 25, color="#2e7d32", alpha=0.35, label="typical tree canopy (~25 m, assumed)")
ret_alt = alt_s[::-1].copy()
ret_alt = np.maximum(ret_alt, alt[1])            # return mission ends at WP1; RTL then flies home level and descends over home
ax.plot(ground_x, np.concatenate([alt_s, ret_alt]), color="#d81b60", lw=2.2, label="planned altitude (relative to launch)")
ax.annotate("RTL: fly home level,\nthen descend over launch", xy=(2 * tot - 150, alt[1]), xytext=(2 * tot - 650, 130), fontsize=7, arrowprops=dict(arrowstyle="-|>"))
ax.plot(ground_x, ground_y + 122, color="#e65100", lw=1.2, ls="--", label="122 m (400 ft) above ground")
ax.plot(ground_x, ground_y + 50, color="#1565c0", lw=1.0, ls=":", label="50 m above ground")
for k in range(0, N + 1):
    ax.plot(sc[k], alt[k], "o", color="white", mec="#d81b60")
    ax.text(sc[k], alt[k] + 6, f"WP{k}", ha="center", fontsize=7)
ax.annotate("30 s loiter\n(far point)", xy=(tot, 200), xytext=(tot, 228), ha="center", fontsize=8, arrowprops=dict(arrowstyle="-|>"))
ax.set_xlabel("distance flown along route (m)  ->  outbound 0 to %d m, return back to 0 at %d m" % (tot, 2 * tot))
ax.set_ylabel("height above launch point (m)")
ax.set_ylim(-30, 255)
ax.set_title("Altitude vs distance, outbound + return (vertical scale exaggerated)")
ax.axvline(tot, color="gray", lw=0.6)
ax.legend(fontsize=7, loc="lower center", ncol=3)
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig("altitude_profile.png")
print("saved")
