"""Bộ kiểm thử chuyên sâu cho các nâng cấp v4.0.0:
- Chuẩn Danh Mục V7 (Zero-Collision + Tinh gọn Thông minh Phương án 2 + 5 mã kiểm toán + hoàn tác)
- SQLite Store (WAL + FTS5 + Unified Undo Journal)
- Dual Drive Backends (GoogleDriveAPIClient OAuth 2.0 giả lập + drive_factory)
- Rác hệ thống MACOSX, Doctor, Watcher, Release Bundle Staging
- CLI hợp nhất (`astorage`) & Web Dashboard FastAPI (`astorage ui`)
"""

from __future__ import annotations

import json
import os
import socket
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

from storage_suite import __version__
from storage_suite import core as sc
from storage_suite.cli import main as cli_main
from storage_suite.cli import pipelines
from storage_suite.ops import dedup, doctor, watcher
from storage_suite.sync import drive_deploy


def _it(fid: str, name: str, mime: str = "application/pdf", size: int = 1024, mod: str = "2026-11-20T06:00:00Z") -> dict:
    d: Dict[str, Any] = {"id": fid, "name": name, "mimeType": mime, "modifiedTime": mod}
    if mime != sc.FOLDER_MIME and mime not in sc.GOOGLE_NATIVE_MIMES:
        d["size"] = size
    return d


class _MockDrive:
    backend_name = "mock"

    def __init__(self) -> None:
        self.renamed: List[tuple[str, str]] = []
        self.moved: List[tuple[str, str]] = []
        self.ensured: List[tuple[str, str]] = []

    def ensure_folder(self, name: str, parent_id: str) -> str:
        fid = f"dir_{len(self.ensured)}"
        self.ensured.append((name, parent_id))
        return fid

    def rename(self, file_id: str, new_name: str) -> None:
        self.renamed.append((file_id, new_name))

    def move(self, file_id: str, new_parent_id: str) -> None:
        self.moved.append((file_id, new_parent_id))

    def batch_rename(self, items):
        out = []
        for fid, nm in items:
            self.rename(fid, nm)
            out.append((fid, True, ""))
        return out

    def batch_move(self, items, workers: int = 8):
        out = []
        for fid, dest in items:
            self.move(fid, dest)
            out.append((fid, True, ""))
        return out

    def search(self, **kwargs):
        return [
            _it("ch_1", "Đề cương môn Đạo Đức Học - PHI3186.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", mod="2026-11-21T05:00:00Z"),
            _it("ch_2", "Giáo Trình Chuẩn - PHI1007.pdf", "application/pdf", mod="2026-11-21T05:01:00Z"),
        ]


