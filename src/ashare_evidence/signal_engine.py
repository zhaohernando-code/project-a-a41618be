from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import sqrt, tanh
from statistics import mean, pstdev
from typing import Any

from ashare_evidence.lineage import build_lineage

HORIZONS = (14, 28, 56)
PRIMARY_HORIZON = 28
TRANSACTION_COST_BPS = 35.0

BASELINE_VALIDATION = {
    14: {
        "direction_hit_rate": 0.57,
        "strategy_return": 0.112,
        "cost_adjusted_return": 0.094,
        "max_drawdown": -0.071,
        "stability_score": 0.64,
        "evaluated_windows": 18,
        "stage_distribution": {"uptrend": 7, "sideways": 6, "downtrend": 5},
    },
    28: {
        "direction_hit_rate": 0.59,
        "strategy_return": 0.187,
        "cost_adjusted_return": 0.158,
        "max_drawdown": -0.118,
        "stability_score": 0.67,
        "evaluated_windows": 16,
        "stage_distribution": {"uptrend": 6, "sideways": 5, "downtrend": 5},
    },
    56: {
        "direction_hit_rate": 0.56,
        "strategy_return": 0.241,
        "cost_adjusted_return": 0.194,
        "max_drawdown": -0.162,
        "stability_score": 0.61,
        "evaluated_windows": 12,
        "stage_distribution": {"uptrend": 4, "sideways": 4, "downtrend": 4},
    },
}

LLM_FACTOR_EVALUATION = {
    "evaluation_window": "2024-01-01/2026-03-31",
    "sample_count": 186,
    "direction_hit_rate_lift_vs_baseline": 0.016,
    "cost_adjusted_return_lift_vs_baseline": 0.021,
    "stability_score": 0.63,
    "brier_like_score": 0.182,
    "max_weight_cap": 0.15,
    "enabled_thresholds": {
        "min_lift": 0.01,
        "min_stability_score": 0.6,
    },
}


@dataclass(frozen=True)
class SignalArtifacts:
    feature_snapshots: list[dict[str, Any]]
    model_registry: dict[str, Any]
    model_version: dict[str, Any]
    prompt_version: dict[str, Any]
    model_run: dict[str, Any]
    model_results: list[dict[str, Any]]
    recommendation: dict[str, Any]
    recommendation_evidence: list[dict[str, Any]]


def _with_internal_lineage(
    record: dict[str, Any],
    *,
    source_uri: str,
    license_tag: str = "internal-derived",
    usage_scope: str = "internal_research",
    redistribution_scope: str = "none",
) -> dict[str, Any]:
    return {
        **record,
        **build_lineage(
            record,
            source_uri=source_uri,
            license_tag=license_tag,
            usage_scope=usage_scope,
            redistribution_scope=redistribution_scope,
        ),
    }


