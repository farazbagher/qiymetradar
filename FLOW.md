# QiymətRadar: ölçmələr və tapıntılar

Bütün rəqəmlər `backend/app/evals/results/*.json` fayllarındandır. Rəqib mağaza və sənədlər **süni**dir (AI yazıb), həqiqət məlumatı generatordan gəlir.

## 1. Scraping: 3 strategiya həqiqətlə müqayisə (6 gün, `scrape_eval.py`)

| Strategiya | Gün üzrə tam düzgün | Orta sürət | Dəyişiklik aşkarlanması |
|---|---|---|---|
| API (JSON) | 6/6 | **0.01 san** | precision 1.0, recall 1.0 (58/58) |
| Statik (BeautifulSoup) | 6/6 | 2.5 san (3 səhifə, 1 san Crawl-delay) | 1.0 / 1.0 |
| Selenium (dinamik) | 6/6 | 3.7 san | 1.0 / 1.0 |

**Dözümlülük** (sayt dizaynı dəyişəndə): statik **0 məhsul** tapır (sağlamlıq qoruması baza yenilənməsini bloklayır), Selenium `TimeoutException` verir, **API dayanıqlıdır** (25/25).
Qiymət formatı dəyişəndə (`1 450,00 ₼`) hər üç strategiya düzgündür. Nəticə: dərsin qaydası doğrudur, **API həmişə ilk seçimdir**.

## 2. Qaimə ekstraksiyası (`docs_eval.py`)

Dəstlər: **tuninq** (şablon A, B; 24 sənəd), **held-out** (şablon C: başqa söz və rəqəm formatı; 18), **heldout2** (C şablonu, 18 yeni sənəd).
Kanallar: mətnli PDF, yüngül pis foto (OCR), çox pis foto ("hard", OCR etibarı ~55). Konfiqlər: `regex` | `local` | `claude` | `ladder` (regex → lokal → insan) | `ladder-cloud` (+ Claude).
Əsas ölçü **səssiz səhv**: sistem "ok" deyib, amma sahə yanlışdır. Bu, insana göndərməkdən (needs_review) çox təhlükəlidir.

| Dəst | Konfiq | Avto-düzgün | İnsana | **Səssiz səhv** |
|---|---|---|---|---|
| tuninq | regex | 100% | 0% | 0% |
| tuninq | lokal | 91.7% | 8.3% | 0% |
| tuninq | claude / ladder / ladder-cloud | 100% | 0% | 0% |
| held-out (C) | regex | **0%** | 100% | 0% |
| held-out (C) | lokal / claude / ladder / ladder-cloud | 61.1% | 38.9% | **0%** |
| heldout2 (C, yeni) | lokal / claude / ladder / ladder-cloud | 66.7% | 33.3% | **0%** |

Oxunur belə:
- **Regex tanımadığı şablonu 0% avto verir, amma 0 səssiz səhv**: uğursuzluq "bağlıdır" (hamısı insana gedir).
- **PDF və yüngül foto kanalında lokal model Claude qədər yaxşıdır** (held-out PDF 6/6). Buluda ehtiyac yoxdur: `ladder` = `ladder-cloud`. Məxfilik və xərc qənaəti.
- İnsana gedən 33-39% **yalnız "hard" şəkillərdir** (OCR zibil), yoxlayıcı onların hamısını düzgün rədd edib. Bunlar üçün həll daha yaxşı skan və ya insan baxışıdır, model deyil.

### Eval-ın tapdığı problemlər (hər biri düzəldilib və testi var)

