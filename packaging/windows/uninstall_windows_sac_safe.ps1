<#
.SYNOPSIS
    Go cai dat Karius Academic System (KAS) tren Windows 11 an toan va sach se.
.DESCRIPTION
    100% pure 7-bit ASCII (tuong thich tuyet doi Windows PowerShell 5.1 & PowerShell 7).
    Tu dong dung tien trinh KAS dang chay, go goi Python, xoa loi tat Desktop/Start Menu,
    don PATH Windows va go dang ky trong Windows Settings -> Apps -> Installed Apps.
    KHONG BAO GIO xoa thu muc tai lieu cua nguoi dung (vd: E:\SACH) hay du lieu Google Drive.
#>
[CmdletBinding()]
param(
    [switch]$RemoveConfig,
    [switch]$RemoveData,
    [switch]$Purge,
    [switch]$RemoveTools,
    [switch]$Yes,
    [int]$WaitPid = 0
)

$ErrorActionPreference = "Continue"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

if ($Purge) {
    $RemoveConfig = $true
    $RemoveData = $true
}

if ($WaitPid -gt 0) {
    try { Wait-Process -Id $WaitPid -Timeout 8 -ErrorAction SilentlyContinue } catch {}
    Start-Sleep -Seconds 2
}

Write-Host ""
Write-Host "==================================================================" -ForegroundColor Yellow
Write-Host "  KARIUS ACADEMIC SYSTEM (KAS) - TRINH GO CAI DAT WINDOWS 11" -ForegroundColor Yellow
Write-Host "  (Bao toan 100% thu muc tai lieu cua ban & du lieu Google Drive)" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Yellow
Write-Host ""

$cfgDir = Join-Path $env:USERPROFILE ".config\kas"
$dataDir = Join-Path $env:USERPROFILE ".local\share\kas"
$kasRoot = Join-Path $env:LOCALAPPDATA "kas"
$binDir = Join-Path $kasRoot "bin"
$regPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\KariusAcademicSystem"

Write-Host "Cac muc se duoc go bo:" -ForegroundColor White
Write-Host "  - Goi Python: karius-academic-system (va storage-management-suite neu co)" -ForegroundColor Gray
Write-Host "  - Lenh CLI & thu muc app: $kasRoot" -ForegroundColor Gray
Write-Host "  - Loi tat Desktop, Start Menu va muc trong Windows Installed Apps" -ForegroundColor Gray
Write-Host "  - Dong tro toi '$binDir' trong bien moi truong User PATH" -ForegroundColor Gray
if ($RemoveConfig) {
    Write-Host "  - [XOA] Cau hinh nguoi dung: $cfgDir" -ForegroundColor Red
} else {
    Write-Host "  - [GIU] Cau hinh nguoi dung: $cfgDir (dung -RemoveConfig hoac -Purge de xoa)" -ForegroundColor DarkGray
}
if ($RemoveData) {
    Write-Host "  - [XOA] Du lieu chi muc & OCR: $dataDir" -ForegroundColor Red
} else {
    Write-Host "  - [GIU] Du lieu chi muc & OCR: $dataDir (dung -RemoveData hoac -Purge de xoa)" -ForegroundColor DarkGray
}
if ($RemoveTools) {
    Write-Host "  - [XOA] Cong cu ben thu 3 qua winget (gh, 7z, ffmpeg, tesseract, poppler)" -ForegroundColor Red
}
Write-Host ""

if (-not $Yes) {
    $ans = Read-Host "Ban co chac chan muon go cai dat Karius Academic System (KAS)? (y/N)"
    if ($ans -notin @("y", "Y", "yes", "YES")) {
        Write-Host "Da huy go cai dat." -ForegroundColor Yellow
        exit 0
    }
    if (-not $RemoveConfig -and -not $RemoveData) {
        $ansPurge = Read-Host "Ban co muon xoa luon cau hinh & du lieu chi muc (~/.config/kas, ~/.local/share/kas)? (y/N)"
        if ($ansPurge -in @("y", "Y", "yes", "YES")) {
            $RemoveConfig = $true
            $RemoveData = $true
        }
    }
}

