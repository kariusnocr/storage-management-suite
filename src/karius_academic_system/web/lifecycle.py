"""Quản lý vòng đời tiến trình, cửa sổ Desktop & tự động đóng/khởi động lại cho Karius Academic System (KAS)."""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from karius_academic_system import APP_SHORT, __version__
from karius_academic_system import core as sc

BOOT_ID = uuid.uuid4().hex[:12]

_STATE_LOCK = threading.Lock()
_PROCESS_EXIT_ALLOWED = False
_RUNTIME_MODE = "ui"  # "ui" | "desktop" | "pywebview"
_TRACKED_BROWSER_PROC: Optional[subprocess.Popen] = None
_SHUTDOWN_HOOKS: List[Callable[[], None]] = []
_CURRENT_HOST = "127.0.0.1"
_CURRENT_PORT = 8765
_CURRENT_STDLIB = True


def _no_window_flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def resolve_console_python(python_exe: Optional[str] = None) -> str:
    """Ưu tiên `python.exe` trên Windows cho các tác vụ CLI chặn chờ (`pip install/uninstall`) thay vì `pythonw.exe`."""
    exe = python_exe or sys.executable
    if os.name == "nt":
        p = Path(exe)
        if p.name.lower() == "pythonw.exe":
            sibling = p.parent / "python.exe"
            if sibling.exists():
                return str(sibling)
    return exe


def resolve_windowless_python(python_exe: Optional[str] = None) -> str:
    """Ưu tiên `pythonw.exe` trên Windows khi chạy máy chủ nền để không nháy cửa sổ dòng lệnh đen."""
    exe = python_exe or sys.executable
    if os.name == "nt":
        p = Path(exe)
        sibling = p.parent / "pythonw.exe"
        if sibling.exists():
            return str(sibling)
    return exe


def runtime_state_path() -> Path:
    """Tệp lưu trạng thái phiên máy chủ & cửa sổ KAS đang chạy (`~/.config/kas/runtime.json`)."""
    return sc.user_config_dir() / "runtime.json"


def browser_profile_dir() -> Path:
    """Thư mục hồ sơ trình duyệt cô lập dành riêng cho cửa sổ KAS Desktop (không bao giờ đụng Edge/Chrome cá nhân)."""
    env_dir = os.environ.get("KAS_DATA_DIR")
    base = Path(env_dir).expanduser() if env_dir else (Path.home() / ".local" / "share" / "kas")
    return base / "browser_profile"


def set_process_exit_allowed(allowed: bool) -> None:
    global _PROCESS_EXIT_ALLOWED
    with _STATE_LOCK:
        _PROCESS_EXIT_ALLOWED = bool(allowed)


def is_process_exit_allowed() -> bool:
    with _STATE_LOCK:
        return _PROCESS_EXIT_ALLOWED


def set_runtime_ui_mode(mode: str) -> None:
    global _RUNTIME_MODE
    with _STATE_LOCK:
        _RUNTIME_MODE = str(mode or "ui")


def get_runtime_ui_mode() -> str:
    with _STATE_LOCK:
        return _RUNTIME_MODE


def set_tracked_browser_process(proc: Optional[subprocess.Popen]) -> None:
    global _TRACKED_BROWSER_PROC
    with _STATE_LOCK:
        _TRACKED_BROWSER_PROC = proc


def get_tracked_browser_pid() -> int:
    with _STATE_LOCK:
        if _TRACKED_BROWSER_PROC is not None and _TRACKED_BROWSER_PROC.poll() is None:
            return int(_TRACKED_BROWSER_PROC.pid)
    return 0


def register_shutdown_hook(fn: Callable[[], None]) -> None:
    with _STATE_LOCK:
        if fn not in _SHUTDOWN_HOOKS:
            _SHUTDOWN_HOOKS.append(fn)


def unregister_shutdown_hook(fn: Callable[[], None]) -> None:
    with _STATE_LOCK:
        if fn in _SHUTDOWN_HOOKS:
            _SHUTDOWN_HOOKS.remove(fn)


