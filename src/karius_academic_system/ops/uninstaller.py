"""Trình gỡ cài đặt phần mềm an toàn, đa nền tảng (`kas uninstall` / `kas go-cai-dat`) cho Karius Academic System (KAS)."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from karius_academic_system import APP_NAME, APP_SHORT, __version__
from karius_academic_system import core as sc

WINDOWS_UNINSTALL_REG_SUBKEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\KariusAcademicSystem"
PACKAGE_NAMES = ("karius-academic-system", "storage-management-suite")
OPTIONAL_WINGET_TOOL_IDS = (
    ("gh", "GitHub.cli"),
    ("7z", "7zip.7zip"),
    ("ffmpeg", "Gyan.FFmpeg"),
    ("tesseract", "UB-Mannheim.TesseractOCR"),
    ("poppler", "oschwartz10612.Poppler"),
)


def _dir_size_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    total = 0
    for root, _dirs, files in os.walk(path):
        for fn in files:
            try:
                total += (Path(root) / fn).stat().st_size
            except OSError:
                continue
    return total


def _windows_install_root() -> Path:
    local_app = os.environ.get("LOCALAPPDATA")
    if local_app:
        return Path(local_app) / "kas"
    return Path.home() / "AppData" / "Local" / "kas"


def _windows_shortcuts() -> List[Path]:
    if os.name != "nt":
        return []
    user_prof = Path(os.environ.get("USERPROFILE") or str(Path.home()))
    appdata = Path(os.environ.get("APPDATA") or str(user_prof / "AppData" / "Roaming"))
    desktop = user_prof / "Desktop"
    # Hỗ trợ thêm trường hợp Desktop đồng bộ OneDrive trên Windows 11
    onedrive_desktop = user_prof / "OneDrive" / "Desktop"
    start_menu_dir = appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Karius Academic System"
    candidates = [
        desktop / "Karius Academic System (KAS).lnk",
        onedrive_desktop / "Karius Academic System (KAS).lnk",
        start_menu_dir,
    ]
    return candidates


def _posix_launchers() -> List[Path]:
    if os.name == "nt":
        return []
    home = Path.home()
    return [
        home / ".local" / "share" / "applications" / "karius-academic-system.desktop",
        home / "Applications" / "Karius Academic System.app",
    ]


def _default_data_root() -> Path:
    env = os.environ.get("KAS_DATA_DIR")
    if env:
        return Path(env).expanduser()
    st = sc.load_app_settings()
    if st.data_dir_override:
        return Path(st.data_dir_override).expanduser()
    return Path.home() / ".local" / "share" / "kas"


def _windows_uninstall_reg_exists() -> bool:
    if os.name != "nt":
        return False
    try:
        import winreg  # type: ignore

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINDOWS_UNINSTALL_REG_SUBKEY):
            return True
    except OSError:
        return False
    except Exception:
        return False


def _windows_user_path_contains(target_dir: Path) -> bool:
    if os.name != "nt":
        return False
    try:
        import winreg  # type: ignore

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
            val, _ = winreg.QueryValueEx(key, "Path")
            norm_target = os.path.normcase(os.path.normpath(str(target_dir)))
            for p in str(val).split(";"):
                if p.strip() and os.path.normcase(os.path.normpath(p.strip().strip('"'))) == norm_target:
                    return True
    except Exception:
        return False
    return False


def _remove_dir_from_windows_user_path(target_dir: Path) -> bool:
    if os.name != "nt":
        return False
    try:
        import winreg  # type: ignore

        norm_target = os.path.normcase(os.path.normpath(str(target_dir)))
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as key:
            cur_val, reg_type = winreg.QueryValueEx(key, "Path")
            parts = [p.strip().strip('"') for p in str(cur_val).split(";") if p.strip()]
            new_parts = [p for p in parts if os.path.normcase(os.path.normpath(p)) != norm_target]
            if len(new_parts) != len(parts):
                winreg.SetValueEx(key, "Path", 0, reg_type or winreg.REG_EXPAND_SZ, ";".join(new_parts))
                return True
    except Exception:
        return False
    return False


def _delete_windows_uninstall_reg() -> bool:
    if os.name != "nt":
        return False
    try:
        import winreg  # type: ignore

        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, WINDOWS_UNINSTALL_REG_SUBKEY)
        return True
    except OSError:
        return False
    except Exception:
        return False


def inspect_installation(
    *,
    remove_config: bool = False,
    remove_data: bool = False,
    remove_tools: bool = False,
) -> Dict[str, Any]:
    """Kiểm kê đầy đủ các thành phần KAS đang cài trên máy để hiển thị trước khi gỡ cài đặt."""
    cfg_dir = sc.user_config_dir()
    data_root = _default_data_root()
    win_root = _windows_install_root()
    win_bin = win_root / "bin"

    items: List[Dict[str, Any]] = [
        {
            "category": "package",
            "label": f"Gói Python `{PACKAGE_NAMES[0]}` (v{__version__})",
            "path": str(Path(__file__).resolve().parent.parent),
            "exists": True,
            "selected": True,
            "size_bytes": 0,
            "size_human": "—",
        }
    ]

    if os.name == "nt":
        items.append({
            "category": "app_bin",
            "label": "Thư mục lệnh CLI & trình gỡ cài đặt cục bộ (`kas.cmd`, `kas-desktop.cmd`)",
            "path": str(win_root),
            "exists": win_root.exists(),
            "selected": win_root.exists(),
            "size_bytes": _dir_size_bytes(win_root),
            "size_human": sc.human_size(_dir_size_bytes(win_root)),
        })
        for sc_path in _windows_shortcuts():
            items.append({
                "category": "shortcut",
                "label": f"Lối tắt Windows ({sc_path.name})",
                "path": str(sc_path),
                "exists": sc_path.exists(),
                "selected": sc_path.exists(),
                "size_bytes": _dir_size_bytes(sc_path),
                "size_human": sc.human_size(_dir_size_bytes(sc_path)),
            })
        has_path = _windows_user_path_contains(win_bin)
        items.append({
            "category": "path",
            "label": "Biến môi trường User PATH trỏ tới `kas\\bin`",
            "path": str(win_bin),
            "exists": has_path,
            "selected": has_path,
            "size_bytes": 0,
            "size_human": "—",
        })
        has_reg = _windows_uninstall_reg_exists()
        items.append({
            "category": "registry",
            "label": "Mục trong Windows Settings -> Apps -> Installed Apps",
            "path": f"HKCU\\{WINDOWS_UNINSTALL_REG_SUBKEY}",
            "exists": has_reg,
            "selected": has_reg,
            "size_bytes": 0,
            "size_human": "—",
        })
    else:
        for lp in _posix_launchers():
            items.append({
                "category": "shortcut",
                "label": f"Lối tắt ứng dụng ({lp.name})",
                "path": str(lp),
                "exists": lp.exists(),
                "selected": lp.exists(),
                "size_bytes": _dir_size_bytes(lp),
                "size_human": sc.human_size(_dir_size_bytes(lp)),
            })

    cfg_size = _dir_size_bytes(cfg_dir)
    items.append({
        "category": "config",
        "label": "Thư mục cấu hình người dùng (vaults.toml, app_settings.json, account.json, OAuth token)",
        "path": str(cfg_dir),
        "exists": cfg_dir.exists(),
        "selected": bool(remove_config and cfg_dir.exists()),
        "optional": True,
        "size_bytes": cfg_size,
        "size_human": sc.human_size(cfg_size),
    })

    data_size = _dir_size_bytes(data_root)
    items.append({
        "category": "data",
        "label": "Thư mục dữ liệu chỉ mục, SQLite `kas.db`, ảnh chụp & OCR `tessdata`",
        "path": str(data_root),
        "exists": data_root.exists(),
        "selected": bool(remove_data and data_root.exists()),
        "optional": True,
        "size_bytes": data_size,
        "size_human": sc.human_size(data_size),
    })

    if remove_tools:
        for tool_name, wg_id in OPTIONAL_WINGET_TOOL_IDS:
            found = sc.find_cli_tool(tool_name, refresh=False)
            items.append({
                "category": "tool",
                "label": f"Công cụ bên thứ 3 `{tool_name}` ({wg_id})",
                "path": found or wg_id,
                "exists": bool(found),
                "selected": bool(found),
                "optional": True,
                "size_bytes": 0,
                "size_human": "—",
            })

    return {
        "app_name": APP_NAME,
        "app_short": APP_SHORT,
        "version": __version__,
        "platform": platform.system(),
        "python": sys.executable,
        "remove_config": remove_config,
        "remove_data": remove_data,
        "remove_tools": remove_tools,
        "config_dir": str(cfg_dir),
        "config_size_human": sc.human_size(cfg_size),
        "data_dir": str(data_root),
        "data_size_human": sc.human_size(data_size),
        "windows_powershell_cmd": (
            "irm https://raw.githubusercontent.com/kariusnocr/storage-management-suite/main/"
            "packaging/windows/uninstall_windows_sac_safe.ps1 | iex"
        ),
        "safety_note": (
            "An toàn tuyệt đối: Trình gỡ cài đặt KHÔNG BAO GIỜ xóa hay chạm vào các thư mục tài liệu của bạn "
            "(như ổ cứng cục bộ, E:\\SÁCH) hay dữ liệu trên Google Drive."
        ),
        "items": items,
    }


def _safe_remove_path(path: Path) -> Tuple[bool, str]:
    if not path.exists():
        return False, "không tồn tại"
    try:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
        return True, f"đã xóa {path}"
    except Exception as exc:
        return False, f"không thể xóa {path}: {exc}"


def perform_uninstall(
    *,
    remove_config: bool = False,
    remove_data: bool = False,
    remove_tools: bool = False,
    uninstall_python_pkg: bool = True,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """Thực thi gỡ cài đặt KAS (mặc định `dry_run=True` an toàn — chỉ xóa thật khi truyền `dry_run=False`)."""
    plan = inspect_installation(
        remove_config=remove_config,
        remove_data=remove_data,
        remove_tools=remove_tools,
    )
    removed: List[str] = []
    skipped: List[str] = []
    errors: List[str] = []

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "plan": plan,
            "removed": removed,
            "skipped": skipped,
            "errors": errors,
        }

    # 0. Tự động đóng cửa sổ & dừng mọi máy chủ nền KAS đang chạy để giải phóng tệp khóa
    from karius_academic_system.web.lifecycle import resolve_console_python, stop_running_kas_instances

    stopped = stop_running_kas_instances(close_windows=True)
    if stopped.get("was_running"):
        removed.append(f"Đã dừng tiến trình KAS đang chạy (PID {stopped.get('pid') or 'active'}) và đóng cửa sổ ứng dụng")

    # 1. Xóa lối tắt, thư mục bin cục bộ, User PATH và mục Windows Installed Apps
    if os.name == "nt":
        win_root = _windows_install_root()
        win_bin = win_root / "bin"
        if _remove_dir_from_windows_user_path(win_bin):
            removed.append(f"User PATH: {win_bin}")
        if _delete_windows_uninstall_reg():
            removed.append(f"Registry: HKCU\\{WINDOWS_UNINSTALL_REG_SUBKEY}")
        for sc_path in _windows_shortcuts():
            if sc_path.exists():
                ok, msg = _safe_remove_path(sc_path)
                (removed if ok else errors).append(msg)
        if win_root.exists():
            ok, msg = _safe_remove_path(win_root)
            (removed if ok else errors).append(msg)
    else:
        for lp in _posix_launchers():
            if lp.exists():
                ok, msg = _safe_remove_path(lp)
                (removed if ok else errors).append(msg)

    # 2. Tùy chọn xóa cấu hình & dữ liệu chỉ mục
    if remove_config:
        cfg_dir = sc.user_config_dir()
        if cfg_dir.exists():
            ok, msg = _safe_remove_path(cfg_dir)
            (removed if ok else errors).append(msg)
    else:
        skipped.append(f"Giữ nguyên thư mục cấu hình: {plan['config_dir']}")

    if remove_data:
        data_root = _default_data_root()
        if data_root.exists():
            ok, msg = _safe_remove_path(data_root)
            (removed if ok else errors).append(msg)
    else:
        skipped.append(f"Giữ nguyên thư mục dữ liệu/chỉ mục: {plan['data_dir']}")

    # 3. Tùy chọn gỡ công cụ bên thứ 3 (chỉ khi người dùng chủ động bật)
    if remove_tools and os.name == "nt" and sc.find_cli_tool("winget"):
        for tool_name, wg_id in OPTIONAL_WINGET_TOOL_IDS:
            if not sc.find_cli_tool(tool_name, refresh=False):
                continue
            try:
                proc = subprocess.run(
                    ["winget", "uninstall", "--exact", "--id", wg_id, "--silent", "--disable-interactivity"],
                    capture_output=True,
                    text=True,
                    timeout=180,
                )
                if proc.returncode == 0:
                    removed.append(f"winget uninstall {wg_id}")
                else:
                    errors.append(f"Không gỡ được {wg_id} (mã lỗi {proc.returncode})")
            except Exception as exc:
                errors.append(f"Lỗi gỡ {wg_id}: {exc}")

    # 4. Gỡ gói Python cuối cùng (để mọi mô-đun đang nạp chạy trọn vẹn trước khi gỡ)
    if uninstall_python_pkg:
        pip_python = resolve_console_python(sys.executable)
        run_kwargs: Dict[str, Any] = {"capture_output": True, "text": True, "timeout": 120}
        if os.name == "nt":
            run_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        for pkg in PACKAGE_NAMES:
            try:
                proc = subprocess.run(
                    [pip_python, "-m", "pip", "uninstall", "-y", pkg],
                    **run_kwargs,
                )
                out_low = (proc.stdout + "\n" + proc.stderr).lower()
                if proc.returncode == 0 and "skipping" not in out_low:
                    removed.append(f"Python package: {pkg}")
            except Exception as exc:
                errors.append(f"Lỗi gỡ gói Python `{pkg}`: {exc}")

    return {
        "ok": len(errors) == 0,
        "dry_run": False,
        "plan": plan,
        "removed": removed,
        "skipped": skipped,
        "errors": errors,
    }


def _generate_windows_detached_ps1(
    *,
    wait_pid: int,
    python_exe: str,
    cfg_dir: Path,
    data_root: Path,
    remove_config: bool,
    remove_data: bool,
    browser_pid: int = 0,
    port: int = 8765,
    browser_profile: Optional[Path] = None,
) -> str:
    """Sinh kịch bản PowerShell thuần 7-bit ASCII tự đóng cửa sổ, dừng hẳn máy chủ KAS rồi dọn sạch."""
    py_esc = python_exe.replace("'", "''")
    cfg_esc = str(cfg_dir).replace("'", "''")
    data_esc = str(data_root).replace("'", "''")
    prof_esc = str(browser_profile or (data_root / "browser_profile")).replace("'", "''")
    rm_cfg = "$true" if remove_config else "$false"
    rm_data = "$true" if remove_data else "$false"
    return "\r\n".join([
        "$ErrorActionPreference = 'Continue'",
        f"$waitPid = {int(wait_pid)}",
        f"$browserPid = {int(browser_pid)}",
        f"$prof = '{prof_esc}'",
        f"$appTag = '--app=http://127.0.0.1:{int(port)}'",
        "if ($waitPid -gt 0) {",
        "    try { Wait-Process -Id $waitPid -Timeout 5 -ErrorAction SilentlyContinue } catch {}",
        "    if (Get-Process -Id $waitPid -ErrorAction SilentlyContinue) {",
        "        Stop-Process -Id $waitPid -Force -ErrorAction SilentlyContinue",
        "    }",
        "}",
        "$kasProcs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {",
        "    $_.ProcessId -ne $PID -and $_.CommandLine -and ($_.CommandLine -match 'karius_academic_system')",
        "}",
        "foreach ($p in $kasProcs) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }",
        "if ($browserPid -gt 0) { Stop-Process -Id $browserPid -Force -ErrorAction SilentlyContinue }",
        "$bProcs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {",
        "    $_.Name -match '^(msedge|chrome|brave)\\.exe$' -and $_.CommandLine",
        "}",
        "foreach ($bp in $bProcs) {",
        "    if ($bp.CommandLine.IndexOf($prof, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {",
        "        Stop-Process -Id $bp.ProcessId -Force -ErrorAction SilentlyContinue",
        "    } elseif ($bp.CommandLine.IndexOf($appTag, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {",
        "        $gp = Get-Process -Id $bp.ProcessId -ErrorAction SilentlyContinue",
        "        if ($gp -and $gp.MainWindowHandle -ne 0) { [void]$gp.CloseMainWindow() }",
        "    }",
        "}",
        "Get-Process msedge,chrome,brave -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like 'Karius Academic System*' } | ForEach-Object { [void]$_.CloseMainWindow() }",
        "Start-Sleep -Milliseconds 1200",
        f"$pyExe = '{py_esc}'",
        "if ($pyExe -match 'pythonw\\.exe$') {",
        "    $candPy = $pyExe -replace 'pythonw\\.exe$', 'python.exe'",
        "    if (Test-Path $candPy) { $pyExe = $candPy }",
        "}",
        "& $pyExe -m pip uninstall -y karius-academic-system storage-management-suite",
        "$binDir = Join-Path $env:LOCALAPPDATA 'kas\\bin'",
        "$kasRoot = Join-Path $env:LOCALAPPDATA 'kas'",
        "$uPath = [Environment]::GetEnvironmentVariable('Path', 'User')",
        "if ($uPath) {",
        "    $kept = ($uPath -split ';') | Where-Object { $_ -and ($_.TrimEnd('\\') -ine $binDir.TrimEnd('\\')) }",
        "    [Environment]::SetEnvironmentVariable('Path', ($kept -join ';'), 'User')",
        "}",
        "Remove-Item -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\KariusAcademicSystem' -Force -ErrorAction SilentlyContinue",
        "$desktop = [Environment]::GetFolderPath('Desktop')",
        "$oneDriveDesktop = Join-Path $env:USERPROFILE 'OneDrive\\Desktop'",
        "$startMenu = Join-Path ([Environment]::GetFolderPath('Programs')) 'Karius Academic System'",
        "Remove-Item -Path (Join-Path $desktop 'Karius Academic System (KAS).lnk') -Force -ErrorAction SilentlyContinue",
        "Remove-Item -Path (Join-Path $oneDriveDesktop 'Karius Academic System (KAS).lnk') -Force -ErrorAction SilentlyContinue",
        "Remove-Item -Path $startMenu -Recurse -Force -ErrorAction SilentlyContinue",
        "Remove-Item -Path $kasRoot -Recurse -Force -ErrorAction SilentlyContinue",
        f"if ({rm_cfg}) {{ Remove-Item -Path '{cfg_esc}' -Recurse -Force -ErrorAction SilentlyContinue }}",
        f"if ({rm_data}) {{ Remove-Item -Path '{data_esc}' -Recurse -Force -ErrorAction SilentlyContinue }}",
        "Remove-Item -Path $MyInvocation.MyCommand.Path -Force -ErrorAction SilentlyContinue",
    ]) + "\r\n"


def schedule_detached_self_uninstall(
    *,
    remove_config: bool = False,
    remove_data: bool = False,
    port: int = 8765,
) -> Dict[str, Any]:
    """Khởi chạy tiến trình gỡ cài đặt tách rời để an toàn đóng cửa sổ, dừng server và gỡ sạch gói KAS."""
    from karius_academic_system.web.lifecycle import (
        browser_profile_dir,
        get_tracked_browser_pid,
        resolve_console_python,
    )

    cfg_dir = sc.user_config_dir()
    data_root = _default_data_root()
    prof_dir = browser_profile_dir()
    bpid = get_tracked_browser_pid()
    tag = uuid.uuid4().hex[:8]

    if os.name == "nt":
        ps1_path = Path(tempfile.gettempdir()) / f"kas_self_uninstall_{tag}.ps1"
        ps1_text = _generate_windows_detached_ps1(
            wait_pid=os.getpid(),
            python_exe=resolve_console_python(sys.executable),
            cfg_dir=cfg_dir,
            data_root=data_root,
            remove_config=remove_config,
            remove_data=remove_data,
            browser_pid=bpid,
            port=port,
            browser_profile=prof_dir,
        )
        ps1_path.write_bytes(ps1_text.encode("ascii", errors="ignore"))
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass", "-File", str(ps1_path)],
            creationflags=creationflags,
            close_fds=True,
        )
        return {
            "ok": True,
            "scheduled": True,
            "closing": True,
            "script": str(ps1_path),
            "message": "Đã khởi chạy trình gỡ cài đặt nền. Ứng dụng và máy chủ KAS sẽ tự động đóng ngay bây giờ.",
        }

    sh_path = Path(tempfile.gettempdir()) / f"kas_self_uninstall_{tag}.sh"
    lines = [
        "#!/bin/sh",
        f"WAIT_PID={os.getpid()}",
        f"BROWSER_PID={int(bpid)}",
        "i=0",
        'while [ "$i" -lt 20 ] && kill -0 "$WAIT_PID" 2>/dev/null; do sleep 0.25; i=$((i + 1)); done',
        'kill -0 "$WAIT_PID" 2>/dev/null && kill -TERM "$WAIT_PID" 2>/dev/null || true',
        '[ "$BROWSER_PID" -gt 0 ] && kill -TERM "$BROWSER_PID" 2>/dev/null || true',
        "sleep 0.6",
        f'"{sys.executable}" -m pip uninstall -y karius-academic-system storage-management-suite >/dev/null 2>&1 || true',
        'rm -f "$HOME/.local/share/applications/karius-academic-system.desktop"',
        'rm -rf "$HOME/Applications/Karius Academic System.app"',
    ]
    if remove_config:
        lines.append(f'rm -rf "{cfg_dir}"')
    if remove_data:
        lines.append(f'rm -rf "{data_root}"')
    lines.append('rm -f "$0"')
    sh_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        os.chmod(sh_path, 0o700)
    except OSError:
        pass
    subprocess.Popen(["/bin/sh", str(sh_path)], start_new_session=True, close_fds=True)
    return {
        "ok": True,
        "scheduled": True,
        "closing": True,
        "script": str(sh_path),
        "message": "Đã khởi chạy trình gỡ cài đặt nền. Ứng dụng và máy chủ KAS sẽ tự động đóng ngay bây giờ.",
    }


def format_uninstall_plan(plan: Dict[str, Any]) -> str:
    lines = [
        "==========================================================================",
        f"🗑️  GỠ CÀI ĐẶT {plan['app_name'].upper()} ({plan['app_short']} v{plan['version']})",
        "==========================================================================",
        f"• Hệ điều hành : {plan['platform']} | Python: {plan['python']}",
        f"• Bảo toàn     : {plan['safety_note']}",
        "",
        "Danh sách thành phần kiểm kê:",
    ]
    for it in plan["items"]:
        status = "SẼ XÓA" if it["selected"] else ("GIỮ LẠI" if it["exists"] else "không có")
        mark = "✗" if it["selected"] else ("•" if it["exists"] else "○")
        size_part = f" ({it['size_human']})" if it["size_human"] != "—" and it["exists"] else ""
        lines.append(f"  {mark} [{status:8s}] {it['label']}{size_part}")
        lines.append(f"                {it['path']}")
    lines.append("==========================================================================")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="kas uninstall",
        description=f"Gỡ cài đặt an toàn {APP_NAME} ({APP_SHORT}) — mặc định chạy thử, chỉ xóa thật khi truyền `--thuc-thi`.",
    )
    ap.add_argument("--thuc-thi", "--execute", action="store_true", dest="execute", help="Thực sự gỡ cài đặt (mặc định chỉ xem trước)")
    ap.add_argument("--dong-y", "--yes", "-y", action="store_true", dest="yes", help="Không hỏi xác nhận")
    ap.add_argument("--xoa-cau-hinh", "--remove-config", action="store_true", dest="remove_config", help="Xóa thêm ~/.config/kas (cấu hình, danh sách kho, token OAuth)")
    ap.add_argument("--xoa-du-lieu", "--remove-data", action="store_true", dest="remove_data", help="Xóa thêm ~/.local/share/kas (SQLite kas.db, ảnh chụp, OCR tessdata)")
    ap.add_argument("--xoa-sach", "--purge", action="store_true", dest="purge", help="Xóa cả cấu hình lẫn dữ liệu chỉ mục của KAS")
    ap.add_argument("--go-cong-cu", "--remove-tools", action="store_true", dest="remove_tools", help="Tùy chọn gỡ thêm các công cụ bên thứ 3 cài qua winget (gh, 7z, ffmpeg, tesseract, poppler)")
    ap.add_argument("--json", action="store_true", dest="as_json", help="Xuất kết quả dạng JSON")
    args = ap.parse_args(argv)

    rm_cfg = bool(args.remove_config or args.purge)
    rm_data = bool(args.remove_data or args.purge)
    rm_tools = bool(args.remove_tools)

    plan = inspect_installation(remove_config=rm_cfg, remove_data=rm_data, remove_tools=rm_tools)
    if not args.execute:
        if args.as_json:
            print(json.dumps({"dry_run": True, "plan": plan}, ensure_ascii=False, indent=2))
        else:
            sc.log(format_uninstall_plan(plan))
            sc.log("Chế độ xem trước (chưa xóa gì). Để thực thi thật, chạy:")
            sc.log("  kas uninstall --thuc-thi")
            sc.log("  kas uninstall --xoa-sach --thuc-thi   (gỡ luôn cấu hình + chỉ mục kas.db)")
        return 0

    if not args.as_json:
        sc.log(format_uninstall_plan(plan))
    if not sc.confirm(f"Xác nhận gỡ cài đặt {APP_NAME} ({APP_SHORT}) khỏi máy này?", args.yes):
        sc.log("Đã hủy thao tác gỡ cài đặt.")
        return 0

    res = perform_uninstall(
        remove_config=rm_cfg,
        remove_data=rm_data,
        remove_tools=rm_tools,
        dry_run=False,
    )
    if args.as_json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        sc.log("\n=== KẾT QUẢ GỠ CÀI ĐẶT ===")
        for r in res["removed"]:
            sc.log(f"  ✓ {r}")
        for s in res["skipped"]:
            sc.log(f"  • {s}")
        for e in res["errors"]:
            sc.log(f"  ✗ {e}")
        sc.log("Hoàn tất gỡ cài đặt Karius Academic System (KAS)!" if res["ok"] else "Gỡ cài đặt hoàn tất với một số cảnh báo.")
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
