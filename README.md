# Karius Academic System (KAS) `v1.0.0`

**Karius Academic System (KAS)** là phần mềm quản trị tri thức, **đa kho dữ liệu (Multi-Vault)**, **tùy chỉnh quy tắc đặt tên linh hoạt**, và **kết nối trực tiếp Chatbot AI / Agent (chuẩn MCP)** — mặc định hỗ trợ kết nối, lập chỉ mục **SQLite WAL + FTS5**, kiểm toán, chuẩn hóa **Chuẩn V6 / Danh Mục V7**, chống trùng lặp, đọc/OCR tiếng Việt và phân tích đa phương tiện trên **mọi kho dữ liệu bất kỳ**:

- **Thư mục cục bộ trên máy tính / Ổ cứng rời / NAS / Thư mục đồng bộ OneDrive · iCloud · Google Drive for Desktop** (`LocalFSBackend` — chạy 100% ngoại tuyến, không cần đăng nhập).
- **Mọi thư mục hoặc Shared Drive trên Google Drive** (`GoogleDriveAPIClient` OAuth 2.0 trên máy cá nhân & `GDriveCLIClient` trên cloud VM).

---

## 1. Tính năng Nổi bật ở `v1.0.0`

- **Đa kho thực thụ (Universal Multi-Vault)**:
  - Quản lý không giới hạn số lượng kho trong `~/.config/kas/vaults.toml` (`kas vault add|list|use|info|remove|init-structure`).
  - Dữ liệu chỉ mục (`kas.db`), báo cáo, quy tắc đặt tên và **Unified Undo Journal** được tách riêng tuyệt đối theo từng kho (`~/.local/share/kas/vaults/<slug>/`).
  - **Tự nhận diện thông minh (Auto-Detect)** giữa kho Chuẩn Học thuật KAS (`academic_v7`) và kho thư mục thông thường (`general`), chuyển kho tức thì trên thanh tiêu đề **Web & Desktop UI** hoặc bằng `kas --kho <slug> <lệnh>`.
- **Tùy chỉnh Thiết lập Quy tắc Đặt tên (`kas rules` & Tab *Quy Tắc Đặt Tên*)**:
  - 4 bộ mẫu chọn nhanh (**Chuẩn Học Thuật KAS V6**, **Gọn Sạch Phổ Thông**, **Kỹ Thuật `snake_case`**, **Xuất Bản `kebab-case`**) cùng tùy biến sâu: kiểu tiền tố số thư mục (`[01]`, `[001]`, `01.`, `01 -`, không tiền tố), kiểu chữ thư mục/tệp, dấu phân cách, độ dài tối đa, từ viết tắt giữ IN HOA, thư mục loại trừ, bảng thay thế chuỗi (`=>`) và Regex cấm.
  - **Bộ Thử Nghiệm Thời Gian Thực (Live Rule Simulator)** kiểm tra và đề xuất tên chuẩn ngay khi gõ; lưu riêng cho từng kho hoặc mặc định toàn cục.
- **Kết nối Chatbot AI & AI Agent (`kas ai` · `kas mcp` & Tab *Trợ Lý AI & Agent*)**:
  - **Máy chủ MCP (Model Context Protocol — JSON-RPC 2.0)** thuần Python (`kas mcp serve` qua `stdio` và HTTP `POST /api/mcp`), cung cấp **10 công cụ Agent an toàn**, tài nguyên (`kas://vaults`, `kas://active/stats`, `kas://active/naming-rules`) và prompt sẵn cho **Claude Desktop, Cursor, Windsurf, Antigravity, VS Code Copilot**.
  - **Trợ lý Chatbot AI tích hợp** hỗ trợ **Trợ Lý Cục Bộ KAS (100% ngoại tuyến, không cần API key)** cùng **OpenAI / Ollama (local) / LM Studio / OpenRouter / Groq / Google Gemini / Anthropic Claude** với vòng lặp gọi công cụ (Tool Calling) trực tiếp trên dữ liệu kho thật.
- **Chuẩn Đặt Tên & Tinh Gọn Thông Minh Danh Mục V7**:
  - Chống trùng tên tuyệt đối (Zero-Collision), duy nhất 1 dấu `" - "`, tinh gọn thông minh Phương án 2, bảo toàn 100% File ID và hoàn tác 1 lệnh qua `kas undo`.
- **An toàn 100% với Windows 11 Smart App Control**:
  - Máy chủ Web Dashboard thuần Python (`--stdlib`, không nạp `.pyd`/`.dll` ngoài) và cửa sổ Desktop độc lập **Microsoft Edge (`--app`)** đã ký số.
  - Gói **`kas-windows-sac-safe.zip`** tích hợp tệp cài 1 nhấp đúp **`Cai_Dat_KAS_Windows11.cmd`** (cài offline từ `.whl` đi kèm — **không cần tắt Smart App Control, không bao giờ gặp lỗi 404 khi kho GitHub ở chế độ Private**).

