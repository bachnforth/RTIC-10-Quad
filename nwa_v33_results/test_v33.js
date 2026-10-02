const fs = require('fs');
const {lua, lauxlib, lualib, to_luastring, to_jsstring} = require('../.codex_tmp/nwa_check/node_modules/fengari');
const source = fs.readFileSync(__dirname + '/nearest_waypoint_ahead_v3_3.lua', 'utf8');

function run(name, setup, actions) {
  const base = String.raw`
msgs={}; mode=5; mode_calls={}; speed_calls={}; speed_ok=true; mode_ok=true;
mode_lands=true; armed=true; flying=true; healthy=true; switch=0; target=nil;
fail_zero=false; race_on_speed=false;
lat0=400000000; lon0=-740000000; aircraft_lat=lat0+13500; aircraft_lon=lon0;
params={MIS_RESTART=0,WP_SPD=6,NWA_START=4,NWA_END=5};
param={add_table=function() return true end,
 add_param=function(self,k,i,n,d) if params['NWA_'..n]==nil then params['NWA_'..n]=d end return true end,
 get=function(self,n) return params[n] end};
function Parameter() local n return {init=function(self,x)n=x return true end,get=function()return params[n]end} end
rc={get_aux_cached=function() return switch end};
gcs={send_text=function(self,l,m)table.insert(msgs,m)end,frame_type=function()return 2 end};
arming={is_armed=function()return armed end};
ahrs={healthy=function()return healthy end,get_position=function()return {lat=function()return aircraft_lat end,lng=function()return aircraft_lon end}end};
items={
 [1]={id=22,x=lat0,y=lon0},
 [2]={id=16,x=lat0,y=lon0},
 [3]={id=178,p1=1,p2=5,p3=0,p4=0},
 [4]={id=16,x=lat0+9000,y=lon0},
 [5]={id=16,x=lat0+18000,y=lon0},
 [6]={id=20,x=0,y=0}
};
mission_state=0; current_index=0; set_calls={}; current_id=0;
function item_object(v)
 return {command=function()return v.id end,x=function()return v.x end,y=function()return v.y end,
 param1=function()return v.p1 end,param2=function()return v.p2 end,
 param3=function()return v.p3 end,param4=function()return v.p4 end}
end
mission={num_commands=function()return 7 end,
 get_item=function(self,i)local v=items[i];if not v then return nil end;return item_object(v) end,
 state=function()return mission_state end,get_current_nav_index=function()return current_index end,
 get_current_nav_id=function()return current_id end,
 set_current_cmd=function(self,i)
   table.insert(set_calls,i)
   if i==0 then
     if fail_zero then return false end
     current_index=1; current_id=items[1].id
   else
     current_index=i; current_id=items[i] and items[i].id or 0
   end
   return true
 end};
vehicle={get_mode=function()return mode end,get_likely_flying=function()return flying end,
 get_target_location=function()return target end,
 set_mode=function(self,n)
   table.insert(mode_calls,n)
   if not mode_ok then return false end
   if mode_lands then mode=n end
   if n~=3 then mission_state=0 end
   return true
 end,
 set_desired_speed=function(self,s)
   table.insert(speed_calls,s)
   if race_on_speed then current_index=6;current_id=20 end
   return speed_ok
 end};
`;
  const L = lauxlib.luaL_newstate(); lualib.luaL_openlibs(L);
  const program = `${base}\n${setup || ''}\nlocal update=(function() ${source} end)()\n${actions}`;
  const status = lauxlib.luaL_dostring(L, to_luastring(program));
  if (status !== lua.LUA_OK) throw new Error(name + ': ' + to_jsstring(lua.lua_tostring(L, -1)));
  console.log(name + ': PASS');
}

const trigger = `switch=2;update();`;
const activate = `mission_state=1;target={};current_index=5;current_id=16;`;

run('setter waits for second observation', '', `${trigger}${activate}update();assert(#speed_calls==0);update();assert(#speed_calls==1 and speed_calls[1]==5);`);
run('setter exactly once', '', `${trigger}${activate}update();update();for i=1,5 do update() end;assert(#speed_calls==1);`);
run('predicate loss between observations', '', `${trigger}${activate}update();target=nil;update();assert(#speed_calls==0 and mode==5);`);
run('post-set NAV race detected without retry', 'race_on_speed=true', `${trigger}${activate}update();update();update();assert(#speed_calls==1 and mode==5);`);
run('external LOITER wins', '', `${trigger}${activate}update();mode=5;mission_state=0;update();assert(mode==5 and #speed_calls==0);`);
run('external RTL wins', '', `${trigger}${activate}update();mode=6;mission_state=0;update();assert(mode==6 and #speed_calls==0);`);
run('flying loss no rollback', '', `${trigger}${activate}update();flying=false;update();assert(mode==3 and #speed_calls==0);`);
run('disarm no rollback', '', `${trigger}${activate}update();armed=false;update();assert(mode==3 and #speed_calls==0);`);
run('nonzero rollback', 'current_index=2;current_id=16', `${trigger}${activate}update();current_index=6;current_id=20;update();assert(mode==5 and set_calls[#set_calls]==2 and current_index==2);`);
run('zero normalized before staging', '', `${trigger}assert(set_calls[1]==0 and set_calls[2]==5 and #mode_calls==1);assert(params.NWA_MINREM==30);`);
run('normalized rollback returns first NAV', '', `${trigger}${activate}update();current_index=6;current_id=20;update();assert(mode==5 and set_calls[#set_calls]==1 and current_index==1);`);
run('normalization failure aborts before AUTO', 'fail_zero=true', `${trigger}assert(#set_calls==1 and set_calls[1]==0 and #mode_calls==0 and #speed_calls==0);`);
run('direct AUTO does not select or set speed', 'mode=3', `update();switch=2;update();assert(#set_calls==0 and #speed_calls==0);`);
run('native later behavior not suppressed', '', `${trigger}${activate}update();update();current_index=6;current_id=20;for i=1,5 do update() end;assert(#speed_calls==1);`);
