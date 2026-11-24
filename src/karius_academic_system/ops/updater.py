"""Cơ chế Tự Động Cập Nhật Phần Mềm (Auto-Updater) có kiểm chứng SHA-256, lịch sử, hoàn tác phiên bản & tự khởi động lại (`kas update`)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from karius_academic_system import APP_NAME, APP_SHORT, __version__
from karius_academic_system import core as sc

WINDOWS_UNINSTALL_REG_SUBKEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\KariusAcademicSystem"

_UPDATE_LOCK = threading.Lock()
_UPDATE_JOBS: Dict[str, Dict[str, Any]] = {}


def _build_ssl_context() -> ssl.SSLContext:
    """Tạo SSLContext tương thích cả Desktop lẫn Android 8–16 (Chaquopy / Conscrypt APEX / certifi)."""
    try:
        from karius_academic_system.web import android_bridge

        android_bridge.configure_android_ssl_certs()
    except Exception:
        pass

    cafile: Optional[str] = None
    capath: Optional[str] = None
    try:
        import certifi  # type: ignore

        c = certifi.where()
        if c and os.path.isfile(c):
            cafile = c
    except Exception:
        pass

    if not cafile:
        env_file = (os.environ.get("SSL_CERT_FILE") or "").strip()
        if env_file and os.path.isfile(env_file):
            cafile = env_file

    for d in (
        (os.environ.get("SSL_CERT_DIR") or "").strip(),
        "/apex/com.android.conscrypt/cacerts",
        "/system/etc/security/cacerts",
    ):
        if d and os.path.isdir(d):
            capath = d
            break

    try:
        ctx = ssl.create_default_context(cafile=cafile, capath=capath)
        if capath and cafile:
            try:
                ctx.load_verify_locations(capath=capath)
            except Exception:
                pass
        return ctx
    except Exception:
        return ssl.create_default_context()


def _urlopen(req: urllib.request.Request, *, timeout: int = 30):
    """Mở kết nối HTTP/HTTPS kèm SSLContext tương thích Android 8–16 (và an toàn với mock thử nghiệm)."""
    try:
        return urllib.request.urlopen(req, timeout=timeout, context=_build_ssl_context())
    except TypeError as exc:
        if "context" in str(exc):
            return urllib.request.urlopen(req, timeout=timeout)
        raise


def update_state_path() -> Path:
    return sc.user_config_dir() / "update_state.json"


def update_staging_dir() -> Path:
    p = Path.home() / ".local" / "share" / "kas" / "updates"
    if os.environ.get("KAS_DATA_DIR"):
        p = Path(os.environ["KAS_DATA_DIR"]).expanduser() / "updates"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _parse_semver(ver: str) -> Tuple[int, ...]:
    cleaned = (ver or "").strip().lstrip("vV")
    main_part = cleaned.split("-", 1)[0]
    parts: List[int] = []
    for seg in main_part.split("."):
        digits = "".join(ch for ch in seg if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts or [0])


def load_update_state() -> Dict[str, Any]:
    p = update_state_path()
    if p.exists():
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                raw.setdefault("history", [])
                return raw
        except Exception:
            pass
    return {
        "last_checked_ts": 0.0,
        "last_checked_utc": "",
        "skipped_version": "",
        "last_check": None,
        "history": [],
    }


def save_update_state(state: Dict[str, Any]) -> Path:
    p = update_state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)
    return p


def _github_headers(token: str = "", accept: str = "application/vnd.github+json") -> Dict[str, str]:
    headers = {"User-Agent": f"{APP_SHORT}/{__version__}", "Accept": accept}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _extract_release_info(data: Dict[str, Any], repo: str) -> Dict[str, Any]:
    tag = str(data.get("tag_name") or "").strip()
    latest_ver = tag.lstrip("vV")
    assets = data.get("assets") if isinstance(data.get("assets"), list) else []

    wheel_asset: Optional[Dict[str, Any]] = None
    apk_asset: Optional[Dict[str, Any]] = None
    sha_asset: Optional[Dict[str, Any]] = None
    for a in assets:
        name = str(a.get("name") or "")
        if name.startswith("karius_academic_system-") and name.endswith(".whl"):
            wheel_asset = {
                "name": name,
                "url": str(a.get("browser_download_url") or ""),
                "api_url": str(a.get("url") or ""),
                "size": int(a.get("size") or 0),
            }
        elif name.endswith(".apk") and "kas" in name.lower():
            apk_asset = {
                "name": name,
                "url": str(a.get("browser_download_url") or ""),
                "api_url": str(a.get("url") or ""),
                "size": int(a.get("size") or 0),
            }
        elif name == "SHA256SUMS.txt":
            sha_asset = {
                "name": name,
                "url": str(a.get("browser_download_url") or ""),
                "api_url": str(a.get("url") or ""),
                "size": int(a.get("size") or 0),
            }

    update_available = bool(latest_ver) and (_parse_semver(latest_ver) > _parse_semver(__version__))
    notes = str(data.get("body") or "").strip()
    if len(notes) > 4000:
        notes = notes[:4000] + "\n..."

    return {
        "ok": True,
        "repo": repo,
        "current_version": __version__,
        "latest_version": latest_ver or __version__,
        "latest_tag": tag,
        "release_name": str(data.get("name") or tag),
        "release_url": str(data.get("html_url") or f"https://github.com/{repo}/releases"),
        "published_at": str(data.get("published_at") or ""),
        "prerelease": bool(data.get("prerelease", False)),
        "release_notes": notes,
        "wheel_asset": wheel_asset,
        "apk_asset": apk_asset,
        "sha256sums_asset": sha_asset,
        "update_available": update_available,
        "powershell_update_cmd": (
            f"irm https://raw.githubusercontent.com/{repo}/main/packaging/windows/install_windows_sac_safe.ps1 | iex"
        ),
    }


def fetch_release_metadata(
    *,
    repo: str = "",
    tag: str = "",
    channel: str = "",
    github_token: str = "",
    timeout: int = 12,
) -> Dict[str, Any]:
    """Tải siêu dữ liệu bản phát hành từ GitHub Releases API (ổn định, thử nghiệm hoặc tag cụ thể)."""
    st = sc.load_app_settings()
    target_repo = (repo or st.github_repo or "kariusnocr/storage-management-suite").strip()
    eff_channel = (channel or st.update_channel or "stable").strip().lower()
    tok = github_token or sc.get_saved_github_token()

    if tag:
        clean_tag = tag if tag.startswith("v") else f"v{tag}"
        url = f"https://api.github.com/repos/{target_repo}/releases/tags/{clean_tag}"
    elif eff_channel == "prerelease":
        url = f"https://api.github.com/repos/{target_repo}/releases?per_page=10"
    else:
        url = f"https://api.github.com/repos/{target_repo}/releases/latest"

    req = urllib.request.Request(url, headers=_github_headers(tok), method="GET")
    try:
        with _urlopen(req, timeout=timeout) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        if isinstance(raw, list):
            published = [r for r in raw if isinstance(r, dict) and not r.get("draft")]
            if not published:
                return {
                    "ok": False,
                    "repo": target_repo,
                    "current_version": __version__,
                    "error": "Không tìm thấy bản phát hành nào trên kho GitHub.",
                }
            data = published[0]
        elif isinstance(raw, dict):
            data = raw
        else:
            return {
                "ok": False,
                "repo": target_repo,
                "current_version": __version__,
                "error": "Phản hồi GitHub API không hợp lệ.",
            }
        return _extract_release_info(data, target_repo)
    except urllib.error.HTTPError as exc:
        err = f"GitHub API trả về HTTP {exc.code}"
        sc.record_event("ERROR", "updater", err, detail=url, source="updater")
        return {
            "ok": False,
            "repo": target_repo,
            "current_version": __version__,
            "error": err,
        }
    except Exception as exc:
        err = f"Không thể kết nối máy chủ cập nhật: {exc}"
        sc.record_exception("updater", exc, message=err, source="updater", meta={"url": url})
        return {
            "ok": False,
            "repo": target_repo,
            "current_version": __version__,
            "error": err,
        }


def check_for_updates(
    *,
    force: bool = False,
    repo: str = "",
    channel: str = "",
    timeout: int = 10,
) -> Dict[str, Any]:
    """Kiểm tra phiên bản mới (có bộ đệm chu kỳ theo `AppSettings.update_check_interval_hours`)."""
    st = sc.load_app_settings()
    state = load_update_state()
    now_ts = time.time()
    interval_sec = max(3600, int(st.update_check_interval_hours) * 3600)

    cached = state.get("last_check")
    if (
        not force
        and not repo
        and not channel
        and isinstance(cached, dict)
        and cached.get("ok")
        and (now_ts - float(state.get("last_checked_ts") or 0.0)) < interval_sec
    ):
        res = dict(cached)
        res["current_version"] = __version__
        res["update_available"] = _parse_semver(str(res.get("latest_version") or "")) > _parse_semver(__version__)
        res["from_cache"] = True
    else:
        res = fetch_release_metadata(repo=repo, channel=channel, timeout=timeout)
        res["from_cache"] = False
        if res.get("ok"):
            state["last_checked_ts"] = now_ts
            state["last_checked_utc"] = sc.now_utc_iso()
            state["last_check"] = res
            save_update_state(state)

    skipped_ver = str(state.get("skipped_version") or "")
    try:
        from karius_academic_system.web import android_bridge

        flavor = android_bridge.detect_runtime_flavor()
    except Exception:
        flavor = "desktop_host"

    res["last_checked_utc"] = str(state.get("last_checked_utc") or "")
    res["skipped_version"] = skipped_ver
    res["is_skipped"] = bool(skipped_ver and skipped_ver == str(res.get("latest_version") or ""))
    res["runtime_flavor"] = flavor
    res["is_android_apk"] = flavor == "chaquopy_apk"
    res["auto_check_updates"] = st.auto_check_updates
    res["auto_install_updates"] = st.auto_install_updates
    res["update_channel"] = st.update_channel
    res["history"] = list(reversed(state.get("history") or []))[:15]
    return res


def skip_update_version(version: str) -> Dict[str, Any]:
    """Đánh dấu bỏ qua thông báo cho một phiên bản cụ thể (vẫn có thể cập nhật thủ công bất cứ lúc nào)."""
    clean = (version or "").strip().lstrip("vV")
    state = load_update_state()
    state["skipped_version"] = clean
    save_update_state(state)
    return {"ok": True, "skipped_version": clean}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().lower()


def parse_sha256sums(text: str) -> Dict[str, str]:
    """Phân tích tệp `SHA256SUMS.txt` chuẩn GNU (`<64-hex>  <filename>`)."""
    mapping: Dict[str, str] = {}
    for line in (text or "").splitlines():
        ln = line.strip()
        if not ln or ln.startswith("#"):
            continue
        parts = ln.split()
        if len(parts) >= 2 and len(parts[0]) == 64:
            fname = Path(parts[-1].lstrip("*")).name
            mapping[fname] = parts[0].lower()
    return mapping


def _download_bytes(url: str, *, token: str = "", is_api_asset: bool = False, timeout: int = 60) -> bytes:
    accept = "application/octet-stream" if is_api_asset else "*/*"
    req = urllib.request.Request(url, headers=_github_headers(token, accept=accept), method="GET")
    with _urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _download_to_file(
    url: str,
    dest_path: Path,
    *,
    token: str = "",
    is_api_asset: bool = False,
    timeout: int = 180,
) -> Tuple[int, str]:
    """Tải luồng tệp lớn (vd: `kas-android.apk` ~34 MB) trực tiếp ra đĩa theo khối 128 KB, đồng thời tính SHA-256."""
    accept = "application/octet-stream" if is_api_asset else "*/*"
    req = urllib.request.Request(url, headers=_github_headers(token, accept=accept), method="GET")
    hasher = hashlib.sha256()
    total = 0
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with _urlopen(req, timeout=timeout) as resp:
        with open(dest_path, "wb") as out_f:
            while True:
                chunk = resp.read(131072)
                if not chunk:
                    break
                out_f.write(chunk)
                hasher.update(chunk)
                total += len(chunk)
    return total, hasher.hexdigest().lower()


def _verify_asset_sha256(
    release_info: Dict[str, Any],
    asset_name: str,
    actual_sha: str,
    *,
    token: str = "",
    emit: Callable[[str], None],
) -> Tuple[str, bool]:
    expected_sha = ""
    sha_verified = False
    sha_asset = release_info.get("sha256sums_asset")
    if isinstance(sha_asset, dict) and (sha_asset.get("url") or sha_asset.get("api_url")):
        emit("  🔐 Đang kiểm chứng toàn vẹn mật mã SHA-256 từ SHA256SUMS.txt...")
        try:
            sha_url = str(sha_asset.get("url") or "")
            try:
                sha_bytes = _download_bytes(sha_url, token="", is_api_asset=False, timeout=30)
            except Exception:
                if token and sha_asset.get("api_url"):
                    sha_bytes = _download_bytes(str(sha_asset["api_url"]), token=token, is_api_asset=True, timeout=30)
                else:
                    raise
            sums = parse_sha256sums(sha_bytes.decode("utf-8", errors="replace"))
            expected_sha = sums.get(asset_name, "")
            if expected_sha:
                if expected_sha != actual_sha:
                    raise RuntimeError(
                        f"KIỂM CHỨNG SHA-256 THẤT BẠI cho {asset_name}! "
                        f"Kỳ vọng={expected_sha[:16]}... | Thực tế={actual_sha[:16]}... — Đã hủy cài đặt để bảo vệ an toàn."
                    )
                sha_verified = True
                emit(f"  ✓ Khớp 100% SHA-256 ({actual_sha[:16]}...)")
        except RuntimeError:
            raise
        except Exception as exc:
            emit(f"  ⚠ Không tải được SHA256SUMS.txt ({exc}) — tiếp tục với tệp từ GitHub HTTPS.")
    return expected_sha, sha_verified


def download_and_verify_wheel(
    release_info: Dict[str, Any],
    *,
    github_token: str = "",
    log_cb: Optional[Callable[[str], None]] = None,
) -> Tuple[Path, Dict[str, Any]]:
    """Tải gói `.whl` từ GitHub Release và kiểm chứng băm mật mã `SHA256SUMS.txt` trước khi cài đặt."""
    emit = log_cb or (lambda _m: None)
    whl = release_info.get("wheel_asset")
    if not isinstance(whl, dict) or not whl.get("name"):
        raise RuntimeError("Bản phát hành không chứa gói cài đặt `.whl` (`karius_academic_system-*.whl`).")

    tok = github_token or sc.get_saved_github_token()
    tag = str(release_info.get("latest_tag") or f"v{release_info.get('latest_version', 'latest')}")
    stage_dir = update_staging_dir() / tag
    stage_dir.mkdir(parents=True, exist_ok=True)
    dest_whl = stage_dir / str(whl["name"])

    dl_url = str(whl.get("url") or "")
    api_url = str(whl.get("api_url") or "")
    emit(f"  ↓ Đang tải {whl['name']} ({sc.human_size(int(whl.get('size') or 0))})...")
    try:
        raw_whl = _download_bytes(dl_url, token="", is_api_asset=False, timeout=90)
    except Exception:
        if tok and api_url:
            raw_whl = _download_bytes(api_url, token=tok, is_api_asset=True, timeout=90)
        else:
            raise

    if len(raw_whl) < 10_000:
        raise RuntimeError(f"Gói tải về có kích thước bất thường ({len(raw_whl)} bytes).")

    actual_sha = _sha256_bytes(raw_whl)
    expected_sha, sha_verified = _verify_asset_sha256(
        release_info,
        str(whl["name"]),
        actual_sha,
        token=tok,
        emit=emit,
    )

    tmp = dest_whl.with_suffix(".whl.tmp")
    tmp.write_bytes(raw_whl)
    tmp.replace(dest_whl)

    return dest_whl, {
        "wheel_path": str(dest_whl),
        "wheel_name": str(whl["name"]),
        "size_bytes": len(raw_whl),
        "sha256": actual_sha,
        "expected_sha256": expected_sha,
        "sha256_verified": sha_verified,
    }


def download_and_verify_apk(
    release_info: Dict[str, Any],
    *,
    github_token: str = "",
    log_cb: Optional[Callable[[str], None]] = None,
) -> Tuple[Path, Dict[str, Any]]:
    """Tải luồng gói `kas-android.apk` từ GitHub Release và kiểm chứng SHA-256 cho cập nhật gốc trên Android."""
    emit = log_cb or (lambda _m: None)
    apk = release_info.get("apk_asset")
    if not isinstance(apk, dict) or not apk.get("name"):
        raise RuntimeError("Bản phát hành chưa đính kèm tệp cài đặt Android (`kas-android.apk`).")

    tok = github_token or sc.get_saved_github_token()
    tag = str(release_info.get("latest_tag") or f"v{release_info.get('latest_version', 'latest')}")
    stage_dir = update_staging_dir() / tag
    stage_dir.mkdir(parents=True, exist_ok=True)
    apk_name = str(apk["name"])
    dest_apk = stage_dir / apk_name
    tmp_apk = dest_apk.with_suffix(".apk.tmp")

    dl_url = str(apk.get("url") or "")
    api_url = str(apk.get("api_url") or "")
    emit(f"  ↓ Đang tải gói Android {apk_name} ({sc.human_size(int(apk.get('size') or 0))})...")
    try:
        try:
            size_bytes, actual_sha = _download_to_file(dl_url, tmp_apk, token="", is_api_asset=False, timeout=240)
        except Exception:
            if tok and api_url:
                size_bytes, actual_sha = _download_to_file(api_url, tmp_apk, token=tok, is_api_asset=True, timeout=240)
            else:
                raise

        if size_bytes < 100_000:
            raise RuntimeError(f"Gói APK tải về có kích thước bất thường ({size_bytes} bytes).")

        expected_sha, sha_verified = _verify_asset_sha256(
            release_info,
            apk_name,
            actual_sha,
            token=tok,
            emit=emit,
        )
        tmp_apk.replace(dest_apk)
    except Exception:
        tmp_apk.unlink(missing_ok=True)
        raise

    return dest_apk, {
        "apk_path": str(dest_apk),
        "apk_name": apk_name,
        "size_bytes": size_bytes,
        "sha256": actual_sha,
        "expected_sha256": expected_sha,
        "sha256_verified": sha_verified,
    }


def _in_virtualenv() -> bool:
    return bool(os.environ.get("VIRTUAL_ENV")) or (getattr(sys, "base_prefix", sys.prefix) != sys.prefix)


def _sync_windows_registry_version(new_version: str) -> bool:
    """Cập nhật số phiên bản mới trong Windows Settings -> Apps -> Installed Apps."""
    if os.name != "nt":
        return False
    try:
        import winreg  # type: ignore

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINDOWS_UNINSTALL_REG_SUBKEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, new_version)
        return True
    except OSError:
        return False
    except Exception:
        return False


def _sync_windows_desktop_shortcut() -> bool:
    """Rút gọn lối tắt Desktop cũ (`Karius Academic System (KAS).lnk`) thành `KAS.lnk` nếu tồn tại."""
    if os.name != "nt":
        return False
    changed = False
    try:
        user_prof = Path(os.environ.get("USERPROFILE") or str(Path.home()))
        for folder in (user_prof / "Desktop", user_prof / "OneDrive" / "Desktop"):
            old_lnk = folder / "Karius Academic System (KAS).lnk"
            new_lnk = folder / "KAS.lnk"
            if old_lnk.is_file():
                if new_lnk.exists():
                    old_lnk.unlink(missing_ok=True)
                else:
                    old_lnk.rename(new_lnk)
                changed = True
    except OSError:
        pass
    return changed


def apply_update(
    *,
    target_version: str = "",
    force: bool = False,
    dry_run: bool = False,
    log_cb: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Tải, xác thực SHA-256 và cài đặt bản cập nhật KAS mới nhất (hỗ trợ cả Desktop `.whl` lẫn Android `.apk`)."""
    emit = log_cb or (lambda _m: None)
    logs: List[str] = []

    def _emit(msg: str) -> None:
        logs.append(msg)
        emit(msg)

    try:
        from karius_academic_system.web import android_bridge

        runtime_flavor = android_bridge.detect_runtime_flavor()
    except Exception:
        runtime_flavor = "desktop_host"

    _emit(f"=== {APP_NAME} ({APP_SHORT}) v{__version__} — TỰ ĐỘNG CẬP NHẬT PHẦN MỀM ({runtime_flavor}) ===")
    rel = fetch_release_metadata(tag=target_version)
    if not rel.get("ok"):
        _emit(f"  ✗ {rel.get('error')}")
        sc.record_event("ERROR", "updater", f"Kiểm tra cập nhật thất bại: {rel.get('error')}", source="updater")
        return {"ok": False, "updated": False, "error": rel.get("error"), "logs": logs}

    new_ver = str(rel.get("latest_version") or "")
    is_newer = _parse_semver(new_ver) > _parse_semver(__version__)
    is_rollback = bool(target_version) and (_parse_semver(new_ver) < _parse_semver(__version__))

    if not target_version and not is_newer and not force:
        _emit(f"  ✓ Bạn đang sử dụng phiên bản mới nhất: v{__version__} ({rel.get('release_name')}).")
        return {
            "ok": True,
            "updated": False,
            "already_latest": True,
            "from_version": __version__,
            "to_version": new_ver,
            "release": rel,
            "logs": logs,
        }

    action_label = "Quay về (Rollback)" if is_rollback else "Nâng cấp"
    _emit(f"  • {action_label}: v{__version__} → v{new_ver} ({rel.get('latest_tag')})")

    if dry_run:
        _emit("  [CHẠY THỬ] Đã kiểm tra xong — không tải/cài gói thật.")
        return {
            "ok": True,
            "dry_run": True,
            "updated": False,
            "from_version": __version__,
            "to_version": new_ver,
            "release": rel,
            "logs": logs,
        }

    # LUỒNG RIÊNG CHO ỨNG DỤNG ANDROID GỐC (kas-android.apk — Chaquopy không có pip CLI)
    if runtime_flavor == "chaquopy_apk":
        try:
            apk_path, verify_meta = download_and_verify_apk(rel, log_cb=_emit)
        except Exception as exc:
            err = f"Lỗi tải / xác thực gói APK Android: {exc}"
            _emit(f"  ✗ {err}")
            sc.record_exception("updater", exc, message=err, source="updater")
            return {"ok": False, "updated": False, "platform": "android_apk", "error": err, "logs": logs}

        state = load_update_state()
        state["skipped_version"] = ""
        state["last_checked_ts"] = time.time()
        state["last_checked_utc"] = sc.now_utc_iso()
        state["last_check"] = dict(rel, update_available=False)
        history = list(state.get("history") or [])
        history.append({
            "timestamp_utc": sc.now_utc_iso(),
            "from_version": __version__,
            "to_version": new_ver,
            "tag": rel.get("latest_tag", ""),
            "sha256": verify_meta["sha256"],
            "sha256_verified": verify_meta["sha256_verified"],
            "kind": "apk_rollback" if is_rollback else "apk_upgrade",
        })
        state["history"] = history[-30:]
        save_update_state(state)

        _emit(f"  ✓ Đã tải & xác thực trọn vẹn gói cài đặt Android: {apk_path.name}!")
        _emit("  📲 Đang mở trình cài đặt gói ứng dụng của Android để nâng cấp KAS...")
        sc.record_event(
            "INFO",
            "updater",
            f"Đã tải và xác thực SHA-256 gói Android APK v{new_ver}",
            detail=str(apk_path),
            source="updater",
        )
        return {
            "ok": True,
            "updated": True,
            "platform": "android_apk",
            "requires_apk_install": True,
            "apk_path": str(apk_path),
            "apk_url": str((rel.get("apk_asset") or {}).get("url") or ""),
            "from_version": __version__,
            "to_version": new_ver,
            "release": rel,
            "verification": verify_meta,
            "logs": logs,
        }

    # LUỒNG WINDOWS / LINUX / TERMUX (.whl qua pip)
    try:
        whl_path, verify_meta = download_and_verify_wheel(rel, log_cb=_emit)
    except Exception as exc:
        err = f"Lỗi tải / xác thực bản cập nhật: {exc}"
        _emit(f"  ✗ {err}")
        sc.record_exception("updater", exc, message=err, source="updater")
        return {"ok": False, "updated": False, "error": str(exc), "logs": logs}

    from karius_academic_system.web.lifecycle import resolve_console_python

    pip_python = resolve_console_python(sys.executable)
    cmd = [pip_python, "-m", "pip", "install", "--upgrade", "--force-reinstall", "--no-deps", "--no-warn-script-location"]
    if not _in_virtualenv() and runtime_flavor != "termux":
        cmd.append("--user")
    if os.name != "nt" and not _in_virtualenv() and runtime_flavor != "termux":
        cmd.append("--break-system-packages")
    cmd.append(str(whl_path))

    _emit(f"  ⚙ Đang cài đặt gói `{whl_path.name}` vào Python ({pip_python})...")
    run_kwargs: Dict[str, Any] = {"capture_output": True, "text": True, "timeout": 180}
    if os.name == "nt":
        run_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(cmd, **run_kwargs)
        if proc.returncode != 0 and "--break-system-packages" in cmd:
            retry = [c for c in cmd if c != "--break-system-packages"]
            proc = subprocess.run(retry, **run_kwargs)
    except Exception as exc:
        err = f"Không thể gọi pip để cài đặt: {exc}"
        _emit(f"  ✗ {err}")
        sc.record_exception("updater", exc, message=err, source="updater")
        return {"ok": False, "updated": False, "error": err, "logs": logs}

    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-1:] or [f"mã lỗi {proc.returncode}"]
        err = f"Cài đặt pip thất bại: {tail[0]}"
        _emit(f"  ✗ {err}")
        sc.record_event("ERROR", "updater", err, detail=(proc.stderr or "")[-1200:], source="updater")
        return {"ok": False, "updated": False, "error": err, "logs": logs}

    if _sync_windows_registry_version(new_ver):
        _emit(f"  ✓ Đã cập nhật số phiên bản v{new_ver} trong Windows Installed Apps.")
    if _sync_windows_desktop_shortcut():
        _emit("  ✓ Đã rút gọn lối tắt Desktop thành `KAS`.")

    state = load_update_state()
    state["skipped_version"] = ""
    state["last_checked_ts"] = time.time()
    state["last_checked_utc"] = sc.now_utc_iso()
    state["last_check"] = dict(rel, update_available=False)
    history = list(state.get("history") or [])
    history.append({
        "timestamp_utc": sc.now_utc_iso(),
        "from_version": __version__,
        "to_version": new_ver,
        "tag": rel.get("latest_tag", ""),
        "sha256": verify_meta["sha256"],
        "sha256_verified": verify_meta["sha256_verified"],
        "kind": "rollback" if is_rollback else "upgrade",
    })
    state["history"] = history[-30:]
    save_update_state(state)

    _emit(f"  ✓ Cập nhật thành công: v{__version__} → v{new_ver}!")
    sc.record_event("INFO", "updater", f"Đã cập nhật KAS thành công: v{__version__} → v{new_ver}", source="updater")
    return {
        "ok": True,
        "updated": True,
        "from_version": __version__,
        "to_version": new_ver,
        "release": rel,
        "verification": verify_meta,
        "logs": logs,
    }