function Find-SignedPython {
    $pyCmd = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCmd) {
        try {
            $exe = (& py -3 -c "import sys; print(sys.executable)" 2>$null | Select-Object -First 1)
            if ($exe) { $exe = $exe.ToString().Trim() }
            if ($exe -and (Test-Path $exe) -and ($exe -notmatch "WindowsApps\\python\.exe$")) { return $exe }
        } catch {}
    }
    foreach ($name in @("python3", "python")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) {
            try {
                $exe = (& $cmd.Source -c "import sys; print(sys.executable)" 2>$null | Select-Object -First 1)
                if ($exe) { $exe = $exe.ToString().Trim() }
                if ($exe -and (Test-Path $exe) -and ($exe -notmatch "WindowsApps\\python\.exe$")) { return $exe }
            } catch {}
        }
    }
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

Write-Host "[1/5] Dang dong cua so va dung tien trinh KAS dang chay (neu co)..." -ForegroundColor Cyan
try {
    $rtPort = 8765
    $rtBrowserPid = 0
    $rtFile = Join-Path $cfgDir "runtime.json"
    if (Test-Path $rtFile) {
        try {
            $rtObj = Get-Content -Path $rtFile -Raw | ConvertFrom-Json
            if ($rtObj.port) { $rtPort = [int]$rtObj.port }
            if ($rtObj.browser_pid) { $rtBrowserPid = [int]$rtObj.browser_pid }
            if ($rtObj.pid -and ([int]$rtObj.pid -ne $PID)) {
                Stop-Process -Id ([int]$rtObj.pid) -Force -ErrorAction SilentlyContinue
            }
        } catch {}
    }
    $procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -and ($_.CommandLine -match "karius_academic_system") -and ($_.ProcessId -ne $PID)
    }
    foreach ($p in $procs) {
        Write-Host "      Dung tien trinh PID $($p.ProcessId)..." -ForegroundColor DarkGray
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }
    if ($rtBrowserPid -gt 0) {
        Stop-Process -Id $rtBrowserPid -Force -ErrorAction SilentlyContinue
    }
    $kasProf = Join-Path $dataDir "browser_profile"
    $appTag = "--app=http://127.0.0.1:$rtPort"
    $bProcs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -match "^(msedge|chrome|brave)\.exe$" -and $_.CommandLine
    }
    foreach ($bp in $bProcs) {
        if ($bp.CommandLine.IndexOf($kasProf, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
            Stop-Process -Id $bp.ProcessId -Force -ErrorAction SilentlyContinue
        } elseif ($bp.CommandLine.IndexOf($appTag, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
            $gp = Get-Process -Id $bp.ProcessId -ErrorAction SilentlyContinue
            if ($gp -and $gp.MainWindowHandle -ne 0) { [void]$gp.CloseMainWindow() }
        }
    }
    Get-Process msedge,chrome,brave -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like "Karius Academic System*" -or $_.MainWindowTitle -like "KAS*" } | ForEach-Object { [void]$_.CloseMainWindow() }
    Start-Sleep -Milliseconds 1200
} catch {}

Write-Host "[2/5] Dang go goi Python 'karius-academic-system'..." -ForegroundColor Cyan
$pythonExe = Find-SignedPython
if ($pythonExe) {
    & $pythonExe -m pip uninstall -y karius-academic-system storage-management-suite
} else {
    Write-Host "      (Khong tim thay trinh thong dich Python - bo qua buoc pip uninstall)" -ForegroundColor DarkGray
}

