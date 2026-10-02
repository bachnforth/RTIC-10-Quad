$ErrorActionPreference = 'Stop'

$Root = 'C:\Users\ebach\Documents\ChatGPT\10 inch Quad\nwa_v33_results'
$Evidence = Join-Path $Root 'sitl_evidence'
$Sitl = 'C:\Users\ebach\Documents\Mission Planner\sitl'
$Exe = Join-Path $Sitl 'ArduCopter.exe'
$Defaults = Join-Path $Sitl 'default_params\copter.parm'
$Python = 'C:\Users\ebach\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$env:PYTHONPATH = 'C:\Users\ebach\Documents\ChatGPT\10 inch Quad\.codex_tmp\nwa_py'
$Runner = Join-Path $Root 'v33_case_runner.py'
$LogDir = Join-Path $Sitl 'logs'
$ScriptSource = Join-Path $Root 'nearest_waypoint_ahead_v3_3.lua'
$ScriptInstalled = Join-Path $Sitl 'scripts\nearest_waypoint_ahead.lua'

New-Item -ItemType Directory -Force -Path $Evidence | Out-Null
$expectedHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $ScriptSource).Hash
Copy-Item -LiteralPath $ScriptSource -Destination $ScriptInstalled -Force
$installedHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $ScriptInstalled).Hash
if ($installedHash -ne $expectedHash) { throw "Installed Lua hash mismatch: $installedHash" }

$cases = if ($args.Count -gt 0) { @($args) } else {
    @('persistent_1','persistent_2','persistent_3','local','rollback0','rollback_nonzero','direct','external')
}
$summary = @()
foreach ($case in $cases) {
    $caseDir = Join-Path $Evidence $case
    New-Item -ItemType Directory -Force -Path $caseDir | Out-Null
    $stdout = Join-Path $caseDir 'sitl_stdout.txt'
    $stderr = Join-Path $caseDir 'sitl_stderr.txt'
    $runnerOut = Join-Path $caseDir 'runner_output.txt'
    $started = Get-Date
    $arguments = @('-M+','-O35.0495395,-79.4901843,100.446743268355,0','-s1','--serial0','tcp:0','--defaults',('"' + $Defaults + '"'))
    $process = Start-Process -FilePath $Exe -ArgumentList $arguments -WorkingDirectory $Sitl -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    Start-Sleep -Seconds 2
    $exitCode = 999
    try {
        & $Python $Runner $case $caseDir *>&1 | Tee-Object -FilePath $runnerOut
        $exitCode = $LASTEXITCODE
    }
    finally {
        if (-not $process.HasExited) { Stop-Process -Id $process.Id }
        $process.WaitForExit()
        Start-Sleep -Seconds 2
    }

    $bin = Get-ChildItem -LiteralPath $LogDir -File -Filter '*.BIN' |
        Where-Object { $_.LastWriteTime -ge $started.AddSeconds(-2) } |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($null -eq $bin -or $bin.Length -eq 0) { throw "No completed BIN for $case" }
    $binDestination = Join-Path $caseDir ("{0}.BIN" -f $case)
    Copy-Item -LiteralPath $bin.FullName -Destination $binDestination -Force
    $summary += [pscustomobject]@{Case=$case; RunnerExit=$exitCode; Bin=$binDestination; BinBytes=(Get-Item $binDestination).Length}
    if ($exitCode -ne 0) { Write-Warning "Case $case runner exited $exitCode; evidence preserved" }
    Start-Sleep -Seconds 1
}

$finalInstalledHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $ScriptInstalled).Hash
if ($finalInstalledHash -ne $expectedHash) { throw "Final installed Lua hash mismatch" }
$summary | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Evidence 'run_summary.json') -Encoding utf8
$summary | Format-Table -AutoSize
