from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ashare_evidence.models import Recommendation, Stock
from ashare_evidence.recommendation_selection import collapse_recommendation_history, recommendation_recency_ordering
from ashare_evidence.research_artifacts import Phase5ProducerContractStudyArtifactView
from ashare_evidence.signal_engine_parts.base import (
    clip,
    recommendation_direction,
    recommendation_direction_with_degrade_flags,
)
from ashare_evidence.watchlist import active_watchlist_symbols

PHASE5_PRODUCER_CONTRACT_STUDY_VERSION = "phase5-producer-contract-study-draft-v1"
LONG_DIRECTIONS = {"buy", "watch"}
VARIANT_CURRENT_HARD_BLOCK = "current_hard_block"
VARIANT_REMOVE_HARD_OVERRIDE_KEEP_PENALTY = "remove_hard_override_keep_penalty"
VARIANT_WATCH_CEILING_KEEP_PENALTY = "watch_ceiling_keep_penalty"
VARIANT_REMOVE_HARD_OVERRIDE_AND_PENALTY = "remove_hard_override_and_penalty"
STUDY_VARIANT_IDS = (
    VARIANT_CURRENT_HARD_BLOCK,
    VARIANT_REMOVE_HARD_OVERRIDE_KEEP_PENALTY,
    VARIANT_WATCH_CEILING_KEEP_PENALTY,
    VARIANT_REMOVE_HARD_OVERRIDE_AND_PENALTY,
)


def _string_list(values: Any) -> list[str]:
    return [str(item) for item in values or [] if item]


def _latest_or_history_recommendations(
    session: Session,
    *,
    symbols: Sequence[str],
    include_history: bool,
) -> list[Recommendation]:
    recommendations = session.scalars(
        select(Recommendation)
        .join(Stock)
        .where(Stock.symbol.in_(symbols))
        .options(joinedload(Recommendation.stock))
        .order_by(*recommendation_recency_ordering(stock_symbol=True))
    ).all()
    by_symbol: dict[str, list[Recommendation]] = defaultdict(list)
    for recommendation in recommendations:
        by_symbol[recommendation.stock.symbol].append(recommendation)

    selected: list[Recommendation] = []
    for symbol in symbols:
        collapsed = collapse_recommendation_history(by_symbol.get(symbol, []))
        if include_history:
            selected.extend(collapsed)
        elif collapsed:
            selected.append(collapsed[0])
    return selected


def _build_record(recommendation: Recommendation) -> dict[str, Any]:
    payload = dict(recommendation.recommendation_payload or {})
    factor_breakdown = dict(payload.get("factor_breakdown") or {})
    evidence = dict(payload.get("evidence") or {})
    fusion = dict(factor_breakdown.get("fusion") or {})
    price_factor = dict(factor_breakdown.get("price_baseline") or {})
    news_factor = dict(factor_breakdown.get("news_event") or {})
    degrade_flags = _string_list(evidence.get("degrade_flags") or fusion.get("active_degrade_flags"))
    fusion_score = fusion.get("score")
    evidence_gap_penalty = fusion.get("evidence_gap_penalty", 0.0)

    exclusion_reason = None
    if not isinstance(fusion_score, (int, float)):
        exclusion_reason = "missing_fusion_score"
    elif not isinstance(evidence_gap_penalty, (int, float)):
        exclusion_reason = "missing_evidence_gap_penalty"

    return {
        "symbol": recommendation.stock.symbol,
        "name": recommendation.stock.name,
        "recommendation_key": recommendation.recommendation_key,
        "as_of_data_time": recommendation.as_of_data_time.isoformat(),
        "as_of_date": recommendation.as_of_data_time.date().isoformat(),
        "generated_at": recommendation.generated_at.isoformat(),
        "current_direction": recommendation.direction,
        "fusion_score": None if exclusion_reason else round(float(fusion_score), 4),
        "evidence_gap_penalty": None if exclusion_reason else round(float(evidence_gap_penalty), 4),
        "degrade_flags": degrade_flags,
        "price_direction": price_factor.get("direction"),
        "price_score": price_factor.get("score"),
        "news_direction": news_factor.get("direction"),
        "news_score": news_factor.get("score"),
        "news_evidence_count": news_factor.get("evidence_count"),
        "news_conflict_ratio": news_factor.get("conflict_ratio"),
        "include_in_aggregate": exclusion_reason is None,
        "exclusion_reason": exclusion_reason,
    }


