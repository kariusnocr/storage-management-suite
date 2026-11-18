# TỔNG QUAN HỆ THỐNG — PHÂN TÍCH HÌNH ẢNH (`[16] PHÂN TÍCH HÌNH ẢNH`)

## 1. Mục đích & Chức năng
Chương trình **`image_analyzer.py`** phụ trách đọc, đánh giá chất lượng và nhận diện trùng lặp trực quan cho toàn bộ tệp hình ảnh trong kho `[A] STORAGE` (`jpg`, `jpeg`, `png`, `webp`, `gif`, `bmp`, `tiff`, `heic`, `psd`, `cdr`):

1. **Thông số kỹ thuật & EXIF/GPS (`phan-tich`, `doc`)**:
   - Đọc kích thước, megapixels, tỷ lệ khung hình (`16:9`, `4:3`, `1:1`, `3:4`...), hệ màu, số khung hình ảnh động GIF/WebP, DPI, máy ảnh (`Make`/`Model`), ngày chụp (`DateTimeOriginal`) và phát hiện tọa độ GPS nhạy cảm (`co_gps_exif`).
2. **Chất lượng thị giác & Phân loại vai trò**:
   - Đo độ sắc nét bằng **phương sai toán tử Laplacian (`sharpness_laplacian`)** phát hiện ảnh mờ nhòe (`anh_mo`).
   - Kiểm tra độ sáng/tương phản (`anh_qua_toi`, `anh_chay_sang`, `anh_it_tuong_phan`), độ phân giải thấp (`anh_thap_phan_giai`), rút trích Top-3 **màu chủ đạo (HEX)** và phân loại vai trò (`slide_bai_giang`, `tai_lieu_chup_ocr`, `anh_man_hinh`, `anh_chup_camera`, `do_hoa_thiet_ke`).
3. **OCR văn bản trên ảnh (`--ocr`)**:
   - Tiền xử lý tương phản + phóng đại thông minh trước khi gọi `tesseract` (tự động dùng `vie+eng` nếu có gói tiếng Việt trong hệ thống hoặc `~/storage_data/tessdata`, fallback `eng`).
4. **Phát hiện ảnh trùng trực quan (`trung-anh`)**:
   - Tính song song **`dHash` 64-bit** và **`pHash` 64-bit (DCT-2D)** giúp phát hiện hai ảnh cùng nội dung dù khác định dạng, bị nén lại JPEG hay thay đổi độ phân giải; giữ bản nét/lớn nhất và hỗ trợ cách ly bản thừa vào `[07] KIỂM TRA/[03] TỆP TRÙNG LẶP`.
5. **Chuẩn hóa tên Chuẩn V6 (`goi-y-ten`, `hoan-tac-ten`) & Tìm kiếm (`tim-anh`)**:
   - Đề xuất tên Chuẩn V6 từ EXIF và dòng tiêu đề OCR cho các ảnh tên mơ hồ (`IMG_...`, `Screenshot...`); lưu nhật kí hoàn tác vào `media_rename_log.json`.

---

## 2. Cú pháp sử dụng nhanh

```bash
# 1. Phân tích nhanh 1 ảnh cục bộ hoặc trên Google Drive
python3 "[09] ĐIỀU PHỐI VẬN HÀNH/storage_cli.py" phan-tich-anh doc <ID_HOẶC_ĐƯỜNG_DẪN> --ocr

# 2. Tải mẫu 20 ảnh một nhánh vào bộ đệm media_cache/image và xuất báo cáo .md/.csv
python3 "[09] ĐIỀU PHỐI VẬN HÀNH/storage_cli.py" phan-tich-anh phan-tich \
  --nhanh "[01] HỌC THUẬT/[04] CHỨNG CHỈ/[01] IELTS" --tu-dong-doc --gioi-han 20 --ocr

# 3. Kiểm tra nhóm ảnh trùng trực quan (chế độ chạy thử)
python3 "[09] ĐIỀU PHỐI VẬN HÀNH/storage_cli.py" phan-tich-anh trung-anh --nguong-hamming 6

# 4. Tìm kiếm ảnh theo nội dung OCR hoặc cờ chất lượng
python3 "[09] ĐIỀU PHỐI VẬN HÀNH/storage_cli.py" phan-tich-anh tim-anh --co co_gps_exif
```
