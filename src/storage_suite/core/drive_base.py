"""Giao thức kết nối Google Drive trừu tượng (`DriveProtocol`) & bộ điều tiết tốc độ."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Protocol, Sequence, Tuple, runtime_checkable


class DriveError(RuntimeError):
    """Ngoại lệ chung cho mọi lỗi thao tác với Google Drive (CLI hoặc API trực tiếp)."""


RETRYABLE_ERRORS = (
    "rateLimitExceeded",
    "userRateLimitExceeded",
    "backendError",
    "internalError",
    "quotaExceeded",
    "429",
    "500",
    "502",
    "503",
    "504",
    "timeout",
    "TLS handshake",
    "connection reset",
    "EOF",
)


class TokenBucket:
    """Bộ điều tiết tốc độ nhẹ (thread-safe) chống vượt ngưỡng Google Drive API."""

    def __init__(self, rate_per_sec: float = 8.0, burst: float = 16.0) -> None:
        self.rate = max(0.5, float(rate_per_sec))
        self.capacity = max(1.0, float(burst))
        self._tokens = self.capacity
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self, tokens: float = 1.0) -> None:
        need = max(0.1, float(tokens))
        while True:
            with self._lock:
                now = time.monotonic()
                elapsed = now - self._last
                self._last = now
                self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
                if self._tokens >= need:
                    self._tokens -= need
                    return
                wait = (need - self._tokens) / self.rate
            time.sleep(min(wait, 1.0))


@runtime_checkable
class DriveProtocol(Protocol):
    """Giao diện chuẩn dùng chung giữa `GDriveCLIClient`, `GoogleDriveAPIClient` và `FakeDrive`."""

    backend_name: str

    def ls(self, folder_id: str) -> List[dict]: ...
    def stream_ls(
        self,
        folder_ids: Sequence[str],
        concurrency: int = 32,
        timeout: int = 600,
    ) -> Tuple[Dict[str, List[dict]], Dict[str, str]]: ...
    def stream_info(
        self,
        file_ids: Sequence[str],
        concurrency: int = 32,
        timeout: int = 600,
    ) -> Dict[str, dict]: ...
    def stream_capabilities(
        self,
        file_ids: Sequence[str],
        fields: str = "canMoveItemOutOfDrive,canEdit,canTrash",
        concurrency: int = 32,
        timeout: int = 600,
    ) -> Dict[str, dict]: ...
    def search(
        self,
        modified_after: Optional[str] = None,
        modified_before: Optional[str] = None,
        parent_id: Optional[str] = None,
        name_exact: Optional[str] = None,
        name_contains: Optional[str] = None,
        file_type: Optional[str] = None,
        include_trashed: bool = False,
        max_results: int = 1000,
    ) -> List[dict]: ...
    def info(self, file_id: str) -> dict: ...
    def capabilities(self, file_id: str, fields: str = "canMoveItemOutOfDrive,canEdit,canTrash") -> dict: ...
    def download(self, file_id: str, out: Path) -> Path: ...
    def export(self, file_id: str, out: Path, fmt: str) -> Path: ...
    def find_child(self, parent_id: str, name: str, folder_only: bool = False) -> Optional[dict]: ...
    def mkdir(self, name: str, parent_id: str) -> str: ...
    def ensure_folder(self, name: str, parent_id: str) -> str: ...
    def upload(self, local: Path, parent_id: str, mime_type: Optional[str] = None) -> str: ...
    def update(self, file_id: str, local: Path, mime_type: Optional[str] = None) -> None: ...
    def rename(self, file_id: str, new_name: str) -> None: ...
    def move(self, file_id: str, new_parent_id: str) -> None: ...
    def copy(self, file_id: str, new_name: str, parent_id: Optional[str] = None) -> str: ...
    def create_shortcut(self, target_id: str, parent_id: str, shortcut_name: Optional[str] = None) -> str: ...
    def batch_rename(self, items: List[Tuple[str, str]]) -> List[Tuple[str, bool, str]]: ...
    def batch_move(self, items: List[Tuple[str, str]], workers: int = 8) -> List[Tuple[str, bool, str]]: ...
    def batch_copy(
        self,
        items: List[Tuple[str, str, str]],
        workers: int = 8,
    ) -> List[Tuple[str, str, bool, str]]: ...
