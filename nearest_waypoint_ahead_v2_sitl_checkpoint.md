# ArduCopter 4.7.1 SITL integration checkpoint

**Status: NOT RUN.** No real ArduCopter mission-engine, Lua, AUTO, speed, or BIN-log result exists yet. The V2 Lua file was not changed during this attempt. The earlier 27 tests remain **MOCK-ONLY**.

The official Linux SITL binary for `Copter-4.7.1` was downloaded to `.codex_tmp/nwa_sitl_arducopter_4.7.1` (7,231,384 bytes). The official version record identifies commit `dbe792162d06cab66c3475fd5556bf7a120f119e` and ArduCopter V4.7.1. Host Python has `pymavlink` and `paramiko` in `.codex_tmp/nwa_py`.

An isolated VirtualBox Debian installer VM named `nwa-copter-471-sitl` stalled while retrieving `partman-iscsi`, before writing a usable disk. An isolated full clone of the existing Debian VM was created as `nwa-sitl-clone`; the original VM was not modified. The clone booted Debian 13 and advertised OpenSSH 10.0 on host port 22223, but guest credentials were unavailable. Work stopped at this safe checkpoint because the user reported imminent computer power loss. Both isolated VMs are powered off.

Next step: gain authorized shell access to `nwa-sitl-clone` (for example, reset a password on the *clone* through its boot recovery mode), transfer the official SITL binary and V2 script, launch Copter, run the specified mission through MAVLink, and collect console, STATUSTEXT, mission/mode transitions, and `.BIN` evidence. Do not treat this checkpoint as an integration pass.
