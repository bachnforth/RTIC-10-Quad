#!/usr/bin/env python3
"""
mesh_logger.py - Record mesh-network health about once per second during a jamming test.

Runs on the drone's Raspberry Pi (the Pi is wired to the drone's Doodle Labs radio).
Writes a CSV that analyze_jamming.py reads directly.

It records three kinds of rows:

  1. One row per ping target, about every 1-2 s: packets sent / received and average
     latency, measured by pinging other mesh nodes through the radio. Needs no radio
     login, so it always works.
  2. One "radio" row per second: signal strength, noise floor, SNR and neighbor count,
     read from the radio over SSH. Optional; needs an SSH key on the radio (see README).
     If SSH fails, ping logging carries on and the failure is noted in the log.
  3. One "gcs_uplink" row every 2 s: how many MAVLink messages the safety-mavlink-filter
     received from QGC on the phone. QGC sends at least a 1 Hz heartbeat, so 0 here
     means the ground-to-drone telemetry link was cut.

It also saves the radio's raw command output to a text file, so nothing is lost if the
parser here guesses wrong about the radio's output format.

Uses only Python's standard library.

Usage (on the Pi):
    python3 mesh_logger.py --target phone=10.223.58.11 --target josh_handheld=10.223.196.126 \\
        --radio 10.223.196.130 --radio-key ~/.ssh/radio_key \\
        --filter-status /tmp/safety_mavlink_filter_status.json
"""

import argparse
import csv
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone

FIELDS = ["timestamp", "wall_time_utc", "node_id", "rssi_dbm", "snr_db", "tx_count",
          "rx_count", "neighbors", "latency_ms", "event", "noise_dbm", "best_rssi_dbm",
          "gcs_msgs_in", "mono_s",
          "tx_bitrate_mbps", "rx_bitrate_mbps", "tx_retries", "tx_failed", "rx_bytes", "tx_bytes",
          "inactive_ms", "expected_mbps", "radio_epoch", "plink",
          "fc_lat", "fc_lon", "fc_alt_m", "fc_rel_alt_m", "fc_gspeed_ms", "fc_unix_s", "fc_rows_s"]

# Shell loop run on the radio. Picks the mesh wireless interface unless one is given,
# then prints one delimited block of stats per second.
REMOTE_SCRIPT = r'''
IFARG="@IFACE@"
IF=""
while true; do
  if [ -z "$IF" ] || ! iw dev "$IF" info >/dev/null 2>&1; then
    NEW="$IFARG"
    [ -z "$NEW" ] && NEW=$(iw dev | awk '/Interface/{i=$2} /type/ && /mesh|IBSS|adhoc|ad-hoc/{print i; exit}')
    [ -z "$NEW" ] && NEW=$(iw dev | awk '/Interface/{print $2; exit}')
    if [ "$NEW" != "$IF" ]; then IF="$NEW"; echo "@@IFACE $IF"; fi
  fi
  echo "@@BEGIN $(date +%s)"
  if [ -n "$IF" ]; then
    echo "@@STA"; iw dev "$IF" station dump 2>&1
    echo "@@SURVEY"; iw dev "$IF" survey dump 2>&1
  else
    echo "@@NOIF"
  fi
  echo "@@BATN"; batctl n 2>&1
  echo "@@END"
  sleep 1
done
'''

PING_SUMMARY = re.compile(r"(\d+) packets transmitted, (\d+) (?:packets )?received")
PING_RTT = re.compile(r"= [\d.]+/([\d.]+)/")
MAC = re.compile(r"([0-9a-f]{2}:){5}[0-9a-f]{2}", re.I)

stop = threading.Event()
children = []  # ssh processes to kill on exit
got_signal = False  # set by the signal handler; Event.set() there can deadlock the main thread


