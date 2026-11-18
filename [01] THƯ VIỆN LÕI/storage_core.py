#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
THƯ VIỆN LÕI — BỘ CHƯƠNG TRÌNH QUẢN LÝ [A] STORAGE (CHUẨN V6, v3.0)
====================================================================
Module dùng chung cho mọi chương trình trong `[00] TỔNG QUAN/[03] QUẢN LÝ` (`[01]`–`[12]`).

Cung cấp:
- Nạp cấu hình tập trung từ `storage_config.json` (ID kho, `[07] KIỂM TRA`, `[04] NHẬP DỮ LIỆU`, viết tắt, ngoại lệ kỹ thuật).
- Lớp `Drive`: gọi trực tiếp binary Go `gdrive` đã cache, hỗ trợ:
  • `stream_ls`, `stream_info`, `stream_capabilities` (`gdrive readonly stream -c 32`, tăng tốc 2–10×)
  • `search` có tự động phân trang theo cửa sổ thời gian `modified_before` khi vượt 100 kết quả
  • `copy`, `batch_copy`, `move`, `batch_move`, `rename`, `batch_rename`, `create_shortcut`
- Đọc/ghi chỉ mục `storage_index.json` nguyên tử, `build_id_map`, `extract_drive_id`, `next_available_stt`.
- Bộ luật kiểm tra quy ước đặt tên Chuẩn V6 (`check_folder_name`, `check_file_name`, `safe_fix_name`)
  kèm bảo vệ cụm từ dễ nhầm (`Tử Vi`, `Phi Tinh`, `The Ego`, `Việt Nam`, tiếng Tây Ban Nha có dấu).
