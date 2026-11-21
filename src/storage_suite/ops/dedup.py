#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RÀ SOÁT TRÙNG LẶP, TỔNG QUAN TRÙNG, SHORTCUT VÀ THƯ MỤC RỖNG — [A] STORAGE (v2.0)
=================================================================================
Phân loại chính xác theo Chuẩn V6, chống dương tính giả:
1. `trung_chac_chan`: cùng dung lượng + cùng tên chuẩn hóa (tách biệt hẳn `Phần 01`/`Phần 02`
   khỏi marker bản sao `Bản 01`, `(1)`, `Copy`).
2. `trung_phien_ban`: cùng dung lượng + chỉ khác hậu tố `Phiên Bản 1`/`Phiên Bản 2`
   (chỉ cách ly khi truyền `--gom-phien-ban`, mặc định kiểm tra SHA-256).
3. `duplicate_tongquan`: các thư mục `[00] TỔNG QUAN` có >1 tệp `TongQuan.md` cùng nội dung
   (cách ly khi truyền `--gom-tong-quan-trung` vào `[99] KIỂM TRA/[03] TỆP TRÙNG LẶP/[01] TỔNG QUAN TRÙNG LẶP`).
4. `nghi_can_duyet`: cùng dung lượng ≥ 1 MB + cùng đuôi (bao gồm `Phần`/`Tập`/`Số` khác nhau) — chỉ báo cáo.
5. `shortcut`: đọc `shortcut_cache.json` theo `modifiedTime`, chỉ gọi Drive cho mục mới/biến động.
6. `thu_muc_rong`: duyệt *bottom-up* phát hiện cả thư mục rỗng lồng nhau.
7. Kiểm tra quyền `capabilities` (`canMoveItemOutOfDrive,canEdit`) trước khi di chuyển (`KHONG_CO_QUYEN`).
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import re
import tempfile
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


from storage_suite import core as sc

_Q_CFG = sc.CONFIG.get("quarantine_subfolders", {})
QUARANTINE = {
    "duplicate": _Q_CFG.get("duplicate", "[03] TỆP TRÙNG LẶP"),
    "duplicate_tongquan": _Q_CFG.get("duplicate_tongquan", "[01] TỔNG QUAN TRÙNG LẶP"),
    "broken_shortcut": _Q_CFG.get("broken_shortcut", "[01] SHORTCUT LỖI 404"),
    "redundant_shortcut": _Q_CFG.get("redundant_shortcut", "[02] SHORTCUT ĐÃ SAO CHÉP"),
    "system_junk": _Q_CFG.get("system_junk", "[06] RÁC HỆ THỐNG"),
}

_DEDUP_CFG = sc.CONFIG.get("dedup", {})
EXCLUDE_MARKERS = tuple(_DEDUP_CFG.get("exclude_markers", (
    "[A] STORAGE/[99] KIỂM TRA", "/[00] TỔNG QUAN", ".obsidian", "MÃ NGUỒN PYTHON", "DỰ ÁN SỐ HÓA",
    "[00] TỔNG QUAN/[03] QUẢN LÝ",
)))
DEFAULT_MIN_SUSPECT = int(_DEDUP_CFG.get("min_suspect_bytes", 1024 * 1024))

# Tuyệt đối KHÔNG gộp `phần|phan|tập|số|phiên bản` vào dấu hiệu bản sao chắc chắn
EXACT_COPY_RE = re.compile(
    r"(,?\s*(?<!phien )(?:ban)\s*\d{1,3}$)|(\(\d{1,3}\)$)|(^copy of\s+)|(\s+copy$)|"
    r"(^ban sao cua\s+)|(\s*-\s*copy$)",
    re.I,
)
VERSION_MARKER_RE = re.compile(r",?\s*(?:phien ban)\s*(\d{1,3})\s*$", re.I)
PART_MARKER_RE = re.compile(
    r"\b(phan|tap|quyen|chuong|buoi|bai|so|part|vol(?:ume)?|chap(?:ter)?|ep(?:isode)?)\s*(\d+)\b",
    re.I,
)


def excluded(path: str) -> bool:
    return sc.is_quarantine_path(path) or any(m in path for m in EXCLUDE_MARKERS)


def _strip_ascii(text: str) -> str:
    return sc.strip_accents(sc.nfc(text)).lower().strip()


def extract_part_sig(name: str, mime: str = "") -> Tuple[Tuple[str, int], ...]:
    base, _ = sc.split_ext(name, mime)
    b = _strip_ascii(base)
    return tuple((m.group(1), int(m.group(2))) for m in PART_MARKER_RE.finditer(b))


def has_version_marker(name: str, mime: str = "") -> bool:
    base, _ = sc.split_ext(name, mime)
    return bool(VERSION_MARKER_RE.search(_strip_ascii(base)))


def has_copy_marker(name: str, mime: str = "") -> bool:
    base, _ = sc.split_ext(name, mime)
    return bool(EXACT_COPY_RE.search(_strip_ascii(base)))


def norm_key(name: str, mime: str = "", strip_version: bool = False) -> Tuple[str, str]:
    base, ext = sc.split_ext(name, mime)
    b = _strip_ascii(base)
    prev = None
    while prev != b:
        prev = b
        b = EXACT_COPY_RE.sub("", b).strip(" ,-_")
        if strip_version:
            b = VERSION_MARKER_RE.sub("", b).strip(" ,-_")
    b = re.sub(r"[^a-z0-9]+", "", b)
    return b, ext.lower()


