# TỔNG QUAN HỆ THỐNG — THƯ VIỆN LÕI (v3.1)

- **Vị trí:** `[A] STORAGE/[00] TỔNG QUAN/[03] QUẢN LÝ/[01] THƯ VIỆN LÕI`
- **Thành phần:**
  - `storage_core.py` *(module lõi dùng chung)*
  - `storage_config.json` *(cấu hình kho, viết tắt `ACRONYMS_UPPER`, khu cách ly `[07] KIỂM TRA`, khu nhập `[04] NHẬP DỮ LIỆU`, ngưỡng trùng lặp & quét tăng cường)*
  - `tests/test_storage_suite.py` *(bộ kiểm thử tự động ngoại tuyến bằng `unittest` — 21 bài kiểm thử cho toàn bộ `[01]`–`[14]`)*

## Tính năng v3.1

1. **Siêu tăng tốc CLI `gdrive` (`stream_ls`, `stream_info`, `stream_capabilities`):** Gộp hàng chục/hàng trăm ID thư mục hoặc tệp vào một tiến trình `gdrive` với `--concurrency 32` và `--format jsonl`, giúp giảm 98% chi phí khởi tạo tiến trình, kèm `Drive.copy()`, `Drive.batch_copy()`, `Drive.create_shortcut()`, và phân trang cửa sổ thời gian cho `Drive.search()`.
2. **Hỗ trợ khu cách ly & tiếp nhận `[07] KIỂM TRA` + bộ đệm nội dung `[13]`/`[14]`:** `is_quarantine_path()`, `quarantine_root_id()`, `ingest_folder_id()`, `content_cache_dir()`, `content_rename_log_path()`, `extract_drive_id()`, `next_available_stt()`.
3. **Chuẩn V6 chính xác hơn:** miễn chữ không phân biệt hoa/thường (tiếng Thái/Hán/Ả Rập), bảo vệ cụm `Tử Vi` (không làm hỏng từ La-tinh `tu vi`) và nguyên âm tiếng Tây Ban Nha có dấu (`é`, `ó`, `í`, `á`, `ú`, `ñ`), bổ sung giới từ Tây Ban Nha (`y`, `del`, `las`, `los`, `al`, `con`, `en`, `para`, `por`).

## Kiểm tra nhanh

```bash
python3 "[01] THƯ VIỆN LÕI/storage_core.py"
python3 -m unittest discover -s "[01] THƯ VIỆN LÕI/tests" -v
```
