# Karius Academic System (KAS) `v1.5.1`

**Karius Academic System (KAS)** là phần mềm quản trị tri thức với **giao diện Desktop Workspace Shell thế hệ mới (*Obsidian Ink* & *Archival Paper*)**, **Bảng Lệnh toàn cục `Ctrl+K` (Command Palette)**, **đa kho dữ liệu (Multi-Vault)**, **tùy chỉnh quy tắc đặt tên linh hoạt**, **dòng lệnh tích hợp (Console)**, **tự động cập nhật phần mềm xác thực SHA-256 (`kas update`)**, **tự động cài đặt công cụ & thư viện (`kas setup`)**, **cơ chế gỡ cài đặt sạch sẽ chuẩn Windows (`kas uninstall`)**, **đăng nhập khóa phần mềm & kết nối bên thứ 3 (Google Drive OAuth 2.0, GitHub, AI, Webhook)** và **kết nối trực tiếp Chatbot AI / Agent (chuẩn MCP)** — hỗ trợ lập chỉ mục **SQLite WAL + FTS5**, kiểm toán, chuẩn hóa **Chuẩn V6 / Danh Mục V7**, chống trùng lặp, đọc/OCR tiếng Việt và phân tích đa phương tiện trên **mọi kho dữ liệu bất kỳ**:

- **Thư mục cục bộ trên máy tính / Ổ cứng rời / NAS / Thư mục đồng bộ OneDrive · iCloud · Google Drive for Desktop** (`LocalFSBackend` — chạy 100% ngoại tuyến, không cần đăng nhập).
- **Mọi thư mục hoặc Shared Drive trên Google Drive** (`GoogleDriveAPIClient` OAuth 2.0 đăng nhập ngay trong giao diện phần mềm & `GDriveCLIClient` trên cloud VM).

---

## 1. Tính năng Nổi bật (`v1.5.1`)

- **Giao Diện Desktop Workspace Shell & Hệ Thống Thiết Kế Mới (`v1.5.1`)**:
  - **Thanh điều hướng trái thu gọn linh hoạt (Collapsible Sidebar Rail · `Ctrl+B`)** phân 4 nhóm ngữ cảnh rõ ràng (*Kho Tri Thức*, *Quản trị & Chuẩn hóa*, *Trợ Lý & Công cụ*, *Hệ thống*) cùng bộ biểu tượng vector SVG nội tuyến (100% ngoại tuyến, 0 phụ thuộc CDN, tương thích tuyệt đối Windows 11 Smart App Control).
  - **Bảng Lệnh Toàn Cục (`Ctrl+K` — Command Palette)**: Tìm tệp tin trực tiếp qua SQLite FTS5, chuyển đổi kho, mở nhanh 12 màn hình chức năng, kích hoạt tác vụ nhanh hoặc chạy trực tiếp lệnh `kas ...` chỉ bằng bàn phím.
  - **Hai bảng màu học thuật tinh tế**: **Obsidian Ink (Tối mặc định)** và **Archival Paper (Sáng)**, đi kèm **thanh biểu đồ phân bố dung lượng nhánh**, **ngăn thông báo Toast** và **hộp thoại xác nhận tùy biến** thay thế hoàn toàn `alert()`/`confirm()`/`prompt()` cũ của trình duyệt.
  - **Kiến trúc Frontend tách mô-đun (`index.html` + `static/styles.css` + `static/app.js`)**: phục vụ an toàn qua cả máy chủ thuần Python (`--stdlib`) lẫn FastAPI với lớp chặn Path Traversal tuyệt đối và luôn mở cho màn hình Khóa Ứng Dụng (App Lock).
