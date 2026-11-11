# QiymətRadar

> English: [README.md](README.md)

Rəqib qiymətlərini **scrape edən**, qaimə-fakturaları **PDF və şəkildən oxuyan** və nəticəni **yoxlayan** agent. Dərsin bütün texnologiyalarını
birləşdirir: BeautifulSoup, Selenium, API, pypdf, OCR, n8n scraping pipeline, LLM ilə strukturlaşdırma, etika qaydaları.

Əsas fikir: **LLM nəyisə çıxardıqda ona inanmırıq, kod yoxlayır.** Hər qəbul edilən dəyər sənədin mətnində həqiqətən olmalıdır,
ƏDV cəmin 18/118 hissəsi olmalıdır, scraping səhvi "qiymət dəyişikliyi" kimi görünməməlidir. Nəticələr və tapıntılar: **[FLOW.md](FLOW.md)**.

## Nə edir

```
Rəqib sayt ──► Strategiya: API → statik (requests + BeautifulSoup) → dinamik (Selenium)
                 │  robots.txt yoxlanır, sorğular arası fasilə, timeout, düzgün User-Agent
                 ▼
            Sağlamlıq yoxlaması (dizayn dəyişibsə baza yenilənmir) ──► Postgres (qiymət tarixçəsi)
                 ▼
            Fərq mühərriki (ucuzlaşdı/bahalaşdı/yeni/silindi/stok, 40%-dən çox = "şübhəli") ──► Claude hesabatı (rəqəmləri yoxlanır) ──► bildiriş

Qaimə (PDF / skan PDF / şəkil) ──► mətnli? pypdf : OCR (Tesseract, az+en)
                 ▼
            regex (pulsuz) ──► lokal model (Ollama) ──► [icazə varsa] Claude ──► insan baxışı
                 └─ hər pillədən sonra yoxlama: tarix, nömrə mətndə varmı, ƏDV 18/118, satıcı siyahıda varmı, OCR etibarı
```

**Məxfilik:** qaimələri yalnız lokal model oxuyur. Buluda (Claude) yalnız `ALLOW_CLOUD_DOCS=1` olanda və şəxsi məlumat (telefon, e-poçt, IBAN) maskalanandan sonra gedir.

## İşə salmaq

```bash
cp .env.example .env                 # POSTGRES_PASSWORD və ANTHROPIC_API_KEY doldur
docker compose up -d --build         # postgres, backend, demoshop (rəqib mağaza simulyatoru), n8n
python3 scripts/build_workflows.py && python3 scripts/provision_n8n.py
ollama pull qwen3:4b                 # Ollama host-da işləməlidir
# Dinamik səhifə (Selenium) üçün, ixtiyari:
docker compose --profile selenium up -d selenium     # .env-də SELENIUM_URL=http://selenium:4444/wd/hub
```

| Servis | Ünvan |
|---|---|
| **Dashboard** | http://localhost:8005/dashboard |
| API sənədi | http://localhost:8005/docs |
| Rəqib mağaza (demo) | http://localhost:8090 (`/`, `/dynamic`, `/api/products`, `/robots.txt`, `/docs`) |
| n8n | http://localhost:5684 (ilk dəfə owner hesabını özün yarat) |
| Postgres | localhost:5438 |

## Demo ssenarisi (5 dəqiqə)

1. Dashboard → **Scrape et**: 24 məhsul, baza yaranır.
2. **Rəqibdə 1 gün irəli** → yenidən **Scrape et**: qiymət dəyişiklikləri, sparklines. **Hesabat yarat**: Claude yazır, hər rəqəm yoxlanır.
3. Strategiyanı **api**, sonra **selenium** seç: eyni nəticə, fərqli sürət (0.01 san / 2.5 san / 3.7 san).
4. **robots.txt testi**: `/private/` qadağan olunub, scraper girmir (status `blocked`).
5. Qaimə: dropdown-dan mətnli PDF, skan PDF və şəkil sına. Skan şəklin OCR etibarı və yoxlamalar görünür.

Dizayn dəyişikliyini simulyasiya etmək (selector sınır, baza qorunur):
```bash
curl -X POST "localhost:8005/demo/glitch?mode=layout"   &&  curl -X POST localhost:8005/scrape/demoshop   # status: error
curl -X POST "localhost:8005/demo/glitch?mode=none"
```

## Test və eval

```bash
docker compose exec backend python -m pytest tests -q                                  # 95 test (ayrı test bazasında)
docker compose exec backend python -m app.evals.scrape_eval                            # 3 strategiya həqiqətlə müqayisə
docker compose exec backend python -m app.evals.docs_eval --split tuning --label docs-tuning
docker compose exec backend python -m app.evals.docs_eval --split heldout --label docs-heldout
docker compose exec backend python -m app.evals.docs_eval --split heldout --seed-offset 6 --label docs-heldout2
```

## n8n workflow-ları

| | |
|---|---|
| **QR1** Qiymət Monitoru | Schedule/Manual → səhifə siyahısı → HTTP Request (1 san fasilə) → HTML → Code → `/prices/ingest` → hesabat → IF → bildiriş (dərsin pipeline-ı) |
| **QR2** Qaimə Oxuyucu | HTTP Request (fayl) → Extract From File → mətn varsa strukturlaşdır, yoxsa OCR üçün yüklə |
| **QR3** Radar Söhbəti | AI Agent (Claude) + yaddaş + 4 alət (dəyişikliklər, məhsul tarixçəsi, sənədlər, hesabat) |
| **QR4** Xəta bildirişi | Error Trigger → `/notify` |

n8n flow-u sorğular arasında fasilə qoyur, amma **robots.txt-i oxumur**: robots yoxlaması backend scraper-indədir.

## Məhdudiyyətlər

- Rəqib mağaza və sənədlər **süni**dir (AI yazıb). Real saytlar və qaimələr daha müxtəlifdir, ölçmələr real performansın yuxarı həddinə yaxındır.
- Yalnız bir real sayt konfiqurasiyası var (`books.toscrape.com`, məşq saytı). Real rəqib saytda ToS və robots.txt əl ilə yoxlanmalıdır.
- Selenium yalnız `selenium/standalone-chromium` konteynerində sınanıb.
- Telegram tokeni yoxdur: `/notify` loga yazır.
- Satıcı siyahısı (`VENDOR_MASTER`) demo rejimindədir. Real layihədə şirkətin təchizatçı siyahısı olmalıdır.

## Təhlükəsizlik

Açarlar yalnız `.env`-də saxlanır, `.env` git-ə düşmür.
