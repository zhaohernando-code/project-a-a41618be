from __future__ import annotations

from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ashare_evidence.models import MarketBar, PaperPortfolio, Recommendation, Stock
from ashare_evidence.phase2.common import build_equal_weight_proxy, safe_mean
from ashare_evidence.phase2.constants import PHASE2_COST_MODEL
from ashare_evidence.phase2.phase5_contract import (
    PHASE5_ACTION_DEFINITION,
    PHASE5_BOARD_LOT,
    PHASE5_CONTRACT_VERSION,
    PHASE5_HOLDING_POLICY_REDESIGN_EXPERIMENT_MENU,
    PHASE5_LONG_DIRECTIONS,
    PHASE5_MAX_POSITION_COUNT,
    PHASE5_MAX_SINGLE_WEIGHT,
    PHASE5_PRIMARY_RESEARCH_BENCHMARK,
    PHASE5_QUANTITY_DEFINITION,
    PHASE5_SIMULATION_POLICY,
)
from ashare_evidence.research_artifacts import Phase5HoldingPolicyExperimentArtifactView
from ashare_evidence.simulation import DEFAULT_INITIAL_CASH
from ashare_evidence.watchlist import active_watchlist_symbols

PHASE5_HOLDING_POLICY_EXPERIMENT_VERSION = "phase5-holding-policy-experiment-v1"
TRADING_DAYS_PER_YEAR = 252


@dataclass(frozen=True)
class PolicyVariant:
    variant_id: str
    label: str
    max_position_count: int
    max_single_weight: float
    min_confidence_score: float
    long_directions: frozenset[str]
    note: str


@dataclass(frozen=True)
class AvailableRecommendation:
    symbol: str
    available_day: date
    as_of_day: date
    generated_at: datetime
    direction: str
    confidence_score: float
    confidence_label: str
    score: int
    recommendation_key: str


def _mean_or_none(values: list[float | None]) -> float | None:
    filtered = [float(item) for item in values if item is not None]
    if not filtered:
        return None
    return round(safe_mean(filtered), 6)


def _annualized_return(total_return: float, day_count: int) -> float | None:
    if day_count <= 0:
        return None
    return round((1.0 + float(total_return)) ** (TRADING_DAYS_PER_YEAR / float(day_count)) - 1.0, 6)


def _model_direction_priority(direction: str) -> int:
    return {
        "buy": 4,
        "watch": 3,
        "reduce": 2,
        "risk_alert": 1,
    }.get(direction, 0)


def _model_advice_score(direction: str, confidence_score: float) -> int:
    return _model_direction_priority(direction) * 100 + int(float(confidence_score) * 100)


