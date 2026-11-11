"""Statik, yoxsa dinamik? (dərs, bölmə 3). Əl ilə 'View Page Source' etməyin avtomatik formasıdır:
xam HTML-də məhsul kartları varsa statikdir (BeautifulSoup kifayətdir), yoxdursa və səhifədə JavaScript varsa dinamikdir."""

from bs4 import BeautifulSoup


def detect_rendering(html: str, item_selector: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    n = len(soup.select(item_selector))
    scripts = len(soup.find_all("script"))
    if n > 0:
        return {"kind": "static", "cards": n, "reason": f"xam HTML-də {n} kart var, BeautifulSoup kifayətdir"}
    if scripts > 0:
        return {"kind": "dynamic", "cards": 0,
                "reason": f"xam HTML-də kart yoxdur, amma {scripts} script var: məlumat JavaScript ilə yüklənir "
                          "(əvvəlcə arxadakı API-ni axtar, yoxdursa Selenium)"}
    return {"kind": "unknown", "cards": 0, "reason": "nə kart, nə script tapıldı: selector səhvdir və ya səhifə boşdur"}
