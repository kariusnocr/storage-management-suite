"""Bộ kiểm thử toàn diện cho Trình Duyệt Kho & Xem Trước Tệp (Vault Explorer & Previewer — KAS v1.6.0):
- Chuẩn hóa đường dẫn & chặn path traversal / symlink escape 2 lớp
- Duyệt thư mục thời gian thực trên Kho Cục Bộ (sắp xếp, lọc tiếng Việt không dấu, cây mở rộng lười)
- Xem trước đa định dạng (văn bản/mã nguồn, ảnh PNG, lưu trữ ZIP, thư mục, tệp nhị phân SHA-256)
- Duyệt tức thì trên chỉ mục SQLite cho Kho Google Drive + đọc bản đệm xem trước
- Máy chủ HTTP `--stdlib` (`/api/explorer/{list,tree,preview,raw}` + HTTP 206 Partial Content Range + chống XSS HTML/JS + App Lock 401)
- Lệnh CLI `kas duyet` / `kas browse` và tích hợp `default_tab = "explorer"`
"""

from __future__ import annotations

import base64
import io
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from karius_academic_system import __version__
from karius_academic_system import core as sc
from karius_academic_system.cli.main import main as kas_main
from karius_academic_system.core import accounts, settings
from karius_academic_system.media import file_reader as fr
from karius_academic_system.ops import explorer
from karius_academic_system.web import app as web_app

# Ảnh PNG 1x1 hợp lệ dùng để kiểm thử xem trước ảnh & phát trực tiếp
_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+X2ZkAAAAASUVORK5CYII="
)


def _http_req(
    url: str,
    *,
    method: str = "GET",
    headers: dict | None = None,
    body: bytes | None = None,
) -> tuple[int, dict[str, str], bytes]:
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            hdrs = {k.lower(): v for k, v in resp.headers.items()}
            return resp.status, hdrs, resp.read()
    except urllib.error.HTTPError as err:
        hdrs = {k.lower(): v for k, v in err.headers.items()}
        return err.code, hdrs, err.read()


