#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TRIỂN KHAI VÀ ĐỒNG BỘ BỘ CHƯƠNG TRÌNH QUẢN LÝ — [A] STORAGE (v2.0)
====================================================================
Đồng bộ thư mục mã nguồn cục bộ với `[A] STORAGE/[00] TỔNG QUAN/[03] QUẢN LÝ` trên Google Drive:

Nâng cấp v2.0:
- Dùng `sync_manifest.json` (`id`, `sha256`, `modifiedTime`):
  • Bỏ qua tệp có SHA-256 cục bộ không đổi (trừ khi truyền `--ep-buoc`).
  • Phát hiện xung đột nếu `remote.modifiedTime` mới hơn mốc đồng bộ gần nhất
    (yêu cầu `--ghi-de-xung-dot` nếu thực sự muốn ghi đè).
- Đổi tên tại chỗ theo `LEGACY_FILE_RENAMES` (giữ nguyên 100% File ID cũ khi chuyển sang `snake_case`).
- Tùy chọn `--don-tep-du` đưa tệp mã cũ dư thừa trên Drive về khu cách ly `[99] KIỂM TRA` (không xóa).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from karius_academic_system import core as sc

QUAN_LY_ID = os.environ.get("KAS_QUAN_LY_ID", sc.quan_ly_id())


def _active_quan_ly_id() -> str:
    return QUAN_LY_ID or os.environ.get("KAS_QUAN_LY_ID") or sc.quan_ly_id()

LEGACY_ROOT_FILES = {
    "Mã Nguồn Chuẩn Hóa Và Đồng Bộ Toàn Kho - Storage.py": ("[04] CHUẨN HÓA TÊN", "storage_toolkit.py"),
    "Mã Nguồn Tạo Bảng Danh Mục Hệ Thống - Storage.py": ("[05] DANH MỤC HỆ THỐNG", "sheet_engine.py"),
}

# Ánh xạ tên tệp tiếng Việt cũ → tên `snake_case` mới (Phương án A) để đổi tên TẠI CHỖ, giữ nguyên ID
LEGACY_FILE_RENAMES: Dict[str, Dict[str, str]] = {
    "[02] QUÉT CHỈ MỤC": {
        "Mã Nguồn Quét Chỉ Mục Toàn Kho - Storage.py": "storage_indexer.py",
    },
    "[03] KIỂM TRA QUY ƯỚC": {
        "Mã Nguồn Kiểm Tra Quy Ước Đặt Tên - Storage.py": "naming_auditor.py",
    },
    "[04] CHUẨN HÓA TÊN": {
        "Mã Nguồn Chuẩn Hóa Và Đồng Bộ Toàn Kho - Storage.py": "storage_toolkit.py",
    },
    "[05] DANH MỤC HỆ THỐNG": {
        "Mã Nguồn Tạo Bảng Danh Mục Hệ Thống - Storage.py": "sheet_engine.py",
        "Mã Nguồn Cập Nhật Bảng Danh Mục Hệ Thống - Storage.py": "sheet_updater.py",
    },
    "[06] RÀ SOÁT TRÙNG LẶP": {
        "Mã Nguồn Rà Soát Trùng Lặp Và Shortcut - Storage.py": "dedup_scanner.py",
    },
    "[07] BÁO CÁO THỐNG KÊ": {
        "Mã Nguồn Báo Cáo Thống Kê Và Biến Động - Storage.py": "stats_reporter.py",
    },
    "[08] TRIỂN KHAI MÃ NGUỒN": {
        "Mã Nguồn Triển Khai Bộ Quản Lý - Storage.py": "deploy_sync.py",
    },
}

SKIP_NAMES = {
    "__pycache__", ".DS_Store", ".pytest_cache", ".git", ".github", ".gitignore",
    ".agents", ".venv", "venv", "build", "node_modules", "README.md", "pyproject.toml",
}


def manifest_path() -> Path:
    return sc.data_dir() / "sync_manifest.json"


def default_local_root() -> Path:
    cwd = Path.cwd()
    for base in (cwd, *list(Path(__file__).resolve().parents)[:5]):
        if (base / "pyproject.toml").exists():
            return base
    return cwd


def should_skip(p: Path) -> bool:
    return p.name in SKIP_NAMES or p.name.startswith(".") or p.suffix in {".pyc", ".pyo"} or p.name.endswith(".egg-info")


