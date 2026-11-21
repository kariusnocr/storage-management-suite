"""Động cơ OCR hợp nhất dùng chung (`tesseract` `vie+eng` + `pdftoppm`) cho [13], [16], [18]."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from storage_suite.core.config import tessdata_dir
from storage_suite.core.utils import nfc

_TESSERACT_LANG_CACHE: Optional[Tuple[str, Optional[str]]] = None


def reset_ocr_cache() -> None:
    global _TESSERACT_LANG_CACHE
    _TESSERACT_LANG_CACHE = None


def resolve_tesseract_lang(force_refresh: bool = False) -> Tuple[str, Optional[str]]:
    """Tự động phát hiện gói ngôn ngữ `vie+eng` (ưu tiên `~/storage_data/tessdata` rồi đến hệ thống)."""
    global _TESSERACT_LANG_CACHE
    if _TESSERACT_LANG_CACHE is not None and not force_refresh:
        return _TESSERACT_LANG_CACHE

    if not shutil.which("tesseract"):
        _TESSERACT_LANG_CACHE = ("", None)
        return _TESSERACT_LANG_CACHE

    custom_td = tessdata_dir()
    env_td: Optional[str] = (
        str(custom_td) if (custom_td / "vie.traineddata").exists() else os.environ.get("TESSDATA_PREFIX")
    )
    env = os.environ.copy()
    if env_td:
        env["TESSDATA_PREFIX"] = env_td
    try:
        proc = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True, timeout=10, env=env)
        langs = {ln.strip() for ln in (proc.stdout + "\n" + proc.stderr).splitlines()[1:] if ln.strip()}
    except Exception:
        langs = {"eng"}

    if "vie" in langs and "eng" in langs:
        res = ("vie+eng", env_td)
    elif "vie" in langs:
        res = ("vie", env_td)
    elif "eng" in langs:
        res = ("eng", env_td)
    else:
        res = (next(iter(langs), "eng"), env_td)

    _TESSERACT_LANG_CACHE = res
    return res


def _pil_lanczos():
    from PIL import Image  # type: ignore

    return getattr(getattr(Image, "Resampling", Image), "LANCZOS", getattr(Image, "BICUBIC", 3))


def ocr_pil_image(img, psm: int = 3, max_chars: int = 50_000, timeout: int = 35) -> Tuple[str, str]:
    """Tiền xử lý tương phản + phóng đại nhẹ ảnh PIL rồi nhận dạng bằng `tesseract` (`vie+eng`)."""
    from PIL import ImageOps  # type: ignore

    lang, tess_prefix = resolve_tesseract_lang()
    if not lang:
        return "", ""

    w, h = img.size
    gray = img.convert("L")
    if 0 < max(w, h) < 1000:
        scale = min(3.0, 1200.0 / float(max(w, h)))
        gray = gray.resize((max(16, int(w * scale)), max(16, int(h * scale))), _pil_lanczos())
    gray = ImageOps.autocontrast(gray, cutoff=1)

    fd, tmp_png = tempfile.mkstemp(prefix="astorage_ocr_", suffix=".png")
    os.close(fd)
    env = os.environ.copy()
    if tess_prefix:
        env["TESSDATA_PREFIX"] = tess_prefix
    try:
        gray.save(tmp_png, format="PNG")
        proc = subprocess.run(
            ["tesseract", tmp_png, "stdout", "-l", lang, "--psm", str(psm)],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        if proc.returncode != 0 or not proc.stdout:
            return "", lang
        lines = [re.sub(r"[ \t\f\v]+", " ", ln).strip() for ln in nfc(proc.stdout).splitlines()]
        clean = "\n".join(ln for ln in lines if ln)
        return clean[:max_chars], lang
    except Exception:
        return "", lang
    finally:
        try:
            os.remove(tmp_png)
        except OSError:
            pass


def ocr_image_file(path: Path, psm: int = 3, max_chars: int = 50_000, timeout: int = 35) -> Tuple[str, str]:
    """Chạy OCR trên tệp ảnh (dùng tiền xử lý PIL nếu có, fallback trực tiếp sang CLI `tesseract`)."""
    lang, tess_prefix = resolve_tesseract_lang()
    if not lang:
        return "", ""
    try:
        from PIL import Image  # type: ignore

        with Image.open(path) as im:
            return ocr_pil_image(im, psm=psm, max_chars=max_chars, timeout=timeout)
    except Exception:
        pass

    env = os.environ.copy()
    if tess_prefix:
        env["TESSDATA_PREFIX"] = tess_prefix
    try:
        proc = subprocess.run(
            ["tesseract", str(path), "stdout", "-l", lang, "--psm", str(psm)],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        if proc.returncode == 0 and proc.stdout:
            return nfc(proc.stdout).strip()[:max_chars], lang
    except Exception:
        pass
    return "", lang


def ocr_pdf_pages(path: Path, max_ocr_pages: int = 5, dpi: int = 150) -> Tuple[str, str]:
    """Chuyển các trang đầu của PDF scan sang PNG bằng `pdftoppm` và OCR bằng `tesseract` (`vie+eng`)."""
    lang, tess_prefix = resolve_tesseract_lang()
    if not lang or not shutil.which("pdftoppm"):
        return "", lang

    tmp_dir = Path(tempfile.mkdtemp(prefix="astorage_pdf_ocr_"))
    env = os.environ.copy()
    if tess_prefix:
        env["TESSDATA_PREFIX"] = tess_prefix
    try:
        prefix = tmp_dir / "page"
        subprocess.run(
            ["pdftoppm", "-png", "-r", str(dpi), "-f", "1", "-l", str(max_ocr_pages), str(path), str(prefix)],
            capture_output=True,
            timeout=90,
            check=False,
        )
        chunks: List[str] = []
        for img in sorted(tmp_dir.glob("page*.png")):
            proc = subprocess.run(
                ["tesseract", str(img), "stdout", "-l", lang],
                capture_output=True,
                text=True,
                timeout=45,
                env=env,
            )
            if proc.returncode == 0 and proc.stdout:
                chunks.append(nfc(proc.stdout))
        return "\n".join(chunks), lang
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
