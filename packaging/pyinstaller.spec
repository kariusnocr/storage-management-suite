# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec đóng gói Karius Academic System (KAS) v1.0 thành ứng dụng độc lập (Windows/macOS/Linux)."""

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parent
SRC = ROOT / "src"
WIN_VERSION_FILE = ROOT / "packaging" / "windows_version_info.txt"

hiddenimports = (
    collect_submodules("karius_academic_system")
    + [
        "uvicorn.logging",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on",
        "openpyxl",
    ]
)

datas = [
    (str(SRC / "karius_academic_system" / "data" / "kas_config.json"), "karius_academic_system/data"),
    (str(SRC / "karius_academic_system" / "web" / "static" / "index.html"), "karius_academic_system/web/static"),
]

a = Analysis(
    [str(SRC / "karius_academic_system" / "__main__.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "scipy"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="kas",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    version=str(WIN_VERSION_FILE) if sys.platform == "win32" and WIN_VERSION_FILE.exists() else None,
    disable_windowed_traceback=False,
)
