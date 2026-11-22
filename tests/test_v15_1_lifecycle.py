"""Bộ kiểm thử chuyên sâu cho Cơ chế Tự Đóng & Tự Khởi Động Lại khi Cập Nhật / Gỡ Cài Đặt (KAS v1.5.1):
- `/api/health` trả về `boot_id` và `pid` để trình duyệt nhận diện chính xác máy chủ mới sau khởi động lại
- Sổ phiên chạy `runtime.json` (`register_runtime`, `read_runtime`, `clear_runtime`) & hồ sơ trình duyệt cô lập (`browser_profile`)
- Kiểm chứng không còn lỗi thiếu dấu phẩy trong `_generate_windows_restart_ps1` (`'8765', '--stdlib'`) trên mọi tổ hợp
- Kiểm chứng `_generate_windows_detached_ps1` chuyển `pythonw.exe` -> `python.exe` để `pip uninstall` chặn chờ đúng và đóng cửa sổ KAS
- Kiểm chứng kịch bản PowerShell cài đặt & gỡ cài đặt Windows tự dừng tiến trình & cửa sổ KAS cũ
- Kiểm chứng `POST /api/shutdown` tắt sạch máy chủ `--stdlib` mà không gây treo cổng.
"""

from __future__ import annotations

import http.client
import json
import os
import re
import socket
import tempfile
import time
import unittest
from pathlib import Path

from karius_academic_system import __version__
from karius_academic_system import core as sc
from karius_academic_system.ops import uninstaller, updater
from karius_academic_system.web import app as web_app
from karius_academic_system.web import desktop
from karius_academic_system.web import lifecycle as lc

