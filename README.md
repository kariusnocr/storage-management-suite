# Storage Management Suite `v4.0.1` — Phần Mềm Quản Lý Kho Dữ Liệu `[A] STORAGE`

Phần mềm quản trị toàn diện kho Google Drive **`[A] STORAGE`** theo **Chuẩn V6** & **Chuẩn Danh Mục V7** — tích hợp bộ 18 mô-đun vận hành/phân tích đa phương tiện, cơ sở dữ liệu **SQLite WAL + FTS5**, **2 backend Google Drive** (`gdrive` CLI & **Google Drive API v3 OAuth 2.0** độc lập), giao diện **Web Dashboard cục bộ (`astorage ui`)** có chế độ thuần Python (`--stdlib`) an toàn với **Windows 11 Smart App Control**, ứng dụng **Desktop (`astorage desktop`)**, đóng gói nhị phân đa nền tảng (**Windows/macOS/Linux**) và **Docker**.

---

## 1. Tính năng Nổi bật ở `v4.0.x`

- **Chuẩn Đặt Tên & Tinh Gọn Thông Minh Danh Mục V7**:
  - Duy nhất 1 dấu phân cách `" - "` (`USSH: Trường ĐH KHXH&NV`, `Tôn Giáo – Tín Ngưỡng`).
  - **Chống trùng tên tuyệt đối (Zero-Collision)**: Tự động gắn `, <Ngữ Cảnh Cha>` cho tên chung/trùng tên (`Handout`, `Key`, `Slide`, `Cấu Phần Sách`...).
  - **Tinh gọn thông minh (Phương án 2)**: Loại trừ `MACOSX`/rác kỹ thuật, lập bảng tối ưu cho gốc + cấp `1..4` + cấp `5` không rỗng + cấp `6` quy mô lớn (`≥ 15` mục), giảm từ `2.741` xuống `~493` bảng (`-82%`) và bảo toàn `100%` Drive File ID.
  - Kiểm toán chuyên biệt 5 mã mới: `DANH_MUC_RAC_KY_THUAT`, `DANH_MUC_MO_COI`, `DANH_MUC_TRUNG_TEN`, `DANH_MUC_SAI_TEN`, `DANH_MUC_CO_THE_TINH_GON`.
- **Kiến trúc Phần mềm Chuẩn (`src/storage_suite/`)**:
  - Loại bỏ hoàn toàn mã khởi nạp lặp; gọi quy trình **in-process** chia sẻ ngữ cảnh.
  - Tầng lưu trữ **SQLite (`storage.db`, WAL + FTS5)**: tìm kiếm toàn kho `<20 ms`, kèm **Unified Undo Journal** (`astorage undo`).
  - Bộ OCR hợp nhất (`vie+eng`) dùng chung cho PDF scan, hình ảnh và slide video.
- **Kết nối Google Drive Độc lập (Dual Backend)**:
  - `GDriveCLIClient`: tốc độ cao trên cloud VM (`gdrive readonly stream`).
  - `GoogleDriveAPIClient` (**OAuth 2.0**): chạy độc lập trên Windows/macOS/Linux cá nhân không cần cài `gdrive` CLI (`astorage auth login`).
- **Đóng gói Phần mềm Mức 3**:
  - CLI hợp nhất: `astorage` / `storage-suite`
  - Web Dashboard cục bộ: `astorage ui` (`http://127.0.0.1:8765`, tự dự phòng máy chủ HTTP thuần Python `--stdlib` không nạp DLL ngoài)
  - Desktop App: `astorage desktop` (`pywebview` hoặc cửa sổ độc lập Microsoft Edge/Chrome đã ký số)
  - Bộ cài Windows 11 an toàn Smart App Control (`astorage-windows-sac-safe.zip`), Binary độc lập (`packaging/pyinstaller.spec`) & Container (`Dockerfile`, `docker-compose.yml`).

---

## 2. Cài đặt Nhanh

### Windows 11 bật Smart App Control (Khuyến nghị — không cần tắt bảo mật)
```powershell
irm https://raw.githubusercontent.com/kariusnocr/storage-management-suite/main/packaging/windows/install_windows_sac_safe.ps1 | iex
```
*(Chạy hoàn toàn trên `python.exe`/`pythonw.exe` chính thức đã ký số + cửa sổ Microsoft Edge `--app`, không bị Smart App Control chặn.)*

### Cài từ mã nguồn (Python 3.11+)
```bash
# Cài bản đầy đủ (CLI + Media/OCR + Web UI + Google Drive API OAuth 2.0 + Desktop)
pip install -e ".[all]"

# Hoặc cài riêng từng thành phần:
pip install -e ".[media,web,drive-api]"
```

