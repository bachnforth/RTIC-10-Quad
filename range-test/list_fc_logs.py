import sys, time
from pymavlink import mavutil
m = mavutil.mavlink_connection("COM9", baud=115200)
hb = m.wait_heartbeat(timeout=15)
print("heartbeat from sys", m.target_system, "comp", m.target_component, "type", hb.type, "armed:", bool(hb.base_mode & 128))
m.mav.log_request_list_send(m.target_system, m.target_component, 0, 0xFFFF)
logs = {}
t0 = time.time()
while time.time() - t0 < 12:
    x = m.recv_match(type="LOG_ENTRY", blocking=True, timeout=2)
    if x is None: continue
    logs[x.id] = (x.num_logs, x.size, x.time_utc)
    if len(logs) >= x.num_logs: break
for i in sorted(logs):
    n, size, tu = logs[i]
    print(i, size, time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(tu)) if tu else "no-time")
