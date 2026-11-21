"""Bộ máy thiết lập & tùy chỉnh quy tắc đặt tên linh hoạt theo kho hoặc toàn cục cho Karius Academic System (KAS)."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from karius_academic_system.core import config as _cfg
from karius_academic_system.core.utils import nfc, strip_accents

_DEFAULT_FORBIDDEN_CHARS = '<>:"/\\|?*'
_DEFAULT_IGNORED_FOLDERS = [
    ".git",
    ".obsidian",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "MACOSX",
    "__MACOSX",
]

FOLDER_INDEX_STYLES: Dict[str, Dict[str, str]] = {
    "bracket_2": {"label": "[01] Ngoặc vuông 2 chữ số", "example": "[01] HỌC THUẬT"},
    "bracket_3": {"label": "[001] Ngoặc vuông 3 chữ số", "example": "[001] HỌC THUẬT"},
    "dot_2": {"label": "01. Số + dấu chấm", "example": "01. HỌC THUẬT"},
    "dash_2": {"label": "01 - Số + gạch ngang", "example": "01 - HỌC THUẬT"},
    "none": {"label": "Không dùng tiền tố số", "example": "Học Thuật"},
}

FOLDER_CASE_OPTIONS = ("upper", "title", "lower", "snake", "kebab", "preserve")
FILE_CASE_OPTIONS = ("title", "sentence", "lower", "upper", "snake", "kebab", "preserve")

_INDEX_PATTERNS: Dict[str, re.Pattern[str]] = {
    "bracket_2": re.compile(r"^\[(\d{2,3})\] (\S.*\S|\S)$"),
    "bracket_3": re.compile(r"^\[(\d{3})\] (\S.*\S|\S)$"),
    "dot_2": re.compile(r"^(\d{2,3})\. (\S.*\S|\S)$"),
    "dash_2": re.compile(r"^(\d{2,3}) - (\S.*\S|\S)$"),
}
_ANY_INDEX_PREFIX = re.compile(r"^\s*(?:\[(\d{1,3})\]|(\d{1,3})(?:\.|\s*-\s*))\s*")
_RE_STT_PREFIX = re.compile(r"^\s*\[\d{1,3}\]\s*")
_RE_NUM_PREFIX = re.compile(r"^\d{1,3}[_\-. ]")
_RE_DATE_PREFIX = re.compile(r"^(\d{2,4}_)?\d{6}_")
_RE_EXT = re.compile(r"\.([A-Za-z0-9]{1,6})$")


@dataclass
class NamingRuleSet:
    """Cấu hình quy tắc đặt tên đầy đủ (hỗ trợ preset + tùy chỉnh chi tiết theo kho hoặc toàn cục)."""

    preset: str = "academic_v6"
    # Quy tắc thư mục
    folder_require_index_prefix: bool = True
    folder_index_style: str = "bracket_2"
    folder_case: str = "upper"
    folder_forbid_underscore: bool = True
    # Quy tắc tệp tin
    file_forbid_index_prefix: bool = True
    file_forbid_date_prefix: bool = True
    file_case: str = "title"
    file_separator: str = " - "
    file_require_extra_info: bool = True
    file_forbid_underscore: bool = True
    # Quy tắc chung
    lowercase_extension: bool = True
    unicode_nfc: bool = True
    strip_accents: bool = False
    forbid_double_spaces: bool = True
    forbid_edge_spaces: bool = True
    max_name_length: int = 180
    forbidden_chars: str = _DEFAULT_FORBIDDEN_CHARS
    # Danh sách tùy biến nâng cao
    acronyms_upper: Dict[str, str] = field(default_factory=dict)
    lowercase_particles: List[str] = field(default_factory=list)
    ignored_folders: List[str] = field(default_factory=lambda: list(_DEFAULT_IGNORED_FOLDERS))
    custom_replacements: Dict[str, str] = field(default_factory=dict)
    custom_regex_blacklist: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NamingRuleSet":
        base_preset = str(data.get("preset") or "academic_v6")
        if base_preset in NAMING_PRESETS:
            merged = dict(NAMING_PRESETS[base_preset]["rules"])
        else:
            merged = asdict(cls())
        merged.update({k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        # Chuẩn hóa kiểu dữ liệu an toàn
        if merged.get("folder_index_style") not in FOLDER_INDEX_STYLES:
            merged["folder_index_style"] = "bracket_2"
        if merged.get("folder_case") not in FOLDER_CASE_OPTIONS:
            merged["folder_case"] = "upper"
        if merged.get("file_case") not in FILE_CASE_OPTIONS:
            merged["file_case"] = "title"
        try:
            merged["max_name_length"] = max(0, int(merged.get("max_name_length", 180)))
        except (TypeError, ValueError):
            merged["max_name_length"] = 180
        ac = merged.get("acronyms_upper")
        if isinstance(ac, list):
            merged["acronyms_upper"] = {str(x).strip().lower(): str(x).strip() for x in ac if str(x).strip()}
        elif isinstance(ac, dict):
            merged["acronyms_upper"] = {str(k).strip().lower(): str(v).strip() for k, v in ac.items() if str(k).strip()}
        else:
            merged["acronyms_upper"] = {}
        merged["lowercase_particles"] = [
            str(x).strip().lower() for x in (merged.get("lowercase_particles") or []) if str(x).strip()
        ]
        merged["ignored_folders"] = [
            str(x).strip() for x in (merged.get("ignored_folders") or []) if str(x).strip()
        ]
        cr = merged.get("custom_replacements")
        merged["custom_replacements"] = (
            {str(k): str(v) for k, v in cr.items() if str(k)} if isinstance(cr, dict) else {}
        )
        merged["custom_regex_blacklist"] = [
            str(x).strip() for x in (merged.get("custom_regex_blacklist") or []) if str(x).strip()
        ]
        return cls(**merged)


NAMING_PRESETS: Dict[str, Dict[str, Any]] = {
    "academic_v6": {
        "name": "Chuẩn Học Thuật KAS V6",
        "description": "Thư mục `[01] TÊN IN HOA CÓ DẤU`; tệp `Tên Viết Hoa Đầu Chữ - Thông Tin Bổ Sung.ext`; chuẩn hóa NFC & viết tắt học thuật.",
        "rules": {
            "preset": "academic_v6",
            "folder_require_index_prefix": True,
            "folder_index_style": "bracket_2",
            "folder_case": "upper",
            "folder_forbid_underscore": True,
            "file_forbid_index_prefix": True,
            "file_forbid_date_prefix": True,
            "file_case": "title",
            "file_separator": " - ",
            "file_require_extra_info": True,
            "file_forbid_underscore": True,
            "lowercase_extension": True,
            "unicode_nfc": True,
            "strip_accents": False,
            "forbid_double_spaces": True,
            "forbid_edge_spaces": True,
            "max_name_length": 180,
            "forbidden_chars": _DEFAULT_FORBIDDEN_CHARS,
            "ignored_folders": list(_DEFAULT_IGNORED_FOLDERS),
        },
    },
    "general_clean": {
        "name": "Gọn Sạch Phổ Thông",
        "description": "Không bắt buộc `[STT]` cho thư mục và không ép kiểu chữ; chỉ bắt lỗi khoảng trắng thừa/kép, ký tự cấm, NFD, đuôi viết hoa & rác OS.",
        "rules": {
            "preset": "general_clean",
            "folder_require_index_prefix": False,
            "folder_index_style": "none",
            "folder_case": "preserve",
            "folder_forbid_underscore": False,
            "file_forbid_index_prefix": False,
            "file_forbid_date_prefix": False,
            "file_case": "preserve",
            "file_separator": "",
            "file_require_extra_info": False,
            "file_forbid_underscore": False,
            "lowercase_extension": True,
            "unicode_nfc": True,
            "strip_accents": False,
            "forbid_double_spaces": True,
            "forbid_edge_spaces": True,
            "max_name_length": 180,
            "forbidden_chars": _DEFAULT_FORBIDDEN_CHARS,
            "ignored_folders": list(_DEFAULT_IGNORED_FOLDERS),
        },
    },
    "snake_case_dev": {
        "name": "Kỹ Thuật snake_case",
        "description": "Không dấu tiếng Việt, chữ thường nối bằng dấu gạch dưới `_` — tối ưu cho kho mã nguồn, bộ dữ liệu nghiên cứu & tự động hóa.",
        "rules": {
            "preset": "snake_case_dev",
            "folder_require_index_prefix": False,
            "folder_index_style": "none",
            "folder_case": "snake",
            "folder_forbid_underscore": False,
            "file_forbid_index_prefix": True,
            "file_forbid_date_prefix": False,
            "file_case": "snake",
            "file_separator": "_",
            "file_require_extra_info": False,
            "file_forbid_underscore": False,
            "lowercase_extension": True,
            "unicode_nfc": True,
            "strip_accents": True,
            "forbid_double_spaces": True,
            "forbid_edge_spaces": True,
            "max_name_length": 140,
            "forbidden_chars": _DEFAULT_FORBIDDEN_CHARS,
            "ignored_folders": list(_DEFAULT_IGNORED_FOLDERS),
        },
    },
    "kebab_web": {
        "name": "Chuẩn Xuất Bản kebab-case",
        "description": "Không dấu tiếng Việt, chữ thường nối bằng dấu gạch ngang `-` — phù hợp xuất bản web, tài liệu kỹ thuật & bài viết Markdown.",
        "rules": {
            "preset": "kebab_web",
            "folder_require_index_prefix": False,
            "folder_index_style": "none",
            "folder_case": "kebab",
            "folder_forbid_underscore": True,
            "file_forbid_index_prefix": True,
            "file_forbid_date_prefix": False,
            "file_case": "kebab",
            "file_separator": "-",
            "file_require_extra_info": False,
            "file_forbid_underscore": True,
            "lowercase_extension": True,
            "unicode_nfc": True,
            "strip_accents": True,
            "forbid_double_spaces": True,
            "forbid_edge_spaces": True,
            "max_name_length": 140,
            "forbidden_chars": _DEFAULT_FORBIDDEN_CHARS,
            "ignored_folders": list(_DEFAULT_IGNORED_FOLDERS),
        },
    },
}


def global_naming_rules_path() -> Path:
    return _cfg.user_config_dir() / "naming_rules.json"


def vault_naming_rules_path() -> Path:
    return _cfg.data_dir() / "naming_rules.json"


def has_custom_naming_rules(scope: str = "any") -> bool:
    if scope == "vault":
        return vault_naming_rules_path().exists()
    if scope == "global":
        return global_naming_rules_path().exists()
    return vault_naming_rules_path().exists() or global_naming_rules_path().exists()


def preset_rules(preset_name: str) -> NamingRuleSet:
    if preset_name not in NAMING_PRESETS:
        raise ValueError(f"Preset quy tắc không tồn tại: `{preset_name}`. Hợp lệ: {', '.join(NAMING_PRESETS)}")
    return NamingRuleSet.from_dict(NAMING_PRESETS[preset_name]["rules"])


def get_active_naming_rules(vault_mode: Optional[str] = None) -> Tuple[NamingRuleSet, str]:
    """Trả về `(NamingRuleSet, nguồn)` theo thứ tự ưu tiên: kho hiện tại → toàn cục → mặc định theo chế độ kho."""
    vp = vault_naming_rules_path()
    if vp.exists():
        try:
            return NamingRuleSet.from_dict(json.loads(vp.read_text(encoding="utf-8"))), f"vault:{vp}"
        except Exception:
            pass
    gp = global_naming_rules_path()
    if gp.exists():
        try:
            return NamingRuleSet.from_dict(json.loads(gp.read_text(encoding="utf-8"))), f"global:{gp}"
        except Exception:
            pass
    eff_mode = vault_mode or _cfg.effective_vault_mode()
    if eff_mode == "general":
        return preset_rules("general_clean"), "default:general_clean"
    return preset_rules("academic_v6"), "default:academic_v6"


def save_naming_rules(rules: NamingRuleSet, scope: str = "vault") -> Path:
    """Lưu quy tắc đặt tên cho kho hiện hành (`vault`) hoặc mặc định toàn cục (`global`)."""
    target = global_naming_rules_path() if scope == "global" else vault_naming_rules_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rules.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(target)
    return target


def reset_naming_rules(scope: str = "vault") -> bool:
    """Xóa cấu hình tùy chỉnh để quay về quy tắc mặc định theo chế độ kho."""
    target = global_naming_rules_path() if scope == "global" else vault_naming_rules_path()
    if target.exists():
        target.unlink()
        return True
    return False


def apply_naming_preset(preset_name: str, scope: str = "vault") -> Tuple[NamingRuleSet, Path]:
    rules = preset_rules(preset_name)
    path = save_naming_rules(rules, scope=scope)
    return rules, path


def _merged_acronyms(rules: NamingRuleSet) -> Dict[str, str]:
    base = dict(_cfg.CONFIG.get("acronyms_upper", {}))
    base.update({k.lower(): v for k, v in rules.acronyms_upper.items()})
    return base


def _merged_lowercase_words(rules: NamingRuleSet) -> set[str]:
    base = set(_cfg.CONFIG.get("lowercase_prefix_words", [])) | set(_cfg.CONFIG.get("title_exceptions", []))
    base.update(w.lower() for w in rules.lowercase_particles)
    return base


def _to_slug_case(text: str, sep: str, do_strip_accents: bool = True) -> str:
    s = strip_accents(text) if do_strip_accents else text
    s = s.lower()
    s = re.sub(r"[^\w\s-]+", " ", s, flags=re.UNICODE)
    s = re.sub(r"[\s_\-]+", sep, s).strip(sep)
    return s


def _transform_case(text: str, case_mode: str, acronyms: Dict[str, str], do_strip_accents: bool = False) -> str:
    from karius_academic_system.core.naming import title_case_vn

    s = strip_accents(text) if do_strip_accents else text
    if case_mode == "upper":
        return s.upper()
    if case_mode == "lower":
        return s.lower()
    if case_mode == "title":
        return title_case_vn(s, acronyms=acronyms)
    if case_mode == "sentence":
        s_clean = re.sub(r"\s{2,}", " ", s.strip())
        return (s_clean[:1].upper() + s_clean[1:].lower()) if s_clean else s_clean
    if case_mode == "snake":
        return _to_slug_case(s, "_", do_strip_accents=do_strip_accents)
    if case_mode == "kebab":
        return _to_slug_case(s, "-", do_strip_accents=do_strip_accents)
    return s


def _apply_custom_replacements(text: str, replacements: Dict[str, str]) -> str:
    out = text
    for src, dst in replacements.items():
        if src:
            out = out.replace(src, dst)
    return out


def _format_index_prefix(num_str: str, style: str) -> str:
    if style == "bracket_2":
        return f"[{num_str.zfill(2)}] "
    if style == "bracket_3":
        return f"[{num_str.zfill(3)}] "
    if style == "dot_2":
        return f"{num_str.zfill(2)}. "
    if style == "dash_2":
        return f"{num_str.zfill(2)} - "
    return ""


def _is_ignored_folder(name: str, parent_path: str, rules: NamingRuleSet) -> bool:
    ignored = {x.lower() for x in rules.ignored_folders}
    if name.lower() in ignored or name.startswith("."):
        return True
    for seg in parent_path.split("/"):
        if seg.lower() in ignored:
            return True
    return False


def evaluate_name_with_rules(
    name: str,
    *,
    is_folder: bool,
    mime: str = "",
    parent_path: str = "",
    rules: Optional[NamingRuleSet] = None,
) -> List[Tuple[str, str, str]]:
    """Kiểm tra tên tệp/thư mục theo `NamingRuleSet` tùy chỉnh (trả về danh sách `(mức độ, mã, mô tả)`)."""
    from karius_academic_system.core.naming import (
        GOOGLE_NATIVE_MIMES,
        _is_cased_alpha,
        is_tech_exception,
        split_ext,
    )

    if rules is None:
        rules, _ = get_active_naming_rules()

    issues: List[Tuple[str, str, str]] = []
    if is_folder and _is_ignored_folder(name, parent_path, rules):
        return issues
    if not is_folder and is_tech_exception(parent_path, name):
        return issues
    if not is_folder and name == "TongQuan.md" and rules.preset == "academic_v6":
        issues.append(("CẢNH BÁO", "TEP_HE_THONG_CU", "Tệp `TongQuan.md` cũ — cần chuẩn hóa thành `Tổng Quan Hệ Thống - <Tên Thư Mục>.md`"))
        return issues

    if rules.forbid_edge_spaces and name != name.strip():
        issues.append(("LỖI", "KHOANG_TRANG_THUA", "Có khoảng trắng ở đầu/cuối tên"))
    if rules.forbid_double_spaces and "  " in name:
        issues.append(("LỖI", "KHOANG_TRANG_DOI", "Có hai khoảng trắng liên tiếp"))
    if rules.unicode_nfc and name != nfc(name):
        issues.append(("CẢNH BÁO", "UNICODE_NFD", "Tên dùng Unicode tổ hợp (NFD) — nên chuẩn hóa NFC"))
    if rules.max_name_length > 0 and len(name) > rules.max_name_length:
        issues.append(("CẢNH BÁO", "TEN_QUA_DAI", f"Độ dài tên ({len(name)}) vượt giới hạn {rules.max_name_length} ký tự"))
    bad_chars = [ch for ch in rules.forbidden_chars if ch in name]
    if bad_chars:
        issues.append(("LỖI", "KY_TU_CAM", f"Chứa ký tự bị cấm: {' '.join(sorted(set(bad_chars)))}"))
    if rules.strip_accents and name != strip_accents(name):
        issues.append(("CẢNH BÁO", "CO_DAU_TIENG_VIET", "Quy tắc hiện tại yêu cầu tên không dấu tiếng Việt"))
    for pat in rules.custom_regex_blacklist:
        try:
            if re.search(pat, name):
                issues.append(("CẢNH BÁO", "VI_PHAM_REGEX_TUY_CHINH", f"Khớp mẫu cấm tùy chỉnh `{pat}`"))
        except re.error:
            pass

    stripped = name.strip()
    if is_folder:
        body = stripped
        if rules.folder_require_index_prefix and rules.folder_index_style != "none":
            rx = _INDEX_PATTERNS.get(rules.folder_index_style, _INDEX_PATTERNS["bracket_2"])
            m = rx.match(stripped)
            if not m:
                ex = FOLDER_INDEX_STYLES[rules.folder_index_style]["example"]
                issues.append(("LỖI", "THIEU_STT", f"Thư mục phải có tiền tố đúng mẫu `{ex}`"))
                body = _ANY_INDEX_PREFIX.sub("", stripped)
            else:
                body = m.group(2)
        if rules.folder_forbid_underscore and "_" in body:
            issues.append(("LỖI", "GACH_DUOI", "Không dùng dấu gạch dưới `_` trong tên thư mục"))
        letters = [c for c in body if _is_cased_alpha(c)]
        if rules.folder_case == "upper" and letters and any(c.islower() for c in letters):
            issues.append(("LỖI", "CHUA_IN_HOA", "Tên thư mục phải viết IN HOA toàn bộ"))
        elif rules.folder_case == "lower" and letters and any(c.isupper() for c in letters):
            issues.append(("CẢNH BÁO", "CHUA_CHU_THUONG", "Tên thư mục phải viết chữ thường"))
        elif rules.folder_case == "snake" and not re.match(r"^[a-z0-9]+(?:_[a-z0-9]+)*$", body):
            issues.append(("CẢNH BÁO", "CHUA_SNAKE_CASE", "Tên thư mục phải theo chuẩn `snake_case`"))
        elif rules.folder_case == "kebab" and not re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", body):
            issues.append(("CẢNH BÁO", "CHUA_KEBAB_CASE", "Tên thư mục phải theo chuẩn `kebab-case`"))
        return issues

    # Tệp tin
    base, ext = split_ext(stripped, mime)
    if rules.lowercase_extension and ext and ext != ext.lower():
        issues.append(("LỖI", "DUOI_VIET_HOA", f"Đuôi tệp phải viết thường (`.{ext}` → `.{ext.lower()}`)"))
    if mime in GOOGLE_NATIVE_MIMES:
        m = _RE_EXT.search(name)
        if m and m.group(1).lower() in {"docx", "xlsx", "pptx", "pdf", "doc", "xls", "ppt", "gdoc", "gsheet"}:
            issues.append(("CẢNH BÁO", "DUOI_THUA_GOOGLE", "Tệp Google gốc/Shortcut không nên có phần mở rộng"))
    if rules.file_forbid_index_prefix and _RE_STT_PREFIX.match(base):
        issues.append(("LỖI", "TIEN_TO_STT", "Tên tệp không được bắt đầu bằng `[STT]`"))
    elif rules.file_forbid_date_prefix and _RE_DATE_PREFIX.match(base):
        issues.append(("LỖI", "TIEN_TO_NGAY", "Tên tệp không được bắt đầu bằng chuỗi ngày `YYMMDD_`"))
    elif rules.file_forbid_index_prefix and _RE_NUM_PREFIX.match(base) and "_" in base[:5]:
        issues.append(("CẢNH BÁO", "TIEN_TO_SO", "Tên tệp bắt đầu bằng số thứ tự kiểu cũ"))
    if rules.file_forbid_underscore and "_" in base:
        issues.append(("CẢNH BÁO", "GACH_DUOI", "Nên thay dấu gạch dưới `_` bằng khoảng trắng"))
    if rules.file_require_extra_info and rules.file_separator and rules.file_separator not in base:
        issues.append(("GỢI Ý", "THIEU_THONG_TIN_BO_SUNG", f"Chưa có phần phân cách `{rules.file_separator}Thông Tin Bổ Sung`"))

    main = base.split(rules.file_separator, 1)[0] if (rules.file_separator and rules.file_separator in base) else base
    if rules.file_case == "title":
        low_allowed = _merged_lowercase_words(rules)
        words = [w for w in re.split(r"\s+", main) if w]
        bad_title = False
        for w in words:
            core = w.strip("()[]{}\"'“”‘’,.;:!?«»+-")
            if not core:
                continue
            low = core.lower()
            if low in low_allowed or strip_accents(low) in low_allowed:
                continue
            if re.match(r"^\([a-z][+-]?\)$", w.strip()) or re.match(r"^(?:e-[A-Z]|i[A-Z])", core):
                continue
            if _is_cased_alpha(core[0]) and not core[0].isupper():
                bad_title = True
                break
        if bad_title:
            issues.append(("CẢNH BÁO", "CHUA_TITLE_CASE", "Tên chính nên viết hoa chữ cái đầu mỗi từ"))
    elif rules.file_case == "snake" and base and not re.match(r"^[a-z0-9]+(?:_[a-z0-9]+)*$", base):
        issues.append(("CẢNH BÁO", "CHUA_SNAKE_CASE", "Tên tệp phải theo chuẩn `snake_case`"))
    elif rules.file_case == "kebab" and base and not re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", base):
        issues.append(("CẢNH BÁO", "CHUA_KEBAB_CASE", "Tên tệp phải theo chuẩn `kebab-case`"))
    elif rules.file_case == "lower":
        letters = [c for c in base if _is_cased_alpha(c)]
        if letters and any(c.isupper() for c in letters):
            issues.append(("CẢNH BÁO", "CHUA_CHU_THUONG", "Tên tệp phải viết chữ thường"))
    elif rules.file_case == "upper":
        letters = [c for c in base if _is_cased_alpha(c)]
        if letters and any(c.islower() for c in letters):
            issues.append(("CẢNH BÁO", "CHUA_IN_HOA", "Tên tệp phải viết IN HOA"))
    elif rules.file_case == "sentence":
        first_alpha = next((c for c in main if _is_cased_alpha(c)), "")
        if first_alpha and not first_alpha.isupper():
            issues.append(("CẢNH BÁO", "CHUA_VIET_HOA_DAU_CAU", "Chữ cái đầu câu cần viết hoa"))

    if rules.file_separator == " - " and re.search(r"\s-\S|\S-\s", base) and " - " not in base:
        issues.append(("CẢNH BÁO", "PHAN_CACH_SAI", "Dấu phân cách phải là ` - ` (có khoảng trắng hai bên)"))
    return issues


def normalize_name_with_rules(
    name: str,
    *,
    is_folder: bool,
    mime: str = "",
    rules: Optional[NamingRuleSet] = None,
) -> str:
    """Đề xuất tên chuẩn hóa theo `NamingRuleSet` tùy chỉnh (bảo toàn phần mở rộng & chống hỏng tên)."""
    from karius_academic_system.core.naming import GOOGLE_NATIVE_MIMES, split_ext

    if rules is None:
        rules, _ = get_active_naming_rules()

    new = nfc(name) if rules.unicode_nfc else name
    if rules.forbid_edge_spaces:
        new = new.strip()
    if new.startswith("- "):
        return name
    if rules.custom_replacements:
        new = _apply_custom_replacements(new, rules.custom_replacements)
    for ch in rules.forbidden_chars:
        if ch in new:
            new = new.replace(ch, " ")
    if rules.forbid_double_spaces:
        new = re.sub(r"\s{2,}", " ", new).strip()

    acronyms = _merged_acronyms(rules)
    if is_folder:
        m = _ANY_INDEX_PREFIX.match(new)
        num_str = (m.group(1) or m.group(2)) if m else ""
        body = new[m.end():].strip() if m else new
        if rules.folder_forbid_underscore:
            body = re.sub(r"\s*_+\s*", " ", body).strip()
        body = _transform_case(body, rules.folder_case, acronyms, do_strip_accents=rules.strip_accents)
        if rules.folder_require_index_prefix and rules.folder_index_style != "none" and num_str:
            out = _format_index_prefix(num_str, rules.folder_index_style) + body if body else new
        elif num_str and not rules.folder_require_index_prefix and rules.folder_case in {"preserve", "upper", "title"}:
            # Giữ nguyên số đầu nếu người dùng không yêu cầu đổi định dạng tiền tố
            out = f"{new[:m.end()]}{body}" if m else body
        else:
            out = body or new
        return out[: rules.max_name_length].rstrip() if rules.max_name_length > 0 else out

    if mime in GOOGLE_NATIVE_MIMES:
        m_ext = _RE_EXT.search(new)
        if m_ext and m_ext.group(1).lower() in {"pdf", "docx", "xlsx", "pptx", "doc", "xls", "ppt"}:
            new = new[: m_ext.start()].strip()

    base, ext = split_ext(new, mime)
    if rules.file_forbid_index_prefix and _RE_STT_PREFIX.match(base):
        base = _RE_STT_PREFIX.sub("", base).strip()
    if rules.file_forbid_underscore and "_" in base and not _RE_DATE_PREFIX.match(base):
        base = re.sub(r"\s*_+\s*", " ", base).strip()
    if rules.file_separator == " - " and re.search(r"\s-\S|\S-\s", base):
        base = re.sub(r"\s+-\s*|\s*-\s+", " - ", base)

    if rules.file_case in {"snake", "kebab"}:
        base = _transform_case(base, rules.file_case, acronyms, do_strip_accents=True)
    elif rules.file_case != "preserve":
        if rules.file_separator and rules.file_separator in base:
            p1, p2 = base.split(rules.file_separator, 1)
            base = (
                _transform_case(p1, rules.file_case, acronyms, do_strip_accents=rules.strip_accents)
                + rules.file_separator
                + (strip_accents(p2.strip()) if rules.strip_accents else p2.strip())
            )
        else:
            base = _transform_case(base, rules.file_case, acronyms, do_strip_accents=rules.strip_accents)
    elif rules.strip_accents:
        base = strip_accents(base)

    if rules.forbid_double_spaces:
        base = re.sub(r"\s{2,}", " ", base).strip()

    ext_out = ext.lower() if (ext and rules.lowercase_extension) else ext
    out = f"{base}.{ext_out}" if ext_out else base
    if rules.max_name_length > 0 and len(out) > rules.max_name_length:
        reserve = len(ext_out) + 1 if ext_out else 0
        out = (base[: max(8, rules.max_name_length - reserve)].rstrip() + (f".{ext_out}" if ext_out else ""))
    return out


def preview_naming(
    name: str,
    *,
    is_folder: bool = False,
    mime: str = "",
    rules: Optional[NamingRuleSet] = None,
) -> Dict[str, Any]:
    """Chạy thử & kiểm tra tức thì 1 tên tệp/thư mục theo `NamingRuleSet` (dùng cho CLI `kas rules test`, Web UI và AI Agent)."""
    if rules is None:
        rules, _ = get_active_naming_rules()
    issues = evaluate_name_with_rules(name, is_folder=is_folder, mime=mime, rules=rules)
    suggested = normalize_name_with_rules(name, is_folder=is_folder, mime=mime, rules=rules)
    return {
        "original": name,
        "suggested": suggested,
        "changed": suggested != name,
        "compliant": len(issues) == 0,
        "preset": rules.preset,
        "is_folder": is_folder,
        "issues": [{"severity": s, "code": c, "description": d} for s, c, d in issues],
    }
