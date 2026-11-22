"""Cầu nối & Động cơ Khởi chạy Hệ điều hành Android (`kas android` & `kas-android.apk`) — KAS v1.7.0.

Hỗ trợ:
1. Ứng dụng Android gốc (`kas-android.apk` / Chaquopy Python 3.11): khởi chạy máy chủ KAS nội bộ trên thiết bị
   (`127.0.0.1`), tự tạo kho tài liệu mặc định trên bộ nhớ Android và kết nối với `MainActivity` WebView.
2. Môi trường Android Termux (`install_android_termux.sh`): nhận diện `~/storage/shared` & `/storage/emulated/0`.
3. Ghép nối Máy tính ↔ Điện thoại Android qua Wi-Fi / LAN (`kas android info`, `kas android serve`).
"""

from __future__ import annotations

import os
import socket
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from karius_academic_system import APP_NAME, APP_SHORT, __version__
from karius_academic_system import core as sc

ANDROID_PACKAGE_ID = "io.github.kariusnocr.kas"
GITHUB_REPO = "kariusnocr/storage-management-suite"

_ANDROID_SERVER_LOCK = threading.Lock()
_ANDROID_SERVER_STATE: Dict[str, Any] = {
    "running": False,
    "port": 0,
    "url": "",
    "engine": "",
    "stop_fn": None,
}


def discover_lan_ipv4() -> List[str]:
    """Tìm danh sách địa chỉ IPv4 mạng nội bộ (Wi-Fi / LAN / Tailscale) mà không gửi gói tin ra ngoài."""
    ips: List[str] = []

    def _add(ip: str) -> None:
        ip = (ip or "").strip()
        if ip and not ip.startswith("127.") and ip != "0.0.0.0" and ":" not in ip and ip not in ips:
            ips.append(ip)

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            _add(s.getsockname()[0])
    except Exception:
        pass

    try:
        host = socket.gethostname()
        for info in socket.getaddrinfo(host, None, socket.AF_INET):
            _add(str(info[4][0]))
    except Exception:
        pass

    return ips


def detect_runtime_flavor() -> str:
    """Phân biệt môi trường đang chạy: `chaquopy_apk`, `termux`, hoặc `desktop_host`."""
    override = (os.environ.get("KAS_ANDROID_RUNTIME") or "").strip().lower()
    if override in {"chaquopy_apk", "termux", "desktop_host"}:
        return override
    if "com.chaquo.python" in sys.modules or "chaquopy" in sys.modules:
        return "chaquopy_apk"
    prefix = os.environ.get("PREFIX", "")
    if "com.termux" in prefix or os.path.isdir("/data/data/com.termux"):
        return "termux"
    if os.environ.get("ANDROID_ROOT") or os.environ.get("ANDROID_DATA"):
        return "chaquopy_apk"
    return "desktop_host"


def candidate_android_storage_paths() -> List[Dict[str, Any]]:
    """Liệt kê các đường dẫn lưu trữ tài liệu ứng viên trên thiết bị Android."""
    candidates: List[Tuple[str, Path]] = []
    ext_env = (os.environ.get("KAS_ANDROID_EXTERNAL_DIR") or "").strip()
    if ext_env:
        candidates.append(("Bộ nhớ Ứng dụng Android (Không cần cấp quyền mở rộng)", Path(ext_env) / "KASVault"))

    shared_docs = Path("/storage/emulated/0/Documents/KAS")
    candidates.append(("Thư mục Tài liệu chung Android (Documents/KAS)", shared_docs))

    sdcard_docs = Path("/sdcard/Documents/KAS")
    if sdcard_docs != shared_docs:
        candidates.append(("Bộ nhớ chia sẻ Android (/sdcard/Documents/KAS)", sdcard_docs))

    termux_shared = Path.home() / "storage" / "shared" / "Documents" / "KAS"
    candidates.append(("Bộ nhớ Termux Shared (~/storage/shared/Documents/KAS)", termux_shared))

    app_data_vault = sc.data_dir() / "android_vault"
    candidates.append(("Kho Nội bộ KAS (App Internal Storage)", app_data_vault))

    results: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for label, p in candidates:
        p_str = str(p)
        if p_str in seen:
            continue
        seen.add(p_str)
        exists = False
        writable = False
        try:
            exists = p.exists()
            probe = p if exists else p.parent
            writable = os.access(str(probe), os.W_OK)
        except OSError:
            pass
        results.append(
            {
                "label": label,
                "path": p_str,
                "exists": exists,
                "writable": writable,
            }
        )
    return results


