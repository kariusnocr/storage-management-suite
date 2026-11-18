# TỔNG QUAN HỆ THỐNG — PHÂN TÍCH NỘI DUNG (`[14] PHÂN TÍCH NỘI DUNG`)

## 1. Mục đích & Chức năng
Chương trình **`content_analyzer.py`** thực hiện phân tích sâu trên dữ liệu văn bản và siêu dữ liệu do `[13] ĐỌC TỆP` trích xuất:

1. **Phân tích toàn diện & Báo cáo chất lượng (`phan-tich`)**:
   - **Nhận diện ngôn ngữ**: Phân biệt Tiếng Việt (`vi`), Tiếng Anh (`en`), Tiếng Pháp (`fr`), Tiếng Tây Ban Nha (`es`), Tiếng Đức (`de`), Tiếng Trung (`zh`), Tiếng Nhật (`ja`), Tiếng Nga (`ru`) kèm độ tin cậy.
   - **Thống kê học thuật**: Số trang, số từ, số ký tự, thời gian đọc ước tính (phút) và 8 từ khóa/cụm từ đặc trưng nhất theo trọng số `TF-IDF`.
   - **Phân loại chủ đề Chuẩn V6**: Đối chiếu nội dung + tiêu đề + mục lục với 15 nhóm chuyên đề của kho để gợi ý nhánh đích và gắn cờ `lech_chu_de` nếu tệp đang nằm ở `[00] CHƯA PHÂN LOẠI` hoặc lệch hẳn chuyên đề.
   - **Xuất báo cáo**: Ghi báo cáo `Báo Cáo Phân Tích Nội Dung - Storage, <Ngày>.md` và `.csv` vào `<STORAGE_DATA_DIR>/reports/`; hỗ trợ `--tai-len` lên `[00] TỔNG QUAN/[02] NHẬT KÍ`.
2. **Đề xuất & Chuẩn hóa tên Chuẩn V6 từ siêu dữ liệu nội dung (`goi-y-ten`, `hoan-tac-ten`)**:
   - Phát hiện các tệp có tên mơ hồ (toàn chữ số, mã băm, `Untitled`, `Scan...`) hoặc thiếu phần `- Thông Tin Bổ Sung` và dựng tên `<Tiêu Đề> - <Tác Giả>.[đuôi]` từ siêu dữ liệu bên trong tệp.
   - Mặc định chạy thử; khi truyền `--thuc-thi --dong-y` sẽ đổi tên tại chỗ (giữ nguyên 100% ID), lưu nhật kí `content_rename_log.json` và hỗ trợ `hoan-tac-ten`.
3. **Phát hiện trùng nội dung & gần trùng ngữ nghĩa (`trung-noi-dung`)**:
   - Kết hợp băm `SHA-256` (trùng nội dung tuyệt đối kể cả khác tên) và chữ ký `SimHash 64-bit` trên 3-shingles (phát hiện hai ấn phẩm cùng nội dung nhưng khác định dạng như `.docx` vs `.pdf` vs `.epub` với khoảng cách Hamming ≤ 3).
4. **Tìm kiếm toàn văn trong bộ đệm nội dung (`tim-noi-dung`)**:
   - Tìm từ khóa (có dấu hoặc không dấu) hoặc `--regex` xuyên suốt toàn bộ văn bản đã trích xuất, lọc theo `--ngon-ngu`, `--co` và trả về đoạn trích ngữ cảnh.

---

## 2. Cú pháp sử dụng

```bash
# 1. Tự động trích xuất (nếu chưa có trong cache) và phân tích một nhánh
python3 "[14] PHÂN TÍCH NỘI DUNG/content_analyzer.py" phan-tich \
  --nhanh "[05] SƯU TẦM/[01] SÁCH/[14] SỨC KHOẺ - Y HỌC" \
  --tu-dong-doc --gioi-han 25

# 2. Xem gợi ý chuẩn hóa tên từ siêu dữ liệu nội dung (chạy thử / thực thi)
python3 "[14] PHÂN TÍCH NỘI DUNG/content_analyzer.py" goi-y-ten --nhanh "[05] SƯU TẦM"
python3 "[14] PHÂN TÍCH NỘI DUNG/content_analyzer.py" goi-y-ten --nhanh "[05] SƯU TẦM" --thuc-thi --dong-y

# 3. Rà soát các cặp tệp trùng hoặc gần trùng nội dung theo SimHash 64-bit
python3 "[14] PHÂN TÍCH NỘI DUNG/content_analyzer.py" trung-noi-dung --nguong-hamming 3

# 4. Tìm kiếm toàn văn trong nội dung đã trích xuất
python3 "[14] PHÂN TÍCH NỘI DUNG/content_analyzer.py" tim-noi-dung --tu-khoa "giai phau than kinh"
```
