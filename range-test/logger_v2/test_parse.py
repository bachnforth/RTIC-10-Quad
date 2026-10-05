import re, sys
sys.path.insert(0, ".")
import mesh_logger as L
raw = open("../flight_2026-10-02/pi/mesh_raw_20261001_180344Z_e0ad6460.txt", errors="replace").read()
blocks = raw.split("@@BEGIN")[1:]
ok = [L.parse_block(b.splitlines()[1:-1]) for b in blocks[:50]]
print(ok[0]); print(ok[10])
bad = open("../flight_2026-10-02/pi/mesh_raw_20261001_175332Z_342e7a1f.txt", errors="replace").read().split("@@BEGIN")[1:]
print(L.parse_block([l for l in bad[3].splitlines()[1:]]))
n = sum(1 for b in blocks if L.parse_block(b.splitlines()[1:])["rssi_dbm"] is not None)
print("blocks with signal:", n, "of", len(blocks))
