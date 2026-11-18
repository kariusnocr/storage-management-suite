# TỔNG QUAN HỆ THỐNG — KIỂM TRA QUY ƯỚC (v2.0)

- **Vị trí:** `[A] STORAGE/[00] TỔNG QUAN/[03] QUẢN LÝ/[03] KIỂM TRA QUY ƯỚC`
- **Tệp mã nguồn:** `naming_auditor.py`

## Quy tắc kiểm tra v2.0

- Sử dụng chung từ điển viết tắt `ACRONYMS_UPPER` và hàm `normalize_sheet_title()` từ `storage_core.py`.
- Loại bỏ cảnh báo giả với chữ không thuộc hệ Latin (`1. เม่นกับงู`), `(a+)`, `e-Business` và tách `TongQuan.md` thành mã `TEP_HE_THONG_CU`.
- `--sua-an-toan` chỉ sửa các lỗi cơ học an toàn (NFC, khoảng trắng, dấu phân cách `-`), nhường bảng `Danh Mục Hệ Thống` cho `[05] --sua-ten-bang` và `<Tên>_<Số>_<ChủĐề>` cho `[04]`.

## Cách dùng

```bash
python3 "[03] KIỂM TRA QUY ƯỚC/naming_auditor.py"
python3 "[03] KIỂM TRA QUY ƯỚC/naming_auditor.py" --sua-an-toan --thuc-thi --dong-y
python3 "[03] KIỂM TRA QUY ƯỚC/naming_auditor.py" --tai-len
```