---

## 2. Cài đặt Nhanh

### Windows 11 có Smart App Control (Khuyến nghị — 1 nhấp đúp, không cần tắt bảo mật)
1. Tải **`kas-windows-sac-safe.zip`** từ **GitHub Releases `v1.0.0`** hoặc từ Google Drive `[A] STORAGE / [00] TỔNG QUAN / [03] QUẢN LÝ / [02] GÓI PHÁT HÀNH`.
2. Giải nén ra một thư mục (vd: `Downloads\kas-windows-sac-safe`).
3. **Nhấp đúp `Cai_Dat_KAS_Windows11.cmd`** *(tự động cài KAS `v1.0.0`, thêm lệnh `kas` vào PATH và tạo lối tắt Desktop **Karius Academic System (KAS)**)*.

> Nếu bạn dùng **PowerShell** với kho GitHub Private và máy đã đăng nhập GitHub CLI (`gh auth login`), có thể chạy 1 lệnh:
> ```powershell
> gh api repos/kariusnocr/storage-management-suite/contents/packaging/windows/install_windows_sac_safe.ps1 -H "Accept: application/vnd.github.raw" | iex
> ```

### Cài bằng Python (`pip`, Python 3.11+)
```bash
# Cài trọn bộ (CLI + Google Drive OAuth 2.0 + Media/OCR + Web UI + Desktop)
pip install -e ".[all]"

# Hoặc cài gọn thuần Python (CLI + Web UI --stdlib + AI/MCP + Google Drive OAuth 2.0):
pip install -e ".[drive-api]"
```

### Chạy bằng Docker
```bash
docker compose up --build -d
# Truy cập Karius Academic System tại http://127.0.0.1:8765
```

---

## 3. Bắt đầu Sử dụng trong 30 giây (`kas`)

```bash
# 1. Kết nối bất kỳ thư mục cục bộ hoặc Google Drive nào
kas vault add "Tài Liệu Cá Nhân" "D:\TaiLieu"
kas vault add "[A] STORAGE" "https://drive.google.com/drive/folders/<FOLDER_ID>"

# 2. Quét chỉ mục SQLite FTS5 & tìm kiếm tức thời (<20 ms)
kas quet
kas db search "triet hoc"

# 3. Tùy chỉnh quy tắc đặt tên cho kho hiện tại
kas rules presets
kas rules apply-preset snake_case_dev
kas rules set max_name_length 120
kas rules test "01_Bài Tập Cuối Kỳ.PDF"

# 4. Kết nối Chatbot AI & MCP Agent (Claude Desktop / Cursor / Antigravity / Ollama / Gemini)
kas ai ask "Thống kê tổng quan kho hiện tại và kiểm tra lỗi đặt tên"
kas ai config --provider gemini --model gemini-2.5-flash --api-key "<API_KEY>"
kas ai chat
kas mcp config --client claude    # In JSON mcpServers để dán vào Claude Desktop / Cursor / Antigravity

# 5. Mở ứng dụng Desktop / Web Dashboard
kas desktop --browser --stdlib
```

---

## 4. Kiến trúc Gói Mã nguồn (`src/karius_academic_system/`)

- `core/`: `vaults.py` (Multi-Vault Registry), `local_fs.py` (`LocalFSBackend`), `config.py` (ngữ cảnh đa kho động), `naming.py` (Chuẩn V6), `naming_rules.py` (bộ máy tùy chỉnh quy tắc đặt tên & 4 presets), `catalog_spec.py` (Chuẩn V7), `drive_api.py` (OAuth 2.0), `drive_cli.py`, `drive_factory.py`, `ocr.py` (`vie+eng`).
- `ai/`: `tools.py` (10 công cụ Agent chuẩn JSON Schema), `mcp_server.py` (máy chủ MCP JSON-RPC 2.0 qua stdio & HTTP `/api/mcp`), `bridge.py` (Chatbot AI đa nhà cung cấp: Offline cục bộ, OpenAI/Ollama/LM Studio, Gemini, Claude).
- `store/`: `sqlite_store.py` (SQLite WAL + FTS5 + Unified Undo Journal hỗ trợ cả Drive lẫn LocalFS).
- `ops/`: `indexer.py`, `auditor.py`, `normalizer.py`, `catalog_engine.py`, `dedup.py`, `reporter.py`, `transfer.py`, `ingestor.py`, `inspector.py`, `doctor.py`, `watcher.py`.
- `media/`: `file_reader.py`, `content_analyzer.py`, `image_analyzer.py`, `audio_analyzer.py`, `video_analyzer.py`.
- `sync/`: `drive_deploy.py`, `github_sync.py`.
- `cli/` & `web/`: `kas`, `kas-desktop`, Web Dashboard FastAPI + máy chủ thuần Python `--stdlib`.
