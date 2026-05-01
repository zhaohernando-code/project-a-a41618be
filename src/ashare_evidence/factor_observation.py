from __future__ import annotations

import json
from bisect import bisect_left
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ashare_evidence.benchmark import CSI_BENCHMARKS, DEFAULT_BENCHMARK_ID, benchmark_close_maps
from ashare_evidence.models import MarketBar, Recommendation, Stock
from ashare_evidence.phase2.factor_ic import FactorICResult, aggregate_ic_results, compute_rank_ic
from ashare_evidence.recommendation_selection import recommendation_recency_ordering
from ashare_evidence.watchlist import active_watchlist_symbols

FACTOR_KEYS = ("price_baseline", "news_event", "fundamental", "size_factor", "reversal", "liquidity")
HORIZONS = (10, 20, 40)
MIN_SYMBOLS_PER_SNAPSHOT = 5
MIN_SNAPSHOT_COUNT = 3
FUSION_BASELINE = {
    "price_baseline": 0.35,
    "news_event": 0.20,
    "fundamental": 0.15,
    "size_factor": 0.10,
    "reversal": 0.10,
    "liquidity": 0.10,
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool) or value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _extract_factor_scores(payload: dict[str, Any]) -> dict[str, float]:
    factor_breakdown = payload.get("factor_breakdown") if isinstance(payload.get("factor_breakdown"), dict) else {}
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}
    cards = {
        str(card.get("factor_key")): card
        for card in evidence.get("factor_cards", [])
        if isinstance(card, dict) and card.get("factor_key")
    }
    scores: dict[str, float] = {}
    for key in FACTOR_KEYS:
        raw = factor_breakdown.get(key, {}) if isinstance(factor_breakdown.get(key), dict) else {}
        card = cards.get(key, {})
        scores[key] = _safe_float(raw.get("score", card.get("score")))
    return scores


def _extract_dynamic_weights(payload: dict[str, Any]) -> dict[str, float]:
    factor_breakdown = payload.get("factor_breakdown") if isinstance(payload.get("factor_breakdown"), dict) else {}
    weights: dict[str, float] = {}
    for key in FACTOR_KEYS:
        raw = factor_breakdown.get(key, {}) if isinstance(factor_breakdown.get(key), dict) else {}
        weights[key] = _safe_float(raw.get("weight"), FUSION_BASELINE[key])
    total = sum(weights.values())
    return {key: round(value / total, 4) for key, value in weights.items()} if total > 0 else dict(FUSION_BASELINE)


def _close_maps(session: Session, symbols: list[str]) -> dict[str, dict[date, float]]:
    if not symbols:
        return {}
    rows = session.execute(
        select(Stock.symbol, MarketBar.observed_at, MarketBar.close_price)
        .join(MarketBar, MarketBar.stock_id == Stock.id)
        .where(Stock.symbol.in_(symbols), MarketBar.timeframe == "1d")
        .order_by(Stock.symbol.asc(), MarketBar.observed_at.asc())
    ).all()
    result: dict[str, dict[date, float]] = {}
    for symbol, observed_at, close_price in rows:
        result.setdefault(str(symbol), {})[observed_at.date()] = float(close_price)
    return result


def _forward_return(series: dict[date, float], as_of: date, horizon: int) -> tuple[float, date, date] | None:
    days = sorted(series)
    if not days:
        return None
    entry_idx = bisect_left(days, as_of)
    if entry_idx >= len(days):
        return None
    exit_idx = entry_idx + horizon
    if exit_idx >= len(days):
        return None
    entry_day = days[entry_idx]
    exit_day = days[exit_idx]
    entry_close = series[entry_day]
    exit_close = series[exit_day]
    if entry_close == 0:
        return None
    return exit_close / entry_close - 1.0, entry_day, exit_day


def _records_for_scope(session: Session) -> list[Recommendation]:
    symbols = active_watchlist_symbols(session)
    query = (
        select(Recommendation)
        .join(Stock)
        .options(joinedload(Recommendation.stock))
        .order_by(*recommendation_recency_ordering(stock_symbol=True))
    )
    if symbols:
        query = query.where(Stock.symbol.in_(symbols))
    return list(session.scalars(query).all())