class TestCatalogV7Spec(unittest.TestCase):
    def test_v7_single_separator_and_segment_cleanup(self):
        self.assertEqual(
            sc.normalize_catalog_title("[A] STORAGE"),
            "Danh Mục Hệ Thống - Storage",
        )
        self.assertEqual(
            sc.normalize_catalog_title("[A] STORAGE", is_list_copy=True),
            "Danh Mục Hệ Thống - Storage, Bản Danh Sách",
        )
        self.assertEqual(
            sc.normalize_catalog_title("[A] STORAGE/[01] HỌC THUẬT/[01] ĐẠI HỌC/[01] [USSH] TRƯỜNG ĐH KHXH&NV"),
            "Danh Mục Hệ Thống - USSH: Trường ĐH KHXH&NV",
        )
        self.assertEqual(
            sc.normalize_catalog_title("[A] STORAGE/[05] SƯU TẦM/[01] SÁCH/[03] TÔN GIÁO - TÍN NGƯỠNG"),
            "Danh Mục Hệ Thống - Tôn Giáo – Tín Ngưỡng",
        )
        self.assertEqual(
            sc.normalize_catalog_title("[A] STORAGE/[01] ĐỀ/[01] BỘ BÀI GIẢNG TOÁN 12(CHƯƠNG-1)TỪ CƠ BẢN ĐẾN NÂNG CAO"),
            "Danh Mục Hệ Thống - Bộ Bài Giảng Toán 12 (Chương 1) Từ Cơ Bản Đến Nâng Cao",
        )
        # Bảo toàn duy nhất 1 dấu `" - "` theo Chuẩn V7
        for p in (
            "[A] STORAGE/[01] [USSH] TRƯỜNG ĐH KHXH&NV",
            "[A] STORAGE/[05] SƯU TẦM/[01] SÁCH/[14] SỨC KHOẺ - Y HỌC",
            "[A] STORAGE/[01] ĐỀ/CHƯƠNG VI - K12 - KNTT",
        ):
            t = sc.normalize_catalog_title(p)
            self.assertEqual(t.count(" - "), 1, f"Multiple ' - ' in: {t}")

    def test_zero_collision_disambiguation(self):
        paths = [
            "[A] STORAGE",
            "[A] STORAGE/[01] HỌC THUẬT/[04] CHỨNG CHỈ/[01] IELTS/[01] NGỌC BÁCH/[01] HANDOUT",
            "[A] STORAGE/[01] HỌC THUẬT/[04] CHỨNG CHỈ/[01] IELTS/[02] KIÊN LUYỆN/[01] HANDOUT",
            "[A] STORAGE/[01] HỌC THUẬT/[01] ĐẠI HỌC/[02] [VNU-LIC] THƯ VIỆN/[01] ĐẠO - TRƯƠNG LẬP VĂN/[01] CẤU PHẦN SÁCH",
            "[A] STORAGE/[01] HỌC THUẬT/[01] ĐẠI HỌC/[02] [VNU-LIC] THƯ VIỆN/[02] LOGIC HỌC/[01] CẤU PHẦN SÁCH",
        ]
        titles = sc.compute_catalog_titles(paths)
        self.assertEqual(len(titles), len(paths))
        normed = [sc.strip_accents(v).lower() for v in titles.values()]
        self.assertEqual(len(normed), len(set(normed)), f"Collisions found: {titles}")
        self.assertIn("Ngọc Bách", titles[paths[1]])
        self.assertIn("Kiên Luyện", titles[paths[2]])

    def test_smart_pruning_audit_migration_and_undo(self):
        # Xây chỉ mục mini có: cấp 1..5, cấp 5 rỗng, cấp 6 lớn (16 tệp), cấp 7 sâu, MACOSX rác, và bảng mồ côi
        d6_large_path = "[A] STORAGE/[01] HỌC THUẬT/[03] PHỔ THÔNG/[01] THEO MÔN/[01] TOÁN HỌC/[01] TOÁN/[01] KHO ĐỀ LỚN"
        d7_deep_path = f"{d6_large_path}/[01] HANDOUT"
        macosx_path = "[A] STORAGE/[01] HỌC THUẬT/[03] PHỔ THÔNG/[01] MACOSX"
        d5_empty_path = "[A] STORAGE/[01] HỌC THUẬT/[03] PHỔ THÔNG/[01] THEO MÔN/[01] TOÁN HỌC/[02] LÁ RỖNG"

        index = {
            "[A] STORAGE": {"id": "root", "depth": 0, "items": [_it("f00", "[00] TỔNG QUAN", sc.FOLDER_MIME), _it("f01", "[01] HỌC THUẬT", sc.FOLDER_MIME)]},
            "[A] STORAGE/[00] TỔNG QUAN": {"id": "f00", "depth": 1, "items": [_it("sh_root", "Danh Mục Hệ Thống - Storage", sc.SHEET_MIME), _it("f_ds", "[01] DANH SÁCH", sc.FOLDER_MIME)]},
            "[A] STORAGE/[00] TỔNG QUAN/[01] DANH SÁCH": {
                "id": "f_ds", "depth": 2,
                "items": [_it("sh_list", "Danh Mục Hệ Thống - Storage (Bản Danh Sách)", sc.SHEET_MIME)],
            },
            "[A] STORAGE/[01] HỌC THUẬT": {"id": "f01", "depth": 1, "items": [_it("f01_03", "[03] PHỔ THÔNG", sc.FOLDER_MIME)]},
            "[A] STORAGE/[01] HỌC THUẬT/[03] PHỔ THÔNG": {"id": "f01_03", "depth": 2, "items": [_it("f_mon", "[01] THEO MÔN", sc.FOLDER_MIME), _it("f_mac", "[01] MACOSX", sc.FOLDER_MIME)]},
            macosx_path: {"id": "f_mac", "depth": 3, "items": [_it("mac_f", "junk.pdf")]},
            "[A] STORAGE/[01] HỌC THUẬT/[03] PHỔ THÔNG/[01] THEO MÔN": {"id": "f_mon", "depth": 3, "items": [_it("f_toan", "[01] TOÁN HỌC", sc.FOLDER_MIME)]},
            "[A] STORAGE/[01] HỌC THUẬT/[03] PHỔ THÔNG/[01] THEO MÔN/[01] TOÁN HỌC": {"id": "f_toan", "depth": 4, "items": [_it("f_t1", "[01] TOÁN", sc.FOLDER_MIME), _it("f_empty5", "[02] LÁ RỖNG", sc.FOLDER_MIME)]},
            "[A] STORAGE/[01] HỌC THUẬT/[03] PHỔ THÔNG/[01] THEO MÔN/[01] TOÁN HỌC/[01] TOÁN": {"id": "f_t1", "depth": 5, "items": [_it("f_d6", "[01] KHO ĐỀ LỚN", sc.FOLDER_MIME)]},
            d5_empty_path: {"id": "f_empty5", "depth": 5, "items": []},
            d6_large_path: {"id": "f_d6", "depth": 6, "items": [_it(f"pdf_{i}", f"Đề {i} - Toán.pdf") for i in range(16)] + [_it("f_d7", "[01] HANDOUT", sc.FOLDER_MIME)]},
            d7_deep_path: {"id": "f_d7", "depth": 7, "items": [_it("h1", "Handout - Toán.pdf")]},
            # Cây gương [01] DANH SÁCH hiện có
            sc.catalog_folder_for_path(macosx_path): {"id": "ds_mac", "depth": 5, "items": [_it("sh_mac", "Danh Mục Hệ Thống - Macosx", sc.SHEET_MIME)]},
            sc.catalog_folder_for_path(d6_large_path): {"id": "ds_d6", "depth": 8, "items": [_it("sh_d6", "Danh Mục Hệ Thống - Kho Đề Lớn", sc.SHEET_MIME)]},
            sc.catalog_folder_for_path(d7_deep_path): {"id": "ds_d7", "depth": 9, "items": [_it("sh_d7", "Danh Mục Hệ Thống - Handout", sc.SHEET_MIME)]},
            "[A] STORAGE/[00] TỔNG QUAN/[01] DANH SÁCH/[09] THƯ MỤC ĐÃ XÓA": {"id": "ds_orph", "depth": 3, "items": [_it("sh_orph", "Danh Mục Hệ Thống - Thư Mục Đã Xóa", sc.SHEET_MIME)]},
        }

        self.assertFalse(sc.should_have_catalog(macosx_path, index).include)
        self.assertFalse(sc.should_have_catalog(d5_empty_path, index).include)
        self.assertTrue(sc.should_have_catalog(d6_large_path, index).include)  # promoted (16 >= 15)
        self.assertFalse(sc.should_have_catalog(d7_deep_path, index).include)  # pruned (depth 7)

        findings = sc.audit_catalog_tree(index)
        codes = {f.code for f in findings}
        self.assertIn("DANH_MUC_RAC_KY_THUAT", codes)
        self.assertIn("DANH_MUC_MO_COI", codes)
        self.assertIn("DANH_MUC_CO_THE_TINH_GON", codes)
        self.assertIn("DANH_MUC_SAI_TEN", codes)

        plan = sc.build_catalog_migration_plan(index)
        self.assertEqual(plan["summary"]["prunes_junk_count"], 1)
        self.assertEqual(plan["summary"]["prunes_smart_count"], 2)  # d7 + orphan
        self.assertEqual(plan["summary"]["renames_count"], 1)  # Storage (Bản Danh Sách) -> Storage, Bản Danh Sách

        with tempfile.TemporaryDirectory() as td:
            db = sc.StorageDB(Path(td) / "test.db")
            drive = _MockDrive()
            res = sc.apply_catalog_migration_plan(drive, plan, execute=True, apply_prunes=True, db=db)
            self.assertEqual(res["renamed"], 1)
            self.assertEqual(res["pruned"], 3)
            self.assertTrue(res["batch_id"].startswith("catalog_v7_"))

            # Kiểm chứng Unified Undo Journal hoàn tác ngược 100%
            undo_res = db.undo_batch(drive, res["batch_id"], execute=True)
            self.assertTrue(undo_res["ok"])
            self.assertEqual(undo_res["reverted"], 4)
            db.close()


