"""Make the Route B plan from the Route A plan: replace the route-specific sections, keep the generic ones."""
import re, json

A = open("../route_A_nnw_alternative/RANGE_TEST_PLAN.md", encoding="utf-8").read()
D = json.load(open("mission_data.json"))
Z = json.load(open("recovery_table.json"))
rows = D["rows"]
sc = D["scen"]


def section(text, num):
    m = re.search(r"^## %s\. .*?(?=^## \d+\. |\Z)" % num, text, re.S | re.M)
    return m.group(0), m.start(), m.end()


def replace(text, num, new):
    _, a, b = section(text, num)
    return text[:a] + new.rstrip() + "\n\n" + text[b:]


def r1(x): return f"{x:.1f}"


# ------------------------------------------------------------------ section 0
S0 = """## 0. Decisions and checks only you can make

1. **Route.** You asked for a route that is generally north and follows roads, with dirt roads allowed. This plan (Route B) follows roads, including dirt roads, and ends 1500 m from launch at **bearing 4.7° (almost due north, 4.7° east of north)**. The earlier version, Route A, ends 12.6° west of north on a better road and is kept in `..\\route_A_nnw_alternative\\`. The tradeoffs are in section 2.
2. **Part of this route is only close to a road, not on one.** On the paved and gravel roads the route is 45 m beside the road. Over the pasture it is 45 to 85 m from the dirt road, and on the last 650 m it is 80 to 100 m east of a faint forest track, because of the camp (item 3). I placed the dirt-road and camp points by eye on the satellite image, because the mapped dirt road (a 2007 TIGER import) is misplaced. **Check the route on the ground and in Mission Planner's satellite view before flying.**
3. **A small camp with trailers and vehicles is about 100 m from the route.** It sits at the end of the dirt road, about 1.2 km out. I can't tell whether anyone is there. The route passes 90 m or more from the nearest building, which is outside the 76 m "power lost in a 10 m/s wind" landing radius. If someone lives or works there, tell them, or choose Route A, which stays 280 m away.
4. **Recovery gets worse at the far end.** The last two waypoints are over forest, and the nearest drivable road is about 225 m from the far point. See section 7.
5. **Land access.** This looks like former Fort McClellan / Pelham Range land (the map labels it, and OpenStreetMap shows roads named "Gate 3 Road" and "Gate 5 Road"). I can't confirm who owns it. Ask for permission to fly there and to walk off the roads, and **ask specifically about unexploded ordnance (UXO) before walking off a road to recover a drone.**
6. **Hover power is a guess.** I don't have your hover current, and your battery monitor has no current sensor. The battery numbers use 170, 220 and 280 W for hover. A 5-minute hover test with a clamp meter would replace the guess.
7. **Legal.** This mission needs an FAA waiver or other valid authorization. See section 11.
8. **Sharing telemetry with Mission Planner and QGroundControl** needs a small change to the Pi filter that I have not made. See section 13.
"""
out = replace(A, 0, S0)

# ------------------------------------------------------------------ section 2
tbl = ["| WP | Lat | Lon | Leg (m) | Straight-line from launch (m) | Altitude above launch (m) | Climb angle | Ground (m ASL) | Height above ground (m) |", "|---|---|---|---|---|---|---|---|---|"]
names = {0: "0 takeoff", 2: "2 (crossing X1)", 8: "8 far point"}
for r in rows:
    k = r["wp"]
    agl = f"**{r['agl_m']:.0f}**" if r["over_122"] else f"{r['agl_m']:.0f}"
    tbl.append(f"| {names.get(k, k)} | {r['lat']:.6f} | {r['lon']:.6f} | {r['leg_m']:.0f} | {r['straight_m']:.0f} | {r['alt_rel']:.1f} | {'n/a' if k == 0 else r1(r['climb_deg']) + '°'} | {r['ground_m']:.1f} | {agl} |")
