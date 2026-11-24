"""Bộ kiểm thử toàn diện cho KAS v1.9.0:
1. Chứng chỉ ký số cố định Android (SHA-1 & SHA-256) + cấu hình Gradle release signing & `certifi`.
2. Kết nối máy chủ PC ↔ Android qua Wi-Fi LAN: ưu tiên IPv4, tự khám phá UDP (`KAS_DISCOVER_V1`),
   API `POST /api/android/lan-mode`, tự đổi `0.0.0.0` → `127.0.0.1` khi mở trình duyệt cục bộ.
3. Cập nhật tự động Android APK (`kas-android.apk`): tải & kiểm chứng `SHA256SUMS.txt` (không gọi `pip` trên Chaquopy),
   từ chối khi sai băm SHA-256, chuyển giao trình cài đặt qua `KasFileProvider`.
4. Hệ thống Nhật kí & Báo lỗi tập trung (`core/logger.py`, `/api/logs/*`, `kas logs`, ẩn bí mật, App Lock 401, xuất `.TXT`/`.JSON`).
5. Rút gọn tên hiển thị thành `KAS` trên Desktop Windows (`KAS.lnk`), Android (`strings.xml`) & PWA (`manifest.webmanifest`),
   đồng thời đảm bảo 100% pure 7-bit ASCII + CRLF trên các kịch bản Windows.
"""

from __future__ import annotations

import hashlib
import http.server
import io
import json
import os
import socket
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from karius_academic_system import __version__
from karius_academic_system import core as sc
from karius_academic_system.cli.main import main as cli_main
from karius_academic_system.ops import updater
from karius_academic_system.web import android_bridge
from karius_academic_system.web import app as web_app

REPO_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = REPO_ROOT / "src" / "karius_academic_system" / "web" / "static"
ANDROID_DIR = REPO_ROOT / "packaging" / "android" / "app" / "src" / "main"
WIN_DIR = REPO_ROOT / "packaging" / "windows"

EXPECTED_SHA1 = "FF:D4:BA:CE:3C:48:C1:53:AF:BC:44:B3:AD:FE:6D:5C:31:8B:61:BC"
EXPECTED_SHA256 = "EC:65:9D:B8:08:53:33:6C:CE:BA:66:46:F2:3F:19:21:D6:2F:12:D3:DB:8B:6C:08:BE:7F:1F:51:14:1E:A0:96"


