"""Máy chủ Model Context Protocol (MCP — JSON-RPC 2.0) thuần Python cho Karius Academic System (KAS).

Hỗ trợ kết nối trực tiếp KAS với Claude Desktop, Cursor, Windsurf, Antigravity, VS Code Copilot
và mọi AI Agent chuẩn MCP thông qua `kas mcp serve` (stdio) hoặc HTTP `POST /api/mcp`.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, List, Optional

from karius_academic_system import APP_NAME, __version__
from karius_academic_system import core as sc
from karius_academic_system.ai.tools import execute_agent_tool, get_agent_tool_schemas
from karius_academic_system.core.naming_rules import get_active_naming_rules

MCP_PROTOCOL_VERSION = "2024-11-05"


def _mcp_resources() -> List[Dict[str, Any]]:
    return [
        {
            "uri": "kas://vaults",
            "name": "Danh sách kho dữ liệu KAS",
            "description": "Sổ đăng ký các kho cục bộ và Google Drive đang kết nối trong KAS.",
            "mimeType": "application/json",
        },
        {
            "uri": "kas://active/stats",
            "name": "Thống kê kho đang hoạt động",
            "description": "Tổng thư mục, tệp tin, dung lượng và phân bố định dạng của kho hiện tại.",
            "mimeType": "application/json",
        },
        {
            "uri": "kas://active/naming-rules",
            "name": "Quy tắc đặt tên đang áp dụng",
            "description": "Bộ quy tắc đặt tên tùy chỉnh hoặc preset đang áp dụng cho kho hiện hành.",
            "mimeType": "application/json",
        },
    ]


def _read_mcp_resource(uri: str) -> Dict[str, Any]:
    if uri == "kas://vaults":
        payload = execute_agent_tool("kas_list_vaults", {})
    elif uri == "kas://active/stats":
        payload = execute_agent_tool("kas_vault_stats", {})
    elif uri == "kas://active/naming-rules":
        rules, source = get_active_naming_rules()
        payload = {"source": source, "rules": rules.to_dict()}
    else:
        raise KeyError(f"Không tìm thấy tài nguyên MCP: {uri}")
    return {
        "contents": [
            {
                "uri": uri,
                "mimeType": "application/json",
                "text": json.dumps(payload, ensure_ascii=False, indent=2),
            }
        ]
    }


def _mcp_prompts() -> List[Dict[str, Any]]:
    return [
        {
            "name": "kas_audit_advisor",
            "description": "Kiểm toán toàn kho đang hoạt động và đề xuất kế hoạch chuẩn hóa tên an toàn theo quy tắc hiện hành.",
            "arguments": [
                {"name": "branch", "description": "Tùy chọn nhánh thư mục cần tập trung", "required": False},
            ],
        },
        {
            "name": "kas_organize_vault",
            "description": "Phân tích cấu trúc, dung lượng và gợi ý sắp xếp/chọn preset quy tắc đặt tên tối ưu cho kho hiện hành.",
            "arguments": [],
        },
    ]


def _get_mcp_prompt(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    if name == "kas_audit_advisor":
        branch = str(arguments.get("branch") or "").strip()
        scope_txt = f"trên nhánh `{branch}`" if branch else "trên toàn bộ kho đang hoạt động"
        return {
            "description": "Tư vấn kiểm toán & chuẩn hóa tên KAS",
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": (
                            f"Hãy dùng công cụ `kas_vault_stats`, `kas_naming_rules_get` và `kas_audit` "
                            f"để kiểm tra chất lượng đặt tên {scope_txt}, tổng hợp các nhóm lỗi chính "
                            f"và đề xuất lộ trình chuẩn hóa an toàn (kèm lệnh CLI `kas` tương ứng)."
                        ),
                    },
                }
            ],
        }
    if name == "kas_organize_vault":
        return {
            "description": "Phân tích & gợi ý tối ưu tổ chức kho KAS",
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": (
                            "Hãy gọi `kas_list_vaults`, `kas_vault_stats` và `kas_list_folder` ở thư mục gốc "
                            "để đánh giá cấu trúc kho hiện tại, nhận xét điểm mạnh/điểm cần cải thiện "
                            "và gợi ý bộ quy tắc đặt tên (`academic_v6`, `general_clean`, `snake_case_dev`, `kebab_web`) phù hợp nhất."
                        ),
                    },
                }
            ],
        }
    raise KeyError(f"Không tìm thấy prompt MCP: {name}")


def _rpc_error(req_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def handle_mcp_jsonrpc(request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Xử lý 1 thông điệp JSON-RPC 2.0 chuẩn MCP (trả `None` cho notification không cần phản hồi)."""
    if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
        return _rpc_error(None, -32600, "Invalid Request: expected JSON-RPC 2.0 object")

    method = str(request.get("method") or "")
    params = request.get("params") if isinstance(request.get("params"), dict) else {}
    req_id = request.get("id")
    is_notification = "id" not in request

    try:
        if method == "initialize":
            result: Dict[str, Any] = {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"subscribe": False, "listChanged": False},
                    "prompts": {"listChanged": False},
                },
                "serverInfo": {
                    "name": "karius-academic-system",
                    "title": APP_NAME,
                    "version": __version__,
                },
            }
        elif method in {"notifications/initialized", "notifications/cancelled"}:
            return None
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": get_agent_tool_schemas()}
        elif method == "tools/call":
            t_name = str(params.get("name") or "")
            t_args = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
            out = execute_agent_tool(t_name, t_args)
            is_err = isinstance(out, dict) and out.get("ok") is False
            result = {
                "content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False, indent=2)}],
                "structuredContent": out,
                "isError": is_err,
            }
        elif method == "resources/list":
            result = {"resources": _mcp_resources()}
        elif method == "resources/read":
            uri = str(params.get("uri") or "")
            result = _read_mcp_resource(uri)
        elif method == "prompts/list":
            result = {"prompts": _mcp_prompts()}
        elif method == "prompts/get":
            p_name = str(params.get("name") or "")
            p_args = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
            result = _get_mcp_prompt(p_name, p_args)
        else:
            if is_notification:
                return None
            return _rpc_error(req_id, -32601, f"Method not found: {method}")
    except KeyError as exc:
        if is_notification:
            return None
        return _rpc_error(req_id, -32602, str(exc))
    except Exception as exc:
        if is_notification:
            return None
        return _rpc_error(req_id, -32603, f"Internal error: {exc}")

    if is_notification:
        return None
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def generate_mcp_client_config(client: str = "generic", http_port: int = 8765) -> Dict[str, Any]:
    """Sinh đoạn cấu hình JSON sẵn sàng dán vào Claude Desktop, Cursor, Windsurf, Antigravity hoặc client MCP bất kỳ."""
    py_exe = sys.executable or "python3"
    stdio_entry = {
        "command": py_exe,
        "args": ["-m", "karius_academic_system", "mcp", "serve"],
        "env": {"PYTHONUTF8": "1"},
    }
    if client == "http":
        return {
            "mcpServers": {
                "karius-academic-system": {
                    "url": f"http://127.0.0.1:{http_port}/api/mcp",
                    "transport": "http",
                }
            }
        }
    return {"mcpServers": {"karius-academic-system": stdio_entry}}


