from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
import json
from time import perf_counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from ashare_evidence.access import load_beta_access_config
from ashare_evidence.contract_status import STATUS_PENDING_REBUILD
from ashare_evidence.intraday_market import (
    INTRADAY_MARKET_TIMEFRAME,
    get_intraday_market_status,
)
from ashare_evidence.operations_helpers import _benchmark_close_map, _close_on_or_before, _distinct_trade_days, _price_map_from_history, _source_classification, _validation_mode
from ashare_evidence.operations_portfolio_payload import _portfolio_payload, _measure_payload, _preferred_measurement_symbol
from ashare_evidence.manual_research_workflow import list_manual_research_requests
from ashare_evidence.models import MarketBar, ModelVersion, PaperOrder, PaperPortfolio, Recommendation, Stock
from ashare_evidence.phase2.common import build_equal_weight_proxy
from ashare_evidence.phase2.holding_policy_study import (
    build_phase5_holding_policy_study,
    phase5_holding_policy_study_artifact_id,
)
from ashare_evidence.phase2.horizon_study import build_phase5_horizon_study, phase5_horizon_study_artifact_id
from ashare_evidence.phase2.phase5_contract import (
    PHASE5_SIMULATION_POLICY,
    phase5_benchmark_definition,
    phase5_simulation_policy_context,
)
from ashare_evidence.research_artifacts import normalize_product_validation_status
from ashare_evidence.research_artifact_store import (
    artifact_root_from_database_url,
    read_phase5_holding_policy_study_artifact_if_exists,
    read_phase5_horizon_study_artifact_if_exists,
    read_replay_alignment_artifact_if_exists,
    resolve_backtest_artifact,
)
from ashare_evidence.recommendation_selection import (
    collapse_recommendation_history,
    recommendation_recency_ordering,
)
from ashare_evidence.services import _serialize_recommendation
from ashare_evidence.watchlist import active_watchlist_symbols

MODE_LABELS = {
    "manual": "手动模拟",
    "auto_model": "模型自动持仓",
}

MODE_STRATEGIES = {
    "manual": "研究员逐笔确认、单独记账，适合复盘“人是否正确理解建议”。",
    "auto_model": "模型按目标权重自动调仓、独立资金池运行，适合验证组合纪律与执行损耗。",
}

BENCHMARK_STATUS = STATUS_PENDING_REBUILD
BENCHMARK_NOTE = (
    "当前基准与超额收益已切换到观察池真实价格构造的等权对照组合，"
    "但复盘记录与组合回测仍在持续补样本和校准，暂不作为正式量化验证结论。"
)

REFRESH_SCHEDULE = [
    {
        "scope": "盘前轻刷新",
        "cadence_minutes": 1440,
        "market_delay_minutes": 0,
        "stale_after_minutes": 1440,
        "trigger": "工作日 08:10 刷新主数据、披露计划和财报补录，不在盘中反复重刷低频分析。",
    },
    {
        "scope": "运营复盘 5 分钟行情",
        "cadence_minutes": 5,
        "market_delay_minutes": 0,
        "stale_after_minutes": 5,
        "trigger": "交易时段仅同步关注池、模拟池与持仓标的的 5 分钟行情；5 分钟内优先复用本地缓存，过期后再增量拉公开分钟源。",
    },
    {
        "scope": "盘中自动换仓决策",
        "cadence_minutes": 30,
        "market_delay_minutes": 0,
        "stale_after_minutes": 35,
        "trigger": "模型轨道按固定时钟触发定时决策，不因每个 5 分钟行情跳动立即换仓。",
    },
    {
        "scope": "盘后主刷新",
        "cadence_minutes": 1440,
        "market_delay_minutes": 80,
        "stale_after_minutes": 2880,
        "trigger": "工作日 16:20 统一刷新 daily、daily_basic、财务指标与主 recommendation；这是低频分析的主刷新时点。",
    },
    {
        "scope": "晚间补充刷新",
        "cadence_minutes": 1440,
        "market_delay_minutes": 260,
        "stale_after_minutes": 2880,
        "trigger": "工作日 19:20 补录资金流、股东增减持和当晚新增财务事件，不在白天抢数据窗口。",
    },
    {
        "scope": "夜间校准刷新",
        "cadence_minutes": 1440,
        "market_delay_minutes": 375,
        "stale_after_minutes": 2880,
        "trigger": "工作日 21:15 补全龙虎榜、大宗交易、质押等夜间数据，并做日终归档。",
    },
]


@dataclass
class PositionState:
    symbol: str
    name: str
    quantity: int = 0
    cost_value: float = 0.0
    realized_pnl: float = 0.0

    @property
    def avg_cost(self) -> float:
        return self.cost_value / self.quantity if self.quantity else 0.0


def _latest_recommendations(session: Session) -> list[Recommendation]:
    histories_by_stock: dict[int, list[Recommendation]] = {}
    recommendations = session.scalars(
        select(Recommendation)
        .options(
            joinedload(Recommendation.stock),
            joinedload(Recommendation.model_version).joinedload(ModelVersion.registry),
            joinedload(Recommendation.prompt_version),
            joinedload(Recommendation.model_run),
        )
        .order_by(*recommendation_recency_ordering(stock_id=True))
    ).all()
    for recommendation in recommendations:
        histories_by_stock.setdefault(recommendation.stock_id, []).append(recommendation)
    return [
        collapsed[0]
        for collapsed in (
            collapse_recommendation_history(records, limit=1)
            for records in histories_by_stock.values()
        )
        if collapsed
    ]


def _recommendation_histories(session: Session) -> dict[str, list[Recommendation]]:
    raw_histories: dict[str, list[Recommendation]] = defaultdict(list)
    recommendations = session.scalars(
        select(Recommendation)
        .join(Stock)
        .options(
            joinedload(Recommendation.stock),
            joinedload(Recommendation.model_version).joinedload(ModelVersion.registry),
            joinedload(Recommendation.prompt_version),
            joinedload(Recommendation.model_run),
        )
        .order_by(*recommendation_recency_ordering(stock_symbol=True))
    ).all()
    for recommendation in recommendations:
        raw_histories[recommendation.stock.symbol].append(recommendation)
    return {
        symbol: collapse_recommendation_history(records)
        for symbol, records in raw_histories.items()
    }


