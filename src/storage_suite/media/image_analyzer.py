#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PHÂN TÍCH HÌNH ẢNH, CHẤT LƯỢNG THỊ GIÁC, OCR & VÂN TAY TRÙNG LẶP — [A] STORAGE (v3.3)
======================================================================================
Chương trình `[16] PHÂN TÍCH HÌNH ẢNH/image_analyzer.py` quản trị toàn diện các tệp ảnh trong kho:

1. `phan-tich`   : Phân tích danh sách ảnh trong bộ đệm `media_cache/image/` (hoặc tự động
                   tải & quét theo lô khi truyền `--tu-dong-doc`): thông số kích thước, DPI, tỷ lệ khung,
                   EXIF/GPS, bảng màu chủ đạo, độ sắc nét Laplacian, độ sáng/tương phản, vai trò ảnh,
                   OCR tùy chọn (`--ocr`), chữ ký trực quan `dHash`/`pHash 64-bit`, xuất `.md` & `.csv`.
2. `doc`         : Đọc & phân tích tức thì 1 tệp ảnh theo Drive ID/URL hoặc đường dẫn cục bộ.
3. `trung-anh`   : Phát hiện ảnh trùng tuyệt đối (`SHA-256`) và gần trùng trực quan (`dHash`/`pHash`)
                   bất chấp nén lại hay đổi kích thước; tùy chọn cách ly bản kém hơn (`--gom-trung`).
4. `goi-y-ten`   : Đề xuất chuẩn hóa tên Chuẩn V6 từ EXIF, ngày chụp, tiêu đề OCR và ngữ cảnh nhánh.
5. `hoan-tac-ten`: Hoàn tác lô đổi tên ảnh gần nhất từ `media_rename_log.json`.
6. `tim-anh`     : Tìm kiếm nhanh trong `media_cache/image/` theo chữ OCR, vai trò ảnh, màu, kích thước hoặc cờ.
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import math
import re
import shutil
import struct
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple


from storage_suite import core as sc

IMAGE_EXTENSIONS: Set[str] = {
    "jpg", "jpeg", "png", "webp", "gif", "bmp", "tif", "tiff", "heic", "heif", "psd", "cdr",
}

OPAQUE_IMAGE_NAME_RE = re.compile(
    r"^(?:img\d*|dscn?\d*|pxl\d*|mvimg|screenshot|screen\s*shot|capture|photo|image|picture|zalo|untitled|scan|camscanner|z\d{6,}|\d{5,})(?:[ _-]|$)",
    re.I,
)

# Ngưỡng chất lượng thị giác mặc định
BLUR_LAPLACIAN_THRESHOLD = 45.0
DARK_BRIGHTNESS_THRESHOLD = 35.0
OVEREXPOSED_BRIGHTNESS_THRESHOLD = 235.0
LOW_CONTRAST_STD_THRESHOLD = 18.0
LOW_RES_MIN_SIDE = 480

_TESSERACT_LANG_CACHE: Optional[Tuple[str, Optional[str]]] = None


# ---------------------------------------------------------------------------
# 1. TIỆN ÍCH ĐỊNH DẠNG, MÃ HÓA & PERCEPTUAL HASH (dHash / pHash)
# ---------------------------------------------------------------------------

def _pil_resample_lanczos():
    from PIL import Image  # type: ignore
    res = getattr(Image, "Resampling", None)
    return res.LANCZOS if res is not None else Image.LANCZOS


def detect_image_magic(path: Path) -> str:
    """Nhận diện định dạng ảnh thực tế từ magic bytes đầu tệp."""
    try:
        with open(path, "rb") as f:
            head = f.read(64)
    except OSError:
        return "missing"
    if not head:
        return "empty"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if head.startswith(b"RIFF") and len(head) >= 12:
        if head[8:12] == b"WEBP":
            return "webp"
        if head[8:12].startswith(b"CDR"):
            return "cdr"
    if head.startswith(b"BM"):
        return "bmp"
    if head.startswith((b"II*\x00", b"MM\x00*")):
        return "tiff"
    if head.startswith(b"8BPS"):
        return "psd"
    if len(head) >= 12 and head[4:8] == b"ftyp" and head[8:12] in {b"heic", b"heix", b"hevc", b"mif1", b"msf1", b"avif"}:
        return "heic"
    return "unknown"


def hamming_distance64(hex_a: str, hex_b: str) -> int:
    """Tính khoảng cách Hamming giữa hai mã hash 64-bit dạng hex."""
    if not hex_a or not hex_b:
        return 64
    return (int(hex_a, 16) ^ int(hex_b, 16)).bit_count()


def compute_dhash64_from_pil(img) -> str:
    """Tính dHash 64-bit (gradient ngang 9x8) trên đối tượng `PIL.Image.Image`."""
    import numpy as np  # type: ignore
    gray = img.convert("L").resize((9, 8), _pil_resample_lanczos())
    arr = np.asarray(gray, dtype=np.int16)
    diff = arr[:, :-1] > arr[:, 1:]
    val = 0
    for bit in diff.flatten():
        val = (val << 1) | (1 if bit else 0)
    return f"{val:016x}"


def _dct_matrix(n: int):
    import numpy as np  # type: ignore
    k = np.arange(n, dtype=np.float64)[:, None]
    x = np.arange(n, dtype=np.float64)[None, :]
    c = np.cos(math.pi * (2.0 * x + 1.0) * k / (2.0 * n))
    c[0, :] *= math.sqrt(1.0 / n)
    c[1:, :] *= math.sqrt(2.0 / n)
    return c


_DCT32_CACHE = None


def compute_phash64_from_pil(img) -> str:
    """Tính pHash 64-bit (DCT-2D 32x32, giữ tần số thấp 8x8) bất biến trước nén & co giãn."""
    global _DCT32_CACHE
    import numpy as np  # type: ignore
    if _DCT32_CACHE is None:
        _DCT32_CACHE = _dct_matrix(32)
    c = _DCT32_CACHE
    gray = img.convert("L").resize((32, 32), _pil_resample_lanczos())
    arr = np.asarray(gray, dtype=np.float64)
    dct = (c @ arr) @ c.T
    low = dct[:8, :8].flatten()
    # Bỏ qua thành phần DC [0] khi tính trung vị để kháng biến đổi độ sáng đồng đều
    med = float(np.median(low[1:]))
    bits = low >= med
    bits[0] = False
    val = 0
    for b in bits:
        val = (val << 1) | (1 if b else 0)
    return f"{val:016x}"


def compute_image_hashes_from_pil(img) -> Tuple[str, str]:
    """Trả về `(dhash_hex, phash_hex)` cho một khung ảnh `PIL.Image.Image`."""
    return compute_dhash64_from_pil(img), compute_phash64_from_pil(img)


# ---------------------------------------------------------------------------
# 2. SIÊU DỮ LIỆU EXIF/GPS, CHẤT LƯỢNG THỊ GIÁC & OCR
# ---------------------------------------------------------------------------

def _aspect_label(w: int, h: int) -> str:
    if w <= 0 or h <= 0:
        return "khac"
    ratio = w / float(h)
    presets = [
        (16 / 9, "16:9"),
        (9 / 16, "9:16"),
        (4 / 3, "4:3"),
        (3 / 4, "3:4"),
        (3 / 2, "3:2"),
        (2 / 3, "2:3"),
        (1.0, "1:1"),
    ]
    best_lbl = "khac"
    best_diff = 0.08
    for target, lbl in presets:
        diff = abs(ratio - target) / target
        if diff < best_diff:
            best_diff = diff
            best_lbl = lbl
    return best_lbl


