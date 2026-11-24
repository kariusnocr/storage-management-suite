# HƯỚNG DẪN CÀI ĐẶT & SỬ DỤNG — KARIUS ACADEMIC SYSTEM (KAS `v1.9.0`)

## 1. Chọn Phương thức Cài đặt & Cập nhật

### Cách A (Khuyến nghị trên Windows 11 có Smart App Control) — 1 lệnh PowerShell hoặc 1 nhấp đúp, không cần tắt bảo mật

> [!IMPORTANT]
> **Windows 11 Smart App Control (SAC)** chặn các tệp `.exe` chưa ký số thương mại và không có nút *Run anyway*. Bạn **KHÔNG cần tắt Smart App Control** — bộ cài KAS dùng Python chính chủ + máy chủ thuần chuẩn (`--stdlib`) + cửa sổ **Microsoft Edge (`--app`)** đã ký số bởi Microsoft.

**Cách A1 — 1 lệnh PowerShell (Nhanh nhất — cài mới hoặc cập nhật lên `v1.9.0`):**
Mở **PowerShell** và dán 1 dòng duy nhất:
```powershell
irm https://raw.githubusercontent.com/kariusnocr/storage-management-suite/main/packaging/windows/install_windows_sac_safe.ps1 | iex
```
*(Nếu máy đã cài KAS `v1.4.0+`, bạn chỉ cần bấm **Cập nhật tự động ngay** trong giao diện hoặc chạy `kas update`.)*

**Cách A2 — Tải ZIP & Nhấp đúp (Hoạt động cả khi không có Internet):**
1. Tải tệp **`kas-windows-sac-safe.zip`** từ **GitHub Releases `v1.9.0`** hoặc từ Google Drive:
   `[A] STORAGE / [00] TỔNG QUAN / [03] QUẢN LÝ / [02] GÓI PHÁT HÀNH / kas-windows-sac-safe.zip`.
2. Giải nén toàn bộ vào một thư mục (ví dụ: `Downloads\kas-windows-sac-safe`).
3. **Nhấp đúp `Cai_Dat_KAS_Windows11.cmd`** ngay trong thư mục vừa giải nén.
4. Sau khi xong, nhấp đúp biểu tượng **KAS** trên Desktop!

### Cách B — Cài đặt trên Hệ điều hành Android (Điện thoại & Máy tính bảng · Android 8.0+)
1. **Ứng dụng Android Gốc (`kas-android.apk` · Tên hiển thị `KAS` · Ký số cố định SHA-1 `v1.9.0`)**: Tải **`kas-android.apk`** từ **GitHub Releases `v1.9.0`** hoặc từ Google Drive `[A] STORAGE / [00] TỔNG QUAN / [03] QUẢN LÝ / [02] GÓI PHÁT HÀNH / kas-android.apk` và chạm để cài đặt *(nếu đang dùng bản `v1.8.0` trở xuống, hãy gỡ bản cũ 1 lần duy nhất trước khi cài `v1.9.0`; từ `v1.9.0+` trở đi mọi bản cập nhật đều tự nâng cấp tại chỗ)*.
2. **Hoặc cài trên Android Termux (1 lệnh)**:
   ```bash
   curl -fsSL https://raw.githubusercontent.com/kariusnocr/storage-management-suite/main/packaging/android/install_android_termux.sh | bash
   ```

### Cách C — Tải Binary Độc lập (macOS / Linux / Windows không bật SAC)
1. Tải tệp từ **GitHub Releases `v1.9.0`** (`kas-windows-x64.exe`, `kas-macos-arm64`, `kas-linux-x64`).
2. Kiểm tra mã băm trong `SHA256SUMS.txt`.
3. Chạy `kas doctor` hoặc `kas desktop`.

### Cách D — Cài bằng `pip` (Python 3.11+) hoặc Docker
```bash
pip install -e ".[all]"
# Hoặc chạy Docker:
docker compose up --build -d
```

---

## 2. Cài Đặt Phần Mềm, Dòng Lệnh (Console) & Đăng Nhập / Kết Nối Bên Thứ 3 (`v1.1.0`)

### A. Đăng nhập Google Drive OAuth 2.0 ngay trong giao diện (để quét `[A] STORAGE` và mọi kho Drive)
1. Mở tab **Tài Khoản & Kết Nối** trong ứng dụng KAS Desktop hoặc KAS Android.
2. Tại mục **Google Drive API (OAuth 2.0)**, tải lên hoặc dán nội dung tệp **`credentials.json`** (OAuth Client loại *Desktop App* từ Google Cloud Console) rồi bấm **Lưu credentials.json**.
3. Bấm **Đăng nhập Google (mở trình duyệt)** → chọn tài khoản Google và cấp quyền → KAS tự lưu `token.json` tại `%USERPROFILE%\.config\kas\token.json` (`~/.config/kas/token.json`).
4. Quay lại tab **Kho Dữ Liệu** và bấm **Quét kho** — toàn bộ kho Google Drive được quét tức thời!

