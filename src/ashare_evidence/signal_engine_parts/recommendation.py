from __future__ import annotations

from datetime import timedelta
from math import sqrt
from typing import Any

from ashare_evidence.phase2 import (
    PHASE2_COST_DEFINITION,
    PHASE2_LABEL_DEFINITION,
    PHASE2_MANUAL_REVIEW_NOTE,
    PHASE2_POLICY_VERSION,
    PHASE2_PRIMARY_HORIZON,
    PHASE2_RULE_BASELINE,
    PHASE2_WINDOW_DEFINITION,
    phase2_target_horizon_label,
)
from ashare_evidence.phase2.phase5_contract import phase5_benchmark_definition
from ashare_evidence.signal_engine_parts.base import (
    FUSION_WEIGHTS,
    HORIZONS,
    PRIMARY_HORIZON,
    TRANSACTION_COST_BPS,
    VALIDATION_PENDING,
    clip,
    confidence_expression,
    confidence_label,
    json_datetime,
    recommendation_direction,
    recommendation_direction_with_degrade_flags,
    with_internal_lineage,
)
from ashare_evidence.signal_engine_parts.fusion_helpers import (
    actionable_summary,
    display_conflicts,
    dynamic_weights,
    factor_card,
    resolve_factor_conflict,
    supporting_context,
)


