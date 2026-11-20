"""Phase 5 unit tests (no internet): surprises, beat/miss/inline, beat rate, price reaction timing,
quarter matching and estimate revisions."""
import pandas as pd
import pytest

from core.earnings import (beat_rate, classify, match_quarter, price_reaction, revision_direction,
                           revisions_table, surprise_pct, typical_move, unrounded_estimate)

T = pd.Timestamp


def test_surprise_pct():
    assert surprise_pct(2.10, 2.00) == pytest.approx(5.0)
    assert surprise_pct(-0.9, -1.0) == pytest.approx(10.0)   # smaller loss than expected = positive surprise
    assert surprise_pct(1.0, 0) is None and surprise_pct(None, 1.0) is None


def test_unrounded_estimate_matches_surprise():
    # Shown as 0.40 vs 0.40 but the surprise is -1.11% -> the exact estimate was ~0.4045
    assert unrounded_estimate(0.40, 0.40, -1.11) == pytest.approx(0.4045, abs=1e-4)
    assert unrounded_estimate(-0.9, -1.0, 10.0) == pytest.approx(-1.0)          # loss case
    assert unrounded_estimate(2.10, 1.98, 50.0) == 1.98                           # inconsistent -> keep as is
    assert unrounded_estimate(2.10, 1.98, None) == 1.98


def test_classify_with_inline_band():
    assert classify(5.8) == "beat" and classify(-3.2) == "miss"
    assert classify(0.9) == "inline" and classify(-1.0) == "inline"
    assert classify(None) is None


def test_beat_rate_last_n():
    results = pd.Series(["miss"] * 4 + ["beat", "beat", "inline", "beat"] * 2)
    rate, beats, n = beat_rate(results, 8)
    assert (beats, n) == (6, 8) and rate == pytest.approx(0.75)
    assert beat_rate(pd.Series([None, None]), 8) == (None, 0, 0)


def _close():
    idx = pd.bdate_range("2026-01-05", periods=15)  # Mon 5 Jan ...
    return pd.Series([100, 101, 102, 103, 104, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119], index=idx, dtype=float)


def test_reaction_after_close_uses_same_day_close_as_base():
    c = _close()
    r = price_reaction(c, T("2026-01-09"), "after close")      # Fri 9 Jan close = 104
    assert r.base_date == T("2026-01-09") and r.reaction_date == T("2026-01-12")
    assert r.move_1d == pytest.approx(110 / 104 - 1)
    assert r.move_5d == pytest.approx(114 / 104 - 1)


def test_reaction_before_open_uses_previous_close_as_base():
    c = _close()
    r = price_reaction(c, T("2026-01-12"), "before open")     # Mon 12 Jan, before the open
    assert r.base_date == T("2026-01-09") and r.reaction_date == T("2026-01-12")
    assert r.move_1d == pytest.approx(110 / 104 - 1)


def test_reaction_unknown_time_uses_first_close_after_date():
    c = _close()
    r = price_reaction(c, T("2026-01-10"), "unknown")          # Saturday -> base Fri, reaction Mon
    assert r.base_date == T("2026-01-09") and r.reaction_date == T("2026-01-12")


def test_reaction_outside_history():
    assert price_reaction(_close(), T("2030-01-01"), "after close").move_1d is None


def test_typical_move_is_average_absolute():
    assert typical_move(pd.Series([0.04, -0.02, None, -0.06])) == pytest.approx(0.04)


def test_match_quarter_known_and_estimated():
    q = pd.DataFrame({"period_end": [T("2026-03-28"), T("2026-06-27")], "fiscal_year": [2026, 2026],
                      "fiscal_quarter": [2, 3]})
    m = match_quarter(T("2026-07-30"), q)
    assert m == {"period_end": T("2026-06-27"), "fiscal_year": 2026, "fiscal_quarter": 3, "estimated": False}
    # reported before the 10-Q exists: step to the next quarter and mark it estimated
    est = match_quarter(T("2026-10-30"), q)
    assert est["fiscal_quarter"] == 4 and est["estimated"] is True
    wrap = match_quarter(T("2027-01-30"), q)
    assert wrap["fiscal_year"] == 2027 and wrap["fiscal_quarter"] == 1
    assert match_quarter(T("2025-01-01"), q) is None


def test_revisions_table_and_direction():
    trend = pd.DataFrame({"current": [2.91], "7daysAgo": [2.90], "30daysAgo": [2.85], "60daysAgo": [2.80],
                          "90daysAgo": [2.70], "currency": ["USD"]}, index=["0q"])
    t = revisions_table(trend)
    assert list(t.columns) == ["90 days ago", "60 days ago", "30 days ago", "7 days ago", "Now"]
    assert revision_direction(t.iloc[0]) == "up"
    assert revision_direction(pd.Series({"90 days ago": 2.0, "Now": 1.9})) == "down"
    assert revision_direction(pd.Series({"90 days ago": 2.0, "Now": 2.01})) == "flat"