class TestSQLiteStoreAndFTS5(unittest.TestCase):
    def test_import_export_fts5_and_undo_journal(self):
        idx = {
            "[A] STORAGE": {"id": "r0", "depth": 0, "items": [_it("d1", "[01] HỌC THUẬT", sc.FOLDER_MIME)]},
            "[A] STORAGE/[01] HỌC THUẬT": {
                "id": "d1",
                "depth": 1,
                "items": [
                    _it("f1", "Giáo Trình Triết Học Mác-Lênin - PHI1007.pdf", size=500_000),
                    _it("f2", "Đề Cương Đạo Đức Học - PHI3186.docx", size=120_000),
                ],
            },
        }
        with tempfile.TemporaryDirectory() as td:
            with sc.StorageDB(Path(td) / "storage.db") as db:
                counts = db.import_index_dict(idx)
                self.assertEqual(counts["folders"], 2)
                self.assertEqual(counts["items"], 3)

                exported = db.export_index_dict()
                self.assertEqual(len(exported["[A] STORAGE/[01] HỌC THUẬT"]["items"]), 2)

                # FTS5 tìm cả không dấu & có dấu
                hits = db.search_fts("triet hoc")
                self.assertEqual(len(hits), 1)
                self.assertEqual(hits[0]["id"], "f1")

                db.update_fts_keywords("f2", "kant aristotle dao duc hoc")
                hits2 = db.search_fts("aristotle")
                self.assertEqual(len(hits2), 1)
                self.assertEqual(hits2[0]["id"], "f2")

                st = db.stats_summary()
                self.assertEqual(st["total_files"], 2)
                self.assertEqual(st["total_bytes"], 620_000)


