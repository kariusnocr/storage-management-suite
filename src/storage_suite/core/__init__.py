"""Thư viện lõi hợp nhất `storage_suite.core` (v4.0.0) — xuất toàn bộ API lõi cho mọi mô-đun."""

from __future__ import annotations

from storage_suite import __version__
from storage_suite.core.catalog_spec import (
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
from storage_suite.core.config import (
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
    catalog_policy,
    config_path,
    content_cache_dir,
    content_rename_log_path,
    danh_sach_id,
    data_dir,
    db_path,
    drive_backend_preference,
    folder_metadata_path,
    github_repo,
    github_sync_log_path,
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
    reports_dir,
    runs_dir,
    sheets_log_path,
    shortcut_cache_path,
    snapshots_dir,
    tessdata_dir,
    tong_quan_id,
    transfer_log_path,
    user_config_dir,
)
from storage_suite.core.drive_api import (
    GoogleDriveAPIClient,
    auth_login,
    auth_logout,
    auth_status,
    is_google_api_installed,
)
from storage_suite.core.drive_base import DriveError, DriveProtocol, TokenBucket
from storage_suite.core.drive_cli import Drive, GDriveCLIClient, find_gdrive_bin, is_gdrive_cli_available
from storage_suite.core.drive_factory import create_drive, detect_drive_backends
from storage_suite.core.models import AuditFinding, CatalogDecision, PipelineStepResult, StorageItem, UndoAction
from storage_suite.core.naming import (
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
from storage_suite.core.ocr import ocr_image_file, ocr_pdf_pages, ocr_pil_image, reset_ocr_cache, resolve_tesseract_lang
from storage_suite.core.utils import (
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
from storage_suite.store import Index, StorageDB, build_id_map, iter_items, load_index, save_index


def describe() -> str:
    backends = detect_drive_backends()
    return (
        f"storage_suite {__version__} | gốc={ROOT_NAME} ({ROOT_ID}) | kiểm tra={QUARANTINE_FOLDER} ({quarantine_root_id()}) | "
        f"dữ liệu={data_dir()} | backend={backends['selected']}"
    )


__all__ = [name for name in globals() if not name.startswith("__")] + ["__version__"]
