#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PHÂN TÍCH NỘI DUNG, NGÔN NGỮ, TỪ KHÓA, TRÙNG NỘI DUNG & GỢI Ý TÊN CHUẨN V6 — [A] STORAGE (v3.1)
==================================================================================================
Chương trình `[14] PHÂN TÍCH NỘI DUNG/content_analyzer.py` khai thác dữ liệu từ `[13] ĐỌC TỆP`:

1. `phan-tich`      : Phân tích toàn diện các tệp trong bộ đệm (hoặc tự động gọi `[13]` trích xuất trước
                      khi truyền `--tu-dong-doc`): nhận diện ngôn ngữ, đếm từ/trang/thời gian đọc,
                      rút trích từ khóa đặc trưng TF-IDF, phân loại chủ đề Chuẩn V6, kiểm tra chất lượng
                      (`can_ocr`, `co_mat_khau`, `tep_hong`, `tep_rong`, `sai_khop_dinh_dang`, `lech_chu_de`)
                      và xuất báo cáo Markdown + CSV.
2. `goi-y-ten`      : Đề xuất tên tệp Chuẩn V6 (`Tiêu Đề - Tác Giả.[đuôi]`) từ siêu dữ liệu nội dung bên trong
                      tệp cho những tệp có tên mơ hồ hoặc thiếu thông tin bổ sung. Mặc định chạy thử;
                      khi có `--thuc-thi` sẽ đổi tên tại chỗ (giữ nguyên 100% ID) kèm nhật kí hoàn tác.
3. `hoan-tac-ten`   : Hoàn tác một lô đổi tên theo siêu dữ liệu từ `content_rename_log.json`.
4. `trung-noi-dung` : Phát hiện trùng lặp nội dung tuyệt đối (`SHA-256`) và trùng lặp gần (`SimHash 64-bit`,
                      khoảng cách Hamming ≤ `--nguong-hamming`) kể cả khác định dạng/khác tên.
5. `tim-noi-dung`   : Tìm kiếm toàn văn (có dấu/không dấu hoặc `--regex`) trên toàn bộ văn bản đã trích xuất,
                      trả về đoạn trích ngữ cảnh.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple


from storage_suite import core as sc


from storage_suite.media import file_reader as fr


# ---------------------------------------------------------------------------
# 1. NHẬN DIỆN NGÔN NGỮ & TỪ DỪNG (STOPWORDS)
# ---------------------------------------------------------------------------

VI_SPECIFIC_CHARS = set(
    "ăâđêôơưĂÂĐÊÔƠƯ"
    "àáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩị"
    "òóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ"
    "ÀÁẢÃẠẰẮẲẴẶẦẤẨẪẬÈÉẺẼẸỀẾỂỄỆÌÍỈĨỊ"
    "ÒÓỎÕỌỒỐỔỖỘỜỚỞỠỢÙÚỦŨỤỪỨỬỮỰỲÝỶỸỴ"
)

STOPWORDS_VI = {
    "của", "và", "các", "trong", "những", "được", "người", "không", "với", "cho",
    "này", "một", "là", "có", "để", "khi", "theo", "về", "từ", "như", "nhưng",
    "cũng", "vào", "đã", "đang", "sẽ", "trên", "dưới", "hay", "hoặc", "nếu",
    "thì", "mà", "bởi", "vì", "do", "qua", "lại", "ra", "đến", "tại", "còn",
    "rất", "nhiều", "ít", "hơn", "nhất", "cùng", "khác", "mỗi", "mọi", "tất",
    "cả", "chỉ", "sau", "trước", "giữa", "ngoài", "bên", "theo", "việc", "cách",
    "phần", "chương", "mục", "bài", "trang", "hình", "bảng", "năm", "ngày",
}

STOPWORDS_EN = {
    "the", "and", "of", "to", "in", "is", "that", "for", "with", "as", "on",
    "are", "this", "by", "be", "from", "or", "at", "an", "not", "but", "have",
    "has", "had", "were", "was", "which", "their", "they", "you", "all", "can",
    "her", "his", "its", "one", "our", "out", "who", "will", "would", "about",
    "into", "more", "other", "some", "such", "than", "then", "them", "these",
    "time", "two", "very", "what", "when", "where", "how", "also", "been",
    "chapter", "page", "figure", "table", "section", "part",
}

STOPWORDS_FR = {
    "le", "la", "les", "des", "dans", "une", "pour", "que", "est", "sur",
    "avec", "plus", "par", "pas", "sont", "mais", "comme", "tout", "aux", "cette",
}

STOPWORDS_ES = {
    "el", "la", "los", "las", "del", "una", "para", "por", "con", "como",
    "más", "sobre", "sus", "este", "esta", "entre", "cuando", "todo", "también",
}

STOPWORDS_DE = {
    "der", "die", "das", "und", "den", "von", "mit", "sich", "auf", "für",
    "nicht", "ist", "dem", "als", "auch", "es", "an", "werden", "aus", "er",
}

ALL_STOPWORDS = STOPWORDS_VI | STOPWORDS_EN | STOPWORDS_FR | STOPWORDS_ES | STOPWORDS_DE


def detect_language(text: str, metadata: Optional[dict] = None) -> Tuple[str, float]:
    """
    Nhận diện ngôn ngữ chính của văn bản (`vi`, `en`, `fr`, `es`, `de`, `zh`, `ja`, `ru`, `unknown`).
    Trả về `(mã_ngôn_ngữ, độ_tin_cậy_0_đến_1)`.
    """
    sample = (text or "")[:25_000]
    if not sample.strip():
        meta_lang = str((metadata or {}).get("language", "")).lower().strip()
        if meta_lang.startswith("vi"):
            return "vi", 0.7
        if meta_lang.startswith("en"):
            return "en", 0.7
        if meta_lang:
            return meta_lang[:2], 0.6
        return "unknown", 0.0

    # Kiểm tra hệ chữ tượng hình / Cyrillic trước
    cjk_count = len(re.findall(r"[\u4e00-\u9fff]", sample))
    kana_count = len(re.findall(r"[\u3040-\u30ff]", sample))
    cyr_count = len(re.findall(r"[\u0400-\u04ff]", sample))
    alpha_count = max(1, sum(1 for ch in sample if ch.isalpha()))

    if kana_count / alpha_count > 0.12:
        return "ja", round(min(0.99, 0.6 + kana_count / alpha_count), 2)
    if cjk_count / alpha_count > 0.25:
        return "zh", round(min(0.99, 0.6 + cjk_count / alpha_count), 2)
    if cyr_count / alpha_count > 0.25:
        return "ru", round(min(0.99, 0.6 + cyr_count / alpha_count), 2)

    words = [w.lower() for w in re.findall(r"[A-Za-zÀ-ỹ]+", sample)]
    if not words:
        return "unknown", 0.0

    total_w = len(words)
    vi_char_words = sum(1 for w in words if any(ch in VI_SPECIFIC_CHARS for ch in w))
    scores = {
        "vi": (sum(1 for w in words if w in STOPWORDS_VI) + vi_char_words * 1.4) / total_w,
        "en": sum(1 for w in words if w in STOPWORDS_EN) / total_w,
        "fr": sum(1 for w in words if w in STOPWORDS_FR) / total_w,
        "es": sum(1 for w in words if w in STOPWORDS_ES) / total_w,
        "de": sum(1 for w in words if w in STOPWORDS_DE) / total_w,
    }
    best_lang, best_score = max(scores.items(), key=lambda kv: kv[1])
    if best_score < 0.015:
        if vi_char_words >= 2:
            return "vi", 0.65
        return "en", 0.50
    conf = min(0.99, round(0.45 + best_score * 2.2, 2))
    return best_lang, conf