def _extract_exif_metadata(img) -> Tuple[Dict[str, Any], bool]:
    from PIL import ExifTags  # type: ignore
    meta: Dict[str, Any] = {}
    has_gps = False

    # 1. PNG info / metadata văn bản nhúng
    info = getattr(img, "info", {}) or {}
    for k_src, k_dst in (("Title", "title"), ("Author", "author"), ("Description", "title"), ("Software", "software")):
        v = info.get(k_src)
        if isinstance(v, str) and v.strip():
            meta.setdefault(k_dst, sc.nfc(v.strip())[:240])
    if "dpi" in info and isinstance(info["dpi"], tuple) and len(info["dpi"]) == 2:
        try:
            meta["dpi"] = [round(float(info["dpi"][0])), round(float(info["dpi"][1]))]
        except Exception:
            pass

    # 2. EXIF tags chuẩn
    exif_fn = getattr(img, "getexif", None)
    if not exif_fn:
        return meta, has_gps
    try:
        exif = exif_fn()
    except Exception:
        return meta, has_gps
    if not exif:
        return meta, has_gps

    tag_map = {ExifTags.TAGS.get(k, str(k)): v for k, v in exif.items()}
    for src_k, dst_k in (
        ("ImageDescription", "title"),
        ("Artist", "author"),
        ("DateTimeOriginal", "created"),
        ("DateTime", "modified"),
        ("Make", "camera_make"),
        ("Model", "camera_model"),
        ("Software", "software"),
        ("Orientation", "orientation"),
    ):
        val = tag_map.get(src_k)
        if val is not None and str(val).strip():
            if dst_k == "orientation":
                try:
                    meta[dst_k] = int(val)
                except Exception:
                    pass
            else:
                meta.setdefault(dst_k, sc.nfc(str(val).strip())[:240])

    # Kiểm tra sub-IFD EXIF & GPSInfo (tag 0x8825 = 34853)
    try:
        exif_ifd = exif.get_ifd(0x8769)
        if exif_ifd:
            sub_map = {ExifTags.TAGS.get(k, str(k)): v for k, v in exif_ifd.items()}
            if sub_map.get("DateTimeOriginal") and not meta.get("created"):
                meta["created"] = str(sub_map["DateTimeOriginal"]).strip()
    except Exception:
        pass

    try:
        gps_ifd = exif.get_ifd(0x8825)
        if gps_ifd and len(gps_ifd) > 0:
            has_gps = True
    except Exception:
        if "GPSInfo" in tag_map and tag_map["GPSInfo"]:
            has_gps = True

    return meta, has_gps