def pick_original(group: List[Tuple[str, dict]]) -> Tuple[str, dict]:
    """Giữ bản: không có dấu hiệu bản sao/phiên bản phụ > sửa đổi sớm nhất > đường dẫn nông nhất > tên ngắn nhất."""
    return sorted(
        group,
        key=lambda x: (
            has_copy_marker(x[1]["name"], x[1].get("mimeType", "")),
            has_version_marker(x[1]["name"], x[1].get("mimeType", "")),
            x[1].get("modifiedTime", "9999"),
            x[0].count("/"),
            len(x[1]["name"]),
            x[1]["id"],
        ),
    )[0]


def _uniform_parts(group: List[Tuple[str, dict]]) -> bool:
    sigs = {extract_part_sig(it["name"], it.get("mimeType", "")) for _, it in group}
    return len(sigs) <= 1


def find_duplicates(index: dict, branch: Optional[str] = None, min_suspect: int = DEFAULT_MIN_SUSPECT):
    """Trả về `(certain, version_dups, suspect)`."""
    by_size = defaultdict(list)
    for path, it in sc.iter_items(index, branch):
        if it["mimeType"] == sc.FOLDER_MIME or it["mimeType"] in sc.GOOGLE_NATIVE_MIMES or excluded(path):
            continue
        size = it.get("size") or 0
        if size <= 0:
            continue
        by_size[size].append((path, it))

    certain, version_dups, suspect = [], [], []
    for size, items in by_size.items():
        if len(items) < 2:
            continue
        by_key = defaultdict(list)
        for p, it in items:
            by_key[norm_key(it["name"], it["mimeType"], strip_version=False)].append((p, it))

        leftovers = []
        for key, grp in by_key.items():
            if len(grp) > 1 and key[0] and _uniform_parts(grp):
                keep = pick_original(grp)
                certain.append({
                    "size": size,
                    "kind": "duplicate",
                    "keep": keep,
                    "extra": [g for g in grp if g is not keep],
                })
            else:
                leftovers.extend(grp)

        # Kiểm tra nhóm `Phiên Bản 1` / `Phiên Bản 2` từ phần còn lại
        still_left = []
        if len(leftovers) > 1:
            by_ver_key = defaultdict(list)
            for p, it in leftovers:
                by_ver_key[norm_key(it["name"], it["mimeType"], strip_version=True)].append((p, it))
            for key, grp in by_ver_key.items():
                if (
                    len(grp) > 1
                    and key[0]
                    and any(has_version_marker(it["name"], it["mimeType"]) for _, it in grp)
                    and _uniform_parts(grp)
                ):
                    keep = pick_original(grp)
                    version_dups.append({
                        "size": size,
                        "kind": "version_duplicate",
                        "keep": keep,
                        "extra": [g for g in grp if g is not keep],
                    })
                else:
                    still_left.extend(grp)

        if size >= min_suspect and len(still_left) > 1:
            by_ext = defaultdict(list)
            for p, it in still_left:
                by_ext[norm_key(it["name"], it["mimeType"])[1]].append((p, it))
            for _, grp in by_ext.items():
                if len(grp) > 1:
                    suspect.append({"size": size, "items": grp})

    certain.sort(key=lambda g: -g["size"] * len(g["extra"]))
    version_dups.sort(key=lambda g: -g["size"] * len(g["extra"]))
    suspect.sort(key=lambda g: -g["size"])
    return certain, version_dups, suspect


def find_duplicate_tongquan(index: dict, branch: Optional[str] = None) -> List[dict]:
    """Tìm các thư mục `[00] TỔNG QUAN` có >1 tệp `TongQuan.md` cùng kích thước."""
    groups = []
    prefix = (branch.rstrip("/") + "/") if branch else ""
    for path, data in sorted(index.items()):
        if branch and not (path == branch or path.startswith(prefix)):
            continue
        if sc.is_quarantine_path(path) or ".obsidian" in path or "[03] QUẢN LÝ" in path:
            continue
        if not path.endswith("/" + sc.TONG_QUAN_FOLDER):
            continue
        tqs = [
            it for it in data.get("items", [])
            if it.get("mimeType") != sc.FOLDER_MIME and it.get("name") == "TongQuan.md"
        ]
        if len(tqs) < 2:
            continue
        by_sz = defaultdict(list)
        for it in tqs:
            by_sz[int(it.get("size") or 0)].append((path, it))
        for sz, grp in by_sz.items():
            if len(grp) > 1:
                keep = pick_original(grp)
                groups.append({
                    "size": sz,
                    "kind": "duplicate_tongquan",
                    "keep": keep,
                    "extra": [g for g in grp if g is not keep],
                })
    return groups


