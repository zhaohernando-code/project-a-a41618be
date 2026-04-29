"""Integration tests for the revamped fusion logic."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def test_direction_thresholds():
    from ashare_evidence.signal_engine_parts.base import recommendation_direction

    assert recommendation_direction(0.30, False) == "buy"
    assert recommendation_direction(0.15, False) == "add"
    assert recommendation_direction(0.05, False) == "watch"
    assert recommendation_direction(-0.10, False) == "watch"
    assert recommendation_direction(-0.15, False) == "reduce"
    assert recommendation_direction(-0.30, False) == "sell"
    assert recommendation_direction(0.50, True) == "risk_alert"
    print("PASS: direction thresholds")


def test_financial_trends():
    from ashare_evidence.analysis_pipeline import _compute_financial_trends

    strong = _compute_financial_trends({
        "revenue_yoy_pct": 0.25, "netprofit_yoy_pct": 0.30,
        "roe": 0.18, "eps": 1.2, "operating_cashflow_per_share": 1.1,
    })
    assert strong["available"]
    assert strong["composite_score"] > 0.4, f"Expected strong positive, got {strong['composite_score']}"

    weak = _compute_financial_trends({
        "revenue_yoy_pct": -0.10, "netprofit_yoy_pct": -0.25,
        "roe": 0.02, "eps": -0.3, "operating_cashflow_per_share": -0.1,
    })
    assert weak["available"]
    assert weak["composite_score"] < -0.15, f"Expected negative, got {weak['composite_score']}"

    none_result = _compute_financial_trends(None)
    assert not none_result["available"]
    print("PASS: financial trends")


def test_dynamic_weights():
    from ashare_evidence.signal_engine_parts.recommendation import _dynamic_weights

    high_price = {"confidence_score": 0.7, "direction": "positive", "score": 0.4}
    low_news = {"confidence_score": 0.3, "direction": "neutral", "score": 0.05}
    no_fund = {"confidence_score": 0.0, "weight": 0.0, "score": 0.0, "direction": "neutral", "evidence_count": 0}
    w = _dynamic_weights(high_price, low_news, no_fund)
    assert abs(sum(w.values()) - 1.0) < 0.01
    assert w["price_baseline"] > w["news_event"], f"High-confidence price should get more weight: {w}"

    all_equal = {"confidence_score": 0.5, "direction": "positive", "score": 0.3}
    fund_equal = {"confidence_score": 0.5, "weight": 0.20, "score": 0.2, "direction": "positive", "evidence_count": 1}
    w2 = _dynamic_weights(all_equal, all_equal, fund_equal)
    assert abs(sum(w2.values()) - 1.0) < 0.01
    print("PASS: dynamic weights")


def test_conflict_resolution():
    from ashare_evidence.signal_engine_parts.recommendation import _resolve_factor_conflict

    dir1, notes1 = _resolve_factor_conflict("positive", "positive", "negative", 0.6, 0.5, 0.4)
    assert dir1 == "positive"

    dir2, notes2 = _resolve_factor_conflict("negative", "negative", "positive", 0.6, 0.5, 0.4)
    assert dir2 == "negative"

    dir3, notes3 = _resolve_factor_conflict("negative", "positive", "neutral", 0.5, 0.35, 0.0)
    assert dir3 is None
    assert len(notes3) > 0

    print("PASS: conflict resolution")


def test_factor_scoring():
    from ashare_evidence.signal_engine_parts.factors import compute_fundamental_factor

    snap = {"eps": 1.2, "roe": 0.15, "revenue_yoy_pct": 0.20, "netprofit_yoy_pct": 0.25,
            "operating_cashflow_per_share": 1.0}
    from ashare_evidence.analysis_pipeline import _compute_financial_trends
    trends = _compute_financial_trends(snap)

    result = compute_fundamental_factor(
        financial_snapshot=snap, financial_trends=trends, financial_llm=None,
    )
    assert result["direction"] == "positive"
    assert result["score"] > 0.1
    assert result["evidence_count"] == 1

    empty_result = compute_fundamental_factor(
        financial_snapshot=None, financial_trends=None, financial_llm=None,
    )
    assert empty_result["evidence_count"] == 0
    assert empty_result["score"] == 0.0
    print("PASS: fundamental factor scoring")


def test_actionable_summary():
    from ashare_evidence.signal_engine_parts.recommendation import _actionable_summary

    price = {"direction": "positive", "drivers": ["tech bullish"]}
    news = {"direction": "positive", "drivers": ["news bullish"]}
    fund = {"direction": "positive", "evidence_count": 1, "drivers": ["fund bullish"]}

    summary = _actionable_summary("测试股", "buy", 0.35, price, news, fund)
    assert "建仓" in summary
    assert "偏多" in summary

    summary2 = _actionable_summary("测试股", "reduce", -0.20, price, news, None)
    assert "减仓" in summary2
    assert "偏多" in summary2  # price is still positive but overall signal is reduce

    print("PASS: actionable summary")


if __name__ == "__main__":
    test_direction_thresholds()
    test_financial_trends()
    test_dynamic_weights()
    test_conflict_resolution()
    test_factor_scoring()
    test_actionable_summary()
    print("\nAll Phase 3-4 logic tests passed!")
