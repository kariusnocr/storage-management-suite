"""Ứng dụng Web Dashboard cục bộ (`kas ui`) — Karius Academic System (KAS) v1.0 (FastAPI + máy chủ thuần Python an toàn Smart App Control)."""

import argparse
import collections
import contextlib
import http.server
import io
import json
import os
import threading
import time
import urllib.parse
import uuid
import webbrowser
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from karius_academic_system import APP_NAME, APP_SHORT, __version__
from karius_academic_system import core as sc
from karius_academic_system.web import lifecycle as lc

_STATIC_DIR = Path(__file__).resolve().parent / "static"
_TASKS: Dict[str, Dict[str, Any]] = {}
_TASKS_LOCK = threading.Lock()
_ALLOWED_UI_COMMANDS = {"doctor", "kiem-tra", "bao-cao", "trung-lap", "danh-muc", "quet", "github"}


def _load_index_safe() -> Dict[str, Dict[str, Any]]:
    try:
        return sc.load_index(required=False)
    except Exception:
        return {}


_STATIC_MIME_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".ico": "image/x-icon",
    ".json": "application/json; charset=utf-8",
    ".webmanifest": "application/manifest+json; charset=utf-8",
}


def _render_index_html() -> str:
    html_path = _STATIC_DIR / "index.html"
    if not html_path.exists():
        return f"<h1>{APP_NAME} ({APP_SHORT}) v{__version__}</h1><p>Missing static/index.html</p>"
    return html_path.read_text(encoding="utf-8")


def _read_static_asset(rel_name: str) -> Optional[Tuple[bytes, str]]:
    """Đọc tệp tĩnh an toàn trong `web/static/` (chống path traversal tuyệt đối)."""
    clean = (rel_name or "").lstrip("/")
    if not clean or ".." in clean or "\\" in clean:
        return None
    try:
        base = _STATIC_DIR.resolve()
        target = (base / clean).resolve()
        if not target.is_file() or target.parent != base:
            return None
        mime = _STATIC_MIME_TYPES.get(target.suffix.lower())
        if not mime:
            return None
        return target.read_bytes(), mime
    except OSError:
        return None


def _api_android_info_data(port: int = 8765) -> Dict[str, Any]:
    from karius_academic_system.web import android_bridge

    return android_bridge.detect_android_environment(port=port)


