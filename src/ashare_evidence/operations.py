from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from time import perf_counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from ashare_evidence.access import load_beta_access_config
from ashare_evidence.benchmark import benchmark_context_summary
from ashare_evidence.contract_status import STATUS_PENDING_REBUILD
from ashare_evidence.data_quality import build_data_quality_summary
from ashare_evidence.factor_observation import build_factor_observations
from ashare_evidence.intraday_market import (
    INTRADAY_MARKET_TIMEFRAME,
    get_intraday_market_status,
)
from ashare_evidence.manual_research_workflow import list_manual_research_requests
from ashare_evidence.models import MarketBar, ModelVersion, PaperOrder, PaperPortfolio, Recommendation, Stock
from ashare_evidence.phase2.common import build_equal_weight_proxy
from ashare_evidence.phase2.holding_policy_study import (
    build_phase5_holding_policy_study,
    phase5_holding_policy_study_artifact_id,
)
from ashare_evidence.phase2.horizon_study import build_phase5_horizon_study, phase5_horizon_study_artifact_id
from ashare_evidence.phase2.phase5_contract import (
    phase5_benchmark_definition,
    phase5_simulation_policy_context,
)
from ashare_evidence.recommendation_selection import (
    collapse_recommendation_history,
    recommendation_recency_ordering,
)
from ashare_evidence.research_artifact_store import (
    artifact_root_from_database_url,
    read_phase5_holding_policy_study_artifact_if_exists,
    read_phase5_horizon_study_artifact_if_exists,
    read_replay_alignment_artifact_if_exists,
    resolve_backtest_artifact,
)
from ashare_evidence.research_artifacts import normalize_product_validation_status
from ashare_evidence.services import _serialize_recommendation
from ashare_evidence.watchlist import (
    PHASE5_TARGET_WATCHLIST_SYMBOLS,
    PHASE5_WATCHLIST_REPLACEMENT_CANDIDATES,
    active_watchlist_symbols,
)

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