- **Cơ Chế Tự Động Cập Nhật Phần Mềm Xác Thực SHA-256 (`kas update` / `kas cap-nhat` & Trung Tâm Cập Nhật trong Tab *Cài Đặt*)**:
  - Tự động kiểm tra bản phát hành mới từ GitHub Releases ngay khi khởi động (chu kỳ đệm tùy chỉnh 1–168 giờ, hỗ trợ kênh **Ổn định / Thử nghiệm** & chế độ **Auto-Install**), hiển thị thanh thông báo đầu trang cùng nút **Cập nhật tự động ngay** / **Bỏ qua bản này**.
  - Tự tải gói `.whl`, **kiểm chứng toàn vẹn mật mã `SHA256SUMS.txt`** (tự hủy nếu sai băm), cài nâng cấp trực tiếp, đồng bộ số phiên bản trong *Windows Installed Apps*, tự khởi động lại máy chủ nền và tự tải lại cửa sổ ứng dụng sang phiên bản mới.
  - Lưu đầy đủ **Lịch sử cập nhật** và hỗ trợ **Quay về phiên bản trước (Rollback)** 1 bấm hoặc bằng `kas update --rollback`.
- **Cơ Chế Gỡ Cài Đặt Phần Mềm An Toàn & Chuẩn Hệ Điều Hành (`kas uninstall` / `kas go-cai-dat` & Tab *Cài Đặt*)**:
  - Hỗ trợ **4 cách gỡ sạch sẽ**: (1) trực tiếp trong **Windows Settings → Apps → Installed Apps** (đăng ký tự động không cần quyền Admin), (2) trong giao diện KAS **Tab Cài Đặt → Gỡ Cài Đặt Phần Mềm**, (3) nhấp đúp **`Go_Cai_Dat_KAS_Windows11.cmd`** / lối tắt Start Menu, hoặc (4) 1 lệnh PowerShell (`irm .../uninstall_windows_sac_safe.ps1 | iex`) / CLI `kas uninstall --thuc-thi`.
  - Tự dừng máy chủ nền, gỡ gói Python, xóa lối tắt Desktop/Start Menu, dọn `User PATH` & khóa Registry; tùy chọn giữ lại hoặc xóa sạch `~/.config/kas` & `~/.local/share/kas` — **bảo toàn 100% thư mục tài liệu của bạn và dữ liệu trên Google Drive**.
- **Tự Động Cài Đặt Công Cụ, Thư Viện & OCR Tiếng Việt (`kas setup` & Tab *Chẩn đoán*)**:
  - Tự động cài các thư viện Python khuyến nghị (`Pillow`, `numpy`, `fastapi`, `uvicorn`) kèm cơ chế bảo vệ chống lỗi **Smart App Control** (bắt `OSError`, tự dự phòng thuần Python `--stdlib`).
  - Tự động cài công cụ hệ thống còn thiếu qua `winget` (Windows) / `brew` (macOS): **GitHub CLI (`gh`)**, **Git (`git`)**, **7-Zip (`7z`)**, **FFmpeg / FFprobe**, **Tesseract OCR**, **Poppler (`pdftotext`, `pdfinfo`, `pdftoppm`)** và tự động làm mới + lưu vào `User PATH` Windows (không cần khởi động lại máy).
  - Tự động tải dữ liệu **OCR Tiếng Việt + Tiếng Anh** (`vie.traineddata` & `eng.traineddata`) vào `~/.local/share/kas/tessdata` (không cần quyền Admin).
  - `kas doctor` tự phân biệt rõ máy cá nhân (đang dùng **Google Drive API OAuth 2.0** nên không cần `gdrive` CLI của Cloud VM) và nhận diện cả **GitHub CLI** lẫn **GitHub PAT**.
- **Cài Đặt Phần Mềm Toàn Diện (`kas settings` & Tab *Cài Đặt*)**:
  - Tùy chỉnh Giao diện (**Tối / Sáng**), Ngôn ngữ (**Tiếng Việt / English**), Tab mặc định khi mở app, Cổng/Host Web Server, Backend mặc định (`auto / api / cli / local`), số luồng quét (`1–64`), chế độ Danh mục V7 (`smart / full`), thư mục dữ liệu tùy chỉnh (`data_dir_override`), kiểm tra cập nhật GitHub Releases trực tuyến, xuất/nhập cấu hình JSON và tắt nhanh máy chủ cục bộ.
