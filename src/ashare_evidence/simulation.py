from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from ashare_evidence.dashboard import DIRECTION_LABELS
from ashare_evidence.db import utcnow
from ashare_evidence.intraday_market import (
    INTRADAY_DECISION_INTERVAL_SECONDS,
    INTRADAY_MARKET_INTERVAL_SECONDS,
    INTRADAY_MARKET_TIMEFRAME,
    get_intraday_market_status,
)
from ashare_evidence.lineage import build_lineage
from ashare_evidence.models import (
    MarketBar,
    ModelVersion,
    PaperFill,
    PaperOrder,
    PaperPortfolio,
    Recommendation,
    SimulationEvent,
    SimulationSession,
    Stock,
)
from ashare_evidence.operations import _benchmark_close_map, _distinct_trade_days, _market_history, _portfolio_payload
from ashare_evidence.phase2.phase5_contract import (
    PHASE5_BOARD_LOT,
    PHASE5_LONG_DIRECTIONS,
    PHASE5_MAX_POSITION_COUNT,
    PHASE5_MAX_SINGLE_WEIGHT,
    PHASE5_SELL_DIRECTIONS,
    phase5_auto_execution_context,
    phase5_simulation_policy_context,
)
from ashare_evidence.recommendation_selection import (
    collapse_recommendation_history,
    recommendation_recency_ordering,
)
from ashare_evidence.research_artifact_store import (
    artifact_root_from_database_url,
    portfolio_backtest_artifact_id,
)
from ashare_evidence.services import _serialize_recommendation
from ashare_evidence.symbols import normalize_symbol
from ashare_evidence.watchlist import active_watchlist_symbols

SESSION_STATUSES = {
    "draft": "待启动",
    "running": "运行中",
    "paused": "已暂停",
    "ended": "已结束",
}

TRACK_LABELS = {
    "manual": "用户轨道",
    "model": "模型轨道",
    "shared": "共享时间线",
}

DEFAULT_STEP_INTERVAL_SECONDS = INTRADAY_DECISION_INTERVAL_SECONDS
DEFAULT_INITIAL_CASH = 200000.0
DEFAULT_BENCHMARK = "000300.SH"
MAX_TIMELINE_EVENTS = 16
MAX_DECISION_DIFFS = 8
MAX_MODEL_ADVICES = 4
WATCHLIST_SCOPE_ACTIVE = "active_watchlist_default"
WATCHLIST_SCOPE_CUSTOM = "custom"


def _sync_portfolio_backtest_artifact_payload(portfolio: PaperPortfolio) -> None:
    canonical_artifact_id = portfolio_backtest_artifact_id(portfolio.portfolio_key)
    if not canonical_artifact_id:
        return
    payload = dict(portfolio.portfolio_payload or {})
    portfolio.portfolio_payload = {
        **payload,
        "backtest_artifact_id": canonical_artifact_id,
    }


def _auto_execute_requested(simulation_session: SimulationSession) -> bool:
    return bool(simulation_session.session_payload.get("requested_auto_execute_model", simulation_session.auto_execute_model))


def _effective_auto_execute_model(simulation_session: SimulationSession) -> bool:
    return _auto_execute_requested(simulation_session)


def _model_direction_priority(direction: str) -> int:
    return {
        "buy": 4,
        "watch": 3,
        "reduce": 2,
        "risk_alert": 1,
    }.get(direction, 0)


def _model_advice_score(direction: str, confidence_score: float) -> int:
    return _model_direction_priority(direction) * 100 + int(float(confidence_score) * 100)


