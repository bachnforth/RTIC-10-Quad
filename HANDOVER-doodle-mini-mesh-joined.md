# Handover: Doodle Labs Mini joined to Josh's mesh (Roster #8)

Date: 2026-09-23 (work done 2026-09-22)
Supersedes: `HANDOVER-doodle-mini.md` (Downloads) for the questions "is the Mini on the mesh?" and "does it work on the Pi?"
Related: `Pi-camera-integration-handover_to claude.docx` (same folder) covers the camera/video payload, a separate effort.

## About the user
- New to programming. Define jargon (DHCP, subnet, adapter, bridge).
- Wants Claude to run commands itself. Ask the user only for physical tasks (cables, power) and approvals.
- Claude must never handle passwords. The Mini admin password and the mesh password were typed by the user only and were never shared. Do not ask for them.

## Outcome: done
- **Mini is on Josh's mesh**: Mesh ID `666`, channel 20 (907 MHz), 10 MHz bandwidth, WPA3-SAE, radio0. Status showed 4 associated stations.
- **Mini management IP**: `10.223.196.148/16` (was `10.223.79.19`). Changed on the WAN2 interface (Advanced Settings > Network Configuration > Interfaces).
- **Mini identity**: model MB-1700v4-2L-X (sub-model RM-915v4-2L-X), firmware 2024-10.5, MAC `00:30:1A:3C:4F:13`, hostname `smartradio-301a3c4f13`. Login is `root` with a password the user set.
- **TX power**: left on automatic (TPC and Aggressive TPC). Josh confirmed this is fine. Operating distance is still 4000 m (guide suggests 2000 m for bench; not changed).
- **Mini plugged into the Pi works end to end**: Pi `eth0` linked up, the existing `mini` NetworkManager profile (static `10.223.79.20/16`) auto-applied, Pi pinged the Mini (<1 ms) and Josh's handheld `10.223.196.126` through the mesh (5-48 ms, after ~15 s for batman-adv routing to converge).
- **Roster table** in `C:\Users\ebach\Downloads\MESH_JOIN_GUIDE_Roster3_8.html` (Roster #8 mini row) is filled in except the admin password cell, which the user fills in themselves.

## Current state at handover (verify, it may have changed)
- The user moved the Mini's USB cable back to the laptop, but Windows was **not showing the LAN9500A adapter** afterwards. The user then said "disregard" (Josh approved the config, so no more Mini web-UI changes were needed). The Mini may or may not still be on the laptop.
- The old laptop adapter `Ethernet 5` (static `10.223.58.10/16`, no gateway) is gone from the adapter list. If the Mini is reconnected, Windows may create a new adapter name and the static IP must be set again (needs elevation, see gotchas).
- Windows Mobile Hotspot is ON: SSID `RN081`, WPA2, 2.4 GHz, laptop side `192.168.137.1/24`. Password is in Settings > Network & internet > Mobile hotspot (not recorded here).
- Pi (`quadpi`, user `ebach`) is on the hotspot via profile `RN081-static` at `192.168.137.2/24`. `RoboticsLan` autoconnect was re-enabled, so after a Pi Wi-Fi reconnect or reboot it will go back to `RoboticsLan` (`192.168.40.193`), which the laptop cannot reach (client isolation).
- SSH: `ssh -i C:\Users\ebach\.ssh\id_ed25519_rpi ebach@192.168.137.2` (only works while the Pi is on the hotspot).

## Mesh reference (from `MESH_JOIN_GUIDE_Roster3_8.html`)
- Flat `10.223.0.0/16`, no DHCP, no internet, no gateway. Static IPs only.
- Roster #8: laptop `10.223.58.10`, phone `.58.11`, Pi `.58.30`, handheld mgmt `10.223.196.108`, mini mgmt `10.223.196.148`.
- Josh: handheld #18 `10.223.196.126`, mini repeater #1 `10.223.196.140`, repeater #2 `.141`, Pi `10.223.50.30`.
- Note: the Pi's current mesh-side address is `10.223.79.20`, not the guide's `10.223.58.30`. It works, but it is off-scheme. Optional cleanup.

## Open items
1. Admin password cell in the roster table (user only).
2. Tell Josh: the Mini's `WAN` alias picked up a DHCP lease (`10.196.98.24/8`, gateway `10.196.98.1`) from something on the mesh. The guide says there should be no DHCP on the mesh.
3. Optional: renumber the Pi's `mini` profile to `10.223.58.30/16` to match the roster scheme.
4. Optional: set Mini operating distance to 2000 m for bench work.
5. The Pi camera and power validation is a separate workstream (see camera handover). The user says the FC-shared-rail power has been flown for over a week without issues, though that document still lists it as an open decision.

## Gotchas learned (save time)
- **Elevated PowerShell**: `Start-Process powershell -Verb RunAs -File script.ps1` silently fails here (exit -196608). Base64-encode the script and use `-EncodedCommand`, have it write a transcript/sentinel file, then read that back.
- **Mini web UI is only reachable from a machine wired to it** (USB-Ethernet to the Mini, static IP in `10.223.0.0/16`, no gateway). The Claude built-in browser cannot reach it. The user logs in from their own browser; Claude must not enter passwords.
- **LuCI "Apply with revert" fails when you change the very address you are connected on.** It reverted twice, then worked on the third attempt once a second tab reloaded the new IP quickly.
- **Changing Channel in the Simple Configuration page silently resets Bandwidth** (it went to 3 MHz). Set it back to 10 MHz before submitting.
- **Pi Wi-Fi**: `RoboticsLan` autoconnect wins the radio and blocks other profiles. To use the hotspot: `sudo nmcli connection modify RoboticsLan autoconnect no`, `sudo nmcli connection down RoboticsLan`, `sudo nmcli connection up RN081-static`, then restore with `... autoconnect yes` when done. The fresh DHCP `RN081` profile kept timing out for an undiagnosed reason; the static `RN081-static` profile works.
- Passwords containing `$` need single quotes in bash.
- Windows-side mesh ping from the laptop only works while the laptop is wired to the Mini; moving the Mini's cable to the Pi cuts the laptop off from the mesh (use the hotspot to reach the Pi instead).
