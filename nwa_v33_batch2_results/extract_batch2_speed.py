from __future__ import annotations
import csv,json,math,statistics,shutil
from pathlib import Path
from pymavlink import mavutil

ROOT=Path(__file__).resolve().parent
CASES={
 "15_multiple_speed":(6,7,8,7.0),
 "16_speed_zero":(6,7,8,5.0),
 "17_speed_type0":(5,6,7,5.0),
 "18_speed_type1":(5,6,7,5.0),
}
def before(a,t):
    z=None
    for x in a:
        if x["t"]<=t:z=x
        else:break
    return z

summary={};(ROOT/"telemetry").mkdir(exist_ok=True);(ROOT/"logs").mkdir(exist_ok=True)
for case,(target,nextdo,nextnav,speed) in CASES.items():
    case_dir=ROOT/"events"/case;binpath=case_dir/f"{case}.BIN"
    shutil.copy2(binpath,ROOT/"logs"/f"{case}.BIN")
    c=mavutil.mavlink_connection(str(binpath));recs=[]
    while True:
        q=c.recv_match()
        if q is None:break
        d=q.to_dict();d["typ"]=q.get_type()
        if "TimeUS" in d:d["t"]=d["TimeUS"]/1e6
        recs.append(d)
    msgs=[r for r in recs if r["typ"]=="MSG"]
    apply=next(r["t"] for r in msgs if r.get("Message")==f"NWA: speed applied {speed:.1f}m/s")
    navstart=next(r["t"] for r in msgs if r.get("Message")==f"Mission: {target} WP")
    do=next(r["t"] for r in msgs if r.get("Message")==f"Mission: {nextdo} ChangeSpeed")
    nav2=next(r["t"] for r in msgs if r.get("Message")==f"Mission: {nextnav} WP")
    xkf=[{"t":r["t"],"vn":r["VN"],"ve":r["VE"],"hv":math.hypot(r["VN"],r["VE"])} for r in recs if r["typ"]=="XKF1" and r.get("C")==0]
    pn=[{"t":r["t"],"dv":r["DVN"],"tv":r["TVN"],"v":r["VN"]} for r in recs if r["typ"]=="PSCN"]
    pe=[{"t":r["t"],"dv":r["DVE"],"tv":r["TVE"],"v":r["VE"]} for r in recs if r["typ"]=="PSCE"]
    out=[];t=math.ceil(apply*10)/10;end=min(nav2+5,max(x["t"] for x in xkf))
    while t<=end:
        v,n,e=before(xkf,t),before(pn,t),before(pe,t)
        if v and n and e:
            seq=target if t<do else nextnav
            out.append({"boot_s":round(t,3),"mission_seq":seq,"ekf_vn_mps":v["vn"],"ekf_ve_mps":v["ve"],"horizontal_velocity_mps":v["hv"],"psc_desired_hvel_mps":math.hypot(n["dv"],e["dv"]),"psc_target_hvel_mps":math.hypot(n["tv"],e["tv"]),"psc_actual_hvel_mps":math.hypot(n["v"],e["v"])})
        t=round(t+.1,10)
    with (ROOT/"telemetry"/f"{case}_speed_telemetry_10hz.csv").open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=out[0].keys());w.writeheader();w.writerows(out)
    nav=[r for r in out if r["mission_seq"]==target]
    band=[r for r in nav if abs(r["horizontal_velocity_mps"]-speed)<=.25]
    lastbad=max((i for i,r in enumerate(nav) if abs(r["horizontal_velocity_mps"]-speed)>.25),default=-1)
    settled=nav[lastbad+1] if lastbad+1<len(nav) else None
    summary[case]={"target_seq":target,"target_speed_mps":speed,"apply_boot_s":apply,"nav_start_boot_s":navstart,"next_do_boot_s":do,"next_nav_boot_s":nav2,"nav_duration_after_apply_s":do-apply,"peak_nav_hvel_mps":max(r["horizontal_velocity_mps"] for r in nav),"first_band_boot_s":band[0]["boot_s"] if band else None,"settled_boot_s":settled["boot_s"] if settled else None,"settled_mean_hvel_mps":statistics.mean(r["horizontal_velocity_mps"] for r in nav if settled and r["boot_s"]>=settled["boot_s"]) if settled else None,"time_remaining_at_settle_s":do-settled["boot_s"] if settled else None}
(ROOT/"telemetry"/"speed_summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
print(json.dumps(summary,indent=2))
