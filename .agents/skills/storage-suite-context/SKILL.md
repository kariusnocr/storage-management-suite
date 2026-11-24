---
name: storage-suite-context
description: Reference context for Karius Academic System (KAS) v1.9.0 (`kas`), Native Android APK (`packaging/android/`, `MainActivity.java`, `KasFileProvider.java`, `styles.xml`, `kas-android.apk`, permanent release SHA-1 signing, Wi-Fi LAN UDP discovery, native APK SHA-256 auto-update, `web/android_bridge.py`, `kas android`), Persistent System Logs & Crash Journal (`core/logger.py`, `kas logs`, `/api/logs/*`), Android Termux & Mobile PWA (`manifest.webmanifest`, `sw.js`), Vault Explorer & Previewer (`ops/explorer.py`, `kas duyet`, `/api/explorer/*`), Desktop Workspace Shell UI (`web/static/{index.html,styles.css,app.js}`), detached lifecycle auto-restart/close (`web/lifecycle.py`), SHA-256 auto-updater (`kas update`), safe uninstaller (`kas uninstall`), multi-vault management (Local Folders + any Google Drive folder), auto-setup (`kas setup`), app settings (`kas settings`), in-app command console, local account/app-lock & 3rd-party integrations (`kas account`), customizable naming rules (`kas rules`), AI Chatbot & MCP Agent (`kas ai`, `kas mcp`), Chuẩn V6 / Danh Mục V7, and kariusnocr/storage-management-suite.
---

# Karius Academic System (KAS `v1.9.0`) Context

## 1. Software Identity & Architecture

- **Software Name**: **Karius Academic System (KAS)** (`v1.9.0`, short display label **`KAS`** on Windows Desktop `KAS.lnk`, Android Home Screen `strings.xml`, and PWA `manifest.webmanifest`)
- **Supported Platforms**: **Windows, Linux, and Android ONLY** (macOS / Darwin / Homebrew / `.app` / `.dmg` are intentionally NOT supported or built in CI/Releases).
- **Python Package & Android App**: `karius-academic-system` (`src/karius_academic_system/`, `tests/`, `docs/`, `packaging/`, `Dockerfile`) and `io.github.kariusnocr.kas` (`packaging/android/` → `kas-android.apk`, `versionCode 10900`)
- **Permanent Android Release Certificate Fingerprints** (stored in GitHub Actions Secrets `KAS_ANDROID_KEYSTORE_*`, NEVER in git):
  - **SHA-1**: `FF:D4:BA:CE:3C:48:C1:53:AF:BC:44:B3:AD:FE:6D:5C:31:8B:61:BC`
  - **SHA-256**: `EC:65:9D:B8:08:53:33:6C:CE:BA:66:46:F2:3F:19:21:D6:2F:12:D3:DB:8B:6C:08:BE:7F:1F:51:14:1E:A0:96`
- **Unified CLI & Desktop/Mobile**: `kas`, `kas-desktop` (`kas ui` / `kas desktop` / `kas android` / `kas logs`)
- **GitHub Repository**: `kariusnocr/storage-management-suite` (**PUBLIC** repo — 1-line Windows PowerShell install, 1-line Android Termux install `packaging/android/install_android_termux.sh`, signed `kas-android.apk`, and offline `kas-windows-sac-safe.zip`!)
- **Windows Encoding Rule (CRITICAL)**: All `.ps1` and `.cmd` scripts in `packaging/windows/` MUST be **100% pure 7-bit ASCII + CRLF** (never Unicode em-dash or diacritics or `chcp 65001` in `.cmd`).
- **Multi-Vault Registry**: `~/.config/kas/vaults.toml` (per-vault isolated data dirs `~/.local/share/kas/vaults/<slug>/`, SQLite DB `kas.db` with automatic FTS5 + non-FTS5 Android fallback).
- **Zero Hardcoded Personal IDs**: `src/karius_academic_system/data/kas_config.json` ships completely generic (`root_id = ""`, `known_ids = {}`).

## 2. Key Subsystems