def _variant_projection(record: dict[str, Any], variant_id: str) -> dict[str, Any]:
    degrade_flags = list(record["degrade_flags"])
    has_missing_news = "missing_news_evidence" in degrade_flags
    other_flags = [flag for flag in degrade_flags if flag != "missing_news_evidence"]
    adjusted_score = float(record["fusion_score"])

    if variant_id == VARIANT_REMOVE_HARD_OVERRIDE_AND_PENALTY and has_missing_news:
        adjusted_score = clip(adjusted_score + float(record["evidence_gap_penalty"]))

    effective_flags = degrade_flags
    if variant_id in {
        VARIANT_REMOVE_HARD_OVERRIDE_KEEP_PENALTY,
        VARIANT_REMOVE_HARD_OVERRIDE_AND_PENALTY,
    }:
        effective_flags = other_flags

    if variant_id == VARIANT_WATCH_CEILING_KEEP_PENALTY:
        direction = recommendation_direction_with_degrade_flags(adjusted_score, degrade_flags)
    else:
        direction = recommendation_direction(adjusted_score, bool(effective_flags))

    return {
        "variant_id": variant_id,
        "direction": direction,
        "adjusted_fusion_score": round(adjusted_score, 4),
        "effective_degrade_flags": effective_flags,
        "is_long_direction": direction in LONG_DIRECTIONS,
        "changes_direction": direction != record["current_direction"],
        "promoted_from_risk_alert": record["current_direction"] == "risk_alert" and direction in LONG_DIRECTIONS,
        "missing_news_only_buy": has_missing_news and not other_flags and direction == "buy",
    }


def _variant_summary(records: list[dict[str, Any]], variant_id: str) -> dict[str, Any]:
    direction_counts = Counter()
    changed_direction_count = 0
    promoted_from_risk_alert_count = 0
    missing_news_only_long_count = 0
    missing_news_only_buy_count = 0

    for record in records:
        projection = record["variants"][variant_id]
        direction_counts[projection["direction"]] += 1
        changed_direction_count += int(projection["changes_direction"])
        promoted_from_risk_alert_count += int(projection["promoted_from_risk_alert"])
        has_missing_only = "missing_news_evidence" in record["degrade_flags"] and len(record["degrade_flags"]) == 1
        missing_news_only_long_count += int(has_missing_only and projection["is_long_direction"])
        missing_news_only_buy_count += int(projection["missing_news_only_buy"])

    return {
        "variant_id": variant_id,
        "direction_counts": dict(direction_counts),
        "long_count": sum(direction_counts[item] for item in LONG_DIRECTIONS),
        "buy_count": direction_counts["buy"],
        "watch_count": direction_counts["watch"],
        "risk_alert_count": direction_counts["risk_alert"],
        "reduce_count": direction_counts["reduce"],
        "changed_direction_count": changed_direction_count,
        "promoted_from_risk_alert_count": promoted_from_risk_alert_count,
        "missing_news_only_long_count": missing_news_only_long_count,
        "missing_news_only_buy_count": missing_news_only_buy_count,
    }


