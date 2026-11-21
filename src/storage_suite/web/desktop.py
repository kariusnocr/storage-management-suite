"""Ứng dụng Desktop gốc (`astorage desktop`) bọc giao diện Web Dashboard bằng `pywebview`."""

from __future__ import annotations

import argparse
import socket
import threading
import time
import webbrowser
from typing import List, Optional

from storage_suite import __version__
from storage_suite import core as sc
from storage_suite.web.app import create_app


def _find_free_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="astorage desktop", description="Khởi chạy ứng dụng Desktop Storage Management Suite.")
    ap.add_argument("--port", type=int, default=0, help="Cổng nội bộ (0 = tự chọn cổng trống)")
    ap.add_argument("--browser", action="store_true", help="Mở bằng trình duyệt mặc định thay vì cửa sổ pywebview")
    args = ap.parse_args(argv)

    try:
        import uvicorn
    except ImportError:
        sc.log('Thiếu thư viện Web UI. Cài bằng: pip install "storage-management-suite[desktop]"')
        return 1

    host = "127.0.0.1"
    port = args.port or _find_free_port(host)
    url = f"http://{host}:{port}"
    app = create_app()

    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    srv_thread = threading.Thread(target=server.run, daemon=True)
    srv_thread.start()

    # Chờ máy chủ nội bộ sẵn sàng tối đa 5 giây
    deadline = time.monotonic() + 5.0
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)

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
            server.should_exit = True
            return 0
        except ImportError:
            sc.log("Chưa cài `pywebview` — chuyển sang mở bằng trình duyệt cục bộ...")

    sc.log(f"Đang mở Storage Management Suite tại {url} (nhấn Ctrl+C để thoát)...")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        while srv_thread.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        server.should_exit = True
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
