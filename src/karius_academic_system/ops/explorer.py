"""Trình Duyệt Kho (Vault Explorer & Previewer) — Karius Academic System (KAS) v1.6.0.

Hỗ trợ di chuyển giữa các thư mục/tệp tin và xem trước trực tiếp (văn bản, mã nguồn, ảnh, PDF,
âm thanh, video, tài liệu DOCX/XLSX/PPTX/EPUB/ZIP...) trên cả:
- Kho cục bộ (`LocalFSBackend`): đọc trực tiếp thời gian thực + mở bằng ứng dụng hệ thống / Explorer.
- Kho Google Drive: duyệt tức thì (<15 ms) trên chỉ mục SQLite WAL + tải xem trước theo yêu cầu.
"""

from __future__ import annotations

import mimetypes
import os
import subprocess
import sys
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from karius_academic_system import core as sc
from karius_academic_system.core.drive_base import DriveError
from karius_academic_system.core.local_fs import LOCAL_ID_PREFIX, LocalFSBackend, local_path_from_id, make_local_id
from karius_academic_system.media import file_reader as fr

MAX_INLINE_TEXT_BYTES = 160_000
MAX_PREVIEW_TEXT_CHARS = 35_000
MAX_SHA256_BYTES = 25 * 1024 * 1024

_IMAGE_EXTS = {"png", "jpg", "jpeg", "webp", "gif", "bmp", "svg", "ico"}
_AUDIO_EXTS = {"mp3", "wav", "ogg", "m4a", "flac", "aac", "opus"}
_VIDEO_EXTS = {"mp4", "webm", "mov", "m4v", "ogv"}
_CODE_EXTS = {
    "py", "js", "ts", "jsx", "tsx", "html", "htm", "css", "scss", "json", "yaml", "yml",
    "toml", "xml", "sql", "sh", "bash", "ps1", "cmd", "bat", "c", "cpp", "h", "java",
    "go", "rs", "php", "rb", "r", "tex", "ini", "cfg", "env",
}
_TEXT_EXTS = {"txt", "md", "markdown", "csv", "tsv", "log", "rst", "rtf", "org"}
_OFFICE_EXTS = {"docx", "xlsx", "pptx", "doc", "xls", "ppt", "odt", "ods", "odp"}
_EBOOK_EXTS = {"epub", "mobi", "azw", "azw3", "opf", "prc", "djvu"}
_ARCHIVE_EXTS = {"zip", "rar", "7z", "tar", "gz", "bz2", "xz"}


def classify_item(name: str, mime_type: str = "", is_folder: bool = False) -> Tuple[str, str]:
    """Phân loại mục thành `(category, ext)` để hiển thị biểu tượng và chọn bộ xem trước."""
    if is_folder or mime_type == sc.FOLDER_MIME:
        return "folder", ""
    _, ext = sc.split_ext(name, mime_type)
    ext = ext.lower()
    if mime_type in sc.GOOGLE_NATIVE_MIMES:
        return "gdoc", ext
    if ext == "pdf" or mime_type == "application/pdf":
        return "pdf", "pdf"
    if ext in _IMAGE_EXTS or mime_type.startswith("image/"):
        return "image", ext
    if ext in _AUDIO_EXTS or mime_type.startswith("audio/"):
        return "audio", ext
    if ext in _VIDEO_EXTS or mime_type.startswith("video/"):
        return "video", ext
    if ext in _CODE_EXTS:
        return "code", ext
    if ext in _TEXT_EXTS or mime_type.startswith("text/"):
        return "text", ext
    if ext in _OFFICE_EXTS:
        return "office", ext
    if ext in _EBOOK_EXTS:
        return "ebook", ext
    if ext in _ARCHIVE_EXTS:
        return "archive", ext
    return "other", ext


def normalize_rel_path(raw_path: str, root_name: str = "") -> str:
    """Chuẩn hóa đường dẫn tương đối bên trong kho (chặn tuyệt đối `..` và hỗ trợ bỏ tiền tố `root_name`)."""
    txt = sc.nfc(str(raw_path or "")).replace("\\", "/").strip("/")
    if not txt or txt == ".":
        return ""
    rname = sc.nfc(root_name or sc.ROOT_NAME or "").strip("/")
    if rname:
        if txt == rname:
            return ""
        if txt.startswith(rname + "/"):
            txt = txt[len(rname) + 1 :]
    parts = [p for p in txt.split("/") if p and p != "."]
    if any(p == ".." for p in parts):
        raise ValueError(f"Đường dẫn không hợp lệ (chứa `..`): `{raw_path}`")
    return "/".join(parts)


