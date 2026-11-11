"""Qaimədən sahələri çıxarmaq: regex (pulsuz) -> lokal model -> (icazə varsa) Claude -> insan baxışı.

Dizayn (ReklamPilot-dakı "LLM qərar vermir, kod yoxlayır" prinsipi):
- Hər nəticə DETERMİNİSTİK yoxlamadan keçir (validate): tarix düzgündürmü, ƏDV cəmin 18/118 hissəsidirmi və ƏN VACİBİ
  hər dəyər sənəd mətnində həqiqətən varmı (halüsinasiyaya qarşı "grounding").
- Yoxlamadan keçməyən nəticə "needs_review" olur. Səssiz səhv (status=ok amma yanlış) ən təhlükəli xətadır, onu ölçürük.
- Məxfilik: sənədi yalnız lokal model oxuyur. Buluda yalnız ALLOW_CLOUD_DOCS=1 olanda, şəxsi məlumat maskalanandan sonra gedir.
"""

import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

from pydantic import BaseModel, Field

from difflib import SequenceMatcher

from app.parsing import parse_price, slugify

VAT_RATE = 0.18
FOREIGN_SCRIPT = re.compile(r"[\u0370-\u03ff\u0400-\u04ff]")
MONTHS = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avqust", "sentyabr", "oktyabr", "noyabr", "dekabr"]
MIN_OCR_CONF = 55.0


class InvoiceData(BaseModel):
    invoice_no: str = Field(description="Sənəd (qaimə/faktura) nömrəsi")
    date: str = Field(description="Sənəd tarixi, YYYY-MM-DD formatında")
    vendor: str = Field(description="Satıcı / təchizatçı şirkətin adı (alıcı yox)")
    total: float = Field(description="ÖDƏNİLƏCƏK yekun məbləğ (ƏDV daxil), ədəd kimi")
    vat: Optional[float] = Field(default=None, description="ƏDV MƏBLƏĞİ (faiz yox), ədəd kimi")
    currency: str = Field(default="AZN", description="Valyuta kodu")


# ------------------------------------------------------------------ məxfilik
PII = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[EMAIL]"),
    (re.compile(r"\bAZ\d{2}[A-Z]{4}\d{20}\b"), "[IBAN]"),
    (re.compile(r"(?:\+994|\b0)[\s\-]?\(?\d{2}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}\b"), "[TELEFON]"),
]


def mask_pii(text: str) -> str:
    """Telefon, e-poçt, IBAN gizlədilir. Qaimə nömrəsi, tarix, məbləğ və satıcı adı toxunulmaz qalır (ekstraksiya üçün lazımdır)."""
    for rx, token in PII:
        text = rx.sub(token, text)
    return text


# ------------------------------------------------------------------ regex baseline (A və B şablonları üçün yazılıb)
_NUM = r"([\d][\d\s.,]*\d)"


def _last_amount(line: str) -> Optional[float]:
    nums = re.findall(_NUM, line)
    for raw in reversed(nums):
        try:
            return parse_price(raw)
        except ValueError:
            continue
    return None


def clean_vendor(v: str) -> str:
    """OCR sətrin sonuna səs-küy ('|', '_', '~') əlavə edə bilər: 'Nova Tech MMC | |' -> 'Nova Tech MMC'."""
    return re.sub(r"[\s|_~^<>\-–—.,;:]+$", "", v).strip()


