"""Quản lý cấu hình tập trung, hồ sơ đa kho (`profiles.toml`) và đường dẫn dữ liệu."""

from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path
from typing import Any, Dict, Optional

from storage_suite import __version__

FOLDER_MIME = "application/vnd.google-apps.folder"
SHORTCUT_MIME = "application/vnd.google-apps.shortcut"
SHEET_MIME = "application/vnd.google-apps.spreadsheet"
GOOGLE_NATIVE_MIMES = {
    "application/vnd.google-apps.document",
    SHEET_MIME,
    "application/vnd.google-apps.presentation",
    "application/vnd.google-apps.form",
    "application/vnd.google-apps.drawing",
    "application/vnd.google-apps.jam",
    "application/vnd.google-apps.site",
    "application/vnd.google-apps.map",
    "application/vnd.google-apps.colaboratory",
    SHORTCUT_MIME,
}

_BUNDLED_CONFIG_PATH = Path(__file__).resolve().parent.parent / "data" / "storage_config.json"


def _load_bundled_default() -> Dict[str, Any]:
    if _BUNDLED_CONFIG_PATH.exists():
        return json.loads(_BUNDLED_CONFIG_PATH.read_text(encoding="utf-8"))
    return {
        "version": __version__,
        "root_name": "[A] STORAGE",
        "root_id": "194HC3C2WC1BSzfK3cn_0_uUJ4vfDuBsr",
        "tong_quan_folder": "[00] TỔNG QUAN",
        "danh_sach_folder": "[01] DANH SÁCH",
        "quarantine_folder": "[07] KIỂM TRA",
        "github_repo": "kariusnocr/storage-management-suite",
        "github_default_branch": "main",
        "drive_backend": "auto",
        "known_ids": {},
        "master_sheet_id": "1BJoV-UtcoSEdjq1w5e0HmfibyTdvLEX8cy22jeKKnDc",
        "master_sheet_list_id": "1Pakm-B2FZFFNOsxct_aRmFm2DDQxsQiVsiwB_l2xQt4",
        "quarantine_subfolders": {},
        "catalog_policy": {"spec_version": "V7", "mode": "smart"},
        "tech_exception_path_markers": [],
        "title_exceptions": [],
        "lowercase_prefix_words": [],
        "acronyms_upper": {},
        "dedup": {"min_suspect_bytes": 1048576, "exclude_markers": []},
        "incremental_scan": {"full_scan_threshold_folders": 200, "lookback_overlap_seconds": 90, "stream_concurrency": 32},
    }


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = json.loads(json.dumps(base))
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def user_config_dir() -> Path:
    """Thư mục cấu hình người dùng (`~/.config/astorage` hoặc `ASTORAGE_CONFIG_DIR`)."""
    env = os.environ.get("ASTORAGE_CONFIG_DIR")
    p = Path(env).expanduser() if env else Path.home() / ".config" / "astorage"
    p.mkdir(parents=True, exist_ok=True)
    return p


def profiles_path() -> Path:
    return user_config_dir() / "profiles.toml"


def load_profile_override(profile_name: Optional[str] = None) -> Dict[str, Any]:
    """Đọc ghi đè hồ sơ từ `~/.config/astorage/profiles.toml` nếu tồn tại."""
    p = profiles_path()
    if not p.exists():
        return {}
    try:
        doc = tomllib.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    active = profile_name or os.environ.get("ASTORAGE_PROFILE") or doc.get("default_profile") or "default"
    profiles = doc.get("profiles") or {}
    prof = profiles.get(active)
    return dict(prof) if isinstance(prof, dict) else {}


def config_path() -> Path:
    env = os.environ.get("STORAGE_CONFIG_PATH")
    if env:
        return Path(env).expanduser()
    return _BUNDLED_CONFIG_PATH


def load_config(profile_name: Optional[str] = None) -> Dict[str, Any]:
    cfg = _load_bundled_default()
    p = config_path()
    if p.exists() and p.resolve() != _BUNDLED_CONFIG_PATH.resolve():
        try:
            override = json.loads(p.read_text(encoding="utf-8"))
            cfg = _deep_merge(cfg, override)
        except Exception:
            pass
    prof = load_profile_override(profile_name)
    if prof:
        cfg = _deep_merge(cfg, prof)
    return cfg


CONFIG: Dict[str, Any] = load_config()

ROOT_NAME: str = CONFIG["root_name"]
ROOT_ID: str = os.environ.get("STORAGE_ROOT_ID", CONFIG["root_id"])
KNOWN_IDS: Dict[str, str] = dict(CONFIG["known_ids"])
MASTER_SHEET_ID: str = CONFIG["master_sheet_id"]
MASTER_SHEET_LIST_ID: str = CONFIG["master_sheet_list_id"]
TONG_QUAN_FOLDER: str = CONFIG["tong_quan_folder"]
DANH_SACH_FOLDER: str = CONFIG.get("danh_sach_folder", "[01] DANH SÁCH")
DANH_SACH_PATH: str = f"{ROOT_NAME}/{TONG_QUAN_FOLDER}/{DANH_SACH_FOLDER}"
QUARANTINE_FOLDER: str = CONFIG.get("quarantine_folder", "[07] KIỂM TRA")
KIEM_TRA_FOLDER: str = QUARANTINE_FOLDER
QUARANTINE_MARKERS = ("[07] KIỂM TRA", "[99] KIỂM TRA")


