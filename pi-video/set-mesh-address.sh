#!/bin/bash
# Gives the Pi its permanent mesh address (Roster #8: 10.223.58.30).
# Run with:  sudo bash set-mesh-address.sh
# WARNING: if you are connected over the mesh at the old address (10.223.79.20),
# this disconnects you. Reconnect at 10.223.58.30.
set -e

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this with sudo:  sudo bash set-mesh-address.sh"
  exit 1
fi

if nmcli -t -f NAME con show | grep -qx mini; then
  nmcli con mod mini connection.id mesh-doodle ipv4.addresses 10.223.58.30/16
else
  nmcli con add type ethernet con-name mesh-doodle ifname eth0 \
    ipv4.method manual ipv4.addresses 10.223.58.30/16 ipv4.never-default yes \
    ipv6.method disabled connection.autoconnect yes connection.autoconnect-priority 100
fi
# no gateway on the mesh, so Wi-Fi keeps handling internet traffic
nmcli con mod mesh-doodle ipv4.never-default yes
nmcli con up mesh-doodle || true
