import json, math
from access_points import adj, coord, dijkstra, nearest_node, key
from route_def import LAUNCH, dist, bearing
src=nearest_node(LAUNCH); dd=dijkstra(src)
res=[]
for k,c in coord.items():
    if k not in dd: continue
    d=dist(LAUNCH,c)
    if 1380<=d<=1620:
        b=bearing(LAUNCH,c); dev=min(b,360-b) if b<180 else 360-b
        res.append((dev,d,dd[k],k,b))
res.sort()
for dev,d,pl,k,b in res[:15]: print(f"dev {dev:5.1f}  straight {d:6.0f}  roadpath {pl:6.0f}  node {k} brg {b:.0f}")