class Writer:
    """Thread-safe CSV writer that flushes every row, so a power cut loses at most a moment."""

    def __init__(self, path, echo):
        self.f = open(path, "a", newline="")
        self.w = csv.DictWriter(self.f, FIELDS)
        if self.f.tell() == 0:
            self.w.writeheader()
        self.lock = threading.Lock()
        self.last_sync = 0.0
        self.echo = echo

    def row(self, t=None, **kw):
        now, mono = time.time(), time.monotonic()
        t = now if t is None else t
        kw["timestamp"] = f"{t:.3f}"
        kw["wall_time_utc"] = datetime.fromtimestamp(t, timezone.utc).strftime("%H:%M:%S")
        # Seconds since boot never jumps, so rows logged before the clock was set can be corrected later.
        kw["mono_s"] = f"{mono - (now - t):.3f}"
        with self.lock:
            if self.f.closed:  # a worker finishing after shutdown
                return
            self.w.writerow(kw)
            self.f.flush()
            if mono - self.last_sync > 2:
                os.fsync(self.f.fileno())
                self.last_sync = mono
        if self.echo:
            shown = {k: v for k, v in kw.items() if v not in ("", None) and k != "timestamp"}
            print(" ".join(f"{k}={v}" for k, v in shown.items()), flush=True)

    def close(self):
        with self.lock:
            self.f.flush()
            os.fsync(self.f.fileno())
            self.f.close()


def ping_loop(name, ip, count, out):
    """Send a short burst of pings to one mesh node, log sent/received/latency, repeat."""
    while not stop.is_set():
        t = time.time()
        try:
            p = subprocess.run(["ping", "-n", "-q", "-c", str(count), "-i", "0.2", "-W", "1", ip],
                               capture_output=True, text=True, timeout=count * 0.2 + 5)
            text = p.stdout
        except subprocess.TimeoutExpired:
            text = ""
        m = PING_SUMMARY.search(text)
        tx, rx = (int(m.group(1)), int(m.group(2))) if m else (count, 0)
        r = PING_RTT.search(text) if rx else None
        out.row(t, node_id=name, tx_count=tx, rx_count=rx,
                latency_ms=r.group(1) if r else "", event="" if m else "ping_error")
        stop.wait(max(0.0, 1.0 - (time.time() - t)))


def clock_watch_loop(out):
    """Log a 'clock_step' event whenever the Pi's clock is set, with how far it moved.

    The Pi has no clock battery, so after a boot its time is wrong until someone sets it.
    Rows before the step can be corrected by adding offset_s (or by using mono_s).
    """
    base = time.time() - time.monotonic()
    while not stop.wait(1):
        cur = time.time() - time.monotonic()
        if abs(cur - base) > 2:
            out.row(node_id="logger", event=f"clock_step offset_s={cur - base:+.3f}")
            base = cur


def trim_old_logs(out_dir, max_mb):
    """Delete the oldest logs until the folder is under max_mb.

    Goes by size and file age on disk rather than by date, because the Pi's clock can be
    wrong after a boot.
    """
    files = [os.path.join(out_dir, n) for n in os.listdir(out_dir) if n.startswith("mesh_")]
    files.sort(key=os.path.getmtime)
    total = sum(os.path.getsize(f) for f in files)
    removed = []
    while files and total > max_mb * 1024 * 1024:
        f = files.pop(0)
        total -= os.path.getsize(f)
        os.remove(f)
        removed.append(os.path.basename(f))
    return removed


def filter_status_loop(path, out):
    """Log how many messages the MAVLink filter got from QGC since the last reading.

    The filter rewrites its status file every 2 s with running totals. Messages from the
    phone are either forwarded to the flight controller ('to_fc') or blocked; both prove
    the uplink delivered them. Kept out of tx/rx so it doesn't skew the ping delivery ratio.
    """
    last_total, last_uptime = None, None
    while not stop.wait(2):
        try:
            with open(path) as f:
                st = json.load(f)
        except (OSError, ValueError) as e:
            out.row(node_id="gcs_uplink", event=f"filter_status_unreadable: {e}"[:200])
            continue
        total = st.get("counts", {}).get("to_fc", 0) + sum(st.get("blocked", {}).values())
        uptime = st.get("uptime_s")
        if last_uptime is not None and uptime == last_uptime:
            out.row(node_id="gcs_uplink", event="filter_status_stale")  # filter not updating
        elif last_total is not None and total >= last_total:
            out.row(node_id="gcs_uplink", gcs_msgs_in=total - last_total)
        else:
            out.row(node_id="gcs_uplink", event="filter_restarted")  # first reading, or counts reset
        last_total, last_uptime = total, uptime


