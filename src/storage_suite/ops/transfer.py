#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QUẢN LÝ SAO CHÉP, DI CHUYỂN & SHORTCUT — [A] STORAGE (CHUẨN V6, v3.0)
=====================================================================
Chương trình `[10] SAO CHÉP DI CHUYỂN/transfer_manager.py` phục vụ các tác vụ:
1. `sao-chep`    : Sao chép tệp đơn, nhiều tệp, hoặc **sao chép đệ quy toàn bộ cây thư mục** sang nhánh đích.
2. `di-chuyen`   : Di chuyển tệp hoặc thư mục sang nhánh đích, kiểm tra trước quyền `capabilities`
                   (`canMoveItemOutOfDrive,canEdit`) để tách riêng mục `KHONG_CO_QUYEN`.
3. `tao-shortcut`: Tạo shortcut chuẩn V6 tại thư mục đích trỏ tới mục nguồn.
4. `lo-kich-ban` : Thực thi kịch bản hàng loạt từ tệp `.json` hoặc `.csv` (hỗ trợ cả ngàn mục).
5. `hoan-tac`    : Hoàn tác an toàn theo mã lô (`batch_id`) từ `<STORAGE_DATA_DIR>/transfer_log.json`
                   (đưa mục di chuyển về chỗ cũ & đổi lại tên gốc; đưa bản sao/shortcut mới tạo vào `[07] KIỂM TRA`).

Tính năng thông minh Chuẩn V6:
- Tự động chuẩn hóa tên tệp sang `Tên Viết Hoa Đầu Mỗi Chữ - Thông Tin Bổ Sung.[đuôi]` (`--chuan-hoa-ten`).
- Tự động cấp số thứ tự `[STT]` kế tiếp chưa dùng tại thư mục đích khi chuyển/sao chép thư mục (`--tu-danh-stt`).
- Chống trùng lặp tại đích (`--bo-qua-trung`): bỏ qua nếu thư mục đích đã có tệp cùng tên chuẩn hóa & cùng kích thước.
- Mặc định **CHẠY THỬ (dry-run)**; chỉ ghi lên Drive khi truyền `--thuc-thi`.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


from storage_suite import core as sc


def _folder_context_title(dest_path: str) -> str:
    if not dest_path or dest_path == sc.ROOT_NAME:
        return "Storage"
    segs = [s for s in dest_path.split("/") if s and s != sc.TONG_QUAN_FOLDER]
    last = segs[-1] if segs else "Storage"
    if last == sc.ROOT_NAME:
        return "Storage"
    clean = re.sub(r"^\[\d{2,3}\]\s*", "", last)
    clean = re.sub(r"^\[([^\]]+)\]\s*(.+)$", lambda m: f"{m.group(1).strip()} - {m.group(2).strip()}", clean)
    clean = re.sub(r"^\[([^\]]+)\]$", r"\1", clean)
    clean = re.sub(r"\s*_+\s*", " ", clean).strip()
    return sc.title_case_vn(clean)


def format_v6_transfer_name(
    name: str,
    mime: str,
    dest_path: str,
    is_folder: bool,
    existing_dest_items: Optional[Sequence[dict]] = None,
    normalize_v6: bool = True,
    auto_stt: bool = True,
) -> str:
    """
    Chuẩn hóa tên mục khi sao chép / di chuyển vào `dest_path`:
    - Thư mục: `[STT] TÊN IN HOA CÓ DẤU` (tự cấp `[STT]` tiếp theo nếu chưa có hoặc bị trùng STT tại đích).
    - Tệp tin: `Tên Viết Hoa Đầu Mỗi Chữ Có Dấu - Thông Tin Bổ Sung.[đuôi]`.
    """
    existing = list(existing_dest_items or [])
    clean = sc.safe_fix_name(name, is_folder=is_folder, mime=mime)

    if is_folder:
        if not normalize_v6 and not auto_stt:
            return clean
        m = re.match(r"^\[(\d{2,3})\]\s*(.+)$", clean)
        body = m.group(2).strip().upper() if m else re.sub(r"^\[\d{1,3}\]\s*", "", clean).strip().upper()
        body = re.sub(r"\s*_+\s*", " ", body).strip()
        used_stts = set()
        for it in existing:
            if it.get("mimeType") == sc.FOLDER_MIME:
                m_ex = re.match(r"^\[(\d{2,3})\]", it.get("name", ""))
                if m_ex:
                    used_stts.add(int(m_ex.group(1)))
        if m and not auto_stt:
            return f"[{int(m.group(1)):02d}] {body}"
        if m and int(m.group(1)) not in used_stts:
            return f"[{int(m.group(1)):02d}] {body}"
        stt_prefix = sc.next_available_stt(existing)
        return f"{stt_prefix} {body}"

    if not normalize_v6 or sc.is_tech_exception(dest_path, clean):
        return clean
    if clean.startswith("Danh Mục Hệ Thống - ") or clean.startswith("Tổng Quan Hệ Thống - "):
        return clean

    base, ext = sc.split_ext(clean, mime)
    base = re.sub(r"^\[\d{1,3}\]\s*", "", base).strip()
    base = re.sub(r"^(\d{2,4}_)?\d{6}_", "", base).strip()
    if " - " in base:
        parts = [p.strip() for p in base.split(" - ") if p.strip()]
        main_title = sc.title_case_vn(parts[0])
        rest = " - ".join(sc.title_case_vn(p) for p in parts[1:])
        new_base = f"{main_title} - {rest}"
    else:
        main_title = sc.title_case_vn(base)
        ctx = _folder_context_title(dest_path)
        new_base = f"{main_title} - {ctx}"
    return f"{new_base}.{ext.lower()}" if ext else new_base


