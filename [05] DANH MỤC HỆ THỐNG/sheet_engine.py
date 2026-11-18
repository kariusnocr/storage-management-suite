#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ĐỘNG CƠ BẢNG DANH MỤC HỆ THỐNG — [A] STORAGE (CHUẨN V6, v2.0)
=============================================================
Sinh lại nội dung bảng Google Sheets `Danh Mục Hệ Thống - <Tên Thư Mục>` từ chỉ mục mới nhất
(`storage_index.json`) và cập nhật TẠI CHỖ — giữ nguyên ID, URL và quyền chia sẻ.

Nâng cấp v2.0:
- Dùng chung `storage_core.py` (`sc.normalize_sheet_title`, `sc.title_case_vn`, `sc.Drive`).
- Bổ sung tab thứ 2 **`Thống Kê Nhanh`** trong tệp `.xlsx` (tổng quan mục, phân bố theo cấp & định dạng).
- Hỗ trợ `--chi-thay-doi`: tính chữ ký SHA-256 cây con (`sheets_sync_state.json` / đối chiếu snapshot)
  để chỉ cập nhật những bảng (ở mọi độ sâu 0..13) thực sự có biến động.
- Hỗ trợ `--sua-ten-bang`: chuẩn hóa lại tên các bảng bị dính `.pdf`, `_`, sai chữ hoa viết tắt.
- Mặc định CHẠY THỬ; thêm `--thuc-thi` để ghi lên Drive.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import gzip
import hashlib
import json
import os
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def _nap_thu_vien_loi():
    """Tìm `storage_core.py` trong `[01] THƯ VIỆN LÕI` (hoặc biến môi trường STORAGE_CORE_DIR)."""
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
    raise SystemExit(
        "Không tìm thấy storage_core.py — hãy đặt thư mục `[01] THƯ VIỆN LÕI` cạnh chương trình "
        "hoặc khai báo STORAGE_CORE_DIR."
    )


sc = _nap_thu_vien_loi()

try:
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
except ImportError:  # pragma: no cover
    raise SystemExit("Thiếu thư viện openpyxl — cài bằng: pip install openpyxl")

SHEET_MIME = sc.SHEET_MIME
SHEET_PREFIX = "Danh Mục Hệ Thống - "
SCHEMA_VERSION = "v2.0"

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
    ("Tệp nén", lambda m, e: e in {"zip", "rar", "7z", "gz", "tar"} or "zip" in m or "rar" in m),
    ("Mã nguồn / Cấu hình", lambda m, e: e in {"py", "json", "js", "ts", "ipynb", "sh", "yaml", "yml", "xml", "html", "opf"}),
]


def _classify_item(it: dict) -> str:
    mime = it.get("mimeType", "")
    _, ext = sc.split_ext(it.get("name", ""), mime)
    ext = ext.lower()
    for label, fn in _FORMAT_BUCKETS:
        if fn(mime, ext):
            return label
    return "Khác"


def title_case_vn(folder_body: str) -> str:
    return sc.title_case_vn(folder_body)


def sheet_name_for(path: str) -> str:
    return sc.normalize_sheet_title(path)


def sync_state_path() -> Path:
    return sc.data_dir() / "sheets_sync_state.json"


def compute_subtree_signature(index: dict, target_path: str, include_schema: bool = True) -> str:
    """Chữ ký SHA-256 ổn định của toàn bộ nhánh con dưới `target_path`."""
    h = hashlib.sha256()
    if include_schema:
        h.update(f"schema:{SCHEMA_VERSION}\n".encode("utf-8"))
    prefix = target_path + "/"
    paths = sorted(p for p in index if p == target_path or p.startswith(prefix))
    for p in paths:
        data = index[p]
        h.update(f"D|{p}|{data.get('id', '')}\n".encode("utf-8"))
        for it in sorted(data.get("items", []), key=lambda x: (x.get("id", ""), x.get("name", ""))):
            mime = it.get("mimeType", "")
            name = it.get("name", "")
            is_dmht = (mime == SHEET_MIME and name.startswith(SHEET_PREFIX)) or (
                mime == sc.FOLDER_MIME and name == sc.TONG_QUAN_FOLDER
            )
            mod = "" if is_dmht else (it.get("modifiedTime") or "")
            sz = "" if mime == sc.FOLDER_MIME else str(it.get("size") or 0)
            h.update(f"I|{it.get('id', '')}|{name}|{mime}|{sz}|{mod}\n".encode("utf-8"))
    return h.hexdigest()


