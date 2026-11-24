"""Trình tự động cài đặt công cụ hệ thống, thư viện Python & dữ liệu OCR tiếng Việt (`kas setup`)."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from karius_academic_system import APP_NAME, APP_SHORT, __version__
from karius_academic_system import core as sc
from karius_academic_system.core.tools_env import (
    add_dirs_to_windows_user_path,
    find_cli_tool,
    refresh_system_path,
    shared_tessdata_dir,
)

TESSDATA_FAST_BASE_URL = "https://github.com/tesseract-ocr/tessdata_fast/raw/main"


@dataclass(frozen=True)
class PythonPkgSpec:
    import_name: str
    pip_name: str
    group: str  # core | recommended | optional
    purpose: str


@dataclass(frozen=True)
class SystemToolSpec:
    id: str
    binaries: Tuple[str, ...]
    purpose: str
    winget_id: str
    apt_pkg: str


PYTHON_PACKAGE_SPECS: Tuple[PythonPkgSpec, ...] = (
    PythonPkgSpec("openpyxl", "openpyxl", "core", "Đọc/ghi bảng tính Excel (.xlsx)"),
    PythonPkgSpec("googleapiclient", "google-api-python-client", "core", "Kết nối Google Drive API trực tiếp"),
    PythonPkgSpec("google_auth_oauthlib", "google-auth-oauthlib", "core", "Đăng nhập Google OAuth 2.0"),
    PythonPkgSpec("google_auth_httplib2", "google-auth-httplib2", "core", "Kênh HTTP xác thực Google API"),
    PythonPkgSpec("PIL", "Pillow", "recommended", "Phân tích hình ảnh, EXIF, dHash/pHash, Contact Sheet"),
    PythonPkgSpec("numpy", "numpy", "recommended", "Phân tích độ nét Laplacian, pHash & thống kê ảnh"),
    PythonPkgSpec("fastapi", "fastapi", "recommended", "Web API hiệu năng cao (tự dự phòng --stdlib nếu SAC chặn)"),
    PythonPkgSpec("uvicorn", "uvicorn", "recommended", "Máy chủ ASGI cho FastAPI"),
    PythonPkgSpec("webview", "pywebview", "optional", "Cửa sổ Desktop gốc (không bắt buộc trên Windows 11 SAC)"),
)

SYSTEM_TOOL_SPECS: Tuple[SystemToolSpec, ...] = (
    SystemToolSpec("gh", ("gh",), "GitHub CLI (quản lý repo, PR, Releases)", "GitHub.cli", "gh"),
    SystemToolSpec("git", ("git",), "Quản lý phiên bản Git", "Git.Git", "git"),
    SystemToolSpec("7z", ("7z",), "Kiểm tra tệp nén ZIP/RAR/7Z", "7zip.7zip", "p7zip-full"),
    SystemToolSpec("ffmpeg", ("ffmpeg", "ffprobe"), "Xử lý & đọc metadata âm thanh/video", "Gyan.FFmpeg", "ffmpeg"),
    SystemToolSpec("tesseract", ("tesseract",), "Nhận dạng chữ OCR (tiếng Việt & tiếng Anh)", "UB-Mannheim.TesseractOCR", "tesseract-ocr"),
    SystemToolSpec("poppler", ("pdftotext", "pdfinfo", "pdftoppm"), "Đọc văn bản & kết xuất ảnh trang PDF", "oschwartz10612.Poppler", "poppler-utils"),
)

_SETUP_LOCK = threading.Lock()
_SETUP_JOBS: Dict[str, Dict[str, Any]] = {}
_LAST_SETUP_JOB_ID: str = ""


def _in_virtualenv() -> bool:
    return bool(os.environ.get("VIRTUAL_ENV")) or (getattr(sys, "base_prefix", sys.prefix) != sys.prefix)


def probe_python_package(mod_name: str) -> Tuple[bool, str, bool]:
    """Kiểm tra gói Python có nạp được không. Trả về `(ok, version_or_reason, blocked_by_sac)`."""
    try:
        mod = importlib.import_module(mod_name)
        return True, str(getattr(mod, "__version__", "installed")), False
    except ImportError:
        return False, "", False
    except OSError as exc:
        # Windows Smart App Control thường trả WinError 4551 khi nạp .pyd/.dll chưa ký số
        return False, f"bị Smart App Control / OS chặn ({exc})", True


def download_ocr_traineddata(
    langs: Sequence[str] = ("vie", "eng"),
    *,
    force: bool = False,
    timeout: int = 45,
    log_cb: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Tải dữ liệu OCR chính thức (`vie.traineddata`, `eng.traineddata`) vào `~/.local/share/kas/tessdata` (không cần Admin)."""
    emit = log_cb or (lambda _m: None)
    dest_dir = shared_tessdata_dir()
    downloaded: List[str] = []
    skipped: List[str] = []
    errors: List[str] = []

    for lang in langs:
        fname = f"{lang}.traineddata"
        target = dest_dir / fname
        if target.exists() and target.stat().st_size > 100_000 and not force:
            skipped.append(str(target))
            emit(f"  ✓ Đã có sẵn {fname} tại {target}")
            continue
        url = f"{TESSDATA_FAST_BASE_URL}/{fname}"
        emit(f"  ↓ Đang tải {fname} từ {url} ...")
        tmp = target.with_suffix(".traineddata.tmp")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": f"{APP_SHORT}/{__version__}"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
            if len(data) < 100_000:
                raise ValueError(f"Kích thước tệp tải về bất thường ({len(data)} bytes)")
            tmp.write_bytes(data)
            tmp.replace(target)
            downloaded.append(str(target))
            emit(f"  ✓ Đã tải {fname} ({sc.human_size(len(data))}) → {target}")
        except Exception as exc:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
            msg = f"Không tải được {fname}: {exc}"
            errors.append(msg)
            emit(f"  ✗ {msg}")

    sc.reset_ocr_cache()
    return {
        "ok": len(errors) == 0,
        "tessdata_dir": str(dest_dir),
        "downloaded": downloaded,
        "skipped": skipped,
        "errors": errors,
    }


