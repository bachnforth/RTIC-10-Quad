$ErrorActionPreference = 'Stop'
$Root = 'C:\Users\ebach\Documents\ChatGPT\10 inch Quad\nwa_v33_batch2_results'
$Sitl = 'C:\Users\ebach\Documents\Mission Planner\sitl'
$Exe = Join-Path $Sitl 'ArduCopter.exe'
$Defaults = Join-Path $Sitl 'default_params\copter.parm'
$Python = 'C:\Users\ebach\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$env:PYTHONPATH = 'C:\Users\ebach\Documents\ChatGPT\10 inch Quad\.codex_tmp\nwa_py'
$Runner = Join-Path $Root 'batch2_case_runner.py'
$LogDir = Join-Path $Sitl 'logs'
$ScriptSource = Join-Path $Root 'nearest_waypoint_ahead_v3_3_TESTED_UNCHANGED.lua'
$ScriptInstalled = Join-Path $Sitl 'scripts\nearest_waypoint_ahead.lua'
$ExpectedHash = 'F2A704BA02A26E93F01B782D05715BF94BEF937A828B5B58F21B9E3023F6A997'

if ((Get-FileHash $ScriptSource -Algorithm SHA256).Hash -ne $ExpectedHash) { throw 'Frozen source hash mismatch' }
Copy-Item $ScriptSource $ScriptInstalled -Force
if ((Get-FileHash $ScriptInstalled -Algorithm SHA256).Hash -ne $ExpectedHash) { throw 'Installed script hash mismatch' }

$allCases = @(
'01_mid_leg','02_leg_begin','03_beyond_destination','04_before_start','05_maxdist_inside','06_maxdist_outside',
'07_minrem_above','08_minrem_below','09_short_leg','10_ambiguous_parallel','11_intersecting',
'12_takeoff_waypoints','13_final_rtl','14_final_land','15_multiple_speed','16_speed_zero','17_speed_type0','18_speed_type1',
'19_vertical_type2','20_vertical_type3','21a_do_jump','21b_condition','22_malformed',
'23_disabled','24_enabled','25_once','26_rearm','27_high_no_edge','28_edges_pending','29_mis_restart',
'30a_maxdist_zero','30b_maxdist_1000','30c_maxdist_1001','31a_minleg_one','31b_minleg_100','31c_minleg_101',
'32a_minrem_five','32b_minrem_500','32c_minrem_501','33a_enable_invalid','33b_ambig_invalid','33c_maxdist_negative',
'35_loiter_wait_init','36_loiter_wait_stable','37_rtl_pending','38_disarm_pending','40_nav_advance',
'42_direct_after_success','43_arm_cycles','44_index_zero','45_index_nonzero')
$cases = if ($args.Count -gt 0) { @($args) } else { $allCases }
$runRows = @()
foreach ($case in $cases) {
    $out = Join-Path $Root ('events\' + $case)
    New-Item -ItemType Directory -Force $out | Out-Null
    $stdout = Join-Path $out 'sitl_stdout.txt'; $stderr = Join-Path $out 'sitl_stderr.txt'; $runnerOut=Join-Path $out 'runner_output.txt'
    $started=Get-Date
    $speed = if ($case -in @('28_edges_pending','35_loiter_wait_init','36_loiter_wait_stable','37_rtl_pending','38_disarm_pending','40_nav_advance','44_index_zero','45_index_nonzero')) { 1 } else { 5 }
    $arguments=@('-M+','-O35.0495395,-79.4901843,100.446743268355,0',("-s$speed"),'--serial0','tcp:0','--defaults',('"'+$Defaults+'"'))
    $p=Start-Process $Exe -ArgumentList $arguments -WorkingDirectory $Sitl -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    $startupWait = if ($speed -eq 1) { 2500 } else { 800 }
    Start-Sleep -Milliseconds $startupWait
    $exit=999
    try { & $Python $Runner $case $out *>&1 | Tee-Object $runnerOut; $exit=$LASTEXITCODE }
    finally { if (-not $p.HasExited) { Stop-Process -Id $p.Id }; $p.WaitForExit(); Start-Sleep -Milliseconds 500 }
    $bin=Get-ChildItem $LogDir -Filter '*.BIN' | Where-Object {$_.LastWriteTime -ge $started.AddSeconds(-2)} | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($bin) { Copy-Item $bin.FullName (Join-Path $out ($case+'.BIN')) -Force }
    $missionFile = Join-Path $out 'mission.waypoints'
    if (Test-Path -LiteralPath $missionFile) { Copy-Item $missionFile (Join-Path $Root ('missions\'+$case+'.waypoints')) -Force }
    $runRows += [pscustomobject]@{Case=$case;Exit=$exit;BinBytes=if($bin){$bin.Length}else{0}}
}
$runRows | Export-Csv (Join-Path $Root 'deterministic_run_summary.csv') -NoTypeInformation
if ((Get-FileHash $ScriptSource -Algorithm SHA256).Hash -ne $ExpectedHash -or (Get-FileHash $ScriptInstalled -Algorithm SHA256).Hash -ne $ExpectedHash) { throw 'Final Lua hash mismatch' }
$runRows | Format-Table -AutoSize
