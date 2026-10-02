# Initial autonomous-test fence and speed

This patch adds conservative containment for the first outdoor waypoint test.

## Changes

- Enable the geofence.
- Use only maximum-altitude and Home-centered circular fences (`FENCE_TYPE=3`); do not depend on an unloaded polygon fence.
- Maximum altitude: 20 m above Home.
- Radius: 50 m around Home.
- Margin: 5 m.
- Reduce autonomous waypoint speed from 10 m/s to 3 m/s.

## Existing RTL configuration retained

- `RTL_ALT_M=15`: return at 15 m, subject to RTL cone behavior.
- `RTL_ALT_FINAL_M=0`: land after returning.
- `RTL_LOIT_TIME=5000`: pause for five seconds over Home before descent.
- `RTL_CONE_SLOPE=3`: enabled.
- `RTL_SPEED_MS=0`: use waypoint speed, which this patch sets to 3 m/s.
- `FENCE_ACTION=1`: attempt RTL, falling back to Land if RTL is unavailable.
- `AUTO_OPTIONS=0`: no arming in Auto and no automatic mission takeoff merely from selecting Auto.

## Expected indoor behavior

After enabling the fence, the vehicle may show a GPS-related PreArm warning indoors. That is expected. Do not disable GPS, EKF, fence, or arming checks to remove it.

Use **Compare Params**, select this file, and confirm exactly six differences before continuing. Keep the propellers removed and do not arm.
