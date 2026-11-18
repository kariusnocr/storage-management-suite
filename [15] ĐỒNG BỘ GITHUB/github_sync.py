#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ĐỒNG BỘ KHO MÃ NGUỒN VỚI GITHUB & LIÊN THÔNG GOOGLE DRIVE — [A] STORAGE (v3.2)
==============================================================================
Chương trình `[15] ĐỒNG BỘ GITHUB/github_sync.py` kết nối hệ thống quản lý kho
`[A] STORAGE` (`/home/antigravity/storage_quan_ly` ↔ Drive `[00] TỔNG QUAN/[03] QUẢN LÝ`)
với kho lưu trữ GitHub `kariusnocr/storage-management-suite`:

1. `trang-thai`       : Kiểm tra trạng thái Git cục bộ, nhánh, tệp thay đổi, độ lệch so với
                        `sync_manifest.json` của Google Drive và kết quả GitHub Actions CI gần nhất.
2. `kiem-tra-bao-mat` : Quét toàn bộ mã nguồn trước khi đẩy để ngăn rò rỉ khóa riêng tư,
                        token xác thực (GitHub/Google OAuth) hoặc tệp dữ liệu quá lớn (>10 MB).
3. `day-len`          : Kiểm tra bảo mật → chạy bộ kiểm thử tự động `unittest` → tạo commit
                        và đẩy lên GitHub (mặc định chạy thử; ghi thật khi có `--thuc-thi`).
                        Tự động chuyển sang nhánh PR nếu nhánh `main` bật khóa bảo vệ.
4. `keo-ve`           : Kéo các bản cập nhật mới từ GitHub về máy cục bộ (`git fetch` + `pull --ff-only`).
5. `dong-bo-2-chieu`  : Phối hợp liên hoàn `[08] deploy_sync.py` và `github_sync.py` để đồng bộ
                        đồng thời cả Google Drive `[03] QUẢN LÝ` (giữ 100% ID) lẫn GitHub.
6. `phat-hanh`        : Tạo thẻ phiên bản và phát hành GitHub Release (`gh release create`).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


def _nap_thu_vien_loi():
    here = Path(__file__).resolve().parent
    cands = [Path(os.environ["STORAGE_CORE_DIR"])] if os.environ.get("STORAGE_CORE_DIR") else []
    for base in [here, *list(here.parents)[:3]]:
        cands.append(base)
        if base.is_dir():
            cands += [d for d in base.iterdir() if d.is_dir() and "THƯ VIỆN LÕI" in d.name]
    for c in cands:
        if (c / "storage_core.py").exists():
            sys.path.insert(0, str(c))
            import storage_core  # noqa: E402
            return storage_core
    raise SystemExit("Không tìm thấy storage_core.py — hãy đặt `[01] THƯ VIỆN LÕI` cạnh chương trình.")


sc = _nap_thu_vien_loi()

SKIP_AUDIT_DIRS = {".git", "__pycache__", ".pytest_cache"}