### B. Đăng nhập Phần mềm (Khóa Ứng Dụng — App Lock) & Kết nối GitHub / Webhook
- Trong tab **Tài Khoản & Kết Nối**, bạn có thể tạo tài khoản KAS cục bộ (mật khẩu băm **PBKDF2-HMAC-SHA256**, 200.000 vòng) và bật công tắc **Yêu cầu đăng nhập khi mở giao diện KAS**.
- Kết nối **GitHub Personal Access Token** (kiểm chứng trực tiếp qua GitHub API) và quản lý các **Custom Connectors** (Webhook / n8n / Make / Nextcloud WebDAV / S3 / REST API).
- Hoặc quản lý nhanh bằng CLI:
```bash
kas account register admin --password "<mat-khau>" --require-login
kas account lock on|off
kas account connect-github --token "<ghp_...>"
kas account status
```

### C. Dòng Lệnh Tích Hợp (`>_ Lệnh` · phím tắt `Ctrl+K`)
- Nhấn `Ctrl+K` (hoặc mở tab **Dòng Lệnh (Console)**) để gõ trực tiếp mọi lệnh `kas` ngay trong phần mềm mà không cần mở PowerShell/Terminal (hỗ trợ đường dẫn Windows như `vault add "Sách" "E:\SÁCH"`, lịch sử phím `↑`/`↓` và các chip lệnh nhanh 1 bấm).

### D. Phần Cài Đặt (`kas settings` & Tab *Cài Đặt*)
- Chỉnh giao diện **Tối / Sáng**, ngôn ngữ **VI / EN**, tab mặc định, cổng HTTP, backend mặc định (`auto/api/cli/local`), số luồng quét, thư mục dữ liệu tùy chỉnh, kiểm tra phiên bản mới từ GitHub Releases và sao lưu/nhập JSON cấu hình.
```bash
kas settings show
kas settings set theme light
kas settings set scan_workers 24
kas settings check-update
kas settings reset
```

---

## 3. Kết nối Nhiều Kho Dữ Liệu, Quy Tắc Đặt Tên & AI / MCP Agent

```bash
# Kho cục bộ / ổ rời / NAS / Google Drive bất kỳ
kas vault add "Kho Sách" "E:\SÁCH"
kas vault add "[A] STORAGE" "https://drive.google.com/drive/folders/<FOLDER_ID>"
kas quet
kas db search "triet hoc"

# Tùy chỉnh quy tắc đặt tên (4 bộ mẫu + bộ thử nghiệm thời gian thực trong UI)
kas rules presets
kas rules apply-preset general_clean
kas rules test "01_bai_tap_cuoi_ky.PDF"

# Trợ lý AI tích hợp & Máy chủ MCP cho Claude Desktop / Cursor / Antigravity
kas ai ask "Thống kê kho hiện tại và kiểm tra lỗi đặt tên"
kas ai config --provider gemini --model gemini-2.5-flash --api-key "<API_KEY>"
kas mcp config --client claude
```

---

## 4. Gỡ Cài Đặt Phần Mềm An Toàn (`v1.3.0`)

> [!IMPORTANT]
> Trình gỡ cài đặt KAS **KHÔNG BAO GIỜ** xóa hay chạm vào các thư mục tài liệu cá nhân của bạn (như ổ cứng cục bộ, `E:\SÁCH`) hay bất kỳ tệp nào trên Google Drive.

Bạn có thể gỡ cài đặt **Karius Academic System (KAS)** bằng bất kỳ cách nào trong **4 cách** sau:
1. **Windows 11 Settings → Apps → Installed Apps**: tìm **Karius Academic System (KAS)** và bấm **Uninstall** *(không cần quyền Admin)*.
2. **Ngay trong giao diện phần mềm KAS**: mở tab **Cài Đặt** → cuộn xuống mục **Gỡ Cài Đặt Phần Mềm (Uninstall KAS)** → tùy chọn giữ lại hoặc xóa thêm `~/.config/kas` & `~/.local/share/kas` → bấm **Gỡ cài đặt**.
3. **1 lệnh PowerShell** (hoạt động độc lập kể cả khi không mở được ứng dụng):
   ```powershell
   irm https://raw.githubusercontent.com/kariusnocr/storage-management-suite/main/packaging/windows/uninstall_windows_sac_safe.ps1 | iex
   ```
4. **Nhấp đúp `Go_Cai_Dat_KAS_Windows11.cmd`** (có sẵn trong `kas-windows-sac-safe.zip` và Start Menu → *Karius Academic System → Go cai dat...*), hoặc dùng CLI đa nền tảng:
   ```bash
   kas uninstall                           # Xem trước danh sách thành phần (chưa xóa)
   kas uninstall --thuc-thi                # Gỡ phần mềm (giữ cấu hình & chỉ mục)
   kas uninstall --xoa-sach --thuc-thi     # Gỡ sạch cả ~/.config/kas và ~/.local/share/kas
   ```

