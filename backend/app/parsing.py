"""Qiymət mətnini ədədə çevirmək və məhsul açarı (slug). Scraping-in ən kövrək yeri budur,
ona görə bütün sayt formatları (£51.77, 1 450,00 AZN, 1.450,00 ₼, 3,422.00) burada və testlərdə toplanıb."""

import re
import unicodedata

CURRENCY_MARKS = [
    ("£", "GBP"), ("$", "USD"), ("€", "EUR"), ("₼", "AZN"),
    ("azn", "AZN"), ("manat", "AZN"), ("usd", "USD"), ("eur", "EUR"), ("gbp", "GBP"),
]


def detect_currency(raw: str, default: str = "AZN") -> str:
    low = raw.lower()
    for mark, code in CURRENCY_MARKS:
        if mark in low:
            return code
    return default


def parse_price(raw: str) -> float:
    """'£51.77' -> 51.77, '1 450,00 AZN' -> 1450.0, '1.450,00 ₼' -> 1450.0, '3,422.00' -> 3422.0.

    Qayda: həm '.', həm ',' varsa sonuncusu onluq ayırıcıdır. Yalnız biri varsa və bir dəfə keçirsə,
    ondan sonra düz 3 rəqəm gəlirsə (və tam hissə 0 deyilsə) minlik ayırıcıdır ('1.450' -> 1450), əks halda onluqdur.
    Oxunmayan və ya müsbət olmayan qiymət ValueError verir: səssizcə 0 yazmaqdansa dayanmaq yaxşıdır."""
    s = raw.replace(" ", " ").replace(" ", " ").replace(" ", " ")
    # 'Â£51.77' kimi səhv kodlaşdırmanın qalığı da burada yox olur (yalnız rəqəm, nöqtə, vergül, boşluq saxlanır)
    m = re.search(r"\d[\d\s.,]*\d|\d", s)
    if not m:
        raise ValueError(f"qiymət oxunmadı: {raw!r}")
    num = re.sub(r"\s+", "", m.group())
    dots, commas = num.count("."), num.count(",")
    if dots and commas:
        dec = "." if num.rfind(".") > num.rfind(",") else ","
        thou = "," if dec == "." else "."
        num = num.replace(thou, "").replace(dec, ".")
    elif dots or commas:
        sep = "." if dots else ","
        if num.count(sep) > 1:
            num = num.replace(sep, "")                       # '1.234.567' -> minlik
        else:
            head, tail = num.split(sep)
            num = head + tail if (len(tail) == 3 and head not in ("0", "")) else head + "." + tail
    value = float(num)
    if value <= 0:
        raise ValueError(f"qiymət müsbət deyil: {raw!r}")
    return value


def slugify(name: str) -> str:
    """Məhsul adından sabit açar: kiçik hərf, diakritiklər azaldılıb, boşluq -> '-'."""
    table = str.maketrans({"ə": "e", "Ə": "e", "ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ç": "c", "Ç": "c",
                           "ğ": "g", "Ğ": "g", "ö": "o", "Ö": "o", "ü": "u", "Ü": "u"})
    folded = unicodedata.normalize("NFKD", name.translate(table)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", folded.lower()).strip("-")[:120]
