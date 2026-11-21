#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ĐỘNG CƠ BẢNG DANH MỤC HỆ THỐNG — [A] STORAGE (CHUẨN V6, v3.0)
=============================================================
Sinh lại nội dung bảng Google Sheets `Danh Mục Hệ Thống - <Tên Thư Mục>` từ:
- Chỉ mục toàn kho (`storage_index.json`),
- Bộ đệm siêu dữ liệu thư mục Drive API (`folder_metadata.json`: ngày tạo, chủ sở hữu, chia sẻ, mô tả),
- Bộ đệm đích & siêu dữ liệu Shortcut (`shortcut_cache.json`).

Nâng cấp v3.0:
- Bổ sung thống kê cộng dồn ngay trên từng dòng Thư mục trong Tab 1 `Danh Mục Hệ Thống`
  (17 cột: Phân loại, Định dạng, Thông tin bổ sung tách từ Chuẩn V6, Số thư mục con,
  Số tệp tin, Dung lượng hiển thị + Byte chuẩn số để sắp xếp, Ngày tạo, Chủ sở hữu, Chia sẻ).
- Nâng cấp Tab 2 `Thống Kê & Siêu Dữ Liệu` với Thẻ siêu dữ liệu thư mục gốc, KPI tách bạch
  Nội dung vs Hệ thống (`[00] TỔNG QUAN`), Phân bố cấp độ, Nhóm định dạng, Phần mở rộng
  và Top 15 tệp nặng nhất / cập nhật gần nhất (có công thức `=SUM` và liên kết trực tiếp).
- Bổ sung Tab 3 `Thư Mục Con Trực Tiếp` so sánh trực tiếp dung lượng, số tệp, tỷ trọng `%`
  và siêu dữ liệu của từng thư mục con kế tiếp.
- Tính toán cây cộng dồn một lần O(N) (`precompute_tree_rollup`) và tối ưu tái sử dụng Style
  `openpyxl`, hỗ trợ cập nhật hàng nghìn bảng nhanh và ổn định.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import gzip
import hashlib
import json
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


from storage_suite import core as sc

try:
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
except ImportError:  # pragma: no cover
    raise SystemExit("Thiếu thư viện openpyxl — cài bằng: pip install openpyxl")

SHEET_MIME = sc.SHEET_MIME
SHEET_PREFIX = "Danh Mục Hệ Thống - "
SCHEMA_VERSION = "v3.0"

_EMPTY_EXCLUDES = (f"{sc.ROOT_NAME}/{sc.KIEM_TRA_FOLDER}", "/[00] TỔNG QUAN", ".obsidian")

_FORMAT_BUCKETS = [
    ("Thư mục", lambda m, e: m == sc.FOLDER_MIME),
    ("Shortcut", lambda m, e: m == sc.SHORTCUT_MIME),
    ("Google Docs/Sheets/Slides", lambda m, e: m.startswith("application/vnd.google-apps")),
    ("PDF", lambda m, e: e == "pdf" or m == "application/pdf"),
    ("Sách điện tử (EPUB/MOBI/AZW/DJVU/PRC)", lambda m, e: e in {"epub", "mobi", "azw3", "djvu", "prc"}),
    ("Văn bản Office", lambda m, e: e in {"doc", "docx", "xls", "xlsx", "ppt", "pptx", "odt", "ods", "odp", "rtf"}),
    ("Markdown / Văn bản thô", lambda m, e: e in {"md", "txt", "csv", "tsv", "tex"} or m.startswith("text/")),
    ("Âm thanh", lambda m, e: m.startswith("audio/")),
    ("Video", lambda m, e: m.startswith("video/")),
    ("Hình ảnh", lambda m, e: m.startswith("image/")),
    ("Tệp nén", lambda m, e: e in {"zip", "rar", "7z", "gz", "tar"} or "zip" in m or "rar" in m or "compressed" in m),
    ("Mã nguồn / Cấu hình", lambda m, e: e in {"py", "json", "js", "ts", "ipynb", "sh", "yaml", "yml", "xml", "html", "opf"}),
]

# Style dùng chung giúp giảm phân bổ bộ nhớ khi xuất ~2.737 tệp .xlsx
_HDR_FILL = PatternFill("solid", fgColor="1F4E78")
_SEC_FILL = PatternFill("solid", fgColor="2F5597")
_SUB_FILL = PatternFill("solid", fgColor="D9E1F2")
_TOTAL_FILL = PatternFill("solid", fgColor="E9EDF4")
_LOOSE_FILL = PatternFill("solid", fgColor="F2F4F8")
_FOLDER_FILL = PatternFill("solid", fgColor="EEF2F8")
_NONE_FILL = PatternFill()

_HDR_FONT = Font(name="Arial", size=11, bold=True, color="FFFFFF")
_SEC_FONT = Font(name="Arial", size=10, bold=True, color="FFFFFF")
_TITLE_FONT = Font(name="Arial", size=13, bold=True, color="1F4E78")
_BOLD_FONT = Font(name="Arial", size=10, bold=True)
_REG_FONT = Font(name="Arial", size=10)
_LINK_FONT = Font(name="Arial", size=10, color="0563C1", underline="single")
_FOLDER_LINK_FONT = Font(name="Arial", size=10, bold=True, color="0563C1", underline="single")

_THIN_SIDE = Side(border_style="thin", color="D9D9D9")
_MED_TOP = Side(border_style="medium", color="1F4E78")
_BORDER = Border(left=_THIN_SIDE, right=_THIN_SIDE, top=_THIN_SIDE, bottom=_THIN_SIDE)
_TOTAL_BORDER = Border(left=_THIN_SIDE, right=_THIN_SIDE, top=_MED_TOP, bottom=_MED_TOP)

_ALIGN_CTR = Alignment(horizontal="center", vertical="center")
_ALIGN_HDR = Alignment(horizontal="center", vertical="center", wrap_text=True)
_ALIGN_RIGHT = Alignment(horizontal="right", vertical="center")
_ALIGN_LEFT = Alignment(horizontal="left", vertical="center")
_NUM_INT = "#,##0"
_NUM_PCT = "0.00%"


def _classify_item(it: dict) -> str:
    mime = it.get("mimeType", "")
    _, ext = sc.split_ext(it.get("name", ""), mime)
    ext = ext.lower()
    for label, fn in _FORMAT_BUCKETS:
        if fn(mime, ext):
            return label
    return "Khác"


def _is_system_path(path: str) -> bool:
    return path.endswith("/" + sc.TONG_QUAN_FOLDER) or f"/{sc.TONG_QUAN_FOLDER}/" in path or path == f"{sc.ROOT_NAME}/{sc.TONG_QUAN_FOLDER}"


def _is_dmht_sheet(it: dict) -> bool:
    return it.get("mimeType") == SHEET_MIME and str(it.get("name", "")).startswith(SHEET_PREFIX)


def title_case_vn(folder_body: str) -> str:
    return sc.title_case_vn(folder_body)


def sheet_name_for(path: str) -> str:
    return sc.normalize_sheet_title(path)


def sync_state_path() -> Path:
    return sc.data_dir() / "sheets_sync_state.json"


def _load_meta_caches(
    folder_meta: Optional[dict] = None,
    shortcut_cache: Optional[dict] = None,
) -> Tuple[dict, dict]:
    fm = folder_meta if folder_meta is not None else (sc.read_json(sc.folder_metadata_path(), {}) or {})
    sh = shortcut_cache if shortcut_cache is not None else (sc.read_json(sc.shortcut_cache_path(), {}) or {})
    return fm, sh


def _folder_group_label(name: str, child_path: str) -> str:
    if name == sc.TONG_QUAN_FOLDER or _is_system_path(child_path):
        return f"Hệ thống ({sc.TONG_QUAN_FOLDER})"
    if name == sc.KIEM_TRA_FOLDER or sc.is_in_kiem_tra(child_path):
        return f"Cách ly ({sc.KIEM_TRA_FOLDER})"
    return "Nội dung"


