"""Trình điều khiển Google Drive qua binary Go `gdrive` (ưu tiên trên cloud VM)."""

from __future__ import annotations

import concurrent.futures as cf
import glob
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from storage_suite.core.config import FOLDER_MIME, SHORTCUT_MIME
from storage_suite.core.drive_base import RETRYABLE_ERRORS, DriveError
from storage_suite.core.utils import nfc


def find_gdrive_bin() -> str:
    """Ưu tiên gọi trực tiếp binary Go đã cache để bỏ qua shell launcher ở hàng nghìn lệnh con."""
    env = os.environ.get("GDRIVE_BIN")
    if env and os.path.exists(env):
        return env

    candidate_globs: List[str] = []
    app_dir = os.environ.get("ANTIGRAVITY_APP_DATA_DIR")
    if app_dir:
        candidate_globs.append(str(Path(app_dir) / "plugin_data/gdrive/bin/gdrive-*"))
    candidate_globs.extend([
        "/opt/antigravity/plugin_data/gdrive/bin/gdrive-*",
        str(Path.home() / ".gemini/antigravity/plugin_data/gdrive/bin/gdrive-*"),
    ])
    for pattern in candidate_globs:
        matches = sorted((p for p in glob.glob(pattern) if os.access(p, os.X_OK)), reverse=True)
        if matches:
            return matches[0]

    found = shutil.which("gdrive")
    if found:
        return found
    for cand in ("/opt/antigravity/bin/gdrive",):
        if os.path.exists(cand):
            return cand
    raise DriveError("Không tìm thấy CLI `gdrive`. Đặt GDRIVE_BIN, thêm `gdrive` vào PATH, hoặc dùng backend `api` (OAuth 2.0).")


def is_gdrive_cli_available() -> bool:
    try:
        find_gdrive_bin()
        return True
    except DriveError:
        return False


