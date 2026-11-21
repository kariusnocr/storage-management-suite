# TỔNG QUAN HỆ THỐNG — [03] QUẢN LÝ (`v4.0.0`)

Thư mục **`[A] STORAGE / [00] TỔNG QUAN / [03] QUẢN LÝ`** (`1dU9BqIFxdLyhsFzxZxOiKWVNHI0vk7W3`) là trung tâm lưu trữ tài liệu quản trị và bản phát hành phần mềm **Storage Management Suite `v4.0.0`**, được kết nối chính thức với kho mã nguồn GitHub **`kariusnocr/storage-management-suite`**.

---

## 1. Kiến trúc Gói Phần Mềm (`src/storage_suite/`)

Từ phiên bản **`v4.0.0`**, toàn bộ 18 mô-đun rời rạc (`[01]`–`[18]`) được hợp nhất thành gói phần mềm chuẩn Python **`storage-management-suite`** với lệnh điều phối duy nhất **`astorage`** (và giao diện **`astorage ui`** / **`astorage desktop`**):

| Phân hệ gói | Mô-đun chính | Lệnh `astorage` | Vai trò |
| :--- | :--- | :--- | :--- |
| `core/` | `config`, `drive_cli`, `drive_api`, `naming`, `catalog_spec`, `ocr` | `auth`, `version` | Cấu hình đa hồ sơ, Dual Drive (`gdrive` CLI + OAuth 2.0 API độc lập), Chuẩn V6, **Chuẩn Danh Mục V7**, OCR `vie+eng` hợp nhất |
| `store/` | `sqlite_store`, `legacy_compat` | `db`, `undo` | Cơ sở dữ liệu SQLite (WAL + FTS5 tìm kiếm `<20 ms`) và Sổ cái Hoàn tác Hợp nhất |
| `ops/` | `indexer`, `auditor`, `normalizer`, `catalog_engine`, `dedup`, `reporter`, `transfer`, `ingestor`, `inspector`, `doctor`, `watcher` | `quet`, `kiem-tra`, `chuan-hoa`, `danh-muc`, `danh-muc-chuan`, `trung-lap`, `bao-cao`, `sao-chep-di-chuyen`, `nhap-du-lieu`, `tra-cuu`, `doctor`, `watch` | Toàn bộ nghiệp vụ quản trị kho, tinh gọn danh mục thông minh V7, dọn rác `MACOSX`, chẩn đoán hệ thống & theo dõi biến động |
| `media/` | `file_reader`, `content_analyzer`, `image_analyzer`, `audio_analyzer`, `video_analyzer` | `doc-tep`, `phan-tich`, `phan-tich-anh`, `phan-tich-am-thanh`, `phan-tich-video` | Đọc đa định dạng, TF-IDF/SimHash, EXIF/dHash/pHash/OCR `vie+eng`, ID3/EBU R128 LUFS, Contact Sheet 3×2 |
| `sync/` | `drive_deploy`, `github_sync` | `trien-khai`, `github` | Xuất bản tài liệu + gói `.whl` lên Drive `[03] QUẢN LÝ`, kiểm toán bảo mật, đồng bộ Git/GitHub & Releases |
| `cli/` & `web/` | `cli/main`, `cli/pipelines`, `web/app`, `web/desktop` | `quy-trinh-nhanh`, `bao-tri-dinh-ki`, `ui`, `desktop` | Pipeline in-process dùng chung ngữ cảnh, Web Dashboard cục bộ (FastAPI) & Desktop App (`pywebview`) |

---

## 2. Cấu trúc Phân phối trên Google Drive `[03] QUẢN LÝ`

Thay vì đồng bộ rời rạc 40 tệp mã nguồn, `[00] TỔNG QUAN / [03] QUẢN LÝ` được tổ chức tinh gọn:
- **`Tổng Quan Hệ Thống - Quản Lý.md`** *(giữ nguyên File ID gốc)*: Tài liệu kiến trúc tổng quan này.
- **`[01] TÀI LIỆU HỆ THỐNG/`**: Đặc tả **Chuẩn Danh Mục V7**, hướng dẫn cài đặt phần mềm (Windows/macOS/Linux/Docker/OAuth 2.0), và `README.md`.
- **`[02] GÓI PHÁT HÀNH/`**: Gói cài đặt `.whl` / `.tar.gz` và bản phát hành đóng gói sẵn cho từng phiên bản.

---

## 3. Quy trình Vận hành Chuẩn

```bash
astorage doctor                          # Kiểm tra công cụ, OCR vie+eng, Drive backend & SQLite
astorage quet --tang-cuong               # Quét tăng cường vào storage.db (FTS5)
astorage kiem-tra                        # Kiểm toán Chuẩn V6 + 5 mã Chuẩn Danh Mục V7
astorage danh-muc-chuan                  # Chạy thử tinh gọn & chuẩn hóa tên Danh Mục V7
astorage trung-lap --don-rac-he-thong    # Rà soát trùng lặp & thư mục rác MACOSX
astorage quy-trinh-nhanh                 # Chạy chuỗi bảo trì nhanh in-process (chạy thử)
astorage ui                              # Mở giao diện quản trị trực quan cục bộ
```
