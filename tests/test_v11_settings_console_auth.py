"""Bộ kiểm thử chuyên sâu cho Karius Academic System (KAS) v1.1.0:
1. Cài đặt phần mềm (AppSettings, ghi đè cấu hình, kiểm tra cập nhật, sao lưu/nhập JSON, CLI `kas settings`)
2. Dòng lệnh tích hợp (Console: tách tham số Windows `E:\\SÁCH`, chặn lệnh đệ quy, lịch sử, chạy đồng bộ/nền qua HTTP)
3. Đăng nhập phần mềm (PBKDF2-HMAC-SHA256, App Lock HTTP 401 -> Cookie -> 200 -> Logout) & Kết nối bên thứ 3 (Google Drive OAuth, GitHub PAT, Connector tùy chỉnh).
"""

from __future__ import annotations

import json
import os
import socket
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from karius_academic_system import __version__
from karius_academic_system import core as sc
from karius_academic_system.cli.console import (
    clear_command_history,
    load_command_history,
    run_console_command_sync,
    split_command_line,
    validate_console_argv,
)
from karius_academic_system.cli.main import main as kas_cli
from karius_academic_system.web.app import start_embedded_server


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _http_req(
    url: str,
    method: str = "GET",
    body: dict | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict, dict[str, str]]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req_headers = dict(headers or {})
    if body is not None:
        req_headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            resp_headers = {k.lower(): v for k, v in resp.headers.items()}
            return resp.status, json.loads(resp.read().decode("utf-8")), resp_headers
    except urllib.error.HTTPError as exc:
        resp_headers = {k.lower(): v for k, v in exc.headers.items()}
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"detail": raw}
        return exc.code, payload, resp_headers


def _extract_cookie(headers: dict[str, str]) -> str:
    sc_hdr = headers.get("set-cookie", "")
    return sc_hdr.split(";", 1)[0].strip() if sc_hdr else ""


class _FakeHTTPResponse:
    def __init__(self, payload: dict, headers: dict[str, str] | None = None) -> None:
        self._bytes = json.dumps(payload).encode("utf-8")
        self.headers = headers or {}

    def read(self) -> bytes:
        return self._bytes

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, *args) -> None:
        return None


