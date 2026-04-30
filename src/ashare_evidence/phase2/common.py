from __future__ import annotations

from datetime import date
from math import sqrt
from statistics import mean, pstdev
from typing import Any


def safe_mean(values: list[float]) -> float:
    return mean(values) if values else 0.0


def safe_std(values: list[float]) -> float:
    return pstdev(values) if len(values) > 1 else 0.0


def pct_change(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return current / previous - 1


def rank(values: list[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    for position, (index, _value) in enumerate(ordered, start=1):
        ranks[index] = float(position)
    return ranks


def pearson_correlation(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or len(left) < 2:
        return 0.0
    left_mean = safe_mean(left)
    right_mean = safe_mean(right)
    numerator = sum((lhs - left_mean) * (rhs - right_mean) for lhs, rhs in zip(left, right, strict=True))
    left_denom = sqrt(sum((lhs - left_mean) ** 2 for lhs in left))
    right_denom = sqrt(sum((rhs - right_mean) ** 2 for rhs in right))
    if left_denom == 0 or right_denom == 0:
        return 0.0
    return numerator / (left_denom * right_denom)


def spearman_correlation(left: list[float], right: list[float]) -> float:
    return pearson_correlation(rank(left), rank(right))


def build_equal_weight_proxy(price_maps: dict[str, dict[date, float]], symbols: list[str]) -> dict[date, float]:
    if not symbols:
        return {}
    all_days = sorted({trade_day for symbol in symbols for trade_day in price_maps.get(symbol, {})})
    if len(all_days) < 2:
        return {}

    benchmark = {all_days[0]: 100.0}
    prior_day = all_days[0]
    prior_close = 100.0
    for trade_day in all_days[1:]:
        day_returns: list[float] = []
        for symbol in symbols:
            current_close = price_maps.get(symbol, {}).get(trade_day)
            previous_close = price_maps.get(symbol, {}).get(prior_day)
            if current_close in {None, 0} or previous_close in {None, 0}:
                continue
            day_returns.append(pct_change(float(current_close), float(previous_close)))
        day_return = safe_mean(day_returns)
        prior_close = round(prior_close * (1 + day_return), 6)
        benchmark[trade_day] = prior_close
        prior_day = trade_day
    return benchmark


def build_expanding_equal_weight_proxy(
    price_maps: dict[str, dict[date, float]],
    membership_start_dates: dict[str, date],
) -> tuple[dict[date, float], dict[str, Any]]:
    symbols = [symbol for symbol in membership_start_dates if price_maps.get(symbol)]
    if not symbols:
        return {}, {
            "proxy_membership_rule": "expanding_active_watchlist_join_date_forward_only",
            "proxy_symbol_count": 0,
            "defaulted_symbol_count": 0,
            "defaulted_symbols": [],
            "min_constituent_count": 0,
            "max_constituent_count": 0,
            "first_active_day": None,
            "last_active_day": None,
        }

    all_days = sorted({trade_day for symbol in symbols for trade_day in price_maps.get(symbol, {})})
    if not all_days:
        return {}, {
            "proxy_membership_rule": "expanding_active_watchlist_join_date_forward_only",
            "proxy_symbol_count": len(symbols),
            "defaulted_symbol_count": 0,
            "defaulted_symbols": [],
            "min_constituent_count": 0,
            "max_constituent_count": 0,
            "first_active_day": None,
            "last_active_day": None,
        }

    benchmark: dict[date, float] = {}
    constituent_counts: dict[date, int] = {}
    prior_day: date | None = None
    prior_close = 100.0

    for trade_day in all_days:
        active_symbols = [
            symbol
            for symbol in symbols
            if membership_start_dates[symbol] <= trade_day and trade_day in price_maps.get(symbol, {})
        ]
        if not active_symbols:
            continue
        constituent_counts[trade_day] = len(active_symbols)
        if prior_day is None:
            benchmark[trade_day] = prior_close
            prior_day = trade_day
            continue

        day_returns: list[float] = []
        for symbol in active_symbols:
            if membership_start_dates[symbol] > prior_day:
                continue
            previous_close = price_maps.get(symbol, {}).get(prior_day)
            current_close = price_maps.get(symbol, {}).get(trade_day)
            if current_close in {None, 0} or previous_close in {None, 0}:
                continue
            day_returns.append(pct_change(float(current_close), float(previous_close)))

        if day_returns:
            prior_close = round(prior_close * (1 + safe_mean(day_returns)), 6)
        benchmark[trade_day] = prior_close
        prior_day = trade_day

    count_values = list(constituent_counts.values())
    return benchmark, {
        "proxy_membership_rule": "expanding_active_watchlist_join_date_forward_only",
        "proxy_symbol_count": len(symbols),
        "defaulted_symbol_count": 0,
        "defaulted_symbols": [],
        "min_constituent_count": min(count_values) if count_values else 0,
        "max_constituent_count": max(count_values) if count_values else 0,
        "first_active_day": min(benchmark).isoformat() if benchmark else None,
        "last_active_day": max(benchmark).isoformat() if benchmark else None,
    }


def return_between(series: dict[date, float], entry_day: date, exit_day: date) -> float | None:
    entry = series.get(entry_day)
    exit_value = series.get(exit_day)
    if entry in {None, 0} or exit_value is None:
        return None
    return float(exit_value) / float(entry) - 1
