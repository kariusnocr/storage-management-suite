"""Tự động chọn backend Google Drive tối ưu (`cli` trên cloud VM hoặc `api` OAuth 2.0 trên máy cá nhân)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from storage_suite.core.config import drive_backend_preference
from storage_suite.core.drive_api import GoogleDriveAPIClient, auth_status, is_google_api_installed
from storage_suite.core.drive_base import DriveError, DriveProtocol
from storage_suite.core.drive_cli import GDriveCLIClient, find_gdrive_bin, is_gdrive_cli_available


def detect_drive_backends() -> Dict[str, Any]:
    """Chẩn đoán trạng thái sẵn sàng của cả hai backend Google Drive (`cli` và `api`)."""
    cli_ok = is_gdrive_cli_available()
    cli_bin = ""
    if cli_ok:
        try:
            cli_bin = find_gdrive_bin()
        except DriveError:
            cli_ok = False
    api_info = auth_status()
    pref = drive_backend_preference()
    selected = "none"
    if pref == "cli" and cli_ok:
        selected = "cli"
    elif pref == "api" and api_info["libs_installed"]:
        selected = "api"
    elif cli_ok:
        selected = "cli"
    elif api_info["authenticated"]:
        selected = "api"
    elif api_info["libs_installed"]:
        selected = "api"
    return {
        "preference": pref,
        "selected": selected,
        "cli": {"available": cli_ok, "bin": cli_bin},
        "api": api_info,
    }


def create_drive(backend: Optional[str] = None, **kwargs: Any) -> DriveProtocol:
    """Khởi tạo client Google Drive phù hợp (`auto` | `cli` | `api`)."""
    choice = (backend or drive_backend_preference() or "auto").strip().lower()
    if choice == "cli":
        return GDriveCLIClient(**kwargs)
    if choice == "api":
        return GoogleDriveAPIClient(**kwargs)
    if choice != "auto":
        raise DriveError(f"Backend Google Drive không hợp lệ: `{choice}` (chỉ hỗ trợ `auto`, `cli`, `api`).")

    if is_gdrive_cli_available():
        return GDriveCLIClient(**kwargs)
    if is_google_api_installed():
        return GoogleDriveAPIClient(**kwargs)
    raise DriveError(
        "Không tìm thấy backend Google Drive nào sẵn sàng.\n"
        "- Trên cloud VM: bảo đảm CLI `gdrive` nằm trong PATH hoặc đặt `GDRIVE_BIN`.\n"
        '- Trên máy cá nhân: cài `pip install "storage-management-suite[drive-api]"` và chạy `astorage auth login`.'
    )
