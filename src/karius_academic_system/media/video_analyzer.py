#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PHÂN TÍCH VIDEO, LUỒNG DỮ LIỆU, KEYFRAME OCR & KHÓA HỌC — [A] STORAGE (v3.3)
=============================================================================
Chương trình `[18] PHÂN TÍCH VIDEO/video_analyzer.py` quản trị và kiểm toán kho video
(`.mp4`, `.ts`, `.mov`, `.mkv`, `.avi`, `.webm`):

1. `phan-tich`          : Tải & phân tích sâu theo lô giới hạn dung lượng (`--max-mb 250`, xóa tạm
                          ngay trong `finally`) hoặc tổng hợp từ `media_cache/video/` + kiểm toán
                          chỉ mục `storage_index.json`; hỗ trợ `--ocr` slide và `--contact-sheet`.
2. `doc`                : Đọc & kiểm tra tức thì 1 tệp video (cục bộ hoặc Drive ID/URL).
3. `trung-video`        : Phát hiện video trùng lặp khác độ phân giải/bitrate/định dạng qua đa chữ ký
                          `keyframe pHash` + đối chiếu thời lượng; tùy chọn cách ly bản kém hơn (`--gom-trung`).
4. `kiem-tra-khoa-hoc`  : Kiểm toán siêu tốc trực tiếp trên `storage_index.json` (không tải tệp lớn):
                          thống kê theo khóa học, tệp `.ts` (`can_remux_mp4`), bài giảng khuyết số
                          (`thieu_bai_trong_chuoi`) và tên dính liền không dấu (`ten_dinh_lien_khong_dau`).
5. `goi-y-ten`          : Đề xuất chuẩn hóa tên Chuẩn V6 từ metadata/OCR slide và ngữ cảnh khóa học.
6. `hoan-tac-ten`       : Hoàn tác lô đổi tên video gần nhất từ `media_rename_log.json`.
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import json
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from karius_academic_system import core as sc
from karius_academic_system.media import audio_analyzer as aud_mod
from karius_academic_system.media import image_analyzer as img_mod

VIDEO_EXTENSIONS: Set[str] = {
    "mp4", "ts", "mov", "mkv", "avi", "webm", "flv", "wmv", "m4v", "mpg", "mpeg", "3gp",
}

MODERN_VIDEO_CODECS: Set[str] = {"h264", "hevc", "h265", "vp9", "av1"}

OPAQUE_VIDEO_NAME_RE = re.compile(
    r"^(?:vid|video|mov|rec|recording|capture|clip|screen|bandicam|obs|cam|c|img|untitled|\d{6,})(?:[ _-]?\d+)*$",
    re.I,
)

VIDEO_SEQ_PATTERNS = [
    re.compile(r"(?:bài|bai|buổi|buoi|phần|phan|chương|chuong|tập|tap|lesson|section|part|unit|day|module)\s*0*(\d{1,4})\b", re.I),
    re.compile(r"^0*(\d{1,4})(?:\s*[.\-_]|\s+)"),
    re.compile(r"^0*(\d{1,4})$"),
]

_ENGLISH_LONG_SUFFIX_RE = re.compile(
    r"(?:tion|sion|ment|ness|able|ible|ally|ence|ance|logy|graphy|ization|isation|"
    r"ship|hood|ward|less|ous|ful|ary|ory|ery|ity|ics|ant|ent|ure|age|ate|ive|ing|ers|est)$",
    re.I,
)

_GLUED_VN_MARKERS: Tuple[str, ...] = (
    "vacac", "cacthuoc", "huongdan", "thuchanh", "phienban", "duongthang",
    "cungtron", "nguoimoi", "soluoc", "khoahoc", "hieuchinh", "thietke",
    "nhungcau", "taolayer", "cualayer", "dtutruoc", "trongautocad",
    "gioithieu", "banve", "kichban", "chinhsua", "hinhanh",
)


# ---------------------------------------------------------------------------
# 1. PHÂN TÍCH LUỒNG KỸ THUẬT & NHẬN DIỆN LỖI TÊN KHÓA HỌC
# ---------------------------------------------------------------------------

def has_glued_unaccented_name(name: str) -> bool:
    """Phát hiện tên tệp có cụm từ tiếng Việt dính liền không dấu (như khóa AutoCAD)."""
    base, _ = sc.split_ext(name)
    main = base.split(" - ")[0]
    tokens = re.findall(r"[A-Za-z]+", main)
    for tok in tokens:
        low = tok.lower()
        if any(mk in low for mk in _GLUED_VN_MARKERS) and len(low) >= 10:
            return True
        if len(low) >= 14 and not _ENGLISH_LONG_SUFFIX_RE.search(low):
            return True
    return False


def _aspect_label(w: int, h: int) -> str:
    if w <= 0 or h <= 0:
        return "khac"
    ratio = w / float(h)
    presets = [
        (16 / 9, "16:9"),
        (9 / 16, "9:16"),
        (4 / 3, "4:3"),
        (3 / 4, "3:4"),
        (1.0, "1:1"),
    ]
    best = "khac"
    best_diff = 0.08
    for target, lbl in presets:
        diff = abs(ratio - target) / target
        if diff < best_diff:
            best_diff = diff
            best = lbl
    return best


def _resolution_tier(w: int, h: int) -> str:
    if w <= 0 or h <= 0:
        return "khong_ro"
    short = min(w, h)
    long_side = max(w, h)
    if short >= 2160 or long_side >= 3800:
        return "4K"
    if short >= 1080 or long_side >= 1900:
        return "1080p"
    if short >= 720 or long_side >= 1260:
        return "720p"
    if short >= 480:
        return "480p"
    return "SD_Thap"


def _parse_fps(raw: str) -> float:
    s = (raw or "").strip()
    if not s or s == "0/0":
        return 0.0
    if "/" in s:
        a, b = s.split("/", 1)
        try:
            num, den = float(a), float(b)
            return round(num / den, 2) if den > 0 else 0.0
        except ValueError:
            return 0.0
    try:
        return round(float(s), 2)
    except ValueError:
        return 0.0


