#!/bin/bash
# One-time setup on the Pi. Run with:  sudo bash setup-video.sh
# Installing the video software needs internet (the mesh has none); skipped if already installed.
set -e

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this with sudo:  sudo bash setup-video.sh"
  exit 1
fi

HERE="$(cd "$(dirname "$0")" && pwd)"

if ! command -v gst-launch-1.0 >/dev/null; then
  echo "== Installing video software =="
  apt-get update
  apt-get install -y --no-install-recommends gstreamer1.0-tools gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good gstreamer1.0-plugins-bad
fi
command -v rpicam-vid >/dev/null || apt-get install -y rpicam-apps-lite

echo "== Checking the camera is detected =="
rpicam-hello --list-cameras || echo "WARNING: camera not detected. Check the ribbon cable, then reboot."

echo "== Retiring the old FPV preview service (picam-stream now drives the analog output) =="
if systemctl list-unit-files quadpi-camera-preview.service >/dev/null 2>&1; then
  systemctl disable --now quadpi-camera-preview.service || true
fi

echo "== Installing the stream script and auto-start service =="
install -m 755 "$HERE/picam-stream.sh" /usr/local/bin/picam-stream.sh
install -m 644 "$HERE/picam-stream.service" /etc/systemd/system/picam-stream.service
[ -f /etc/default/picam-stream ] || cat > /etc/default/picam-stream <<'EOF'
# Edit these to change the stream, then run: sudo systemctl restart picam-stream
DEST_HOST="10.223.58.11"   # phone; use 10.223.58.10 for the laptop
DEST_PORT="5600"
WIDTH="1280"
HEIGHT="720"
FPS="30"
BITRATE="1500000"
FPV_PREVIEW="1"            # 1 = also show on the analog FPV (composite) output
EOF
systemctl daemon-reload
systemctl enable picam-stream.service
systemctl restart picam-stream.service

echo
echo "Done. The stream now starts automatically at every boot."
echo "Check it with:  systemctl status picam-stream"
echo "To go back to the old preview-only setup:"
echo "  sudo systemctl disable --now picam-stream && sudo systemctl enable --now quadpi-camera-preview"
