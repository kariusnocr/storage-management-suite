"""Trình điều khiển Google Drive API v3 trực tiếp (OAuth 2.0) chạy độc lập trên Windows/macOS/Linux.

Cài đặt thư viện phụ thuộc (optional extra `[drive-api]`):
    pip install "storage-management-suite[drive-api]"
Đăng nhập một lần:
    kas auth login --credentials path/to/client_secrets.json
"""

from __future__ import annotations

import concurrent.futures as cf
import io
import mimetypes
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from karius_academic_system.core.config import (
    FOLDER_MIME,
    SHORTCUT_MIME,
    oauth_credentials_path,
    oauth_token_path,
)
from karius_academic_system.core.drive_base import RETRYABLE_ERRORS, DriveError, TokenBucket
from karius_academic_system.core.utils import nfc

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]

_EXPORT_MIMES: Dict[str, str] = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "csv": "text/csv",
    "tsv": "text/tab-separated-values",
    "txt": "text/plain",
    "md": "text/markdown",
    "html": "text/html",
}

_SEARCH_TYPE_MIMES: Dict[str, str] = {
    "folder": FOLDER_MIME,
    "document": "application/vnd.google-apps.document",
    "docs": "application/vnd.google-apps.document",
    "spreadsheet": "application/vnd.google-apps.spreadsheet",
    "sheets": "application/vnd.google-apps.spreadsheet",
    "presentation": "application/vnd.google-apps.presentation",
    "slides": "application/vnd.google-apps.presentation",
    "pdf": "application/pdf",
}

_LS_FIELDS = "nextPageToken, files(id, name, mimeType, size, modifiedTime, parents, shortcutDetails)"
_INFO_FIELDS = (
    "id, name, mimeType, size, createdTime, modifiedTime, parents, shared, description, "
    "owners(displayName, emailAddress), permissions(id, role, type), shortcutDetails, capabilities"
)


def is_google_api_installed() -> bool:
    try:
        import google.oauth2.credentials  # noqa: F401
        import googleapiclient.discovery  # noqa: F401
        return True
    except ImportError:
        return False


def _require_google_api() -> Tuple[Any, Any, Any, Any, Any]:
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
    except ImportError as exc:
        raise DriveError(
            "Thiếu thư viện Google Drive API OAuth 2.0. Cài đặt bằng:\n"
            '  pip install "storage-management-suite[drive-api]"'
        ) from exc
    return Credentials, Request, InstalledAppFlow, build, (MediaFileUpload, MediaIoBaseDownload)


def auth_status(token_file: Optional[Path] = None, credentials_file: Optional[Path] = None) -> Dict[str, Any]:
    """Kiểm tra trạng thái đăng nhập OAuth 2.0 cục bộ."""
    tpath = Path(token_file) if token_file else oauth_token_path()
    cpath = Path(credentials_file) if credentials_file else oauth_credentials_path()
    info: Dict[str, Any] = {
        "backend": "api",
        "libs_installed": is_google_api_installed(),
        "credentials_path": str(cpath),
        "credentials_exists": cpath.exists(),
        "token_path": str(tpath),
        "token_exists": tpath.exists(),
        "authenticated": False,
        "expired": False,
        "has_refresh_token": False,
    }
    if not info["libs_installed"] or not tpath.exists():
        return info
    try:
        Credentials, _, _, _, _ = _require_google_api()
        creds = Credentials.from_authorized_user_file(str(tpath), DRIVE_SCOPES)
        info["expired"] = bool(creds.expired)
        info["has_refresh_token"] = bool(creds.refresh_token)
        info["authenticated"] = bool(creds.valid or (creds.expired and creds.refresh_token))
    except Exception as exc:
        info["error"] = str(exc)
    return info


