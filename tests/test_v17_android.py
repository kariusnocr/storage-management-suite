"""Bộ kiểm thử toàn diện cho Hệ sinh thái Karius Academic System (KAS v1.7.0) trên hệ điều hành Android:
- Nhận diện môi trường Android (`chaquopy_apk`, `termux`, `desktop_host`) & khám phá IPv4 LAN
- Khởi tạo Kho Tài Liệu Android mặc định (`bootstrap_android_vault`) + quét chỉ mục SQLite tức thì
- Điểm vào máy chủ nhúng Chaquopy (`start_android_embedded_server` / `kas_android_boot.py`)
- Endpoint HTTP `/api/android/info`, `POST /api/android/init-vault`, PWA `/manifest.webmanifest`, `/sw.js`, `/static/icon.svg` & App Lock
- Lệnh CLI `kas android info`, `kas android init-vault` & bảo vệ Console `kas android serve`
- Kiểm chứng cấu trúc dự án Android Gradle (`packaging/android/`), `build_android_apk.py --stage-only` & `drive_deploy` đồng bộ `.apk`
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from karius_academic_system import __version__
from karius_academic_system import core as sc
from karius_academic_system.cli import console
from karius_academic_system.cli.main import main as kas_main
from karius_academic_system.core import accounts
from karius_academic_system.sync import drive_deploy
from karius_academic_system.web import android_bridge

REPO_ROOT = Path(__file__).resolve().parent.parent


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


class TestV17AndroidEcosystem(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._env_backup = {
            k: os.environ.get(k)
            for k in (
                "KAS_CONFIG_DIR",
                "KAS_DATA_DIR",
                "KAS_ROOT_ID",
                "KAS_VAULT",
                "KAS_ANDROID_RUNTIME",
                "KAS_ANDROID_EXTERNAL_DIR",
            )
        }
        tmp_path = Path(self._tmp.name)
        os.environ["KAS_CONFIG_DIR"] = str(tmp_path / "cfg")
        os.environ["KAS_DATA_DIR"] = str(tmp_path / "data")
        os.environ.pop("KAS_ROOT_ID", None)
        os.environ.pop("KAS_VAULT", None)
        os.environ.pop("KAS_ANDROID_RUNTIME", None)
        os.environ["KAS_ANDROID_EXTERNAL_DIR"] = str(tmp_path / "android_ext")
        sc.reload_config()

    def tearDown(self) -> None:
        android_bridge.stop_android_embedded_server()
        for k, v in self._env_backup.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        sc.reload_config()
        self._tmp.cleanup()

    def test_version_and_android_environment_detection(self) -> None:
        self.assertTrue(__version__.startswith("1."), __version__)
        info = android_bridge.detect_android_environment(port=8765)
        self.assertTrue(info["ok"])
        self.assertEqual(info["version"], __version__)
        self.assertEqual(info["package_id"], "io.github.kariusnocr.kas")
        self.assertIn("kas-android.apk", info["downloads"]["apk_latest_url"])
        self.assertIn("install_android_termux.sh", info["downloads"]["termux_one_liner"])
        self.assertEqual(info["pwa"]["manifest_url"], "/manifest.webmanifest")

        os.environ["KAS_ANDROID_RUNTIME"] = "chaquopy_apk"
        apk_info = android_bridge.detect_android_environment(port=8765)
        self.assertTrue(apk_info["is_android"])
        self.assertEqual(apk_info["runtime_flavor"], "chaquopy_apk")

        os.environ["KAS_ANDROID_RUNTIME"] = "termux"
        tmx_info = android_bridge.detect_android_environment(port=8765)
        self.assertTrue(tmx_info["is_android"])
        self.assertEqual(tmx_info["runtime_flavor"], "termux")

    def test_bootstrap_android_vault_and_cli_commands(self) -> None:
        res = android_bridge.bootstrap_android_vault()
        self.assertTrue(res["ok"])
        self.assertTrue(res["created"])
        vpath = Path(res["vault_path"])
        self.assertTrue((vpath / "[00] TỔNG QUAN" / "Chào Mừng KAS Trên Android.md").is_file())
        self.assertTrue((vpath / "[01] HỌC THUẬT").is_dir())
        self.assertTrue((vpath / "[02] TƯ LIỆU").is_dir())

        # CLI `kas android info --json` & `kas android init-vault --json`
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = kas_main(["android", "info", "--json"])
        self.assertEqual(rc, 0)
        cli_info = json.loads(buf.getvalue())
        self.assertEqual(cli_info["package_id"], "io.github.kariusnocr.kas")

        custom_dir = Path(self._tmp.name) / "custom_android_vault"
        buf2 = io.StringIO()
        with contextlib.redirect_stdout(buf2):
            rc2 = kas_main(["android", "init-vault", str(custom_dir), "--ten", "Kho Điện Thoại", "--json"])
        self.assertEqual(rc2, 0)
        cli_init = json.loads(buf2.getvalue())
        self.assertEqual(cli_init["vault"]["name"], "Kho Điện Thoại")
        self.assertTrue((custom_dir / "[00] TỔNG QUAN").is_dir())

        # Console guard blocks `android serve` but allows `android info`
        ok_serve, msg_serve = console.validate_console_argv(["android", "serve"])
        self.assertFalse(ok_serve)
        self.assertIn("android info", msg_serve)
        ok_info, _ = console.validate_console_argv(["android", "info"])
        self.assertTrue(ok_info)

    def test_embedded_chaquopy_server_pwa_assets_and_app_lock(self) -> None:
        app_files = Path(self._tmp.name) / "apk_files"
        ext_files = Path(self._tmp.name) / "apk_ext"

        # Kiểm thử qua mô-đun `kas_android_boot.py` như khi MainActivity.java gọi Chaquopy
        boot_dir = REPO_ROOT / "packaging" / "android" / "app" / "src" / "main" / "python"
        sys.path.insert(0, str(boot_dir))
        try:
            import kas_android_boot

            raw_json = kas_android_boot.start_server_json(str(app_files), str(ext_files), 0)
            boot_data = json.loads(raw_json)
        finally:
            if str(boot_dir) in sys.path:
                sys.path.remove(str(boot_dir))

        self.assertTrue(boot_data["ok"])
        base = boot_data["url"]

        # 1. /api/health báo cáo runtime_flavor = chaquopy_apk & is_android = True
        st_h, _, raw_h = _http_req(f"{base}/api/health")
        self.assertEqual(st_h, 200)
        health = json.loads(raw_h.decode("utf-8"))
        self.assertTrue(health["is_android"])
        self.assertEqual(health["runtime_flavor"], "chaquopy_apk")

        # 2. PWA /manifest.webmanifest, /sw.js, /static/icon.svg
        st_m, hdr_m, raw_m = _http_req(f"{base}/manifest.webmanifest")
        self.assertEqual(st_m, 200)
        self.assertIn("application/manifest+json", hdr_m.get("content-type", ""))
        manifest = json.loads(raw_m.decode("utf-8"))
        self.assertEqual(manifest["short_name"], "KAS")

        st_sw, hdr_sw, raw_sw = _http_req(f"{base}/sw.js")
        self.assertEqual(st_sw, 200)
        self.assertIn("application/javascript", hdr_sw.get("content-type", ""))
        self.assertIn(f"kas-pwa-v{__version__}".encode("utf-8"), raw_sw)

        st_ic, hdr_ic, _ = _http_req(f"{base}/static/icon.svg")
        self.assertEqual(st_ic, 200)
        self.assertIn("image/svg+xml", hdr_ic.get("content-type", ""))

        # 3. /api/android/info & POST /api/android/init-vault
        st_ai, _, raw_ai = _http_req(f"{base}/api/android/info")
        self.assertEqual(st_ai, 200)
        self.assertEqual(json.loads(raw_ai.decode("utf-8"))["package_id"], "io.github.kariusnocr.kas")

        new_v_dir = Path(self._tmp.name) / "api_android_vault"
        st_iv, _, raw_iv = _http_req(
            f"{base}/api/android/init-vault",
            method="POST",
            headers={"Content-Type": "application/json"},
            body=json.dumps({"path": str(new_v_dir), "name": "Kho Android API"}).encode("utf-8"),
        )
        self.assertEqual(st_iv, 200)
        self.assertEqual(json.loads(raw_iv.decode("utf-8"))["vault"]["name"], "Kho Android API")

        # 4. App Lock bảo vệ /api/android/* nhưng giữ mở /manifest.webmanifest và /sw.js
        accounts.register_account("android_user", "MatKhau@1234", require_login=True)
        st_lk, _, _ = _http_req(f"{base}/api/android/info")
        self.assertEqual(st_lk, 401)
        st_m_open, _, _ = _http_req(f"{base}/manifest.webmanifest")
        self.assertEqual(st_m_open, 200)
        st_sw_open, _, _ = _http_req(f"{base}/sw.js")
        self.assertEqual(st_sw_open, 200)

    def test_android_gradle_project_staging_and_drive_deploy_apk(self) -> None:
        # 1. Kiểm chứng dự án Android Gradle & script build_android_apk.py --stage-only
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "packaging" / "build_android_apk.py"), "--stage-only"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn("[ANDROID]", proc.stdout)
        staged_pkg = REPO_ROOT / "packaging" / "android" / "app" / "src" / "main" / "python" / "karius_academic_system"
        try:
            self.assertTrue((staged_pkg / "__init__.py").is_file())
            self.assertTrue((staged_pkg / "web" / "android_bridge.py").is_file())
            self.assertTrue((staged_pkg / "web" / "static" / "index.html").is_file())
            self.assertTrue((staged_pkg / "web" / "static" / "manifest.webmanifest").is_file())
        finally:
            shutil.rmtree(staged_pkg, ignore_errors=True)

        app_gradle = (REPO_ROOT / "packaging" / "android" / "app" / "build.gradle").read_text(encoding="utf-8")
        self.assertIn('applicationId "io.github.kariusnocr.kas"', app_gradle)
        self.assertIn(f'versionName "{__version__}"', app_gradle)
        self.assertIn('version "3.11"', app_gradle)

        # 2. Kiểm chứng stage_release_bundle của drive_deploy bao gồm cả tệp .apk
        fake_repo = Path(self._tmp.name) / "fake_repo"
        (fake_repo / "docs").mkdir(parents=True)
        (fake_repo / "dist").mkdir(parents=True)
        (fake_repo / "README.md").write_text("# KAS", encoding="utf-8")
        (fake_repo / "dist" / "kas-android.apk").write_bytes(b"PK\x03\x04FAKE_APK")
        staging = Path(self._tmp.name) / "staging"
        drive_deploy.stage_release_bundle(fake_repo, staging)
        self.assertTrue((staging / "[02] GÓI PHÁT HÀNH" / "kas-android.apk").is_file())


if __name__ == "__main__":
    unittest.main()
