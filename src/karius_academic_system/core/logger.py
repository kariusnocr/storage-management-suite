"""Hệ thống Ghi Nhận Nhật Kí Sự Kiện & Báo Lỗi Bền Bỉ (Persistent Logging & Crash Journal) — KAS v1.9.0.

Chức năng:
- Lưu bền bỉ nhật kí có cấu trúc JSONL (`kas_events.jsonl`) & văn bản xoay vòng (`kas.log`) tại `<data_root>/logs/`.
- Tự động xoay vòng tệp khi vượt 2 MB (giữ tối đa 3 bản lưu cũ), không làm đầy bộ nhớ máy tính / điện thoại Android.
- Tự động ẩn thông tin nhạy cảm (`ghp_`, `github_pat_`, `sk-`, `AIza`, `Bearer ...`, mật khẩu) trước khi ghi hoặc xuất tệp.
- Tự động bắt ngoại lệ chưa được xử lý (`sys.excepthook`, `threading.excepthook`) và hợp nhất nhật kí Android gốc (`android_native.log`).
- Hỗ trợ lọc theo mức độ (`ERROR`, `WARNING`, `INFO`), tìm kiếm không dấu, xóa sạch và xuất tệp chẩn đoán (`.txt` / `.json`).
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import platform
import re
import sys
import threading
import traceback
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from karius_academic_system import APP_NAME, APP_SHORT, __version__

MAX_LOG_BYTES = 2 * 1024 * 1024
MAX_ROTATED_BACKUPS = 3
VALID_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

_LOG_LOCK = threading.RLock()
_TLS = threading.local()
_HOOKS_INSTALLED = False

_RE_SECRET_PATTERNS = [
    (re.compile(r"\b(ghp_[A-Za-z0-9]{16,})\b"), "ghp_***REDACTED***"),
    (re.compile(r"\b(github_pat_[A-Za-z0-9_]{16,})\b"), "github_pat_***REDACTED***"),
    (re.compile(r"\b(gho_[A-Za-z0-9]{16,})\b"), "gho_***REDACTED***"),
    (re.compile(r"\b(AIza[0-9A-Za-z\-_]{20,})\b"), "AIza***REDACTED***"),
    (re.compile(r"\b(sk-[A-Za-z0-9\-_]{16,})\b"), "sk-***REDACTED***"),
    (re.compile(r"(Bearer\s+)[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE), r"\1***REDACTED***"),
    (
        re.compile(r'("(?:password|api_key|token|client_secret|access_token|refresh_token)"\s*:\s*")([^"]*)(")', re.IGNORECASE),
        r"\1***REDACTED***\3",
    ),
    (
        re.compile(
            r"\b((?:password|passwd|api_key|client_secret|access_token|refresh_token|secret)\s*=\s*)([^\s&;,'\"]+)",
            re.IGNORECASE,
        ),
        r"\1***REDACTED***",
    ),
]


def _now_utc_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text or "") if unicodedata.category(c) != "Mn")


def redact_secrets(text: str) -> str:
    """Ẩn tự động token/API key/mật khẩu trong chuỗi nhật kí trước khi lưu đĩa hoặc xuất tệp."""
    out = str(text or "")
    for pat, repl in _RE_SECRET_PATTERNS:
        out = pat.sub(repl, out)
    return out


def logs_dir() -> Path:
    """Thư mục lưu nhật kí dùng chung toàn hệ thống (`<KAS_DATA_DIR>/logs` hoặc `~/.local/share/kas/logs`)."""
    env = (os.environ.get("KAS_DATA_DIR") or "").strip()
    if env:
        base = Path(env).expanduser()
    else:
        base = Path.home() / ".local" / "share" / "kas"
    p = base / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def events_jsonl_path() -> Path:
    return logs_dir() / "kas_events.jsonl"


def text_log_path() -> Path:
    return logs_dir() / "kas.log"


def android_native_log_path() -> Path:
    return logs_dir() / "android_native.log"


def _rotate_if_needed(path: Path) -> None:
    try:
        if not path.exists() or path.stat().st_size < MAX_LOG_BYTES:
            return
        for idx in range(MAX_ROTATED_BACKUPS, 0, -1):
            src = path.with_name(f"{path.name}.{idx}")
            dst = path.with_name(f"{path.name}.{idx + 1}")
            if idx == MAX_ROTATED_BACKUPS:
                if src.exists():
                    src.unlink(missing_ok=True)
            elif src.exists():
                src.replace(dst)
        path.replace(path.with_name(f"{path.name}.1"))
    except OSError:
        pass


def _normalize_level(level: str) -> str:
    lv = str(level or "INFO").strip().upper()
    if lv in {"WARN"}:
        return "WARNING"
    if lv in {"ERR", "FATAL"}:
        return "ERROR"
    return lv if lv in VALID_LEVELS else "INFO"


def record_event(
    level: str,
    category: str,
    message: str,
    *,
    detail: str = "",
    traceback_text: str = "",
    source: str = "backend",
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Ghi 1 sự kiện / lỗi bền bỉ xuống đĩa (`kas_events.jsonl` & `kas.log`)."""
    if getattr(_TLS, "in_logger", False):
        return {}
    _TLS.in_logger = True
    try:
        ts = _now_utc_iso()
        norm_lv = _normalize_level(level)
        cat = (category or "general").strip()[:48] or "general"
        src = (source or "backend").strip()[:32] or "backend"
        msg = redact_secrets(str(message or "").strip())[:2000]
        det = redact_secrets(str(detail or "").strip())[:4000]
        tb = redact_secrets(str(traceback_text or "").strip())[:8000]

        safe_meta: Dict[str, Any] = {}
        if isinstance(meta, dict):
            for k, v in list(meta.items())[:16]:
                safe_meta[str(k)[:48]] = redact_secrets(str(v))[:300]

        entry: Dict[str, Any] = {
            "ts": ts,
            "level": norm_lv,
            "category": cat,
            "source": src,
            "message": msg,
            "detail": det,
            "traceback": tb,
            "version": __version__,
            "pid": os.getpid(),
            "meta": safe_meta,
        }

        with _LOG_LOCK:
            jp = events_jsonl_path()
            tp = text_log_path()
            _rotate_if_needed(jp)
            _rotate_if_needed(tp)

            with open(jp, "a", encoding="utf-8") as jf:
                jf.write(json.dumps(entry, ensure_ascii=False) + "\n")

            line = f"[{ts}] [{norm_lv:<7}] [{src}/{cat}] {msg}"
            if det:
                line += f" | {det}"
            with open(tp, "a", encoding="utf-8") as tf:
                tf.write(line + "\n")
                if tb:
                    for tb_ln in tb.splitlines():
                        tf.write(f"    {tb_ln}\n")
        return entry
    except Exception:
        return {}
    finally:
        _TLS.in_logger = False