def _generate_windows_restart_ps1(
    wait_pid: int,
    python_exe: str,
    host: str,
    port: int,
    stdlib: bool = True,
    *,
    reopen_window: bool = False,
) -> str:
    """Sinh kịch bản PowerShell thuần 7-bit ASCII đợi/dừng máy chủ cũ rồi khởi chạy bản KAS mới trên cùng cổng."""
    py_path = Path(python_exe)
    pythonw = py_path.parent / "pythonw.exe"
    launcher = str(pythonw if pythonw.exists() else py_path).replace("'", "''")
    host_esc = str(host or "127.0.0.1").replace("'", "''")
    probe_host = "127.0.0.1" if host_esc in {"", "0.0.0.0", "::"} else host_esc
    if reopen_window:
        arg_list = ["-m", "karius_academic_system", "desktop", "--browser", "--port", str(int(port))]
    else:
        arg_list = ["-m", "karius_academic_system", "ui", "--host", host_esc, "--port", str(int(port))]
    if stdlib:
        arg_list.append("--stdlib")
    ps_args = ", ".join(f"'{a}'" for a in arg_list)
    return "\r\n".join([
        "$ErrorActionPreference = 'SilentlyContinue'",
        f"$waitPid = {int(wait_pid)}",
        "if ($waitPid -gt 0) {",
        "    try { Wait-Process -Id $waitPid -Timeout 6 -ErrorAction SilentlyContinue } catch {}",
        "    if (Get-Process -Id $waitPid -ErrorAction SilentlyContinue) {",
        "        Stop-Process -Id $waitPid -Force -ErrorAction SilentlyContinue",
        "    }",
        "}",
        "$leftover = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {",
        "    $_.ProcessId -ne $PID -and $_.CommandLine -and ($_.CommandLine -match 'karius_academic_system') -and ($_.CommandLine -match '\\b(ui|desktop)\\b')",
        "}",
        "foreach ($p in $leftover) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }",
        "for ($i = 0; $i -lt 25; $i++) {",
        "    $busy = $false",
        "    try {",
        f"        $c = New-Object System.Net.Sockets.TcpClient('{probe_host}', {int(port)})",
        "        $c.Close()",
        "        $busy = $true",
        "    } catch {}",
        "    if (-not $busy) { break }",
        "    Start-Sleep -Milliseconds 250",
        "}",
        "Start-Sleep -Milliseconds 350",
        "$env:PYTHONUTF8 = '1'",
        f"Start-Process -FilePath '{launcher}' -ArgumentList @({ps_args}) -WindowStyle Hidden",
        "Remove-Item -Path $MyInvocation.MyCommand.Path -Force -ErrorAction SilentlyContinue",
    ]) + "\r\n"