def _bucket_returns(rows: list[dict[str, Any]], factor_key: str) -> list[dict[str, Any]]:
    valid = [
        (row["scores"][factor_key], row["forward_excess_return"], row["symbol"])
        for row in rows
        if row.get("scores", {}).get(factor_key) is not None
    ]
    if len(valid) < MIN_SYMBOLS_PER_SNAPSHOT:
        return []
    valid.sort(key=lambda item: item[0])
    bucket_count = 3 if len(valid) < 20 else 5
    buckets: list[dict[str, Any]] = []
    for bucket_index in range(bucket_count):
        start = round(bucket_index * len(valid) / bucket_count)
        end = round((bucket_index + 1) * len(valid) / bucket_count)
        bucket = valid[start:end]
        if not bucket:
            continue
        mean_return = sum(item[1] for item in bucket) / len(bucket)
        buckets.append(
            {
                "bucket": bucket_index + 1,
                "label": f"Q{bucket_index + 1}",
                "mean_forward_excess_return": round(mean_return, 6),
                "sample_count": len(bucket),
                "symbols": [item[2] for item in bucket],
            }
        )
    return buckets


def _ic_result_to_dict(result: FactorICResult) -> dict[str, Any]:
    return {
        "factor_name": result.factor_name,
        "horizon_days": result.horizon_days,
        "rank_ic_mean": result.ic_mean,
        "ic_std": result.ic_std,
        "ic_ir": result.ic_ir,
        "positive_ic_rate": result.ic_positive_rate,
        "sample_count": result.sample_count,
        "computed_at": result.computed_at,
    }


