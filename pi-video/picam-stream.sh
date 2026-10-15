#!/bin/bash
# Streams the Pi camera to QGroundControl as H.264 video over UDP (RTP),
# and (optionally) shows the same picture on the composite output for the analog FPV transmitter.
# Settings live in /etc/default/picam-stream so they can change without editing this file.

DEST_HOST="10.223.58.11"   # the Galaxy S24 running QGroundControl (laptop would be 10.223.58.10)
DEST_PORT="5600"           # QGC's default video port
WIDTH="1280"
HEIGHT="720"
FPS="30"
BITRATE="1500000"          # bits per second (1.5 Mbit/s); raise only after a mesh throughput test
FPV_PREVIEW="1"            # 1 = also show the picture on the composite (analog FPV) output, 0 = off

[ -f /etc/default/picam-stream ] && . /etc/default/picam-stream
DASHBOARD_MIRROR_PORT="${DASHBOARD_MIRROR_PORT:-0}"

# The camera can only be used by one program, so this replaces quadpi-camera-preview.service.
if [ "$FPV_PREVIEW" = "1" ]; then PREVIEW_OPT="--fullscreen"; else PREVIEW_OPT="--nopreview"; fi
SINK=(udpsink "host=$DEST_HOST" "port=$DEST_PORT" sync=false async=false)
if [ "$DASHBOARD_MIRROR_PORT" != "0" ]; then
    [[ $DASHBOARD_MIRROR_PORT =~ ^1560[0-9]$ ]] || { echo 'Invalid dashboard mirror port' >&2; exit 1; }
    SINK=(multiudpsink "clients=$DEST_HOST:$DEST_PORT,127.0.0.1:$DASHBOARD_MIRROR_PORT" sync=false async=false)
fi

# rpicam-vid grabs the camera and compresses it with the Pi's hardware H.264 encoder.
# --inline repeats the stream headers so QGC can join mid-stream.
# --intra sends a full "key frame" once a second so lost packets heal quickly.
# --flush pushes each frame out immediately (lower delay).
# gst-launch-1.0 then wraps the video in RTP packets and sends them over UDP.
exec rpicam-vid -t 0 $PREVIEW_OPT \
  --width "$WIDTH" --height "$HEIGHT" --framerate "$FPS" \
  --codec h264 --profile baseline --inline --intra "$FPS" \
  --bitrate "$BITRATE" --flush -o - \
| gst-launch-1.0 -q fdsrc fd=0 ! h264parse config-interval=-1 \
    ! rtph264pay config-interval=1 pt=96 \
    ! "${SINK[@]}"
