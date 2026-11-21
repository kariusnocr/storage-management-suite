"""Danh mục công cụ Agent chuẩn hóa JSON Schema cho Karius Academic System (KAS) — dùng chung bởi MCP Server, Chatbot AI & HTTP API."""

from __future__ import annotations

from collections import Counter
from typing import Any, Callable, Dict, List

from karius_academic_system import APP_NAME, __version__
from karius_academic_system import core as sc
from karius_academic_system.core.naming_rules import (
    NAMING_PRESETS,
    NamingRuleSet,
    apply_naming_preset,
    get_active_naming_rules,
    preview_naming,
    save_naming_rules,
)


def _tool_list_vaults(args: Dict[str, Any]) -> Dict[str, Any]:
    reg = sc.get_vault_registry()
    act = sc.active_vault()
    return {
        "app": f"{APP_NAME} v{__version__}",
        "active_slug": act.slug if act else reg.active_slug,
        "registry_path": str(reg.path),
        "vaults": [v.to_dict() for v in reg.list_vaults()],
    }


def _tool_switch_vault(args: Dict[str, Any]) -> Dict[str, Any]:
    slug = str(args.get("slug") or "").strip()
    if not slug:
        return {"ok": False, "error": "Thiếu tham số `slug` của kho cần chuyển."}
    try:
        vc = sc.activate_vault(slug, persist=bool(args.get("persist", True)))
        return {"ok": True, "active_vault": vc.to_dict()}
    except KeyError as exc:
        return {"ok": False, "error": str(exc)}


def _tool_vault_stats(args: Dict[str, Any]) -> Dict[str, Any]:
    vc = sc.active_vault()
    with sc.StorageDB() as db:
        st = db.stats_summary()
    return {
        "vault": vc.to_dict() if vc else {"name": sc.ROOT_NAME, "root": sc.ROOT_ID, "mode": sc.effective_vault_mode()},
        "stats": st,
    }


def _tool_search(args: Dict[str, Any]) -> Dict[str, Any]:
    query = str(args.get("query") or "").strip()
    limit = max(1, min(100, int(args.get("limit") or 20)))
    if not query:
        return {"query": "", "count": 0, "results": []}
    with sc.StorageDB() as db:
        rows = db.search_fts(query, limit=limit)
    return {"query": query, "count": len(rows), "results": rows}


def _tool_list_folder(args: Dict[str, Any]) -> Dict[str, Any]:
    req_path = str(args.get("path") or "").strip()
    limit = max(1, min(200, int(args.get("limit") or 60)))
    index = sc.load_index(required=False)
    if not index:
        return {"ok": False, "error": "Chưa có chỉ mục kho. Hãy chạy `kas quet` trước."}
    target = req_path or sc.ROOT_NAME
    if target not in index and sc.ROOT_NAME and f"{sc.ROOT_NAME}/{target.lstrip('/')}" in index:
        target = f"{sc.ROOT_NAME}/{target.lstrip('/')}"
    if target not in index:
        # Tìm gần đúng theo tiền tố/tên
        low = target.lower()
        matches = [p for p in sorted(index) if low in p.lower()][:20]
        return {"ok": False, "error": f"Không thấy thư mục `{target}` trong chỉ mục.", "suggestions": matches}
    data = index[target]
    items = data.get("items", [])[:limit]
    return {
        "ok": True,
        "path": target,
        "total_items": len(data.get("items", [])),
        "shown": len(items),
        "items": [
            {
                "name": it.get("name"),
                "id": it.get("id"),
                "is_folder": it.get("mimeType") == sc.FOLDER_MIME,
                "size": int(it.get("size") or 0),
                "modifiedTime": it.get("modifiedTime", ""),
            }
            for it in items
        ],
    }


def _tool_audit(args: Dict[str, Any]) -> Dict[str, Any]:
    from karius_academic_system.ops import auditor

    index = sc.load_index(required=False)
    if not index:
        return {"ok": False, "error": "Chưa có chỉ mục kho để kiểm toán. Hãy chạy `kas quet` trước."}
    branch = sc.normalize_branch(str(args.get("branch") or "").strip() or None)
    max_issues = max(1, min(100, int(args.get("max_issues") or 30)))
    issues = auditor.audit(index, branch=branch, check_structure=True)
    by_sev = Counter(i[0] for i in issues)
    by_code = Counter(i[1] for i in issues)
    rules, source = get_active_naming_rules()
    return {
        "ok": True,
        "vault": sc.ROOT_NAME,
        "rules_preset": rules.preset,
        "rules_source": source,
        "total_findings": len(issues),
        "by_severity": dict(by_sev),
        "top_codes": [{"code": c, "count": n} for c, n in by_code.most_common(15)],
        "sample_issues": [
            {
                "severity": i[0],
                "code": i[1],
                "path": i[2],
                "name": i[3],
                "kind": i[5],
                "description": i[6],
                "suggestion": i[7],
            }
            for i in issues[:max_issues]
        ],
        "safe_next_command": "kas kiem-tra --sua-an-toan --thuc-thi" if issues else "",
    }


