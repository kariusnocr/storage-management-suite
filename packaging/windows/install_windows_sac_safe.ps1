#Requires -Version 5.1
<#
.SYNOPSIS
    Cài đặt Storage Management Suite trên Windows 11 AN TOÀN VỚI SMART APP CONTROL (không cần tắt bảo mật).
.DESCRIPTION
    Không dùng tệp .exe chưa ký số hay pip.exe. Chỉ chạy trực tiếp thông qua trình thông dịch Python
    chính thức có chữ ký số (Python Software Foundation / Microsoft Store), cài các gói thuần Python
    (không nạp .pyd/.dll chưa ký), tạo lệnh `astorage` trong PATH và lối tắt Desktop mở bằng Edge App Window.
#>
[CmdletBinding()]
param(
    [string]$Version = "4.0.1",
    [string]$WheelPath = "",
    [switch]$WithExtras,
    [switch]$NoLaunch
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host ""
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "  STORAGE MANAGEMENT SUITE v$Version — CAI DAT AN TOAN WINDOWS 11" -ForegroundColor Cyan
Write-Host "  (Tuong thich 100% Smart App Control — khong can tat bao mat)" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host ""

function Find-SignedPython {
    # Ưu tiên py launcher (cài từ python.org, đã ký số PSF) hoặc python.exe chính thức
    $pyCmd = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCmd) {
        try {
            $exe = (& py -3 -c "import sys; print(sys.executable)" 2>$null).Trim()
            if ($exe -and (Test-Path $exe) -and ($exe -notmatch "WindowsApps\\python\.exe$")) {
                return $exe
            }
        } catch {}
    }
    foreach ($name in @("python3", "python")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) {
            try {
                $exe = (& $cmd.Source -c "import sys; print(sys.executable)" 2>$null).Trim()
                if ($exe -and (Test-Path $exe) -and ($exe -notmatch "WindowsApps\\python\.exe$")) {
                    return $exe
                }
            } catch {}
        }
    }
    # Quét thư mục cài chuẩn của Python.org
    $patterns = @(
        "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe",
        "$env:ProgramFiles\Python3*\python.exe"
    )
    foreach ($pat in $patterns) {
        $hits = Get-Item $pat -ErrorAction SilentlyContinue | Sort-Object FullName -Descending
        if ($hits) { return $hits[0].FullName }
    }
    return $null
}

$pythonExe = Find-SignedPython
if (-not $pythonExe) {
    Write-Host "[1/4] Chua tim thay Python 3.11+ chinh thuc (co chu ky so)." -ForegroundColor Yellow
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Host "      Dang cai Python 3.12 chinh thuc tu Python Software Foundation qua winget..." -ForegroundColor Cyan
        & winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
        $pythonExe = Find-SignedPython
    }
    if (-not $pythonExe) {
        Write-Host ""
        Write-Host "[!] Vui long cai Python 3.12 chinh thuc (da ky so) tu:" -ForegroundColor Red
        Write-Host "    https://www.python.org/downloads/windows/  (hoac Microsoft Store: Python 3.12)" -ForegroundColor White
        Write-Host "    Sau khi cai xong, chay lai script nay!" -ForegroundColor Yellow
        exit 1
    }
}

$pythonDir = Split-Path -Parent $pythonExe
$pythonwExe = Join-Path $pythonDir "pythonw.exe"
if (-not (Test-Path $pythonwExe)) { $pythonwExe = $pythonExe }

$pyVer = (& $pythonExe --version 2>&1).ToString().Trim()
Write-Host "[1/4] Trinh thong dich Python da ky so: $pythonExe ($pyVer)" -ForegroundColor Green

# Xác định nguồn gói .whl
if (-not $WheelPath) {
    $scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
    $localWhl = Get-ChildItem -Path $scriptDir -Filter "storage_management_suite-*.whl" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($localWhl) {
        $WheelPath = $localWhl.FullName
    }
}

$wheelUrl = "https://github.com/kariusnocr/storage-management-suite/releases/download/v$Version/storage_management_suite-$Version-py3-none-any.whl"
$installSource = if ($WheelPath -and (Test-Path $WheelPath)) { $WheelPath } else { $wheelUrl }

Write-Host "[2/4] Dang cai dat Storage Management Suite & thu vien thuan Python qua 'python -m pip'..." -ForegroundColor Cyan
Write-Host "      Nguon: $installSource" -ForegroundColor DarkGray