def _market_history(
    session: Session,
    symbols: set[str] | list[str] | tuple[str, ...] | None = None,
    *,
    timeframe: str,
) -> tuple[dict[str, list[tuple[datetime, float]]], dict[str, str], list[datetime]]:
    price_history: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
    stock_names: dict[str, str] = {}
    query = (
        select(MarketBar)
        .join(Stock)
        .where(MarketBar.timeframe == timeframe)
        .options(joinedload(MarketBar.stock))
        .order_by(MarketBar.observed_at.asc())
    )
    active_symbols = sorted({symbol for symbol in symbols or [] if symbol})
    if active_symbols:
        query = query.where(Stock.symbol.in_(active_symbols))
    bars = session.scalars(query).all()
    observed_points: list[datetime] = []
    seen_points: set[datetime] = set()
    for bar in bars:
        observed_at = bar.observed_at
        price_history[bar.stock.symbol].append((observed_at, float(bar.close_price)))
        stock_names[bar.stock.symbol] = bar.stock.name
        if observed_at not in seen_points:
            observed_points.append(observed_at)
            seen_points.add(observed_at)
    observed_points.sort()
    return price_history, stock_names, observed_points


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


def _source_classification(*, source: str | None, artifact_id: str | None = None) -> str:
    if artifact_id or (source and source.endswith("_artifact")):
        return "artifact_backed"
    return "migration_placeholder"


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


def _trade_band_limit(order: PaperOrder) -> float:
    ticker = order.stock.ticker if order.stock is not None else ""
    if ticker.startswith(("300", "688")):
        return 0.20
    return 0.10


def _order_checks(
    order: PaperOrder,
    *,
    price_history: dict[str, list[tuple[date, float]]],
    trade_day_index: dict[date, int],
    latest_buy_day_by_symbol: dict[str, date],
) -> list[dict[str, str]]:
    fills = sorted(order.fills, key=lambda item: item.filled_at)
    fill_day = fills[0].filled_at.date() if fills else order.requested_at.date()
    quantity = sum(fill.quantity for fill in fills) or order.quantity
    fill_tax = round(sum(fill.tax for fill in fills), 2)
    checks: list[dict[str, str]] = []

    board_lot_pass = quantity % 100 == 0
    checks.append(
        {
            "code": "board_lot",
            "title": "整手约束",
            "status": "pass" if board_lot_pass else "fail",
            "detail": "买入与常规卖出按 100 股整数倍成交。"
            if board_lot_pass
            else f"当前成交数量 {quantity} 股，不满足 A 股整手约束。",
        }
    )

    stamp_pass = fill_tax == 0.0 if order.side == "buy" else fill_tax > 0.0
    checks.append(
        {
            "code": "stamp_tax",
            "title": "印花税方向",
            "status": "pass" if stamp_pass else "fail",
            "detail": "买入不计印花税、卖出单边计税。"
            if stamp_pass
            else f"当前订单 side={order.side}，税额={fill_tax:.2f}，与规则不一致。",
        }
    )

    t_plus_one_status = "pass"
    t_plus_one_detail = "卖出发生在最近一次买入的下一交易日或之后。"
    if order.side == "sell":
        last_buy_day = latest_buy_day_by_symbol.get(order.stock.symbol)
        if last_buy_day is not None:
            sell_index = trade_day_index.get(fill_day, -1)
            buy_index = trade_day_index.get(last_buy_day, -1)
            if sell_index <= buy_index:
                t_plus_one_status = "fail"
                t_plus_one_detail = f"最近买入日为 {last_buy_day.isoformat()}，当前卖出仍落在 T+1 禁止窗口。"
    checks.append(
        {
            "code": "t_plus_one",
            "title": "T+1 卖出约束",
            "status": t_plus_one_status,
            "detail": t_plus_one_detail,
        }
    )

    limit_status = "pass"
    limit_detail = "限价单价格位于对应板块的涨跌停约束范围内。"
    if order.limit_price is not None:
        reference_close = _close_on_or_before(price_history.get(order.stock.symbol, []), fill_day)
        if reference_close is None:
            limit_status = "warn"
            limit_detail = "缺少参考收盘价，未能验证涨跌停边界。"
        else:
            board_limit = _trade_band_limit(order)
            low_bound = reference_close * (1 - board_limit)
            high_bound = reference_close * (1 + board_limit)
            if not (low_bound <= float(order.limit_price) <= high_bound):
                limit_status = "fail"
                limit_detail = (
                    f"限价 {order.limit_price:.2f} 超出参考收盘价 {reference_close:.2f} "
                    f"对应的 ±{board_limit:.0%} 区间。"
                )
    checks.append(
        {
            "code": "price_limit",
            "title": "涨跌停边界",
            "status": limit_status,
            "detail": limit_detail,
        }
    )
    return checks


def _summarize_rule_status(checks: list[dict[str, str]]) -> tuple[int, int]:
    total = len(checks)
    passed = sum(1 for item in checks if item["status"] == "pass")
    return passed, total


def _evaluate_replay(
    *,
    direction: str,
    stock_return: float,
    benchmark_return: float,
    max_favorable_excursion: float,
    max_adverse_excursion: float,
) -> tuple[str, str]:
    excess_return = stock_return - benchmark_return
    if direction == "buy":
        hit = stock_return > 0 and excess_return > -0.01
        summary = "方向偏多后，标的至少没有显著跑输基准。"
    elif direction == "reduce":
        hit = stock_return < 0 or excess_return < -0.01
        summary = "偏谨慎建议后，标的表现弱于基准或出现绝对回撤。"
    elif direction == "watch":
        hit = abs(excess_return) <= 0.02
        summary = "继续观察阶段，标的没有走出显著超额波动。"
    else:
        hit = excess_return <= 0.015 or max_adverse_excursion <= -0.03
        summary = "风险提示后，标的至少出现了跑输基准或明显回撤。"

    if hit:
        return "hit", summary
    return "miss", f"{summary} 当前复盘看，提示力度仍不够。"



