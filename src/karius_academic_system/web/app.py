"""Ứng dụng Web Dashboard cục bộ (`kas ui`) — Karius Academic System (KAS) v1.0 (FastAPI + máy chủ thuần Python an toàn Smart App Control)."""

import argparse
import collections
import contextlib
import http.server
import io
import json
import threading
import time
import urllib.parse
import uuid
import webbrowser
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from karius_academic_system import APP_NAME, APP_SHORT, __version__
from karius_academic_system import core as sc

_STATIC_DIR = Path(__file__).resolve().parent / "static"
_TASKS: Dict[str, Dict[str, Any]] = {}
_TASKS_LOCK = threading.Lock()
_ALLOWED_UI_COMMANDS = {"doctor", "kiem-tra", "bao-cao", "trung-lap", "danh-muc", "quet", "github"}


def _load_index_safe() -> Dict[str, Dict[str, Any]]:
    try:
        return sc.load_index(required=False)
    except Exception:
        return {}


def _render_index_html() -> str:
    html_path = _STATIC_DIR / "index.html"
    if not html_path.exists():
        return f"<h1>{APP_NAME} ({APP_SHORT}) v{__version__}</h1><p>Missing static/index.html</p>"
    return html_path.read_text(encoding="utf-8")


def _api_health_data() -> Dict[str, Any]:
    vc = sc.active_vault()
    return {
        "status": "ok",
        "app_name": APP_NAME,
        "app_short": APP_SHORT,
        "version": __version__,
        "has_vault": sc.has_configured_vault(),
        "vault_slug": vc.slug if vc else sc.VAULT_SLUG,
        "root_name": sc.ROOT_NAME,
        "root_id": sc.ROOT_ID,
        "vault_mode": sc.effective_vault_mode(),
    }


def _api_vaults_list_data() -> Dict[str, Any]:
    reg = sc.get_vault_registry()
    act = sc.active_vault()
    act_slug = act.slug if act else reg.active_slug
    return {
        "active_slug": act_slug,
        "active": act.to_dict() if act else None,
        "registry_path": str(reg.path),
        "vaults": [v.to_dict() for v in reg.list_vaults()],
    }