def detect_android_environment(port: int = 8765) -> Dict[str, Any]:
    """Tổng hợp thông tin môi trường Android, liên kết tải APK, lệnh Termux và địa chỉ ghép nối LAN."""
    flavor = detect_runtime_flavor()
    is_android = flavor in {"chaquopy_apk", "termux"}
    st = sc.load_app_settings()
    eff_port = int(port or _ANDROID_SERVER_STATE.get("port") or st.ui_port or 8765)
    lan_ips = discover_lan_ipv4()
    lan_urls = [f"http://{ip}:{eff_port}" for ip in lan_ips]
    storage_paths = candidate_android_storage_paths()

    recommended_path = ""
    for sp in storage_paths:
        if sp["writable"] or sp["exists"]:
            recommended_path = sp["path"]
            break
    if not recommended_path and storage_paths:
        recommended_path = storage_paths[0]["path"]

    return {
        "ok": True,
        "app_name": APP_NAME,
        "app_short": APP_SHORT,
        "version": __version__,
        "package_id": ANDROID_PACKAGE_ID,
        "is_android": is_android,
        "runtime_flavor": flavor,
        "active_port": eff_port,
        "local_url": f"http://127.0.0.1:{eff_port}",
        "lan_ips": lan_ips,
        "lan_urls": lan_urls,
        "primary_lan_url": lan_urls[0] if lan_urls else f"http://127.0.0.1:{eff_port}",
        "recommended_vault_path": recommended_path,
        "storage_candidates": storage_paths,
        "downloads": {
            "apk_latest_url": f"https://github.com/{GITHUB_REPO}/releases/latest/download/kas-android.apk",
            "apk_versioned_url": f"https://github.com/{GITHUB_REPO}/releases/download/v{__version__}/kas-android.apk",
            "release_page_url": f"https://github.com/{GITHUB_REPO}/releases/tag/v{__version__}",
            "termux_one_liner": (
                f"curl -fsSL https://raw.githubusercontent.com/{GITHUB_REPO}/main/"
                "packaging/android/install_android_termux.sh | bash"
            ),
            "lan_serve_cmd": f"kas android serve --port {eff_port}",
        },
        "pwa": {
            "manifest_url": "/manifest.webmanifest",
            "service_worker_url": "/sw.js",
            "icon_url": "/static/icon.svg",
            "installable": True,
        },
    }


def bootstrap_android_vault(
    preferred_dir: str = "",
    *,
    vault_name: str = "Kho Tài Liệu Android",
    create_starter_files: bool = True,
    force_new: bool = False,
) -> Dict[str, Any]:
    """Khởi tạo và kích hoạt một kho tài liệu cục bộ trên thiết bị Android."""
    reg = sc.VaultRegistry()
    active = reg.get_active_vault()
    if active is not None and not force_new and not preferred_dir:
        sc.reload_config(active.slug)
        return {
            "ok": True,
            "created": False,
            "vault": active.to_dict(),
            "vault_path": active.root,
        }

    target_dir: Optional[Path] = None
    if preferred_dir:
        target_dir = Path(preferred_dir).expanduser()
    else:
        for cand in candidate_android_storage_paths():
            p = Path(cand["path"])
            try:
                p.mkdir(parents=True, exist_ok=True)
                target_dir = p
                break
            except OSError:
                continue

    if target_dir is None:
        target_dir = sc.data_dir() / "android_vault"
    target_dir.mkdir(parents=True, exist_ok=True)

    starter_branches = ["[00] TỔNG QUAN", "[01] HỌC THUẬT", "[02] TƯ LIỆU"]
    for br in starter_branches:
        (target_dir / br).mkdir(parents=True, exist_ok=True)

    welcome_md = target_dir / "[00] TỔNG QUAN" / "Chào Mừng KAS Trên Android.md"
    if create_starter_files and not welcome_md.exists():
        welcome_md.write_text(
            f"# Chào mừng đến với {APP_NAME} ({APP_SHORT}) v{__version__} trên Android\n\n"
            "- **Duyệt Kho**: Chạm vào bất kỳ thư mục nào để đi vào ngay; chạm vào tệp để xem trước trực tiếp.\n"
            "- **Đa Kho Dữ Liệu**: Bạn có thể kết nối thêm thư mục trong bộ nhớ máy (`/storage/emulated/0/...`) "
            "hoặc đăng nhập **Google Drive OAuth 2.0** tại mục *Tài Khoản & Kết Nối*.\n"
            "- **Ghép nối Máy tính**: Chuyển đổi linh hoạt giữa máy chủ nội bộ trên điện thoại và máy chủ KAS trên PC qua Wi-Fi.\n",
            encoding="utf-8",
        )

    vc = reg.add_vault(
        name=vault_name,
        source=str(target_dir.resolve()),
        mode="academic_v7",
        activate=True,
    )
    sc.reload_config(vc.slug)

    # Quét nhanh cấu trúc ban đầu vào SQLite để Tổng quan & Tìm kiếm có dữ liệu tức thì
    try:
        from karius_academic_system.ops import indexer

        idx = indexer.scan_local_vault(target_dir.resolve())
        sc.save_index(idx, snapshot=False)
    except Exception:
        pass

    return {
        "ok": True,
        "created": True,
        "vault": vc.to_dict(),
        "vault_path": str(target_dir.resolve()),
    }


