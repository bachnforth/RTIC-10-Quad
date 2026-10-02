# Initial 5 m waypoint test

Planning Home: `35.04901493, -79.48968350`, 103.72 m ASL.

Mission:

1. Take off vertically to 5 m above Home.
2. Fly 5 m north and hold for 2 seconds.
3. Fly 5 m east and hold for 2 seconds.
4. Fly 5 m south and hold for 2 seconds, ending 5 m east of Home.
5. Execute RTL. Existing RTL configuration may climb before returning, pauses 5 seconds over Home, and then lands.

The maximum horizontal distance from planning Home is approximately 7.1 m, well inside the configured 50 m fence. The mission uses relative altitudes for all airborne navigation commands.

## Load and inspect only

1. In Mission Planner **PLAN**, select **Load File**.
2. Choose `initial_5m_waypoint_test.waypoints`.
3. Confirm the visible route stays entirely inside the verified open clearing.
4. Confirm the command table contains TAKEOFF, three WAYPOINT commands at 5 m, then RTL.
5. Save a local copy if desired.

Do not select **Write** until the planned route and real-world obstacle clearance have been reviewed. Loading the file changes only the Mission Planner workspace; **Write** uploads it to the aircraft.