def discover_targets(index: dict, branch: Optional[str] = None, max_depth: int = 99) -> List[dict]:
    """Trả về danh sách dict `{path, depth, tq_id, sheet_id, current_name, sheet_name, sibling_names}`."""
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
        if sc.is_in_tong_quan(path) and tq is None:
            continue
        if tq is None and (sc.is_quarantine_path(path) or not data.get("items")):
            continue
        sheet = None
        sibling_names = set()
        if tq:
            tq_path = f"{path}/{sc.TONG_QUAN_FOLDER}"
            for it in index.get(tq_path, {}).get("items", []):
                sibling_names.add(sc.nfc(it.get("name", "")))
                if it.get("mimeType") == SHEET_MIME and it.get("name", "").startswith(SHEET_PREFIX) and sheet is None:
                    sheet = it
        expected_name = sheet_name_for(path)
        current_name = sheet["name"] if sheet else ""
        targets.append({
            "path": path,
            "depth": depth,
            "tq_id": tq["id"] if tq else None,
            "sheet_id": sheet["id"] if sheet else None,
            "current_name": current_name,
            "sheet_name": expected_name,
            "sibling_names": sibling_names,
        })
    targets.sort(key=lambda t: (t["depth"], t["path"]))
    return targets


def _write_summary_sheet(
    wb: openpyxl.Workbook,
    target_path: str,
    n_folders: int,
    n_files: int,
    total_bytes: int,
    by_level: Dict[int, List[int]],
    by_cat: Dict[str, List[int]],
) -> None:
    ws = wb.create_sheet(title="Thống Kê Nhanh")
    header_fill = PatternFill("solid", fgColor="1F4E78")
    sub_fill = PatternFill("solid", fgColor="D9E1F2")
    header_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
    bold_font = Font(name="Arial", size=10, bold=True)
    reg_font = Font(name="Arial", size=10)
    thin = Side(border_style="thin", color="D9D9D9")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    # Khối KPI tổng quan
    ws.append(["CHỈ SỐ TỔNG QUAN NHÁNH", "GIÁ TRỊ"])
    for ci in (1, 2):
        c = ws.cell(row=1, column=ci)
        c.fill, c.font = header_fill, header_font
        c.alignment = Alignment(horizontal="center", vertical="center")

    kpis = [
        ("Đường dẫn nhánh", target_path),
        ("Tên bảng chuẩn V6", sheet_name_for(target_path)),
        ("Cập nhật lần cuối", sc.today_vn()),
        ("Tổng số thư mục con", n_folders),
        ("Tổng số tệp tin", n_files),
        ("Tổng dung lượng (đọc được)", sc.human_size(total_bytes)),
        ("Tổng dung lượng (byte)", total_bytes),
    ]
    for label, val in kpis:
        ws.append([label, val])
        rn = ws.max_row
        ws.cell(row=rn, column=1).font = bold_font
        ws.cell(row=rn, column=2).font = reg_font
        for ci in (1, 2):
            ws.cell(row=rn, column=ci).border = border
            ws.cell(row=rn, column=ci).fill = sub_fill if rn == 2 else PatternFill()

    ws.append([])

    # Bảng phân bố theo cấp độ
    ws.append(["Cấp Độ Tương Đối", "Số Thư Mục", "Số Tệp Tin", "Tổng Dung Lượng", "Dung Lượng (Byte)"])
    hdr_row = ws.max_row
    for ci in range(1, 6):
        c = ws.cell(row=hdr_row, column=ci)
        c.fill, c.font = header_fill, header_font
        c.alignment = Alignment(horizontal="center", vertical="center")

    for lvl in sorted(by_level):
        fd_cnt, fl_cnt, b_sum = by_level[lvl]
        ws.append([f"Cấp {lvl}", fd_cnt, fl_cnt, sc.human_size(b_sum), b_sum])
        rn = ws.max_row
        for ci in range(1, 6):
            c = ws.cell(row=rn, column=ci)
            c.font = reg_font
            c.border = border

    ws.append([])

    # Bảng phân bố theo nhóm định dạng
    ws.append(["Nhóm Định Dạng / Loại Mục", "Số Lượng", "Tỷ Lệ (%)", "Tổng Dung Lượng", "Dung Lượng (Byte)"])
    cat_hdr_row = ws.max_row
    for ci in range(1, 6):
        c = ws.cell(row=cat_hdr_row, column=ci)
        c.fill, c.font = header_fill, header_font
        c.alignment = Alignment(horizontal="center", vertical="center")

    tot_items = max(1, n_folders + n_files)
    for cat_name, (cnt, b_sum) in sorted(by_cat.items(), key=lambda kv: (-kv[1][1], -kv[1][0], kv[0])):
        pct = round(100.0 * cnt / tot_items, 2)
        ws.append([cat_name, cnt, pct, sc.human_size(b_sum), b_sum])
        rn = ws.max_row
        for ci in range(1, 6):
            c = ws.cell(row=rn, column=ci)
            c.font = reg_font
            c.border = border

    for i, w in enumerate([40, 32, 16, 20, 22], start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"


def build_xlsx(index: dict, target_path: str, out_xlsx: Path | str) -> int:
    rows, _, _ = build_xlsx_with_stats(index, target_path, out_xlsx)
    return rows


def build_xlsx_with_stats(index: dict, target_path: str, out_xlsx: Path | str) -> Tuple[int, int, int]:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Danh Mục Hệ Thống"
    header_fill = PatternFill("solid", fgColor="1F4E78")
    header_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
    folder_fill = PatternFill("solid", fgColor="D9E1F2")
    bold_font = Font(name="Arial", size=10, bold=True)
    reg_font = Font(name="Arial", size=10)
    link_font = Font(name="Arial", size=10, color="0563C1", underline="single")
    thin = Side(border_style="thin", color="D9D9D9")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    headers = [
        "STT", "Phân Loại", "Cấp Độ", "Tên Mục (Chuẩn V6)", "Đường Dẫn Thư Mục Cha",
        "ID Google Drive", "URL Truy Cập Trực Tiếp", "Dung Lượng", "Cập Nhật Lần Cuối",
    ]
    ws.append(headers)
    for ci in range(1, len(headers) + 1):
        c = ws.cell(row=1, column=ci)
        c.fill, c.font = header_fill, header_font
        c.alignment = Alignment(horizontal="center", vertical="center")

    prefix = target_path + "/"
    base_depth = index.get(target_path, {}).get("depth", target_path.count("/"))
    rows = []
    n_folders = n_files = total_bytes = 0
    by_level: Dict[int, List[int]] = defaultdict(lambda: [0, 0, 0])
    by_cat: Dict[str, List[int]] = defaultdict(lambda: [0, 0])

    for path in sorted(index):
        if path != target_path and not path.startswith(prefix):
            continue
        data = index[path]
        rel = data.get("depth", path.count("/")) - base_depth + 1
        for it in sorted(data.get("items", []), key=lambda x: (x.get("mimeType") != sc.FOLDER_MIME, x.get("name", ""))):
            mime = it.get("mimeType", "")
            is_f = mime == sc.FOLDER_MIME
            sz = 0 if is_f else int(it.get("size") or 0)
            if is_f:
                n_folders += 1
                by_level[rel][0] += 1
            else:
                n_files += 1
                total_bytes += sz
                by_level[rel][1] += 1
                by_level[rel][2] += sz
            cat_label = _classify_item(it)
            by_cat[cat_label][0] += 1
            by_cat[cat_label][1] += sz

            mod = (it.get("modifiedTime") or "")[:10]
            if mod and len(mod) == 10:
                y, m, d = mod.split("-")
                mod = f"{d}-{m}-{y}"
            rows.append((
                "Thư mục" if is_f else "Tệp tin",
                rel,
                it.get("name", ""),
                path,
                it["id"],
                sc.drive_url(it["id"], mime),
                "" if is_f else sc.human_size(sz),
                mod,
                is_f,
            ))

    for idx, r in enumerate(rows, start=1):
        ws.append([idx, *r[:8]])
        rn = idx + 1
        for ci in range(1, 10):
            c = ws.cell(row=rn, column=ci)
            c.border = border
            c.fill, c.font = (folder_fill, bold_font) if r[8] else (PatternFill(), reg_font)
        u = ws.cell(row=rn, column=7)
        u.hyperlink = r[5]
        u.font = link_font

    for i, w in enumerate([8, 12, 9, 58, 52, 36, 48, 12, 16], start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:I{len(rows) + 1}"

    _write_summary_sheet(wb, target_path, n_folders, n_files, total_bytes, by_level, by_cat)

    out_path = Path(out_xlsx)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    return len(rows), n_folders, n_files


# Giữ tương thích chữ ký hàm cũ từ `sheet_engine.py` v1
def build_xlsx_for_path(index_data: dict, target_path: str, out_xlsx: str) -> Tuple[int, int, int]:
    return build_xlsx_with_stats(index_data, target_path, out_xlsx)


def _find_prev_snapshot_index(current_index_path: Path) -> Optional[dict]:
    snaps = sorted(sc.snapshots_dir().glob("storage_index_*.json*"))
    if not snaps:
        return None
    # Nếu có >= 2 ảnh chụp, ưu tiên ảnh gần thứ 2 khi ảnh mới nhất vừa tạo trùng thời điểm hiện hành
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
) -> Tuple[List[dict], Dict[str, str]]:
    """Trả về `(targets_can_cap_nhat, signatures_by_path)`."""
    sigs: Dict[str, str] = {}
    todo: List[dict] = []
    synced_by_path = {v.get("path"): (k, v) for k, v in sync_state.items() if isinstance(v, dict) and v.get("path")}
    for t in targets:
        path = t["path"]
        sid = t["sheet_id"]
        sig = compute_subtree_signature(index, path, include_schema=True)
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
        # Chưa có bản ghi sync_state: đối chiếu với ảnh chụp trước nếu chỉ chạy --chi-thay-doi (không áp dụng khi --tiep-tuc)
        if only_changed and not resume and prev_index is not None and path in prev_index and t["depth"] > 1:
            sig_now_raw = compute_subtree_signature(index, path, include_schema=False)
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


def process_one(drive: sc.Drive, index: dict, t: dict, tmp_dir: str, create_missing: bool):
    safe_id = t["sheet_id"] or f"new_{abs(hash(t['path']))}"
    xlsx = Path(tmp_dir) / f"{safe_id}.xlsx"
    rows, _, _ = build_xlsx_with_stats(index, t["path"], xlsx)
    try:
        if t["sheet_id"]:
            drive.update(t["sheet_id"], xlsx, mime_type=SHEET_MIME)
            if t["path"] == sc.ROOT_NAME and sc.MASTER_SHEET_LIST_ID:
                drive.update(sc.MASTER_SHEET_LIST_ID, xlsx, mime_type=SHEET_MIME)
            return t, "cập nhật", rows, t["sheet_id"], ""
        if not create_missing:
            return t, "bỏ qua (chưa có bảng)", rows, "", ""
        tq_id = t["tq_id"] or drive.ensure_folder(sc.TONG_QUAN_FOLDER, index[t["path"]]["id"])
        new_id = drive.upload(xlsx, tq_id, mime_type=SHEET_MIME)
        if new_id:
            drive.rename(new_id, t["sheet_name"])
        return t, "tạo mới", rows, new_id, ""
    except sc.DriveError as e:
        return t, "lỗi", rows, t.get("sheet_id") or "", str(e)
    finally:
        try:
            xlsx.unlink()
        except OSError:
            pass


def refresh_key_sheets(max_depth: int = 2, workers: int = 8) -> None:
    """Hàm tương thích nhanh để làm mới các bảng trọng yếu từ cấp 0..max_depth."""
    index = sc.load_index()
    targets = discover_targets(index, branch=None, max_depth=max_depth)
    have = [t for t in targets if t["sheet_id"]]
    drive = sc.Drive()
    tmp_dir = tempfile.mkdtemp(prefix="danh_muc_key_")
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(process_one, drive, index, t, tmp_dir, False) for t in have]
        for f in cf.as_completed(futs):
            f.result()


