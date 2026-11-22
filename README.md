# Karius Academic System (KAS) `v1.7.0`

**Karius Academic System (KAS)** là phần mềm quản trị tri thức đa nền tảng (**Windows · macOS · Linux · Android**) với **Ứng dụng Android Gốc (`kas-android.apk`) nhúng Python 3.11 + SQLite chạy độc lập trên điện thoại/máy tính bảng**, **Trình Duyệt Kho & Xem Trước Tệp trực tiếp (Vault Explorer & Previewer)**, **giao diện Desktop Workspace & Mobile Touch Shell (*Obsidian Ink* & *Archival Paper*)**, **Bảng Lệnh toàn cục `Ctrl+K` (Command Palette)**, **đa kho dữ liệu (Multi-Vault)**, **tùy chỉnh quy tắc đặt tên linh hoạt**, **dòng lệnh tích hợp (Console)**, **tự động cập nhật phần mềm xác thực SHA-256 (`kas update`)**, **tự động cài đặt công cụ & thư viện (`kas setup`)**, **cơ chế gỡ cài đặt sạch sẽ chuẩn Windows (`kas uninstall`)**, **đăng nhập khóa phần mềm & kết nối bên thứ 3 (Google Drive OAuth 2.0, GitHub, AI, Webhook)** và **kết nối trực tiếp Chatbot AI / Agent (chuẩn MCP)** — hỗ trợ lập chỉ mục **SQLite WAL + FTS5**, kiểm toán, chuẩn hóa **Chuẩn V6 / Danh Mục V7**, chống trùng lặp, đọc/OCR tiếng Việt và phân tích đa phương tiện trên **mọi kho dữ liệu bất kỳ**:

- **Thư mục cục bộ trên máy tính / Điện thoại & Máy tính bảng Android / Ổ cứng rời / NAS / Thư mục đồng bộ OneDrive · iCloud · Google Drive for Desktop** (`LocalFSBackend` — chạy 100% ngoại tuyến, không cần đăng nhập).
- **Mọi thư mục hoặc Shared Drive trên Google Drive** (`GoogleDriveAPIClient` OAuth 2.0 đăng nhập ngay trong giao diện phần mềm & `GDriveCLIClient` trên cloud VM).

---

## 1. Tính năng Nổi bật (`v1.7.0`)

- **Hệ Sinh Thái KAS Trên Hệ Điều Hành Android (`kas-android.apk` · `kas android` · Termux · PWA — MỚI `v1.7.0`)**:
  - **Ứng dụng Android Gốc (`kas-android.apk` · Android 8.0+ / API 26–35)**: Nhúng trực tiếp môi trường **Python 3.11 + SQLite + toàn bộ lõi `karius_academic_system`** bên trong tệp APK qua **Chaquopy** (`arm64-v8a` & `x86_64`), tự tạo sẵn **Kho Tài Liệu Android** trên bộ nhớ thiết bị và chạy độc lập 100% ngoại tuyến mà không cần máy tính.
  - **Chế độ Kép (On-Device & Ghép nối PC qua Wi-Fi/LAN)**: Chuyển đổi 1 chạm ngay trong ứng dụng Android giữa **Máy chủ Nội bộ trên điện thoại (`127.0.0.1`)** và **Máy chủ KAS trên máy tính qua mạng Wi-Fi (`http://192.168.x.x:8765`)**, hỗ trợ nút Back vật lý / vuốt cạnh Android để lùi thư mục trong *Duyệt Kho*, chọn tệp gốc Android (`credentials.json`) và tải tệp trực tiếp về `Downloads`.
  - **Giao diện Cảm ứng Di động & Progressive Web App (PWA)**: Thanh Điều Hướng Đáy (**Mobile Bottom Navigation Bar**: *Tổng quan, Duyệt Kho, Tìm kiếm, Trợ Lý AI, Menu*), chạm 1 lần mở thư mục trong *Duyệt Kho*, và hỗ trợ cài đặt PWA toàn màn hình (`manifest.webmanifest`, `sw.js`).
  - **Trình cài đặt 1 lệnh cho Android Termux (`install_android_termux.sh`) & CLI `kas android`**: Tự cài đặt Python, Git, OCR Tiếng Việt (`tesseract` + `vie.traineddata`), `ffmpeg`, `7z`, `poppler`, tạo lối tắt *Termux:Widget* và cung cấp lệnh `kas android info|init-vault|serve`.