def _build_pip_install_cmd(pip_name: str) -> List[str]:
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "--no-warn-script-location"]
    if not _in_virtualenv():
        cmd.append("--user")
    if os.name != "nt" and not _in_virtualenv():
        # Tránh PEP 668 externally-managed-environment trên Debian/Ubuntu
        cmd.append("--break-system-packages")
    cmd.append(pip_name)
    return cmd


def install_python_packages(
    *,
    include_pywebview: bool = False,
    dry_run: bool = False,
    log_cb: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Tự động cài các thư viện Python còn thiếu (cài từng gói độc lập & kiểm chứng tương thích Smart App Control)."""
    emit = log_cb or (lambda _m: None)
    installed: List[str] = []
    already_ok: List[str] = []
    blocked_sac: List[str] = []
    errors: List[str] = []

    for spec in PYTHON_PACKAGE_SPECS:
        if spec.group == "optional" and not include_pywebview:
            continue
        ok, ver, sac = probe_python_package(spec.import_name)
        if ok:
            already_ok.append(spec.pip_name)
            emit(f"  ✓ {spec.pip_name} ({ver}) đã sẵn sàng")
            continue
        if sac:
            blocked_sac.append(spec.pip_name)
            emit(f"  ⚠ {spec.pip_name}: {ver} — bỏ qua (KAS tự chạy dự phòng thuần Python)")
            continue
        cmd = _build_pip_install_cmd(spec.pip_name)
        if dry_run:
            emit(f"  [CHẠY THỬ] {' '.join(cmd)}")
            installed.append(spec.pip_name)
            continue
        emit(f"  ↓ Đang cài thư viện Python `{spec.pip_name}`...")
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
            if proc.returncode != 0 and "--break-system-packages" in cmd:
                # pip phiên bản cũ không có cờ --break-system-packages
                retry_cmd = [c for c in cmd if c != "--break-system-packages"]
                proc = subprocess.run(retry_cmd, capture_output=True, text=True, timeout=240)
            if proc.returncode != 0:
                tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-1:] or ["mã lỗi " + str(proc.returncode)]
                msg = f"Cài `{spec.pip_name}` thất bại: {tail[0]}"
                errors.append(msg)
                emit(f"  ✗ {msg}")
                continue
            importlib.invalidate_caches()
            ok2, ver2, sac2 = probe_python_package(spec.import_name)
            if ok2:
                installed.append(spec.pip_name)
                emit(f"  ✓ Đã cài `{spec.pip_name}` ({ver2})")
            elif sac2:
                blocked_sac.append(spec.pip_name)
                emit(f"  ⚠ Đã cài `{spec.pip_name}` nhưng Windows Smart App Control chặn nạp .pyd — KAS sẽ tự dùng chế độ thuần Python.")
            else:
                installed.append(spec.pip_name)
                emit(f"  ✓ Đã cài `{spec.pip_name}` (có hiệu lực sau khi khởi động lại KAS)")
        except Exception as exc:
            msg = f"Lỗi khi cài `{spec.pip_name}`: {exc}"
            errors.append(msg)
            emit(f"  ✗ {msg}")

    return {
        "ok": len(errors) == 0,
        "installed": installed,
        "already_ok": already_ok,
        "blocked_sac": blocked_sac,
        "errors": errors,
    }


def _detect_pkg_manager() -> str:
    if os.name == "nt":
        return "winget" if find_cli_tool("winget") else ""
    if shutil.which("apt-get"):
        return "apt"
    return ""


def _tool_install_command(pkg_mgr: str, spec: SystemToolSpec) -> Optional[List[str]]:
    if pkg_mgr == "winget" and spec.winget_id:
        return [
            "winget",
            "install",
            "--exact",
            "--id",
            spec.winget_id,
            "--accept-package-agreements",
            "--accept-source-agreements",
            "--disable-interactivity",
            "--silent",
        ]
    if pkg_mgr == "apt" and spec.apt_pkg:
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            return ["apt-get", "install", "-y", spec.apt_pkg]
    return None


def install_system_tools(
    *,
    dry_run: bool = False,
    log_cb: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Tự động cài công cụ hệ thống còn thiếu (`gh`, `git`, `7z`, `ffmpeg`, `tesseract`, `poppler`) & tự cập nhật PATH."""
    emit = log_cb or (lambda _m: None)
    refresh_system_path()

    pkg_mgr = _detect_pkg_manager()
    already_ok: List[str] = []
    installed: List[str] = []
    skipped_manual: List[str] = []
    errors: List[str] = []

    missing_specs: List[SystemToolSpec] = []
    for spec in SYSTEM_TOOL_SPECS:
        if all(bool(find_cli_tool(b, refresh=False)) for b in spec.binaries):
            already_ok.append(spec.id)
            emit(f"  ✓ {spec.id} ({', '.join(spec.binaries)}) đã có sẵn")
        else:
            missing_specs.append(spec)

    if not missing_specs:
        return {
            "ok": True,
            "package_manager": pkg_mgr,
            "installed": [],
            "already_ok": already_ok,
            "skipped_manual": [],
            "persisted_path_dirs": [],
            "errors": [],
        }

    if not pkg_mgr:
        msg = "Không tìm thấy trình quản lý gói tự động (winget/apt). Vui lòng cài thủ công các công cụ còn thiếu."
        emit(f"  ⚠ {msg}")
        return {
            "ok": False,
            "package_manager": "",
            "installed": [],
            "already_ok": already_ok,
            "skipped_manual": [s.id for s in missing_specs],
            "persisted_path_dirs": [],
            "errors": [msg],
        }

    for spec in missing_specs:
        cmd = _tool_install_command(pkg_mgr, spec)
        if not cmd:
            skipped_manual.append(spec.id)
            emit(f"  ○ Bỏ qua `{spec.id}` (cần quyền quản trị / cài thủ công trên {platform.system()}: {spec.apt_pkg})")
            continue
        if dry_run:
            emit(f"  [CHẠY THỬ] {' '.join(cmd)}")
            installed.append(spec.id)
            continue
        emit(f"  ↓ Đang cài `{spec.id}` qua `{pkg_mgr}` ({spec.purpose})...")
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=420)
            # WinGet có thể trả mã -1978335189 (0x8A15002B: đã cài sẵn phiên bản mới nhất)
            if proc.returncode in (0, -1978335189, 2316632107):
                installed.append(spec.id)
                emit(f"  ✓ Hoàn tất cài đặt `{spec.id}`")
            else:
                lines = [ln.strip() for ln in (proc.stdout + "\n" + proc.stderr).splitlines() if ln.strip()]
                tail = lines[-1] if lines else f"mã lỗi {proc.returncode}"
                msg = f"Cài `{spec.id}` qua `{pkg_mgr}` thất bại: {tail}"
                errors.append(msg)
                emit(f"  ✗ {msg}")
        except Exception as exc:
            msg = f"Lỗi cài `{spec.id}`: {exc}"
            errors.append(msg)
            emit(f"  ✗ {msg}")

    # Tự động quét lại WinGet/Program Files & ghi bền vững vào User PATH trên Windows
    persisted_dirs: List[str] = []
    if not dry_run:
        refresh_system_path()
        discovered_dirs: List[str] = []
        for spec in SYSTEM_TOOL_SPECS:
            for b in spec.binaries:
                found = find_cli_tool(b, refresh=False)
                if found:
                    parent = str(Path(found).parent)
                    if parent not in discovered_dirs:
                        discovered_dirs.append(parent)
        if os.name == "nt" and discovered_dirs:
            persisted_dirs = add_dirs_to_windows_user_path(discovered_dirs)
            if persisted_dirs:
                emit(f"  ✓ Đã tự thêm {len(persisted_dirs)} thư mục công cụ vào PATH Windows: {', '.join(persisted_dirs)}")
        sc.reset_ocr_cache()

    return {
        "ok": len(errors) == 0,
        "package_manager": pkg_mgr,
        "installed": installed,
        "already_ok": already_ok,
        "skipped_manual": skipped_manual,
        "persisted_path_dirs": persisted_dirs,
        "errors": errors,
    }