def record_exception(
    category: str,
    exc: BaseException,
    *,
    message: str = "",
    source: str = "backend",
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Ghi lại ngoại lệ kèm đầy đủ stack trace đã ẩn bí mật."""
    tb_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    msg = message or f"{type(exc).__name__}: {exc}"
    return record_event(
        "ERROR",
        category,
        msg,
        detail=f"{type(exc).__name__}: {exc}",
        traceback_text=tb_str,
        source=source,
        meta=meta,
    )


def install_global_exception_hooks() -> None:
    """Đăng ký trình bắt lỗi toàn cục cho tiến trình chính và mọi luồng nền (an toàn khi gọi nhiều lần)."""
    global _HOOKS_INSTALLED
    if _HOOKS_INSTALLED:
        return
    _HOOKS_INSTALLED = True

    orig_sys_hook = sys.excepthook

    def _kas_sys_excepthook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            orig_sys_hook(exc_type, exc_value, exc_tb)
            return
        try:
            tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
            record_event(
                "CRITICAL",
                "uncaught",
                f"Lỗi nghiêm trọng chưa được bắt: {exc_type.__name__}: {exc_value}",
                traceback_text=tb_str,
                source="python",
            )
        except Exception:
            pass
        orig_sys_hook(exc_type, exc_value, exc_tb)

    sys.excepthook = _kas_sys_excepthook

    if hasattr(threading, "excepthook"):
        orig_thread_hook = threading.excepthook

        def _kas_thread_excepthook(args):
            try:
                tb_str = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
                tname = getattr(args.thread, "name", "unknown")
                record_event(
                    "ERROR",
                    "thread_uncaught",
                    f"Lỗi luồng nền ({tname}): {args.exc_type.__name__}: {args.exc_value}",
                    traceback_text=tb_str,
                    source="python",
                )
            except Exception:
                pass
            orig_thread_hook(args)

        threading.excepthook = _kas_thread_excepthook


def _read_android_native_log_lines(limit: int = 200) -> List[Dict[str, Any]]:
    """Đọc thêm tệp `android_native.log` do MainActivity.java ghi (nếu đang chạy trên APK Android)."""
    p = android_native_log_path()
    if not p.is_file():
        return []
    entries: List[Dict[str, Any]] = []
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]
        for ln in lines:
            raw = ln.strip()
            if not raw:
                continue
            # Format: [2026-11-23T12:00:00Z] [ERROR] [wifi] message
            m = re.match(r"^\[([^\]]+)\]\s+\[([A-Z]+)\]\s+\[([^\]]+)\]\s+(.*)$", raw)
            if m:
                entries.append(
                    {
                        "ts": m.group(1),
                        "level": _normalize_level(m.group(2)),
                        "category": m.group(3),
                        "source": "android_native",
                        "message": redact_secrets(m.group(4)),
                        "detail": "",
                        "traceback": "",
                        "version": __version__,
                        "pid": os.getpid(),
                        "meta": {},
                    }
                )
            else:
                entries.append(
                    {
                        "ts": "",
                        "level": "INFO",
                        "category": "android",
                        "source": "android_native",
                        "message": redact_secrets(raw),
                        "detail": "",
                        "traceback": "",
                        "version": __version__,
                        "pid": os.getpid(),
                        "meta": {},
                    }
                )
    except OSError:
        pass
    return entries


def list_logs(
    *,
    level: str = "",
    category: str = "",
    query: str = "",
    limit: int = 200,
    include_android_native: bool = True,
) -> Dict[str, Any]:
    """Đọc danh sách sự kiện & nhật kí báo lỗi mới nhất kèm thống kê tổng quan."""
    lim = max(1, min(int(limit or 200), 2000))
    lv_filter = _normalize_level(level) if level and level.strip().upper() not in {"ALL", "*"} else ""
    cat_filter = (category or "").strip().lower()
    q_norm = _strip_accents((query or "").strip().lower())

    entries: List[Dict[str, Any]] = []
    jp = events_jsonl_path()
    with _LOG_LOCK:
        if jp.is_file():
            try:
                raw_lines = jp.read_text(encoding="utf-8", errors="replace").splitlines()
                for ln in raw_lines[-3000:]:
                    ln = ln.strip()
                    if not ln:
                        continue
                    try:
                        obj = json.loads(ln)
                        if isinstance(obj, dict):
                            entries.append(obj)
                    except json.JSONDecodeError:
                        continue
            except OSError:
                pass
        if include_android_native:
            entries.extend(_read_android_native_log_lines(limit=300))

    # Sắp xếp mới nhất trước theo timestamp ISO-8601
    entries.sort(key=lambda e: str(e.get("ts") or ""), reverse=True)

    counts = {"total": len(entries), "errors": 0, "warnings": 0, "info": 0}
    for e in entries:
        lv = _normalize_level(str(e.get("level") or "INFO"))
        if lv in {"ERROR", "CRITICAL"}:
            counts["errors"] += 1
        elif lv == "WARNING":
            counts["warnings"] += 1
        else:
            counts["info"] += 1

    filtered: List[Dict[str, Any]] = []
    for e in entries:
        lv = _normalize_level(str(e.get("level") or "INFO"))
        if lv_filter:
            if lv_filter == "ERROR":
                if lv not in {"ERROR", "CRITICAL"}:
                    continue
            elif lv != lv_filter:
                continue
        if cat_filter and str(e.get("category") or "").lower() != cat_filter:
            continue
        if q_norm:
            hay = _strip_accents(
                f"{e.get('category', '')} {e.get('source', '')} {e.get('message', '')} "
                f"{e.get('detail', '')} {e.get('traceback', '')}".lower()
            )
            if q_norm not in hay:
                continue
        filtered.append(e)
        if len(filtered) >= lim:
            break

    ldir = logs_dir()
    log_files: List[Dict[str, Any]] = []
    total_bytes = 0
    try:
        for f in sorted(ldir.iterdir()):
            if f.is_file():
                sz = f.stat().st_size
                total_bytes += sz
                log_files.append({"name": f.name, "size": sz, "path": str(f)})
    except OSError:
        pass

    return {
        "ok": True,
        "version": __version__,
        "log_dir": str(ldir),
        "total_bytes": total_bytes,
        "counts": counts,
        "filtered_count": len(filtered),
        "files": log_files,
        "entries": filtered,
    }


def clear_logs() -> Dict[str, Any]:
    """Xóa sạch nhật kí cũ và ghi dấu mốc bắt đầu phiên ghi mới."""
    ldir = logs_dir()
    removed = 0
    with _LOG_LOCK:
        for f in list(ldir.iterdir()):
            if f.is_file() and (
                f.name.startswith("kas_events.jsonl")
                or f.name.startswith("kas.log")
                or f.name == "android_native.log"
            ):
                try:
                    f.unlink(missing_ok=True)
                    removed += 1
                except OSError:
                    pass
    record_event("INFO", "logs", f"Đã dọn sạch {removed} tệp nhật kí cũ theo yêu cầu người dùng.", source="system")
    return {"ok": True, "removed_files": removed, "log_dir": str(ldir)}


def _collect_system_diagnostics() -> Dict[str, Any]:
    """Thu thập thông tin môi trường an toàn (không chứa bí mật) để đính kèm gói xuất nhật kí."""
    info: Dict[str, Any] = {
        "app_name": APP_NAME,
        "app_short": APP_SHORT,
        "version": __version__,
        "exported_utc": _now_utc_iso(),
        "os": platform.platform(),
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "log_dir": str(logs_dir()),
    }
    try:
        from karius_academic_system.web import android_bridge

        env = android_bridge.detect_android_environment()
        info["runtime_flavor"] = env.get("runtime_flavor")
        info["is_android"] = env.get("is_android")
        info["lan_urls"] = env.get("lan_urls")
        info["listening_host"] = env.get("listening_host")
        info["android_cert_sha1"] = (env.get("signing") or {}).get("sha1", "")
    except Exception:
        pass
    try:
        from karius_academic_system import core as sc

        vc = sc.active_vault()
        info["active_vault"] = vc.slug if vc else ""
        info["vault_source_kind"] = vc.source_kind if vc else ""
    except Exception:
        pass
    return info


def export_logs_bundle(
    *,
    fmt: str = "txt",
    level: str = "",
    limit: int = 1000,
    include_diagnostics: bool = True,
    extra_native_logs: str = "",
) -> Tuple[str, str, bytes]:
    """Đóng gói báo cáo nhật kí & chẩn đoán đã ẩn bí mật sẵn sàng tải về tệp `.txt` hoặc `.json`."""
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    norm_fmt = (fmt or "txt").strip().lower()
    listing = list_logs(level=level, limit=limit, include_android_native=True)
    diag = _collect_system_diagnostics() if include_diagnostics else {}

    if norm_fmt == "json":
        payload: Dict[str, Any] = {
            "diagnostics": diag,
            "counts": listing["counts"],
            "entries": listing["entries"],
        }
        if extra_native_logs:
            payload["extra_native_logs"] = redact_secrets(extra_native_logs)
        raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        return f"kas-logs-v{__version__}-{stamp}.json", "application/json; charset=utf-8", raw

    lines: List[str] = [
        "=" * 74,
        f"  {APP_NAME} ({APP_SHORT}) v{__version__} — BÁO CÁO NHẬT KÍ & CHẨN ĐOÁN LỖI",
        "=" * 74,
    ]
    if diag:
        lines.append("[THÔNG TIN MÔI TRƯỜNG]")
        for k, v in diag.items():
            lines.append(f"  - {k}: {v}")
        lines.append("")

    c = listing["counts"]
    lines.append(
        f"[THỐNG KÊ NHẬT KÍ] Tổng: {c['total']} | Lỗi: {c['errors']} | "
        f"Cảnh báo: {c['warnings']} | Thông tin: {c['info']}"
    )
    lines.append("-" * 74)
    for e in listing["entries"]:
        lines.append(
            f"[{e.get('ts', '')}] [{str(e.get('level', 'INFO')):<8}] "
            f"[{e.get('source', '')}/{e.get('category', '')}] {e.get('message', '')}"
        )
        if e.get("detail") and e.get("detail") != e.get("message"):
            lines.append(f"    Chi tiết: {e['detail']}")
        if e.get("meta"):
            lines.append(f"    Meta: {json.dumps(e['meta'], ensure_ascii=False)}")
        if e.get("traceback"):
            lines.append("    Traceback:")
            for tb_ln in str(e["traceback"]).splitlines():
                lines.append(f"      {tb_ln}")
    if extra_native_logs:
        lines.append("")
        lines.append("-" * 74)
        lines.append("[NHẬT KÍ ANDROID GỐC BỔ SUNG]")
        lines.append(redact_secrets(extra_native_logs))
    lines.append("")
    raw = "\n".join(lines).encode("utf-8")
    return f"kas-logs-v{__version__}-{stamp}.txt", "text/plain; charset=utf-8", raw
