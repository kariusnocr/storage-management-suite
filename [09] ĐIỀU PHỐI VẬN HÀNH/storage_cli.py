#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BỘ ĐIỀU PHỐI VẬN HÀNH HỢP NHẤT — [A] STORAGE (CHUẨN V6, v3.3)
==============================================================
Điểm vào duy nhất (CLI) cho mọi tác vụ quản trị kho `[A] STORAGE`:

- `quet`               : `[02] QUÉT CHỈ MỤC/storage_indexer.py`
- `kiem-tra`           : `[03] KIỂM TRA QUY ƯỚC/naming_auditor.py`
- `chuan-hoa`          : `[04] CHUẨN HÓA TÊN/storage_toolkit.py`
- `danh-muc`           : `[05] DANH MỤC HỆ THỐNG/sheet_engine.py`
- `trung-lap`          : `[06] RÀ SOÁT TRÙNG LẶP/dedup_scanner.py`
- `bao-cao`            : `[07] BÁO CÁO THỐNG KÊ/stats_reporter.py`
- `trien-khai`         : `[08] TRIỂN KHAI MÃ NGUỒN/deploy_sync.py`
- `sao-chep-di-chuyen` : `[10] SAO CHÉP DI CHUYỂN/transfer_manager.py`
- `nhap-du-lieu`       : `[11] NHẬP DỮ LIỆU MỚI/data_ingestor.py`
- `tra-cuu`            : `[12] TRA CỨU VÀ KIỂM TOÁN/storage_inspector.py`
- `doc-tep`            : `[13] ĐỌC TỆP/file_reader.py`
- `phan-tich`          : `[14] PHÂN TÍCH NỘI DUNG/content_analyzer.py`
- `github`             : `[15] ĐỒNG BỘ GITHUB/github_sync.py`
- `phan-tich-anh`      : `[16] PHÂN TÍCH HÌNH ẢNH/image_analyzer.py`
- `phan-tich-am-thanh` : `[17] PHÂN TÍCH ÂM THANH/audio_analyzer.py`
- `phan-tich-video`    : `[18] PHÂN TÍCH VIDEO/video_analyzer.py`
- `kiem-thu`           : Chạy toàn bộ kiểm thử tự động trong `[01] THƯ VIỆN LÕI/tests`
- `quy-trinh-nhanh`    : `[02] tăng cường` → `[03]` → `[04]` → `[05]` → `[07]` (mặc định chạy thử)
- `bao-tri-dinh-ki`    : Quét toàn kho → `[03]` → `[06]` → `[04]` → `[12] kiểm toán tổng quan` → `[05]` → `[07]` (mặc định chạy thử)

Mọi lần chạy quy trình đều lưu nhật kí tại `<STORAGE_DATA_DIR>/runs/` kèm mã thoát thống nhất.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple


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
    raise SystemExit("Không tìm thấy storage_core.py — đặt `[01] THƯ VIỆN LÕI` cạnh chương trình.")


sc = _nap_thu_vien_loi()

MODULES_ROOT = Path(__file__).resolve().parent.parent

MODULE_SCRIPTS = {
    "quet": MODULES_ROOT / "[02] QUÉT CHỈ MỤC" / "storage_indexer.py",
    "kiem-tra": MODULES_ROOT / "[03] KIỂM TRA QUY ƯỚC" / "naming_auditor.py",
    "chuan-hoa": MODULES_ROOT / "[04] CHUẨN HÓA TÊN" / "storage_toolkit.py",
    "danh-muc": MODULES_ROOT / "[05] DANH MỤC HỆ THỐNG" / "sheet_engine.py",
    "trung-lap": MODULES_ROOT / "[06] RÀ SOÁT TRÙNG LẶP" / "dedup_scanner.py",
    "bao-cao": MODULES_ROOT / "[07] BÁO CÁO THỐNG KÊ" / "stats_reporter.py",
    "trien-khai": MODULES_ROOT / "[08] TRIỂN KHAI MÃ NGUỒN" / "deploy_sync.py",
    "sao-chep-di-chuyen": MODULES_ROOT / "[10] SAO CHÉP DI CHUYỂN" / "transfer_manager.py",
    "nhap-du-lieu": MODULES_ROOT / "[11] NHẬP DỮ LIỆU MỚI" / "data_ingestor.py",
    "tra-cuu": MODULES_ROOT / "[12] TRA CỨU VÀ KIỂM TOÁN" / "storage_inspector.py",
    "doc-tep": MODULES_ROOT / "[13] ĐỌC TỆP" / "file_reader.py",
    "phan-tich": MODULES_ROOT / "[14] PHÂN TÍCH NỘI DUNG" / "content_analyzer.py",
    "github": MODULES_ROOT / "[15] ĐỒNG BỘ GITHUB" / "github_sync.py",
    "phan-tich-anh": MODULES_ROOT / "[16] PHÂN TÍCH HÌNH ẢNH" / "image_analyzer.py",
    "phan-tich-am-thanh": MODULES_ROOT / "[17] PHÂN TÍCH ÂM THANH" / "audio_analyzer.py",
    "phan-tich-video": MODULES_ROOT / "[18] PHÂN TÍCH VIDEO" / "video_analyzer.py",
}


