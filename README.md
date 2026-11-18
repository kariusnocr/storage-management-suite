# Bộ Chương Trình Quản Lý Kho Dữ Liệu `[A] STORAGE` (Chuẩn V6 — v3.2)

Kho lưu trữ chính thức chứa bộ **15 chương trình quản trị, chuẩn hóa, đọc và phân tích dữ liệu** cho kho Google Drive **`[A] STORAGE`**, được đồng bộ hai chiều với thư mục **`[A] STORAGE/[00] TỔNG QUAN/[03] QUẢN LÝ`** (`1dU9BqIFxdLyhsFzxZxOiKWVNHI0vk7W3`).

---

## 1. Kiến trúc 15 Mô-đun (`[01]`–`[15]`)

| Thư mục mô-đun | Tệp mã nguồn | Lệnh `storage_cli.py` | Chức năng chính |
| :--- | :--- | :--- | :--- |
| `[01] THƯ VIỆN LÕI` | `storage_core.py`<br>`storage_config.json`<br>`tests/test_storage_suite.py` | `kiem-thu` | Thư viện lõi Chuẩn V6, bao bọc `gdrive` tốc độ cao (`stream_ls`, `stream_info`, `stream_capabilities`), bộ kiểm thử tự động ngoại tuyến (`22/22` bài kiểm thử) |
| `[02] QUÉT CHỈ MỤC` | `storage_indexer.py` | `quet` | Quét toàn kho theo tầng BFS dùng `stream_ls` hoặc quét tăng cường (`--tang-cuong`) kèm bộ đệm shortcut |
| `[03] KIỂM TRA QUY ƯỚC` | `naming_auditor.py` | `kiem-tra` | Kiểm toán quy ước đặt tên & cấu trúc thư mục theo Chuẩn V6, sửa lỗi cơ học an toàn (`--sua-an-toan`) |
| `[04] CHUẨN HÓA TÊN` | `storage_toolkit.py` | `chuan-hoa` | Chuẩn hóa tên bất biến (100% không chạm tệp đã đạt Chuẩn V6), khôi phục dấu tiếng Việt theo ngữ cảnh |
| `[05] DANH MỤC HỆ THỐNG` | `sheet_engine.py`<br>`sheet_updater.py` | `danh-muc` | Tạo và cập nhật tại chỗ hệ thống bảng Google Sheets `Danh Mục Hệ Thống - …` kèm tab `Thống Kê Nhanh` |
| `[06] RÀ SOÁT TRÙNG LẶP` | `dedup_scanner.py` | `trung-lap` | Phát hiện và cách ly an toàn bản sao trùng lặp (`SHA-256`), phiên bản thừa, `TongQuan.md` trùng và shortcut lỗi |
| `[07] BÁO CÁO THỐNG KÊ` | `stats_reporter.py` | `bao-cao` | Tính điểm **Sức khỏe Kho (Health Score)**, phân tích xu hướng snapshot và xuất nhật kí biến động `.md` / `.csv` |
| `[08] TRIỂN KHAI MÃ NGUỒN` | `deploy_sync.py` | `trien-khai` | Đồng bộ hai chiều giữa thư mục cục bộ và Google Drive `[03] QUẢN LÝ` qua `sync_manifest.json` (giữ 100% File ID) |
| `[09] ĐIỀU PHỐI VẬN HÀNH` | `storage_cli.py` | *(điểm vào chính)* | CLI điều phối hợp nhất cho mọi mô-đun lẻ cùng 2 quy trình `quy-trinh-nhanh` và `bao-tri-dinh-ki` |
| `[10] SAO CHÉP DI CHUYỂN` | `transfer_manager.py` | `sao-chep-di-chuyen` | Sao chép/di chuyển đệ quy, chia nhánh tự động đánh số `[STT]`, đổi số thứ tự và hoàn tác theo lô |
| `[11] NHẬP DỮ LIỆU MỚI` | `data_ingestor.py` | `nhap-du-lieu` | Tiếp nhận dữ liệu mới từ máy cục bộ, Drive ID/URL hoặc khu `[07] KIỂM TRA/[04] NHẬP DỮ LIỆU`, tự phân loại chủ đề & đặt tên Chuẩn V6 |
| `[12] TRA CỨU VÀ KIỂM TOÁN` | `storage_inspector.py` | `tra-cuu` | Tìm kiếm tức thì (<0,2s), kiểm toán & tự động bù đắp bộ 3 `[00] TỔNG QUAN`, kiểm toán quyền và dọn thư mục rỗng |
| `[13] ĐỌC TỆP` | `file_reader.py` | `doc-tep` | Bộ đọc đa định dạng (`PDF`, `DOCX`, `PPTX`, `XLSX`, `EPUB`, `MOBI/AZW3`, `DOC/XLS/PPT`, `MD/CSV/HTML/JSON`, Google Docs/Sheets/Slides, Ảnh EXIF, `MP3/MP4`, `ZIP/RAR/7Z`) có bộ đệm bền vững |
| `[14] PHÂN TÍCH NỘI DUNG` | `content_analyzer.py` | `phan-tich` | Nhận diện ngôn ngữ, từ khóa `TF-IDF`, phân loại chủ đề, gợi ý tên Chuẩn V6 từ siêu dữ liệu, tìm trùng nội dung `SimHash 64-bit` và tìm kiếm toàn văn |
| `[15] ĐỒNG BỘ GITHUB` | `github_sync.py` | `github` | Kiểm toán bảo mật mã nguồn, đồng bộ Git/GitHub, theo dõi GitHub Actions CI và đồng bộ liên hoàn Drive ↔ Local ↔ GitHub |

