"""Bộ kiểm thử chuyên sâu cho cơ chế Gỡ cài đặt phần mềm (KAS v1.3.0):
- Kiểm kê thành phần cài đặt (`inspect_installation`)
- Chế độ xem trước an toàn (`dry_run=True`), bảo toàn 100% thư mục tài liệu cá nhân của người dùng
- Gỡ cấu hình & dữ liệu cô lập (`remove_config=True`, `remove_data=True`) mà KHÔNG chạm thư mục kho tài liệu
- Kiểm chứng kịch bản gỡ Windows (100% pure 7-bit ASCII + CRLF) & đóng gói trong `kas-windows-sac-safe.zip`
- Kiểm chứng bảo vệ Console & HTTP `/api/uninstall/plan`, `/api/uninstall/run` (`dry_run` / `confirm=False`).
"""

from __future__ import annotations

import json
import os
import socket
import tempfile
import unittest
import urllib.request
import zipfile
from pathlib import Path

from karius_academic_system import __version__
from karius_academic_system import core as sc
from karius_academic_system.cli.console import validate_console_argv
from karius_academic_system.cli.main import main as kas_cli
from karius_academic_system.ops import uninstaller
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


class TestKASv13Uninstaller(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._env_backup = {k: os.environ.get(k) for k in ("KAS_CONFIG_DIR", "KAS_DATA_DIR")}
        self.cfg_dir = self.root / "cfg"
        self.data_dir = self.root / "data"
        self.user_vault = self.root / "KhoTaiLieuCaNhan"
        self.user_vault.mkdir(parents=True)
        (self.user_vault / "SachQuanTrong.pdf").write_text("Noi dung sach khong bao gio duoc xoa", encoding="utf-8")

        os.environ["KAS_CONFIG_DIR"] = str(self.cfg_dir)
        os.environ["KAS_DATA_DIR"] = str(self.data_dir)
        sc.reload_config()
        self.assertEqual(kas_cli(["vault", "add", "Tủ Sách", str(self.user_vault)]), 0)
        self.assertEqual(kas_cli(["quet"]), 0)

    def tearDown(self) -> None:
        for k, v in self._env_backup.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        sc.reload_config()
        self._tmp.cleanup()

    def test_inspect_dry_run_and_safe_purge_preserves_user_vault_100_percent(self) -> None:
        self.assertTrue(__version__.startswith("1."), __version__)

        # 1. Mặc định không chọn xóa config/data
        plan_keep = uninstaller.inspect_installation(remove_config=False, remove_data=False)
        self.assertEqual(plan_keep["version"], __version__)
        self.assertIn("KHÔNG BAO GIỜ", plan_keep["safety_note"])
        cfg_item = next(i for i in plan_keep["items"] if i["category"] == "config")
        data_item = next(i for i in plan_keep["items"] if i["category"] == "data")
        self.assertFalse(cfg_item["selected"])
        self.assertFalse(data_item["selected"])

        # 2. Chế độ dry_run=True KHÔNG xóa bất kỳ tệp nào
        dry_res = uninstaller.perform_uninstall(
            remove_config=True,
            remove_data=True,
            uninstall_python_pkg=False,
            dry_run=True,
        )
        self.assertTrue(dry_res["ok"])
        self.assertTrue(dry_res["dry_run"])
        self.assertTrue(self.cfg_dir.exists())
        self.assertTrue(self.data_dir.exists())

        # 3. Thực thi xóa cấu hình & dữ liệu cô lập (không gỡ pip trong lúc test) -> xóa sạch cfg/data nhưng GIỮ NGUYÊN 100% kho tài liệu cá nhân!
        exec_res = uninstaller.perform_uninstall(
            remove_config=True,
            remove_data=True,
            uninstall_python_pkg=False,
            dry_run=False,
        )
        self.assertTrue(exec_res["ok"], exec_res["errors"])
        self.assertFalse(self.cfg_dir.exists())
        self.assertFalse(self.data_dir.exists())
        self.assertTrue((self.user_vault / "SachQuanTrong.pdf").exists())

    def test_windows_uninstaller_scripts_ascii_crlf_and_sac_zip_bundle(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        win_dir = repo_root / "packaging" / "windows"
        for fname in ("uninstall_windows_sac_safe.ps1", "Go_Cai_Dat_KAS_Windows11.cmd"):
            p = win_dir / fname
            self.assertTrue(p.exists(), f"Thiếu {p}")
            raw = p.read_bytes()
            self.assertEqual([b for b in raw if b >= 128], [], f"{fname} chứa ký tự ngoài ASCII 7-bit!")
            self.assertNotIn(b"\n", raw.replace(b"\r\n", b""), f"{fname} chưa chuẩn CRLF!")

        # Kiểm tra script tự gỡ tách rời sinh ra trên Windows cũng thuần ASCII + CRLF
        ps_text = uninstaller._generate_windows_detached_ps1(
            wait_pid=12345,
            python_exe=r"C:\Python312\python.exe",
            cfg_dir=Path(r"C:\Users\Admin\.config\kas"),
            data_root=Path(r"C:\Users\Admin\.local\share\kas"),
            remove_config=True,
            remove_data=False,
        )
        ps_bytes = ps_text.encode("ascii")
        self.assertNotIn(b"\n", ps_bytes.replace(b"\r\n", b""))
        self.assertIn(b"KariusAcademicSystem", ps_bytes)

        # Kiểm tra build_sac_bundle đóng gói cả 2 tệp gỡ cài đặt vào ZIP
        import importlib.util

        spec = importlib.util.spec_from_file_location("build_sac_bundle", repo_root / "packaging" / "build_sac_bundle.py")
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        fake_dist = self.root / "dist"
        fake_dist.mkdir()
        (fake_dist / "karius_academic_system-1.3.0-py3-none-any.whl").write_bytes(b"PK\x05\x06" + b"\x00" * 18)
        out_zip = mod.build_sac_bundle(fake_dist, self.root / "kas-windows-sac-safe.zip")
        with zipfile.ZipFile(out_zip, "r") as zf:
            names = set(zf.namelist())
        self.assertIn("Go_Cai_Dat_KAS_Windows11.cmd", names)
        self.assertIn("uninstall_windows_sac_safe.ps1", names)
        self.assertIn("Cai_Dat_KAS_Windows11.cmd", names)
        self.assertIn("install_windows_sac_safe.ps1", names)

    def test_cli_console_guard_and_stdlib_http_uninstall_endpoints(self) -> None:
        # CLI preview mặc định an toàn
        self.assertEqual(kas_cli(["uninstall"]), 0)
        self.assertEqual(kas_cli(["go-cai-dat", "--json"]), 0)
        self.assertTrue(self.cfg_dir.exists())

        # Console cho phép xem trước nhưng chặn `--thuc-thi` trực tiếp
        ok_preview, _ = validate_console_argv(["uninstall"])
        self.assertTrue(ok_preview)
        ok_exec, msg_exec = validate_console_argv(["uninstall", "--thuc-thi"])
        self.assertFalse(ok_exec)
        self.assertIn("Cài Đặt", msg_exec)

        # HTTP endpoints (stdlib)
        port = _free_port()
        _, stop_fn, engine = start_embedded_server(host="127.0.0.1", port=port, prefer_stdlib=True)
        self.assertEqual(engine, "stdlib-http")
        base = f"http://127.0.0.1:{port}"
        try:
            st, plan = _http_json(f"{base}/api/uninstall/plan?remove_config=true&remove_data=false")
            self.assertEqual(st, 200)
            self.assertTrue(plan["remove_config"])
            self.assertFalse(plan["remove_data"])

            # Không truyền confirm=true -> luôn chỉ chạy xem trước, không tắt server
            st_dry, res_dry = _http_json(
                f"{base}/api/uninstall/run",
                method="POST",
                body={"remove_config": True, "confirm": False, "dry_run": False},
            )
            self.assertEqual(st_dry, 200)
            self.assertTrue(res_dry["dry_run"])
            self.assertFalse(res_dry["scheduled"])
        finally:
            stop_fn()


if __name__ == "__main__":
    unittest.main()
