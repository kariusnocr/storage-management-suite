# HƯỚNG DẪN CÀI ĐẶT & SỬ DỤNG — KARIUS ACADEMIC SYSTEM (KAS `v5.0.0`)

## 1. Chọn Phương thức Cài đặt

### Cách A (Khuyến nghị trên Windows 11 có Smart App Control) — Cài An toàn không cần tắt bảo mật

> [!IMPORTANT]
> **Windows 11 Smart App Control (SAC)** chặn các tệp `.exe` chưa ký số thương mại và không có nút *Run anyway*. Bạn **KHÔNG nên tắt Smart App Control**.
>
> Karius Academic System (KAS) chạy trực tiếp trên **Python chính thức đã ký số** (`python.exe` / `pythonw.exe`) + **máy chủ Web thuần Python (`--stdlib`)** + cửa sổ độc lập **Microsoft Edge (`--app`)** — hoàn toàn không dùng `.exe` hay `.pyd` chưa ký số.

**Cài nhanh bằng 1 lệnh PowerShell:**
```powershell
irm https://raw.githubusercontent.com/kariusnocr/storage-management-suite/main/packaging/windows/install_windows_sac_safe.ps1 | iex
```

Hoặc tải **`kas-windows-sac-safe.zip`** từ **GitHub Releases**, giải nén và chạy:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install_windows_sac_safe.ps1
```

### Cách B — Tải Binary Độc lập (macOS / Linux / Windows không bật SAC)
1. Tải tệp từ **GitHub Releases** (`kas-windows-x64.exe`, `kas-macos-arm64`, `kas-linux-x64`).
2. Kiểm tra mã băm trong `SHA256SUMS.txt`.
3. Chạy `kas doctor` hoặc `kas desktop`.

### Cách C — Cài bằng `pip` (Python 3.11+)
```bash
pip install "karius-academic-system[all]"
# Hoặc từ mã nguồn cục bộ:
pip install -e ".[all]"
```

### Cách D — Chạy bằng Docker
```bash
docker compose up --build -d
# Mở http://127.0.0.1:8765
```

---

## 2. Kết nối Nhiều Kho Dữ Liệu (Cục bộ & Google Drive bất kỳ)

KAS mặc định **không gắn cứng vào bất kỳ kho đơn lẻ nào**. Bạn có thể kết nối đồng thời bao nhiêu kho tùy ý:

### A. Kết nối Thư mục Cục bộ / Ổ cứng rời / NAS / OneDrive đồng bộ (100% ngoại tuyến)
```bash
kas vault add hoc-tap --nguon "D:\TaiLieuHocTap" --ten "Kho Học Tập Cá Nhân"
kas quet
kas db search "kinh te"
```

### B. Kết nối Bất kỳ Thư mục Google Drive nào (OAuth 2.0 trên máy cá nhân)
1. Tạo OAuth Desktop Client trong Google Cloud Console (bật Google Drive API) → tải `credentials.json`.
2. Đăng nhập một lần:
   ```bash
   kas auth login --credentials /đường/dẫn/credentials.json
   kas auth status
   ```
3. Kết nối một hoặc nhiều kho Google Drive (chỉ cần dán URL thư mục Drive hoặc Folder ID):
   ```bash
   kas vault add storage --nguon https://drive.google.com/drive/folders/<FOLDER_ID_1> --ten "[A] STORAGE"
   kas vault add nghien-cuu --nguon https://drive.google.com/drive/folders/<FOLDER_ID_2> --ten "Kho Nghiên Cứu"
   ```
4. Chuyển kho hoặc chỉ định kho theo từng lệnh:
   ```bash
   kas vault list
   kas vault use nghien-cuu
   kas --kho storage danh-muc-chuan
   ```

### C. Chế độ Tự nhận diện Cấu trúc Kho (`auto` | `academic_v7` | `general`)
- **`auto` (mặc định)**: KAS tự phát hiện kho có khung `[00] TỔNG QUAN` / `[07] KIỂM TRA` hoặc thư mục đánh số `[NN] ...` (`academic_v7`) hay là kho thư mục thường (`general`) để áp dụng bộ kiểm toán phù hợp mà không gây cảnh báo thừa.
- Nếu muốn áp dụng khung Chuẩn KAS đầy đủ cho một kho mới, chạy:
  ```bash
  kas vault init-structure --thuc-thi --dong-y
  ```

---

## 3. Khởi chạy Giao diện Desktop / Web Dashboard

- Nhấp đúp biểu tượng **Karius Academic System (KAS)** trên Desktop (Windows), hoặc chạy:
  ```bash
  kas desktop --browser --stdlib
  ```
- Trên thanh tiêu đề có sẵn **Bộ chuyển kho (Vault Switcher)** và tab **Kho Dữ Liệu (Vaults)** để thêm kho cục bộ, dán link Google Drive, quét chỉ mục và chuyển kho tức thì.