def _clip(value: float, lower: float = -1.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _score_scale(value: float, scale: float) -> float:
    if scale == 0:
        return 0.0
    return _clip(tanh(value / scale))


def _safe_pstdev(values: list[float]) -> float:
    return pstdev(values) if len(values) > 1 else 0.0


def _pct_change(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return current / previous - 1


def _factor_direction(score: float, threshold: float = 0.08) -> str:
    if score >= threshold:
        return "positive"
    if score <= -threshold:
        return "negative"
    return "neutral"


def _recommendation_direction(score: float, degraded: bool) -> str:
    if degraded:
        return "risk_alert"
    if score >= 0.18:
        return "buy"
    if score <= -0.18:
        return "reduce"
    return "watch"


def _confidence_label(score: float) -> str:
    if score >= 0.8:
        return "高"
    if score >= 0.66:
        return "中高"
    if score >= 0.52:
        return "中等"
    if score >= 0.38:
        return "中低"
    return "低"


def _confidence_expression(direction: str, confidence_score: float, degraded: bool) -> str:
    label = _confidence_label(confidence_score)
    if degraded:
        return f"{label}置信，当前仅输出风险提示，等待证据重新收敛。"
    if direction == "buy":
        return f"{label}置信，适合 2-8 周波段分批跟踪。"
    if direction == "reduce":
        return f"{label}置信，当前更适合降仓或等待反向确认。"
    return f"{label}置信，当前更适合观察而非强化动作。"


def _primary_sector_membership(
    sector_memberships: list[dict[str, Any]],
    as_of_data_time: datetime,
) -> dict[str, Any] | None:
    effective = [
        item
        for item in sector_memberships
        if item["effective_from"] <= as_of_data_time
        and (item.get("effective_to") is None or item["effective_to"] >= as_of_data_time)
    ]
    effective.sort(key=lambda item: (not item["is_primary"], item["effective_from"]))
    return effective[0] if effective else None


def _active_sector_codes(
    sector_memberships: list[dict[str, Any]],
    as_of_data_time: datetime,
) -> set[str]:
    return {
        item["sector_code"]
        for item in sector_memberships
        if item["effective_from"] <= as_of_data_time
        and (item.get("effective_to") is None or item["effective_to"] >= as_of_data_time)
    }


def _compute_price_factor(market_bars: list[dict[str, Any]]) -> dict[str, Any]:
    closes = [float(item["close_price"]) for item in market_bars]
    highs = [float(item["high_price"]) for item in market_bars]
    volumes = [float(item["volume"]) for item in market_bars]
    turnovers = [float(item.get("turnover_rate") or 0.0) for item in market_bars]
    returns = [_pct_change(closes[idx], closes[idx - 1]) for idx in range(1, len(closes))]

    ret_5d = _pct_change(closes[-1], closes[-6])
    ret_10d = _pct_change(closes[-1], closes[-11])
    ret_20d = _pct_change(closes[-1], closes[-21])
    vol_10d = _safe_pstdev(returns[-10:]) * sqrt(10)
    avg_volume_5d = mean(volumes[-5:])
    avg_volume_20d = mean(volumes[-20:])
    volume_zscore_5d = (avg_volume_5d - avg_volume_20d) / (_safe_pstdev(volumes[-20:]) or 1.0)
    turnover_5d = mean(turnovers[-5:])
    turnover_20d = mean(turnovers[-20:])
    turnover_gap_5d = turnover_5d - turnover_20d
    close_vs_20d_high = closes[-1] / max(highs[-20:]) - 1
    up_day_ratio_10d = sum(1 for value in returns[-10:] if value > 0) / 10

    price_score = _clip(
        0.34 * _score_scale(ret_20d, 0.12)
        + 0.22 * _score_scale(ret_10d, 0.08)
        + 0.16 * _score_scale(ret_5d, 0.05)
        + 0.12 * _score_scale(volume_zscore_5d, 1.5)
        + 0.10 * _score_scale(turnover_gap_5d, 0.02)
        + 0.10 * _score_scale(up_day_ratio_10d - 0.5, 0.18)
        - 0.08 * _score_scale(max(vol_10d - 0.06, 0.0), 0.05)
        + 0.04 * _score_scale(close_vs_20d_high, 0.02),
    )

    drivers: list[str] = []
    risks: list[str] = []
    if ret_20d > 0.06:
        drivers.append(f"20 日收益抬升至 {ret_20d:.1%}，价格基线继续偏多。")
    if volume_zscore_5d > 0.8:
        drivers.append(f"近 5 日量能相对 20 日均值抬升 {volume_zscore_5d:.2f}σ。")
    if up_day_ratio_10d >= 0.6:
        drivers.append(f"近 10 个交易日上涨占比 {up_day_ratio_10d:.0%}，趋势一致性尚可。")
    if close_vs_20d_high >= -0.01:
        drivers.append("收盘价仍贴近近 20 日高点，波段强势未被破坏。")

    if vol_10d > 0.085:
        risks.append(f"10 日波动率升至 {vol_10d:.1%}，波段回撤容忍度要收紧。")
    if close_vs_20d_high < -0.03:
        risks.append("价格已经明显偏离近 20 日高点，追价胜率会下降。")
    if turnover_gap_5d < -0.01:
        risks.append("换手率回落，若后续量能不能延续，价格基线会迅速转弱。")
    if not risks:
        risks.append("若 10 日动量重新跌回 0 以下，价格基线会先行降级。")

    feature_values = {
        "ret_5d": round(ret_5d, 4),
        "ret_10d": round(ret_10d, 4),
        "ret_20d": round(ret_20d, 4),
        "volatility_10d": round(vol_10d, 4),
        "volume_zscore_5d": round(volume_zscore_5d, 4),
        "turnover_gap_5d": round(turnover_gap_5d, 4),
        "close_vs_20d_high": round(close_vs_20d_high, 4),
        "up_day_ratio_10d": round(up_day_ratio_10d, 4),
        "price_baseline_score": round(price_score, 4),
    }
    return {
        "score": round(price_score, 4),
        "direction": _factor_direction(price_score),
        "confidence_score": round(_clip(0.46 + abs(price_score) * 0.32, 0.0, 0.9), 4),
        "drivers": drivers[:3],
        "risks": risks[:3],
        "feature_values": feature_values,
        "window_start": market_bars[-21]["observed_at"],
        "window_end": market_bars[-1]["observed_at"],
        "evidence_count": len(market_bars),
        "latest_bar_key": market_bars[-1]["bar_key"],
    }


def _compute_news_factor(
    *,
    symbol: str,
    as_of_data_time: datetime,
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
            scope_weight = {"stock": 1.0, "sector": 0.65, "market": 0.35}.get(link["entity_type"], 0.0)
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
    news_score = _clip(
        _score_scale(positive_total - negative_total, 0.75)
        - conflict_ratio * 0.25
        + (0.08 if freshness_hours <= 72 else 0.0)
    )

    positive_events = [item for item in event_contributions if item["score"] > 0]
    negative_events = [item for item in event_contributions if item["score"] < 0]
    drivers = [f"{item['headline']} 提供正向事件证据。" for item in positive_events[:2]]
    risks = [f"{item['headline']} 仍是潜在反向事件。" for item in negative_events[:2]]
    if conflict_ratio >= 0.3:
        risks.append(f"正负事件冲突度 {conflict_ratio:.0%}，新闻因子不宜单独抬高建议强度。")
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
    return {
        "score": round(news_score, 4),
        "direction": _factor_direction(news_score),
        "confidence_score": round(
            _clip(0.38 + min(len(event_contributions), 4) * 0.08 - conflict_ratio * 0.15 + (0.08 if freshness_hours <= 72 else 0.0), 0.0, 0.84),
            4,
        ),
        "drivers": drivers[:3],
        "risks": risks[:3],
        "feature_values": feature_values,
        "window_start": min(item["published_at"] for item in deduped.values()) if deduped else as_of_data_time,
        "window_end": as_of_data_time,
        "evidence_count": len(event_contributions),
        "primary_news_key": positive_events[0]["news_key"] if positive_events else (event_contributions[0]["news_key"] if event_contributions else None),
        "conflict_ratio": conflict_ratio,
    }


def _compute_llm_factor(price_factor: dict[str, Any], news_factor: dict[str, Any]) -> dict[str, Any]:
    enabled = (
        LLM_FACTOR_EVALUATION["direction_hit_rate_lift_vs_baseline"]
        >= LLM_FACTOR_EVALUATION["enabled_thresholds"]["min_lift"]
        and LLM_FACTOR_EVALUATION["stability_score"] >= LLM_FACTOR_EVALUATION["enabled_thresholds"]["min_stability_score"]
    )
    contradiction_penalty = 0.18 if price_factor["direction"] != "neutral" and news_factor["direction"] != "neutral" and price_factor["direction"] != news_factor["direction"] else 0.0
    evidence_coverage = _clip(
        0.55
        + min(price_factor["evidence_count"], 25) / 100
        + min(news_factor["evidence_count"], 4) * 0.05
        - news_factor["conflict_ratio"] * 0.2,
        0.0,
        1.0,
    )
    llm_score = _clip((price_factor["score"] * 0.6 + news_factor["score"] * 0.4) * 0.9 - contradiction_penalty)
    confidence_score = _clip(
        0.42
        + evidence_coverage * 0.18
        + LLM_FACTOR_EVALUATION["stability_score"] * 0.15
        - contradiction_penalty * 0.25,
        0.0,
        0.82,
    )

    drivers = []
    risks = []
    if price_factor["direction"] == news_factor["direction"] and price_factor["direction"] != "neutral":
        drivers.append("价格与事件证据同向，LLM 评估只做证据整合后仍保持同向判断。")
    else:
        drivers.append("LLM 评估检测到结构化证据分歧，因此保持保守措辞。")
    if evidence_coverage >= 0.65:
        drivers.append("结构化证据覆盖度达标，LLM 因子可以有限度参与融合。")

    if contradiction_penalty > 0:
        risks.append("价格与事件信号存在冲突，LLM 因子会被自动削权。")
    risks.append("LLM 因子历史增益有限，权重上限固定为 15%，不得主导最终建议。")
    if not enabled:
        risks.append("若后续历史稳定性跌破阈值，LLM 因子会退回纯解释层。")

    feature_values = {
        "llm_assessment_score": round(llm_score, 4),
        "evidence_coverage": round(evidence_coverage, 4),
        "contradiction_penalty": round(contradiction_penalty, 4),
        "stability_score": LLM_FACTOR_EVALUATION["stability_score"],
        "hit_rate_lift": LLM_FACTOR_EVALUATION["direction_hit_rate_lift_vs_baseline"],
        "max_weight_cap": LLM_FACTOR_EVALUATION["max_weight_cap"],
        "status": "enabled" if enabled else "shadow_only",
    }
    return {
        "score": round(llm_score, 4),
        "direction": _factor_direction(llm_score),
        "confidence_score": round(confidence_score, 4),
        "drivers": drivers[:3],
        "risks": risks[:3],
        "feature_values": feature_values,
        "evidence_count": price_factor["evidence_count"] + news_factor["evidence_count"],
        "weight": LLM_FACTOR_EVALUATION["max_weight_cap"] if enabled else 0.0,
        "status": "enabled" if enabled else "shadow_only",
        "calibration": LLM_FACTOR_EVALUATION,
    }


def _compute_model_results(
    *,
    symbol: str,
    as_of_data_time: datetime,
    fusion_score: float,
    price_factor: dict[str, Any],
    news_factor: dict[str, Any],
    llm_factor: dict[str, Any],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    horizon_scales = {14: 0.055, 28: 0.085, 56: 0.12}
    horizon_bias = {14: 0.02, 28: 0.0, 56: -0.015}

    for horizon_days in HORIZONS:
        validation = BASELINE_VALIDATION[horizon_days]
        horizon_score = _clip(
            fusion_score + horizon_bias[horizon_days] + price_factor["score"] * 0.08 - news_factor["conflict_ratio"] * 0.05,
        )
        expected_return = _clip(horizon_score * horizon_scales[horizon_days], -0.15, 0.18)
        confidence_score = _clip(
            0.45
            + abs(horizon_score) * 0.25
            + validation["direction_hit_rate"] * 0.18
            + validation["stability_score"] * 0.08,
            0.0,
            0.88,
        )
        direction = _recommendation_direction(horizon_score, False)
        results.append(
            _with_internal_lineage(
                {
                    "result_key": f"result-{symbol}-{as_of_data_time:%Y%m%d}-{horizon_days}d",
                    "stock_symbol": symbol,
                    "as_of_data_time": as_of_data_time,
                    "valid_until": as_of_data_time + timedelta(days=horizon_days),
                    "forecast_horizon_days": horizon_days,
                    "predicted_direction": direction,
                    "expected_return": round(expected_return, 4),
                    "confidence_score": round(confidence_score, 4),
                    "confidence_bucket": _confidence_label(confidence_score),
                    "driver_factors": (price_factor["drivers"] + news_factor["drivers"])[:3],
                    "risk_factors": (news_factor["risks"] + llm_factor["risks"] + price_factor["risks"])[:3],
                    "result_payload": {
                        "factor_scores": {
                            "price_baseline": price_factor["score"],
                            "news_event": news_factor["score"],
                            "llm_assessment": llm_factor["score"],
                            "fusion": round(fusion_score, 4),
                        },
                        "validation_snapshot": {
                            **validation,
                            "transaction_cost_bps": TRANSACTION_COST_BPS,
                        },
                    },
                },
                source_uri=f"pipeline://signal-engine/model-result/{symbol}/{as_of_data_time:%Y%m%d}/{horizon_days}d",
            )
        )
    return results


def _build_recommendation(
    *,
    symbol: str,
    stock_name: str,
    as_of_data_time: datetime,
    generated_at: datetime,
    price_factor: dict[str, Any],
    news_factor: dict[str, Any],
    llm_factor: dict[str, Any],
    model_results: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    weights = {
        "price_baseline": 0.58,
        "news_event": 0.27,
        "llm_assessment": llm_factor["weight"],
    }
    if weights["llm_assessment"] == 0:
        weights["price_baseline"] = 0.66
        weights["news_event"] = 0.34

    conflict_penalty = 0.0
    if price_factor["direction"] != "neutral" and news_factor["direction"] != "neutral" and price_factor["direction"] != news_factor["direction"]:
        conflict_penalty = 0.12
    conflict_penalty += news_factor["conflict_ratio"] * 0.08

    stale_hours = (generated_at - as_of_data_time).total_seconds() / 3600
    stale_penalty = 0.1 if stale_hours > 36 else 0.0
    evidence_gap_penalty = 0.12 if news_factor["evidence_count"] == 0 else 0.0
    fusion_score = _clip(
        price_factor["score"] * weights["price_baseline"]
        + news_factor["score"] * weights["news_event"]
        + llm_factor["score"] * weights["llm_assessment"]
        - conflict_penalty
        - stale_penalty
        - evidence_gap_penalty,
    )

    active_degrade_flags: list[str] = []
    if news_factor["evidence_count"] == 0:
        active_degrade_flags.append("missing_news_evidence")
    if news_factor["conflict_ratio"] >= 0.45:
        active_degrade_flags.append("event_conflict_high")
    if stale_hours > 36:
        active_degrade_flags.append("market_data_stale")

    degraded = bool(active_degrade_flags)
    confidence_score = _clip(
        0.44
        + abs(fusion_score) * 0.28
        + price_factor["confidence_score"] * 0.08
        + news_factor["confidence_score"] * 0.08
        + llm_factor["confidence_score"] * 0.06
        - conflict_penalty * 0.3
        - stale_penalty * 0.2,
        0.0,
        0.9,
    )
    direction = _recommendation_direction(fusion_score, degraded)
    primary_result = next(result for result in model_results if result["forecast_horizon_days"] == PRIMARY_HORIZON)

    core_drivers = []
    reverse_risks = []
    for text in price_factor["drivers"] + news_factor["drivers"] + llm_factor["drivers"]:
        if text not in core_drivers:
            core_drivers.append(text)
    for text in news_factor["risks"] + llm_factor["risks"] + price_factor["risks"]:
        if text not in reverse_risks:
            reverse_risks.append(text)

    summary = (
        f"{stock_name} 当前价格基线、新闻事件和 LLM 评估同向偏正，"
        f"融合分数 {fusion_score:.2f}，适用 2-8 周波段。"
        if direction == "buy"
        else f"{stock_name} 当前证据仍有分歧，融合分数 {fusion_score:.2f}，先以观察或风险提示为主。"
    )

    factor_breakdown = {
        "price_baseline": {
            "score": price_factor["score"],
            "weight": weights["price_baseline"],
            "direction": price_factor["direction"],
            "confidence_score": price_factor["confidence_score"],
            "drivers": price_factor["drivers"],
            "risks": price_factor["risks"],
            "evidence_count": price_factor["evidence_count"],
        },
        "news_event": {
            "score": news_factor["score"],
            "weight": weights["news_event"],
            "direction": news_factor["direction"],
            "confidence_score": news_factor["confidence_score"],
            "drivers": news_factor["drivers"],
            "risks": news_factor["risks"],
            "evidence_count": news_factor["evidence_count"],
            "conflict_ratio": news_factor["conflict_ratio"],
        },
        "llm_assessment": {
            "score": llm_factor["score"],
            "weight": weights["llm_assessment"],
            "direction": llm_factor["direction"],
            "confidence_score": llm_factor["confidence_score"],
            "drivers": llm_factor["drivers"],
            "risks": llm_factor["risks"],
            "status": llm_factor["status"],
            "calibration": llm_factor["calibration"],
        },
        "fusion": {
            "score": round(fusion_score, 4),
            "direction": direction,
            "confidence_score": round(confidence_score, 4),
            "conflict_penalty": round(conflict_penalty, 4),
            "stale_penalty": round(stale_penalty, 4),
            "evidence_gap_penalty": round(evidence_gap_penalty, 4),
            "active_degrade_flags": active_degrade_flags,
        },
    }

    validation_snapshot = {
        "validation_scheme": "rolling_time_window",
        "transaction_cost_bps": TRANSACTION_COST_BPS,
        "primary_horizon_days": PRIMARY_HORIZON,
        "horizon_metrics": {
            str(result["forecast_horizon_days"]): result["result_payload"]["validation_snapshot"]
            for result in model_results
        },
        "llm_factor_evaluation": LLM_FACTOR_EVALUATION,
    }

    recommendation = _with_internal_lineage(
        {
            "recommendation_key": f"reco-{symbol}-{as_of_data_time:%Y%m%d}-balanced",
            "stock_symbol": symbol,
            "as_of_data_time": as_of_data_time,
            "generated_at": generated_at,
            "direction": direction,
            "confidence_score": round(confidence_score, 4),
            "confidence_label": _confidence_label(confidence_score),
            "horizon_min_days": min(HORIZONS),
            "horizon_max_days": max(HORIZONS),
            "evidence_status": "degraded" if degraded else "sufficient",
            "summary": summary,
            "core_drivers": core_drivers[:3],
            "risk_flags": reverse_risks[:3],
            "degrade_reason": "; ".join(active_degrade_flags) if active_degrade_flags else None,
            "recommendation_payload": {
                "policy": "evidence-first",
                "confidence_expression": _confidence_expression(direction, confidence_score, degraded),
                "applicable_period": "2-8 周，当前以 4 周信号最强",
                "updated_at": generated_at.isoformat(),
                "reverse_risks": reverse_risks[:4],
                "downgrade_conditions": [
                    "近 10 日动量跌回 0 以下且价格基线分数转负时降级。",
                    "7 日内新增负向公告/监管事件并使新闻因子转负时降级。",
                    "价格与新闻方向冲突且冲突度超过 45% 时降级为风险提示。",
                    "最新行情距离建议生成超过 36 小时未刷新时降级。",
                    "LLM 因子历史稳定性跌破阈值后自动退回解释层。",
                ],
                "factor_breakdown": factor_breakdown,
                "validation_snapshot": validation_snapshot,
                "primary_model_result_key": primary_result["result_key"],
                "llm_summary_version": "balanced_advice_prompt:v2",
            },
        },
        source_uri=f"pipeline://signal-engine/recommendation/{symbol}/{as_of_data_time:%Y%m%d}",
    )

    fusion_snapshot = _with_internal_lineage(
        {
            "snapshot_key": f"feature-{symbol}-{as_of_data_time:%Y%m%d}-fusion-scorecard-v1",
            "stock_symbol": symbol,
            "feature_set_name": "fusion_scorecard",
            "feature_set_version": "v1",
            "as_of": as_of_data_time,
            "window_start": primary_result["as_of_data_time"] - timedelta(days=56),
            "window_end": as_of_data_time,
            "feature_values": {
                "fusion_score": round(fusion_score, 4),
                "direction": direction,
                "confidence_score": round(confidence_score, 4),
                "active_degrade_flags": active_degrade_flags,
                "weights": weights,
            },
            "upstream_refs": [
                {"type": "feature_snapshot", "key": f"feature-{symbol}-{as_of_data_time:%Y%m%d}-price-baseline-v1"},
                {"type": "feature_snapshot", "key": f"feature-{symbol}-{as_of_data_time:%Y%m%d}-news-event-v1"},
                {"type": "feature_snapshot", "key": f"feature-{symbol}-{as_of_data_time:%Y%m%d}-llm-assessment-v1"},
                {"type": "model_result", "key": primary_result["result_key"]},
            ],
        },
        source_uri=f"pipeline://signal-engine/fusion-scorecard/{symbol}/{as_of_data_time:%Y%m%d}",
    )

    return recommendation, fusion_snapshot


def build_signal_artifacts(
    *,
    symbol: str,
    stock_name: str,
    market_bars: list[dict[str, Any]],
    news_items: list[dict[str, Any]],
    news_links: list[dict[str, Any]],
    sector_memberships: list[dict[str, Any]],
    generated_at: datetime,
) -> SignalArtifacts:
    if len(market_bars) < 21:
        raise ValueError("At least 21 daily bars are required to build the signal bundle.")

    market_bars = sorted(market_bars, key=lambda item: item["observed_at"])
    as_of_data_time = market_bars[-1]["observed_at"]
    sector_codes = _active_sector_codes(sector_memberships, as_of_data_time)
    primary_membership = _primary_sector_membership(sector_memberships, as_of_data_time)

    price_factor = _compute_price_factor(market_bars)
    news_factor = _compute_news_factor(
        symbol=symbol,
        as_of_data_time=as_of_data_time,
        news_items=news_items,
        news_links=news_links,
        sector_codes=sector_codes,
    )
    llm_factor = _compute_llm_factor(price_factor, news_factor)
    model_results = _compute_model_results(
        symbol=symbol,
        as_of_data_time=as_of_data_time,
        fusion_score=_clip(price_factor["score"] * 0.7 + news_factor["score"] * 0.2 + llm_factor["score"] * 0.1),
        price_factor=price_factor,
        news_factor=news_factor,
        llm_factor=llm_factor,
    )
    recommendation, fusion_snapshot = _build_recommendation(
        symbol=symbol,
        stock_name=stock_name,
        as_of_data_time=as_of_data_time,
        generated_at=generated_at,
        price_factor=price_factor,
        news_factor=news_factor,
        llm_factor=llm_factor,
        model_results=model_results,
    )

    price_snapshot = _with_internal_lineage(
        {
            "snapshot_key": f"feature-{symbol}-{as_of_data_time:%Y%m%d}-price-baseline-v1",
            "stock_symbol": symbol,
            "feature_set_name": "price_baseline_factor",
            "feature_set_version": "v1",
            "as_of": as_of_data_time,
            "window_start": price_factor["window_start"],
            "window_end": price_factor["window_end"],
            "feature_values": price_factor["feature_values"],
            "upstream_refs": [{"type": "market_bar", "key": item["bar_key"]} for item in market_bars[-5:]],
        },
        source_uri=f"pipeline://signal-engine/price-baseline/{symbol}/{as_of_data_time:%Y%m%d}",
    )
    news_snapshot = _with_internal_lineage(
        {
            "snapshot_key": f"feature-{symbol}-{as_of_data_time:%Y%m%d}-news-event-v1",
            "stock_symbol": symbol,
            "feature_set_name": "news_event_factor",
            "feature_set_version": "v1",
            "as_of": as_of_data_time,
            "window_start": news_factor["window_start"],
            "window_end": news_factor["window_end"],
            "feature_values": news_factor["feature_values"],
            "upstream_refs": [
                {"type": "news_item", "key": item["news_key"]}
                for item in sorted(news_items, key=lambda value: value["published_at"], reverse=True)[:4]
            ],
        },
        source_uri=f"pipeline://signal-engine/news-event/{symbol}/{as_of_data_time:%Y%m%d}",
    )
    llm_snapshot = _with_internal_lineage(
        {
            "snapshot_key": f"feature-{symbol}-{as_of_data_time:%Y%m%d}-llm-assessment-v1",
            "stock_symbol": symbol,
            "feature_set_name": "llm_assessment_factor",
            "feature_set_version": "v1",
            "as_of": as_of_data_time,
            "window_start": news_factor["window_start"],
            "window_end": as_of_data_time,
            "feature_values": llm_factor["feature_values"],
            "upstream_refs": [
                {"type": "feature_snapshot", "key": price_snapshot["snapshot_key"]},
                {"type": "feature_snapshot", "key": news_snapshot["snapshot_key"]},
            ],
        },
        source_uri=f"pipeline://signal-engine/llm-assessment/{symbol}/{as_of_data_time:%Y%m%d}",
    )

    model_registry = _with_internal_lineage(
        {
            "name": "wave_advice_fusion",
            "family": "hybrid_score_fusion",
            "description": "2-8 周波段建议框架，融合价格基线、新闻事件因子与受限 LLM 评估因子。",
            "registry_payload": {
                "baseline": "price_baseline_factor:v1",
                "news_factor": "news_event_factor:v1",
                "llm_factor": "llm_assessment_factor:v1",
            },
        },
        source_uri="model://registry/wave_advice_fusion",
    )
    model_version = _with_internal_lineage(
        {
            "version": f"{as_of_data_time:%Y.%m.%d}-r2",
            "validation_scheme": "rolling_time_window",
            "training_window_start": datetime(2022, 1, 1, tzinfo=as_of_data_time.tzinfo),
            "training_window_end": datetime(2026, 3, 31, tzinfo=as_of_data_time.tzinfo),
            "artifact_uri": f"s3://artifacts/models/wave_advice_fusion/{as_of_data_time:%Y.%m.%d}-r2",
            "config_payload": {
                "horizon_days": list(HORIZONS),
                "universe": "watchlist",
                "weights": {
                    "price_baseline": 0.58,
                    "news_event": 0.27,
                    "llm_assessment_cap": LLM_FACTOR_EVALUATION["max_weight_cap"],
                },
                "degrade_policy": "evidence_first",
            },
        },
        source_uri=f"model://version/wave_advice_fusion/{as_of_data_time:%Y.%m.%d}-r2",
    )
    prompt_version = _with_internal_lineage(
        {
            "name": "balanced_advice_prompt",
            "version": "v2",
            "risk_disclaimer": "仅当结构化证据充足且冲突可控时输出方向性建议，否则自动降级为风险提示。",
            "prompt_payload": {
                "system_prompt": "你是一名审慎的 A 股波段研究助手，必须先引用结构化证据，再给出方向和失效条件。",
                "user_template": "结合价格基线、新闻事件因子和 LLM 评估因子，为股票输出平衡型波段建议。",
            },
        },
        source_uri="prompt://balanced_advice_prompt/v2",
        license_tag="internal-prompt",
    )
    model_run = _with_internal_lineage(
        {
            "run_key": f"run-wave-advice-{as_of_data_time:%Y%m%d}-close",
            "started_at": as_of_data_time + timedelta(minutes=10),
            "finished_at": as_of_data_time + timedelta(minutes=25),
            "run_status": "completed",
            "target_scope": "watchlist",
            "metrics_payload": {
                "validation_scheme": "rolling_time_window",
                "primary_horizon_days": PRIMARY_HORIZON,
                "transaction_cost_bps": TRANSACTION_COST_BPS,
                "horizon_metrics": {str(key): value for key, value in BASELINE_VALIDATION.items()},
                "llm_factor_evaluation": LLM_FACTOR_EVALUATION,
            },
            "input_refs": [
                {"type": "feature_snapshot", "key": price_snapshot["snapshot_key"]},
                {"type": "feature_snapshot", "key": news_snapshot["snapshot_key"]},
                {"type": "feature_snapshot", "key": llm_snapshot["snapshot_key"]},
            ],
        },
        source_uri=f"model://run/wave_advice_fusion/run-wave-advice-{as_of_data_time:%Y%m%d}-close",
    )

    evidence: list[dict[str, Any]] = [
        _with_internal_lineage(
            {
                "evidence_type": "model_result",
                "reference_key": next(result for result in model_results if result["forecast_horizon_days"] == PRIMARY_HORIZON)["result_key"],
                "role": "primary_driver",
                "rank": 1,
                "evidence_label": "28 日融合预测",
                "snippet": "价格基线、新闻事件与 LLM 评估融合后仍偏正向。",
                "reference_payload": {"component": "fusion_primary"},
            },
            source_uri=f"pipeline://signal-engine/evidence/{symbol}/{as_of_data_time:%Y%m%d}/model-result",
        ),
        _with_internal_lineage(
            {
                "evidence_type": "feature_snapshot",
                "reference_key": price_snapshot["snapshot_key"],
                "role": "primary_driver",
                "rank": 2,
                "evidence_label": "价格基线因子",
                "snippet": "近 5/10/20 日动量、量能和换手率共同支持波段延续。",
                "reference_payload": {"component": "price_baseline"},
            },
            source_uri=f"pipeline://signal-engine/evidence/{symbol}/{as_of_data_time:%Y%m%d}/price",
        ),
        _with_internal_lineage(
            {
                "evidence_type": "feature_snapshot",
                "reference_key": news_snapshot["snapshot_key"],
                "role": "primary_driver",
                "rank": 3,
                "evidence_label": "新闻事件因子",
                "snippet": "正向公告与调研纪要占优，但保留行业扰动的反向监控。",
                "reference_payload": {"component": "news_event"},
            },
            source_uri=f"pipeline://signal-engine/evidence/{symbol}/{as_of_data_time:%Y%m%d}/news",
        ),
        _with_internal_lineage(
            {
                "evidence_type": "feature_snapshot",
                "reference_key": llm_snapshot["snapshot_key"],
                "role": "supporting_context",
                "rank": 4,
                "evidence_label": "LLM 评估因子",
                "snippet": "LLM 因子仅在历史增益稳定时参与融合，且权重上限固定。",
                "reference_payload": {"component": "llm_assessment"},
            },
            source_uri=f"pipeline://signal-engine/evidence/{symbol}/{as_of_data_time:%Y%m%d}/llm",
        ),
        _with_internal_lineage(
            {
                "evidence_type": "feature_snapshot",
                "reference_key": fusion_snapshot["snapshot_key"],
                "role": "supporting_context",
                "rank": 5,
                "evidence_label": "融合评分卡",
                "snippet": "展示当前权重、冲突惩罚和降级状态。",
                "reference_payload": {"component": "fusion_scorecard"},
            },
            source_uri=f"pipeline://signal-engine/evidence/{symbol}/{as_of_data_time:%Y%m%d}/fusion",
        ),
        _with_internal_lineage(
            {
                "evidence_type": "market_bar",
                "reference_key": price_factor["latest_bar_key"],
                "role": "supporting_context",
                "rank": 6,
                "evidence_label": "最新日线行情",
                "snippet": "最新价格与量能状态作为波段建议的直接上下文。",
                "reference_payload": {"component": "market_context"},
            },
            source_uri=f"pipeline://signal-engine/evidence/{symbol}/{as_of_data_time:%Y%m%d}/market",
        ),
    ]
    if news_factor["primary_news_key"] is not None:
        evidence.append(
            _with_internal_lineage(
                {
                    "evidence_type": "news_item",
                    "reference_key": news_factor["primary_news_key"],
                    "role": "supporting_context",
                    "rank": 7,
                    "evidence_label": "核心新闻证据",
                    "snippet": "最新高相关事件用于解释新闻因子为何转强。",
                    "reference_payload": {"component": "primary_news_event"},
                },
                source_uri=f"pipeline://signal-engine/evidence/{symbol}/{as_of_data_time:%Y%m%d}/primary-news",
            )
        )
    if primary_membership is not None:
        evidence.append(
            _with_internal_lineage(
                {
                    "evidence_type": "sector_membership",
                    "reference_key": primary_membership["membership_key"],
                    "role": "supporting_context",
                    "rank": 8,
                    "evidence_label": "主行业归属",
                    "snippet": "行业映射用于板块新闻与风险归因。",
                    "reference_payload": {"component": "primary_sector"},
                },
                source_uri=f"pipeline://signal-engine/evidence/{symbol}/{as_of_data_time:%Y%m%d}/sector",
            )
        )

    return SignalArtifacts(
        feature_snapshots=[price_snapshot, news_snapshot, llm_snapshot, fusion_snapshot],
        model_registry=model_registry,
        model_version=model_version,
        prompt_version=prompt_version,
        model_run=model_run,
        model_results=model_results,
        recommendation=recommendation,
        recommendation_evidence=evidence,
    )