- **Android Material 3 UI, Permanent Signing, Wi-Fi LAN Discovery & APK Auto-Update (`packaging/android/`, `packaging/build_android_apk.py`, `web/android_bridge.py`, `kas android`, `/api/android/{info,init-vault,lan-mode}`)**:
  - **Native Android APK (`kas-android.apk`, `v1.9.0`)**: Gradle + Chaquopy Python 3.11 (`arm64-v8a`, `x86_64`, `certifi` bundled + Conscrypt CA SSL setup) + permanent `signingConfigs.release` + zero-flash `KasAppTheme` (`styles.xml` `#0C0E12`) + `KasFileProvider.java` (pure Android SDK `ContentProvider` serving `kas/data/updates/` & `kas/data/logs/`) + `network_security_config.xml` + `MainActivity.java` with UDP LAN PC auto-discovery (`KAS_DISCOVER_V1` port `8766`), pre-flight `/api/health` check + `onReceivedError` recovery dialog, native APK installer (`REQUEST_INSTALL_PACKAGES` + `onResume()` auto-resume), `android_native.log` + Share Sheet export, live `getSigningInfo()` SHA-1/SHA-256, dynamic Dark/Light `StatusBar`/`NavigationBar` sync, and `window.KASAndroid` JS bridge.
  - **PC ↔ Android Wi-Fi LAN Pairing**: 1-click `POST /api/android/lan-mode` toggles `ui_host` (`0.0.0.0` ↔ `127.0.0.1`), starts/stops UDP discovery responder (`8766`), opens Windows Firewall Private rules when permitted, prioritizes real Wi-Fi IPv4 (`192.168.*` > `10.*` > `172.16-31.*`, excluding `169.254.*`), and opens local browser to `127.0.0.1` when bound to `0.0.0.0`.
  - **Mobile Material 3 Touch Shell & PWA (`web/static/{index.html,styles.css,app.js,manifest.webmanifest,sw.js}`)**: Short name `KAS`, Material 3 Navigation Bar with active pill indicators (`mobile-nav-pill`), Top App Bar Android mode chip (`#androidTopbarModeBtn`), Drawer quick bar (`#androidDrawerQuickBar`), Explorer **Folder Tree Drawer** + **Modal Bottom Sheet Previewer**, 2-line zero-overflow mobile Explorer rows, 2×2 mobile KPIs, 1-column mobile forms/grids, swipe gestures, and `100dvh` AI chat layout.
- **Persistent System Logs & Crash Journal (`core/logger.py`, `kas logs` / `kas nhat-ki`, `/api/logs`, `/api/logs/export`, `/api/logs/client`, `/api/logs/clear`, `#systemLogsCard` in Tab *Chẩn đoán*)**:
  - Rotating `kas_events.jsonl` & `kas.log` (`2 MB × 3` backups) in `<KAS_DATA_DIR>/logs`, automatic secret redaction (`ghp_...`, `AIza...`, `Bearer ...`, `sk-...`, passwords), global `sys.excepthook` & `threading.excepthook`, HTTP 500 capture, frontend `window.onerror`/`unhandledrejection` capture, Android `android_native.log` merge, and `.TXT`/`.JSON` diagnostic export (with native Android Share Sheet).
- **Vault Explorer & Previewer (`ops/explorer.py`, `kas duyet` / `kas browse`, `/api/explorer/{list,tree,preview,raw,open-os}`)**:
  - 3-pane explorer inside `#tab-explorer`, Back/Forward/Up navigation, Breadcrumbs, accent-insensitive filter, sort, keyboard navigation, Local live streaming (`206 Partial Content`, traversal/XSS hardening) & Google Drive SQLite browsing.
- **Desktop Workspace Shell UI, Lifecycle Auto-Close/Restart, SHA-256 Auto-Updater & Safe Uninstaller**:
  - `web/app.py`, `web/desktop.py`, `web/lifecycle.py`, `ops/updater.py` (desktop `.whl` + native Android `kas-android.apk` SHA-256 flows + auto-shortening legacy Desktop `.lnk` to `KAS.lnk`), `ops/uninstaller.py` (cleans both `KAS.lnk` & legacy `.lnk`).
- **Auto-Setup, App Settings, Command Console, Account / App Lock, Naming Rules & AI/MCP Agent**:
  - `core/tools_env.py`, `ops/setup_tools.py`, `core/settings.py`, `cli/console.py`, `core/accounts.py`, `core/naming_rules.py`, `ai/{tools,mcp_server,bridge}.py`.
- **Optional Personal Vault `[A] STORAGE`**:
  - Root: `194HC3C2WC1BSzfK3cn_0_uUJ4vfDuBsr`, `[03] QUẢN LÝ`: `1dU9BqIFxdLyhsFzxZxOiKWVNHI0vk7W3`, `[01] DANH SÁCH`: `1GqdqbI1yVPD3e-HAenW6WioSQZpPaRYz`, `[07] KIỂM TRA`: `1dpIWrMRwREX-bSt4k-PxSzVxbLrj3XLy`.

## 3. Key Commands

```bash
kas setup                                      # Auto-install Python libs, CLI tools & Vietnamese OCR
kas android info | kas android init-vault      # Android ecosystem info, SHA-1, LAN pairing & Android vault
kas android serve --port 8765                  # Serve KAS over Wi-Fi/LAN + UDP discovery for Android
kas logs | kas logs export --format txt        # View or export system & crash logs (redacted)
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
