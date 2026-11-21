#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PHÂN TÍCH ÂM THANH, PHỔ LUFS, KHOẢNG LẶNG & VÂN TAY ÂM HỌC — [A] STORAGE (v3.3)
=================================================================================
Chương trình `[17] PHÂN TÍCH ÂM THANH/audio_analyzer.py` quản trị kho âm thanh
(`.mp3`, `.m4a`, `.m4b`, `.wav`, `.flac`, `.aac`, `.ogg`, `.wma`):

1. `phan-tich`      : Đọc thông số kỹ thuật (`ffprobe` + ID3v1/v2 Unicode), phân tích
                      độ lớn phát sóng EBU R128 (`LUFS`), đỉnh méo tiếng (`clipping`),
                      khoảng lặng (`silencedetect`), dấu vân tay âm học và xuất `.md`/`.csv`.
2. `doc`            : Đọc & kiểm tra tức thì 1 tệp âm thanh (cục bộ hoặc Drive ID/URL).
3. `trung-am-thanh` : Rà soát tệp âm thanh trùng nội dung khác bitrate/định dạng bằng
                      đường bao năng lượng phổ thời gian (`Audio Envelope Fingerprint`),
                      tùy chọn cách ly bản chất lượng thấp hơn vào `[07] KIỂM TRA`.
4. `kiem-tra-chuoi` : Kiểm toán siêu tốc trên chỉ mục để tìm lỗ hổng số bài/phần/track
                      bị khuyết trong các thư mục luyện nghe HSK, IELTS, Ngữ Văn, Sách nói.
5. `goi-y-ten`      : Đề xuất chuẩn hóa tên Chuẩn V6 từ thẻ ID3/MP4 (`title`, `artist`, `album`).
6. `hoan-tac-ten`   : Hoàn tác lô đổi tên âm thanh gần nhất từ `media_rename_log.json`.
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import time
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple


from storage_suite import core as sc

AUDIO_EXTENSIONS: Set[str] = {
    "mp3", "m4a", "m4b", "wav", "flac", "aac", "ogg", "wma", "opus", "aiff",
}

LOSSLESS_CODECS: Set[str] = {"flac", "alac", "pcm_s16le", "pcm_s24le", "pcm_s32le", "pcm_f32le", "wav"}

OPAQUE_AUDIO_NAME_RE = re.compile(
    r"^(?:track|audio|rec|recording|voice|untitled|sound|clip|file|bai|phan|part|\d{1,6})([ _-]?\d*)?$",
    re.I,
)

SEQ_NUM_PATTERNS = [
    re.compile(r"(?:phần|phan|part|tập|tap|bài|bai|buổi|buoi|track|lesson|unit|test|cd\d*\s*-?|p)\s*0*(\d{1,4})\b", re.I),
    re.compile(r"^0*(\d{1,4})(?:\s*[.\-_]|\s+)"),
    re.compile(r"^0*(\d{1,4})$"),
]


# ---------------------------------------------------------------------------
# 1. ĐỌC SIÊU DỮ LIỆU ID3/MP4 & FFPROBE
# ---------------------------------------------------------------------------

def _decode_id3_text(payload: bytes) -> str:
    if not payload:
        return ""
    enc = payload[0]
    body = payload[1:]
    try:
        if enc == 0:
            # Ưu tiên UTF-8 nếu hợp lệ, sau đó CP1258 / Latin-1
            raw = body.rstrip(b"\x00")
            try:
                return sc.nfc(raw.decode("utf-8").strip())
            except UnicodeDecodeError:
                return sc.nfc(raw.decode("cp1258", errors="replace").strip())
        if enc == 1:
            return sc.nfc(body.decode("utf-16", errors="replace").rstrip("\x00").strip())
        if enc == 2:
            return sc.nfc(body.decode("utf-16-be", errors="replace").rstrip("\x00").strip())
        if enc == 3:
            return sc.nfc(body.decode("utf-8", errors="replace").rstrip("\x00").strip())
    except Exception:
        pass
    return sc.nfc(body.decode("utf-8", errors="replace").rstrip("\x00").strip())


def read_id3_tags(path: Path) -> Tuple[Dict[str, str], bool]:
    """Đọc bổ sung thẻ ID3v2 / ID3v1 bằng Python thuần để xử lý chuẩn Unicode tiếng Việt."""
    tags: Dict[str, str] = {}
    has_cover = False
    try:
        with open(path, "rb") as f:
            head = f.read(10)
            if len(head) == 10 and head[:3] == b"ID3":
                ver_major = head[3]
                sz = ((head[6] & 0x7F) << 21) | ((head[7] & 0x7F) << 14) | ((head[8] & 0x7F) << 7) | (head[9] & 0x7F)
                raw = f.read(min(sz, 2 * 1024 * 1024))
                pos = 0
                frame_map = {
                    "TIT2": "title", "TT2": "title",
                    "TPE1": "artist", "TP1": "artist",
                    "TALB": "album", "TAL": "album",
                    "TRCK": "track", "TRK": "track",
                    "TCON": "genre", "TCO": "genre",
                    "TDRC": "date", "TYER": "date", "TYE": "date",
                }
                while pos + 10 <= len(raw) and ver_major in (3, 4):
                    fid = raw[pos : pos + 4].decode("latin-1", errors="ignore")
                    if not re.match(r"^[A-Z0-9]{4}$", fid):
                        break
                    b4 = raw[pos + 4 : pos + 8]
                    if ver_major == 4:
                        fsz = ((b4[0] & 0x7F) << 21) | ((b4[1] & 0x7F) << 14) | ((b4[2] & 0x7F) << 7) | (b4[3] & 0x7F)
                    else:
                        fsz = int.from_bytes(b4, "big")
                    pos += 10
                    if fsz <= 0 or pos + fsz > len(raw):
                        break
                    fdata = raw[pos : pos + fsz]
                    pos += fsz
                    if fid == "APIC":
                        has_cover = True
                    elif fid in frame_map:
                        val = _decode_id3_text(fdata)
                        if val:
                            tags.setdefault(frame_map[fid], val)

            # Fallback ID3v1 (128 byte cuối)
            f.seek(0, os.SEEK_END)
            fsize = f.tell()
            if fsize >= 128:
                f.seek(fsize - 128)
                tail = f.read(128)
                if tail[:3] == b"TAG":
                    for sl, key in ((slice(3, 33), "title"), (slice(33, 63), "artist"), (slice(63, 93), "album"), (slice(93, 97), "date")):
                        val = tail[sl].rstrip(b"\x00 ").decode("utf-8", errors="ignore").strip()
                        if val:
                            tags.setdefault(key, sc.nfc(val))
    except OSError:
        pass
    return tags, has_cover


