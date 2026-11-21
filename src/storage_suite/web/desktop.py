"""Ứng dụng Desktop gốc (`astorage desktop`) — hỗ trợ pywebview và chế độ cửa sổ độc lập Edge/Chrome an toàn với Smart App Control."""

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
from typing import List, Optional

from storage_suite import __version__
from storage_suite import core as sc
from storage_suite.web.app import start_embedded_server


def _find_free_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def _is_suite_running(url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/api/health", timeout=0.6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("status") == "ok" and "root_id" in data
    except Exception:
        return False


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


def launch_standalone_window(url: str) -> Optional[subprocess.Popen]:
    """Mở cửa sổ ứng dụng độc lập (không thanh địa chỉ/tab) bằng trình duyệt đã ký số của hệ điều hành."""
    browser = find_app_mode_browser()
    if browser:
        try:
            return subprocess.Popen(
                [browser, f"--app={url}", "--window-size=1280,840"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            pass
    try:
        webbrowser.open(url)
    except Exception:
        pass
    return None


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="astorage desktop", description="Khởi chạy ứng dụng Desktop Storage Management Suite.")
    ap.add_argument("--port", type=int, default=8765, help="Cổng nội bộ (mặc định 8765; truyền 0 để tự chọn cổng trống)")
    ap.add_argument("--browser", action="store_true", help="Mở bằng cửa sổ ứng dụng Edge/Chrome (an toàn với Smart App Control)")
    ap.add_argument("--stdlib", action="store_true", help="Dùng máy chủ HTTP thuần Python (không nạp .pyd/.dll ngoài)")
    args = ap.parse_args(argv)

    host = "127.0.0.1"
    port = args.port if args.port > 0 else _find_free_port(host)
    url = f"http://{host}:{port}"

    # Nếu đã có máy chủ chạy sẵn trên cùng cổng (ví dụ nhấp đúp shortcut lần 2), chỉ mở lại cửa sổ
    if args.port > 0 and _is_suite_running(url):
        sc.log(f"Phát hiện Storage Management Suite đang chạy sẵn tại {url} — mở cửa sổ ứng dụng...")
        launch_standalone_window(url)
        return 0

    try:
        srv_thread, stop_fn, engine = start_embedded_server(host=host, port=port, prefer_stdlib=args.stdlib)
    except OSError:
        port = _find_free_port(host)
        url = f"http://{host}:{port}"
        srv_thread, stop_fn, engine = start_embedded_server(host=host, port=port, prefer_stdlib=args.stdlib)

    sc.log(f"Storage Management Suite Desktop v{__version__} ({engine}) sẵn sàng tại {url}")

    if not args.browser:
        try:
            import webview  # type: ignore

            webview.create_window(
                f"Storage Management Suite v{__version__} — [A] STORAGE",
                url,
                width=1280,
                height=840,
                min_size=(960, 640),
            )
            webview.start()
            stop_fn()
            return 0
        except (ImportError, OSError):
            sc.log("Chuyển sang cửa sổ ứng dụng độc lập Edge/Chrome (tương thích hoàn toàn Windows Smart App Control)...")

    sc.log(f"Đang mở cửa sổ ứng dụng tại {url} (nhấn Ctrl+C để thoát)...")
    launch_standalone_window(url)
    try:
        while srv_thread.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        stop_fn()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
