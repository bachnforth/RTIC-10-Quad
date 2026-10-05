# Handover: mesh_logger.py (mesh-link logger for a Raspberry Pi on a drone)

Version: v2 with `--radio-extra`, 2026-10-05. File: `mesh_logger.py` in this folder.
SHA-256: `67146a330b77281e8217245a7a8a557633bc826018e9611a2fec2a35ef5feabd`

**Status of this version.** The radio-output parser is tested on real radio output (482 of 482 one-second blocks parsed). The radio-interface re-check is tested with a stub radio. The telemetry tap is tested with a fake telemetry sender. The `--radio-extra` option is syntax-checked only. **Nothing here has been run in flight, and the logger has only ever read Doodle Labs SmartRadio handhelds (firmware 2024-10.5), never a Doodle Labs Mini.** Treat a first run as a test.

## 1. What it does

It runs on the Raspberry Pi that is wired to the drone's Doodle Labs radio, and writes one CSV (plus a raw-output text file) per boot. About once a second it records:

| Rows (`node_id`) | What | Needs |
|---|---|---|
| `radio` | The drone-side radio's signal (dBm), noise floor, SNR, number of mesh neighbors, bit rates, retries, failed transmissions, bytes, link state | SSH key on that radio |
| `radio_<name>` | The same, for a second radio (for example the ground radio) | SSH key on that radio, and a network path to it |
| one per `--target` | Ping packets sent, received and delay to another mesh node | nothing |
| `gcs_uplink` | How many MAVLink messages the Pi's telemetry filter received from the ground station | the `safety_mavlink_filter` status file |
| `fc` | Drone latitude, longitude, altitude, ground speed and GPS time, read (without transmitting) from the telemetry the Pi sends toward QGroundControl | `pymavlink` and the `CAP_NET_RAW` permission |
| `logger` | Start and stop, clock corrections, trimmed old logs | nothing |

Every row also has `timestamp`, `wall_time_utc` and `mono_s` (seconds since the Pi booted, which never jumps).

## 2. Why it was changed (v1 to v2)

The first range test (2026-10-02) recorded no radio data. The radio is powered on after the Pi, so when the logger connected the radio's wireless interface did not exist yet, and v1 only looked once. v2 re-checks every second. v2 also records more link numbers and the drone's position and GPS time, and it can read a second radio.

## 3. Requirements

- A Raspberry Pi (tested: Pi Zero 2 W, Debian 13, Python 3) wired to a Doodle Labs radio.
- Python 3 only, for the core logger. The `fc` rows also need `pymavlink` (the Pi had it in `~/mavenv`).
- `ssh` and `ping` on the Pi.
- An SSH key on each radio you want to read (section 5).

## 4. Install on the Pi

1. Copy the file: `scp mesh_logger.py ebach@<pi-address>:~/jamming/mesh_logger.py`, then `chmod +x ~/jamming/mesh_logger.py`.
2. Make a key pair **on that Pi** (section 5).
3. Try it by hand first, with the radio powered, for a minute:
   ```
   python3 ~/jamming/mesh_logger.py --target phone=<phone-ip> --radio <drone-radio-ip> --radio-key ~/.ssh/radio_key --out-dir ~/jam_logs
   ```
   Each second you should see a `radio` row with `rssi_dbm` filled in. Stop it with Ctrl+C.
4. Install the service so it starts at every boot. Save this as `/etc/systemd/system/mesh-logger.service` (change the user, paths and addresses to match):
   ```
   [Unit]
   Description=Mesh link logger
   After=network.target

   [Service]
   Type=simple
   User=<your-user>
   ExecStart=/home/<your-user>/mavenv/bin/python /home/<your-user>/jamming/mesh_logger.py --quiet \
     --target ground=<ground-radio-ip> --target phone=<phone-ip> \
     --radio <drone-radio-ip> --radio-key /home/<your-user>/.ssh/radio_key \
     --radio-extra ground=<ground-radio-ip> \
     --mav-tap-port 14550 --out-dir /home/<your-user>/jam_logs --max-mb 500
   AmbientCapabilities=CAP_NET_RAW
   CapabilityBoundingSet=CAP_NET_RAW
   Restart=always
   RestartSec=5

   [Install]
   WantedBy=multi-user.target
   ```
   Then `sudo systemctl daemon-reload && sudo systemctl enable --now mesh-logger`.
   - Leave out `--mav-tap-port 14550` and the two `Ambient...` lines if your Pi has no MAVLink telemetry to a ground station.
   - Use `python3` instead of the `mavenv` path if you don't want the `fc` rows.
   - `--radio-extra` only works if the Pi can reach that radio across the mesh and the key is installed there.
