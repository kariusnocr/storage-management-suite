#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BÁO CÁO THỐNG KÊ, SỨC KHỎE KHO & NHẬT KÍ BIẾN ĐỘNG — [A] STORAGE (v2.0)
========================================================================
1. Chỉ số Sức khỏe Kho (Repository Health Score 0–100):
   - Tỷ lệ đạt chuẩn V6, số lỗi `TRUNG_TEN`, `TongQuan.md` trùng,
   - Dung lượng trùng lặp có thể thu hồi, shortcut (qua `shortcut_cache.json`), thư mục rỗng,
   - Xu hướng biến thiên qua nhiều ảnh chụp trong `snapshots/`.
2. Thống kê hiện trạng kho: nhánh cấp 1/2, nhóm định dạng, top tệp/thư mục nặng, cập nhật gần đây.
3. Nhật kí biến động: so sánh 2 ảnh chụp → xuất cả `.md` tóm tắt VÀ **toàn bộ `.csv` không giới hạn 300 dòng**.
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from karius_academic_system import core as sc

CATEGORIES = [
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

_EXCLUDE_DEDUP = tuple(sc.CONFIG.get("dedup", {}).get(
    "exclude_markers", ("[A] STORAGE/[99] KIỂM TRA", "/[00] TỔNG QUAN", ".obsidian", "MÃ NGUỒN PYTHON", "DỰ ÁN SỐ HÓA")
))
_COPY_RE = re.compile(r"(,?\s*(?<!phien )(?:ban)\s*\d{1,3}$)|(\(\d{1,3}\)$)|(^copy of\s+)|(\s+copy$)", re.I)


def category(it: dict) -> str:
    _, ext = sc.split_ext(it["name"], it["mimeType"])
    ext = ext.lower()
    for name, fn in CATEGORIES:
        if fn(it["mimeType"], ext):
            return name
    return "Khác"


def short(p: str) -> str:
    return p.replace(sc.ROOT_NAME + "/", "") if p != sc.ROOT_NAME else p


def branch_at(path: str, level: int) -> Optional[str]:
    parts = path.split("/")
    return "/".join(parts[1:level + 1]) if len(parts) > level else None


def compute_health_metrics(index: dict) -> dict:
    """Tính nhanh các chỉ số Sức khỏe Kho (0–100) trên phần kho hoạt động (loại trừ vùng cách ly `[99] KIỂM TRA`)."""
    tot_items = 0
    quarantined_items = 0
    err_ids: Set[str] = set()
    warn_ids: Set[str] = set()
    trung_ten_items = 0
    tongquan_dup_pairs = 0
    shortcut_total = 0
    total_file_bytes = 0

    by_size_key = defaultdict(list)

    for path, data in index.items():
        items = data.get("items", [])
        if sc.is_quarantine_path(path):
            quarantined_items += sum(1 for it in items if it.get("mimeType") != sc.FOLDER_MIME)
            continue
        in_obs = ".obsidian" in path
        names = Counter(sc.nfc(it.get("name", "")) for it in items)
        if not in_obs:
            for _, cnt in names.items():
                if cnt > 1:
                    trung_ten_items += cnt
        if path.endswith("/" + sc.TONG_QUAN_FOLDER):
            tqs = [it for it in items if it.get("mimeType") != sc.FOLDER_MIME and it.get("name") == "TongQuan.md"]
            if len(tqs) > 1:
                tongquan_dup_pairs += len(tqs) - 1

        for it in items:
            tot_items += 1
            mime = it.get("mimeType", "")
            is_f = mime == sc.FOLDER_MIME
            if mime == sc.SHORTCUT_MIME:
                shortcut_total += 1
            elif not is_f:
                sz = int(it.get("size") or 0)
                total_file_bytes += sz
                if sz > 0 and mime not in sc.GOOGLE_NATIVE_MIMES and not any(m in path for m in _EXCLUDE_DEDUP):
                    base, ext = sc.split_ext(it["name"], mime)
                    b = sc.strip_accents(sc.nfc(base)).lower().strip()
                    b = _COPY_RE.sub("", b).strip(" ,-_")
                    k = re.sub(r"[^a-z0-9]+", "", b)
                    if k:
                        by_size_key[(sz, k, ext.lower())].append(sz)

            issues = sc.check_folder_name(it["name"], path) if is_f else sc.check_file_name(it["name"], mime, path)
            for sev, _, _ in issues:
                if sev == "LỖI":
                    err_ids.add(it["id"])
                elif sev == "CẢNH BÁO":
                    warn_ids.add(it["id"])

    dup_groups = 0
    dup_extra_files = 0
    dup_waste_bytes = 0
    for _, grp in by_size_key.items():
        if len(grp) > 1:
            dup_groups += 1
            dup_extra_files += len(grp) - 1
            dup_waste_bytes += grp[0] * (len(grp) - 1)

    # Thư mục rỗng (bottom-up)
    empty_set: Set[str] = set()
    for path in sorted(index.keys(), key=lambda p: (-p.count("/"), p)):
        if path == sc.ROOT_NAME or any(m in (path + "/") for m in _EXCLUDE_DEDUP):
            continue
        direct = [it for it in index[path].get("items", []) if it.get("name") != sc.TONG_QUAN_FOLDER]
        if any(it.get("mimeType") != sc.FOLDER_MIME for it in direct):
            continue
        subs = [it for it in direct if it.get("mimeType") == sc.FOLDER_MIME]
        if not subs or all(f"{path}/{sf['name']}" in empty_set for sf in subs):
            empty_set.add(path)

    sc_cache = sc.read_json(sc.shortcut_cache_path(), {}) or {}
    broken_sc = sum(1 for v in sc_cache.values() if v.get("targetStatus") in ("broken", "trashed"))

    v6_rate = 1.0 - (len(err_ids) / max(tot_items, 1))
    dup_name_penalty = min(1.0, (trung_ten_items / max(tot_items, 1)) * 8.0)
    waste_penalty = min(1.0, (dup_waste_bytes / max(total_file_bytes, 1)) * 15.0)
    clutter_ratio = (len(empty_set) + broken_sc) / max(len(index), 1)
    clutter_penalty = min(1.0, clutter_ratio * 5.0)

    score = round(45.0 * v6_rate + 25.0 * (1.0 - dup_name_penalty) + 15.0 * (1.0 - waste_penalty) + 15.0 * (1.0 - clutter_penalty), 1)
    return {
        "score": score,
        "total_items": tot_items,
        "quarantined_items": quarantined_items,
        "total_folders": len(index),
        "total_bytes": total_file_bytes,
        "error_items": len(err_ids),
        "warning_items": len(warn_ids),
        "v6_pct": round(100.0 * v6_rate, 2),
        "trung_ten_items": trung_ten_items,
        "tongquan_dup_pairs": tongquan_dup_pairs,
        "dup_groups": dup_groups,
        "dup_extra_files": dup_extra_files,
        "dup_waste_bytes": dup_waste_bytes,
        "shortcuts": shortcut_total,
        "cached_broken_shortcuts": broken_sc,
        "empty_folders": len(empty_set),
    }


def _snapshot_trend(limit: int = 5) -> List[Tuple[str, str, str, str, str, str]]:
    snaps = sorted(sc.snapshots_dir().glob("storage_index_*.json*"))[-limit:]
    rows = []
    for sp in snaps:
        try:
            meta, idx = load_snapshot(sp)
            hm = compute_health_metrics(idx)
            ts_label = meta.get("scanned_iso") or meta.get("scanned_at") or sp.name
            rows.append((
                str(ts_label),
                sc.fmt_int(hm["total_folders"]),
                sc.fmt_int(hm["total_items"] - hm["total_folders"]),
                sc.human_size(hm["total_bytes"]),
                f"{hm['v6_pct']:.2f}%",
                f"{hm['score']:.1f}/100",
            ))
        except Exception:
            continue
    return rows


def stats_report(index: dict, recent_days: int, top_n: int) -> str:
    lvl1 = defaultdict(lambda: [0, 0, 0])
    lvl2 = defaultdict(lambda: [0, 0, 0])
    cats = defaultdict(lambda: [0, 0])
    files = []
    folder_size = defaultdict(int)
    recent = []
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=recent_days)).strftime("%Y-%m-%dT%H:%M:%S")
    tot_f = tot_d = tot_b = 0

    for path, it in sc.iter_items(index):
        full = f"{path}/{it['name']}"
        is_dir = it["mimeType"] == sc.FOLDER_MIME
        size = 0 if is_dir else (it.get("size") or 0)
        c = category(it)
        cats[c][0] += 1
        cats[c][1] += size
        for lvl, bucket in ((1, lvl1), (2, lvl2)):
            b = branch_at(full if is_dir else path, lvl)
            if b is None:
                continue
            if is_dir and full.count("/") == lvl:
                continue  # chính thư mục nhánh, không đếm vào bản thân nó
            bucket[b][0 if is_dir else 1] += 1
            bucket[b][2] += size
        if is_dir:
            tot_d += 1
            continue
        tot_f += 1
        tot_b += size
        files.append((size, path, it))
        p = path
        while True:
            folder_size[p] += size
            if "/" not in p:
                break
            p = p.rsplit("/", 1)[0]
        if it.get("modifiedTime", "") >= cutoff and not sc.is_in_tong_quan(path):
            recent.append((it["modifiedTime"], path, it))

    files.sort(key=lambda x: -x[0])
    recent.sort(key=lambda x: x[0], reverse=True)
    heavy = sorted(((s, p) for p, s in folder_size.items() if p.count("/") >= 2), reverse=True)

    hm = compute_health_metrics(index)
    trend = _snapshot_trend(limit=5)
    grade = "Xuất sắc" if hm["score"] >= 90 else ("Tốt" if hm["score"] >= 75 else "Cần tối ưu")

    L = [
        "# BÁO CÁO THỐNG KÊ VÀ SỨC KHỎE KHO — STORAGE",
        "",
        f"- **Thời gian lập:** {sc.today_vn()}",
        f"- **Tổng số thư mục:** `{sc.fmt_int(tot_d)}`",
        f"- **Tổng số tệp:** `{sc.fmt_int(tot_f)}`",
        f"- **Tổng dung lượng (tệp không phải Google gốc):** `{sc.human_size(tot_b)}`",
        f"- **Điểm Sức khỏe Kho (Health Score):** **`{hm['score']:.1f}/100`** (*{grade}*)",
        "",
        "## 0. Chỉ số Sức khỏe Kho & Xu hướng",
        "",
        sc.md_table(
            ["Chỉ số", "Giá trị", "Ghi chú"],
            [
                ("Tỷ lệ đạt chuẩn tên V6", f"**{hm['v6_pct']:.2f}%**",
                 f"{sc.fmt_int(hm['error_items'])} LỖI / {sc.fmt_int(hm['warning_items'])} CẢNH BÁO"),
                ("Mục `TRUNG_TEN` (cùng thư mục)", f"`{sc.fmt_int(hm['trung_ten_items'])}`",
                 f"Gồm `{sc.fmt_int(hm['tongquan_dup_pairs'])}` cặp `TongQuan.md` trùng"),
                ("Trùng lặp chắc chắn có thể dọn", f"`{sc.fmt_int(hm['dup_groups'])}` nhóm (`{sc.fmt_int(hm['dup_extra_files'])}` bản thừa)",
                 f"≈ **{sc.human_size(hm['dup_waste_bytes'])}** lãng phí"),
                ("Shortcut trong kho", f"`{sc.fmt_int(hm['shortcuts'])}`",
                 f"{sc.fmt_int(hm['cached_broken_shortcuts'])} hỏng theo cache"),
                ("Thư mục rỗng (kể cả lồng nhau)", f"`{sc.fmt_int(hm['empty_folders'])}`", "Quét bottom-up"),
                (f"Mục đang cách ly tại `{sc.QUARANTINE_FOLDER}`", f"`{sc.fmt_int(hm['quarantined_items'])}`", "Loại trừ khỏi lỗi kho hoạt động"),
            ],
            ["l", "r", "l"],
        ),
        "",
    ]
    if trend:
        L += [
            "### Xu hướng qua các ảnh chụp gần đây",
            "",
            sc.md_table(["Mốc quét (UTC)", "Thư mục", "Tệp", "Dung lượng", "Chuẩn V6", "Health Score"], trend,
                        ["l", "r", "r", "r", "r", "r"]),
            "",
        ]

    L += [
        "## 1. Theo nhánh cấp 1",
        "",
        sc.md_table(["Nhánh", "Thư mục", "Tệp", "Dung lượng"],
                    [(f"`{k}`", sc.fmt_int(v[0]), sc.fmt_int(v[1]), sc.human_size(v[2])) for k, v in sorted(lvl1.items())],
                    ["l", "r", "r", "r"]),
        "",
        "## 2. Theo nhánh cấp 2",
        "",
        sc.md_table(["Nhánh", "Thư mục", "Tệp", "Dung lượng"],
                    [(f"`{k}`", sc.fmt_int(v[0]), sc.fmt_int(v[1]), sc.human_size(v[2])) for k, v in sorted(lvl2.items())],
                    ["l", "r", "r", "r"]),
        "",
        "## 3. Theo nhóm định dạng",
        "",
        sc.md_table(["Nhóm", "Số lượng", "Dung lượng"],
                    [(k, sc.fmt_int(v[0]), sc.human_size(v[1])) for k, v in sorted(cats.items(), key=lambda x: -x[1][1])],
                    ["l", "r", "r"]),
        "",
        f"## 4. Top {top_n} tệp lớn nhất",
        "",
        sc.md_table(["Dung lượng", "Tệp", "Thư mục"],
                    [(sc.human_size(s), f"[{it['name']}]({sc.drive_url(it['id'], it['mimeType'])})", f"`{short(p)}`")
                     for s, p, it in files[:top_n]], ["r", "l", "l"]),
        "",
        f"## 5. Top {top_n} thư mục nặng nhất (cộng dồn)",
        "",
        sc.md_table(["Dung lượng", "Thư mục"], [(sc.human_size(s), f"`{short(p)}`") for s, p in heavy[:top_n]], ["r", "l"]),
        "",
        f"## 6. Tệp cập nhật trong {recent_days} ngày gần đây ({sc.fmt_int(len(recent))} tệp, hiển thị tối đa 100)",
        "",
        sc.md_table(["Thời điểm (UTC)", "Tệp", "Thư mục"],
                    [(t[:16].replace("T", " "), f"`{it['name']}`", f"`{short(p)}`") for t, p, it in recent[:100]])
        if recent else "_Không có._",
    ]
    return "\n".join(L)