"""

from __future__ import annotations

import concurrent.futures as cf
import csv
import datetime as _dt
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

__version__ = "3.2.0"

# ---------------------------------------------------------------------------
# 1. NẠP CẤU HÌNH KHO
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG: Dict[str, Any] = {
    "version": __version__,
    "root_name": "[A] STORAGE",
    "root_id": "194HC3C2WC1BSzfK3cn_0_uUJ4vfDuBsr",
    "tong_quan_folder": "[00] TỔNG QUAN",
    "quarantine_folder": "[07] KIỂM TRA",
    "github_repo": "kariusnocr/storage-management-suite",
    "github_default_branch": "main",
    "known_ids": {
        "[00] TỔNG QUAN": "1ZLU1RnH4PpJ--CXXPjrum7uxncbOttZU",
        "[00] TỔNG QUAN/[01] DANH SÁCH": "1GqdqbI1yVPD3e-HAenW6WioSQZpPaRYz",
        "[00] TỔNG QUAN/[02] NHẬT KÍ": "10FI7CMFvGgM9i1rj4IkUFRESv5-ito2Y",
        "[00] TỔNG QUAN/[03] QUẢN LÝ": "1dU9BqIFxdLyhsFzxZxOiKWVNHI0vk7W3",
        "[07] KIỂM TRA": "1dpIWrMRwREX-bSt4k-PxSzVxbLrj3XLy",
        "[99] KIỂM TRA": "1dpIWrMRwREX-bSt4k-PxSzVxbLrj3XLy",
        "[07] KIỂM TRA/[00] TỔNG QUAN": "1diW_N3ZSfgqunXogD3aRErJjGfRv8QMd",
        "[07] KIỂM TRA/[01] SHORTCUT LỖI 404": "1_o38THe5uq1ZDaiSH9l1QdSJZ0ZMlsAr",
        "[07] KIỂM TRA/[02] SHORTCUT ĐÃ SAO CHÉP": "1Mp-kCOZkl2MBSihpHBCdARGhVtA6DuxH",
        "[07] KIỂM TRA/[03] TỆP TRÙNG LẶP": "1oT10jMXJuS_Av8y_bAzPC_PVZzuj5LXK",
        "[07] KIỂM TRA/[03] TỆP TRÙNG LẶP/[01] TỔNG QUAN TRÙNG LẶP": "17WTrOaBVrL1vSG1GEQ5RJ53RZLjbmD0O",
        "[07] KIỂM TRA/[04] NHẬP DỮ LIỆU": "1Xhgp46XpL3ng_l_d-_-wHb4S12DTuPri",
    },
    "master_sheet_id": "1BJoV-UtcoSEdjq1w5e0HmfibyTdvLEX8cy22jeKKnDc",
    "master_sheet_list_id": "1Pakm-B2FZFFNOsxct_aRmFm2DDQxsQiVsiwB_l2xQt4",
    "quarantine_subfolders": {
        "broken_shortcut": "[01] SHORTCUT LỖI 404",
        "redundant_shortcut": "[02] SHORTCUT ĐÃ SAO CHÉP",
        "duplicate": "[03] TỆP TRÙNG LẶP",
        "duplicate_tongquan": "[01] TỔNG QUAN TRÙNG LẶP",
        "ingest": "[04] NHẬP DỮ LIỆU",
        "empty_folder": "[05] THƯ MỤC RỖNG",
    },
    "tech_exception_path_markers": [
        ".obsidian",
        "MÃ NGUỒN PYTHON",
        "DỰ ÁN SỐ HÓA",
        "OCR CHUẨN HOÁ",
        "[00] TỔNG QUAN/[03] QUẢN LÝ",
    ],
    "title_exceptions": [
        "a", "an", "and", "as", "at", "by", "for", "in", "of", "on", "or",
        "the", "to", "vs", "via", "de", "du", "la", "le", "von", "van",
        "der", "e", "et", "x", "y", "del", "las", "los", "al", "con", "en", "para", "por",
    ],
    "lowercase_prefix_words": [
        "e-business", "e-book", "ebook", "ebooks", "e-learning", "ios",
        "iphone", "ipad", "macos", "imac", "icloud", "wifi",
    ],
    "acronyms_upper": {
        "ussh": "USSH", "vnu": "VNU", "ulis": "ULIS", "uel": "UEL", "ueb": "UEB", "uet": "UET",
        "ielts": "IELTS", "toefl": "TOEFL", "toeic": "TOEIC", "hsk": "HSK", "hskk": "HSKK",
        "thpt": "THPT", "thptqg": "THPTQG", "tnthpt": "TN THPT", "thcs": "THCS",
        "thcsthpt": "THCS - THPT", "kscl": "KSCL", "hsa": "HSA", "tsa": "TSA",
        "gtnn": "GTNN", "gtln": "GTLN", "gd": "GD", "dt": "ĐT", "gddt": "GD&ĐT",
        "bgddt": "BGD&ĐT", "dh": "ĐH", "dhqghn": "ĐHQGHN", "khxh": "KHXH", "khxhnv": "KHXH&NV",
        "cnxhkh": "CNXHKH", "ktct": "KTCT", "tthcm": "TTHCM", "lsd": "LSĐ", "btvn": "BTVN",
        "ctdt": "CTĐT", "ktdg": "KTĐG", "knm": "KNM", "lms": "LMS", "unesco": "UNESCO",
        "ds": "DS", "ocr": "OCR", "asr": "ASR", "pdf": "PDF", "epub": "EPUB", "mobi": "MOBI",
        "azw3": "AZW3", "djvu": "DJVU", "docx": "DOCX", "xlsx": "XLSX", "pptx": "PPTX",
        "mp3": "MP3", "mp4": "MP4", "wav": "WAV", "zip": "ZIP", "rar": "RAR",
        "json": "JSON", "csv": "CSV", "nxb": "NXB", "gs": "GS", "pgs": "PGS", "ts": "TS",
        "ths": "ThS", "sv": "SV", "gv": "GV", "clb": "CLB", "drl": "ĐRL",
        "hk": "HK", "hk1": "HK1", "hk2": "HK2", "k70": "K70", "k71": "K71", "k29": "K29",
        "a1": "A1", "a2": "A2", "b1": "B1", "b2": "B2", "c1": "C1", "c2": "C2",
        "vstep": "VSTEP", "sat": "SAT", "act": "ACT", "gre": "GRE", "gmat": "GMAT",
        "autocad": "AutoCAD", "wps": "WPS", "nhlb": "NHLB", "lb": "LB", "vtv": "VTV",
        "ai": "AI", "it": "IT", "pc": "PC", "id": "ID", "url": "URL", "sha256": "SHA-256",
        "pep": "PEP", "cli": "CLI", "dgnl": "ĐGNL", "dgtd": "ĐGTD", "obe": "OBE", "tdm": "TDM",
        "nlxh": "NLXH", "gdkpl": "GDKPL", "gdkt": "GDKT", "tbt": "TBT", "tts": "TTS", "mh": "MH",
        "vp": "VP", "ftu": "FTU", "hsk1": "HSK1", "hsk2": "HSK2", "hsk3": "HSK3",
        "lic": "LIC", "vip": "VIP",
        "vn": "VN", "kntt": "KNTT", "ctst": "CTST", "cd": "CD", "sn": "SN",
        "ii": "II", "iii": "III", "iv": "IV", "vii": "VII",
        "viii": "VIII", "ix": "IX", "xi": "XI", "xii": "XII",
    },
    "dedup": {
        "min_suspect_bytes": 1048576,
        "exclude_markers": [
            "[A] STORAGE/[07] KIỂM TRA",
            "[A] STORAGE/[99] KIỂM TRA",
            "/[00] TỔNG QUAN",
            ".obsidian",
            "MÃ NGUỒN PYTHON",
            "DỰ ÁN SỐ HÓA",
            "[00] TỔNG QUAN/[03] QUẢN LÝ",
        ],
    },
    "incremental_scan": {
        "full_scan_threshold_folders": 200,
        "lookback_overlap_seconds": 90,
        "stream_concurrency": 32,
    },
}


def config_path() -> Path:
    env = os.environ.get("STORAGE_CONFIG_PATH")
    if env:
        return Path(env).expanduser()
    return Path(__file__).resolve().parent / "storage_config.json"


def load_config() -> Dict[str, Any]:
    cfg = json.loads(json.dumps(_DEFAULT_CONFIG))
    p = config_path()
    if p.exists():
        try:
            override = json.loads(p.read_text(encoding="utf-8"))
            for k, v in override.items():
                if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                    cfg[k].update(v)
                else:
                    cfg[k] = v
        except Exception:
            pass
    return cfg


CONFIG: Dict[str, Any] = load_config()

ROOT_NAME = CONFIG["root_name"]
ROOT_ID = os.environ.get("STORAGE_ROOT_ID", CONFIG["root_id"])
KNOWN_IDS: Dict[str, str] = dict(CONFIG["known_ids"])
MASTER_SHEET_ID = CONFIG["master_sheet_id"]
MASTER_SHEET_LIST_ID = CONFIG["master_sheet_list_id"]

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
TONG_QUAN_FOLDER = CONFIG["tong_quan_folder"]
QUARANTINE_FOLDER = CONFIG.get("quarantine_folder", "[07] KIỂM TRA")
QUARANTINE_MARKERS = ("[07] KIỂM TRA", "[99] KIỂM TRA")


def is_quarantine_path(path: str) -> bool:
    """Trả về True nếu đường dẫn thuộc khu vực kiểm tra/cách ly (`[07] KIỂM TRA` hoặc `[99] KIỂM TRA` cũ)."""
    return any(m in path for m in QUARANTINE_MARKERS)


def quarantine_root_id() -> str:
    """ID thư mục gốc `[07] KIỂM TRA` (`1dpIWrMRwREX-bSt4k-PxSzVxbLrj3XLy`)."""
    return os.environ.get(
        "STORAGE_QUARANTINE_ID",
        KNOWN_IDS.get("[07] KIỂM TRA") or KNOWN_IDS.get("[99] KIỂM TRA", "1dpIWrMRwREX-bSt4k-PxSzVxbLrj3XLy"),
    )


def ingest_folder_id() -> str:
    """ID thư mục tiếp nhận dữ liệu mới `[07] KIỂM TRA/[04] NHẬP DỮ LIỆU`."""
    return os.environ.get(
        "STORAGE_INGEST_ID",
        KNOWN_IDS.get("[07] KIỂM TRA/[04] NHẬP DỮ LIỆU", "1Xhgp46XpL3ng_l_d-_-wHb4S12DTuPri"),
    )


def data_dir() -> Path:
    """Thư mục dữ liệu cục bộ (chỉ mục, kế hoạch, báo cáo). Ghi đè bằng `STORAGE_DATA_DIR`."""
    p = Path(os.environ.get("STORAGE_DATA_DIR", str(Path.home() / "storage_data"))).expanduser()
    p.mkdir(parents=True, exist_ok=True)
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


def sheets_log_path() -> Path:
    """Bản đồ <đường dẫn thư mục> → bảng `Danh Mục Hệ Thống`."""
    return data_dir() / "uploaded_sheets_log.json"


def shortcut_cache_path() -> Path:
    return data_dir() / "shortcut_cache.json"


def transfer_log_path() -> Path:
    return data_dir() / "transfer_log.json"


def ingest_log_path() -> Path:
    return data_dir() / "ingest_log.json"


def content_cache_dir() -> Path:
    """Thư mục lưu bộ đệm trích xuất nội dung & siêu dữ liệu (`records/` và `text/`)."""
    p = data_dir() / "content_cache"
    (p / "records").mkdir(parents=True, exist_ok=True)
    (p / "text").mkdir(parents=True, exist_ok=True)
    return p


def content_rename_log_path() -> Path:
    """Nhật kí đổi tên dựa trên siêu dữ liệu nội dung (hỗ trợ hoàn tác 1 lệnh)."""
    return data_dir() / "content_rename_log.json"


def github_repo() -> str:
    """Tên kho lưu trữ GitHub kết nối (`owner/repo`)."""
    return os.environ.get("STORAGE_GITHUB_REPO", CONFIG.get("github_repo", "kariusnocr/storage-management-suite"))


def github_sync_log_path() -> Path:
    """Nhật kí đồng bộ Git / GitHub."""
    return data_dir() / "github_sync_log.json"


# ---------------------------------------------------------------------------
# 2. TIỆN ÍCH CHUNG
# ---------------------------------------------------------------------------

def today_vn() -> str:
    return _dt.datetime.now().strftime("%d-%m-%Y")


def now_stamp() -> str:
    return _dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def now_utc_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def human_size(n: Optional[float]) -> str:
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.2f} {unit}"
        n /= 1024
    return f"{n:.2f} TB"


def fmt_int(n: int) -> str:
    """Định dạng số kiểu Việt Nam: 21602 → 21.602"""
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


_RE_DRIVE_URL_ID = re.compile(
    r"(?:/folders/|/d/|id=)([A-Za-z0-9_-]{20,})"
)


def extract_drive_id(id_or_url: str) -> str:
    """Trích xuất ID Google Drive từ chuỗi ID thuần hoặc URL Drive/Docs/Sheets/Slides."""
    s = (id_or_url or "").strip()
    if not s:
        return ""
    m = _RE_DRIVE_URL_ID.search(s)
    if m:
        return m.group(1)
    return s


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
    """Ghi JSON nguyên tử (ghi ra tệp tạm rồi đổi tên) để tránh hỏng tệp khi bị ngắt."""
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
    """Tạo bảng Markdown. align: danh sách 'l' | 'r' | 'c'."""
    def esc(v: Any) -> str:
        return str(v).replace("|", "\\|").replace("\n", " ")

    align = align or ["l"] * len(header)
    sep = {"l": ":---", "r": "---:", "c": ":---:"}
    out = ["| " + " | ".join(esc(h) for h in header) + " |",
           "| " + " | ".join(sep.get(a, ":---") for a in align) + " |"]
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


# ---------------------------------------------------------------------------
# 3. LỚP GỌI GOOGLE DRIVE (qua binary gdrive đã cache + stream đa luồng)
# ---------------------------------------------------------------------------

class DriveError(RuntimeError):
    pass


_RETRYABLE = ("rateLimitExceeded", "userRateLimitExceeded", "backendError", "internalError",
              "500", "502", "503", "504", "timeout", "TLS handshake", "connection reset", "EOF")


def find_gdrive_bin() -> str:
    """Ưu tiên gọi trực tiếp binary Go đã cache để bỏ qua shell launcher ở hàng nghìn lệnh con."""
    env = os.environ.get("GDRIVE_BIN")
    if env and os.path.exists(env):
        return env

    candidate_globs = []
    app_dir = os.environ.get("ANTIGRAVITY_APP_DATA_DIR")
    if app_dir:
        candidate_globs.append(str(Path(app_dir) / "plugin_data/gdrive/bin/gdrive-*"))
    candidate_globs.extend([
        "/opt/antigravity/plugin_data/gdrive/bin/gdrive-*",
        str(Path.home() / ".gemini/antigravity/plugin_data/gdrive/bin/gdrive-*"),
    ])
    for pattern in candidate_globs:
        matches = sorted((p for p in glob.glob(pattern) if os.access(p, os.X_OK)), reverse=True)
        if matches:
            return matches[0]

    found = shutil.which("gdrive")
    if found:
        return found
    for cand in ("/opt/antigravity/bin/gdrive",):
        if os.path.exists(cand):
            return cand
    raise DriveError("Không tìm thấy CLI `gdrive`. Đặt biến môi trường GDRIVE_BIN hoặc thêm gdrive vào PATH.")


class Drive:
    """Bao bọc CLI `gdrive` với cơ chế thử lại theo cấp số và hỗ trợ `readonly stream` tốc độ cao."""

    def __init__(self, retries: int = 5, timeout: int = 180, bin_path: Optional[str] = None):
        self.bin = bin_path or find_gdrive_bin()
        self.retries = retries
        self.timeout = timeout

    # -- thấp tầng ----------------------------------------------------------
    def run(
        self,
        args: Sequence[str],
        as_json: bool = False,
        timeout: Optional[int] = None,
        stdin_text: Optional[str] = None,
    ) -> Any:
        cmd = [self.bin] + (["--json"] if as_json else []) + list(args)
        last_err = ""
        for attempt in range(self.retries):
            try:
                proc = subprocess.run(
                    cmd,
                    input=stdin_text,
                    capture_output=True,
                    text=True,
                    timeout=timeout or self.timeout,
                )
            except subprocess.TimeoutExpired:
                last_err = "timeout"
                time.sleep(min(30, 2 ** attempt))
                continue
            if proc.returncode == 0:
                out = proc.stdout
                if not as_json:
                    return out
                out = out.strip()
                if not out:
                    return None
                try:
                    return json.loads(out)
                except json.JSONDecodeError:
                    start = min([i for i in (out.find("["), out.find("{")) if i >= 0], default=-1)
                    if start >= 0:
                        return json.loads(out[start:])
                    raise DriveError(f"Không đọc được JSON từ: {' '.join(cmd)}\n{out[:500]}")
            last_err = (proc.stderr or proc.stdout or "").strip()
            if any(k.lower() in last_err.lower() for k in _RETRYABLE):
                time.sleep(min(30, 1.5 * (2 ** attempt)))
                continue
            break
        raise DriveError(f"Lỗi gdrive ({' '.join(args[:2])}): {last_err[:800]}")

    # -- đọc đơn & đọc luồng (stream) ---------------------------------------
    def ls(self, folder_id: str) -> List[dict]:
        # CLI trả tối đa 20 mục nếu không truyền --max; truyền --max 0 để lấy toàn bộ trang.
        res = self.run(["readonly", "ls", folder_id, "--max", "0"], as_json=True)
        if isinstance(res, dict):
            res = res.get("files", [])
        return res or []

    def stream_ls(
        self,
        folder_ids: Sequence[str],
        concurrency: int = 32,
        timeout: int = 600,
    ) -> Tuple[Dict[str, List[dict]], Dict[str, str]]:
        """
        Quét đồng thời danh sách thư mục trong 1 tiến trình Go duy nhất (`gdrive readonly stream ls`).
        Trả về `(items_by_folder_id, errors_by_folder_id)`.
        """
        unique_ids = list(dict.fromkeys(fid for fid in folder_ids if fid))
        if not unique_ids:
            return {}, {}
        if len(unique_ids) == 1:
            fid = unique_ids[0]
            try:
                return {fid: self.ls(fid)}, {}
            except DriveError as e:
                return {}, {fid: str(e)}

        out_map: Dict[str, List[dict]] = {}
        err_map: Dict[str, str] = {}
        c = max(1, min(64, int(concurrency)))
        stdin_payload = "\n".join(unique_ids) + "\n"
        try:
            raw = self.run(
                ["readonly", "stream", "ls", "-i", "-", "--max", "0", "-c", str(c)],
                as_json=False,
                timeout=timeout,
                stdin_text=stdin_payload,
            ) or ""
            for line in raw.splitlines():
                line = line.strip()
                if not line or not line.startswith("{"):
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                fid = rec.get("input", "")
                if not fid:
                    continue
                if rec.get("status") == "ok":
                    data = rec.get("data")
                    if isinstance(data, dict):
                        data = data.get("files", [])
                    out_map[fid] = data or []
                else:
                    err_map[fid] = str(rec.get("error") or "stream_ls_error")
        except DriveError:
            pass

        # Thử lại bằng `self.ls` cho các thư mục bị sót hoặc báo lỗi tạm thời
        missing = [fid for fid in unique_ids if fid not in out_map]
        if missing:
            def _fallback_one(fid: str):
                try:
                    return fid, self.ls(fid), ""
                except DriveError as e:
                    return fid, None, str(e)

            with cf.ThreadPoolExecutor(max_workers=min(16, len(missing))) as pool:
                for fid, items, err in pool.map(_fallback_one, missing):
                    if items is not None:
                        out_map[fid] = items
                        err_map.pop(fid, None)
                    else:
                        err_map[fid] = err
        return out_map, err_map

    def stream_info(
        self,
        file_ids: Sequence[str],
        concurrency: int = 32,
        timeout: int = 600,
    ) -> Dict[str, dict]:
        """Lấy metadata hàng loạt trong 1 tiến trình Go (`gdrive readonly stream info`)."""
        unique_ids = list(dict.fromkeys(fid for fid in file_ids if fid))
        if not unique_ids:
            return {}
        if len(unique_ids) == 1:
            fid = unique_ids[0]
            try:
                return {fid: self.info(fid)}
            except DriveError:
                return {}

        out_map: Dict[str, dict] = {}
        c = max(1, min(64, int(concurrency)))
        stdin_payload = "\n".join(unique_ids) + "\n"
        try:
            raw = self.run(
                ["readonly", "stream", "info", "-i", "-", "-c", str(c)],
                as_json=False,
                timeout=timeout,
                stdin_text=stdin_payload,
            ) or ""
            for line in raw.splitlines():
                line = line.strip()
                if not line or not line.startswith("{"):
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                fid = rec.get("input", "")
                if fid and rec.get("status") == "ok" and isinstance(rec.get("data"), dict):
                    out_map[fid] = rec["data"]
        except DriveError:
            for fid in unique_ids:
                try:
                    out_map[fid] = self.info(fid)
                except DriveError:
                    pass
        return out_map

    def stream_capabilities(
        self,
        file_ids: Sequence[str],
        fields: str = "canMoveItemOutOfDrive,canEdit,canTrash",
        concurrency: int = 32,
        timeout: int = 600,
    ) -> Dict[str, dict]:
        """Kiểm tra quyền hàng loạt trong 1 tiến trình Go (`gdrive readonly stream capabilities`)."""
        unique_ids = list(dict.fromkeys(fid for fid in file_ids if fid))
        if not unique_ids:
            return {}
        if len(unique_ids) == 1:
            fid = unique_ids[0]
            try:
                return {fid: self.capabilities(fid, fields)}
            except DriveError:
                return {}

        out_map: Dict[str, dict] = {}
        c = max(1, min(64, int(concurrency)))
        args = ["readonly", "stream", "capabilities", "-i", "-", "-c", str(c)]
        if fields:
            args += ["--filter", fields]
        stdin_payload = "\n".join(unique_ids) + "\n"
        try:
            raw = self.run(args, as_json=False, timeout=timeout, stdin_text=stdin_payload) or ""
            for line in raw.splitlines():
                line = line.strip()
                if not line or not line.startswith("{"):
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                fid = rec.get("input", "")
                if fid and rec.get("status") == "ok" and isinstance(rec.get("data"), dict):
                    data = rec["data"]
                    caps = data.get("capabilities") if isinstance(data.get("capabilities"), dict) else data
                    out_map[fid] = caps if isinstance(caps, dict) else {}
        except DriveError:
            for fid in unique_ids:
                try:
                    out_map[fid] = self.capabilities(fid, fields)
                except DriveError:
                    pass
        return out_map

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
        """
        Tìm kiếm tệp/thư mục trên Drive.
        Vì `gdrive readonly search` giới hạn tối đa 100 mục/lần gọi (sắp xếp `modifiedTime desc`),
        khi `max_results > 100` hàm tự động trượt cửa sổ `modified_before` để lấy đủ các trang tiếp theo.
        """
        target_max = 1000 if max_results <= 0 else int(max_results)
        per_call = min(1000, target_max)
        collected: List[dict] = []
        seen_ids = set()
        cur_before = modified_before
        max_pages = max(1, (target_max + 99) // 100)

        for _ in range(max_pages):
            args = ["readonly", "search", "--max", str(per_call)]
            if modified_after:
                args += ["--modified-after", modified_after]
            if cur_before:
                args += ["--modified-before", cur_before]
            if parent_id:
                args += ["--parent-id", parent_id]
            if name_exact:
                args += ["--name-exact", name_exact]
            if name_contains:
                args += ["--name-contains", name_contains]
            if file_type:
                args += ["--type", file_type]
            if include_trashed:
                args.append("--include-trashed")

            res = self.run(args, as_json=True)
            if isinstance(res, dict):
                res = res.get("files", [])
            page = res or []
            new_in_page = 0
            for it in page:
                fid = it.get("id")
                if fid and fid not in seen_ids:
                    seen_ids.add(fid)
                    collected.append(it)
                    new_in_page += 1
                    if len(collected) >= target_max:
                        return collected

            # Nếu trang trả về < 100 mục hoặc không có modifiedTime để trượt cửa sổ thì dừng
            if len(page) < 100 or new_in_page == 0:
                break
            mods = [it.get("modifiedTime", "").rstrip("Z") for it in page if it.get("modifiedTime")]
            if not mods:
                break
            min_mod = min(mods)
            if cur_before and min_mod >= cur_before:
                break
            cur_before = min_mod

        return collected

    def info(self, file_id: str) -> dict:
        return self.run(["readonly", "info", file_id], as_json=True) or {}

    def capabilities(self, file_id: str, fields: str = "canMoveItemOutOfDrive,canEdit,canTrash") -> dict:
        args = ["readonly", "capabilities", file_id]
        if fields:
            args += ["--filter", fields]
        res = self.run(args, as_json=True) or {}
        if isinstance(res, dict) and "capabilities" in res and isinstance(res["capabilities"], dict):
            return res["capabilities"]
        return res if isinstance(res, dict) else {}

    def download(self, file_id: str, out: Path) -> Path:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        self.run(["readonly", "download", file_id, "--out", str(out)])
        return Path(out)

    def export(self, file_id: str, out: Path, fmt: str) -> Path:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        self.run(["readonly", "export", file_id, str(out), "--format", fmt])
        return Path(out)

    def find_child(self, parent_id: str, name: str, folder_only: bool = False) -> Optional[dict]:
        target = nfc(name)
        for it in self.ls(parent_id):
            if nfc(it.get("name", "")) == target and (not folder_only or it.get("mimeType") == FOLDER_MIME):
                return it
        return None

    # -- ghi ----------------------------------------------------------------
    def mkdir(self, name: str, parent_id: str) -> str:
        out = self.run(["mutate", "mkdir", name, "--parent", parent_id], as_json=False) or ""
        m = re.search(r"\b([A-Za-z0-9_-]{25,})\b", out)
        found = self.find_child(parent_id, name, folder_only=True)
        if found:
            return found["id"]
        if m:
            return m.group(1)
        raise DriveError(f"Không xác định được ID thư mục vừa tạo: {name}")

    def ensure_folder(self, name: str, parent_id: str) -> str:
        found = self.find_child(parent_id, name, folder_only=True)
        return found["id"] if found else self.mkdir(name, parent_id)

    def upload(self, local: Path, parent_id: str, mime_type: Optional[str] = None) -> str:
        args = ["mutate", "upload", str(local), "--parent", parent_id]
        if mime_type:
            args += ["--mime-type", mime_type]
        out = self.run(args, as_json=False) or ""
        found = self.find_child(parent_id, Path(local).name)
        if found:
            return found["id"]
        m = re.search(r"\b([A-Za-z0-9_-]{25,})\b", out)
        return m.group(1) if m else ""

    def update(self, file_id: str, local: Path, mime_type: Optional[str] = None) -> None:
        args = ["mutate", "update", file_id, str(local)]
        if mime_type:
            args += ["--mime-type", mime_type]
        self.run(args)

    def rename(self, file_id: str, new_name: str) -> None:
        self.run(["mutate", "rename", file_id, new_name])

    def move(self, file_id: str, new_parent_id: str) -> None:
        self.run(["mutate", "mv", file_id, new_parent_id])

    def copy(self, file_id: str, new_name: str, parent_id: Optional[str] = None) -> str:
        """Sao chép tệp phía máy chủ (`gdrive mutate cp`) và trả về ID bản sao mới."""
        args = ["mutate", "cp", file_id, new_name]
        if parent_id:
            args += ["--parent", parent_id]
        out = self.run(args, as_json=False) or ""
        m = re.search(r"\b([A-Za-z0-9_-]{25,})\b", out)
        if parent_id:
            found = self.find_child(parent_id, new_name)
            if found:
                return found["id"]
        return m.group(1) if m else ""

    def create_shortcut(self, target_id: str, parent_id: str, shortcut_name: Optional[str] = None) -> str:
        """Tạo shortcut trỏ tới `target_id` trong `parent_id` (và đổi tên nếu truyền `shortcut_name`)."""
        out = self.run(["mutate", "create-shortcut", target_id, parent_id], as_json=False) or ""
        m = re.search(r"\b([A-Za-z0-9_-]{25,})\b", out)
        sc_id = m.group(1) if m else ""
        if not sc_id:
            for it in self.ls(parent_id):
                if it.get("mimeType") == SHORTCUT_MIME:
                    sc_id = it["id"]
                    break
        if sc_id and shortcut_name:
            self.rename(sc_id, shortcut_name)
        return sc_id

    def batch_rename(self, items: List[Tuple[str, str]]) -> List[Tuple[str, bool, str]]:
        """Đổi tên theo lô bằng `gdrive mutate batch`; mục chưa xong được thử lại tuần tự."""
        if not items:
            return []
        ops = [{"op": "rename", "id": fid, "fileId": fid, "name": nm, "target": nm} for fid, nm in items]
        fd, tmp = tempfile.mkstemp(prefix="gdrive_batch_", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(ops, f, ensure_ascii=False)
        done_idx = set()
        try:
            proc = subprocess.run([self.bin, "mutate", "batch", "-f", tmp], capture_output=True, text=True, timeout=300)
            out = (proc.stdout or "") + "\n" + (proc.stderr or "")
            if proc.returncode == 0 and f"Executed {len(items)} operations" in out:
                return [(fid, True, "") for fid, _ in items]
            done_idx = {int(m.group(1)) for m in re.finditer(r"^\[(\d+)\]\s+Renamed\s+", out, flags=re.M)}
        except Exception:
            pass
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
        results = []
        for i, (fid, nm) in enumerate(items):
            if i in done_idx:
                results.append((fid, True, ""))
                continue
            try:
                self.rename(fid, nm)
                results.append((fid, True, ""))
            except DriveError as e:
                results.append((fid, False, str(e)))
        return results

    def batch_move(self, items: List[Tuple[str, str]], workers: int = 8) -> List[Tuple[str, bool, str]]:
        """Di chuyển hàng loạt `(file_id, new_parent_id)` dùng binary Go trực tiếp."""
        if not items:
            return []

        def one(pair: Tuple[str, str]) -> Tuple[str, bool, str]:
            fid, dest_id = pair
            try:
                self.move(fid, dest_id)
                return fid, True, ""
            except DriveError as e:
                return fid, False, str(e)

        with cf.ThreadPoolExecutor(max_workers=max(1, min(workers, len(items)))) as pool:
            return list(pool.map(one, items))

    def batch_copy(
        self,
        items: List[Tuple[str, str, str]],
        workers: int = 8,
    ) -> List[Tuple[str, str, bool, str]]:
        """
        Sao chép hàng loạt `(source_id, new_name, dest_parent_id)`.
        Trả về `[(source_id, new_file_id, success, error_msg)]`.
        """
        if not items:
            return []

        def one(triple: Tuple[str, str, str]) -> Tuple[str, str, bool, str]:
            src_id, new_name, dest_id = triple
            try:
                new_id = self.copy(src_id, new_name, dest_id)
                return src_id, new_id, True, ""
            except DriveError as e:
                return src_id, "", False, str(e)

        with cf.ThreadPoolExecutor(max_workers=max(1, min(workers, len(items)))) as pool:
            return list(pool.map(one, items))


# ---------------------------------------------------------------------------
# 4. CHỈ MỤC KHO
# ---------------------------------------------------------------------------

Index = Dict[str, Dict[str, Any]]


def load_index(path: Optional[Path] = None, required: bool = True) -> Index:
    p = Path(path) if path else index_path()
    data = read_json(p)
    if data is None:
        if required:
            raise SystemExit(f"Chưa có chỉ mục tại {p}. Hãy chạy chương trình [02] QUÉT CHỈ MỤC trước.")
        return {}
    if isinstance(data, dict) and "folders" in data and "meta" in data:
        data = data["folders"]
    return data


def save_index(index: Index, path: Optional[Path] = None) -> Path:
    p = Path(path) if path else index_path()
    write_json(p, index, indent=None)
    return p


def build_id_map(index: Index) -> Tuple[Dict[str, str], Dict[str, Tuple[str, dict]]]:
    """Trả về `(folder_id_to_path, item_id_to_(parent_path, item))` để tra cứu nhanh O(1)."""
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


def iter_items(index: Index, branch: Optional[str] = None):
    """Duyệt (đường_dẫn_cha, item) cho mọi mục trong chỉ mục, lọc theo tiền tố nhánh nếu có."""
    prefix = branch.rstrip("/") + "/" if branch else ""
    for path, data in index.items():
        if branch and not (path == branch or path.startswith(prefix)):
            continue
        for it in data.get("items", []):
            yield path, it


def normalize_branch(branch: Optional[str]) -> Optional[str]:
    """Cho phép nhập '[01] HỌC THUẬT' hoặc '[A] STORAGE/[01] HỌC THUẬT'."""
    if not branch:
        return None
    b = nfc(branch.strip().strip("/"))
    if not b.startswith(ROOT_NAME):
        b = f"{ROOT_NAME}/{b}"
    return b


def is_in_tong_quan(path: str) -> bool:
    return f"/{TONG_QUAN_FOLDER}" in path


def next_available_stt(existing_items: Iterable[Any], min_stt: int = 1) -> str:
    """Tính số thứ tự `[STT]` 2 chữ số tiếp theo chưa được sử dụng bởi các thư mục con hiện có."""
    used = set()
    for it in existing_items:
        if isinstance(it, dict):
            if it.get("mimeType") != FOLDER_MIME:
                continue
            raw_name = it.get("name", "").strip()
        else:
            raw_name = str(it).strip()
        m = re.match(r"^\[(\d{2,3})\]", raw_name)
        if m:
            n = int(m.group(1))
            if 0 < n < 90:
                used.add(n)
    cur = max(1, min_stt)
    while cur in used:
        cur += 1
    return f"[{cur:02d}]"


# ---------------------------------------------------------------------------
# 5. BỘ LUẬT QUY ƯỚC ĐẶT TÊN CHUẨN V6
# ---------------------------------------------------------------------------

RE_FOLDER_V6 = re.compile(r"^\[(\d{2,3})\] (\S.*\S|\S)$")
RE_STT_PREFIX = re.compile(r"^\s*\[\d{1,3}\]\s*")
RE_NUM_PREFIX = re.compile(r"^\d{1,3}[_\-. ]")
RE_DATE_PREFIX = re.compile(r"^(\d{2,4}_)?\d{6}_")
RE_EXT = re.compile(r"\.([A-Za-z0-9]{1,6})$")
KNOWN_EXTS = {
    "pdf", "epub", "mobi", "azw3", "djvu", "doc", "docx", "xls", "xlsx", "csv", "tsv", "ppt", "pptx",
    "txt", "md", "rtf", "odt", "ods", "odp", "html", "htm", "json", "xml", "yaml", "yml", "py", "ipynb",
    "js", "ts", "css", "sh", "bat", "zip", "rar", "7z", "tar", "gz", "jpg", "jpeg", "png", "gif", "webp",
    "bmp", "tif", "tiff", "heic", "svg", "mp3", "m4a", "wav", "flac", "ogg", "aac", "wma", "mp4", "mkv",
    "avi", "mov", "wmv", "webm", "flv", "m4v", "srt", "vtt", "ass", "apk", "exe", "msi", "iso", "psd",
    "ai", "indd", "tex", "bib", "enl", "ris", "canvas", "base", "pages", "numbers", "key", "drawio",
    "prc", "opf", "db", "ini",
}
TITLE_EXCEPTIONS = set(CONFIG["title_exceptions"])
LOWERCASE_PREFIX_WORDS = set(CONFIG["lowercase_prefix_words"])
ACRONYMS_UPPER: Dict[str, str] = dict(CONFIG["acronyms_upper"])
TECH_EXCEPTION_PATH_MARKERS = tuple(CONFIG["tech_exception_path_markers"])
TECH_FILE_RE = re.compile(r"^(?:readme|[a-z0-9_\-.]+\.(?:py|json|js|ts|sh|yaml|yml|toml|cfg|ini|txt|md|zip|opf|db))$")

SEVERITY_ORDER = {"LỖI": 0, "CẢNH BÁO": 1, "GỢI Ý": 2}
_VOWELS = set("aeiouyàáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵ"
              "áéíóúñüäöüß")


def split_ext(name: str, mime: str = "") -> Tuple[str, str]:
    """Tách (phần tên, đuôi không dấu chấm). Tệp Google gốc/shortcut được coi là không có đuôi."""
    if mime in GOOGLE_NATIVE_MIMES:
        return name, ""
    m = RE_EXT.search(name)
    if m and (m.group(1).lower() in KNOWN_EXTS) and m.start() > 0:
        return name[: m.start()], m.group(1)
    return name, ""


def is_tech_exception(parent_path: str, name: str) -> bool:
    if name.lower() in {"metadata.opf", "desktop.ini", "thumbs.db"}:
        return True
    if parent_path.endswith("[02] NHẬT KÍ") and name == "sheets_index.json":
        return True
    if any(mark in parent_path for mark in TECH_EXCEPTION_PATH_MARKERS) and TECH_FILE_RE.match(name):
        return True
    return parent_path.endswith(".obsidian") or "/.obsidian" in parent_path


_ROMAN_PREDECESSORS = {
    "chuong", "phan", "tap", "quyen", "ki", "ky", "cap", "muc", "hang",
    "lan", "buoi", "so", "giai", "doan", "loai", "vong", "the", "ki",
}


def _has_tone_or_vowel_diacritic(word: str) -> bool:
    no_d = word.replace("đ", "d").replace("Đ", "D")
    return no_d != strip_accents(no_d)


def _title_case_part(core: str, ac_map: Dict[str, str], prev_norm: str = "") -> str:
    if not core:
        return core
    low_exact = core.lower()
    low_ascii = strip_accents(core).lower()
    if low_exact in ac_map:
        return ac_map[low_exact]
    if low_ascii in ac_map and not _has_tone_or_vowel_diacritic(core):
        return ac_map[low_ascii]
    # Bảo vệ `Tử Vi` (prev_norm == "tu") không bao giờ bị biến thành số La Mã `VI`
    if low_exact == "vi" and prev_norm in _ROMAN_PREDECESSORS and prev_norm != "tu":
        return "VI"
    if any(ch.isdigit() for ch in core) or not (set(low_ascii) & _VOWELS) or "&" in core:
        return core
    return core[:1].upper() + core[1:].lower()


def title_case_vn(text: str, acronyms: Optional[Dict[str, str]] = None) -> str:
    """Chuyển tên thư mục/tiêu đề sang Title Case tiếng Việt, giữ nguyên viết tắt và từ ghép gạch nối."""
    ac_map = acronyms or ACRONYMS_UPPER
    out = []
    prev_norm = ""
    for raw in re.sub(r"\s{2,}", " ", text.strip()).split(" "):
        if not raw:
            continue
        if raw in ("-", "&", "/", "–"):
            out.append(raw)
            continue
        lead_len = len(raw) - len(raw.lstrip("([{\"'“‘«*"))
        trail_len = len(raw) - len(raw.rstrip(")]}.:,\"'”’»*"))
        core = raw[lead_len : len(raw) - trail_len if trail_len else len(raw)]
        lead = raw[:lead_len]
        trail = raw[len(raw) - trail_len :] if trail_len else ""
        if not core:
            out.append(raw)
        elif "-" in core and not core.startswith("-"):
            sub = "-".join(_title_case_part(p, ac_map, prev_norm) for p in core.split("-"))
            out.append(lead + sub + trail)
            prev_norm = strip_accents(core.split("-")[-1]).lower()
        else:
            out.append(lead + _title_case_part(core, ac_map, prev_norm) + trail)
            prev_norm = strip_accents(core).lower()
    return " ".join(out)


def normalize_sheet_title(folder_path: str) -> str:
    """Sinh tên chuẩn `Danh Mục Hệ Thống - <Tên Thư Mục>` không dính `_` hay đuôi `.PDF`."""
    if folder_path == ROOT_NAME:
        return "Danh Mục Hệ Thống - Storage"
    last = folder_path.split("/")[-1]
    body = re.sub(r"^\[\d{2,3}\]\s*", "", last)
    body = re.sub(r"^\[([^\]]+)\]\s*(.+)$", lambda m: f"{m.group(1).strip()} - {m.group(2).strip()}", body)
    body = re.sub(r"^\[([^\]]+)\]$", r"\1", body)
    body = re.sub(r"\.(pdf|docx?|xlsx?|pptx?)$", "", body, flags=re.I)
    body = re.sub(r"\s*_+\s*", " ", body).strip()
    return f"Danh Mục Hệ Thống - {title_case_vn(body)}"


def _is_cased_alpha(ch: str) -> bool:
    return ch.isalpha() and ch.lower() != ch.upper()


def _word_is_title(word: str) -> bool:
    core = word.strip("()[]{}\"'“”‘’,.;:!?«»+-")
    if not core:
        return True
    low = core.lower()
    if low in LOWERCASE_PREFIX_WORDS or low in TITLE_EXCEPTIONS or strip_accents(low) in TITLE_EXCEPTIONS:
        return True
    # Nhãn lựa chọn đơn kiểu `(a+)`, `(b)` hoặc từ mở đầu e-/i- như `e-Business`
    if re.match(r"^\([a-z][+-]?\)$", word.strip()):
        return True
    if re.match(r"^(?:e-[A-Z]|i[A-Z])", core):
        return True
    first = core[0]
    if not _is_cased_alpha(first):
        # Bỏ qua số, ký hiệu và chữ viết không có khái niệm hoa/thường (tiếng Thái, Hán, Ả Rập…)
        return True
    return first.isupper()


def check_folder_name(name: str, parent_path: str = "") -> List[Tuple[str, str, str]]:
    """Trả về danh sách (mức độ, mã lỗi, mô tả) cho tên thư mục."""
    issues: List[Tuple[str, str, str]] = []
    if parent_path.endswith(".obsidian") or "/.obsidian" in parent_path or name.startswith("."):
        return issues
    if "[00] TỔNG QUAN/[03] QUẢN LÝ" in parent_path and name in {"tests", "__pycache__", "scripts"}:
        return issues
    if name != name.strip():
        issues.append(("LỖI", "KHOANG_TRANG_THUA", "Có khoảng trắng ở đầu/cuối tên"))
    if "  " in name:
        issues.append(("LỖI", "KHOANG_TRANG_DOI", "Có hai khoảng trắng liên tiếp"))
    if name != nfc(name):
        issues.append(("CẢNH BÁO", "UNICODE_NFD", "Tên dùng Unicode tổ hợp (NFD) — nên chuẩn hóa NFC"))
    m = RE_FOLDER_V6.match(name.strip())
    if not m:
        issues.append(("LỖI", "THIEU_STT", "Thư mục phải có dạng `[STT] TÊN IN HOA CÓ DẤU`"))
        body = RE_STT_PREFIX.sub("", name)
    else:
        body = m.group(2)
    if "_" in body:
        issues.append(("LỖI", "GACH_DUOI", "Không dùng dấu gạch dưới `_` trong tên thư mục"))
    letters = [c for c in body if _is_cased_alpha(c)]
    if letters and any(c.islower() for c in letters):
        issues.append(("LỖI", "CHUA_IN_HOA", "Tên thư mục phải viết IN HOA toàn bộ"))
    return issues


def check_file_name(name: str, mime: str = "", parent_path: str = "") -> List[Tuple[str, str, str]]:
    """Trả về danh sách (mức độ, mã lỗi, mô tả) cho tên tệp."""
    issues: List[Tuple[str, str, str]] = []
    if is_tech_exception(parent_path, name):
        return issues
    if name == "TongQuan.md":
        issues.append(("CẢNH BÁO", "TEP_HE_THONG_CU",
                       "Tệp `TongQuan.md` cũ — cần chuẩn hóa thành `Tổng Quan Hệ Thống - <Tên Thư Mục>.md`"))
        return issues
    if name != name.strip():
        issues.append(("LỖI", "KHOANG_TRANG_THUA", "Có khoảng trắng ở đầu/cuối tên"))
    if "  " in name:
        issues.append(("LỖI", "KHOANG_TRANG_DOI", "Có hai khoảng trắng liên tiếp"))
    if name != nfc(name):
        issues.append(("CẢNH BÁO", "UNICODE_NFD", "Tên dùng Unicode tổ hợp (NFD) — nên chuẩn hóa NFC"))
    base, ext = split_ext(name.strip(), mime)
    if ext and ext != ext.lower():
        issues.append(("LỖI", "DUOI_VIET_HOA", f"Đuôi tệp phải viết thường (`.{ext}` → `.{ext.lower()}`)"))
    if mime in GOOGLE_NATIVE_MIMES:
        m = RE_EXT.search(name)
        if m and m.group(1).lower() in {"docx", "xlsx", "pptx", "pdf", "doc", "xls", "ppt", "gdoc", "gsheet"}:
            issues.append(("CẢNH BÁO", "DUOI_THUA_GOOGLE", "Tệp Google gốc/Shortcut không nên có phần mở rộng"))
    if RE_STT_PREFIX.match(base):
        issues.append(("LỖI", "TIEN_TO_STT", "Tên tệp không được bắt đầu bằng `[STT]`"))
    elif RE_DATE_PREFIX.match(base):
        issues.append(("LỖI", "TIEN_TO_NGAY", "Tên tệp không được bắt đầu bằng chuỗi ngày `YYMMDD_`"))
    elif RE_NUM_PREFIX.match(base) and "_" in base[:5]:
        issues.append(("CẢNH BÁO", "TIEN_TO_SO", "Tên tệp bắt đầu bằng số thứ tự kiểu cũ"))
    if "_" in base:
        issues.append(("CẢNH BÁO", "GACH_DUOI", "Nên thay dấu gạch dưới `_` bằng khoảng trắng"))
    if " - " not in base:
        issues.append(("GỢI Ý", "THIEU_THONG_TIN_BO_SUNG", "Chưa có phần `- Thông Tin Bổ Sung`"))
    main = base.split(" - ", 1)[0]
    words = [w for w in re.split(r"\s+", main) if w]
    if words and not all(_word_is_title(w) for w in words):
        issues.append(("CẢNH BÁO", "CHUA_TITLE_CASE", "Tên chính nên viết hoa chữ cái đầu mỗi từ"))
    if re.search(r"\s-\S|\S-\s", base) and " - " not in base:
        issues.append(("CẢNH BÁO", "PHAN_CACH_SAI", "Dấu phân cách phải là ` - ` (có khoảng trắng hai bên)"))
    return issues


def safe_fix_name(name: str, is_folder: bool, mime: str = "") -> str:
    """Sửa các lỗi *cơ học* an toàn (khoảng trắng, NFC, đuôi viết thường, IN HOA thư mục, `_` → khoảng trắng)."""
    new = nfc(name).strip()
    if new.startswith("- "):
        return name
    new = re.sub(r"\s{2,}", " ", new)
    if is_folder:
        m = re.match(r"^\[(\d{1,3})\]\s*(.*)$", new)
        if m:
            stt, body = m.group(1), m.group(2)
            stt = stt.zfill(2)
            body = re.sub(r"\s*_+\s*", " ", body).strip().upper()
            new = f"[{stt}] {body}" if body else new
        return new
    if mime in GOOGLE_NATIVE_MIMES:
        m_ext = RE_EXT.search(new)
        if m_ext and m_ext.group(1).lower() in {"pdf", "docx", "xlsx", "pptx", "doc", "xls", "ppt"}:
            new = new[: m_ext.start()].strip()
    base, ext = split_ext(new, mime)
    base = re.sub(r"\s*_+\s*", " ", base).strip() if "_" in base and not RE_DATE_PREFIX.match(base) else base
    base = re.sub(r"\s+-\s*|\s*-\s+", " - ", base) if re.search(r"\s-\S|\S-\s", base) else base
    base = re.sub(r"\s{2,}", " ", base).strip()
    return f"{base}.{ext.lower()}" if ext else base


# ---------------------------------------------------------------------------
# 6. XUẤT BẢN BÁO CÁO LÊN DRIVE
# ---------------------------------------------------------------------------

def publish_file(drive: Drive, local: Path, parent_id: str, name: Optional[str] = None) -> str:
    """Tải tệp lên thư mục đích; nếu đã có tệp trùng tên thì cập nhật tại chỗ (giữ ID/URL)."""
    local = Path(local)
    target_name = name or local.name
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


def nhat_ki_id() -> str:
    return os.environ.get("STORAGE_NHAT_KI_ID", KNOWN_IDS["[00] TỔNG QUAN/[02] NHẬT KÍ"])


# ---------------------------------------------------------------------------
# 7. MÔ TẢ
# ---------------------------------------------------------------------------

def describe() -> str:
    return (f"storage_core {__version__} | gốc={ROOT_NAME} ({ROOT_ID}) | kiểm tra={QUARANTINE_FOLDER} ({quarantine_root_id()}) | "
            f"dữ liệu={data_dir()} | gdrive={find_gdrive_bin()}")


if __name__ == "__main__":
    print(describe())
