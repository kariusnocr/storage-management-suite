# TỔNG QUAN HỆ THỐNG — SAO CHÉP DI CHUYỂN (`[10] SAO CHÉP DI CHUYỂN`)

## 1. Mục đích & Chức năng
Chương trình **`transfer_manager.py`** cung cấp bộ công cụ sao chép, di chuyển và tạo shortcut an toàn, tuân thủ Chuẩn V6 cho kho dữ liệu **`[A] STORAGE`**:

- **Sao chép (`sao-chep`)**: Sao chép phía máy chủ (`server-side copy`) cho một tệp, nhiều tệp, hoặc **đệ quy toàn bộ cây thư mục** sang thư mục đích mà không cần tải xuống máy cục bộ.
- **Di chuyển (`di-chuyen`)**: Di chuyển tệp hoặc thư mục sang nhánh đích, tự động kiểm tra trước quyền `canMoveItemOutOfDrive,canEdit` bằng `stream_capabilities` để tách riêng các mục không đủ quyền (`KHONG_CO_QUYEN`).
- **Tạo Shortcut (`tao-shortcut`)**: Tạo shortcut chuẩn V6 tại thư mục đích trỏ về tệp/thư mục nguồn.
- **Thực thi theo kịch bản lô (`lo-kich-ban`)**: Đọc tệp kịch bản `.json` hoặc `.csv` để thực thi hàng trăm/nghìn lệnh chuyển đổi cấu trúc trong một lần chạy.
- **Tự động chuẩn hóa Chuẩn V6 & Cấp `[STT]`**:
  - `--chuan-hoa-ten`: Chuẩn hóa tên tệp sang `Tên Viết Hoa Đầu Mỗi Chữ Có Dấu - Thông Tin Bổ Sung.[đuôi]` dựa trên ngữ cảnh thư mục đích.
  - `--tu-danh-stt`: Tự động cấp số thứ tự `[STT]` kế tiếp chưa sử dụng khi sao chép/di chuyển thư mục vào nhánh đích.
  - Tự động phát hiện và bỏ qua tệp đã tồn tại ở thư mục đích (cùng tên chuẩn hóa và cùng dung lượng).
- **Hoàn tác an toàn (`hoan-tac`)**: Mọi lô thực thi đều được ghi vào `<STORAGE_DATA_DIR>/transfer_log.json` kèm `batch_id` để hoàn tác nguyên trạng (không xóa vĩnh viễn bất kỳ tệp nào).

---

## 2. Cú pháp sử dụng

```bash
# 1. Chạy thử sao chép tệp hoặc cả cây thư mục sang nhánh đích (kèm chuẩn hóa tên V6)
python3 "[10] SAO CHÉP DI CHUYỂN/transfer_manager.py" sao-chep \
  --nguon "[02] NGHIÊN CỨU" \
  --dich "[05] SƯU TẦM/[02] TÀI LIỆU" \
  --chuan-hoa-ten

# 2. Di chuyển tệp/thư mục thực tế lên Drive
python3 "[10] SAO CHÉP DI CHUYỂN/transfer_manager.py" di-chuyen \
  --nguon <ID_HOẶC_ĐƯỜNG_DẪN> \
  --dich "[05] SƯU TẦM/[01] SÁCH/[14] SỨC KHOẺ - Y HỌC" \
  --chuan-hoa-ten --thuc-thi --dong-y

# 3. Chạy theo kịch bản hàng loạt (.json hoặc .csv)
python3 "[10] SAO CHÉP DI CHUYỂN/transfer_manager.py" lo-kich-ban \
  --kich-ban /duong/dan/kich_ban.json --thuc-thi --dong-y

# 4. Xem lịch sử & hoàn tác lô gần nhất
python3 "[10] SAO CHÉP DI CHUYỂN/transfer_manager.py" lich-su
python3 "[10] SAO CHÉP DI CHUYỂN/transfer_manager.py" hoan-tac --thuc-thi --dong-y
```
