"""Saytların konfiqurasiyası. demoshop = öz simulyasiya olunmuş rəqib mağazamız (qiymətləri dəyişdirmək olur).
books = real açıq məşq saytı (books.toscrape.com, robots.txt yoxdur)."""

import os

from app.scrapers.base import SiteConfig


def sites() -> dict:
    shop = os.environ.get("DEMOSHOP_URL", "http://demoshop:8090")
    common = dict(site="demoshop", item_selector="article.product", name_selector="h3 a", name_attr="title",
                  price_selector="p.price", stock_selector="span.stock", link_selector="h3 a", default_currency="AZN")
    return {
        "demoshop": SiteConfig(id="demoshop", start_url=f"{shop}/?page=1", strategy="static", next_selector="a.next", max_pages=5,
                               api_url=f"{shop}/api/products", **common),
        "demoshop-dynamic": SiteConfig(id="demoshop-dynamic", start_url=f"{shop}/dynamic", strategy="selenium",
                                       wait_selector="article.product", api_url=f"{shop}/api/products", **common),
        "demoshop-private": SiteConfig(id="demoshop-private", start_url=f"{shop}/private/prices", strategy="static",
                                       **{**common, "site": "demoshop-private"}),
        "books": SiteConfig(id="books", site="books", start_url="https://books.toscrape.com/catalogue/page-1.html", strategy="static",
                            item_selector="article.product_pod", name_selector="h3 a", name_attr="title", price_selector="p.price_color",
                            stock_selector="p.instock", link_selector="h3 a", next_selector="li.next a", max_pages=3, default_currency="GBP"),
    }
