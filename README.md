# KAS — Karius Academic System

[![Version](https://img.shields.io/badge/release-v1.9.0-0ea5e9?style=flat-square)](https://github.com/kariusnocr/storage-management-suite/releases/latest)
[![Platforms](https://img.shields.io/badge/platforms-Windows%20%7C%20Linux%20%7C%20Android-10b981?style=flat-square)](#nền-tảng-hỗ-trợ)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776ab?style=flat-square)](pyproject.toml)
[![CI](https://github.com/kariusnocr/storage-management-suite/actions/workflows/ci.yml/badge.svg)](https://github.com/kariusnocr/storage-management-suite/actions/workflows/ci.yml)

Phần mềm quản trị tri thức & đa kho dữ liệu (**Local FS** + **Google Drive**) dành riêng cho **Windows, Linux và Android** — tích hợp duyệt/xem trước tệp trực tiếp, tìm kiếm toàn văn **SQLite FTS5** (`<20 ms`), chuẩn hóa quy ước đặt tên, **OCR tiếng Việt**, **Chatbot AI / MCP Server**, tự động cập nhật xác thực **SHA-256** và nhật kí chẩn đoán lỗi.

---

## Nền tảng hỗ trợ

| Nền tảng | Hình thức cài đặt | Gói phát hành |
| :--- | :--- | :--- |
| **Windows 10 / 11** *(an toàn Smart App Control)* | 1 lệnh PowerShell hoặc nhấp đúp `.cmd` | [`kas-windows-sac-safe.zip`](https://github.com/kariusnocr/storage-management-suite/releases/latest) · [`kas-windows-x64.exe`](https://github.com/kariusnocr/storage-management-suite/releases/latest) |
| **Linux** *(x86_64 / Docker)* | Binary độc lập, `pip` hoặc Docker Compose | [`kas-linux-x64`](https://github.com/kariusnocr/storage-management-suite/releases/latest) · `.whl` |
| **Android 8.0+** *(API 26–35)* | Ứng dụng gốc độc lập (Python 3.11 nhúng) hoặc Termux | [`kas-android.apk`](https://github.com/kariusnocr/storage-management-suite/releases/latest/download/kas-android.apk) |

> **Phạm vi hỗ trợ**: KAS tập trung phát triển và kiểm thử chính thức trên **Windows, Linux và Android**.

---

## Tính năng chính

| Nhóm | Khả năng cốt lõi |
| :--- | :--- |
| **Đa kho dữ liệu (Multi-Vault)** | Quản lý song song mọi thư mục cục bộ (PC, điện thoại Android, ổ rời, NAS, OneDrive) và mọi thư mục / Shared Drive trên Google Drive (OAuth 2.0 ngay trong UI). |
| **Duyệt Kho & Xem Trước (`kas duyet`)** | Cây thư mục 3 khung (Desktop) / Drawer & Bottom Sheet Material 3 (Android), xem trực tiếp ảnh, PDF, audio/video (`HTTP 206`), văn bản, mã nguồn, DOCX/XLSX/PPTX/EPUB/ZIP. |
| **Tìm kiếm & Chuẩn hóa V6/V7** | Chỉ mục SQLite WAL + FTS5 tiếng Việt có/không dấu (`<20 ms`), 4 bộ mẫu quy tắc đặt tên tùy chỉnh + Live Simulator, kiểm toán, chống trùng lặp, dọn rác hệ thống & hoàn tác 1 bước (**Undo Journal**). |
| **AI Chatbot & MCP Agent** | Máy chủ **MCP (JSON-RPC 2.0)** với 10 công cụ cho Claude Desktop, Cursor, Antigravity; Chatbot AI hỗ trợ chế độ cục bộ ngoại tuyến, Ollama, OpenAI, Gemini, Claude. |
| **Android Gốc & Ghép nối PC Wi-Fi** | Ứng dụng tên gọn **`KAS`**, ký số phát hành cố định (`SHA-1`), tự cập nhật APK xác thực `SHA-256`, bật/tắt chia sẻ Wi-Fi LAN 1 chạm trên PC và tự khám phá PC cùng mạng qua UDP (`8766`). |
| **Tự cài công cụ, Cập nhật & Gỡ sạch** | `kas setup` tự cài công cụ CLI & dữ liệu OCR tiếng Việt (`vie+eng`); `kas update` tự tải, xác thực `SHA256SUMS.txt`, tự khởi động lại & Rollback; `kas uninstall` gỡ sạch (bảo toàn 100% tài liệu). |
| **Bảo mật & Nhật kí chẩn đoán (`kas logs`)** | Khóa ứng dụng PBKDF2-HMAC-SHA256 (200.000 vòng), kết nối GitHub/Webhook; nhật kí báo lỗi xoay vòng tự ẩn bí mật, xuất tệp `.TXT` / `.JSON` (tự chia sẻ trên Android). |

---

## Cài đặt nhanh

### Windows 11 (Khuyến nghị — an toàn Smart App Control)
Mở PowerShell và chạy 1 lệnh (tự cài KAS, công cụ CLI, OCR tiếng Việt và tạo lối tắt **`KAS`** trên Desktop):
```powershell
irm https://raw.githubusercontent.com/kariusnocr/storage-management-suite/main/packaging/windows/install_windows_sac_safe.ps1 | iex
```
- **Cài offline**: Tải [`kas-windows-sac-safe.zip`](https://github.com/kariusnocr/storage-management-suite/releases/latest) → giải nén → nhấp đúp **`Cai_Dat_KAS_Windows11.cmd`**.
- **Cập nhật** *(từ `v1.4.0+`)*: Bấm **Cập nhật tự động ngay** trong ứng dụng hoặc chạy `kas update`.
- **Gỡ cài đặt**: Qua *Windows Settings → Apps → Installed Apps*, tab *Cài Đặt* hoặc:
  ```powershell
  irm https://raw.githubusercontent.com/kariusnocr/storage-management-suite/main/packaging/windows/uninstall_windows_sac_safe.ps1 | iex
  ```

### Android (Điện thoại & Máy tính bảng)
1. **Ứng dụng gốc (`KAS`)**: Tải [`kas-android.apk`](https://github.com/kariusnocr/storage-management-suite/releases/latest/download/kas-android.apk) và chạm để cài đặt.
   *(Nếu nâng cấp từ bản `<= v1.8.0`, hãy gỡ bản cũ 1 lần để chuyển sang chứng chỉ ký số cố định; từ `v1.9.0+` mọi bản cập nhật đều nâng cấp tại chỗ.)*
2. **Android Termux (1 lệnh)**:
   ```bash
   curl -fsSL https://raw.githubusercontent.com/kariusnocr/storage-management-suite/main/packaging/android/install_android_termux.sh | bash
   ```

### Linux & Docker
```bash
# Cài từ mã nguồn (Python 3.11+)
pip install -e ".[all]"

# Hoặc chạy bằng Docker Compose (truy cập http://127.0.0.1:8765)
docker compose up --build -d
```
Hoặc tải trực tiếp binary [`kas-linux-x64`](https://github.com/kariusnocr/storage-management-suite/releases/latest) đã kiểm chứng `SHA256SUMS.txt`.

---

## Bắt đầu nhanh (`kas`)

```bash
# Kết nối kho cục bộ hoặc Google Drive bất kỳ
kas vault add "Tài Liệu" "E:\SÁCH"
kas vault add "Kho Drive" "https://drive.google.com/drive/folders/<FOLDER_ID>"

# Quét chỉ mục, duyệt thư mục & tìm kiếm tức thì
kas quet
kas duyet
kas db search "triet hoc"

# Mở ứng dụng giao diện & ghép nối điện thoại Android qua Wi-Fi
kas desktop --browser --stdlib
kas android serve --port 8765

# Trợ lý AI, MCP Server, nhật kí lỗi & cập nhật
kas ai ask "Thống kê kho và kiểm tra lỗi đặt tên"
kas mcp config --client claude
kas logs export --format txt
kas update
```

---

## Chứng chỉ Android cố định (`io.github.kariusnocr.kas`)

Dùng để đăng ký OAuth trên **Google Auth Platform** và xác minh tính toàn vẹn của `kas-android.apk`:

- **SHA-1**: `FF:D4:BA:CE:3C:48:C1:53:AF:BC:44:B3:AD:FE:6D:5C:31:8B:61:BC`
- **SHA-256**: `EC:65:9D:B8:08:53:33:6C:CE:BA:66:46:F2:3F:19:21:D6:2F:12:D3:DB:8B:6C:08:BE:7F:1F:51:14:1E:A0:96`

---

## Cấu trúc dự án & Tài liệu

```text
src/karius_academic_system/
├── core/        # Đa kho, LocalFS, Google Drive OAuth, Cài đặt, Tài khoản, Quy tắc tên, Nhật kí lỗi
├── store/       # SQLite WAL + FTS5 & Unified Undo Journal
├── ops/         # Duyệt kho, Quét chỉ mục, Kiểm toán, Chuẩn hóa, V7, Trùng lặp, Setup, Update, Uninstall
├── media/       # Đọc đa định dạng, phân tích nội dung, ảnh/OCR, âm thanh, video
├── ai/          # 10 công cụ Agent, MCP Server (JSON-RPC 2.0) & Chatbot AI
├── web/         # Máy chủ Web (FastAPI / stdlib), Desktop Shell, Cầu nối Android & Giao diện tĩnh
├── cli/         # Điểm vào CLI `kas` & Trình nhập lệnh tích hợp (Console)
└── sync/        # Đồng bộ Google Drive & kiểm toán bảo mật GitHub
packaging/       # Bộ cài Windows SAC-safe, dự án Android Gradle/Chaquopy & PyInstaller (Windows/Linux)
tests/           # Bộ kiểm thử tự động ngoại tuyến (90+ kiểm thử)
docs/            # Hướng dẫn cài đặt, tổng quan kiến trúc & quy ước Danh Mục V7
```

- [Hướng dẫn cài đặt & sử dụng chi tiết](docs/H%C6%B0%E1%BB%9Bng%20D%E1%BA%ABn%20C%C3%A0i%20%C4%90%E1%BA%B7t%20Ph%E1%BA%A7n%20M%E1%BB%81m%20-%20Storage.md)
- [Tổng quan kiến trúc hệ thống](docs/T%E1%BB%95ng%20Quan%20H%E1%BB%87%20Th%E1%BB%91ng%20-%20Qu%E1%BA%A3n%20L%C3%BD.md)
- [Quy ước Danh Mục V7](docs/T%E1%BB%95ng%20Quan%20H%E1%BB%87%20Th%E1%BB%91ng%20-%20Quy%20%C6%AF%E1%BB%9Bc%20Danh%20M%E1%BB%A5c%20V7.md)
- [Tải bản phát hành mới nhất (GitHub Releases)](https://github.com/kariusnocr/storage-management-suite/releases/latest)
