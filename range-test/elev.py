import json, os, requests, time
CACHE="elev_cache.json"
_c=json.load(open(CACHE)) if os.path.exists(CACHE) else {}
H={"User-Agent":"quad-range-test-planner/1.0"}
def elevation(lat,lon):
    k=f"{lat:.6f},{lon:.6f}"
    if k in _c: return _c[k]
    for t in range(5):
        try:
            r=requests.get("https://epqs.nationalmap.gov/v1/json",params=dict(x=lon,y=lat,units="Meters",wkid=4326,includeDate="false"),headers=H,timeout=30)
            v=float(r.json()["value"]); _c[k]=v; json.dump(_c,open(CACHE,"w")); return v
        except Exception as e:
            time.sleep(2)
    raise RuntimeError("EPQS failed "+k)
