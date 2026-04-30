from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ashare_evidence.contract_status import STATUS_RESEARCH_CANDIDATE
from ashare_evidence.models import Recommendation, Stock
from ashare_evidence.phase2.common import return_between
from ashare_evidence.phase2.constants import PHASE2_LABEL_DEFINITION, PHASE2_PRIMARY_HORIZON
from ashare_evidence.phase2.phase5_contract import (
    PHASE5_MARKET_REFERENCE_BENCHMARK,
    PHASE5_PRIMARY_RESEARCH_BENCHMARK,
    PHASE5_RESEARCH_UNIVERSE_RULE,
    phase5_benchmark_context,
    phase5_benchmark_definition,
    phase5_research_contract_context,
)
from ashare_evidence.recommendation_selection import (
    collapse_recommendation_history,
    recommendation_recency_ordering,
)
from ashare_evidence.research_artifacts import ReplayAlignmentArtifactView


def replay_hit_status(direction: str, excess_return: float, stock_return: float) -> tuple[str, str]:
    if direction == "buy":
        hit = excess_return > 0 or stock_return > 0
        summary = "偏多建议后，标的在评估窗口内取得正收益或正超额。"
    elif direction == "reduce":
        hit = excess_return < 0 or stock_return < 0
        summary = "偏谨慎建议后，标的在评估窗口内出现负收益或负超额。"
    elif direction == "risk_alert":
        hit = stock_return < 0
        summary = "风险提示后，标的在评估窗口内出现回撤。"
    else:
        hit = abs(excess_return) <= 0.02
        summary = "观察建议后，标的未偏离基准过远。"
    return ("hit", summary) if hit else ("miss", f"{summary} 当前结果说明建议力度仍不足。")


def _select_latest_replay_candidate(
    records: list[Recommendation],
    *,
    series: dict[date, float],
) -> tuple[Recommendation, date, date, float] | None:
    for reviewed in records[1:]:
        trade_days = sorted(day for day in series if day >= reviewed.as_of_data_time.date())
        if len(trade_days) <= PHASE2_PRIMARY_HORIZON:
            continue
        entry_day = reviewed.as_of_data_time.date()
        exit_day = trade_days[min(PHASE2_PRIMARY_HORIZON, len(trade_days) - 1)]
        stock_return = return_between(series, entry_day, exit_day)
        if stock_return is None:
            continue
        return reviewed, entry_day, exit_day, stock_return
    return None


def build_replay_artifacts(
    session: Session,
    *,
    active_symbols: set[str],
    close_maps: dict[str, dict[date, float]],
    market_proxy: dict[date, float],
    market_proxy_context: dict[str, object] | None,
    sector_map: dict[str, str],
) -> list[ReplayAlignmentArtifactView]:
    histories = session.scalars(
        select(Recommendation)
        .join(Stock)
        .options(joinedload(Recommendation.stock))
        .order_by(*recommendation_recency_ordering(stock_symbol=True))
    ).all()
    raw_grouped: dict[str, list[Recommendation]] = defaultdict(list)
    for recommendation in histories:
        raw_grouped[recommendation.stock.symbol].append(recommendation)
    grouped = {
        symbol: collapse_recommendation_history(records)
        for symbol, records in raw_grouped.items()
    }

    artifacts: list[ReplayAlignmentArtifactView] = []
    for symbol, records in grouped.items():
        if symbol not in active_symbols or len(records) < 2:
            continue
        series = close_maps.get(symbol, {})
        replay_candidate = _select_latest_replay_candidate(records, series=series)
        if replay_candidate is None:
            continue
        reviewed, entry_day, exit_day, stock_return = replay_candidate
        benchmark_definition = phase5_benchmark_definition(market_proxy=bool(market_proxy), sector_proxy=False)
        benchmark_return = return_between(market_proxy, entry_day, exit_day)
        if benchmark_return is None:
            benchmark_return = stock_return
            benchmark_definition = "phase2_single_symbol_absolute_return_fallback"
        excess_return = stock_return - benchmark_return
        hit_status, summary = replay_hit_status(reviewed.direction, excess_return, stock_return)
        artifacts.append(
            ReplayAlignmentArtifactView(
                artifact_id=f"replay-alignment:{reviewed.recommendation_key}",
                manifest_id=f"rolling-validation:{reviewed.recommendation_key}",
                recommendation_id=reviewed.id,
                recommendation_key=reviewed.recommendation_key,
                label_definition=PHASE2_LABEL_DEFINITION,
                review_window_definition=f"{PHASE2_PRIMARY_HORIZON} 个交易日 review window",
                entry_rule="recommendation_as_of_close",
                exit_rule=f"next_{PHASE2_PRIMARY_HORIZON}th_trade_day_close",
                benchmark_definition=benchmark_definition,
                benchmark_context={
                    **phase5_benchmark_context(
                        market_proxy=bool(market_proxy),
                        sector_proxy=False,
                        sector_code=sector_map.get(symbol),
                    ),
                    **(market_proxy_context or {}),
                    "symbol_scope": sorted(active_symbols),
                    "universe_rule": PHASE5_RESEARCH_UNIVERSE_RULE,
                },
                hit_definition="buy 看正收益或正超额；reduce / risk_alert 看负收益或负超额；watch 看接近基准。",
                stock_return=round(stock_return, 6),
                benchmark_return=round(benchmark_return, 6),
                excess_return=round(excess_return, 6),
                realized_outcome={"entry_day": entry_day.isoformat(), "exit_day": exit_day.isoformat(), "summary": summary, "hit_status": hit_status},
                alignment_status=STATUS_RESEARCH_CANDIDATE,
                validation_status=STATUS_RESEARCH_CANDIDATE,
                status_note="Replay 已切换到真实后续交易日窗口与 proxy benchmark，对外仍仅可作为 research candidate。",
            )
        )
    return artifacts