S2 = f"""## 2. The route

Files: `range_test_1500m_north.waypoints` (load in Mission Planner), `route_map.png`, `altitude_profile.png`, `waypoint_table.csv`.

![route map](route_map.png)

**Why 45 m beside the road, not on it.** If the drone fails above a road it can hit a car or a person on the road, and flight over moving vehicles is restricted. If it fails 45 m to the side, the road is still close for walking or driving to it, and nobody is under it. 45 m is inside your 30 to 60 m window and far enough that a gust or GPS wander of 10 to 15 m won't put the drone over the road surface.

**How the route runs** (roads from OpenStreetMap, checked against satellite imagery):

1. **Launch to WP1 (309 m).** Northwest across the open airfield to a point 45 m east of the gravel airfield road.
2. **WP1 to WP2 (133 m), crossing X1.** Across Pelham Range Road, the only paved road, at about 88°. The crossing is at the end of the open field, where you can see along the road to the east.
3. **WP2 to WP4 (about 500 m).** Northwest along the north side of Pelham Range Road, then north along the east side of the north-south road, over forest canopy.
4. **WP4 to WP5 (260 m).** North, crossing a faint dirt track (X2) and then the dirt road that runs east into the pasture (X3). WP5 is at the pasture's edge.
5. **WP5 to WP6 (280 m).** East across the pasture, 45 to 85 m north of the dirt road, over open land. It crosses the pasture's dirt road (X4) near WP6.
6. **WP6 to WP8 (about 465 m).** Northeast through forest, 90 to 100 m east of the camp, then 80 to 100 m east of the forest track north. WP8 is the far point.

**Distances (checked in code).** The far point is **1500.0 m** from launch by WGS84 geodesic (the ellipsoid model of the Earth), and I checked the whole mission file a second way with the haversine (sphere) formula, which gives 1503.7 m. Mission Planner uses a sphere, so it will show about 1504 m. The outbound path actually flown is **{D['total_path']:.0f} m**, because the route bends around the roads. The straight-line bearing from launch to the far point is **{D['far_bearing']:.1f}°**.

{chr(10).join(tbl)}

The waypoints are 133 to 310 m apart, not exactly 250 m, because I put waypoints at the corners (for example WP1 and WP2 bracket the road crossing) and divided the straight stretches evenly. The altitude steps are even per waypoint (21.25 m each), so the climb angle is steeper on the short crossing leg (9.1°) than elsewhere (about 4 to 7°).

**Route A or Route B?**

| | Route A (`route_A_nnw_alternative`) | **Route B (this plan)** |
|---|---|---|
| Direction of far point | 12.6° west of north | **4.7° east of north** |
| Roads followed | Gravel airfield road, paved Pelham Range Rd, the north-south service road | Same as A for the first 1 km, then **dirt roads and a faint forest track** |
| Path flown out | 1615 m, 7 waypoints | 1947 m, 8 waypoints |
| Far end | Over open pasture, close to a road (146 m from the nearest drivable road) | **Over forest; nearest drivable road 225 m away** |
| Buildings near the route | Compound 280 m to the east | **Camp with trailers about 100 m away** |
| Road crossings (each way) | 3 | 4 |
| Battery used (nominal) | 41% | 47% |

**Road crossings (outbound; the return leg crosses each one again, so eight crossings in total).**

| # | Where | Type | Angle | Distance along route |
|---|---|---|---|---|
| X1 | 33.7268, -85.9077, at WP1 to WP2 | Pelham Range Road, paved, the only real road | about 88° | 354 to 366 m |
| X2 | about 33.7306, -85.9102, just south of WP4 | Faint dirt track into the marsh | about 87° | about 830 m |
| X3 | about 33.7329, -85.9100, just south of WP5 | Dirt road east into the pasture | about 90° | about 1150 m |
| X4 | about 33.7335, -85.9078, near WP6 | Dirt road along the pasture's east edge, which leads to the camp | about 90° | about 1400 m |

At X1 I recommend a spotter (a second person watching the road) to pause the mission if a vehicle appears. The sight line along the road is about 500 m to the east. Use "pause" in Auto mode (Mission Planner: Actions > Pause, or QGC: Pause).

**Populated areas.** The camp (trailers and vehicles) is about 100 m from the route at its closest. It is not under the route. The base buildings are about 400 m east of launch. A power-line corridor and a cell tower show on the map more than 2 km east. OpenStreetMap is incomplete and the imagery may be old, so **walk or drive the first kilometer before flying.**

**Water.** There is a marshy clearing east of the road at WP4 to WP5 (wet ground, not open water). No ponds under the route.
"""
out = replace(out, 2, S2)

