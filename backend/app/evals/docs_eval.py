"""Sənəd ekstraksiyası eval-ı: 5 konfiq, 2 dəst, 3 kanal.

Dəstlər:
  tuning  : şablon A, B (regex və prompt bu şablonlara və onların OCR səhvlərinə baxılaraq yazılıb). Kanallar: mətnli PDF, yüngül pis foto (OCR)
  heldout : şablon C (başqa söz ehtiyatı və rəqəm formatı). Kanallar: mətnli PDF, yüngül pis foto, çox pis foto. Tuninqdə görülməyib.
Konfiqlər: regex | local | claude | ladder (regex -> lokal -> insan) | ladder-cloud (regex -> lokal -> Claude -> insan)

Əsas ölçü "səssiz səhv" dərəcəsidir: sistem "ok" deyib, amma sahə yanlışdır. Bu, avtomatik qəbul olunan səhv məlumatdır
və "needs_review"-dan (insana göndərmək) çox təhlükəlidir.

Qeyd: sənədlər süni və etiketlər generatordandır (həqiqət məlum). Real qaimələr daha müxtəlifdir. Satıcı adı diakritiklərə
həssas olmadan müqayisə olunur (OCR 'Ş' hərfini 'S' oxuyur; real sistemdə satıcı siyahı ilə uyğunlaşdırılır).

İstifadə: python -m app.evals.docs_eval --split tuning --modes regex,local,claude,ladder,ladder-cloud --label docs-tuning
"""

import argparse
import hashlib
import json
import time
from collections import Counter
from pathlib import Path

from app.docs import invoicegen as ig
from app.docs.extract import Deps, InvoiceData, default_deps, extract
from app.docs.reader import read_document
from app.parsing import slugify

RESULTS = Path(__file__).parent / "results"
SEEDS = range(1, 7)
FIELDS = ["invoice_no", "date", "vendor", "total", "vat"]


def build_docs(split: str, seed_offset: int = 0) -> list:
    docs = []
    spec = ([("A", ch) for ch in ("pdf", "noisy")] + [("B", ch) for ch in ("pdf", "noisy")] if split == "tuning"
            else [("C", ch) for ch in ("pdf", "noisy", "hard")])
    for tpl, ch in spec:
        for seed in (s + seed_offset for s in SEEDS):
            inv = ig.make_invoice(seed, tpl)
            lines = ig.render_lines(inv, tpl)
            if ch == "pdf":
                data, name = ig.to_pdf_bytes(lines), f"{tpl}{seed}-pdf.pdf"
            else:
                data, name = ig.image_to_bytes(ig.degrade(ig.to_image(lines), ch), "JPEG"), f"{tpl}{seed}-{ch}.jpg"
            doc = read_document(data, name)
            docs.append({"id": f"{tpl}{seed}-{ch}", "template": tpl, "channel": ch, "truth": inv.fields(), "text": doc.text,
                         "ocr_conf": doc.meta.get("ocr_conf")})
    return docs


def field_ok(name: str, pred: dict, truth: dict) -> bool:
    p, t = pred.get(name), truth[name]
    if p is None:
        return False
    if name in ("total", "vat"):
        return isinstance(p, (int, float)) and abs(p - t) <= 0.005
    if name == "vendor":
        return slugify(str(p)) == slugify(t)
    return str(p).strip() == str(t).strip()


class Cached:
    """Eyni mətn üçün model bir dəfə çağırılır: konfiqlər arasında ədalətli müqayisə və vaxta qənaət."""

    def __init__(self, runnable, store: dict, key: str):
        self.r, self.store, self.key = runnable, store, key

    def invoke(self, msgs):
        k = (self.key, hashlib.md5(msgs[-1].content.encode()).hexdigest())
        if k not in self.store:
            t0 = time.perf_counter()
            try:
                out = self.r.invoke(msgs)
            except Exception:
                out = None
            self.store[k] = (out, time.perf_counter() - t0)
        return self.store[k][0]