# ---------------------------------------------------------------------------
# NHẬT KÍ BIẾN ĐỘNG
# ---------------------------------------------------------------------------

def load_snapshot(path: Path | str) -> Tuple[dict, dict]:
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and "folders" in data:
        return data.get("meta", {}), data["folders"]
    return {}, data


def flatten(index: dict) -> Dict[str, Tuple[str, dict]]:
    out = {}
    for path, it in sc.iter_items(index):
        out[it["id"]] = (path, it)
    return out


def diff_report(a_path: Path | str, b_path: Path | str) -> Tuple[str, Tuple[int, int, int, int], List[Tuple]]:
    ma, ia = load_snapshot(a_path)
    mb, ib = load_snapshot(b_path)
    fa, fb = flatten(ia), flatten(ib)
    added = sorted([fb[k] for k in fb.keys() - fa.keys()], key=lambda x: (x[0], x[1]["name"]))
    removed = sorted([fa[k] for k in fa.keys() - fb.keys()], key=lambda x: (x[0], x[1]["name"]))
    renamed, moved = [], []
    for k in fa.keys() & fb.keys():
        (pa, ita), (pb, itb) = fa[k], fb[k]
        if ita["name"] != itb["name"]:
            renamed.append((pb, ita["name"], itb["name"], itb))
        # bỏ qua "di chuyển" phát sinh do thư mục cha đổi tên: so sánh ID thư mục cha
        if ia.get(pa, {}).get("id") != ib.get(pb, {}).get("id"):
            moved.append((pa, pb, itb))
    renamed.sort(key=lambda x: (x[0], x[2]))
    moved.sort(key=lambda x: (x[1], x[2]["name"]))

    size_delta = sum((it.get("size") or 0) for _, it in added) - sum((it.get("size") or 0) for _, it in removed)

    csv_rows: List[Tuple] = []
    for p, it in added:
        kind = "Thư mục" if it["mimeType"] == sc.FOLDER_MIME else "Tệp tin"
        csv_rows.append(("THÊM MỚI", kind, "", it["name"], "", p, it["id"], it.get("size") or 0))
    for p, it in removed:
        kind = "Thư mục" if it["mimeType"] == sc.FOLDER_MIME else "Tệp tin"
        csv_rows.append(("MẤT / CHUYỂN RA NGOÀI", kind, it["name"], "", p, "", it["id"], it.get("size") or 0))
    for p, old_n, new_n, it in renamed:
        kind = "Thư mục" if it["mimeType"] == sc.FOLDER_MIME else "Tệp tin"
        csv_rows.append(("ĐỔI TÊN", kind, old_n, new_n, p, p, it["id"], it.get("size") or 0))
    for pa, pb, it in moved:
        kind = "Thư mục" if it["mimeType"] == sc.FOLDER_MIME else "Tệp tin"
        csv_rows.append(("DI CHUYỂN", kind, it["name"], it["name"], pa, pb, it["id"], it.get("size") or 0))

    def rows_simple(lst, limit=300):
        return [(("📁 " if it["mimeType"] == sc.FOLDER_MIME else "") + f"`{it['name']}`", f"`{short(p)}`")
                for p, it in lst[:limit]]

    L = [
        "# NHẬT KÍ BIẾN ĐỘNG KHO — STORAGE",
        "",
        f"- **Lập ngày:** {sc.today_vn()}",
        f"- **Ảnh chụp trước:** `{Path(a_path).name}`" + (f" (quét lúc {ma.get('scanned_at')})" if ma else ""),
        f"- **Ảnh chụp sau:** `{Path(b_path).name}`" + (f" (quét lúc {mb.get('scanned_at')})" if mb else ""),
        f"- **Thêm mới:** `{sc.fmt_int(len(added))}` | **Mất/chuyển ra ngoài:** `{sc.fmt_int(len(removed))}` | "
        f"**Đổi tên:** `{sc.fmt_int(len(renamed))}` | **Di chuyển:** `{sc.fmt_int(len(moved))}`",
        f"- **Chênh lệch dung lượng:** `{'+' if size_delta >= 0 else '-'}{sc.human_size(abs(size_delta))}`",
        f"- **Tổng số dòng chi tiết (tệp CSV đầy đủ):** `{sc.fmt_int(len(csv_rows))}`",
        "",
        "## 1. Mục thêm mới (hiển thị tối đa 300)",
        "",
        sc.md_table(["Tên", "Thư mục"], rows_simple(added)) if added else "_Không có._",
        "",
        "## 2. Mục bị xóa / chuyển ra ngoài kho (hiển thị tối đa 300)",
        "",
        sc.md_table(["Tên", "Thư mục cũ"], rows_simple(removed)) if removed else "_Không có._",
        "",
        "## 3. Đổi tên (hiển thị tối đa 300)",
        "",
        sc.md_table(["Tên cũ", "Tên mới", "Thư mục"],
                    [(f"`{o}`", f"`{n}`", f"`{short(p)}`") for p, o, n, _ in renamed[:300]])
        if renamed else "_Không có._",
        "",
        "## 4. Di chuyển (hiển thị tối đa 300)",
        "",
        sc.md_table(["Tên", "Từ", "Đến"],
                    [(f"`{it['name']}`", f"`{short(a)}`", f"`{short(b)}`") for a, b, it in moved[:300]])
        if moved else "_Không có._",
    ]
    return "\n".join(L), (len(added), len(removed), len(renamed), len(moved)), csv_rows


