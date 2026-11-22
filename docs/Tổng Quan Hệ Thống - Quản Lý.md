# TỔNG QUAN HỆ THỐNG — KARIUS ACADEMIC SYSTEM (KAS `v1.7.0`)

**Karius Academic System (KAS `v1.7.0`)** là nền tảng quản trị tri thức học thuật đa nền tảng (**Windows · macOS · Linux · Android**) với **Ứng dụng Android Gốc (`kas-android.apk`, nhúng Python 3.11 + SQLite qua Chaquopy)**, **Trình Duyệt Kho & Xem Trước Tệp trực tiếp (Vault Explorer & Previewer)**, **giao diện Desktop Workspace & Mobile Touch Shell (*Obsidian Ink* & *Archival Paper*)**, **Bảng Lệnh toàn cục `Ctrl+K`**, đa kho dữ liệu (Multi-Vault), tùy chỉnh quy tắc đặt tên linh hoạt, dòng lệnh tích hợp, tự động cài công cụ/OCR (`kas setup`), tự động cập nhật xác thực SHA-256 (`kas update`), gỡ cài đặt sạch (`kas uninstall`), bảo vệ đăng nhập cục bộ, kết nối dịch vụ bên thứ 3 (Google Drive OAuth 2.0, GitHub, AI, Webhook/Connector) và máy chủ AI/MCP Agent — hỗ trợ **mọi thư mục cục bộ trên máy tính/điện thoại Android** và **mọi thư mục / Shared Drive trên Google Drive**, phát triển tại **`kariusnocr/storage-management-suite`**.

---

## 1. Kiến trúc Gói Phần Mềm (`src/karius_academic_system/` & `packaging/android/`)

Toàn bộ phần mềm được đóng gói chuẩn Python **`karius-academic-system`** (`v1.7.0`) và gói ứng dụng Android **`kas-android.apk`** với lệnh điều phối duy nhất **`kas`** và ứng dụng giao diện **`kas ui`** / **`kas desktop`** / **`kas android`**:

| Phân hệ gói | Mô-đun chính | Lệnh `kas` | Vai trò |
| :--- | :--- | :--- | :--- |
| `core/` | `vaults`, `local_fs`, `config`, `settings`, `accounts`, `tools_env`, `naming`, `naming_rules`, `catalog_spec`, `drive_api`, `drive_cli`, `ocr` | `vault`, `settings`, `account`, `rules`, `auth`, `version` | Sổ đăng ký đa kho (`vaults.toml`), `LocalFSBackend`, **Cài đặt ứng dụng** (`app_settings.json`), **Tài khoản PBKDF2 / App Lock & Kết nối bên thứ 3** (Google Drive OAuth 2.0, GitHub PAT, Custom Connectors), Quy tắc đặt tên tùy chỉnh, Chuẩn V6/V7, tự làm mới PATH & OCR `vie+eng` |
| `ai/` | `tools`, `mcp_server`, `bridge` | `ai`, `mcp` | **10 công cụ Agent chuẩn JSON Schema**, máy chủ **MCP (JSON-RPC 2.0)** qua stdio & HTTP `/api/mcp`, Chatbot AI tích hợp (Offline cục bộ, Ollama, OpenAI, Gemini, Claude) |
| `store/` | `sqlite_store`, `legacy_compat` | `db`, `undo` | Cơ sở dữ liệu SQLite riêng theo từng kho (`kas.db`, WAL + FTS5 tìm kiếm `<20 ms` + Android Fallback) và Sổ cái Hoàn tác Hợp nhất |
| `ops/` | `explorer`, `indexer`, `auditor`, `normalizer`, `catalog_engine`, `dedup`, `reporter`, `transfer`, `ingestor`, `inspector`, `doctor`, `setup_tools`, `uninstaller`, `updater`, `watcher` | `duyet`, `quet`, `kiem-tra`, `chuan-hoa`, `danh-muc`, `danh-muc-chuan`, `trung-lap`, `bao-cao`, `sao-chep-di-chuyen`, `nhap-du-lieu`, `tra-cuu`, `doctor`, `setup`, `update`, `uninstall`, `watch` | **Duyệt thư mục & xem trước đa định dạng thời gian thực / SQLite**, quản trị kho đa nguồn, tự động cài đặt công cụ/OCR, tự động cập nhật SHA-256 + Rollback, gỡ cài đặt an toàn, tinh gọn danh mục V7, dọn rác `MACOSX` |
| `media/` | `file_reader`, `content_analyzer`, `image_analyzer`, `audio_analyzer`, `video_analyzer` | `doc-tep`, `phan-tich`, `phan-tich-anh`, `phan-tich-am-thanh`, `phan-tich-video` | Đọc đa định dạng, TF-IDF/SimHash, EXIF/dHash/pHash/OCR `vie+eng`, ID3/EBU R128 LUFS, Contact Sheet 3×2 |
| `sync/` | `drive_deploy`, `github_sync` | `trien-khai`, `github` | Xuất bản tài liệu + gói cài đặt (`.whl`, `.zip`, `.exe`, `.apk`) lên `[03] QUẢN LÝ`, kiểm toán bảo mật, đồng bộ Git/GitHub |
| `cli/`, `web/` & `packaging/android/` | `cli/main`, `cli/console`, `web/app`, `web/desktop`, `web/lifecycle`, `web/android_bridge`, `web/static/{index.html,styles.css,app.js,manifest.webmanifest,sw.js}`, `MainActivity.java` | `android`, `quy-trinh-nhanh`, `bao-tri-dinh-ki`, `ui`, `desktop` | **Ứng dụng Android Gốc (`kas-android.apk`), Thanh Điều Hướng Đáy Di Động & PWA**, ghép nối Wi-Fi/LAN, Trình Duyệt Kho 3 khung, Collapsible Sidebar, `Ctrl+K` Command Palette, tự đóng/khởi động lại khi cập nhật/gỡ, Web Server FastAPI + `--stdlib` |

---

## 2. Quy trình Vận hành Chuẩn

```bash
# Kết nối kho bất kỳ, cấu hình cài đặt & tài khoản
kas vault add "Tủ Sách" "E:\SÁCH"
kas vault add "[A] STORAGE" "https://drive.google.com/drive/folders/<FOLDER_ID>"
kas android info                         # Xem trạng thái Android, link tải APK & IP ghép nối Wi-Fi/LAN
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