def evaluate(split: str, modes: list, only: int | None = None, seed_offset: int = 0) -> dict:
    docs = build_docs(split, seed_offset)[:only]
    base = default_deps()
    store: dict = {}
    deps = Deps(local=lambda: Cached(base.local(), store, "local"), claude=lambda: Cached(base.claude(), store, "claude"))
    out = {"split": split, "n": len(docs), "modes": {}}
    for mode in modes:
        rows, t_mode = [], time.perf_counter()
        for d in docs:
            allow = mode in ("claude", "ladder-cloud")
            r = extract(d["text"], mode=mode, allow_cloud=allow, deps=deps, ocr_conf=d["ocr_conf"])
            correct = {f: field_ok(f, r.data, d["truth"]) for f in FIELDS}
            exact = all(correct.values())
            rows.append({"id": d["id"], "template": d["template"], "channel": d["channel"], "status": r.status, "extractor": r.extractor,
                         "exact": exact, "fields": correct, "issues": r.issues, "calls": r.calls, "ocr_conf": d["ocr_conf"],
                         "pred": r.data, "truth": d["truth"]})
        n = len(rows)
        ok = [x for x in rows if x["status"] == "ok"]
        silent = [x for x in ok if not x["exact"]]
        auto = [x for x in ok if x["exact"]]
        calls = Counter()
        for x in rows:
            calls.update(x["calls"])
        by = {}
        for key in ("template", "channel"):
            for v in sorted({x[key] for x in rows}):
                sub = [x for x in rows if x[key] == v]
                by[f"{key}={v}"] = {"auto_correct": sum(1 for x in sub if x["status"] == "ok" and x["exact"]),
                                    "silent_error": sum(1 for x in sub if x["status"] == "ok" and not x["exact"]), "n": len(sub)}
        out["modes"][mode] = {
            "n": n,
            "auto_correct": len(auto), "auto_correct_pct": round(100 * len(auto) / n, 1),
            "needs_review": n - len(ok), "needs_review_pct": round(100 * (n - len(ok)) / n, 1),
            "silent_errors": len(silent), "silent_error_pct": round(100 * len(silent) / n, 1),
            "exact_any_status_pct": round(100 * sum(x["exact"] for x in rows) / n, 1),
            "field_accuracy": {f: round(100 * sum(x["fields"][f] for x in rows) / n, 1) for f in FIELDS},
            "calls": dict(calls), "by": by, "rows": rows,
        }
    out["llm_seconds"] = {k: round(sum(v[1] for kk, v in store.items() if kk[0] == k), 1) for k in ("local", "claude")}
    out["llm_calls_unique"] = {k: sum(1 for kk in store if kk[0] == k) for k in ("local", "claude")}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="tuning", choices=["tuning", "heldout"])
    ap.add_argument("--modes", default="regex,local,claude,ladder,ladder-cloud")
    ap.add_argument("--label", default=None)
    ap.add_argument("--only", type=int, default=None, help="yalnız ilk N sənəd (sürətli sınaq)")
    ap.add_argument("--seed-offset", type=int, default=0, help="yeni sənədlər üçün (məs. 6: seed 7-12), heldout2 üçün")
    a = ap.parse_args()
    label = a.label or f"docs-{a.split}"
    t0 = time.perf_counter()
    res = evaluate(a.split, a.modes.split(","), a.only, a.seed_offset)
    res["label"], res["seconds"] = label, round(time.perf_counter() - t0, 1)
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"{label}.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n== {label}: {res['n']} sənəd, {res['seconds']} san, LLM çağırışları {res['llm_calls_unique']}, LLM vaxtı {res['llm_seconds']}")
    print(f"{'konfiq':14} {'avto-düzgün':>12} {'insana':>8} {'səssiz səhv':>12} {'hər halda düzgün':>17}   sahələr (nömrə/tarix/satıcı/cəmi/ƏDV)")
    for m, s in res["modes"].items():
        fa = s["field_accuracy"]
        print(f"{m:14} {s['auto_correct_pct']:>11}% {s['needs_review_pct']:>7}% {s['silent_error_pct']:>11}% {s['exact_any_status_pct']:>16}%   "
              f"{fa['invoice_no']}/{fa['date']}/{fa['vendor']}/{fa['total']}/{fa['vat']}")


if __name__ == "__main__":
    main()