def build_breadcrumbs(rel_path: str, root_name: str) -> List[Dict[str, str]]:
    crumbs = [{"name": root_name or "Kho gốc", "path": ""}]
    if not rel_path:
        return crumbs
    acc: List[str] = []
    for part in rel_path.split("/"):
        acc.append(part)
        crumbs.append({"name": part, "path": "/".join(acc)})
    return crumbs


def _is_active_local_vault() -> Tuple[bool, Optional[Path]]:
    vc = sc.active_vault()
    if vc is not None and vc.source_kind == "local":
        p = Path(vc.root).expanduser()
        if p.is_dir():
            return True, p.resolve()
    if sc.VAULT_SOURCE_KIND == "local" and sc.VAULT_ROOT:
        p = Path(sc.VAULT_ROOT).expanduser()
        if p.is_dir():
            return True, p.resolve()
    return False, None


def _ensure_db_populated(db: sc.StorageDB) -> bool:
    if db.has_index():
        return True
    try:
        idx = sc.load_index(required=False)
        if idx:
            db.import_index_dict(idx)
            return True
    except Exception:
        pass
    return False


def _sort_entries(entries: List[Dict[str, Any]], sort_by: str = "name", order: str = "asc") -> List[Dict[str, Any]]:
    reverse = str(order or "asc").lower() == "desc"
    key_name = str(sort_by or "name").lower()

    folders = [e for e in entries if e["is_folder"]]
    files = [e for e in entries if not e["is_folder"]]

    def _sort_key(item: Dict[str, Any]):
        if key_name == "size":
            return (int(item.get("size") or 0), sc.strip_accents(item["name"]).lower())
        if key_name in {"modified", "date", "time"}:
            return (str(item.get("modified_time") or ""), sc.strip_accents(item["name"]).lower())
        if key_name in {"type", "ext", "category"}:
            return (str(item.get("ext") or item.get("category") or ""), sc.strip_accents(item["name"]).lower())
        return (sc.strip_accents(item["name"]).lower(), item["name"].lower())

    folders.sort(key=_sort_key, reverse=reverse)
    files.sort(key=_sort_key, reverse=reverse)
    return folders + files


def _filter_entries(entries: List[Dict[str, Any]], filter_q: str) -> List[Dict[str, Any]]:
    q = sc.strip_accents(str(filter_q or "").strip()).lower()
    if not q:
        return entries
    return [
        e for e in entries
        if q in sc.strip_accents(e["name"]).lower() or q in str(e.get("ext") or "").lower()
    ]


def _quick_local_counts(folder: Path, limit: int = 500) -> Tuple[int, int]:
    cf = 0
    ci = 0
    try:
        for i, ch in enumerate(folder.iterdir()):
            if i >= limit:
                break
            try:
                if ch.is_dir():
                    cf += 1
                else:
                    ci += 1
            except OSError:
                continue
    except OSError:
        pass
    return cf, ci


