import csv, json, math, os, sys, time
from datetime import datetime, timezone
from pymavlink import mavutil

OUT = os.path.dirname(os.path.abspath(__file__))
events=[]; samples=[]
latest_boot=None; last_seq=None

def utcnow(): return datetime.now(timezone.utc).isoformat(timespec='milliseconds')
def event(kind, text, **kw):
    row={'utc':utcnow(),'boot_ms':latest_boot,'kind':kind,'text':text,**kw}
    events.append(row); print(json.dumps(row),flush=True)

m=mavutil.mavlink_connection('tcp:127.0.0.1:5762',source_system=250)
h=m.wait_heartbeat(timeout=10)
if not h: raise RuntimeError('no heartbeat')
event('heartbeat','connected',mode=h.custom_mode,base_mode=h.base_mode)

def recv(timeout=.1):
    global latest_boot,last_seq
    x=m.recv_match(blocking=True,timeout=timeout)
    if not x: return None
    d=x.to_dict(); typ=x.get_type()
    if 'time_boot_ms' in d: latest_boot=d['time_boot_ms']
    if typ=='STATUSTEXT': event('STATUSTEXT',x.text,severity=x.severity)
    elif typ=='MISSION_CURRENT':
        if x.seq != last_seq:
            last_seq=x.seq; event('MISSION_CURRENT',f'seq {x.seq}',seq=x.seq)
    elif typ=='COMMAND_ACK': event('COMMAND_ACK',f'cmd {x.command} result {x.result}',command=x.command,result=x.result)
    elif typ in ('GLOBAL_POSITION_INT','LOCAL_POSITION_NED'):
        if typ=='GLOBAL_POSITION_INT':
            vx=x.vx*.01; vy=x.vy*.01; rel_alt=x.relative_alt*.001
        else:
            vx=x.vx; vy=x.vy; rel_alt=-x.z
        samples.append({'utc':utcnow(),'boot_ms':latest_boot,'type':typ,'seq':last_seq,'vx_mps':vx,'vy_mps':vy,'hvel_mps':math.hypot(vx,vy),'rel_alt_m':rel_alt})
    return x

def wait_type(types,timeout,condition=lambda x:True):
    end=time.time()+timeout
    while time.time()<end:
        x=recv(.2)
        if x and x.get_type() in types and condition(x): return x
    return None