def build_factor_observations(
    session: Session,
    *,
    artifact_root: str,
    min_records: int = MIN_SYMBOLS_PER_SNAPSHOT,
    horizons: tuple[int, ...] = HORIZONS,
    persist: bool = True,
) -> dict[str, Any]:
    recommendations = _records_for_scope(session)
    symbols = sorted({record.stock.symbol for record in recommendations if record.stock is not None})
    close_maps = _close_maps(session, symbols)
    benchmark_maps = benchmark_close_maps(session)
    primary_benchmark_symbol = CSI_BENCHMARKS[DEFAULT_BENCHMARK_ID]["symbol"]
    primary_benchmark = benchmark_maps.get(primary_benchmark_symbol, {})
    by_as_of: dict[date, list[Recommendation]] = {}
    for record in recommendations:
        if record.as_of_data_time is None or record.stock is None:
            continue
        by_as_of.setdefault(record.as_of_data_time.date(), []).append(record)

    observation_rows: list[dict[str, Any]] = []
    snapshot_results: dict[int, list[FactorICResult]] = {horizon: [] for horizon in horizons}
    per_horizon_rows: dict[int, list[dict[str, Any]]] = {horizon: [] for horizon in horizons}
    benchmark_source = "csi_index_daily"
    if not primary_benchmark:
        benchmark_source = "active_universe_equal_weight_proxy_pending_csi_index_bars"

    for as_of_day, records in sorted(by_as_of.items()):
        scored_records: list[dict[str, Any]] = []
        for record in records:
            symbol = record.stock.symbol
            forward_inputs = {
                horizon: _forward_return(close_maps.get(symbol, {}), as_of_day, horizon)
                for horizon in horizons
            }
            if not any(forward_inputs.values()):
                continue
            payload = record.recommendation_payload or {}
            scored_records.append(
                {
                    "symbol": symbol,
                    "recommendation_key": record.recommendation_key,
                    "as_of_date": as_of_day,
                    "as_of": record.as_of_data_time,
                    "direction": record.direction,
                    "scores": _extract_factor_scores(payload),
                    "dynamic_weights": _extract_dynamic_weights(payload),
                    "forward_inputs": forward_inputs,
                }
            )
        for horizon in horizons:
            horizon_rows: list[dict[str, Any]] = []
            stock_returns: list[float] = []
            for item in scored_records:
                forward = item["forward_inputs"].get(horizon)
                if forward is None:
                    continue
                stock_return, entry_day, exit_day = forward
                stock_returns.append(stock_return)
                horizon_rows.append(
                    {
                        "symbol": item["symbol"],
                        "recommendation_key": item["recommendation_key"],
                        "as_of": item["as_of"].isoformat(),
                        "as_of_date": as_of_day.isoformat(),
                        "horizon_days": horizon,
                        "direction": item["direction"],
                        "scores": item["scores"],
                        "dynamic_weights": item["dynamic_weights"],
                        "stock_forward_return": stock_return,
                        "entry_trade_day": entry_day.isoformat(),
                        "exit_trade_day": exit_day.isoformat(),
                    }
                )
            if len(horizon_rows) < min_records:
                continue
            benchmark_return = None
            if primary_benchmark:
                benchmark_forward = _forward_return(primary_benchmark, as_of_day, horizon)
                if benchmark_forward is not None:
                    benchmark_return = benchmark_forward[0]
            if benchmark_return is None:
                benchmark_return = sum(stock_returns) / len(stock_returns) if stock_returns else 0.0
            for row in horizon_rows:
                row["benchmark_return"] = round(float(benchmark_return), 6)
                row["benchmark_source"] = benchmark_source
                row["forward_excess_return"] = round(float(row["stock_forward_return"]) - float(benchmark_return), 6)
            factor_scores = {
                factor_key: [float(row["scores"][factor_key]) for row in horizon_rows]
                for factor_key in FACTOR_KEYS
            }
            forward_excess = [float(row["forward_excess_return"]) for row in horizon_rows]
            snapshot_results[horizon].extend(compute_rank_ic(factor_scores, forward_excess, horizon))
            per_horizon_rows[horizon].extend(horizon_rows)
            observation_rows.extend(horizon_rows)

    factor_results: dict[str, Any] = {}
    for horizon in horizons:
        aggregate = aggregate_ic_results(snapshot_results[horizon])
        horizon_key = f"{horizon}d"
        factor_results[horizon_key] = {}
        for factor_key in FACTOR_KEYS:
            rows = per_horizon_rows[horizon]
            item = aggregate.get(factor_key)
            factor_results[horizon_key][factor_key] = {
                **(_ic_result_to_dict(item) if item else {
                    "factor_name": factor_key,
                    "horizon_days": horizon,
                    "rank_ic_mean": None,
                    "ic_std": None,
                    "ic_ir": None,
                    "positive_ic_rate": None,
                    "sample_count": len(rows),
                    "computed_at": datetime.now(UTC).isoformat(),
                }),
                "bucket_returns": _bucket_returns(rows, factor_key),
            }

    distinct_as_of = sorted({row["as_of_date"] for row in observation_rows})
    status = (
        "verified_candidate"
        if len(distinct_as_of) >= MIN_SNAPSHOT_COUNT and len(observation_rows) >= MIN_SNAPSHOT_COUNT * min_records
        else "insufficient_sample"
    )
    results: dict[str, Any] = {
        "artifact_type": "factor_ic_study",
        "status": status,
        "generated_at": datetime.now(UTC).isoformat(),
        "universe_symbol_count": len(symbols),
        "symbols": symbols,
        "horizons": list(horizons),
        "benchmark_context": {
            "primary_benchmark": DEFAULT_BENCHMARK_ID,
            "primary_symbol": primary_benchmark_symbol,
            "source": benchmark_source,
            "status": "available" if primary_benchmark else "pending_csi_index_bars",
        },
        "observation_count": len(observation_rows),
        "distinct_as_of_date_count": len(distinct_as_of),
        "min_symbols_per_snapshot": min_records,
        "min_snapshot_count": MIN_SNAPSHOT_COUNT,
        "factor_results": factor_results,
        "observation_rows": observation_rows,
        "note": (
            "因子可信度基于滚动 RankIC/IC_IR；当前融合贡献仍单独按 factor_score × dynamic_weight 解释。"
            if status != "insufficient_sample"
            else "样本不足，不能输出精确因子可信度或权重结论。"
        ),
    }
    if persist:
        _write_artifact(results, artifact_root=artifact_root)
    return results


