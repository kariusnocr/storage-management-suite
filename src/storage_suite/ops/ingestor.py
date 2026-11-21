#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TIẾP NHẬN, PHÂN LOẠI & NHẬP DỮ LIỆU MỚI — [A] STORAGE (CHUẨN V6, v3.0)
=======================================================================
Chương trình `[11] NHẬP DỮ LIỆU MỚI/data_ingestor.py` tự động hóa quy trình tiếp nhận dữ liệu mới vào kho:

1. Đa nguồn đầu vào:
   - `--tu-khu-nhap`   : Quét khu tiếp nhận `[07] KIỂM TRA/[04] NHẬP DỮ LIỆU` (`1Xhgp46XpL3ng_l_d-_-wHb4S12DTuPri`).
                         Tự động phát hiện các **Shortcut trỏ tới tệp/thư mục ngoài** (ví dụ `Sách Ngành Y học`),
                         đệ quy cây thư mục đích của shortcut và sao chép phía máy chủ (`server-side copy`)
                         thành tệp thật trong kho, sau đó chuyển shortcut đã xử lý sang `[02] SHORTCUT ĐÃ SAO CHÉP`.
   - `--nguon-drive`   : Nhập trực tiếp từ một ID hoặc URL tệp/thư mục Google Drive bất kỳ.
   - `--nguon-cuc-bo`  : Tải lên tệp hoặc đệ quy cả cây thư mục từ máy cục bộ.
2. Kiểm tra trùng lặp toàn kho (`storage_index.json`):
   - Đối chiếu khóa tên chuẩn hóa + kích thước với toàn bộ kho hoạt động; tự động bỏ qua bản trùng (`TRUNG_TOAN_KHO`).
3. Tự động phân loại nhánh đích (`auto_classify_destination`) hoặc chỉ định `--dich`:
   - Nhận diện chủ đề (Y học, Triết học, Tâm lý học, Huyền học, Lịch sử, Văn học, Ngoại ngữ, Âm nhạc…) để định tuyến
     chính xác vào nhánh `[05] SƯU TẦM/[01] SÁCH/...` hoặc `[01] HỌC THUẬT/...`.
