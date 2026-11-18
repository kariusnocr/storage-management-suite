# TỔNG QUAN HỆ THỐNG — PHÂN TÍCH ÂM THANH (`[17] PHÂN TÍCH ÂM THANH`)

## 1. Mục đích & Chức năng
Chương trình **`audio_analyzer.py`** quản trị và kiểm toán chất lượng toàn bộ **1.410+ tệp âm thanh** (`.mp3`, `.m4a`, `.m4b`, `.wav`, `.flac`, `.aac`, `.ogg`) trong kho `[A] STORAGE`:

1. **Siêu dữ liệu & Thông số luồng (`phan-tich`, `doc`)**:
   - Đọc `duration_sec`, `bitrate_kbps`, `sample_rate_hz`, `channels`, `codec`, ảnh bìa nhúng (`has_cover_art`) qua `ffprobe` + bộ đọc **ID3v1/ID3v2 thuần Python** (hỗ trợ UTF-8/UTF-16/CP1258 tiếng Việt chuẩn xác).
2. **Phân tích Phổ & Chất lượng Tín hiệu**:
   - Đo chuẩn độ lớn phát sóng **EBU R128 (`integrated_lufs`, `lra_lu`)**, `mean_volume_db`, `max_volume_db` và khoảng lặng bằng `ffmpeg` (`volumedetect`, `ebur128`, `silencedetect`).
   - Tự động gắn cờ: `bi_re_tieng` (clipping `>= -0.1 dB`), `am_luong_nho` (`< -28 LUFS`), `nhieu_khoang_lang` (`>= 35%`), `am_thanh_rong_im_lang` (`>= 95%`), `du_doan_cat_nham_cuoi`, `bitrate_thap` (`< 64 kbps`), `am_thanh_hong`.
3. **Vân tay Âm học (`trung-am-thanh`)**:
   - Trích xuất đường bao năng lượng log-RMS 64 chiều (ở 8kHz mono qua pipe `ffmpeg`, tối đa 180 giây đầu) và chữ ký 64-bit để phát hiện hai tệp âm thanh cùng nội dung dù khác bitrate hoặc định dạng.
4. **Kiểm toán Chuỗi bài luyện nghe (`kiem-tra-chuoi`)**:
   - Quét trực tiếp trên `storage_index.json` phát hiện số bài/phần/track bị khuyết trong các thư mục chứng chỉ (`HSK`, `IELTS`) và bài giảng (`Ngữ Văn`).
5. **Chuẩn hóa tên Chuẩn V6 (`goi-y-ten`, `hoan-tac-ten`)**:
   - Đề xuất tên Chuẩn V6 từ thẻ `title`/`artist`/`album` cho các tệp tên mơ hồ (`Track 01`, `Audio_02`); hỗ trợ hoàn tác qua `media_rename_log.json`.

---

## 2. Cú pháp sử dụng nhanh

```bash
# 1. Kiểm toán siêu tốc toàn bộ lỗ hổng số thứ tự bài nghe từ chỉ mục (< 0,5 giây)
python3 "[09] ĐIỀU PHỐI VẬN HÀNH/storage_cli.py" phan-tich-am-thanh kiem-tra-chuoi

# 2. Tải & phân tích 15 tệp audio mẫu nhánh HSK rồi xuất báo cáo .md/.csv
python3 "[09] ĐIỀU PHỐI VẬN HÀNH/storage_cli.py" phan-tich-am-thanh phan-tich \
  --nhanh "[01] HỌC THUẬT/[04] CHỨNG CHỈ/[02] HSK" --tu-dong-doc --gioi-han 15

# 3. Rà soát tệp âm thanh trùng nội dung khác bitrate/định dạng
python3 "[09] ĐIỀU PHỐI VẬN HÀNH/storage_cli.py" phan-tich-am-thanh trung-am-thanh
```
