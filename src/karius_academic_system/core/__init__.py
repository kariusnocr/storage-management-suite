"""Thư viện lõi hợp nhất `karius_academic_system.core` (KAS v1.0.0) — xuất toàn bộ API lõi đa kho."""

from __future__ import annotations

from karius_academic_system import APP_NAME, APP_SHORT, __version__
from karius_academic_system.core import config as _cfg
from karius_academic_system.core.catalog_spec import (
    SHEET_PREFIX,
    TONG_QUAN_PREFIX,
    apply_catalog_migration_plan,
    audit_catalog_tree,
    build_catalog_migration_plan,
    compute_catalog_titles,
    evaluate_catalog_scope,
    is_excluded_catalog_folder,
    normalize_catalog_segment,
    normalize_catalog_title,
    normalize_sheet_title,
    should_have_catalog,
)
from karius_academic_system.core.config import (
    ACTIVE_VAULT,
    CONFIG,
    DANH_SACH_FOLDER,
    DANH_SACH_PATH,
    FOLDER_MIME,
    GOOGLE_NATIVE_MIMES,
    KIEM_TRA_FOLDER,
    KNOWN_IDS,
    MASTER_SHEET_ID,
    MASTER_SHEET_LIST_ID,
    QUARANTINE_FOLDER,
    QUARANTINE_MARKERS,
    ROOT_ID,
    ROOT_NAME,
    SHEET_MIME,
    SHORTCUT_MIME,
    TONG_QUAN_FOLDER,
    VAULT_MODE,
    VAULT_ROOT,
    VAULT_SLUG,
    VAULT_SOURCE_KIND,
    activate_vault,
    active_vault,
    catalog_policy,
    config_path,
    content_cache_dir,
    content_rename_log_path,
    danh_sach_id,
    data_dir,
    db_path,
    drive_backend_preference,
    effective_vault_mode,
    folder_metadata_path,
    get_vault_registry,
    github_repo,
    github_sync_log_path,
    has_configured_vault,
    index_path,
    ingest_folder_id,
    ingest_log_path,
    is_in_danh_sach_tree,
    is_in_kiem_tra,
    is_quarantine_path,
    load_config,
    media_cache_dir,
    media_rename_log_path,
    nhat_ki_id,
    oauth_credentials_path,
    oauth_token_path,
    profiles_path,
    quan_ly_id,
    quarantine_root_id,
    reload_config,
    reports_dir,
    runs_dir,
    sheets_log_path,
    shortcut_cache_path,
    snapshots_dir,
    sync_known_ids_from_index,
    tessdata_dir,
    tong_quan_id,
    transfer_log_path,
    user_config_dir,
    vaults_path,
)
from karius_academic_system.core.drive_api import (
    GoogleDriveAPIClient,
    auth_login,
    auth_logout,
    auth_status,
    is_google_api_installed,
)
from karius_academic_system.core.drive_base import DriveError, DriveProtocol, TokenBucket
from karius_academic_system.core.drive_cli import Drive, GDriveCLIClient, find_gdrive_bin, is_gdrive_cli_available
from karius_academic_system.core.drive_factory import create_backend, create_drive, detect_drive_backends
from karius_academic_system.core.local_fs import LocalFSBackend, local_path_from_id, make_local_id
from karius_academic_system.core.models import AuditFinding, CatalogDecision, PipelineStepResult, StorageItem, UndoAction
from karius_academic_system.core.naming import (
    ACRONYMS_UPPER,
    KNOWN_EXTS,
    LOWERCASE_PREFIX_WORDS,
    RE_DATE_PREFIX,
    RE_EXT,
    RE_FOLDER_V6,
    RE_NUM_PREFIX,
    RE_STT_PREFIX,
    SEVERITY_ORDER,
    TECH_EXCEPTION_PATH_MARKERS,
    TECH_FILE_RE,
    TITLE_EXCEPTIONS,
    catalog_folder_for_path,
    check_file_name,
    check_folder_name,
    extract_extra_info_v6,
    format_label,
    is_in_tong_quan,
    is_tech_exception,
    next_available_stt,
    normalize_branch,
    safe_fix_name,
    split_ext,
    title_case_vn,
)
from karius_academic_system.core.naming_rules import (
    FILE_CASE_OPTIONS,
    FOLDER_CASE_OPTIONS,
    FOLDER_INDEX_STYLES,
    NAMING_PRESETS,
    NamingRuleSet,
    apply_naming_preset,
    evaluate_name_with_rules,
    get_active_naming_rules,
    global_naming_rules_path,
    has_custom_naming_rules,
    normalize_name_with_rules,
    preset_rules,
    preview_naming,
    reset_naming_rules,
    save_naming_rules,
    vault_naming_rules_path,
)
from karius_academic_system.core.ocr import ocr_image_file, ocr_pdf_pages, ocr_pil_image, reset_ocr_cache, resolve_tesseract_lang
from karius_academic_system.core.utils import (
    _TZ_VN,
    confirm,
    drive_url,
    extract_drive_id,
    fmt_date_vn,
    fmt_datetime_vn,
    fmt_int,
    human_size,
    log,
    md_table,
    nfc,
    now_stamp,
    now_utc_iso,
    publish_file,
    read_json,
    sha256_file,
    strip_accents,
    summarize_owners,
    summarize_sharing,
    today_vn,
    write_csv,
    write_json,
)
from karius_academic_system.core.vaults import (
    VaultConfig,
    VaultRegistry,
    detect_source_kind,
    detect_vault_layout,
    extract_drive_folder_id,
    slugify_vault,
)
from karius_academic_system.store import Index, StorageDB, build_id_map, iter_items, load_index, save_index


def describe() -> str:
    backends = detect_drive_backends()
    vc = _cfg.active_vault()
    if vc is not None:
        vault_part = f"kho={vc.slug} ('{vc.name}' | {vc.source_kind}:{vc.root} | chế độ={vc.effective_mode()})"
    elif _cfg.ROOT_ID:
        vault_part = f"kho='{_cfg.ROOT_NAME}' ({_cfg.ROOT_ID})"
    else:
        vault_part = "chưa chọn kho (dùng `kas vault add` để kết nối bất kỳ kho nào)"
    return (
        f"{APP_NAME} ({APP_SHORT}) {__version__} | {vault_part} | "
        f"dữ liệu={data_dir()} | backend={backends['selected']}"
    )


__all__ = [name for name in globals() if not name.startswith("__")] + ["__version__"]
