KARIUS ACADEMIC SYSTEM (KAS) v1.1.0 - GOI AN TOAN WINDOWS 11 SMART APP CONTROL
===============================================================================

HE THONG QUAN TRI TRI THUC, DA KHO DU LIEU VA KET NOI AI / AGENT:
- Quan ly bat ky thu muc cuc bo nao tren may tinh / o cung roi / NAS / OneDrive
  (chay 100% ngoai tuyen, khong can dang nhap).
- Quan ly bat ky thu muc / Shared Drive nao tren Google Drive (qua OAuth 2.0).
- Tuy chinh linh hoat quy tac dat ten theo tung kho (Presets + Live Tester).
- Tich hop Chatbot AI & May chu MCP chuan ket noi Claude Desktop / Cursor / Antigravity / Ollama / Gemini.
- Chay truc tiep bang Python chinh thuc da ky so + cua so Microsoft Edge App Window,
  tuong thich 100% Windows 11 Smart App Control (KHONG can tat bao mat).

CAI DAT NHANH (CHON 1 TRONG 2 CACH):

Cach 1 - KHUYEN NGHI (1 NHAP DUP - KHONG BAO GIO BI LOI 404 PRIVATE REPO):
  1. Giai nen toan bo tep 'kas-windows-sac-safe.zip' nay ra mot thu muc (vd: Downloads\kas).
  2. Nhap dup vao tep:  Cai_Dat_KAS_Windows11.cmd
     (Hoac mo PowerShell NGAY TRONG thu muc vua giai nen va chay:
      powershell -NoProfile -ExecutionPolicy Bypass -File .\install_windows_sac_safe.ps1)
  3. Sau khi xong, nhap dup bieu tuong "Karius Academic System (KAS)" tren Desktop!

Cach 2 - 1 lenh PowerShell cho kho GitHub Private (neu may da cai & dang nhap `gh`):
  gh api repos/kariusnocr/storage-management-suite/contents/packaging/windows/install_windows_sac_safe.ps1 -H "Accept: application/vnd.github.raw" | iex

LENH CO BAN TRONG POWERSHELL:
  kas vault add "Tai Lieu" "D:\ThuMucCuaBan"
  kas vault add "Kho Drive" "https://drive.google.com/drive/folders/<FOLDER_ID>"
  kas rules presets       (tuy chinh quy tac dat ten)
  kas ai chat             (tro chuyen voi Tro ly AI)
  kas mcp config          (lay JSON ket noi Claude Desktop / Cursor / Antigravity)
  kas desktop             (mo ung dung Desktop)
