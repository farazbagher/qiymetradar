import os
from contextlib import asynccontextmanager
from typing import Optional

import requests
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from app import db, report, service
from app.docservice import process_document, process_text
from app.ethics import PoliteSession, RobotsDisallowed
from app.scrapers.detect import detect_rendering
from app.scrapers.sites import sites

DEMOSHOP = os.environ.get("DEMOSHOP_URL", "http://demoshop:8090")


class UTF8JSONResponse(JSONResponse):
    media_type = "application/json; charset=utf-8"

    def render(self, content):
        import json
        return json.dumps(content, ensure_ascii=False, default=str).encode("utf-8")


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.migrate()
    yield


app = FastAPI(title="QiymətRadar", default_response_class=UTF8JSONResponse, lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# ------------------------------------------------------------------ scraping
@app.get("/sites")
def list_sites() -> dict:
    return {"sites": [{"id": c.id, "site": c.site, "strategy": c.strategy, "url": c.start_url} for c in sites().values()]}


@app.post("/scrape/{site_id}")
def scrape(site_id: str, strategy: Optional[str] = None) -> dict:
    if strategy not in (None, "static", "api", "selenium"):
        raise HTTPException(400, "strategy: static | api | selenium")
    try:
        return service.run_scrape(site_id, strategy)
    except KeyError:
        raise HTTPException(404, f"naməlum sayt: {site_id}")


@app.get("/detect/{site_id}")
def detect(site_id: str) -> dict:
    """Statik, yoxsa dinamik? (xam HTML-də məhsul kartı varmı)."""
    cfg = sites().get(site_id)
    if cfg is None:
        raise HTTPException(404, "naməlum sayt")
    try:
        r = PoliteSession().get(cfg.start_url)
    except RobotsDisallowed as e:
        return {"kind": "blocked", "reason": str(e)}
    return detect_rendering(r.text, cfg.item_selector)


class IngestIn(BaseModel):
    site: str = "demoshop"
    rows: list
    strategy: str = "n8n"


@app.post("/prices/ingest")
def ingest(payload: IngestIn) -> dict:
    return service.ingest_raw(payload.site, payload.rows, payload.strategy)


@app.get("/changes")
def changes(site: str = "demoshop") -> dict:
    return service.latest_changes(site)


@app.get("/products")
def products(site: Optional[str] = None) -> dict:
    return {"products": db.list_products(site)}


@app.get("/products/search")
def product_search(q: str) -> dict:
    out = []
    for p in db.find_product(q):
        out.append({**p, "history": db.product_history(p["id"])})
    return {"results": out}


@app.get("/products/{product_id}/history")
def history(product_id: int) -> dict:
    return {"history": db.product_history(product_id)}


@app.get("/runs")
def runs() -> dict:
    return {"runs": db.list_runs()}


# ------------------------------------------------------------------ sənədlər
@app.post("/documents/extract")
async def extract_upload(file: UploadFile = File(...), mode: str = Form("ladder")) -> dict:
    data = await file.read()
    if len(data) > 15_000_000:
        raise HTTPException(413, "fayl 15 MB-dan böyükdür")
    try:
        return process_document(data, file.filename or "upload", mode)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except PermissionError as e:
        raise HTTPException(403, str(e))


class TextIn(BaseModel):
    filename: str = "n8n.pdf"
    text: str
    mode: str = "ladder"


@app.post("/documents/extract-text")
def extract_text(payload: TextIn) -> dict:
    try:
        return process_text(payload.text, payload.filename, payload.mode)
    except PermissionError as e:
        raise HTTPException(403, str(e))


class UrlIn(BaseModel):
    url: str
    mode: str = "ladder"


@app.post("/documents/extract-url")
def extract_url(payload: UrlIn) -> dict:
    if not payload.url.startswith(("http://", "https://")):
        raise HTTPException(400, "url http:// və ya https:// ilə başlamalıdır")
    try:
        r = PoliteSession().get(payload.url)
        r.raise_for_status()
    except RobotsDisallowed as e:
        raise HTTPException(403, str(e))
    except requests.RequestException as e:
        raise HTTPException(502, f"yüklənmədi: {e}")
    name = payload.url.rsplit("/", 1)[-1] or "document"
    try:
        return process_document(r.content, name, payload.mode)
    except (ValueError, PermissionError) as e:
        raise HTTPException(400, str(e))


@app.get("/documents")
def documents() -> dict:
    return {"documents": db.list_documents()}


# ------------------------------------------------------------------ hesabat və bildiriş
@app.post("/report/run")
def report_run(site: str = "demoshop", use_llm: bool = True) -> dict:
    return report.make_report(site, use_llm)


@app.get("/report/latest")
def report_latest() -> dict:
    return {"report": db.latest_report()}


class NotifyIn(BaseModel):
    text: str


@app.post("/notify")
def notify(payload: NotifyIn) -> dict:
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN", ""), os.environ.get("STAFF_CHAT_ID", "")
    if not token or not chat:
        print(f"[NOTIFY/log] {payload.text}", flush=True)
        return {"sent": False, "reason": "Telegram tokeni yoxdur, loga yazıldı"}
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat, "text": payload.text}, timeout=15)
    return {"sent": r.ok}


# ------------------------------------------------------------------ demo idarəsi
@app.post("/demo/advance")
def demo_advance(days: int = 1) -> dict:
    return requests.post(f"{DEMOSHOP}/admin/advance", params={"days": days}, timeout=10).json()


@app.post("/demo/glitch")
def demo_glitch(mode: str = "none") -> dict:
    r = requests.post(f"{DEMOSHOP}/admin/glitch", params={"mode": mode}, timeout=10)
    if not r.ok:
        raise HTTPException(400, r.text)
    return r.json()


@app.post("/demo/reset")
def demo_reset() -> dict:
    db.reset_all()
    return requests.post(f"{DEMOSHOP}/admin/reset", timeout=10).json()


@app.get("/demo/docs")
def demo_docs() -> dict:
    return requests.get(f"{DEMOSHOP}/docs", timeout=10).json()


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard() -> str:
    from app.dashboard import HTML
    return HTML