def _fusion_state(
    *,
    as_of_data_time,
    generated_at,
    price_factor: dict[str, Any],
    news_factor: dict[str, Any],
    fundamental_factor: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if fundamental_factor is None:
        fundamental_factor = {
            "score": 0.0, "direction": "neutral", "confidence_score": 0.0,
            "evidence_count": 0, "weight": 0.0,
        }

    weights = dynamic_weights(price_factor, news_factor, fundamental_factor)

    fusion_score = clip(
        price_factor["score"] * weights["price_baseline"]
        + news_factor["score"] * weights["news_event"]
        + fundamental_factor["score"] * weights["fundamental"]
    )

    stale_hours = (generated_at - as_of_data_time).total_seconds() / 3600
    stale_penalty = 0.10 if stale_hours > 36 else 0.0
    evidence_gap_penalty = 0.12 if news_factor["evidence_count"] == 0 and fundamental_factor["evidence_count"] == 0 else 0.0
    fusion_score = clip(fusion_score - stale_penalty - evidence_gap_penalty)

    active_degrade_flags: list[str] = []
    if news_factor["evidence_count"] == 0 and fundamental_factor["evidence_count"] == 0:
        active_degrade_flags.append("missing_news_evidence")
    if news_factor.get("conflict_ratio", 0) >= 0.45:
        active_degrade_flags.append("event_conflict_high")
    if stale_hours > 36:
        active_degrade_flags.append("market_data_stale")

    resolved_dir, conflict_notes = resolve_factor_conflict(
        price_factor["direction"], news_factor["direction"], fundamental_factor["direction"],
        price_factor["confidence_score"], news_factor["confidence_score"], fundamental_factor["confidence_score"],
    )

    confidence_score = clip(
        0.44
        + abs(fusion_score) * 0.28
        + price_factor["confidence_score"] * 0.08
        + news_factor["confidence_score"] * 0.08
        - stale_penalty * 0.2,
        0.0,
        0.9,
    )

    degraded = bool(active_degrade_flags)
    if resolved_dir == "positive":
        direction = recommendation_direction_with_degrade_flags(abs(fusion_score), active_degrade_flags)
        if direction == "watch":
            direction = "watch"
        else:
            direction = recommendation_direction(fusion_score, degraded)
    elif resolved_dir == "negative":
        direction = recommendation_direction(fusion_score, degraded)
    else:
        direction = recommendation_direction(fusion_score, True)

    return {
        "fusion_score": round(fusion_score, 4),
        "direction": direction,
        "confidence_score": round(confidence_score, 4),
        "active_degrade_flags": active_degrade_flags,
        "degraded": degraded,
        "effective_weights": weights,
        "conflict_notes": conflict_notes,
    }


def compute_model_results(
    *,
    symbol: str,
    as_of_data_time,
    price_factor: dict[str, Any],
    news_factor: dict[str, Any],
    manual_review_layer: dict[str, Any],
    fusion_state: dict[str, Any],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    ret_feature_by_horizon = {
        10: float(price_factor["feature_values"]["ret_10d"]),
        20: float(price_factor["feature_values"]["ret_20d"]),
        40: float(price_factor["feature_values"]["ret_40d"]),
    }

    for horizon_days in HORIZONS:
        horizon_scale = sqrt(horizon_days / PHASE2_PRIMARY_HORIZON)
        horizon_score = clip(
            fusion_state["fusion_score"] * (1.0 if horizon_days == PRIMARY_HORIZON else 0.94)
            + ret_feature_by_horizon[horizon_days] * 0.18
            + float(price_factor["feature_values"]["trend_component"]) * 0.08
            - float(price_factor["feature_values"]["risk_pressure"]) * 0.06
            - news_factor["conflict_ratio"] * 0.06,
        )
        expected_return = clip(horizon_score * (0.05 * horizon_scale), -0.15, 0.18)
        confidence_score = clip(
            0.45
            + abs(horizon_score) * 0.24
            + price_factor["confidence_score"] * 0.10
            + news_factor["confidence_score"] * 0.08,
            0.0,
            0.88,
        )
        direction = recommendation_direction(horizon_score, False)
        results.append(
            with_internal_lineage(
                {
                    "result_key": f"result-{symbol}-{as_of_data_time:%Y%m%d}-{horizon_days}d",
                    "stock_symbol": symbol,
                    "as_of_data_time": as_of_data_time,
                    "valid_until": as_of_data_time + timedelta(days=horizon_days),
                    "forecast_horizon_days": horizon_days,
                    "predicted_direction": direction,
                    "expected_return": round(expected_return, 4),
                    "confidence_score": round(confidence_score, 4),
                    "confidence_bucket": confidence_label(confidence_score),
                    "driver_factors": (price_factor["drivers"] + news_factor["drivers"])[:3],
                    "risk_factors": (news_factor["risks"] + manual_review_layer["risks"] + price_factor["risks"])[:3],
                    "result_payload": {
                        "factor_scores": {
                            "price_baseline": price_factor["score"],
                            "news_event": news_factor["score"],
                            "fusion": fusion_state["fusion_score"],
                        },
                        "validation_snapshot": {
                            **VALIDATION_PENDING,
                            "transaction_cost_bps": TRANSACTION_COST_BPS,
                            "validation_scheme": PHASE2_LABEL_DEFINITION,
                            "window_definition": PHASE2_WINDOW_DEFINITION,
                        },
                    },
                },
                source_uri=f"pipeline://signal-engine/model-result/{symbol}/{as_of_data_time:%Y%m%d}/{horizon_days}d",
            )
        )
    return results


def build_recommendation(
    *,
    symbol: str,
    stock_name: str,
    as_of_data_time,
    generated_at,
    price_factor: dict[str, Any],
    news_factor: dict[str, Any],
    manual_review_layer: dict[str, Any],
    model_results: list[dict[str, Any]],
    fusion_state: dict[str, Any],
    sector_proxy_available: bool,
    fundamental_factor: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if fundamental_factor is None:
        fundamental_factor = {
            "score": 0.0, "direction": "neutral", "confidence_score": 0.0,
            "drivers": [], "risks": [], "evidence_count": 0, "weight": 0.0,
            "feature_values": {"fundamental_score": 0.0, "available": False},
        }

    direction = str(fusion_state["direction"])
    confidence_score = float(fusion_state["confidence_score"])
    active_degrade_flags = list(fusion_state["active_degrade_flags"])
    effective_weights = fusion_state.get("effective_weights", dict(FUSION_WEIGHTS))
    primary_result = next(result for result in model_results if result["forecast_horizon_days"] == PRIMARY_HORIZON)

    core_drivers = []
    for text in price_factor["drivers"] + news_factor["drivers"] + fundamental_factor.get("drivers", []):
        if text not in core_drivers:
            core_drivers.append(text)

    reverse_risks = []
    for text in news_factor["risks"] + fundamental_factor.get("risks", []) + price_factor["risks"]:
        if text not in reverse_risks:
            reverse_risks.append(text)
    for note in fusion_state.get("conflict_notes", []):
        if note not in reverse_risks:
            reverse_risks.append(note)

    summary = actionable_summary(stock_name, direction,
                                  price_factor, news_factor, fundamental_factor)

    downgrade_conditions = [
        "近 10 日与 20 日动量同时跌回 0 以下时降级。",
        "7 日内新增负向公告/监管事件并使新闻因子转负时降级。",
        "价格与新闻方向冲突且冲突度超过 45% 时降级为风险提示。",
        "最新行情距离建议生成超过 36 小时未刷新时降级。",
    ]
    factor_breakdown = {
        "price_baseline": {
            "score": price_factor["score"],
            "weight": effective_weights.get("price_baseline", FUSION_WEIGHTS["price_baseline"]),
            "direction": price_factor["direction"],
            "confidence_score": price_factor["confidence_score"],
            "drivers": price_factor["drivers"],
            "risks": price_factor["risks"],
            "evidence_count": price_factor["evidence_count"],
            "components": {
                "trend_component": price_factor["feature_values"]["trend_component"],
                "confirmation_component": price_factor["feature_values"]["confirmation_component"],
                "risk_pressure": price_factor["feature_values"]["risk_pressure"],
            },
        },
        "news_event": {
            "score": news_factor["score"],
            "weight": effective_weights.get("news_event", FUSION_WEIGHTS["news_event"]),
            "direction": news_factor["direction"],
            "confidence_score": news_factor["confidence_score"],
            "drivers": news_factor["drivers"],
            "risks": news_factor["risks"],
            "evidence_count": news_factor["evidence_count"],
            "conflict_ratio": news_factor["conflict_ratio"],
        },
        "fundamental": {
            "score": fundamental_factor["score"],
            "weight": effective_weights.get("fundamental", FUSION_WEIGHTS.get("fundamental", 0.20)),
            "direction": fundamental_factor["direction"],
            "confidence_score": fundamental_factor["confidence_score"],
            "drivers": fundamental_factor.get("drivers", []),
            "risks": fundamental_factor.get("risks", []),
            "evidence_count": fundamental_factor.get("evidence_count", 0),
            "feature_values": fundamental_factor.get("feature_values", {}),
        },
        "manual_review_layer": {
            "score": manual_review_layer["score"],
            "direction": manual_review_layer["direction"],
            "confidence_score": manual_review_layer["confidence_score"],
            "drivers": manual_review_layer["drivers"],
            "risks": manual_review_layer["risks"],
            "status": manual_review_layer["status"],
            "calibration": manual_review_layer["calibration"],
        },
        "fusion": {
            "score": fusion_state["fusion_score"],
            "direction": direction,
            "confidence_score": confidence_score,
            "active_degrade_flags": active_degrade_flags,
            "effective_weights": effective_weights,
        },
    }
    factor_cards = [
        factor_card(
            factor_key,
            factor_payload=factor_payload,
            recommendation_direction_value=direction,
            degrade_flags=active_degrade_flags,
        )
        for factor_key, factor_payload in factor_breakdown.items()
    ]
    recommendation = with_internal_lineage(
        {
            "recommendation_key": f"reco-{symbol}-{as_of_data_time:%Y%m%d}-phase2",
            "stock_symbol": symbol,
            "as_of_data_time": as_of_data_time,
            "generated_at": generated_at,
            "direction": direction,
            "confidence_score": round(confidence_score, 4),
            "confidence_label": confidence_label(confidence_score),
            "horizon_min_days": min(HORIZONS),
            "horizon_max_days": max(HORIZONS),
            "evidence_status": "degraded" if fusion_state["degraded"] else "sufficient",
            "summary": summary,
            "core_drivers": core_drivers[:3],
            "risk_flags": reverse_risks[:3],
            "degrade_reason": "; ".join(active_degrade_flags) if active_degrade_flags else None,
            "recommendation_payload": {
                "policy": PHASE2_POLICY_VERSION,
                "confidence_expression": confidence_expression(
                    direction,
                    confidence_score,
                    fusion_state["degraded"],
                    degrade_flags=active_degrade_flags,
                ),
                "updated_at": generated_at.isoformat(),
                "downgrade_conditions": downgrade_conditions,
                "factor_breakdown": factor_breakdown,
                "validation_status": VALIDATION_PENDING["status"],
                "validation_note": VALIDATION_PENDING["note"],
                "primary_model_result_key": primary_result["result_key"],
                "validation_metrics_artifact_id": f"validation-metrics:{primary_result['result_key']}",
                "manual_review_summary_version": "manual_review_artifact:v1",
                "core_quant": {
                    "score": fusion_state["fusion_score"],
                    "score_scale": "phase2_rule_baseline_score",
                    "direction": direction,
                    "confidence_bucket": confidence_label(confidence_score),
                    "target_horizon_label": phase2_target_horizon_label(),
                    "horizon_min_days": min(HORIZONS),
                    "horizon_max_days": max(HORIZONS),
                    "as_of_time": json_datetime(as_of_data_time),
                    "available_time": json_datetime(generated_at),
                    "model_version": PHASE2_RULE_BASELINE,
                    "policy_version": PHASE2_POLICY_VERSION,
                },
                "evidence": {
                    "primary_drivers": core_drivers[:3],
                    "supporting_context": supporting_context(
                        news_factor=news_factor,
                        manual_review_layer=manual_review_layer,
                    ),
                    "conflicts": display_conflicts(news_factor, active_degrade_flags),
                    "degrade_flags": active_degrade_flags,
                    "data_freshness": f"当前分析基于 {as_of_data_time.isoformat()} 的数据快照生成。",
                    "source_links": [
                        f"pipeline://signal-engine/recommendation/{symbol}/{as_of_data_time:%Y%m%d}",
                        f"pipeline://signal-engine/model-result/{symbol}/{as_of_data_time:%Y%m%d}/{PRIMARY_HORIZON}d",
                    ],
                    "factor_cards": factor_cards,
                },
                "risk": {
                    "risk_flags": reverse_risks[:4],
                    "downgrade_conditions": downgrade_conditions,
                    "invalidators": downgrade_conditions[:3],
                    "coverage_gaps": [
                        VALIDATION_PENDING["note"],
                        "手动 Codex/GPT 研究会以 durable artifact 形式保留，但不进入核心评分。",
                    ],
                },
                "historical_validation": {
                    "status": VALIDATION_PENDING["status"],
                    "note": VALIDATION_PENDING["note"],
                    "artifact_type": "validation_metrics",
                    "artifact_id": f"validation-metrics:{primary_result['result_key']}",
                    "manifest_id": f"rolling-validation:{primary_result['result_key']}",
                    "artifact_generated_at": json_datetime(generated_at),
                    "label_definition": PHASE2_LABEL_DEFINITION,
                    "window_definition": PHASE2_WINDOW_DEFINITION,
                    "benchmark_definition": phase5_benchmark_definition(
                        market_proxy=True,
                        sector_proxy=sector_proxy_available,
                    ),
                    "cost_definition": PHASE2_COST_DEFINITION,
                    "metrics": {},
                },
                "manual_llm_review": {
                    "status": manual_review_layer["status"],
                    "trigger_mode": "manual",
                    "model_label": "Codex/GPT manual review",
                    "requested_at": None,
                    "generated_at": None,
                    "summary": PHASE2_MANUAL_REVIEW_NOTE,
                    "risks": [],
                    "disagreements": [],
                    "source_packet": [primary_result["result_key"]],
                    "artifact_id": None,
                    "question": None,
                    "raw_answer": None,
                },
            },
        },
        source_uri=f"pipeline://signal-engine/recommendation/{symbol}/{as_of_data_time:%Y%m%d}",
    )
    fusion_snapshot = with_internal_lineage(
        {
            "snapshot_key": f"feature-{symbol}-{as_of_data_time:%Y%m%d}-fusion-scorecard-v1",
            "stock_symbol": symbol,
            "feature_set_name": "fusion_scorecard",
            "feature_set_version": "phase2-rule-baseline-v1",
            "as_of": as_of_data_time,
            "window_start": primary_result["as_of_data_time"] - timedelta(days=max(HORIZONS)),
            "window_end": as_of_data_time,
            "feature_values": {
                "fusion_score": fusion_state["fusion_score"],
                "direction": direction,
                "confidence_score": round(confidence_score, 4),
                "active_degrade_flags": active_degrade_flags,
                "weights": FUSION_WEIGHTS,
            },
            "upstream_refs": [
                {"type": "feature_snapshot", "key": f"feature-{symbol}-{as_of_data_time:%Y%m%d}-price-baseline-v1"},
                {"type": "feature_snapshot", "key": f"feature-{symbol}-{as_of_data_time:%Y%m%d}-news-event-v1"},
                {"type": "feature_snapshot", "key": f"feature-{symbol}-{as_of_data_time:%Y%m%d}-manual-review-layer-v1"},
                {"type": "model_result", "key": primary_result["result_key"]},
            ],
        },
        source_uri=f"pipeline://signal-engine/fusion-scorecard/{symbol}/{as_of_data_time:%Y%m%d}",
    )
    return recommendation, fusion_snapshot


__all__ = [
    "build_recommendation",
    "compute_model_results",
]