def main() -> None:
    ap = argparse.ArgumentParser(description="Động cơ cập nhật bảng Danh Mục Hệ Thống (v2.0).")
    ap.add_argument("--nhanh", help="Giới hạn trong một nhánh")
    ap.add_argument("--do-sau", type=int, default=99, help="Độ sâu tối đa của thư mục đích (mặc định: 99 = toàn bộ)")
    ap.add_argument("--chi-thay-doi", action="store_true", help="Chỉ cập nhật bảng có nhánh con biến động")
    ap.add_argument("--tiep-tuc", action="store_true", help="Bỏ qua các bảng đã khớp chữ ký trong sheets_sync_state.json (tiếp tục lô dở)")
    ap.add_argument("--toan-bo", action="store_true", help="Ép cập nhật lại toàn bộ bảng bất kể đã đồng bộ")
    ap.add_argument("--tao-moi", action="store_true", help="Tạo bảng cho thư mục chưa có (kèm [00] TỔNG QUAN nếu thiếu)")
    ap.add_argument("--sua-ten-bang", action="store_true", help="Chuẩn hóa tên bảng lệch quy ước (dính .pdf, _, sai viết tắt)")
    ap.add_argument("--thuc-thi", action="store_true", help="Ghi lên Drive (mặc định chạy thử)")
    ap.add_argument("--dong-y", action="store_true", help="Không hỏi xác nhận")
    ap.add_argument("--luong", type=int, default=8, help="Số luồng song song (mặc định 8)")
    ap.add_argument("--xuat-cuc-bo", help="Chỉ xuất tệp .xlsx của một đường dẫn ra máy (không ghi Drive)")
    args = ap.parse_args()

    index = sc.load_index()
    if args.xuat_cuc_bo:
        p = sc.normalize_branch(args.xuat_cuc_bo)
        out = sc.reports_dir() / f"{sheet_name_for(p)}.xlsx"
        n, nf, nfl = build_xlsx_with_stats(index, p, out)
        sc.log(f"Đã xuất {n} dòng ({nf} thư mục, {nfl} tệp + tab Thống Kê Nhanh) → {out}")
        return

    branch = sc.normalize_branch(args.nhanh)
    if branch == sc.ROOT_NAME:
        branch = None
    targets = discover_targets(index, branch, args.do_sau)
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
    )
    title_fixes = collect_title_fixes(have) if args.sua_ten_bang else []

    sc.log(
        f"Thư mục đích: {len(targets)} | đã có bảng: {len(have)} | chưa có bảng: {len(missing)} | "
        f"cần cập nhật nội dung: {len(to_update)} | cần chuẩn hóa tên bảng: {len(title_fixes)}"
    )
    for t in missing[:10]:
        sc.log(f"  - thiếu: {t['path']}  →  {t['sheet_name']}")
    for fx in title_fixes[:15]:
        sc.log(f"  - đổi tên bảng: {fx['old_name']}  →  {fx['new_name']}")

    if not args.thuc_thi:
        sc.log("(Chạy thử — thêm --thuc-thi để cập nhật Drive; --chi-thay-doi / --tao-moi / --sua-ten-bang.)")
        return

    total_ops = len(title_fixes) + len(to_update)
    if total_ops == 0:
        sc.log("Mọi bảng Danh Mục Hệ Thống đều đã đồng bộ mới nhất.")
        return
    if not sc.confirm(f"Thực thi {len(title_fixes)} lệnh đổi tên bảng + {len(to_update)} lệnh cập nhật/tạo bảng?", args.dong_y):
        return

    drive = sc.Drive()

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
        sc.log(f"\nĐang cập nhật/tạo {len(to_update)} bảng (gồm tab Danh Mục Hệ Thống + Thống Kê Nhanh)...")
        tmp_dir = tempfile.mkdtemp(prefix="danh_muc_")
        stats: Dict[str, int] = {}
        with cf.ThreadPoolExecutor(max_workers=args.luong) as pool:
            futs = [pool.submit(process_one, drive, index, t, tmp_dir, args.tao_moi) for t in to_update]
            for n, f in enumerate(cf.as_completed(futs), 1):
                t, status, rows, sid, err = f.result()
                stats[status] = stats.get(status, 0) + 1
                if status in ("cập nhật", "tạo mới") and sid:
                    sync_state[sid] = {
                        "path": t["path"],
                        "sig": sigs[t["path"]],
                        "sheet_name": t["sheet_name"],
                        "rows": rows,
                        "updated_iso": sc.now_utc_iso(),
                    }
                if err:
                    sc.log(f"  ! {t['path']}: {err[:200]}")
                if n % 25 == 0 or n == len(futs):
                    sc.write_json(state_p, sync_state, indent=None)
                    sc.log(f"  → {n}/{len(futs)} | " + ", ".join(f"{k}: {v}" for k, v in stats.items()))
        sc.write_json(state_p, sync_state, indent=None)

    # Cập nhật bản đồ uploaded_sheets_log.json
    sheets_map = {}
    for t in targets:
        sid = t["sheet_id"] or next((k for k, v in sync_state.items() if v.get("path") == t["path"]), None)
        if sid:
            sheets_map[t["path"]] = {
                "path": t["path"],
                "depth": t["depth"],
                "tq_id": t["tq_id"],
                "sheet_name": t["sheet_name"] if args.sua_ten_bang or not t["current_name"] else t["current_name"],
                "sheet_id": sid,
            }
    sc.write_json(sc.sheets_log_path(), sheets_map, indent=1)
    sc.log(f"Hoàn tất. Đã lưu trạng thái đồng bộ → {state_p}")


if __name__ == "__main__":
    main()
