import sys, time
from pymavlink import mavutil
log_id, size, out = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
m = mavutil.mavlink_connection("COM9", baud=115200)
m.wait_heartbeat(timeout=15)
data = bytearray(size)
got = set()
CH = 90
def req(ofs, cnt):
    m.mav.log_request_data_send(m.target_system, m.target_component, log_id, ofs, cnt)
req(0, 0xFFFFFFFF)
last = time.time(); t0 = time.time()
while len(got) * CH < size and time.time() - t0 < 1500:
    x = m.recv_match(type="LOG_DATA", blocking=True, timeout=1)
    if x is None:
        if time.time() - last > 2:
            # re-request first missing chunk
            miss = next((o for o in range(0, size, CH) if o not in got), None)
            if miss is None: break
            req(miss, min(0xFFFFFFFF, size - miss)); last = time.time()
        continue
    if x.id != log_id: continue
    d = bytes(x.data[:x.count]); data[x.ofs:x.ofs+x.count] = d; got.add(x.ofs); last = time.time()
m.mav.log_request_end_send(m.target_system, m.target_component)
miss = sum(1 for o in range(0, size, CH) if o not in got)
open(out, "wb").write(data)
print("log", log_id, "bytes", size, "missing chunks", miss, "seconds", round(time.time()-t0))
