"""Tầng tương thích chỉ mục kết hợp SQLite (`storage.db`) và JSON (`storage_index.json`)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Tuple

from storage_suite.core.config import FOLDER_MIME, db_path, index_path
from storage_suite.core.utils import read_json, write_json
from storage_suite.store.sqlite_store import StorageDB

Index = Dict[str, Dict[str, Any]]


def load_index(path: Optional[Path] = None, required: bool = True) -> Index:
    """
    Nạp chỉ mục kho:
    - Nếu không truyền đường dẫn tùy chỉnh và `storage.db` mới hơn hoặc bằng `storage_index.json`,
      đọc trực tiếp từ SQLite; nếu `storage_index.json` mới hơn thì tự đồng bộ vào `storage.db`.
    - Nếu truyền `path` cụ thể (JSON hoặc `.db`), đọc đúng tệp đó.
    """
    if path is not None:
        p = Path(path)
        if p.suffix == ".db":
            if not p.exists():
                if required:
                    raise SystemExit(f"Chưa có cơ sở dữ liệu chỉ mục tại {p}. Hãy chạy `astorage quet` trước.")
                return {}
            with StorageDB(p) as db:
                return db.export_index_dict()
        data = read_json(p)
        if data is None:
            if required:
                raise SystemExit(f"Chưa có chỉ mục tại {p}. Hãy chạy `astorage quet` trước.")
            return {}
        if isinstance(data, dict) and "folders" in data and "meta" in data:
            data = data["folders"]
        return data

    json_p = index_path()
    sql_p = db_path()

    json_exists = json_p.exists()
    sql_exists = sql_p.exists()

    if sql_exists and (not json_exists or sql_p.stat().st_mtime >= json_p.stat().st_mtime):
        with StorageDB(sql_p) as db:
            if db.has_index():
                return db.export_index_dict()

    if json_exists:
        data = read_json(json_p)
        if isinstance(data, dict) and "folders" in data and "meta" in data:
            data = data["folders"]
        if isinstance(data, dict):
            try:
                with StorageDB(sql_p) as db:
                    db.import_index_dict(data)
            except Exception:
                pass
            return data

    if required:
        raise SystemExit(f"Chưa có chỉ mục tại {json_p} hoặc {sql_p}. Hãy chạy `astorage quet` trước.")
    return {}


def save_index(index: Index, path: Optional[Path] = None, sync_sqlite: bool = True) -> Path:
    """Lưu chỉ mục nguyên tử ra JSON và tự đồng bộ vào `storage.db` (SQLite WAL + FTS5)."""
    p = Path(path) if path else index_path()
    write_json(p, index, indent=None)
    if sync_sqlite and path is None:
        try:
            with StorageDB(db_path()) as db:
                db.import_index_dict(index)
        except Exception:
            pass
    return p


def build_id_map(index: Index) -> Tuple[Dict[str, str], Dict[str, Tuple[str, dict]]]:
    folder_paths: Dict[str, str] = {}
    items_by_id: Dict[str, Tuple[str, dict]] = {}
    for path, data in index.items():
        if data.get("id"):
            folder_paths[data["id"]] = path
        for it in data.get("items", []):
            items_by_id[it["id"]] = (path, it)
            if it.get("mimeType") == FOLDER_MIME:
                folder_paths.setdefault(it["id"], f"{path}/{it['name']}")
    return folder_paths, items_by_id


def iter_items(index: Index, branch: Optional[str] = None) -> Iterator[Tuple[str, dict]]:
    prefix = branch.rstrip("/") + "/" if branch else ""
    for path, data in index.items():
        if branch and not (path == branch or path.startswith(prefix)):
            continue
        for it in data.get("items", []):
            yield path, it
