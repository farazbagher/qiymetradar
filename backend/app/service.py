"""Scraping xidməti: scrape -> sağlamlıq yoxlaması -> saxla -> əvvəlki run ilə fərq."""

import time

import requests

from app import db
from app.ethics import PoliteSession, RobotsDisallowed
from app.parsing import detect_currency, parse_price, slugify
from app.prices import DEFAULT_ALERT_PCT, diff, run_health
from app.scrapers.api import scrape_api
from app.scrapers.base import Item, ScrapeResult, SiteConfig
from app.scrapers.dynamic import DynamicScrapingUnavailable, scrape_selenium
from app.scrapers.sites import sites
import os


def alert_pct() -> float:
    return float(os.environ.get("ALERT_PCT", DEFAULT_ALERT_PCT))


def items_to_map(items: list) -> dict:
    out = {}
    for it in items:
        slug = slugify(it.name)
        if slug and slug not in out:                          # təkrar kart olarsa ilk götürülür
            out[slug] = it.as_dict()
    return out


def scrape_site(cfg: SiteConfig, strategy: str, session) -> ScrapeResult:
    if strategy == "api":
        return scrape_api(cfg, session)
    if strategy == "selenium":
        return scrape_selenium(cfg)
    from app.scrapers.static import scrape_static
    return scrape_static(cfg, session)


def persist_run(site: str, strategy: str, result: ScrapeResult, seconds: float) -> dict:
    """Sağlamlıq yoxlaması: kəskin azalma / sıfır = dizayn dəyişib, baza yenilənmir (G2)."""
    current = items_to_map(result.items)
    prev_runs = db.last_ok_runs(site, 1)
    prev = db.snapshot_map(prev_runs[0]["id"]) if prev_runs else None
    problem = run_health(len(prev) if prev else 0, len(current), result.warnings)
    if problem:
        run_id = db.create_run(site, strategy, "error", len(current), problem, seconds)
        return {"run_id": run_id, "status": "error", "error": problem, "items": len(current), "warnings": result.warnings[:5]}
    run_id = db.create_run(site, strategy, "ok", len(current), "", seconds)
    db.save_snapshots(run_id, site, current)
    d = diff(prev, current, alert_pct())
    return {"run_id": run_id, "status": "ok", "items": len(current), "strategy": strategy, "pages": result.pages,
            "warnings": result.warnings[:5], "stats": d.stats(), "changes": [c.as_dict() for c in d.changes]}


def run_scrape(cfg_id: str, strategy: str | None = None, session=None) -> dict:
    cfgs = sites()
    if cfg_id not in cfgs:
        raise KeyError(cfg_id)
    cfg = cfgs[cfg_id]
    strategy = strategy or cfg.strategy
    session = session or PoliteSession()
    t0 = time.perf_counter()
    try:
        result = scrape_site(cfg, strategy, session)
    except RobotsDisallowed as e:
        run_id = db.create_run(cfg.site, strategy, "blocked", 0, str(e), time.perf_counter() - t0)
        return {"run_id": run_id, "status": "blocked", "error": str(e), "items": 0}
    except DynamicScrapingUnavailable as e:
        run_id = db.create_run(cfg.site, strategy, "error", 0, str(e), time.perf_counter() - t0)
        return {"run_id": run_id, "status": "error", "error": str(e), "items": 0}
    except (requests.RequestException, Exception) as e:
        run_id = db.create_run(cfg.site, strategy, "error", 0, f"{type(e).__name__}: {e}"[:300], time.perf_counter() - t0)
        return {"run_id": run_id, "status": "error", "error": f"{type(e).__name__}: {e}"[:300], "items": 0}
    return persist_run(cfg.site, strategy, result, time.perf_counter() - t0)


def ingest_raw(site: str, rows: list, strategy: str = "n8n") -> dict:
    """n8n-dən gələn xam sətirlər: [{"title": "...", "price": "749.00 AZN", "stock": "Stokdadır"}].
    Qiymətin ədədə çevrilməsi BURADA edilir (tək həqiqət mənbəyi): n8n Code node-u yalnız massivləri birləşdirir."""
    warnings, items = [], []
    for r in rows:
        name = (r.get("title") or r.get("name") or "").strip()
        raw = str(r.get("price", ""))
        try:
            items.append(Item(name=name, price=parse_price(raw), currency=detect_currency(raw, "AZN"),
                              in_stock="yoxdur" not in str(r.get("stock", "")).lower()))
        except ValueError as e:
            warnings.append(f"{name or '?'}: {e}")
    return persist_run(site, strategy, ScrapeResult(items=items, warnings=warnings, pages=1, strategy=strategy), 0.0)


def latest_changes(site: str) -> dict:
    runs = db.last_ok_runs(site, 2)
    if not runs:
        return {"site": site, "runs": 0, "changes": [], "stats": {}}
    cur = db.snapshot_map(runs[0]["id"])
    prev = db.snapshot_map(runs[1]["id"]) if len(runs) > 1 else None
    d = diff(prev, cur, alert_pct())
    return {"site": site, "runs": len(runs), "run_id": runs[0]["id"], "stats": d.stats(), "changes": [c.as_dict() for c in d.changes]}
