from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from datetime import date, datetime
from itertools import combinations
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ashare_evidence.models import Recommendation, Stock
from ashare_evidence.phase2.common import safe_mean
from ashare_evidence.phase2.constants import PHASE2_HORIZONS
from ashare_evidence.phase2.phase5_contract import (
    PHASE5_CONTRACT_VERSION,
    PHASE5_PRIMARY_HORIZON_STATUS,
    PHASE5_PRIMARY_RESEARCH_BENCHMARK,
    phase5_matches_primary_benchmark,
)
from ashare_evidence.research_artifacts import Phase5HorizonStudyArtifactView
from ashare_evidence.watchlist import active_watchlist_symbols

PHASE5_REQUIRED_BENCHMARK = PHASE5_PRIMARY_RESEARCH_BENCHMARK


def _mean_or_none(values: list[float | None]) -> float | None:
    filtered = [item for item in values if item is not None]
    if not filtered:
        return None
    return round(safe_mean(filtered), 6)


def _as_day(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _build_record(recommendation: Recommendation) -> dict[str, Any]:
    payload = dict(recommendation.recommendation_payload or {})
    historical_validation = dict(payload.get("historical_validation") or {})
    metrics = dict(historical_validation.get("metrics") or {})
    walk_forward = dict(metrics.get("walk_forward") or {})
    comparison = dict(metrics.get("candidate_horizon_comparison") or {})
    candidates = [
        {
            "rank": item.get("rank"),
            "horizon": item.get("horizon"),
            "artifact_id": item.get("artifact_id"),
            "sample_count": item.get("sample_count"),
            "net_excess_return": item.get("net_excess_return"),
            "rank_ic_mean": item.get("rank_ic_mean"),
            "positive_excess_rate": item.get("positive_excess_rate"),
            "turnover_mean": item.get("turnover_mean"),
        }
        for item in comparison.get("candidates") or []
        if isinstance(item, dict)
    ]
    candidates_by_horizon = {
        int(item["horizon"]): item
        for item in candidates
        if isinstance(item.get("horizon"), int)
    }
    leader = dict(comparison.get("recommended_research_leader") or {})
    exclusion_reason = None
    if comparison.get("contract_version") != PHASE5_CONTRACT_VERSION:
        exclusion_reason = "contract_mismatch"
    elif not phase5_matches_primary_benchmark(historical_validation.get("benchmark_definition")):
        exclusion_reason = "benchmark_mismatch"
    elif walk_forward.get("coverage_status") != "full_baseline":
        exclusion_reason = "coverage_not_full_baseline"
    elif comparison.get("selection_readiness") != "comparison_ready":
        exclusion_reason = "selection_not_ready"
    elif not candidates or not isinstance(leader.get("horizon"), int):
        exclusion_reason = "missing_candidate_comparison"

    return {
        "symbol": recommendation.stock.symbol,
        "name": recommendation.stock.name,
        "generated_at": recommendation.generated_at.isoformat(),
        "as_of_data_time": recommendation.as_of_data_time.isoformat(),
        "as_of_date": recommendation.as_of_data_time.date().isoformat(),
        "recommendation_key": recommendation.recommendation_key,
        "benchmark_definition": historical_validation.get("benchmark_definition"),
        "contract_version": comparison.get("contract_version"),
        "coverage_status": walk_forward.get("coverage_status"),
        "selection_readiness": comparison.get("selection_readiness"),
        "primary_horizon_status": comparison.get("primary_horizon_status"),
        "leader_horizon": leader.get("horizon"),
        "leader_rank": leader.get("rank"),
        "walk_forward_window_count": comparison.get("walk_forward_window_count"),
        "candidates": candidates,
        "candidates_by_horizon": candidates_by_horizon,
        "include_in_aggregate": exclusion_reason is None,
        "exclusion_reason": exclusion_reason,
    }


def build_phase5_horizon_study(
    session: Session,
    *,
    symbols: Sequence[str] | None = None,
    include_history: bool = False,
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
            "contract_version": PHASE5_CONTRACT_VERSION,
            "primary_horizon_status": PHASE5_PRIMARY_HORIZON_STATUS,
            "summary": {
                "included_record_count": 0,
                "excluded_record_count": 0,
                "included_symbol_count": 0,
                "included_as_of_date_count": 0,
            },
            "leaderboard": [],
            "pairwise_net_excess": [],
            "time_stability": {
                "symbol_count": 0,
                "stable_symbol_count": 0,
                "unstable_symbol_count": 0,
                "symbols": [],
            },
            "decision": {
                "approval_state": "no_scope_symbols",
                "candidate_frontier": [],
                "lagging_horizons": [],
                "note": "当前没有可用于 Phase 5 horizon study 的 symbol scope。",
            },
            "records": [],
        }

    recommendations = session.scalars(
        select(Recommendation)
        .join(Stock)
        .where(Stock.symbol.in_(scope_symbols))
        .options(joinedload(Recommendation.stock))
        .order_by(Stock.symbol.asc(), Recommendation.as_of_data_time.desc(), Recommendation.generated_at.desc())
    ).all()

    selected: list[Recommendation] = []
    seen_keys: set[tuple[str, str] | tuple[str]] = set()
    for recommendation in recommendations:
        symbol = recommendation.stock.symbol
        key: tuple[str, str] | tuple[str]
        if include_history:
            key = (symbol, recommendation.as_of_data_time.date().isoformat())
        else:
            key = (symbol,)
        if key in seen_keys:
            continue
        selected.append(recommendation)
        seen_keys.add(key)

    records = [_build_record(recommendation) for recommendation in selected]
    included = [item for item in records if item["include_in_aggregate"]]
    excluded = [item for item in records if not item["include_in_aggregate"]]

    leaderboard: list[dict[str, Any]] = []
    pairwise_rows: list[dict[str, Any]] = []
    horizons = list(PHASE2_HORIZONS)
    for horizon in horizons:
        horizon_candidates = [
            item["candidates_by_horizon"].get(horizon)
            for item in included
            if item["candidates_by_horizon"].get(horizon) is not None
        ]
        leader_count = sum(1 for item in included if item.get("leader_horizon") == horizon)
        leaderboard.append(
            {
                "horizon": horizon,
                "leader_count": leader_count,
                "leader_share": round(leader_count / len(included), 6) if included else 0.0,
                "mean_net_excess_return": _mean_or_none(
                    [item.get("net_excess_return") for item in horizon_candidates]
                ),
                "mean_rank_ic_mean": _mean_or_none(
                    [item.get("rank_ic_mean") for item in horizon_candidates]
                ),
                "mean_positive_excess_rate": _mean_or_none(
                    [item.get("positive_excess_rate") for item in horizon_candidates]
                ),
            }
        )

    leaderboard.sort(
        key=lambda item: (
            item["leader_count"],
            item["mean_net_excess_return"] if item["mean_net_excess_return"] is not None else float("-inf"),
            item["mean_rank_ic_mean"] if item["mean_rank_ic_mean"] is not None else float("-inf"),
            item["mean_positive_excess_rate"] if item["mean_positive_excess_rate"] is not None else float("-inf"),
        ),
        reverse=True,
    )

    pairwise_win_counter: Counter[int] = Counter()
    for left_horizon, right_horizon in combinations(horizons, 2):
        left_wins = 0
        right_wins = 0
        ties = 0
        spreads: list[float] = []
        sample_count = 0
        for item in included:
            left_candidate = item["candidates_by_horizon"].get(left_horizon)
            right_candidate = item["candidates_by_horizon"].get(right_horizon)
            if left_candidate is None or right_candidate is None:
                continue
            left_value = left_candidate.get("net_excess_return")
            right_value = right_candidate.get("net_excess_return")
            if left_value is None or right_value is None:
                continue
            spread = round(float(left_value) - float(right_value), 6)
            spreads.append(spread)
            sample_count += 1
            if spread > 0:
                left_wins += 1
                pairwise_win_counter[left_horizon] += 1
            elif spread < 0:
                right_wins += 1
                pairwise_win_counter[right_horizon] += 1
            else:
                ties += 1
        pairwise_rows.append(
            {
                "left_horizon": left_horizon,
                "right_horizon": right_horizon,
                "sample_count": sample_count,
                "left_wins": left_wins,
                "right_wins": right_wins,
                "ties": ties,
                "mean_net_excess_spread": _mean_or_none(spreads),
            }
        )

    stability_rows: list[dict[str, Any]] = []
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in included:
        by_symbol[item["symbol"]].append(item)
    for symbol, symbol_rows in sorted(by_symbol.items()):
        leaders = sorted({int(item["leader_horizon"]) for item in symbol_rows if isinstance(item["leader_horizon"], int)})
        as_of_dates = sorted({item["as_of_date"] for item in symbol_rows})
        stability_rows.append(
            {
                "symbol": symbol,
                "name": symbol_rows[0]["name"],
                "snapshot_count": len(symbol_rows),
                "as_of_dates": as_of_dates,
                "leader_horizons": leaders,
                "is_stable": len(leaders) == 1,
            }
        )

    candidate_frontier = [int(item["horizon"]) for item in leaderboard if item["leader_count"] > 0]
    lagging_horizons = sorted(
        int(item["horizon"])
        for item in leaderboard
        if item["leader_count"] == 0 and pairwise_win_counter[int(item["horizon"])] == 0
    )

    if not included:
        approval_state = "insufficient_phase5_evidence"
        note = "当前 scope 内没有满足 Phase 5 contract、active watchlist 等权 benchmark 和 full-baseline coverage 的 candidate comparison。"
    else:
        front_runner = leaderboard[0]
        if front_runner["leader_count"] == len(included):
            approval_state = "consensus_front_runner"
            note = f"{front_runner['horizon']}d 在当前 scope 内对所有纳入记录都保持 leader，可继续评估是否满足主 horizon 审批条件。"
        elif len(candidate_frontier) >= 2:
            approval_state = "split_leadership"
            note = (
                f"{candidate_frontier[0]}d 与 {candidate_frontier[1]}d 之间仍然存在 split leadership；"
                f"{', '.join(f'{item}d' for item in lagging_horizons) or '其余 horizon'} 可以继续视为劣后候选。"
            )
        else:
            approval_state = "single_front_runner_not_yet_consensus"
            note = (
                f"{front_runner['horizon']}d 当前是唯一 front runner，但 leader coverage 仍不足以解除 "
                f"{PHASE5_PRIMARY_HORIZON_STATUS}。"
            )

    return {
        "generated_at": datetime.now().astimezone().isoformat(),
        "scope": {
            "symbols": scope_symbols,
            "active_watchlist_symbols": active_symbols,
            "include_history": include_history,
            "selection_mode": "latest_per_symbol_as_of_day" if include_history else "latest_per_symbol",
        },
        "contract_version": PHASE5_CONTRACT_VERSION,
        "required_benchmark_definition": PHASE5_REQUIRED_BENCHMARK,
        "primary_horizon_status": PHASE5_PRIMARY_HORIZON_STATUS,
        "summary": {
            "selected_record_count": len(records),
            "included_record_count": len(included),
            "excluded_record_count": len(excluded),
            "included_symbol_count": len({item["symbol"] for item in included}),
            "included_as_of_date_count": len({item["as_of_date"] for item in included}),
            "excluded_reasons": dict(Counter(item["exclusion_reason"] for item in excluded)),
        },
        "leaderboard": leaderboard,
        "pairwise_net_excess": pairwise_rows,
        "time_stability": {
            "symbol_count": len(stability_rows),
            "stable_symbol_count": sum(1 for item in stability_rows if item["is_stable"]),
            "unstable_symbol_count": sum(1 for item in stability_rows if not item["is_stable"]),
            "symbols": stability_rows,
        },
        "decision": {
            "approval_state": approval_state,
            "candidate_frontier": candidate_frontier,
            "lagging_horizons": lagging_horizons,
            "note": note,
        },
        "records": [
            {
                key: value
                for key, value in item.items()
                if key != "candidates_by_horizon"
            }
            for item in records
        ],
    }


def phase5_horizon_study_artifact_id(payload: dict[str, Any]) -> str:
    scope = dict(payload.get("scope") or {})
    summary = dict(payload.get("summary") or {})
    records = list(payload.get("records") or [])
    included_dates = sorted(
        {
            str(item.get("as_of_date"))
            for item in records
            if item.get("include_in_aggregate") and item.get("as_of_date")
        }
    )
    if included_dates:
        date_key = included_dates[0] if len(included_dates) == 1 else f"{included_dates[0]}_to_{included_dates[-1]}"
    else:
        date_key = "no_included_dates"
    mode = "history" if scope.get("include_history") else "latest"
    scope_kind = "custom" if scope.get("symbols") != scope.get("active_watchlist_symbols") else "active_watchlist"
    symbol_count = int(summary.get("included_symbol_count") or 0)
    return f"phase5-horizon-study:{mode}:{scope_kind}:{date_key}:{symbol_count}symbols"


def build_phase5_horizon_study_artifact(payload: dict[str, Any]) -> Phase5HorizonStudyArtifactView:
    return Phase5HorizonStudyArtifactView(
        artifact_id=phase5_horizon_study_artifact_id(payload),
        generated_at=datetime.fromisoformat(str(payload["generated_at"])),
        created_at=datetime.fromisoformat(str(payload["generated_at"])),
        scope=dict(payload.get("scope") or {}),
        contract_version=str(payload.get("contract_version") or PHASE5_CONTRACT_VERSION),
        required_benchmark_definition=str(payload.get("required_benchmark_definition") or PHASE5_REQUIRED_BENCHMARK),
        primary_horizon_status=str(payload.get("primary_horizon_status") or PHASE5_PRIMARY_HORIZON_STATUS),
        summary=dict(payload.get("summary") or {}),
        leaderboard=[dict(item) for item in payload.get("leaderboard") or []],
        pairwise_net_excess=[dict(item) for item in payload.get("pairwise_net_excess") or []],
        time_stability=dict(payload.get("time_stability") or {}),
        decision=dict(payload.get("decision") or {}),
        records=[dict(item) for item in payload.get("records") or []],
    )