def _find_available_port(host: str = "127.0.0.1", preferred_port: int = 8765) -> int:
    for candidate in (preferred_port, 8766, 8767, 0):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((host, candidate))
                return int(s.getsockname()[1])
        except OSError:
            continue
    return preferred_port


def start_android_embedded_server(
    app_files_dir: str = "",
    external_files_dir: str = "",
    port: int = 8765,
) -> Dict[str, Any]:
    """Điểm vào khởi chạy máy chủ KAS nhúng bên trong APK Android (gọi từ `MainActivity` qua Chaquopy)."""
    with _ANDROID_SERVER_LOCK:
        if _ANDROID_SERVER_STATE["running"] and _ANDROID_SERVER_STATE["url"]:
            return {
                "ok": True,
                "already_running": True,
                "port": _ANDROID_SERVER_STATE["port"],
                "url": _ANDROID_SERVER_STATE["url"],
                "engine": _ANDROID_SERVER_STATE["engine"],
            }

        os.environ["KAS_ANDROID_RUNTIME"] = "chaquopy_apk"
        if app_files_dir:
            base = Path(app_files_dir) / "kas"
            cfg_dir = base / "config"
            dat_dir = base / "data"
            cfg_dir.mkdir(parents=True, exist_ok=True)
            dat_dir.mkdir(parents=True, exist_ok=True)
            os.environ["KAS_CONFIG_DIR"] = str(cfg_dir)
            os.environ["KAS_DATA_DIR"] = str(dat_dir)
        if external_files_dir:
            os.environ["KAS_ANDROID_EXTERNAL_DIR"] = str(external_files_dir)

        # Đảm bảo Chaquopy giải nén gói dữ liệu & tài nguyên tĩnh ra hệ thống tệp
        try:
            import karius_academic_system.data  # noqa: F401
            import karius_academic_system.web.static  # noqa: F401
        except Exception:
            pass

        sc.reload_config()
        vault_res = bootstrap_android_vault()

        from karius_academic_system.web.app import start_embedded_server

        bound_port = _find_available_port("127.0.0.1", int(port or 8765))
        _, stop_fn, engine = start_embedded_server(host="127.0.0.1", port=bound_port, prefer_stdlib=True)
        url = f"http://127.0.0.1:{bound_port}"
        _ANDROID_SERVER_STATE.update(
            {
                "running": True,
                "port": bound_port,
                "url": url,
                "engine": engine,
                "stop_fn": stop_fn,
            }
        )
        return {
            "ok": True,
            "already_running": False,
            "port": bound_port,
            "url": url,
            "engine": engine,
            "vault": vault_res.get("vault"),
        }


def stop_android_embedded_server() -> Dict[str, Any]:
    """Dừng máy chủ KAS nhúng trên Android (khi ứng dụng giải phóng tài nguyên hoặc trong kiểm thử)."""
    with _ANDROID_SERVER_LOCK:
        stop_fn: Optional[Callable[[], None]] = _ANDROID_SERVER_STATE.get("stop_fn")
        if callable(stop_fn):
            try:
                stop_fn()
            except Exception:
                pass
        _ANDROID_SERVER_STATE.update(
            {
                "running": False,
                "port": 0,
                "url": "",
                "engine": "",
                "stop_fn": None,
            }
        )
    return {"ok": True}
