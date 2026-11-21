"""Ứng dụng Web Dashboard cục bộ (`astorage ui`) dùng FastAPI + SQLite FTS5."""

import argparse
import collections
import contextlib
import io
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from storage_suite import __version__
from storage_suite import core as sc

_STATIC_DIR = Path(__file__).resolve().parent / "static"
_TASKS: Dict[str, Dict[str, Any]] = {}
_TASKS_LOCK = threading.Lock()


def _load_index_safe() -> Dict[str, Dict[str, Any]]:
    try:
        return sc.load_index(required=False)
    except Exception:
        return {}


def create_app():
    """Khởi tạo ứng dụng FastAPI phục vụ giao diện quản trị cục bộ `astorage ui`."""
    try:
        from fastapi import FastAPI, HTTPException, Query
        from fastapi.responses import HTMLResponse, JSONResponse
        from pydantic import BaseModel
    except ImportError as exc:
        raise RuntimeError(
            'Thiếu thư viện Web UI. Cài đặt bằng: pip install "storage-management-suite[web]"'
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
        html_path = _STATIC_DIR / "index.html"
        if not html_path.exists():
            return HTMLResponse("<h1>Storage Management Suite v4.0</h1><p>Missing static/index.html</p>")
        return HTMLResponse(html_path.read_text(encoding="utf-8"))

    @app.get("/api/health")
    def api_health() -> Dict[str, Any]:
        return {"status": "ok", "version": __version__, "root_name": sc.ROOT_NAME, "root_id": sc.ROOT_ID}

    @app.get("/api/overview")
    def api_overview() -> Dict[str, Any]:
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

    @app.get("/api/search")
    def api_search(
        q: str = Query(..., min_length=1),
        branch: Optional[str] = None,
        limit: int = Query(50, ge=1, le=200),
    ) -> Dict[str, Any]:
        t0 = time.perf_counter()
        norm_branch = sc.normalize_branch(branch) if branch else None
        with sc.StorageDB() as db:
            hits = db.search_fts(q, branch=norm_branch, limit=limit)
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
        for h in hits:
            h["size_human"] = sc.human_size(h.get("size", 0))
            h["url"] = sc.drive_url(h["id"], h.get("mime_type", ""))
        return {"query": q, "elapsed_ms": elapsed_ms, "count": len(hits), "results": hits}

    @app.get("/api/audit")
    def api_audit(branch: Optional[str] = None, limit: int = Query(100, ge=1, le=500)) -> Dict[str, Any]:
        from storage_suite.ops.auditor import audit

        idx = _load_index_safe()
        norm_branch = sc.normalize_branch(branch) if branch else None
        if norm_branch == sc.ROOT_NAME:
            norm_branch = None
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
                for i in issues[:limit]
            ],
        }

    @app.get("/api/catalog-v7/plan")
    def api_catalog_plan(
        mode: str = Query("smart", pattern="^(smart|full)$"),
        branch: Optional[str] = None,
        limit: int = Query(100, ge=1, le=500),
    ) -> Dict[str, Any]:
        idx = _load_index_safe()
        norm_branch = sc.normalize_branch(branch) if branch else None
        if norm_branch == sc.ROOT_NAME:
            norm_branch = None
        plan = sc.build_catalog_migration_plan(idx, branch=norm_branch, policy={"mode": mode}) if idx else {
            "summary": {}, "renames": [], "prunes": [], "missing": [],
        }
        return {
            "mode": mode,
            "summary": plan["summary"],
            "renames": plan["renames"][:limit],
            "prunes": plan["prunes"][:limit],
            "missing": plan["missing"][:limit],
        }

    @app.post("/api/catalog-v7/execute")
    def api_catalog_execute(req: ExecuteCatalogRequest) -> Dict[str, Any]:
        idx = _load_index_safe()
        norm_branch = sc.normalize_branch(req.branch) if req.branch else None
        if norm_branch == sc.ROOT_NAME:
            norm_branch = None
        plan = sc.build_catalog_migration_plan(idx, branch=norm_branch, policy={"mode": req.mode})
        if not req.confirm:
            return {"dry_run": True, "summary": plan["summary"]}
        drive = sc.create_drive()
        with sc.StorageDB() as db:
            res = sc.apply_catalog_migration_plan(
                drive, plan, execute=True, apply_prunes=req.apply_prunes, db=db
            )
        return res

    @app.get("/api/junk")
    def api_junk(branch: Optional[str] = None, limit: int = Query(100, ge=1, le=500)) -> Dict[str, Any]:
        from storage_suite.ops.dedup import find_system_junk

        idx = _load_index_safe()
        norm_branch = sc.normalize_branch(branch) if branch else None
        items = find_system_junk(idx, None if norm_branch == sc.ROOT_NAME else norm_branch) if idx else []
        return {"count": len(items), "items": items[:limit]}

    @app.get("/api/doctor")
    def api_doctor() -> Dict[str, Any]:
        from storage_suite.ops.doctor import run_doctor

        return run_doctor()

    @app.get("/api/undo/batches")
    def api_undo_list() -> Dict[str, Any]:
        with sc.StorageDB() as db:
            return {"batches": db.list_undo_batches(limit=30)}

    @app.post("/api/undo/{batch_id}")
    def api_undo_run(batch_id: str, execute: bool = False) -> Dict[str, Any]:
        drive = sc.create_drive() if execute else None
        with sc.StorageDB() as db:
            res = db.undo_batch(drive, batch_id, execute=execute)
        if not res.get("ok") and "Không tìm thấy" in str(res.get("error", "")):
            raise HTTPException(status_code=404, detail=res["error"])
        return res

    @app.post("/api/tasks/run")
    def api_task_run(req: TaskRequest):
        allowed_safe = {"doctor", "kiem-tra", "bao-cao", "trung-lap", "danh-muc", "quet", "github"}
        if req.command not in allowed_safe:
            raise HTTPException(status_code=400, detail=f"Lệnh `{req.command}` không được hỗ trợ chạy trực tiếp từ Web UI.")
        tid = uuid.uuid4().hex[:10]
        rec: Dict[str, Any] = {
            "id": tid,
            "command": req.command,
            "args": req.args,
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
                    rc = invoke_module_in_process(req.command, req.args)
            except Exception as exc:
                buf.write(f"\n[LỖI] {exc}\n")
                rc = 1
            with _TASKS_LOCK:
                _TASKS[tid]["status"] = "done" if rc == 0 else "failed"
                _TASKS[tid]["returncode"] = rc
                _TASKS[tid]["finished_utc"] = sc.now_utc_iso()
                _TASKS[tid]["output"] = buf.getvalue()[-20_000:]

        threading.Thread(target=_worker, daemon=True).start()
        return JSONResponse(rec)

    @app.get("/api/tasks/{task_id}")
    def api_task_status(task_id: str) -> Dict[str, Any]:
        with _TASKS_LOCK:
            rec = _TASKS.get(task_id)
        if not rec:
            raise HTTPException(status_code=404, detail="Không tìm thấy tác vụ.")
        return rec

    return app


def run_web_server(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="astorage ui", description="Khởi chạy giao diện Web Dashboard cục bộ.")
    ap.add_argument("--host", default="127.0.0.1", help="Địa chỉ lắng nghe (mặc định 127.0.0.1)")
    ap.add_argument("--port", type=int, default=8765, help="Cổng HTTP (mặc định 8765)")
    args = ap.parse_args(argv)
    try:
        import uvicorn
    except ImportError:
        sc.log('Thiếu uvicorn. Cài bằng: pip install "storage-management-suite[web]"')
        return 1
    app = create_app()
    sc.log(f"Storage Management Suite UI v{__version__} đang chạy tại http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0
