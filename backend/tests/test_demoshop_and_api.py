from fastapi.testclient import TestClient

from app.scrapers.base import SiteConfig
from app.scrapers.static import parse_html
from demoshop import server as shop
from tests.conftest import FakeResp

shop_client = TestClient(shop.app)
CFG = SiteConfig(id="d", site="demoshop", start_url="http://s/", stock_selector="span.stock", next_selector="a.next")


def setup_function():
    shop.STATE.update(day=0, glitch="none")


def all_pages_items():
    items, page = [], 1
    while True:
        r = shop_client.get(f"/?page={page}")
        if r.status_code == 404:
            return items
        items += parse_html(r.text, CFG, "http://s/")[0]
        page += 1


def test_shop_is_deterministic_and_changes_by_day():
    d0 = shop.products_at(0)
    assert shop.products_at(0) == d0 and len(d0) == 24
    d1 = shop.products_at(1)
    assert sum(a["price"] != b["price"] for a, b in zip(d0, d1)) > 0
    # gün 2: +dron, gün 3: -powerbank, gün 4: +kindle
    assert [len(shop.products_at(d)) for d in (2, 3, 4)] == [25, 24, 25]


def test_static_scraper_matches_shop_truth_on_all_pages_every_day():
    for day in range(0, 5):
        shop.STATE["day"] = day
        got = {i.name: (i.price, i.in_stock) for i in all_pages_items()}
        truth = {p["name"]: (p["price"], p["in_stock"]) for p in shop.products_at(day)}
        assert got == truth, day


def test_dynamic_page_has_no_cards_in_raw_html_but_api_has_them():
    r = shop_client.get("/dynamic")
    assert parse_html(r.text, CFG, "")[0] == [] and "<script>" in r.text
    assert len(shop_client.get("/api/products").json()["products"]) == 24


def test_layout_glitch_breaks_selectors_and_price_format_glitch_is_parsed():
    shop_client.post("/admin/glitch", params={"mode": "layout"})
    assert parse_html(shop_client.get("/").text, CFG, "")[0] == []
    shop_client.post("/admin/glitch", params={"mode": "price_format"})
    items = all_pages_items()
    assert len(items) == 24 and items[3].price == 1450.0                          # '1 450,00 ₼'
    assert shop_client.post("/admin/glitch", params={"mode": "bad"}).status_code == 400


def test_docs_route_is_ours_not_swagger():
    r = shop_client.get("/docs")
    assert r.headers["content-type"].startswith("application/json") and len(r.json()["documents"]) == 6


def test_extract_url_rejects_empty_and_non_http_urls(clean_db):
    with api_client() as c:
        assert c.post("/documents/extract-url", json={"url": ""}).status_code == 400
        assert c.post("/documents/extract-url", json={"url": "file:///etc/passwd"}).status_code == 400


def test_robots_and_documents_endpoints():
    assert "Disallow: /private/" in shop_client.get("/robots.txt").text
    pdf = shop_client.get("/docs/inv-001.pdf")
    assert pdf.content[:4] == b"%PDF" and shop_client.get("/docs/nope.pdf").status_code == 404
    assert shop_client.get("/docs/inv-001.json").json()["invoice_no"].startswith("2026-")


# ------------------------------------------------------------------ backend API (real test DB)
def api_client():
    from app.main import app
    return TestClient(app)


def test_ingest_twice_gives_diff_and_guards_against_broken_run(clean_db):
    with api_client() as c:
        rows = [{"title": f"Mehsul {i}", "price": f"{100 + i}.00 AZN", "stock": "Stokdadır"} for i in range(10)]
        r1 = c.post("/prices/ingest", json={"site": "t", "rows": rows}).json()
        assert r1["status"] == "ok" and r1["stats"]["baseline"] is True
        rows2 = [dict(r) for r in rows]
        rows2[0]["price"] = "130,00 ₼"                      # +30% (yerli format da oxunur)
        rows2[1]["stock"] = "Stokda yoxdur"
        r2 = c.post("/prices/ingest", json={"site": "t", "rows": rows2}).json()
        kinds = sorted(x["kind"] for x in r2["changes"])
        assert kinds == ["out_of_stock", "price_up"]
        # kəskin azalma: baza yenilənmir
        r3 = c.post("/prices/ingest", json={"site": "t", "rows": rows2[:3]}).json()
        assert r3["status"] == "error" and "kəskin azaldı" in r3["error"]
        assert c.get("/changes", params={"site": "t"}).json()["run_id"] == r2["run_id"]
        runs = c.get("/runs").json()["runs"]
        assert [r["status"] for r in runs][:1] == ["error"]


def test_ingest_skips_unparseable_rows_and_reports_warning(clean_db):
    with api_client() as c:
        r = c.post("/prices/ingest", json={"site": "t", "rows": [{"title": "A", "price": "10 AZN"}, {"title": "B", "price": "tezliklə"}]}).json()
        assert r["items"] == 1 and any("B" in w for w in r["warnings"])


def test_product_history_and_search(clean_db):
    with api_client() as c:
        for p in ("10.00", "12.00", "9.00"):
            c.post("/prices/ingest", json={"site": "t", "rows": [{"title": "Lenovo Noutbuk", "price": p}, {"title": "Mouse", "price": "5.00"}]})
        res = c.get("/products/search", params={"q": "lenovo"}).json()["results"]
        assert len(res) == 1 and [h["price"] for h in res[0]["history"]] == [10.0, 12.0, 9.0]
        assert c.get("/products", params={"site": "t"}).json()["products"][0]["site"] == "t"


def test_document_text_endpoint_with_regex_and_unknown_mode(clean_db):
    from app.docs import invoicegen as ig
    inv = ig.make_invoice(1, "A")
    text = "\n".join(ig.render_lines(inv, "A"))
    with api_client() as c:
        r = c.post("/documents/extract-text", json={"filename": "a.pdf", "text": text, "mode": "regex"}).json()
        assert r["status"] == "ok" and r["data"]["invoice_no"] == inv.invoice_no and r["extractor"] == "regex"
        assert c.get("/documents").json()["documents"][0]["status"] == "ok"
        assert c.post("/documents/extract-text", json={"text": text, "mode": "claude"}).status_code == 403


def test_document_upload_scanned_pdf_uses_ocr(clean_db):
    from app.docs import invoicegen as ig
    inv = ig.make_invoice(3, "A")           # seed 3: OCR bu şəkli təmiz oxuyur (deterministik)
    pdf = ig.image_to_pdf_bytes(ig.degrade(ig.to_image(ig.render_lines(inv, "A")), "noisy"))
    with api_client() as c:
        r = c.post("/documents/extract", files={"file": ("scan.pdf", pdf, "application/pdf")}, data={"mode": "regex"}).json()
        assert r["kind"] == "pdf-scan" and r["method"] == "ocr"
        assert r["status"] == "ok" and r["data"]["total"] == inv.total


def test_unsupported_upload_is_400(clean_db):
    with api_client() as c:
        assert c.post("/documents/extract", files={"file": ("a.docx", b"x", "application/octet-stream")}).status_code == 400
