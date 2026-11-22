@echo off
setlocal
title Cai dat Karius Academic System (KAS) v1.5.1 - Windows 11 Smart App Control Safe

echo ========================================================================
echo   KARIUS ACADEMIC SYSTEM (KAS) v1.5.1 - TRINH CAI DAT 1 NHAP DUP
echo   Thu muc cai dat: "%~dp0"
echo ========================================================================
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_windows_sac_safe.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if not "%EXIT_CODE%"=="0" (
    echo [LOI] Qua trinh cai dat ket thuc voi ma loi %EXIT_CODE%.
    echo Vui long xem dong thong bao phia tren de khac phuc.
) else (
    echo [OK] Cai dat thanh cong! Ban co the dong cua so nay.
)
pause
exit /b %EXIT_CODE%
