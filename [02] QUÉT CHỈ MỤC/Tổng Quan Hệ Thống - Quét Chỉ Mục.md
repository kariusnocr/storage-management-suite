# TỔNG QUAN HỆ THỐNG — QUÉT CHỈ MỤC (v3.0)

- **Vị trí:** `[A] STORAGE/[00] TỔNG QUAN/[03] QUẢN LÝ/[02] QUÉT CHỈ MỤC`
- **Tệp mã nguồn:** `storage_indexer.py`
- **Chế độ:** Chỉ đọc, không thay đổi dữ liệu trên Drive.

## Nâng cấp v3.0

- **`--tang-cuong`:** gọi `gdrive readonly search --modified-after` để chỉ quét lại những thư mục thực sự có biến động (tự fallback về quét toàn kho nếu vượt ngưỡng).
- **`--kem-sieu-du-lieu`:** gọi `gdrive readonly stream info` thu thập tăng cường ngày tạo (`createdTime`), chủ sở hữu, trạng thái chia sẻ & mô tả của toàn bộ thư mục vào `folder_metadata.json`.
- **`--chi-sieu-du-lieu`:** chỉ cập nhật siêu dữ liệu thư mục & shortcut dựa trên `storage_index.json` hiện có.
- **`--kem-shortcut`:** làm mới bộ đệm `shortcut_cache.json` theo lô bằng `stream info` (kèm siêu dữ liệu & trạng thái đích).

## Cách dùng

```bash
# Quét tăng cường + siêu dữ liệu thư mục + shortcut
python3 "[02] QUÉT CHỈ MỤC/storage_indexer.py" --tang-cuong --kem-sieu-du-lieu --kem-shortcut

# Chỉ thu thập siêu dữ liệu thư mục & shortcut từ chỉ mục hiện có
python3 "[02] QUÉT CHỈ MỤC/storage_indexer.py" --chi-sieu-du-lieu --kem-shortcut --luong 25

# Quét toàn kho (24 luồng) kèm toàn bộ siêu dữ liệu
python3 "[02] QUÉT CHỈ MỤC/storage_indexer.py" --toan-bo --luong 24 --kem-sieu-du-lieu --kem-shortcut
```
