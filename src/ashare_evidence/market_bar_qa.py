from __future__ import annotations

from ashare_evidence.models import MarketBar


def dedup_daily_bars(bars: list[MarketBar]) -> list[MarketBar]:
    by_date: dict[str, list[MarketBar]] = {}
    for bar in bars:
        trade_date = bar.observed_at.strftime("%Y-%m-%d")
        by_date.setdefault(trade_date, []).append(bar)
    deduped: list[MarketBar] = []
    for date_bars in by_date.values():
        if len(date_bars) > 1:
            best = min(date_bars, key=lambda b: abs((b.observed_at.hour * 60 + b.observed_at.minute) - 900))
            deduped.append(best)
        else:
            deduped.append(date_bars[0])
    deduped.sort(key=lambda b: b.observed_at)
    return deduped


def check_bar_unit_consistency(bars: list[MarketBar]) -> list[str]:
    warnings: list[str] = []
    for bar in bars:
        if bar.volume is None or bar.close_price is None or bar.amount is None:
            continue
        implied_amount = float(bar.volume) * float(bar.close_price)
        actual_amount = float(bar.amount)
        if implied_amount <= 0 or actual_amount <= 0:
            continue
        ratio = actual_amount / implied_amount
        if ratio < 0.5 or ratio > 2.0:
            warnings.append(
                f"{bar.observed_at.strftime('%Y-%m-%d')} amount/volume ratio {ratio:.2f} "
                f"异常（amount={actual_amount:.0f}, vol={bar.volume:.0f}, close={bar.close_price:.2f}）"
            )
    return warnings
