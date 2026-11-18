# TỔNG QUAN HỆ THỐNG — BÁO CÁO THỐNG KÊ (v2.0)

- **Vị trí:** `[A] STORAGE/[00] TỔNG QUAN/[03] QUẢN LÝ/[07] BÁO CÁO THỐNG KÊ`
- **Tệp mã nguồn:** `stats_reporter.py`

## Đầu ra

1. `Báo Cáo Thống Kê Kho - Storage, DD-MM-YYYY.md`: thống kê theo nhánh cấp 1/2, nhóm định dạng, top tệp/thư mục nặng, cập nhật gần đây kèm **Chỉ số Sức khỏe Kho (Health Score 0–100)** và xu hướng snapshot.
2. `Nhật Kí Biến Động Kho - Storage, DD-MM-YYYY.md`: tóm tắt thêm/mất/đổi tên/di chuyển giữa 2 ảnh chụp chỉ mục.
3. `Nhật Kí Biến Động Kho - Storage, DD-MM-YYYY.csv`: **toàn bộ chi tiết biến động (không giới hạn 300 dòng)**.

## Cách dùng

```bash
python3 "[07] BÁO CÁO THỐNG KÊ/stats_reporter.py"
python3 "[07] BÁO CÁO THỐNG KÊ/stats_reporter.py" --tai-len
```