# ---------------------------------------------------------------------------
# 2. TRÍCH XUẤT TỪ KHÓA ĐẶC TRƯNG TF-IDF
# ---------------------------------------------------------------------------

def _tokenize_terms(text: str) -> Tuple[List[str], List[str]]:
    """Tách từ đơn và cụm 2 từ (bigram) có nghĩa từ văn bản."""
    raw_words = [w.lower() for w in re.findall(r"[A-Za-zÀ-ỹ0-9]+", (text or "")[:60_000])]
    unigrams: List[str] = []
    for w in raw_words:
        if len(w) < 3 or w.isdigit() or w in ALL_STOPWORDS:
            continue
        unigrams.append(w)

    bigrams: List[str] = []
    for i in range(len(raw_words) - 1):
        w1, w2 = raw_words[i], raw_words[i + 1]
        if len(w1) < 2 or len(w2) < 2 or w1.isdigit() or w2.isdigit():
            continue
        if w1 in ALL_STOPWORDS or w2 in ALL_STOPWORDS:
            continue
        bigrams.append(f"{w1} {w2}")
    return unigrams, bigrams


def extract_keywords_tfidf(
    records: Sequence[Dict[str, Any]],
    top_k: int = 8,
) -> Dict[str, List[str]]:
    """
    Tính điểm TF-IDF trên tập bản ghi để rút trích `top_k` từ khóa/cụm từ đặc trưng nhất cho mỗi tệp.
    Trả về `{file_id: [tu_khoa_1, tu_khoa_2, ...]}`.
    """
    doc_tf: Dict[str, Dict[str, float]] = {}
    df: Dict[str, int] = collections.Counter()
    n_docs = max(1, len(records))

    for rec in records:
        fid = rec.get("id") or rec.get("name", "")
        meta = rec.get("metadata") or {}
        header_txt = " ".join([
            str(meta.get("title", "")),
            str(meta.get("subject", "")),
            str(meta.get("keywords", "")),
            " ".join(rec.get("outline") or []),
        ])
        body_txt = rec.get("text") or rec.get("text_preview") or ""
        uni, bi = _tokenize_terms(f"{header_txt}\n{body_txt}")
        header_uni, header_bi = _tokenize_terms(header_txt)
        header_set = set(header_uni) | set(header_bi)

        counts: Dict[str, int] = collections.Counter(uni)
        bi_counts = collections.Counter(bi)
        for bg, cnt in bi_counts.items():
            if cnt >= 2 or bg in header_set:
                counts[bg] = cnt

        tf_map: Dict[str, float] = {}
        for term, cnt in counts.items():
            weight = 1.0 + math.log(cnt)
            if " " in term:
                weight *= 1.25
            if term in header_set:
                weight *= 1.35
            tf_map[term] = weight
        doc_tf[fid] = tf_map
        for term in tf_map:
            df[term] += 1

    out: Dict[str, List[str]] = {}
    for fid, tf_map in doc_tf.items():
        scored: List[Tuple[float, str]] = []
        for term, tf_val in tf_map.items():
            idf = math.log((1.0 + n_docs) / (1.0 + df[term])) + 1.0
            scored.append((tf_val * idf, term))
        scored.sort(key=lambda x: (-x[0], x[1]))

        chosen: List[str] = []
        covered_tokens: Set[str] = set()
        for _, term in scored:
            toks = set(term.split())
            if len(toks) == 1 and (term in covered_tokens):
                continue
            chosen.append(term)
            covered_tokens.update(toks)
            if len(chosen) >= top_k:
                break
        out[fid] = chosen
    return out


# ---------------------------------------------------------------------------
# 3. PHÂN LOẠI CHỦ ĐỀ CHUẨN V6 & PHÁT HIỆN LỆCH CHỦ ĐỀ
# ---------------------------------------------------------------------------