def serve_mcp_stdio() -> int:
    """Chạy máy chủ MCP JSON-RPC 2.0 qua `stdin`/`stdout` (hỗ trợ cả NDJSON và Content-Length LSP framing)."""
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer

    def _write_msg(msg: Dict[str, Any], framed: bool) -> None:
        raw = json.dumps(msg, ensure_ascii=False).encode("utf-8")
        if framed:
            header = f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii")
            stdout.write(header + raw)
        else:
            stdout.write(raw + b"\n")
        stdout.flush()

    while True:
        line = stdin.readline()
        if not line:
            break
        stripped = line.strip()
        if not stripped:
            continue

        framed = False
        if stripped.lower().startswith(b"content-length:"):
            framed = True
            try:
                length = int(stripped.split(b":", 1)[1].strip())
            except ValueError:
                continue
            while True:
                hdr = stdin.readline()
                if not hdr or hdr in (b"\r\n", b"\n"):
                    break
            body = stdin.read(length)
        else:
            body = stripped

        try:
            req = json.loads(body.decode("utf-8"))
        except Exception as exc:
            _write_msg(_rpc_error(None, -32700, f"Parse error: {exc}"), framed=framed)
            continue

        resp = handle_mcp_jsonrpc(req)
        if resp is not None:
            _write_msg(resp, framed=framed)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Máy chủ MCP (Model Context Protocol) cho Karius Academic System (KAS).")
    sub = ap.add_subparsers(dest="sub", required=True)
    sub.add_parser("serve", help="Khởi động MCP Server (JSON-RPC 2.0 qua stdio)")
    p_cfg = sub.add_parser("config", help="In cấu hình JSON kết nối Claude Desktop / Cursor / Antigravity / AI Agent")
    p_cfg.add_argument("--client", choices=["generic", "claude", "cursor", "antigravity", "http"], default="generic")
    p_cfg.add_argument("--port", type=int, default=8765)
    sub.add_parser("tools", help="Liệt kê các công cụ MCP mà KAS cung cấp cho Agent")
    args = ap.parse_args(argv)

    if args.sub == "serve":
        return serve_mcp_stdio()
    if args.sub == "config":
        print(json.dumps(generate_mcp_client_config(client=args.client, http_port=args.port), ensure_ascii=False, indent=2))
        return 0
    if args.sub == "tools":
        for t in get_agent_tool_schemas():
            sc.log(f"• {t['name']:24s} — {t['description']}")
        return 0
    return 0
