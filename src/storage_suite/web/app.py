"""Ứng dụng Web Dashboard cục bộ (`astorage ui`) dùng FastAPI hoặc máy chủ HTTP thuần Python (an toàn với Smart App Control)."""

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

from storage_suite import __version__
from storage_suite import core as sc

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
        return f"<h1>Storage Management Suite v{__version__}</h1><p>Missing static/index.html</p>"
    return html_path.read_text(encoding="utf-8")


def _api_health_data() -> Dict[str, Any]:
    return {"status": "ok", "version": __version__, "root_name": sc.ROOT_NAME, "root_id": sc.ROOT_ID}


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
    from storage_suite.ops.dedup import find_system_junk

    junk = find_system_junk(idx) if idx else []
    drive_backends = sc.detect_drive_backends()

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
        "version": __version__,
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
    from storage_suite.ops.auditor import audit

    idx = _load_index_safe()
    norm_branch = sc.normalize_branch(branch) if branch else None
    if norm_branch == sc.ROOT_NAME:
        norm_branch = None
    lim = max(1, min(500, int(limit)))
    issues = audit(idx, norm_branch, check_structure=True) if idx else []
    by_sev = collections.Counter(i[0] for i in issues)
    by_code = collections.Counter((i[0], i[1]) for i in issues)
    return {
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
    drive = sc.create_drive()
    with sc.StorageDB() as db:
        res = sc.apply_catalog_migration_plan(
            drive, plan, execute=True, apply_prunes=apply_prunes, db=db, index=idx
        )
    if res.get("index_updated"):
        sc.save_index(idx)
    return res


def _api_junk_data(branch: Optional[str] = None, limit: int = 100) -> Dict[str, Any]:
    from storage_suite.ops.dedup import find_system_junk

    idx = _load_index_safe()
    norm_branch = sc.normalize_branch(branch) if branch else None
    lim = max(1, min(500, int(limit)))
    items = find_system_junk(idx, None if norm_branch == sc.ROOT_NAME else norm_branch) if idx else []
    return {"count": len(items), "items": items[:lim]}


def _api_doctor_data() -> Dict[str, Any]:
    from storage_suite.ops.doctor import run_doctor

    return run_doctor()


def _api_undo_list_data() -> Dict[str, Any]:
    with sc.StorageDB() as db:
        return {"batches": db.list_undo_batches(limit=30)}


def _api_undo_run_data(batch_id: str, execute: bool = False) -> Tuple[int, Dict[str, Any]]:
    drive = sc.create_drive() if execute else None
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
        from storage_suite.cli.pipelines import invoke_module_in_process

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
                if path == "/api/overview":
                    self._send_json(200, _api_overview_data())
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
    """Khởi tạo ứng dụng FastAPI phục vụ giao diện quản trị cục bộ `astorage ui`."""
    try:
        from fastapi import FastAPI, HTTPException, Query
        from fastapi.responses import HTMLResponse, JSONResponse
        from pydantic import BaseModel
    except (ImportError, OSError) as exc:
        raise RuntimeError(
            'Thiếu thư viện Web UI hoặc DLL bị chặn bởi Smart App Control. Dùng máy chủ thuần Python (`astorage ui --stdlib`).'
        ) from exc

    app = FastAPI(
        title="Storage Management Suite",
        version=__version__,
        description="Giao diện quản trị kho dữ liệu [A] STORAGE (Chuẩn V6 / Danh Mục V7).",
    )

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
    """
    Khởi chạy máy chủ nền trả về `(thread, stop_fn, engine_name)`.
    Tự động chuyển sang máy chủ HTTP thuần Python (`stdlib`) khi thiếu `uvicorn`/`fastapi`
    hoặc khi Windows Smart App Control chặn DLL mở rộng `.pyd`.
    """
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
    ap = argparse.ArgumentParser(prog="astorage ui", description="Khởi chạy giao diện Web Dashboard cục bộ.")
    ap.add_argument("--host", default="127.0.0.1", help="Địa chỉ lắng nghe (mặc định 127.0.0.1)")
    ap.add_argument("--port", type=int, default=8765, help="Cổng HTTP (mặc định 8765)")
    ap.add_argument("--open", action="store_true", dest="open_browser", help="Tự mở trình duyệt sau khi khởi chạy")
    ap.add_argument("--stdlib", action="store_true", help="Dùng máy chủ HTTP thuần Python (không nạp .pyd/.dll ngoài)")
    args = ap.parse_args(argv)

    url = f"http://{args.host}:{args.port}"
    th, stop_fn, engine = start_embedded_server(host=args.host, port=args.port, prefer_stdlib=args.stdlib)
    sc.log(f"Storage Management Suite UI v{__version__} ({engine}) đang chạy tại {url}")
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
