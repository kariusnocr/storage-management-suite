"""Giao diện dòng lệnh hợp nhất `astorage` / `storage-suite` (v4.0.0)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from storage_suite import __version__
from storage_suite import core as sc
from storage_suite.cli.pipelines import (
    MODULE_MAP,
    build_maintenance_steps,
    build_quick_steps,
    invoke_module_in_process,
    run_pipeline,
)


def _cmd_auth(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(prog="astorage auth", description="Quản lý xác thực Google Drive API (OAuth 2.0) độc lập.")
    ap.add_argument("action", choices=["status", "login", "logout"], help="Thao tác xác thực")
    ap.add_argument("--credentials", help="Đường dẫn tệp OAuth `credentials.json` tải từ Google Cloud Console")
    ap.add_argument("--token", help="Đường dẫn lưu `token.json`")
    ap.add_argument("--port", type=int, default=0, help="Cổng local callback cho OAuth 2.0 (0 = tự động)")
    ap.add_argument("--no-browser", action="store_true", help="Không tự mở trình duyệt")
    ap.add_argument("--json", action="store_true", dest="as_json", help="Xuất JSON")
    args = ap.parse_args(argv)

    if args.action == "status":
        info = sc.detect_drive_backends()
        if args.as_json:
            print(json.dumps(info, ensure_ascii=False, indent=2))
        else:
            sc.log(f"Backend ưu tiên : {info['preference']} | Đang chọn: {info['selected']}")
            sc.log(f"  • CLI gdrive  : {'Sẵn sàng (' + info['cli']['bin'] + ')' if info['cli']['available'] else 'Không có'}")
            api = info["api"]
            sc.log(
                f"  • Drive API   : libs={'OK' if api['libs_installed'] else 'Chưa cài'} | "
                f"credentials={'có' if api['credentials_exists'] else 'chưa có'} ({api['credentials_path']}) | "
                f"token={'đã đăng nhập' if api['authenticated'] else 'chưa đăng nhập'} ({api['token_path']})"
            )
        return 0

    if args.action == "login":
        try:
            tpath = sc.auth_login(
                credentials_file=Path(args.credentials) if args.credentials else None,
                token_file=Path(args.token) if args.token else None,
                port=args.port,
                open_browser=not args.no_browser,
            )
            sc.log(f"Đăng nhập OAuth 2.0 thành công! Đã lưu token tại: {tpath}")
            return 0
        except sc.DriveError as exc:
            sc.log(f"Lỗi đăng nhập: {exc}")
            return 1

    removed = sc.auth_logout(token_file=Path(args.token) if args.token else None)
    sc.log("Đã đăng xuất và xóa token OAuth 2.0 cục bộ." if removed else "Không có token OAuth 2.0 cục bộ nào để xóa.")
    return 0


def _cmd_db(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(prog="astorage db", description="Quản trị cơ sở dữ liệu SQLite (WAL + FTS5).")
    sub = ap.add_subparsers(dest="action", required=True)
    sub.add_parser("sync", help="Đồng bộ `storage_index.json` vào `storage.db` (FTS5)")
    sub.add_parser("stats", help="Xem thống kê tức thì từ `storage.db`")
    p_s = sub.add_parser("search", help="Tìm kiếm toàn văn tức thì (<20 ms) bằng SQLite FTS5")
    p_s.add_argument("query", help="Từ khóa tìm kiếm (có dấu hoặc không dấu)")
    p_s.add_argument("--nhanh", help="Lọc theo nhánh")
    p_s.add_argument("--gioi-han", type=int, default=25, help="Số kết quả tối đa")
    args = ap.parse_args(argv)

    if args.action == "sync":
        data = sc.read_json(sc.index_path())
        if not data:
            sc.log(f"Chưa tìm thấy {sc.index_path()}. Hãy chạy `astorage quet` trước.")
            return 1
        if isinstance(data, dict) and "folders" in data and "meta" in data:
            data = data["folders"]
        with sc.StorageDB() as db:
            res = db.import_index_dict(data)
        sc.log(f"Đã đồng bộ SQLite ({sc.db_path()}): {res['folders']} thư mục, {res['items']} mục (FTS5 sẵn sàng).")
        return 0

    with sc.StorageDB() as db:
        if args.action == "stats":
            st = db.stats_summary()
            sc.log(
                f"SQLite DB: {st['db_path']} ({sc.human_size(st['db_size_bytes'])})\n"
                f"Thư mục: {sc.fmt_int(st['total_folders'])} | Tệp tin: {sc.fmt_int(st['total_files'])} | "
                f"Tổng dung lượng: {sc.human_size(st['total_bytes'])} | Cập nhật: {st['last_import_utc'] or '—'}"
            )
            for b, info in sorted(st["branches"].items()):
                sc.log(f"  - {b:22s}: {info['folders']:5d} thư mục | {info['files']:6d} tệp | {sc.human_size(info['bytes'])}")
            return 0

        branch = sc.normalize_branch(args.nhanh) if args.nhanh else None
        hits = db.search_fts(args.query, branch=branch, limit=args.gioi_han)
        sc.log(f"Tìm thấy {len(hits)} kết quả cho `{args.query}`:")
        for h in hits:
            sc.log(f"  • {h['name']} ({sc.human_size(h['size'])}) — {h['parent_path']}")
        return 0


def _cmd_undo(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(prog="astorage undo", description="Sổ cái hoàn tác hợp nhất (Unified Undo Journal).")
    sub = ap.add_subparsers(dest="action", required=True)
    sub.add_parser("list", help="Liệt kê các lô thao tác gần nhất")
    p_r = sub.add_parser("run", help="Hoàn tác một lô thao tác theo batch_id")
    p_r.add_argument("batch_id", help="Mã lô cần hoàn tác")
    p_r.add_argument("--thuc-thi", action="store_true", help="Thực sự hoàn tác trên Drive (mặc định chạy thử)")
    p_r.add_argument("--dong-y", action="store_true", help="Không hỏi xác nhận")
    args = ap.parse_args(argv)

    with sc.StorageDB() as db:
        if args.action == "list":
            batches = db.list_undo_batches()
            if not batches:
                sc.log("Chưa có lô thao tác nào trong Unified Undo Journal.")
                return 0
            for b in batches:
                st = f"đã hoàn tác {b['undone_at']}" if b["undone_at"] else "có thể hoàn tác"
                sc.log(f"  • {b['batch_id']} | {b['kind']} | {b['action_count']} thao tác | {st} | {b['description']}")
            return 0

        if args.thuc_thi and not sc.confirm(f"Hoàn tác lô `{args.batch_id}` trên Google Drive?", args.dong_y):
            return 0
        drive = sc.create_drive() if args.thuc_thi else None
        res = db.undo_batch(drive, args.batch_id, execute=args.thuc_thi)
        sc.log(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res.get("ok") else 1


def _cmd_tests() -> int:
    from storage_suite.sync.github_sync import default_repo_root

    root = default_repo_root()
    test_dir = root / "tests"
    if not test_dir.exists():
        sc.log(f"Không tìm thấy thư mục kiểm thử tại {test_dir}.")
        return 1
    proc = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", str(test_dir), "-v"], cwd=str(root))
    return proc.returncode


def main(argv: Optional[List[str]] = None) -> int:
    all_cmds = [
        *MODULE_MAP.keys(),
        "danh-muc-chuan",
        "auth",
        "db",
        "undo",
        "ui",
        "desktop",
        "kiem-thu",
        "quy-trinh-nhanh",
        "bao-tri-dinh-ki",
        "version",
    ]
    ap = argparse.ArgumentParser(
        prog="astorage",
        description=f"Storage Management Suite v{__version__} — Phần mềm quản trị kho [A] STORAGE.",
    )
    ap.add_argument("lenh", choices=all_cmds, help="Lệnh hoặc quy trình cần chạy")
    ap.add_argument("--thuc-thi", action="store_true", help="Cho phép ghi lên Drive ở quy trình phối hợp")
    ap.add_argument("--dong-y", action="store_true", help="Không hỏi xác nhận")
    ap.add_argument("--tai-len", action="store_true", help="Tải báo cáo lên [00] TỔNG QUAN/[02] NHẬT KÍ")
    ap.add_argument("--nhanh", help="Giới hạn phạm vi nhánh")
    ap.add_argument("--bo-qua-quet", action="store_true", help="Bỏ qua bước [02] trong `quy-trinh-nhanh`")
    ap.add_argument("--tang-cuong", action="store_true", help="Dùng `--tang-cuong` cho [02] trong `bao-tri-dinh-ki`")

    raw_args = list(sys.argv[1:] if argv is None else argv)
    if not raw_args or raw_args[0] in {"-h", "--help"}:
        ap.print_help()
        return 0

    cmd = raw_args[0]
    rest = raw_args[1:]

    if cmd == "version":
        sc.log(sc.describe())
        return 0
    if cmd == "auth":
        return _cmd_auth(rest)
    if cmd == "db":
        return _cmd_db(rest)
    if cmd == "undo":
        return _cmd_undo(rest)
    if cmd == "danh-muc-chuan":
        return invoke_module_in_process("danh-muc", ["--chuan-hoa-v7", *rest])
    if cmd == "ui":
        from storage_suite.web.app import run_web_server

        return run_web_server(rest)
    if cmd == "desktop":
        from storage_suite.web.desktop import main as desktop_main

        return desktop_main(rest)
    if cmd == "kiem-thu":
        return _cmd_tests()

    if cmd in MODULE_MAP:
        return invoke_module_in_process(cmd, rest)

    args = ap.parse_args(raw_args)
    if args.lenh == "quy-trinh-nhanh":
        steps = build_quick_steps(args.thuc_thi, args.dong_y, args.tai_len, args.nhanh, args.bo_qua_quet)
        return run_pipeline("quy-trinh-nhanh", steps)
    if args.lenh == "bao-tri-dinh-ki":
        steps = build_maintenance_steps(args.thuc_thi, args.dong_y, args.tai_len, args.nhanh, args.tang_cuong)
        return run_pipeline("bao-tri-dinh-ki", steps)

    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
