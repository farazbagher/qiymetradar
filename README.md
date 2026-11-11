# QiymətRadar

A price-monitoring and invoice-reading agent that **does not trust its own LLM**.
It scrapes competitor prices, reads supplier invoices from PDFs and photos, and checks every value
with code before anything is accepted.

> Azərbaycanca: [README.az.md](README.az.md) · Full measurements and findings (in Azerbaijani): [FLOW.md](FLOW.md)

**Stack:** Python, FastAPI, PostgreSQL, BeautifulSoup, Selenium, pypdf, Tesseract OCR, Ollama (local LLM), Claude API, n8n, Docker.
**Tests:** 95, run against a separate test database.

## What it does

```
Competitor site ──► strategy: API → static HTML (requests + BeautifulSoup) → dynamic (Selenium)
                     │  robots.txt respected, crawl delay, timeouts, honest User-Agent
                     ▼
                Health check (if the layout changed, the database is NOT updated) ──► Postgres price history
                     ▼
                Diff engine (cheaper / pricier / new / removed / stock; >40% = "suspicious")
                     ──► Claude report (every number in it is checked) ──► notification

Invoice (PDF / scanned PDF / photo) ──► has text? pypdf : OCR (Tesseract, az + en)
                     ▼
                regex (free) ──► local model (Ollama) ──► [only if allowed] Claude ──► human review
                     └─ after each step: date, invoice number must appear verbatim in the text,
                        VAT must be 18/118 of the total, supplier must match the supplier list, OCR confidence
```

**Privacy:** invoices are read by the local model. They go to the cloud (Claude) only when `ALLOW_CLOUD_DOCS=1`,
and only after phone numbers, e-mails and IBANs are masked.

## Results

All numbers come from `backend/app/evals/results/*.json`. The competitor shop and the invoices are **synthetic**,
so the ground truth is known exactly; real-world performance will be lower.

**Scraping, 3 strategies vs. ground truth (6 simulated days):**

| Strategy | Days fully correct | Avg. time | Change detection |
|---|---|---|---|
| API (JSON) | 6/6 | 0.01 s | precision 1.0, recall 1.0 (58/58) |
| Static (BeautifulSoup) | 6/6 | 2.5 s | 1.0 / 1.0 |
| Selenium | 6/6 | 3.7 s | 1.0 / 1.0 |

When the site layout changes, the static scraper finds 0 products and the health check **blocks the database update**
instead of reporting every product as "removed".

**Invoice extraction.** The key metric is the **silent error**: the system says "ok" but a field is wrong.
That is worse than sending a document to a human.

| Set | Auto-correct | Sent to human | Silent errors |
|---|---|---|---|
| Tuning (templates A, B; 24 docs) | 100% | 0% | 0% |
| Held-out (unseen template C; 18 docs) | 61.1% | 38.9% | **0%** |
| Held-out 2 (template C, 18 new docs) | 66.7% | 33.3% | **0%** |

Everything sent to a human is a badly degraded photo, and the validator rejected all of them.
On PDFs and lightly degraded photos the local model matched Claude, so the cloud step is not needed.

## Bugs the evaluation caught

| Problem | Fix |
|---|---|
| OCR read the Latin `HF` in an invoice number as Cyrillic `НЕ`; the "appears in text" check passed it | Numbers containing Cyrillic or Greek letters are rejected |
| After a small prompt change the local model wrote `INV-2 026-906`; my check stripped spaces and accepted it, so silent errors jumped **from 0% to 29%** | The number must appear in the text **verbatim** |
| The local model copied the example date from the prompt instead of reading the document | Concrete date removed from the prompt (has a test) |
| Claude wrote "23 products in total" in a report (real: 24) | Every number in a report is checked against the statistics; one retry, then a template |

The second row is the main lesson of this project: **without re-running the eval, that regression would have been invisible.**

## Run it

```bash
cp .env.example .env                 # set POSTGRES_PASSWORD (and ANTHROPIC_API_KEY for reports)
docker compose up -d --build         # postgres, backend, demo shop, n8n
python3 scripts/build_workflows.py && python3 scripts/provision_n8n.py
ollama pull qwen3:4b                 # Ollama runs on the host
docker compose --profile selenium up -d selenium     # optional, for the dynamic page
```

| Service | URL |
|---|---|
| Dashboard | http://localhost:8005/dashboard |
| API docs | http://localhost:8005/docs |
| Demo competitor shop | http://localhost:8090 |
| n8n | http://localhost:5684 |

Tests and evals:

```bash
docker compose exec backend python -m pytest tests -q
docker compose exec backend python -m app.evals.scrape_eval
docker compose exec backend python -m app.evals.docs_eval --split heldout --label docs-heldout
```

Running the tests outside Docker needs Tesseract with the `aze` language pack and the DejaVu Sans font
(set `INVOICE_FONT=/path/to/DejaVuSans.ttf` if it is not at the Debian default path).

## Honest limitations

- The shop and invoices are synthetic and use 3 invoice templates. Treat the numbers as an upper bound.
- The only real-site config is `books.toscrape.com`, a site built for scraping practice. On a real competitor site,
  terms of service and robots.txt must be checked by hand.
- The n8n flow adds delays between requests but does not read robots.txt; the backend scraper does.
- The supplier list is a demo list, which makes vendor matching look better than it would on real data.
- Badly degraded photos are deliberately not auto-read; they go to a human.
