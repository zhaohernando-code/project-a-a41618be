from __future__ import annotations

from math import log, tanh
from statistics import mean
from typing import Any

from ashare_evidence.signal_engine_parts.base import (
    clip,
    factor_direction,
    pct_change,
    safe_pstdev,
    score_scale,
)
from ashare_evidence.signal_engine_parts.normalization import (  # noqa: F401
    cross_sectional_mad,
    cross_sectional_median,
)


def _lagged_return(closes: list[float], horizon: int) -> tuple[float, int]:
    lag = min(horizon, max(len(closes) - 1, 1))
    return pct_change(closes[-1], closes[-(lag + 1)]), lag


def _format_mv(mv: float) -> str:
    """Format market cap value in wan yuan to human-readable string."""
    if mv >= 10000:
        return f"{mv / 10000:.1f}亿"
    return f"{mv:.0f}万"


def compute_size_factor(
    market_bars: list[dict[str, Any]],
    *,
    cross_sectional_stats: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    """Compute size (market cap) factor based on Fama-French (1993) small-cap premium.

    Academic basis:
      - Fama & French (1993): Common risk factors in the returns on stocks and bonds.
      - Liu, Stambaugh & Yuan (2019): Size and value in China (A-share small-cap premium).

    NOTE: Size premium is a LONG-TERM factor. It takes months to years for the
    small-cap premium to materialize. DO NOT use this as a short-term timing signal.
    The score reflects a structural tilt, not a tactical call.
    """
    if not market_bars:
        return {
            "score": 0.0,
            "direction": "neutral",
            "confidence_score": 0.0,
            "drivers": ["缺乏行情数据，市值因子暂不参与评分。"],
            "risks": [],
            "feature_values": {"size_score": 0.0, "available": False},
            "evidence_count": 0,
        }

    latest = market_bars[-1]
    total_mv = latest.get("total_mv")
    if total_mv is None:
        total_mv = latest.get("circ_mv")

    if total_mv is None or total_mv <= 0:
        return {
            "score": 0.0,
            "direction": "neutral",
            "confidence_score": 0.0,
            "drivers": ["市值数据暂不可用，当前不参与评分。注意：市值因子是长期结构性因子，不适用于短线择时。"],
            "risks": ["若 tushare daily_basic 接口未覆盖该标的，市值数据将持续缺失。"],
            "feature_values": {"size_score": 0.0, "available": False, "total_mv": None, "circ_mv": None},
            "evidence_count": 0,
        }

    log_mcap = log(total_mv)

    cs = cross_sectional_stats or {}
    if "log_mcap" in cs:
        median = cs["log_mcap"].get("median", 0)
        mad = cs["log_mcap"].get("mad", 1) or 1
        normalized = (log_mcap - median) / mad
    else:
        # Without cross-sectional context, use hardcoded reference for A-shares.
        # Median log(market cap) for A-shares is approximately ln(50亿) ~ ln(500000万) = 13.12.
        # MAD is approximately 1.2 (one order of magnitude spread).
        median = 13.12
        mad = 1.2
        normalized = (log_mcap - median) / mad

    # Negative sign: smaller market cap -> positive score (small-cap premium)
    score = float(clip(-tanh(normalized)))
    confidence_score = clip(0.35 + abs(score) * 0.20, 0.0, 0.70)

    total_mv_label = _format_mv(total_mv)
    drivers: list[str] = []
    risks: list[str] = []
    if total_mv is not None:
        if score > 0.15:
            drivers.append(
                f"总市值 {total_mv_label}，相对 A 股中位数偏小，小市值溢价作为长期结构性加分。"
            )
        elif score < -0.15:
            drivers.append(
                f"总市值 {total_mv_label}，相对 A 股中位数偏大，大盘股长期溢价有限。"
            )
        else:
            drivers.append(
                f"总市值 {total_mv_label}，接近 A 股中位数水平，市值因子暂无明显倾斜。"
            )
    drivers.append("注意：市值因子是长期结构性因子，建议持仓期 6 个月以上才纳入考量，不适用于短线择时。")

    if total_mv is not None and total_mv < 100000:
        risks.append("小微市值标的流动性风险较高，波幅可能超出模型预期。")
    elif total_mv is not None and total_mv > 10000000:
        risks.append("超大市值标的弹性有限，趋势行情中超额收益空间可能受限。")
    else:
        risks.append("市值信号需要结合价格趋势和流动性判断才能转化为有效建议。")

    feature_values = {
        "size_score": round(score, 4),
        "available": True,
        "total_mv": total_mv,
        "circ_mv": latest.get("circ_mv"),
        "log_mcap": round(log_mcap, 4),
        "normalized_log_mcap": round(normalized, 4),
    }

    return {
        "score": round(score, 4),
        "direction": factor_direction(score),
        "confidence_score": round(confidence_score, 4),
        "drivers": drivers[:3],
        "risks": risks[:3],
        "feature_values": feature_values,
        "window_start": market_bars[0]["observed_at"],
        "window_end": market_bars[-1]["observed_at"],
        "evidence_count": 1,
        "weight": 0.10,
    }


def compute_reversal_factor(market_bars: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute short-term reversal factor from daily market bars.

    Academic basis: Jegadeesh (1990), Lehmann (1990).
    A-shares: Cheema & Nartea (2017) - A-shares exhibit strong short-term reversal
    rather than momentum. Losers bounce back, winners revert.

    Returns positive score when recent losers are expected to rebound.
    """
    closes = [float(item["close_price"]) for item in market_bars]

    ret_5d, lookback_5d = _lagged_return(closes, 5)
    ret_1d, lookback_1d = _lagged_return(closes, 1)

    ret5d_scale = 0.06
    ret1d_scale = 0.03
    signal_5d = score_scale(-ret_5d, ret5d_scale)
    signal_1d = score_scale(-ret_1d, ret1d_scale)
    score = clip(0.6 * signal_5d + 0.4 * signal_1d)
    direction = factor_direction(score)
    confidence = clip(0.3 + abs(score) * 0.25, 0.0, 0.75)

    drivers: list[str] = []
    risks: list[str] = []
    if ret_5d > 0.05:
        drivers.append(f"近 5 日涨幅 {ret_5d:.1%}，短线超买后反转压力增大。")
    elif ret_5d < -0.05:
        drivers.append(f"近 5 日跌幅 {ret_5d:.1%}，超卖后反弹动力增强。")
    if ret_1d > 0.03:
        drivers.append(f"昨日涨幅 {ret_1d:.1%}，日线级别反转观察信号。")
    elif ret_1d < -0.03:
        drivers.append(f"昨日跌幅 {ret_1d:.1%}，日线级别反弹观察信号。")
    if abs(ret_5d) < 0.02 and abs(ret_1d) < 0.01:
        risks.append("短期波动过窄，反转信号缺乏足够的价格空间。")
    if not drivers:
        drivers.append("短期涨跌幅度有限，反转因子暂未形成明显信号。")
    if not risks:
        risks.append("若短期趋势加速延续而非反转，因子将给出错误信号。")

    feature_values = {
        "ret_5d": round(ret_5d, 4),
        "ret_5d_lookback_days": lookback_5d,
        "ret_1d": round(ret_1d, 4),
        "ret_1d_lookback_days": lookback_1d,
        "signal_5d": round(signal_5d, 4),
        "signal_1d": round(signal_1d, 4),
        "reversal_score": round(score, 4),
    }

    return {
        "score": round(score, 4),
        "direction": direction,
        "confidence_score": round(confidence, 4),
        "drivers": drivers[:3],
        "risks": risks[:3],
        "feature_values": feature_values,
        "window_start": market_bars[-(lookback_5d + 1)]["observed_at"],
        "window_end": market_bars[-1]["observed_at"],
        "evidence_count": len(market_bars),
    }


def compute_liquidity_factor(market_bars: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute liquidity factor based on Amihud (2002) ILLIQ measure.

    Higher ILLIQ = higher expected return (liquidity premium).
    The factor prefers liquid stocks over illiquid ones (practical for retail):
      positive score = liquid (low ILLIQ), negative score = illiquid (high ILLIQ).
    """
    closes = [float(item["close_price"]) for item in market_bars]

    illiq_values: list[float] = []
    for idx in range(1, len(closes)):
        ret = abs(pct_change(closes[idx], closes[idx - 1]))
        amount_raw = market_bars[idx].get("amount") or 0
        if float(amount_raw) <= 0:
            amount_raw = float(market_bars[idx]["volume"]) * float(market_bars[idx]["close_price"])
        amount_value = float(amount_raw)
        if amount_value > 0:
            illiq_values.append(ret / amount_value)

    if len(illiq_values) < 5:
        return {
            "score": 0.0,
            "direction": "neutral",
            "confidence_score": 0.0,
            "drivers": ["流动性数据不足（缺少成交额或观测天数 < 5），无法计算 ILLIQ 指标。"],
            "risks": [],
            "feature_values": {
                "avg_illiq_20d": 0.0, "log_illiq": 0.0, "log_illiq_zscore": 0.0,
                "illiq_obs_count": len(illiq_values), "liquidity_score": 0.0,
            },
            "evidence_count": 0,
        }

    avg_illiq_20d = mean(illiq_values[-20:]) if len(illiq_values) >= 20 else mean(illiq_values)
    log_illiq = log(max(avg_illiq_20d, 1e-12))

    # Self-normalization using full available ILLIQ history
    log_illiqs = [log(max(v, 1e-12)) for v in illiq_values]
    log_mean_val = mean(log_illiqs)
    log_std = safe_pstdev(log_illiqs) or 1.0
    log_illiq_zscore = (log_illiq - log_mean_val) / log_std

    # Score = -tanh(zscore): positive when more liquid than typical.
    # score_scale(zscore, 1.0) = tanh(zscore).
    score = clip(-score_scale(log_illiq_zscore, 1.0))
    direction = factor_direction(score)
    confidence = clip(0.35 + abs(score) * 0.2, 0.0, 0.75)

    drivers: list[str] = []
    risks: list[str] = []
    if score > 0.15:
        drivers.append("成交额充裕，流动性指标偏好，适合短线进出。")
    elif score < -0.15:
        drivers.append("流动性偏弱，ILLIQ 较高，需要注意交易成本。")
    if avg_illiq_20d > mean(illiq_values) * 1.5:
        risks.append("近 20 日 ILLIQ 高于历史均值，流动性在收缩。")
    if not drivers:
        drivers.append("流动性指标处于中性区间，暂未形成明显信号。")
    if not risks:
        risks.append("若成交额持续萎缩，ILLIQ 将走高并拖累流动性评分。")

    feature_values = {
        "avg_illiq_20d": round(avg_illiq_20d, 10),
        "log_illiq": round(log_illiq, 4),
        "log_illiq_zscore": round(log_illiq_zscore, 4),
        "illiq_obs_count": len(illiq_values),
        "liquidity_score": round(score, 4),
    }

    return {
        "score": round(score, 4),
        "direction": direction,
        "confidence_score": round(confidence, 4),
        "drivers": drivers[:3],
        "risks": risks[:3],
        "feature_values": feature_values,
        "window_start": market_bars[0]["observed_at"],
        "window_end": market_bars[-1]["observed_at"],
        "evidence_count": len(illiq_values),
    }