def register_runtime(
    *,
    host: str,
    port: int,
    stdlib: bool,
    mode: str = "ui",
    browser_pid: int = 0,
) -> Path:
    """Ghi thông tin phiên máy chủ KAS đang chạy để tiến trình cập nhật / gỡ cài đặt nhận diện chính xác."""
    global _CURRENT_HOST, _CURRENT_PORT, _CURRENT_STDLIB, _RUNTIME_MODE
    with _STATE_LOCK:
        _CURRENT_HOST = host
        _CURRENT_PORT = int(port)
        _CURRENT_STDLIB = bool(stdlib)
        _RUNTIME_MODE = mode
        bpid = int(browser_pid or (int(_TRACKED_BROWSER_PROC.pid) if (_TRACKED_BROWSER_PROC and _TRACKED_BROWSER_PROC.poll() is None) else 0))

    path = runtime_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "pid": os.getpid(),
        "boot_id": BOOT_ID,
        "version": __version__,
        "host": host,
        "port": int(port),
        "stdlib": bool(stdlib),
        "mode": mode,
        "browser_pid": bpid,
        "browser_profile": str(browser_profile_dir()),
        "started_utc": sc.now_utc_iso(),
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def read_runtime() -> Dict[str, Any]:
    path = runtime_state_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def clear_runtime(*, only_if_self: bool = True) -> None:
    path = runtime_state_path()
    if not path.exists():
        return
    if only_if_self:
        cur = read_runtime()
        if cur and int(cur.get("pid") or 0) not in (0, os.getpid()):
            return
    try:
        path.unlink()
    except OSError:
        pass


def _is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            proc = subprocess.run(
                ["tasklist", "/FI", f"PID eq {int(pid)}", "/NH"],
                capture_output=True,
                text=True,
                timeout=4,
                creationflags=_no_window_flags(),
            )
            return str(int(pid)) in (proc.stdout or "")
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def _probe_health(host: str, port: int, timeout: float = 0.8) -> Optional[Dict[str, Any]]:
    try:
        with urllib.request.urlopen(f"http://{host}:{int(port)}/api/health", timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, dict) and data.get("status") == "ok" and data.get("app_short") == APP_SHORT:
                return data
    except Exception:
        pass
    return None


