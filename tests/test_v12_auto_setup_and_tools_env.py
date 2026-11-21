"""Bộ kiểm thử chuyên sâu cho Karius Academic System (KAS) v1.2.0:
- Tự động phát hiện công cụ & làm mới PATH (`core/tools_env.py`)
- Tự động cài đặt thư viện Python, công cụ CLI (`gh`, `git`, `7z`, `ffmpeg`, `tesseract`, `poppler`) & tải dữ liệu OCR Tiếng Việt (`vie+eng`)
- Khả năng chống lỗi Windows Smart App Control (`OSError`) trong `kas doctor`
- Thông báo rõ ràng cho `CLI gdrive` (không cần khi đang dùng Drive API OAuth) & nhận diện GitHub PAT trong `kas doctor`
- Endpoint HTTP `/api/setup/plan`, `/api/setup/run`, `/api/setup/jobs/{id}` trên máy chủ `--stdlib`.
"""

from __future__ import annotations

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
from karius_academic_system.ops import doctor, setup_tools
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


class _FakeBinaryResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "_FakeBinaryResponse":
        return self

    def __exit__(self, *args) -> None:
        return None


class TestKASv12AutoSetupAndDoctor(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._env_backup = {
            k: os.environ.get(k)
            for k in ("KAS_CONFIG_DIR", "KAS_DATA_DIR", "KAS_TESSDATA_DIR", "KAS_BACKEND")
        }
        os.environ["KAS_CONFIG_DIR"] = str(self.root / "cfg")
        os.environ["KAS_DATA_DIR"] = str(self.root / "data")
        os.environ["KAS_TESSDATA_DIR"] = str(self.root / "tessdata")
        os.environ.pop("KAS_BACKEND", None)
        sc.reload_config()

    def tearDown(self) -> None:
        for k, v in self._env_backup.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        sc.reload_config()
        sc.reset_ocr_cache()
        self._tmp.cleanup()

    def test_download_ocr_traineddata_and_shared_tessdata_dir(self) -> None:
        self.assertEqual(__version__, "1.2.0")
        td = sc.shared_tessdata_dir()
        self.assertEqual(td, self.root / "tessdata")

        fake_bytes = b"TESSDATA_FAST_HEADER" + (b"\x00" * 150_000)
        with mock.patch("urllib.request.urlopen", return_value=_FakeBinaryResponse(fake_bytes)):
            res = setup_tools.download_ocr_traineddata(("vie", "eng"))
        self.assertTrue(res["ok"])
        self.assertEqual(len(res["downloaded"]), 2)
        self.assertTrue((td / "vie.traineddata").exists())
        self.assertTrue((td / "eng.traineddata").exists())

        # Lần gọi thứ 2 phải bỏ qua vì đã tồn tại đủ dung lượng
        res2 = setup_tools.download_ocr_traineddata(("vie", "eng"))
        self.assertTrue(res2["ok"])
        self.assertEqual(len(res2["skipped"]), 2)
        self.assertEqual(len(res2["downloaded"]), 0)

    def test_smart_app_control_oserror_handled_safely_in_probe_and_doctor(self) -> None:
        real_import = setup_tools.importlib.import_module

        def _fake_import(name: str):
            if name == "PIL":
                raise OSError("[WinError 4551] An Application Control policy has blocked this file")
            return real_import(name)

        with mock.patch.object(setup_tools.importlib, "import_module", side_effect=_fake_import):
            ok, reason, blocked = setup_tools.probe_python_package("PIL")
            self.assertFalse(ok)
            self.assertTrue(blocked)
            self.assertIn("Smart App Control", reason)

            doc = doctor.run_doctor()
            pil_entry = next(p for p in doc["python_packages"] if p["name"] == "Pillow")
            self.assertFalse(pil_entry["ok"])
            self.assertTrue(pil_entry["blocked_by_sac"])
            report = doctor.format_doctor_report(doc)
            self.assertIn("bị SAC chặn", report)

    def test_doctor_clarifies_gdrive_cli_when_oauth_active_and_recognizes_github_pat(self) -> None:
        sc.connect_github_token("ghp_demo_token_for_doctor_check", verify=False)
        fake_res = doctor.run_doctor()
        fake_res["drive"]["cli"]["available"] = False
        fake_res["drive"]["api"]["libs_installed"] = True
        fake_res["drive"]["api"]["authenticated"] = True
        fake_res["github"]["available"] = False
        fake_res["github"]["cli_authenticated"] = False
        fake_res["github"]["pat_connected"] = True
        fake_res["github"]["pat_login"] = "kariusnocr"

        report = doctor.format_doctor_report(fake_res)
        self.assertIn("Không cần (đang dùng Drive API OAuth trực tiếp trên máy cá nhân)", report)
        self.assertIn("Đã kết nối qua PAT (@kariusnocr)", report)
        self.assertTrue(any(t["name"] == "gh" for t in fake_res["cli_tools"]))

    def test_cli_setup_dry_run_and_stdlib_http_setup_endpoints(self) -> None:
        self.assertEqual(kas_cli(["setup", "--chay-thu"]), 0)

        port = _free_port()
        _, stop_fn, engine = start_embedded_server(host="127.0.0.1", port=port, prefer_stdlib=True)
        self.assertEqual(engine, "stdlib-http")
        base = f"http://127.0.0.1:{port}"
        try:
            st, plan = _http_json(f"{base}/api/setup/plan")
            self.assertEqual(st, 200)
            self.assertIn("missing_python", plan)
            self.assertIn("missing_tools", plan)
            self.assertIn("missing_ocr_files", plan)

            st_run, job = _http_json(f"{base}/api/setup/run", method="POST", body={"scope": "all", "dry_run": True})
            self.assertEqual(st_run, 200)
            jid = job["id"]
            cur = job
            for _ in range(40):
                st_poll, cur = _http_json(f"{base}/api/setup/jobs/{jid}")
                self.assertEqual(st_poll, 200)
                if cur["status"] != "running":
                    break
                time.sleep(0.05)
            self.assertIn(cur["status"], {"done", "done_with_warnings"})
            self.assertTrue(any("HOÀN TẤT" in ln for ln in cur["logs"]))
        finally:
            stop_fn()


if __name__ == "__main__":
    unittest.main()
