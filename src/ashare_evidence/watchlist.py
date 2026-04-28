from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ashare_evidence.analysis_pipeline import refresh_real_analysis
from ashare_evidence.db import align_datetime_timezone, utcnow
from ashare_evidence.lineage import build_lineage
from ashare_evidence.models import Recommendation, Stock, WatchlistEntry
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


def _serialize_watchlist_entry(session: Session, entry: WatchlistEntry) -> dict[str, Any]:
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
        "status": entry.status,
        "source_kind": entry.source_kind,
        "analysis_status": entry.analysis_status,
        "added_at": entry.created_at,
        "updated_at": entry.updated_at,
        "last_analyzed_at": entry.last_analyzed_at,
        "last_error": entry.last_error,
        "latest_direction": latest.direction if latest is not None else None,
        "latest_confidence_label": latest.confidence_label if latest is not None else None,
        "latest_generated_at": latest_generated_at,
    }


def active_watchlist_symbols(session: Session) -> list[str]:
    entries = session.scalars(
        select(WatchlistEntry)
        .where(WatchlistEntry.status == ACTIVE_STATUS)
        .order_by(WatchlistEntry.updated_at.desc(), WatchlistEntry.created_at.asc())
    ).all()
    return [entry.symbol for entry in entries]


def list_watchlist_entries(session: Session) -> dict[str, Any]:
    entries = session.scalars(
        select(WatchlistEntry)
        .where(WatchlistEntry.status == ACTIVE_STATUS)
        .order_by(WatchlistEntry.updated_at.desc(), WatchlistEntry.created_at.asc())
    ).all()
    return {
        "generated_at": utcnow(),
        "items": [_serialize_watchlist_entry(session, entry) for entry in entries],
    }


def add_watchlist_symbol(session: Session, symbol: str, stock_name: str | None = None) -> dict[str, Any]:
    entry = _sync_watchlist_symbol(
        session,
        symbol=symbol,
        stock_name=stock_name,
        source_kind=USER_SOURCE_KIND,
        force_refresh=False,
    )
    session.commit()
    session.refresh(entry)
    return _serialize_watchlist_entry(session, entry)


def refresh_watchlist_symbol(session: Session, symbol: str) -> dict[str, Any]:
    normalized_symbol = normalize_symbol(symbol)
    existing = session.scalar(select(WatchlistEntry).where(WatchlistEntry.symbol == normalized_symbol))
    if existing is None or existing.status != ACTIVE_STATUS:
        raise LookupError(f"{normalized_symbol} 不在当前自选池中。")
    entry = _sync_watchlist_symbol(
        session,
        symbol=normalized_symbol,
        stock_name=existing.display_name,
        source_kind=existing.source_kind,
        force_refresh=True,
    )
    entry.updated_at = utcnow()
    session.commit()
    session.refresh(entry)
    return _serialize_watchlist_entry(session, entry)


def remove_watchlist_symbol(session: Session, symbol: str) -> dict[str, Any]:
    normalized_symbol = normalize_symbol(symbol)
    entry = session.scalar(select(WatchlistEntry).where(WatchlistEntry.symbol == normalized_symbol))
    if entry is None or entry.status != ACTIVE_STATUS:
        raise LookupError(f"{normalized_symbol} 不在当前自选池中。")
    entry.status = REMOVED_STATUS
    entry.analysis_status = "removed"
    entry.last_error = None
    entry.updated_at = utcnow()
    session.flush()
    remaining = len(active_watchlist_symbols(session))
    session.commit()
    return {
        "symbol": normalized_symbol,
        "removed": True,
        "active_count": remaining,
        "removed_at": utcnow(),
    }