CONTENT_TOPIC_ROUTES: List[Tuple[str, Tuple[str, ...], str]] = [
    (
        "Triết Học",
        ("triet hoc", "sieu hinh", "nhan thuc luan", "logic hoc", "dao duc hoc", "my hoc",
         "hien sinh", "hien tuong hoc", "descartes", "kant", "hegel", "nietzsche", "plato",
         "aristotle", "heidegger", "spinoza", "marx", "philosophy", "metaphysics", "epistemology"),
        "[A] STORAGE/[05] SƯU TẦM/[01] SÁCH/[01] TRIẾT HỌC",
    ),
    (
        "Tâm Lý Học",
        ("tam ly hoc", "phan tam hoc", "tam than", "hanh vi", "cam xuc", "nhan cach",
         "freud", "jung", "adler", "lacan", "psychology", "psychotherapy", "cognitive", "trauma"),
        "[A] STORAGE/[05] SƯU TẦM/[01] SÁCH/[02] TÂM LÝ HỌC",
    ),
    (
        "Tôn Giáo - Tín Ngưỡng",
        ("ton giao", "phat giao", "cong giao", "kito giao", "hoi giao", "kinh thanh",
         "kinh phat", "thien tong", "bat nha", "tin nguong", "than hoc", "buddhism", "theology"),
        "[A] STORAGE/[05] SƯU TẦM/[01] SÁCH/[03] TÔN GIÁO - TÍN NGƯỠNG",
    ),
    (
        "Huyền Học - Tâm Linh",
        ("tu vi", "kinh dich", "phong thuy", "phi tinh", "bat tu", "tuong phap", "huyen hoc",
         "chiem tinh", "tarot", "co hoc tinh hoa", "am duong", "ngu hanh", "que dich", "astrology"),
        "[A] STORAGE/[05] SƯU TẦM/[01] SÁCH/[04] HUYỀN HỌC - TÂM LINH",
    ),
    (
        "Văn Học",
        ("tieu thuyet", "van hoc", "truyen ngan", "thi tap", "tho ca", "truong篇", "kich",
         "novel", "literature", "poetry", "fiction"),
        "[A] STORAGE/[05] SƯU TẦM/[01] SÁCH/[05] VĂN HỌC",
    ),
    (
        "Lịch Sử",
        ("lich su", "co dai", "trung dai", "can dai", "su hoc", "viet nam su luoc",
         "dai viet su ky", "trieu dai", "chien tranh", "history", "civilization", "dynasty"),
        "[A] STORAGE/[05] SƯU TẦM/[01] SÁCH/[06] LỊCH SỬ",
    ),
    (
        "Văn Hoá - Xã Hội",
        ("van hoa", "xa hoi hoc", "nhan hoc", "dan toc hoc", "phong tuc", "le hoi",
         "sociology", "anthropology", "culture"),
        "[A] STORAGE/[05] SƯU TẦM/[01] SÁCH/[07] VĂN HOÁ - XÃ HỘI",
    ),
    (
        "Chính Trị - Pháp Luật",
        ("chinh tri", "phap luat", "hien phap", "bo luat", "nha nuoc", "ngoai giao",
         "geopolitics", "constitutional", "legislation"),
        "[A] STORAGE/[05] SƯU TẦM/[01] SÁCH/[08] CHÍNH TRỊ - PHÁP LUẬT",
    ),
    (
        "Kinh Tế - Kinh Doanh",
        ("kinh te", "quan tri", "tai chinh", "marketing", "chung khoan", "dau tu",
         "doanh nghiep", "thuong mai", "economics", "finance", "management", "investing"),
        "[A] STORAGE/[05] SƯU TẦM/[01] SÁCH/[09] KINH TẾ - KINH DOANH",
    ),
    (
        "Khoa Học - Công Nghệ",
        ("vat ly", "hoa hoc", "sinh hoc", "toan hoc", "thien van", "tri tue nhan tao",
         "lap trinh", "thuat toan", "quantum", "physics", "mathematics", "algorithm", "computer science"),
        "[A] STORAGE/[05] SƯU TẦM/[01] SÁCH/[10] KHOA HỌC - CÔNG NGHỆ",
    ),
    (
        "Kĩ Năng - Phát Triển Bản Thân",
        ("ki nang", "ky nang", "phat trien ban than", "giao tiep", "lanh dao", "quan ly thoi gian",
         "thoi quen", "tu duy", "self-help", "productivity", "leadership"),
        "[A] STORAGE/[05] SƯU TẦM/[01] SÁCH/[12] KĨ NĂNG - PHÁT TRIỂN BẢN THÂN",
    ),
    (
        "Tiểu Sử - Hồi Ký",
        ("tieu su", "hoi ky", "tu truyen", "biography", "autobiography", "memoir"),
        "[A] STORAGE/[05] SƯU TẦM/[01] SÁCH/[13] TIỂU SỬ - HỒI KÝ",
    ),
    (
        "Sức Khoẻ - Y Học",
        ("y hoc", "suc khoe", "giai phau", "benh hoc", "duoc hoc", "dong y", "ung thu",
         "dinh duong", "chan doan", "dieu tri", "sinh ly hoc", "anatomy", "neuroanatom",
         "medical", "medicine", "clinical", "physiology", "pathology", "netter"),
        "[A] STORAGE/[05] SƯU TẦM/[01] SÁCH/[14] SỨC KHOẺ - Y HỌC",
    ),
    (
        "Giáo Dục - Nuôi Dạy Con",
        ("giao duc", "nuoi day con", "su pham", "day hoc", "pedagogy", "parenting"),
        "[A] STORAGE/[05] SƯU TẦM/[01] SÁCH/[15] GIÁO DỤC - NUÔI DẠY CON",
    ),
    (
        "Ngôn Ngữ & Chứng Chỉ",
        ("ngu phap", "tu vung", "ngon ngu hoc", "ielts", "toefl", "toeic", "hsk", "vstep",
         "linguistics", "vocabulary", "grammar"),
        "[A] STORAGE/[05] SƯU TẦM/[01] SÁCH/[17] NGÔN NGỮ",
    ),
]


def classify_topic(
    name: str,
    text: str,
    metadata: Optional[dict] = None,
    outline: Optional[Sequence[str]] = None,
) -> Tuple[str, str, int]:
    """
    Phân loại chủ đề dựa trên tên tệp, siêu dữ liệu, mục lục (trọng số x3) và nội dung văn bản (trọng số x1).
    Trả về `(nhãn_chủ_đề, nhánh_đề_xuất, điểm_khớp)`.
    """
    meta = metadata or {}
    header_raw = " ".join([
        name or "",
        str(meta.get("title", "")),
        str(meta.get("subject", "")),
        str(meta.get("keywords", "")),
        " ".join((outline or [])[:20]),
    ])
    header_norm = sc.strip_accents(sc.nfc(header_raw)).lower()
    body_norm = sc.strip_accents(sc.nfc((text or "")[:30_000])).lower()

    best_label = "Chưa Phân Loại"
    best_branch = "[A] STORAGE/[05] SƯU TẦM/[01] SÁCH/[00] CHƯA PHÂN LOẠI"
    best_score = 0

    for label, keywords, branch in CONTENT_TOPIC_ROUTES:
        score = 0
        for kw in keywords:
            kw_l = kw.lower().strip()
            if kw_l in header_norm:
                score += 3
            if body_norm:
                hits = len(re.findall(r"\b" + re.escape(kw_l) + r"\b", body_norm))
                score += min(6, hits)
        if score > best_score:
            best_score = score
            best_label = label
            best_branch = branch

    return best_label, best_branch, best_score


def is_topic_mismatch(parent_path: str, recommended_branch: str, topic_score: int) -> bool:
    """
    Phát hiện tệp có thể đặt nhầm thư mục chuyên đề:
    - Nếu tệp đang nằm trong `[00] CHƯA PHÂN LOẠI` mà điểm chủ đề ≥ 4 → gợi ý phân loại (`True`).
    - Nếu tệp đang nằm trong một nhánh sách `[05] SƯU TẦM/[01] SÁCH/[XX]` khác hẳn nhánh đề xuất và điểm ≥ 9 → `True`.
    """
    if not parent_path or not recommended_branch or topic_score < 4:
        return False
    if "[00] CHƯA PHÂN LOẠI" in parent_path and topic_score >= 4:
        return True
    books_prefix = "[A] STORAGE/[05] SƯU TẦM/[01] SÁCH/"
    if parent_path.startswith(books_prefix) and recommended_branch.startswith(books_prefix):
        curr_cat = parent_path[len(books_prefix):].split("/", 1)[0]
        rec_cat = recommended_branch[len(books_prefix):].split("/", 1)[0]
        if curr_cat != rec_cat and topic_score >= 9:
            return True
    return False


# ---------------------------------------------------------------------------
# 4. BĂM SIMHASH 64-BIT & PHÁT HIỆN TRÙNG LẶP / GẦN TRÙNG NỘI DUNG
# ---------------------------------------------------------------------------

def compute_simhash64(text: str) -> int:
    """Tính chữ ký ngữ nghĩa `SimHash 64-bit` trên các cụm 3 từ (3-shingles) đã chuẩn hóa."""
    words = [w.lower() for w in re.findall(r"[A-Za-zÀ-ỹ0-9]+", sc.nfc(text or "")[:100_000]) if len(w) >= 2]
    if not words:
        return 0
    if len(words) < 3:
        shingles = [" ".join(words)]
    else:
        shingles = [f"{words[i]} {words[i + 1]} {words[i + 2]}" for i in range(len(words) - 2)]

    freq = collections.Counter(shingles)
    v = [0] * 64
    for sh, weight in freq.items():
        digest = hashlib.blake2b(sh.encode("utf-8"), digest_size=8).digest()
        h = int.from_bytes(digest, "big")
        for bit in range(64):
            if (h >> bit) & 1:
                v[bit] += weight
            else:
                v[bit] -= weight

    fingerprint = 0
    for bit in range(64):
        if v[bit] > 0:
            fingerprint |= (1 << bit)
    return fingerprint


