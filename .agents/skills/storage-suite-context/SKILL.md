---
name: storage-suite-context
description: Reference context for Storage Management Suite v4.0.0 (`astorage`), the [A] STORAGE Google Drive archive, Chuẩn V6 / Chuẩn Danh Mục V7, and kariusnocr/storage-management-suite. Use when operating on [A] STORAGE, updating catalogs, running audits/analyzers, or syncing Drive and GitHub.
---

# `[A] STORAGE` & `storage-management-suite` Context (v4.0.0)

## 1. Key Identifiers & Locations

- **GitHub Repository**: `kariusnocr/storage-management-suite` (`src/storage_suite/`, `tests/`, `docs/`, `packaging/`, `Dockerfile`)
- **Unified Software CLI**: `astorage` (alias `storage-suite`), Desktop GUI: `astorage desktop` / `astorage ui`
- **Google Drive Root**: `[A] STORAGE` (`194HC3C2WC1BSzfK3cn_0_uUJ4vfDuBsr`)
- **Governance & Sync Folders**:
  - `[00] TỔNG QUAN`: `1ZLU1RnH4PpJ--CXXPjrum7uxncbOttZU`
  - `[00] TỔNG QUAN/[01] DANH SÁCH`: `1GqdqbI1yVPD3e-HAenW6WioSQZpPaRYz`
  - `[00] TỔNG QUAN/[02] NHẬT KÍ`: `10FI7CMFvGgM9i1rj4IkUFRESv5-ito2Y`
  - `[00] TỔNG QUAN/[03] QUẢN LÝ` (v4.0: docs + `.whl` release bundle): `1dU9BqIFxdLyhsFzxZxOiKWVNHI0vk7W3`
  - `[07] KIỂM TRA` (quarantine & ingest staging): `1dpIWrMRwREX-bSt4k-PxSzVxbLrj3XLy`
    - `[01] SHORTCUT LỖI 404`: `1_o38THe5uq1ZDaiSH9l1QdSJZ0ZMlsAr`
    - `[02] SHORTCUT ĐÃ SAO CHÉP`: `1Mp-kCOZkl2MBSihpHBCdARGhVtA6DuxH`
    - `[03] TỆP TRÙNG LẶP`: `1oT10jMXJuS_Av8y_bAzPC_PVZzuj5LXK`
    - `[04] NHẬP DỮ LIỆU`: `1Xhgp46XpL3ng_l_d-_-wHb4S12DTuPri`
    - `[06] RÁC HỆ THỐNG` & `[07] DANH MỤC ĐÃ TINH GỌN` (auto-created on execute)
- **Master Catalog Spreadsheets**:
  - `Danh Mục Hệ Thống - Storage`: `1BJoV-UtcoSEdjq1w5e0HmfibyTdvLEX8cy22jeKKnDc`
  - `Danh Mục Hệ Thống - Storage, Bản Danh Sách`: `1Pakm-B2FZFFNOsxct_aRmFm2DDQxsQiVsiwB_l2xQt4`

## 2. Chuẩn V6 & Chuẩn Danh Mục V7

- **Folders**: `[STT] TÊN IN HOA CÓ DẤU`
- **Content Files**: `Tên Viết Hoa Đầu Mỗi Chữ Có Dấu - Thông Tin Bổ Sung.[đuôi]` (no `[STT]`, lowercase ext)
- **Catalog Sheets (V7 — Zero-Collision & Smart Pruning)**:
  - Format: `Danh Mục Hệ Thống - <Tên Chuẩn Hóa>[, <Ngữ Cảnh Cha>]`
  - Only ONE `" - "` separator: `[USSH] TRƯỜNG ĐH` → `USSH: Trường ĐH`; internal ` - ` → en-dash `–`.
  - Generic/colliding names automatically receive `, <Parent Context>` until 0 collisions across the tree.
  - **Smart Pruning Policy (`mode="smart"`)**: root + depth `1..4` + non-empty depth `5` + depth `6` with `>= 15` items; excludes `MACOSX`, `__MACOSX`, `.obsidian`, `.git`, `__pycache__`, `tests` (reduces `2.741` → `~493` sheets).

## 3. Dual Drive Backends & SQLite Store

- **Drive Backends (`STORAGE_DRIVE_BACKEND=auto|cli|api`)**:
  - `cli`: `GDriveCLIClient` (cloud VM `gdrive` binary with `stream_ls`).
  - `api`: `GoogleDriveAPIClient` (standalone OAuth 2.0 Google Drive API v3 via `astorage auth login` for Windows/macOS/Linux).
- **SQLite Store**: `~/storage_data/storage.db` (WAL + FTS5 full-text search + Unified Undo Journal).

## 4. Key Commands

```bash
astorage doctor                          # Full environment & toolchain check
astorage kiem-thu                        # Run offline test suite
astorage quet --tang-cuong               # Incremental Drive scan -> SQLite + JSON
astorage db search "triet hoc"           # Sub-20ms FTS5 search
astorage kiem-tra                        # Chuẩn V6 + Catalog V7 audit
astorage danh-muc-chuan                  # Dry-run Catalog V7 smart pruning & rename plan
astorage trung-lap --don-rac-he-thong    # Dry-run dedup + MACOSX junk quarantine
astorage undo list                       # Inspect Unified Undo Journal
astorage ui                              # Start local Web Dashboard (127.0.0.1:8765)
astorage desktop                         # Launch Desktop App (pywebview)
astorage auth status                     # Check CLI + OAuth 2.0 Drive backends
astorage trien-khai phat-hanh-drive      # Dry-run publish docs + .whl to Drive [03] QUẢN LÝ
```