def resolve_repo_target(
    spec: str,
    index: dict,
    drive: Optional[sc.Drive] = None,
) -> Dict[str, Any]:
    """
    Phân giải `spec` (có thể là đường dẫn trong kho, URL Google Drive, hoặc ID) thành:
    `{"id": str, "name": str, "path": str, "mimeType": str, "size": Optional[int], "parent_path": str, "parent_id": str}`.
    """
    raw = (spec or "").strip()
    if not raw:
        raise ValueError("Đầu vào nguồn/đích trống.")

    folder_paths, items_by_id = sc.build_id_map(index)
    folder_paths[sc.ROOT_ID] = sc.ROOT_NAME

    # 1. Thử khớp theo đường dẫn kho
    norm_p = sc.normalize_branch(raw)
    if norm_p and norm_p in index:
        d = index[norm_p]
        parent_p = norm_p.rsplit("/", 1)[0] if "/" in norm_p else ""
        return {
            "id": d["id"],
            "name": norm_p.split("/")[-1],
            "path": norm_p,
            "mimeType": sc.FOLDER_MIME,
            "size": None,
            "parent_path": parent_p,
            "parent_id": index.get(parent_p, {}).get("id", ""),
        }

    # Đường dẫn tới một tệp nằm trong thư mục cha thuộc index
    if norm_p and "/" in norm_p:
        parent_p, child_name = norm_p.rsplit("/", 1)
        if parent_p in index:
            for it in index[parent_p].get("items", []):
                if sc.nfc(it.get("name", "")) == sc.nfc(child_name):
                    return {
                        "id": it["id"],
                        "name": it["name"],
                        "path": f"{parent_p}/{it['name']}" if it.get("mimeType") == sc.FOLDER_MIME else parent_p,
                        "mimeType": it.get("mimeType", ""),
                        "size": it.get("size"),
                        "parent_path": parent_p,
                        "parent_id": index[parent_p].get("id", ""),
                    }

    # 2. Thử trích xuất ID từ URL hoặc ID trực tiếp
    cand_id = sc.extract_drive_id(raw)
    if cand_id in items_by_id:
        parent_p, it = items_by_id[cand_id]
        is_f = it.get("mimeType") == sc.FOLDER_MIME
        return {
            "id": cand_id,
            "name": it.get("name", ""),
            "path": f"{parent_p}/{it['name']}" if is_f else parent_p,
            "mimeType": it.get("mimeType", ""),
            "size": it.get("size"),
            "parent_path": parent_p,
            "parent_id": index.get(parent_p, {}).get("id", ""),
        }
    if cand_id in folder_paths:
        p = folder_paths[cand_id]
        parent_p = p.rsplit("/", 1)[0] if "/" in p else ""
        return {
            "id": cand_id,
            "name": p.split("/")[-1],
            "path": p,
            "mimeType": sc.FOLDER_MIME,
            "size": None,
            "parent_path": parent_p,
            "parent_id": index.get(parent_p, {}).get("id", ""),
        }

    # 3. Hỏi trực tiếp Drive nếu mục nằm ngoài chỉ mục hiện tại
    if drive is not None and re.match(r"^[A-Za-z0-9_-]{10,}$", cand_id):
        info = drive.info(cand_id)
        if info and info.get("id"):
            parents = info.get("parents") or []
            p_id = parents[0] if parents else ""
            p_path = folder_paths.get(p_id, "")
            is_f = info.get("mimeType") == sc.FOLDER_MIME
            nm = info.get("name", cand_id)
            return {
                "id": info["id"],
                "name": nm,
                "path": (f"{p_path}/{nm}" if (is_f and p_path) else (p_path or nm)),
                "mimeType": info.get("mimeType", ""),
                "size": int(info["size"]) if info.get("size") else None,
                "parent_path": p_path,
                "parent_id": p_id,
            }

    raise ValueError(f"Không tìm thấy mục nguồn/đích: `{spec}`")


