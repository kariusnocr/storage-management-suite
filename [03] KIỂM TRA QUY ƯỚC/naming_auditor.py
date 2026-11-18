#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KIỂM TRA QUY ƯỚC ĐẶT TÊN — [A] STORAGE (CHUẨN V6, v2.0)
======================================================
Rà soát toàn bộ chỉ mục theo `Tổng Quan Hệ Thống - Quy Ước Đặt Tên.md`:

Tên thư mục  : `[STT] TÊN IN HOA CÓ DẤU`
Tên tệp      : `Tên Viết Hoa Đầu Mỗi Chữ Có Dấu - Thông Tin Bổ Sung.[đuôi]`
Mã nguồn     : `[Tên Viết Thường Tiếng Anh Ngắn Gọn].[đuôi]` (snake_case trong vùng ngoại lệ kỹ thuật)
Cấu trúc     : trùng tên, trùng STT, nhảy STT, thiếu `[00] TỔNG QUAN`, thiếu `Danh Mục Hệ Thống - …`.

Đầu ra (trong `<STORAGE_DATA_DIR>/reports/`):
- `Báo Cáo Kiểm Tra Quy Ước - Storage, DD-MM-YYYY.md`
- `Báo Cáo Kiểm Tra Quy Ước - Storage, DD-MM-YYYY.csv`
"""

import argparse
import concurrent.futures as cf
import os
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path


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

RE_STT = re.compile(r"^\[(\d{2,3})\]")


def _skip_quarantine(path: str, branch: str | None) -> bool:
    return sc.is_quarantine_path(path) and not (branch and sc.is_quarantine_path(branch))


def audit(index, branch=None, check_structure=True):
    issues = []  # (mức độ, mã, đường dẫn cha, tên, id, loại, mô tả, đề xuất)

    for path, data in index.items():
        if branch and not (path == branch or path.startswith(branch.rstrip("/") + "/")):
            continue
        if _skip_quarantine(path, branch):
            continue
        items = data.get("items", [])
        in_obsidian = ".obsidian" in path

        # --- tên từng mục ---
        for it in items:
            is_folder = it["mimeType"] == sc.FOLDER_MIME
            name = it["name"]
            if is_folder:
                found = sc.check_folder_name(name, path)
            else:
                found = sc.check_file_name(name, it["mimeType"], path)
            if not found:
                continue
            suggestion = sc.safe_fix_name(name, is_folder, it["mimeType"])
            for sev, code, desc in found:
                issues.append((sev, code, path, name, it["id"], "Thư mục" if is_folder else "Tệp tin", desc,
                               suggestion if suggestion != name else ""))

        if not check_structure or in_obsidian:
            continue

        # --- trùng tên trong cùng thư mục ---
        names = Counter(sc.nfc(it["name"]) for it in items)
        for nm, cnt in names.items():
            if cnt > 1:
                for it in items:
                    if sc.nfc(it["name"]) == nm:
                        issues.append(("LỖI", "TRUNG_TEN", path, it["name"], it["id"],
                                       "Thư mục" if it["mimeType"] == sc.FOLDER_MIME else "Tệp tin",
                                       f"{cnt} mục cùng tên trong một thư mục", ""))

        # --- STT thư mục con ---
        subfolders = [it for it in items if it["mimeType"] == sc.FOLDER_MIME]
        stts = defaultdict(list)
        for it in subfolders:
            m = RE_STT.match(it["name"])
            if m:
                stts[int(m.group(1))].append(it)
        for stt, group in stts.items():
            if len(group) > 1 and stt != 0:
                for it in group:
                    issues.append(("CẢNH BÁO", "TRUNG_STT", path, it["name"], it["id"], "Thư mục",
                                   f"STT [{stt:02d}] bị dùng {len(group)} lần", ""))
        nums = sorted(n for n in stts if 0 < n < 90)
        if nums and not sc.is_in_danh_sach_tree(path):
            missing = sorted(set(range(1, nums[-1] + 1)) - set(nums))
            if missing:
                issues.append(("GỢI Ý", "NHAY_STT", path, "", data.get("id", ""), "Thư mục",
                               "Thiếu STT: " + ", ".join(f"[{n:02d}]" for n in missing[:15]), ""))

        # --- [00] TỔNG QUAN ---
        is_tq = path.split("/")[-1] == sc.TONG_QUAN_FOLDER
        if sc.is_in_tong_quan(path) and not is_tq:
            continue
        if is_tq:
            parent_path = path.rsplit("/", 1)[0] if "/" in path else sc.ROOT_NAME
            if sc.is_in_tong_quan(parent_path):
                continue
            expected_sheet = sc.normalize_sheet_title(parent_path)
            cat_path = sc.catalog_folder_for_path(parent_path)
            cat_items = index.get(cat_path, {}).get("items", []) if cat_path != path else []
            has_sheet = any(
                it.get("mimeType") == sc.SHEET_MIME and it["name"].startswith("Danh Mục Hệ Thống - ")
                for it in [*items, *cat_items]
            )
            if not has_sheet:
                issues.append(("CẢNH BÁO", "THIEU_DANH_MUC", path, "", data.get("id", ""), "Thư mục",
                               f"Thiếu bảng `{expected_sheet}`", ""))
            continue
        if items and path != sc.ROOT_NAME:
            has_tq = any(it["name"] == sc.TONG_QUAN_FOLDER and it["mimeType"] == sc.FOLDER_MIME for it in items)
            if not has_tq:
                issues.append(("GỢI Ý", "THIEU_TONG_QUAN", path, "", data.get("id", ""), "Thư mục",
                               "Thư mục chưa có `[00] TỔNG QUAN`", ""))
    return issues


def build_report(issues, index, branch, min_sev):
    sev_rank = sc.SEVERITY_ORDER
    shown = [i for i in issues if sev_rank[i[0]] <= sev_rank[min_sev]]
    total_items = sum(
        len(d.get("items", [])) for p, d in index.items()
        if (not branch or p == branch or p.startswith(branch + "/")) and not _skip_quarantine(p, branch)
    )
    bad_ids = {i[4] for i in shown if i[0] == "LỖI"}
    by_code = Counter((i[0], i[1]) for i in shown)
    by_root = Counter()
    for i in shown:
        parts = i[2].split("/")
        by_root[parts[1] if len(parts) > 1 else "(gốc)"] += 1

    lines = [f"# BÁO CÁO KIỂM TRA QUY ƯỚC ĐẶT TÊN — CHUẨN V6", "",
             f"- **Thời gian:** {sc.today_vn()}",
             f"- **Phạm vi:** `{branch or sc.ROOT_NAME}`" + ("" if branch else f" *(không tính vùng cách ly `{sc.QUARANTINE_FOLDER}`)*"),
             f"- **Tổng số mục đã rà soát:** `{sc.fmt_int(total_items)}`",
             f"- **Số mục có LỖI:** `{sc.fmt_int(len(bad_ids))}` "
             f"(tỷ lệ đạt chuẩn ≈ **{100 - 100 * len(bad_ids) / max(total_items, 1):.2f}%**)",
             f"- **Tổng số phát hiện (từ mức {min_sev} trở lên):** `{sc.fmt_int(len(shown))}`", "",
             "## 1. Thống kê theo mã lỗi", "",
             sc.md_table(["Mức độ", "Mã", "Số lượng"],
                         [(s, f"`{c}`", sc.fmt_int(n)) for (s, c), n in
                          sorted(by_code.items(), key=lambda x: (sev_rank[x[0][0]], -x[1]))],
                         ["l", "l", "r"]), "",
             "## 2. Thống kê theo nhánh gốc", "",
             sc.md_table(["Nhánh", "Số phát hiện"], [(f"`{k}`", sc.fmt_int(v)) for k, v in by_root.most_common()],
                         ["l", "r"]), "",
             "## 3. Ví dụ tiêu biểu (tối đa 15 mục mỗi mã)", ""]
    per_code = defaultdict(list)
    for i in shown:
        if len(per_code[i[1]]) < 15:
            per_code[i[1]].append(i)
    for (sev, code), _ in sorted(by_code.items(), key=lambda x: (sev_rank[x[0][0]], -x[1])):
        lines += [f"### `{code}` ({sev})", ""]
        lines.append(sc.md_table(["Tên hiện tại", "Thư mục cha", "Mô tả", "Đề xuất an toàn"],
                                 [(f"`{i[3]}`" if i[3] else "—", f"`{i[2].replace(sc.ROOT_NAME + '/', '')}`",
                                   i[6], f"`{i[7]}`" if i[7] else "—") for i in per_code[code]]))
        lines.append("")
    lines += ["---", "",
              "> Lỗi cần khôi phục dấu tiếng Việt / tách thông tin bổ sung dùng `[04] CHUẨN HÓA TÊN/storage_toolkit.py`. "
              "Lỗi cơ học sửa an toàn bằng `--sua-an-toan --thuc-thi`."]
    return "\n".join(lines), shown


def build_fix_plan(index, branch):
    plan = []
    for path, data in index.items():
        if branch and not (path == branch or path.startswith(branch.rstrip("/") + "/")):
            continue
        if _skip_quarantine(path, branch):
            continue
        items = data.get("items", [])
        taken = {sc.nfc(it["name"]) for it in items}
        for it in items:
            is_folder = it["mimeType"] == sc.FOLDER_MIME
            if not is_folder and (
                sc.is_tech_exception(path, it["name"])
                or it["name"].startswith("Danh Mục Hệ Thống - ")
                or re.match(r"^[A-Za-zÀ-ỹ]+_\d{6,8}_", it["name"])
            ):
                continue
            if ".obsidian" in path or it["name"].startswith("."):
                continue
            new = sc.safe_fix_name(it["name"], is_folder, it["mimeType"])
            if new == it["name"] or not new:
                continue
            if sc.nfc(new) in taken and sc.nfc(new) != sc.nfc(it["name"]):
                continue
            taken.add(sc.nfc(new))
            plan.append({"id": it["id"], "path": path, "old_name": it["name"], "new_name": new,
                         "kind": "folder" if is_folder else "file"})
    return plan


def execute_plan(plan, index, workers=8, chunk=8):
    drive = sc.Drive()
    log_path = sc.data_dir() / "executed_safe_fixes.json"
    executed = sc.read_json(log_path, {}) or {}
    pending = [p for p in plan if executed.get(p["id"], {}).get("new_name") != p["new_name"]]
    sc.log(f"Đã làm trước đó: {len(plan) - len(pending)} | Cần thực hiện: {len(pending)}")
    chunks = [pending[i:i + chunk] for i in range(0, len(pending), chunk)]
    _, by_id = sc.build_id_map(index)
    ok = fail = 0
    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(drive.batch_rename, [(p["id"], p["new_name"]) for p in ch]): ch for ch in chunks}
        for n, fut in enumerate(cf.as_completed(futs), 1):
            ch = futs[fut]
            plan_by_id = {p["id"]: p for p in ch}
            for fid, success, err in fut.result():
                p = plan_by_id[fid]
                if success:
                    ok += 1
                    executed[fid] = {"old_name": p["old_name"], "new_name": p["new_name"], "ts": int(time.time())}
                    if fid in by_id:
                        by_id[fid][1]["name"] = p["new_name"]
                else:
                    fail += 1
                    sc.log(f"  ! {p['old_name']} → {p['new_name']}: {err[:150]}")
            if n % 25 == 0 or n == len(chunks):
                sc.write_json(log_path, executed)
                sc.log(f"  → {ok + fail}/{len(pending)} | thành công {ok} | lỗi {fail} | "
                       f"{(ok + fail) / max(time.time() - t0, 1e-6):.1f} mục/giây")
    sc.write_json(log_path, executed)
    sc.save_index(index)
    sc.log(f"Hoàn tất: {ok} thành công, {fail} lỗi.")


def main():
    ap = argparse.ArgumentParser(description="Kiểm tra quy ước đặt tên Chuẩn V6 cho [A] STORAGE.")
    ap.add_argument("--nhanh", help="Chỉ kiểm tra một nhánh, ví dụ \"[01] HỌC THUẬT\"")
    ap.add_argument("--muc-do", choices=["LỖI", "CẢNH BÁO", "GỢI Ý"], default="GỢI Ý",
                    help="Mức độ tối thiểu đưa vào báo cáo (mặc định: tất cả)")
    ap.add_argument("--bo-qua-cau-truc", action="store_true", help="Chỉ kiểm tra tên, bỏ qua kiểm tra cấu trúc")
    ap.add_argument("--sua-an-toan", action="store_true", help="Lập kế hoạch sửa các lỗi cơ học an toàn")
    ap.add_argument("--thuc-thi", action="store_true", help="Áp dụng kế hoạch sửa lên Drive")
    ap.add_argument("--dong-y", action="store_true", help="Không hỏi xác nhận")
    ap.add_argument("--tai-len", action="store_true", help="Tải báo cáo .md lên [00] TỔNG QUAN/[02] NHẬT KÍ")
    ap.add_argument("--luong", type=int, default=8)
    args = ap.parse_args()

    index = sc.load_index()
    branch = sc.normalize_branch(args.nhanh)
    if branch == sc.ROOT_NAME:
        branch = None

    sc.log("Đang rà soát chỉ mục...")
    issues = audit(index, branch, check_structure=not args.bo_qua_cau_truc)
    issues.sort(key=lambda i: (sc.SEVERITY_ORDER[i[0]], i[1], i[2], i[3]))
    report, shown = build_report(issues, index, branch, args.muc_do)

    base = f"Báo Cáo Kiểm Tra Quy Ước - Storage, {sc.today_vn()}"
    md_path = sc.reports_dir() / f"{base}.md"
    csv_path = sc.reports_dir() / f"{base}.csv"
    md_path.write_text(report, encoding="utf-8")
    sc.write_csv(csv_path, ["Mức độ", "Mã", "Thư mục cha", "Tên", "ID", "Loại", "Mô tả", "Đề xuất an toàn", "URL"],
                 [(*i, sc.drive_url(i[4], sc.FOLDER_MIME if i[5] == "Thư mục" else "")) for i in shown])
    cnt = Counter(i[0] for i in shown)
    sc.log(f"Phát hiện: {cnt.get('LỖI', 0)} LỖI | {cnt.get('CẢNH BÁO', 0)} CẢNH BÁO | {cnt.get('GỢI Ý', 0)} GỢI Ý")
    sc.log(f"Báo cáo: {md_path}\nChi tiết: {csv_path}")

    if args.tai_len:
        fid = sc.publish_file(sc.Drive(), md_path, sc.nhat_ki_id())
        sc.log(f"Đã tải báo cáo lên [02] NHẬT KÍ: {sc.drive_url(fid)}")

    if args.sua_an_toan:
        plan = build_fix_plan(index, branch)
        plan_path = sc.data_dir() / "planned_safe_fixes.json"
        sc.write_json(plan_path, plan)
        kinds = Counter(p["kind"] for p in plan)
        sc.log(f"\nKế hoạch sửa an toàn: {len(plan)} mục ({kinds.get('folder', 0)} thư mục, "
               f"{kinds.get('file', 0)} tệp) → {plan_path}")
        for p in plan[:15]:
            sc.log(f"  • {p['old_name']}  →  {p['new_name']}")
        if args.thuc_thi and plan:
            if sc.confirm(f"Áp dụng {len(plan)} thao tác đổi tên lên Drive?", args.dong_y):
                execute_plan(plan, index, workers=args.luong)
        elif plan:
            sc.log("(Chạy thử — thêm --thuc-thi để áp dụng.)")


if __name__ == "__main__":
    main()
