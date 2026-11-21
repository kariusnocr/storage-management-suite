# TỔNG QUAN HỆ THỐNG — KARIUS ACADEMIC SYSTEM (KAS `v5.0.0`)

**Karius Academic System (KAS `v5.0.0`)** là nền tảng quản trị đa kho dữ liệu (Multi-Vault) hỗ trợ **mọi thư mục cục bộ trên máy tính** (ổ cứng ngoài, NAS, thư mục đồng bộ OneDrive/iCloud/Google Drive Desktop) và **mọi thư mục / Shared Drive trên Google Drive**, được phát triển tại kho mã nguồn GitHub **`kariusnocr/storage-management-suite`**.

---

## 1. Kiến trúc Gói Phần Mềm (`src/karius_academic_system/`)

Toàn bộ phần mềm được đóng gói chuẩn Python **`karius-academic-system`** với lệnh điều phối duy nhất **`kas`** (và ứng dụng giao diện **`kas ui`** / **`kas desktop`**):

| Phân hệ gói | Mô-đun chính | Lệnh `kas` | Vai trò |
| :--- | :--- | :--- | :--- |
| `core/` | `vaults`, `local_fs`, `config`, `drive_factory`, `drive_cli`, `drive_api`, `naming`, `catalog_spec`, `ocr` | `vault`, `auth`, `version` | Sổ đăng ký đa kho (`~/.config/kas/vaults.toml`), `LocalFSBackend`, Google Drive API OAuth 2.0 & `gdrive` CLI, tự nhận diện bố cục (`academic_v7` / `general`), Chuẩn V6, **Chuẩn Danh Mục V7**, OCR `vie+eng` |
| `store/` | `sqlite_store`, `legacy_compat` | `db`, `undo` | Cơ sở dữ liệu SQLite riêng theo từng kho (`kas.db`, WAL + FTS5 tìm kiếm `<20 ms`) và Sổ cái Hoàn tác Hợp nhất |
| `ops/` | `indexer`, `auditor`, `normalizer`, `catalog_engine`, `dedup`, `reporter`, `transfer`, `ingestor`, `inspector`, `doctor`, `watcher` | `quet`, `kiem-tra`, `chuan-hoa`, `danh-muc`, `danh-muc-chuan`, `trung-lap`, `bao-cao`, `sao-chep-di-chuyen`, `nhap-du-lieu`, `tra-cuu`, `doctor`, `watch` | Quản trị kho đa nguồn, tự động thích ứng kiểm toán theo chế độ kho (`general` / `academic_v7`), tinh gọn danh mục V7, dọn rác `MACOSX` |
| `media/` | `file_reader`, `content_analyzer`, `image_analyzer`, `audio_analyzer`, `video_analyzer` | `doc-tep`, `phan-tich`, `phan-tich-anh`, `phan-tich-am-thanh`, `phan-tich-video` | Đọc đa định dạng, TF-IDF/SimHash, EXIF/dHash/pHash/OCR `vie+eng`, ID3/EBU R128 LUFS, Contact Sheet 3×2 |
| `sync/` | `drive_deploy`, `github_sync` | `trien-khai`, `github` | Xuất bản tài liệu + gói cài đặt lên `[03] QUẢN LÝ` của bất kỳ kho KAS V7 nào, kiểm toán bảo mật, đồng bộ Git/GitHub |
| `cli/` & `web/` | `cli/main`, `cli/pipelines`, `web/app`, `web/desktop` | `quy-trinh-nhanh`, `bao-tri-dinh-ki`, `ui`, `desktop` | Pipeline in-process dùng chung ngữ cảnh, Web Dashboard & Desktop App chuyển kho tức thì (tương thích Windows 11 Smart App Control) |

---

## 2. Cơ chế Đa Kho (Multi-Vault) & Không Gắn Cứng ID Cá Nhân

- Mặc định khi cài mới, KAS **không chứa bất kỳ ID Google Drive cá nhân nào** (`kas_config.json` hoàn toàn trung lập).
- Mọi kho dữ liệu do người dùng kết nối được lưu trong **`~/.config/kas/vaults.toml`** và cô lập hoàn toàn chỉ mục/báo cáo/hoàn tác tại **`~/.local/share/kas/vaults/<slug>/`**.
- **Chế độ nhận diện bố cục thông minh (`auto`)**:
  - **`academic_v7`**: Tự kích hoạt khi kho có `[00] TỔNG QUAN` / `[07] KIỂM TRA` hoặc `≥ 50%` thư mục gốc dạng `[NN] ...` (kiểm toán đầy đủ Chuẩn V6 + Chuẩn Danh Mục V7).
  - **`general`**: Tự áp dụng cho mọi thư mục/kho Drive thông thường (kiểm toán trùng tên, rác `MACOSX`/`.DS_Store`, lỗi tên nghiêm trọng; không báo giả quy ước `[STT]`).
  - Có thể khởi tạo khung KAS V7 bất cứ lúc nào trên mọi kho bằng `kas vault init-structure --thuc-thi`.

---

## 3. Quy trình Vận hành Chuẩn

```bash
# Kết nối kho bất kỳ (thư mục máy tính hoặc link Google Drive)
kas vault add "Tài Liệu Học Tập" ~/Documents/HocTap
kas vault add "Kho Nghiên Cứu Drive" "https://drive.google.com/drive/folders/<FOLDER_ID>"
kas vault list                           # Xem danh sách kho & chuyển kho bằng `kas vault use <slug>`

# Vận hành trên kho đang kích hoạt (hoặc chỉ định nhanh qua `--kho <slug>`)
kas doctor                               # Kiểm tra công cụ, sổ kho, OCR vie+eng, backend & SQLite
kas quet --tang-cuong                    # Quét tăng cường vào kas.db (FTS5)
kas kiem-tra                             # Kiểm toán tự thích ứng (general hoặc Chuẩn V6 + V7)
kas danh-muc-chuan                       # Chạy thử tinh gọn & chuẩn hóa tên Danh Mục V7
kas trung-lap --don-rac-he-thong         # Rà soát trùng lặp & thư mục rác MACOSX
kas quy-trinh-nhanh                      # Chạy chuỗi bảo trì nhanh in-process (chạy thử)
kas desktop                              # Mở ứng dụng Desktop Karius Academic System (KAS)
```
