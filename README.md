# Karius Academic System (KAS) `v5.0.0`

**Karius Academic System (KAS)** là phần mềm quản trị tri thức và **đa kho dữ liệu (Multi-Vault)** tổng quát — mặc định hỗ trợ kết nối, lập chỉ mục **SQLite WAL + FTS5**, kiểm toán, chuẩn hóa **Chuẩn V6 / Danh Mục V7**, chống trùng lặp, đọc/OCR tiếng Việt và phân tích đa phương tiện trên **mọi kho dữ liệu bất kỳ**:

- **Thư mục cục bộ trên máy tính / Ổ cứng rời / NAS / Thư mục đồng bộ OneDrive · iCloud · Google Drive for Desktop** (`LocalFSBackend` — chạy 100% ngoại tuyến, không cần đăng nhập).
- **Mọi thư mục hoặc Shared Drive trên Google Drive** (`GoogleDriveAPIClient` OAuth 2.0 trên máy cá nhân & `GDriveCLIClient` trên cloud VM).

---

## 1. Tính năng Nổi bật ở `v5.0.0`

- **Đa kho thực thụ (Universal Multi-Vault)**:
  - Quản lý không giới hạn số lượng kho trong `~/.config/kas/vaults.toml` (`kas vault add|list|use|info|remove|init-structure`).
  - Dữ liệu chỉ mục (`kas.db`), báo cáo và **Unified Undo Journal** được tách riêng tuyệt đối theo từng kho (`~/.local/share/kas/vaults/<slug>/`).
  - **Tự nhận diện thông minh (Auto-Detect)**: tự phân biệt kho theo **Chuẩn Học thuật KAS (`academic_v7`)** (có `[00] TỔNG QUAN` / `[07] KIỂM TRA` / thư mục `[NN] ...`) với **kho thư mục thông thường (`general`)** — không áp đặt cấu trúc cứng lên kho thường.
  - Chuyển đổi nóng (hot-switch) giữa các kho ngay trên thanh tiêu đề **Web & Desktop UI** hoặc bằng cờ toàn cục `kas --kho <slug> <lệnh>`.
- **Chuẩn Đặt Tên & Tinh Gọn Thông Minh Danh Mục V7**:
  - Chống trùng tên tuyệt đối (Zero-Collision) với `, <Ngữ Cảnh Cha>`, duy nhất 1 dấu `" - "`, tinh gọn thông minh Phương án 2, bảo toàn 100% File ID và hoàn tác 1 lệnh qua `kas undo`.
- **An toàn 100% với Windows 11 Smart App Control**:
  - Máy chủ Web Dashboard có chế độ thuần Python (`--stdlib`, không nạp `.pyd`/`.dll` ngoài) và mở cửa sổ Desktop độc lập bằng **Microsoft Edge (`--app`)** đã ký số.
  - Bộ cài `kas-windows-sac-safe.zip` chạy hoàn toàn qua `python.exe` / `pythonw.exe` chính thức đã ký số — **không cần tắt Smart App Control**.

---

## 2. Cài đặt Nhanh

### Windows 11 có Smart App Control (Khuyến nghị — không cần tắt bảo mật)
```powershell
irm https://raw.githubusercontent.com/kariusnocr/storage-management-suite/main/packaging/windows/install_windows_sac_safe.ps1 | iex
```
*(Tự động tạo lối tắt Desktop **Karius Academic System (KAS)** và lệnh `kas` trong PATH.)*

### Cài bằng Python (`pip`, Python 3.11+)
```bash
# Cài trọn bộ (CLI + Google Drive OAuth 2.0 + Media/OCR + Web UI + Desktop)
pip install -e ".[all]"

# Hoặc cài gọn thuần Python (CLI + Web UI --stdlib + Google Drive OAuth 2.0):
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
# 1. Kết nối bất kỳ thư mục cục bộ nào (chạy 100% ngoại tuyến)
kas vault add tai-lieu --nguon /duong/dan/thu/muc/cua/ban --ten "Kho Tài Liệu Cá Nhân"

# 2. Hoặc kết nối bất kỳ thư mục Google Drive nào (dán URL hoặc Folder ID)
kas auth login --credentials /duong/dan/credentials.json
kas vault add storage --nguon https://drive.google.com/drive/folders/<FOLDER_ID> --ten "[A] STORAGE"

# 3. Xem danh sách kho & chuyển kho hoạt động
kas vault list
kas vault use tai-lieu

# 4. Quét chỉ mục SQLite FTS5 & tìm kiếm tức thời (<20 ms)
kas quet
kas db search "triet hoc"

# 5. Thực thi lệnh trên một kho cụ thể bất kỳ bằng cờ `--kho`
kas --kho storage danh-muc-chuan
kas --kho tai-lieu trung-lap --don-rac-he-thong

# 6. Mở ứng dụng Desktop / Web Dashboard (chuyển kho tức thì ngay trên giao diện)
kas desktop --browser --stdlib
# hoặc: kas ui --open --stdlib
```

---

## 4. Kiến trúc Gói Mã nguồn (`src/karius_academic_system/`)

- `core/`: `vaults.py` (Multi-Vault Registry), `local_fs.py` (`LocalFSBackend`), `config.py` (ngữ cảnh đa kho động), `drive_api.py` (OAuth 2.0), `drive_cli.py`, `drive_factory.py`, `naming.py` (Chuẩn V6), `catalog_spec.py` (Chuẩn V7), `ocr.py` (`vie+eng`).
- `store/`: `sqlite_store.py` (SQLite WAL + FTS5 + Unified Undo Journal hỗ trợ cả Drive lẫn LocalFS).
- `ops/`: `indexer.py`, `auditor.py`, `normalizer.py`, `catalog_engine.py`, `dedup.py`, `reporter.py`, `transfer.py`, `ingestor.py`, `inspector.py`, `doctor.py`, `watcher.py`.
- `media/`: `file_reader.py`, `content_analyzer.py`, `image_analyzer.py`, `audio_analyzer.py`, `video_analyzer.py`.
- `sync/`: `drive_deploy.py`, `github_sync.py`.
- `cli/` & `web/`: `kas`, `kas-desktop`, Web Dashboard FastAPI + máy chủ thuần Python `--stdlib`.
