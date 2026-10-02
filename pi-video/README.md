# Pi camera to QGroundControl over the Doodle mesh

Video path: Pi camera -> Pi Zero 2 W (10.223.58.30) -> Doodle mini on the drone
-> mesh -> handheld radio -> handheld's Wi-Fi -> QGroundControl on the Galaxy S24 (10.223.58.11, UDP port 5600).
To send to the laptop instead, set DEST_HOST="10.223.58.10" in `/etc/default/picam-stream`.

## Files
- `setup-video.sh` : one-time install (video software + auto-start service). Needs Wi-Fi/internet.
- `picam-stream.sh` : the stream itself (720p, 30 fps, 1.5 Mbit/s H.264).
- `picam-stream.service` : makes the stream start at every boot.
- `set-mesh-address.sh` : sets the Pi's permanent mesh address, 10.223.58.30.

## QGroundControl settings (on the laptop)
Application Settings -> General -> Video:
- Video Source: **UDP h.264 Video Stream**
- UDP Port: **5600**
Windows Firewall must allow QGroundControl to receive UDP 5600.

## Changing quality later
On the Pi, edit `/etc/default/picam-stream`, then `sudo systemctl restart picam-stream`.
Only raise BITRATE after testing how much the mesh can carry.

## Useful checks on the Pi
- `systemctl status picam-stream` : is it running?
- `journalctl -u picam-stream -n 30` : recent errors
- `rpicam-hello --list-cameras` : is the camera detected?
- `vcgencmd get_throttled` : 0x0 means the 5 V supply is healthy