# Ghép động các tiền tố nhạy cảm để tệp mã nguồn không tự khớp chính nó khi quét
_SECRET_RULES: List[Tuple[str, re.Pattern[str], str]] = [
    (
        "PRIVATE_KEY",
        re.compile(r"-----BEGIN " + r"(?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
        "Phát hiện khóa riêng tư (Private Key)",
    ),
    (
        "GITHUB_TOKEN",
        re.compile(r"\b(?:gh" + r"p_[A-Za-z0-9]{30,}|gh" + r"o_[A-Za-z0-9]{30,}|github_" + r"pat_[A-Za-z0-9_]{30,})\b"),
        "Phát hiện GitHub Personal Access / OAuth Token",
    ),
    (
        "GOOGLE_OAUTH_TOKEN",
        re.compile(r"\b(?:ya" + r"29\.[A-Za-z0-9_-]{30,}|AI" + r"za[0-9A-Za-z_-]{35})\b"),
        "Phát hiện Google OAuth Token / API Key",
    ),
]


def default_repo_root() -> Path:
    here = Path(__file__).resolve().parent
    return here.parent if here.name.startswith("[") else here


def _run_cmd(
    cmd: Sequence[str],
    cwd: Path,
    timeout: int = 120,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        list(cmd),
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if check and proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"Lệnh thất bại ({' '.join(cmd)}): {err[:600]}")
    return proc


# ---------------------------------------------------------------------------
# 1. KIỂM TRA BẢO MẬT & ĐỐI CHIẾU MANIFEST GOOGLE DRIVE
# ---------------------------------------------------------------------------

def audit_repo_security(
    repo_root: Optional[Path] = None,
    max_file_mb: float = 10.0,
) -> List[Dict[str, str]]:
    """
    Quét toàn bộ cây thư mục mã nguồn (trừ `.git`, `__pycache__`) để ngăn chặn:
    - Rò rỉ khóa riêng tư hoặc token OAuth/GitHub/Google
    - Đưa nhầm tệp dữ liệu lớn (> `max_file_mb` MB) hoặc chỉ mục kho vào Git
    """
    root = Path(repo_root) if repo_root else default_repo_root()
    max_bytes = int(max_file_mb * 1024 * 1024)
    findings: List[Dict[str, str]] = []

    for p in sorted(root.rglob("*")):
        if any(part in SKIP_AUDIT_DIRS for part in p.parts):
            continue
        if not p.is_file() or p.suffix in {".pyc", ".pyo"}:
            continue
        rel = str(p.relative_to(root))
        sz = p.stat().st_size
        if max_bytes > 0 and sz > max_bytes:
            findings.append({
                "path": rel,
                "code": "TEP_QUA_LON",
                "description": f"Dung lượng {sc.human_size(sz)} vượt ngưỡng {max_file_mb} MB cho Git",
            })
            continue
        if p.name in {
            "storage_index.json",
            "storage_index.json.gz",
            "storage_index_meta.json",
            "shortcut_cache.json",
            "quarantine_log.json",
        }:
            findings.append({
                "path": rel,
                "code": "DU_LIEU_KHO_TRONG_GIT",
                "description": f"Tệp dữ liệu vận hành `{p.name}` phải nằm trong STORAGE_DATA_DIR, không đưa vào Git",
            })
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for code, rx, desc in _SECRET_RULES:
            if rx.search(content):
                findings.append({
                    "path": rel,
                    "code": code,
                    "description": desc,
                })
    return findings


def compare_with_drive_manifest(repo_root: Optional[Path] = None) -> Dict[str, List[str]]:
    """So sánh SHA-256 các tệp mô-đun cục bộ với `sync_manifest.json` của Google Drive `[03] QUẢN LÝ`."""
    root = Path(repo_root) if repo_root else default_repo_root()
    manifest_p = sc.data_dir() / "sync_manifest.json"
    manifest = sc.read_json(manifest_p, default={}) or {}

    skip_names = {"__pycache__", ".DS_Store", ".pytest_cache", ".git", ".github", ".gitignore", "README.md", "pyproject.toml"}
    local_hashes: Dict[str, str] = {}
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel_parts = p.relative_to(root).parts
        if any(part in skip_names or part.startswith(".") for part in rel_parts) or p.suffix in {".pyc", ".pyo"}:
            continue
        rel = "/".join(rel_parts)
        local_hashes[rel] = sc.sha256_file(p)

    untracked_on_drive: List[str] = []
    modified_since_drive_sync: List[str] = []
    in_sync: List[str] = []

    for rel, sha in local_hashes.items():
        rec = manifest.get(rel)
        if not rec:
            untracked_on_drive.append(rel)
        elif rec.get("sha256") != sha:
            modified_since_drive_sync.append(rel)
        else:
            in_sync.append(rel)

    return {
        "in_sync": in_sync,
        "modified_since_drive_sync": modified_since_drive_sync,
        "untracked_on_drive": untracked_on_drive,
    }


# ---------------------------------------------------------------------------
# 2. KHỞI TẠO GIT, KIỂM TRA TRẠNG THÁI & ĐỒNG BỘ GITHUB
# ---------------------------------------------------------------------------

def ensure_gh_git_auth(cwd: Path) -> bool:
    """Chạy `gh auth status` để kích hoạt credential helper cho `git` trên máy ảo."""
    if not shutil.which("gh"):
        return False
    proc = _run_cmd(["gh", "auth", "status"], cwd=cwd)
    return proc.returncode == 0


def ensure_git_initialized(
    repo_root: Optional[Path] = None,
    remote_repo: Optional[str] = None,
    default_branch: str = "main",
) -> Dict[str, Any]:
    """Khởi tạo kho Git cục bộ và gắn remote `origin` nếu chưa có."""
    root = Path(repo_root) if repo_root else default_repo_root()
    target_repo = remote_repo or sc.github_repo()
    remote_url = f"https://github.com/{target_repo}.git"
    ensure_gh_git_auth(root)

    git_dir = root / ".git"
    created = False
    if not git_dir.exists():
        _run_cmd(["git", "init", "-b", default_branch], cwd=root, check=True)
        created = True

    rem_proc = _run_cmd(["git", "remote", "get-url", "origin"], cwd=root)
    if rem_proc.returncode != 0:
        _run_cmd(["git", "remote", "add", "origin", remote_url], cwd=root, check=True)
    elif rem_proc.stdout.strip() != remote_url:
        _run_cmd(["git", "remote", "set-url", "origin", remote_url], cwd=root, check=True)

    return {
        "repo_root": str(root),
        "remote_repo": target_repo,
        "remote_url": remote_url,
        "initialized_new": created,
    }


def inspect_git_status(
    repo_root: Optional[Path] = None,
    check_remote: bool = True,
) -> Dict[str, Any]:
    """Thu thập trạng thái Git cục bộ, độ lệch Drive manifest và kết quả GitHub Actions CI."""
    root = Path(repo_root) if repo_root else default_repo_root()
    is_git = (root / ".git").exists()
    branch = ""
    head_sha = ""
    remote_url = ""
    changed_files: List[Dict[str, str]] = []
    ahead = 0
    behind = 0

    if is_git:
        b_proc = _run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root)
        if b_proc.returncode == 0:
            branch = b_proc.stdout.strip()
        h_proc = _run_cmd(["git", "rev-parse", "--short", "HEAD"], cwd=root)
        if h_proc.returncode == 0:
            head_sha = h_proc.stdout.strip()
        r_proc = _run_cmd(["git", "remote", "get-url", "origin"], cwd=root)
        if r_proc.returncode == 0:
            remote_url = r_proc.stdout.strip()

        st_proc = _run_cmd(["git", "status", "--porcelain"], cwd=root)
        if st_proc.returncode == 0:
            for ln in st_proc.stdout.splitlines():
                if len(ln) >= 4:
                    changed_files.append({"status": ln[:2].strip(), "path": ln[3:].strip()})

        ab_proc = _run_cmd(["git", "rev-list", "--left-right", "--count", "HEAD...@{u}"], cwd=root)
        if ab_proc.returncode == 0 and "\t" in ab_proc.stdout.strip():
            parts = ab_proc.stdout.strip().split("\t")
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                ahead, behind = int(parts[0]), int(parts[1])

    ci_runs: List[Dict[str, Any]] = []
    if check_remote and shutil.which("gh"):
        target_repo = sc.github_repo()
        ci_proc = _run_cmd(
            [
                "gh", "run", "list", "-R", target_repo, "--limit", "3",
                "--json", "databaseId,workflowName,headBranch,status,conclusion,createdAt",
            ],
            cwd=root,
        )
        if ci_proc.returncode == 0 and ci_proc.stdout.strip():
            try:
                ci_runs = json.loads(ci_proc.stdout)
            except json.JSONDecodeError:
                pass

    drive_diff = compare_with_drive_manifest(root)
    sec_issues = audit_repo_security(root)
    return {
        "is_git_repo": is_git,
        "branch": branch,
        "head_sha": head_sha,
        "remote_repo": sc.github_repo(),
        "remote_url": remote_url,
        "changed_files": changed_files,
        "ahead": ahead,
        "behind": behind,
        "drive_sync": drive_diff,
        "security_issues": sec_issues,
        "ci_runs": ci_runs,
    }