def verify_groups_sha256(
    groups: List[dict],
    drive: Optional[sc.Drive] = None,
    max_mb: float = 50.0,
    workers: int = 12,
    require_verified: bool = True,
) -> Tuple[List[dict], List[dict]]:
    """
    Xác minh mã băm SHA-256 trước khi đưa vào diện cách ly.
    Trả về `(nhom_dat_xac_minh, danh_sach_loai_hoac_bo_qua)`.
    """
    if not groups:
        return [], []
    drive = drive or sc.create_drive(retries=4)
    max_bytes = int(max_mb * 1024 * 1024)
    to_hash: Dict[str, Tuple[str, dict]] = {}
    verified_groups: List[dict] = []
    rejected: List[dict] = []

    eligible: List[dict] = []
    for g in groups:
        if g["size"] <= 0 or g["size"] > max_bytes:
            if not require_verified:
                verified_groups.append(g)
            else:
                rejected.append({"group": g, "reason": f"vuot_gioi_han_{max_mb}MB"})
            continue
        eligible.append(g)
        kp, kit = g["keep"]
        to_hash[kit["id"]] = (kp, kit)
        for ep, eit in g["extra"]:
            to_hash[eit["id"]] = (ep, eit)

    if not eligible:
        return verified_groups, rejected

    hashes: Dict[str, Optional[str]] = {}
    with tempfile.TemporaryDirectory(prefix="dedup_sha256_") as tmp_dir:
        tmp_root = Path(tmp_dir)

        def hash_one(item_tuple: Tuple[str, Tuple[str, dict]]) -> Tuple[str, Optional[str]]:
            fid, (_, it) = item_tuple
            out = tmp_root / fid
            try:
                drive.download(fid, out)
                digest = sc.sha256_file(out)
                return fid, digest
            except Exception:
                return fid, None
            finally:
                try:
                    out.unlink()
                except OSError:
                    pass

        with cf.ThreadPoolExecutor(max_workers=workers) as pool:
            for n, (fid, dig) in enumerate(pool.map(hash_one, to_hash.items()), 1):
                hashes[fid] = dig
                if n % 100 == 0:
                    sc.log(f"  → Đã băm SHA-256 {n}/{len(to_hash)} tệp...")

    for g in eligible:
        kp, kit = g["keep"]
        keep_hash = hashes.get(kit["id"])
        if not keep_hash:
            if not require_verified:
                verified_groups.append(g)
            else:
                rejected.append({"group": g, "reason": "loi_tai_ban_giu"})
            continue
        matched_extra = []
        mismatched = []
        for ep, eit in g["extra"]:
            ehash = hashes.get(eit["id"])
            if ehash == keep_hash:
                matched_extra.append((ep, eit))
            elif ehash is None:
                if not require_verified:
                    matched_extra.append((ep, eit))
                else:
                    mismatched.append((ep, eit, "loi_tai_ban_phu"))
            else:
                mismatched.append((ep, eit, f"khac_sha256 ({ehash[:12]} != {keep_hash[:12]})"))
        if matched_extra:
            ng = dict(g)
            ng["extra"] = matched_extra
            ng["sha256"] = keep_hash
            verified_groups.append(ng)
        if mismatched:
            rejected.append({"group": g, "reason": "khac_noi_dung_hoac_loi", "items": mismatched})

    return verified_groups, rejected


def find_shortcuts(index: dict, branch: Optional[str] = None) -> List[Tuple[str, dict]]:
    return [
        (p, it) for p, it in sc.iter_items(index, branch)
        if it["mimeType"] == sc.SHORTCUT_MIME and not sc.is_quarantine_path(p)
    ]


def check_shortcuts(
    shortcuts: List[Tuple[str, dict]],
    index: dict,
    workers: int = 12,
    drive: Optional[sc.Drive] = None,
):
    """
    Kiểm tra đích shortcut, tận dụng `shortcut_cache.json` theo `modifiedTime` và `stream_info`.
    Phân loại: `ok` / `broken` / `redundant` / `unknown`.
    """
    drive = drive or sc.create_drive(retries=3)
    cache_p = sc.shortcut_cache_path()
    cache = sc.read_json(cache_p, {}) or {}
    real_ids = {it["id"] for _, it in sc.iter_items(index) if it["mimeType"] != sc.SHORTCUT_MIME}
    real_names = defaultdict(set)
    for _, it in sc.iter_items(index):
        if it["mimeType"] not in (sc.SHORTCUT_MIME, sc.FOLDER_MIME):
            real_names[(norm_key(it["name"], it["mimeType"])[0], it.get("size"))].add(it["id"])

    def eval_cached(pair, entry):
        tid = entry.get("targetId", "")
        if not tid:
            return None
        if tid in real_ids:
            return pair, "redundant", tid, "Đích nằm ngay trong kho (cache)"
        st = entry.get("targetStatus")
        if st == "broken":
            return pair, "broken", tid, "404 — đích không tồn tại / không có quyền (cache)"
        if st == "trashed":
            return pair, "broken", tid, "Đích đã nằm trong Thùng rác (cache)"
        if st == "ok":
            key = (norm_key(entry.get("targetName", ""), entry.get("targetMime", ""))[0], entry.get("targetSize"))
            if key[0] and key in real_names:
                return pair, "redundant", tid, "Đã có bản sao thật trong kho (cache)"
            return pair, "ok", tid, entry.get("targetName", "")
        return None

    cached_results = {}
    need_fetch = []
    for pair in shortcuts:
        _, it = pair
        c_entry = cache.get(it["id"])
        if c_entry and c_entry.get("modifiedTime") == it.get("modifiedTime"):
            res = eval_cached(pair, c_entry)
            if res is not None:
                cached_results[it["id"]] = res
                continue
        need_fetch.append(pair)

    sc.log(f"Shortcut: {len(cached_results)} lấy từ cache | {len(need_fetch)} cần hỏi Drive")

    sc_info_pre = drive.stream_info([it["id"] for _, it in need_fetch], concurrency=max(16, workers)) if (need_fetch and hasattr(drive, "stream_info")) else {}
    ext_tids = [
        (sc_info_pre.get(it["id"], {}).get("shortcutDetails") or {}).get("targetId", "")
        for _, it in need_fetch
    ]
    ext_tids = [tid for tid in ext_tids if tid and tid not in real_ids]
    target_info_pre = drive.stream_info(ext_tids, concurrency=max(16, workers)) if (ext_tids and hasattr(drive, "stream_info")) else {}

    def job(pair):
        _, it = pair
        info = sc_info_pre.get(it["id"])
        if info is None:
            try:
                info = drive.info(it["id"])
            except sc.DriveError as e:
                return pair, "unknown", "", str(e)[:200], None
        det = info.get("shortcutDetails") or {}
        tid = det.get("targetId")
        if not tid:
            return pair, "unknown", "", "CLI không trả về shortcutDetails", None
        rec = {"modifiedTime": it.get("modifiedTime"), "targetId": tid, "targetMimeType": det.get("targetMimeType", "")}
        if tid in real_ids:
            rec["targetStatus"] = "ok"
            return pair, "redundant", tid, "Đích nằm ngay trong kho", rec
        tinfo = target_info_pre.get(tid)
        if tinfo is None:
            try:
                tinfo = drive.info(tid)
            except sc.DriveError as e:
                msg = str(e)
                if "404" in msg or "notFound" in msg or "File not found" in msg:
                    rec["targetStatus"] = "broken"
                    return pair, "broken", tid, "404 — đích không tồn tại / không có quyền", rec
                rec["targetStatus"] = "error"
                return pair, "unknown", tid, msg[:200], rec
        if tinfo.get("trashed"):
            rec["targetStatus"] = "trashed"
            return pair, "broken", tid, "Đích đã nằm trong Thùng rác", rec
        rec["targetName"] = tinfo.get("name", "")
        rec["targetSize"] = int(tinfo["size"]) if tinfo.get("size") else None
        rec["targetMime"] = tinfo.get("mimeType", "")
        rec["targetStatus"] = "ok"
        key = (norm_key(rec["targetName"], rec["targetMime"])[0], rec["targetSize"])
        if key[0] and key in real_names:
            return pair, "redundant", tid, "Đã có bản sao thật trong kho", rec
        return pair, "ok", tid, rec["targetName"], rec

    fetched_results = {}
    if need_fetch:
        with cf.ThreadPoolExecutor(max_workers=workers) as pool:
            for n, (pair, st, tid, note, rec) in enumerate(pool.map(job, need_fetch), 1):
                fetched_results[pair[1]["id"]] = (pair, st, tid, note)
                if rec is not None:
                    cache[pair[1]["id"]] = rec
                if n % 50 == 0:
                    sc.log(f"  → đã kiểm tra {n}/{len(need_fetch)} shortcut mới")
        sc.write_json(cache_p, cache, indent=None)

    return [
        cached_results[it["id"]] if it["id"] in cached_results else fetched_results[it["id"]]
        for _, it in shortcuts
    ]


