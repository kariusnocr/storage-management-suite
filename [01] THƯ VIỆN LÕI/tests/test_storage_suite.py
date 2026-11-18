#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BỘ KIỂM THỬ TỰ ĐỘNG NGOẠI TUYẾN — BỘ QUẢN LÝ [A] STORAGE (v3.0)
=================================================================
Kiểm chứng ngoại tuyến toàn bộ quy tắc lõi & hành vi an toàn của `[01]`–`[12]`
(dùng thư mục tạm + Drive giả lập).
Chạy bằng:
    python3 -m unittest discover -s "[01] THƯ VIỆN LÕI/tests" -v
"""

from __future__ import annotations

import gzip
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
CORE_DIR = TESTS_DIR.parent
REPO_ROOT = CORE_DIR.parent

if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))

import storage_core as sc  # noqa: E402


def _load_mod(name: str, rel_path: str):
    p = REPO_ROOT / rel_path
    spec = importlib.util.spec_from_file_location(name, str(p))
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


storage_indexer = _load_mod("storage_indexer_testmod", "[02] QUÉT CHỈ MỤC/storage_indexer.py")
naming_auditor = _load_mod("naming_auditor_testmod", "[03] KIỂM TRA QUY ƯỚC/naming_auditor.py")
storage_toolkit = _load_mod("storage_toolkit_testmod", "[04] CHUẨN HÓA TÊN/storage_toolkit.py")
sheet_engine = _load_mod("sheet_engine_testmod", "[05] DANH MỤC HỆ THỐNG/sheet_engine.py")
dedup_scanner = _load_mod("dedup_scanner_testmod", "[06] RÀ SOÁT TRÙNG LẶP/dedup_scanner.py")
stats_reporter = _load_mod("stats_reporter_testmod", "[07] BÁO CÁO THỐNG KÊ/stats_reporter.py")
deploy_sync = _load_mod("deploy_sync_testmod", "[08] TRIỂN KHAI MÃ NGUỒN/deploy_sync.py")
storage_cli = _load_mod("storage_cli_testmod", "[09] ĐIỀU PHỐI VẬN HÀNH/storage_cli.py")
transfer_manager = _load_mod("transfer_manager_testmod", "[10] SAO CHÉP DI CHUYỂN/transfer_manager.py")
data_ingestor = _load_mod("data_ingestor_testmod", "[11] NHẬP DỮ LIỆU MỚI/data_ingestor.py")
storage_inspector = _load_mod("storage_inspector_testmod", "[12] TRA CỨU VÀ KIỂM TOÁN/storage_inspector.py")
file_reader = _load_mod("file_reader_testmod", "[13] ĐỌC TỆP/file_reader.py")
content_analyzer = _load_mod("content_analyzer_testmod", "[14] PHÂN TÍCH NỘI DUNG/content_analyzer.py")
github_sync = _load_mod("github_sync_testmod", "[15] ĐỒNG BỘ GITHUB/github_sync.py")


def _it(fid: str, name: str, mime: str = "application/pdf", size: int = 1024, mod: str = "2026-11-16T06:00:00Z"):
    d = {"id": fid, "name": name, "mimeType": mime, "modifiedTime": mod}
    if mime != sc.FOLDER_MIME and mime not in sc.GOOGLE_NATIVE_MIMES:
        d["size"] = size
    return d


class FakeDrive:
    """Mô phỏng tối thiểu `sc.Drive` cho kiểm thử ngoại tuyến (tương thích v3.0)."""

    def __init__(self, tree_by_id=None, caps=None, downloads=None, search_items=None):
        self.tree = tree_by_id or {}
        self.caps = caps or {}
        self.downloads = downloads or {}
        self.search_items = search_items or []
        self.infos = {}
        self.renamed = []
        self.updated = []
        self.uploaded = []
        self.moved = []
        self.copied = []
        self.shortcuts = []
        self.mkdirs = []

    def ls(self, folder_id: str):
        return list(self.tree.get(folder_id, []))

    def stream_ls(self, folder_ids, concurrency=32, timeout=600):
        return {fid: self.ls(fid) for fid in folder_ids}, {}

    def search(self, **kwargs):
        return list(self.search_items)

    def info(self, file_id: str):
        if file_id in self.infos:
            return dict(self.infos[file_id])
        return {"id": file_id, "name": file_id, "mimeType": "application/pdf", "modifiedTime": "2026-11-17T08:00:00Z", "parents": []}

    def stream_info(self, file_ids, concurrency=32, timeout=600):
        return {fid: self.info(fid) for fid in file_ids}

    def capabilities(self, file_id: str, fields: str = ""):
        return dict(self.caps.get(file_id, {"canMoveItemOutOfDrive": True, "canEdit": True}))

    def stream_capabilities(self, file_ids, fields: str = "", concurrency=32, timeout=600):
        return {fid: self.capabilities(fid, fields) for fid in file_ids}

    def download(self, file_id: str, out: Path):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(self.downloads.get(file_id, b"same-content"))
        return out

    def export(self, file_id: str, out: Path, fmt: str):
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = self.downloads.get(file_id, b"# Tai Lieu Google\nNoi dung van ban trich xuat.")
        out.write_bytes(payload)
        return out

    def find_child(self, parent_id: str, name: str, folder_only: bool = False):
        for it in self.ls(parent_id):
            if sc.nfc(it["name"]) == sc.nfc(name) and (not folder_only or it["mimeType"] == sc.FOLDER_MIME):
                return it
        return None

    def mkdir(self, name: str, parent_id: str):
        new_id = f"dir_{len(self.mkdirs)}_{abs(hash(name)) % 10000}"
        self.mkdirs.append((name, parent_id, new_id))
        self.tree.setdefault(parent_id, []).append(_it(new_id, name, sc.FOLDER_MIME))
        self.tree.setdefault(new_id, [])
        return new_id

    def ensure_folder(self, name: str, parent_id: str):
        ex = self.find_child(parent_id, name, folder_only=True)
        return ex["id"] if ex else self.mkdir(name, parent_id)

    def rename(self, file_id: str, new_name: str):
        self.renamed.append((file_id, new_name))

    def update(self, file_id: str, local: Path, mime_type=None):
        self.updated.append((file_id, Path(local).name))

    def upload(self, local: Path, parent_id: str, mime_type=None):
        nid = f"up_{len(self.uploaded)}"
        self.uploaded.append((Path(local).name, parent_id, nid))
        self.infos[nid] = {"id": nid, "name": Path(local).name, "modifiedTime": "2026-11-17T08:05:00Z"}
        return nid

    def move(self, file_id: str, new_parent_id: str):
        self.moved.append((file_id, new_parent_id))

    def copy(self, file_id: str, new_name: str, parent_id: str):
        cid = f"cp_{len(self.copied)}_{file_id}"
        self.copied.append((file_id, new_name, parent_id, cid))
        self.tree.setdefault(parent_id, []).append(_it(cid, new_name, "application/pdf"))
        return cid

    def create_shortcut(self, target_id: str, parent_id: str, shortcut_name: Optional[str] = None):
        sid = f"sc_{len(self.shortcuts)}_{target_id}"
        self.shortcuts.append((target_id, parent_id, shortcut_name, sid))
        return sid

    def batch_move(self, items, workers=8):
        out = []
        for fid, dest in items:
            self.move(fid, dest)
            out.append((fid, True, ""))
        return out

    def batch_rename(self, items):
        for fid, nm in items:
            self.rename(fid, nm)
        return [(fid, True, "") for fid, _ in items]


class TestStorageCoreRules(unittest.TestCase):
    def test_thai_spanish_and_special_tokens_no_false_title_case(self):
        samples = [
            ("1. เม่นกับงู - Truyện Cổ Tích Thái Lan.pdf", "application/pdf"),
            ("第一章 Tổng Quan - Triết Học.pdf", "application/pdf"),
            ("Khái Niệm (a+) Trong Logic - Học Thuật.pdf", "application/pdf"),
            ("e-Business Principles - Kinh Tế Số.pdf", "application/pdf"),
            ("eBook Hướng Dẫn - Công Nghệ.epub", "application/epub+zip"),
            ("iOS Architecture Guide - Lập Trình.pdf", "application/pdf"),
            ("Lecciones Preliminares de Filosofía - Manuel García Morente.pdf", "application/pdf"),
            ("Historia de la Filosofía y de las Ciencias - Julian Marias.pdf", "application/pdf"),
        ]
        for fname, mime in samples:
            codes = {c for _, c, _ in sc.check_file_name(fname, mime, "[A] STORAGE/[05] SƯU TẦM/[01] SÁCH")}
            self.assertNotIn("CHUA_TITLE_CASE", codes, f"False positive CHUA_TITLE_CASE on {fname}: {codes}")

    def test_tu_vi_guard_and_quarantine_helpers(self):
        self.assertEqual(sc.title_case_vn("NHẬP MÔN TỬ VI ĐẨU SỐ"), "Nhập Môn Tử Vi Đẩu Số")
        self.assertEqual(sc.title_case_vn("Spiritu Tu Vi"), "Spiritu Tu Vi")
        self.assertTrue(sc.is_quarantine_path("[A] STORAGE/[07] KIỂM TRA/[03] TỆP TRÙNG LẶP"))
        self.assertTrue(sc.is_quarantine_path("[A] STORAGE/[99] KIỂM TRA/[03] TỆP TRÙNG LẶP"))
        self.assertFalse(sc.is_quarantine_path("[A] STORAGE/[05] SƯU TẦM"))
        self.assertEqual(
            sc.extract_drive_id("https://drive.google.com/drive/folders/194HC3C2WC1BSzfK3cn_0_uUJ4vfDuBsr?usp=sharing"),
            "194HC3C2WC1BSzfK3cn_0_uUJ4vfDuBsr",
        )
        self.assertEqual(
            sc.next_available_stt(["[00] TỔNG QUAN", "[01] TRIẾT HỌC", "[02] LỊCH SỬ"]),
            "[03]",
        )

    def test_tongquan_classified_as_tep_he_thong_cu_only(self):
        issues = sc.check_file_name("TongQuan.md", "text/markdown", "[A] STORAGE/[01] HỌC THUẬT/[00] TỔNG QUAN")
        codes = [c for _, c, _ in issues]
        self.assertEqual(codes, ["TEP_HE_THONG_CU"])

    def test_tech_exceptions(self):
        self.assertTrue(sc.is_tech_exception("[A] STORAGE/[00] TỔNG QUAN/[02] NHẬT KÍ", "sheets_index.json"))
        self.assertTrue(sc.is_tech_exception("[A] STORAGE/[00] TỔNG QUAN/[03] QUẢN LÝ/[01] THƯ VIỆN LÕI", "storage_config.json"))
        self.assertTrue(sc.is_tech_exception("[A] STORAGE/[00] TỔNG QUAN/[03] QUẢN LÝ/[09] ĐIỀU PHỐI VẬN HÀNH", "storage_cli.py"))
        self.assertTrue(sc.is_tech_exception("[A] STORAGE/[00] TỔNG QUAN/[03] QUẢN LÝ/[10] SAO CHÉP DI CHUYỂN", "transfer_manager.py"))
        self.assertFalse(sc.is_tech_exception("[A] STORAGE/[01] HỌC THUẬT", "sheets_index.json"))
        self.assertEqual(sc.check_folder_name("tests", "[A] STORAGE/[00] TỔNG QUAN/[03] QUẢN LÝ/[01] THƯ VIỆN LÕI"), [])
        self.assertEqual(sc.check_folder_name("plugins", "[A] STORAGE/[06] ĐỒNG BỘ/[01] M-OBSIDIANS/.obsidian"), [])

    def test_normalize_sheet_title_and_vietnamese_vi(self):
        self.assertEqual(sc.normalize_sheet_title("[A] STORAGE"), "Danh Mục Hệ Thống - Storage")
        self.assertEqual(
            sc.normalize_sheet_title("[A] STORAGE/[01] HỌC THUẬT/[01] ĐẠI HỌC/[01] [USSH] TRƯỜNG ĐH KHXH&NV/[01] [QH-2026-X-TR] K71 TRIẾT HỌC/[01] CHÍNH KHÓA/[01] [FLF1107-16] TIẾNG ANH B1"),
            "Danh Mục Hệ Thống - FLF1107-16 - Tiếng Anh B1",
        )
        self.assertEqual(
            sc.normalize_sheet_title("[A] STORAGE/[01] ĐỀ/7.31 CÂU ĐÚNG SAI HAY VÀ KHÓ.PDF"),
            "Danh Mục Hệ Thống - 7.31 Câu Đúng Sai Hay Và Khó",
        )
        self.assertEqual(
            sc.normalize_sheet_title("[A] STORAGE/[05] SƯU TẦM/[01] [TỬ VI]"),
            "Danh Mục Hệ Thống - Tử Vi",
        )
        self.assertEqual(
            sc.normalize_sheet_title("[A] STORAGE/[02] NGHIÊN CỨU/CÁC TƯ TƯỞNG CỦA CÁC TRIẾT GIA VĨ ĐẠI"),
            "Danh Mục Hệ Thống - Các Tư Tưởng Của Các Triết Gia Vĩ Đại",
        )
        self.assertEqual(
            sc.normalize_sheet_title("[A] STORAGE/[02] NGHIÊN CỨU/TÂM LÝ HỌC GIAO TIẾP & HÀNH VI"),
            "Danh Mục Hệ Thống - Tâm Lý Học Giao Tiếp & Hành Vi",
        )
        self.assertEqual(
            sc.normalize_sheet_title("[A] STORAGE/[01] ĐỀ/CHƯƠNG VI - K12 - KNTT"),
            "Danh Mục Hệ Thống - Chương VI - K12 - KNTT",
        )
        self.assertEqual(
            sc.normalize_sheet_title("[A] STORAGE/[01] HỌC THUẬT/[03] PHỔ THÔNG/[00] TỔNG QUAN/[02] [CÁCH IN TÀI LIỆU XỊN]"),
            "Danh Mục Hệ Thống - Cách In Tài Liệu Xịn",
        )
        self.assertEqual(
            sc.normalize_sheet_title("[A] STORAGE/[01] ĐỀ/[01] [MUST SEE] KẸO CAO SU"),
            "Danh Mục Hệ Thống - Must See - Kẹo Cao Su",
        )
        self.assertEqual(sc.title_case_vn("*TÀI LIỆU BDHSG LỊCH SỬ"), "*Tài Liệu BDHSG Lịch Sử")

    def test_safe_fix_name_preserves_leading_hyphen_and_strips_native_ext(self):
        self.assertEqual(sc.safe_fix_name(" - Cuộc Đời Và Số Mệnh.prc", False), " - Cuộc Đời Và Số Mệnh.prc")
        self.assertEqual(
            sc.safe_fix_name("Danh Mục Hệ Thống - Đề Hay.pdf", False, sc.SHEET_MIME),
            "Danh Mục Hệ Thống - Đề Hay",
        )


class TestToolkitIdempotencyAndRules(unittest.TestCase):
    def test_fifty_plus_v6_filenames_produce_zero_changes(self):
        v6_samples = [
            ("[A] STORAGE/[03] SÁNG TÁC/[02] VĂN", "Bức Thư Gửi Tới Chính Mình - Sáng Tác Văn, 10-09-2026", "application/vnd.google-apps.document"),
            ("[A] STORAGE/[03] SÁNG TÁC/[01] THƠ", "Đợi Gặp Cố Nhân - Sáng Tác Thơ, 23-09-2026", "application/vnd.google-apps.document"),
            ("[A] STORAGE/[05] SƯU TẦM/[01] SÁCH/[01] TRIẾT HỌC", "Bàn Về Khế Ước Xã Hội - Jean-Jacques Rousseau.epub", "application/epub+zip"),
            ("[A] STORAGE/[05] SƯU TẦM/[01] SÁCH/[01] TRIẾT HỌC", "Siêu Hình Học - NXB Tân Việt 1943 Nguyễn Đình Thi 336 Trang.pdf", "application/pdf"),
            ("[A] STORAGE/[05] SƯU TẦM/[01] SÁCH/[01] TRIẾT HỌC", "Lecciones Preliminares de Filosofía - Manuel García Morente.pdf", "application/pdf"),
            ("[A] STORAGE/[01] HỌC THUẬT/[03] PHỔ THÔNG", "Bài Tập Trắc Nghiệm Dạng Đúng Sai Môn Toán 12 - Toán.pdf", "application/pdf"),
            ("[A] STORAGE/[01] HỌC THUẬT/[01] ĐẠI HỌC", "Giáo Trình Logic Học Đại Cương Full 268 Trang - Logic Học Đại Cương.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            ("[A] STORAGE/[00] TỔNG QUAN", "Tổng Quan Hệ Thống - Quy Ước Đặt Tên.md", "text/markdown"),
            ("[A] STORAGE/[00] TỔNG QUAN/[02] NHẬT KÍ", "sheets_index.json", "application/json"),
            ("[A] STORAGE/[00] TỔNG QUAN/[02] NHẬT KÍ", "Nhật Kí Hệ Thống Hóa - Storage, 16-11-2026.md", "text/markdown"),
            ("[A] STORAGE/[00] TỔNG QUAN/[03] QUẢN LÝ/[04] CHUẨN HÓA TÊN", "storage_toolkit.py", "text/x-python"),
            ("[A] STORAGE/[00] TỔNG QUAN/[03] QUẢN LÝ/[01] THƯ VIỆN LÕI", "storage_config.json", "application/json"),
            ("[A] STORAGE/[05] SƯU TẦM/[01] SÁCH/[01] DỰ ÁN SỐ HÓA", "Readme Hướng Dẫn Sử Dụng - Mã Nguồn Descartes", "application/vnd.google-apps.document"),
            ("[A] STORAGE/[05] SƯU TẦM/[01] SÁCH/[01] DỰ ÁN SỐ HÓA", "av_processor.py", "text/x-python"),
            ("[A] STORAGE/[05] SƯU TẦM/[01] SÁCH/[01] DỰ ÁN SỐ HÓA", "config.json", "application/json"),
            ("[A] STORAGE/[06] ĐỒNG BỘ/[01] M-OBSIDIANS/.obsidian", "app.json", "application/json"),
            ("[A] STORAGE/[01] HỌC THUẬT/[01] ĐẠI HỌC", "Tổng Quan Hệ Thống - Đại Học.md", "text/markdown"),
            ("[A] STORAGE/[01] HỌC THUẬT/[01] ĐẠI HỌC/[00] TỔNG QUAN", "Danh Mục Hệ Thống - Đại Học", sc.SHEET_MIME),
            ("[A] STORAGE/[05] SƯU TẦM/[01] SÁCH/[02] NGOẠI NGỮ", "1. เม่นกับงู - Truyện Cổ Tích Thái.pdf", "application/pdf"),
            ("[A] STORAGE/[05] SƯU TẦM/[01] SÁCH/[03] KINH TẾ", "e-Business Models - Kinh Tế Số, Phần 01.pdf", "application/pdf"),
            ("[A] STORAGE/[05] SƯU TẦM/[01] SÁCH/[03] KINH TẾ", "Hành Vi Người Tiêu Dùng - Kotler, Phiên Bản 2.epub", "application/epub+zip"),
            ("[A] STORAGE/[01] HỌC THUẬT/[02] CAO HỌC", "Đề Cương Ôn Tập Triết Học Mác-Lênin - Cao Học, 2026.pdf", "application/pdf"),
            ("[A] STORAGE/[04] BIÊN TẬP", "Bảng Điểm Tổng Kết - Học Kì 1", sc.SHEET_MIME),
            ("[A] STORAGE/[04] BIÊN TẬP", "Slide Thuyết Trình Nhóm 03 - Kỹ Năng Mềm", "application/vnd.google-apps.presentation"),
            ("[A] STORAGE/[05] SƯU TẦM/[04] ÂM NHẠC", "Nocturne Op.9 No.2 - Frédéric Chopin.flac", "audio/flac"),
            ("[A] STORAGE/[05] SƯU TẦM/[04] ÂM NHẠC", "Vết Mưa - Vũ Cát Tường.mp3", "audio/mpeg"),
            ("[A] STORAGE/[01] HỌC THUẬT/[03] PHỔ THÔNG", "30 Đề Minh Họa TN THPT 2026 - Vật Lí.zip", "application/zip"),
            ("[A] STORAGE/[02] NGHIÊN CỨU", "Kinh Dịch Đại Toàn - Nguyễn Hiến Lê.mobi", "application/x-mobipocket-ebook"),
            ("[A] STORAGE/[02] NGHIÊN CỨU", "Đạo Đức Kinh - Lão Tử, Nguyễn Duy Cần.azw3", "application/octet-stream"),
            ("[A] STORAGE/[01] HỌC THUẬT/[04] CHỨNG CHỈ", "Cambridge IELTS 19 Academic - Tiếng Anh, Kèm Audio.rar", "application/x-rar"),
            ("[A] STORAGE/[01] HỌC THUẬT/[04] CHỨNG CHỈ", "HSK 6 Standard Course - Giáo Trình Tiếng Trung.pdf", "application/pdf"),
        ]
        for n in range(1, 26):
            v6_samples.append((
                "[A] STORAGE/[03] SÁNG TÁC/[02] VĂN",
                f"Nhật Kí Nghiên Cứu Số {n:02d} - Sáng Tác Văn, 16-11-2026.md",
                "text/markdown",
            ))
        self.assertGreaterEqual(len(v6_samples), 55)

        index = {}
        for idx_i, (p, name, mime) in enumerate(v6_samples):
            entry = index.setdefault(p, {"id": f"dir_{abs(hash(p))}", "depth": p.count("/"), "items": []})
            entry["items"].append(_it(f"f_{idx_i}", name, mime, size=1000 + idx_i))
        plan = storage_toolkit.build_full_rename_plan(index, {}, include_sheets=False)
        self.assertEqual(plan, [], f"Expected 0 renames on 56 V6 samples, got: {plan}")

    def test_legacy_conversions_and_duplicate_tongquan_skip(self):
        index = {
            "[A] STORAGE/[01] HỌC THUẬT/[03] PHỔ THÔNG/[00] TỔNG QUAN": {
                "id": "d_pt_tq",
                "depth": 3,
                "items": [
                    _it("f1", "01_260513_HocTotCungChiNgoc_TongQuan", sc.SHEET_MIME),
                    _it("f2", "03_260708_NenTangLop12_TongQuan.zip", "application/zip"),
                    _it("tq1", "TongQuan.md", "text/markdown", size=2048, mod="2026-11-16T06:00:00Z"),
                    _it("tq2", "TongQuan.md", "text/markdown", size=2048, mod="2026-11-16T06:05:00Z"),
                ],
            },
            "[A] STORAGE/[01] HỌC THUẬT/[01] ĐẠI HỌC/[00] TỔNG QUAN": {
                "id": "d_dh_tq",
                "depth": 3,
                "items": [
                    _it("tq_ok", "TongQuan.md", "text/markdown", size=1900),
                ],
            },
            "[A] STORAGE/[05] SƯU TẦM/[01] SÁCH/[09] SÁCH TRUYỆN CỔ - PDF": {
                "id": "d_sach",
                "depth": 4,
                "items": [
                    _it("b1", " - Cuộc Đời Và Số Mệnh.prc", "application/octet-stream"),
                    _it("v1", "LeMinhDat_26032571_LongTieng.mp4", "video/mp4"),
                ],
            },
        }
        plan = storage_toolkit.build_full_rename_plan(index, {}, include_sheets=False)
        by_id = {p["id"]: p["new_name"] for p in plan}
        self.assertEqual(by_id["f1"], "Học Tốt Cùng Chị Ngọc - Phổ Thông, 13-05-2026")
        self.assertIn("Nền Tảng Lớp 12", by_id["f2"])
        self.assertEqual(by_id["tq_ok"], "Tổng Quan Hệ Thống - Đại Học.md")
        self.assertNotIn("tq1", by_id)
        self.assertNotIn("tq2", by_id)
        self.assertEqual(by_id["b1"], "Cuộc Đời Và Số Mệnh - Sách Truyện Cổ - PDF.prc")
        self.assertEqual(by_id["v1"], "Lồng Tiếng - Lê Minh Đạt, 26032571.mp4")


class TestDedupScannerRules(unittest.TestCase):
    def test_parts_vs_versions_vs_exact_copies(self):
        p = "[A] STORAGE/[01] HỌC THUẬT/[03] PHỔ THÔNG/[01] TOÁN"
        index = {
            p: {
                "id": "d1",
                "depth": 3,
                "items": [
                    _it("p1", "Chuyên Đề Hàm Số - Toán, Phần 01.pdf", size=2_000_000),
                    _it("p2", "Chuyên Đề Hàm Số - Toán, Phần 02.pdf", size=2_000_000),
                    _it("v1", "Đề Thi Thử Ninh Bình - Lịch Sử, Phiên Bản 1.pdf", size=300_000, mod="2026-11-16T05:00:00Z"),
                    _it("v2", "Đề Thi Thử Ninh Bình - Lịch Sử, Phiên Bản 2.pdf", size=300_000, mod="2026-11-16T06:00:00Z"),
                    _it("c1", "Sách Hay - Tác Giả.pdf", size=500_000, mod="2026-11-16T05:00:00Z"),
                    _it("c2", "Sách Hay - Tác Giả (1).pdf", size=500_000, mod="2026-11-16T06:00:00Z"),
                    _it("b1", "Sách B - Tác Giả, Bản 01.pdf", size=400_000, mod="2026-11-16T05:00:00Z"),
                    _it("b2", "Sách B - Tác Giả, Bản 02.pdf", size=400_000, mod="2026-11-16T06:00:00Z"),
                ],
            }
        }
        certain, version_dups, suspect = dedup_scanner.find_duplicates(index)
        cert_extra_ids = {ep[1]["id"] for g in certain for ep in g["extra"]}
        ver_extra_ids = {ep[1]["id"] for g in version_dups for ep in g["extra"]}
        susp_ids = {x[1]["id"] for g in suspect for x in g["items"]}

        self.assertEqual(cert_extra_ids, {"c2", "b2"})
        self.assertEqual(ver_extra_ids, {"v2"})
        self.assertEqual(susp_ids, {"p1", "p2"})

    def test_duplicate_tongquan_and_nested_empty_and_capabilities(self):
        tq_p = "[A] STORAGE/[01] HỌC THUẬT/[00] TỔNG QUAN"
        empty_parent = "[A] STORAGE/[02] NGHIÊN CỨU/[01] NHÁNH RỖNG"
        empty_child = "[A] STORAGE/[02] NGHIÊN CỨU/[01] NHÁNH RỖNG/[01] CON RỖNG"
        non_empty = "[A] STORAGE/[02] NGHIÊN CỨU/[02] CÓ TỆP"
        index = {
            "[A] STORAGE": {"id": "root", "depth": 0, "items": []},
            tq_p: {
                "id": "tq_id",
                "depth": 2,
                "items": [
                    _it("tq_a", "TongQuan.md", "text/markdown", size=3000, mod="2026-11-16T05:00:00Z"),
                    _it("tq_b", "TongQuan.md", "text/markdown", size=3000, mod="2026-11-16T06:00:00Z"),
                ],
            },
            empty_parent: {"id": "ep", "depth": 2, "items": [_it("ec", "[01] CON RỖNG", sc.FOLDER_MIME)]},
            empty_child: {"id": "ec", "depth": 3, "items": []},
            non_empty: {"id": "ne", "depth": 2, "items": [_it("doc1", "Tài Liệu - Tác Giả.pdf", size=1234)]},
        }
        dup_tq = dedup_scanner.find_duplicate_tongquan(index)
        self.assertEqual(len(dup_tq), 1)
        self.assertEqual(dup_tq[0]["extra"][0][1]["id"], "tq_b")

        empty = dedup_scanner.find_empty_folders_detailed(index)
        self.assertEqual([(p, n) for p, _, n in empty], [(empty_parent, True), (empty_child, False)])

        fake = FakeDrive(
            caps={"tq_b": {"canMoveItemOutOfDrive": False, "canEdit": False}, "ok1": {"canMoveItemOutOfDrive": True}},
            downloads={"tq_a": b"hello", "tq_b": b"hello", "d1": b"a", "d2": b"b"},
        )
        allowed, blocked = dedup_scanner.check_capabilities(
            [{"id": "tq_b", "name": "TongQuan.md"}, {"id": "ok1", "name": "Dup.pdf"}],
            drive=fake,
        )
        self.assertEqual([x["id"] for x in allowed], ["ok1"])
        self.assertEqual([x["id"] for x in blocked], ["tq_b"])

        ver_groups, rej = dedup_scanner.verify_groups_sha256(
            [{"size": 1, "kind": "version_duplicate", "keep": (tq_p, _it("d1", "A")), "extra": [(tq_p, _it("d2", "B"))]}],
            drive=fake,
            require_verified=True,
        )
        self.assertEqual(ver_groups, [])
        self.assertEqual(len(rej), 1)

        with tempfile.TemporaryDirectory() as td:
            old_env = os.environ.get("STORAGE_DATA_DIR")
            os.environ["STORAGE_DATA_DIR"] = td
            try:
                fake_exec = FakeDrive(caps={"tq_b": {"canMoveItemOutOfDrive": True}})
                moves = dedup_scanner.quarantine_moves([], dup_tongquan=dup_tq)
                blocked_res = dedup_scanner.execute_moves(moves, index, workers=2, drive=fake_exec)
                self.assertEqual(blocked_res, [])
                self.assertEqual([it["id"] for it in index[tq_p]["items"]], ["tq_a"])
                self.assertEqual([it["id"] for it in sc.load_index()[tq_p]["items"]], ["tq_a"])
            finally:
                if old_env is None:
                    os.environ.pop("STORAGE_DATA_DIR", None)
                else:
                    os.environ["STORAGE_DATA_DIR"] = old_env


class TestSheetEngineStatsAndDeploy(unittest.TestCase):
    def test_sheet_engine_tabs_and_incremental_signature(self):
        with tempfile.TemporaryDirectory() as td:
            old_env = os.environ.get("STORAGE_DATA_DIR")
            os.environ["STORAGE_DATA_DIR"] = td
            try:
                p = "[A] STORAGE/[01] HỌC THUẬT"
                index = {
                    p: {"id": "ht", "depth": 1, "items": [_it("tq_dir", "[00] TỔNG QUAN", sc.FOLDER_MIME), _it("f1", "Sách - A.pdf", size=2048)]},
                    f"{p}/[00] TỔNG QUAN": {
                        "id": "tq_dir",
                        "depth": 2,
                        "items": [_it("sh1", "Danh Mục Hệ Thống - Học Thuật.pdf", sc.SHEET_MIME, mod="2026-11-16T06:00:00Z")],
                    },
                }
                xlsx = Path(td) / "out.xlsx"
                rows, nf, nfl = sheet_engine.build_xlsx_with_stats(index, p, xlsx)
                self.assertGreaterEqual(rows, 2)
                import openpyxl
                wb = openpyxl.load_workbook(xlsx)
                self.assertEqual(wb.sheetnames, ["Danh Mục Hệ Thống", "Thống Kê Nhanh"])

                sig1 = sheet_engine.compute_subtree_signature(index, p)
                index[f"{p}/[00] TỔNG QUAN"]["items"][0]["modifiedTime"] = "2026-11-17T09:00:00Z"
                sig2 = sheet_engine.compute_subtree_signature(index, p)
                self.assertEqual(sig1, sig2)

                targets = sheet_engine.discover_targets(index, branch=None, max_depth=99)
                todo, _ = sheet_engine.filter_changed_targets(index, targets, {"sh1": {"sig": sig2}}, only_changed=True, force_all=False)
                self.assertEqual(todo, [])

                fixes = sheet_engine.collect_title_fixes(targets)
                self.assertEqual(len(fixes), 1)
                self.assertEqual(fixes[0]["new_name"], "Danh Mục Hệ Thống - Học Thuật")
            finally:
                if old_env is None:
                    os.environ.pop("STORAGE_DATA_DIR", None)
                else:
                    os.environ["STORAGE_DATA_DIR"] = old_env

    def test_stats_reporter_health_score_and_unbounded_csv(self):
        with tempfile.TemporaryDirectory() as td:
            old_env = os.environ.get("STORAGE_DATA_DIR")
            os.environ["STORAGE_DATA_DIR"] = td
            try:
                p = "[A] STORAGE/[01] HỌC THUẬT"
                items_a = [_it(f"id_{i}", f"Tài Liệu {i:03d} - Toán.pdf", size=1000) for i in range(350)]
                items_b = [_it(f"id_{i}", f"Tài Liệu {i:03d} - Toán Mới.pdf", size=1000) for i in range(350)]
                idx_a = {p: {"id": "ht", "depth": 1, "items": items_a}}
                idx_b = {p: {"id": "ht", "depth": 1, "items": items_b}}
                pa = Path(td) / "a.json.gz"
                pb = Path(td) / "b.json.gz"
                with gzip.open(pa, "wt", encoding="utf-8") as fa:
                    json.dump(idx_a, fa)
                with gzip.open(pb, "wt", encoding="utf-8") as fb:
                    json.dump(idx_b, fb)

                rep = stats_reporter.stats_report(idx_b, 7, 10)
                self.assertIn("Health Score", rep)
                md, counts, csv_rows = stats_reporter.diff_report(pa, pb)
                self.assertEqual(counts[2], 350)
                self.assertEqual(len(csv_rows), 350)
                self.assertIn("ĐỔI TÊN", csv_rows[0])
            finally:
                if old_env is None:
                    os.environ.pop("STORAGE_DATA_DIR", None)
                else:
                    os.environ["STORAGE_DATA_DIR"] = old_env

    def test_deploy_sync_conflict_skip_and_legacy_rename(self):
        with tempfile.TemporaryDirectory() as td:
            old_env = os.environ.get("STORAGE_DATA_DIR")
            os.environ["STORAGE_DATA_DIR"] = Path(td, "data").__str__()
            try:
                src = Path(td) / "src"
                sub2 = src / "[02] QUÉT CHỈ MỤC"
                sub2.mkdir(parents=True)
                f_idx = sub2 / "storage_indexer.py"
                f_idx.write_text("print('indexer v2')", encoding="utf-8")

                tree = {
                    deploy_sync.QUAN_LY_ID: [_it("fld2", "[02] QUÉT CHỈ MỤC", sc.FOLDER_MIME)],
                    "fld2": [_it("old_idx_id", "Mã Nguồn Quét Chỉ Mục Toàn Kho - Storage.py", "text/x-python", mod="2026-11-17T06:00:00Z")],
                }
                fake = FakeDrive(tree_by_id=tree)
                fake.infos["old_idx_id"] = {"id": "old_idx_id", "modifiedTime": "2026-11-17T07:10:00Z"}

                rc = deploy_sync.cmd_push(fake, src, dry_run=False, assume_yes=True)
                self.assertEqual(rc, 0)
                self.assertIn(("old_idx_id", "storage_indexer.py"), fake.renamed)
                self.assertIn(("old_idx_id", "storage_indexer.py"), fake.updated)

                fake.tree["fld2"] = [_it("old_idx_id", "storage_indexer.py", "text/x-python", mod="2026-11-17T07:10:00Z")]
                fake.updated.clear()
                rc2 = deploy_sync.cmd_push(fake, src, dry_run=False, assume_yes=True)
                self.assertEqual(rc2, 0)
                self.assertEqual(fake.updated, [])

                f_idx.write_text("print('indexer v3')", encoding="utf-8")
                fake.tree["fld2"] = [_it("old_idx_id", "storage_indexer.py", "text/x-python", mod="2026-11-17T09:99:00Z")]
                rc3 = deploy_sync.cmd_push(fake, src, dry_run=False, assume_yes=True)
                self.assertEqual(rc3, 3)
                self.assertEqual(fake.updated, [])
            finally:
                if old_env is None:
                    os.environ.pop("STORAGE_DATA_DIR", None)
                else:
                    os.environ["STORAGE_DATA_DIR"] = old_env

    def test_indexer_incremental_crawl(self):
        old_index = {
            sc.ROOT_NAME: {"id": sc.ROOT_ID, "depth": 0, "items": [_it("d1", "[01] A", sc.FOLDER_MIME)]},
            f"{sc.ROOT_NAME}/[01] A": {"id": "d1", "depth": 1, "items": [_it("d2", "[01] CU", sc.FOLDER_MIME)]},
            f"{sc.ROOT_NAME}/[01] A/[01] CU": {"id": "d2", "depth": 2, "items": [_it("old_f", "Cũ - X.pdf")]},
        }
        fake = FakeDrive(
            tree_by_id={
                "d1": [_it("d2", "[01] MOI", sc.FOLDER_MIME)],
                "d2": [_it("new_f", "Mới - X.pdf")],
            },
            search_items=[{"id": "d2", "name": "[01] MOI", "mimeType": sc.FOLDER_MIME}],
        )
        fake.infos["d2"] = {"id": "d2", "parents": ["d1"]}
        new_idx, errs, cnt, full = storage_indexer.incremental_crawl(
            fake, old_index, {"scanned_iso": "2026-11-17T06:00:00Z"}
        )
        self.assertFalse(full)
        self.assertEqual(errs, {})
        self.assertGreater(cnt, 0)
        self.assertNotIn(f"{sc.ROOT_NAME}/[01] A/[01] CU", new_idx)
        self.assertIn(f"{sc.ROOT_NAME}/[01] A/[01] MOI", new_idx)

    def test_naming_auditor_safe_fixes_skip_dmht_and_quarantine(self):
        idx = {
            "[A] STORAGE/[01] HỌC THUẬT": {
                "id": "d_ht",
                "depth": 1,
                "items": [
                    _it("s1", "Sách- Tác Giả.pdf"),
                    _it("dm1", "Danh Mục Hệ Thống - Duan_sohoa_logichocdaicuong", sc.SHEET_MIME),
                    _it("vd1", "LeMinhDat_26032571_LongTieng.mp4", "video/mp4"),
                ],
            },
            "[A] STORAGE/[07] KIỂM TRA/[03] TỆP TRÙNG LẶP/[01] TỔNG QUAN TRÙNG LẶP": {
                "id": "d_07",
                "depth": 3,
                "items": [_it("q1", "TongQuan.md", "text/markdown"), _it("q2", "TongQuan.md", "text/markdown")],
            },
        }
        plan = naming_auditor.build_fix_plan(idx, None)
        self.assertEqual([x["id"] for x in plan], ["s1"])
        self.assertEqual(plan[0]["new_name"], "Sách - Tác Giả.pdf")
        self.assertEqual(naming_auditor.audit(idx, branch=None), naming_auditor.audit(
            {"[A] STORAGE/[01] HỌC THUẬT": idx["[A] STORAGE/[01] HỌC THUẬT"]}, branch=None
        ))
        self.assertTrue(any(i[1] == "TRUNG_TEN" for i in naming_auditor.audit(idx, branch="[A] STORAGE/[07] KIỂM TRA")))

    def test_storage_cli_workflow_steps(self):
        dry_q = storage_cli.build_quick_steps(thuc_thi=False, dong_y=False, tai_len=False, nhanh=None, bo_qua_quet=False)
        flat_dry = " ".join(" ".join(cmd) for _, cmd in dry_q)
        self.assertNotIn("--thuc-thi", flat_dry)
        self.assertNotIn("--execute", flat_dry)

        exec_m = storage_cli.build_maintenance_steps(thuc_thi=True, dong_y=True, tai_len=True, nhanh=None, tang_cuong=True)
        flat_exec = " ".join(" ".join(cmd) for _, cmd in exec_m)
        self.assertIn("--thuc-thi", flat_exec)
        self.assertIn("--execute", flat_exec)
        self.assertIn("kiem-toan-tong-quan", flat_exec)


class TestNewModulesV3(unittest.TestCase):
    def test_transfer_manager_move_copy_and_undo(self):
        with tempfile.TemporaryDirectory() as td:
            old_env = os.environ.get("STORAGE_DATA_DIR")
            os.environ["STORAGE_DATA_DIR"] = td
            try:
                src_p = "[A] STORAGE/[05] SƯU TẦM/[01] SÁCH"
                dst_p = "[A] STORAGE/[02] NGHIÊN CỨU"
                index = {
                    "[A] STORAGE": {
                        "id": "root",
                        "depth": 0,
                        "items": [
                            _it("id_st", "[05] SƯU TẦM", sc.FOLDER_MIME),
                            _it("id_nc", "[02] NGHIÊN CỨU", sc.FOLDER_MIME),
                        ],
                    },
                    "[A] STORAGE/[05] SƯU TẦM": {
                        "id": "id_st",
                        "depth": 1,
                        "items": [_it("id_sach", "[01] SÁCH", sc.FOLDER_MIME)],
                    },
                    src_p: {
                        "id": "id_sach",
                        "depth": 2,
                        "items": [
                            _it("f_kant", "Phê Phán Lý Tính Thuần Túy - Immanuel Kant.pdf", size=5000),
                            _it("f_hegel", "Hiện Tượng Học Tinh Thần - Hegel.pdf", size=6000),
                        ],
                    },
                    dst_p: {
                        "id": "id_nc",
                        "depth": 1,
                        "items": [
                            _it("id_nc_tq", "[00] TỔNG QUAN", sc.FOLDER_MIME),
                            _it("id_nc_01", "[01] LỊCH SỬ", sc.FOLDER_MIME),
                        ],
                    },
                    f"{dst_p}/[00] TỔNG QUAN": {"id": "id_nc_tq", "depth": 2, "items": []},
                    f"{dst_p}/[01] LỊCH SỬ": {"id": "id_nc_01", "depth": 2, "items": []},
                }
                fake = FakeDrive(
                    tree_by_id={
                        "id_sach": list(index[src_p]["items"]),
                        "id_nc": list(index[dst_p]["items"]),
                    }
                )
                planned, skipped = transfer_manager.plan_transfers(
                    [
                        {
                            "op": "move",
                            "source": "f_kant",
                            "dest": dst_p,
                            "normalize_v6": True,
                            "auto_stt": True,
                        },
                        {
                            "op": "copy",
                            "source": src_p,
                            "dest": dst_p,
                            "normalize_v6": True,
                            "auto_stt": True,
                        },
                    ],
                    index,
                    drive=fake,
                    skip_duplicates=True,
                )
                self.assertEqual(skipped, [])
                self.assertGreaterEqual(len(planned), 3)
                # Thư mục sao chép vào dst_p (đã có [00], [01]) phải tự động nhận [02] SÁCH
                mkdir_ops = [op for op in planned if op["op"] == "mkdir_copy"]
                self.assertEqual(mkdir_ops[0]["target_name"], "[02] SÁCH")

                res = transfer_manager.execute_transfer_plan(planned, index, drive=fake)
                self.assertEqual(res["blocked"], [])
                self.assertEqual(res["failed"], [])
                self.assertEqual([it["id"] for it in index[src_p]["items"]], ["f_hegel"])

                reverted = transfer_manager.undo_transfer_batch(
                    batch_id=res["batch_id"], drive=fake, index=index, assume_yes=True
                )
                self.assertEqual(reverted, len(res["executed"]))
            finally:
                if old_env is None:
                    os.environ.pop("STORAGE_DATA_DIR", None)
                else:
                    os.environ["STORAGE_DATA_DIR"] = old_env

    def test_data_ingestor_staging_shortcut_and_dedup(self):
        with tempfile.TemporaryDirectory() as td:
            old_env = os.environ.get("STORAGE_DATA_DIR")
            os.environ["STORAGE_DATA_DIR"] = td
            try:
                dest_p = "[A] STORAGE/[05] SƯU TẦM/[01] SÁCH/[14] SỨC KHOẺ - Y HỌC"
                index = {
                    "[A] STORAGE": {"id": "root", "depth": 0, "items": []},
                    dest_p: {
                        "id": "id_yhoc",
                        "depth": 3,
                        "items": [
                            _it("existing_1", "Atlas Giải Phẫu Người - Frank Netter.pdf", size=12345),
                        ],
                    },
                }
                ingest_id = sc.ingest_folder_id()
                ext_folder_id = "ext_med_folder"
                fake = FakeDrive(
                    tree_by_id={
                        ingest_id: [
                            {
                                "id": "sc_med",
                                "name": "Sách Ngành Y học ",
                                "mimeType": sc.SHORTCUT_MIME,
                            }
                        ],
                        ext_folder_id: [
                            _it("ext_dup", "Atlas Giải Phẫu Người - Frank Netter (1).pdf", size=12345),
                            _it("ext_new", "Bệnh Học Nội Khoa - Đại Học Y Hà Nội.pdf", size=54321),
                        ],
                    }
                )
                fake.infos["sc_med"] = {
                    "id": "sc_med",
                    "name": "Sách Ngành Y học ",
                    "mimeType": sc.SHORTCUT_MIME,
                    "shortcutDetails": {"targetId": ext_folder_id, "targetMimeType": sc.FOLDER_MIME},
                }
                fake.infos[ext_folder_id] = {"id": ext_folder_id, "name": "Sách Ngành Y học ", "mimeType": sc.FOLDER_MIME}

                bundle = data_ingestor.plan_ingest_from_staging(
                    index,
                    fake,
                    explicit_dest=dest_p,
                )
                self.assertEqual(len(bundle["duplicates_skipped"]), 1)
                self.assertEqual(bundle["duplicates_skipped"][0]["source_id"], "ext_dup")
                copy_ops = [op for op in bundle["planned_ops"] if op["op"] == "copy_remote_file"]
                self.assertEqual(len(copy_ops), 1)
                self.assertEqual(copy_ops[0]["source_id"], "ext_new")
                self.assertEqual(copy_ops[0]["target_name"], "Bệnh Học Nội Khoa - Đại Học Y Hà Nội.pdf")

                exec_res = data_ingestor.execute_ingest_plan(bundle, index, drive=fake, init_tong_quan=False)
                self.assertEqual(exec_res["failed"], [])
                self.assertEqual(len(fake.copied), 1)
            finally:
                if old_env is None:
                    os.environ.pop("STORAGE_DATA_DIR", None)
                else:
                    os.environ["STORAGE_DATA_DIR"] = old_env

    def test_storage_inspector_search_tongquan_heal_and_empty_folders(self):
        with tempfile.TemporaryDirectory() as td:
            old_env = os.environ.get("STORAGE_DATA_DIR")
            os.environ["STORAGE_DATA_DIR"] = td
            try:
                p_sach = "[A] STORAGE/[05] SƯU TẦM/[01] SÁCH/[01] TRIẾT HỌC"
                p_empty = "[A] STORAGE/[05] SƯU TẦM/[01] SÁCH/[02] NHÁNH RỖNG"
                index = {
                    "[A] STORAGE": {"id": "root", "depth": 0, "items": []},
                    p_sach: {
                        "id": "id_th",
                        "depth": 3,
                        "items": [_it("f1", "Siêu Hình Học - Aristotle.pdf", size=4096)],
                    },
                    p_empty: {"id": "id_emp", "depth": 3, "items": []},
                }
                hits = storage_inspector.search_index(index, query="Aristotle")
                self.assertEqual(len(hits), 1)
                self.assertEqual(hits[0]["id"], "f1")

                missing = storage_inspector.audit_tong_quan_coverage(index)
                missing_paths = {m["path"] for m in missing}
                self.assertIn(p_sach, missing_paths)
                self.assertNotIn(p_empty, missing_paths)

                fake = FakeDrive(tree_by_id={"id_th": list(index[p_sach]["items"])})
                heal_res = storage_inspector.heal_tong_quan_coverage(missing, index, drive=fake)
                self.assertGreaterEqual(heal_res["created_tq_folders"], 1)
                self.assertGreaterEqual(heal_res["created_overview_mds"], 1)

                empties = storage_inspector.find_empty_folders_bottom_up(index)
                self.assertEqual([e["path"] for e in empties], [p_empty])
            finally:
                if old_env is None:
                    os.environ.pop("STORAGE_DATA_DIR", None)
                else:
                    os.environ["STORAGE_DATA_DIR"] = old_env

    @staticmethod
    def _build_sample_docx_bytes(title: str, author: str, heading: str, body: str) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(
                "docProps/core.xml",
                f"""<?xml version="1.0" encoding="UTF-8"?>
                <cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
                                   xmlns:dc="http://purl.org/dc/elements/1.1/">
                    <dc:title>{title}</dc:title>
                    <dc:creator>{author}</dc:creator>
                </cp:coreProperties>""",
            )
            zf.writestr(
                "docProps/app.xml",
                """<?xml version="1.0" encoding="UTF-8"?>
                <Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">
                    <Pages>12</Pages>
                </Properties>""",
            )
            zf.writestr(
                "word/document.xml",
                f"""<?xml version="1.0" encoding="UTF-8"?>
                <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
                  <w:body>
                    <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>{heading}</w:t></w:r></w:p>
                    <w:p><w:r><w:t>{body}</w:t></w:r></w:p>
                  </w:body>
                </w:document>""",
            )
        return buf.getvalue()

    @staticmethod
    def _build_sample_epub_bytes(title: str, author: str, lang: str, chapter_html: str) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("mimetype", "application/epub+zip")
            zf.writestr(
                "META-INF/container.xml",
                """<?xml version="1.0"?>
                <container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
                  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
                </container>""",
            )
            zf.writestr(
                "OEBPS/content.opf",
                f"""<?xml version="1.0" encoding="UTF-8"?>
                <package xmlns="http://www.idpf.org/2007/opf" version="2.0">
                  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
                    <dc:title>{title}</dc:title>
                    <dc:creator>{author}</dc:creator>
                    <dc:language>{lang}</dc:language>
                    <dc:publisher>NXB Tri Thức</dc:publisher>
                  </metadata>
                  <manifest><item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/></manifest>
                  <spine><itemref idref="ch1"/></spine>
                </package>""",
            )
            zf.writestr("OEBPS/ch1.xhtml", chapter_html)
        return buf.getvalue()

    @staticmethod
    def _build_sample_mobi_bytes(title: str, author: str, html_body: str) -> bytes:
        import struct as _st
        text_bytes = html_body.encode("utf-8")
        author_b = author.encode("utf-8")
        title_b = title.encode("utf-8")
        exth_rec1 = _st.pack(">II", 100, 8 + len(author_b)) + author_b
        exth_rec2 = _st.pack(">II", 503, 8 + len(title_b)) + title_b
        exth_body = exth_rec1 + exth_rec2
        exth_pad = (4 - (len(exth_body) % 4)) % 4
        exth_hdr = b"EXTH" + _st.pack(">II", 12 + len(exth_body) + exth_pad, 2) + exth_body + (b"\x00" * exth_pad)

        palmdoc = _st.pack(">HHIHHHH", 1, 0, len(text_bytes), 1, 4096, 0, 0)
        mobi_len = 232
        mobi_hdr = bytearray(mobi_len)
        mobi_hdr[0:4] = b"MOBI"
        _st.pack_into(">I", mobi_hdr, 4, mobi_len)
        _st.pack_into(">I", mobi_hdr, 112, 0x40)  # EXTH flag at rec0[128:132] (16 + 112 = 128)
        rec0 = palmdoc + bytes(mobi_hdr) + exth_hdr

        num_records = 2
        header_size = 78 + num_records * 8 + 2
        rec0_off = header_size
        rec1_off = rec0_off + len(rec0)

        pdb = bytearray(78)
        pdb[:min(31, len(title_b))] = title_b[:31]
        pdb[60:68] = b"BOOKMOBI"
        _st.pack_into(">H", pdb, 76, num_records)
        rec_table = _st.pack(">II", rec0_off, 0) + _st.pack(">II", rec1_off, 0) + b"\x00\x00"
        return bytes(pdb) + rec_table + rec0 + text_bytes

    def test_file_reader_multiformat_and_flags(self):
        with tempfile.TemporaryDirectory() as td:
            td_p = Path(td)

            # 1. DOCX
            docx_p = td_p / "Siêu Hình Học - Aristotle.docx"
            docx_p.write_bytes(
                self._build_sample_docx_bytes(
                    "Siêu Hình Học",
                    "Aristotle",
                    "Chương 1: Bản Thể Luận",
                    "Triết học nghiên cứu về bản thể, nhận thức luận, siêu hình học và đạo đức học của con người.",
                )
            )
            r_docx = file_reader.read_local_file(docx_p)
            self.assertEqual(r_docx["status"], "ok")
            self.assertEqual(r_docx["metadata"]["title"], "Siêu Hình Học")
            self.assertEqual(r_docx["metadata"]["author"], "Aristotle")
            self.assertEqual(r_docx["stats"]["pages"], 12)
            self.assertIn("Chương 1: Bản Thể Luận", r_docx["outline"])

            # 2. EPUB
            epub_p = td_p / "Giải Phẫu Thần Kinh - Frank Netter.epub"
            epub_p.write_bytes(
                self._build_sample_epub_bytes(
                    "Giải Phẫu Thần Kinh Lâm Sàng",
                    "Frank Netter",
                    "vi",
                    "<html><body><h1>Hệ Thần Kinh Trung Ương</h1><p>Giải phẫu học và sinh lý học thần kinh trong y học lâm sàng.</p></body></html>",
                )
            )
            r_epub = file_reader.read_local_file(epub_p)
            self.assertEqual(r_epub["status"], "ok")
            self.assertEqual(r_epub["metadata"]["author"], "Frank Netter")
            self.assertIn("Hệ Thần Kinh Trung Ương", r_epub["outline"])
            self.assertIn("sinh lý học thần kinh", r_epub["text"])

            # 3. MOBI
            mobi_p = td_p / "Tử Vi Đẩu Số Tân Biên - Vân Đằng Thái Thứ Lang.mobi"
            mobi_p.write_bytes(
                self._build_sample_mobi_bytes(
                    "Tử Vi Đẩu Số Tân Biên",
                    "Vân Đằng Thái Thứ Lang",
                    "<html><body><h1>Luận Giải Mệnh Cung</h1><p>Tử vi, kinh dịch và phong thủy trong huyền học cổ truyền.</p></body></html>",
                )
            )
            r_mobi = file_reader.read_local_file(mobi_p)
            self.assertEqual(r_mobi["status"], "ok")
            self.assertEqual(r_mobi["metadata"]["title"], "Tử Vi Đẩu Số Tân Biên")
            self.assertEqual(r_mobi["metadata"]["author"], "Vân Đằng Thái Thứ Lang")
            self.assertIn("Luận Giải Mệnh Cung", r_mobi["outline"])

            # 4. PPTX & XLSX
            pptx_p = td_p / "Bài Giảng Logic - Học Thuật.pptx"
            with zipfile.ZipFile(pptx_p, "w") as zf:
                zf.writestr(
                    "ppt/presentation.xml",
                    "<p:presentation xmlns:p='http://schemas.openxmlformats.org/presentationml/2006/main'/>",
                )
                zf.writestr(
                    "ppt/slides/slide1.xml",
                    "<p:sld xmlns:p='http://schemas.openxmlformats.org/presentationml/2006/main' "
                    "xmlns:a='http://schemas.openxmlformats.org/drawingml/2006/main'>"
                    "<a:p><a:r><a:t>Nhập Môn Logic Học</a:t></a:r></a:p></p:sld>",
                )
            r_pptx = file_reader.read_local_file(pptx_p)
            self.assertEqual(r_pptx["stats"]["slides"], 1)
            self.assertIn("Slide 1: Nhập Môn Logic Học", r_pptx["outline"])

            xlsx_p = td_p / "Bảng Điểm - Học Thuật.xlsx"
            with zipfile.ZipFile(xlsx_p, "w") as zf:
                zf.writestr(
                    "xl/workbook.xml",
                    "<workbook xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'>"
                    "<sheets><sheet name='K70 Triết Học' sheetId='1'/></sheets></workbook>",
                )
                zf.writestr(
                    "xl/sharedStrings.xml",
                    "<sst xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'>"
                    "<si><t>Sinh Viên Xuất Sắc</t></si></sst>",
                )
                zf.writestr(
                    "xl/worksheets/sheet1.xml",
                    "<worksheet xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'>"
                    "<sheetData><row r='1'><c r='A1' t='s'><v>0</v></c></row></sheetData></worksheet>",
                )
            r_xlsx = file_reader.read_local_file(xlsx_p)
            self.assertIn("K70 Triết Học", r_xlsx["outline"])
            self.assertIn("Sinh Viên Xuất Sắc", r_xlsx["text"])

            # 5. PDF (bản có văn bản vs bản scan cần OCR vs sai khớp định dạng)
            pdf_text_p = td_p / "Triết Học Hiện Sinh - Jean Paul Sartre.pdf"
            long_pdf_line = "Triet hoc hien sinh va nhan thuc luan trong the ky hai muoi cua Sartre va Heidegger. " * 4
            pdf_text_p.write_bytes(
                b"%PDF-1.4\n1 0 obj << /Type /Page >> endobj\n"
                b"2 0 obj << /Title (Triet Hoc Hien Sinh) /Author (Jean Paul Sartre) >> endobj\n"
                b"3 0 obj << /Length 200 >>\nstream\nBT (" + long_pdf_line.encode("ascii") + b") Tj ET\nendstream\nendobj\n%%EOF"
            )
            r_pdf = file_reader.read_local_file(pdf_text_p)
            self.assertEqual(r_pdf["metadata"]["author"], "Jean Paul Sartre")
            self.assertNotIn("can_ocr", r_pdf["flags"])

            pdf_scan_p = td_p / "Bản Scan Cổ - Tư Liệu.pdf"
            pdf_scan_p.write_bytes(
                b"%PDF-1.4\n1 0 obj << /Type /Page >> endobj\n2 0 obj << /Type /Page >> endobj\n%%EOF"
            )
            r_scan = file_reader.read_local_file(pdf_scan_p)
            self.assertIn("can_ocr", r_scan["flags"])

            mismatch_p = td_p / "Tệp Đổi Sai Đuôi - Kiểm Thử.pdf"
            with zipfile.ZipFile(mismatch_p, "w") as zf:
                zf.writestr("hello.txt", "Nội dung bên trong tệp nén ZIP nhưng đặt đuôi .pdf")
            r_mis = file_reader.read_local_file(mismatch_p)
            self.assertIn("sai_khop_dinh_dang", r_mis["flags"])

            # 6. JSON hỏng
            bad_json_p = td_p / "bad_config.json"
            bad_json_p.write_text("{invalid_json: ", encoding="utf-8")
            r_bad_json = file_reader.read_local_file(bad_json_p)
            self.assertIn("tep_hong", r_bad_json["flags"])

    def test_content_analyzer_lang_tfidf_topic_simhash_rename_and_search(self):
        with tempfile.TemporaryDirectory() as td:
            old_env = os.environ.get("STORAGE_DATA_DIR")
            os.environ["STORAGE_DATA_DIR"] = td
            try:
                vi_body = (
                    "Giải phẫu học và sinh lý học hệ thần kinh trung ương trong y học lâm sàng giúp bác sĩ "
                    "chẩn đoán và điều trị các bệnh lý thần kinh, đột quỵ não và chấn thương sọ não tại bệnh viện. "
                    "Nghiên cứu giải phẫu thần kinh và bệnh học nội khoa là nền tảng của y học hiện đại."
                ) * 3
                en_body = (
                    "Quantum mechanics and general relativity are the two foundational pillars of modern theoretical physics. "
                    "In quantum physics, wave functions and quantum entanglement describe subatomic particles and fields "
                    "with remarkable mathematical precision across experimental physics laboratories."
                ) * 3

                b_doc1 = self._build_sample_docx_bytes(
                    "Giải Phẫu Thần Kinh Lâm Sàng",
                    "Frank Netter",
                    "Chương 1: Hệ Thần Kinh",
                    vi_body,
                )
                b_doc2 = self._build_sample_epub_bytes(
                    "Giải Phẫu Thần Kinh Lâm Sàng",
                    "Frank Netter",
                    "vi",
                    f"<html><body><h1>Chương 1: Hệ Thần Kinh</h1><p>{vi_body}</p></body></html>",
                )
                b_doc3 = self._build_sample_docx_bytes(
                    "Quantum Physics Foundations",
                    "Richard Feynman",
                    "Chapter 1: Quantum Mechanics",
                    en_body,
                )

                p_unclass = "[A] STORAGE/[05] SƯU TẦM/[01] SÁCH/[00] CHƯA PHÂN LOẠI"
                p_yhoc = "[A] STORAGE/[05] SƯU TẦM/[01] SÁCH/[14] SỨC KHOẺ - Y HỌC"
                index = {
                    "[A] STORAGE": {"id": "root", "depth": 0, "items": []},
                    p_unclass: {
                        "id": "dir_un",
                        "depth": 3,
                        "items": [
                            _it("f_opaque", "scan_001.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", size=len(b_doc1)),
                            _it("f_en", "Quantum Physics Foundations.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", size=len(b_doc3)),
                        ],
                    },
                    p_yhoc: {
                        "id": "dir_yh",
                        "depth": 3,
                        "items": [
                            _it("f_epub", "Giải Phẫu Thần Kinh Lâm Sàng - Frank Netter.epub", mime="application/epub+zip", size=len(b_doc2)),
                            _it("f_huge", "Video Bài Giảng Giải Phẫu - Y Học.mp4", mime="video/mp4", size=90 * 1024 * 1024),
                        ],
                    },
                }
                fake = FakeDrive(
                    downloads={
                        "f_opaque": b_doc1,
                        "f_epub": b_doc2,
                        "f_en": b_doc3,
                    }
                )

                # 1. Trích xuất lô + kiểm tra cache hit ở lần gọi thứ 2
                ext_res1 = file_reader.batch_extract(index, fake, max_mb=50.0, workers=2)
                self.assertEqual(ext_res1["total"], 4)
                self.assertEqual(ext_res1["cache_hits"], 0)
                self.assertEqual(ext_res1["by_status"].get("qua_dung_luong"), 1)

                ext_res2 = file_reader.batch_extract(index, fake, max_mb=50.0, workers=2)
                self.assertEqual(ext_res2["cache_hits"], 4)

                # 2. Phân tích toàn diện: ngôn ngữ, chủ đề, cờ lệch chủ đề, SimHash gần trùng, gợi ý tên V6
                recs = file_reader.iter_cached_records(include_text=True, index=index)
                summary = content_analyzer.analyze_records(recs, persist_cache=True)
                self.assertGreaterEqual(summary["by_language"].get("vi", 0), 2)
                self.assertGreaterEqual(summary["by_language"].get("en", 0), 1)

                by_id = {r["id"]: r for r in summary["records"]}
                self.assertEqual(by_id["f_opaque"]["analysis"]["topic"], "Sức Khoẻ - Y Học")
                self.assertIn("lech_chu_de", by_id["f_opaque"]["flags"])
                self.assertEqual(by_id["f_en"]["analysis"]["topic"], "Khoa Học - Công Nghệ")

                # SimHash phát hiện f_opaque (.docx) và f_epub (.epub) có cùng nội dung văn bản dù khác định dạng
                near_pairs = summary["duplicates"]["near_pairs"]
                self.assertGreaterEqual(len(near_pairs), 1)
                pair_ids = {near_pairs[0]["a"]["id"], near_pairs[0]["b"]["id"]}
                self.assertEqual(pair_ids, {"f_opaque", "f_epub"})

                # Gợi ý tên Chuẩn V6 từ siêu dữ liệu cho `scan_001.docx` và `Quantum Physics Foundations.docx`
                sug_map = {s["id"]: s["new_name"] for s in summary["rename_suggestions"]}
                self.assertEqual(sug_map.get("f_opaque"), "Giải Phẫu Thần Kinh Lâm Sàng - Frank Netter.docx")
                self.assertEqual(sug_map.get("f_en"), "Quantum Physics Foundations - Richard Feynman.docx")

                # Áp dụng đổi tên và hoàn tác
                apply_res = content_analyzer.apply_rename_suggestions(
                    summary["rename_suggestions"], fake, index=index, execute=True
                )
                self.assertEqual(apply_res["renamed"], 2)
                self.assertEqual(index[p_unclass]["items"][0]["name"], "Giải Phẫu Thần Kinh Lâm Sàng - Frank Netter.docx")

                undone = content_analyzer.undo_rename_batch(apply_res["batch_id"], fake, index=index)
                self.assertEqual(undone, 2)
                self.assertEqual(index[p_unclass]["items"][0]["name"], "scan_001.docx")

                # Tìm kiếm toàn văn không dấu
                hits = content_analyzer.search_content_cache(query="chan thương so nao", index=index)
                self.assertGreaterEqual(len(hits), 2)

                # Xuất báo cáo Markdown & CSV
                md_p, csv_p = content_analyzer.write_analysis_reports(summary)
                self.assertTrue(md_p.exists())
                self.assertTrue(csv_p.exists())
            finally:
                if old_env is None:
                    os.environ.pop("STORAGE_DATA_DIR", None)
                else:
                    os.environ["STORAGE_DATA_DIR"] = old_env

    def test_github_sync_security_audit_and_dry_run(self):
        # 1. Kiểm tra deploy_sync bỏ qua các tệp cấu hình riêng của Git/GitHub khi đẩy lên Drive
        self.assertTrue(deploy_sync.should_skip(Path(".git")))
        self.assertTrue(deploy_sync.should_skip(Path(".github")))
        self.assertTrue(deploy_sync.should_skip(Path(".gitignore")))
        self.assertTrue(deploy_sync.should_skip(Path("README.md")))
        self.assertFalse(deploy_sync.should_skip(Path("github_sync.py")))

        # 2. Kiểm tra quét bảo mật trên kho mã nguồn thật (phải sạch 100%)
        real_findings = github_sync.audit_repo_security(REPO_ROOT)
        self.assertEqual(real_findings, [])

        # 3. Kiểm tra phát hiện token/khóa nhạy cảm và tệp dữ liệu cấm trên thư mục giả lập
        with tempfile.TemporaryDirectory() as td:
            td_p = Path(td)
            (td_p / "clean.py").write_text("print('an toan')\n", encoding="utf-8")
            self.assertEqual(github_sync.audit_repo_security(td_p), [])

            fake_token = "ghp_" + ("A1b2C3d4E5f6" * 3)
            (td_p / "leak.py").write_text(f"TOKEN = '{fake_token}'\n", encoding="utf-8")
            (td_p / "storage_index.json.gz").write_bytes(b"fake_index")
            findings = github_sync.audit_repo_security(td_p)
            codes = {f["code"] for f in findings}
            self.assertIn("DU_LIEU_KHO_TRONG_GIT", codes)
            self.assertIn("GITHUB_TOKEN", codes)

            # Chế độ chạy thử push_to_github phải chặn ngay khi phát hiện vi phạm bảo mật
            res_blocked = github_sync.push_to_github(
                td_p, message="test", execute=False, run_tests=False
            )
            self.assertFalse(res_blocked["ok"])
            self.assertEqual(res_blocked["stage"], "security_audit")

            # Sau khi xóa tệp vi phạm, chế độ chạy thử push_to_github trả về ok=True, dry_run=True
            (td_p / "leak.py").unlink()
            (td_p / "storage_index.json.gz").unlink()
            res_dry = github_sync.push_to_github(
                td_p, message="test clean", execute=False, run_tests=False
            )
            self.assertTrue(res_dry["ok"])
            self.assertTrue(res_dry["dry_run"])


if __name__ == "__main__":
    unittest.main()