- **Dòng Lệnh Tích Hợp (Tab *Dòng Lệnh (Console)* & Bảng Lệnh `Ctrl+K`)**:
  - Chạy trực tiếp mọi lệnh `kas ...` ngay trong giao diện ứng dụng Desktop/Web (tách tham số chuẩn Windows giữ nguyên đường dẫn như `E:\SÁCH`, hỗ trợ lịch sử phím `↑`/`↓`, chip lệnh nhanh 1 bấm, tự động chặn các lệnh lặp cửa sổ như `ui`/`desktop`, chạy bất đồng bộ có theo dõi thời gian thực).
- **Đăng Nhập Phần Mềm & Kết Nối Bên Thứ 3 (`kas account` & Tab *Tài Khoản & Kết Nối*)**:
  - **Tài khoản KAS cục bộ & Khóa Ứng Dụng (App Lock)**: Đăng ký/đăng nhập bảo vệ bằng băm **PBKDF2-HMAC-SHA256 (200.000 vòng + muối ngẫu nhiên)**, phiên cookie `HttpOnly; SameSite=Lax`, tự khóa toàn bộ `/api/*` khi bật yêu cầu đăng nhập.
  - **Google Drive OAuth 2.0 ngay trong UI**: Chọn hoặc dán tệp `credentials.json`, bấm **Đăng nhập Google bằng trình duyệt** 1 nút là quét được mọi kho Google Drive (như `[A] STORAGE`) mà không cần mở terminal.
  - **GitHub & Dịch vụ bên thứ 3**: Kết nối GitHub Personal Access Token (kiểm chứng trực tiếp qua GitHub API), xem nhanh trạng thái nhà cung cấp AI và thêm các **Custom Connectors** (Webhook / n8n / Make / Nextcloud WebDAV / S3 / REST API).
- **Đa kho thực thụ (Universal Multi-Vault)**:
  - Quản lý không giới hạn số lượng kho trong `~/.config/kas/vaults.toml` (`kas vault add|list|use|info|remove|init-structure`), dữ liệu SQLite `kas.db` và **Unified Undo Journal** tách riêng theo từng kho.
- **Tùy chỉnh Quy tắc Đặt tên (`kas rules` & Tab *Quy Tắc Đặt Tên*)**:
  - 4 bộ mẫu chọn nhanh (**Chuẩn Học Thuật KAS V6**, **Gọn Sạch Phổ Thông**, **Kỹ Thuật `snake_case`**, **Xuất Bản `kebab-case`**) + **Bộ Thử Nghiệm Thời Gian Thực (Live Rule Simulator)**.
- **Kết nối Chatbot AI & AI Agent (`kas ai` · `kas mcp` & Tab *Trợ Lý AI & Agent*)**:
  - **Máy chủ MCP (Model Context Protocol — JSON-RPC 2.0)** thuần Python (`kas mcp serve` qua `stdio` & HTTP `POST /api/mcp`) cung cấp **10 công cụ Agent an toàn** cho **Claude Desktop, Cursor, Windsurf, Antigravity**.
  - **Trợ lý Chatbot AI tích hợp**: **Trợ Lý Cục Bộ KAS (100% ngoại tuyến)** cùng **OpenAI / Ollama / LM Studio / OpenRouter / Groq / Google Gemini / Anthropic Claude**.
- **An toàn 100% với Windows 11 Smart App Control**:
  - Máy chủ thuần Python (`--stdlib`) + cửa sổ Desktop độc lập **Microsoft Edge (`--app`)** đã ký số + kịch bản PowerShell 5.1 / `.cmd` chuẩn **100% 7-bit ASCII + CRLF**.

---

## 2. Cài đặt, Cập nhật & Gỡ cài đặt Nhanh

### Windows 11 có Smart App Control (Khuyến nghị — 1 lệnh PowerShell hoặc 1 nhấp đúp)

**Cài mới hoặc cập nhật lên `v1.5.1` (1 lệnh PowerShell — tự cài toàn bộ công cụ & OCR Tiếng Việt):**
```powershell
irm https://raw.githubusercontent.com/kariusnocr/storage-management-suite/main/packaging/windows/install_windows_sac_safe.ps1 | iex
```

