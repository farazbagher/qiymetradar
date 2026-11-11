from app.report import grounded, template_report

STATS = {"site": "demoshop", "runs": 2, "products_total": 24, "minor_changes": 3, "price_changes": 7, "baseline": False, "price_down": 3, "price_up": 4, "new": 0, "removed": 0, "out_of_stock": 2,
         "back_in_stock": 0, "suspicious": 0, "unchanged": 14,
         "top_moves": [{"name": "Lenovo IdeaPad 15 noutbuk", "old": 1450.0, "new": 1621.26, "pct": 11.81, "suspicious": False}]}


def test_grounded_accepts_only_numbers_from_stats():
    assert grounded("Lenovo IdeaPad 15 noutbuk 1450.0 -> 1621.26 (11.81%), 3 məhsul ucuzlaşıb.", STATS)
    assert not grounded("Lenovo 12% bahalaşıb.", STATS)                # 12 statistikada yoxdur
    assert not grounded("Qiymət 1622 AZN oldu.", STATS)                # yuvarlaqlaşdırılıb: rədd
    assert grounded("1. **Cəmi**: 24 məhsul\n2. **Ucuzlaşan**: 3", STATS)            # siyahı nömrələri ədəd sayılmır
    assert not grounded("1. **Cəmi**: 99 məhsul", STATS)
    assert grounded("1450 AZN-dən 1621,26 AZN-ə qalxdı (11,81%).", STATS)   # '.0' atılması və vergül formatı ədədi eynidir


def test_template_covers_states():
    assert "hələ scraping aparılmayıb" in template_report({**STATS, "runs": 0})
    assert "baza yaradıldı" in template_report({**STATS, "baseline": True})
    t = template_report(STATS)
    assert "3 məhsul ucuzlayıb" in t and "+11.81%" in t
    assert grounded(t, STATS)                                          # şablonun özü də "əsaslandırılmış"dır


def test_llm_report_retries_once_with_the_invented_numbers_then_falls_back(monkeypatch):
    from langchain_core.messages import AIMessage
    from app import llm, report

    class Fake:
        def __init__(self, answers):
            self.answers, self.seen = list(answers), []

        def invoke(self, msgs):
            self.seen.append(msgs[-1].content)
            return AIMessage(content=self.answers.pop(0))

    # 1-ci cavabda uydurma '99', 2-ci düzəlişdə təmiz
    fake = Fake(["Cəmi 99 məhsul var.", "24 məhsuldan 3-ü ucuzlaşıb."])
    monkeypatch.setattr(llm, "claude_chat", lambda: fake)
    assert report.llm_report(STATS) == "24 məhsuldan 3-ü ucuzlaşıb."
    assert "99" in fake.seen[1]                                         # düzəliş sorğusu uydurulan ədədi göstərir
    # hər iki cavab uydurmadırsa None (çağıran şablona qayıdır)
    fake2 = Fake(["Cəmi 99 məhsul.", "Cəmi 77 məhsul."])
    monkeypatch.setattr(llm, "claude_chat", lambda: fake2)
    assert report.llm_report(STATS) is None