def run_offline_test_suite(repo_root: Optional[Path] = None) -> Tuple[bool, str]:
    """Chạy bộ kiểm thử tự động `test_storage_suite.py` trước khi cho phép đẩy lên GitHub."""
    root = Path(repo_root) if repo_root else default_repo_root()
    test_dir = root / "[01] THƯ VIỆN LÕI" / "tests"
    if not test_dir.exists():
        return True, "Không tìm thấy thư mục tests"
    proc = _run_cmd([sys.executable, "-m", "unittest", "discover", "-s", str(test_dir), "-v"], cwd=root, timeout=120)
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    return proc.returncode == 0, out.strip()


def push_to_github(
    repo_root: Optional[Path] = None,
    message: Optional[str] = None,
    branch: str = "main",
    execute: bool = False,
    run_tests: bool = True,
    create_pr: bool = False,
) -> Dict[str, Any]:
    """
    Kiểm tra bảo mật, chạy kiểm thử, tạo commit và đẩy lên GitHub.
    Mặc định chạy thử (`execute=False`).
    """
    root = Path(repo_root) if repo_root else default_repo_root()
    sec_issues = audit_repo_security(root)
    if sec_issues:
        return {
            "ok": False,
            "dry_run": not execute,
            "stage": "security_audit",
            "security_issues": sec_issues,
            "error": f"Phát hiện {len(sec_issues)} vi phạm bảo mật/dung lượng — hủy đẩy lên GitHub.",
        }

    tests_ok = True
    test_output = ""
    if run_tests:
        tests_ok, test_output = run_offline_test_suite(root)
        if not tests_ok:
            return {
                "ok": False,
                "dry_run": not execute,
                "stage": "unit_tests",
                "security_issues": [],
                "tests_passed": False,
                "error": "Bộ kiểm thử tự động thất bại — hủy đẩy lên GitHub.",
                "test_output": test_output[-1500:],
            }

    commit_msg = message or f"chore(storage): đồng bộ bộ chương trình quản lý [A] STORAGE v{sc.__version__} ({sc.today_vn()})"
    st = inspect_git_status(root, check_remote=False)

    if not execute:
        return {
            "ok": True,
            "dry_run": True,
            "remote_repo": sc.github_repo(),
            "branch": branch,
            "commit_message": commit_msg,
            "changed_files": st["changed_files"],
            "security_issues": [],
            "tests_passed": tests_ok,
        }

    ensure_git_initialized(root, default_branch=branch)
    _run_cmd(["git", "add", "-A"], cwd=root, check=True)

    status_after_add = _run_cmd(["git", "status", "--porcelain"], cwd=root)
    committed = False
    if status_after_add.stdout.strip():
        c_proc = _run_cmd(["git", "commit", "-m", commit_msg], cwd=root, check=True)
        committed = c_proc.returncode == 0

    head_sha = _run_cmd(["git", "rev-parse", "--short", "HEAD"], cwd=root).stdout.strip()
    target_repo = sc.github_repo()
    pr_url = ""
    pushed_branch = branch

    if not create_pr:
        push_proc = _run_cmd(["git", "push", "-u", "origin", f"HEAD:{branch}"], cwd=root)
        if push_proc.returncode != 0:
            # Nếu nhánh từ xa có commit khởi tạo (ví dụ README khởi tạo), thử fetch + rebase/merge rồi đẩy lại
            _run_cmd(["git", "fetch", "origin", branch], cwd=root)
            rebase_proc = _run_cmd(["git", "rebase", f"origin/{branch}"], cwd=root)
            if rebase_proc.returncode != 0:
                _run_cmd(["git", "rebase", "--abort"], cwd=root)
                _run_cmd(["git", "merge", f"origin/{branch}", "--allow-unrelated-histories", "--no-edit"], cwd=root)
            push_proc = _run_cmd(["git", "push", "-u", "origin", f"HEAD:{branch}"], cwd=root)

        if push_proc.returncode != 0:
            # Chuyển sang cơ chế tạo nhánh tính năng + mở Pull Request nếu nhánh chính bị chặn đẩy trực tiếp
            create_pr = True

    if create_pr:
        pushed_branch = f"sync/{sc.now_stamp()}"
        _run_cmd(["git", "push", "-u", "origin", f"HEAD:refs/heads/{pushed_branch}"], cwd=root, check=True)
        pr_proc = _run_cmd(
            [
                "gh", "pr", "create", "-R", target_repo,
                "--base", branch,
                "--head", pushed_branch,
                "--title", commit_msg,
                "--body", f"Đồng bộ tự động từ bộ quản lý kho `[A] STORAGE` (`{head_sha}`).",
            ],
            cwd=root,
        )
        if pr_proc.returncode == 0:
            pr_url = pr_proc.stdout.strip().splitlines()[-1]
            _run_cmd(["gh", "pr", "merge", pr_url, "-R", target_repo, "--squash", "--delete-branch"], cwd=root)

    rec = {
        "timestamp": sc.now_utc_iso(),
        "action": "push",
        "repo": target_repo,
        "branch": pushed_branch,
        "head_sha": head_sha,
        "committed": committed,
        "commit_message": commit_msg,
        "pr_url": pr_url,
    }
    log_data = sc.read_json(sc.github_sync_log_path(), default={"history": []})
    if not isinstance(log_data, dict) or "history" not in log_data:
        log_data = {"history": []}
    log_data["history"].append(rec)
    sc.write_json(sc.github_sync_log_path(), log_data)

    return {
        "ok": True,
        "dry_run": False,
        "remote_repo": target_repo,
        "branch": pushed_branch,
        "head_sha": head_sha,
        "committed": committed,
        "commit_message": commit_msg,
        "pr_url": pr_url,
    }