class TestGoogleDriveAPIClientMocked(unittest.TestCase):
    def test_oauth_drive_api_protocol_operations(self):
        class _Exec:
            def __init__(self, payload):
                self._payload = payload

            def execute(self):
                return self._payload

        class _FakeFilesResource:
            def __init__(self):
                self.calls = []

            def list(self, **kwargs):
                self.calls.append(("list", kwargs))
                if kwargs.get("pageToken") is None and "root_p" in kwargs.get("q", ""):
                    return _Exec({"files": [_it("f1", "A.pdf")], "nextPageToken": "p2"})
                return _Exec({"files": [_it("f2", "B.pdf")]})

            def get(self, **kwargs):
                self.calls.append(("get", kwargs))
                return _Exec({
                    "id": kwargs["fileId"],
                    "name": "A.pdf",
                    "parents": ["old_parent"],
                    "capabilities": {"canEdit": True, "canMoveItemOutOfDrive": True, "canTrash": False},
                })

            def get_media(self, **kwargs):
                self.calls.append(("get_media", kwargs))
                return _Exec(b"pdf-binary-bytes")

            def export(self, **kwargs):
                self.calls.append(("export", kwargs))
                return _Exec(b"# Exported Markdown")

            def create(self, **kwargs):
                self.calls.append(("create", kwargs))
                return _Exec({"id": "new_created_id"})

            def update(self, **kwargs):
                self.calls.append(("update", kwargs))
                return _Exec({"id": kwargs["fileId"], "name": kwargs.get("body", {}).get("name", "A.pdf")})

            def copy(self, **kwargs):
                self.calls.append(("copy", kwargs))
                return _Exec({"id": "copied_id"})

        fake_files = _FakeFilesResource()

        class _FakeService:
            def files(self):
                return fake_files

        client = sc.GoogleDriveAPIClient(service_factory=lambda: _FakeService(), rate_per_sec=100.0)
        self.assertIsInstance(client, sc.DriveProtocol)

        # Pagination ls
        items = client.ls("root_p")
        self.assertEqual([i["id"] for i in items], ["f1", "f2"])

        # stream_ls / capabilities / search
        smap, errs = client.stream_ls(["root_p"])
        self.assertFalse(errs)
        self.assertEqual(len(smap["root_p"]), 2)
        caps = client.capabilities("f1", "canEdit,canTrash")
        self.assertEqual(caps, {"canEdit": True, "canTrash": False})
        self.assertEqual(len(client.search(name_contains="A", file_type="pdf")), 1)

        # Mutate & IO
        with tempfile.TemporaryDirectory() as td:
            dl = client.download("f1", Path(td) / "a.pdf")
            self.assertEqual(dl.read_bytes(), b"pdf-binary-bytes")
            ex = client.export("doc1", Path(td) / "doc.md", "md")
            self.assertEqual(ex.read_bytes(), b"# Exported Markdown")
            self.assertEqual(client.mkdir("[01] MỚI", "root_p"), "new_created_id")
            client.rename("f1", "A - Mới.pdf")
            client.move("f1", "new_parent")
            self.assertEqual(client.copy("f1", "Copy.pdf", "root_p"), "copied_id")
            self.assertEqual(client.create_shortcut("f1", "root_p", "SC"), "new_created_id")