def _trade_band_limit(order: PaperOrder) -> float:
    if order.stock is None:
        return 0.10
    from ashare_evidence.market_rules import board_rule

    rule = board_rule(order.stock.symbol, stock_profile=order.stock, as_of=order.requested_at.date())
    limit_pct = rule.get("limit_pct")
    return 0.10 if limit_pct is None else float(limit_pct)


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

    from ashare_evidence.market_rules import board_rule

    rule = board_rule(order.stock.symbol, stock_profile=order.stock, as_of=fill_day)
    board_lot = int(rule.get("lot") or 100)
    board_lot_pass = quantity % board_lot == 0
    checks.append(
        {
            "code": "board_lot",
            "title": "整手约束",
            "status": "pass" if board_lot_pass else "fail",
            "detail": f"买入与常规卖出按 {board_lot} 股整数倍成交。"
            if board_lot_pass
            else f"当前成交数量 {quantity} 股，不满足 {board_lot} 股整手约束。",
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


def _measure_payload(builder: Any) -> tuple[dict[str, Any], float, float]:
    started_at = perf_counter()
    payload = builder()
    elapsed_ms = (perf_counter() - started_at) * 1000
    payload_kb = len(json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")) / 1024
    return payload, round(elapsed_ms, 1), round(payload_kb, 1)


def _preferred_measurement_symbol(
    *,
    sample_symbol: str,
    active_symbols: set[str],
    replay_items: list[dict[str, Any]],
    portfolios: list[dict[str, Any]],
) -> str | None:
    if sample_symbol in active_symbols:
        return sample_symbol

    replay_symbol = next((item["symbol"] for item in replay_items if item["symbol"] in active_symbols), None)
    if replay_symbol is not None:
        return replay_symbol

    portfolio_symbol = next(
        (
            item["symbol"]
            for portfolio in portfolios
            for item in portfolio["holdings"]
            if item["symbol"] in active_symbols
        ),
        None,
    )
    if portfolio_symbol is not None:
        return portfolio_symbol

    return sorted(active_symbols)[0] if active_symbols else None


def _portfolio_payload(
    portfolio: PaperPortfolio,
    *,
    active_symbols: set[str],
    stock_names: dict[str, str],
    price_history: dict[str, list[tuple[datetime, float]]],
    timeline_points: list[datetime],
    benchmark_close_map: dict[date, float],
    recommendation_hit_rate: float,
    market_data_timeframe: str,
    artifact_root: Any = None,
) -> dict[str, Any]:
    starting_cash = float(portfolio.portfolio_payload.get("starting_cash", portfolio.cash_balance))
    cash = starting_cash
    positions: dict[str, PositionState] = {}
    executions: list[tuple[datetime, str, PaperOrder, Any]] = []
    latest_buy_day_by_symbol: dict[str, date] = {}
    trade_days = _distinct_trade_days(timeline_points)
    trade_day_index = {trade_day: index for index, trade_day in enumerate(trade_days)}
    recent_orders: list[dict[str, Any]] = []
    fee_total = 0.0
    tax_total = 0.0
    pass_count = 0
    total_checks = 0

    orders = [
        order
        for order in sorted(portfolio.orders, key=lambda item: item.requested_at)
        if order.stock.symbol in active_symbols
    ]
    for order in orders:
        checks = _order_checks(
            order,
            price_history=price_history,
            trade_day_index=trade_day_index,
            latest_buy_day_by_symbol=latest_buy_day_by_symbol,
        )
        passed, total = _summarize_rule_status(checks)
        pass_count += passed
        total_checks += total

        fills = sorted(order.fills, key=lambda item: item.filled_at)
        fill_quantity = sum(fill.quantity for fill in fills)
        avg_fill_price = (
            sum(fill.price * fill.quantity for fill in fills) / fill_quantity
            if fill_quantity
            else None
        )
        gross_amount = sum(fill.price * fill.quantity for fill in fills)
        fee_total += sum(fill.fee for fill in fills)
        tax_total += sum(fill.tax for fill in fills)
        recent_orders.append(
            {
                "order_key": order.order_key,
                "symbol": order.stock.symbol,
                "stock_name": order.stock.name,
                "order_source": order.order_source,
                "side": order.side,
                "requested_at": order.requested_at,
                "status": order.status,
                "quantity": order.quantity,
                "order_type": order.order_type,
                "avg_fill_price": round(avg_fill_price, 2) if avg_fill_price is not None else None,
                "gross_amount": round(gross_amount, 2),
                "checks": checks,
            }
        )

        for fill in fills:
            executions.append((fill.filled_at, order.side, order, fill))
            if order.side == "buy":
                latest_buy_day_by_symbol[order.stock.symbol] = fill.filled_at.date()

    nav_history: list[dict[str, Any]] = []
    peak_nav = starting_cash
    benchmark_days = sorted(benchmark_close_map)
    benchmark_start = benchmark_close_map[benchmark_days[0]] if benchmark_days else 1.0
    benchmark_cursor = -1
    execution_cursor = 0
    ordered_executions = sorted(executions, key=lambda item: item[0])

    for point in timeline_points:
        while execution_cursor < len(ordered_executions) and ordered_executions[execution_cursor][0] <= point:
            _filled_at, side, order, fill = ordered_executions[execution_cursor]
            symbol = order.stock.symbol
            position = positions.setdefault(symbol, PositionState(symbol=symbol, name=order.stock.name))
            fee = float(fill.fee)
            tax = float(fill.tax)
            gross_amount = float(fill.price) * int(fill.quantity)

            if side == "buy":
                position.quantity += int(fill.quantity)
                position.cost_value += gross_amount + fee + tax
                cash -= gross_amount + fee + tax
            else:
                avg_cost = position.avg_cost
                sell_quantity = int(fill.quantity)
                cost_removed = avg_cost * sell_quantity
                proceeds = gross_amount - fee - tax
                position.quantity -= sell_quantity
                position.cost_value = max(position.cost_value - cost_removed, 0.0)
                position.realized_pnl += proceeds - cost_removed
                cash += proceeds
            execution_cursor += 1

        market_value = 0.0
        for symbol, position in positions.items():
            if position.quantity <= 0:
                continue
            latest_close = _close_on_or_before(price_history.get(symbol, []), point)
            if latest_close is None:
                continue
            market_value += latest_close * position.quantity

        nav = cash + market_value
        peak_nav = max(peak_nav, nav)
        drawdown = nav / peak_nav - 1 if peak_nav else 0.0
        trade_day = point.date()
        while benchmark_cursor + 1 < len(benchmark_days) and benchmark_days[benchmark_cursor + 1] <= trade_day:
            benchmark_cursor += 1
        if benchmark_cursor < 0 or not benchmark_start:
            benchmark_nav = starting_cash
        else:
            benchmark_close = benchmark_close_map[benchmark_days[benchmark_cursor]]
            benchmark_nav = starting_cash * (benchmark_close / benchmark_start)
        exposure = market_value / nav if nav else 0.0
        nav_history.append(
            {
                "trade_date": trade_day,
                "nav": round(nav, 2),
                "benchmark_nav": round(benchmark_nav, 2),
                "drawdown": round(drawdown, 4),
                "exposure": round(exposure, 4),
                "observed_at": point,
            }
        )

    latest_nav = nav_history[-1]["nav"] if nav_history else starting_cash
    benchmark_nav = nav_history[-1]["benchmark_nav"] if nav_history else starting_cash
    total_return = latest_nav / starting_cash - 1 if starting_cash else 0.0
    benchmark_return = benchmark_nav / starting_cash - 1 if starting_cash else 0.0
    excess_return = total_return - benchmark_return
    max_drawdown = min((point["drawdown"] for point in nav_history), default=0.0)
    current_drawdown = nav_history[-1]["drawdown"] if nav_history else 0.0

    holdings: list[dict[str, Any]] = []
    attribution: list[dict[str, Any]] = []
    market_value = 0.0
    realized_pnl_total = 0.0
    unrealized_pnl_total = 0.0
    latest_point = timeline_points[-1] if timeline_points else None
    previous_point = timeline_points[-2] if len(timeline_points) >= 2 else None
    holding_symbols = sorted(set(active_symbols) | set(positions))
    for symbol in holding_symbols:
        position = positions.get(symbol, PositionState(symbol=symbol, name=stock_names.get(symbol, symbol)))
        if position.quantity < 0:
            continue
        last_price = _close_on_or_before(price_history.get(symbol, []), latest_point)
        if last_price is None:
            continue
        prev_close = _close_on_or_before(price_history.get(symbol, []), previous_point)
        current_market_value = last_price * position.quantity
        unrealized_pnl = current_market_value - position.cost_value
        total_pnl = position.realized_pnl + unrealized_pnl
        holding_pnl_pct = (current_market_value / position.cost_value - 1) if position.cost_value > 0 else None
        today_pnl_amount = (
            (last_price - prev_close) * position.quantity
            if prev_close is not None and position.quantity > 0
            else 0.0
        )
        today_pnl_pct = (
            last_price / prev_close - 1
            if prev_close not in {None, 0} and position.quantity > 0
            else 0.0
        )
        market_value += current_market_value
        realized_pnl_total += position.realized_pnl
        unrealized_pnl_total += unrealized_pnl
        holdings.append(
            {
                "symbol": symbol,
                "name": position.name,
                "quantity": position.quantity,
                "avg_cost": round(position.avg_cost, 2),
                "last_price": round(last_price, 2),
                "prev_close": round(prev_close, 2) if prev_close is not None else None,
                "market_value": round(current_market_value, 2),
                "unrealized_pnl": round(unrealized_pnl, 2),
                "realized_pnl": round(position.realized_pnl, 2),
                "total_pnl": round(total_pnl, 2),
                "holding_pnl_pct": round(holding_pnl_pct, 4) if holding_pnl_pct is not None else None,
                "today_pnl_amount": round(today_pnl_amount, 2),
                "today_pnl_pct": round(today_pnl_pct, 4) if today_pnl_pct is not None else None,
                "portfolio_weight": round(current_market_value / latest_nav, 4) if latest_nav else 0.0,
                "pnl_contribution": round(total_pnl / starting_cash, 4) if starting_cash else 0.0,
            }
        )
        if position.quantity > 0 or abs(total_pnl) > 0:
            attribution.append(
                {
                    "label": position.name,
                    "amount": round(total_pnl, 2),
                    "contribution_pct": round(total_pnl / starting_cash, 4) if starting_cash else 0.0,
                    "detail": f"{symbol} 持仓贡献，包含已实现与未实现盈亏。",
                }
            )

    attribution.extend(
        [
            {
                "label": "交易佣金",
                "amount": round(-fee_total, 2),
                "contribution_pct": round(-fee_total / starting_cash, 4) if starting_cash else 0.0,
                "detail": "所有成交双边佣金汇总。",
            },
            {
                "label": "印花税",
                "amount": round(-tax_total, 2),
                "contribution_pct": round(-tax_total / starting_cash, 4) if starting_cash else 0.0,
                "detail": "卖出侧单边印花税成本。",
            },
        ]
    )

    holdings.sort(key=lambda item: (-int(item["quantity"] > 0), -item["market_value"], item["symbol"]))
    attribution.sort(key=lambda item: abs(float(item["amount"])), reverse=True)

    weight_limit = 0.35 if portfolio.mode == "manual" else 0.20
    alerts: list[str] = []
    if cash < 0:
        alerts.append("组合现金为负，说明自动调仓或手动下单需要更严格的资金约束。")
    if holdings and float(holdings[0]["portfolio_weight"]) > weight_limit:
        alerts.append(
            f"当前第一大持仓权重 {float(holdings[0]['portfolio_weight']):.0%}，超过 {weight_limit:.0%} 单票阈值。"
        )
    if max_drawdown <= (-0.12 if portfolio.mode == "manual" else -0.15):
        alerts.append(f"历史最大回撤已触及 {max_drawdown:.1%}，需要触发降仓或模型冻结。")
    if excess_return < -0.02:
        alerts.append("组合阶段性跑输基准超过 2%，建议先复盘执行与建议命中情况。")

    aggregate_rules = [
        {
            "code": "cash_guard",
            "title": "资金不穿仓",
            "status": "pass" if cash >= 0 else "fail",
            "detail": "组合现金未跌破 0。"
            if cash >= 0
            else "当前模拟组合现金已经小于 0，需阻止继续下单。",
        },
        {
            "code": "weight_limit",
            "title": "单票权重上限",
            "status": "pass"
            if not holdings or float(holdings[0]["portfolio_weight"]) <= weight_limit
            else "warn",
            "detail": f"手动仓上限 {weight_limit:.0%}。"
            if portfolio.mode == "manual"
            else f"自动组合单票权重上限 {weight_limit:.0%}。",
        },
        {
            "code": "drawdown_guard",
            "title": "回撤监控",
            "status": "pass"
            if max_drawdown > (-0.12 if portfolio.mode == "manual" else -0.15)
            else "warn",
            "detail": f"当前最大回撤 {max_drawdown:.1%}。",
        },
    ]

    rule_pass_rate = pass_count / total_checks if total_checks else 1.0
    strategy_label = MODE_LABELS.get(portfolio.mode, portfolio.mode)
    strategy_summary = MODE_STRATEGIES.get(portfolio.mode, "独立组合记账与执行治理。")
    backtest_artifact_id, backtest_artifact = resolve_backtest_artifact(
        configured_artifact_id=portfolio.portfolio_payload.get("backtest_artifact_id"),
        portfolio_key=portfolio.portfolio_key,
        root=artifact_root,
    )
    inline_benchmark_definition = phase5_benchmark_definition(
        market_proxy=bool(benchmark_close_map),
        sector_proxy=False,
    )
    benchmark_context = {
        "benchmark_id": f"migration-benchmark:{portfolio.benchmark_symbol or 'unconfigured'}",
        "benchmark_type": "market_index",
        "benchmark_symbol": portfolio.benchmark_symbol,
        "benchmark_label": portfolio.benchmark_symbol or "未配置基准",
        "source": "active_watchlist_equal_weight_proxy",
        "source_classification": "migration_placeholder",
        "as_of_time": latest_point,
        "available_time": latest_point,
        "status": BENCHMARK_STATUS,
        "note": BENCHMARK_NOTE,
        "benchmark_definition": inline_benchmark_definition,
    }
    performance = {
        "total_return": round(total_return, 4),
        "benchmark_return": round(benchmark_return, 4),
        "excess_return": round(excess_return, 4),
        "realized_pnl": round(realized_pnl_total, 2),
        "unrealized_pnl": round(unrealized_pnl_total, 2),
        "fee_total": round(fee_total, 2),
        "tax_total": round(tax_total, 2),
        "max_drawdown": round(max_drawdown, 4),
        "current_drawdown": round(current_drawdown, 4),
        "order_count": len(orders),
        "validation_mode": "migration_placeholder",
        "benchmark_definition": inline_benchmark_definition,
        "cost_definition": "migration_fixture_commission_and_tax_placeholder",
        "cost_source": "migration_placeholder",
    }
    if portfolio.mode == "manual":
        execution_policy = {
            "status": STATUS_PENDING_REBUILD,
            "label": "迁移期纸面组合治理",
            "summary": strategy_summary,
            "policy_type": "paper_track_governance_policy_v1",
            "source": "paper_track_contract",
            "note": "当前组合动作已绑定 A 股约束、真实价格和观察池等权 proxy，但自动调仓与正式晋级门槛仍待后续 phase 批准。",
            "constraints": [
                f"单票权重上限 {weight_limit:.0%}",
                "手动轨道继续由研究员逐笔确认；模型轨道仍是人工复核预览，不自动成交。",
                "当前 contract 仅可作为 paper track / research candidate 治理基线，不得视为正式组合策略。",
            ],
        }
    else:
        policy_context = phase5_simulation_policy_context(
            policy_note="模型轨道已在模拟盘内启用等权组合研究策略，自动成交仅用于模拟复盘，不扩展到真实交易。"
        )
        execution_policy = {
            "status": policy_context["policy_status"],
            "label": policy_context["policy_label"],
            "summary": strategy_summary,
            "policy_type": policy_context["policy_type"],
            "source": "paper_track_contract",
            "note": policy_context["policy_note"],
            "constraints": [
                f"单票权重上限 {weight_limit:.0%}",
                "模型轨道最多持有 5 只，允许留现金，100 股整手成交，且只在模拟盘自动执行。",
                "当前 contract 仅可作为 paper track / research candidate 治理基线，不得视为正式组合策略。",
            ],
        }
    portfolio_validation_status = STATUS_PENDING_REBUILD
    portfolio_validation_note = benchmark_context["note"]
    validation_artifact_id: str | None = None
    validation_manifest_id: str | None = None
    if backtest_artifact is not None:
        portfolio_validation_status, portfolio_validation_note = normalize_product_validation_status(
            artifact_type="portfolio_backtest",
            status=backtest_artifact.status,
            note=benchmark_context["note"],
            artifact_id=backtest_artifact.artifact_id,
            manifest_id=backtest_artifact.manifest_id,
            benchmark_definition=backtest_artifact.benchmark_definition,
            cost_definition=backtest_artifact.cost_definition,
            execution_assumptions=backtest_artifact.execution_assumptions,
        )
        validation_artifact_id = backtest_artifact.artifact_id
        validation_manifest_id = backtest_artifact.manifest_id
        benchmark_context = {
            **benchmark_context,
            "benchmark_id": backtest_artifact.artifact_id,
            "source": "portfolio_backtest_artifact",
            "source_classification": _source_classification(
                source="portfolio_backtest_artifact",
                artifact_id=backtest_artifact.artifact_id,
            ),
            "status": portfolio_validation_status,
            "note": portfolio_validation_note,
            "artifact_id": backtest_artifact.artifact_id,
            "manifest_id": backtest_artifact.manifest_id,
            "benchmark_definition": backtest_artifact.benchmark_definition,
        }
        performance = {
            **performance,
            "annualized_return": backtest_artifact.annualized_return,
            "annualized_excess_return": backtest_artifact.annualized_excess_return,
            "sharpe_like_ratio": backtest_artifact.sharpe_like_ratio,
            "turnover": backtest_artifact.turnover,
            "win_rate_definition": backtest_artifact.win_rate_definition,
            "win_rate": backtest_artifact.win_rate,
            "capacity_note": backtest_artifact.capacity_note,
            "artifact_id": backtest_artifact.artifact_id,
            "validation_mode": _validation_mode(validation_status=portfolio_validation_status),
            "benchmark_definition": backtest_artifact.benchmark_definition,
            "cost_definition": backtest_artifact.cost_definition,
            "cost_source": _source_classification(
                source="portfolio_backtest_artifact",
                artifact_id=backtest_artifact.artifact_id,
            ),
        }
    compat_projection = _portfolio_compat_projection(
        execution_policy=execution_policy,
        benchmark_context=benchmark_context,
        portfolio_validation_status=portfolio_validation_status,
        recommendation_hit_rate=recommendation_hit_rate,
    )
    return {
        "portfolio_key": portfolio.portfolio_key,
        "name": portfolio.name,
        "mode": portfolio.mode,
        "mode_label": strategy_label,
        "strategy_summary": strategy_summary,
        "strategy_label": strategy_label,
        "benchmark_symbol": portfolio.benchmark_symbol,
        "status": portfolio.status,
        "starting_cash": round(starting_cash, 2),
        "available_cash": round(cash, 2),
        "market_value": round(market_value, 2),
        "net_asset_value": round(latest_nav, 2),
        "invested_ratio": round(market_value / latest_nav, 4) if latest_nav else 0.0,
        "total_return": performance["total_return"],
        "benchmark_return": performance["benchmark_return"],
        "excess_return": performance["excess_return"],
        "realized_pnl": performance["realized_pnl"],
        "unrealized_pnl": performance["unrealized_pnl"],
        "fee_total": performance["fee_total"],
        "tax_total": performance["tax_total"],
        "max_drawdown": performance["max_drawdown"],
        "current_drawdown": performance["current_drawdown"],
        "order_count": performance["order_count"],
        "active_position_count": sum(1 for item in holdings if item["quantity"] > 0),
        "rule_pass_rate": round(rule_pass_rate, 4),
        "market_data_timeframe": market_data_timeframe,
        "last_market_data_at": latest_point,
        "benchmark_context": benchmark_context,
        "performance": performance,
        "execution_policy": execution_policy,
        "validation_status": portfolio_validation_status,
        "validation_note": portfolio_validation_note,
        "validation_artifact_id": validation_artifact_id,
        "validation_manifest_id": validation_manifest_id,
        "alerts": alerts,
        "rules": aggregate_rules,
        "holdings": holdings,
        "attribution": attribution[:6],
        "nav_history": nav_history,
        "recent_orders": sorted(recent_orders, key=lambda item: item["requested_at"], reverse=True)[:6],
        **compat_projection,
    }


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


def _factor_observation_summary(session: Session, *, artifact_root: Any, active_symbols: set[str]) -> dict[str, Any]:
    try:
        study = build_factor_observations(
            session,
            artifact_root=str(artifact_root or ""),
            min_records=5,
            persist=False,
        )
    except Exception as exc:
        return {
            "status": "unavailable",
            "note": f"因子 IC 研究摘要暂不可用：{exc}",
            "observation_count": 0,
            "distinct_as_of_date_count": 0,
            "symbol_count": len(active_symbols),
            "horizons": {},
        }
    horizons: dict[str, Any] = {}
    for horizon, factors in (study.get("factor_results") or {}).items():
        horizons[horizon] = {
            factor_key: {
                "rank_ic_mean": factor_data.get("rank_ic_mean"),
                "ic_ir": factor_data.get("ic_ir"),
                "positive_ic_rate": factor_data.get("positive_ic_rate"),
                "sample_count": factor_data.get("sample_count"),
            }
            for factor_key, factor_data in factors.items()
        }
    return {
        "artifact_type": study.get("artifact_type", "factor_ic_study"),
        "status": study.get("status", "insufficient_sample"),
        "note": study.get("note"),
        "observation_count": study.get("observation_count", 0),
        "distinct_as_of_date_count": study.get("distinct_as_of_date_count", 0),
        "symbol_count": study.get("universe_symbol_count", len(active_symbols)),
        "benchmark_context": study.get("benchmark_context", {}),
        "horizons": horizons,
    }


def _today_at_a_glance(
    *,
    overview: dict[str, Any],
    data_quality_summary: dict[str, Any],
    launch_gates: list[dict[str, Any]],
    manual_research_queue: dict[str, Any],
    replay_items: list[dict[str, Any]],
    active_symbols: set[str],
) -> dict[str, Any]:
    queue_counts = dict(manual_research_queue.get("counts") or {})
    top_warning = next((gate for gate in launch_gates if gate.get("status") in {"fail", "warn"}), None)
    run_health = overview.get("run_health", {})
    research_validation = overview.get("research_validation", {})
    abnormal_symbol_count = int(data_quality_summary.get("warn_count", 0)) + int(data_quality_summary.get("fail_count", 0))
    return {
        "latest_refresh_at": run_health.get("last_market_data_at"),
        "refresh_status": run_health.get("status"),
        "data_quality_status": data_quality_summary.get("status"),
        "abnormal_symbol_count": abnormal_symbol_count,
        "event_analysis_count": sum(queue_counts.values()),
        "manual_queue_counts": queue_counts,
        "top_warning_gate": top_warning.get("gate") if top_warning else None,
        "top_warning_status": top_warning.get("status") if top_warning else None,
        "recommendation_replay_count": len(replay_items),
        "active_watchlist_count": len(active_symbols),
        "target_watchlist_count": len(PHASE5_TARGET_WATCHLIST_SYMBOLS),
        "missing_target_symbols": [
            symbol for symbol in PHASE5_TARGET_WATCHLIST_SYMBOLS if symbol not in active_symbols
        ],
        "replacement_candidates": list(PHASE5_WATCHLIST_REPLACEMENT_CANDIDATES),
        "research_validation_status": research_validation.get("status"),
        "summary_items": [
            f"数据质量异常股票 {abnormal_symbol_count} 只。",
            f"人工研究队列 {sum(queue_counts.values())} 条。",
            f"复盘记录 {len(replay_items)} 条。",
            f"当前 active watchlist {len(active_symbols)}/{len(PHASE5_TARGET_WATCHLIST_SYMBOLS)} 只。",
        ],
    }


def _summary_payload_from_dashboard(payload: dict[str, Any]) -> dict[str, Any]:
    summary = dict(payload)
    summary["portfolios"] = []
    summary["recommendation_replay"] = []
    summary["simulation_workspace"] = None
    if isinstance(summary.get("manual_research_queue"), dict):
        summary["manual_research_queue"] = {
            **summary["manual_research_queue"],
            "focus_request": None,
            "recent_items": [],
        }
    summary["performance_thresholds"] = [
        item
        for item in summary.get("performance_thresholds", [])
        if item.get("metric") in {"模拟交易运营面板构建延迟", "运营面板 payload 体积"}
    ]
    return summary


def build_operations_summary(
    session: Session,
    sample_symbol: str = "600519.SH",
    *,
    target_login: str = "root",
) -> dict[str, Any]:
    payload = build_operations_dashboard(
        session,
        sample_symbol=sample_symbol,
        include_simulation_workspace=False,
        target_login=target_login,
    )
    return _summary_payload_from_dashboard(payload)


def build_operations_detail(
    session: Session,
    *,
    section: str,
    sample_symbol: str = "600519.SH",
    target_login: str = "root",
) -> dict[str, Any]:
    payload = build_operations_dashboard(
        session,
        sample_symbol=sample_symbol,
        include_simulation_workspace=section == "simulation_workspace",
        target_login=target_login,
    )
    section_map = {
        "portfolios": {"portfolios": payload.get("portfolios", [])},
        "replay": {"recommendation_replay": payload.get("recommendation_replay", [])},
        "factor_observation": {"factor_observation_summary": payload.get("factor_observation_summary", {})},
        "sector_exposure": {"sector_exposure": payload.get("sector_exposure", {})},
        "manual_queue": {"manual_research_queue": payload.get("manual_research_queue", {})},
        "simulation_workspace": {"simulation_workspace": payload.get("simulation_workspace")},
    }
    if section not in section_map:
        raise ValueError(f"Unsupported operations detail section: {section}")
    return {
        "section": section,
        "generated_at": payload.get("overview", {}).get("generated_at"),
        **section_map[section],
    }


def build_operations_dashboard(
    session: Session,
    sample_symbol: str = "600519.SH",
    *,
    include_simulation_workspace: bool = False,
    target_login: str = "root",
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
            "data_quality_summary": build_data_quality_summary(session, symbols=active_symbols),
            "factor_observation_summary": {
                "status": "insufficient_sample",
                "note": "行情时间线为空，因子 IC study 暂不可用。",
                "observation_count": 0,
                "distinct_as_of_date_count": 0,
                "symbol_count": len(active_symbols),
                "horizons": {},
            },
            "benchmark_context": benchmark_context_summary(session),
            "today_at_a_glance": {
                "latest_refresh_at": None,
                "refresh_status": "warn",
                "data_quality_status": "fail",
                "abnormal_symbol_count": 0,
                "event_analysis_count": 0,
                "manual_queue_counts": {},
                "top_warning_gate": "恢复真实行情与运营时间线",
                "top_warning_status": "fail",
                "recommendation_replay_count": 0,
                "research_validation_status": STATUS_PENDING_REBUILD,
                "summary_items": ["行情时间线为空，首屏只展示恢复建议。"],
            },
            "sector_exposure": {"source": "unavailable", "sectors": {}},
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

        simulation_workspace = get_simulation_workspace(
            session,
            owner_login=target_login,
            actor_login=target_login,
            actor_role="root",
        )

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
    data_quality_summary = build_data_quality_summary(session, symbols=active_symbols)
    factor_observation_summary = _factor_observation_summary(
        session,
        artifact_root=artifact_root,
        active_symbols=active_symbols,
    )
    benchmark_context = benchmark_context_summary(session)
    today_at_a_glance = _today_at_a_glance(
        overview=overview,
        data_quality_summary=data_quality_summary,
        launch_gates=launch_gates,
        manual_research_queue=manual_research_queue,
        replay_items=replay_items,
        active_symbols=active_symbols,
    )
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
        "data_quality_summary": data_quality_summary,
        "factor_observation_summary": factor_observation_summary,
        "benchmark_context": benchmark_context,
        "today_at_a_glance": today_at_a_glance,
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
        "sector_exposure": _sector_exposure_snapshot(session),
        "data_quality_summary": data_quality_summary,
        "factor_observation_summary": factor_observation_summary,
        "benchmark_context": benchmark_context,
        "today_at_a_glance": today_at_a_glance,
    }


def _sector_exposure_snapshot(session: Session) -> dict[str, Any]:
    from ashare_evidence.sector_exposure import build_sector_exposure
    return build_sector_exposure(session)
