from __future__ import annotations

import csv
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path

from pymavlink import mavutil


ROOT = Path(__file__).resolve().parent
BIN = ROOT / "ArduCopter-4.7.1-NWA-V3.2-validation.BIN"
TELEMETRY = ROOT / "nav6_nav8_telemetry_10hz.csv"
EVENTS = ROOT / "mission_events.csv"


def magnitude(north: float, east: float) -> float:
    return math.hypot(north, east)


def iso_utc(epoch_seconds: float) -> str:
    return datetime.fromtimestamp(epoch_seconds, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def nearest_before(samples, time_s):
    best = None
    for sample in samples:
        if sample["boot_s"] <= time_s:
            best = sample
        else:
            break
    return best


connection = mavutil.mavlink_connection(str(BIN))
messages = []
while True:
    message = connection.recv_match()
    if message is None:
        break
    record = message.to_dict()
    if "TimeUS" in record:
        record["boot_s"] = record["TimeUS"] / 1_000_000.0
    messages.append(record)

# RTC records map monotonic TimeUS to Unix epoch microseconds.  Use the median
# offset to suppress the sub-millisecond scheduling jitter between records.
rtc_offsets = [
    record["Epoch"] / 1_000_000.0 - record["boot_s"]
    for record in messages
    if record["mavpackettype"] == "RTC" and record.get("Epoch", 0) > 0
]
epoch_offset = statistics.median(rtc_offsets)

events = []
for record in messages:
    kind = record["mavpackettype"]
    if kind == "MSG" and (
        record.get("Message", "").startswith("NWA:")
        or record.get("Message", "").startswith("Mission:")
        or record.get("Message", "").startswith("Reached command")
    ):
        events.append((record["boot_s"], kind, record["Message"]))
    elif kind == "MISE" and 205 <= record["boot_s"] <= 245:
        events.append(
            (
                record["boot_s"],
                kind,
                f"seq={record['CNum']} command={record['CId']} param1={record['Prm1']:.1f} param2={record['Prm2']:.1f}",
            )
        )
    elif kind == "MODE" and 205 <= record["boot_s"] <= 245:
        events.append((record["boot_s"], kind, f"mode_num={record['ModeNum']} reason={record['Rsn']}"))

with EVENTS.open("w", newline="", encoding="utf-8") as stream:
    writer = csv.writer(stream)
    writer.writerow(["utc", "boot_s", "record_type", "detail"])
    for boot_s, kind, detail in sorted(events):
        writer.writerow([iso_utc(epoch_offset + boot_s), f"{boot_s:.6f}", kind, detail])

mise = [record for record in messages if record["mavpackettype"] == "MISE"]
nav6_start = next(record["boot_s"] for record in mise if record["CNum"] == 6)
seq7_time = next(record["boot_s"] for record in mise if record["CNum"] == 7)
nav8_start = next(record["boot_s"] for record in mise if record["CNum"] == 8)
speed_apply = next(
    record["boot_s"]
    for record in messages
    if record["mavpackettype"] == "MSG" and record.get("Message") == "NWA: speed applied 5.0m/s"
)
mode_end = next(
    record["boot_s"]
    for record in messages
    if record["mavpackettype"] == "MODE" and record["boot_s"] > nav8_start and record["ModeNum"] != 3
)

xkf = [
    {
        "boot_s": record["boot_s"],
        "vn": record["VN"],
        "ve": record["VE"],
        "hvel": magnitude(record["VN"], record["VE"]),
    }
    for record in messages
    if record["mavpackettype"] == "XKF1" and record.get("C") == 0 and speed_apply <= record["boot_s"] <= mode_end
]
gps = [record for record in messages if record["mavpackettype"] == "GPS" and record.get("I") == 0]
pscn = [record for record in messages if record["mavpackettype"] == "PSCN"]
psce = [record for record in messages if record["mavpackettype"] == "PSCE"]

# Emit one row per 0.1 s using the last record at or before each sample time.
rows = []
sample_time = math.ceil(speed_apply * 10) / 10
while sample_time <= mode_end:
    velocity = nearest_before(xkf, sample_time)
    gps_row = nearest_before(gps, sample_time)
    north = nearest_before(pscn, sample_time)
    east = nearest_before(psce, sample_time)
    if velocity and gps_row and north and east:
        sequence = 6 if sample_time < seq7_time else 8
        rows.append(
            {
                "utc": iso_utc(epoch_offset + sample_time),
                "boot_s": sample_time,
                "mission_seq": sequence,
                "ekf_vn_mps": velocity["vn"],
                "ekf_ve_mps": velocity["ve"],
                "horizontal_velocity_mps": velocity["hvel"],
                "gps_speed_mps": gps_row["Spd"],
                "psc_desired_hvel_mps": magnitude(north["DVN"], east["DVE"]),
                "psc_target_hvel_mps": magnitude(north["TVN"], east["TVE"]),
                "psc_actual_hvel_mps": magnitude(north["VN"], east["VE"]),
            }
        )
    sample_time = round(sample_time + 0.1, 10)

with TELEMETRY.open("w", newline="", encoding="utf-8") as stream:
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                key: f"{value:.4f}" if isinstance(value, float) else value
                for key, value in row.items()
            }
        )

