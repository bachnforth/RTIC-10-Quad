import math, os, requests
from PIL import Image
H={"User-Agent":"quad-range-test-planner/1.0 (personal hobby flight planning)"}
URL="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
def deg2tile(lat,lon,z):
    n=2**z; x=(lon+180)/360*n
    y=(1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*n
    return x,y
def tile2deg(x,y,z):
    n=2**z; lon=x/n*360-180
    lat=math.degrees(math.atan(math.sinh(math.pi*(1-2*y/n)))); return lat,lon
def get_tile(z,x,y):
    os.makedirs("tilecache",exist_ok=True)
    p=f"tilecache/{z}_{x}_{y}.jpg"
    if not os.path.exists(p):
        r=requests.get(URL.format(z=z,x=x,y=y),headers=H,timeout=30); r.raise_for_status()
        open(p,"wb").write(r.content)
    return Image.open(p).convert("RGB")
def mosaic(lat0,lon0,lat1,lon1,z):
    """lat0/lon0 = south-west, lat1/lon1 = north-east. returns (img, (north,west,south,east) of img, fx, fy)"""
    x0,y1=deg2tile(lat0,lon0,z); x1,y0=deg2tile(lat1,lon1,z)
    tx0,tx1,ty0,ty1=int(x0),int(x1),int(y0),int(y1)
    img=Image.new("RGB",((tx1-tx0+1)*256,(ty1-ty0+1)*256))
    for tx in range(tx0,tx1+1):
        for ty in range(ty0,ty1+1):
            img.paste(get_tile(z,tx,ty),((tx-tx0)*256,(ty-ty0)*256))
    return img,(tx0,ty0,z)
def latlon_to_px(lat,lon,meta):
    tx0,ty0,z=meta; x,y=deg2tile(lat,lon,z); return (x-tx0)*256,(y-ty0)*256
