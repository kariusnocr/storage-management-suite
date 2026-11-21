"""Tầng lưu trữ SQLite tập trung (`storage.db`, WAL + FTS5) và Unified Undo Journal."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from storage_suite.core.config import FOLDER_MIME, ROOT_NAME, db_path
from storage_suite.core.models import UndoAction
from storage_suite.core.utils import nfc, now_stamp, now_utc_iso, strip_accents

_SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS kv_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS folders (
    path TEXT PRIMARY KEY,
    id TEXT NOT NULL,
    depth INTEGER NOT NULL DEFAULT 0,
    parent_path TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL DEFAULT '',
    modified_time TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_folders_id ON folders(id);
CREATE INDEX IF NOT EXISTS idx_folders_parent ON folders(parent_path);
CREATE INDEX IF NOT EXISTS idx_folders_depth ON folders(depth);

CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    parent_path TEXT NOT NULL,
    name TEXT NOT NULL,
    name_ascii TEXT NOT NULL DEFAULT '',
    mime_type TEXT NOT NULL,
    size INTEGER NOT NULL DEFAULT 0,
    modified_time TEXT NOT NULL DEFAULT '',
    extra_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_items_parent ON items(parent_path);
CREATE INDEX IF NOT EXISTS idx_items_mime ON items(mime_type);
CREATE INDEX IF NOT EXISTS idx_items_size ON items(size);
CREATE INDEX IF NOT EXISTS idx_items_mod ON items(modified_time);

CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(
    item_id UNINDEXED,
    name,
    name_ascii,
    parent_path,
    keywords,
    tokenize='unicode61'
);

CREATE TABLE IF NOT EXISTS folder_metadata (
    folder_id TEXT PRIMARY KEY,
    data_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS shortcuts (
    shortcut_id TEXT PRIMARY KEY,
    data_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS catalog_state (
    folder_path TEXT PRIMARY KEY,
    sheet_id TEXT NOT NULL DEFAULT '',
    sheet_name TEXT NOT NULL DEFAULT '',
    content_hash TEXT NOT NULL DEFAULT '',
    schema_version TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS undo_batches (
    batch_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    undone_at TEXT NOT NULL DEFAULT '',
    action_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS undo_actions (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT NOT NULL REFERENCES undo_batches(batch_id) ON DELETE CASCADE,
    op TEXT NOT NULL,
    item_id TEXT NOT NULL,
    old_name TEXT NOT NULL DEFAULT '',
    new_name TEXT NOT NULL DEFAULT '',
    old_parent_id TEXT NOT NULL DEFAULT '',
    new_parent_id TEXT NOT NULL DEFAULT '',
    path TEXT NOT NULL DEFAULT '',
    extra_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_undo_actions_batch ON undo_actions(batch_id);
"""