def find_empty_folders_detailed(index: dict, branch: Optional[str] = None) -> List[Tuple[str, str, bool]]:
    """
    Duyệt từ sâu ra nông (*bottom-up*) để tìm cả thư mục rỗng trực tiếp và thư mục chỉ chứa thư mục con rỗng.
    Trả về `[(path, id, is_nested)]`.
    """
    empty_set: Set[str] = set()
    results: List[Tuple[str, str, bool]] = []
    prefix = (branch.rstrip("/") + "/") if branch else ""

    for path in sorted(index.keys(), key=lambda p: (-p.count("/"), p)):
        if path == sc.ROOT_NAME:
            continue
        if excluded(path + "/"):
            continue
        data = index[path]
        items = [it for it in data.get("items", []) if it.get("name") != sc.TONG_QUAN_FOLDER]
        has_files = any(it.get("mimeType") != sc.FOLDER_MIME for it in items)
        if has_files:
            continue
        subfolders = [it for it in items if it.get("mimeType") == sc.FOLDER_MIME]
        if not subfolders:
            empty_set.add(path)
            if not branch or path == branch or path.startswith(prefix):
                results.append((path, data.get("id", ""), False))
        elif all(f"{path}/{sf['name']}" in empty_set for sf in subfolders):
            empty_set.add(path)
            if not branch or path == branch or path.startswith(prefix):
                results.append((path, data.get("id", ""), True))

    return sorted(results, key=lambda x: x[0])


def find_empty_folders(index: dict, branch: Optional[str] = None) -> List[Tuple[str, str]]:
    return [(p, fid) for p, fid, _ in find_empty_folders_detailed(index, branch)]


def quarantine_moves(
    certain: List[dict],
    version_dups: Optional[List[dict]] = None,
    dup_tongquan: Optional[List[dict]] = None,
    sc_results=None,
) -> List[dict]:
    moves = []
    for grp_list in (certain or [], version_dups or []):
        for g in grp_list:
            for p, it in g["extra"]:
                rec = {
                    "id": it["id"],
                    "name": it["name"],
                    "from_path": p,
                    "kind": "duplicate",
                    "subkind": g.get("kind", "duplicate"),
                    "keep_id": g["keep"][1]["id"],
                    "keep_path": g["keep"][0],
                }
                if g.get("sha256"):
                    rec["sha256"] = g["sha256"]
                moves.append(rec)
    for g in dup_tongquan or []:
        for p, it in g["extra"]:
            rec = {
                "id": it["id"],
                "name": it["name"],
                "from_path": p,
                "kind": "duplicate_tongquan",
                "subkind": "duplicate_tongquan",
                "keep_id": g["keep"][1]["id"],
                "keep_path": g["keep"][0],
            }
            if g.get("sha256"):
                rec["sha256"] = g["sha256"]
            moves.append(rec)
    for (p, it), status, tid, note in sc_results or []:
        if status == "broken":
            moves.append({
                "id": it["id"], "name": it["name"], "from_path": p,
                "kind": "broken_shortcut", "note": note,
            })
        elif status == "redundant":
            moves.append({
                "id": it["id"], "name": it["name"], "from_path": p,
                "kind": "redundant_shortcut", "note": note, "target_id": tid,
            })
    return moves


