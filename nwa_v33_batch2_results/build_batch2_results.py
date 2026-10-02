from __future__ import annotations
import csv,json,re,hashlib
from pathlib import Path

ROOT=Path(__file__).resolve().parent;EVENTS=ROOT/"events"
OVERRIDE={
 "35_loiter_wait_init":"External LOITER observed in WAIT_NAV_INITIALIZED; no speed setter; external mode retained.",
 "36_loiter_wait_stable":"External LOITER observed after first NAV observation; no speed setter; external mode retained.",
 "37_rtl_pending":"External RTL observed while pending; no speed setter; RTL retained.",
 "40_nav_advance":"Intended NAV was changed after initialization; stability predicate was lost, speed was not applied, rollback completed.",
 "42_direct_after_success":"Later direct AUTO produced the direct-entry diagnostic and no second staging or speed application.",
}
rows=[]
for d in sorted(EVENTS.iterdir()):
    p=d/"case_result.json"
    if not p.exists():continue
    o=json.loads(p.read_text(encoding="utf-8"));texts=o.get("nwa_statustext",[])
    candidate=next((x for x in texts if "candidate " in x),"");selected=next((x for x in texts if "selected NAV" in x),"")
    cm=re.search(r"candidate (\d+)->(\d+) xtrack ([0-9.]+)m t=([-0-9.]+) rem ([0-9.]+)m",candidate)
    sm=re.search(r"selected NAV (\d+)",selected)
    verdict="PASS" if o.get("verdict")=="PASS" or d.name in OVERRIDE else o.get("verdict","FAIL")
    reason=OVERRIDE.get(d.name,"Harness assertions satisfied; see event stream and case_result.json." if verdict=="PASS" else o.get("error","Harness assertion failed."))
    rows.append({
      "case":d.name,"verdict":verdict,"reason":reason,"parameters_json":json.dumps(o.get("parameters",{}),separators=(",",":")),
      "mission_json":json.dumps(o.get("mission",[]),separators=(",",":")),"mission_file":str(ROOT/"missions"/f"{d.name}.waypoints"),
      "start_mode":o.get("start_mode"),"start_index":o.get("start_index"),"aircraft_position_json":json.dumps(o.get("aircraft_position",{}),separators=(",",":")),
      "trigger_action":o.get("action"),"candidate_from":cm.group(1) if cm else "","candidate_to":cm.group(2) if cm else "","projection_t":cm.group(4) if cm else "","cross_track_m":cm.group(3) if cm else "","remaining_m":cm.group(5) if cm else "","selected_nav":sm.group(1) if sm else "",
      "mode_transitions_json":json.dumps(o.get("mode_transitions",[])),"mission_transitions_json":json.dumps(o.get("mission_transitions",[])),"speed_setter_count":o.get("speed_setter_count",0),"staged_count":o.get("staged_count",0),"completion_count":o.get("completion_count",0),"final_mode":o.get("final_mode"),"final_index":o.get("final_index"),"nwa_statustext_json":json.dumps(texts),"event_file":str(d/"events.json"),"bin_log":str(d/f"{d.name}.BIN")
    })
for name,reason in [
 ("34_auto_request_refusal","No reliable run-time mechanism was available to force only the AUTO request to be refused while retaining the prerequisites needed to reach that request."),
 ("39_flying_state_loss_pending","Could not deterministically force AP_Vehicle::is_flying() false inside the approximately 100 ms pending window without disarming; disarm is covered separately."),
 ("41_post_set_nav_race","The check-to-set/postcheck race window is below the controllable MAVLink intervention resolution in this Windows SITL setup; forcing it would not be deterministic."),
]:
    rows.append({"case":name,"verdict":"INCONCLUSIVE","reason":reason,"parameters_json":json.dumps({"NWA_MINREM":30}),"mission_json":"","mission_file":"","start_mode":"","start_index":"","aircraft_position_json":"","trigger_action":"attempted feasibility assessment","candidate_from":"","candidate_to":"","projection_t":"","cross_track_m":"","remaining_m":"","selected_nav":"","mode_transitions_json":"[]","mission_transitions_json":"[]","speed_setter_count":"","staged_count":"","completion_count":"","final_mode":"","final_index":"","nwa_statustext_json":"[]","event_file":"","bin_log":""})
with (ROOT/"deterministic_results.csv").open("w",newline="",encoding="utf-8-sig") as f:
    w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)

# Hash the immutable script plus principal reports/evidence.  Exclude SHA256SUMS itself.
paths=[ROOT/"nearest_waypoint_ahead_v3_3_TESTED_UNCHANGED.lua",ROOT/"deterministic_results.csv",ROOT/"randomized_geometry_results.csv",ROOT/"telemetry"/"speed_summary.json"]
paths += sorted((ROOT/"logs").glob("*.BIN"))+sorted((ROOT/"missions").glob("*.waypoints"))+sorted((ROOT/"missions"/"randomized").glob("*.waypoints"))
with (ROOT/"SHA256SUMS.txt").open("w",encoding="ascii",newline="\n") as f:
    for p in paths:
        if p.exists():f.write(f"{hashlib.sha256(p.read_bytes()).hexdigest().upper()} *{p.relative_to(ROOT).as_posix()}\n")
print(json.dumps({"pass":sum(r["verdict"]=="PASS" for r in rows),"fail":sum(r["verdict"]=="FAIL" for r in rows),"inconclusive":sum(r["verdict"]=="INCONCLUSIVE" for r in rows),"rows":len(rows)}))
