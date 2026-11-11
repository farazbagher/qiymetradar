"""Qaimə-faktura generatoru: HƏQİQƏT məlumatı (truth) bilinən sənədlər yaradır.

Niyə: ekstraksiya dəqiqliyini ölçmək üçün düzgün cavabı əvvəlcədən bilməliyik. Eyni truth 3 kanalla verilir:
mətnli PDF (pypdf), təmiz şəkil və pis keyfiyyətli şəkil (OCR). 3 şablon var; C şablonu yalnız held-out testdədir
(regex və prompt-lar onu görmədən yazılıb).

Sənədlər süni (AI yazıb): real qaimələr daha müxtəlifdir. Bu ölçmə real performansın yuxarı həddinə yaxındır.
"""

import io
import os
import random
from dataclasses import asdict, dataclass, field

# Docker şəklində fonts-dejavu-core bu yolu qurur; başqa sistemdə INVOICE_FONT ilə dəyişmək olar
FONT = os.environ.get("INVOICE_FONT") or "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
MONTHS = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avqust", "sentyabr", "oktyabr", "noyabr", "dekabr"]
VENDORS = ["Nova Tech MMC", "Xəzər Elektronika QSC", "Bakı Ofis Təchizatı MMC", "Qafqaz Kompüter MMC", "Şirvan Texno MMC",
           "Abşeron Dijital MMC", "Gəncə Avadanlıq MMC", "Sumqayıt İT Həlləri MMC", "Lənkəran Smart MMC", "Naxçıvan Texnika MMC"]
BUYERS = ["Mavi Qapı Kafe MMC", "Dəniz Logistika MMC", "Günəş Klinikası MMC", "Atlas Tikinti MMC", "Yaşıl Bağ Market MMC"]
CATALOG = [("Noutbuk Pro 15", 1450.0), ("Monitor 27 düym", 520.0), ("Printer LaserJet", 380.0), ("Mexaniki klaviatura", 95.0),
           ("Simsiz qulaqlıq", 140.0), ("Veb kamera HD", 60.0), ("Planşet 10 düym", 410.0), ("Router Wi-Fi 6", 125.0),
           ("Xarici disk 2TB", 170.0), ("Flash yaddaş 128GB", 28.0)]
VAT_RATE = 0.18


@dataclass
class InvoiceTruth:
    invoice_no: str
    date: str                       # ISO YYYY-MM-DD
    vendor: str
    buyer: str
    items: list = field(default_factory=list)   # [{"name","qty","unit"}]
    subtotal: float = 0.0
    vat: float = 0.0
    total: float = 0.0
    currency: str = "AZN"
    phone: str = ""
    email: str = ""
    iban: str = ""

    def fields(self) -> dict:
        """Ölçülən sahələr (qalanı sənədi real göstərmək üçündür)."""
        return {"invoice_no": self.invoice_no, "date": self.date, "vendor": self.vendor,
                "total": self.total, "vat": self.vat, "currency": self.currency}

    def as_dict(self) -> dict:
        return asdict(self)


def make_invoice(seed: int, template: str) -> InvoiceTruth:
    rnd = random.Random(f"{template}-{seed}")
    year = 2026
    month, day = rnd.randint(1, 12), rnd.randint(1, 28)
    n = rnd.randint(100, 999)
    no = {"A": f"{year}-{n:04d}", "B": f"INV-{year}-{n}", "C": f"HF/{n}/{year % 100}"}[template]
    items = []
    for name, base in rnd.sample(CATALOG, rnd.randint(2, 4)):
        items.append({"name": name, "qty": rnd.randint(1, 5), "unit": round(base * rnd.uniform(0.9, 1.1), 2)})
    subtotal = round(sum(i["qty"] * i["unit"] for i in items), 2)
    vat = round(subtotal * VAT_RATE, 2)
    vendor = rnd.choice(VENDORS)
    slug = "".join(c for c in vendor.split()[0].lower() if c.isascii() and c.isalpha()) or "firma"
    return InvoiceTruth(
        invoice_no=no, date=f"{year}-{month:02d}-{day:02d}", vendor=vendor, buyer=rnd.choice(BUYERS), items=items,
        subtotal=subtotal, vat=vat, total=round(subtotal + vat, 2), currency="AZN",
        phone=f"+994 {rnd.choice([50, 51, 55, 70, 77])} {rnd.randint(100, 999)} {rnd.randint(10, 99)} {rnd.randint(10, 99)}",
        email=f"info@{slug}.az", iban="AZ" + str(rnd.randint(10, 99)) + "NABZ" + "".join(str(rnd.randint(0, 9)) for _ in range(20)))


def _fmt(v: float, style: str) -> str:
    s = f"{v:,.2f}"                        # 3,422.00
    if style == "space-comma":            # 3 422,00
        return s.replace(",", " ").replace(".", ",")
    if style == "dot-comma":              # 3.422,00
        return s.replace(",", "X").replace(".", ",").replace("X", ".")
    return s.replace(",", "")             # 3422.00