def check_capabilities(
    moves: List[dict],
    drive: Optional[sc.Drive] = None,
    workers: int = 12,
) -> Tuple[List[dict], List[dict]]:
    """Kiểm tra quyền trước khi di chuyển (`KHONG_CO_QUYEN` tách riêng thay vì lỗi 403 giữa chừng)."""
    if not moves:
        return [], []
    drive = drive or sc.create_drive(retries=3)
    allowed, blocked = [], []
    caps_map = (
        drive.stream_capabilities([m["id"] for m in moves], "canMoveItemOutOfDrive,canEdit", concurrency=max(16, workers))
        if hasattr(drive, "stream_capabilities")
        else {}
    )

    def one(m: dict):
        caps = caps_map.get(m["id"])
        if caps is None:
            try:
                caps = drive.capabilities(m["id"], "canMoveItemOutOfDrive,canEdit")
            except sc.DriveError as e:
                return m, True, f"skip_check:{str(e)[:80]}"
        if caps and caps.get("canMoveItemOutOfDrive") is False:
            return m, False, "canMoveItemOutOfDrive=False (khác chủ sở hữu/thiếu quyền)"
        if caps and "canMoveItemOutOfDrive" not in caps and caps.get("canEdit") is False:
            return m, False, "canEdit=False"
        return m, True, ""

    with cf.ThreadPoolExecutor(max_workers=min(workers, len(moves))) as pool:
        for m, ok, note in pool.map(one, moves):
            if ok:
                allowed.append(m)
            else:
                bm = dict(m)
                bm["permission_error"] = note
                blocked.append(bm)
    return allowed, blocked


def _resolve_quarantine_destinations(drive: sc.Drive, kinds_needed: Set[str]) -> Dict[str, str]:
    kiem_tra = sc.quarantine_root_id()
    dest: Dict[str, str] = {}
    for k in ("duplicate", "broken_shortcut", "redundant_shortcut", "system_junk"):
        if k in kinds_needed or (k == "duplicate" and "duplicate_tongquan" in kinds_needed):
            dest[k] = drive.ensure_folder(QUARANTINE[k], kiem_tra)
    if "duplicate_tongquan" in kinds_needed:
        dest["duplicate_tongquan"] = drive.ensure_folder(QUARANTINE["duplicate_tongquan"], dest["duplicate"])
    return dest


def execute_moves(moves: List[dict], index: dict, workers: int = 8, drive: Optional[sc.Drive] = None) -> List[dict]:
    drive = drive or sc.create_drive()
    log_path = sc.data_dir() / "quarantine_log.json"
    qlog = sc.read_json(log_path, []) or []
    done_ids = {e["id"] for e in qlog if not e.get("restored")}

    pending = [m for m in moves if m["id"] not in done_ids]
    skipped_already = len(moves) - len(pending)
    if not pending:
        sc.log(f"Mọi mục ({skipped_already}) đều đã nằm trong nhật kí cách ly.")
        return []

    sc.log(f"Đang kiểm tra quyền thao tác cho {len(pending)} mục trước khi di chuyển...")
    allowed, blocked = check_capabilities(pending, drive=drive, workers=max(8, workers))
    if blocked:
        sc.log(f"[KHONG_CO_QUYEN] Phát hiện {len(blocked)} mục không có quyền di chuyển — bỏ qua an toàn.")
        sc.write_json(sc.data_dir() / "quarantine_permissions_blocked.json", blocked)

    if not allowed:
        sc.log("Không còn mục hợp lệ nào để di chuyển.")
        return blocked

    dest = _resolve_quarantine_destinations(drive, {m["kind"] for m in allowed})
    pairs = [(m["id"], dest[m["kind"]]) for m in allowed]
    by_id = {m["id"]: m for m in allowed}

    ok = fail = 0
    moved_ids: Set[str] = set()
    undo_actions: List[sc.UndoAction] = []
    results = drive.batch_move(pairs, workers=workers)
    for n, (fid, success, err) in enumerate(results, 1):
        m = by_id[fid]
        if success:
            ok += 1
            moved_ids.add(fid)
            from_id = m.get("from_parent_id") or index.get(m["from_path"], {}).get("id") or ""
            qlog.append({
                **m,
                "from_id": from_id,
                "to_id": dest[m["kind"]],
                "ts": int(time.time()),
            })
            undo_actions.append(
                sc.UndoAction(
                    op="quarantine_move",
                    item_id=fid,
                    old_name=m["name"],
                    new_name=m["name"],
                    old_parent_id=from_id,
                    new_parent_id=dest[m["kind"]],
                    path=m.get("from_path", ""),
                    extra={"kind": m["kind"], "subkind": m.get("subkind", m["kind"])},
                )
            )
        else:
            fail += 1
            if "403" in err or "insufficientFilePermissions" in err or "cannotMove" in err:
                bm = dict(m)
                bm["permission_error"] = f"KHONG_CO_QUYEN: {err[:160]}"
                blocked.append(bm)
            sc.log(f"  ! {m['name']}: {err[:200]}")
        if n % 100 == 0:
            sc.write_json(log_path, qlog)
    sc.write_json(log_path, qlog)
    batch_id = ""
    if undo_actions:
        try:
            with sc.StorageDB() as db:
                batch_id = db.record_undo_batch(
                    kind="quarantine",
                    actions=undo_actions,
                    description=f"Cách ly {len(undo_actions)} mục vào {sc.KIEM_TRA_FOLDER}",
                )
        except Exception:
            batch_id = ""
    if moved_ids:
        touched_paths = {m["from_path"] for m in allowed if m["id"] in moved_ids}
        for fp in touched_paths:
            if fp in index and isinstance(index[fp].get("items"), list):
                index[fp]["items"] = [it for it in index[fp]["items"] if it.get("id") not in moved_ids]
        sc.save_index(index)
    sc.log(
        f"Đã chuyển vào cách ly: {ok} | đã làm trước đó: {skipped_already} | "
        f"KHÔNG CÓ QUYỀN: {len(blocked)} | lỗi khác: {max(0, fail - len(blocked))} | "
        f"mã hoàn tác: {batch_id or '—'} | log: {log_path}"
    )
    return blocked


