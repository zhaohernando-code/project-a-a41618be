from __future__ import annotations

from math import sqrt
from statistics import mean
from typing import Any

from ashare_evidence.phase2 import PHASE2_MANUAL_REVIEW_NOTE
from ashare_evidence.signal_engine_parts.base import (
    MANUAL_REVIEW_PLACEHOLDER,
    clip,
    factor_direction,
    pct_change,
    safe_pstdev,
    score_scale,
)


def primary_sector_membership(
    sector_memberships: list[dict[str, Any]],
    as_of_data_time,
) -> dict[str, Any] | None:
    effective = [
        item
        for item in sector_memberships
        if item["effective_from"] <= as_of_data_time
        and (item.get("effective_to") is None or item["effective_to"] >= as_of_data_time)
    ]
    effective.sort(key=lambda item: (not item["is_primary"], item["effective_from"]))
    return effective[0] if effective else None


def active_sector_codes(
    sector_memberships: list[dict[str, Any]],
    as_of_data_time,
) -> set[str]:
    return {
        item["sector_code"]
        for item in sector_memberships
        if item["effective_from"] <= as_of_data_time
        and (item.get("effective_to") is None or item["effective_to"] >= as_of_data_time)
    }


def _lagged_return(closes: list[float], horizon: int) -> tuple[float, int]:
    lag = min(horizon, max(len(closes) - 1, 1))
    return pct_change(closes[-1], closes[-(lag + 1)]), lag


def compute_price_factor(market_bars: list[dict[str, Any]]) -> dict[str, Any]:
    closes = [float(item["close_price"]) for item in market_bars]
    highs = [float(item["high_price"]) for item in market_bars]
    volumes = [float(item["volume"]) for item in market_bars]
    turnovers = [float(item.get("turnover_rate") or 0.0) for item in market_bars]
    returns = [pct_change(closes[idx], closes[idx - 1]) for idx in range(1, len(closes))]

    ret_10d, lookback_10d = _lagged_return(closes, 10)
    ret_20d, lookback_20d = _lagged_return(closes, 20)
    ret_40d, lookback_40d = _lagged_return(closes, 40)
    vol_20d = safe_pstdev(returns[-20:]) * sqrt(20)
    avg_volume_5d = mean(volumes[-5:])
    avg_volume_20d = mean(volumes[-20:])
    volume_zscore_5d = (avg_volume_5d - avg_volume_20d) / (safe_pstdev(volumes[-20:]) or 1.0)
    turnover_5d = mean(turnovers[-5:])
    turnover_20d = mean(turnovers[-20:])
    turnover_gap_5d = turnover_5d - turnover_20d
    close_vs_40d_high = closes[-1] / max(highs[-40:]) - 1
    up_day_ratio_10d = sum(1 for value in returns[-10:] if value > 0) / 10
    drawdown_20d = closes[-1] / max(closes[-20:]) - 1

    trend_component = clip(
        0.25 * score_scale(ret_10d, 0.06)
        + 0.45 * score_scale(ret_20d, 0.10)
        + 0.30 * score_scale(ret_40d, 0.16),
    )
    confirmation_component = clip(
        0.35 * score_scale(volume_zscore_5d, 1.5)
        + 0.25 * score_scale(turnover_gap_5d, 0.02)
        + 0.20 * score_scale(up_day_ratio_10d - 0.5, 0.18)
        + 0.20 * score_scale(close_vs_40d_high, 0.03),
    )
    risk_pressure = clip(
        0.55 * score_scale(max(vol_20d - 0.08, 0.0), 0.05)
        + 0.45 * score_scale(abs(min(drawdown_20d, 0.0)), 0.08),
        0.0,
        1.0,
    )
    price_score = clip(0.60 * trend_component + 0.25 * confirmation_component - 0.15 * risk_pressure)

    drivers: list[str] = []
    risks: list[str] = []
    if ret_20d > 0.05:
        drivers.append(f"20 日收益提升至 {ret_20d:.1%}，中枢趋势仍偏多。")
    if ret_40d > 0.10:
        drivers.append(f"40 日累计收益达到 {ret_40d:.1%}，中期趋势延续。")
    if volume_zscore_5d > 0.8:
        drivers.append(f"近 5 日量能相对 20 日均值抬升 {volume_zscore_5d:.2f}σ。")
    if up_day_ratio_10d >= 0.6:
        drivers.append(f"近 10 个交易日上涨占比 {up_day_ratio_10d:.0%}，短期确认仍在。")

    if vol_20d > 0.11:
        risks.append(f"20 日波动率升至 {vol_20d:.1%}，回撤容忍度要收紧。")
    if drawdown_20d < -0.06:
        risks.append("价格已明显跌离近 20 日中枢，趋势延续概率下降。")
    if close_vs_40d_high < -0.05:
        risks.append("收盘价偏离近 40 日高点较大，追价性价比下降。")
    if turnover_gap_5d < -0.01:
        risks.append("换手率回落，若量能不能延续，价格基线会优先转弱。")
    if not risks:
        risks.append("若 10 日与 20 日动量同时回落至零轴下方，价格基线会先行降级。")

    feature_values = {
        "ret_10d": round(ret_10d, 4),
        "ret_10d_lookback_days": lookback_10d,
        "ret_20d": round(ret_20d, 4),
        "ret_20d_lookback_days": lookback_20d,
        "ret_40d": round(ret_40d, 4),
        "ret_40d_lookback_days": lookback_40d,
        "volatility_20d": round(vol_20d, 4),
        "volume_zscore_5d": round(volume_zscore_5d, 4),
        "turnover_gap_5d": round(turnover_gap_5d, 4),
        "close_vs_40d_high": round(close_vs_40d_high, 4),
        "up_day_ratio_10d": round(up_day_ratio_10d, 4),
        "drawdown_20d": round(drawdown_20d, 4),
        "trend_component": round(trend_component, 4),
        "confirmation_component": round(confirmation_component, 4),
        "risk_pressure": round(risk_pressure, 4),
        "price_baseline_score": round(price_score, 4),
    }
    agreement_bonus = 0.05 if trend_component > 0 and confirmation_component > 0 else 0.0
    confidence_score = clip(0.44 + abs(price_score) * 0.26 + agreement_bonus - risk_pressure * 0.08, 0.0, 0.9)
    return {
        "score": round(price_score, 4),
        "direction": factor_direction(price_score),
        "confidence_score": round(confidence_score, 4),
        "drivers": drivers[:3],
        "risks": risks[:3],
        "feature_values": feature_values,
        "window_start": market_bars[-(lookback_40d + 1)]["observed_at"],
        "window_end": market_bars[-1]["observed_at"],
        "evidence_count": len(market_bars),
        "latest_bar_key": market_bars[-1]["bar_key"],
    }


