"""Bộ kiểm thử chuyên sâu cho Karius Academic System (KAS) v5.0.0 — Đa Kho (Multi-Vault) & LocalFSBackend."""

from __future__ import annotations

import json
import os
import socket
import tempfile
import unittest
import urllib.request
from pathlib import Path

from karius_academic_system import APP_NAME, APP_SHORT, __version__
from karius_academic_system import core as sc
from karius_academic_system.cli import main as cli_main
from karius_academic_system.ops import auditor, dedup, indexer
from karius_academic_system.web.app import start_embedded_server


class TestKASMultiVaultAndLocalFS(unittest.TestCase):
    def setUp(self) -> None:
        self._old_env = {
            k: os.environ.get(k)
            for k in ("KAS_CONFIG_DIR", "KAS_DATA_DIR", "KAS_VAULT", "KAS_ROOT_NAME", "KAS_ROOT_ID")
        }
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)
        os.environ["KAS_CONFIG_DIR"] = str(self.tmp_path / "cfg")
        os.environ.pop("KAS_DATA_DIR", None)
        os.environ.pop("KAS_VAULT", None)
        os.environ.pop("KAS_ROOT_NAME", None)
        os.environ.pop("KAS_ROOT_ID", None)
        sc.reload_config()

    def tearDown(self) -> None:
        for k, v in self._old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        sc.reload_config()
        self._tmp.cleanup()

    def test_default_config_has_no_hardcoded_personal_drive_ids(self):
        self.assertEqual(APP_NAME, "Karius Academic System")
        self.assertEqual(APP_SHORT, "KAS")
        self.assertEqual(__version__, "5.0.0")
        cfg = sc.load_config()
        self.assertEqual(cfg["root_id"], "")
        self.assertEqual(cfg["known_ids"], {})
        self.assertEqual(cfg["master_sheet_id"], "")
        self.assertEqual(sc.extract_drive_folder_id("https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWx?usp=sharing"), "1AbCdEfGhIjKlMnOpQrStUvWx")
        kind_d, fid = sc.detect_source_kind("https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWx")
        self.assertEqual(kind_d, "gdrive")
        self.assertEqual(fid, "1AbCdEfGhIjKlMnOpQrStUvWx")

    def test_local_vault_full_lifecycle_scan_audit_quarantine_and_undo(self):
        # 1. Tạo kho thư mục cục bộ thông thường (general vault — không cần [00] TỔNG QUAN)
        gen_dir = self.tmp_path / "KhoTaiLieuThuong"
        (gen_dir / "Mon Triet Hoc").mkdir(parents=True)
        (gen_dir / "Mon Triet Hoc" / "Giao Trinh Triet Hoc.pdf").write_bytes(b"%PDF-1.4 sample content" * 20)
        (gen_dir / "Mon Triet Hoc" / "MACOSX").mkdir()
        (gen_dir / "Mon Triet Hoc" / "MACOSX" / "junk.dat").write_bytes(b"junk")
        (gen_dir / "Mon Triet Hoc" / ".DS_Store").write_bytes(b"ds")

        # 2. Tạo kho thứ 2 chuẩn học thuật KAS (academic_v7)
        acad_dir = self.tmp_path / "KhoHocThuatKAS"
        (acad_dir / "[00] TỔNG QUAN").mkdir(parents=True)
        (acad_dir / "[01] TRIẾT HỌC").mkdir(parents=True)
        (acad_dir / "[01] TRIẾT HỌC" / "Nhập Môn Logic Học - Kant.pdf").write_bytes(b"%PDF-1.4 logic" * 10)

        # 3. Kết nối cả 2 kho qua CLI `kas vault add`
        self.assertEqual(cli_main.main(["vault", "add", "thuong", "--nguon", str(gen_dir), "--ten", "Kho Thường"]), 0)
        self.assertEqual(cli_main.main(["vault", "add", "hocthuat", "--nguon", str(acad_dir), "--ten", "Kho Học Thuật"]), 0)

        reg = sc.get_vault_registry()
        self.assertEqual(len(reg.list_vaults()), 2)
        self.assertEqual(reg.get_vault("thuong").effective_mode(), "general")
        self.assertEqual(reg.get_vault("hocthuat").effective_mode(), "academic_v7")

        # 4. Quét kho thường qua `--kho thuong` + xác minh không bị spam lỗi THIEU_TONG_QUAN
        os.environ["KAS_DATA_DIR"] = str(self.tmp_path / "data_thuong")
        sc.activate_vault("thuong", persist=True)
        indexer.main(["--khong-chup"])
        idx = sc.load_index()
        self.assertIn("Kho Thường", idx)

        issues = auditor.audit(idx, check_structure=True)
        codes = {i[1] for i in issues}
        self.assertNotIn("THIEU_TONG_QUAN", codes)
        self.assertIn("RAC_HE_THONG", codes)

        # 5. Cách ly rác hệ thống trên kho cục bộ thật và hoàn tác ngược 100% qua Unified Undo Journal
        junk = dedup.find_system_junk(idx)
        self.assertEqual(len(junk), 2)
        local_drv = sc.create_backend()
        self.assertIsInstance(local_drv, sc.LocalFSBackend)
        blocked = dedup.execute_moves(junk, idx, workers=2, drive=local_drv)
        self.assertEqual(blocked, [])
        self.assertFalse((gen_dir / "Mon Triet Hoc" / "MACOSX").exists())
        self.assertFalse((gen_dir / "Mon Triet Hoc" / ".DS_Store").exists())
        self.assertTrue((gen_dir / "[07] KIỂM TRA" / "[06] RÁC HỆ THỐNG" / "MACOSX").exists())

        with sc.StorageDB() as db:
            batches = db.list_undo_batches()
            self.assertEqual(len(batches), 1)
            ures = db.undo_batch(local_drv, batches[0]["batch_id"], execute=True)
            self.assertTrue(ures["ok"], f"Undo failed: {ures}")
            self.assertEqual(ures["reverted"], 2)
        self.assertTrue((gen_dir / "Mon Triet Hoc" / "MACOSX").exists())
        self.assertTrue((gen_dir / "Mon Triet Hoc" / ".DS_Store").exists())

    def test_web_api_multi_vault_add_and_hot_switch(self):
        v1 = self.tmp_path / "VaultOne"
        v2 = self.tmp_path / "VaultTwo"
        v1.mkdir()
        v2.mkdir()
        (v1 / "Tai Lieu Mot.pdf").write_bytes(b"pdf1" * 100)
        (v2 / "[00] TỔNG QUAN").mkdir()
        (v2 / "Tai Lieu Hai.pdf").write_bytes(b"pdf2" * 100)

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]

        th, stop_fn, engine = start_embedded_server(host="127.0.0.1", port=port, prefer_stdlib=True)
        self.assertEqual(engine, "stdlib-http")
        base = f"http://127.0.0.1:{port}"
        try:
            def _post(path: str, payload: dict) -> dict:
                req = urllib.request.Request(
                    f"{base}{path}",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req) as resp:
                    return json.loads(resp.read().decode("utf-8"))

            r1 = _post("/api/vaults/add", {"source": str(v1), "slug": "v1", "name": "Kho Một", "mode": "auto"})
            self.assertTrue(r1["ok"])
            self.assertEqual(r1["vault"]["effective_mode"], "general")

            r2 = _post("/api/vaults/add", {"source": str(v2), "slug": "v2", "name": "Kho Hai", "mode": "auto"})
            self.assertTrue(r2["ok"])
            self.assertEqual(r2["vault"]["effective_mode"], "academic_v7")

            # Hot-switch về v1
            sw = _post("/api/vaults/activate", {"slug": "v1", "persist": True})
            self.assertEqual(sw["vault"]["slug"], "v1")
            with urllib.request.urlopen(f"{base}/api/health") as resp:
                h = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(h["app_short"], "KAS")
                self.assertEqual(h["vault_slug"], "v1")
                self.assertEqual(h["root_name"], "Kho Một")
        finally:
            stop_fn()
            th.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
