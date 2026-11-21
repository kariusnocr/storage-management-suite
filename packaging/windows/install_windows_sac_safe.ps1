<#
.SYNOPSIS
    Cai dat Karius Academic System (KAS) v1.1.0 tren Windows 11 AN TOAN VOI SMART APP CONTROL.
.DESCRIPTION
    100% pure 7-bit ASCII (tuong thich tuyet doi Windows PowerShell 5.1 & PowerShell 7 khong loi ma hoa).
    Khong dung tep .exe chua ky so hay pip.exe. Chay truc tiep qua trinh thong dich Python chinh thuc
    da ky so, ho tro cai offline tu goi ZIP (khong bi 404 khi repo GitHub la Private) hoac qua gh / token.
#>
[CmdletBinding()]
param(
    [string]$Version = "1.1.0",
    [string]$WheelPath = "",
    [string]$GitHubToken = "",
    [string]$Repo = "kariusnocr/storage-management-suite",
    [switch]$WithExtras,
    [switch]$NoLaunch
)

$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.ServicePointManager]::SecurityProtocol } catch {}

Write-Host ""
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "  KARIUS ACADEMIC SYSTEM (KAS) v$Version - CAI DAT WINDOWS 11" -ForegroundColor Cyan
Write-Host "  (Tuong thich 100% Smart App Control - khong can tat bao mat)" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host ""

