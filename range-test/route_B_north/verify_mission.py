"""Independent check of range_test_1500m_north.waypoints (haversine, not the geodesic library used to build it)."""
import math
R=6371008.8
def hav(a,b):
    p1,p2=math.radians(a[0]),math.radians(b[0]); dl=math.radians(b[1]-a[1]); dp=p2-p1
    h=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(h))
rows=[l.split("\t") for l in open("range_test_1500m_north.waypoints").read().splitlines()[1:]]
home=(float(rows[0][8]),float(rows[0][9]))
names={"16":"WAYPOINT","19":"LOITER_TIME","20":"RTL","22":"TAKEOFF","178":"DO_CHANGE_SPEED"}
prev=home; cum=0; mx=0
for r in rows:
    seq,cur,frame,cmd=r[0],r[1],r[2],r[3]; lat,lon,alt=float(r[8]),float(r[9]),float(r[10])
    nav = cmd in("16","19")
    d=0
    if nav: d=hav(prev,(lat,lon)); cum+=d; prev=(lat,lon)
    print(f"{seq:>2} frame={frame} {names.get(cmd,cmd):<16} lat={lat:.6f} lon={lon:.6f} alt={alt:7.1f} leg={d:6.1f} m  from_home={hav(home,(lat,lon)) if nav else 0:7.1f} m")
    if nav: mx=max(mx,hav(home,(lat,lon)))
    assert seq==str(rows.index(r)) and (cmd=="16" and seq=="0" or frame=="3"), "frame/sequence problem"
print("max straight-line distance from home: %.1f m; total flown path (out+back, excl. RTL leg) %.0f m"%(mx,cum))