- **Cơ Chế Di Chuyển Giữa Các Thư Mục/Tệp & Xem Trước Trực Tiếp (`Duyệt Kho` & `kas duyet` · `v1.6.0+`)**:
  - **Không gian duyệt 3 khung chuyên nghiệp**: **Cây thư mục mở rộng lười (Lazy Folder Tree)** bên trái, **Danh sách / Lưới thẻ** ở giữa (chuyển đổi 1 bấm, lưu lựa chọn), và **Khung Xem Trước (Preview Inspector)** dính bên phải.
  - **Điều hướng nhanh chuẩn ứng dụng Desktop**: Thanh đường dẫn **Breadcrumb** nhấp nhảy cấp tức thì, lịch sử **Lùi (`Alt+←`) / Tiến (`Alt+→`) / Lên thư mục cha (`Backspace` / `Alt+↑`)**, di chuyển bằng bàn phím (**`↑`/`↓` chọn**, **`Enter` mở thư mục/tệp**), lọc không dấu tức thời trong thư mục và sắp xếp theo *Tên / Dung lượng / Ngày cập nhật / Loại tệp*.
  - **Xem trước trực tiếp đa định dạng ngay trong ứng dụng**: Ảnh (`PNG/JPG/WebP/SVG`), **PDF** (khung nhúng + trích xuất mục lục/văn bản), **Âm thanh & Video** (hỗ trợ phát tua mượt qua HTTP `206 Partial Content Range`), **Văn bản & Mã nguồn**, **DOCX / XLSX / PPTX / EPUB / ZIP** (trích xuất văn bản, mục lục, siêu dữ liệu), và nút **Mở ứng dụng ngoài / Hiện trong File Explorer** (kho cục bộ) hoặc **Tải & xem nội dung / Mở trên Google Drive** (kho Google Drive).
  - **Liên thông toàn hệ thống**: Bấm trực tiếp vào nhánh trong *Tổng quan*, bấm **Duyệt vị trí** từ kết quả *Tìm kiếm FTS5* hoặc chọn tệp trong *Bảng Lệnh `Ctrl+K`* để nhảy thẳng đến thư mục chứa và tự động mở bản xem trước tệp đó.
  - **An toàn tuyệt đối**: Chặn path traversal / symlink escape 2 lớp, vô hiệu hóa XSS với tệp HTML/JS/SVG tải xem từ kho cục bộ, và bảo vệ toàn bộ `/api/explorer/*` dưới lớp Khóa Ứng Dụng (App Lock).
- **Giao Diện Desktop Workspace Shell & Hệ Thống Thiết Kế Mới (`v1.5.0+`)**:
  - **Thanh điều hướng trái thu gọn linh hoạt (Collapsible Sidebar Rail · `Ctrl+B`)** phân 4 nhóm ngữ cảnh rõ ràng (*Kho Tri Thức*, *Quản trị & Chuẩn hóa*, *Trợ Lý & Công cụ*, *Hệ thống*) cùng bộ biểu tượng vector SVG nội tuyến (100% ngoại tuyến, 0 phụ thuộc CDN, tương thích tuyệt đối Windows 11 Smart App Control).
  - **Bảng Lệnh Toàn Cục (`Ctrl+K` — Command Palette)**: Tìm tệp tin trực tiếp qua SQLite FTS5, chuyển đổi kho, mở nhanh 13 màn hình chức năng, kích hoạt tác vụ nhanh hoặc chạy trực tiếp lệnh `kas ...` chỉ bằng bàn phím.
  - **Hai bảng màu học thuật tinh tế**: **Obsidian Ink (Tối mặc định)** và **Archival Paper (Sáng)**, đi kèm **thanh biểu đồ phân bố dung lượng nhánh**, **ngăn thông báo Toast** và **hộp thoại xác nhận tùy biến** thay thế hoàn toàn `alert()`/`confirm()`/`prompt()` cũ của trình duyệt.
  - **Kiến trúc Frontend tách mô-đun (`index.html` + `static/styles.css` + `static/app.js`)**: phục vụ an toàn qua cả máy chủ thuần Python (`--stdlib`) lẫn FastAPI với lớp chặn Path Traversal tuyệt đối và luôn mở cho màn hình Khóa Ứng Dụng (App Lock).
- **Cơ Chế Tự Động Cập Nhật Phần Mềm Xác Thực SHA-256 (`kas update` / `kas cap-nhat` & Trung Tâm Cập Nhật trong Tab *Cài Đặt*)**:
  - Tự động kiểm tra bản phát hành mới từ GitHub Releases ngay khi khởi động (chu kỳ đệm tùy chỉnh 1–168 giờ, hỗ trợ kênh **Ổn định / Thử nghiệm** & chế độ **Auto-Install**), hiển thị thanh thông báo đầu trang cùng nút **Cập nhật tự động ngay** / **Bỏ qua bản này**.
  - Tự tải gói `.whl`, **kiểm chứng toàn vẹn mật mã `SHA256SUMS.txt`** (tự hủy nếu sai băm), cài nâng cấp trực tiếp, đồng bộ số phiên bản trong *Windows Installed Apps*, tự đóng/khởi động lại máy chủ nền và tự tải lại cửa sổ ứng dụng sang phiên bản mới.
  - Lưu đầy đủ **Lịch sử cập nhật** và hỗ trợ **Quay về phiên bản trước (Rollback)** 1 bấm hoặc bằng `kas update --rollback`.
