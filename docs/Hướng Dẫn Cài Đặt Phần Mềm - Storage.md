# HƯỚNG DẪN CÀI ĐẶT & SỬ DỤNG — KARIUS ACADEMIC SYSTEM (KAS `v1.1.0`)

## 1. Chọn Phương thức Cài đặt & Cập nhật

### Cách A (Khuyến nghị trên Windows 11 có Smart App Control) — 1 lệnh PowerShell hoặc 1 nhấp đúp, không cần tắt bảo mật

> [!IMPORTANT]
> **Windows 11 Smart App Control (SAC)** chặn các tệp `.exe` chưa ký số thương mại và không có nút *Run anyway*. Bạn **KHÔNG cần tắt Smart App Control** — bộ cài KAS dùng Python chính chủ + máy chủ thuần chuẩn (`--stdlib`) + cửa sổ **Microsoft Edge (`--app`)** đã ký số bởi Microsoft.

**Cách A1 — 1 lệnh PowerShell (Nhanh nhất — cài mới hoặc cập nhật lên `v1.1.0`):**
Mở **PowerShell** và dán 1 dòng duy nhất:
```powershell
irm https://raw.githubusercontent.com/kariusnocr/storage-management-suite/main/packaging/windows/install_windows_sac_safe.ps1 | iex
```

**Cách A2 — Tải ZIP & Nhấp đúp (Hoạt động cả khi không có Internet):**
1. Tải tệp **`kas-windows-sac-safe.zip`** từ **GitHub Releases `v1.1.0`** hoặc từ Google Drive:
   `[A] STORAGE / [00] TỔNG QUAN / [03] QUẢN LÝ / [02] GÓI PHÁT HÀNH / kas-windows-sac-safe.zip`.
2. Giải nén toàn bộ vào một thư mục (ví dụ: `Downloads\kas-windows-sac-safe`).
3. **Nhấp đúp `Cai_Dat_KAS_Windows11.cmd`** ngay trong thư mục vừa giải nén.
4. Sau khi xong, nhấp đúp biểu tượng **Karius Academic System (KAS)** trên Desktop!

### Cách B — Tải Binary Độc lập (macOS / Linux / Windows không bật SAC)
1. Tải tệp từ **GitHub Releases `v1.1.0`** (`kas-windows-x64.exe`, `kas-macos-arm64`, `kas-linux-x64`).
2. Kiểm tra mã băm trong `SHA256SUMS.txt`.
3. Chạy `kas doctor` hoặc `kas desktop`.

### Cách C — Cài bằng `pip` (Python 3.11+)
```bash
pip install -e ".[all]"
# Hoặc cài gọn thuần Python:
pip install -e ".[drive-api]"
```

### Cách D — Chạy bằng Docker
```bash
docker compose up --build -d
# Mở http://127.0.0.1:8765
```

---

## 2. Cài Đặt Phần Mềm, Dòng Lệnh (Console) & Đăng Nhập / Kết Nối Bên Thứ 3 (`v1.1.0`)

### A. Đăng nhập Google Drive OAuth 2.0 ngay trong giao diện (để quét `[A] STORAGE` và mọi kho Drive)
1. Mở tab **Tài Khoản & Kết Nối** trong ứng dụng KAS Desktop.
2. Tại mục **Google Drive API (OAuth 2.0)**, tải lên hoặc dán nội dung tệp **`credentials.json`** (OAuth Client loại *Desktop App* từ Google Cloud Console) rồi bấm **Lưu credentials.json**.
3. Bấm **Đăng nhập Google (mở trình duyệt)** → chọn tài khoản Google và cấp quyền → KAS tự lưu `token.json` tại `%USERPROFILE%\.config\kas\token.json` (`~/.config/kas/token.json`).
4. Quay lại tab **Kho Dữ Liệu** và bấm **Quét kho** — toàn bộ kho Google Drive được quét tức thời!

### B. Đăng nhập Phần mềm (Khóa Ứng Dụng — App Lock) & Kết nối GitHub / Webhook
- Trong tab **Tài Khoản & Kết Nối**, bạn có thể tạo tài khoản KAS cục bộ (mật khẩu băm **PBKDF2-HMAC-SHA256**, 200.000 vòng) và bật công tắc **Yêu cầu đăng nhập khi mở giao diện KAS**.
- Kết nối **GitHub Personal Access Token** (kiểm chứng trực tiếp qua GitHub API) và quản lý các **Custom Connectors** (Webhook / n8n / Make / Nextcloud WebDAV / S3 / REST API).
- Hoặc quản lý nhanh bằng CLI:
```bash
kas account register admin --password "<mat-khau>" --require-login
kas account lock on|off
kas account connect-github --token "<ghp_...>"
kas account status
```

### C. Dòng Lệnh Tích Hợp (`>_ Lệnh` · phím tắt `Ctrl+K`)
- Nhấn `Ctrl+K` (hoặc mở tab **Dòng Lệnh (Console)**) để gõ trực tiếp mọi lệnh `kas` ngay trong phần mềm mà không cần mở PowerShell/Terminal (hỗ trợ đường dẫn Windows như `vault add "Sách" "E:\SÁCH"`, lịch sử phím `↑`/`↓` và các chip lệnh nhanh 1 bấm).

### D. Phần Cài Đặt (`kas settings` & Tab *Cài Đặt*)
- Chỉnh giao diện **Tối / Sáng**, ngôn ngữ **VI / EN**, tab mặc định, cổng HTTP, backend mặc định (`auto/api/cli/local`), số luồng quét, thư mục dữ liệu tùy chỉnh, kiểm tra phiên bản mới từ GitHub Releases và sao lưu/nhập JSON cấu hình.
```bash
kas settings show
kas settings set theme light
kas settings set scan_workers 24
kas settings check-update
kas settings reset
```

---

## 3. Kết nối Nhiều Kho Dữ Liệu, Quy Tắc Đặt Tên & AI / MCP Agent

```bash
# Kho cục bộ / ổ rời / NAS / Google Drive bất kỳ
kas vault add "Kho Sách" "E:\SÁCH"
kas vault add "[A] STORAGE" "https://drive.google.com/drive/folders/<FOLDER_ID>"
kas quet
kas db search "triet hoc"

# Tùy chỉnh quy tắc đặt tên (4 bộ mẫu + bộ thử nghiệm thời gian thực trong UI)
kas rules presets
kas rules apply-preset general_clean
kas rules test "01_bai_tap_cuoi_ky.PDF"

# Trợ lý AI tích hợp & Máy chủ MCP cho Claude Desktop / Cursor / Antigravity
kas ai ask "Thống kê kho hiện tại và kiểm tra lỗi đặt tên"
kas ai config --provider gemini --model gemini-2.5-flash --api-key "<API_KEY>"
kas mcp config --client claude
```
