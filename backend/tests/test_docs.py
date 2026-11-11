import io

import pytest

from app.docs import invoicegen as ig
from app.docs.extract import Deps, InvoiceData, extract, mask_pii, regex_extract, validate
from app.docs.reader import read_document


def truth_text(seed=1, tpl="A"):
    inv = ig.make_invoice(seed, tpl)
    return inv, "\n".join(ig.render_lines(inv, tpl))


# ------------------------------------------------------------------ generator
@pytest.mark.parametrize("tpl", ["A", "B", "C"])
def test_truth_is_arithmetically_consistent(tpl):
    for seed in range(1, 20):
        inv = ig.make_invoice(seed, tpl)
        assert inv.subtotal == pytest.approx(sum(i["qty"] * i["unit"] for i in inv.items), abs=0.02)
        assert inv.vat == pytest.approx(inv.subtotal * 0.18, abs=0.01)
        assert inv.total == pytest.approx(inv.subtotal + inv.vat, abs=0.01)


def test_generator_is_deterministic_and_templates_differ():
    assert ig.make_invoice(3, "A") == ig.make_invoice(3, "A")
    assert ig.make_invoice(3, "A").invoice_no != ig.make_invoice(3, "B").invoice_no


# ------------------------------------------------------------------ oxuyucu
def test_text_pdf_roundtrip_via_pypdf():
    inv, text = truth_text(2, "A")
    doc = read_document(ig.to_pdf_bytes(text.split("\n")), "a.pdf")
    assert doc.kind == "pdf-text" and doc.method == "pypdf"
    assert inv.invoice_no in doc.text and inv.vendor in doc.text


def test_scanned_pdf_has_no_text_layer_and_falls_back_to_ocr():
    inv, text = truth_text(2, "A")
    pdf = ig.image_to_pdf_bytes(ig.to_image(text.split("\n")))
    from app.docs.reader import _pdf_text
    assert len(_pdf_text(pdf).strip()) < 20                    # pypdf boş qaytarır
    doc = read_document(pdf, "scan.pdf")
    assert doc.kind == "pdf-scan" and doc.method == "ocr" and doc.meta["ocr_conf"] > 70
    assert inv.invoice_no.replace("-", "") in doc.text.replace("-", "").replace(" ", "")


def test_image_ocr_clean_extracts_all_fields():
    inv, text = truth_text(4, "A")
    doc = read_document(ig.image_to_bytes(ig.to_image(text.split("\n"))), "x.png")
    rx = regex_extract(doc.text)
    assert rx["date"] == inv.date and rx["total"] == inv.total and rx["vat"] == inv.vat


def test_unsupported_format():
    with pytest.raises(ValueError):
        read_document(b"x", "a.docx")


# ------------------------------------------------------------------ regex baseline
@pytest.mark.parametrize("tpl", ["A", "B"])
def test_regex_baseline_solves_known_templates(tpl):
    for seed in range(1, 9):
        inv, text = truth_text(seed, tpl)
        rx = regex_extract(text)
        assert rx["invoice_no"] == inv.invoice_no and rx["date"] == inv.date and rx["vendor"] == inv.vendor
        assert rx["total"] == inv.total and rx["vat"] == inv.vat, (tpl, seed, rx)


def test_regex_baseline_does_not_know_template_c():
    inv, text = truth_text(1, "C")
    rx = regex_extract(text)
    assert rx["total"] is None or rx["invoice_no"] != inv.invoice_no


def test_regex_tolerates_ocr_variants_of_number_sign_and_label():
    assert regex_extract("QAİMƏ-FAKTURA Ne 2026-0424\nSatici: Sirvan Texno MMC")["invoice_no"] == "2026-0424"
    assert regex_extract("QAİMƏ-FAKTURA Na 2026-0708\nSatıcı: X MMC")["invoice_no"] == "2026-0708"
    assert regex_extract("QAİMƏ-FAKTURA N: 2026-0346\nSatıcı: X MMC")["invoice_no"] == "2026-0346"
    assert regex_extract("QAİMƏ-FAKTURA Nə 2026-0346\nSatici: Sirvan Texno MMC")["vendor"] == "Sirvan Texno MMC"
    assert regex_extract("Nova Tech MMC\nNo 12")["invoice_no"] is None                # 'Nova' sözündəki 'No' nömrə kimi tutulmur


def test_regex_ignores_subtotal_line_for_vat():
    text = "Yekun (ƏDV-siz): 1966.45 AZN\nƏDV (18%): 353.96 AZN"
    assert regex_extract(text)["vat"] == 353.96


def test_regex_cleans_ocr_noise_after_vendor():
    assert regex_extract("Satıcı: Nova Tech MMC | |\n")["vendor"] == "Nova Tech MMC"


# ------------------------------------------------------------------ yoxlayıcı
def good(inv, text):
    return {"invoice_no": inv.invoice_no, "date": inv.date, "vendor": inv.vendor, "total": inv.total, "vat": inv.vat, "currency": "AZN"}


def test_validate_accepts_correct_data_in_all_number_formats():
    for tpl in "ABC":
        inv, text = truth_text(5, tpl)
        assert validate(good(inv, text), text) == [], tpl