class TestKASv11SettingsConsoleAndAuth(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._env_backup = {
            k: os.environ.get(k)
            for k in (
                "KAS_CONFIG_DIR",
                "KAS_DATA_DIR",
                "KAS_ROOT_ID",
                "KAS_ROOT_NAME",
                "KAS_BACKEND",
                "GITHUB_TOKEN",
            )
        }
        os.environ["KAS_CONFIG_DIR"] = str(self.root / "cfg")
        os.environ["KAS_DATA_DIR"] = str(self.root / "data")
        for k in ("KAS_ROOT_ID", "KAS_ROOT_NAME", "KAS_BACKEND", "GITHUB_TOKEN"):
            os.environ.pop(k, None)
        sc.destroy_all_sessions()
        sc.reload_config()

        self.vault_dir = self.root / "KhoKiemThu"
        (self.vault_dir / "Mon Hoc").mkdir(parents=True)
        (self.vault_dir / "Mon Hoc" / "Tai Lieu - 2026.pdf").write_text("noi dung", encoding="utf-8")
        self.assertEqual(kas_cli(["vault", "add", "Kho v11", str(self.vault_dir)]), 0)
        self.assertEqual(kas_cli(["quet"]), 0)

    def tearDown(self) -> None:
        sc.destroy_all_sessions()
        for k, v in self._env_backup.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        sc.reload_config()
        self._tmp.cleanup()

    def test_app_settings_persistence_overrides_update_check_and_cli(self) -> None:
        self.assertEqual(__version__, "1.1.0")
        default_st = sc.load_app_settings()
        self.assertEqual(default_st.theme, "dark")
        self.assertEqual(default_st.drive_backend, "auto")

        custom_data = self.root / "custom_data"
        st = sc.AppSettings(
            theme="light",
            language="en",
            default_tab="console",
            drive_backend="api",
            scan_workers=16,
            catalog_default_mode="full",
            ui_port=9123,
            data_dir_override=str(custom_data),
        )
        sc.save_app_settings(st)

        loaded = sc.load_app_settings()
        self.assertEqual(loaded.theme, "light")
        self.assertEqual(loaded.default_tab, "console")
        self.assertEqual(loaded.drive_backend, "api")
        self.assertEqual(loaded.scan_workers, 16)
        self.assertEqual(loaded.ui_port, 9123)
        self.assertEqual(sc.drive_backend_preference(), "api")

        # Nếu không đặt KAS_DATA_DIR thì core/config.py phải tôn trọng data_dir_override (và tách riêng theo kho đang chọn)
        os.environ.pop("KAS_DATA_DIR", None)
        sc.reload_config()
        self.assertEqual(sc.data_dir(), custom_data / "vaults" / "kho-v11")
        os.environ["KAS_DATA_DIR"] = str(self.root / "data")
        sc.reload_config()

        # Kiểm tra CLI `kas settings show / set / reset`
        self.assertEqual(kas_cli(["settings", "show"]), 0)
        self.assertEqual(kas_cli(["settings", "set", "scan_workers", "24"]), 0)
        self.assertEqual(sc.load_app_settings().scan_workers, 24)
        self.assertEqual(kas_cli(["settings", "set", "invalid_key_xyz", "1"]), 1)

        # Kiểm tra check_latest_release (mock HTTP)
        fake_release = {
            "tag_name": "v1.2.0",
            "name": "KAS v1.2.0",
            "html_url": "https://github.com/kariusnocr/storage-management-suite/releases/tag/v1.2.0",
            "published_at": "2026-11-22T00:00:00Z",
        }
        with mock.patch("urllib.request.urlopen", return_value=_FakeHTTPResponse(fake_release)):
            upd = sc.check_latest_release()
        self.assertTrue(upd["ok"])
        self.assertTrue(upd["update_available"])
        self.assertEqual(upd["latest_version"], "1.2.0")

        self.assertEqual(kas_cli(["settings", "reset"]), 0)
        self.assertEqual(sc.load_app_settings().theme, "dark")

    def test_console_windows_path_splitting_validation_execution_and_history(self) -> None:
        # 1. Bảo toàn đường dẫn Windows có dấu backslash và khoảng trắng
        argv = split_command_line(r'kas vault add "Tủ Sách" "E:\SÁCH\Triết Học"')
        self.assertEqual(argv, ["vault", "add", "Tủ Sách", r"E:\SÁCH\Triết Học"])

        # 2. Chặn lệnh tương tác gây lặp giao diện & xử lý ngoặc không đóng
        ok_ui, _ = validate_console_argv(["ui"])
        self.assertFalse(ok_ui)
        ok_desktop, _ = validate_console_argv(["--kho", "abc", "desktop"])
        self.assertFalse(ok_desktop)
        ok_ai_chat, _ = validate_console_argv(["ai", "chat"])
        self.assertFalse(ok_ai_chat)
        ok_mcp_serve, _ = validate_console_argv(["mcp", "serve"])
        self.assertFalse(ok_mcp_serve)
        ok_ver, _ = validate_console_argv(["version"])
        self.assertTrue(ok_ver)

        bad_quote = run_console_command_sync('vault add "chưa đóng ngoặc')
        self.assertFalse(bad_quote["ok"])
        self.assertEqual(bad_quote["returncode"], 2)

        # 3. Thực thi lệnh thật & lưu lịch sử
        clear_command_history()
        res = run_console_command_sync("kas version")
        self.assertTrue(res["ok"])
        self.assertEqual(res["returncode"], 0)
        self.assertIn("1.1.0", res["output"])
        hist = load_command_history()
        self.assertEqual(len(hist), 1)
        self.assertEqual(hist[0]["command"], "kas version")

    def test_account_third_party_integrations_and_cli(self) -> None:
        # 1. Tài khoản cục bộ + PBKDF2 + đổi mật khẩu
        prof, tok = sc.register_account("karius", "MatKhau123", display_name="Karius Admin", email="admin@kas.local", require_login=True)
        self.assertEqual(prof["username"], "karius")
        self.assertTrue(sc.is_app_lock_enabled())
        self.assertIsNotNone(sc.verify_session(tok))

        # Không lưu mật khẩu dạng văn bản thuần trên đĩa
        raw_disk = sc.account_path().read_text(encoding="utf-8")
        self.assertNotIn("MatKhau123", raw_disk)

        ok_bad, _, _ = sc.authenticate_account("karius", "SaiMatKhau")
        self.assertFalse(ok_bad)
        ok_good, _, tok2 = sc.authenticate_account("karius", "MatKhau123")
        self.assertTrue(ok_good)
        self.assertIsNotNone(tok2)

        sc.change_account_password("MatKhau123", "MatKhauMoi456")
        ok_old, _, _ = sc.authenticate_account("karius", "MatKhau123")
        self.assertFalse(ok_old)
        ok_new, _, _ = sc.authenticate_account("karius", "MatKhauMoi456")
        self.assertTrue(ok_new)

        # 2. Lưu Google Drive OAuth credentials.json (cả dán JSON và đường dẫn tệp)
        fake_creds = {
            "installed": {
                "client_id": "1234567890-abcdefg.apps.googleusercontent.com",
                "project_id": "kas-academic-demo",
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }
        g_res = sc.save_google_credentials_json(json.dumps(fake_creds))
        self.assertTrue(g_res["ok"])
        self.assertTrue(sc.oauth_credentials_path().exists())
        self.assertEqual(g_res["project_id"], "kas-academic-demo")

        with self.assertRaises(ValueError):
            sc.save_google_credentials_json('{"not_google": true}')

        # 3. Kết nối GitHub PAT (mock API)
        gh_resp = _FakeHTTPResponse(
            {"login": "kariusnocr", "name": "Karius", "html_url": "https://github.com/kariusnocr"},
            headers={"X-OAuth-Scopes": "repo, workflow"},
        )
        with mock.patch("urllib.request.urlopen", return_value=gh_resp):
            gh_st = sc.connect_github_token("ghp_demo_token_1234567890")
        self.assertTrue(gh_st["connected"])
        self.assertEqual(gh_st["method"], "pat")
        self.assertEqual(gh_st["login"], "kariusnocr")
        self.assertEqual(sc.get_saved_github_token(), "ghp_demo_token_1234567890")

        # 4. Connector bên thứ 3 tùy chỉnh (Webhook / n8n / WebDAV)
        conns = sc.add_custom_connector(
            "n8n-sync",
            "n8n",
            "https://n8n.local/webhook/kas",
            api_key="sec_key_99887766",
            notes="Đồng bộ báo cáo",
        )
        self.assertEqual(len(conns), 1)
        self.assertTrue(conns[0]["has_api_key"])
        self.assertNotIn("sec_key_99887766", json.dumps(conns))
        self.assertEqual(len(sc.remove_custom_connector("n8n-sync")), 0)

        # 5. CLI `kas account status / lock`
        self.assertEqual(kas_cli(["account", "status"]), 0)
        self.assertEqual(kas_cli(["account", "lock", "off"]), 0)
        self.assertFalse(sc.is_app_lock_enabled())

    def test_stdlib_http_app_lock_console_settings_and_integrations_end_to_end(self) -> None:
        port = _free_port()
        _, stop_fn, engine = start_embedded_server(host="127.0.0.1", port=port, prefer_stdlib=True)
        self.assertEqual(engine, "stdlib-http")
        base = f"http://127.0.0.1:{port}"
        try:
            # 1. Trước khi bật khóa, /api/overview mở bình thường
            st, ov, _ = _http_req(f"{base}/api/overview")
            self.assertEqual(st, 200)
            self.assertEqual(ov["version"], "1.1.0")

            # 2. Đăng ký tài khoản kèm require_login=True -> nhận cookie phiên
            st, reg, hdrs = _http_req(
                f"{base}/api/account/register",
                method="POST",
                body={"username": "admin", "password": "secret123", "display_name": "Quản Trị", "require_login": True},
            )
            self.assertEqual(st, 200)
            self.assertTrue(reg["ok"])
            cookie = _extract_cookie(hdrs)
            self.assertTrue(cookie.startswith("kas_session="))

            # 3. Gọi API KHÔNG gửi cookie -> bị khóa 401
            st_unauth, body_unauth, _ = _http_req(f"{base}/api/overview")
            self.assertEqual(st_unauth, 401)
            self.assertTrue(body_unauth.get("locked"))

            # Nhưng /api/health và /api/account/status vẫn public để UI hiển thị màn hình đăng nhập
            st_acc, acc_body, _ = _http_req(f"{base}/api/account/status")
            self.assertEqual(st_acc, 200)
            self.assertTrue(acc_body["locked"])

            # 4. Gọi API KÈM cookie phiên -> mở 200
            auth_hdr = {"Cookie": cookie}
            st_ok, _, _ = _http_req(f"{base}/api/overview", headers=auth_hdr)
            self.assertEqual(st_ok, 200)

            # 5. Lưu & kiểm tra Cài đặt qua HTTP
            st_set, set_body, _ = _http_req(
                f"{base}/api/settings",
                method="POST",
                body={"theme": "light", "scan_workers": 20, "default_tab": "console"},
                headers=auth_hdr,
            )
            self.assertEqual(st_set, 200)
            self.assertEqual(set_body["settings"]["theme"], "light")
            self.assertEqual(set_body["settings"]["scan_workers"], 20)

            st_exp, exp_body, _ = _http_req(f"{base}/api/settings/export", headers=auth_hdr)
            self.assertEqual(st_exp, 200)
            self.assertEqual(exp_body["settings"]["theme"], "light")

            # 6. Chạy Dòng Lệnh tích hợp qua HTTP (async job + polling)
            st_run, job_body, _ = _http_req(
                f"{base}/api/console/run",
                method="POST",
                body={"command": "kas vault list"},
                headers=auth_hdr,
            )
            self.assertEqual(st_run, 200)
            jid = job_body["id"]
            final_job = job_body
            for _ in range(30):
                st_poll, final_job, _ = _http_req(f"{base}/api/console/jobs/{jid}", headers=auth_hdr)
                self.assertEqual(st_poll, 200)
                if final_job["status"] != "running":
                    break
                time.sleep(0.05)
            self.assertEqual(final_job["status"], "done")
            self.assertEqual(final_job["returncode"], 0)
            self.assertIn("Kho v11", final_job["output"])

            # 7. Lưu Google credentials & Connector qua HTTP
            st_gc, gc_body, _ = _http_req(
                f"{base}/api/integrations/google/credentials",
                method="POST",
                body={
                    "credentials_json": json.dumps(
                        {"installed": {"client_id": "987654321-xyz.apps.googleusercontent.com", "project_id": "kas-ui"}}
                    )
                },
                headers=auth_hdr,
            )
            self.assertEqual(st_gc, 200)
            self.assertTrue(gc_body["ok"])

            st_conn, conn_body, _ = _http_req(
                f"{base}/api/integrations/connectors/add",
                method="POST",
                body={"name": "hook-1", "kind": "webhook", "endpoint_url": "https://example.invalid/hook"},
                headers=auth_hdr,
            )
            self.assertEqual(st_conn, 200)
            self.assertEqual(len(conn_body["connectors"]), 1)

            # 8. Đăng xuất -> cookie cũ bị hủy -> truy cập lại bị 401
            st_out, _, _ = _http_req(f"{base}/api/account/logout", method="POST", body={}, headers=auth_hdr)
            self.assertEqual(st_out, 200)
            st_after, _, _ = _http_req(f"{base}/api/overview", headers=auth_hdr)
            self.assertEqual(st_after, 401)

            # 9. Đăng nhập lại bằng mật khẩu -> nhận cookie mới -> truy cập thành công 200
            st_in, _, hdrs_in = _http_req(
                f"{base}/api/account/login",
                method="POST",
                body={"username": "admin", "password": "secret123"},
            )
            self.assertEqual(st_in, 200)
            cookie2 = _extract_cookie(hdrs_in)
            st_reok, _, _ = _http_req(f"{base}/api/overview", headers={"Cookie": cookie2})
            self.assertEqual(st_reok, 200)
        finally:
            stop_fn()


if __name__ == "__main__":
    unittest.main()
