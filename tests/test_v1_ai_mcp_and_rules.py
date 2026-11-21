"""Bộ kiểm thử cho Karius Academic System (KAS) v1.0.0 — Quy tắc Đặt tên tùy chỉnh, Chatbot AI, MCP Server & Gói Windows 1-click."""

from __future__ import annotations

import json
import os
import socket
import tempfile
import unittest
import urllib.request
import zipfile
from pathlib import Path
from unittest import mock

from karius_academic_system import __version__
from karius_academic_system import core as sc
from karius_academic_system.ai import (
    AIConfig,
    chat_with_agent,
    execute_agent_tool,
    generate_mcp_client_config,
    handle_mcp_jsonrpc,
    load_ai_config,
    save_ai_config,
)
from karius_academic_system.cli.main import main as kas_cli
from karius_academic_system.ops import auditor
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


class TestKASv1NamingRulesAndAI(unittest.TestCase):
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
                "KAS_AI_PROVIDER",
                "KAS_AI_API_KEY",
            )
        }
        os.environ["KAS_CONFIG_DIR"] = str(self.root / "cfg")
        os.environ["KAS_DATA_DIR"] = str(self.root / "data")
        for k in ("KAS_ROOT_ID", "KAS_ROOT_NAME", "KAS_BACKEND", "KAS_AI_PROVIDER", "KAS_AI_API_KEY"):
            os.environ.pop(k, None)

        self.vault_dir = self.root / "KhoKiemThu"
        (self.vault_dir / "Mon Triet Hoc").mkdir(parents=True)
        (self.vault_dir / "Mon Triet Hoc" / "01_bai_tap_AI.PDF").write_text("Noi dung triet hoc", encoding="utf-8")
        (self.vault_dir / "Mon Triet Hoc" / "Copy of Ghi Chu.txt").write_text("ban sao", encoding="utf-8")
        sc.reload_config()

        # Đăng ký kho bằng cú pháp vị trí mới `kas vault add "<Tên>" "<Đường dẫn>"`
        self.assertEqual(kas_cli(["vault", "add", "Kho Kiểm Thử", str(self.vault_dir)]), 0)
        self.assertEqual(kas_cli(["quet"]), 0)

    def tearDown(self) -> None:
        for k, v in self._env_backup.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        sc.reload_config()
        self._tmp.cleanup()

    def test_custom_naming_rules_presets_cli_and_auditor_enforcement(self):
        self.assertTrue(__version__.startswith("1."), __version__)

        # 1. Preset snake_case_dev chuẩn hóa không dấu + chữ thường + dấu gạch dưới
        p_snake = sc.preview_naming("01_Bài Tập AI.PDF", is_folder=False, rules=sc.preset_rules("snake_case_dev"))
        self.assertEqual(p_snake["suggested"], "01_bai_tap_ai.pdf")
        self.assertFalse(p_snake["compliant"])

        # 2. Preset kebab_web chuẩn hóa gạch ngang
        p_kebab = sc.preview_naming("Tổng Quan Triết Học.MD", is_folder=False, rules=sc.preset_rules("kebab_web"))
        self.assertEqual(p_kebab["suggested"], "tong-quan-triet-hoc.md")

        # 3. Quy tắc tùy biến sâu: kiểu tiền tố thư mục dot_2 + custom_replacements + custom_regex_blacklist
        custom = sc.NamingRuleSet(
            preset="custom",
            folder_require_index_prefix=True,
            folder_index_style="dot_2",
            folder_case="title",
            file_case="title",
            file_separator=" - ",
            file_require_extra_info=False,
            acronyms_upper={"ai": "AI"},
            custom_replacements={"bai tap": "Bài Tập"},
            custom_regex_blacklist=[r"(?i)^copy of"],
        )
        sc.save_naming_rules(custom, scope="vault")
        self.assertTrue(sc.has_custom_naming_rules("vault"))

        p_folder = sc.preview_naming("[1] mon triet hoc", is_folder=True, rules=custom)
        self.assertEqual(p_folder["suggested"], "01. Mon Triet Hoc")

        p_file = sc.preview_naming("01_bai tap_ai.PDF", is_folder=False, rules=custom)
        self.assertEqual(p_file["suggested"], "01 Bài Tập AI.pdf")

        # Kiểm chứng auditor tự áp dụng quy tắc tùy chỉnh của kho (bắt lỗi regex `Copy of` và `THIEU_STT`)
        idx = sc.load_index()
        issues = auditor.audit(idx)
        codes = {i[1] for i in issues}
        self.assertIn("VI_PHAM_REGEX_TUY_CHINH", codes)
        self.assertIn("THIEU_STT", codes)

        plan = auditor.build_fix_plan(idx, None)
        self.assertTrue(any(p["old_name"] == "01_bai_tap_AI.PDF" and p["new_name"].endswith(".pdf") for p in plan))

        # Kiểm chứng CLI `kas rules`
        self.assertEqual(kas_cli(["rules", "presets"]), 0)
        self.assertEqual(kas_cli(["rules", "apply-preset", "kebab_web"]), 0)
        self.assertEqual(kas_cli(["rules", "set", "max_name_length", "90"]), 0)
        loaded_rules, _ = sc.get_active_naming_rules()
        self.assertEqual(loaded_rules.max_name_length, 90)
        self.assertEqual(kas_cli(["rules", "test", "Tài Liệu Học Tập.PDF"]), 0)
        self.assertEqual(kas_cli(["rules", "reset"]), 0)
        self.assertFalse(sc.has_custom_naming_rules("vault"))

    def test_mcp_jsonrpc_server_and_agent_tools(self):
        # 1. Initialize handshake
        init_resp = handle_mcp_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        self.assertEqual(init_resp["result"]["serverInfo"]["version"], __version__)

        # 2. tools/list
        tools_resp = handle_mcp_jsonrpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tool_names = {t["name"] for t in tools_resp["result"]["tools"]}
        self.assertIn("kas_search", tool_names)
        self.assertIn("kas_audit", tool_names)
        self.assertIn("kas_naming_rules_set", tool_names)

        # 3. tools/call -> kas_search
        call_resp = handle_mcp_jsonrpc(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "kas_search", "arguments": {"query": "triet"}},
            }
        )
        self.assertFalse(call_resp["result"]["isError"])
        self.assertGreaterEqual(call_resp["result"]["structuredContent"]["count"], 1)

        # 4. resources/list & resources/read
        res_list = handle_mcp_jsonrpc({"jsonrpc": "2.0", "id": 4, "method": "resources/list"})
        uris = {r["uri"] for r in res_list["result"]["resources"]}
        self.assertIn("kas://vaults", uris)
        res_read = handle_mcp_jsonrpc(
            {"jsonrpc": "2.0", "id": 5, "method": "resources/read", "params": {"uri": "kas://active/naming-rules"}}
        )
        self.assertIn("general_clean", res_read["result"]["contents"][0]["text"])

        # 5. prompts/list & prompts/get
        p_get = handle_mcp_jsonrpc(
            {"jsonrpc": "2.0", "id": 6, "method": "prompts/get", "params": {"name": "kas_audit_advisor"}}
        )
        self.assertIn("kas_audit", p_get["result"]["messages"][0]["content"]["text"])

        # 6. Client config generator
        mcp_cfg = generate_mcp_client_config("claude")
        self.assertIn("karius-academic-system", mcp_cfg["mcpServers"])

    def test_ai_chatbot_offline_and_mocked_openai_tool_calling_loop(self):
        # 1. Trợ lý offline không cần API key
        r1 = chat_with_agent("Liệt kê các kho dữ liệu")
        self.assertTrue(r1["ok"])
        self.assertEqual(r1["tool_calls"][0]["tool"], "kas_list_vaults")
        self.assertIn("Kho Kiểm Thử", r1["reply"])

        r2 = chat_with_agent("Tìm tài liệu triet")
        self.assertEqual(r2["tool_calls"][0]["tool"], "kas_search")

        # 2. Cấu hình masked API key
        save_ai_config(AIConfig(provider="openai_compat", model="gpt-4o-mini", api_key="sk-test-secret-9999"))
        loaded = load_ai_config()
        masked = loaded.masked_dict()
        self.assertTrue(masked["has_api_key"])
        self.assertNotIn("secret", masked["api_key_masked"])

        # 3. Mock vòng lặp tool calling 2 lượt cho OpenAI-compatible provider
        responses = [
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {"name": "kas_vault_stats", "arguments": "{}"},
                                }
                            ],
                        }
                    }
                ]
            },
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "Kho của bạn hiện có 2 tệp tin trong nhánh Mon Triet Hoc.",
                        }
                    }
                ]
            },
        ]
        with mock.patch("karius_academic_system.ai.bridge._http_post_json", side_effect=responses):
            r_llm = chat_with_agent("Thống kê kho giúp tôi", config=loaded)
        self.assertEqual(r_llm["tool_calls"][0]["tool"], "kas_vault_stats")
        self.assertIn("Mon Triet Hoc", r_llm["reply"])

        # 4. Kiểm chứng direct tool execution
        out = execute_agent_tool("kas_preview_rename", {"names": ["01_test.PDF"], "preset": "snake_case_dev"})
        self.assertEqual(out["results"][0]["suggested"], "01_test.pdf")

    def test_web_api_rules_ai_mcp_and_sac_bundle_1click_cmd(self):
        port = _free_port()
        _, stop_fn, engine = start_embedded_server("127.0.0.1", port, prefer_stdlib=True)
        self.assertEqual(engine, "stdlib-http")
        try:
            base = f"http://127.0.0.1:{port}"
            st, rules_data = _http_json(f"{base}/api/rules")
            self.assertEqual(st, 200)
            self.assertIn("academic_v6", rules_data["presets"])

            st_p, prev = _http_json(
                f"{base}/api/rules/preview",
                method="POST",
                body={"name": "01_Tài Liệu Học Tập.PDF", "preset": "kebab_web"},
            )
            self.assertEqual(st_p, 200)
            self.assertEqual(prev["results"][0]["suggested"], "01-tai-lieu-hoc-tap.pdf")

            st_s, saved = _http_json(
                f"{base}/api/rules",
                method="POST",
                body={"scope": "vault", "preset": "snake_case_dev"},
            )
            self.assertEqual(st_s, 200)
            self.assertEqual(saved["rules"]["preset"], "snake_case_dev")

            st_ai, ai_cfg = _http_json(f"{base}/api/ai/config")
            self.assertEqual(st_ai, 200)
            self.assertIn("claude_desktop", ai_cfg["mcp"])

            st_chat, chat_res = _http_json(
                f"{base}/api/ai/chat",
                method="POST",
                body={"message": "Xem quy tắc đặt tên đang áp dụng"},
            )
            self.assertEqual(st_chat, 200)
            self.assertIn("snake_case_dev", chat_res["reply"])

            st_mcp, mcp_res = _http_json(
                f"{base}/api/mcp",
                method="POST",
                body={"jsonrpc": "2.0", "id": 99, "method": "tools/list"},
            )
            self.assertEqual(st_mcp, 200)
            self.assertGreaterEqual(len(mcp_res["result"]["tools"]), 10)
        finally:
            stop_fn()

        # Kiểm chứng toàn bộ script Windows (.ps1/.cmd) là 100% ASCII thuần (tránh lỗi PowerShell 5.1 ANSI/em-dash)
        repo_root = Path(__file__).resolve().parent.parent
        win_dir = repo_root / "packaging" / "windows"
        for script_path in (*win_dir.glob("*.ps1"), *win_dir.glob("*.cmd")):
            raw_bytes = script_path.read_bytes()
            non_ascii = [b for b in raw_bytes if b >= 128]
            self.assertEqual(non_ascii, [], f"{script_path.name} contains non-ASCII bytes that break Windows PowerShell 5.1 / cmd.exe")

        # Kiểm chứng gói Windows SAC-safe ZIP chứa tệp cài 1 nhấp đúp Cai_Dat_KAS_Windows11.cmd với dòng CRLF chuẩn Windows
        import importlib.util

        spec = importlib.util.spec_from_file_location("build_sac_bundle", repo_root / "packaging" / "build_sac_bundle.py")
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        dist_dir = self.root / "fake_dist"
        dist_dir.mkdir()
        (dist_dir / f"karius_academic_system-{__version__}-py3-none-any.whl").write_bytes(b"fake-wheel")
        out_zip = self.root / "kas-windows-sac-safe.zip"
        mod.build_sac_bundle(dist_dir, out_zip)
        with zipfile.ZipFile(out_zip) as zf:
            names = set(zf.namelist())
            self.assertIn("Cai_Dat_KAS_Windows11.cmd", names)
            self.assertIn("install_windows_sac_safe.ps1", names)
            self.assertIn(f"karius_academic_system-{__version__}-py3-none-any.whl", names)
            for win_file in ("Cai_Dat_KAS_Windows11.cmd", "install_windows_sac_safe.ps1", "Chay_Karius_Academic_System.cmd"):
                data = zf.read(win_file)
                self.assertTrue(all(b < 128 for b in data), f"{win_file} in ZIP must be pure ASCII")
                self.assertIn(b"\r\n", data, f"{win_file} in ZIP must use CRLF")
                self.assertNotIn(b"\n", data.replace(b"\r\n", b""), f"{win_file} in ZIP has stray LF without CR")


if __name__ == "__main__":
    unittest.main()
