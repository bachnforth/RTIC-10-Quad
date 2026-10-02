# Handover: Pi camera video to QGroundControl over the Doodle Labs mesh

Date: 2026-09-23
Project folder: `C:\Users\ebach\Documents\ChatGPT\10 inch Quad`
Read first: `HANDOVER-doodle-mini.md` (2026-09-22, same folder) for the Mini/Pi networking background,
and `pi-video\README.md` for the video scripts written today.

## About the user
- New to programming. Define jargon when you use it (DHCP, subnet, SSH, adapter, etc.).
- Wants you to do the work: run the commands yourself. Ask the user only for physical tasks
  (cables, power, typing passwords) and for approvals.
- Never ask the user to paste passwords. The user types the Mini/handheld admin password and the
  mesh password into the radio's own web page. Do not record or store them.

## END STATE (definition of done)
1. **Radios on the shared mesh.** The Mini (on the drone) and the handheld (on the ground) both use:
   Mesh ID `666`, channel 20 (907 MHz), 10 MHz bandwidth, band 915v4, WPA3-SAE, scenario "Mesh on radio0",
   operating distance 2000 m, mesh password supplied by the user. Bench TX power 16 dBm with a fan on
   the Mini (field use: set to max, verified over SSH). Management IPs (Roster #8): Mini `10.223.196.148/16`,
   handheld `10.223.196.108/16`. Do not delete any interface on Network > Interfaces (WAN3 is the config path).
2. **Laptop on the mesh.** Laptop plugged into the handheld's USB-D port; that adapter has static
   `10.223.58.10`, mask `255.255.0.0`, NO gateway. `ping 10.223.196.126` (Josh's handheld #18) and
   `ping 10.223.196.140` (Josh's mini) succeed.
3. **Pi on the mesh.** Pi Zero 2 W (hostname `quadpi`, user `ebach`, Debian 13) has NetworkManager profile
   `mesh-doodle` = static `10.223.58.30/16`, no default route (Wi-Fi keeps internet). Laptop can ping and SSH to
   `10.223.58.30` over the mesh.
4. **Video service on the Pi.** Scripts in `pi-video\` installed via `sudo bash setup-video.sh`. Service
   `picam-stream` is enabled, starts at boot, and sends H.264/RTP (720p, 30 fps, 1.5 Mbit/s) from the Pi Camera
   Module 2 to `10.223.58.10` UDP port 5600.
5. **QGroundControl shows live video.** QGC (Windows) > Application Settings > General > Video >
   Video Source = "UDP h.264 Video Stream", UDP port 5600. Windows Firewall allows QGC to receive UDP 5600
   (needs admin PowerShell; ask the user before changing the firewall).
6. **Throughput checked before flight.** Measure what the mesh actually carries between the Pi and laptop
   (e.g. iperf3, if the user approves installing it) and confirm 1.5 Mbit/s is sustainable. Reason: on 21 Sep the
   team saw small packets cross the mesh while bandwidth-heavy traffic did not. Lower BITRATE in
   `/etc/default/picam-stream` if needed.
7. **Change record written.** Update this folder with a short note listing every setting changed on the radios,
   Pi and laptop, plus the original values so anything can be reverted.

## Current state (as of 16:45 local)
- Files written today in `pi-video\`: `setup-video.sh`, `picam-stream.sh`, `picam-stream.service`,
  `set-mesh-address.sh`, `README.md`. Shell syntax checked but NOT run on a Pi. Verify rpicam-vid flags on the
  Pi (`rpicam-vid --help`) and the GStreamer pipeline before trusting them.
- Camera: Raspberry Pi Camera Module 2, ribbon already installed on the Pi Zero.
- No radio settings have been changed. No Windows settings have been changed. No firmware flashed.
- The user is Roster #8 (Pi `10.223.58.30`, laptop `10.223.58.10`, handheld/mini mgmt IPs above).
  Confirm against the address plan in `MESH_JOIN_GUIDE_Roster3_8` (user's Downloads / attached) if in doubt.

## Blocking problem right now
- **Windows does not see the Mini when its USB data cable is plugged into the laptop's left USB-A port**
  (JST-to-USB-A harness, Mini powered from the flight battery via a 5 V BEC). The Settings > Network adapter
  list shows only: Ethernet (Realtek, laptop port), Ethernet 4 (Realtek USB dongle), Ethernet 5
  (Microchip LAN9500A "Adapter #2", MAC 00:80:0F:11:70:00, manual 10.223.58.10/16, not connected; probably
  from the handheld work), VirtualBox, McAfee VPN, Wi-Fi x2. No new adapter and no "unknown USB device"
  appeared. The user says the cable is fine. The Mini's own MAC should be 00:30:1A:3C:4F:16.
- Per the handover, the Mini WAS proven working on the Pi over USB (Pi `10.223.79.20`, Mini `10.223.79.19`,
  ping 0.5 ms, web UI is HTTPS with a self-signed certificate). The laptop-to-Mini USB link was never proven.
- Suggested first checks: `Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -like 'USB*' }`,
  Device Manager for unknown/failed USB devices, `pnputil /enum-devices /connected /class Net`, try another
  USB-A port, confirm no 5 V on the Mini's Port 1 pin 1 (must stay empty), try swapping D+/D-.
- Fallback: put the Mini back on the Pi and configure it from there (see below).

## Reaching the Pi and Mini (constraints)
- Laptop Wi-Fi `192.168.40.119/23` and Pi Wi-Fi `192.168.40.193/23` are on RoboticsLan, which uses client
  isolation: the laptop cannot reach the Pi over that Wi-Fi. A phone hotspot (WPA2) likely avoids this.
- The Pi Zero 2 W has ONE USB data port. The keyboard and the Mini cannot both be connected without an OTG hub.
  Power-cycle the Pi with the keyboard already attached if the keyboard stops responding.
- SSH key for the Pi: `C:\Users\ebach\.ssh\id_ed25519_rpi`.
- Once the Pi and laptop are both on the mesh, laptop-to-Pi SSH at `10.223.58.30` works over the mesh
  (the mesh has no DHCP and no internet, so every device uses a static IP with no gateway).
- To install packages the Pi needs internet: keep its Wi-Fi up. `setup-video.sh` installs GStreamer.
- Fallback way to configure the Mini from the Pi: hotspot + a small relay on the Pi (for example socat) so the
  laptop browser can open the Mini's HTTPS page; the user types the passwords there.

## Safety rules (from the team's mesh guide)
1. Never transmit without BOTH antennas on the Mini. Whips on before power, every time.
2. Heatsink clamped on the Mini, and a fan on the bench at low TX power (16 dBm). Full power with no
   airflow overheats it and drops it off the mesh.
3. Never probe the live 1 mm header pins on the Mini. Never put 5 V on Port 1 pin 1 or on the unused ports.
4. Every Doodle radio also answers at `192.168.153.1` on its USB/config port, and that address is bridged into
   the mesh. Use it only with all other radios powered off.
5. Sticker IPs are unreliable; read the live IP on Network > Interfaces (br-wan).
6. Do the bench work with props OFF and the flight controller unarmed.

## Approvals and boundaries
- Ask before: installing software on the laptop or Pi, changing Windows firewall or adapter settings,
  saving or applying radio settings, downloading files.
- Do not change anything on Josh's radios. Do not guess the mesh password.
- Clean shutdown of the Pi (`sudo shutdown -h now`) before cutting flight-pack power.

## Quick facts
- Mini: RM-1700-22M3, label MAC 00:30:1A:3C:4F:13, label IP 10.223.79.19.
- Handheld ("wearable"): RM-1700-22W3 / SmartRadio, currently mesh ID 0105, channel 12, placeholder key.
- Josh's nodes: handheld #18 `10.223.196.126`, handheld #13 `.196.102`, mini repeater #1 `.196.140`,
  repeater #2 `.196.141`; Josh's laptop `10.223.50.10`, Pi `10.223.50.30`.
- Older Pi NetworkManager profile `mini` (10.223.79.20/16) is renamed/changed by `set-mesh-address.sh`.