def pull_from_github(
    repo_root: Optional[Path] = None,
    branch: str = "main",
    execute: bool = False,
) -> Dict[str, Any]:
    """Kéo thay đổi mới nhất từ nhánh `branch` trên GitHub về thư mục mã nguồn cục bộ."""
    root = Path(repo_root) if repo_root else default_repo_root()
    ensure_git_initialized(root, default_branch=branch)
    _run_cmd(["git", "fetch", "origin", branch], cwd=root, check=True)
    if not execute:
        diff_proc = _run_cmd(["git", "log", f"HEAD..origin/{branch}", "--oneline"], cwd=root)
        incoming = [ln.strip() for ln in diff_proc.stdout.splitlines() if ln.strip()]
        return {"ok": True, "dry_run": True, "branch": branch, "incoming_commits": incoming}

    _run_cmd(["git", "pull", "--ff-only", "origin", branch], cwd=root, check=True)
    head_sha = _run_cmd(["git", "rev-parse", "--short", "HEAD"], cwd=root).stdout.strip()
    return {"ok": True, "dry_run": False, "branch": branch, "head_sha": head_sha}


def sync_bidirectional(
    repo_root: Optional[Path] = None,
    message: Optional[str] = None,
    branch: str = "main",
    execute: bool = False,
    assume_yes: bool = False,
    force_drive_conflict: bool = False,
) -> Dict[str, Any]:
    """
    Đồng bộ liên hoàn:
    1. Đẩy mã nguồn cục bộ lên Google Drive `[00] TỔNG QUAN/[03] QUẢN LÝ` qua `[08] deploy_sync.py` (giữ 100% ID).
    2. Kiểm tra bảo mật, chạy kiểm thử và đẩy mã nguồn lên GitHub `kariusnocr/storage-management-suite`.
    """
    root = Path(repo_root) if repo_root else default_repo_root()
    deploy_script = root / "[08] TRIỂN KHAI MÃ NGUỒN" / "deploy_sync.py"
    deploy_cmd = [sys.executable, str(deploy_script), "day-len"]
    if force_drive_conflict:
        deploy_cmd.append("--ghi-de-xung-dot")
    if execute:
        deploy_cmd.append("--thuc-thi")
        if assume_yes:
            deploy_cmd.append("--dong-y")

    d_proc = _run_cmd(deploy_cmd, cwd=root, timeout=300)
    drive_ok = d_proc.returncode == 0

    gh_res = push_to_github(
        repo_root=root,
        message=message,
        branch=branch,
        execute=execute,
        run_tests=True,
    )
    return {
        "ok": drive_ok and gh_res.get("ok", False),
        "dry_run": not execute,
        "drive_returncode": d_proc.returncode,
        "drive_output": (d_proc.stdout or "").strip()[-1200:],
        "github": gh_res,
    }