def schedule_detached_server_restart(
    host: str = "127.0.0.1",
    port: int = 8765,
    stdlib: bool = True,
    *,
    reopen_window: bool = False,
    wait_pid: Optional[int] = None,
) -> Dict[str, Any]:
    """Khởi chạy lại máy chủ KAS sau khi tiến trình hiện tại giải phóng cổng HTTP."""
    tag = uuid.uuid4().hex[:8]
    pid_to_wait = os.getpid() if wait_pid is None else int(wait_pid)
    if os.name == "nt":
        ps1 = Path(tempfile.gettempdir()) / f"kas_restart_{tag}.ps1"
        ps1.write_bytes(
            _generate_windows_restart_ps1(
                pid_to_wait,
                sys.executable,
                host,
                port,
                stdlib=stdlib,
                reopen_window=reopen_window,
            ).encode("ascii")
        )
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass", "-File", str(ps1)],
            creationflags=flags,
            close_fds=True,
        )
        return {"ok": True, "restarting": True, "script": str(ps1)}

    sh = Path(tempfile.gettempdir()) / f"kas_restart_{tag}.sh"
    flag = " --stdlib" if stdlib else ""
    if reopen_window:
        launch_cmd = f'PYTHONUTF8=1 "{sys.executable}" -m karius_academic_system desktop --browser --port {int(port)}{flag}'
    else:
        launch_cmd = f'PYTHONUTF8=1 "{sys.executable}" -m karius_academic_system ui --host "{host}" --port {int(port)}{flag}'
    lines = [
        "#!/bin/sh",
        f"WAIT_PID={int(pid_to_wait)}",
        'if [ "$WAIT_PID" -gt 0 ]; then',
        "  i=0",
        '  while [ "$i" -lt 25 ] && kill -0 "$WAIT_PID" 2>/dev/null; do',
        "    sleep 0.25",
        "    i=$((i + 1))",
        "  done",
        '  kill -0 "$WAIT_PID" 2>/dev/null && kill -TERM "$WAIT_PID" 2>/dev/null || true',
        "fi",
        "sleep 0.5",
        f"nohup {launch_cmd} >/dev/null 2>&1 &",
        'rm -f "$0"',
    ]
    sh.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        os.chmod(sh, 0o700)
    except OSError:
        pass
    subprocess.Popen(["/bin/sh", str(sh)], start_new_session=True, close_fds=True)
    return {"ok": True, "restarting": True, "script": str(sh)}


