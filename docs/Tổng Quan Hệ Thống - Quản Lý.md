# TỔNG QUAN HỆ THỐNG — KARIUS ACADEMIC SYSTEM (KAS `v1.6.0`)

**Karius Academic System (KAS `v1.6.0`)** là nền tảng quản trị tri thức học thuật với **Trình Duyệt Kho & Xem Trước Tệp trực tiếp (Vault Explorer & Previewer)**, **giao diện Desktop Workspace Shell (*Obsidian Ink* & *Archival Paper*)**, **Bảng Lệnh toàn cục `Ctrl+K`**, đa kho dữ liệu (Multi-Vault), tùy chỉnh quy tắc đặt tên linh hoạt, dòng lệnh tích hợp, tự động cài công cụ/OCR (`kas setup`), tự động cập nhật xác thực SHA-256 (`kas update`), gỡ cài đặt sạch (`kas uninstall`), bảo vệ đăng nhập cục bộ, kết nối dịch vụ bên thứ 3 (Google Drive OAuth 2.0, GitHub, AI, Webhook/Connector) và máy chủ AI/MCP Agent — hỗ trợ **mọi thư mục cục bộ trên máy tính** và **mọi thư mục / Shared Drive trên Google Drive**, phát triển tại **`kariusnocr/storage-management-suite`**.

---

## 1. Kiến trúc Gói Phần Mềm (`src/karius_academic_system/`)

Toàn bộ phần mềm được đóng gói chuẩn Python **`karius-academic-system`** (`v1.6.0`) với lệnh điều phối duy nhất **`kas`** và ứng dụng giao diện **`kas ui`** / **`kas desktop`**:

| Phân hệ gói | Mô-đun chính | Lệnh `kas` | Vai trò |
| :--- | :--- | :--- | :--- |
| `core/` | `vaults`, `local_fs`, `config`, `settings`, `accounts`, `tools_env`, `naming`, `naming_rules`, `catalog_spec`, `drive_api`, `drive_cli`, `ocr` | `vault`, `settings`, `account`, `rules`, `auth`, `version` | Sổ đăng ký đa kho (`vaults.toml`), `LocalFSBackend`, **Cài đặt ứng dụng** (`app_settings.json`), **Tài khoản PBKDF2 / App Lock & Kết nối bên thứ 3** (Google Drive OAuth 2.0, GitHub PAT, Custom Connectors), Quy tắc đặt tên tùy chỉnh, Chuẩn V6/V7, tự làm mới PATH & OCR `vie+eng` |
| `ai/` | `tools`, `mcp_server`, `bridge` | `ai`, `mcp` | **10 công cụ Agent chuẩn JSON Schema**, máy chủ **MCP (JSON-RPC 2.0)** qua stdio & HTTP `/api/mcp`, Chatbot AI tích hợp (Offline cục bộ, Ollama, OpenAI, Gemini, Claude) |
| `store/` | `sqlite_store`, `legacy_compat` | `db`, `undo` | Cơ sở dữ liệu SQLite riêng theo từng kho (`kas.db`, WAL + FTS5 tìm kiếm `<20 ms`) và Sổ cái Hoàn tác Hợp nhất |
| `ops/` | `explorer`, `indexer`, `auditor`, `normalizer`, `catalog_engine`, `dedup`, `reporter`, `transfer`, `ingestor`, `inspector`, `doctor`, `setup_tools`, `uninstaller`, `updater`, `watcher` | `duyet`, `quet`, `kiem-tra`, `chuan-hoa`, `danh-muc`, `danh-muc-chuan`, `trung-lap`, `bao-cao`, `sao-chep-di-chuyen`, `nhap-du-lieu`, `tra-cuu`, `doctor`, `setup`, `update`, `uninstall`, `watch` | **Duyệt thư mục & xem trước đa định dạng thời gian thực / SQLite**, quản trị kho đa nguồn, tự động cài đặt công cụ/OCR, tự động cập nhật SHA-256 + Rollback, gỡ cài đặt an toàn, tinh gọn danh mục V7, dọn rác `MACOSX` |
| `media/` | `file_reader`, `content_analyzer`, `image_analyzer`, `audio_analyzer`, `video_analyzer` | `doc-tep`, `phan-tich`, `phan-tich-anh`, `phan-tich-am-thanh`, `phan-tich-video` | Đọc đa định dạng, TF-IDF/SimHash, EXIF/dHash/pHash/OCR `vie+eng`, ID3/EBU R128 LUFS, Contact Sheet 3×2 |
| `sync/` | `drive_deploy`, `github_sync` | `trien-khai`, `github` | Xuất bản tài liệu + gói cài đặt lên `[03] QUẢN LÝ`, kiểm toán bảo mật, đồng bộ Git/GitHub |
| `cli/` & `web/` | `cli/main`, `cli/console`, `cli/pipelines`, `web/app`, `web/desktop`, `web/lifecycle`, `web/static/{index.html,styles.css,app.js}` | `quy-trinh-nhanh`, `bao-tri-dinh-ki`, `ui`, `desktop` | Pipeline in-process, **Desktop Workspace Shell (Trình Duyệt Kho 3 khung, Collapsible Sidebar, `Ctrl+K` Command Palette, Toast & Custom Modal, Storage Bars)**, tự đóng/khởi động lại khi cập nhật/gỡ, Dòng lệnh tích hợp, Web Server FastAPI + `--stdlib` an toàn Windows 11 SAC & App Lock |

---

## 2. Quy trình Vận hành Chuẩn

```bash
# Kết nối kho bất kỳ, cấu hình cài đặt & tài khoản
kas vault add "Tủ Sách" "E:\SÁCH"
kas vault add "[A] STORAGE" "https://drive.google.com/drive/folders/<FOLDER_ID>"
kas settings show
kas account status

# Duyệt thư mục, quét chỉ mục, kiểm toán & AI/Agent
kas duyet                                # Liệt kê nhanh thư mục gốc của kho hiện hành
kas doctor                               # Kiểm tra công cụ, sổ kho, OCR vie+eng, backend & SQLite
kas quet --tang-cuong                    # Quét tăng cường vào kas.db (FTS5)
kas kiem-tra                             # Kiểm toán theo quy tắc tùy chỉnh của kho
kas ai chat                              # Trò chuyện trực tiếp với Trợ Lý AI/Agent KAS
kas mcp config --client claude           # Xuất cấu hình MCP cho Claude Desktop / Cursor / Antigravity
kas desktop --browser --stdlib           # Mở ứng dụng Desktop Karius Academic System (KAS)
```
