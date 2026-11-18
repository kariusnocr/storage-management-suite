#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TRA CỨU TỨC THÌ, KIỂM TOÁN TỔNG QUAN, KIỂM TOÁN QUYỀN & DỌN THƯ MỤC RỖNG — [A] STORAGE (v3.0)
==============================================================================================
Chương trình `[12] TRA CỨU VÀ KIỂM TOÁN/storage_inspector.py` cung cấp 4 nhóm công cụ chuyên sâu:

1. `tim-kiem`            : Tra cứu tức thì (<0,2s) trên `storage_index.json` theo từ khóa (có/không dấu),
                           biểu thức chính quy (`--regex`), ID (`--id`), nhánh, loại mục, đuôi tệp, dung lượng, ngày sửa.
2. `kiem-toan-tong-quan` : Kiểm toán độ phủ bộ 3 quản trị chuẩn ở từng thư mục:
                           • Thư mục con `[00] TỔNG QUAN`
                           • Tệp mô tả `Tổng Quan Hệ Thống - <Tên Thư Mục>.md`
                           • Bảng Google Sheets `Danh Mục Hệ Thống - <Tên Thư Mục>`
                           Hỗ trợ `--bu-dap --thuc-thi` để tự động tạo `[00] TỔNG QUAN` và sinh tệp `Tổng Quan Hệ Thống - *.md`.
3. `kiem-toan-quyen`     : Rà soát hàng loạt quyền `canMoveItemOutOfDrive,canEdit` bằng `stream_capabilities`
                           để phát hiện các tệp/thư mục bị hạn chế quyền chỉnh sửa/di chuyển.
4. `don-thu-muc-rong`    : Phát hiện thư mục rỗng (kể cả rỗng lồng nhau bottom-up) và di chuyển an toàn
                           vào `[07] KIỂM TRA/[05] THƯ MỤC RỖNG` khi truyền `--thuc-thi` (kèm nhật kí hoàn tác).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple


def _nap_thu_vien_loi():
    here = Path(__file__).resolve().parent
    cands = [Path(os.environ["STORAGE_CORE_DIR"])] if os.environ.get("STORAGE_CORE_DIR") else []
    for base in [here, *list(here.parents)[:3]]:
        cands.append(base)
        if base.is_dir():
            cands += [d for d in base.iterdir() if d.is_dir() and "THƯ VIỆN LÕI" in d.name]
    for c in cands:
        if (c / "storage_core.py").exists():
            sys.path.insert(0, str(c))
            import storage_core  # noqa: E402
            return storage_core
    raise SystemExit("Không tìm thấy storage_core.py — đặt `[01] THƯ VIỆN LÕI` cạnh chương trình hoặc đặt STORAGE_CORE_DIR.")


sc = _nap_thu_vien_loi()


# ---------------------------------------------------------------------------
# 1. TRA CỨU TỨC THÌ TRÊN CHỈ MỤC (tim-kiem)
# ---------------------------------------------------------------------------

