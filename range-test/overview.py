import json, sys
from tiles import *
from PIL import ImageDraw
L=(33.7238114,-85.9064364)
img,meta=mosaic(33.715,-85.925,33.752,-85.888,16)
d=ImageDraw.Draw(img)
colors={"service":(255,255,0),"residential":(255,140,0),"unclassified":(0,255,255),"track":(255,0,255),"tertiary":(255,0,0),"trunk":(255,0,0),"trunk_link":(255,0,0)}
for e in json.load(open("osm_roads.json"))["elements"]:
    h=e["tags"]["highway"]; pts=[latlon_to_px(g["lat"],g["lon"],meta) for g in e["geometry"]]
    d.line(pts,fill=colors.get(h,(255,255,255)),width=2)
for e in json.load(open("osm_hazards.json"))["elements"]:
    if e["type"]=="node":
        x,y=latlon_to_px(e["lat"],e["lon"],meta); d.ellipse([x-5,y-5,x+5,y+5],outline=(255,0,0),width=2)
x,y=latlon_to_px(*L,meta); d.ellipse([x-8,y-8,x+8,y+8],outline=(0,255,0),width=3)
# 1500 m north marker
import math
lat15=L[0]+1500/111132.0
x,y=latlon_to_px(lat15,L[1],meta); d.ellipse([x-8,y-8,x+8,y+8],outline=(255,255,255),width=3)
x0,y0=latlon_to_px(*L,meta); d.line([(x0,y0),(x,y)],fill=(0,255,0),width=1)
img.save("overview_z16.png"); print(img.size)
