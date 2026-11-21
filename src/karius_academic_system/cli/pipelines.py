"""Bộ chạy quy trình hợp nhất trong tiến trình (in-process pipeline) dùng chung ngữ cảnh."""

from __future__ import annotations

import contextlib
import importlib
import io
import sys
import time
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from karius_academic_system import core as sc

MODULE_MAP: Dict[str, str] = {
    "quet": "karius_academic_system.ops.indexer",
    "kiem-tra": "karius_academic_system.ops.auditor",
    "chuan-hoa": "karius_academic_system.ops.normalizer",
    "danh-muc": "karius_academic_system.ops.catalog_engine",
    "trung-lap": "karius_academic_system.ops.dedup",
    "bao-cao": "karius_academic_system.ops.reporter",
    "trien-khai": "karius_academic_system.sync.drive_deploy",
    "sao-chep-di-chuyen": "karius_academic_system.ops.transfer",
    "nhap-du-lieu": "karius_academic_system.ops.ingestor",
    "tra-cuu": "karius_academic_system.ops.inspector",
    "doc-tep": "karius_academic_system.media.file_reader",
    "phan-tich": "karius_academic_system.media.content_analyzer",
    "github": "karius_academic_system.sync.github_sync",
    "phan-tich-anh": "karius_academic_system.media.image_analyzer",
    "phan-tich-am-thanh": "karius_academic_system.media.audio_analyzer",
    "phan-tich-video": "karius_academic_system.media.video_analyzer",
    "doctor": "karius_academic_system.ops.doctor",
    "setup": "karius_academic_system.ops.setup_tools",
    "cai-dat-phu-thuoc": "karius_academic_system.ops.setup_tools",
    "watch": "karius_academic_system.ops.watcher",
}


class _TeeWriter:
    def __init__(self, *streams) -> None:
        self._streams = [s for s in streams if s is not None]

    def write(self, data: str) -> int:
        for s in self._streams:
            s.write(data)
            s.flush()
        return len(data)

    def flush(self) -> None:
        for s in self._streams:
            s.flush()


def invoke_module_in_process(cmd_name: str, extra_args: Sequence[str] = ()) -> int:
    """Gọi trực tiếp hàm `main()` của mô-đun trong cùng tiến trình Python (không spawn subprocess)."""
    mod_path = MODULE_MAP.get(cmd_name)
    if not mod_path:
        raise ValueError(f"Không tìm thấy mô-đun cho lệnh `{cmd_name}`")
    mod = importlib.import_module(mod_path)
    main_fn: Callable = getattr(mod, "main")

    prev_argv = sys.argv[:]
    sys.argv = [f"kas {cmd_name}", *list(extra_args)]
    try:
        try:
            res = main_fn(list(extra_args))
        except TypeError:
            res = main_fn()
        return int(res) if isinstance(res, int) else 0
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        sc.log(str(code))
        return 1
    finally:
        sys.argv = prev_argv


def run_step_in_process(
    step_name: str,
    cmd_name: str,
    args: Sequence[str],
    log_handle: Optional[io.TextIOBase] = None,
) -> Tuple[int, float]:
    t0 = time.time()
    header = f"\n>>> [{step_name}] kas {cmd_name} {' '.join(args)}\n"
    sc.log(header.strip())
    if log_handle:
        log_handle.write(header)
        log_handle.flush()

    tee = _TeeWriter(sys.stdout, log_handle)
    with contextlib.redirect_stdout(tee), contextlib.redirect_stderr(tee):
        try:
            rc = invoke_module_in_process(cmd_name, args)
        except Exception as exc:
            sc.log(f"[LỖI] {step_name}: {exc}")
            rc = 1

    dt_sec = round(time.time() - t0, 2)
    footer = f"<<< [{step_name}] mã thoát={rc} | thời gian={dt_sec}s\n"
    sc.log(footer.strip())
    if log_handle:
        log_handle.write(footer)
        log_handle.flush()
    return rc, dt_sec