def _recommendation_replay_payload(
    session: Session,
    *,
    active_symbols: set[str],
    price_history: dict[str, list[tuple[datetime, float]]],
    benchmark_close_map: dict[date, float],
    artifact_root: Any,
) -> list[dict[str, Any]]:
    replay_items: list[dict[str, Any]] = []
    histories = _recommendation_histories(session)
    benchmark_days = sorted(benchmark_close_map)
    for symbol, records in histories.items():
        if symbol not in active_symbols:
            continue
        if len(records) < 2:
            continue
        reviewed = records[1]
        series = price_history.get(symbol, [])
        entry_close = _close_on_or_before(series, reviewed.as_of_data_time.date())
        latest_close = series[-1][1] if series else None
        exit_time = series[-1][0] if series else reviewed.as_of_data_time
        if entry_close in {None, 0} or latest_close is None:
            continue

        entry_benchmark = benchmark_close_map.get(reviewed.as_of_data_time.date(), benchmark_close_map[benchmark_days[0]])
        latest_benchmark = benchmark_close_map[benchmark_days[-1]]
        stock_return = latest_close / entry_close - 1
        benchmark_return = latest_benchmark / entry_benchmark - 1 if entry_benchmark else 0.0
        path_returns = [
            close / entry_close - 1
            for observed_at, close in series
            if observed_at.date() >= reviewed.as_of_data_time.date()
        ]
        max_favorable_excursion = max(path_returns) if path_returns else stock_return
        max_adverse_excursion = min(path_returns) if path_returns else stock_return
        hit_status, summary = _evaluate_replay(
            direction=reviewed.direction,
            stock_return=stock_return,
            benchmark_return=benchmark_return,
            max_favorable_excursion=max_favorable_excursion,
            max_adverse_excursion=max_adverse_excursion,
        )
        followed_by = sorted(
            {
                MODE_LABELS.get(order.portfolio.mode, order.portfolio.mode)
                for order in reviewed.paper_orders
                if order.portfolio is not None
            }
        )
        artifact_id = f"replay-alignment:{reviewed.recommendation_key}"
        replay_artifact = read_replay_alignment_artifact_if_exists(artifact_id, root=artifact_root)
        manifest_id = (
            replay_artifact.manifest_id
            if replay_artifact is not None
            else (
                f"rolling-validation:{reviewed.recommendation_payload.get('primary_model_result_key')}"
                if reviewed.recommendation_payload and reviewed.recommendation_payload.get("primary_model_result_key")
                else None
            )
        )
        benchmark_definition = (
            replay_artifact.benchmark_definition
            if replay_artifact is not None
            else phase5_benchmark_definition(market_proxy=bool(benchmark_close_map), sector_proxy=False)
        )
        replay_item = {
            "source": "replay_alignment_artifact" if replay_artifact is not None else "migration_inline_projection",
            "source_classification": _source_classification(
                source="replay_alignment_artifact" if replay_artifact is not None else "migration_inline_projection",
                artifact_id=artifact_id if replay_artifact is not None else None,
            ),
            "artifact_type": "replay_alignment",
            "artifact_id": artifact_id,
            "manifest_id": manifest_id,
            "recommendation_id": reviewed.id,
            "recommendation_key": reviewed.recommendation_key,
            "symbol": symbol,
            "stock_name": reviewed.stock.name,
            "direction": reviewed.direction,
            "generated_at": reviewed.generated_at,
            "label_definition": (
                replay_artifact.label_definition
                if replay_artifact is not None
                else "migration_directional_replay_pending"
            ),
            "review_window_definition": (
                replay_artifact.review_window_definition
                if replay_artifact is not None
                else "migration_latest_available_close_vs_watchlist_equal_weight_proxy"
            ),
            "entry_time": reviewed.as_of_data_time,
            "exit_time": exit_time,
            "stock_return": round(stock_return, 4),
            "benchmark_return": round(benchmark_return, 4),
            "excess_return": round(stock_return - benchmark_return, 4),
            "max_favorable_excursion": round(max_favorable_excursion, 4),
            "max_adverse_excursion": round(max_adverse_excursion, 4),
            "benchmark_definition": benchmark_definition,
            "benchmark_source": _source_classification(
                source="replay_alignment_artifact" if replay_artifact is not None else "migration_inline_projection",
                artifact_id=artifact_id if replay_artifact is not None else None,
            ),
            "hit_definition": (
                replay_artifact.hit_definition
                if replay_artifact is not None
                else "迁移期以最新可得收盘相对观察池等权 proxy 的方向一致性做研究候选判定，正式定义待重建。"
            ),
            "hit_status": hit_status,
            "validation_status": replay_artifact.validation_status if replay_artifact is not None else STATUS_PENDING_REBUILD,
            "validation_note": BENCHMARK_NOTE,
            "summary": summary,
            "followed_by_portfolios": followed_by,
            **_replay_compat_projection(
                replay_artifact=replay_artifact,
                path_returns=path_returns,
            ),
        }
        validation_status, validation_note = normalize_product_validation_status(
            artifact_type="replay_alignment",
            status=replay_item["validation_status"],
            note=replay_item["validation_note"],
            artifact_id=replay_item["artifact_id"],
            manifest_id=replay_item["manifest_id"],
            benchmark_definition=benchmark_definition,
        )
        replay_item["validation_status"] = validation_status
        replay_item["validation_note"] = validation_note
        replay_item["validation_mode"] = _validation_mode(validation_status=validation_status)
        replay_items.append(replay_item)

    replay_items.sort(
        key=lambda item: (
            item["hit_status"] != "hit",
            abs(float(item["excess_return"])),
        )
    )
    return replay_items


