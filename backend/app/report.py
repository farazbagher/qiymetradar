"""Gündəlik hesabat. Claude yalnız TOPLANMIŞ statistikanı görür (məhsul adları rəqibin açıq məlumatıdır, sənədlər getmir).
Halüsinasiyaya qarşı: hesabatdakı hər rəqəm statistikada olmalıdır, yoxsa deterministik şablona qayıdırıq."""

import json
import os
import re

from app import db
from app.service import latest_changes

PRICE_KINDS = ("price_down", "price_up")


def build_stats(site: str) -> dict:
    ch = latest_changes(site)
    changes = ch.get("changes", [])
    movers = sorted([c for c in changes if c["kind"] in PRICE_KINDS], key=lambda c: abs(c["pct"] or 0), reverse=True)[:5]
    by = ch.get("stats", {}).get("by_kind", {})
    total = len(db.snapshot_map(ch["run_id"])) if ch.get("runs") else 0       # model ümumi sayı özü hesablamasın (səhv edir)
    return {"site": site, "runs": ch.get("runs", 0), "products_total": total, "baseline": ch.get("stats", {}).get("baseline", False),
            "minor_changes": ch.get("stats", {}).get("minor", 0), "price_changes": by.get("price_down", 0) + by.get("price_up", 0),
            "price_down": by.get("price_down", 0), "price_up": by.get("price_up", 0), "new": by.get("new", 0),
            "removed": by.get("removed", 0), "out_of_stock": by.get("out_of_stock", 0), "back_in_stock": by.get("back_in_stock", 0),
            "suspicious": ch.get("stats", {}).get("suspicious", 0), "unchanged": ch.get("stats", {}).get("unchanged", 0),
            "top_moves": [{"name": c["name"], "old": c["old"], "new": c["new"], "pct": c["pct"], "suspicious": c["suspicious"]} for c in movers]}


def template_report(stats: dict) -> str:
    if stats["runs"] == 0:
        return f"{stats['site']} üçün hələ scraping aparılmayıb."
    if stats["baseline"]:
        return f"{stats['site']}: ilk scraping tamamlandı, baza yaradıldı. Dəyişiklik növbəti scraping-dən sonra görünəcək."
    lines = [f"{stats['site']}: {stats['price_down']} məhsul ucuzlayıb, {stats['price_up']} məhsul bahalaşıb, {stats['new']} yeni, "
             f"{stats['removed']} silinmiş, {stats['out_of_stock']} stokdan çıxıb."]
    for m in stats["top_moves"]:
        flag = " (şübhəli: yoxla)" if m["suspicious"] else ""
        lines.append(f"{m['name']}: {m['old']} -> {m['new']} AZN ({m['pct']:+}%){flag}.")
    return "\n".join(lines)


def _tokens(s: str) -> set:
    """Mətndəki ədədlər ƏDƏDİ olaraq (980 == 980.0 == '980,0'): model '.0' atanda yanlış rədd olunmasın."""
    s = re.sub(r"(?m)^\s*\d+[.)]\s+", "", s)               # siyahı nömrələri ('1. ...') məlumat deyil, format işarəsidir
    return {round(float(t.replace(",", ".")), 2) for t in re.findall(r"\d+(?:[.,]\d+)?", s)}


def grounded(text: str, stats: dict) -> bool:
    """Mətndəki hər ədəd statistikada varmı (rəqəm uydurulmayıb)?"""
    allowed = _tokens(json.dumps(stats, ensure_ascii=False))
    return _tokens(text) <= allowed


def llm_report(stats: dict, max_attempts: int = 2):
    """Claude hesabat yazır. Mətndə statistikada olmayan ədəd varsa, uydurduğu ədədləri göstərib BİR DƏFƏ yenidən yazdırırıq.
    Hələ də olmasa None qaytarır (çağıran şablona qayıdır)."""
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
    from app import llm
    msgs = [SystemMessage(content=(
        "Sən qiymət analitikisən. Yalnız verilən JSON-dakı faktlardan istifadə et. Rəqəmləri JSON-dakı kimi, DƏYİŞDİRMƏDƏN, yuvarlaqlaşdırmadan köçür. "
        "Heç nə hesablama, cəmləmə: JSON-da olmayan HEÇ BİR ədəd yazma (məsələn ümumi məhsul sayı JSON-da yoxdursa onu yazma). "
        "Nömrələnmiş siyahı və Markdown başlıq yazma. Azərbaycan dilində 4-6 cümlə yaz, sonda bir qısa tövsiyə ver.")),
        HumanMessage(content=json.dumps(stats, ensure_ascii=False))]
    allowed = _tokens(json.dumps(stats, ensure_ascii=False))
    for attempt in range(max_attempts):
        try:
            out = llm.claude_chat().invoke(msgs).content
        except Exception:
            return None
        bad = sorted(_tokens(out) - allowed)
        if not bad:
            return out
        msgs += [AIMessage(content=out), HumanMessage(content=f"Mətndə statistikada olmayan ədədlər var: {', '.join(f'{b:g}' for b in bad)}. "
                                                              "Onları çıxar və yalnız JSON-dakı ədədlərlə yenidən yaz.")]
    return None


def make_report(site: str, use_llm: bool = True) -> dict:
    stats = build_stats(site)
    text, source = template_report(stats), "template"
    if use_llm and os.environ.get("ANTHROPIC_API_KEY") and stats["runs"] > 0 and not stats["baseline"]:
        out = llm_report(stats)
        if out and grounded(out, stats):
            text, source = re.sub(r"(?m)^#+\s*", "", out).replace("**", "").strip(), "claude"
    rid = db.save_report(text, stats, source)
    return {"id": rid, "text": text, "source": source, "stats": stats}