def start_update_job(
    *,
    target_version: str = "",
    force: bool = False,
    dry_run: bool = False,
    auto_restart: bool = False,
    host: str = "127.0.0.1",
    port: int = 8765,
    stdlib: bool = True,
    reopen_window: bool = False,
    shutdown_cb: Optional[Callable[[], None]] = None,
) -> Tuple[int, Dict[str, Any]]:
    """Khởi chạy nền tác vụ tự động cập nhật để Web/Desktop/Android UI theo dõi trực tiếp."""
    with _UPDATE_LOCK:
        for existing in _UPDATE_JOBS.values():
            if existing["status"] == "running":
                return 200, dict(existing)
        jid = uuid.uuid4().hex[:10]
        job: Dict[str, Any] = {
            "id": jid,
            "status": "running",
            "started_utc": sc.now_utc_iso(),
            "finished_utc": "",
            "ok": None,
            "updated": False,
            "restarting": False,
            "requires_apk_install": False,
            "apk_path": "",
            "apk_url": "",
            "to_version": "",
            "logs": [],
            "result": None,
        }
        _UPDATE_JOBS[jid] = job

    def _cb(line: str) -> None:
        with _UPDATE_LOCK:
            _UPDATE_JOBS[jid]["logs"].append(line)

    def _worker() -> None:
        try:
            res = apply_update(target_version=target_version, force=force, dry_run=dry_run, log_cb=_cb)
            req_apk = bool(res.get("requires_apk_install"))
            will_restart = bool(auto_restart and res.get("ok") and res.get("updated") and not dry_run and not req_apk)
            if will_restart:
                _cb("  ↻ Đang khởi động lại máy chủ KAS sang phiên bản mới (giao diện sẽ tự tải lại sau vài giây)...")
            with _UPDATE_LOCK:
                _UPDATE_JOBS[jid].update({
                    "status": "done" if res.get("ok") else "failed",
                    "ok": bool(res.get("ok")),
                    "updated": bool(res.get("updated")),
                    "restarting": will_restart,
                    "requires_apk_install": req_apk,
                    "apk_path": str(res.get("apk_path") or ""),
                    "apk_url": str(res.get("apk_url") or ""),
                    "to_version": str(res.get("to_version") or ""),
                    "finished_utc": sc.now_utc_iso(),
                    "result": res,
                })
            if will_restart:
                time.sleep(1.3)
                schedule_detached_server_restart(
                    host=host,
                    port=port,
                    stdlib=stdlib,
                    reopen_window=reopen_window,
                )
                if callable(shutdown_cb):
                    shutdown_cb()
        except Exception as exc:
            sc.record_exception("updater", exc, message=f"Lỗi tiến trình tự động cập nhật: {exc}", source="updater")
            with _UPDATE_LOCK:
                _UPDATE_JOBS[jid]["logs"].append(f"[LỖI] {exc}")
                _UPDATE_JOBS[jid].update({
                    "status": "failed",
                    "ok": False,
                    "finished_utc": sc.now_utc_iso(),
                })

    threading.Thread(target=_worker, daemon=True).start()
    return 200, dict(job)