def is_quarantine_path(path: str) -> bool:
    """Trả về True nếu đường dẫn thuộc khu vực kiểm tra/cách ly (`[07] KIỂM TRA` hoặc `[99] KIỂM TRA`)."""
    return any(m in path for m in QUARANTINE_MARKERS)


is_in_kiem_tra = is_quarantine_path


def is_in_danh_sach_tree(path: str) -> bool:
    """Trả về True nếu đường dẫn thuộc cây danh mục tập trung `[00] TỔNG QUAN/[01] DANH SÁCH`."""
    return path == DANH_SACH_PATH or path.startswith(DANH_SACH_PATH + "/")


def tong_quan_id() -> str:
    return os.environ.get(
        "STORAGE_TONG_QUAN_ID",
        KNOWN_IDS.get("[00] TỔNG QUAN", "1ZLU1RnH4PpJ--CXXPjrum7uxncbOttZU"),
    )


def danh_sach_id() -> str:
    return os.environ.get(
        "STORAGE_DANH_SACH_ID",
        KNOWN_IDS.get("[00] TỔNG QUAN/[01] DANH SÁCH", "1GqdqbI1yVPD3e-HAenW6WioSQZpPaRYz"),
    )


def nhat_ki_id() -> str:
    return os.environ.get(
        "STORAGE_NHAT_KI_ID",
        KNOWN_IDS.get("[00] TỔNG QUAN/[02] NHẬT KÍ", "10FI7CMFvGgM9i1rj4IkUFRESv5-ito2Y"),
    )


def quan_ly_id() -> str:
    return os.environ.get(
        "STORAGE_QUAN_LY_ID",
        KNOWN_IDS.get("[00] TỔNG QUAN/[03] QUẢN LÝ", "1dU9BqIFxdLyhsFzxZxOiKWVNHI0vk7W3"),
    )


def quarantine_root_id() -> str:
    return os.environ.get(
        "STORAGE_QUARANTINE_ID",
        KNOWN_IDS.get("[07] KIỂM TRA") or KNOWN_IDS.get("[99] KIỂM TRA", "1dpIWrMRwREX-bSt4k-PxSzVxbLrj3XLy"),
    )


def ingest_folder_id() -> str:
    return os.environ.get(
        "STORAGE_INGEST_ID",
        KNOWN_IDS.get("[07] KIỂM TRA/[04] NHẬP DỮ LIỆU", "1Xhgp46XpL3ng_l_d-_-wHb4S12DTuPri"),
    )


def data_dir() -> Path:
    """Thư mục dữ liệu cục bộ (SQLite DB, chỉ mục, cache, báo cáo). Ghi đè bằng `STORAGE_DATA_DIR`."""
    p = Path(os.environ.get("STORAGE_DATA_DIR", str(Path.home() / "storage_data"))).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p


def db_path() -> Path:
    """Đường dẫn cơ sở dữ liệu SQLite tập trung (`storage.db`)."""
    return data_dir() / "storage.db"


def index_path() -> Path:
    return data_dir() / "storage_index.json"


def snapshots_dir() -> Path:
    p = data_dir() / "snapshots"
    p.mkdir(parents=True, exist_ok=True)
    return p


def reports_dir() -> Path:
    p = data_dir() / "reports"
    p.mkdir(parents=True, exist_ok=True)
    return p


def runs_dir() -> Path:
    p = data_dir() / "runs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def tessdata_dir() -> Path:
    p = data_dir() / "tessdata"
    p.mkdir(parents=True, exist_ok=True)
    return p


def sheets_log_path() -> Path:
    return data_dir() / "uploaded_sheets_log.json"


def folder_metadata_path() -> Path:
    return data_dir() / "folder_metadata.json"


def shortcut_cache_path() -> Path:
    return data_dir() / "shortcut_cache.json"


def transfer_log_path() -> Path:
    return data_dir() / "transfer_log.json"


def ingest_log_path() -> Path:
    return data_dir() / "ingest_log.json"


def content_cache_dir() -> Path:
    p = data_dir() / "content_cache"
    (p / "records").mkdir(parents=True, exist_ok=True)
    (p / "text").mkdir(parents=True, exist_ok=True)
    return p


def content_rename_log_path() -> Path:
    return data_dir() / "content_rename_log.json"


def github_repo() -> str:
    return os.environ.get("STORAGE_GITHUB_REPO", CONFIG.get("github_repo", "kariusnocr/storage-management-suite"))


def github_sync_log_path() -> Path:
    return data_dir() / "github_sync_log.json"


def media_cache_dir(kind: str = "") -> Path:
    base = data_dir() / "media_cache"
    target = base / kind if kind in {"image", "audio", "video"} else base
    target.mkdir(parents=True, exist_ok=True)
    return target


def media_rename_log_path() -> Path:
    return data_dir() / "media_rename_log.json"


def oauth_credentials_path() -> Path:
    env = os.environ.get("ASTORAGE_OAUTH_CLIENT_SECRETS")
    if env:
        return Path(env).expanduser()
    return user_config_dir() / "credentials.json"


def oauth_token_path() -> Path:
    env = os.environ.get("ASTORAGE_OAUTH_TOKEN")
    if env:
        return Path(env).expanduser()
    return user_config_dir() / "token.json"


def drive_backend_preference() -> str:
    return os.environ.get("STORAGE_DRIVE_BACKEND", CONFIG.get("drive_backend", "auto")).strip().lower()


def catalog_policy() -> Dict[str, Any]:
    return dict(CONFIG.get("catalog_policy") or {})