def undo_moves(assume_yes: bool, drive: Optional[sc.Drive] = None) -> None:
    log_path = sc.data_dir() / "quarantine_log.json"
    qlog = sc.read_json(log_path, []) or []
    todo = [e for e in qlog if not e.get("restored") and e.get("from_id")]
    if not todo:
        sc.log("Không có mục nào cần hoàn tác.")
        return
    if not sc.confirm(f"Đưa {len(todo)} mục về vị trí cũ?", assume_yes):
        return
    drive = drive or sc.create_drive()
    res = drive.batch_move([(e["id"], e["from_id"]) for e in todo], workers=8)
    by_id = {e["id"]: e for e in todo}
    done = 0
    now_ts = int(time.time())
    for fid, success, err in res:
        e = by_id[fid]
        if success:
            e["restored"] = now_ts
            done += 1
        else:
            sc.log(f"  ! {e['name']}: {err[:200]}")
    sc.write_json(log_path, qlog)
    sc.log(f"Đã hoàn tác {done}/{len(todo)} mục.")


def short(p: str) -> str:
    return p.replace(sc.ROOT_NAME + "/", "")


def build_report(
    branch: Optional[str],
    certain: List[dict],
    version_dups: List[dict],
    dup_tongquan: List[dict],
    suspect: List[dict],
    shortcuts: List[Tuple[str, dict]],
    sc_results,
    empty: List[Tuple[str, str, bool]],
    blocked: Optional[List[dict]] = None,
) -> str:
    wasted_certain = sum(g["size"] * len(g["extra"]) for g in certain)
    n_certain = sum(len(g["extra"]) for g in certain)
    wasted_ver = sum(g["size"] * len(g["extra"]) for g in version_dups)
    n_ver = sum(len(g["extra"]) for g in version_dups)
    n_tq = sum(len(g["extra"]) for g in dup_tongquan)
    n_empty_direct = sum(1 for _, _, nested in empty if not nested)
    n_empty_nested = sum(1 for _, _, nested in empty if nested)

    status_cnt = defaultdict(int)
    for _, s, _, _ in sc_results or []:
        status_cnt[s] += 1

    L = [
        "# BÁO CÁO RÀ SOÁT TRÙNG LẶP VÀ SHORTCUT — STORAGE",
        "",
        f"- **Thời gian:** {sc.today_vn()}",
        f"- **Phạm vi:** `{branch or sc.ROOT_NAME}`",
        f"- **Trùng chắc chắn:** `{sc.fmt_int(len(certain))}` nhóm — `{sc.fmt_int(n_certain)}` bản thừa (≈ **{sc.human_size(wasted_certain)}**)",
        f"- **Trùng phiên bản (`Phiên Bản 1`/`2` cùng dung lượng):** `{sc.fmt_int(len(version_dups))}` nhóm — `{sc.fmt_int(n_ver)}` bản thừa (≈ **{sc.human_size(wasted_ver)}**)",
        f"- **`TongQuan.md` trùng trong `[00] TỔNG QUAN`:** `{sc.fmt_int(len(dup_tongquan))}` cặp ({sc.fmt_int(n_tq)} bản dư)",
        f"- **Nghi trùng / khác `Phần`·`Tập` (cùng dung lượng ≥ 1 MB):** `{sc.fmt_int(len(suspect))}`",
        f"- **Shortcut:** `{sc.fmt_int(len(shortcuts))}`"
        + (" — " + ", ".join(f"{k}: {v}" for k, v in status_cnt.items())
           if sc_results else " (dùng `--kiem-tra-shortcut` để kiểm tra đích)"),
        f"- **Thư mục rỗng:** `{sc.fmt_int(len(empty))}` (`{n_empty_direct}` trực tiếp, `{n_empty_nested}` rỗng lồng nhau)",
    ]
    if blocked:
        L.append(f"- **Không có quyền di chuyển (`KHONG_CO_QUYEN`):** `{sc.fmt_int(len(blocked))}`")
    L.append("")

    L += ["## 1. Tệp trùng lặp chắc chắn (top 100)", ""]
    rows = []
    for g in certain[:100]:
        kp, kit = g["keep"]
        for p, it in g["extra"]:
            rows.append((f"`{it['name']}`", f"`{short(p)}`", f"`{kit['name']}`", f"`{short(kp)}`", sc.human_size(g["size"])))
    L += [sc.md_table(["Bản thừa", "Vị trí bản thừa", "Bản giữ lại", "Vị trí bản giữ", "Dung lượng"], rows,
                      ["l", "l", "l", "l", "r"]) if rows else "_Không có._", ""]

    L += ["## 2. Trùng phiên bản (`Phiên Bản 1`/`Phiên Bản 2`)", ""]
    vrows = []
    for g in version_dups[:100]:
        kp, kit = g["keep"]
        for p, it in g["extra"]:
            vrows.append((f"`{it['name']}`", f"`{short(p)}`", f"`{kit['name']}`", sc.human_size(g["size"])))
    L += [sc.md_table(["Bản thừa", "Thư mục", "Bản giữ lại", "Dung lượng"], vrows, ["l", "l", "l", "r"]) if vrows else "_Không có._", ""]

    L += ["## 3. `TongQuan.md` trùng lặp (hiển thị tối đa 50)", ""]
    tqrows = [(f"`{short(g['keep'][0])}`", f"`{g['extra'][0][1]['id']}`", f"`{g['keep'][1]['id']}`", sc.human_size(g["size"]))
              for g in dup_tongquan[:50]]
    L += [sc.md_table(["Thư mục `[00] TỔNG QUAN`", "ID bản cách ly", "ID bản giữ", "Dung lượng"], tqrows,
                      ["l", "l", "l", "r"]) if tqrows else "_Không có._", ""]

    L += ["## 4. Nghi trùng / đa phần (top 50) — kiểm tra thủ công", ""]
    srows = [(sc.human_size(g["size"]), "<br>".join(f"`{short(p)}/{it['name']}`" for p, it in g["items"][:6]))
             for g in suspect[:50]]
    L += [sc.md_table(["Dung lượng", "Các tệp"], srows, ["r", "l"]) if srows else "_Không có._", "", "## 5. Shortcut", ""]
    if sc_results:
        sc_rows = [(s, f"`{it['name']}`", f"`{short(p)}`", note) for (p, it), s, _, note in sc_results if s != "ok"]
        L.append(sc.md_table(["Trạng thái", "Shortcut", "Vị trí", "Ghi chú"], sc_rows[:200]) if sc_rows else "_Không có shortcut lỗi/thừa._")
    else:
        L.append(sc.md_table(["Shortcut", "Vị trí"], [(f"`{it['name']}`", f"`{short(p)}`") for p, it in shortcuts[:200]])
                 if shortcuts else "_Không có shortcut._")

    L += ["", "## 6. Thư mục rỗng (kể cả lồng nhau)", ""]
    L.append("\n".join(f"- `{short(p)}`" + (" *(rỗng lồng nhau)*" if nested else "") for p, _, nested in empty[:300]) or "_Không có._")
    if blocked:
        L += ["", "## 7. Mục không có quyền di chuyển (`KHONG_CO_QUYEN`)", ""]
        L.append(sc.md_table(["Loại", "Tên", "Thư mục", "Chi tiết"],
                             [(m["kind"], f"`{m['name']}`", f"`{short(m['from_path'])}`", m.get("permission_error", ""))
                              for m in blocked[:100]]))
    L += ["", "---", "", "> Mọi bản thừa chỉ được **di chuyển** vào `[99] KIỂM TRA` (không xóa). Hoàn tác bằng `--hoan-tac`."]
    return "\n".join(L)