class GDriveCLIClient:
    """Bao bọc CLI `gdrive` với thử lại theo cấp số và hỗ trợ `readonly stream` tốc độ cao."""

    backend_name: str = "cli"
    _RE_OUT_ID = re.compile(r"(?<![A-Za-z0-9_-])([A-Za-z0-9_-]{25,})(?![A-Za-z0-9_-])")

    def __init__(self, retries: int = 5, timeout: int = 180, bin_path: Optional[str] = None):
        self.bin = bin_path or find_gdrive_bin()
        self.retries = retries
        self.timeout = timeout

    def run(
        self,
        args: Sequence[str],
        as_json: bool = False,
        timeout: Optional[int] = None,
        stdin_text: Optional[str] = None,
    ) -> Any:
        cmd = [self.bin] + (["--json"] if as_json else []) + list(args)
        last_err = ""
        for attempt in range(self.retries):
            try:
                proc = subprocess.run(
                    cmd,
                    input=stdin_text,
                    capture_output=True,
                    text=True,
                    timeout=timeout or self.timeout,
                )
            except subprocess.TimeoutExpired:
                last_err = "timeout"
                time.sleep(min(30, 2 ** attempt))
                continue
            if proc.returncode == 0:
                out = proc.stdout
                if not as_json:
                    return out
                out = out.strip()
                if not out:
                    return None
                try:
                    return json.loads(out)
                except json.JSONDecodeError:
                    start = min([i for i in (out.find("["), out.find("{")) if i >= 0], default=-1)
                    if start >= 0:
                        return json.loads(out[start:])
                    raise DriveError(f"Không đọc được JSON từ: {' '.join(cmd)}\n{out[:500]}")
            last_err = (proc.stderr or proc.stdout or "").strip()
            if any(k.lower() in last_err.lower() for k in RETRYABLE_ERRORS):
                time.sleep(min(30, 1.5 * (2 ** attempt)))
                continue
            break
        raise DriveError(f"Lỗi gdrive ({' '.join(args[:2])}): {last_err[:800]}")

    def ls(self, folder_id: str) -> List[dict]:
        res = self.run(["readonly", "ls", folder_id, "--max", "0"], as_json=True)
        if isinstance(res, dict):
            res = res.get("files", [])
        return res or []

    def stream_ls(
        self,
        folder_ids: Sequence[str],
        concurrency: int = 32,
        timeout: int = 600,
    ) -> Tuple[Dict[str, List[dict]], Dict[str, str]]:
        unique_ids = list(dict.fromkeys(fid for fid in folder_ids if fid))
        if not unique_ids:
            return {}, {}
        if len(unique_ids) == 1:
            fid = unique_ids[0]
            try:
                return {fid: self.ls(fid)}, {}
            except DriveError as e:
                return {}, {fid: str(e)}

        out_map: Dict[str, List[dict]] = {}
        err_map: Dict[str, str] = {}
        c = max(1, min(64, int(concurrency)))
        stdin_payload = "\n".join(unique_ids) + "\n"
        try:
            raw = self.run(
                ["readonly", "stream", "ls", "-i", "-", "--max", "0", "-c", str(c)],
                as_json=False,
                timeout=timeout,
                stdin_text=stdin_payload,
            ) or ""
            for line in raw.splitlines():
                line = line.strip()
                if not line or not line.startswith("{"):
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                fid = rec.get("input", "")
                if not fid:
                    continue
                if rec.get("status") == "ok":
                    data = rec.get("data")
                    if isinstance(data, dict):
                        data = data.get("files", [])
                    out_map[fid] = data or []
                else:
                    err_map[fid] = str(rec.get("error") or "stream_ls_error")
        except DriveError:
            pass

        missing = [fid for fid in unique_ids if fid not in out_map]
        if missing:
            def _fallback_one(fid: str):
                try:
                    return fid, self.ls(fid), ""
                except DriveError as e:
                    return fid, None, str(e)

            with cf.ThreadPoolExecutor(max_workers=min(16, len(missing))) as pool:
                for fid, items, err in pool.map(_fallback_one, missing):
                    if items is not None:
                        out_map[fid] = items
                        err_map.pop(fid, None)
                    else:
                        err_map[fid] = err
        return out_map, err_map

    def stream_info(
        self,
        file_ids: Sequence[str],
        concurrency: int = 32,
        timeout: int = 600,
    ) -> Dict[str, dict]:
        unique_ids = list(dict.fromkeys(fid for fid in file_ids if fid))
        if not unique_ids:
            return {}
        if len(unique_ids) == 1:
            fid = unique_ids[0]
            try:
                return {fid: self.info(fid)}
            except DriveError:
                return {}

        out_map: Dict[str, dict] = {}
        c = max(1, min(64, int(concurrency)))
        stdin_payload = "\n".join(unique_ids) + "\n"
        try:
            raw = self.run(
                ["readonly", "stream", "info", "-i", "-", "-c", str(c)],
                as_json=False,
                timeout=timeout,
                stdin_text=stdin_payload,
            ) or ""
            for line in raw.splitlines():
                line = line.strip()
                if not line or not line.startswith("{"):
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                fid = rec.get("input", "")
                if fid and rec.get("status") == "ok" and isinstance(rec.get("data"), dict):
                    out_map[fid] = rec["data"]
        except DriveError:
            for fid in unique_ids:
                try:
                    out_map[fid] = self.info(fid)
                except DriveError:
                    pass
        return out_map

    def stream_capabilities(
        self,
        file_ids: Sequence[str],
        fields: str = "canMoveItemOutOfDrive,canEdit,canTrash",
        concurrency: int = 32,
        timeout: int = 600,
    ) -> Dict[str, dict]:
        unique_ids = list(dict.fromkeys(fid for fid in file_ids if fid))
        if not unique_ids:
            return {}
        if len(unique_ids) == 1:
            fid = unique_ids[0]
            try:
                return {fid: self.capabilities(fid, fields)}
            except DriveError:
                return {}

        out_map: Dict[str, dict] = {}
        c = max(1, min(64, int(concurrency)))
        args = ["readonly", "stream", "capabilities", "-i", "-", "-c", str(c)]
        if fields:
            args += ["--filter", fields]
        stdin_payload = "\n".join(unique_ids) + "\n"
        try:
            raw = self.run(args, as_json=False, timeout=timeout, stdin_text=stdin_payload) or ""
            for line in raw.splitlines():
                line = line.strip()
                if not line or not line.startswith("{"):
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                fid = rec.get("input", "")
                if fid and rec.get("status") == "ok" and isinstance(rec.get("data"), dict):
                    data = rec["data"]
                    caps = data.get("capabilities") if isinstance(data.get("capabilities"), dict) else data
                    out_map[fid] = caps if isinstance(caps, dict) else {}
        except DriveError:
            for fid in unique_ids:
                try:
                    out_map[fid] = self.capabilities(fid, fields)
                except DriveError:
                    pass
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
        target_max = 1000 if max_results <= 0 else int(max_results)
        per_call = min(1000, target_max)
        collected: List[dict] = []
        seen_ids = set()
        cur_before = modified_before
        max_pages = max(1, (target_max + 99) // 100)

        for _ in range(max_pages):
            args = ["readonly", "search", "--max", str(per_call)]
            if modified_after:
                args += ["--modified-after", modified_after]
            if cur_before:
                args += ["--modified-before", cur_before]
            if parent_id:
                args += ["--parent-id", parent_id]
            if name_exact:
                args += ["--name-exact", name_exact]
            if name_contains:
                args += ["--name-contains", name_contains]
            if file_type:
                args += ["--type", file_type]
            if include_trashed:
                args.append("--include-trashed")

            res = self.run(args, as_json=True)
            if isinstance(res, dict):
                res = res.get("files", [])
            page = res or []
            new_in_page = 0
            for it in page:
                fid = it.get("id")
                if fid and fid not in seen_ids:
                    seen_ids.add(fid)
                    collected.append(it)
                    new_in_page += 1
                    if len(collected) >= target_max:
                        return collected

            if len(page) < 100 or new_in_page == 0:
                break
            mods = [it.get("modifiedTime", "").rstrip("Z") for it in page if it.get("modifiedTime")]
            if not mods:
                break
            min_mod = min(mods)
            if cur_before and min_mod >= cur_before:
                break
            cur_before = min_mod

        return collected

    def info(self, file_id: str) -> dict:
        return self.run(["readonly", "info", file_id], as_json=True) or {}

    def capabilities(self, file_id: str, fields: str = "canMoveItemOutOfDrive,canEdit,canTrash") -> dict:
        args = ["readonly", "capabilities", file_id]
        if fields:
            args += ["--filter", fields]
        res = self.run(args, as_json=True) or {}
        if isinstance(res, dict) and "capabilities" in res and isinstance(res["capabilities"], dict):
            return res["capabilities"]
        return res if isinstance(res, dict) else {}

    def download(self, file_id: str, out: Path) -> Path:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        self.run(["readonly", "download", file_id, "--out", str(out)])
        return Path(out)

    def export(self, file_id: str, out: Path, fmt: str) -> Path:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        self.run(["readonly", "export", file_id, str(out), "--format", fmt])
        return Path(out)

    def find_child(self, parent_id: str, name: str, folder_only: bool = False) -> Optional[dict]:
        target = nfc(name)
        for it in self.ls(parent_id):
            if nfc(it.get("name", "")) == target and (not folder_only or it.get("mimeType") == FOLDER_MIME):
                return it
        return None

    def mkdir(self, name: str, parent_id: str) -> str:
        out = self.run(["mutate", "mkdir", name, "--parent", parent_id], as_json=False) or ""
        m = self._RE_OUT_ID.search(out)
        found = self.find_child(parent_id, name, folder_only=True)
        if found:
            return found["id"]
        if m:
            return m.group(1)
        raise DriveError(f"Không xác định được ID thư mục vừa tạo: {name}")

    def ensure_folder(self, name: str, parent_id: str) -> str:
        found = self.find_child(parent_id, name, folder_only=True)
        return found["id"] if found else self.mkdir(name, parent_id)

    def upload(self, local: Path, parent_id: str, mime_type: Optional[str] = None) -> str:
        args = ["mutate", "upload", str(local), "--parent", parent_id]
        if mime_type:
            args += ["--mime-type", mime_type]
        out = self.run(args, as_json=False) or ""
        found = self.find_child(parent_id, Path(local).name)
        if found:
            return found["id"]
        m = self._RE_OUT_ID.search(out)
        return m.group(1) if m else ""

    def update(self, file_id: str, local: Path, mime_type: Optional[str] = None) -> None:
        args = ["mutate", "update", file_id, str(local)]
        if mime_type:
            args += ["--mime-type", mime_type]
        self.run(args)

    def rename(self, file_id: str, new_name: str) -> None:
        self.run(["mutate", "rename", file_id, new_name])

    def move(self, file_id: str, new_parent_id: str) -> None:
        self.run(["mutate", "mv", file_id, new_parent_id])

    def copy(self, file_id: str, new_name: str, parent_id: Optional[str] = None) -> str:
        args = ["mutate", "cp", file_id, new_name]
        if parent_id:
            args += ["--parent", parent_id]
        out = self.run(args, as_json=False) or ""
        m = self._RE_OUT_ID.search(out)
        if parent_id:
            found = self.find_child(parent_id, new_name)
            if found:
                return found["id"]
        return m.group(1) if m else ""

    def create_shortcut(self, target_id: str, parent_id: str, shortcut_name: Optional[str] = None) -> str:
        out = self.run(["mutate", "create-shortcut", target_id, parent_id], as_json=False) or ""
        m = self._RE_OUT_ID.search(out)
        sc_id = m.group(1) if m else ""
        if not sc_id:
            for it in self.ls(parent_id):
                if it.get("mimeType") == SHORTCUT_MIME:
                    sc_id = it["id"]
                    break
        if sc_id and shortcut_name:
            self.rename(sc_id, shortcut_name)
        return sc_id

    def batch_rename(self, items: List[Tuple[str, str]]) -> List[Tuple[str, bool, str]]:
        if not items:
            return []
        ops = [{"op": "rename", "id": fid, "fileId": fid, "name": nm, "target": nm} for fid, nm in items]
        fd, tmp = tempfile.mkstemp(prefix="gdrive_batch_", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(ops, f, ensure_ascii=False)
        done_idx = set()
        try:
            proc = subprocess.run([self.bin, "mutate", "batch", "-f", tmp], capture_output=True, text=True, timeout=300)
            out = (proc.stdout or "") + "\n" + (proc.stderr or "")
            if proc.returncode == 0 and f"Executed {len(items)} operations" in out:
                return [(fid, True, "") for fid, _ in items]
            done_idx = {int(m.group(1)) for m in re.finditer(r"^\[(\d+)\]\s+Renamed\s+", out, flags=re.M)}
        except Exception:
            pass
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
        results = []
        for i, (fid, nm) in enumerate(items):
            if i in done_idx:
                results.append((fid, True, ""))
                continue
            try:
                self.rename(fid, nm)
                results.append((fid, True, ""))
            except DriveError as e:
                results.append((fid, False, str(e)))
        return results

    def batch_move(self, items: List[Tuple[str, str]], workers: int = 8) -> List[Tuple[str, bool, str]]:
        if not items:
            return []

        def one(pair: Tuple[str, str]) -> Tuple[str, bool, str]:
            fid, dest_id = pair
            try:
                self.move(fid, dest_id)
                return fid, True, ""
            except DriveError as e:
                return fid, False, str(e)

        with cf.ThreadPoolExecutor(max_workers=max(1, min(workers, len(items)))) as pool:
            return list(pool.map(one, items))

    def batch_copy(
        self,
        items: List[Tuple[str, str, str]],
        workers: int = 8,
    ) -> List[Tuple[str, str, bool, str]]:
        if not items:
            return []

        def one(triple: Tuple[str, str, str]) -> Tuple[str, str, bool, str]:
            src_id, new_name, dest_id = triple
            try:
                new_id = self.copy(src_id, new_name, dest_id)
                return src_id, new_id, True, ""
            except DriveError as e:
                return src_id, "", False, str(e)

        with cf.ThreadPoolExecutor(max_workers=max(1, min(workers, len(items)))) as pool:
            return list(pool.map(one, items))


# Bí danh tương thích ngược với v3.x
Drive = GDriveCLIClient