# ------------------------------------------------------------------ section 3
S3 = """## 3. Altitude and terrain check

![altitude profile](altitude_profile.png)

- Ground along the route varies by only about 15 m (178 to 193 m above sea level), so the planned altitude above launch and the height above ground stay within 10 m of each other.
- **Fewer than 50 m of clearance:** the first part of the first leg, from takeoff at 30 m up to about 200 m along it. That part is over the open airfield with no trees within 300 m. Every waypoint from WP1 on has at least 55 m above ground. The legs over trees (WP2 onward) are 78 m or more above ground, so about 50 m or more above a 25 m tree canopy. I used 25 m as a typical tree height, which I did not measure. The USGS elevation data is bare ground, not treetops.
- **Higher than 122 m (400 ft) above the ground below:** WP5 (131 m), WP6 (156 m), WP7 (180 m), WP8 (198 m) and the legs between them. The 122 m limit is crossed about 1.1 km along the route. The same applies on the way back.
"""
out = replace(out, 3, S3)

# ------------------------------------------------------------------ section 6 numbers
nom, low, high = sc["nominal"], sc["low"], sc["high"]
tbl6 = f"""| Scenario | Flight time | Energy used | Remaining |
|---|---|---|---|
| Low (170 W hover) | {low['time_s']/60:.1f} min | {low['energy_Wh']:.0f} Wh, {low['used_pct']:.0f}% | **{low['reserve_pct']:.0f}%** |
| **Nominal (220 W)** | {nom['time_s']/60:.1f} min | {nom['energy_Wh']:.0f} Wh, {nom['used_pct']:.0f}% | **{nom['reserve_pct']:.0f}%** |
| High (280 W) | {high['time_s']/60:.1f} min | {high['energy_Wh']:.0f} Wh, {high['used_pct']:.0f}% | **{high['reserve_pct']:.0f}%** |"""
a, b, _ = (None, None, None)
m = re.search(r"\| Scenario \| Flight time.*?\n\n", out, re.S)
out = out[:m.start()] + tbl6 + "\n\n" + out[m.end():]
out = out.replace("The reserve is **above 30%** in all three cases, so no change is needed.", "The reserve is **above 30%** in all three cases, so no change is needed (the high case, with 41% left, is the one to watch).")

# ------------------------------------------------------------------ section 5 numbers
out = out.replace("The last return waypoint is at 54.3 m, so a normal end of mission has no extra climb.", "The last return waypoint is at 51.2 m, so a normal end of mission has a climb of about 4 m.")

# ------------------------------------------------------------------ section 7 tables
ground = {
    1: "Open mowed airfield", 2: "Road edge and forest edge", 3: "**Dense forest**",
    4: "**Forest**, faint track within 30 m", 5: "Open pasture edge and marsh", 6: "Forest at the pasture's east edge, dirt road within 40 m",
    7: "**Forest**, camp 90 m west", 8: "**Forest**, track 80 m west"}
t7 = ["| WP | Height (m) | Fall time | Radius, 5 m/s wind | Radius, 10 m/s wind | Ground there | Best access | Walk from access to WP |", "|---|---|---|---|---|---|---|---|"]
for z in Z:
    t7.append(f"| {z['wp']} | {z['agl']:.0f} | {z['fall_s']:.0f} s | {z['R5']:.0f} m | {z['R10']:.0f} m | {ground[z['wp']]} | {z['ap']} | {z['walk_m']:.0f} m |")
