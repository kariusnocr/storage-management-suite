#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BỘ CÔNG CỤ CHUẨN HÓA & ĐỒNG BỘ HỆ THỐNG [A] STORAGE — CHUẨN V6 (v2.0)
======================================================================
Quy tắc đặt tên Chuẩn V6:
1. Thư mục: `[STT] TÊN IN HOA CÓ DẤU`
2. Tệp nội dung: `Tên Viết Hoa Đầu Mỗi Chữ Có Dấu - Thông Tin Bổ Sung.[đuôi]`
3. Mã nguồn & cấu hình: `[Tên Viết Thường Tiếng Anh Ngắn Gọn].[đuôi]` (`snake_case` tại vùng ngoại lệ)

Nâng cấp v2.0:
- Dùng chung `storage_core.py` (`sc.Drive`, `sc.ACRONYMS_UPPER`, `sc.is_tech_exception`, `STORAGE_DATA_DIR`).
- Bất biến (idempotent) 100%: thêm `is_already_v6()` bỏ qua tệp đã đạt Chuẩn V6, `[03] QUẢN LÝ`,
  tệp Google gốc (`GOOGLE_NATIVE_MIMES`) và bảng `Danh Mục Hệ Thống`.
- Chống đụng độ thông minh cho thư mục có nhiều `TongQuan.md` trùng (nhường `[06]` cách ly thay vì sinh `, Phần 01`).
- Checkpoint JSON gọn, chỉ ghi `storage_index.json` một lần sau khi hoàn tất lô thực thi.
"""

import argparse
import concurrent.futures
import json
import re
import sys
import time
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Tuple

from karius_academic_system import core as sc

SCRATCH_DIR = sc.data_dir()
INDEX_PATH = sc.index_path()
SHEETS_LOG_PATH = sc.sheets_log_path()
PLAN_PATH = SCRATCH_DIR / "planned_v6_renames.json"
EXEC_LOG_PATH = SCRATCH_DIR / "executed_v6_renames.json"
FOLDER_MIME = sc.FOLDER_MIME
ACRONYMS_UPPER = sc.ACRONYMS_UPPER


def strip_accents(text: str) -> str:
    return sc.strip_accents(text)


def has_vn_diacritics(text: str) -> bool:
    return strip_accents(text) != text


def load_or_build_sheets_log(index_data: dict) -> dict:
    if SHEETS_LOG_PATH.exists():
        return json.loads(SHEETS_LOG_PATH.read_text(encoding="utf-8"))
    out = {}
    for p, d in index_data.items():
        if p.endswith("/[00] TỔNG QUAN"):
            parent = p[: -len("/[00] TỔNG QUAN")]
            for it in d.get("items", []):
                if it.get("mimeType") == sc.SHEET_MIME and it.get("name", "").startswith("Danh Mục Hệ Thống"):
                    out[parent] = {
                        "path": parent,
                        "depth": parent.count("/"),
                        "tq_id": d.get("id"),
                        "sheet_name": it["name"],
                        "sheet_id": it["id"],
                    }
                    break
    return out


# ============================================================================
# 1. TỪ ĐIỂN CỤM TỪ HỌC THUẬT & SÁNG TÁC (CURATED LEXICON)
# ============================================================================
CURATED_PHRASES = {
    # Bổ sung cho các tệp cũ còn tồn đọng
    "leminhdat": "Lê Minh Đạt",
    "longtieng": "Lồng Tiếng",
    "chuyennangtothi": "Chuyện Nàng Tô Thị",
    "cachintailieusachonline": "Cách In Tài Liệu Sách Online",
    "cachintailieuxin": "Cách In Tài Liệu Xịn",
    "khoadrivefree": "Khóa Drive Free",
    "khoadrive2k82026": "Khóa Drive 2K8 2026",
    "khoahocdrive12free": "Khóa Học Drive 12 Free",
    "khoahocdrive": "Khóa Học Drive",
    "khoa2k9xps2027": "Khóa 2K9 XPS 2027",
    "comaiphuong": "Cô Mai Phương",
    "comaiphuong48ngaylaygoctienganh": "Cô Mai Phương 48 Ngày Lấy Gốc Tiếng Anh",
    "laygoc": "Lấy Gốc",
    "cosuongmai": "Cô Sương Mai",
    "vancosuongmai12": "Văn Cô Sương Mai 12",
    "thaychi": "Thầy Chí",
    "toanthaychi12": "Toán Thầy Chí 12",
    "thayvungocanhly12": "Thầy Vũ Ngọc Anh Lý 12",
    "hoctotcungchingoc": "Học Tốt Cùng Chị Ngọc",
    "chingoc": "Chị Ngọc",
    "kho219detruongso": "Kho 219 Đề Trường Sở",
    "truongso": "Trường Sở",
    "nentanglop12": "Nền Tảng Lớp 12",
    "nentang": "Nền Tảng",
    "guigmailqua0879904833dehocthu": "Gửi Gmail Qua 0879904833 Để Học Thử",
    "dehocthu": "Để Học Thử",
    "linkshop": "Link Shop",
    "reviewsach": "Review Sách",
    "dethithucacsotruongcodalopsuanhthien": "Đề Thi Thử Các Sở Trường Có Đáp Án Lớp Sử Anh Thiện",
    "thluocsutriethoc": "Lược Sử Triết Học",
    "luocsu": "Lược Sử",
    "nhanhoc": "Nhân Học",
    "studychewinggumwhilestudyingeffectsonal": "Study Chewing Gum While Studying Effects On All",
    # Học thuật & Phổ thông
    "baitap": "Bài Tập",
    "baitaptracnghiem": "Bài Tập Trắc Nghiệm",
    "baitaptuluan": "Bài Tập Tự Luận",
    "tuluan": "Tự Luận",
    "tracnghiem": "Trắc Nghiệm",
    "tracnghiemdungsai": "Trắc Nghiệm Đúng Sai",
    "traloingan": "Trả Lời Ngắn",
    "dungsai": "Đúng Sai",
    "vandung": "Vận Dụng",
    "vandungcao": "Vận Dụng Cao",
    "thonghieu": "Thông Hiểu",
    "nhanbiet": "Nhận Biết",
    "coban": "Cơ Bản",
    "nangcao": "Nâng Cao",
    "chuyen": "Chuyên",
    "chuyende": "Chuyên Đề",
    "chongsaingu": "Chống Sai Ngu",
    "kinhdien": "Kinh Điển",
    "congthuc": "Công Thức",
    "giainhanh": "Giải Nhanh",
    "nhapmon": "Nhập Môn",
    "daicuong": "Đại Cương",
    "giaotrinh": "Giáo Trình",
    "tailieu": "Tài Liệu",
    "tailieuthamkhao": "Tài Liệu Tham Khảo",
    "thamkhao": "Tham Khảo",
    "decuong": "Đề Cương",
    "ontap": "Ôn Tập",
    "huongdanontap": "Hướng Dẫn Ôn Tập",
    "onthi": "Ôn Thi",
    "luyenthi": "Luyện Thi",
    "luyende": "Luyện Đề",
    "deluyen": "Đề Luyện",
    "deluyenso": "Đề Luyện Số",
    "dethi": "Đề Thi",
    "dethithu": "Đề Thi Thử",
    "thithu": "Thi Thử",
    "totnghiep": "Tốt Nghiệp",
    "minhhoa": "Minh Họa",
    "demh": "Đề Minh Họa",
    "dapan": "Đáp Án",
    "dapanchitiet": "Đáp Án Chi Tiết",
    "loigiai": "Lời Giải",
    "loigiaichitiet": "Lời Giải Chi Tiết",
    "huongdan": "Hướng Dẫn",
    "huongdancham": "Hướng Dẫn Chấm",
    "huongdangiai": "Hướng Dẫn Giải",
    "cauhoi": "Câu Hỏi",
    "cautruc": "Cấu Trúc",
    "cautrucmoi": "Cấu Trúc Mới",
    "renluyen": "Rèn Luyện",
    "baihoc": "Bài Học",
    "baigiang": "Bài Giảng",
    "lythuyet": "Lý Thuyết",
    "thuchanh": "Thực Hành",
    "phuongphap": "Phương Pháp",
    "phuongphapluan": "Phương Pháp Luận",
    "kynang": "Kỹ Năng",
    "kynangmem": "Kỹ Năng Mềm",
    "ngochuyenlb": "Ngọc Huyền LB",
    "congochuyenlb": "Cô Ngọc Huyền LB",
    "nguyenhuyen": "Nguyễn Huyền",
    "thaynguyenhuyen": "Thầy Nguyễn Huyền",
    "dovanduoc": "Đỗ Văn Đức",
    "thaydovanduoc": "Thầy Đỗ Văn Đức",
    "vungocanh": "Vũ Ngọc Anh",
    "thayvungocanh": "Thầy Vũ Ngọc Anh",
    "phamvanthuan": "Phạm Văn Thuận",
    "lenam": "Lê Nam",
    "thuthuy": "Thu Thủy",
    "hoctot": "Học Tốt",
    "hinhhoc": "Hình Học",
    "hoctothinhhoc": "Học Tốt Hình Học",
    "xulisolieu": "Xử Lí Số Liệu",
    "moingaymotde": "Mỗi Ngày Một Đề",
    "tuancuoi": "Tuần Cuối",
    "moinhat": "Mới Nhất",
    "viettay": "Viết Tay",
    "hamso": "Hàm Số",
    "logarit": "Logarit",
    "muvalogarit": "Mũ Và Logarit",
    "nguyenham": "Nguyên Hàm",
    "tichphan": "Tích Phân",
    "ungdung": "Ứng Dụng",
    "sophuc": "Số Phức",
    "khoangcach": "Khoảng Cách",
    "goc": "Góc",
    "thetic": "Thể Tích",
    "thetich": "Thể Tích",
    "khoibay": "Khối Đa Diện",
    "khoidadien": "Khối Đa Diện",
    "matcau": "Mặt Cầu",
    "matnon": "Mặt Nón",
    "mattru": "Mặt Trụ",
    "toado": "Tọa Độ",
    "khonggian": "Không Gian",
    "xacsuat": "Xác Suất",
    "thongke": "Thống Kê",
    "capso": "Cấp Số",
    "capsocong": "Cấp Số Cộng",
    "capsonhan": "Cấp Số Nhân",
    "gioihan": "Giới Hạn",
    "daoham": "Đạo Hàm",
    "luonggiac": "Lượng Giác",
    "phuongtrinh": "Phương Trình",
    "batphuongtrinh": "Bất Phương Trình",
    "hephuongtrinh": "Hệ Phương Trình",
    "daodong": "Dao Động",
    "daodongco": "Dao Động Cơ",
    "songco": "Sóng Cơ",
    "songanhsang": "Sóng Ánh Sáng",
    "dienxoaychieu": "Điện Xoay Chiều",
    "luongtu": "Lượng Tử",
    "luongtuanhsang": "Lượng Tử Ánh Sáng",
    "luongtubuoi": "Lượng Tử Buổi",
    "hatnhan": "Hạt Nhân",
    "vatly": "Vật Lý",
    "vatli": "Vật Lí",
    "hoahoc": "Hóa Học",
    "sinhhoc": "Sinh Học",
    "toanhoc": "Toán Học",
    "toan": "Toán",
    "nguvan": "Ngữ Văn",
    "lichsu": "Lịch Sử",
    "diali": "Địa Lí",
    "dialy": "Địa Lý",
    "tienganh": "Tiếng Anh",
    "tiengtrung": "Tiếng Trung",
    "tiengphap": "Tiếng Pháp",
    "tiengduc": "Tiếng Đức",
    "tiengnhat": "Tiếng Nhật",
    "tienghan": "Tiếng Hàn",
    "triethoc": "Triết Học",
    "logichoc": "Logic Học",
    "logichocdaicuong": "Logic Học Đại Cương",
    "tamlyhoc": "Tâm Lý Học",
    "xahoihoc": "Xã Hội Học",
    "chinhtrihoc": "Chính Trị Học",
    "tongiaohoc": "Tôn Giáo Học",
    "myhoc": "Mỹ Học",
    "daoduchoc": "Đạo Đức Học",
    "kinhdich": "Kinh Dịch",
    "daoduckinh": "Đạo Đức Kinh",
    "nho": "Nho",
    "phat": "Phật",
    "dao": "Đạo",
    "phuongdong": "Phương Đông",
    "phuongtay": "Phương Tây",
    "codai": "Cổ Đại",
    "trungdai": "Trung Đại",
    "candai": "Cận Đại",
    "hiendai": "Hiện Đại",
    "duongdai": "Đương Đại",
    "sieuhinhhoc": "Siêu Hình Học",
    "nhanthuchoc": "Nhận Thức Luận",
    "nhanthucluan": "Nhận Thức Luận",
    "bienthung": "Biện Chứng",
    "bienchung": "Biện Chứng",
    "duyvat": "Duy Vật",
    "duytam": "Duy Tâm",
    "maclenin": "Mác-Lênin",
    "tuonghinh": "Tượng Hình",
    "nghiencuu": "Nghiên Cứu",
    "bainghiencuu": "Bài Nghiên Cứu",
    "tieuluan": "Tiểu Luận",
    "luanvan": "Luận Văn",
    "luancu": "Luận Cứ",
    "chuyennganh": "Chuyên Ngành",
    "ngoaikhoa": "Ngoại Khóa",
    "hoithao": "Hội Thảo",
    "gioithieu": "Giới Thiệu",
    "gioithieusach": "Giới Thiệu Sách",
    "binhluan": "Bình Luận",
    "binhchu": "Bình Chú",
    "thaoluan": "Thảo Luận",
    "khaimac": "Khai Mạc",
    "bemac": "Bế Mạc",
    "tonghop": "Tổng Hợp",
    "bantonghop": "Bản Tổng Hợp",
    "toanbo": "Toàn Bộ",
    "toantap": "Toàn Tập",
    "tronbo": "Trọn Bộ",
    "chuanhoa": "Chuẩn Hóa",
    "sohoa": "Số Hóa",
    "duansohoa": "Dự Án Số Hóa",
    "manguon": "Mã Nguồn",
    "bochuongtrinhcon": "Bộ Chương Trình Con",
    "cauhinh": "Cấu Hình",
    "hethong": "Hệ Thống",
    "hethonghoa": "Hệ Thống Hóa",
    "danhmuc": "Danh Mục",
    "danhmuchethong": "Danh Mục Hệ Thống",
    "danhsach": "Danh Sách",
    "danhsachlop": "Danh Sách Lớp",
    "sinhvien": "Sinh Viên",
    "dongphuc": "Đồng Phục",
    "dangky": "Đăng Ký",
    "dangki": "Đăng Kí",
    "daotao": "Đào Tạo",
    "tientrinh": "Tiến Trình",
    "lichtrinh": "Lịch Trình",
    "namhoc": "Năm Học",
    "hocky": "Học Kỳ",
    "hocki": "Học Kì",
    "tuanso": "Tuần Số",
    "tuan": "Tuần",
    "buoi": "Buổi",
    "phan": "Phần",
    "tap": "Tập",
    "chuong": "Chương",
    "bai": "Bài",
    "donvi": "Đơn Vị",
    "trang": "Trang",
    "quyen": "Quyển",
    "cuon": "Cuốn",
    "so": "Số",
    "de": "Đề",
    "deso": "Đề Số",
    "cau": "Câu",
    "chup": "Chụp",
    "xoay": "Xoay",
    "xet": "Xét",
    "lotrinh": "Lộ Trình",
    "goiy": "Gợi Ý",
    "khotailieu": "Kho Tài Liệu",
    "tudien": "Từ Điển",
    "tuvung": "Từ Vựng",
    "nguphap": "Ngữ Pháp",
    "mucluc": "Mục Lục",
    "loinoi": "Lời Nói",
    "loinoidau": "Lời Nói Đầu",
    "bia": "Bìa",
    "danlo": "Dẫn Lộ",
    "daiy": "Đại Ý",
    "chuthich": "Chú Thích",
    "dinhchanh": "Đính Chánh",
    "phuluc": "Phụ Lục",
    "xuatban": "Xuất Bản",
    "banquyen": "Bản Quyền",
    "bandich": "Bản Dịch",
    "tiengviet": "Tiếng Việt",
    "suyniem": "Suy Niệm",
    "nhungsuyniem": "Những Suy Niệm",
    "nhungsuyniemsieuhinhhoc": "Những Suy Niệm Siêu Hình Học",
    "khainiem": "Khái Niệm",
    "phandoan": "Phán Đoán",
    "quyluat": "Quy Luật",
    "suyluan": "Suy Luận",
    "diendich": "Diễn Dịch",
    "quynap": "Quy Nạp",
    "loaisuy": "Loại Suy",
    "chungminh": "Chứng Minh",
    "giathuyet": "Giả Thuyết",
    "nguyenvuhao": "Nguyễn Vũ Hảo",
    "nguyenquanghung": "Nguyễn Quang Hưng",
    "buithanhquat": "Bùi Thanh Quất",
    "dominhhop": "Đỗ Minh Hợp",
    "ngotatto": "Ngô Tất Tố",
    "quangduc": "Quảng Đức",
    "khiemquaibi": "Khiêm Quái Bi",
    "vietdichchanhtong": "Việt Dịch Chánh Tông",
    "diengiang": "Diễn Giảng",
    "nguoiquantu": "Người Quân Tử",
    "daocuanguoiquantu": "Đạo Của Người Quân Tử",
    "dongianhoaviechoc": "Đơn Giản Hóa Việc Học",
    "trunglap": "Trùng Lặp",
    "nhatki": "Nhật Kí",
    "nhatky": "Nhật Ký",
    "chimuc": "Chỉ Mục",
    "bangsheet": "Bảng Sheet",
    "toankho": "Toàn Kho",
    "kiemtra": "Kiểm Tra",
    "xuly": "Xử Lý",
    "dongbo": "Đồng Bộ",
    "hangloat": "Hàng Loạt",
    "taobang": "Tạo Bảng",
    "bientap": "Biên Tập",
    "sangtac": "Sáng Tác",
    "sangtactho": "Sáng Tác Thơ",
    "sangtacvan": "Sáng Tác Văn",
    "suutam": "Sưu Tầm",
    "khoahoc": "Khóa Học",
    "amnhac": "Âm Nhạc",
    "trichdan": "Trích Dẫn",
    "nhungnguoikhonkho": "Những Người Khốn Khổ",
    # Sáng tác Thơ & Văn
    "anhthu": "Ánh Thu",
    "datruong": "Dã Tràng",
    "doigapconhan": "Đợi Gặp Cố Nhân",
    "doinhanthe": "Đời Nhân Thế",
    "doitoicobaminhdat": "Đời Tôi Có Ba Mình Đạt",
    "dongthua": "Đông Thừa",
    "giaotam": "Giao Tâm",
    "huongduongtutruyenhoid": "Hướng Dương Tự Truyện Hồi I",
    "huongduongtutruyenhoii": "Hướng Dương Tự Truyện Hồi I",
    "kariustamtinhthitap": "Karius Tâm Tình Thi Tập",
    "khuyettam": "Khuyết Tâm",
    "minhtu": "Minh Tư",
    "muahoacuoi": "Mùa Hoa Cuối",
    "ngosubatquyet": "Ngộ Sự Bất Quyết",
    "nguyetanhthihontap": "Nguyệt Ánh Thi Hồn Tập",
    "quyeuduocchet": "Quyền Được Chết",
    "quyenduocchet": "Quyền Được Chết",
    "thoidai": "Thời Đại",
    "thuduc": "Thủ Đức",
    "tianangchomha": "Tia Nắng Chớm Hạ",
    "tieutam": "Tiểu Tâm",
    "tinhyeuvacaichet": "Tình Yêu Và Cái Chết",
    "tuton": "Tự Tôn",
    "vatdoisaodoi": "Vật Đổi Sao Dời",
    "biettinhhuuhan": "Biết Tính Hữu Hạn",
    "bucthuguitoichinhminh": "Bức Thư Gửi Tới Chính Mình",
    "caibong": "Cái Bóng",
    "camtrihoiuc": "Cảm Tri Hồi Ức",
    "changbaogiogaplai": "Chẳng Bao Giờ Gặp Lại",
    "cohoi": "Cơ Hội",
    "damang": "Đa Mang",
    "damnhiem": "Đảm Nhiệm",
    "hyvong": "Hy Vọng",
    "ketimkiemchanly": "Kẻ Tìm Kiếm Chân Lý",
    "khongconcamxuc": "Không Còn Cảm Xúc",
    "kiuc": "Kí Ức",
    "lidogigaplai": "Lí Do Gì Gặp Lại",
    "loianhnoianhvandanggiu": "Lời Anh Nói Anh Vẫn Đang Giữ",
    "loihenuocdamon": "Lời Hẹn Ước Đã Mòn",
    "loiuythac": "Lời Ủy Thác",
    "menhcach": "Mệnh Cách",
    "metroi": "Mệt Rồi",
    "nenluachonnghenghieptheodammehayhoancanh": "Nên Lựa Chọn Nghề Nghiệp Theo Đam Mê Hay Hoàn Cảnh",
    "nguyennhungdaycungphaitinh": "Ngủ Yên Nhưng Dậy Cũng Phải Tỉnh",
    "nguongvong": "Ngưỡng Vọng",
    "noivenguyenhoc": "Nói Về Nguyên Học",
    "quotenguyenniem": "Quote Nguyên Niệm",
    "sucodoc": "Sự Cô Độc",
    "tailieukhongcotieude": "Tài Liệu Không Có Tiêu Đề",
    "thiennhan": "Thiên Nhãn",
    "thoomongmo": "Thờ Ơ Mộng Mơ",
    "thongnhat": "Thống Nhất",
    "tiemlongthamuyen": "Tiềm Long Thâm Uyên",
    "timchetkiemsong": "Tìm Chết Kiếm Sống",
    "tintuong": "Tin Tưởng",
    "tinhcammahodanhchonhau": "Tình Cảm Mà Họ Dành Cho Nhau",
    "tinhyeuvachanly": "Tình Yêu Và Chân Lý",
    "tinhyeuvatinnguong": "Tình Yêu Và Tín Ngưỡng",
    "toiuu": "Tối Ưu",
    "tusu": "Tự Sự",
    "c8nhuocthuy": "Chương 8 Nhược Thủy",
    "nhuocthuy": "Nhược Thủy",
    # Huyền Thư Dịch Quán & Nghiên cứu
    "huyenthudichquan": "Huyền Thư Dịch Quán",
    "baicungphithienxathaybachvanson": "Bài Cúng Phi Thiên Xà Thầy Bạch Vân Sơn",
    "duongcongtaomenhtrachnhat4c": "Đường Công Tạo Mệnh Trạch Nhật 4C",
    "huyenhocphuongtay2": "Huyền Học Phương Tây 2",
    "khicuamoclawpsoffice1": "Khí Của Mộc Là WPS Office 1",
    "nguyenthuylinhlopcaohock29triethocxincapbang": "Nguyễn Thùy Linh Lớp Cao Học K29 Triết Học Xin Cấp Bằng",
    "phan112tutuongcuacactrietgiavidai": "Phần 1 - 12 Tư Tưởng Của Các Triết Gia Vĩ Đại",
    "trietgiavidai": "Triết Gia Vĩ Đại",
    "nhanminhhoc": "Nhân Minh Học",
    "tuvi": "Tử Vi",
    "tuvidauso": "Tử Vi Đẩu Số",
    "phitinh": "Phi Tinh",
    "huyenkhongphitinh": "Huyền Không Phi Tinh",
    "vietnam": "Việt Nam",
    "theego": "The Ego",
    "suckhoe": "Sức Khoẻ",
    "yhoc": "Y Học",
    "suckhoeyhoc": "Sức Khoẻ - Y Học",
    "giaiphau": "Giải Phẫu",
    "giaiphauhoc": "Giải Phẫu Học",
    "benhhoc": "Bệnh Học",
    "duochoc": "Dược Học",
    "dongy": "Đông Y",
    "yhoccoTruyen": "Y Học Cổ Truyền",
    "yhoccotruyen": "Y Học Cổ Truyền",
    # Các từ đơn thông dụng dễ thiếu dấu
    "sach": "Sách",
    "va": "Và",
    "cua": "Của",
    "trong": "Trong",
    "voi": "Với",
    "cho": "Cho",
    "ve": "Về",
    "tu": "Từ",
    "den": "Đến",
    "cac": "Các",
    "nhung": "Những",
    "mot": "Một",
    "hai": "Hai",
    "ba": "Ba",
    "bon": "Bốn",
    "nam": "Năm",
    "sau": "Sáu",
    "bay": "Bảy",
    "chin": "Chín",
    "muoi": "Mười",
    "nguoi": "Người",
    "doi": "Đời",
    "thoi": "Thời",
    "ngay": "Ngày",
    "thang": "Tháng",
    "tinh": "Tình",
    "yeu": "Yêu",
    "tam": "Tâm",
    "tri": "Trí",
    "duc": "Đức",
    "nhan": "Nhân",
    "nghia": "Nghĩa",
    "le": "Lễ",
    "tin": "Tín",
    "thien": "Thiên",
    "dia": "Địa",
    "menh": "Mệnh",
    "van": "Văn",
    "tho": "Thơ",
    "su": "Sử",
    "triet": "Triết",
    "hoc": "Học",
    "lop": "Lớp",
    "mon": "Môn",
    "truong": "Trường",
    "dai": "Đại",
    "cao": "Cao",
    "dang": "Đẳng",
    "pho": "Phổ",
    "thong": "Thông",
    "chung": "Chứng",
    "chi": "Chỉ",
    "khoa": "Khóa",
    "bo": "Bộ",
    "ban": "Bản",
    "moi": "Mới",
    "cu": "Cũ",
    "co": "Cổ",
    "kim": "Kim",
    "dong": "Đông",
    "tay": "Tây",
    "bac": "Bắc",
    "viet": "Việt",
    "trung": "Trung",
    "quoc": "Quốc",
    "the": "Thế",
    "gioi": "Giới",
    "lich": "Lịch",
}

# Các từ tiếng Anh phổ biến giữ nguyên không ép dấu tiếng Việt
ENGLISH_WORDS = {
    "section", "track", "course", "courses", "lecture", "lectures", "worksheet",
    "worksheets", "reading", "listening", "writing", "speaking", "test", "tests",
    "unit", "units", "lesson", "lessons", "screenshot", "part", "parts", "vol",
    "volume", "chapter", "file", "files", "audio", "video", "slide", "slides",
    "full", "master", "outline", "review", "ebook", "step", "season", "boost",
    "your", "vocabulary", "cambridge", "english", "grammar", "practice", "book",
    "workbook", "student", "teacher", "edition", "answer", "key", "keys", "guide",
    "introduction", "advanced", "intermediate", "elementary", "basic", "complete",
    "official", "academic", "general", "training", "mock", "exam", "exams",
    "paper", "papers", "sample", "samples", "essay", "essays", "task", "topic",
    "topics", "band", "score", "tips", "strategy", "strategies", "list", "word",
    "words", "phrase", "phrases", "idiom", "idioms", "collocation", "collocations",
    "pronunciation", "phonetics", "communication", "business", "science", "art",
    "history", "philosophy", "psychology", "economics", "finance", "marketing",
    "management", "leadership", "mind", "life", "world", "power", "secret",
    "secrets", "way", "think", "thinking", "fast", "slow", "habit", "habits",
    "atomic", "deep", "work", "flow", "focus", "memory", "brain", "learn",
    "learning", "how", "what", "why", "when", "where", "who", "the", "and",
    "for", "with", "from", "into", "about", "over", "under", "between",
    "warmup", "edited", "transcript", "untitled", "document", "lines", "prayer",
    "date", "selection", "office", "free", "scan", "new", "old", "first",
    "second", "third", "final", "version", "draft", "note", "notes", "summary",
    "series", "flashstudy", "mapstudy", "stamped", "removed", "watermarked",
    "watermark", "describe", "videomeetings", "videoplayback", "success",
    "completion", "handout", "linegraph", "stories", "opinion", "bookstore",
    "sentence", "matching", "paragraph", "globalsuccess", "discuss", "question",
    "passage", "youtube", "destination", "technology", "multiple", "template",
    "environment", "android", "fighter", "process", "education", "headings",
    "animals", "urbanisation", "intelligence", "diagram", "disagree", "solutions",
    "group", "schedule", "field", "trip", "reflection", "zoom", "informal", "letter",
    "ego", "id", "superego", "freud", "jung", "atlas", "human", "anatomy", "clinical",
}


# ============================================================================
# 2. BỘ KHÔI PHỤC DẤU NGỮ CẢNH (CONTEXTUAL DIACRITIC ENGINE)
# ============================================================================
class ContextualDiacriticEngine:
    def __init__(self, index_data: dict):
        # global_ngrams[unaccented_joined_key] -> Counter({accented_Title_Case: score})
        self.global_ngrams: Dict[str, Counter] = defaultdict(Counter)
        self.word_lexicon: Dict[str, Counter] = defaultdict(Counter)
        self._build_from_index(index_data)

    @staticmethod
    def _clean_title_word(w: str) -> str:
        low = strip_accents(w).lower()
        if low in ACRONYMS_UPPER:
            return ACRONYMS_UPPER[low]
        if len(w) <= 1:
            return strip_accents(w).upper()
        return w[0].upper() + w[1:].lower()

    def _add_accented_phrase(self, phrase: str, weight: int, target_map: Optional[Dict[str, Counter]] = None):
        tokens = re.findall(r"[A-Za-zÀ-ỹ0-9]+", phrase)
        if not tokens:
            return
        cleaned = [self._clean_title_word(t) for t in tokens]
        keys = [strip_accents(t).lower() for t in tokens]

        for i, (k, c) in enumerate(zip(keys, cleaned)):
            # Không nạp từ 1 ký tự vào từ điển dấu để tránh biến A, E, O, U, I thành Á, Ế, Ở, Ừ, Í
            if len(k) <= 1 or k.isdigit():
                continue
            bonus = weight * (3 if has_vn_diacritics(c) else 1)
            self.word_lexicon[k][c] += bonus
            if target_map is not None:
                target_map[k][c] += bonus * 5

        max_n = min(6, len(tokens))
        for n in range(1, max_n + 1):
            for i in range(len(tokens) - n + 1):
                sub_keys = keys[i : i + n]
                if any(not k for k in sub_keys):
                    continue
                joined_key = "".join(sub_keys)
                if len(joined_key) <= 1:
                    continue
                spaced_val = " ".join(cleaned[i : i + n])
                bonus = weight * (3 if has_vn_diacritics(spaced_val) else 1)
                self.global_ngrams[joined_key][spaced_val] += bonus
                if target_map is not None:
                    target_map[joined_key][spaced_val] += bonus * 5

    def _build_from_index(self, index_data: dict):
        # 1. Nạp từ điển cố định với trọng số tuyệt đối
        for k, val in CURATED_PHRASES.items():
            self.global_ngrams[k.strip()][val] += 100000
        for k, val in ACRONYMS_UPPER.items():
            self.global_ngrams[k][val] += 100000
            self.word_lexicon[k][val] += 100000

        # 2. Nạp từ toàn bộ 2.945 đường dẫn thư mục có dấu và 5.038 tên sách Chuẩn V5
        for path, data in index_data.items():
            for seg in path.split("/"):
                seg_clean = re.sub(r"^\[[^\]]+\]\s*", "", seg)
                self._add_accented_phrase(seg_clean, weight=15)
            for item in data.get("items", []):
                if item.get("mimeType") == FOLDER_MIME:
                    continue
                name = item["name"]
                if re.match(r"^\[\d{2,3}\]\s+", name):
                    base = re.sub(r"\.[A-Za-z0-9]{1,6}$", "", name)
                    base = re.sub(r"^\[\d{2,3}\]\s+", "", base)
                    if has_vn_diacritics(base):
                        self._add_accented_phrase(base, weight=4)

    def build_local_map(self, folder_path: str) -> Dict[str, Counter]:
        local_map: Dict[str, Counter] = defaultdict(Counter)
        for seg in folder_path.split("/"):
            seg_clean = re.sub(r"^\[[^\]]+\]\s*", "", seg)
            self._add_accented_phrase(seg_clean, weight=50, target_map=local_map)
        return local_map

    def segment_glued_token(self, tok: str) -> List[str]:
        """Tách các chuỗi chữ IN HOA hoặc viết thường dính liền (VD: PHANDTRACNGHIEMDUNGSAI, tuancuoi)."""
        low = strip_accents(tok).lower()
        if (
            len(low) <= 4
            or low.isdigit()
            or low in ENGLISH_WORDS
            or low in ACRONYMS_UPPER
            or low in CURATED_PHRASES
        ):
            return [tok]
        if len(low) <= 6 and low in self.word_lexicon and self.word_lexicon[low].most_common(1)[0][1] >= 15:
            return [tok]

        n = len(low)
        dp = [-1e18] * (n + 1)
        back = [0] * (n + 1)
        dp[0] = 0.0
        for i in range(n):
            if dp[i] <= -1e17:
                continue
            for l in range(1, min(18, n - i + 1)):
                sub = low[i : i + l]
                score = None
                if sub in CURATED_PHRASES:
                    score = 120.0 * (l ** 1.25)
                elif sub in self.global_ngrams and l >= 2:
                    _, cnt = self.global_ngrams[sub].most_common(1)[0]
                    if cnt >= 10:
                        score = (40.0 + min(cnt, 100)) * (l ** 1.15)
                elif sub in self.word_lexicon and l >= 2:
                    _, cnt = self.word_lexicon[sub].most_common(1)[0]
                    if cnt >= 5:
                        score = (25.0 + min(cnt, 80)) * (l ** 1.1)
                elif sub in ENGLISH_WORDS and l >= 3:
                    score = 50.0 * (l ** 1.15)
                elif sub in ACRONYMS_UPPER and l >= 2:
                    score = 45.0 * (l ** 1.1)
                elif l == 1 and sub in "abcdef":
                    score = 5.0
                if score is not None and dp[i] + score > dp[i + l]:
                    dp[i + l] = dp[i] + score
                    back[i + l] = i
        if dp[n] <= -1e17:
            return [tok]
        parts = []
        cur = n
        while cur > 0:
            prev = back[cur]
            parts.append(low[prev:cur])
            cur = prev
        parts.reverse()
        return parts

    def split_pascal_tokens(self, text: str) -> List[str]:
        # Loại bỏ mã hash 10 ký tự ngẫu nhiên sau PHAN1TOANHOCVAXULISOLIEUDESO<N>
        text = re.sub(r"^(PHAN\d+TOANHOCVAXULISOLIEUDESO\d{1,3})[A-Za-z0-9]{10}$", r"\1", text)
        text = text.replace("-", " ").replace("_", " ")
        raw_parts = re.findall(
            r"\b[A-Z]{3}\d{4}\b|\b[A-BC]\d\b|\bK\d{2}\b|[0-9]+|[A-ZÀ-Ỹ]+(?=[A-ZÀ-Ỹ][a-zà-ỹ]|\b|[0-9])|[A-ZÀ-Ỹ]?[a-zà-ỹ]+",
            text,
        )
        expanded = []
        for p in raw_parts:
            if not p:
                continue
            if re.match(r"^([A-Z]{3}\d{4}|[A-C]\d|K\d{2}|\d+)$", p):
                expanded.append(p)
            elif len(p) >= 6 and (p.isupper() or p.islower()):
                expanded.extend(self.segment_glued_token(p))
            else:
                expanded.append(p)
        return expanded

    def restore_segment(self, raw_segment: str, local_map: Optional[Dict[str, Counter]] = None) -> str:
        if not raw_segment:
            return ""
        # Bảo toàn mã học phần đại học kiểu FLF1107, HIS1160, PHI1006
        if re.match(r"^[A-Z]{3}\d{4}$", raw_segment):
            return raw_segment

        full_key = strip_accents(raw_segment).lower()
        if full_key in CURATED_PHRASES:
            return CURATED_PHRASES[full_key]
        if full_key in ACRONYMS_UPPER:
            return ACRONYMS_UPPER[full_key]
        if local_map and full_key in local_map:
            return local_map[full_key].most_common(1)[0][0]

        tokens = self.split_pascal_tokens(raw_segment)
        if not tokens:
            return raw_segment

        n = len(tokens)
        norm_tokens = [strip_accents(t).lower() for t in tokens]

        dp_score = [-1e18] * (n + 1)
        dp_text: List[List[str]] = [[] for _ in range(n + 1)]
        dp_score[0] = 0.0

        for i in range(n):
            if dp_score[i] <= -1e17:
                continue
            if norm_tokens[i].isdigit() or re.match(r"^([A-Z]{3}\d{4}|[A-C]\d|K\d{2})$", tokens[i]):
                cand_score = dp_score[i] + 500.0
                if cand_score > dp_score[i + 1]:
                    dp_score[i + 1] = cand_score
                    dp_text[i + 1] = dp_text[i] + [tokens[i]]

            max_w = min(6, n - i)
            for w in range(1, max_w + 1):
                sub_norm = norm_tokens[i : i + w]
                joined = "".join(sub_norm)

                best_phrase = None
                phrase_weight = 0.0

                if joined in CURATED_PHRASES:
                    best_phrase = CURATED_PHRASES[joined]
                    phrase_weight = 500.0 * (w ** 1.35)
                elif w == 1 and joined in ACRONYMS_UPPER:
                    best_phrase = ACRONYMS_UPPER[joined]
                    phrase_weight = 450.0
                elif w == 1 and len(joined) == 1:
                    best_phrase = joined.upper()
                    phrase_weight = 400.0
                elif w == 1 and joined in ENGLISH_WORDS and not has_vn_diacritics(tokens[i]):
                    best_phrase = tokens[i][0].upper() + tokens[i][1:].lower()
                    phrase_weight = 300.0
                elif local_map and joined in local_map:
                    best_phrase, cnt = local_map[joined].most_common(1)[0]
                    phrase_weight = (250.0 + min(cnt, 200)) * (w ** 1.3)
                elif joined in self.global_ngrams:
                    best_phrase, cnt = self.global_ngrams[joined].most_common(1)[0]
                    diacritic_mult = 1.25 if has_vn_diacritics(best_phrase) else 0.85
                    phrase_weight = (80.0 + min(cnt, 150)) * (w ** 1.25) * diacritic_mult
                elif w == 1:
                    t_orig = tokens[i]
                    if t_orig.isupper() and len(t_orig) <= 5:
                        best_phrase = t_orig
                    elif norm_tokens[i] in self.word_lexicon:
                        best_phrase = self.word_lexicon[norm_tokens[i]].most_common(1)[0][0]
                    else:
                        best_phrase = t_orig[0].upper() + t_orig[1:]
                    phrase_weight = 5.0

                if best_phrase is not None:
                    cand_score = dp_score[i] + phrase_weight
                    if cand_score > dp_score[i + w]:
                        dp_score[i + w] = cand_score
                        dp_text[i + w] = dp_text[i] + [best_phrase]

        result = " ".join(dp_text[n])
        result = re.sub(r"\s+", " ", result).strip()
        result = re.sub(r"\bGD\s*&\s*ĐT\b", "GD&ĐT", result)
        result = re.sub(r"\bKHXH\s*&\s*NV\b", "KHXH&NV", result)
        return result


# ============================================================================
# 3. BỘ LẬP KẾ HOẠCH ĐẶT TÊN KHÔNG ĐỤNG ĐỘ (COLLISION-FREE PLANNER)
# ============================================================================
DIGITIZATION_MODULE_PATTERNS = [
    (re.compile(r".*_AvProcessor_.*\.py$", re.I), "av_processor.py"),
    (re.compile(r".*_Config_.*\.json$", re.I), "config.json"),
    (re.compile(r".*_DocxBuilder_.*\.py$", re.I), "docx_builder.py"),
    (re.compile(r".*_InputRouter_.*\.py$", re.I), "input_router.py"),
    (re.compile(r".*_IntegrityChecker_.*\.py$", re.I), "integrity_checker.py"),
    (re.compile(r".*_OcrAsrNormalizer_.*\.py$", re.I), "ocr_asr_normalizer.py"),
    (re.compile(r".*_BuildUnit01_.*\.py$", re.I), "build_unit_01.py"),
    (re.compile(r".*_BuildUnit02_.*\.py$", re.I), "build_unit_02.py"),
    (re.compile(r".*_BuildUnit03_.*\.py$", re.I), "build_unit_03.py"),
    (re.compile(r".*_BuildUnit04_.*\.py$", re.I), "build_unit_04.py"),
    (re.compile(r".*_BuildUnit05_.*\.py$", re.I), "build_unit_05.py"),
    (re.compile(r".*_BuildUnit06_.*\.py$", re.I), "build_unit_06.py"),
    (re.compile(r".*_BuildUnit07_.*\.py$", re.I), "build_unit_07.py"),
    (re.compile(r".*_BuildUnit08_.*\.py$", re.I), "build_unit_08.py"),
    (re.compile(r".*_MergeAllUnits_.*\.py$", re.I), "merge_all_units.py"),
    (re.compile(r".*_OcrDocxEngine_.*\.py$", re.I), "ocr_docx_engine.py"),
    (re.compile(r".*_MasterCompiler_.*_V1\.py$", re.I), "master_compiler.py"),
    (re.compile(r".*_MasterCompiler_.*_V2\.py$", re.I), "master_compiler_v2.py"),
    (re.compile(r".*_BuildMasterCompilation_.*\.py$", re.I), "build_master_compilation.py"),
    (re.compile(r".*Digitization.*_V1\.zip$", re.I), "digitization_suite_v1.zip"),
    (re.compile(r".*Digitization.*_V2\.zip$", re.I), "digitization_suite_v2.zip"),
    (re.compile(r".*Automation.*\.zip$", re.I), "automation_suite.zip"),
    (re.compile(r"^\d{2,4}_\d{6}_.*Readme.*$", re.I), "readme"),
]

SYSTEM_EXACT_RENAMES = {
    "01_261116_NhatKiHeThongHoa_Storage.md": "Nhật Kí Hệ Thống Hóa - Storage, 16-11-2026.md",
    "02_261116_ChiMucBangSheetToanKho_Storage.json": "sheets_index.json",
    "03_261116_NhatKiXuLyKiemTra_Storage.md": "Nhật Kí Xử Lý Kiểm Tra - Storage, 16-11-2026.md",
    "04_261116_NhatKiChuanHoaTenHeThong_Storage.md": "Nhật Kí Chuẩn Hóa Tên Hệ Thống - Storage, 16-11-2026.md",
    "01_261116_MaNguonTaoBangSheet_Storage.py": "sheet_engine.py",
    "02_261116_MaNguonDongBoHangLoat_Storage.py": "storage_toolkit.py",
}


def format_folder_title_case(folder_path: str, engine: Optional[ContextualDiacriticEngine] = None) -> str:
    if folder_path == sc.ROOT_NAME:
        return "Storage"
    segs = folder_path.split("/")
    last = segs[-1]
    if last == sc.TONG_QUAN_FOLDER and len(segs) >= 2:
        last = segs[-2]
    if last == sc.ROOT_NAME:
        return "Storage"
    clean = re.sub(r"^\[\d{2,3}\]\s*", "", last)
    clean = re.sub(r"^\[([^\]]+)\]\s*(.+)$", lambda m: f"{m.group(1).strip()} - {m.group(2).strip()}", clean)
    clean = re.sub(r"^\[([^\]]+)\]$", r"\1", clean)
    clean = re.sub(r"\.(pdf|docx?|xlsx?|pptx?)$", "", clean, flags=re.I)
    clean = re.sub(r"\s*_+\s*", " ", clean).strip()
    return sc.title_case_vn(clean)


def is_already_v6(old_name: str, mime: str, folder_path: str) -> bool:
    """
    Kiểm tra bất biến: tệp đã đạt Chuẩn V6 hoặc thuộc vùng ngoại lệ kỹ thuật thì trả về True
    để engine KHÔNG tách/sửa lại gây hỏng tên.
    """
    if "[00] TỔNG QUAN/[03] QUẢN LÝ" in folder_path or sc.is_quarantine_path(folder_path):
        return True
    if sc.is_tech_exception(folder_path, old_name):
        return True
    if old_name == "TongQuan.md" or old_name in SYSTEM_EXACT_RENAMES:
        return False
    if old_name.startswith("Danh Mục Hệ Thống - ") or "DanhMucHeThong" in old_name:
        return True
    # Bắt các định dạng cũ bắt buộc cần chuẩn hóa
    if re.match(r"^\d{2,4}_\d{6}_", old_name):
        return False
    if re.match(r"^\[\d{1,3}\]\s+", old_name):
        return False
    if old_name.lstrip().startswith("- "):
        return False
    if re.match(r"^[A-Za-zÀ-ỹ]+_\d{6,8}_[A-Za-z0-9_]+", old_name):
        return False
    base, _ = sc.split_ext(old_name, mime)
    if " - " in base:
        return True
    return False


def clean_book_or_music_name(
    old_name: str, folder_path: str, engine: ContextualDiacriticEngine, local_map: Dict[str, Counter], mime: str = ""
) -> Tuple[str, str]:
    """Làm sạch tên tệp Sách / Âm nhạc đang ở dạng `[STT] Tên - Thông Tin.[đuôi]`."""
    base, ext_raw = sc.split_ext(old_name, mime)
    ext = f".{ext_raw.lower()}" if ext_raw else ""

    base = re.sub(r"^\[\d{2,3}\]\s+", "", base).strip()

    if " - " in base:
        parts = base.split(" - ")
        title_part = " - ".join(parts[:-1]).strip()
        meta_part = parts[-1].strip()
    else:
        title_part = base
        meta_part = format_folder_title_case(folder_path, engine)

    needs_vn_restore = bool(
        re.search(r"^\([A-Za-z]+\)|Dantocking|thuvienPDF|Epub\.vn|Nottram\.edu", title_part, flags=re.I)
    )

    title_part = re.sub(r"^\([A-Za-z]+\)\s*-?\s*", "", title_part).strip()
    title_part = re.sub(r"\b(?:Dantocking\.com|Dantocking|thuvienPDF\.com|Epub\.vn|Nottram\.edu\s*\.Vn)\b", "", title_part, flags=re.I).strip()
    title_part = re.sub(r"\[Book\]-MANTESH", "", title_part, flags=re.I).strip()
    meta_part = re.sub(r"\b(?:Dantocking\.com|Dantocking|Davidbeitler\.com)\b", "", meta_part, flags=re.I).strip()
    meta_part = re.sub(r"\s+\bPdf$", "", meta_part, flags=re.I).strip()
    meta_part = re.sub(r"VNPDF$", "VN", meta_part).strip()

    if not meta_part or meta_part.upper() in ("PDF", "EPUB", "MOBI", "SÁCH", "TÀI LIỆU"):
        segs = folder_path.split("/")
        parent_ctx = format_folder_title_case("/".join(segs[:-1]), engine) if len(segs) > 1 else "Sưu Tầm Sách"
        if meta_part.upper() in ("PDF", "EPUB", "MOBI"):
            meta_part = f"{parent_ctx}, Bản {meta_part.upper()}"
        else:
            meta_part = parent_ctx

    m_author = re.match(r"^(.+?)\s*\(([^()]{3,40})\)$", title_part)
    if m_author and not re.search(r"\b(Scan|V1|V2|Phần|Tập)\b", m_author.group(2), re.I):
        title_part = m_author.group(1).strip()
        author_part = m_author.group(2).strip()
        if author_part.lower() not in meta_part.lower():
            meta_part = f"{author_part}, {meta_part}"

    if needs_vn_restore and not has_vn_diacritics(title_part):
        title_part = engine.restore_segment(title_part, local_map)

    title_part = re.sub(r"\s+", " ", title_part).strip(" -_,")
    meta_part = re.sub(r"\s+", " ", meta_part).strip(" -_,")
    return f"{title_part} - {meta_part}", ext


def convert_regular_file(
    old_name: str, folder_path: str, engine: ContextualDiacriticEngine, local_map: Dict[str, Counter], mime: str = ""
) -> Tuple[str, str, str, int]:
    """
    Chuyển đổi tệp thường từ dạng cũ sang Chuẩn V6:
      `Tên Viết Hoa Đầu Mỗi Chữ Có Dấu - Thông Tin Bổ Sung.[ext]`
    Trả về: `(base_name_without_ext, ext_with_dot, formatted_date, stt_int)`.
    """
    if old_name in SYSTEM_EXACT_RENAMES:
        target = SYSTEM_EXACT_RENAMES[old_name]
        base, ext_raw = sc.split_ext(target, mime)
        ext = f".{ext_raw.lower()}" if ext_raw else ""
        return base, ext, "16-11-2026", 1

    stem, ext_raw = sc.split_ext(old_name, mime)
    ext = f".{ext_raw.lower()}" if ext_raw else ""

    # Trường hợp lỗi dấu gạch ngang đầu tên như `" - Cuộc Đời Và Số Mệnh.prc"` hoặc `" - Sách Chuyen Nang To Thi.pdf"`
    if stem.lstrip().startswith("- "):
        cleaned_stem = re.sub(r"^\s*-\s+", "", stem).strip()
        if has_vn_diacritics(cleaned_stem) and not re.search(r"\bChuyen\b|\bCuoc\b|\bSach\b", cleaned_stem):
            title_clean = sc.title_case_vn(cleaned_stem)
        else:
            title_clean = engine.restore_segment(cleaned_stem, local_map)
        ctx = format_folder_title_case(folder_path, engine)
        return f"{title_clean} - {ctx}", ext, "", 1

    # Trường hợp `<TenKhongDau>_<MaSo/Ngay>_<ChuDe>` như `LeMinhDat_26032571_LongTieng.mp4`
    m_named = re.match(r"^([A-Za-z]+)_(\d{6,8})_(.+)$", stem)
    if m_named:
        who_raw, code, subj_raw = m_named.groups()
        who_clean = engine.restore_segment(who_raw, local_map)
        subj_clean = engine.restore_segment(subj_raw, local_map)
        return f"{subj_clean} - {who_clean}, {code}", ext, "", 1

    m = re.match(r"^(\d{2,4})_(\d{6})_(.+)$", stem)
    if not m:
        restored = sc.title_case_vn(stem) if has_vn_diacritics(stem) else engine.restore_segment(stem, local_map)
        ctx = format_folder_title_case(folder_path, engine)
        return f"{restored} - {ctx}", ext, "", 1

    stt_str, yymmdd, rest = m.groups()
    stt_int = int(stt_str)
    yy, mm, dd = yymmdd[:2], yymmdd[2:4], yymmdd[4:6]
    date_str = f"{dd}-{mm}-20{yy}"

    # Tách hậu tố phiên bản _V1, _V2 nếu có
    version_num = None
    m_ver = re.search(r"_V(\d+)$", rest, flags=re.I)
    if m_ver:
        version_num = m_ver.group(1)
        rest = rest[: m_ver.start()]

    if "_" in rest:
        parts = rest.split("_")
        title_raw = "_".join(parts[:-1])
        meta_raw = parts[-1]
    else:
        title_raw = rest
        meta_raw = ""

    # Xử lý đặc biệt cho [03] SÁNG TÁC
    if "[03] SÁNG TÁC" in folder_path:
        genre = "Thơ" if "[01] THƠ" in folder_path else ("Văn" if "[02] VĂN" in folder_path else "Trích Dẫn")
        if re.match(r"^V?\d{6,8}$", title_raw, re.I):
            digits = re.sub(r"\D", "", title_raw)
            if len(digits) == 6:
                d_s = f"{digits[:2]}-{digits[2:4]}-20{digits[4:6]}"
                title_clean = f"Bản Thảo {genre} Ngày {d_s}"
            elif len(digits) == 8 and digits.startswith(("00", "01", "02", "03")):
                b_no = digits[:2]
                d_s = f"{digits[2:4]}-{digits[4:6]}-20{digits[6:8]}"
                title_clean = f"Bản Thảo {genre} Số {b_no} Ngày {d_s}"
            elif len(digits) == 8:
                d_s = f"{digits[:2]}-{digits[2:4]}-{digits[4:8]}"
                title_clean = f"Bản Thảo {genre} Ngày {d_s}"
            else:
                title_clean = f"Bản Thảo {genre} {digits}"
        elif title_raw.lower() == "untitleddocument":
            title_clean = f"Bản Thảo {genre} Chưa Đặt Tiêu Đề"
        elif re.match(r"^Dream(\d{6})$", title_raw, re.I):
            d6 = re.match(r"^Dream(\d{6})$", title_raw, re.I).group(1)
            title_clean = f"Dream Ngày {d6[:2]}-{d6[2:4]}-20{d6[4:6]}"
        else:
            title_clean = engine.restore_segment(title_raw, local_map)

        meta_clean = engine.restore_segment(meta_raw, local_map) if meta_raw else f"Sáng Tác {genre}"
        meta_items = [meta_clean, date_str]
        if version_num:
            meta_items.append(f"Phiên Bản {version_num}")
        return f"{title_clean} - {', '.join(meta_items)}", ext, date_str, stt_int

    title_clean = engine.restore_segment(title_raw, local_map)
    meta_clean = engine.restore_segment(meta_raw, local_map) if meta_raw else ""

    if re.match(r"^\d{1,3}$", title_clean.strip()):
        parent_title = format_folder_title_case(folder_path, engine)
        title_clean = f"{parent_title} - Phần {title_clean.strip()}"
    elif title_clean.lower() == "untitled document":
        parent_title = format_folder_title_case(folder_path, engine)
        title_clean = f"Tài Liệu Chưa Đặt Tiêu Đề ({parent_title})"

    parent_ctx = format_folder_title_case(folder_path, engine)
    if not meta_clean or meta_clean.lower() == title_clean.lower() or meta_clean.lower() == "tổng quan":
        meta_clean = f"{parent_ctx}, {date_str}"
    elif meta_raw.lower() == "tongquan":
        meta_clean = f"{parent_ctx}, {date_str}"

    if version_num:
        meta_clean = f"{meta_clean}, Phiên Bản {version_num}"

    return f"{title_clean} - {meta_clean}", ext, date_str, stt_int


def _tongquan_target_name(folder_path: str, engine: Optional[ContextualDiacriticEngine] = None) -> str:
    ctx = format_folder_title_case(folder_path, engine)
    if folder_path in (sc.ROOT_NAME, f"{sc.ROOT_NAME}/{sc.TONG_QUAN_FOLDER}"):
        return "Tổng Quan Hệ Thống - Quy Ước Đặt Tên.md"
    return f"Tổng Quan Hệ Thống - {ctx}.md"


def build_full_rename_plan(
    index_data: dict,
    sheets_log: dict,
    branch_prefix: Optional[str] = None,
    include_sheets: bool = False,
) -> List[dict]:
    print("[1/3] Khởi tạo ContextualDiacriticEngine (học ngữ cảnh thư mục & kho sách)...")
    engine = ContextualDiacriticEngine(index_data)

    plan: List[dict] = []
    seen_file_ids = set()
    skipped_dup_tongquan = 0
    prefix_slash = branch_prefix.rstrip("/") + "/" if branch_prefix else ""

    print("[2/3] Lập kế hoạch đặt tên Chuẩn V6 bất biến và chống đụng độ cho từng thư mục...")
    for folder_path, data in index_data.items():
        if branch_prefix and not (folder_path == branch_prefix or folder_path.startswith(prefix_slash)):
            continue
        if folder_path.endswith(".obsidian") or "/.obsidian" in folder_path:
            continue
        if "[00] TỔNG QUAN/[03] QUẢN LÝ" in folder_path or sc.is_quarantine_path(folder_path):
            continue

        local_map = engine.build_local_map(folder_path)
        items = data.get("items", [])
        existing_names = {sc.nfc(it.get("name", "")) for it in items if it.get("mimeType") != FOLDER_MIME}
        tongquan_items = [it for it in items if it.get("mimeType") != FOLDER_MIME and it.get("name") == "TongQuan.md"]

        if len(tongquan_items) > 1:
            skipped_dup_tongquan += len(tongquan_items) - 1

        folder_candidates = []
        for item in items:
            if item.get("mimeType") == FOLDER_MIME:
                continue
            fid = item["id"]
            old_name = item["name"]
            mime = item.get("mimeType", "")

            # 1. Khôi phục tên kỹ thuật cho các module dự án số hóa (nếu chưa đổi)
            restored_mod = None
            if "DỰ ÁN SỐ HÓA" in folder_path or "OCR CHUẨN HOÁ" in folder_path:
                for pat, mod_name in DIGITIZATION_MODULE_PATTERNS:
                    if pat.match(old_name):
                        restored_mod = mod_name
                        break
            if restored_mod:
                if old_name != restored_mod:
                    plan.append({
                        "id": fid,
                        "path": folder_path,
                        "old_name": old_name,
                        "new_name": restored_mod,
                        "category": "tech_module_restore",
                    })
                    seen_file_ids.add(fid)
                continue

            # 2. Tệp hệ thống TongQuan.md: chỉ đổi khi không trùng trong thư mục (nhường [06] cách ly bản dư trước)
            if old_name == "TongQuan.md":
                if len(tongquan_items) > 1:
                    continue
                new_tq = _tongquan_target_name(folder_path, engine)
                if sc.nfc(new_tq) in existing_names and sc.nfc(new_tq) != sc.nfc(old_name):
                    skipped_dup_tongquan += 1
                    continue
                if old_name != new_tq:
                    plan.append({
                        "id": fid,
                        "path": folder_path,
                        "old_name": old_name,
                        "new_name": new_tq,
                        "category": "system_tongquan",
                    })
                    seen_file_ids.add(fid)
                continue

            # 3. Kiểm tra bất biến: bỏ qua mọi tệp đã đạt Chuẩn V6 / bảng Danh Mục / ngoại lệ kỹ thuật
            if is_already_v6(old_name, mime, folder_path):
                continue

            # 4. Tệp Sách & Âm nhạc đang có tiền tố [STT]
            if re.match(r"^\[\d{2,3}\]\s+", old_name):
                m_stt = re.match(r"^\[(\d{2,3})\]", old_name)
                stt_num = int(m_stt.group(1)) if m_stt else 1
                base_v6, ext = clean_book_or_music_name(old_name, folder_path, engine, local_map, mime=mime)
                folder_candidates.append({
                    "id": fid,
                    "path": folder_path,
                    "old_name": old_name,
                    "base_v6": base_v6,
                    "ext": ext,
                    "date_str": "",
                    "stt": stt_num,
                    "category": "book_music_v6",
                })
                seen_file_ids.add(fid)
                continue

            # 5. Tệp thường dạng cũ cần chuẩn hóa
            base_v6, ext, date_str, stt_num = convert_regular_file(old_name, folder_path, engine, local_map, mime=mime)
            folder_candidates.append({
                "id": fid,
                "path": folder_path,
                "old_name": old_name,
                "base_v6": base_v6,
                "ext": ext,
                "date_str": date_str,
                "stt": stt_num,
                "category": "regular_v6",
            })
            seen_file_ids.add(fid)

        # Kiểm tra và khử đụng độ với các tệp đang tồn tại sẵn trong thư mục
        by_target = defaultdict(list)
        for cand in folder_candidates:
            full_target = f"{cand['base_v6']}{cand['ext']}"
            by_target[full_target].append(cand)

        taken = {
            sc.nfc(it["name"]) for it in items
            if it.get("mimeType") != FOLDER_MIME and it["id"] not in seen_file_ids
        }
        for full_target, group in by_target.items():
            if len(group) == 1 and sc.nfc(full_target) not in taken:
                c = group[0]
                if c["old_name"] != full_target:
                    taken.add(sc.nfc(full_target))
                    plan.append({
                        "id": c["id"],
                        "path": c["path"],
                        "old_name": c["old_name"],
                        "new_name": full_target,
                        "category": c["category"],
                    })
            else:
                group.sort(key=lambda x: x["stt"])
                dates = {g["date_str"] for g in group if g["date_str"]}
                for idx_g, c in enumerate(group, start=1):
                    if len(dates) == len(group) and c["date_str"] and c["date_str"] not in c["base_v6"]:
                        disamb_base = f"{c['base_v6']}, {c['date_str']}"
                    else:
                        label = "Bản" if c["category"] == "book_music_v6" else "Phần"
                        disamb_base = f"{c['base_v6']}, {label} {idx_g:02d}"
                    final_name = f"{disamb_base}{c['ext']}"
                    while sc.nfc(final_name) in taken:
                        idx_g += 1
                        final_name = f"{c['base_v6']}, Phần {idx_g:02d}{c['ext']}"
                    taken.add(sc.nfc(final_name))
                    if c["old_name"] != final_name:
                        plan.append({
                            "id": c["id"],
                            "path": c["path"],
                            "old_name": c["old_name"],
                            "new_name": final_name,
                            "category": c["category"],
                        })

    if skipped_dup_tongquan:
        sc.log(f"  [!] Đã bỏ qua {skipped_dup_tongquan} thư mục/bản TongQuan.md trùng lặp để [06] RÀ SOÁT TRÙNG LẶP cách ly trước.")

    if include_sheets:
        print("[3/3] Kiểm tra tên bảng Google Sheets Danh Mục Hệ Thống...")
        for path_key, s_info in sheets_log.items():
            if branch_prefix and not (path_key == branch_prefix or path_key.startswith(prefix_slash)):
                continue
            new_sheet_name = sc.normalize_sheet_title(path_key)
            old_sheet_name = s_info.get("sheet_name", "")
            sid = s_info.get("sheet_id")
            if sid and sid not in seen_file_ids and old_sheet_name != new_sheet_name:
                plan.append({
                    "id": sid,
                    "path": f"{path_key}/[00] TỔNG QUAN",
                    "old_name": old_sheet_name,
                    "new_name": new_sheet_name,
                    "category": "system_sheet",
                })
                seen_file_ids.add(sid)
    else:
        print("[3/3] Bỏ qua tên bảng Danh Mục Hệ Thống (mặc định để `[05] sheet_engine.py --sua-ten-bang` xử lý).")

    return plan


# ============================================================================
# 4. BỘ THỰC THI ĐA LUỒNG CÓ CHECKPOINT (CHECKPOINTED BATCH EXECUTOR)
# ============================================================================
def execute_rename_plan(
    categories: Optional[List[str]] = None,
    branch_prefix: Optional[str] = None,
    limit: int = 3500,
    workers: int = 24,
    assume_yes: bool = False,
):
    if not PLAN_PATH.exists():
        print("Chưa có file kế hoạch. Vui lòng chạy --plan trước.")
        sys.exit(1)

    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    executed: Dict[str, dict] = sc.read_json(EXEC_LOG_PATH, {}) or {}

    pending = []
    prefix_slash = branch_prefix.rstrip("/") + "/" if branch_prefix else ""
    for item in plan:
        fid = item["id"]
        if item["old_name"] == item["new_name"]:
            continue
        if fid in executed and executed[fid].get("new_name") == item["new_name"]:
            continue
        if categories and item["category"] not in categories:
            continue
        if branch_prefix and not (item["path"] == branch_prefix or item["path"].startswith(prefix_slash)):
            continue
        pending.append(item)

    batch = pending[:limit]
    chunk_size = 8
    chunks = [batch[i : i + chunk_size] for i in range(0, len(batch), chunk_size)]
    print(
        f"Đã hoàn thành trước đó: {len(executed)} | Chờ xử lý khớp bộ lọc: {len(pending)} | "
        f"Lô hiện tại: {len(batch)} ({len(chunks)} chunks, workers={workers})",
        flush=True,
    )
    if not batch:
        return
    if not sc.confirm(f"Thực thi đổi tên {len(batch)} mục trên Drive?", assume_yes):
        return

    drive = sc.create_drive()
    index_data = sc.load_index()
    _, by_id = sc.build_id_map(index_data)

    t0 = time.time()
    done_items = 0
    ok_count = 0
    fail_count = 0
    failures = []
    last_ckpt = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(drive.batch_rename, [(it["id"], it["new_name"]) for it in ch]): ch
            for ch in chunks
        }
        for fut in concurrent.futures.as_completed(futures):
            ch_by_id = {it["id"]: it for it in futures[fut]}
            for fid, success, err in fut.result():
                item = ch_by_id[fid]
                done_items += 1
                if success:
                    ok_count += 1
                    executed[fid] = {
                        "old_name": item["old_name"],
                        "new_name": item["new_name"],
                        "category": item["category"],
                        "ts": int(time.time()),
                    }
                    if fid in by_id:
                        parent_p, item_ref = by_id[fid]
                        was_folder = item_ref.get("mimeType") == sc.FOLDER_MIME
                        item_ref["name"] = item["new_name"]
                        if was_folder:
                            old_fp = f"{parent_p}/{item['old_name']}"
                            new_fp = f"{parent_p}/{item['new_name']}"
                            if old_fp in index_data or any(k.startswith(old_fp + "/") for k in index_data):
                                moved_keys = [k for k in list(index_data.keys()) if k == old_fp or k.startswith(old_fp + "/")]
                                for ok in moved_keys:
                                    nk = new_fp + ok[len(old_fp):]
                                    index_data[nk] = index_data.pop(ok)
                                _, by_id = sc.build_id_map(index_data)
                else:
                    fail_count += 1
                    failures.append((fid, item["old_name"], item["new_name"], err))

            if done_items - last_ckpt >= 250 or done_items == len(batch):
                last_ckpt = done_items
                elapsed = time.time() - t0
                rate = done_items / elapsed if elapsed > 0 else 0
                print(
                    f"  -> Tiến độ: {done_items}/{len(batch)} | Thành công: {ok_count} | "
                    f"Lỗi: {fail_count} | Tốc độ: {rate:.1f} tệp/giây",
                    flush=True,
                )
                sc.write_json(EXEC_LOG_PATH, executed, indent=None)

    sc.save_index(index_data, INDEX_PATH)
    print(f"Đã cập nhật chỉ mục {INDEX_PATH} (compact) sau khi hoàn tất lô.")

    if failures:
        print(f"\n[CẢNH BÁO] Có {len(failures)} mục lỗi:")
        for fid, o, n, e in failures[:15]:
            print(f"  - {fid}: {o} -> {n} | {e[:160]}")


def main():
    parser = argparse.ArgumentParser(description="Bộ Công Cụ Chuẩn Hóa Hệ Thống [A] STORAGE — Chuẩn V6 (v2.0)")
    parser.add_argument("--plan", action="store_true", help="Sinh kế hoạch đổi tên Chuẩn V6 toàn kho")
    parser.add_argument("--execute", "--thuc-thi", dest="execute", action="store_true", help="Thực thi đổi tên theo lô có checkpoint")
    parser.add_argument("--dong-y", action="store_true", help="Không hỏi xác nhận khi thực thi")
    parser.add_argument("--categories", type=str, default="", help="Danh sách category cách nhau dấu phẩy")
    parser.add_argument("--branch", "--nhanh", dest="branch", type=str, default="", help="Nhánh thư mục cần giới hạn")
    parser.add_argument("--kem-bang", action="store_true", help="Kèm chuẩn hóa tên các bảng Danh Mục Hệ Thống")
    parser.add_argument("--limit", type=int, default=3500, help="Số lượng tối đa mỗi lô")
    parser.add_argument("--workers", "--luong", dest="workers", type=int, default=24, help="Số luồng song song")
    args = parser.parse_args()

    branch = sc.normalize_branch(args.branch) if args.branch else None
    if branch == sc.ROOT_NAME:
        branch = None

    if args.plan or (not args.execute):
        index_data = sc.load_index()
        sheets_log = load_or_build_sheets_log(index_data)
        plan = build_full_rename_plan(index_data, sheets_log, branch_prefix=branch, include_sheets=args.kem_bang)
        sc.write_json(PLAN_PATH, plan, indent=2)
        by_cat = Counter(x["category"] for x in plan)
        print(f"\nĐã lưu kế hoạch vào {PLAN_PATH} (Tổng cộng: {len(plan)} mục):")
        for k, v in sorted(by_cat.items()):
            print(f"  - {k}: {v} mục")
        if not args.execute and plan:
            print("(Chạy thử — thêm --execute --thuc-thi để áp dụng lên Drive.)")

    if args.execute:
        cats = [c.strip() for c in args.categories.split(",") if c.strip()] if args.categories else None
        execute_rename_plan(
            categories=cats,
            branch_prefix=branch,
            limit=args.limit,
            workers=args.workers,
            assume_yes=args.dong_y,
        )


if __name__ == "__main__":
    main()

