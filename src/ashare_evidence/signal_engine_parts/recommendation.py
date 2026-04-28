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

PLACEHOLDER_FUSION_HEADLINE = "用于汇总价格、事件与降级状态的融合层。"
DEGRADE_FLAG_DISPLAY = {
    "missing_news_evidence": "近期缺少新增事件证据，当前更多依赖价格趋势观察。",
    "event_conflict_high": "价格与事件方向冲突较高，系统已主动下调对外表达。",
    "market_data_stale": "最新行情刷新偏旧，短线结论需要谨慎使用。",
}


def _display_ready_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text == PLACEHOLDER_FUSION_HEADLINE or "Phase 2 规则基线" in text:
        return None
    return text


def _humanize_degrade_flag(flag: str) -> str:
    cleaned = str(flag).strip()
    if not cleaned:
        return ""
    return DEGRADE_FLAG_DISPLAY.get(cleaned, cleaned.replace("_", " "))


def _factor_headline_fallback(
    factor_key: str,
    *,
    factor_payload: dict[str, Any],
    recommendation_direction_value: str,
    degrade_flags: list[str],
) -> str:
    direction = str(factor_payload.get("direction") or "")
    evidence_count = factor_payload.get("evidence_count")
    conflict_ratio = factor_payload.get("conflict_ratio")
    if factor_key == "price_baseline":
        if direction == "positive":
            return "近端价格趋势仍偏强，量价确认暂未转弱。"
        if direction == "negative":
            return "价格趋势已经转弱，短线确认项同步回落。"
        return "价格趋势暂未形成单边优势，仍需等待新的量价确认。"
    if factor_key == "news_event":
        if isinstance(evidence_count, (int, float)) and evidence_count <= 0:
            return "近期缺少新增高置信事件，当前更多依赖价格趋势观察。"
        if isinstance(conflict_ratio, (int, float)) and float(conflict_ratio) >= 0.45:
            return "近期事件正负并存且冲突较高，暂时不适合放大解读。"
        if direction == "positive":
            return "近期公告与行业催化偏正向，正在为价格趋势补充证据。"
        if direction == "negative":
            return "近期负向公告或行业扰动增多，事件层开始压制判断。"
        return "事件层暂未形成一致方向，更多用于验证风险是否扩大。"
    if factor_key == "manual_review_layer":
        return "人工研究结论会单独展示，当前只作为补充解释，不直接进入量化评分。"
    if "market_data_stale" in degrade_flags:
        return "最新行情刷新偏旧，当前结论先保留在观察区间。"
    if "event_conflict_high" in degrade_flags:
        return "价格与事件信号分歧较大，系统先下调对外表达。"
    if "missing_news_evidence" in degrade_flags:
        return "近期缺少新增事件证据，当前主要依赖价格趋势延续。"
    if recommendation_direction_value == "buy":
        return "价格与事件暂时同向，综合后维持偏积极观察。"
    if recommendation_direction_value in {"reduce", "risk_alert"}:
        return "综合价格与事件后，当前更适合偏谨慎处理。"
    return "价格与事件综合后暂未形成可放大的单边结论。"


def _factor_risk_fallback(
    factor_key: str,
    *,
    factor_payload: dict[str, Any],
    degrade_flags: list[str],
) -> str | None:
    conflict_ratio = factor_payload.get("conflict_ratio")
    if factor_key == "price_baseline":
        return "若 10 日与 20 日动量继续下行，价格基线会优先转弱。"
    if factor_key == "news_event":
        if isinstance(conflict_ratio, (int, float)) and float(conflict_ratio) >= 0.35:
            return "事件冲突仍偏高，新增负面消息会更快触发降级。"
        return "若后续事件方向反转，事件层会率先削弱当前判断。"
    if factor_key == "manual_review_layer":
        return "人工研究仍需补充正式记录后才能作为稳定参考。"
    if degrade_flags:
        return _humanize_degrade_flag(degrade_flags[0])
    return "如果价格与事件继续背离，综合层会优先收缩对外表达。"


def _factor_card(
    factor_key: str,
    *,
    factor_payload: dict[str, Any],
    recommendation_direction_value: str,
    degrade_flags: list[str],
) -> dict[str, Any]:
    return {
        "factor_key": factor_key,
        "score": factor_payload.get("score"),
        "direction": factor_payload.get("direction"),
        "headline": (
            next(
                (text for item in factor_payload.get("drivers") or [] if (text := _display_ready_text(item))),
                None,
            )
            or _factor_headline_fallback(
                factor_key,
                factor_payload=factor_payload,
                recommendation_direction_value=recommendation_direction_value,
                degrade_flags=degrade_flags,
            )
        ),
        "risk_note": (
            next(
                (text for item in factor_payload.get("risks") or [] if (text := _display_ready_text(item))),
                None,
            )
            or _factor_risk_fallback(
                factor_key,
                factor_payload=factor_payload,
                degrade_flags=degrade_flags,
            )
        ),
        "status": factor_payload.get("status"),
    }