5. The Pi has no clock battery, so its time is wrong after a power cycle. Set it before a test if you can (`sudo date -u -s '<UTC time>'`). The logger records the correction, and the `fc` rows carry GPS time as a backup.

## 5. SSH key (read this carefully)

- **The private key never leaves the Pi** that made it. Do not copy it, email it or put it in a repository.
- **The public key** (`~/.ssh/radio_key.pub`) goes on each radio you want to read, appended to `/etc/dropbear/authorized_keys`. Anyone who installs it needs that radio's admin password, typed by them.
- Make the key on the Pi: `ssh-keygen -t rsa -b 2048 -f ~/.ssh/radio_key -N ""`. (Doodle Labs radios on this firmware only accept the older `ssh-rsa` key type, so use RSA, and the logger passes the matching options.)
- Install it from a laptop plugged into the radio, using the radio's USB address (192.168.153.1 on the SmartRadios here):
  ```
  cmd /c 'ssh -o HostKeyAlgorithms=+ssh-rsa -o PubkeyAcceptedAlgorithms=+ssh-rsa root@192.168.153.1 "cat >> /etc/dropbear/authorized_keys" < "C:\path\to\radio_key.pub"'
  ```
  and type the radio's password when asked.
- To remove access later, delete that key's line from `/etc/dropbear/authorized_keys` on the radio.
- If you can't get the password, the logger still works without a key: the ping targets, `gcs_uplink` and `fc` rows are recorded, and the radio rows show `radio_ssh_down`.

## 6. Options

| Option | Meaning |
|---|---|
| `--target NAME=IP` | Ping this address about once a second (repeat for several) |
| `--radio IP` | The radio to read over SSH (logged as `radio`) |
| `--radio-extra NAME=IP` | Another radio to read (logged as `radio_NAME`), same user and key |
| `--radio-user`, `--radio-key`, `--radio-iface` | SSH user (default `root`), key file, and the radio's wireless interface (default: found automatically) |
| `--filter-status FILE` | The telemetry filter's status file, for `gcs_uplink` rows |
| `--mav-tap-port PORT` | Log drone position and GPS time from MAVLink sent to this UDP port |
| `--out-dir DIR`, `--max-mb N` | Where to write, and delete the oldest logs beyond N MB |
| `--quiet` | Don't print each row (use this in the service) |

## 7. CSV columns

`timestamp, wall_time_utc, node_id, rssi_dbm, snr_db, tx_count, rx_count, neighbors, latency_ms, event, noise_dbm, best_rssi_dbm, gcs_msgs_in, mono_s, tx_bitrate_mbps, rx_bitrate_mbps, tx_retries, tx_failed, rx_bytes, tx_bytes, inactive_ms, expected_mbps, radio_epoch, plink, fc_lat, fc_lon, fc_alt_m, fc_rel_alt_m, fc_gspeed_ms, fc_unix_s, fc_rows_s`

- `tx_retries` and `tx_failed` are running totals on the radio, so use the change per second.
- `radio_epoch` is the radio's own clock, which is not the real time. It is useful only for lining up radio rows with each other.
- `event` carries messages such as `radio_iface=wlan0`, `radio_ssh_down: ...` (the radio could not be reached) and `clock_step offset_s=...`.

## 8. Known limits

- **The `fc` tap only sees telemetry while the Pi can send it.** If the phone's address cannot be resolved on the mesh, no packets leave the Pi and the `fc` rows show zero messages. Use the flight controller's own log for position in that case.
- The tap logs what the Pi sent, not what the phone received.
- Pings and SSH to the ground radio only work while there is a mesh path to it.
- Because the Pi's clock may be wrong, file names (which use the Pi's clock at boot) can be misleading. Match files by their contents (`fc` rows, `mono_s`, duration), not their names.
- The raw text files (`mesh_raw_*.txt`) keep the radio's full output, so the parser can be improved later without a new flight.

## 9. Related files

- `analyze_jamming.py` and its README, in `C:\Users\ebach\Documents\Claude\10 inch\Jamming\`, read these CSVs.
- `CHANGE-RECORD-pi-video.md` lists every change made on the project's Pi, with how to revert it.
- The flight analysis that uses the flight controller log is in `range-test\flight_2026-10-02\`.
