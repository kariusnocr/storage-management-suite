"""Quản lý Đa Kho Dữ Liệu (Multi-Vault Registry) cho Karius Academic System (KAS) v1.0."""

from __future__ import annotations

import datetime as _dt
import os
import re
import tomllib
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_DRIVE_URL_PATTERNS = (
    re.compile(r"drive\.google\.com/(?:drive/(?:u/\d+/)?folders|file/d)/([A-Za-z0-9_-]{10,})"),
    re.compile(r"docs\.google\.com/(?:spreadsheets|document|presentation)/d/([A-Za-z0-9_-]{10,})"),
    re.compile(r"[?&]id=([A-Za-z0-9_-]{10,})"),
)
_DRIVE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{15,}$")
_WIN_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")
_STT_FOLDER_RE = re.compile(r"^\[\d{1,3}\]\s+")


def _now_utc_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _strip_accents(s: str) -> str:
    decomposed = unicodedata.normalize("NFD", s or "")
    out = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return out.replace("đ", "d").replace("Đ", "D")


def slugify_vault(text: str) -> str:
    """Chuẩn hóa tên kho thành mã định danh (slug) an toàn trên mọi hệ điều hành."""
    cleaned = _strip_accents(text).lower().strip()
    cleaned = re.sub(r"^\[[^\]]+\]\s*", "", cleaned)
    cleaned = re.sub(r"[^a-z0-9]+", "-", cleaned).strip("-")
    return cleaned or "vault"


def extract_drive_folder_id(raw: str) -> str:
    """Trích xuất Google Drive Folder ID từ URL hoặc chuỗi ID thuần."""
    s = (raw or "").strip()
    if not s:
        return ""
    for rx in _DRIVE_URL_PATTERNS:
        m = rx.search(s)
        if m:
            return m.group(1)
    return s


def detect_source_kind(source: str) -> Tuple[str, str]:
    """
    Nhận diện tự động nguồn kho dữ liệu:
    - Trả về `("local", resolved_path)` nếu là thư mục cục bộ (Windows/macOS/Linux/NAS/OneDrive...).
    - Trả về `("gdrive", folder_id)` nếu là URL hoặc Folder ID của Google Drive.
    """
    raw = (source or "").strip().strip('"').strip("'")
    if not raw:
        return "local", ""
    if "drive.google.com" in raw or "docs.google.com" in raw:
        return "gdrive", extract_drive_folder_id(raw)
    if _WIN_DRIVE_RE.match(raw) or raw.startswith(("/", "\\", "~", "./", "../", ".\\", "..\\")):
        return "local", str(Path(raw).expanduser().resolve())
    cand = Path(raw).expanduser()
    if cand.exists() and cand.is_dir():
        return "local", str(cand.resolve())
    if _DRIVE_ID_RE.match(raw):
        return "gdrive", raw
    return "local", str(cand.resolve())


