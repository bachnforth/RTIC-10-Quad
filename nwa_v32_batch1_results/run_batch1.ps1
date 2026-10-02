$ErrorActionPreference = 'Stop'

$Root = 'C:\Users\ebach\Documents\ChatGPT\10 inch Quad\nwa_v32_batch1_results'
$Sitl = 'C:\Users\ebach\Documents\Mission Planner\sitl'
$Exe = Join-Path $Sitl 'ArduCopter.exe'
$Defaults = Join-Path $Sitl 'default_params\copter.parm'
$Python = 'C:\Users\ebach\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$env:PYTHONPATH = 'C:\Users\ebach\Documents\ChatGPT\10 inch Quad\.codex_tmp\nwa_py'
$Runner = Join-Path $Root 'batch1_case_runner.py'
$LogDir = Join-Path $Sitl 'logs'
$ScriptSource = 'C:\Users\ebach\Downloads\nearest_waypoint_ahead_v3_2.lua'
$ScriptInstalled = Join-Path $Sitl 'scripts\nearest_waypoint_ahead.lua'
$ExpectedHash = '08FB26474C79008156E6DC3085D8A5EB3E4F887FF77614AFB59CE140E539553E'

$sourceHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $ScriptSource).Hash
if ($sourceHash -ne $ExpectedHash) { throw "Source Lua hash mismatch: $sourceHash" }
Copy-Item -LiteralPath $ScriptSource -Destination $ScriptInstalled -Force
$installedHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $ScriptInstalled).Hash
if ($installedHash -ne $ExpectedHash) { throw "Installed Lua hash mismatch: $installedHash" }

$cases = if ($args.Count -gt 0) { @($args) } else { @('fallback','persistent','direct','minrem','vertical','once','external','rollback0','rollback_nonzero') }
$summary = @()
foreach ($case in $cases) {
    $caseDir = Join-Path $Root $case
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
        if (-not $process.HasExited) {
            Stop-Process -Id $process.Id
        }
        $process.WaitForExit()
        Start-Sleep -Seconds 2
    }

    $bin = Get-ChildItem -LiteralPath $LogDir -File -Filter '*.BIN' |
        Where-Object { $_.LastWriteTime -ge $started.AddSeconds(-2) } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($null -eq $bin -or $bin.Length -eq 0) { throw "No completed BIN for $case" }
    $binDestination = Join-Path $caseDir ("{0}.BIN" -f $case)
    Copy-Item -LiteralPath $bin.FullName -Destination $binDestination -Force
    $summary += [pscustomobject]@{
        Case = $case
        RunnerExit = $exitCode
        Bin = $binDestination
        BinBytes = (Get-Item -LiteralPath $binDestination).Length
    }
    if ($exitCode -ne 0) {
        Write-Warning "Case $case runner exited $exitCode; continuing to preserve and analyze evidence"
    }
    Start-Sleep -Seconds 1
}

$finalSourceHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $ScriptSource).Hash
$finalInstalledHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $ScriptInstalled).Hash
if ($finalSourceHash -ne $ExpectedHash -or $finalInstalledHash -ne $ExpectedHash) {
    throw "Final Lua hash mismatch source=$finalSourceHash installed=$finalInstalledHash"
}

$summary | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Root 'run_summary.json') -Encoding utf8
$summary | Format-Table -AutoSize
