"""Scraping eval-ı: 3 strategiya (static / api / selenium) rəqib mağazanın BİLİNƏN həqiqəti ilə müqayisə olunur.

Ölçülür:
1. Məhsul dəqiqliyi: hər gün hər strategiya mağazanın real vəziyyəti ilə (ad, qiymət, stok) tam üst-üstə düşürmü?
2. Dəyişiklik aşkarlanması: gündən-günə fərq mühərriki həqiqi dəyişiklikləri tapırmı (precision/recall, (məhsul, növ) cütləri)?
3. Dözümlülük: sayt dizaynı dəyişəndə (layout) və qiymət formatı dəyişəndə (price_format) hər strategiya nə edir?

İstifadə: python -m app.evals.scrape_eval   (demoshop və SELENIUM_URL lazımdır; Selenium yoxdursa həmin sütun atlanır)
"""

import json
import os
import time
from pathlib import Path

import requests

from app.ethics import PoliteSession
from app.prices import diff
from app.parsing import slugify
from app.scrapers.dynamic import DynamicScrapingUnavailable
from app.scrapers.sites import sites
from app.service import items_to_map, scrape_site

SHOP = os.environ.get("DEMOSHOP_URL", "http://demoshop:8090")
RESULTS = Path(__file__).parent / "results"
DAYS = 6


def truth_map() -> dict:
    st = requests.get(f"{SHOP}/admin/state", timeout=10).json()
    return {slugify(p["name"]): {"name": p["name"], "price": p["price"], "in_stock": p["in_stock"]} for p in st["products"]}


def scraped_map(strategy: str, cfg_id: str):
    cfg = sites()[cfg_id]
    t0 = time.perf_counter()
    try:
        res = scrape_site(cfg, strategy, PoliteSession())
    except DynamicScrapingUnavailable:
        return None, 0.0
    except Exception as e:
        return {"__error__": f"{type(e).__name__}"}, time.perf_counter() - t0
    return {s: {"name": v["name"], "price": v["price"], "in_stock": v["in_stock"]} for s, v in items_to_map(res.items).items()}, time.perf_counter() - t0


def same(a: dict, b: dict) -> bool:
    return a.keys() == b.keys() and all(abs(a[k]["price"] - b[k]["price"]) < 0.005 and a[k]["in_stock"] == b[k]["in_stock"] for k in a)


def change_pairs(prev: dict, cur: dict) -> set:
    return {(c.slug, c.kind) for c in diff(prev, cur, alert_pct=5.0).changes}


def main() -> None:
    strategies = {"static": "demoshop", "api": "demoshop", "selenium": "demoshop-dynamic"}
    requests.post(f"{SHOP}/admin/reset", timeout=10)
    out = {"days": DAYS, "strategies": {}, "robustness": {}}
    prev_truth, prev_scraped = None, {s: None for s in strategies}
    stats = {s: {"exact_days": 0, "days": 0, "seconds": 0.0, "tp": 0, "fp": 0, "fn": 0, "skipped": False} for s in strategies}
    for day in range(DAYS):
        if day:
            requests.post(f"{SHOP}/admin/advance", timeout=10)
        truth = truth_map()
        truth_changes = change_pairs(prev_truth, truth) if prev_truth else set()
        for s, cfg_id in strategies.items():
            got, secs = scraped_map(s, cfg_id)
            if got is None:
                stats[s]["skipped"] = True
                continue
            st = stats[s]
            st["days"] += 1
            st["seconds"] += secs
            st["exact_days"] += int("__error__" not in got and same(got, truth))
            if prev_scraped[s] is not None and "__error__" not in got:
                found = change_pairs(prev_scraped[s], got)
                st["tp"] += len(found & truth_changes)
                st["fp"] += len(found - truth_changes)
                st["fn"] += len(truth_changes - found)
            prev_scraped[s] = got if "__error__" not in got else prev_scraped[s]
        prev_truth = truth
    for s, st in stats.items():
        if st["skipped"] and st["days"] == 0:
            out["strategies"][s] = {"skipped": "SELENIUM_URL yoxdur"}
            continue
        tp, fp, fn = st["tp"], st["fp"], st["fn"]
        out["strategies"][s] = {"exact_days": f"{st['exact_days']}/{st['days']}", "avg_seconds": round(st["seconds"] / max(1, st["days"]), 2),
                                "change_precision": round(tp / (tp + fp), 3) if tp + fp else None,
                                "change_recall": round(tp / (tp + fn), 3) if tp + fn else None, "tp_fp_fn": [tp, fp, fn]}
    # dözümlülük
    for mode in ("layout", "price_format"):
        requests.post(f"{SHOP}/admin/glitch", params={"mode": mode}, timeout=10)
        truth = truth_map()
        row = {}
        for s, cfg_id in strategies.items():
            got, _ = scraped_map(s, cfg_id)
            if got is None:
                row[s] = "atlandı"
            elif "__error__" in got:
                row[s] = f"xəta ({got['__error__']})"
            else:
                row[s] = f"{len(got)} məhsul, düzgün={same(got, truth)}"
        out["robustness"][mode] = row
    requests.post(f"{SHOP}/admin/glitch", params={"mode": "none"}, timeout=10)
    requests.post(f"{SHOP}/admin/reset", timeout=10)
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "scrape-eval.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
