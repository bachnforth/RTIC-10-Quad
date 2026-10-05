import requests, json, time, sys
H={"User-Agent":"quad-range-test-planner/1.0 (personal hobby flight planning)","Accept":"application/json"}
BB="(33.715,-85.930,33.755,-85.885)"
queries={
 "roads":f'[out:json][timeout:40];way["highway"]{BB};out geom tags;',
 "hazards":f'[out:json][timeout:40];(way["power"~"line|minor_line"]{BB};node["power"="tower"]{BB};node["man_made"~"tower|mast"]{BB};way["natural"="water"]{BB};way["waterway"]{BB};);out geom tags;',
 "buildings":f'[out:json][timeout:40];way["building"]{BB};out center tags;',
}
urls=["https://overpass-api.de/api/interpreter","https://overpass.private.coffee/api/interpreter","https://overpass.kumi.systems/api/interpreter"]
for name,q in queries.items():
    for attempt in range(6):
        u=urls[attempt%len(urls)]
        try:
            r=requests.post(u,data={"data":q},headers=H,timeout=60); r.raise_for_status()
            json.dump(r.json(),open(f"osm_{name}.json","w")); print(name,u,len(r.json()["elements"])); break
        except Exception as e:
            print(name,u,str(e)[:80]); time.sleep(5)
