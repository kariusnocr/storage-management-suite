"""Chuẩn Đặt Tên & Chính Sách Tinh Gọn Thông Minh Danh Mục Hệ Thống (Chuẩn Danh Mục V7).

Giải quyết triệt để 4 nhóm lỗi thực tế trên kho `[A] STORAGE`:
1. Chống trùng tên tuyệt đối (Zero-Collision): Tự động gắn `, <Ngữ Cảnh Cha>` khi tên danh mục
   thuộc nhóm tên chung (`Handout`, `Key`, `Slide`, `Tập 1`...) hoặc trùng tên trên toàn cây.
2. Duy nhất một dấu phân cách `" - "`:
   - `[USSH] TRƯỜNG ĐH KHXH&NV` → `USSH: Trường ĐH KHXH&NV` (không sinh thêm `" - "` thứ 2).
   - `TÔN GIÁO - TÍN NGƯỠNG` → `Tôn Giáo – Tín Ngưỡng` (dùng en-dash `–` cho cụm nội bộ).
   - Chuẩn hóa ngoặc dính chữ (`12(CHƯƠNG-1)TỪ` → `12 (Chương 1) Từ`).
3. Chính sách Tinh gọn Thông minh (Phương án 2):
   - Loại trừ tuyệt đối thư mục rác/kỹ thuật (`MACOSX`, `__MACOSX`, `.obsidian`, `.git`, ...).
   - Lập bảng riêng cho gốc (`depth=0`), cấp `1..4`, cấp `5` không rỗng (`>= 1` mục), và thăng hạng
     cấp `6` quy mô lớn (`>= 15` mục trực tiếp) — giảm từ `2.741` xuống `~493` bảng tinh gọn.
4. Kiểm toán 5 mã chuyên biệt: `DANH_MUC_RAC_KY_THUAT`, `DANH_MUC_MO_COI`, `DANH_MUC_TRUNG_TEN`,
   `DANH_MUC_SAI_TEN`, `DANH_MUC_CO_THE_TINH_GON`.
"""

from __future__ import annotations

import collections
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from storage_suite.core.config import (
    DANH_SACH_PATH,
    FOLDER_MIME,
    ROOT_NAME,
    SHEET_MIME,
    TONG_QUAN_FOLDER,
    catalog_policy,
    is_in_danh_sach_tree,
)
from storage_suite.core.models import AuditFinding, CatalogDecision, UndoAction
from storage_suite.core.naming import catalog_folder_for_path, title_case_vn
from storage_suite.core.utils import nfc, strip_accents

SHEET_PREFIX = "Danh Mục Hệ Thống - "
TONG_QUAN_PREFIX = "Tổng Quan Hệ Thống - "


