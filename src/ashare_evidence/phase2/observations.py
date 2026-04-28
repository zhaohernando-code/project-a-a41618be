from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from math import sqrt
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ashare_evidence.lineage import build_lineage
from ashare_evidence.models import FeatureSnapshot, MarketBar, NewsEntityLink, NewsItem
from ashare_evidence.phase2.common import pct_change, return_between, safe_mean, safe_std
from ashare_evidence.phase2.constants import PHASE2_FEATURE_VERSION, PHASE2_HORIZONS
from ashare_evidence.phase2.phase5_contract import phase5_benchmark_definition


@dataclass(frozen=True)
class Phase2Observation:
    index: int
    as_of: datetime
    trade_day: date
    score: float
    turnover_estimate: float
    feature_snapshot_keys: list[str]
    feature_values: dict[str, float]


def feature_lineage(record: dict[str, Any], *, symbol: str, feature_name: str, as_of: datetime) -> dict[str, Any]:
    return build_lineage(
        record,
        source_uri=f"pipeline://phase2/{feature_name}/{symbol}/{as_of:%Y%m%d}",
        license_tag="internal-derived",
        usage_scope="internal_research",
        redistribution_scope="none",
    )


def upsert_feature_snapshot(session: Session, snapshot: dict[str, Any], stock_id: int) -> None:
    instance = session.scalar(select(FeatureSnapshot).filter_by(snapshot_key=snapshot["snapshot_key"]))
    payload = {
        "stock_id": stock_id,
        "feature_set_name": snapshot["feature_set_name"],
        "feature_set_version": snapshot["feature_set_version"],
        "as_of": snapshot["as_of"],
        "window_start": snapshot.get("window_start"),
        "window_end": snapshot.get("window_end"),
        "feature_values": snapshot["feature_values"],
        "upstream_refs": snapshot["upstream_refs"],
        "license_tag": snapshot["license_tag"],
        "usage_scope": snapshot["usage_scope"],
        "redistribution_scope": snapshot["redistribution_scope"],
        "source_uri": snapshot["source_uri"],
        "lineage_hash": snapshot["lineage_hash"],
    }
    if instance is None:
        session.add(FeatureSnapshot(snapshot_key=snapshot["snapshot_key"], **payload))
    else:
        for key, value in payload.items():
            setattr(instance, key, value)
    session.flush()