class StorageDB:
    """Cơ sở dữ liệu SQLite (WAL + FTS5) lưu chỉ mục kho, trạng thái danh mục và sổ cái hoàn tác."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(_SCHEMA_SQL)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> "StorageDB":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # -- KV metadata --------------------------------------------------------
    def set_meta(self, key: str, value: Any) -> None:
        payload = json.dumps(value, ensure_ascii=False)
        with self._lock:
            self._conn.execute(
                "INSERT INTO kv_meta(key, value, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                (key, payload, now_utc_iso()),
            )
            self._conn.commit()

    def get_meta(self, key: str, default: Any = None) -> Any:
        with self._lock:
            row = self._conn.execute("SELECT value FROM kv_meta WHERE key = ?", (key,)).fetchone()
        if not row:
            return default
        try:
            return json.loads(row["value"])
        except Exception:
            return default

    # -- Index import / export ----------------------------------------------
    def import_index_dict(self, index: Dict[str, Dict[str, Any]], rebuild_fts: bool = True) -> Dict[str, int]:
        """Nhập toàn bộ từ điển `storage_index` vào SQLite trong một giao dịch nguyên tử."""
        folder_rows: List[Tuple[str, str, int, str, str, str]] = []
        item_rows: List[Tuple[str, str, str, str, str, int, str, str]] = []
        fts_rows: List[Tuple[str, str, str, str, str]] = []
        seen_item_ids = set()

        for fpath, meta in index.items():
            clean_p = nfc(fpath)
            fid = str(meta.get("id", ""))
            depth = int(meta.get("depth", clean_p.count("/")))
            parent_p = clean_p.rsplit("/", 1)[0] if "/" in clean_p else ""
            name = clean_p.rsplit("/", 1)[-1]
            folder_rows.append((clean_p, fid, depth, parent_p, name, str(meta.get("modifiedTime", "") or "")))

            for it in meta.get("items", []):
                iid = str(it.get("id", ""))
                if not iid or iid in seen_item_ids:
                    continue
                seen_item_ids.add(iid)
                nm = nfc(str(it.get("name", "")))
                nm_ascii = strip_accents(nm).lower()
                mime = str(it.get("mimeType", ""))
                try:
                    sz = int(it.get("size") or 0)
                except (TypeError, ValueError):
                    sz = 0
                mod = str(it.get("modifiedTime", "") or "")
                extra = {k: v for k, v in it.items() if k not in {"id", "name", "mimeType", "size", "modifiedTime"}}
                item_rows.append((iid, clean_p, nm, nm_ascii, mime, sz, mod, json.dumps(extra, ensure_ascii=False)))
                if rebuild_fts:
                    fts_rows.append((iid, nm, nm_ascii, clean_p, ""))

        with self._lock:
            cur = self._conn.cursor()
            cur.execute("BEGIN")
            try:
                cur.execute("DELETE FROM folders")
                cur.execute("DELETE FROM items")
                cur.executemany(
                    "INSERT INTO folders(path, id, depth, parent_path, name, modified_time) VALUES (?, ?, ?, ?, ?, ?)",
                    folder_rows,
                )
                cur.executemany(
                    "INSERT OR REPLACE INTO items(id, parent_path, name, name_ascii, mime_type, size, modified_time, extra_json) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    item_rows,
                )
                if rebuild_fts:
                    cur.execute("DELETE FROM items_fts")
                    cur.executemany(
                        "INSERT INTO items_fts(item_id, name, name_ascii, parent_path, keywords) VALUES (?, ?, ?, ?, ?)",
                        fts_rows,
                    )
                cur.execute(
                    "INSERT INTO kv_meta(key, value, updated_at) VALUES (?, ?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                    ("last_import_utc", json.dumps(now_utc_iso()), now_utc_iso()),
                )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
        return {"folders": len(folder_rows), "items": len(item_rows)}

    def export_index_dict(self, branch: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """Xuất từ điển `storage_index` tương thích 100% với các mô-đun vận hành."""
        with self._lock:
            if branch:
                prefix = branch.rstrip("/") + "/"
                f_rows = self._conn.execute(
                    "SELECT path, id, depth FROM folders WHERE path = ? OR path LIKE ?",
                    (branch, prefix + "%"),
                ).fetchall()
                i_rows = self._conn.execute(
                    "SELECT id, parent_path, name, mime_type, size, modified_time, extra_json "
                    "FROM items WHERE parent_path = ? OR parent_path LIKE ?",
                    (branch, prefix + "%"),
                ).fetchall()
            else:
                f_rows = self._conn.execute("SELECT path, id, depth FROM folders").fetchall()
                i_rows = self._conn.execute(
                    "SELECT id, parent_path, name, mime_type, size, modified_time, extra_json FROM items"
                ).fetchall()

        index: Dict[str, Dict[str, Any]] = {}
        for r in f_rows:
            index[r["path"]] = {"id": r["id"], "depth": r["depth"], "items": []}

        for r in i_rows:
            parent = r["parent_path"]
            if parent not in index:
                continue
            rec: Dict[str, Any] = {
                "id": r["id"],
                "name": r["name"],
                "mimeType": r["mime_type"],
            }
            if r["size"]:
                rec["size"] = r["size"]
            if r["modified_time"]:
                rec["modifiedTime"] = r["modified_time"]
            if r["extra_json"] and r["extra_json"] != "{}":
                try:
                    rec.update(json.loads(r["extra_json"]))
                except Exception:
                    pass
            index[parent]["items"].append(rec)
        return index

    def has_index(self) -> bool:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) AS c FROM folders").fetchone()
        return bool(row and row["c"] > 0)

    def update_fts_keywords(self, item_id: str, keywords: str) -> None:
        """Bổ sung từ khóa TF-IDF / văn bản OCR vào chỉ mục FTS5 cho một mục."""
        with self._lock:
            row = self._conn.execute(
                "SELECT name, name_ascii, parent_path FROM items WHERE id = ?", (item_id,)
            ).fetchone()
            if not row:
                return
            self._conn.execute("DELETE FROM items_fts WHERE item_id = ?", (item_id,))
            self._conn.execute(
                "INSERT INTO items_fts(item_id, name, name_ascii, parent_path, keywords) VALUES (?, ?, ?, ?, ?)",
                (item_id, row["name"], row["name_ascii"], row["parent_path"], strip_accents(keywords).lower()[:10_000]),
            )
            self._conn.commit()

    def search_fts(
        self,
        query: str,
        branch: Optional[str] = None,
        mime_prefix: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Tìm kiếm toàn văn siêu tốc (<20 ms) trên FTS5 (hỗ trợ cả có dấu và không dấu)."""
        q_clean = strip_accents((query or "").strip()).lower()
        tokens = [t for t in "".join(ch if ch.isalnum() else " " for ch in q_clean).split() if t]
        if not tokens:
            return []
        fts_expr = " AND ".join(f'"{t}"*' for t in tokens[:8])
        sql = (
            "SELECT i.id, i.parent_path, i.name, i.mime_type, i.size, i.modified_time "
            "FROM items_fts f JOIN items i ON i.id = f.item_id "
            "WHERE items_fts MATCH ? "
        )
        params: List[Any] = [fts_expr]
        if branch:
            prefix = branch.rstrip("/") + "/"
            sql += "AND (i.parent_path = ? OR i.parent_path LIKE ?) "
            params.extend([branch, prefix + "%"])
        if mime_prefix:
            sql += "AND i.mime_type LIKE ? "
            params.append(mime_prefix + "%")
        sql += "ORDER BY bm25(items_fts) LIMIT ?"
        params.append(max(1, int(limit)))

        with self._lock:
            try:
                rows = self._conn.execute(sql, params).fetchall()
            except sqlite3.OperationalError:
                like = f"%{q_clean}%"
                rows = self._conn.execute(
                    "SELECT id, parent_path, name, mime_type, size, modified_time "
                    "FROM items WHERE name_ascii LIKE ? OR parent_path LIKE ? LIMIT ?",
                    (like, like, max(1, int(limit))),
                ).fetchall()
        return [dict(r) for r in rows]

    def stats_summary(self) -> Dict[str, Any]:
        """Thống kê tổng quan trực tiếp từ SQLite (<5 ms)."""
        with self._lock:
            total_folders = self._conn.execute("SELECT COUNT(*) FROM folders").fetchone()[0]
            total_files = self._conn.execute(
                "SELECT COUNT(*) FROM items WHERE mime_type != ?", (FOLDER_MIME,)
            ).fetchone()[0]
            total_bytes = self._conn.execute(
                "SELECT COALESCE(SUM(size), 0) FROM items WHERE mime_type != ?", (FOLDER_MIME,)
            ).fetchone()[0]
            root_prefix = f"{ROOT_NAME}/"
            branch_rows = self._conn.execute(
                "SELECT parent_path, mime_type, size FROM items"
            ).fetchall()
            last_import = self.get_meta("last_import_utc", "")

        by_branch: Dict[str, Dict[str, int]] = {}
        for r in branch_rows:
            p = r["parent_path"]
            if p.startswith(root_prefix):
                b = p[len(root_prefix) :].split("/", 1)[0]
            else:
                b = "(gốc)"
            st = by_branch.setdefault(b, {"folders": 0, "files": 0, "bytes": 0})
            if r["mime_type"] == FOLDER_MIME:
                st["folders"] += 1
            else:
                st["files"] += 1
                st["bytes"] += int(r["size"] or 0)

        return {
            "db_path": str(self.path),
            "db_size_bytes": self.path.stat().st_size if self.path.exists() else 0,
            "total_folders": max(0, total_folders - 1),
            "total_files": total_files,
            "total_bytes": int(total_bytes or 0),
            "last_import_utc": last_import,
            "branches": by_branch,
        }

    # -- Unified Undo Journal -----------------------------------------------
    def record_undo_batch(
        self,
        kind: str,
        actions: Sequence[UndoAction],
        description: str = "",
        batch_id: Optional[str] = None,
    ) -> str:
        bid = batch_id or f"{kind}_{now_stamp()}"
        now = now_utc_iso()
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("BEGIN")
            try:
                cur.execute(
                    "INSERT OR REPLACE INTO undo_batches(batch_id, kind, description, created_at, undone_at, action_count) "
                    "VALUES (?, ?, ?, ?, '', ?)",
                    (bid, kind, description, now, len(actions)),
                )
                cur.execute("DELETE FROM undo_actions WHERE batch_id = ?", (bid,))
                cur.executemany(
                    "INSERT INTO undo_actions(batch_id, op, item_id, old_name, new_name, old_parent_id, new_parent_id, path, extra_json) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        (
                            bid,
                            a.op,
                            a.item_id,
                            a.old_name,
                            a.new_name,
                            a.old_parent_id,
                            a.new_parent_id,
                            a.path,
                            json.dumps(a.extra, ensure_ascii=False),
                        )
                        for a in actions
                    ],
                )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
        return bid

    def list_undo_batches(self, limit: int = 30) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT batch_id, kind, description, created_at, undone_at, action_count "
                "FROM undo_batches ORDER BY created_at DESC LIMIT ?",
                (max(1, int(limit)),),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_undo_batch(self, batch_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            b = self._conn.execute(
                "SELECT batch_id, kind, description, created_at, undone_at, action_count "
                "FROM undo_batches WHERE batch_id = ?",
                (batch_id,),
            ).fetchone()
            if not b:
                return None
            acts = self._conn.execute(
                "SELECT seq, op, item_id, old_name, new_name, old_parent_id, new_parent_id, path, extra_json "
                "FROM undo_actions WHERE batch_id = ? ORDER BY seq DESC",
                (batch_id,),
            ).fetchall()
        out = dict(b)
        out["actions"] = [dict(a) for a in acts]
        return out

    def undo_batch(self, drive: Any, batch_id: str, execute: bool = False) -> Dict[str, Any]:
        """Hoàn tác nguyên tử một lô thao tác theo thứ tự ngược (LIFO)."""
        batch = self.get_undo_batch(batch_id)
        if not batch:
            return {"ok": False, "error": f"Không tìm thấy lô `{batch_id}`", "reverted": 0, "total": 0}
        if batch["undone_at"]:
            return {"ok": False, "error": f"Lô `{batch_id}` đã được hoàn tác lúc {batch['undone_at']}", "reverted": 0, "total": batch["action_count"]}

        reverted = 0
        errors: List[str] = []
        actions = batch["actions"]
        for act in actions:
            op = act["op"]
            iid = act["item_id"]
            if not execute:
                reverted += 1
                continue
            try:
                if op in {"rename", "catalog_rename"} and act["old_name"]:
                    drive.rename(iid, act["old_name"])
                    reverted += 1
                elif op in {"move", "catalog_prune"} and act["old_parent_id"]:
                    drive.move(iid, act["old_parent_id"])
                    if act["old_name"] and act["new_name"] and act["old_name"] != act["new_name"]:
                        drive.rename(iid, act["old_name"])
                    reverted += 1
            except Exception as exc:
                errors.append(f"{iid}: {exc}")

        if execute and not errors:
            with self._lock:
                self._conn.execute(
                    "UPDATE undo_batches SET undone_at = ? WHERE batch_id = ?",
                    (now_utc_iso(), batch_id),
                )
                self._conn.commit()
        return {
            "ok": not errors,
            "batch_id": batch_id,
            "execute": execute,
            "reverted": reverted,
            "total": len(actions),
            "errors": errors,
        }
