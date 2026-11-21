"""Theo dõi biến động kho dữ liệu định kỳ & cảnh báo tức thì Chuẩn V6 / Danh Mục V7 (`kas watch`)."""

from __future__ import annotations

import argparse
import time
from typing import Any, Dict, List, Optional

from karius_academic_system import core as sc


def poll_once(
    drive: Any,
    since_iso: str,
    branch: Optional[str] = None,
    auto_audit: bool = True,
) -> Dict[str, Any]:
    """Dò các mục thay đổi trên Drive sau mốc `since_iso` và kiểm tra nhanh Chuẩn V6."""
    items = drive.search(modified_after=since_iso, max_results=200) or []
    violations: List[Dict[str, Any]] = []
    max_mod = since_iso
    for it in items:
        mt = it.get("modifiedTime") or ""
        if mt > max_mod:
            max_mod = mt
        if not auto_audit:
            continue
        is_f = it.get("mimeType") == sc.FOLDER_MIME
        name = it.get("name", "")
        found = sc.check_folder_name(name, "") if is_f else sc.check_file_name(name, it.get("mimeType", ""), "")
        for sev, code, desc in found:
            if sev in {"LỖI", "CẢNH BÁO"}:
                violations.append({
                    "id": it.get("id", ""),
                    "name": name,
                    "severity": sev,
                    "code": code,
                    "description": desc,
                    "modifiedTime": mt,
                })
    return {
        "checked_utc": sc.now_utc_iso(),
        "since_iso": since_iso,
        "next_cursor_iso": max_mod,
        "changed_count": len(items),
        "violations": violations,
    }


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Theo dõi biến động kho [A] STORAGE và cảnh báo Chuẩn V6.")
    ap.add_argument("--chu-ki", type=int, default=300, help="Chu kì kiểm tra theo giây (mặc định 300s)")
    ap.add_argument("--mot-lan", action="store_true", help="Chỉ chạy 1 lượt rồi thoát")
    ap.add_argument("--tu-moc", help="Mốc thời gian ISO UTC bắt đầu dò (mặc định: hiện tại)")
    ap.add_argument("--nhanh", help="Giới hạn nhánh")
    args = ap.parse_args(argv)

    drive = sc.create_drive()
    cursor = args.tu_moc or sc.now_utc_iso()
    branch = sc.normalize_branch(args.nhanh)
    sc.log(f"Đang theo dõi biến động kho từ mốc {cursor} (chu kì={args.chu_ki}s)...")

    while True:
        res = poll_once(drive, cursor, branch=branch)
        cursor = res["next_cursor_iso"]
        if res["changed_count"]:
            sc.log(f"[{res['checked_utc']}] Phát hiện {res['changed_count']} mục thay đổi | {len(res['violations'])} cảnh báo Chuẩn V6")
            for v in res["violations"][:15]:
                sc.log(f"  [{v['severity']}] {v['code']}: {v['name']} — {v['description']}")
        else:
            sc.log(f"[{res['checked_utc']}] Không có biến động mới.")
        if args.mot_lan:
            return 0
        time.sleep(max(10, args.chu_ki))


if __name__ == "__main__":
    raise SystemExit(main())