class TestV16VaultExplorer(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._env_backup = {
            k: os.environ.get(k)
            for k in (
                "KAS_CONFIG_DIR",
                "KAS_DATA_DIR",
                "KAS_ROOT_ID",
                "KAS_VAULT",
                "XDG_CONFIG_HOME",
                "XDG_DATA_HOME",
            )
        }
        tmp_path = Path(self._tmp.name)
        os.environ["KAS_CONFIG_DIR"] = str(tmp_path / "cfg")
        os.environ["KAS_DATA_DIR"] = str(tmp_path / "data")
        os.environ.pop("KAS_ROOT_ID", None)
        os.environ.pop("KAS_VAULT", None)

        # Tạo kho cục bộ mẫu có cấu trúc nhiều cấp & nhiều định dạng
        self.vault_dir = tmp_path / "local_vault"
        self.vault_dir.mkdir(parents=True)
        (self.vault_dir / "[01] HỌC THUẬT" / "Triết Học").mkdir(parents=True)
        (self.vault_dir / "[02] TƯ LIỆU").mkdir(parents=True)

        (self.vault_dir / "ghi-chu.md").write_text("# Đề cương nghiên cứu\nXin chào KAS v1.6.0!\n", encoding="utf-8")
        (self.vault_dir / "[01] HỌC THUẬT" / "Triết Học Đại Cương.txt").write_text(
            "Nội dung triết học cổ điển và hiện đại.\nDòng thứ hai.", encoding="utf-8"
        )
        (self.vault_dir / "[01] HỌC THUẬT" / "Triết Học" / "so-do.png").write_bytes(_TINY_PNG)
        (self.vault_dir / "[01] HỌC THUẬT" / "payload.html").write_text(
            "<html><body><script>alert('xss')</script></body></html>", encoding="utf-8"
        )
        (self.vault_dir / "[02] TƯ LIỆU" / "data.bin").write_bytes(b"\x00\x01\x02\x03" * 64)
        with zipfile.ZipFile(self.vault_dir / "[02] TƯ LIỆU" / "bo-tai-lieu.zip", "w") as zf:
            zf.writestr("readme.txt", "Bên trong tệp nén ZIP mẫu")
            zf.writestr("chuong1.md", "# Chương 1")

        # Tệp nằm ngoài kho dùng để kiểm thử symlink escape
        self.outside_secret = tmp_path / "secret_outside.txt"
        self.outside_secret.write_text("TOP SECRET", encoding="utf-8")

        sc.reload_config()

    def tearDown(self) -> None:
        for k, v in self._env_backup.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        sc.reload_config()
        self._tmp.cleanup()

    def _register_local_vault(self) -> sc.VaultConfig:
        reg = sc.VaultRegistry()
        vc = reg.add_vault(name="Kho Học Thuật", source=str(self.vault_dir), mode="academic_v7", activate=True)
        sc.reload_config(vc.slug)
        return vc

    def test_version_helpers_and_settings_allowlist(self) -> None:
        self.assertTrue(__version__.startswith("1."), __version__)
        self.assertIn("explorer", settings.VALID_DEFAULT_TABS)
        cfg = settings.AppSettings.from_dict({"default_tab": "explorer"})
        settings.save_app_settings(cfg)
        self.assertEqual(settings.load_app_settings().default_tab, "explorer")

        # Chuẩn hóa đường dẫn & chặn `..`
        self.assertEqual(explorer.normalize_rel_path("[A] STORAGE/[01] HỌC THUẬT", root_name="[A] STORAGE"), "[01] HỌC THUẬT")
        self.assertEqual(explorer.normalize_rel_path("[A] STORAGE", root_name="[A] STORAGE"), "")
        self.assertEqual(explorer.normalize_rel_path(r"[01] HỌC THUẬT\Triết Học"), "[01] HỌC THUẬT/Triết Học")
        with self.assertRaises(ValueError):
            explorer.normalize_rel_path("../etc/passwd")
        with self.assertRaises(ValueError):
            explorer.normalize_rel_path("[01] HỌC THUẬT/../../secret")

        # Phân loại tệp & breadcrumbs
        self.assertEqual(explorer.classify_item("bai.pdf"), ("pdf", "pdf"))
        self.assertEqual(explorer.classify_item("anh.PNG"), ("image", "png"))
        self.assertEqual(explorer.classify_item("nhac.mp3"), ("audio", "mp3"))
        self.assertEqual(explorer.classify_item("clip.mp4"), ("video", "mp4"))
        self.assertEqual(explorer.classify_item("app.py"), ("code", "py"))
        self.assertEqual(explorer.classify_item("notes.md"), ("text", "md"))
        self.assertEqual(explorer.classify_item("bao-cao.docx"), ("office", "docx"))
        self.assertEqual(explorer.classify_item("sach.epub"), ("ebook", "epub"))
        self.assertEqual(explorer.classify_item("archive.zip"), ("archive", "zip"))
        self.assertEqual(
            explorer.classify_item("Doc", "application/vnd.google-apps.document"),
            ("gdoc", ""),
        )
        crumbs = explorer.build_breadcrumbs("a/b", "Kho")
        self.assertEqual([c["path"] for c in crumbs], ["", "a", "a/b"])

    def test_local_vault_browse_sort_filter_tree_and_preview(self) -> None:
        self._register_local_vault()

        # 1. Duyệt thư mục gốc trực tiếp không cần quét chỉ mục
        root_res = explorer.browse_folder("")
        self.assertTrue(root_res["ok"])
        self.assertEqual(root_res["data_source"], "local_live")
        self.assertEqual(root_res["stats"]["folders"], 2)
        self.assertEqual(root_res["stats"]["files"], 1)
        # Thư mục luôn đứng trước tệp tin
        self.assertTrue(root_res["entries"][0]["is_folder"])
        self.assertTrue(root_res["entries"][1]["is_folder"])
        self.assertFalse(root_res["entries"][2]["is_folder"])
        self.assertEqual(root_res["entries"][2]["name"], "ghi-chu.md")

        # 2. Duyệt thư mục con & lọc không dấu tiếng Việt
        sub = explorer.browse_folder("[01] HỌC THUẬT", filter_q="triet hoc")
        self.assertEqual(sub["parent_path"], "")
        names = [e["name"] for e in sub["entries"]]
        self.assertIn("Triết Học", names)
        self.assertIn("Triết Học Đại Cương.txt", names)
        self.assertNotIn("payload.html", names)

        # 3. Cây thư mục mở rộng lười
        tree = explorer.list_folder_children_tree("[01] HỌC THUẬT")
        self.assertEqual([c["name"] for c in tree["children"]], ["Triết Học"])

        # 4. Xem trước đa định dạng: văn bản, ảnh, ZIP, nhị phân, thư mục
        pv_md = explorer.preview_item(path="ghi-chu.md")
        self.assertEqual(pv_md["preview_mode"], "text")
        self.assertIn("Xin chào KAS v1.6.0", pv_md["text_preview"])
        self.assertIn("/api/explorer/raw?id=", pv_md["raw_url"])

        pv_img = explorer.preview_item(path="[01] HỌC THUẬT/Triết Học/so-do.png")
        self.assertEqual(pv_img["preview_mode"], "image")
        self.assertTrue(pv_img["raw_url"].startswith("/api/explorer/raw?id="))

        pv_zip = explorer.preview_item(path="[02] TƯ LIỆU/bo-tai-lieu.zip")
        self.assertEqual(pv_zip["preview_mode"], "document")

        pv_bin = explorer.preview_item(path="[02] TƯ LIỆU/data.bin")
        self.assertEqual(pv_bin["preview_mode"], "binary")
        self.assertTrue(len(pv_bin["metadata"].get("sha256", "")) == 64)

        pv_dir = explorer.preview_item(path="[01] HỌC THUẬT")
        self.assertEqual(pv_dir["preview_mode"], "folder")
        self.assertEqual(pv_dir["child_folders"], 1)
        self.assertEqual(pv_dir["child_files"], 2)

        # 5. Chống XSS với HTML & chặn symlink thoát khỏi kho
        _, html_mime, _ = explorer.read_raw_local_file(path="[01] HỌC THUẬT/payload.html")
        self.assertEqual(html_mime, "text/plain; charset=utf-8")

        escape_link = self.vault_dir / "escape_link.txt"
        try:
            escape_link.symlink_to(self.outside_secret)
            with self.assertRaises((PermissionError, sc.DriveError)):
                explorer.read_raw_local_file(path="escape_link.txt")
        except (OSError, NotImplementedError):
            pass

    def test_gdrive_sqlite_vault_browse_and_cached_preview(self) -> None:
        reg = sc.VaultRegistry()
        vc = reg.add_vault(
            name="[A] STORAGE",
            source="https://drive.google.com/drive/folders/1FAKE_ROOT_ID_TEST_0001",
            mode="academic_v7",
            activate=True,
        )
        sc.reload_config(vc.slug)

        # Chưa quét chỉ mục → needs_scan=True
        empty_res = explorer.browse_folder("")
        self.assertTrue(empty_res["needs_scan"])
        self.assertEqual(empty_res["data_source"], "empty_index")

        # Nạp chỉ mục mẫu theo định dạng chuẩn storage_index vào SQLite
        sample_idx = {
            "[A] STORAGE": {
                "id": "1FAKE_ROOT_ID_TEST_0001",
                "depth": 0,
                "items": [
                    {
                        "id": "FLD_01",
                        "name": "[01] HỌC THUẬT",
                        "mimeType": sc.FOLDER_MIME,
                        "size": 0,
                        "modifiedTime": "2026-11-20T09:00:00Z",
                    }
                ],
            },
            "[A] STORAGE/[01] HỌC THUẬT": {
                "id": "FLD_01",
                "depth": 1,
                "items": [
                    {
                        "id": "FLD_TOAN",
                        "name": "Toán Học",
                        "mimeType": sc.FOLDER_MIME,
                        "size": 0,
                        "modifiedTime": "2026-11-20T09:00:00Z",
                    },
                    {
                        "id": "FILE_PDF_1",
                        "name": "Giải Tích 1.pdf",
                        "mimeType": "application/pdf",
                        "size": 102400,
                        "modifiedTime": "2026-11-20T09:00:00Z",
                    },
                ],
            },
            "[A] STORAGE/[01] HỌC THUẬT/Toán Học": {
                "id": "FLD_TOAN",
                "depth": 2,
                "items": [],
            },
        }
        with sc.StorageDB() as db:
            db.import_index_dict(sample_idx)

        root_res = explorer.browse_folder("")
        self.assertEqual(root_res["data_source"], "sqlite_index")
        self.assertEqual(len(root_res["entries"]), 1)
        self.assertEqual(root_res["entries"][0]["name"], "[01] HỌC THUẬT")
        self.assertEqual(root_res["entries"][0]["child_folders"], 1)
        self.assertEqual(root_res["entries"][0]["child_files"], 1)

        # Nhảy thẳng bằng đường dẫn có tiền tố ROOT_NAME (giống FTS5 parent_path)
        sub_res = explorer.browse_folder("[A] STORAGE/[01] HỌC THUẬT")
        self.assertEqual(sub_res["current_path"], "[01] HỌC THUẬT")
        self.assertEqual(len(sub_res["entries"]), 2)
        self.assertTrue(sub_res["entries"][0]["is_folder"])
        self.assertEqual(sub_res["entries"][1]["id"], "FILE_PDF_1")

        # Lưu bộ đệm file_reader và kiểm tra preview dùng bộ đệm tức thì
        fr.save_cached_record(
            {
                "id": "FILE_PDF_1",
                "modifiedTime": "2026-11-20T09:00:00Z",
                "outline": ["Chương 1: Giới hạn", "Chương 2: Đạo hàm"],
                "metadata": {"author": "KAS Demo"},
                "stats": {"pages": 120},
            },
            text="Chương 1: Giới hạn và liên tục của hàm số.",
        )
        pv = explorer.preview_item(item_id="FILE_PDF_1")
        self.assertTrue(pv["from_cache"])
        self.assertEqual(pv["preview_mode"], "document")
        self.assertIn("Giới hạn và liên tục", pv["text_preview"])
        self.assertTrue(pv["url"].startswith("https://drive.google.com/"))

    def test_cli_duyet_and_stdlib_http_endpoints_range_and_app_lock(self) -> None:
        self._register_local_vault()

        # 1. CLI `kas duyet` & `--xem`
        buf = io.StringIO()
        import contextlib

        with contextlib.redirect_stdout(buf):
            rc = kas_main(["duyet", "[01] HỌC THUẬT", "--json"])
        self.assertEqual(rc, 0)
        cli_list = json.loads(buf.getvalue())
        self.assertEqual(cli_list["current_path"], "[01] HỌC THUẬT")

        buf2 = io.StringIO()
        with contextlib.redirect_stdout(buf2):
            rc2 = kas_main(["browse", "ghi-chu.md", "--xem", "--json"])
        self.assertEqual(rc2, 0)
        cli_pv = json.loads(buf2.getvalue())
        self.assertIn("Xin chào KAS v1.6.0", cli_pv["text_preview"])

        # 2. Máy chủ HTTP `--stdlib`: list, tree, preview, raw + Range 206 + traversal 400 + App Lock 401
        server = web_app.create_stdlib_server("127.0.0.1", 0)
        port = server.server_address[1]
        th = threading.Thread(target=server.serve_forever, daemon=True)
        th.start()
        base = f"http://127.0.0.1:{port}"
        try:
            st, _, raw = _http_req(f"{base}/api/explorer/list")
            self.assertEqual(st, 200)
            payload = json.loads(raw.decode("utf-8"))
            self.assertEqual(payload["data_source"], "local_live")

            st_t, _, raw_t = _http_req(f"{base}/api/explorer/tree?path={urllib.parse.quote('[01] HỌC THUẬT')}")
            self.assertEqual(st_t, 200)
            self.assertEqual(json.loads(raw_t.decode("utf-8"))["children"][0]["name"], "Triết Học")

            st_p, _, raw_p = _http_req(f"{base}/api/explorer/preview?path=ghi-chu.md")
            self.assertEqual(st_p, 200)
            pv_json = json.loads(raw_p.decode("utf-8"))
            self.assertEqual(pv_json["preview_mode"], "text")

            # Raw streaming đầy đủ + XSS hardening
            st_h, hdr_h, body_h = _http_req(
                f"{base}/api/explorer/raw?path={urllib.parse.quote('[01] HỌC THUẬT/payload.html')}"
            )
            self.assertEqual(st_h, 200)
            self.assertEqual(hdr_h.get("content-type"), "text/plain; charset=utf-8")
            self.assertEqual(hdr_h.get("x-content-type-options"), "nosniff")
            self.assertIn(b"<script>", body_h)

            # HTTP 206 Partial Content Range
            st_r, hdr_r, body_r = _http_req(
                f"{base}/api/explorer/raw?path={urllib.parse.quote('[02] TƯ LIỆU/data.bin')}",
                headers={"Range": "bytes=0-15"},
            )
            self.assertEqual(st_r, 206)
            self.assertEqual(len(body_r), 16)
            self.assertTrue(hdr_r.get("content-range", "").startswith("bytes 0-15/"))

            # Chặn path traversal qua HTTP
            st_bad, _, _ = _http_req(f"{base}/api/explorer/raw?path=../../etc/passwd")
            self.assertEqual(st_bad, 400)

            # Khóa Ứng Dụng (App Lock) phải chặn mọi /api/explorer/* khi chưa đăng nhập
            accounts.register_account("tester", "MatKhau@1234", require_login=True)
            st_lk, _, raw_lk = _http_req(f"{base}/api/explorer/list")
            self.assertEqual(st_lk, 401)
            self.assertTrue(json.loads(raw_lk.decode("utf-8")).get("locked"))

            st_lk_raw, _, _ = _http_req(f"{base}/api/explorer/raw?path=ghi-chu.md")
            self.assertEqual(st_lk_raw, 401)

            # Đăng nhập lấy phiên → /api/explorer/list hoạt động trở lại
            login_body = json.dumps({"username": "tester", "password": "MatKhau@1234"}).encode("utf-8")
            st_lg, hdr_lg, _ = _http_req(
                f"{base}/api/account/login",
                method="POST",
                headers={"Content-Type": "application/json"},
                body=login_body,
            )
            self.assertEqual(st_lg, 200)
            cookie = hdr_lg.get("set-cookie", "").split(";", 1)[0]
            self.assertTrue(cookie.startswith("kas_session="))
            st_ok, _, _ = _http_req(f"{base}/api/explorer/list", headers={"Cookie": cookie})
            self.assertEqual(st_ok, 200)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
