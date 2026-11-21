"""Tầng lưu trữ SQLite (WAL + FTS5) & Unified Undo Journal."""

from storage_suite.store.legacy_compat import Index, build_id_map, iter_items, load_index, save_index
from storage_suite.store.sqlite_store import StorageDB

__all__ = [
    "Index",
    "StorageDB",
    "build_id_map",
    "iter_items",
    "load_index",
    "save_index",
]
