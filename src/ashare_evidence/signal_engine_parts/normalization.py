"""Cross-sectional normalization for multi-factor models.

Provides z-score, percentile, robust MAD scaling, and winsorization
across a watchlist universe. All features entering factor computations
should be cross-sectionally normalized to remove scale bias.

References:
  - Grinold & Kahn (2000), "Active Portfolio Management", Ch. 10 (signal weighting)
  - Freyberger, Neuhierl & Weber (2020), "Dissecting Characteristics Nonparametrically"
"""

from __future__ import annotations

from math import tanh
from statistics import median, pstdev
from typing import Any


def winsorize(values: list[float], *, lower_pct: float = 0.01, upper_pct: float = 0.99) -> list[float]:
    """Clip values at lower/upper percentiles to handle outliers.

    Uses the (n-1)*pct index formula (standard percentile rank definition).
    """
    if not values:
        return values
    n = len(values)
    sorted_vals = sorted(values)
    lower_idx = max(0, int((n - 1) * lower_pct))
    upper_idx = min(n - 1, int((n - 1) * upper_pct))
    lower_bound = sorted_vals[lower_idx]
    upper_bound = sorted_vals[upper_idx]
    return [max(lower_bound, min(upper_bound, v)) for v in values]


def cross_sectional_zscore(raw_values: dict[str, float]) -> dict[str, float]:
    """Compute z-scores across the cross-section of symbols.

    Args:
        raw_values: {symbol: raw_feature_value}

    Returns:
        {symbol: zscore} where zscore = (value - mean) / std (or 0 if std==0)
    """
    if not raw_values:
        return {}
    vals = list(raw_values.values())
    v_mean = sum(vals) / len(vals)
    v_std = pstdev(vals) if len(vals) > 1 else 0.0
    if v_std < 1e-12:
        return {s: 0.0 for s in raw_values}
    return {s: (v - v_mean) / v_std for s, v in raw_values.items()}


def cross_sectional_percentile(raw_values: dict[str, float]) -> dict[str, float]:
    """Compute percentile ranks (0-1) across the cross-section."""
    if not raw_values:
        return {}
    n = len(raw_values)
    if n <= 1:
        return {s: 0.5 for s in raw_values}
    sorted_items = sorted(raw_values.items(), key=lambda x: x[1])
    result: dict[str, float] = {}
    for rank, (symbol, _) in enumerate(sorted_items):
        result[symbol] = rank / (n - 1)
    return result


def cross_sectional_median(raw_values: dict[str, float]) -> float:
    """Return the cross-sectional median of a feature."""
    if not raw_values:
        return 0.0
    return float(median(raw_values.values()))


def cross_sectional_mad(raw_values: dict[str, float]) -> float:
    """Median Absolute Deviation: median(|x_i - median(x)|)."""
    if not raw_values:
        return 1.0
    med = cross_sectional_median(raw_values)
    abs_devs = [abs(v - med) for v in raw_values.values()]
    return float(median(abs_devs)) if abs_devs else 1.0


def cross_sectional_robust_scale(raw_values: dict[str, float]) -> dict[str, float]:
    """Robust scaling using median and MAD (1.4826 factor for normal consistency)."""
    if not raw_values:
        return {}
    med = cross_sectional_median(raw_values)
    mad = cross_sectional_mad(raw_values)
    scale = mad * 1.4826
    if scale < 1e-12:
        return {s: 0.0 for s in raw_values}
    return {s: (v - med) / scale for s, v in raw_values.items()}


class FeatureDistributions:
    """Collect per-feature raw values across symbols for normalization.

    Usage:
        dist = FeatureDistributions()
        dist.collect("ret_10d", {"000001.SZ": 0.05, "000002.SZ": -0.03})
        # ... after collecting all symbols ...
        z_scores = dist.feature_zscores("ret_10d")
    """

    def __init__(self) -> None:
        self._store: dict[str, dict[str, float]] = {}

    def collect(self, feature_name: str, symbol_values: dict[str, float]) -> None:
        existing = self._store.setdefault(feature_name, {})
        existing.update(symbol_values)

    def feature_values(self, feature_name: str) -> dict[str, float]:
        return self._store.get(feature_name, {})

    def feature_zscores(self, feature_name: str) -> dict[str, float]:
        raw = self._store.get(feature_name, {})
        return cross_sectional_zscore(raw)

    def feature_percentiles(self, feature_name: str) -> dict[str, float]:
        raw = self._store.get(feature_name, {})
        return cross_sectional_percentile(raw)

    def feature_median(self, feature_name: str) -> float:
        raw = self._store.get(feature_name, {})
        return cross_sectional_median(raw)

    def feature_mad(self, feature_name: str) -> float:
        raw = self._store.get(feature_name, {})
        return cross_sectional_mad(raw)

    def feature_names(self) -> list[str]:
        return sorted(self._store.keys())

    def symbol_count(self) -> int:
        symbols: set[str] = set()
        for vals in self._store.values():
            symbols.update(vals.keys())
        return len(symbols)


def score_scale_cs(value: float, median_val: float, mad_val: float) -> float:
    """Data-driven tanh scaling using cross-sectional median and MAD.

    Replaces hardcoded scale parameters. Maps value to [-1, 1] via
    tanh((value - median) / (mad * 1.5)), where 1.5 is a smoothing factor
    that ensures the interquartile range maps roughly to [-0.5, 0.5].
    """
    scaled_mad = mad_val * 1.5
    if scaled_mad < 1e-12:
        return 0.0
    return max(-1.0, min(1.0, tanh((value - median_val) / scaled_mad)))


def feature_summary(raw_values: dict[str, float]) -> dict[str, Any]:
    """Return descriptive statistics for a feature distribution."""
    if not raw_values:
        return {"count": 0}
    vals = list(raw_values.values())
    n = len(vals)
    v_mean = sum(vals) / n
    v_std = pstdev(vals) if n > 1 else 0.0
    sorted_vals = sorted(vals)
    return {
        "count": n,
        "mean": round(v_mean, 6),
        "std": round(v_std, 6),
        "min": round(sorted_vals[0], 6),
        "p25": round(sorted_vals[max(0, n // 4)], 6),
        "median": round(sorted_vals[n // 2], 6),
        "p75": round(sorted_vals[min(n - 1, 3 * n // 4)], 6),
        "max": round(sorted_vals[-1], 6),
    }
