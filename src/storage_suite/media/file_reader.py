#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ĐỌC TỆP ĐA ĐỊNH DẠNG & TRÍCH XUẤT NỘI DUNG / SIÊU DỮ LIỆU — [A] STORAGE (v3.1)
================================================================================
Chương trình `[13] ĐỌC TỆP/file_reader.py` cung cấp tầng đọc tệp thống nhất cho toàn kho:

1. `doc`        : Đọc tức thì 1 tệp theo ID Google Drive, URL Drive hoặc đường dẫn tệp cục bộ;
                  hiển thị siêu dữ liệu, thống kê (số trang/từ/dòng/thời lượng), dàn ý và đoạn trích.
2. `trich-xuat` : Quét và trích xuất theo lô có kiểm soát (`--nhanh`, `--dinh-dang`, `--max-mb`,
                  `--gioi-han`, `--luong`, `--ocr`, `--kiem-tra-sau`), lưu vào bộ đệm bền vững
                  `<STORAGE_DATA_DIR>/content_cache/` theo khóa `(id, modifiedTime)` và tự xóa tệp tạm.
3. `thong-ke`   : Thống kê độ phủ bộ đệm trích xuất theo định dạng, trạng thái, cờ cảnh báo và nhánh.

Hỗ trợ định dạng:
- Tài liệu & sách : PDF (`pdfinfo` + `pdftotext` + dự phòng thuần Python + OCR `tesseract`),
                    DOCX, PPTX, XLSX (`zipfile` + XML), EPUB, OPF, MOBI/AZW3/PRC (PalmDB + EXTH + PalmDOC),
                    DOC/XLS/PPT (OLE2), MD, TXT, CSV/TSV, HTML, JSON, PY/TS/JS/SH.
- Google gốc      : Google Docs (`md`), Google Sheets (`csv`), Google Slides (`txt`) qua `gdrive export`.
- Đa phương tiện  : Ảnh JPG/PNG/WEBP/GIF (`Pillow` EXIF), Âm thanh/Video MP3/MP4/MOV/TS/WAV (`ffprobe`).
- Tệp nén         : ZIP (`zipfile`), RAR/7Z (`7z l -slt`), kèm kiểm tra mật khẩu và toàn vẹn CRC.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import io
import json
import re
import shutil
import struct
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
import zipfile
import zlib
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


from storage_suite import core as sc

MAX_CACHED_TEXT_CHARS = 300_000
MAX_PREVIEW_CHARS = 1_500

GOOGLE_DOC_MIME = "application/vnd.google-apps.document"
GOOGLE_SHEET_MIME = "application/vnd.google-apps.spreadsheet"
GOOGLE_SLIDE_MIME = "application/vnd.google-apps.presentation"

TEXT_EXTENSIONS = {
    "md", "txt", "csv", "tsv", "html", "htm", "json", "py", "js", "yaml", "yml",
    "ini", "cfg", "toml", "sh", "sql", "xml", "css", "tex", "log", "rst",
}
IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif", "bmp", "tif", "tiff"}
AUDIO_EXTENSIONS = {"mp3", "wav", "flac", "m4a", "aac", "ogg", "wma"}
VIDEO_EXTENSIONS = {"mp4", "mov", "mkv", "avi", "webm", "flv", "wmv"}
ARCHIVE_EXTENSIONS = {"zip", "rar", "7z", "tar", "gz", "bz2"}
EBOOK_MOBI_EXTENSIONS = {"mobi", "azw", "azw3", "prc"}
OLE_EXTENSIONS = {"doc", "xls", "ppt"}

# Nhóm tương thích giữa đuôi tệp và định dạng magic-byte
COMPATIBLE_MAGIC_FAMILIES: Dict[str, Set[str]] = {
    "pdf": {"pdf"},
    "docx": {"docx", "zip"},
    "pptx": {"pptx", "zip"},
    "xlsx": {"xlsx", "zip"},
    "epub": {"epub", "zip"},
    "zip": {"zip", "docx", "pptx", "xlsx", "epub"},
    "rar": {"rar"},
    "7z": {"7z"},
    "doc": {"ole", "docx", "rtf", "text"},
    "xls": {"ole", "xlsx", "text"},
    "ppt": {"ole", "pptx"},
    "mobi": {"mobi"},
    "azw": {"mobi"},
    "azw3": {"mobi"},
    "prc": {"mobi"},
    "jpg": {"jpg"},
    "jpeg": {"jpg"},
    "png": {"png"},
    "gif": {"gif"},
    "webp": {"webp"},
    "mp3": {"mp3", "audio"},
    "wav": {"wav", "audio"},
    "mp4": {"mp4", "video"},
    "mov": {"mp4", "video"},
    "m4a": {"mp4", "audio"},
    "ts": {"ts", "video", "text"},
}


# ---------------------------------------------------------------------------
# 1. TIỆN ÍCH VĂN BẢN, BẢNG MÃ & MAGIC BYTES
# ---------------------------------------------------------------------------

class _HTMLTextExtractor(HTMLParser):
    """Bộ tách văn bản và tiêu đề nhẹ từ HTML/XHTML dùng thư viện chuẩn."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._in_title = False
        self._curr_heading: Optional[str] = None
        self._heading_buf: List[str] = []
        self.title: str = ""
        self.meta: Dict[str, str] = {}
        self.headings: List[str] = []
        self.chunks: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        t = tag.lower()
        if t in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
            return
        if t == "title":
            self._in_title = True
        elif t in {"h1", "h2", "h3"}:
            self._curr_heading = t
            self._heading_buf = []
        elif t in {"p", "div", "br", "li", "tr", "section", "article", "blockquote"}:
            self.chunks.append("\n")
        elif t == "meta":
            ad = {k.lower(): (v or "") for k, v in attrs if k}
            name = (ad.get("name") or ad.get("property") or "").lower()
            content = ad.get("content", "").strip()
            if name and content:
                self.meta[name] = content

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in {"script", "style", "noscript", "svg"} and self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if t == "title":
            self._in_title = False
        elif t in {"h1", "h2", "h3"} and self._curr_heading == t:
            h = _clean_whitespace(" ".join(self._heading_buf))
            if h and h not in self.headings and len(self.headings) < 40:
                self.headings.append(h)
            self._curr_heading = None
            self._heading_buf = []
            self.chunks.append("\n")
        elif t in {"p", "div", "li", "tr", "td", "th"}:
            self.chunks.append(" ")

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        if self._in_title and not self.title:
            self.title = _clean_whitespace(data)
        if self._curr_heading is not None:
            self._heading_buf.append(data)
        self.chunks.append(data)

    def get_text(self) -> str:
        raw = "".join(self.chunks)
        lines = [_clean_whitespace(ln) for ln in raw.splitlines()]
        return "\n".join(ln for ln in lines if ln)


def _clean_whitespace(text: str) -> str:
    return re.sub(r"[ \t\r\f\v]+", " ", (text or "")).strip()


def _normalize_extracted_text(text: str) -> str:
    if not text:
        return ""
    text = sc.nfc(text.replace("\x00", " ").replace("\r\n", "\n").replace("\r", "\n"))
    lines = [re.sub(r"[ \t\f\v]+", " ", ln).strip() for ln in text.splitlines()]
    compact: List[str] = []
    blank_run = 0
    for ln in lines:
        if not ln:
            blank_run += 1
            if blank_run <= 1 and compact:
                compact.append("")
        else:
            blank_run = 0
            compact.append(ln)
    return "\n".join(compact).strip()


def compute_text_stats(text: str, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Tính số dòng, số từ, số ký tự từ văn bản trích xuất."""
    norm = text or ""
    words = re.findall(r"\w+", norm, flags=re.UNICODE)
    lines = [ln for ln in norm.splitlines() if ln.strip()]
    out: Dict[str, Any] = {
        "char_count": len(norm),
        "word_count": len(words),
        "line_count": len(lines),
    }
    if extra:
        for k, v in extra.items():
            if v is not None:
                out[k] = v
    return out