def find_system_junk(index: dict, branch: Optional[str] = None) -> List[dict]:
    """Phát hiện thư mục/tệp rác hệ điều hành (`MACOSX`, `__MACOSX`, `.DS_Store`, `Thumbs.db`) ngoài khu cách ly."""
    junk: List[dict] = []
    junk_files = {".ds_store", "thumbs.db", "desktop.ini"}
    prefix = branch.rstrip("/") + "/" if branch else ""
    for path, data in sorted(index.items()):
        if branch and not (path == branch or path.startswith(prefix)):
            continue
        if sc.is_quarantine_path(path) or sc.is_in_danh_sach_tree(path):
            continue
        for it in data.get("items", []):
            name = sc.nfc(it.get("name", "")).strip()
            mime = it.get("mimeType", "")
            body = re.sub(r"^\[\d{1,3}\]\s*", "", name).strip()
            if mime == sc.FOLDER_MIME and body.upper() in {"MACOSX", "__MACOSX"}:
                junk.append({
                    "kind": "system_junk",
                    "subkind": "macosx_folder",
                    "id": it["id"],
                    "name": name,
                    "from_path": path,
                    "from_parent_id": data.get("id", ""),
                    "note": "Thư mục rác nén từ macOS",
                })
            elif mime != sc.FOLDER_MIME and name.lower() in junk_files:
                junk.append({
                    "kind": "system_junk",
                    "subkind": "os_junk_file",
                    "id": it["id"],
                    "name": name,
                    "from_path": path,
                    "from_parent_id": data.get("id", ""),
                    "note": "Tệp siêu dữ liệu rác hệ điều hành",
                })
    return junk