def _browse_local_vault(
    root: Path,
    rel_path: str,
    root_name: str,
    *,
    sort_by: str = "name",
    order: str = "asc",
    filter_q: str = "",
) -> Dict[str, Any]:
    backend = LocalFSBackend(root)
    item_id = f"{LOCAL_ID_PREFIX}{rel_path}" if rel_path else backend.root_id
    target = backend.resolve_path(item_id)
    if not target.exists() or not target.is_dir():
        raise FileNotFoundError(f"Thư mục không tồn tại trong kho cục bộ: `{rel_path or '/'}`")

    entries: List[Dict[str, Any]] = []
    for raw in backend.ls(item_id):
        is_dir = raw.get("mimeType") == sc.FOLDER_MIME
        nm = sc.nfc(str(raw.get("name") or ""))
        child_rel = f"{rel_path}/{nm}" if rel_path else nm
        cat, ext = classify_item(nm, str(raw.get("mimeType") or ""), is_folder=is_dir)
        sz = int(raw.get("size") or 0)
        cf, ci = _quick_local_counts(target / nm) if is_dir else (0, 0)
        entries.append({
            "id": raw["id"],
            "name": nm,
            "path": child_rel,
            "parent_path": rel_path,
            "is_folder": is_dir,
            "mime_type": raw.get("mimeType", ""),
            "category": cat,
            "ext": ext,
            "size": sz,
            "size_human": "—" if is_dir else sc.human_size(sz),
            "modified_time": raw.get("modifiedTime", ""),
            "child_folders": cf,
            "child_files": ci,
            "url": "",
            "can_raw_preview": (not is_dir) and cat in {"image", "pdf", "audio", "video", "text", "code"},
            "can_open_os": True,
        })

    total_folders = sum(1 for e in entries if e["is_folder"])
    total_files = sum(1 for e in entries if not e["is_folder"])
    total_bytes = sum(int(e["size"] or 0) for e in entries if not e["is_folder"])

    filtered = _filter_entries(entries, filter_q)
    ordered = _sort_entries(filtered, sort_by=sort_by, order=order)

    tree_branches: List[Dict[str, Any]] = []
    try:
        for ch in sorted(root.iterdir(), key=lambda p: sc.strip_accents(p.name).lower()):
            if ch.is_dir():
                cf, ci = _quick_local_counts(ch, limit=200)
                tree_branches.append({
                    "name": sc.nfc(ch.name),
                    "path": sc.nfc(ch.name),
                    "id": make_local_id(root, ch),
                    "has_children": cf > 0,
                    "child_folders": cf,
                    "child_files": ci,
                })
    except OSError:
        pass

    parent_rel = rel_path.rsplit("/", 1)[0] if "/" in rel_path else ("" if rel_path else None)
    return {
        "ok": True,
        "source_kind": "local",
        "data_source": "local_live",
        "has_vault": True,
        "root_name": root_name,
        "vault_root": str(root),
        "current_path": rel_path,
        "current_id": item_id,
        "current_fs_path": str(target),
        "parent_path": parent_rel,
        "breadcrumbs": build_breadcrumbs(rel_path, root_name),
        "stats": {
            "folders": total_folders,
            "files": total_files,
            "total_items": len(entries),
            "shown_items": len(ordered),
            "bytes": total_bytes,
            "size_human": sc.human_size(total_bytes),
        },
        "entries": ordered,
        "tree_branches": tree_branches,
        "can_open_os": True,
    }


