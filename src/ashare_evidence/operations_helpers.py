"""Shared helper functions for operations dashboard."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from ashare_evidence.contract_status import STATUS_PENDING_REBUILD
from ashare_evidence.intraday_market import INTRADAY_MARKET_TIMEFRAME, get_intraday_market_status

def _distinct_trade_days(observed_points: list[datetime]) -> list[date]:
    trade_days = sorted({item.date() for item in observed_points})
    return trade_days



def _price_map_from_history(
    price_history: dict[str, list[tuple[datetime, float]]],
) -> dict[str, dict[date, float]]:
    close_maps: dict[str, dict[date, float]] = {}
    for symbol, series in price_history.items():
        daily_map: dict[date, float] = {}
        for observed_at, close in sorted(series, key=lambda item: item[0]):
            daily_map[observed_at.date()] = float(close)
        if daily_map:
            close_maps[symbol] = daily_map
    return close_maps



def _benchmark_close_map(
    trade_days: list[date],
    *,
    price_history: dict[str, list[tuple[datetime, float]]],
    active_symbols: set[str] | list[str] | tuple[str, ...],
) -> dict[date, float]:
    close_maps = _price_map_from_history(price_history)
    proxy = build_equal_weight_proxy(close_maps, sorted({symbol for symbol in active_symbols if symbol}))
    if proxy:
        return {trade_day: float(proxy[trade_day]) for trade_day in trade_days if trade_day in proxy}
    if not trade_days:
        return {}
    return {trade_day: 100.0 for trade_day in trade_days}



def _source_classification(*, source: str | None, artifact_id: str | None = None) -> str:
    if artifact_id or (source and source.endswith("_artifact")):
        return "artifact_backed"
    return "migration_placeholder"



def _validation_mode(*, validation_status: str) -> str:
    return "artifact_backed" if validation_status == "verified" else "migration_placeholder"



def _close_on_or_before(series: list[tuple[datetime, float]], point: datetime | date | None) -> float | None:
    if point is None:
        return None
    last_close: float | None = None
    target_day = point if isinstance(point, date) and not isinstance(point, datetime) else None
    target_time = point if isinstance(point, datetime) else None
    for observed_at, close in series:
        if target_time is not None:
            if observed_at > target_time:
                break
        elif observed_at.date() > target_day:
            break
        last_close = close
    return last_close