def build_setup_plan() -> Dict[str, Any]:
    """Lập danh sách các thành phần còn thiếu có thể tự động cài đặt ngay."""
    refresh_system_path()
    missing_py = []
    sac_blocked_py = []
    for spec in PYTHON_PACKAGE_SPECS:
        if spec.group == "optional":
            continue
        ok, _ver, sac = probe_python_package(spec.import_name)
        if not ok:
            if sac:
                sac_blocked_py.append(spec.pip_name)
            else:
                missing_py.append({"name": spec.pip_name, "group": spec.group, "purpose": spec.purpose})

    missing_tools = []
    for spec in SYSTEM_TOOL_SPECS:
        missing_bins = [b for b in spec.binaries if not find_cli_tool(b, refresh=False)]
        if missing_bins:
            missing_tools.append({
                "id": spec.id,
                "missing_binaries": missing_bins,
                "purpose": spec.purpose,
                "winget_id": spec.winget_id,
                "apt_pkg": spec.apt_pkg,
            })

    td = shared_tessdata_dir()
    missing_ocr_files = [f"{lg}.traineddata" for lg in ("vie", "eng") if not (td / f"{lg}.traineddata").exists()]

    return {
        "platform": platform.system(),
        "package_manager": _detect_pkg_manager(),
        "tessdata_dir": str(td),
        "missing_python": missing_py,
        "sac_blocked_python": sac_blocked_py,
        "missing_tools": missing_tools,
        "missing_ocr_files": missing_ocr_files,
        "needs_setup": bool(missing_py or missing_tools or missing_ocr_files),
    }


