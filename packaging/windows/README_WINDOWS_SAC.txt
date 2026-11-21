KARIUS ACADEMIC SYSTEM (KAS) v5.0.0 — GOI AN TOAN WINDOWS 11 SMART APP CONTROL
===============================================================================

HE THONG QUAN TRI TRI THUC & DA KHO DU LIEU:
- Quan ly bat ky thu muc cuc bo nao tren may tinh / o cung roi / NAS / OneDrive
  (chay 100% ngoai tuyen, khong can dang nhap).
- Quan ly bat ky thu muc / Shared Drive nao tren Google Drive (qua OAuth 2.0).
- Chay truc tiep bang Python chinh thuc da ky so + cua so Microsoft Edge App Window,
  tuong thich 100% Windows 11 Smart App Control (KHONG can tat bao mat).

CAI DAT NHANH (CHON 1 TRONG 2 CACH):

Cach 1 (1 lenh PowerShell):
  irm https://raw.githubusercontent.com/kariusnocr/storage-management-suite/main/packaging/windows/install_windows_sac_safe.ps1 | iex

Cach 2 (Cai offline tu goi ZIP nay):
  1. Giai nen toan bo thu muc nay.
  2. Mo PowerShell trong thu muc vua giai nen va chay:
     powershell -NoProfile -ExecutionPolicy Bypass -File .\install_windows_sac_safe.ps1
  3. Nhap dup bieu tuong "Karius Academic System (KAS)" tren Desktop hoac go:
     kas vault add tai-lieu --nguon D:\ThuMucCuaBan
     kas vault add drive-kho --nguon https://drive.google.com/drive/folders/<FOLDER_ID>
     kas quet
     kas desktop --browser --stdlib
