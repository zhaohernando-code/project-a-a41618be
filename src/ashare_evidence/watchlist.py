from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ashare_evidence.account_space import ROLE_ROOT, ROOT_ACCOUNT_LOGIN, record_account_presence
from ashare_evidence.analysis_pipeline import refresh_real_analysis, repair_stock_profile_snapshot
from ashare_evidence.db import align_datetime_timezone, utcnow
from ashare_evidence.lineage import build_lineage
from ashare_evidence.models import Recommendation, Stock, WatchlistEntry, WatchlistFollow
from ashare_evidence.recommendation_selection import (
    collapse_recommendation_history,
    recommendation_recency_ordering,
)
from ashare_evidence.stock_master import resolve_stock_profile
from ashare_evidence.symbols import normalize_symbol

ACTIVE_STATUS = "active"
REMOVED_STATUS = "removed"
USER_SOURCE_KIND = "user_input"
PENDING_REAL_DATA_STATUS = "pending_real_data"
PHASE5_TARGET_WATCHLIST_SYMBOLS: tuple[str, ...] = (
    "600519.SH",
    "601318.SH",
    "300750.SZ",
    "002594.SZ",
    "600522.SH",
    "002028.SZ",
    "000001.SZ",
    "000651.SZ",
    "600036.SH",
    "600276.SH",
    "601012.SH",
    "600031.SH",
    "688981.SH",
    "300760.SZ",
    "601899.SH",
    "600309.SH",
)
PHASE5_WATCHLIST_REPLACEMENT_CANDIDATES: tuple[str, ...] = (
    "000858.SZ",
    "601088.SH",
    "600887.SH",
    "002475.SZ",
    "300124.SZ",
)


def _dissect_symbol(symbol: str) -> tuple[str, str]:
    ticker, _, market = symbol.partition(".")
    exchange = {
        "SH": "SSE",
        "SZ": "SZSE",
        "BJ": "BSE",
    }[market]
    return ticker, exchange


def _lineage_for_watchlist(symbol: str, *, source_kind: str, display_name: str) -> dict[str, str]:
    payload = {
        "symbol": symbol,
        "display_name": display_name,
        "source_kind": source_kind,
    }
    return build_lineage(
        payload,
        source_uri=f"watchlist://{source_kind}/{symbol}",
        license_tag="user-input" if source_kind == USER_SOURCE_KIND else "internal-derived",
        usage_scope="internal_research",
        redistribution_scope="none",
    )


def _latest_recommendation(session: Session, symbol: str) -> Recommendation | None:
    recommendations = session.scalars(
        select(Recommendation)
        .join(Stock)
        .options(joinedload(Recommendation.stock))
        .where(Stock.symbol == symbol)
        .order_by(*recommendation_recency_ordering())
    ).all()
    history = collapse_recommendation_history(recommendations, limit=1)
    return history[0] if history else None


def _resolve_display_name(session: Session, *, symbol: str, stock_name: str | None) -> str:
    stock = session.scalar(select(Stock).where(Stock.symbol == symbol))
    if stock is not None and stock.name:
        return stock.name
    resolved_profile = resolve_stock_profile(session, symbol=symbol, preferred_name=stock_name)
    return resolved_profile.name or stock_name or symbol


def _upsert_watchlist_entry(
    session: Session,
    *,
    symbol: str,
    display_name: str,
    source_kind: str,
    analyzed_at: datetime | None,
    analysis_status: str,
    last_error: str | None,
) -> WatchlistEntry:
    ticker, exchange = _dissect_symbol(symbol)
    entry = session.scalar(select(WatchlistEntry).where(WatchlistEntry.symbol == symbol))
    lineage = _lineage_for_watchlist(symbol, source_kind=source_kind, display_name=display_name)
    payload = {
        "symbol": symbol,
        "ticker": ticker,
        "exchange": exchange,
        "display_name": display_name,
        "status": ACTIVE_STATUS,
        "source_kind": source_kind,
        "analysis_status": analysis_status,
        "last_analyzed_at": analyzed_at,
        "last_error": last_error,
        "watchlist_payload": {
            "source_kind": source_kind,
            "watchlist_scope": "一期自选股池",
            "data_policy": "real_only",
        },
        **lineage,
    }
    if entry is None:
        entry = WatchlistEntry(**payload)
        session.add(entry)
    else:
        for key, value in payload.items():
            setattr(entry, key, value)
    session.flush()
    return entry


def _get_follow(session: Session, *, account_login: str, symbol: str) -> WatchlistFollow | None:
    return session.scalar(
        select(WatchlistFollow).where(
            WatchlistFollow.account_login == account_login,
            WatchlistFollow.symbol == symbol,
        )
    )


