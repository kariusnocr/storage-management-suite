#!/usr/bin/env python3
"""Trình chuẩn bị & đóng gói APK Android gốc (`kas-android.apk`) cho Karius Academic System (KAS) v1.7.0.

Chức năng:
1. Kiểm tra tính toàn vẹn của dự án Android Gradle (`packaging/android/`).
2. Đồng bộ gói Python `src/karius_academic_system` vào `packaging/android/app/src/main/python/karius_academic_system`
   để Chaquopy đóng gói trực tiếp vào APK.
3. Gọi `gradle assembleRelease` (khi không truyền `--stage-only`) và xuất tệp `dist/kas-android.apk` đã ký số.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parent.parent
ANDROID_DIR = REPO_ROOT / "packaging" / "android"
SRC_PKG_DIR = REPO_ROOT / "src" / "karius_academic_system"
STAGED_PYTHON_DIR = ANDROID_DIR / "app" / "src" / "main" / "python"
STAGED_PKG_DIR = STAGED_PYTHON_DIR / "karius_academic_system"

REQUIRED_ANDROID_FILES = [
    ANDROID_DIR / "settings.gradle",
    ANDROID_DIR / "build.gradle",
    ANDROID_DIR / "gradle.properties",
    ANDROID_DIR / "app" / "build.gradle",
    ANDROID_DIR / "app" / "src" / "main" / "AndroidManifest.xml",
    ANDROID_DIR / "app" / "src" / "main" / "java" / "io" / "github" / "kariusnocr" / "kas" / "MainActivity.java",
    ANDROID_DIR / "app" / "src" / "main" / "python" / "kas_android_boot.py",
    ANDROID_DIR / "install_android_termux.sh",
]


def validate_android_project() -> None:
    missing: List[str] = [str(p.relative_to(REPO_ROOT)) for p in REQUIRED_ANDROID_FILES if not p.exists()]
    if missing:
        raise FileNotFoundError(f"Thiếu tệp cấu hình dự án Android: {', '.join(missing)}")


def stage_python_sources() -> Path:
    """Sao chép sạch `src/karius_academic_system` vào `packaging/android/app/src/main/python/karius_academic_system`."""
    validate_android_project()
    if STAGED_PKG_DIR.exists():
        shutil.rmtree(STAGED_PKG_DIR)

    def _ignore(directory: str, contents: List[str]) -> List[str]:
        return [
            c
            for c in contents
            if c == "__pycache__" or c.endswith((".pyc", ".pyo", ".egg-info"))
        ]

    shutil.copytree(SRC_PKG_DIR, STAGED_PKG_DIR, ignore=_ignore)
    return STAGED_PKG_DIR


def build_apk(out_apk: Path, *, clean_staged: bool = True) -> Path:
    stage_python_sources()
    gradle_bin = shutil.which("gradle")
    gradlew = ANDROID_DIR / ("gradlew.bat" if sys.platform.startswith("win") else "gradlew")
    cmd = [str(gradlew) if gradlew.exists() else (gradle_bin or "gradle"), "assembleRelease", "--no-daemon"]

    print(f"[ANDROID] Đang biên dịch APK bằng lệnh: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, cwd=str(ANDROID_DIR), check=True)
        outputs_dir = ANDROID_DIR / "app" / "build" / "outputs" / "apk" / "release"
        apks = sorted(outputs_dir.glob("*.apk"))
        if not apks:
            raise RuntimeError(f"Không tìm thấy tệp APK đầu ra trong {outputs_dir}")
        out_apk.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(apks[0], out_apk)
        print(f"[ANDROID] Đã tạo gói APK cài đặt thành công: {out_apk} ({out_apk.stat().st_size:,} bytes)")
        return out_apk
    finally:
        if clean_staged and STAGED_PKG_DIR.exists():
            shutil.rmtree(STAGED_PKG_DIR, ignore_errors=True)


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Đóng gói ứng dụng Android gốc `kas-android.apk` cho KAS.")
    ap.add_argument(
        "--out",
        default=str(REPO_ROOT / "dist" / "kas-android.apk"),
        help="Đường dẫn tệp APK đầu ra (mặc định: dist/kas-android.apk)",
    )
    ap.add_argument(
        "--stage-only",
        action="store_true",
        help="Chỉ kiểm tra cấu trúc dự án Android và đồng bộ nguồn Python vào Chaquopy (không gọi Gradle)",
    )
    ap.add_argument(
        "--clean-staged",
        action="store_true",
        help="Dọn thư mục Python tạm sau khi kiểm tra --stage-only",
    )
    args = ap.parse_args(argv)

    if args.stage_only:
        staged = stage_python_sources()
        print(f"[ANDROID] Đã kiểm chứng cấu trúc & đồng bộ gói Python tại: {staged}")
        if args.clean_staged and staged.exists():
            shutil.rmtree(staged, ignore_errors=True)
        return 0

    build_apk(Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