def search_index(
    index: dict,
    query: Optional[str] = None,
    regex_pat: Optional[str] = None,
    item_id: Optional[str] = None,
    branch: Optional[str] = None,
    kind: str = "all",
    exts: Optional[Sequence[str]] = None,
    min_mb: Optional[float] = None,
    max_mb: Optional[float] = None,
    modified_after: Optional[str] = None,
    include_quarantine: bool = False,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Tìm kiếm nhanh trên `storage_index.json` với bộ lọc đa tiêu chí."""
    q_tokens = []
    if query:
        q_norm = sc.strip_accents(sc.nfc(query)).lower().strip()
        q_tokens = [t for t in q_norm.split() if t]
    rx = re.compile(regex_pat, re.I) if regex_pat else None
    ext_set = {e.lower().lstrip(".") for e in (exts or []) if e.strip()}
    min_b = int(min_mb * 1024 * 1024) if min_mb is not None else None
    max_b = int(max_mb * 1024 * 1024) if max_mb is not None else None
    norm_branch = sc.normalize_branch(branch) if branch else None
    if norm_branch == sc.ROOT_NAME:
        norm_branch = None

    matches: List[Dict[str, Any]] = []
    for path, it in sc.iter_items(index, norm_branch):
        if not include_quarantine and sc.is_quarantine_path(path):
            continue
        mime = it.get("mimeType", "")
        is_f = mime == sc.FOLDER_MIME
        name = it.get("name", "")
        fid = it.get("id", "")
        sz = int(it.get("size") or 0) if not is_f else 0
        mod = it.get("modifiedTime", "")

        if item_id and item_id not in fid:
            continue
        if kind == "folder" and not is_f:
            continue
        if kind == "file" and is_f:
            continue
        if kind == "shortcut" and mime != sc.SHORTCUT_MIME:
            continue
        if kind == "sheet" and mime != sc.SHEET_MIME:
            continue
        if kind == "doc" and mime != "application/vnd.google-apps.document":
            continue

        if ext_set:
            _, ext = sc.split_ext(name, mime)
            if ext.lower() not in ext_set:
                continue
        if min_b is not None and sz < min_b:
            continue
        if max_b is not None and sz > max_b:
            continue
        if modified_after and mod < modified_after:
            continue

        full_text = f"{path}/{name}"
        if rx and not rx.search(full_text):
            continue
        if q_tokens:
            hay = sc.strip_accents(sc.nfc(full_text)).lower()
            if not all(tok in hay for tok in q_tokens):
                continue

        matches.append({
            "id": fid,
            "name": name,
            "path": path,
            "mimeType": mime,
            "kind": "Thư mục" if is_f else ("Shortcut" if mime == sc.SHORTCUT_MIME else "Tệp tin"),
            "size": sz,
            "modifiedTime": mod,
            "url": sc.drive_url(fid, mime),
        })
        if limit > 0 and len(matches) >= limit:
            break

    return matches


# ---------------------------------------------------------------------------
# 2. KIỂM TOÁN & TỰ ĐỘNG BÙ ĐẮP BỘ 3 `[00] TỔNG QUAN` (kiem-toan-tong-quan)
# ---------------------------------------------------------------------------

def _expected_overview_md_name(folder_path: str) -> str:
    if folder_path == sc.ROOT_NAME:
        return "Tổng Quan Hệ Thống - Quy Ước Đặt Tên.md"
    segs = folder_path.split("/")
    last = segs[-1]
    clean = re.sub(r"^\[\d{2,3}\]\s*", "", last)
    clean = re.sub(r"^\[([^\]]+)\]\s*(.+)$", lambda m: f"{m.group(1).strip()} - {m.group(2).strip()}", clean)
    clean = re.sub(r"^\[([^\]]+)\]$", r"\1", clean)
    clean = re.sub(r"\.(pdf|docx?|xlsx?|pptx?)$", "", clean, flags=re.I)
    clean = re.sub(r"\s*_+\s*", " ", clean).strip()
    return f"Tổng Quan Hệ Thống - {sc.title_case_vn(clean)}.md"


def audit_tong_quan_coverage(
    index: dict,
    branch: Optional[str] = None,
    max_depth: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Rà soát mọi thư mục nội dung trong kho xem đã có đủ:
    1. Thư mục con `[00] TỔNG QUAN`
    2. Tệp `Tổng Quan Hệ Thống - <Tên Thư Mục>.md`
    3. Bảng `Danh Mục Hệ Thống - <Tên Thư Mục>`
    Trả về danh sách các thư mục còn thiếu ít nhất 1 thành phần.
    """
    norm_branch = sc.normalize_branch(branch) if branch else None
    if norm_branch == sc.ROOT_NAME:
        norm_branch = None
    prefix = norm_branch.rstrip("/") + "/" if norm_branch else ""

    gaps: List[Dict[str, Any]] = []
    for path, data in sorted(index.items(), key=lambda kv: (kv[0].count("/"), kv[0])):
        if max_depth is not None and path.count("/") > max_depth:
            continue
        if norm_branch and not (path == norm_branch or path.startswith(prefix)):
            continue
        if path.endswith("/" + sc.TONG_QUAN_FOLDER) or sc.is_in_tong_quan(path):
            continue
        if ".obsidian" in path:
            continue
        # Đối với [07] KIỂM TRA: chỉ kiểm tra gốc [07] KIỂM TRA, không ép các hố cách ly con phải có bảng riêng
        if sc.is_quarantine_path(path) and path.count("/") > 1:
            continue
        items = data.get("items", [])
        if not items and path != sc.ROOT_NAME:
            continue

        tq_item = next(
            (it for it in items if it.get("name") == sc.TONG_QUAN_FOLDER and it.get("mimeType") == sc.FOLDER_MIME),
            None,
        )
        tq_path = f"{path}/{sc.TONG_QUAN_FOLDER}"
        tq_items = index.get(tq_path, {}).get("items", []) if tq_item else []
        cat_path = sc.catalog_folder_for_path(path)
        cat_items = index.get(cat_path, {}).get("items", []) if cat_path != tq_path else []

        expected_md = _expected_overview_md_name(path)
        expected_sheet = sc.normalize_sheet_title(path)

        has_md = any(
            it.get("mimeType") != sc.FOLDER_MIME
            and (sc.nfc(it.get("name", "")) == sc.nfc(expected_md) or it.get("name", "").startswith("Tổng Quan Hệ Thống - "))
            for it in tq_items
        )
        has_sheet = any(
            it.get("mimeType") == sc.SHEET_MIME and it.get("name", "").startswith("Danh Mục Hệ Thống - ")
            for it in [*tq_items, *cat_items]
        )

        if not tq_item or not has_md or not has_sheet:
            gaps.append({
                "path": path,
                "folder_id": data.get("id", ""),
                "tq_id": tq_item["id"] if tq_item else "",
                "has_tq_folder": bool(tq_item),
                "has_overview_md": has_md,
                "has_sheet": has_sheet,
                "expected_md": expected_md,
                "expected_sheet": expected_sheet,
            })
    return gaps


def generate_overview_markdown(folder_path: str, index: dict) -> str:
    """Sinh nội dung chuẩn cho tệp `Tổng Quan Hệ Thống - <Tên Thư Mục>.md` dựa trên chỉ mục hiện tại."""
    data = index.get(folder_path, {})
    items = [it for it in data.get("items", []) if it.get("name") != sc.TONG_QUAN_FOLDER]
    subfolders = [it for it in items if it.get("mimeType") == sc.FOLDER_MIME]
    files = [it for it in items if it.get("mimeType") != sc.FOLDER_MIME]
    total_size = sum(int(it.get("size") or 0) for it in files)

    md_title = _expected_overview_md_name(folder_path).replace(".md", "").upper()
    L = [
        f"# {md_title}",
        "",
        "## 1. Thông tin định danh",
        f"- **Đường dẫn trong kho:** `{folder_path}`",
        f"- **ID Thư mục Google Drive:** `{data.get('id', '')}`",
        f"- **URL truy cập:** {sc.drive_url(data.get('id', ''), sc.FOLDER_MIME)}",
        f"- **Bảng Danh Mục Hệ Thống:** `{sc.normalize_sheet_title(folder_path)}`",
        f"- **Cập nhật lần cuối:** {sc.today_vn()}",
        "",
        "## 2. Thống kê cấu trúc trực tiếp",
        f"- **Số thư mục con trực tiếp:** `{sc.fmt_int(len(subfolders))}`",
        f"- **Số tệp tin trực tiếp:** `{sc.fmt_int(len(files))}`",
        f"- **Tổng dung lượng tệp trực tiếp:** `{sc.human_size(total_size)}`",
        "",
    ]
    if subfolders:
        L += [
            "## 3. Danh sách thư mục con trực tiếp",
            "",
            sc.md_table(
                ["STT", "Tên Thư Mục", "ID Google Drive"],
                [(i, f"`{sf['name']}`", f"`{sf['id']}`") for i, sf in enumerate(sorted(subfolders, key=lambda x: x["name"]), 1)],
                ["r", "l", "l"],
            ),
            "",
        ]
    if files:
        L += [
            "## 4. Danh sách tệp tiêu biểu (tối đa 50)",
            "",
            sc.md_table(
                ["STT", "Tên Tệp (Chuẩn V6)", "Dung Lượng"],
                [(i, f"`{fl['name']}`", sc.human_size(fl.get("size"))) for i, fl in enumerate(sorted(files, key=lambda x: x["name"])[:50], 1)],
                ["r", "l", "r"],
            ),
            "",
        ]
    return "\n".join(L)


def heal_tong_quan_coverage(
    gaps: Sequence[Dict[str, Any]],
    index: dict,
    drive: Optional[sc.Drive] = None,
) -> Dict[str, int]:
    """
    Tự động tạo thư mục `[00] TỔNG QUAN` và tệp `Tổng Quan Hệ Thống - <Tên Thư Mục>.md`
    cho các thư mục còn thiếu, đồng thời cập nhật `storage_index.json`.
    """
    drive = drive or sc.Drive()
    created_folders = 0
    created_mds = 0
    errors = 0

    for g in gaps:
        path = g["path"]
        fid = g["folder_id"]
        if not fid:
            continue
        tq_id = g["tq_id"]
        tq_path = f"{path}/{sc.TONG_QUAN_FOLDER}"
        try:
            if not tq_id:
                tq_id = drive.ensure_folder(sc.TONG_QUAN_FOLDER, fid)
                created_folders += 1
                index[path].setdefault("items", []).append({
                    "id": tq_id,
                    "name": sc.TONG_QUAN_FOLDER,
                    "mimeType": sc.FOLDER_MIME,
                    "modifiedTime": sc.now_utc_iso(),
                })
                index.setdefault(tq_path, {"id": tq_id, "depth": tq_path.count("/"), "items": []})

            if not g["has_overview_md"]:
                md_name = g["expected_md"]
                md_content = generate_overview_markdown(path, index)
                with tempfile.TemporaryDirectory(prefix="heal_tq_") as td:
                    tmp_md = Path(td) / md_name
                    tmp_md.write_text(md_content, encoding="utf-8")
                    md_id = sc.publish_file(drive, tmp_md, tq_id, name=md_name)
                created_mds += 1
                tq_items = index.setdefault(tq_path, {"id": tq_id, "depth": tq_path.count("/"), "items": []}).setdefault("items", [])
                if not any(it.get("id") == md_id for it in tq_items):
                    tq_items.append({
                        "id": md_id,
                        "name": md_name,
                        "mimeType": "text/markdown",
                        "size": len(md_content.encode("utf-8")),
                        "modifiedTime": sc.now_utc_iso(),
                    })
        except sc.DriveError as e:
            errors += 1
            sc.log(f"  ! Lỗi bù đắp [00] TỔNG QUAN tại `{path}`: {str(e)[:180]}")

    if created_folders or created_mds:
        sc.save_index(index)
    return {"created_tq_folders": created_folders, "created_overview_mds": created_mds, "errors": errors}


# ---------------------------------------------------------------------------
# 3. KIỂM TOÁN QUYỀN TRUY CẬP / DI CHUYỂN (kiem-toan-quyen)
# ---------------------------------------------------------------------------

def audit_permissions(
    index: dict,
    drive: sc.Drive,
    branch: Optional[str] = None,
    limit: int = 500,
    workers: int = 32,
) -> Tuple[List[dict], int]:
    """Kiểm tra hàng loạt quyền `canMoveItemOutOfDrive,canEdit` bằng `stream_capabilities`."""
    norm_branch = sc.normalize_branch(branch) if branch else None
    if norm_branch == sc.ROOT_NAME:
        norm_branch = None
    candidates: List[Tuple[str, dict]] = []
    for path, it in sc.iter_items(index, norm_branch):
        if it.get("mimeType") == sc.FOLDER_MIME and it.get("name") == sc.TONG_QUAN_FOLDER:
            continue
        candidates.append((path, it))
        if limit > 0 and len(candidates) >= limit:
            break

    fids = [it["id"] for _, it in candidates]
    if hasattr(drive, "stream_capabilities"):
        caps_map = drive.stream_capabilities(fids, "canMoveItemOutOfDrive,canEdit", concurrency=max(8, workers))
    else:
        caps_map = {fid: drive.capabilities(fid, "canMoveItemOutOfDrive,canEdit") for fid in fids}

    restricted: List[dict] = []
    for path, it in candidates:
        caps = caps_map.get(it["id"], {})
        can_move = caps.get("canMoveItemOutOfDrive", True)
        can_edit = caps.get("canEdit", True)
        if can_move is False or can_edit is False:
            restricted.append({
                "id": it["id"],
                "name": it["name"],
                "path": path,
                "mimeType": it.get("mimeType", ""),
                "canMoveItemOutOfDrive": can_move,
                "canEdit": can_edit,
            })
    return restricted, len(candidates)


# ---------------------------------------------------------------------------
# 4. DỌN THƯ MỤC RỖNG AN TOÀN (don-thu-muc-rong)
# ---------------------------------------------------------------------------

def find_empty_folders_bottom_up(index: dict, branch: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Tìm các thư mục rỗng (không chứa bất kỳ tệp nội dung nào ngoài `[00] TỔNG QUAN` hoặc thư mục con rỗng).
    Đánh dấu `is_root_empty=True` cho thư mục rỗng cao nhất để chỉ cần di chuyển 1 lần.
    """
    norm_branch = sc.normalize_branch(branch) if branch else None
    if norm_branch == sc.ROOT_NAME:
        norm_branch = None
    prefix = norm_branch.rstrip("/") + "/" if norm_branch else ""

    empty_set: Set[str] = set()
    details: Dict[str, bool] = {}

    for path in sorted(index.keys(), key=lambda p: (-p.count("/"), p)):
        if path == sc.ROOT_NAME or sc.is_quarantine_path(path) or sc.is_in_tong_quan(path) or ".obsidian" in path:
            continue
        items = [it for it in index[path].get("items", []) if it.get("name") != sc.TONG_QUAN_FOLDER]
        if any(it.get("mimeType") != sc.FOLDER_MIME for it in items):
            continue
        subs = [it for it in items if it.get("mimeType") == sc.FOLDER_MIME]
        if not subs:
            empty_set.add(path)
            details[path] = False
        elif all(f"{path}/{sf['name']}" in empty_set for sf in subs):
            empty_set.add(path)
            details[path] = True

    results: List[Dict[str, Any]] = []
    for path in sorted(empty_set):
        if norm_branch and not (path == norm_branch or path.startswith(prefix)):
            continue
        parent_p = path.rsplit("/", 1)[0] if "/" in path else ""
        is_top_empty = parent_p not in empty_set
        results.append({
            "path": path,
            "id": index[path].get("id", ""),
            "parent_path": parent_p,
            "parent_id": index.get(parent_p, {}).get("id", ""),
            "is_nested": details[path],
            "is_top_empty": is_top_empty,
        })
    return results


def quarantine_empty_folders(
    empty_list: Sequence[Dict[str, Any]],
    index: dict,
    drive: Optional[sc.Drive] = None,
) -> int:
    """Di chuyển các thư mục rỗng cấp cao nhất (`is_top_empty=True`) vào `[07] KIỂM TRA/[05] THƯ MỤC RỖNG`."""
    drive = drive or sc.Drive()
    top_items = [e for e in empty_list if e.get("is_top_empty") and e.get("id")]
    if not top_items:
        return 0
    dest_id = drive.ensure_folder(
        sc.CONFIG.get("quarantine_subfolders", {}).get("empty_folder", "[05] THƯ MỤC RỖNG"),
        sc.quarantine_root_id(),
    )
    moved_ops = []
    for e in top_items:
        try:
            drive.move(e["id"], dest_id)
            moved_ops.append({
                "op": "move",
                "source_id": e["id"],
                "source_name": e["path"].split("/")[-1],
                "source_path": e["parent_path"],
                "old_parent_id": e["parent_id"],
                "dest_parent_id": dest_id,
                "target_name": e["path"].split("/")[-1],
                "ts": int(time.time()),
            })
            if e["parent_path"] in index:
                index[e["parent_path"]]["items"] = [
                    it for it in index[e["parent_path"]].get("items", []) if it.get("id") != e["id"]
                ]
            sub_prefix = e["path"] + "/"
            for k in [p for p in list(index.keys()) if p == e["path"] or p.startswith(sub_prefix)]:
                index.pop(k, None)
        except sc.DriveError as err:
            sc.log(f"  ! Không thể di chuyển thư mục rỗng `{e['path']}`: {str(err)[:180]}")

    if moved_ops:
        sc.save_index(index)
        tlog = sc.read_json(sc.transfer_log_path(), []) or []
        tlog.append({
            "batch_id": f"empty_{sc.now_stamp()}",
            "created_iso": sc.now_utc_iso(),
            "operations": moved_ops,
            "restored": False,
        })
        sc.write_json(sc.transfer_log_path(), tlog, indent=1)
    return len(moved_ops)


def main() -> None:
    ap = argparse.ArgumentParser(description="Tra cứu tức thì & Kiểm toán toàn diện kho [A] STORAGE (v3.0).")
    ap.add_argument(
        "lenh",
        choices=["tim-kiem", "kiem-toan-tong-quan", "kiem-toan-quyen", "don-thu-muc-rong"],
        help="Chức năng cần chạy",
    )
    ap.add_argument("--tu-khoa", help="Từ khóa tìm kiếm (hỗ trợ cả có dấu và không dấu)")
    ap.add_argument("--regex", help="Biểu thức chính quy tìm theo đường dẫn/tên")
    ap.add_argument("--id", dest="item_id", help="Tìm theo ID Google Drive")
    ap.add_argument("--nhanh", help="Giới hạn trong một nhánh")
    ap.add_argument("--loai", choices=["all", "folder", "file", "shortcut", "sheet", "doc"], default="all")
    ap.add_argument("--duoi", help="Danh sách đuôi tệp cách nhau dấu phẩy (ví dụ: pdf,epub)")
    ap.add_argument("--min-mb", type=float, help="Dung lượng tối thiểu (MB)")
    ap.add_argument("--max-mb", type=float, help="Dung lượng tối đa (MB)")
    ap.add_argument("--tu-ngay", help="Cập nhật từ ngày (YYYY-MM-DD)")
    ap.add_argument("--ke-ca-kiem-tra", action="store_true", help="Bao gồm cả vùng [07] KIỂM TRA khi tìm kiếm")
    ap.add_argument("--gioi-han", type=int, default=100, help="Số kết quả tối đa (mặc định 100)")
    ap.add_argument("--do-sau-toi-da", type=int, default=None, help="Độ sâu thư mục tối đa khi kiểm toán tổng quan")
    ap.add_argument("--xuat-csv", help="Đường dẫn xuất kết quả ra tệp CSV")
    ap.add_argument("--bu-dap", action="store_true", help="Tự động tạo [00] TỔNG QUAN và Tổng Quan Hệ Thống - *.md còn thiếu")
    ap.add_argument("--thuc-thi", action="store_true", help="Thực sự ghi lên Drive (mặc định: chạy thử)")
    ap.add_argument("--dong-y", action="store_true", help="Không hỏi xác nhận")
    ap.add_argument("--tai-len", action="store_true", help="Tải báo cáo kiểm toán lên [02] NHẬT KÍ")
    args = ap.parse_args()

    index = sc.load_index()

    if args.lenh == "tim-kiem":
        t0 = time.time()
        exts = [x.strip() for x in args.duoi.split(",")] if args.duoi else None
        results = search_index(
            index,
            query=args.tu_khoa,
            regex_pat=args.regex,
            item_id=args.item_id,
            branch=args.nhanh,
            kind=args.loai,
            exts=exts,
            min_mb=args.min_mb,
            max_mb=args.max_mb,
            modified_after=args.tu_ngay,
            include_quarantine=args.ke_ca_kiem_tra,
            limit=args.gioi_han,
        )
        el_ms = (time.time() - t0) * 1000.0
        sc.log(f"Tìm thấy {len(results)} kết quả (trong {el_ms:.1f} ms):")
        for i, r in enumerate(results, 1):
            sz_str = f" | {sc.human_size(r['size'])}" if r["size"] else ""
            sc.log(f"  {i:02d}. [{r['kind']}] `{r['name']}` ({r['id']}){sz_str}\n      ↳ {r['path']}")
        if args.xuat_csv:
            sc.write_csv(
                Path(args.xuat_csv),
                ["Loại", "Tên", "Thư mục cha", "ID", "Dung lượng (B)", "Cập nhật", "URL"],
                [(r["kind"], r["name"], r["path"], r["id"], r["size"], r["modifiedTime"], r["url"]) for r in results],
            )
            sc.log(f"Đã xuất CSV: {args.xuat_csv}")
        return

    if args.lenh == "kiem-toan-tong-quan":
        gaps = audit_tong_quan_coverage(index, branch=args.nhanh, max_depth=args.do_sau_toi_da)
        miss_tq = sum(1 for g in gaps if not g["has_tq_folder"])
        miss_md = sum(1 for g in gaps if not g["has_overview_md"])
        miss_sh = sum(1 for g in gaps if not g["has_sheet"])
        sc.log(
            f"=== KIỂM TOÁN BỘ 3 `[00] TỔNG QUAN` ===\n"
            f"  • Tổng thư mục chưa đủ bộ 3 : {len(gaps)}\n"
            f"  • Thiếu thư mục [00] TỔNG QUAN : {miss_tq}\n"
            f"  • Thiếu Tổng Quan Hệ Thống.md  : {miss_md}\n"
            f"  • Thiếu Danh Mục Hệ Thống      : {miss_sh}"
        )
        for g in gaps[:25]:
            flags = []
            if not g["has_tq_folder"]:
                flags.append("thiếu [00] TỔNG QUAN")
            if not g["has_overview_md"]:
                flags.append("thiếu .md")
            if not g["has_sheet"]:
                flags.append("thiếu Sheet")
            sc.log(f"  - `{g['path']}`: {', '.join(flags)}")

        if args.bu_dap and gaps:
            need_heal = [g for g in gaps if not g["has_tq_folder"] or not g["has_overview_md"]]
            if not args.thuc_thi:
                sc.log(f"(Chạy thử — sẽ tự động tạo mới cho {len(need_heal)} thư mục khi thêm --thuc-thi.)")
            elif need_heal and sc.confirm(f"Tự động tạo [00] TỔNG QUAN & Tổng Quan Hệ Thống.md cho {len(need_heal)} thư mục?", args.dong_y):
                res = heal_tong_quan_coverage(need_heal, index)
                sc.log(
                    f"Đã bù đắp: {res['created_tq_folders']} thư mục `[00] TỔNG QUAN`, "
                    f"{res['created_overview_mds']} tệp `Tổng Quan Hệ Thống - *.md` (lỗi: {res['errors']})."
                )
        return

    if args.lenh == "kiem-toan-quyen":
        drive = sc.Drive()
        restricted, checked = audit_permissions(index, drive, branch=args.nhanh, limit=args.gioi_han)
        sc.log(f"Đã kiểm tra quyền {checked} mục → phát hiện {len(restricted)} mục bị hạn chế quyền di chuyển/chỉnh sửa:")
        for r in restricted[:30]:
            sc.log(f"  • `{r['name']}` ({r['id']}) tại `{r['path']}` | canMove={r['canMoveItemOutOfDrive']} | canEdit={r['canEdit']}")
        return

    if args.lenh == "don-thu-muc-rong":
        empty = find_empty_folders_bottom_up(index, branch=args.nhanh)
        top_cnt = sum(1 for e in empty if e["is_top_empty"])
        sc.log(f"Phát hiện {len(empty)} thư mục rỗng ({top_cnt} nhánh rỗng gốc):")
        for e in empty[:30]:
            tag = " [NHÁNH GỐC SẼ CÁCH LY]" if e["is_top_empty"] else " (con rỗng)"
            sc.log(f"  • `{e['path']}` ({e['id']}){tag}")
        if args.thuc_thi and top_cnt > 0:
            if sc.confirm(f"Di chuyển {top_cnt} nhánh thư mục rỗng vào `{sc.QUARANTINE_FOLDER}`?", args.dong_y):
                moved = quarantine_empty_folders(empty, index)
                sc.log(f"Đã di chuyển {moved}/{top_cnt} nhánh thư mục rỗng vào `{sc.QUARANTINE_FOLDER}`.")
        elif top_cnt > 0:
            sc.log("(Chạy thử — thêm --thuc-thi để di chuyển thư mục rỗng vào khu kiểm tra.)")


if __name__ == "__main__":
    main()
