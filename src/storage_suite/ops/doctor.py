"""Trình chẩn đoán sức khỏe phần mềm & môi trường (`astorage doctor`)."""

from __future__ import annotations

import argparse
import importlib
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

from storage_suite import __version__
from storage_suite import core as sc


def _check_python_pkg(mod_name: str, pip_name: str, required: bool = False) -> Dict[str, Any]:
    try:
        mod = importlib.import_module(mod_name)
        ver = getattr(mod, "__version__", "installed")
        return {"name": pip_name, "ok": True, "version": str(ver), "required": required}
    except ImportError:
        return {"name": pip_name, "ok": False, "version": "", "required": required}


def _check_cli_tool(bin_name: str, purpose: str) -> Dict[str, Any]:
    path = shutil.which(bin_name) or ""
    return {"name": bin_name, "ok": bool(path), "path": path, "purpose": purpose}


def _check_fonts() -> Dict[str, Any]:
    cands = [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/Library/Fonts/Arial Unicode.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ]
    found = [str(p) for p in cands if p.exists()]
    return {"ok": bool(found), "paths": found}


def _check_gh() -> Dict[str, Any]:
    gh = shutil.which("gh") or ""
    if not gh:
        return {"available": False, "authenticated": False, "path": ""}
    try:
        proc = subprocess.run([gh, "auth", "status"], capture_output=True, text=True, timeout=10)
        return {"available": True, "authenticated": proc.returncode == 0, "path": gh}
    except Exception:
        return {"available": True, "authenticated": False, "path": gh}


def run_doctor() -> Dict[str, Any]:
    """Chẩn đoán toàn bộ phụ thuộc Python, công cụ đa phương tiện, OCR, Drive backends, GitHub và SQLite."""
    py_pkgs = [
        _check_python_pkg("openpyxl", "openpyxl", required=True),
        _check_python_pkg("PIL", "Pillow", required=False),
        _check_python_pkg("numpy", "numpy", required=False),
        _check_python_pkg("fastapi", "fastapi", required=False),
        _check_python_pkg("uvicorn", "uvicorn", required=False),
        _check_python_pkg("googleapiclient", "google-api-python-client", required=False),
        _check_python_pkg("google_auth_oauthlib", "google-auth-oauthlib", required=False),
        _check_python_pkg("webview", "pywebview", required=False),
    ]
    cli_tools = [
        _check_cli_tool("ffmpeg", "Xử lý âm thanh/video"),
        _check_cli_tool("ffprobe", "Đọc metadata đa phương tiện"),
        _check_cli_tool("tesseract", "Nhận dạng chữ OCR"),
        _check_cli_tool("pdftotext", "Đọc văn bản PDF"),
        _check_cli_tool("pdfinfo", "Đọc siêu dữ liệu PDF"),
        _check_cli_tool("pdftoppm", "Chuyển trang PDF sang ảnh OCR"),
        _check_cli_tool("7z", "Kiểm tra tệp nén ZIP/RAR/7Z"),
        _check_cli_tool("git", "Quản lý phiên bản Git"),
    ]

    ocr_lang, ocr_prefix = sc.resolve_tesseract_lang(force_refresh=True)
    drive_info = sc.detect_drive_backends()
    gh_info = _check_gh()
    fonts_info = _check_fonts()

    db_file = sc.db_path()
    idx_file = sc.index_path()
    db_stats: Dict[str, Any] = {"db_exists": db_file.exists(), "json_exists": idx_file.exists()}
    if db_file.exists():
        try:
            with sc.StorageDB(db_file) as db:
                st = db.stats_summary()
                db_stats.update({
                    "folders": st["total_folders"],
                    "files": st["total_files"],
                    "total_size": sc.human_size(st["total_bytes"]),
                    "db_size": sc.human_size(st["db_size_bytes"]),
                    "last_import_utc": st["last_import_utc"],
                })
        except Exception as exc:
            db_stats["error"] = str(exc)

    req_ok = all(p["ok"] for p in py_pkgs if p["required"])
    drive_ok = drive_info["selected"] != "none"
    overall_ok = req_ok and drive_ok

    return {
        "version": __version__,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "data_dir": str(sc.data_dir()),
        "overall_ok": overall_ok,
        "python_packages": py_pkgs,
        "cli_tools": cli_tools,
        "ocr": {
            "ok": bool(ocr_lang),
            "lang": ocr_lang,
            "vietnamese_ready": "vie" in (ocr_lang or ""),
            "tessdata_prefix": ocr_prefix or "",
        },
        "fonts": fonts_info,
        "drive": drive_info,
        "github": gh_info,
        "storage_db": db_stats,
    }