def create_github_release(
    tag: str,
    title: Optional[str] = None,
    notes: Optional[str] = None,
    repo_root: Optional[Path] = None,
    execute: bool = False,
) -> Dict[str, Any]:
    """Tạo bản phát hành GitHub Release (`gh release create`). Mặc định chạy thử."""
    root = Path(repo_root) if repo_root else default_repo_root()
    target_repo = sc.github_repo()
    rel_title = title or f"Bộ Quản Lý [A] STORAGE {tag} ({sc.today_vn()})"
    rel_notes = notes or (
        f"Phát hành bộ chương trình quản trị kho dữ liệu `[A] STORAGE` phiên bản `{tag}` "
        f"(gồm 15 chương trình `[01]`–`[15]` theo Chuẩn V6)."
    )
    if not execute:
        return {
            "ok": True,
            "dry_run": True,
            "repo": target_repo,
            "tag": tag,
            "title": rel_title,
            "notes": rel_notes,
        }
    ensure_gh_git_auth(root)
    proc = _run_cmd(
        ["gh", "release", "create", tag, "-R", target_repo, "--title", rel_title, "--notes", rel_notes],
        cwd=root,
        check=True,
    )
    return {
        "ok": True,
        "dry_run": False,
        "repo": target_repo,
        "tag": tag,
        "url": proc.stdout.strip(),
    }


