from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from ashare_evidence.dashboard import DIRECTION_LABELS
from ashare_evidence.dashboard_demo import normalize_symbol
from ashare_evidence.db import utcnow
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
from ashare_evidence.operations import MODE_LABELS, _benchmark_close_map, _market_history, _portfolio_payload
from ashare_evidence.services import _serialize_recommendation
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

DEFAULT_STEP_INTERVAL_SECONDS = 300
DEFAULT_INITIAL_CASH = 200000.0
DEFAULT_BENCHMARK = "CSI300"
MAX_TIMELINE_EVENTS = 16
MAX_DECISION_DIFFS = 8
MAX_MODEL_ADVICES = 4


def _lineage(payload: dict[str, Any], source_uri: str) -> dict[str, str]:
    return build_lineage(
        payload,
        source_uri=source_uri,
        license_tag="internal-derived",
        usage_scope="internal_research",
        redistribution_scope="none",
    )


def _latest_session(session: Session) -> SimulationSession | None:
    sessions = session.scalars(
        select(SimulationSession).order_by(SimulationSession.created_at.desc(), SimulationSession.id.desc())
    ).all()
    for item in sessions:
        if item.status != "ended":
            return item
    return sessions[0] if sessions else None


def _watch_symbols(session: Session, simulation_session: SimulationSession) -> list[str]:
    configured = [
        normalize_symbol(symbol)
        for symbol in simulation_session.session_payload.get("watch_symbols", [])
        if str(symbol).strip()
    ]
    if configured:
        return configured
    active = active_watchlist_symbols(session)
    if active:
        simulation_session.session_payload = {**simulation_session.session_payload, "watch_symbols": active}
        return active
    return []


def _latest_market_bars(session: Session, symbols: list[str]) -> dict[str, MarketBar]:
    if not symbols:
        return {}
    bars = session.scalars(
        select(MarketBar)
        .join(Stock)
        .where(Stock.symbol.in_(symbols))
        .options(joinedload(MarketBar.stock))
        .order_by(Stock.symbol.asc(), MarketBar.observed_at.desc())
    ).all()
    latest: dict[str, MarketBar] = {}
    for bar in bars:
        latest.setdefault(bar.stock.symbol, bar)
    return latest


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
        .order_by(Stock.symbol.asc(), Recommendation.generated_at.desc())
    ).all()
    latest: dict[str, Recommendation] = {}
    for recommendation in recommendations:
        latest.setdefault(recommendation.stock.symbol, recommendation)
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
        "step_trigger": "refresh_tick",
        "fill_rule": "latest_price_immediate",
        "supports_manual_step": True,
        "supports_resume": True,
        "restart_count": restart_count,
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
        auto_execute_model=True,
    )


def _portfolio_context(session: Session, simulation_session: SimulationSession) -> tuple[dict[str, list[tuple[Any, float]]], list[Any], dict[Any, float]]:
    price_history, _stock_names, trade_days = _market_history(session, _watch_symbols(session, simulation_session))
    benchmark_close_map = _benchmark_close_map(trade_days)
    return price_history, trade_days, benchmark_close_map


