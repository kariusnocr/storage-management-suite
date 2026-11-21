# HƯỚNG DẪN CÀI ĐẶT & SỬ DỤNG PHẦN MỀM — STORAGE MANAGEMENT SUITE (`v4.0.1`)

## 1. Chọn Phương thức Cài đặt

### Cách A (Khuyến nghị trên Windows 11 có Smart App Control) — Cài An toàn qua Python có Chữ ký số (KHÔNG cần tắt Smart App Control)

> [!IMPORTANT]
> Trên **Windows 11**, tính năng **Smart App Control (SAC)** sẽ chặn mọi tệp `.exe` chưa ký số thương mại (như `astorage-windows-x64.exe`) và **không có nút "Run anyway"**. Bạn **KHÔNG nên tắt Smart App Control** (khi đã tắt sẽ không bật lại được nếu không cài lại Windows).
>
> Thay vào đó, hãy chạy trực tiếp bằng trình thông dịch **Python chính thức đã ký số** (`Python Software Foundation` / `Microsoft Store`) + máy chủ HTTP thuần Python (`--stdlib`, không nạp tệp `.pyd`/`.dll` ngoài) + cửa sổ **Microsoft Edge App Window** (đã ký số bởi Microsoft):

**Cài nhanh bằng 1 lệnh trong PowerShell (tự tạo lối tắt Desktop & lệnh `astorage`):**
```powershell
irm https://raw.githubusercontent.com/kariusnocr/storage-management-suite/main/packaging/windows/install_windows_sac_safe.ps1 | iex
```

Hoặc tải **`astorage-windows-sac-safe.zip`** từ **GitHub Releases** / Drive `[03] QUẢN LÝ/[02] GÓI PHÁT HÀNH`, giải nén và chạy:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install_windows_sac_safe.ps1
```

Hoặc cài thủ công (lưu ý dùng `py -3 -m pip`, **không** gõ `pip.exe`):
```powershell
winget install -e --id Python.Python.3.12 --scope user
py -3 -m pip install --user --upgrade https://github.com/kariusnocr/storage-management-suite/releases/download/v4.0.1/storage_management_suite-4.0.1-py3-none-any.whl openpyxl google-api-python-client google-auth-oauthlib
py -3 -m storage_suite desktop --browser --stdlib
```

### Cách B — Tải Bản Thực thi Độc lập (macOS / Linux / Windows không bật Smart App Control)
1. Tải tệp tương ứng từ trang **GitHub Releases** của `kariusnocr/storage-management-suite`:
   - Windows: `astorage-windows-x64.exe` *(yêu cầu ký số Authenticode qua Azure Artifact Signing / SignPath nếu bật Smart App Control)*
   - macOS: `astorage-macos-arm64`
   - Linux: `astorage-linux-x64`
2. Đối chiếu mã băm trong `SHA256SUMS.txt`.
3. Chạy `astorage doctor` hoặc `astorage desktop`.

### Cách C — Cài bằng `pip` / `pipx` (Linux / macOS / WSL2 / nhà phát triển)
```bash
# Cài trọn bộ gồm CLI, Media/OCR, Web UI, Desktop (pywebview) và Google Drive API OAuth 2.0
pip install "storage-management-suite[all]"
# Hoặc từ mã nguồn cục bộ:
pip install -e ".[all]"
```

### Cách D — Chạy bằng Docker (Tích hợp sẵn ffmpeg, tesseract vie+eng, poppler, 7z — không bị Smart App Control chặn)
```bash
docker compose up --build -d
# Truy cập Web Dashboard tại http://127.0.0.1:8765
```

---

## 2. Thiết lập Kết nối Google Drive Độc lập (OAuth 2.0 trên Windows/macOS/Linux)

Trên cloud VM đã có sẵn CLI `gdrive`, phần mềm sẽ tự nhận diện (`backend=cli`).
Trên máy tính cá nhân không cài `gdrive`, dùng trực tiếp **Google Drive API v3 (OAuth 2.0)**:

1. Vào **Google Cloud Console** → tạo dự án (hoặc chọn dự án sẵn có) → bật **Google Drive API**.
2. Vào **APIs & Services → Credentials → Create Credentials → OAuth client ID → Desktop app** → tải tệp `credentials.json`.
3. Chạy lệnh đăng nhập một lần:
   ```bash
   astorage auth login --credentials /đường/dẫn/credentials.json
   astorage auth status
   ```
4. Token được lưu an toàn tại `~/.config/astorage/token.json` (quyền `0600`) và tự động làm mới (`refresh_token`).
5. Để ép dùng backend OAuth 2.0 thay vì CLI: đặt biến môi trường `STORAGE_DRIVE_BACKEND=api`.

---

## 3. Cấu hình Đa Kho (`~/.config/astorage/profiles.toml`)

Bạn có thể quản lý nhiều kho Google Drive khác nhau bằng tệp `~/.config/astorage/profiles.toml`:

```toml
default_profile = "storage"

[profiles.storage]
root_name = "[A] STORAGE"
root_id = "194HC3C2WC1BSzfK3cn_0_uUJ4vfDuBsr"
drive_backend = "auto"

[profiles.archive_extra]
root_name = "[B] ARCHIVE"
root_id = "<FOLDER_ID_KHAC>"
drive_backend = "api"
```

Chuyển đổi hồ sơ bằng biến môi trường `ASTORAGE_PROFILE=archive_extra`.

---

## 4. Tự đóng gói Nhị phân / Ứng dụng Desktop từ Mã nguồn

```bash
pip install -e ".[all]" pyinstaller
python packaging/build_binary.py --mode cli       # Đóng gói CLI + Web UI
python packaging/build_binary.py --mode desktop   # Đóng gói cửa sổ Desktop App (pywebview)
```
