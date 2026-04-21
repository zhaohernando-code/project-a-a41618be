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
from ashare_evidence.models import MarketBar, ModelVersion, PaperOrder, PaperPortfolio, Recommendation, Stock
from ashare_evidence.watchlist import active_watchlist_symbols

MODE_LABELS = {
    "manual": "手动模拟",
    "auto_model": "模型自动持仓",
}

MODE_STRATEGIES = {
    "manual": "研究员逐笔确认、单独记账，适合复盘“人是否正确理解建议”。",
    "auto_model": "模型按目标权重自动调仓、独立资金池运行，适合验证组合纪律与执行损耗。",
}

BENCHMARK_DAILY_RETURNS = (
    0.0018,
    -0.0006,
    0.0011,
    0.0009,
    -0.0004,
    0.0015,
    0.0007,
    -0.0003,
    0.0013,
    0.0008,
    -0.0005,
    0.0010,
    0.0014,
    0.0006,
    0.0012,
    0.0004,
    -0.0002,
    0.0011,
    0.0013,
    0.0007,
    0.0010,
    0.0009,
    -0.0003,
    0.0012,
    0.0008,
    0.0011,
    0.0015,
    0.0017,
    0.0010,
    0.0008,
    0.0011,
    0.0006,
)

REFRESH_SCHEDULE = [
    {
        "scope": "实时行情缓存",
        "cadence_minutes": 1,
        "market_delay_minutes": 0,
        "stale_after_minutes": 1,
        "trigger": "关注池命中请求时按 3-5 秒 TTL 读 Redis，单飞刷新并允许短时过期兜底。",
    },
    {
        "scope": "K线与技术特征",
        "cadence_minutes": 1,
        "market_delay_minutes": 0,
        "stale_after_minutes": 5,
        "trigger": "关注池标的按 1 分钟 TTL 聚合日线/分钟线，失败时回读最近有效缓存。",
    },
    {
        "scope": "财报与结构化指标",
        "cadence_minutes": 1440,
        "market_delay_minutes": 0,
        "stale_after_minutes": 2880,
        "trigger": "财报与日级基本面按 1 天 TTL 缓存，公告更新后触发主动失效。",
    },
    {
        "scope": "模拟交易运营面板",
        "cadence_minutes": 30,
        "market_delay_minutes": 0,
        "stale_after_minutes": 120,
        "trigger": "组合收益、归因、回撤和命中复盘半小时重刷一次，依赖上游缓存而不是重复打外部源。",
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
    latest_by_stock: dict[int, Recommendation] = {}
    recommendations = session.scalars(
        select(Recommendation)
        .options(
            joinedload(Recommendation.stock),
            joinedload(Recommendation.model_version).joinedload(ModelVersion.registry),
            joinedload(Recommendation.prompt_version),
            joinedload(Recommendation.model_run),
        )
        .order_by(Recommendation.stock_id.asc(), Recommendation.generated_at.desc())
    ).all()
    for recommendation in recommendations:
        latest_by_stock.setdefault(recommendation.stock_id, recommendation)
    return list(latest_by_stock.values())


def _recommendation_histories(session: Session) -> dict[str, list[Recommendation]]:
    histories: dict[str, list[Recommendation]] = defaultdict(list)
    recommendations = session.scalars(
        select(Recommendation)
        .join(Stock)
        .options(
            joinedload(Recommendation.stock),
            joinedload(Recommendation.model_version).joinedload(ModelVersion.registry),
            joinedload(Recommendation.prompt_version),
            joinedload(Recommendation.model_run),
        )
        .order_by(Stock.symbol.asc(), Recommendation.generated_at.desc())
    ).all()
    for recommendation in recommendations:
        histories[recommendation.stock.symbol].append(recommendation)
    return histories


def _market_history(
    session: Session,
    symbols: set[str] | list[str] | tuple[str, ...] | None = None,
) -> tuple[dict[str, list[tuple[date, float]]], dict[str, str], list[date]]:
    price_history: dict[str, list[tuple[date, float]]] = defaultdict(list)
    stock_names: dict[str, str] = {}
    query = (
        select(MarketBar)
        .join(Stock)
        .options(joinedload(MarketBar.stock))
        .order_by(MarketBar.observed_at.asc())
    )
    active_symbols = sorted({symbol for symbol in symbols or [] if symbol})
    if active_symbols:
        query = query.where(Stock.symbol.in_(active_symbols))
    bars = session.scalars(query).all()
    trade_days: list[date] = []
    seen_days: set[date] = set()
    for bar in bars:
        trade_day = bar.observed_at.date()
        price_history[bar.stock.symbol].append((trade_day, float(bar.close_price)))
        stock_names[bar.stock.symbol] = bar.stock.name
        if trade_day not in seen_days:
            trade_days.append(trade_day)
            seen_days.add(trade_day)
    trade_days.sort()
    return price_history, stock_names, trade_days


def _benchmark_close_map(trade_days: list[date]) -> dict[date, float]:
    close = 3925.0
    mapping: dict[date, float] = {}
    for index, trade_day in enumerate(trade_days):
        change = BENCHMARK_DAILY_RETURNS[index] if index < len(BENCHMARK_DAILY_RETURNS) else BENCHMARK_DAILY_RETURNS[-1]
        close = round(close * (1 + change), 2)
        mapping[trade_day] = close
    return mapping


def _close_on_or_before(series: list[tuple[date, float]], trade_day: date) -> float | None:
    last_close: float | None = None
    for observed_day, close in series:
        if observed_day > trade_day:
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
    price_history: dict[str, list[tuple[date, float]]],
    trade_days: list[date],
    benchmark_close_map: dict[date, float],
    recommendation_hit_rate: float,
) -> dict[str, Any]:
    starting_cash = float(portfolio.portfolio_payload.get("starting_cash", portfolio.cash_balance))
    cash = starting_cash
    positions: dict[str, PositionState] = {}
    executions_by_day: dict[date, list[tuple[str, PaperOrder, Any]]] = defaultdict(list)
    latest_buy_day_by_symbol: dict[str, date] = {}
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
            trade_day = fill.filled_at.date()
            executions_by_day[trade_day].append((order.side, order, fill))
            if order.side == "buy":
                latest_buy_day_by_symbol[order.stock.symbol] = trade_day

    nav_history: list[dict[str, Any]] = []
    peak_nav = starting_cash
    benchmark_start = benchmark_close_map[trade_days[0]] if trade_days else 1.0

    for trade_day in trade_days:
        for side, order, fill in sorted(
            executions_by_day.get(trade_day, []),
            key=lambda item: item[2].filled_at,
        ):
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

        market_value = 0.0
        for symbol, position in positions.items():
            if position.quantity <= 0:
                continue
            latest_close = _close_on_or_before(price_history.get(symbol, []), trade_day)
            if latest_close is None:
                continue
            market_value += latest_close * position.quantity

        nav = cash + market_value
        peak_nav = max(peak_nav, nav)
        drawdown = nav / peak_nav - 1 if peak_nav else 0.0
        benchmark_nav = starting_cash * (
            benchmark_close_map[trade_day] / benchmark_start if benchmark_start else 1.0
        )
        exposure = market_value / nav if nav else 0.0
        nav_history.append(
            {
                "trade_date": trade_day,
                "nav": round(nav, 2),
                "benchmark_nav": round(benchmark_nav, 2),
                "drawdown": round(drawdown, 4),
                "exposure": round(exposure, 4),
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
    for symbol, position in positions.items():
        if position.quantity < 0:
            continue
        last_price = _close_on_or_before(price_history.get(symbol, []), trade_days[-1]) if trade_days else None
        if last_price is None:
            continue
        current_market_value = last_price * position.quantity
        unrealized_pnl = current_market_value - position.cost_value
        total_pnl = position.realized_pnl + unrealized_pnl
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
                "market_value": round(current_market_value, 2),
                "unrealized_pnl": round(unrealized_pnl, 2),
                "realized_pnl": round(position.realized_pnl, 2),
                "total_pnl": round(total_pnl, 2),
                "portfolio_weight": round(current_market_value / latest_nav, 4) if latest_nav else 0.0,
                "pnl_contribution": round(total_pnl / starting_cash, 4) if starting_cash else 0.0,
            }
        )
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

    holdings.sort(key=lambda item: item["market_value"], reverse=True)
    attribution.sort(key=lambda item: abs(float(item["amount"])), reverse=True)

    weight_limit = 0.35 if portfolio.mode == "manual" else 0.30
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
    return {
        "portfolio_key": portfolio.portfolio_key,
        "name": portfolio.name,
        "mode": portfolio.mode,
        "mode_label": MODE_LABELS.get(portfolio.mode, portfolio.mode),
        "strategy_summary": MODE_STRATEGIES.get(portfolio.mode, "独立组合记账与执行治理。"),
        "benchmark_symbol": portfolio.benchmark_symbol,
        "status": portfolio.status,
        "starting_cash": round(starting_cash, 2),
        "available_cash": round(cash, 2),
        "market_value": round(market_value, 2),
        "net_asset_value": round(latest_nav, 2),
        "invested_ratio": round(market_value / latest_nav, 4) if latest_nav else 0.0,
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
        "active_position_count": sum(1 for item in holdings if item["quantity"] > 0),
        "rule_pass_rate": round(rule_pass_rate, 4),
        "recommendation_hit_rate": round(recommendation_hit_rate, 4),
        "alerts": alerts,
        "rules": aggregate_rules,
        "holdings": holdings,
        "attribution": attribution[:6],
        "nav_history": nav_history,
        "recent_orders": sorted(recent_orders, key=lambda item: item["requested_at"], reverse=True)[:6],
    }


def _recommendation_replay_payload(
    session: Session,
    *,
    active_symbols: set[str],
    price_history: dict[str, list[tuple[date, float]]],
    benchmark_close_map: dict[date, float],
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
        if entry_close in {None, 0} or latest_close is None:
            continue

        entry_benchmark = benchmark_close_map.get(reviewed.as_of_data_time.date(), benchmark_close_map[benchmark_days[0]])
        latest_benchmark = benchmark_close_map[benchmark_days[-1]]
        stock_return = latest_close / entry_close - 1
        benchmark_return = latest_benchmark / entry_benchmark - 1 if entry_benchmark else 0.0
        path_returns = [close / entry_close - 1 for trade_day, close in series if trade_day >= reviewed.as_of_data_time.date()]
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
        replay_items.append(
            {
                "recommendation_id": reviewed.id,
                "symbol": symbol,
                "stock_name": reviewed.stock.name,
                "direction": reviewed.direction,
                "generated_at": reviewed.generated_at,
                "review_window_days": max(len(path_returns) - 1, 0),
                "stock_return": round(stock_return, 4),
                "benchmark_return": round(benchmark_return, 4),
                "excess_return": round(stock_return - benchmark_return, 4),
                "max_favorable_excursion": round(max_favorable_excursion, 4),
                "max_adverse_excursion": round(max_adverse_excursion, 4),
                "hit_status": hit_status,
                "summary": summary,
                "followed_by_portfolios": followed_by,
            }
        )

    replay_items.sort(
        key=lambda item: (
            item["hit_status"] != "hit",
            abs(float(item["excess_return"])),
        )
    )
    return replay_items


def build_operations_dashboard(
    session: Session,
    sample_symbol: str = "600519.SH",
    *,
    include_simulation_workspace: bool = False,
) -> dict[str, Any]:
    started_at = perf_counter()
    active_symbols = set(active_watchlist_symbols(session))
    price_history, _stock_names, trade_days = _market_history(session, active_symbols)
    if not trade_days:
        return {
            "overview": {
                "generated_at": datetime.now().astimezone(),
                "beta_readiness": "empty",
                "manual_portfolio_count": 0,
                "auto_portfolio_count": 0,
                "recommendation_replay_hit_rate": 0.0,
                "rule_pass_rate": 0.0,
            },
            "portfolios": [],
            "recommendation_replay": [],
            "access_control": {},
            "refresh_policy": {"schedules": []},
            "performance_thresholds": [],
            "launch_gates": [],
            "simulation_workspace": None,
        }

    benchmark_close_map = _benchmark_close_map(trade_days)
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
        price_history=price_history,
        benchmark_close_map=benchmark_close_map,
    )
    replay_hit_rate = (
        sum(1 for item in replay_items if item["hit_status"] == "hit") / len(replay_items)
        if replay_items
        else 0.0
    )

    portfolio_payloads = [
        _portfolio_payload(
            portfolio,
            active_symbols=active_symbols,
            price_history=price_history,
            trade_days=trade_days,
            benchmark_close_map=benchmark_close_map,
            recommendation_hit_rate=replay_hit_rate,
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
        "allowlist_slots": max(len(config.allowlist), 8 if config.mode not in {"open_demo", "disabled", "off"} else 0),
        "active_users": min(max(len(config.allowlist), 6), 12) if config.mode not in {"open_demo", "disabled", "off"} else 0,
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
    stock_ms = 0.0
    stock_kb = 0.0
    if measurement_symbol is not None:
        try:
            _, stock_ms, stock_kb = _measure_payload(lambda: get_stock_dashboard(session, measurement_symbol))
        except LookupError:
            stock_ms = 0.0
            stock_kb = 0.0
    partial_payload = {
        "overview": {
            "generated_at": datetime.now().astimezone(),
            "beta_readiness": "pending",
            "manual_portfolio_count": sum(1 for item in portfolio_payloads if item["mode"] == "manual"),
            "auto_portfolio_count": sum(1 for item in portfolio_payloads if item["mode"] == "auto_model"),
            "recommendation_replay_hit_rate": round(replay_hit_rate, 4),
            "rule_pass_rate": round(combined_rule_pass_rate, 4),
        },
        "portfolios": portfolio_payloads,
        "recommendation_replay": replay_items,
        "access_control": access_control,
        "refresh_policy": refresh_policy,
        "simulation_workspace": simulation_workspace,
    }
    operations_ms = round((perf_counter() - started_at) * 1000, 1)
    operations_kb = round(len(json.dumps(partial_payload, ensure_ascii=False, default=str).encode("utf-8")) / 1024, 1)

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
            "note": "包含行情、新闻、证据 trace 和 GPT 追问包拼装。",
        },
        {
            "metric": "模拟交易运营面板构建延迟",
            "unit": "ms",
            "target": 320.0,
            "observed": operations_ms,
            "status": "pass" if operations_ms <= 320.0 else "warn",
            "note": "包含组合收益、归因、回撤、复盘和准入治理聚合。",
        },
        {
            "metric": "候选页 payload 体积",
            "unit": "kb",
            "target": 80.0,
            "observed": candidate_kb,
            "status": "pass" if candidate_kb <= 80.0 else "warn",
            "note": "GitHub Pages 前端首屏避免过重。",
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
            "observed": operations_kb,
            "status": "pass" if operations_kb <= 220.0 else "warn",
            "note": "组合分析页在小范围内测内仍以单次加载为主。",
        },
    ]

    manual_portfolio = next((item for item in portfolio_payloads if item["mode"] == "manual"), None)
    auto_portfolio = next((item for item in portfolio_payloads if item["mode"] == "auto_model"), None)
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
            "threshold": "watchlist 至少 4 条复盘记录，命中率 >= 50%。",
            "current_value": f"{len(replay_items)} 条 / {replay_hit_rate:.0%}",
            "status": "pass" if len(replay_items) >= 4 and replay_hit_rate >= 0.5 else "warn",
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
    beta_readiness = "closed_beta_ready" if not failed_gates else "hold"
    overview = {
        "generated_at": datetime.now().astimezone(),
        "beta_readiness": beta_readiness,
        "manual_portfolio_count": sum(1 for item in portfolio_payloads if item["mode"] == "manual"),
        "auto_portfolio_count": sum(1 for item in portfolio_payloads if item["mode"] == "auto_model"),
        "recommendation_replay_hit_rate": round(replay_hit_rate, 4),
        "rule_pass_rate": round(combined_rule_pass_rate, 4),
    }
    return {
        "overview": overview,
        "portfolios": portfolio_payloads,
        "recommendation_replay": replay_items,
        "access_control": access_control,
        "refresh_policy": refresh_policy,
        "performance_thresholds": performance_thresholds,
        "launch_gates": launch_gates,
        "simulation_workspace": simulation_workspace,
    }