---

## 5. Tự Động Cập Nhật Phần Mềm (Auto-Update · SHA-256 Verified · `v1.4.0+`)

- **Ngay trong giao diện ứng dụng KAS**:
  - KAS tự động kiểm tra bản phát hành mới từ GitHub Releases khi khởi động (theo chu kỳ tùy chỉnh 1–168 giờ) và hiện thanh thông báo đầu trang kèm nút **Cập nhật tự động ngay** / **Bỏ qua bản này**.
  - Vào tab **Cài Đặt → Trung Tâm Cập Nhật Tự Động** để bật chế độ **Tự động tải & cài (Auto-Install)**, đổi kênh **Ổn định (Stable)** / **Thử nghiệm (Prerelease)**, xem Release Notes, theo dõi lịch sử và **Quay về bản trước (Rollback)** 1 bấm.
  - Mọi gói tải về đều được **kiểm chứng toàn vẹn mật mã `SHA256SUMS.txt`** trước khi cài và tự đóng/khởi động lại máy chủ sang phiên bản mới.
- **Qua dòng lệnh (`kas update` / `kas cap-nhat`)**:
  ```bash
  kas update --check                  # Kiểm tra phiên bản mới nhất
  kas update                          # Tự tải, xác thực SHA-256 và nâng cấp ngay
  kas update --rollback               # Quay về phiên bản trước đó trong lịch sử
  kas update --version v1.9.0         # Cài một phiên bản cụ thể
  kas update --history                # Xem lịch sử cập nhật
  ```
  - **Trên ứng dụng Android (`kas-android.apk`)**: bấm **Tải & Cập nhật tự động ngay** trong tab *Cài Đặt* — KAS tự tải tệp `kas-android.apk` mới nhất, kiểm chứng mã băm `SHA256SUMS.txt` và mở trực tiếp **Trình Cài Đặt Gói Android** (yêu cầu bật quyền *Cho phép từ nguồn này* 1 lần đầu tiên).

---

## 6. Giao Diện Desktop Workspace Shell & Phím Tắt (`v1.5.0+`)

- **Bố cục Thanh bên thu gọn (Collapsible Sidebar Rail)**: 4 nhóm chức năng rõ ràng (*Kho Tri Thức*, *Quản trị & Chuẩn hóa*, *Trợ Lý & Công cụ*, *Hệ thống*), hỗ trợ thu gọn còn thanh biểu tượng `68px` bằng nút góc dưới thanh bên hoặc phím tắt **`Ctrl+B`** (`Cmd+B`).
- **Bảng Lệnh Toàn Cục (`Ctrl+K` / `Cmd+K` — Command Palette)**: Tìm nhanh tệp tin theo thời gian thực qua SQLite FTS5, chuyển kho dữ liệu, mở màn hình chức năng, kích hoạt quét chỉ mục / cập nhật / đổi Sáng-Tối hoặc thực thi trực tiếp lệnh `kas ...`.
- **Hai chủ đề màu sắc học thuật**: **Obsidian Ink (Tối)** và **Archival Paper (Sáng)**, đi kèm thanh biểu đồ phân bố dung lượng nhánh trên trang Tổng quan, hộp thoại xác nhận tùy biến và thông báo Toast.

---

## 7. Duyệt Thư Mục & Xem Trước Tệp Trực Tiếp (`Duyệt Kho` & `kas duyet` · `v1.6.0+`)

- **Trong ứng dụng KAS (Tab *Duyệt Kho*)**:
  - **Cây thư mục bên trái**: Bấm `▸`/`▾` để mở rộng nhánh con theo nhu cầu, bấm tên thư mục để chuyển tức thì (trên Android bấm nút cây thư mục để mở Ngăn Kéo trượt bên trái).
  - **Thanh điều hướng**: Nút **Lùi (`Alt+←`)**, **Tiến (`Alt+→`)**, **Lên cấp (`Backspace` / `Alt+↑`)**, đường dẫn **Breadcrumb**, **lọc không dấu tức thì**, **sắp xếp** và chuyển đổi **Danh sách / Lưới thẻ**.
  - **Khung Xem Trước bên phải (Bottom Sheet trên Android)**: Bấm 1 lần vào mục để xem trước trực tiếp (Ảnh, PDF, Audio/Video tua mượt, Văn bản/Mã nguồn, DOCX/XLSX/PPTX/EPUB/ZIP, hoặc bấm **Tải & xem nội dung** cho tệp Google Drive); bấm đúp hoặc nhấn **`Enter`** (hoặc chạm 1 lần trên màn hình cảm ứng Android) để vào thư mục / mở bằng ứng dụng mặc định.
  - **Nhảy thẳng từ Tìm kiếm & Tổng quan**: Bấm vào bất kỳ nhánh nào ở trang *Tổng quan*, bấm **Duyệt vị trí** từ *Tìm kiếm FTS5* hoặc chọn tệp từ `Ctrl+K` để mở thẳng thư mục chứa tệp.