def _norm_dup_sig(name: str, mime: str, size: Optional[int]) -> Tuple[str, int]:
    base, ext = sc.split_ext(name, mime)
    k = re.sub(r"[^a-z0-9]+", "", sc.strip_accents(sc.nfc(base)).lower())
    return f"{k}.{ext.lower()}", int(size or 0)


def _expand_folder_copy_ops(
    src_folder_id: str,
    src_folder_path: str,
    dest_parent_id: str,
    dest_parent_path: str,
    new_folder_name: str,
    index: dict,
    drive: Optional[sc.Drive],
    normalize_v6: bool,
) -> List[dict]:
    """Mở rộng đệ quy cây thư mục nguồn thành danh sách thao tác `mkdir_copy` và `copy_file`."""
    ops: List[dict] = []
    dest_folder_path = f"{dest_parent_path}/{new_folder_name}" if dest_parent_path else new_folder_name
    ops.append({
        "op": "mkdir_copy",
        "source_id": src_folder_id,
        "source_name": src_folder_path.split("/")[-1],
        "source_path": src_folder_path,
        "dest_parent_id": dest_parent_id,
        "dest_parent_path": dest_parent_path,
        "target_name": new_folder_name,
        "target_path": dest_folder_path,
        "mimeType": sc.FOLDER_MIME,
    })

    # Lấy danh sách mục con từ index (hoặc gọi drive.ls nếu thư mục ngoài index)
    if src_folder_path in index:
        children = list(index[src_folder_path].get("items", []))
    elif drive is not None:
        children = drive.ls(src_folder_id)
    else:
        children = []

    sim_items: List[dict] = []
    for ch in children:
        ch_mime = ch.get("mimeType", "")
        ch_name = ch.get("name", "")
        if ch_mime == sc.FOLDER_MIME:
            if ch_name == sc.TONG_QUAN_FOLDER:
                sub_target_name = sc.TONG_QUAN_FOLDER
            else:
                sub_target_name = format_v6_transfer_name(
                    ch_name, ch_mime, dest_folder_path, is_folder=True,
                    existing_dest_items=sim_items, normalize_v6=normalize_v6, auto_stt=False,
                )
            sim_items.append({"id": ch["id"], "name": sub_target_name, "mimeType": sc.FOLDER_MIME})
            child_src_path = f"{src_folder_path}/{ch_name}" if src_folder_path else ch_name
            ops.extend(_expand_folder_copy_ops(
                ch["id"], child_src_path, f"$FOLDER:{dest_folder_path}", dest_folder_path,
                sub_target_name, index, drive, normalize_v6,
            ))
        elif ch_mime == sc.SHORTCUT_MIME:
            ops.append({
                "op": "shortcut",
                "source_id": ch["id"],
                "source_name": ch_name,
                "source_path": src_folder_path,
                "dest_parent_id": f"$FOLDER:{dest_folder_path}",
                "dest_parent_path": dest_folder_path,
                "target_name": ch_name,
                "mimeType": ch_mime,
            })
        else:
            target_file_name = format_v6_transfer_name(
                ch_name, ch_mime, dest_folder_path, is_folder=False,
                existing_dest_items=sim_items, normalize_v6=normalize_v6, auto_stt=False,
            )
            sim_items.append({"id": ch["id"], "name": target_file_name, "mimeType": ch_mime, "size": ch.get("size")})
            ops.append({
                "op": "copy_file",
                "source_id": ch["id"],
                "source_name": ch_name,
                "source_path": src_folder_path,
                "dest_parent_id": f"$FOLDER:{dest_folder_path}",
                "dest_parent_path": dest_folder_path,
                "target_name": target_file_name,
                "mimeType": ch_mime,
                "size": ch.get("size"),
            })
    return ops