def precompute_tree_rollup(
    index: dict,
    folder_meta: Optional[dict] = None,
    shortcut_cache: Optional[dict] = None,
) -> dict:
    """
    Tính một lần O(N) toàn bộ cây quan hệ cha-con và thống kê cộng dồn cho mọi thư mục trong `index`.
    Giúp sinh hàng nghìn bảng `.xlsx` nhanh mà không lặp lại việc quét toàn từ điển `index`.
    """
    fm, sh = _load_meta_caches(folder_meta, shortcut_cache)
    children_map: Dict[str, List[str]] = defaultdict(list)
    stats: Dict[str, dict] = {}
    empty_set = set()

    # Duyệt bottom-up (sâu nhất trước) để cộng dồn chính xác chỉ trong 1 lượt
    sorted_desc = sorted(index.keys(), key=lambda p: (-index[p].get("depth", p.count("/")), p))
    for path in sorted_desc:
        if "/" in path:
            parent_p = path.rsplit("/", 1)[0]
            if parent_p in index:
                children_map[parent_p].append(path)

    for path in list(children_map.keys()):
        children_map[path].sort()

    for path in sorted_desc:
        data = index[path]
        items = data.get("items", [])
        sys_dir = _is_system_path(path)
        fid = data.get("id", "")
        meta = fm.get(fid, {})

        direct_folders = 0
        direct_content_folders = 0
        direct_files = 0
        direct_content_files = 0
        direct_system_files = 0
        direct_bytes = 0
        direct_content_bytes = 0
        direct_system_bytes = 0
        shortcuts = 0
        broken_shortcuts = 0
        latest_mod = meta.get("modifiedTime") or ""
        fmt_counter: Counter = Counter()
        fmt_bytes: Counter = Counter()

        tot_folders = 0
        tot_content_folders = 0
        tot_files = 0
        content_files = 0
        system_files = 0
        tot_bytes = 0
        content_bytes = 0
        system_bytes = 0
        empty_desc = 0

        non_tq_has_file = False
        non_tq_sub_paths = []

        for it in items:
            mime = it.get("mimeType", "")
            name = it.get("name", "")
            mod = it.get("modifiedTime") or ""
            if mod and not _is_dmht_sheet(it) and mod > latest_mod:
                latest_mod = mod

            if mime == sc.FOLDER_MIME:
                direct_folders += 1
                tot_folders += 1
                if name != sc.TONG_QUAN_FOLDER and not sys_dir:
                    direct_content_folders += 1
                    tot_content_folders += 1
                    non_tq_sub_paths.append(f"{path}/{name}")
                cpath = f"{path}/{name}"
                cst = stats.get(cpath)
                if cst:
                    tot_folders += cst["total_folders"]
                    tot_content_folders += cst["total_content_folders"]
                    tot_files += cst["total_files"]
                    content_files += cst["content_files"]
                    system_files += cst["system_files"]
                    tot_bytes += cst["total_bytes"]
                    content_bytes += cst["content_bytes"]
                    system_bytes += cst["system_bytes"]
                    shortcuts += cst["shortcuts"]
                    broken_shortcuts += cst["broken_shortcuts"]
                    empty_desc += cst["empty_descendant_folders"]
                    if cst["is_empty"] and name != sc.TONG_QUAN_FOLDER:
                        empty_desc += 1
                    if cst["latest_mod_iso"] > latest_mod:
                        latest_mod = cst["latest_mod_iso"]
                    for fk, fv in cst["_fmt_counts"].items():
                        fmt_counter[fk] += fv
                    for fk, fb in cst["_fmt_bytes"].items():
                        fmt_bytes[fk] += fb
            else:
                if name != sc.TONG_QUAN_FOLDER:
                    non_tq_has_file = True
                sz = int(it.get("size") or 0)
                direct_files += 1
                tot_files += 1
                direct_bytes += sz
                tot_bytes += sz
                if sys_dir:
                    direct_system_files += 1
                    system_files += 1
                    direct_system_bytes += sz
                    system_bytes += sz
                else:
                    direct_content_files += 1
                    content_files += 1
                    direct_content_bytes += sz
                    content_bytes += sz
                if mime == sc.SHORTCUT_MIME:
                    shortcuts += 1
                    sc_rec = sh.get(it.get("id", ""), {})
                    if sc_rec.get("targetStatus") in ("broken", "trashed"):
                        broken_shortcuts += 1
                fl = sc.format_label(mime, name)
                fmt_counter[fl] += 1
                fmt_bytes[fl] += sz

        is_empty = False
        if path != sc.ROOT_NAME and not any(m in (path + "/") for m in _EMPTY_EXCLUDES):
            if not non_tq_has_file and (not non_tq_sub_paths or all(sp in empty_set for sp in non_tq_sub_paths)):
                is_empty = True
                empty_set.add(path)

        dom_fmt = "—"
        if fmt_counter:
            top_f, top_c = max(fmt_counter.items(), key=lambda kv: (kv[1], fmt_bytes.get(kv[0], 0), kv[0]))
            pct_f = 100.0 * top_c / max(1, tot_files)
            dom_fmt = f"{top_f} ({pct_f:.1f}%)"

        stats[path] = {
            "id": fid,
            "direct_folders": direct_folders,
            "direct_content_folders": direct_content_folders,
            "direct_files": direct_files,
            "direct_content_files": direct_content_files,
            "direct_system_files": direct_system_files,
            "direct_bytes": direct_bytes,
            "direct_content_bytes": direct_content_bytes,
            "direct_system_bytes": direct_system_bytes,
            "total_folders": tot_folders,
            "total_content_folders": tot_content_folders,
            "total_files": tot_files,
            "content_files": content_files,
            "system_files": system_files,
            "shortcuts": shortcuts,
            "broken_shortcuts": broken_shortcuts,
            "total_bytes": tot_bytes,
            "content_bytes": content_bytes,
            "system_bytes": system_bytes,
            "empty_descendant_folders": empty_desc,
            "is_empty": is_empty,
            "latest_mod_iso": latest_mod,
            "dominant_format": dom_fmt,
            "_fmt_counts": fmt_counter,
            "_fmt_bytes": fmt_bytes,
        }

    return {
        "children_map": children_map,
        "stats": stats,
        "folder_meta": fm,
        "shortcut_cache": sh,
    }


def _iter_subtree_paths(index: dict, target_path: str, tree_ctx: Optional[dict] = None) -> Iterable[str]:
    if tree_ctx is not None:
        children_map = tree_ctx["children_map"]
        stack = [target_path]
        while stack:
            cur = stack.pop()
            if cur in index:
                yield cur
            subs = children_map.get(cur)
            if subs:
                for ch in reversed(subs):
                    stack.append(ch)
        return
    prefix = target_path + "/"
    for path in sorted(index):
        if path == target_path or path.startswith(prefix):
            yield path


def compute_subtree_signature(
    index: dict,
    target_path: str,
    include_schema: bool = True,
    folder_meta: Optional[dict] = None,
    shortcut_cache: Optional[dict] = None,
    tree_ctx: Optional[dict] = None,
) -> str:
    """Chữ ký SHA-256 ổn định của cây con, bao gồm cả siêu dữ liệu thư mục & đích shortcut."""
    if tree_ctx is not None:
        fm = folder_meta if folder_meta is not None else tree_ctx["folder_meta"]
        sh = shortcut_cache if shortcut_cache is not None else tree_ctx["shortcut_cache"]
    elif include_schema and (folder_meta is None or shortcut_cache is None):
        fm, sh = _load_meta_caches(folder_meta, shortcut_cache)
    else:
        fm = folder_meta or {}
        sh = shortcut_cache or {}
    h = hashlib.sha256()
    if include_schema:
        h.update(f"schema:{SCHEMA_VERSION}\n".encode("utf-8"))
    paths = sorted(_iter_subtree_paths(index, target_path, tree_ctx))
    for p in paths:
        data = index[p]
        fid = data.get("id", "")
        m = fm.get(fid) if include_schema else None
        meta_sig = (
            f"{m.get('createdTime', '')}|{m.get('ownerSummary', '')}|"
            f"{m.get('shareSummary', '')}|{m.get('description', '')}"
            if m else ""
        )
        h.update(f"D|{p}|{fid}|{meta_sig}\n".encode("utf-8"))
        for it in sorted(data.get("items", []), key=lambda x: (x.get("id", ""), x.get("name", ""))):
            mime = it.get("mimeType", "")
            name = it.get("name", "")
            mod = "" if _is_dmht_sheet(it) else (it.get("modifiedTime") or "")
            sz = "" if mime == sc.FOLDER_MIME else str(it.get("size") or 0)
            sc_sig = ""
            if include_schema and mime == sc.SHORTCUT_MIME and sh:
                sr = sh.get(it.get("id", ""))
                if sr:
                    sc_sig = f"|{sr.get('targetId', '')}|{sr.get('targetStatus', '')}|{sr.get('targetName', '')}"
            h.update(f"I|{it.get('id', '')}|{name}|{mime}|{sz}|{mod}{sc_sig}\n".encode("utf-8"))
    return h.hexdigest()


def discover_targets(index: dict, branch: Optional[str] = None, max_depth: int = 99) -> List[dict]:
    """Trả về danh sách dict `{path, depth, tq_id, cat_path, cat_folder_id, sheet_id, current_name, sheet_name, sibling_names}`."""
    targets = []
    prefix = (branch.rstrip("/") + "/") if branch else ""
    for path, data in index.items():
        if branch and not (path == branch or path.startswith(prefix)):
            continue
        if path.endswith("/" + sc.TONG_QUAN_FOLDER) or ".obsidian" in path:
            continue
        if path.startswith(f"{sc.ROOT_NAME}/{sc.TONG_QUAN_FOLDER}/"):
            continue
        depth = data.get("depth", path.count("/"))
        if depth > max_depth:
            continue
        tq = next(
            (it for it in data.get("items", []) if it["name"] == sc.TONG_QUAN_FOLDER and it["mimeType"] == sc.FOLDER_MIME),
            None,
        )
        cat_path = sc.catalog_folder_for_path(path)
        cat_data = index.get(cat_path, {})
        sheet = None
        sibling_names = set()
        for it in cat_data.get("items", []):
            sibling_names.add(sc.nfc(it.get("name", "")))
            if _is_dmht_sheet(it) and sheet is None:
                sheet = it
        if tq:
            tq_path = f"{path}/{sc.TONG_QUAN_FOLDER}"
            for it in index.get(tq_path, {}).get("items", []):
                if sheet is None:
                    sibling_names.add(sc.nfc(it.get("name", "")))
                if _is_dmht_sheet(it) and sheet is None:
                    sheet = it
        if sc.is_in_tong_quan(path) and tq is None and sheet is None:
            continue
        if tq is None and sheet is None and (f"{sc.KIEM_TRA_FOLDER}/" in path or not data.get("items")):
            continue
        expected_name = sheet_name_for(path)
        current_name = sheet["name"] if sheet else ""
        targets.append({
            "path": path,
            "depth": depth,
            "tq_id": tq["id"] if tq else None,
            "cat_path": cat_path,
            "cat_folder_id": cat_data.get("id"),
            "sheet_id": sheet["id"] if sheet else None,
            "current_name": current_name,
            "sheet_name": expected_name,
            "sibling_names": sibling_names,
        })
    targets.sort(key=lambda t: (t["depth"], t["path"]))
    return targets


def _style_header_row(ws, row_num: int, cols: int, fill=_HDR_FILL, font=_HDR_FONT, height: int = 28) -> None:
    ws.row_dimensions[row_num].height = height
    for ci in range(1, cols + 1):
        c = ws.cell(row=row_num, column=ci)
        c.fill, c.font, c.alignment, c.border = fill, font, _ALIGN_HDR, _BORDER


def _style_section_banner(ws, row_num: int, title: str, cols: int) -> None:
    ws.append([title] + [""] * (cols - 1))
    rn = ws.max_row
    ws.row_dimensions[rn].height = 22
    for ci in range(1, cols + 1):
        c = ws.cell(row=rn, column=ci)
        c.fill, c.font, c.border = _SEC_FILL, _SEC_FONT, _BORDER
        c.alignment = _ALIGN_LEFT


