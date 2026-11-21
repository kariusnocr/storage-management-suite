@echo off
setlocal
set PYTHONUTF8=1

where py >nul 2>&1
if %ERRORLEVEL%==0 (
    py -3 -c "import karius_academic_system" >nul 2>&1
    if %ERRORLEVEL%==0 (
        start "" pyw -3 -m karius_academic_system desktop --browser --stdlib
        exit /b 0
    )
)

where python >nul 2>&1
if %ERRORLEVEL%==0 (
    python -c "import karius_academic_system" >nul 2>&1
    if %ERRORLEVEL%==0 (
        start "" pythonw -m karius_academic_system desktop --browser --stdlib
        exit /b 0
    )
)

echo Chua cai dat Karius Academic System (KAS) tren Python he thong.
echo Dang chay trinh cai dat an toan Smart App Control...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_windows_sac_safe.ps1"
pause
