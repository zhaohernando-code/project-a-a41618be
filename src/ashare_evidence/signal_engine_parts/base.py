from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import tanh
from statistics import pstdev
from typing import Any

from ashare_evidence.contract_status import manual_review_placeholder, pending_rebuild_payload
from ashare_evidence.lineage import build_lineage
from ashare_evidence.phase2 import (
    PHASE2_COST_DEFINITION,
    PHASE2_COST_MODEL,
    PHASE2_HORIZONS,
    PHASE2_MANUAL_REVIEW_NOTE,
    PHASE2_POLICY_VERSION,
    PHASE2_PRIMARY_HORIZON,
    PHASE2_RULE_BASELINE,
)

HORIZONS = PHASE2_HORIZONS
PRIMARY_HORIZON = PHASE2_PRIMARY_HORIZON
TRANSACTION_COST_BPS = float(PHASE2_COST_MODEL["round_trip_cost_bps"])
VALIDATION_PENDING = pending_rebuild_payload()
MANUAL_REVIEW_PLACEHOLDER = manual_review_placeholder(PHASE2_MANUAL_REVIEW_NOTE)
FUSION_WEIGHTS = {
    "price_baseline": 0.35,
    "news_event": 0.20,
    "fundamental": 0.15,
    "size_factor": 0.10,
    "reversal": 0.10,
    "liquidity": 0.10,
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


def with_internal_lineage(
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


def clip(value: float, lower: float = -1.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def score_scale(value: float, scale: float) -> float:
    if scale == 0:
        return 0.0
    return clip(tanh(value / scale))


def safe_pstdev(values: list[float]) -> float:
    return pstdev(values) if len(values) > 1 else 0.0


def json_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def pct_change(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return current / previous - 1


def factor_direction(score: float, threshold: float = 0.08) -> str:
    if score >= threshold:
        return "positive"
    if score <= -threshold:
        return "negative"
    return "neutral"


def recommendation_direction(score: float, degraded: bool) -> str:
    if degraded:
        return "risk_alert"
    if score >= 0.28:
        return "buy"
    if score >= 0.12:
        return "add"
    if score <= -0.28:
        return "sell"
    if score <= -0.12:
        return "reduce"
    return "watch"


def recommendation_direction_with_degrade_flags(score: float, degrade_flags: list[str] | tuple[str, ...]) -> str:
    flags = [str(item) for item in degrade_flags if item]
    other_flags = [flag for flag in flags if flag != "missing_news_evidence"]
    if other_flags:
        return recommendation_direction(score, True)
    base_direction = recommendation_direction(score, False)
    if "missing_news_evidence" in flags and base_direction == "buy":
        return "watch"
    return base_direction


def confidence_label(score: float) -> str:
    if score >= 0.8:
        return "高"
    if score >= 0.66:
        return "中高"
    if score >= 0.52:
        return "中等"
    if score >= 0.38:
        return "中低"
    return "低"


def confidence_expression(
    direction: str,
    confidence_score: float,
    degraded: bool,
    *,
    degrade_flags: list[str] | tuple[str, ...] | None = None,
) -> str:
    label = confidence_label(confidence_score)
    flags = {str(item) for item in degrade_flags or [] if item}
    if degraded and flags == {"missing_news_evidence"}:
        return f"{label}置信，事件证据暂未补齐，当前更适合作为观察信号。"
    if degraded:
        return f"{label}置信，当前优先输出风险提示，等待结构化证据重新收敛。"
    if direction == "buy":
        return f"{label}置信，当前更适合作为 {PHASE2_RULE_BASELINE} 的 Phase 2 观察信号。"
    if direction == "reduce":
        return f"{label}置信，当前更适合降仓或等待反向确认。"
    return f"{label}置信，当前更适合继续观察而非强化动作。"


__all__ = [
    "FUSION_WEIGHTS",
    "HORIZONS",
    "MANUAL_REVIEW_PLACEHOLDER",
    "PHASE2_COST_DEFINITION",
    "PHASE2_POLICY_VERSION",
    "PHASE2_RULE_BASELINE",
    "PRIMARY_HORIZON",
    "SignalArtifacts",
    "TRANSACTION_COST_BPS",
    "VALIDATION_PENDING",
    "clip",
    "confidence_expression",
    "confidence_label",
    "factor_direction",
    "json_datetime",
    "pct_change",
    "recommendation_direction",
    "recommendation_direction_with_degrade_flags",
    "safe_pstdev",
    "score_scale",
    "with_internal_lineage",
]