def get_update_job(job_id: str) -> Optional[Dict[str, Any]]:
    with _UPDATE_LOCK:
        j = _UPDATE_JOBS.get(job_id)
        if not j:
            return None
        out = dict(j)
        out["logs"] = list(j["logs"])
        return out


def maybe_start_background_update_check() -> None:
    """Chạy kiểm tra cập nhật nền không chặn khi khởi động máy chủ KAS (nếu `auto_check_updates=True`)."""
    st = sc.load_app_settings()
    if not st.auto_check_updates:
        return

    def _bg() -> None:
        try:
            info = check_for_updates(force=False)
            if info.get("ok") and info.get("update_available") and not info.get("is_skipped"):
                sc.log(
                    f"🚀 Đã có bản cập nhật mới: {APP_SHORT} v{info['latest_version']} "
                    f"(hiện tại: v{__version__}). Chạy `kas update` hoặc bấm cập nhật trên giao diện."
                )
                if st.auto_install_updates and not info.get("is_android_apk"):
                    res = apply_update(force=False, log_cb=sc.log)
                    if res.get("ok") and res.get("updated") and not res.get("requires_apk_install"):
                        from karius_academic_system.web.lifecycle import (
                            get_runtime_ui_mode,
                            read_runtime,
                            trigger_graceful_shutdown,
                        )

                        rt = read_runtime()
                        if rt and int(rt.get("pid") or 0) == os.getpid():
                            mode = get_runtime_ui_mode()
                            sc.log(f"↻ Đang tự động khởi động lại KAS sang v{res.get('to_version')}...")
                            schedule_detached_server_restart(
                                host=str(rt.get("host") or st.ui_host or "127.0.0.1"),
                                port=int(rt.get("port") or st.ui_port or 8765),
                                stdlib=bool(rt.get("stdlib", True)),
                                reopen_window=(mode == "pywebview"),
                            )
                            trigger_graceful_shutdown(delay_sec=0.5, close_windows=(mode == "pywebview"))
        except Exception:
            pass

    threading.Thread(target=_bg, daemon=True).start()