def stage_release_bundle(repo_root: Path, staging_dir: Path) -> Path:
    """Chuẩn bị thư mục đồng bộ gọn lên Drive `[00] TỔNG QUAN/[03] QUẢN LÝ`: chỉ gồm tài liệu `docs/` + gói phát hành `dist/*.whl`."""
    import shutil as _sh

    staging_dir.mkdir(parents=True, exist_ok=True)
    docs_src = repo_root / "docs"
    if docs_src.is_dir():
        for md in sorted(docs_src.glob("*.md")):
            if md.name == "Tổng Quan Hệ Thống - Quản Lý.md":
                _sh.copy2(md, staging_dir / md.name)
            else:
                out_dir = staging_dir / "[01] TÀI LIỆU HỆ THỐNG"
                out_dir.mkdir(parents=True, exist_ok=True)
                _sh.copy2(md, out_dir / md.name)
    readme = repo_root / "README.md"
    if readme.exists():
        out_dir = staging_dir / "[01] TÀI LIỆU HỆ THỐNG"
        out_dir.mkdir(parents=True, exist_ok=True)
        _sh.copy2(readme, out_dir / "Giới Thiệu Phần Mềm - Storage.md")
    dist_src = repo_root / "dist"
    if dist_src.is_dir():
        artifacts = sorted([p for p in dist_src.iterdir() if p.is_file() and p.suffix in {".whl", ".gz", ".zip", ".exe", ".apk"}])
        if artifacts:
            rel_dir = staging_dir / "[02] GÓI PHÁT HÀNH"
            rel_dir.mkdir(parents=True, exist_ok=True)
            for art in artifacts:
                _sh.copy2(art, rel_dir / art.name)
    return staging_dir


def cmd_list(drive: sc.Drive) -> None:
    qid = _active_quan_ly_id()
    if not qid:
        raise SystemExit("Kho hiện tại chưa có thư mục [03] QUẢN LÝ. Hãy chạy `kas vault init-structure --thuc-thi` hoặc cấu hình KAS_QUAN_LY_ID.")
    sc.log(f"[03] QUẢN LÝ ({qid}):")
    root_items = sorted(drive.ls(qid), key=lambda x: (x["mimeType"] != sc.FOLDER_MIME, x["name"]))
    for it in root_items:
        is_f = it["mimeType"] == sc.FOLDER_MIME
        sc.log(f"├── {'📁' if is_f else '📄'} {it['name']}  ({it['id']})")
        if is_f:
            sub = sorted(drive.ls(it["id"]), key=lambda x: (x["mimeType"] != sc.FOLDER_MIME, x["name"]))
            for j, ch in enumerate(sub):
                branch = "└──" if j == len(sub) - 1 else "├──"
                cf_icon = "📁" if ch["mimeType"] == sc.FOLDER_MIME else "📄"
                sc.log(f"│   {branch} {cf_icon} {ch['name']}  ({ch['id']})")


def download_tree(drive: sc.Drive, folder_id: str, dest: Path, rel_prefix: str, manifest: dict) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for it in drive.ls(folder_id):
        name = it["name"]
        rel = f"{rel_prefix}/{name}" if rel_prefix else name
        if it["mimeType"] == sc.FOLDER_MIME:
            download_tree(drive, it["id"], dest / name, rel, manifest)
        elif it["mimeType"] in sc.GOOGLE_NATIVE_MIMES:
            continue
        else:
            out = dest / name
            drive.download(it["id"], out)
            manifest[rel] = {
                "id": it["id"],
                "sha256": sc.sha256_file(out),
                "modifiedTime": it.get("modifiedTime", ""),
                "synced_iso": sc.now_utc_iso(),
            }
            sc.log(f"  ↓ {out}")


def cmd_pull(drive: sc.Drive, local_root: Path) -> None:
    qid = _active_quan_ly_id()
    if not qid:
        raise SystemExit("Kho hiện tại chưa có thư mục [03] QUẢN LÝ.")
    sc.log(f"Đang tải [03] QUẢN LÝ ({qid}) → {local_root} ...")
    manifest = sc.read_json(manifest_path(), {}) or {}
    download_tree(drive, qid, local_root, "", manifest)
    sc.write_json(manifest_path(), manifest, indent=1)
    sc.log(f"Hoàn tất tải về & cập nhật manifest ({manifest_path()}).")