def inspect_video_streams(path: Path) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Đọc toàn bộ thông số luồng video/audio/subtitles và tags bằng `ffprobe`."""
    meta: Dict[str, Any] = {}
    stats: Dict[str, Any] = {
        "duration_sec": 0.0,
        "bitrate_kbps": 0,
        "width": 0,
        "height": 0,
        "resolution_tier": "khong_ro",
        "fps": 0.0,
        "aspect_label": "khac",
        "video_codec": "",
        "audio_codec": "",
        "has_audio": False,
        "audio_sample_rate_hz": 0,
        "audio_channels": 0,
        "subtitle_count": 0,
    }
    if not shutil.which("ffprobe"):
        return meta, stats

    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", str(path)],
            capture_output=True,
            text=True,
            timeout=35,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return meta, stats
        info = json.loads(proc.stdout)
    except Exception:
        return meta, stats

    fmt = info.get("format") or {}
    if fmt.get("format_name"):
        meta["container"] = str(fmt["format_name"])
    if fmt.get("duration"):
        try:
            stats["duration_sec"] = round(float(fmt["duration"]), 2)
        except ValueError:
            pass
    if fmt.get("bit_rate") and str(fmt["bit_rate"]).isdigit():
        stats["bitrate_kbps"] = round(int(fmt["bit_rate"]) / 1000)

    raw_tags = fmt.get("tags") or {}
    for k, v in raw_tags.items():
        kl = k.lower()
        val = sc.nfc(str(v).strip())
        if not val:
            continue
        if kl == "title":
            meta["title"] = val[:240]
        elif kl in {"artist", "author"}:
            meta["author"] = val[:240]
        elif kl in {"creation_time", "date"}:
            meta["created"] = val[:64]
        elif kl == "comment":
            meta["comment"] = val[:240]

    for st in info.get("streams") or []:
        ctype = st.get("codec_type", "")
        disp = st.get("disposition") or {}
        if ctype == "video" and disp.get("attached_pic") != 1 and not stats["video_codec"]:
            w = int(st.get("width") or 0)
            h = int(st.get("height") or 0)
            stats["video_codec"] = str(st.get("codec_name") or "").lower()
            stats["width"] = w
            stats["height"] = h
            stats["resolution_tier"] = _resolution_tier(w, h)
            stats["aspect_label"] = _aspect_label(w, h)
            stats["fps"] = _parse_fps(str(st.get("avg_frame_rate") or st.get("r_frame_rate") or ""))
            if not stats["duration_sec"] and st.get("duration"):
                try:
                    stats["duration_sec"] = round(float(st["duration"]), 2)
                except ValueError:
                    pass
        elif ctype == "audio" and not stats["has_audio"]:
            stats["has_audio"] = True
            stats["audio_codec"] = str(st.get("codec_name") or "").lower()
            if st.get("sample_rate") and str(st["sample_rate"]).isdigit():
                stats["audio_sample_rate_hz"] = int(st["sample_rate"])
            if st.get("channels"):
                stats["audio_channels"] = int(st["channels"])
        elif ctype == "subtitle":
            stats["subtitle_count"] += 1

    return meta, stats


# ---------------------------------------------------------------------------
# 2. RÚT KEYFRAMES, PHASH ĐA KHUNG HÌNH, KIỂM TRA KHUNG HÌNH ĐỨNG, OCR & CONTACT SHEET
# ---------------------------------------------------------------------------

def _fmt_ts(sec: float) -> str:
    s = max(0, int(round(sec)))
    h, rem = divmod(s, 3600)
    m, ss = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{ss:02d}" if h else f"{m:02d}:{ss:02d}"


def _load_unicode_font(size: int = 16, bold: bool = False):
    from PIL import ImageFont  # type: ignore

    cands = (
        [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
        if bold
        else [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
    )
    for fp in cands:
        if Path(fp).exists():
            try:
                return ImageFont.truetype(fp, size), True
            except Exception:
                pass
    return ImageFont.load_default(), False


def _draw_text_safe(text: str, has_ttf: bool) -> str:
    clean = sc.nfc(text or "")
    if has_ttf:
        return clean
    return sc.strip_accents(clean).encode("latin-1", "ignore").decode("latin-1")


def _build_contact_sheet(
    pil_frames: List[Tuple[float, Any]],
    out_path: Path,
    header_title: str,
) -> Optional[Path]:
    """Ghép tối đa 6 khung hình đại diện thành ảnh lưới 3x2 kèm dấu thời gian."""
    if not pil_frames:
        return None
    from PIL import Image, ImageDraw  # type: ignore

    cols = 3
    tile_w, tile_h = 400, 225
    pad = 14
    header_h = 48
    rows = max(1, (len(pil_frames) + cols - 1) // cols)
    canvas_w = cols * tile_w + (cols + 1) * pad
    canvas_h = header_h + rows * (tile_h + 26) + pad
    canvas = Image.new("RGB", (canvas_w, canvas_h), (24, 26, 32))
    draw = ImageDraw.Draw(canvas)
    f_hdr, hdr_ttf = _load_unicode_font(16, bold=True)
    f_lbl, lbl_ttf = _load_unicode_font(14, bold=False)
    draw.text((pad, 14), _draw_text_safe(header_title, hdr_ttf)[:100], fill=(240, 244, 248), font=f_hdr)

    res_filter = getattr(Image, "Resampling", None)
    lanczos = res_filter.LANCZOS if res_filter is not None else Image.LANCZOS

    for idx, (ts, im) in enumerate(pil_frames[: cols * 2]):
        r, c = divmod(idx, cols)
        x0 = pad + c * (tile_w + pad)
        y0 = header_h + r * (tile_h + 26)
        thumb = im.convert("RGB")
        thumb.thumbnail((tile_w, tile_h), lanczos)
        off_x = x0 + (tile_w - thumb.width) // 2
        off_y = y0 + (tile_h - thumb.height) // 2
        canvas.paste(thumb, (off_x, off_y))
        draw.rectangle([x0, y0, x0 + tile_w, y0 + tile_h], outline=(70, 78, 92), width=1)
        draw.text((x0 + 4, y0 + tile_h + 4), _draw_text_safe(f"#{idx + 1}  {_fmt_ts(ts)}", lbl_ttf), fill=(185, 210, 255), font=f_lbl)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, format="JPEG", quality=86)
    return out_path


def extract_video_keyframes(
    path: Path,
    duration_sec: float,
    num_frames: int = 5,
    enable_ocr: bool = False,
    contact_sheet_out: Optional[Path] = None,
    header_title: str = "",
) -> Dict[str, Any]:
    """
    Rút tối đa 5 khung hình tiêu biểu tại ~8%, 28%, 50%, 72%, 90% thời lượng để:
    - Xác minh khả năng giải mã thực tế ở đầu/giữa/cuối tệp
    - Tính `dHash` & `pHash` từng khung hình (chia sẻ trực tiếp từ `[16] image_analyzer`)
    - Phát hiện video tĩnh (`khung_hinh_dung`)
    - Tùy chọn OCR slide (`--ocr`) và tạo Contact Sheet 3x2 (`--contact-sheet`)
    """
    import numpy as np  # type: ignore
    from PIL import Image  # type: ignore

    out: Dict[str, Any] = {
        "timestamps": [],
        "dhashes": [],
        "phashes": [],
        "decode_ok": 0,
        "decode_failed": 0,
        "is_frozen": False,
        "ocr_text": "",
        "ocr_heading": "",
        "contact_sheet_path": "",
    }
    if not shutil.which("ffmpeg") or img_mod is None:
        return out

    fracs = [0.08, 0.28, 0.50, 0.72, 0.90][: max(1, num_frames)]
    raw_ts: List[float] = []
    if duration_sec > 1.5:
        max_seek = max(0.0, duration_sec - 0.35)
        for fr in fracs:
            t = round(min(max_seek, max(0.0, duration_sec * fr)), 2)
            if not raw_ts or abs(t - raw_ts[-1]) >= 0.25:
                raw_ts.append(t)
    else:
        raw_ts = [0.0]

    tmp_dir = Path(tempfile.mkdtemp(prefix="vid_kf_"))
    pil_frames: List[Tuple[float, Any]] = []
    tiny_arrays: List[Any] = []
    try:
        for i, ts in enumerate(raw_ts):
            kf_jpg = tmp_dir / f"kf_{i}.jpg"
            proc = subprocess.run(
                ["ffmpeg", "-v", "error", "-ss", f"{ts:.2f}", "-i", str(path), "-frames:v", "1", "-q:v", "3", "-y", str(kf_jpg)],
                capture_output=True,
                timeout=35,
            )
            if proc.returncode == 0 and kf_jpg.exists() and kf_jpg.stat().st_size > 200:
                try:
                    with Image.open(kf_jpg) as im_raw:
                        im_rgb = im_raw.convert("RGB")
                    dh, ph = img_mod.compute_image_hashes_from_pil(im_rgb)
                    out["timestamps"].append(ts)
                    out["dhashes"].append(dh)
                    out["phashes"].append(ph)
                    out["decode_ok"] += 1
                    pil_frames.append((ts, im_rgb))
                    small = np.asarray(im_rgb.convert("L").resize((32, 32)), dtype=np.float32)
                    tiny_arrays.append(small)
                except Exception:
                    out["decode_failed"] += 1
            else:
                out["decode_failed"] += 1

        # Dự phòng nếu fast-seek thất bại hoàn toàn (một số tệp .ts không có bảng seek index chuẩn)
        if out["decode_ok"] == 0:
            fb_jpg = tmp_dir / "kf_fb.jpg"
            proc_fb = subprocess.run(
                ["ffmpeg", "-v", "error", "-i", str(path), "-frames:v", "1", "-q:v", "3", "-y", str(fb_jpg)],
                capture_output=True,
                timeout=35,
            )
            if proc_fb.returncode == 0 and fb_jpg.exists() and fb_jpg.stat().st_size > 200:
                with Image.open(fb_jpg) as im_raw:
                    im_rgb = im_raw.convert("RGB")
                dh, ph = img_mod.compute_image_hashes_from_pil(im_rgb)
                out["timestamps"].append(0.0)
                out["dhashes"].append(dh)
                out["phashes"].append(ph)
                out["decode_ok"] = 1
                out["decode_failed"] = 0
                pil_frames.append((0.0, im_rgb))

        # Phát hiện video có khung hình đứng yên hoàn toàn (cần >= 3 khung hình giống hệt nhau)
        if len(out["phashes"]) >= 3 and len(tiny_arrays) >= 3:
            ph0 = out["phashes"][0]
            arr0 = tiny_arrays[0]
            max_ph_diff = max(img_mod.hamming_distance64(ph0, p) for p in out["phashes"][1:])
            max_mad = max(float(np.mean(np.abs(arr0 - a))) for a in tiny_arrays[1:])
            if max_ph_diff <= 2 and max_mad < 4.0:
                out["is_frozen"] = True

        # OCR slide từ khung hình đầu/giữa nếu được yêu cầu
        if enable_ocr and pil_frames:
            ocr_idxs = [0]
            if len(pil_frames) >= 2:
                ocr_idxs.append(len(pil_frames) // 2)
            chunks: List[str] = []
            seen_lines: Set[str] = set()
            for idx in ocr_idxs:
                txt, _ = img_mod.run_image_ocr_from_pil(pil_frames[idx][1])
                if txt:
                    for ln in txt.splitlines():
                        k = sc.strip_accents(ln).lower().strip()
                        if k and k not in seen_lines:
                            seen_lines.add(k)
                            chunks.append(ln)
            merged_ocr = "\n".join(chunks)[:20_000]
            out["ocr_text"] = merged_ocr
            out["ocr_heading"] = img_mod._extract_first_heading(merged_ocr)

        if contact_sheet_out and pil_frames:
            saved_cs = _build_contact_sheet(pil_frames, contact_sheet_out, header_title or path.name)
            if saved_cs:
                out["contact_sheet_path"] = str(saved_cs)
    finally:
        for _, im in pil_frames:
            try:
                im.close()
            except Exception:
                pass
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return out


def classify_video_role(name: str, parent_path: str) -> str:
    low = f"{parent_path}/{name}".lower()
    if any(k in low for k in ("khoá học", "khoa hoc", "autocad", "canva", "capcut", "đồ hoạ", "do hoa", "photoshop")):
        return "khoa_hoc_thuc_hanh"
    if any(k in low for k in ("ielts", "hsk", "phổ thông", "pho thong", "ngữ văn", "ngu van", "toán", "ussh", "flf", "đại học")):
        return "bai_giang_luyen_thi"
    stem, _ = sc.split_ext(name)
    if OPAQUE_VIDEO_NAME_RE.match(stem.strip()) or any(k in low for k in ("screen", "obs", "bandicam")):
        return "ban_ghi_man_hinh"
    if "review" in low or "giới thiệu" in low:
        return "video_review_tai_lieu"
    return "video_khac"


# ---------------------------------------------------------------------------
# 3. ĐỌC & PHÂN TÍCH MỘT TỆP VIDEO CỤC BỘ / GOOGLE DRIVE + BỘ ĐỆM
# ---------------------------------------------------------------------------

def analyze_local_video(
    path: Path,
    name: Optional[str] = None,
    parent_path: str = "",
    enable_ocr: bool = False,
    make_contact_sheet: bool = False,
    file_id: str = "",
) -> Dict[str, Any]:
    path = Path(path)
    display_name = name or path.name
    _, ext = sc.split_ext(display_name)
    ext = ext.lower()

    if not path.exists():
        return {"status": "video_hong", "ext": ext, "flags": ["video_hong"], "metadata": {}, "stats": {}, "audio_signal": {}, "keyframes": {}}

    size = path.stat().st_size
    sha256 = sc.sha256_file(path)
    if size == 0:
        return {"status": "tep_rong", "ext": ext, "sha256": sha256, "flags": ["tep_rong"], "metadata": {}, "stats": {}, "audio_signal": {}, "keyframes": {}}

    meta, stats = inspect_video_streams(path)
    dur = float(stats.get("duration_sec") or 0.0)
    w, h = int(stats.get("width") or 0), int(stats.get("height") or 0)

    flags: List[str] = []
    if ext == "ts":
        flags.append("can_remux_mp4")
    if has_glued_unaccented_name(display_name):
        flags.append("ten_dinh_lien_khong_dau")

    if dur <= 0.0 or w <= 0 or h <= 0 or not stats.get("video_codec"):
        return {
            "status": "video_hong", "ext": ext, "sha256": sha256,
            "metadata": meta, "stats": stats, "audio_signal": {},
            "keyframes": {"timestamps": [], "dhashes": [], "phashes": [], "decode_ok": 0, "decode_failed": 0},
            "role": classify_video_role(display_name, parent_path),
            "ocr_heading": "", "ocr_text": "",
            "flags": list(dict.fromkeys(flags + ["video_hong"])),
        }

    cs_out: Optional[Path] = None
    if make_contact_sheet:
        safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", file_id or sc.split_ext(display_name)[0])[:80]
        cs_out = sc.reports_dir() / "contact_sheets" / f"{safe_id}.jpg"

    hdr = f"{display_name} ({w}x{h}, {_fmt_ts(dur)})"
    kf_res = extract_video_keyframes(
        path, dur, num_frames=5, enable_ocr=enable_ocr, contact_sheet_out=cs_out, header_title=hdr,
    )

    if kf_res["decode_ok"] == 0:
        flags.append("video_hong")
    elif kf_res["decode_failed"] > 0:
        flags.append("video_loi_giai_ma")
    if kf_res["is_frozen"]:
        flags.append("khung_hinh_dung")
    if min(w, h) < 480:
        flags.append("do_phan_giai_thap")
    if enable_ocr and kf_res.get("ocr_text"):
        flags.append("da_ocr")

    audio_sig: Dict[str, Any] = {}
    if not stats.get("has_audio"):
        flags.append("khong_co_am_thanh")
    elif aud_mod is not None:
        audio_sig = aud_mod.analyze_audio_signal(path, dur)
        max_db = audio_sig.get("max_volume_db")
        lufs = audio_sig.get("integrated_lufs")
        sil_pct = float(audio_sig.get("silence_ratio_pct") or 0.0)
        if max_db is not None and max_db >= -0.1:
            flags.append("bi_re_tieng")
        if sil_pct >= 95.0 or (max_db is not None and max_db <= -65.0):
            flags.append("am_thanh_rong_im_lang")
        elif lufs is not None and lufs < -28.0:
            flags.append("am_luong_nho")

    role = classify_video_role(display_name, parent_path)
    status = "video_hong" if "video_hong" in flags else "ok"
    return {
        "status": status,
        "ext": ext,
        "sha256": sha256,
        "metadata": meta,
        "stats": stats,
        "audio_signal": audio_sig,
        "keyframes": {
            "timestamps": kf_res["timestamps"],
            "dhashes": kf_res["dhashes"],
            "phashes": kf_res["phashes"],
            "decode_ok": kf_res["decode_ok"],
            "decode_failed": kf_res["decode_failed"],
            "is_frozen": kf_res["is_frozen"],
            "contact_sheet_path": kf_res["contact_sheet_path"],
        },
        "role": role,
        "ocr_heading": kf_res.get("ocr_heading", ""),
        "ocr_text": kf_res.get("ocr_text", ""),
        "flags": list(dict.fromkeys(flags)),
    }


def cache_record_path(file_id: str) -> Path:
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", file_id)
    return sc.media_cache_dir("video") / f"{safe_id}.json"


def load_cached_video(file_id: str, modified_time: Optional[str] = None) -> Optional[Dict[str, Any]]:
    rec = sc.read_json(cache_record_path(file_id))
    if not isinstance(rec, dict):
        return None
    if modified_time and rec.get("modifiedTime") and rec.get("modifiedTime") != modified_time:
        return None
    return rec


def save_cached_video(record: Dict[str, Any]) -> Dict[str, Any]:
    sc.write_json(cache_record_path(record["id"]), record)
    return record


def iter_cached_videos(branch: Optional[str] = None, index: Optional[dict] = None) -> List[Dict[str, Any]]:
    norm_branch = sc.normalize_branch(branch)
    prefix = norm_branch.rstrip("/") + "/" if norm_branch else ""
    id_to_entry: Dict[str, Tuple[str, dict]] = {}
    if index:
        _, id_to_entry = sc.build_id_map(index)

    out: List[Dict[str, Any]] = []
    for p in sorted(sc.media_cache_dir("video").glob("*.json")):
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


def analyze_drive_video(
    item: dict,
    parent_path: str,
    drive: sc.Drive,
    force_refresh: bool = False,
    max_mb: float = 250.0,
    enable_ocr: bool = False,
    make_contact_sheet: bool = False,
) -> Dict[str, Any]:
    fid = item["id"]
    name = item.get("name", fid)
    mime = item.get("mimeType", "")
    size = int(item.get("size") or 0)
    mod = item.get("modifiedTime", "")
    full_path = f"{parent_path}/{name}" if parent_path else name
    _, ext = sc.split_ext(name, mime)
    ext = ext.lower()

    if not force_refresh:
        cached = load_cached_video(fid, modified_time=mod)
        if cached is not None:
            ocr_ok = not enable_ocr or cached.get("ocr_checked")
            cs_path = (cached.get("keyframes") or {}).get("contact_sheet_path")
            cs_ok = not make_contact_sheet or (bool(cs_path) and Path(cs_path).exists())
            if ocr_ok and cs_ok:
                cached["cache_hit"] = True
                return cached

    max_bytes = int(max_mb * 1024 * 1024) if max_mb and max_mb > 0 else 0
    if max_bytes > 0 and size > max_bytes:
        extra_flags = ["qua_dung_luong"]
        if ext == "ts":
            extra_flags.append("can_remux_mp4")
        if has_glued_unaccented_name(name):
            extra_flags.append("ten_dinh_lien_khong_dau")
        rec = {
            "id": fid, "name": name, "path": full_path, "parent_path": parent_path,
            "mimeType": mime, "ext": ext, "size": size, "modifiedTime": mod,
            "analyzed_at": sc.now_utc_iso(), "status": "qua_dung_luong",
            "metadata": {}, "stats": {}, "audio_signal": {},
            "keyframes": {"timestamps": [], "dhashes": [], "phashes": []},
            "role": classify_video_role(name, parent_path),
            "ocr_heading": "", "ocr_text": "", "ocr_checked": enable_ocr,
            "flags": extra_flags, "cache_hit": False,
        }
        return save_cached_video(rec)

    tmp_dir = Path(tempfile.mkdtemp(prefix="storage_vid_"))
    try:
        safe_name = re.sub(r"[/\\:\x00]", "_", name) or f"{fid}.{ext or 'mp4'}"
        local_tmp = tmp_dir / safe_name
        drive.download(fid, local_tmp)
        parsed = analyze_local_video(
            local_tmp,
            name=name,
            parent_path=parent_path,
            enable_ocr=enable_ocr,
            make_contact_sheet=make_contact_sheet,
            file_id=fid,
        )
    except Exception as e:
        return {
            "id": fid, "name": name, "path": full_path, "parent_path": parent_path,
            "mimeType": mime, "ext": ext, "size": size, "modifiedTime": mod,
            "analyzed_at": sc.now_utc_iso(), "status": "loi_tai",
            "metadata": {}, "stats": {}, "audio_signal": {},
            "keyframes": {"timestamps": [], "dhashes": [], "phashes": []},
            "role": classify_video_role(name, parent_path),
            "ocr_heading": "", "ocr_text": "", "ocr_checked": enable_ocr,
            "flags": ["loi_tai"], "error": str(e), "cache_hit": False,
        }
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    rec = {
        "id": fid, "name": name, "path": full_path, "parent_path": parent_path,
        "mimeType": mime, "ext": parsed.get("ext", ext), "size": size, "modifiedTime": mod,
        "analyzed_at": sc.now_utc_iso(),
        "status": parsed.get("status", "ok"),
        "sha256": parsed.get("sha256", ""),
        "metadata": parsed.get("metadata", {}),
        "stats": parsed.get("stats", {}),
        "audio_signal": parsed.get("audio_signal", {}),
        "keyframes": parsed.get("keyframes", {}),
        "role": parsed.get("role", "video_khac"),
        "ocr_heading": parsed.get("ocr_heading", ""),
        "ocr_text": (parsed.get("ocr_text") or "")[:20_000],
        "ocr_checked": enable_ocr,
        "flags": parsed.get("flags", []),
        "error": parsed.get("error", ""),
        "cache_hit": False,
    }
    return save_cached_video(rec)


def select_video_candidates(
    index: dict,
    branch: Optional[str] = None,
    include_quarantine: bool = False,
    limit: int = 15,
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
        if ext.lower() in VIDEO_EXTENSIONS or mime.startswith("video/"):
            out.append((pp, it))
            if limit > 0 and len(out) >= limit:
                break
    return out


def batch_analyze_videos(
    index: dict,
    drive: sc.Drive,
    branch: Optional[str] = None,
    max_mb: float = 250.0,
    limit: int = 15,
    workers: int = 2,
    enable_ocr: bool = False,
    make_contact_sheet: bool = False,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    cands = select_video_candidates(index, branch=branch, limit=limit)
    records: List[Dict[str, Any]] = []
    if cands:
        with cf.ThreadPoolExecutor(max_workers=max(1, min(workers, len(cands)))) as pool:
            futs = [
                pool.submit(
                    analyze_drive_video, it, pp, drive,
                    force_refresh=force_refresh, max_mb=max_mb,
                    enable_ocr=enable_ocr, make_contact_sheet=make_contact_sheet,
                )
                for pp, it in cands
            ]
            for f in cf.as_completed(futs):
                records.append(f.result())
    records.sort(key=lambda r: r.get("path", ""))
    errs = [r for r in records if r.get("status") == "loi_tai"]
    if errs:
        sc.log(f"⚠️  {len(errs)}/{len(records)} video lỗi tải/xử lý (ví dụ: {errs[0].get('name')}: {errs[0].get('error', '')[:160]})")
    return {"total": len(records), "cache_hits": sum(1 for r in records if r.get("cache_hit")), "errors": len(errs), "records": records}


# ---------------------------------------------------------------------------
# 4. KIỂM TOÁN KHÓA HỌC TRÊN CHỈ MỤC, TRÙNG VIDEO ĐA KEYFRAME & CHUẨN HÓA V6
# ---------------------------------------------------------------------------

def audit_video_catalog(index: dict, branch: Optional[str] = None) -> Dict[str, Any]:
    """
    Kiểm toán siêu tốc toàn bộ kho video trên `storage_index.json` (không tải tệp):
    - Phân bố theo khóa học & định dạng
    - Danh sách `.ts` (`can_remux_mp4`)
    - Thư mục có lỗ hổng bài học (`thieu_bai_trong_chuoi`)
    - Danh sách tệp có tên dính liền không dấu (`ten_dinh_lien_khong_dau`)
    """
    norm_branch = sc.normalize_branch(branch)
    prefix = norm_branch.rstrip("/") + "/" if norm_branch else ""
    explicit_qr = bool(norm_branch and sc.is_quarantine_path(norm_branch))

    total_videos = 0
    total_bytes = 0
    by_ext: Dict[str, int] = collections.Counter()
    by_course: Dict[str, Dict[str, Any]] = {}
    ts_files: List[Dict[str, Any]] = []
    glued_files: List[Dict[str, Any]] = []
    course_gaps: List[Dict[str, Any]] = []

    for path in sorted(index.keys()):
        if norm_branch and not (path == norm_branch or path.startswith(prefix)):
            continue
        if not explicit_qr and sc.is_quarantine_path(path):
            continue
        node = index[path]
        vitems = []
        for it in node.get("items", []):
            mime = it.get("mimeType", "")
            if mime in {sc.FOLDER_MIME, sc.SHORTCUT_MIME} or mime in sc.GOOGLE_NATIVE_MIMES:
                continue
            name = it.get("name", "")
            _, ext = sc.split_ext(name, mime)
            ext_l = ext.lower()
            if ext_l in VIDEO_EXTENSIONS or mime.startswith("video/"):
                vitems.append((it, ext_l))

        if not vitems:
            continue

        parts = path.split("/")
        course_key = "/".join(parts[: min(4, len(parts))])
        c_stat = by_course.setdefault(course_key, {"count": 0, "bytes": 0, "ts_count": 0})

        nums: List[int] = []
        for it, ext_l in vitems:
            name = it.get("name", "")
            sz = int(it.get("size") or 0)
            total_videos += 1
            total_bytes += sz
            by_ext[ext_l or "?"] += 1
            c_stat["count"] += 1
            c_stat["bytes"] += sz

            if ext_l == "ts":
                c_stat["ts_count"] += 1
                ts_files.append({"id": it["id"], "name": name, "path": f"{path}/{name}", "size": sz})
            if has_glued_unaccented_name(name):
                glued_files.append({"id": it["id"], "name": name, "path": f"{path}/{name}", "parent_path": path})

            if len(vitems) >= 3:
                base, _ = sc.split_ext(name, it.get("mimeType", ""))
                for rx in VIDEO_SEQ_PATTERNS:
                    m = rx.search(base)
                    if m:
                        nums.append(int(m.group(1)))
                        break

        if len(vitems) >= 3 and len(nums) >= 3:
            uniq = sorted(set(nums))
            lo, hi = uniq[0], uniq[-1]
            span = hi - lo + 1
            if span <= len(uniq) * 2 + 12 and span <= 500:
                missing = [x for x in range(lo, hi + 1) if x not in set(uniq)]
                if missing:
                    course_gaps.append({
                        "path": path,
                        "video_count": len(vitems),
                        "range": f"{lo}..{hi}",
                        "missing_count": len(missing),
                        "missing_numbers": missing[:25],
                    })

    return {
        "total_videos": total_videos,
        "total_bytes": total_bytes,
        "by_ext": dict(by_ext),
        "by_course": by_course,
        "ts_remux_candidates": ts_files,
        "glued_ascii_names": glued_files,
        "course_gaps": course_gaps,
    }


def _rank_video_keep(rec: Dict[str, Any]) -> Tuple[int, int, int, int, int, str]:
    st = rec.get("stats") or {}
    area = int(st.get("width") or 0) * int(st.get("height") or 0)
    has_audio = 1 if st.get("has_audio") else 0
    codec_ok = 1 if str(st.get("video_codec") or "").lower() in MODERN_VIDEO_CODECS else 0
    is_mp4 = 1 if str(rec.get("ext") or "").lower() == "mp4" else 0
    br = int(st.get("bitrate_kbps") or 0)
    return (area, has_audio, codec_ok, is_mp4, br, rec.get("id", ""))


def _match_keyframe_phashes(
    ph_a: Sequence[str],
    ph_b: Sequence[str],
    max_hamming: int,
) -> Tuple[float, float]:
    """Trả về `(tỷ_lệ_khớp, khoảng_cách_Hamming_trung_bình)` giữa hai chuỗi pHash keyframe."""
    if not ph_a or not ph_b or img_mod is None:
        return 0.0, 64.0
    if len(ph_a) == len(ph_b):
        dists = [img_mod.hamming_distance64(a, b) for a, b in zip(ph_a, ph_b)]
    else:
        short, long = (ph_a, ph_b) if len(ph_a) <= len(ph_b) else (ph_b, ph_a)
        dists = [min(img_mod.hamming_distance64(s, l) for l in long) for s in short]
    matches = sum(1 for d in dists if d <= max_hamming)
    avg_d = sum(dists) / float(len(dists))
    return matches / float(len(dists)), round(avg_d, 2)


def find_video_duplicates(
    records: Sequence[Dict[str, Any]],
    max_hamming: int = 8,
    min_match_ratio: float = 0.60,
) -> Dict[str, Any]:
    """Phát hiện video trùng tuyệt đối (SHA-256) và gần trùng khác độ phân giải (keyframe pHash + thời lượng)."""
    by_sha: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)
    sig_pool: List[Dict[str, Any]] = []

    for r in records:
        if r.get("status") != "ok":
            continue
        if r.get("sha256"):
            by_sha[r["sha256"]].append(r)
        kfs = r.get("keyframes") or {}
        if kfs.get("phashes") and float((r.get("stats") or {}).get("duration_sec") or 0.0) > 0:
            sig_pool.append(r)

    exact_groups: List[Dict[str, Any]] = []
    exact_extra_ids: Set[str] = set()
    for sha, grp in by_sha.items():
        if len(grp) > 1:
            ordered = sorted(grp, key=_rank_video_keep, reverse=True)
            exact_groups.append({"sha256": sha, "keep": ordered[0], "extra": ordered[1:], "count": len(grp)})
            for ex in ordered[1:]:
                exact_extra_ids.add(ex["id"])

    pool = [r for r in sig_pool if r.get("id") not in exact_extra_ids]
    n = len(pool)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    pairs: List[Dict[str, Any]] = []
    for i in range(n):
        di = float(pool[i]["stats"].get("duration_sec") or 0.0)
        pi = pool[i]["keyframes"]["phashes"]
        for j in range(i + 1, n):
            dj = float(pool[j]["stats"].get("duration_sec") or 0.0)
            dur_tol = max(3.0, 0.03 * max(di, dj))
            if abs(di - dj) > dur_tol:
                continue
            pj = pool[j]["keyframes"]["phashes"]
            ratio, avg_dist = _match_keyframe_phashes(pi, pj, max_hamming=max_hamming)
            if ratio >= min_match_ratio:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[rj] = ri
                pairs.append({
                    "a": pool[i],
                    "b": pool[j],
                    "keyframe_match_pct": round(ratio * 100.0, 1),
                    "avg_phash_dist": avg_dist,
                    "dur_diff_sec": round(abs(di - dj), 2),
                })

    clusters: Dict[int, List[Dict[str, Any]]] = collections.defaultdict(list)
    for idx in range(n):
        clusters[find(idx)].append(pool[idx])

    visual_groups: List[Dict[str, Any]] = []
    for grp in clusters.values():
        if len(grp) > 1:
            ordered = sorted(grp, key=_rank_video_keep, reverse=True)
            visual_groups.append({"keep": ordered[0], "extra": ordered[1:], "count": len(grp)})

    pairs.sort(key=lambda p: (-p["keyframe_match_pct"], p["avg_phash_dist"]))
    return {"exact_groups": exact_groups, "visual_groups": visual_groups, "pairs": pairs}


def quarantine_video_duplicates(
    dup_result: Dict[str, Any],
    drive: sc.Drive,
    index: Optional[dict] = None,
    execute: bool = False,
) -> Dict[str, Any]:
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
                "subkind": "video_duplicate",
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

    results = drive.batch_move([(m["id"], dest_id) for m in allowed], workers=4)
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


def _clean_frag(txt: str) -> str:
    s = re.sub(r'[\\/:*?"<>|\r\n]+', " ", sc.nfc(txt or "")).strip(" .-_")
    return re.sub(r"\s{2,}", " ", s)


def _infer_course_subject(parent_path: str) -> str:
    if not parent_path:
        return ""
    last = parent_path.split("/")[-1]
    clean = re.sub(r"^\[\d{2,3}\]\s*", "", last)
    clean = re.sub(r"^\[([^\]]+)\]\s*", "", clean).strip()
    if clean and clean.upper() not in {"TỔNG QUAN", "THEO MÔN"}:
        return sc.title_case_vn(clean)[:40]
    return ""


def suggest_video_v6_name(rec: Dict[str, Any]) -> Optional[Dict[str, str]]:
    name = rec.get("name", "")
    mime = rec.get("mimeType", "")
    parent_path = rec.get("parent_path", "")
    if not name or sc.is_tech_exception(parent_path, name):
        return None
    base, ext = sc.split_ext(name, mime)
    ext = (rec.get("ext") or ext or "mp4").lower()

    stem_main = base.split(" - ")[0].strip()
    is_opaque = bool(OPAQUE_VIDEO_NAME_RE.match(stem_main))
    is_glued = has_glued_unaccented_name(name)
    has_supp = " - " in base
    if has_supp and not is_opaque and not is_glued:
        return None

    meta = rec.get("metadata") or {}
    ocr_head = _clean_frag(rec.get("ocr_heading") or "")
    meta_title = _clean_frag(meta.get("title") or "")

    if is_opaque or is_glued:
        main = meta_title or ocr_head
        if not main:
            return None
        # Giữ nguyên tiền tố "Bài X" nếu bản cũ đang có số bài
        m_bai = re.match(r"^((?:Bài|Buổi|Phần|Tập)\s*\d{1,3})\b", stem_main, re.I)
        if m_bai and not re.match(r"^(?:Bài|Buổi|Phần|Tập)\b", main, re.I):
            main = f"{sc.title_case_vn(m_bai.group(1))} {main}"
    else:
        main = _clean_frag(stem_main.replace("_", " "))

    main_title = sc.title_case_vn(main[:90])
    supp: List[str] = []
    if has_supp:
        existing_supp = _clean_frag(base.split(" - ", 1)[1])
        if existing_supp:
            supp.append(existing_supp)
    elif meta.get("author"):
        supp.append(sc.title_case_vn(_clean_frag(meta["author"])[:45]))
    if not supp:
        ctx = _infer_course_subject(parent_path)
        if ctx:
            supp.append(ctx)
    if not supp:
        supp.append("Video Bài Giảng")

    cand = f"{main_title} - {', '.join(supp)}.{ext}"
    if cand == name:
        return None
    reason = "Đặt tên theo tiêu đề slide/metadata thay tên mơ hồ/dính liền" if (is_opaque or is_glued) else "Bổ sung ngữ cảnh Chuẩn V6"
    return {
        "id": rec.get("id", ""),
        "old_name": name,
        "new_name": cand,
        "parent_path": parent_path,
        "reason": reason,
    }


def apply_video_rename_suggestions(suggestions: Sequence[Dict[str, str]], drive: sc.Drive, index: Optional[dict] = None, execute: bool = False) -> Dict[str, Any]:
    batch_id = f"vid_rename_{sc.now_stamp()}"
    if not execute:
        return {"batch_id": batch_id, "dry_run": True, "planned": len(suggestions), "renamed": 0, "items": list(suggestions)}
    results = drive.batch_rename([(s["id"], s["new_name"]) for s in suggestions if s.get("id") and s.get("new_name")])
    ok_ids = {fid for fid, ok, _ in results if ok}
    ops = [s for s in suggestions if s.get("id") in ok_ids]
    for op in ops:
        rec = load_cached_video(op["id"])
        if rec:
            rec["name"] = op["new_name"]
            if rec.get("parent_path"):
                rec["path"] = f"{rec['parent_path']}/{op['new_name']}"
            save_cached_video(rec)
    if index and ops:
        _, id_map = sc.build_id_map(index)
        for op in ops:
            if op["id"] in id_map:
                id_map[op["id"]][1]["name"] = op["new_name"]
        sc.save_index(index)
    if ops:
        log_data = sc.read_json(sc.media_rename_log_path(), default={"batches": []}) or {"batches": []}
        log_data["batches"].append({"batch_id": batch_id, "kind": "video", "timestamp": sc.now_utc_iso(), "operations": ops})
        sc.write_json(sc.media_rename_log_path(), log_data)
    return {"batch_id": batch_id, "dry_run": False, "planned": len(suggestions), "renamed": len(ops), "items": ops}


def undo_video_rename_batch(batch_id: Optional[str], drive: sc.Drive, index: Optional[dict] = None) -> int:
    log_data = sc.read_json(sc.media_rename_log_path(), default={"batches": []}) or {"batches": []}
    target = None
    for b in reversed(log_data.get("batches", [])):
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
# 5. TỔNG HỢP & XUẤT BÁO CÁO
# ---------------------------------------------------------------------------

def summarize_videos(
    records: Sequence[Dict[str, Any]],
    index: Optional[dict] = None,
    branch: Optional[str] = None,
    max_hamming: int = 8,
) -> Dict[str, Any]:
    by_res: Dict[str, int] = collections.Counter()
    by_role: Dict[str, int] = collections.Counter()
    by_flag: Dict[str, int] = collections.Counter()
    suggestions: List[Dict[str, str]] = []
    total_bytes = 0
    total_sec = 0.0

    for r in records:
        st = r.get("stats") or {}
        total_bytes += int(r.get("size") or 0)
        total_sec += float(st.get("duration_sec") or 0.0)
        by_res[st.get("resolution_tier") or "khong_ro"] += 1
        by_role[r.get("role") or "video_khac"] += 1
        for fl in r.get("flags") or []:
            by_flag[fl] += 1
        sug = suggest_video_v6_name(r)
        if sug:
            suggestions.append(sug)

    dups = find_video_duplicates(records, max_hamming=max_hamming)
    catalog_audit = audit_video_catalog(index, branch=branch) if index else None
    return {
        "total": len(records),
        "total_bytes": total_bytes,
        "total_duration_hours": round(total_sec / 3600.0, 2),
        "by_resolution": dict(by_res),
        "by_role": dict(by_role),
        "by_flag": dict(by_flag),
        "rename_suggestions": suggestions,
        "duplicates": dups,
        "catalog_audit": catalog_audit,
        "records": list(records),
    }


def write_video_reports(summary: Dict[str, Any], branch: Optional[str] = None) -> Tuple[Path, Path]:
    today = sc.today_vn()
    md_p = sc.reports_dir() / f"Báo Cáo Phân Tích Video - Storage, {today}.md"
    csv_p = sc.reports_dir() / f"Báo Cáo Phân Tích Video - Storage, {today}.csv"

    dups = summary["duplicates"]
    sugs = summary["rename_suggestions"]
    cat = summary.get("catalog_audit")

    lines = [
        f"# BÁO CÁO PHÂN TÍCH VIDEO & KHÓA HỌC — [A] STORAGE ({today})",
        "",
        f"- **Phạm vi nhánh**: `{sc.normalize_branch(branch) or sc.ROOT_NAME}`",
        f"- **Số video đã phân tích sâu (cache)**: **{sc.fmt_int(summary['total'])}** ({sc.human_size(summary['total_bytes'])}, tổng thời lượng **{summary['total_duration_hours']} giờ**)",
        f"- **Nhóm trùng SHA-256**: **{len(dups['exact_groups'])}** | **Nhóm trùng keyframe pHash**: **{len(dups['visual_groups'])}**",
        f"- **Gợi ý chuẩn hóa tên V6**: **{len(sugs)}**",
    ]
    if cat:
        lines += [
            f"- **Kiểm toán toàn chỉ mục phạm vi**: **{sc.fmt_int(cat['total_videos'])}** video ({sc.human_size(cat['total_bytes'])}) | `.ts` cần remux: **{len(cat['ts_remux_candidates'])}** | Tên dính liền không dấu: **{len(cat['glued_ascii_names'])}** | Khóa thiếu bài: **{len(cat['course_gaps'])}**",
        ]
    lines.append("")
    sec_no = 1

    if summary["by_resolution"]:
        lines += [
            f"## {sec_no}. Phân bố Độ Phân Giải & Vai Trò (mẫu đã đọc)",
            "",
            sc.md_table(["Độ phân giải", "Số tệp"], sorted(summary["by_resolution"].items(), key=lambda x: -x[1]), ["l", "r"]),
            "",
            sc.md_table(["Vai trò video", "Số tệp"], sorted(summary["by_role"].items(), key=lambda x: -x[1]), ["l", "r"]),
            "",
        ]
        sec_no += 1
    if summary["by_flag"]:
        lines += [
            f"## {sec_no}. Thống kê Cờ Kỹ Thuật & Chất Lượng",
            "",
            sc.md_table(["Cờ cảnh báo", "Số tệp"], sorted(summary["by_flag"].items(), key=lambda x: -x[1]), ["l", "r"]),
            "",
        ]
        sec_no += 1
    if cat and cat.get("course_gaps"):
        lines += [
            f"## {sec_no}. Lỗ Hổng Chuỗi Bài Giảng Khóa Học (từ Chỉ Mục)",
            "",
            sc.md_table(
                ["Thư mục", "Số video", "Dải số", "Bài thiếu (mẫu)"],
                [[g["path"], g["video_count"], g["range"], ", ".join(str(x) for x in g["missing_numbers"][:10])] for g in cat["course_gaps"][:30]],
                ["l", "r", "c", "l"],
            ),
            "",
        ]
        sec_no += 1
    if dups["pairs"]:
        lines += [
            f"## {sec_no}. Cặp Video Gần Trùng Đa Keyframe (pHash)",
            "",
            sc.md_table(
                ["Khớp Keyframe", "Lệch (s)", "Video A", "Video B"],
                [[f"{p['keyframe_match_pct']}%", p["dur_diff_sec"], p["a"]["name"], p["b"]["name"]] for p in dups["pairs"][:25]],
                ["r", "r", "l", "l"],
            ),
            "",
        ]
        sec_no += 1

    rows_sample = []
    for r in summary["records"][:60]:
        st = r.get("stats") or {}
        rows_sample.append([
            r.get("name", ""),
            f"{st.get('width', 0)}x{st.get('height', 0)} ({st.get('resolution_tier', '')})",
            _fmt_ts(st.get("duration_sec") or 0),
            f"{st.get('video_codec', '')}/{st.get('audio_codec', '-')}",
            f"{st.get('bitrate_kbps', '')} kbps",
            r.get("ocr_heading", "")[:40],
            ", ".join(r.get("flags") or []),
        ])
    if rows_sample:
        lines += [
            f"## {sec_no}. Chi Tiết Mẫu Video Đã Phân Tích (tối đa 60 tệp)",
            "",
            sc.md_table(["Tên tệp", "Phân giải", "Thời lượng", "Codec V/A", "Bitrate", "Tiêu đề OCR", "Cờ"], rows_sample),
            "",
        ]
    md_p.write_text("\n".join(lines), encoding="utf-8")

    csv_rows = []
    for r in summary["records"]:
        st = r.get("stats") or {}
        sg = r.get("audio_signal") or {}
        kf = r.get("keyframes") or {}
        csv_rows.append([
            r.get("id", ""), r.get("name", ""), r.get("path", ""), r.get("ext", ""), r.get("status", ""),
            r.get("size", 0), st.get("duration_sec", ""), st.get("width", ""), st.get("height", ""),
            st.get("resolution_tier", ""), st.get("fps", ""), st.get("bitrate_kbps", ""),
            st.get("video_codec", ""), st.get("audio_codec", ""), "Có" if st.get("has_audio") else "Không",
            st.get("subtitle_count", 0), sg.get("integrated_lufs", ""), r.get("role", ""),
            ";".join(kf.get("phashes") or []), r.get("ocr_heading", ""), kf.get("contact_sheet_path", ""),
            ", ".join(r.get("flags") or []),
        ])
    sc.write_csv(
        csv_p,
        [
            "ID", "Tên tệp", "Đường dẫn", "Đuôi", "Trạng thái", "Dung lượng (B)", "Thời lượng (s)",
            "Rộng", "Cao", "Phân hạng", "FPS", "Bitrate (kbps)", "Video Codec", "Audio Codec",
            "Có Audio", "Phụ đề", "Audio LUFS", "Vai trò", "Keyframe pHashes", "Tiêu đề OCR",
            "Contact Sheet", "Cờ",
        ],
        csv_rows,
    )
    return md_p, csv_p


def main() -> None:
    ap = argparse.ArgumentParser(description="Phân tích video, luồng kỹ thuật, keyframe OCR & kiểm toán khóa học (v3.3).")
    ap.add_argument("lenh", nargs="?", default="phan-tich", choices=["phan-tich", "doc", "trung-video", "kiem-tra-khoa-hoc", "goi-y-ten", "hoan-tac-ten"])
    ap.add_argument("muc_tieu", nargs="?", help="Đường dẫn cục bộ hoặc Drive ID/URL cho lệnh `doc`.")
    ap.add_argument("--nhanh", help="Giới hạn phạm vi nhánh.")
    ap.add_argument("--tu-dong-doc", action="store_true", help="Tải & phân tích sâu các video chưa có trong media_cache.")
    ap.add_argument("--chi-chi-muc", action="store_true", help="Chỉ kiểm toán chỉ mục khóa học (không tải tệp).")
    ap.add_argument("--ocr", action="store_true", help="Chạy OCR đọc tiêu đề slide từ keyframes.")
    ap.add_argument("--contact-sheet", action="store_true", help="Tạo ảnh ghép 3x2 Contact Sheet vào reports/contact_sheets/.")
    ap.add_argument("--max-mb", type=float, default=250.0, help="Giới hạn dung lượng tối đa mỗi video (mặc định 250 MB).")
    ap.add_argument("--gioi-han", type=int, default=15, help="Số video tối đa tải & đọc mỗi lô (mặc định 15).")
    ap.add_argument("--luong", type=int, default=2, help="Số luồng xử lý song song (mặc định 2).")
    ap.add_argument("--nguong-hamming", type=int, default=8, help="Ngưỡng khoảng cách pHash keyframe (mặc định 8).")
    ap.add_argument("--gom-trung", action="store_true", help="Lập kế hoạch cách ly video trùng vào [07] KIỂM TRA.")
    ap.add_argument("--ma-lo", help="Mã lô cần hoàn tác.")
    ap.add_argument("--thuc-thi", action="store_true", help="Thực sự đổi tên/di chuyển trên Google Drive.")
    ap.add_argument("--dong-y", action="store_true", help="Không hỏi xác nhận khi --thuc-thi.")
    ap.add_argument("--tai-len", action="store_true", help="Tải báo cáo lên [00] TỔNG QUAN/[02] NHẬT KÍ.")
    args = ap.parse_args()

    if args.lenh == "doc":
        if not args.muc_tieu:
            raise SystemExit("Truyền đường dẫn video cục bộ hoặc ID/URL Google Drive.")
        p_local = Path(args.muc_tieu).expanduser()
        if p_local.exists():
            rec = analyze_local_video(p_local, enable_ocr=args.ocr, make_contact_sheet=args.contact_sheet)
        else:
            fid = sc.extract_drive_id(args.muc_tieu)
            drive = sc.create_drive()
            index = sc.load_index(required=False)
            _, id_map = sc.build_id_map(index) if index else ({}, {})
            pp, item = id_map[fid] if fid in id_map else ("", drive.info(fid))
            rec = analyze_drive_video(
                item, pp, drive, force_refresh=True, max_mb=args.max_mb,
                enable_ocr=args.ocr, make_contact_sheet=args.contact_sheet,
            )
        sc.log(f"🎬 {rec.get('name', args.muc_tieu)} | trạng thái={rec.get('status')} | vai trò={rec.get('role')}")
        sc.log(f"   • Luồng     : {rec.get('stats')}")
        sc.log(f"   • Keyframes : {rec.get('keyframes')}")
        sc.log(f"   • Cờ        : {rec.get('flags')}")
        if rec.get("ocr_heading"):
            sc.log(f"   • OCR Slide : {rec['ocr_heading']}")
        return

    index = sc.load_index(required=False)
    if args.lenh == "hoan-tac-ten":
        n = undo_video_rename_batch(args.ma_lo, sc.create_drive(), index=index)
        sc.log(f"↩️  Đã hoàn tác {n} mục đổi tên video.")
        return

    if args.lenh == "kiem-tra-khoa-hoc" or args.chi_chi_muc:
        if not index:
            raise SystemExit("Chưa có storage_index.json.")
        cat = audit_video_catalog(index, branch=args.nhanh)
        sc.log(f"🎬 Kiểm toán nhanh video ({sc.normalize_branch(args.nhanh) or sc.ROOT_NAME}): {cat['total_videos']} tệp ({sc.human_size(cat['total_bytes'])})")
        sc.log(f"   • Định dạng              : {cat['by_ext']}")
        sc.log(f"   • Tệp .ts (can_remux_mp4): {len(cat['ts_remux_candidates'])}")
        sc.log(f"   • Tên dính liền không dấu: {len(cat['glued_ascii_names'])}")
        sc.log(f"   • Thư mục thiếu bài học  : {len(cat['course_gaps'])}")
        for g in cat["course_gaps"][:15]:
            sc.log(f"     - {g['path']} ({g['video_count']} video, dải {g['range']}): thiếu {g['missing_numbers']}")
        if args.lenh == "kiem-tra-khoa-hoc":
            return

    if args.tu_dong_doc and index:
        batch_analyze_videos(
            index, sc.create_drive(), branch=args.nhanh, max_mb=args.max_mb, limit=args.gioi_han,
            workers=args.luong, enable_ocr=args.ocr, make_contact_sheet=args.contact_sheet,
        )

    recs = iter_cached_videos(branch=args.nhanh, index=index)
    summary = summarize_videos(recs, index=index, branch=args.nhanh, max_hamming=args.nguong_hamming)

    if args.lenh == "trung-video":
        dups = summary["duplicates"]
        sc.log(f"🎞️  Trùng video: {len(dups['exact_groups'])} nhóm SHA-256, {len(dups['visual_groups'])} nhóm keyframe pHash.")
        for p in dups["pairs"][:20]:
            sc.log(f" • [{p['keyframe_match_pct']}% | lệch {p['dur_diff_sec']}s] {p['a']['name']}  <~>  {p['b']['name']}")
        if args.gom_trung:
            preview = quarantine_video_duplicates(dups, sc.create_drive(), index=index, execute=False)
            do_exec = bool(args.thuc_thi and preview["planned"] > 0 and sc.confirm(f"Cách ly {preview['planned']} video trùng vào [07] KIỂM TRA?", assume_yes=args.dong_y))
            qres = quarantine_video_duplicates(dups, sc.create_drive(), index=index, execute=do_exec) if do_exec else preview
            sc.log(f"📦 Cách ly video trùng: dự kiến={qres['planned']}, đã chuyển={qres['moved']}, dry_run={qres['dry_run']}")
        return

    if args.lenh == "goi-y-ten":
        sugs = summary["rename_suggestions"]
        sc.log(f"🏷️  Gợi ý chuẩn hóa tên cho {len(sugs)} video:")
        for s in sugs[:30]:
            sc.log(f" • {s['old_name']}  →  {s['new_name']} ({s['id']})")
        if args.thuc_thi and sugs and sc.confirm(f"Đổi tên {len(sugs)} video trên Drive?", assume_yes=args.dong_y):
            res = apply_video_rename_suggestions(sugs, sc.create_drive(), index=index, execute=True)
            sc.log(f"✅ Đã đổi tên {res['renamed']}/{res['planned']} video (lô {res['batch_id']}).")
        return

    md_p, csv_p = write_video_reports(summary, branch=args.nhanh)
    sc.log(f"🎬 Đã phân tích {summary['total']} video | cờ={summary['by_flag']} | trùng keyframe={len(summary['duplicates']['visual_groups'])}")
    sc.log(f"📝 Báo cáo MD : {md_p}")
    sc.log(f"📝 Báo cáo CSV: {csv_p}")
    if args.tai_len:
        drive = sc.create_drive()
        sc.publish_file(drive, md_p, sc.nhat_ki_id())
        sc.publish_file(drive, csv_p, sc.nhat_ki_id())
        sc.log("☁️  Đã tải báo cáo phân tích video lên [02] NHẬT KÍ.")


if __name__ == "__main__":
    main()
