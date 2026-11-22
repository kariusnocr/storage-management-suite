"""Bộ thực thi Dòng Lệnh tích hợp (In-App Command Console) an toàn cho Karius Academic System (KAS)."""

from __future__ import annotations

import contextlib
import io
import json
import shlex
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from karius_academic_system import core as sc

_CONSOLE_LOCK = threading.Lock()
_CONSOLE_JOBS: Dict[str, Dict[str, Any]] = {}

_BLOCKED_INTERACTIVE_COMMANDS = {
    "ui": "Giao diện Web đang chạy sẵn trong cửa sổ này.",
    "desktop": "Ứng dụng Desktop đang mở sẵn.",
}


def console_history_path() -> Path:
    return sc.user_config_dir() / "command_history.json"


def split_command_line(raw_command: str) -> List[str]:
    """Tách chuỗi lệnh `kas` an toàn (bảo toàn dấu `\\` đường dẫn Windows như `E:\\SÁCH`)."""
    txt = (raw_command or "").strip()
    if not txt:
        return []
    try:
        tokens = shlex.split(txt, posix=False)
    except ValueError as exc:
        raise ValueError(f"Cú pháp dấu ngoặc kép không hợp lệ: {exc}") from exc
    cleaned: List[str] = []
    for tok in tokens:
        if len(tok) >= 2 and ((tok[0] == '"' and tok[-1] == '"') or (tok[0] == "'" and tok[-1] == "'")):
            cleaned.append(tok[1:-1])
        else:
            cleaned.append(tok)
    if cleaned and cleaned[0].lower() in {"kas", "kas.cmd", "kas.exe"}:
        cleaned = cleaned[1:]
    return cleaned


def validate_console_argv(argv: List[str]) -> Tuple[bool, str]:
    if not argv:
        return False, "Vui lòng nhập lệnh KAS (ví dụ: `version`, `doctor`, `vault list`, `quet`, `auth status`)."
    # Tìm lệnh chính sau cờ toàn cục `--kho <slug>` / `--vault <slug>`
    idx = 0
    while idx + 1 < len(argv) and argv[idx] in {"--kho", "--vault"}:
        idx += 2
    if idx >= len(argv):
        return False, "Thiếu tên lệnh sau `--kho`."
    cmd = argv[idx]
    rest = argv[idx + 1 :]
    if cmd in _BLOCKED_INTERACTIVE_COMMANDS:
        return False, _BLOCKED_INTERACTIVE_COMMANDS[cmd]
    if cmd == "ai" and rest and rest[0] == "chat":
        return False, "Hãy dùng `ai ask \"<câu hỏi>\"` trong Dòng Lệnh, hoặc trò chuyện trực tiếp tại tab **Trợ Lý AI & Agent**."
    if cmd == "mcp" and rest and rest[0] == "serve":
        return False, "`mcp serve` là máy chủ stdio dành cho Claude Desktop/Cursor. Trong ứng dụng hãy dùng `mcp config` hoặc `mcp tools`."
    if cmd in {"uninstall", "go-cai-dat"} and any(a in {"--thuc-thi", "--execute"} for a in rest):
        return False, "Để gỡ cài đặt thật khi ứng dụng đang mở, hãy vào tab **Cài Đặt → Gỡ Cài Đặt Phần Mềm** (hoặc chạy `kas uninstall --thuc-thi` ngoài PowerShell/Terminal). Trong Console bạn vẫn có thể chạy `uninstall` để xem trước."
    return True, ""


def load_command_history(limit: int = 50) -> List[Dict[str, Any]]:
    p = console_history_path()
    if not p.exists():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return raw[-limit:]
    except Exception:
        pass
    return []


