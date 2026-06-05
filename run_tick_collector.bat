@echo off
:: 한글 깨짐 방지 (터미널 및 파이썬 강제 UTF-8 설정)
chcp 65001 >nul
set PYTHONIOENCODING=utf-8

cd /d "%~dp0"
echo [%date% %time%] 틱 데이터 수집 스케줄러 시작 >> logs\tick_collector.log

:loop
:: [수정 코드] PowerShell을 이용해 절대 실패하지 않는 24시간제 시간 추출
for /f "tokens=*" %%a in ('powershell -NoProfile -Command "Get-Date -Format 'HHmm'"') do set "hourMin=%%a"

:: 15시 30분(장 마감)이 넘으면 무한 루프 종료
if %hourMin% GEQ 1530 (
    echo [%date% %time%] 장 마감 시간 도달. 수집기 종료. >> logs\tick_collector.log
    goto end
)

echo [%date% %time%] 틱 데이터 수집기 실행/재실행 >> logs\tick_collector.log

:: 파이썬 스크립트 실행
python tick_collector.py >> logs\tick_collector.log 2>&1

:: 튕겼을 경우 5초 대기 후 다시 loop로 돌아가서 끈질기게 재실행
timeout /t 5 /nobreak >nul
goto loop

:end
exit