def _write_artifact(results: dict[str, Any], *, artifact_root: str) -> None:
    directory = Path(artifact_root) / "studies"
    directory.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    filepath = directory / f"factor-ic-study:{ts}.json"
    filepath.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _build_weight_grid() -> list[tuple[str, dict[str, float]]]:
    return [
        ("baseline", dict(FUSION_BASELINE)),
        ("price_heavy", {**FUSION_BASELINE, "price_baseline": 0.45, "news_event": 0.15, "fundamental": 0.10}),
        ("news_heavy", {**FUSION_BASELINE, "price_baseline": 0.25, "news_event": 0.30, "fundamental": 0.15}),
        (
            "balanced",
            {
                "price_baseline": 0.25,
                "news_event": 0.20,
                "fundamental": 0.20,
                "size_factor": 0.12,
                "reversal": 0.12,
                "liquidity": 0.11,
            },
        ),
        ("size_aware", {**FUSION_BASELINE, "size_factor": 0.15, "reversal": 0.08, "liquidity": 0.07}),
    ]


def _weighted_score(row: dict[str, Any], weights: dict[str, float]) -> float:
    return sum(float(row["scores"].get(key, 0.0)) * float(weights.get(key, 0.0)) for key in FACTOR_KEYS)


def sweep_weights(session: Session, *, artifact_root: str, persist: bool = True) -> dict[str, Any]:
    observations = build_factor_observations(
        session,
        artifact_root=artifact_root,
        min_records=MIN_SYMBOLS_PER_SNAPSHOT,
        persist=False,
    )
    rows = observations.get("observation_rows", [])
    weight_grid = _build_weight_grid()
    sweep_results: list[dict[str, Any]] = []
    for label, weights in weight_grid:
        by_horizon: dict[int, list[FactorICResult]] = {}
        spread_rows: dict[int, list[float]] = {}
        grouped: dict[tuple[int, str], list[dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault((int(row["horizon_days"]), str(row["as_of_date"])), []).append(row)
        for (horizon, _as_of), group_rows in grouped.items():
            if len(group_rows) < MIN_SYMBOLS_PER_SNAPSHOT:
                continue
            scores = [_weighted_score(row, weights) for row in group_rows]
            forward = [float(row["forward_excess_return"]) for row in group_rows]
            by_horizon.setdefault(horizon, []).extend(
                compute_rank_ic({"fusion_score": scores}, forward, horizon)
            )
            ranked = sorted(zip(scores, forward), key=lambda item: item[0])
            top = ranked[-max(1, len(ranked) // 3):]
            bottom = ranked[:max(1, len(ranked) // 3)]
            spread_rows.setdefault(horizon, []).append(
                sum(item[1] for item in top) / len(top) - sum(item[1] for item in bottom) / len(bottom)
            )
        horizon_metrics: dict[str, Any] = {}
        for horizon, ic_rows in by_horizon.items():
            aggregate = aggregate_ic_results(ic_rows)
            fusion = aggregate.get("fusion_score")
            spreads = spread_rows.get(horizon, [])
            horizon_metrics[f"{horizon}d"] = {
                "rank_ic_mean": fusion.ic_mean if fusion else None,
                "ic_ir": fusion.ic_ir if fusion else None,
                "positive_ic_rate": fusion.ic_positive_rate if fusion else None,
                "sample_count": fusion.sample_count if fusion else 0,
                "mean_top_bottom_spread": round(sum(spreads) / len(spreads), 6) if spreads else None,
                "snapshot_count": len(spreads),
            }
        sweep_results.append({"label": label, "weights": weights, "horizon_metrics": horizon_metrics})
    status = "insufficient_sample" if observations.get("status") == "insufficient_sample" else "research_candidate"
    results: dict[str, Any] = {
        "artifact_type": "weight_sweep_study",
        "status": status,
        "generated_at": datetime.now(UTC).isoformat(),
        "baseline_weights": FUSION_BASELINE,
        "benchmark_context": observations.get("benchmark_context", {}),
        "observation_count": observations.get("observation_count", 0),
        "distinct_as_of_date_count": observations.get("distinct_as_of_date_count", 0),
        "sweep_results": sweep_results,
        "note": "权重 sweep 只产出研究证据，不自动修改生产权重；不得把 in-sample 最优组合作为上线结论。",
    }
    if persist:
        _write_sweep_artifact(results, artifact_root=artifact_root)
    return results


def _write_sweep_artifact(results: dict[str, Any], *, artifact_root: str) -> None:
    directory = Path(artifact_root) / "studies"
    directory.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    filepath = directory / f"weight-sweep-study:{ts}.json"
    filepath.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