def _browse_indexed_vault(
    rel_path: str,
    root_name: str,
    *,
    sort_by: str = "name",
    order: str = "asc",
    filter_q: str = "",
) -> Dict[str, Any]:
    with sc.StorageDB() as db:
        has_idx = _ensure_db_populated(db)
        if not has_idx:
            return {
                "ok": True,
                "source_kind": sc.VAULT_SOURCE_KIND or "gdrive",
                "data_source": "empty_index",
                "has_vault": sc.has_configured_vault(),
                "needs_scan": True,
                "root_name": root_name,
                "current_path": "",
                "current_id": sc.ROOT_ID,
                "parent_path": None,
                "breadcrumbs": build_breadcrumbs("", root_name),
                "stats": {"folders": 0, "files": 0, "total_items": 0, "shown_items": 0, "bytes": 0, "size_human": "0 B"},
                "entries": [],
                "tree_branches": [],
                "can_open_os": False,
            }

        # Xác định tên gốc thực tế trong bảng `folders` (depth = 0)
        root_row = db._conn.execute("SELECT path, id FROM folders WHERE depth = 0 LIMIT 1").fetchone()
        db_root = root_row["path"] if root_row else root_name
        db_root_id = root_row["id"] if root_row else sc.ROOT_ID
        norm_rel = normalize_rel_path(rel_path, root_name=db_root)
        full_folder_path = f"{db_root}/{norm_rel}" if norm_rel else db_root

        cur_row = db._conn.execute("SELECT path, id, depth FROM folders WHERE path = ?", (full_folder_path,)).fetchone()
        if not cur_row:
            raise FileNotFoundError(f"Không tìm thấy thư mục trong chỉ mục: `{norm_rel or '/'}`")

        # Đếm số thư mục con / tệp con của từng thư mục trong 1 truy vấn SQL nhanh
        sub_folders = db._conn.execute(
            "SELECT path, id, name, modified_time FROM folders WHERE parent_path = ?",
            (full_folder_path,),
        ).fetchall()
        sub_items = db._conn.execute(
            "SELECT id, name, mime_type, size, modified_time FROM items WHERE parent_path = ?",
            (full_folder_path,),
        ).fetchall()

        folder_by_name = {r["name"]: r for r in sub_folders}
        entries: List[Dict[str, Any]] = []
        seen_folder_ids = set()

        for sf in sub_folders:
            seen_folder_ids.add(sf["id"])
            sf_rel = normalize_rel_path(sf["path"], root_name=db_root)
            cf_cnt = db._conn.execute("SELECT COUNT(*) AS c FROM folders WHERE parent_path = ?", (sf["path"],)).fetchone()["c"]
            ci_cnt = db._conn.execute(
                "SELECT COUNT(*) AS c FROM items WHERE parent_path = ? AND mime_type != ?",
                (sf["path"], sc.FOLDER_MIME),
            ).fetchone()["c"]
            entries.append({
                "id": sf["id"],
                "name": sf["name"],
                "path": sf_rel,
                "parent_path": norm_rel,
                "is_folder": True,
                "mime_type": sc.FOLDER_MIME,
                "category": "folder",
                "ext": "",
                "size": 0,
                "size_human": "—",
                "modified_time": sf["modified_time"] or "",
                "child_folders": int(cf_cnt),
                "child_files": int(ci_cnt),
                "url": sc.drive_url(sf["id"], sc.FOLDER_MIME),
                "can_raw_preview": False,
                "can_open_os": False,
            })

        for it in sub_items:
            is_dir = it["mime_type"] == sc.FOLDER_MIME
            if is_dir and (it["id"] in seen_folder_ids or it["name"] in folder_by_name):
                continue
            nm = it["name"]
            item_rel = f"{norm_rel}/{nm}" if norm_rel else nm
            cat, ext = classify_item(nm, it["mime_type"], is_folder=is_dir)
            sz = int(it["size"] or 0)
            entries.append({
                "id": it["id"],
                "name": nm,
                "path": item_rel,
                "parent_path": norm_rel,
                "is_folder": is_dir,
                "mime_type": it["mime_type"],
                "category": cat,
                "ext": ext,
                "size": sz,
                "size_human": "—" if is_dir else sc.human_size(sz),
                "modified_time": it["modified_time"] or "",
                "child_folders": 0,
                "child_files": 0,
                "url": sc.drive_url(it["id"], it["mime_type"]),
                "can_raw_preview": False,
                "can_open_os": False,
            })

        # Nhánh cấp 1 cho cây điều hướng bên trái
        branch_rows = db._conn.execute(
            "SELECT path, id, name FROM folders WHERE parent_path = ? ORDER BY name ASC",
            (db_root,),
        ).fetchall()
        tree_branches: List[Dict[str, Any]] = []
        for br in branch_rows:
            br_rel = normalize_rel_path(br["path"], root_name=db_root)
            cf_cnt = db._conn.execute("SELECT COUNT(*) AS c FROM folders WHERE parent_path = ?", (br["path"],)).fetchone()["c"]
            ci_cnt = db._conn.execute(
                "SELECT COUNT(*) AS c FROM items WHERE parent_path = ? AND mime_type != ?",
                (br["path"], sc.FOLDER_MIME),
            ).fetchone()["c"]
            tree_branches.append({
                "name": br["name"],
                "path": br_rel,
                "id": br["id"],
                "has_children": int(cf_cnt) > 0,
                "child_folders": int(cf_cnt),
                "child_files": int(ci_cnt),
            })

    total_folders = sum(1 for e in entries if e["is_folder"])
    total_files = sum(1 for e in entries if not e["is_folder"])
    total_bytes = sum(int(e["size"] or 0) for e in entries if not e["is_folder"])

    filtered = _filter_entries(entries, filter_q)
    ordered = _sort_entries(filtered, sort_by=sort_by, order=order)
    parent_rel = norm_rel.rsplit("/", 1)[0] if "/" in norm_rel else ("" if norm_rel else None)

    return {
        "ok": True,
        "source_kind": sc.VAULT_SOURCE_KIND or "gdrive",
        "data_source": "sqlite_index",
        "has_vault": True,
        "root_name": db_root,
        "current_path": norm_rel,
        "current_id": cur_row["id"] or db_root_id,
        "current_url": sc.drive_url(cur_row["id"] or db_root_id, sc.FOLDER_MIME),
        "parent_path": parent_rel,
        "breadcrumbs": build_breadcrumbs(norm_rel, db_root),
        "stats": {
            "folders": total_folders,
            "files": total_files,
            "total_items": len(entries),
            "shown_items": len(ordered),
            "bytes": total_bytes,
            "size_human": sc.human_size(total_bytes),
        },
        "entries": ordered,
        "tree_branches": tree_branches,
        "can_open_os": False,
    }


