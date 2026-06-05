# Registers 6 scheduled tasks for KIS data collection + backtest + KRX + DART.
# KIS_Ranking / KIS_EOD / KIS_Backtest / KIS_KRX / KIS_DART : PowerShell Register-ScheduledTask
# KIS_Monthly                                                : schtasks (PowerShell has no native monthly trigger)
$ErrorActionPreference = "Stop"
$dir = $PSScriptRoot
if (-not $dir) { $dir = (Get-Location).Path }
$bat         = Join-Path $dir "run_collector.bat"
$batBacktest = Join-Path $dir "run_backtest.bat"
$batKrx      = Join-Path $dir "run_krx.bat"
$batDart     = Join-Path $dir "run_dart.bat"
$pyMonthly   = Join-Path $dir "monthly_xlsx_builder.py"

Write-Host "Installing KIS scheduled tasks from: $dir"
Write-Host ""

foreach ($f in @($bat, $batBacktest, $batKrx, $batDart)) {
    if (-not (Test-Path $f)) {
        Write-Host "[ERROR] $f not found" -ForegroundColor Red
        exit 1
    }
}

# Remove existing tasks (clean install)
foreach ($t in @("KIS_Ranking","KIS_EOD","KIS_Monthly","KIS_Backtest","KIS_KRX","KIS_DART")) {
    Unregister-ScheduledTask -TaskName $t -Confirm:$false -ErrorAction SilentlyContinue
}

$action         = New-ScheduledTaskAction -Execute $bat         -Argument "auto" -WorkingDirectory $dir
$actionBacktest = New-ScheduledTaskAction -Execute $batBacktest -Argument "auto" -WorkingDirectory $dir
$actionKrx      = New-ScheduledTaskAction -Execute $batKrx      -Argument "auto" -WorkingDirectory $dir
$actionDart     = New-ScheduledTaskAction -Execute $batDart     -Argument "auto" -WorkingDirectory $dir

function New-KisSettings {
    $s = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -ExecutionTimeLimit (New-TimeSpan -Hours 2)
    $s.DisallowStartIfOnBatteries = $false
    $s.StopIfGoingOnBatteries = $false
    return $s
}

# [1/6] KIS_Ranking : daily 09:00, repeat every 30 min for 5h30m
$trg = New-ScheduledTaskTrigger -Daily -At "09:00"
$rep = New-ScheduledTaskTrigger -Once -At "09:00" `
        -RepetitionInterval (New-TimeSpan -Minutes 30) `
        -RepetitionDuration (New-TimeSpan -Hours 5 -Minutes 30)
$trg.Repetition = $rep.Repetition
Register-ScheduledTask -TaskName "KIS_Ranking" -Action $action -Trigger $trg `
        -Settings (New-KisSettings) -Force | Out-Null
Write-Host "[1/6] KIS_Ranking  - daily 09:00, every 30 min until 14:30"

# [2/6] KIS_EOD : daily 15:40
$trgEod = New-ScheduledTaskTrigger -Daily -At "15:40"
Register-ScheduledTask -TaskName "KIS_EOD" -Action $action -Trigger $trgEod `
        -Settings (New-KisSettings) -Force | Out-Null
Write-Host "[2/6] KIS_EOD      - daily 15:40"

# [3/6] KIS_Backtest : daily 16:00
$trgBt = New-ScheduledTaskTrigger -Daily -At "16:00"
Register-ScheduledTask -TaskName "KIS_Backtest" -Action $actionBacktest -Trigger $trgBt `
        -Settings (New-KisSettings) -Force | Out-Null
Write-Host "[3/6] KIS_Backtest - daily 16:00"

# [4/6] KIS_KRX : daily 08:30 (전일치 KRX 신용/공매도)
$trgKrx = New-ScheduledTaskTrigger -Daily -At "08:30"
Register-ScheduledTask -TaskName "KIS_KRX" -Action $actionKrx -Trigger $trgKrx `
        -Settings (New-KisSettings) -Force | Out-Null
Write-Host "[4/6] KIS_KRX      - daily 08:30 (T-1 credit/short balance)"

# [5/6] KIS_DART : daily 19:00 (당일 공시)
$trgDart = New-ScheduledTaskTrigger -Daily -At "19:00"
Register-ScheduledTask -TaskName "KIS_DART" -Action $actionDart -Trigger $trgDart `
        -Settings (New-KisSettings) -Force | Out-Null
Write-Host "[5/6] KIS_DART     - daily 19:00 (today's disclosures)"

# [6/6] KIS_Monthly : 1st of month 02:00
$monthlyCmd = 'cmd /c cd /d "' + $dir + '" && py -3.11 "' + $pyMonthly + '"'
schtasks /create /tn "KIS_Monthly" /tr $monthlyCmd /sc monthly /mo 1 /d 1 /st 02:00 /f | Out-Null
$mt = Get-ScheduledTask -TaskName "KIS_Monthly"
$mt.Settings.StartWhenAvailable = $true
Set-ScheduledTask -TaskName "KIS_Monthly" -Settings $mt.Settings | Out-Null
Write-Host "[6/6] KIS_Monthly  - 1st of month 02:00"

Write-Host ""
Write-Host "=== Verification (next run time) ==="
$allOk = $true
foreach ($t in @("KIS_Ranking","KIS_EOD","KIS_Backtest","KIS_KRX","KIS_DART","KIS_Monthly")) {
    $info = Get-ScheduledTask -TaskName $t | Get-ScheduledTaskInfo
    $next = if ($info.NextRunTime) { $info.NextRunTime } else { "<NONE - PROBLEM>"; $allOk = $false }
    Write-Host ("  {0,-13} next: {1}" -f $t, $next)
}
Write-Host ""
if ($allOk) {
    Write-Host "All 6 tasks have a valid next-run time. OK." -ForegroundColor Green
} else {
    Write-Host "A task has no next-run time. Check above." -ForegroundColor Red
}