def set_param(name,value):
    m.mav.param_set_send(m.target_system,m.target_component,name.encode(),float(value),mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
    x=wait_type({'PARAM_VALUE'},4,lambda q:q.param_id==name)
    if not x or abs(x.param_value-value)>.01: raise RuntimeError(f'param {name} failed: {x}')
    event('PARAM',f'{name}={x.param_value}',name=name,value=x.param_value)

for name,value in [('SCR_ENABLE',1),('MIS_RESTART',0),('RC7_OPTION',300),('WP_SPD',6),('NWA_ENABLE',1),('NWA_MAXDIST',100),('NWA_MINREM',20),('NWA_DEBUG',1),('NWA_ONCE',1)]: set_param(name,value)

# Corrected QGC mission including ArduPilot's sequence-zero HOME.
mission=[
 (0,0,16,0,0,0,0,35.0495415,-79.490181,100.44,1),
 (1,3,22,0,0,0,0,35.0495415,-79.490181,20,0),
 (2,3,16,0,0,0,0,35.049,-79.492,20,0),
 (3,3,178,1,8,-1,0,0,0,0,0),
 (4,3,16,0,0,0,0,35.049,-79.49013,20,0),
 (5,3,178,1,5,-1,0,0,0,0,0),
 (6,3,16,0,0,0,0,35.05,-79.49015,20,0),
 (7,3,178,1,10,-1,0,0,0,0,0),
 (8,3,16,0,0,0,0,35.0620741,-79.491148,20,0),
 (9,3,20,0,0,0,0,0,0,0,0),
]
m.mav.mission_clear_all_send(m.target_system,m.target_component)
wait_type({'MISSION_ACK'},3)
m.mav.mission_count_send(m.target_system,m.target_component,len(mission))
sent=set(); end=time.time()+20
while time.time()<end:
    x=recv(.5)
    if not x: continue
    if x.get_type() in ('MISSION_REQUEST','MISSION_REQUEST_INT'):
        seq=x.seq
        if seq>=len(mission): raise RuntimeError('bad request '+str(seq))
        _,frame,cmd,p1,p2,p3,p4,lat,lon,alt,current=mission[seq]
        m.mav.mission_item_int_send(m.target_system,m.target_component,seq,frame,cmd,current,1,p1,p2,p3,p4,int(round(lat*1e7)),int(round(lon*1e7)),alt)
        sent.add(seq)
    elif x.get_type()=='MISSION_ACK':
        if x.type!=mavutil.mavlink.MAV_MISSION_ACCEPTED: raise RuntimeError('upload ack '+str(x))
        break
else: raise RuntimeError('mission upload timeout')
if len(sent)!=len(mission): raise RuntimeError(f'only sent {sent}')
event('MISSION_UPLOAD','accepted',count=len(mission))

# Download and verify exact command IDs and speed values.
m.mav.mission_request_list_send(m.target_system,m.target_component)
c=wait_type({'MISSION_COUNT'},4)
if not c or c.count!=10: raise RuntimeError(f'download count {c}')
download=[]
for i in range(c.count):
    m.mav.mission_request_int_send(m.target_system,m.target_component,i)
    x=wait_type({'MISSION_ITEM_INT','MISSION_ITEM'},3,lambda q:q.seq==i)
    if not x: raise RuntimeError('download item '+str(i))
    download.append({'seq':i,'command':x.command,'param1':x.param1,'param2':x.param2,'x':x.x,'y':x.y,'z':x.z})
expected=[16,22,16,178,16,178,16,178,16,20]
if [x['command'] for x in download]!=expected: raise RuntimeError(str(download))
event('MISSION_VERIFY','commands verified',commands=expected)
with open(os.path.join(OUT,'mission_download.json'),'w') as f: json.dump(download,f,indent=2)

# Request timestamped navigation telemetry.
for msgid,hz in [(0,2),(24,2),(30,5),(32,10),(33,10),(42,5),(62,5),(74,5),(85,10),(87,10)]:
    m.mav.command_long_send(m.target_system,m.target_component,mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,0,msgid,1e6/hz,0,0,0,0,0)
    time.sleep(.03)

def set_mode(mode):
    m.set_mode_apm(mode)
    x=wait_type({'HEARTBEAT'},8,lambda q:q.custom_mode==mode)
    if not x: raise RuntimeError('mode failed '+str(mode))
    event('MODE',f'mode {mode}',mode=mode)

def rc7(pwm):
    vals=[65535]*8; vals[6]=pwm
    for _ in range(8):
        m.mav.rc_channels_override_send(m.target_system,m.target_component,*vals)
        recv(.1)
    event('RC7',str(pwm),pwm=pwm)

rc7(1000)
set_mode(4) # GUIDED
m.arducopter_arm();
if not wait_type({'HEARTBEAT'},15,lambda q:(q.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)!=0): raise RuntimeError('arm timeout')
event('ARM','armed')
m.mav.command_long_send(m.target_system,m.target_component,mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,0,0,0,0,0,0,0,20)
event('TAKEOFF','requested 20m')
end=time.time()+45; airborne=False
while time.time()<end:
    x=recv(.1)
    if x and x.get_type()=='GLOBAL_POSITION_INT' and x.relative_alt>=18000:
        airborne=True; break
if not airborne: raise RuntimeError('takeoff altitude timeout')
event('TAKEOFF','altitude reached')

# Let the vehicle settle at home, approximately mid-leg WP2(seq4)->WP3(seq6).
settle=time.time()+4
while time.time()<settle: recv(.1)
rc7(2000)
event('TRIGGER','Scripting1 HIGH')

# Capture through NAV 6 and into NAV 8 until speed has had time to settle near 10m/s.
seen6=False; seen8=False; seq8_since=None
end=time.time()+100
while time.time()<end:
    x=recv(.1)
    if last_seq==6: seen6=True
    if last_seq==8:
        if not seen8: seq8_since=time.time()
        seen8=True
    if seen8 and time.time()-seq8_since>18: break
if not seen6: raise RuntimeError('NAV 6 not observed')
if not seen8: raise RuntimeError('NAV 8 not observed')
event('CAPTURE','NAV6 and NAV8 captured')

set_mode(5) # LOITER
time.sleep(1)
m.arducopter_disarm()
if not wait_type({'HEARTBEAT'},10,lambda q:(q.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)==0): raise RuntimeError('disarm timeout')
event('ARM','disarmed')

with open(os.path.join(OUT,'events.json'),'w') as f: json.dump(events,f,indent=2)
with open(os.path.join(OUT,'telemetry.csv'),'w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=['utc','boot_ms','type','seq','vx_mps','vy_mps','hvel_mps','rel_alt_m']);w.writeheader();w.writerows(samples)
print('COMPLETE',len(samples),'samples')
