# TỔNG QUAN HỆ THỐNG — DANH MỤC HỆ THỐNG (v3.1)

- **Vị trí:** `[A] STORAGE/[00] TỔNG QUAN/[03] QUẢN LÝ/[05] DANH MỤC HỆ THỐNG`
- **Cây danh mục tập trung:** `[A] STORAGE/[00] TỔNG QUAN/[01] DANH SÁCH/<đường_dẫn_tương_đối>` (`1GqdqbI1yVPD3e-HAenW6WioSQZpPaRYz`)
- **Tệp mã nguồn:**
  - `sheet_engine.py` *(động cơ chính v3.1)*
  - `sheet_updater.py` *(vỏ bọc tương thích giữ File ID cũ, gọi trực tiếp `sheet_engine`)*

## Nâng cấp v3.0 – v3.1

- **Cây thư mục danh mục đệ quy tập trung (`v3.1` — `--gom-ve-danh-sach`):** toàn bộ `2.738` bảng `Danh Mục Hệ Thống - <Tên Thư Mục>` của các nhánh `[01]..[07]` được gom về cây thư mục phản chiếu 1:1 bên trong `[A] STORAGE/[00] TỔNG QUAN/[01] DANH SÁCH` (chỉ thành viên có quyền truy cập `[A] STORAGE / [00] TỔNG QUAN` mới nhìn thấy các tệp danh mục; người xem liên kết công khai ở các nhánh con không còn thấy bảng danh mục hệ thống).
- **Tab 1 `Danh Mục Hệ Thống` (17 cột):** bổ sung `Định Dạng`, `Thông Tin Bổ Sung` (tách từ Chuẩn V6 hoặc đích Shortcut), **thống kê cộng dồn trên từng dòng Thư mục** (`Số Thư Mục Con`, `Số Tệp Tin`, `Dung Lượng`), cột `Dung Lượng (Byte)` chuẩn số để sắp xếp, kèm `Ngày Tạo`, `Chủ Sở Hữu`, `Chia Sẻ & Quyền`.
- **Tab 2 `Thống Kê & Siêu Dữ Liệu`:** Thẻ siêu dữ liệu Drive API của thư mục gốc (kèm đường dẫn & liên kết tới thư mục lưu bảng trong `[01] DANH SÁCH`), KPI tách bạch **Nội dung vs Hệ thống `[00] TỔNG QUAN`**, Phân bố cấp độ (`=SUM`), Nhóm định dạng (`=SUM`/`%`), Top 15 phần mở rộng, Top 15 tệp nặng nhất & Top 15 tệp cập nhật gần nhất.
- **Tab 3 `Thư Mục Con Trực Tiếp`:** đối chiếu trực tiếp toàn bộ thư mục con kế tiếp, dòng tệp trực tiếp và tổng toàn nhánh dùng công thức `=SUM`/`=COUNT`/`=IF`.
- **Triển khai linh hoạt:** `--gom-ve-danh-sach`, `--chi-thay-doi`, `--tiep-tuc`, `--do-sau-tu`/`--do-sau`, `--sua-ten-bang`, tối ưu cây cộng dồn $O(N)$ (`precompute_tree_rollup`).

## Cách dùng

```bash
# Tạo cây thư mục gương đệ quy và gom toàn bộ bảng Danh Mục Hệ Thống về [00] TỔNG QUAN/[01] DANH SÁCH
python3 "[05] DANH MỤC HỆ THỐNG/sheet_engine.py" --gom-ve-danh-sach --thuc-thi --dong-y --luong 24

# Chạy thử kiểm tra các bảng cần cập nhật/tạo/đổi tên
python3 "[05] DANH MỤC HỆ THỐNG/sheet_engine.py" --chi-thay-doi --sua-ten-bang --tao-moi

# Thực thi nâng cấp các bảng trọng yếu cấp 0..2 trước
python3 "[05] DANH MỤC HỆ THỐNG/sheet_engine.py" --do-sau 2 --toan-bo --sua-ten-bang --tao-moi --thuc-thi --dong-y

# Tiếp tục phần còn lại ở cấp 3..99 (có checkpoint sheets_sync_state.json)
python3 "[05] DANH MỤC HỆ THỐNG/sheet_engine.py" --do-sau-tu 3 --do-sau 99 --tiep-tuc --sua-ten-bang --tao-moi --thuc-thi --dong-y

# Xuất riêng bảng của một nhánh ra tệp .xlsx trên máy
python3 "[05] DANH MỤC HỆ THỐNG/sheet_engine.py" --xuat-cuc-bo "[05] SƯU TẦM"
```

