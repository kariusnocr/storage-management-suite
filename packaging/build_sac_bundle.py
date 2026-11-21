#!/usr/bin/env python3
"""Đóng gói gói Windows an toàn với Smart App Control (`astorage-windows-sac-safe.zip`)."""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def build_sac_bundle(dist_dir: Path, out_zip: Path) -> Path:
    win_dir = ROOT / "packaging" / "windows"
    wheels = sorted(dist_dir.glob("storage_management_suite-*.whl"))
    if not wheels:
        raise FileNotFoundError(f"Không tìm thấy tệp .whl trong {dist_dir}. Hãy build wheel trước.")
    wheel = wheels[-1]

    out_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(wheel, arcname=wheel.name)
        for name in ("install_windows_sac_safe.ps1", "Chay_Ung_Dung_Desktop.cmd", "README_WINDOWS_SAC.txt"):
            src = win_dir / name
            if src.exists():
                zf.write(src, arcname=name)
    return out_zip


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    ap = argparse.ArgumentParser(description="Đóng gói bộ cài Windows an toàn Smart App Control (ZIP).")
    ap.add_argument("--dist-dir", default=str(ROOT / "dist"), help="Thư mục chứa tệp .whl")
    ap.add_argument("--out", default=str(ROOT / "dist" / "astorage-windows-sac-safe.zip"), help="Đường dẫn tệp ZIP đầu ra")
    args = ap.parse_args()
    out = build_sac_bundle(Path(args.dist_dir), Path(args.out))
    print(f"Đã tạo gói Windows SAC-safe: {out} ({out.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
