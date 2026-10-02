from __future__ import annotations

import csv, json, math, random, sys, time
from datetime import datetime, timezone
from pathlib import Path
from pymavlink import mavutil

OUT = Path(sys.argv[1]).resolve(); OUT.mkdir(parents=True, exist_ok=True)
MISSIONS = OUT.parent / "missions" / "randomized"; MISSIONS.mkdir(parents=True, exist_ok=True)
HOME_LAT, HOME_LON, HOME_ALT = 35.0495415, -79.4901810, 100.44
MPD = 111319.49079327358
RNG = random.Random(3300471)
events, rows = [], []
latest_boot = last_seq = last_mode = None
latest_pos = None

def utcnow(): return datetime.now(timezone.utc).isoformat(timespec="milliseconds")
def event(kind, text, **extra):
    row={"utc":utcnow(),"boot_ms":latest_boot,"kind":kind,"text":text,**extra}; events.append(row)
    print(json.dumps(row), flush=True)

m=mavutil.mavlink_connection("tcp:127.0.0.1:5762",source_system=255)
hb=m.wait_heartbeat(timeout=20)
if not hb: raise RuntimeError("no heartbeat")
m.target_system=hb.get_srcSystem();m.target_component=hb.get_srcComponent()

def recv(timeout=.05):
    global latest_boot,last_seq,last_mode,latest_pos
    q=m.recv_match(blocking=True,timeout=timeout)
    if not q:return None
    d=q.to_dict(); typ=q.get_type()
    if "time_boot_ms" in d:latest_boot=d["time_boot_ms"]
    if typ=="GLOBAL_POSITION_INT":latest_pos=(q.lat*1e-7,q.lon*1e-7,q.relative_alt*.001)
    elif typ=="MISSION_CURRENT" and q.seq!=last_seq:last_seq=q.seq;event("MISSION_CURRENT",f"seq {q.seq}",seq=q.seq)
    elif typ=="HEARTBEAT" and q.custom_mode!=last_mode:last_mode=q.custom_mode;event("MODE",f"mode {q.custom_mode}",mode=q.custom_mode)
    elif typ=="STATUSTEXT":event("STATUSTEXT",q.text,severity=q.severity)
    return q

def pump(sec):
    end=time.monotonic()+sec
    while time.monotonic()<end:recv(min(.03,end-time.monotonic()))
def wait(types,sec,pred=lambda x:True):
    end=time.monotonic()+sec
    while time.monotonic()<end:
        q=recv(min(.08,end-time.monotonic()))
        if q and q.get_type() in types and pred(q):return q
    return None
