#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vỏ bọc tương thích cho `[05] DANH MỤC HỆ THỐNG/sheet_engine.py` (v2.0).
Giữ nguyên File ID tương ứng với trình cập nhật cũ và chuyển tiếp toàn bộ lệnh sang `sheet_engine.main()`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import sheet_engine  # noqa: E402

main = sheet_engine.main
refresh_key_sheets = sheet_engine.refresh_key_sheets
build_xlsx_for_path = sheet_engine.build_xlsx_for_path


if __name__ == "__main__":
    main()