def plan_transfers(
    specs: Sequence[Dict[str, Any]],
    index: dict,
    drive: Optional[sc.Drive] = None,
    skip_duplicates: bool = True,
) -> Tuple[List[dict], List[dict]]:
    """
    Lập kế hoạch cho danh sách yêu cầu chuyển/sao chép/shortcut:
    Mỗi phần tử trong `specs` có dạng:
      `{"op": "copy"|"move"|"shortcut", "source": str, "dest": str, "new_name": Optional[str],
        "normalize_v6": bool, "auto_stt": bool}`
    Trả về `(planned_ops, skipped_items)`.
    """
    planned: List[dict] = []
    skipped: List[dict] = []

    # Theo dõi danh sách mục tại từng thư mục đích để cấp STT tăng dần và phát hiện trùng lặp trong cùng lô
    dest_items_map: Dict[str, List[dict]] = {}

    def get_dest_items(dest_path: str, dest_id: str) -> List[dict]:
        key = dest_path or dest_id
        if key not in dest_items_map:
            if dest_path and dest_path in index:
                dest_items_map[key] = [dict(x) for x in index[dest_path].get("items", [])]
            elif drive is not None and dest_id:
                dest_items_map[key] = [dict(x) for x in drive.ls(dest_id)]
            else:
                dest_items_map[key] = []
        return dest_items_map[key]

    for sp in specs:
        op_raw = sp.get("op", "copy").lower()
        if op_raw in ("sao-chep", "cp", "copy"):
            op = "copy"
        elif op_raw in ("di-chuyen", "mv", "move"):
            op = "move"
        elif op_raw in ("tao-shortcut", "shortcut", "ln"):
            op = "shortcut"
        else:
            raise ValueError(f"Thao tác không hợp lệ: {op_raw}")

        src = resolve_repo_target(sp["source"], index, drive=drive)
        dst = resolve_repo_target(sp["dest"], index, drive=drive)
        if dst["mimeType"] != sc.FOLDER_MIME:
            raise ValueError(f"Đích phải là một thư mục: `{sp['dest']}`")

        is_folder = src["mimeType"] == sc.FOLDER_MIME
        dest_items = get_dest_items(dst["path"], dst["id"])
        explicit_name = sp.get("new_name")
        normalize_v6 = bool(sp.get("normalize_v6", False))
        auto_stt = bool(sp.get("auto_stt", True))

        if explicit_name:
            target_name = sc.nfc(explicit_name.strip())
        else:
            target_name = format_v6_transfer_name(
                src["name"],
                src["mimeType"],
                dst["path"],
                is_folder=is_folder,
                existing_dest_items=dest_items,
                normalize_v6=normalize_v6,
                auto_stt=auto_stt if is_folder else False,
            )

        # Kiểm tra nếu di chuyển về chính thư mục hiện tại
        if op == "move" and src.get("parent_id") and src["parent_id"] == dst["id"] and target_name == src["name"]:
            skipped.append({"source": src["name"], "dest": dst["path"], "reason": "da_o_thu_muc_dich"})
            continue

        # Kiểm tra trùng lặp tại thư mục đích cho tệp
        if not is_folder and skip_duplicates and op in ("copy", "move"):
            src_sig = _norm_dup_sig(target_name, src["mimeType"], src.get("size"))
            dup_found = any(
                it.get("mimeType") != sc.FOLDER_MIME
                and _norm_dup_sig(it.get("name", ""), it.get("mimeType", ""), it.get("size")) == src_sig
                for it in dest_items
            )
            if dup_found:
                skipped.append({
                    "source_id": src["id"],
                    "source": src["name"],
                    "dest": dst["path"],
                    "reason": "trung_tai_dich",
                })
                continue

        # Tránh đụng tên trực tiếp tại đích
        existing_names = {sc.nfc(it.get("name", "")) for it in dest_items}
        if sc.nfc(target_name) in existing_names and not is_folder:
            base, ext = sc.split_ext(target_name, src["mimeType"])
            idx_n = 2
            while sc.nfc(target_name) in existing_names:
                cand_base = f"{base}, Bản {idx_n:02d}"
                target_name = f"{cand_base}.{ext}" if ext else cand_base
                idx_n += 1

        dest_items.append({
            "id": src["id"],
            "name": target_name,
            "mimeType": src["mimeType"] if "mimeType" in src else "",
            "size": src.get("size"),
        })

        if op == "copy" and is_folder:
            planned.extend(_expand_folder_copy_ops(
                src["id"],
                src["path"],
                dst["id"],
                dst["path"],
                target_name,
                index,
                drive,
                normalize_v6=normalize_v6,
            ))
        elif op == "copy":
            planned.append({
                "op": "copy_file",
                "source_id": src["id"],
                "source_name": src["name"],
                "source_path": src["parent_path"],
                "dest_parent_id": dst["id"],
                "dest_parent_path": dst["path"],
                "target_name": target_name,
                "mimeType": src["mimeType"],
                "size": src.get("size"),
            })
        elif op == "move":
            planned.append({
                "op": "move",
                "source_id": src["id"],
                "source_name": src["name"],
                "source_path": src["parent_path"],
                "old_parent_id": src.get("parent_id", ""),
                "dest_parent_id": dst["id"],
                "dest_parent_path": dst["path"],
                "target_name": target_name,
                "mimeType": src["mimeType"],
                "size": src.get("size"),
            })
        elif op == "shortcut":
            planned.append({
                "op": "shortcut",
                "source_id": src["id"],
                "source_name": src["name"],
                "source_path": src["parent_path"],
                "dest_parent_id": dst["id"],
                "dest_parent_path": dst["path"],
                "target_name": target_name,
                "mimeType": sc.SHORTCUT_MIME,
            })

    return planned, skipped


