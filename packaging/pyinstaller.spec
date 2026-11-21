# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec đóng gói Storage Management Suite v4.0 thành ứng dụng độc lập (Windows/macOS/Linux)."""

from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parent
SRC = ROOT / "src"

hiddenimports = (
    collect_submodules("storage_suite")
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
    (str(SRC / "storage_suite" / "data" / "storage_config.json"), "storage_suite/data"),
    (str(SRC / "storage_suite" / "web" / "static" / "index.html"), "storage_suite/web/static"),
]

a = Analysis(
    [str(SRC / "storage_suite" / "__main__.py")],
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
    name="astorage",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
)