def _effective_policy(policy: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    base = catalog_policy()
    if policy:
        base.update(policy)
    return base


def _strip_stt(segment: str) -> str:
    return re.sub(r"^\[\d{1,3}\]\s*", "", nfc(segment or "").strip()).strip()


def is_excluded_catalog_folder(folder_path: str, policy: Optional[Dict[str, Any]] = None) -> bool:
    """Trả về True nếu đường dẫn chứa thư mục rác/kỹ thuật không được phép lập Danh Mục."""
    pol = _effective_policy(policy)
    excl = {s.upper() for s in pol.get("exclude_names") or ("__MACOSX", "MACOSX", ".OBSIDIAN", ".GIT", "__PYCACHE__", "NODE_MODULES", "TESTS")}
    clean = nfc(folder_path or "").strip().rstrip("/")
    if not clean or clean == ROOT_NAME:
        return False
    parts = clean.split("/")[1:] if clean.startswith(ROOT_NAME + "/") else clean.split("/")
    for part in parts:
        raw_upper = part.strip().upper()
        body_upper = _strip_stt(part).upper()
        if raw_upper in excl or body_upper in excl:
            return True
        if raw_upper.startswith(".") or body_upper.endswith("MACOSX"):
            return True
        if part == TONG_QUAN_FOLDER:
            return True
    return False


def normalize_catalog_segment(folder_name: str) -> str:
    """
    Chuẩn hóa 1 đoạn tên thư mục thành phần tên hiển thị theo Chuẩn Danh Mục V7:
    - Bỏ `[STT]` ở đầu (`[01] HỌC THUẬT` → `Học Thuật`).
    - Chuyển tiền tố mã `[USSH] TRƯỜNG ĐH KHXH&NV` → `USSH: Trường ĐH KHXH&NV` (không tạo `" - "` kép).
    - Chuyển cụm gạch nối nội bộ ` - ` → ` – ` (en-dash) để bảo toàn duy nhất 1 dấu `" - "` theo Chuẩn V6.
    - Sửa ngoặc đơn dính chữ (`Toán 12(CHƯƠNG-1)TỪ` → `Toán 12 (Chương 1) Từ`), bỏ đuôi `.pdf`/`.docx`.
    """
    body = _strip_stt(folder_name)
    if not body:
        return ""
    # Khối định danh `[CODE] BODY` → `CODE: BODY`
    m_code = re.match(r"^\[([^\]]+)\]\s*(.+)$", body)
    code_prefix = ""
    if m_code:
        code_prefix = m_code.group(1).strip()
        body = m_code.group(2).strip()
    else:
        body = re.sub(r"^\[([^\]]+)\]$", r"\1", body)

    # Xóa đuôi tệp bị dính trong tên thư mục cũ (`SÁCH TÂM LINH - PDF`)
    body = re.sub(r"\s*[-–]\s*(pdf|docx?|xlsx?|pptx?|epub)\s*$", "", body, flags=re.I)
    body = re.sub(r"\.(pdf|docx?|xlsx?|pptx?)$", "", body, flags=re.I)
    body = re.sub(r"\s*_+\s*", " ", body)

    # Tách ngoặc đơn dính chữ: `12(CHƯƠNG-1)TỪ` → `12 (CHƯƠNG 1) TỪ`
    body = re.sub(r"(\S)\(", r"\1 (", body)
    body = re.sub(r"\)(\S)", r") \1", body)
    body = re.sub(r"\(([^)]+)\)", lambda m: "(" + re.sub(r"\s*-\s*", " ", m.group(1).strip()) + ")", body)

    # Chuẩn hóa dấu gạch nối nội bộ có khoảng trắng thành en-dash `–` (bảo toàn `" - "` duy nhất)
    body = re.sub(r"\s+[-–—]\s+", " – ", body)
    # Tách gạch nối đơn bị dính giữa chữ thường/hoa không phải mã viết tắt như `RC-Nguyễn`
    body = re.sub(r"(?<=[A-Za-zÀ-ỹ]{2})\s*-\s*(?=[A-ZÀ-Ỹ][a-zà-ỹ]{2,})", " – ", body)
    body = re.sub(r"\s{2,}", " ", body).strip()

    formatted_body = title_case_vn(body)
    if code_prefix:
        # Giữ nguyên mã đơn khối (`USSH`, `VNU-LIC`, `PHI1007`, `QH-2026-X-TR`); cụm nhiều từ dùng Title Case
        is_code_token = (" " not in code_prefix) and (code_prefix.isupper() or any(ch.isdigit() for ch in code_prefix))
        formatted_code = code_prefix if is_code_token else title_case_vn(code_prefix)
        return f"{formatted_code}: {formatted_body}" if formatted_body else formatted_code
    return formatted_body


def normalize_catalog_title(
    folder_path: str,
    context_segments: Optional[Sequence[str]] = None,
    *,
    is_list_copy: bool = False,
) -> str:
    """
    Sinh tên bảng chuẩn Chuẩn Danh Mục V7:
    - Gốc `[A] STORAGE`: `Danh Mục Hệ Thống - Storage` (hoặc `Danh Mục Hệ Thống - Storage, Bản Danh Sách`).
    - Thư mục con: `Danh Mục Hệ Thống - <Tên Chuẩn Hóa>[, <Ngữ Cảnh Cha>]`.
    """
    clean = nfc(folder_path or "").strip().rstrip("/")
    if not clean or clean == ROOT_NAME:
        return f"{SHEET_PREFIX}Storage, Bản Danh Sách" if is_list_copy else f"{SHEET_PREFIX}Storage"
    last = clean.split("/")[-1]
    seg = normalize_catalog_segment(last)
    if context_segments:
        ctx = ", ".join(s for s in context_segments if s)
        if ctx:
            return f"{SHEET_PREFIX}{seg}, {ctx}"
    return f"{SHEET_PREFIX}{seg}"


def normalize_sheet_title(folder_path: str, style: str = "v7") -> str:
    """
    Hàm tương thích cho toàn bộ hệ thống.
    - `style="v7"` (mặc định v4.0): dùng Chuẩn Danh Mục V7 (1 dấu `" - "` duy nhất, en-dash nội bộ).
    - `style="v6"`: giữ quy tắc cũ v3.x khi cần đối chiếu lịch sử.
    """
    clean = nfc(folder_path or "").strip().rstrip("/")
    if style == "v6":
        if not clean or clean == ROOT_NAME:
            return f"{SHEET_PREFIX}Storage"
        last = clean.split("/")[-1]
        body = re.sub(r"^\[\d{2,3}\]\s*", "", last)
        body = re.sub(r"^\[([^\]]+)\]\s*(.+)$", lambda m: f"{m.group(1).strip()} - {m.group(2).strip()}", body)
        body = re.sub(r"^\[([^\]]+)\]$", r"\1", body)
        body = re.sub(r"\.(pdf|docx?|xlsx?|pptx?)$", "", body, flags=re.I)
        body = re.sub(r"\s*_+\s*", " ", body).strip()
        return f"{SHEET_PREFIX}{title_case_vn(body)}"
    return normalize_catalog_title(clean)


def should_have_catalog(
    folder_path: str,
    index: Dict[str, Dict[str, Any]],
    policy: Optional[Dict[str, Any]] = None,
) -> CatalogDecision:
    """Đánh giá một thư mục có nên lập bảng `Danh Mục Hệ Thống` riêng theo Chính sách Tinh gọn Thông minh V7 không."""
    pol = _effective_policy(policy)
    clean = nfc(folder_path or "").strip().rstrip("/")
    if not clean or clean == ROOT_NAME:
        return CatalogDecision(
            folder_path=ROOT_NAME,
            depth=0,
            include=True,
            reason="root",
            base_title=normalize_catalog_title(ROOT_NAME),
            final_title=normalize_catalog_title(ROOT_NAME),
            catalog_folder_path=catalog_folder_for_path(ROOT_NAME),
        )

    parts = clean.split("/")
    depth = len(parts) - 1 if parts[0] == ROOT_NAME else len(parts)
    if is_in_danh_sach_tree(clean) or is_excluded_catalog_folder(clean, pol):
        return CatalogDecision(
            folder_path=clean,
            depth=depth,
            include=False,
            reason="excluded_or_system",
            catalog_folder_path=catalog_folder_for_path(clean),
        )

    items = (index.get(clean) or {}).get("items", [])
    non_tq = [it for it in items if not (it.get("mimeType") == FOLDER_MIME and it.get("name") == TONG_QUAN_FOLDER)]
    subs = [it for it in non_tq if it.get("mimeType") == FOLDER_MIME]
    n_items = len(non_tq)
    n_subs = len(subs)

    mode = str(pol.get("mode", "smart")).lower()
    always_d = int(pol.get("always_include_max_depth", 4))
    std_d = int(pol.get("standard_max_depth", 5))
    prom_d = int(pol.get("promote_depth_limit", 6))
    min_leaf = int(pol.get("min_items_for_leaf", 1))
    min_prom = int(pol.get("min_items_for_promote", 15))

    if mode == "full":
        inc, reason = True, "full_mode"
    elif depth <= always_d:
        inc, reason = True, f"core_depth<={always_d}"
    elif depth <= std_d:
        if n_items >= min_leaf or n_subs >= 1:
            inc, reason = True, f"depth_{depth}_active"
        else:
            inc, reason = False, f"depth_{depth}_empty_leaf"
    elif depth <= prom_d and n_items >= min_prom:
        inc, reason = True, f"depth_{depth}_promoted(items={n_items}>={min_prom})"
    else:
        inc, reason = False, f"pruned_depth_{depth}(items={n_items})"

    base_title = normalize_catalog_title(clean)
    return CatalogDecision(
        folder_path=clean,
        depth=depth,
        include=inc,
        reason=reason,
        direct_items=n_items,
        direct_subfolders=n_subs,
        base_title=base_title,
        final_title=base_title,
        catalog_folder_path=catalog_folder_for_path(clean),
    )


def _norm_key(text: str) -> str:
    return strip_accents(nfc(text or "").strip()).lower()


def compute_catalog_titles(
    folder_paths: Iterable[str],
    policy: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """
    Tính tên bảng `Danh Mục Hệ Thống - ...` ĐỘC NHẤT TOÀN KHO (Zero-Collision) cho tập thư mục.
    - Tên thuộc nhóm chung (`generic_names`) hoặc bị trùng lặp (`count >= 2`) sẽ tự động gắn
      `, <Ngữ Cảnh Cha>` (tăng dần cấp cha cho đến khi độc nhất 100%).
    """
    pol = _effective_policy(policy)
    generic_keys = {_norm_key(g) for g in pol.get("generic_names") or []}
    max_levels = max(1, int(pol.get("max_disambiguate_levels", 2)))

    clean_paths = sorted(dict.fromkeys(nfc(p).strip().rstrip("/") for p in folder_paths if p))
    base_seg: Dict[str, str] = {}
    ancestors: Dict[str, List[str]] = {}

    for p in clean_paths:
        if p == ROOT_NAME:
            base_seg[p] = "Storage"
            ancestors[p] = []
            continue
        parts = p.split("/")
        rel_parts = parts[1:] if parts[0] == ROOT_NAME else parts
        base_seg[p] = normalize_catalog_segment(rel_parts[-1])
        # Danh sách ngữ cảnh cha từ gần nhất → xa nhất
        anc_segs = [normalize_catalog_segment(seg) for seg in reversed(rel_parts[:-1])]
        ancestors[p] = [s for s in anc_segs if s]

    # Bước 1: Gán mức disambiguation ban đầu (0 hoặc 1 nếu là tên chung)
    levels: Dict[str, int] = {}
    for p in clean_paths:
        if p == ROOT_NAME:
            levels[p] = 0
        elif _norm_key(base_seg[p]) in generic_keys and ancestors[p]:
            levels[p] = 1
        else:
            levels[p] = 0

    def _render(p: str, lv: int) -> str:
        if p == ROOT_NAME:
            return f"{SHEET_PREFIX}Storage"
        if lv <= 0 or not ancestors[p]:
            return f"{SHEET_PREFIX}{base_seg[p]}"
        ctx: List[str] = []
        seen_k = {_norm_key(base_seg[p])}
        for cand in ancestors[p]:
            ck = _norm_key(cand)
            if ck in seen_k:
                continue
            seen_k.add(ck)
            ctx.append(cand)
            if len(ctx) >= lv:
                break
        return normalize_catalog_title(p, ctx)

    # Bước 2: Lặp tăng cấp ngữ cảnh cho mọi nhóm trùng tên cho đến khi 0 va chạm
    for _ in range(12):
        titles = {p: _render(p, levels[p]) for p in clean_paths}
        counts = collections.Counter(_norm_key(t) for t in titles.values())
        colliding = [p for p, t in titles.items() if counts[_norm_key(t)] > 1]
        if not colliding:
            return titles
        progressed = False
        for p in colliding:
            cap = max(max_levels, len(ancestors[p]))
            if levels[p] < cap:
                levels[p] += 1
                progressed = True
        if not progressed:
            # Phòng hờ cực hiếm (cùng tên ở các nhánh sâu có cha giống hệt nhau): thêm STT phân biệt
            by_key: Dict[str, List[str]] = collections.defaultdict(list)
            for p in colliding:
                by_key[_norm_key(titles[p])].append(p)
            for group in by_key.values():
                if len(group) <= 1:
                    continue
                for idx_i, p in enumerate(sorted(group), start=1):
                    titles[p] = f"{titles[p]} ({idx_i})"
            return titles

    return {p: _render(p, levels[p]) for p in clean_paths}


def evaluate_catalog_scope(
    index: Dict[str, Dict[str, Any]],
    branch: Optional[str] = None,
    policy: Optional[Dict[str, Any]] = None,
) -> Dict[str, CatalogDecision]:
    """Đánh giá toàn bộ cây thư mục nội dung theo Chính sách Tinh gọn Thông minh V7 và tính tên chuẩn độc nhất."""
    pol = _effective_policy(policy)
    prefix = branch.rstrip("/") + "/" if branch else ""
    decisions: Dict[str, CatalogDecision] = {}

    for fpath in sorted(index.keys()):
        if branch and not (fpath == branch or fpath.startswith(prefix)):
            continue
        if fpath != ROOT_NAME and (is_in_danh_sach_tree(fpath) or fpath == f"{ROOT_NAME}/{TONG_QUAN_FOLDER}" or fpath.startswith(f"{ROOT_NAME}/{TONG_QUAN_FOLDER}/")):
            continue
        dec = should_have_catalog(fpath, index, pol)
        decisions[fpath] = dec

    included_paths = [p for p, d in decisions.items() if d.include]
    titles = compute_catalog_titles(included_paths, pol)
    for p, t in titles.items():
        decisions[p].final_title = t
    return decisions


def _source_path_from_danh_sach_folder(ds_folder: str) -> str:
    if ds_folder == DANH_SACH_PATH:
        return ROOT_NAME
    prefix = DANH_SACH_PATH + "/"
    if ds_folder.startswith(prefix):
        return f"{ROOT_NAME}/{ds_folder[len(prefix):]}"
    return ""


def audit_catalog_tree(
    index: Dict[str, Dict[str, Any]],
    branch: Optional[str] = None,
    policy: Optional[Dict[str, Any]] = None,
) -> List[AuditFinding]:
    """
    Kiểm toán chuyên sâu toàn bộ cây `[01] DANH SÁCH` theo Chuẩn Danh Mục V7:
    - `DANH_MUC_RAC_KY_THUAT` (LỖI): bảng/thư mục gương cho `MACOSX` hoặc vùng loại trừ.
    - `DANH_MUC_MO_COI` (CẢNH BÁO): bảng tồn tại nhưng thư mục nội dung nguồn không còn.
    - `DANH_MUC_TRUNG_TEN` (CẢNH BÁO): nhiều bảng dùng chung một tên trên toàn cây.
    - `DANH_MUC_SAI_TEN` (CẢNH BÁO): tên bảng chưa đúng chuẩn V7 (có kèm đề xuất chuẩn).
    - `DANH_MUC_CO_THE_TINH_GON` (GỢI Ý): bảng nằm ngoài ngưỡng Tinh gọn Thông minh V7.
    """
    pol = _effective_policy(policy)
    decisions = evaluate_catalog_scope(index, branch=branch, policy=pol)
    findings: List[AuditFinding] = []
    sheet_name_groups: Dict[str, List[Tuple[str, dict]]] = collections.defaultdict(list)
    b_prefix = branch.rstrip("/") + "/" if branch else ""

    for fpath, meta in index.items():
        if not is_in_danh_sach_tree(fpath):
            continue
        src_path = _source_path_from_danh_sach_folder(fpath)
        if branch and src_path and not (src_path == branch or src_path.startswith(b_prefix)):
            continue
        for it in meta.get("items", []):
            if it.get("mimeType") != SHEET_MIME or not str(it.get("name", "")).startswith(SHEET_PREFIX):
                continue
            sheet_name_groups[_norm_key(it["name"])].append((fpath, it))

            # Bảng tổng tại gốc `[01] DANH SÁCH`
            if fpath == DANH_SACH_PATH:
                expected_root_copy = normalize_catalog_title(ROOT_NAME, is_list_copy=True)
                if nfc(it["name"]) != expected_root_copy:
                    findings.append(
                        AuditFinding(
                            severity="CẢNH BÁO",
                            code="DANH_MUC_SAI_TEN",
                            parent_path=fpath,
                            name=it["name"],
                            item_id=it["id"],
                            item_type="Google Sheets",
                            description=f"Tên bảng danh mục chưa đạt Chuẩn V7 (`{expected_root_copy}`)",
                            suggestion=expected_root_copy,
                        )
                    )
                continue

            if is_excluded_catalog_folder(src_path, pol):
                findings.append(
                    AuditFinding(
                        severity="LỖI",
                        code="DANH_MUC_RAC_KY_THUAT",
                        parent_path=fpath,
                        name=it["name"],
                        item_id=it["id"],
                        item_type="Google Sheets",
                        description=f"Bảng danh mục sinh nhầm cho thư mục rác/kỹ thuật `{src_path}` — cần chuyển về khu cách ly",
                        suggestion="",
                    )
                )
                continue

            if src_path not in index:
                findings.append(
                    AuditFinding(
                        severity="CẢNH BÁO",
                        code="DANH_MUC_MO_COI",
                        parent_path=fpath,
                        name=it["name"],
                        item_id=it["id"],
                        item_type="Google Sheets",
                        description=f"Thư mục nguồn `{src_path}` không còn tồn tại trong chỉ mục",
                        suggestion="",
                    )
                )
                continue

            dec = decisions.get(src_path)
            if dec and not dec.include:
                findings.append(
                    AuditFinding(
                        severity="GỢI Ý",
                        code="DANH_MUC_CO_THE_TINH_GON",
                        parent_path=fpath,
                        name=it["name"],
                        item_id=it["id"],
                        item_type="Google Sheets",
                        description=f"Nằm ngoài ngưỡng tinh gọn thông minh V7 ({dec.reason}) — có thể gom về bảng cấp cha",
                        suggestion="",
                    )
                )
                continue

            if dec and dec.final_title and nfc(it["name"]) != nfc(dec.final_title):
                findings.append(
                    AuditFinding(
                        severity="CẢNH BÁO",
                        code="DANH_MUC_SAI_TEN",
                        parent_path=fpath,
                        name=it["name"],
                        item_id=it["id"],
                        item_type="Google Sheets",
                        description=f"Tên bảng chưa đúng Chuẩn Danh Mục V7 (đề xuất: `{dec.final_title}`)",
                        suggestion=dec.final_title,
                    )
                )

    for grp in sheet_name_groups.values():
        if len(grp) <= 1:
            continue
        for fpath, it in grp:
            src_path = _source_path_from_danh_sach_folder(fpath)
            dec = decisions.get(src_path)
            sug = dec.final_title if (dec and dec.include and dec.final_title != it["name"]) else ""
            findings.append(
                AuditFinding(
                    severity="CẢNH BÁO",
                    code="DANH_MUC_TRUNG_TEN",
                    parent_path=fpath,
                    name=it["name"],
                    item_id=it["id"],
                    item_type="Google Sheets",
                    description=f"Trùng tên với {len(grp) - 1} bảng Danh Mục khác trong `[01] DANH SÁCH`",
                    suggestion=sug,
                )
            )
    return findings


def build_catalog_migration_plan(
    index: Dict[str, Dict[str, Any]],
    branch: Optional[str] = None,
    policy: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Lập kế hoạch chuyển đổi cây `[01] DANH SÁCH` sang Chuẩn Danh Mục V7 (mặc định chỉ đọc):
    - `renames`: giữ nguyên Drive File ID, đổi tên tại chỗ sang tên V7 độc nhất.
    - `prunes`: di chuyển bảng rác (`MACOSX`) hoặc bảng ngoài ngưỡng tinh gọn về `[07] KIỂM TRA` (không xóa cứng).
    - `missing`: thư mục đạt chuẩn tinh gọn nhưng chưa có bảng Danh Mục.
    """
    pol = _effective_policy(policy)
    decisions = evaluate_catalog_scope(index, branch=branch, policy=pol)
    b_prefix = branch.rstrip("/") + "/" if branch else ""

    renames: List[Dict[str, Any]] = []
    prunes: List[Dict[str, Any]] = []
    kept_unchanged = 0
    covered_sources: Set[str] = set()

    for fpath, meta in sorted(index.items()):
        if not is_in_danh_sach_tree(fpath):
            continue
        src_path = _source_path_from_danh_sach_folder(fpath)
        if branch and src_path and not (src_path == branch or src_path.startswith(b_prefix)):
            continue
        parent_id = meta.get("id", "")
        for it in meta.get("items", []):
            if it.get("mimeType") != SHEET_MIME or not str(it.get("name", "")).startswith(SHEET_PREFIX):
                continue

            if fpath == DANH_SACH_PATH:
                expected = normalize_catalog_title(ROOT_NAME, is_list_copy=True)
                if nfc(it["name"]) != expected:
                    renames.append({
                        "id": it["id"],
                        "parent_id": parent_id,
                        "catalog_folder": fpath,
                        "source_path": ROOT_NAME,
                        "old_name": it["name"],
                        "new_name": expected,
                        "reason": "root_list_copy_v7",
                    })
                else:
                    kept_unchanged += 1
                covered_sources.add(ROOT_NAME)
                continue

            if is_excluded_catalog_folder(src_path, pol):
                prunes.append({
                    "id": it["id"],
                    "parent_id": parent_id,
                    "catalog_folder": fpath,
                    "source_path": src_path,
                    "name": it["name"],
                    "category": "system_junk",
                    "reason": "excluded_tech_or_macosx",
                })
                continue

            if src_path not in index:
                prunes.append({
                    "id": it["id"],
                    "parent_id": parent_id,
                    "catalog_folder": fpath,
                    "source_path": src_path,
                    "name": it["name"],
                    "category": "pruned_catalog",
                    "reason": "orphan_source_missing",
                })
                continue

            dec = decisions.get(src_path)
            if dec and not dec.include:
                prunes.append({
                    "id": it["id"],
                    "parent_id": parent_id,
                    "catalog_folder": fpath,
                    "source_path": src_path,
                    "name": it["name"],
                    "category": "pruned_catalog",
                    "reason": dec.reason,
                })
                continue

            covered_sources.add(src_path)
            if dec and nfc(it["name"]) != nfc(dec.final_title):
                renames.append({
                    "id": it["id"],
                    "parent_id": parent_id,
                    "catalog_folder": fpath,
                    "source_path": src_path,
                    "old_name": it["name"],
                    "new_name": dec.final_title,
                    "reason": "normalize_v7_zero_collision",
                })
            else:
                kept_unchanged += 1

    # Kiểm tra bảng gốc tại `[00] TỔNG QUAN`
    root_tq = f"{ROOT_NAME}/{TONG_QUAN_FOLDER}"
    if root_tq in index and any(
        it.get("mimeType") == SHEET_MIME and str(it.get("name", "")).startswith(SHEET_PREFIX)
        for it in index[root_tq].get("items", [])
    ):
        covered_sources.add(ROOT_NAME)

    missing = [
        {
            "source_path": p,
            "expected_title": d.final_title,
            "catalog_folder": d.catalog_folder_path,
            "depth": d.depth,
            "reason": d.reason,
        }
        for p, d in sorted(decisions.items())
        if d.include and p not in covered_sources
    ]

    total_eligible = sum(1 for d in decisions.values() if d.include)
    total_existing = kept_unchanged + len(renames) + len(prunes)
    return {
        "policy": pol,
        "summary": {
            "existing_sheets": total_existing,
            "target_eligible_catalogs": total_eligible,
            "kept_unchanged": kept_unchanged,
            "renames_count": len(renames),
            "prunes_count": len(prunes),
            "prunes_junk_count": sum(1 for x in prunes if x["category"] == "system_junk"),
            "prunes_smart_count": sum(1 for x in prunes if x["category"] == "pruned_catalog"),
            "missing_count": len(missing),
        },
        "renames": renames,
        "prunes": prunes,
        "missing": missing,
    }


def apply_catalog_migration_plan(
    drive: Any,
    plan: Dict[str, Any],
    *,
    execute: bool = False,
    apply_prunes: bool = True,
    db: Optional[Any] = None,
    quarantine_root_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Thực thi kế hoạch chuẩn hóa & tinh gọn Danh Mục V7 (mặc định dry-run).
    - Đổi tên tại chỗ (bảo toàn 100% Drive File ID).
    - Di chuyển bảng rác / bảng đã tinh gọn vào `[07] KIỂM TRA` (không bao giờ xóa vĩnh viễn).
    - Lưu toàn bộ thao tác vào `StorageDB` Unified Undo Journal để hoàn tác 1 lệnh.
    """
    from storage_suite.core.config import CONFIG
    from storage_suite.core.config import quarantine_root_id as default_qroot

    renames = plan.get("renames", [])
    prunes = plan.get("prunes", []) if apply_prunes else []
    if not execute:
        return {
            "execute": False,
            "renamed": len(renames),
            "pruned": len(prunes),
            "errors": [],
            "batch_id": "",
        }

    actions: List[UndoAction] = []
    errors: List[str] = []

    if renames:
        pairs = [(r["id"], r["new_name"]) for r in renames]
        res = drive.batch_rename(pairs)
        by_id = {r["id"]: r for r in renames}
        for fid, ok, err in res:
            rec = by_id[fid]
            if ok:
                actions.append(
                    UndoAction(
                        op="catalog_rename",
                        item_id=fid,
                        old_name=rec["old_name"],
                        new_name=rec["new_name"],
                        old_parent_id=rec.get("parent_id", ""),
                        path=rec.get("catalog_folder", ""),
                    )
                )
            else:
                errors.append(f"rename {fid}: {err}")

    if prunes:
        qroot = quarantine_root_id or default_qroot()
        qsubs = CONFIG.get("quarantine_subfolders") or {}
        dest_cache: Dict[str, str] = {}
        move_items: List[Tuple[str, str]] = []
        prune_by_id: Dict[str, Tuple[Dict[str, Any], str]] = {}
        for pr in prunes:
            cat = pr.get("category", "pruned_catalog")
            sub_name = qsubs.get(cat, "[07] DANH MỤC ĐÃ TINH GỌN" if cat == "pruned_catalog" else "[06] RÁC HỆ THỐNG")
            if sub_name not in dest_cache:
                dest_cache[sub_name] = drive.ensure_folder(sub_name, qroot)
            dest_id = dest_cache[sub_name]
            move_items.append((pr["id"], dest_id))
            prune_by_id[pr["id"]] = (pr, dest_id)

        mres = drive.batch_move(move_items)
        for fid, ok, err in mres:
            pr, dest_id = prune_by_id[fid]
            if ok:
                actions.append(
                    UndoAction(
                        op="catalog_prune",
                        item_id=fid,
                        old_name=pr["name"],
                        new_name=pr["name"],
                        old_parent_id=pr.get("parent_id", ""),
                        new_parent_id=dest_id,
                        path=pr.get("catalog_folder", ""),
                        extra={"reason": pr.get("reason", "")},
                    )
                )
            else:
                errors.append(f"move {fid}: {err}")

    batch_id = ""
    if db is not None and actions:
        batch_id = db.record_undo_batch(
            kind="catalog_v7",
            actions=actions,
            description=f"Chuẩn hóa & tinh gọn Danh Mục V7 ({len(renames)} đổi tên, {len(prunes)} tinh gọn)",
        )

    return {
        "execute": True,
        "renamed": sum(1 for a in actions if a.op == "catalog_rename"),
        "pruned": sum(1 for a in actions if a.op == "catalog_prune"),
        "errors": errors,
        "batch_id": batch_id,
    }