class TestOpsDoctorWatcherDeployAndWebUI(unittest.TestCase):
    def test_system_junk_doctor_watcher_and_release_bundle(self):
        idx = {
            "[A] STORAGE/[01] HỌC THUẬT": {
                "id": "f1",
                "depth": 1,
                "items": [
                    _it("m1", "[02] MACOSX", sc.FOLDER_MIME),
                    _it("ds1", ".DS_Store", "application/octet-stream"),
                    _it("ok1", "Tài Liệu - Học Thuật.pdf"),
                ],
            }
        }
        junk = dedup.find_system_junk(idx)
        self.assertEqual(len(junk), 2)
        self.assertEqual({j["subkind"] for j in junk}, {"macosx_folder", "os_junk_file"})

        # Kiểm chứng execute_moves với system_junk đi đúng [06] RÁC HỆ THỐNG và cập nhật index
        with tempfile.TemporaryDirectory() as td_q:
            old_env = os.environ.get("STORAGE_DATA_DIR")
            os.environ["STORAGE_DATA_DIR"] = td_q
            try:
                mdrive = _MockDrive()
                mdrive.capabilities = lambda fid, fields="": {"canMoveItemOutOfDrive": True, "canEdit": True}  # type: ignore[attr-defined]
                blocked = dedup.execute_moves(junk, idx, workers=2, drive=mdrive)
                self.assertEqual(blocked, [])
                self.assertEqual(len(mdrive.moved), 2)
                self.assertTrue(any(nm == "[06] RÁC HỆ THỐNG" for nm, _ in mdrive.ensured))
                self.assertEqual(len(idx["[A] STORAGE/[01] HỌC THUẬT"]["items"]), 1)
            finally:
                if old_env is None:
                    os.environ.pop("STORAGE_DATA_DIR", None)
                else:
                    os.environ["STORAGE_DATA_DIR"] = old_env

        # Kiểm chứng lưu trữ thư mục mã cũ [01]–[18] không đụng tới [01] TÀI LIỆU HỆ THỐNG
        mdrive2 = _MockDrive()
        mdrive2.ls = lambda fid: [  # type: ignore[attr-defined]
            _it("leg1", "[01] THƯ VIỆN LÕI", sc.FOLDER_MIME),
            _it("leg2", "[18] PHÂN TÍCH VIDEO", sc.FOLDER_MIME),
            _it("new1", "[01] TÀI LIỆU HỆ THỐNG", sc.FOLDER_MIME),
            _it("new2", "[02] GÓI PHÁT HÀNH", sc.FOLDER_MIME),
        ]
        arc = drive_deploy.archive_legacy_module_folders(mdrive2, dry_run=False)
        self.assertEqual(arc["found"], 2)
        self.assertEqual(arc["moved"], 2)
        self.assertEqual([fid for fid, _ in mdrive2.moved], ["leg1", "leg2"])

        doc_res = doctor.run_doctor()
        self.assertEqual(doc_res["version"], __version__)
        self.assertIn("python_packages", doc_res)
        self.assertIn("drive", doc_res)

        w_res = watcher.poll_once(_MockDrive(), "2026-11-20T00:00:00Z")
        self.assertEqual(w_res["changed_count"], 2)
        self.assertTrue(any(v["code"] == "CHUA_TITLE_CASE" for v in w_res["violations"]))

        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "repo"
            (repo / "docs").mkdir(parents=True)
            (repo / "dist").mkdir(parents=True)
            (repo / "docs" / "Tổng Quan Hệ Thống - Quản Lý.md").write_text("# Master", encoding="utf-8")
            (repo / "docs" / "Quy Ước.md").write_text("# Spec", encoding="utf-8")
            (repo / "README.md").write_text("# README", encoding="utf-8")
            (repo / "dist" / "storage_management_suite-4.0.0-py3-none-any.whl").write_bytes(b"wheel")
            staged = drive_deploy.stage_release_bundle(repo, Path(td) / "staged")
            self.assertTrue((staged / "Tổng Quan Hệ Thống - Quản Lý.md").exists())
            self.assertTrue((staged / "[01] TÀI LIỆU HỆ THỐNG" / "Giới Thiệu Phần Mềm - Storage.md").exists())
            self.assertTrue((staged / "[02] GÓI PHÁT HÀNH" / "storage_management_suite-4.0.0-py3-none-any.whl").exists())

    def test_cli_pipelines_and_fastapi_web_ui(self):
        q_steps = pipelines.build_quick_steps(False, False, False, None, False)
        self.assertTrue(all("--thuc-thi" not in args for _, _, args in q_steps))
        m_steps = pipelines.build_maintenance_steps(True, True, True, None, True)
        self.assertTrue(any("--don-rac-he-thong" in args for _, _, args in m_steps))

        self.assertEqual(cli_main.main(["version"]), 0)

        # Kiểm chứng FastAPI Web Dashboard thật trên cổng nội bộ tạm (không cần httpx)
        try:
            import uvicorn
            from storage_suite.web.app import create_app
        except ImportError:
            self.skipTest("fastapi/uvicorn chưa cài")

        with tempfile.TemporaryDirectory() as td:
            old_env = os.environ.get("STORAGE_DATA_DIR")
            os.environ["STORAGE_DATA_DIR"] = td
            try:
                sample_idx = {
                    "[A] STORAGE": {"id": "r0", "depth": 0, "items": [_it("d1", "[01] HỌC THUẬT", sc.FOLDER_MIME)]},
                    "[A] STORAGE/[01] HỌC THUẬT": {"id": "d1", "depth": 1, "items": [_it("f1", "Triết Học Nhập Môn - PHI1001.pdf", size=2048)]},
                }
                sc.save_index(sample_idx)
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(("127.0.0.1", 0))
                    port = s.getsockname()[1]

                app = create_app()
                server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
                th = threading.Thread(target=server.run, daemon=True)
                th.start()
                deadline = time.monotonic() + 5.0
                while not server.started and time.monotonic() < deadline:
                    time.sleep(0.05)

                base = f"http://127.0.0.1:{port}"
                with urllib.request.urlopen(f"{base}/") as resp:
                    html = resp.read().decode("utf-8")
                    self.assertIn("Storage Management Suite", html)
                with urllib.request.urlopen(f"{base}/api/health") as resp:
                    self.assertEqual(json.loads(resp.read())["version"], __version__)
                with urllib.request.urlopen(f"{base}/api/overview") as resp:
                    ov = json.loads(resp.read())
                    self.assertEqual(ov["stats"]["files"], 1)
                with urllib.request.urlopen(f"{base}/api/search?q=triet") as resp:
                    sr = json.loads(resp.read())
                    self.assertEqual(sr["count"], 1)
                with urllib.request.urlopen(f"{base}/api/catalog-v7/plan?mode=smart") as resp:
                    cp = json.loads(resp.read())
                    self.assertIn("summary", cp)
                with urllib.request.urlopen(f"{base}/api/doctor") as resp:
                    dr = json.loads(resp.read())
                    self.assertEqual(dr["version"], __version__)

                server.should_exit = True
                th.join(timeout=3)
            finally:
                if old_env is None:
                    os.environ.pop("STORAGE_DATA_DIR", None)
                else:
                    os.environ["STORAGE_DATA_DIR"] = old_env


if __name__ == "__main__":
    unittest.main()