| # | Problem | Necə tapıldı | Düzəliş |
|---|---|---|---|
| 1 | Regex `Yekun (ƏDV-siz)` sətrini ƏDV sayırdı | Yoxlayıcı tutdu (ƏDV 18/118 qaydası), sənəd lokal modelə keçdi | Regex "ƏDV-siz" sətrini keçir |
| 2 | OCR-ın `Nova Tech MMC \| \|` satıcısı "ok" qəbul olunurdu | Dashboard-da gördüm | Sondakı səs-küy təmizlənir, `\|` simvolu yoxlamada rədd |
| 3 | OCR `HF`-i **Kiril `НЕ`** oxudu, "mətndə var" yoxlaması keçdi | Held-out: **səssiz səhv** (lokal 11%, claude 5.6%) | Nömrədə Kiril/Yunan hərf = rədd |
| 4 | OCR `Dijital` → `Dilital` satıcı adı | tuninq: səssiz səhv | Təchizatçı siyahısı ilə uyğunlaşdırma (yaxın ad düzəldilir, uzaq ad insana) |
| 5 | Lokal model prompt-dakı **nümunə tarixi** təkrar etdi (sənəddəki tarixi oxumayıb) | Dashboard-da canlı gördüm, yoxlayıcı tutdu | Prompt-dan konkret tarix çıxarıldı (testi var) |
| 6 | Prompt dəyişəndən sonra lokal model `INV-2 026-906` (boşluqlu) yazdı, yoxlamam boşluqları atıb qəbul etdi: **29% səssiz səhv** | Yenidən eval | Nömrə mətndə **eynilə** olmalıdır + mətndəki formaya təmir |

6-cı tapıntı ən vacibidir: **eval-sız bu görünməzdi**. Prompt-da kiçik dəyişiklik səssiz səhvi 0%-dən 29%-ə qaldırdı və yalnız yenidən ölçmə tutdu.

## 3. Hesabat və halüsinasiya qoruması

Claude hesabatda `"Cəmi 23 məhsul"` uydurdu (real 24; özü toplamışdı). Hər rəqəm statistika ilə **ədədi** yoxlanır, uyğun gəlmirsə bir dəfə düzəliş cəhdi, olmasa şablon.
Yoxlama özü 3 dəfə səhv rədd edirdi: `980` vs `980.0` (sətir müqayisəsi), nömrələnmiş siyahı "1." ədəd sayılırdı, "7 dəyişib" (3+4) statistikada hazır yox idi. İndi 5/5 hesabat Claude tərəfindən yazılır və yoxlanılır.

## 4. n8n
QR1 (qiymət pipeline-ı, 3 səhifə, 1 san fasilə) 24 məhsulu yazdı, fərq tapdı, hesabat və bildiriş verdi. QR2 hər iki budağı keçdi: mətnli PDF → Extract From File → regex; skan PDF → OCR.
QR3 söhbət agenti dəyişiklikləri, məhsul tarixçəsini və sənədləri alətlərdən düzgün oxudu. **Məhdudiyyət:** n8n flow-u robots.txt-i oxumur (backend scraper-i oxuyur).

## 5. Dürüst məhdudiyyətlər
- Sənədlər süni və 3 şablondur. Real qaimələr daha müxtəlifdir, bu rəqəmlər yuxarı hədd kimi oxunmalıdır.
- Regex tuninq dəstində 100%-dir, çünki həmin şablonlara və OCR səhvlərinə baxılaraq yazılıb. Held-out-da sıfırdır.
- 3-5-ci düzəlişlər held-out-da tapılıb, ona görə held-out artıq "təmiz" deyil. Bunu `heldout2` (yeni sənədlər, eyni şablon) yoxlayır, **yeni şablon deyil**.
- Təchizatçı siyahısı demo rejimindədir və vendor dəqiqliyini süni olaraq yüksəldir. Real layihədə şirkətin real siyahısı olmalıdır.
- "hard" şəkillər üçün avtomatik oxuma yoxdur: bu, qəsdən qəbul edilən nəticədir (insan baxışı).
- Selenium yalnız `selenium/standalone-chromium` ilə sınanıb. Real rəqib sayt ToS/robots.txt əl ilə yoxlanmalıdır.
