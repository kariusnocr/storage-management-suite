"""Điểm vào Python nhúng trong APK Android (`kas_android_boot.py`) — KAS v1.9.0."""

from __future__ import annotations

import json

from karius_academic_system.web.android_bridge import (
    bootstrap_android_vault,
    configure_android_ssl_certs,
    start_android_embedded_server,
    stop_android_embedded_server,
)


def start_server_url(app_files_dir: str = "", external_files_dir: str = "", port: int = 8765) -> str:
    """Khởi chạy máy chủ KAS nội bộ trên Android và trả về URL `http://127.0.0.1:<port>`."""
    configure_android_ssl_certs()
    res = start_android_embedded_server(
        app_files_dir=str(app_files_dir or ""),
        external_files_dir=str(external_files_dir or ""),
        port=int(port or 8765),
    )
    return str(res.get("url") or "http://127.0.0.1:8765")


def start_server_json(app_files_dir: str = "", external_files_dir: str = "", port: int = 8765) -> str:
    """Khởi chạy máy chủ KAS nội bộ trên Android và trả về chuỗi JSON trạng thái."""
    configure_android_ssl_certs()
    res = start_android_embedded_server(
        app_files_dir=str(app_files_dir or ""),
        external_files_dir=str(external_files_dir or ""),
        port=int(port or 8765),
    )
    return json.dumps(res, ensure_ascii=False)


def ensure_vault(preferred_dir: str = "", vault_name: str = "Kho Tài Liệu Android") -> str:
    """Khởi tạo kho tài liệu Android và trả về chuỗi JSON."""
    res = bootstrap_android_vault(
        preferred_dir=str(preferred_dir or ""),
        vault_name=str(vault_name or "Kho Tài Liệu Android"),
        create_starter_files=True,
        force_new=bool(preferred_dir),
    )
    return json.dumps(res, ensure_ascii=False)


def stop_server() -> str:
    """Dừng máy chủ KAS nội bộ trên Android."""
    return json.dumps(stop_android_embedded_server(), ensure_ascii=False)
