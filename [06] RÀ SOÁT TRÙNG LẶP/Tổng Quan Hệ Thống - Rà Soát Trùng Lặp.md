# TỔNG QUAN HỆ THỐNG — RÀ SOÁT TRÙNG LẶP (v2.0)

- **Vị trí:** `[A] STORAGE/[00] TỔNG QUAN/[03] QUẢN LÝ/[06] RÀ SOÁT TRÙNG LẶP`
- **Tệp mã nguồn:** `dedup_scanner.py`

## Nâng cấp v2.0

- Tách rạch ròi 3 nhóm: `trung_chac_chan` (`Bản 01`, `(1)`, `Copy`), `trung_phien_ban` (`Phiên Bản 1`/`Phiên Bản 2`, chỉ gom khi bật `--gom-phien-ban`), và `nghi_can_duyet` (`Phần 01`/`Phần 02` — không bao giờ tự cách ly).
- `--gom-tong-quan-trung`: phát hiện & cách ly các bản `TongQuan.md` trùng trong `[00] TỔNG QUAN` vào `[99] KIỂM TRA/[03] TỆP TRÙNG LẶP/[01] TỔNG QUAN TRÙNG LẶP`.
- `--xac-minh-noi-dung`: đối chiếu SHA-256 trước khi đưa vào diện cách ly.
- Tận dụng `shortcut_cache.json`, kiểm tra quyền `capabilities` (`KHONG_CO_QUYEN`), phát hiện thư mục rỗng lồng nhau *bottom-up*, và hoàn tác an toàn bằng `--hoan-tac`.

## Cách dùng

```bash
python3 "[06] RÀ SOÁT TRÙNG LẶP/dedup_scanner.py" --gom-tong-quan-trung --gom-phien-ban --xac-minh-noi-dung --kiem-tra-shortcut
python3 "[06] RÀ SOÁT TRÙNG LẶP/dedup_scanner.py" --gom-tong-quan-trung --gom-phien-ban --xac-minh-noi-dung --kiem-tra-shortcut --thuc-thi --dong-y
python3 "[06] RÀ SOÁT TRÙNG LẶP/dedup_scanner.py" --hoan-tac
```
