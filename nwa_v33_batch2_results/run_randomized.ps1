$ErrorActionPreference='Stop'
$Root='C:\Users\ebach\Documents\ChatGPT\10 inch Quad\nwa_v33_batch2_results'
$Sitl='C:\Users\ebach\Documents\Mission Planner\sitl'
$Python='C:\Users\ebach\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$env:PYTHONPATH='C:\Users\ebach\Documents\ChatGPT\10 inch Quad\.codex_tmp\nwa_py'
$Expected='F2A704BA02A26E93F01B782D05715BF94BEF937A828B5B58F21B9E3023F6A997'
$Source=Join-Path $Root 'nearest_waypoint_ahead_v3_3_TESTED_UNCHANGED.lua'
$Installed=Join-Path $Sitl 'scripts\nearest_waypoint_ahead.lua'
if((Get-FileHash $Source -Algorithm SHA256).Hash -ne $Expected){throw 'source hash mismatch'}
Copy-Item $Source $Installed -Force
$Out=Join-Path $Root 'events\randomized_campaign';New-Item -ItemType Directory -Force $Out|Out-Null
$started=Get-Date
$args=@('-M+','-O35.0495395,-79.4901843,100.446743268355,0','-s5','--serial0','tcp:0','--defaults',('"'+(Join-Path $Sitl 'default_params\copter.parm')+'"'))
$p=Start-Process (Join-Path $Sitl 'ArduCopter.exe') -ArgumentList $args -WorkingDirectory $Sitl -WindowStyle Hidden -RedirectStandardOutput (Join-Path $Out 'sitl_stdout.txt') -RedirectStandardError (Join-Path $Out 'sitl_stderr.txt') -PassThru
Start-Sleep -Milliseconds 1000
try{& $Python (Join-Path $Root 'random_geometry_runner.py') $Out *>&1|Tee-Object (Join-Path $Out 'runner_output.txt');$code=$LASTEXITCODE}
finally{if(-not $p.HasExited){Stop-Process -Id $p.Id};$p.WaitForExit();Start-Sleep -Milliseconds 500}
$bin=Get-ChildItem (Join-Path $Sitl 'logs') -Filter '*.BIN'|Where-Object{$_.LastWriteTime -ge $started.AddSeconds(-2)}|Sort-Object LastWriteTime -Descending|Select-Object -First 1
if($bin){Copy-Item $bin.FullName (Join-Path $Out 'randomized_campaign.BIN') -Force;Copy-Item $bin.FullName (Join-Path $Root 'logs\randomized_campaign.BIN') -Force}
if((Get-FileHash $Source -Algorithm SHA256).Hash -ne $Expected -or (Get-FileHash $Installed -Algorithm SHA256).Hash -ne $Expected){throw 'final hash mismatch'}
exit $code
