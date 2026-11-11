"""Rəqib mağaza simulyatoru (QiymətRadar-ın scraping hədəfi).

Real sayta zərər vermədən scraping-i, qiymət fərqini və səhvləri sınamaq üçün:
- /                 statik HTML (8 məhsul/səhifə, a.next ilə səhifələmə)  -> requests + BeautifulSoup
- /dynamic          boş səhifə, JavaScript 900 ms sonra /api/products-dan doldurur  -> Selenium
- /api/products     eyni məlumat JSON  -> API (ən etibarlı yol)
- /robots.txt       /private/ qadağan, Crawl-delay: 1
- /private/prices   topdan qiymətlər (scraper bura GİRMƏMƏLİDİR)
- /docs/...         mətnli PDF qaimələr, skan PDF və şəkillər
- POST /admin/advance  bir gün irəli: bəzi qiymətlər dəyişir, stok dəyişir, məhsul əlavə/silinir
- POST /admin/glitch   mode=layout|price_format|none: sayt dizaynı dəyişir / qiymət formatı dəyişir (scraper-in dözümlülüyünü sınamaq üçün)
- POST /admin/reset
"""

import html
import random

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response

from app.docs import invoicegen as ig

app = FastAPI(title="DemoShop", docs_url=None, redoc_url=None, openapi_url=None)   # /docs bizim sənəd siyahımızdır, Swagger deyil

CATALOG = [
    ("Samsung Galaxy A55 telefon", 749.0), ("Apple iPhone 15 telefon", 2399.0), ("Xiaomi Redmi Note 13 telefon", 459.0),
    ("Lenovo IdeaPad 15 noutbuk", 1450.0), ("HP Pavilion 14 noutbuk", 1299.0), ("Asus Vivobook 16 noutbuk", 1190.0),
    ("Samsung 27 düym monitor", 520.0), ("LG UltraWide 34 monitor", 980.0), ("Logitech MX Master siçan", 189.0),
    ("Mexaniki klaviatura RGB", 95.0), ("Sony WH-1000XM5 qulaqlıq", 649.0), ("JBL Flip 6 dinamik", 229.0),
    ("Apple iPad 10 planşet", 1099.0), ("Samsung Galaxy Tab S9 planşet", 1349.0), ("Canon EOS R50 fotoaparat", 1799.0),
    ("GoPro Hero 12 kamera", 799.0), ("TP-Link Wi-Fi 6 router", 125.0), ("Xarici disk 2TB", 170.0),
    ("Flash yaddaş 128GB", 28.0), ("Powerbank 20000 mAh", 59.0), ("Smart saat Amazfit GTR", 289.0), ("Veb kamera Full HD", 64.0),
    ("Printer HP LaserJet", 380.0), ("Oyun konsolu PS5", 1399.0),
]
EXTRA = {2: ("DJI Mini 4 dron", 1850.0), 4: ("Kindle Paperwhite oxu cihazı", 289.0)}   # gün -> yeni məhsul
REMOVED = {3: "Powerbank 20000 mAh"}                                                 # gün -> silinən məhsul
PER_PAGE = 8
STATE = {"day": 0, "glitch": "none"}


def products_at(day: int) -> list:
    """Deterministik: eyni gün həmişə eyni qiymətlər (testdə və eval-da truth kimi istifadə olunur)."""
    items = {n: {"name": n, "price": p, "in_stock": True} for n, p in CATALOG}
    for d in range(1, day + 1):
        for name, it in list(items.items()):
            rnd = random.Random(f"{name}-{d}")
            if rnd.random() < 0.35:
                it["price"] = round(it["price"] * (1 + rnd.choice([-1, 1]) * rnd.uniform(0.03, 0.15)), 2)
            if rnd.random() < 0.08:
                it["in_stock"] = not it["in_stock"]
        if d in EXTRA:
            n, p = EXTRA[d]
            items[n] = {"name": n, "price": p, "in_stock": True}
        if d in REMOVED:
            items.pop(REMOVED[d], None)
    return list(items.values())


def fmt_price(p: float) -> str:
    if STATE["glitch"] == "price_format":
        return f"{p:,.2f}".replace(",", " ").replace(".", ",") + " ₼"      # '1 450,00 ₼'
    return f"{p:.2f} AZN"


def card(it: dict, cls: dict) -> str:
    stock = "" if it["in_stock"] else "Stokda yoxdur"
    return (f'<article class="{cls["card"]}"><h3><a title="{html.escape(it["name"])}" href="/p/{html.escape(it["name"])}">'
            f'{html.escape(it["name"][:28])}...</a></h3><p class="{cls["price"]}">{fmt_price(it["price"])}</p>'
            f'<span class="stock">{stock or "Stokdadır"}</span></article>')