def _round_down_board_lot(quantity: int) -> int:
    if quantity <= 0:
        return 0
    return int(quantity // PHASE5_BOARD_LOT * PHASE5_BOARD_LOT)


def _board_lot_quantity_for_target_value(target_value: float, price: float) -> int:
    if target_value <= 0 or price <= 0:
        return 0
    return _round_down_board_lot(int(target_value / price))


def _current_weights(
    *,
    positions: dict[str, int],
    price_map: dict[str, float],
    nav: float,
) -> dict[str, float]:
    if nav <= 0:
        return {}
    return {
        symbol: round(float(quantity) * float(price_map[symbol]) / nav, 6)
        for symbol, quantity in positions.items()
        if quantity > 0 and symbol in price_map
    }


def _phase5_policy_targets(
    candidates: list[dict[str, Any]],
    *,
    nav: float,
    variant: PolicyVariant,
) -> dict[str, dict[str, Any]]:
    if nav <= 0:
        return {}
    target_value = nav * variant.max_single_weight
    ranked = sorted(
        (
            item
            for item in candidates
            if item["direction"] in variant.long_directions
            and float(item["confidence_score"]) >= variant.min_confidence_score
            and _board_lot_quantity_for_target_value(target_value, float(item["reference_price"])) >= PHASE5_BOARD_LOT
        ),
        key=lambda item: (-_model_direction_priority(str(item["direction"])), -int(item["score"]), str(item["symbol"])),
    )
    selected = ranked[: variant.max_position_count]
    targets: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(selected, start=1):
        target_quantity = _board_lot_quantity_for_target_value(target_value, float(item["reference_price"]))
        actual_weight = 0.0 if nav <= 0 else round(target_quantity * float(item["reference_price"]) / nav, 6)
        targets[str(item["symbol"])] = {
            "target_weight": actual_weight,
            "target_quantity": target_quantity,
            "rank": index,
            "direction": item["direction"],
            "confidence_score": float(item["confidence_score"]),
        }
    return targets


def _variant_grid(experiment_id: str) -> list[PolicyVariant]:
    baseline = PolicyVariant(
        variant_id="baseline_top5_weight20_conf0",
        label="Baseline 5x20%",
        max_position_count=PHASE5_MAX_POSITION_COUNT,
        max_single_weight=PHASE5_MAX_SINGLE_WEIGHT,
        min_confidence_score=0.0,
        long_directions=frozenset(PHASE5_LONG_DIRECTIONS),
        note="Current Phase 5 simulation baseline: top-5 long directions, 20% cap, no extra confidence floor.",
    )
    if experiment_id == "profitability_signal_threshold_sweep_v1":
        return [
            baseline,
            PolicyVariant(
                variant_id="threshold_conf65_top5_weight20",
                label="Threshold >= 0.65",
                max_position_count=PHASE5_MAX_POSITION_COUNT,
                max_single_weight=PHASE5_MAX_SINGLE_WEIGHT,
                min_confidence_score=0.65,
                long_directions=frozenset(PHASE5_LONG_DIRECTIONS),
                note="Raise the entry floor to confidence >= 0.65 while keeping the baseline capacity unchanged.",
            ),
            PolicyVariant(
                variant_id="threshold_conf70_top5_weight20",
                label="Threshold >= 0.70",
                max_position_count=PHASE5_MAX_POSITION_COUNT,
                max_single_weight=PHASE5_MAX_SINGLE_WEIGHT,
                min_confidence_score=0.70,
                long_directions=frozenset(PHASE5_LONG_DIRECTIONS),
                note="Only allow the strongest long recommendations to enter the overnight target portfolio.",
            ),
        ]
    if experiment_id == "construction_max_position_count_sweep_v1":
        return [
            PolicyVariant(
                variant_id="capacity_top3_weight33_conf0",
                label="Top 3 x 33%",
                max_position_count=3,
                max_single_weight=round(1.0 / 3.0, 6),
                min_confidence_score=0.0,
                long_directions=frozenset(PHASE5_LONG_DIRECTIONS),
                note="Concentrate into the highest-ranked three names with equal-weight sizing.",
            ),
            baseline,
            PolicyVariant(
                variant_id="capacity_top7_weight14_conf0",
                label="Top 7 x 14%",
                max_position_count=7,
                max_single_weight=round(1.0 / 7.0, 6),
                min_confidence_score=0.0,
                long_directions=frozenset(PHASE5_LONG_DIRECTIONS),
                note="Broaden capacity and reduce per-name cap to test whether exposure improves with a wider basket.",
            ),
        ]
    raise ValueError(f"unsupported holding-policy experiment id: {experiment_id}")


def _variant_baseline_id(experiment_id: str) -> str:
    for variant in _variant_grid(experiment_id):
        if variant.variant_id == "baseline_top5_weight20_conf0":
            return variant.variant_id
    raise ValueError(f"baseline variant missing for {experiment_id}")


def _daily_close_maps(
    session: Session,
    *,
    symbols: Sequence[str],
) -> dict[str, dict[date, float]]:
    if not symbols:
        return {}
    bars = session.scalars(
        select(MarketBar)
        .join(Stock)
        .where(Stock.symbol.in_(symbols), MarketBar.timeframe == "1d")
        .options(joinedload(MarketBar.stock))
        .order_by(Stock.symbol.asc(), MarketBar.observed_at.asc())
    ).all()
    close_maps: dict[str, dict[date, float]] = {}
    for bar in bars:
        close_maps.setdefault(bar.stock.symbol, {})[bar.observed_at.date()] = float(bar.close_price)
    return close_maps


def _auto_model_starting_cash(session: Session) -> float:
    portfolios = session.scalars(
        select(PaperPortfolio)
        .where(PaperPortfolio.mode == "auto_model", PaperPortfolio.status != "archived")
        .order_by(PaperPortfolio.id.asc())
    ).all()
    cash_values = [
        float((portfolio.portfolio_payload or {}).get("starting_cash") or portfolio.cash_balance or 0.0)
        for portfolio in portfolios
        if float((portfolio.portfolio_payload or {}).get("starting_cash") or portfolio.cash_balance or 0.0) > 0
    ]
    return round(cash_values[0], 2) if cash_values else round(DEFAULT_INITIAL_CASH, 2)


def _recommendation_available_day(as_of_day: date, trade_days: list[date]) -> date | None:
    next_index = bisect_right(trade_days, as_of_day)
    if next_index >= len(trade_days):
        return None
    return trade_days[next_index]


def _recommendation_histories(
    session: Session,
    *,
    symbols: Sequence[str],
    trade_days: list[date],
) -> dict[str, list[AvailableRecommendation]]:
    if not symbols or not trade_days:
        return {}
    recommendations = session.scalars(
        select(Recommendation)
        .join(Stock)
        .where(Stock.symbol.in_(symbols))
        .options(joinedload(Recommendation.stock))
        .order_by(Stock.symbol.asc(), Recommendation.generated_at.asc(), Recommendation.id.asc())
    ).all()
    histories: dict[str, list[AvailableRecommendation]] = {}
    for recommendation in recommendations:
        available_day = _recommendation_available_day(recommendation.as_of_data_time.date(), trade_days)
        if available_day is None:
            continue
        symbol = recommendation.stock.symbol
        score = _model_advice_score(recommendation.direction, float(recommendation.confidence_score))
        candidate = AvailableRecommendation(
            symbol=symbol,
            available_day=available_day,
            as_of_day=recommendation.as_of_data_time.date(),
            generated_at=recommendation.generated_at,
            direction=recommendation.direction,
            confidence_score=float(recommendation.confidence_score),
            confidence_label=recommendation.confidence_label,
            score=score,
            recommendation_key=recommendation.recommendation_key,
        )
        symbol_history = histories.setdefault(symbol, [])
        if symbol_history and symbol_history[-1].available_day == candidate.available_day:
            if symbol_history[-1].generated_at <= candidate.generated_at:
                symbol_history[-1] = candidate
        else:
            symbol_history.append(candidate)
    return histories


def _candidate_snapshot(
    trade_day: date,
    *,
    symbols: Sequence[str],
    histories: dict[str, list[AvailableRecommendation]],
    history_index: dict[str, int],
    close_maps: dict[str, dict[date, float]],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for symbol in symbols:
        history = histories.get(symbol) or []
        pointer = history_index.get(symbol, -1)
        while pointer + 1 < len(history) and history[pointer + 1].available_day <= trade_day:
            pointer += 1
        history_index[symbol] = pointer
        if pointer < 0 or pointer >= len(history):
            continue
        record = history[pointer]
        price = (close_maps.get(symbol) or {}).get(trade_day)
        if price is None:
            continue
        candidates.append(
            {
                "symbol": symbol,
                "direction": record.direction,
                "confidence_score": record.confidence_score,
                "confidence_label": record.confidence_label,
                "score": record.score,
                "reference_price": float(price),
                "recommendation_key": record.recommendation_key,
                "available_day": record.available_day.isoformat(),
                "as_of_day": record.as_of_day.isoformat(),
            }
        )
    return candidates


def _turnover_ratio(
    *,
    current_weights: dict[str, float],
    target_weights: dict[str, float],
) -> float:
    asset_symbols = sorted(set(current_weights) | set(target_weights))
    current_cash = max(0.0, 1.0 - sum(current_weights.values()))
    target_cash = max(0.0, 1.0 - sum(target_weights.values()))
    total_shift = abs(current_cash - target_cash)
    for symbol in asset_symbols:
        total_shift += abs(float(current_weights.get(symbol, 0.0)) - float(target_weights.get(symbol, 0.0)))
    return round(total_shift / 2.0, 6)


def _replay_variant(
    *,
    symbols: Sequence[str],
    trade_days: list[date],
    close_maps: dict[str, dict[date, float]],
    benchmark_map: dict[date, float],
    histories: dict[str, list[AvailableRecommendation]],
    starting_cash: float,
    variant: PolicyVariant,
) -> dict[str, Any]:
    if len(trade_days) < 2:
        return {
            "variant_id": variant.variant_id,
            "label": variant.label,
            "include_in_aggregate": False,
            "exclusion_reason": "insufficient_trade_days",
            "params": {
                "max_position_count": variant.max_position_count,
                "max_single_weight": variant.max_single_weight,
                "min_confidence_score": variant.min_confidence_score,
                "long_directions": sorted(variant.long_directions),
            },
            "summary": {},
            "timeline": [],
        }

    positions: dict[str, int] = {}
    cash = float(starting_cash)
    history_index = {symbol: -1 for symbol in symbols}
    benchmark_start = float(benchmark_map.get(trade_days[0]) or 100.0)
    benchmark_end = float(benchmark_map.get(trade_days[-1]) or benchmark_start)

    nav_points: list[float] = [float(starting_cash)]
    benchmark_points: list[float] = [float(starting_cash)]
    daily_turnovers: list[float] = []
    invested_ratios: list[float] = []
    active_position_counts: list[float] = []
    rebalance_days: list[date] = []
    positive_after_cost_days = 0
    timeline: list[dict[str, Any]] = []
    traded_symbol_counts: list[int] = []

    for trade_day, next_day in zip(trade_days[:-1], trade_days[1:]):
        prices_today = {
            symbol: close_maps[symbol][trade_day]
            for symbol in symbols
            if trade_day in close_maps.get(symbol, {})
        }
        if not prices_today:
            continue
        nav = cash + sum(int(positions.get(symbol, 0)) * float(price) for symbol, price in prices_today.items())
        if nav <= 0:
            continue
        candidates = _candidate_snapshot(
            trade_day,
            symbols=symbols,
            histories=histories,
            history_index=history_index,
            close_maps=close_maps,
        )
        targets = _phase5_policy_targets(candidates, nav=nav, variant=variant)
        target_quantities = {symbol: int(item["target_quantity"]) for symbol, item in targets.items()}
        target_weights = {
            symbol: round(int(target_quantities[symbol]) * float(prices_today[symbol]) / nav, 6)
            for symbol in target_quantities
            if symbol in prices_today and target_quantities[symbol] > 0
        }
        current_weights = _current_weights(positions=positions, price_map=prices_today, nav=nav)
        turnover = _turnover_ratio(current_weights=current_weights, target_weights=target_weights)
        positions = {symbol: quantity for symbol, quantity in target_quantities.items() if quantity > 0}
        invested_value = sum(int(quantity) * float(prices_today[symbol]) for symbol, quantity in positions.items())
        cash = round(nav - invested_value, 6)
        invested_ratio = 0.0 if nav <= 0 else round(invested_value / nav, 6)
        active_position_count = sum(1 for quantity in positions.values() if quantity > 0)

        prices_next = {
            symbol: close_maps[symbol][next_day]
            for symbol in positions
            if next_day in close_maps.get(symbol, {})
        }
        next_nav = cash + sum(int(positions[symbol]) * float(prices_next.get(symbol, prices_today[symbol])) for symbol in positions)
        benchmark_now = float(benchmark_map.get(trade_day) or benchmark_start)
        benchmark_next = float(benchmark_map.get(next_day) or benchmark_now)
        benchmark_nav = float(starting_cash) * (benchmark_next / benchmark_start if benchmark_start else 1.0)
        strategy_day_return = 0.0 if nav <= 0 else float(next_nav) / float(nav) - 1.0
        benchmark_day_return = 0.0 if benchmark_now in {0.0, None} else float(benchmark_next) / float(benchmark_now) - 1.0
        after_cost_excess = strategy_day_return - benchmark_day_return - (
            float(turnover) * float(PHASE2_COST_MODEL["round_trip_cost_bps"]) / 10000.0
        )
        if after_cost_excess > 0:
            positive_after_cost_days += 1
        if turnover > 0:
            rebalance_days.append(trade_day)
        traded_symbol_count = sum(
            1
            for symbol in sorted(set(current_weights) | set(target_weights))
            if round(float(current_weights.get(symbol, 0.0)) - float(target_weights.get(symbol, 0.0)), 6) != 0.0
        )
        traded_symbol_counts.append(traded_symbol_count)
        nav_points.append(round(float(next_nav), 6))
        benchmark_points.append(round(float(benchmark_nav), 6))
        daily_turnovers.append(turnover)
        invested_ratios.append(invested_ratio)
        active_position_counts.append(float(active_position_count))
        timeline.append(
            {
                "trade_day": trade_day.isoformat(),
                "next_trade_day": next_day.isoformat(),
                "candidate_count": len(candidates),
                "selected_symbol_count": active_position_count,
                "selected_symbols": sorted(positions),
                "invested_ratio": invested_ratio,
                "active_position_count": active_position_count,
                "turnover": turnover,
                "nav": round(float(nav), 6),
                "next_nav": round(float(next_nav), 6),
                "benchmark_nav": round(float(benchmark_nav), 6),
                "strategy_day_return": round(strategy_day_return, 6),
                "benchmark_day_return": round(benchmark_day_return, 6),
                "after_cost_excess_return": round(after_cost_excess, 6),
            }
        )

    replay_day_count = len(timeline)
    final_nav = nav_points[-1] if nav_points else float(starting_cash)
    total_return = 0.0 if starting_cash <= 0 else float(final_nav) / float(starting_cash) - 1.0
    benchmark_total_return = (
        0.0
        if benchmark_start in {0.0, None}
        else float(benchmark_end) / float(benchmark_start) - 1.0
    )
    annualized_return = _annualized_return(total_return, replay_day_count)
    annualized_benchmark_return = _annualized_return(benchmark_total_return, replay_day_count)
    annualized_excess_return = (
        None
        if annualized_return is None or annualized_benchmark_return is None
        else round(float(annualized_return) - float(annualized_benchmark_return), 6)
    )
    mean_turnover = _mean_or_none(daily_turnovers)
    baseline_cost_drag = (
        None
        if mean_turnover is None
        else round(float(mean_turnover) * float(PHASE2_COST_MODEL["round_trip_cost_bps"]) / 10000.0, 6)
    )
    after_cost_annualized_excess = (
        None
        if annualized_excess_return is None or baseline_cost_drag is None
        else round(float(annualized_excess_return) - float(baseline_cost_drag), 6)
    )
    mean_rebalance_interval_days = None
    if len(rebalance_days) >= 2:
        intervals = [(right - left).days for left, right in zip(rebalance_days[:-1], rebalance_days[1:], strict=True)]
        mean_rebalance_interval_days = round(safe_mean(intervals), 6) if intervals else None

    return {
        "variant_id": variant.variant_id,
        "label": variant.label,
        "include_in_aggregate": replay_day_count > 0,
        "exclusion_reason": None if replay_day_count > 0 else "no_replay_days",
        "note": variant.note,
        "params": {
            "max_position_count": variant.max_position_count,
            "max_single_weight": round(variant.max_single_weight, 6),
            "min_confidence_score": round(variant.min_confidence_score, 6),
            "long_directions": sorted(variant.long_directions),
        },
        "summary": {
            "replay_day_count": replay_day_count,
            "annualized_return": annualized_return,
            "annualized_benchmark_return": annualized_benchmark_return,
            "annualized_excess_return": annualized_excess_return,
            "baseline_cost_drag": baseline_cost_drag,
            "annualized_excess_return_after_baseline_cost": after_cost_annualized_excess,
            "mean_turnover": mean_turnover,
            "mean_invested_ratio": _mean_or_none(invested_ratios),
            "mean_active_position_count": _mean_or_none(active_position_counts),
            "positive_after_cost_day_ratio": round(positive_after_cost_days / replay_day_count, 6)
            if replay_day_count
            else None,
            "rebalance_day_count": len(rebalance_days),
            "rebalance_day_ratio": round(len(rebalance_days) / replay_day_count, 6) if replay_day_count else None,
            "mean_rebalance_interval_days": mean_rebalance_interval_days,
            "mean_traded_symbol_count": _mean_or_none([float(item) for item in traded_symbol_counts]),
            "final_nav": round(final_nav, 6),
        },
        "timeline": timeline,
    }


def _variant_metric(variant: dict[str, Any], key: str) -> float:
    summary = dict(variant.get("summary") or {})
    value = summary.get(key)
    return float(value) if value is not None else float("-inf")


def _recommend_variant(experiment_id: str, variants: list[dict[str, Any]]) -> dict[str, Any]:
    included = [variant for variant in variants if variant.get("include_in_aggregate")]
    baseline_variant_id = _variant_baseline_id(experiment_id)
    baseline = next((variant for variant in included if variant["variant_id"] == baseline_variant_id), None)
    if not included or baseline is None:
        return {
            "baseline_variant_id": baseline_variant_id,
            "recommended_variant_id": None,
            "recommendation_status": "insufficient_experiment_evidence",
            "note": "The replay did not produce enough baseline evidence to compare holding-policy variants.",
            "baseline_metrics": {},
            "recommended_metrics": {},
            "metric_deltas_vs_baseline": {},
        }

    if experiment_id == "profitability_signal_threshold_sweep_v1":
        recommended = max(
            included,
            key=lambda item: (
                _variant_metric(item, "annualized_excess_return_after_baseline_cost"),
                _variant_metric(item, "positive_after_cost_day_ratio"),
                -_variant_metric(item, "mean_turnover"),
            ),
        )
        target_keys = [
            "annualized_excess_return_after_baseline_cost",
            "positive_after_cost_day_ratio",
            "mean_turnover",
        ]
    elif experiment_id == "construction_max_position_count_sweep_v1":
        recommended = max(
            included,
            key=lambda item: (
                _variant_metric(item, "mean_invested_ratio"),
                _variant_metric(item, "mean_active_position_count"),
                _variant_metric(item, "annualized_excess_return_after_baseline_cost"),
            ),
        )
        target_keys = [
            "mean_invested_ratio",
            "mean_active_position_count",
            "annualized_excess_return_after_baseline_cost",
        ]
    else:
        raise ValueError(f"unsupported holding-policy experiment id: {experiment_id}")

    baseline_metrics = {
        key: (baseline.get("summary") or {}).get(key)
        for key in target_keys
    }
    recommended_metrics = {
        key: (recommended.get("summary") or {}).get(key)
        for key in target_keys
    }
    metric_deltas: dict[str, float | None] = {}
    for key in target_keys:
        baseline_value = baseline_metrics.get(key)
        recommended_value = recommended_metrics.get(key)
        if baseline_value is None or recommended_value is None:
            metric_deltas[key] = None
            continue
        metric_deltas[key] = round(float(recommended_value) - float(baseline_value), 6)

    if recommended["variant_id"] == baseline["variant_id"]:
        status = "baseline_still_best"
        note = "The current Phase 5 baseline still ranks best on the tracked experiment metrics."
    else:
        status = "variant_outperforms_baseline"
        note = (
            f"{recommended['variant_id']} improves on the current baseline for the primary experiment focus."
        )
    return {
        "baseline_variant_id": baseline["variant_id"],
        "recommended_variant_id": recommended["variant_id"],
        "recommendation_status": status,
        "note": note,
        "baseline_metrics": baseline_metrics,
        "recommended_metrics": recommended_metrics,
        "metric_deltas_vs_baseline": metric_deltas,
    }


def build_phase5_holding_policy_experiment(
    session: Session,
    *,
    experiment_id: str,
    symbols: Sequence[str] | None = None,
) -> dict[str, Any]:
    menu_item = dict(PHASE5_HOLDING_POLICY_REDESIGN_EXPERIMENT_MENU.get(experiment_id) or {})
    if not menu_item:
        raise ValueError(f"unsupported holding-policy experiment id: {experiment_id}")

    active_symbols = list(active_watchlist_symbols(session))
    scope_symbols = list(dict.fromkeys(symbols or active_symbols))
    close_maps = _daily_close_maps(session, symbols=scope_symbols)
    trade_days = sorted({trade_day for close_map in close_maps.values() for trade_day in close_map})
    histories = _recommendation_histories(session, symbols=scope_symbols, trade_days=trade_days)
    benchmark_map = build_equal_weight_proxy(close_maps, scope_symbols)
    starting_cash = _auto_model_starting_cash(session)

    if not scope_symbols or len(trade_days) < 2 or not benchmark_map:
        return {
            "generated_at": datetime.now().astimezone().isoformat(),
            "scope": {
                "symbols": scope_symbols,
                "active_watchlist_symbols": active_symbols,
                "starting_cash": starting_cash,
                "selection_mode": "latest_recommendation_available_t_plus_1_daily_rebalance",
            },
            "contract_version": PHASE5_CONTRACT_VERSION,
            "policy_type": PHASE5_SIMULATION_POLICY,
            "action_definition": PHASE5_ACTION_DEFINITION,
            "quantity_definition": PHASE5_QUANTITY_DEFINITION,
            "required_benchmark_definition": PHASE5_PRIMARY_RESEARCH_BENCHMARK,
            "experiment_id": experiment_id,
            "experiment_version": PHASE5_HOLDING_POLICY_EXPERIMENT_VERSION,
            "experiment_definition": menu_item,
            "summary": {
                "trade_day_count": len(trade_days),
                "variant_count": len(_variant_grid(experiment_id)),
                "included_variant_count": 0,
            },
            "decision": {
                "baseline_variant_id": _variant_baseline_id(experiment_id),
                "recommended_variant_id": None,
                "recommendation_status": "insufficient_scope",
                "note": "The current scope does not have enough daily history, benchmark data, or watchlist symbols for a Phase 5 holding-policy replay.",
            },
            "variants": [],
        }

    variants = [
        _replay_variant(
            symbols=scope_symbols,
            trade_days=trade_days,
            close_maps=close_maps,
            benchmark_map=benchmark_map,
            histories=histories,
            starting_cash=starting_cash,
            variant=variant,
        )
        for variant in _variant_grid(experiment_id)
    ]
    decision = _recommend_variant(experiment_id, variants)
    included_variants = [variant for variant in variants if variant.get("include_in_aggregate")]
    return {
        "generated_at": datetime.now().astimezone().isoformat(),
        "scope": {
            "symbols": scope_symbols,
            "active_watchlist_symbols": active_symbols,
            "starting_cash": starting_cash,
            "selection_mode": "latest_recommendation_available_t_plus_1_daily_rebalance",
            "trade_day_range": {
                "start": trade_days[0].isoformat(),
                "end": trade_days[-1].isoformat(),
            },
        },
        "contract_version": PHASE5_CONTRACT_VERSION,
        "policy_type": PHASE5_SIMULATION_POLICY,
        "action_definition": PHASE5_ACTION_DEFINITION,
        "quantity_definition": PHASE5_QUANTITY_DEFINITION,
        "required_benchmark_definition": PHASE5_PRIMARY_RESEARCH_BENCHMARK,
        "experiment_id": experiment_id,
        "experiment_version": PHASE5_HOLDING_POLICY_EXPERIMENT_VERSION,
        "experiment_definition": menu_item,
        "summary": {
            "trade_day_count": len(trade_days),
            "variant_count": len(variants),
            "included_variant_count": len(included_variants),
            "history_symbol_count": len(histories),
        },
        "decision": decision,
        "variants": variants,
    }


def phase5_holding_policy_experiment_artifact_id(payload: dict[str, Any]) -> str:
    scope = dict(payload.get("scope") or {})
    experiment_id = str(payload.get("experiment_id") or "unknown_experiment")
    trade_day_range = dict(scope.get("trade_day_range") or {})
    date_key = (
        f"{trade_day_range.get('start')}_to_{trade_day_range.get('end')}"
        if trade_day_range.get("start") and trade_day_range.get("end")
        else "no_trade_day_range"
    )
    symbol_count = len(scope.get("symbols") or [])
    variant_count = len(payload.get("variants") or [])
    return f"phase5-holding-policy-experiment:{experiment_id}:{date_key}:{symbol_count}symbols:{variant_count}variants"


def build_phase5_holding_policy_experiment_artifact(
    payload: dict[str, Any],
) -> Phase5HoldingPolicyExperimentArtifactView:
    return Phase5HoldingPolicyExperimentArtifactView(
        artifact_id=phase5_holding_policy_experiment_artifact_id(payload),
        generated_at=datetime.fromisoformat(str(payload["generated_at"])),
        created_at=datetime.fromisoformat(str(payload["generated_at"])),
        scope=dict(payload.get("scope") or {}),
        contract_version=str(payload.get("contract_version") or PHASE5_CONTRACT_VERSION),
        policy_type=str(payload.get("policy_type") or PHASE5_SIMULATION_POLICY),
        action_definition=str(payload.get("action_definition") or PHASE5_ACTION_DEFINITION),
        quantity_definition=str(payload.get("quantity_definition") or PHASE5_QUANTITY_DEFINITION),
        required_benchmark_definition=str(
            payload.get("required_benchmark_definition") or PHASE5_PRIMARY_RESEARCH_BENCHMARK
        ),
        experiment_id=str(payload.get("experiment_id") or "unknown_experiment"),
        experiment_version=str(payload.get("experiment_version") or PHASE5_HOLDING_POLICY_EXPERIMENT_VERSION),
        experiment_definition=dict(payload.get("experiment_definition") or {}),
        summary=dict(payload.get("summary") or {}),
        decision=dict(payload.get("decision") or {}),
        variants=[dict(item) for item in payload.get("variants") or []],
    )