def main() -> None:
    ap = argparse.ArgumentParser(description="Báo cáo thống kê, sức khỏe kho & nhật kí biến động (v2.0).")
    ap.add_argument("--gan-day", type=int, default=7, help="Số ngày liệt kê tệp mới cập nhật (mặc định 7)")
    ap.add_argument("--top", type=int, default=30, help="Số dòng cho bảng top (mặc định 30)")
    ap.add_argument("--so-sanh", nargs=2, metavar=("TRUOC", "SAU"), help="Hai tệp ảnh chụp cần so sánh")
    ap.add_argument("--bo-qua-bien-dong", action="store_true", help="Không lập nhật kí biến động")
    ap.add_argument("--tai-len", action="store_true", help="Đăng báo cáo & CSV vào [00] TỔNG QUAN/[02] NHẬT KÍ")
    args = ap.parse_args()

    outputs: List[Path] = []
    index = sc.load_index()
    stats_md = sc.reports_dir() / f"Báo Cáo Thống Kê Kho - Storage, {sc.today_vn()}.md"
    stats_md.write_text(stats_report(index, args.gan_day, args.top), encoding="utf-8")
    outputs.append(stats_md)
    sc.log(f"Báo cáo thống kê: {stats_md}")

    if not args.bo_qua_bien_dong:
        if args.so_sanh:
            a, b = args.so_sanh
        else:
            snaps = sorted(sc.snapshots_dir().glob("storage_index_*.json*"))
            a, b = (snaps[-2], snaps[-1]) if len(snaps) >= 2 else (None, None)
        if a and b:
            md, counts, csv_rows = diff_report(a, b)
            diff_md = sc.reports_dir() / f"Nhật Kí Biến Động Kho - Storage, {sc.today_vn()}.md"
            diff_csv = sc.reports_dir() / f"Nhật Kí Biến Động Kho - Storage, {sc.today_vn()}.csv"
            diff_md.write_text(md, encoding="utf-8")
            sc.write_csv(
                diff_csv,
                ["Loại biến động", "Phân loại", "Tên cũ", "Tên mới", "Thư mục cũ", "Thư mục mới", "ID", "Dung lượng (B)"],
                csv_rows,
            )
            outputs.extend([diff_md, diff_csv])
            sc.log(
                f"Nhật kí biến động: {diff_md} + {diff_csv.name} "
                f"(thêm {counts[0]}, mất {counts[1]}, đổi tên {counts[2]}, di chuyển {counts[3]})"
            )
        else:
            sc.log("Chưa đủ 2 ảnh chụp chỉ mục để lập nhật kí biến động.")

    if args.tai_len:
        drive = sc.create_drive()
        for p in outputs:
            fid = sc.publish_file(drive, p, sc.nhat_ki_id())
            sc.log(f"Đã đăng: {p.name} → {sc.drive_url(fid)}")


if __name__ == "__main__":
    main()
