# TỔNG QUAN HỆ THỐNG — ĐỒNG BỘ GITHUB (`[15] ĐỒNG BỘ GITHUB`)

## 1. Mục đích & Chức năng
Chương trình **`github_sync.py`** kết nối bộ chương trình quản lý kho dữ liệu **`[A] STORAGE`** (`[00] TỔNG QUAN/[03] QUẢN LÝ` ↔ `/home/antigravity/storage_quan_ly`) với kho lưu trữ GitHub riêng tư **`kariusnocr/storage-management-suite`**:

1. **Kiểm tra trạng thái hợp nhất (`trang-thai`)**:
   - Hiển thị nhánh Git hiện tại, mã băm `HEAD`, danh sách tệp thay đổi, số commit lệch (`ahead`/`behind`).
   - Đối chiếu `SHA-256` giữa các tệp mô-đun cục bộ và `sync_manifest.json` của Google Drive `[03] QUẢN LÝ`.
   - Truy vấn 3 lần chạy **GitHub Actions CI** gần nhất qua `gh run list`.
2. **Kiểm toán bảo mật trước khi đẩy (`kiem-tra-bao-mat`)**:
   - Quét toàn bộ cây thư mục mã nguồn để chặn đứng nguy cơ lộ khóa riêng tư (`PRIVATE KEY`), token xác thực (`GitHub PAT/OAuth`, `Google OAuth`), tệp dữ liệu vận hành (`storage_index.json`, `shortcut_cache.json`) hoặc tệp vượt ngưỡng `10 MB`.
3. **Đẩy mã nguồn an toàn lên GitHub (`day-len`)**:
   - Tự động thực hiện quy trình 3 bước: **Kiểm tra bảo mật → Chạy bộ kiểm thử tự động `unittest` → Tạo commit & đẩy lên GitHub**.
   - Mặc định **chạy thử (dry-run)**; chỉ ghi và đẩy thật khi truyền `--thuc-thi`. Tự động chuyển sang nhánh tính năng và mở/gộp Pull Request nếu nhánh đích bật khóa bảo vệ.
4. **Kéo cập nhật từ GitHub (`keo-ve`)**:
   - Kiểm tra các commit mới trên `origin/main` (chạy thử) hoặc kéo về máy cục bộ (`--thuc-thi`).
5. **Đồng bộ liên hoàn 2 chiều Drive ↔ Local ↔ GitHub (`dong-bo-2-chieu`)**:
   - Phối hợp `[08] deploy_sync.py day-len` (cập nhật tại chỗ lên Google Drive `[00] TỔNG QUAN/[03] QUẢN LÝ`, giữ nguyên 100% File ID) và `github_sync.py day-len` (đẩy lên GitHub `kariusnocr/storage-management-suite`) chỉ bằng một lệnh duy nhất.
6. **Phát hành phiên bản (`phat-hanh`)**:
   - Tạo thẻ phiên bản (`v3.2.0`...) và GitHub Release qua `gh release create`.

---

## 2. Cú pháp sử dụng

```bash
# 1. Xem trạng thái Git, độ lệch Google Drive [03] QUẢN LÝ và kết quả GitHub Actions CI
python3 "[15] ĐỒNG BỘ GITHUB/github_sync.py" trang-thai

# 2. Quét kiểm tra bảo mật toàn bộ kho mã nguồn
python3 "[15] ĐỒNG BỘ GITHUB/github_sync.py" kiem-tra-bao-mat

# 3. Đẩy mã nguồn lên GitHub (chạy thử / thực thi)
python3 "[15] ĐỒNG BỘ GITHUB/github_sync.py" day-len
python3 "[15] ĐỒNG BỘ GITHUB/github_sync.py" day-len --thuc-thi --thong-diep "feat: nâng cấp bộ quản lý v3.2"

# 4. Đồng bộ liên hoàn cả Google Drive [03] QUẢN LÝ lẫn GitHub
python3 "[15] ĐỒNG BỘ GITHUB/github_sync.py" dong-bo-2-chieu --ghi-de-xung-dot --thuc-thi --dong-y

# 5. Phát hành phiên bản mới trên GitHub Releases
python3 "[15] ĐỒNG BỘ GITHUB/github_sync.py" phat-hanh --the v3.2.0 --thuc-thi
```
