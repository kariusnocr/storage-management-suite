"""Quản lý cấu hình tập trung, ngữ cảnh đa kho động (`vaults.toml`) và đường dẫn dữ liệu cho Karius Academic System (KAS)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from karius_academic_system import APP_NAME, APP_SHORT, __version__
from karius_academic_system.core.vaults import VaultConfig, VaultRegistry, detect_source_kind

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

_BUNDLED_CONFIG_PATH = Path(__file__).resolve().parent.parent / "data" / "kas_config.json"


def _load_bundled_default() -> Dict[str, Any]:
    if _BUNDLED_CONFIG_PATH.exists():
        return json.loads(_BUNDLED_CONFIG_PATH.read_text(encoding="utf-8"))
    return {
        "version": __version__,
        "app_name": APP_NAME,
        "app_short": APP_SHORT,
        "root_name": "",
        "root_id": "",
        "vault_mode": "auto",
        "tong_quan_folder": "[00] TỔNG QUAN",
        "danh_sach_folder": "[01] DANH SÁCH",
        "quarantine_folder": "[07] KIỂM TRA",
        "github_repo": "kariusnocr/storage-management-suite",
        "github_default_branch": "main",
        "drive_backend": "auto",
        "known_ids": {},
        "master_sheet_id": "",
        "master_sheet_list_id": "",
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
    """Thư mục cấu hình người dùng (`~/.config/kas` hoặc `KAS_CONFIG_DIR`)."""
    env = os.environ.get("KAS_CONFIG_DIR")
    p = Path(env).expanduser() if env else Path.home() / ".config" / "kas"
    p.mkdir(parents=True, exist_ok=True)
    return p


def vaults_path() -> Path:
    return user_config_dir() / "vaults.toml"


profiles_path = vaults_path


def config_path() -> Path:
    env = os.environ.get("KAS_CONFIG_PATH")
    if env:
        return Path(env).expanduser()
    return _BUNDLED_CONFIG_PATH


def get_vault_registry() -> VaultRegistry:
    return VaultRegistry(vaults_path())


def _resolve_active_vault(vault_slug: Optional[str] = None) -> Optional[VaultConfig]:
    reg = get_vault_registry()
    if vault_slug:
        vc = reg.get_vault(vault_slug)
        if vc is not None:
            return vc
    return reg.get_active_vault()


def load_config(vault_slug: Optional[str] = None) -> Dict[str, Any]:
    cfg = _load_bundled_default()
    p = config_path()
    if p.exists() and p.resolve() != _BUNDLED_CONFIG_PATH.resolve():
        try:
            override = json.loads(p.read_text(encoding="utf-8"))
            cfg = _deep_merge(cfg, override)
        except Exception:
            pass
    vc = _resolve_active_vault(vault_slug)
    if vc is not None:
        cfg["root_name"] = vc.name
        cfg["root_id"] = "loc:." if vc.source_kind == "local" else vc.root
        cfg["vault_slug"] = vc.slug
        cfg["vault_source_kind"] = vc.source_kind
        cfg["vault_root"] = vc.root
        cfg["vault_mode"] = vc.effective_mode()
        cfg["drive_backend"] = vc.effective_backend()
        cfg["tong_quan_folder"] = vc.tong_quan_folder
        cfg["danh_sach_folder"] = vc.danh_sach_folder
        cfg["quarantine_folder"] = vc.quarantine_folder
        cfg["known_ids"] = dict(vc.known_ids)
        cfg["master_sheet_id"] = vc.master_sheet_id
        cfg["master_sheet_list_id"] = vc.master_sheet_list_id
        if vc.topic_routes:
            cfg["topic_routes"] = {k: list(v) for k, v in vc.topic_routes.items()}
    # Ghi đè trực tiếp qua biến môi trường nếu có
    if os.environ.get("KAS_ROOT_NAME"):
        cfg["root_name"] = os.environ["KAS_ROOT_NAME"]
    if os.environ.get("KAS_ROOT_ID"):
        raw_root = os.environ["KAS_ROOT_ID"]
        kind, norm = detect_source_kind(raw_root)
        cfg["vault_source_kind"] = kind
        cfg["vault_root"] = norm
        cfg["root_id"] = "loc:." if kind == "local" else norm
    return cfg


# Ngữ cảnh kho hiện hành (có thể chuyển nóng qua `activate_vault()`)
ACTIVE_VAULT: Optional[VaultConfig] = None
CONFIG: Dict[str, Any] = {}
ROOT_NAME: str = ""
ROOT_ID: str = ""
VAULT_SLUG: str = ""
VAULT_SOURCE_KIND: str = ""
VAULT_ROOT: str = ""
VAULT_MODE: str = "auto"
KNOWN_IDS: Dict[str, str] = {}
MASTER_SHEET_ID: str = ""
MASTER_SHEET_LIST_ID: str = ""
TONG_QUAN_FOLDER: str = "[00] TỔNG QUAN"
DANH_SACH_FOLDER: str = "[01] DANH SÁCH"
DANH_SACH_PATH: str = ""
QUARANTINE_FOLDER: str = "[07] KIỂM TRA"
KIEM_TRA_FOLDER: str = "[07] KIỂM TRA"
QUARANTINE_MARKERS = ("[07] KIỂM TRA", "[99] KIỂM TRA")


def _sync_core_facade() -> None:
    """Đồng bộ lại các biến ngữ cảnh trên facade `karius_academic_system.core` khi đổi kho lúc chạy."""
    core_mod = sys.modules.get("karius_academic_system.core")
    if core_mod is None:
        return
    for attr in (
        "ACTIVE_VAULT",
        "CONFIG",
        "ROOT_NAME",
        "ROOT_ID",
        "VAULT_SLUG",
        "VAULT_SOURCE_KIND",
        "VAULT_ROOT",
        "VAULT_MODE",
        "KNOWN_IDS",
        "MASTER_SHEET_ID",
        "MASTER_SHEET_LIST_ID",
        "TONG_QUAN_FOLDER",
        "DANH_SACH_FOLDER",
        "DANH_SACH_PATH",
        "QUARANTINE_FOLDER",
        "KIEM_TRA_FOLDER",
        "QUARANTINE_MARKERS",
    ):
        setattr(core_mod, attr, globals()[attr])


def reload_config(vault_slug: Optional[str] = None) -> Dict[str, Any]:
    """Tải lại toàn bộ ngữ cảnh cấu hình theo kho được chọn (hỗ trợ hot-switch trong CLI & Web UI)."""
    global ACTIVE_VAULT, CONFIG, ROOT_NAME, ROOT_ID, VAULT_SLUG, VAULT_SOURCE_KIND, VAULT_ROOT
    global VAULT_MODE, KNOWN_IDS, MASTER_SHEET_ID, MASTER_SHEET_LIST_ID
    global TONG_QUAN_FOLDER, DANH_SACH_FOLDER, DANH_SACH_PATH, QUARANTINE_FOLDER, KIEM_TRA_FOLDER, QUARANTINE_MARKERS

    ACTIVE_VAULT = _resolve_active_vault(vault_slug)
    CONFIG = load_config(vault_slug)
    ROOT_NAME = str(CONFIG.get("root_name") or (ACTIVE_VAULT.name if ACTIVE_VAULT else "") or "KAS VAULT")
    ROOT_ID = str(CONFIG.get("root_id") or "")
    VAULT_SLUG = str(CONFIG.get("vault_slug") or (ACTIVE_VAULT.slug if ACTIVE_VAULT else ""))
    VAULT_SOURCE_KIND = str(CONFIG.get("vault_source_kind") or (ACTIVE_VAULT.source_kind if ACTIVE_VAULT else ""))
    VAULT_ROOT = str(CONFIG.get("vault_root") or (ACTIVE_VAULT.root if ACTIVE_VAULT else ""))
    VAULT_MODE = str(CONFIG.get("vault_mode") or "auto")
    KNOWN_IDS = dict(CONFIG.get("known_ids") or {})
    MASTER_SHEET_ID = str(CONFIG.get("master_sheet_id") or "")
    MASTER_SHEET_LIST_ID = str(CONFIG.get("master_sheet_list_id") or "")
    TONG_QUAN_FOLDER = str(CONFIG.get("tong_quan_folder") or "[00] TỔNG QUAN")
    DANH_SACH_FOLDER = str(CONFIG.get("danh_sach_folder") or "[01] DANH SÁCH")
    DANH_SACH_PATH = f"{ROOT_NAME}/{TONG_QUAN_FOLDER}/{DANH_SACH_FOLDER}"
    QUARANTINE_FOLDER = str(CONFIG.get("quarantine_folder") or "[07] KIỂM TRA")
    KIEM_TRA_FOLDER = QUARANTINE_FOLDER
    QUARANTINE_MARKERS = tuple(dict.fromkeys((QUARANTINE_FOLDER, "[07] KIỂM TRA", "[99] KIỂM TRA")))
    _sync_core_facade()
    return CONFIG


def activate_vault(slug: str, *, persist: bool = False) -> VaultConfig:
    """Chuyển ngữ cảnh hoạt động sang kho `slug` ngay lập tức (tùy chọn lưu làm kho mặc định)."""
    reg = get_vault_registry()
    vc = reg.set_active(slug) if persist else reg.get_vault(slug)
    if vc is None:
        raise KeyError(f"Không tìm thấy kho `{slug}`.")
    os.environ["KAS_VAULT"] = vc.slug
    reload_config(vc.slug)
    return vc


def has_configured_vault() -> bool:
    return bool(ROOT_ID or ACTIVE_VAULT)


def active_vault() -> Optional[VaultConfig]:
    return ACTIVE_VAULT


def effective_vault_mode() -> str:
    if ACTIVE_VAULT is not None:
        return ACTIVE_VAULT.effective_mode()
    return VAULT_MODE if VAULT_MODE in {"academic_v7", "general"} else "academic_v7"


def is_quarantine_path(path: str) -> bool:
    """Trả về True nếu đường dẫn thuộc khu vực kiểm tra/cách ly của kho hiện hành."""
    return any(m and (m in path) for m in QUARANTINE_MARKERS)


is_in_kiem_tra = is_quarantine_path


def is_in_danh_sach_tree(path: str) -> bool:
    """Trả về True nếu đường dẫn thuộc cây danh mục tập trung `[00] TỔNG QUAN/[01] DANH SÁCH`."""
    if not DANH_SACH_PATH:
        return False
    return path == DANH_SACH_PATH or path.startswith(DANH_SACH_PATH + "/")


def _lookup_known_id(rel_key: str, env_var: str = "") -> str:
    if env_var and os.environ.get(env_var):
        return os.environ[env_var]
    if rel_key in KNOWN_IDS and KNOWN_IDS[rel_key]:
        return KNOWN_IDS[rel_key]
    if VAULT_SOURCE_KIND == "local":
        return f"loc:{rel_key}"
    return ""


def tong_quan_id() -> str:
    return _lookup_known_id(TONG_QUAN_FOLDER, "KAS_TONG_QUAN_ID")


def danh_sach_id() -> str:
    return _lookup_known_id(f"{TONG_QUAN_FOLDER}/{DANH_SACH_FOLDER}", "KAS_DANH_SACH_ID")


def nhat_ki_id() -> str:
    return _lookup_known_id(f"{TONG_QUAN_FOLDER}/[02] NHẬT KÍ", "KAS_NHAT_KI_ID")


def quan_ly_id() -> str:
    return _lookup_known_id(f"{TONG_QUAN_FOLDER}/[03] QUẢN LÝ", "KAS_QUAN_LY_ID")


def quarantine_root_id() -> str:
    return (
        _lookup_known_id(QUARANTINE_FOLDER, "KAS_QUARANTINE_ID")
        or _lookup_known_id("[99] KIỂM TRA")
    )


def ingest_folder_id() -> str:
    return _lookup_known_id(f"{QUARANTINE_FOLDER}/[04] NHẬP DỮ LIỆU", "KAS_INGEST_ID")


def sync_known_ids_from_index(index: Dict[str, Any]) -> Dict[str, str]:
    """Tự động cập nhật `known_ids` & nhận diện bố cục kho (`academic_v7` vs `general`) từ chỉ mục vừa quét."""
    from karius_academic_system.core.vaults import detect_vault_layout

    if not index:
        return {}
    detected_mode, discovered = detect_vault_layout(
        index,
        root_name=ROOT_NAME,
        tong_quan_folder=TONG_QUAN_FOLDER,
        danh_sach_folder=DANH_SACH_FOLDER,
        quarantine_folder=QUARANTINE_FOLDER,
    )
    KNOWN_IDS.update(discovered)
    if ACTIVE_VAULT is not None:
        try:
            reg = get_vault_registry()
            if reg.get_vault(ACTIVE_VAULT.slug) is not None:
                merged_ids = dict(ACTIVE_VAULT.known_ids)
                merged_ids.update(discovered)
                reg.update_vault(
                    ACTIVE_VAULT.slug,
                    known_ids=merged_ids,
                    detected_mode=detected_mode,
                )
        except Exception:
            pass
    _sync_core_facade()
    return discovered


def _read_app_settings_raw() -> Dict[str, Any]:
    p = user_config_dir() / "app_settings.json"
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def data_dir() -> Path:
    """
    Thư mục dữ liệu cục bộ (SQLite DB, chỉ mục, cache, báo cáo) tách biệt riêng cho từng kho.
    Thứ tự ưu tiên: `KAS_DATA_DIR` > `app_settings.data_dir_override` > `~/.local/share/kas/vaults/<slug>` > `~/.local/share/kas/default`.
    """
    env = os.environ.get("KAS_DATA_DIR")
    if env:
        p = Path(env).expanduser()
        p.mkdir(parents=True, exist_ok=True)
        return p
    override_root = str(_read_app_settings_raw().get("data_dir_override") or "").strip()
    base = Path(override_root).expanduser() if override_root else (Path.home() / ".local" / "share" / "kas")
    if VAULT_SLUG:
        p = base / "vaults" / VAULT_SLUG
    else:
        p = base / "default"
    p.mkdir(parents=True, exist_ok=True)
    return p


def db_path() -> Path:
    """Đường dẫn cơ sở dữ liệu SQLite tập trung (`kas.db`)."""
    p = data_dir() / "kas.db"
    legacy = data_dir() / "storage.db"
    if not p.exists() and legacy.exists():
        return legacy
    return p


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
    env = os.environ.get("KAS_TESSDATA_DIR")
    if env:
        p = Path(env).expanduser()
        p.mkdir(parents=True, exist_ok=True)
        return p
    shared = Path.home() / ".local" / "share" / "kas" / "tessdata"
    vault_td = data_dir() / "tessdata"
    if (shared / "vie.traineddata").exists() or not (vault_td / "vie.traineddata").exists():
        shared.mkdir(parents=True, exist_ok=True)
        return shared
    return vault_td


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
    return os.environ.get("KAS_GITHUB_REPO", CONFIG.get("github_repo", "kariusnocr/storage-management-suite"))


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
    env = os.environ.get("KAS_OAUTH_CLIENT_SECRETS")
    if env:
        return Path(env).expanduser()
    return user_config_dir() / "credentials.json"


def oauth_token_path() -> Path:
    env = os.environ.get("KAS_OAUTH_TOKEN")
    if env:
        return Path(env).expanduser()
    return user_config_dir() / "token.json"


def drive_backend_preference() -> str:
    env = os.environ.get("KAS_BACKEND")
    if env:
        return env.strip().lower()
    pref = str(_read_app_settings_raw().get("drive_backend") or "").strip().lower()
    if pref and pref != "auto":
        return pref
    return str(CONFIG.get("drive_backend", "auto")).strip().lower()


def catalog_policy() -> Dict[str, Any]:
    return dict(CONFIG.get("catalog_policy") or {})


# Khởi nạp cấu hình lần đầu khi import
reload_config()