def auth_login(
    credentials_file: Optional[Path] = None,
    token_file: Optional[Path] = None,
    port: int = 0,
    open_browser: bool = True,
) -> Path:
    """Chạy luồng đăng nhập OAuth 2.0 trên trình duyệt cục bộ và lưu `token.json`."""
    Credentials, Request, InstalledAppFlow, _, _ = _require_google_api()
    cpath = Path(credentials_file).expanduser() if credentials_file else oauth_credentials_path()
    tpath = Path(token_file).expanduser() if token_file else oauth_token_path()
    tpath.parent.mkdir(parents=True, exist_ok=True)

    creds = None
    if tpath.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(tpath), DRIVE_SCOPES)
        except Exception:
            creds = None

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif not creds or not creds.valid:
        if not cpath.exists():
            raise DriveError(
                f"Không tìm thấy tệp OAuth Client Secrets tại `{cpath}`.\n"
                "Hãy tải `credentials.json` (Desktop app) từ Google Cloud Console rồi chạy:\n"
                "  kas auth login --credentials /đường/dẫn/credentials.json"
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(cpath), DRIVE_SCOPES)
        creds = flow.run_local_server(port=port, open_browser=open_browser)

    tpath.write_text(creds.to_json(), encoding="utf-8")
    try:
        tpath.chmod(0o600)
    except OSError:
        pass
    return tpath


def auth_logout(token_file: Optional[Path] = None) -> bool:
    """Xóa tệp `token.json` cục bộ."""
    tpath = Path(token_file).expanduser() if token_file else oauth_token_path()
    if tpath.exists():
        tpath.unlink()
        return True
    return False


