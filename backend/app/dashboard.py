HTML = r"""<!doctype html>
<html lang="az"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>QiymətRadar</title>
<style>
:root{--bg:#0d1620;--panel:#14212e;--panel2:#1a2b3c;--line:#243a50;--ink:#e6eef7;--mute:#8da2b8;--acc:#2dd4bf;--up:#fb7185;--down:#4ade80;--warn:#fbbf24;--info:#60a5fa}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,"Segoe UI",system-ui,sans-serif}
header{position:sticky;top:0;z-index:5;background:var(--bg);border-bottom:1px solid var(--line);padding:12px 20px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
header h1{font-size:20px;margin:0 8px 0 0;letter-spacing:-.01em}header h1 span{color:var(--acc)}
button,select,input[type=file]{font:inherit;background:var(--panel2);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:7px 12px;cursor:pointer}
button:hover{border-color:var(--acc)}button.primary{background:var(--acc);color:#04201c;border-color:var(--acc);font-weight:600}
button:disabled{opacity:.5;cursor:wait}
#msg{color:var(--mute);font-size:13px;margin-left:auto}
main{max-width:1180px;margin:0 auto;padding:20px;display:grid;gap:20px}
section{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px 18px;min-width:0}
section h2{margin:0 0 4px;font-size:16px}section p.sub{margin:0 0 12px;color:var(--mute);font-size:13px}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--line);vertical-align:middle}
th{color:var(--mute);font-weight:500;font-size:12px;text-transform:uppercase;letter-spacing:.06em}
.scroll{overflow-x:auto}
.badge{display:inline-block;padding:1px 9px;border-radius:99px;font-size:12px;font-weight:600}
.b-price_down{background:#14532d;color:var(--down)}.b-price_up{background:#4c1d2b;color:var(--up)}
.b-new{background:#17304f;color:var(--info)}.b-removed{background:#3a3a3a;color:#ccc}
.b-out_of_stock{background:#4a3a10;color:var(--warn)}.b-back_in_stock{background:#14403b;color:var(--acc)}
.b-ok{background:#14532d;color:var(--down)}.b-needs_review{background:#4a3a10;color:var(--warn)}
.b-error,.b-blocked{background:#4c1d2b;color:var(--up)}
.sus{color:var(--warn);font-size:12px}
.mono{font-family:ui-monospace,Menlo,monospace;font-size:13px}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.card{background:var(--panel2);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin-top:12px}
.kv{display:grid;grid-template-columns:130px 1fr;gap:4px 12px;font-size:14px}.kv b{color:var(--mute);font-weight:500}
pre{white-space:pre-wrap;background:#0a121a;border-radius:8px;padding:10px;font-size:12px;max-height:220px;overflow:auto;margin:8px 0 0}
.report{white-space:pre-wrap}
svg.spark{width:110px;height:26px;vertical-align:middle}
.hint{color:var(--mute);font-size:13px}
@media(max-width:700px){main{padding:12px}.kv{grid-template-columns:1fr}}
</style></head><body>
<header>
  <h1>Qiymət<span>Radar</span></h1>
  <button class="primary" id="b-scrape">Scrape et</button>
  <select id="strategy"><option value="">strategiya: avto (static)</option><option value="static">static (BeautifulSoup)</option><option value="api">api (JSON)</option><option value="selenium">selenium (dinamik)</option></select>
  <button id="b-day">Rəqibdə 1 gün irəli</button>
  <button id="b-report">Hesabat yarat</button>
  <button id="b-private">robots.txt testi</button>
  <button id="b-reset">Sıfırla</button>
  <span id="msg">hazırdır</span>
</header>
<main>
  <section><h2>Qiymət dəyişiklikləri</h2><p class="sub">Son iki uğurlu scraping arasındakı fərq. Şübhəli (40%-dən çox) dəyişiklik parser xətası ola bilər, yoxla.</p>
    <div class="scroll"><table id="t-changes"><thead><tr><th>Növ</th><th>Məhsul</th><th>Əvvəl</th><th>İndi</th><th>%</th></tr></thead><tbody></tbody></table></div>
    <p class="hint" id="changes-hint"></p></section>

  <section><h2>Hesabat</h2><p class="sub">Claude yalnız toplanmış statistikanı görür. Hər rəqəm yoxlanır, uyğun gəlmirsə şablon göstərilir.</p>
    <div class="report" id="report">Hələ hesabat yoxdur.</div><p class="hint" id="report-src"></p></section>

  <section><h2>Qaimə-faktura oxuyucu</h2><p class="sub">PDF (mətnli və ya skan) və ya şəkil yüklə. Sahələr çıxarılır və hər dəyər sənəd mətni ilə yoxlanır.</p>
    <div class="row">
      <input type="file" id="file" accept=".pdf,.png,.jpg,.jpeg">
      <select id="mode"><option value="ladder">ladder (regex → lokal model → insan)</option><option value="regex">yalnız regex</option><option value="local">yalnız lokal model</option></select>
      <button class="primary" id="b-upload">Çıxar</button>
      <span class="hint">və ya demo sənəd:</span>
      <select id="demo"></select><button id="b-demo">Yüklə və çıxar</button>
    </div>
    <div id="docresult"></div>
    <div class="scroll" style="margin-top:14px"><table id="t-docs"><thead><tr><th>#</th><th>Fayl</th><th>Növ</th><th>Üsul</th><th>Nömrə</th><th>Tarix</th><th>Satıcı</th><th>Cəmi</th><th>Status</th></tr></thead><tbody></tbody></table></div></section>

  <section><h2>Məhsullar</h2><p class="sub">Hər məhsulun qiymət tarixçəsi.</p>
    <div class="scroll"><table id="t-prod"><thead><tr><th>Məhsul</th><th>Qiymət</th><th>Tarixçə</th><th>Stok</th></tr></thead><tbody></tbody></table></div></section>

  <section><h2>Scraping tarixçəsi</h2><p class="sub">blocked = robots.txt qadağan etdi. error = sağlamlıq yoxlaması və ya şəbəkə xətası (baza yenilənmədi).</p>
    <div class="scroll"><table id="t-runs"><thead><tr><th>#</th><th>Sayt</th><th>Strategiya</th><th>Status</th><th>Məhsul</th><th>Saniyə</th><th>Xəta</th></tr></thead><tbody></tbody></table></div></section>
</main>
<script>
const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const KIND={price_down:'ucuzlaşdı',price_up:'bahalaşdı',new:'yeni',removed:'silindi',out_of_stock:'stokdan çıxdı',back_in_stock:'stoka qayıtdı'};
const msg=t=>$('#msg').textContent=t;
async function api(path,opt){const r=await fetch(path,opt);let j={};try{j=await r.json()}catch(e){}if(!r.ok)throw new Error(j.detail||r.statusText);return j}
async function busy(btn,label,fn){btn.disabled=true;msg(label+'...');try{await fn();msg('hazırdır')}catch(e){msg('XƏTA: '+e.message)}btn.disabled=false;await loadAll()}

function spark(h){if(h.length<2)return '<span class="hint">1 ölçmə</span>';const p=h.map(x=>x.price),min=Math.min(...p),max=Math.max(...p),w=110,ht=26;
  const pts=p.map((v,i)=>[i*(w-6)/(p.length-1)+3,max===min?ht/2:ht-3-(v-min)/(max-min)*(ht-6)]);
  const up=p[p.length-1]>p[0],col=p[p.length-1]===p[0]?'#8da2b8':(up?'#fb7185':'#4ade80');
  return `<svg class="spark" viewBox="0 0 ${w} ${ht}"><polyline fill="none" stroke="${col}" stroke-width="2" points="${pts.map(q=>q.join(',')).join(' ')}"/><circle cx="${pts.at(-1)[0]}" cy="${pts.at(-1)[1]}" r="3" fill="${col}"/></svg>`}

async function loadChanges(){const c=await api('/changes?site=demoshop');const tb=$('#t-changes tbody');
  if(!c.runs){tb.innerHTML='';$('#changes-hint').textContent='Hələ scraping aparılmayıb: "Scrape et" düyməsinə bas.';return}
  if(c.stats.baseline){tb.innerHTML='';$('#changes-hint').textContent='İlk scraping: baza yaradıldı. "Rəqibdə 1 gün irəli" və yenidən "Scrape et" ilə dəyişiklikləri gör.';return}
  tb.innerHTML=c.changes.map(x=>`<tr><td><span class="badge b-${x.kind}">${KIND[x.kind]}</span></td><td>${esc(x.name)} ${x.suspicious?'<span class="sus">şübhəli</span>':''}</td><td class="mono">${x.old??''}</td><td class="mono">${x.new??''}</td><td class="mono">${x.pct!=null?(x.pct>0?'+':'')+x.pct+'%':''}</td></tr>`).join('')||'<tr><td colspan=5 class="hint">Dəyişiklik yoxdur.</td></tr>';
  $('#changes-hint').textContent=`${c.stats.changes} dəyişiklik, ${c.stats.minor} kiçik (eşikdən aşağı), ${c.stats.unchanged} dəyişməyib.`}
async function loadProducts(){const {products}=await api('/products?site=demoshop');
  const rows=await Promise.all(products.map(async p=>({p,h:(await api(`/products/${p.id}/history`)).history})));
  $('#t-prod tbody').innerHTML=rows.map(({p,h})=>`<tr><td>${esc(p.name)}</td><td class="mono">${p.price.toFixed(2)} ${p.currency}</td><td>${spark(h)}</td><td>${p.in_stock?'':'<span class="badge b-out_of_stock">yoxdur</span>'}</td></tr>`).join('')}
async function loadRuns(){const {runs}=await api('/runs');$('#t-runs tbody').innerHTML=runs.map(r=>`<tr><td>${r.id}</td><td>${esc(r.site)}</td><td>${esc(r.strategy)}</td><td><span class="badge b-${r.status}">${r.status}</span></td><td>${r.items}</td><td class="mono">${(+r.seconds).toFixed(1)}</td><td class="hint">${esc(r.error)}</td></tr>`).join('')}
async function loadDocs(){const {documents}=await api('/documents');$('#t-docs tbody').innerHTML=documents.map(d=>`<tr><td>${d.id}</td><td>${esc(d.filename)}</td><td>${esc(d.kind)}</td><td>${esc(d.method)} / ${esc(d.extractor)}</td><td class="mono">${esc(d.data.invoice_no)}</td><td class="mono">${esc(d.data.date)}</td><td>${esc(d.data.vendor)}</td><td class="mono">${d.data.total??''}</td><td><span class="badge b-${d.status}">${d.status==='ok'?'ok':'baxış lazımdır'}</span></td></tr>`).join('')}
async function loadReport(){const {report}=await api('/report/latest');if(!report)return;$('#report').textContent=report.text;$('#report-src').textContent='mənbə: '+(report.source==='claude'?'Claude (rəqəmlər yoxlanıb)':'deterministik şablon')+' · '+report.created_at.slice(0,19).replace('T',' ')}
function showDoc(r){const f=r.data||{};const iss=(r.issues||[]).length?`<div class="sus">Problemlər: ${r.issues.map(esc).join('; ')}</div>`:'';
  $('#docresult').innerHTML=`<div class="card"><div class="row"><span class="badge b-${r.status}">${r.status==='ok'?'yoxlamadan keçdi':'insan baxışı lazımdır'}</span><span class="hint">${esc(r.kind)} · ${esc(r.method)} · çıxaran: ${esc(r.extractor)} · ${r.seconds}s${r.ocr_conf!=null?' · OCR etibarı '+r.ocr_conf:''}</span></div>
  <div class="kv" style="margin-top:8px"><b>Nömrə</b><span class="mono">${esc(f.invoice_no)}</span><b>Tarix</b><span class="mono">${esc(f.date)}</span><b>Satıcı</b><span>${esc(f.vendor)}</span><b>Cəmi</b><span class="mono">${esc(f.total)} ${esc(f.currency)}</span><b>ƏDV</b><span class="mono">${esc(f.vat)}</span></div>${iss}
  <details style="margin-top:8px"><summary class="hint">Sənədin mətni (ilk 600 simvol)</summary><pre>${esc(r.text_preview)}</pre></details></div>`}

$('#b-scrape').onclick=e=>busy(e.target,'scraping',async()=>{const s=$('#strategy').value;const r=await api('/scrape/demoshop'+(s?'?strategy='+s:''),{method:'POST'});if(r.status!=='ok')throw new Error(r.error||r.status)});
$('#b-day').onclick=e=>busy(e.target,'rəqibdə yeni gün',()=>api('/demo/advance',{method:'POST'}));
$('#b-report').onclick=e=>busy(e.target,'hesabat',()=>api('/report/run',{method:'POST'}));
$('#b-private').onclick=e=>busy(e.target,'robots.txt yoxlanır',async()=>{const r=await api('/scrape/demoshop-private',{method:'POST'});throw new Error(r.status==='blocked'?'BLOKLANDI: '+r.error:'bloklanmadı?! '+r.status)});
$('#b-reset').onclick=e=>busy(e.target,'sıfırlanır',async()=>{await api('/demo/reset',{method:'POST'});$('#docresult').innerHTML='';$('#report').textContent='Hələ hesabat yoxdur.'});
$('#b-upload').onclick=e=>busy(e.target,'sənəd oxunur (lokal model 10-30 san çəkə bilər)',async()=>{const f=$('#file').files[0];if(!f)throw new Error('fayl seç');const fd=new FormData();fd.append('file',f);fd.append('mode',$('#mode').value);showDoc(await api('/documents/extract',{method:'POST',body:fd}))});
$('#b-demo').onclick=e=>busy(e.target,'demo sənəd oxunur',async()=>{showDoc(await api('/documents/extract-url',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:$('#demo').value,mode:$('#mode').value})}))});

async function loadAll(){await Promise.all([loadChanges(),loadProducts(),loadRuns(),loadDocs(),loadReport()])}
(async()=>{try{const d=await api('/demo/docs');$('#demo').innerHTML=d.documents.flatMap(x=>[[`http://demoshop:8090${x.pdf}`,`${x.name} · mətnli PDF`],[`http://demoshop:8090${x.scan_pdf}`,`${x.name} · skan PDF (OCR)`],[`http://demoshop:8090${x.scan_image}`,`${x.name} · şəkil (OCR)`]]).map(([v,l])=>`<option value="${v}">${l}</option>`).join('')}catch(e){}
  loadAll()})();
</script></body></html>
"""
