# HƯỚNG DẪN CÀI ĐẶT & SỬ DỤNG — KARIUS ACADEMIC SYSTEM (KAS `v1.0.0`)

## 1. Chọn Phương thức Cài đặt

### Cách A (Khuyến nghị trên Windows 11 có Smart App Control) — Cài 1 nhấp đúp, không cần tắt bảo mật

> [!IMPORTANT]
> - **Windows 11 Smart App Control (SAC)** chặn các tệp `.exe` chưa ký số thương mại và không có nút *Run anyway*. Bạn **KHÔNG nên tắt Smart App Control**.
> - Nếu kho GitHub đang ở chế độ **Private**, lệnh `irm https://raw.githubusercontent.com/...` không có xác thực sẽ trả về **`404: Not Found`**. Hãy dùng gói ZIP cài 1 nhấp đúp dưới đây (không cần token, không bao giờ gặp lỗi 404).

**Cách A1 — Tải ZIP & Nhấp đúp (Đơn giản nhất, hoạt động 100% với kho Private):**
1. Tải tệp **`kas-windows-sac-safe.zip`** từ **GitHub Releases `v1.0.0`** (khi đã đăng nhập GitHub) hoặc từ Google Drive:
   `[A] STORAGE / [00] TỔNG QUAN / [03] QUẢN LÝ / [02] GÓI PHÁT HÀNH / kas-windows-sac-safe.zip`.
2. Giải nén toàn bộ vào một thư mục (ví dụ: `Downloads\kas-windows-sac-safe`).
3. **Nhấp đúp `Cai_Dat_KAS_Windows11.cmd`** ngay trong thư mục vừa giải nén.
   *(Hoặc mở PowerShell **ngay tại thư mục vừa giải nén** — không chạy ở `C:\WINDOWS\system32` — rồi gõ:)*
   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\install_windows_sac_safe.ps1
   ```
4. Sau khi xong, nhấp đúp biểu tượng **Karius Academic System (KAS)** trên Desktop!

**Cách A2 — 1 lệnh PowerShell khi máy đã đăng nhập GitHub CLI (`gh auth login`):**
```powershell
gh api repos/kariusnocr/storage-management-suite/contents/packaging/windows/install_windows_sac_safe.ps1 -H "Accept: application/vnd.github.raw" | iex
```

### Cách B — Tải Binary Độc lập (macOS / Linux / Windows không bật SAC)
1. Tải tệp từ **GitHub Releases `v1.0.0`** (`kas-windows-x64.exe`, `kas-macos-arm64`, `kas-linux-x64`).
2. Kiểm tra mã băm trong `SHA256SUMS.txt`.
3. Chạy `kas doctor` hoặc `kas desktop`.

### Cách C — Cài bằng `pip` (Python 3.11+)
```bash
pip install -e ".[all]"
# Hoặc cài gọn thuần Python:
pip install -e ".[drive-api]"
```

### Cách D — Chạy bằng Docker
```bash
docker compose up --build -d
# Mở http://127.0.0.1:8765
```

---

## 2. Kết nối Nhiều Kho Dữ Liệu (Cục bộ & Google Drive bất kỳ)

```bash
# Kho cục bộ / ổ rời / NAS / thư mục đồng bộ OneDrive (100% ngoại tuyến)
kas vault add "Kho Học Tập" "D:\TaiLieuHocTap"
kas quet
kas db search "triet hoc"

# Kho Google Drive bất kỳ (dán URL thư mục Drive hoặc Folder ID)
kas auth login --credentials /đường/dẫn/credentials.json
kas vault add "[A] STORAGE" "https://drive.google.com/drive/folders/<FOLDER_ID>"
kas vault list
kas vault use kho-hoc-tap
```

---

## 3. Tùy chỉnh Thiết lập Quy tắc Đặt tên

Bạn có thể chỉnh trực quan trong tab **Quy Tắc Đặt Tên** của ứng dụng Desktop (có **Bộ Thử Nghiệm Thời Gian Thực**), hoặc dùng CLI `kas rules`:

```bash
kas rules presets                           # Xem 4 bộ mẫu: academic_v6, general_clean, snake_case_dev, kebab_web
kas rules apply-preset general_clean        # Áp dụng mẫu cho kho hiện tại (thêm --global để đặt mặc định toàn cục)
kas rules set folder_index_style dot_2      # Đổi kiểu tiền tố thư mục thành `01. ...`
kas rules set max_name_length 140           # Giới hạn độ dài tên tối đa
kas rules test "01_bai_tap_cuoi_ky.PDF"     # Xem trước kết quả kiểm tra & đề xuất chuẩn hóa
kas rules reset                             # Khôi phục quy tắc mặc định
```

---

## 4. Kết nối Chatbot AI & AI Agent (Chuẩn MCP)

### A. Trợ lý AI tích hợp ngay trong KAS (CLI & Tab *Trợ Lý AI & Agent*)
- Mặc định dùng **Trợ Lý Cục Bộ KAS** chạy **100% ngoại tuyến** không cần API key.
- Dễ dàng kết nối **Google Gemini**, **OpenAI**, **Ollama (chạy LLM miễn phí ngay trên máy)**, **LM Studio**, **OpenRouter**, hoặc **Anthropic Claude** để trò chuyện có Tool Calling trực tiếp trên dữ liệu kho:
```bash
kas ai ask "Thống kê kho hiện tại và kiểm tra lỗi đặt tên"
kas ai config --provider openai_compat --base-url http://localhost:11434/v1 --model llama3.1
kas ai config --provider gemini --model gemini-2.5-flash --api-key "<API_KEY>"
kas ai chat
```

### B. Kết nối AI Agent bên ngoài qua giao thức MCP (Claude Desktop, Cursor, Windsurf, Antigravity)
Chạy lệnh sau (hoặc bấm nút **Sao chép JSON MCP** trong tab **Trợ Lý AI & Agent**) rồi dán vào cấu hình MCP của client AI:
```bash
kas mcp config --client claude      # Stdio MCP (`kas mcp serve`)
kas mcp config --client http        # HTTP JSON-RPC 2.0 (`http://127.0.0.1:8765/api/mcp`)
kas mcp tools                       # Xem danh sách 10 công cụ an toàn KAS cung cấp cho Agent
```