def _apply_legacy_renames(
    drive: sc.Drive,
    local_dir: Path,
    rel_prefix: str,
    remote_items: Dict[str, dict],
    dry_run: bool,
    actions: List[Tuple[str, str]],
) -> None:
    rename_rules = LEGACY_FILE_RENAMES.get(rel_prefix, {})
    for legacy_name, new_name in rename_rules.items():
        lk = sc.nfc(legacy_name)
        nk = sc.nfc(new_name)
        legacy_it = remote_items.get(lk)
        if not legacy_it or legacy_it["mimeType"] == sc.FOLDER_MIME:
            continue
        if nk in remote_items:
            continue
        if not (local_dir / new_name).exists():
            continue
        fid = legacy_it["id"]
        if dry_run:
            actions.append(("đổi tên tại chỗ (giữ ID)", f"{rel_prefix}/{legacy_name} → {new_name} ({fid})"))
        else:
            drive.rename(fid, new_name)
            actions.append(("đã đổi tên (giữ ID)", f"{rel_prefix}/{legacy_name} → {new_name} ({fid})"))
        renamed_copy = dict(legacy_it)
        renamed_copy["name"] = new_name
        remote_items.pop(lk, None)
        remote_items[nk] = renamed_copy


def _quarantine_dest_for_extras(drive: sc.Drive) -> str:
    kiem_tra = sc.quarantine_root_id()
    q_dup = sc.CONFIG.get("quarantine_subfolders", {}).get("duplicate", "[03] TỆP TRÙNG LẶP")
    return drive.ensure_folder(q_dup, kiem_tra)


def sync_folder(
    drive: sc.Drive,
    local_dir: Path,
    remote_id: str,
    rel_prefix: str,
    manifest: dict,
    dry_run: bool,
    force: bool,
    overwrite_conflict: bool,
    clean_extras: bool,
    actions: List[Tuple[str, str]],
    conflicts: List[str],
    extra_dest_id: Optional[List[str]],
) -> None:
    remote_items = {sc.nfc(it["name"]): it for it in drive.ls(remote_id)}
    _apply_legacy_renames(drive, local_dir, rel_prefix, remote_items, dry_run, actions)

    local_names = set()
    for entry in sorted(local_dir.iterdir(), key=lambda p: (not p.is_dir(), p.name)):
        if should_skip(entry):
            continue
        key = sc.nfc(entry.name)
        local_names.add(key)
        rel = f"{rel_prefix}/{entry.name}" if rel_prefix else entry.name
        existing = remote_items.get(key)

        if entry.is_dir():
            if existing and existing["mimeType"] == sc.FOLDER_MIME:
                sub_id = existing["id"]
                actions.append(("giữ thư mục", f"{rel} ({sub_id})"))
            else:
                if dry_run:
                    actions.append(("tạo thư mục", rel))
                    sub_id = None
                else:
                    sub_id = drive.mkdir(entry.name, remote_id)
                    actions.append(("tạo thư mục", f"{rel} ({sub_id})"))
            if sub_id:
                sync_folder(
                    drive, entry, sub_id, rel, manifest, dry_run,
                    force, overwrite_conflict, clean_extras, actions, conflicts, extra_dest_id,
                )
            else:
                for sub_e in sorted(entry.rglob("*")):
                    if not should_skip(sub_e) and sub_e.is_file():
                        sub_rel = f"{rel}/{sub_e.relative_to(entry).as_posix()}"
                        actions.append(("tải lên mới", sub_rel))
        else:
            local_hash = sc.sha256_file(entry)
            m_entry = manifest.get(rel)

            if existing and existing["mimeType"] != sc.FOLDER_MIME:
                remote_mod = existing.get("modifiedTime", "")
                if (
                    m_entry
                    and m_entry.get("id") == existing["id"]
                    and m_entry.get("modifiedTime")
                    and remote_mod > m_entry["modifiedTime"]
                    and m_entry.get("sha256") != local_hash
                    and not overwrite_conflict
                ):
                    msg = (f"{rel} ({existing['id']}): Drive mới hơn ({remote_mod} > {m_entry['modifiedTime']}) "
                           f"— bỏ qua để tránh ghi đè ngược (dùng --ghi-de-xung-dot nếu chắc chắn)")
                    conflicts.append(msg)
                    actions.append(("XUNG ĐỘT (bỏ qua)", msg))
                    continue

                if m_entry and m_entry.get("id") == existing["id"] and m_entry.get("sha256") == local_hash and not force:
                    actions.append(("bỏ qua (không đổi SHA-256)", rel))
                    continue

                actions.append(("cập nhật tại chỗ", f"{rel} ({existing['id']})"))
                if not dry_run:
                    drive.update(existing["id"], entry)
                    info = drive.info(existing["id"])
                    manifest[rel] = {
                        "id": existing["id"],
                        "sha256": local_hash,
                        "modifiedTime": info.get("modifiedTime", sc.now_utc_iso()),
                        "synced_iso": sc.now_utc_iso(),
                    }
            else:
                actions.append(("tải lên mới", rel))
                if not dry_run:
                    new_id = drive.upload(entry, remote_id)
                    if new_id:
                        info = drive.info(new_id)
                        manifest[rel] = {
                            "id": new_id,
                            "sha256": local_hash,
                            "modifiedTime": info.get("modifiedTime", sc.now_utc_iso()),
                            "synced_iso": sc.now_utc_iso(),
                        }

    if clean_extras:
        for rname, rit in sorted(remote_items.items()):
            if rit["mimeType"] in sc.GOOGLE_NATIVE_MIMES or rit["mimeType"] == sc.FOLDER_MIME:
                continue
            if rname not in local_names:
                rel = f"{rel_prefix}/{rit['name']}" if rel_prefix else rit["name"]
                if dry_run:
                    actions.append(("cách ly tệp dư trên Drive", f"{rel} ({rit['id']}) → [99] KIỂM TRA"))
                else:
                    if not extra_dest_id[0]:
                        extra_dest_id[0] = _quarantine_dest_for_extras(drive)
                    drive.move(rit["id"], extra_dest_id[0])
                    actions.append(("đã cách ly tệp dư", f"{rel} ({rit['id']}) → [99] KIỂM TRA"))


