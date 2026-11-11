"""Statik səhifə: requests + BeautifulSoup (dərs, bölmə 4). 'View Page Source'-da məlumat görünürsə bu kifayətdir."""

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.parsing import detect_currency, parse_price
from app.scrapers.base import Item, ScrapeResult, SiteConfig

OUT_OF_STOCK = re.compile(r"yoxdur|bitib|out of stock|tükənib|sold out", re.I)


def parse_html(html: str, cfg: SiteConfig, base_url: str = "") -> tuple:
    """Bir səhifənin HTML-indən məhsul siyahısı. Sayt dizaynı dəyişəndə None yoxlaması səssiz sınmanın qarşısını alır."""
    soup = BeautifulSoup(html, "html.parser")
    items, warnings = [], []
    for card in soup.select(cfg.item_selector):
        name_el = card.select_one(cfg.name_selector)
        price_el = card.select_one(cfg.price_selector)
        if name_el is None or price_el is None:
            warnings.append("kartda ad və ya qiymət elementi tapılmadı, keçildi")
            continue
        name = (name_el.get(cfg.name_attr) if cfg.name_attr else None) or name_el.get_text(strip=True)
        raw = price_el.get_text(strip=True)
        try:
            price = parse_price(raw)
        except ValueError as e:
            warnings.append(f"{name}: {e}")
            continue
        stock_el = card.select_one(cfg.stock_selector) if cfg.stock_selector else None
        in_stock = not (stock_el and OUT_OF_STOCK.search(stock_el.get_text(" ", strip=True)))
        link_el = card.select_one(cfg.link_selector)
        url = urljoin(base_url, link_el["href"]) if link_el is not None and link_el.get("href") else ""
        items.append(Item(name=name.strip(), price=price, currency=detect_currency(raw, cfg.default_currency),
                          in_stock=in_stock, url=url))
    next_url = None
    if cfg.next_selector:
        nxt = soup.select_one(cfg.next_selector)
        if nxt is not None and nxt.get("href"):
            next_url = urljoin(base_url, nxt["href"])
    return items, warnings, next_url


def scrape_static(cfg: SiteConfig, session) -> ScrapeResult:
    res = ScrapeResult(strategy="static")
    url, seen = cfg.start_url, set()
    while url and url not in seen and res.pages < cfg.max_pages:
        seen.add(url)
        r = session.get(url)
        r.raise_for_status()
        items, warnings, url = parse_html(r.text, cfg, base_url=r.url if hasattr(r, "url") and r.url else url)
        res.items.extend(items)
        res.warnings.extend(warnings)
        res.pages += 1
    return res
