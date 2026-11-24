"""Cầu nối & Động cơ Khởi chạy Hệ điều hành Android (`kas android` & `kas-android.apk`) — KAS v1.9.0.

Hỗ trợ:
1. Ứng dụng Android gốc (`kas-android.apk` / Chaquopy Python 3.11): khởi chạy máy chủ KAS nội bộ trên thiết bị
   (`127.0.0.1`), tự cấu hình chứng chỉ SSL Android 8–16, tạo kho tài liệu mặc định và kết nối `MainActivity`.
2. Chứng chỉ ký số cố định lâu dài (`ANDROID_CERT_SHA1` / `ANDROID_CERT_SHA256`) cho Google Auth / OAuth & cài đè APK.
3. Ghép nối Máy tính ↔ Điện thoại Android qua Wi-Fi / LAN: phát hiện IPv4 LAN ưu tiên Wi-Fi thật,
   dịch vụ tự khám phá UDP LAN (`KAS_DISCOVER_V1` cổng 8766), bật/tắt chế độ chia sẻ Wi-Fi LAN 1 bấm.
4. Môi trường Android Termux (`install_android_termux.sh`): nhận diện `~/storage/shared` & `/storage/emulated/0`.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from karius_academic_system import APP_NAME, APP_SHORT, __version__
from karius_academic_system import core as sc

ANDROID_PACKAGE_ID = "io.github.kariusnocr.kas"
GITHUB_REPO = "kariusnocr/storage-management-suite"

# Vân tay chứng chỉ ký số phát hành cố định của kas-android.apk (dữ liệu công khai — dùng cho Google Cloud OAuth & đối chiếu APK)
ANDROID_CERT_SHA1 = "FF:D4:BA:CE:3C:48:C1:53:AF:BC:44:B3:AD:FE:6D:5C:31:8B:61:BC"
ANDROID_CERT_SHA256 = "EC:65:9D:B8:08:53:33:6C:CE:BA:66:46:F2:3F:19:21:D6:2F:12:D3:DB:8B:6C:08:BE:7F:1F:51:14:1E:A0:96"

LAN_DISCOVERY_PORT = 8766
LAN_DISCOVERY_PROBE = b"KAS_DISCOVER_V1"

_ANDROID_SERVER_LOCK = threading.Lock()
_ANDROID_SERVER_STATE: Dict[str, Any] = {
    "running": False,
    "host": "127.0.0.1",
    "port": 0,
    "url": "",
    "engine": "",
    "stop_fn": None,
}

_ACTIVE_BINDING_LOCK = threading.Lock()
_ACTIVE_BINDING: Dict[str, Any] = {
    "host": "",
    "port": 0,
}

_DISCOVERY_LOCK = threading.Lock()
_DISCOVERY_STATE: Dict[str, Any] = {
    "running": False,
    "port": 0,
    "http_port": 8765,
    "stop_event": None,
    "sock": None,
}


def set_active_server_binding(host: str, port: int) -> None:
    """Ghi nhận địa chỉ lắng nghe thực tế của máy chủ Web/Desktop hiện tại."""
    with _ACTIVE_BINDING_LOCK:
        _ACTIVE_BINDING["host"] = str(host or "").strip()
        _ACTIVE_BINDING["port"] = int(port or 0)


def get_active_server_binding() -> Tuple[str, int]:
    with _ACTIVE_BINDING_LOCK:
        return str(_ACTIVE_BINDING["host"]), int(_ACTIVE_BINDING["port"])


def is_lan_host(host: str) -> bool:
    h = (host or "").strip().lower()
    return h not in {"", "127.0.0.1", "localhost", "::1"}


def configure_android_ssl_certs() -> Dict[str, str]:
    """Đảm bảo Python/OpenSSL trên Android 8–16 tìm thấy kho chứng chỉ CA hợp lệ cho HTTPS GitHub/Google."""
    info: Dict[str, str] = {"ssl_cert_file": "", "ssl_cert_dir": ""}
    try:
        import certifi  # type: ignore

        ca_file = certifi.where()
        if ca_file and os.path.isfile(ca_file):
            os.environ.setdefault("SSL_CERT_FILE", ca_file)
            os.environ.setdefault("REQUESTS_CA_BUNDLE", ca_file)
            info["ssl_cert_file"] = ca_file
    except Exception:
        pass

    for ca_dir in ("/apex/com.android.conscrypt/cacerts", "/system/etc/security/cacerts"):
        if os.path.isdir(ca_dir):
            os.environ.setdefault("SSL_CERT_DIR", ca_dir)
            info["ssl_cert_dir"] = ca_dir
            break
    return info


def _ipv4_priority(ip: str) -> Tuple[int, str]:
    """Ưu tiên dải mạng Wi-Fi/LAN thật (`192.168.*` trước `10.*` trước `172.16-31.*`, hạ ưu tiên VirtualBox/Docker)."""
    parts = ip.split(".")
    if len(parts) != 4:
        return (99, ip)
    try:
        a, b = int(parts[0]), int(parts[1])
    except ValueError:
        return (99, ip)
    if a == 192 and b == 168:
        # 192.168.56.x thường là VirtualBox Host-Only
        return (20, ip) if int(parts[2]) == 56 else (0, ip)
    if a == 10:
        return (1, ip)
    if a == 172 and 16 <= b <= 31:
        return (5, ip)
    return (10, ip)


def discover_lan_ipv4() -> List[str]:
    """Tìm danh sách địa chỉ IPv4 mạng nội bộ (ưu tiên Wi-Fi / LAN thật, loại loopback & APIPA 169.254.*)."""
    ips: List[str] = []

    def _add(ip: str) -> None:
        ip = (ip or "").strip()
        if (
            ip
            and not ip.startswith("127.")
            and not ip.startswith("169.254.")
            and ip != "0.0.0.0"
            and ":" not in ip
            and ip not in ips
        ):
            ips.append(ip)

    # 1. Thăm dò bảng định tuyến cục bộ (không gửi gói tin thật ra Internet với UDP connect)
    for probe_target in (("8.8.8.8", 80), ("192.168.1.1", 80), ("10.255.255.255", 1)):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(probe_target)
                _add(s.getsockname()[0])
        except Exception:
            pass

    # 2. Lấy thêm mọi IPv4 gắn trên tên máy
    for host_candidate in {socket.gethostname(), socket.getfqdn()}:
        if not host_candidate:
            continue
        try:
            for info in socket.getaddrinfo(host_candidate, None, socket.AF_INET):
                _add(str(info[4][0]))
        except Exception:
            pass

    ips.sort(key=_ipv4_priority)
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


def start_lan_discovery_responder(http_port: int, discovery_port: int = LAN_DISCOVERY_PORT) -> bool:
    """Khởi chạy dịch vụ phản hồi UDP LAN (`KAS_DISCOVER_V1`) để ứng dụng Android tự tìm thấy PC cùng Wi-Fi."""
    with _DISCOVERY_LOCK:
        if _DISCOVERY_STATE["running"] and _DISCOVERY_STATE["http_port"] == int(http_port):
            return True
    stop_lan_discovery_responder()

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", int(discovery_port)))
        sock.settimeout(0.6)
    except OSError:
        return False

    stop_ev = threading.Event()
    bound_udp_port = int(sock.getsockname()[1])

    def _serve_udp() -> None:
        while not stop_ev.is_set():
            try:
                data, addr = sock.recvfrom(512)
            except socket.timeout:
                continue
            except OSError:
                break
            if not data or LAN_DISCOVERY_PROBE not in data:
                continue
            try:
                ips = discover_lan_ipv4()
                urls = [f"http://{ip}:{int(http_port)}" for ip in ips]
                payload = json.dumps(
                    {
                        "app": APP_SHORT,
                        "app_name": APP_NAME,
                        "version": __version__,
                        "hostname": socket.gethostname(),
                        "port": int(http_port),
                        "urls": urls,
                        "primary_url": urls[0] if urls else "",
                    },
                    ensure_ascii=False,
                ).encode("utf-8")
                sock.sendto(payload, addr)
            except Exception:
                continue
        try:
            sock.close()
        except Exception:
            pass

    th = threading.Thread(target=_serve_udp, name="kas-lan-discovery", daemon=True)
    th.start()
    with _DISCOVERY_LOCK:
        _DISCOVERY_STATE.update(
            {
                "running": True,
                "port": bound_udp_port,
                "http_port": int(http_port),
                "stop_event": stop_ev,
                "sock": sock,
            }
        )
    sc.record_event(
        "INFO",
        "android_lan",
        f"Đã bật bộ tự khám phá PC qua Wi-Fi LAN (UDP :{bound_udp_port} → HTTP :{int(http_port)}).",
        source="android_bridge",
    )
    return True


def stop_lan_discovery_responder() -> None:
    with _DISCOVERY_LOCK:
        ev = _DISCOVERY_STATE.get("stop_event")
        sock = _DISCOVERY_STATE.get("sock")
        if ev is not None:
            ev.set()
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
        _DISCOVERY_STATE.update({"running": False, "port": 0, "stop_event": None, "sock": None})


def windows_firewall_hint_command(http_port: int = 8765, udp_port: int = LAN_DISCOVERY_PORT) -> str:
    return (
        f'netsh advfirewall firewall add rule name="KAS Wi-Fi LAN (TCP {int(http_port)})" '
        f"dir=in action=allow protocol=TCP localport={int(http_port)} profile=private; "
        f'netsh advfirewall firewall add rule name="KAS Wi-Fi Discovery (UDP {int(udp_port)})" '
        f"dir=in action=allow protocol=UDP localport={int(udp_port)} profile=private"
    )


def try_open_windows_firewall_ports(http_port: int = 8765, udp_port: int = LAN_DISCOVERY_PORT) -> Dict[str, Any]:
    """Cố gắng mở quy tắc Windows Firewall mạng Private cho TCP/UDP LAN (không gây lỗi nếu thiếu quyền Admin)."""
    cmd_hint = windows_firewall_hint_command(http_port, udp_port)
    if os.name != "nt":
        return {"attempted": False, "ok": True, "message": "Không phải Windows.", "manual_cmd": ""}
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    ok_all = True
    errors: List[str] = []
    rules = [
        (f"KAS Wi-Fi LAN (TCP {int(http_port)})", "TCP", int(http_port)),
        (f"KAS Wi-Fi Discovery (UDP {int(udp_port)})", "UDP", int(udp_port)),
    ]
    for rname, proto, port_num in rules:
        try:
            chk = subprocess.run(
                ["netsh", "advfirewall", "firewall", "show", "rule", f"name={rname}"],
                capture_output=True,
                text=True,
                timeout=8,
                creationflags=flags,
            )
            if chk.returncode == 0 and rname.lower() in (chk.stdout or "").lower():
                continue
            add = subprocess.run(
                [
                    "netsh",
                    "advfirewall",
                    "firewall",
                    "add",
                    "rule",
                    f"name={rname}",
                    "dir=in",
                    "action=allow",
                    f"protocol={proto}",
                    f"localport={port_num}",
                    "profile=private",
                ],
                capture_output=True,
                text=True,
                timeout=8,
                creationflags=flags,
            )
            if add.returncode != 0:
                ok_all = False
                errors.append((add.stderr or add.stdout or "").strip())
        except Exception as exc:
            ok_all = False
            errors.append(str(exc))
    return {
        "attempted": True,
        "ok": ok_all,
        "message": (
            f"Đã mở cổng Windows Firewall Private (TCP {http_port}, UDP {udp_port})."
            if ok_all
            else "Cần quyền Quản trị viên (Run as Administrator) để mở cổng Windows Firewall nếu điện thoại bị tường lửa chặn."
        ),
        "errors": [e for e in errors if e],
        "manual_cmd": cmd_hint,
    }


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


def detect_android_environment(port: int = 8765, listening_host: str = "") -> Dict[str, Any]:
    """Tổng hợp thông tin môi trường Android, chứng chỉ SHA-1, liên kết tải APK, lệnh Termux và trạng thái ghép nối Wi-Fi LAN."""
    flavor = detect_runtime_flavor()
    is_android = flavor in {"chaquopy_apk", "termux"}
    st = sc.load_app_settings()
    bound_host, bound_port = get_active_server_binding()
    eff_host = (listening_host or bound_host or st.ui_host or "127.0.0.1").strip()
    eff_port = int(port or bound_port or _ANDROID_SERVER_STATE.get("port") or st.ui_port or 8765)
    lan_enabled = is_lan_host(eff_host)
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
        "listening_host": eff_host,
        "active_port": eff_port,
        "lan_enabled": lan_enabled,
        "lan_discovery_active": bool(_DISCOVERY_STATE.get("running")),
        "discovery_port": LAN_DISCOVERY_PORT,
        "local_url": f"http://127.0.0.1:{eff_port}",
        "lan_ips": lan_ips,
        "lan_urls": lan_urls,
        "primary_lan_url": lan_urls[0] if lan_urls else f"http://127.0.0.1:{eff_port}",
        "windows_firewall_cmd": windows_firewall_hint_command(eff_port, LAN_DISCOVERY_PORT),
        "recommended_vault_path": recommended_path,
        "storage_candidates": storage_paths,
        "signing": {
            "package_name": ANDROID_PACKAGE_ID,
            "sha1": ANDROID_CERT_SHA1,
            "sha256": ANDROID_CERT_SHA256,
            "oauth_note": (
                "Dùng mã SHA-1 trên khi tạo OAuth Client loại Android trong Google Auth Platform. "
                "Lưu ý: Để nạp tệp credentials.json cho tính năng đăng nhập Google Drive trong KAS, "
                "hãy chọn loại Desktop app (hoạt động chung cho cả PC và Android)."
            ),
        },
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
            "- **Ghép nối Máy tính**: Bật *Chia sẻ Wi-Fi LAN* trên PC, sau đó chạm nút **Tự tìm PC cùng Wi-Fi** trên điện thoại.\n",
            encoding="utf-8",
        )

    vc = reg.add_vault(
        name=vault_name,
        source=str(target_dir.resolve()),
        mode="academic_v7",
        activate=True,
    )
    sc.reload_config(vc.slug)

    try:
        from karius_academic_system.ops import indexer

        idx = indexer.scan_local_vault(target_dir.resolve())
        sc.save_index(idx, snapshot=False)
    except Exception as exc:
        sc.record_exception("android_vault", exc, message="Lỗi quét chỉ mục ban đầu cho Kho Android")

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

        sc.install_global_exception_hooks()
        ssl_info = configure_android_ssl_certs()

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
                "host": "127.0.0.1",
                "port": bound_port,
                "url": url,
                "engine": engine,
                "stop_fn": stop_fn,
            }
        )
        sc.record_event(
            "INFO",
            "android_boot",
            f"Đã khởi chạy máy chủ KAS Android nội bộ v{__version__} tại {url} ({engine})",
            source="android_bridge",
            meta={"ssl_cert_file": ssl_info.get("ssl_cert_file", ""), "ssl_cert_dir": ssl_info.get("ssl_cert_dir", "")},
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
                "host": "127.0.0.1",
                "port": 0,
                "url": "",
                "engine": "",
                "stop_fn": None,
            }
        )
    return {"ok": True}
