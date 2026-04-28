"""Portfolio payload builder for operations dashboard."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any

from ashare_evidence.contract_status import STATUS_PENDING_REBUILD
from ashare_evidence.intraday_market import INTRADAY_MARKET_TIMEFRAME, get_intraday_market_status

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


