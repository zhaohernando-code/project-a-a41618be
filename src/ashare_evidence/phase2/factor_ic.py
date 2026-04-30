"""Factor Information Coefficient (IC) computation for multi-factor models.

Computes Rank IC (Spearman correlation) between each factor's score and
forward excess returns over multiple horizons. Used for:
  - Calibrating fusion weights via IC_IR (Information Ratio = IC_mean / IC_std)
  - Detecting factor decay (rolling IC trending toward zero)
  - Monitoring factor performance over time

References:
  - Grinold & Kahn (2000), "Active Portfolio Management", Ch. 10
  - Qian, Hua & Sorensen (2007), "Quantitative Equity Portfolio Management", Ch. 4
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from math import sqrt

from ashare_evidence.phase2.common import spearman_correlation


@dataclass
class FactorICResult:
    """IC metrics for a single factor over a specific period."""
    factor_name: str
    horizon_days: int
    ic_mean: float
    ic_std: float
    ic_ir: float  # Information Ratio: ic_mean / ic_std (annualized proxy)
    ic_positive_rate: float  # fraction of periods where IC > 0
    sample_count: int
    computed_at: str


@dataclass
class RollingICSeries:
    """Rolling window IC time series for a factor."""
    factor_name: str
    horizon_days: int
    window_size_days: int
    ic_values: list[float] = field(default_factory=list)
    dates: list[str] = field(default_factory=list)

    def recent_ic_mean(self, periods: int = 10) -> float:
        if not self.ic_values:
            return 0.0
        window = self.ic_values[-periods:]
        return sum(window) / len(window)

    def is_decaying(self, threshold: float = 0.01, periods: int = 10) -> bool:
        """Returns True if the rolling IC has been below `threshold` for `periods` consecutive windows."""
        if len(self.ic_values) < periods:
            return False
        return all(abs(ic) < threshold for ic in self.ic_values[-periods:])


def compute_rank_ic(
    factor_scores: dict[str, list[float]],
    forward_returns: list[float],
    horizon_days: int,
) -> list[FactorICResult]:
    """Compute Rank IC for each factor at a single point in time.

    Args:
        factor_scores: {factor_name: [score_per_symbol]} where list order
            must match the order of forward_returns.
        forward_returns: [forward_return_per_symbol] for the same list of symbols.
        horizon_days: forecast horizon for the forward returns.

    Returns:
        List of FactorICResult, one per factor.
    """
    n_symbols = len(forward_returns)
    if n_symbols < 5:  # minimum for meaningful rank correlation
        return []

    results: list[FactorICResult] = []
    for name, scores in factor_scores.items():
        if len(scores) != n_symbols:
            continue
        ic = spearman_correlation(list(scores), list(forward_returns))
        results.append(FactorICResult(
            factor_name=name,
            horizon_days=horizon_days,
            ic_mean=round(ic, 6),
            ic_std=0.0,  # single-point IC has no std; set at aggregation level
            ic_ir=0.0,
            ic_positive_rate=1.0 if ic > 0 else 0.0,
            sample_count=n_symbols,
            computed_at=datetime.now().isoformat(),
        ))
    return results


def aggregate_ic_results(
    results: list[FactorICResult],
    *,
    periods_per_year: int = 20,
) -> dict[str, FactorICResult]:
    """Aggregate multiple IC snapshots into per-factor metrics.

    Args:
        results: List of IC results across time periods (same factor+horizon).
        periods_per_year: scaling for annualizing IC_IR. Default 20 (monthly).

    Returns:
        {factor_name: aggregated FactorICResult}
    """
    by_factor: dict[str, list[FactorICResult]] = {}
    for r in results:
        by_factor.setdefault(r.factor_name, []).append(r)

    aggregated: dict[str, FactorICResult] = {}
    for name, items in by_factor.items():
        ic_vals = [r.ic_mean for r in items]
        n = len(ic_vals)
        if n < 3:
            continue
        ic_mean = sum(ic_vals) / n
        ic_std = sqrt(sum((v - ic_mean) ** 2 for v in ic_vals) / (n - 1)) if n > 1 else 0.0
        ic_ir = (ic_mean / ic_std * sqrt(periods_per_year)) if ic_std > 0 else 0.0
        pos_rate = sum(1 for v in ic_vals if v > 0) / n
        aggregated[name] = FactorICResult(
            factor_name=name,
            horizon_days=items[0].horizon_days,
            ic_mean=round(ic_mean, 6),
            ic_std=round(ic_std, 6),
            ic_ir=round(ic_ir, 4),
            ic_positive_rate=round(pos_rate, 4),
            sample_count=sum(r.sample_count for r in items),
            computed_at=datetime.now().isoformat(),
        )
    return aggregated


def ic_based_weights(
    ic_results: dict[str, FactorICResult],
    *,
    default_weights: dict[str, float] | None = None,
) -> dict[str, float]:
    """Compute fusion weights from IC_IR (Information Ratio).

    Only factors with positive IC_IR contribute. Negative IC_IR factors get zero weight.
    Falls back to default_weights if IC data is unavailable for a factor.

    Args:
        ic_results: Aggregated IC results per factor.
        default_weights: Fallback weights when IC data is missing.

    Returns:
        {factor_name: weight} summing to 1.0.
    """
    defaults = default_weights or {}
    raw: dict[str, float] = {}
    for name, result in ic_results.items():
        raw[name] = max(result.ic_ir, 0.0)
    # Fill missing factors with defaults
    for name, dw in defaults.items():
        if name not in raw:
            raw[name] = dw * 0.15  # low default weight for uncalibrated factors
    total = sum(raw.values())
    if total <= 0:
        return dict(defaults) if defaults else {}
    return {name: round(w / total, 4) for name, w in raw.items()}


def rolling_ic_weights(
    base_weights: dict[str, float],
    recent_ic_series: dict[str, RollingICSeries],
    *,
    sensitivity: float = 0.5,
) -> dict[str, float]:
    """Adjust weights based on recent IC vs historical mean.

    effective_w_i = base_w_i * (1 + tanh((IC_recent_i - IC_mean_i) / (IC_std_i + eps)) * sensitivity)

    This up-weights factors that are performing better than their historical average
    and down-weights those performing worse.

    Args:
        base_weights: Baseline weights (e.g., from ic_based_weights or default).
        recent_ic_series: Recent rolling IC data per factor.
        sensitivity: How strongly to respond to recent IC deviation (0=no change, 1=max).

    Returns:
        Adjusted weights summing to 1.0.
    """
    from math import tanh

    adjusted: dict[str, float] = {}
    for name, bw in base_weights.items():
        series = recent_ic_series.get(name)
        if series is None or not series.ic_values:
            adjusted[name] = bw
            continue
        recent = series.recent_ic_mean(periods=5)
        if len(series.ic_values) > 5:
            hist_mean = sum(series.ic_values[:-5]) / (len(series.ic_values) - 5)
            hist_std = sqrt(sum((v - hist_mean) ** 2 for v in series.ic_values[:-5]) / max(len(series.ic_values) - 6, 1)) or 0.01
            deviation = (recent - hist_mean) / hist_std
        else:
            deviation = 0.0
        multiplier = 1.0 + tanh(deviation) * sensitivity
        adjusted[name] = bw * max(0.3, min(2.0, multiplier))

    total = sum(adjusted.values())
    return {name: round(w / total, 4) for name, w in adjusted.items()} if total > 0 else dict(base_weights)