class GoogleDriveAPIClient:
    """Client Google Drive API v3 chạy độc lập (OAuth 2.0), tương thích 100% `DriveProtocol`."""

    backend_name: str = "api"

    def __init__(
        self,
        token_file: Optional[Path] = None,
        credentials_file: Optional[Path] = None,
        retries: int = 5,
        rate_per_sec: float = 10.0,
        service_factory: Optional[Callable[[], Any]] = None,
    ) -> None:
        self.token_file = Path(token_file).expanduser() if token_file else oauth_token_path()
        self.credentials_file = Path(credentials_file).expanduser() if credentials_file else oauth_credentials_path()
        self.retries = max(1, int(retries))
        self.bucket = TokenBucket(rate_per_sec=rate_per_sec, burst=max(10.0, rate_per_sec * 2))
        self._service_factory = service_factory
        self._local = threading.local()
        self._creds: Any = None
        self._cred_lock = threading.Lock()

    def _load_credentials(self) -> Any:
        with self._cred_lock:
            if self._creds is not None and getattr(self._creds, "valid", False):
                return self._creds
            Credentials, Request, _, _, _ = _require_google_api()
            if not self.token_file.exists():
                raise DriveError(
                    f"Chưa đăng nhập Google Drive API (`{self.token_file}` không tồn tại). "
                    "Hãy chạy `kas auth login` trước."
                )
            creds = Credentials.from_authorized_user_file(str(self.token_file), DRIVE_SCOPES)
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                self.token_file.write_text(creds.to_json(), encoding="utf-8")
            if not creds.valid:
                raise DriveError("Token OAuth 2.0 đã hết hạn và không thể làm mới. Hãy chạy lại `kas auth login`.")
            self._creds = creds
            return creds

    def _service(self) -> Any:
        svc = getattr(self._local, "service", None)
        if svc is not None:
            return svc
        if self._service_factory is not None:
            svc = self._service_factory()
        else:
            _, _, _, build, _ = _require_google_api()
            creds = self._load_credentials()
            svc = build("drive", "v3", credentials=creds, cache_discovery=False)
        self._local.service = svc
        return svc

    def _exec(self, fn: Callable[[], Any], op_name: str = "api") -> Any:
        last_err = ""
        for attempt in range(self.retries):
            self.bucket.acquire()
            try:
                return fn()
            except Exception as exc:
                last_err = str(exc)
                if any(k.lower() in last_err.lower() for k in RETRYABLE_ERRORS):
                    time.sleep(min(30, 1.5 * (2 ** attempt)))
                    continue
                raise DriveError(f"Lỗi Google Drive API ({op_name}): {last_err[:800]}") from exc
        raise DriveError(f"Lỗi Google Drive API ({op_name}) sau {self.retries} lần thử: {last_err[:800]}")

    @staticmethod
    def _escape_q(val: str) -> str:
        return val.replace("\\", "\\\\").replace("'", "\\'")

    def ls(self, folder_id: str) -> List[dict]:
        q = f"'{self._escape_q(folder_id)}' in parents and trashed = false"
        out: List[dict] = []
        page_token: Optional[str] = None
        while True:
            def _call(pt=page_token):
                return (
                    self._service()
                    .files()
                    .list(
                        q=q,
                        pageSize=1000,
                        pageToken=pt,
                        fields=_LS_FIELDS,
                        supportsAllDrives=True,
                        includeItemsFromAllDrives=True,
                    )
                    .execute()
                )

            res = self._exec(_call, "ls") or {}
            out.extend(res.get("files") or [])
            page_token = res.get("nextPageToken")
            if not page_token:
                break
        return out

    def stream_ls(
        self,
        folder_ids: Sequence[str],
        concurrency: int = 16,
        timeout: int = 600,
    ) -> Tuple[Dict[str, List[dict]], Dict[str, str]]:
        unique_ids = list(dict.fromkeys(fid for fid in folder_ids if fid))
        if not unique_ids:
            return {}, {}
        out_map: Dict[str, List[dict]] = {}
        err_map: Dict[str, str] = {}

        def _one(fid: str):
            try:
                return fid, self.ls(fid), ""
            except DriveError as exc:
                return fid, None, str(exc)

        workers = max(1, min(int(concurrency), 16, len(unique_ids)))
        with cf.ThreadPoolExecutor(max_workers=workers) as pool:
            for fid, items, err in pool.map(_one, unique_ids):
                if items is not None:
                    out_map[fid] = items
                else:
                    err_map[fid] = err
        return out_map, err_map

    def stream_info(
        self,
        file_ids: Sequence[str],
        concurrency: int = 16,
        timeout: int = 600,
    ) -> Dict[str, dict]:
        unique_ids = list(dict.fromkeys(fid for fid in file_ids if fid))
        if not unique_ids:
            return {}
        out_map: Dict[str, dict] = {}

        def _one(fid: str):
            try:
                return fid, self.info(fid)
            except DriveError:
                return fid, None

        workers = max(1, min(int(concurrency), 16, len(unique_ids)))
        with cf.ThreadPoolExecutor(max_workers=workers) as pool:
            for fid, data in pool.map(_one, unique_ids):
                if isinstance(data, dict):
                    out_map[fid] = data
        return out_map

    def stream_capabilities(
        self,
        file_ids: Sequence[str],
        fields: str = "canMoveItemOutOfDrive,canEdit,canTrash",
        concurrency: int = 16,
        timeout: int = 600,
    ) -> Dict[str, dict]:
        unique_ids = list(dict.fromkeys(fid for fid in file_ids if fid))
        if not unique_ids:
            return {}
        out_map: Dict[str, dict] = {}

        def _one(fid: str):
            try:
                return fid, self.capabilities(fid, fields)
            except DriveError:
                return fid, None

        workers = max(1, min(int(concurrency), 16, len(unique_ids)))
        with cf.ThreadPoolExecutor(max_workers=workers) as pool:
            for fid, data in pool.map(_one, unique_ids):
                if isinstance(data, dict):
                    out_map[fid] = data
        return out_map

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
    ) -> List[dict]:
        clauses: List[str] = []
        if not include_trashed:
            clauses.append("trashed = false")
        if modified_after:
            clauses.append(f"modifiedTime > '{self._escape_q(modified_after)}'")
        if modified_before:
            clauses.append(f"modifiedTime < '{self._escape_q(modified_before)}'")
        if parent_id:
            clauses.append(f"'{self._escape_q(parent_id)}' in parents")
        if name_exact:
            clauses.append(f"name = '{self._escape_q(name_exact)}'")
        if name_contains:
            clauses.append(f"name contains '{self._escape_q(name_contains)}'")
        if file_type:
            mime = _SEARCH_TYPE_MIMES.get(file_type.lower(), file_type)
            clauses.append(f"mimeType = '{self._escape_q(mime)}'")
        q = " and ".join(clauses) if clauses else "trashed = false"

        target_max = 1000 if max_results <= 0 else int(max_results)
        collected: List[dict] = []
        page_token: Optional[str] = None
        while len(collected) < target_max:
            page_size = min(1000, target_max - len(collected))

            def _call(pt=page_token, ps=page_size):
                return (
                    self._service()
                    .files()
                    .list(
                        q=q,
                        orderBy="modifiedTime desc",
                        pageSize=ps,
                        pageToken=pt,
                        fields=_LS_FIELDS,
                        supportsAllDrives=True,
                        includeItemsFromAllDrives=True,
                    )
                    .execute()
                )

            res = self._exec(_call, "search") or {}
            collected.extend(res.get("files") or [])
            page_token = res.get("nextPageToken")
            if not page_token:
                break
        return collected[:target_max]

    def info(self, file_id: str) -> dict:
        def _call():
            return self._service().files().get(fileId=file_id, fields=_INFO_FIELDS, supportsAllDrives=True).execute()

        return self._exec(_call, "info") or {}

    def capabilities(self, file_id: str, fields: str = "canMoveItemOutOfDrive,canEdit,canTrash") -> dict:
        def _call():
            return (
                self._service()
                .files()
                .get(fileId=file_id, fields="capabilities", supportsAllDrives=True)
                .execute()
            )

        res = self._exec(_call, "capabilities") or {}
        caps = res.get("capabilities") or {}
        if fields:
            wanted = {f.strip() for f in fields.split(",") if f.strip()}
            return {k: v for k, v in caps.items() if k in wanted}
        return dict(caps)

    def download(self, file_id: str, out: Path) -> Path:
        out_p = Path(out)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        if self._service_factory is None:
            _, _, _, _, (_, MediaIoBaseDownload) = _require_google_api()
        else:
            MediaIoBaseDownload = None

        def _call():
            req = self._service().files().get_media(fileId=file_id, supportsAllDrives=True)
            if MediaIoBaseDownload is None:
                data = req.execute()
                out_p.write_bytes(data if isinstance(data, (bytes, bytearray)) else bytes(data))
                return
            with open(out_p, "wb") as fh:
                downloader = MediaIoBaseDownload(fh, req)
                done = False
                while not done:
                    _, done = downloader.next_chunk()

        self._exec(_call, "download")
        return out_p

    def export(self, file_id: str, out: Path, fmt: str) -> Path:
        out_p = Path(out)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        mime = _EXPORT_MIMES.get(fmt.lower(), fmt)

        def _call():
            data = self._service().files().export(fileId=file_id, mimeType=mime).execute()
            if isinstance(data, str):
                out_p.write_text(data, encoding="utf-8")
            elif isinstance(data, (bytes, bytearray)):
                out_p.write_bytes(bytes(data))
            elif isinstance(data, io.BytesIO):
                out_p.write_bytes(data.getvalue())
            else:
                out_p.write_bytes(bytes(data))

        self._exec(_call, "export")
        return out_p

    def find_child(self, parent_id: str, name: str, folder_only: bool = False) -> Optional[dict]:
        target = nfc(name)
        for it in self.ls(parent_id):
            if nfc(it.get("name", "")) == target and (not folder_only or it.get("mimeType") == FOLDER_MIME):
                return it
        return None

    def mkdir(self, name: str, parent_id: str) -> str:
        body = {"name": name, "mimeType": FOLDER_MIME, "parents": [parent_id]}

        def _call():
            return self._service().files().create(body=body, fields="id", supportsAllDrives=True).execute()

        res = self._exec(_call, "mkdir") or {}
        fid = res.get("id", "")
        if not fid:
            raise DriveError(f"Không xác định được ID thư mục vừa tạo: {name}")
        return fid

    def ensure_folder(self, name: str, parent_id: str) -> str:
        found = self.find_child(parent_id, name, folder_only=True)
        return found["id"] if found else self.mkdir(name, parent_id)

    def upload(self, local: Path, parent_id: str, mime_type: Optional[str] = None) -> str:
        local_p = Path(local)
        guessed, _ = mimetypes.guess_type(str(local_p))
        use_mime = mime_type or guessed or "application/octet-stream"
        body: Dict[str, Any] = {"name": local_p.name, "parents": [parent_id]}
        if mime_type:
            body["mimeType"] = mime_type

        if self._service_factory is None:
            _, _, _, _, (MediaFileUpload, _) = _require_google_api()
            media = MediaFileUpload(str(local_p), mimetype=use_mime, resumable=True)
        else:
            media = str(local_p)

        def _call():
            return (
                self._service()
                .files()
                .create(body=body, media_body=media, fields="id", supportsAllDrives=True)
                .execute()
            )

        res = self._exec(_call, "upload") or {}
        return str(res.get("id", ""))

    def update(self, file_id: str, local: Path, mime_type: Optional[str] = None) -> None:
        local_p = Path(local)
        guessed, _ = mimetypes.guess_type(str(local_p))
        use_mime = mime_type or guessed or "application/octet-stream"
        body: Dict[str, Any] = {}
        if mime_type:
            body["mimeType"] = mime_type

        if self._service_factory is None:
            _, _, _, _, (MediaFileUpload, _) = _require_google_api()
            media = MediaFileUpload(str(local_p), mimetype=use_mime, resumable=True)
        else:
            media = str(local_p)

        def _call():
            return (
                self._service()
                .files()
                .update(fileId=file_id, body=body, media_body=media, fields="id", supportsAllDrives=True)
                .execute()
            )

        self._exec(_call, "update")

    def rename(self, file_id: str, new_name: str) -> None:
        def _call():
            return (
                self._service()
                .files()
                .update(fileId=file_id, body={"name": new_name}, fields="id, name", supportsAllDrives=True)
                .execute()
            )

        self._exec(_call, "rename")

    def move(self, file_id: str, new_parent_id: str) -> None:
        meta = self.info(file_id)
        prev_parents = ",".join(meta.get("parents") or [])

        def _call():
            return (
                self._service()
                .files()
                .update(
                    fileId=file_id,
                    addParents=new_parent_id,
                    removeParents=prev_parents,
                    fields="id, parents",
                    supportsAllDrives=True,
                )
                .execute()
            )

        self._exec(_call, "move")

    def copy(self, file_id: str, new_name: str, parent_id: Optional[str] = None) -> str:
        body: Dict[str, Any] = {"name": new_name}
        if parent_id:
            body["parents"] = [parent_id]

        def _call():
            return self._service().files().copy(fileId=file_id, body=body, fields="id", supportsAllDrives=True).execute()

        res = self._exec(_call, "copy") or {}
        return str(res.get("id", ""))

    def create_shortcut(self, target_id: str, parent_id: str, shortcut_name: Optional[str] = None) -> str:
        name = shortcut_name
        if not name:
            meta = self.info(target_id)
            name = meta.get("name") or target_id
        body = {
            "name": name,
            "mimeType": SHORTCUT_MIME,
            "parents": [parent_id],
            "shortcutDetails": {"targetId": target_id},
        }

        def _call():
            return self._service().files().create(body=body, fields="id", supportsAllDrives=True).execute()

        res = self._exec(_call, "create_shortcut") or {}
        return str(res.get("id", ""))

    def batch_rename(self, items: List[Tuple[str, str]], workers: int = 8) -> List[Tuple[str, bool, str]]:
        if not items:
            return []

        def _one(pair: Tuple[str, str]) -> Tuple[str, bool, str]:
            fid, nm = pair
            try:
                self.rename(fid, nm)
                return fid, True, ""
            except DriveError as exc:
                return fid, False, str(exc)

        with cf.ThreadPoolExecutor(max_workers=max(1, min(workers, len(items)))) as pool:
            return list(pool.map(_one, items))

    def batch_move(self, items: List[Tuple[str, str]], workers: int = 8) -> List[Tuple[str, bool, str]]:
        if not items:
            return []

        def _one(pair: Tuple[str, str]) -> Tuple[str, bool, str]:
            fid, dest = pair
            try:
                self.move(fid, dest)
                return fid, True, ""
            except DriveError as exc:
                return fid, False, str(exc)

        with cf.ThreadPoolExecutor(max_workers=max(1, min(workers, len(items)))) as pool:
            return list(pool.map(_one, items))

    def batch_copy(
        self,
        items: List[Tuple[str, str, str]],
        workers: int = 8,
    ) -> List[Tuple[str, str, bool, str]]:
        if not items:
            return []

        def _one(triple: Tuple[str, str, str]) -> Tuple[str, str, bool, str]:
            src_id, new_name, dest_id = triple
            try:
                new_id = self.copy(src_id, new_name, dest_id)
                return src_id, new_id, True, ""
            except DriveError as exc:
                return src_id, "", False, str(exc)

        with cf.ThreadPoolExecutor(max_workers=max(1, min(workers, len(items)))) as pool:
            return list(pool.map(_one, items))