def execute_transfer_plan(
    planned: List[dict],
    index: dict,
    drive: Optional[sc.Drive] = None,
    workers: int = 8,
) -> Dict[str, Any]:
    """
    Thực thi kế hoạch sao chép / di chuyển / tạo shortcut, cập nhật `storage_index.json`
    và lưu lô hoàn tác vào `<STORAGE_DATA_DIR>/transfer_log.json`.
    """
    drive = drive or sc.create_drive()
    batch_id = f"tr_{sc.now_stamp()}"
    created_folders: Dict[str, str] = {}  # target_path -> new_folder_id
    executed_ops: List[dict] = []
    blocked_ops: List[dict] = []
    failed_ops: List[dict] = []

    # 1. Kiểm tra quyền trước cho các lệnh `move`
    move_ops = [op for op in planned if op["op"] == "move"]
    if move_ops:
        caps_map = (
            drive.stream_capabilities([m["source_id"] for m in move_ops], "canMoveItemOutOfDrive,canEdit", concurrency=max(8, workers))
            if hasattr(drive, "stream_capabilities")
            else {m["source_id"]: drive.capabilities(m["source_id"], "canMoveItemOutOfDrive,canEdit") for m in move_ops}
        )
    else:
        caps_map = {}

    for step in planned:
        kind = step["op"]
        dest_pid = step["dest_parent_id"]
        if isinstance(dest_pid, str) and dest_pid.startswith("$FOLDER:"):
            folder_key = dest_pid[len("$FOLDER:"):]
            dest_pid = created_folders.get(folder_key, "")
            if not dest_pid:
                failed_ops.append({**step, "error": f"Thư mục cha `{folder_key}` chưa tạo được"})
                continue

        try:
            if kind == "mkdir_copy":
                new_dir_id = drive.ensure_folder(step["target_name"], dest_pid)
                created_folders[step["target_path"]] = new_dir_id
                # Cập nhật chỉ mục cục bộ
                if step["dest_parent_path"] in index:
                    parent_items = index[step["dest_parent_path"]].setdefault("items", [])
                    if not any(it.get("id") == new_dir_id for it in parent_items):
                        parent_items.append({
                            "id": new_dir_id,
                            "name": step["target_name"],
                            "mimeType": sc.FOLDER_MIME,
                            "modifiedTime": sc.now_utc_iso(),
                        })
                index.setdefault(step["target_path"], {
                    "id": new_dir_id,
                    "depth": step["target_path"].count("/"),
                    "items": [],
                })
                executed_ops.append({
                    **step,
                    "dest_parent_id": dest_pid,
                    "created_id": new_dir_id,
                    "ts": int(time.time()),
                })

            elif kind == "copy_file":
                new_id = drive.copy(step["source_id"], step["target_name"], dest_pid)
                if step["dest_parent_path"] in index and new_id:
                    index[step["dest_parent_path"]].setdefault("items", []).append({
                        "id": new_id,
                        "name": step["target_name"],
                        "mimeType": step["mimeType"],
                        "size": step.get("size"),
                        "modifiedTime": sc.now_utc_iso(),
                    })
                executed_ops.append({
                    **step,
                    "dest_parent_id": dest_pid,
                    "created_id": new_id,
                    "ts": int(time.time()),
                })

            elif kind == "shortcut":
                sc_id = drive.create_shortcut(step["source_id"], dest_pid, shortcut_name=step["target_name"])
                if step["dest_parent_path"] in index and sc_id:
                    index[step["dest_parent_path"]].setdefault("items", []).append({
                        "id": sc_id,
                        "name": step["target_name"],
                        "mimeType": sc.SHORTCUT_MIME,
                        "modifiedTime": sc.now_utc_iso(),
                    })
                executed_ops.append({
                    **step,
                    "dest_parent_id": dest_pid,
                    "created_id": sc_id,
                    "ts": int(time.time()),
                })

            elif kind == "move":
                fid = step["source_id"]
                caps = caps_map.get(fid, {})
                if caps and (caps.get("canMoveItemOutOfDrive") is False or (
                    "canMoveItemOutOfDrive" not in caps and caps.get("canEdit") is False
                )):
                    blocked_ops.append({**step, "permission_error": "KHONG_CO_QUYEN (canMoveItemOutOfDrive/canEdit=False)"})
                    continue

                old_pid = step.get("old_parent_id") or index.get(step["source_path"], {}).get("id", "")
                if dest_pid and dest_pid != old_pid:
                    drive.move(fid, dest_pid)
                if step["target_name"] != step["source_name"]:
                    drive.rename(fid, step["target_name"])

                # Cập nhật chỉ mục cục bộ
                moved_item = None
                if step["source_path"] in index:
                    src_items = index[step["source_path"]].get("items", [])
                    for it in src_items:
                        if it.get("id") == fid:
                            moved_item = dict(it)
                            break
                    index[step["source_path"]]["items"] = [it for it in src_items if it.get("id") != fid]
                if moved_item is None:
                    moved_item = {"id": fid, "name": step["target_name"], "mimeType": step["mimeType"], "size": step.get("size")}
                else:
                    moved_item["name"] = step["target_name"]
                    moved_item["modifiedTime"] = sc.now_utc_iso()

                if step["dest_parent_path"] in index:
                    index[step["dest_parent_path"]].setdefault("items", []).append(moved_item)

                if step["mimeType"] == sc.FOLDER_MIME:
                    old_sub = f"{step['source_path']}/{step['source_name']}"
                    new_sub = f"{step['dest_parent_path']}/{step['target_name']}"
                    for k in [p for p in list(index.keys()) if p == old_sub or p.startswith(old_sub + "/")]:
                        nk = new_sub + k[len(old_sub):]
                        entry = index.pop(k)
                        entry["depth"] = nk.count("/")
                        index[nk] = entry

                executed_ops.append({
                    **step,
                    "old_parent_id": old_pid,
                    "dest_parent_id": dest_pid,
                    "ts": int(time.time()),
                })
        except sc.DriveError as e:
            failed_ops.append({**step, "error": str(e)[:250]})

    if executed_ops:
        sc.save_index(index)
        tlog = sc.read_json(sc.transfer_log_path(), []) or []
        tlog.append({
            "batch_id": batch_id,
            "created_iso": sc.now_utc_iso(),
            "operations": executed_ops,
            "restored": False,
        })
        sc.write_json(sc.transfer_log_path(), tlog, indent=1)

    return {
        "batch_id": batch_id,
        "executed": executed_ops,
        "blocked": blocked_ops,
        "failed": failed_ops,
    }


