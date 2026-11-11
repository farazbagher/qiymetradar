import pytest

from app.parsing import detect_currency, parse_price, slugify


@pytest.mark.parametrize("raw,expected", [
    ("£51.77", 51.77), ("Â£51.77", 51.77), ("749.00 AZN", 749.0), ("1 450,00 AZN", 1450.0), ("1 450,00 ₼", 1450.0),
    ("1.450,00 ₼", 1450.0), ("3,422.00", 3422.0), ("3.422,00 manat", 3422.0), ("49,90", 49.9), ("1450", 1450.0),
    ("AZN 3422.00", 3422.0), ("1.450", 1450.0), ("0.450", 0.45), ("1,234,567.89", 1234567.89), ("1.234.567", 1234567.0),
    ("Qiymət: 28 AZN", 28.0), (" 1 450,00 ", 1450.0),
])
def test_parse_price_formats(raw, expected):
    assert parse_price(raw) == pytest.approx(expected)


@pytest.mark.parametrize("raw", ["pululsuz", "", "AZN", "0.00", "-"])
def test_parse_price_rejects_garbage(raw):
    with pytest.raises(ValueError):
        parse_price(raw)


def test_currency_detection():
    assert detect_currency("£51.77") == "GBP"
    assert detect_currency("1 450,00 ₼") == "AZN"
    assert detect_currency("3.422,00 manat") == "AZN"
    assert detect_currency("19.99") == "AZN"
    assert detect_currency("19.99", default="USD") == "USD"


def test_slugify_folds_azerbaijani_letters():
    assert slugify("Lenovo IdeaPad 15 noutbuk") == "lenovo-ideapad-15-noutbuk"
    assert slugify("Şirvan Çay-Əla ığ") == "sirvan-cay-ela-ig"
    assert slugify("  Sony WH-1000XM5  qulaqlıq ") == "sony-wh-1000xm5-qulaqliq"
