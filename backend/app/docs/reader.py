"""Sənəddən mətn: mətnli PDF -> pypdf, skan PDF və şəkil -> OCR (dərs, bölmə 6-7).

Qayda (dərsin cədvəli): əvvəl pypdf sına. Mətn boşdursa PDF skandır, səhifələri şəkilə çevirib OCR et.
OCR xam mətn verir (bəzən səhv: '№' -> 'Ne', '%' -> '96'), strukturlaşdırmanı və yoxlamanı növbəti qat edir."""

import io
from dataclasses import dataclass, field

MIN_TEXT_CHARS = 20


@dataclass
class DocText:
    text: str
    kind: str                       # pdf-text | pdf-scan | image | text
    method: str                     # pypdf | ocr | given
    meta: dict = field(default_factory=dict)


def ocr_image(img) -> tuple:
    """(mətn, orta etibar 0-100). Boz ton + avto-kontrast + kiçikdirsə böyütmə, --psm 6 (vahid mətn bloku)."""
    import pytesseract
    from PIL import Image, ImageOps
    img = ImageOps.autocontrast(img.convert("L"))
    if img.width < 1600:
        img = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
    cfg = "--psm 6"
    text = pytesseract.image_to_string(img, lang="aze+eng", config=cfg)
    data = pytesseract.image_to_data(img, lang="aze+eng", config=cfg, output_type=pytesseract.Output.DICT)
    confs = [float(c) for c, w in zip(data["conf"], data["text"]) if w.strip() and float(c) >= 0]
    return text, (sum(confs) / len(confs) if confs else 0.0)


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    return "\n".join((p.extract_text() or "") for p in reader.pages)


def _pdf_to_images(data: bytes, dpi: int = 200) -> list:
    import fitz  # pymupdf
    from PIL import Image
    doc = fitz.open(stream=data, filetype="pdf")
    out = []
    for page in doc:
        pix = page.get_pixmap(dpi=dpi)
        out.append(Image.open(io.BytesIO(pix.tobytes("png"))))
    return out


def read_document(data: bytes, filename: str) -> DocText:
    from PIL import Image
    name = filename.lower()
    if name.endswith(".pdf"):
        text = _pdf_text(data)
        if len(text.strip()) >= MIN_TEXT_CHARS:
            return DocText(text=text, kind="pdf-text", method="pypdf")
        texts, confs = [], []
        for img in _pdf_to_images(data):
            t, c = ocr_image(img)
            texts.append(t)
            confs.append(c)
        return DocText(text="\n".join(texts), kind="pdf-scan", method="ocr", meta={"ocr_conf": round(sum(confs) / max(1, len(confs)), 1)})
    if name.endswith((".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp")):
        t, c = ocr_image(Image.open(io.BytesIO(data)))
        return DocText(text=t, kind="image", method="ocr", meta={"ocr_conf": round(c, 1)})
    if name.endswith(".txt"):
        return DocText(text=data.decode("utf-8", "replace"), kind="text", method="given")
    raise ValueError(f"dəstəklənməyən format: {filename}")