def run_auto_setup(
    *,
    install_python: bool = True,
    install_tools: bool = True,
    install_ocr_data: bool = True,
    include_pywebview: bool = False,
    dry_run: bool = False,
    log_cb: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Thực thi quy trình tự động cài đặt trọn bộ công cụ, thư viện Python và dữ liệu OCR tiếng Việt."""
    logs: List[str] = []

    def _emit(msg: str) -> None:
        logs.append(msg)
        if log_cb:
            log_cb(msg)

    _emit(f"=== {APP_NAME} ({APP_SHORT}) v{__version__} — TỰ ĐỘNG CÀI ĐẶT CÔNG CỤ & THƯ VIỆN ===")
    result: Dict[str, Any] = {
        "ok": True,
        "dry_run": dry_run,
        "started_utc": sc.now_utc_iso(),
        "python": None,
        "tools": None,
        "ocr_data": None,
        "logs": logs,
    }

    if install_python:
        _emit("\n[1/3] Kiểm tra & cài đặt thư viện Python...")
        py_res = install_python_packages(include_pywebview=include_pywebview, dry_run=dry_run, log_cb=_emit)
        result["python"] = py_res
        if not py_res["ok"]:
            result["ok"] = False

    if install_tools:
        _emit("\n[2/3] Kiểm tra & cài đặt công cụ hệ thống (gh, git, 7z, ffmpeg, tesseract, poppler)...")
        tl_res = install_system_tools(dry_run=dry_run, log_cb=_emit)
        result["tools"] = tl_res
        if not tl_res["ok"]:
            result["ok"] = False

    if install_ocr_data:
        _emit("\n[3/3] Kiểm tra & tải dữ liệu OCR Tiếng Việt + Tiếng Anh (vie.traineddata, eng.traineddata)...")
        if dry_run:
            _emit(f"  [CHẠY THỬ] Tải vie.traineddata & eng.traineddata vào {shared_tessdata_dir()}")
            result["ocr_data"] = {"ok": True, "tessdata_dir": str(shared_tessdata_dir()), "downloaded": ["vie", "eng"], "skipped": [], "errors": []}
        else:
            ocr_res = download_ocr_traineddata(("vie", "eng"), log_cb=_emit)
            result["ocr_data"] = ocr_res
            if not ocr_res["ok"]:
                result["ok"] = False

    result["finished_utc"] = sc.now_utc_iso()
    _emit("\n=== HOÀN TẤT TỰ ĐỘNG CÀI ĐẶT ===")
    return result


def start_setup_job(
    *,
    install_python: bool = True,
    install_tools: bool = True,
    install_ocr_data: bool = True,
    include_pywebview: bool = False,
    dry_run: bool = False,
) -> Tuple[int, Dict[str, Any]]:
    """Khởi chạy nền tác vụ tự động cài đặt để Web/Desktop UI theo dõi trực tiếp theo thời gian thực."""
    global _LAST_SETUP_JOB_ID
    with _SETUP_LOCK:
        for existing in _SETUP_JOBS.values():
            if existing["status"] == "running":
                return 200, dict(existing)
        jid = uuid.uuid4().hex[:10]
        job: Dict[str, Any] = {
            "id": jid,
            "status": "running",
            "started_utc": sc.now_utc_iso(),
            "finished_utc": "",
            "ok": None,
            "logs": [],
            "result": None,
        }
        _SETUP_JOBS[jid] = job
        _LAST_SETUP_JOB_ID = jid

    def _cb(line: str) -> None:
        with _SETUP_LOCK:
            _SETUP_JOBS[jid]["logs"].append(line)

    def _worker() -> None:
        try:
            res = run_auto_setup(
                install_python=install_python,
                install_tools=install_tools,
                install_ocr_data=install_ocr_data,
                include_pywebview=include_pywebview,
                dry_run=dry_run,
                log_cb=_cb,
            )
            with _SETUP_LOCK:
                _SETUP_JOBS[jid].update({
                    "status": "done" if res.get("ok") else "done_with_warnings",
                    "ok": bool(res.get("ok")),
                    "finished_utc": sc.now_utc_iso(),
                    "result": res,
                })
        except Exception as exc:
            with _SETUP_LOCK:
                _SETUP_JOBS[jid]["logs"].append(f"[LỖI] {exc}")
                _SETUP_JOBS[jid].update({
                    "status": "failed",
                    "ok": False,
                    "finished_utc": sc.now_utc_iso(),
                })

    threading.Thread(target=_worker, daemon=True).start()
    return 200, dict(job)


def get_setup_job(job_id: str) -> Optional[Dict[str, Any]]:
    with _SETUP_LOCK:
        j = _SETUP_JOBS.get(job_id)
        if not j:
            return None
        out = dict(j)
        out["logs"] = list(j["logs"])
        return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="kas setup",
        description=f"Tự động cài đặt công cụ hệ thống, thư viện Python & OCR tiếng Việt cho {APP_NAME} ({APP_SHORT}).",
    )
    ap.add_argument("--python", action="store_true", help="Chỉ cài thư viện Python còn thiếu")
    ap.add_argument("--tools", action="store_true", help="Chỉ cài công cụ hệ thống (gh, git, 7z, ffmpeg, tesseract, poppler)")
    ap.add_argument("--ocr-data", action="store_true", help="Chỉ tải dữ liệu OCR tiếng Việt & tiếng Anh (vie+eng)")
    ap.add_argument("--include-pywebview", action="store_true", help="Cài thêm pywebview (không cần trên Windows 11 SAC)")
    ap.add_argument("--chay-thu", "--dry-run", action="store_true", dest="dry_run", help="Chỉ hiển thị lệnh sẽ chạy, không cài thật")
    ap.add_argument("--json", action="store_true", dest="as_json", help="Xuất kết quả dạng JSON")
    args = ap.parse_args(argv)

    any_specific = args.python or args.tools or args.ocr_data
    do_py = args.python if any_specific else True
    do_tools = args.tools if any_specific else True
    do_ocr = args.ocr_data if any_specific else True

    res = run_auto_setup(
        install_python=do_py,
        install_tools=do_tools,
        install_ocr_data=do_ocr,
        include_pywebview=args.include_pywebview,
        dry_run=args.dry_run,
        log_cb=(None if args.as_json else sc.log),
    )
    if args.as_json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