def test_validate_catches_hallucinations_and_inconsistencies():
    inv, text = truth_text(5, "A")
    d = good(inv, text)
    assert "nömrə sənəd mətnində yoxdur" in validate({**d, "invoice_no": "2026-9999"}, text)
    assert "yekun məbləğ sənəd mətnində yoxdur" in validate({**d, "total": d["total"] + 100, "vat": None}, text)
    assert any("18/118" in i for i in validate({**d, "vat": 100.0}, text))
    assert any("tarix" in i for i in validate({**d, "date": "2026-13-45"}, text))
    assert any("tarix" in i for i in validate({**d, "date": "2025-01-01"}, text))
    assert "satıcı adı sənəd mətnində yoxdur" in validate({**d, "vendor": "Uydurma MMC"}, text)
    noisy = text.replace(inv.vendor, inv.vendor + " |", 1)
    assert any("şübhəli simvol" in i for i in validate({**d, "vendor": inv.vendor + " |"}, noisy))
    assert any("OCR etibarı" in i for i in validate(d, text, ocr_conf=40))
    assert "invoice_no tapılmadı" in validate({**d, "invoice_no": None}, text)


# ------------------------------------------------------------------ məxfilik
def test_mask_pii_hides_contacts_but_keeps_invoice_fields():
    inv, text = truth_text(7, "A")
    masked = mask_pii(text)
    assert inv.phone not in masked and inv.email not in masked and inv.iban not in masked
    assert "[TELEFON]" in masked and "[EMAIL]" in masked and "[IBAN]" in masked
    assert inv.invoice_no in masked and inv.vendor in masked and f"{inv.total:.2f}" in masked
    assert validate(good(inv, masked), masked) == []           # maskalanmış mətndə də yoxlama keçir


# ------------------------------------------------------------------ konveyer
class FakeLLM:
    def __init__(self, data):
        self.data, self.seen = data, []

    def invoke(self, msgs):
        self.seen.append(msgs[-1].content)
        return None if self.data is None else InvoiceData(**self.data)


def deps(local=None, claude=None):
    return Deps(local=lambda: local, claude=lambda: claude)


def test_ladder_stops_at_regex_when_valid_no_llm_calls():
    inv, text = truth_text(1, "A")
    llm = FakeLLM(None)
    r = extract(text, "ladder", allow_cloud=False, deps=deps(llm, llm))
    assert r.ok and r.extractor == "regex" and r.calls == {} and llm.seen == []


def test_ladder_falls_to_local_for_unknown_template():
    inv, text = truth_text(1, "C")
    local = FakeLLM(good(inv, text))
    r = extract(text, "ladder", allow_cloud=False, deps=deps(local, None))
    assert r.ok and r.extractor == "local" and r.calls == {"local": 1}
    assert inv.phone in local.seen[0]                           # lokal model xam mətni görür (məxfilik: maşından çıxmır)


def test_ladder_without_cloud_permission_ends_in_review():
    inv, text = truth_text(1, "C")
    bad = dict(good(inv, text), total=999999.0)
    r = extract(text, "ladder", allow_cloud=False, deps=deps(FakeLLM(bad), FakeLLM(good(inv, text))))
    assert r.status == "needs_review" and "claude" not in r.calls and r.tried == ["regex", "local"]


def test_ladder_with_cloud_escalates_with_masked_text_only():
    inv, text = truth_text(1, "C")
    bad = dict(good(inv, text), total=999999.0)
    claude = FakeLLM(good(inv, text))
    r = extract(text, "ladder", allow_cloud=True, deps=deps(FakeLLM(bad), claude))
    assert r.ok and r.extractor == "claude" and r.calls == {"local": 1, "claude": 1}
    sent = claude.seen[0]
    assert inv.email not in sent and inv.phone not in sent and inv.iban not in sent   # buluda şəxsi məlumat getmir


def test_llm_failure_is_not_fatal():
    inv, text = truth_text(1, "C")
    r = extract(text, "local", deps=deps(FakeLLM(None), None))
    assert r.status == "needs_review" and r.issues


def test_hallucinated_llm_answer_is_rejected():
    inv, text = truth_text(1, "C")
    r = extract(text, "local", deps=deps(FakeLLM(dict(good(inv, text), invoice_no="HF/777/26")), None))
    assert r.status == "needs_review" and "nömrə sənəd mətnində yoxdur" in r.issues


def test_claude_mode_requires_cloud_permission():
    with pytest.raises(PermissionError):
        extract("x", "claude", allow_cloud=False, deps=deps(None, None))


# ------------------------------------------------------------------ eval-dan çıxan qorumalar
def test_foreign_script_in_invoice_number_is_flagged():
    inv, text = truth_text(3, "C")
    bad_no = "НЕ/425/26"                                              # Kiril 'Н', 'Е' (OCR 'HF'-i belə oxuyub)
    text2 = text.replace(inv.invoice_no, bad_no)
    issues = validate({**good(inv, text), "invoice_no": bad_no}, text2)
    assert any("Kiril" in i for i in issues)
    assert validate(good(inv, text), text) == []                       # normal Latın nömrə problemsizdir