def format_doctor_report(res: Dict[str, Any]) -> str:
    lines = [
        "==========================================================================",
        f"🩺 STORAGE MANAGEMENT SUITE v{res['version']} — CHẨN ĐOÁN HỆ THỐNG (DOCTOR)",
        "==========================================================================",
        f"• Python / Hệ điều hành : {res['python']} ({res['platform']})",
        f"• Thư mục dữ liệu       : {res['data_dir']}",
        f"• Kết nối Google Drive  : backend={res['drive']['selected']} (ưu tiên={res['drive']['preference']})",
        f"   ├─ CLI `gdrive`      : {'OK — ' + res['drive']['cli']['bin'] if res['drive']['cli']['available'] else 'Không có'}",
        f"   └─ API OAuth 2.0     : libs={'OK' if res['drive']['api']['libs_installed'] else 'Chưa cài'} | token={'Đã đăng nhập' if res['drive']['api']['authenticated'] else 'Chưa đăng nhập'}",
        f"• GitHub CLI (`gh`)     : {'Đã đăng nhập' if res['github']['authenticated'] else ('Có CLI nhưng chưa đăng nhập' if res['github']['available'] else 'Chưa cài')}",
        f"• OCR Tesseract         : {res['ocr']['lang'] or 'Chưa cài'} | Tiếng Việt: {'Sẵn sàng' if res['ocr']['vietnamese_ready'] else 'Thiếu vie.traineddata'}",
        f"• Font Unicode          : {'OK' if res['fonts']['ok'] else 'Chưa tìm thấy DejaVu/Arial'}",
    ]
    st = res["storage_db"]
    if st.get("db_exists"):
        lines.append(
            f"• SQLite Store (WAL+FTS): {st.get('folders', 0)} thư mục | {st.get('files', 0)} tệp | "
            f"{st.get('total_size', '0 B')} | DB={st.get('db_size', '0 B')}"
        )
    else:
        lines.append(f"• SQLite Store          : Chưa khởi tạo (JSON={'có' if st.get('json_exists') else 'chưa có'})")

    lines.append("\n📦 Thư viện Python:")
    for p in res["python_packages"]:
        mark = "✓" if p["ok"] else ("✗" if p["required"] else "○")
        tag = "(bắt buộc)" if p["required"] else "(tùy chọn)"
        lines.append(f"  {mark} {p['name']:26s} {p['version'] or 'chưa cài':14s} {tag}")

    lines.append("\n🛠️  Công cụ hệ thống:")
    for t in res["cli_tools"]:
        mark = "✓" if t["ok"] else "○"
        lines.append(f"  {mark} {t['name']:12s} {t['purpose']:34s} {t['path'] or 'chưa cài'}")

    lines.append("==========================================================================")
    lines.append(f"Trạng thái tổng thể: {'SẴN SÀNG ✅' if res['overall_ok'] else 'CẦN BỔ SUNG CẤU HÌNH ⚠️'}")
    return "\n".join(lines)


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Chẩn đoán môi trường Storage Management Suite v4.0.")
    ap.add_argument("--json", action="store_true", dest="as_json", help="Xuất kết quả dạng JSON")
    args = ap.parse_args(argv)
    res = run_doctor()
    if args.as_json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        sc.log(format_doctor_report(res))
    return 0 if res["overall_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