def set_param(name,value):
    m.mav.param_set_send(m.target_system,m.target_component,name.encode(),float(value),mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
    q=wait({"PARAM_VALUE"},5,lambda x:x.param_id==name)
    if not q or abs(q.param_value-value)>.01:raise RuntimeError(f"parameter {name} failed")
def set_mode(mode):
    m.set_mode_apm(mode)
    if not wait({"HEARTBEAT"},5,lambda x:x.custom_mode==mode):raise RuntimeError(f"mode {mode} failed")
def set_current(seq):
    m.mav.mission_set_current_send(m.target_system,m.target_component,seq)
    if not wait({"MISSION_CURRENT"},4,lambda x:x.seq==seq):raise RuntimeError(f"current {seq} failed")
def rc7(pwm):
    v=[65535]*8;v[6]=pwm
    for _ in range(5):m.mav.rc_channels_override_send(m.target_system,m.target_component,*v);pump(.04)

def ll(lat0,lon0,n,e):return lat0+n/MPD,lon0+e/(MPD*math.cos(math.radians(lat0)))
def mission_rows(points,lat0,lon0):
    out=[(0,0,16,0,0,0,0,lat0,lon0,HOME_ALT,1),(1,3,22,0,0,0,0,lat0,lon0,20,0)]
    for n,e in points:
        lat,lon=ll(lat0,lon0,n,e);seq=len(out);out.append((seq,3,16,0,0,0,0,lat,lon,20,0))
    seq=len(out);out.append((seq,2,20,0,0,0,0,0,0,0,0));return out
def upload(mis,path):
    m.mav.mission_clear_all_send(m.target_system,m.target_component);wait({"MISSION_ACK"},2)
    m.mav.mission_count_send(m.target_system,m.target_component,len(mis));sent=set();end=time.monotonic()+12
    while time.monotonic()<end:
        q=recv(.2)
        if not q:continue
        if q.get_type() in ("MISSION_REQUEST","MISSION_REQUEST_INT"):
            seq=q.seq;_,frame,cmd,p1,p2,p3,p4,lat,lon,alt,current=mis[seq]
            m.mav.mission_item_int_send(m.target_system,m.target_component,seq,frame,cmd,current,1,p1,p2,p3,p4,int(round(lat*1e7)),int(round(lon*1e7)),alt);sent.add(seq)
        elif q.get_type()=="MISSION_ACK":break
    if len(sent)!=len(mis):raise RuntimeError(f"upload incomplete {len(sent)}/{len(mis)}")
    with path.open("w",encoding="ascii",newline="\n") as f:
        f.write("QGC WPL 110\n")
        for a in mis:
            seq,frame,cmd,p1,p2,p3,p4,lat,lon,alt,current=a
            f.write(f"{seq}\t{current}\t{frame}\t{cmd}\t{p1}\t{p2}\t{p3}\t{p4}\t{lat:.7f}\t{lon:.7f}\t{alt:.3f}\t1\n")

def oracle(mis,alat,alon):
    cand=[];prev=None
    for seq in range(2,len(mis)-1):
        lat=round(mis[seq][7],7);lon=round(mis[seq][8],7)
        an=(lat-alat)*MPD;ae=(lon-alon)*MPD*math.cos(math.radians(alat))
        if prev:
            pseq,pn,pe=prev;dn,de=an-pn,ae-pe;l2=dn*dn+de*de;length=math.sqrt(l2)
            if length<2 or length>50000:return {"kind":"reject","reason":"invalid_leg"}
            t=-(pn*dn+pe*de)/l2;cn,ce=pn+t*dn,pe+t*de;dist=math.hypot(cn,ce);rem=(1-t)*length
            if 0<=t<=1 and rem>=30:cand.append({"from":pseq,"to":seq,"t":t,"dist":dist,"remaining":rem,"length":length})
        prev=(seq,an,ae)
    if not cand:return {"kind":"reject","reason":"no_eligible"}
    cand.sort(key=lambda x:x["dist"]);best=cand[0]
    if best["dist"]>100:return {"kind":"reject","reason":"maxdist",**best}
    if len(cand)>1 and cand[1]["dist"]-best["dist"]<1:return {"kind":"reject","reason":"ambiguous",**best,"second_dist":cand[1]["dist"]}
    return {"kind":"select","reason":"eligible",**best}

def gen_points(i):
    family=i%4
    if family==0:
        angle=RNG.uniform(0,2*math.pi);u=(math.cos(angle),math.sin(angle));v=(-u[1],u[0])
        length=RNG.uniform(3,360);t=RNG.uniform(-.35,1.35);cross=RNG.uniform(-135,135)
        return [(-t*length*u[0]+cross*v[0],-t*length*u[1]+cross*v[1]),((1-t)*length*u[0]+cross*v[0],(1-t)*length*u[1]+cross*v[1])],"single"
    if family==1:
        # Three independent points create two competing or separated legs.
        while True:
            p=[(RNG.uniform(-240,240),RNG.uniform(-160,160)) for _ in range(3)]
            if all(math.dist(p[j],p[j+1])>=3 for j in range(2)):return p,"polyline"
    if family==2:
        # Parallel legs with a connector well away from the aircraft.
        d=RNG.uniform(-115,115);gap=RNG.uniform(.15,8);length=RNG.uniform(80,260);rot=RNG.uniform(0,2*math.pi)
        raw=[(-length/2,d),(length/2,d),(-length/2,d+gap),(length/2,d+gap)]
        c,s=math.cos(rot),math.sin(rot);return [(x*c-y*s,x*s+y*c) for x,y in raw],"parallel"
    # Crossing legs; offset moves intersection relative to the aircraft.
    offx,offy=RNG.uniform(-120,120),RNG.uniform(-120,120);span=RNG.uniform(70,220);rot=RNG.uniform(0,2*math.pi)
    raw=[(-span,-span),(span,span),(-span,span),(span,-span)];c,s=math.cos(rot),math.sin(rot)
    return [(x*c-y*s+offx,x*s+y*c+offy) for x,y in raw],"crossing"

for mid,hz in [(0,10),(33,10),(42,10)]:
    m.mav.command_long_send(m.target_system,m.target_component,mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,0,mid,1e6/hz,0,0,0,0,0)
pump(.4)
for n,v in [("ARMING_SKIPCHK",65535),("SCR_ENABLE",1),("RC7_OPTION",300),("WP_SPD",6),("NWA_DEBUG",1),("NWA_START",2),("NWA_END",0),("NWA_MINREM",30),("NWA_MAXDIST",100),("NWA_MINLEG",2),("NWA_AMBIG",1),("NWA_ENABLE",1),("NWA_ONCE",0),("MIS_RESTART",0)]:set_param(n,v)

set_mode(4)
while latest_boot is None or latest_boot<25000:pump(.2)
armed=None
while not armed:
    m.arducopter_arm();armed=wait({"HEARTBEAT"},2,lambda x:bool(x.base_mode&mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED))
m.mav.command_long_send(m.target_system,m.target_component,mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,0,0,0,0,0,0,0,20)
if not wait({"GLOBAL_POSITION_INT"},45,lambda x:x.relative_alt>=18000):raise RuntimeError("takeoff timeout")
pump(1)

for i in range(120):
    # GUIDED holds altitude without depending on the simulated pilot throttle.
    set_mode(4) if last_mode!=4 else None; pump(.12)
    if latest_pos is None:raise RuntimeError("no position")
    base_lat,base_lon,_=latest_pos;points,family=gen_points(i);mis=mission_rows(points,base_lat,base_lon)
    mission_path=MISSIONS/f"random_{i+1:03d}_{family}.waypoints";upload(mis,mission_path);set_current(1)
    pump(.1);alat,alon,aalt=latest_pos;expected=oracle(mis,alat,alon)
    begin=len(events);rc7(1000);pump(.12);rc7(2000);pump(.3)
    texts=[e["text"] for e in events[begin:] if e["kind"]=="STATUSTEXT" and e["text"].startswith("NWA:")]
    selected=None
    for t in texts:
        if t.startswith("NWA: selected NAV "):
            try:selected=int(t.split()[3])
            except:pass
    staged=sum("staged NAV" in t for t in texts);speed=sum("speed applied" in t for t in texts)
    actual_kind="select" if selected is not None else "reject"
    match=actual_kind==expected["kind"] and (actual_kind=="reject" or selected==expected["to"])
    rows.append({"case":i+1,"family":family,"aircraft_lat":alat,"aircraft_lon":alon,"points_ne_json":json.dumps(points),"expected":expected["kind"],"expected_to":expected.get("to"),"oracle_reason":expected["reason"],"oracle_t":expected.get("t"),"oracle_xtrack_m":expected.get("dist"),"oracle_remaining_m":expected.get("remaining"),"actual":actual_kind,"actual_to":selected,"staged_count":staged,"speed_setter_count":speed,"mode_transitions":json.dumps([e.get("mode") for e in events[begin:] if e["kind"]=="MODE"]),"mission_transitions":json.dumps([e.get("seq") for e in events[begin:] if e["kind"]=="MISSION_CURRENT"]),"nwa_statustext":json.dumps(texts),"mission_file":str(mission_path),"verdict":"PASS" if match else "FAIL"})
    event("RANDOM_CASE",f"{i+1} {'PASS' if match else 'FAIL'}",expected=expected,actual=actual_kind,actual_to=selected)
    if last_mode==3:set_mode(4);pump(.15)

with (OUT.parent/"randomized_geometry_results.csv").open("w",newline="",encoding="utf-8-sig") as f:
    w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
(OUT/"randomized_events.json").write_text(json.dumps(events,indent=2),encoding="utf-8")
try:
    set_mode(5);m.arducopter_disarm();pump(.3)
except:pass
print(json.dumps({"total":len(rows),"pass":sum(r["verdict"]=="PASS" for r in rows),"fail":sum(r["verdict"]=="FAIL" for r in rows)}))
