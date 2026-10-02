# Camp Mackall QGroundControl test plan

File: `Camp_Mackall_QGC_TEST_5m.plan`

Status: local planning file only. It has not been uploaded to the aircraft.

The planning coordinates are immediately beside Mackall Army Airfield (KHFF). Current FAA material describes active military/UAS operations and restricted access at the airfield. Treat this file as an offline planning exercise unless the operator has the required site and airspace authorization and completes a current-day airspace/NOTAM check.

## Mission sequence

1. Planned Home: `35.04901493, -79.48968350` at `103.72 m` AMSL.
2. Take off vertically to `5 m` above Home.
3. Fly `5 m` north; hold for `2 seconds`.
4. Fly `5 m` east; hold for `2 seconds`.
5. Fly `5 m` south; hold for `2 seconds`.
6. Execute Return to Launch (RTL).

The farthest waypoint is about `7.1 m` from Planned Home. All airborne mission items use relative altitude. Each waypoint has a `2 m` acceptance radius. The QGC plan uses `3 m/s` as its multirotor time-estimation speed; the aircraft's ArduPilot navigation parameters determine actual flight speed because this plan contains no speed-change command.

## QGroundControl review

1. Keep the propellers removed.
2. Open QGroundControl and select **Plan**.
3. Select **Open** and choose `Camp_Mackall_QGC_TEST_5m.plan`.
4. Confirm the route contains Takeoff, three Waypoints, and RTL in that order.
5. Confirm every airborne item shows `5 m` relative altitude and the route remains within the intended open clearing.
6. Do not select **Upload** during the indoor review.

Opening the file changes only QGroundControl's planning workspace. **Upload** sends the displayed plan to the flight controller. **Download** replaces the planning workspace with the mission currently stored on the flight controller.

AUTO mode executes the mission stored on the flight controller after all outdoor preflight checks pass. RTL is the final mission command and can also be triggered by configured failsafes; actual RTL behavior follows the aircraft's current ArduPilot RTL settings.

Before any upload or outdoor execution, verify the real launch point, GPS/home lock, obstacle clearance, airspace permission, weather, battery sensing, and the route against current imagery.

## Controller check on 2026-09-19

A read-only MAVLink mission query returned one sequence-zero Home placeholder (`NAV_WAYPOINT`, global frame). No executable mission items were stored on the flight controller. The QGC test plan remained local and was not uploaded.
