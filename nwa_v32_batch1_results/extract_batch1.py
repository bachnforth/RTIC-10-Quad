from __future__ import annotations

import csv
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path

from pymavlink import mavutil


ROOT = Path(__file__).resolve().parent
CASES = ["fallback", "persistent", "persistent_repeat", "direct", "minrem", "vertical", "once", "external", "rollback0", "rollback_nonzero"]


def iso(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def mag(n, e):
    return math.hypot(n, e)


def before(records, time_s):
    result = None
    for record in records:
        if record["boot_s"] <= time_s:
            result = record
        else:
            break
    return result


def distance_m(lat1, lon1, lat2, lon2):
    north = (lat2 - lat1) * 111319.49079327358
    east = (lon2 - lon1) * 111319.49079327358 * math.cos(math.radians(lat2))
    return math.hypot(north, east)


summary = {}
for case in CASES:
    case_dir = ROOT / case
    connection = mavutil.mavlink_connection(str(case_dir / f"{case}.BIN"))
    records = []
    while True:
        message = connection.recv_match()
        if message is None:
            break
        record = message.to_dict()
        record["record_type"] = message.get_type()
        if "TimeUS" in record:
            record["boot_s"] = record["TimeUS"] / 1e6
        records.append(record)

    rtc_offsets = [
        record["Epoch"] / 1e6 - record["boot_s"]
        for record in records
        if record["record_type"] == "RTC" and record.get("Epoch", 0) > 0
    ]
    epoch_offset = statistics.median(rtc_offsets)

    event_rows = []
    for record in records:
        kind = record["record_type"]
        if kind == "MSG" and (
            record.get("Message", "").startswith("NWA:")
            or record.get("Message", "").startswith("Mission:")
            or record.get("Message", "").startswith("Reached command")
        ):
            detail = record["Message"]
        elif kind == "MODE" and record.get("boot_s", 0) > 40:
            detail = f"mode={record['ModeNum']} reason={record['Rsn']}"
        elif kind == "MISE":
            detail = f"seq={record['CNum']} command={record['CId']} param1={record['Prm1']:.1f} param2={record['Prm2']:.1f}"
        elif kind == "ARM" and record.get("boot_s", 0) > 40:
            detail = f"armed={record['ArmState']} method={record['Method']} forced={record['Forced']}"
        else:
            continue
        event_rows.append((record["boot_s"], kind, detail))

    with (case_dir / "bin_events.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["utc", "boot_s", "record_type", "detail"])
        for boot_s, kind, detail in event_rows:
            writer.writerow([iso(epoch_offset + boot_s), f"{boot_s:.6f}", kind, detail])

    version = next(record["FWS"] for record in records if record["record_type"] == "VER")
    nwa_messages = [record["Message"] for record in records if record["record_type"] == "MSG" and record.get("Message", "").startswith("NWA:")]
    modes = [(record["boot_s"], record["ModeNum"], record["Rsn"]) for record in records if record["record_type"] == "MODE" and record["boot_s"] > 40]
    mise = [
        (record["boot_s"], record["CNum"], record["CId"], record["Prm1"], record["Prm2"])
        for record in records
        if record["record_type"] == "MISE"
    ]
    live_events = json.loads((case_dir / "events.json").read_text(encoding="utf-8"))
    mission_changes = [(event["utc"], event.get("boot_ms"), event.get("seq")) for event in live_events if event["kind"] == "MISSION_CURRENT"]
    summary[case] = {
        "version": version,
        "epoch_offset": epoch_offset,
        "speed_apply_count": sum(message.startswith("NWA: speed applied") for message in nwa_messages),
        "nwa_messages": nwa_messages,
        "modes": modes,
        "mise": mise,
        "mission_current_live": mission_changes,
    }

    if case not in ("fallback", "persistent", "persistent_repeat"):
        continue

    target_speed = 6.0 if case == "fallback" else 5.0
    tolerance = 0.30 if case == "fallback" else 0.25
    target_seq = 4 if case == "fallback" else 5
    next_do_seq = 5 if case == "fallback" else 6
    next_nav_seq = 6 if case == "fallback" else 7
    destination_lat, destination_lon = 35.0510415, -79.4901810

    apply_time = next(
        record["boot_s"]
        for record in records
        if record["record_type"] == "MSG" and record.get("Message") == f"NWA: speed applied {target_speed:.1f}m/s"
    )
    nav_start = next(record["boot_s"] for record in records if record["record_type"] == "MISE" and record["CNum"] == target_seq)
    nav_end = next(record["boot_s"] for record in records if record["record_type"] == "MISE" and record["CNum"] == next_do_seq)
    next_nav = next(record["boot_s"] for record in records if record["record_type"] == "MISE" and record["CNum"] == next_nav_seq)
    xkf = [
        {"boot_s": record["boot_s"], "vn": record["VN"], "ve": record["VE"], "hvel": mag(record["VN"], record["VE"])}
        for record in records
        if record["record_type"] == "XKF1" and record.get("C") == 0
    ]
    pscn = [record for record in records if record["record_type"] == "PSCN"]
    psce = [record for record in records if record["record_type"] == "PSCE"]
    gps = [record for record in records if record["record_type"] == "GPS" and record.get("I") == 0]
    positions = [record for record in records if record["record_type"] == "POS"]

    telemetry_rows = []
    sample_time = math.ceil(apply_time * 10) / 10
    capture_end = min(nav_end + 7, modes[-1][0])
    while sample_time <= capture_end:
        velocity = before(xkf, sample_time)
        north = before(pscn, sample_time)
        east = before(psce, sample_time)
        gps_row = before(gps, sample_time)
        if velocity and north and east and gps_row:
            seq = target_seq if sample_time < nav_end else next_nav_seq
            telemetry_rows.append(
                {
                    "utc": iso(epoch_offset + sample_time),
                    "boot_s": sample_time,
                    "mission_seq": seq,
                    "ekf_vn_mps": velocity["vn"],
                    "ekf_ve_mps": velocity["ve"],
                    "horizontal_velocity_mps": velocity["hvel"],
                    "gps_speed_mps": gps_row["Spd"],
                    "psc_desired_hvel_mps": mag(north["DVN"], east["DVE"]),
                    "psc_target_hvel_mps": mag(north["TVN"], east["TVE"]),
                    "psc_actual_hvel_mps": mag(north["VN"], east["VE"]),
                }
            )
        sample_time = round(sample_time + 0.1, 10)

    with (case_dir / "speed_telemetry_10hz.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(telemetry_rows[0]))
        writer.writeheader()
        for row in telemetry_rows:
            writer.writerow({key: f"{value:.4f}" if isinstance(value, float) else value for key, value in row.items()})

    nav_velocity = [sample for sample in xkf if apply_time <= sample["boot_s"] < nav_end]
    inside = [sample for sample in nav_velocity if target_speed - tolerance <= sample["hvel"] <= target_speed + tolerance]
    last_outside = max(
        (index for index, sample in enumerate(nav_velocity) if not target_speed - tolerance <= sample["hvel"] <= target_speed + tolerance),
        default=-1,
    )
    settled = nav_velocity[last_outside + 1] if last_outside + 1 < len(nav_velocity) else None
    metrics = {
        "target_speed": target_speed,
        "tolerance": tolerance,
        "apply_time": apply_time,
        "nav_start": nav_start,
        "nav_end": nav_end,
        "nav_duration_after_apply": nav_end - apply_time,
        "apply_before_nav_start_ms": (nav_start - apply_time) * 1000,
        "next_do_time": nav_end,
        "next_nav_time": next_nav,
        "peak_hvel": max(sample["hvel"] for sample in nav_velocity),
        "first_in_target_band": inside[0] if inside else None,
        "last_in_target_band": inside[-1] if inside else None,
        "settled": settled,
    }
    if settled:
        settled_samples = [sample for sample in nav_velocity if sample["boot_s"] >= settled["boot_s"]]
        position = before(positions, settled["boot_s"])
        metrics.update(
            {
                "settled_mean": statistics.mean(sample["hvel"] for sample in settled_samples),
                "settled_min": min(sample["hvel"] for sample in settled_samples),
                "settled_max": max(sample["hvel"] for sample in settled_samples),
                "time_remaining_at_settle": nav_end - settled["boot_s"],
                "distance_remaining_at_settle": distance_m(position["Lat"], position["Lng"], destination_lat, destination_lon),
            }
        )

    if case == "persistent" and settled is None:
        # Quantify the speed at which this failed case actually settles.
        actual_tolerance = 0.30
        last_outside_six = max(index for index, sample in enumerate(nav_velocity) if not 6 - actual_tolerance <= sample["hvel"] <= 6 + actual_tolerance)
        six_settled = nav_velocity[last_outside_six + 1]
        six_samples = nav_velocity[last_outside_six + 1 :]
        position = before(positions, six_settled["boot_s"])
        metrics["actual_six_settle"] = {
            "sample": six_settled,
            "mean": statistics.mean(sample["hvel"] for sample in six_samples),
            "min": min(sample["hvel"] for sample in six_samples),
            "max": max(sample["hvel"] for sample in six_samples),
            "time_remaining": nav_end - six_settled["boot_s"],
            "distance_remaining": distance_m(position["Lat"], position["Lng"], destination_lat, destination_lon),
        }
    summary[case]["speed_metrics"] = metrics

(ROOT / "analysis_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps({case: summary[case].get("speed_metrics", {"speed_apply_count": summary[case]["speed_apply_count"]}) for case in CASES}, indent=2))
