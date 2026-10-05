"""Road graph from OSM: driving distance from launch to every junction near the route."""
import json, heapq, collections, math
from route_def import LAUNCH, dist

D = json.load(open("mission_data.json"))
wps = [tuple(w) for w in D["wps"]]
path = [tuple(p) for p in D["path"]]

ROADS = json.load(open("osm_roads.json"))["elements"]
key = lambda p: (round(p[0], 5), round(p[1], 5))
adj = collections.defaultdict(dict)
deg = collections.Counter()
coord = {}
way_of = collections.defaultdict(set)
for e in ROADS:
    pts = [(g["lat"], g["lon"]) for g in e["geometry"]]
    for a, b in zip(pts, pts[1:]):
        ka, kb = key(a), key(b)
        coord[ka] = a; coord[kb] = b
        d = dist(a, b)
        if kb not in adj[ka] or adj[ka][kb] > d:
            adj[ka][kb] = d; adj[kb][ka] = d
        way_of[ka].add(e["id"]); way_of[kb].add(e["id"])
for k in adj:
    deg[k] = len(adj[k])


def nearest_node(p):
    return min(adj, key=lambda k: dist(p, coord[k]))


def dijkstra(src):
    dd = {src: 0.0}
    pq = [(0.0, src)]
    while pq:
        d, u = heapq.heappop(pq)
        if d > dd.get(u, 1e18):
            continue
        for v, w in adj[u].items():
            nd = d + w
            if nd < dd.get(v, 1e18):
                dd[v] = nd
                heapq.heappush(pq, (nd, v))
    return dd


def dist_to_path(p, poly, step=5):
    best = (1e9, None)
    for a, b in zip(poly, poly[1:]):
        L = dist(a, b); n = max(1, int(L / step))
        for k in range(n + 1):
            f = k / n
            q = (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)
            d = dist(p, q)
            if d < best[0]:
                best = (d, q)
    return best


src = nearest_node(LAUNCH)
dd = dijkstra(src)
print("launch nearest road node", src, round(dist(LAUNCH, coord[src])), "m away")
cands = []
for k, c in coord.items():
    if deg[k] >= 3 or deg[k] == 1:
        d_route, q = dist_to_path(c, path)
        if d_route <= 400 and k in dd:
            nearest_wp = min(range(len(wps)), key=lambda i: dist(c, wps[i]))
            cands.append((nearest_wp, d_route, k, dd[k], deg[k]))
cands.sort()
for nw, dr, k, drv, dg in cands:
    print(f"node {k} deg{dg} nearest WP{nw} dist_to_route {dr:.0f} m  drive_from_launch {drv:.0f} m  ways {sorted(way_of[k])}")
json.dump([dict(lat=coord[k][0], lon=coord[k][1], deg=dg, nearest_wp=nw, dist_to_route=dr, drive_m=drv) for nw, dr, k, drv, dg in cands],
          open("access_candidates.json", "w"), indent=1)