4. Tự động chuẩn hóa tên tệp/thư mục theo Chuẩn V6 & khởi tạo `[00] TỔNG QUAN` + `Tổng Quan Hệ Thống - <Tên>.md`.
5. Mặc định **CHẠY THỬ (dry-run)**; chỉ ghi lên Drive khi truyền `--thuc-thi`.
"""

from __future__ import annotations

import argparse
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple


from storage_suite import core as sc

# Quy tắc định tuyến chủ đề tự động (từ khóa không dấu -> danh sách nhánh ưu tiên)
TOPIC_ROUTES: List[Tuple[Tuple[str, ...], List[str]]] = [
    (
        ("y hoc", "suc khoe", "giai phau", "benh hoc", "duoc hoc", "dong y", "ung thu", "dinh duong",
         "anatomy", "neuroanatom", "medical", "medicine", "clinical", "physiology", "pathology", " Netter"),
        [
            "[A] STORAGE/[05] SƯU TẦM/[01] SÁCH/[14] SỨC KHOẺ - Y HỌC",
            "[A] STORAGE/[05] SƯU TẦM/[01] SÁCH",
        ],
    ),
    (
        ("tu vi", "kinh dich", "phong thuy", "phi tinh", "bat tu", "tuong phap", "huyen hoc", "chiem tinh", "tarot", "co hoc tinh hoa"),
        [
            "[A] STORAGE/[05] SƯU TẦM/[01] SÁCH/[06] HUYỀN HỌC",
            "[A] STORAGE/[05] SƯU TẦM/[01] SÁCH",
        ],
    ),
    (
        ("tam ly", "phan tam", "freud", "jung", "the ego", "tam than", "hanh vi", "cam xuc", "psychology"),
        [
            "[A] STORAGE/[05] SƯU TẦM/[01] SÁCH/[05] TÂM LÝ HỌC",
            "[A] STORAGE/[05] SƯU TẦM/[01] SÁCH",
        ],
    ),
    (
        ("triet hoc", "sieu hinh", "nhan thuc luan", "logic hoc", "dao duc hoc", "my hoc", "descartes", "kant", "hegel", "nietzsche", "plato", "aristotle"),
        [
            "[A] STORAGE/[05] SƯU TẦM/[01] SÁCH/[01] TRIẾT HỌC",
            "[A] STORAGE/[01] HỌC THUẬT/[01] ĐẠI HỌC",
            "[A] STORAGE/[05] SƯU TẦM/[01] SÁCH",
        ],
    ),
    (
        ("lich su", "co dai", "trung dai", "can dai", "su hoc", "viet nam su luoc", "dai viet su ky"),
        [
            "[A] STORAGE/[05] SƯU TẦM/[01] SÁCH/[02] LỊCH SỬ",
            "[A] STORAGE/[05] SƯU TẦM/[01] SÁCH",
        ],
    ),
    (
        ("tieu thuyet", "van hoc", "truyen ngan", "thi tap", "tho ca"),
        [
            "[A] STORAGE/[05] SƯU TẦM/[01] SÁCH/[03] VĂN HỌC",
            "[A] STORAGE/[05] SƯU TẦM/[01] SÁCH",
        ],
    ),
    (
        ("kinh te", "quan tri", "tai chinh", "marketing", "chung khoan", "dau tu"),
        [
            "[A] STORAGE/[05] SƯU TẦM/[01] SÁCH/[04] KINH TẾ",
            "[A] STORAGE/[05] SƯU TẦM/[01] SÁCH",
        ],
    ),
    (
        ("ton giao", "phat giao", "cong giao", "kinh thanh", "kinh phat", "thien"),
        [
            "[A] STORAGE/[05] SƯU TẦM/[01] SÁCH/[07] TÔN GIÁO",
            "[A] STORAGE/[05] SƯU TẦM/[01] SÁCH",
        ],
    ),
    (
        ("ielts", "toefl", "toeic", "hsk", "vstep"),
        [
            "[A] STORAGE/[01] HỌC THUẬT/[04] CHỨNG CHỈ",
        ],
    ),
]


def _norm_key_for_dedup(name: str, mime: str = "") -> Tuple[str, str]:
    base, ext = sc.split_ext(name, mime)
    b = sc.strip_accents(sc.nfc(base)).lower().strip()
    b = re.sub(r"^\[\d{1,3}\]\s*", "", b)
    b = re.sub(r"^(\d{2,4}_)?\d{6}_", "", b)
    # Tách phần tên chính trước " - " để so khớp kể cả khi tệp nguồn chưa gắn "- Thông Tin Bổ Sung"
    main_part = b.split(" - ", 1)[0].strip()
    k_full = re.sub(r"[^a-z0-9]+", "", b)
    k_main = re.sub(r"[^a-z0-9]+", "", main_part)
    return k_full, f"{k_main}|{ext.lower()}"


def build_repo_dedup_lookup(index: dict) -> Tuple[Dict[Tuple[str, int], Tuple[str, dict]], Dict[Tuple[str, int], Tuple[str, dict]]]:
    """
    Xây dựng 2 bảng tra cứu O(1) trên toàn bộ kho hoạt động (loại trừ vùng `[07] KIỂM TRA`):
    - `by_full_key`: `(norm_full_name, size) -> (folder_path, item)`
    - `by_main_key`: `(norm_main_title_and_ext, size) -> (folder_path, item)`
    """
    by_full: Dict[Tuple[str, int], Tuple[str, dict]] = {}
    by_main: Dict[Tuple[str, int], Tuple[str, dict]] = {}
    for path, it in sc.iter_items(index):
        if sc.is_quarantine_path(path) or sc.is_in_tong_quan(path):
            continue
        mime = it.get("mimeType", "")
        if mime == sc.FOLDER_MIME or mime in sc.GOOGLE_NATIVE_MIMES:
            continue
        sz = int(it.get("size") or 0)
        if sz <= 0:
            continue
        kf, km = _norm_key_for_dedup(it.get("name", ""), mime)
        if kf:
            by_full.setdefault((kf, sz), (path, it))
        if km and not km.startswith("|"):
            by_main.setdefault((km, sz), (path, it))
    return by_full, by_main


def check_duplicate_in_repo(
    name: str,
    mime: str,
    size: Optional[int],
    by_full: Dict[Tuple[str, int], Tuple[str, dict]],
    by_main: Dict[Tuple[str, int], Tuple[str, dict]],
) -> Optional[Tuple[str, dict]]:
    sz = int(size or 0)
    if sz <= 0 or mime == sc.FOLDER_MIME or mime in sc.GOOGLE_NATIVE_MIMES:
        return None
    kf, km = _norm_key_for_dedup(name, mime)
    if kf and (kf, sz) in by_full:
        return by_full[(kf, sz)]
    if km and (km, sz) in by_main:
        return by_main[(km, sz)]
    return None


def auto_classify_destination(
    name: str,
    context_hint: str,
    mime: str,
    index: dict,
    explicit_dest: Optional[str] = None,
) -> str:
    """Xác định đường dẫn nhánh đích Chuẩn V6 trong kho."""
    if explicit_dest:
        norm = sc.normalize_branch(explicit_dest)
        if norm:
            return norm

    _, ext = sc.split_ext(name, mime)
    ext = ext.lower()
    if ext in {"mp3", "flac", "wav", "m4a", "aac", "ogg"} or mime.startswith("audio/"):
        cand = "[A] STORAGE/[05] SƯU TẦM/[04] ÂM NHẠC"
        if cand in index:
            return cand

    combined = sc.strip_accents(sc.nfc(f"{context_hint} {name}")).lower()
    for keywords, route_candidates in TOPIC_ROUTES:
        if any(kw.lower() in combined for kw in keywords):
            for rc in route_candidates:
                if rc in index:
                    return rc
                # Tìm nhánh con khớp tên chủ đề trong index
                target_tail = sc.strip_accents(rc.split("/")[-1]).upper()
                target_body = re.sub(r"^\[\d{2,3}\]\s*", "", target_tail)
                for p in index:
                    if sc.is_quarantine_path(p) or sc.is_in_tong_quan(p):
                        continue
                    last_seg = sc.strip_accents(p.split("/")[-1]).upper()
                    if target_body and target_body in last_seg:
                        return p
            return route_candidates[0]

    if ext in {"pdf", "epub", "mobi", "azw3", "djvu", "prc"}:
        return "[A] STORAGE/[05] SƯU TẦM/[01] SÁCH"
    return "[A] STORAGE/[05] SƯU TẦM/[02] TÀI LIỆU"


def _folder_context_label(dest_path: str) -> str:
    if not dest_path or dest_path == sc.ROOT_NAME:
        return "Storage"
    segs = [s for s in dest_path.split("/") if s and s != sc.TONG_QUAN_FOLDER]
    last = segs[-1] if segs else "Storage"
    clean = re.sub(r"^\[\d{2,3}\]\s*", "", last)
    clean = re.sub(r"^\[([^\]]+)\]\s*(.+)$", lambda m: f"{m.group(1).strip()} - {m.group(2).strip()}", clean)
    clean = re.sub(r"^\[([^\]]+)\]$", r"\1", clean)
    clean = re.sub(r"\s*_+\s*", " ", clean).strip()
    return sc.title_case_vn(clean)


_INGEST_VN_PHRASES = [
    (re.compile(r"\bBenh\s+Hen\s+Suyen\b", re.I), "Bệnh Hen Suyễn"),
    (re.compile(r"\bTieng\s+Viet\b", re.I), "Tiếng Việt"),
    (re.compile(r"\bY\s+Hoc\b", re.I), "Y Học"),
    (re.compile(r"\bSuc\s+Khoe\b", re.I), "Sức Khoẻ"),
    (re.compile(r"\bGiai\s+Phau\b", re.I), "Giải Phẫu"),
    (re.compile(r"\bBenh\s+Hoc\b", re.I), "Bệnh Học"),
    (re.compile(r"\bLam\s+Sang\b", re.I), "Lâm Sàng"),
    (re.compile(r"\bNoi\s+Khoa\b", re.I), "Nội Khoa"),
    (re.compile(r"\bNgoai\s+Khoa\b", re.I), "Ngoại Khoa"),
]


def normalize_ingested_file_name(name: str, mime: str, dest_path: str, source_hint: str = "") -> str:
    """
    Chuẩn hóa tên tệp mới nhập theo Chuẩn V6:
      `Tên Viết Hoa Đầu Mỗi Chữ Có Dấu - Thông Tin Bổ Sung.[đuôi]`
    """
    clean = sc.safe_fix_name(name, is_folder=False, mime=mime)
    if sc.is_tech_exception(dest_path, clean):
        return clean
    base, ext = sc.split_ext(clean, mime)
    base = re.sub(r"^\[\d{1,3}\]\s*", "", base).strip()
    base = re.sub(r"^(\d{2,4}_)?\d{6}_", "", base).strip()
    # Loại bỏ hậu tố trang tải / Google Drive / đuôi lặp trong thân tên
    base = re.sub(
        r"(?:\s*[-–]\s*)?(?:\(\s*)?\b(?:Dantocking\.com|Dantocking|thuvienPDF\.com|Epub\.vn|Nottram\.edu\.vn|z-lib\.org|z-library|libgen\.li|Google\s+Drive)\b(?:\s*\))?",
        "",
        base,
        flags=re.I,
    )
    if ext:
        base = re.sub(rf"\.{re.escape(ext)}\b", "", base, flags=re.I)
    base = re.sub(r"\(\s*\)", "", base)
    # Tách từ CamelCase thuần Việt hoặc từ dính (ví dụ BenhHenSuyen -> Benh Hen Suyen)
    if " " not in base and re.search(r"[a-z][A-Z]", base):
        base = re.sub(r"([a-z])([A-Z])", r"\1 \2", base)
    for rx, rep in _INGEST_VN_PHRASES:
        base = rx.sub(rep, base)
    base = re.sub(r"\s{2,}", " ", base).strip(" -_,")

    ctx = _folder_context_label(dest_path)
    hint_clean = sc.title_case_vn(re.sub(r"^\[\d{1,3}\]\s*", "", source_hint.strip())) if source_hint else ""

    if " - " in base:
        parts = [p.strip() for p in base.split(" - ") if p.strip()]
        main_title = sc.title_case_vn(parts[0])
        meta_part = ", ".join(sc.title_case_vn(p) for p in parts[1:])
        if not meta_part:
            meta_part = hint_clean or ctx
    else:
        # Tách tác giả trong ngoặc đơn cuối tên nếu có: `Tên Sách (Tác Giả)`
        m_paren = re.match(r"^(.+?)\s*\(([^()]{3,45})\)$", base)
        if m_paren:
            main_title = sc.title_case_vn(m_paren.group(1).strip())
            author = sc.title_case_vn(m_paren.group(2).strip())
            meta_part = f"{author}, {ctx}" if author.lower() not in ctx.lower() else author
        else:
            main_title = sc.title_case_vn(base)
            meta_part = hint_clean if (hint_clean and hint_clean.lower() != main_title.lower()) else ctx

    final_base = f"{main_title} - {meta_part}".strip(" -_,")
    final_base = re.sub(r"\(\s*\)", "", final_base)
    final_base = re.sub(r"\s{2,}", " ", final_base).strip(" -_,")
    return f"{final_base}.{ext.lower()}" if ext else final_base


def normalize_ingested_folder_name(name: str, existing_dest_items: Sequence[dict]) -> str:
    """Chuẩn hóa tên thư mục mới nhập sang `[STT] TÊN IN HOA CÓ DẤU`."""
    clean = sc.nfc(name).strip()
    body = re.sub(r"^\[\d{1,3}\]\s*", "", clean)
    body = re.sub(r"\s*_+\s*", " ", body).strip().upper()
    stt = sc.next_available_stt(existing_dest_items)
    return f"{stt} {body}" if body else stt


def _crawl_external_drive_folder(
    drive: sc.Drive,
    root_folder_id: str,
    root_label: str,
    workers: int = 24,
) -> Dict[str, dict]:
    """
    Quét BFS cây thư mục nguồn trên Google Drive (ví dụ đích của shortcut trong `[04] NHẬP DỮ LIỆU`).
    Trả về `{"": {"id": root_folder_id, "name": root_label, "items": [...]}, "Sub": ...}`.
    """
    tree: Dict[str, dict] = {}
    wave: List[Tuple[str, str, str]] = [("", root_folder_id, root_label)]
    while wave:
        fids = [fid for _, fid, _ in wave]
        if hasattr(drive, "stream_ls"):
            items_map, _ = drive.stream_ls(fids, concurrency=max(8, workers))
        else:
            items_map = {fid: drive.ls(fid) for fid in fids}
        next_wave: List[Tuple[str, str, str]] = []
        for rel_path, fid, label in wave:
            items = items_map.get(fid, [])
            tree[rel_path] = {"id": fid, "name": label, "items": items}
            for it in items:
                if it.get("mimeType") == sc.FOLDER_MIME and it.get("name") != sc.TONG_QUAN_FOLDER:
                    child_rel = f"{rel_path}/{it['name']}" if rel_path else it["name"]
                    next_wave.append((child_rel, it["id"], it["name"]))
        wave = next_wave
    return tree


def plan_ingest_from_staging(
    index: dict,
    drive: sc.Drive,
    explicit_dest: Optional[str] = None,
    flatten_into_dest: bool = False,
) -> Dict[str, Any]:
    """
    Quét khu vực tiếp nhận `[07] KIỂM TRA/[04] NHẬP DỮ LIỆU` và lập kế hoạch nhập dữ liệu:
    - Tự động giải nén các Shortcut trỏ tới tệp/thư mục ngoài thành các lệnh sao chép tệp thật vào nhánh đích.
    - Đối chiếu chống trùng lặp toàn kho (`storage_index.json`).
    """
    staging_id = sc.ingest_folder_id()
    staging_items = drive.ls(staging_id)
    by_full, by_main = build_repo_dedup_lookup(index)

    planned_ops: List[dict] = []
    duplicates_skipped: List[dict] = []
    shortcuts_resolved: List[dict] = []
    dest_sim_items: Dict[str, List[dict]] = {}

    def get_sim_items(dest_path: str) -> List[dict]:
        if dest_path not in dest_sim_items:
            dest_sim_items[dest_path] = [dict(x) for x in index.get(dest_path, {}).get("items", [])]
        return dest_sim_items[dest_path]

    for item in staging_items:
        name = item.get("name", "")
        mime = item.get("mimeType", "")
        fid = item.get("id", "")
        if name == sc.TONG_QUAN_FOLDER or name.startswith("Tổng Quan Hệ Thống - ") or name.startswith("Danh Mục Hệ Thống - "):
            continue

        # Trường hợp 1: Shortcut trong khu [04] NHẬP DỮ LIỆU
        if mime == sc.SHORTCUT_MIME:
            info = drive.info(fid)
            det = info.get("shortcutDetails") or {}
            tid = det.get("targetId", "")
            tmime = det.get("targetMimeType", "")
            if not tid:
                continue
            tinfo = drive.info(tid)
            tname = (tinfo.get("name") or name).strip()
            tmime = tinfo.get("mimeType") or tmime

            if tmime == sc.FOLDER_MIME:
                ext_tree = _crawl_external_drive_folder(drive, tid, tname)
                dest_branch = auto_classify_destination(tname, tname, tmime, index, explicit_dest)
                copied_for_sc = 0
                dup_for_sc = 0

                # Ánh xạ đường dẫn tương đối trong cây nguồn -> đường dẫn đích trong kho
                rel_to_dest_path: Dict[str, str] = {"": dest_branch}
                for rel_p in sorted(ext_tree.keys(), key=lambda k: (k.count("/"), k)):
                    node = ext_tree[rel_p]
                    if rel_p and not flatten_into_dest:
                        parent_rel = rel_p.rsplit("/", 1)[0] if "/" in rel_p else ""
                        parent_dest = rel_to_dest_path.get(parent_rel, dest_branch)
                        sim_parent = get_sim_items(parent_dest)
                        folder_v6 = normalize_ingested_folder_name(node["name"], sim_parent)
                        target_folder_path = f"{parent_dest}/{folder_v6}"
                        rel_to_dest_path[rel_p] = target_folder_path
                        sim_parent.append({"id": f"new_{rel_p}", "name": folder_v6, "mimeType": sc.FOLDER_MIME})
                        planned_ops.append({
                            "op": "ensure_folder",
                            "source_id": node["id"],
                            "source_name": node["name"],
                            "dest_parent_path": parent_dest,
                            "target_name": folder_v6,
                            "target_path": target_folder_path,
                            "from_shortcut_id": fid,
                        })
                    else:
                        rel_to_dest_path[rel_p] = dest_branch

                    cur_dest_path = rel_to_dest_path[rel_p]
                    sim_cur = get_sim_items(cur_dest_path)
                    taken_names = {sc.nfc(x.get("name", "")) for x in sim_cur}

                    for ch in node.get("items", []):
                        ch_mime = ch.get("mimeType", "")
                        if ch_mime == sc.FOLDER_MIME:
                            continue
                        ch_name = ch.get("name", "")
                        ch_size = int(ch["size"]) if ch.get("size") is not None else None
                        dup_match = check_duplicate_in_repo(ch_name, ch_mime, ch_size, by_full, by_main)
                        if dup_match is not None:
                            dup_for_sc += 1
                            duplicates_skipped.append({
                                "source_id": ch["id"],
                                "source_name": ch_name,
                                "size": ch_size,
                                "existing_path": dup_match[0],
                                "existing_name": dup_match[1]["name"],
                                "existing_id": dup_match[1]["id"],
                                "from_shortcut": tname,
                            })
                            continue

                        v6_name = normalize_ingested_file_name(ch_name, ch_mime, cur_dest_path, source_hint=tname)
                        if sc.nfc(v6_name) in taken_names:
                            b_part, e_part = sc.split_ext(v6_name, ch_mime)
                            seq = 2
                            while sc.nfc(v6_name) in taken_names:
                                v6_name = f"{b_part}, Bản {seq:02d}.{e_part}" if e_part else f"{b_part}, Bản {seq:02d}"
                                seq += 1
                        taken_names.add(sc.nfc(v6_name))
                        sim_cur.append({"id": ch["id"], "name": v6_name, "mimeType": ch_mime, "size": ch_size})
                        # Đăng ký vào bảng tra cứu trùng để chống trùng ngay giữa các tệp trong cùng đợt nhập
                        if ch_size and ch_size > 0:
                            kf, km = _norm_key_for_dedup(v6_name, ch_mime)
                            by_full[(kf, ch_size)] = (cur_dest_path, {"id": ch["id"], "name": v6_name})
                            by_main[(km, ch_size)] = (cur_dest_path, {"id": ch["id"], "name": v6_name})

                        copied_for_sc += 1
                        planned_ops.append({
                            "op": "copy_remote_file",
                            "source_id": ch["id"],
                            "source_name": ch_name,
                            "dest_parent_path": cur_dest_path,
                            "target_name": v6_name,
                            "mimeType": ch_mime,
                            "size": ch_size,
                            "from_shortcut_id": fid,
                            "from_shortcut_name": name,
                        })

                shortcuts_resolved.append({
                    "shortcut_id": fid,
                    "shortcut_name": name,
                    "target_id": tid,
                    "target_name": tname,
                    "target_mime": tmime,
                    "dest_branch": dest_branch,
                    "files_to_copy": copied_for_sc,
                    "duplicates_skipped": dup_for_sc,
                })
                planned_ops.append({
                    "op": "archive_ingested_shortcut",
                    "source_id": fid,
                    "source_name": name.strip(),
                    "target_id": tid,
                })
            else:
                tsize = int(tinfo["size"]) if tinfo.get("size") is not None else None
                dup_match = check_duplicate_in_repo(tname, tmime, tsize, by_full, by_main)
                dest_branch = auto_classify_destination(tname, name, tmime, index, explicit_dest)
                if dup_match is not None:
                    duplicates_skipped.append({
                        "source_id": tid,
                        "source_name": tname,
                        "size": tsize,
                        "existing_path": dup_match[0],
                        "existing_name": dup_match[1]["name"],
                        "existing_id": dup_match[1]["id"],
                        "from_shortcut": name,
                    })
                else:
                    v6_name = normalize_ingested_file_name(tname, tmime, dest_branch)
                    planned_ops.append({
                        "op": "copy_remote_file",
                        "source_id": tid,
                        "source_name": tname,
                        "dest_parent_path": dest_branch,
                        "target_name": v6_name,
                        "mimeType": tmime,
                        "size": tsize,
                        "from_shortcut_id": fid,
                        "from_shortcut_name": name,
                    })
                shortcuts_resolved.append({
                    "shortcut_id": fid,
                    "shortcut_name": name,
                    "target_id": tid,
                    "target_name": tname,
                    "target_mime": tmime,
                    "dest_branch": dest_branch,
                    "files_to_copy": 0 if dup_match else 1,
                    "duplicates_skipped": 1 if dup_match else 0,
                })
                planned_ops.append({
                    "op": "archive_ingested_shortcut",
                    "source_id": fid,
                    "source_name": name.strip(),
                    "target_id": tid,
                })
            continue

        # Trường hợp 2: Tệp thật nằm trực tiếp trong [04] NHẬP DỮ LIỆU
        if mime != sc.FOLDER_MIME:
            fsize = int(item["size"]) if item.get("size") is not None else None
            dup_match = check_duplicate_in_repo(name, mime, fsize, by_full, by_main)
            if dup_match is not None:
                duplicates_skipped.append({
                    "source_id": fid,
                    "source_name": name,
                    "size": fsize,
                    "existing_path": dup_match[0],
                    "existing_name": dup_match[1]["name"],
                    "existing_id": dup_match[1]["id"],
                    "from_shortcut": "(trực tiếp trong [04] NHẬP DỮ LIỆU)",
                })
                planned_ops.append({
                    "op": "quarantine_duplicate_staging_file",
                    "source_id": fid,
                    "source_name": name,
                })
                continue

            dest_branch = auto_classify_destination(name, "", mime, index, explicit_dest)
            v6_name = normalize_ingested_file_name(name, mime, dest_branch)
            planned_ops.append({
                "op": "move_staging_file",
                "source_id": fid,
                "source_name": name,
                "dest_parent_path": dest_branch,
                "target_name": v6_name,
                "mimeType": mime,
                "size": fsize,
            })

    return {
        "source_mode": "staging",
        "staging_id": staging_id,
        "shortcuts_resolved": shortcuts_resolved,
        "planned_ops": planned_ops,
        "duplicates_skipped": duplicates_skipped,
    }


def plan_ingest_from_local(
    local_source: Path,
    index: dict,
    explicit_dest: Optional[str] = None,
) -> Dict[str, Any]:
    """Lập kế hoạch nhập tệp hoặc cây thư mục từ máy cục bộ vào kho."""
    src = Path(local_source).expanduser().resolve()
    if not src.exists():
        raise SystemExit(f"Đường dẫn cục bộ không tồn tại: {src}")

    by_full, by_main = build_repo_dedup_lookup(index)
    planned_ops: List[dict] = []
    duplicates_skipped: List[dict] = []

    if src.is_file():
        fsize = src.stat().st_size
        dup_match = check_duplicate_in_repo(src.name, "", fsize, by_full, by_main)
        dest_branch = auto_classify_destination(src.name, src.parent.name, "", index, explicit_dest)
        if dup_match is not None:
            duplicates_skipped.append({
                "source_id": str(src),
                "source_name": src.name,
                "size": fsize,
                "existing_path": dup_match[0],
                "existing_name": dup_match[1]["name"],
                "existing_id": dup_match[1]["id"],
                "from_shortcut": "(máy cục bộ)",
            })
        else:
            v6_name = normalize_ingested_file_name(src.name, "", dest_branch)
            planned_ops.append({
                "op": "upload_local_file",
                "local_path": str(src),
                "source_name": src.name,
                "dest_parent_path": dest_branch,
                "target_name": v6_name,
                "size": fsize,
            })
    else:
        dest_branch = auto_classify_destination(src.name, src.name, sc.FOLDER_MIME, index, explicit_dest)
        for p in sorted(src.rglob("*")):
            if p.name.startswith(".") or "__pycache__" in p.parts:
                continue
            if p.is_file():
                fsize = p.stat().st_size
                dup_match = check_duplicate_in_repo(p.name, "", fsize, by_full, by_main)
                if dup_match is not None:
                    duplicates_skipped.append({
                        "source_id": str(p),
                        "source_name": p.name,
                        "size": fsize,
                        "existing_path": dup_match[0],
                        "existing_name": dup_match[1]["name"],
                        "existing_id": dup_match[1]["id"],
                        "from_shortcut": str(src.name),
                    })
                    continue
                v6_name = normalize_ingested_file_name(p.name, "", dest_branch, source_hint=p.parent.name)
                planned_ops.append({
                    "op": "upload_local_file",
                    "local_path": str(p),
                    "source_name": p.name,
                    "dest_parent_path": dest_branch,
                    "target_name": v6_name,
                    "size": fsize,
                })

    return {
        "source_mode": "local",
        "local_source": str(src),
        "shortcuts_resolved": [],
        "planned_ops": planned_ops,
        "duplicates_skipped": duplicates_skipped,
    }


def _ensure_branch_path_on_drive(drive: sc.Drive, index: dict, branch_path: str) -> str:
    """Đảm bảo đường dẫn `branch_path` tồn tại trên Drive và trả về `folder_id`."""
    if branch_path in index and index[branch_path].get("id"):
        return index[branch_path]["id"]
    parts = [p for p in branch_path.split("/") if p]
    if not parts or parts[0] != sc.ROOT_NAME:
        raise ValueError(f"Đường dẫn đích phải bắt đầu bằng {sc.ROOT_NAME}: {branch_path}")
    cur_path = sc.ROOT_NAME
    cur_id = sc.ROOT_ID
    for seg in parts[1:]:
        next_path = f"{cur_path}/{seg}"
        if next_path in index and index[next_path].get("id"):
            cur_id = index[next_path]["id"]
        else:
            cur_id = drive.ensure_folder(seg, cur_id)
            index.setdefault(next_path, {"id": cur_id, "depth": next_path.count("/"), "items": []})
        cur_path = next_path
    return cur_id


def execute_ingest_plan(
    plan_bundle: Dict[str, Any],
    index: dict,
    drive: Optional[sc.Drive] = None,
    init_tong_quan: bool = True,
) -> Dict[str, Any]:
    """Thực thi kế hoạch nhập dữ liệu mới lên Google Drive và cập nhật chỉ mục + `ingest_log.json`."""
    drive = drive or sc.create_drive()
    ops = plan_bundle.get("planned_ops", [])
    batch_id = f"ing_{sc.now_stamp()}"
    executed: List[dict] = []
    failed: List[dict] = []
    created_branch_paths: Set[str] = set()

    kiem_tra_id = sc.quarantine_root_id()
    q_sub = sc.CONFIG.get("quarantine_subfolders", {})
    sc_copied_dir_id: Optional[str] = None
    dup_dir_id: Optional[str] = None

    for step in ops:
        kind = step["op"]
        try:
            if kind == "ensure_folder":
                parent_id = _ensure_branch_path_on_drive(drive, index, step["dest_parent_path"])
                new_dir_id = drive.ensure_folder(step["target_name"], parent_id)
                index.setdefault(step["target_path"], {
                    "id": new_dir_id,
                    "depth": step["target_path"].count("/"),
                    "items": [],
                })
                p_items = index.setdefault(step["dest_parent_path"], {
                    "id": parent_id,
                    "depth": step["dest_parent_path"].count("/"),
                    "items": [],
                }).setdefault("items", [])
                if not any(x.get("id") == new_dir_id for x in p_items):
                    p_items.append({
                        "id": new_dir_id,
                        "name": step["target_name"],
                        "mimeType": sc.FOLDER_MIME,
                        "modifiedTime": sc.now_utc_iso(),
                    })
                created_branch_paths.add(step["target_path"])
                executed.append({**step, "created_id": new_dir_id, "ts": int(time.time())})

            elif kind == "copy_remote_file":
                dest_pid = _ensure_branch_path_on_drive(drive, index, step["dest_parent_path"])
                new_id = drive.copy(step["source_id"], step["target_name"], dest_pid)
                if new_id:
                    index[step["dest_parent_path"]].setdefault("items", []).append({
                        "id": new_id,
                        "name": step["target_name"],
                        "mimeType": step.get("mimeType", ""),
                        "size": step.get("size"),
                        "modifiedTime": sc.now_utc_iso(),
                    })
                executed.append({**step, "dest_parent_id": dest_pid, "created_id": new_id, "ts": int(time.time())})

            elif kind == "move_staging_file":
                dest_pid = _ensure_branch_path_on_drive(drive, index, step["dest_parent_path"])
                drive.move(step["source_id"], dest_pid)
                if step["target_name"] != step["source_name"]:
                    drive.rename(step["source_id"], step["target_name"])
                index[step["dest_parent_path"]].setdefault("items", []).append({
                    "id": step["source_id"],
                    "name": step["target_name"],
                    "mimeType": step.get("mimeType", ""),
                    "size": step.get("size"),
                    "modifiedTime": sc.now_utc_iso(),
                })
                executed.append({**step, "dest_parent_id": dest_pid, "ts": int(time.time())})

            elif kind == "upload_local_file":
                dest_pid = _ensure_branch_path_on_drive(drive, index, step["dest_parent_path"])
                local_p = Path(step["local_path"])
                with tempfile.TemporaryDirectory(prefix="ingest_up_") as td:
                    staged = Path(td) / step["target_name"]
                    staged.write_bytes(local_p.read_bytes())
                    new_id = drive.upload(staged, dest_pid)
                if new_id:
                    index[step["dest_parent_path"]].setdefault("items", []).append({
                        "id": new_id,
                        "name": step["target_name"],
                        "mimeType": "",
                        "size": step.get("size"),
                        "modifiedTime": sc.now_utc_iso(),
                    })
                executed.append({**step, "dest_parent_id": dest_pid, "created_id": new_id, "ts": int(time.time())})

            elif kind == "archive_ingested_shortcut":
                if not sc_copied_dir_id:
                    sc_copied_dir_id = drive.ensure_folder(
                        q_sub.get("redundant_shortcut", "[02] SHORTCUT ĐÃ SAO CHÉP"),
                        kiem_tra_id,
                    )
                if step["source_name"] != step["source_name"].strip():
                    drive.rename(step["source_id"], step["source_name"].strip())
                drive.move(step["source_id"], sc_copied_dir_id)
                executed.append({
                    **step,
                    "old_parent_id": sc.ingest_folder_id(),
                    "dest_parent_id": sc_copied_dir_id,
                    "ts": int(time.time()),
                })

            elif kind == "quarantine_duplicate_staging_file":
                if not dup_dir_id:
                    dup_dir_id = drive.ensure_folder(q_sub.get("duplicate", "[03] TỆP TRÙNG LẶP"), kiem_tra_id)
                drive.move(step["source_id"], dup_dir_id)
                executed.append({
                    **step,
                    "old_parent_id": sc.ingest_folder_id(),
                    "dest_parent_id": dup_dir_id,
                    "ts": int(time.time()),
                })
        except sc.DriveError as e:
            failed.append({**step, "error": str(e)[:250]})

    # Khởi tạo bộ khung [00] TỔNG QUAN + Tổng Quan Hệ Thống - <Tên>.md cho các thư mục mới tạo
    if init_tong_quan and created_branch_paths:
        for bp in sorted(created_branch_paths):
            folder_id = index.get(bp, {}).get("id")
            if not folder_id:
                continue
            try:
                tq_id = drive.ensure_folder(sc.TONG_QUAN_FOLDER, folder_id)
                ctx_title = _folder_context_label(bp)
                doc_name = f"Tổng Quan Hệ Thống - {ctx_title}.md"
                doc_body = (
                    f"# TỔNG QUAN HỆ THỐNG — {ctx_title.upper()}\n\n"
                    f"- **Đường dẫn nhánh:** `{bp}`\n"
                    f"- **ID Thư mục:** `{folder_id}`\n"
                    f"- **Ngày khởi tạo:** {sc.today_vn()}\n"
                    f"- **Chuẩn đặt tên:** Chuẩn V6 (`Tên Viết Hoa Đầu Mỗi Chữ Có Dấu - Thông Tin Bổ Sung.[đuôi]`)\n"
                )
                with tempfile.TemporaryDirectory(prefix="tq_init_") as td:
                    md_file = Path(td) / doc_name
                    md_file.write_text(doc_body, encoding="utf-8")
                    sc.publish_file(drive, md_file, tq_id, name=doc_name)
            except sc.DriveError:
                pass

    if executed:
        sc.save_index(index)
        ilog = sc.read_json(sc.ingest_log_path(), []) or []
        ilog.append({
            "batch_id": batch_id,
            "created_iso": sc.now_utc_iso(),
            "executed": executed,
            "restored": False,
        })
        sc.write_json(sc.ingest_log_path(), ilog, indent=1)

    return {
        "batch_id": batch_id,
        "executed": executed,
        "failed": failed,
    }


def build_ingest_report(plan_bundle: Dict[str, Any], exec_result: Optional[Dict[str, Any]] = None) -> str:
    shortcuts = plan_bundle.get("shortcuts_resolved", [])
    ops = plan_bundle.get("planned_ops", [])
    dups = plan_bundle.get("duplicates_skipped", [])
    copy_ops = [o for o in ops if o["op"] in ("copy_remote_file", "move_staging_file", "upload_local_file")]

    L = [
        "# BÁO CÁO TIẾP NHẬN & NHẬP DỮ LIỆU MỚI — STORAGE",
        "",
        f"- **Thời gian:** {sc.today_vn()}",
        f"- **Chế độ nguồn:** `{plan_bundle.get('source_mode')}`",
        f"- **Số Shortcut ngoài đã phân giải:** `{sc.fmt_int(len(shortcuts))}`",
        f"- **Số tệp mới đạt chuẩn V6 cần nhập:** `{sc.fmt_int(len(copy_ops))}`",
        f"- **Số tệp trùng toàn kho đã tự động loại trừ (`TRUNG_TOAN_KHO`):** `{sc.fmt_int(len(dups))}`",
    ]
    if exec_result:
        L.append(
            f"- **Kết quả thực thi (`{exec_result['batch_id']}`):** "
            f"`{len(exec_result['executed'])}` thành công, `{len(exec_result['failed'])}` lỗi"
        )
    L.append("")

    if shortcuts:
        L += [
            "## 1. Phân giải Shortcut tại `[07] KIỂM TRA/[04] NHẬP DỮ LIỆU`",
            "",
            sc.md_table(
                ["Shortcut", "ID Đích", "Tên Gốc Đích", "Nhánh Đích Chuẩn V6", "Tệp Mới", "Bản Trùng Bỏ Qua"],
                [
                    (
                        f"`{s['shortcut_name']}`",
                        f"`{s['target_id']}`",
                        f"`{s['target_name']}`",
                        f"`{s['dest_branch'].replace(sc.ROOT_NAME + '/', '')}`",
                        sc.fmt_int(s["files_to_copy"]),
                        sc.fmt_int(s["duplicates_skipped"]),
                    )
                    for s in shortcuts
                ],
                ["l", "l", "l", "l", "r", "r"],
            ),
            "",
        ]

    L += ["## 2. Danh sách tệp mới nhập & chuẩn hóa tên Chuẩn V6 (hiển thị tối đa 100)", ""]
    if copy_ops:
        L.append(
            sc.md_table(
                ["Tên Gốc", "Tên Chuẩn V6 Mới", "Nhánh Đích", "Dung Lượng"],
                [
                    (
                        f"`{o['source_name']}`",
                        f"`{o['target_name']}`",
                        f"`{o['dest_parent_path'].replace(sc.ROOT_NAME + '/', '')}`",
                        sc.human_size(o.get("size")),
                    )
                    for o in copy_ops[:100]
                ],
                ["l", "l", "l", "r"],
            )
        )
    else:
        L.append("_Không có tệp mới cần nhập._")
    L.append("")

    L += ["## 3. Tệp trùng lặp đã có sẵn trong kho (`TRUNG_TOAN_KHO`, hiển thị tối đa 100)", ""]
    if dups:
        L.append(
            sc.md_table(
                ["Tên Tệp Nguồn", "Dung Lượng", "Bản Đã Có Trong Kho", "Vị Trí Hiện Tại"],
                [
                    (
                        f"`{d['source_name']}`",
                        sc.human_size(d.get("size")),
                        f"`{d['existing_name']}`",
                        f"`{d['existing_path'].replace(sc.ROOT_NAME + '/', '')}`",
                    )
                    for d in dups[:100]
                ],
                ["l", "r", "l", "l"],
            )
        )
    else:
        L.append("_Không có tệp trùng lặp._")

    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser(description="Tiếp nhận, phân loại & nhập dữ liệu mới vào [A] STORAGE (Chuẩn V6, v3.0).")
    ap.add_argument("--tu-khu-nhap", action="store_true", help="Quét khu tiếp nhận `[07] KIỂM TRA/[04] NHẬP DỮ LIỆU`")
    ap.add_argument("--nguon-drive", help="ID hoặc URL của tệp/thư mục Google Drive cần nhập vào kho")
    ap.add_argument("--nguon-cuc-bo", help="Đường dẫn tệp hoặc thư mục trên máy cục bộ cần tải lên kho")
    ap.add_argument("--dich", help="Chỉ định tường minh nhánh đích (nếu bỏ trống sẽ tự động phân loại theo chủ đề)")
    ap.add_argument("--gop-phang", action="store_true", help="Gộp thẳng tệp vào nhánh đích thay vì giữ thư mục con")
    ap.add_argument("--khong-tao-tong-quan", action="store_true", help="Không tự tạo [00] TỔNG QUAN cho thư mục mới")
    ap.add_argument("--tai-len", action="store_true", help="Đăng báo cáo nhập dữ liệu lên [00] TỔNG QUAN/[02] NHẬT KÍ")
    ap.add_argument("--thuc-thi", action="store_true", help="Thực sự sao chép/di chuyển/tải lên Drive (mặc định chạy thử)")
    ap.add_argument("--dong-y", action="store_true", help="Không hỏi xác nhận")
    args = ap.parse_args()

    index = sc.load_index()
    drive = sc.create_drive()

    if args.nguon_cuc_bo:
        plan_bundle = plan_ingest_from_local(Path(args.nguon_cuc_bo), index, explicit_dest=args.dich)
    elif args.nguon_drive:
        tid = sc.extract_drive_id(args.nguon_drive)
        tinfo = drive.info(tid)
        tname = tinfo.get("name", tid).strip()
        tmime = tinfo.get("mimeType", "")
        by_full, by_main = build_repo_dedup_lookup(index)
        dest_branch = auto_classify_destination(tname, tname, tmime, index, args.dich)
        planned_ops: List[dict] = []
        dups: List[dict] = []
        if tmime == sc.FOLDER_MIME:
            ext_tree = _crawl_external_drive_folder(drive, tid, tname)
            for rel_p, node in sorted(ext_tree.items()):
                for ch in node.get("items", []):
                    if ch.get("mimeType") == sc.FOLDER_MIME:
                        continue
                    ch_sz = int(ch["size"]) if ch.get("size") is not None else None
                    dm = check_duplicate_in_repo(ch["name"], ch.get("mimeType", ""), ch_sz, by_full, by_main)
                    if dm:
                        dups.append({
                            "source_id": ch["id"], "source_name": ch["name"], "size": ch_sz,
                            "existing_path": dm[0], "existing_name": dm[1]["name"], "existing_id": dm[1]["id"],
                        })
                    else:
                        v6_n = normalize_ingested_file_name(ch["name"], ch.get("mimeType", ""), dest_branch, source_hint=tname)
                        planned_ops.append({
                            "op": "copy_remote_file", "source_id": ch["id"], "source_name": ch["name"],
                            "dest_parent_path": dest_branch, "target_name": v6_n,
                            "mimeType": ch.get("mimeType", ""), "size": ch_sz,
                        })
        else:
            tsz = int(tinfo["size"]) if tinfo.get("size") is not None else None
            dm = check_duplicate_in_repo(tname, tmime, tsz, by_full, by_main)
            if dm:
                dups.append({
                    "source_id": tid, "source_name": tname, "size": tsz,
                    "existing_path": dm[0], "existing_name": dm[1]["name"], "existing_id": dm[1]["id"],
                })
            else:
                v6_n = normalize_ingested_file_name(tname, tmime, dest_branch)
                planned_ops.append({
                    "op": "copy_remote_file", "source_id": tid, "source_name": tname,
                    "dest_parent_path": dest_branch, "target_name": v6_n, "mimeType": tmime, "size": tsz,
                })
        plan_bundle = {
            "source_mode": f"drive:{tid}",
            "shortcuts_resolved": [],
            "planned_ops": planned_ops,
            "duplicates_skipped": dups,
        }
    else:
        # Mặc định: quét khu tiếp nhận `[07] KIỂM TRA/[04] NHẬP DỮ LIỆU`
        plan_bundle = plan_ingest_from_staging(
            index,
            drive,
            explicit_dest=args.dich,
            flatten_into_dest=args.gop_phang,
        )

    plan_path = sc.data_dir() / "planned_ingest.json"
    sc.write_json(plan_path, plan_bundle, indent=2)

    ops = plan_bundle["planned_ops"]
    dups = plan_bundle["duplicates_skipped"]
    scs = plan_bundle["shortcuts_resolved"]
    sc.log(
        f"\n=== KẾ HOẠCH NHẬP DỮ LIỆU MỚI ===\n"
        f"  • Shortcut phân giải : {len(scs)}\n"
        f"  • Thao tác dự kiến   : {len(ops)}\n"
        f"  • Bản trùng bỏ qua   : {len(dups)}\n"
        f"  • Tệp kế hoạch       : {plan_path}"
    )
    for s in scs:
        sc.log(
            f"  [SHORTCUT] `{s['shortcut_name']}` → đích `{s['target_name']}` ({s['target_id']}) "
            f"| nhánh đích: `{s['dest_branch']}` | tệp mới: {s['files_to_copy']} | trùng: {s['duplicates_skipped']}"
        )
    for o in ops[:25]:
        sc.log(f"  • [{o['op']}] `{o.get('source_name', '')}` → `{o.get('dest_parent_path', '')}/{o.get('target_name', '')}`")
    if len(ops) > 25:
        sc.log(f"  ... và {len(ops) - 25} thao tác khác.")

    exec_res = None
    if args.thuc_thi and ops:
        if sc.confirm(f"Thực thi {len(ops)} thao tác nhập dữ liệu lên Google Drive?", args.dong_y):
            exec_res = execute_ingest_plan(
                plan_bundle,
                index,
                drive=drive,
                init_tong_quan=not args.khong_tao_tong_quan,
            )
            sc.log(f"Hoàn tất nhập dữ liệu (`{exec_res['batch_id']}`): {len(exec_res['executed'])} thành công, {len(exec_res['failed'])} lỗi.")
    elif ops:
        sc.log("(Chạy thử — thêm --thuc-thi để nhập dữ liệu vào kho.)")

    rep_md = build_ingest_report(plan_bundle, exec_res)
    base_name = f"Báo Cáo Nhập Dữ Liệu Mới - Storage, {sc.today_vn()}"
    md_out = sc.reports_dir() / f"{base_name}.md"
    md_out.write_text(rep_md, encoding="utf-8")
    sc.log(f"Báo cáo: {md_out}")

    if args.tai_len:
        fid = sc.publish_file(drive, md_out, sc.nhat_ki_id())
        sc.log(f"Đã tải báo cáo lên [02] NHẬT KÍ: {sc.drive_url(fid)}")


if __name__ == "__main__":
    main()
