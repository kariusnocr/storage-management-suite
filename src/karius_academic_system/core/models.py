"""Các mô hình dữ liệu chuẩn hóa có kiểu tĩnh cho Karius Academic System (KAS) v5.0."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass(slots=True)
class StorageItem:
    """Đại diện một tệp tin, thư mục hoặc shortcut trong kho Google Drive."""

    id: str
    name: str
    mime_type: str
    parent_path: str = ""
    size: int = 0
    modified_time: str = ""

    def to_dict(self) -> Dict[str, Any]:
        rec: Dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "mimeType": self.mime_type,
        }
        if self.size:
            rec["size"] = int(self.size)
        if self.modified_time:
            rec["modifiedTime"] = self.modified_time
        return rec

    @classmethod
    def from_dict(cls, data: Dict[str, Any], parent_path: str = "") -> "StorageItem":
        raw_sz = data.get("size")
        try:
            size = int(raw_sz) if raw_sz is not None else 0
        except (TypeError, ValueError):
            size = 0
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            mime_type=str(data.get("mimeType", "")),
            parent_path=parent_path,
            size=size,
            modified_time=str(data.get("modifiedTime", "") or ""),
        )


@dataclass(slots=True)
class AuditFinding:
    """Một phát hiện vi phạm quy ước tên, cấu trúc hoặc danh mục."""

    severity: str  # "LỖI" | "CẢNH BÁO" | "GỢI Ý"
    code: str
    parent_path: str
    name: str
    item_id: str
    item_type: str
    description: str
    suggestion: str = ""

    def as_tuple(self) -> tuple[str, str, str, str, str, str, str, str]:
        return (
            self.severity,
            self.code,
            self.parent_path,
            self.name,
            self.item_id,
            self.item_type,
            self.description,
            self.suggestion,
        )


@dataclass(slots=True)
class CatalogDecision:
    """Quyết định lập bảng Danh Mục Hệ Thống theo chính sách Tinh gọn Thông minh V7."""

    folder_path: str
    depth: int
    include: bool
    reason: str
    direct_items: int = 0
    direct_subfolders: int = 0
    base_title: str = ""
    final_title: str = ""
    catalog_folder_path: str = ""


@dataclass(slots=True)
class UndoAction:
    """Một thao tác nguyên tử có thể hoàn tác trong Unified Undo Journal."""

    op: str  # "rename" | "move" | "create" | "catalog_rename" | "catalog_prune"
    item_id: str
    old_name: str = ""
    new_name: str = ""
    old_parent_id: str = ""
    new_parent_id: str = ""
    path: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PipelineStepResult:
    """Kết quả thực thi một bước trong quy trình điều phối."""

    step: str
    returncode: int
    elapsed_sec: float
    summary: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
