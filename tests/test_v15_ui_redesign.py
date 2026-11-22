"""Bộ kiểm thử chuyên sâu cho Giao diện Desktop Workspace Shell & Hệ thống Thiết kế (KAS v1.5.0):
- Phục vụ tài nguyên tĩnh tách biệt (`/static/styles.css`, `/static/app.js`) trên máy chủ thuần Python & FastAPI
- Bảo mật chống Path Traversal trên `/static/*`
- Tương thích App Lock (tệp tĩnh luôn mở 200 cho màn hình khóa trong khi `/api/*` chặn 401)
- Kiểm tra toàn vẹn 100% DOM ID và hàm sự kiện giữa `index.html` và `app.js`
- Đảm bảo 0 phụ thuộc CDN ngoài (100% offline / SAC-safe) và không dùng `alert()`/`confirm()`/`prompt()` trình duyệt
"""

import collections
import http.client
import json
import os
import re
import shutil
import tempfile
import threading
import unittest
from pathlib import Path

from karius_academic_system import __version__
from karius_academic_system import core as sc
from karius_academic_system.web import app as web_app

_STATIC_DIR = Path(web_app.__file__).resolve().parent / "static"


class TestV15UiRedesign(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="kas_v15_ui_"))
        self._old_env = {
            "KAS_CONFIG_DIR": os.environ.get("KAS_CONFIG_DIR"),
            "KAS_DATA_DIR": os.environ.get("KAS_DATA_DIR"),
            "KAS_VAULT": os.environ.get("KAS_VAULT"),
        }
        os.environ["KAS_CONFIG_DIR"] = str(self.tmp / "cfg")
        os.environ["KAS_DATA_DIR"] = str(self.tmp / "data")
        os.environ.pop("KAS_VAULT", None)
        sc.reload_config()

        self.srv = web_app.create_stdlib_server(host="127.0.0.1", port=0)
        self.port = self.srv.server_address[1]
        self.th = threading.Thread(target=self.srv.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
        self.th.start()

    def tearDown(self) -> None:
        self.srv.shutdown()
        self.srv.server_close()
        for k, v in self._old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        sc.reload_config()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _get(self, path: str) -> tuple[int, str, bytes]:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request("GET", path)
            resp = conn.getresponse()
            body = resp.read()
            ctype = resp.getheader("Content-Type", "")
            return resp.status, ctype, body
        finally:
            conn.close()

    def test_version_and_static_asset_delivery(self) -> None:
        self.assertEqual(__version__, "1.5.0")

        code, ctype, raw_html = self._get("/")
        self.assertEqual(code, 200)
        self.assertIn("text/html", ctype)
        html = raw_html.decode("utf-8")
        self.assertIn("Karius Academic System", html)
        self.assertIn("/static/styles.css", html)
        self.assertIn("/static/app.js", html)

        code_css, ctype_css, raw_css = self._get("/static/styles.css")
        self.assertEqual(code_css, 200)
        self.assertIn("text/css", ctype_css)
        css = raw_css.decode("utf-8")
        self.assertIn("--bg: #0c0e12", css)
        self.assertIn('[data-theme="light"]', css)
        for forbidden_hex in ("#6366f1", "#8b5cf6", "#a855f7", "#4f46e5"):
            self.assertNotIn(forbidden_hex, css.lower())

        code_js, ctype_js, raw_js = self._get("/static/app.js")
        self.assertEqual(code_js, 200)
        self.assertIn("application/javascript", ctype_js)
        js = raw_js.decode("utf-8")
        self.assertIn("openCommandPalette", js)
        self.assertIn("showConfirmModal", js)
        self.assertIn("showToast", js)
        # Không dùng hộp thoại trình duyệt cũ (alert/confirm/prompt)
        self.assertIsNone(re.search(r"(?<![.\w])(?:alert|confirm|prompt)\s*\(", js))

    def test_static_path_traversal_blocked(self) -> None:
        for attack_path in (
            "/static/../app.py",
            "/static/%2e%2e/app.py",
            "/static/..%5capp.py",
            "/static/nonexistent.css",
            "/static/index.html",
            "/static/",
        ):
            code, _, _ = self._get(attack_path)
            self.assertEqual(code, 404, f"Expected 404 for {attack_path}, got {code}")

        self.assertIsNone(web_app._read_static_asset("../app.py"))
        self.assertIsNone(web_app._read_static_asset("..\\app.py"))
        self.assertIsNone(web_app._read_static_asset("index.html"))

    def test_app_lock_allows_static_assets_while_protecting_api(self) -> None:
        sc.register_account("karius_ui", "secret1234", display_name="Karius UI", require_login=True)

        code_api, _, raw_api = self._get("/api/overview")
        self.assertEqual(code_api, 401)
        self.assertTrue(json.loads(raw_api.decode("utf-8")).get("locked"))

        for static_url in ("/", "/static/styles.css", "/static/app.js"):
            code, _, _ = self._get(static_url)
            self.assertEqual(code, 200, f"Static resource {static_url} must load under App Lock")

    def test_dom_id_and_handler_integrity_offline_safe(self) -> None:
        html = (_STATIC_DIR / "index.html").read_text(encoding="utf-8")
        js = (_STATIC_DIR / "app.js").read_text(encoding="utf-8")

        # 1. Single <h1> and zero duplicate id attributes
        h1_matches = re.findall(r"<h1\b", html)
        self.assertEqual(len(h1_matches), 1)
        all_ids = re.findall(r'\bid="([A-Za-z0-9_-]+)"', html)
        dups = [k for k, v in collections.Counter(all_ids).items() if v > 1]
        self.assertEqual(dups, [], f"Duplicate HTML IDs: {dups}")

        # 2. Every getElementById in app.js exists in index.html
        js_ids = set(re.findall(r"""getElementById\(['"]([A-Za-z0-9_-]+)['"]\)""", js))
        missing_ids = sorted(js_ids - set(all_ids))
        self.assertEqual(missing_ids, [], f"Missing DOM IDs in index.html: {missing_ids}")

        # 3. Every inline HTML handler function is defined in app.js
        defined_fns = set(re.findall(r"(?:async\s+)?function\s+([A-Za-z0-9_]+)\s*\(", js))
        handlers = re.findall(r'on(?:click|change|input|keydown)="([^"]+)"', html)
        called_fns = set()
        for h in handlers:
            for fn in re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(", h):
                if fn != "if":
                    called_fns.add(fn)
        missing_fns = sorted(called_fns - defined_fns)
        self.assertEqual(missing_fns, [], f"Missing JS handlers in app.js: {missing_fns}")

        # 4. Zero external CDN assets (100% offline & SAC safe)
        self.assertIsNone(re.search(r"""<(?:link|script)\b[^>]+(?:href|src)=['"]https?://""", html, re.I))

    def test_fastapi_static_routes_parity(self) -> None:
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            self.skipTest("fastapi/httpx not installed")
        app = web_app.create_app()
        client = TestClient(app)
        r_css = client.get("/static/styles.css")
        self.assertEqual(r_css.status_code, 200)
        self.assertIn("text/css", r_css.headers.get("content-type", ""))
        r_js = client.get("/static/app.js")
        self.assertEqual(r_js.status_code, 200)
        self.assertIn("application/javascript", r_js.headers.get("content-type", ""))
        self.assertEqual(client.get("/static/nonexistent.css").status_code, 404)
        self.assertEqual(client.get("/static/index.html").status_code, 404)


if __name__ == "__main__":
    unittest.main()
