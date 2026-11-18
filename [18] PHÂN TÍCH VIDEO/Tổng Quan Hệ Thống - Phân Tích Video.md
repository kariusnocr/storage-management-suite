# TỔNG QUAN HỆ THỐNG — PHÂN TÍCH VIDEO (`[18] PHÂN TÍCH VIDEO`)

## 1. Mục đích & Chức năng
Chương trình **`video_analyzer.py`** phụ trách kiểm toán, phân tích luồng kỹ thuật và nhận diện trùng lặp cho toàn bộ **615+ tệp video (`46,74 GB`)** trong kho `[A] STORAGE` (`.mp4`, `.ts`, `.mov`, `.mkv`, `.avi`, `.webm`):

1. **Kiểm toán khóa học siêu tốc trên chỉ mục (`kiem-tra-khoa-hoc`, `--chi-chi-muc`)**:
   - Quét trực tiếp `storage_index.json` không cần tải tệp lớn: thống kê phân bố khóa học, phát hiện tệp phát sóng `.ts` (`can_remux_mp4`), thư mục khóa học khuyết số bài giảng (`thieu_bai_trong_chuoi`), và tên dính liền không dấu kiểu AutoCAD (`ten_dinh_lien_khong_dau`).
2. **Phân tích luồng kỹ thuật & sức khỏe giải mã (`phan-tich`, `doc`)**:
   - Dùng `ffprobe` trích xuất codec video/audio, độ phân giải (`4K`, `1080p`, `720p`, `480p`, `SD_Thap`), FPS, bitrate, tỷ lệ khung hình, số luồng phụ đề và chia sẻ mô-đun `[17]` để kiểm tra mức âm lượng LUFS/khoảng lặng của track âm thanh.
   - Rút tối đa **5 khung hình tiêu biểu (Keyframes)** tại `8%`, `28%`, `50%`, `72%`, `90%` thời lượng bằng `ffmpeg` để xác minh giải mã thực tế, phát hiện `video_hong`, `video_loi_giai_ma`, `khong_co_am_thanh`, `do_phan_giai_thap`, `khung_hinh_dung`.
3. **OCR slide bài giảng & Contact Sheet (`--ocr`, `--contact-sheet`)**:
   - Chia sẻ trực tiếp `dHash`/`pHash 64-bit` và bộ OCR `tesseract` từ `[16]` để rút tiêu đề slide giảng dạy (`ocr_heading`), phục vụ tìm kiếm & đề xuất tên Chuẩn V6.
   - Khi bật `--contact-sheet`, ghép 6 khung hình đại diện thành ảnh lưới 3×2 kèm dấu thời gian tại `~/storage_data/reports/contact_sheets/`.
4. **Phát hiện video trùng đa chữ ký (`trung-video`)**:
   - Đối chiếu đồng thời độ lệch thời lượng (`<= max(3s, 3% duration)`) và tỷ lệ khớp `keyframe pHash` (`>= 60%`, `Hamming <= 8`), giúp tìm ra hai bản cùng video khác độ phân giải (`1080p` vs `480p`) hoặc `.ts` thừa cạnh `.mp4`; hỗ trợ cách ly bản kém hơn vào `[07] KIỂM TRA/[03] TỆP TRÙNG LẶP`.
5. **Kiểm soát băng thông an toàn tuyệt đối**:
   - Giới hạn mặc định `--max-mb 250`, `--gioi-han 15`, xóa tệp tải tạm ngay trong khối `finally` và lưu kết quả bền vững tại `~/storage_data/media_cache/video/`.

---

## 2. Cú pháp sử dụng nhanh

```bash
# 1. Kiểm toán nhanh toàn bộ 615 video khóa học từ chỉ mục (0 giây tải mạng)
python3 "[09] ĐIỀU PHỐI VẬN HÀNH/storage_cli.py" phan-tich-video kiem-tra-khoa-hoc

# 2. Phân tích 1 video cụ thể và xuất Contact Sheet + OCR slide
python3 "[09] ĐIỀU PHỐI VẬN HÀNH/storage_cli.py" phan-tich-video doc <ID_HOẶC_ĐƯỜNG_DẪN> --ocr --contact-sheet

# 3. Tải & phân tích sâu 5 video mẫu của một khóa học (tự xóa tạm ngay)
python3 "[09] ĐIỀU PHỐI VẬN HÀNH/storage_cli.py" phan-tich-video phan-tich \
  --nhanh "[05] SƯU TẦM/[03] KHOÁ HỌC/[07] CANVA PRO A TO Z" --tu-dong-doc --gioi-han 5 --ocr

# 4. Tìm video trùng lặp khác độ phân giải (chế độ chạy thử)
python3 "[09] ĐIỀU PHỐI VẬN HÀNH/storage_cli.py" phan-tich-video trung-video
```