def regex_extract(text: str) -> dict:
    """Sadə bazis: açar sözlər A (Azərbaycanca) və B (ingiliscə) şablonlarına görə seçilib. C şablonunu görmədən yazılıb."""
    out = {"invoice_no": None, "date": None, "vendor": None, "total": None, "vat": None, "currency": None}
    # nömrə: '№' / '#' ya da OCR-ın '№' əvəzinə yazdığı 'Ne', 'Nə', 'N:' (tuninq dəstində müşahidə olunan formalar)
    m = re.search(r"(?:№|#)\s*([A-Z0-9][\w\-/]*)", text)
    if not m:
        head = next((ln for ln in text.splitlines() if ln.strip()), "")
        m = re.search(r"\b(?:Ne|Nə|Na|No|N)\b\.?\s*:?\s*(\d[\w\-/]*)", head)
    if m:
        out["invoice_no"] = m.group(1)
    m = re.search(r"\b(\d{2})\.(\d{2})\.(\d{4})\b", text)
    if m:
        out["date"] = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    else:
        m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
        if m:
            out["date"] = m.group(0)
    m = re.search(r"(?:Sat[ıi]c[ıi]|Supplier)\s*:\s*(.+)", text)
    if m:
        out["vendor"] = clean_vendor(m.group(1))
    for line in text.splitlines():
        if re.search(r"Cəmi ödəniləcək|Total due", line, re.I):
            out["total"] = _last_amount(line)
        elif re.search(r"ƏDV|VAT", line) and not re.search(r"ƏDV-siz|ƏDV-sız|Subtotal|without VAT", line, re.I) and out["vat"] is None:
            out["vat"] = _last_amount(line.split(":", 1)[-1])      # ': ' sonrası: '(18%)' / '1896' məbləğ sayılmasın
    if re.search(r"\bAZN\b|manat", text):
        out["currency"] = "AZN"
    return out


# ------------------------------------------------------------------ təchizatçı siyahısı (supplier master)
SNAP_RATIO = 0.86


def vendor_master() -> list:
    """VENDOR_MASTER env: boş = söndürülüb | 'demo' = demo təchizatçılar | 'Ad1;Ad2;...'. Real şirkətin təchizatçı siyahısı olur."""
    v = os.environ.get("VENDOR_MASTER", "").strip()
    if not v:
        return []
    if v == "demo":
        from app.docs.invoicegen import VENDORS
        return list(VENDORS)
    return [x.strip() for x in v.split(";") if x.strip()]


def reconcile_vendor(name: str, master: list) -> tuple:
    """(kanonik ad | None, 'exact'|'snapped'|'unknown'). OCR 'Dijital'->'Dilital' kimi kiçik səhvləri siyahıdakı adla düzəldir,
    uzaq adı (uydurma) 'unknown' sayır ki, insan baxsın."""
    slug = slugify(name)
    by_slug = {slugify(m): m for m in master}
    if slug in by_slug:
        return by_slug[slug], "exact"
    best, ratio = None, 0.0
    for sl, canon in by_slug.items():
        r = SequenceMatcher(None, slug, sl).ratio()
        if r > ratio:
            best, ratio = canon, r
    return (best, "snapped") if best and ratio >= SNAP_RATIO else (None, "unknown")


# ------------------------------------------------------------------ təmir
def repair_invoice_no(data: dict, text: str):
    """Kiçik model nömrənin içinə boşluq qoya bilir ('INV-2 026-906'). Boşluqsuz forması mətndə eynilə varsa, mətndəki formanı götürürük.
    (qaytarır: (data, qeyd | None)). Mətndə heç bir formada yoxdursa toxunmuruq, yoxlama onu rədd edəcək."""
    no = str(data.get("invoice_no") or "")
    if not no or no.strip().casefold() in text.casefold():
        return data, None
    squashed = re.sub(r"\s+", "", no)
    m = re.search(r"\s?".join(re.escape(c) for c in squashed), text, re.I)
    if m and re.sub(r"\s+", "", m.group(0)).casefold() == squashed.casefold() and " " not in m.group(0).strip():
        return {**data, "invoice_no": m.group(0).strip()}, f"nömrə mətndəki formaya düzəldildi: {m.group(0).strip()}"
    return data, None


# ------------------------------------------------------------------ yoxlama
def _amount_forms(v: float) -> set:
    plain = f"{v:.2f}"
    comma_thou = f"{v:,.2f}"
    return {plain, comma_thou, comma_thou.replace(",", " ").replace(".", ","), comma_thou.replace(",", "X").replace(".", ",").replace("X", ".")}