def browse_folder(
    path: str = "",
    *,
    sort_by: str = "name",
    order: str = "asc",
    filter_q: str = "",
) -> Dict[str, Any]:
    """Liệt kê thư mục con và tệp tin tại `path` trong kho đang hoạt động."""
    if not sc.has_configured_vault():
        return {
            "ok": True,
            "has_vault": False,
            "source_kind": "",
            "data_source": "none",
            "root_name": "",
            "current_path": "",
            "parent_path": None,
            "breadcrumbs": [],
            "stats": {"folders": 0, "files": 0, "total_items": 0, "shown_items": 0, "bytes": 0, "size_human": "0 B"},
            "entries": [],
            "tree_branches": [],
            "can_open_os": False,
        }

    root_name = sc.ROOT_NAME or "Kho gốc"
    rel_path = normalize_rel_path(path, root_name=root_name)

    is_local, local_root = _is_active_local_vault()
    if is_local and local_root is not None:
        return _browse_local_vault(local_root, rel_path, root_name, sort_by=sort_by, order=order, filter_q=filter_q)
    return _browse_indexed_vault(rel_path, root_name, sort_by=sort_by, order=order, filter_q=filter_q)


def list_folder_children_tree(path: str = "") -> Dict[str, Any]:
    """Lấy danh sách thư mục con trực tiếp của `path` cho cây thư mục mở rộng lười (lazy tree)."""
    if not sc.has_configured_vault():
        return {"ok": True, "path": "", "children": []}
    root_name = sc.ROOT_NAME or "Kho gốc"
    rel_path = normalize_rel_path(path, root_name=root_name)

    is_local, local_root = _is_active_local_vault()
    if is_local and local_root is not None:
        target = local_path_from_id(local_root, f"{LOCAL_ID_PREFIX}{rel_path}" if rel_path else f"{LOCAL_ID_PREFIX}.")
        if not target.is_dir():
            return {"ok": True, "path": rel_path, "children": []}
        children: List[Dict[str, Any]] = []
        try:
            for ch in sorted(target.iterdir(), key=lambda p: sc.strip_accents(p.name).lower()):
                if not ch.is_dir():
                    continue
                nm = sc.nfc(ch.name)
                ch_rel = f"{rel_path}/{nm}" if rel_path else nm
                cf, ci = _quick_local_counts(ch, limit=150)
                children.append({
                    "name": nm,
                    "path": ch_rel,
                    "id": make_local_id(local_root, ch),
                    "has_children": cf > 0,
                    "child_folders": cf,
                    "child_files": ci,
                })
        except OSError:
            pass
        return {"ok": True, "path": rel_path, "children": children}

    with sc.StorageDB() as db:
        if not _ensure_db_populated(db):
            return {"ok": True, "path": rel_path, "children": []}
        root_row = db._conn.execute("SELECT path FROM folders WHERE depth = 0 LIMIT 1").fetchone()
        db_root = root_row["path"] if root_row else root_name
        norm_rel = normalize_rel_path(rel_path, root_name=db_root)
        full_path = f"{db_root}/{norm_rel}" if norm_rel else db_root
        rows = db._conn.execute(
            "SELECT path, id, name FROM folders WHERE parent_path = ? ORDER BY name ASC",
            (full_path,),
        ).fetchall()
        children = []
        for r in rows:
            r_rel = normalize_rel_path(r["path"], root_name=db_root)
            cf = db._conn.execute("SELECT COUNT(*) AS c FROM folders WHERE parent_path = ?", (r["path"],)).fetchone()["c"]
            ci = db._conn.execute(
                "SELECT COUNT(*) AS c FROM items WHERE parent_path = ? AND mime_type != ?",
                (r["path"], sc.FOLDER_MIME),
            ).fetchone()["c"]
            children.append({
                "name": r["name"],
                "path": r_rel,
                "id": r["id"],
                "has_children": int(cf) > 0,
                "child_folders": int(cf),
                "child_files": int(ci),
            })
        return {"ok": True, "path": norm_rel, "children": children}