def _llm_summary_for_key(news_key: str, item_by_key: dict[str, dict[str, Any]]) -> str | None:
    item = item_by_key.get(news_key)
    if not item:
        return None
    llm = (item.get("raw_payload") or {}).get("llm_analysis")
    if isinstance(llm, dict) and not llm.get("_fallback"):
        summary = llm.get("summary_sentence", "").strip()
        if summary:
            return summary
    return None


def _news_driver_texts(
    events: list[dict[str, Any]],
    item_by_key: dict[str, dict[str, Any]],
) -> list[str]:
    texts: list[str] = []
    for event in events:
        llm_summary = _llm_summary_for_key(event["news_key"], item_by_key)
        if llm_summary:
            texts.append(f"公告解读：{llm_summary}")
        else:
            texts.append(f"{event['headline']} 提供正向事件证据。")
    return texts


def _news_risk_texts(
    events: list[dict[str, Any]],
    item_by_key: dict[str, dict[str, Any]],
) -> list[str]:
    texts: list[str] = []
    for event in events:
        llm_summary = _llm_summary_for_key(event["news_key"], item_by_key)
        if llm_summary:
            texts.append(f"风险公告：{llm_summary}")
        else:
            texts.append(f"{event['headline']} 仍是潜在反向事件。")
    return texts