# ---------------------------------------------------------------------------
# 3. GIAO DIỆN DÒNG LỆNH (CLI)
# ---------------------------------------------------------------------------

def _print_status(st: Dict[str, Any]) -> None:
    sc.log("=" * 74)
    sc.log(f"🐙 KHO GITHUB KẾT NỐI : {st['remote_repo']}")
    sc.log(f"🔗 URL REMOTE         : {st['remote_url'] or '(chưa cấu hình)'}")
    sc.log(f"🌿 NHÁNH HIỆN TẠI     : {st['branch'] or '(chưa khởi tạo)'} | HEAD: {st['head_sha'] or '-'}")
    sc.log(f"🔄 ĐỘ LỆCH UPSTREAM   : ahead={st['ahead']}, behind={st['behind']}")
    sc.log(f"📝 TỆP THAY ĐỔI GIT   : {len(st['changed_files'])} tệp")
    for ch in st["changed_files"][:25]:
        sc.log(f"   • [{ch['status']}] {ch['path']}")
    ds = st["drive_sync"]
    sc.log(
        f"☁️  ĐỒNG BỘ DRIVE [03] : khớp={len(ds['in_sync'])}, "
        f"sửa cục bộ={len(ds['modified_since_drive_sync'])}, "
        f"mới chưa đẩy Drive={len(ds['untracked_on_drive'])}"
    )
    for rel in ds["modified_since_drive_sync"][:10]:
        sc.log(f"   • [sửa] {rel}")
    for rel in ds["untracked_on_drive"][:10]:
        sc.log(f"   • [mới] {rel}")
    if st["security_issues"]:
        sc.log(f"🚨 CẢNH BÁO BẢO MẬT   : {len(st['security_issues'])} mục")
        for s in st["security_issues"]:
            sc.log(f"   • [{s['code']}] {s['path']}: {s['description']}")
    else:
        sc.log("🛡️  KIỂM TRA BẢO MẬT  : An toàn (0 rò rỉ khóa/token, 0 tệp quá cỡ)")
    if st["ci_runs"]:
        sc.log("⚙️  GITHUB ACTIONS CI GẦN NHẤT:")
        for r in st["ci_runs"]:
            sc.log(
                f"   • #{r.get('databaseId')} [{r.get('workflowName')}] "
                f"nhánh={r.get('headBranch')} | trạng thái={r.get('status')} | kết quả={r.get('conclusion')}"
            )
    sc.log("=" * 74)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Đồng bộ bộ chương trình quản lý [A] STORAGE với GitHub & Google Drive (v3.2)."
    )
    ap.add_argument(
        "lenh",
        nargs="?",
        default="trang-thai",
        choices=["trang-thai", "kiem-tra-bao-mat", "day-len", "keo-ve", "dong-bo-2-chieu", "phat-hanh"],
        help="Lệnh: trang-thai, kiem-tra-bao-mat, day-len, keo-ve, dong-bo-2-chieu, phat-hanh.",
    )
    ap.add_argument("--nhanh-git", default="main", help="Nhánh Git mục tiêu (mặc định: main).")
    ap.add_argument("--thong-diep", help="Thông điệp commit hoặc tiêu đề bản phát hành.")
    ap.add_argument("--the", default=f"v{sc.__version__}", help="Thẻ phiên bản cho lệnh `phat-hanh` (mặc định: v3.2.0).")
    ap.add_argument("--tao-pr", action="store_true", help="Đẩy sang nhánh riêng và mở Pull Request thay vì đẩy thẳng.")
    ap.add_argument("--bo-qua-kiem-thu", action="store_true", help="Bỏ qua bước chạy unittest trước khi đẩy.")
    ap.add_argument("--ghi-de-xung-dot", action="store_true", help="Cho phép ghi đè xung đột trên Google Drive khi `dong-bo-2-chieu`.")
    ap.add_argument("--thuc-thi", action="store_true", help="Thực sự ghi/đẩy lên GitHub và Drive (mặc định: chạy thử).")
    ap.add_argument("--dong-y", action="store_true", help="Không hỏi xác nhận khi --thuc-thi.")
    args = ap.parse_args()

    root = default_repo_root()

    if args.lenh == "trang-thai":
        st = inspect_git_status(root, check_remote=True)
        _print_status(st)
        return

    if args.lenh == "kiem-tra-bao-mat":
        issues = audit_repo_security(root)
        if not issues:
            sc.log("🛡️  Kiểm tra bảo mật hoàn tất: 0 phát hiện rò rỉ khóa/token hoặc tệp quá cỡ.")
            return
        sc.log(f"🚨 Phát hiện {len(issues)} vấn đề bảo mật/dung lượng:")
        for it in issues:
            sc.log(f" • [{it['code']}] {it['path']}: {it['description']}")
        sys.exit(2)

    if args.lenh == "day-len":
        res = push_to_github(
            repo_root=root,
            message=args.thong_diep,
            branch=args.nhanh_git,
            execute=args.thuc_thi,
            run_tests=not args.bo_qua_kiem_thu,
            create_pr=args.tao_pr,
        )
        if not res.get("ok"):
            sc.log(f"❌ {res.get('error')}")
            if res.get("test_output"):
                sc.log(res["test_output"])
            sys.exit(1)
        if res.get("dry_run"):
            sc.log(
                f"🔍 [CHẠY THỬ] Sẵn sàng đẩy lên `{res['remote_repo']}` (nhánh `{res['branch']}`): "
                f"{len(res['changed_files'])} tệp thay đổi | kiểm thử={res['tests_passed']}"
            )
            sc.log(f"   • Thông điệp commit dự kiến: {res['commit_message']}")
            sc.log("💡 Thêm `--thuc-thi` để thực sự tạo commit và đẩy lên GitHub.")
        else:
            sc.log(
                f"✅ Đã đồng bộ lên GitHub `{res['remote_repo']}` "
                f"(nhánh `{res['branch']}`, HEAD `{res['head_sha']}`)."
            )
            if res.get("pr_url"):
                sc.log(f"   • Pull Request: {res['pr_url']}")
        return

    if args.lenh == "keo-ve":
        res = pull_from_github(repo_root=root, branch=args.nhanh_git, execute=args.thuc_thi)
        if res.get("dry_run"):
            inc = res.get("incoming_commits", [])
            sc.log(f"🔍 [CHẠY THỬ] Có {len(inc)} commit mới trên `origin/{args.nhanh_git}`.")
            for c in inc[:15]:
                sc.log(f"   • {c}")
        else:
            sc.log(f"✅ Đã kéo bản cập nhật mới nhất về máy cục bộ (HEAD `{res.get('head_sha')}`).")
        return

    if args.lenh == "dong-bo-2-chieu":
        res = sync_bidirectional(
            repo_root=root,
            message=args.thong_diep,
            branch=args.nhanh_git,
            execute=args.thuc_thi,
            assume_yes=args.dong_y,
            force_drive_conflict=args.ghi_de_xung_dot,
        )
        sc.log(res.get("drive_output", ""))
        gh_part = res.get("github", {})
        if not res.get("ok"):
            sc.log(f"❌ Đồng bộ 2 chiều chưa hoàn tất: drive_rc={res.get('drive_returncode')}, github_ok={gh_part.get('ok')}")
            sys.exit(1)
        if res.get("dry_run"):
            sc.log("🔍 [CHẠY THỬ] Đã kiểm tra đồng bộ cả Google Drive `[03] QUẢN LÝ` lẫn GitHub. Thêm `--thuc-thi --dong-y` để áp dụng.")
        else:
            sc.log(f"✅ Đã đồng bộ hoàn tất cả Google Drive `[03] QUẢN LÝ` lẫn GitHub `{gh_part.get('remote_repo')}` (`{gh_part.get('head_sha')}`).")
        return

    if args.lenh == "phat-hanh":
        res = create_github_release(
            tag=args.the,
            title=args.thong_diep,
            repo_root=root,
            execute=args.thuc_thi,
        )
        if res.get("dry_run"):
            sc.log(f"🔍 [CHẠY THỬ] Dự kiến tạo bản phát hành `{res['tag']}` trên `{res['repo']}`: {res['title']}")
        else:
            sc.log(f"✅ Đã phát hành `{res['tag']}`: {res.get('url')}")


if __name__ == "__main__":
    main()
