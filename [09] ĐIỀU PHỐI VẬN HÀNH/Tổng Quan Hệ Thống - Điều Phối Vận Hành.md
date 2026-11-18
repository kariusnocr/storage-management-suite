# TỔNG QUAN HỆ THỐNG — ĐIỀU PHỐI VẬN HÀNH (v3.3)

- **Vị trí:** `[A] STORAGE/[00] TỔNG QUAN/[03] QUẢN LÝ/[09] ĐIỀU PHỐI VẬN HÀNH`
- **Tệp mã nguồn:** `storage_cli.py`

## Chức năng

Cung cấp điểm vào duy nhất (CLI) cho toàn bộ bộ chương trình `[01]`–`[18]`:

- Lệnh từng mô-đun:
  - `quet`: `[02] QUÉT CHỈ MỤC/storage_indexer.py`
  - `kiem-tra`: `[03] KIỂM TRA QUY ƯỚC/naming_auditor.py`
  - `chuan-hoa`: `[04] CHUẨN HÓA TÊN/storage_toolkit.py`
  - `danh-muc`: `[05] DANH MỤC HỆ THỐNG/sheet_engine.py`
  - `trung-lap`: `[06] RÀ SOÁT TRÙNG LẶP/dedup_scanner.py`
  - `bao-cao`: `[07] BÁO CÁO THỐNG KÊ/stats_reporter.py`
  - `trien-khai`: `[08] TRIỂN KHAI MÃ NGUỒN/deploy_sync.py`
  - `sao-chep-di-chuyen`: `[10] SAO CHÉP DI CHUYỂN/transfer_manager.py`
  - `nhap-du-lieu`: `[11] NHẬP DỮ LIỆU MỚI/data_ingestor.py`
  - `tra-cuu`: `[12] TRA CỨU VÀ KIỂM TOÁN/storage_inspector.py`
  - `doc-tep`: `[13] ĐỌC TỆP/file_reader.py`
  - `phan-tich`: `[14] PHÂN TÍCH NỘI DUNG/content_analyzer.py`
  - `github`: `[15] ĐỒNG BỘ GITHUB/github_sync.py`
  - `phan-tich-anh`: `[16] PHÂN TÍCH HÌNH ẢNH/image_analyzer.py`
  - `phan-tich-am-thanh`: `[17] PHÂN TÍCH ÂM THANH/audio_analyzer.py`
  - `phan-tich-video`: `[18] PHÂN TÍCH VIDEO/video_analyzer.py`
  - `kiem-thu`: Chạy toàn bộ kiểm thử tự động trong `[01] THƯ VIỆN LÕI/tests`
- Quy trình liên hoàn:
  - `quy-trinh-nhanh`: `[02] tăng cường` → `[03]` → `[04]` → `[05] --chi-thay-doi` → `[07]`.
  - `bao-tri-dinh-ki`: `[02]` → `[03]` → `[06]` → `[04]` → `[12] kiem-toan-tong-quan` → `[05]` → `[07]`.
- Toàn bộ lần chạy đều lưu log chi tiết tại `<STORAGE_DATA_DIR>/runs/`.

## Cách dùng

```bash
python3 "[09] ĐIỀU PHỐI VẬN HÀNH/storage_cli.py" kiem-thu
python3 "[09] ĐIỀU PHỐI VẬN HÀNH/storage_cli.py" sao-chep-di-chuyen di-chuyen --nguon "..." --dich "..."
python3 "[09] ĐIỀU PHỐI VẬN HÀNH/storage_cli.py" nhap-du-lieu --tu-khu-nhap
python3 "[09] ĐIỀU PHỐI VẬN HÀNH/storage_cli.py" tra-cuu tim-kiem --tu-khoa "Triết Học"
python3 "[09] ĐIỀU PHỐI VẬN HÀNH/storage_cli.py" doc-tep trich-xuat --nhanh "[05] SƯU TẦM" --gioi-han 25
python3 "[09] ĐIỀU PHỐI VẬN HÀNH/storage_cli.py" phan-tich phan-tich --tai-len
python3 "[09] ĐIỀU PHỐI VẬN HÀNH/storage_cli.py" phan-tich-anh phan-tich --nhanh "[01] HỌC THUẬT/[04] CHỨNG CHỈ/[01] IELTS" --tu-dong-doc --gioi-han 10 --ocr
python3 "[09] ĐIỀU PHỐI VẬN HÀNH/storage_cli.py" phan-tich-am-thanh kiem-tra-chuoi
python3 "[09] ĐIỀU PHỐI VẬN HÀNH/storage_cli.py" phan-tich-video kiem-tra-khoa-hoc
python3 "[09] ĐIỀU PHỐI VẬN HÀNH/storage_cli.py" github trang-thai
python3 "[09] ĐIỀU PHỐI VẬN HÀNH/storage_cli.py" github dong-bo-2-chieu --ghi-de-xung-dot --thuc-thi --dong-y
python3 "[09] ĐIỀU PHỐI VẬN HÀNH/storage_cli.py" quy-trinh-nhanh --thuc-thi --dong-y --tai-len
```