def _tool_preview_rename(args: Dict[str, Any]) -> Dict[str, Any]:
    raw_names = args.get("names")
    if isinstance(raw_names, str):
        names = [raw_names]
    elif isinstance(raw_names, list):
        names = [str(x) for x in raw_names if str(x).strip()]
    else:
        single = str(args.get("name") or "").strip()
        names = [single] if single else []
    is_folder = bool(args.get("is_folder", False))
    preset = str(args.get("preset") or "").strip()
    if preset and preset in NAMING_PRESETS:
        rules = NamingRuleSet.from_dict(NAMING_PRESETS[preset]["rules"])
    else:
        rules, _ = get_active_naming_rules()
    return {
        "preset": rules.preset,
        "results": [preview_naming(nm, is_folder=is_folder, rules=rules) for nm in names[:50]],
    }


def _tool_naming_rules_get(args: Dict[str, Any]) -> Dict[str, Any]:
    rules, source = get_active_naming_rules()
    return {
        "source": source,
        "rules": rules.to_dict(),
        "available_presets": {
            k: {"name": v["name"], "description": v["description"]} for k, v in NAMING_PRESETS.items()
        },
    }


def _tool_naming_rules_set(args: Dict[str, Any]) -> Dict[str, Any]:
    scope = "global" if str(args.get("scope") or "vault").strip().lower() == "global" else "vault"
    preset = str(args.get("preset") or "").strip()
    updates = args.get("updates")
    if preset and not updates:
        if preset not in NAMING_PRESETS:
            return {"ok": False, "error": f"Preset không hợp lệ: `{preset}`. Hợp lệ: {', '.join(NAMING_PRESETS)}"}
        rules, path = apply_naming_preset(preset, scope=scope)
        return {"ok": True, "scope": scope, "saved_path": str(path), "rules": rules.to_dict()}
    cur, _ = get_active_naming_rules()
    data = cur.to_dict()
    if preset and preset in NAMING_PRESETS:
        data.update(NAMING_PRESETS[preset]["rules"])
    if isinstance(updates, dict):
        data.update(updates)
        if "preset" not in updates and not preset:
            data["preset"] = "custom"
    new_rules = NamingRuleSet.from_dict(data)
    saved = save_naming_rules(new_rules, scope=scope)
    return {"ok": True, "scope": scope, "saved_path": str(saved), "rules": new_rules.to_dict()}


def _tool_undo_list(args: Dict[str, Any]) -> Dict[str, Any]:
    limit = max(1, min(50, int(args.get("limit") or 15)))
    with sc.StorageDB() as db:
        batches = db.list_undo_batches(limit=limit)
    return {"count": len(batches), "batches": batches}


