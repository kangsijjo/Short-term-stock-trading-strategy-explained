@echo off
REM 등록된 자동 수집 작업 삭제 (관리자 권한 필요)

schtasks /delete /tn "KISDataCollector_Daily" /f
schtasks /delete /tn "KISDataCollector_Startup" /f

echo.
echo 작업 삭제 완료.
pause