def undo_transfer_batch(
    batch_id: Optional[str] = None,
    drive: Optional[sc.Drive] = None,
    index: Optional[dict] = None,
    assume_yes: bool = False,
) -> int:
    """
    Hoàn tác một lô trong `transfer_log.json` (mặc định: lô gần nhất chưa hoàn tác).
    - `move`: di chuyển mục về `old_parent_id` và đổi lại `source_name`.
    - `copy_file` / `shortcut` / `mkdir_copy`: đưa mục mới tạo vào `[07] KIỂM TRA/[03] TỆP TRÙNG LẶP` (không xóa).
    """
    log_p = sc.transfer_log_path()
    tlog = sc.read_json(log_p, []) or []
    candidates = [b for b in tlog if not b.get("restored") and (not batch_id or b.get("batch_id") == batch_id)]
    if not candidates:
        sc.log("Không tìm thấy lô thao tác nào cần hoàn tác.")
        return 0
    target_batch = candidates[-1]
    ops = list(reversed(target_batch.get("operations", [])))
    if not sc.confirm(f"Hoàn tác lô `{target_batch['batch_id']}` ({len(ops)} thao tác)?", assume_yes):
        return 0

    drive = drive or sc.create_drive()
    index = index if index is not None else sc.load_index(required=False)
    quarantine_dup_id = drive.ensure_folder(
        sc.CONFIG.get("quarantine_subfolders", {}).get("duplicate", "[03] TỆP TRÙNG LẶP"),
        sc.quarantine_root_id(),
    )

    reverted = 0
    for op in ops:
        kind = op.get("op")
        try:
            if kind == "move":
                fid = op["source_id"]
                if op.get("old_parent_id") and op["old_parent_id"] != op.get("dest_parent_id"):
                    drive.move(fid, op["old_parent_id"])
                if op.get("source_name") and op["source_name"] != op.get("target_name"):
                    drive.rename(fid, op["source_name"])
                reverted += 1
            elif kind in ("copy_file", "shortcut", "mkdir_copy") and op.get("created_id"):
                drive.move(op["created_id"], quarantine_dup_id)
                reverted += 1
        except sc.DriveError as e:
            sc.log(f"  ! Lỗi hoàn tác {op.get('target_name')}: {str(e)[:180]}")

    target_batch["restored"] = True
    target_batch["restored_iso"] = sc.now_utc_iso()
    sc.write_json(log_p, tlog, indent=1)
    sc.log(f"Đã hoàn tác {reverted}/{len(ops)} thao tác của lô `{target_batch['batch_id']}`.")
    return reverted


