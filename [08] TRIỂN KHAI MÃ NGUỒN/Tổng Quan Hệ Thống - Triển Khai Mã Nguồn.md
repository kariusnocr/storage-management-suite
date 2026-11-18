# TỔNG QUAN HỆ THỐNG — TRIỂN KHAI MÃ NGUỒN (v2.0)

- **Vị trí:** `[A] STORAGE/[00] TỔNG QUAN/[03] QUẢN LÝ/[08] TRIỂN KHAI MÃ NGUỒN`
- **Tệp mã nguồn:** `deploy_sync.py`

## Chức năng v2.0

- `danh-sach`: xem cấu trúc `[03] QUẢN LÝ` hiện tại trên Google Drive.
- `tai-ve`: tải toàn bộ `[03] QUẢN LÝ` về máy và ghi `sync_manifest.json`.
- `day-len`: đồng bộ bộ mã từ máy lên `[03] QUẢN LÝ`:
  - Tự đổi tên tại chỗ (`LEGACY_FILE_RENAMES`) các tệp cũ sang `snake_case`, giữ nguyên 100% File ID.
  - Bỏ qua tệp có SHA-256 không đổi (dùng `--ep-buoc` nếu muốn ép ghi đè).
  - Cảnh báo xung đột nếu bản trên Drive mới hơn `sync_manifest.json` (`--ghi-de-xung-dot` để ghi đè có chủ đích).
  - `--don-tep-du`: cách ly tệp thừa trên Drive về `[99] KIỂM TRA` (không xóa).

## Cách dùng

```bash
python3 "[08] TRIỂN KHAI MÃ NGUỒN/deploy_sync.py" danh-sach
python3 "[08] TRIỂN KHAI MÃ NGUỒN/deploy_sync.py" day-len --thu-muc ~/storage_quan_ly
python3 "[08] TRIỂN KHAI MÃ NGUỒN/deploy_sync.py" day-len --thu-muc ~/storage_quan_ly --thuc-thi --dong-y
```
