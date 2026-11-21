"""Giao diện dòng lệnh hợp nhất `kas` — Karius Academic System (KAS) v5.0.0."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from karius_academic_system import APP_NAME, APP_SHORT, __version__
from karius_academic_system import core as sc
from karius_academic_system.cli.pipelines import (
    MODULE_MAP,
    build_maintenance_steps,
    build_quick_steps,
    invoke_module_in_process,
    run_pipeline,
)


def _cmd_vault(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(
        prog="kas vault",
        description="Quản lý đa kho dữ liệu (thư mục cục bộ / ổ rời / NAS / mọi kho Google Drive).",
    )
    sub = ap.add_subparsers(dest="action", required=True)

    p_ls = sub.add_parser("list", help="Liệt kê mọi kho dữ liệu đã kết nối")
    p_ls.add_argument("--json", action="store_true", dest="as_json", help="Xuất JSON")

    p_add = sub.add_parser("add", help="Kết nối một kho mới (thư mục cục bộ hoặc URL/ID Google Drive)")
    p_add.add_argument("slug", nargs="?", help="Mã ngắn của kho (bỏ trống sẽ tự sinh từ tên)")
    p_add.add_argument("--nguon", "--source", required=True, dest="source", help="Đường dẫn thư mục trên máy hoặc URL/Folder ID Google Drive")
    p_add.add_argument("--ten", "--name", dest="name", help="Tên hiển thị của kho")
    p_add.add_argument("--backend", choices=["auto", "local", "gdrive-api", "gdrive-cli"], default="auto", help="Trình điều khiển kết nối")
    p_add.add_argument("--che-do", "--mode", dest="mode", choices=["auto", "academic_v7", "general"], default="auto", help="Chế độ chuẩn hóa cấu trúc")
    p_add.add_argument("--khong-kich-hoat", action="store_true", help="Không đặt kho vừa thêm làm kho mặc định")

    p_use = sub.add_parser("use", help="Chuyển kho hoạt động mặc định")
    p_use.add_argument("slug", help="Mã kho cần chuyển sang")

    p_info = sub.add_parser("info", help="Xem chi tiết kho hiện hành hoặc một kho cụ thể")
    p_info.add_argument("slug", nargs="?", help="Mã kho (mặc định kho đang kích hoạt)")
    p_info.add_argument("--json", action="store_true", dest="as_json", help="Xuất JSON")

    p_rm = sub.add_parser("remove", help="Gỡ kho khỏi danh sách quản lý KAS (không xóa tệp gốc)")
    p_rm.add_argument("slug", help="Mã kho cần gỡ")

    p_init = sub.add_parser("init-structure", help="Khởi tạo khung thư mục Chuẩn KAS ([00] TỔNG QUAN, [01] DANH SÁCH, [07] KIỂM TRA)")
    p_init.add_argument("--thuc-thi", action="store_true", help="Tạo thư mục thật (mặc định chạy thử)")
    p_init.add_argument("--dong-y", action="store_true", help="Không hỏi xác nhận")

    args = ap.parse_args(argv)
    reg = sc.get_vault_registry()

    if args.action == "list":
        vaults = reg.list_vaults()
        act = sc.active_vault()
        act_slug = act.slug if act else reg.active_slug
        if args.as_json:
            print(json.dumps({"active": act_slug, "registry": str(reg.path), "vaults": [v.to_dict() for v in vaults]}, ensure_ascii=False, indent=2))
            return 0
        if not vaults:
            sc.log(f"Chưa có kho nào trong {reg.path}.")
            sc.log("Hãy kết nối kho đầu tiên bằng:")
            sc.log("  kas vault add tai-lieu --nguon /duong/dan/thu/muc")
            sc.log("  kas vault add drive-hoc-thuat --nguon https://drive.google.com/drive/folders/<FOLDER_ID>")
            return 0
        for v in vaults:
            mark = "*" if v.slug == act_slug else " "
            sc.log(
                f" {mark} {v.slug:20s} | {v.name} | {v.source_kind}:{v.root} | "
                f"backend={v.effective_backend()} | chế độ={v.effective_mode()}"
            )
        return 0

    if args.action == "add":
        kind, norm_root = sc.detect_source_kind(args.source)
        display_name = args.name
        if kind == "gdrive" and not display_name:
            try:
                drv = sc.create_backend(backend=None if args.backend == "auto" else args.backend)
                info = drv.info(norm_root)
                if info and info.get("name"):
                    display_name = str(info["name"])
            except Exception:
                pass
        vc = reg.add_vault(
            args.source,
            slug=args.slug,
            name=display_name,
            backend=args.backend,
            mode=args.mode,
            activate=not args.khong_kich_hoat,
        )
        if not args.khong_kich_hoat:
            sc.activate_vault(vc.slug, persist=True)
        sc.log(f"Đã kết nối kho `{vc.slug}` ('{vc.name}') | nguồn={vc.source_kind}:{vc.root} | chế độ={vc.effective_mode()}")
        sc.log(f"Sổ đăng ký: {reg.path} | Quét chỉ mục ngay bằng: kas --kho {vc.slug} quet")
        return 0

    if args.action == "use":
        try:
            vc = sc.activate_vault(args.slug, persist=True)
        except KeyError as exc:
            sc.log(str(exc))
            return 1
        sc.log(f"Đã chuyển sang kho mặc định: `{vc.slug}` ('{vc.name}' | {vc.source_kind}:{vc.root})")
        return 0

    if args.action == "info":
        vc = reg.get_vault(args.slug) if args.slug else sc.active_vault()
        if not vc:
            sc.log("Không tìm thấy kho tương ứng. Dùng `kas vault list` để xem danh sách.")
            return 1
        if args.as_json:
            print(json.dumps(vc.to_dict(), ensure_ascii=False, indent=2))
        else:
            sc.log(f"Kho      : {vc.slug} ({vc.name})")
            sc.log(f"Nguồn    : {vc.source_kind} → {vc.root}")
            sc.log(f"Backend  : {vc.effective_backend()} (cấu hình: {vc.backend})")
            sc.log(f"Chế độ   : {vc.effective_mode()} (cấu hình: {vc.mode}, phát hiện: {vc.detected_mode or 'chưa quét'})")
            sc.log(f"Quét cuối: {vc.last_scan_utc or 'chưa quét'}")
            sc.log(f"Dữ liệu  : {sc.data_dir()}")
        return 0

    if args.action == "remove":
        ok = reg.remove_vault(args.slug)
        if not ok:
            sc.log(f"Không tìm thấy kho `{args.slug}`.")
            return 1
        sc.reload_config()
        sc.log(f"Đã gỡ kho `{args.slug}` khỏi danh sách quản lý KAS (dữ liệu gốc vẫn nguyên vẹn).")
        return 0

    if args.action == "init-structure":
        if not sc.ROOT_ID:
            sc.log("Chưa chọn kho dữ liệu. Dùng `kas vault add` hoặc `kas vault use <slug>` trước.")
            return 1
        plan = [
            (sc.TONG_QUAN_FOLDER, sc.ROOT_ID),
            (f"{sc.TONG_QUAN_FOLDER}/{sc.DANH_SACH_FOLDER}", None),
            (f"{sc.TONG_QUAN_FOLDER}/[02] NHẬT KÍ", None),
            (sc.QUARANTINE_FOLDER, sc.ROOT_ID),
        ]
        if not args.thuc_thi:
            sc.log(f"[Chạy thử] Sẽ đảm bảo khung Chuẩn KAS V7 trong `{sc.ROOT_NAME}`:")
            for nm, _ in plan:
                sc.log(f"  • {nm}")
            sc.log("Thêm `--thuc-thi --dong-y` để tạo thư mục.")
            return 0
        if not sc.confirm(f"Khởi tạo khung thư mục Chuẩn KAS trong `{sc.ROOT_NAME}`?", args.dong_y):
            return 0
        drv = sc.create_backend()
        tq_id = drv.ensure_folder(sc.TONG_QUAN_FOLDER, sc.ROOT_ID)
        ds_id = drv.ensure_folder(sc.DANH_SACH_FOLDER, tq_id)
        nk_id = drv.ensure_folder("[02] NHẬT KÍ", tq_id)
        qt_id = drv.ensure_folder(sc.QUARANTINE_FOLDER, sc.ROOT_ID)
        vc = sc.active_vault()
        if vc is not None:
            merged = dict(vc.known_ids)
            merged.update({
                sc.TONG_QUAN_FOLDER: tq_id,
                f"{sc.TONG_QUAN_FOLDER}/{sc.DANH_SACH_FOLDER}": ds_id,
                f"{sc.TONG_QUAN_FOLDER}/[02] NHẬT KÍ": nk_id,
                sc.QUARANTINE_FOLDER: qt_id,
            })
            reg.update_vault(vc.slug, known_ids=merged, mode="academic_v7", detected_mode="academic_v7")
            sc.reload_config(vc.slug)
        sc.log(f"Đã khởi tạo khung Chuẩn KAS V7 trong `{sc.ROOT_NAME}` (chế độ: academic_v7).")
        return 0

    return 1


def _cmd_auth(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(prog="kas auth", description="Quản lý xác thực Google Drive API (OAuth 2.0) độc lập.")
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
            sc.log(f"  • Local FS    : Sẵn sàng ({info['local']['root'] or 'mọi thư mục trên máy'})")
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

    if args.action == "logout":
        removed = sc.auth_logout(Path(args.token) if args.token else None)
        sc.log("Đã xóa token OAuth 2.0." if removed else "Không có token OAuth 2.0 nào để xóa.")
        return 0
    return 1


def _cmd_db(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(prog="kas db", description="Quản lý cơ sở dữ liệu SQLite (WAL + FTS5) của kho đang chọn.")
    sub = ap.add_subparsers(dest="action", required=True)
    sub.add_parser("sync", help="Đồng bộ storage_index.json vào SQLite (kas.db)")
    sub.add_parser("stats", help="Xem thống kê tức thời từ SQLite")
    p_search = sub.add_parser("search", help="Tìm kiếm toàn văn FTS5 (<20 ms)")
    p_search.add_argument("query", help="Từ khóa tìm kiếm (có dấu hoặc không dấu)")
    p_search.add_argument("--nhanh", help="Giới hạn trong một nhánh")
    p_search.add_argument("--gioi-han", type=int, default=30, help="Số kết quả tối đa")
    args = ap.parse_args(argv)

    with sc.StorageDB() as db:
        if args.action == "sync":
            idx = sc.read_json(sc.index_path(), {})
            if not idx:
                sc.log(f"Không tìm thấy chỉ mục JSON tại {sc.index_path()}. Hãy chạy `kas quet` trước.")
                return 1
            counts = db.import_index_dict(idx)
            sc.log(f"Đã đồng bộ SQLite ({db.path}): {sc.fmt_int(counts['folders'])} thư mục, {sc.fmt_int(counts['items'])} mục.")
            return 0
        if args.action == "stats":
            st = db.stats_summary()
            sc.log(f"SQLite DB: {st['db_path']} ({sc.human_size(st['db_size_bytes'])})")
            sc.log(
                f"Thư mục: {sc.fmt_int(st['total_folders'])} | Tệp tin: {sc.fmt_int(st['total_files'])} | "
                f"Tổng dung lượng: {sc.human_size(st['total_bytes'])} | Cập nhật: {st['last_import_utc'] or '—'}"
            )
            for b, info in sorted(st["branches"].items()):
                sc.log(f"  - {b:22s}: {info['folders']:5d} thư mục | {info['files']:6d} tệp | {sc.human_size(info['bytes'])}")
            return 0
        if args.action == "search":
            branch = sc.normalize_branch(args.nhanh) if args.nhanh else None
            hits = db.search_fts(args.query, branch=branch, limit=args.gioi_han)
            sc.log(f"Tìm thấy {len(hits)} kết quả cho `{args.query}`:")
            for h in hits:
                sc.log(f"  • {h['name']}  ({sc.human_size(h.get('size', 0))}) — {h['parent_path']}  [{h['id']}]")
            return 0
    return 1


def _cmd_undo(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(prog="kas undo", description="Nhật kí hoàn tác thống nhất (Unified Undo Journal).")
    sub = ap.add_subparsers(dest="action", required=True)
    sub.add_parser("list", help="Liệt kê các lô thao tác có thể hoàn tác")
    p_run = sub.add_parser("run", help="Hoàn tác một lô thao tác theo mã lô")
    p_run.add_argument("batch_id", help="Mã lô cần hoàn tác")
    p_run.add_argument("--thuc-thi", action="store_true", help="Thực sự hoàn tác trên kho (mặc định chạy thử)")
    p_run.add_argument("--dong-y", action="store_true", help="Không hỏi xác nhận")
    args = ap.parse_args(argv)

    with sc.StorageDB() as db:
        if args.action == "list":
            batches = db.list_undo_batches(limit=30)
            if not batches:
                sc.log("Chưa có lô thao tác nào trong Unified Undo Journal của kho này.")
                return 0
            for b in batches:
                st = f"đã hoàn tác lúc {b['undone_at']}" if b["undone_at"] else "có thể hoàn tác"
                sc.log(f"  • {b['batch_id']} | {b['kind']} | {b['action_count']} thao tác | {st} | {b['description']}")
            return 0
        if args.action == "run":
            if args.thuc_thi and not sc.confirm(f"Hoàn tác lô `{args.batch_id}` trên kho `{sc.ROOT_NAME}`?", args.dong_y):
                return 0
            drive = sc.create_backend() if args.thuc_thi else None
            res = db.undo_batch(drive, args.batch_id, execute=args.thuc_thi)
            sc.log(json.dumps(res, ensure_ascii=False, indent=2))
            return 0 if res.get("ok") else 1
    return 1


def _cmd_tests() -> int:
    from karius_academic_system.sync.github_sync import default_repo_root

    root = default_repo_root()
    test_dir = root / "tests"
    if not test_dir.exists():
        sc.log(f"Không tìm thấy thư mục kiểm thử tại {test_dir}.")
        return 1
    proc = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", str(test_dir), "-v"], cwd=str(root))
    return proc.returncode


def main(argv: Optional[List[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

    raw_args = list(sys.argv[1:] if argv is None else argv)

    # Trích xuất cờ toàn cục `--kho <slug>` / `--vault <slug>` trước lệnh con
    selected_vault: Optional[str] = None
    while len(raw_args) >= 2 and raw_args[0] in {"--kho", "--vault"}:
        selected_vault = raw_args[1]
        raw_args = raw_args[2:]
    if selected_vault:
        try:
            sc.activate_vault(selected_vault, persist=False)
        except KeyError as exc:
            sc.log(f"[LỖI] {exc} (dùng `kas vault list` để xem danh sách kho)")
            return 1

    all_cmds = [
        "vault",
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
        prog="kas",
        description=f"{APP_NAME} ({APP_SHORT}) v{__version__} — Hệ thống quản trị tri thức & đa kho dữ liệu.",
    )
    ap.add_argument("--kho", "--vault", dest="vault_slug", help="Chọn kho dữ liệu để thực thi lệnh")
    ap.add_argument("lenh", choices=all_cmds, help="Lệnh hoặc quy trình cần chạy")
    ap.add_argument("--thuc-thi", action="store_true", help="Cho phép ghi lên kho ở quy trình phối hợp")
    ap.add_argument("--dong-y", action="store_true", help="Không hỏi xác nhận")
    ap.add_argument("--tai-len", action="store_true", help="Tải báo cáo lên [00] TỔNG QUAN/[02] NHẬT KÍ")
    ap.add_argument("--nhanh", help="Giới hạn phạm vi nhánh")
    ap.add_argument("--bo-qua-quet", action="store_true", help="Bỏ qua bước quét trong `quy-trinh-nhanh`")
    ap.add_argument("--tang-cuong", action="store_true", help="Dùng `--tang-cuong` cho bước quét trong `bao-tri-dinh-ki`")

    if not raw_args or raw_args[0] in {"-h", "--help"}:
        ap.print_help()
        return 0

    cmd = raw_args[0]
    rest = raw_args[1:]

    if cmd == "version":
        sc.log(sc.describe())
        return 0
    if cmd == "vault":
        return _cmd_vault(rest)
    if cmd == "auth":
        return _cmd_auth(rest)
    if cmd == "db":
        return _cmd_db(rest)
    if cmd == "undo":
        return _cmd_undo(rest)
    if cmd == "danh-muc-chuan":
        return invoke_module_in_process("danh-muc", ["--chuan-hoa-v7", *rest])
    if cmd == "ui":
        from karius_academic_system.web.app import run_web_server

        return run_web_server(rest)
    if cmd == "desktop":
        from karius_academic_system.web.desktop import main as desktop_main

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
