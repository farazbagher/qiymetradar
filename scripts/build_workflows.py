#!/usr/bin/env python3
"""n8n workflow-ları (generatordan, python3.9+). İstifadə: python3 scripts/build_workflows.py

QR1  Qiymət monitoru: dərsin pipeline-ı  Schedule/Manual -> səhifə siyahısı -> HTTP Request -> HTML -> Code -> backend (ingest) -> hesabat -> IF -> bildiriş
QR2  Qaimə oxuyucu:   HTTP Request (fayl) -> Extract From File (PDF) -> IF mətn var? -> [ekstraksiya | skan: OCR üçün backend-ə yüklə]
QR3  Radar söhbəti:   Chat Trigger -> AI Agent (+ yaddaş, 4 alət)
QR4  Xəta bildirişi:  Error Trigger -> /notify

Etik qeyd: n8n flow-u sorğular arasında 1 san fasilə qoyur (batching), amma robots.txt-i OXUMUR. robots.txt yoxlaması
backend scraper-indədir (POST /scrape/...). Real saytda n8n flow-undan əvvəl robots.txt əl ilə yoxlanmalıdır.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "n8n" / "workflows"
CRED = {"anthropic": {"anthropicApi": {"id": "qrAnthropic00001", "name": "Anthropic account"}}}
BACKEND = "={{ $env.BACKEND_URL }}"
ERROR_WF = "QrErrorNotify"


def node(i, name, type_, ver, params, pos, **extra):
    return {"parameters": params, "id": f"qr000000-0000-4000-8000-{i:012d}", "name": name,
            "type": type_, "typeVersion": ver, "position": list(pos), **extra}


def conns(*edges):
    """edge = (mənbə, hədəf, tip, çıxış_indeksi)"""
    out = {}
    for src, dst, ctype, idx in edges:
        slots = out.setdefault(src, {}).setdefault(ctype, [])
        while len(slots) <= idx:
            slots.append([])
        slots[idx].append({"node": dst, "type": ctype, "index": 0})
    return out


def workflow(wid, name, nodes, connections, error_wf=True):
    settings = {"executionOrder": "v1"}
    if error_wf:
        settings["errorWorkflow"] = ERROR_WF
    return {"id": wid, "name": name, "nodes": nodes, "connections": connections, "active": False, "settings": settings}


def http(i, name, method, url, pos, body=None, timeout=60000, **extra):
    params = {"method": method, "url": url, "options": {"timeout": timeout}}
    if body is not None:
        params.update({"sendBody": True, "specifyBody": "json", "jsonBody": body})
    return node(i, name, "n8n-nodes-base.httpRequest", 4.2, params, pos, retryOnFail=True, maxTries=2, waitBetweenTries=2000, **extra)


# ------------------------------------------------------------------ QR1
PAGES_JS = """// 3 səhifə (hər birində 8 məhsul). Real layihədə bu siyahı sayt konfiqurasiyasından gəlir.
const base = $env.DEMOSHOP_URL;
return [1, 2, 3].map(p => ({ json: { page: p, url: `${base}/?page=${p}` } }));"""

MERGE_JS = """// HTML node hər səhifə üçün 3 massiv qaytarır (Return Array). Hamısını bir siyahıya yığırıq.
// Qiymətin ədədə çevrilməsi BURADA edilmir: xam mətni backend parse edir (tək həqiqət mənbəyi: £, ₼, '1 450,00' formatları).
const rows = [];
for (const item of $input.all()) {
  const { title = [], price = [], stock = [] } = item.json;
  for (let i = 0; i < title.length; i++) rows.push({ title: title[i], price: price[i], stock: stock[i] || '' });
}
return [{ json: { site: 'demoshop', strategy: 'n8n', rows } }];"""


def flow_price() -> dict:
    nodes = [
        node(1, "Schedule Trigger", "n8n-nodes-base.scheduleTrigger", 1.2,
             {"rule": {"interval": [{"field": "days", "daysInterval": 1, "triggerAtHour": 9}]}}, (-1100, -100)),
        node(2, "Manual Trigger", "n8n-nodes-base.manualTrigger", 1, {}, (-1100, 100)),
        node(3, "Səhifə siyahısı", "n8n-nodes-base.code", 2, {"mode": "runOnceForAllItems", "language": "javaScript", "jsCode": PAGES_JS}, (-860, 0)),
        node(4, "HTTP Request", "n8n-nodes-base.httpRequest", 4.2,
             {"method": "GET", "url": "={{ $json.url }}", "options": {
                 "timeout": 15000, "batching": {"batch": {"batchSize": 1, "batchInterval": 1000}},     # sorğular arası 1 san (etika)
                 "response": {"response": {"responseFormat": "text", "outputPropertyName": "data"}},
                 }, "sendHeaders": True,
              "headerParameters": {"parameters": [{"name": "User-Agent", "value": "QiymetRadarBot/1.0 (n8n)"}]}},
             (-620, 0), retryOnFail=True, maxTries=2, waitBetweenTries=2000),
        node(5, "HTML", "n8n-nodes-base.html", 1.2,
             {"operation": "extractHtmlContent", "sourceData": "json", "dataPropertyName": "data",
              "extractionValues": {"values": [
                  {"key": "title", "cssSelector": "article.product h3 a", "returnValue": "attribute", "attribute": "title", "returnArray": True},
                  {"key": "price", "cssSelector": "article.product p.price", "returnValue": "text", "returnArray": True},
                  {"key": "stock", "cssSelector": "article.product span.stock", "returnValue": "text", "returnArray": True}]},
              "options": {}}, (-380, 0)),
        node(6, "Code - Birləşdir", "n8n-nodes-base.code", 2, {"mode": "runOnceForAllItems", "language": "javaScript", "jsCode": MERGE_JS}, (-140, 0)),
        http(7, "Backend - Qiymətləri yaz", "POST", BACKEND + "/prices/ingest", (100, 0), body="={{ JSON.stringify($json) }}"),
        http(8, "Backend - Hesabat", "POST", BACKEND + "/report/run?site=demoshop", (340, 0), timeout=120000),
        node(9, "IF - dəyişiklik var?", "n8n-nodes-base.if", 2.2,
             {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                             "conditions": [{"id": "c1", "leftValue": "={{ $('Backend - Qiymətləri yaz').first().json.stats.changes }}",
                                             "rightValue": 0, "operator": {"type": "number", "operation": "gt"}}], "combinator": "and"}, "options": {}},
             (580, 0)),
        http(10, "Bildiriş - Telegram", "POST", BACKEND + "/notify", (820, -80),
             body="={{ JSON.stringify({ text: 'QiymətRadar: ' + $json.text }) }}"),
    ]
    c = conns(("Schedule Trigger", "Səhifə siyahısı", "main", 0), ("Manual Trigger", "Səhifə siyahısı", "main", 0),
              ("Səhifə siyahısı", "HTTP Request", "main", 0), ("HTTP Request", "HTML", "main", 0), ("HTML", "Code - Birləşdir", "main", 0),
              ("Code - Birləşdir", "Backend - Qiymətləri yaz", "main", 0), ("Backend - Qiymətləri yaz", "Backend - Hesabat", "main", 0),
              ("Backend - Hesabat", "IF - dəyişiklik var?", "main", 0), ("IF - dəyişiklik var?", "Bildiriş - Telegram", "main", 0))
    return workflow("QrPriceMonitor", "QR1 - Qiymət Monitoru (scraping pipeline)", nodes, c)


# ------------------------------------------------------------------ QR2
DOCS_JS = """// Demo: biri mətnli PDF, biri skan PDF. Real layihədə bura e-poçt qoşması və ya qovluq node-u gəlir.
const base = $env.DEMOSHOP_URL;
return [
  { json: { url: `${base}/docs/inv-001.pdf`, name: 'inv-001.pdf' } },
  { json: { url: `${base}/docs/scan/inv-003.pdf`, name: 'inv-003-skan.pdf' } },
];"""

TEXT_PAYLOAD_JS = """// Extract From File PDF-dən mətni çıxarıb: backend yalnız strukturlaşdırır və yoxlayır.
const j = $input.first().json;
return [{ json: { filename: $('Sənəd siyahısı').item.json.name, text: j.text, mode: 'ladder' } }];"""


def flow_docs() -> dict:
    nodes = [
        node(1, "Manual Trigger", "n8n-nodes-base.manualTrigger", 1, {}, (-1000, 0)),
        node(2, "Sənəd siyahısı", "n8n-nodes-base.code", 2, {"mode": "runOnceForAllItems", "language": "javaScript", "jsCode": DOCS_JS}, (-780, 0)),
        node(3, "HTTP Request - Faylı yüklə", "n8n-nodes-base.httpRequest", 4.2,
             {"method": "GET", "url": "={{ $json.url }}", "options": {"timeout": 30000, "response": {"response": {"responseFormat": "file", "outputPropertyName": "data"}}}},
             (-540, 0)),
        node(4, "Extract From File", "n8n-nodes-base.extractFromFile", 1.1,
             {"operation": "pdf", "binaryPropertyName": "data", "options": {"keepSource": "both"}}, (-300, 0)),
        node(5, "IF - mətn qatı var?", "n8n-nodes-base.if", 2.2,
             {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                             "conditions": [{"id": "c1", "leftValue": "={{ ($json.text || '').trim().length }}", "rightValue": 20,
                                             "operator": {"type": "number", "operation": "gte"}}], "combinator": "and"}, "options": {}}, (-60, 0)),
        node(6, "Code - Mətn yükü", "n8n-nodes-base.code", 2, {"mode": "runOnceForAllItems", "language": "javaScript", "jsCode": TEXT_PAYLOAD_JS}, (180, -120)),
        http(7, "Backend - Mətni strukturlaşdır", "POST", BACKEND + "/documents/extract-text", (420, -120), body="={{ JSON.stringify($json) }}", timeout=180000),
        node(8, "Backend - Skan: OCR", "n8n-nodes-base.httpRequest", 4.2,
             {"method": "POST", "url": BACKEND + "/documents/extract", "sendBody": True, "contentType": "multipart-form-data",
              "bodyParameters": {"parameters": [{"parameterType": "formBinaryData", "name": "file", "inputDataFieldName": "data"},
                                                {"name": "mode", "value": "ladder"}]},
              "options": {"timeout": 180000}}, (180, 140), retryOnFail=True, maxTries=2, waitBetweenTries=2000),
        node(9, "Code - Nəticə", "n8n-nodes-base.code", 2,
             {"mode": "runOnceForEachItem", "language": "javaScript",
              "jsCode": "const d = $json;\nreturn { json: { fayl: d.filename, uslub: d.method + ' / ' + d.extractor, status: d.status, nomre: d.data.invoice_no, tarix: d.data.date, satici: d.data.vendor, cemi: d.data.total, problemler: d.issues } };"},
             (680, 0)),
    ]
    c = conns(("Manual Trigger", "Sənəd siyahısı", "main", 0), ("Sənəd siyahısı", "HTTP Request - Faylı yüklə", "main", 0),
              ("HTTP Request - Faylı yüklə", "Extract From File", "main", 0), ("Extract From File", "IF - mətn qatı var?", "main", 0),
              ("IF - mətn qatı var?", "Code - Mətn yükü", "main", 0), ("IF - mətn qatı var?", "Backend - Skan: OCR", "main", 1),
              ("Code - Mətn yükü", "Backend - Mətni strukturlaşdır", "main", 0),
              ("Backend - Mətni strukturlaşdır", "Code - Nəticə", "main", 0), ("Backend - Skan: OCR", "Code - Nəticə", "main", 0))
    return workflow("QrInvoiceReader", "QR2 - Qaimə Oxuyucu (PDF + OCR)", nodes, c)


# ------------------------------------------------------------------ QR3
RETRY_JS = """const call = async (opts) => {
  let lastErr;
  for (let i = 1; i <= 3; i++) {
    try { return await this.helpers.httpRequest({ json: true, timeout: 120000, ...opts }); }
    catch (e) { lastErr = e; if (i < 3) await new Promise((r) => setTimeout(r, 800 * i)); }
  }
  throw lastErr;
};
const fail = () => JSON.stringify({ error: true, message: 'Backend hazırda cavab vermir. Bir azdan yenidən cəhd edin.' });
"""


def tool(i, name, description, schema, code, pos):
    return node(i, name, "@n8n/n8n-nodes-langchain.toolCode", 1.3,
                {"name": name, "description": description, "language": "javaScript", "jsCode": code,
                 "specifyInputSchema": True, "schemaType": "manual", "inputSchema": json.dumps(schema)}, pos)


def flow_chat() -> dict:
    changes = RETRY_JS + """try { return JSON.stringify(await call({ url: 'http://backend:8000/changes?site=demoshop' })); } catch (e) { return fail(); }"""
    history = RETRY_JS + """try { return JSON.stringify(await call({ url: `http://backend:8000/products/search?q=${encodeURIComponent(query.mehsul)}` })); } catch (e) { return fail(); }"""
    docs = RETRY_JS + """try { const r = await call({ url: 'http://backend:8000/documents' }); return JSON.stringify(r.documents.slice(0, 10).map(d => ({ id: d.id, fayl: d.filename, status: d.status, mellumat: d.data, problemler: d.issues }))); } catch (e) { return fail(); }"""
    report = RETRY_JS + """try { return JSON.stringify(await call({ method: 'POST', url: 'http://backend:8000/report/run?site=demoshop' })); } catch (e) { return fail(); }"""
    system = ("Sən QiymətRadar-san: rəqib qiymətləri və qaimə-fakturalar üzrə köməkçi.\n"
              "Qaydalar:\n- Qiymət, dəyişiklik və sənəd məlumatını YALNIZ alətlərdən götür. Rəqəm uydurma, yuvarlaqlaşdırma.\n"
              "- 'Nə dəyişib?' sualında dəyisikliklər alətini işlət. 'şübhəli' işarəli dəyişiklik parser xətası ola bilər: bunu de.\n"
              "- Konkret məhsulun qiymət tarixçəsi üçün mehsul_tarixcesi işlət.\n"
              "- Qaimələr üçün senedler alətini işlət. status=needs_review olan sənəd insan baxışı tələb edir: bunu aydın de, sahələrə etibar etmə.\n"
              "- Alətdə məlumat yoxdursa 'məlumat yoxdur' de.\n- Cavabı Azərbaycan dilində, qısa ver.")
    nodes = [
        node(1, "ChatTrigger", "@n8n/n8n-nodes-langchain.chatTrigger", 1.4, {"public": True, "options": {}}, (-600, 0), webhookId="qr-chat-0001"),
        node(2, "AI Agent", "@n8n/n8n-nodes-langchain.agent", 3.1, {"promptType": "auto", "options": {"systemMessage": system}}, (-300, 0),
             retryOnFail=True, maxTries=2, waitBetweenTries=3000),
        node(3, "Anthropic Chat Model", "@n8n/n8n-nodes-langchain.lmChatAnthropic", 1.5,
             {"model": {"__rl": True, "mode": "id", "value": "claude-haiku-4-5-20251001"}, "options": {"temperature": 0.2}},
             (-480, 260), credentials=CRED["anthropic"], retryOnFail=True, maxTries=3, waitBetweenTries=2000),
        node(4, "Window Buffer Memory", "@n8n/n8n-nodes-langchain.memoryBufferWindow", 1.3,
             {"sessionIdType": "customKey", "sessionKey": "={{ $('ChatTrigger').first().json.sessionId }}", "contextWindowLength": 10}, (-300, 260)),
        tool(5, "deyisikliklər", "Son iki scraping arasında rəqib qiymət dəyişikliklərini qaytarır (ucuzlaşma, bahalaşma, yeni, silinmiş, stok).",
             {"type": "object", "properties": {}}, changes, (-120, 260)),
        tool(6, "mehsul_tarixcesi", "Məhsulun adı ilə qiymət tarixçəsini qaytarır. Lazım olan: mehsul (ad və ya ad hissəsi).",
             {"type": "object", "properties": {"mehsul": {"type": "string", "description": "Məsələn: noutbuk, iPhone"}}, "required": ["mehsul"]}, history, (60, 260)),
        tool(7, "senedler", "Son oxunmuş qaimə-fakturaları qaytarır: sahələr, status (ok / needs_review) və problemlər.",
             {"type": "object", "properties": {}}, docs, (240, 260)),
        tool(8, "hesabat", "Gündəlik qiymət hesabatını yaradır (Claude yazır, rəqəmlər statistika ilə yoxlanır).",
             {"type": "object", "properties": {}}, report, (420, 260)),
    ]
    c = conns(("ChatTrigger", "AI Agent", "main", 0), ("Anthropic Chat Model", "AI Agent", "ai_languageModel", 0), ("Window Buffer Memory", "AI Agent", "ai_memory", 0),
              ("deyisikliklər", "AI Agent", "ai_tool", 0), ("mehsul_tarixcesi", "AI Agent", "ai_tool", 0), ("senedler", "AI Agent", "ai_tool", 0), ("hesabat", "AI Agent", "ai_tool", 0))
    return workflow("QrRadarChat", "QR3 - Radar Söhbəti (AI Agent)", nodes, c)


# ------------------------------------------------------------------ QR4
def flow_error() -> dict:
    nodes = [
        node(1, "Error Trigger", "n8n-nodes-base.errorTrigger", 1, {}, (-400, 0)),
        http(2, "Bildiriş - Xəta", "POST", BACKEND + "/notify", (-160, 0),
             body="={{ JSON.stringify({ text: 'QiymətRadar xətası\\nWorkflow: ' + $json.workflow.name + '\\nNode: ' + $json.execution.lastNodeExecuted + '\\nXəta: ' + $json.execution.error.message }) }}"),
    ]
    return workflow(ERROR_WF, "QR4 - Xəta Bildirişi (Error Trigger)", nodes, conns(("Error Trigger", "Bildiriş - Xəta", "main", 0)), error_wf=False)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for fname, wf in [("qr1-qiymet-monitoru", flow_price()), ("qr2-qaime-oxuyucu", flow_docs()), ("qr3-radar-sohbeti", flow_chat()), ("qr4-xeta-bildirisi", flow_error())]:
        (OUT / f"{fname}.json").write_text(json.dumps(wf, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("yazıldı:", fname, f"({len(wf['nodes'])} node)")


if __name__ == "__main__":
    main()