def detect_vault_layout(
    index_or_root_items: Any,
    *,
    root_name: str = "",
    tong_quan_folder: str = "[00] TỔNG QUAN",
    danh_sach_folder: str = "[01] DANH SÁCH",
    quarantine_folder: str = "[07] KIỂM TRA",
) -> Tuple[str, Dict[str, str]]:
    """
    Tự nhận diện cấu trúc của bất kỳ kho nào:
    - Trả về `("academic_v7" | "general", discovered_known_ids)`.
    - Kho đạt `academic_v7` nếu có `[00] TỔNG QUAN`, `[07] KIỂM TRA` (hoặc `[99] KIỂM TRA`),
      hoặc >= 50% thư mục cấp 1 mang đánh số `[NN] ...`.
    """
    known: Dict[str, str] = {}
    root_folders: List[Dict[str, Any]] = []

    if isinstance(index_or_root_items, dict):
        idx = index_or_root_items
        rkey = root_name if root_name in idx else next(iter(idx.keys()), "")
        if rkey and isinstance(idx.get(rkey), dict):
            for it in idx[rkey].get("items", []):
                if it.get("mimeType") == "application/vnd.google-apps.folder":
                    root_folders.append(it)
            # Dò các thư mục hệ thống động trong toàn chỉ mục
            sys_rel_paths = [
                tong_quan_folder,
                f"{tong_quan_folder}/{danh_sach_folder}",
                f"{tong_quan_folder}/[02] NHẬT KÍ",
                f"{tong_quan_folder}/[03] QUẢN LÝ",
                quarantine_folder,
                "[99] KIỂM TRA",
                f"{quarantine_folder}/[00] TỔNG QUAN",
                f"{quarantine_folder}/[01] SHORTCUT LỖI 404",
                f"{quarantine_folder}/[02] SHORTCUT ĐÃ SAO CHÉP",
                f"{quarantine_folder}/[03] TỆP TRÙNG LẶP",
                f"{quarantine_folder}/[03] TỆP TRÙNG LẶP/[01] TỔNG QUAN TRÙNG LẶP",
                f"{quarantine_folder}/[04] NHẬP DỮ LIỆU",
            ]
            for rel in sys_rel_paths:
                full = f"{rkey}/{rel}"
                if full in idx and idx[full].get("id"):
                    known[rel] = str(idx[full]["id"])
    elif isinstance(index_or_root_items, list):
        for it in index_or_root_items:
            if isinstance(it, dict) and it.get("mimeType") == "application/vnd.google-apps.folder":
                root_folders.append(it)
                nm = str(it.get("name", ""))
                if nm in {tong_quan_folder, quarantine_folder, "[99] KIỂM TRA"} and it.get("id"):
                    known[nm] = str(it["id"])

    names = {str(f.get("name", "")) for f in root_folders}
    has_sys = (tong_quan_folder in names) or (quarantine_folder in names) or ("[99] KIỂM TRA" in names)
    numbered = sum(1 for n in names if _STT_FOLDER_RE.match(n))
    ratio = (numbered / len(names)) if names else 0.0
    detected_mode = "academic_v7" if (has_sys or (len(names) >= 2 and ratio >= 0.5)) else "general"
    return detected_mode, known


@dataclass
class VaultConfig:
    """Hồ sơ cấu hình cho một kho dữ liệu do KAS quản lý."""

    slug: str
    name: str
    source_kind: str = "local"  # "local" | "gdrive"
    root: str = ""  # đường dẫn cục bộ hoặc Drive Folder ID
    backend: str = "auto"  # "auto" | "local" | "gdrive-api" | "gdrive-cli"
    mode: str = "auto"  # "auto" | "academic_v7" | "general"
    detected_mode: str = ""
    tong_quan_folder: str = "[00] TỔNG QUAN"
    danh_sach_folder: str = "[01] DANH SÁCH"
    quarantine_folder: str = "[07] KIỂM TRA"
    master_sheet_id: str = ""
    master_sheet_list_id: str = ""
    known_ids: Dict[str, str] = field(default_factory=dict)
    topic_routes: Dict[str, List[str]] = field(default_factory=dict)
    created_utc: str = ""
    last_scan_utc: str = ""

    def effective_backend(self) -> str:
        if self.source_kind == "local" or self.backend == "local":
            return "local"
        if self.backend in {"gdrive-api", "api"}:
            return "api"
        if self.backend in {"gdrive-cli", "cli"}:
            return "cli"
        return "auto"

    def effective_mode(self) -> str:
        if self.mode in {"academic_v7", "general"}:
            return self.mode
        return self.detected_mode or "general"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "slug": self.slug,
            "name": self.name,
            "source_kind": self.source_kind,
            "root": self.root,
            "backend": self.backend,
            "mode": self.mode,
            "detected_mode": self.detected_mode,
            "effective_mode": self.effective_mode(),
            "effective_backend": self.effective_backend(),
            "tong_quan_folder": self.tong_quan_folder,
            "danh_sach_folder": self.danh_sach_folder,
            "quarantine_folder": self.quarantine_folder,
            "master_sheet_id": self.master_sheet_id,
            "master_sheet_list_id": self.master_sheet_list_id,
            "known_ids": dict(self.known_ids),
            "topic_routes": {k: list(v) for k, v in self.topic_routes.items()},
            "created_utc": self.created_utc,
            "last_scan_utc": self.last_scan_utc,
        }


