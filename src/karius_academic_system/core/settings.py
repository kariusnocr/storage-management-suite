"""Quản lý Cài đặt Phần mềm (`~/.config/kas/app_settings.json`) & Kiểm tra cập nhật cho Karius Academic System (KAS)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Tuple

from karius_academic_system import APP_NAME, APP_SHORT, __version__
from karius_academic_system.core import config as _cfg

VALID_THEMES = ("dark", "light")
VALID_LANGUAGES = ("vi", "en")
VALID_DEFAULT_TABS = ("vaults", "overview", "explorer", "search", "console", "rules", "ai", "account", "settings")
VALID_BACKENDS = ("auto", "api", "cli", "local")
VALID_CATALOG_MODES = ("smart", "full")
VALID_UPDATE_CHANNELS = ("stable", "prerelease")


@dataclass
class AppSettings:
    """Cấu hình toàn ứng dụng của Karius Academic System (KAS)."""

    theme: str = "dark"
    language: str = "vi"
    default_tab: str = "vaults"
    drive_backend: str = "auto"
    scan_workers: int = 32
    scan_incremental_default: bool = True
    catalog_default_mode: str = "smart"
    ui_host: str = "127.0.0.1"
    ui_port: int = 8765
    open_browser_on_start: bool = True
    data_dir_override: str = ""
    github_repo: str = "kariusnocr/storage-management-suite"
    auto_check_updates: bool = True
    auto_install_updates: bool = False
    update_channel: str = "stable"
    update_check_interval_hours: int = 6

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppSettings":
        base = asdict(cls())
        for k, v in (data or {}).items():
            if k in base:
                base[k] = v
        if base["theme"] not in VALID_THEMES:
            base["theme"] = "dark"
        if base["language"] not in VALID_LANGUAGES:
            base["language"] = "vi"
        if base["default_tab"] not in VALID_DEFAULT_TABS:
            base["default_tab"] = "vaults"
        if base["drive_backend"] not in VALID_BACKENDS:
            base["drive_backend"] = "auto"
        if base["catalog_default_mode"] not in VALID_CATALOG_MODES:
            base["catalog_default_mode"] = "smart"
        if base["update_channel"] not in VALID_UPDATE_CHANNELS:
            base["update_channel"] = "stable"
        try:
            base["scan_workers"] = max(1, min(64, int(base["scan_workers"])))
        except (TypeError, ValueError):
            base["scan_workers"] = 32
        try:
            base["ui_port"] = max(1024, min(65535, int(base["ui_port"])))
        except (TypeError, ValueError):
            base["ui_port"] = 8765
        try:
            base["update_check_interval_hours"] = max(1, min(168, int(base["update_check_interval_hours"])))
        except (TypeError, ValueError):
            base["update_check_interval_hours"] = 6
        base["scan_incremental_default"] = bool(base["scan_incremental_default"])
        base["open_browser_on_start"] = bool(base["open_browser_on_start"])
        base["auto_check_updates"] = bool(base["auto_check_updates"])
        base["auto_install_updates"] = bool(base["auto_install_updates"])
        base["ui_host"] = str(base.get("ui_host") or "127.0.0.1").strip() or "127.0.0.1"
        base["data_dir_override"] = str(base.get("data_dir_override") or "").strip()
        base["github_repo"] = str(base.get("github_repo") or "kariusnocr/storage-management-suite").strip()
        return cls(**base)


def app_settings_path() -> Path:
    return _cfg.user_config_dir() / "app_settings.json"


def load_app_settings() -> AppSettings:
    p = app_settings_path()
    if p.exists():
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return AppSettings.from_dict(raw)
        except Exception:
            pass
    return AppSettings()


def save_app_settings(settings: AppSettings) -> Path:
    p = app_settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(settings.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)
    # Áp dụng ngay vào ngữ cảnh động của KAS
    if settings.drive_backend and settings.drive_backend != "auto":
        os.environ["KAS_BACKEND"] = settings.drive_backend
    else:
        os.environ.pop("KAS_BACKEND", None)
    _cfg.reload_config()
    return p


def reset_app_settings() -> AppSettings:
    p = app_settings_path()
    if p.exists():
        p.unlink()
    os.environ.pop("KAS_BACKEND", None)
    _cfg.reload_config()
    return AppSettings()


def _parse_semver(ver: str) -> Tuple[int, ...]:
    cleaned = (ver or "").strip().lstrip("vV")
    parts = []
    for seg in cleaned.split("."):
        digits = "".join(ch for ch in seg if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts or [0])


def check_latest_release(repo: str = "", github_token: str = "", timeout: int = 8) -> Dict[str, Any]:
    """Kiểm tra phiên bản KAS mới nhất trực tiếp từ GitHub Releases API (thuần Python stdlib)."""
    settings = load_app_settings()
    target_repo = (repo or settings.github_repo or "kariusnocr/storage-management-suite").strip()
    url = f"https://api.github.com/repos/{target_repo}/releases/latest"
    headers = {"User-Agent": f"{APP_SHORT}/{__version__}", "Accept": "application/vnd.github+json"}
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        latest_tag = str(data.get("tag_name") or "").strip()
        latest_ver = latest_tag.lstrip("vV")
        update_available = _parse_semver(latest_ver) > _parse_semver(__version__)
        return {
            "ok": True,
            "repo": target_repo,
            "current_version": __version__,
            "latest_version": latest_ver or __version__,
            "latest_tag": latest_tag,
            "release_name": str(data.get("name") or latest_tag),
            "release_url": str(data.get("html_url") or f"https://github.com/{target_repo}/releases"),
            "published_at": str(data.get("published_at") or ""),
            "update_available": update_available,
            "powershell_update_cmd": f"irm https://raw.githubusercontent.com/{target_repo}/main/packaging/windows/install_windows_sac_safe.ps1 | iex",
        }
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "repo": target_repo,
            "current_version": __version__,
            "error": f"GitHub API trả về HTTP {exc.code}",
        }
    except Exception as exc:
        return {
            "ok": False,
            "repo": target_repo,
            "current_version": __version__,
            "error": f"Không thể kiểm tra cập nhật: {exc}",
        }


def get_system_paths_info() -> Dict[str, Any]:
    """Trả về thông tin đường dẫn cấu hình/dữ liệu để hiển thị trong màn hình Cài đặt."""
    return {
        "app_name": APP_NAME,
        "app_short": APP_SHORT,
        "version": __version__,
        "config_dir": str(_cfg.user_config_dir()),
        "settings_file": str(app_settings_path()),
        "vaults_file": str(_cfg.vaults_path()),
        "active_data_dir": str(_cfg.data_dir()),
        "active_db_file": str(_cfg.db_path()),
        "oauth_credentials_file": str(_cfg.oauth_credentials_path()),
        "oauth_token_file": str(_cfg.oauth_token_path()),
    }
