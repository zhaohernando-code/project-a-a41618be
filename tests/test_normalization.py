"""Tests for the cross-sectional normalization module (src/ashare_evidence/signal_engine_parts/normalization.py).

Validation targets:
  1. z-score: mean≈0, std≈1 for 3+ symbols
  2. Winsorization clips at correct boundaries
  3. Percentile maps min→0, max→1
  4. Robust scale is less sensitive to outliers than z-score
  5. FeatureDistributions correctly aggregates across symbols
  6. score_scale_cs maps median→~0, extreme→±~1
  7. feature_summary returns correct count/mean/percentiles
"""

from __future__ import annotations  # noqa: I001  -- match project convention

from math import isclose, tanh

import pytest

from ashare_evidence.signal_engine_parts.normalization import (
    FeatureDistributions,
    cross_sectional_mad,
    cross_sectional_median,
    cross_sectional_percentile,
    cross_sectional_robust_scale,
    cross_sectional_zscore,
    feature_summary,
    score_scale_cs,
    winsorize,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

EPS = 1e-9


def _approx_zero(x: float, atol: float = 0.02) -> bool:
    return abs(x) < atol


def _approx_one(x: float, atol: float = 0.02) -> bool:
    return abs(x - 1.0) < atol


# ---------------------------------------------------------------------------
# 1. cross_sectional_zscore
# ---------------------------------------------------------------------------


class TestCrossSectionalZscore:
    """Mean ≈ 0, std ≈ 1 for any cross-section with 3+ symbols."""

    def test_three_symbols(self) -> None:
        raw = {"A": 10.0, "B": 20.0, "C": 30.0}
        result = cross_sectional_zscore(raw)
        vals = list(result.values())
        mean = sum(vals) / len(vals)
        std = (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5
        assert _approx_zero(mean), f"mean={mean} expected ≈0"
        assert _approx_one(std), f"std={std} expected ≈1"

    def test_five_symbols_negative_values(self) -> None:
        raw = {"A": -5.0, "B": -1.0, "C": 0.0, "D": 3.0, "E": 12.0}
        result = cross_sectional_zscore(raw)
        vals = list(result.values())
        mean = sum(vals) / len(vals)
        std = (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5
        assert _approx_zero(mean), f"mean={mean}"
        assert _approx_one(std), f"std={std}"

    def test_preserves_keys(self) -> None:
        raw = {"000001.SZ": 0.05, "600000.SH": -0.02, "000002.SZ": 0.03}
        result = cross_sectional_zscore(raw)
        assert set(result.keys()) == set(raw.keys())

    def test_empty_dict(self) -> None:
        assert cross_sectional_zscore({}) == {}

    def test_single_symbol(self) -> None:
        result = cross_sectional_zscore({"A": 42.0})
        assert result == {"A": 0.0}

    def test_constant_values(self) -> None:
        result = cross_sectional_zscore({"A": 5.0, "B": 5.0, "C": 5.0})
        assert all(v == 0.0 for v in result.values())

    def test_one_obvious_outlier(self) -> None:
        """z-score should flag the outlier with |z| >= 2."""
        raw = {"A": 100.0, "B": 1.0, "C": 1.0, "D": 1.0, "E": 1.0}
        result = cross_sectional_zscore(raw)
        assert abs(result["A"]) >= 2.0


# ---------------------------------------------------------------------------
# 2. winsorize
# ---------------------------------------------------------------------------


class TestWinsorize:
    """Clipping at computed percentile boundaries."""

    def test_default_percentiles(self) -> None:
        values = list(range(1, 101))  # 1..100
        clipped = winsorize(values)
        assert clipped[0] == 2  # 1% of 100 = index 1, value=2
        assert clipped[-1] == 100  # 99% of 100 = index 99 (last element), value=100

    def test_clips_lower_tail(self) -> None:
        values = [0.0, 0.0, 0.0, 50.0, 100.0, 100.0, 100.0]
        clipped = winsorize(values, lower_pct=0.2)
        # 7 * 0.2 = 1.4 -> int = 1, lower bound = sorted[1] = 0.0
        assert min(clipped) >= 0.0

    def test_clips_upper_tail(self) -> None:
        values = [1.0, 2.0, 3.0, 4.0, 100.0, 200.0]
        clipped = winsorize(values, lower_pct=0.0, upper_pct=0.8)
        # 6 * 0.8 = 4.8 -> int = 4, upper bound = sorted[4] = 100.0
        assert all(v <= 100.0 for v in clipped)
        # values above 100 should be clipped down to 100
        assert clipped[-1] == 100.0  # 200 was clipped
        assert clipped[-2] == 100.0  # 100 stays

    def test_boundary_values(self) -> None:
        """With 5 values, lower_pct=0.2 => index 1, upper_pct=0.7 => index 3."""
        values = [10.0, 20.0, 30.0, 40.0, 500.0]
        clipped = winsorize(values, lower_pct=0.2, upper_pct=0.7)
        # lower = sorted[1] = 20, upper = sorted[3] = 40
        assert clipped[0] == 20.0  # 10 was clipped up
        assert clipped[-1] == 40.0  # 500 was clipped down

    def test_empty(self) -> None:
        assert winsorize([]) == []

    def test_single_value(self) -> None:
        assert winsorize([3.14]) == [3.14]

    def test_all_same(self) -> None:
        assert winsorize([5.0, 5.0, 5.0]) == [5.0, 5.0, 5.0]

    def test_preserves_order_input_order(self) -> None:
        """Winsorize should preserve original order (only modifies values)."""
        values = [-999.0, 50.0, 999.0]
        clipped = winsorize(values, lower_pct=0.0, upper_pct=1.0)
        # With pct=0 and 1, bounds are the actual min/max
        # sorted = [-999, 50, 999], lower_idx=0 => -999, upper_idx=2 => 999
        assert clipped == [-999.0, 50.0, 999.0]


# ---------------------------------------------------------------------------
# 3. cross_sectional_percentile
# ---------------------------------------------------------------------------


class TestCrossSectionalPercentile:
    """Min → 0, Max → 1, strictly monotonic."""

    def test_min_is_zero_max_is_one(self) -> None:
        raw = {"A": 1.0, "B": 3.0, "C": 5.0}
        result = cross_sectional_percentile(raw)
        assert result["A"] == 0.0  # smallest
        assert result["C"] == 1.0  # largest

    def test_linear_spacing(self) -> None:
        raw = {"A": 10.0, "B": 20.0, "C": 30.0, "D": 40.0}
        result = cross_sectional_percentile(raw)
        assert result["A"] == 0.0
        assert result["B"] == pytest.approx(1 / 3)
        assert result["C"] == pytest.approx(2 / 3)
        assert result["D"] == 1.0

    def test_duplicate_values(self) -> None:
        """Ties get the same rank position due to sort stability."""
        raw = {"A": 0.0, "B": 0.0, "C": 1.0}
        result = cross_sectional_percentile(raw)
        # sorted: A (0.0), B (0.0), C (1.0)
        assert result["A"] == 0.0
        assert result["B"] == 0.5  # 1 / (3-1)
        assert result["C"] == 1.0

    def test_two_symbols(self) -> None:
        result = cross_sectional_percentile({"A": 1.0, "B": 2.0})
        assert result["A"] == 0.0
        assert result["B"] == 1.0

    def test_one_symbol(self) -> None:
        result = cross_sectional_percentile({"A": 42.0})
        assert result["A"] == 0.5

    def test_empty(self) -> None:
        assert cross_sectional_percentile({}) == {}

    def test_negative_values(self) -> None:
        raw = {"A": -10.0, "B": 0.0, "C": 5.0}
        result = cross_sectional_percentile(raw)
        assert result["A"] == 0.0
        assert result["C"] == 1.0


# ---------------------------------------------------------------------------
# 4. cross_sectional_robust_scale (less sensitive to outliers than z-score)
# ---------------------------------------------------------------------------


class TestCrossSectionalRobustScale:
    """MAD-based scaling with robust location/scale."""

    def test_median_robust_to_outliers(self) -> None:
        """Median (used by robust scale) is not pulled by extreme outlier,
        unlike mean (used by z-score)."""
        raw = {"A": 10.0, "B": 11.0, "C": 12.0, "D": 1_000_000.0}
        med = cross_sectional_median(raw)
        # median should stay near the tight cluster center
        assert 10.0 <= med <= 12.0, f"median={med} pulled by outlier"
        # mean is massively pulled
        vals = list(raw.values())
        v_mean = sum(vals) / len(vals)
        assert v_mean > 250_000  # mean is dominated by the outlier

    def test_median_centered(self) -> None:
        """Symbol at median value should get ~0."""
        # median of {10, 20, 30, 40} is (20+30)/2 = 25
        # But the median() function from statistics picks the middle of sorted list:
        # for 4 items, median is mean of 2nd and 3rd = (20+30)/2 = 25.
        # So no symbol has exactly 25. Let's use an odd count.
        raw = {"A": 10.0, "B": 20.0, "C": 30.0}  # median = 20
        rs = cross_sectional_robust_scale(raw)
        assert _approx_zero(rs["B"]), f"median symbol should be ~0, got {rs['B']}"

    def test_mad_zero_returns_all_zero(self) -> None:
        """If all values are identical, MAD = 0, all scores should be 0."""
        raw = {"A": 5.0, "B": 5.0, "C": 5.0}
        result = cross_sectional_robust_scale(raw)
        assert all(v == 0.0 for v in result.values())

    def test_empty(self) -> None:
        assert cross_sectional_robust_scale({}) == {}

    def test_single_symbol(self) -> None:
        result = cross_sectional_robust_scale({"A": 42.0})
        assert result == {"A": 0.0}

    def test_scale_matches_expected_range(self) -> None:
        """Values within 1 MAD of median should map to roughly (-1, 1)."""
        raw = {"A": 0.0, "B": 5.0, "C": 10.0, "D": 15.0, "E": 20.0}
        rs = cross_sectional_robust_scale(raw)
        # MAD for {0, 5, 10, 15, 20}: median=10, devs=[10,5,0,5,10], MAD=5
        # scale = 5 * 1.4826 ≈ 7.413
        # A: (0 - 10) / 7.413 ≈ -1.35
        # E: (20 - 10) / 7.413 ≈ 1.35
        assert all(abs(v) <= 2.0 for v in rs.values()), (
            f"All robust scores should be within [-2, 2], got {rs}"
        )


# ---------------------------------------------------------------------------
# 5. FeatureDistributions
# ---------------------------------------------------------------------------


class TestFeatureDistributions:
    """Aggregate features across symbols and normalize."""

    def test_collect_and_retrieve(self) -> None:
        dist = FeatureDistributions()
        dist.collect("ret_10d", {"A": 0.05, "B": -0.02})
        dist.collect("ret_10d", {"C": 0.03})
        values = dist.feature_values("ret_10d")
        assert values == {"A": 0.05, "B": -0.02, "C": 0.03}

    def test_multiple_features(self) -> None:
        dist = FeatureDistributions()
        dist.collect("ret_10d", {"A": 0.05, "B": -0.02})
        dist.collect("vol_20d", {"A": 0.30, "B": 0.25})
        assert set(dist.feature_names()) == {"ret_10d", "vol_20d"}

    def test_symbol_count(self) -> None:
        dist = FeatureDistributions()
        dist.collect("ret_10d", {"A": 0.05, "B": -0.02})
        dist.collect("vol_20d", {"B": 0.25, "C": 0.30})
        assert dist.symbol_count() == 3

    def test_symbol_count_empty(self) -> None:
        assert FeatureDistributions().symbol_count() == 0

    def test_feature_zscores(self) -> None:
        dist = FeatureDistributions()
        dist.collect("ret_10d", {"A": 10.0, "B": 20.0, "C": 30.0})
        zs = dist.feature_zscores("ret_10d")
        assert set(zs.keys()) == {"A", "B", "C"}
        vals = list(zs.values())
        v_mean = sum(vals) / len(vals)
        assert _approx_zero(v_mean), f"z-score mean={v_mean}"

    def test_feature_percentiles(self) -> None:
        dist = FeatureDistributions()
        dist.collect("ret_10d", {"A": 1.0, "B": 2.0, "C": 3.0})
        pc = dist.feature_percentiles("ret_10d")
        assert pc["A"] == 0.0
        assert pc["C"] == 1.0

    def test_feature_median_and_mad(self) -> None:
        dist = FeatureDistributions()
        dist.collect("ret_10d", {"A": 1.0, "B": 2.0, "C": 3.0, "D": 100.0})
        med = dist.feature_median("ret_10d")
        # median of {1, 2, 3, 100} = (2+3)/2 = 2.5
        assert med == 2.5
        mad = dist.feature_mad("ret_10d")
        # |v - 2.5| = [1.5, 0.5, 0.5, 97.5], median of those = (0.5+1.5)/2 = 1.0
        assert mad == 1.0

    def test_missing_feature_returns_empty(self) -> None:
        dist = FeatureDistributions()
        assert dist.feature_values("nonexistent") == {}
        assert dist.feature_zscores("nonexistent") == {}
        assert dist.feature_percentiles("nonexistent") == {}
        assert dist.feature_median("nonexistent") == 0.0
        assert dist.feature_mad("nonexistent") == 1.0

    def test_collect_merges_not_replaces(self) -> None:
        dist = FeatureDistributions()
        dist.collect("ret_10d", {"A": 0.05, "B": -0.02})
        dist.collect("ret_10d", {"B": 99.0})  # update B
        assert dist.feature_values("ret_10d") == {"A": 0.05, "B": 99.0}


# ---------------------------------------------------------------------------
# 6. score_scale_cs
# ---------------------------------------------------------------------------


class TestScoreScaleCs:
    """tanh-based scaling: median → ~0, extreme → ±~1."""

    def test_median_value(self) -> None:
        score = score_scale_cs(value=0.0, median_val=0.0, mad_val=1.0)
        assert _approx_zero(score), f"median should map to 0, got {score}"

    def test_extreme_positive(self) -> None:
        """Very large deviation should saturate near +1."""
        score = score_scale_cs(value=1e6, median_val=0.0, mad_val=1.0)
        assert isclose(score, 1.0, abs_tol=EPS)

    def test_extreme_negative(self) -> None:
        score = score_scale_cs(value=-1e6, median_val=0.0, mad_val=1.0)
        assert isclose(score, -1.0, abs_tol=EPS)

    def test_outcome_range(self) -> None:
        """Output must always be in [-1, 1]."""
        for v in [-100.0, -5.0, -1.0, 0.0, 1.0, 5.0, 100.0]:
            s = score_scale_cs(v, median_val=0.0, mad_val=1.0)
            assert -1.0 <= s <= 1.0, f"score={s} out of range for value={v}"

    def test_mad_zero(self) -> None:
        """If MAD is 0 (or effectively 0), score should be 0."""
        assert score_scale_cs(42.0, median_val=10.0, mad_val=0.0) == 0.0
        assert score_scale_cs(42.0, median_val=10.0, mad_val=1e-13) == 0.0

    def test_tanh_formula(self) -> None:
        """Verify the mathematical formula directly."""
        value, med, mad = 5.0, 0.0, 2.0
        expected = tanh((5.0 - 0.0) / (2.0 * 1.5))
        result = score_scale_cs(value, med, mad)
        assert isclose(result, expected, abs_tol=EPS)

    def test_one_mad_away(self) -> None:
        """A value 1 MAD away from median should map to tanh(1/1.5) ≈ 0.58."""
        score = score_scale_cs(value=1.0, median_val=0.0, mad_val=1.0)
        expected = tanh(1.0 / 1.5)
        assert isclose(score, expected, abs_tol=1e-6)


# ---------------------------------------------------------------------------
# 7. feature_summary
# ---------------------------------------------------------------------------


class TestFeatureSummary:
    """Descriptive statistics for feature distributions."""

    def test_count_mean(self) -> None:
        raw = {"A": 10.0, "B": 20.0, "C": 30.0}
        s = feature_summary(raw)
        assert s["count"] == 3
        assert s["mean"] == 20.0

    def test_std(self) -> None:
        raw = {"A": 10.0, "B": 20.0, "C": 30.0}
        s = feature_summary(raw)
        # population std of [10, 20, 30]: sqrt(200/3) ≈ 8.164966
        assert isclose(s["std"], 8.164966, abs_tol=1e-5)

    def test_min_max(self) -> None:
        raw = {"A": -5.0, "B": 0.0, "C": 15.0}
        s = feature_summary(raw)
        assert s["min"] == -5.0
        assert s["max"] == 15.0

    def test_percentiles(self) -> None:
        """With 7 values, quartiles should align."""
        raw = {str(i): float(i * 10) for i in range(7)}  # 0, 10, 20, ..., 60
        s = feature_summary(raw)
        # n=7: p25 = sorted[1] = 10, median = sorted[3] = 30, p75 = sorted[5] = 50
        assert s["p25"] == 10.0
        assert s["median"] == 30.0
        assert s["p75"] == 50.0

    def test_single_value(self) -> None:
        s = feature_summary({"A": 42.0})
        assert s["count"] == 1
        assert s["mean"] == 42.0
        assert s["std"] == 0.0

    def test_empty(self) -> None:
        s = feature_summary({})
        assert s == {"count": 0}

    def test_two_values(self) -> None:
        s = feature_summary({"A": 0.0, "B": 10.0})
        assert s["count"] == 2
        assert s["mean"] == 5.0
        assert s["median"] == 10.0  # n//2 = 1 => sorted[1] = 10
        assert s["min"] == 0.0
        assert s["max"] == 10.0

    def test_rounding_six_decimals(self) -> None:
        raw = {"A": 1.0 / 3.0, "B": 2.0 / 3.0, "C": 1.0}
        s = feature_summary(raw)
        assert s["mean"] == round(2.0 / 3.0, 6)  # 0.666667 rounded to 6 dp
        assert s["count"] == 3


# ---------------------------------------------------------------------------
# 8. cross_sectional_median / cross_sectional_mad (supporting functions)
# ---------------------------------------------------------------------------


class TestCrossSectionalMedian:
    def test_basic(self) -> None:
        assert cross_sectional_median({"A": 1.0, "B": 2.0, "C": 3.0}) == 2.0

    def test_even_count(self) -> None:
        assert cross_sectional_median({"A": 1.0, "B": 3.0}) == 2.0

    def test_empty(self) -> None:
        assert cross_sectional_median({}) == 0.0


class TestCrossSectionalMad:
    def test_basic(self) -> None:
        # values [1, 2, 3], median=2, abs_devs=[1, 0, 1], MAD=1
        assert cross_sectional_mad({"A": 1.0, "B": 2.0, "C": 3.0}) == 1.0

    def test_constant(self) -> None:
        assert cross_sectional_mad({"A": 5.0, "B": 5.0, "C": 5.0}) == 0.0

    def test_empty(self) -> None:
        assert cross_sectional_mad({}) == 1.0

    def test_with_outlier(self) -> None:
        # values [1, 2, 3, 100], median=2.5
        # abs_devs=[1.5, 0.5, 0.5, 97.5], MAD of {0.5, 0.5, 1.5, 97.5} = (0.5+1.5)/2 = 1.0
        mad = cross_sectional_mad({"A": 1.0, "B": 2.0, "C": 3.0, "D": 100.0})
        assert mad == 1.0