def cmd_push(
    drive: sc.Drive,
    local_root: Path,
    dry_run: bool,
    assume_yes: bool,
    force: bool = False,
    overwrite_conflict: bool = False,
    clean_extras: bool = False,
) -> int:
    if not local_root.is_dir():
        raise SystemExit(f"Thư mục nguồn không tồn tại: {local_root}")
    qid = _active_quan_ly_id()
    if not qid:
        raise SystemExit("Kho hiện tại chưa có thư mục [03] QUẢN LÝ. Hãy chạy `kas vault init-structure --thuc-thi` hoặc cấu hình KAS_QUAN_LY_ID.")
    root_items = {sc.nfc(it["name"]): it for it in drive.ls(qid)}
    manifest = sc.read_json(manifest_path(), {}) or {}
    actions: List[Tuple[str, str]] = []
    conflicts: List[str] = []

    if not dry_run and not sc.confirm(f"Đồng bộ {local_root} → [03] QUẢN LÝ ({qid})?", assume_yes):
        return 0

    # 1. Đảm bảo thư mục con tồn tại trước
    sub_ids: Dict[str, str] = {}
    for entry in sorted(local_root.iterdir()):
        if entry.is_dir() and not should_skip(entry):
            ex = root_items.get(sc.nfc(entry.name))
            if ex and ex["mimeType"] == sc.FOLDER_MIME:
                sub_ids[sc.nfc(entry.name)] = ex["id"]
            elif dry_run:
                actions.append(("tạo thư mục", entry.name))
            else:
                fid = drive.mkdir(entry.name, qid)
                sub_ids[sc.nfc(entry.name)] = fid
                actions.append(("tạo thư mục", f"{entry.name} ({fid})"))

    # 2. Di chuyển + đổi tên các tệp cũ nằm rời ở gốc nếu có
    for legacy_name, (target_folder, target_file) in LEGACY_ROOT_FILES.items():
        legacy = root_items.get(sc.nfc(legacy_name))
        if not legacy or legacy["mimeType"] == sc.FOLDER_MIME:
            continue
        dest_id = sub_ids.get(sc.nfc(target_folder))
        if dry_run:
            actions.append(("di chuyển tệp gốc cũ", f"{legacy_name} → {target_folder}/{target_file}"))
        elif dest_id:
            if not drive.find_child(dest_id, target_file) and not drive.find_child(dest_id, legacy_name):
                drive.move(legacy["id"], dest_id)
                drive.rename(legacy["id"], target_file)
                actions.append(("đã chuyển & đổi tên", f"{legacy_name} ({legacy['id']}) → {target_folder}/{target_file}"))

    # 3. Đồng bộ toàn bộ cây thư mục cục bộ lên `[03] QUẢN LÝ`
    extra_dest_id: List[str] = [""]
    sync_folder(
        drive, local_root, qid, "", manifest, dry_run,
        force, overwrite_conflict, clean_extras, actions, conflicts, extra_dest_id,
    )

    if not dry_run:
        sc.write_json(manifest_path(), manifest, indent=1)

    sc.log("\n=== KẾT QUẢ TRIỂN KHAI ===" + (" (CHẠY THỬ)" if dry_run else ""))
    for act, detail in actions:
        sc.log(f"  • {act:28s}: {detail}")
    if conflicts:
        sc.log(f"\n[CẢNH BÁO XUNG ĐỘT] Có {len(conflicts)} tệp bị sửa trên Drive sau lần đồng bộ gần nhất.")
    if dry_run:
        sc.log("\n(Chạy thử — thêm --thuc-thi để áp dụng lên kho dữ liệu.)")
    return 3 if conflicts else 0