def _portfolio_summary(
    session: Session,
    simulation_session: SimulationSession,
    portfolio: PaperPortfolio,
    *,
    context: tuple[dict[str, list[tuple[Any, float]]], list[Any], dict[Any, float]] | None = None,
    watch_symbols: set[str] | None = None,
) -> dict[str, Any]:
    active_watch_symbols = watch_symbols or set(_watch_symbols(session, simulation_session))
    price_history, trade_days, benchmark_close_map = context or _portfolio_context(session, simulation_session)
    return _portfolio_payload(
        portfolio,
        active_symbols=active_watch_symbols,
        price_history=price_history,
        trade_days=trade_days,
        benchmark_close_map=benchmark_close_map,
        recommendation_hit_rate=0.0,
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
    return session.scalars(
        select(SimulationEvent)
        .where(SimulationEvent.session_id == simulation_session.id)
        .order_by(SimulationEvent.happened_at.desc(), SimulationEvent.id.desc())
        .limit(64)
    ).all()


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
    symbols = _watch_symbols(session, simulation_session)
    latest_bars = _latest_market_bars(session, symbols)
    latest_recommendations = _latest_recommendations(session, symbols)
    holdings = {item["symbol"]: int(item["quantity"]) for item in model_summary["holdings"]}
    available_cash = float(model_summary["available_cash"])

    advices: list[dict[str, Any]] = []
    for symbol in symbols:
        recommendation = latest_recommendations.get(symbol)
        bar = latest_bars.get(symbol)
        if recommendation is None or bar is None:
            continue
        summary = _serialize_recommendation(recommendation)
        reco = summary["recommendation"]
        price = float(bar.close_price)
        quantity = 0
        action = "hold"
        if reco["direction"] == "buy":
            budget = available_cash * 0.24
            quantity = max(int(budget / price / 100) * 100, 0)
            action = "buy" if quantity > 0 else "hold"
        elif reco["direction"] in {"reduce", "risk_alert"}:
            owned = holdings.get(symbol, 0)
            quantity = min(owned, max((owned // 2) // 100 * 100, 100 if owned >= 100 else 0))
            action = "sell" if quantity > 0 else "hold"
        score = {
            "buy": 300,
            "watch": 200,
            "reduce": 120,
            "risk_alert": 80,
        }.get(reco["direction"], 0) + int(float(reco["confidence_score"]) * 100)
        advices.append(
            {
                "symbol": symbol,
                "stock_name": summary["stock"]["name"],
                "direction": reco["direction"],
                "direction_label": DIRECTION_LABELS.get(reco["direction"], reco["direction"]),
                "action": action,
                "quantity": quantity,
                "reference_price": round(price, 2),
                "confidence_label": reco["confidence_label"],
                "generated_at": reco["generated_at"],
                "reason": reco["core_drivers"][0] if reco["core_drivers"] else reco["summary"],
                "risk_flags": reco["reverse_risks"][:3],
                "score": score,
            }
        )
    advices.sort(key=lambda item: (item["action"] == "hold", -item["score"], item["symbol"]))
    return advices[:MAX_MODEL_ADVICES]


def _kline_payload(session: Session, simulation_session: SimulationSession) -> dict[str, Any]:
    focus_symbol = simulation_session.focus_symbol or (_watch_symbols(session, simulation_session)[0] if _watch_symbols(session, simulation_session) else None)
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
        .where(Stock.symbol == focus_symbol)
        .options(joinedload(MarketBar.stock))
        .order_by(MarketBar.observed_at.desc())
        .limit(48)
    ).all()
    bars = list(reversed(bars))
    return {
        "symbol": focus_symbol,
        "stock_name": bars[-1].stock.name if bars else focus_symbol,
        "last_updated": bars[-1].observed_at if bars else simulation_session.last_data_time,
        "points": [
            {
                "observed_at": bar.observed_at,
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
            "step_trigger_label": "按数据刷新推进",
            "fill_rule_label": "最新价即时成交",
            "auto_execute_model": simulation_session.auto_execute_model,
            "restart_count": simulation_session.restart_count,
            "started_at": simulation_session.started_at,
            "last_resumed_at": simulation_session.last_resumed_at,
            "paused_at": simulation_session.paused_at,
            "ended_at": simulation_session.ended_at,
            "last_data_time": simulation_session.last_data_time,
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
            "auto_execute_model": simulation_session.auto_execute_model,
            "editable_fields": ["initial_cash", "watch_symbols", "focus_symbol", "step_interval_seconds", "auto_execute_model"],
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
    if simulation_session.current_step > 0 and initial_cash != simulation_session.initial_cash:
        raise ValueError("模拟已经开始，不能直接修改初始资金；请使用重启。")

    simulation_session.focus_symbol = normalized_focus_symbol
    simulation_session.initial_cash = initial_cash
    simulation_session.step_interval_seconds = step_interval_seconds
    simulation_session.auto_execute_model = auto_execute_model
    simulation_session.session_payload = {
        **simulation_session.session_payload,
        "watch_symbols": normalized_watch_symbols,
    }
    manual_portfolio, model_portfolio = _ensure_session_portfolios(session, simulation_session)
    for portfolio in (manual_portfolio, model_portfolio):
        portfolio.benchmark_symbol = simulation_session.benchmark_symbol
        portfolio.status = simulation_session.status
        portfolio.portfolio_payload = {
            **portfolio.portfolio_payload,
            "watch_symbols": normalized_watch_symbols,
            "starting_cash": initial_cash,
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
        detail=f"初始资金 {initial_cash:.0f}，股票池 {len(normalized_watch_symbols)} 只，步长 {step_interval_seconds} 秒。",
        event_payload={
            "watch_symbols": normalized_watch_symbols,
            "focus_symbol": normalized_focus_symbol,
            "auto_execute_model": auto_execute_model,
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
    return session.scalar(
        select(Recommendation)
        .join(Stock)
        .where(Stock.symbol == symbol)
        .options(
            joinedload(Recommendation.stock),
            joinedload(Recommendation.model_version).joinedload(ModelVersion.registry),
            joinedload(Recommendation.prompt_version),
            joinedload(Recommendation.model_run),
        )
        .order_by(Recommendation.generated_at.desc())
        .limit(1)
    )


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
            "risk_flags": recommendation.recommendation_payload.get("reverse_risks", [])[:3] if recommendation is not None else [],
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


def step_simulation_session(session: Session) -> dict[str, Any]:
    simulation_session = ensure_simulation_session(session)
    if simulation_session.status != "running":
        raise ValueError("只有运行中的模拟才能推进单步。")
    _manual_portfolio, model_portfolio = _ensure_session_portfolios(session, simulation_session)
    model_summary = _portfolio_summary(session, simulation_session, model_portfolio)
    simulation_session.current_step += 1
    next_data_time = (simulation_session.last_data_time or utcnow()) + timedelta(
        seconds=simulation_session.step_interval_seconds
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
    primary = next((item for item in advices if item["action"] in {"buy", "sell"} and item["quantity"] > 0), None)
    if primary is None:
        _record_event(
            session,
            simulation_session,
            step_index=simulation_session.current_step,
            track="model",
            event_type="model_decision",
            happened_at=next_data_time,
            title="模型维持观望",
            detail="当前刷新步没有满足执行阈值的新动作，模型继续持有并等待下一次刷新。",
            event_payload={"action_summary": "持有", "risk_flags": []},
        )
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
        detail=f"{primary['stock_name']} 建议 {action_label} {primary['quantity']} 股。主要理由：{reason}",
        event_payload={
            "action_summary": f"{action_label} {primary['quantity']} 股",
            "reason_tags": [reason],
            "risk_flags": primary["risk_flags"],
        },
    )
    if simulation_session.auto_execute_model and recommendation is not None and primary["quantity"] > 0:
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
