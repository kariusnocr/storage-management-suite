"""Bộ khởi tạo trình điều khiển lưu trữ đa nguồn cho Karius Academic System (KAS): LocalFS, Google Drive API OAuth 2.0 và gdrive CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from karius_academic_system.core import config as cfg
from karius_academic_system.core.drive_api import GoogleDriveAPIClient, auth_status, is_google_api_installed
from karius_academic_system.core.drive_base import DriveError, DriveProtocol
from karius_academic_system.core.drive_cli import GDriveCLIClient, find_gdrive_bin, is_gdrive_cli_available
from karius_academic_system.core.local_fs import LocalFSBackend


def detect_drive_backends() -> Dict[str, Any]:
    """Chẩn đoán trạng thái sẵn sàng của cả 3 trình điều khiển (`local`, `cli`, `api`)."""
    cli_ok = is_gdrive_cli_available()
    cli_bin = ""
    if cli_ok:
        try:
            cli_bin = find_gdrive_bin()
        except DriveError:
            cli_ok = False
    api_info = auth_status()
    pref = cfg.drive_backend_preference()
    vc = cfg.active_vault()
    local_root = ""
    if vc and vc.source_kind == "local":
        local_root = vc.root
    elif cfg.VAULT_SOURCE_KIND == "local" and cfg.VAULT_ROOT:
        local_root = cfg.VAULT_ROOT

    selected = "none"
    if pref == "local" or (vc and vc.source_kind == "local"):
        selected = "local"
    elif pref == "cli" and cli_ok:
        selected = "cli"
    elif pref == "api" and api_info["libs_installed"]:
        selected = "api"
    elif cli_ok:
        selected = "cli"
    elif api_info["authenticated"] or api_info["libs_installed"]:
        selected = "api"
    else:
        selected = "local"

    return {
        "preference": pref,
        "selected": selected,
        "local": {"available": True, "root": local_root},
        "cli": {"available": cli_ok, "bin": cli_bin},
        "api": api_info,
    }


def create_backend(
    backend: Optional[str] = None,
    *,
    root_dir: Optional[Path | str] = None,
    **kwargs: Any,
) -> DriveProtocol:
    """Khởi tạo trình điều khiển lưu trữ phù hợp với kho đang kích hoạt (`local` | `cli` | `api` | `auto`)."""
    vc = cfg.active_vault()
    choice = (backend or cfg.drive_backend_preference() or "auto").strip().lower()

    if choice == "local" or (root_dir is not None) or (choice == "auto" and vc and vc.source_kind == "local"):
        target = root_dir or (vc.root if vc and vc.source_kind == "local" else cfg.VAULT_ROOT)
        if not target:
            raise DriveError(
                "Chưa cấu hình thư mục kho cục bộ. Thêm kho bằng: `kas vault add <tên> --nguon <đường_dẫn>`"
            )
        return LocalFSBackend(target)

    if choice in {"cli", "gdrive-cli"}:
        return GDriveCLIClient(**kwargs)
    if choice in {"api", "gdrive-api"}:
        return GoogleDriveAPIClient(**kwargs)
    if choice != "auto":
        raise DriveError(f"Backend lưu trữ không hợp lệ: `{choice}` (hỗ trợ `auto`, `local`, `cli`, `api`).")

    if is_gdrive_cli_available():
        return GDriveCLIClient(**kwargs)
    if is_google_api_installed():
        return GoogleDriveAPIClient(**kwargs)
    raise DriveError(
        "Không tìm thấy trình điều khiển Google Drive nào sẵn sàng.\n"
        "- Với thư mục cục bộ: dùng `kas vault add <tên> --nguon <đường_dẫn_thư_mục>` (chạy 100% ngoại tuyến).\n"
        "- Với Google Drive trên máy cá nhân: cài `google-api-python-client google-auth-oauthlib` và chạy `kas auth login`.\n"
        "- Trên cloud VM: bảo đảm CLI `gdrive` nằm trong PATH hoặc đặt `GDRIVE_BIN`."
    )


create_drive = create_backend