nav6_velocity = [sample for sample in xkf if speed_apply <= sample["boot_s"] < seq7_time]
last_outside_index = max(
    index for index, sample in enumerate(nav6_velocity) if not (4.75 <= sample["hvel"] <= 5.25)
)
settled = nav6_velocity[last_outside_index + 1]
settled_samples = nav6_velocity[last_outside_index + 1 :]

nav8_velocity = [sample for sample in xkf if nav8_start <= sample["boot_s"] < mode_end]
first_nav8_over_525 = next(sample for sample in nav8_velocity if sample["hvel"] > 5.25)
first_nav8_at_95 = next(sample for sample in nav8_velocity if sample["hvel"] >= 9.5)

psc_combined = []
for north in pscn:
    if not (speed_apply <= north["boot_s"] < mode_end):
        continue
    east = nearest_before(psce, north["boot_s"])
    if east:
        psc_combined.append(
            {
                "boot_s": north["boot_s"],
                "desired": magnitude(north["DVN"], east["DVE"]),
                "target": magnitude(north["TVN"], east["TVE"]),
            }
        )
first_desired_over_525 = next(sample for sample in psc_combined if sample["boot_s"] >= seq7_time and sample["desired"] > 5.25)
first_desired_at_95 = next(sample for sample in psc_combined if sample["boot_s"] >= seq7_time and sample["desired"] >= 9.5)

def stamp(boot_s):
    return f"{iso_utc(epoch_offset + boot_s)} / boot {boot_s:.6f} s"


print(f"RTC epoch offset: {epoch_offset:.6f}")
print(f"NAV 6 MISE: {stamp(nav6_start)}")
print(f"5 m/s applied: {stamp(speed_apply)}")
print(f"seq 7 MISE: {stamp(seq7_time)}")
print(f"NAV 8 MISE: {stamp(nav8_start)}")
print(f"AUTO ended: {stamp(mode_end)}")
print(f"NAV 6 duration after speed applied: {seq7_time - speed_apply:.3f} s")
print(
    f"NAV 6 actual speed settled in 4.75..5.25 m/s: {stamp(settled['boot_s'])}; "
    f"{seq7_time - settled['boot_s']:.3f} s before completion"
)
print(
    f"NAV 6 settled actual mean/min/max: {statistics.mean(s['hvel'] for s in settled_samples):.3f}/"
    f"{min(s['hvel'] for s in settled_samples):.3f}/{max(s['hvel'] for s in settled_samples):.3f} m/s"
)
print(f"NAV 6 peak actual speed: {max(s['hvel'] for s in nav6_velocity):.3f} m/s")
print(f"NAV 8 actual first >5.25 m/s: {stamp(first_nav8_over_525['boot_s'])}")
print(f"NAV 8 actual first >=9.5 m/s: {stamp(first_nav8_at_95['boot_s'])}")
print(f"NAV 8 PSC desired first >5.25 m/s: {stamp(first_desired_over_525['boot_s'])}")
print(f"NAV 8 PSC desired first >=9.5 m/s: {stamp(first_desired_at_95['boot_s'])}")
print(
    f"NAV 8 final 5 s actual mean: "
    f"{statistics.mean(s['hvel'] for s in nav8_velocity if s['boot_s'] >= mode_end - 5):.3f} m/s"
)