def _toml_escape(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")
    return f'"{escaped}"'


def _dump_registry_toml(active_vault: str, vaults: Dict[str, VaultConfig]) -> str:
    lines: List[str] = [
        "# Karius Academic System (KAS) — Sổ đăng ký Đa Kho Dữ Liệu",
        f"active_vault = {_toml_escape(active_vault)}",
        "",
    ]
    for slug in sorted(vaults.keys()):
        v = vaults[slug]
        lines.append(f"[vaults.{slug}]")
        lines.append(f"name = {_toml_escape(v.name)}")
        lines.append(f"source_kind = {_toml_escape(v.source_kind)}")
        lines.append(f"root = {_toml_escape(v.root)}")
        lines.append(f"backend = {_toml_escape(v.backend)}")
        lines.append(f"mode = {_toml_escape(v.mode)}")
        if v.detected_mode:
            lines.append(f"detected_mode = {_toml_escape(v.detected_mode)}")
        lines.append(f"tong_quan_folder = {_toml_escape(v.tong_quan_folder)}")
        lines.append(f"danh_sach_folder = {_toml_escape(v.danh_sach_folder)}")
        lines.append(f"quarantine_folder = {_toml_escape(v.quarantine_folder)}")
        if v.master_sheet_id:
            lines.append(f"master_sheet_id = {_toml_escape(v.master_sheet_id)}")
        if v.master_sheet_list_id:
            lines.append(f"master_sheet_list_id = {_toml_escape(v.master_sheet_list_id)}")
        if v.created_utc:
            lines.append(f"created_utc = {_toml_escape(v.created_utc)}")
        if v.last_scan_utc:
            lines.append(f"last_scan_utc = {_toml_escape(v.last_scan_utc)}")
        if v.known_ids:
            lines.append(f"[vaults.{slug}.known_ids]")
            for k, val in sorted(v.known_ids.items()):
                lines.append(f"{_toml_escape(k)} = {_toml_escape(val)}")
        if v.topic_routes:
            lines.append(f"[vaults.{slug}.topic_routes]")
            for k, arr in sorted(v.topic_routes.items()):
                joined = ", ".join(_toml_escape(x) for x in arr)
                lines.append(f"{_toml_escape(k)} = [{joined}]")
        lines.append("")
    return "\n".join(lines)


class VaultRegistry:
    """Đọc/ghi sổ đăng ký nhiều kho tại `~/.config/kas/vaults.toml`."""

    def __init__(self, path: Optional[Path] = None) -> None:
        if path is not None:
            self.path = Path(path)
        else:
            env_cfg = os.environ.get("KAS_CONFIG_DIR")
            cfg_dir = Path(env_cfg).expanduser() if env_cfg else (Path.home() / ".config" / "kas")
            cfg_dir.mkdir(parents=True, exist_ok=True)
            self.path = cfg_dir / "vaults.toml"
        self.active_slug: str = ""
        self.vaults: Dict[str, VaultConfig] = {}
        self.reload()

    def reload(self) -> None:
        self.active_slug = ""
        self.vaults = {}
        if not self.path.exists():
            return
        try:
            doc = tomllib.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return
        self.active_slug = str(doc.get("active_vault") or "").strip()
        raw_vaults = doc.get("vaults") or {}
        if isinstance(raw_vaults, dict):
            for slug, rec in raw_vaults.items():
                if not isinstance(rec, dict):
                    continue
                vc = VaultConfig(
                    slug=str(slug),
                    name=str(rec.get("name") or slug),
                    source_kind=str(rec.get("source_kind") or "local"),
                    root=str(rec.get("root") or ""),
                    backend=str(rec.get("backend") or "auto"),
                    mode=str(rec.get("mode") or "auto"),
                    detected_mode=str(rec.get("detected_mode") or ""),
                    tong_quan_folder=str(rec.get("tong_quan_folder") or "[00] TỔNG QUAN"),
                    danh_sach_folder=str(rec.get("danh_sach_folder") or "[01] DANH SÁCH"),
                    quarantine_folder=str(rec.get("quarantine_folder") or "[07] KIỂM TRA"),
                    master_sheet_id=str(rec.get("master_sheet_id") or ""),
                    master_sheet_list_id=str(rec.get("master_sheet_list_id") or ""),
                    known_ids={str(k): str(v) for k, v in (rec.get("known_ids") or {}).items()},
                    topic_routes={str(k): [str(x) for x in v] for k, v in (rec.get("topic_routes") or {}).items() if isinstance(v, list)},
                    created_utc=str(rec.get("created_utc") or ""),
                    last_scan_utc=str(rec.get("last_scan_utc") or ""),
                )
                self.vaults[vc.slug] = vc
        if self.active_slug and self.active_slug not in self.vaults:
            self.active_slug = next(iter(sorted(self.vaults.keys())), "")
        elif not self.active_slug and self.vaults:
            self.active_slug = next(iter(sorted(self.vaults.keys())))

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        content = _dump_registry_toml(self.active_slug, self.vaults)
        tmp = self.path.with_suffix(".toml.tmp")
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, self.path)
        return self.path

    def list_vaults(self) -> List[VaultConfig]:
        return [self.vaults[k] for k in sorted(self.vaults.keys())]

    def get_vault(self, slug: str) -> Optional[VaultConfig]:
        return self.vaults.get((slug or "").strip())

    def get_active_vault(self) -> Optional[VaultConfig]:
        env_v = (os.environ.get("KAS_VAULT") or "").strip()
        if env_v and env_v in self.vaults:
            return self.vaults[env_v]
        if self.active_slug and self.active_slug in self.vaults:
            return self.vaults[self.active_slug]
        return None

    def add_vault(
        self,
        source: str,
        *,
        slug: Optional[str] = None,
        name: Optional[str] = None,
        backend: str = "auto",
        mode: str = "auto",
        tong_quan_folder: str = "[00] TỔNG QUAN",
        danh_sach_folder: str = "[01] DANH SÁCH",
        quarantine_folder: str = "[07] KIỂM TRA",
        activate: bool = True,
    ) -> VaultConfig:
        kind, normalized_root = detect_source_kind(source)
        if not normalized_root:
            raise ValueError("Nguồn kho dữ liệu không được để trống.")
        eff_backend = "local" if kind == "local" else (backend or "auto")
        if kind == "local":
            inferred_name = Path(normalized_root).name or "Local Vault"
        else:
            inferred_name = name or f"Drive Vault ({normalized_root[:8]})"
        final_name = (name or inferred_name).strip()
        final_slug = slugify_vault(slug or final_name)

        # Tự phát hiện nhanh cấu trúc nếu là thư mục cục bộ đã tồn tại
        detected_mode = ""
        known_ids: Dict[str, str] = {}
        if kind == "local" and Path(normalized_root).is_dir():
            root_p = Path(normalized_root)
            fake_items = [
                {
                    "id": f"loc:{child.name}",
                    "name": child.name,
                    "mimeType": "application/vnd.google-apps.folder" if child.is_dir() else "application/octet-stream",
                }
                for child in root_p.iterdir()
            ]
            detected_mode, known_ids = detect_vault_layout(
                fake_items,
                root_name=final_name,
                tong_quan_folder=tong_quan_folder,
                danh_sach_folder=danh_sach_folder,
                quarantine_folder=quarantine_folder,
            )

        vc = VaultConfig(
            slug=final_slug,
            name=final_name,
            source_kind=kind,
            root=normalized_root,
            backend=eff_backend,
            mode=mode if mode in {"auto", "academic_v7", "general"} else "auto",
            detected_mode=detected_mode,
            tong_quan_folder=tong_quan_folder,
            danh_sach_folder=danh_sach_folder,
            quarantine_folder=quarantine_folder,
            known_ids=known_ids,
            created_utc=_now_utc_iso(),
        )
        self.vaults[final_slug] = vc
        if activate or not self.active_slug:
            self.active_slug = final_slug
        self.save()
        return vc

    def set_active(self, slug: str) -> VaultConfig:
        vc = self.vaults.get(slug)
        if not vc:
            raise KeyError(f"Không tìm thấy kho `{slug}` trong {self.path}")
        self.active_slug = slug
        self.save()
        return vc

    def update_vault(self, slug: str, **updates: Any) -> VaultConfig:
        vc = self.vaults.get(slug)
        if not vc:
            raise KeyError(f"Không tìm thấy kho `{slug}`")
        for k, val in updates.items():
            if hasattr(vc, k) and val is not None:
                setattr(vc, k, val)
        self.save()
        return vc

    def remove_vault(self, slug: str) -> bool:
        if slug not in self.vaults:
            return False
        del self.vaults[slug]
        if self.active_slug == slug:
            self.active_slug = next(iter(sorted(self.vaults.keys())), "")
        self.save()
        return True