STA_FIELDS = (("tx_retries", r"tx retries:\s*(\d+)"), ("tx_failed", r"tx failed:\s*(\d+)"),
              ("rx_bytes", r"rx bytes:\s*(\d+)"), ("tx_bytes", r"tx bytes:\s*(\d+)"),
              ("inactive_ms", r"inactive time:\s*(\d+)"),
              ("tx_bitrate_mbps", r"tx bitrate:\s*([\d.]+)"), ("rx_bitrate_mbps", r"rx bitrate:\s*([\d.]+)"),
              ("expected_mbps", r"expected throughput:\s*([\d.]+)"))


def parse_block(lines):
    """Pull signal, noise, bitrates, retries and neighbor count out of one second of the radio's output.

    With several mesh neighbors, the per-link numbers (bitrate, retries, ...) come from the neighbor
    with the strongest signal.
    """
    sec, noise, in_use = None, None, False
    bat_neighbors, bat_ok, no_if = 0, False, False
    stations = []                     # one dict per "Station ..." entry
    for ln in lines:
        s = ln.strip()
        if s in ("@@STA", "@@SURVEY", "@@BATN"):
            sec = s
            continue
        if s == "@@NOIF":
            no_if = True
            continue
        if sec == "@@STA":
            if s.startswith("Station "):
                stations.append({})
                continue
            if not stations:
                continue
            st = stations[-1]
            m = re.match(r"signal:\s*(-?\d+)", s)  # skips the separate "signal avg:" line
            if m:
                st["signal"] = int(m.group(1))
            for key, pat in STA_FIELDS:
                m2 = re.match(pat, s)
                if m2:
                    st[key] = float(m2.group(1)) if "." in m2.group(1) else int(m2.group(1))
            m3 = re.match(r"mesh plink:\s*(\S+)", s)
            if m3:
                st["plink"] = m3.group(1)
        elif sec == "@@SURVEY":
            if s.startswith("frequency:"):
                in_use = "[in use]" in s
            m = re.match(r"noise:\s*(-?\d+)", s)
            if m and in_use:
                noise = int(m.group(1))
        elif sec == "@@BATN":
            if s.lower().startswith("[b.a.t.m.a.n"):
                bat_ok = True  # header line; it contains our own MAC, so don't count it
            elif MAC.search(s):
                bat_neighbors += 1
    signals = [st["signal"] for st in stations if "signal" in st]
    rssi = round(sum(signals) / len(signals), 1) if signals else None
    best = max((st for st in stations if "signal" in st), key=lambda st: st["signal"], default={})
    out = {
        "rssi_dbm": rssi,
        "best_rssi_dbm": max(signals) if signals else None,
        "noise_dbm": noise,
        "snr_db": round(rssi - noise, 1) if rssi is not None and noise is not None else None,
        "neighbors": bat_neighbors if bat_ok else len(signals),
        "plink": "no_interface" if no_if else best.get("plink"),
    }
    for key, _ in STA_FIELDS:
        out[key] = best.get(key)
    return out


def radio_loop(host, user, key, iface, out, raw, node="radio"):
    """Keep one SSH session to the radio open, streaming stats; reconnect if it drops."""
    # The radios' SSH server only offers the old ssh-rsa key type, which modern ssh refuses.
    cmd = ["ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
           "-o", "ServerAliveInterval=2", "-o", "ServerAliveCountMax=3",
           "-o", "StrictHostKeyChecking=accept-new",
           "-o", "HostKeyAlgorithms=+ssh-rsa", "-o", "PubkeyAcceptedAlgorithms=+ssh-rsa"]
    if key:
        cmd += ["-i", os.path.expanduser(key)]
    cmd += [f"{user}@{host}", REMOTE_SCRIPT.replace("@IFACE@", iface or "")]
    while not stop.is_set():
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, bufsize=1)
        children.append(proc)
        block, last_msg, radio_epoch = None, "", ""
        for line in proc.stdout:
            if line.startswith("@@BEGIN"):
                raw.write(f"{line.rstrip()} pi={time.time():.3f}\n")
                block = []
                continue
            raw.write(line)
            if line.startswith("@@IFACE"):
                out.row(node_id=node, event="radio_iface=" + line.split(maxsplit=1)[-1].strip())
            elif line.startswith("@@END") and block is not None:
                vals = parse_block(block)
                out.row(node_id=node, radio_epoch=radio_epoch, **{k: ("" if v is None else v) for k, v in vals.items()})
                block = None
            elif block is not None:
                block.append(line)
            elif line.strip():
                last_msg = line.strip()
            if stop.is_set():
                break
        raw.flush()
        proc.terminate()
        if not stop.is_set():
            out.row(node_id=node, event=f"radio_ssh_down: {last_msg}"[:200])
            stop.wait(3)



