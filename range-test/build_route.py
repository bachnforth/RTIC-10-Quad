"""Build the outbound path (road-following, offset to one side) and the waypoint list."""
import json, math
from route_def import *
import route_def as rd

def offset_line(pts, off, side="R"):
    out=[]
    for i,p in enumerate(pts):
        b_prev = bearing(pts[i-1],p) if i>0 else None
        b_next = bearing(p,pts[i+1]) if i<len(pts)-1 else None
        if b_prev is None: b=b_next
        elif b_next is None: b=b_prev
        else:
            x=math.sin(math.radians(b_prev))+math.sin(math.radians(b_next)); y=math.cos(math.radians(b_prev))+math.cos(math.radians(b_next))
            b=math.degrees(math.atan2(x,y))%360
        out.append(offset_point(p,b,off,side))
    return out

def cumulative(pts):
    c=[0.0]
    for a,b in zip(pts,pts[1:]): c.append(c[-1]+dist(a,b))
    return c

def nearest_on_polyline(p, pts):
    """nearest point on polyline (sample at 2 m) -> (point, index-ish distance)"""
    best=None
    for a,b in zip(pts,pts[1:]):
        L=dist(a,b); n=max(1,int(L/2))
        for k in range(n+1):
            f=k/n; q=(a[0]+(b[0]-a[0])*f, a[1]+(b[1]-a[1])*f)
            d=dist(p,q)
            if best is None or d<best[0]: best=(d,q)
    return best[1],best[0]

def build():
    R=rd._roads()
    air,main=centerline()
    pelham=R[6250654]
    pelham=[p for p in pelham if p[1]<=-85.9072]          # from the E-W portion's west end NW to the junction
    # airfield road: east side (right when travelling north)
    airN=[p for p in air if 33.7240<=p[0]<=33.72726]
    air_off=offset_line(airN,OFFSET_M,"R")
    a_start=min(air_off,key=lambda p:abs(p[0]-33.7243))
    a_end=min(air_off,key=lambda p:abs(p[0]-33.7262))
    # Pelham Rd: travelling NW the north/east side is the right-hand side
    pel_off=offset_line(pelham[::-1][::-1],OFFSET_M,"R")  # pelham list runs SE->NW, right side = NE/north side
    cross_pt,_=nearest_on_polyline(a_end,pel_off)
    # N-S road: travelling north, east side is the right-hand side
    main_off=offset_line(main,OFFSET_M,"R")
    pel_after=[p for p in pel_off if dist(p,cross_pt)<1e9]
    # portion of the Pelham offset line from the crossing point to its NW end
    ci=min(range(len(pel_off)),key=lambda i:dist(pel_off[i],cross_pt))
    pel_leg=[cross_pt]+pel_off[ci+1:]
    # cut the corner at the junction: Pelham offset line up to lat 33.7285, then the N-S road offset line from lat 33.7300 north
    pel_part=[p for p in pel_leg[1:] if p[0]<=33.72850]
    main_part=[p for p in main_off if p[0]>=33.73000]
    path=[LAUNCH,a_end,cross_pt]+pel_part+main_part
    return path,dict(a_start=a_start,a_end=a_end,cross=cross_pt),air,pelham,main

def truncate_at_straight(path,target=FAR_STRAIGHT_M):
    """cut path at the point whose straight-line distance from launch is `target` m (first crossing after 1000 m)."""
    for i in range(1,len(path)):
        d0,d1=dist(LAUNCH,path[i-1]),dist(LAUNCH,path[i])
        if d0<target<=d1:
            lo,hi=0.0,1.0
            for _ in range(50):
                m=(lo+hi)/2; q=(path[i-1][0]+(path[i][0]-path[i-1][0])*m, path[i-1][1]+(path[i][1]-path[i-1][1])*m)
                if dist(LAUNCH,q)<target: lo=m
                else: hi=m
            q=(path[i-1][0]+(path[i][0]-path[i-1][0])*hi, path[i-1][1]+(path[i][1]-path[i-1][1])*hi)
            return path[:i]+[q]
    raise RuntimeError("path never reaches target straight-line distance")

def resample(path, spacing=SPACING_M, keep=()):
    """waypoints: path corners (those in `keep`) + equal subdivisions of each stretch between them"""
    ch=cumulative(path); total=ch[-1]
    corner_idx=[0]+[i for i,p in enumerate(path) if p in keep]+[len(path)-1]
    corner_idx=sorted(set(corner_idx))
    wps=[path[0]]
    for ia,ib in zip(corner_idx,corner_idx[1:]):
        seg=ch[ib]-ch[ia]; n=max(1,round(seg/spacing))
        for k in range(1,n+1):
            s=ch[ia]+seg*k/n
            # locate s along path
            j=max(i for i in range(len(path)) if ch[i]<=s+1e-9)
            if j>=len(path)-1: wps.append(path[-1]); continue
            f=(s-ch[j])/(ch[j+1]-ch[j])
            wps.append((path[j][0]+(path[j+1][0]-path[j][0])*f, path[j][1]+(path[j+1][1]-path[j][1])*f))
    return wps,total

if __name__=="__main__":
    path,k,air,pel,main=build()
    path=truncate_at_straight(path)
    print("path vertices",len(path),"length",round(cumulative(path)[-1]),"straight",round(dist(LAUNCH,path[-1])),"bearing",round(bearing(LAUNCH,path[-1]),1))
    keep=[k["a_end"],k["cross"]]
    wps,total=resample(path,keep=keep)
    for i,w in enumerate(wps): print(i,round(w[0],6),round(w[1],6),round(dist(LAUNCH,w)))
    json.dump(dict(path=path,wps=wps,keys=k),open("route_draft.json","w"))
