# TỔNG QUAN HỆ THỐNG — [03] QUẢN LÝ (v3.2)

Thư mục `[A] STORAGE/[00] TỔNG QUAN/[03] QUẢN LÝ` (`1dU9BqIFxdLyhsFzxZxOiKWVNHI0vk7W3`) chứa toàn bộ 15 chương trình quản trị kho dữ liệu `[A] STORAGE` và được kết nối đồng bộ hai chiều với kho GitHub riêng tư **`kariusnocr/storage-management-suite`**. Thư mục và tài liệu đặt theo **Chuẩn V6**, tệp mã nguồn và cấu hình dùng **`snake_case` PEP 8** theo §2.3 để `import` trực tiếp và chạy kiểm thử tự động.

## 1. Cấu trúc thư mục (`[01]`–`[15]`)

| Thư mục con | Tệp mã nguồn & cấu hình | Chức năng chính |
| :--- | :--- | :--- |
| `[01] THƯ VIỆN LÕI` | `storage_core.py`<br>`storage_config.json`<br>`tests/test_storage_suite.py` | Cấu hình tập trung (`[07] KIỂM TRA`, `github_repo`), `Drive` siêu tốc (`stream_ls`, `stream_info`, `stream_capabilities`, `copy`, `create_shortcut`, `search` phân trang), luật Chuẩn V6 v3.2, kiểm thử ngoại tuyến (`22/22` bài kiểm thử) |
| `[02] QUÉT CHỈ MỤC` | `storage_indexer.py` | Quét toàn kho theo tầng BFS dùng `stream_ls` hoặc **quét tăng cường (`--tang-cuong`)** chống lệch đồng hồ, kèm `--kem-shortcut` cập nhật `shortcut_cache.json` |
| `[03] KIỂM TRA QUY ƯỚC` | `naming_auditor.py` | Kiểm tra tên & cấu trúc theo Chuẩn V6 (`TEP_HE_THONG_CU`, miễn chữ không có hoa/thường như tiếng Thái, Tây Ban Nha); sửa lỗi cơ học an toàn (`--sua-an-toan`) |
| `[04] CHUẨN HÓA TÊN` | `storage_toolkit.py` | Chuẩn hóa tên bất biến (100% không chạm tệp đã đạt V6), khôi phục dấu theo ngữ cảnh, xử lý `TongQuan.md` không trùng |
| `[05] DANH MỤC HỆ THỐNG` | `sheet_engine.py`<br>`sheet_updater.py` | Tạo/cập nhật tại chỗ bảng Google Sheets `Danh Mục Hệ Thống - …` có thêm tab **`Thống Kê Nhanh`**, `--chi-thay-doi`, `--sua-ten-bang` |
| `[06] RÀ SOÁT TRÙNG LẶP` | `dedup_scanner.py` | Tách `trung_chac_chan`, `trung_phien_ban` (`--gom-phien-ban`), `duplicate_tongquan` (`--gom-tong-quan-trung`), xác minh SHA-256, `stream_capabilities`, thư mục rỗng lồng nhau |
| `[07] BÁO CÁO THỐNG KÊ` | `stats_reporter.py` | Chỉ số **Sức khỏe Kho (Health Score)**, xu hướng snapshot, thống kê nhánh/định dạng, nhật kí biến động `.md` + **`.csv` đầy đủ** |
| `[08] TRIỂN KHAI MÃ NGUỒN` | `deploy_sync.py` | Đồng bộ 2 chiều với Drive dùng `sync_manifest.json` (bỏ qua SHA-256 không đổi, phát hiện xung đột, đổi tên giữ nguyên File ID) |
| `[09] ĐIỀU PHỐI VẬN HÀNH` | `storage_cli.py` | Điểm vào thống nhất cho mọi lệnh lẻ (`[02]`–`[15]`), `kiem-thu`, `quy-trinh-nhanh` và `bao-tri-dinh-ki`, ghi nhật kí chạy vào `runs/` |
| `[10] SAO CHÉP DI CHUYỂN` | `transfer_manager.py` | Sao chép/di chuyển đệ quy tệp & thư mục, chia thư mục con tự động đánh số `[STT]`, đổi số thứ tự không va chạm (`--doi-stt`), nhật kí `transfer_log.json` & `--hoan-tac` |
| `[11] NHẬP DỮ LIỆU MỚI` | `data_ingestor.py` | Nhập dữ liệu mới từ máy cục bộ, từ Drive ID/URL ngoài hoặc từ `[07] KIỂM TRA/[04] NHẬP DỮ LIỆU` (hỗ trợ cả shortcut tới thư mục ngoài), chống trùng toàn kho và tự gán tên Chuẩn V6 |
| `[12] TRA CỨU VÀ KIỂM TOÁN` | `storage_inspector.py` | Tìm kiếm tức thì, vẽ cây thư mục, kiểm toán & tự động bù đắp `[00] TỔNG QUAN` (`kiem-toan-tong-quan --bu-dap`), dọn thư mục rỗng từ lá lên gốc (`don-thu-muc-rong`) |
| `[13] ĐỌC TỆP` | `file_reader.py` | Đọc tệp đa định dạng (`PDF`, `DOCX`, `PPTX`, `XLSX`, `EPUB`, `OPF`, `MOBI/AZW3/PRC`, `DOC/XLS/PPT`, `MD/TXT/CSV/HTML/JSON/PY`, Google Docs/Sheets/Slides, Ảnh EXIF, Âm thanh/Video `ffprobe`, `ZIP/RAR/7Z`), bộ đệm bền vững `content_cache/` theo `(id, modifiedTime)`, phát hiện `can_ocr`, `co_mat_khau`, `tep_hong`, `sai_khop_dinh_dang` |
| `[14] PHÂN TÍCH NỘI DUNG` | `content_analyzer.py` | Nhận diện ngôn ngữ (`vi/en/fr/es/de/zh/ja/ru`), trích xuất từ khóa `TF-IDF`, phân loại chủ đề Chuẩn V6 & phát hiện `lech_chu_de`, gợi ý & chuẩn hóa tên Chuẩn V6 từ siêu dữ liệu nội dung (`goi-y-ten`, `hoan-tac-ten`), rà soát trùng/gần trùng nội dung bằng `SimHash 64-bit` (`trung-noi-dung`), tìm kiếm toàn văn (`tim-noi-dung`) |
| `[15] ĐỒNG BỘ GITHUB` | `github_sync.py` | Kết nối với GitHub `kariusnocr/storage-management-suite`: kiểm tra trạng thái Git & GitHub Actions CI (`trang-thai`), quét bảo mật chống rò rỉ khóa/token (`kiem-tra-bao-mat`), đẩy/kéo (`day-len`, `keo-ve`), đồng bộ liên hoàn Drive ↔ Local ↔ GitHub (`dong-bo-2-chieu`) và tạo bản phát hành (`phat-hanh`) |