function Find-SignedPython {
    $pyCmd = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCmd) {
        try {
            $exe = (& py -3 -c "import sys; print(sys.executable)" 2>$null | Select-Object -First 1)
            if ($exe) { $exe = $exe.ToString().Trim() }
            if ($exe -and (Test-Path $exe) -and ($exe -notmatch "WindowsApps\\python\.exe$")) {
                return $exe
            }
        } catch {}
    }
    foreach ($name in @("python3", "python")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) {
            try {
                $exe = (& $cmd.Source -c "import sys; print(sys.executable)" 2>$null | Select-Object -First 1)
                if ($exe) { $exe = $exe.ToString().Trim() }
                if ($exe -and (Test-Path $exe) -and ($exe -notmatch "WindowsApps\\python\.exe$")) {
                    return $exe
                }
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

function Find-LocalWheel {
    $candidates = @()
    if ($PSScriptRoot) { $candidates += $PSScriptRoot }
    $cwdPath = (Get-Location).Path
    if ($cwdPath) { $candidates += $cwdPath }
    $dlDir = Join-Path $env:USERPROFILE "Downloads"
    if (Test-Path $dlDir) {
        $candidates += $dlDir
        $subDl = Get-ChildItem -Path $dlDir -Directory -Filter "kas-windows-sac-safe*" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 2
        foreach ($d in $subDl) { $candidates += $d.FullName }
    }
    foreach ($dir in ($candidates | Select-Object -Unique)) {
        if (-not $dir -or -not (Test-Path $dir)) { continue }
        $hit = Get-ChildItem -Path $dir -Filter "karius_academic_system-*.whl" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($hit) { return $hit.FullName }
    }
    return $null
}

function Download-ReleaseWheel {
    param([string]$RepoName, [string]$TagVer, [string]$Token)

    $tmpDir = Join-Path ([System.IO.Path]::GetTempPath()) ("kas_install_" + [Guid]::NewGuid().ToString("N").Substring(0, 8))
    New-Item -ItemType Directory -Force -Path $tmpDir | Out-Null
    $whlName = "karius_academic_system-$TagVer-py3-none-any.whl"
    $destWhl = Join-Path $tmpDir $whlName

    $ghCmd = Get-Command gh -ErrorAction SilentlyContinue
    if ($ghCmd) {
        try {
            Write-Host "      Dang tai $whlName qua GitHub CLI (gh)..." -ForegroundColor DarkGray
            & gh release download "v$TagVer" -R $RepoName -p $whlName -D $tmpDir --clobber 2>$null | Out-Null
            if (Test-Path $destWhl) { return $destWhl }
        } catch {}
    }

    $effToken = if ($Token) { $Token } elseif ($env:GITHUB_TOKEN) { $env:GITHUB_TOKEN } elseif ($env:GH_TOKEN) { $env:GH_TOKEN } else { "" }
    if ($effToken) {
        try {
            Write-Host "      Dang tai $whlName qua GitHub API (co xac thuc token)..." -ForegroundColor DarkGray
            $hdr = @{ Authorization = "Bearer $effToken"; "User-Agent" = "KAS-Installer"; Accept = "application/vnd.github+json" }
            $rel = Invoke-RestMethod -Uri "https://api.github.com/repos/$RepoName/releases/tags/v$TagVer" -Headers $hdr
            $asset = $rel.assets | Where-Object { $_.name -eq $whlName } | Select-Object -First 1
            if ($asset) {
                $dlHdr = @{ Authorization = "Bearer $effToken"; "User-Agent" = "KAS-Installer"; Accept = "application/octet-stream" }
                Invoke-WebRequest -Uri $asset.url -Headers $dlHdr -OutFile $destWhl -UseBasicParsing
                if (Test-Path $destWhl) { return $destWhl }
            }
        } catch {
            Write-Host "      [!] Khong tai duoc bang token: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }

    $publicUrl = "https://github.com/$RepoName/releases/download/v$TagVer/$whlName"
    try {
        Write-Host "      Dang tai $whlName tu GitHub Release..." -ForegroundColor DarkGray
        Invoke-WebRequest -Uri $publicUrl -OutFile $destWhl -UseBasicParsing
        if (Test-Path $destWhl) { return $destWhl }
    } catch {
        Write-Host ""
        Write-Host "[!] KHONG TAI DUOC GOI CAI DAT TU GITHUB (loi 404 / kho dang o che do Private)." -ForegroundColor Red
        Write-Host "    Cach cai nhanh nhat (KHONG can token, KHONG bao gio bi 404):" -ForegroundColor Yellow
        Write-Host "    1. Tai tep 'kas-windows-sac-safe.zip' tu GitHub Releases v$TagVer" -ForegroundColor White
        Write-Host "       hoac tu Google Drive: [A] STORAGE / [00] TONG QUAN / [03] QUAN LY / [02] GOI PHAT HANH" -ForegroundColor White
        Write-Host "    2. Giai nen tep ZIP ra mot thu muc (vd: Downloads\kas-windows-sac-safe)." -ForegroundColor White
        Write-Host "    3. Nhap dup 'Cai_Dat_KAS_Windows11.cmd' ngay trong thu muc vua giai nen!" -ForegroundColor Green
        Write-Host ""
        Write-Host "    (Hoac neu dung PowerShell voi repo Private, hay dang nhap 'gh auth login' hoac dat `$env:GITHUB_TOKEN='ghp_...' roi chay lai.)" -ForegroundColor DarkGray
        exit 1
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

try {
    & $pythonExe -m pip --version 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { & $pythonExe -m ensurepip --upgrade | Out-Null }
} catch {
    & $pythonExe -m ensurepip --upgrade | Out-Null
}

if (-not $WheelPath -or -not (Test-Path $WheelPath)) {
    $localWhl = Find-LocalWheel
    if ($localWhl) {
        $WheelPath = $localWhl
    } else {
        $WheelPath = Download-ReleaseWheel -RepoName $Repo -TagVer $Version -Token $GitHubToken
    }
}

Write-Host "[2/4] Dang cai dat Karius Academic System (KAS) v$Version va thu vien thuan Python..." -ForegroundColor Cyan
Write-Host "      Nguon: $WheelPath" -ForegroundColor DarkGray

& $pythonExe -m pip install --user --upgrade --force-reinstall --no-warn-script-location $WheelPath
if ($LASTEXITCODE -ne 0) { throw "Cai dat goi KAS that bai (ma loi pip: $LASTEXITCODE)" }
& $pythonExe -m pip install --user --upgrade --no-warn-script-location openpyxl google-api-python-client google-auth-oauthlib google-auth-httplib2

if ($WithExtras) {
    Write-Host "      Dang cai them tuy chon [media,web]..." -ForegroundColor Cyan
    & $pythonExe -m pip install --user --upgrade --no-warn-script-location fastapi uvicorn pillow numpy
}

Write-Host "[3/4] Dang tao lenh CLI 'kas.cmd' (khong dung .exe chua ky) va them vao PATH..." -ForegroundColor Cyan
$binDir = Join-Path $env:LOCALAPPDATA "kas\bin"
New-Item -ItemType Directory -Force -Path $binDir | Out-Null

$cliCmd = "@echo off`r`nset PYTHONUTF8=1`r`n`"$pythonExe`" -m karius_academic_system %*`r`n"
[System.IO.File]::WriteAllText((Join-Path $binDir "kas.cmd"), $cliCmd, [System.Text.Encoding]::ASCII)

$desktopCmd = "@echo off`r`nset PYTHONUTF8=1`r`nstart `"`" `"$pythonwExe`" -m karius_academic_system desktop --browser --stdlib %*`r`n"
[System.IO.File]::WriteAllText((Join-Path $binDir "kas-desktop.cmd"), $desktopCmd, [System.Text.Encoding]::ASCII)

$userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
if (-not $userPath) { $userPath = "" }
$parts = $userPath -split ";" | Where-Object { $_ -ne "" }
if ($parts -notcontains $binDir) {
    $newPath = ($parts + $binDir) -join ";"
    [System.Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    $env:Path = "$binDir;$env:Path"
}

Write-Host "[4/4] Dang tao loi tat Desktop & Start Menu (pythonw.exe da ky so + Edge App Window)..." -ForegroundColor Cyan
try {
    $wsh = New-Object -ComObject WScript.Shell
    $desktopDir = [Environment]::GetFolderPath("Desktop")
    $startMenuDir = Join-Path ([Environment]::GetFolderPath("Programs")) "Karius Academic System"
    New-Item -ItemType Directory -Force -Path $startMenuDir | Out-Null

    foreach ($lnkPath in @(
        (Join-Path $desktopDir "Karius Academic System (KAS).lnk"),
        (Join-Path $startMenuDir "Karius Academic System (KAS).lnk")
    )) {
        $sc = $wsh.CreateShortcut($lnkPath)
        $sc.TargetPath = $pythonwExe
        $sc.Arguments = "-m karius_academic_system desktop --browser --stdlib"
        $sc.WorkingDirectory = $env:USERPROFILE
        $sc.Description = "Karius Academic System (KAS) v$Version - Quan tri Da Kho Du Lieu va AI Agent"
        $sc.IconLocation = "$env:SystemRoot\System32\shell32.dll,43"
        $sc.Save()
    }
    Write-Host "      Da tao loi tat: $desktopDir\Karius Academic System (KAS).lnk" -ForegroundColor Green
} catch {
    Write-Host "      (Bo qua tao loi tat: $($_.Exception.Message))" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== KIEM TRA SAU CAI DAT ===" -ForegroundColor Green
$env:PYTHONUTF8 = "1"
& $pythonExe -m karius_academic_system version
& $pythonExe -m karius_academic_system doctor

Write-Host ""
Write-Host "HOAN TAT! Ban co the:" -ForegroundColor Green
Write-Host "  1. Nhap dup 'Karius Academic System (KAS)' tren Desktop de ket noi kho cuc bo, Google Drive, Quy tac dat ten va Tro ly AI." -ForegroundColor White
Write-Host "  2. Mo PowerShell moi va go:" -ForegroundColor White
Write-Host '       kas vault add "Tai Lieu" "D:\TaiLieu"' -ForegroundColor Cyan
Write-Host '       kas vault add "[A] STORAGE" "https://drive.google.com/drive/folders/<FOLDER_ID>"' -ForegroundColor Cyan
Write-Host "       kas rules presets  |  kas ai chat  |  kas mcp config" -ForegroundColor Cyan
Write-Host ""

if (-not $NoLaunch) {
    Write-Host "Dang mo Karius Academic System (KAS)..." -ForegroundColor Cyan
    Start-Process -FilePath $pythonwExe -ArgumentList "-m karius_academic_system desktop --browser --stdlib"
}
