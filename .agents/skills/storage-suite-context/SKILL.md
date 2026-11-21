---
name: storage-suite-context
description: Reference context for the [A] STORAGE Google Drive archive and kariusnocr/storage-management-suite (v3.3.0, Chuẩn V6). Use when working on any module [01]-[18], scanning/auditing Drive folders, updating catalogs, or syncing between Google Drive and GitHub.
---

# `[A] STORAGE` & `storage-management-suite` Context (v3.3.0)

## 1. Key Identifiers & Locations

- **GitHub Repository**: `kariusnocr/storage-management-suite` (default branch `main`, CI workflow `.github/workflows/ci.yml` — `Storage Suite CI`)
- **Google Drive Root**: `[A] STORAGE` (`194HC3C2WC1BSzfK3cn_0_uUJ4vfDuBsr`)
- **Governance & Sync Folders** (also defined in `[01] THƯ VIỆN LÕI/storage_config.json`):
  - `[00] TỔNG QUAN`: `1ZLU1RnH4PpJ--CXXPjrum7uxncbOttZU`
  - `[00] TỔNG QUAN/[01] DANH SÁCH` (centralized `v3.1` mirror tree of `2.700+` `Danh Mục Hệ Thống` sheets): `1GqdqbI1yVPD3e-HAenW6WioSQZpPaRYz`
  - `[00] TỔNG QUAN/[02] NHẬT KÍ` (reports, change logs, `sheets_index.json`): `10FI7CMFvGgM9i1rj4IkUFRESv5-ito2Y`
  - `[00] TỔNG QUAN/[03] QUẢN LÝ` (2-way sync mirror of modules `[01]`–`[18]`): `1dU9BqIFxdLyhsFzxZxOiKWVNHI0vk7W3`
  - `[07] KIỂM TRA` (quarantine & ingest staging): `1dpIWrMRwREX-bSt4k-PxSzVxbLrj3XLy`
    - `[01] SHORTCUT LỖI 404`: `1_o38THe5uq1ZDaiSH9l1QdSJZ0ZMlsAr`
    - `[02] SHORTCUT ĐÃ SAO CHÉP`: `1Mp-kCOZkl2MBSihpHBCdARGhVtA6DuxH`
    - `[03] TỆP TRÙNG LẶP`: `1oT10jMXJuS_Av8y_bAzPC_PVZzuj5LXK`
    - `[04] NHẬP DỮ LIỆU`: `1Xhgp46XpL3ng_l_d-_-wHb4S12DTuPri`
- **Master Catalog Spreadsheets**:
  - `Danh Mục Hệ Thống - Storage`: `1BJoV-UtcoSEdjq1w5e0HmfibyTdvLEX8cy22jeKKnDc`
  - `Danh Mục Hệ Thống - Storage (Bản Danh Sách)`: `1Pakm-B2FZFFNOsxct_aRmFm2DDQxsQiVsiwB_l2xQt4`
- **Top-Level Content Branches**:
  - `[01] HỌC THUẬT` (`1seVG0DBozIgAI0_hpQZTc4m6nt1s9UIb`) — Đại học (USSH/VNU-LIC), Cao học, Phổ thông, Chứng chỉ (IELTS, HSK, MOS, TOEIC, VSTEP, ĐGNL-ĐGTD, SAT)
  - `[02] NGHIÊN CỨU` (`19u5gcsMHbmbg03p_miRWC4PP3a42IqWV`) — Lĩnh vực, Liên ngành, Dự án
  - `[03] SÁNG TÁC` (`1BZgLyYTL5YBVT8TJ5f0skYlg69lgQAyU`) — Thơ, Văn
  - `[04] BIÊN TẬP` (`1z0wYSabv04y2TkxUja_RzvPs8LKLmvSX`) — G-Obsidians, điểm sách, đề cương
  - `[05] SƯU TẦM` (`1L9IE9jHC5bUIB6UMwqXN0qDzfGW5DAm3`) — Sách (`[01]`–`[19]`), Tài liệu, Khoá học, Âm nhạc
  - `[06] ĐỒNG BỘ` (`1zHUIuJq-QKrfbom1B63GWOc1V0HhfJUd`) — `[01] M-OBSIDIANS`

## 2. Chuẩn V6 Naming Rules

1. **Folders**: `[STT] TÊN IN HOA CÓ DẤU` (2–3 digits in brackets, Vietnamese uppercase with diacritics, natural spaces, no `_`).
2. **Content & Governance Files**: `Tên Viết Hoa Đầu Mỗi Chữ Có Dấu - Thông Tin Bổ Sung.[đuôi]` (no `[STT]` prefix; ` - ` separator; comma-separated metadata; lowercase extension; no extension for native Google Docs/Sheets/Slides/Shortcuts).
3. **Source Code & Technical Configs**: `snake_case` PEP 8 (e.g. `storage_core.py`, `storage_config.json`, `sheets_index.json`, `.obsidian/*`).

## 3. Architecture (`[01]`–`[18]`) & Unified CLI

All modules are orchestrated through `[09] ĐIỀU PHỐI VẬN HÀNH/storage_cli.py`:
- `[01]` `storage_core.py` / `storage_config.json` / `tests/test_storage_suite.py` (`kiem-thu`)
- `[02]` `storage_indexer.py` (`quet` — wave-based BFS `stream_ls`, supports `--tang-cuong`, `--nhanh`)
- `[03]` `naming_auditor.py` (`kiem-tra`) & `[04]` `storage_toolkit.py` (`chuan-hoa`)
- `[05]` `sheet_engine.py` / `sheet_updater.py` (`danh-muc`)
- `[06]` `dedup_scanner.py` (`trung-lap`) & `[07]` `stats_reporter.py` (`bao-cao`)
- `[08]` `deploy_sync.py` (`trien-khai` — skips dotfiles such as `.agents`, `.git`, `.github`)
- `[10]` `transfer_manager.py` (`sao-chep-di-chuyen`), `[11]` `data_ingestor.py` (`nhap-du-lieu`), `[12]` `storage_inspector.py` (`tra-cuu`)
- `[13]` `file_reader.py` (`doc-tep`), `[14]` `content_analyzer.py` (`phan-tich`), `[15]` `github_sync.py` (`github`)
- `[16]` `image_analyzer.py` (`phan-tich-anh`), `[17]` `audio_analyzer.py` (`phan-tich-am-thanh`), `[18]` `video_analyzer.py` (`phan-tich-video`)

## 4. Safety & Operational Rules

1. **Dry-run by default**: Drive/GitHub writes only execute when `--thuc-thi` (or `--execute` in `[04]`) is passed.
2. **Preserve Drive File IDs & never hard-delete**: Always update/rename in place; quarantine duplicates, broken shortcuts, and empty folders under `[07] KIỂM TRA` with undo logs.
3. **Separate runtime data from Git**: Keep indexes, caches, snapshots, and `tessdata/` under `STORAGE_DATA_DIR` (default `~/storage_data`), never inside the Git repo.
4. **Verification commands**:
   ```bash
   python3 "[09] ĐIỀU PHỐI VẬN HÀNH/storage_cli.py" kiem-thu
   python3 "[15] ĐỒNG BỘ GITHUB/github_sync.py" kiem-tra-bao-mat
   python3 "[09] ĐIỀU PHỐI VẬN HÀNH/storage_cli.py" github trang-thai
   python3 "[09] ĐIỀU PHỐI VẬN HÀNH/storage_cli.py" quet --tang-cuong
   ```