def _write_summary_sheet(
    wb: openpyxl.Workbook,
    index: dict,
    target_path: str,
    branch_st: dict,
    folder_meta: dict,
    shortcut_cache: dict,
    by_level: Dict[int, List[int]],
    by_cat: Dict[str, List[int]],
    by_ext: Dict[str, List[int]],
    top_heavy_files: List[Tuple[int, str, dict]],
    top_recent_files: List[Tuple[str, str, dict]],
) -> None:
    ws = wb.create_sheet(title="Thống Kê & Siêu Dữ Liệu")

    target_data = index.get(target_path, {})
    target_id = target_data.get("id", "")
    fmeta = folder_meta.get(target_id, {})
    leaf_name = target_path.split("/")[-1]
    parent_path = target_path.rsplit("/", 1)[0] if "/" in target_path else ""
    parent_id = index.get(parent_path, {}).get("id", "") if parent_path else ""
    parent_url = sc.drive_url(parent_id, sc.FOLDER_MIME) if parent_id else ""
    self_url = sc.drive_url(target_id, sc.FOLDER_MIME) if target_id else ""
    cat_path = sc.catalog_folder_for_path(target_path)
    cat_id = index.get(cat_path, {}).get("id", "")
    cat_url = sc.drive_url(cat_id, sc.FOLDER_MIME) if cat_id else ""

    created_str = sc.fmt_datetime_vn(fmeta.get("createdTime")) or "Chưa thu thập"
    mod_self_str = sc.fmt_datetime_vn(fmeta.get("modifiedTime")) or "Chưa có"
    latest_sub_str = sc.fmt_datetime_vn(branch_st.get("latest_mod_iso")) or mod_self_str
    owner_str = fmeta.get("ownerSummary") or sc.summarize_owners(fmeta) or "Chưa thu thập"
    share_str = fmeta.get("shareSummary") or sc.summarize_sharing(fmeta) or "Chưa thu thập"
    desc_str = (fmeta.get("description") or "").strip() or "(Không có mô tả)"

    # 1. Khối siêu dữ liệu thư mục gốc
    ws.append(["SIÊU DỮ LIỆU THƯ MỤC HIỆN HÀNH", "GIÁ TRỊ", "NGUỒN / GHI CHÚ"])
    _style_header_row(ws, 1, 3)

    meta_rows = [
        ("Đường dẫn đầy đủ", target_path, "Vị trí chuẩn V6 trong kho", None),
        ("Tên thư mục", leaf_name, f"Cấp độ gốc {target_path.count('/')}", None),
        ("Tên bảng Google Sheets", sheet_name_for(target_path), f"Phiên bản cấu trúc {SCHEMA_VERSION}", None),
        ("Thư mục lưu bảng Danh Mục", cat_path, "Cây danh mục tập trung tại [00] TỔNG QUAN/[01] DANH SÁCH", cat_url or None),
        ("ID Google Drive thư mục", target_id or "—", "Định danh duy nhất bất biến", None),
        ("URL mở thư mục trực tiếp", self_url or "—", "Bấm để mở thư mục trên Google Drive", self_url or None),
        ("Thư mục cha", parent_path or "(Thư mục gốc kho)", "Nhánh chứa trực tiếp", None),
        ("URL thư mục cha", parent_url or "—", "Liên kết về thư mục cấp trên", parent_url or None),
        ("Ngày tạo thư mục", created_str, "Google Drive API (createdTime)", None),
        ("Cập nhật chính thư mục", mod_self_str, "Google Drive API (modifiedTime)", None),
        ("Hoạt động mới nhất trong nhánh", latest_sub_str, "Mới nhất toàn cây con (trừ bảng tự sinh)", None),
        ("Chủ sở hữu", owner_str, "Google Drive API (owners)", None),
        ("Trạng thái chia sẻ & Quyền", share_str, "Tóm tắt an toàn từ permissions", None),
        ("Mô tả thư mục", desc_str, "Thuộc tính description trên Drive", None),
        ("Thời điểm tổng hợp bảng", sc.fmt_datetime_vn(sc.now_utc_iso()), f"Động cơ sheet_engine {SCHEMA_VERSION}", None),
    ]
    for k, v, note, link in meta_rows:
        ws.append([k, v, note])
        rn = ws.max_row
        c1, c2, c3 = ws.cell(rn, 1), ws.cell(rn, 2), ws.cell(rn, 3)
        c1.font, c2.font, c3.font = _BOLD_FONT, (_LINK_FONT if link else _REG_FONT), _REG_FONT
        c1.fill = _SUB_FILL if rn == 2 else _NONE_FILL
        c2.fill = _SUB_FILL if rn == 2 else _NONE_FILL
        c3.fill = _SUB_FILL if rn == 2 else _NONE_FILL
        for ci in (1, 2, 3):
            ws.cell(rn, ci).border = _BORDER
        if link:
            c2.hyperlink = link

    ws.append([])

    # 2. Khối KPI tổng quan nhánh
    _style_section_banner(ws, ws.max_row + 1, "CHỈ SỐ THỐNG KÊ TỔNG QUAN NHÁNH", 3)
    ws.append(["Chỉ Số Thống Kê", "Giá Trị", "Giải Thích / Chi Tiết"])
    _style_header_row(ws, ws.max_row, 3)

    n_dir = branch_st["total_folders"]
    n_files = branch_st["total_files"]
    n_cfiles = branch_st["content_files"]
    n_sfiles = branch_st["system_files"]
    tot_b = branch_st["total_bytes"]
    c_b = branch_st["content_bytes"]
    s_b = branch_st["system_bytes"]
    avg_b = (c_b / n_cfiles) if n_cfiles else 0
    ok_sc = branch_st["shortcuts"] - branch_st["broken_shortcuts"]

    kpis = [
        ("Thư mục con trực tiếp", branch_st["direct_folders"],
         f"{sc.fmt_int(branch_st['direct_content_folders'])} nội dung + {sc.fmt_int(branch_st['direct_folders'] - branch_st['direct_content_folders'])} hệ thống", _NUM_INT),
        ("Tổng thư mục con toàn nhánh", n_dir,
         f"{sc.fmt_int(branch_st['total_content_folders'])} thư mục nội dung + {sc.fmt_int(n_dir - branch_st['total_content_folders'])} [00] TỔNG QUAN", _NUM_INT),
        ("Thư mục rỗng trong nhánh", branch_st["empty_descendant_folders"],
         "Đếm bottom-up (loại trừ [00] TỔNG QUAN & [07] KIỂM TRA)", _NUM_INT),
        ("Tệp nội dung (ngoài [00] TỔNG QUAN)", n_cfiles,
         "Tài liệu, sách, bài giảng, đề thi, dữ liệu người dùng", _NUM_INT),
        ("Tệp hệ thống ([00] TỔNG QUAN)", n_sfiles,
         "Bảng Danh Mục Hệ Thống, Tổng Quan, Nhật Kí, Mã Nguồn", _NUM_INT),
        ("Tổng số tệp tin toàn nhánh", n_files,
         "Tệp nội dung + Tệp hệ thống", _NUM_INT),
        ("Số lượng Shortcut", branch_st["shortcuts"],
         f"{sc.fmt_int(ok_sc)} hoạt động | {sc.fmt_int(branch_st['broken_shortcuts'])} lỗi 404 / thùng rác", _NUM_INT),
        ("Dung lượng tệp nội dung", sc.human_size(c_b), f"{sc.fmt_int(c_b)} byte", None),
        ("Dung lượng tệp hệ thống", sc.human_size(s_b), f"{sc.fmt_int(s_b)} byte", None),
        ("Tổng dung lượng toàn nhánh (Hiển thị)", sc.human_size(tot_b), "Cộng dồn toàn bộ tệp có kích thước", None),
        ("Tổng dung lượng toàn nhánh (Byte)", tot_b, "Giá trị số nguyên dùng để đối chiếu / cộng dồn", _NUM_INT),
        ("Dung lượng trung bình / tệp nội dung", sc.human_size(avg_b), "Tính trên tệp ngoài [00] TỔNG QUAN", None),
        ("Định dạng chủ đạo của nhánh", branch_st["dominant_format"], "Nhóm định dạng chiếm số lượng cao nhất", None),
    ]
    for label, val, note, num_fmt in kpis:
        ws.append([label, val, note])
        rn = ws.max_row
        c1, c2, c3 = ws.cell(rn, 1), ws.cell(rn, 2), ws.cell(rn, 3)
        c1.font, c2.font, c3.font = _BOLD_FONT, _REG_FONT, _REG_FONT
        if num_fmt and isinstance(val, (int, float)):
            c2.number_format = num_fmt
            c2.alignment = _ALIGN_RIGHT
        for ci in (1, 2, 3):
            ws.cell(rn, ci).border = _BORDER

    ws.append([])

    # 3. Phân bố theo cấp độ tương đối (7 cột A..G)
    _style_section_banner(ws, ws.max_row + 1, "PHÂN BỐ CẤU TRÚC THEO CẤP ĐỘ TƯƠNG ĐỐI", 7)
    ws.append(["Cấp Độ Tương Đối", "Số Thư Mục", "Tệp Nội Dung", "Tệp Hệ Thống", "Tổng Số Tệp", "Tổng Dung Lượng", "Dung Lượng (Byte)"])
    _style_header_row(ws, ws.max_row, 7)
    lvl_start = ws.max_row + 1
    for lvl in sorted(by_level):
        fd_cnt, cf_cnt, sf_cnt, b_sum = by_level[lvl]
        ws.append([f"Cấp {lvl}", fd_cnt, cf_cnt, sf_cnt, cf_cnt + sf_cnt, sc.human_size(b_sum), b_sum])
        rn = ws.max_row
        for ci in range(1, 8):
            c = ws.cell(rn, ci)
            c.font, c.border = _REG_FONT, _BORDER
            if ci in (2, 3, 4, 5, 7):
                c.number_format = _NUM_INT
                c.alignment = _ALIGN_RIGHT
            elif ci == 6:
                c.alignment = _ALIGN_RIGHT
    lvl_end = ws.max_row
    if lvl_end >= lvl_start:
        ws.append([
            "Tổng cộng",
            f"=SUM(B{lvl_start}:B{lvl_end})",
            f"=SUM(C{lvl_start}:C{lvl_end})",
            f"=SUM(D{lvl_start}:D{lvl_end})",
            f"=SUM(E{lvl_start}:E{lvl_end})",
            sc.human_size(tot_b),
            f"=SUM(G{lvl_start}:G{lvl_end})",
        ])
        tr = ws.max_row
        for ci in range(1, 8):
            c = ws.cell(tr, ci)
            c.fill, c.font, c.border = _TOTAL_FILL, _BOLD_FONT, _TOTAL_BORDER
            if ci in (2, 3, 4, 5, 7):
                c.number_format = _NUM_INT
                c.alignment = _ALIGN_RIGHT
            elif ci == 6:
                c.alignment = _ALIGN_RIGHT

    ws.append([])

    # 4. Phân bố theo nhóm định dạng (6 cột A..F)
    _style_section_banner(ws, ws.max_row + 1, "PHÂN BỐ THEO NHÓM ĐỊNH DẠNG", 6)
    ws.append(["Nhóm Định Dạng / Loại Mục", "Số Lượng Mục", "Tỷ Lệ Số Lượng (%)", "Tổng Dung Lượng", "Dung Lượng (Byte)", "Tỷ Lệ Dung Lượng (%)"])
    _style_header_row(ws, ws.max_row, 6)
    cat_start = ws.max_row + 1
    tot_items = max(1, n_dir + n_files)
    cat_tot_row = cat_start + len(by_cat)
    for idx_c, (cat_name, (cnt, b_sum)) in enumerate(
        sorted(by_cat.items(), key=lambda kv: (-kv[1][1], -kv[1][0], kv[0]))
    ):
        rn = cat_start + idx_c
        pct_cnt = f"=IF($B${cat_tot_row}>0, B{rn}/$B${cat_tot_row}, 0)" if by_cat else 0
        pct_byt = f"=IF($E${cat_tot_row}>0, E{rn}/$E${cat_tot_row}, 0)" if by_cat else 0
        ws.append([cat_name, cnt, pct_cnt, sc.human_size(b_sum), b_sum, pct_byt])
        for ci in range(1, 7):
            c = ws.cell(rn, ci)
            c.font, c.border = _REG_FONT, _BORDER
            if ci in (2, 5):
                c.number_format = _NUM_INT
                c.alignment = _ALIGN_RIGHT
            elif ci in (3, 6):
                c.number_format = _NUM_PCT
                c.alignment = _ALIGN_RIGHT
            elif ci == 4:
                c.alignment = _ALIGN_RIGHT
    cat_end = ws.max_row
    if cat_end >= cat_start:
        ws.append([
            "Tổng cộng",
            f"=SUM(B{cat_start}:B{cat_end})",
            f"=SUM(C{cat_start}:C{cat_end})",
            sc.human_size(tot_b),
            f"=SUM(E{cat_start}:E{cat_end})",
            f"=SUM(F{cat_start}:F{cat_end})",
        ])
        for ci in range(1, 7):
            c = ws.cell(cat_tot_row, ci)
            c.fill, c.font, c.border = _TOTAL_FILL, _BOLD_FONT, _TOTAL_BORDER
            if ci in (2, 5):
                c.number_format = _NUM_INT
                c.alignment = _ALIGN_RIGHT
            elif ci in (3, 6):
                c.number_format = _NUM_PCT
                c.alignment = _ALIGN_RIGHT
            elif ci == 4:
                c.alignment = _ALIGN_RIGHT

    ws.append([])

    # 5. Chi tiết Top phần mở rộng tệp (6 cột A..F)
    _style_section_banner(ws, ws.max_row + 1, "CHI TIẾT PHẦN MỞ RỘNG / LOẠI TỆP PHỔ BIẾN (TOP 15)", 6)
    ws.append(["Định Dạng / Đuôi Tệp", "Số Lượng Tệp", "Tỷ Lệ Tệp (%)", "Tổng Dung Lượng", "Dung Lượng (Byte)", "Tỷ Lệ Dung Lượng (%)"])
    _style_header_row(ws, ws.max_row, 6)
    top_exts = sorted(by_ext.items(), key=lambda kv: (-kv[1][0], -kv[1][1], kv[0]))[:15]
    if top_exts:
        for ext_name, (cnt, b_sum) in top_exts:
            pct_f = (cnt / n_files) if n_files else 0.0
            pct_b = (b_sum / tot_b) if tot_b else 0.0
            ws.append([ext_name, cnt, pct_f, sc.human_size(b_sum), b_sum, pct_b])
            rn = ws.max_row
            for ci in range(1, 7):
                c = ws.cell(rn, ci)
                c.font, c.border = _REG_FONT, _BORDER
                if ci in (2, 5):
                    c.number_format = _NUM_INT
                    c.alignment = _ALIGN_RIGHT
                elif ci in (3, 6):
                    c.number_format = _NUM_PCT
                    c.alignment = _ALIGN_RIGHT
                elif ci == 4:
                    c.alignment = _ALIGN_RIGHT
    else:
        ws.append(["(Chưa có tệp tin trong nhánh)", 0, 0, "0 B", 0, 0])
        for ci in range(1, 7):
            ws.cell(ws.max_row, ci).border = _BORDER

    ws.append([])

    # 6. Top 15 tệp nặng nhất trong nhánh (7 cột A..G)
    _style_section_banner(ws, ws.max_row + 1, "TOP 15 TỆP DUNG LƯỢNG LỚN NHẤT TRONG NHÁNH", 7)
    ws.append(["STT", "Tên Tệp", "Định Dạng", "Thư Mục Cha", "Dung Lượng", "Dung Lượng (Byte)", "URL Truy Cập Trực Tiếp"])
    _style_header_row(ws, ws.max_row, 7)
    if top_heavy_files:
        for rank, (sz, p_str, it) in enumerate(top_heavy_files, 1):
            url = sc.drive_url(it["id"], it.get("mimeType", ""))
            ws.append([rank, it.get("name", ""), sc.format_label(it.get("mimeType", ""), it.get("name", "")), p_str, sc.human_size(sz), sz, url])
            rn = ws.max_row
            for ci in range(1, 8):
                c = ws.cell(rn, ci)
                c.font, c.border = _REG_FONT, _BORDER
                if ci in (1, 6):
                    c.number_format = _NUM_INT
                    c.alignment = _ALIGN_RIGHT
                elif ci == 5:
                    c.alignment = _ALIGN_RIGHT
            u = ws.cell(rn, 7)
            u.hyperlink, u.font = url, _LINK_FONT
    else:
        ws.append(["—", "(Không có tệp có kích thước > 0 B)", "", "", "", 0, ""])
        for ci in range(1, 8):
            ws.cell(ws.max_row, ci).border = _BORDER

    ws.append([])

    # 7. Top 15 tệp cập nhật gần nhất trong nhánh (7 cột A..G)
    _style_section_banner(ws, ws.max_row + 1, "TOP 15 TỆP CẬP NHẬT GẦN NHẤT TRONG NHÁNH", 7)
    ws.append(["STT", "Tên Tệp", "Định Dạng", "Thư Mục Cha", "Dung Lượng", "Cập Nhật Lúc (UTC+7)", "URL Truy Cập Trực Tiếp"])
    _style_header_row(ws, ws.max_row, 7)
    if top_recent_files:
        for rank, (mod_iso, p_str, it) in enumerate(top_recent_files, 1):
            sz = int(it.get("size") or 0)
            url = sc.drive_url(it["id"], it.get("mimeType", ""))
            ws.append([
                rank,
                it.get("name", ""),
                sc.format_label(it.get("mimeType", ""), it.get("name", "")),
                p_str,
                sc.human_size(sz) if sz else "—",
                sc.fmt_datetime_vn(mod_iso),
                url,
            ])
            rn = ws.max_row
            for ci in range(1, 8):
                c = ws.cell(rn, ci)
                c.font, c.border = _REG_FONT, _BORDER
                if ci == 1:
                    c.number_format = _NUM_INT
                    c.alignment = _ALIGN_RIGHT
                elif ci == 5:
                    c.alignment = _ALIGN_RIGHT
            u = ws.cell(rn, 7)
            u.hyperlink, u.font = url, _LINK_FONT
    else:
        ws.append(["—", "(Chưa có lịch sử cập nhật tệp)", "", "", "", "", ""])
        for ci in range(1, 8):
            ws.cell(ws.max_row, ci).border = _BORDER

    for i, w in enumerate([42, 52, 24, 38, 22, 26, 52], start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"


def _write_children_sheet(
    wb: openpyxl.Workbook,
    index: dict,
    target_path: str,
    branch_st: dict,
    tree_ctx: dict,
) -> None:
    ws = wb.create_sheet(title="Thư Mục Con Trực Tiếp")
    headers = [
        "STT", "Tên Thư Mục Con", "Phân Nhóm", "Thư Mục Con (Cộng Dồn)",
        "Tệp Nội Dung", "Tệp Hệ Thống", "Tổng Số Tệp",
        "Dung Lượng", "Dung Lượng (Byte)", "Tỷ Trọng Dung Lượng (%)", "Tỷ Trọng Tệp (%)",
        "Số Shortcut", "Ngày Tạo", "Cập Nhật Thư Mục", "Hoạt Động Mới Nhất Nhánh",
        "Định Dạng Chủ Đạo", "Chủ Sở Hữu", "Chia Sẻ & Quyền",
        "ID Google Drive", "URL Truy Cập Trực Tiếp",
    ]
    n_cols = len(headers)
    ws.append(headers)
    _style_header_row(ws, 1, n_cols)

    stats = tree_ctx["stats"]
    fm = tree_ctx["folder_meta"]
    items = index.get(target_path, {}).get("items", [])
    direct_dirs = sorted(
        (it for it in items if it.get("mimeType") == sc.FOLDER_MIME),
        key=lambda x: x.get("name", ""),
    )

    if not direct_dirs:
        ws.append([
            "—", "(Thư mục hiện hành chưa có thư mục con trực tiếp)", "",
            0, 0, 0, 0, "0 B", 0, 0, 0, 0, "", "", "", "", "", "", "", "",
        ])
        for ci in range(1, n_cols + 1):
            ws.cell(2, ci).font = _REG_FONT
            ws.cell(2, ci).border = _BORDER
        for i, w in enumerate([8, 40, 25, 18, 15, 15, 15, 15, 20, 19, 17, 14, 14, 16, 19, 24, 18, 28, 36, 50], start=1):
            ws.column_dimensions[get_column_letter(i)].width = w
        ws.freeze_panes = "A2"
        return

    n_dir_rows = len(direct_dirs)
    sub_tot_row = 1 + n_dir_rows + 1
    loose_row = sub_tot_row + 1
    branch_tot_row = loose_row + 1

    for idx_d, it in enumerate(direct_dirs, start=1):
        rn = 1 + idx_d
        cname = it.get("name", "")
        cid = it["id"]
        cpath = f"{target_path}/{cname}"
        cst = stats.get(cpath, {})
        cmeta = fm.get(cid, {})

        sub_fds = cst.get("total_folders", 0)
        cf = cst.get("content_files", 0)
        sf = cst.get("system_files", 0)
        tf = cst.get("total_files", 0)
        cb = cst.get("content_bytes", 0) + cst.get("system_bytes", 0)
        sh_cnt = cst.get("shortcuts", 0)
        created = sc.fmt_date_vn(cmeta.get("createdTime")) or "—"
        mod_dir = sc.fmt_date_vn(cmeta.get("modifiedTime") or it.get("modifiedTime")) or "—"
        latest_branch = sc.fmt_date_vn(cst.get("latest_mod_iso")) or mod_dir
        owner = cmeta.get("ownerSummary") or sc.summarize_owners(cmeta) or "—"
        share = cmeta.get("shareSummary") or sc.summarize_sharing(cmeta) or "—"
        dom = cst.get("dominant_format") or "—"
        url = sc.drive_url(cid, sc.FOLDER_MIME)

        ws.append([
            idx_d,
            cname,
            _folder_group_label(cname, cpath),
            sub_fds,
            cf,
            sf,
            tf,
            sc.human_size(cb),
            cb,
            f"=IF($I${branch_tot_row}>0, I{rn}/$I${branch_tot_row}, 0)",
            f"=IF($G${branch_tot_row}>0, G{rn}/$G${branch_tot_row}, 0)",
            sh_cnt,
            created,
            mod_dir,
            latest_branch,
            dom,
            owner,
            share,
            cid,
            url,
        ])
        for ci in range(1, n_cols + 1):
            c = ws.cell(rn, ci)
            c.border = _BORDER
            c.font = _BOLD_FONT if ci == 2 else _REG_FONT
            if ci in (1, 4, 5, 6, 7, 9, 12):
                c.number_format = _NUM_INT
                c.alignment = _ALIGN_RIGHT
            elif ci in (10, 11):
                c.number_format = _NUM_PCT
                c.alignment = _ALIGN_RIGHT
            elif ci == 8:
                c.alignment = _ALIGN_RIGHT
        u = ws.cell(rn, 20)
        u.hyperlink, u.font = url, _LINK_FONT

    # Tổng hợp khối thư mục con
    sum_sub_bytes = branch_st["total_bytes"] - branch_st["direct_bytes"]
    ws.append([
        "—",
        "Tổng các thư mục con trực tiếp",
        f"{n_dir_rows} thư mục con",
        f"=SUM(D2:D{1 + n_dir_rows})",
        f"=SUM(E2:E{1 + n_dir_rows})",
        f"=SUM(F2:F{1 + n_dir_rows})",
        f"=SUM(G2:G{1 + n_dir_rows})",
        sc.human_size(sum_sub_bytes),
        f"=SUM(I2:I{1 + n_dir_rows})",
        f"=IF($I${branch_tot_row}>0, I{sub_tot_row}/$I${branch_tot_row}, 0)",
        f"=IF($G${branch_tot_row}>0, G{sub_tot_row}/$G${branch_tot_row}, 0)",
        f"=SUM(L2:L{1 + n_dir_rows})",
        "", "", "", "", "", "", "", "",
    ])
    for ci in range(1, n_cols + 1):
        c = ws.cell(sub_tot_row, ci)
        c.fill, c.font, c.border = _TOTAL_FILL, _BOLD_FONT, _BORDER
        if ci in (4, 5, 6, 7, 9, 12):
            c.number_format, c.alignment = _NUM_INT, _ALIGN_RIGHT
        elif ci in (10, 11):
            c.number_format, c.alignment = _NUM_PCT, _ALIGN_RIGHT
        elif ci == 8:
            c.alignment = _ALIGN_RIGHT

    # Tệp nằm trực tiếp tại thư mục hiện hành
    loose_sh = sum(1 for it in items if it.get("mimeType") == sc.SHORTCUT_MIME)
    ws.append([
        "—",
        "Tệp nằm trực tiếp tại thư mục hiện hành",
        "Trực tiếp",
        0,
        branch_st["direct_content_files"],
        branch_st["direct_system_files"],
        branch_st["direct_files"],
        sc.human_size(branch_st["direct_bytes"]),
        branch_st["direct_bytes"],
        f"=IF($I${branch_tot_row}>0, I{loose_row}/$I${branch_tot_row}, 0)",
        f"=IF($G${branch_tot_row}>0, G{loose_row}/$G${branch_tot_row}, 0)",
        loose_sh,
        "", "", "", "", "", "", "", "",
    ])
    for ci in range(1, n_cols + 1):
        c = ws.cell(loose_row, ci)
        c.fill, c.font, c.border = _LOOSE_FILL, _REG_FONT, _BORDER
        if ci in (4, 5, 6, 7, 9, 12):
            c.number_format, c.alignment = _NUM_INT, _ALIGN_RIGHT
        elif ci in (10, 11):
            c.number_format, c.alignment = _NUM_PCT, _ALIGN_RIGHT
        elif ci == 8:
            c.alignment = _ALIGN_RIGHT

    # Tổng toàn nhánh (= thư mục con + cháu + tệp trực tiếp)
    ws.append([
        "—",
        "TỔNG TOÀN NHÁNH (Bao gồm thư mục con & tệp trực tiếp)",
        "Toàn nhánh",
        f"=COUNT(A2:A{1 + n_dir_rows})+D{sub_tot_row}",
        f"=E{sub_tot_row}+E{loose_row}",
        f"=F{sub_tot_row}+F{loose_row}",
        f"=G{sub_tot_row}+G{loose_row}",
        sc.human_size(branch_st["total_bytes"]),
        f"=I{sub_tot_row}+I{loose_row}",
        f"=J{sub_tot_row}+J{loose_row}",
        f"=K{sub_tot_row}+K{loose_row}",
        f"=L{sub_tot_row}+L{loose_row}",
        "", "", "", "", "", "", "", "",
    ])
    for ci in range(1, n_cols + 1):
        c = ws.cell(branch_tot_row, ci)
        c.fill, c.font, c.border = _SUB_FILL, _BOLD_FONT, _TOTAL_BORDER
        if ci in (4, 5, 6, 7, 9, 12):
            c.number_format, c.alignment = _NUM_INT, _ALIGN_RIGHT
        elif ci in (10, 11):
            c.number_format, c.alignment = _NUM_PCT, _ALIGN_RIGHT
        elif ci == 8:
            c.alignment = _ALIGN_RIGHT

    for i, w in enumerate([8, 40, 25, 18, 15, 15, 15, 15, 20, 19, 17, 14, 14, 16, 19, 24, 18, 28, 36, 50], start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:T{1 + n_dir_rows}"


def build_xlsx(
    index: dict,
    target_path: str,
    out_xlsx: Path | str,
    folder_meta: Optional[dict] = None,
    shortcut_cache: Optional[dict] = None,
    tree_ctx: Optional[dict] = None,
) -> int:
    rows, _, _ = build_xlsx_with_stats(
        index, target_path, out_xlsx,
        folder_meta=folder_meta, shortcut_cache=shortcut_cache, tree_ctx=tree_ctx,
    )
    return rows


def build_xlsx_with_stats(
    index: dict,
    target_path: str,
    out_xlsx: Path | str,
    folder_meta: Optional[dict] = None,
    shortcut_cache: Optional[dict] = None,
    tree_ctx: Optional[dict] = None,
) -> Tuple[int, int, int]:
    if tree_ctx is None:
        tree_ctx = precompute_tree_rollup(index, folder_meta=folder_meta, shortcut_cache=shortcut_cache)
    fm = tree_ctx["folder_meta"]
    sh = tree_ctx["shortcut_cache"]
    stats = tree_ctx["stats"]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Danh Mục Hệ Thống"

    headers = [
        "STT", "Phân Loại", "Định Dạng", "Cấp Độ", "Tên Mục (Chuẩn V6)",
        "Thông Tin Bổ Sung", "Đường Dẫn Thư Mục Cha",
        "Số Thư Mục Con", "Số Tệp Tin", "Dung Lượng", "Dung Lượng (Byte)",
        "Ngày Tạo", "Cập Nhật Lần Cuối", "Chủ Sở Hữu", "Chia Sẻ & Quyền",
        "ID Google Drive", "URL Truy Cập Trực Tiếp",
    ]
    n_cols = len(headers)
    ws.append(headers)
    _style_header_row(ws, 1, n_cols)

    base_depth = index.get(target_path, {}).get("depth", target_path.count("/"))
    rows_out = []
    n_folders = n_files = 0
    by_level: Dict[int, List[int]] = defaultdict(lambda: [0, 0, 0, 0])
    by_cat: Dict[str, List[int]] = defaultdict(lambda: [0, 0])
    by_ext: Dict[str, List[int]] = defaultdict(lambda: [0, 0])
    heavy_candidates: List[Tuple[int, str, dict]] = []
    recent_candidates: List[Tuple[str, str, dict]] = []

    for path in _iter_subtree_paths(index, target_path, tree_ctx):
        data = index[path]
        sys_dir = _is_system_path(path)
        rel = data.get("depth", path.count("/")) - base_depth + 1
        for it in sorted(data.get("items", []), key=lambda x: (x.get("mimeType") != sc.FOLDER_MIME, x.get("name", ""))):
            mime = it.get("mimeType", "")
            name = it.get("name", "")
            fid = it["id"]
            is_f = mime == sc.FOLDER_MIME
            fmt_lbl = sc.format_label(mime, name)

            if is_f:
                n_folders += 1
                by_level[rel][0] += 1
                cpath = f"{path}/{name}"
                cst = stats.get(cpath, {})
                cmeta = fm.get(fid, {})
                sub_f_cnt: object = cst.get("total_folders", 0)
                sub_fl_cnt: object = cst.get("total_files", 0)
                sz = cst.get("total_bytes", 0)
                sz_disp = sc.human_size(sz)
                extra_info = sc.extract_extra_info_v6(name, mime, path)
                created_d = sc.fmt_date_vn(cmeta.get("createdTime")) or "—"
                mod_d = sc.fmt_date_vn(cmeta.get("modifiedTime") or it.get("modifiedTime")) or "—"
                owner_s = cmeta.get("ownerSummary") or sc.summarize_owners(cmeta) or "—"
                share_s = cmeta.get("shareSummary") or sc.summarize_sharing(cmeta) or "—"
                kind_lbl = "Thư mục"
                cat_sz = 0
            else:
                n_files += 1
                sz = int(it.get("size") or 0)
                if sys_dir:
                    by_level[rel][2] += 1
                else:
                    by_level[rel][1] += 1
                by_level[rel][3] += sz
                sc_rec = sh.get(fid) if mime == sc.SHORTCUT_MIME else None
                sub_f_cnt = ""
                sub_fl_cnt = ""
                sz_disp = sc.human_size(sz) if sz or mime not in sc.GOOGLE_NATIVE_MIMES else "—"
                extra_info = sc.extract_extra_info_v6(name, mime, path, shortcut_info=sc_rec)
                if sc_rec:
                    created_d = sc.fmt_date_vn(sc_rec.get("createdTime")) or "—"
                    owner_s = sc_rec.get("ownerSummary") or "—"
                    share_s = sc_rec.get("shareSummary") or "—"
                else:
                    created_d = "—"
                    owner_s = "—"
                    share_s = "—"
                mod_d = sc.fmt_date_vn(it.get("modifiedTime")) or "—"
                kind_lbl = "Tệp tin"
                cat_sz = sz

                by_ext[fmt_lbl][0] += 1
                by_ext[fmt_lbl][1] += sz
                if sz > 0 and not _is_dmht_sheet(it):
                    heavy_candidates.append((sz, path, it))
                mod_iso = it.get("modifiedTime") or ""
                if mod_iso and not _is_dmht_sheet(it):
                    recent_candidates.append((mod_iso, path, it))

            cat_label = _classify_item(it)
            by_cat[cat_label][0] += 1
            by_cat[cat_label][1] += cat_sz

            url = sc.drive_url(fid, mime)
            rows_out.append((
                kind_lbl,
                fmt_lbl,
                rel,
                name,
                extra_info,
                path,
                sub_f_cnt,
                sub_fl_cnt,
                sz_disp,
                sz,
                created_d,
                mod_d,
                owner_s,
                share_s,
                fid,
                url,
                is_f,
            ))

    for idx_r, r in enumerate(rows_out, start=1):
        ws.append([idx_r, *r[:16]])
        rn = idx_r + 1
        is_f = r[16]
        row_fill = _FOLDER_FILL if is_f else _NONE_FILL
        row_font = _BOLD_FONT if is_f else _REG_FONT
        for ci in range(1, n_cols + 1):
            c = ws.cell(row=rn, column=ci)
            c.border = _BORDER
            c.fill = row_fill
            c.font = row_font
            if ci in (1, 4, 8, 9, 11):
                if c.value != "":
                    c.number_format = _NUM_INT
                    c.alignment = _ALIGN_RIGHT
            elif ci == 10:
                c.alignment = _ALIGN_RIGHT
        u = ws.cell(row=rn, column=n_cols)
        u.hyperlink = r[15]
        u.font = _FOLDER_LINK_FONT if is_f else _LINK_FONT

    widths = [8, 12, 16, 10, 48, 34, 46, 17, 15, 15, 20, 14, 17, 18, 28, 36, 50]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:Q{max(1, len(rows_out) + 1)}"

    heavy_candidates.sort(key=lambda x: (-x[0], x[2].get("name", "")))
    recent_candidates.sort(key=lambda x: x[0], reverse=True)
    branch_st = stats.get(target_path, {
        "direct_folders": 0, "direct_content_folders": 0, "direct_files": 0,
        "direct_content_files": 0, "direct_system_files": 0, "direct_bytes": 0,
        "total_folders": n_folders, "total_content_folders": n_folders,
        "total_files": n_files, "content_files": n_files, "system_files": 0,
        "shortcuts": 0, "broken_shortcuts": 0, "total_bytes": 0,
        "content_bytes": 0, "system_bytes": 0, "empty_descendant_folders": 0,
        "latest_mod_iso": "", "dominant_format": "—",
    })

    _write_summary_sheet(
        wb, index, target_path, branch_st, fm, sh,
        by_level, by_cat, by_ext,
        heavy_candidates[:15], recent_candidates[:15],
    )
    _write_children_sheet(wb, index, target_path, branch_st, tree_ctx)

    out_path = Path(out_xlsx)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    return len(rows_out), n_folders, n_files


# Giữ tương thích chữ ký hàm cũ từ `sheet_engine.py` v1/v2
def build_xlsx_for_path(index_data: dict, target_path: str, out_xlsx: str) -> Tuple[int, int, int]:
    return build_xlsx_with_stats(index_data, target_path, out_xlsx)


def _find_prev_snapshot_index(current_index_path: Path) -> Optional[dict]:
    snaps = sorted(sc.snapshots_dir().glob("storage_index_*.json*"))
    if not snaps:
        return None
    cand = snaps[-2] if len(snaps) >= 2 else snaps[-1]
    try:
        opener = gzip.open if cand.suffix == ".gz" else open
        with opener(cand, "rt", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "folders" in data:
            return data["folders"]
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def filter_changed_targets(
    index: dict,
    targets: List[dict],
    sync_state: dict,
    only_changed: bool,
    force_all: bool,
    prev_index: Optional[dict] = None,
    resume: bool = False,
    tree_ctx: Optional[dict] = None,
) -> Tuple[List[dict], Dict[str, str]]:
    """Trả về `(targets_can_cap_nhat, signatures_by_path)`."""
    sigs: Dict[str, str] = {}
    todo: List[dict] = []
    synced_by_path = {v.get("path"): (k, v) for k, v in sync_state.items() if isinstance(v, dict) and v.get("path")}
    for t in targets:
        path = t["path"]
        sid = t["sheet_id"]
        sig = compute_subtree_signature(index, path, include_schema=True, tree_ctx=tree_ctx)
        sigs[path] = sig
        if force_all or (not only_changed and not resume):
            todo.append(t)
            continue
        recorded = sync_state.get(sid) if sid else None
        if recorded is None and path in synced_by_path:
            rec_sid, rec_val = synced_by_path[path]
            if not sid:
                t["sheet_id"] = rec_sid
            recorded = rec_val
        if recorded is not None:
            if recorded.get("sig") != sig:
                todo.append(t)
            continue
        if not t["sheet_id"]:
            todo.append(t)
            continue
        if only_changed and not resume and prev_index is not None and path in prev_index and t["depth"] > 1:
            sig_now_raw = compute_subtree_signature(index, path, include_schema=False, tree_ctx=tree_ctx)
            sig_prev_raw = compute_subtree_signature(prev_index, path, include_schema=False)
            if sig_now_raw == sig_prev_raw:
                continue
        todo.append(t)
    return todo, sigs


def collect_title_fixes(targets: List[dict]) -> List[dict]:
    fixes = []
    for t in targets:
        sid = t["sheet_id"]
        cur = t["current_name"]
        exp = t["sheet_name"]
        if not sid or not cur or cur == exp:
            continue
        if sc.nfc(exp) in t.get("sibling_names", set()) and sc.nfc(cur) != sc.nfc(exp):
            continue
        fixes.append({"id": sid, "path": t["path"], "old_name": cur, "new_name": exp})
    return fixes


def ensure_catalog_folder_path(drive: sc.Drive, index: dict, target_path: str) -> str:
    """Đảm bảo thư mục gương trong `[00] TỔNG QUAN/[01] DANH SÁCH/<rel_path>` tồn tại và trả về ID."""
    if target_path == sc.ROOT_NAME:
        return sc.tong_quan_id()
    cat_path = sc.catalog_folder_for_path(target_path)
    existing_id = index.get(cat_path, {}).get("id")
    if existing_id:
        return existing_id
    prefix = f"{sc.ROOT_NAME}/"
    rel = target_path[len(prefix):] if target_path.startswith(prefix) else target_path
    parts = [p for p in rel.split("/") if p]
    cur_id = sc.danh_sach_id()
    cur_cat = sc.DANH_SACH_PATH
    for part in parts:
        cur_cat = f"{cur_cat}/{part}"
        cid = index.get(cur_cat, {}).get("id")
        if not cid:
            cid = drive.ensure_folder(part, cur_id)
        cur_id = cid
    return cur_id


def process_one(
    drive: sc.Drive,
    index: dict,
    t: dict,
    tmp_dir: str,
    create_missing: bool,
    tree_ctx: Optional[dict] = None,
):
    safe_id = t["sheet_id"] or f"new_{abs(hash(t['path']))}"
    xlsx = Path(tmp_dir) / f"{safe_id}.xlsx"
    rows, nf, nfl = build_xlsx_with_stats(index, t["path"], xlsx, tree_ctx=tree_ctx)
    try:
        if t["sheet_id"]:
            drive.update(t["sheet_id"], xlsx, mime_type=SHEET_MIME)
            if t["path"] == sc.ROOT_NAME and sc.MASTER_SHEET_LIST_ID:
                drive.update(sc.MASTER_SHEET_LIST_ID, xlsx, mime_type=SHEET_MIME)
            return t, "cập nhật", (rows, nf, nfl), t["sheet_id"], ""
        if not create_missing:
            return t, "bỏ qua (chưa có bảng)", (rows, nf, nfl), "", ""
        if not t["tq_id"] and t["path"] in index:
            drive.ensure_folder(sc.TONG_QUAN_FOLDER, index[t["path"]]["id"])
        dest_folder_id = t.get("cat_folder_id") or ensure_catalog_folder_path(drive, index, t["path"])
        new_id = drive.upload(xlsx, dest_folder_id, mime_type=SHEET_MIME)
        if new_id:
            drive.rename(new_id, t["sheet_name"])
        return t, "tạo mới", (rows, nf, nfl), new_id, ""
    except sc.DriveError as e:
        return t, "lỗi", (rows, nf, nfl), t.get("sheet_id") or "", str(e)
    finally:
        try:
            xlsx.unlink()
        except OSError:
            pass


def migrate_sheets_to_danh_sach_tree(
    drive: sc.Drive,
    index: dict,
    branch: Optional[str] = None,
    workers: int = 24,
    dry_run: bool = False,
    assume_yes: bool = False,
) -> Tuple[int, int, int]:
    """
    Tạo cây thư mục đệ quy phản chiếu 1:1 trong `[A] STORAGE/[00] TỔNG QUAN/[01] DANH SÁCH`
    và di chuyển toàn bộ bảng `Danh Mục Hệ Thống - <Tên>` (trừ bảng gốc `Storage`) về đó.
    Trả về `(so_thu_muc_tao_moi, so_bang_da_chuyen, so_loi)`.
    """
    all_targets = [
        t for t in discover_targets(index, branch=branch, max_depth=99)
        if t["path"] != sc.ROOT_NAME and t["sheet_id"]
    ]
    root_prefix = f"{sc.ROOT_NAME}/"
    required_rels_set = set()
    for t in all_targets:
        rel = t["path"][len(root_prefix):]
        parts = rel.split("/")
        for k in range(1, len(parts) + 1):
            required_rels_set.add("/".join(parts[:k]))
    required_rels = sorted(required_rels_set, key=lambda r: (r.count("/"), r))

    folders_ckpt_path = sc.data_dir() / "catalog_tree_folders.json"
    moves_ckpt_path = sc.data_dir() / "catalog_tree_moves.json"
    raw_folder_map: Dict[str, str] = sc.read_json(folders_ckpt_path, {}) or {}
    # Loại bỏ các ID 32 ký tự bị cắt dấu '-' ở cuối để ensure_folder tự tra lại ID 33 ký tự thật trên Drive
    folder_map: Dict[str, str] = {
        k: v for k, v in raw_folder_map.items()
        if k == "" or (isinstance(v, str) and len(v) != 32)
    }
    folder_map[""] = sc.danh_sach_id()
    ds_prefix = f"{sc.DANH_SACH_PATH}/"
    for p, d in index.items():
        if p.startswith(ds_prefix) and d.get("id") and len(d["id"]) != 32:
            folder_map.setdefault(p[len(ds_prefix):], d["id"])

    moved_map: Dict[str, str] = sc.read_json(moves_ckpt_path, {}) or {}
    for t in all_targets:
        sid = t["sheet_id"]
        cat_items = index.get(t["cat_path"], {}).get("items", [])
        if any(it.get("id") == sid for it in cat_items) and t.get("cat_folder_id"):
            moved_map.setdefault(sid, t["cat_folder_id"])

    missing_folders = [r for r in required_rels if r not in folder_map]
    pending_targets = [
        t for t in all_targets
        if moved_map.get(t["sheet_id"]) != folder_map.get(t["path"][len(root_prefix):], "__missing__")
    ]

    sc.log(
        f"[Cây danh mục đệ quy] Nhánh đích: {sc.DANH_SACH_PATH} ({sc.danh_sach_id()})\n"
        f"  • Tổng thư mục gương cần có : {len(required_rels)} (cần tạo mới: {len(missing_folders)})\n"
        f"  • Tổng bảng Danh Mục cần gom: {len(all_targets)} (cần di chuyển: {len(pending_targets)})"
    )
    if dry_run:
        sc.log("(Chạy thử — thêm --thuc-thi để tạo cây thư mục gương và di chuyển bảng về [01] DANH SÁCH.)")
        return len(missing_folders), len(pending_targets), 0

    if not missing_folders and not pending_targets:
        sc.log("Toàn bộ cây thư mục gương và bảng Danh Mục Hệ Thống đã nằm trong [01] DANH SÁCH.")
    else:
        if not sc.confirm(
            f"Tạo {len(missing_folders)} thư mục gương và di chuyển {len(pending_targets)} bảng Danh Mục về {sc.DANH_SACH_PATH}?",
            assume_yes,
        ):
            return 0, 0, 0

    created_folders = 0
    errors = 0

    # 1. Tạo cây thư mục gương theo từng độ sâu (1..max_depth)
    by_depth: Dict[int, List[str]] = defaultdict(list)
    for r in required_rels:
        by_depth[r.count("/") + 1].append(r)

    for depth in sorted(by_depth):
        level_rels = by_depth[depth]
        todo_rels = [r for r in level_rels if r not in folder_map]
        if not todo_rels:
            continue
        # Nếu tầng này đang chạy tiếp sau gián đoạn (hoặc tầng 1), dùng ensure_folder để chống tạo trùng
        use_ensure = (depth == 1) or (len(todo_rels) < len(level_rels))
        sc.log(f"  [Cấp {depth:02d}] Đang tạo {len(todo_rels)}/{len(level_rels)} thư mục gương ({workers} luồng)...")

        def _create_one_dir(rel_path: str) -> Tuple[str, str, str]:
            parent_rel = rel_path.rsplit("/", 1)[0] if "/" in rel_path else ""
            leaf = rel_path.rsplit("/", 1)[-1]
            parent_id = folder_map.get(parent_rel, "")
            if not parent_id:
                return rel_path, "", f"Thiếu thư mục cha cho {rel_path}"
            try:
                fid = drive.ensure_folder(leaf, parent_id) if use_ensure else drive.mkdir(leaf, parent_id)
                return rel_path, fid, ""
            except Exception as exc:
                return rel_path, "", str(exc)

        with cf.ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(_create_one_dir, r) for r in todo_rels]
            for n, fut in enumerate(cf.as_completed(futs), 1):
                rel_p, fid, err = fut.result()
                if fid:
                    folder_map[rel_p] = fid
                    created_folders += 1
                else:
                    errors += 1
                    sc.log(f"    ! Lỗi tạo thư mục {rel_p}: {err[:180]}")
                if n % 25 == 0 or n == len(futs):
                    sc.write_json(folders_ckpt_path, folder_map, indent=None)
        sc.write_json(folders_ckpt_path, folder_map, indent=None)
        sc.log(f"  [Cấp {depth:02d}] Xong ({len(folder_map) - 1}/{len(required_rels)} thư mục gương sẵn sàng).")

    # 2. Di chuyển các bảng Danh Mục Hệ Thống về thư mục gương tương ứng
    move_tasks: List[Tuple[dict, str, str]] = []
    for t in all_targets:
        sid = t["sheet_id"]
        rel = t["path"][len(root_prefix):]
        dest_id = folder_map.get(rel, "")
        if not sid or not dest_id:
            continue
        if moved_map.get(sid) == dest_id:
            continue
        move_tasks.append((t, sid, dest_id))

    moved_ok = 0
    if move_tasks:
        sc.log(f"\nĐang di chuyển {len(move_tasks)} bảng Danh Mục Hệ Thống vào {sc.DANH_SACH_PATH} ({workers} luồng)...")

        def _move_one_sheet(task: Tuple[dict, str, str]) -> Tuple[dict, str, str, str]:
            t_item, s_id, d_id = task
            try:
                drive.move(s_id, d_id)
                return t_item, s_id, d_id, ""
            except Exception as exc:
                return t_item, s_id, d_id, str(exc)

        with cf.ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(_move_one_sheet, task) for task in move_tasks]
            for n, fut in enumerate(cf.as_completed(futs), 1):
                t_item, s_id, d_id, err = fut.result()
                if not err:
                    moved_map[s_id] = d_id
                    moved_ok += 1
                else:
                    errors += 1
                    sc.log(f"    ! Lỗi chuyển bảng {t_item['sheet_name']} ({s_id}): {err[:180]}")
                if n % 25 == 0 or n == len(futs):
                    sc.write_json(moves_ckpt_path, moved_map, indent=None)
                    sc.log(f"  → Đã chuyển {n}/{len(futs)} bảng (thành công: {moved_ok}, lỗi: {errors})")
        sc.write_json(moves_ckpt_path, moved_map, indent=None)

    # 3. Đồng bộ ngay cấu trúc storage_index.json tại chỗ
    now_iso = sc.now_utc_iso()
    ds_entry = index.setdefault(sc.DANH_SACH_PATH, {
        "id": sc.danh_sach_id(),
        "depth": sc.DANH_SACH_PATH.count("/"),
        "items": [],
    })
    ds_entry["id"] = sc.danh_sach_id()

    for rel in required_rels:
        fid = folder_map.get(rel)
        if not fid:
            continue
        full_cat = f"{sc.DANH_SACH_PATH}/{rel}"
        parent_cat = full_cat.rsplit("/", 1)[0]
        leaf_name = full_cat.rsplit("/", 1)[-1]
        cat_entry = index.setdefault(full_cat, {
            "id": fid,
            "depth": full_cat.count("/"),
            "items": [],
        })
        cat_entry["id"] = fid
        cat_entry["depth"] = full_cat.count("/")
        if parent_cat in index:
            p_items = [
                it for it in index[parent_cat].get("items", [])
                if not (it.get("mimeType") == sc.FOLDER_MIME and (it.get("name") == leaf_name or len(it.get("id", "")) == 32))
            ]
            p_items.append({
                "id": fid,
                "name": leaf_name,
                "mimeType": sc.FOLDER_MIME,
                "modifiedTime": now_iso,
            })
            index[parent_cat]["items"] = p_items

    for t in all_targets:
        sid = t["sheet_id"]
        rel = t["path"][len(root_prefix):]
        dest_id = folder_map.get(rel)
        if not sid or not dest_id or moved_map.get(sid) != dest_id:
            continue
        full_cat = f"{sc.DANH_SACH_PATH}/{rel}"
        old_tq_path = f"{t['path']}/{sc.TONG_QUAN_FOLDER}"
        sheet_obj = None
        if old_tq_path in index:
            old_items = index[old_tq_path].get("items", [])
            kept = []
            for it in old_items:
                if it.get("id") == sid:
                    sheet_obj = it
                else:
                    kept.append(it)
            index[old_tq_path]["items"] = kept
        if sheet_obj is None:
            sheet_obj = {
                "id": sid,
                "name": t["current_name"] or t["sheet_name"],
                "mimeType": SHEET_MIME,
                "modifiedTime": now_iso,
            }
        cat_items = index[full_cat].setdefault("items", [])
        if not any(it.get("id") == sid for it in cat_items):
            cat_items.append(sheet_obj)

    sc.save_index(index)
    sc.log(
        f"Hoàn tất tập trung hóa cây danh mục: tạo mới {created_folders} thư mục gương, "
        f"di chuyển {moved_ok} bảng, lỗi {errors}. Đã cập nhật {sc.index_path()}"
    )
    return created_folders, moved_ok, errors


def refresh_key_sheets(max_depth: int = 2, workers: int = 8) -> None:
    """Hàm tương thích nhanh để làm mới các bảng trọng yếu từ cấp 0..max_depth."""
    index = sc.load_index()
    tree_ctx = precompute_tree_rollup(index)
    targets = discover_targets(index, branch=None, max_depth=max_depth)
    have = [t for t in targets if t["sheet_id"]]
    drive = sc.create_drive()
    tmp_dir = tempfile.mkdtemp(prefix="danh_muc_key_")
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(process_one, drive, index, t, tmp_dir, False, tree_ctx) for t in have]
        for f in cf.as_completed(futs):
            f.result()