m = re.search(r"\| WP \| Height \(m\) \| Fall time.*?\n\n", out, re.S)
out = out[:m.start()] + "\n".join(t7) + "\n\n" + out[m.end():]
aps = """| ID | Location | Lat, Lon | Drive from launch (m) |
|---|---|---|---|
| A | Launch / hangar apron | 33.72339, -85.90631 | 0 |
| B | Airfield road meets Pelham Range Road | 33.72726, -85.90846 | 975 |
| C | Pelham Range Road bend | 33.72802, -85.90939 | 1098 |
| D | Pelham Range Road meets the north-south road | 33.72911, -85.91129 | 1312 |
| E | North-south road meets a faint dirt track | 33.73052, -85.91066 | 1480 |
| F | North-south road meets the dirt road to the pasture | 33.73289, -85.91056 | 1744 |
| G | Dirt road at the pasture's east side, toward the camp (OpenStreetMap shows a dead end) | 33.73285, -85.90822 | 1929 |
| H | North east-west road, where the forest track from the camp ends | 33.73928, -85.90463 | 2930 |

Drive distances from G and H are map estimates: the road network in the data may be missing links (for example the pasture road to the camp), and I can't tell whether a car can use the forest track."""
m = re.search(r"\| ID \| Location \| Lat, Lon.*?\n\n", out, re.S)
out = out[:m.start()] + aps + "\n\n" + out[m.end():]
out = out.replace("**What this means.** Failures at WP3 and WP4 (and partly WP2) come down in forest. A quad that lands in 25 m trees may hang in them, and you may need a tall pole or a tree service to get it down. The pasture legs (WP6 and WP7) and the airfield leg are the good recovery areas. This is the main cost of the \"nothing straight north\" choice in section 0.",
                  "**What this means.** Failures at WP3, WP4 and WP6 to WP8 (and partly WP2) come down in forest. A quad that lands in 25 m trees may hang in them, and you may need a tall pole or a tree service to get it down. Only the airfield leg and WP5 are good recovery areas. This is the cost of staying close to due north: Route A keeps the far end over pasture. A failure at WP7 or WP8 means a walk of 225 to 290 m through forest, possibly past the camp.")

# ------------------------------------------------------------------ section 15
S15 = """## 15. Files

All files are in `range-test\\route_B_north\\` unless noted.

| File | What it is |
|---|---|
| `range_test_1500m_north.waypoints` | The mission to load in Mission Planner |
| `range_test_changes.param` | Recommended parameter changes |
| `corridor_fence.poly` | Optional ±150 m corridor polygon for the geofence |
| `route_map.png`, `altitude_profile.png` | The map preview and the side view |
| `waypoint_table.csv`, `mission_data.json` | The computed numbers |
| `recovery_table.json`, `landing_zones.json`, `access_points_chosen.json` | The recovery data |
| `make_mission.py`, `build_route.py`, `make_figs.py`, `make_extras.py`, `verify_mission.py`, `build_plan.py` | The scripts that produced all of this (run with `..\\.venv\\Scripts\\python.exe`). The dirt-road points in `build_route.py` were placed by eye on the satellite image. |
| `..\\route_A_nnw_alternative\\` | Route A, the earlier version with all its files |
| `..\\.venv\\` | The isolated Python environment (pymavlink, numpy, pandas, matplotlib, reportlab and a bundled ffmpeg) |

Data sources: OpenStreetMap roads (© OpenStreetMap contributors, ODbL), Esri World Imagery tiles for the map, USGS 3DEP elevation.
"""
out = replace(out, 15, S15)
out = out.replace("# 1.5 km mesh-radio range test: plan, mission and checklists", "# 1.5 km mesh-radio range test: plan, mission and checklists (Route B, generally north)")
out = out.replace("Files are in this folder (`range-test\\`).", "Files are in this folder (`range-test\\route_B_north\\`).")
out = out.replace("`range_test_1500m.waypoints`", "`range_test_1500m_north.waypoints`")
out = out.replace("then 6 waypoints rising from 54.3 to 175.7 m, LOITER_TIME with 30 at 200 m, 6 waypoints back down", "then 7 waypoints rising from 51.2 to 178.8 m, LOITER_TIME with 30 at 200 m, 7 waypoints back down")
out = out.replace("Confirm WP7 is at the far north end of the road.", "Confirm the last waypoint (the far point) is in the forest north-northeast of the pasture.")
out = out.replace("**Over people and moving vehicles.**", "**Over people and moving vehicles.**")
open("RANGE_TEST_PLAN.md", "w", encoding="utf-8").write(out)
print(len(out.splitlines()), "lines")
for h in re.findall(r"^## .*", out, re.M): print(h)

t = open("RANGE_TEST_PLAN.md", encoding="utf-8").read()
t = t.replace("from WP4 to WP7 and back, up to 191 m (627 ft)", "from WP5 to WP8 and back, up to 198 m (650 ft)")
t = t.replace("landing in the forest at WP3 and WP4 is not good", "landing in the forest at WP3, WP4 and WP6 to WP8 is not good")
open("RANGE_TEST_PLAN.md", "w", encoding="utf-8").write(t)
