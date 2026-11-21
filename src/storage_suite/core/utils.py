"""Các hàm tiện ích dùng chung: thời gian UTC+7, Unicode NFC, SHA-256, JSON/CSV/Markdown."""

from __future__ import annotations

import csv
import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import unicodedata
from pathlib import Path
from typing import Any, Iterable, List, Optional, Sequence

from storage_suite.core.config import FOLDER_MIME, SHEET_MIME

_TZ_VN = _dt.timezone(_dt.timedelta(hours=7))


def today_vn() -> str:
    return _dt.datetime.now(_TZ_VN).strftime("%d-%m-%Y")


def now_stamp() -> str:
    return _dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def now_utc_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso_utc(iso_str: Optional[str]) -> Optional[_dt.datetime]:
    s = (iso_str or "").strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt_obj = _dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt_obj.tzinfo is None:
        dt_obj = dt_obj.replace(tzinfo=_dt.timezone.utc)
    return dt_obj.astimezone(_TZ_VN)


def fmt_date_vn(iso_str: Optional[str]) -> str:
    dt_obj = _parse_iso_utc(iso_str)
    return dt_obj.strftime("%d-%m-%Y") if dt_obj else ""


def fmt_datetime_vn(iso_str: Optional[str]) -> str:
    dt_obj = _parse_iso_utc(iso_str)
    return dt_obj.strftime("%d-%m-%Y %H:%M (UTC+7)") if dt_obj else ""


def summarize_owners(meta: Optional[dict]) -> str:
    if not meta:
        return ""
    names: List[str] = []
    seen = set()
    for owner in meta.get("owners") or []:
        if not isinstance(owner, dict):
            continue
        label = (owner.get("displayName") or "").strip()
        if not label and owner.get("emailAddress"):
            label = owner["emailAddress"].split("@", 1)[0].strip()
        if label and label not in seen:
            seen.add(label)
            names.append(label)
    return ", ".join(names)


def summarize_sharing(meta: Optional[dict]) -> str:
    if not meta:
        return ""
    if "permissions" not in meta:
        return "Đã chia sẻ" if meta.get("shared") is True else ""
    perms = meta.get("permissions") or []
    public_part = ""
    viewers = 0
    commenters = 0
    editors = 0
    for p in perms:
        if not isinstance(p, dict):
            continue
        role = (p.get("role") or "").strip()
        ptype = (p.get("type") or "").strip()
        if role == "owner":
            continue
        if ptype == "anyone" or p.get("id") == "anyoneWithLink":
            if role in ("writer", "organizer", "fileOrganizer"):
                public_part = "Công khai qua link (sửa)"
            elif role == "commenter":
                public_part = "Công khai qua link (nhận xét)"
            else:
                public_part = "Công khai qua link (xem)"
        else:
            if role in ("writer", "organizer", "fileOrganizer"):
                editors += 1
            elif role == "commenter":
                commenters += 1
            else:
                viewers += 1
    internal_parts: List[str] = []
    if viewers:
        internal_parts.append(f"{viewers} xem")
    if commenters:
        internal_parts.append(f"{commenters} nhận xét")
    if editors:
        internal_parts.append(f"{editors} sửa")
    total_int = viewers + commenters + editors
    if public_part and total_int:
        return f"{public_part} + {total_int} nội bộ ({', '.join(internal_parts)})"
    if public_part:
        return public_part
    if total_int:
        return f"Chia sẻ nội bộ ({', '.join(internal_parts)})"
    return "Riêng tư (chỉ chủ sở hữu)"


def human_size(n: Optional[float]) -> str:
    val = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if val < 1024 or unit == "TB":
            return f"{val:.0f} {unit}" if unit == "B" else f"{val:.2f} {unit}"
        val /= 1024
    return f"{val:.2f} TB"


def fmt_int(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def strip_accents(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


_RE_DRIVE_URL_ID = re.compile(r"(?:/folders/|/d/|id=)([A-Za-z0-9_-]{20,})")


def extract_drive_id(id_or_url: str) -> str:
    s = (id_or_url or "").strip()
    if not s:
        return ""
    m = _RE_DRIVE_URL_ID.search(s)
    return m.group(1) if m else s


def drive_url(item_id: str, mime_type: str = "") -> str:
    if mime_type == FOLDER_MIME:
        return f"https://drive.google.com/drive/folders/{item_id}"
    if mime_type == "application/vnd.google-apps.document":
        return f"https://docs.google.com/document/d/{item_id}/edit"
    if mime_type == SHEET_MIME:
        return f"https://docs.google.com/spreadsheets/d/{item_id}/edit"
    if mime_type == "application/vnd.google-apps.presentation":
        return f"https://docs.google.com/presentation/d/{item_id}/edit"
    return f"https://drive.google.com/file/d/{item_id}/view"


def log(msg: str) -> None:
    print(msg, flush=True)


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def write_json(path: Path, data: Any, indent: Optional[int] = 1) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", dir=str(path.parent))
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)
    os.replace(tmp, path)


def write_csv(path: Path, header: Sequence[str], rows: Iterable[Sequence[Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow(r)


def md_table(header: Sequence[str], rows: Iterable[Sequence[Any]], align: Optional[Sequence[str]] = None) -> str:
    def esc(v: Any) -> str:
        return str(v).replace("|", "\\|").replace("\n", " ")

    align = align or ["l"] * len(header)
    sep = {"l": ":---", "r": "---:", "c": ":---:"}
    out = [
        "| " + " | ".join(esc(h) for h in header) + " |",
        "| " + " | ".join(sep.get(a, ":---") for a in align) + " |",
    ]
    for r in rows:
        out.append("| " + " | ".join(esc(v) for v in r) + " |")
    return "\n".join(out)


def confirm(prompt: str, assume_yes: bool = False) -> bool:
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        log(f"{prompt} → bỏ qua (không có terminal tương tác; dùng --dong-y để xác nhận).")
        return False
    ans = input(f"{prompt} [y/N]: ").strip().lower()
    return ans in ("y", "yes", "c", "co", "có")


def publish_file(drive: Any, local: Path, parent_id: str, name: Optional[str] = None) -> str:
    """Tải tệp lên thư mục đích; nếu đã có tệp trùng tên thì cập nhật tại chỗ (giữ ID/URL)."""
    local = Path(local)
    target_name = name or local.name
    tmp_dir: Optional[Path] = None
    try:
        if name and name != local.name:
            tmp_dir = Path(tempfile.mkdtemp(prefix="publish_"))
            staged = tmp_dir / name
            shutil.copyfile(local, staged)
            local = staged
        existing = drive.find_child(parent_id, target_name)
        if existing:
            drive.update(existing["id"], local)
            return existing["id"]
        return drive.upload(local, parent_id)
    finally:
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)
