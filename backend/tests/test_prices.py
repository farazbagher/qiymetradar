from app.prices import diff, pct_change, run_health


def snap(**kw):
    return {k: {"name": k.title(), "price": v[0], "in_stock": v[1] if len(v) > 1 else True} for k, v in kw.items()}


def test_baseline_has_no_changes():
    d = diff(None, snap(a=(10.0,)))
    assert d.baseline and d.changes == [] and d.stats()["baseline"] is True


def test_threshold_and_direction():
    prev = snap(a=(100.0,), b=(100.0,), c=(100.0,), d=(100.0,))
    cur = snap(a=(94.0,), b=(106.0,), c=(102.0,), d=(100.0,))
    d = diff(prev, cur, alert_pct=5)
    kinds = {c.slug: c.kind for c in d.changes}
    assert kinds == {"a": "price_down", "b": "price_up"}
    assert d.minor == 1 and d.unchanged == 1                  # c eşikdən kiçik, d dəyişməyib


def test_exact_threshold_is_alerted():
    d = diff(snap(a=(100.0,)), snap(a=(95.0,)), alert_pct=5)
    assert d.changes[0].pct == -5.0


def test_new_removed_and_stock_changes():
    prev = snap(a=(10.0, True), b=(10.0, False), gone=(5.0,))
    cur = snap(a=(10.0, False), b=(10.0, True), fresh=(7.0,))
    kinds = sorted(c.kind for c in diff(prev, cur).changes)
    assert kinds == ["back_in_stock", "new", "out_of_stock", "removed"]


def test_suspicious_flag_for_huge_swings():
    d = diff(snap(a=(100.0,), b=(100.0,)), snap(a=(40.0,), b=(70.0,)), suspicious_pct=40)
    by = {c.slug: c for c in d.changes}
    assert by["a"].suspicious and not by["b"].suspicious


def test_pct_change_rounding():
    assert pct_change(749.0, 801.43) == 7.0


def test_run_health_guard():
    assert run_health(24, 24, []) is None
    assert run_health(0, 5, []) is None                       # birinci run
    assert "heç bir məhsul" in run_health(24, 0, ["x"])
    assert "kəskin azaldı" in run_health(24, 11, [])
    assert run_health(24, 12, []) is None                     # tam 50%: hələ icazə var
