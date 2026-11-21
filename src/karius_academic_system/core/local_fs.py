"""Trình điều khiển hệ thống tệp cục bộ (`LocalFSBackend`) cho Karius Academic System (KAS) v5.0.

Cho phép KAS quản lý trực tiếp mọi thư mục trên máy cá nhân, ổ cứng rời, NAS hoặc thư mục đồng bộ
OneDrive / iCloud / Google Drive for Desktop mà không cần Internet hay OAuth 2.0.
"""

from __future__ import annotations

import datetime as _dt
import mimetypes
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from karius_academic_system.core.drive_base import DriveError

FOLDER_MIME = "application/vnd.google-apps.folder"
LOCAL_ID_PREFIX = "loc:"


def _iso_mtime(st: os.stat_result) -> str:
    return _dt.datetime.fromtimestamp(st.st_mtime, tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iso_ctime(st: os.stat_result) -> str:
    return _dt.datetime.fromtimestamp(st.st_ctime, tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _guess_mime(p: Path) -> str:
    if p.is_dir():
        return FOLDER_MIME
    mt, _ = mimetypes.guess_type(str(p))
    return mt or "application/octet-stream"


def make_local_id(root: Path, target: Path) -> str:
    rel = target.resolve().relative_to(root.resolve()).as_posix()
    return f"{LOCAL_ID_PREFIX}{rel}"


def local_path_from_id(root: Path, item_id: str) -> Path:
    raw = (item_id or "").strip()
    root_res = root.resolve()
    if not raw or raw in {LOCAL_ID_PREFIX, f"{LOCAL_ID_PREFIX}.", "."}:
        return root_res
    if raw.startswith(LOCAL_ID_PREFIX):
        rel = raw[len(LOCAL_ID_PREFIX):].strip("/")
        cand = (root_res / rel).resolve() if rel and rel != "." else root_res
    else:
        cand = Path(raw).expanduser().resolve()
    # Chống path traversal ra ngoài thư mục gốc kho
    try:
        cand.relative_to(root_res)
    except ValueError as exc:
        raise DriveError(f"Đường dẫn nằm ngoài phạm vi kho cục bộ: `{item_id}`") from exc
    return cand


class LocalFSBackend:
    """Cài đặt đầy đủ `DriveProtocol` trên thư mục cục bộ (100% ngoại tuyến, hỗ trợ Undo Journal)."""

    backend_name: str = "local"

    def __init__(self, root_dir: Path | str) -> None:
        self.root = Path(root_dir).expanduser().resolve()
        if not self.root.exists() or not self.root.is_dir():
            raise DriveError(f"Thư mục kho cục bộ không tồn tại: `{self.root}`")

    @property
    def root_id(self) -> str:
        return f"{LOCAL_ID_PREFIX}."

    def resolve_path(self, item_id: str) -> Path:
        return local_path_from_id(self.root, item_id)

    def _entry_dict(self, p: Path) -> dict:
        st = p.stat()
        is_dir = p.is_dir()
        rec: dict = {
            "id": make_local_id(self.root, p),
            "name": p.name,
            "mimeType": FOLDER_MIME if is_dir else _guess_mime(p),
            "modifiedTime": _iso_mtime(st),
            "createdTime": _iso_ctime(st),
        }
        if not is_dir:
            rec["size"] = int(st.st_size)
        if p.resolve() != self.root:
            rec["parents"] = [make_local_id(self.root, p.parent)]
        return rec

    def ls(self, folder_id: str) -> List[dict]:
        target = self.resolve_path(folder_id)
        if not target.is_dir():
            raise DriveError(f"Không phải thư mục cục bộ: `{target}`")
        out: List[dict] = []
        try:
            entries = sorted(target.iterdir(), key=lambda x: x.name)
        except OSError as exc:
            raise DriveError(f"Không đọc được thư mục `{target}`: {exc}") from exc
        for ch in entries:
            try:
                out.append(self._entry_dict(ch))
            except OSError:
                continue
        return out

    def stream_ls(
        self,
        folder_ids: Sequence[str],
        concurrency: int = 32,
        timeout: int = 600,
    ) -> Tuple[Dict[str, List[dict]], Dict[str, str]]:
        out_map: Dict[str, List[dict]] = {}
        err_map: Dict[str, str] = {}
        for fid in dict.fromkeys(folder_ids):
            try:
                out_map[fid] = self.ls(fid)
            except DriveError as exc:
                err_map[fid] = str(exc)
        return out_map, err_map

    def info(self, file_id: str) -> dict:
        target = self.resolve_path(file_id)
        if not target.exists():
            raise DriveError(f"Không tìm thấy mục cục bộ: `{target}`")
        return self._entry_dict(target)

    def stream_info(
        self,
        file_ids: Sequence[str],
        concurrency: int = 32,
        timeout: int = 600,
    ) -> Dict[str, dict]:
        out: Dict[str, dict] = {}
        for fid in dict.fromkeys(file_ids):
            try:
                out[fid] = self.info(fid)
            except DriveError:
                pass
        return out

    def capabilities(self, file_id: str, fields: str = "canMoveItemOutOfDrive,canEdit,canTrash") -> dict:
        target = self.resolve_path(file_id)
        writable = os.access(target.parent if target.exists() else self.root, os.W_OK)
        all_caps = {"canMoveItemOutOfDrive": writable, "canEdit": writable, "canTrash": writable}
        if not fields:
            return all_caps
        wanted = {f.strip() for f in fields.split(",") if f.strip()}
        return {k: v for k, v in all_caps.items() if k in wanted}

    def stream_capabilities(
        self,
        file_ids: Sequence[str],
        fields: str = "canMoveItemOutOfDrive,canEdit,canTrash",
        concurrency: int = 32,
        timeout: int = 600,
    ) -> Dict[str, dict]:
        return {fid: self.capabilities(fid, fields) for fid in dict.fromkeys(file_ids)}

    def search(
        self,
        modified_after: Optional[str] = None,
        modified_before: Optional[str] = None,
        parent_id: Optional[str] = None,
        name_exact: Optional[str] = None,
        name_contains: Optional[str] = None,
        file_type: Optional[str] = None,
        include_trashed: bool = False,
        max_results: int = 1000,
    ) -> List[dict]:
        base = self.resolve_path(parent_id) if parent_id else self.root
        hits: List[dict] = []
        cap = max(1, int(max_results)) if max_results > 0 else 10_000
        for dirpath, dirnames, filenames in os.walk(base):
            cur_dir = Path(dirpath)
            candidates = [cur_dir / d for d in dirnames] + [cur_dir / f for f in filenames]
            for p in candidates:
                try:
                    rec = self._entry_dict(p)
                except OSError:
                    continue
                if file_type == "folder" and rec["mimeType"] != FOLDER_MIME:
                    continue
                if file_type and file_type != "folder" and file_type.lower() not in rec["mimeType"].lower() and not p.suffix.lower().endswith(file_type.lower()):
                    continue
                if name_exact and rec["name"] != name_exact:
                    continue
                if name_contains and name_contains.lower() not in rec["name"].lower():
                    continue
                if modified_after and rec["modifiedTime"] < modified_after:
                    continue
                if modified_before and rec["modifiedTime"] > modified_before:
                    continue
                hits.append(rec)
                if len(hits) >= cap:
                    return hits
        return hits

    def download(self, file_id: str, out: Path) -> Path:
        src = self.resolve_path(file_id)
        if not src.is_file():
            raise DriveError(f"Không thể tải tệp cục bộ (không phải tệp): `{src}`")
        dest = Path(out)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.resolve() != dest.resolve():
            shutil.copy2(src, dest)
        return dest

    def export(self, file_id: str, out: Path, fmt: str) -> Path:
        return self.download(file_id, out)

    def find_child(self, parent_id: str, name: str, folder_only: bool = False) -> Optional[dict]:
        parent = self.resolve_path(parent_id)
        cand = parent / name
        if not cand.exists():
            return None
        if folder_only and not cand.is_dir():
            return None
        return self._entry_dict(cand)

    def mkdir(self, name: str, parent_id: str) -> str:
        parent = self.resolve_path(parent_id)
        new_dir = parent / name
        new_dir.mkdir(parents=True, exist_ok=True)
        return make_local_id(self.root, new_dir)

    def ensure_folder(self, name: str, parent_id: str) -> str:
        found = self.find_child(parent_id, name, folder_only=True)
        return found["id"] if found else self.mkdir(name, parent_id)

    def upload(self, local: Path, parent_id: str, mime_type: Optional[str] = None) -> str:
        src = Path(local)
        dest = self.resolve_path(parent_id) / src.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        return make_local_id(self.root, dest)

    def update(self, file_id: str, local: Path, mime_type: Optional[str] = None) -> None:
        dest = self.resolve_path(file_id)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(Path(local), dest)

    def rename(self, file_id: str, new_name: str) -> None:
        src = self.resolve_path(file_id)
        if not src.exists():
            raise DriveError(f"Không tìm thấy mục cần đổi tên: `{src}`")
        dest = src.parent / new_name
        if dest.exists() and dest.resolve() != src.resolve():
            raise DriveError(f"Đích đổi tên đã tồn tại: `{dest}`")
        src.rename(dest)

    def move(self, file_id: str, new_parent_id: str) -> None:
        src = self.resolve_path(file_id)
        if not src.exists():
            raise DriveError(f"Không tìm thấy mục cần di chuyển: `{src}`")
        dest_dir = self.resolve_path(new_parent_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        if dest.exists() and dest.resolve() != src.resolve():
            # Tránh ghi đè âm thầm khi cách ly nhiều thư mục trùng tên (vd. nhiều thư mục `[02] MACOSX`)
            stem, suf = (src.name, "") if src.is_dir() else (src.stem, src.suffix)
            n = 2
            while (dest_dir / f"{stem} ({n}){suf}").exists():
                n += 1
            dest = dest_dir / f"{stem} ({n}){suf}"
        shutil.move(str(src), str(dest))

    def copy(self, file_id: str, new_name: str, parent_id: Optional[str] = None) -> str:
        src = self.resolve_path(file_id)
        dest_dir = self.resolve_path(parent_id) if parent_id else src.parent
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / new_name
        if src.is_dir():
            shutil.copytree(src, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dest)
        return make_local_id(self.root, dest)

    def create_shortcut(self, target_id: str, parent_id: str, shortcut_name: Optional[str] = None) -> str:
        src = self.resolve_path(target_id)
        dest_dir = self.resolve_path(parent_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        link = dest_dir / (shortcut_name or f"{src.name}.url")
        link.write_text(f"[InternetShortcut]\nURL={src.as_uri()}\n", encoding="utf-8")
        return make_local_id(self.root, link)

    def batch_rename(self, items: List[Tuple[str, str]]) -> List[Tuple[str, bool, str]]:
        out: List[Tuple[str, bool, str]] = []
        for fid, nm in items:
            try:
                self.rename(fid, nm)
                out.append((fid, True, ""))
            except Exception as exc:
                out.append((fid, False, str(exc)))
        return out

    def batch_move(self, items: List[Tuple[str, str]], workers: int = 8) -> List[Tuple[str, bool, str]]:
        out: List[Tuple[str, bool, str]] = []
        for fid, dest in items:
            try:
                self.move(fid, dest)
                out.append((fid, True, ""))
            except Exception as exc:
                out.append((fid, False, str(exc)))
        return out

    def batch_copy(
        self,
        items: List[Tuple[str, str, str]],
        workers: int = 8,
    ) -> List[Tuple[str, str, bool, str]]:
        out: List[Tuple[str, str, bool, str]] = []
        for src_id, new_name, dest_id in items:
            try:
                nid = self.copy(src_id, new_name, dest_id)
                out.append((src_id, nid, True, ""))
            except Exception as exc:
                out.append((src_id, "", False, str(exc)))
        return out