def _is_port_open(host: str, port: int, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def close_pywebview_windows() -> int:
    """Đóng sạch mọi cửa sổ `pywebview` đang mở (nếu có) để `webview.start()` thoát ngay."""
    closed = 0
    try:
        if "webview" in sys.modules:
            wv = sys.modules["webview"]
            for win in list(getattr(wv, "windows", []) or []):
                try:
                    win.destroy()
                    closed += 1
                except Exception:
                    pass
    except Exception:
        pass
    return closed


def close_kas_browser_windows(
    *,
    browser_pid: int = 0,
    port: int = 0,
    profile_dir: Optional[Path] = None,
) -> int:
    """Đóng chỉ riêng cửa sổ KAS Desktop App (tuyệt đối không đóng trình duyệt cá nhân của người dùng)."""
    closed = 0
    with _STATE_LOCK:
        proc = _TRACKED_BROWSER_PROC
        eff_port = int(port or _CURRENT_PORT)
    if proc is not None and proc.poll() is None:
        try:
            proc.terminate()
            closed += 1
        except Exception:
            pass

    eff_profile = str(profile_dir or browser_profile_dir())
    if os.name == "nt":
        prof_esc = eff_profile.replace("'", "''")
        ps_cmd = "; ".join([
            "$ErrorActionPreference = 'SilentlyContinue'",
            f"$prof = '{prof_esc}'",
            f"$appTag = '--app=http://127.0.0.1:{eff_port}'",
            "$procs = Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^(msedge|chrome|brave)\\.exe$' -and $_.CommandLine }",
            "foreach ($p in $procs) {",
            "  if ($p.CommandLine.IndexOf($prof, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {",
            "    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue",
            "  } elseif ($p.CommandLine.IndexOf($appTag, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {",
            "    $gp = Get-Process -Id $p.ProcessId -ErrorAction SilentlyContinue",
            "    if ($gp -and $gp.MainWindowHandle -ne 0) { [void]$gp.CloseMainWindow() }",
            "  }",
            "}",
            "Get-Process msedge,chrome,brave -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like 'Karius Academic System*' } | ForEach-Object { [void]$_.CloseMainWindow() }",
        ])
        try:
            subprocess.run(
                ["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_cmd],
                capture_output=True,
                timeout=6,
                creationflags=_no_window_flags(),
            )
            closed += 1
        except Exception:
            pass
    elif browser_pid > 0 and browser_pid != os.getpid():
        try:
            os.kill(browser_pid, signal.SIGTERM)
            closed += 1
        except OSError:
            pass

    return closed


def trigger_graceful_shutdown(
    *,
    delay_sec: float = 0.45,
    close_windows: bool = False,
    hard_exit_timeout: float = 2.8,
) -> None:
    """Dừng máy chủ cục bộ an toàn sau khi gửi xong phản hồi HTTP; tự thoát tiến trình nếu đang chạy ở chế độ ứng dụng."""
    allow_exit = is_process_exit_allowed()

    def _runner() -> None:
        if delay_sec > 0:
            time.sleep(delay_sec)

        clear_runtime(only_if_self=True)

        if close_windows:
            close_pywebview_windows()
            close_kas_browser_windows(browser_pid=get_tracked_browser_pid())
        else:
            # Nếu đang chạy bằng pywebview thì bắt buộc đóng cửa sổ pywebview để `webview.start()` kết thúc và khởi động lại
            if get_runtime_ui_mode() == "pywebview":
                close_pywebview_windows()

        with _STATE_LOCK:
            hooks = list(_SHUTDOWN_HOOKS)
        for fn in hooks:
            try:
                fn()
            except Exception:
                pass

        if allow_exit:
            def _watchdog() -> None:
                time.sleep(max(0.5, hard_exit_timeout))
                os._exit(0)

            threading.Thread(target=_watchdog, daemon=True).start()

    threading.Thread(target=_runner, daemon=True).start()


def stop_running_kas_instances(
    *,
    close_windows: bool = False,
    timeout: float = 6.0,
) -> Dict[str, Any]:
    """Phát hiện và dừng sạch mọi tiến trình máy chủ KAS đang chạy (phục vụ CLI `kas update` / `kas uninstall`)."""
    st = sc.load_app_settings()
    rt = read_runtime()
    host = str(rt.get("host") or st.ui_host or "127.0.0.1")
    port = int(rt.get("port") or st.ui_port or 8765)
    stdlib = bool(rt.get("stdlib", True))
    mode = str(rt.get("mode") or "desktop")
    pid = int(rt.get("pid") or 0)
    browser_pid = int(rt.get("browser_pid") or 0)
    profile_raw = str(rt.get("browser_profile") or "")
    profile_dir = Path(profile_raw) if profile_raw else browser_profile_dir()

    health = _probe_health(host, port)
    if health and not pid:
        pid = int(health.get("pid") or 0)

    was_running = bool(health or (pid > 0 and pid != os.getpid() and _is_pid_alive(pid)))

    # 1. Thử tắt mềm qua HTTP `/api/shutdown` trước
    if health:
        try:
            req = urllib.request.Request(
                f"http://{host}:{port}/api/shutdown",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=2.0):
                pass
        except Exception:
            pass

    deadline = time.monotonic() + min(2.5, timeout)
    while time.monotonic() < deadline:
        alive_pid = pid > 0 and pid != os.getpid() and _is_pid_alive(pid)
        if not alive_pid and not _is_port_open(host, port):
            break
        time.sleep(0.2)

    # 2. Nếu tiến trình cũ vẫn còn sống (hoặc bị khóa bởi App Lock 401), dừng trực tiếp theo PID / CommandLine
    if pid > 0 and pid != os.getpid() and _is_pid_alive(pid):
        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    capture_output=True,
                    timeout=5,
                    creationflags=_no_window_flags(),
                )
            except Exception:
                pass
        else:
            try:
                os.kill(pid, signal.SIGTERM)
                time.sleep(0.5)
                if _is_pid_alive(pid):
                    os.kill(pid, signal.SIGKILL)
            except OSError:
                pass

    # Trên Windows quét thêm mọi tiến trình `karius_academic_system` (ui/desktop) còn sót
    if os.name == "nt":
        ps_kill = (
            "$ErrorActionPreference='SilentlyContinue'; "
            f"$myPid={os.getpid()}; "
            "Get-CimInstance Win32_Process | Where-Object { "
            "$_.ProcessId -ne $myPid -and $_.CommandLine -and "
            "($_.CommandLine -match 'karius_academic_system') -and "
            "($_.CommandLine -match '\\b(ui|desktop)\\b') "
            "} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
        )
        try:
            subprocess.run(
                ["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_kill],
                capture_output=True,
                timeout=6,
                creationflags=_no_window_flags(),
            )
        except Exception:
            pass

    if close_windows:
        close_kas_browser_windows(browser_pid=browser_pid, port=port, profile_dir=profile_dir)

    # Đợi cổng HTTP được giải phóng hoàn toàn
    end_wait = time.monotonic() + max(1.0, timeout - 2.5)
    while time.monotonic() < end_wait and _is_port_open(host, port):
        time.sleep(0.2)

    clear_runtime(only_if_self=False)
    return {
        "was_running": was_running,
        "pid": pid,
        "host": host,
        "port": port,
        "stdlib": stdlib,
        "mode": mode,
        "browser_pid": browser_pid,
    }
