---
name: storage-suite-context
description: Reference context for Karius Academic System (KAS) v1.0.0 (`kas`), multi-vault management (Local Folders + any Google Drive folder), customizable naming rules (`kas rules`), AI Chatbot & MCP Agent (`kas ai`, `kas mcp`), Chuẩn V6 / Danh Mục V7, and kariusnocr/storage-management-suite.
---

# Karius Academic System (KAS `v1.0.0`) Context

## 1. Software Identity & Architecture

- **Software Name**: **Karius Academic System (KAS)** (`v1.0.0`)
- **Python Package**: `karius-academic-system` (`src/karius_academic_system/`, `tests/`, `docs/`, `packaging/`, `Dockerfile`)
- **Unified CLI & Desktop**: `kas` and `kas-desktop` (`kas ui` / `kas desktop`)
- **GitHub Repository**: `kariusnocr/storage-management-suite` (PRIVATE repo — Windows SAC-safe installs use `kas-windows-sac-safe.zip` + `Cai_Dat_KAS_Windows11.cmd` or `gh api`!)
- **Multi-Vault Registry**: `~/.config/kas/vaults.toml` (per-vault isolated data dirs `~/.local/share/kas/vaults/<slug>/`, SQLite DB `kas.db`).
- **Zero Hardcoded Personal IDs**: `src/karius_academic_system/data/kas_config.json` ships completely generic (`root_id = ""`, `known_ids = {}`).

## 2. Key Subsystems

- **Customizable Naming Rules (`core/naming_rules.py` & `kas rules`)**:
  - 4 presets (`academic_v6`, `general_clean`, `snake_case_dev`, `kebab_web`) + full per-vault (`<vault_data_dir>/naming_rules.json`) or global (`~/.config/kas/naming_rules.json`) customization + live simulator (`preview_naming`).
- **AI Chatbot & MCP Agent (`ai/` & `kas ai` / `kas mcp`)**:
  - 10 safe JSON-Schema tools (`ai/tools.py`) shared by native pure-Python MCP JSON-RPC 2.0 server (`kas mcp serve` + HTTP `POST /api/mcp`) and multi-provider AI Chatbot (`builtin_offline`, `openai_compat` [OpenAI/Ollama/LM Studio/OpenRouter/Groq], `gemini`, `anthropic`).
- **Optional Personal Vault `[A] STORAGE`**:
  - Root: `194HC3C2WC1BSzfK3cn_0_uUJ4vfDuBsr`, `[03] QUẢN LÝ`: `1dU9BqIFxdLyhsFzxZxOiKWVNHI0vk7W3`, `[01] DANH SÁCH`: `1GqdqbI1yVPD3e-HAenW6WioSQZpPaRYz`, `[07] KIỂM TRA`: `1dpIWrMRwREX-bSt4k-PxSzVxbLrj3XLy`.

## 3. Key Commands

```bash
kas vault add "My Vault" ~/Documents/Study     # Connect any local folder
kas vault add "Drive Vault" <URL_or_ID>        # Connect any Google Drive folder
kas rules presets | kas rules apply-preset ... # Customize naming rules
kas ai ask "..."  | kas ai chat                # Built-in AI Chatbot/Agent
kas mcp serve     | kas mcp config             # MCP Server for Claude/Cursor/Antigravity
kas doctor | kas kiem-thu | kas quet           # Diagnostics, tests, indexing
kas desktop --browser --stdlib                 # Windows 11 SAC-safe Desktop App
```
