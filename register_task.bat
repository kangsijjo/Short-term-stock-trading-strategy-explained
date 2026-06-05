@echo off
REM ============================================================
REM  Windows 작업 스케줄러에 자동 수집 작업 등록
REM
REM  ★ 관리자 권한 cmd에서 실행하세요 ★
REM     (이 파일 우클릭 → "관리자 권한으로 실행")
REM
REM  등록되는 작업:
REM   1) 평일(월~금) 15:35에 자동 실행
REM   2) 시스템 시작 후 3분 뒤 자동 실행
REM ============================================================

setlocal

set TASK_DAILY=KISDataCollector_Daily
set TASK_STARTUP=KISDataCollector_Startup
set BATPATH=%~dp0run_collector.bat

REM 배치 파일 존재 확인
if not exist "%BATPATH%" (
    echo [ERROR] run_collector.bat 을 찾을 수 없습니다: %BATPATH%
    pause
    exit /b 1
)

echo ============================================================
echo  작업 스케줄러 등록 시작
echo  배치 파일: %BATPATH%
echo ============================================================
echo.

REM ---- 평일 15:35 트리거 ----
echo [1/2] 평일 15:35 작업 등록 중...
schtasks /create /f ^
  /tn "%TASK_DAILY%" ^
  /tr "\"%BATPATH%\"" ^
  /sc weekly /d MON,TUE,WED,THU,FRI ^
  /st 15:35 ^
  /rl HIGHEST

if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] 평일 작업 등록 실패. 관리자 권한으로 실행했는지 확인하세요.
    pause
    exit /b 1
)

REM ---- 시스템 시작 시 트리거 (3분 지연) ----
echo.
echo [2/2] 시스템 시작 시 작업 등록 중...
schtasks /create /f ^
  /tn "%TASK_STARTUP%" ^
  /tr "\"%BATPATH%\"" ^
  /sc onstart ^
  /delay 0000:03 ^
  /rl HIGHEST

if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] 시작 시 작업 등록 실패.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  등록 완료!
echo ============================================================
echo.
echo  등록된 작업:
echo   - %TASK_DAILY%   (평일 15:35)
echo   - %TASK_STARTUP% (시스템 시작 후 3분)
echo.
echo  확인: 작업 스케줄러 (taskschd.msc) 열기
echo  수동 실행 테스트: schtasks /run /tn "%TASK_DAILY%"
echo  삭제하려면: unregister_task.bat 실행
echo.
pause
