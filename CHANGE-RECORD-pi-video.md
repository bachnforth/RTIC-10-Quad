# Change record: Pi video over the mesh

Every setting changed on the radios, Pi and laptop, with the original value so it can be reverted.

| When | Device | Setting | Original | New | Status |
|---|---|---|---|---|---|
| 2026-09-23 17:03 | Laptop | Ethernet 5 (Mini's LAN9500A) Speed & Duplex | Auto Negotiation | 100 Mbps Full Duplex | Reverted to Auto Negotiation at 17:05 (did not bring the link up) |
| 2026-09-23 17:10 | Laptop | Windows Mobile Hotspot (SSID RN081) | Off | On | Active; turn off in Settings > Network & internet > Mobile hotspot |
| 2026-09-23 | Pi | NetworkManager `RoboticsLan` autoconnect (user typed) | yes | no | Active; restore with `sudo nmcli connection modify RoboticsLan autoconnect yes` |
| 2026-09-23 18:04 | Pi | `quadpi-camera-preview.service` (analog FPV preview on composite out) | running, enabled | disabled and stopped | `picam-stream` now drives the analog output too. Revert: `sudo systemctl disable --now picam-stream && sudo systemctl enable --now quadpi-camera-preview` |
| 2026-09-23 17:3x | Pi | Installed packages gstreamer1.0-tools, -plugins-base, -plugins-good, -plugins-bad (fetched over RoboticsLan) | not installed | installed | `sudo apt remove` them to revert |
| 2026-09-23 18:04 | Pi | Installed `/usr/local/bin/picam-stream.sh`, `/etc/systemd/system/picam-stream.service`, `/etc/default/picam-stream`; service enabled | none | stream to 10.223.58.11:5600, 720p30, 1.5 Mbit/s, FPV_PREVIEW=1 | Active. Copies of the scripts in `~/pi-video` on the Pi |
| 2026-09-24 08:15 | User's handheld (radio MAC 00:30:1A:3C:C4:82) | Simple Configuration: Mesh ID, mesh password, channel (user entered) | Mesh ID 0105, channel 12 (915 MHz), placeholder password | Mesh ID 666, channel 20 (907 MHz), mesh password; bandwidth 10 MHz, distance 2000 m, TPC on unchanged | Active. Wi-Fi AP `Meshnet-0610` on radio1 unchanged |
| 2026-09-24 08:15 | User's handheld | Management IP (side effect of Simple Configuration Save & Apply) | 10.223.196.108 | 10.223.196.130 (the radio's default, from its MAC C4:82) | Unique on the mesh; roster table should say .130 |
| 2026-09-24 08:40 | Galaxy S24 | Wi-Fi `Meshnet-0610` IP settings (user entered) | DHCP | Static 10.223.58.11/16, gateway and DNS 10.223.58.1 (placeholders, nothing uses that address) | Active. Also Auto reconnect turned off for RoboticsLan-5G and Meshnet-0610; USB debugging turned on |
| 2026-09-24 08:30 | Laptop | Google SDK Platform-Tools (adb) unzipped to `platform-tools\` in this folder | not present | present | Delete the folder to remove |
| 2026-09-24 09:05 | Pi | `/etc/default/picam-stream` DEST_HOST (hotspot test; QGC on the phone showed live video) | 10.223.58.11 | 192.168.137.3 (TEMPORARY) | Revert: `sudo cp /etc/default/picam-stream.mesh-backup /etc/default/picam-stream && sudo systemctl restart picam-stream` |
| 2026-09-24 09:00 | Galaxy S24 | Wi-Fi `RN081` IP settings (user entered) | DHCP (failed: the hotspot hands out no addresses) | Static 192.168.137.3/24, gateway and DNS 192.168.137.1 | Only for the hotspot test |
| 2026-09-28 | Pi | `/etc/default/picam-stream` DEST_HOST restored from `.mesh-backup` (Pi now wired to the user's handheld 10.223.196.130 with a custom USB cord; Mini not used) | 192.168.137.3 | 10.223.58.11 | Active |
| 2026-09-28 | Pi | Persistent system logs: `/etc/systemd/journald.conf.d/persistent.conf` (Storage=persistent, SystemMaxUse=50M) and `/var/log/journal` | logs lost at every reboot | logs kept across reboots, capped at 50 MB | Active. Revert: `sudo rm /etc/systemd/journald.conf.d/persistent.conf && sudo rm -r /var/log/journal && sudo systemctl restart systemd-journald` |
| 2026-09-23 | pi-video scripts | Stream destination DEST_HOST; added FPV_PREVIEW option | 10.223.58.10 (laptop), no preview | 10.223.58.11 (Galaxy S24), preview on | Edited in this folder |

## Findings, 2026-09-23 evening (no changes made)
- Laptop on the handheld's USB-D (`Ethernet 3`, 10.223.58.10/16) reaches the Mini (10.223.196.148, 3-20 ms) and Josh's handheld #18 (10.223.196.126) over mesh 666. The handheld is already on mesh 666; it did not answer at 10.223.196.108.
- The Mini's radio is healthy, but its built-in USB-Ethernet chip (LAN9500A, MAC 00:30:1A:3C:4F:16) has no link on the Pi or the laptop, including after a power cycle.
- Mini kernel log: `eth0` (AG71xx, MII, external PHY uid 004dd042, MAC …4F:14) joins br-wan and never gets a link. `eth1` (AR934X built-in switch, MAC …4F:15) went to forwarding at 23.68 s, then down at 23.86 s. eth0 and eth1 both show 0 packets. No interface is misconfigured.
- It worked on the Pi on 2026-09-22. On 2026-09-23 the laptop logged "Device Descriptor Request Failed" (15:37) and then read the chip's MAC as the unprogrammed default 00:80:0F:11:70:00 (16:28), which suggests an electrical problem on the USB harness or board around then.

- 2026-09-24 12:24, read on the Pi (no changes made): the LAN9500A's EEPROM is intact (MAC 00:30:1A:3C:4F:16). Its built-in PHY (SMSC OUI 00:01:F0, model 15) answers, has auto-negotiation on, advertises 10/100, and has energy-detect power-down off (reg 17 = 0x0000). It reports no link (BMSR 0x7809), nothing from a link partner (reg 5 = 0x0001, reg 6 = 0x0000) and no energy on the line (reg 17 ENERGYON = 0). So the USB chip is healthy and sending, but it gets no signal at all from the radio's eth0 side. Suspect the Mini's radio-side eth0 PHY or the board connection between them. Next step: swap-test with one of Josh's Minis, then Doodle Labs support.

Note: the Pi's hotspot profile is named `RN081-statice` (typo from 2026-09-22). The laptop hotspot connects the Pi but does not pass internet through (cause not found).

## 2026-09-30: safety arbiter bench setup
| When | Device | Setting | Original | New | Status |
|---|---|---|---|---|---|
| 2026-09-30 | Laptop | Wi-Fi adapter IPv4 (user entered, Settings) | Automatic (DHCP) | Manual 10.223.58.10/16, no gateway, no DNS | Active. Applies to the whole Wi-Fi adapter, so RN08 etc. will not get an address. Revert: Settings > Wi-Fi > properties > IP assignment > Automatic (DHCP) |
| 2026-09-30 | Laptop | Wi-Fi joined Meshnet-0610 (saved profile) | RN08 (phone hotspot) | Meshnet-0610 | Active |
| 2026-09-30 | Galaxy S24 | USB tethering (user) / Mobile Hotspot (user) / Wi-Fi | tethering off, hotspot on, Wi-Fi on | tethering on (laptop internet over USB), hotspot off, Wi-Fi off (turned off by Claude via adb because joining the mesh broke tethered internet) | Active. Turn Wi-Fi back on in phone settings when needed |
| 2026-09-30 | Pi | `/boot/firmware/cmdline.txt`: removed `console=serial0,115200` (no login console on GPIO14/15, which now go to the LUX) | `console=serial0,115200 console=tty1 ...` | `console=tty1 ...` | Active. Backup `cmdline.txt.pre-safety-arbiter`. Revert: `sudo cp /boot/firmware/cmdline.txt.pre-safety-arbiter /boot/firmware/cmdline.txt` and reboot |
| 2026-09-30 | Pi | `/boot/firmware/config.txt`: appended `enable_uart=1` under `[all]` (turns on the GPIO14/15 UART for the LUX MAVLink link) | not present (no /dev/serial0) | `enable_uart=1` | Active. Backup `config.txt.pre-safety-arbiter`. Revert: copy the backup back and reboot |
| 2026-09-30 | Pi | Python venv `~/mavenv` with pymavlink 2.4.50, fastcrc 0.5.0, lxml 6.1.3 (offline wheels in `~/safety-arbiter/wheels`) | none | installed | Active. Remove: `rm -r ~/mavenv ~/safety-arbiter/wheels` |
| 2026-09-30 | Pi | `~/safety-arbiter/safety_mavlink_filter.py` (SHA-256 09f002b3...c56c79c); not running, not a service | none | copied | Active. Remove the folder to revert |
| 2026-09-30 | LUX | Full parameter backup before changes | - | `params\LUXF765_PRE_SAFETY_ARBITER_2026-09-30.param` (1213 params) | Reference for revert |
| 2026-09-30 | LUX SD | `APM/scripts/esad_gate.lua` renamed (user approved) - old SA-based gate that would conflict with the arbiter | `esad_gate.lua` | `esad_gate.lua.disabled` | Active. Copy in `backups\LUX_SD_scripts_2026-09-30\`. Revert: rename back (MAVFtp) and set SERVO9/10 as that script expects |
| 2026-09-30 | LUX SD | Added `APM/scripts/safety_arbiter.lua` (SHA-256 05b49ed6...) and `APM/scripts/modules/MAVLink/` mavlink_msgs.lua, mavlink_msg_COMMAND_LONG.lua, mavlink_msg_COMMAND_ACK.lua; all verified by readback | none | present | Active. Revert: delete them |
| 2026-09-30 | LUX | SERVO9_FUNCTION / SERVO10_FUNCTION | 145 / 148 | 94 / 95 | Active. Revert: 145 / 148 |
| 2026-09-30 | LUX | SERIAL2_PROTOCOL / SERIAL2_BAUD (ESP32 status on RX5) | -1 / 57 | 28 / 115 | Active |
| 2026-09-30 | LUX | SERIAL1_PROTOCOL / SERIAL1_BAUD (Pi MAVLink on TX1/RX1) | -1 / 57 | 2 / 115 | Active |
| 2026-09-30 | Galaxy S24 | Added `Android/data/org.mavlink.qgroundcontrol/files/QGroundControl/MavlinkActions/SafetyDevice.json` (SHA-256 218e8e4d...) via adb | none | present | Active. Revert: delete the file and clear the Fly View actions file setting in QGC |
| 2026-09-30 | Pi | pyserial 3.5 added to `~/mavenv` (needed by the filter) | none | installed | Active |
| 2026-09-30 | Pi | Filter started by hand (nohup), target laptop 10.223.58.10:14550 for bench stage 1 | not running | running | Temporary; not a service. Stop: `pkill -f "mavenv/bin/python safety"` |
| 2026-09-30 11:0x | Pi | Filter restarted with target the Galaxy 10.223.58.11:14550 for bench stage 2 (earlier stage 1 target laptop 10.223.58.10:14560) | - | running | Temporary; not a service |
| 2026-09-30 11:27 | LUX SD | `APM/scripts/safety_arbiter.lua` replaced with v2 (43bd5aa8...) | v1 05b49ed6... | v2 | Superseded (stopped on hardware, see BENCH_RESULTS) |
| 2026-09-30 12:4x | LUX SD | `APM/scripts/safety_arbiter.lua` replaced with v3 (b6e86ec0...) | v2 43bd5aa8... | v3 | Active. Copies of v1 and v3 in `backups\` |
| 2026-09-30 | Laptop | QGroundControl process ended (user approved) - it had taken COM6/COM9 | running | closed | - |
| 2026-09-30 13:0x | Pi | systemd service `safety-mavlink-filter.service` installed and enabled (user approved): runs the filter at boot, target Galaxy 10.223.58.11:14550, Restart=always | manual start | service | Active. Revert: `sudo systemctl disable --now safety-mavlink-filter && sudo rm /etc/systemd/system/safety-mavlink-filter.service && sudo systemctl daemon-reload` |

## 2026-09-30: jamming-test mesh logger
| When | Device | Setting | Original | New | Status |
|---|---|---|---|---|---|
| 2026-09-30 18:29 UTC | Pi | System clock set from the laptop (`sudo date -u -s @<epoch>`) | Thu 24 Sep 02:03 UTC (6.5 days slow) | Wed 30 Sep 18:29 UTC | Drifts again after power-off; re-set before each test |
| 2026-09-30 | Pi | Added `~/jamming/` (mesh_logger.py, analyze_jamming.py, README.md; source in `C:\Users\ebach\Documents\Claude\10 inch\Jamming\`) | none | present, not running, not a service | Remove: `rm -r ~/jamming` |
| 2026-09-30 | Pi | SSH key `~/.ssh/radio_key` (RSA 2048, no passphrase) for reading the handheld's radio stats | none | created and installed on the handheld (below) | Remove: `rm ~/.ssh/radio_key*` |
| 2026-09-30 | Pi | Test logs in `/tmp/jam_test`, `/tmp/jam_test2` | none | present | Cleared at reboot |
| 2026-09-30 18:38 UTC | User's handheld (10.223.196.130) | Pi's `radio_key.pub` appended to `/etc/dropbear/authorized_keys` (user typed the password) | Pi key not present | present; Pi can log in as root with the key | Active. Revert: remove the line ending `pi-mesh-logger` from that file |
| 2026-09-30 14:3x | LUX | Firmware reflashed with the identical official ArduCopter 4.7.1 (git dbe79216, LumenierLUXF765-NDAA apj from firmware.ardupilot.org, ArduPilot uploader.py over USB) to erase the crash dump from the 10:15 watchdog reset (user chose option 1) | 4.7.1 dbe79216 + crash dump | 4.7.1 dbe79216, no crash dump | Done. Backup before: `params\LUXF765_PRE_REFLASH_2026-09-30.param`; all 1224 params kept (only auto-updated calibrations, stream rates and counters differ); ARMING_CRSDP_IGN stays 0; CrashDump pre-arm gone; arbiter v3 running |

## 2026-10-01: mesh logger runs at boot
| When | Device | Setting | Original | New | Status |
|---|---|---|---|---|---|
| 2026-10-01 16:0x UTC | Pi | `~/jamming/mesh_logger.py` updated: `mono_s` column, `clock_step` events, boot-id in file names, trims `~/jam_logs` to 500 MB at startup | previous version | new version | Active. Previous copy kept as `~/jamming/mesh_logger.py.pre-boot-service` |
| 2026-10-01 16:04 UTC | Pi | systemd service `mesh-logger.service` installed and enabled (user approved): runs the logger at boot as ebach, Restart=always, targets handheld_self/phone/josh_handheld + radio + filter status, logs to `~/jam_logs` | none (started by hand) | runs at boot; verified after a reboot at 16:06 UTC | Active. Revert: `sudo systemctl disable --now mesh-logger && sudo rm /etc/systemd/system/mesh-logger.service && sudo systemctl daemon-reload` |
| 2026-10-01 | Pi | Pi rebooted once by Claude to verify the service (filter and picam-stream came back active) | - | - | - |
