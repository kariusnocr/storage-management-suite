---
name: storage-suite-context
description: Reference context for Karius Academic System (KAS) v1.7.0 (`kas`), Native Android APK (`packaging/android/`, `kas-android.apk`, `web/android_bridge.py`, `kas android`), Android Termux & Mobile PWA (`manifest.webmanifest`, `sw.js`), Vault Explorer & Previewer (`ops/explorer.py`, `kas duyet`, `/api/explorer/*`), Desktop Workspace Shell UI (`web/static/{index.html,styles.css,app.js}`), detached lifecycle auto-restart/close (`web/lifecycle.py`), SHA-256 auto-updater (`kas update`), safe uninstaller (`kas uninstall`), multi-vault management (Local Folders + any Google Drive folder), auto-setup (`kas setup`), app settings (`kas settings`), in-app command console, local account/app-lock & 3rd-party integrations (`kas account`), customizable naming rules (`kas rules`), AI Chatbot & MCP Agent (`kas ai`, `kas mcp`), Chuẩn V6 / Danh Mục V7, and kariusnocr/storage-management-suite.
---

# Karius Academic System (KAS `v1.7.0`) Context

## 1. Software Identity & Architecture

- **Software Name**: **Karius Academic System (KAS)** (`v1.7.0`)
- **Python Package & Android App**: `karius-academic-system` (`src/karius_academic_system/`, `tests/`, `docs/`, `packaging/`, `Dockerfile`) and `io.github.kariusnocr.kas` (`packaging/android/` → `kas-android.apk`)
- **Unified CLI & Desktop/Mobile**: `kas`, `kas-desktop` (`kas ui` / `kas desktop` / `kas android`)
- **GitHub Repository**: `kariusnocr/storage-management-suite` (**PUBLIC** repo — 1-line Windows PowerShell install, 1-line Android Termux install `packaging/android/install_android_termux.sh`, native `kas-android.apk`, and offline `kas-windows-sac-safe.zip`!)
- **Windows Encoding Rule (CRITICAL)**: All `.ps1` and `.cmd` scripts in `packaging/windows/` MUST be **100% pure 7-bit ASCII + CRLF** (never Unicode em-dash or diacritics or `chcp 65001` in `.cmd`).
- **Multi-Vault Registry**: `~/.config/kas/vaults.toml` (per-vault isolated data dirs `~/.local/share/kas/vaults/<slug>/`, SQLite DB `kas.db` with automatic FTS5 + non-FTS5 Android fallback).
- **Zero Hardcoded Personal IDs**: `src/karius_academic_system/data/kas_config.json` ships completely generic (`root_id = ""`, `known_ids = {}`).

## 2. Key Subsystems

- **Android Operating System Ecosystem (`packaging/android/`, `packaging/build_android_apk.py`, `web/android_bridge.py`, `kas android`, `/api/android/{info,init-vault}`)**:
  - **Native Android APK (`kas-android.apk`)**: Gradle + Chaquopy Python 3.11 (`arm64-v8a`, `x86_64`) + `MainActivity.java` WebView + `window.KASAndroid` JS bridge (`showServerSwitcher`, `requestStorageAccess`, hardware Back button hook `window.kasHandleAndroidBack`, native file chooser & `DownloadManager`). Runs standalone on-device (`127.0.0.1`) or connects to a PC KAS server over Wi-Fi/LAN.
  - **Mobile Touch Shell & PWA (`manifest.webmanifest`, `sw.js`, `#mobileBottomNav`)**: 5-button bottom navigation bar on mobile screens (`<= 860px`), single-tap folder entry on touch devices, and installable PWA manifest + service worker.
  - **Termux 1-Liner (`packaging/android/install_android_termux.sh`)**: Installs Python, Git, Tesseract + `vie.traineddata`, FFmpeg, 7z, Poppler, creates `~/.shortcuts/KAS.sh`, and launches KAS UI on Android.
