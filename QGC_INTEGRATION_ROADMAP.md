# QGroundControl integration roadmap

## Current mission capability

Completed on 2026-09-20:

- QGroundControl is installed on the Galaxy S24 and receives live ArduCopter telemetry.
- The Galaxy loads the vehicle parameters and can open local `.plan` files.
- The Camp Mackall test plan is stored in QGC's Android app folder:
  `Android/data/org.mavlink.qgroundcontrol/files/QGroundControl/Missions`.
- A filtered MAVLink relay connects QGC to the LUX F765 through the PC and local Wi-Fi.
- The relay permits parameter and mission downloads plus ordinary mission uploads.
- It blocks parameter writes, arming, mode changes, manual-control messages, actuator commands, and non-mission fence/rally writes.
- No mission has been uploaded during this phase.

The current workflow supports creating, editing, saving, opening, downloading, and uploading ordinary waypoint missions while the aircraft, PC, and phone remain connected to the same bench network.

## Mission workflow

1. Create or open a plan in QGC Plan view.
2. Confirm the firmware is ArduPilot and the vehicle is a multirotor.
3. Review Planned Home, relative altitude, waypoint order, acceptance radius, speed, and the final RTL or Land command.
4. Save the plan locally before uploading.
5. Select Upload only when the exact displayed plan is approved for transfer.
6. After upload, use Download from Vehicle and compare the returned mission with the saved file.
7. Mission upload stores commands but does not start them. AUTO/Start Mission is a separate flight action.

The first upload should be a props-off bench round trip: upload the approved test mission, download it again, and confirm every item. Do not arm or start the mission during that test.

## Remaining blockers before flight

- Resolve the excessive magnetic-field pre-arm failure in a clean location.
- Verify the launch position and route outdoors with reliable GPS/Home establishment.
- Review the configured 14.0 V critical battery threshold and the currently unset low-battery threshold.
- Decide whether the disabled GCS failsafe is appropriate for the eventual field telemetry link.
- Complete current airspace, NOTAM, site-permission, obstacle, weather, and battery checks.
- Validate RC input and failsafe behavior with the transmitter connected.

## Field telemetry architecture

The present PC relay is suitable for setup and mission management on the bench. Field use needs a direct vehicle-to-Galaxy data path.

Preferred future architecture:

```text
LUX F765 MAVLink
        |
        v
Onboard companion computer / MAVLink router
        |
        +--> Wi-Fi or LTE IP link --> Galaxy QGroundControl
```

QGC can use UDP, TCP, serial, Bluetooth, and supported telemetry-radio links. A companion computer can route MAVLink over UDP while keeping flight-critical control and failsafes in ArduPilot.

Suggested logical separation:

- MAVLink telemetry and mission traffic: UDP port `14550`.
- Video: a separate RTSP session or UDP video port such as `5600`.
- Existing RadioMaster/ELRS: primary direct manual-control link.
- Existing ESP32 safety system: independent of QGC, LTE, video, and the companion computer.

Loss of QGC, video, LTE, Wi-Fi, or the companion computer must not assert either ESP32 safety command.

## Future video architecture

The existing Raspberry Pi service only provides a local fullscreen camera preview. QGC needs an encoded network stream:

```text
Camera
  |
  v
Raspberry Pi / video encoder
  |
  +--> H.264 or H.265 over RTSP or UDP
  |
  v
Wi-Fi or LTE network
  |
  v
QGroundControl Fly view
```

QGC supports RTSP, UDP H.264, UDP H.265, TCP-MPEG2, and MPEG-TS sources. RTSP is the preferred first integration target because its stream address is explicit and it is straightforward to test on the local network. UDP H.264 on port `5600` is a suitable alternative when minimum latency is more important than recovery from packet loss.

Keep the existing analog FPV video path independent during initial digital-video development. The digital stream should be treated as situational-awareness video until end-to-end latency, interruptions, thermal load, and recovery after network loss have been measured.

No video hardware purchase or aircraft wiring change is part of the current mission-integration phase.

## Future QGC flight commands

QGC can issue confirmed actions such as Start Mission, Pause, RTL, Land, change altitude, Go To, and Orbit when supported by the connected firmware and vehicle state. These commands require a full command-enabled MAVLink path.

The current filtered relay intentionally blocks those actions. Enable command traffic only after the compass problem, RC/failsafe tests, outdoor GPS/Home checks, and command-by-command props-off validation are complete. Continue using the RadioMaster/ELRS link for direct piloting.

## References

- QGC communication links: https://docs.qgroundcontrol.com/master/en/qgc-user-guide/settings_view/comm_links.html
- QGC mission planning: https://docs.qgroundcontrol.com/master/en/qgc-user-guide/plan_view/plan_view.html
- QGC Fly tools and confirmation: https://docs.qgroundcontrol.com/master/en/qgc-user-guide/fly_view/fly_tools.html
- QGC video settings: https://docs.qgroundcontrol.com/master/en/qgc-user-guide/settings_view/video.html
