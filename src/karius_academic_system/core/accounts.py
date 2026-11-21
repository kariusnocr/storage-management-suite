"""Quản lý Tài khoản Đăng nhập Phần mềm (Local Auth & App Lock) và Kết nối Dịch vụ Bên thứ 3 (Google Drive, GitHub, AI, Webhook/Connector)."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from karius_academic_system import APP_SHORT, __version__
from karius_academic_system.core import config as _cfg
from karius_academic_system.core.drive_api import auth_login, auth_logout, auth_status
from karius_academic_system.core.utils import now_utc_iso

_PBKDF2_ITERATIONS = 200_000
_SESSION_TTL_SECONDS = 7 * 24 * 3600

_SESSIONS_LOCK = threading.Lock()
_SESSIONS: Dict[str, Dict[str, Any]] = {}

_GOOGLE_OAUTH_LOCK = threading.Lock()
_GOOGLE_OAUTH_STATE: Dict[str, Any] = {
    "status": "idle",
    "message": "",
    "started_utc": "",
    "finished_utc": "",
}


def account_path() -> Path:
    return _cfg.user_config_dir() / "account.json"


def integrations_path() -> Path:
    return _cfg.user_config_dir() / "integrations.json"


def _write_secret_json(path: Path, payload: Dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    tmp.replace(path)
    return path


def _read_json_dict(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _mask_secret(secret: str) -> str:
    s = (secret or "").strip()
    if len(s) > 8:
        return f"{s[:4]}***{s[-4:]}"
    return "***" if s else ""


def _hash_password(password: str, salt_hex: Optional[str] = None) -> Tuple[str, str]:
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return salt.hex(), dk.hex()


def _verify_password(password: str, salt_hex: str, expected_hash: str) -> bool:
    if not salt_hex or not expected_hash:
        return False
    _, actual = _hash_password(password, salt_hex=salt_hex)
    return hmac.compare_digest(actual, expected_hash)


def _public_account_view(acc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not acc or not acc.get("username"):
        return None
    return {
        "username": acc.get("username", ""),
        "display_name": acc.get("display_name") or acc.get("username", ""),
        "email": acc.get("email", ""),
        "require_login": bool(acc.get("require_login", False)),
        "created_utc": acc.get("created_utc", ""),
        "last_login_utc": acc.get("last_login_utc", ""),
    }


def load_account() -> Dict[str, Any]:
    return _read_json_dict(account_path())


def is_app_lock_enabled() -> bool:
    acc = load_account()
    return bool(acc.get("username") and acc.get("password_hash") and acc.get("require_login"))


def create_session(username: str) -> str:
    token = secrets.token_urlsafe(32)
    now = time.time()
    with _SESSIONS_LOCK:
        # Dọn phiên hết hạn
        expired = [k for k, v in _SESSIONS.items() if v["expires_at"] < now]
        for k in expired:
            _SESSIONS.pop(k, None)
        _SESSIONS[token] = {
            "username": username,
            "created_at": now,
            "expires_at": now + _SESSION_TTL_SECONDS,
        }
    return token


def verify_session(token: Optional[str]) -> Optional[Dict[str, Any]]:
    if not token:
        return None
    now = time.time()
    with _SESSIONS_LOCK:
        sess = _SESSIONS.get(token)
        if not sess:
            return None
        if sess["expires_at"] < now:
            _SESSIONS.pop(token, None)
            return None
        return dict(sess)


def destroy_session(token: Optional[str]) -> bool:
    if not token:
        return False
    with _SESSIONS_LOCK:
        return _SESSIONS.pop(token, None) is not None


def destroy_all_sessions() -> None:
    with _SESSIONS_LOCK:
        _SESSIONS.clear()


def account_status(session_token: Optional[str] = None) -> Dict[str, Any]:
    acc = load_account()
    has_acc = bool(acc.get("username") and acc.get("password_hash"))
    req_login = bool(has_acc and acc.get("require_login", False))
    sess = verify_session(session_token)
    authenticated = bool(sess and sess.get("username") == acc.get("username")) if has_acc else False
    locked = req_login and not authenticated
    return {
        "has_account": has_acc,
        "require_login": req_login,
        "authenticated": authenticated,
        "locked": locked,
        "account": _public_account_view(acc),
        "account_path": str(account_path()),
    }


def register_account(
    username: str,
    password: str,
    *,
    display_name: str = "",
    email: str = "",
    require_login: bool = False,
) -> Tuple[Dict[str, Any], str]:
    uname = (username or "").strip()
    if len(uname) < 2:
        raise ValueError("Tên đăng nhập phải có ít nhất 2 ký tự.")
    if len(password or "") < 4:
        raise ValueError("Mật khẩu phải có ít nhất 4 ký tự.")
    salt_hex, hash_hex = _hash_password(password)
    now_iso = now_utc_iso()
    record = {
        "username": uname,
        "display_name": (display_name or uname).strip(),
        "email": (email or "").strip(),
        "require_login": bool(require_login),
        "password_salt": salt_hex,
        "password_hash": hash_hex,
        "created_utc": now_iso,
        "last_login_utc": now_iso,
    }
    _write_secret_json(account_path(), record)
    destroy_all_sessions()
    token = create_session(uname)
    return _public_account_view(record) or {}, token


def authenticate_account(username: str, password: str) -> Tuple[bool, str, Optional[str]]:
    acc = load_account()
    if not acc.get("username") or not acc.get("password_hash"):
        return False, "Chưa có tài khoản KAS nào được tạo trên máy này.", None
    uname = (username or "").strip()
    if uname.lower() != str(acc["username"]).lower():
        return False, "Tên đăng nhập không đúng.", None
    if not _verify_password(password or "", str(acc.get("password_salt", "")), str(acc.get("password_hash", ""))):
        return False, "Mật khẩu không đúng.", None
    acc["last_login_utc"] = now_utc_iso()
    _write_secret_json(account_path(), acc)
    token = create_session(str(acc["username"]))
    return True, "Đăng nhập thành công.", token


def update_account_profile(
    *,
    display_name: Optional[str] = None,
    email: Optional[str] = None,
    require_login: Optional[bool] = None,
) -> Dict[str, Any]:
    acc = load_account()
    if not acc.get("username"):
        raise ValueError("Chưa có tài khoản KAS. Hãy đăng ký tài khoản trước.")
    if display_name is not None and display_name.strip():
        acc["display_name"] = display_name.strip()
    if email is not None:
        acc["email"] = email.strip()
    if require_login is not None:
        acc["require_login"] = bool(require_login)
    _write_secret_json(account_path(), acc)
    return _public_account_view(acc) or {}


def change_account_password(old_password: str, new_password: str) -> None:
    acc = load_account()
    if not acc.get("username"):
        raise ValueError("Chưa có tài khoản KAS.")
    if not _verify_password(old_password or "", str(acc.get("password_salt", "")), str(acc.get("password_hash", ""))):
        raise ValueError("Mật khẩu hiện tại không chính xác.")
    if len(new_password or "") < 4:
        raise ValueError("Mật khẩu mới phải có ít nhất 4 ký tự.")
    salt_hex, hash_hex = _hash_password(new_password)
    acc["password_salt"] = salt_hex
    acc["password_hash"] = hash_hex
    _write_secret_json(account_path(), acc)


def delete_account(password: str = "") -> bool:
    acc = load_account()
    if not acc.get("username"):
        return False
    if acc.get("password_hash") and not _verify_password(
        password or "", str(acc.get("password_salt", "")), str(acc.get("password_hash", ""))
    ):
        raise ValueError("Mật khẩu xác nhận không đúng.")
    p = account_path()
    if p.exists():
        p.unlink()
    destroy_all_sessions()
    return True


# ==================== KẾT NỐI DỊCH VỤ BÊN THỨ 3 ====================


def _load_integrations() -> Dict[str, Any]:
    data = _read_json_dict(integrations_path())
    data.setdefault("github", {})
    data.setdefault("connectors", [])
    return data


def _save_integrations(data: Dict[str, Any]) -> Path:
    return _write_secret_json(integrations_path(), data)


def save_google_credentials_json(raw_json_or_path: str) -> Dict[str, Any]:
    """Lưu tệp `credentials.json` OAuth 2.0 (chấp nhận dán JSON trực tiếp hoặc đường dẫn tệp trên máy)."""
    raw = (raw_json_or_path or "").strip()
    if not raw:
        raise ValueError("Vui lòng dán nội dung JSON hoặc chọn tệp `credentials.json` từ Google Cloud Console.")
    if raw.startswith("{"):
        text = raw
    else:
        src = Path(raw).expanduser()
        if not src.is_file():
            raise ValueError(f"Không tìm thấy tệp credentials tại: `{src}`")
        text = src.read_text(encoding="utf-8")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Nội dung `credentials.json` không phải JSON hợp lệ: {exc}") from exc
    if not isinstance(parsed, dict) or ("installed" not in parsed and "web" not in parsed):
        raise ValueError("Tệp `credentials.json` không đúng chuẩn Google OAuth Client (thiếu khóa `installed` hoặc `web`).")
    client_block = parsed.get("installed") or parsed.get("web") or {}
    if not client_block.get("client_id"):
        raise ValueError("Thiếu trường `client_id` trong `credentials.json`.")
    dest = _cfg.oauth_credentials_path()
    _write_secret_json(dest, parsed)
    return {
        "ok": True,
        "credentials_path": str(dest),
        "client_id_masked": _mask_secret(str(client_block.get("client_id", ""))),
        "project_id": str(client_block.get("project_id", "")),
    }


def start_google_oauth_login_async(open_browser: bool = True) -> Dict[str, Any]:
    """Khởi chạy luồng đăng nhập Google Drive OAuth 2.0 trong luồng nền (mở trình duyệt xác thực Google)."""
    st = auth_status()
    if not st["libs_installed"]:
        return {
            "ok": False,
            "status": "error",
            "message": "Thiếu thư viện Google Drive API. Hãy cài bằng: pip install google-api-python-client google-auth-oauthlib",
        }
    if not st["credentials_exists"]:
        return {
            "ok": False,
            "status": "error",
            "message": f"Chưa có tệp credentials.json tại {st['credentials_path']}. Hãy tải lên hoặc dán credentials.json trước.",
        }
    with _GOOGLE_OAUTH_LOCK:
        if _GOOGLE_OAUTH_STATE["status"] == "running":
            return {"ok": True, **dict(_GOOGLE_OAUTH_STATE)}
        _GOOGLE_OAUTH_STATE.update(
            {
                "status": "running",
                "message": "Đã mở trình duyệt đăng nhập Google OAuth 2.0 — vui lòng chọn tài khoản Google và cấp quyền...",
                "started_utc": now_utc_iso(),
                "finished_utc": "",
            }
        )

    def _worker() -> None:
        try:
            tpath = auth_login(open_browser=open_browser)
            with _GOOGLE_OAUTH_LOCK:
                _GOOGLE_OAUTH_STATE.update(
                    {
                        "status": "done",
                        "message": f"Đăng nhập Google Drive OAuth 2.0 thành công! Đã lưu token tại {tpath}.",
                        "finished_utc": now_utc_iso(),
                    }
                )
        except Exception as exc:
            with _GOOGLE_OAUTH_LOCK:
                _GOOGLE_OAUTH_STATE.update(
                    {
                        "status": "error",
                        "message": f"Lỗi đăng nhập Google Drive: {exc}",
                        "finished_utc": now_utc_iso(),
                    }
                )

    threading.Thread(target=_worker, daemon=True).start()
    return {"ok": True, **dict(_GOOGLE_OAUTH_STATE)}


def get_google_oauth_login_state() -> Dict[str, Any]:
    with _GOOGLE_OAUTH_LOCK:
        state = dict(_GOOGLE_OAUTH_STATE)
    state["auth"] = auth_status()
    return state


def disconnect_google_drive() -> Dict[str, Any]:
    removed = auth_logout()
    with _GOOGLE_OAUTH_LOCK:
        _GOOGLE_OAUTH_STATE.update({"status": "idle", "message": "Đã đăng xuất Google Drive.", "finished_utc": now_utc_iso()})
    return {"ok": True, "removed": removed, "auth": auth_status()}


def connect_github_token(token: str, *, verify: bool = True) -> Dict[str, Any]:
    """Kết nối tài khoản GitHub bằng Personal Access Token (kiểm chứng trực tiếp qua GitHub API)."""
    tok = (token or "").strip()
    if len(tok) < 8:
        raise ValueError("GitHub Personal Access Token quá ngắn hoặc không hợp lệ.")
    user_info: Dict[str, Any] = {"login": "", "name": "", "html_url": "", "scopes": ""}
    if verify:
        req = urllib.request.Request(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {tok}",
                "User-Agent": f"{APP_SHORT}/{__version__}",
                "Accept": "application/vnd.github+json",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                user_info["login"] = str(body.get("login") or "")
                user_info["name"] = str(body.get("name") or user_info["login"])
                user_info["html_url"] = str(body.get("html_url") or "")
                user_info["scopes"] = str(resp.headers.get("X-OAuth-Scopes") or "")
        except urllib.error.HTTPError as exc:
            raise ValueError(f"Token GitHub không hợp lệ hoặc bị từ chối (HTTP {exc.code}).") from exc
        except Exception as exc:
            raise ValueError(f"Không thể xác thực với GitHub API: {exc}") from exc

    data = _load_integrations()
    data["github"] = {
        "token": tok,
        "login": user_info["login"],
        "name": user_info["name"],
        "html_url": user_info["html_url"],
        "scopes": user_info["scopes"],
        "connected_utc": now_utc_iso(),
    }
    _save_integrations(data)
    return get_github_integration_status()


def disconnect_github() -> Dict[str, Any]:
    data = _load_integrations()
    data["github"] = {}
    _save_integrations(data)
    return get_github_integration_status()


def get_saved_github_token() -> str:
    data = _load_integrations()
    return str((data.get("github") or {}).get("token") or os.environ.get("GITHUB_TOKEN") or "")


def get_github_integration_status() -> Dict[str, Any]:
    data = _load_integrations()
    gh_saved = data.get("github") or {}
    has_pat = bool(gh_saved.get("token"))
    gh_cli_bin = shutil.which("gh") or ""
    gh_cli_logged_in = False
    gh_cli_user = ""
    if gh_cli_bin and not has_pat:
        try:
            proc = subprocess.run([gh_cli_bin, "api", "user", "--jq", ".login"], capture_output=True, text=True, timeout=3)
            if proc.returncode == 0 and proc.stdout.strip():
                gh_cli_logged_in = True
                gh_cli_user = proc.stdout.strip()
        except Exception:
            pass
    return {
        "connected": has_pat or gh_cli_logged_in,
        "method": "pat" if has_pat else ("gh_cli" if gh_cli_logged_in else "none"),
        "login": str(gh_saved.get("login") or gh_cli_user),
        "name": str(gh_saved.get("name") or gh_cli_user),
        "html_url": str(gh_saved.get("html_url") or ""),
        "token_masked": _mask_secret(str(gh_saved.get("token") or "")),
        "connected_utc": str(gh_saved.get("connected_utc") or ""),
        "gh_cli_installed": bool(gh_cli_bin),
    }


def add_custom_connector(
    name: str,
    kind: str,
    endpoint_url: str,
    *,
    api_key: str = "",
    notes: str = "",
) -> List[Dict[str, Any]]:
    nm = (name or "").strip()
    url = (endpoint_url or "").strip()
    if not nm or not url:
        raise ValueError("Cần nhập đầy đủ tên kết nối và đường dẫn Endpoint URL.")
    data = _load_integrations()
    connectors = [c for c in (data.get("connectors") or []) if c.get("name") != nm]
    connectors.append(
        {
            "name": nm,
            "kind": (kind or "webhook").strip(),
            "endpoint_url": url,
            "api_key": (api_key or "").strip(),
            "notes": (notes or "").strip(),
            "added_utc": now_utc_iso(),
        }
    )
    data["connectors"] = connectors
    _save_integrations(data)
    return list_custom_connectors()


def remove_custom_connector(name: str) -> List[Dict[str, Any]]:
    data = _load_integrations()
    data["connectors"] = [c for c in (data.get("connectors") or []) if c.get("name") != name]
    _save_integrations(data)
    return list_custom_connectors()


def list_custom_connectors() -> List[Dict[str, Any]]:
    data = _load_integrations()
    out: List[Dict[str, Any]] = []
    for c in data.get("connectors") or []:
        out.append(
            {
                "name": c.get("name", ""),
                "kind": c.get("kind", "webhook"),
                "endpoint_url": c.get("endpoint_url", ""),
                "has_api_key": bool(c.get("api_key")),
                "api_key_masked": _mask_secret(str(c.get("api_key") or "")),
                "notes": c.get("notes", ""),
                "added_utc": c.get("added_utc", ""),
            }
        )
    return out


def get_all_integrations_summary() -> Dict[str, Any]:
    from karius_academic_system.ai import load_ai_config

    ai_cfg = load_ai_config()
    return {
        "google_drive": get_google_oauth_login_state(),
        "github": get_github_integration_status(),
        "ai_provider": ai_cfg.masked_dict(),
        "connectors": list_custom_connectors(),
    }