def _api_vault_add_data(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    source = str(body.get("source") or "").strip()
    if not source:
        return 400, {"detail": "Vui lòng nhập đường dẫn thư mục cục bộ hoặc URL/Folder ID Google Drive."}
    slug = str(body.get("slug") or "").strip() or None
    name = str(body.get("name") or "").strip() or None
    backend = str(body.get("backend") or "auto").strip()
    mode = str(body.get("mode") or "auto").strip()
    activate = bool(body.get("activate", True))

    reg = sc.get_vault_registry()
    kind, norm_root = sc.detect_source_kind(source)
    if kind == "local" and not Path(norm_root).is_dir():
        return 400, {"detail": f"Thư mục cục bộ không tồn tại: `{norm_root}`"}
    if kind == "gdrive" and not name:
        try:
            drv = sc.create_backend(backend=None if backend == "auto" else backend)
            info = drv.info(norm_root)
            if info and info.get("name"):
                name = str(info["name"])
        except Exception:
            pass
    vc = reg.add_vault(source, slug=slug, name=name, backend=backend, mode=mode, activate=activate)
    if activate:
        sc.activate_vault(vc.slug, persist=True)
    return 200, {"ok": True, "vault": vc.to_dict(), "vaults": _api_vaults_list_data()}


def _api_vault_activate_data(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    slug = str(body.get("slug") or "").strip()
    if not slug:
        return 400, {"detail": "Thiếu mã kho `slug`."}
    persist = bool(body.get("persist", True))
    try:
        vc = sc.activate_vault(slug, persist=persist)
    except KeyError as exc:
        return 404, {"detail": str(exc)}
    return 200, {"ok": True, "vault": vc.to_dict(), "vaults": _api_vaults_list_data()}


def _api_vault_remove_data(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    slug = str(body.get("slug") or "").strip()
    if not slug:
        return 400, {"detail": "Thiếu mã kho `slug`."}
    reg = sc.get_vault_registry()
    if not reg.remove_vault(slug):
        return 404, {"detail": f"Không tìm thấy kho `{slug}`."}
    sc.reload_config()
    return 200, {"ok": True, "removed": slug, "vaults": _api_vaults_list_data()}


def _api_vault_init_structure_data(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    if not sc.ROOT_ID:
        return 400, {"detail": "Chưa chọn kho dữ liệu đang hoạt động."}
    confirm = bool(body.get("confirm", False))
    folders = [
        sc.TONG_QUAN_FOLDER,
        f"{sc.TONG_QUAN_FOLDER}/{sc.DANH_SACH_FOLDER}",
        f"{sc.TONG_QUAN_FOLDER}/[02] NHẬT KÍ",
        sc.QUARANTINE_FOLDER,
    ]
    if not confirm:
        return 200, {"dry_run": True, "root_name": sc.ROOT_NAME, "folders": folders}
    drv = sc.create_backend()
    tq_id = drv.ensure_folder(sc.TONG_QUAN_FOLDER, sc.ROOT_ID)
    ds_id = drv.ensure_folder(sc.DANH_SACH_FOLDER, tq_id)
    nk_id = drv.ensure_folder("[02] NHẬT KÍ", tq_id)
    qt_id = drv.ensure_folder(sc.QUARANTINE_FOLDER, sc.ROOT_ID)
    vc = sc.active_vault()
    if vc is not None:
        reg = sc.get_vault_registry()
        merged = dict(vc.known_ids)
        merged.update({
            sc.TONG_QUAN_FOLDER: tq_id,
            f"{sc.TONG_QUAN_FOLDER}/{sc.DANH_SACH_FOLDER}": ds_id,
            f"{sc.TONG_QUAN_FOLDER}/[02] NHẬT KÍ": nk_id,
            sc.QUARANTINE_FOLDER: qt_id,
        })
        reg.update_vault(vc.slug, known_ids=merged, mode="academic_v7", detected_mode="academic_v7")
        sc.reload_config(vc.slug)
    return 200, {"ok": True, "root_name": sc.ROOT_NAME, "created": folders}


def _api_overview_data() -> Dict[str, Any]:
    idx = _load_index_safe()
    with sc.StorageDB() as db:
        if not db.has_index() and idx:
            db.import_index_dict(idx)
        db_stats = db.stats_summary() if db.has_index() else {
            "total_folders": 0, "total_files": 0, "total_bytes": 0, "branches": {}, "db_size_bytes": 0, "last_import_utc": "",
        }
        undo_batches = db.list_undo_batches(limit=10)

    cat_plan = sc.build_catalog_migration_plan(idx) if idx else {"summary": {}}
    from karius_academic_system.ops.dedup import find_system_junk

    junk = find_system_junk(idx) if idx else []
    drive_backends = sc.detect_drive_backends()
    vc = sc.active_vault()

    branches_list = [
        {
            "name": b,
            "folders": st["folders"],
            "files": st["files"],
            "bytes": st["bytes"],
            "size_human": sc.human_size(st["bytes"]),
        }
        for b, st in sorted(db_stats.get("branches", {}).items())
    ]
    return {
        "app_name": APP_NAME,
        "app_short": APP_SHORT,
        "version": __version__,
        "has_vault": sc.has_configured_vault(),
        "active_vault": vc.to_dict() if vc else None,
        "vault_mode": sc.effective_vault_mode(),
        "root_name": sc.ROOT_NAME,
        "root_id": sc.ROOT_ID,
        "stats": {
            "folders": db_stats.get("total_folders", 0),
            "files": db_stats.get("total_files", 0),
            "bytes": db_stats.get("total_bytes", 0),
            "size_human": sc.human_size(db_stats.get("total_bytes", 0)),
            "db_size_human": sc.human_size(db_stats.get("db_size_bytes", 0)),
            "last_import_utc": db_stats.get("last_import_utc", ""),
        },
        "branches": branches_list,
        "catalog_v7": cat_plan.get("summary", {}),
        "system_junk_count": len(junk),
        "drive_backend": drive_backends,
        "recent_undo_batches": undo_batches,
    }


def _api_search_data(q: str, branch: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
    t0 = time.perf_counter()
    norm_branch = sc.normalize_branch(branch) if branch else None
    lim = max(1, min(200, int(limit)))
    with sc.StorageDB() as db:
        hits = db.search_fts(q, branch=norm_branch, limit=lim)
    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
    for h in hits:
        h["size_human"] = sc.human_size(h.get("size", 0))
        h["url"] = sc.drive_url(h["id"], h.get("mime_type", ""))
    return {"query": q, "elapsed_ms": elapsed_ms, "count": len(hits), "results": hits}


def _api_audit_data(branch: Optional[str] = None, limit: int = 100) -> Dict[str, Any]:
    from karius_academic_system.ops.auditor import audit

    idx = _load_index_safe()
    norm_branch = sc.normalize_branch(branch) if branch else None
    if norm_branch == sc.ROOT_NAME:
        norm_branch = None
    lim = max(1, min(500, int(limit)))
    issues = audit(idx, norm_branch, check_structure=True) if idx else []
    by_sev = collections.Counter(i[0] for i in issues)
    by_code = collections.Counter((i[0], i[1]) for i in issues)
    return {
        "vault_mode": sc.effective_vault_mode(),
        "total": len(issues),
        "by_severity": dict(by_sev),
        "by_code": [{"severity": s, "code": c, "count": n} for (s, c), n in by_code.most_common()],
        "items": [
            {
                "severity": i[0],
                "code": i[1],
                "parent_path": i[2],
                "name": i[3],
                "id": i[4],
                "type": i[5],
                "description": i[6],
                "suggestion": i[7],
                "url": sc.drive_url(i[4], sc.FOLDER_MIME if i[5] == "Thư mục" else ""),
            }
            for i in issues[:lim]
        ],
    }


def _api_catalog_plan_data(mode: str = "smart", branch: Optional[str] = None, limit: int = 100) -> Dict[str, Any]:
    eff_mode = mode if mode in {"smart", "full"} else "smart"
    idx = _load_index_safe()
    norm_branch = sc.normalize_branch(branch) if branch else None
    if norm_branch == sc.ROOT_NAME:
        norm_branch = None
    lim = max(1, min(500, int(limit)))
    plan = sc.build_catalog_migration_plan(idx, branch=norm_branch, policy={"mode": eff_mode}) if idx else {
        "summary": {}, "renames": [], "prunes": [], "missing": [],
    }
    return {
        "mode": eff_mode,
        "summary": plan["summary"],
        "renames": plan["renames"][:lim],
        "prunes": plan["prunes"][:lim],
        "missing": plan["missing"][:lim],
    }


def _api_catalog_execute_data(
    mode: str = "smart",
    branch: Optional[str] = None,
    apply_prunes: bool = True,
    confirm: bool = False,
) -> Dict[str, Any]:
    idx = _load_index_safe()
    norm_branch = sc.normalize_branch(branch) if branch else None
    if norm_branch == sc.ROOT_NAME:
        norm_branch = None
    plan = sc.build_catalog_migration_plan(idx, branch=norm_branch, policy={"mode": mode})
    if not confirm:
        return {"dry_run": True, "summary": plan["summary"]}
    drive = sc.create_backend()
    with sc.StorageDB() as db:
        res = sc.apply_catalog_migration_plan(
            drive, plan, execute=True, apply_prunes=apply_prunes, db=db, index=idx
        )
    if res.get("index_updated"):
        sc.save_index(idx)
    return res


def _api_junk_data(branch: Optional[str] = None, limit: int = 100) -> Dict[str, Any]:
    from karius_academic_system.ops.dedup import find_system_junk

    idx = _load_index_safe()
    norm_branch = sc.normalize_branch(branch) if branch else None
    lim = max(1, min(500, int(limit)))
    items = find_system_junk(idx, None if norm_branch == sc.ROOT_NAME else norm_branch) if idx else []
    return {"count": len(items), "items": items[:lim]}


def _api_doctor_data() -> Dict[str, Any]:
    from karius_academic_system.ops.doctor import run_doctor

    return run_doctor()


def _api_undo_list_data() -> Dict[str, Any]:
    with sc.StorageDB() as db:
        return {"batches": db.list_undo_batches(limit=30)}


def _api_undo_run_data(batch_id: str, execute: bool = False) -> Tuple[int, Dict[str, Any]]:
    drive = sc.create_backend() if execute else None
    with sc.StorageDB() as db:
        res = db.undo_batch(drive, batch_id, execute=execute)
    if not res.get("ok") and "Không tìm thấy" in str(res.get("error", "")):
        return 404, {"detail": res["error"]}
    return 200, res


def _api_task_run_data(command: str, args: Optional[List[str]] = None) -> Tuple[int, Dict[str, Any]]:
    if command not in _ALLOWED_UI_COMMANDS:
        return 400, {"detail": f"Lệnh `{command}` không được hỗ trợ chạy trực tiếp từ Web UI."}
    arg_list = [str(a) for a in (args or [])]
    tid = uuid.uuid4().hex[:10]
    rec: Dict[str, Any] = {
        "id": tid,
        "command": command,
        "args": arg_list,
        "status": "running",
        "returncode": None,
        "started_utc": sc.now_utc_iso(),
        "finished_utc": "",
        "output": "",
    }
    with _TASKS_LOCK:
        _TASKS[tid] = rec

    def _worker():
        from karius_academic_system.cli.pipelines import invoke_module_in_process

        buf = io.StringIO()
        rc = 0
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                rc = invoke_module_in_process(command, arg_list)
        except Exception as exc:
            buf.write(f"\n[LỖI] {exc}\n")
            rc = 1
        with _TASKS_LOCK:
            _TASKS[tid]["status"] = "done" if rc == 0 else "failed"
            _TASKS[tid]["returncode"] = rc
            _TASKS[tid]["finished_utc"] = sc.now_utc_iso()
            _TASKS[tid]["output"] = buf.getvalue()[-20_000:]

    threading.Thread(target=_worker, daemon=True).start()
    return 200, rec


def _api_task_status_data(task_id: str) -> Tuple[int, Dict[str, Any]]:
    with _TASKS_LOCK:
        rec = _TASKS.get(task_id)
    if not rec:
        return 404, {"detail": "Không tìm thấy tác vụ."}
    return 200, rec


def _api_rules_get_data() -> Dict[str, Any]:
    rules, source = sc.get_active_naming_rules()
    return {
        "source": source,
        "has_vault_override": sc.has_custom_naming_rules("vault"),
        "has_global_override": sc.has_custom_naming_rules("global"),
        "rules": rules.to_dict(),
        "presets": sc.NAMING_PRESETS,
        "folder_index_styles": sc.FOLDER_INDEX_STYLES,
        "folder_case_options": list(sc.FOLDER_CASE_OPTIONS),
        "file_case_options": list(sc.FILE_CASE_OPTIONS),
    }


def _api_rules_save_data(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    scope = "global" if str(body.get("scope") or "vault").strip().lower() == "global" else "vault"
    preset = str(body.get("preset") or "").strip()
    raw_rules = body.get("rules")
    if preset and not isinstance(raw_rules, dict):
        if preset not in sc.NAMING_PRESETS:
            return 400, {"detail": f"Preset không tồn tại: `{preset}`."}
        rules, saved = sc.apply_naming_preset(preset, scope=scope)
        return 200, {"ok": True, "scope": scope, "saved_path": str(saved), "data": _api_rules_get_data(), "rules": rules.to_dict()}
    if not isinstance(raw_rules, dict):
        return 400, {"detail": "Thiếu đối tượng `rules` hoặc tên `preset`."}
    rules = sc.NamingRuleSet.from_dict(raw_rules)
    saved = sc.save_naming_rules(rules, scope=scope)
    return 200, {"ok": True, "scope": scope, "saved_path": str(saved), "data": _api_rules_get_data(), "rules": rules.to_dict()}


def _api_rules_reset_data(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    scope = "global" if str(body.get("scope") or "vault").strip().lower() == "global" else "vault"
    removed = sc.reset_naming_rules(scope=scope)
    return 200, {"ok": True, "scope": scope, "removed": removed, "data": _api_rules_get_data()}


def _api_rules_preview_data(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    raw_names = body.get("names")
    if isinstance(raw_names, list):
        names = [str(x) for x in raw_names if str(x)]
    else:
        single = str(body.get("name") or "")
        names = [single] if single else []
    if not names:
        return 400, {"detail": "Vui lòng nhập ít nhất một tên tệp hoặc thư mục cần kiểm thử."}
    is_folder = bool(body.get("is_folder", False))
    raw_rules = body.get("rules")
    preset = str(body.get("preset") or "").strip()
    if isinstance(raw_rules, dict):
        rules = sc.NamingRuleSet.from_dict(raw_rules)
    elif preset and preset in sc.NAMING_PRESETS:
        rules = sc.preset_rules(preset)
    else:
        rules, _ = sc.get_active_naming_rules()
    return 200, {
        "ok": True,
        "preset": rules.preset,
        "results": [sc.preview_naming(nm, is_folder=is_folder, rules=rules) for nm in names[:50]],
    }


def _api_ai_config_get_data(port: int = 8765) -> Dict[str, Any]:
    from karius_academic_system.ai import AI_PROVIDERS, ai_config_path, generate_mcp_client_config, load_ai_config

    cfg = load_ai_config()
    return {
        "config_path": str(ai_config_path()),
        "config": cfg.masked_dict(),
        "providers": AI_PROVIDERS,
        "mcp": {
            "stdio_command": "kas mcp serve",
            "http_endpoint": f"http://127.0.0.1:{port}/api/mcp",
            "claude_desktop": generate_mcp_client_config(client="claude", http_port=port),
            "cursor_antigravity": generate_mcp_client_config(client="cursor", http_port=port),
            "http_client": generate_mcp_client_config(client="http", http_port=port),
        },
    }


def _api_ai_config_save_data(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    from karius_academic_system.ai import AI_PROVIDERS, load_ai_config, save_ai_config

    cfg = load_ai_config()
    if body.get("provider"):
        prov = str(body["provider"]).strip()
        if prov not in AI_PROVIDERS:
            return 400, {"detail": f"Provider không hỗ trợ: `{prov}`."}
        cfg.provider = prov
        if not body.get("base_url"):
            cfg.base_url = AI_PROVIDERS[prov]["default_base_url"]
        if not body.get("model"):
            cfg.model = AI_PROVIDERS[prov]["default_model"]
    if "base_url" in body and body["base_url"] is not None:
        cfg.base_url = str(body["base_url"]).strip().rstrip("/")
    if "model" in body and body["model"] is not None:
        cfg.model = str(body["model"]).strip()
    if body.get("clear_api_key"):
        cfg.api_key = ""
    elif body.get("api_key"):
        cfg.api_key = str(body["api_key"]).strip()
    if "system_prompt" in body and body["system_prompt"] is not None:
        cfg.system_prompt = str(body["system_prompt"])
    if "temperature" in body and body["temperature"] is not None:
        cfg.temperature = max(0.0, min(1.5, float(body["temperature"])))
    saved = save_ai_config(cfg)
    return 200, {"ok": True, "saved_path": str(saved), "config": cfg.masked_dict()}


def _api_ai_chat_data(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    from karius_academic_system.ai import chat_with_agent

    message = str(body.get("message") or "").strip()
    if not message:
        return 400, {"detail": "Vui lòng nhập nội dung câu hỏi cho Trợ Lý AI."}
    history = body.get("history") if isinstance(body.get("history"), list) else []
    try:
        res = chat_with_agent(message, history=history)
        return 200, res
    except Exception as exc:
        return 502, {"ok": False, "detail": str(exc)}


def _api_agent_tools_data() -> Dict[str, Any]:
    from karius_academic_system.ai import get_agent_tool_schemas, get_openai_tools_spec

    return {
        "app": f"{APP_NAME} ({APP_SHORT}) v{__version__}",
        "mcp_tools": get_agent_tool_schemas(),
        "openai_tools": get_openai_tools_spec(),
    }


def _api_agent_execute_data(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    from karius_academic_system.ai import execute_agent_tool

    tool_name = str(body.get("tool") or body.get("name") or "").strip()
    if not tool_name:
        return 400, {"detail": "Thiếu tên công cụ `tool`."}
    tool_args = body.get("arguments") if isinstance(body.get("arguments"), dict) else {}
    res = execute_agent_tool(tool_name, tool_args)
    return 200, {"ok": True, "tool": tool_name, "result": res}


def _api_mcp_rpc_data(body: Dict[str, Any]) -> Tuple[int, Any]:
    from karius_academic_system.ai import handle_mcp_jsonrpc

    resp = handle_mcp_jsonrpc(body)
    if resp is None:
        return 200, {"jsonrpc": "2.0", "ok": True}
    return 200, resp


def create_stdlib_server(host: str = "127.0.0.1", port: int = 8765) -> http.server.ThreadingHTTPServer:
    """
    Khởi tạo máy chủ HTTP thuần thư viện chuẩn Python (`http.server.ThreadingHTTPServer`).
    Không nạp bất kỳ tệp `.pyd`/`.dll` ngoài nào — chạy hoàn hảo trên Windows 11 bật Smart App Control.
    """

    class _DashboardHandler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

        def _send_bytes(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, status: int, payload: Any) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._send_bytes(status, data, "application/json; charset=utf-8")

        def _read_json_body(self) -> Dict[str, Any]:
            raw_len = int(self.headers.get("Content-Length") or "0")
            if raw_len <= 0:
                return {}
            raw = self.rfile.read(min(raw_len, 2 * 1024 * 1024))
            try:
                parsed = json.loads(raw.decode("utf-8"))
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            qs = urllib.parse.parse_qs(parsed.query)

            def _q1(key: str, default: Optional[str] = None) -> Optional[str]:
                vals = qs.get(key)
                return vals[0] if vals else default

            try:
                if path in {"/", "/index.html"}:
                    self._send_bytes(200, _render_index_html().encode("utf-8"), "text/html; charset=utf-8")
                    return
                if path == "/api/health":
                    self._send_json(200, _api_health_data())
                    return
                if path == "/api/vaults":
                    self._send_json(200, _api_vaults_list_data())
                    return
                if path == "/api/overview":
                    self._send_json(200, _api_overview_data())
                    return
                if path == "/api/rules":
                    self._send_json(200, _api_rules_get_data())
                    return
                if path == "/api/ai/config":
                    self._send_json(200, _api_ai_config_get_data(port=self.server.server_address[1]))
                    return
                if path == "/api/agent/tools":
                    self._send_json(200, _api_agent_tools_data())
                    return
                if path == "/api/search":
                    q = (_q1("q") or "").strip()
                    if not q:
                        self._send_json(422, {"detail": "Thiếu tham số truy vấn `q`."})
                        return
                    self._send_json(200, _api_search_data(q, branch=_q1("branch"), limit=int(_q1("limit", "50") or "50")))
                    return
                if path == "/api/audit":
                    self._send_json(200, _api_audit_data(branch=_q1("branch"), limit=int(_q1("limit", "100") or "100")))
                    return
                if path == "/api/catalog-v7/plan":
                    self._send_json(
                        200,
                        _api_catalog_plan_data(
                            mode=_q1("mode", "smart") or "smart",
                            branch=_q1("branch"),
                            limit=int(_q1("limit", "100") or "100"),
                        ),
                    )
                    return
                if path == "/api/junk":
                    self._send_json(200, _api_junk_data(branch=_q1("branch"), limit=int(_q1("limit", "100") or "100")))
                    return
                if path == "/api/doctor":
                    self._send_json(200, _api_doctor_data())
                    return
                if path == "/api/undo/batches":
                    self._send_json(200, _api_undo_list_data())
                    return
                if path.startswith("/api/tasks/"):
                    tid = urllib.parse.unquote(path[len("/api/tasks/"):])
                    code, data = _api_task_status_data(tid)
                    self._send_json(code, data)
                    return
                self._send_json(404, {"detail": f"Không tìm thấy đường dẫn: {path}"})
            except Exception as exc:
                self._send_json(500, {"detail": str(exc)})

        def do_POST(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            qs = urllib.parse.parse_qs(parsed.query)
            body = self._read_json_body()
            try:
                if path == "/api/vaults/add":
                    code, data = _api_vault_add_data(body)
                    self._send_json(code, data)
                    return
                if path == "/api/vaults/activate":
                    code, data = _api_vault_activate_data(body)
                    self._send_json(code, data)
                    return
                if path == "/api/vaults/remove":
                    code, data = _api_vault_remove_data(body)
                    self._send_json(code, data)
                    return
                if path == "/api/vaults/init-structure":
                    code, data = _api_vault_init_structure_data(body)
                    self._send_json(code, data)
                    return
                if path == "/api/rules":
                    code, data = _api_rules_save_data(body)
                    self._send_json(code, data)
                    return
                if path == "/api/rules/reset":
                    code, data = _api_rules_reset_data(body)
                    self._send_json(code, data)
                    return
                if path == "/api/rules/preview":
                    code, data = _api_rules_preview_data(body)
                    self._send_json(code, data)
                    return
                if path == "/api/ai/config":
                    code, data = _api_ai_config_save_data(body)
                    self._send_json(code, data)
                    return
                if path == "/api/ai/chat":
                    code, data = _api_ai_chat_data(body)
                    self._send_json(code, data)
                    return
                if path == "/api/agent/execute":
                    code, data = _api_agent_execute_data(body)
                    self._send_json(code, data)
                    return
                if path == "/api/mcp":
                    code, data = _api_mcp_rpc_data(body)
                    self._send_json(code, data)
                    return
                if path == "/api/catalog-v7/execute":
                    res = _api_catalog_execute_data(
                        mode=str(body.get("mode", "smart")),
                        branch=body.get("branch"),
                        apply_prunes=bool(body.get("apply_prunes", True)),
                        confirm=bool(body.get("confirm", False)),
                    )
                    self._send_json(200, res)
                    return
                if path == "/api/tasks/run":
                    code, data = _api_task_run_data(str(body.get("command", "")), body.get("args"))
                    self._send_json(code, data)
                    return
                if path.startswith("/api/undo/"):
                    bid = urllib.parse.unquote(path[len("/api/undo/"):])
                    ex_q = (qs.get("execute") or ["false"])[0].lower() in {"1", "true", "yes"}
                    code, data = _api_undo_run_data(bid, execute=ex_q or bool(body.get("execute", False)))
                    self._send_json(code, data)
                    return
                if path == "/api/shutdown":
                    self._send_json(200, {"ok": True, "message": "Đang tắt máy chủ cục bộ..."})
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                    return
                self._send_json(404, {"detail": f"Không tìm thấy đường dẫn: {path}"})
            except Exception as exc:
                self._send_json(500, {"detail": str(exc)})

    http.server.ThreadingHTTPServer.allow_reuse_address = True
    return http.server.ThreadingHTTPServer((host, port), _DashboardHandler)


def create_app():
    """Khởi tạo ứng dụng FastAPI phục vụ giao diện quản trị cục bộ `kas ui`."""
    try:
        from fastapi import Body, FastAPI, HTTPException, Query
        from fastapi.responses import HTMLResponse, JSONResponse
        from pydantic import BaseModel
    except (ImportError, OSError) as exc:
        raise RuntimeError(
            'Thiếu thư viện Web UI hoặc DLL bị chặn bởi Smart App Control. Dùng máy chủ thuần Python (`kas ui --stdlib`).'
        ) from exc

    app = FastAPI(
        title=f"{APP_NAME} ({APP_SHORT})",
        version=__version__,
        description="Hệ thống quản trị tri thức, đa kho dữ liệu, tùy chỉnh quy tắc đặt tên & kết nối AI/MCP Agent.",
    )

    class VaultAddRequest(BaseModel):
        source: str
        slug: Optional[str] = None
        name: Optional[str] = None
        backend: str = "auto"
        mode: str = "auto"
        activate: bool = True

    class VaultSlugRequest(BaseModel):
        slug: str
        persist: bool = True

    class VaultInitRequest(BaseModel):
        confirm: bool = False

    class ExecuteCatalogRequest(BaseModel):
        mode: str = "smart"
        branch: Optional[str] = None
        apply_prunes: bool = True
        confirm: bool = False

    class TaskRequest(BaseModel):
        command: str
        args: List[str] = []

    @app.get("/", response_class=HTMLResponse)
    def index_page():
        return HTMLResponse(_render_index_html())

    @app.get("/api/health")
    def api_health() -> Dict[str, Any]:
        return _api_health_data()

    @app.get("/api/vaults")
    def api_vaults() -> Dict[str, Any]:
        return _api_vaults_list_data()

    @app.post("/api/vaults/add")
    def api_vault_add(req: VaultAddRequest):
        code, data = _api_vault_add_data(req.dict() if hasattr(req, "dict") else req.model_dump())
        if code != 200:
            raise HTTPException(status_code=code, detail=data.get("detail", "Lỗi thêm kho"))
        return JSONResponse(data)

    @app.post("/api/vaults/activate")
    def api_vault_activate(req: VaultSlugRequest):
        code, data = _api_vault_activate_data(req.dict() if hasattr(req, "dict") else req.model_dump())
        if code != 200:
            raise HTTPException(status_code=code, detail=data.get("detail", "Không tìm thấy kho"))
        return JSONResponse(data)

    @app.post("/api/vaults/remove")
    def api_vault_remove(req: VaultSlugRequest):
        code, data = _api_vault_remove_data(req.dict() if hasattr(req, "dict") else req.model_dump())
        if code != 200:
            raise HTTPException(status_code=code, detail=data.get("detail", "Không tìm thấy kho"))
        return JSONResponse(data)

    @app.post("/api/vaults/init-structure")
    def api_vault_init(req: VaultInitRequest):
        code, data = _api_vault_init_structure_data(req.dict() if hasattr(req, "dict") else req.model_dump())
        if code != 200:
            raise HTTPException(status_code=code, detail=data.get("detail", "Lỗi khởi tạo khung"))
        return JSONResponse(data)

    @app.get("/api/rules")
    def api_rules_get() -> Dict[str, Any]:
        return _api_rules_get_data()

    @app.post("/api/rules")
    def api_rules_save(body: Dict[str, Any] = Body(...)):
        code, data = _api_rules_save_data(body)
        if code != 200:
            raise HTTPException(status_code=code, detail=data.get("detail", "Lỗi lưu quy tắc"))
        return JSONResponse(data)

    @app.post("/api/rules/reset")
    def api_rules_reset(body: Dict[str, Any] = Body(default={})):
        code, data = _api_rules_reset_data(body)
        return JSONResponse(data, status_code=code)

    @app.post("/api/rules/preview")
    def api_rules_preview(body: Dict[str, Any] = Body(...)):
        code, data = _api_rules_preview_data(body)
        if code != 200:
            raise HTTPException(status_code=code, detail=data.get("detail", "Lỗi kiểm thử tên"))
        return JSONResponse(data)

    @app.get("/api/ai/config")
    def api_ai_config_get() -> Dict[str, Any]:
        return _api_ai_config_get_data()

    @app.post("/api/ai/config")
    def api_ai_config_save(body: Dict[str, Any] = Body(...)):
        code, data = _api_ai_config_save_data(body)
        if code != 200:
            raise HTTPException(status_code=code, detail=data.get("detail", "Lỗi lưu cấu hình AI"))
        return JSONResponse(data)

    @app.post("/api/ai/chat")
    def api_ai_chat(body: Dict[str, Any] = Body(...)):
        code, data = _api_ai_chat_data(body)
        if code != 200:
            raise HTTPException(status_code=code, detail=data.get("detail", "Lỗi phản hồi AI"))
        return JSONResponse(data)

    @app.get("/api/agent/tools")
    def api_agent_tools() -> Dict[str, Any]:
        return _api_agent_tools_data()

    @app.post("/api/agent/execute")
    def api_agent_execute(body: Dict[str, Any] = Body(...)):
        code, data = _api_agent_execute_data(body)
        if code != 200:
            raise HTTPException(status_code=code, detail=data.get("detail", "Lỗi gọi công cụ Agent"))
        return JSONResponse(data)

    @app.post("/api/mcp")
    def api_mcp_rpc(body: Dict[str, Any] = Body(...)):
        code, data = _api_mcp_rpc_data(body)
        return JSONResponse(data, status_code=code)

    @app.get("/api/overview")
    def api_overview() -> Dict[str, Any]:
        return _api_overview_data()

    @app.get("/api/search")
    def api_search(
        q: str = Query(..., min_length=1),
        branch: Optional[str] = None,
        limit: int = Query(50, ge=1, le=200),
    ) -> Dict[str, Any]:
        return _api_search_data(q, branch=branch, limit=limit)

    @app.get("/api/audit")
    def api_audit(branch: Optional[str] = None, limit: int = Query(100, ge=1, le=500)) -> Dict[str, Any]:
        return _api_audit_data(branch=branch, limit=limit)

    @app.get("/api/catalog-v7/plan")
    def api_catalog_plan(
        mode: str = Query("smart", pattern="^(smart|full)$"),
        branch: Optional[str] = None,
        limit: int = Query(100, ge=1, le=500),
    ) -> Dict[str, Any]:
        return _api_catalog_plan_data(mode=mode, branch=branch, limit=limit)

    @app.post("/api/catalog-v7/execute")
    def api_catalog_execute(req: ExecuteCatalogRequest) -> Dict[str, Any]:
        return _api_catalog_execute_data(
            mode=req.mode,
            branch=req.branch,
            apply_prunes=req.apply_prunes,
            confirm=req.confirm,
        )

    @app.get("/api/junk")
    def api_junk(branch: Optional[str] = None, limit: int = Query(100, ge=1, le=500)) -> Dict[str, Any]:
        return _api_junk_data(branch=branch, limit=limit)

    @app.get("/api/doctor")
    def api_doctor() -> Dict[str, Any]:
        return _api_doctor_data()

    @app.get("/api/undo/batches")
    def api_undo_list() -> Dict[str, Any]:
        return _api_undo_list_data()

    @app.post("/api/undo/{batch_id}")
    def api_undo_run(batch_id: str, execute: bool = False) -> Dict[str, Any]:
        code, data = _api_undo_run_data(batch_id, execute=execute)
        if code != 200:
            raise HTTPException(status_code=code, detail=data.get("detail", "Lỗi hoàn tác"))
        return data

    @app.post("/api/tasks/run")
    def api_task_run(req: TaskRequest):
        code, data = _api_task_run_data(req.command, req.args)
        if code != 200:
            raise HTTPException(status_code=code, detail=data.get("detail", "Lệnh không hợp lệ"))
        return JSONResponse(data)

    @app.get("/api/tasks/{task_id}")
    def api_task_status(task_id: str) -> Dict[str, Any]:
        code, data = _api_task_status_data(task_id)
        if code != 200:
            raise HTTPException(status_code=code, detail=data.get("detail", "Không tìm thấy tác vụ"))
        return data

    return app


def start_embedded_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    prefer_stdlib: bool = False,
) -> Tuple[threading.Thread, Callable[[], None], str]:
    """Khởi chạy máy chủ nền trả về `(thread, stop_fn, engine_name)` (tự dự phòng `--stdlib` trên Windows SAC)."""
    if not prefer_stdlib:
        try:
            import uvicorn

            app = create_app()
            config = uvicorn.Config(app, host=host, port=port, log_level="warning")
            server = uvicorn.Server(config)
            th = threading.Thread(target=server.run, daemon=True)
            th.start()
            deadline = time.monotonic() + 5.0
            while not server.started and th.is_alive() and time.monotonic() < deadline:
                time.sleep(0.05)
            if server.started:
                return th, lambda: setattr(server, "should_exit", True), "fastapi+uvicorn"
        except (ImportError, OSError, RuntimeError):
            pass

    httpd = create_stdlib_server(host=host, port=port)
    th = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True)
    th.start()

    def _stop() -> None:
        try:
            httpd.shutdown()
            httpd.server_close()
        except Exception:
            pass

    return th, _stop, "stdlib-http"


def run_web_server(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="kas ui", description=f"Khởi chạy giao diện Web Dashboard {APP_NAME} ({APP_SHORT}).")
    ap.add_argument("--host", default="127.0.0.1", help="Địa chỉ lắng nghe (mặc định 127.0.0.1)")
    ap.add_argument("--port", type=int, default=8765, help="Cổng HTTP (mặc định 8765)")
    ap.add_argument("--open", action="store_true", dest="open_browser", help="Tự mở trình duyệt sau khi khởi chạy")
    ap.add_argument("--stdlib", action="store_true", help="Dùng máy chủ HTTP thuần Python (không nạp .pyd/.dll ngoài)")
    args = ap.parse_args(argv)

    url = f"http://{args.host}:{args.port}"
    th, stop_fn, engine = start_embedded_server(host=args.host, port=args.port, prefer_stdlib=args.stdlib)
    sc.log(f"{APP_NAME} ({APP_SHORT}) UI v{__version__} ({engine}) đang chạy tại {url}")
    if args.open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        while th.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        sc.log("Đang dừng máy chủ Web UI...")
        stop_fn()
    return 0
