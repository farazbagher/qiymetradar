"""Qiymət fərqi mühərriki (təmiz funksiyalar, DB-siz). İki scraping nəticəsini müqayisə edib dəyişiklikləri tapır.

Mühafizə qaydaları (guardrails, ReklamPilot-dakı kimi): scraping səhvi "qiymət dəyişikliyi" kimi görünməsin.
- G1: bir məhsulun qiyməti `suspicious_pct`-dən çox dəyişibsə, xəbərdarlıq "şübhəli" işarəsi alır (parser xətası ola bilər).
- G2: run-ın məhsul sayı əvvəlkindən kəskin azalıbsa və ya 0-dırsa, run xətalı sayılır və baza yenilənmir
  (sayt dizaynı dəyişib, selector sınıb ehtimalı). Əks halda hər məhsul "silinib" kimi görünərdi.
"""

from dataclasses import dataclass, field

DEFAULT_ALERT_PCT = 5.0
DEFAULT_SUSPICIOUS_PCT = 40.0
MAX_DROP_RATIO = 0.5


@dataclass
class Change:
    kind: str                 # price_down | price_up | new | removed | out_of_stock | back_in_stock
    slug: str
    name: str
    old: float | None = None
    new: float | None = None
    pct: float | None = None
    suspicious: bool = False

    def as_dict(self) -> dict:
        return {"kind": self.kind, "slug": self.slug, "name": self.name, "old": self.old, "new": self.new,
                "pct": self.pct, "suspicious": self.suspicious}


@dataclass
class DiffResult:
    changes: list = field(default_factory=list)
    unchanged: int = 0
    minor: int = 0            # eşikdən kiçik dəyişikliklər (xəbərdarlıq verilmir)
    baseline: bool = False    # əvvəlki run yoxdur: yalnız baza yaradılır

    def stats(self) -> dict:
        by = {}
        for c in self.changes:
            by[c.kind] = by.get(c.kind, 0) + 1
        return {"changes": len(self.changes), "by_kind": by, "unchanged": self.unchanged, "minor": self.minor,
                "suspicious": sum(c.suspicious for c in self.changes), "baseline": self.baseline}


def pct_change(old: float, new: float) -> float:
    return round((new - old) / old * 100, 2)


def diff(prev: dict | None, cur: dict, alert_pct: float = DEFAULT_ALERT_PCT, suspicious_pct: float = DEFAULT_SUSPICIOUS_PCT) -> DiffResult:
    """prev/cur: {slug: {"name", "price", "in_stock"}}. prev None/boş: baza run-ı."""
    if not prev:
        return DiffResult(baseline=True, unchanged=len(cur))
    res = DiffResult()
    for slug, now in cur.items():
        before = prev.get(slug)
        if before is None:
            res.changes.append(Change("new", slug, now["name"], new=now["price"]))
            continue
        p = pct_change(before["price"], now["price"])
        if abs(p) >= alert_pct:
            res.changes.append(Change("price_down" if p < 0 else "price_up", slug, now["name"], before["price"], now["price"], p,
                                      suspicious=abs(p) >= suspicious_pct))
        elif p != 0:
            res.minor += 1
        else:
            res.unchanged += 1
        if before["in_stock"] and not now["in_stock"]:
            res.changes.append(Change("out_of_stock", slug, now["name"], new=now["price"]))
        elif not before["in_stock"] and now["in_stock"]:
            res.changes.append(Change("back_in_stock", slug, now["name"], new=now["price"]))
    for slug, before in prev.items():
        if slug not in cur:
            res.changes.append(Change("removed", slug, before["name"], old=before["price"]))
    return res


def run_health(prev_count: int, cur_count: int, warnings: list) -> str | None:
    """Xəta mesajı qaytarır (run-ı rədd et) və ya None (sağlamdır)."""
    if cur_count == 0:
        return "heç bir məhsul tapılmadı: selector sınıb və ya sayt dizaynı dəyişib" + (f" ({warnings[0]})" if warnings else "")
    if prev_count and cur_count < prev_count * MAX_DROP_RATIO:
        return f"məhsul sayı {prev_count} -> {cur_count} kəskin azaldı: sayt dizaynı dəyişmiş ola bilər, baza yenilənmədi"
    return None
