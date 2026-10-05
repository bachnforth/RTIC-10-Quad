import json
from tiles import *
from PIL import ImageDraw
d=json.load(open("route_draft.json")); L=(33.7238114,-85.9064364)
img,meta=mosaic(33.7225,-85.9150,33.7390,-85.9020,17)
dr=ImageDraw.Draw(img)
for e in json.load(open("osm_roads.json"))["elements"]:
    dr.line([latlon_to_px(g["lat"],g["lon"],meta) for g in e["geometry"]],fill=(255,255,0),width=1)
dr.line([latlon_to_px(*p,meta) for p in d["path"]],fill=(255,0,255),width=2)
for i,w in enumerate(d["wps"]):
    x,y=latlon_to_px(*w,meta); dr.ellipse([x-5,y-5,x+5,y+5],outline=(0,255,255),width=2); dr.text((x+8,y-6),str(i),fill=(255,255,255))
xa,ya=latlon_to_px(33.7390,-85.9150,meta); xb,yb=latlon_to_px(33.7225,-85.9020,meta)
img.crop((int(xa),int(ya),int(xb),int(yb))).save("draft_route.png")