def compute_news_factor(
    *,
    symbol: str,
    as_of_data_time,
    news_items: list[dict[str, Any]],
    news_links: list[dict[str, Any]],
    sector_codes: set[str],
) -> dict[str, Any]:
    item_by_key = {item["news_key"]: item for item in news_items}
    deduped: dict[str, dict[str, Any]] = {}
    for item in sorted(news_items, key=lambda value: value["published_at"], reverse=True):
        deduped.setdefault(item["dedupe_key"], item)

    link_groups: dict[str, list[dict[str, Any]]] = {}
    for link in news_links:
        if link["effective_at"] > as_of_data_time:
            continue
        item = item_by_key.get(link["news_key"])
        if item is None or deduped.get(item["dedupe_key"], {}).get("news_key") != link["news_key"]:
            continue
        if link["entity_type"] == "stock" and link.get("stock_symbol") == symbol:
            link_groups.setdefault(link["news_key"], []).append(link)
        elif link["entity_type"] == "sector" and link.get("sector_code") in sector_codes:
            link_groups.setdefault(link["news_key"], []).append(link)
        elif link["entity_type"] == "market":
            link_groups.setdefault(link["news_key"], []).append(link)

    event_contributions: list[dict[str, Any]] = []
    for news_key, links in link_groups.items():
        item = item_by_key[news_key]
        total = 0.0
        for link in links:
            age_hours = max((as_of_data_time - link["effective_at"]).total_seconds() / 3600, 0.0)
            decay = 0.5 ** (age_hours / max(float(link["decay_half_life_hours"]), 1.0))
            scope_weight = {"stock": 1.0, "sector": 0.7, "market": 0.35}.get(link["entity_type"], 0.0)
            direction_sign = {"positive": 1.0, "negative": -1.0, "neutral": 0.0}.get(link["impact_direction"], 0.0)
            total += direction_sign * float(link["relevance_score"]) * scope_weight * decay
        event_contributions.append(
            {
                "news_key": news_key,
                "headline": item["headline"],
                "published_at": item["published_at"],
                "score": round(total, 4),
            }
        )

    event_contributions.sort(key=lambda item: abs(item["score"]), reverse=True)
    positive_total = sum(item["score"] for item in event_contributions if item["score"] > 0)
    negative_total = -sum(item["score"] for item in event_contributions if item["score"] < 0)
    gross_total = positive_total + negative_total
    conflict_ratio = round(min(positive_total, negative_total) / gross_total, 4) if gross_total else 0.0
    freshness_hours = (
        min((as_of_data_time - item["published_at"]).total_seconds() / 3600 for item in deduped.values())
        if deduped
        else 999.0
    )
    freshness_bonus = 0.08 if freshness_hours <= 72 else 0.0
    coverage_bonus = min(len(event_contributions), 4) * 0.03
    news_score = clip(
        score_scale(positive_total - negative_total, 0.75)
        + freshness_bonus
        + coverage_bonus
        - conflict_ratio * 0.28,
    )

    positive_events = [item for item in event_contributions if item["score"] > 0]
    negative_events = [item for item in event_contributions if item["score"] < 0]
    drivers = _news_driver_texts(positive_events[:2], item_by_key)
    risks = _news_risk_texts(negative_events[:2], item_by_key)
    if conflict_ratio >= 0.25:
        risks.append(f"正负事件冲突度 {conflict_ratio:.0%}，新闻因子不能单独抬高建议强度。")
    if not drivers:
        drivers.append("近 7 日缺少高相关正向事件，新闻因子暂未形成加分。")
    if not risks:
        risks.append("若 7 日内出现负向公告或行业监管扰动，新闻因子会优先转负。")

    feature_values = {
        "news_event_score": round(news_score, 4),
        "deduped_event_count": len(event_contributions),
        "positive_decay_total": round(positive_total, 4),
        "negative_decay_total": round(negative_total, 4),
        "conflict_ratio": conflict_ratio,
        "freshness_hours": round(freshness_hours, 2),
        "event_keys": [item["news_key"] for item in event_contributions[:4]],
    }
    confidence_score = clip(
        0.36
        + min(len(event_contributions), 4) * 0.08
        + freshness_bonus
        - conflict_ratio * 0.18,
        0.0,
        0.84,
    )
    return {
        "score": round(news_score, 4),
        "direction": factor_direction(news_score),
        "confidence_score": round(confidence_score, 4),
        "drivers": drivers[:3],
        "risks": risks[:3],
        "feature_values": feature_values,
        "window_start": min(item["published_at"] for item in deduped.values()) if deduped else as_of_data_time,
        "window_end": as_of_data_time,
        "evidence_count": len(event_contributions),
        "primary_news_key": positive_events[0]["news_key"] if positive_events else (event_contributions[0]["news_key"] if event_contributions else None),
        "conflict_ratio": conflict_ratio,
    }