## 2. Biến môi trường

- `STORAGE_DATA_DIR`: thư mục lưu chỉ mục, ảnh chụp, cache và báo cáo (mặc định `~/storage_data`).
- `STORAGE_ROOT_ID`: ID thư mục gốc `[A] STORAGE` (mặc định `194HC3C2WC1BSzfK3cn_0_uUJ4vfDuBsr`).
- `STORAGE_GITHUB_REPO`: kho lưu trữ GitHub kết nối (mặc định `kariusnocr/storage-management-suite`).
- `STORAGE_CONFIG_PATH`: đường dẫn ghi đè `storage_config.json`.
- `GDRIVE_BIN`: đường dẫn CLI/binary `gdrive` (mặc định tự dùng binary Go đã cache).

## 3. Quy trình vận hành nhanh (qua `[09] storage_cli.py`)

```bash
# Chạy kiểm thử tự động ngoại tuyến (22 bài kiểm thử)
python3 "[09] ĐIỀU PHỐI VẬN HÀNH/storage_cli.py" kiem-thu

# Đọc 1 tệp hoặc trích xuất theo lô vào bộ đệm content_cache
python3 "[09] ĐIỀU PHỐI VẬN HÀNH/storage_cli.py" doc-tep doc <ID_HOẶC_ĐƯỜNG_DẪN>
python3 "[09] ĐIỀU PHỐI VẬN HÀNH/storage_cli.py" doc-tep trich-xuat --nhanh "[05] SƯU TẦM" --gioi-han 25

# Phân tích nội dung, gợi ý tên từ siêu dữ liệu, tìm kiếm toàn văn
python3 "[09] ĐIỀU PHỐI VẬN HÀNH/storage_cli.py" phan-tich phan-tich --tai-len
python3 "[09] ĐIỀU PHỐI VẬN HÀNH/storage_cli.py" phan-tich goi-y-ten
python3 "[09] ĐIỀU PHỐI VẬN HÀNH/storage_cli.py" phan-tich tim-noi-dung --tu-khoa "triet hoc"

# Kiểm tra trạng thái GitHub & đồng bộ liên hoàn Drive ↔ Local ↔ GitHub
python3 "[09] ĐIỀU PHỐI VẬN HÀNH/storage_cli.py" github trang-thai
python3 "[09] ĐIỀU PHỐI VẬN HÀNH/storage_cli.py" github dong-bo-2-chieu --ghi-de-xung-dot --thuc-thi --dong-y

# Bảo trì định kì toàn diện
python3 "[09] ĐIỀU PHỐI VẬN HÀNH/storage_cli.py" bao-tri-dinh-ki --tang-cuong --tai-len
```

## 4. Nguyên tắc an toàn

- Mọi chương trình có tác động ghi **mặc định chạy thử (dry-run)**; chỉ thay đổi trên Drive hoặc GitHub khi có `--thuc-thi` (hoặc `--execute` ở `[04]`).
- **Không xóa vĩnh viễn**: tệp trùng, thư mục rỗng hoặc shortcut lỗi chỉ được *di chuyển* vào `[07] KIỂM TRA` kèm nhật kí để hoàn tác bằng `--hoan-tac`.