def _round_down_board_lot(quantity: int) -> int:
    if quantity <= 0:
        return 0
    return int(quantity // PHASE5_BOARD_LOT * PHASE5_BOARD_LOT)


def _board_lot_quantity_for_target_value(target_value: float, price: float) -> int:
    if target_value <= 0 or price <= 0:
        return 0
    return _round_down_board_lot(int(target_value / price))


def _board_lot_quantity_affordable(available_cash: float, price: float) -> int:
    if available_cash <= 0 or price <= 0:
        return 0
    rough_budget = available_cash * 0.999
    return _board_lot_quantity_for_target_value(rough_budget, price)


def _phase5_policy_targets(
    candidates: list[dict[str, Any]],
    *,
    nav: float,
) -> dict[str, dict[str, Any]]:
    if nav <= 0:
        return {}
    target_value = nav * PHASE5_MAX_SINGLE_WEIGHT
    ranked = sorted(
        (
            item
            for item in candidates
            if item["direction"] in PHASE5_LONG_DIRECTIONS
            and _board_lot_quantity_for_target_value(target_value, item["reference_price"]) >= PHASE5_BOARD_LOT
        ),
        key=lambda item: (-_model_direction_priority(item["direction"]), -item["score"], item["symbol"]),
    )
    selected = ranked[:PHASE5_MAX_POSITION_COUNT]
    return {
        item["symbol"]: {
            "target_weight": PHASE5_MAX_SINGLE_WEIGHT,
            "target_quantity": _board_lot_quantity_for_target_value(target_value, item["reference_price"]),
            "rank": index + 1,
        }
        for index, item in enumerate(selected)
    }


def _lineage(payload: dict[str, Any], source_uri: str) -> dict[str, str]:
    return build_lineage(
        payload,
        source_uri=source_uri,
        license_tag="internal-derived",
        usage_scope="internal_research",
        redistribution_scope="none",
    )


def _recommendation_primary_reason(recommendation_view: dict[str, Any]) -> str:
    evidence = recommendation_view.get("evidence") or {}
    primary_drivers = [str(item) for item in evidence.get("primary_drivers", []) if item]
    if primary_drivers:
        return primary_drivers[0]
    supporting_context = [str(item) for item in evidence.get("supporting_context", []) if item]
    if supporting_context:
        return supporting_context[0]
    return str(recommendation_view.get("summary", ""))


def _recommendation_risk_flags(recommendation_view: dict[str, Any], *, limit: int = 3) -> list[str]:
    risk_layer = recommendation_view.get("risk") or {}
    layered_flags = [str(item) for item in risk_layer.get("risk_flags", []) if item]
    invalidators = [str(item) for item in risk_layer.get("invalidators", []) if item]
    coverage_gaps = [str(item) for item in risk_layer.get("coverage_gaps", []) if item]
    return [*layered_flags, *invalidators, *coverage_gaps][:limit]


def _latest_session(session: Session) -> SimulationSession | None:
    sessions = session.scalars(
        select(SimulationSession).order_by(SimulationSession.created_at.desc(), SimulationSession.id.desc())
    ).all()
    for item in sessions:
        if item.status != "ended":
            return item
    return sessions[0] if sessions else None


def _sync_watch_symbols_from_active_watchlist(
    session: Session,
    simulation_session: SimulationSession,
    active_symbols: list[str],
) -> list[str]:
    simulation_session.session_payload = {
        **simulation_session.session_payload,
        "watch_symbols": active_symbols,
        "watch_symbols_scope": WATCHLIST_SCOPE_ACTIVE,
    }
    if not simulation_session.focus_symbol or simulation_session.focus_symbol not in active_symbols:
        simulation_session.focus_symbol = active_symbols[0] if active_symbols else None
    return active_symbols


def _watch_symbols(session: Session, simulation_session: SimulationSession) -> list[str]:
    configured = [
        normalize_symbol(symbol)
        for symbol in simulation_session.session_payload.get("watch_symbols", [])
        if str(symbol).strip()
    ]
    active = active_watchlist_symbols(session)
    scope = str(simulation_session.session_payload.get("watch_symbols_scope") or WATCHLIST_SCOPE_ACTIVE)
    if configured:
        if scope != WATCHLIST_SCOPE_CUSTOM and active and configured != active:
            return _sync_watch_symbols_from_active_watchlist(session, simulation_session, active)
        return configured
    if active:
        return _sync_watch_symbols_from_active_watchlist(session, simulation_session, active)
    return []


def _latest_market_bars(session: Session, symbols: list[str]) -> dict[str, MarketBar]:
    if not symbols:
        return {}
    bars = session.scalars(
        select(MarketBar)
        .join(Stock)
        .where(Stock.symbol.in_(symbols), MarketBar.timeframe == INTRADAY_MARKET_TIMEFRAME)
        .options(joinedload(MarketBar.stock))
        .order_by(Stock.symbol.asc(), MarketBar.observed_at.desc())
    ).all()
    latest: dict[str, MarketBar] = {}
    for bar in bars:
        latest.setdefault(bar.stock.symbol, bar)
    return latest


def _latest_market_data_time_for_session(session: Session, simulation_session: SimulationSession) -> datetime | None:
    watch_symbols = _watch_symbols(session, simulation_session)
    latest_bars = _latest_market_bars(session, watch_symbols)
    if not latest_bars:
        return None
    return max(bar.observed_at for bar in latest_bars.values())


def _latest_recommendations(session: Session, symbols: list[str]) -> dict[str, Recommendation]:
    if not symbols:
        return {}
    recommendations = session.scalars(
        select(Recommendation)
        .join(Stock)
        .where(Stock.symbol.in_(symbols))
        .options(
            joinedload(Recommendation.stock),
            joinedload(Recommendation.model_version).joinedload(ModelVersion.registry),
            joinedload(Recommendation.prompt_version),
            joinedload(Recommendation.model_run),
        )
        .order_by(*recommendation_recency_ordering(stock_symbol=True))
    ).all()
    histories: dict[str, list[Recommendation]] = defaultdict(list)
    for recommendation in recommendations:
        histories[recommendation.stock.symbol].append(recommendation)
    latest: dict[str, Recommendation] = {}
    for symbol, records in histories.items():
        collapsed = collapse_recommendation_history(records, limit=1)
        if collapsed:
            latest[symbol] = collapsed[0]
    return latest


def _session_portfolios(
    session: Session,
    simulation_session: SimulationSession,
) -> tuple[PaperPortfolio, PaperPortfolio]:
    portfolios = session.scalars(
        select(PaperPortfolio)
        .where(
            PaperPortfolio.portfolio_key.in_(
                [simulation_session.manual_portfolio_key or "", simulation_session.model_portfolio_key or ""]
            )
        )
        .options(
            selectinload(PaperPortfolio.orders).selectinload(PaperOrder.fills),
            selectinload(PaperPortfolio.orders).joinedload(PaperOrder.stock),
            selectinload(PaperPortfolio.orders).joinedload(PaperOrder.portfolio),
            selectinload(PaperPortfolio.orders).joinedload(PaperOrder.recommendation).joinedload(Recommendation.stock),
        )
    ).all()
    by_key = {portfolio.portfolio_key: portfolio for portfolio in portfolios}
    manual = by_key.get(simulation_session.manual_portfolio_key or "")
    model = by_key.get(simulation_session.model_portfolio_key or "")
    if manual is None or model is None:
        raise LookupError("模拟轨道组合未初始化。")
    return manual, model


def _create_track_portfolio(session: Session, simulation_session: SimulationSession, track: str) -> PaperPortfolio:
    portfolio_key = f"{simulation_session.session_key}-{track}"
    mode = "manual" if track == "manual" else "auto_model"
    name = "用户手动轨道" if track == "manual" else "模型自动轨道"
    payload = {
        "simulation_session_key": simulation_session.session_key,
        "track_kind": track,
        "starting_cash": simulation_session.initial_cash,
        "watch_symbols": _watch_symbols(session, simulation_session),
        "fill_rule": "latest_price_immediate",
        "timeline_mode": "refresh_step",
        "backtest_artifact_id": portfolio_backtest_artifact_id(portfolio_key),
    }
    portfolio = PaperPortfolio(
        portfolio_key=portfolio_key,
        name=name,
        mode=mode,
        benchmark_symbol=simulation_session.benchmark_symbol,
        base_currency="CNY",
        cash_balance=simulation_session.initial_cash,
        status=simulation_session.status,
        portfolio_payload=payload,
        **_lineage(payload, f"simulation://portfolio/{simulation_session.session_key}/{track}"),
    )
    session.add(portfolio)
    session.flush()
    if track == "manual":
        simulation_session.manual_portfolio_key = portfolio_key
    else:
        simulation_session.model_portfolio_key = portfolio_key
    return portfolio


def _ensure_session_portfolios(session: Session, simulation_session: SimulationSession) -> tuple[PaperPortfolio, PaperPortfolio]:
    manual = None
    model = None
    if simulation_session.manual_portfolio_key or simulation_session.model_portfolio_key:
        try:
            manual, model = _session_portfolios(session, simulation_session)
        except LookupError:
            manual = None
            model = None
    if manual is None:
        manual = _create_track_portfolio(session, simulation_session, "manual")
    if model is None:
        model = _create_track_portfolio(session, simulation_session, "model")
    _sync_portfolio_backtest_artifact_payload(manual)
    _sync_portfolio_backtest_artifact_payload(model)
    return manual, model


def _default_data_time(session: Session, symbols: list[str]) -> datetime:
    latest_bars = _latest_market_bars(session, symbols)
    if latest_bars:
        return max(bar.observed_at for bar in latest_bars.values())
    return utcnow()


def _record_event(
    session: Session,
    simulation_session: SimulationSession,
    *,
    step_index: int,
    track: str,
    event_type: str,
    happened_at: datetime,
    title: str,
    detail: str,
    symbol: str | None = None,
    severity: str = "info",
    event_payload: dict[str, Any] | None = None,
) -> SimulationEvent:
    payload = {
        "session_key": simulation_session.session_key,
        "step_index": step_index,
        "track": track,
        "event_type": event_type,
        "happened_at": happened_at.isoformat(),
        "symbol": symbol,
        "title": title,
        "detail": detail,
        "severity": severity,
        "event_payload": event_payload or {},
    }
    event = SimulationEvent(
        event_key=f"{simulation_session.session_key}-{event_type}-{uuid4().hex[:10]}",
        session_id=simulation_session.id,
        step_index=step_index,
        track=track,
        event_type=event_type,
        happened_at=happened_at,
        symbol=symbol,
        title=title,
        detail=detail,
        severity=severity,
        event_payload=event_payload or {},
        **_lineage(payload, f"simulation://event/{simulation_session.session_key}/{event_type}/{step_index}"),
    )
    session.add(event)
    session.flush()
    return event


def _new_session(
    session: Session,
    *,
    name: str,
    status: str,
    initial_cash: float,
    focus_symbol: str | None,
    watch_symbols: list[str],
    benchmark_symbol: str,
    step_interval_seconds: int,
    auto_execute_model: bool,
    restart_count: int = 0,
) -> SimulationSession:
    created_at = utcnow()
    session_key = f"sim-{created_at:%Y%m%d%H%M%S}-{uuid4().hex[:6]}"
    payload = {
        "watch_symbols": watch_symbols,
        "watch_symbols_scope": WATCHLIST_SCOPE_ACTIVE,
        "step_trigger": "refresh_tick",
        "fill_rule": "latest_price_immediate",
        "supports_manual_step": True,
        "supports_resume": True,
        "restart_count": restart_count,
        "market_data_interval_seconds": INTRADAY_MARKET_INTERVAL_SECONDS,
        "market_data_timeframe": INTRADAY_MARKET_TIMEFRAME,
        "requested_auto_execute_model": auto_execute_model,
    }
    simulation_session = SimulationSession(
        session_key=session_key,
        name=name,
        status=status,
        focus_symbol=focus_symbol,
        benchmark_symbol=benchmark_symbol,
        initial_cash=initial_cash,
        current_step=0,
        step_interval_seconds=step_interval_seconds,
        auto_execute_model=auto_execute_model,
        restart_count=restart_count,
        started_at=None,
        last_resumed_at=None,
        paused_at=None,
        ended_at=None,
        last_data_time=_default_data_time(session, watch_symbols),
        session_payload=payload,
        **_lineage(
            {
                "session_key": session_key,
                "status": status,
                "watch_symbols": watch_symbols,
                "initial_cash": initial_cash,
                "step_interval_seconds": step_interval_seconds,
            },
            f"simulation://session/{session_key}",
        ),
    )
    session.add(simulation_session)
    session.flush()
    _ensure_session_portfolios(session, simulation_session)
    _record_event(
        session,
        simulation_session,
        step_index=0,
        track="shared",
        event_type="session_created",
        happened_at=created_at,
        title="模拟进程已创建",
        detail="双轨同步模拟已建档，等待启动。",
        event_payload={"watch_symbols": watch_symbols, "focus_symbol": focus_symbol},
    )
    return simulation_session


def ensure_simulation_session(session: Session) -> SimulationSession:
    simulation_session = _latest_session(session)
    if simulation_session is not None:
        requested_auto_execute_model = _auto_execute_requested(simulation_session)
        if simulation_session.auto_execute_model or simulation_session.session_payload.get("requested_auto_execute_model") is None:
            simulation_session.auto_execute_model = _effective_auto_execute_model(simulation_session)
            simulation_session.session_payload = {
                **simulation_session.session_payload,
                "requested_auto_execute_model": requested_auto_execute_model,
            }
        _ensure_session_portfolios(session, simulation_session)
        return simulation_session
    watch_symbols = active_watchlist_symbols(session)
    focus_symbol = watch_symbols[0] if watch_symbols else None
    return _new_session(
        session,
        name="双轨同步模拟",
        status="draft",
        initial_cash=DEFAULT_INITIAL_CASH,
        focus_symbol=focus_symbol,
        watch_symbols=watch_symbols,
        benchmark_symbol=DEFAULT_BENCHMARK,
        step_interval_seconds=DEFAULT_STEP_INTERVAL_SECONDS,
        auto_execute_model=False,
    )


def _portfolio_context(
    session: Session,
    simulation_session: SimulationSession,
) -> tuple[dict[str, list[tuple[Any, float]]], dict[str, str], list[Any], dict[Any, float]]:
    watch_symbols = _watch_symbols(session, simulation_session)
    price_history, stock_names, timeline_points = _market_history(
        session,
        watch_symbols,
        timeframe=INTRADAY_MARKET_TIMEFRAME,
    )
    if not timeline_points:
        price_history, stock_names, timeline_points = _market_history(session, watch_symbols, timeframe="1d")
    latest_timeline_point = timeline_points[-1] if timeline_points else None
    last_data_time = simulation_session.last_data_time
    comparable_last_data_time = (
        last_data_time.replace(tzinfo=None) if last_data_time is not None and last_data_time.tzinfo is not None else last_data_time
    )
    comparable_latest_timeline_point = (
        latest_timeline_point.replace(tzinfo=None)
        if latest_timeline_point is not None and latest_timeline_point.tzinfo is not None
        else latest_timeline_point
    )
    if comparable_last_data_time is not None and (
        comparable_latest_timeline_point is None or comparable_last_data_time > comparable_latest_timeline_point
    ):
        # Keep the portfolio replay aligned with the session clock even when
        # the newest 5-minute bar has not landed yet, so same-step fills appear
        # in holdings and NAV immediately.
        timeline_points = [*timeline_points, comparable_last_data_time]
    benchmark_close_map = _benchmark_close_map(
        _distinct_trade_days(timeline_points),
        price_history=price_history,
        active_symbols=watch_symbols,
    )
    return price_history, stock_names, timeline_points, benchmark_close_map


def _portfolio_summary(
    session: Session,
    simulation_session: SimulationSession,
    portfolio: PaperPortfolio,
    *,
    context: tuple[dict[str, list[tuple[Any, float]]], dict[str, str], list[Any], dict[Any, float]] | None = None,
    watch_symbols: set[str] | None = None,
) -> dict[str, Any]:
    active_watch_symbols = watch_symbols or set(_watch_symbols(session, simulation_session))
    price_history, stock_names, timeline_points, benchmark_close_map = context or _portfolio_context(session, simulation_session)
    bind = session.get_bind()
    artifact_root = artifact_root_from_database_url(bind.url.render_as_string(hide_password=False) if bind else None)
    return _portfolio_payload(
        portfolio,
        active_symbols=active_watch_symbols,
        stock_names=stock_names,
        price_history=price_history,
        timeline_points=timeline_points,
        benchmark_close_map=benchmark_close_map,
        recommendation_hit_rate=0.0,
        market_data_timeframe=INTRADAY_MARKET_TIMEFRAME if timeline_points else "1d",
        artifact_root=artifact_root,
    )


def _risk_exposure(summary: dict[str, Any]) -> dict[str, Any]:
    max_weight = max((float(item["portfolio_weight"]) for item in summary["holdings"]), default=0.0)
    return {
        "invested_ratio": summary["invested_ratio"],
        "cash_ratio": round(1 - float(summary["invested_ratio"]), 4),
        "max_position_weight": round(max_weight, 4),
        "drawdown": summary["current_drawdown"],
        "active_position_count": summary["active_position_count"],
    }


def _track_state(role: str, summary: dict[str, Any], latest_reason: str | None) -> dict[str, Any]:
    return {
        "role": role,
        "label": TRACK_LABELS[role],
        "portfolio": summary,
        "risk_exposure": _risk_exposure(summary),
        "latest_reason": latest_reason,
    }


def _session_events(session: Session, simulation_session: SimulationSession) -> list[SimulationEvent]:
    events = session.scalars(
        select(SimulationEvent)
        .where(SimulationEvent.session_id == simulation_session.id)
        .order_by(SimulationEvent.happened_at.desc(), SimulationEvent.id.desc())
        .limit(MAX_TIMELINE_EVENTS * 4)
    ).all()
    return [event for event in events if not _is_noop_model_decision_event(event)][:MAX_TIMELINE_EVENTS]


def _is_noop_model_decision_event(event: SimulationEvent) -> bool:
    if event.track != "model" or event.event_type != "model_decision" or event.symbol:
        return False
    payload = event.event_payload or {}
    return event.title == "模型维持观望" or payload.get("action_summary") == "持有"


def _serialize_lineage(instance: Any) -> dict[str, str]:
    return {
        "license_tag": instance.license_tag,
        "usage_scope": instance.usage_scope,
        "redistribution_scope": instance.redistribution_scope,
        "source_uri": instance.source_uri,
        "lineage_hash": instance.lineage_hash,
    }


def _serialize_event(event: SimulationEvent) -> dict[str, Any]:
    payload = event.event_payload or {}
    return {
        "event_key": event.event_key,
        "step_index": event.step_index,
        "track": event.track,
        "track_label": TRACK_LABELS.get(event.track, event.track),
        "event_type": event.event_type,
        "happened_at": event.happened_at,
        "symbol": event.symbol,
        "title": event.title,
        "detail": event.detail,
        "severity": event.severity,
        "reason_tags": payload.get("reason_tags", []),
        "payload": payload,
        "lineage": _serialize_lineage(event),
    }


def _compose_diff_summary(manual_action: str, model_action: str) -> str:
    if manual_action == model_action:
        return "两侧在该时点采取了相同动作。"
    if manual_action == "未操作":
        return "该时点模型已先行决策，用户仍保持观望。"
    if model_action == "持有":
        return "该时点用户主动下单，模型选择继续持有。"
    return "该时点用户与模型采取了不同动作。"


def _decision_differences(events: list[SimulationEvent]) -> list[dict[str, Any]]:
    grouped: dict[int, dict[str, SimulationEvent]] = defaultdict(dict)
    for event in sorted(events, key=lambda item: item.happened_at):
        if event.step_index <= 0:
            continue
        if event.track not in {"manual", "model"}:
            continue
        if event.event_type not in {"order_filled", "model_decision"}:
            continue
        grouped[event.step_index][event.track] = event

    diffs: list[dict[str, Any]] = []
    for step_index, tracks in sorted(grouped.items(), reverse=True):
        manual = tracks.get("manual")
        model = tracks.get("model")
        manual_payload = manual.event_payload if manual is not None else {}
        model_payload = model.event_payload if model is not None else {}
        manual_action = manual_payload.get("action_summary", "未操作")
        model_action = model_payload.get("action_summary", "持有")
        happened_at = max(
            [item.happened_at for item in tracks.values()],
            default=utcnow(),
        )
        symbol = (manual.symbol if manual is not None else None) or (model.symbol if model is not None else None)
        diffs.append(
            {
                "step_index": step_index,
                "happened_at": happened_at,
                "symbol": symbol,
                "manual_action": manual_action,
                "manual_reason": manual.detail if manual is not None else "该步用户未下单。",
                "model_action": model_action,
                "model_reason": model.detail if model is not None else "该步模型未触发新决策。",
                "difference_summary": _compose_diff_summary(manual_action, model_action),
                "risk_focus": model_payload.get("risk_flags", manual_payload.get("risk_flags", [])),
            }
        )
        if len(diffs) >= MAX_DECISION_DIFFS:
            break
    return diffs


def _comparison_metrics(manual_summary: dict[str, Any], model_summary: dict[str, Any]) -> list[dict[str, Any]]:
    metrics = [
        ("收益率", "pct", manual_summary["total_return"], model_summary["total_return"]),
        ("超额收益", "pct", manual_summary["excess_return"], model_summary["excess_return"]),
        ("仓位", "pct", manual_summary["invested_ratio"], model_summary["invested_ratio"]),
        ("最大回撤", "pct", manual_summary["max_drawdown"], model_summary["max_drawdown"]),
        ("持仓数", "count", manual_summary["active_position_count"], model_summary["active_position_count"]),
    ]
    payload: list[dict[str, Any]] = []
    for label, unit, manual_value, model_value in metrics:
        diff = float(manual_value) - float(model_value)
        if diff == 0:
            leader = "tie"
        elif label == "最大回撤":
            leader = "manual" if float(manual_value) > float(model_value) else "model"
        else:
            leader = "manual" if diff > 0 else "model"
        payload.append(
            {
                "label": label,
                "unit": unit,
                "manual_value": manual_value,
                "model_value": model_value,
                "difference": round(diff, 4) if unit == "pct" else diff,
                "leader": leader,
            }
        )
    return payload


def _model_advices(
    session: Session,
    simulation_session: SimulationSession,
    model_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    bind = session.get_bind()
    artifact_root = artifact_root_from_database_url(bind.url.render_as_string(hide_password=False) if bind else None)
    symbols = _watch_symbols(session, simulation_session)
    latest_bars = _latest_market_bars(session, symbols)
    latest_recommendations = _latest_recommendations(session, symbols)
    holdings = {item["symbol"]: int(item["quantity"]) for item in model_summary["holdings"]}
    holding_weights = {item["symbol"]: float(item["portfolio_weight"]) for item in model_summary["holdings"]}
    available_cash = float(model_summary["available_cash"])
    nav = float(model_summary["net_asset_value"])

    candidate_rows: list[dict[str, Any]] = []
    for symbol in symbols:
        recommendation = latest_recommendations.get(symbol)
        bar = latest_bars.get(symbol)
        if recommendation is None or bar is None:
            continue
        summary = _serialize_recommendation(recommendation, artifact_root=artifact_root)
        reco = summary["recommendation"]
        price = float(bar.close_price)
        score = _model_advice_score(reco["direction"], float(reco["confidence_score"]))
        candidate_rows.append(
            {
                "symbol": symbol,
                "stock_name": summary["stock"]["name"],
                "direction": reco["direction"],
                "direction_label": DIRECTION_LABELS.get(reco["direction"], reco["direction"]),
                "reference_price": round(price, 2),
                "confidence_label": reco["confidence_label"],
                "generated_at": reco["generated_at"],
                "reason": _recommendation_primary_reason(reco),
                "risk_flags": _recommendation_risk_flags(reco),
                "score": score,
                "confidence_score": float(reco["confidence_score"]),
            }
        )

    targets = _phase5_policy_targets(candidate_rows, nav=nav)
    advices: list[dict[str, Any]] = []
    for item in candidate_rows:
        symbol = item["symbol"]
        current_quantity = holdings.get(symbol, 0)
        current_weight = holding_weights.get(symbol, 0.0)
        target = targets.get(symbol, {"target_weight": 0.0, "target_quantity": 0, "rank": None})
        target_quantity = int(target["target_quantity"])
        quantity = 0
        action = "hold"
        if current_quantity > 0 and (
            item["direction"] in PHASE5_SELL_DIRECTIONS
            or target_quantity < current_quantity
        ):
            action = "sell"
            quantity = _round_down_board_lot(min(current_quantity, current_quantity - target_quantity))
        elif item["direction"] in PHASE5_LONG_DIRECTIONS and target_quantity > current_quantity:
            affordable_quantity = _board_lot_quantity_affordable(available_cash, item["reference_price"])
            quantity = _round_down_board_lot(min(target_quantity - current_quantity, affordable_quantity))
            if quantity >= PHASE5_BOARD_LOT:
                action = "buy"

        policy_context = phase5_simulation_policy_context()
        policy_note = policy_context["policy_note"]
        if (
            item["direction"] in PHASE5_LONG_DIRECTIONS
            and target_quantity <= 0
            and current_quantity <= 0
            and nav * PHASE5_MAX_SINGLE_WEIGHT < item["reference_price"] * PHASE5_BOARD_LOT
        ):
            policy_note = (
                f"{policy_context['policy_note']} 当前 {symbol} 在单票 20% 上限下不足一手，"
                "因此不会被纳入本轮目标持仓。"
            )
            policy_context = phase5_simulation_policy_context(policy_note=policy_note)

        advices.append(
            {
                **item,
                "action": action,
                "quantity": quantity if quantity > 0 else None,
                "current_weight": round(current_weight, 4),
                "target_weight": round(float(target["target_weight"]), 4),
                "trade_delta_weight": round(float(target["target_weight"]) - current_weight, 4),
                "policy_status": policy_context["policy_status"],
                "policy_type": policy_context["policy_type"],
                "policy_note": policy_context["policy_note"],
                "action_definition": policy_context["action_definition"],
                "quantity_definition": policy_context["quantity_definition"],
                "rank": target["rank"],
            }
        )
    action_rank = {"sell": 0, "buy": 1, "hold": 2}
    advices.sort(key=lambda item: (action_rank.get(item["action"], 9), -item["score"], item["symbol"]))
    return advices[:MAX_MODEL_ADVICES]


def _kline_payload(session: Session, simulation_session: SimulationSession) -> dict[str, Any]:
    watch_symbols = _watch_symbols(session, simulation_session)
    focus_symbol = simulation_session.focus_symbol or (watch_symbols[0] if watch_symbols else None)
    if not focus_symbol:
        return {
            "symbol": None,
            "stock_name": None,
            "last_updated": simulation_session.last_data_time,
            "points": [],
        }
    bars = session.scalars(
        select(MarketBar)
        .join(Stock)
        .where(Stock.symbol == focus_symbol, MarketBar.timeframe == INTRADAY_MARKET_TIMEFRAME)
        .options(joinedload(MarketBar.stock))
        .order_by(MarketBar.observed_at.desc())
        .limit(48)
    ).all()
    if not bars:
        bars = session.scalars(
            select(MarketBar)
            .join(Stock)
            .where(Stock.symbol == focus_symbol, MarketBar.timeframe == "1d")
            .options(joinedload(MarketBar.stock))
            .order_by(MarketBar.observed_at.desc())
            .limit(60)
        ).all()
    bars = list(reversed(bars))
    return {
        "symbol": focus_symbol,
        "stock_name": bars[-1].stock.name if bars else focus_symbol,
        "last_updated": bars[-1].observed_at if bars else simulation_session.last_data_time,
        "points": [
            {
                "observed_at": bar.observed_at,
                "open_price": bar.open_price,
                "high_price": bar.high_price,
                "low_price": bar.low_price,
                "close_price": bar.close_price,
                "volume": bar.volume,
            }
            for bar in bars
        ],
    }


def _last_reason_for_track(events: list[SimulationEvent], track: str) -> str | None:
    for event in events:
        if event.track == track and event.event_type in {"order_filled", "model_decision"}:
            return event.detail
    return None


def _workspace_payload(session: Session, simulation_session: SimulationSession) -> dict[str, Any]:
    auto_execution_context = phase5_auto_execution_context()
    manual_portfolio, model_portfolio = _ensure_session_portfolios(session, simulation_session)
    watch_symbols = _watch_symbols(session, simulation_session)
    portfolio_context = _portfolio_context(session, simulation_session)
    active_watch_symbols = set(watch_symbols)
    manual_summary = _portfolio_summary(
        session,
        simulation_session,
        manual_portfolio,
        context=portfolio_context,
        watch_symbols=active_watch_symbols,
    )
    model_summary = _portfolio_summary(
        session,
        simulation_session,
        model_portfolio,
        context=portfolio_context,
        watch_symbols=active_watch_symbols,
    )
    events = _session_events(session, simulation_session)
    model_advices = _model_advices(session, simulation_session, model_summary)
    focus_symbol = simulation_session.focus_symbol or (watch_symbols[0] if watch_symbols else None)
    intraday_status = get_intraday_market_status(session, symbols=watch_symbols)

    return {
        "session": {
            "session_key": simulation_session.session_key,
            "name": simulation_session.name,
            "status": simulation_session.status,
            "status_label": SESSION_STATUSES.get(simulation_session.status, simulation_session.status),
            "focus_symbol": focus_symbol,
            "watch_symbols": watch_symbols,
            "benchmark_symbol": simulation_session.benchmark_symbol,
            "initial_cash": simulation_session.initial_cash,
            "current_step": simulation_session.current_step,
            "step_interval_seconds": simulation_session.step_interval_seconds,
            "step_trigger_label": "30 分钟定时决策",
            "fill_rule_label": "最新价即时成交",
            "auto_execute_model": _effective_auto_execute_model(simulation_session),
            "auto_execute_model_requested": _auto_execute_requested(simulation_session),
            "auto_execute_status": auto_execution_context["auto_execute_status"],
            "auto_execute_note": auto_execution_context["auto_execute_note"],
            "restart_count": simulation_session.restart_count,
            "started_at": simulation_session.started_at,
            "last_resumed_at": simulation_session.last_resumed_at,
            "paused_at": simulation_session.paused_at,
            "ended_at": simulation_session.ended_at,
            "last_data_time": simulation_session.last_data_time,
            "market_data_timeframe": INTRADAY_MARKET_TIMEFRAME,
            "market_data_interval_seconds": int(
                simulation_session.session_payload.get("market_data_interval_seconds") or INTRADAY_MARKET_INTERVAL_SECONDS
            ),
            "last_market_data_at": intraday_status["latest_market_data_at"],
            "data_latency_seconds": intraday_status["data_latency_seconds"],
            "intraday_source_status": intraday_status,
            "resumable": simulation_session.status in {"paused", "running"},
        },
        "controls": {
            "can_start": simulation_session.status == "draft",
            "can_pause": simulation_session.status == "running",
            "can_resume": simulation_session.status == "paused",
            "can_step": simulation_session.status == "running",
            "can_restart": True,
            "can_end": simulation_session.status in {"running", "paused"},
            "end_requires_confirmation": True,
        },
        "configuration": {
            "focus_symbol": focus_symbol,
            "watch_symbols": watch_symbols,
            "initial_cash": simulation_session.initial_cash,
            "benchmark_symbol": simulation_session.benchmark_symbol,
            "step_interval_seconds": simulation_session.step_interval_seconds,
            "market_data_interval_seconds": int(
                simulation_session.session_payload.get("market_data_interval_seconds") or INTRADAY_MARKET_INTERVAL_SECONDS
            ),
            "auto_execute_model": _effective_auto_execute_model(simulation_session),
            "auto_execute_model_requested": _auto_execute_requested(simulation_session),
            "auto_execute_status": auto_execution_context["auto_execute_status"],
            "auto_execute_note": auto_execution_context["auto_execute_note"],
            "editable_fields": [
                "initial_cash",
                "watch_symbols",
                "focus_symbol",
                "step_interval_seconds",
            ],
        },
        "manual_track": _track_state("manual", manual_summary, _last_reason_for_track(events, "manual")),
        "model_track": _track_state("model", model_summary, _last_reason_for_track(events, "model")),
        "comparison_metrics": _comparison_metrics(manual_summary, model_summary),
        "model_advices": model_advices,
        "timeline": [_serialize_event(event) for event in reversed(events[:MAX_TIMELINE_EVENTS])],
        "decision_differences": _decision_differences(events),
        "kline": _kline_payload(session, simulation_session),
    }


def get_simulation_workspace(session: Session) -> dict[str, Any]:
    simulation_session = ensure_simulation_session(session)
    session.flush()
    return _workspace_payload(session, simulation_session)


def update_simulation_config(
    session: Session,
    *,
    initial_cash: float,
    watch_symbols: list[str],
    focus_symbol: str | None,
    step_interval_seconds: int,
    auto_execute_model: bool,
) -> dict[str, Any]:
    simulation_session = ensure_simulation_session(session)
    if simulation_session.status == "ended":
        raise ValueError("当前进程已结束，请使用重启创建新进程。")
    if initial_cash <= 0:
        raise ValueError("初始资金必须大于 0。")
    normalized_watch_symbols = [normalize_symbol(symbol) for symbol in watch_symbols if str(symbol).strip()]
    if not normalized_watch_symbols:
        normalized_watch_symbols = active_watchlist_symbols(session)
    if not normalized_watch_symbols:
        raise ValueError("请至少保留一只自选股票作为模拟池。")
    normalized_focus_symbol = normalize_symbol(focus_symbol) if focus_symbol else normalized_watch_symbols[0]
    if normalized_focus_symbol not in normalized_watch_symbols:
        normalized_focus_symbol = normalized_watch_symbols[0]
    scope = (
        WATCHLIST_SCOPE_ACTIVE
        if normalized_watch_symbols == active_watchlist_symbols(session)
        else WATCHLIST_SCOPE_CUSTOM
    )
    if simulation_session.current_step > 0 and initial_cash != simulation_session.initial_cash:
        raise ValueError("模拟已经开始，不能直接修改初始资金；请使用重启。")

    simulation_session.focus_symbol = normalized_focus_symbol
    simulation_session.initial_cash = initial_cash
    simulation_session.step_interval_seconds = step_interval_seconds
    simulation_session.session_payload = {
        **simulation_session.session_payload,
        "watch_symbols": normalized_watch_symbols,
        "watch_symbols_scope": scope,
        "market_data_interval_seconds": INTRADAY_MARKET_INTERVAL_SECONDS,
        "market_data_timeframe": INTRADAY_MARKET_TIMEFRAME,
        "requested_auto_execute_model": auto_execute_model,
    }
    simulation_session.auto_execute_model = _effective_auto_execute_model(simulation_session)
    manual_portfolio, model_portfolio = _ensure_session_portfolios(session, simulation_session)
    for portfolio in (manual_portfolio, model_portfolio):
        portfolio.benchmark_symbol = simulation_session.benchmark_symbol
        portfolio.status = simulation_session.status
        portfolio.portfolio_payload = {
            **portfolio.portfolio_payload,
            "watch_symbols": normalized_watch_symbols,
            "starting_cash": initial_cash,
            "backtest_artifact_id": portfolio_backtest_artifact_id(portfolio.portfolio_key),
        }
        if simulation_session.current_step == 0 and not portfolio.orders:
            portfolio.cash_balance = initial_cash

    _record_event(
        session,
        simulation_session,
        step_index=simulation_session.current_step,
        track="shared",
        event_type="config_updated",
        happened_at=utcnow(),
        title="模拟参数已更新",
        detail=(
            f"初始资金 {initial_cash:.0f}，股票池 {len(normalized_watch_symbols)} 只，"
            f"决策步长 {step_interval_seconds} 秒，行情步长 {INTRADAY_MARKET_INTERVAL_SECONDS} 秒。"
            + (
                " 模型轨道自动执行已启用，后续会按等权组合研究策略自动生成模拟成交。"
                if auto_execute_model
                else ""
            )
        ),
        event_payload={
            "watch_symbols": normalized_watch_symbols,
            "focus_symbol": normalized_focus_symbol,
            "auto_execute_model": _effective_auto_execute_model(simulation_session),
            "requested_auto_execute_model": auto_execute_model,
        },
    )
    session.flush()
    return _workspace_payload(session, simulation_session)


def start_simulation_session(session: Session) -> dict[str, Any]:
    simulation_session = ensure_simulation_session(session)
    if simulation_session.status == "ended":
        raise ValueError("当前进程已结束，请使用重启。")
    if simulation_session.status == "running":
        return _workspace_payload(session, simulation_session)
    now = utcnow()
    simulation_session.status = "running"
    simulation_session.started_at = simulation_session.started_at or now
    simulation_session.last_resumed_at = now
    simulation_session.paused_at = None
    manual_portfolio, model_portfolio = _ensure_session_portfolios(session, simulation_session)
    manual_portfolio.status = "running"
    model_portfolio.status = "running"
    _record_event(
        session,
        simulation_session,
        step_index=simulation_session.current_step,
        track="shared",
        event_type="session_started",
        happened_at=now,
        title="模拟已启动",
        detail="用户轨道与模型轨道已对齐到同一时间线，后续按刷新步推进。",
        event_payload={"auto_execute_model": simulation_session.auto_execute_model},
    )
    session.flush()
    return _workspace_payload(session, simulation_session)


def pause_simulation_session(session: Session) -> dict[str, Any]:
    simulation_session = ensure_simulation_session(session)
    if simulation_session.status != "running":
        raise ValueError("只有运行中的进程才能暂停。")
    now = utcnow()
    simulation_session.status = "paused"
    simulation_session.paused_at = now
    manual_portfolio, model_portfolio = _ensure_session_portfolios(session, simulation_session)
    manual_portfolio.status = "paused"
    model_portfolio.status = "paused"
    _record_event(
        session,
        simulation_session,
        step_index=simulation_session.current_step,
        track="shared",
        event_type="session_paused",
        happened_at=now,
        title="模拟已暂停",
        detail="双轨时间线已冻结，可继续查看建议、修改焦点或稍后恢复。",
    )
    session.flush()
    return _workspace_payload(session, simulation_session)


def resume_simulation_session(session: Session) -> dict[str, Any]:
    simulation_session = ensure_simulation_session(session)
    if simulation_session.status != "paused":
        raise ValueError("只有暂停中的进程才能恢复。")
    now = utcnow()
    simulation_session.status = "running"
    simulation_session.paused_at = None
    simulation_session.last_resumed_at = now
    manual_portfolio, model_portfolio = _ensure_session_portfolios(session, simulation_session)
    manual_portfolio.status = "running"
    model_portfolio.status = "running"
    _record_event(
        session,
        simulation_session,
        step_index=simulation_session.current_step,
        track="shared",
        event_type="session_resumed",
        happened_at=now,
        title="模拟已恢复",
        detail="双轨继续沿上次暂停的时间节点推进。",
    )
    session.flush()
    return _workspace_payload(session, simulation_session)


def _recommendation_for_symbol(session: Session, symbol: str) -> Recommendation | None:
    recommendations = session.scalars(
        select(Recommendation)
        .join(Stock)
        .where(Stock.symbol == symbol)
        .options(
            joinedload(Recommendation.stock),
            joinedload(Recommendation.model_version).joinedload(ModelVersion.registry),
            joinedload(Recommendation.prompt_version),
            joinedload(Recommendation.model_run),
        )
        .order_by(*recommendation_recency_ordering())
    ).all()
    history = collapse_recommendation_history(recommendations, limit=1)
    return history[0] if history else None


def _create_fill_for_order(
    session: Session,
    simulation_session: SimulationSession,
    *,
    portfolio: PaperPortfolio,
    stock: Stock,
    side: str,
    quantity: int,
    reference_price: float,
    requested_at: datetime,
    recommendation: Recommendation | None,
    reason: str,
    track: str,
    limit_price: float | None = None,
) -> None:
    fee = round(max(reference_price * quantity * 0.0003, 5.0), 2)
    tax = round(reference_price * quantity * 0.001, 2) if side == "sell" else 0.0
    order_payload = {
        "simulation_session_key": simulation_session.session_key,
        "track_kind": track,
        "step_index": simulation_session.current_step,
        "execution_mode": "manual" if track == "manual" else "auto_model",
        "fill_rule": "latest_price_immediate",
        "reason": reason,
        "action_summary": f"{'买入' if side == 'buy' else '卖出'} {quantity} 股",
    }
    order = PaperOrder(
        order_key=f"{simulation_session.session_key}-{track}-order-{uuid4().hex[:8]}",
        portfolio=portfolio,
        stock=stock,
        recommendation=recommendation,
        order_source="manual" if track == "manual" else "model",
        side=side,
        requested_at=requested_at,
        quantity=quantity,
        order_type="market" if limit_price is None else "limit",
        limit_price=limit_price,
        status="filled",
        notes=reason,
        order_payload=order_payload,
        **_lineage(order_payload, f"simulation://order/{simulation_session.session_key}/{track}/{stock.symbol}"),
    )
    session.add(order)
    session.flush()

    fill_payload = {
        "simulation_session_key": simulation_session.session_key,
        "matching_rule": "latest_price_immediate",
        "step_index": simulation_session.current_step,
    }
    fill = PaperFill(
        fill_key=f"{simulation_session.session_key}-{track}-fill-{uuid4().hex[:8]}",
        order=order,
        stock=stock,
        filled_at=requested_at,
        price=reference_price,
        quantity=quantity,
        fee=fee,
        tax=tax,
        slippage_bps=0.0,
        fill_payload=fill_payload,
        **_lineage(fill_payload, f"simulation://fill/{simulation_session.session_key}/{track}/{stock.symbol}"),
    )
    session.add(fill)
    session.flush()

    _record_event(
        session,
        simulation_session,
        step_index=simulation_session.current_step,
        track=track,
        event_type="order_filled",
        happened_at=requested_at,
        symbol=stock.symbol,
        title=f"{TRACK_LABELS[track]}已成交",
        detail=f"{stock.name} 按最新价 {reference_price:.2f} {'买入' if side == 'buy' else '卖出'} {quantity} 股。理由：{reason}",
        severity="success",
        event_payload={
            "action_summary": order_payload["action_summary"],
            "reason": reason,
            "price": round(reference_price, 2),
            "quantity": quantity,
            "risk_flags": (
                _recommendation_risk_flags(
                    _serialize_recommendation(
                        recommendation,
                        artifact_root=artifact_root_from_database_url(
                            session.get_bind().url.render_as_string(hide_password=False) if session.get_bind() else None
                        ),
                    )["recommendation"]
                )
                if recommendation is not None
                else []
            ),
        },
    )


def _validate_order_request(
    summary: dict[str, Any],
    *,
    symbol: str,
    side: str,
    quantity: int,
    reference_price: float,
) -> None:
    if quantity <= 0 or quantity % 100 != 0:
        raise ValueError("一期模拟下单数量必须为 100 股整数倍。")
    if side not in {"buy", "sell"}:
        raise ValueError("仅支持 buy / sell。")
    if side == "buy":
        estimated_fee = round(max(reference_price * quantity * 0.0003, 5.0), 2)
        estimated_cost = reference_price * quantity + estimated_fee
        if estimated_cost > float(summary["available_cash"]):
            raise ValueError("可用资金不足，无法按最新价即时成交。")
        return
    holding = next((item for item in summary["holdings"] if item["symbol"] == symbol), None)
    if holding is None or int(holding["quantity"]) < quantity:
        raise ValueError("当前持仓不足，无法卖出指定数量。")


def place_manual_order(
    session: Session,
    *,
    symbol: str,
    side: str,
    quantity: int,
    reason: str,
    limit_price: float | None = None,
) -> dict[str, Any]:
    simulation_session = ensure_simulation_session(session)
    if simulation_session.status not in {"running", "paused"}:
        raise ValueError("请先启动模拟，再进行手动下单。")
    manual_portfolio, _model_portfolio = _ensure_session_portfolios(session, simulation_session)
    manual_summary = _portfolio_summary(session, simulation_session, manual_portfolio)
    normalized_symbol = normalize_symbol(symbol)
    stock = session.scalar(select(Stock).where(Stock.symbol == normalized_symbol))
    if stock is None:
        raise LookupError(f"未找到股票 {normalized_symbol}。")
    latest_bar = _latest_market_bars(session, [normalized_symbol]).get(normalized_symbol)
    if latest_bar is None:
        raise LookupError(f"缺少 {normalized_symbol} 的最新价格。")
    reference_price = float(latest_bar.close_price)
    _validate_order_request(
        manual_summary,
        symbol=normalized_symbol,
        side=side,
        quantity=quantity,
        reference_price=reference_price,
    )
    recommendation = _recommendation_for_symbol(session, normalized_symbol)
    requested_at = simulation_session.last_data_time or latest_bar.observed_at
    _create_fill_for_order(
        session,
        simulation_session,
        portfolio=manual_portfolio,
        stock=stock,
        side=side,
        quantity=quantity,
        reference_price=reference_price if limit_price is None else limit_price,
        requested_at=requested_at,
        recommendation=recommendation,
        reason=reason,
        track="manual",
        limit_price=limit_price,
    )
    session.flush()
    return _workspace_payload(session, simulation_session)


def step_simulation_session(session: Session, *, anchor_time: datetime | None = None) -> dict[str, Any]:
    simulation_session = ensure_simulation_session(session)
    if simulation_session.status != "running":
        raise ValueError("只有运行中的模拟才能推进单步。")
    _manual_portfolio, model_portfolio = _ensure_session_portfolios(session, simulation_session)
    model_summary = _portfolio_summary(session, simulation_session, model_portfolio)
    simulation_session.current_step += 1
    next_data_time = anchor_time or (
        (simulation_session.last_data_time or utcnow()) + timedelta(
            seconds=simulation_session.step_interval_seconds
        )
    )
    simulation_session.last_data_time = next_data_time
    _record_event(
        session,
        simulation_session,
        step_index=simulation_session.current_step,
        track="shared",
        event_type="refresh_step",
        happened_at=next_data_time,
        title=f"第 {simulation_session.current_step} 步刷新",
        detail="共享时间线已推进一个刷新步，模型建议与用户轨道对比已重新计算。",
        event_payload={"watch_symbols": _watch_symbols(session, simulation_session)},
    )

    advices = _model_advices(session, simulation_session, model_summary)
    primary = next((item for item in advices if item["action"] in {"buy", "sell"} and (item["quantity"] or 0) > 0), None)
    if primary is None:
        session.flush()
        return _workspace_payload(session, simulation_session)

    recommendation = _recommendation_for_symbol(session, primary["symbol"])
    reason = primary["reason"]
    action_label = "买入" if primary["action"] == "buy" else "卖出"
    _record_event(
        session,
        simulation_session,
        step_index=simulation_session.current_step,
        track="model",
        event_type="model_decision",
        happened_at=next_data_time,
        symbol=primary["symbol"],
        title="模型给出新建议",
        detail=(
            f"{primary['stock_name']} 按等权组合研究策略给出{action_label} {primary['quantity']} 股，"
            f"目标权重 {primary['target_weight']:.0%}，当前权重 {primary['current_weight']:.0%}。主要理由：{reason}"
        ),
        event_payload={
            "action_summary": f"{action_label} {primary['quantity']} 股",
            "reason_tags": [reason],
            "risk_flags": primary["risk_flags"],
            "policy_status": primary["policy_status"],
            "policy_type": primary["policy_type"],
            "policy_note": primary["policy_note"],
            "target_weight": primary["target_weight"],
            "current_weight": primary["current_weight"],
            "quantity": primary["quantity"],
        },
    )
    if _effective_auto_execute_model(simulation_session) and recommendation is not None and primary["quantity"] and primary["quantity"] > 0:
        _validate_order_request(
            model_summary,
            symbol=primary["symbol"],
            side="buy" if primary["action"] == "buy" else "sell",
            quantity=primary["quantity"],
            reference_price=float(primary["reference_price"]),
        )
        stock = recommendation.stock
        _create_fill_for_order(
            session,
            simulation_session,
            portfolio=model_portfolio,
            stock=stock,
            side="buy" if primary["action"] == "buy" else "sell",
            quantity=primary["quantity"],
            reference_price=float(primary["reference_price"]),
            requested_at=next_data_time,
            recommendation=recommendation,
            reason=reason,
            track="model",
        )
    session.flush()
    return _workspace_payload(session, simulation_session)


def advance_running_simulation_session(session: Session) -> dict[str, Any] | None:
    simulation_session = _latest_session(session)
    if simulation_session is None or simulation_session.status != "running":
        return None
    latest_market_data_time = _latest_market_data_time_for_session(session, simulation_session)
    if latest_market_data_time is None:
        return None
    session_data_time = simulation_session.last_data_time
    comparable_session_time = (
        session_data_time.replace(tzinfo=None) if session_data_time is not None and session_data_time.tzinfo is not None else session_data_time
    )
    comparable_market_time = (
        latest_market_data_time.replace(tzinfo=None)
        if latest_market_data_time.tzinfo is not None
        else latest_market_data_time
    )
    if comparable_session_time is not None and comparable_session_time >= comparable_market_time:
        return None
    return step_simulation_session(session, anchor_time=latest_market_data_time)


def restart_simulation_session(session: Session) -> dict[str, Any]:
    current = ensure_simulation_session(session)
    if current.status != "ended":
        current.status = "ended"
        current.ended_at = utcnow()
        _record_event(
            session,
            current,
            step_index=current.current_step,
            track="shared",
            event_type="session_restarted",
            happened_at=current.ended_at,
            title="旧进程已归档",
            detail="当前模拟已归档，系统将基于相同参数创建新的双轨进程。",
        )
    watch_symbols = _watch_symbols(session, current)
    new_session = _new_session(
        session,
        name=current.name,
        status="running",
        initial_cash=current.initial_cash,
        focus_symbol=current.focus_symbol or (watch_symbols[0] if watch_symbols else None),
        watch_symbols=watch_symbols,
        benchmark_symbol=current.benchmark_symbol or DEFAULT_BENCHMARK,
        step_interval_seconds=current.step_interval_seconds,
        auto_execute_model=current.auto_execute_model,
        restart_count=current.restart_count + 1,
    )
    started_at = utcnow()
    new_session.status = "running"
    new_session.started_at = started_at
    new_session.last_resumed_at = started_at
    _record_event(
        session,
        new_session,
        step_index=0,
        track="shared",
        event_type="session_started",
        happened_at=started_at,
        title="新模拟已重启",
        detail="双轨已按同一初始资金和股票池重新对齐。",
        event_payload={"restart_count": new_session.restart_count},
    )
    session.flush()
    return _workspace_payload(session, new_session)


def end_simulation_session(session: Session, *, confirm: bool) -> dict[str, Any]:
    if not confirm:
        raise ValueError("结束模拟需要二次确认。")
    simulation_session = ensure_simulation_session(session)
    if simulation_session.status == "ended":
        return _workspace_payload(session, simulation_session)
    ended_at = utcnow()
    simulation_session.status = "ended"
    simulation_session.ended_at = ended_at
    manual_portfolio, model_portfolio = _ensure_session_portfolios(session, simulation_session)
    manual_portfolio.status = "ended"
    model_portfolio.status = "ended"
    _record_event(
        session,
        simulation_session,
        step_index=simulation_session.current_step,
        track="shared",
        event_type="session_ended",
        happened_at=ended_at,
        title="模拟已结束",
        detail="双轨时间线已停止，当前留痕可继续用于复盘和模型迭代。",
        severity="warn",
    )
    session.flush()
    return _workspace_payload(session, simulation_session)
