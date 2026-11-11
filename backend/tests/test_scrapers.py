from app.scrapers.api import parse_api
from app.scrapers.base import SiteConfig
from app.scrapers.detect import detect_rendering
from app.scrapers.static import parse_html, scrape_static
from tests.conftest import FakeSession

CFG = SiteConfig(id="t", site="t", start_url="http://s/?page=1", stock_selector="span.stock", next_selector="a.next")

PAGE1 = """<html><body>
<article class="product"><h3><a title="Telefon A" href="/p/a">Telefon...</a></h3><p class="price">749.00 AZN</p><span class="stock">Stokdadır</span></article>
<article class="product"><h3><a title="Telefon B" href="/p/b">Tel...</a></h3><p class="price">1 450,00 ₼</p><span class="stock">Stokda yoxdur</span></article>
<article class="product"><h3><a title="Qiymətsiz" href="/p/c">x</a></h3></article>
<article class="product"><h3><a title="Pis qiymət" href="/p/d">x</a></h3><p class="price">tezliklə</p></article>
<a class="next" href="/?page=2">Növbəti</a></body></html>"""
PAGE2 = """<html><body><article class="product"><h3><a title="Telefon C" href="/p/e">T</a></h3><p class="price">99.90 AZN</p><span class="stock">Stokdadır</span></article></body></html>"""


def test_parse_html_extracts_and_skips_broken_cards():
    items, warnings, nxt = parse_html(PAGE1, CFG, "http://s/")
    assert [(i.name, i.price, i.in_stock) for i in items] == [("Telefon A", 749.0, True), ("Telefon B", 1450.0, False)]
    assert items[0].url == "http://s/p/a" and items[1].currency == "AZN"
    assert len(warnings) == 2 and nxt == "http://s/?page=2"


def test_scrape_static_follows_pagination_and_stops():
    sess = FakeSession({"http://s/?page=1": PAGE1, "http://s/?page=2": PAGE2})
    res = scrape_static(CFG, sess)
    assert res.pages == 2 and [i.name for i in res.items] == ["Telefon A", "Telefon B", "Telefon C"]
    assert sess.calls == ["http://s/?page=1", "http://s/?page=2"]


def test_scrape_static_respects_max_pages_and_loops():
    loop = '<article class="product"><h3><a title="X" href="/x">x</a></h3><p class="price">1.00 AZN</p></article><a class="next" href="/?page=1">n</a>'
    res = scrape_static(CFG, FakeSession({"http://s/?page=1": loop}))
    assert res.pages == 1                       # özünə qayıdan 'növbəti' sonsuz dövr yaratmır


def test_layout_change_yields_zero_items():
    items, _, _ = parse_html(PAGE1.replace('class="product"', 'class="item-box"'), CFG, "http://s/")
    assert items == []


def test_detect_static_vs_dynamic():
    assert detect_rendering(PAGE1, "article.product")["kind"] == "static"
    dyn = "<html><body><div id=list>Yüklənir</div><script>fetch('/api')</script></body></html>"
    assert detect_rendering(dyn, "article.product")["kind"] == "dynamic"
    assert detect_rendering("<html><body></body></html>", "article.product")["kind"] == "unknown"


def test_parse_api_handles_strings_numbers_and_bad_rows():
    data = {"products": [{"name": "A", "price": 10.5, "in_stock": True}, {"name": "B", "price": "1 450,00 ₼", "in_stock": False},
                         {"name": "C"}, {"price": 5}, {"name": "D", "price": "yoxdur"}]}
    items, warnings = parse_api(data, CFG)
    assert [(i.name, i.price, i.in_stock) for i in items] == [("A", 10.5, True), ("B", 1450.0, False)]
    assert len(warnings) == 3
