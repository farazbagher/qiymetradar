"""API (dərs, bölmə 1): sayt arxada JSON verirsə, scraping-dən daha etibarlı və sürətlidir, həmişə ilk seçimdir."""

from app.parsing import detect_currency, parse_price
from app.scrapers.base import Item, ScrapeResult, SiteConfig


def parse_api(data, cfg: SiteConfig) -> tuple:
    items, warnings = [], []
    rows = data.get("products", data) if isinstance(data, dict) else data
    for row in rows:
        name = row.get("name") or row.get("title")
        raw = row.get("price")
        if not name or raw is None:
            warnings.append("sətirdə ad və ya qiymət yoxdur, keçildi")
            continue
        try:
            price = float(raw) if isinstance(raw, (int, float)) else parse_price(str(raw))
        except ValueError as e:
            warnings.append(f"{name}: {e}")
            continue
        items.append(Item(name=name, price=price, currency=row.get("currency") or detect_currency(str(raw), cfg.default_currency),
                          in_stock=bool(row.get("in_stock", True)), url=row.get("url", "")))
    return items, warnings


def scrape_api(cfg: SiteConfig, session) -> ScrapeResult:
    r = session.get(cfg.api_url or cfg.start_url)
    r.raise_for_status()
    items, warnings = parse_api(r.json(), cfg)
    return ScrapeResult(items=items, warnings=warnings, pages=1, strategy="api")
