"""Bộ luật quy ước đặt tên Chuẩn V6 cho thư mục, tệp nội dung và mã nguồn."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from karius_academic_system.core import config as _cfg
from karius_academic_system.core.config import (
    CONFIG,
    FOLDER_MIME,
    GOOGLE_NATIVE_MIMES,
    SHEET_MIME,
    SHORTCUT_MIME,
)
from karius_academic_system.core.utils import nfc, strip_accents

RE_FOLDER_V6 = re.compile(r"^\[(\d{2,3})\] (\S.*\S|\S)$")
RE_STT_PREFIX = re.compile(r"^\s*\[\d{1,3}\]\s*")
RE_NUM_PREFIX = re.compile(r"^\d{1,3}[_\-. ]")
RE_DATE_PREFIX = re.compile(r"^(\d{2,4}_)?\d{6}_")
RE_EXT = re.compile(r"\.([A-Za-z0-9]{1,6})$")

KNOWN_EXTS = {
    "pdf", "epub", "mobi", "azw3", "djvu", "doc", "docx", "xls", "xlsx", "csv", "tsv", "ppt", "pptx",
    "txt", "md", "rtf", "odt", "ods", "odp", "html", "htm", "mht", "mhtml", "json", "xml", "yaml", "yml", "py", "ipynb",
    "js", "ts", "css", "sh", "bat", "zip", "rar", "7z", "tar", "gz", "jpg", "jpeg", "png", "gif", "webp",
    "bmp", "tif", "tiff", "heic", "svg", "mp3", "m4a", "wav", "flac", "ogg", "aac", "wma", "mp4", "mkv",
    "avi", "mov", "wmv", "webm", "flv", "m4v", "srt", "vtt", "ass", "apk", "exe", "msi", "iso", "psd",
    "ai", "indd", "tex", "bib", "enl", "ris", "canvas", "base", "pages", "numbers", "key", "drawio",
    "prc", "opf", "db", "ini", "whl",
}

TITLE_EXCEPTIONS = set(CONFIG["title_exceptions"])
LOWERCASE_PREFIX_WORDS = set(CONFIG["lowercase_prefix_words"])
ACRONYMS_UPPER: Dict[str, str] = dict(CONFIG["acronyms_upper"])
TECH_EXCEPTION_PATH_MARKERS = tuple(CONFIG["tech_exception_path_markers"])
TECH_FILE_RE = re.compile(
    r"^(?:readme|[a-z0-9_\-.]+\.(?:py|json|js|ts|sh|yaml|yml|toml|cfg|ini|txt|md|zip|whl|tar\.gz|opf|db))$"
)

SEVERITY_ORDER = {"LỖI": 0, "CẢNH BÁO": 1, "GỢI Ý": 2}
_VOWELS = set(
    "aeiouyàáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵ"
    "áéíóúñüäöüß"
)

_GOOGLE_MIME_LABELS: Dict[str, str] = {
    FOLDER_MIME: "Thư mục",
    SHORTCUT_MIME: "Shortcut",
    "application/vnd.google-apps.document": "Google Docs",
    SHEET_MIME: "Google Sheets",
    "application/vnd.google-apps.presentation": "Google Slides",
    "application/vnd.google-apps.form": "Google Forms",
    "application/vnd.google-apps.drawing": "Google Drawings",
    "application/vnd.google-apps.colaboratory": "Google Colab",
    "application/vnd.google-apps.site": "Google Sites",
    "application/vnd.google-apps.map": "Google My Maps",
    "application/vnd.google-apps.jam": "Google Jamboard",
}

_ROMAN_PREDECESSORS = {
    "chuong", "phan", "tap", "quyen", "ki", "ky", "cap", "muc", "hang",
    "lan", "buoi", "so", "giai", "doan", "loai", "vong", "the",
}


def normalize_branch(branch: Optional[str]) -> Optional[str]:
    if not branch:
        return None
    b = nfc(branch.strip().strip("/"))
    rname = _cfg.ROOT_NAME
    if rname and not b.startswith(rname):
        b = f"{rname}/{b}"
    return b


def is_in_tong_quan(path: str) -> bool:
    return f"/{_cfg.TONG_QUAN_FOLDER}" in path


def catalog_folder_for_path(target_path: str) -> str:
    clean = nfc(target_path or "").strip().rstrip("/")
    rname = _cfg.ROOT_NAME
    tq = _cfg.TONG_QUAN_FOLDER
    ds_path = _cfg.DANH_SACH_PATH
    if not clean or clean == rname:
        return f"{rname}/{tq}"
    prefix = f"{rname}/"
    if clean.startswith(prefix):
        return f"{ds_path}/{clean[len(prefix):]}"
    return f"{clean}/{tq}"


def next_available_stt(existing_items: Iterable[Any], min_stt: int = 1) -> str:
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


def split_ext(name: str, mime: str = "") -> Tuple[str, str]:
    if mime in GOOGLE_NATIVE_MIMES:
        return name, ""
    m = RE_EXT.search(name)
    if m and (m.group(1).lower() in KNOWN_EXTS) and m.start() > 0:
        return name[: m.start()], m.group(1)
    return name, ""


def format_label(mime: str, name: str = "") -> str:
    m = (mime or "").strip()
    if m in _GOOGLE_MIME_LABELS:
        return _GOOGLE_MIME_LABELS[m]
    if m.startswith("application/vnd.google-apps."):
        return "Google Workspace"
    _, ext = split_ext(name or "", m)
    if ext:
        return ext.upper()
    if m == "application/pdf":
        return "PDF"
    if m == "text/markdown":
        return "MD"
    if m == "text/plain":
        return "TXT"
    if "/" in m:
        sub = m.split("/", 1)[1].split(";", 1)[0].strip()
        if sub.isalnum() and len(sub) <= 8:
            return sub.upper()
    return "Tệp khác"


def extract_extra_info_v6(
    name: str,
    mime: str = "",
    parent_path: str = "",
    shortcut_info: Optional[dict] = None,
) -> str:
    clean_name = nfc(name or "").strip()
    if mime == FOLDER_MIME:
        return "Thư mục tổng quan & danh mục hệ thống" if clean_name == _cfg.TONG_QUAN_FOLDER else ""
    if mime == SHORTCUT_MIME:
        if not shortcut_info:
            return ""
        tname = shortcut_info.get("targetName") or ""
        tmime = shortcut_info.get("targetMime") or shortcut_info.get("targetMimeType") or ""
        tstatus = shortcut_info.get("targetStatus") or ""
        tlbl = format_label(tmime, tname) if (tmime or tname) else ""
        if tname:
            base_str = f"→ [{tlbl}] {tname}" if tlbl else f"→ {tname}"
        else:
            base_str = f"→ [{tlbl}]" if tlbl else "→ Shortcut"
        if tstatus == "broken":
            return f"{base_str} (lỗi 404)"
        if tstatus == "trashed":
            return f"{base_str} (trong thùng rác)"
        return base_str
    base, _ = split_ext(clean_name, mime)
    if " - " in base:
        return base.split(" - ", 1)[1].strip()
    return ""


def is_tech_exception(parent_path: str, name: str) -> bool:
    if name.lower() in {"metadata.opf", "desktop.ini", "thumbs.db"}:
        return True
    if parent_path.endswith("[02] NHẬT KÍ") and name == "sheets_index.json":
        return True
    if any(mark in parent_path for mark in TECH_EXCEPTION_PATH_MARKERS) and TECH_FILE_RE.match(name):
        return True
    return parent_path.endswith(".obsidian") or "/.obsidian" in parent_path


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
        if raw in ("-", "&", "/", "–", "+", ":"):
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


def _is_cased_alpha(ch: str) -> bool:
    return ch.isalpha() and ch.lower() != ch.upper()


def _word_is_title(word: str) -> bool:
    core = word.strip("()[]{}\"'“”‘’,.;:!?«»+-")
    if not core:
        return True
    low = core.lower()
    if low in LOWERCASE_PREFIX_WORDS or low in TITLE_EXCEPTIONS or strip_accents(low) in TITLE_EXCEPTIONS:
        return True
    if re.match(r"^\([a-z][+-]?\)$", word.strip()):
        return True
    if re.match(r"^(?:e-[A-Z]|i[A-Z])", core):
        return True
    first = core[0]
    if not _is_cased_alpha(first):
        return True
    return first.isupper()


def check_folder_name(name: str, parent_path: str = "") -> List[Tuple[str, str, str]]:
    issues: List[Tuple[str, str, str]] = []
    if parent_path.endswith(".obsidian") or "/.obsidian" in parent_path or name.startswith("."):
        return issues
    if "[00] TỔNG QUAN/[03] QUẢN LÝ" in parent_path and name in {"tests", "__pycache__", "scripts", "releases", "docs"}:
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
    issues: List[Tuple[str, str, str]] = []
    if is_tech_exception(parent_path, name):
        return issues
    if name == "TongQuan.md":
        issues.append(("CẢNH BÁO", "TEP_HE_THONG_CU", "Tệp `TongQuan.md` cũ — cần chuẩn hóa thành `Tổng Quan Hệ Thống - <Tên Thư Mục>.md`"))
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