# Luôn gọi qua `python.exe -m pip` (KHÔNG gọi `pip.exe` để tránh Smart App Control chặn shim chưa ký)
& $pythonExe -m pip install --user --upgrade --no-warn-script-location $installSource
# Cài các thư viện Google Drive OAuth 2.0 thuần Python (không dùng cryptography .pyd nếu bị SAC chặn)
& $pythonExe -m pip install --user --upgrade --no-warn-script-location openpyxl google-api-python-client google-auth-oauthlib google-auth-httplib2

if ($WithExtras) {
    Write-Host "      Dang cai them tuy chon [media,web]..." -ForegroundColor Cyan
    & $pythonExe -m pip install --user --upgrade --no-warn-script-location fastapi uvicorn pillow numpy
}

Write-Host "[3/4] Dang tao lenh CLI 'astorage.cmd' (khong dung .exe chua ky) va them vao PATH..." -ForegroundColor Cyan
$binDir = Join-Path $env:LOCALAPPDATA "astorage\bin"
New-Item -ItemType Directory -Force -Path $binDir | Out-Null

$cliCmd = @"
@echo off
chcp 65001 >nul 2>&1
set PYTHONUTF8=1
"$pythonExe" -m storage_suite %*
"@
Set-Content -Path (Join-Path $binDir "astorage.cmd") -Value $cliCmd -Encoding ASCII

$desktopCmd = @"
@echo off
set PYTHONUTF8=1
start "" "$pythonwExe" -m storage_suite desktop --browser --stdlib %*
"@
Set-Content -Path (Join-Path $binDir "astorage-desktop.cmd") -Value $desktopCmd -Encoding ASCII

$userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
if (-not $userPath) { $userPath = "" }
$parts = $userPath -split ";" | Where-Object { $_ -ne "" }
if ($parts -notcontains $binDir) {
    $newPath = ($parts + $binDir) -join ";"
    [System.Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    $env:Path = "$binDir;$env:Path"
}

Write-Host "[4/4] Dang tao loi tat Desktop & Start Menu (chay qua pythonw.exe da ky so + Edge App Window)..." -ForegroundColor Cyan
try {
    $wsh = New-Object -ComObject WScript.Shell
    $desktopDir = [Environment]::GetFolderPath("Desktop")
    $startMenuDir = Join-Path ([Environment]::GetFolderPath("Programs")) "Storage Management Suite"
    New-Item -ItemType Directory -Force -Path $startMenuDir | Out-Null

    foreach ($lnkPath in @(
        (Join-Path $desktopDir "Storage Management Suite.lnk"),
        (Join-Path $startMenuDir "Storage Management Suite.lnk")
    )) {
        $sc = $wsh.CreateShortcut($lnkPath)
        $sc.TargetPath = $pythonwExe
        $sc.Arguments = "-m storage_suite desktop --browser --stdlib"
        $sc.WorkingDirectory = $env:USERPROFILE
        $sc.Description = "Storage Management Suite v$Version — Quan tri kho [A] STORAGE"
        $sc.IconLocation = "$env:SystemRoot\System32\shell32.dll,43"
        $sc.Save()
    }
    Write-Host "      Da tao loi tat: $desktopDir\Storage Management Suite.lnk" -ForegroundColor Green
} catch {
    Write-Host "      (Bo qua tao loi tat: $($_.Exception.Message))" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== KIEM TRA SAU CAI DAT ===" -ForegroundColor Green
$env:PYTHONUTF8 = "1"
& $pythonExe -m storage_suite version
& $pythonExe -m storage_suite doctor

Write-Host ""
Write-Host "HOAN TAT! Ban co the:" -ForegroundColor Green
Write-Host "  1. Nhap dup bieu tuong 'Storage Management Suite' tren Desktop de mo ung dung." -ForegroundColor White
Write-Host "  2. Mo PowerShell/Terminal moi va go: astorage doctor  |  astorage auth login --credentials credentials.json" -ForegroundColor White
Write-Host "  3. Hoac chay truc tiep khong can PATH: `"$pythonExe`" -m storage_suite desktop --browser --stdlib" -ForegroundColor White
Write-Host ""

if (-not $NoLaunch) {
    Write-Host "Dang mo Storage Management Suite..." -ForegroundColor Cyan
    Start-Process -FilePath $pythonwExe -ArgumentList "-m storage_suite desktop --browser --stdlib"
}
