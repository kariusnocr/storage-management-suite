# QUY ƯỚC ĐẶT TÊN & TINH GỌN DANH MỤC HỆ THỐNG — CHUẨN V7 (`v4.0.0`)

Tài liệu này bổ sung và chuẩn hóa chính thức hệ thống bảng Google Sheets **`Danh Mục Hệ Thống`** tập trung tại **`[A] STORAGE / [00] TỔNG QUAN / [01] DANH SÁCH`** (`1GqdqbI1yVPD3e-HAenW6WioSQZpPaRYz`).

---

## 1. Quy tắc Đặt tên Bảng Danh Mục (Zero-Collision V7)

### 1.1. Công thức chuẩn
```text
Danh Mục Hệ Thống - <Tên Chuẩn Hóa>[, <Ngữ Cảnh Phân Biệt>]
```

- **Bảng gốc toàn kho**:
  - Tại `[00] TỔNG QUAN`: `Danh Mục Hệ Thống - Storage`
  - Tại `[00] TỔNG QUAN / [01] DANH SÁCH`: `Danh Mục Hệ Thống - Storage, Bản Danh Sách`
- **Duy nhất một dấu phân cách `" - "`**:
  1. Bỏ tiền tố `[STT]` ở đầu tên thư mục (`[01] HỌC THUẬT` → `Học Thuật`).
  2. Khối mã định danh trong ngoặc vuông `[MÃ] TÊN` → chuyển thành **`MÃ: Tên`** (ví dụ: `[USSH] TRƯỜNG ĐH KHXH&NV` → `Danh Mục Hệ Thống - USSH: Trường ĐH KHXH&NV`, không tạo dấu `" - "` thứ hai).
  3. Cụm song song có gạch nối nội bộ `A - B` → chuyển thành dấu gạch ngang ngắn **`–`** (en-dash), ví dụ: `TÔN GIÁO - TÍN NGƯỠNG` → `Danh Mục Hệ Thống - Tôn Giáo – Tín Ngưỡng`.
  4. Tự động chèn khoảng trắng chuẩn quanh ngoặc đơn dính chữ (`Toán 12(CHƯƠNG-1)TỪ` → `Toán 12 (Chương 1) Từ`), loại bỏ phần mở rộng bị dính (`.PDF`, `- PDF`), và chuẩn hóa chữ viết tắt theo `acronyms_upper`.
- **Quy tắc chống trùng tên toàn kho (Disambiguation)**:
  - Nếu `<Tên Chuẩn Hóa>` thuộc nhóm tên chung (`Handout`, `Key`, `Slide`, `Tài Liệu`, `Bài Tập`, `Ôn Tập`, `Cấu Phần Sách`, `Chính Khóa`, `Ngoại Khoá`, `Tập 1..3`…) **hoặc** xuất hiện `≥ 2` lần trong toàn kho → tự động gắn thêm hậu tố `, <Ngữ Cảnh Cha Gần Nhất>` (tăng dần cấp cha cho tới khi **0 va chạm** trên toàn cây `[01] DANH SÁCH`).
  - Ví dụ:
    - `Danh Mục Hệ Thống - Chính Khóa, QH-2026-X-TR: K71 Triết Học`
    - `Danh Mục Hệ Thống - Cấu Phần Sách, Đạo – Trương Lập Văn`

---

## 2. Chính sách Tinh gọn Thông minh (Phương án 2)

Cấu hình mặc định tại `catalog_policy` trong `storage_config.json`:

| Cấp độ thư mục (`depth`) | Điều kiện lập bảng `Danh Mục Hệ Thống` riêng | Mục đích |
| :--- | :--- | :--- |
| **Cấp 0** (`[A] STORAGE`) | Luôn lập bảng | Toàn cảnh tổng kho |
| **Cấp 1–4** | Luôn lập bảng (trừ vùng loại trừ) | Bảo phủ 100% nhánh lớn, trường/khoa, học phần và tủ sách chính |
| **Cấp 5** | Lập bảng khi thư mục không rỗng (`≥ 1` mục con ngoài `[00] TỔNG QUAN`) | Tránh sinh bảng cho thư mục lá rỗng |
| **Cấp 6** | Thăng hạng lập bảng riêng khi có **`≥ 15` mục trực tiếp** | Bảo toàn các kho tài liệu lớn nằm ở tầng sâu |
| **Cấp 7+** | Không tách bảng riêng (hiển thị đầy đủ trong bảng cấp cha gần nhất) | Loại bỏ hơn `2.100` bảng lá vụn vặt, tăng tốc đồng bộ `5×` |
| **Danh sách cấm tuyệt đối** | `__MACOSX`, `MACOSX`, `.obsidian`, `.git`, `__pycache__`, `node_modules`, `tests` | Không bao giờ lập danh mục cho thư mục rác/kỹ thuật |

> Trên chỉ mục thực tế `[A] STORAGE` (`21-11-2026`), chính sách này tinh gọn từ **`2.739` bảng** xuống còn **`493` bảng chuẩn xác (`-82%`)** với **`0` trùng tên**.

---

## 3. Năm Mã Kiểm toán Danh Mục Tự động (`astorage kiem-tra`)

| Mức độ | Mã kiểm toán | Ý nghĩa |
| :--- | :--- | :--- |
| `LỖI` | `DANH_MUC_RAC_KY_THUAT` | Bảng danh mục sinh nhầm cho `MACOSX` hoặc vùng loại trừ |
| `CẢNH BÁO` | `DANH_MUC_MO_COI` | Bảng trong `[01] DANH SÁCH` không còn thư mục nguồn tương ứng |
| `CẢNH BÁO` | `DANH_MUC_TRUNG_TEN` | Từ 2 bảng trở lên trùng tên trên toàn cây danh mục |
| `CẢNH BÁO` | `DANH_MUC_SAI_TEN` | Tên bảng chưa khớp công thức Chuẩn Danh Mục V7 |
| `GỢI Ý` | `DANH_MUC_CO_THE_TINH_GON` | Bảng nằm ngoài ngưỡng Tinh gọn Thông minh V7 |

---

## 4. Lộ trình Chuyển đổi An toàn (Bảo toàn 100% ID & Có Hoàn tác)

```bash
# Bước 1: Xem trước kế hoạch chi tiết (chỉ đọc — lưu JSON trong ~/storage_data/reports/)
astorage danh-muc-chuan

# Bước 2a: Chỉ đổi tên chuẩn V7 tại chỗ (giữ nguyên File ID, chưa di chuyển bảng tinh gọn)
astorage danh-muc-chuan --chi-doi-ten --thuc-thi --dong-y

# Bước 2b: Hoặc áp dụng trọn gói (đổi tên tại chỗ + chuyển bảng tinh gọn/rác về [07] KIỂM TRA)
astorage danh-muc-chuan --thuc-thi --dong-y

# Bước 3: Hoàn tác toàn bộ lô chỉ bằng 1 lệnh nếu cần
astorage undo list
astorage undo run <batch_id> --thuc-thi --dong-y
```
