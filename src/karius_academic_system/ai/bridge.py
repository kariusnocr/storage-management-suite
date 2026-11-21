"""Cầu nối Chatbot AI & Agent đa nhà cung cấp (OpenAI-compatible / Ollama / Gemini / Anthropic / Offline Cục Bộ) thuần Python stdlib."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from karius_academic_system import APP_NAME, __version__
from karius_academic_system import core as sc
from karius_academic_system.ai.tools import execute_agent_tool, get_agent_tool_schemas, get_openai_tools_spec

AI_PROVIDERS: Dict[str, Dict[str, Any]] = {
    "builtin_offline": {
        "name": "Trợ Lý Cục Bộ KAS (Ngoại Tuyến — Không Cần API Key)",
        "default_base_url": "",
        "default_model": "kas-local-agent",
        "requires_api_key": False,
        "description": "Hiểu tiếng Việt tự nhiên để tra cứu, thống kê, kiểm toán, thử quy tắc đặt tên và chuyển kho ngay lập tức hoàn toàn ngoại tuyến.",
    },
    "openai_compat": {
        "name": "OpenAI / Ollama / LM Studio / OpenRouter / Groq / DeepSeek",
        "default_base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
        "requires_api_key": False,
        "description": "Mọi dịch vụ tương thích OpenAI Chat Completions + Function Calling (dùng `http://localhost:11434/v1` cho Ollama miễn phí trên máy).",
    },
    "gemini": {
        "name": "Google Gemini API",
        "default_base_url": "https://generativelanguage.googleapis.com/v1beta",
        "default_model": "gemini-2.5-flash",
        "requires_api_key": True,
        "description": "Kết nối trực tiếp Google Gemini REST API kèm native Tool Calling thao tác kho dữ liệu KAS.",
    },
    "anthropic": {
        "name": "Anthropic Claude API",
        "default_base_url": "https://api.anthropic.com/v1",
        "default_model": "claude-sonnet-4-20250514",
        "requires_api_key": True,
        "description": "Kết nối trực tiếp Anthropic Messages API kèm Tool Use.",
    },
}

DEFAULT_SYSTEM_PROMPT = (
    f"Bạn là trợ lý quản trị tri thức & dữ liệu của {APP_NAME} (KAS v{__version__}). "
    "Hãy trả lời ngắn gọn, chính xác bằng tiếng Việt, chủ động gọi các công cụ KAS để lấy số liệu thật từ kho đang hoạt động "
    "trước khi trả lời. Không bịa tên tệp hay số liệu. Không tự ý sửa đổi/xóa dữ liệu thật của người dùng; "
    "khi đề xuất thao tác ghi, hãy nêu rõ lệnh `kas ...` an toàn để người dùng xác nhận."
)


@dataclass
class AIConfig:
    provider: str = "builtin_offline"
    base_url: str = ""
    model: str = "kas-local-agent"
    api_key: str = ""
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    temperature: float = 0.2
    max_tool_rounds: int = 5

    def masked_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        key = d.get("api_key") or ""
        if len(key) > 8:
            d["api_key_masked"] = f"{key[:4]}***{key[-4:]}"
        elif key:
            d["api_key_masked"] = "***"
        else:
            d["api_key_masked"] = ""
        d["has_api_key"] = bool(key)
        d.pop("api_key", None)
        return d


def ai_config_path() -> Path:
    return sc.user_config_dir() / "ai_config.json"


def load_ai_config() -> AIConfig:
    data: Dict[str, Any] = {}
    p = ai_config_path()
    if p.exists():
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data.update(raw)
        except Exception:
            pass
    # Cho phép ghi đè bằng biến môi trường (ưu tiên bảo mật CI/Server)
    if os.environ.get("KAS_AI_PROVIDER"):
        data["provider"] = os.environ["KAS_AI_PROVIDER"].strip()
    if os.environ.get("KAS_AI_BASE_URL"):
        data["base_url"] = os.environ["KAS_AI_BASE_URL"].strip()
    if os.environ.get("KAS_AI_MODEL"):
        data["model"] = os.environ["KAS_AI_MODEL"].strip()
    if os.environ.get("KAS_AI_API_KEY"):
        data["api_key"] = os.environ["KAS_AI_API_KEY"].strip()

    prov = str(data.get("provider") or "builtin_offline")
    if prov not in AI_PROVIDERS:
        prov = "builtin_offline"
    meta = AI_PROVIDERS[prov]
    return AIConfig(
        provider=prov,
        base_url=str(data.get("base_url") or meta["default_base_url"]).rstrip("/"),
        model=str(data.get("model") or meta["default_model"]),
        api_key=str(data.get("api_key") or ""),
        system_prompt=str(data.get("system_prompt") or DEFAULT_SYSTEM_PROMPT),
        temperature=float(data.get("temperature", 0.2)),
        max_tool_rounds=max(1, min(8, int(data.get("max_tool_rounds", 5)))),
    )


def save_ai_config(cfg: AIConfig) -> Path:
    p = ai_config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(asdict(cfg), ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    tmp.replace(p)
    return p


def _http_post_json(url: str, payload: Dict[str, Any], headers: Dict[str, str], timeout: int = 60) -> Dict[str, Any]:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=raw, headers={"Content-Type": "application/json", **headers}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"HTTP {exc.code} từ AI Provider: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Không kết nối được tới AI Provider ({url}): {exc.reason}") from exc


def _run_builtin_offline_agent(message: str) -> Tuple[str, List[Dict[str, Any]]]:
    """Trợ lý Agent cục bộ thông minh chạy 100% ngoại tuyến không cần API key."""
    msg = message.strip()
    low = sc.strip_accents(msg).lower()
    trace: List[Dict[str, Any]] = []

    def _call(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        out = execute_agent_tool(name, args)
        trace.append({"tool": name, "arguments": args, "result": out})
        return out

    # 1. Thử nghiệm quy tắc đặt tên ("thử tên ...", "kiểm tra tên ...")
    m_test = re.search(r"(?:thu ten|kiem tra ten|chuan hoa ten|test name)\s*[:\"'“”]*\s*(.+)", low)
    if m_test:
        # Lấy đoạn gốc có dấu tương ứng ở cuối câu
        idx = low.find(m_test.group(1))
        sample = msg[idx:].strip(" \"'“”`")
        is_folder = any(k in low for k in ("thu muc", "folder"))
        res = _call("kas_preview_rename", {"names": [sample], "is_folder": is_folder})
        item = res["results"][0]
        issues_txt = "\n".join(f"- `[{i['severity']}] {i['code']}`: {i['description']}" for i in item["issues"]) or "- Không có lỗi (đạt chuẩn 100%)."
        return (
            f"### Kiểm thử quy tắc đặt tên (`preset: {item['preset']}`)\n"
            f"- **Tên gốc:** `{item['original']}`\n"
            f"- **Đề xuất:** `{item['suggested']}`\n"
            f"- **Trạng thái:** {'Đạt chuẩn ✅' if item['compliant'] else 'Cần chỉnh sửa ⚠️'}\n\n"
            f"**Chi tiết:**\n{issues_txt}"
        ), trace

    # 2. Chuyển kho ("chuyển kho <slug>")
    m_sw = re.search(r"(?:chuyen kho|chon kho|doi kho|use vault)\s+([a-z0-9_-]+)", low)
    if m_sw:
        res = _call("kas_switch_vault", {"slug": m_sw.group(1)})
        if res.get("ok"):
            v = res["active_vault"]
            return f"Đã chuyển sang kho **`{v['slug']}`** ({v['name']} · `{v['source_kind']}:{v['root']}`).", trace
        return f"Không thể chuyển kho: {res.get('error')}", trace

    # 3. Liệt kê kho ("danh sách kho", "các kho")
    if any(k in low for k in ("danh sach kho", "cac kho", "liet ke kho", "list vault", "vaults")):
        res = _call("kas_list_vaults", {})
        vaults = res.get("vaults") or []
        if not vaults:
            return (
                "Chưa có kho dữ liệu nào được kết nối.\n"
                "Hãy dùng tab **Kho Dữ Liệu** hoặc chạy lệnh:\n"
                "- `kas vault add \"Tài Liệu\" \"D:\\TaiLieu\"`\n"
                "- `kas vault add \"Kho Drive\" \"https://drive.google.com/drive/folders/<ID>\"`"
            ), trace
        lines = [f"### Danh sách kho đã kết nối ({len(vaults)} kho)\n"]
        for v in vaults:
            mark = " **(Đang chọn)**" if v["slug"] == res.get("active_slug") else ""
            lines.append(f"- `{v['slug']}` — **{v['name']}**{mark} · `{v['source_kind']}` · chế độ `{v.get('mode')}`")
        return "\n".join(lines), trace

    # 4. Quy tắc đặt tên
    if any(k in low for k in ("quy tac", "naming rule", "preset")):
        res = _call("kas_naming_rules_get", {})
        r = res["rules"]
        return (
            f"### Quy tắc đặt tên đang kích hoạt (`{r['preset']}`)\n"
            f"- **Nguồn cấu hình:** `{res['source']}`\n"
            f"- **Thư mục:** tiền tố bắt buộc=`{r['folder_require_index_prefix']}` (`{r['folder_index_style']}`), kiểu chữ=`{r['folder_case']}`\n"
            f"- **Tệp tin:** kiểu chữ=`{r['file_case']}`, phân cách=`{r['file_separator']}`, đuôi chữ thường=`{r['lowercase_extension']}`\n"
            f"- **Tùy chỉnh ngay:** mở tab **Quy Tắc Đặt Tên** hoặc chạy `kas rules presets` / `kas rules apply-preset <tên>`."
        ), trace

    # 5. Kiểm toán / kiểm tra lỗi
    if any(k in low for k in ("kiem toan", "kiem tra loi", "audit", "loi dat ten", "vi pham")):
        res = _call("kas_audit", {"max_issues": 10})
        if not res.get("ok"):
            return f"Chưa thể kiểm toán: {res.get('error')}", trace
        sev = res.get("by_severity") or {}
        top = "\n".join(f"- `{c['code']}`: **{c['count']}**" for c in (res.get("top_codes") or [])[:8]) or "- Không có phát hiện nào 🎉"
        return (
            f"### Kết quả kiểm toán kho `{res['vault']}` (preset `{res['rules_preset']}`)\n"
            f"- **Tổng phát hiện:** `{res['total_findings']}` "
            f"(LỖI: `{sev.get('LỖI', 0)}`, CẢNH BÁO: `{sev.get('CẢNH BÁO', 0)}`, GỢI Ý: `{sev.get('GỢI Ý', 0)}`)\n\n"
            f"**Nhóm mã nổi bật:**\n{top}"
        ), trace

    # 6. Lịch sử hoàn tác
    if any(k in low for k in ("hoan tac", "undo", "lich su")):
        res = _call("kas_undo_list", {"limit": 10})
        batches = res.get("batches") or []
        if not batches:
            return "Hiện chưa có lô thao tác nào trong Sổ cái Hoàn tác của kho này.", trace
        lines = [f"### Sổ cái Hoàn tác ({len(batches)} lô gần nhất)\n"]
        for b in batches:
            lines.append(f"- `{b['batch_id']}` ({b['kind']}) — {b['description']} · `{b['actions_count']}` mục · `{b['status']}`")
        return "\n".join(lines), trace

    # 7. Tìm kiếm ("tìm ...", "search ...")
    m_search = re.search(r"(?:tim kiem|tim tai lieu|tim tep|tim|search|tra cuu)\s+(.+)", low)
    if m_search:
        idx = low.find(m_search.group(1))
        q = msg[idx:].strip(" \"'“”`?!")
        res = _call("kas_search", {"query": q, "limit": 12})
        rows = res.get("results") or []
        if not rows:
            return f"Không tìm thấy mục nào khớp với `{q}` trong chỉ mục hiện tại. (Nếu kho chưa quét, hãy chạy `kas quet`.)", trace
        lines = [f"### Kết quả tìm kiếm `{q}` ({len(rows)} mục đầu)\n"]
        for r in rows:
            icon = "📁" if r.get("is_folder") else "📄"
            lines.append(f"- {icon} **{r['name']}** — `{r['parent_path']}`")
        return "\n".join(lines), trace

    # 8. Thống kê tổng quan (hoặc câu hỏi chung)
    res = _call("kas_vault_stats", {})
    st = res.get("stats") or {}
    v = res.get("vault") or {}
    if st.get("total_items", 0) > 0:
        return (
            f"### Tổng quan kho `{v.get('name') or sc.ROOT_NAME}` (Trợ Lý Cục Bộ KAS)\n"
            f"- **Thư mục:** `{st.get('folders', 0):,}` | **Tệp tin:** `{st.get('files', 0):,}` | **Dung lượng:** `{sc.human_size(int(st.get('total_bytes', 0)))}`\n\n"
            "Bạn có thể hỏi trực tiếp bằng tiếng Việt như:\n"
            "- *\"Tìm tài liệu triết học\"*\n"
            "- *\"Kiểm tra lỗi đặt tên trong kho\"*\n"
            "- *\"Thử tên 01_bai_tap_cuoi_ky.PDF\"*\n"
            "- *\"Liệt kê các kho dữ liệu\"* hoặc *\"Xem quy tắc đặt tên\"*\n\n"
            "> Mẹo: Bạn có thể kết nối **Gemini / OpenAI / Ollama (local) / Claude** ngay ở mục **Cấu hình AI Provider** phía trên hoặc kết nối **Claude Desktop / Cursor / Antigravity** qua giao thức **MCP**."
        ), trace

    return (
        f"Xin chào! Tôi là **Trợ Lý Cục Bộ {APP_NAME} (KAS v{__version__})**.\n"
        "Kho hiện tại chưa có chỉ mục (hoặc chưa chọn kho). Bạn có thể hỏi:\n"
        "- *\"Liệt kê các kho dữ liệu\"*\n"
        "- *\"Xem quy tắc đặt tên\"*\n"
        "- *\"Thử tên 01_tai_lieu_hoc_tap.PDF\"*\n"
        "Hoặc thiết lập LLM ngoài (**Ollama / Gemini / OpenAI / Claude**) để trò chuyện tự do với đầy đủ Tool Calling!"
    ), trace


def _chat_openai_compat(cfg: AIConfig, messages: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]]]:
    url = f"{cfg.base_url or AI_PROVIDERS['openai_compat']['default_base_url']}/chat/completions"
    headers = {"Authorization": f"Bearer {cfg.api_key}"} if cfg.api_key else {}
    conv: List[Dict[str, Any]] = [{"role": "system", "content": cfg.system_prompt}]
    for m in messages:
        role = m.get("role")
        if role in {"user", "assistant"}:
            conv.append({"role": role, "content": str(m.get("content") or "")})

    tools = get_openai_tools_spec()
    trace: List[Dict[str, Any]] = []
    for _ in range(cfg.max_tool_rounds):
        resp = _http_post_json(
            url,
            {
                "model": cfg.model,
                "messages": conv,
                "tools": tools,
                "tool_choice": "auto",
                "temperature": cfg.temperature,
            },
            headers,
        )
        choice = (resp.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            return str(msg.get("content") or "(Không có nội dung phản hồi)"), trace
        conv.append(msg)
        for tc in tool_calls:
            fn_info = tc.get("function") or {}
            t_name = str(fn_info.get("name") or "")
            raw_args = fn_info.get("arguments") or "{}"
            try:
                t_args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
            except Exception:
                t_args = {}
            out = execute_agent_tool(t_name, t_args)
            trace.append({"tool": t_name, "arguments": t_args, "result": out})
            conv.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.get("id", t_name),
                    "name": t_name,
                    "content": json.dumps(out, ensure_ascii=False),
                }
            )
    return "Đã đạt giới hạn vòng gọi công cụ AI.", trace


def _chat_gemini(cfg: AIConfig, messages: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]]]:
    if not cfg.api_key:
        raise RuntimeError("Thiếu API Key cho Google Gemini (cấu hình trong tab Trợ Lý AI hoặc biến `KAS_AI_API_KEY`).")
    base = cfg.base_url or AI_PROVIDERS["gemini"]["default_base_url"]
    url = f"{base}/models/{cfg.model}:generateContent?key={cfg.api_key}"
    contents: List[Dict[str, Any]] = []
    for m in messages:
        role = "model" if m.get("role") == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": str(m.get("content") or "")}]})

    func_decls = [
        {
            "name": t["name"],
            "description": t["description"],
            "parameters": t["inputSchema"],
        }
        for t in get_agent_tool_schemas()
    ]
    trace: List[Dict[str, Any]] = []
    for _ in range(cfg.max_tool_rounds):
        resp = _http_post_json(
            url,
            {
                "systemInstruction": {"parts": [{"text": cfg.system_prompt}]},
                "contents": contents,
                "tools": [{"functionDeclarations": func_decls}],
                "generationConfig": {"temperature": cfg.temperature},
            },
            headers={},
        )
        cand = (resp.get("candidates") or [{}])[0]
        content = cand.get("content") or {}
        parts = content.get("parts") or []
        fcalls = [p["functionCall"] for p in parts if isinstance(p, dict) and "functionCall" in p]
        if not fcalls:
            texts = [str(p.get("text") or "") for p in parts if isinstance(p, dict) and "text" in p]
            return "\n".join(t for t in texts if t).strip() or "(Không có nội dung phản hồi)", trace
        contents.append({"role": "model", "parts": parts})
        resp_parts = []
        for fc in fcalls:
            t_name = str(fc.get("name") or "")
            t_args = fc.get("args") if isinstance(fc.get("args"), dict) else {}
            out = execute_agent_tool(t_name, t_args)
            trace.append({"tool": t_name, "arguments": t_args, "result": out})
            resp_parts.append({"functionResponse": {"name": t_name, "response": {"result": out}}})
        contents.append({"role": "user", "parts": resp_parts})
    return "Đã đạt giới hạn vòng gọi công cụ Gemini.", trace


def _chat_anthropic(cfg: AIConfig, messages: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]]]:
    if not cfg.api_key:
        raise RuntimeError("Thiếu API Key cho Anthropic Claude (cấu hình trong tab Trợ Lý AI hoặc biến `KAS_AI_API_KEY`).")
    base = cfg.base_url or AI_PROVIDERS["anthropic"]["default_base_url"]
    url = f"{base}/messages"
    headers = {"x-api-key": cfg.api_key, "anthropic-version": "2023-06-01"}
    conv: List[Dict[str, Any]] = [
        {"role": "assistant" if m.get("role") == "assistant" else "user", "content": str(m.get("content") or "")}
        for m in messages
    ]
    tools = [
        {"name": t["name"], "description": t["description"], "input_schema": t["inputSchema"]}
        for t in get_agent_tool_schemas()
    ]
    trace: List[Dict[str, Any]] = []
    for _ in range(cfg.max_tool_rounds):
        resp = _http_post_json(
            url,
            {
                "model": cfg.model,
                "max_tokens": 2048,
                "system": cfg.system_prompt,
                "tools": tools,
                "messages": conv,
                "temperature": cfg.temperature,
            },
            headers,
        )
        blocks = resp.get("content") or []
        tool_uses = [b for b in blocks if isinstance(b, dict) and b.get("type") == "tool_use"]
        if not tool_uses:
            texts = [str(b.get("text") or "") for b in blocks if isinstance(b, dict) and b.get("type") == "text"]
            return "\n".join(t for t in texts if t).strip() or "(Không có nội dung phản hồi)", trace
        conv.append({"role": "assistant", "content": blocks})
        res_blocks = []
        for tu in tool_uses:
            t_name = str(tu.get("name") or "")
            t_args = tu.get("input") if isinstance(tu.get("input"), dict) else {}
            out = execute_agent_tool(t_name, t_args)
            trace.append({"tool": t_name, "arguments": t_args, "result": out})
            res_blocks.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tu.get("id", t_name),
                    "content": json.dumps(out, ensure_ascii=False),
                }
            )
        conv.append({"role": "user", "content": res_blocks})
    return "Đã đạt giới hạn vòng gọi công cụ Claude.", trace


def chat_with_agent(
    message: str,
    *,
    history: Optional[List[Dict[str, Any]]] = None,
    config: Optional[AIConfig] = None,
) -> Dict[str, Any]:
    """Gửi câu hỏi tới AI Chatbot/Agent được cấu hình (tự động thực thi Tool Calling trên kho KAS hiện hành)."""
    cfg = config or load_ai_config()
    msgs = list(history or [])
    msgs.append({"role": "user", "content": message})

    if cfg.provider == "builtin_offline":
        reply, trace = _run_builtin_offline_agent(message)
    elif cfg.provider == "openai_compat":
        reply, trace = _chat_openai_compat(cfg, msgs)
    elif cfg.provider == "gemini":
        reply, trace = _chat_gemini(cfg, msgs)
    elif cfg.provider == "anthropic":
        reply, trace = _chat_anthropic(cfg, msgs)
    else:
        reply, trace = _run_builtin_offline_agent(message)

    return {
        "ok": True,
        "provider": cfg.provider,
        "model": cfg.model,
        "reply": reply,
        "tool_calls": trace,
    }


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Trợ lý Chatbot AI & Agent tích hợp trong Karius Academic System (KAS).")
    sub = ap.add_subparsers(dest="sub", required=True)
    sub.add_parser("status", help="Xem cấu hình AI Provider hiện tại")
    p_cfg = sub.add_parser("config", help="Cấu hình nhà cung cấp AI (builtin_offline | openai_compat | gemini | anthropic)")
    p_cfg.add_argument("--provider", choices=list(AI_PROVIDERS))
    p_cfg.add_argument("--model")
    p_cfg.add_argument("--base-url")
    p_cfg.add_argument("--api-key")
    p_cfg.add_argument("--clear-key", action="store_true", help="Xóa API key đã lưu")
    p_ask = sub.add_parser("ask", help="Hỏi 1 câu trực tiếp với AI Agent trên kho hiện tại")
    p_ask.add_argument("question", nargs="+")
    sub.add_parser("chat", help="Mở phiên trò chuyện tương tác với KAS AI Agent trong terminal")
    args = ap.parse_args(argv)

    if args.sub == "status":
        cfg = load_ai_config()
        print(json.dumps({"config_path": str(ai_config_path()), "config": cfg.masked_dict(), "providers": AI_PROVIDERS}, ensure_ascii=False, indent=2))
        return 0
    if args.sub == "config":
        cfg = load_ai_config()
        if args.provider:
            cfg.provider = args.provider
            if not args.base_url:
                cfg.base_url = AI_PROVIDERS[args.provider]["default_base_url"]
            if not args.model:
                cfg.model = AI_PROVIDERS[args.provider]["default_model"]
        if args.base_url is not None:
            cfg.base_url = args.base_url.rstrip("/")
        if args.model is not None:
            cfg.model = args.model
        if args.clear_key:
            cfg.api_key = ""
        elif args.api_key is not None:
            cfg.api_key = args.api_key
        saved = save_ai_config(cfg)
        sc.log(f"Đã lưu cấu hình AI tại {saved}: provider={cfg.provider} | model={cfg.model}")
        return 0
    if args.sub == "ask":
        q = " ".join(args.question).strip()
        res = chat_with_agent(q)
        if res["tool_calls"]:
            sc.log(f"[AI Agent đã gọi {len(res['tool_calls'])} công cụ: {', '.join(t['tool'] for t in res['tool_calls'])}]")
        print(res["reply"])
        return 0
    if args.sub == "chat":
        cfg = load_ai_config()
        sc.log(f"=== {APP_NAME} AI Agent ({cfg.provider} / {cfg.model}) — gõ 'exit' để thoát ===")
        hist: List[Dict[str, Any]] = []
        while True:
            try:
                user_in = input("\nBạn > ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not user_in or user_in.lower() in {"exit", "quit", "thoat"}:
                break
            res = chat_with_agent(user_in, history=hist, config=cfg)
            if res["tool_calls"]:
                sc.log(f"  [Tools: {', '.join(t['tool'] for t in res['tool_calls'])}]")
            print(f"\nKAS AI > {res['reply']}")
            hist.append({"role": "user", "content": user_in})
            hist.append({"role": "assistant", "content": res["reply"]})
        return 0
    return 0
