"""
Layer 1 of the pipeline: turn a file on disk into plain text.

Strategy:
  - PDFs: try PyMuPDF's native text extraction first (fast, exact, free).
    If a page comes back with ~no text, it's likely a scanned image —
    rasterize that page and run OCR on it instead.
  - Images (png/jpg/etc.): straight to OCR.
"""
import os
import tempfile
import pytesseract
from PIL import Image

import pymupdf as fitz  # PyMuPDF
from app.config import TESSERACT_CMD

if TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

MIN_CHARS_PER_PAGE = 20  # below this, assume the page is a scanned image


def extract_text(file_path: str) -> tuple[str, bool]:
    """Returns (text, used_ocr)."""
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        return _extract_pdf(file_path)
    elif ext in (".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp"):
        text = pytesseract.image_to_string(Image.open(file_path))
        return text, True
    else:
        # Fall back to treating it as plain text
        try:
            with open(file_path, "r", errors="ignore") as f:
                return f.read(), False
        except Exception:
            return "", False


def _extract_pdf(file_path: str) -> tuple[str, bool]:
    doc = fitz.open(file_path)
    pages_text = []
    used_ocr = False

    for page in doc:
        text = page.get_text().strip()
        if len(text) >= MIN_CHARS_PER_PAGE:
            pages_text.append(text)
            continue

        # Likely scanned — rasterize this page and OCR it.
        used_ocr = True
        pix = page.get_pixmap(dpi=300)
        img_path = os.path.join(
            tempfile.gettempdir(), f"_ocr_page_{page.number}_{os.getpid()}.png"
        )
        pix.save(img_path)
        try:
            ocr_text = pytesseract.image_to_string(Image.open(img_path))
        finally:
            if os.path.exists(img_path):
                os.remove(img_path)
        pages_text.append(ocr_text)

    doc.close()
    return "\n\n".join(pages_text), used_ocr
