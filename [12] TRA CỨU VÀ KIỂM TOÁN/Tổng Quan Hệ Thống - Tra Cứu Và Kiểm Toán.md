# TỔNG QUAN HỆ THỐNG — TRA CỨU VÀ KIỂM TOÁN (`[12] TRA CỨU VÀ KIỂM TOÁN`)

## 1. Mục đích & Chức năng
Chương trình **`storage_inspector.py`** cung cấp bộ công cụ tra cứu tức thì và kiểm toán cấu trúc chuyên sâu cho kho dữ liệu **`[A] STORAGE`**:

1. **Tra cứu tức thì (`tim-kiem`)**:
   - Tìm kiếm dưới `0,2 giây` trên toàn bộ chỉ mục `storage_index.json` theo từ khóa tiếng Việt (có dấu hoặc không dấu), biểu thức chính quy (`--regex`), ID Google Drive (`--id`), nhánh (`--nhanh`), phân loại (`folder`, `file`, `shortcut`, `sheet`, `doc`), phần mở rộng (`--duoi`), khoảng dung lượng (`--min-mb`, `--max-mb`) và ngày cập nhật (`--tu-ngay`).
2. **Kiểm toán & Bù đắp bộ 3 `[00] TỔNG QUAN` (`kiem-toan-tong-quan`)**:
   - Kiểm tra mọi thư mục trong kho đã có đủ 3 thành phần quản trị chuẩn chưa:
     1. Thư mục con `[00] TỔNG QUAN`
     2. Tệp mô tả `Tổng Quan Hệ Thống - <Tên Thư Mục>.md`
     3. Bảng Google Sheets `Danh Mục Hệ Thống - <Tên Thư Mục>`
   - Tùy chọn `--bu-dap --thuc-thi` tự động tạo thư mục `[00] TỔNG QUAN` và sinh tệp `Tổng Quan Hệ Thống - <Tên Thư Mục>.md` cho các thư mục chuyên đề mới.
3. **Kiểm toán quyền (`kiem-toan-quyen`)**:
   - Sử dụng `gdrive readonly stream capabilities` để phát hiện nhanh các tệp/thư mục thuộc chủ sở hữu ngoài không có quyền di chuyển/chỉnh sửa (`canMoveItemOutOfDrive=False`, `canEdit=False`).
4. **Dọn thư mục rỗng an toàn (`don-thu-muc-rong`)**:
   - Quét *bottom-up* phát hiện các thư mục rỗng hoặc chỉ chứa thư mục con rỗng, và di chuyển an toàn về `[07] KIỂM TRA/[05] THƯ MỤC RỖNG` khi bật `--thuc-thi`.

---

## 2. Cú pháp sử dụng

```bash
# 1. Tìm kiếm nhanh ấn phẩm theo từ khóa (có hoặc không dấu) và đuôi tệp
python3 "[12] TRA CỨU VÀ KIỂM TOÁN/storage_inspector.py" tim-kiem \
  --tu-khoa "giai phau" --duoi pdf,epub

# 2. Kiểm toán và tự động bù đắp [00] TỔNG QUAN + Tổng Quan Hệ Thống - *.md còn thiếu
python3 "[12] TRA CỨU VÀ KIỂM TOÁN/storage_inspector.py" kiem-toan-tong-quan --bu-dap
python3 "[12] TRA CỨU VÀ KIỂM TOÁN/storage_inspector.py" kiem-toan-tong-quan --bu-dap --thuc-thi --dong-y

# 3. Kiểm toán quyền di chuyển/chỉnh sửa trên một nhánh
python3 "[12] TRA CỨU VÀ KIỂM TOÁN/storage_inspector.py" kiem-toan-quyen --nhanh "[05] SƯU TẦM"

# 4. Rà soát và cách ly các thư mục rỗng
python3 "[12] TRA CỨU VÀ KIỂM TOÁN/storage_inspector.py" don-thu-muc-rong
```