_REPO_ROOT = Path(__file__).resolve().parent.parent
_STATIC_DIR = Path(web_app.__file__).resolve().parent / "static"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class TestKASv151LifecycleRestartClose(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._env_backup = {k: os.environ.get(k) for k in ("KAS_CONFIG_DIR", "KAS_DATA_DIR")}
        os.environ["KAS_CONFIG_DIR"] = str(self.root / "cfg")
        os.environ["KAS_DATA_DIR"] = str(self.root / "data")
        sc.reload_config()
        lc.set_process_exit_allowed(False)

    def tearDown(self) -> None:
        lc.set_process_exit_allowed(False)
        for k, v in self._env_backup.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        sc.reload_config()
        self._tmp.cleanup()

    def test_version_runtime_registry_and_isolated_browser_command(self) -> None:
        self.assertTrue(__version__.startswith("1."), __version__)

        rt_path = lc.register_runtime(host="127.0.0.1", port=8765, stdlib=True, mode="desktop", browser_pid=4242)
        self.assertTrue(rt_path.exists())
        rt = lc.read_runtime()
        self.assertEqual(rt["pid"], os.getpid())
        self.assertEqual(rt["boot_id"], lc.BOOT_ID)
        self.assertEqual(rt["port"], 8765)
        self.assertEqual(rt["browser_pid"], 4242)
        self.assertIn("browser_profile", rt["browser_profile"])

        cmd = desktop.build_app_window_command("/usr/bin/msedge", "http://127.0.0.1:8765")
        self.assertTrue(any(a.startswith("--user-data-dir=") and "browser_profile" in a for a in cmd))
        self.assertIn("--app=http://127.0.0.1:8765", cmd)
        self.assertIn("--new-window", cmd)

        lc.clear_runtime(only_if_self=True)
        self.assertFalse(rt_path.exists())

    def test_windows_restart_ps1_valid_array_syntax_and_no_missing_comma(self) -> None:
        for stdlib in (True, False):
            for reopen in (True, False):
                ps = updater._generate_windows_restart_ps1(
                    9999,
                    r"C:\Python312\pythonw.exe",
                    "127.0.0.1",
                    8765,
                    stdlib=stdlib,
                    reopen_window=reopen,
                )
                raw = ps.encode("ascii")
                self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))
                # Kiểm chứng không bao giờ lặp lại lỗi thiếu dấu phẩy `'8765' '--stdlib'`!
                self.assertNotIn("'8765' '--stdlib'", ps)
                m = re.search(r"-ArgumentList @\(([^)]+)\)", ps)
                self.assertIsNotNone(m, f"Thiếu -ArgumentList @(...) trong script: {ps}")
                items = [tok.strip() for tok in m.group(1).split(",")]
                for tok in items:
                    self.assertRegex(tok, r"^'[^']+'$", f"Phần tử mảng PowerShell không hợp lệ: {tok}")
                if stdlib:
                    self.assertIn("'--stdlib'", items)
                else:
                    self.assertNotIn("'--stdlib'", items)
                if reopen:
                    self.assertIn("'desktop'", items)
                else:
                    self.assertIn("'ui'", items)
                self.assertIn("Stop-Process -Id $waitPid -Force", ps)
                self.assertIn("System.Net.Sockets.TcpClient", ps)
                self.assertIn("-WindowStyle Hidden", ps)

    def test_windows_detached_uninstall_ps1_closes_window_and_uses_python_exe(self) -> None:
        ps = uninstaller._generate_windows_detached_ps1(
            wait_pid=8888,
            python_exe=r"C:\Python312\pythonw.exe",
            cfg_dir=Path(r"C:\Users\Admin\.config\kas"),
            data_root=Path(r"C:\Users\Admin\.local\share\kas"),
            remove_config=False,
            remove_data=False,
            browser_pid=7777,
            port=8765,
        )
        raw = ps.encode("ascii")
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))
        self.assertIn("pythonw\\.exe$", ps)
        self.assertIn("Stop-Process -Id $browserPid -Force", ps)
        self.assertIn("browser_profile", ps)
        self.assertIn("CloseMainWindow()", ps)
        self.assertIn("OneDrive\\Desktop", ps)

    def test_windows_installer_and_uninstaller_scripts_handle_running_kas(self) -> None:
        win_dir = _REPO_ROOT / "packaging" / "windows"
        inst_raw = (win_dir / "install_windows_sac_safe.ps1").read_bytes()
        uninst_raw = (win_dir / "uninstall_windows_sac_safe.ps1").read_bytes()
        for name, raw in (("install_windows_sac_safe.ps1", inst_raw), ("uninstall_windows_sac_safe.ps1", uninst_raw)):
            self.assertEqual([b for b in raw if b >= 128], [], f"{name} có byte ngoài ASCII!")
            self.assertNotIn(b"\n", raw.replace(b"\r\n", b""), f"{name} chưa chuẩn CRLF!")
        inst_txt = inst_raw.decode("ascii")
        uninst_txt = uninst_raw.decode("ascii")
        self.assertIn("browser_profile", inst_txt)
        self.assertIn("Stop-Process -Id $op.ProcessId -Force", inst_txt)
        self.assertIn("runtime.json", uninst_txt)
        self.assertIn("CloseMainWindow()", uninst_txt)

    def test_health_exposes_boot_id_and_shutdown_stops_server_cleanly(self) -> None:
        port = _free_port()
        th, stop_fn, engine = web_app.start_embedded_server(host="127.0.0.1", port=port, prefer_stdlib=True)
        self.assertEqual(engine, "stdlib-http")
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request("GET", "/api/health")
            resp = conn.getresponse()
            health = json.loads(resp.read().decode("utf-8"))
            conn.close()
            self.assertEqual(resp.status, 200)
            self.assertEqual(health["boot_id"], lc.BOOT_ID)
            self.assertEqual(health["pid"], os.getpid())

            conn2 = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn2.request("POST", "/api/shutdown", body=b"{}", headers={"Content-Type": "application/json"})
            resp2 = conn2.getresponse()
            sd = json.loads(resp2.read().decode("utf-8"))
            conn2.close()
            self.assertEqual(resp2.status, 200)
            self.assertTrue(sd["ok"])
            self.assertTrue(sd["closing"])

            # Máy chủ phải tự dừng trong vòng vài giây và nhả cổng ngay!
            deadline = time.monotonic() + 5.0
            while th.is_alive() and time.monotonic() < deadline:
                time.sleep(0.1)
            self.assertFalse(th.is_alive(), "Máy chủ stdlib không tự tắt sau /api/shutdown!")
        finally:
            stop_fn()

    def test_frontend_lifecycle_overlay_boot_id_and_window_close(self) -> None:
        html = (_STATIC_DIR / "index.html").read_text(encoding="utf-8")
        js = (_STATIC_DIR / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="lifecycleOverlay"', html)
        self.assertIn("h.boot_id !== oldBootId", js)
        self.assertIn("window.location.replace(", js)
        self.assertIn("window.close()", js)


if __name__ == "__main__":
    unittest.main()
