"""Ứng dụng Desktop gốc (`kas desktop`) — Karius Academic System (KAS) v1.6.0."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import time
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional

from karius_academic_system import APP_NAME, APP_SHORT, __version__
from karius_academic_system import core as sc
from karius_academic_system.web.app import start_embedded_server
from karius_academic_system.web.lifecycle import (
    browser_profile_dir,
    clear_runtime,
    register_runtime,
    set_process_exit_allowed,
    set_runtime_ui_mode,
    set_tracked_browser_process,
    stop_running_kas_instances,
)


def _find_free_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def _probe_running_kas(url: str) -> Optional[Dict[str, Any]]:
    try:
        with urllib.request.urlopen(f"{url}/api/health", timeout=0.6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, dict) and data.get("status") == "ok" and data.get("app_short") == APP_SHORT:
                return data
    except Exception:
        pass
    return None


def _is_kas_running(url: str) -> bool:
    return _probe_running_kas(url) is not None


def find_app_mode_browser() -> Optional[str]:
    """Tìm Microsoft Edge hoặc Google Chrome (đã ký số chính thức) để mở cửa sổ Desktop App (`--app=URL`)."""
    candidates: List[str] = []
    if os.name == "nt":
        for env_key in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
            base = os.environ.get(env_key)
            if not base:
                continue
            candidates.extend([
                str(Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe"),
                str(Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"),
                str(Path(base) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe"),
            ])
    for name in ("msedge", "microsoft-edge", "google-chrome", "chromium", "chromium-browser", "chrome"):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    for c in candidates:
        if c and Path(c).exists():
            return c
    return None


def build_app_window_command(browser: str, url: str, profile_dir: Optional[Path] = None) -> List[str]:
    """Tạo lệnh mở cửa sổ Desktop độc lập với hồ sơ trình duyệt cô lập riêng cho KAS."""
    prof = profile_dir or browser_profile_dir()
    prof.mkdir(parents=True, exist_ok=True)
    return [
        browser,
        f"--user-data-dir={prof}",
        "--no-first-run",
        "--no-default-browser-check",
        "--new-window",
        f"--app={url}",
        "--window-size=1320,860",
    ]


def launch_standalone_window(url: str) -> Optional[subprocess.Popen]:
    """Mở cửa sổ ứng dụng độc lập (không thanh địa chỉ/tab) bằng trình duyệt đã ký số của hệ điều hành."""
    browser = find_app_mode_browser()
    if browser:
        try:
            proc = subprocess.Popen(
                build_app_window_command(browser, url),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            set_tracked_browser_process(proc)
            return proc
        except OSError:
            pass
    try:
        webbrowser.open(url)
    except Exception:
        pass
    return None


def main(argv: Optional[List[str]] = None) -> int:
    st = sc.load_app_settings()
    ap = argparse.ArgumentParser(prog="kas desktop", description=f"Khởi chạy ứng dụng Desktop {APP_NAME} ({APP_SHORT}).")
    ap.add_argument("--port", type=int, default=st.ui_port, help=f"Cổng nội bộ (mặc định {st.ui_port}; truyền 0 để tự chọn cổng trống)")
    ap.add_argument("--browser", action="store_true", help="Mở bằng cửa sổ ứng dụng Edge/Chrome (an toàn với Smart App Control)")
    ap.add_argument("--stdlib", action="store_true", help="Dùng máy chủ HTTP thuần Python (không nạp .pyd/.dll ngoài)")
    args = ap.parse_args(argv)

    set_process_exit_allowed(True)

    host = st.ui_host or "127.0.0.1"
    port = args.port if args.port > 0 else _find_free_port(host)
    url = f"http://{host}:{port}"

    if args.port > 0:
        existing = _probe_running_kas(url)
        if existing is not None:
            running_ver = str(existing.get("version") or "")
            if running_ver == __version__:
                sc.log(f"Phát hiện {APP_NAME} ({APP_SHORT}) v{running_ver} đang chạy sẵn tại {url} — mở cửa sổ ứng dụng...")
                launch_standalone_window(url)
                return 0
            sc.log(f"Phát hiện phiên bản cũ (v{running_ver or '?'}) đang chạy tại {url} — tự động dừng để khởi chạy v{__version__}...")
            stop_running_kas_instances(close_windows=False)

    try:
        srv_thread, stop_fn, engine = start_embedded_server(host=host, port=port, prefer_stdlib=args.stdlib)
    except OSError:
        port = _find_free_port(host)
        url = f"http://{host}:{port}"
        srv_thread, stop_fn, engine = start_embedded_server(host=host, port=port, prefer_stdlib=args.stdlib)

    is_stdlib = engine == "stdlib-http"
    sc.log(f"{APP_NAME} ({APP_SHORT}) Desktop v{__version__} ({engine}) sẵn sàng tại {url}")

    try:
        if not args.browser:
            try:
                import webview  # type: ignore

                set_runtime_ui_mode("pywebview")
                register_runtime(host=host, port=port, stdlib=is_stdlib, mode="pywebview")
                try:
                    from karius_academic_system.ops.updater import maybe_start_background_update_check

                    maybe_start_background_update_check()
                except Exception:
                    pass
                webview.create_window(
                    f"{APP_NAME} ({APP_SHORT}) v{__version__}",
                    url,
                    width=1320,
                    height=860,
                    min_size=(960, 640),
                )
                webview.start()
                stop_fn()
                return 0
            except (ImportError, OSError):
                sc.log("Chuyển sang cửa sổ ứng dụng độc lập Edge/Chrome (tương thích hoàn toàn Windows Smart App Control)...")

        set_runtime_ui_mode("desktop")
        sc.log(f"Đang mở {APP_NAME} tại {url} (nhấn Ctrl+C để thoát)...")
        bproc = launch_standalone_window(url)
        register_runtime(
            host=host,
            port=port,
            stdlib=is_stdlib,
            mode="desktop",
            browser_pid=(int(bproc.pid) if bproc is not None else 0),
        )
        try:
            from karius_academic_system.ops.updater import maybe_start_background_update_check

            maybe_start_background_update_check()
        except Exception:
            pass
        try:
            while srv_thread.is_alive():
                time.sleep(0.35)
        except KeyboardInterrupt:
            stop_fn()
        return 0
    finally:
        clear_runtime(only_if_self=True)


if __name__ == "__main__":
    raise SystemExit(main())