def resolve_local_target(*, item_id: str = "", path: str = "") -> Tuple[Path, Path]:
    """Giải mã đường dẫn mục cục bộ an toàn (tuyệt đối chặn path traversal ra ngoài kho)."""
    is_local, local_root = _is_active_local_vault()
    if not is_local or local_root is None:
        raise PermissionError("Kho hiện tại không phải kho cục bộ.")
    if item_id:
        resolved = local_path_from_id(local_root, item_id)
    else:
        rel = normalize_rel_path(path, root_name=sc.ROOT_NAME or "")
        resolved = local_path_from_id(local_root, f"{LOCAL_ID_PREFIX}{rel}" if rel else f"{LOCAL_ID_PREFIX}.")
    # Bảo vệ 2 lớp chống symlink trỏ ra ngoài kho
    try:
        resolved.resolve().relative_to(local_root.resolve())
    except ValueError as exc:
        raise PermissionError(f"Đường dẫn nằm ngoài phạm vi kho cục bộ: `{item_id or path}`") from exc
    return local_root, resolved


def read_raw_local_file(*, item_id: str = "", path: str = "") -> Tuple[Path, str, str]:
    """Trả về `(resolved_path, safe_mime, download_name)` cho endpoint `/api/explorer/raw`."""
    _, target = resolve_local_target(item_id=item_id, path=path)
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"Không tìm thấy tệp cục bộ: `{item_id or path}`")
    ext = target.suffix.lower().lstrip(".")
    # Chặn tuyệt đối XSS từ tệp HTML/XML/JS người dùng mở trực tiếp trên origin localhost của KAS
    if ext in {"html", "htm", "xhtml", "xml", "js", "mjs"}:
        mime = "text/plain; charset=utf-8"
    else:
        guessed, _ = mimetypes.guess_type(str(target))
        mime = guessed or "application/octet-stream"
        if mime.startswith("text/") and "charset=" not in mime:
            mime = f"{mime}; charset=utf-8"
    return target, mime, target.name


