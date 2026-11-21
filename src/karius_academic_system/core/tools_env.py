"""Tự động phát hiện công cụ CLI đa nền tảng & tự làm mới PATH trên Windows/macOS/Linux cho Karius Academic System (KAS)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

# Các thư mục cài đặt chuẩn trên Windows cho các công cụ phổ biến không tự thêm vào PATH
_WINDOWS_STATIC_DIRS: Sequence[str] = (
    r"C:\Program Files\GitHub CLI",
    r"C:\Program Files\Git\cmd",
    r"C:\Program Files\Git\bin",
    r"C:\Program Files\7-Zip",
    r"C:\Program Files (x86)\7-Zip",
    r"C:\Program Files\Tesseract-OCR",
    r"C:\Program Files (x86)\Tesseract-OCR",
    r"C:\ProgramData\chocolatey\bin",
)

# Các mẫu thư mục WinGet Packages chứa tệp nhị phân của Poppler / FFmpeg / Tesseract
_WINGET_PACKAGE_GLOBS: Sequence[tuple[str, str]] = (
    ("oschwartz10612.Poppler*", "poppler-*/Library/bin"),
    ("oschwartz10612.Poppler*", "Library/bin"),
    ("Gyan.FFmpeg*", "ffmpeg-*/bin"),
    ("BtbN.FFmpeg*", "ffmpeg-*/bin"),
    ("UB-Mannheim.TesseractOCR*", ""),
)

_POSIX_EXTRA_DIRS: Sequence[str] = (
    "/opt/homebrew/bin",
    "/usr/local/bin",
    "/opt/antigravity/bin",
)


def shared_tessdata_dir() -> Path:
    """Thư mục lưu dữ liệu OCR (`vie.traineddata`, `eng.traineddata`) dùng chung cho mọi kho (không cần quyền Admin)."""
    env = os.environ.get("KAS_TESSDATA_DIR")
    p = Path(env).expanduser() if env else (Path.home() / ".local" / "share" / "kas" / "tessdata")
    p.mkdir(parents=True, exist_ok=True)
    return p


def _read_windows_registry_paths() -> List[str]:
    """Đọc PATH mới nhất từ Registry (Machine + User) trên Windows để nhận ngay phần mềm vừa cài bằng winget."""
    if os.name != "nt":
        return []
    dirs: List[str] = []
    try:
        import winreg  # type: ignore

        targets = [
            (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
            (winreg.HKEY_CURRENT_USER, r"Environment"),
        ]
        for hive, subkey in targets:
            try:
                with winreg.OpenKey(hive, subkey) as key:
                    val, _ = winreg.QueryValueEx(key, "Path")
                    if isinstance(val, str):
                        expanded = os.path.expandvars(val)
                        for part in expanded.split(os.pathsep):
                            p = part.strip().strip('"')
                            if p:
                                dirs.append(p)
            except OSError:
                continue
    except Exception:
        return []
    return dirs


def discover_standard_tool_dirs() -> List[str]:
    """Quét các thư mục cài đặt chuẩn trên hệ điều hành hiện tại (WinGet, Program Files, Scoop, Homebrew...)."""
    found: List[str] = []
    if os.name == "nt":
        local_app = os.environ.get("LOCALAPPDATA", "")
        user_prof = os.environ.get("USERPROFILE", str(Path.home()))
        candidates: List[Path] = [Path(d) for d in _WINDOWS_STATIC_DIRS]
        if local_app:
            la = Path(local_app)
            candidates.extend([
                la / "kas" / "bin",
                la / "Microsoft" / "WinGet" / "Links",
                la / "Programs" / "Tesseract-OCR",
                la / "Programs" / "Git" / "cmd",
                la / "Programs" / "GitHub CLI",
                la / "Programs" / "7-Zip",
            ])
            wg_pkgs = la / "Microsoft" / "WinGet" / "Packages"
            if wg_pkgs.is_dir():
                for pkg_glob, sub_glob in _WINGET_PACKAGE_GLOBS:
                    for pkg_dir in sorted(wg_pkgs.glob(pkg_glob), reverse=True):
                        if not sub_glob:
                            candidates.append(pkg_dir)
                        else:
                            for sub in sorted(pkg_dir.glob(sub_glob), reverse=True):
                                candidates.append(sub)
        if user_prof:
            candidates.append(Path(user_prof) / "scoop" / "shims")
        for c in candidates:
            try:
                if c.is_dir():
                    found.append(str(c))
            except OSError:
                continue
    else:
        for d in _POSIX_EXTRA_DIRS:
            if Path(d).is_dir():
                found.append(d)
    return found


def refresh_system_path() -> List[str]:
    """Làm mới `os.environ['PATH']` trong tiến trình hiện tại từ Registry (Windows) & các thư mục công cụ chuẩn."""
    current_parts = [p.strip().strip('"') for p in os.environ.get("PATH", "").split(os.pathsep) if p.strip()]
    seen_norm = {os.path.normcase(os.path.normpath(p)) for p in current_parts}
    added: List[str] = []

    for candidate in [*_read_windows_registry_paths(), *discover_standard_tool_dirs()]:
        if not candidate:
            continue
        norm = os.path.normcase(os.path.normpath(candidate))
        if norm in seen_norm:
            continue
        try:
            if Path(candidate).is_dir():
                current_parts.append(candidate)
                seen_norm.add(norm)
                added.append(candidate)
        except OSError:
            continue

    if added:
        os.environ["PATH"] = os.pathsep.join(current_parts)
    return added


def add_dirs_to_windows_user_path(dirs: Iterable[str]) -> List[str]:
    """Ghi bền vững các thư mục công cụ mới vào biến `Path` của người dùng Windows (`HKCU\\Environment`)."""
    if os.name != "nt":
        return []
    valid_dirs = [str(Path(d)) for d in dirs if d and Path(d).is_dir()]
    if not valid_dirs:
        return []
    persisted: List[str] = []
    try:
        import winreg  # type: ignore

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as key:
            try:
                cur_val, reg_type = winreg.QueryValueEx(key, "Path")
            except FileNotFoundError:
                cur_val, reg_type = "", winreg.REG_EXPAND_SZ
            parts = [p.strip().strip('"') for p in str(cur_val).split(";") if p.strip()]
            seen = {os.path.normcase(os.path.normpath(p)) for p in parts}
            for d in valid_dirs:
                norm = os.path.normcase(os.path.normpath(d))
                if norm not in seen:
                    parts.append(d)
                    seen.add(norm)
                    persisted.append(d)
            if persisted:
                winreg.SetValueEx(key, "Path", 0, reg_type or winreg.REG_EXPAND_SZ, ";".join(parts))
    except Exception:
        return []
    refresh_system_path()
    return persisted


def find_cli_tool(name: str, refresh: bool = True) -> str:
    """Tìm đường dẫn thực thi của một công cụ CLI (tự động quét lại Registry/WinGet/Program Files nếu chưa thấy)."""
    hit = shutil.which(name)
    if hit:
        return hit
    if refresh:
        refresh_system_path()
        hit = shutil.which(name)
        if hit:
            return hit
    return ""


def ensure_tools_on_path() -> Dict[str, str]:
    """Bảo đảm các công cụ đa phương tiện/OCR/Git hiện có trên máy được nạp sẵn vào `PATH` của tiến trình KAS."""
    refresh_system_path()
    tool_names = ("gh", "git", "7z", "ffmpeg", "ffprobe", "tesseract", "pdftotext", "pdfinfo", "pdftoppm")
    return {t: (shutil.which(t) or "") for t in tool_names}
