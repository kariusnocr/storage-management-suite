@echo off
chcp 65001 >nul 2>&1
set PYTHONUTF8=1

where py >nul 2>&1
if %ERRORLEVEL%==0 (
    py -3 -c "import storage_suite" >nul 2>&1
    if %ERRORLEVEL%==0 (
        start "" pyw -3 -m storage_suite desktop --browser --stdlib
        exit /b 0
    )
)

where python >nul 2>&1
if %ERRORLEVEL%==0 (
    python -c "import storage_suite" >nul 2>&1
    if %ERRORLEVEL%==0 (
        start "" pythonw -m storage_suite desktop --browser --stdlib
        exit /b 0
    )
)

echo Chua cai dat Storage Management Suite tren Python he thong.
echo Dang chay trinh cai dat an toan Smart App Control...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_windows_sac_safe.ps1"