def _upsert_watchlist_follow(
    session: Session,
    *,
    account_login: str,
    actor_login: str,
    symbol: str,
    source_kind: str,
    status: str,
) -> WatchlistFollow:
    follow = _get_follow(session, account_login=account_login, symbol=symbol)
    now = utcnow()
    payload = {
        "account_login": account_login,
        "symbol": symbol,
        "status": status,
        "source_kind": source_kind,
        "added_at": follow.added_at if follow and follow.status == ACTIVE_STATUS and follow.added_at else now,
        "removed_at": now if status != ACTIVE_STATUS else None,
        "last_actor_login": actor_login,
        "follow_payload": {
            "watchlist_scope": "account_isolated_follow",
            "migrated_from_global_entry": False,
        },
    }
    if follow is None:
        follow = WatchlistFollow(**payload)
        session.add(follow)
    else:
        if follow.status != ACTIVE_STATUS and status == ACTIVE_STATUS:
            payload["added_at"] = now
        for key, value in payload.items():
            setattr(follow, key, value)
    session.flush()
    return follow


def _reconcile_entry_tracking_state(session: Session, *, symbol: str) -> WatchlistEntry | None:
    entry = session.scalar(select(WatchlistEntry).where(WatchlistEntry.symbol == symbol))
    if entry is None:
        return None
    active_count = session.scalar(
        select(WatchlistFollow).where(
            WatchlistFollow.symbol == symbol,
            WatchlistFollow.status == ACTIVE_STATUS,
        )
    )
    entry.status = ACTIVE_STATUS if active_count is not None else REMOVED_STATUS
    entry.updated_at = utcnow()
    session.flush()
    return entry


def _sync_watchlist_symbol(
    session: Session,
    *,
    symbol: str,
    stock_name: str | None,
    source_kind: str,
    force_refresh: bool,
) -> WatchlistEntry:
    normalized_symbol = normalize_symbol(symbol)
    latest = _latest_recommendation(session, normalized_symbol)
    refresh_error: str | None = None
    if force_refresh or latest is None:
        try:
            latest = refresh_real_analysis(
                session,
                symbol=normalized_symbol,
                stock_name=stock_name,
            )
        except Exception as exc:
            session.rollback()
            try:
                repair_stock_profile_snapshot(session, symbol=normalized_symbol, stock_name=stock_name)
            except Exception:
                session.rollback()
            latest = _latest_recommendation(session, normalized_symbol)
            refresh_error = f"真实数据刷新失败：{exc}"
    analyzed_at = latest.generated_at if latest is not None else None
    analysis_status = "ready" if latest is not None else PENDING_REAL_DATA_STATUS
    last_error = refresh_error if latest is not None else (refresh_error or "暂无真实分析结果，请先完成真实数据同步后再刷新。")
    display_name = latest.stock.name if latest is not None else _resolve_display_name(
        session,
        symbol=normalized_symbol,
        stock_name=stock_name,
    )
    return _upsert_watchlist_entry(
        session,
        symbol=normalized_symbol,
        display_name=display_name,
        source_kind=source_kind,
        analyzed_at=analyzed_at,
        analysis_status=analysis_status,
        last_error=last_error,
    )


def _serialize_watchlist_entry(session: Session, entry: WatchlistEntry, *, follow: WatchlistFollow | None = None) -> dict[str, Any]:
    stock = session.scalar(select(Stock).where(Stock.symbol == entry.symbol))
    latest = _latest_recommendation(session, entry.symbol)
    latest_generated_at = (
        align_datetime_timezone(latest.generated_at, reference=entry.updated_at)
        if latest is not None
        else None
    )
    return {
        "symbol": entry.symbol,
        "name": stock.name if stock is not None else entry.display_name,
        "exchange": stock.exchange if stock is not None else entry.exchange,
        "ticker": stock.ticker if stock is not None else entry.ticker,
        "status": follow.status if follow is not None else entry.status,
        "source_kind": follow.source_kind if follow is not None else entry.source_kind,
        "analysis_status": entry.analysis_status,
        "added_at": follow.added_at if follow is not None else entry.created_at,
        "updated_at": follow.updated_at if follow is not None else entry.updated_at,
        "last_analyzed_at": entry.last_analyzed_at,
        "last_error": entry.last_error,
        "latest_direction": latest.direction if latest is not None else None,
        "latest_confidence_label": latest.confidence_label if latest is not None else None,
        "latest_generated_at": latest_generated_at,
    }


def active_watchlist_symbols(session: Session, *, account_login: str | None = None) -> list[str]:
    query = select(WatchlistFollow).where(WatchlistFollow.status == ACTIVE_STATUS)
    if account_login is not None:
        query = query.where(WatchlistFollow.account_login == account_login)
    follows = session.scalars(query.order_by(WatchlistFollow.updated_at.desc(), WatchlistFollow.created_at.asc())).all()
    return [follow.symbol for follow in follows]