def hamming_distance64(a: int, b: int) -> int:
    """Số bit khác nhau giữa hai chữ ký SimHash 64-bit."""
    return (a ^ b).bit_count()


def find_content_duplicates(
    records: Sequence[Dict[str, Any]],
    max_hamming: int = 3,
    min_words: int = 40,
) -> Dict[str, Any]:
    """
    Phát hiện:
    1. `exact_groups` : Các nhóm tệp có cùng `sha256` hoặc cùng băm văn bản chuẩn hóa.
    2. `near_pairs`   : Các cặp tệp khác `sha256` nhưng có khoảng cách Hamming SimHash ≤ `max_hamming`
                        (sử dụng chia 4 băng 16-bit để lọc ứng viên nhanh).
    """
    by_sha: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)
    sim_items: List[Tuple[int, Dict[str, Any]]] = []

    for rec in records:
        if rec.get("status") not in {"ok", "can_ocr"}:
            continue
        sha = rec.get("sha256", "")
        if sha:
            by_sha[sha].append(rec)
        wc = int((rec.get("stats") or {}).get("word_count") or 0)
        if wc < min_words:
            continue
        sh_hex = rec.get("simhash")
        if sh_hex:
            sh_val = int(sh_hex, 16)
        else:
            txt = rec.get("text") or rec.get("text_preview") or ""
            sh_val = compute_simhash64(txt)
            rec["simhash"] = f"{sh_val:016x}"
        if sh_val != 0:
            sim_items.append((sh_val, rec))

    exact_groups = [
        {"sha256": sha, "count": len(grp), "items": grp}
        for sha, grp in by_sha.items()
        if len(grp) > 1
    ]
    exact_groups.sort(key=lambda g: -g["count"])

    # LSH 4 băng 16-bit (nếu max_hamming <= 3 thì ít nhất 1 trong 4 băng phải trùng khớp tuyệt đối)
    buckets: Dict[Tuple[int, int], List[int]] = collections.defaultdict(list)
    for idx, (sh_val, _) in enumerate(sim_items):
        for band in range(4):
            piece = (sh_val >> (band * 16)) & 0xFFFF
            buckets[(band, piece)].append(idx)

    seen_pairs: Set[Tuple[int, int]] = set()
    near_pairs: List[Dict[str, Any]] = []

    def _CheckPair(i: int, j: int) -> None:
        if i >= j:
            i, j = j, i
        if (i, j) in seen_pairs:
            return
        seen_pairs.add((i, j))
        sh_a, rec_a = sim_items[i]
        sh_b, rec_b = sim_items[j]
        if rec_a.get("id") == rec_b.get("id"):
            return
        if rec_a.get("sha256") and rec_a.get("sha256") == rec_b.get("sha256"):
            return
        dist = hamming_distance64(sh_a, sh_b)
        if dist <= max_hamming:
            sim_pct = round((64 - dist) * 100.0 / 64.0, 1)
            near_pairs.append({
                "hamming": dist,
                "similarity_pct": sim_pct,
                "a": rec_a,
                "b": rec_b,
            })

    if max_hamming <= 3:
        for idxs in buckets.values():
            if len(idxs) > 1:
                for a_pos in range(len(idxs)):
                    for b_pos in range(a_pos + 1, len(idxs)):
                        _CheckPair(idxs[a_pos], idxs[b_pos])
    else:
        for i in range(len(sim_items)):
            for j in range(i + 1, len(sim_items)):
                _CheckPair(i, j)

    near_pairs.sort(key=lambda p: (p["hamming"], p["a"].get("name", "")))
    return {
        "exact_groups": exact_groups,
        "near_pairs": near_pairs,
    }


# ---------------------------------------------------------------------------
# 5. ĐỀ XUẤT & ÁP DỤNG TÊN TỆP CHUẨN V6 TỪ SIÊU DỮ LIỆU NỘI DUNG
# ---------------------------------------------------------------------------

_BAD_META_TITLES = {
    "untitled", "document", "doc1", "book1", "presentation1", "slide 1",
    "microsoft word", "powerpoint presentation", "trang bìa", "mục lục",
    "table of contents", "cover", "unknown", "none", "null",
}

_BAD_META_AUTHORS = {
    "admin", "administrator", "user", "windows user", "microsoft", "microsoft office user",
    "dell", "hp", "asus", "acer", "lenovo", "pc", "owner", "unknown", "none", "author",
}

_OPAQUE_NAME_RE = re.compile(
    r"^(scan|img|doc|document|file|book|ebook|untitled|new|copy|tai\s*lieu|sach)[\s_-]*\d*$"
    r"|^[0-9a-f]{8,}$"
    r"|^\d{3,}$",
    flags=re.I,
)


