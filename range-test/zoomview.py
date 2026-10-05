import json, sys
from tiles import *
from PIL import ImageDraw
L=(33.7238114,-85.9064364)
def crop(name,lat0,lon0,lat1,lon1,z=17,roads=True):
    img,meta=mosaic(lat0,lon0,lat1,lon1,z)
    # crop to exact bbox
    xa,ya=latlon_to_px(lat1,lon0,meta); xb,yb=latlon_to_px(lat0,lon1,meta)
    d=ImageDraw.Draw(img)
    if roads:
        for e in json.load(open("osm_roads.json"))["elements"]:
            pts=[latlon_to_px(g["lat"],g["lon"],meta) for g in e["geometry"]]
            d.line(pts,fill=(255,255,0),width=1)
    x,y=latlon_to_px(*L,meta); d.ellipse([x-6,y-6,x+6,y+6],outline=(0,255,0),width=2)
    img.crop((int(xa),int(ya),int(xb),int(yb))).save(name)
if __name__=="__main__":
    a=[float(v) for v in sys.argv[2:6]]; crop(sys.argv[1],*a)