def build_observation_context(
    session: Session,
    *,
    symbol: str,
    bars: list[MarketBar],
    items: list[NewsItem],
    links: list[NewsEntityLink],
    market_proxy: dict[date, float],
    sector_proxy: dict[date, float] | None,
    stock_id: int,
) -> list[Phase2Observation]:
    observations: list[Phase2Observation] = []
    closes = [float(bar.close_price) for bar in bars]
    highs = [float(bar.high_price) for bar in bars]
    amounts = [float(bar.amount) for bar in bars]
    turnovers = [float(bar.turnover_rate or 0.0) for bar in bars]
    returns = [pct_change(closes[index], closes[index - 1]) for index in range(1, len(closes))]
    if len(bars) <= max(PHASE2_HORIZONS) * 2:
        return observations

    for index in range(max(PHASE2_HORIZONS), len(bars) - max(PHASE2_HORIZONS)):
        as_of = bars[index].observed_at
        trade_day = as_of.date()
        momentum_10 = pct_change(closes[index], closes[index - 10])
        momentum_20 = pct_change(closes[index], closes[index - 20])
        momentum_40 = pct_change(closes[index], closes[index - 40])
        volatility_20 = safe_std(returns[index - 20 : index]) * sqrt(20)
        turnover_gap = safe_mean(turnovers[index - 5 : index]) - safe_mean(turnovers[index - 20 : index])
        drawdown_40 = closes[index] / max(highs[index - 39 : index + 1]) - 1
        amount_cv_20 = safe_std(amounts[index - 20 : index]) / max(safe_mean(amounts[index - 20 : index]), 1.0)
        active_links = [link for link in links if as_of - timedelta(days=14) <= link.effective_at <= as_of]
        positive_events = sum(1 for link in active_links if link.impact_direction == "positive")
        negative_events = sum(1 for link in active_links if link.impact_direction == "negative")
        event_balance = (positive_events - negative_events) / max(len(active_links), 1)
        market_proxy_20 = return_between(market_proxy, bars[index - 20].observed_at.date(), trade_day) or 0.0
        sector_proxy_20 = return_between(sector_proxy or {}, bars[index - 20].observed_at.date(), trade_day) if sector_proxy else None
        score = (
            0.28 * momentum_20
            + 0.18 * momentum_10
            + 0.12 * momentum_40
            - 0.12 * volatility_20
            + 0.10 * turnover_gap
            + 0.18 * event_balance
            - 0.12 * amount_cv_20
            + 0.06 * drawdown_40
        )
        turnover_estimate = min(max(abs(score) * 0.16 + abs(turnover_gap) * 2.4, 0.02), 0.65)

        shared_snapshot = {
            "stock_symbol": symbol,
            "as_of": as_of,
            "window_start": bars[index - 40].observed_at,
            "window_end": as_of,
            "feature_set_version": PHASE2_FEATURE_VERSION,
        }
        market_snapshot_key = f"feature-{symbol}-{as_of:%Y%m%d}-phase2-market-snapshot-v1"
        event_snapshot_key = f"feature-{symbol}-{as_of:%Y%m%d}-phase2-event-snapshot-v1"
        fundamental_snapshot_key = f"feature-{symbol}-{as_of:%Y%m%d}-phase2-fundamental-snapshot-v1"
        benchmark_snapshot_key = f"feature-{symbol}-{as_of:%Y%m%d}-phase2-benchmark-snapshot-v1"
        feature_snapshot_key = f"feature-{symbol}-{as_of:%Y%m%d}-phase2-feature-snapshot-v1"

        snapshots = [
            {
                **shared_snapshot,
                "snapshot_key": market_snapshot_key,
                "feature_set_name": "phase2_market_snapshot",
                "feature_values": {
                    "as_of_time": as_of.isoformat(),
                    "available_time": (as_of + timedelta(hours=1, minutes=20)).isoformat(),
                    "source": "tushare_pro_market_snapshot",
                    "coverage": 1.0,
                    "momentum_10d": round(momentum_10, 6),
                    "momentum_20d": round(momentum_20, 6),
                    "momentum_40d": round(momentum_40, 6),
                    "volatility_20d": round(volatility_20, 6),
                    "turnover_gap_20d": round(turnover_gap, 6),
                    "drawdown_40d": round(drawdown_40, 6),
                    "amount_cv_20d": round(amount_cv_20, 6),
                },
                "upstream_refs": [{"type": "market_bar", "key": bars[index].bar_key}],
            },
            {
                **shared_snapshot,
                "snapshot_key": event_snapshot_key,
                "feature_set_name": "phase2_event_snapshot",
                "feature_values": {
                    "as_of_time": as_of.isoformat(),
                    "available_time": as_of.isoformat(),
                    "source": "cninfo_event_snapshot",
                    "coverage": 1.0 if items else 0.0,
                    "positive_event_count_14d": positive_events,
                    "negative_event_count_14d": negative_events,
                    "event_balance_14d": round(event_balance, 6),
                    "linked_event_count_14d": len(active_links),
                },
                "upstream_refs": [{"type": "news_item", "key": item.news_key} for item in items if item.published_at <= as_of][-5:],
            },
            {
                **shared_snapshot,
                "snapshot_key": fundamental_snapshot_key,
                "feature_set_name": "phase2_fundamental_snapshot",
                "feature_values": {
                    "as_of_time": as_of.isoformat(),
                    "available_time": None,
                    "source": "phase2_unavailable_in_fixture",
                    "coverage": 0.0,
                    "status": "excluded_unavailable",
                    "excluded_reason": "正式财务可得时间流水线尚未接入 fixture / offline producer。",
                },
                "upstream_refs": [],
            },
            {
                **shared_snapshot,
                "snapshot_key": benchmark_snapshot_key,
                "feature_set_name": "phase2_benchmark_snapshot",
                "feature_values": {
                    "as_of_time": as_of.isoformat(),
                    "available_time": as_of.isoformat(),
                    "source": "phase2_proxy_benchmark_snapshot",
                    "coverage": 1.0 if market_proxy else 0.0,
                    "market_proxy_return_20d": round(market_proxy_20, 6),
                    "sector_proxy_return_20d": round(float(sector_proxy_20 or 0.0), 6) if sector_proxy_20 is not None else None,
                    "benchmark_definition": phase5_benchmark_definition(
                        market_proxy=bool(market_proxy),
                        sector_proxy=sector_proxy is not None,
                    ),
                },
                "upstream_refs": [{"type": "feature_snapshot", "key": market_snapshot_key}],
            },
            {
                **shared_snapshot,
                "snapshot_key": feature_snapshot_key,
                "feature_set_name": "phase2_feature_snapshot",
                "feature_values": {
                    "as_of_time": as_of.isoformat(),
                    "available_time": as_of.isoformat(),
                    "source": "phase2_feature_snapshot",
                    "coverage": 1.0,
                    "active_feature_groups": ["price_liquidity", "event"],
                    "market_snapshot_key": market_snapshot_key,
                    "event_snapshot_key": event_snapshot_key,
                    "fundamental_snapshot_key": fundamental_snapshot_key,
                    "benchmark_snapshot_key": benchmark_snapshot_key,
                    "phase2_score": round(score, 6),
                    "turnover_estimate": round(turnover_estimate, 6),
                },
                "upstream_refs": [
                    {"type": "feature_snapshot", "key": market_snapshot_key},
                    {"type": "feature_snapshot", "key": event_snapshot_key},
                    {"type": "feature_snapshot", "key": fundamental_snapshot_key},
                    {"type": "feature_snapshot", "key": benchmark_snapshot_key},
                ],
            },
        ]

        for snapshot in snapshots:
            snapshot.update(feature_lineage(snapshot["feature_values"], symbol=symbol, feature_name=snapshot["feature_set_name"], as_of=as_of))
            upsert_feature_snapshot(session, snapshot, stock_id)

        observations.append(
            Phase2Observation(
                index=index,
                as_of=as_of,
                trade_day=trade_day,
                score=float(score),
                turnover_estimate=float(turnover_estimate),
                feature_snapshot_keys=[
                    market_snapshot_key,
                    event_snapshot_key,
                    fundamental_snapshot_key,
                    benchmark_snapshot_key,
                    feature_snapshot_key,
                ],
                feature_values={
                    "momentum_10d": momentum_10,
                    "momentum_20d": momentum_20,
                    "momentum_40d": momentum_40,
                    "volatility_20d": volatility_20,
                    "turnover_gap_20d": turnover_gap,
                    "drawdown_40d": drawdown_40,
                    "amount_cv_20d": amount_cv_20,
                    "event_balance_14d": event_balance,
                },
            )
        )
    return observations