def _compute_dominant_colors(img, top_n: int = 3) -> List[Dict[str, Any]]:
    import numpy as np  # type: ignore
    small = img.convert("RGB").resize((64, 64), _pil_resample_lanczos())
    arr = np.asarray(small, dtype=np.uint8).reshape(-1, 3)
    # Lượng tử hóa nhẹ về bước 32 để gom nhóm sắc độ ổn định và cực nhanh
    q = (arr // 32) * 32 + 16
    keys, counts = np.unique(q, axis=0, return_counts=True)
    order = np.argsort(-counts)
    total = float(len(arr)) or 1.0
    out: List[Dict[str, Any]] = []
    for idx in order[:top_n]:
        r, g, b = [min(255, int(c)) for c in keys[idx]]
        pct = round((float(counts[idx]) / total) * 100.0, 1)
        out.append({"hex": f"#{r:02x}{g:02x}{b:02x}", "pct": pct})
    return out


def compute_visual_quality(img) -> Dict[str, Any]:
    """Đánh giá độ nét Laplacian, độ sáng, tương phản và bảng màu chủ đạo."""
    import numpy as np  # type: ignore

    # Chuẩn hóa kích thước phân tích về cạnh dài tối đa 1024px để tốc độ ổn định O(1M pixel)
    w, h = img.size
    max_side = max(w, h)
    if max_side > 1024:
        scale = 1024.0 / float(max_side)
        work = img.resize((max(8, int(w * scale)), max(8, int(h * scale))), _pil_resample_lanczos())
    else:
        work = img

    gray = np.asarray(work.convert("L"), dtype=np.float32)
    brightness_mean = round(float(np.mean(gray)), 2)
    contrast_std = round(float(np.std(gray)), 2)

    if gray.shape[0] >= 3 and gray.shape[1] >= 3:
        lap = (
            gray[:-2, 1:-1]
            + gray[2:, 1:-1]
            + gray[1:-1, :-2]
            + gray[1:-1, 2:]
            - 4.0 * gray[1:-1, 1:-1]
        )
        lap_var = round(float(np.var(lap)), 2)
    else:
        lap_var = 0.0

    # Độ bão hòa màu (kênh S trong HSV)
    hsv_arr = np.asarray(work.convert("HSV"), dtype=np.float32)
    sat_mean = round(float(np.mean(hsv_arr[:, :, 1])) / 255.0 * 100.0, 1)
    dominant = _compute_dominant_colors(work, top_n=3)

    return {
        "sharpness_laplacian": lap_var,
        "brightness_mean": brightness_mean,
        "contrast_std": contrast_std,
        "saturation_pct": sat_mean,
        "dominant_colors": dominant,
    }


def _resolve_tesseract_lang() -> Tuple[str, Optional[str]]:
    """Tự động phát hiện gói ngôn ngữ `vie+eng` qua động cơ OCR hợp nhất `core.ocr`."""
    return sc.resolve_tesseract_lang()


def run_image_ocr_from_pil(img) -> Tuple[str, str]:
    """Tiền xử lý tương phản + phóng đại nhẹ và chạy `tesseract` OCR qua `core.ocr`."""
    return sc.ocr_pil_image(img)


def _extract_first_heading(ocr_text: str) -> str:
    noise_chars = set("¢=\\|{}[]~^`<>")
    for ln in (ocr_text or "").splitlines():
        s = re.sub(r"^[#>*\-•.:;\d\s]+", "", ln).strip(" .,:;-_")
        if len(s) < 6 or len(s) > 90:
            continue
        if any(ch in s for ch in noise_chars) or ".." in s:
            continue
        non_space = [c for c in s if not c.isspace()]
        if not non_space:
            continue
        alpha = sum(1 for c in non_space if c.isalpha())
        if alpha < 5 or (alpha / len(non_space)) < 0.65:
            continue
        tokens = s.split()
        if len(tokens) == 1 and len(s) < 6:
            continue
        good_tokens = [t for t in tokens if sum(1 for c in t if c.isalpha()) >= 2]
        if len(good_tokens) < max(1, math.ceil(len(tokens) * 0.55)):
            continue
        return s
    return ""


def classify_image_role(
    name: str,
    ext: str,
    stats: Dict[str, Any],
    meta: Dict[str, Any],
    ocr_words: int = 0,
    parent_path: str = "",
) -> str:
    """Phân loại vai trò hình ảnh phục vụ thống kê kho học tập."""
    low_name = name.lower()
    if ext in {"psd", "cdr"} or (meta.get("color_mode") in {"RGBA", "CMYK"} and "canva" in parent_path.lower()):
        return "do_hoa_thiet_ke"
    if meta.get("camera_make") or meta.get("camera_model") or meta.get("has_gps"):
        return "anh_chup_camera"
    if any(k in low_name for k in ("screenshot", "chup man hinh", "man hinh", "screen shot")):
        return "anh_man_hinh"
    w = int(stats.get("width") or 0)
    h = int(stats.get("height") or 0)
    if ocr_words >= 12 or (h > w and stats.get("saturation_pct", 100.0) < 25.0):
        return "tai_lieu_chup_ocr"
    if _aspect_label(w, h) in {"16:9", "4:3"} and stats.get("contrast_std", 0.0) >= 18.0:
        return "slide_bai_giang"
    if ext == "png":
        return "anh_man_hinh"
    return "anh_tai_lieu"


# ---------------------------------------------------------------------------
# 3. ĐỌC & PHÂN TÍCH MỘT TỆP ẢNH CỤC BỘ HOẶC GOOGLE DRIVE
# ---------------------------------------------------------------------------

def _inspect_psd_header(path: Path) -> Dict[str, Any]:
    raw = path.read_bytes()[:32]
    if len(raw) >= 26 and raw[:4] == b"8BPS":
        channels, height, width, depth, color_mode = struct.unpack(">HIIHH", raw[12:26])
        return {"width": int(width), "height": int(height), "channels": int(channels), "depth": int(depth)}
    return {}


def analyze_local_image(
    path: Path,
    name: Optional[str] = None,
    parent_path: str = "",
    enable_ocr: bool = False,
) -> Dict[str, Any]:
    """Phân tích đầy đủ 1 tệp ảnh trên đĩa cục bộ."""
    from PIL import Image, ImageSequence  # type: ignore

    path = Path(path)
    display_name = name or path.name
    _, ext = sc.split_ext(display_name)
    ext = ext.lower()

    if not path.exists():
        return {"status": "anh_hong", "ext": ext, "flags": ["anh_hong"], "metadata": {}, "stats": {}, "ocr_text": ""}

    size = path.stat().st_size
    sha256 = sc.sha256_file(path)
    if size == 0:
        return {"status": "tep_rong", "ext": ext, "sha256": sha256, "flags": ["tep_rong"], "metadata": {}, "stats": {}, "ocr_text": ""}

    magic = detect_image_magic(path)
    flags: List[str] = []
    if ext in {"jpg", "jpeg"} and magic not in {"jpg", "unknown"}:
        flags.append("sai_khop_dinh_dang")
    elif ext in {"png", "gif", "webp", "bmp", "psd", "cdr"} and magic not in {ext, "unknown"}:
        flags.append("sai_khop_dinh_dang")

    # Tệp vector/nguồn đặc biệt mà Pillow không giải mã đầy đủ
    if ext == "cdr" or (ext == "heic" and magic == "heic"):
        try:
            with Image.open(path) as img:
                img.load()
        except Exception:
            return {
                "status": "dinh_dang_dac_biet",
                "ext": ext,
                "magic_format": magic,
                "sha256": sha256,
                "metadata": {"special_format": ext.upper()},
                "stats": {"width": 0, "height": 0, "megapixels": 0.0, "aspect_label": "khac"},
                "quality": {},
                "hashes": {"dhash": "", "phash": ""},
                "role": "do_hoa_thiet_ke" if ext == "cdr" else "anh_chup_camera",
                "ocr_text": "",
                "ocr_heading": "",
                "flags": flags + ["dinh_dang_dac_biet"],
            }

    try:
        with Image.open(path) as img:
            img.load()
            w, h = img.size
            fmt = img.format or ext.upper()
            mode = img.mode or ""
            is_anim = bool(getattr(img, "is_animated", False))
            n_frames = int(getattr(img, "n_frames", 1) or 1)
            if is_anim and n_frames <= 1:
                n_frames = sum(1 for _ in ImageSequence.Iterator(img))

            meta, has_gps = _extract_exif_metadata(img)
            meta["image_format"] = fmt
            meta["color_mode"] = mode
            meta["has_gps"] = has_gps
            if has_gps:
                flags.append("co_gps_exif")

            quality = compute_visual_quality(img)
            dhash, phash = compute_image_hashes_from_pil(img)

            ocr_text = ""
            ocr_lang = ""
            if enable_ocr:
                ocr_text, ocr_lang = run_image_ocr_from_pil(img)
                if ocr_text:
                    flags.append("da_ocr")
                    meta["ocr_lang"] = ocr_lang
    except Exception as e:
        if ext == "psd" and magic == "psd":
            psd_info = _inspect_psd_header(path)
            return {
                "status": "dinh_dang_dac_biet",
                "ext": ext,
                "magic_format": magic,
                "sha256": sha256,
                "metadata": {"special_format": "PSD"},
                "stats": {**psd_info, "megapixels": round(psd_info.get("width", 0) * psd_info.get("height", 0) / 1_000_000, 3)},
                "quality": {},
                "hashes": {"dhash": "", "phash": ""},
                "role": "do_hoa_thiet_ke",
                "ocr_text": "",
                "ocr_heading": "",
                "flags": flags + ["dinh_dang_dac_biet"],
            }
        return {
            "status": "anh_hong",
            "ext": ext,
            "magic_format": magic,
            "sha256": sha256,
            "metadata": {},
            "stats": {},
            "quality": {},
            "hashes": {"dhash": "", "phash": ""},
            "role": "khac",
            "ocr_text": "",
            "ocr_heading": "",
            "flags": flags + ["anh_hong"],
            "error": str(e),
        }

    # Đánh dấu các cờ chất lượng thị giác
    contrast_std = float(quality.get("contrast_std", 0.0))
    lap_var = float(quality.get("sharpness_laplacian", 0.0))
    bright = float(quality.get("brightness_mean", 128.0))
    if contrast_std < LOW_CONTRAST_STD_THRESHOLD:
        flags.append("anh_it_tuong_phan")
    if lap_var < BLUR_LAPLACIAN_THRESHOLD and contrast_std >= 10.0:
        flags.append("anh_mo")
    if bright < DARK_BRIGHTNESS_THRESHOLD:
        flags.append("anh_qua_toi")
    elif bright > OVEREXPOSED_BRIGHTNESS_THRESHOLD and (contrast_std < 22.0 or (lap_var < 80.0 and contrast_std < 35.0)):
        flags.append("anh_chay_sang")
    if min(w, h) < LOW_RES_MIN_SIDE:
        flags.append("anh_thap_phan_giai")

    ocr_words = len(re.findall(r"\w+", ocr_text)) if ocr_text else 0
    stats = {
        "width": w,
        "height": h,
        "megapixels": round((w * h) / 1_000_000.0, 3),
        "aspect_label": _aspect_label(w, h),
        "is_animated": is_anim,
        "frames": n_frames,
        "ocr_word_count": ocr_words,
    }
    role = classify_image_role(display_name, ext, {**stats, **quality}, meta, ocr_words=ocr_words, parent_path=parent_path)
    heading = _extract_first_heading(ocr_text)

    return {
        "status": "ok",
        "ext": ext,
        "magic_format": magic,
        "sha256": sha256,
        "metadata": meta,
        "stats": stats,
        "quality": quality,
        "hashes": {"dhash": dhash, "phash": phash},
        "role": role,
        "ocr_heading": heading,
        "ocr_text": ocr_text,
        "flags": list(dict.fromkeys(flags)),
    }


# ---------------------------------------------------------------------------
# 4. BỘ ĐỆM BỀN VỮNG & QUÉT THEO LÔ TRÊN GOOGLE DRIVE
# ---------------------------------------------------------------------------

def cache_record_path(file_id: str) -> Path:
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", file_id)
    return sc.media_cache_dir("image") / f"{safe_id}.json"


def load_cached_image(file_id: str, modified_time: Optional[str] = None) -> Optional[Dict[str, Any]]:
    rec = sc.read_json(cache_record_path(file_id))
    if not isinstance(rec, dict):
        return None
    if modified_time and rec.get("modifiedTime") and rec.get("modifiedTime") != modified_time:
        return None
    return rec


def save_cached_image(record: Dict[str, Any]) -> Dict[str, Any]:
    sc.write_json(cache_record_path(record["id"]), record)
    return record


def iter_cached_images(branch: Optional[str] = None, index: Optional[dict] = None) -> List[Dict[str, Any]]:
    norm_branch = sc.normalize_branch(branch)
    prefix = norm_branch.rstrip("/") + "/" if norm_branch else ""
    id_to_entry: Dict[str, Tuple[str, dict]] = {}
    if index:
        _, id_to_entry = sc.build_id_map(index)

    out: List[Dict[str, Any]] = []
    for p in sorted(sc.media_cache_dir("image").glob("*.json")):
        rec = sc.read_json(p)
        if not isinstance(rec, dict) or not rec.get("id"):
            continue
        fid = rec["id"]
        if fid in id_to_entry:
            pp, item = id_to_entry[fid]
            rec["parent_path"] = pp
            rec["name"] = item.get("name", rec.get("name", ""))
            rec["path"] = f"{pp}/{rec['name']}"
        pv = rec.get("path") or rec.get("parent_path") or ""
        if norm_branch and not (pv == norm_branch or pv.startswith(prefix)):
            continue
        out.append(rec)
    return out


def analyze_drive_image(
    item: dict,
    parent_path: str,
    drive: sc.Drive,
    force_refresh: bool = False,
    max_mb: float = 25.0,
    enable_ocr: bool = False,
) -> Dict[str, Any]:
    """Tải tạm (nếu chưa có cache), phân tích 1 tệp ảnh trên Drive và xóa tệp tạm ngay."""
    fid = item["id"]
    name = item.get("name", fid)
    mime = item.get("mimeType", "")
    size = int(item.get("size") or 0)
    mod = item.get("modifiedTime", "")
    full_path = f"{parent_path}/{name}" if parent_path else name
    _, ext = sc.split_ext(name, mime)
    ext = ext.lower()

    if not force_refresh:
        cached = load_cached_image(fid, modified_time=mod)
        if cached is not None and (not enable_ocr or "da_ocr" in cached.get("flags", []) or cached.get("ocr_checked")):
            cached["cache_hit"] = True
            return cached

    max_bytes = int(max_mb * 1024 * 1024) if max_mb and max_mb > 0 else 0
    if max_bytes > 0 and size > max_bytes:
        rec = {
            "id": fid, "name": name, "path": full_path, "parent_path": parent_path,
            "mimeType": mime, "ext": ext, "size": size, "modifiedTime": mod,
            "analyzed_at": sc.now_utc_iso(), "status": "qua_dung_luong",
            "metadata": {}, "stats": {}, "quality": {}, "hashes": {"dhash": "", "phash": ""},
            "role": "khac", "ocr_heading": "", "ocr_text": "", "ocr_checked": enable_ocr,
            "flags": ["qua_dung_luong"], "cache_hit": False,
        }
        return save_cached_image(rec)

    tmp_dir = Path(tempfile.mkdtemp(prefix="storage_img_"))
    try:
        safe_name = re.sub(r"[/\\:\x00]", "_", name) or f"{fid}.{ext or 'jpg'}"
        local_tmp = tmp_dir / safe_name
        drive.download(fid, local_tmp)
        parsed = analyze_local_image(local_tmp, name=name, parent_path=parent_path, enable_ocr=enable_ocr)
    except Exception as e:
        return {
            "id": fid, "name": name, "path": full_path, "parent_path": parent_path,
            "mimeType": mime, "ext": ext, "size": size, "modifiedTime": mod,
            "analyzed_at": sc.now_utc_iso(), "status": "loi_tai",
            "metadata": {}, "stats": {}, "quality": {}, "hashes": {"dhash": "", "phash": ""},
            "role": "khac", "ocr_heading": "", "ocr_text": "", "ocr_checked": enable_ocr,
            "flags": ["loi_tai"], "error": str(e), "cache_hit": False,
        }
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    rec = {
        "id": fid, "name": name, "path": full_path, "parent_path": parent_path,
        "mimeType": mime, "ext": parsed.get("ext", ext), "size": size, "modifiedTime": mod,
        "analyzed_at": sc.now_utc_iso(),
        "status": parsed.get("status", "ok"),
        "magic_format": parsed.get("magic_format", ""),
        "sha256": parsed.get("sha256", ""),
        "metadata": parsed.get("metadata", {}),
        "stats": parsed.get("stats", {}),
        "quality": parsed.get("quality", {}),
        "hashes": parsed.get("hashes", {"dhash": "", "phash": ""}),
        "role": parsed.get("role", "khac"),
        "ocr_heading": parsed.get("ocr_heading", ""),
        "ocr_text": (parsed.get("ocr_text") or "")[:20_000],
        "ocr_checked": enable_ocr,
        "flags": parsed.get("flags", []),
        "error": parsed.get("error", ""),
        "cache_hit": False,
    }
    return save_cached_image(rec)


def select_image_candidates(
    index: dict,
    branch: Optional[str] = None,
    include_quarantine: bool = False,
    limit: int = 30,
) -> List[Tuple[str, dict]]:
    norm_branch = sc.normalize_branch(branch)
    explicit_qr = bool(norm_branch and sc.is_quarantine_path(norm_branch))
    out: List[Tuple[str, dict]] = []
    for pp, it in sc.iter_items(index, branch=norm_branch):
        mime = it.get("mimeType", "")
        if mime in {sc.FOLDER_MIME, sc.SHORTCUT_MIME} or mime in sc.GOOGLE_NATIVE_MIMES:
            continue
        if not include_quarantine and not explicit_qr and sc.is_quarantine_path(pp):
            continue
        _, ext = sc.split_ext(it.get("name", ""), mime)
        if ext.lower() in IMAGE_EXTENSIONS or mime.startswith("image/"):
            out.append((pp, it))
            if limit > 0 and len(out) >= limit:
                break
    return out


def batch_analyze_images(
    index: dict,
    drive: sc.Drive,
    branch: Optional[str] = None,
    max_mb: float = 25.0,
    limit: int = 30,
    workers: int = 4,
    enable_ocr: bool = False,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    cands = select_image_candidates(index, branch=branch, limit=limit)
    records: List[Dict[str, Any]] = []
    if cands:
        with cf.ThreadPoolExecutor(max_workers=max(1, min(workers, len(cands)))) as pool:
            futs = [
                pool.submit(
                    analyze_drive_image, it, pp, drive,
                    force_refresh=force_refresh, max_mb=max_mb, enable_ocr=enable_ocr,
                )
                for pp, it in cands
            ]
            for f in cf.as_completed(futs):
                records.append(f.result())
    records.sort(key=lambda r: r.get("path", ""))
    errs = [r for r in records if r.get("status") == "loi_tai"]
    if errs:
        sc.log(f"⚠️  {len(errs)}/{len(records)} ảnh lỗi tải/xử lý (ví dụ: {errs[0].get('name')}: {errs[0].get('error', '')[:160]})")
    return {"total": len(records), "cache_hits": sum(1 for r in records if r.get("cache_hit")), "errors": len(errs), "records": records}


# ---------------------------------------------------------------------------
# 5. TRÙNG LẶP TRỰC QUAN (PERCEPTUAL HASH) & ĐỔI TÊN CHUẨN V6
# ---------------------------------------------------------------------------

def _rank_image_keep(rec: Dict[str, Any]) -> Tuple[int, float, int, int, str]:
    st = rec.get("stats") or {}
    q = rec.get("quality") or {}
    area = int(st.get("width") or 0) * int(st.get("height") or 0)
    sharp = float(q.get("sharpness_laplacian") or 0.0)
    has_v6 = 1 if (" - " in rec.get("name", "") and not OPAQUE_IMAGE_NAME_RE.match(rec.get("name", ""))) else 0
    return (area, round(sharp, 1), has_v6, -int(rec.get("path", "").count("/")), rec.get("id", ""))


def find_visual_duplicates(
    records: Sequence[Dict[str, Any]],
    max_hamming: int = 6,
) -> Dict[str, Any]:
    """Phát hiện ảnh trùng tuyệt đối (SHA-256) và trùng trực quan (dHash/pHash) bằng đồ thị nối nhóm."""
    by_sha: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)
    hashed: List[Dict[str, Any]] = []

    for r in records:
        if r.get("status") != "ok":
            continue
        if r.get("sha256"):
            by_sha[r["sha256"]].append(r)
        hs = r.get("hashes") or {}
        if hs.get("dhash") and hs.get("phash"):
            hashed.append(r)

    exact_groups: List[Dict[str, Any]] = []
    exact_member_ids: Set[str] = set()
    for sha, grp in by_sha.items():
        if len(grp) > 1:
            ordered = sorted(grp, key=_rank_image_keep, reverse=True)
            exact_groups.append({"sha256": sha, "keep": ordered[0], "extra": ordered[1:], "count": len(grp)})
            for g in ordered[1:]:
                exact_member_ids.add(g["id"])

    # Gom cặp tương đồng trực quan (bỏ qua các bản đã bị loại bởi trùng SHA-256)
    pool = [r for r in hashed if r.get("id") not in exact_member_ids]
    n = len(pool)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    pair_scores: List[Dict[str, Any]] = []
    for i in range(n):
        hi = pool[i]["hashes"]
        dh_i, ph_i = hi["dhash"], hi["phash"]
        for j in range(i + 1, n):
            hj = pool[j]["hashes"]
            d_dist = hamming_distance64(dh_i, hj["dhash"])
            p_dist = hamming_distance64(ph_i, hj["phash"])
            if min(d_dist, p_dist) <= max_hamming and max(d_dist, p_dist) <= max_hamming + 4:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[rj] = ri
                sim = round((1.0 - ((d_dist + p_dist) / 128.0)) * 100.0, 1)
                pair_scores.append({
                    "a": pool[i], "b": pool[j],
                    "dhash_dist": d_dist, "phash_dist": p_dist, "similarity_pct": sim,
                })

    clusters: Dict[int, List[Dict[str, Any]]] = collections.defaultdict(list)
    for idx in range(n):
        clusters[find(idx)].append(pool[idx])

    visual_groups: List[Dict[str, Any]] = []
    for grp in clusters.values():
        if len(grp) > 1:
            ordered = sorted(grp, key=_rank_image_keep, reverse=True)
            visual_groups.append({"keep": ordered[0], "extra": ordered[1:], "count": len(grp)})

    visual_groups.sort(key=lambda g: -g["count"])
    pair_scores.sort(key=lambda p: (p["dhash_dist"] + p["phash_dist"]))
    return {"exact_groups": exact_groups, "visual_groups": visual_groups, "pairs": pair_scores}


def quarantine_visual_duplicates(
    dup_result: Dict[str, Any],
    drive: sc.Drive,
    index: Optional[dict] = None,
    execute: bool = False,
) -> Dict[str, Any]:
    """Đưa bản ảnh trùng kém chất lượng hơn vào `[07] KIỂM TRA/[03] TỆP TRÙNG LẶP` (mặc định chạy thử)."""
    moves: List[dict] = []
    seen_ids: Set[str] = set()
    for grp in dup_result.get("exact_groups", []) + dup_result.get("visual_groups", []):
        keep = grp["keep"]
        for ex in grp["extra"]:
            if ex["id"] in seen_ids:
                continue
            seen_ids.add(ex["id"])
            moves.append({
                "id": ex["id"],
                "name": ex["name"],
                "from_path": ex.get("parent_path", ""),
                "kind": "duplicate",
                "subkind": "visual_duplicate",
                "keep_id": keep["id"],
                "keep_path": keep.get("parent_path", ""),
            })

    if not execute or not moves:
        return {"dry_run": not execute, "planned": len(moves), "moved": 0, "blocked": 0, "items": moves}

    dest_id = sc.KNOWN_IDS.get("[07] KIỂM TRA/[03] TỆP TRÙNG LẶP", "1oT10jMXJuS_Av8y_bAzPC_PVZzuj5LXK")
    caps_map = drive.stream_capabilities([m["id"] for m in moves], "canMoveItemOutOfDrive,canEdit")
    allowed, blocked = [], []
    for m in moves:
        c = caps_map.get(m["id"], {})
        if c.get("canMoveItemOutOfDrive") is False or ("canMoveItemOutOfDrive" not in c and c.get("canEdit") is False):
            blocked.append(m)
        else:
            allowed.append(m)

    if not allowed:
        return {"dry_run": False, "planned": len(moves), "moved": 0, "blocked": len(blocked), "items": []}

    results = drive.batch_move([(m["id"], dest_id) for m in allowed], workers=6)
    ok_ids = {fid for fid, ok, _ in results if ok}
    log_p = sc.data_dir() / "quarantine_log.json"
    qlog = sc.read_json(log_p, default=[]) or []
    for m in allowed:
        if m["id"] in ok_ids:
            qlog.append({
                **m,
                "from_id": (index or {}).get(m["from_path"], {}).get("id"),
                "to_id": dest_id,
                "ts": int(time.time()),
            })
    sc.write_json(log_p, qlog)

    if index and ok_ids:
        for fp in {m["from_path"] for m in allowed if m["id"] in ok_ids}:
            if fp in index and isinstance(index[fp].get("items"), list):
                index[fp]["items"] = [it for it in index[fp]["items"] if it.get("id") not in ok_ids]
        sc.save_index(index)

    return {"dry_run": False, "planned": len(moves), "moved": len(ok_ids), "blocked": len(blocked), "items": allowed}


def _clean_filename_fragment(txt: str) -> str:
    s = re.sub(r'[\\/:*?"<>|\r\n]+', " ", sc.nfc(txt or "")).strip(" .-_")
    return re.sub(r"\s{2,}", " ", s)


def _format_exif_date_vn(raw_dt: str) -> str:
    m = re.match(r"^(\d{4})[:\-](\d{2})[:\-](\d{2})", (raw_dt or "").strip())
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return ""


def _infer_context_subject(parent_path: str) -> str:
    if not parent_path:
        return ""
    last = parent_path.split("/")[-1]
    clean = re.sub(r"^\[\d{2,3}\]\s*", "", last)
    clean = re.sub(r"^\[([^\]]+)\]\s*", "", clean).strip()
    if clean and clean.upper() not in {"TỔNG QUAN", "CHƯA PHÂN LOẠI", "THEO MÔN"}:
        return sc.title_case_vn(clean)[:40]
    return ""


def _trim_title_words(txt: str, limit: int = 80) -> str:
    s = (txt or "").strip(" ,;:-_")
    if len(s) > limit:
        cut = s[:limit]
        if " " in cut:
            cut = cut.rsplit(" ", 1)[0]
        s = cut
    words = s.split()
    dangling = {"in", "of", "at", "to", "for", "with", "on", "from", "by", "and", "the", "a", "va", "cua", "cho", "tai"}
    while len(words) >= 4 and sc.strip_accents(words[-1]).lower() in dangling:
        words.pop()
    return " ".join(words).strip(" ,;:-_")


def suggest_image_v6_name(rec: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """Đề xuất tên ảnh Chuẩn V6 từ EXIF, ngày chụp, OCR heading và ngữ cảnh thư mục."""
    name = rec.get("name", "")
    mime = rec.get("mimeType", "")
    parent_path = rec.get("parent_path", "")
    if not name or sc.is_tech_exception(parent_path, name):
        return None
    base, ext = sc.split_ext(name, mime)
    ext = (rec.get("ext") or ext or "jpg").lower()

    has_supp = " - " in base
    stem_main = base.split(" - ", 1)[0].strip() if has_supp else base.strip()
    existing_supp = _clean_filename_fragment(base.split(" - ", 1)[1]) if has_supp else ""
    is_opaque = bool(OPAQUE_IMAGE_NAME_RE.match(stem_main))
    if has_supp and not is_opaque and not sc.check_file_name(name, mime, parent_path):
        return None

    meta = rec.get("metadata") or {}
    heading = _clean_filename_fragment(rec.get("ocr_heading") or "")
    exif_title = _clean_filename_fragment(meta.get("title") or "")

    if is_opaque:
        main = exif_title or heading
        if not main:
            # Dùng nhãn vai trò + ngữ cảnh nếu ảnh không có chữ/EXIF title
            role_lbl = {
                "slide_bai_giang": "Slide Bài Giảng",
                "tai_lieu_chup_ocr": "Tài Liệu Ảnh Chụp",
                "anh_man_hinh": "Ảnh Chụp Màn Hình",
                "anh_chup_camera": "Ảnh Tư Liệu",
                "do_hoa_thiet_ke": "Đồ Họa Thiết Kế",
            }.get(rec.get("role", ""), "Hình Ảnh Tư Liệu")
            main = role_lbl
    elif not has_supp:
        main = _clean_filename_fragment(stem_main.replace("_", " "))
    else:
        return None

    main_title = sc.title_case_vn(_trim_title_words(main, 82))
    supp_parts: List[str] = []
    if existing_supp:
        supp_parts.append(existing_supp)
    if meta.get("author"):
        supp_parts.append(_clean_filename_fragment(meta["author"]))
    elif meta.get("camera_model"):
        supp_parts.append(_clean_filename_fragment(meta["camera_model"]))
    if not existing_supp:
        ctx_subj = _infer_context_subject(parent_path)
        if ctx_subj and ctx_subj.lower() not in main_title.lower():
            supp_parts.append(ctx_subj)
    dt_vn = _format_exif_date_vn(meta.get("created") or meta.get("modified") or "")
    if dt_vn:
        supp_parts.append(dt_vn)
    if not supp_parts:
        supp_parts.append("Hình Ảnh")

    candidate = f"{main_title} - {', '.join(dict.fromkeys(supp_parts))}.{ext}"
    if candidate == name:
        return None
    reason = "Tên ảnh mờ/chưa chuẩn + bổ sung EXIF/OCR" if is_opaque else "Bổ sung thông tin EXIF/ngữ cảnh"
    return {
        "id": rec.get("id", ""),
        "old_name": name,
        "new_name": candidate,
        "parent_path": parent_path,
        "reason": reason,
    }


def apply_image_rename_suggestions(
    suggestions: Sequence[Dict[str, str]],
    drive: sc.Drive,
    index: Optional[dict] = None,
    execute: bool = False,
) -> Dict[str, Any]:
    batch_id = f"img_rename_{sc.now_stamp()}"
    if not execute:
        return {"batch_id": batch_id, "dry_run": True, "planned": len(suggestions), "renamed": 0, "items": list(suggestions)}

    pairs = [(s["id"], s["new_name"]) for s in suggestions if s.get("id") and s.get("new_name")]
    results = drive.batch_rename(pairs)
    ok_ids = {fid for fid, ok, _ in results if ok}
    ops = [s for s in suggestions if s.get("id") in ok_ids]

    for op in ops:
        rec = load_cached_image(op["id"])
        if rec:
            rec["name"] = op["new_name"]
            if rec.get("parent_path"):
                rec["path"] = f"{rec['parent_path']}/{op['new_name']}"
            save_cached_image(rec)

    if index and ops:
        _, id_map = sc.build_id_map(index)
        for op in ops:
            if op["id"] in id_map:
                id_map[op["id"]][1]["name"] = op["new_name"]
        sc.save_index(index)

    if ops:
        log_data = sc.read_json(sc.media_rename_log_path(), default={"batches": []}) or {"batches": []}
        log_data["batches"].append({"batch_id": batch_id, "kind": "image", "timestamp": sc.now_utc_iso(), "operations": ops})
        sc.write_json(sc.media_rename_log_path(), log_data)

    return {"batch_id": batch_id, "dry_run": False, "planned": len(suggestions), "renamed": len(ops), "items": ops}


def undo_image_rename_batch(batch_id: Optional[str], drive: sc.Drive, index: Optional[dict] = None) -> int:
    log_data = sc.read_json(sc.media_rename_log_path(), default={"batches": []}) or {"batches": []}
    batches = log_data.get("batches", [])
    target = None
    for b in reversed(batches):
        if b.get("undone"):
            continue
        if not batch_id or b.get("batch_id") == batch_id:
            target = b
            break
    if not target:
        return 0
    ops = target.get("operations", [])
    res = drive.batch_rename([(op["id"], op["old_name"]) for op in ops if op.get("id") and op.get("old_name")])
    ok_ids = {fid for fid, ok, _ in res if ok}
    if index and ok_ids:
        _, id_map = sc.build_id_map(index)
        for op in ops:
            if op["id"] in ok_ids and op["id"] in id_map:
                id_map[op["id"]][1]["name"] = op["old_name"]
        sc.save_index(index)
    target["undone"] = True
    target["undone_at"] = sc.now_utc_iso()
    sc.write_json(sc.media_rename_log_path(), log_data)
    return len(ok_ids)


# ---------------------------------------------------------------------------
# 6. TỔNG HỢP, TÌM KIẾM & BÁO CÁO
# ---------------------------------------------------------------------------

def summarize_images(records: Sequence[Dict[str, Any]], max_hamming: int = 6) -> Dict[str, Any]:
    by_ext: Dict[str, int] = collections.Counter()
    by_role: Dict[str, int] = collections.Counter()
    by_flag: Dict[str, int] = collections.Counter()
    suggestions: List[Dict[str, str]] = []
    total_bytes = 0

    for r in records:
        total_bytes += int(r.get("size") or 0)
        by_ext[r.get("ext") or "?"] += 1
        by_role[r.get("role") or "khac"] += 1
        for fl in r.get("flags") or []:
            by_flag[fl] += 1
        sug = suggest_image_v6_name(r)
        if sug:
            suggestions.append(sug)

    dups = find_visual_duplicates(records, max_hamming=max_hamming)
    return {
        "total": len(records),
        "total_bytes": total_bytes,
        "by_ext": dict(by_ext),
        "by_role": dict(by_role),
        "by_flag": dict(by_flag),
        "rename_suggestions": suggestions,
        "duplicates": dups,
        "records": list(records),
    }


def search_image_cache(
    query: Optional[str] = None,
    role: Optional[str] = None,
    flag: Optional[str] = None,
    branch: Optional[str] = None,
    limit: int = 40,
    index: Optional[dict] = None,
) -> List[Dict[str, Any]]:
    recs = iter_cached_images(branch=branch, index=index)
    q_norm = sc.strip_accents(sc.nfc(query or "")).lower().strip()
    hits: List[Dict[str, Any]] = []
    for r in recs:
        if role and r.get("role") != role:
            continue
        if flag and flag not in (r.get("flags") or []):
            continue
        if q_norm:
            hay = " ".join([
                r.get("name", ""),
                r.get("ocr_text", ""),
                str((r.get("metadata") or {}).get("title", "")),
                str((r.get("metadata") or {}).get("camera_model", "")),
            ])
            if q_norm not in sc.strip_accents(sc.nfc(hay)).lower():
                continue
        hits.append(r)
        if limit > 0 and len(hits) >= limit:
            break
    return hits


def write_image_reports(summary: Dict[str, Any], branch: Optional[str] = None) -> Tuple[Path, Path]:
    today = sc.today_vn()
    md_p = sc.reports_dir() / f"Báo Cáo Phân Tích Hình Ảnh - Storage, {today}.md"
    csv_p = sc.reports_dir() / f"Báo Cáo Phân Tích Hình Ảnh - Storage, {today}.csv"

    dups = summary["duplicates"]
    sugs = summary["rename_suggestions"]
    sec_no = 1
    lines = [
        f"# BÁO CÁO PHÂN TÍCH HÌNH ẢNH & CHẤT LƯỢNG THỊ GIÁC — [A] STORAGE ({today})",
        "",
        f"- **Phạm vi nhánh**: `{sc.normalize_branch(branch) or sc.ROOT_NAME}`",
        f"- **Tổng số tệp ảnh phân tích**: **{sc.fmt_int(summary['total'])}** ({sc.human_size(summary['total_bytes'])})",
        f"- **Nhóm trùng SHA-256**: **{len(dups['exact_groups'])}** | **Nhóm trùng trực quan (dHash/pHash)**: **{len(dups['visual_groups'])}**",
        f"- **Gợi ý chuẩn hóa tên V6**: **{len(sugs)}**",
        "",
        f"## {sec_no}. Phân bố Theo Định Dạng & Vai Trò",
        "",
        sc.md_table(["Định dạng", "Số tệp"], sorted(summary["by_ext"].items(), key=lambda x: -x[1]), ["l", "r"]),
        "",
        sc.md_table(["Vai trò hình ảnh", "Số tệp"], sorted(summary["by_role"].items(), key=lambda x: -x[1]), ["l", "r"]),
        "",
    ]
    sec_no += 1
    if summary["by_flag"]:
        lines += [
            f"## {sec_no}. Thống kê Cờ Chất Lượng & Quyền Riêng Tư",
            "",
            sc.md_table(["Cờ cảnh báo", "Số tệp"], sorted(summary["by_flag"].items(), key=lambda x: -x[1]), ["l", "r"]),
            "",
        ]
        sec_no += 1
    if dups["pairs"]:
        lines += [
            f"## {sec_no}. Cặp Ảnh Gần Trùng Trực Quan (dHash / pHash)",
            "",
            sc.md_table(
                ["Tương đồng", "dHash/pHash", "Ảnh giữ", "Ảnh dư"],
                [
                    [f"{p['similarity_pct']}%", f"{p['dhash_dist']}/{p['phash_dist']}", p["a"]["name"], p["b"]["name"]]
                    for p in dups["pairs"][:25]
                ],
                ["r", "c", "l", "l"],
            ),
            "",
        ]
        sec_no += 1
    if sugs:
        lines += [
            f"## {sec_no}. Đề Xuất Chuẩn Hóa Tên Chuẩn V6 (tối đa 30 mục)",
            "",
            sc.md_table(["ID", "Tên hiện tại", "Tên đề xuất", "Lý do"], [[s["id"], s["old_name"], s["new_name"], s["reason"]] for s in sugs[:30]]),
            "",
        ]
        sec_no += 1

    rows_sample = []
    for r in summary["records"][:60]:
        st = r.get("stats") or {}
        q = r.get("quality") or {}
        cols = ", ".join(c["hex"] for c in (q.get("dominant_colors") or [])[:2])
        rows_sample.append([
            r.get("name", ""),
            f"{st.get('width', 0)}x{st.get('height', 0)}",
            st.get("aspect_label", ""),
            q.get("sharpness_laplacian", ""),
            r.get("role", ""),
            cols,
            ", ".join(r.get("flags") or []),
        ])
    if rows_sample:
        lines += [
            f"## {sec_no}. Chi Tiết Mẫu Hình Ảnh (tối đa 60 tệp)",
            "",
            sc.md_table(["Tên tệp", "Kích thước", "Tỷ lệ", "Độ nét", "Vai trò", "Màu chủ đạo", "Cờ"], rows_sample),
            "",
        ]
    md_p.write_text("\n".join(lines), encoding="utf-8")

    csv_rows = []
    for r in summary["records"]:
        st = r.get("stats") or {}
        q = r.get("quality") or {}
        m = r.get("metadata") or {}
        h = r.get("hashes") or {}
        csv_rows.append([
            r.get("id", ""), r.get("name", ""), r.get("path", ""), r.get("ext", ""), r.get("status", ""),
            r.get("size", 0), st.get("width", 0), st.get("height", 0), st.get("megapixels", 0),
            st.get("aspect_label", ""), q.get("sharpness_laplacian", ""), q.get("brightness_mean", ""),
            q.get("contrast_std", ""), ";".join(c["hex"] for c in (q.get("dominant_colors") or [])),
            m.get("camera_model", ""), "Có" if m.get("has_gps") else "", r.get("role", ""),
            h.get("dhash", ""), h.get("phash", ""), r.get("ocr_heading", ""),
            ", ".join(r.get("flags") or []),
        ])
    sc.write_csv(
        csv_p,
        [
            "ID", "Tên tệp", "Đường dẫn", "Đuôi", "Trạng thái", "Dung lượng (B)",
            "Rộng", "Cao", "MP", "Tỷ lệ", "Độ nét Laplacian", "Độ sáng", "Tương phản",
            "Màu chủ đạo", "Máy ảnh", "GPS EXIF", "Vai trò", "dHash", "pHash", "Tiêu đề OCR", "Cờ",
        ],
        csv_rows,
    )
    return md_p, csv_p


def main() -> None:
    ap = argparse.ArgumentParser(description="Phân tích hình ảnh, chất lượng thị giác, OCR & trùng lặp trực quan (v3.3).")
    ap.add_argument("lenh", nargs="?", default="phan-tich", choices=["phan-tich", "doc", "trung-anh", "goi-y-ten", "hoan-tac-ten", "tim-anh"])
    ap.add_argument("muc_tieu", nargs="?", help="ID Drive / URL hoặc đường dẫn ảnh cục bộ cho lệnh `doc`.")
    ap.add_argument("--nhanh", help="Giới hạn phạm vi nhánh.")
    ap.add_argument("--tu-dong-doc", action="store_true", help="Tải & phân tích các ảnh chưa có trong media_cache.")
    ap.add_argument("--ocr", action="store_true", help="Bật nhận dạng chữ OCR trên ảnh (tesseract).")
    ap.add_argument("--max-mb", type=float, default=25.0, help="Giới hạn dung lượng tối đa mỗi ảnh (mặc định 25 MB).")
    ap.add_argument("--gioi-han", type=int, default=30, help="Số ảnh tối đa xử lý mỗi lô (mặc định 30).")
    ap.add_argument("--luong", type=int, default=4, help="Số luồng tải/phân tích song song.")
    ap.add_argument("--nguong-hamming", type=int, default=6, help="Ngưỡng khoảng cách Hamming cho trùng trực quan (mặc định 6).")
    ap.add_argument("--gom-trung", action="store_true", help="Lập kế hoạch cách ly ảnh trùng trực quan vào [07] KIỂM TRA.")
    ap.add_argument("--tu-khoa", help="Từ khóa tìm kiếm (cho lệnh `tim-anh`).")
    ap.add_argument("--vai-tro", help="Lọc theo vai trò ảnh (cho lệnh `tim-anh`).")
    ap.add_argument("--co", help="Lọc theo cờ chất lượng (`anh_mo`, `co_gps_exif`, ...).")
    ap.add_argument("--ma-lo", help="Mã lô cần hoàn tác.")
    ap.add_argument("--thuc-thi", action="store_true", help="Thực sự ghi/đổi tên/di chuyển trên Google Drive.")
    ap.add_argument("--dong-y", action="store_true", help="Không hỏi xác nhận khi --thuc-thi.")
    ap.add_argument("--tai-len", action="store_true", help="Tải báo cáo lên [00] TỔNG QUAN/[02] NHẬT KÍ.")
    args = ap.parse_args()

    if args.lenh == "doc":
        if not args.muc_tieu:
            raise SystemExit("Truyền đường dẫn ảnh cục bộ hoặc ID/URL Google Drive.")
        p_local = Path(args.muc_tieu).expanduser()
        if p_local.exists():
            rec = analyze_local_image(p_local, enable_ocr=args.ocr)
        else:
            fid = sc.extract_drive_id(args.muc_tieu)
            drive = sc.create_drive()
            index = sc.load_index(required=False)
            _, id_map = sc.build_id_map(index) if index else ({}, {})
            if fid in id_map:
                pp, item = id_map[fid]
            else:
                info = drive.info(fid)
                pp, item = "", info
            rec = analyze_drive_image(item, pp, drive, force_refresh=True, max_mb=args.max_mb, enable_ocr=args.ocr)
        sc.log(f"🖼️  {rec.get('name', args.muc_tieu)} | trạng thái={rec.get('status')} | vai trò={rec.get('role')}")
        sc.log(f"   • Thông số: {rec.get('stats')} | Chất lượng: {rec.get('quality')}")
        sc.log(f"   • Hash    : {rec.get('hashes')} | Cờ: {rec.get('flags')}")
        if rec.get("ocr_text"):
            sc.log(f"   • OCR     : {rec['ocr_text'][:300]}")
        return

    index = sc.load_index(required=False)
    if args.lenh == "hoan-tac-ten":
        n = undo_image_rename_batch(args.ma_lo, sc.create_drive(), index=index)
        sc.log(f"↩️  Đã hoàn tác {n} mục đổi tên ảnh.")
        return

    if args.lenh == "tim-anh":
        hits = search_image_cache(args.tu_khoa, args.vai_tro, args.co, args.nhanh, args.gioi_han, index=index)
        sc.log(f"🔎 Tìm thấy {len(hits)} ảnh phù hợp:")
        for h in hits:
            st = h.get("stats") or {}
            sc.log(f" • {h.get('path', h.get('name'))} ({st.get('width', 0)}x{st.get('height', 0)}, {h.get('role')}) [{', '.join(h.get('flags') or [])}]")
        return

    if args.tu_dong_doc and index:
        drive = sc.create_drive()
        batch_analyze_images(index, drive, branch=args.nhanh, max_mb=args.max_mb, limit=args.gioi_han, workers=args.luong, enable_ocr=args.ocr)

    recs = iter_cached_images(branch=args.nhanh, index=index)
    summary = summarize_images(recs, max_hamming=args.nguong_hamming)

    if args.lenh == "trung-anh":
        dups = summary["duplicates"]
        sc.log(f"🖼️  Trùng ảnh: {len(dups['exact_groups'])} nhóm SHA-256, {len(dups['visual_groups'])} nhóm trực quan (Hamming ≤ {args.nguong_hamming}).")
        for g in dups["visual_groups"][:15]:
            sc.log(f" • Giữ: {g['keep']['name']} ({g['keep']['stats'].get('width')}x{g['keep']['stats'].get('height')})")
            for ex in g["extra"]:
                sc.log(f"    ↳ Dư: {ex['name']} ({ex['stats'].get('width')}x{ex['stats'].get('height')}, {ex['id']})")
        if args.gom_trung:
            preview = quarantine_visual_duplicates(dups, sc.create_drive(), index=index, execute=False)
            do_exec = bool(args.thuc_thi and preview["planned"] > 0 and sc.confirm(f"Cách ly {preview['planned']} ảnh trùng vào [07] KIỂM TRA?", assume_yes=args.dong_y))
            qres = quarantine_visual_duplicates(dups, sc.create_drive(), index=index, execute=do_exec) if do_exec else preview
            sc.log(f"📦 Cách ly ảnh trùng: dự kiến={qres['planned']}, đã chuyển={qres['moved']}, dry_run={qres['dry_run']}")
        return

    if args.lenh == "goi-y-ten":
        sugs = summary["rename_suggestions"]
        sc.log(f"🏷️  Gợi ý chuẩn hóa tên cho {len(sugs)} ảnh:")
        for s in sugs[:30]:
            sc.log(f" • {s['old_name']}  →  {s['new_name']} ({s['id']})")
        if args.thuc_thi and sugs and sc.confirm(f"Đổi tên {len(sugs)} ảnh trên Drive?", assume_yes=args.dong_y):
            res = apply_image_rename_suggestions(sugs, sc.create_drive(), index=index, execute=True)
            sc.log(f"✅ Đã đổi tên {res['renamed']}/{res['planned']} ảnh (lô {res['batch_id']}).")
        return

    md_p, csv_p = write_image_reports(summary, branch=args.nhanh)
    sc.log(f"🖼️  Đã phân tích {summary['total']} ảnh | cờ={summary['by_flag']} | trùng trực quan={len(summary['duplicates']['visual_groups'])}")
    sc.log(f"📝 Báo cáo MD : {md_p}")
    sc.log(f"📝 Báo cáo CSV: {csv_p}")
    if args.tai_len:
        drive = sc.create_drive()
        sc.publish_file(drive, md_p, sc.nhat_ki_id())
        sc.publish_file(drive, csv_p, sc.nhat_ki_id())
        sc.log("☁️  Đã tải báo cáo phân tích hình ảnh lên [02] NHẬT KÍ.")


if __name__ == "__main__":
    main()
