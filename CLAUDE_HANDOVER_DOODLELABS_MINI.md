# Handover: Reach and configure Doodle Labs Mini through Raspberry Pi Zero 2 W

Date: 2026-09-22  
Workspace: `C:\Users\ebach\Documents\ChatGPT\10 inch Quad`

## Objective

Reach the Doodle Labs Mini installed on the drone. It is connected to a Raspberry Pi Zero 2 W. The immediate goal is to establish access to the Pi and determine whether the Pi can see and reach the Mini. Later, configure the Mini to meet the mesh-join guide, but only after the correct mesh password is obtained.

## Hardware identities

### Doodle Labs Mini

- Label MAC: `00:30:1A:3C:4F:13`
- Label IP: `10.223.79.19`
- Model: `RM-1700-22M3 A1000 D3325`
- Connected to the Raspberry Pi Zero 2 W; the exact USB/network interface still needs verification.

### Raspberry Pi Zero 2 W

- Hostname: `quadpi`
- Username: `ebach`
- User knows the password; it was created privately in Raspberry Pi Imager and was not recorded here.
- Wi-Fi MAC: `88:A2:9E:C4:B8:13`
- SSH key on laptop: `C:\Users\ebach\.ssh\id_ed25519_rpi`
- OS shown locally: Debian GNU/Linux 13, aarch64
- Current Wi-Fi address: `192.168.40.193/23` on `RoboticsLan`

### Windows laptop

- Normal Wi-Fi address: `192.168.40.119/23` on `RoboticsLan`
- Windows Mobile Hotspot adapter: `Local Area Connection* 2`
- Hotspot adapter MAC: `F6-4E-B4-DD-65-91`
- Hotspot address: `192.168.137.1/24`
- Hotspot SSID: `RN081`, 2.4 GHz
- Do not copy or expose the hotspot password from screenshots; the user knows it.

## Mesh-join guide

Source: `C:\Users\ebach\Downloads\MESH_JOIN_GUIDE_Roster3_8.html`

Confirmed requirements:

- Mesh ID: `666`
- Channel 20 / 907 MHz
- Bandwidth: 10 MHz
- Security: WPA3-SAE
- Mesh interface: radio0
- Operating distance: 2000 m
- Bench TX power: 16 dBm; field use calls for explicit maximum
- Roster #8 laptop: `10.223.58.10/16`
- Suggested wearable management address: `10.223.196.108/16`
- Suggested Mini management address: `10.223.196.148/16`
- Mesh password is blank in the guide. User contacted Josh for it. Do not configure the mesh until it is supplied.

The Mini label IP (`10.223.79.19`) differs from the guide's suggested future address (`10.223.196.148`). Treat `10.223.79.19` as the current/factory management address until verified.

## Confirmed working state

The Pi boots normally with a monitor and keyboard, and the user can log in locally as `ebach`.

The Pi joins `RoboticsLan`, receives `192.168.40.193`, and can ping gateway `192.168.40.1`.

## RoboticsLan obstacle

The Pi and laptop are associated with the same access point and share the same `/23`, but cannot communicate directly:

- Pi cannot ping laptop `192.168.40.119`.
- Laptop cannot ping, ARP, or SSH to Pi `192.168.40.193`.
- Both can reach the gateway.

This strongly indicates wireless client isolation on `RoboticsLan`, not a bad Pi address or SSH problem.

## Windows Mobile Hotspot attempt

The Pi sees `RN081` with excellent signal and authenticates successfully, but Windows Internet Connection Sharing does not provide DHCP or pass local traffic.

Pi NetworkManager profiles:

- `RoboticsLan`: `7101db60-9667-415c-8981-2769b5b19b51`
- `RN081`: `b1824e6e-f938-48cc-8d73-c24af4a369cb`
- `RN081-static`: `658e9e45-6386-4294-a286-f04a418b8d44`

The static profile used `192.168.137.2/24`, gateway/DNS `192.168.137.1`, and IPv6 disabled. It associated with hotspot BSSID `F6:4E:B4:DD:65:91`, but the Pi could not ping `192.168.137.1`. Windows showed neighbor `192.168.137.2` as unreachable with an all-zero MAC and could not ping or SSH to it.