def get_rollback_target_version() -> str:
    """Lấy số phiên bản gần nhất trước bản hiện tại từ lịch sử cập nhật để hỗ trợ Rollback 1 bấm."""
    state = load_update_state()
    for entry in reversed(state.get("history") or []):
        prev = str(entry.get("from_version") or "").strip()
        if prev and prev != __version__:
            return prev
    return ""


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="kas update",
        description=f"Kiểm tra và tự động cập nhật {APP_NAME} ({APP_SHORT}) có xác thực SHA-256.",
    )
    ap.add_argument("--check", "--kiem-tra", action="store_true", dest="check_only", help="Chỉ kiểm tra phiên bản mới, không cài")
    ap.add_argument("--version", dest="target_version", default="", help="Cài đặt một phiên bản cụ thể (vd: v1.5.1)")
    ap.add_argument("--rollback", action="store_true", help="Quay về phiên bản trước đó trong lịch sử cập nhật")
    ap.add_argument("--skip", action="store_true", help="Bỏ qua thông báo phiên bản mới nhất hiện tại")
    ap.add_argument("--history", action="store_true", help="Xem lịch sử các lần cập nhật")
    ap.add_argument("--force", action="store_true", help="Cài lại ngay cả khi đang ở bản mới nhất")
    ap.add_argument("--no-restart", action="store_true", dest="no_restart", help="Không tự khởi động lại máy chủ KAS đang chạy sau khi cập nhật")
    ap.add_argument("--chay-thu", "--dry-run", action="store_true", dest="dry_run", help="Chạy thử không tải/cài thật")
    ap.add_argument("--json", action="store_true", dest="as_json", help="Xuất kết quả dạng JSON")
    args = ap.parse_args(argv)

    if args.history:
        state = load_update_state()
        hist = list(reversed(state.get("history") or []))
        if args.as_json:
            print(json.dumps({"current_version": __version__, "history": hist}, ensure_ascii=False, indent=2))
            return 0
        if not hist:
            sc.log(f"Chưa có lịch sử cập nhật tự động (phiên bản hiện tại: v{__version__}).")
            return 0
        sc.log(f"Lịch sử cập nhật {APP_SHORT} (hiện tại: v{__version__}):")
        for h in hist:
            vmark = "SHA-256 ✓" if h.get("sha256_verified") else "HTTPS"
            sc.log(f"  • {h.get('timestamp_utc')} | v{h.get('from_version')} → v{h.get('to_version')} ({h.get('kind')}, {vmark})")
        return 0

    if args.check_only or args.skip:
        info = check_for_updates(force=True)
        if args.skip and info.get("ok") and info.get("latest_version"):
            skip_update_version(str(info["latest_version"]))
            info["skipped_version"] = str(info["latest_version"])
            info["is_skipped"] = True
        if args.as_json:
            print(json.dumps(info, ensure_ascii=False, indent=2))
            return 0 if info.get("ok") else 1
        if not info.get("ok"):
            sc.log(f"[LỖI] {info.get('error')}")
            return 1
        if info.get("update_available"):
            sc.log(f"🚀 Có bản mới: {APP_SHORT} v{info['latest_version']} (hiện tại: v{__version__})")
            sc.log(f"   Trang phát hành: {info['release_url']}")
            sc.log("   Chạy `kas update` để tự động tải, xác thực SHA-256 và nâng cấp ngay!")
        else:
            sc.log(f"✓ Bạn đang dùng phiên bản mới nhất: {APP_SHORT} v{__version__}.")
        return 0

    target = args.target_version
    if args.rollback:
        target = get_rollback_target_version()
        if not target:
            sc.log("Không tìm thấy phiên bản trước trong lịch sử cập nhật. Hãy truyền `--version vX.Y.Z`.")
            return 1

    res = apply_update(
        target_version=target,
        force=args.force,
        dry_run=args.dry_run,
        log_cb=(None if args.as_json else sc.log),
    )
    if res.get("ok") and res.get("updated") and not args.dry_run and not args.no_restart:
        try:
            from karius_academic_system.web.lifecycle import stop_running_kas_instances

            stopped = stop_running_kas_instances(close_windows=False)
            if stopped.get("was_running"):
                schedule_detached_server_restart(
                    host=str(stopped.get("host") or "127.0.0.1"),
                    port=int(stopped.get("port") or 8765),
                    stdlib=bool(stopped.get("stdlib", True)),
                    reopen_window=(stopped.get("mode") == "pywebview"),
                    wait_pid=0,
                )
                res["restarted_running_instance"] = True
                if not args.as_json:
                    sc.log(f"  ↻ Đã tự đóng máy chủ KAS cũ và khởi động lại phiên bản v{res.get('to_version')}!")
        except Exception:
            pass
    if args.as_json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
