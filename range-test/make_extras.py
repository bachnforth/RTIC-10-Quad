"""Fence polygon (corridor +/-150 m), parameter file, recovery table data."""
import json, math
from route_def import LAUNCH, G, dist, bearing
from build_route import offset_line
D=json.load(open("mission_data.json")); wps=[tuple(w) for w in D["wps"]]
# corridor polygon: offset the route 150 m left and right; extend each end by 150 m
b0=bearing(wps[0],wps[1]); b1=bearing(wps[-2],wps[-1])
def ext(p,b,d):
    lon,lat,_=G.fwd(p[1],p[0],b,d); return (lat,lon)
core=[ext(wps[0],(b0+180)%360,150)]+wps[:]+[ext(wps[-1],b1,150)]
left=offset_line(core,150,"L"); right=offset_line(core,150,"R")
poly=left+right[::-1]
with open("corridor_fence.poly","w",newline="\n") as f:
    f.write("#saved by range-test planner (Mission Planner polygon format)\n")
    for p in poly: f.write(f"{p[0]:.7f} {p[1]:.7f}\n")
# recovery table
APS=json.load(open("access_points_chosen.json")); Z={z["wp"]:z for z in json.load(open("landing_zones.json"))}
best={1:"B",2:"B",3:"C",4:"E",5:"F",6:"F",7:"G"}
rec=[]
for k,lab in best.items():
    ap=[a for a in APS if a[0]==lab][0]
    rec.append(dict(ap=lab,drive_m=ap[4],walk_m=dist((ap[2],ap[3]),wps[k]),**Z[k]))
json.dump(rec,open("recovery_table.json","w"),indent=1)
for r in rec: print({a:(round(b) if isinstance(b,float) else b) for a,b in r.items()})
print("polygon vertices",len(poly))
