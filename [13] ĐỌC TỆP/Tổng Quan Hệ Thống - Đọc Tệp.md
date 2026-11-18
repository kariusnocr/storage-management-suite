# TỔNG QUAN HỆ THỐNG — ĐỌC TỆP (`[13] ĐỌC TỆP`)

## 1. Mục đích & Chức năng
Chương trình **`file_reader.py`** đóng vai trò là tầng đọc tệp đa định dạng và trích xuất văn bản, siêu dữ liệu, thông số kỹ thuật cho kho dữ liệu **`[A] STORAGE`**:

1. **Đọc tức thì 1 tệp (`doc`)**:
   - Chấp nhận ID Google Drive, URL Google Drive hoặc đường dẫn tệp cục bộ.
   - Trích xuất và hiển thị: định dạng thực tế theo *magic bytes*, băm `SHA-256`, siêu dữ liệu (`title`, `author`, `subject`, `publisher`, `isbn`, `language`, `created`...), thống kê (`char_count`, `word_count`, `line_count`, `pages`/`slides`/`duration_sec`), dàn ý/mục lục (`outline`) và đoạn trích văn bản.
2. **Trích xuất theo lô có kiểm soát & Bộ đệm bền vững (`trich-xuat`)**:
   - Lọc theo nhánh (`--nhanh`), định dạng (`--dinh-dang pdf,epub,docx`), giới hạn dung lượng mỗi tệp (`--max-mb`, mặc định `50 MB`), giới hạn số lượng tệp mỗi lô (`--gioi-han`) và chạy đa luồng (`--luong`).
   - Lưu kết quả vào `<STORAGE_DATA_DIR>/content_cache/records/<id>.json` và `text/<id>.txt` theo khóa `(id, modifiedTime)` — các lần chạy tiếp theo không phải tải lại tệp chưa thay đổi. Tệp tạm sau khi tải về được xóa ngay lập tức.
3. **Đa định dạng & Kiểm tra toàn vẹn kỹ thuật**:
   - **Tài liệu & sách**: `PDF` (`pdfinfo` + `pdftotext` + bộ đọc dự phòng thuần Python + OCR `tesseract` khi bật `--ocr`), `DOCX`, `PPTX`, `XLSX` (`zipfile` + XML), `EPUB`, `OPF`, `MOBI/AZW3/PRC` (PalmDB + EXTH + giải nén PalmDOC LZ77), `DOC/XLS/PPT` (OLE2), `MD`, `TXT`, `CSV/TSV`, `HTML`, `JSON`, `PY/TS/JS/SH`.
   - **Tệp Google gốc**: Google Docs (`md`), Google Sheets (`csv`), Google Slides (`txt`) qua `gdrive readonly export`.
   - **Đa phương tiện & Tệp nén**: Ảnh `JPG/PNG/WEBP/GIF` (`Pillow` EXIF), Âm thanh/Video `MP3/MP4/MOV/TS` (`ffprobe`), Tệp nén `ZIP/RAR/7Z` (`zipfile` / `7z l -slt` kèm kiểm tra mật khẩu và `--kiem-tra-sau` kiểm tra CRC).
   - Tự động gắn cờ: `can_ocr`, `co_mat_khau`, `tep_hong`, `tep_rong`, `sai_khop_dinh_dang`, `qua_dung_luong`.

---

## 2. Cú pháp sử dụng

```bash
# 1. Đọc chi tiết 1 tệp theo ID Google Drive hoặc đường dẫn cục bộ
python3 "[13] ĐỌC TỆP/file_reader.py" doc <ID_HOẶC_URL_HOẶC_ĐƯỜNG_DẪN>

# 2. Trích xuất theo lô một nhánh cụ thể vào bộ đệm content_cache
python3 "[13] ĐỌC TỆP/file_reader.py" trich-xuat \
  --nhanh "[05] SƯU TẦM/[01] SÁCH/[14] SỨC KHOẺ - Y HỌC" \
  --dinh-dang epub,pdf,docx --max-mb 30 --gioi-han 25 --luong 4

# 3. Xem thống kê độ phủ bộ đệm trích xuất
python3 "[13] ĐỌC TỆP/file_reader.py" thong-ke
```