_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "kas_list_vaults",
        "description": "Liệt kê toàn bộ các kho dữ liệu (Local Folder và Google Drive) đã kết nối với Karius Academic System (KAS) cùng kho đang kích hoạt.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "handler": _tool_list_vaults,
    },
    {
        "name": "kas_switch_vault",
        "description": "Chuyển đổi kho dữ liệu đang hoạt động trong KAS sang mã kho `slug` được chỉ định.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "Mã slug của kho (lấy từ kas_list_vaults)"},
                "persist": {"type": "boolean", "description": "Lưu làm kho mặc định trong vaults.toml", "default": True},
            },
            "required": ["slug"],
        },
        "handler": _tool_switch_vault,
    },
    {
        "name": "kas_vault_stats",
        "description": "Lấy thống kê tổng quan kho đang hoạt động (tổng thư mục, tổng tệp, dung lượng, phân bố loại định dạng, thời điểm quét gần nhất).",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "handler": _tool_vault_stats,
    },
    {
        "name": "kas_search",
        "description": "Tìm kiếm toàn văn siêu tốc (SQLite FTS5) tên tệp/thư mục/đường dẫn trong kho hiện tại.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Từ khóa cần tìm kiếm (hỗ trợ tiếng Việt có hoặc không dấu)"},
                "limit": {"type": "integer", "description": "Số kết quả tối đa (1..100)", "default": 20},
            },
            "required": ["query"],
        },
        "handler": _tool_search,
    },
    {
        "name": "kas_list_folder",
        "description": "Liệt kê các tệp và thư mục con bên trong một đường dẫn cụ thể của kho đang hoạt động.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Đường dẫn thư mục (bỏ trống để xem thư mục gốc của kho)"},
                "limit": {"type": "integer", "description": "Số mục tối đa trả về (1..200)", "default": 60},
            },
        },
        "handler": _tool_list_folder,
    },
    {
        "name": "kas_audit",
        "description": "Chạy kiểm toán quy ước đặt tên (chỉ đọc, an toàn tuyệt đối) theo bộ quy tắc tùy chỉnh của kho hiện tại và trả về thống kê cùng ví dụ vi phạm.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "branch": {"type": "string", "description": "Tùy chọn: chỉ kiểm toán một nhánh thư mục con"},
                "max_issues": {"type": "integer", "description": "Số ví dụ vi phạm tối đa trả về (1..100)", "default": 30},
            },
        },
        "handler": _tool_audit,
    },
    {
        "name": "kas_preview_rename",
        "description": "Kiểm tra & xem trước tên sau khi chuẩn hóa theo quy tắc đặt tên đang bật hoặc theo một preset cụ thể (chỉ đọc, không sửa tệp thật).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Danh sách tên tệp hoặc thư mục cần kiểm thử",
                },
                "is_folder": {"type": "boolean", "description": "True nếu là tên thư mục, False nếu là tên tệp", "default": False},
                "preset": {"type": "string", "description": "Tùy chọn preset thử nghiệm: academic_v6, general_clean, snake_case_dev, kebab_web"},
            },
            "required": ["names"],
        },
        "handler": _tool_preview_rename,
    },
    {
        "name": "kas_naming_rules_get",
        "description": "Đọc bộ quy tắc đặt tên đang áp dụng cho kho hiện tại cùng danh sách các preset có sẵn.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "handler": _tool_naming_rules_get,
    },
    {
        "name": "kas_naming_rules_set",
        "description": "Áp dụng preset hoặc tùy chỉnh chi tiết quy tắc đặt tên cho kho hiện hành (`vault`) hoặc mặc định toàn cục (`global`).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "scope": {"type": "string", "enum": ["vault", "global"], "default": "vault"},
                "preset": {"type": "string", "description": "Tên preset: academic_v6, general_clean, snake_case_dev, kebab_web"},
                "updates": {"type": "object", "description": "Các trường quy tắc muốn ghi đè (vd: folder_case, file_case, lowercase_extension, max_name_length...)"},
            },
        },
        "handler": _tool_naming_rules_set,
    },
    {
        "name": "kas_undo_list",
        "description": "Xem danh sách các lô thao tác gần đây trong Sổ cái Hoàn tác Hợp nhất của kho hiện tại.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Số lô gần nhất (1..50)", "default": 15},
            },
        },
        "handler": _tool_undo_list,
    },
]

_TOOL_MAP: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {t["name"]: t["handler"] for t in _TOOLS}


def get_agent_tool_schemas() -> List[Dict[str, Any]]:
    """Trả về danh sách schema công cụ chuẩn MCP (`name`, `description`, `inputSchema`)."""
    return [
        {
            "name": t["name"],
            "description": t["description"],
            "inputSchema": t["inputSchema"],
        }
        for t in _TOOLS
    ]


def get_openai_tools_spec() -> List[Dict[str, Any]]:
    """Chuyển đổi sang định dạng OpenAI Function Calling `tools`."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["inputSchema"],
            },
        }
        for t in _TOOLS
    ]


def execute_agent_tool(name: str, arguments: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Thực thi an toàn một công cụ KAS Agent theo tên và tham số JSON."""
    fn = _TOOL_MAP.get(name)
    if fn is None:
        return {"ok": False, "error": f"Công cụ không tồn tại: `{name}`", "available_tools": sorted(_TOOL_MAP)}
    try:
        return fn(dict(arguments or {}))
    except Exception as exc:
        return {"ok": False, "error": f"Lỗi khi chạy công cụ `{name}`: {exc}"}
