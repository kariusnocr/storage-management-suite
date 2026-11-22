@echo off
setlocal
title Go cai dat Karius Academic System (KAS) v1.5.1 - Windows 11

echo ========================================================================
echo   KARIUS ACADEMIC SYSTEM (KAS) v1.5.1 - TRINH GO CAI DAT 1 NHAP DUP
echo   Thu muc: "%~dp0"
echo ========================================================================
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall_windows_sac_safe.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if not "%EXIT_CODE%"=="0" (
    echo [LOI] Qua trinh go cai dat ket thuc voi ma loi %EXIT_CODE%.
) else (
    echo [OK] Da go cai dat Karius Academic System (KAS)! Ban co the dong cua so nay.
)
pause
exit /b %EXIT_CODE%