def classes() -> dict:
    # layout glitch: sayt dizaynı dəyişir, köhnə selector-lar sınır (real saytlarda tez-tez olur)
    return {"card": "item-box", "price": "amount"} if STATE["glitch"] == "layout" else {"card": "product", "price": "price"}


@app.get("/", response_class=HTMLResponse)
def index(page: int = Query(1, ge=1)):
    items = products_at(STATE["day"])
    chunk = items[(page - 1) * PER_PAGE: page * PER_PAGE]
    if not chunk:
        raise HTTPException(404, "səhifə yoxdur")
    cls = classes()
    nxt = f'<a class="next" href="/?page={page + 1}">Növbəti</a>' if page * PER_PAGE < len(items) else ""
    return f"<html><head><meta charset='utf-8'><title>DemoShop</title></head><body><h1>DemoShop</h1>{''.join(card(i, cls) for i in chunk)}{nxt}</body></html>"


@app.get("/dynamic", response_class=HTMLResponse)
def dynamic():
    cls = classes()
    return f"""<html><head><meta charset='utf-8'><title>DemoShop dinamik</title></head><body><h1>DemoShop</h1>
<div id="list">Yüklənir...</div>
<script>
setTimeout(async () => {{
  const r = await fetch('/api/products'); const data = await r.json();
  document.getElementById('list').innerHTML = data.products.map(p =>
    `<article class="{cls['card']}"><h3><a title="${{p.name}}" href="#">${{p.name.slice(0, 28)}}...</a></h3>` +
    `<p class="{cls['price']}">${{p.price_text}}</p><span class="stock">${{p.in_stock ? 'Stokdadır' : 'Stokda yoxdur'}}</span></article>`).join('');
}}, 900);
</script></body></html>"""


@app.get("/api/products")
def api_products():
    items = products_at(STATE["day"])
    return {"day": STATE["day"], "products": [{**i, "currency": "AZN", "price_text": fmt_price(i["price"])} for i in items]}


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots():
    return "User-agent: *\nDisallow: /private/\nCrawl-delay: 1\n"


@app.get("/private/prices", response_class=HTMLResponse)
def private():
    return "<html><body><article class='product'><h3><a title='Topdan qiymət'>x</a></h3><p class='price'>1.00 AZN</p></article></body></html>"


# ---------------------------------------------------------------- sənədlər
DOC_SPECS = {f"inv-{n:03d}": ("A" if n % 2 else "B", n) for n in range(1, 7)}


def _doc(name: str):
    if name not in DOC_SPECS:
        raise HTTPException(404, "sənəd yoxdur")
    tpl, seed = DOC_SPECS[name]
    inv = ig.make_invoice(seed, tpl)
    return inv, ig.render_lines(inv, tpl)


@app.get("/docs")
def docs_list():
    return {"documents": [{"name": n, "pdf": f"/docs/{n}.pdf", "scan_pdf": f"/docs/scan/{n}.pdf", "scan_image": f"/docs/scan/{n}.jpg"} for n in DOC_SPECS]}


@app.get("/docs/{name}.pdf")
def doc_pdf(name: str):
    _, lines = _doc(name)
    return Response(ig.to_pdf_bytes(lines), media_type="application/pdf")


@app.get("/docs/scan/{name}.pdf")
def doc_scan_pdf(name: str):
    _, lines = _doc(name)
    return Response(ig.image_to_pdf_bytes(ig.degrade(ig.to_image(lines), "noisy")), media_type="application/pdf")


@app.get("/docs/scan/{name}.jpg")
def doc_scan_jpg(name: str):
    _, lines = _doc(name)
    return Response(ig.image_to_bytes(ig.degrade(ig.to_image(lines), "noisy"), "JPEG"), media_type="image/jpeg")


@app.get("/docs/{name}.json")
def doc_truth(name: str):
    inv, _ = _doc(name)
    return inv.as_dict()


# ---------------------------------------------------------------- admin
@app.get("/admin/state")
def admin_state():
    return {"day": STATE["day"], "glitch": STATE["glitch"], "products": products_at(STATE["day"])}


@app.post("/admin/advance")
def admin_advance(days: int = 1):
    STATE["day"] += max(1, days)
    return {"day": STATE["day"]}


@app.post("/admin/glitch")
def admin_glitch(mode: str = "none"):
    if mode not in ("none", "layout", "price_format"):
        raise HTTPException(400, "mode: none | layout | price_format")
    STATE["glitch"] = mode
    return {"glitch": mode}


@app.post("/admin/reset")
def admin_reset():
    STATE.update(day=0, glitch="none")
    return STATE