def _write_sheets_log(all_targets: List[dict], sync_state: dict, tree_ctx: dict, fix_names: bool = False) -> None:
    rollup_stats = tree_ctx["stats"]
    sheets_map = {}
    for t in all_targets:
        sid = t["sheet_id"] or next((k for k, v in sync_state.items() if v.get("path") == t["path"]), None)
        if sid:
            bst = rollup_stats.get(t["path"], {})
            st_rec = sync_state.get(sid, {})
            entry = {
                "path": t["path"],
                "depth": t["depth"],
                "tq_id": t["tq_id"],
                "cat_path": t.get("cat_path") or sc.catalog_folder_for_path(t["path"]),
                "cat_folder_id": t.get("cat_folder_id"),
                "sheet_name": st_rec.get("sheet_name") or (t["sheet_name"] if fix_names or not t["current_name"] else t["current_name"]),
                "sheet_id": sid,
                "url": sc.drive_url(sid, SHEET_MIME),
                "rows": bst.get("total_folders", 0) + bst.get("total_files", 0),
                "folders": bst.get("total_folders", 0),
                "files": bst.get("total_files", 0),
                "content_files": bst.get("content_files", 0),
                "system_files": bst.get("system_files", 0),
                "total_bytes": bst.get("total_bytes", 0),
                "schema_version": st_rec.get("schema_version", "v1/v2"),
            }
            if t["path"] == sc.ROOT_NAME and sc.MASTER_SHEET_LIST_ID:
                entry["sheet_id_danh_sach"] = sc.MASTER_SHEET_LIST_ID
            sheets_map[t["path"]] = entry
    sc.write_json(sc.sheets_log_path(), sheets_map, indent=1)