def render_lines(inv: InvoiceTruth, template: str) -> list:
    y, m, d = inv.date.split("-")
    L = []
    if template == "A":
        L += [f"QAİMƏ-FAKTURA № {inv.invoice_no}", f"Satıcı: {inv.vendor}", f"Alıcı: {inv.buyer}", f"Tarix: {d}.{m}.{y}",
              f"Əlaqə: {inv.phone}, {inv.email}", f"Hesab: {inv.iban}", ""]
        L += [f"{i['name']}: {i['qty']} x {_fmt(i['unit'], 'plain')} = {_fmt(i['qty'] * i['unit'], 'plain')}" for i in inv.items]
        L += ["", f"Yekun (ƏDV-siz): {_fmt(inv.subtotal, 'plain')} AZN", f"ƏDV (18%): {_fmt(inv.vat, 'plain')} AZN",
              f"Cəmi ödəniləcək: {_fmt(inv.total, 'plain')} AZN"]
    elif template == "B":
        L += [f"INVOICE #{inv.invoice_no}", f"Date: {inv.date}", f"Supplier: {inv.vendor}", f"Bill to: {inv.buyer}",
              f"Contact: {inv.phone} / {inv.email}", f"IBAN: {inv.iban}", ""]
        L += [f"{i['name']}: {i['qty']} pcs x {_fmt(i['unit'], 'space-comma')} = {_fmt(i['qty'] * i['unit'], 'space-comma')}" for i in inv.items]
        L += ["", f"Subtotal: AZN {_fmt(inv.subtotal, 'space-comma')}", f"VAT 18%: AZN {_fmt(inv.vat, 'space-comma')}",
              f"Total due: AZN {_fmt(inv.total, 'space-comma')}"]
    else:  # C: başqa söz ehtiyatı və rəqəm formatı (held-out)
        L += ["HESAB-FAKTURA", f"Nömrə: {inv.invoice_no}", f"Tarix: {int(d)} {MONTHS[int(m) - 1]} {y}-cı il", f"Təchizatçı: {inv.vendor}",
              f"Müştəri: {inv.buyer}", f"Telefon: {inv.phone}", f"E-poçt: {inv.email}", f"Bank hesabı: {inv.iban}", ""]
        L += [f"{i['name']} - {i['qty']} ədəd, vahid qiymət {_fmt(i['unit'], 'dot-comma')} manat" for i in inv.items]
        L += ["", f"Cəmi (ƏDV-siz): {_fmt(inv.subtotal, 'dot-comma')} manat", f"ƏDV 18%: {_fmt(inv.vat, 'dot-comma')} manat",
              f"Yekun məbləğ: {_fmt(inv.total, 'dot-comma')} manat"]
    return L


def to_pdf_bytes(lines: list) -> bytes:
    """Mətn qatı olan PDF (pypdf oxuya bilər)."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas
    if "DejaVu" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("DejaVu", FONT))     # reportlab-ın Helvetica-sı 'ə' hərfini bilmir
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(595, 842))
    c.setFont("DejaVu", 11)
    y = 800
    for line in lines:
        c.drawString(50, y, line)
        y -= 20
    c.save()
    return buf.getvalue()


def to_image(lines: list, size: int = 30):
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype(FONT, size)
    img = Image.new("L", (1500, 80 + len(lines) * (size + 14)), 255)
    d = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        d.text((50, 40 + i * (size + 14)), line, font=font, fill=0)
    return img


def degrade(img, level: str = "noisy", seed: int = 7):
    """Pis keyfiyyətli skan/foto simulyasiyası. noisy: yüngül; hard: əyri, bulanıq, aşağı kontrast, güclü səs-küy."""
    from PIL import ImageFilter
    p = {"noisy": dict(angle=2, blur=1.3, noise=90, contrast=0.45), "hard": dict(angle=3.5, blur=2.1, noise=140, contrast=0.32)}[level]
    rnd = random.Random(seed)
    img = img.rotate(p["angle"], expand=True, fillcolor=255).filter(ImageFilter.GaussianBlur(p["blur"]))
    px = img.load()
    for _ in range(img.width * img.height // 20):
        x, y = rnd.randrange(img.width), rnd.randrange(img.height)
        px[x, y] = max(0, min(255, px[x, y] + rnd.randint(-p["noise"], p["noise"])))
    return img.point(lambda v: int(130 + v * p["contrast"]))


def image_to_bytes(img, fmt: str = "PNG") -> bytes:
    buf = io.BytesIO()
    img.convert("L").save(buf, format=fmt, **({"quality": 60} if fmt == "JPEG" else {}))
    return buf.getvalue()


def image_to_pdf_bytes(img) -> bytes:
    """Skan edilmiş PDF: yalnız şəkil var, mətn qatı YOXDUR (pypdf boş qaytarır, OCR lazımdır)."""
    buf = io.BytesIO()
    img.convert("L").save(buf, format="PDF", resolution=150)
    return buf.getvalue()