def _symbol_summary(records: list[dict[str, Any]], variant_summaries: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_symbol[record["symbol"]].append(record)

    rows: list[dict[str, Any]] = []
    baseline = variant_summaries[VARIANT_CURRENT_HARD_BLOCK]
    _ = baseline
    for symbol, symbol_records in sorted(by_symbol.items()):
        variant_counts: dict[str, dict[str, int]] = {}
        for variant_id in STUDY_VARIANT_IDS:
            direction_counter = Counter(record["variants"][variant_id]["direction"] for record in symbol_records)
            variant_counts[variant_id] = {
                "buy": direction_counter["buy"],
                "watch": direction_counter["watch"],
                "risk_alert": direction_counter["risk_alert"],
                "reduce": direction_counter["reduce"],
                "long_count": direction_counter["buy"] + direction_counter["watch"],
            }
        rows.append(
            {
                "symbol": symbol,
                "name": symbol_records[0]["name"],
                "record_count": len(symbol_records),
                "missing_news_only_record_count": sum(
                    int("missing_news_evidence" in record["degrade_flags"] and len(record["degrade_flags"]) == 1)
                    for record in symbol_records
                ),
                "variant_direction_counts": variant_counts,
            }
        )
    return rows


def _decision(variant_summaries: dict[str, dict[str, Any]]) -> dict[str, Any]:
    current = variant_summaries[VARIANT_CURRENT_HARD_BLOCK]
    watch_ceiling = variant_summaries[VARIANT_WATCH_CEILING_KEEP_PENALTY]
    penalty_only = variant_summaries[VARIANT_REMOVE_HARD_OVERRIDE_KEEP_PENALTY]
    no_penalty = variant_summaries[VARIANT_REMOVE_HARD_OVERRIDE_AND_PENALTY]

    if watch_ceiling["long_count"] > current["long_count"] and watch_ceiling["missing_news_only_buy_count"] == 0:
        return {
            "recommended_variant_id": VARIANT_WATCH_CEILING_KEEP_PENALTY,
            "approval_state": "narrow_relaxation_recommended",
            "note": (
                "在当前候选方案里，保留 `0.12` evidence-gap penalty、去掉 "
                "`missing_news_evidence` 的硬性 `risk_alert` 覆盖，并把缺证据但其余条件偏正的记录上限收口到 `watch`，"
                "是最保守且能恢复 deployable supply 的替代方案。"
            ),
        }
    if penalty_only["long_count"] > current["long_count"] and penalty_only["missing_news_only_buy_count"] <= 1:
        return {
            "recommended_variant_id": VARIANT_REMOVE_HARD_OVERRIDE_KEEP_PENALTY,
            "approval_state": "hard_override_only_reconsider",
            "note": "当前数据已显示主要问题更像是硬性 `risk_alert` 覆盖，而不仅是 penalty；下一步可优先复核是否只去掉 override。",  # noqa: E501
        }
    if no_penalty["long_count"] > penalty_only["long_count"]:
        return {
            "recommended_variant_id": VARIANT_REMOVE_HARD_OVERRIDE_AND_PENALTY,
            "approval_state": "penalty_and_override_both_bind",
            "note": "若后续需要显著恢复 long supply，说明不仅硬覆盖，连 evidence-gap penalty 本身也值得继续复核。",  # noqa: E501
        }
    return {
        "recommended_variant_id": VARIANT_CURRENT_HARD_BLOCK,
        "approval_state": "current_contract_still_preferred",
        "note": "当前样本下，替代 contract 还没有在不放大 claim 风险的前提下明显改善 supply。",
    }


def build_phase5_producer_contract_study(
    session: Session,
    *,
    symbols: Sequence[str] | None = None,
    include_history: bool = True,
) -> dict[str, Any]:
    active_symbols = list(active_watchlist_symbols(session))
    scope_symbols = list(dict.fromkeys(symbols or active_symbols))
    if not scope_symbols:
        return {
            "generated_at": datetime.now().astimezone().isoformat(),
            "scope": {
                "symbols": [],
                "active_watchlist_symbols": active_symbols,
                "include_history": include_history,
                "selection_mode": "latest_per_symbol_as_of_day" if include_history else "latest_per_symbol",
            },
            "contract_version": PHASE5_PRODUCER_CONTRACT_STUDY_VERSION,
            "summary": {
                "included_record_count": 0,
                "excluded_record_count": 0,
                "missing_news_record_count": 0,
                "missing_news_only_record_count": 0,
            },
            "variants": [],
            "symbol_analysis": [],
            "focus_records": [],
            "decision": {
                "recommended_variant_id": VARIANT_CURRENT_HARD_BLOCK,
                "approval_state": "no_scope_symbols",
                "note": "当前没有可用于 producer-contract study 的 symbol scope。",
            },
        }

    selected = _latest_or_history_recommendations(
        session,
        symbols=scope_symbols,
        include_history=include_history,
    )
    records = [_build_record(recommendation) for recommendation in selected]
    included = [item for item in records if item["include_in_aggregate"]]
    excluded = [item for item in records if not item["include_in_aggregate"]]

    for record in included:
        record["variants"] = {
            variant_id: _variant_projection(record, variant_id)
            for variant_id in STUDY_VARIANT_IDS
        }

    variant_summaries = {
        variant_id: _variant_summary(included, variant_id)
        for variant_id in STUDY_VARIANT_IDS
    }
    symbol_analysis = _symbol_summary(included, variant_summaries)
    focus_records = [
        {
            "symbol": record["symbol"],
            "name": record["name"],
            "as_of_date": record["as_of_date"],
            "current_direction": record["current_direction"],
            "fusion_score": record["fusion_score"],
            "evidence_gap_penalty": record["evidence_gap_penalty"],
            "degrade_flags": list(record["degrade_flags"]),
            "price_direction": record["price_direction"],
            "news_direction": record["news_direction"],
            "news_evidence_count": record["news_evidence_count"],
            "variants": {
                variant_id: {
                    "direction": record["variants"][variant_id]["direction"],
                    "adjusted_fusion_score": record["variants"][variant_id]["adjusted_fusion_score"],
                }
                for variant_id in STUDY_VARIANT_IDS
            },
        }
        for record in included
        if "missing_news_evidence" in record["degrade_flags"]
    ]
    focus_records.sort(key=lambda item: (item["symbol"], item["as_of_date"]))

    return {
        "generated_at": datetime.now().astimezone().isoformat(),
        "scope": {
            "symbols": scope_symbols,
            "active_watchlist_symbols": active_symbols,
            "include_history": include_history,
            "selection_mode": "latest_per_symbol_as_of_day" if include_history else "latest_per_symbol",
        },
        "contract_version": PHASE5_PRODUCER_CONTRACT_STUDY_VERSION,
        "summary": {
            "included_record_count": len(included),
            "excluded_record_count": len(excluded),
            "missing_news_record_count": sum(
                int("missing_news_evidence" in record["degrade_flags"]) for record in included
            ),
            "missing_news_only_record_count": sum(
                int("missing_news_evidence" in record["degrade_flags"] and len(record["degrade_flags"]) == 1)
                for record in included
            ),
            "included_as_of_dates": sorted({str(record["as_of_date"]) for record in included if record.get("as_of_date")}),
        },
        "variants": [variant_summaries[variant_id] for variant_id in STUDY_VARIANT_IDS],
        "symbol_analysis": symbol_analysis,
        "focus_records": focus_records,
        "decision": _decision(variant_summaries),
    }


def phase5_producer_contract_study_artifact_id(payload: dict[str, Any]) -> str:
    scope = dict(payload.get("scope") or {})
    summary = dict(payload.get("summary") or {})
    symbols = list(scope.get("symbols") or [])
    include_history = bool(scope.get("include_history"))
    focus_records = list(payload.get("focus_records") or [])
    date_keys = sorted({str(item.get("as_of_date")) for item in focus_records if item.get("as_of_date")})
    if not date_keys:
        date_keys = [str(item) for item in summary.get("included_as_of_dates") or [] if item]
    if not date_keys:
        date_key = "no_dates"
    elif include_history:
        date_key = f"{date_keys[0]}_to_{date_keys[-1]}"
    else:
        date_key = date_keys[-1]
    mode = "history" if include_history else "latest"
    return f"phase5-producer-contract-study:{mode}:{date_key}:{len(symbols)}symbols"


def build_phase5_producer_contract_study_artifact(payload: dict[str, Any]) -> Phase5ProducerContractStudyArtifactView:
    return Phase5ProducerContractStudyArtifactView(
        artifact_id=phase5_producer_contract_study_artifact_id(payload),
        generated_at=datetime.fromisoformat(str(payload["generated_at"])),
        scope=dict(payload.get("scope") or {}),
        contract_version=str(payload["contract_version"]),
        summary=dict(payload.get("summary") or {}),
        variants=list(payload.get("variants") or []),
        symbol_analysis=list(payload.get("symbol_analysis") or []),
        focus_records=list(payload.get("focus_records") or []),
        decision=dict(payload.get("decision") or {}),
    )