def _supporting_context(
    *,
    news_factor: dict[str, Any],
    manual_review_layer: dict[str, Any],
) -> list[str]:
    context = ["价格层仍是当前判断的主轴，近期趋势和量价确认决定了大部分方向。"]
    evidence_count = news_factor.get("evidence_count")
    conflict_ratio = news_factor.get("conflict_ratio")
    if isinstance(evidence_count, (int, float)) and evidence_count <= 0:
        context.append("近期没有新增高置信事件，当前更多依赖价格趋势是否延续。")
    elif isinstance(conflict_ratio, (int, float)) and float(conflict_ratio) >= 0.35:
        context.append("事件层存在正负并存的情况，需要继续观察冲突是否扩大。")
    else:
        context.append("事件层主要用于确认价格趋势是否得到新的公告或行业催化支撑。")
    if manual_review_layer.get("status"):
        context.append("人工研究结论单独展示，当前只作为补充解释，不直接改变量化评分。")
    return context


def _display_conflicts(news_factor: dict[str, Any], active_degrade_flags: list[str]) -> list[str]:
    conflicts: list[str] = []
    if news_factor["conflict_ratio"] > 0:
        conflicts.append(f"新闻事件冲突度 {news_factor['conflict_ratio']:.0%}。")
    conflicts.extend(
        humanized
        for humanized in (_humanize_degrade_flag(flag) for flag in active_degrade_flags)
        if humanized
    )
    return conflicts


def _fusion_state(
    *,
    as_of_data_time,
    generated_at,
    price_factor: dict[str, Any],
    news_factor: dict[str, Any],
) -> dict[str, Any]:
    conflict_penalty = 0.0
    if price_factor["direction"] != "neutral" and news_factor["direction"] != "neutral" and price_factor["direction"] != news_factor["direction"]:
        conflict_penalty = 0.12
    conflict_penalty += news_factor["conflict_ratio"] * 0.08

    stale_hours = (generated_at - as_of_data_time).total_seconds() / 3600
    stale_penalty = 0.1 if stale_hours > 36 else 0.0
    evidence_gap_penalty = 0.12 if news_factor["evidence_count"] == 0 else 0.0
    fusion_score = clip(
        price_factor["score"] * FUSION_WEIGHTS["price_baseline"]
        + news_factor["score"] * FUSION_WEIGHTS["news_event"]
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

    confidence_score = clip(
        0.44
        + abs(fusion_score) * 0.28
        + price_factor["confidence_score"] * 0.08
        + news_factor["confidence_score"] * 0.08
        - conflict_penalty * 0.3
        - stale_penalty * 0.2,
        0.0,
        0.9,
    )
    degraded = bool(active_degrade_flags)
    direction = recommendation_direction_with_degrade_flags(fusion_score, active_degrade_flags)
    return {
        "fusion_score": round(fusion_score, 4),
        "direction": direction,
        "confidence_score": round(confidence_score, 4),
        "conflict_penalty": round(conflict_penalty, 4),
        "stale_penalty": round(stale_penalty, 4),
        "evidence_gap_penalty": round(evidence_gap_penalty, 4),
        "active_degrade_flags": active_degrade_flags,
        "degraded": degraded,
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
) -> tuple[dict[str, Any], dict[str, Any]]:
    direction = str(fusion_state["direction"])
    confidence_score = float(fusion_state["confidence_score"])
    active_degrade_flags = list(fusion_state["active_degrade_flags"])
    primary_result = next(result for result in model_results if result["forecast_horizon_days"] == PRIMARY_HORIZON)
    core_drivers = []
    reverse_risks = []
    for text in price_factor["drivers"] + news_factor["drivers"]:
        if text not in core_drivers:
            core_drivers.append(text)
    for text in news_factor["risks"] + price_factor["risks"]:
        if text not in reverse_risks:
            reverse_risks.append(text)

    summary = (
        f"{stock_name} 当前主要依据价格趋势与事件证据形成偏正判断，融合分数 {fusion_state['fusion_score']:.2f}，"
        f"按 Phase 2 的 10/20/40 交易日前瞻超额收益窗口继续跟踪。"
        if direction == "buy"
        else f"{stock_name} 当前证据仍有分歧，融合分数 {fusion_state['fusion_score']:.2f}，先以观察或风险提示为主。"
    )
    downgrade_conditions = [
        "近 10 日与 20 日动量同时跌回 0 以下时降级。",
        "7 日内新增负向公告/监管事件并使新闻因子转负时降级。",
        "价格与新闻方向冲突且冲突度超过 45% 时降级为风险提示。",
        "最新行情距离建议生成超过 36 小时未刷新时降级。",
        "手动 Codex/GPT 研究结论只保留在解释层，不得直接上升为核心驱动。",
    ]
    factor_breakdown = {
        "price_baseline": {
            "score": price_factor["score"],
            "weight": FUSION_WEIGHTS["price_baseline"],
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
            "weight": FUSION_WEIGHTS["news_event"],
            "direction": news_factor["direction"],
            "confidence_score": news_factor["confidence_score"],
            "drivers": news_factor["drivers"],
            "risks": news_factor["risks"],
            "evidence_count": news_factor["evidence_count"],
            "conflict_ratio": news_factor["conflict_ratio"],
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
            "conflict_penalty": fusion_state["conflict_penalty"],
            "stale_penalty": fusion_state["stale_penalty"],
            "evidence_gap_penalty": fusion_state["evidence_gap_penalty"],
            "active_degrade_flags": active_degrade_flags,
        },
    }
    factor_cards = [
        _factor_card(
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
                    "supporting_context": _supporting_context(
                        news_factor=news_factor,
                        manual_review_layer=manual_review_layer,
                    ),
                    "conflicts": _display_conflicts(news_factor, active_degrade_flags),
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