def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(description="Động cơ cập nhật & chuẩn hóa Danh Mục Hệ Thống V7 (v4.0).")
    ap.add_argument("--nhanh", help="Giới hạn trong một nhánh")
    ap.add_argument("--do-sau", type=int, default=99, help="Độ sâu tối đa của thư mục đích (mặc định: 99 = toàn bộ)")
    ap.add_argument("--do-sau-tu", type=int, default=0, help="Độ sâu tối thiểu của thư mục đích (mặc định: 0)")
    ap.add_argument("--chi-thay-doi", action="store_true", help="Chỉ cập nhật bảng có nhánh con hoặc siêu dữ liệu biến động")
    ap.add_argument("--tiep-tuc", action="store_true", help="Bỏ qua các bảng đã khớp chữ ký trong sheets_sync_state.json")
    ap.add_argument("--toan-bo", action="store_true", help="Ép cập nhật lại toàn bộ bảng bất kể đã đồng bộ")
    ap.add_argument("--tao-moi", action="store_true", help="Tạo bảng cho thư mục chưa có (đặt tại cây [01] DANH SÁCH)")
    ap.add_argument("--sua-ten-bang", action="store_true", help="Chuẩn hóa tên bảng lệch quy ước")
    ap.add_argument("--chuan-hoa-v7", action="store_true", help="Lập/thực thi kế hoạch Chuẩn Danh Mục V7 (đổi tên không trùng + tinh gọn thông minh)")
    ap.add_argument("--chi-doi-ten", action="store_true", help="Khi dùng --chuan-hoa-v7: chỉ đổi tên chuẩn V7, chưa di chuyển bảng tinh gọn")
    ap.add_argument("--che-do-danh-muc", choices=["smart", "full"], default="smart", help="Chế độ tinh gọn danh mục (mặc định: smart)")
    ap.add_argument("--gom-ve-danh-sach", action="store_true", help="Tạo cây thư mục đệ quy trong [00] TỔNG QUAN/[01] DANH SÁCH và di chuyển bảng về đó")
    ap.add_argument("--thuc-thi", action="store_true", help="Ghi lên Drive (mặc định chạy thử)")
    ap.add_argument("--dong-y", action="store_true", help="Không hỏi xác nhận")
    ap.add_argument("--luong", type=int, default=12, help="Số luồng song song (mặc định 12)")
    ap.add_argument("--xuat-cuc-bo", help="Chỉ xuất tệp .xlsx của một đường dẫn ra máy (không ghi Drive)")
    args = ap.parse_args(argv)

    index = sc.load_index()
    branch = sc.normalize_branch(args.nhanh)
    if branch == sc.ROOT_NAME:
        branch = None

    if args.chuan_hoa_v7:
        policy = {"mode": args.che_do_danh_muc}
        plan = sc.build_catalog_migration_plan(index, branch=branch, policy=policy)
        s = plan["summary"]
        plan_out = sc.reports_dir() / f"Kế Hoạch Chuẩn Hóa Danh Mục V7 - Storage, {sc.today_vn()}.json"
        sc.write_json(plan_out, plan, indent=2)
        sc.log(
            f"[Chuẩn Danh Mục V7 | chế độ={args.che_do_danh_muc}] "
            f"Hiện có: {s['existing_sheets']} | Mục tiêu tinh gọn: {s['target_eligible_catalogs']} | "
            f"Giữ nguyên: {s['kept_unchanged']} | Đổi tên chuẩn V7: {s['renames_count']} | "
            f"Tinh gọn/cách ly: {s['prunes_count']} (rác kỹ thuật: {s['prunes_junk_count']}, tinh gọn: {s['prunes_smart_count']}) | "
            f"Thiếu mới: {s['missing_count']}"
        )
        for r in plan["renames"][:15]:
            sc.log(f"  • đổi tên: {r['old_name']}  →  {r['new_name']}")
        sc.log(f"Kế hoạch chi tiết: {plan_out}")
        if not args.thuc_thi:
            sc.log("(Chạy thử — thêm --thuc-thi --dong-y để áp dụng lên Drive; hỗ trợ hoàn tác 1 lệnh qua `astorage undo`.)")
            return
        apply_prunes = not args.chi_doi_ten
        prompt = f"Thực thi Chuẩn Danh Mục V7 ({s['renames_count']} đổi tên" + (f" + {s['prunes_count']} cách ly tinh gọn" if apply_prunes else "") + ")?"
        if not sc.confirm(prompt, args.dong_y):
            return
        drive = sc.create_drive()
        with sc.StorageDB() as db:
            res = sc.apply_catalog_migration_plan(
                drive,
                plan,
                execute=True,
                apply_prunes=apply_prunes,
                db=db,
                workers=args.luong,
                index=index,
            )
        if res.get("index_updated"):
            sc.save_index(index)
        sc.log(
            f"Hoàn tất Chuẩn Danh Mục V7: đổi tên={res['renamed']} | tinh gọn/cách ly={res['pruned']} | "
            f"lỗi={len(res['errors'])} | mã hoàn tác={res['batch_id'] or '—'}"
        )
        return

    if args.gom_ve_danh_sach:
        drive = sc.create_drive()
        migrate_sheets_to_danh_sach_tree(
            drive,
            index,
            branch=branch,
            workers=args.luong,
            dry_run=not args.thuc_thi,
            assume_yes=args.dong_y,
        )
        if args.thuc_thi:
            tree_ctx = precompute_tree_rollup(index)
            all_targets = discover_targets(index, None, 99)
            sync_state = sc.read_json(sync_state_path(), {}) or {}
            _write_sheets_log(all_targets, sync_state, tree_ctx)
        return

    tree_ctx = precompute_tree_rollup(index)
    if args.xuat_cuc_bo:
        p = sc.normalize_branch(args.xuat_cuc_bo)
        out = sc.reports_dir() / f"{sheet_name_for(p)}.xlsx"
        n, nf, nfl = build_xlsx_with_stats(index, p, out, tree_ctx=tree_ctx)
        sc.log(f"Đã xuất {n} dòng ({nf} thư mục, {nfl} tệp | 3 tab {SCHEMA_VERSION}) → {out}")
        return

    all_targets = discover_targets(index, branch, 99)
    if args.che_do_danh_muc == "smart":
        decisions = sc.evaluate_catalog_scope(index, branch=branch, policy={"mode": "smart"})
        for t in all_targets:
            dec = decisions.get(t["path"])
            if dec and dec.include and dec.final_title:
                t["sheet_name"] = dec.final_title
        all_targets = [t for t in all_targets if (decisions.get(t["path"]) is None or decisions[t["path"]].include)]
    targets = [t for t in all_targets if args.do_sau_tu <= t["depth"] <= args.do_sau]
    have = [t for t in targets if t["sheet_id"]]
    missing = [t for t in targets if not t["sheet_id"]]

    state_p = sync_state_path()
    sync_state = sc.read_json(state_p, {}) or {}
    prev_index = _find_prev_snapshot_index(sc.index_path()) if (args.chi_thay_doi and not args.toan_bo and not args.tiep_tuc) else None

    active_pool = targets if args.tao_moi else have
    to_update, sigs = filter_changed_targets(
        index,
        active_pool,
        sync_state,
        only_changed=args.chi_thay_doi and not args.toan_bo,
        force_all=args.toan_bo,
        prev_index=prev_index,
        resume=args.tiep_tuc and not args.toan_bo,
        tree_ctx=tree_ctx,
    )
    title_fixes = collect_title_fixes(have) if args.sua_ten_bang else []

    sc.log(
        f"[{SCHEMA_VERSION}] Thư mục đích ({args.do_sau_tu}..{args.do_sau}): {len(targets)} | "
        f"đã có bảng: {len(have)} | chưa có bảng: {len(missing)} | "
        f"cần cập nhật nội dung: {len(to_update)} | cần chuẩn hóa tên bảng: {len(title_fixes)} | "
        f"cache siêu dữ liệu thư mục: {len(tree_ctx['folder_meta'])} | cache shortcut: {len(tree_ctx['shortcut_cache'])}"
    )
    for t in missing[:10]:
        sc.log(f"  - thiếu: {t['path']}  →  {t['sheet_name']}")
    for fx in title_fixes[:15]:
        sc.log(f"  - đổi tên bảng: {fx['old_name']}  →  {fx['new_name']}")

    if not args.thuc_thi:
        sc.log("(Chạy thử — thêm --thuc-thi để cập nhật Drive; --chi-thay-doi / --tao-moi / --sua-ten-bang / --gom-ve-danh-sach.)")
        return

    total_ops = len(title_fixes) + len(to_update)
    if total_ops == 0:
        sc.log("Mọi bảng Danh Mục Hệ Thống đều đã đồng bộ mới nhất.")
        return
    if not sc.confirm(f"Thực thi {len(title_fixes)} lệnh đổi tên bảng + {len(to_update)} lệnh cập nhật/tạo bảng ({SCHEMA_VERSION})?", args.dong_y):
        return

    drive = sc.create_drive()

    if title_fixes:
        sc.log(f"\nĐang chuẩn hóa tên {len(title_fixes)} bảng Danh Mục Hệ Thống...")
        chunks = [title_fixes[i:i + 8] for i in range(0, len(title_fixes), 8)]
        ren_ok = ren_fail = 0
        with cf.ThreadPoolExecutor(max_workers=min(args.luong, len(chunks))) as pool:
            futs = [pool.submit(drive.batch_rename, [(x["id"], x["new_name"]) for x in ch]) for ch in chunks]
            for f in cf.as_completed(futs):
                for fid, success, err in f.result():
                    if success:
                        ren_ok += 1
                    else:
                        ren_fail += 1
                        sc.log(f"  ! lỗi đổi tên {fid}: {err[:160]}")
        sc.log(f"Đổi tên bảng xong: {ren_ok} thành công, {ren_fail} lỗi.")

    if to_update:
        sc.log(f"\nĐang cập nhật/tạo {len(to_update)} bảng (3 tab {SCHEMA_VERSION}) với {args.luong} luồng...")
        tmp_dir = tempfile.mkdtemp(prefix="danh_muc_v3_")
        stats_cnt: Dict[str, int] = {}
        with cf.ThreadPoolExecutor(max_workers=args.luong) as pool:
            futs = [pool.submit(process_one, drive, index, t, tmp_dir, args.tao_moi, tree_ctx) for t in to_update]
            for n, f in enumerate(cf.as_completed(futs), 1):
                t, status, (rows, _, _), sid, err = f.result()
                stats_cnt[status] = stats_cnt.get(status, 0) + 1
                if status in ("cập nhật", "tạo mới") and sid:
                    sync_state[sid] = {
                        "path": t["path"],
                        "sig": sigs[t["path"]],
                        "sheet_name": t["sheet_name"],
                        "schema_version": SCHEMA_VERSION,
                        "rows": rows,
                        "updated_iso": sc.now_utc_iso(),
                    }
                if err:
                    sc.log(f"  ! {t['path']}: {err[:200]}")
                if n % 25 == 0 or n == len(futs):
                    sc.write_json(state_p, sync_state, indent=None)
                    sc.log(f"  → {n}/{len(futs)} | " + ", ".join(f"{k}: {v}" for k, v in stats_cnt.items()))
        sc.write_json(state_p, sync_state, indent=None)

    _write_sheets_log(all_targets, sync_state, tree_ctx, fix_names=args.sua_ten_bang)
    sc.log(f"Hoàn tất. Đã lưu trạng thái đồng bộ → {state_p}")


if __name__ == "__main__":
    main()