def load_batch_manifest(manifest_file: Path) -> List[Dict[str, Any]]:
    """Đọc kịch bản hàng loạt từ tệp `.json` hoặc `.csv`."""
    p = Path(manifest_file)
    if not p.exists():
        raise SystemExit(f"Không tìm thấy tệp kịch bản: {p}")
    if p.suffix.lower() == ".json":
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "operations" in data:
            data = data["operations"]
        return list(data)
    specs = []
    with open(p, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            specs.append({
                "op": row.get("op") or row.get("thao_tac") or "copy",
                "source": row.get("source") or row.get("nguon") or "",
                "dest": row.get("dest") or row.get("dich") or "",
                "new_name": row.get("new_name") or row.get("ten_moi") or None,
                "normalize_v6": str(row.get("normalize_v6", "true")).lower() in ("1", "true", "yes", "co"),
                "auto_stt": str(row.get("auto_stt", "true")).lower() in ("1", "true", "yes", "co"),
            })
    return specs


def main() -> None:
    ap = argparse.ArgumentParser(description="Sao chép, di chuyển & tạo shortcut chuẩn V6 cho [A] STORAGE (v3.0).")
    ap.add_argument(
        "lenh",
        choices=["sao-chep", "di-chuyen", "tao-shortcut", "lo-kich-ban", "hoan-tac", "lich-su"],
        help="Thao tác cần thực hiện",
    )
    ap.add_argument("--nguon", nargs="+", help="Một hoặc nhiều ID / URL / đường dẫn nhánh nguồn")
    ap.add_argument("--dich", help="ID / URL / đường dẫn thư mục đích")
    ap.add_argument("--ten-moi", help="Tên mới tại đích (khi thao tác trên 1 mục nguồn)")
    ap.add_argument("--kich-ban", help="Đường dẫn tệp kịch bản .json hoặc .csv (cho lệnh `lo-kich-ban`)")
    ap.add_argument("--chuan-hoa-ten", action="store_true", help="Tự động chuẩn hóa tên đích theo Chuẩn V6")
    ap.add_argument("--tu-danh-stt", action="store_true", default=True, help="Tự cấp [STT] kế tiếp khi chuyển/sao chép thư mục")
    ap.add_argument("--cho-phep-trung", action="store_true", help="Không bỏ qua tệp trùng tại thư mục đích")
    ap.add_argument("--lo-id", help="Mã lô cần hoàn tác (mặc định: lô mới nhất)")
    ap.add_argument("--thuc-thi", action="store_true", help="Thực sự ghi lên Drive (mặc định: chạy thử)")
    ap.add_argument("--dong-y", action="store_true", help="Không hỏi xác nhận")
    ap.add_argument("--luong", type=int, default=8, help="Số luồng song song (mặc định 8)")
    args = ap.parse_args()

    if args.lenh == "lich-su":
        tlog = sc.read_json(sc.transfer_log_path(), []) or []
        if not tlog:
            sc.log("Chưa có lịch sử sao chép/di chuyển nào.")
            return
        for b in tlog[-10:]:
            status = "ĐÃ HOÀN TÁC" if b.get("restored") else "ĐANG HIỆU LỰC"
            sc.log(f"• {b['batch_id']} | {b.get('created_iso')} | {len(b.get('operations', []))} thao tác | {status}")
        return

    if args.lenh == "hoan-tac":
        if not args.thuc_thi:
            tlog = sc.read_json(sc.transfer_log_path(), []) or []
            cands = [b for b in tlog if not b.get("restored") and (not args.lo_id or b.get("batch_id") == args.lo_id)]
            if not cands:
                sc.log("Không có lô nào cần hoàn tác.")
            else:
                b = cands[-1]
                sc.log(f"[CHẠY THỬ] Sẽ hoàn tác lô `{b['batch_id']}` gồm {len(b.get('operations', []))} thao tác (thêm --thuc-thi để áp dụng).")
            return
        undo_transfer_batch(batch_id=args.lo_id, assume_yes=args.dong_y)
        return

    index = sc.load_index()
    drive = sc.create_drive()

    if args.lenh == "lo-kich-ban":
        if not args.kich_ban:
            raise SystemExit("Vui lòng chỉ định `--kich-ban <file.json|.csv>`.")
        specs = load_batch_manifest(Path(args.kich_ban))
    else:
        if not args.nguon or not args.dich:
            raise SystemExit("Vui lòng truyền đủ `--nguon <...>` và `--dich <...>`.")
        if args.ten_moi and len(args.nguon) > 1:
            raise SystemExit("Chỉ dùng `--ten-moi` khi truyền đúng 1 mục `--nguon`.")
        specs = [
            {
                "op": args.lenh,
                "source": s,
                "dest": args.dich,
                "new_name": args.ten_moi,
                "normalize_v6": args.chuan_hoa_ten,
                "auto_stt": args.tu_danh_stt,
            }
            for s in args.nguon
        ]

    planned, skipped = plan_transfers(
        specs,
        index,
        drive=drive,
        skip_duplicates=not args.cho_phep_trung,
    )

    sc.log(f"\n=== KẾ HOẠCH SAO CHÉP / DI CHUYỂN ({len(planned)} thao tác, bỏ qua {len(skipped)}) ===")
    for i, p in enumerate(planned[:30], 1):
        sc.log(f"  {i:02d}. [{p['op']}] `{p['source_name']}` → `{p['dest_parent_path']}/{p['target_name']}`")
    if len(planned) > 30:
        sc.log(f"  ... và {len(planned) - 30} thao tác khác.")
    for s in skipped[:15]:
        sc.log(f"  [BỎ QUA] `{s['source']}` → `{s['dest']}` ({s['reason']})")

    plan_out = sc.data_dir() / "planned_transfers.json"
    sc.write_json(plan_out, {"planned": planned, "skipped": skipped})
    sc.log(f"Chi tiết kế hoạch: {plan_out}")

    if not args.thuc_thi:
        sc.log("(Chạy thử — thêm --thuc-thi để thực hiện trên Google Drive.)")
        return
    if not planned:
        sc.log("Không có thao tác nào cần thực thi.")
        return
    if not sc.confirm(f"Thực thi {len(planned)} thao tác lên Google Drive?", args.dong_y):
        return

    res = execute_transfer_plan(planned, index, drive=drive, workers=args.luong)
    sc.log(
        f"\nHoàn tất lô `{res['batch_id']}`: thành công {len(res['executed'])}, "
        f"không có quyền {len(res['blocked'])}, lỗi {len(res['failed'])}."
    )


if __name__ == "__main__":
    main()