**Hoặc cập nhật tự động (nếu máy đang cài KAS `v1.4.0+`):**
- Bấm nút **Cập nhật tự động ngay** ngay trên ứng dụng KAS, hoặc chạy `kas update`.

**Gỡ cài đặt an toàn (1 lệnh PowerShell — hoặc mở Windows Settings → Apps → Installed Apps / Tab Cài Đặt):**
```powershell
irm https://raw.githubusercontent.com/kariusnocr/storage-management-suite/main/packaging/windows/uninstall_windows_sac_safe.ps1 | iex
```

**Hoặc tải ZIP cài/gỡ offline 1 nhấp đúp:**
1. Tải **`kas-windows-sac-safe.zip`** từ **GitHub Releases `v1.5.1`** hoặc Google Drive `[A] STORAGE / [00] TỔNG QUAN / [03] QUẢN LÝ / [02] GÓI PHÁT HÀNH`.
2. Giải nén và nhấp đúp **`Cai_Dat_KAS_Windows11.cmd`** (để cài) hoặc **`Go_Cai_Dat_KAS_Windows11.cmd`** (để gỡ).

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
kas vault add "Tài Liệu Cá Nhân" "E:\SÁCH"
kas vault add "[A] STORAGE" "https://drive.google.com/drive/folders/<FOLDER_ID>"

# 2. Quét chỉ mục SQLite FTS5 & tìm kiếm tức thời (<20 ms)
kas quet
kas db search "triet hoc"

# 3. Cài đặt phần mềm & tài khoản / kết nối
kas settings show
kas settings set theme light
kas settings check-update
kas account register admin --password "<mat-khau>" --require-login
kas account status

# 4. Tùy chỉnh quy tắc đặt tên & kết nối AI / MCP Agent
kas rules apply-preset general_clean
kas ai ask "Thống kê tổng quan kho hiện tại và kiểm tra lỗi đặt tên"
kas mcp config --client claude

# 5. Mở ứng dụng Desktop / Web Dashboard (nhấn Ctrl+K để mở nhanh Dòng Lệnh)
kas desktop --browser --stdlib
```

---

## 4. Kiến trúc Gói Mã nguồn (`src/karius_academic_system/`)

- `core/`: `vaults.py` (Multi-Vault Registry), `local_fs.py` (`LocalFSBackend`), `config.py`, `settings.py` (Cài đặt phần mềm & Kiểm tra cập nhật), `accounts.py` (Tài khoản cục bộ PBKDF2 / App Lock & Kết nối Google Drive OAuth / GitHub PAT / Custom Connectors), `naming.py` (Chuẩn V6), `naming_rules.py` (Quy tắc tùy chỉnh), `catalog_spec.py` (Chuẩn V7), `drive_api.py` (OAuth 2.0), `drive_cli.py`, `drive_factory.py`, `ocr.py` (`vie+eng`).
- `ai/`: `tools.py` (10 công cụ Agent JSON Schema), `mcp_server.py` (MCP JSON-RPC 2.0), `bridge.py` (Chatbot AI đa nhà cung cấp).
- `store/`: `sqlite_store.py` (SQLite WAL + FTS5 + Unified Undo Journal).
- `ops/`: `indexer.py`, `auditor.py`, `normalizer.py`, `catalog_engine.py`, `dedup.py`, `reporter.py`, `transfer.py`, `ingestor.py`, `inspector.py`, `doctor.py`, `watcher.py`.
- `media/`: `file_reader.py`, `content_analyzer.py`, `image_analyzer.py`, `audio_analyzer.py`, `video_analyzer.py`.
- `sync/`: `drive_deploy.py`, `github_sync.py`.
- `cli/` & `web/`: `cli/main.py`, `cli/console.py` (Dòng lệnh tích hợp), `cli/pipelines.py`, `web/app.py` (FastAPI + `--stdlib` HTTP Server + App Lock Guard), `web/desktop.py`.