def _append_history(entry: Dict[str, Any]) -> None:
    p = console_history_path()
    hist = load_command_history(limit=100)
    hist.append(entry)
    hist = hist[-100:]
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(hist, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def clear_command_history() -> None:
    p = console_history_path()
    if p.exists():
        p.unlink()


def run_console_command_sync(raw_command: str) -> Dict[str, Any]:
    """Thực thi đồng bộ một lệnh `kas` trong tiến trình (bắt toàn bộ stdout/stderr UTF-8)."""
    from karius_academic_system.cli.main import main as kas_main

    try:
        argv = split_command_line(raw_command)
    except ValueError as exc:
        return {
            "ok": False,
            "command": raw_command.strip(),
            "argv": [],
            "returncode": 2,
            "output": str(exc),
            "elapsed_ms": 0.0,
        }
    ok, err = validate_console_argv(argv)
    if not ok:
        return {
            "ok": False,
            "command": raw_command.strip(),
            "argv": argv,
            "returncode": 2,
            "output": err,
            "elapsed_ms": 0.0,
        }

    t0 = time.perf_counter()
    buf = io.StringIO()
    rc = 0
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            res = kas_main(argv)
            rc = int(res) if isinstance(res, int) else 0
    except SystemExit as exc:
        code = exc.code
        if code is None:
            rc = 0
        elif isinstance(code, int):
            rc = code
        else:
            buf.write(str(code) + "\n")
            rc = 1
    except Exception as exc:
        buf.write(f"[LỖI] {exc}\n")
        rc = 1

    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 1)
    out_text = buf.getvalue()[-40_000:]
    record = {
        "ok": rc == 0,
        "command": "kas " + " ".join(argv),
        "raw": raw_command.strip(),
        "argv": argv,
        "returncode": rc,
        "output": out_text or "(Lệnh hoàn tất — không có đầu ra)",
        "elapsed_ms": elapsed_ms,
        "finished_utc": sc.now_utc_iso(),
    }
    _append_history(
        {
            "command": record["command"],
            "returncode": rc,
            "elapsed_ms": elapsed_ms,
            "finished_utc": record["finished_utc"],
        }
    )
    return record


def start_console_job(raw_command: str) -> Tuple[int, Dict[str, Any]]:
    """Khởi chạy nền một lệnh `kas` để giao diện theo dõi realtime (không chặn HTTP server)."""
    try:
        argv = split_command_line(raw_command)
    except ValueError as exc:
        return 400, {"detail": str(exc)}
    ok, err = validate_console_argv(argv)
    if not ok:
        return 400, {"detail": err}

    jid = uuid.uuid4().hex[:10]
    job = {
        "id": jid,
        "command": "kas " + " ".join(argv),
        "argv": argv,
        "status": "running",
        "started_utc": sc.now_utc_iso(),
        "finished_utc": "",
        "returncode": None,
        "elapsed_ms": 0.0,
        "output": "",
    }
    with _CONSOLE_LOCK:
        _CONSOLE_JOBS[jid] = job

    def _worker() -> None:
        res = run_console_command_sync(raw_command)
        with _CONSOLE_LOCK:
            _CONSOLE_JOBS[jid].update(
                {
                    "status": "done" if res["returncode"] == 0 else "failed",
                    "returncode": res["returncode"],
                    "elapsed_ms": res["elapsed_ms"],
                    "finished_utc": res.get("finished_utc") or sc.now_utc_iso(),
                    "output": res["output"],
                }
            )

    threading.Thread(target=_worker, daemon=True).start()
    return 200, dict(job)


def get_console_job(job_id: str) -> Optional[Dict[str, Any]]:
    with _CONSOLE_LOCK:
        j = _CONSOLE_JOBS.get(job_id)
        return dict(j) if j else None


QUICK_COMMANDS: List[Dict[str, str]] = [
    {"label": "Phiên bản & Kho hiện tại", "cmd": "version", "group": "Hệ thống"},
    {"label": "Chẩn đoán Doctor", "cmd": "doctor", "group": "Hệ thống"},
    {"label": "Tự động cài công cụ & thư viện", "cmd": "setup", "group": "Hệ thống"},
    {"label": "Danh sách kho", "cmd": "vault list", "group": "Kho dữ liệu"},
    {"label": "Quét chỉ mục kho", "cmd": "quet", "group": "Kho dữ liệu"},
    {"label": "Thống kê SQLite", "cmd": "db stats", "group": "Kho dữ liệu"},
    {"label": "Kiểm toán quy ước", "cmd": "kiem-tra", "group": "Kiểm toán"},
    {"label": "Danh sách preset tên", "cmd": "rules presets", "group": "Quy tắc"},
    {"label": "Trạng thái Google Drive", "cmd": "auth status", "group": "Kết nối"},
    {"label": "Lịch sử Hoàn tác (Undo)", "cmd": "undo list", "group": "An toàn"},
    {"label": "Cấu hình MCP Agent", "cmd": "mcp config --client claude", "group": "AI & Agent"},
]
