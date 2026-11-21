STORAGE MANAGEMENT SUITE v4.0.1 — GOI AN TOAN CHO WINDOWS 11 SMART APP CONTROL
===============================================================================

TAI SAO WINDOWS 11 CHAN FILE `astorage-windows-x64.exe`?
- Tinh nang Smart App Control (SAC) tren Windows 11 chan MOI file .exe chua co chung chi
  ky so thuong mai (Authenticode) va khong co nut "Run anyway".
- KHONG NEN tat Smart App Control vi tren Windows 11 khi tat di se khong bat lai duoc
  neu khong cai lai Windows.

CACH CHAY AN TOAN 100% KHI VAN BAT SMART APP CONTROL:
Phan mem chay truc tiep qua trinh thong dich Python chinh thuc (da duoc ky so boi
Python Software Foundation / Microsoft) va mo giao dien Desktop bang cua so doc lap
Microsoft Edge (da ky so boi Microsoft) — KHONG dung file .exe chua ky, KHONG can tat SAC!

HUONG DAN CAI DAT NHANH (CHON 1 TRONG 2 CACH):

Cach 1 (1 lenh PowerShell — nhanh nhat, khong can giai nen):
  Mo PowerShell va dan lenh sau:
  irm https://raw.githubusercontent.com/kariusnocr/storage-management-suite/main/packaging/windows/install_windows_sac_safe.ps1 | iex

Cach 2 (Cai offline tu goi ZIP nay):
  1. Giai nen toan bo thu muc nay.
  2. Mo PowerShell trong thu muc vua giai nen va chay:
     powershell -NoProfile -ExecutionPolicy Bypass -File .\install_windows_sac_safe.ps1
  3. Sau khi cai xong, nhap dup bieu tuong "Storage Management Suite" tren Desktop
     hoac mo PowerShell moi va go:
     astorage doctor
     astorage auth login --credentials C:\duong\dan\credentials.json
     astorage desktop --browser --stdlib