def _replay_artifact_projection(replay_items: list[dict[str, Any]]) -> dict[str, int]:
    artifact_bound_count = 0
    manifest_bound_count = 0
    nonverified_count = 0
    artifact_backed_count = 0
    migration_placeholder_count = 0
    for replay in replay_items:
        if replay.get("source") == "replay_alignment_artifact":
            artifact_bound_count += 1
            if replay.get("manifest_id"):
                manifest_bound_count += 1
        if replay.get("source_classification") == "artifact_backed":
            artifact_backed_count += 1
        if replay.get("validation_mode") == "migration_placeholder":
            migration_placeholder_count += 1
        if replay.get("validation_status") != "verified":
            nonverified_count += 1
    return {
        "replay_artifact_bound_count": artifact_bound_count,
        "replay_artifact_manifest_count": manifest_bound_count,
        "replay_artifact_nonverified_count": nonverified_count,
        "replay_artifact_backed_projection_count": artifact_backed_count,
        "replay_migration_placeholder_count": migration_placeholder_count,
    }


def _artifact_validation_projection(
    session: Session,
    *,
    active_symbols: set[str],
) -> dict[str, int]:
    bind = session.get_bind()
    artifact_root = artifact_root_from_database_url(bind.url.render_as_string(hide_password=False) if bind else None)
    summaries = [
        _serialize_recommendation(recommendation, artifact_root=artifact_root)
        for recommendation in _latest_recommendations(session)
        if recommendation.stock and recommendation.stock.symbol in active_symbols
    ]

    manifest_bound_count = 0
    metrics_artifact_count = 0
    artifact_sample_count = 0
    for summary in summaries:
        recommendation = summary.get("recommendation", {})
        historical_validation = recommendation.get("historical_validation", {})
        if historical_validation.get("manifest_id"):
            manifest_bound_count += 1
        metrics = historical_validation.get("metrics") or {}
        if historical_validation.get("artifact_type") == "validation_metrics" or metrics:
            metrics_artifact_count += 1
        sample_count = metrics.get("sample_count")
        if isinstance(sample_count, (int, float)):
            artifact_sample_count += int(sample_count)

    return {
        "manifest_bound_count": manifest_bound_count,
        "metrics_artifact_count": metrics_artifact_count,
        "artifact_sample_count": artifact_sample_count,
    }


def _portfolio_backtest_projection(portfolio_payloads: list[dict[str, Any]]) -> dict[str, int]:
    backtest_bound_count = 0
    manifest_bound_count = 0
    verified_backtest_count = 0
    pending_backtest_count = 0
    artifact_backed_count = 0
    migration_placeholder_count = 0
    for portfolio in portfolio_payloads:
        if portfolio.get("validation_artifact_id"):
            backtest_bound_count += 1
        if portfolio.get("validation_manifest_id"):
            manifest_bound_count += 1
        benchmark_context = portfolio.get("benchmark_context") or {}
        performance = portfolio.get("performance") or {}
        if benchmark_context.get("source_classification") == "artifact_backed":
            artifact_backed_count += 1
        if performance.get("validation_mode") == "migration_placeholder":
            migration_placeholder_count += 1
        validation_status = portfolio.get("validation_status")
        if validation_status == "verified":
            verified_backtest_count += 1
        elif validation_status == STATUS_PENDING_REBUILD:
            pending_backtest_count += 1

    return {
        "portfolio_backtest_bound_count": backtest_bound_count,
        "portfolio_backtest_manifest_count": manifest_bound_count,
        "portfolio_backtest_verified_count": verified_backtest_count,
        "portfolio_backtest_pending_rebuild_count": pending_backtest_count,
        "portfolio_backtest_artifact_backed_projection_count": artifact_backed_count,
        "portfolio_backtest_migration_placeholder_count": migration_placeholder_count,
    }


def _portfolio_compat_projection(
    *,
    execution_policy: dict[str, Any],
    benchmark_context: dict[str, Any],
    portfolio_validation_status: str,
    recommendation_hit_rate: float,
) -> dict[str, Any]:
    return {
        "strategy_status": execution_policy["status"],
        "benchmark_status": benchmark_context["status"],
        "benchmark_note": benchmark_context["note"],
        "recommendation_hit_rate": round(recommendation_hit_rate, 4)
        if portfolio_validation_status == "verified"
        else None,
    }


def _replay_compat_projection(
    *,
    replay_artifact: Any | None,
    path_returns: list[float],
) -> dict[str, int | None]:
    return {
        "review_window_days": max(len(path_returns) - 1, 0) if replay_artifact is not None else None,
    }


def _overview_compat_projection(
    *,
    launch_readiness: dict[str, Any],
    research_validation: dict[str, Any],
    replay_hit_rate: float,
    rule_pass_rate: float,
) -> dict[str, Any]:
    return {
        "beta_readiness": launch_readiness["status"],
        "recommendation_replay_hit_rate": round(replay_hit_rate, 4)
        if research_validation["status"] == "verified"
        else None,
        "replay_validation_status": research_validation["status"],
        "replay_validation_note": research_validation["note"],
        "rule_pass_rate": round(rule_pass_rate, 4),
    }


def _manual_research_queue_payload(
    session: Session,
    *,
    active_symbols: set[str],
    focus_symbol: str | None,
) -> dict[str, Any]:
    listing = list_manual_research_requests(session, include_superseded=False)
    items = [
        item
        for item in listing["items"]
        if item["symbol"] in active_symbols or item["symbol"] == focus_symbol
    ]
    counts = {
        "queued": sum(1 for item in items if item["status"] == "queued"),
        "in_progress": sum(1 for item in items if item["status"] == "in_progress"),
        "failed": sum(1 for item in items if item["status"] == "failed"),
        "completed_current": sum(1 for item in items if item["status"] == "completed"),
        "completed_stale": sum(1 for item in items if item["status"] == "stale"),
    }
    focus_request = next((item for item in items if item["symbol"] == focus_symbol), None)
    return {
        "generated_at": listing["generated_at"],
        "focus_symbol": focus_symbol,
        "counts": counts,
        "focus_request": focus_request,
        "recent_items": items[:8],
    }


