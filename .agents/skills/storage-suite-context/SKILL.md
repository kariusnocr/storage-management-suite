---
name: storage-suite-context
description: Reference context for Karius Academic System (KAS) v5.0.0 (`kas`), multi-vault management (Local Folders + any Google Drive folder), Chuẩn V6 / Chuẩn Danh Mục V7, the [A] STORAGE vault, and kariusnocr/storage-management-suite. Use when operating on KAS vaults, updating catalogs, running audits/analyzers, or syncing Drive and GitHub.
---

# Karius Academic System (KAS `v5.0.0`) Context

## 1. Software Identity & Architecture

- **Software Name**: **Karius Academic System (KAS)** (`v5.0.0`)
- **Python Package**: `karius-academic-system` (`src/karius_academic_system/`, `tests/`, `docs/`, `packaging/`, `Dockerfile`)
- **Unified CLI & Desktop**: `kas` and `kas-desktop` (`kas ui` / `kas desktop`)
- **GitHub Repository**: `kariusnocr/storage-management-suite`
- **Multi-Vault Registry**: `~/.config/kas/vaults.toml` (per-vault isolated data dirs `~/.local/share/kas/vaults/<slug>/`, SQLite DB `kas.db`).
- **Zero Hardcoded Personal IDs**: `src/karius_academic_system/data/kas_config.json` ships completely generic (`root_id = ""`, `known_ids = {}`). Any local directory or Google Drive folder/Shared Drive can be added as a vault.

## 2. Example Vault: `[A] STORAGE` (Optional Personal Vault)

When operating specifically on the user's mounted `[A] STORAGE` Google Drive archive, register it via `kas vault add "[A] STORAGE" 194HC3C2WC1BSzfK3cn_0_uUJ4vfDuBsr --slug a-storage --backend cli`:
- **Root**: `[A] STORAGE` (`194HC3C2WC1BSzfK3cn_0_uUJ4vfDuBsr`)
- **System Folders (auto-discovered on scan)**:
  - `[00] TỔNG QUAN`: `1ZLU1RnH4PpJ--CXXPjrum7uxncbOttZU`
  - `[00] TỔNG QUAN/[01] DANH SÁCH`: `1GqdqbI1yVPD3e-HAenW6WioSQZpPaRYz`
  - `[00] TỔNG QUAN/[02] NHẬT KÍ`: `10FI7CMFvGgM9i1rj4IkUFRESv5-ito2Y`
  - `[00] TỔNG QUAN/[03] QUẢN LÝ`: `1dU9BqIFxdLyhsFzxZxOiKWVNHI0vk7W3`
  - `[07] KIỂM TRA`: `1dpIWrMRwREX-bSt4k-PxSzVxbLrj3XLy`

## 3. Vault Modes (`auto` | `academic_v7` | `general`)

- **`academic_v7`**: Auto-detected when a vault has `[00] TỔNG QUAN` / `[07] KIỂM TRA` or `>= 50%` `[NN] ...` top-level folders. Enables full Chuẩn V6 naming + **Chuẩn Danh Mục V7** (zero-collision + smart pruning) rules.
- **`general`**: Auto-detected for ordinary local/Drive vaults. Audits duplicate names, `MACOSX`/OS junk, and fatal filename issues without false `[STT]` structural spam.
- Optional structure scaffold on any vault: `kas vault init-structure --thuc-thi`.

## 4. Three Storage Backends (`KAS_BACKEND=auto|local|cli|api`)

1. **`local`** (`LocalFSBackend`): Any local folder, external HDD, NAS, or OneDrive/iCloud/Google Drive Desktop synced folder (100% offline, `loc:` IDs).
2. **`cli`** (`GDriveCLIClient`): Cloud VM `gdrive` CLI binary (`stream_ls`).
3. **`api`** (`GoogleDriveAPIClient`): Standalone OAuth 2.0 Google Drive API v3 (`kas auth login`) for Windows/macOS/Linux.

## 5. Key Commands

```bash
kas vault add "My Vault" ~/Documents/Study     # Connect any local folder
kas vault add "Drive Vault" <URL_or_ID>        # Connect any Google Drive folder
kas vault list                                 # List connected vaults
kas vault use <slug>                           # Switch default vault
kas --kho <slug> quet --tang-cuong             # Scan a specific vault -> kas.db (FTS5)
kas doctor                                     # Full environment, vault & backend check
kas kiem-thu                                   # Run offline test suite
kas db search "triet hoc"                      # Sub-20ms FTS5 search
kas kiem-tra                                   # Mode-aware audit (general or V6+V7)
kas danh-muc-chuan                             # Dry-run Catalog V7 smart pruning & rename plan
kas trung-lap --don-rac-he-thong               # Dry-run dedup + MACOSX junk quarantine
kas undo list                                  # Inspect Unified Undo Journal
kas desktop                                    # Launch Desktop App (SAC-safe Edge/Chrome --app or pywebview)
kas ui --stdlib                                # Zero-DLL pure-Python Web Dashboard (127.0.0.1:8765)
kas auth status                                # Check Local / CLI / OAuth 2.0 backends
```
