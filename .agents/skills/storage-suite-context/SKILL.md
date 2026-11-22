---
name: storage-suite-context
description: Reference context for Karius Academic System (KAS) v1.5.1 (`kas`), Desktop Workspace Shell UI (`web/static/{index.html,styles.css,app.js}`), SHA-256 auto-updater (`kas update`), safe uninstaller (`kas uninstall`), multi-vault management (Local Folders + any Google Drive folder), auto-setup of tools/libraries/Vietnamese OCR (`kas setup`), app settings (`kas settings`), in-app command console, local account/app-lock & 3rd-party integrations (`kas account`), customizable naming rules (`kas rules`), AI Chatbot & MCP Agent (`kas ai`, `kas mcp`), Chuẩn V6 / Danh Mục V7, and kariusnocr/storage-management-suite.
---

# Karius Academic System (KAS `v1.5.1`) Context

## 1. Software Identity & Architecture

- **Software Name**: **Karius Academic System (KAS)** (`v1.5.1`)
- **Python Package**: `karius-academic-system` (`src/karius_academic_system/`, `tests/`, `docs/`, `packaging/`, `Dockerfile`)
- **Unified CLI & Desktop**: `kas` and `kas-desktop` (`kas ui` / `kas desktop`)
- **GitHub Repository**: `kariusnocr/storage-management-suite` (**PUBLIC** repo — 1-line PowerShell install `irm https://raw.githubusercontent.com/kariusnocr/storage-management-suite/main/packaging/windows/install_windows_sac_safe.ps1 | iex` and offline `kas-windows-sac-safe.zip` + `Cai_Dat_KAS_Windows11.cmd` both work and automatically run `kas setup`!)
- **Windows Encoding Rule (CRITICAL)**: All `.ps1` and `.cmd` scripts in `packaging/windows/` MUST be **100% pure 7-bit ASCII + CRLF** (never Unicode em-dash or diacritics or `chcp 65001` in `.cmd`).
- **Multi-Vault Registry**: `~/.config/kas/vaults.toml` (per-vault isolated data dirs `~/.local/share/kas/vaults/<slug>/`, SQLite DB `kas.db`).
- **Zero Hardcoded Personal IDs**: `src/karius_academic_system/data/kas_config.json` ships completely generic (`root_id = ""`, `known_ids = {}`).

## 2. Key Subsystems

- **Desktop Workspace Shell UI (`web/app.py`, `web/static/{index.html,styles.css,app.js}`)**:
  - Modular zero-CDN Vanilla HTML/CSS/JS (*Obsidian Ink* Dark & *Archival Paper* Light), collapsible 4-group sidebar (`Ctrl+B`), global Command Palette (`Ctrl+K`) with live debounced FTS5 file search, proportional horizontal storage bars, custom confirm/prompt modal & toast stack, strict path-traversal protection on `/static/*` (both stdlib & FastAPI), and App Lock static-asset compatibility.
- **SHA-256 Verified Auto-Updater & Safe Uninstaller (`ops/updater.py`, `ops/uninstaller.py`, `kas update`, `kas uninstall`)**:
  - Cached background startup check, `SHA256SUMS.txt` verification, zero-downtime detached auto-restart & browser reload, update history + 1-click Rollback, and 4-way safe uninstall (Windows Installed Apps Registry, in-UI 2-step `GO-CAI-DAT`, PowerShell 1-liner, `.cmd` / CLI).
- **Auto-Setup & Cross-Platform PATH Self-Healing (`core/tools_env.py`, `ops/setup_tools.py`, `kas setup`, Tab *Chẩn đoán*)**:
  - Automatically installs recommended Python packages (`Pillow`, `numpy`, `fastapi`, `uvicorn`) with Windows Smart App Control `OSError` protection, installs missing system tools via `winget`/`brew` (`gh`, `git`, `7z`, `ffmpeg`/`ffprobe`, `tesseract`, `poppler`), downloads Vietnamese + English OCR data (`vie.traineddata`, `eng.traineddata`) into `~/.local/share/kas/tessdata`, and refreshes/persists Windows User PATH automatically.
- **App Settings (`core/settings.py` & `kas settings`)**:
  - Persisted at `~/.config/kas/app_settings.json` (theme, language, default tab, UI host/port, default backend, scan workers, catalog mode, custom data dir override, GitHub update check & channel, backup export/import JSON).
- **In-App Command Console (`cli/console.py` & Console Tab)**:
  - Runs `kas ...` commands directly inside Web/Desktop UI with Windows path-safe `shlex.split(..., posix=False)`, recursive command guard, persistent `~/.config/kas/command_history.json`, and async job polling.
- **Account / App Lock & 3rd-Party Integrations (`core/accounts.py` & `kas account`)**:
  - Local account at `~/.config/kas/account.json` (`0600`) with PBKDF2-HMAC-SHA256 (200k iterations), `HttpOnly; SameSite=Lax` session cookie guard across all `/api/*` endpoints when `require_login=True`.
  - In-UI Google Drive OAuth 2.0 credentials upload/paste + 1-click browser login, GitHub PAT verification/connect, AI provider summary, and custom Webhook/n8n/WebDAV/REST connectors (`~/.config/kas/integrations.json`).
- **Customizable Naming Rules (`core/naming_rules.py` & `kas rules`)**:
  - 4 presets (`academic_v6`, `general_clean`, `snake_case_dev`, `kebab_web`) + per-vault/global customization + live simulator.
- **AI Chatbot & MCP Agent (`ai/` & `kas ai` / `kas mcp`)**:
  - 10 JSON-Schema tools (`ai/tools.py`) shared by native MCP JSON-RPC 2.0 server (`kas mcp serve` + HTTP `POST /api/mcp`) and multi-provider AI Chatbot (`builtin_offline`, `openai_compat`, `gemini`, `anthropic`).
- **Optional Personal Vault `[A] STORAGE`**:
  - Root: `194HC3C2WC1BSzfK3cn_0_uUJ4vfDuBsr`, `[03] QUẢN LÝ`: `1dU9BqIFxdLyhsFzxZxOiKWVNHI0vk7W3`, `[01] DANH SÁCH`: `1GqdqbI1yVPD3e-HAenW6WioSQZpPaRYz`, `[07] KIỂM TRA`: `1dpIWrMRwREX-bSt4k-PxSzVxbLrj3XLy`.

## 3. Key Commands

```bash
kas setup                                      # Auto-install Python libs, CLI tools (gh, tesseract, ffmpeg, 7z, poppler) & Vietnamese OCR
kas vault add "My Vault" "E:\SÁCH"             # Connect any local folder
kas vault add "Drive Vault" <URL_or_ID>        # Connect any Google Drive folder
kas settings show | kas settings check-update  # App settings & release check
kas account status | kas account register ...  # Local account/App Lock & GitHub connect
kas rules presets | kas rules apply-preset ... # Customize naming rules
kas ai ask "..."  | kas ai chat                # Built-in AI Chatbot/Agent
kas mcp serve     | kas mcp config             # MCP Server for Claude/Cursor/Antigravity
kas doctor | kas kiem-thu | kas quet           # Diagnostics, tests, indexing
kas desktop --browser --stdlib                 # Windows 11 SAC-safe Desktop App
```