- **Vault Explorer & Previewer (`ops/explorer.py`, `kas duyet` / `kas browse`, `/api/explorer/{list,tree,preview,raw,open-os}`)**:
  - 3-pane explorer inside `#tab-explorer` (Lazy Folder Tree + List/Grid view + Sticky Preview Inspector), Back/Forward/Up navigation, Breadcrumbs, accent-insensitive filter, sort by name/size/modified/type, keyboard navigation (`↑`/`↓`/`Enter`/`Backspace`/`Alt+←/→/↑`), jump-to-location from Overview branches, FTS5 Search, and `Ctrl+K` Command Palette.
  - Supports **Local vaults live** (`LocalFSBackend` + OS default open/reveal + HTTP `206 Partial Content` streaming for audio/video/PDF + 2-layer traversal/symlink protection + XSS hardening for HTML/JS/SVG) and **Google Drive vaults** (instant SQLite browsing + cached/on-demand Drive content extraction).
- **Desktop Workspace Shell UI (`web/app.py`, `web/static/{index.html,styles.css,app.js}`)**:
  - Modular zero-CDN Vanilla HTML/CSS/JS (*Obsidian Ink* Dark & *Archival Paper* Light), collapsible 4-group sidebar (`Ctrl+B`), global Command Palette (`Ctrl+K`) with live debounced FTS5 file search, proportional horizontal storage bars, custom confirm/prompt modal & toast stack, strict path-traversal protection on `/static/*` (both stdlib & FastAPI), and App Lock static-asset compatibility.
- **Lifecycle Auto-Close/Restart, SHA-256 Auto-Updater & Safe Uninstaller (`web/lifecycle.py`, `ops/updater.py`, `ops/uninstaller.py`, `kas update`, `kas uninstall`)**:
  - Isolated `browser_profile` + `boot_id` reload verification, PowerShell 5.1 AST CI checks on all static & generated `.ps1` scripts, cached background startup update check, `SHA256SUMS.txt` verification, update history + 1-click Rollback, and 4-way safe uninstall.
- **Auto-Setup & Cross-Platform PATH Self-Healing (`core/tools_env.py`, `ops/setup_tools.py`, `kas setup`, Tab *Chẩn đoán*)**:
  - Automatically installs recommended Python packages (`Pillow`, `numpy`, `fastapi`, `uvicorn`) with Windows Smart App Control `OSError` protection, installs missing system tools via `winget`/`brew`, downloads Vietnamese + English OCR data (`vie.traineddata`, `eng.traineddata`), and refreshes/persists Windows User PATH automatically.
- **App Settings, Command Console, Account / App Lock, Naming Rules & AI/MCP Agent**:
  - `core/settings.py`, `cli/console.py`, `core/accounts.py`, `core/naming_rules.py`, `ai/{tools,mcp_server,bridge}.py`.
- **Optional Personal Vault `[A] STORAGE`**:
  - Root: `194HC3C2WC1BSzfK3cn_0_uUJ4vfDuBsr`, `[03] QUẢN LÝ`: `1dU9BqIFxdLyhsFzxZxOiKWVNHI0vk7W3`, `[01] DANH SÁCH`: `1GqdqbI1yVPD3e-HAenW6WioSQZpPaRYz`, `[07] KIỂM TRA`: `1dpIWrMRwREX-bSt4k-PxSzVxbLrj3XLy`.

## 3. Key Commands

```bash
kas setup                                      # Auto-install Python libs, CLI tools & Vietnamese OCR
kas android info | kas android init-vault      # Android ecosystem info, LAN pairing & local Android vault
kas android serve --port 8765                  # Serve KAS over Wi-Fi/LAN for Android devices
kas vault add "My Vault" "E:\SÁCH"             # Connect any local folder
kas vault add "Drive Vault" <URL_or_ID>        # Connect any Google Drive folder
kas duyet [path] [--xem]                       # Browse folders & preview files from CLI/Console
kas settings show | kas settings check-update  # App settings & release check
kas account status | kas account register ...  # Local account/App Lock & GitHub connect
kas rules presets | kas rules apply-preset ... # Customize naming rules
kas ai ask "..."  | kas ai chat                # Built-in AI Chatbot/Agent
kas mcp serve     | kas mcp config             # MCP Server for Claude/Cursor/Antigravity
kas doctor | kas kiem-thu | kas quet           # Diagnostics, tests, indexing
kas desktop --browser --stdlib                 # Windows 11 SAC-safe Desktop App
```