def mav_tap_loop(port, out):
    """Listen (read-only) to the MAVLink telemetry the Pi sends toward QGC and log the drone's position and GPS time.

    This puts the drone's distance and a correct clock into the same CSV as the radio numbers, so the radio data
    can be lined up with distance even when the Pi's own clock is wrong. It never transmits anything.
    Needs the CAP_NET_RAW permission (the systemd unit grants it) and pymavlink (the Pi's ~/mavenv has it).
    """
    import socket
    import struct
    try:
        from pymavlink.dialects.v20 import common as mav2
    except ImportError:
        out.row(node_id="fc", event="mav_tap_unavailable: pymavlink not importable (run the logger with ~/mavenv/bin/python)")
        return
    try:
        sock = socket.socket(socket.AF_PACKET, socket.SOCK_DGRAM, socket.htons(0x0003))   # all protocols: ETH_P_IP misses outgoing frames on some kernels
        sock.settimeout(0.5)
    except (PermissionError, OSError) as e:
        out.row(node_id="fc", event=f"mav_tap_unavailable: {e}"[:200])
        return
    mav = mav2.MAVLink(None)
    mav.robust_parsing = True
    last = {}
    n_msgs, t_emit = 0, time.monotonic()
    while not stop.is_set():
        try:
            pkt, addr = sock.recvfrom(2048)
        except socket.timeout:
            pkt, addr = b"", (None, 0, 0)
        except OSError as e:
            out.row(node_id="fc", event=f"mav_tap_error: {e}"[:200])
            stop.wait(2)
            continue
        if addr[2] == 4 and addr[1] == 0x0800 and len(pkt) > 28 and pkt[9] == 17:      # outgoing IPv4 + UDP
            ihl = (pkt[0] & 15) * 4
            dport = struct.unpack("!H", pkt[ihl + 2:ihl + 4])[0]
            if dport == port:
                try:
                    msgs = mav.parse_buffer(pkt[ihl + 8:]) or []
                except Exception:
                    msgs = []
                for m in msgs:
                    n_msgs += 1
                    name = m.get_type()
                    if name == "GLOBAL_POSITION_INT":
                        last.update(fc_lat=m.lat / 1e7, fc_lon=m.lon / 1e7, fc_alt_m=round(m.alt / 1000, 1),
                                    fc_rel_alt_m=round(m.relative_alt / 1000, 1),
                                    fc_gspeed_ms=round((m.vx ** 2 + m.vy ** 2) ** 0.5 / 100, 2))
                    elif name == "SYSTEM_TIME" and m.time_unix_usec > 1.6e15:
                        last["fc_unix_s"] = round(m.time_unix_usec / 1e6, 3)
        if time.monotonic() - t_emit >= 1.0:
            row = dict(last)
            row["fc_rows_s"] = n_msgs
            out.row(node_id="fc", **row)
            n_msgs, t_emit = 0, time.monotonic()
            last = {k: v for k, v in last.items() if k == "fc_unix_s"}    # position must be refreshed each second


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", action="append", default=[], metavar="NAME=IP",
                    help="a mesh node to ping (repeat for several), e.g. josh=10.223.196.126")
    ap.add_argument("--count", type=int, default=5, help="pings per burst (default 5, sent 0.2 s apart)")
    ap.add_argument("--radio", metavar="IP", help="the radio's management IP, to read radio stats over SSH")
    ap.add_argument("--radio-user", default="root")
    ap.add_argument("--radio-key", metavar="FILE", help="SSH private key for the radio")
    ap.add_argument("--radio-extra", action="append", default=[], metavar="NAME=IP",
                    help="another radio to read over SSH (same user and key), logged as node radio_NAME; repeat for several")
    ap.add_argument("--radio-iface", help="wireless interface on the radio (default: auto-detect)")
    ap.add_argument("--filter-status", metavar="FILE",
                    help="safety-mavlink-filter status file, to log messages received from QGC")
    ap.add_argument("--mav-tap-port", type=int, default=0, metavar="PORT",
                    help="log drone position/GPS time seen in MAVLink sent to this UDP port (e.g. 14550); needs CAP_NET_RAW")
    ap.add_argument("--out-dir", default=os.path.expanduser("~/jam_logs"))
    ap.add_argument("--max-mb", type=float, default=500,
                    help="delete the oldest logs at startup until the folder is under this size (default 500)")
    ap.add_argument("--quiet", action="store_true", help="don't print each row")
    args = ap.parse_args()

    if not (args.target or args.radio or args.radio_extra or args.filter_status or args.mav_tap_port):
        sys.exit("Nothing to log: give at least one --target, --radio or --filter-status.")
    targets = []
    for spec in args.target:
        name, _, ip = spec.partition("=") if "=" in spec else (spec, "", spec)
        targets.append((name, ip))

    os.makedirs(args.out_dir, exist_ok=True)
    removed = trim_old_logs(args.out_dir, args.max_mb)
    try:  # unique per boot, since the clock may restart at the same wrong time
        with open("/proc/sys/kernel/random/boot_id") as f:
            boot_id = f.read().strip()[:8]
    except OSError:
        boot_id = "noboot"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ") + "_" + boot_id
    csv_path = os.path.join(args.out_dir, f"mesh_log_{stamp}.csv")
    raw_path = os.path.join(args.out_dir, f"mesh_raw_{stamp}.txt")
    out = Writer(csv_path, echo=not args.quiet)
    raw = open(raw_path, "a")

    def on_signal(*_):
        global got_signal
        got_signal = True
    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    print(f"Logging to {csv_path}", flush=True)
    print(f"Pi clock now (UTC): {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} - check this is right!", flush=True)
    out.row(node_id="logger", event=f"logger_start boot={boot_id} targets=" + ";".join(f"{n}={i}" for n, i in targets))
    if removed:
        out.row(node_id="logger", event="trimmed_old_logs " + ";".join(removed)[:200])

    threads = [threading.Thread(target=ping_loop, args=(n, ip, args.count, out), daemon=True)
               for n, ip in targets]
    threads.append(threading.Thread(target=clock_watch_loop, args=(out,), daemon=True))
    if args.radio:
        threads.append(threading.Thread(target=radio_loop, daemon=True,
                                        args=(args.radio, args.radio_user, args.radio_key,
                                              args.radio_iface, out, raw)))
    extra_raws = []
    for spec in args.radio_extra:
        name, _, ip = spec.partition("=")
        rawx = open(os.path.join(args.out_dir, f"mesh_raw_{stamp}_{name}.txt"), "a")
        extra_raws.append(rawx)
        threads.append(threading.Thread(target=radio_loop, daemon=True,
                                        args=(ip, args.radio_user, args.radio_key, None, out, rawx, f"radio_{name}")))
    if args.mav_tap_port:
        threads.append(threading.Thread(target=mav_tap_loop, args=(args.mav_tap_port, out), daemon=True))
    if args.filter_status:
        threads.append(threading.Thread(target=filter_status_loop, daemon=True,
                                        args=(args.filter_status, out)))
    for th in threads:
        th.start()

    while not got_signal:
        time.sleep(0.5)
    stop.set()

    for p in children:
        p.terminate()
    for th in threads:
        th.join(timeout=4)
    out.row(node_id="logger", event="logger_stop")
    out.close()
    raw.close()
    for rx in extra_raws:
        rx.close()
    print(f"Stopped. Log saved to {csv_path}", flush=True)


if __name__ == "__main__":
    main()