def compute_fundamental_factor(
    *,
    financial_snapshot: dict[str, Any] | None,
    financial_trends: dict[str, Any] | None,
    financial_llm: dict[str, Any] | None,
) -> dict[str, Any]:
    if not financial_trends or not financial_trends.get("available"):
        return {
            "score": 0.0,
            "direction": "neutral",
            "confidence_score": 0.0,
            "drivers": ["基本面数据暂不可用，当前不参与评分。"],
            "risks": [],
            "feature_values": {"fundamental_score": 0.0, "available": False},
            "evidence_count": 0,
            "weight": 0.0,
        }

    composite = float(financial_trends["composite_score"])
    llm_verdict = None
    drivers: list[str] = []
    risks: list[str] = []

    if financial_llm and not financial_llm.get("_fallback"):
        llm_verdict = financial_llm.get("verdict")
        for d in (financial_llm.get("key_drivers") or [])[:2]:
            drivers.append(f"基本面亮点：{d}")
        for r in (financial_llm.get("key_risks") or [])[:2]:
            risks.append(f"基本面风险：{r}")
        summary = financial_llm.get("summary_sentence", "").strip()
        if summary and not drivers:
            drivers.append(f"基本面评估：{summary}")

    if not drivers:
        if composite > 0.15:
            drivers.append("财务趋势记分卡偏正面，营收、利润或ROE表现优于基准。")
        elif composite < -0.15:
            drivers.append("财务趋势记分卡偏负面，关注营收增速与现金流质量。")

    if not risks:
        if composite < 0.05:
            risks.append("财务指标存在改善空间，若持续恶化将拖累中期判断。")
        if financial_snapshot:
            cf = financial_snapshot.get("operating_cashflow_per_share") or financial_snapshot.get("operating_cashflow")
            eps = financial_snapshot.get("eps") or financial_snapshot.get("basic_eps")
            if cf and eps and float(cf) < float(eps) * 0.3:
                risks.append("经营现金流明显低于每股收益，盈利质量需关注。")

    if llm_verdict:
        verdict_score = {"positive": 0.5, "negative": -0.5, "mixed": 0.0, "neutral": 0.0}.get(llm_verdict, 0.0)
    else:
        verdict_score = 0.0
    adjusted_score = clip(composite * 0.7 + verdict_score * 0.3)

    feature_values = {
        "fundamental_score": round(adjusted_score, 4),
        "composite_trend_score": composite,
        "growth_quality": financial_trends.get("growth_quality", 0),
        "profitability_quality": financial_trends.get("profitability_quality", 0),
        "cash_flow_quality": financial_trends.get("cash_flow_quality", 0),
        "available": True,
        "llm_verdict": llm_verdict,
    }

    confidence = clip(0.3 + abs(adjusted_score) * 0.4 + (0.15 if llm_verdict else 0), 0.0, 0.8)

    return {
        "score": round(adjusted_score, 4),
        "direction": factor_direction(adjusted_score),
        "confidence_score": round(confidence, 4),
        "drivers": drivers[:2],
        "risks": risks[:2],
        "feature_values": feature_values,
        "evidence_count": 1 if financial_trends.get("available") else 0,
        "weight": 0.20,
    }


def compute_manual_review_layer(price_factor: dict[str, Any], news_factor: dict[str, Any]) -> dict[str, Any]:
    feature_values = {
        "manual_review_score": 0.0,
        "status": MANUAL_REVIEW_PLACEHOLDER["status"],
        "note": MANUAL_REVIEW_PLACEHOLDER["note"],
        "input_evidence_count": price_factor["evidence_count"] + news_factor["evidence_count"],
    }
    return {
        "score": 0.0,
        "direction": "neutral",
        "confidence_score": 0.0,
        "drivers": [PHASE2_MANUAL_REVIEW_NOTE],
        "risks": ["当前未接入经验证的手动研究产物，系统不会把语言模型输出计入核心建议。"],
        "feature_values": feature_values,
        "evidence_count": price_factor["evidence_count"] + news_factor["evidence_count"],
        "weight": 0.0,
        "status": MANUAL_REVIEW_PLACEHOLDER["status"],
        "calibration": MANUAL_REVIEW_PLACEHOLDER,
    }


__all__ = [
    "active_sector_codes",
    "compute_fundamental_factor",
    "compute_manual_review_layer",
    "compute_news_factor",
    "compute_price_factor",
    "primary_sector_membership",
]
