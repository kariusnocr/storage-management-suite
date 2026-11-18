# TỔNG QUAN HỆ THỐNG — DANH MỤC HỆ THỐNG (v2.0)

- **Vị trí:** `[A] STORAGE/[00] TỔNG QUAN/[03] QUẢN LÝ/[05] DANH MỤC HỆ THỐNG`
- **Tệp mã nguồn:**
  - `sheet_engine.py` *(động cơ chính v2.0)*
  - `sheet_updater.py` *(vỏ bọc tương thích giữ File ID cũ, gọi trực tiếp `sheet_engine`)*

## Nâng cấp v2.0

- Bổ sung **tab thứ 2 `Thống Kê Nhanh`** trong tệp `.xlsx` (KPI tổng quan, phân bố theo cấp độ & nhóm định dạng).
- **`--chi-thay-doi`:** băm chữ ký SHA-256 cây con (`sheets_sync_state.json`) và đối chiếu ảnh chụp trước để chỉ cập nhật các bảng có biến động ở mọi độ sâu `0..13`.
- **`--sua-ten-bang`:** chuẩn hóa tên bảng `Danh Mục Hệ Thống - ...` theo `storage_core.normalize_sheet_title()` (bỏ `.pdf`, `_`, sửa viết tắt `THPTQG`, `KHXH&NV`, `GDKT&PL`, `Vĩ Đại`/`Hành Vi`).

## Cách dùng

```bash
# Chạy thử kiểm tra các bảng cần cập nhật/tạo/đổi tên
python3 "[05] DANH MỤC HỆ THỐNG/sheet_engine.py" --chi-thay-doi --sua-ten-bang --tao-moi

# Thực thi ghi lên Drive (giữ nguyên ID/URL mọi bảng hiện có)
python3 "[05] DANH MỤC HỆ THỐNG/sheet_engine.py" --chi-thay-doi --sua-ten-bang --tao-moi --thuc-thi --dong-y

# Xuất riêng bảng của một nhánh ra tệp .xlsx trên máy
python3 "[05] DANH MỤC HỆ THỐNG/sheet_engine.py" --xuat-cuc-bo "[03] SÁNG TÁC"
```
