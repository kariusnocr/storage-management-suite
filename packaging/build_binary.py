#!/usr/bin/env python3
"""Kịch bản trợ giúp đóng gói binary độc lập (CLI + Web UI + Desktop) qua PyInstaller."""

from __future__ import annotations

import argparse
import hashlib
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description="Đóng gói nhị phân độc lập Storage Management Suite v4.0.")
    ap.add_argument("--mode", choices=["cli", "desktop"], default="cli", help="Chế độ đóng gói: cli hoặc desktop (pywebview)")
    args = ap.parse_args()

    if not shutil.which("pyinstaller"):
        print("Thiếu PyInstaller. Cài bằng: pip install pyinstaller", file=sys.stderr)
        return 1

    dist_dir = ROOT / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    spec = ROOT / "packaging" / "pyinstaller.spec"

    cmd = ["pyinstaller", "--clean", "--noconfirm", str(spec)]
    if args.mode == "desktop":
        entry = ROOT / "src" / "storage_suite" / "web" / "desktop.py"
        sep = ";" if platform.system() == "Windows" else ":"
        cmd = [
            "pyinstaller",
            "--clean",
            "--noconfirm",
            "--onefile",
            "--windowed",
            "--name", "astorage-desktop",
            "--paths", str(ROOT / "src"),
            "--add-data", f"{ROOT / 'src/storage_suite/data/storage_config.json'}{sep}storage_suite/data",
            "--add-data", f"{ROOT / 'src/storage_suite/web/static/index.html'}{sep}storage_suite/web/static",
            "--collect-submodules", "storage_suite",
            str(entry),
        ]

    print("Đang chạy:", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(ROOT))
    if proc.returncode != 0:
        return proc.returncode

    sys_tag = f"{platform.system().lower()}-{platform.machine().lower()}"
    for art in sorted(dist_dir.glob("astorage*")):
        if art.is_file() and not art.name.endswith(".sha256"):
            digest = sha256_file(art)
            print(f"Đã tạo ({sys_tag}): {art.name} | SHA-256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