def _date_forms(iso: str) -> set:
    y, m, d = iso.split("-")
    return {iso, f"{d}.{m}.{y}", f"{int(d)} {MONTHS[int(m) - 1]} {y}", f"{d}/{m}/{y}"}


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s).casefold()


def validate(data: dict, text: str, ocr_conf: Optional[float] = None) -> list:
    """Problemlərin siyahısı (boşdursa nəticə qəbul olunur). Hər dəyər mətndə olmalıdır: LLM uydura bilməz."""
    issues = []
    flat = _squash(text)
    for k in ("invoice_no", "date", "vendor", "total"):
        if data.get(k) in (None, ""):
            issues.append(f"{k} tapılmadı")
    if issues:
        return issues
    try:
        datetime.strptime(data["date"], "%Y-%m-%d")
    except ValueError:
        issues.append("tarix YYYY-MM-DD deyil")
    else:
        if not any(_squash(f) in flat for f in _date_forms(data["date"])):
            issues.append("tarix sənəd mətnində yoxdur")
    if str(data["invoice_no"]).strip().casefold() not in text.casefold():       # nömrə EYNİLƏ olmalıdır: 'INV-2 026-906' ≠ 'INV-2026-906'
        issues.append("nömrə sənəd mətnində yoxdur")
    elif FOREIGN_SCRIPT.search(str(data["invoice_no"])):
        issues.append("nömrədə Kiril/Yunan hərfləri var (OCR 'HF'-i 'НЕ' oxuya bilər)")
    if _squash(str(data["vendor"])) not in flat:
        issues.append("satıcı adı sənəd mətnində yoxdur")
    elif re.search(r"[|_~^<>]", str(data["vendor"])):
        issues.append("satıcı adında şübhəli simvol var (OCR səs-küyü)")
    total = data["total"]
    if not isinstance(total, (int, float)) or total <= 0:
        issues.append("yekun məbləğ müsbət ədəd deyil")
    elif not any(_squash(f) in flat for f in _amount_forms(float(total))):
        issues.append("yekun məbləğ sənəd mətnində yoxdur")
    vat = data.get("vat")
    if vat is not None and isinstance(total, (int, float)) and total > 0:
        if abs(vat - total * VAT_RATE / (1 + VAT_RATE)) > 0.05:
            issues.append("ƏDV məbləği yekunun 18/118 hissəsi ilə uyğun deyil")
        elif not any(_squash(f) in flat for f in _amount_forms(float(vat))):
            issues.append("ƏDV məbləği sənəd mətnində yoxdur")
    if ocr_conf is not None and ocr_conf < MIN_OCR_CONF:
        issues.append(f"OCR etibarı aşağıdır ({ocr_conf:.0f})")
    return issues


# ------------------------------------------------------------------ LLM
SYSTEM = (
    "Sən qaimə-faktura mətnindən sahələri çıxarırsan. Yalnız sənəddə YAZILMIŞ dəyərləri götür, heç nə uydurma.\n"
    "Qaydalar:\n"
    "- invoice_no: sənədin nömrəsi (sətirdəki nömrə işarəsi OCR-da 'Ne', 'Nə', '№' kimi oxunmuş ola bilər: onu nömrəyə daxil etmə).\n"
    "- date: YYYY-MM-DD formatında. 'gg.aa.iiii', 'iiii-aa-gg' və 'g ay iiii-cı il' formalarının hamısı bu formata çevrilir "
    "(aylar: yanvar=01 ... dekabr=12). Tarixi YALNIZ sənəddəki tarixdən götür.\n"
    "- vendor: SATAN tərəf (Satıcı, Supplier, Təchizatçı). Alıcı, müştəri və ya 'Bill to' DEYİL.\n"
    "- total: ÖDƏNİLƏCƏK yekun məbləğ, ƏDV daxil (Cəmi ödəniləcək, Total due, Yekun məbləğ). 'ƏDV-siz' sətri DEYİL.\n"
    "- vat: ƏDV MƏBLƏĞİ (pulla), faiz DEYİL. '(18%)' OCR-da '(1896)' kimi oxunmuş ola bilər, o məbləğ deyil.\n"
    "- Rəqəm formatları: '3.422,00', '3 422,00' və '3,422.00' hamısı 3422.00 deməkdir.\n"
    "- currency: AZN ('manat' də AZN-dir)."
)