LEGACY_MODULE_FOLDERS = {
    "[01] THƯ VIỆN LÕI",
    "[02] QUÉT CHỈ MỤC",
    "[03] KIỂM TRA QUY ƯỚC",
    "[04] CHUẨN HÓA TÊN",
    "[05] DANH MỤC HỆ THỐNG",
    "[06] RÀ SOÁT TRÙNG LẶP",
    "[07] BÁO CÁO THỐNG KÊ",
    "[08] TRIỂN KHAI MÃ NGUỒN",
    "[09] ĐIỀU PHỐI VẬN HÀNH",
    "[10] SAO CHÉP DI CHUYỂN",
    "[11] NHẬP DỮ LIỆU MỚI",
    "[12] TRA CỨU VÀ KIỂM TOÁN",
    "[13] ĐỌC TỆP",
    "[14] PHÂN TÍCH NỘI DUNG",
    "[15] ĐỒNG BỘ GITHUB",
    "[16] PHÂN TÍCH HÌNH ẢNH",
    "[17] PHÂN TÍCH ÂM THANH",
    "[18] PHÂN TÍCH VIDEO",
}


def archive_legacy_module_folders(
    drive: sc.Drive,
    *,
    dry_run: bool = True,
    db: Optional[sc.StorageDB] = None,
) -> Dict[str, object]:
    """Lưu trữ an toàn các thư mục mô-đun cũ `[01]`–`[18]` trên `[03] QUẢN LÝ` về `[07] KIỂM TRA/[08] MÃ NGUỒN CŨ V3` (không xóa)."""
    qid = _active_quan_ly_id()
    if not qid:
        return {"found": 0, "moved": 0, "batch_id": "", "items": []}
    legacy_keys = {sc.nfc(n) for n in LEGACY_MODULE_FOLDERS}
    remote_items = drive.ls(qid)
    targets = [
        it for it in remote_items
        if it.get("mimeType") == sc.FOLDER_MIME and sc.nfc(it.get("name", "")) in legacy_keys
    ]
    if not targets:
        return {"found": 0, "moved": 0, "batch_id": "", "items": []}

    sub_name = sc.CONFIG.get("quarantine_subfolders", {}).get("legacy_code", "[08] MÃ NGUỒN CŨ V3")
    if dry_run:
        return {
            "found": len(targets),
            "moved": 0,
            "batch_id": "",
            "dest_name": sub_name,
            "items": [it["name"] for it in targets],
        }

    dest_id = drive.ensure_folder(sub_name, sc.quarantine_root_id())
    results = drive.batch_move([(it["id"], dest_id) for it in targets], workers=8)
    by_id = {it["id"]: it for it in targets}
    actions: List[sc.UndoAction] = []
    errors: List[str] = []
    for fid, ok, err in results:
        it = by_id[fid]
        if ok:
            actions.append(
                sc.UndoAction(
                    op="archive_legacy_module",
                    item_id=fid,
                    old_name=it["name"],
                    new_name=it["name"],
                    old_parent_id=qid,
                    new_parent_id=dest_id,
                    path=f"{sc.ROOT_NAME}/{sc.TONG_QUAN_FOLDER}/[03] QUẢN LÝ",
                )
            )
        else:
            errors.append(f"{it['name']}: {err}")

    batch_id = ""
    if db is not None and actions:
        batch_id = db.record_undo_batch(
            kind="archive_legacy_v3",
            actions=actions,
            description=f"Lưu trữ {len(actions)} thư mục mã cũ [01]–[18] từ [03] QUẢN LÝ → {sub_name}",
        )
    return {
        "found": len(targets),
        "moved": len(actions),
        "errors": errors,
        "batch_id": batch_id,
        "dest_id": dest_id,
        "dest_name": sub_name,
        "items": [it["name"] for it in targets],
    }