def decode_bytes_smart(raw: bytes) -> Tuple[str, str]:
    """Giải mã chuỗi byte sang Unicode với thứ tự ưu tiên UTF-8 / UTF-16 / CP1258 / CP1252."""
    if not raw:
        return "", "utf-8"
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig", errors="replace"), "utf-8-sig"
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16", errors="replace"), "utf-16"
    for enc in ("utf-8", "cp1258", "cp1252"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "latin-1"


def detect_magic_format(path: Path) -> str:
    """Nhận diện định dạng thực tế dựa trên magic bytes ở đầu tệp."""
    try:
        with open(path, "rb") as f:
            head = f.read(4096)
    except OSError:
        return "unknown"
    if not head:
        return "empty"
    if head.startswith(b"%PDF-") or b"%PDF-1." in head[:1024]:
        return "pdf"
    if head.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")):
        try:
            with zipfile.ZipFile(path, "r") as zf:
                names = set(zf.namelist())
                if "word/document.xml" in names:
                    return "docx"
                if "ppt/presentation.xml" in names:
                    return "pptx"
                if "xl/workbook.xml" in names:
                    return "xlsx"
                if "META-INF/container.xml" in names:
                    return "epub"
                if "mimetype" in names:
                    mt = zf.read("mimetype").decode("ascii", errors="ignore").strip()
                    if "epub" in mt:
                        return "epub"
                if any(n.lower().endswith(".opf") for n in names):
                    return "epub"
        except Exception:
            pass
        return "zip"
    if head.startswith(b"Rar!\x1a\x07"):
        return "rar"
    if head.startswith(b"7z\xbc\xaf\x27\x1c"):
        return "7z"
    if head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return "ole"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return "webp"
    if head.startswith(b"RIFF") and head[8:12] == b"WAVE":
        return "wav"
    if head.startswith(b"ID3") or (len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0):
        return "mp3"
    if len(head) >= 12 and head[4:8] == b"ftyp":
        return "mp4"
    if len(head) >= 68 and head[60:68] in (b"BOOKMOBI", b"TEXtREAd"):
        return "mobi"
    if head.startswith(b"{\\rtf"):
        return "rtf"
    # Kiểm tra MPEG-TS (byte đồng bộ 0x47 mỗi 188 byte)
    if len(head) >= 564 and head[0] == 0x47 and head[188] == 0x47 and head[376] == 0x47:
        return "ts"
    # Kiểm tra có phải văn bản thuần không
    non_text = sum(1 for b in head[:512] if b == 0)
    if non_text == 0:
        return "text"
    return "binary"


def check_format_mismatch(ext: str, magic_fmt: str) -> bool:
    """Phát hiện tệp có đuôi không khớp với định dạng magic-byte thực tế."""
    ext = (ext or "").lower().lstrip(".")
    if not ext or magic_fmt in {"unknown", "empty", "binary"}:
        return False
    allowed = COMPATIBLE_MAGIC_FAMILIES.get(ext)
    if allowed is not None:
        return magic_fmt not in allowed
    if ext in TEXT_EXTENSIONS or ext == "opf":
        return magic_fmt not in {"text"}
    return False


# ---------------------------------------------------------------------------
# 2. BỘ ĐỌC THEO ĐỊNH DẠNG
# ---------------------------------------------------------------------------

def _parse_pdf_fallback(path: Path) -> Tuple[Dict[str, Any], int, bool, str]:
    """
    Bộ đọc PDF dự phòng thuần Python: trích xuất số trang, cờ `/Encrypt`,
    siêu dữ liệu `/Title`, `/Author` và các luồng văn bản cơ bản khi thiếu `pdfinfo`/`pdftotext`.
    """
    raw = path.read_bytes()
    encrypted = bool(re.search(rb"/Encrypt\b", raw))
    pages = len(re.findall(rb"/Type\s*/Page\b", raw))
    if pages == 0:
        m_cnt = re.findall(rb"/Count\s+(\d+)", raw)
        if m_cnt:
            pages = max(int(x) for x in m_cnt)

    def _decode_pdf_str(b: bytes) -> str:
        if b.startswith(b"\xfe\xff"):
            return b[2:].decode("utf-16-be", errors="replace").strip()
        if b.startswith(b"\xff\xfe"):
            return b[2:].decode("utf-16-le", errors="replace").strip()
        return b.decode("utf-8", errors="replace").strip()

    meta: Dict[str, Any] = {}
    for key, label in ((b"Title", "title"), (b"Author", "author"), (b"Subject", "subject"), (b"Keywords", "keywords")):
        m = re.search(rb"/" + key + rb"\s*\(([^()\\]*(?:\\.[^()\\]*)*)\)", raw)
        if m:
            val = re.sub(rb"\\([()\\])", rb"\1", m.group(1))
            s = _decode_pdf_str(val)
            if s:
                meta[label] = s

    # Giải nén các stream FlateDecode nhỏ hoặc đọc trực tiếp toán tử Tj/TJ
    text_chunks: List[str] = []
    streams = re.findall(rb"stream\r?\n(.*?)\r?\nendstream", raw, flags=re.DOTALL)
    sources = list(streams[:80]) if streams else [raw]
    for st in sources:
        buf = st
        if b"BT" not in buf:
            try:
                buf = zlib.decompress(st)
            except Exception:
                pass
        if b"BT" in buf:
            for m in re.finditer(rb"\(([^()\\]*(?:\\.[^()\\]*)*)\)\s*Tj", buf):
                val = re.sub(rb"\\([()\\])", rb"\1", m.group(1))
                text_chunks.append(_decode_pdf_str(val))
            for m in re.finditer(rb"\[(.*?)\]\s*TJ", buf, flags=re.DOTALL):
                inner = m.group(1)
                parts = [re.sub(rb"\\([()\\])", rb"\1", p) for p in re.findall(rb"\(([^()\\]*(?:\\.[^()\\]*)*)\)", inner)]
                if parts:
                    text_chunks.append("".join(_decode_pdf_str(p) for p in parts))
    return meta, max(pages, 1 if text_chunks else 0), encrypted, "\n".join(text_chunks)


def read_pdf_file(
    path: Path,
    max_pages: int = 40,
    enable_ocr: bool = False,
    ocr_pages: int = 5,
) -> Dict[str, Any]:
    """Đọc tệp PDF bằng `pdfinfo` + `pdftotext`, tự động chuyển sang dự phòng hoặc OCR khi cần."""
    meta: Dict[str, Any] = {}
    flags: List[str] = []
    outline: List[str] = []
    pages = 0
    encrypted = False
    text = ""
    used_poppler = False

    if shutil.which("pdfinfo"):
        try:
            proc = subprocess.run(
                ["pdfinfo", str(path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if proc.returncode == 0:
                used_poppler = True
                for line in proc.stdout.splitlines():
                    if ":" not in line:
                        continue
                    k, v = line.split(":", 1)
                    k = k.strip().lower()
                    v = v.strip()
                    if not v:
                        continue
                    if k == "title":
                        meta["title"] = v
                    elif k == "author":
                        meta["author"] = v
                    elif k == "subject":
                        meta["subject"] = v
                    elif k == "keywords":
                        meta["keywords"] = v
                    elif k == "creator":
                        meta["creator"] = v
                    elif k == "producer":
                        meta["producer"] = v
                    elif k == "creationdate":
                        meta["created"] = v
                    elif k == "pages" and v.isdigit():
                        pages = int(v)
                    elif k == "encrypted" and v.lower().startswith("yes"):
                        encrypted = True
            else:
                err_low = (proc.stderr or "").lower()
                if "incorrect password" in err_low or "encrypted" in err_low:
                    encrypted = True
                    flags.append("co_mat_khau")
        except Exception:
            pass

    if shutil.which("pdftotext") and "co_mat_khau" not in flags:
        try:
            cmd = ["pdftotext", "-enc", "UTF-8", "-q"]
            if max_pages > 0:
                cmd += ["-l", str(max_pages)]
            cmd += [str(path), "-"]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if proc.returncode == 0:
                used_poppler = True
                text = proc.stdout or ""
            else:
                err_low = (proc.stderr or "").lower()
                if "password" in err_low or "encrypted" in err_low:
                    encrypted = True
                    if "co_mat_khau" not in flags:
                        flags.append("co_mat_khau")
        except Exception:
            pass

    # Luôn bổ sung từ bộ phân tích thuần Python nếu Poppler không lấy được trang/văn bản
    fb_meta, fb_pages, fb_enc, fb_text = _parse_pdf_fallback(path)
    for k, v in fb_meta.items():
        meta.setdefault(k, v)
    if pages == 0 and fb_pages > 0:
        pages = fb_pages
    if fb_enc:
        encrypted = True
    if not text.strip() and fb_text.strip():
        text = fb_text

    if encrypted and not text.strip() and "co_mat_khau" not in flags:
        flags.append("co_mat_khau")

    norm_text = _normalize_extracted_text(text)
    sampled_pages = min(pages, max_pages) if (pages > 0 and max_pages > 0) else max(pages, 1)
    chars_per_page = len(norm_text) / max(1, sampled_pages)

    if pages > 0 and chars_per_page < 45 and "co_mat_khau" not in flags:
        flags.append("can_ocr")
        if enable_ocr and shutil.which("pdftoppm") and shutil.which("tesseract"):
            ocr_text = _ocr_pdf_pages(path, max_ocr_pages=min(ocr_pages, max(1, pages)))
            if ocr_text.strip():
                norm_text = _normalize_extracted_text(ocr_text)
                flags.append("da_ocr")

    # Rút trích các dòng nghi là đề mục chương/mục trong PDF
    for ln in norm_text.splitlines()[:120]:
        if 4 <= len(ln) <= 100 and (
            re.match(r"^(CHƯƠNG|PHẦN|MỤC|BÀI|CHAPTER|PART|SECTION|[IVXLC]+\.)\b", ln, flags=re.I)
            or (ln.isupper() and len(ln.split()) >= 2)
        ):
            if ln not in outline and len(outline) < 25:
                outline.append(ln)

    status = "ok"
    if "co_mat_khau" in flags:
        status = "co_mat_khau"
    elif pages == 0 and not norm_text and not used_poppler:
        status = "tep_hong"
        flags.append("tep_hong")
    elif "can_ocr" in flags and "da_ocr" not in flags:
        status = "can_ocr"

    stats = compute_text_stats(norm_text, {"pages": pages, "encrypted": encrypted})
    return {
        "status": status,
        "metadata": meta,
        "stats": stats,
        "outline": outline,
        "text": norm_text,
        "flags": flags,
    }


def _ocr_pdf_pages(path: Path, max_ocr_pages: int = 5) -> str:
    """Chuyển các trang đầu của PDF scan sang PNG và nhận dạng bằng bộ OCR hợp nhất (`vie+eng`)."""
    text, _ = sc.ocr_pdf_pages(path, max_ocr_pages=max_ocr_pages)
    return text


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _parse_ooxml_core_and_app(zf: zipfile.ZipFile) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Đọc `docProps/core.xml` và `docProps/app.xml` chung cho DOCX, PPTX, XLSX."""
    meta: Dict[str, Any] = {}
    app_stats: Dict[str, Any] = {}
    if "docProps/core.xml" in zf.namelist():
        try:
            root = ET.fromstring(zf.read("docProps/core.xml"))
            for el in root.iter():
                ln = _xml_local_name(el.tag).lower()
                val = _clean_whitespace(el.text or "")
                if not val:
                    continue
                if ln == "title":
                    meta["title"] = val
                elif ln in {"creator", "author"}:
                    meta["author"] = val
                elif ln == "subject":
                    meta["subject"] = val
                elif ln == "description":
                    meta["description"] = val
                elif ln == "keywords":
                    meta["keywords"] = val
                elif ln == "created":
                    meta["created"] = val
                elif ln == "modified":
                    meta["modified"] = val
        except Exception:
            pass
    if "docProps/app.xml" in zf.namelist():
        try:
            root = ET.fromstring(zf.read("docProps/app.xml"))
            for el in root.iter():
                ln = _xml_local_name(el.tag).lower()
                val = (el.text or "").strip()
                if ln == "pages" and val.isdigit():
                    app_stats["pages"] = int(val)
                elif ln == "slides" and val.isdigit():
                    app_stats["slides"] = int(val)
        except Exception:
            pass
    return meta, app_stats


def read_docx_file(path: Path) -> Dict[str, Any]:
    """Đọc tệp Word `.docx` bằng `zipfile` + XML (`word/document.xml`, `docProps/core.xml`)."""
    try:
        with zipfile.ZipFile(path, "r") as zf:
            meta, app_stats = _parse_ooxml_core_and_app(zf)
            if "word/document.xml" not in zf.namelist():
                return {"status": "tep_hong", "metadata": meta, "stats": compute_text_stats(""), "outline": [], "text": "", "flags": ["tep_hong"]}
            root = ET.fromstring(zf.read("word/document.xml"))
    except Exception as e:
        return {"status": "tep_hong", "metadata": {}, "stats": compute_text_stats(""), "outline": [], "text": "", "flags": ["tep_hong"], "error": str(e)}

    paragraphs: List[str] = []
    outline: List[str] = []
    for p in root.iter():
        if _xml_local_name(p.tag) != "p":
            continue
        style_val = ""
        texts: List[str] = []
        for child in p.iter():
            cn = _xml_local_name(child.tag)
            if cn == "pStyle":
                for k, v in child.attrib.items():
                    if _xml_local_name(k) == "val":
                        style_val = v
            elif cn == "t" and child.text:
                texts.append(child.text)
        line = _clean_whitespace("".join(texts))
        if not line:
            continue
        paragraphs.append(line)
        if any(h in style_val.lower() for h in ("heading", "title", "tieude", "chuong")) and line not in outline and len(outline) < 40:
            outline.append(line)

    if not outline:
        for ln in paragraphs[:40]:
            if 3 <= len(ln) <= 90 and (ln.isupper() or re.match(r"^(Chương|Phần|Mục|Bài|I+\.|[0-9]+\.)\b", ln, re.I)):
                if ln not in outline and len(outline) < 20:
                    outline.append(ln)

    if not meta.get("title") and outline:
        meta["title"] = outline[0]
    norm_text = _normalize_extracted_text("\n".join(paragraphs))
    flags: List[str] = []
    if not norm_text:
        flags.append("tep_rong")
    stats = compute_text_stats(norm_text, {"paragraphs": len(paragraphs), **app_stats})
    return {
        "status": "tep_rong" if not norm_text else "ok",
        "metadata": meta,
        "stats": stats,
        "outline": outline,
        "text": norm_text,
        "flags": flags,
    }


def read_pptx_file(path: Path) -> Dict[str, Any]:
    """Đọc tệp PowerPoint `.pptx` bằng `zipfile` + XML (`ppt/slides/slide*.xml`)."""
    try:
        with zipfile.ZipFile(path, "r") as zf:
            meta, app_stats = _parse_ooxml_core_and_app(zf)
            slide_names = sorted(
                [n for n in zf.namelist() if re.match(r"^ppt/slides/slide\d+\.xml$", n)],
                key=lambda s: int(re.search(r"(\d+)\.xml$", s).group(1)),  # type: ignore[union-attr]
            )
            slide_texts: List[str] = []
            outline: List[str] = []
            for idx, sname in enumerate(slide_names, 1):
                root = ET.fromstring(zf.read(sname))
                lines: List[str] = []
                for p in root.iter():
                    if _xml_local_name(p.tag) == "p":
                        pts = [c.text for c in p.iter() if _xml_local_name(c.tag) == "t" and c.text]
                        ln = _clean_whitespace("".join(pts))
                        if ln:
                            lines.append(ln)
                if lines:
                    if len(outline) < 40:
                        outline.append(f"Slide {idx}: {lines[0][:90]}")
                    slide_texts.append("\n".join(lines))
    except Exception as e:
        return {"status": "tep_hong", "metadata": {}, "stats": compute_text_stats(""), "outline": [], "text": "", "flags": ["tep_hong"], "error": str(e)}

    norm_text = _normalize_extracted_text("\n\n".join(slide_texts))
    slide_count = len(slide_names) or app_stats.get("slides", 0)
    stats = compute_text_stats(norm_text, {"slides": slide_count, "pages": slide_count})
    flags = ["tep_rong"] if not norm_text else []
    return {
        "status": "tep_rong" if not norm_text else "ok",
        "metadata": meta,
        "stats": stats,
        "outline": outline,
        "text": norm_text,
        "flags": flags,
    }


def read_xlsx_file(path: Path) -> Dict[str, Any]:
    """Đọc tệp Excel `.xlsx` bằng `zipfile` + XML (`workbook.xml`, `sharedStrings.xml`, `sheet*.xml`)."""
    try:
        with zipfile.ZipFile(path, "r") as zf:
            meta, _ = _parse_ooxml_core_and_app(zf)
            sheet_titles: List[str] = []
            if "xl/workbook.xml" in zf.namelist():
                wb = ET.fromstring(zf.read("xl/workbook.xml"))
                for el in wb.iter():
                    if _xml_local_name(el.tag) == "sheet":
                        nm = el.attrib.get("name", "").strip()
                        if nm:
                            sheet_titles.append(nm)
            shared: List[str] = []
            if "xl/sharedStrings.xml" in zf.namelist():
                ss = ET.fromstring(zf.read("xl/sharedStrings.xml"))
                for si in ss.iter():
                    if _xml_local_name(si.tag) == "si":
                        val = "".join(t.text or "" for t in si.iter() if _xml_local_name(t.tag) == "t")
                        shared.append(_clean_whitespace(val))

            ws_files = sorted([n for n in zf.namelist() if re.match(r"^xl/worksheets/sheet\d+\.xml$", n)])
            lines: List[str] = []
            total_rows = 0
            for idx, wsf in enumerate(ws_files):
                sh_name = sheet_titles[idx] if idx < len(sheet_titles) else f"Sheet {idx + 1}"
                lines.append(f"=== {sh_name} ===")
                root = ET.fromstring(zf.read(wsf))
                sheet_rows = 0
                for row_el in root.iter():
                    if _xml_local_name(row_el.tag) != "row":
                        continue
                    total_rows += 1
                    sheet_rows += 1
                    if sheet_rows > 250:
                        continue
                    row_vals: List[str] = []
                    for c in row_el:
                        if _xml_local_name(c.tag) != "c":
                            continue
                        ctype = c.attrib.get("t", "")
                        v_text = ""
                        for sub in c.iter():
                            sn = _xml_local_name(sub.tag)
                            if sn == "v" and sub.text is not None:
                                v_text = sub.text.strip()
                            elif sn == "t" and sub.text is not None:
                                v_text += sub.text
                        if ctype == "s" and v_text.isdigit():
                            si_idx = int(v_text)
                            if 0 <= si_idx < len(shared):
                                v_text = shared[si_idx]
                        if v_text:
                            row_vals.append(_clean_whitespace(v_text))
                    if row_vals:
                        lines.append(" | ".join(row_vals))
    except Exception as e:
        return {"status": "tep_hong", "metadata": {}, "stats": compute_text_stats(""), "outline": [], "text": "", "flags": ["tep_hong"], "error": str(e)}

    norm_text = _normalize_extracted_text("\n".join(lines))
    stats = compute_text_stats(norm_text, {"sheets": len(sheet_titles) or len(ws_files), "rows": total_rows})
    flags = ["tep_rong"] if not norm_text else []
    return {
        "status": "tep_rong" if not norm_text else "ok",
        "metadata": meta,
        "stats": stats,
        "outline": sheet_titles,
        "text": norm_text,
        "flags": flags,
    }


def _parse_opf_xml(xml_bytes: bytes) -> Tuple[Dict[str, Any], Dict[str, str], List[str]]:
    """Phân tích XML `.opf` (Dublin Core metadata, manifest id->href, spine itemrefs)."""
    root = ET.fromstring(xml_bytes)
    meta: Dict[str, Any] = {}
    manifest: Dict[str, str] = {}
    spine: List[str] = []
    subjects: List[str] = []

    for el in root.iter():
        ln = _xml_local_name(el.tag).lower()
        txt = _clean_whitespace(el.text or "")
        if ln == "title" and txt and "title" not in meta:
            meta["title"] = txt
        elif ln == "creator" and txt:
            meta["author"] = f"{meta['author']}, {txt}" if meta.get("author") else txt
        elif ln == "language" and txt and "language" not in meta:
            meta["language"] = txt
        elif ln == "publisher" and txt and "publisher" not in meta:
            meta["publisher"] = txt
        elif ln == "date" and txt and "date" not in meta:
            meta["date"] = txt
        elif ln == "description" and txt and "description" not in meta:
            ext = _HTMLTextExtractor()
            ext.feed(txt)
            meta["description"] = ext.get_text()[:600]
        elif ln == "identifier" and txt:
            if "isbn" in (el.attrib.get("id", "") + str(el.attrib)).lower() or re.match(r"^(97[89])?\d{9}[\dXx]$", re.sub(r"[- ]", "", txt)):
                meta["isbn"] = txt
            else:
                meta.setdefault("identifier", txt)
        elif ln == "subject" and txt:
            subjects.append(txt)
        elif ln == "item":
            iid = el.attrib.get("id", "")
            href = el.attrib.get("href", "")
            if iid and href:
                manifest[iid] = href
        elif ln == "itemref":
            idref = el.attrib.get("idref", "")
            if idref:
                spine.append(idref)

    if subjects:
        meta["subject"] = ", ".join(dict.fromkeys(subjects))
    return meta, manifest, spine


def read_epub_file(path: Path) -> Dict[str, Any]:
    """Đọc sách điện tử `.epub` qua `container.xml` → `.opf` → các chương XHTML trong `spine`."""
    try:
        with zipfile.ZipFile(path, "r") as zf:
            names = zf.namelist()
            opf_path = ""
            if "META-INF/container.xml" in names:
                croot = ET.fromstring(zf.read("META-INF/container.xml"))
                for el in croot.iter():
                    if _xml_local_name(el.tag) == "rootfile":
                        opf_path = el.attrib.get("full-path", "")
                        if opf_path:
                            break
            if not opf_path or opf_path not in names:
                opfs = [n for n in names if n.lower().endswith(".opf")]
                opf_path = opfs[0] if opfs else ""
            if not opf_path:
                return {"status": "tep_hong", "metadata": {}, "stats": compute_text_stats(""), "outline": [], "text": "", "flags": ["tep_hong"]}

            meta, manifest, spine = _parse_opf_xml(zf.read(opf_path))
            opf_dir = str(Path(opf_path).parent)
            if opf_dir == ".":
                opf_dir = ""

            ordered_files: List[str] = []
            for idref in spine:
                href = manifest.get(idref, "")
                if not href:
                    continue
                href_clean = href.split("#", 1)[0]
                full = f"{opf_dir}/{href_clean}" if opf_dir else href_clean
                if full in names:
                    ordered_files.append(full)
                elif href_clean in names:
                    ordered_files.append(href_clean)

            if not ordered_files:
                ordered_files = [n for n in names if n.lower().endswith((".xhtml", ".html", ".htm"))]

            chapters_text: List[str] = []
            outline: List[str] = []
            total_chars = 0
            for ch_path in ordered_files[:80]:
                raw_html, _ = decode_bytes_smart(zf.read(ch_path))
                parser = _HTMLTextExtractor()
                parser.feed(raw_html)
                for h in parser.headings:
                    if h not in outline and len(outline) < 40:
                        outline.append(h)
                ch_txt = parser.get_text()
                if ch_txt:
                    chapters_text.append(ch_txt)
                    total_chars += len(ch_txt)
                    if total_chars >= MAX_CACHED_TEXT_CHARS:
                        break
    except Exception as e:
        return {"status": "tep_hong", "metadata": {}, "stats": compute_text_stats(""), "outline": [], "text": "", "flags": ["tep_hong"], "error": str(e)}

    norm_text = _normalize_extracted_text("\n\n".join(chapters_text))
    est_pages = max(1, round(len(norm_text) / 1800)) if norm_text else 0
    stats = compute_text_stats(norm_text, {"chapters": len(ordered_files), "pages": est_pages})
    flags = ["tep_rong"] if not norm_text else []
    return {
        "status": "tep_rong" if not norm_text else "ok",
        "metadata": meta,
        "stats": stats,
        "outline": outline,
        "text": norm_text,
        "flags": flags,
    }


def read_opf_file(path: Path) -> Dict[str, Any]:
    """Đọc tệp siêu dữ liệu sách `.opf` độc lập."""
    try:
        meta, _, _ = _parse_opf_xml(path.read_bytes())
    except Exception as e:
        return {"status": "tep_hong", "metadata": {}, "stats": compute_text_stats(""), "outline": [], "text": "", "flags": ["tep_hong"], "error": str(e)}
    desc = "\n".join(f"{k}: {v}" for k, v in meta.items() if v)
    return {
        "status": "ok" if meta else "tep_rong",
        "metadata": meta,
        "stats": compute_text_stats(desc),
        "outline": [meta["title"]] if meta.get("title") else [],
        "text": desc,
        "flags": [] if meta else ["tep_rong"],
    }


def _decompress_palmdoc_lz77(data: bytes) -> bytes:
    """Giải nén luồng văn bản PalmDOC LZ77 chuẩn cho tệp MOBI/AZW/PRC."""
    out = bytearray()
    i = 0
    n = len(data)
    while i < n:
        b = data[i]
        i += 1
        if b == 0x00:
            out.append(0x00)
        elif 0x01 <= b <= 0x08:
            out.extend(data[i:i + b])
            i += b
        elif 0x09 <= b <= 0x7F:
            out.append(b)
        elif 0xC0 <= b <= 0xFF:
            out.append(0x20)
            out.append(b ^ 0x80)
        else:  # 0x80..0xBF: cặp khoảng cách - độ dài (2 byte)
            if i >= n:
                break
            b2 = data[i]
            i += 1
            pair = (b << 8) | b2
            dist = (pair >> 3) & 0x07FF
            length = (pair & 0x07) + 3
            if dist == 0 or dist > len(out):
                continue
            for _ in range(length):
                out.append(out[-dist])
    return bytes(out)


def read_mobi_file(path: Path) -> Dict[str, Any]:
    """Đọc sách điện tử `.mobi` / `.azw3` / `.prc`: tiêu đề PalmDB, siêu dữ liệu EXTH và văn bản PalmDOC."""
    try:
        raw = path.read_bytes()
    except OSError as e:
        return {"status": "tep_hong", "metadata": {}, "stats": compute_text_stats(""), "outline": [], "text": "", "flags": ["tep_hong"], "error": str(e)}

    if len(raw) < 78 or raw[60:68] not in (b"BOOKMOBI", b"TEXtREAd"):
        return {"status": "tep_hong", "metadata": {}, "stats": compute_text_stats(""), "outline": [], "text": "", "flags": ["tep_hong"]}

    pdb_title = raw[:32].split(b"\x00", 1)[0].decode("utf-8", errors="ignore").strip()
    num_records = struct.unpack(">H", raw[76:78])[0]
    if num_records == 0 or len(raw) < 78 + num_records * 8:
        return {"status": "tep_hong", "metadata": {"title": pdb_title} if pdb_title else {}, "stats": compute_text_stats(""), "outline": [], "text": "", "flags": ["tep_hong"]}

    offsets = [struct.unpack(">I", raw[78 + i * 8: 82 + i * 8])[0] for i in range(num_records)]
    offsets.append(len(raw))
    rec0 = raw[offsets[0]:offsets[1]]
    if len(rec0) < 16:
        return {"status": "tep_hong", "metadata": {}, "stats": compute_text_stats(""), "outline": [], "text": "", "flags": ["tep_hong"]}

    compression, _, text_length, text_rec_count, _, encryption, _ = (
        struct.unpack(">HHIHHHH", rec0[:16]) if len(rec0) >= 16 else (1, 0, 0, 0, 0, 0, 0)
    )
    meta: Dict[str, Any] = {}
    if pdb_title:
        meta["title"] = pdb_title

    # Đọc MOBI header & EXTH header nếu có
    if len(rec0) >= 24 and rec0[16:20] == b"MOBI":
        mobi_len = struct.unpack(">I", rec0[20:24])[0]
        if len(rec0) >= 92:
            full_name_off, full_name_len = struct.unpack(">II", rec0[84:92])
            if full_name_off + full_name_len <= len(rec0) and full_name_len > 0:
                fn = rec0[full_name_off:full_name_off + full_name_len].decode("utf-8", errors="ignore").strip()
                if fn:
                    meta["title"] = fn
        exth_flags = struct.unpack(">I", rec0[128:132])[0] if len(rec0) >= 132 else 0
        exth_off = 16 + mobi_len
        if (exth_flags & 0x40) and len(rec0) >= exth_off + 12 and rec0[exth_off:exth_off + 4] == b"EXTH":
            exth_count = struct.unpack(">I", rec0[exth_off + 8:exth_off + 12])[0]
            pos = exth_off + 12
            for _ in range(exth_count):
                if pos + 8 > len(rec0):
                    break
                rtype, rlen = struct.unpack(">II", rec0[pos:pos + 8])
                if rlen < 8 or pos + rlen > len(rec0):
                    break
                val = rec0[pos + 8:pos + rlen].decode("utf-8", errors="ignore").strip()
                pos += rlen
                if not val:
                    continue
                if rtype == 100:
                    meta["author"] = val
                elif rtype == 101:
                    meta["publisher"] = val
                elif rtype == 103:
                    meta["description"] = val[:600]
                elif rtype == 104:
                    meta["isbn"] = val
                elif rtype == 105:
                    meta["subject"] = val
                elif rtype == 503:
                    meta["title"] = val
                elif rtype == 524:
                    meta["language"] = val

    flags: List[str] = []
    if encryption != 0:
        flags.append("co_mat_khau")
        return {"status": "co_mat_khau", "metadata": meta, "stats": compute_text_stats(""), "outline": [], "text": "", "flags": flags}

    # Giải nén tối đa 35 bản ghi văn bản đầu tiên
    max_rec = min(num_records - 1, max(1, min(text_rec_count, 35)))
    raw_chunks: List[bytes] = []
    for r_idx in range(1, max_rec + 1):
        chunk = raw[offsets[r_idx]:offsets[r_idx + 1]]
        if compression == 1:
            raw_chunks.append(chunk)
        elif compression == 2:
            raw_chunks.append(_decompress_palmdoc_lz77(chunk))

    html_str, _ = decode_bytes_smart(b"".join(raw_chunks))
    parser = _HTMLTextExtractor()
    parser.feed(html_str)
    norm_text = _normalize_extracted_text(parser.get_text())
    est_pages = max(1, round((text_length or len(norm_text)) / 1800)) if (text_length or norm_text) else 0
    stats = compute_text_stats(norm_text, {"pages": est_pages})
    return {
        "status": "ok",
        "metadata": meta,
        "stats": stats,
        "outline": parser.headings[:30],
        "text": norm_text,
        "flags": flags,
    }


def read_ole_legacy_file(path: Path) -> Dict[str, Any]:
    """Trích xuất chuỗi văn bản UTF-16LE và UTF-8/CP1258 từ tệp Office OLE2 cũ (`.doc`, `.xls`, `.ppt`)."""
    try:
        raw = path.read_bytes()
    except OSError as e:
        return {"status": "tep_hong", "metadata": {}, "stats": compute_text_stats(""), "outline": [], "text": "", "flags": ["tep_hong"], "error": str(e)}

    if not raw.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        # Đôi khi tệp .doc thực chất là RTF hoặc văn bản thuần
        return read_text_like_file(path, "txt")

    chunks: List[str] = []
    # 1. Trích chuỗi UTF-16LE (ký tự tiếng Việt và Latin trong Word/PPT OLE2)
    for m in re.finditer(rb"(?:[\x20-\x7e\r\n\t]\x00|[\x00-\xff][\x01-\x02\x1e-\x20]){8,}", raw):
        s = m.group(0).decode("utf-16-le", errors="ignore").strip()
        if len(s) >= 8 and not s.startswith(("Root Entry", "WordDocument", "SummaryInformation", "DocumentSummary")):
            chunks.append(s)
    # 2. Trích chuỗi ASCII/UTF-8 dài
    for m in re.finditer(rb"[\x20-\x7e\r\n\t]{16,}", raw):
        s = m.group(0).decode("latin-1", errors="ignore").strip()
        if any(k in s for k in ("Root Entry", "Microsoft", "Normal.dot", "Times New Roman", "Arial", "Calibri", "MSWordDoc")):
            continue
        if sum(c.isalpha() for c in s) >= len(s) * 0.55:
            chunks.append(s)

    norm_text = _normalize_extracted_text("\n".join(chunks[:400]))
    stats = compute_text_stats(norm_text)
    return {
        "status": "ok" if norm_text else "tep_rong",
        "metadata": {},
        "stats": stats,
        "outline": [],
        "text": norm_text,
        "flags": [] if norm_text else ["tep_rong"],
    }


def read_text_like_file(path: Path, ext: str) -> Dict[str, Any]:
    """Đọc các tệp văn bản: MD, TXT, CSV/TSV, HTML, JSON, PY/TS/JS/SH."""
    try:
        raw = path.read_bytes()
    except OSError as e:
        return {"status": "tep_hong", "metadata": {}, "stats": compute_text_stats(""), "outline": [], "text": "", "flags": ["tep_hong"], "error": str(e)}

    text, encoding = decode_bytes_smart(raw)
    ext = (ext or "").lower().lstrip(".")
    meta: Dict[str, Any] = {"encoding": encoding}
    outline: List[str] = []
    flags: List[str] = []

    if ext in {"html", "htm"}:
        parser = _HTMLTextExtractor()
        parser.feed(text)
        if parser.title:
            meta["title"] = parser.title
        for k in ("author", "description", "keywords"):
            if k in parser.meta:
                meta[k] = parser.meta[k]
        outline = parser.headings
        norm_text = _normalize_extracted_text(parser.get_text())
    elif ext == "json":
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                outline = [str(k) for k in list(obj.keys())[:30]]
                meta["json_type"] = "object"
                meta["key_count"] = len(obj)
            elif isinstance(obj, list):
                meta["json_type"] = "array"
                meta["item_count"] = len(obj)
            norm_text = _normalize_extracted_text(text[:MAX_CACHED_TEXT_CHARS])
        except json.JSONDecodeError as e:
            flags.append("tep_hong")
            return {
                "status": "tep_hong",
                "metadata": meta,
                "stats": compute_text_stats(text),
                "outline": [],
                "text": _normalize_extracted_text(text[:10_000]),
                "flags": flags,
                "error": f"JSON không hợp lệ: {e}",
            }
    elif ext in {"csv", "tsv"}:
        delim = "\t" if ext == "tsv" else ","
        reader = csv.reader(io.StringIO(text), delimiter=delim)
        rows = list(reader)
        header = [c.strip() for c in rows[0]] if rows else []
        outline = [h for h in header if h][:30]
        preview_rows = [" | ".join(c.strip() for c in r if c.strip()) for r in rows[:250]]
        norm_text = _normalize_extracted_text("\n".join(preview_rows))
        stats = compute_text_stats(norm_text, {"rows": len(rows), "columns": len(header)})
        return {
            "status": "ok" if norm_text else "tep_rong",
            "metadata": meta,
            "stats": stats,
            "outline": outline,
            "text": norm_text,
            "flags": [] if norm_text else ["tep_rong"],
        }
    elif ext == "md":
        # Tách YAML frontmatter nếu có
        m_fm = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, flags=re.DOTALL)
        if m_fm:
            for ln in m_fm.group(1).splitlines():
                if ":" in ln:
                    k, v = ln.split(":", 1)
                    k = k.strip().lower()
                    v = v.strip().strip("\"'")
                    if k in {"title", "author", "tags", "date", "category"} and v:
                        meta[k] = v
        for ln in text.splitlines():
            m_h = re.match(r"^(#{1,3})\s+(.+)$", ln.strip())
            if m_h:
                h = _clean_whitespace(m_h.group(2))
                if h and len(outline) < 40:
                    outline.append(h)
        if not meta.get("title") and outline:
            meta["title"] = outline[0]
        norm_text = _normalize_extracted_text(text)
    elif ext in {"py", "ts", "js", "sh"}:
        for ln in text.splitlines():
            m_sym = re.match(r"^\s*(def|class|function|async\s+def|export\s+function|export\s+class)\s+([A-Za-z_][A-Za-z0-9_]*)", ln)
            if m_sym and len(outline) < 50:
                outline.append(f"{m_sym.group(1)} {m_sym.group(2)}")
        norm_text = _normalize_extracted_text(text)
    else:
        norm_text = _normalize_extracted_text(text)

    if not norm_text:
        flags.append("tep_rong")
    return {
        "status": "tep_rong" if not norm_text else "ok",
        "metadata": meta,
        "stats": compute_text_stats(norm_text),
        "outline": outline,
        "text": norm_text,
        "flags": flags,
    }


def read_image_file(path: Path, enable_ocr: bool = False) -> Dict[str, Any]:
    """Đọc thông số kỹ thuật ảnh (kích thước, hệ màu, EXIF) bằng `Pillow` và OCR tùy chọn."""
    meta: Dict[str, Any] = {}
    stats: Dict[str, Any] = {}
    flags: List[str] = []
    text = ""
    try:
        from PIL import ExifTags, Image  # type: ignore
        with Image.open(path) as img:
            width, height = img.size
            stats["width"] = width
            stats["height"] = height
            meta["image_format"] = img.format or ""
            meta["color_mode"] = img.mode or ""
            exif_fn = getattr(img, "getexif", None)
            if exif_fn:
                exif = exif_fn()
                tag_map = {ExifTags.TAGS.get(k, str(k)): v for k, v in exif.items()}
                for src_k, dst_k in (
                    ("ImageDescription", "title"),
                    ("Artist", "author"),
                    ("DateTimeOriginal", "created"),
                    ("DateTime", "modified"),
                    ("Make", "camera_make"),
                    ("Model", "camera_model"),
                ):
                    if src_k in tag_map and tag_map[src_k]:
                        meta[dst_k] = str(tag_map[src_k]).strip()
    except Exception as e:
        return {"status": "tep_hong", "metadata": {}, "stats": compute_text_stats(""), "outline": [], "text": "", "flags": ["tep_hong"], "error": str(e)}

    if enable_ocr and shutil.which("tesseract"):
        try:
            ocr_txt, _ = sc.ocr_image_file(path)
            if ocr_txt:
                text = _normalize_extracted_text(ocr_txt)
                if text:
                    flags.append("da_ocr")
        except Exception:
            pass

    summary = text or f"Ảnh {meta.get('image_format', '')} {stats.get('width', 0)}x{stats.get('height', 0)} ({meta.get('color_mode', '')})".strip()
    return {
        "status": "ok",
        "metadata": meta,
        "stats": compute_text_stats(text, stats),
        "outline": [],
        "text": summary,
        "flags": flags,
    }


def read_media_file(path: Path) -> Dict[str, Any]:
    """Đọc thời lượng, codec, bitrate, độ phân giải và thẻ tag âm thanh/video bằng `ffprobe`."""
    meta: Dict[str, Any] = {}
    extra_stats: Dict[str, Any] = {}
    outline: List[str] = []

    if shutil.which("ffprobe"):
        try:
            proc = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", str(path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                info = json.loads(proc.stdout)
                fmt = info.get("format", {}) or {}
                if fmt.get("duration"):
                    try:
                        extra_stats["duration_sec"] = round(float(fmt["duration"]), 2)
                    except ValueError:
                        pass
                if fmt.get("bit_rate") and str(fmt["bit_rate"]).isdigit():
                    extra_stats["bitrate_kbps"] = round(int(fmt["bit_rate"]) / 1000)
                tags = fmt.get("tags", {}) or {}
                for k, v in tags.items():
                    kl = k.lower()
                    val = str(v).strip()
                    if not val:
                        continue
                    if kl == "title":
                        meta["title"] = val
                    elif kl in {"artist", "album_artist", "author"}:
                        meta["author"] = val
                    elif kl == "album":
                        meta["album"] = val
                    elif kl == "genre":
                        meta["subject"] = val
                    elif kl in {"date", "year", "creation_time"}:
                        meta["date"] = val

                for st in info.get("streams", []) or []:
                    ctype = st.get("codec_type")
                    cname = st.get("codec_name", "")
                    if ctype == "video" and "video_codec" not in extra_stats:
                        extra_stats["video_codec"] = cname
                        if st.get("width") and st.get("height"):
                            extra_stats["width"] = int(st["width"])
                            extra_stats["height"] = int(st["height"])
                    elif ctype == "audio" and "audio_codec" not in extra_stats:
                        extra_stats["audio_codec"] = cname
                        if st.get("sample_rate") and str(st["sample_rate"]).isdigit():
                            extra_stats["sample_rate"] = int(st["sample_rate"])
        except Exception:
            pass

    # Dự phòng đọc ID3v1 (128 byte cuối) cho tệp MP3 thử nghiệm
    try:
        raw = path.read_bytes()
        if len(raw) >= 128 and raw[-128:-125] == b"TAG":
            t = raw[-125:-95].rstrip(b"\x00 ").decode("utf-8", errors="ignore").strip()
            a = raw[-95:-65].rstrip(b"\x00 ").decode("utf-8", errors="ignore").strip()
            al = raw[-65:-35].rstrip(b"\x00 ").decode("utf-8", errors="ignore").strip()
            if t:
                meta.setdefault("title", t)
            if a:
                meta.setdefault("author", a)
            if al:
                meta.setdefault("album", al)
    except Exception:
        pass

    if not extra_stats and not meta:
        return {"status": "tep_hong", "metadata": {}, "stats": compute_text_stats(""), "outline": [], "text": "", "flags": ["tep_hong"]}

    desc_parts = [f"{k}: {v}" for k, v in {**meta, **extra_stats}.items() if v is not None]
    text = "\n".join(desc_parts)
    if meta.get("title"):
        outline.append(meta["title"])
    return {
        "status": "ok",
        "metadata": meta,
        "stats": compute_text_stats(text, extra_stats),
        "outline": outline,
        "text": text,
        "flags": [],
    }


def read_archive_file(path: Path, ext: str, deep_test: bool = False) -> Dict[str, Any]:
    """Liệt kê mục bên trong tệp nén ZIP / RAR / 7Z, phát hiện mật khẩu và kiểm tra CRC."""
    ext = (ext or "").lower().lstrip(".")
    entries: List[str] = []
    uncompressed_bytes = 0
    encrypted = False
    corrupted = False
    flags: List[str] = []

    if ext == "zip" or detect_magic_format(path) == "zip":
        try:
            with zipfile.ZipFile(path, "r") as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    entries.append(info.filename)
                    uncompressed_bytes += int(info.file_size or 0)
                    if info.flag_bits & 0x1:
                        encrypted = True
                if deep_test and not encrypted:
                    bad = zf.testzip()
                    if bad is not None:
                        corrupted = True
        except Exception as e:
            return {"status": "tep_hong", "metadata": {}, "stats": compute_text_stats(""), "outline": [], "text": "", "flags": ["tep_hong"], "error": str(e)}
    elif shutil.which("7z"):
        try:
            proc = subprocess.run(["7z", "l", "-slt", str(path)], capture_output=True, text=True, timeout=45)
            if proc.returncode == 0:
                curr_path = ""
                is_folder = False
                for ln in proc.stdout.splitlines():
                    ln = ln.strip()
                    if ln.startswith("Path = "):
                        curr_path = ln[7:].strip()
                        is_folder = False
                    elif ln.startswith("Folder = +"):
                        is_folder = True
                    elif ln.startswith("Size = ") and not is_folder:
                        val = ln[7:].strip()
                        if val.isdigit():
                            uncompressed_bytes += int(val)
                        if curr_path and curr_path != str(path):
                            entries.append(curr_path)
                    elif ln.startswith("Encrypted = +"):
                        encrypted = True
                if deep_test and not encrypted:
                    tproc = subprocess.run(["7z", "t", str(path)], capture_output=True, text=True, timeout=60)
                    if tproc.returncode != 0:
                        corrupted = True
            else:
                corrupted = True
        except Exception:
            corrupted = True
    else:
        return {"status": "tep_hong", "metadata": {}, "stats": compute_text_stats(""), "outline": [], "text": "", "flags": ["tep_hong"]}

    if encrypted:
        flags.append("co_mat_khau")
    if corrupted:
        flags.append("tep_hong")

    ext_counts: Dict[str, int] = {}
    for e in entries:
        _, sub_ext = sc.split_ext(Path(e).name)
        if sub_ext:
            ext_counts[sub_ext.lower()] = ext_counts.get(sub_ext.lower(), 0) + 1
    top_exts = ", ".join(f".{k} ({v})" for k, v in sorted(ext_counts.items(), key=lambda x: -x[1])[:8])

    meta: Dict[str, Any] = {"top_extensions": top_exts} if top_exts else {}
    text = "\n".join(entries[:500])
    stats = compute_text_stats(text, {"archive_entries": len(entries), "uncompressed_bytes": uncompressed_bytes, "encrypted": encrypted})
    status = "tep_hong" if corrupted else ("co_mat_khau" if encrypted else "ok")
    return {
        "status": status,
        "metadata": meta,
        "stats": stats,
        "outline": entries[:25],
        "text": text,
        "flags": flags,
    }


# ---------------------------------------------------------------------------
# 3. ĐIỀU PHỐI ĐỌC TỆP CỤC BỘ & GOOGLE DRIVE + BỘ ĐỆM (CACHE)
# ---------------------------------------------------------------------------

def read_local_file(
    path: Path,
    name: Optional[str] = None,
    mime: str = "",
    max_pages: int = 40,
    enable_ocr: bool = False,
    deep_test: bool = False,
) -> Dict[str, Any]:
    """Đọc một tệp trên đĩa cục bộ và trả về bản ghi trích xuất chuẩn hóa."""
    path = Path(path)
    display_name = name or path.name
    _, ext = sc.split_ext(display_name, mime)
    ext = ext.lower()

    if not path.exists():
        return {"status": "tep_hong", "ext": ext, "magic_format": "missing", "sha256": "", "metadata": {}, "stats": compute_text_stats(""), "outline": [], "text": "", "flags": ["tep_hong"]}

    size = path.stat().st_size
    sha256 = sc.sha256_file(path)
    if size == 0:
        return {
            "status": "tep_rong",
            "ext": ext,
            "magic_format": "empty",
            "sha256": sha256,
            "metadata": {},
            "stats": compute_text_stats(""),
            "outline": [],
            "text": "",
            "flags": ["tep_rong"],
        }

    magic_fmt = detect_magic_format(path)
    mismatch = check_format_mismatch(ext, magic_fmt)

    # Chọn bộ đọc theo định dạng thực tế hoặc phần mở rộng
    effective = ext
    if magic_fmt in {"pdf", "docx", "pptx", "xlsx", "epub", "mobi", "rar", "7z", "png", "jpg", "gif", "webp"}:
        effective = magic_fmt
    elif magic_fmt == "ole" and ext not in OLE_EXTENSIONS:
        effective = "doc"

    if effective == "pdf":
        res = read_pdf_file(path, max_pages=max_pages, enable_ocr=enable_ocr)
    elif effective == "docx":
        res = read_docx_file(path)
    elif effective == "pptx":
        res = read_pptx_file(path)
    elif effective == "xlsx":
        res = read_xlsx_file(path)
    elif effective == "epub":
        res = read_epub_file(path)
    elif effective == "opf":
        res = read_opf_file(path)
    elif effective in EBOOK_MOBI_EXTENSIONS or magic_fmt == "mobi":
        res = read_mobi_file(path)
    elif effective in OLE_EXTENSIONS or magic_fmt == "ole":
        res = read_ole_legacy_file(path)
    elif effective in IMAGE_EXTENSIONS:
        res = read_image_file(path, enable_ocr=enable_ocr)
    elif effective in AUDIO_EXTENSIONS or effective in VIDEO_EXTENSIONS or (effective == "ts" and magic_fmt == "ts"):
        res = read_media_file(path)
    elif effective in ARCHIVE_EXTENSIONS or magic_fmt in {"zip", "rar", "7z"}:
        res = read_archive_file(path, effective, deep_test=deep_test)
    elif effective in TEXT_EXTENSIONS or magic_fmt == "text":
        res = read_text_like_file(path, effective)
    else:
        res = {
            "status": "ok",
            "metadata": {},
            "stats": compute_text_stats(""),
            "outline": [],
            "text": "",
            "flags": ["dinh_dang_nhi_phan"],
        }

    flags = list(dict.fromkeys(res.get("flags", [])))
    if mismatch and "sai_khop_dinh_dang" not in flags:
        flags.append("sai_khop_dinh_dang")

    full_text = (res.get("text") or "")[:MAX_CACHED_TEXT_CHARS]
    return {
        "status": res.get("status", "ok"),
        "ext": ext,
        "magic_format": magic_fmt,
        "sha256": sha256,
        "metadata": res.get("metadata", {}),
        "stats": res.get("stats", compute_text_stats(full_text)),
        "outline": res.get("outline", []),
        "text_preview": full_text[:MAX_PREVIEW_CHARS],
        "text": full_text,
        "flags": flags,
        "error": res.get("error", ""),
    }


def cache_record_path(file_id: str) -> Path:
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", file_id)
    return sc.content_cache_dir() / "records" / f"{safe_id}.json"


def cache_text_path(file_id: str) -> Path:
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", file_id)
    return sc.content_cache_dir() / "text" / f"{safe_id}.txt"


def load_cached_record(
    file_id: str,
    modified_time: Optional[str] = None,
    include_text: bool = False,
) -> Optional[Dict[str, Any]]:
    """Đọc bản ghi trích xuất từ bộ đệm nếu khớp `modifiedTime`."""
    rp = cache_record_path(file_id)
    rec = sc.read_json(rp)
    if not isinstance(rec, dict):
        return None
    if modified_time and rec.get("modifiedTime") and rec.get("modifiedTime") != modified_time:
        return None
    if include_text:
        tp = cache_text_path(file_id)
        rec["text"] = tp.read_text(encoding="utf-8") if tp.exists() else rec.get("text_preview", "")
    return rec


def save_cached_record(record: Dict[str, Any], text: str = "") -> Dict[str, Any]:
    """Lưu bản ghi siêu dữ liệu vào `records/<id>.json` và văn bản đầy đủ vào `text/<id>.txt`."""
    fid = record["id"]
    clean_rec = {k: v for k, v in record.items() if k != "text"}
    trimmed_text = (text or "")[:MAX_CACHED_TEXT_CHARS]
    clean_rec["text_preview"] = trimmed_text[:MAX_PREVIEW_CHARS]
    sc.write_json(cache_record_path(fid), clean_rec)
    cache_text_path(fid).write_text(trimmed_text, encoding="utf-8")
    return clean_rec


def iter_cached_records(
    branch: Optional[str] = None,
    include_text: bool = False,
    index: Optional[dict] = None,
) -> List[Dict[str, Any]]:
    """Duyệt toàn bộ bản ghi đã có trong bộ đệm, cập nhật đường dẫn mới nhất từ `index` nếu có."""
    norm_branch = sc.normalize_branch(branch)
    prefix = norm_branch.rstrip("/") + "/" if norm_branch else ""
    id_to_entry: Dict[str, Tuple[str, dict]] = {}
    if index:
        _, id_to_entry = sc.build_id_map(index)

    out: List[Dict[str, Any]] = []
    rec_dir = sc.content_cache_dir() / "records"
    for p in sorted(rec_dir.glob("*.json")):
        rec = sc.read_json(p)
        if not isinstance(rec, dict) or not rec.get("id"):
            continue
        fid = rec["id"]
        if fid in id_to_entry:
            parent_path, item = id_to_entry[fid]
            rec["parent_path"] = parent_path
            rec["name"] = item.get("name", rec.get("name", ""))
            rec["path"] = f"{parent_path}/{rec['name']}"
        path_val = rec.get("path") or rec.get("parent_path") or ""
        if norm_branch and not (path_val == norm_branch or path_val.startswith(prefix)):
            continue
        if include_text:
            tp = cache_text_path(fid)
            rec["text"] = tp.read_text(encoding="utf-8") if tp.exists() else rec.get("text_preview", "")
        out.append(rec)
    return out


def read_drive_item(
    item: dict,
    parent_path: str,
    drive: sc.Drive,
    force_refresh: bool = False,
    max_mb: float = 50.0,
    max_pages: int = 40,
    enable_ocr: bool = False,
    deep_test: bool = False,
) -> Dict[str, Any]:
    """
    Tải (hoặc lấy từ bộ đệm) một mục trên Google Drive, trích xuất nội dung & siêu dữ liệu,
    lưu bộ đệm và xóa tệp tạm ngay lập tức.
    """
    fid = item["id"]
    name = item.get("name", fid)
    mime = item.get("mimeType", "")
    size = int(item.get("size") or 0)
    mod = item.get("modifiedTime", "")
    full_path = f"{parent_path}/{name}" if parent_path else name
    _, ext = sc.split_ext(name, mime)
    ext = ext.lower()

    if not force_refresh:
        cached = load_cached_record(fid, modified_time=mod, include_text=False)
        if cached is not None:
            cached["cache_hit"] = True
            return cached

    max_bytes = int(max_mb * 1024 * 1024) if max_mb and max_mb > 0 else 0
    if max_bytes > 0 and size > max_bytes and mime not in sc.GOOGLE_NATIVE_MIMES:
        rec = {
            "id": fid,
            "name": name,
            "path": full_path,
            "parent_path": parent_path,
            "mimeType": mime,
            "ext": ext,
            "size": size,
            "modifiedTime": mod,
            "extracted_at": sc.now_utc_iso(),
            "status": "qua_dung_luong",
            "magic_format": "skipped_large",
            "sha256": "",
            "metadata": {},
            "stats": {"char_count": 0, "word_count": 0, "line_count": 0},
            "outline": [],
            "text_preview": "",
            "flags": ["qua_dung_luong"],
            "cache_hit": False,
        }
        return save_cached_record(rec, "")

    tmp_dir = Path(tempfile.mkdtemp(prefix="storage_read_"))
    try:
        if mime == GOOGLE_DOC_MIME:
            local_tmp = tmp_dir / f"{name}.md"
            drive.export(fid, local_tmp, "md")
            parsed = read_local_file(local_tmp, name=f"{name}.md", mime="text/markdown")
            parsed["ext"] = "gdoc"
            parsed["magic_format"] = "gdoc"
        elif mime == GOOGLE_SHEET_MIME:
            local_tmp = tmp_dir / f"{name}.csv"
            drive.export(fid, local_tmp, "csv")
            parsed = read_local_file(local_tmp, name=f"{name}.csv", mime="text/csv")
            parsed["ext"] = "gsheet"
            parsed["magic_format"] = "gsheet"
        elif mime == GOOGLE_SLIDE_MIME:
            local_tmp = tmp_dir / f"{name}.txt"
            drive.export(fid, local_tmp, "txt")
            parsed = read_local_file(local_tmp, name=f"{name}.txt", mime="text/plain")
            parsed["ext"] = "gslide"
            parsed["magic_format"] = "gslide"
        else:
            safe_fname = re.sub(r"[/\\:\x00]", "_", name) or f"{fid}.{ext or 'bin'}"
            local_tmp = tmp_dir / safe_fname
            drive.download(fid, local_tmp)
            parsed = read_local_file(
                local_tmp,
                name=name,
                mime=mime,
                max_pages=max_pages,
                enable_ocr=enable_ocr,
                deep_test=deep_test,
            )
    except Exception as e:
        rec = {
            "id": fid,
            "name": name,
            "path": full_path,
            "parent_path": parent_path,
            "mimeType": mime,
            "ext": ext,
            "size": size,
            "modifiedTime": mod,
            "extracted_at": sc.now_utc_iso(),
            "status": "loi_tai",
            "magic_format": "error",
            "sha256": "",
            "metadata": {},
            "stats": {"char_count": 0, "word_count": 0, "line_count": 0},
            "outline": [],
            "text_preview": "",
            "flags": ["loi_tai"],
            "error": str(e),
            "cache_hit": False,
        }
        return rec
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    rec = {
        "id": fid,
        "name": name,
        "path": full_path,
        "parent_path": parent_path,
        "mimeType": mime,
        "ext": parsed.get("ext", ext),
        "size": size,
        "modifiedTime": mod,
        "extracted_at": sc.now_utc_iso(),
        "status": parsed["status"],
        "magic_format": parsed["magic_format"],
        "sha256": parsed["sha256"],
        "metadata": parsed["metadata"],
        "stats": parsed["stats"],
        "outline": parsed["outline"],
        "text_preview": parsed["text_preview"],
        "flags": parsed["flags"],
        "error": parsed.get("error", ""),
        "cache_hit": False,
    }
    saved = save_cached_record(rec, parsed.get("text", ""))
    saved["cache_hit"] = False
    return saved


def select_candidate_items(
    index: dict,
    branch: Optional[str] = None,
    exts: Optional[Set[str]] = None,
    min_mb: float = 0.0,
    include_quarantine: bool = False,
    include_tong_quan: bool = False,
    limit: int = 100,
) -> List[Tuple[str, dict]]:
    """Lọc danh sách mục từ `storage_index.json` để đưa vào lô đọc và trích xuất."""
    norm_branch = sc.normalize_branch(branch)
    min_bytes = int(min_mb * 1024 * 1024) if min_mb and min_mb > 0 else 0
    explicit_tq = bool(norm_branch and sc.TONG_QUAN_FOLDER in norm_branch)
    explicit_qr = bool(norm_branch and sc.is_quarantine_path(norm_branch))

    candidates: List[Tuple[str, dict]] = []
    for parent_path, it in sc.iter_items(index, branch=norm_branch):
        mime = it.get("mimeType", "")
        if mime in {sc.FOLDER_MIME, sc.SHORTCUT_MIME}:
            continue
        if not include_quarantine and not explicit_qr and sc.is_quarantine_path(parent_path):
            continue
        if not include_tong_quan and not explicit_tq and (sc.is_in_tong_quan(parent_path) or parent_path.endswith(f"/{sc.TONG_QUAN_FOLDER}")):
            continue
        if mime in sc.GOOGLE_NATIVE_MIMES and mime not in {GOOGLE_DOC_MIME, GOOGLE_SHEET_MIME, GOOGLE_SLIDE_MIME}:
            continue
        name = it.get("name", "")
        _, ext = sc.split_ext(name, mime)
        ext = ext.lower()
        if mime == GOOGLE_DOC_MIME:
            ext = "gdoc"
        elif mime == GOOGLE_SHEET_MIME:
            ext = "gsheet"
        elif mime == GOOGLE_SLIDE_MIME:
            ext = "gslide"
        if exts and ext not in exts:
            continue
        sz = int(it.get("size") or 0)
        if min_bytes > 0 and sz < min_bytes:
            continue
        candidates.append((parent_path, it))
        if limit > 0 and len(candidates) >= limit:
            break
    return candidates


def batch_extract(
    index: dict,
    drive: sc.Drive,
    branch: Optional[str] = None,
    exts: Optional[Set[str]] = None,
    max_mb: float = 50.0,
    min_mb: float = 0.0,
    limit: int = 100,
    workers: int = 4,
    force_refresh: bool = False,
    max_pages: int = 40,
    enable_ocr: bool = False,
    deep_test: bool = False,
    include_quarantine: bool = False,
) -> Dict[str, Any]:
    """Trích xuất nội dung song song theo lô có kiểm soát và trả về tổng hợp kết quả."""
    candidates = select_candidate_items(
        index,
        branch=branch,
        exts=exts,
        min_mb=min_mb,
        include_quarantine=include_quarantine,
        limit=limit,
    )
    t0 = time.time()
    records: List[Dict[str, Any]] = []
    w = max(1, min(16, int(workers or 4)))

    def _one(pair: Tuple[str, dict]) -> Dict[str, Any]:
        p_path, item = pair
        return read_drive_item(
            item,
            p_path,
            drive,
            force_refresh=force_refresh,
            max_mb=max_mb,
            max_pages=max_pages,
            enable_ocr=enable_ocr,
            deep_test=deep_test,
        )

    if w == 1 or len(candidates) <= 1:
        for pair in candidates:
            records.append(_one(pair))
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=w) as pool:
            for rec in pool.map(_one, candidates):
                records.append(rec)

    by_status: Dict[str, int] = {}
    by_ext: Dict[str, int] = {}
    cache_hits = 0
    for r in records:
        st = r.get("status", "ok")
        by_status[st] = by_status.get(st, 0) + 1
        ex = r.get("ext") or "(không đuôi)"
        by_ext[ex] = by_ext.get(ex, 0) + 1
        if r.get("cache_hit"):
            cache_hits += 1

    return {
        "total": len(records),
        "cache_hits": cache_hits,
        "fresh_extracted": len(records) - cache_hits,
        "elapsed_sec": round(time.time() - t0, 2),
        "by_status": by_status,
        "by_ext": by_ext,
        "records": records,
    }


def cache_stats(index: Optional[dict] = None) -> Dict[str, Any]:
    """Thống kê toàn bộ bộ đệm `content_cache` hiện có."""
    recs = iter_cached_records(include_text=False, index=index)
    by_status: Dict[str, int] = {}
    by_ext: Dict[str, int] = {}
    by_flag: Dict[str, int] = {}
    total_words = 0
    total_chars = 0
    for r in recs:
        st = r.get("status", "ok")
        by_status[st] = by_status.get(st, 0) + 1
        ex = r.get("ext") or "(không đuôi)"
        by_ext[ex] = by_ext.get(ex, 0) + 1
        for fl in r.get("flags", []):
            by_flag[fl] = by_flag.get(fl, 0) + 1
        st_obj = r.get("stats", {}) or {}
        total_words += int(st_obj.get("word_count") or 0)
        total_chars += int(st_obj.get("char_count") or 0)
    return {
        "total_cached": len(recs),
        "total_words": total_words,
        "total_chars": total_chars,
        "by_status": by_status,
        "by_ext": by_ext,
        "by_flag": by_flag,
    }


# ---------------------------------------------------------------------------
# 4. GIAO DIỆN DÒNG LỆNH (CLI)
# ---------------------------------------------------------------------------

def _print_single_record(rec: Dict[str, Any]) -> None:
    sc.log("=" * 76)
    sc.log(f"📄 TỆP       : {rec.get('name', '')}")
    if rec.get("id"):
        sc.log(f"🔑 ID        : {rec['id']}")
    if rec.get("path"):
        sc.log(f"📂 ĐƯỜNG DẪN : {rec['path']}")
    sc.log(
        f"🏷️  ĐỊNH DẠNG : .{rec.get('ext', '')} (magic={rec.get('magic_format', '')}) | "
        f"Dung lượng: {sc.human_size(rec.get('size'))} | Trạng thái: {rec.get('status')}"
    )
    if rec.get("sha256"):
        sc.log(f"🔒 SHA-256   : {rec['sha256']}")
    if rec.get("flags"):
        sc.log(f"⚠️  CỜ        : {', '.join(rec['flags'])}")
    meta = rec.get("metadata") or {}
    if meta:
        sc.log("📋 SIÊU DỮ LIỆU:")
        for k, v in meta.items():
            sc.log(f"   • {k}: {v}")
    st = rec.get("stats") or {}
    if st:
        sc.log("📊 THỐNG KÊ  : " + ", ".join(f"{k}={v}" for k, v in st.items()))
    outline = rec.get("outline") or []
    if outline:
        sc.log("📑 DÀN Ý / MỤC LỤC (tối đa 10 mục đầu):")
        for item in outline[:10]:
            sc.log(f"   - {item}")
    preview = rec.get("text_preview") or (rec.get("text", "")[:MAX_PREVIEW_CHARS])
    if preview:
        sc.log("-" * 76)
        sc.log("📝 ĐOẠN TRÍCH NỘI DUNG:")
        sc.log(preview[:900])
    sc.log("=" * 76)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Bộ đọc tệp đa định dạng và trích xuất nội dung/siêu dữ liệu cho [A] STORAGE (v3.1)."
    )
    ap.add_argument(
        "lenh",
         nargs="?",
        default="thong-ke",
        choices=["doc", "trich-xuat", "thong-ke"],
        help="Lệnh: doc (đọc 1 tệp), trich-xuat (trích xuất theo lô vào cache), thong-ke (xem bộ đệm).",
    )
    ap.add_argument("muc_tieu", nargs="?", help="ID/URL Google Drive hoặc đường dẫn tệp cục bộ (cho lệnh `doc`).")
    ap.add_argument("--nhanh", help="Giới hạn trong một nhánh thư mục của kho.")
    ap.add_argument("--dinh-dang", help="Danh sách đuôi tệp cách nhau dấu phẩy (ví dụ: pdf,epub,docx,md).")
    ap.add_argument("--min-mb", type=float, default=0.0, help="Dung lượng tối thiểu (MB).")
    ap.add_argument("--max-mb", type=float, default=50.0, help="Dung lượng tối đa mỗi tệp tải về (mặc định 50 MB).")
    ap.add_argument("--gioi-han", type=int, default=50, help="Số tệp tối đa trong một lô (mặc định 50, 0 = không giới hạn).")
    ap.add_argument("--luong", type=int, default=4, help="Số luồng tải và trích xuất song song (mặc định 4).")
    ap.add_argument("--so-trang-pdf", type=int, default=40, help="Số trang PDF tối đa trích xuất mỗi tệp (mặc định 40).")
    ap.add_argument("--ocr", action="store_true", help="Bật OCR Tesseract cho PDF scan hoặc ảnh.")
    ap.add_argument("--kiem-tra-sau", action="store_true", help="Kiểm tra toàn vẹn CRC sâu cho tệp nén ZIP/RAR/7Z.")
    ap.add_argument("--lam-moi", action="store_true", help="Bỏ qua bộ đệm, tải và trích xuất lại từ đầu.")
    ap.add_argument("--ke-ca-kiem-tra", action="store_true", help="Bao gồm cả vùng [07] KIỂM TRA.")
    args = ap.parse_args()

    if args.lenh == "doc":
        if not args.muc_tieu:
            raise SystemExit("Vui lòng truyền ID/URL Google Drive hoặc đường dẫn tệp cục bộ cho lệnh `doc`.")
        local_p = Path(args.muc_tieu).expanduser()
        if local_p.exists() and local_p.is_file():
            res = read_local_file(
                local_p,
                max_pages=args.so_trang_pdf,
                enable_ocr=args.ocr,
                deep_test=args.kiem_tra_sau,
            )
            res["name"] = local_p.name
            res["path"] = str(local_p)
            res["size"] = local_p.stat().st_size
            _print_single_record(res)
            return

        fid = sc.extract_drive_id(args.muc_tieu)
        index = sc.load_index(required=False)
        _, id_map = sc.build_id_map(index)
        drive = sc.create_drive()
        if fid in id_map:
            parent_path, item = id_map[fid]
        else:
            info = drive.info(fid)
            parent_path = ""
            item = {
                "id": fid,
                "name": info.get("name", fid),
                "mimeType": info.get("mimeType", ""),
                "size": info.get("size", 0),
                "modifiedTime": info.get("modifiedTime", ""),
            }
        rec = read_drive_item(
            item,
            parent_path,
            drive,
            force_refresh=args.lam_moi,
            max_mb=args.max_mb,
            max_pages=args.so_trang_pdf,
            enable_ocr=args.ocr,
            deep_test=args.kiem_tra_sau,
        )
        _print_single_record(rec)
        return

    if args.lenh == "trich-xuat":
        index = sc.load_index(required=True)
        drive = sc.create_drive()
        exts = {e.strip().lower().lstrip(".") for e in args.dinh_dang.split(",") if e.strip()} if args.dinh_dang else None
        summary = batch_extract(
            index,
            drive,
            branch=args.nhanh,
            exts=exts,
            max_mb=args.max_mb,
            min_mb=args.min_mb,
            limit=args.gioi_han,
            workers=args.luong,
            force_refresh=args.lam_moi,
            max_pages=args.so_trang_pdf,
            enable_ocr=args.ocr,
            deep_test=args.kiem_tra_sau,
            include_quarantine=args.ke_ca_kiem_tra,
        )
        sc.log(
            f"✅ Hoàn tất trích xuất lô: tổng={summary['total']} tệp "
            f"(mới={summary['fresh_extracted']}, từ cache={summary['cache_hits']}) trong {summary['elapsed_sec']}s"
        )
        sc.log(f"   • Theo trạng thái : {summary['by_status']}")
        sc.log(f"   • Theo định dạng  : {summary['by_ext']}")
        return

    index = sc.load_index(required=False)
    st = cache_stats(index=index)
    sc.log(f"📦 BỘ ĐỆM TRÍCH XUẤT NỘI DUNG ({sc.content_cache_dir()}):")
    sc.log(f"   • Tổng số tệp đã lưu cache : {sc.fmt_int(st['total_cached'])}")
    sc.log(f"   • Tổng số từ trích xuất    : {sc.fmt_int(st['total_words'])}")
    sc.log(f"   • Tổng số ký tự trích xuất : {sc.fmt_int(st['total_chars'])}")
    sc.log(f"   • Phân bố trạng thái       : {st['by_status']}")
    sc.log(f"   • Phân bố định dạng        : {st['by_ext']}")
    if st["by_flag"]:
        sc.log(f"   • Phân bố cờ cảnh báo      : {st['by_flag']}")


if __name__ == "__main__":
    main()