@dataclass
class Deps:
    local: Optional[Callable] = None      # () -> runnable (invoke(msgs) -> InvoiceData)
    claude: Optional[Callable] = None


def default_deps() -> Deps:
    from app import llm
    return Deps(local=lambda: llm.local_chat().with_structured_output(InvoiceData),
                claude=lambda: llm.claude_chat().with_structured_output(InvoiceData))


def llm_extract(text: str, runnable) -> Optional[dict]:
    from langchain_core.messages import HumanMessage, SystemMessage
    try:
        out = runnable.invoke([SystemMessage(content=SYSTEM), HumanMessage(content=f"Sənəd mətni:\n\n{text}")])
    except Exception:
        return None                                   # parse xətası, timeout və s.: növbəti pilləyə keç
    return out.model_dump() if out is not None else None


# ------------------------------------------------------------------ konveyer
@dataclass
class Extraction:
    data: dict
    extractor: str                     # regex | local | claude | none
    issues: list = field(default_factory=list)
    status: str = "needs_review"
    calls: dict = field(default_factory=dict)
    tried: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def extract(text: str, mode: str = "ladder", allow_cloud: Optional[bool] = None, deps: Optional[Deps] = None,
            ocr_conf: Optional[float] = None) -> Extraction:
    """mode: regex | local | claude | ladder (regex -> lokal -> insan) | ladder-cloud (regex -> lokal -> Claude -> insan)."""
    if allow_cloud is None:
        allow_cloud = os.environ.get("ALLOW_CLOUD_DOCS", "0") == "1"
    if mode == "ladder-cloud":
        mode, allow_cloud = "ladder", True
    if mode == "claude" and not allow_cloud:
        raise PermissionError("Claude rejimi sənədi buluda göndərir: ALLOW_CLOUD_DOCS=1 olmadan icazə yoxdur")
    deps = deps or default_deps()
    steps = {"regex": ["regex"], "local": ["local"], "claude": ["claude"],
             "ladder": ["regex", "local"] + (["claude"] if allow_cloud else [])}[mode]
    res = Extraction(data={}, extractor="none")
    for step in steps:
        if step == "regex":
            data = regex_extract(text)
        elif step == "local":
            res.calls["local"] = res.calls.get("local", 0) + 1
            data = llm_extract(text, deps.local())
        else:
            res.calls["claude"] = res.calls.get("claude", 0) + 1
            data = llm_extract(mask_pii(text), deps.claude())
        res.tried.append(step)
        if data is None:
            res.issues = [f"{step}: cavab alınmadı"]
            continue
        data, repaired = repair_invoice_no(data, text)
        if repaired:
            res.notes.append(repaired)
        issues = validate(data, text, ocr_conf)
        master = vendor_master()
        if master and not issues:                                     # mətndə olan satıcı adı siyahı ilə uyğunlaşdırılır
            canon, how = reconcile_vendor(str(data["vendor"]), master)
            if how == "unknown":
                issues.append("satıcı təchizatçı siyahısında yoxdur")
            else:
                data = {**data, "vendor": canon}
                if how == "snapped":
                    res.notes.append(f"satıcı siyahıdakı adla düzəldildi: {canon}")
        res.data, res.extractor, res.issues = data, step, issues
        if not issues:
            res.status = "ok"
            return res
    return res                                         # hamısı uğursuz: needs_review (insan baxışı)