def _api_android_init_vault_data(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    from karius_academic_system.web import android_bridge

    try:
        res = android_bridge.bootstrap_android_vault(
            preferred_dir=str(body.get("path") or "").strip(),
            vault_name=str(body.get("name") or "Kho Tài Liệu Android").strip() or "Kho Tài Liệu Android",
            create_starter_files=bool(body.get("create_starter_files", True)),
            force_new=True,
        )
        return 200, res
    except Exception as exc:
        return 400, {"detail": str(exc)}


def _api_health_data() -> Dict[str, Any]:
    from karius_academic_system.web import android_bridge

    vc = sc.active_vault()
    flavor = android_bridge.detect_runtime_flavor()
    return {
        "status": "ok",
        "app_name": APP_NAME,
        "app_short": APP_SHORT,
        "version": __version__,
        "boot_id": lc.BOOT_ID,
        "pid": os.getpid(),
        "runtime_flavor": flavor,
        "is_android": flavor in {"chaquopy_apk", "termux"},
        "has_vault": sc.has_configured_vault(),
        "vault_slug": vc.slug if vc else sc.VAULT_SLUG,
        "root_name": sc.ROOT_NAME,
        "root_id": sc.ROOT_ID,
        "vault_mode": sc.effective_vault_mode(),
    }


def _api_vaults_list_data() -> Dict[str, Any]:
    reg = sc.get_vault_registry()
    act = sc.active_vault()
    act_slug = act.slug if act else reg.active_slug
    return {
        "active_slug": act_slug,
        "active": act.to_dict() if act else None,
        "registry_path": str(reg.path),
        "vaults": [v.to_dict() for v in reg.list_vaults()],
    }


def _api_vault_add_data(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    source = str(body.get("source") or "").strip()
    if not source:
        return 400, {"detail": "Vui lòng nhập đường dẫn thư mục cục bộ hoặc URL/Folder ID Google Drive."}
    slug = str(body.get("slug") or "").strip() or None
    name = str(body.get("name") or "").strip() or None
    backend = str(body.get("backend") or "auto").strip()
    mode = str(body.get("mode") or "auto").strip()
    activate = bool(body.get("activate", True))

    reg = sc.get_vault_registry()
    kind, norm_root = sc.detect_source_kind(source)
    if kind == "local" and not Path(norm_root).is_dir():
        return 400, {"detail": f"Thư mục cục bộ không tồn tại: `{norm_root}`"}
    if kind == "gdrive" and not name:
        try:
            drv = sc.create_backend(backend=None if backend == "auto" else backend)
            info = drv.info(norm_root)
            if info and info.get("name"):
                name = str(info["name"])
        except Exception:
            pass
    vc = reg.add_vault(source, slug=slug, name=name, backend=backend, mode=mode, activate=activate)
    if activate:
        sc.activate_vault(vc.slug, persist=True)
    return 200, {"ok": True, "vault": vc.to_dict(), "vaults": _api_vaults_list_data()}


def _api_vault_activate_data(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    slug = str(body.get("slug") or "").strip()
    if not slug:
        return 400, {"detail": "Thiếu mã kho `slug`."}
    persist = bool(body.get("persist", True))
    try:
        vc = sc.activate_vault(slug, persist=persist)
    except KeyError as exc:
        return 404, {"detail": str(exc)}
    return 200, {"ok": True, "vault": vc.to_dict(), "vaults": _api_vaults_list_data()}


def _api_vault_remove_data(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    slug = str(body.get("slug") or "").strip()
    if not slug:
        return 400, {"detail": "Thiếu mã kho `slug`."}
    reg = sc.get_vault_registry()
    if not reg.remove_vault(slug):
        return 404, {"detail": f"Không tìm thấy kho `{slug}`."}
    sc.reload_config()
    return 200, {"ok": True, "removed": slug, "vaults": _api_vaults_list_data()}


def _api_vault_init_structure_data(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    if not sc.ROOT_ID:
        return 400, {"detail": "Chưa chọn kho dữ liệu đang hoạt động."}
    confirm = bool(body.get("confirm", False))
    folders = [
        sc.TONG_QUAN_FOLDER,
        f"{sc.TONG_QUAN_FOLDER}/{sc.DANH_SACH_FOLDER}",
        f"{sc.TONG_QUAN_FOLDER}/[02] NHẬT KÍ",
        sc.QUARANTINE_FOLDER,
    ]
    if not confirm:
        return 200, {"dry_run": True, "root_name": sc.ROOT_NAME, "folders": folders}
    drv = sc.create_backend()
    tq_id = drv.ensure_folder(sc.TONG_QUAN_FOLDER, sc.ROOT_ID)
    ds_id = drv.ensure_folder(sc.DANH_SACH_FOLDER, tq_id)
    nk_id = drv.ensure_folder("[02] NHẬT KÍ", tq_id)
    qt_id = drv.ensure_folder(sc.QUARANTINE_FOLDER, sc.ROOT_ID)
    vc = sc.active_vault()
    if vc is not None:
        reg = sc.get_vault_registry()
        merged = dict(vc.known_ids)
        merged.update({
            sc.TONG_QUAN_FOLDER: tq_id,
            f"{sc.TONG_QUAN_FOLDER}/{sc.DANH_SACH_FOLDER}": ds_id,
            f"{sc.TONG_QUAN_FOLDER}/[02] NHẬT KÍ": nk_id,
            sc.QUARANTINE_FOLDER: qt_id,
        })
        reg.update_vault(vc.slug, known_ids=merged, mode="academic_v7", detected_mode="academic_v7")
        sc.reload_config(vc.slug)
    return 200, {"ok": True, "root_name": sc.ROOT_NAME, "created": folders}


def _api_overview_data() -> Dict[str, Any]:
    idx = _load_index_safe()
    with sc.StorageDB() as db:
        if not db.has_index() and idx:
            db.import_index_dict(idx)
        db_stats = db.stats_summary() if db.has_index() else {
            "total_folders": 0, "total_files": 0, "total_bytes": 0, "branches": {}, "db_size_bytes": 0, "last_import_utc": "",
        }
        undo_batches = db.list_undo_batches(limit=10)

    cat_plan = sc.build_catalog_migration_plan(idx) if idx else {"summary": {}}
    from karius_academic_system.ops.dedup import find_system_junk

    junk = find_system_junk(idx) if idx else []
    drive_backends = sc.detect_drive_backends()
    vc = sc.active_vault()

    branches_list = [
        {
            "name": b,
            "folders": st["folders"],
            "files": st["files"],
            "bytes": st["bytes"],
            "size_human": sc.human_size(st["bytes"]),
        }
        for b, st in sorted(db_stats.get("branches", {}).items())
    ]
    return {
        "app_name": APP_NAME,
        "app_short": APP_SHORT,
        "version": __version__,
        "has_vault": sc.has_configured_vault(),
        "active_vault": vc.to_dict() if vc else None,
        "vault_mode": sc.effective_vault_mode(),
        "root_name": sc.ROOT_NAME,
        "root_id": sc.ROOT_ID,
        "stats": {
            "folders": db_stats.get("total_folders", 0),
            "files": db_stats.get("total_files", 0),
            "bytes": db_stats.get("total_bytes", 0),
            "size_human": sc.human_size(db_stats.get("total_bytes", 0)),
            "db_size_human": sc.human_size(db_stats.get("db_size_bytes", 0)),
            "last_import_utc": db_stats.get("last_import_utc", ""),
        },
        "branches": branches_list,
        "catalog_v7": cat_plan.get("summary", {}),
        "system_junk_count": len(junk),
        "drive_backend": drive_backends,
        "recent_undo_batches": undo_batches,
    }


def _api_search_data(q: str, branch: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
    t0 = time.perf_counter()
    norm_branch = sc.normalize_branch(branch) if branch else None
    lim = max(1, min(200, int(limit)))
    with sc.StorageDB() as db:
        hits = db.search_fts(q, branch=norm_branch, limit=lim)
    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
    for h in hits:
        h["size_human"] = sc.human_size(h.get("size", 0))
        h["url"] = sc.drive_url(h["id"], h.get("mime_type", ""))
    return {"query": q, "elapsed_ms": elapsed_ms, "count": len(hits), "results": hits}


def _api_explorer_list_data(
    path: str = "",
    sort_by: str = "name",
    order: str = "asc",
    filter_q: str = "",
) -> Tuple[int, Dict[str, Any]]:
    from karius_academic_system.ops import explorer

    try:
        return 200, explorer.browse_folder(path, sort_by=sort_by, order=order, filter_q=filter_q)
    except Exception as exc:
        return explorer.safe_error_status(exc), {"detail": str(exc)}


def _api_explorer_tree_data(path: str = "") -> Tuple[int, Dict[str, Any]]:
    from karius_academic_system.ops import explorer

    try:
        return 200, explorer.list_folder_children_tree(path)
    except Exception as exc:
        return explorer.safe_error_status(exc), {"detail": str(exc)}


def _api_explorer_preview_data(
    item_id: str = "",
    path: str = "",
    fetch_drive: bool = False,
) -> Tuple[int, Dict[str, Any]]:
    from karius_academic_system.ops import explorer

    try:
        return 200, explorer.preview_item(item_id=item_id, path=path, fetch_drive=fetch_drive)
    except Exception as exc:
        return explorer.safe_error_status(exc), {"detail": str(exc)}


def _api_explorer_open_os_data(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    from karius_academic_system.ops import explorer

    try:
        return 200, explorer.open_in_os(
            item_id=str(body.get("id") or ""),
            path=str(body.get("path") or ""),
            reveal=bool(body.get("reveal", False)),
        )
    except Exception as exc:
        return explorer.safe_error_status(exc), {"detail": str(exc)}


def _parse_byte_range(range_header: str, total_size: int) -> Optional[Tuple[int, int]]:
    """Phân tích tiêu đề HTTP `Range: bytes=start-end` phục vụ phát audio/video/PDF mượt."""
    if not range_header or total_size <= 0:
        return None
    raw = range_header.strip()
    if not raw.lower().startswith("bytes="):
        return None
    spec = raw[6:].split(",", 1)[0].strip()
    if "-" not in spec:
        return None
    s_part, e_part = spec.split("-", 1)
    try:
        if not s_part:
            length = int(e_part)
            if length <= 0:
                return None
            start = max(0, total_size - length)
            end = total_size - 1
        else:
            start = int(s_part)
            end = int(e_part) if e_part else (total_size - 1)
        if start < 0 or start >= total_size or end < start:
            return None
        return start, min(end, total_size - 1)
    except ValueError:
        return None


def _safe_raw_headers(filename: str, mime: str) -> List[Tuple[str, str]]:
    encoded_name = urllib.parse.quote(filename, safe="")
    hdrs: List[Tuple[str, str]] = [
        ("X-Content-Type-Options", "nosniff"),
        ("Accept-Ranges", "bytes"),
        ("Content-Disposition", f"inline; filename*=UTF-8''{encoded_name}"),
    ]
    if "svg" in mime.lower():
        hdrs.append(("Content-Security-Policy", "sandbox; default-src 'none'"))
    return hdrs


def _api_audit_data(branch: Optional[str] = None, limit: int = 100) -> Dict[str, Any]:
    from karius_academic_system.ops.auditor import audit

    idx = _load_index_safe()
    norm_branch = sc.normalize_branch(branch) if branch else None
    if norm_branch == sc.ROOT_NAME:
        norm_branch = None
    lim = max(1, min(500, int(limit)))
    issues = audit(idx, norm_branch, check_structure=True) if idx else []
    by_sev = collections.Counter(i[0] for i in issues)
    by_code = collections.Counter((i[0], i[1]) for i in issues)
    return {
        "vault_mode": sc.effective_vault_mode(),
        "total": len(issues),
        "by_severity": dict(by_sev),
        "by_code": [{"severity": s, "code": c, "count": n} for (s, c), n in by_code.most_common()],
        "items": [
            {
                "severity": i[0],
                "code": i[1],
                "parent_path": i[2],
                "name": i[3],
                "id": i[4],
                "type": i[5],
                "description": i[6],
                "suggestion": i[7],
                "url": sc.drive_url(i[4], sc.FOLDER_MIME if i[5] == "Thư mục" else ""),
            }
            for i in issues[:lim]
        ],
    }


def _api_catalog_plan_data(mode: str = "smart", branch: Optional[str] = None, limit: int = 100) -> Dict[str, Any]:
    eff_mode = mode if mode in {"smart", "full"} else "smart"
    idx = _load_index_safe()
    norm_branch = sc.normalize_branch(branch) if branch else None
    if norm_branch == sc.ROOT_NAME:
        norm_branch = None
    lim = max(1, min(500, int(limit)))
    plan = sc.build_catalog_migration_plan(idx, branch=norm_branch, policy={"mode": eff_mode}) if idx else {
        "summary": {}, "renames": [], "prunes": [], "missing": [],
    }
    return {
        "mode": eff_mode,
        "summary": plan["summary"],
        "renames": plan["renames"][:lim],
        "prunes": plan["prunes"][:lim],
        "missing": plan["missing"][:lim],
    }


def _api_catalog_execute_data(
    mode: str = "smart",
    branch: Optional[str] = None,
    apply_prunes: bool = True,
    confirm: bool = False,
) -> Dict[str, Any]:
    idx = _load_index_safe()
    norm_branch = sc.normalize_branch(branch) if branch else None
    if norm_branch == sc.ROOT_NAME:
        norm_branch = None
    plan = sc.build_catalog_migration_plan(idx, branch=norm_branch, policy={"mode": mode})
    if not confirm:
        return {"dry_run": True, "summary": plan["summary"]}
    drive = sc.create_backend()
    with sc.StorageDB() as db:
        res = sc.apply_catalog_migration_plan(
            drive, plan, execute=True, apply_prunes=apply_prunes, db=db, index=idx
        )
    if res.get("index_updated"):
        sc.save_index(idx)
    return res


def _api_junk_data(branch: Optional[str] = None, limit: int = 100) -> Dict[str, Any]:
    from karius_academic_system.ops.dedup import find_system_junk

    idx = _load_index_safe()
    norm_branch = sc.normalize_branch(branch) if branch else None
    lim = max(1, min(500, int(limit)))
    items = find_system_junk(idx, None if norm_branch == sc.ROOT_NAME else norm_branch) if idx else []
    return {"count": len(items), "items": items[:lim]}


def _api_doctor_data() -> Dict[str, Any]:
    from karius_academic_system.ops.doctor import run_doctor

    return run_doctor()


def _api_setup_plan_data() -> Dict[str, Any]:
    from karius_academic_system.ops.setup_tools import build_setup_plan

    return build_setup_plan()


def _api_setup_run_data(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    from karius_academic_system.ops.setup_tools import start_setup_job

    scope = str(body.get("scope") or "all").strip().lower()
    do_py = scope in {"all", "python"} or bool(body.get("install_python", False))
    do_tools = scope in {"all", "tools"} or bool(body.get("install_tools", False))
    do_ocr = scope in {"all", "ocr", "ocr_data"} or bool(body.get("install_ocr_data", False))
    if not (do_py or do_tools or do_ocr):
        do_py = do_tools = do_ocr = True
    return start_setup_job(
        install_python=do_py,
        install_tools=do_tools,
        install_ocr_data=do_ocr,
        include_pywebview=bool(body.get("include_pywebview", False)),
        dry_run=bool(body.get("dry_run", False)),
    )


def _api_setup_job_data(job_id: str) -> Tuple[int, Dict[str, Any]]:
    from karius_academic_system.ops.setup_tools import get_setup_job

    job = get_setup_job(job_id)
    if not job:
        return 404, {"detail": "Không tìm thấy tiến trình cài đặt."}
    return 200, job


def _api_uninstall_plan_data(
    remove_config: bool = False,
    remove_data: bool = False,
    remove_tools: bool = False,
) -> Dict[str, Any]:
    from karius_academic_system.ops.uninstaller import inspect_installation

    return inspect_installation(
        remove_config=remove_config,
        remove_data=remove_data,
        remove_tools=remove_tools,
    )


def _api_uninstall_run_data(body: Dict[str, Any], *, port: int = 8765) -> Tuple[int, Dict[str, Any], bool]:
    """Trả về `(status_code, payload, should_shutdown_server)`."""
    from karius_academic_system.ops.uninstaller import inspect_installation, schedule_detached_self_uninstall

    rm_cfg = bool(body.get("remove_config", False) or body.get("purge", False))
    rm_data = bool(body.get("remove_data", False) or body.get("purge", False))
    dry_run = bool(body.get("dry_run", False))
    confirm = bool(body.get("confirm", False))

    plan = inspect_installation(remove_config=rm_cfg, remove_data=rm_data)
    if dry_run or not confirm:
        return 200, {
            "ok": True,
            "dry_run": True,
            "scheduled": False,
            "plan": plan,
            "message": "Chế độ xem trước (truyền confirm=true và dry_run=false để thực thi gỡ cài đặt thật).",
        }, False

    res = schedule_detached_self_uninstall(remove_config=rm_cfg, remove_data=rm_data, port=port)
    res["plan"] = plan
    return 200, res, True


def _api_update_check_data(force: bool = False) -> Dict[str, Any]:
    from karius_academic_system.ops.updater import check_for_updates, get_rollback_target_version

    info = check_for_updates(force=force)
    info["rollback_target"] = get_rollback_target_version()
    return info


def _api_update_apply_data(
    body: Dict[str, Any],
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    stdlib: bool = True,
    shutdown_cb: Optional[Callable[[], None]] = None,
) -> Tuple[int, Dict[str, Any]]:
    from karius_academic_system.ops.updater import get_rollback_target_version, start_update_job

    target = str(body.get("target_version") or body.get("version") or "").strip()
    if bool(body.get("rollback", False)) and not target:
        target = get_rollback_target_version()
        if not target:
            return 400, {"detail": "Không tìm thấy phiên bản trước trong lịch sử cập nhật để quay về (Rollback)."}
    return start_update_job(
        target_version=target,
        force=bool(body.get("force", False)),
        dry_run=bool(body.get("dry_run", False)),
        auto_restart=bool(body.get("auto_restart", True)),
        host=host,
        port=port,
        stdlib=stdlib,
        reopen_window=(lc.get_runtime_ui_mode() == "pywebview"),
        shutdown_cb=shutdown_cb,
    )


def _api_update_job_data(job_id: str) -> Tuple[int, Dict[str, Any]]:
    from karius_academic_system.ops.updater import get_update_job

    job = get_update_job(job_id)
    if not job:
        return 404, {"detail": "Không tìm thấy tiến trình cập nhật."}
    return 200, job


def _api_update_skip_data(body: Dict[str, Any]) -> Dict[str, Any]:
    from karius_academic_system.ops.updater import skip_update_version

    return skip_update_version(str(body.get("version") or ""))


def _api_undo_list_data() -> Dict[str, Any]:
    with sc.StorageDB() as db:
        return {"batches": db.list_undo_batches(limit=30)}


def _api_undo_run_data(batch_id: str, execute: bool = False) -> Tuple[int, Dict[str, Any]]:
    drive = sc.create_backend() if execute else None
    with sc.StorageDB() as db:
        res = db.undo_batch(drive, batch_id, execute=execute)
    if not res.get("ok") and "Không tìm thấy" in str(res.get("error", "")):
        return 404, {"detail": res["error"]}
    return 200, res


def _api_task_run_data(command: str, args: Optional[List[str]] = None) -> Tuple[int, Dict[str, Any]]:
    if command not in _ALLOWED_UI_COMMANDS:
        return 400, {"detail": f"Lệnh `{command}` không được hỗ trợ chạy trực tiếp từ Web UI."}
    arg_list = [str(a) for a in (args or [])]
    tid = uuid.uuid4().hex[:10]
    rec: Dict[str, Any] = {
        "id": tid,
        "command": command,
        "args": arg_list,
        "status": "running",
        "returncode": None,
        "started_utc": sc.now_utc_iso(),
        "finished_utc": "",
        "output": "",
    }
    with _TASKS_LOCK:
        _TASKS[tid] = rec

    def _worker():
        from karius_academic_system.cli.pipelines import invoke_module_in_process

        buf = io.StringIO()
        rc = 0
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                rc = invoke_module_in_process(command, arg_list)
        except Exception as exc:
            buf.write(f"\n[LỖI] {exc}\n")
            rc = 1
        with _TASKS_LOCK:
            _TASKS[tid]["status"] = "done" if rc == 0 else "failed"
            _TASKS[tid]["returncode"] = rc
            _TASKS[tid]["finished_utc"] = sc.now_utc_iso()
            _TASKS[tid]["output"] = buf.getvalue()[-20_000:]

    threading.Thread(target=_worker, daemon=True).start()
    return 200, rec


def _api_task_status_data(task_id: str) -> Tuple[int, Dict[str, Any]]:
    with _TASKS_LOCK:
        rec = _TASKS.get(task_id)
    if not rec:
        return 404, {"detail": "Không tìm thấy tác vụ."}
    return 200, rec


def _api_rules_get_data() -> Dict[str, Any]:
    rules, source = sc.get_active_naming_rules()
    return {
        "source": source,
        "has_vault_override": sc.has_custom_naming_rules("vault"),
        "has_global_override": sc.has_custom_naming_rules("global"),
        "rules": rules.to_dict(),
        "presets": sc.NAMING_PRESETS,
        "folder_index_styles": sc.FOLDER_INDEX_STYLES,
        "folder_case_options": list(sc.FOLDER_CASE_OPTIONS),
        "file_case_options": list(sc.FILE_CASE_OPTIONS),
    }


def _api_rules_save_data(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    scope = "global" if str(body.get("scope") or "vault").strip().lower() == "global" else "vault"
    preset = str(body.get("preset") or "").strip()
    raw_rules = body.get("rules")
    if preset and not isinstance(raw_rules, dict):
        if preset not in sc.NAMING_PRESETS:
            return 400, {"detail": f"Preset không tồn tại: `{preset}`."}
        rules, saved = sc.apply_naming_preset(preset, scope=scope)
        return 200, {"ok": True, "scope": scope, "saved_path": str(saved), "data": _api_rules_get_data(), "rules": rules.to_dict()}
    if not isinstance(raw_rules, dict):
        return 400, {"detail": "Thiếu đối tượng `rules` hoặc tên `preset`."}
    rules = sc.NamingRuleSet.from_dict(raw_rules)
    saved = sc.save_naming_rules(rules, scope=scope)
    return 200, {"ok": True, "scope": scope, "saved_path": str(saved), "data": _api_rules_get_data(), "rules": rules.to_dict()}


def _api_rules_reset_data(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    scope = "global" if str(body.get("scope") or "vault").strip().lower() == "global" else "vault"
    removed = sc.reset_naming_rules(scope=scope)
    return 200, {"ok": True, "scope": scope, "removed": removed, "data": _api_rules_get_data()}


def _api_rules_preview_data(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    raw_names = body.get("names")
    if isinstance(raw_names, list):
        names = [str(x) for x in raw_names if str(x)]
    else:
        single = str(body.get("name") or "")
        names = [single] if single else []
    if not names:
        return 400, {"detail": "Vui lòng nhập ít nhất một tên tệp hoặc thư mục cần kiểm thử."}
    is_folder = bool(body.get("is_folder", False))
    raw_rules = body.get("rules")
    preset = str(body.get("preset") or "").strip()
    if isinstance(raw_rules, dict):
        rules = sc.NamingRuleSet.from_dict(raw_rules)
    elif preset and preset in sc.NAMING_PRESETS:
        rules = sc.preset_rules(preset)
    else:
        rules, _ = sc.get_active_naming_rules()
    return 200, {
        "ok": True,
        "preset": rules.preset,
        "results": [sc.preview_naming(nm, is_folder=is_folder, rules=rules) for nm in names[:50]],
    }


def _api_ai_config_get_data(port: int = 8765) -> Dict[str, Any]:
    from karius_academic_system.ai import AI_PROVIDERS, ai_config_path, generate_mcp_client_config, load_ai_config

    cfg = load_ai_config()
    return {
        "config_path": str(ai_config_path()),
        "config": cfg.masked_dict(),
        "providers": AI_PROVIDERS,
        "mcp": {
            "stdio_command": "kas mcp serve",
            "http_endpoint": f"http://127.0.0.1:{port}/api/mcp",
            "claude_desktop": generate_mcp_client_config(client="claude", http_port=port),
            "cursor_antigravity": generate_mcp_client_config(client="cursor", http_port=port),
            "http_client": generate_mcp_client_config(client="http", http_port=port),
        },
    }


def _api_ai_config_save_data(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    from karius_academic_system.ai import AI_PROVIDERS, load_ai_config, save_ai_config

    cfg = load_ai_config()
    if body.get("provider"):
        prov = str(body["provider"]).strip()
        if prov not in AI_PROVIDERS:
            return 400, {"detail": f"Provider không hỗ trợ: `{prov}`."}
        cfg.provider = prov
        if not body.get("base_url"):
            cfg.base_url = AI_PROVIDERS[prov]["default_base_url"]
        if not body.get("model"):
            cfg.model = AI_PROVIDERS[prov]["default_model"]
    if "base_url" in body and body["base_url"] is not None:
        cfg.base_url = str(body["base_url"]).strip().rstrip("/")
    if "model" in body and body["model"] is not None:
        cfg.model = str(body["model"]).strip()
    if body.get("clear_api_key"):
        cfg.api_key = ""
    elif body.get("api_key"):
        cfg.api_key = str(body["api_key"]).strip()
    if "system_prompt" in body and body["system_prompt"] is not None:
        cfg.system_prompt = str(body["system_prompt"])
    if "temperature" in body and body["temperature"] is not None:
        cfg.temperature = max(0.0, min(1.5, float(body["temperature"])))
    saved = save_ai_config(cfg)
    return 200, {"ok": True, "saved_path": str(saved), "config": cfg.masked_dict()}


def _api_ai_chat_data(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    from karius_academic_system.ai import chat_with_agent

    message = str(body.get("message") or "").strip()
    if not message:
        return 400, {"detail": "Vui lòng nhập nội dung câu hỏi cho Trợ Lý AI."}
    history = body.get("history") if isinstance(body.get("history"), list) else []
    try:
        res = chat_with_agent(message, history=history)
        return 200, res
    except Exception as exc:
        return 502, {"ok": False, "detail": str(exc)}


def _api_agent_tools_data() -> Dict[str, Any]:
    from karius_academic_system.ai import get_agent_tool_schemas, get_openai_tools_spec

    return {
        "app": f"{APP_NAME} ({APP_SHORT}) v{__version__}",
        "mcp_tools": get_agent_tool_schemas(),
        "openai_tools": get_openai_tools_spec(),
    }


def _api_agent_execute_data(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    from karius_academic_system.ai import execute_agent_tool

    tool_name = str(body.get("tool") or body.get("name") or "").strip()
    if not tool_name:
        return 400, {"detail": "Thiếu tên công cụ `tool`."}
    tool_args = body.get("arguments") if isinstance(body.get("arguments"), dict) else {}
    res = execute_agent_tool(tool_name, tool_args)
    return 200, {"ok": True, "tool": tool_name, "result": res}


def _api_mcp_rpc_data(body: Dict[str, Any]) -> Tuple[int, Any]:
    from karius_academic_system.ai import handle_mcp_jsonrpc

    resp = handle_mcp_jsonrpc(body)
    if resp is None:
        return 200, {"jsonrpc": "2.0", "ok": True}
    return 200, resp


# ==================== CÀI ĐẶT PHẦN MỀM ====================


def _api_settings_get_data() -> Dict[str, Any]:
    return {
        "settings": sc.load_app_settings().to_dict(),
        "paths": sc.get_system_paths_info(),
    }


def _api_settings_save_data(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    raw = body.get("settings") if isinstance(body.get("settings"), dict) else body
    cur = sc.load_app_settings().to_dict()
    cur.update({k: v for k, v in raw.items() if k in cur})
    st = sc.AppSettings.from_dict(cur)
    saved = sc.save_app_settings(st)
    return 200, {"ok": True, "saved_path": str(saved), "settings": st.to_dict(), "paths": sc.get_system_paths_info()}


def _api_settings_reset_data() -> Dict[str, Any]:
    st = sc.reset_app_settings()
    return {"ok": True, "settings": st.to_dict(), "paths": sc.get_system_paths_info()}


def _api_settings_check_update_data() -> Dict[str, Any]:
    return sc.check_latest_release(github_token=sc.get_saved_github_token())


def _api_settings_export_data() -> Dict[str, Any]:
    rules, _ = sc.get_active_naming_rules()
    return {
        "exported_utc": sc.now_utc_iso(),
        "version": __version__,
        "settings": sc.load_app_settings().to_dict(),
        "naming_rules": rules.to_dict(),
        "vaults": _api_vaults_list_data().get("vaults", []),
    }


def _api_settings_import_data(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    imported: List[str] = []
    if isinstance(body.get("settings"), dict):
        sc.save_app_settings(sc.AppSettings.from_dict(body["settings"]))
        imported.append("settings")
    if isinstance(body.get("naming_rules"), dict):
        sc.save_naming_rules(sc.NamingRuleSet.from_dict(body["naming_rules"]), scope="vault")
        imported.append("naming_rules")
    if not imported:
        return 400, {"detail": "Tệp JSON nhập vào không chứa mục `settings` hoặc `naming_rules` hợp lệ."}
    return 200, {"ok": True, "imported": imported, "data": _api_settings_get_data()}


# ==================== DÒNG LỆNH TÍCH HỢP (CONSOLE) ====================


def _api_console_history_data() -> Dict[str, Any]:
    from karius_academic_system.cli.console import QUICK_COMMANDS, load_command_history

    return {
        "history": list(reversed(load_command_history(limit=50))),
        "quick_commands": QUICK_COMMANDS,
    }


def _api_console_run_data(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    from karius_academic_system.cli.console import run_console_command_sync, start_console_job

    raw_cmd = str(body.get("command") or "").strip()
    if not raw_cmd:
        return 400, {"detail": "Vui lòng nhập lệnh KAS cần chạy."}
    if bool(body.get("sync", False)):
        res = run_console_command_sync(raw_cmd)
        return (200 if res.get("returncode") != 2 else 400), res
    return start_console_job(raw_cmd)


def _api_console_job_data(job_id: str) -> Tuple[int, Dict[str, Any]]:
    from karius_academic_system.cli.console import get_console_job

    job = get_console_job(job_id)
    if not job:
        return 404, {"detail": "Không tìm thấy phiên chạy lệnh."}
    return 200, job


def _api_console_clear_history_data() -> Dict[str, Any]:
    from karius_academic_system.cli.console import clear_command_history

    clear_command_history()
    return {"ok": True}


# ==================== TÀI KHOẢN & KẾT NỐI BÊN THỨ 3 ====================

_PUBLIC_API_PATHS = {
    "/api/health",
    "/api/account/status",
    "/api/account/login",
    "/api/account/register",
}


def _extract_session_token(cookie_header: str = "", header_token: str = "") -> str:
    if header_token:
        return header_token.strip()
    for part in (cookie_header or "").split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            if k.strip() == "kas_session":
                return v.strip()
    return ""


def _is_request_locked(path: str, session_token: str) -> bool:
    if not path.startswith("/api/") or path in _PUBLIC_API_PATHS:
        return False
    if not sc.is_app_lock_enabled():
        return False
    return sc.verify_session(session_token) is None


def _session_cookie_header(token: Optional[str]) -> str:
    if token:
        return f"kas_session={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=604800"
    return "kas_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"


def _api_account_register_data(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any], Optional[str]]:
    try:
        prof, token = sc.register_account(
            username=str(body.get("username") or ""),
            password=str(body.get("password") or ""),
            display_name=str(body.get("display_name") or ""),
            email=str(body.get("email") or ""),
            require_login=bool(body.get("require_login", False)),
        )
        return 200, {"ok": True, "account": prof, "status": sc.account_status(token)}, token
    except ValueError as exc:
        return 400, {"detail": str(exc)}, None


def _api_account_login_data(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any], Optional[str]]:
    ok, msg, token = sc.authenticate_account(
        username=str(body.get("username") or ""),
        password=str(body.get("password") or ""),
    )
    if not ok or not token:
        return 401, {"ok": False, "detail": msg}, None
    return 200, {"ok": True, "message": msg, "status": sc.account_status(token)}, token


def _api_account_logout_data(session_token: str) -> Tuple[int, Dict[str, Any]]:
    sc.destroy_session(session_token)
    return 200, {"ok": True, "status": sc.account_status(None)}


def _api_account_update_data(body: Dict[str, Any], session_token: str) -> Tuple[int, Dict[str, Any]]:
    try:
        prof = sc.update_account_profile(
            display_name=body.get("display_name") if "display_name" in body else None,
            email=body.get("email") if "email" in body else None,
            require_login=body.get("require_login") if "require_login" in body else None,
        )
        return 200, {"ok": True, "account": prof, "status": sc.account_status(session_token)}
    except ValueError as exc:
        return 400, {"detail": str(exc)}


def _api_account_password_data(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    try:
        sc.change_account_password(
            old_password=str(body.get("old_password") or ""),
            new_password=str(body.get("new_password") or ""),
        )
        return 200, {"ok": True, "message": "Đã đổi mật khẩu tài khoản KAS thành công."}
    except ValueError as exc:
        return 400, {"detail": str(exc)}


def _api_account_delete_data(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    try:
        removed = sc.delete_account(password=str(body.get("password") or ""))
        return 200, {"ok": True, "removed": removed, "status": sc.account_status(None)}
    except ValueError as exc:
        return 400, {"detail": str(exc)}


def _api_integrations_google_creds_data(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    try:
        res = sc.save_google_credentials_json(str(body.get("credentials_json") or body.get("path") or ""))
        res["integrations"] = sc.get_all_integrations_summary()
        return 200, res
    except ValueError as exc:
        return 400, {"detail": str(exc)}


def _api_integrations_google_login_data(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    res = sc.start_google_oauth_login_async(open_browser=bool(body.get("open_browser", True)))
    return (200 if res.get("ok") else 400), res


def _api_integrations_github_connect_data(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    try:
        gh = sc.connect_github_token(str(body.get("token") or ""), verify=bool(body.get("verify", True)))
        return 200, {"ok": True, "github": gh, "integrations": sc.get_all_integrations_summary()}
    except ValueError as exc:
        return 400, {"detail": str(exc)}


def _api_integrations_connector_add_data(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    try:
        items = sc.add_custom_connector(
            name=str(body.get("name") or ""),
            kind=str(body.get("kind") or "webhook"),
            endpoint_url=str(body.get("endpoint_url") or ""),
            api_key=str(body.get("api_key") or ""),
            notes=str(body.get("notes") or ""),
        )
        return 200, {"ok": True, "connectors": items}
    except ValueError as exc:
        return 400, {"detail": str(exc)}


def _api_integrations_connector_remove_data(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    items = sc.remove_custom_connector(str(body.get("name") or ""))
    return 200, {"ok": True, "connectors": items}


def create_stdlib_server(host: str = "127.0.0.1", port: int = 8765) -> http.server.ThreadingHTTPServer:
    """
    Khởi tạo máy chủ HTTP thuần thư viện chuẩn Python (`http.server.ThreadingHTTPServer`).
    Không nạp bất kỳ tệp `.pyd`/`.dll` ngoài nào — chạy hoàn hảo trên Windows 11 bật Smart App Control.
    """

    class _DashboardHandler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

        def _session_token(self) -> str:
            return _extract_session_token(
                cookie_header=str(self.headers.get("Cookie") or ""),
                header_token=str(self.headers.get("X-KAS-Session") or ""),
            )

        def _send_bytes(
            self,
            status: int,
            body: bytes,
            content_type: str,
            extra_headers: Optional[List[Tuple[str, str]]] = None,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for hk, hv in extra_headers or []:
                self.send_header(hk, hv)
            self.end_headers()
            self.wfile.write(body)

        def _send_json(
            self,
            status: int,
            payload: Any,
            extra_headers: Optional[List[Tuple[str, str]]] = None,
        ) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._send_bytes(status, data, "application/json; charset=utf-8", extra_headers=extra_headers)

        def _read_json_body(self) -> Dict[str, Any]:
            raw_len = int(self.headers.get("Content-Length") or "0")
            if raw_len <= 0:
                return {}
            raw = self.rfile.read(min(raw_len, 4 * 1024 * 1024))
            try:
                parsed = json.loads(raw.decode("utf-8"))
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            qs = urllib.parse.parse_qs(parsed.query)
            sess_tok = self._session_token()

            def _q1(key: str, default: Optional[str] = None) -> Optional[str]:
                vals = qs.get(key)
                return vals[0] if vals else default

            try:
                if path in {"/", "/index.html"}:
                    self._send_bytes(200, _render_index_html().encode("utf-8"), "text/html; charset=utf-8")
                    return
                if path == "/manifest.webmanifest":
                    asset = _read_static_asset("manifest.webmanifest")
                    if asset is None:
                        self._send_json(404, {"detail": "Không tìm thấy manifest.webmanifest"})
                        return
                    self._send_bytes(200, asset[0], asset[1])
                    return
                if path == "/sw.js":
                    asset = _read_static_asset("sw.js")
                    if asset is None:
                        self._send_json(404, {"detail": "Không tìm thấy sw.js"})
                        return
                    self._send_bytes(200, asset[0], asset[1])
                    return
                if path.startswith("/static/"):
                    asset = _read_static_asset(urllib.parse.unquote(path[len("/static/"):]))
                    if asset is None:
                        self._send_json(404, {"detail": f"Không tìm thấy tệp tĩnh: {path}"})
                        return
                    self._send_bytes(200, asset[0], asset[1])
                    return
                if path == "/api/health":
                    self._send_json(200, _api_health_data())
                    return
                if path == "/api/account/status":
                    self._send_json(200, sc.account_status(sess_tok))
                    return
                if _is_request_locked(path, sess_tok):
                    self._send_json(401, {"detail": "Phiên làm việc đang bị khóa. Vui lòng đăng nhập tài khoản KAS.", "locked": True})
                    return
                if path == "/api/android/info":
                    self._send_json(200, _api_android_info_data(port=int(self.server.server_address[1])))
                    return
                if path == "/api/settings":
                    self._send_json(200, _api_settings_get_data())
                    return
                if path == "/api/settings/check-update":
                    self._send_json(200, _api_settings_check_update_data())
                    return
                if path == "/api/settings/export":
                    self._send_json(200, _api_settings_export_data())
                    return
                if path == "/api/console/history":
                    self._send_json(200, _api_console_history_data())
                    return
                if path.startswith("/api/console/jobs/"):
                    jid = urllib.parse.unquote(path[len("/api/console/jobs/"):])
                    code, data = _api_console_job_data(jid)
                    self._send_json(code, data)
                    return
                if path == "/api/integrations":
                    self._send_json(200, sc.get_all_integrations_summary())
                    return
                if path == "/api/integrations/google/login-status":
                    self._send_json(200, sc.get_google_oauth_login_state())
                    return
                if path == "/api/vaults":
                    self._send_json(200, _api_vaults_list_data())
                    return
                if path == "/api/overview":
                    self._send_json(200, _api_overview_data())
                    return
                if path == "/api/rules":
                    self._send_json(200, _api_rules_get_data())
                    return
                if path == "/api/ai/config":
                    self._send_json(200, _api_ai_config_get_data(port=self.server.server_address[1]))
                    return
                if path == "/api/agent/tools":
                    self._send_json(200, _api_agent_tools_data())
                    return
                if path == "/api/search":
                    q = (_q1("q") or "").strip()
                    if not q:
                        self._send_json(422, {"detail": "Thiếu tham số truy vấn `q`."})
                        return
                    self._send_json(200, _api_search_data(q, branch=_q1("branch"), limit=int(_q1("limit", "50") or "50")))
                    return
                if path == "/api/explorer/list":
                    code, data = _api_explorer_list_data(
                        path=_q1("path", "") or "",
                        sort_by=_q1("sort", "name") or "name",
                        order=_q1("order", "asc") or "asc",
                        filter_q=_q1("q", "") or "",
                    )
                    self._send_json(code, data)
                    return
                if path == "/api/explorer/tree":
                    code, data = _api_explorer_tree_data(path=_q1("path", "") or "")
                    self._send_json(code, data)
                    return
                if path == "/api/explorer/preview":
                    fetch_drv = (_q1("fetch_drive", "false") or "false").lower() in {"1", "true", "yes"}
                    code, data = _api_explorer_preview_data(
                        item_id=_q1("id", "") or "",
                        path=_q1("path", "") or "",
                        fetch_drive=fetch_drv,
                    )
                    self._send_json(code, data)
                    return
                if path == "/api/explorer/raw":
                    from karius_academic_system.ops import explorer

                    try:
                        fpath, mime, dl_name = explorer.read_raw_local_file(
                            item_id=_q1("id", "") or "",
                            path=_q1("path", "") or "",
                        )
                    except Exception as exc:
                        self._send_json(explorer.safe_error_status(exc), {"detail": str(exc)})
                        return
                    total = fpath.stat().st_size
                    hdrs = _safe_raw_headers(dl_name, mime)
                    rng = _parse_byte_range(self.headers.get("Range", ""), total)
                    if rng is not None:
                        start, end = rng
                        length = end - start + 1
                        self.send_response(206)
                        self.send_header("Content-Type", mime)
                        self.send_header("Content-Length", str(length))
                        self.send_header("Content-Range", f"bytes {start}-{end}/{total}")
                        self.send_header("Cache-Control", "no-store")
                        for hk, hv in hdrs:
                            self.send_header(hk, hv)
                        self.end_headers()
                        with fpath.open("rb") as fh:
                            fh.seek(start)
                            remaining = length
                            while remaining > 0:
                                chunk = fh.read(min(65536, remaining))
                                if not chunk:
                                    break
                                self.wfile.write(chunk)
                                remaining -= len(chunk)
                        return
                    self.send_response(200)
                    self.send_header("Content-Type", mime)
                    self.send_header("Content-Length", str(total))
                    self.send_header("Cache-Control", "no-store")
                    for hk, hv in hdrs:
                        self.send_header(hk, hv)
                    self.end_headers()
                    with fpath.open("rb") as fh:
                        while True:
                            chunk = fh.read(65536)
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                    return
                if path == "/api/audit":
                    self._send_json(200, _api_audit_data(branch=_q1("branch"), limit=int(_q1("limit", "100") or "100")))
                    return
                if path == "/api/catalog-v7/plan":
                    self._send_json(
                        200,
                        _api_catalog_plan_data(
                            mode=_q1("mode", "smart") or "smart",
                            branch=_q1("branch"),
                            limit=int(_q1("limit", "100") or "100"),
                        ),
                    )
                    return
                if path == "/api/junk":
                    self._send_json(200, _api_junk_data(branch=_q1("branch"), limit=int(_q1("limit", "100") or "100")))
                    return
                if path == "/api/doctor":
                    self._send_json(200, _api_doctor_data())
                    return
                if path == "/api/setup/plan":
                    self._send_json(200, _api_setup_plan_data())
                    return
                if path.startswith("/api/setup/jobs/"):
                    jid = urllib.parse.unquote(path[len("/api/setup/jobs/"):])
                    code, data = _api_setup_job_data(jid)
                    self._send_json(code, data)
                    return
                if path == "/api/uninstall/plan":
                    rm_cfg = (_q1("remove_config", "false") or "false").lower() in {"1", "true", "yes"}
                    rm_data = (_q1("remove_data", "false") or "false").lower() in {"1", "true", "yes"}
                    rm_tools = (_q1("remove_tools", "false") or "false").lower() in {"1", "true", "yes"}
                    self._send_json(200, _api_uninstall_plan_data(remove_config=rm_cfg, remove_data=rm_data, remove_tools=rm_tools))
                    return
                if path == "/api/update/status":
                    self._send_json(200, _api_update_check_data(force=False))
                    return
                if path == "/api/update/check":
                    force_q = (_q1("force", "true") or "true").lower() in {"1", "true", "yes"}
                    self._send_json(200, _api_update_check_data(force=force_q))
                    return
                if path.startswith("/api/update/jobs/"):
                    jid = urllib.parse.unquote(path[len("/api/update/jobs/"):])
                    code, data = _api_update_job_data(jid)
                    self._send_json(code, data)
                    return
                if path == "/api/undo/batches":
                    self._send_json(200, _api_undo_list_data())
                    return
                if path.startswith("/api/tasks/"):
                    tid = urllib.parse.unquote(path[len("/api/tasks/"):])
                    code, data = _api_task_status_data(tid)
                    self._send_json(code, data)
                    return
                self._send_json(404, {"detail": f"Không tìm thấy đường dẫn: {path}"})
            except Exception as exc:
                self._send_json(500, {"detail": str(exc)})

        def do_POST(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            qs = urllib.parse.parse_qs(parsed.query)
            body = self._read_json_body()
            sess_tok = self._session_token()
            try:
                if path == "/api/account/register":
                    code, data, new_tok = _api_account_register_data(body)
                    hdrs = [("Set-Cookie", _session_cookie_header(new_tok))] if new_tok else None
                    self._send_json(code, data, extra_headers=hdrs)
                    return
                if path == "/api/account/login":
                    code, data, new_tok = _api_account_login_data(body)
                    hdrs = [("Set-Cookie", _session_cookie_header(new_tok))] if new_tok else None
                    self._send_json(code, data, extra_headers=hdrs)
                    return
                if _is_request_locked(path, sess_tok):
                    self._send_json(401, {"detail": "Phiên làm việc đang bị khóa. Vui lòng đăng nhập tài khoản KAS.", "locked": True})
                    return
                if path == "/api/account/logout":
                    code, data = _api_account_logout_data(sess_tok)
                    self._send_json(code, data, extra_headers=[("Set-Cookie", _session_cookie_header(None))])
                    return
                if path == "/api/account/update":
                    code, data = _api_account_update_data(body, sess_tok)
                    self._send_json(code, data)
                    return
                if path == "/api/account/password":
                    code, data = _api_account_password_data(body)
                    self._send_json(code, data)
                    return
                if path == "/api/account/delete":
                    code, data = _api_account_delete_data(body)
                    self._send_json(code, data, extra_headers=[("Set-Cookie", _session_cookie_header(None))])
                    return
                if path == "/api/integrations/google/credentials":
                    code, data = _api_integrations_google_creds_data(body)
                    self._send_json(code, data)
                    return
                if path == "/api/integrations/google/login":
                    code, data = _api_integrations_google_login_data(body)
                    self._send_json(code, data)
                    return
                if path == "/api/integrations/google/logout":
                    self._send_json(200, sc.disconnect_google_drive())
                    return
                if path == "/api/integrations/github/connect":
                    code, data = _api_integrations_github_connect_data(body)
                    self._send_json(code, data)
                    return
                if path == "/api/integrations/github/disconnect":
                    self._send_json(200, {"ok": True, "github": sc.disconnect_github()})
                    return
                if path == "/api/integrations/connectors/add":
                    code, data = _api_integrations_connector_add_data(body)
                    self._send_json(code, data)
                    return
                if path == "/api/integrations/connectors/remove":
                    code, data = _api_integrations_connector_remove_data(body)
                    self._send_json(code, data)
                    return
                if path == "/api/settings":
                    code, data = _api_settings_save_data(body)
                    self._send_json(code, data)
                    return
                if path == "/api/settings/reset":
                    self._send_json(200, _api_settings_reset_data())
                    return
                if path == "/api/settings/import":
                    code, data = _api_settings_import_data(body)
                    self._send_json(code, data)
                    return
                if path == "/api/console/run":
                    code, data = _api_console_run_data(body)
                    self._send_json(code, data)
                    return
                if path == "/api/console/history/clear":
                    self._send_json(200, _api_console_clear_history_data())
                    return
                if path == "/api/vaults/add":
                    code, data = _api_vault_add_data(body)
                    self._send_json(code, data)
                    return
                if path == "/api/vaults/activate":
                    code, data = _api_vault_activate_data(body)
                    self._send_json(code, data)
                    return
                if path == "/api/vaults/remove":
                    code, data = _api_vault_remove_data(body)
                    self._send_json(code, data)
                    return
                if path == "/api/vaults/init-structure":
                    code, data = _api_vault_init_structure_data(body)
                    self._send_json(code, data)
                    return
                if path == "/api/rules":
                    code, data = _api_rules_save_data(body)
                    self._send_json(code, data)
                    return
                if path == "/api/rules/reset":
                    code, data = _api_rules_reset_data(body)
                    self._send_json(code, data)
                    return
                if path == "/api/rules/preview":
                    code, data = _api_rules_preview_data(body)
                    self._send_json(code, data)
                    return
                if path == "/api/ai/config":
                    code, data = _api_ai_config_save_data(body)
                    self._send_json(code, data)
                    return
                if path == "/api/ai/chat":
                    code, data = _api_ai_chat_data(body)
                    self._send_json(code, data)
                    return
                if path == "/api/agent/execute":
                    code, data = _api_agent_execute_data(body)
                    self._send_json(code, data)
                    return
                if path == "/api/mcp":
                    code, data = _api_mcp_rpc_data(body)
                    self._send_json(code, data)
                    return
                if path == "/api/catalog-v7/execute":
                    res = _api_catalog_execute_data(
                        mode=str(body.get("mode", "smart")),
                        branch=body.get("branch"),
                        apply_prunes=bool(body.get("apply_prunes", True)),
                        confirm=bool(body.get("confirm", False)),
                    )
                    self._send_json(200, res)
                    return
                if path == "/api/explorer/open-os":
                    code, data = _api_explorer_open_os_data(body)
                    self._send_json(code, data)
                    return
                if path == "/api/tasks/run":
                    code, data = _api_task_run_data(str(body.get("command", "")), body.get("args"))
                    self._send_json(code, data)
                    return
                if path == "/api/setup/run":
                    code, data = _api_setup_run_data(body)
                    self._send_json(code, data)
                    return
                if path == "/api/uninstall/run":
                    srv_port = int(self.server.server_address[1])
                    code, data, should_stop = _api_uninstall_run_data(body, port=srv_port)
                    self._send_json(code, data)
                    if should_stop:
                        lc.trigger_graceful_shutdown(delay_sec=0.45, close_windows=True)
                    return
                if path == "/api/update/apply":
                    srv_host, srv_port = self.server.server_address[0], int(self.server.server_address[1])
                    code, data = _api_update_apply_data(
                        body,
                        host=str(srv_host),
                        port=srv_port,
                        stdlib=True,
                        shutdown_cb=lambda: lc.trigger_graceful_shutdown(
                            delay_sec=0.35,
                            close_windows=(lc.get_runtime_ui_mode() == "pywebview"),
                        ),
                    )
                    self._send_json(code, data)
                    return
                if path == "/api/update/skip":
                    self._send_json(200, _api_update_skip_data(body))
                    return
                if path.startswith("/api/undo/"):
                    bid = urllib.parse.unquote(path[len("/api/undo/"):])
                    ex_q = (qs.get("execute") or ["false"])[0].lower() in {"1", "true", "yes"}
                    code, data = _api_undo_run_data(bid, execute=ex_q or bool(body.get("execute", False)))
                    self._send_json(code, data)
                    return
                if path == "/api/android/init-vault":
                    code, data = _api_android_init_vault_data(body)
                    self._send_json(code, data)
                    return
                if path == "/api/shutdown":
                    self._send_json(200, {"ok": True, "closing": True, "message": "Đang tắt máy chủ cục bộ..."})
                    lc.trigger_graceful_shutdown(delay_sec=0.35, close_windows=True)
                    return
                self._send_json(404, {"detail": f"Không tìm thấy đường dẫn: {path}"})
            except Exception as exc:
                self._send_json(500, {"detail": str(exc)})

    http.server.ThreadingHTTPServer.allow_reuse_address = True
    httpd = http.server.ThreadingHTTPServer((host, port), _DashboardHandler)

    def _stop_this_httpd() -> None:
        try:
            httpd.shutdown()
            httpd.server_close()
        except Exception:
            pass

    lc.register_shutdown_hook(_stop_this_httpd)
    httpd._kas_stop_hook = _stop_this_httpd  # type: ignore[attr-defined]
    return httpd


def create_app():
    """Khởi tạo ứng dụng FastAPI phục vụ giao diện quản trị cục bộ `kas ui`."""
    try:
        from fastapi import Body, FastAPI, HTTPException, Query, Request
        from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
        from pydantic import BaseModel
    except (ImportError, OSError) as exc:
        raise RuntimeError(
            'Thiếu thư viện Web UI hoặc DLL bị chặn bởi Smart App Control. Dùng máy chủ thuần Python (`kas ui --stdlib`).'
        ) from exc

    app = FastAPI(
        title=f"{APP_NAME} ({APP_SHORT})",
        version=__version__,
        description="Hệ thống quản trị tri thức, đa kho dữ liệu, cài đặt, dòng lệnh, tài khoản, kết nối bên thứ 3 & AI/MCP Agent.",
    )

    @app.middleware("http")
    async def kas_auth_guard(request: Request, call_next):
        tok = _extract_session_token(
            cookie_header=request.headers.get("cookie", ""),
            header_token=request.headers.get("x-kas-session", ""),
        )
        if _is_request_locked(request.url.path, tok):
            return JSONResponse(
                {"detail": "Phiên làm việc đang bị khóa. Vui lòng đăng nhập tài khoản KAS.", "locked": True},
                status_code=401,
            )
        return await call_next(request)

    class VaultAddRequest(BaseModel):
        source: str
        slug: Optional[str] = None
        name: Optional[str] = None
        backend: str = "auto"
        mode: str = "auto"
        activate: bool = True

    class VaultSlugRequest(BaseModel):
        slug: str
        persist: bool = True

    class VaultInitRequest(BaseModel):
        confirm: bool = False

    class ExecuteCatalogRequest(BaseModel):
        mode: str = "smart"
        branch: Optional[str] = None
        apply_prunes: bool = True
        confirm: bool = False

    class TaskRequest(BaseModel):
        command: str
        args: List[str] = []

    def _req_tok(request: Request) -> str:
        return _extract_session_token(
            cookie_header=request.headers.get("cookie", ""),
            header_token=request.headers.get("x-kas-session", ""),
        )

    @app.get("/", response_class=HTMLResponse)
    def index_page():
        return HTMLResponse(_render_index_html())

    @app.get("/manifest.webmanifest")
    def pwa_manifest():
        asset = _read_static_asset("manifest.webmanifest")
        if asset is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy manifest.webmanifest")
        return Response(content=asset[0], media_type=asset[1], headers={"Cache-Control": "no-store"})

    @app.get("/sw.js")
    def pwa_service_worker():
        asset = _read_static_asset("sw.js")
        if asset is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy sw.js")
        return Response(
            content=asset[0],
            media_type=asset[1],
            headers={"Cache-Control": "no-store", "Service-Worker-Allowed": "/"},
        )

    @app.get("/static/{filename:path}")
    def static_asset(filename: str):
        asset = _read_static_asset(filename)
        if asset is None:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy tệp tĩnh: /static/{filename}")
        return Response(content=asset[0], media_type=asset[1], headers={"Cache-Control": "no-store"})

    @app.get("/api/health")
    def api_health() -> Dict[str, Any]:
        return _api_health_data()

    @app.get("/api/android/info")
    def api_android_info(request: Request) -> Dict[str, Any]:
        port = int(request.url.port or 8765)
        return _api_android_info_data(port=port)

    @app.post("/api/android/init-vault")
    def api_android_init_vault(body: Dict[str, Any] = Body(default={})):
        code, data = _api_android_init_vault_data(body)
        if code != 200:
            raise HTTPException(status_code=code, detail=data.get("detail", "Không thể khởi tạo kho Android"))
        return JSONResponse(data)

    # --- Account & 3rd-Party Integrations ---
    @app.get("/api/account/status")
    def api_account_status(request: Request) -> Dict[str, Any]:
        return sc.account_status(_req_tok(request))

    @app.post("/api/account/register")
    def api_account_register(body: Dict[str, Any] = Body(...)):
        code, data, new_tok = _api_account_register_data(body)
        if code != 200:
            raise HTTPException(status_code=code, detail=data.get("detail", "Lỗi đăng ký"))
        resp = JSONResponse(data)
        if new_tok:
            resp.headers["Set-Cookie"] = _session_cookie_header(new_tok)
        return resp

    @app.post("/api/account/login")
    def api_account_login(body: Dict[str, Any] = Body(...)):
        code, data, new_tok = _api_account_login_data(body)
        if code != 200:
            raise HTTPException(status_code=code, detail=data.get("detail", "Lỗi đăng nhập"))
        resp = JSONResponse(data)
        if new_tok:
            resp.headers["Set-Cookie"] = _session_cookie_header(new_tok)
        return resp

    @app.post("/api/account/logout")
    def api_account_logout(request: Request):
        _, data = _api_account_logout_data(_req_tok(request))
        resp = JSONResponse(data)
        resp.headers["Set-Cookie"] = _session_cookie_header(None)
        return resp

    @app.post("/api/account/update")
    def api_account_update(request: Request, body: Dict[str, Any] = Body(...)):
        code, data = _api_account_update_data(body, _req_tok(request))
        if code != 200:
            raise HTTPException(status_code=code, detail=data.get("detail", "Lỗi cập nhật tài khoản"))
        return JSONResponse(data)

    @app.post("/api/account/password")
    def api_account_password(body: Dict[str, Any] = Body(...)):
        code, data = _api_account_password_data(body)
        if code != 200:
            raise HTTPException(status_code=code, detail=data.get("detail", "Lỗi đổi mật khẩu"))
        return JSONResponse(data)

    @app.post("/api/account/delete")
    def api_account_delete(body: Dict[str, Any] = Body(default={})):
        code, data = _api_account_delete_data(body)
        if code != 200:
            raise HTTPException(status_code=code, detail=data.get("detail", "Lỗi xóa tài khoản"))
        resp = JSONResponse(data)
        resp.headers["Set-Cookie"] = _session_cookie_header(None)
        return resp

    @app.get("/api/integrations")
    def api_integrations_get() -> Dict[str, Any]:
        return sc.get_all_integrations_summary()

    @app.post("/api/integrations/google/credentials")
    def api_integrations_google_creds(body: Dict[str, Any] = Body(...)):
        code, data = _api_integrations_google_creds_data(body)
        if code != 200:
            raise HTTPException(status_code=code, detail=data.get("detail", "Lỗi lưu credentials"))
        return JSONResponse(data)

    @app.post("/api/integrations/google/login")
    def api_integrations_google_login(body: Dict[str, Any] = Body(default={})):
        code, data = _api_integrations_google_login_data(body)
        if code != 200:
            raise HTTPException(status_code=code, detail=data.get("message", "Lỗi khởi chạy OAuth"))
        return JSONResponse(data)

    @app.get("/api/integrations/google/login-status")
    def api_integrations_google_status() -> Dict[str, Any]:
        return sc.get_google_oauth_login_state()

    @app.post("/api/integrations/google/logout")
    def api_integrations_google_logout() -> Dict[str, Any]:
        return sc.disconnect_google_drive()

    @app.post("/api/integrations/github/connect")
    def api_integrations_github_connect(body: Dict[str, Any] = Body(...)):
        code, data = _api_integrations_github_connect_data(body)
        if code != 200:
            raise HTTPException(status_code=code, detail=data.get("detail", "Lỗi kết nối GitHub"))
        return JSONResponse(data)

    @app.post("/api/integrations/github/disconnect")
    def api_integrations_github_disconnect() -> Dict[str, Any]:
        return {"ok": True, "github": sc.disconnect_github()}

    @app.post("/api/integrations/connectors/add")
    def api_integrations_connector_add(body: Dict[str, Any] = Body(...)):
        code, data = _api_integrations_connector_add_data(body)
        if code != 200:
            raise HTTPException(status_code=code, detail=data.get("detail", "Lỗi thêm kết nối"))
        return JSONResponse(data)

    @app.post("/api/integrations/connectors/remove")
    def api_integrations_connector_remove(body: Dict[str, Any] = Body(...)):
        _, data = _api_integrations_connector_remove_data(body)
        return JSONResponse(data)

    # --- Settings ---
    @app.get("/api/settings")
    def api_settings_get() -> Dict[str, Any]:
        return _api_settings_get_data()

    @app.post("/api/settings")
    def api_settings_save(body: Dict[str, Any] = Body(...)):
        code, data = _api_settings_save_data(body)
        return JSONResponse(data, status_code=code)

    @app.post("/api/settings/reset")
    def api_settings_reset() -> Dict[str, Any]:
        return _api_settings_reset_data()

    @app.get("/api/settings/check-update")
    def api_settings_check_update() -> Dict[str, Any]:
        return _api_settings_check_update_data()

    @app.get("/api/settings/export")
    def api_settings_export() -> Dict[str, Any]:
        return _api_settings_export_data()

    @app.post("/api/settings/import")
    def api_settings_import(body: Dict[str, Any] = Body(...)):
        code, data = _api_settings_import_data(body)
        if code != 200:
            raise HTTPException(status_code=code, detail=data.get("detail", "Lỗi nhập cấu hình"))
        return JSONResponse(data)

    # --- Command Console ---
    @app.get("/api/console/history")
    def api_console_history() -> Dict[str, Any]:
        return _api_console_history_data()

    @app.post("/api/console/run")
    def api_console_run(body: Dict[str, Any] = Body(...)):
        code, data = _api_console_run_data(body)
        if code != 200:
            raise HTTPException(status_code=code, detail=data.get("detail", "Lệnh không hợp lệ"))
        return JSONResponse(data)

    @app.get("/api/console/jobs/{job_id}")
    def api_console_job(job_id: str):
        code, data = _api_console_job_data(job_id)
        if code != 200:
            raise HTTPException(status_code=code, detail=data.get("detail", "Không tìm thấy lệnh"))
        return JSONResponse(data)

    @app.post("/api/console/history/clear")
    def api_console_clear_history() -> Dict[str, Any]:
        return _api_console_clear_history_data()

    # --- Vaults / Rules / AI / MCP / Core Ops ---
    @app.get("/api/vaults")
    def api_vaults() -> Dict[str, Any]:
        return _api_vaults_list_data()

    @app.post("/api/vaults/add")
    def api_vault_add(req: VaultAddRequest):
        code, data = _api_vault_add_data(req.dict() if hasattr(req, "dict") else req.model_dump())
        if code != 200:
            raise HTTPException(status_code=code, detail=data.get("detail", "Lỗi thêm kho"))
        return JSONResponse(data)

    @app.post("/api/vaults/activate")
    def api_vault_activate(req: VaultSlugRequest):
        code, data = _api_vault_activate_data(req.dict() if hasattr(req, "dict") else req.model_dump())
        if code != 200:
            raise HTTPException(status_code=code, detail=data.get("detail", "Không tìm thấy kho"))
        return JSONResponse(data)

    @app.post("/api/vaults/remove")
    def api_vault_remove(req: VaultSlugRequest):
        code, data = _api_vault_remove_data(req.dict() if hasattr(req, "dict") else req.model_dump())
        if code != 200:
            raise HTTPException(status_code=code, detail=data.get("detail", "Không tìm thấy kho"))
        return JSONResponse(data)

    @app.post("/api/vaults/init-structure")
    def api_vault_init(req: VaultInitRequest):
        code, data = _api_vault_init_structure_data(req.dict() if hasattr(req, "dict") else req.model_dump())
        if code != 200:
            raise HTTPException(status_code=code, detail=data.get("detail", "Lỗi khởi tạo khung"))
        return JSONResponse(data)

    @app.get("/api/rules")
    def api_rules_get() -> Dict[str, Any]:
        return _api_rules_get_data()

    @app.post("/api/rules")
    def api_rules_save(body: Dict[str, Any] = Body(...)):
        code, data = _api_rules_save_data(body)
        if code != 200:
            raise HTTPException(status_code=code, detail=data.get("detail", "Lỗi lưu quy tắc"))
        return JSONResponse(data)

    @app.post("/api/rules/reset")
    def api_rules_reset(body: Dict[str, Any] = Body(default={})):
        code, data = _api_rules_reset_data(body)
        return JSONResponse(data, status_code=code)

    @app.post("/api/rules/preview")
    def api_rules_preview(body: Dict[str, Any] = Body(...)):
        code, data = _api_rules_preview_data(body)
        if code != 200:
            raise HTTPException(status_code=code, detail=data.get("detail", "Lỗi kiểm thử tên"))
        return JSONResponse(data)

    @app.get("/api/ai/config")
    def api_ai_config_get() -> Dict[str, Any]:
        return _api_ai_config_get_data()

    @app.post("/api/ai/config")
    def api_ai_config_save(body: Dict[str, Any] = Body(...)):
        code, data = _api_ai_config_save_data(body)
        if code != 200:
            raise HTTPException(status_code=code, detail=data.get("detail", "Lỗi lưu cấu hình AI"))
        return JSONResponse(data)

    @app.post("/api/ai/chat")
    def api_ai_chat(body: Dict[str, Any] = Body(...)):
        code, data = _api_ai_chat_data(body)
        if code != 200:
            raise HTTPException(status_code=code, detail=data.get("detail", "Lỗi phản hồi AI"))
        return JSONResponse(data)

    @app.get("/api/agent/tools")
    def api_agent_tools() -> Dict[str, Any]:
        return _api_agent_tools_data()

    @app.post("/api/agent/execute")
    def api_agent_execute(body: Dict[str, Any] = Body(...)):
        code, data = _api_agent_execute_data(body)
        if code != 200:
            raise HTTPException(status_code=code, detail=data.get("detail", "Lỗi gọi công cụ Agent"))
        return JSONResponse(data)

    @app.post("/api/mcp")
    def api_mcp_rpc(body: Dict[str, Any] = Body(...)):
        code, data = _api_mcp_rpc_data(body)
        return JSONResponse(data, status_code=code)

    @app.get("/api/overview")
    def api_overview() -> Dict[str, Any]:
        return _api_overview_data()

    @app.get("/api/search")
    def api_search(
        q: str = Query(..., min_length=1),
        branch: Optional[str] = None,
        limit: int = Query(50, ge=1, le=200),
    ) -> Dict[str, Any]:
        return _api_search_data(q, branch=branch, limit=limit)

    @app.get("/api/explorer/list")
    def api_explorer_list(
        path: str = "",
        sort: str = "name",
        order: str = "asc",
        q: str = "",
    ):
        code, data = _api_explorer_list_data(path=path, sort_by=sort, order=order, filter_q=q)
        if code != 200:
            raise HTTPException(status_code=code, detail=data.get("detail", "Lỗi duyệt thư mục"))
        return JSONResponse(data)

    @app.get("/api/explorer/tree")
    def api_explorer_tree(path: str = ""):
        code, data = _api_explorer_tree_data(path=path)
        if code != 200:
            raise HTTPException(status_code=code, detail=data.get("detail", "Lỗi tải cây thư mục"))
        return JSONResponse(data)

    @app.get("/api/explorer/preview")
    def api_explorer_preview(id: str = "", path: str = "", fetch_drive: bool = False):
        code, data = _api_explorer_preview_data(item_id=id, path=path, fetch_drive=fetch_drive)
        if code != 200:
            raise HTTPException(status_code=code, detail=data.get("detail", "Lỗi xem trước tệp"))
        return JSONResponse(data)

    @app.get("/api/explorer/raw")
    def api_explorer_raw(id: str = "", path: str = ""):
        from karius_academic_system.ops import explorer

        try:
            fpath, mime, dl_name = explorer.read_raw_local_file(item_id=id, path=path)
        except Exception as exc:
            raise HTTPException(status_code=explorer.safe_error_status(exc), detail=str(exc)) from exc
        headers = dict(_safe_raw_headers(dl_name, mime))
        headers["Cache-Control"] = "no-store"
        return FileResponse(path=str(fpath), media_type=mime, headers=headers)

    @app.post("/api/explorer/open-os")
    def api_explorer_open_os(body: Dict[str, Any] = Body(default={})):
        code, data = _api_explorer_open_os_data(body)
        if code != 200:
            raise HTTPException(status_code=code, detail=data.get("detail", "Không mở được trên hệ điều hành"))
        return JSONResponse(data)

    @app.get("/api/audit")
    def api_audit(branch: Optional[str] = None, limit: int = Query(100, ge=1, le=500)) -> Dict[str, Any]:
        return _api_audit_data(branch=branch, limit=limit)

    @app.get("/api/catalog-v7/plan")
    def api_catalog_plan(
        mode: str = Query("smart", pattern="^(smart|full)$"),
        branch: Optional[str] = None,
        limit: int = Query(100, ge=1, le=500),
    ) -> Dict[str, Any]:
        return _api_catalog_plan_data(mode=mode, branch=branch, limit=limit)

    @app.post("/api/catalog-v7/execute")
    def api_catalog_execute(req: ExecuteCatalogRequest) -> Dict[str, Any]:
        return _api_catalog_execute_data(
            mode=req.mode,
            branch=req.branch,
            apply_prunes=req.apply_prunes,
            confirm=req.confirm,
        )

    @app.get("/api/junk")
    def api_junk(branch: Optional[str] = None, limit: int = Query(100, ge=1, le=500)) -> Dict[str, Any]:
        return _api_junk_data(branch=branch, limit=limit)

    @app.get("/api/doctor")
    def api_doctor() -> Dict[str, Any]:
        return _api_doctor_data()

    @app.get("/api/setup/plan")
    def api_setup_plan() -> Dict[str, Any]:
        return _api_setup_plan_data()

    @app.post("/api/setup/run")
    def api_setup_run(body: Dict[str, Any] = Body(default={})):
        code, data = _api_setup_run_data(body)
        return JSONResponse(data, status_code=code)

    @app.get("/api/setup/jobs/{job_id}")
    def api_setup_job(job_id: str) -> Dict[str, Any]:
        code, data = _api_setup_job_data(job_id)
        if code != 200:
            raise HTTPException(status_code=code, detail=data.get("detail", "Không tìm thấy tiến trình cài đặt"))
        return data

    @app.get("/api/uninstall/plan")
    def api_uninstall_plan(
        remove_config: bool = False,
        remove_data: bool = False,
        remove_tools: bool = False,
    ) -> Dict[str, Any]:
        return _api_uninstall_plan_data(
            remove_config=remove_config,
            remove_data=remove_data,
            remove_tools=remove_tools,
        )

    @app.post("/api/uninstall/run")
    def api_uninstall_run(request: Request, body: Dict[str, Any] = Body(default={})):
        port = int(request.url.port or 8765)
        code, data, should_stop = _api_uninstall_run_data(body, port=port)
        if should_stop:
            lc.trigger_graceful_shutdown(delay_sec=0.45, close_windows=True)
        return JSONResponse(data, status_code=code)

    @app.get("/api/update/status")
    def api_update_status() -> Dict[str, Any]:
        return _api_update_check_data(force=False)

    @app.get("/api/update/check")
    def api_update_check(force: bool = True) -> Dict[str, Any]:
        return _api_update_check_data(force=force)

    @app.post("/api/update/apply")
    def api_update_apply(request: Request, body: Dict[str, Any] = Body(default={})):
        host = request.url.hostname or "127.0.0.1"
        port = int(request.url.port or 8765)
        code, data = _api_update_apply_data(
            body,
            host=host,
            port=port,
            stdlib=False,
            shutdown_cb=lambda: lc.trigger_graceful_shutdown(
                delay_sec=0.35,
                close_windows=(lc.get_runtime_ui_mode() == "pywebview"),
            ),
        )
        if code != 200:
            raise HTTPException(status_code=code, detail=data.get("detail", "Lỗi khởi chạy cập nhật"))
        return JSONResponse(data)

    @app.get("/api/update/jobs/{job_id}")
    def api_update_job(job_id: str) -> Dict[str, Any]:
        code, data = _api_update_job_data(job_id)
        if code != 200:
            raise HTTPException(status_code=code, detail=data.get("detail", "Không tìm thấy tiến trình cập nhật"))
        return data

    @app.post("/api/update/skip")
    def api_update_skip(body: Dict[str, Any] = Body(default={})) -> Dict[str, Any]:
        return _api_update_skip_data(body)

    @app.get("/api/undo/batches")
    def api_undo_list() -> Dict[str, Any]:
        return _api_undo_list_data()

    @app.post("/api/undo/{batch_id}")
    def api_undo_run(batch_id: str, execute: bool = False) -> Dict[str, Any]:
        code, data = _api_undo_run_data(batch_id, execute=execute)
        if code != 200:
            raise HTTPException(status_code=code, detail=data.get("detail", "Lỗi hoàn tác"))
        return data

    @app.post("/api/tasks/run")
    def api_task_run(req: TaskRequest):
        code, data = _api_task_run_data(req.command, req.args)
        if code != 200:
            raise HTTPException(status_code=code, detail=data.get("detail", "Lệnh không hợp lệ"))
        return JSONResponse(data)

    @app.get("/api/tasks/{task_id}")
    def api_task_status(task_id: str) -> Dict[str, Any]:
        code, data = _api_task_status_data(task_id)
        if code != 200:
            raise HTTPException(status_code=code, detail=data.get("detail", "Không tìm thấy tác vụ"))
        return data

    @app.post("/api/shutdown")
    def api_shutdown() -> Dict[str, Any]:
        lc.trigger_graceful_shutdown(delay_sec=0.35, close_windows=True)
        return {"ok": True, "closing": True, "message": "Đang tắt máy chủ cục bộ..."}

    return app


def start_embedded_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    prefer_stdlib: bool = False,
) -> Tuple[threading.Thread, Callable[[], None], str]:
    """Khởi chạy máy chủ nền trả về `(thread, stop_fn, engine_name)` (tự dự phòng `--stdlib` trên Windows SAC)."""
    sc.refresh_system_path()
    if not prefer_stdlib:
        try:
            import uvicorn

            app = create_app()
            config = uvicorn.Config(app, host=host, port=port, log_level="warning")
            server = uvicorn.Server(config)

            def _stop_uvicorn() -> None:
                server.should_exit = True
                lc.unregister_shutdown_hook(_stop_uvicorn)

            app.state.stop_callback = _stop_uvicorn
            lc.register_shutdown_hook(_stop_uvicorn)
            th = threading.Thread(target=server.run, daemon=True)
            th.start()
            deadline = time.monotonic() + 5.0
            while not server.started and th.is_alive() and time.monotonic() < deadline:
                time.sleep(0.05)
            if server.started:
                return th, _stop_uvicorn, "fastapi+uvicorn"
            lc.unregister_shutdown_hook(_stop_uvicorn)
        except (ImportError, OSError, RuntimeError):
            pass

    httpd = create_stdlib_server(host=host, port=port)
    th = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True)
    th.start()

    def _stop() -> None:
        hook = getattr(httpd, "_kas_stop_hook", None)
        if callable(hook):
            lc.unregister_shutdown_hook(hook)
        try:
            httpd.shutdown()
            httpd.server_close()
        except Exception:
            pass

    return th, _stop, "stdlib-http"


def run_web_server(argv: Optional[List[str]] = None) -> int:
    st = sc.load_app_settings()
    ap = argparse.ArgumentParser(prog="kas ui", description=f"Khởi chạy giao diện Web Dashboard {APP_NAME} ({APP_SHORT}).")
    ap.add_argument("--host", default=st.ui_host, help=f"Địa chỉ lắng nghe (mặc định {st.ui_host})")
    ap.add_argument("--port", type=int, default=st.ui_port, help=f"Cổng HTTP (mặc định {st.ui_port})")
    ap.add_argument("--open", action="store_true", dest="open_browser", help="Tự mở trình duyệt sau khi khởi chạy")
    ap.add_argument("--stdlib", action="store_true", help="Dùng máy chủ HTTP thuần Python (không nạp .pyd/.dll ngoài)")
    args = ap.parse_args(argv)

    lc.set_process_exit_allowed(True)
    url = f"http://{args.host}:{args.port}"
    th, stop_fn, engine = start_embedded_server(host=args.host, port=args.port, prefer_stdlib=args.stdlib)
    lc.register_runtime(host=args.host, port=args.port, stdlib=(engine == "stdlib-http"), mode="ui")
    sc.log(f"{APP_NAME} ({APP_SHORT}) UI v{__version__} ({engine}) đang chạy tại {url}")
    try:
        from karius_academic_system.ops.updater import maybe_start_background_update_check

        maybe_start_background_update_check()
    except Exception:
        pass
    if args.open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        while th.is_alive():
            time.sleep(0.35)
    except KeyboardInterrupt:
        sc.log("Đang dừng máy chủ Web UI...")
        stop_fn()
    finally:
        lc.clear_runtime(only_if_self=True)
    return 0