Windows services `SharedAccess`, `WlanSvc`, and `Dhcp` were running. `SharedAccess` was restarted with elevation, which temporarily turned the hotspot off. The user turned it back on.

A final clean DHCP retry was made:

```bash
sudo nmcli --ask con up uuid b1824e6e-f938-48cc-8d73-c24af4a369cb
```

It failed again with:

```text
Connection activation failed: IP configuration could not be reserved
(no available address, timeout, etc.)
```

The Pi fell back to `RoboticsLan` at `192.168.40.193`. At handover, the active connections were `RoboticsLan` on `wlan0` and loopback.

Conclusion: do not keep retrying the same hotspot setup unless repairing/resetting Windows ICS itself. Authentication works; DHCP and even local layer-2 traffic are failing.

## Pi boot/media observations

- SD card approximately 59.48 GB, MBR signature `741173c8`.
- Boot root `PARTUUID=741173c8-02` matches the disk.
- Boot filesystem was clean.
- Configuration contains `otg_mode=1` and `dtoverlay=dwc2,dr_mode=host`.

The Pi USB port is intentionally in host mode, presumably for the Mini. It is not configured as a USB Ethernet gadget to the laptop.

## Highest-value next step

Use the Pi's local keyboard/monitor to determine whether the powered Mini enumerates as USB and creates a network interface. This has not yet been tested and is the most direct path to the Mini.

Run on the Pi with the Mini powered and connected:

```bash
lsusb
ip -br link
ip -br addr
nmcli device status
sudo dmesg --ctime | tail -n 80
```

Look for a USB Ethernet interface such as `usb0`, `eth0`, or `enx...`, and USB/RNDIS/CDC-Ethernet messages.

If a USB Ethernet interface exists but lacks a useful IPv4 address, temporarily place it in the Mini label-IP subnet. Replace `INTERFACE` with the actual name:

```bash
sudo ip addr add 10.223.79.20/16 dev INTERFACE
sudo ip link set INTERFACE up
ping -c 3 10.223.79.19
```

Then test the likely web service locally from the Pi:

```bash
curl -I --connect-timeout 5 http://10.223.79.19/
curl -k -I --connect-timeout 5 https://10.223.79.19/
```

Do not make the temporary address persistent until the interface and connectivity are confirmed.

If no USB Ethernet interface appears:

1. Compare `lsusb` and `dmesg` with the Mini disconnected and connected/powered.
2. Verify the cable supports data and is connected to the correct Mini data port.
3. Verify whether this Mini model exposes management over USB; it may require wired Ethernet pins/an adapter.
4. Check power stability; a device that repeatedly resets may never enumerate.

## Better ways to regain remote SSH access

1. Put the laptop and Pi on a personal phone hotspot that permits peer-to-peer clients. Find the Pi in the phone's client list and SSH to it.
2. Use a travel router or ordinary router with client isolation disabled.
3. Connect a supported USB Ethernet adapter to the Pi through an OTG hub and wire it to the laptop with compatible static addresses.
4. Repair/reset Windows Mobile Hotspot/ICS only if desired; it is not required for local Mini diagnostics.

Once peer-to-peer networking works:

```powershell
ssh -i C:\Users\ebach\.ssh\id_ed25519_rpi ebach@PI_ADDRESS
```

## Separate wearable-radio context

This is not the current device but may matter later:

- MAC: `00:30:1A:3C:C4:82`
- Label/current management IP: `10.223.196.130`
- Model: `RM-1700-22W3`
- Reachable through USB Ethernet at `192.168.153.1` when laptop was on `192.168.153.10/24`
- Hostname: `smartradio-301a3cc482`
- Firmware: `firmware-2024-10.5`
- Observed settings: channel 12 (915 MHz), 10 MHz, mesh ID `0105`, WPA2 `psk2+ccmp`, placeholder key `123hackme`, radio0, TX 32 dBm
- No changes applied because the correct mesh password is unknown.

## Change and safety record

- No mesh changes made to either Doodle Labs radio.
- No firmware flashed.
- No intentional Pi file changes beyond NetworkManager Wi-Fi profiles.
- Temporary Windows addresses from wearable work may remain on a disconnected adapter (`192.168.153.2/24` and `10.223.196.200/16`). They do not explain the Wi-Fi isolation or hotspot failure.
