"""Giao diện dòng lệnh hợp nhất `kas` — Karius Academic System (KAS) v1.0.0."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, List, Optional

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
    p_add.add_argument("target_or_slug", nargs="?", help="Mã kho (hoặc tên hiển thị nếu truyền thêm tham số thứ 2 là đường dẫn/URL)")
    p_add.add_argument("source_pos", nargs="?", help="Đường dẫn thư mục cục bộ hoặc URL/Folder ID Google Drive (tùy chọn thay --nguon)")
    p_add.add_argument("--nguon", "--source", dest="source", help="Đường dẫn thư mục trên máy hoặc URL/Folder ID Google Drive")
    p_add.add_argument("--slug", dest="slug_opt", help="Mã ngắn của kho (tự sinh nếu bỏ trống)")
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
            sc.log('  kas vault add "Tài Liệu Học Tập" "D:\\TaiLieu"')
            sc.log('  kas vault add "Kho Drive" "https://drive.google.com/drive/folders/<FOLDER_ID>"')
            return 0
        for v in vaults:
            mark = "*" if v.slug == act_slug else " "
            sc.log(
                f" {mark} {v.slug:20s} | {v.name} | {v.source_kind}:{v.root} | "
                f"backend={v.effective_backend()} | chế độ={v.effective_mode()}"
            )
        return 0

    if args.action == "add":
        # Hỗ trợ cả 2 cú pháp:
        #   1) kas vault add tai-lieu --nguon /path/or/url [--ten "..."]
        #   2) kas vault add "Tài Liệu Học Tập" /path/or/url
        src_val = args.source or args.source_pos
        slug_val = args.slug_opt
        display_name = args.name
        if args.source:
            slug_val = slug_val or args.target_or_slug
        elif args.source_pos:
            display_name = display_name or args.target_or_slug
            slug_val = slug_val or sc.slugify_vault(args.target_or_slug or "")
        elif args.target_or_slug:
            src_val = args.target_or_slug
        if not src_val:
            sc.log("Thiếu nguồn kho! Ví dụ: `kas vault add \"Tài Liệu\" \"D:\\TaiLieu\"` hoặc `kas vault add tai-lieu --nguon \"D:\\TaiLieu\"`.")
            return 1
        kind, norm_root = sc.detect_source_kind(src_val)
        if kind == "gdrive" and not display_name:
            try:
                drv = sc.create_backend(backend=None if args.backend == "auto" else args.backend)
                info = drv.info(norm_root)
                if info and info.get("name"):
                    display_name = str(info["name"])
            except Exception:
                pass
        vc = reg.add_vault(
            src_val,
            slug=slug_val,
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


def _parse_rule_value(key: str, raw: str, current: Any) -> Any:
    if isinstance(current, bool):
        return raw.strip().lower() in {"1", "true", "yes", "on", "co", "bat"}
    if isinstance(current, int):
        return int(raw.strip())
    if isinstance(current, list):
        txt = raw.strip()
        if txt.startswith("["):
            return json.loads(txt)
        return [x.strip() for x in txt.split(",") if x.strip()]
    if isinstance(current, dict):
        return json.loads(raw)
    return raw


def _cmd_rules(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(
        prog="kas rules",
        description="Tùy chỉnh thiết lập quy tắc đặt tên theo kho hoặc toàn cục (preset + tham số chi tiết + kiểm thử tức thì).",
    )
    sub = ap.add_subparsers(dest="action", required=True)

    p_show = sub.add_parser("show", help="Xem bộ quy tắc đặt tên đang áp dụng")
    p_show.add_argument("--json", action="store_true", dest="as_json", help="Xuất JSON")

    sub.add_parser("presets", help="Liệt kê các bộ mẫu (preset) quy tắc đặt tên sẵn có")

    p_pre = sub.add_parser("apply-preset", help="Áp dụng nhanh một bộ mẫu quy tắc đặt tên")
    p_pre.add_argument("preset", choices=list(sc.NAMING_PRESETS), help="Tên preset")
    p_pre.add_argument("--global", dest="is_global", action="store_true", help="Lưu làm mặc định toàn cục")

    p_set = sub.add_parser("set", help="Thiết lập từng tham số quy tắc đặt tên (vd: folder_case title)")
    p_set.add_argument("key", help="Tên trường quy tắc (xem bằng `kas rules show --json`)")
    p_set.add_argument("value", help="Giá trị mới (true/false, số, chuỗi, danh sách cách nhau bởi dấu phẩy, hoặc JSON)")
    p_set.add_argument("--global", dest="is_global", action="store_true", help="Lưu làm mặc định toàn cục")

    p_test = sub.add_parser("test", help="Kiểm thử & xem trước chuẩn hóa cho một tên tệp hoặc thư mục")
    p_test.add_argument("name", help="Tên tệp hoặc thư mục cần kiểm thử")
    p_test.add_argument("--folder", action="store_true", help="Kiểm thử dưới dạng tên thư mục")
    p_test.add_argument("--preset", choices=list(sc.NAMING_PRESETS), help="Thử tạm bằng một preset cụ thể")
    p_test.add_argument("--json", action="store_true", dest="as_json", help="Xuất JSON")

    p_exp = sub.add_parser("export", help="Xuất bộ quy tắc hiện tại ra tệp JSON")
    p_exp.add_argument("path", help="Đường dẫn tệp JSON đích")

    p_imp = sub.add_parser("import", help="Nhập bộ quy tắc từ tệp JSON")
    p_imp.add_argument("path", help="Đường dẫn tệp JSON nguồn")
    p_imp.add_argument("--global", dest="is_global", action="store_true", help="Lưu làm mặc định toàn cục")

    p_rst = sub.add_parser("reset", help="Khôi phục quy tắc đặt tên về mặc định")
    p_rst.add_argument("--global", dest="is_global", action="store_true", help="Khôi phục cấu hình toàn cục")

    args = ap.parse_args(argv)

    if args.action == "presets":
        for key, meta in sc.NAMING_PRESETS.items():
            sc.log(f"• {key:16s} — {meta['name']}")
            sc.log(f"    {meta['description']}")
        return 0

    if args.action == "show":
        rules, source = sc.get_active_naming_rules()
        if args.as_json:
            print(json.dumps({"source": source, "rules": rules.to_dict()}, ensure_ascii=False, indent=2))
            return 0
        d = rules.to_dict()
        sc.log(f"Bộ quy tắc đặt tên đang áp dụng | preset={rules.preset} | nguồn={source}")
        for k, v in d.items():
            sc.log(f"  - {k:28s}: {v}")
        return 0

    if args.action == "apply-preset":
        scope = "global" if args.is_global else "vault"
        rules, path = sc.apply_naming_preset(args.preset, scope=scope)
        sc.log(f"Đã áp dụng preset `{rules.preset}` ({scope}) tại {path}.")
        return 0

    if args.action == "set":
        scope = "global" if args.is_global else "vault"
        rules, _ = sc.get_active_naming_rules()
        d = rules.to_dict()
        if args.key not in d:
            sc.log(f"Tham số không hợp lệ: `{args.key}`. Các tham số hợp lệ: {', '.join(sorted(d))}")
            return 1
        try:
            d[args.key] = _parse_rule_value(args.key, args.value, d[args.key])
        except Exception as exc:
            sc.log(f"Giá trị không hợp lệ cho `{args.key}`: {exc}")
            return 1
        if args.key != "preset":
            d["preset"] = "custom"
        new_rules = sc.NamingRuleSet.from_dict(d)
        path = sc.save_naming_rules(new_rules, scope=scope)
        sc.log(f"Đã cập nhật `{args.key}` = {d[args.key]!r} ({scope}) tại {path}.")
        return 0

    if args.action == "test":
        rules = sc.preset_rules(args.preset) if args.preset else sc.get_active_naming_rules()[0]
        res = sc.preview_naming(args.name, is_folder=args.folder, rules=rules)
        if args.as_json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
            return 0
        sc.log(f"Kiểm thử ({'Thư mục' if args.folder else 'Tệp tin'} | preset={res['preset']}):")
        sc.log(f"  Gốc      : {res['original']}")
        sc.log(f"  Đề xuất  : {res['suggested']}")
        sc.log(f"  Đạt chuẩn: {'CÓ ✅' if res['compliant'] else 'CHƯA ⚠️'}")
        for i in res["issues"]:
            sc.log(f"  • [{i['severity']}] {i['code']}: {i['description']}")
        return 0

    if args.action == "export":
        rules, _ = sc.get_active_naming_rules()
        out = Path(args.path).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(rules.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        sc.log(f"Đã xuất bộ quy tắc ra {out}.")
        return 0

    if args.action == "import":
        src = Path(args.path).expanduser()
        if not src.exists():
            sc.log(f"Không tìm thấy tệp {src}.")
            return 1
        rules = sc.NamingRuleSet.from_dict(json.loads(src.read_text(encoding="utf-8")))
        scope = "global" if args.is_global else "vault"
        saved = sc.save_naming_rules(rules, scope=scope)
        sc.log(f"Đã nhập bộ quy tắc `{rules.preset}` ({scope}) vào {saved}.")
        return 0

    if args.action == "reset":
        scope = "global" if args.is_global else "vault"
        removed = sc.reset_naming_rules(scope=scope)
        sc.log(f"Đã khôi phục quy tắc mặc định ({scope})." if removed else f"Chưa có cấu hình tùy chỉnh ({scope}) để xóa.")
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


def _cmd_settings(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(prog="kas settings", description="Quản lý Cài đặt ứng dụng Karius Academic System (KAS).")
    sub = ap.add_subparsers(dest="action", required=True)
    p_show = sub.add_parser("show", help="Xem toàn bộ cài đặt phần mềm hiện tại")
    p_show.add_argument("--json", action="store_true", dest="as_json", help="Xuất JSON")
    p_set = sub.add_parser("set", help="Cập nhật một mục cài đặt (vd: theme light, drive_backend api)")
    p_set.add_argument("key", help="Tên mục cài đặt")
    p_set.add_argument("value", help="Giá trị mới")
    sub.add_parser("reset", help="Khôi phục toàn bộ cài đặt về mặc định")
    sub.add_parser("check-update", help="Kiểm tra phiên bản KAS mới nhất trên GitHub Releases")
    args = ap.parse_args(argv)

    if args.action == "show":
        st = sc.load_app_settings()
        if args.as_json:
            print(json.dumps({"settings": st.to_dict(), "paths": sc.get_system_paths_info()}, ensure_ascii=False, indent=2))
            return 0
        sc.log(f"Cài đặt phần mềm ({sc.app_settings_path()}):")
        for k, v in st.to_dict().items():
            sc.log(f"  - {k:26s}: {v}")
        return 0
    if args.action == "set":
        st = sc.load_app_settings()
        d = st.to_dict()
        if args.key not in d:
            sc.log(f"Mục cài đặt không hợp lệ: `{args.key}`. Hợp lệ: {', '.join(sorted(d))}")
            return 1
        d[args.key] = _parse_rule_value(args.key, args.value, d[args.key])
        new_st = sc.AppSettings.from_dict(d)
        saved = sc.save_app_settings(new_st)
        sc.log(f"Đã lưu cài đặt `{args.key}` = {new_st.to_dict()[args.key]!r} tại {saved}.")
        return 0
    if args.action == "reset":
        sc.reset_app_settings()
        sc.log("Đã khôi phục toàn bộ cài đặt KAS về mặc định.")
        return 0
    if args.action == "check-update":
        res = sc.check_latest_release(github_token=sc.get_saved_github_token())
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res.get("ok") else 1
    return 1


def _cmd_account(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(prog="kas account", description="Quản lý Tài khoản đăng nhập KAS & Kết nối dịch vụ bên thứ 3.")
    sub = ap.add_subparsers(dest="action", required=True)
    p_st = sub.add_parser("status", help="Xem trạng thái tài khoản KAS và kết nối bên thứ 3")
    p_st.add_argument("--json", action="store_true", dest="as_json")
    p_reg = sub.add_parser("register", help="Tạo tài khoản KAS cục bộ")
    p_reg.add_argument("username", help="Tên đăng nhập")
    p_reg.add_argument("--password", required=True, help="Mật khẩu (tối thiểu 4 ký tự)")
    p_reg.add_argument("--name", default="", help="Tên hiển thị")
    p_reg.add_argument("--email", default="", help="Email (tùy chọn)")
    p_reg.add_argument("--require-login", action="store_true", help="Bật khóa đăng nhập khi mở giao diện KAS")
    p_lk = sub.add_parser("lock", help="Bật/tắt yêu cầu đăng nhập khi mở ứng dụng")
    p_lk.add_argument("mode", choices=["on", "off"])
    p_gh = sub.add_parser("connect-github", help="Kết nối tài khoản GitHub bằng Personal Access Token")
    p_gh.add_argument("--token", required=True, help="GitHub PAT")
    p_gh.add_argument("--no-verify", action="store_true", help="Lưu không kiểm chứng trực tuyến")
    args = ap.parse_args(argv)

    if args.action == "status":
        payload = {"account": sc.account_status(), "integrations": sc.get_all_integrations_summary()}
        if args.as_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0
        acc = payload["account"]
        sc.log(f"Tài khoản KAS: {'Đã tạo (' + acc['account']['username'] + ')' if acc['has_account'] else 'Chưa tạo'} | Khóa mở app: {'BẬT' if acc['require_login'] else 'TẮT'}")
        gd = payload["integrations"]["google_drive"]["auth"]
        gh = payload["integrations"]["github"]
        sc.log(f"  • Google Drive : {'Đã đăng nhập' if gd['authenticated'] else 'Chưa đăng nhập'} (credentials={'có' if gd['credentials_exists'] else 'chưa có'})")
        sc.log(f"  • GitHub       : {'Đã kết nối (' + gh['login'] + ')' if gh['connected'] else 'Chưa kết nối'}")
        sc.log(f"  • AI Provider  : {payload['integrations']['ai_provider']['provider']} ({payload['integrations']['ai_provider']['model']})")
        return 0
    if args.action == "register":
        profile, _ = sc.register_account(
            args.username, args.password, display_name=args.name, email=args.email, require_login=args.require_login
        )
        sc.log(f"Đã tạo tài khoản KAS `{profile['username']}` (khóa mở app={'BẬT' if profile['require_login'] else 'TẮT'}).")
        return 0
    if args.action == "lock":
        prof = sc.update_account_profile(require_login=(args.mode == "on"))
        sc.log(f"Đã {'BẬT' if prof['require_login'] else 'TẮT'} khóa đăng nhập cho tài khoản `{prof['username']}`.")
        return 0
    if args.action == "connect-github":
        st = sc.connect_github_token(args.token, verify=not args.no_verify)
        sc.log(f"Đã kết nối GitHub: {st.get('login') or '(token đã lưu)'}.")
        return 0
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


def _cmd_browse(argv: List[str]) -> int:
    from karius_academic_system.ops import explorer

    ap = argparse.ArgumentParser(
        prog="kas duyet",
        description="Di chuyển duyệt thư mục và xem trước tệp tin trong kho hiện hành.",
    )
    ap.add_argument("path", nargs="?", default="", help="Đường dẫn thư mục hoặc tệp tương đối trong kho")
    ap.add_argument("--sort", default="name", choices=["name", "size", "modified", "type"], help="Tiêu chí sắp xếp")
    ap.add_argument("--desc", action="store_true", help="Sắp xếp giảm dần")
    ap.add_argument("--loc", "--filter", dest="filter_q", default="", help="Lọc theo tên tệp/thư mục")
    ap.add_argument("--xem", "--preview", dest="preview", action="store_true", help="Xem trước chi tiết tệp/thư mục")
    ap.add_argument("--tai-drive", action="store_true", help="Tải nội dung tệp Google Drive để xem trước")
    ap.add_argument("--json", action="store_true", dest="as_json", help="Xuất kết quả định dạng JSON")
    args = ap.parse_args(argv)

    try:
        if args.preview:
            data = explorer.preview_item(path=args.path, fetch_drive=args.tai_drive)
            if args.as_json:
                print(json.dumps(data, ensure_ascii=False, indent=2))
                return 0
            sc.log(f"[XEM TRƯỚC] {data.get('name')} ({data.get('category')} · {data.get('size_human')})")
            sc.log(f"  Đường dẫn : {data.get('path') or '/'}")
            if data.get("mime_type"):
                sc.log(f"  MIME      : {data.get('mime_type')}")
            if data.get("url"):
                sc.log(f"  Drive URL : {data.get('url')}")
            if data.get("outline"):
                sc.log(f"  Mục lục   : {', '.join(str(x) for x in data['outline'][:8])}")
            txt = data.get("text_preview") or ""
            if txt:
                sc.log("-" * 60)
                print(txt[:2500])
            return 0

        data = explorer.browse_folder(
            args.path,
            sort_by=args.sort,
            order="desc" if args.desc else "asc",
            filter_q=args.filter_q,
        )
        if args.as_json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
            return 0
        if not data.get("has_vault"):
            sc.log("[CẢNH BÁO] Chưa kết nối kho dữ liệu nào. Dùng `kas vault add <đường_dẫn>`.")
            return 1
        if data.get("needs_scan"):
            sc.log("[CẢNH BÁO] Kho Google Drive chưa có chỉ mục. Chạy `kas quet` trước khi duyệt.")
            return 1
        st = data.get("stats", {})
        cur = data.get("current_path") or "/"
        sc.log(f"[DUYỆT KHO] {data.get('root_name')} :: {cur} ({st.get('folders', 0)} thư mục, {st.get('files', 0)} tệp, {st.get('size_human', '0 B')})")
        for it in data.get("entries", []):
            tag = "[DIR]" if it["is_folder"] else f"[{(it.get('ext') or it.get('category') or 'FILE').upper():>4}]"
            meta = f"{it.get('child_folders', 0)} TM / {it.get('child_files', 0)} tệp" if it["is_folder"] else it.get("size_human", "")
            print(f"  {tag:<7} {it['name']:<52}  {meta}")
        return 0
    except Exception as exc:
        sc.log(f"[LỖI] {exc}")
        return 1


def main(argv: Optional[List[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

    sc.refresh_system_path()
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
        "duyet",
        "browse",
        "rules",
        "ai",
        "mcp",
        "settings",
        "account",
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
        description=f"{APP_NAME} ({APP_SHORT}) v{__version__} — Hệ thống quản trị tri thức, đa kho dữ liệu & kết nối AI/MCP Agent.",
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
    if cmd in {"duyet", "browse"}:
        return _cmd_browse(rest)
    if cmd == "rules":
        return _cmd_rules(rest)
    if cmd == "settings":
        return _cmd_settings(rest)
    if cmd == "account":
        return _cmd_account(rest)
    if cmd == "ai":
        from karius_academic_system.ai.bridge import main as ai_main

        return ai_main(rest)
    if cmd == "mcp":
        from karius_academic_system.ai.mcp_server import main as mcp_main

        return mcp_main(rest)
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
