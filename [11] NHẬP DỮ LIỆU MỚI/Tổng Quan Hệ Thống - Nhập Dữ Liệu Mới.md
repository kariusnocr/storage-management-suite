# TỔNG QUAN HỆ THỐNG — NHẬP DỮ LIỆU MỚI (`[11] NHẬP DỮ LIỆU MỚI`)

## 1. Mục đích & Chức năng
Chương trình **`data_ingestor.py`** quản lý toàn bộ quy trình tiếp nhận, lọc trùng, phân loại chủ đề và chuẩn hóa Chuẩn V6 cho dữ liệu mới đưa vào kho **`[A] STORAGE`**:

1. **Tiếp nhận từ khu vực chờ `[07] KIỂM TRA/[04] NHẬP DỮ LIỆU` (`--tu-khu-nhap`)**:
   - Tự động phát hiện các **Shortcut trỏ tới tệp hoặc thư mục bên ngoài kho** (ví dụ: shortcut `Sách Ngành Y học` trỏ tới thư mục của chủ sở hữu khác).
   - Đệ quy toàn bộ cây thư mục đích của shortcut và thực hiện **sao chép phía máy chủ (`server-side copy`)** để biến thành tệp thật thuộc quyền sở hữu của kho `[A] STORAGE`.
   - Sau khi sao chép hoàn tất, tự động chuyển shortcut gốc sang `[07] KIỂM TRA/[02] SHORTCUT ĐÃ SAO CHÉP`.
2. **Tiếp nhận từ ID/URL Google Drive bất kỳ (`--nguon-drive`)** hoặc **từ máy cục bộ (`--nguon-cuc-bo`)**.
3. **Chống trùng lặp toàn kho (`TRUNG_TOAN_KHO`)**:
   - Đối chiếu tên chuẩn hóa và kích thước của từng tệp nguồn với toàn bộ `storage_index.json` trước khi nhập; tự động bỏ qua nếu kho đã có sẵn ấn phẩm/tài liệu đó.
4. **Định tuyến chủ đề tự động & Chuẩn hóa Chuẩn V6**:
   - Tự động gợi ý nhánh đích phù hợp (`[05] SƯU TẦM/[01] SÁCH/[14] SỨC KHOẺ - Y HỌC`, `[01] TRIẾT HỌC`, `[05] TÂM LÝ HỌC`, `[06] HUYỀN HỌC`, v.v.) hoặc nhận nhánh tường minh qua `--dich`.
   - Tự động chuẩn hóa tên tệp sang `Tên Viết Hoa Đầu Mỗi Chữ Có Dấu - Thông Tin Bổ Sung.[đuôi]` và tên thư mục sang `[STT] TÊN IN HOA CÓ DẤU`.
   - Tự động khởi tạo `[00] TỔNG QUAN` + `Tổng Quan Hệ Thống - <Tên Thư Mục>.md` cho thư mục chuyên đề mới.

---

## 2. Cú pháp sử dụng

```bash
# 1. Chạy thử quét khu tiếp nhận [07] KIỂM TRA/[04] NHẬP DỮ LIỆU
python3 "[11] NHẬP DỮ LIỆU MỚI/data_ingestor.py" --tu-khu-nhap

# 2. Thực thi nhập dữ liệu từ khu [04] NHẬP DỮ LIỆU vào nhánh đích tự động
python3 "[11] NHẬP DỮ LIỆU MỚI/data_ingestor.py" --tu-khu-nhap --thuc-thi --dong-y --tai-len

# 3. Nhập từ một thư mục/tệp Google Drive ngoài vào nhánh chỉ định
python3 "[11] NHẬP DỮ LIỆU MỚI/data_ingestor.py" \
  --nguon-drive "https://drive.google.com/drive/folders/1lDvvcRAV3Kh5XaAyzQ8dTcH07Xv6zDZe" \
  --dich "[05] SƯU TẦM/[01] SÁCH/[14] SỨC KHOẺ - Y HỌC" \
  --thuc-thi --dong-y

# 4. Tải lên và chuẩn hóa dữ liệu từ máy cục bộ
python3 "[11] NHẬP DỮ LIỆU MỚI/data_ingestor.py" \
  --nguon-cuc-bo /duong/dan/thu_muc_moi \
  --dich "[05] SƯU TẦM/[02] TÀI LIỆU" \
  --thuc-thi --dong-y
```