def runs_dir() -> Path:
    p = sc.data_dir() / "runs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def run_step(step_name: str, cmd: List[str], log_handle=None) -> Tuple[int, float]:
    t0 = time.time()
    header = f"\n>>> [{step_name}] {' '.join(cmd)}\n"
    sc.log(header.strip())
    if log_handle:
        log_handle.write(header)
        log_handle.flush()

    proc = subprocess.Popen(
        cmd,
        cwd=str(MODULES_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
        if log_handle:
            log_handle.write(line)
    rc = proc.wait()
    dt_sec = round(time.time() - t0, 2)
    footer = f"<<< [{step_name}] mã thoát={rc} | thời gian={dt_sec}s\n"
    sc.log(footer.strip())
    if log_handle:
        log_handle.write(footer)
        log_handle.flush()
    return rc, dt_sec


def run_pipeline(name: str, steps: List[Tuple[str, List[str]]]) -> int:
    ts = sc.now_stamp()
    log_file = runs_dir() / f"run_{ts}_{name}.log"
    records = []
    final_rc = 0
    with open(log_file, "w", encoding="utf-8") as lf:
        lf.write(f"# RUN {name} | started_utc={sc.now_utc_iso()}\n")
        for s_name, cmd in steps:
            rc, sec = run_step(s_name, cmd, log_handle=lf)
            records.append({"step": s_name, "cmd": cmd, "returncode": rc, "elapsed_sec": sec})
            if rc != 0:
                final_rc = rc
                break
    sc.write_json(
        runs_dir() / "latest_run.json",
        {
            "workflow": name,
            "finished_utc": sc.now_utc_iso(),
            "returncode": final_rc,
            "log_file": str(log_file),
            "steps": records,
        },
        indent=1,
    )
    sc.log(f"\nNhật kí điều phối: {log_file} (mã thoát={final_rc})")
    return final_rc


def build_quick_steps(
    thuc_thi: bool,
    dong_y: bool,
    tai_len: bool,
    nhanh: Optional[str],
    bo_qua_quet: bool,
) -> List[Tuple[str, List[str]]]:
    py = sys.executable
    steps: List[Tuple[str, List[str]]] = []
    branch_flag = ["--nhanh", nhanh] if nhanh else []

    if not bo_qua_quet:
        scan_cmd = [py, str(MODULE_SCRIPTS["quet"]), "--kem-shortcut"]
        if nhanh:
            scan_cmd += branch_flag
        else:
            scan_cmd.append("--tang-cuong")
        steps.append(("02 Quét Chỉ Mục", scan_cmd))

    audit_cmd = [py, str(MODULE_SCRIPTS["kiem-tra"]), *branch_flag]
    if tai_len:
        audit_cmd.append("--tai-len")
    steps.append(("03 Kiểm Tra Quy Ước", audit_cmd))

    kit_cmd = [py, str(MODULE_SCRIPTS["chuan-hoa"]), "--plan", *branch_flag]
    if thuc_thi:
        kit_cmd += ["--execute", "--dong-y" if dong_y else ""]
    kit_cmd = [c for c in kit_cmd if c]
    steps.append(("04 Chuẩn Hóa Tên", kit_cmd))

    sheet_cmd = [py, str(MODULE_SCRIPTS["danh-muc"]), "--chi-thay-doi", "--sua-ten-bang", *branch_flag]
    if thuc_thi:
        sheet_cmd += ["--thuc-thi", "--dong-y" if dong_y else ""]
    sheet_cmd = [c for c in sheet_cmd if c]
    steps.append(("05 Danh Mục Hệ Thống", sheet_cmd))

    rep_cmd = [py, str(MODULE_SCRIPTS["bao-cao"])]
    if tai_len:
        rep_cmd.append("--tai-len")
    steps.append(("07 Báo Cáo Thống Kê", rep_cmd))
    return steps


def build_maintenance_steps(
    thuc_thi: bool,
    dong_y: bool,
    tai_len: bool,
    nhanh: Optional[str],
    tang_cuong: bool,
) -> List[Tuple[str, List[str]]]:
    py = sys.executable
    branch_flag = ["--nhanh", nhanh] if nhanh else []
    steps: List[Tuple[str, List[str]]] = []

    scan_cmd = [py, str(MODULE_SCRIPTS["quet"]), "--luong", "32", "--kem-shortcut", *branch_flag]
    if tang_cuong and not nhanh:
        scan_cmd.append("--tang-cuong")
    steps.append(("02 Quét Chỉ Mục", scan_cmd))

    audit_cmd = [py, str(MODULE_SCRIPTS["kiem-tra"]), *branch_flag]
    if tai_len:
        audit_cmd.append("--tai-len")
    steps.append(("03 Kiểm Tra Quy Ước", audit_cmd))

    dedup_cmd = [
        py, str(MODULE_SCRIPTS["trung-lap"]),
        "--kiem-tra-shortcut", "--gom-tong-quan-trung", "--gom-phien-ban", "--xac-minh-noi-dung",
        *branch_flag,
    ]
    if thuc_thi:
        dedup_cmd.append("--thuc-thi")
        if dong_y:
            dedup_cmd.append("--dong-y")
    if tai_len:
        dedup_cmd.append("--tai-len")
    steps.append(("06 Rà Soát Trùng Lặp", dedup_cmd))

    kit_cmd = [py, str(MODULE_SCRIPTS["chuan-hoa"]), "--plan", *branch_flag]
    if thuc_thi:
        kit_cmd.append("--execute")
        if dong_y:
            kit_cmd.append("--dong-y")
    steps.append(("04 Chuẩn Hóa Tên", kit_cmd))

    insp_cmd = [py, str(MODULE_SCRIPTS["tra-cuu"]), "kiem-toan-tong-quan", "--bu-dap", *branch_flag]
    if thuc_thi:
        insp_cmd.append("--thuc-thi")
        if dong_y:
            insp_cmd.append("--dong-y")
    steps.append(("12 Kiểm Toán Độ Phủ Tổng Quan", insp_cmd))

    if thuc_thi:
        steps.append(("02 Quét Lại Chỉ Mục Sau Chuẩn Hóa", [py, str(MODULE_SCRIPTS["quet"]), "--tang-cuong", "--kem-shortcut"]))

    sheet_cmd = [py, str(MODULE_SCRIPTS["danh-muc"]), "--chi-thay-doi", "--tao-moi", "--sua-ten-bang", *branch_flag]
    if thuc_thi:
        sheet_cmd.append("--thuc-thi")
        if dong_y:
            sheet_cmd.append("--dong-y")
    steps.append(("05 Danh Mục Hệ Thống", sheet_cmd))

    rep_cmd = [py, str(MODULE_SCRIPTS["bao-cao"])]
    if tai_len:
        rep_cmd.append("--tai-len")
    steps.append(("07 Báo Cáo Thống Kê", rep_cmd))
    return steps


def main() -> None:
    choices = list(MODULE_SCRIPTS.keys()) + ["kiem-thu", "quy-trinh-nhanh", "bao-tri-dinh-ki"]
    ap = argparse.ArgumentParser(description="Điều phối vận hành thống nhất — [A] STORAGE (v3.0).")
    ap.add_argument("lenh", choices=choices, help="Lệnh hoặc quy trình cần chạy")
    ap.add_argument("--thuc-thi", action="store_true", help="Cho phép ghi lên Drive ở quy trình phối hợp")
    ap.add_argument("--dong-y", action="store_true", help="Không hỏi xác nhận")
    ap.add_argument("--tai-len", action="store_true", help="Tải các báo cáo lên [02] NHẬT KÍ")
    ap.add_argument("--nhanh", help="Giới hạn phạm vi nhánh")
    ap.add_argument("--bo-qua-quet", action="store_true", help="Bỏ qua bước [02] trong `quy-trinh-nhanh`")
    ap.add_argument("--tang-cuong", action="store_true", help="Dùng `--tang-cuong` cho [02] trong `bao-tri-dinh-ki`")
    args, extra = ap.parse_known_args()

    py = sys.executable
    if args.lenh in MODULE_SCRIPTS:
        script = MODULE_SCRIPTS[args.lenh]
        forward = list(extra)
        if args.thuc_thi:
            forward.append("--thuc-thi")
        if args.dong_y:
            forward.append("--dong-y")
        if args.tai_len:
            forward.append("--tai-len")
        if args.nhanh:
            forward += ["--nhanh", args.nhanh]
        rc = run_pipeline(args.lenh, [(args.lenh, [py, str(script), *forward])])
        sys.exit(rc)

    if args.lenh == "kiem-thu":
        test_dir = MODULES_ROOT / "[01] THƯ VIỆN LÕI" / "tests"
        rc = run_pipeline(
            "kiem-thu",
            [("unittest", [py, "-m", "unittest", "discover", "-s", str(test_dir), "-v"])],
        )
        sys.exit(rc)

    if args.lenh == "quy-trinh-nhanh":
        steps = build_quick_steps(args.thuc_thi, args.dong_y, args.tai_len, args.nhanh, args.bo_qua_quet)
        sys.exit(run_pipeline("quy-trinh-nhanh", steps))

    if args.lenh == "bao-tri-dinh-ki":
        steps = build_maintenance_steps(args.thuc_thi, args.dong_y, args.tai_len, args.nhanh, args.tang_cuong)
        sys.exit(run_pipeline("bao-tri-dinh-ki", steps))


if __name__ == "__main__":
    main()
