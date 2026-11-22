"""Bộ kiểm thử chuyên sâu cho Cơ chế Tự Động Cập Nhật Phần Mềm (KAS v1.4.0):
- Cài đặt kênh cập nhật (`stable`/`prerelease`), chu kỳ kiểm tra, cờ `auto_install_updates`
- Kiểm tra cập nhật có bộ đệm (`from_cache`), bỏ qua phiên bản (`skip_update_version`)
- Xác thực toàn vẹn mật mã `SHA256SUMS.txt` (chấp nhận đúng băm, HỦY NGAY khi sai băm!)
- Luồng `apply_update`, ghi lịch sử & lấy phiên bản hoàn tác (`get_rollback_target_version`)
- Kịch bản khởi động lại nền Windows chuẩn 100% ASCII + CRLF
- CLI `kas update --check/--history/--chay-thu` & HTTP `/api/update/*` trên máy chủ `--stdlib`.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

from karius_academic_system import __version__
from karius_academic_system import core as sc
from karius_academic_system.cli.main import main as kas_cli
from karius_academic_system.ops import updater
from karius_academic_system.web.app import start_embedded_server


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _http_json(url: str, method: str = "GET", body: dict | None = None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=8) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


class _FakeBytesResp:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "_FakeBytesResp":
        return self

    def __exit__(self, *args) -> None:
        return None


class TestKASv14AutoUpdater(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._env_backup = {k: os.environ.get(k) for k in ("KAS_CONFIG_DIR", "KAS_DATA_DIR")}
        os.environ["KAS_CONFIG_DIR"] = str(self.root / "cfg")
        os.environ["KAS_DATA_DIR"] = str(self.root / "data")
        sc.reload_config()

        self.fake_whl_bytes = b"PK\x03\x04FAKE_KAS_WHEEL_CONTENT_" + (b"A" * 20_000)
        self.fake_whl_sha = hashlib.sha256(self.fake_whl_bytes).hexdigest()
        self.fake_release_json = {
            "tag_name": "v9.5.0",
            "name": "Karius Academic System (KAS) v9.5.0",
            "html_url": "https://github.com/kariusnocr/storage-management-suite/releases/tag/v9.5.0",
            "published_at": "2026-12-01T00:00:00Z",
            "prerelease": False,
            "body": "## What's New\n- Amazing new v9.5.0 features!",
            "assets": [
                {
                    "name": "karius_academic_system-9.5.0-py3-none-any.whl",
                    "browser_download_url": "https://example.invalid/karius_academic_system-9.5.0-py3-none-any.whl",
                    "url": "https://api.example.invalid/assets/1",
                    "size": len(self.fake_whl_bytes),
                },
                {
                    "name": "SHA256SUMS.txt",
                    "browser_download_url": "https://example.invalid/SHA256SUMS.txt",
                    "url": "https://api.example.invalid/assets/2",
                    "size": 120,
                },
            ],
        }

    def tearDown(self) -> None:
        for k, v in self._env_backup.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        sc.reload_config()
        self._tmp.cleanup()

    def _mock_urlopen_factory(self, sha_override: str | None = None):
        sha_val = sha_override if sha_override is not None else self.fake_whl_sha
        sums_bytes = f"{sha_val}  karius_academic_system-9.5.0-py3-none-any.whl\n".encode("utf-8")
        rel_bytes = json.dumps(self.fake_release_json).encode("utf-8")
        real_urlopen = urllib.request.urlopen

        def _fake_open(req, timeout=10):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if url.startswith("http://127.0.0.1:"):
                return real_urlopen(req, timeout=timeout)
            if "api.github.com" in url:
                return _FakeBytesResp(rel_bytes)
            if url.endswith(".whl"):
                return _FakeBytesResp(self.fake_whl_bytes)
            if url.endswith("SHA256SUMS.txt"):
                return _FakeBytesResp(sums_bytes)
            raise AssertionError(f"Unexpected URL in test: {url}")

        return _fake_open

    def test_settings_update_preferences_and_cached_check_with_skip(self) -> None:
        self.assertEqual(__version__, "1.4.0")
        st = sc.AppSettings(auto_check_updates=True, auto_install_updates=True, update_channel="prerelease", update_check_interval_hours=12)
        sc.save_app_settings(st)
        loaded = sc.load_app_settings()
        self.assertTrue(loaded.auto_install_updates)
        self.assertEqual(loaded.update_channel, "prerelease")
        self.assertEqual(loaded.update_check_interval_hours, 12)

        with mock.patch("urllib.request.urlopen", side_effect=self._mock_urlopen_factory()):
            r1 = updater.check_for_updates(force=True)
        self.assertTrue(r1["ok"])
        self.assertTrue(r1["update_available"])
        self.assertEqual(r1["latest_version"], "9.5.0")
        self.assertFalse(r1["from_cache"])
        self.assertIn("Amazing new v9.5.0", r1["release_notes"])

        # Lần gọi kế tiếp không có force=True phải dùng bộ đệm (không gọi mạng!)
        with mock.patch("urllib.request.urlopen", side_effect=AssertionError("Phải đọc từ cache!")):
            r2 = updater.check_for_updates(force=False)
        self.assertTrue(r2["from_cache"])
        self.assertEqual(r2["latest_version"], "9.5.0")

        # Bỏ qua phiên bản 9.5.0
        updater.skip_update_version("v9.5.0")
        with mock.patch("urllib.request.urlopen", side_effect=AssertionError("Phải đọc từ cache!")):
            r3 = updater.check_for_updates(force=False)
        self.assertTrue(r3["is_skipped"])

    def test_sha256_verification_passes_valid_and_aborts_tampered_wheel(self) -> None:
        with mock.patch("urllib.request.urlopen", side_effect=self._mock_urlopen_factory()):
            rel = updater.fetch_release_metadata()
            whl_path, meta = updater.download_and_verify_wheel(rel)
        self.assertTrue(whl_path.exists())
        self.assertTrue(meta["sha256_verified"])
        self.assertEqual(meta["sha256"], self.fake_whl_sha)

        # Kiểm thử phát hiện tệp bị giả mạo / sai băm SHA-256 -> PHẢI HỦY NGAY!
        bad_sha = "0" * 64
        with mock.patch("urllib.request.urlopen", side_effect=self._mock_urlopen_factory(sha_override=bad_sha)):
            rel2 = updater.fetch_release_metadata()
            with self.assertRaises(RuntimeError) as ctx:
                updater.download_and_verify_wheel(rel2)
        self.assertIn("SHA-256 THẤT BẠI", str(ctx.exception))

    def test_apply_update_records_history_rollback_target_and_restart_script_ascii(self) -> None:
        fake_proc = mock.MagicMock(returncode=0, stdout="Successfully installed karius-academic-system-9.5.0", stderr="")
        with mock.patch("urllib.request.urlopen", side_effect=self._mock_urlopen_factory()):
            with mock.patch("subprocess.run", return_value=fake_proc) as run_mock:
                res = updater.apply_update()
        self.assertTrue(res["ok"])
        self.assertTrue(res["updated"])
        self.assertEqual(res["from_version"], __version__)
        self.assertEqual(res["to_version"], "9.5.0")
        self.assertTrue(res["verification"]["sha256_verified"])
        self.assertTrue(run_mock.called)

        # Kiểm chứng lịch sử đã được ghi lại
        st = updater.load_update_state()
        self.assertEqual(len(st["history"]), 1)
        self.assertEqual(st["history"][0]["to_version"], "9.5.0")

        # Giả lập đang chạy ở bản 9.5.0 -> rollback phải trả về bản trước đó (__version__)
        st["history"][0]["from_version"] = "1.3.0"
        updater.save_update_state(st)
        self.assertEqual(updater.get_rollback_target_version(), "1.3.0")

        # Kịch bản tự khởi động lại trên Windows phải 100% ASCII + CRLF
        ps_txt = updater._generate_windows_restart_ps1(9999, r"C:\Python312\python.exe", "127.0.0.1", 8765, stdlib=True)
        ps_raw = ps_txt.encode("ascii")
        self.assertNotIn(b"\n", ps_raw.replace(b"\r\n", b""))

    def test_cli_and_stdlib_http_update_endpoints(self) -> None:
        with mock.patch("urllib.request.urlopen", side_effect=self._mock_urlopen_factory()):
            self.assertEqual(kas_cli(["update", "--check", "--json"]), 0)
            self.assertEqual(kas_cli(["update", "--chay-thu"]), 0)
            self.assertEqual(kas_cli(["update", "--history"]), 0)

        port = _free_port()
        _, stop_fn, engine = start_embedded_server(host="127.0.0.1", port=port, prefer_stdlib=True)
        self.assertEqual(engine, "stdlib-http")
        base = f"http://127.0.0.1:{port}"
        try:
            with mock.patch("urllib.request.urlopen", side_effect=self._mock_urlopen_factory()):
                st_chk, chk = _http_json(f"{base}/api/update/check?force=true")
                self.assertEqual(st_chk, 200)
                self.assertTrue(chk["update_available"])
                self.assertEqual(chk["latest_version"], "9.5.0")

                st_skip, skip = _http_json(f"{base}/api/update/skip", method="POST", body={"version": "9.5.0"})
                self.assertEqual(st_skip, 200)
                self.assertEqual(skip["skipped_version"], "9.5.0")

                st_run, job = _http_json(
                    f"{base}/api/update/apply",
                    method="POST",
                    body={"dry_run": True, "auto_restart": False},
                )
                self.assertEqual(st_run, 200)
                jid = job["id"]
                cur = job
                for _ in range(30):
                    st_poll, cur = _http_json(f"{base}/api/update/jobs/{jid}")
                    self.assertEqual(st_poll, 200)
                    if cur["status"] != "running":
                        break
                    time.sleep(0.05)
                self.assertEqual(cur["status"], "done")
                self.assertTrue(cur["ok"])
        finally:
            stop_fn()


if __name__ == "__main__":
    unittest.main()