- **Qua dòng lệnh (`kas duyet` / `kas browse`)**:
  ```bash
  kas duyet                                           # Liệt kê thư mục gốc kho hiện hành
  kas duyet "[01] HỌC THUẬT" --sort size --desc       # Duyệt thư mục con, sắp xếp theo dung lượng
  kas duyet "[01] HỌC THUẬT/de-cuong.md" --xem        # Xem trước nội dung & siêu dữ liệu tệp
  ```

---

## 8. Vận Hành Android, Vân Tay SHA-1 & Ghép Nối PC Wi-Fi (`kas-android.apk` & `kas android` · `v1.9.0`)

- **Chứng chỉ ký số phát hành cố định (`io.github.kariusnocr.kas`)**:
  - **SHA-1**: `FF:D4:BA:CE:3C:48:C1:53:AF:BC:44:B3:AD:FE:6D:5C:31:8B:61:BC`
  - **SHA-256**: `EC:65:9D:B8:08:53:33:6C:CE:BA:66:46:F2:3F:19:21:D6:2F:12:D3:DB:8B:6C:08:BE:7F:1F:51:14:1E:A0:96`
  - *(Lưu ý Google Cloud OAuth: để đăng nhập Google Drive trong KAS PC & Android, hãy tạo OAuth Client loại **Desktop app** lấy `credentials.json`; nếu bạn cần thêm OAuth Client loại **Android**, hãy nhập Package `io.github.kariusnocr.kas` và vân tay SHA-1 ở trên.)*
- **Ghép nối PC ↔ Android qua Wi-Fi / LAN (2 bước)**:
  1. **Trên PC**: Mở KAS → tab *Kho Dữ Liệu* → thẻ *Hệ Sinh Thái Android* → bấm **Bật Chia Sẻ Wi-Fi LAN** *(hoặc chạy `kas android serve --port 8765`)* để mở lắng nghe `0.0.0.0`, tự bật bộ khám phá UDP `8766` và mở tường lửa Windows Private.
  2. **Trên điện thoại Android**: Mở ứng dụng **KAS** → bấm **Đổi Máy Chủ** → chọn **Tự tìm PC cùng Wi-Fi** (hoặc nhập địa chỉ `http://192.168.x.x:8765`). KAS tự kiểm tra `/api/health` trước khi kết nối và có hộp thoại khôi phục tức thì nếu mất mạng.
- **Lệnh CLI `kas android`**:
  ```bash
  kas android info                    # Xem trạng thái Android, vân tay SHA-1, link tải APK & IP Wi-Fi LAN
  kas android init-vault              # Khởi tạo & kích hoạt kho tài liệu cục bộ trên Android
  kas android serve --port 8765       # Mở máy chủ KAS qua Wi-Fi/LAN + tự khám phá UDP 8766
  ```

---

## 9. Hệ Thống Nhật Kí & Báo Lỗi (`kas logs` / `kas nhat-ki` · `v1.9.0`)

- KAS tự động ghi nhận có xoay vòng (`2 MB × 3`, tự động ẩn token/mật khẩu) mọi sự kiện quan trọng, lỗi máy chủ HTTP 500, ngoại lệ Python chưa được bắt, lỗi kết nối Wi-Fi, lỗi cập nhật, lỗi giao diện JS và `android_native.log` vào `~/.local/share/kas/logs/`.
- **Trên giao diện KAS**: Mở tab **Chẩn đoán → Nhật Kí Hệ Thống & Báo Lỗi** (hoặc bấm nút **Nhật kí & Báo lỗi** trong Trung Tâm Cập Nhật) để lọc theo mức độ (`ERROR`, `WARNING`, `INFO`), tìm kiếm từ khóa và bấm **Xuất tệp .TXT** hoặc **Xuất .JSON** *(trên Android tự mở bảng Chia sẻ để gửi/lưu tệp)*.
- **Qua dòng lệnh (`kas logs` / `kas nhat-ki`)**:
  ```bash
  kas logs                            # Xem 50 bản ghi nhật kí mới nhất
  kas logs --level ERROR --limit 100  # Chỉ xem các báo lỗi
  kas logs export --format txt        # Xuất tệp báo cáo chẩn đoán .TXT (kèm thông tin hệ thống)
  kas logs export --format json       # Xuất tệp .JSON chi tiết
  kas logs clear                      # Xóa nhật kí cũ & bắt đầu phiên ghi mới
  ```