def inspect_audio_metadata(path: Path) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Đọc metadata & thông số kỹ thuật luồng audio bằng `ffprobe` + ID3v1/v2 + `wave` fallback."""
    meta: Dict[str, Any] = {}
    stats: Dict[str, Any] = {}
    id3_tags, id3_cover = read_id3_tags(path)
    has_cover = id3_cover

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
                        stats["duration_sec"] = round(float(fmt["duration"]), 2)
                    except ValueError:
                        pass
                if fmt.get("bit_rate") and str(fmt["bit_rate"]).isdigit():
                    stats["bitrate_kbps"] = round(int(fmt["bit_rate"]) / 1000)

                raw_tags = fmt.get("tags", {}) or {}
                for k, v in raw_tags.items():
                    kl = k.lower()
                    val = sc.nfc(str(v).strip())
                    if not val:
                        continue
                    if kl == "title":
                        meta["title"] = val
                    elif kl in {"artist", "album_artist", "author"}:
                        meta.setdefault("artist", val)
                    elif kl == "album":
                        meta["album"] = val
                    elif kl == "genre":
                        meta["genre"] = val
                    elif kl in {"track", "tracknumber"}:
                        meta["track"] = val
                    elif kl in {"date", "year", "creation_time"}:
                        meta["date"] = val

                for st in info.get("streams", []) or []:
                    ctype = st.get("codec_type")
                    disp = st.get("disposition") or {}
                    if disp.get("attached_pic") == 1:
                        has_cover = True
                    if ctype == "audio" and "audio_codec" not in stats:
                        stats["audio_codec"] = st.get("codec_name", "")
                        if st.get("sample_rate") and str(st["sample_rate"]).isdigit():
                            stats["sample_rate_hz"] = int(st["sample_rate"])
                        if st.get("channels"):
                            stats["channels"] = int(st["channels"])
                        if not stats.get("bitrate_kbps") and st.get("bit_rate") and str(st["bit_rate"]).isdigit():
                            stats["bitrate_kbps"] = round(int(st["bit_rate"]) / 1000)
                        st_tags = st.get("tags", {}) or {}
                        for k, v in st_tags.items():
                            if k.lower() in {"title", "artist", "album", "track", "genre", "date"} and str(v).strip():
                                meta.setdefault(k.lower(), sc.nfc(str(v).strip()))
        except Exception:
            pass

    # Trộn thẻ ID3 tiếng Việt chuẩn xác nếu ffprobe thiếu
    for k, v in id3_tags.items():
        if v and not meta.get(k):
            meta[k] = v
    meta["has_cover_art"] = has_cover

    # Dự phòng `wave` chuẩn Python nếu là WAV chưa đọc được
    if not stats.get("duration_sec"):
        try:
            with wave.open(str(path), "rb") as wf:
                sr = wf.getframerate()
                nf = wf.getnframes()
                ch = wf.getnchannels()
                sw = wf.getsampwidth()
                if sr > 0:
                    dur = nf / float(sr)
                    stats["duration_sec"] = round(dur, 2)
                    stats.setdefault("sample_rate_hz", sr)
                    stats.setdefault("channels", ch)
                    stats.setdefault("audio_codec", f"pcm_s{sw * 8}le")
                    stats.setdefault("bitrate_kbps", round(sr * ch * sw * 8 / 1000))
        except Exception:
            pass

    return meta, stats


# ---------------------------------------------------------------------------
# 2. PHÂN TÍCH PHỔ ÂM LUFS, MÉO TIẾNG, KHOẢNG LẶNG & VÂN TAY ÂM HỌC
# ---------------------------------------------------------------------------

def _parse_ffmpeg_audio_analysis(stderr: str, duration_sec: float) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "integrated_lufs": None,
        "lra_lu": None,
        "mean_volume_db": None,
        "max_volume_db": None,
        "silence_segments": 0,
        "silence_total_sec": 0.0,
        "silence_ratio_pct": 0.0,
        "trailing_silence_sec": 0.0,
    }
    m_mean = re.search(r"mean_volume:\s*([-\d.inf]+)\s*dB", stderr, re.I)
    if m_mean and "inf" not in m_mean.group(1).lower():
        out["mean_volume_db"] = round(float(m_mean.group(1)), 2)

    m_max = re.search(r"max_volume:\s*([-\d.inf]+)\s*dB", stderr, re.I)
    if m_max and "inf" not in m_max.group(1).lower():
        out["max_volume_db"] = round(float(m_max.group(1)), 2)

    # Khối Summary của ebur128 nằm ở cuối stderr
    m_i = re.findall(r"Integrated loudness:\s*\n\s*I:\s*([-\d.inf]+)\s*LUFS", stderr, re.M)
    if m_i and "inf" not in m_i[-1].lower():
        out["integrated_lufs"] = round(float(m_i[-1]), 2)
    m_lra = re.findall(r"Loudness range:\s*\n\s*LRA:\s*([-\d.inf]+)\s*LU", stderr, re.M)
    if m_lra and "inf" not in m_lra[-1].lower():
        out["lra_lu"] = round(float(m_lra[-1]), 2)

    sil_starts = [float(x) for x in re.findall(r"silence_start:\s*([\d.]+)", stderr)]
    sil_durs = [float(x) for x in re.findall(r"silence_duration:\s*([\d.]+)", stderr)]
    sil_ends = [float(x) for x in re.findall(r"silence_end:\s*([\d.]+)", stderr)]

    total_sil = sum(sil_durs)
    # Nếu có silence_start ở cuối chưa có silence_end
    trailing = 0.0
    if len(sil_starts) > len(sil_durs) and duration_sec > 0:
        tail_gap = max(0.0, duration_sec - sil_starts[-1])
        total_sil += tail_gap
        trailing = tail_gap
    elif sil_ends and sil_durs and duration_sec > 0 and abs(sil_ends[-1] - duration_sec) <= 1.0:
        trailing = sil_durs[-1]

    out["silence_segments"] = len(sil_starts)
    out["silence_total_sec"] = round(total_sil, 2)
    out["trailing_silence_sec"] = round(trailing, 2)
    if duration_sec > 0:
        out["silence_ratio_pct"] = round(min(100.0, (total_sil / duration_sec) * 100.0), 1)
    return out


def _analyze_wav_numpy_fallback(path: Path) -> Optional[Dict[str, Any]]:
    import numpy as np  # type: ignore
    try:
        with wave.open(str(path), "rb") as wf:
            sr = wf.getframerate()
            ch = wf.getnchannels()
            sw = wf.getsampwidth()
            raw = wf.readframes(wf.getnframes())
    except Exception:
        return None
    if not raw or sw != 2 or sr <= 0:
        return None
    arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        arr = arr.reshape(-1, ch).mean(axis=1)
    peak = float(np.max(np.abs(arr))) if len(arr) else 0.0
    rms = float(np.sqrt(np.mean(arr * arr))) if len(arr) else 0.0
    max_db = round(20.0 * math.log10(max(peak, 1e-7)), 2)
    mean_db = round(20.0 * math.log10(max(rms, 1e-7)), 2)
    win = max(1, int(sr * 0.5))
    n_win = len(arr) // win
    sil_cnt = 0
    for i in range(n_win):
        w_rms = float(np.sqrt(np.mean(arr[i * win : (i + 1) * win] ** 2)))
        if w_rms < 0.008:
            sil_cnt += 1
    sil_pct = round((sil_cnt / max(1, n_win)) * 100.0, 1) if n_win else 0.0
    return {
        "integrated_lufs": round(mean_db - 1.5, 2),
        "lra_lu": 0.0,
        "mean_volume_db": mean_db,
        "max_volume_db": max_db,
        "silence_segments": sil_cnt,
        "silence_total_sec": round(sil_cnt * 0.5, 2),
        "silence_ratio_pct": sil_pct,
        "trailing_silence_sec": 0.0,
    }


def analyze_audio_signal(path: Path, duration_sec: float) -> Dict[str, Any]:
    """Chạy 1 lượt `ffmpeg` (`volumedetect + ebur128 + silencedetect`) để đo chất lượng tín hiệu."""
    if shutil.which("ffmpeg"):
        try:
            proc = subprocess.run(
                [
                    "ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-vn",
                    "-af", "volumedetect,ebur128=framelog=verbose,silencedetect=noise=-42dB:d=2.0",
                    "-f", "null", "-",
                ],
                capture_output=True,
                text=True,
                timeout=90,
            )
            if proc.returncode == 0:
                return _parse_ffmpeg_audio_analysis(proc.stderr or "", duration_sec)
        except Exception:
            pass
    fb = _analyze_wav_numpy_fallback(path)
    return fb or {}


def compute_audio_fingerprint(path: Path) -> Tuple[str, List[float]]:
    """
    Trích xuất dấu vân tay âm học trên 180 giây đầu ở dạng PCM 8kHz mono:
    - Trả về `(hash_64bit_hex, vector_nang_luong_64_chieu)` bất biến với bitrate/codec.
    """
    import numpy as np  # type: ignore

    pcm = b""
    if shutil.which("ffmpeg"):
        try:
            proc = subprocess.run(
                ["ffmpeg", "-v", "error", "-t", "180", "-i", str(path), "-vn", "-ac", "1", "-ar", "8000", "-f", "s16le", "pipe:1"],
                capture_output=True,
                timeout=60,
            )
            if proc.returncode == 0 and proc.stdout:
                pcm = proc.stdout
        except Exception:
            pcm = b""

    if not pcm:
        try:
            with wave.open(str(path), "rb") as wf:
                sr = wf.getframerate()
                ch = wf.getnchannels()
                sw = wf.getsampwidth()
                if sw == 2 and sr > 0:
                    raw = wf.readframes(min(wf.getnframes(), sr * 180))
                    arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
                    if ch > 1:
                        arr = arr.reshape(-1, ch).mean(axis=1)
                    if sr != 8000 and len(arr) > 10:
                        xp = np.linspace(0.0, 1.0, len(arr))
                        xnew = np.linspace(0.0, 1.0, max(64, int(len(arr) * (8000.0 / sr))))
                        arr = np.interp(xnew, xp, arr)
                    pcm_arr = arr / 32768.0
                else:
                    return "", []
        except Exception:
            return "", []
    else:
        pcm_arr = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0

    if len(pcm_arr) < 128:
        return "", []

    # Chia thành tối đa 320 khung đều nhau để tạo đường bao log-RMS rồi nội suy về 64 điểm
    n_bins = min(320, max(65, len(pcm_arr) // 512))
    chunks = np.array_split(pcm_arr, n_bins)
    curve = np.array([math.log10(float(np.sqrt(np.mean(c * c))) + 1e-6) for c in chunks], dtype=np.float64)

    xp = np.linspace(0.0, 1.0, len(curve))
    vec64 = np.interp(np.linspace(0.0, 1.0, 64), xp, curve)
    vec65 = np.interp(np.linspace(0.0, 1.0, 65), xp, curve)

    # Chuẩn hóa L2 để dùng độ tương đồng cosine
    centered = vec64 - float(np.mean(vec64))
    norm = float(np.linalg.norm(centered))
    unit_vec = [round(float(x / norm), 3) for x in centered] if norm > 1e-8 else [0.0] * 64

    val = 0
    for i in range(64):
        val = (val << 1) | (1 if vec65[i + 1] > vec65[i] else 0)
    return f"{val:016x}", unit_vec


def classify_audio_role(name: str, parent_path: str, duration_sec: float, meta: Dict[str, Any]) -> str:
    low = f"{parent_path}/{name}".lower()
    if any(k in low for k in ("hsk", "ielts", "listening", "toeic", "vstep", "nghe", "audio book")):
        if duration_sec <= 900 or "luyen nghe" in low or "listening" in low or "hsk" in low:
            return "luyen_nghe_ngoai_ngu"
    if any(k in low for k in ("phật giáo", "phat giao", "niệm phật", "huyền thư", "sách nói", "sach noi", "truyện")):
        return "sach_noi_phap_bao"
    if any(k in low for k in ("âm nhạc", "am nhac", "nhạc", "mp3", "music")) and not any(k in low for k in ("học thuật", "bài tập", "ngữ văn")):
        return "am_nhac"
    if duration_sec >= 900 or any(k in low for k in ("ngữ văn", "đại học", "ussh", "bài giảng", "llvh")):
        return "bai_giang_hoc_thuat"
    genre = str(meta.get("genre", "")).lower()
    if any(k in genre for k in ("speech", "podcast", "audiobook", "lecture")):
        return "bai_giang_hoc_thuat"
    return "am_thanh_khac"


# ---------------------------------------------------------------------------
# 3. ĐỌC & PHÂN TÍCH MỘT TỆP ÂM THANH (LOCAL / DRIVE) + BỘ ĐỆM
# ---------------------------------------------------------------------------

def analyze_local_audio(
    path: Path,
    name: Optional[str] = None,
    parent_path: str = "",
) -> Dict[str, Any]:
    path = Path(path)
    display_name = name or path.name
    _, ext = sc.split_ext(display_name)
    ext = ext.lower()

    if not path.exists():
        return {"status": "am_thanh_hong", "ext": ext, "flags": ["am_thanh_hong"], "metadata": {}, "stats": {}, "signal": {}}

    size = path.stat().st_size
    sha256 = sc.sha256_file(path)
    if size == 0:
        return {"status": "tep_rong", "ext": ext, "sha256": sha256, "flags": ["tep_rong"], "metadata": {}, "stats": {}, "signal": {}}

    meta, stats = inspect_audio_metadata(path)
    dur = float(stats.get("duration_sec") or 0.0)
    if dur <= 0.0:
        return {
            "status": "am_thanh_hong", "ext": ext, "sha256": sha256,
            "metadata": meta, "stats": stats, "signal": {},
            "fingerprint": {"hash": "", "vec": []}, "role": "am_thanh_khac",
            "flags": ["am_thanh_hong"],
        }

    signal = analyze_audio_signal(path, dur)
    fp_hash, fp_vec = compute_audio_fingerprint(path)

    flags: List[str] = []
    max_db = signal.get("max_volume_db")
    mean_db = signal.get("mean_volume_db")
    lufs = signal.get("integrated_lufs")
    sil_pct = float(signal.get("silence_ratio_pct") or 0.0)
    trail_sil = float(signal.get("trailing_silence_sec") or 0.0)

    if max_db is not None and max_db >= -0.1:
        flags.append("bi_re_tieng")
    if sil_pct >= 95.0 or (max_db is not None and max_db <= -65.0):
        flags.append("am_thanh_rong_im_lang")
    elif sil_pct >= 35.0:
        flags.append("nhieu_khoang_lang")
    if trail_sil >= 20.0 and dur >= 40.0:
        flags.append("du_doan_cat_nham_cuoi")
    if (lufs is not None and lufs < -28.0) or (lufs is None and mean_db is not None and mean_db < -32.0):
        flags.append("am_luong_nho")

    br = int(stats.get("bitrate_kbps") or 0)
    codec = str(stats.get("audio_codec") or "").lower()
    if 0 < br < 64 and codec not in LOSSLESS_CODECS:
        flags.append("bitrate_thap")

    role = classify_audio_role(display_name, parent_path, dur, meta)
    return {
        "status": "ok",
        "ext": ext,
        "sha256": sha256,
        "metadata": meta,
        "stats": stats,
        "signal": signal,
        "fingerprint": {"hash": fp_hash, "vec": fp_vec},
        "role": role,
        "flags": list(dict.fromkeys(flags)),
    }


def cache_record_path(file_id: str) -> Path:
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", file_id)
    return sc.media_cache_dir("audio") / f"{safe_id}.json"


def load_cached_audio(file_id: str, modified_time: Optional[str] = None) -> Optional[Dict[str, Any]]:
    rec = sc.read_json(cache_record_path(file_id))
    if not isinstance(rec, dict):
        return None
    if modified_time and rec.get("modifiedTime") and rec.get("modifiedTime") != modified_time:
        return None
    return rec


def save_cached_audio(record: Dict[str, Any]) -> Dict[str, Any]:
    sc.write_json(cache_record_path(record["id"]), record)
    return record


def iter_cached_audio(branch: Optional[str] = None, index: Optional[dict] = None) -> List[Dict[str, Any]]:
    norm_branch = sc.normalize_branch(branch)
    prefix = norm_branch.rstrip("/") + "/" if norm_branch else ""
    id_to_entry: Dict[str, Tuple[str, dict]] = {}
    if index:
        _, id_to_entry = sc.build_id_map(index)

    out: List[Dict[str, Any]] = []
    for p in sorted(sc.media_cache_dir("audio").glob("*.json")):
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


def analyze_drive_audio(
    item: dict,
    parent_path: str,
    drive: sc.Drive,
    force_refresh: bool = False,
    max_mb: float = 100.0,
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
        cached = load_cached_audio(fid, modified_time=mod)
        if cached is not None:
            cached["cache_hit"] = True
            return cached

    max_bytes = int(max_mb * 1024 * 1024) if max_mb and max_mb > 0 else 0
    if max_bytes > 0 and size > max_bytes:
        rec = {
            "id": fid, "name": name, "path": full_path, "parent_path": parent_path,
            "mimeType": mime, "ext": ext, "size": size, "modifiedTime": mod,
            "analyzed_at": sc.now_utc_iso(), "status": "qua_dung_luong",
            "metadata": {}, "stats": {}, "signal": {}, "fingerprint": {"hash": "", "vec": []},
            "role": "am_thanh_khac", "flags": ["qua_dung_luong"], "cache_hit": False,
        }
        return save_cached_audio(rec)

    tmp_dir = Path(tempfile.mkdtemp(prefix="storage_aud_"))
    try:
        safe_name = re.sub(r"[/\\:\x00]", "_", name) or f"{fid}.{ext or 'mp3'}"
        local_tmp = tmp_dir / safe_name
        drive.download(fid, local_tmp)
        parsed = analyze_local_audio(local_tmp, name=name, parent_path=parent_path)
    except Exception as e:
        return {
            "id": fid, "name": name, "path": full_path, "parent_path": parent_path,
            "mimeType": mime, "ext": ext, "size": size, "modifiedTime": mod,
            "analyzed_at": sc.now_utc_iso(), "status": "loi_tai",
            "metadata": {}, "stats": {}, "signal": {}, "fingerprint": {"hash": "", "vec": []},
            "role": "am_thanh_khac", "flags": ["loi_tai"], "error": str(e), "cache_hit": False,
        }
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    rec = {
        "id": fid, "name": name, "path": full_path, "parent_path": parent_path,
        "mimeType": mime, "ext": parsed.get("ext", ext), "size": size, "modifiedTime": mod,
        "analyzed_at": sc.now_utc_iso(), "status": parsed.get("status", "ok"),
        "sha256": parsed.get("sha256", ""), "metadata": parsed.get("metadata", {}),
        "stats": parsed.get("stats", {}), "signal": parsed.get("signal", {}),
        "fingerprint": parsed.get("fingerprint", {"hash": "", "vec": []}),
        "role": parsed.get("role", "am_thanh_khac"), "flags": parsed.get("flags", []),
        "error": parsed.get("error", ""), "cache_hit": False,
    }
    return save_cached_audio(rec)


def select_audio_candidates(
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
        if ext.lower() in AUDIO_EXTENSIONS or mime.startswith("audio/"):
            out.append((pp, it))
            if limit > 0 and len(out) >= limit:
                break
    return out


def batch_analyze_audio(
    index: dict,
    drive: sc.Drive,
    branch: Optional[str] = None,
    max_mb: float = 100.0,
    limit: int = 30,
    workers: int = 3,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    cands = select_audio_candidates(index, branch=branch, limit=limit)
    records: List[Dict[str, Any]] = []
    if cands:
        with cf.ThreadPoolExecutor(max_workers=max(1, min(workers, len(cands)))) as pool:
            futs = [pool.submit(analyze_drive_audio, it, pp, drive, force_refresh=force_refresh, max_mb=max_mb) for pp, it in cands]
            for f in cf.as_completed(futs):
                records.append(f.result())
    records.sort(key=lambda r: r.get("path", ""))
    errs = [r for r in records if r.get("status") == "loi_tai"]
    if errs:
        sc.log(f"⚠️  {len(errs)}/{len(records)} tệp âm thanh lỗi tải/xử lý (ví dụ: {errs[0].get('name')}: {errs[0].get('error', '')[:160]})")
    return {"total": len(records), "cache_hits": sum(1 for r in records if r.get("cache_hit")), "errors": len(errs), "records": records}


# ---------------------------------------------------------------------------
# 4. TRÙNG LẶP ÂM HỌC, KIỂM TOÁN CHUỖI BÀI & GỢI Ý TÊN CHUẨN V6
# ---------------------------------------------------------------------------

def _rank_audio_keep(rec: Dict[str, Any]) -> Tuple[int, int, int, int, str]:
    st = rec.get("stats") or {}
    codec = str(st.get("audio_codec") or "").lower()
    is_lossless = 1 if codec in LOSSLESS_CODECS else 0
    br = int(st.get("bitrate_kbps") or 0)
    sr = int(st.get("sample_rate_hz") or 0)
    has_art = 1 if (rec.get("metadata") or {}).get("has_cover_art") else 0
    return (is_lossless, br, sr, has_art, rec.get("id", ""))


def _cosine_sim(v1: Sequence[float], v2: Sequence[float]) -> float:
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    n1 = math.sqrt(sum(a * a for a in v1))
    n2 = math.sqrt(sum(b * b for b in v2))
    if n1 <= 1e-9 or n2 <= 1e-9:
        return 0.0
    return dot / (n1 * n2)


def find_audio_duplicates(
    records: Sequence[Dict[str, Any]],
    min_cosine: float = 0.92,
    max_dur_diff: float = 2.5,
) -> Dict[str, Any]:
    by_sha: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)
    fingerprinted: List[Dict[str, Any]] = []

    for r in records:
        if r.get("status") != "ok":
            continue
        if r.get("sha256"):
            by_sha[r["sha256"]].append(r)
        fp = r.get("fingerprint") or {}
        if fp.get("vec") and float((r.get("stats") or {}).get("duration_sec") or 0.0) > 0:
            fingerprinted.append(r)

    exact_groups: List[Dict[str, Any]] = []
    exact_extra_ids: Set[str] = set()
    for sha, grp in by_sha.items():
        if len(grp) > 1:
            ordered = sorted(grp, key=_rank_audio_keep, reverse=True)
            exact_groups.append({"sha256": sha, "keep": ordered[0], "extra": ordered[1:], "count": len(grp)})
            for ex in ordered[1:]:
                exact_extra_ids.add(ex["id"])

    pool = [r for r in fingerprinted if r.get("id") not in exact_extra_ids]
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
        vi = pool[i]["fingerprint"]["vec"]
        hi = pool[i]["fingerprint"].get("hash", "")
        for j in range(i + 1, n):
            dj = float(pool[j]["stats"].get("duration_sec") or 0.0)
            if abs(di - dj) > max_dur_diff:
                continue
            vj = pool[j]["fingerprint"]["vec"]
            cos = _cosine_sim(vi, vj)
            hdist = (int(hi, 16) ^ int(pool[j]["fingerprint"].get("hash", ""), 16)).bit_count() if hi and pool[j]["fingerprint"].get("hash") else 64
            if cos >= min_cosine or (hdist <= 6 and cos >= 0.85):
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[rj] = ri
                pairs.append({
                    "a": pool[i], "b": pool[j],
                    "cosine_pct": round(cos * 100.0, 1),
                    "hamming": hdist,
                    "dur_diff_sec": round(abs(di - dj), 2),
                })

    clusters: Dict[int, List[Dict[str, Any]]] = collections.defaultdict(list)
    for idx in range(n):
        clusters[find(idx)].append(pool[idx])

    acoustic_groups: List[Dict[str, Any]] = []
    for grp in clusters.values():
        if len(grp) > 1:
            ordered = sorted(grp, key=_rank_audio_keep, reverse=True)
            acoustic_groups.append({"keep": ordered[0], "extra": ordered[1:], "count": len(grp)})

    pairs.sort(key=lambda p: -p["cosine_pct"])
    return {"exact_groups": exact_groups, "acoustic_groups": acoustic_groups, "pairs": pairs}


def quarantine_audio_duplicates(
    dup_result: Dict[str, Any],
    drive: sc.Drive,
    index: Optional[dict] = None,
    execute: bool = False,
) -> Dict[str, Any]:
    """Đưa bản âm thanh trùng kém chất lượng hơn vào `[07] KIỂM TRA/[03] TỆP TRÙNG LẶP` (mặc định chạy thử)."""
    moves: List[dict] = []
    seen_ids: Set[str] = set()
    for grp in dup_result.get("exact_groups", []) + dup_result.get("acoustic_groups", []):
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
                "subkind": "audio_duplicate",
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


def audit_audio_sequences(index: dict, branch: Optional[str] = None) -> List[Dict[str, Any]]:
    """Quét nhanh trên `storage_index.json` phát hiện thư mục luyện nghe/bài giảng bị khuyết số bài."""
    norm_branch = sc.normalize_branch(branch)
    prefix = norm_branch.rstrip("/") + "/" if norm_branch else ""
    gaps: List[Dict[str, Any]] = []

    for path in sorted(index.keys()):
        if norm_branch and not (path == norm_branch or path.startswith(prefix)):
            continue
        if sc.is_quarantine_path(path):
            continue
        node = index[path]
        audio_items = []
        for it in node.get("items", []):
            mime = it.get("mimeType", "")
            _, ext = sc.split_ext(it.get("name", ""), mime)
            if ext.lower() in AUDIO_EXTENSIONS or mime.startswith("audio/"):
                audio_items.append(it)
        if len(audio_items) < 3:
            continue

        nums: List[int] = []
        for it in audio_items:
            base, _ = sc.split_ext(it.get("name", ""), it.get("mimeType", ""))
            found = None
            for rx in SEQ_NUM_PATTERNS:
                m = rx.search(base)
                if m:
                    found = int(m.group(1))
                    break
            if found is not None and 0 <= found <= 9999:
                nums.append(found)

        uniq = sorted(set(nums))
        if len(uniq) < 3:
            continue
        lo, hi = uniq[0], uniq[-1]
        span = hi - lo + 1
        # Chỉ báo cáo nếu chuỗi số có tính liên tục cao (tránh nhầm danh mục năm/ngày)
        if span > len(uniq) * 2 + 12 or span > 500:
            continue
        missing = [x for x in range(lo, hi + 1) if x not in set(uniq)]
        if missing:
            gaps.append({
                "path": path,
                "audio_count": len(audio_items),
                "range": f"{lo}..{hi}",
                "missing_count": len(missing),
                "missing_numbers": missing[:25],
            })
    return gaps


def suggest_audio_v6_name(rec: Dict[str, Any]) -> Optional[Dict[str, str]]:
    name = rec.get("name", "")
    mime = rec.get("mimeType", "")
    parent_path = rec.get("parent_path", "")
    if not name or sc.is_tech_exception(parent_path, name):
        return None
    base, ext = sc.split_ext(name, mime)
    ext = (rec.get("ext") or ext or "mp3").lower()
    meta = rec.get("metadata") or {}

    has_supp = " - " in base
    stem_main = base.split(" - ", 1)[0].strip() if has_supp else base.strip()
    existing_supp = re.sub(r'[\\/:*?"<>|\r\n]+', " ", base.split(" - ", 1)[1]).strip(" .-_") if has_supp else ""
    is_opaque = bool(OPAQUE_AUDIO_NAME_RE.match(stem_main))
    if has_supp and not is_opaque:
        return None

    title_raw = re.sub(r'[\\/:*?"<>|\r\n]+', " ", str(meta.get("title") or "")).strip()
    artist_raw = re.sub(r'[\\/:*?"<>|\r\n]+', " ", str(meta.get("artist") or "")).strip()
    album_raw = re.sub(r'[\\/:*?"<>|\r\n]+', " ", str(meta.get("album") or "")).strip()

    if is_opaque:
        if not title_raw:
            return None
        main = title_raw
    else:
        if not (artist_raw or album_raw):
            return None
        main = stem_main.replace("_", " ")

    main_title = sc.title_case_vn(re.sub(r"\s{2,}", " ", main)[:90])
    supp: List[str] = []
    if existing_supp:
        supp.append(existing_supp)
    else:
        if artist_raw and artist_raw.lower() not in main_title.lower():
            supp.append(sc.title_case_vn(artist_raw[:50]))
        if album_raw and album_raw.lower() not in main_title.lower() and album_raw.lower() not in (artist_raw or "").lower():
            supp.append(sc.title_case_vn(album_raw[:45]))
        if not supp and parent_path:
            last = re.sub(r"^\[\d{2,3}\]\s*", "", parent_path.split("/")[-1]).strip()
            if last:
                supp.append(sc.title_case_vn(last[:40]))
    if not supp:
        return None

    cand = f"{main_title} - {', '.join(supp)}.{ext}"
    if cand == name:
        return None
    return {
        "id": rec.get("id", ""),
        "old_name": name,
        "new_name": cand,
        "parent_path": parent_path,
        "reason": "Chuẩn hóa tên từ thẻ ID3/MP4",
    }


def apply_audio_rename_suggestions(suggestions: Sequence[Dict[str, str]], drive: sc.Drive, index: Optional[dict] = None, execute: bool = False) -> Dict[str, Any]:
    batch_id = f"aud_rename_{sc.now_stamp()}"
    if not execute:
        return {"batch_id": batch_id, "dry_run": True, "planned": len(suggestions), "renamed": 0, "items": list(suggestions)}
    results = drive.batch_rename([(s["id"], s["new_name"]) for s in suggestions if s.get("id") and s.get("new_name")])
    ok_ids = {fid for fid, ok, _ in results if ok}
    ops = [s for s in suggestions if s.get("id") in ok_ids]
    for op in ops:
        rec = load_cached_audio(op["id"])
        if rec:
            rec["name"] = op["new_name"]
            if rec.get("parent_path"):
                rec["path"] = f"{rec['parent_path']}/{op['new_name']}"
            save_cached_audio(rec)
    if index and ops:
        _, id_map = sc.build_id_map(index)
        for op in ops:
            if op["id"] in id_map:
                id_map[op["id"]][1]["name"] = op["new_name"]
        sc.save_index(index)
    if ops:
        log_data = sc.read_json(sc.media_rename_log_path(), default={"batches": []}) or {"batches": []}
        log_data["batches"].append({"batch_id": batch_id, "kind": "audio", "timestamp": sc.now_utc_iso(), "operations": ops})
        sc.write_json(sc.media_rename_log_path(), log_data)
    return {"batch_id": batch_id, "dry_run": False, "planned": len(suggestions), "renamed": len(ops), "items": ops}


def undo_audio_rename_batch(batch_id: Optional[str], drive: sc.Drive, index: Optional[dict] = None) -> int:
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
# 5. TỔNG HỢP & BÁO CÁO
# ---------------------------------------------------------------------------

def summarize_audio(records: Sequence[Dict[str, Any]], index: Optional[dict] = None, branch: Optional[str] = None, min_cosine: float = 0.92) -> Dict[str, Any]:
    by_ext: Dict[str, int] = collections.Counter()
    by_role: Dict[str, int] = collections.Counter()
    by_flag: Dict[str, int] = collections.Counter()
    suggestions: List[Dict[str, str]] = []
    total_bytes = 0
    total_sec = 0.0

    for r in records:
        total_bytes += int(r.get("size") or 0)
        total_sec += float((r.get("stats") or {}).get("duration_sec") or 0.0)
        by_ext[r.get("ext") or "?"] += 1
        by_role[r.get("role") or "am_thanh_khac"] += 1
        for fl in r.get("flags") or []:
            by_flag[fl] += 1
        sug = suggest_audio_v6_name(r)
        if sug:
            suggestions.append(sug)

    dups = find_audio_duplicates(records, min_cosine=min_cosine)
    seq_gaps = audit_audio_sequences(index, branch=branch) if index else []
    return {
        "total": len(records),
        "total_bytes": total_bytes,
        "total_duration_hours": round(total_sec / 3600.0, 2),
        "by_ext": dict(by_ext),
        "by_role": dict(by_role),
        "by_flag": dict(by_flag),
        "rename_suggestions": suggestions,
        "duplicates": dups,
        "sequence_gaps": seq_gaps,
        "records": list(records),
    }


def write_audio_reports(summary: Dict[str, Any], branch: Optional[str] = None) -> Tuple[Path, Path]:
    today = sc.today_vn()
    md_p = sc.reports_dir() / f"Báo Cáo Phân Tích Âm Thanh - Storage, {today}.md"
    csv_p = sc.reports_dir() / f"Báo Cáo Phân Tích Âm Thanh - Storage, {today}.csv"

    dups = summary["duplicates"]
    gaps = summary["sequence_gaps"]
    sugs = summary["rename_suggestions"]
    sec_no = 1
    lines = [
        f"# BÁO CÁO PHÂN TÍCH ÂM THANH & PHỔ TÍN HIỆU — [A] STORAGE ({today})",
        "",
        f"- **Phạm vi nhánh**: `{sc.normalize_branch(branch) or sc.ROOT_NAME}`",
        f"- **Số tệp âm thanh đã phân tích**: **{sc.fmt_int(summary['total'])}** ({sc.human_size(summary['total_bytes'])}, tổng thời lượng **{summary['total_duration_hours']} giờ**)",
        f"- **Trùng nội dung**: **{len(dups['exact_groups'])}** nhóm SHA-256, **{len(dups['acoustic_groups'])}** nhóm vân tay âm học",
        f"- **Thư mục có lỗ hổng chuỗi bài**: **{len(gaps)}** | **Gợi ý đổi tên V6**: **{len(sugs)}**",
        "",
        f"## {sec_no}. Phân bố Định Dạng & Vai Trò",
        "",
        sc.md_table(["Vai trò âm thanh", "Số tệp"], sorted(summary["by_role"].items(), key=lambda x: -x[1]), ["l", "r"]),
        "",
    ]
    sec_no += 1
    if summary["by_flag"]:
        lines += [
            f"## {sec_no}. Thống kê Cờ Chất Lượng Tín Hiệu",
            "",
            sc.md_table(["Cờ cảnh báo", "Số tệp"], sorted(summary["by_flag"].items(), key=lambda x: -x[1]), ["l", "r"]),
            "",
        ]
        sec_no += 1
    if gaps:
        lines += [
            f"## {sec_no}. Kiểm Toán Chuỗi Bài Nghe Bị Thiếu Số (tối đa 30 thư mục)",
            "",
            sc.md_table(
                ["Thư mục", "Số tệp", "Dải số", "Số bài thiếu (mẫu)"],
                [[g["path"], g["audio_count"], g["range"], ", ".join(str(x) for x in g["missing_numbers"][:10])] for g in gaps[:30]],
                ["l", "r", "c", "l"],
            ),
            "",
        ]
        sec_no += 1
    if dups["pairs"]:
        lines += [
            f"## {sec_no}. Cặp Âm Thanh Trùng Vân Tay Âm Học",
            "",
            sc.md_table(
                ["Tương đồng", "Lệch thời lượng", "Tệp A", "Tệp B"],
                [[f"{p['cosine_pct']}%", f"{p['dur_diff_sec']}s", p["a"]["name"], p["b"]["name"]] for p in dups["pairs"][:25]],
                ["r", "r", "l", "l"],
            ),
            "",
        ]
        sec_no += 1

    rows_sample = []
    for r in summary["records"][:60]:
        st = r.get("stats") or {}
        sg = r.get("signal") or {}
        rows_sample.append([
            r.get("name", ""), st.get("duration_sec", ""), f"{st.get('bitrate_kbps', '')} kbps",
            sg.get("integrated_lufs", ""), sg.get("max_volume_db", ""), f"{sg.get('silence_ratio_pct', 0)}%",
            r.get("role", ""), ", ".join(r.get("flags") or []),
        ])
    if rows_sample:
        lines += [
            f"## {sec_no}. Chi Tiết Mẫu Âm Thanh (tối đa 60 tệp)",
            "",
            sc.md_table(["Tên tệp", "Thời lượng (s)", "Bitrate", "LUFS", "Peak (dB)", "Im lặng", "Vai trò", "Cờ"], rows_sample),
            "",
        ]
    md_p.write_text("\n".join(lines), encoding="utf-8")

    csv_rows = []
    for r in summary["records"]:
        st = r.get("stats") or {}
        sg = r.get("signal") or {}
        m = r.get("metadata") or {}
        csv_rows.append([
            r.get("id", ""), r.get("name", ""), r.get("path", ""), r.get("ext", ""), r.get("status", ""),
            r.get("size", 0), st.get("duration_sec", ""), st.get("bitrate_kbps", ""), st.get("sample_rate_hz", ""),
            st.get("channels", ""), st.get("audio_codec", ""), sg.get("integrated_lufs", ""), sg.get("lra_lu", ""),
            sg.get("mean_volume_db", ""), sg.get("max_volume_db", ""), sg.get("silence_ratio_pct", ""),
            m.get("title", ""), m.get("artist", ""), m.get("album", ""), r.get("role", ""),
            (r.get("fingerprint") or {}).get("hash", ""), ", ".join(r.get("flags") or []),
        ])
    sc.write_csv(
        csv_p,
        [
            "ID", "Tên tệp", "Đường dẫn", "Đuôi", "Trạng thái", "Dung lượng (B)", "Thời lượng (s)",
            "Bitrate (kbps)", "Sample Rate", "Kênh", "Codec", "LUFS", "LRA (LU)", "Mean dB", "Peak dB",
            "Tỷ lệ im lặng (%)", "Title (ID3)", "Artist (ID3)", "Album (ID3)", "Vai trò", "AudioHash", "Cờ",
        ],
        csv_rows,
    )
    return md_p, csv_p


def main() -> None:
    ap = argparse.ArgumentParser(description="Phân tích âm thanh, phổ LUFS, khoảng lặng & vân tay âm học (v3.3).")
    ap.add_argument("lenh", nargs="?", default="phan-tich", choices=["phan-tich", "doc", "trung-am-thanh", "kiem-tra-chuoi", "goi-y-ten", "hoan-tac-ten"])
    ap.add_argument("muc_tieu", nargs="?", help="Đường dẫn cục bộ hoặc Drive ID/URL cho lệnh `doc`.")
    ap.add_argument("--nhanh", help="Giới hạn phạm vi nhánh.")
    ap.add_argument("--tu-dong-doc", action="store_true", help="Tải & phân tích các tệp audio chưa có trong media_cache.")
    ap.add_argument("--chi-chi-muc", action="store_true", help="Chỉ kiểm toán chuỗi bài trên storage_index.json (không tải tệp).")
    ap.add_argument("--max-mb", type=float, default=100.0, help="Giới hạn dung lượng tối đa mỗi tệp (mặc định 100 MB).")
    ap.add_argument("--gioi-han", type=int, default=30, help="Số tệp tối đa mỗi lô (mặc định 30).")
    ap.add_argument("--luong", type=int, default=3, help="Số luồng xử lý song song.")
    ap.add_argument("--nguong-tuong-dong", type=float, default=0.92, help="Ngưỡng tương đồng cosine vân tay âm học (0.92).")
    ap.add_argument("--gom-trung", action="store_true", help="Lập kế hoạch cách ly tệp âm thanh trùng vào [07] KIỂM TRA.")
    ap.add_argument("--ma-lo", help="Mã lô cần hoàn tác.")
    ap.add_argument("--thuc-thi", action="store_true", help="Thực sự đổi tên/di chuyển trên Google Drive.")
    ap.add_argument("--dong-y", action="store_true", help="Không hỏi xác nhận khi --thuc-thi.")
    ap.add_argument("--tai-len", action="store_true", help="Tải báo cáo lên [00] TỔNG QUAN/[02] NHẬT KÍ.")
    args = ap.parse_args()

    if args.lenh == "doc":
        if not args.muc_tieu:
            raise SystemExit("Truyền đường dẫn audio cục bộ hoặc ID/URL Google Drive.")
        p_local = Path(args.muc_tieu).expanduser()
        if p_local.exists():
            rec = analyze_local_audio(p_local)
        else:
            fid = sc.extract_drive_id(args.muc_tieu)
            drive = sc.create_drive()
            index = sc.load_index(required=False)
            _, id_map = sc.build_id_map(index) if index else ({}, {})
            pp, item = id_map[fid] if fid in id_map else ("", drive.info(fid))
            rec = analyze_drive_audio(item, pp, drive, force_refresh=True, max_mb=args.max_mb)
        sc.log(f"🎵 {rec.get('name', args.muc_tieu)} | trạng thái={rec.get('status')} | vai trò={rec.get('role')}")
        sc.log(f"   • Luồng    : {rec.get('stats')}")
        sc.log(f"   • Tín hiệu : {rec.get('signal')}")
        sc.log(f"   • Thẻ tag  : {rec.get('metadata')} | Cờ: {rec.get('flags')}")
        return

    index = sc.load_index(required=False)
    if args.lenh == "hoan-tac-ten":
        n = undo_audio_rename_batch(args.ma_lo, sc.create_drive(), index=index)
        sc.log(f"↩️  Đã hoàn tác {n} mục đổi tên âm thanh.")
        return

    if args.lenh == "kiem-tra-chuoi" or args.chi_chi_muc:
        if not index:
            raise SystemExit("Chưa có storage_index.json.")
        gaps = audit_audio_sequences(index, branch=args.nhanh)
        sc.log(f"🔢 Kiểm toán chuỗi bài âm thanh: phát hiện {len(gaps)} thư mục có lỗ hổng đánh số.")
        for g in gaps[:30]:
            sc.log(f" • {g['path']} ({g['audio_count']} tệp, dải {g['range']}): thiếu {g['missing_numbers']}")
        if args.lenh == "kiem-tra-chuoi":
            return

    if args.tu_dong_doc and index:
        batch_analyze_audio(index, sc.create_drive(), branch=args.nhanh, max_mb=args.max_mb, limit=args.gioi_han, workers=args.luong)

    recs = iter_cached_audio(branch=args.nhanh, index=index)
    summary = summarize_audio(recs, index=index, branch=args.nhanh, min_cosine=args.nguong_tuong_dong)

    if args.lenh == "trung-am-thanh":
        dups = summary["duplicates"]
        sc.log(f"🎧 Trùng âm thanh: {len(dups['exact_groups'])} nhóm SHA-256, {len(dups['acoustic_groups'])} nhóm vân tay âm học.")
        for p in dups["pairs"][:20]:
            sc.log(f" • [{p['cosine_pct']}% | lệch {p['dur_diff_sec']}s] {p['a']['name']}  <~>  {p['b']['name']}")
        if args.gom_trung:
            preview = quarantine_audio_duplicates(dups, sc.create_drive(), index=index, execute=False)
            do_exec = bool(args.thuc_thi and preview["planned"] > 0 and sc.confirm(f"Cách ly {preview['planned']} âm thanh trùng vào [07] KIỂM TRA?", assume_yes=args.dong_y))
            qres = quarantine_audio_duplicates(dups, sc.create_drive(), index=index, execute=do_exec) if do_exec else preview
            sc.log(f"📦 Cách ly âm thanh trùng: dự kiến={qres['planned']}, đã chuyển={qres['moved']}, dry_run={qres['dry_run']}")
        return

    if args.lenh == "goi-y-ten":
        sugs = summary["rename_suggestions"]
        sc.log(f"🏷️  Gợi ý chuẩn hóa tên cho {len(sugs)} tệp âm thanh:")
        for s in sugs[:30]:
            sc.log(f" • {s['old_name']}  →  {s['new_name']} ({s['id']})")
        if args.thuc_thi and sugs and sc.confirm(f"Đổi tên {len(sugs)} tệp âm thanh trên Drive?", assume_yes=args.dong_y):
            res = apply_audio_rename_suggestions(sugs, sc.create_drive(), index=index, execute=True)
            sc.log(f"✅ Đã đổi tên {res['renamed']}/{res['planned']} tệp âm thanh (lô {res['batch_id']}).")
        return

    md_p, csv_p = write_audio_reports(summary, branch=args.nhanh)
    sc.log(f"🎵 Đã phân tích {summary['total']} âm thanh | cờ={summary['by_flag']} | lỗ hổng chuỗi={len(summary['sequence_gaps'])}")
    sc.log(f"📝 Báo cáo MD : {md_p}")
    sc.log(f"📝 Báo cáo CSV: {csv_p}")
    if args.tai_len:
        drive = sc.create_drive()
        sc.publish_file(drive, md_p, sc.nhat_ki_id())
        sc.publish_file(drive, csv_p, sc.nhat_ki_id())
        sc.log("☁️  Đã tải báo cáo phân tích âm thanh lên [02] NHẬT KÍ.")


if __name__ == "__main__":
    main()