def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(description="Triển khai & đồng bộ tài liệu + gói phát hành lên [03] QUẢN LÝ (KAS v1.0).")
    ap.add_argument("lenh", choices=["danh-sach", "tai-ve", "day-len", "phat-hanh-drive"], help="Thao tác cần thực hiện")
    ap.add_argument("--thu-muc", help="Thư mục nguồn trên máy (mặc định: thư mục gốc kho lưu trữ)")
    ap.add_argument("--thuc-thi", action="store_true", help="Thực sự ghi lên kho dữ liệu (mặc định chạy thử)")
    ap.add_argument("--dong-y", action="store_true", help="Không hỏi xác nhận")
    ap.add_argument("--ep-buoc", action="store_true", help="Tải lên lại kể cả tệp có SHA-256 không đổi")
    ap.add_argument("--ghi-de-xung-dot", action="store_true", help="Cho phép ghi đè nếu bản trên kho mới hơn manifest")
    ap.add_argument("--don-tep-du", action="store_true", help="Đưa tệp dư trên kho (không còn ở máy) vào [07] KIỂM TRA")
    ap.add_argument("--luu-tru-ma-cu", action="store_true", help="Chuyển 18 thư mục mã nguồn cũ [01]–[18] trên [03] QUẢN LÝ về [07] KIỂM TRA/[08] MÃ NGUỒN CŨ V3")
    args = ap.parse_args(argv)

    drive = sc.create_drive()
    local_root = Path(args.thu_muc).expanduser() if args.thu_muc else default_local_root()
    if args.lenh == "danh-sach":
        cmd_list(drive)
    elif args.lenh == "tai-ve":
        cmd_pull(drive, local_root)
    elif args.lenh == "phat-hanh-drive":
        import shutil as _sh
        import tempfile as _tf

        tmp = Path(_tf.mkdtemp(prefix="kas_drive_bundle_"))
        try:
            stage_release_bundle(local_root, tmp)
            rc = cmd_push(
                drive, tmp,
                dry_run=not args.thuc_thi,
                assume_yes=args.dong_y,
                force=args.ep_buoc,
                overwrite_conflict=args.ghi_de_xung_dot,
                clean_extras=args.don_tep_du,
            )
            if args.luu_tru_ma_cu or args.don_tep_du:
                with sc.StorageDB() as db:
                    arc = archive_legacy_module_folders(drive, dry_run=not args.thuc_thi, db=db)
                if arc["found"]:
                    if args.thuc_thi:
                        sc.log(
                            f"Đã lưu trữ {arc['moved']}/{arc['found']} thư mục mã cũ [01]–[18] → "
                            f"{sc.KIEM_TRA_FOLDER}/{arc['dest_name']} | mã hoàn tác: {arc['batch_id'] or '—'}"
                        )
                    else:
                        sc.log(
                            f"(Chạy thử) Sẽ lưu trữ {arc['found']} thư mục mã cũ [01]–[18] → "
                            f"{sc.KIEM_TRA_FOLDER}/{arc['dest_name']}"
                        )
            if rc:
                sys.exit(rc)
        finally:
            _sh.rmtree(tmp, ignore_errors=True)
    elif args.lenh == "day-len":
        rc = cmd_push(
            drive, local_root,
            dry_run=not args.thuc_thi,
            assume_yes=args.dong_y,
            force=args.ep_buoc,
            overwrite_conflict=args.ghi_de_xung_dot,
            clean_extras=args.don_tep_du,
        )
        if rc:
            sys.exit(rc)


if __name__ == "__main__":
    main()