def list_watchlist_entries(
    session: Session,
    *,
    target_login: str = ROOT_ACCOUNT_LOGIN,
    actor_login: str = ROOT_ACCOUNT_LOGIN,
    actor_role: str = ROLE_ROOT,
) -> dict[str, Any]:
    record_account_presence(
        session,
        actor_login=actor_login,
        actor_role=actor_role,
        target_login=target_login,
        mark_acted=False,
    )
    follows = session.scalars(
        select(WatchlistFollow)
        .where(
            WatchlistFollow.account_login == target_login,
            WatchlistFollow.status == ACTIVE_STATUS,
        )
        .order_by(WatchlistFollow.updated_at.desc(), WatchlistFollow.created_at.asc())
    ).all()
    entry_map = {
        entry.symbol: entry
        for entry in session.scalars(select(WatchlistEntry).where(WatchlistEntry.symbol.in_([item.symbol for item in follows]))).all()
    }
    return {
        "generated_at": utcnow(),
        "items": [
            _serialize_watchlist_entry(session, entry_map[follow.symbol], follow=follow)
            for follow in follows
            if follow.symbol in entry_map
        ],
    }


def add_watchlist_symbol(
    session: Session,
    symbol: str,
    stock_name: str | None = None,
    *,
    actor_login: str = ROOT_ACCOUNT_LOGIN,
    actor_role: str = ROLE_ROOT,
    target_login: str = ROOT_ACCOUNT_LOGIN,
) -> dict[str, Any]:
    record_account_presence(
        session,
        actor_login=actor_login,
        actor_role=actor_role,
        target_login=target_login,
        mark_acted=True,
    )
    entry = _sync_watchlist_symbol(
        session,
        symbol=symbol,
        stock_name=stock_name,
        source_kind=USER_SOURCE_KIND,
        force_refresh=False,
    )
    follow = _upsert_watchlist_follow(
        session,
        account_login=target_login,
        actor_login=actor_login,
        symbol=entry.symbol,
        source_kind=USER_SOURCE_KIND,
        status=ACTIVE_STATUS,
    )
    _reconcile_entry_tracking_state(session, symbol=entry.symbol)
    session.commit()
    session.refresh(entry)
    session.refresh(follow)
    return _serialize_watchlist_entry(session, entry, follow=follow)


def refresh_watchlist_symbol(
    session: Session,
    symbol: str,
    *,
    actor_login: str = ROOT_ACCOUNT_LOGIN,
    actor_role: str = ROLE_ROOT,
    target_login: str = ROOT_ACCOUNT_LOGIN,
) -> dict[str, Any]:
    record_account_presence(
        session,
        actor_login=actor_login,
        actor_role=actor_role,
        target_login=target_login,
        mark_acted=True,
    )
    normalized_symbol = normalize_symbol(symbol)
    follow = _get_follow(session, account_login=target_login, symbol=normalized_symbol)
    existing = session.scalar(select(WatchlistEntry).where(WatchlistEntry.symbol == normalized_symbol))
    if follow is None or follow.status != ACTIVE_STATUS or existing is None:
        raise LookupError(f"{normalized_symbol} 不在当前自选池中。")
    entry = _sync_watchlist_symbol(
        session,
        symbol=normalized_symbol,
        stock_name=existing.display_name,
        source_kind=follow.source_kind,
        force_refresh=True,
    )
    follow.updated_at = utcnow()
    _reconcile_entry_tracking_state(session, symbol=normalized_symbol)
    session.commit()
    session.refresh(entry)
    session.refresh(follow)
    return _serialize_watchlist_entry(session, entry, follow=follow)


def remove_watchlist_symbol(
    session: Session,
    symbol: str,
    *,
    actor_login: str = ROOT_ACCOUNT_LOGIN,
    actor_role: str = ROLE_ROOT,
    target_login: str = ROOT_ACCOUNT_LOGIN,
) -> dict[str, Any]:
    record_account_presence(
        session,
        actor_login=actor_login,
        actor_role=actor_role,
        target_login=target_login,
        mark_acted=True,
    )
    normalized_symbol = normalize_symbol(symbol)
    follow = _get_follow(session, account_login=target_login, symbol=normalized_symbol)
    if follow is None or follow.status != ACTIVE_STATUS:
        raise LookupError(f"{normalized_symbol} 不在当前自选池中。")
    follow.status = REMOVED_STATUS
    follow.removed_at = utcnow()
    follow.last_actor_login = actor_login
    follow.updated_at = utcnow()
    session.flush()
    _reconcile_entry_tracking_state(session, symbol=normalized_symbol)
    remaining = len(active_watchlist_symbols(session, account_login=target_login))
    session.commit()
    return {
        "symbol": normalized_symbol,
        "removed": True,
        "active_count": remaining,
        "removed_at": utcnow(),
    }