- **Cơ Chế Gỡ Cài Đặt Phần Mềm An Toàn & Chuẩn Hệ Điều Hành (`kas uninstall` / `kas go-cai-dat` & Tab *Cài Đặt*)**:
  - Hỗ trợ **4 cách gỡ sạch sẽ**: (1) trực tiếp trong **Windows Settings → Apps → Installed Apps** (đăng ký tự động không cần quyền Admin), (2) trong giao diện KAS **Tab Cài Đặt → Gỡ Cài Đặt Phần Mềm**, (3) nhấp đúp **`Go_Cai_Dat_KAS_Windows11.cmd`** / lối tắt Start Menu, hoặc (4) 1 lệnh PowerShell (`irm .../uninstall_windows_sac_safe.ps1 | iex`) / CLI `kas uninstall --thuc-thi`.
  - Tự dừng máy chủ nền & đóng cửa sổ ứng dụng, gỡ gói Python, xóa lối tắt Desktop/Start Menu, dọn `User PATH` & khóa Registry; tùy chọn giữ lại hoặc xóa sạch `~/.config/kas` & `~/.local/share/kas` — **bảo toàn 100% thư mục tài liệu của bạn và dữ liệu trên Google Drive**.
- **Tự Động Cài Đặt Công Cụ, Thư Viện & OCR Tiếng Việt (`kas setup` & Tab *Chẩn đoán*)**:
  - Tự động cài các thư viện Python khuyến nghị (`Pillow`, `numpy`, `fastapi`, `uvicorn`) kèm cơ chế bảo vệ chống lỗi **Smart App Control** (bắt `OSError`, tự dự phòng thuần Python `--stdlib`).
  - Tự động cài công cụ hệ thống còn thiếu qua `winget` (Windows) / `brew` (macOS): **GitHub CLI (`gh`)**, **Git (`git`)**, **7-Zip (`7z`)**, **FFmpeg / FFprobe**, **Tesseract OCR**, **Poppler (`pdftotext`, `pdfinfo`, `pdftoppm`)** và tự động làm mới + lưu vào `User PATH` Windows (không cần khởi động lại máy).
  - Tự động tải dữ liệu **OCR Tiếng Việt + Tiếng Anh** (`vie.traineddata` & `eng.traineddata`) vào `~/.local/share/kas/tessdata` (không cần quyền Admin).
  - `kas doctor` tự phân biệt rõ máy cá nhân (đang dùng **Google Drive API OAuth 2.0** nên không cần `gdrive` CLI của Cloud VM) và nhận diện cả **GitHub CLI** lẫn **GitHub PAT**.
- **Cài Đặt Phần Mềm Toàn Diện (`kas settings` & Tab *Cài Đặt*)**:
  - Tùy chỉnh Giao diện (**Tối / Sáng**), Ngôn ngữ (**Tiếng Việt / English**), Tab mặc định khi mở app (gồm cả `explorer`), Cổng/Host Web Server, Backend mặc định (`auto / api / cli / local`), số luồng quét (`1–64`), chế độ Danh mục V7 (`smart / full`), thư mục dữ liệu tùy chỉnh (`data_dir_override`), kiểm tra cập nhật GitHub Releases trực tuyến, xuất/nhập cấu hình JSON và tắt nhanh máy chủ cục bộ.
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

### Điện thoại & Máy tính bảng Android (Android 8.0+ — 3 cách cài đặt)

1. **Cài Ứng dụng Android Gốc (`kas-android.apk` — Chạy độc lập 100% trên điện thoại)**:
   - Tải **`kas-android.apk`** từ **GitHub Releases `v1.7.0`** hoặc từ Google Drive `[A] STORAGE / [00] TỔNG QUAN / [03] QUẢN LÝ / [02] GÓI PHÁT HÀNH / kas-android.apk` và chạm để cài đặt.
2. **Cài trọn bộ CLI + OCR Tiếng Việt trên Android Termux (1 lệnh)**:
   ```bash
   curl -fsSL https://raw.githubusercontent.com/kariusnocr/storage-management-suite/main/packaging/android/install_android_termux.sh | bash
   ```
3. **Ghép nối với Máy chủ KAS trên Máy tính qua Wi-Fi / LAN (hoặc cài PWA)**:
   - Trên máy tính chạy `kas android serve --port 8765`, sau đó mở địa chỉ `http://<IP-LAN>:8765` trên điện thoại Android (trong ứng dụng `kas-android.apk` hoặc Chrome Android → *Thêm vào màn hình chính*).

### Windows 11 có Smart App Control (Khuyến nghị — 1 lệnh PowerShell hoặc 1 nhấp đúp)

**Cài mới hoặc cập nhật lên `v1.7.0` (1 lệnh PowerShell — tự cài toàn bộ công cụ & OCR Tiếng Việt):**
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
1. Tải **`kas-windows-sac-safe.zip`** từ **GitHub Releases `v1.7.0`** hoặc Google Drive `[A] STORAGE / [00] TỔNG QUAN / [03] QUẢN LÝ / [02] GÓI PHÁT HÀNH`.
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