def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(description="Rà soát trùng lặp, rác hệ thống và shortcut hỏng cho [A] STORAGE (v4.0).")
    ap.add_argument("--nhanh", help="Giới hạn trong một nhánh")
    ap.add_argument("--kiem-tra-shortcut", action="store_true", help="Kiểm tra đích shortcut (dùng shortcut_cache.json)")
    ap.add_argument("--gom-phien-ban", action="store_true", help="Đưa nhóm `Phiên Bản 1`/`Phiên Bản 2` trùng vào kế hoạch cách ly")
    ap.add_argument("--gom-tong-quan-trung", action="store_true", help="Đưa cặp `TongQuan.md` trùng trong `[00] TỔNG QUAN` vào kế hoạch cách ly")
    ap.add_argument("--don-rac-he-thong", action="store_true", help="Đưa thư mục/tệp rác hệ điều hành (`MACOSX`, `.DS_Store`, `Thumbs.db`) vào kế hoạch cách ly `[06] RÁC HỆ THỐNG`")
    ap.add_argument("--xac-minh-noi-dung", action="store_true", help="Xác minh SHA-256 trước khi đưa vào kế hoạch cách ly")
    ap.add_argument("--toi-da-hash-mb", type=float, default=50.0, help="Giới hạn kích thước mỗi tệp (MB) khi xác minh SHA-256 (mặc định 50)")
    ap.add_argument("--chi-trung-lap", action="store_true", help="Không cách ly shortcut dù có bật --kiem-tra-shortcut")
    ap.add_argument("--thuc-thi", action="store_true", help="Di chuyển bản thừa vào [07] KIỂM TRA")
    ap.add_argument("--hoan-tac", action="store_true", help="Đưa các mục đã cách ly về vị trí cũ")
    ap.add_argument("--dong-y", action="store_true", help="Không hỏi xác nhận")
    ap.add_argument("--tai-len", action="store_true", help="Tải báo cáo lên [00] TỔNG QUAN/[02] NHẬT KÍ")
    ap.add_argument("--luong", type=int, default=12, help="Số luồng song song")
    args = ap.parse_args(argv)

    if args.hoan_tac:
        undo_moves(args.dong_y)
        return

    index = sc.load_index()
    branch = sc.normalize_branch(args.nhanh)
    branch = None if branch == sc.ROOT_NAME else branch

    sc.log("Đang tìm tệp trùng lặp, rác hệ thống & cặp TongQuan.md trùng...")
    certain, version_dups, suspect = find_duplicates(index, branch)
    dup_tongquan = find_duplicate_tongquan(index, branch)
    shortcuts = find_shortcuts(index, branch)
    system_junk = find_system_junk(index, branch)

    sc_results = None
    if args.kiem_tra_shortcut and shortcuts:
        sc.log(f"Đang kiểm tra đích của {len(shortcuts)} shortcut...")
        sc_results = check_shortcuts(shortcuts, index, workers=args.luong)

    active_certain = certain
    active_ver = version_dups if args.gom_phien_ban else []
    active_tq = dup_tongquan if args.gom_tong_quan_trung else []

    if args.xac_minh_noi_dung:
        drive = sc.create_drive()
        if active_ver:
            sc.log(f"Đang xác minh SHA-256 cho {len(active_ver)} nhóm Phiên Bản...")
            active_ver, ver_rej = verify_groups_sha256(
                active_ver, drive=drive, max_mb=args.toi_da_hash_mb, workers=args.luong, require_verified=True
            )
            if ver_rej:
                sc.log(f"  [!] Loại {len(ver_rej)} nhóm Phiên Bản không khớp SHA-256 / vượt ngưỡng.")
        if active_certain:
            sc.log(f"Đang xác minh SHA-256 cho {len(active_certain)} nhóm trùng chắc chắn (<= {args.toi_da_hash_mb} MB)...")
            active_certain, cert_rej = verify_groups_sha256(
                active_certain, drive=drive, max_mb=args.toi_da_hash_mb, workers=args.luong, require_verified=False
            )
            if cert_rej:
                sc.log(f"  [!] Loại {len(cert_rej)} nhóm khác SHA-256.")
        if active_tq:
            sc.log(f"Đang xác minh SHA-256 cho {len(active_tq)} cặp TongQuan.md trùng...")
            active_tq, tq_rej = verify_groups_sha256(
                active_tq, drive=drive, max_mb=5.0, workers=min(16, max(8, args.luong)), require_verified=True
            )
            if tq_rej:
                sc.log(f"  [!] Loại {len(tq_rej)} cặp TongQuan.md khác SHA-256.")

    empty = find_empty_folders_detailed(index, branch)
    moves = quarantine_moves(
        active_certain,
        version_dups=active_ver,
        dup_tongquan=active_tq,
        sc_results=None if args.chi_trung_lap else sc_results,
    )
    if args.don_rac_he_thong and system_junk:
        moves.extend(system_junk)

    report = build_report(branch, certain, version_dups, dup_tongquan, suspect, shortcuts, sc_results, empty)
    if system_junk:
        report += f"\n\n## 7. Rác hệ điều hành (`MACOSX`, `.DS_Store`, `Thumbs.db`)\n\n- Phát hiện **`{len(system_junk)}`** mục (cách ly an toàn vào `[07] KIỂM TRA/[06] RÁC HỆ THỐNG` khi truyền `--don-rac-he-thong --thuc-thi`).\n"
    md = sc.reports_dir() / f"Báo Cáo Rà Soát Trùng Lặp - Storage, {sc.today_vn()}.md"
    md.write_text(report, encoding="utf-8")
    sc.write_json(sc.data_dir() / "planned_quarantine.json", moves)
    sc.write_csv(
        sc.reports_dir() / f"Báo Cáo Rà Soát Trùng Lặp - Storage, {sc.today_vn()}.csv",
        ["Loại", "Phân nhóm", "Tên", "Vị trí", "ID", "Giữ lại (ID)", "Giữ lại (vị trí)", "SHA-256", "Ghi chú"],
        [
            (
                m["kind"], m.get("subkind", m["kind"]), m["name"], m["from_path"], m["id"],
                m.get("keep_id", m.get("target_id", "")), m.get("keep_path", ""), m.get("sha256", ""), m.get("note", ""),
            )
            for m in moves
        ],
    )
    sc.log(
        f"Trùng chắc chắn: {len(certain)} ({sum(len(g['extra']) for g in certain)} bản thừa) | "
        f"trùng Phiên Bản: {len(version_dups)} | TongQuan trùng: {len(dup_tongquan)} | "
        f"rác hệ thống: {len(system_junk)} | nghi trùng: {len(suspect)} | shortcut: {len(shortcuts)} | thư mục rỗng: {len(empty)}"
    )
    sc.log(f"Báo cáo: {md} | Kế hoạch cách ly: {len(moves)} mục")

    if args.tai_len:
        fid = sc.publish_file(sc.create_drive(), md, sc.nhat_ki_id())
        sc.log(f"Đã tải lên [02] NHẬT KÍ: {sc.drive_url(fid)}")

    if args.thuc_thi:
        if not moves:
            sc.log("Không có mục nào cần cách ly.")
        elif sc.confirm(f"Di chuyển {len(moves)} mục vào [07] KIỂM TRA?", args.dong_y):
            execute_moves(moves, index, workers=min(10, args.luong))
    elif moves:
        sc.log(f"(Chạy thử — {len(moves)} mục sẽ được cách ly khi thêm --thuc-thi.)")


if __name__ == "__main__":
    main()