def preview_item(*, item_id: str = "", path: str = "", fetch_drive: bool = False) -> Dict[str, Any]:
    """Tạo bản xem trước chi tiết cho một thư mục hoặc tệp tin (hỗ trợ cả kho Cục bộ & Google Drive)."""
    if not sc.has_configured_vault():
        raise ValueError("Chưa chọn kho dữ liệu đang hoạt động.")

    is_local, local_root = _is_active_local_vault()
    if is_local and local_root is not None:
        _, target = resolve_local_target(item_id=item_id, path=path)
        if not target.exists():
            raise FileNotFoundError(f"Không tìm thấy mục: `{item_id or path}`")
        rel = "" if target.resolve() == local_root.resolve() else target.resolve().relative_to(local_root.resolve()).as_posix()
        rel = sc.nfc(rel)
        eid = make_local_id(local_root, target)
        st = target.stat()
        mod_utc = sc.now_utc_iso()
        try:
            import datetime as _dt

            mod_utc = _dt.datetime.fromtimestamp(st.st_mtime, tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            pass

        if target.is_dir():
            cf, ci = _quick_local_counts(target, limit=2000)
            total_sz = 0
            try:
                for ch in target.iterdir():
                    if ch.is_file():
                        total_sz += ch.stat().st_size
            except OSError:
                pass
            return {
                "ok": True,
                "source_kind": "local",
                "id": eid,
                "name": sc.nfc(target.name),
                "path": rel,
                "fs_path": str(target),
                "is_folder": True,
                "category": "folder",
                "preview_mode": "folder",
                "mime_type": sc.FOLDER_MIME,
                "size": total_sz,
                "size_human": sc.human_size(total_sz),
                "modified_time": mod_utc,
                "child_folders": cf,
                "child_files": ci,
                "can_open_os": True,
            }

        mime, _ = mimetypes.guess_type(str(target))
        mime = mime or "application/octet-stream"
        cat, ext = classify_item(target.name, mime, is_folder=False)
        size = int(st.st_size)
        base: Dict[str, Any] = {
            "ok": True,
            "source_kind": "local",
            "id": eid,
            "name": sc.nfc(target.name),
            "path": rel,
            "fs_path": str(target),
            "is_folder": False,
            "category": cat,
            "ext": ext,
            "mime_type": mime,
            "size": size,
            "size_human": sc.human_size(size),
            "modified_time": mod_utc,
            "raw_url": f"/api/explorer/raw?id={urllib.parse.quote(eid, safe='')}",
            "can_open_os": True,
            "metadata": {},
            "outline": [],
            "text_preview": "",
            "stats": {},
        }

        if cat in {"text", "code"}:
            raw_bytes = target.read_bytes()[:MAX_INLINE_TEXT_BYTES]
            decoded, enc = fr.decode_bytes_smart(raw_bytes)
            base["preview_mode"] = "text"
            base["text_preview"] = decoded[:MAX_PREVIEW_TEXT_CHARS]
            base["truncated"] = size > MAX_INLINE_TEXT_BYTES or len(decoded) > MAX_PREVIEW_TEXT_CHARS
            base["metadata"] = {"encoding": enc, "lines": decoded.count("\n") + 1}
            base["stats"] = fr.compute_text_stats(decoded)
            return base

        if cat == "image":
            base["preview_mode"] = "image"
            try:
                rec = fr.read_image_file(target, enable_ocr=False)
                base["metadata"] = rec.get("metadata", {})
            except Exception:
                pass
            return base

        if cat == "pdf":
            base["preview_mode"] = "pdf"
            try:
                rec = fr.read_pdf_file(target, max_pages=10, enable_ocr=False)
                base["metadata"] = rec.get("metadata", {})
                base["outline"] = rec.get("outline", [])[:25]
                base["text_preview"] = (rec.get("text") or "")[:MAX_PREVIEW_TEXT_CHARS]
                base["stats"] = rec.get("stats", {})
            except Exception:
                pass
            return base

        if cat in {"audio", "video"}:
            base["preview_mode"] = cat
            try:
                rec = fr.read_media_file(target)
                base["metadata"] = rec.get("metadata", {})
            except Exception:
                pass
            return base

        if cat in {"office", "ebook", "archive"}:
            base["preview_mode"] = "document"
            try:
                rec = fr.read_local_file(target, name=target.name, mime=mime, max_pages=12, enable_ocr=False)
                base["metadata"] = rec.get("metadata", {})
                base["outline"] = rec.get("outline", [])[:30]
                base["text_preview"] = (rec.get("text") or rec.get("text_preview") or "")[:MAX_PREVIEW_TEXT_CHARS]
                base["stats"] = rec.get("stats", {})
                base["flags"] = rec.get("flags", [])
            except Exception as exc:
                base["error"] = str(exc)
            return base

        base["preview_mode"] = "binary"
        if size <= MAX_SHA256_BYTES:
            try:
                base["metadata"]["sha256"] = sc.sha256_file(target)
            except Exception:
                pass
        return base

    # --- KHO GOOGLE DRIVE / SQLITE INDEX ---
    with sc.StorageDB() as db:
        _ensure_db_populated(db)
        root_row = db._conn.execute("SELECT path FROM folders WHERE depth = 0 LIMIT 1").fetchone()
        db_root = root_row["path"] if root_row else (sc.ROOT_NAME or "")

        row = None
        if item_id:
            row = db._conn.execute(
                "SELECT id, parent_path, name, mime_type, size, modified_time FROM items WHERE id = ?",
                (item_id,),
            ).fetchone()
            if not row:
                frow = db._conn.execute("SELECT path, id, name, modified_time FROM folders WHERE id = ?", (item_id,)).fetchone()
                if frow:
                    rel_f = normalize_rel_path(frow["path"], root_name=db_root)
                    cf = db._conn.execute("SELECT COUNT(*) AS c FROM folders WHERE parent_path = ?", (frow["path"],)).fetchone()["c"]
                    ci = db._conn.execute(
                        "SELECT COUNT(*) AS c FROM items WHERE parent_path = ? AND mime_type != ?",
                        (frow["path"], sc.FOLDER_MIME),
                    ).fetchone()["c"]
                    sz = db._conn.execute(
                        "SELECT COALESCE(SUM(size), 0) AS s FROM items WHERE parent_path = ?",
                        (frow["path"],),
                    ).fetchone()["s"]
                    return {
                        "ok": True,
                        "source_kind": "gdrive",
                        "id": frow["id"],
                        "name": frow["name"],
                        "path": rel_f,
                        "is_folder": True,
                        "category": "folder",
                        "preview_mode": "folder",
                        "mime_type": sc.FOLDER_MIME,
                        "size": int(sz or 0),
                        "size_human": sc.human_size(int(sz or 0)),
                        "modified_time": frow["modified_time"] or "",
                        "child_folders": int(cf),
                        "child_files": int(ci),
                        "url": sc.drive_url(frow["id"], sc.FOLDER_MIME),
                        "can_open_os": False,
                    }
        elif path:
            norm_rel = normalize_rel_path(path, root_name=db_root)
            full_p = f"{db_root}/{norm_rel}" if norm_rel else db_root
            frow = db._conn.execute("SELECT path, id, name, modified_time FROM folders WHERE path = ?", (full_p,)).fetchone()
            if frow:
                return preview_item(item_id=frow["id"], fetch_drive=False)
            parent_p = full_p.rsplit("/", 1)[0] if "/" in full_p else db_root
            nm = full_p.rsplit("/", 1)[-1]
            row = db._conn.execute(
                "SELECT id, parent_path, name, mime_type, size, modified_time FROM items WHERE parent_path = ? AND name = ?",
                (parent_p, nm),
            ).fetchone()

    if not row:
        raise FileNotFoundError(f"Không tìm thấy mục trong chỉ mục kho: `{item_id or path}`")

    is_dir = row["mime_type"] == sc.FOLDER_MIME
    cat, ext = classify_item(row["name"], row["mime_type"], is_folder=is_dir)
    rel_parent = normalize_rel_path(row["parent_path"], root_name=db_root)
    rel_item = f"{rel_parent}/{row['name']}" if rel_parent else row["name"]
    sz = int(row["size"] or 0)

    out: Dict[str, Any] = {
        "ok": True,
        "source_kind": "gdrive",
        "id": row["id"],
        "name": row["name"],
        "path": rel_item,
        "parent_path": rel_parent,
        "is_folder": is_dir,
        "category": cat,
        "ext": ext,
        "mime_type": row["mime_type"],
        "size": sz,
        "size_human": sc.human_size(sz),
        "modified_time": row["modified_time"] or "",
        "url": sc.drive_url(row["id"], row["mime_type"]),
        "can_open_os": False,
        "preview_mode": "drive_card",
        "metadata": {},
        "outline": [],
        "text_preview": "",
        "stats": {},
        "from_cache": False,
    }

    cached = fr.load_cached_record(
        row["id"],
        modified_time=row["modified_time"] or None,
        include_text=True,
    )
    if cached:
        out["from_cache"] = True
        cached_txt = cached.get("text") or cached.get("text_preview") or ""
        out["preview_mode"] = "document" if (cached_txt or cached.get("outline")) else "drive_card"
        out["metadata"] = cached.get("metadata", {})
        out["outline"] = (cached.get("outline") or [])[:30]
        out["text_preview"] = cached_txt[:MAX_PREVIEW_TEXT_CHARS]
        out["stats"] = cached.get("stats", {})
        return out

    if fetch_drive and not is_dir:
        try:
            rec = fr.read_drive_item(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "mimeType": row["mime_type"],
                    "size": sz,
                    "modifiedTime": row["modified_time"] or "",
                },
                parent_path=row["parent_path"],
                max_mb=15.0,
                max_pages=10,
                enable_ocr=False,
                use_cache=True,
            )
            out["preview_mode"] = "document"
            out["metadata"] = rec.get("metadata", {})
            out["outline"] = (rec.get("outline") or [])[:30]
            out["text_preview"] = (rec.get("text") or rec.get("text_preview") or "")[:MAX_PREVIEW_TEXT_CHARS]
            out["stats"] = rec.get("stats", {})
            out["flags"] = rec.get("flags", [])
        except Exception as exc:
            out["error"] = str(exc)

    return out


def open_in_os(*, item_id: str = "", path: str = "", reveal: bool = False) -> Dict[str, Any]:
    """Mở tệp bằng ứng dụng mặc định của hệ điều hành hoặc mở thư mục chứa trong File Explorer / Finder."""
    _, target = resolve_local_target(item_id=item_id, path=path)
    if not target.exists():
        raise FileNotFoundError(f"Không tìm thấy mục cục bộ: `{item_id or path}`")

    if os.name == "nt":
        if reveal and target.is_file():
            subprocess.Popen(["explorer.exe", f"/select,{target}"])
        else:
            os.startfile(str(target))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        if reveal and target.is_file():
            subprocess.Popen(["open", "-R", str(target)])
        else:
            subprocess.Popen(["open", str(target)])
    else:
        dest = target.parent if (reveal and target.is_file()) else target
        subprocess.Popen(["xdg-open", str(dest)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    return {"ok": True, "opened": str(target), "reveal": bool(reveal)}


def safe_error_status(exc: Exception) -> int:
    if isinstance(exc, FileNotFoundError):
        return 404
    if isinstance(exc, (PermissionError, ValueError, DriveError)):
        return 400
    return 500
