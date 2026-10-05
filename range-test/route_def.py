"""Route geometry: road centerlines from OpenStreetMap, offset to the side, sampled every ~250 m."""
import json, math
from pyproj import Geod
G = Geod(ellps="WGS84")
LAUNCH = (33.7238114, -85.9064364)      # Mission Planner Home Location (from the user's screenshot)
LAUNCH_ASL = 181.52                      # m, Home ASL shown in Mission Planner
OFFSET_M = 45.0                          # lateral offset from the road centerline (30-60 m requested)
SPACING_M = 250.0
FAR_STRAIGHT_M = 1500.0

def _roads():
    return {e["id"]: [(g["lat"], g["lon"]) for g in e["geometry"]] for e in json.load(open("osm_roads.json"))["elements"]}

def dist(a, b):
    return G.inv(a[1], a[0], b[1], b[0])[2]

def bearing(a, b):
    return G.inv(a[1], a[0], b[1], b[0])[0] % 360

def offset_point(p, brg_along, off_m, side):
    """Point off_m to the 'side' ('E' or 'W' of travel; positive=right) of p, given the direction of travel."""
    brg = (brg_along + (90 if side == "R" else -90)) % 360
    lon, lat, _ = G.fwd(p[1], p[0], brg, off_m)
    return (lat, lon)

def centerline():
    R = _roads()
    air = R[6249938]                      # gravel road along the west edge of the airfield (runs N)
    # keep from the south end up to the Pelham Range Rd junction
    air = [p for p in air if p[0] <= 33.72730]
    main = R[6254977]                     # the N-S service road through the woods/pasture
    # main is stored west->east; find the part from the (33.72893,-85.91141) area north to 33.7383
    i0 = min(range(len(main)), key=lambda i: dist(main[i], (33.72893, -85.91141)))
    i1 = min(range(len(main)), key=lambda i: dist(main[i], (33.73826, -85.91046)))
    seg = main[i0:i1 + 1] if i0 < i1 else main[i1:i0 + 1][::-1]
    return air, seg