Write-Host "[3/5] Dang xoa loi tat Desktop, Start Menu, lenh 'kas' va don User PATH..." -ForegroundColor Cyan
$desktopDir = [Environment]::GetFolderPath("Desktop")
$oneDriveDesktop = Join-Path $env:USERPROFILE "OneDrive\Desktop"
$startMenuDir = Join-Path ([Environment]::GetFolderPath("Programs")) "Karius Academic System"

foreach ($lnk in @(
    (Join-Path $desktopDir "KAS.lnk"),
    (Join-Path $oneDriveDesktop "KAS.lnk"),
    (Join-Path $desktopDir "Karius Academic System (KAS).lnk"),
    (Join-Path $oneDriveDesktop "Karius Academic System (KAS).lnk")
)) {
    if (Test-Path $lnk) {
        Remove-Item -Path $lnk -Force -ErrorAction SilentlyContinue
        Write-Host "      Da xoa: $lnk" -ForegroundColor DarkGray
    }
}

if (Test-Path $startMenuDir) {
    Remove-Item -Path $startMenuDir -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "      Da xoa thu muc Start Menu: $startMenuDir" -ForegroundColor DarkGray
}

$userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath) {
    $normBin = $binDir.TrimEnd("\")
    $kept = ($userPath -split ";") | Where-Object { $_ -and ($_.Trim().Trim('"').TrimEnd("\") -ine $normBin) }
    [System.Environment]::SetEnvironmentVariable("Path", ($kept -join ";"), "User")
}

Write-Host "[4/5] Dang go dang ky Windows Settings -> Apps -> Installed Apps..." -ForegroundColor Cyan
if (Test-Path $regPath) {
    Remove-Item -Path $regPath -Force -ErrorAction SilentlyContinue
    Write-Host "      Da xoa khoa Registry: $regPath" -ForegroundColor DarkGray
}

Write-Host "[5/5] Dang xu ly cau hinh, du lieu chi muc va don thu muc cai dat..." -ForegroundColor Cyan
if ($RemoveConfig -and (Test-Path $cfgDir)) {
    Remove-Item -Path $cfgDir -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "      Da xoa cau hinh: $cfgDir" -ForegroundColor DarkGray
}
if ($RemoveData -and (Test-Path $dataDir)) {
    Remove-Item -Path $dataDir -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "      Da xoa du lieu chi muc: $dataDir" -ForegroundColor DarkGray
}
if ($RemoveTools) {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        foreach ($wgId in @("GitHub.cli", "7zip.7zip", "Gyan.FFmpeg", "UB-Mannheim.TesseractOCR", "oschwartz10612.Poppler")) {
            Write-Host "      Dang go cong cu winget: $wgId..." -ForegroundColor DarkGray
            & winget uninstall --exact --id $wgId --silent --disable-interactivity 2>$null | Out-Null
        }
    }
}

if (Test-Path $kasRoot) {
    $selfPath = $MyInvocation.MyCommand.Path
    if ($selfPath -and ($selfPath.StartsWith($kasRoot, [System.StringComparison]::OrdinalIgnoreCase))) {
        # Neu dang chay chinh tep trong %LOCALAPPDATA%\kas, hen xoa thu muc sau khi script thoat
        Start-Process -FilePath "cmd.exe" -ArgumentList "/c timeout /t 2 /nobreak >nul & rmdir /s /q `"$kasRoot`"" -WindowStyle Hidden
    } else {
        Remove-Item -Path $kasRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Write-Host ""
Write-Host "HOAN TAT GO CAI DAT KARIUS ACADEMIC SYSTEM (KAS)!" -ForegroundColor Green
Write-Host "  - Cac thu muc tai lieu cuc bo va Google Drive cua ban van duoc bao toan 100%." -ForegroundColor White
if (-not $RemoveConfig) {
    Write-Host "  - Cau hinh duoc giu lai tai: $cfgDir" -ForegroundColor DarkGray
}
if (-not $RemoveData) {
    Write-Host "  - Du lieu chi muc duoc giu lai tai: $dataDir" -ForegroundColor DarkGray
}
Write-Host ""