def test_reconcile_vendor_exact_snapped_unknown():
    from app.docs.extract import reconcile_vendor
    master = ["Abşeron Dijital MMC", "Nova Tech MMC", "Şirvan Texno MMC"]
    assert reconcile_vendor("Abşeron Dijital MMC", master) == ("Abşeron Dijital MMC", "exact")
    assert reconcile_vendor("Sirvan Texno MMC", master) == ("Şirvan Texno MMC", "exact")      # OCR 'Ş'->'S' diakritik fərqidir
    assert reconcile_vendor("Abşeron Dilital MMC", master) == ("Abşeron Dijital MMC", "snapped")
    assert reconcile_vendor("Uydurma Firma MMC", master) == (None, "unknown")


def test_pipeline_snaps_ocr_garbled_vendor_and_rejects_unknown_vendor(monkeypatch):
    inv = ig.make_invoice(1, "C")
    inv.vendor = "Abşeron Dijital MMC"
    text = "\n".join(ig.render_lines(inv, "C")).replace("Dijital", "Dilital")        # OCR 'j' -> 'l' oxuyub
    data = dict(good(inv, text), vendor="Abşeron Dilital MMC")
    monkeypatch.setenv("VENDOR_MASTER", "Abşeron Dijital MMC;Nova Tech MMC")
    r = extract(text, "local", deps=deps(FakeLLM(data), None))
    assert r.ok and r.data["vendor"] == "Abşeron Dijital MMC" and r.notes            # siyahıdakı adla düzəldildi, qeyd düşdü
    monkeypatch.setenv("VENDOR_MASTER", "Tamam Başqa MMC;Nova Tech MMC")
    r2 = extract(text, "local", deps=deps(FakeLLM(data), None))
    assert r2.status == "needs_review" and "satıcı təchizatçı siyahısında yoxdur" in r2.issues
    monkeypatch.setenv("VENDOR_MASTER", "")                                          # siyahı söndürülüb: köhnə davranış
    r3 = extract(text, "local", deps=deps(FakeLLM(data), None))
    assert r3.ok and r3.data["vendor"] == "Abşeron Dilital MMC" and not r3.notes


def test_vendor_master_env_parsing(monkeypatch):
    from app.docs.extract import vendor_master
    monkeypatch.setenv("VENDOR_MASTER", "")
    assert vendor_master() == []
    monkeypatch.setenv("VENDOR_MASTER", "A MMC; B MMC ;")
    assert vendor_master() == ["A MMC", "B MMC"]
    monkeypatch.setenv("VENDOR_MASTER", "demo")
    assert "Nova Tech MMC" in vendor_master()


def test_system_prompt_has_no_concrete_example_date():
    """Kiçik lokal model prompt-dakı nümunə tarixi oxuya bilmədikdə təkrar edirdi (inv-003 skanında müşahidə olundu)."""
    from app.docs.extract import SYSTEM
    import re
    assert not re.search(r"\d{2}\.\d{2}\.\d{4}|\d{4}-\d{2}-\d{2}", SYSTEM)


def test_invoice_number_must_match_text_verbatim_not_squashed():
    inv, text = truth_text(2, "B")
    spaced = {**good(inv, text), "invoice_no": inv.invoice_no[:5] + " " + inv.invoice_no[5:]}
    assert "nömrə sənəd mətnində yoxdur" in validate(spaced, text)           # əvvəl boşluqları atıb qəbul edirdi: səssiz səhv


def test_repair_invoice_no_restores_text_form_and_pipeline_accepts():
    from app.docs.extract import repair_invoice_no
    inv, text = truth_text(2, "B")
    broken = inv.invoice_no[:5] + " " + inv.invoice_no[5:]                    # 'INV-2 026-...'
    fixed, note = repair_invoice_no({**good(inv, text), "invoice_no": broken}, text)
    assert fixed["invoice_no"] == inv.invoice_no and note
    r = extract(text, "local", deps=deps(FakeLLM({**good(inv, text), "invoice_no": broken}), None))
    assert r.ok and r.data["invoice_no"] == inv.invoice_no and any("düzəldildi" in n for n in r.notes)
    # mətndə heç olmayan nömrə təmir olunmur
    same, note2 = repair_invoice_no({**good(inv, text), "invoice_no": "INV-9 999-000"}, text)
    assert note2 is None and same["invoice_no"] == "INV-9 999-000"


def test_invoice_font_path_can_be_overridden_by_env(monkeypatch):
    import importlib
    monkeypatch.setenv("INVOICE_FONT", "/custom/fonts/Some.ttf")
    mod = importlib.reload(ig)
    try:
        assert mod.FONT == "/custom/fonts/Some.ttf"
    finally:
        monkeypatch.undo()
        importlib.reload(ig)


def test_invoice_font_defaults_to_docker_path(monkeypatch):
    import importlib
    monkeypatch.delenv("INVOICE_FONT", raising=False)
    mod = importlib.reload(ig)
    try:
        assert mod.FONT == "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    finally:
        monkeypatch.undo()
        importlib.reload(ig)