def run_pipeline(name: str, steps: List[Tuple[str, str, List[str]]]) -> int:
    """Chạy tuần tự chuỗi bước in-process, ghi nhật kí hợp nhất tại `<KAS_DATA_DIR>/runs/`."""
    ts = sc.now_stamp()
    log_file = sc.runs_dir() / f"run_{ts}_{name}.log"
    records = []
    final_rc = 0
    with open(log_file, "w", encoding="utf-8") as lf:
        lf.write(f"# RUN {name} | version={sc.__version__} | started_utc={sc.now_utc_iso()}\n")
        for step_name, cmd_name, cmd_args in steps:
            rc, sec = run_step_in_process(step_name, cmd_name, cmd_args, log_handle=lf)
            records.append({
                "step": step_name,
                "command": f"kas {cmd_name} {' '.join(cmd_args)}".strip(),
                "returncode": rc,
                "elapsed_sec": sec,
            })
            if rc != 0:
                final_rc = rc
                break
    sc.write_json(
        sc.runs_dir() / "latest_run.json",
        {
            "workflow": name,
            "version": sc.__version__,
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
) -> List[Tuple[str, str, List[str]]]:
    steps: List[Tuple[str, str, List[str]]] = []
    branch_flag = ["--nhanh", nhanh] if nhanh else []

    if not bo_qua_quet:
        scan_args = ["--kem-shortcut", *(branch_flag if nhanh else ["--tang-cuong"])]
        steps.append(("02 Quét Chỉ Mục", "quet", scan_args))

    audit_args = [*branch_flag, *(["--tai-len"] if tai_len else [])]
    steps.append(("03 Kiểm Tra Quy Ước & Danh Mục V7", "kiem-tra", audit_args))

    kit_args = ["--plan", *branch_flag]
    if thuc_thi:
        kit_args += ["--execute", *(["--dong-y"] if dong_y else [])]
    steps.append(("04 Chuẩn Hóa Tên", "chuan-hoa", kit_args))

    sheet_args = ["--chi-thay-doi", "--sua-ten-bang", "--che-do-danh-muc", "smart", *branch_flag]
    if thuc_thi:
        sheet_args += ["--thuc-thi", *(["--dong-y"] if dong_y else [])]
    steps.append(("05 Danh Mục Hệ Thống V7", "danh-muc", sheet_args))

    rep_args = ["--tai-len"] if tai_len else []
    steps.append(("07 Báo Cáo Thống Kê", "bao-cao", rep_args))
    return steps


def build_maintenance_steps(
    thuc_thi: bool,
    dong_y: bool,
    tai_len: bool,
    nhanh: Optional[str],
    tang_cuong: bool,
) -> List[Tuple[str, str, List[str]]]:
    branch_flag = ["--nhanh", nhanh] if nhanh else []
    steps: List[Tuple[str, str, List[str]]] = []

    scan_args = ["--luong", "32", "--kem-shortcut", *branch_flag]
    if tang_cuong and not nhanh:
        scan_args.append("--tang-cuong")
    steps.append(("02 Quét Chỉ Mục", "quet", scan_args))

    steps.append(("03 Kiểm Tra Quy Ước & Danh Mục V7", "kiem-tra", [*branch_flag, *(["--tai-len"] if tai_len else [])]))

    dedup_args = [
        "--kiem-tra-shortcut", "--gom-tong-quan-trung", "--gom-phien-ban",
        "--don-rac-he-thong", "--xac-minh-noi-dung", *branch_flag,
    ]
    if thuc_thi:
        dedup_args += ["--thuc-thi", *(["--dong-y"] if dong_y else [])]
    if tai_len:
        dedup_args.append("--tai-len")
    steps.append(("06 Rà Soát Trùng Lặp & Rác Hệ Thống", "trung-lap", dedup_args))

    kit_args = ["--plan", *branch_flag]
    if thuc_thi:
        kit_args += ["--execute", *(["--dong-y"] if dong_y else [])]
    steps.append(("04 Chuẩn Hóa Tên", "chuan-hoa", kit_args))

    insp_args = ["kiem-toan-tong-quan", "--bu-dap", *branch_flag]
    if thuc_thi:
        insp_args += ["--thuc-thi", *(["--dong-y"] if dong_y else [])]
    steps.append(("12 Kiểm Toán Độ Phủ Tổng Quan", "tra-cuu", insp_args))

    if thuc_thi:
        steps.append(("02 Quét Lại Chỉ Mục Sau Chuẩn Hóa", "quet", ["--tang-cuong", "--kem-shortcut"]))

    sheet_args = ["--chi-thay-doi", "--tao-moi", "--sua-ten-bang", "--che-do-danh-muc", "smart", *branch_flag]
    if thuc_thi:
        sheet_args += ["--thuc-thi", *(["--dong-y"] if dong_y else [])]
    steps.append(("05 Danh Mục Hệ Thống V7", "danh-muc", sheet_args))

    steps.append(("07 Báo Cáo Thống Kê", "bao-cao", ["--tai-len"] if tai_len else []))
    return steps