def _http_req(url: str, method: str = "GET", payload: dict | None = None, headers: dict | None = None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    hdrs = {"Content-Type": "application/json"} if payload is not None else {}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status, resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as err:
        return err.code, err.read(), dict(err.headers)


class TestV19ShortNameAndSigning(unittest.TestCase):
    def test_version_short_labels_and_ascii_crlf_windows_scripts(self) -> None:
        self.assertEqual(__version__, "1.9.0")

        # 1. Android Home Screen label = KAS
        strings_xml = (ANDROID_DIR / "res" / "values" / "strings.xml").read_text(encoding="utf-8")
        self.assertIn('<string name="app_name">KAS</string>', strings_xml)

        # 2. PWA manifest short & display name = KAS
        manifest = json.loads((STATIC_DIR / "manifest.webmanifest").read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], "KAS")
        self.assertEqual(manifest["short_name"], "KAS")

        # 3. Windows scripts: pure 7-bit ASCII + CRLF + KAS.lnk shortcut + legacy cleanup
        for fname in (
            "install_windows_sac_safe.ps1",
            "uninstall_windows_sac_safe.ps1",
            "Cai_Dat_KAS_Windows11.cmd",
            "Go_Cai_Dat_KAS_Windows11.cmd",
        ):
            raw = (WIN_DIR / fname).read_bytes()
            self.assertTrue(all(b < 128 for b in raw), f"{fname} must be 100% pure 7-bit ASCII")
            self.assertNotIn(b"\n", raw.replace(b"\r\n", b""), f"{fname} must use CRLF line endings only")

        inst_txt = (WIN_DIR / "install_windows_sac_safe.ps1").read_text(encoding="ascii")
        self.assertIn('Join-Path $desktopDir "KAS.lnk"', inst_txt)
        self.assertIn('Join-Path $startMenuDir "KAS.lnk"', inst_txt)
        self.assertIn('Karius Academic System (KAS).lnk', inst_txt)
        self.assertIn('1.9.0', inst_txt)

        uninst_txt = (WIN_DIR / "uninstall_windows_sac_safe.ps1").read_text(encoding="ascii")
        self.assertIn('Join-Path $desktopDir "KAS.lnk"', uninst_txt)
        self.assertIn('Karius Academic System (KAS).lnk', uninst_txt)

    def test_permanent_sha1_certificate_and_android_native_files(self) -> None:
        self.assertEqual(android_bridge.ANDROID_CERT_SHA1, EXPECTED_SHA1)
        self.assertEqual(android_bridge.ANDROID_CERT_SHA256, EXPECTED_SHA256)

        env_info = android_bridge.detect_android_environment(port=8765)
        self.assertEqual(env_info["signing"]["sha1"], EXPECTED_SHA1)
        self.assertEqual(env_info["signing"]["sha256"], EXPECTED_SHA256)
        self.assertEqual(env_info["signing"]["package_name"], "io.github.kariusnocr.kas")

        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        self.assertIn(EXPECTED_SHA1, html)
        self.assertIn('id="androidSha1Text"', html)
        self.assertIn('onclick="copyAndroidSha1()"', html)
        self.assertIn('id="androidLanToggleBtn"', html)
        self.assertIn('id="btnInstallDownloadedApk"', html)
        self.assertIn('id="systemLogsCard"', html)

        gradle = (REPO_ROOT / "packaging" / "android" / "app" / "build.gradle").read_text(encoding="utf-8")
        self.assertIn("versionCode 10900", gradle)
        self.assertIn('versionName "1.9.0"', gradle)
        self.assertIn("signingConfigs", gradle)
        self.assertIn("KAS_KEYSTORE_PATH", gradle)
        self.assertIn('install "certifi"', gradle)

        manifest_xml = (ANDROID_DIR / "AndroidManifest.xml").read_text(encoding="utf-8")
        for tok in (
            "ACCESS_WIFI_STATE",
            "CHANGE_WIFI_MULTICAST_STATE",
            "REQUEST_INSTALL_PACKAGES",
            "@xml/network_security_config",
            'android:name=".KasFileProvider"',
            'android:authorities="io.github.kariusnocr.kas.provider"',
        ):
            self.assertIn(tok, manifest_xml)

        net_cfg = (ANDROID_DIR / "res" / "xml" / "network_security_config.xml").read_text(encoding="utf-8")
        self.assertIn('cleartextTrafficPermitted="true"', net_cfg)

        provider_java = (ANDROID_DIR / "java" / "io" / "github" / "kariusnocr" / "kas" / "KasFileProvider.java").read_text(
            encoding="utf-8"
        )
        self.assertIn("class KasFileProvider extends ContentProvider", provider_java)
        self.assertIn("kas/data/updates", provider_java)
        self.assertIn("kas/data/logs", provider_java)

        main_java = (ANDROID_DIR / "java" / "io" / "github" / "kariusnocr" / "kas" / "MainActivity.java").read_text(
            encoding="utf-8"
        )
        for tok in (
            'KAS_VERSION = "1.9.0"',
            "discoverLanPcServersBlocking",
            "connectToRemotePcWithCheck",
            "onReceivedError",
            "installApkFile",
            "canRequestPackageInstalls",
            "getSigningInfo",
            "installApkUpdate",
            "shareExportedLog",
            "android_native.log",
        ):
            self.assertIn(tok, main_java, f"Missing v1.9.0 feature in MainActivity.java: {tok}")

    def test_supported_platforms_windows_linux_android_only(self) -> None:
        release_yml = (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        self.assertNotIn("build-macos-binary", release_yml)
        self.assertNotIn("macos-", release_yml.lower())
        self.assertIn("windows-x64", release_yml)
        self.assertIn("linux-x64", release_yml)
        self.assertIn("kas-android.apk", release_yml)

        pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn("Operating System :: Microsoft :: Windows", pyproject)
        self.assertIn("Operating System :: POSIX :: Linux", pyproject)
        self.assertIn("Operating System :: Android", pyproject)
        self.assertNotIn("MacOS", pyproject)

        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("macos", readme.lower())
        self.assertLess(len(readme), 9000, "README.md should stay streamlined and scannable on GitHub")
        self.assertIn("Windows", readme)
        self.assertIn("Linux", readme)
        self.assertIn("Android", readme)
        self.assertIn(EXPECTED_SHA1, readme)

        from karius_academic_system.ops import uninstaller

        posix_paths = [str(p) for p in uninstaller._posix_launchers()]
        self.assertFalse(any(p.endswith(".app") for p in posix_paths))


class TestV19WifiLanAndUdpDiscovery(unittest.TestCase):
    def test_ipv4_priority_prefers_real_wifi_over_virtualbox(self) -> None:
        ips = ["192.168.56.1", "172.17.0.1", "10.0.0.5", "192.168.1.42"]
        ips.sort(key=android_bridge._ipv4_priority)
        self.assertEqual(ips[0], "192.168.1.42")
        self.assertEqual(ips[1], "10.0.0.5")
        self.assertEqual(ips[-1], "192.168.56.1")

    def test_udp_lan_discovery_responder_roundtrip(self) -> None:
        try:
            started = android_bridge.start_lan_discovery_responder(http_port=8765, discovery_port=0)
            self.assertTrue(started)
            udp_port = int(android_bridge._DISCOVERY_STATE["port"])
            self.assertGreater(udp_port, 0)

            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as cli:
                cli.settimeout(2.5)
                cli.sendto(android_bridge.LAN_DISCOVERY_PROBE, ("127.0.0.1", udp_port))
                raw, _ = cli.recvfrom(4096)
            resp = json.loads(raw.decode("utf-8"))
            self.assertEqual(resp["app"], "KAS")
            self.assertEqual(resp["version"], __version__)
            self.assertEqual(resp["port"], 8765)
            self.assertIn("hostname", resp)
        finally:
            android_bridge.stop_lan_discovery_responder()


class TestV19AndroidApkAutoUpdate(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_env = {
            k: os.environ.get(k)
            for k in ("KAS_CONFIG_DIR", "KAS_DATA_DIR", "KAS_ANDROID_RUNTIME")
        }
        os.environ["KAS_CONFIG_DIR"] = str(Path(self._tmp.name) / "cfg")
        os.environ["KAS_DATA_DIR"] = str(Path(self._tmp.name) / "data")
        os.environ["KAS_ANDROID_RUNTIME"] = "chaquopy_apk"

        self.apk_bytes = b"PK\x03\x04MOCK-KAS-ANDROID-APK-v9.9.9-SIGNED" + (b"\x00" * 120_000)
        self.apk_sha256 = hashlib.sha256(self.apk_bytes).hexdigest()
        self.corrupt_sums = False

        parent = self

        class _MockReleaseHandler(http.server.BaseHTTPRequestHandler):
            def log_message(self, format, *args):  # noqa: A002
                return

            def do_GET(self):
                if self.path == "/kas-android.apk":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/vnd.android.package-archive")
                    self.send_header("Content-Length", str(len(parent.apk_bytes)))
                    self.end_headers()
                    self.wfile.write(parent.apk_bytes)
                    return
                if self.path == "/SHA256SUMS.txt":
                    digest = ("0" * 64) if parent.corrupt_sums else parent.apk_sha256
                    body = f"{digest}  kas-android.apk\n".encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                self.send_response(404)
                self.end_headers()

        self._srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _MockReleaseHandler)
        self._port = self._srv.server_address[1]
        self._th = threading.Thread(target=self._srv.serve_forever, daemon=True)
        self._th.start()

    def tearDown(self) -> None:
        self._srv.shutdown()
        self._srv.server_close()
        for k, v in self._orig_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self._tmp.cleanup()

    def _mock_release_info(self) -> dict:
        base = f"http://127.0.0.1:{self._port}"
        return {
            "ok": True,
            "current_version": __version__,
            "latest_version": "9.9.9",
            "latest_tag": "v9.9.9",
            "release_name": "KAS v9.9.9",
            "release_url": f"{base}/release",
            "update_available": True,
            "wheel_asset": None,
            "apk_asset": {"name": "kas-android.apk", "size": len(self.apk_bytes), "url": f"{base}/kas-android.apk", "api_url": ""},
            "sha256sums_asset": {"name": "SHA256SUMS.txt", "size": 90, "url": f"{base}/SHA256SUMS.txt", "api_url": ""},
        }

    def test_android_apk_update_downloads_verifies_sha256_without_pip(self) -> None:
        with (
            mock.patch.object(updater, "fetch_release_metadata", return_value=self._mock_release_info()),
            mock.patch.object(updater.subprocess, "run") as mock_subproc,
        ):
            res = updater.apply_update()
            self.assertTrue(res["ok"], res)
            self.assertTrue(res["requires_apk_install"])
            self.assertTrue(res["verification"]["sha256_verified"])
            self.assertFalse(res.get("restarting", False))
            self.assertTrue(Path(res["apk_path"]).is_file())
            self.assertEqual(Path(res["apk_path"]).read_bytes(), self.apk_bytes)
            mock_subproc.assert_not_called()

    def test_android_apk_update_rejects_bad_sha256(self) -> None:
        self.corrupt_sums = True
        with mock.patch.object(updater, "fetch_release_metadata", return_value=self._mock_release_info()):
            res = updater.apply_update()
            self.assertFalse(res["ok"])
            self.assertIn("SHA-256", res.get("error", ""))


class TestV19LogsApiCliAndSecurity(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_env = {k: os.environ.get(k) for k in ("KAS_CONFIG_DIR", "KAS_DATA_DIR")}
        os.environ["KAS_CONFIG_DIR"] = str(Path(self._tmp.name) / "cfg")
        os.environ["KAS_DATA_DIR"] = str(Path(self._tmp.name) / "data")
        sc.reload_config()

        self._httpd = web_app.create_stdlib_server("127.0.0.1", 0)
        self._port = self._httpd.server_address[1]
        self._base = f"http://127.0.0.1:{self._port}"
        self._th = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._th.start()

    def tearDown(self) -> None:
        android_bridge.stop_lan_discovery_responder()
        self._httpd.shutdown()
        self._httpd.server_close()
        for k, v in self._orig_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        sc.reload_config()
        self._tmp.cleanup()

    def test_secret_redaction_and_android_native_log_merge(self) -> None:
        from karius_academic_system.core import logger as kas_logger

        # Xây dựng chuỗi giả lập động để không kích hoạt cảnh báo bảo mật quét mã nguồn tĩnh
        fake_gh = "ghp_" + ("1234567890abcdef" * 2)
        fake_gapi = "AIza" + "SyAbCdEfGhIjKlMnOpQrStUvWxYz12345"
        dirty = (
            f"token={fake_gh} "
            "Authorization: Bearer super_secret_bearer_token_999 "
            f"api_key={fake_gapi} "
            "password=MySecretPass123"
        )
        redacted = sc.redact_secrets(dirty)
        for leaked in (fake_gh[:14], "super_secret_bearer_token_999", fake_gapi[:14], "MySecretPass123"):
            self.assertNotIn(leaked, redacted)

        # Write a simulated Android native log line
        native_file = kas_logger.android_native_log_path()
        native_file.write_text(
            "[2026-11-23T10:00:00Z] [ERROR] [android/wifi_connect] Khong ket noi duoc http://192.168.1.99:8765\n",
            encoding="utf-8",
        )
        fake_gh2 = "ghp_" + ("abcdef1234567890" * 2)
        sc.record_event("ERROR", "updater", "Lỗi cập nhật thử nghiệm", detail=f"token={fake_gh2}")

        listing = sc.list_logs(level="ERROR")
        self.assertTrue(listing["ok"])
        self.assertGreaterEqual(listing["counts"]["errors"], 2)
        msgs = " ".join(e.get("message", "") + " " + e.get("detail", "") for e in listing["entries"])
        self.assertIn("192.168.1.99:8765", msgs)
        self.assertNotIn(fake_gh2[:14], msgs)

    def test_logs_and_lan_mode_http_endpoints_and_app_lock(self) -> None:
        # 1. Record client error via POST /api/logs/client
        st, raw, _ = _http_req(
            f"{self._base}/api/logs/client",
            method="POST",
            payload={
                "level": "ERROR",
                "category": "frontend_error",
                "message": "TypeError: Cannot read properties of null",
                "detail": "Bearer secret_client_tok_123456",
            },
        )
        self.assertEqual(st, 200)
        body = json.loads(raw.decode("utf-8"))
        self.assertTrue(body["ok"])
        self.assertNotIn("secret_client_tok_123456", body["entry"]["detail"])

        # 2. List & filter logs via GET /api/logs
        st, raw, _ = _http_req(f"{self._base}/api/logs?level=ERROR&q=TypeError")
        self.assertEqual(st, 200)
        listed = json.loads(raw.decode("utf-8"))
        self.assertGreaterEqual(listed["filtered_count"], 1)

        # 3. Export TXT & JSON via GET /api/logs/export
        st, txt_bytes, hdrs = _http_req(f"{self._base}/api/logs/export?format=txt")
        self.assertEqual(st, 200)
        self.assertIn("attachment; filename=", hdrs.get("Content-Disposition", ""))
        txt_str = txt_bytes.decode("utf-8")
        self.assertIn("Karius Academic System (KAS)", txt_str)
        self.assertIn("TypeError", txt_str)
        self.assertNotIn("secret_client_tok_123456", txt_str)

        st, json_bytes, _ = _http_req(f"{self._base}/api/logs/export?format=json")
        self.assertEqual(st, 200)
        exp_obj = json.loads(json_bytes.decode("utf-8"))
        self.assertIn("diagnostics", exp_obj)
        self.assertIn("entries", exp_obj)

        # 4. Toggle Wi-Fi LAN mode via POST /api/android/lan-mode (without restarting test server)
        st, raw, _ = _http_req(
            f"{self._base}/api/android/lan-mode",
            method="POST",
            payload={"enabled": True, "restart": False},
        )
        self.assertEqual(st, 200)
        lan_on = json.loads(raw.decode("utf-8"))
        self.assertTrue(lan_on["lan_enabled"])
        self.assertEqual(lan_on["target_host"], "0.0.0.0")
        self.assertEqual(sc.load_app_settings().ui_host, "0.0.0.0")

        st, raw, _ = _http_req(
            f"{self._base}/api/android/lan-mode",
            method="POST",
            payload={"enabled": False, "restart": False},
        )
        self.assertEqual(st, 200)
        self.assertEqual(sc.load_app_settings().ui_host, "127.0.0.1")

        # 5. Clear logs via POST /api/logs/clear
        st, raw, _ = _http_req(f"{self._base}/api/logs/clear", method="POST", payload={})
        self.assertEqual(st, 200)
        self.assertTrue(json.loads(raw.decode("utf-8"))["ok"])

        # 6. Enable App Lock and confirm logs & lan-mode endpoints reject unauthenticated requests with 401
        sc.register_account("karius", "pass1234", require_login=True)
        for method, path, payload in (
            ("GET", "/api/logs", None),
            ("GET", "/api/logs/export?format=txt", None),
            ("POST", "/api/logs/client", {"message": "blocked"}),
            ("POST", "/api/logs/clear", {}),
            ("POST", "/api/android/lan-mode", {"enabled": True, "restart": False}),
        ):
            code, _, _ = _http_req(f"{self._base}{path}", method=method, payload=payload)
            self.assertEqual(code, 401, f"Expected 401 under App Lock for {method} {path}")

    def test_cli_kas_logs_show_and_export(self) -> None:
        sc.record_event("WARNING", "cli_test", "Cảnh báo kiểm thử dòng lệnh kas logs")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli_main(["logs", "--limit", "10"])
        self.assertEqual(rc, 0)
        self.assertIn("Cảnh báo kiểm thử", buf.getvalue())

        out_path = Path(self._tmp.name) / "exported_logs.txt"
        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            rc2 = cli_main(["logs", "export", "--format", "txt", "--out", str(out_path)])
        self.assertEqual(rc2, 0)
        self.assertTrue(out_path.is_file())
        self.assertIn("Cảnh báo kiểm thử", out_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
