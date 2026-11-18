# TỔNG QUAN HỆ THỐNG — QUÉT CHỈ MỤC (v2.0)

- **Vị trí:** `[A] STORAGE/[00] TỔNG QUAN/[03] QUẢN LÝ/[02] QUÉT CHỈ MỤC`
- **Tệp mã nguồn:** `storage_indexer.py`
- **Chế độ:** Chỉ đọc, không thay đổi dữ liệu trên Drive.

## Nâng cấp v2.0

- **`--tang-cuong`:** gọi `gdrive readonly search --modified-after` để chỉ quét lại những thư mục thực sự có biến động (nhanh gấp 15–30×; tự fallback về quét toàn kho nếu biến động > ngưỡng).
- **`--kem-shortcut`:** cập nhật bộ đệm `shortcut_cache.json` theo `modifiedTime` để `[06]` kiểm tra shortcut tức thì.

## Cách dùng

```bash
# Quét tăng cường hằng ngày (vài giây) + làm mới cache shortcut
python3 "[02] QUÉT CHỈ MỤC/storage_indexer.py" --tang-cuong --kem-shortcut

# Quét toàn kho (24 luồng)
python3 "[02] QUÉT CHỈ MỤC/storage_indexer.py" --toan-bo --luong 24 --kem-shortcut
```