---

## 2. Hướng dẫn sử dụng nhanh

```bash
# 1. Chạy bộ kiểm thử tự động ngoại tuyến (không cần kết nối mạng)
python3 "[09] ĐIỀU PHỐI VẬN HÀNH/storage_cli.py" kiem-thu

# 2. Kiểm tra trạng thái đồng bộ GitHub, Google Drive [03] QUẢN LÝ và GitHub Actions CI
python3 "[09] ĐIỀU PHỐI VẬN HÀNH/storage_cli.py" github trang-thai

# 3. Đồng bộ liên hoàn mã nguồn lên cả Google Drive [03] QUẢN LÝ lẫn GitHub
python3 "[09] ĐIỀU PHỐI VẬN HÀNH/storage_cli.py" github dong-bo-2-chieu --ghi-de-xung-dot --thuc-thi --dong-y

# 4. Đọc và phân tích nội dung tệp theo nhánh
python3 "[09] ĐIỀU PHỐI VẬN HÀNH/storage_cli.py" doc-tep trich-xuat --nhanh "[05] SƯU TẦM/[01] SÁCH/[14] SỨC KHOẺ - Y HỌC" --gioi-han 25
python3 "[09] ĐIỀU PHỐI VẬN HÀNH/storage_cli.py" phan-tich phan-tich --tai-len
```

---

## 3. Nguyên tắc An toàn & Bảo mật

1. **Mặc định Chạy thử (Dry-run)**: Mọi thao tác có ghi dữ liệu lên Google Drive hoặc GitHub đều mặc định chạy thử; chỉ thực thi khi truyền cờ `--thuc-thi` (hoặc `--execute`).
2. **Bảo toàn 100% Drive File ID & Không xóa vĩnh viễn**: Mọi bản cập nhật mã nguồn, tài liệu và bảng tính đều ghi đè tại chỗ (`update`/`rename`); các mục dư thừa chỉ di chuyển vào khu cách ly `[07] KIỂM TRA` kèm nhật kí hoàn tác.
3. **Tách biệt Mã nguồn & Dữ liệu vận hành**: Dữ liệu chỉ mục lớn (`storage_index.json`, `content_cache/`, `snapshots/`) được lưu tại `~/storage_data` bên ngoài kho Git và được bảo vệ tự động bởi `github_sync.py kiem-tra-bao-mat`.