def _clean_meta_field(val: str, is_author: bool = False) -> str:
    s = sc.nfc(str(val or "")).strip()
    if not s:
        return ""
    s = re.sub(r"^Microsoft\s+Word\s*-\s*", "", s, flags=re.I)
    s = re.sub(r"\.(docx?|pptx?|xlsx?|pdf|epub|mobi|md|txt)$", "", s, flags=re.I)
    s = re.sub(r"\((z-lib\.org|libgen\.li|annas-archive[^)]*)\)", "", s, flags=re.I)
    s = re.sub(r"[_]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" -–—:;,.")
    if len(s) < 3 or len(s) > 110:
        return ""
    low = sc.strip_accents(s).lower()
    if is_author:
        if low in _BAD_META_AUTHORS or re.match(r"^(user|admin|pc|laptop)\d*$", low):
            return ""
    else:
        if low in _BAD_META_TITLES or re.match(r"^(slide|page|trang|chuong|chapter)\s*\d+$", low):
            return ""
    if s.isdigit():
        return ""
    return sc.title_case_vn(s)


def _folder_fallback_context(parent_path: str) -> str:
    if not parent_path:
        return "Storage"
    segs = [s for s in parent_path.split("/") if s and s != sc.TONG_QUAN_FOLDER]
    last = segs[-1] if segs else "Storage"
    clean = re.sub(r"^\[\d{2,3}\]\s*", "", last)
    clean = re.sub(r"^\[([^\]]+)\]\s*(.+)$", lambda m: f"{m.group(1).strip()} - {m.group(2).strip()}", clean)
    clean = re.sub(r"^\[([^\]]+)\]$", r"\1", clean)
    return sc.title_case_vn(clean.strip()) or "Storage"


def is_opaque_or_incomplete_filename(name: str, mime: str = "", parent_path: str = "") -> Tuple[bool, str]:
    """
    Kiểm tra xem tên tệp hiện tại có mơ hồ (toàn số/mã băm/untitled), vi phạm quy ước,
    hoặc thiếu phần `- Thông Tin Bổ Sung` cần làm giàu từ siêu dữ liệu bên trong hay không.
    """
    if sc.is_tech_exception(parent_path, name):
        return False, ""
    base, _ = sc.split_ext(name, mime)
    main_part = base.split(" - ", 1)[0].strip()
    norm_main = sc.strip_accents(main_part).lower().strip()
    if _OPAQUE_NAME_RE.match(norm_main):
        return True, "TEN_MO_HO"
    issues = sc.check_file_name(name, mime=mime, parent_path=parent_path)
    codes = [code for _, code, _ in issues]
    if any(sev in {"LỖI", "CẢNH BÁO"} for sev, _, _ in issues):
        return True, ",".join(codes)
    if "THIEU_THONG_TIN_BO_SUNG" in codes:
        return True, "THIEU_THONG_TIN_BO_SUNG"
    return False, ""


def suggest_v6_name_from_content(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Dựng tên tệp Chuẩn V6 (`<Tiêu Đề> - <Tác Giả / Ngữ Cảnh>.[đuôi]`) từ siêu dữ liệu
    và dàn ý bên trong tệp nếu tên hiện tại mơ hồ hoặc thiếu thông tin bổ sung.
    """
    name = record.get("name", "")
    mime = record.get("mimeType", "")
    parent_path = record.get("parent_path", "")
    if not name or sc.is_tech_exception(parent_path, name):
        return None
    if name.startswith(("Tổng Quan Hệ Thống -", "Danh Mục Hệ Thống -")):
        return None

    needs_fix, reason = is_opaque_or_incomplete_filename(name, mime=mime, parent_path=parent_path)
    if not needs_fix:
        return None

    base, ext = sc.split_ext(name, mime)
    ext_low = ext.lower()
    meta = record.get("metadata") or {}
    outline = record.get("outline") or []

    meta_title = _clean_meta_field(meta.get("title", ""), is_author=False)
    if not meta_title and outline:
        first_h = re.sub(r"^Slide\s+\d+:\s*", "", str(outline[0]))
        meta_title = _clean_meta_field(first_h, is_author=False)
    meta_author = _clean_meta_field(meta.get("author", ""), is_author=True)

    if reason == "THIEU_THONG_TIN_BO_SUNG":
        # Giữ nguyên phần tên chính đã tốt, chỉ bổ sung Tác giả (hoặc ngữ cảnh thư mục nếu có meta)
        clean_main = sc.title_case_vn(base.strip())
        suffix = meta_author or (meta_title if meta_title and sc.strip_accents(meta_title).lower() != sc.strip_accents(clean_main).lower() else "")
        if not suffix:
            return None
        candidate_base = f"{clean_main} - {suffix}"
    else:
        # Tên hiện tại mơ hồ hoặc lỗi quy ước: ưu tiên tiêu đề nội dung
        main_title = meta_title
        if not main_title:
            fixed = sc.safe_fix_name(name, is_folder=False, mime=mime)
            fixed_base, _ = sc.split_ext(fixed, mime)
            main_title = fixed_base.split(" - ", 1)[0].strip()
        if not main_title or _OPAQUE_NAME_RE.match(sc.strip_accents(main_title).lower()):
            return None
        existing_suffix = base.split(" - ", 1)[1].strip() if " - " in base else ""
        suffix = meta_author or (sc.title_case_vn(existing_suffix) if existing_suffix else _folder_fallback_context(parent_path))
        if sc.strip_accents(main_title).lower() == sc.strip_accents(suffix).lower():
            suffix = _folder_fallback_context(parent_path)
        candidate_base = f"{main_title} - {suffix}" if suffix else main_title

    candidate_base = re.sub(r"\s+", " ", candidate_base).strip()
    new_name = f"{candidate_base}.{ext_low}" if (ext_low and mime not in sc.GOOGLE_NATIVE_MIMES) else candidate_base
    if new_name == name:
        return None

    # Chỉ đề xuất nếu tên mới đạt 0 LỖI và 0 CẢNH BÁO theo Chuẩn V6
    post_issues = sc.check_file_name(new_name, mime=mime, parent_path=parent_path)
    if any(sev in {"LỖI", "CẢNH BÁO"} for sev, _, _ in post_issues):
        return None

    return {
        "id": record.get("id", ""),
        "old_name": name,
        "new_name": new_name,
        "parent_path": parent_path,
        "reason": reason,
        "meta_title": meta_title,
        "meta_author": meta_author,
    }


def apply_rename_suggestions(
    suggestions: Sequence[Dict[str, Any]],
    drive: sc.Drive,
    index: Optional[dict] = None,
    execute: bool = False,
) -> Dict[str, Any]:
    """
    Thực thi (hoặc chạy thử) đổi tên tại chỗ theo siêu dữ liệu nội dung,
    ghi nhật kí hoàn tác vào `content_rename_log.json` và đồng bộ `storage_index.json`.
    """
    batch_id = f"content_rename_{sc.now_stamp()}"
    if not execute:
        return {
            "batch_id": batch_id,
            "dry_run": True,
            "planned": len(suggestions),
            "renamed": 0,
            "failed": 0,
            "items": list(suggestions),
        }

    pairs = [(s["id"], s["new_name"]) for s in suggestions if s.get("id") and s.get("new_name")]
    results = drive.batch_rename(pairs)
    ok_ids = {fid for fid, ok, _ in results if ok}
    failed = sum(1 for _, ok, _ in results if not ok)

    executed_ops: List[Dict[str, Any]] = []
    for s in suggestions:
        if s.get("id") in ok_ids:
            executed_ops.append({
                "id": s["id"],
                "old_name": s["old_name"],
                "new_name": s["new_name"],
                "parent_path": s.get("parent_path", ""),
                "reason": s.get("reason", ""),
            })
            # Cập nhật cache record
            rec = fr.load_cached_record(s["id"], include_text=True)
            if rec:
                txt = rec.pop("text", "")
                rec["name"] = s["new_name"]
                if rec.get("parent_path"):
                    rec["path"] = f"{rec['parent_path']}/{s['new_name']}"
                fr.save_cached_record(rec, txt)

    if index and executed_ops:
        _, id_map = sc.build_id_map(index)
        for op in executed_ops:
            if op["id"] in id_map:
                _, item = id_map[op["id"]]
                item["name"] = op["new_name"]
        sc.save_index(index)

    if executed_ops:
        log_data = sc.read_json(sc.content_rename_log_path(), default={"batches": []})
        if not isinstance(log_data, dict) or "batches" not in log_data:
            log_data = {"batches": []}
        log_data["batches"].append({
            "batch_id": batch_id,
            "timestamp": sc.now_utc_iso(),
            "operations": executed_ops,
        })
        sc.write_json(sc.content_rename_log_path(), log_data)

    return {
        "batch_id": batch_id,
        "dry_run": False,
        "planned": len(suggestions),
        "renamed": len(executed_ops),
        "failed": failed,
        "items": executed_ops,
    }


def undo_rename_batch(
    batch_id: Optional[str],
    drive: sc.Drive,
    index: Optional[dict] = None,
) -> int:
    """Hoàn tác lô đổi tên theo siêu dữ liệu từ `content_rename_log.json`."""
    log_data = sc.read_json(sc.content_rename_log_path(), default={"batches": []})
    batches = log_data.get("batches", []) if isinstance(log_data, dict) else []
    if not batches:
        return 0

    target = None
    if batch_id:
        for b in reversed(batches):
            if b.get("batch_id") == batch_id:
                target = b
                break
    else:
        for b in reversed(batches):
            if not b.get("undone"):
                target = b
                break
    if not target:
        return 0

    ops = target.get("operations", [])
    pairs = [(op["id"], op["old_name"]) for op in ops if op.get("id") and op.get("old_name")]
    res = drive.batch_rename(pairs)
    ok_ids = {fid for fid, ok, _ in res if ok}

    if index and ok_ids:
        _, id_map = sc.build_id_map(index)
        for op in ops:
            if op["id"] in ok_ids and op["id"] in id_map:
                _, item = id_map[op["id"]]
                item["name"] = op["old_name"]
        sc.save_index(index)

    target["undone"] = True
    target["undone_at"] = sc.now_utc_iso()
    sc.write_json(sc.content_rename_log_path(), log_data)
    return len(ok_ids)


# ---------------------------------------------------------------------------
# 6. PHÂN TÍCH TỔNG HỢP, TÌM KIẾM TOÀN VĂN & XUẤT BÁO CÁO
# ---------------------------------------------------------------------------

def analyze_records(
    records: List[Dict[str, Any]],
    persist_cache: bool = True,
) -> Dict[str, Any]:
    """
    Làm giàu và phân tích sâu danh sách bản ghi đã trích xuất:
    - Ngôn ngữ & độ tin cậy
    - Thời gian đọc ước tính (phút)
    - Từ khóa đặc trưng TF-IDF
    - Phân loại chủ đề Chuẩn V6 & phát hiện lệch chủ đề
    - Chữ ký ngữ nghĩa SimHash 64-bit
    - Gợi ý tên Chuẩn V6 từ siêu dữ liệu
    - Trùng lặp nội dung (tuyệt đối & gần trùng)
    """
    kw_by_id = extract_keywords_tfidf(records, top_k=8)
    by_lang: Dict[str, int] = collections.Counter()
    by_topic: Dict[str, int] = collections.Counter()
    by_flag: Dict[str, int] = collections.Counter()
    suggestions: List[Dict[str, Any]] = []

    for rec in records:
        fid = rec.get("id") or rec.get("name", "")
        txt = rec.get("text") or rec.get("text_preview") or ""
        meta = rec.get("metadata") or {}
        outline = rec.get("outline") or []
        stats = rec.get("stats") or {}

        lang, conf = detect_language(txt, metadata=meta)
        wc = int(stats.get("word_count") or 0)
        read_min = round(wc / 220.0, 1) if wc > 0 else 0.0
        kws = kw_by_id.get(fid, [])
        topic_label, rec_branch, topic_score = classify_topic(
            rec.get("name", ""),
            txt,
            metadata=meta,
            outline=outline,
        )
        sh_val = compute_simhash64(txt) if wc >= 10 else 0
        sh_hex = f"{sh_val:016x}" if sh_val else ""

        flags = list(dict.fromkeys(rec.get("flags") or []))
        if rec.get("status") == "ok" and is_topic_mismatch(rec.get("parent_path", ""), rec_branch, topic_score):
            if "lech_chu_de" not in flags:
                flags.append("lech_chu_de")
        if rec.get("status") == "ok" and 0 < wc < 15 and rec.get("ext") in {"pdf", "docx", "epub", "md", "txt"}:
            if "noi_dung_qua_ngan" not in flags:
                flags.append("noi_dung_qua_ngan")

        sug = suggest_v6_name_from_content(rec)
        if sug:
            suggestions.append(sug)

        analysis = {
            "language": lang,
            "language_confidence": conf,
            "reading_time_min": read_min,
            "keywords": kws,
            "topic": topic_label,
            "recommended_branch": rec_branch,
            "topic_score": topic_score,
            "suggested_name": sug["new_name"] if sug else "",
        }
        rec["analysis"] = analysis
        rec["simhash"] = sh_hex
        rec["flags"] = flags

        by_lang[lang] += 1
        by_topic[topic_label] += 1
        for fl in flags:
            by_flag[fl] += 1

        if persist_cache and rec.get("id"):
            fr.save_cached_record(rec, txt)

    dups = find_content_duplicates(records)
    return {
        "total": len(records),
        "by_language": dict(by_lang),
        "by_topic": dict(by_topic),
        "by_flag": dict(by_flag),
        "rename_suggestions": suggestions,
        "duplicates": dups,
        "records": records,
    }


def search_content_cache(
    query: Optional[str] = None,
    branch: Optional[str] = None,
    regex_pat: Optional[str] = None,
    lang: Optional[str] = None,
    flag: Optional[str] = None,
    limit: int = 50,
    index: Optional[dict] = None,
) -> List[Dict[str, Any]]:
    """Tìm kiếm toàn văn trên toàn bộ bộ đệm `content_cache` kèm đoạn trích ngữ cảnh."""
    recs = fr.iter_cached_records(branch=branch, include_text=True, index=index)
    q_norm = sc.strip_accents(sc.nfc(query or "")).lower().strip()
    q_tokens = [t for t in q_norm.split() if t]
    tok_regexes = [re.compile(r"\b" + re.escape(t) + r"\b") for t in q_tokens]
    rx = re.compile(regex_pat, re.I) if regex_pat else None

    hits: List[Dict[str, Any]] = []
    for rec in recs:
        if lang:
            r_lang = (rec.get("analysis") or {}).get("language") or detect_language(rec.get("text", ""), rec.get("metadata"))[0]
            if r_lang.lower() != lang.lower():
                continue
        if flag and flag not in (rec.get("flags") or []):
            continue

        meta = rec.get("metadata") or {}
        full_hay = "\n".join([
            rec.get("name", ""),
            str(meta.get("title", "")),
            str(meta.get("author", "")),
            " ".join(rec.get("outline") or []),
            rec.get("text") or rec.get("text_preview") or "",
        ])

        snippet = ""
        if rx:
            m = rx.search(full_hay)
            if not m:
                continue
            start = max(0, m.start() - 80)
            end = min(len(full_hay), m.end() + 120)
            snippet = re.sub(r"\s+", " ", full_hay[start:end]).strip()
        elif q_tokens:
            hay_norm = sc.strip_accents(sc.nfc(full_hay)).lower()
            if not all(trx.search(hay_norm) for trx in tok_regexes):
                continue
            pos = hay_norm.find(q_norm)
            if pos < 0:
                m0 = tok_regexes[0].search(hay_norm)
                pos = m0.start() if m0 else 0
            start = max(0, pos - 80)
            end = min(len(full_hay), pos + 140)
            snippet = re.sub(r"\s+", " ", full_hay[start:end]).strip()
        else:
            snippet = re.sub(r"\s+", " ", (rec.get("text_preview") or "")[:180]).strip()

        hits.append({
            "id": rec.get("id", ""),
            "name": rec.get("name", ""),
            "path": rec.get("path", ""),
            "ext": rec.get("ext", ""),
            "status": rec.get("status", ""),
            "flags": rec.get("flags", []),
            "snippet": snippet,
        })
        if limit > 0 and len(hits) >= limit:
            break
    return hits


def write_analysis_reports(
    summary: Dict[str, Any],
    branch: Optional[str] = None,
) -> Tuple[Path, Path]:
    """Xuất báo cáo phân tích nội dung ra Markdown và CSV chuẩn quy ước đặt tên V6."""
    today = sc.today_vn()
    md_path = sc.reports_dir() / f"Báo Cáo Phân Tích Nội Dung - Storage, {today}.md"
    csv_path = sc.reports_dir() / f"Báo Cáo Phân Tích Nội Dung - Storage, {today}.csv"

    recs: List[Dict[str, Any]] = summary.get("records", [])
    dups = summary.get("duplicates", {})
    sugs = summary.get("rename_suggestions", [])

    lines: List[str] = [
        f"# BÁO CÁO PHÂN TÍCH NỘI DUNG & SIÊU DỮ LIỆU — [A] STORAGE ({today})",
        "",
        f"- **Phạm vi nhánh**: `{sc.normalize_branch(branch) or sc.ROOT_NAME}`",
        f"- **Tổng số tệp phân tích**: **{sc.fmt_int(summary['total'])}**",
        f"- **Số gợi ý chuẩn hóa tên từ siêu dữ liệu**: **{sc.fmt_int(len(sugs))}**",
        f"- **Số nhóm trùng nội dung tuyệt đối (SHA-256)**: **{sc.fmt_int(len(dups.get('exact_groups', [])))}**",
        f"- **Số cặp gần trùng nội dung (SimHash)**: **{sc.fmt_int(len(dups.get('near_pairs', [])))}**",
        "",
        "## 1. Phân bố Ngôn ngữ",
        "",
        sc.md_table(
            ["Ngôn ngữ", "Số tệp"],
            sorted(summary.get("by_language", {}).items(), key=lambda x: -x[1]),
            align=["left", "right"],
        ),
        "",
        "## 2. Phân bố Chủ đề Nội dung",
        "",
        sc.md_table(
            ["Chủ đề", "Số tệp"],
            sorted(summary.get("by_topic", {}).items(), key=lambda x: -x[1]),
            align=["left", "right"],
        ),
        "",
    ]

    if summary.get("by_flag"):
        lines += [
            "## 3. Thống kê Cờ Chất lượng & Kỹ thuật",
            "",
            sc.md_table(
                ["Cờ cảnh báo", "Số tệp"],
                sorted(summary["by_flag"].items(), key=lambda x: -x[1]),
                align=["left", "right"],
            ),
            "",
        ]

    if sugs:
        lines += [
            "## 4. Gợi ý Chuẩn hóa Tên Chuẩn V6 từ Siêu dữ liệu Nội dung (tối đa 40 mục đầu)",
            "",
            sc.md_table(
                ["ID", "Tên hiện tại", "Tên đề xuất Chuẩn V6", "Lý do"],
                [[s["id"], s["old_name"], s["new_name"], s["reason"]] for s in sugs[:40]],
            ),
            "",
        ]

    if dups.get("near_pairs"):
        lines += [
            "## 5. Cặp Tệp Gần Trùng Nội Dung theo SimHash (tối đa 30 cặp đầu)",
            "",
            sc.md_table(
                ["Độ tương đồng", "Hamming", "Tệp A", "Tệp B"],
                [
                    [f"{p['similarity_pct']}%", p["hamming"], p["a"].get("path", p["a"].get("name", "")), p["b"].get("path", p["b"].get("name", ""))]
                    for p in dups["near_pairs"][:30]
                ],
                align=["right", "right", "left", "left"],
            ),
            "",
        ]

    sample_rows = []
    for r in recs[:60]:
        an = r.get("analysis") or {}
        st = r.get("stats") or {}
        meta = r.get("metadata") or {}
        sample_rows.append([
            r.get("name", ""),
            r.get("ext", ""),
            an.get("language", ""),
            sc.fmt_int(int(st.get("word_count") or 0)),
            an.get("topic", ""),
            ", ".join((an.get("keywords") or [])[:5]),
            meta.get("author", ""),
            ", ".join(r.get("flags") or []),
        ])
    if sample_rows:
        lines += [
            "## 6. Bảng Chi tiết Mẫu Phân tích (tối đa 60 tệp đầu)",
            "",
            sc.md_table(
                ["Tên tệp", "Đuôi", "Ngôn ngữ", "Số từ", "Chủ đề", "Từ khóa TF-IDF", "Tác giả (Meta)", "Cờ"],
                sample_rows,
                align=["left", "left", "center", "right", "left", "left", "left", "left"],
            ),
            "",
        ]

    md_path.write_text("\n".join(lines), encoding="utf-8")

    csv_rows = []
    for r in recs:
        an = r.get("analysis") or {}
        st = r.get("stats") or {}
        meta = r.get("metadata") or {}
        csv_rows.append([
            r.get("id", ""),
            r.get("name", ""),
            r.get("path", ""),
            r.get("ext", ""),
            r.get("magic_format", ""),
            r.get("status", ""),
            r.get("size", 0),
            r.get("sha256", ""),
            r.get("simhash", ""),
            an.get("language", ""),
            an.get("language_confidence", ""),
            st.get("word_count", 0),
            st.get("pages", ""),
            an.get("reading_time_min", 0),
            meta.get("title", ""),
            meta.get("author", ""),
            an.get("topic", ""),
            an.get("recommended_branch", ""),
            ", ".join(an.get("keywords") or []),
            an.get("suggested_name", ""),
            ", ".join(r.get("flags") or []),
        ])
    sc.write_csv(
        csv_path,
        [
            "ID", "Tên tệp", "Đường dẫn", "Đuôi", "Magic", "Trạng thái", "Dung lượng (B)",
            "SHA-256", "SimHash", "Ngôn ngữ", "Độ tin cậy NN", "Số từ", "Số trang",
            "Phút đọc", "Tiêu đề (Meta)", "Tác giả (Meta)", "Chủ đề", "Nhánh đề xuất",
            "Từ khóa TF-IDF", "Tên đề xuất V6", "Cờ cảnh báo",
        ],
        csv_rows,
    )
    return md_path, csv_path


# ---------------------------------------------------------------------------
# 7. GIAO DIỆN DÒNG LỆNH (CLI)
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Bộ phân tích nội dung, ngôn ngữ, từ khóa, trùng nội dung và gợi ý tên Chuẩn V6 (v3.1)."
    )
    ap.add_argument(
        "lenh",
        nargs="?",
        default="phan-tich",
        choices=["phan-tich", "goi-y-ten", "hoan-tac-ten", "trung-noi-dung", "tim-noi-dung"],
        help="Lệnh: phan-tich, goi-y-ten, hoan-tac-ten, trung-noi-dung, tim-noi-dung.",
    )
    ap.add_argument("--nhanh", help="Giới hạn trong một nhánh thư mục.")
    ap.add_argument("--dinh-dang", help="Danh sách đuôi tệp cách nhau dấu phẩy (khi bật --tu-dong-doc).")
    ap.add_argument("--tu-dong-doc", action="store_true", help="Tự động gọi [13] trích xuất các tệp chưa có trong cache trước khi phân tích.")
    ap.add_argument("--max-mb", type=float, default=50.0, help="Dung lượng tối đa mỗi tệp khi --tu-dong-doc (mặc định 50 MB).")
    ap.add_argument("--gioi-han", type=int, default=50, help="Số tệp tối đa khi --tu-dong-doc hoặc số kết quả tìm kiếm (mặc định 50).")
    ap.add_argument("--luong", type=int, default=4, help="Số luồng tải song song khi --tu-dong-doc (mặc định 4).")
    ap.add_argument("--tu-khoa", help="Từ khóa tìm kiếm toàn văn (cho lệnh `tim-noi-dung`).")
    ap.add_argument("--regex", help="Biểu thức chính quy tìm trong nội dung (`tim-noi-dung`).")
    ap.add_argument("--ngon-ngu", help="Lọc theo mã ngôn ngữ (vi, en, fr, es, zh...).")
    ap.add_argument("--co", help="Lọc theo cờ cảnh báo (can_ocr, co_mat_khau, tep_hong, lech_chu_de...).")
    ap.add_argument("--nguong-hamming", type=int, default=3, help="Ngưỡng khoảng cách Hamming cho trùng nội dung SimHash (mặc định 3).")
    ap.add_argument("--ma-lo", help="Mã lô cần hoàn tác (cho lệnh `hoan-tac-ten`).")
    ap.add_argument("--thuc-thi", action="store_true", help="Thực sự đổi tên trên Google Drive (mặc định: chạy thử).")
    ap.add_argument("--dong-y", action="store_true", help="Không hỏi xác nhận khi --thuc-thi.")
    ap.add_argument("--tai-len", action="store_true", help="Tải báo cáo phân tích lên [00] TỔNG QUAN/[02] NHẬT KÍ.")
    args = ap.parse_args()

    index = sc.load_index(required=False)

    if args.lenh == "hoan-tac-ten":
        drive = sc.create_drive()
        restored = undo_rename_batch(args.ma_lo, drive, index=index)
        sc.log(f"↩️  Đã hoàn tác {restored} mục đổi tên theo siêu dữ liệu.")
        return

    if args.lenh == "tim-noi-dung":
        hits = search_content_cache(
            query=args.tu_khoa,
            branch=args.nhanh,
            regex_pat=args.regex,
            lang=args.ngon_ngu,
            flag=args.co,
            limit=args.gioi_han,
            index=index,
        )
        sc.log(f"🔎 Tìm thấy {len(hits)} kết quả trong bộ đệm nội dung:")
        for h in hits:
            fl_str = f" [{', '.join(h['flags'])}]" if h.get("flags") else ""
            sc.log(f" • {h['path']} ({h['id']}){fl_str}")
            if h.get("snippet"):
                sc.log(f"   ↳ “{h['snippet']}”")
        return

    if args.tu_dong_doc and index:
        drive = sc.create_drive()
        exts = {e.strip().lower().lstrip(".") for e in args.dinh_dang.split(",") if e.strip()} if args.dinh_dang else None
        fr.batch_extract(
            index,
            drive,
            branch=args.nhanh,
            exts=exts,
            max_mb=args.max_mb,
            limit=args.gioi_han,
            workers=args.luong,
        )

    recs = fr.iter_cached_records(branch=args.nhanh, include_text=True, index=index)
    if args.dinh_dang:
        allowed_exts = {e.strip().lower().lstrip(".") for e in args.dinh_dang.split(",") if e.strip()}
        recs = [r for r in recs if (r.get("ext") or "").lower() in allowed_exts]

    summary = analyze_records(recs, persist_cache=True)

    if args.lenh == "trung-noi-dung":
        dups = find_content_duplicates(recs, max_hamming=args.nguong_hamming)
        sc.log(
            f"🧬 Kết quả rà soát trùng nội dung trên {len(recs)} tệp: "
            f"{len(dups['exact_groups'])} nhóm trùng SHA-256, {len(dups['near_pairs'])} cặp gần trùng SimHash (Hamming ≤ {args.nguong_hamming})."
        )
        for g in dups["exact_groups"][:15]:
            sc.log(f" • [SHA-256 {g['sha256'][:12]}…] ({g['count']} tệp):")
            for it in g["items"]:
                sc.log(f"    - {it.get('path', it.get('name', ''))} ({it.get('id', '')})")
        for p in dups["near_pairs"][:15]:
            sc.log(
                f" • [SimHash {p['similarity_pct']}% | Hamming={p['hamming']}] "
                f"{p['a'].get('name')}  <~>  {p['b'].get('name')}"
            )
        return

    if args.lenh == "goi-y-ten":
        sugs = summary["rename_suggestions"]
        sc.log(f"🏷️  Phát hiện {len(sugs)} tệp có thể chuẩn hóa/làm giàu tên từ siêu dữ liệu nội dung:")
        for s in sugs[:40]:
            sc.log(f" • [{s['reason']}] {s['old_name']}  →  {s['new_name']} ({s['id']})")
        if args.thuc_thi and sugs:
            if sc.confirm(f"Xác nhận đổi tên tại chỗ {len(sugs)} tệp trên Google Drive?", assume_yes=args.dong_y):
                drive = sc.create_drive()
                res = apply_rename_suggestions(sugs, drive, index=index, execute=True)
                sc.log(f"✅ Đã đổi tên {res['renamed']}/{res['planned']} tệp (lô {res['batch_id']}).")
        elif sugs:
            sc.log("💡 Chế độ CHẠY THỬ. Truyền thêm `--thuc-thi --dong-y` để áp dụng đổi tên tại chỗ.")
        return

    md_p, csv_p = write_analysis_reports(summary, branch=args.nhanh)
    sc.log(f"📊 Đã phân tích {summary['total']} tệp:")
    sc.log(f"   • Ngôn ngữ        : {summary['by_language']}")
    sc.log(f"   • Chủ đề          : {summary['by_topic']}")
    if summary["by_flag"]:
        sc.log(f"   • Cờ chất lượng   : {summary['by_flag']}")
    sc.log(f"   • Gợi ý tên V6    : {len(summary['rename_suggestions'])} tệp")
    sc.log(
        f"   • Trùng nội dung  : {len(summary['duplicates']['exact_groups'])} nhóm SHA-256, "
        f"{len(summary['duplicates']['near_pairs'])} cặp SimHash"
    )
    sc.log(f"📝 Báo cáo Markdown : {md_p}")
    sc.log(f"📝 Báo cáo CSV      : {csv_p}")

    if args.tai_len:
        drive = sc.create_drive()
        md_id = sc.publish_file(drive, md_p, sc.nhat_ki_id())
        csv_id = sc.publish_file(drive, csv_p, sc.nhat_ki_id())
        sc.log(f"☁️  Đã tải báo cáo lên [02] NHẬT KÍ: md={md_id}, csv={csv_id}")


if __name__ == "__main__":
    main()
