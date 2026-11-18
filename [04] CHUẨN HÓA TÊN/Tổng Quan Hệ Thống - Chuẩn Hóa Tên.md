# TỔNG QUAN HỆ THỐNG — CHUẨN HÓA TÊN (v2.0)

- **Vị trí:** `[A] STORAGE/[00] TỔNG QUAN/[03] QUẢN LÝ/[04] CHUẨN HÓA TÊN`
- **Tệp mã nguồn:** `storage_toolkit.py`

## Nâng cấp v2.0

- **Bất biến 100% (`is_already_v6`):** bỏ qua hoàn toàn các tệp đã đạt Chuẩn V6, vùng `[03] QUẢN LÝ`, tệp Google gốc và bảng `Danh Mục Hệ Thống` (chấm dứt tình trạng tự đổi tên lại tệp đã chuẩn).
- Bảo vệ `Readme Hướng Dẫn Sử Dụng - ...` bằng regex `^\d{2,4}_\d{6}_.*Readme.*$`.
- Thư mục có nhiều `TongQuan.md` trùng được nhường cho `[06]` cách ly trước thay vì tự gắn `, Phần 01`.
- Chỉ ghi `storage_index.json` dạng compact một lần sau khi hoàn tất lô thực thi.

## Cách dùng

```bash
python3 "[04] CHUẨN HÓA TÊN/storage_toolkit.py" --plan
python3 "[04] CHUẨN HÓA TÊN/storage_toolkit.py" --plan --execute --dong-y
```