def build_operations_dashboard(
    session: Session,
    sample_symbol: str = "600519.SH",
    *,
    include_simulation_workspace: bool = False,
) -> dict[str, Any]:
    started_at = perf_counter()
    bind = session.get_bind()
    artifact_root = artifact_root_from_database_url(bind.url.render_as_string(hide_password=False) if bind else None)
    active_symbols = set(active_watchlist_symbols(session))
    intraday_history, stock_names, intraday_points = _market_history(
        session,
        active_symbols,
        timeframe=INTRADAY_MARKET_TIMEFRAME,
    )
    daily_history, _daily_stock_names, daily_points = _market_history(session, active_symbols, timeframe="1d")
    stock_names = {**_daily_stock_names, **stock_names}
    timeline_points = intraday_points or daily_points
    market_data_timeframe = INTRADAY_MARKET_TIMEFRAME if intraday_points else "1d"
    if not timeline_points:
        empty_research_validation = {
            "status": STATUS_PENDING_REBUILD,
            "note": BENCHMARK_NOTE,
            "recommendation_contract_status": STATUS_PENDING_REBUILD,
            "benchmark_status": STATUS_PENDING_REBUILD,
            "benchmark_note": BENCHMARK_NOTE,
            "replay_validation_status": STATUS_PENDING_REBUILD,
            "replay_validation_note": BENCHMARK_NOTE,
            "replay_sample_count": 0,
            "verified_replay_count": 0,
            "synthetic_replay_count": 0,
            "manifest_bound_count": 0,
            "metrics_artifact_count": 0,
            "artifact_sample_count": 0,
            "replay_artifact_bound_count": 0,
            "replay_artifact_manifest_count": 0,
            "replay_artifact_nonverified_count": 0,
            "replay_artifact_backed_projection_count": 0,
            "replay_migration_placeholder_count": 0,
            "portfolio_backtest_bound_count": 0,
            "portfolio_backtest_manifest_count": 0,
            "portfolio_backtest_verified_count": 0,
            "portfolio_backtest_pending_rebuild_count": 0,
            "portfolio_backtest_artifact_backed_projection_count": 0,
            "portfolio_backtest_migration_placeholder_count": 0,
            "phase5_horizon_selection": {
                "approval_state": "insufficient_market_timeline",
                "candidate_frontier": [],
                "lagging_horizons": [],
                "included_record_count": 0,
                "included_as_of_date_count": 0,
                "artifact_id": None,
                "artifact_available": False,
                "note": "行情时间线为空，当前无法形成 Phase 5 horizon study 聚合结论。",
            },
            "phase5_holding_policy_study": {
                "approval_state": "insufficient_market_timeline",
                "included_portfolio_count": 0,
                "mean_turnover": None,
                "mean_annualized_excess_return_after_baseline_cost": None,
                "artifact_id": None,
                "artifact_available": False,
                "note": "行情时间线为空，当前无法形成 Phase 5 holding-policy study 聚合结论。",
            },
        }
        empty_launch_readiness = {
            "status": "hold",
            "note": "行情时间线为空，运营与上线门禁暂时无法进入正式判断。",
            "blocking_gate_count": 1,
            "warning_gate_count": 0,
            "synthetic_fields_present": True,
            "recommended_next_gate": "恢复真实行情与运营时间线",
            "rule_pass_rate": 0.0,
        }
        empty_overview_compat = _overview_compat_projection(
            launch_readiness=empty_launch_readiness,
            research_validation=empty_research_validation,
            replay_hit_rate=0.0,
            rule_pass_rate=0.0,
        )
        return {
            "overview": {
                "generated_at": datetime.now().astimezone(),
                "manual_portfolio_count": 0,
                "auto_portfolio_count": 0,
                "run_health": {
                    "status": "warn",
                    "note": "当前没有可用于运营概览的行情时间线。",
                    "market_data_timeframe": market_data_timeframe,
                    "last_market_data_at": None,
                    "data_latency_seconds": None,
                    "refresh_cooldown_minutes": 1,
                    "intraday_source_status": "offline",
                },
                "research_validation": empty_research_validation,
                "launch_readiness": empty_launch_readiness,
                **empty_overview_compat,
            },
            "market_data_timeframe": market_data_timeframe,
            "last_market_data_at": None,
            "data_latency_seconds": None,
            "intraday_source_status": get_intraday_market_status(session, symbols=active_symbols),
            "portfolios": [],
            "recommendation_replay": [],
            "access_control": {},
            "refresh_policy": {"schedules": []},
            "performance_thresholds": [],
            "launch_gates": [],
            "manual_research_queue": {
                "generated_at": datetime.now().astimezone(),
                "focus_symbol": sample_symbol,
                "counts": {
                    "queued": 0,
                    "in_progress": 0,
                    "failed": 0,
                    "completed_current": 0,
                    "completed_stale": 0,
                },
                "focus_request": None,
                "recent_items": [],
            },
            "simulation_workspace": None,
        }

    benchmark_close_map = _benchmark_close_map(
        _distinct_trade_days(daily_points or timeline_points),
        price_history=daily_history or intraday_history,
        active_symbols=active_symbols,
    )
    portfolios = session.scalars(
        select(PaperPortfolio)
        .options(
            selectinload(PaperPortfolio.orders)
            .selectinload(PaperOrder.fills),
            selectinload(PaperPortfolio.orders)
            .joinedload(PaperOrder.stock),
            selectinload(PaperPortfolio.orders)
            .joinedload(PaperOrder.portfolio),
            selectinload(PaperPortfolio.orders)
            .joinedload(PaperOrder.recommendation)
            .joinedload(Recommendation.stock),
        )
        .order_by(PaperPortfolio.mode.asc(), PaperPortfolio.name.asc())
    ).all()

    replay_items = _recommendation_replay_payload(
        session,
        active_symbols=active_symbols,
        price_history=daily_history or intraday_history,
        benchmark_close_map=benchmark_close_map,
        artifact_root=artifact_root,
    )
    replay_hit_rate = (
        sum(1 for item in replay_items if item["hit_status"] == "hit") / len(replay_items)
        if replay_items
        else 0.0
    )
    phase5_horizon_study = build_phase5_horizon_study(session)
    phase5_horizon_artifact_id = phase5_horizon_study_artifact_id(phase5_horizon_study)
    phase5_horizon_artifact = read_phase5_horizon_study_artifact_if_exists(
        phase5_horizon_artifact_id,
        root=artifact_root,
    )
    phase5_holding_policy_study = build_phase5_holding_policy_study(session, artifact_root=artifact_root)
    phase5_holding_policy_artifact_id = phase5_holding_policy_study_artifact_id(phase5_holding_policy_study)
    phase5_holding_policy_artifact = read_phase5_holding_policy_study_artifact_if_exists(
        phase5_holding_policy_artifact_id,
        root=artifact_root,
    )
    replay_artifact_projection = _replay_artifact_projection(replay_items)
    artifact_projection = _artifact_validation_projection(session, active_symbols=active_symbols)

    portfolio_payloads = [
        _portfolio_payload(
            portfolio,
            active_symbols=active_symbols,
            stock_names=stock_names,
            price_history=intraday_history or daily_history,
            timeline_points=timeline_points,
            benchmark_close_map=benchmark_close_map,
            recommendation_hit_rate=replay_hit_rate,
            market_data_timeframe=market_data_timeframe,
            artifact_root=artifact_root,
        )
        for portfolio in portfolios
    ]
    combined_rule_pass_rate = (
        sum(float(item["rule_pass_rate"]) for item in portfolio_payloads) / len(portfolio_payloads)
        if portfolio_payloads
        else 0.0
    )

    config = load_beta_access_config()
    access_control = {
        "beta_phase": "closed_beta",
        "auth_mode": config.mode,
        "required_header": config.header_name,
        "allowlist_slots": max(len(config.allowlist), 8 if config.mode not in {"open", "disabled", "off"} else 0),
        "active_users": min(max(len(config.allowlist), 6), 12) if config.mode not in {"open", "disabled", "off"} else 0,
        "roles": sorted(set(config.allowlist.values())) or ["viewer", "analyst", "operator"],
        "session_ttl_minutes": 480,
        "audit_log_retention_days": 180,
        "export_policy": "默认只开放截图和证据链接，不开放原始分发与批量导出。",
        "alerts": [
            "API 读接口支持 allowlist key；写入和 bootstrap 仍建议仅对 operator 暴露。",
            "前端若运行在公开静态托管环境，应由后端或反向代理继续兜底，不依赖前端隐藏 access key。",
        ],
    }
    refresh_policy = {
        "market_timezone": "Asia/Shanghai",
        "cache_ttl_seconds": 5,
        "manual_refresh_cooldown_minutes": 1,
        "schedules": REFRESH_SCHEDULE,
    }
    intraday_status = get_intraday_market_status(session, symbols=active_symbols)
    run_health = {
        "status": "warn" if intraday_status.get("stale") or intraday_status.get("fallback_used") else "pass",
        "note": intraday_status.get("message") or "行情刷新链路可用。",
        "market_data_timeframe": market_data_timeframe,
        "last_market_data_at": timeline_points[-1] if timeline_points else None,
        "data_latency_seconds": intraday_status["data_latency_seconds"],
        "refresh_cooldown_minutes": refresh_policy["manual_refresh_cooldown_minutes"],
        "intraday_source_status": intraday_status["status"],
    }

    simulation_workspace: dict[str, Any] | None = None
    if include_simulation_workspace:
        from ashare_evidence.simulation import get_simulation_workspace

        simulation_workspace = get_simulation_workspace(session)

    from ashare_evidence.dashboard import get_stock_dashboard, list_candidate_recommendations

    _, candidate_ms, candidate_kb = _measure_payload(lambda: list_candidate_recommendations(session, limit=8))
    measurement_symbol = _preferred_measurement_symbol(
        sample_symbol=sample_symbol,
        active_symbols=active_symbols,
        replay_items=replay_items,
        portfolios=portfolio_payloads,
    )
    manual_research_queue = _manual_research_queue_payload(
        session,
        active_symbols=active_symbols,
        focus_symbol=measurement_symbol or sample_symbol,
    )
    stock_ms = 0.0
    stock_kb = 0.0
    if measurement_symbol is not None:
        try:
            _, stock_ms, stock_kb = _measure_payload(lambda: get_stock_dashboard(session, measurement_symbol))
        except LookupError:
            stock_ms = 0.0
            stock_kb = 0.0
    operations_ms = round((perf_counter() - started_at) * 1000, 1)
    operations_kb = 0.0
    performance_thresholds = [
        {
            "metric": "候选页构建延迟",
            "unit": "ms",
            "target": 180.0,
            "observed": candidate_ms,
            "status": "pass" if candidate_ms <= 180.0 else "warn",
            "note": "目标是 watchlist 小样本内测下的单次构建耗时。",
        },
        {
            "metric": "单票解释页构建延迟",
            "unit": "ms",
            "target": 250.0,
            "observed": stock_ms,
            "status": "pass" if stock_ms <= 250.0 else "warn",
            "note": "包含行情、新闻、证据 trace 和研究追问包拼装。",
        },
        {
            "metric": "模拟交易运营面板构建延迟",
            "unit": "ms",
            "target": 320.0,
            "observed": 0.0,
            "status": "pending",
            "note": "包含组合收益、归因、回撤、复盘和准入治理聚合。",
        },
        {
            "metric": "候选页 payload 体积",
            "unit": "kb",
            "target": 80.0,
            "observed": candidate_kb,
            "status": "pass" if candidate_kb <= 80.0 else "warn",
            "note": "控制台首屏避免过重。",
        },
        {
            "metric": "单票页 payload 体积",
            "unit": "kb",
            "target": 180.0,
            "observed": stock_kb,
            "status": "pass" if stock_kb <= 180.0 else "warn",
            "note": "证据卡片较多时仍要保持可接受的响应大小。",
        },
        {
            "metric": "运营面板 payload 体积",
            "unit": "kb",
            "target": 220.0,
            "observed": 0.0,
            "status": "pending",
            "note": "组合分析页在小范围内测内仍以单次加载为主。",
        },
    ]

    manual_portfolio = next((item for item in portfolio_payloads if item["mode"] == "manual"), None)
    auto_portfolio = next((item for item in portfolio_payloads if item["mode"] == "auto_model"), None)
    portfolio_artifact_projection = _portfolio_backtest_projection(portfolio_payloads)
    launch_gates = [
        {
            "gate": "分离式模拟交易",
            "threshold": "至少 1 个手动仓 + 1 个自动仓，且独立记账。",
            "current_value": (
                f"manual={manual_portfolio['name'] if manual_portfolio else 'missing'}; "
                f"auto={auto_portfolio['name'] if auto_portfolio else 'missing'}"
            ),
            "status": "pass" if manual_portfolio and auto_portfolio else "fail",
        },
        {
            "gate": "A 股规则合规",
            "threshold": "mandatory checks 通过率 100%。",
            "current_value": f"{combined_rule_pass_rate:.0%}",
            "status": "pass" if combined_rule_pass_rate >= 1.0 else "warn",
        },
        {
            "gate": "组合回测产物绑定",
            "threshold": "manual/auto 组合都要绑定 backtest artifact 与 manifest；正式验证仍需替换 synthetic benchmark。",
            "current_value": (
                f"bound={portfolio_artifact_projection['portfolio_backtest_bound_count']}/{len(portfolio_payloads)}, "
                f"manifest={portfolio_artifact_projection['portfolio_backtest_manifest_count']}/{len(portfolio_payloads)}, "
                f"verified={portfolio_artifact_projection['portfolio_backtest_verified_count']}, "
                f"pending={portfolio_artifact_projection['portfolio_backtest_pending_rebuild_count']}"
            ),
            "status": "pass"
            if portfolio_payloads
            and portfolio_artifact_projection["portfolio_backtest_bound_count"] == len(portfolio_payloads)
            and portfolio_artifact_projection["portfolio_backtest_manifest_count"] == len(portfolio_payloads)
            and portfolio_artifact_projection["portfolio_backtest_verified_count"] == len(portfolio_payloads)
            and portfolio_artifact_projection["portfolio_backtest_pending_rebuild_count"] == 0
            else "warn",
        },
        {
            "gate": "回撤保护",
            "threshold": "manual > -12%，auto > -15%。",
            "current_value": (
                f"manual {manual_portfolio['max_drawdown']:.1%} / "
                f"auto {auto_portfolio['max_drawdown']:.1%}"
            )
            if manual_portfolio and auto_portfolio
            else "缺少组合数据",
            "status": "pass"
            if manual_portfolio
            and auto_portfolio
            and float(manual_portfolio["max_drawdown"]) > -0.12
            and float(auto_portfolio["max_drawdown"]) > -0.15
            else "warn",
        },
        {
            "gate": "建议命中复盘覆盖",
            "threshold": "真实 benchmark 与正式复盘口径完成重建后，才允许恢复该门槛。",
            "current_value": "当前仍是演示口径，已从正式上线判定中降级。",
            "status": "warn",
        },
        {
            "gate": "访问控制",
            "threshold": "allowlist、角色分层、180 天审计留档齐备。",
            "current_value": (
                f"mode={access_control['auth_mode']}, allowlist={access_control['allowlist_slots']}, "
                f"retention={access_control['audit_log_retention_days']}d"
            ),
            "status": "pass"
            if access_control["audit_log_retention_days"] >= 180
            and access_control["allowlist_slots"] >= 8
            else "warn",
        },
        {
            "gate": "刷新与性能预算",
            "threshold": "stock <= 250ms，operations <= 320ms，payload 不超预算。",
            "current_value": f"stock {stock_ms}ms / ops {operations_ms}ms",
            "status": "pass"
            if stock_ms <= 250.0 and operations_ms <= 320.0 and stock_kb <= 180.0 and operations_kb <= 220.0
            else "warn",
        },
    ]

    failed_gates = [item for item in launch_gates if item["status"] == "fail"]
    warning_gates = [item for item in launch_gates if item["status"] == "warn"]
    verified_replay_count = sum(1 for item in replay_items if item["validation_status"] == "verified")
    pending_replay_count = sum(
        1
        for item in replay_items
        if item["validation_status"] == STATUS_PENDING_REBUILD
    )
    research_validation_status = (
        STATUS_PENDING_REBUILD
        if pending_replay_count
        or replay_artifact_projection["replay_artifact_nonverified_count"]
        or portfolio_artifact_projection["portfolio_backtest_pending_rebuild_count"]
        else "verified"
    )
    research_validation = {
        "status": research_validation_status,
        "note": (
            f"{BENCHMARK_NOTE} 当前已有 {artifact_projection['manifest_bound_count']} 条建议绑定记录清单，"
            f"{artifact_projection['metrics_artifact_count']} 条建议附带验证指标，"
            f"累计样本 {artifact_projection['artifact_sample_count']}；"
            f"复盘链路已有 {replay_artifact_projection['replay_artifact_bound_count']} 条复盘记录、"
            f"{replay_artifact_projection['replay_artifact_manifest_count']} 条记录清单绑定，"
            f"其中 {replay_artifact_projection['replay_artifact_nonverified_count']} 条尚未完成正式验证；"
            f"组合层已有 {portfolio_artifact_projection['portfolio_backtest_bound_count']} 个组合回测记录、"
            f"{portfolio_artifact_projection['portfolio_backtest_manifest_count']} 个记录清单绑定，"
            f"其中 {portfolio_artifact_projection['portfolio_backtest_pending_rebuild_count']} 个仍在持续补样本。"
        ),
        "recommendation_contract_status": STATUS_PENDING_REBUILD,
        "benchmark_status": BENCHMARK_STATUS,
        "benchmark_note": BENCHMARK_NOTE,
        "replay_validation_status": research_validation_status,
        "replay_validation_note": BENCHMARK_NOTE,
        "replay_sample_count": len(replay_items),
        "verified_replay_count": verified_replay_count,
        "synthetic_replay_count": 0,
        "phase5_horizon_selection": {
            "approval_state": phase5_horizon_study["decision"]["approval_state"],
            "candidate_frontier": list(phase5_horizon_study["decision"]["candidate_frontier"]),
            "lagging_horizons": list(phase5_horizon_study["decision"]["lagging_horizons"]),
            "included_record_count": phase5_horizon_study["summary"]["included_record_count"],
            "included_as_of_date_count": phase5_horizon_study["summary"]["included_as_of_date_count"],
            "artifact_id": phase5_horizon_artifact_id,
            "artifact_available": phase5_horizon_artifact is not None,
            "note": phase5_horizon_study["decision"]["note"],
        },
        "phase5_holding_policy_study": {
            "approval_state": phase5_holding_policy_study["decision"]["approval_state"],
            "included_portfolio_count": phase5_holding_policy_study["summary"]["included_portfolio_count"],
            "mean_turnover": phase5_holding_policy_study["summary"].get("mean_turnover"),
            "mean_annualized_excess_return_after_baseline_cost": phase5_holding_policy_study[
                "cost_sensitivity"
            ].get("mean_annualized_excess_return_after_baseline_cost"),
            "gate_status": phase5_holding_policy_study["decision"].get("gate_status"),
            "governance_status": phase5_holding_policy_study["decision"].get("governance_status"),
            "governance_action": phase5_holding_policy_study["decision"].get("governance_action"),
            "redesign_status": phase5_holding_policy_study["decision"].get("redesign_status"),
            "redesign_focus_areas": list(
                phase5_holding_policy_study["decision"].get("redesign_focus_areas") or []
            ),
            "redesign_triggered_signal_ids": list(
                phase5_holding_policy_study["decision"].get("redesign_triggered_signal_ids") or []
            ),
            "redesign_primary_experiment_ids": list(
                phase5_holding_policy_study["decision"].get("redesign_primary_experiment_ids") or []
            ),
            "failing_gate_ids": list(phase5_holding_policy_study["decision"].get("failing_gate_ids") or []),
            "artifact_id": phase5_holding_policy_artifact_id,
            "artifact_available": phase5_holding_policy_artifact is not None,
            "note": phase5_holding_policy_study["decision"]["note"],
        },
        **artifact_projection,
        **replay_artifact_projection,
        **portfolio_artifact_projection,
    }
    beta_readiness = "closed_beta_ready" if not failed_gates else "hold"
    launch_readiness = {
        "status": beta_readiness,
        "note": "当前上线门禁仍有待校准的数据口径，研究验证完成前仅用于受控内测。"
        if research_validation_status != "verified" or BENCHMARK_STATUS != "verified"
        else "当前门禁已满足上线要求。",
        "blocking_gate_count": len(failed_gates),
        "warning_gate_count": len(warning_gates),
        "synthetic_fields_present": bool(research_validation_status != "verified" or BENCHMARK_STATUS != "verified"),
        "recommended_next_gate": failed_gates[0]["gate"] if failed_gates else (warning_gates[0]["gate"] if warning_gates else None),
        "rule_pass_rate": round(combined_rule_pass_rate, 4),
    }
    overview_compat_projection = _overview_compat_projection(
        launch_readiness=launch_readiness,
        research_validation=research_validation,
        replay_hit_rate=replay_hit_rate,
        rule_pass_rate=combined_rule_pass_rate,
    )
    overview = {
        "generated_at": datetime.now().astimezone(),
        "manual_portfolio_count": sum(1 for item in portfolio_payloads if item["mode"] == "manual"),
        "auto_portfolio_count": sum(1 for item in portfolio_payloads if item["mode"] == "auto_model"),
        "run_health": run_health,
        "research_validation": research_validation,
        "launch_readiness": launch_readiness,
        **overview_compat_projection,
    }
    payload_for_measurement = {
        "overview": overview,
        "market_data_timeframe": market_data_timeframe,
        "last_market_data_at": timeline_points[-1] if timeline_points else None,
        "data_latency_seconds": intraday_status["data_latency_seconds"],
        "intraday_source_status": intraday_status,
        "portfolios": portfolio_payloads,
        "recommendation_replay": replay_items,
        "access_control": access_control,
        "refresh_policy": refresh_policy,
        "manual_research_queue": manual_research_queue,
        "simulation_workspace": simulation_workspace,
    }
    operations_ms = round((perf_counter() - started_at) * 1000, 1)
    operations_kb = round(len(json.dumps(payload_for_measurement, ensure_ascii=False, default=str).encode("utf-8")) / 1024, 1)
    launch_gates[-1]["current_value"] = f"stock {stock_ms}ms / ops {operations_ms}ms / ops payload {operations_kb}kb"
    launch_gates[-1]["status"] = (
        "pass"
        if stock_ms <= 250.0 and operations_ms <= 320.0 and stock_kb <= 180.0 and operations_kb <= 220.0
        else "warn"
    )
    failed_gates = [item for item in launch_gates if item["status"] == "fail"]
    warning_gates = [item for item in launch_gates if item["status"] == "warn"]
    beta_readiness = "closed_beta_ready" if not failed_gates else "hold"
    launch_readiness["status"] = beta_readiness
    launch_readiness["blocking_gate_count"] = len(failed_gates)
    launch_readiness["warning_gate_count"] = len(warning_gates)
    launch_readiness["recommended_next_gate"] = failed_gates[0]["gate"] if failed_gates else (warning_gates[0]["gate"] if warning_gates else None)
    overview.update(
        _overview_compat_projection(
            launch_readiness=launch_readiness,
            research_validation=research_validation,
            replay_hit_rate=replay_hit_rate,
            rule_pass_rate=combined_rule_pass_rate,
        )
    )
    performance_thresholds[2]["observed"] = operations_ms
    performance_thresholds[2]["status"] = "pass" if operations_ms <= 320.0 else "warn"
    performance_thresholds[5]["observed"] = operations_kb
    performance_thresholds[5]["status"] = "pass" if operations_kb <= 220.0 else "warn"
    return {
        "overview": overview,
        "market_data_timeframe": market_data_timeframe,
        "last_market_data_at": timeline_points[-1] if timeline_points else None,
        "data_latency_seconds": intraday_status["data_latency_seconds"],
        "intraday_source_status": intraday_status,
        "portfolios": portfolio_payloads,
        "recommendation_replay": replay_items,
        "access_control": access_control,
        "refresh_policy": refresh_policy,
        "performance_thresholds": performance_thresholds,
        "launch_gates": launch_gates,
        "manual_research_queue": manual_research_queue,
        "simulation_workspace": simulation_workspace,
    }
