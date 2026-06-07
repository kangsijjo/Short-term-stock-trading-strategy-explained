@echo off
setlocal EnableExtensions EnableDelayedExpansion
REM ============================================================
REM  Paper Trading 자동 실행 — 매일 평일 16:30
REM  1) live_signal.py — 오늘의 메인 전략 신호 감지
REM  2) paper_tracker.py — 가상 포지션 + 누적 손익 리포트
REM ============================================================

cd /d "%~dp0"
set "EXITCODE=0"

for /f %%I in ('powershell -NoProfile -Command "(Get-Date).DayOfWeek.value__"') do set "DOW=%%I"
for /f %%I in ('powershell -NoProfile -Command "(Get-Date).ToString('yyyyMMdd')"') do set "TODAY=%%I"

REM 주말 스킵
if "!DOW!"=="0" goto :weekend
if "!DOW!"=="6" goto :weekend
goto :weekday

:weekend
echo [SKIP] Weekend.
if /i not "%1"=="auto" pause
endlocal
exit /b 0

:weekday
set "LOGDIR=logs"
if not exist "!LOGDIR!" mkdir "!LOGDIR!"
set "LOGFILE=!LOGDIR!\paper_!TODAY!.log"

Forfiles /P "!LOGDIR!" /M paper_*.log /D -30 /C "cmd /c del @file" 2>nul

echo. >> "!LOGFILE!"
echo ============================================================ >> "!LOGFILE!"
echo  Start: %DATE% %TIME% >> "!LOGFILE!"
echo ============================================================ >> "!LOGFILE!"

REM venv 우선 사용
if exist ".venv\Scripts\python.exe" (
    echo === us_market === >> "!LOGFILE!"
    ".venv\Scripts\python.exe" us_market_collector.py >> "!LOGFILE!" 2>&1
    echo. >> "!LOGFILE!"
    echo === live_signal === >> "!LOGFILE!"
    ".venv\Scripts\python.exe" live_signal.py >> "!LOGFILE!" 2>&1
    echo. >> "!LOGFILE!"
    echo === paper_tracker === >> "!LOGFILE!"
    ".venv\Scripts\python.exe" paper_tracker.py >> "!LOGFILE!" 2>&1
    echo. >> "!LOGFILE!"
    echo === exit_rule_engine === >> "!LOGFILE!"
    ".venv\Scripts\python.exe" exit_rule_engine.py >> "!LOGFILE!" 2>&1
    echo. >> "!LOGFILE!"
    echo === dashboard === >> "!LOGFILE!"
    ".venv\Scripts\python.exe" dashboard_generator.py >> "!LOGFILE!" 2>&1
    set "EXITCODE=!ERRORLEVEL!"
    goto :report
)
where py >nul 2>nul
if !ERRORLEVEL! EQU 0 (
    py -3.11 live_signal.py >> "!LOGFILE!" 2>&1
    py -3.11 paper_tracker.py >> "!LOGFILE!" 2>&1
    set "EXITCODE=!ERRORLEVEL!"
    goto :report
)
echo [ERROR] python not found >> "!LOGFILE!"
set "EXITCODE=2"

:report
echo. >> "!LOGFILE!"
echo  Exit code: !EXITCODE! (time: %TIME%) >> "!LOGFILE!"
echo Exit code: !EXITCODE!
echo Log file: !LOGFILE!

if /i not "%1"=="auto" pause
set "RC=!EXITCODE!"
endlocal & exit /b %RC%