### Đăng nhập Google Drive API trên máy cá nhân (Windows/macOS/Linux)
```bash
astorage auth login --credentials /đường/dẫn/credentials.json
astorage auth status
```

### Chạy bằng Docker
```bash
docker compose up --build -d
# Mở trình duyệt tại http://127.0.0.1:8765
```

---

## 3. Hướng dẫn Sử dụng Nhanh (`astorage`)

```bash
# 1. Chẩn đoán sức khỏe môi trường & công cụ
astorage doctor

# 2. Chạy bộ kiểm thử tự động ngoại tuyến
astorage kiem-thu

# 3. Quét chỉ mục kho (lưu tự động vào SQLite FTS5 + JSON snapshot)
astorage quet --tang-cuong

# 4. Tra cứu toàn kho tức thì (<20 ms) bằng SQLite FTS5
astorage db search "triet hoc"

# 5. Kiểm toán Chuẩn V6 + Danh Mục V7
astorage kiem-tra

# 6. Lập kế hoạch (chạy thử) & thực thi Chuẩn Danh Mục V7 (Tinh gọn thông minh + Chống trùng tên)
astorage danh-muc-chuan
astorage danh-muc-chuan --thuc-thi --dong-y

# 7. Quét trùng lặp + cách ly thư mục rác MACOSX (chạy thử mặc định)
astorage trung-lap --don-rac-he-thong

# 8. Hoàn tác 1 lệnh từ Unified Undo Journal
astorage undo list
astorage undo run <batch_id> --thuc-thi --dong-y

# 9. Mở Giao diện Web Dashboard hoặc Ứng dụng Desktop
astorage ui
astorage desktop

# 10. Xuất bản tài liệu + gói `.whl` lên Google Drive [00] TỔNG QUAN/[03] QUẢN LÝ
astorage trien-khai phat-hanh-drive
```

---

## 4. Cấu trúc Kho Mã Nguồn (`v4.0.0`)

| Thư mục / Tệp | Vai trò |
| :--- | :--- |
| `pyproject.toml` | Khai báo gói PEP 621, entry points `astorage`, `storage-suite`, `astorage-desktop` |
| `src/storage_suite/core/` | Cấu hình đa hồ sơ (`profiles.toml`), Dual Drive (`cli` + `api` OAuth 2.0), Chuẩn V6, **Chuẩn Danh Mục V7**, OCR hợp nhất (`vie+eng`) |
| `src/storage_suite/store/` | Cơ sở dữ liệu SQLite (`storage.db`, WAL + FTS5) & Unified Undo Journal |
| `src/storage_suite/ops/` | Quét chỉ mục, kiểm toán V6/V7, chuẩn hóa tên, động cơ danh mục, rà soát trùng & `MACOSX`, thống kê, chuyển/nhập dữ liệu, tra cứu, `doctor`, `watch` |
| `src/storage_suite/media/` | Bộ đọc đa định dạng (`PDF/Office/EPUB/MOBI/Archive`) & phân tích Nội dung, Hình ảnh, Âm thanh, Video |
| `src/storage_suite/sync/` | Đồng bộ tài liệu & gói phát hành lên Drive `[03] QUẢN LÝ` và đồng bộ GitHub/CI |
| `src/storage_suite/cli/` | Điểm vào CLI hợp nhất & bộ chạy quy trình in-process |
| `src/storage_suite/web/` | FastAPI Dashboard cục bộ (`astorage ui`) & trình khởi chạy Desktop (`pywebview`) |
| `packaging/` & `Dockerfile` | Cấu hình PyInstaller đa nền tảng (`.exe`/`.app`/Linux) và container Docker |
| `docs/` | Tài liệu đặc tả Chuẩn Danh Mục V7, tổng quan hệ thống và hướng dẫn cài đặt |
| `tests/` | Bộ kiểm thử mô-đun ngoại tuyến (`unittest` / `pytest`) |

---

## 5. Nguyên tắc An toàn & Bảo mật

1. **Mặc định Chạy thử (Dry-run)**: Mọi thao tác ghi lên Google Drive hoặc GitHub chỉ thực thi khi truyền `--thuc-thi` (hoặc xác nhận rõ trong Web UI).
2. **Bảo toàn 100% Drive File ID & Không xóa vĩnh viễn**: Mọi bản cập nhật đều đổi tên/ghi đè tại chỗ; tệp dư, bảng tinh gọn và thư mục rác `MACOSX` chỉ di chuyển vào `[07] KIỂM TRA` kèm nhật kí hoàn tác trong **Unified Undo Journal**.
3. **Tách biệt Mã nguồn & Dữ liệu vận hành**: Cơ sở dữ liệu `storage.db`, ảnh chụp, bộ đệm và token OAuth được lưu ngoài kho Git (`~/storage_data/` và `~/.config/astorage/`).
