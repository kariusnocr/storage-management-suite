# TỔNG QUAN HỆ THỐNG — KARIUS ACADEMIC SYSTEM (KAS `v1.0.0`)

**Karius Academic System (KAS `v1.0.0`)** là nền tảng quản trị đa kho dữ liệu (Multi-Vault), tùy chỉnh quy tắc đặt tên linh hoạt và kết nối trực tiếp Chatbot AI / Agent chuẩn MCP — hỗ trợ **mọi thư mục cục bộ trên máy tính** (ổ cứng ngoài, NAS, thư mục đồng bộ OneDrive/iCloud/Google Drive Desktop) và **mọi thư mục / Shared Drive trên Google Drive**, phát triển tại **`kariusnocr/storage-management-suite`**.

---

## 1. Kiến trúc Gói Phần Mềm (`src/karius_academic_system/`)

Toàn bộ phần mềm được đóng gói chuẩn Python **`karius-academic-system`** (`v1.0.0`) với lệnh điều phối duy nhất **`kas`** (và ứng dụng giao diện **`kas ui`** / **`kas desktop`**):

| Phân hệ gói | Mô-đun chính | Lệnh `kas` | Vai trò |
| :--- | :--- | :--- | :--- |
| `core/` | `vaults`, `local_fs`, `config`, `naming`, `naming_rules`, `catalog_spec`, `drive_api`, `drive_cli`, `ocr` | `vault`, `rules`, `auth`, `version` | Sổ đăng ký đa kho (`~/.config/kas/vaults.toml`), `LocalFSBackend`, Google Drive API OAuth 2.0 & `gdrive` CLI, bộ máy **tùy chỉnh quy tắc đặt tên** (4 presets + tùy biến sâu), Chuẩn V6/V7, OCR `vie+eng` |
| `ai/` | `tools`, `mcp_server`, `bridge` | `ai`, `mcp` | **10 công cụ Agent chuẩn JSON Schema**, máy chủ **MCP (JSON-RPC 2.0)** qua stdio & HTTP `/api/mcp`, Chatbot AI tích hợp (Offline cục bộ, Ollama, OpenAI, Gemini, Claude) |
| `store/` | `sqlite_store`, `legacy_compat` | `db`, `undo` | Cơ sở dữ liệu SQLite riêng theo từng kho (`kas.db`, WAL + FTS5 tìm kiếm `<20 ms`) và Sổ cái Hoàn tác Hợp nhất |
| `ops/` | `indexer`, `auditor`, `normalizer`, `catalog_engine`, `dedup`, `reporter`, `transfer`, `ingestor`, `inspector`, `doctor`, `watcher` | `quet`, `kiem-tra`, `chuan-hoa`, `danh-muc`, `danh-muc-chuan`, `trung-lap`, `bao-cao`, `sao-chep-di-chuyen`, `nhap-du-lieu`, `tra-cuu`, `doctor`, `watch` | Quản trị kho đa nguồn, tự động áp dụng quy tắc đặt tên tùy chỉnh, tinh gọn danh mục V7, dọn rác `MACOSX` |
| `media/` | `file_reader`, `content_analyzer`, `image_analyzer`, `audio_analyzer`, `video_analyzer` | `doc-tep`, `phan-tich`, `phan-tich-anh`, `phan-tich-am-thanh`, `phan-tich-video` | Đọc đa định dạng, TF-IDF/SimHash, EXIF/dHash/pHash/OCR `vie+eng`, ID3/EBU R128 LUFS, Contact Sheet 3×2 |
| `sync/` | `drive_deploy`, `github_sync` | `trien-khai`, `github` | Xuất bản tài liệu + gói cài đặt lên `[03] QUẢN LÝ`, kiểm toán bảo mật, đồng bộ Git/GitHub |
| `cli/` & `web/` | `cli/main`, `cli/pipelines`, `web/app`, `web/desktop` | `quy-trinh-nhanh`, `bao-tri-dinh-ki`, `ui`, `desktop` | Pipeline in-process, Web Dashboard & Desktop App chuyển kho tức thì, Studio Quy Tắc Đặt Tên & Trợ Lý AI/MCP (tương thích Windows 11 Smart App Control) |

---

## 2. Quy trình Vận hành Chuẩn

```bash
# Kết nối kho bất kỳ & tùy chỉnh quy tắc đặt tên
kas vault add "Tài Liệu Học Tập" "D:\HocTap"
kas vault add "[A] STORAGE" "https://drive.google.com/drive/folders/<FOLDER_ID>"
kas rules presets                        # Chọn mẫu quy tắc hoặc tùy chỉnh bằng `kas rules set`

# Quét, kiểm toán & kết nối AI/Agent
kas doctor                               # Kiểm tra công cụ, sổ kho, OCR vie+eng, backend & SQLite
kas quet --tang-cuong                    # Quét tăng cường vào kas.db (FTS5)
kas kiem-tra                             # Kiểm toán theo quy tắc tùy chỉnh của kho
kas ai chat                              # Trò chuyện trực tiếp với Trợ Lý AI/Agent KAS
kas mcp config --client claude           # Xuất cấu hình MCP cho Claude Desktop / Cursor / Antigravity
kas desktop --browser --stdlib           # Mở ứng dụng Desktop Karius Academic System (KAS)
```
