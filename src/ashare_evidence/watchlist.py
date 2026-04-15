from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ashare_evidence.dashboard_demo import WATCHLIST_SYMBOLS, build_dashboard_bundle, normalize_symbol
from ashare_evidence.db import utcnow
from ashare_evidence.lineage import build_lineage
from ashare_evidence.models import Recommendation, Stock, WatchlistEntry
from ashare_evidence.services import ingest_bundle

ACTIVE_STATUS = "active"
REMOVED_STATUS = "removed"
DEFAULT_SOURCE_KIND = "default_seed"
USER_SOURCE_KIND = "user_input"


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
    return session.scalar(
        select(Recommendation)
        .join(Stock)
        .options(joinedload(Recommendation.stock))
        .where(Stock.symbol == symbol)
        .order_by(Recommendation.generated_at.desc())
        .limit(1)
    )


def _upsert_watchlist_entry(
    session: Session,
    *,
    symbol: str,
    display_name: str,
    source_kind: str,
    analyzed_at: datetime | None,
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
        "analysis_status": "ready",
        "last_analyzed_at": analyzed_at,
        "last_error": None,
        "watchlist_payload": {
            "source_kind": source_kind,
            "watchlist_scope": "一期自选股池",
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


def _analyze_watchlist_symbol(
    session: Session,
    *,
    symbol: str,
    stock_name: str | None,
    source_kind: str,
) -> WatchlistEntry:
    normalized_symbol = normalize_symbol(symbol)
    latest_name = stock_name
    analyzed_at: datetime | None = None
    for snapshot in ("previous", "latest"):
        recommendation = ingest_bundle(
            session,
            build_dashboard_bundle(normalized_symbol, snapshot=snapshot, stock_name=stock_name),
        )
        analyzed_at = recommendation.generated_at
        latest_name = recommendation.stock.name

    stock = session.scalar(select(Stock).where(Stock.symbol == normalized_symbol))
    resolved_name = stock.name if stock is not None else latest_name or normalized_symbol
    return _upsert_watchlist_entry(
        session,
        symbol=normalized_symbol,
        display_name=resolved_name,
        source_kind=source_kind,
        analyzed_at=analyzed_at,
    )


def _serialize_watchlist_entry(session: Session, entry: WatchlistEntry) -> dict[str, Any]:
    stock = session.scalar(select(Stock).where(Stock.symbol == entry.symbol))
    latest = _latest_recommendation(session, entry.symbol)
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
        "latest_generated_at": latest.generated_at if latest is not None else None,
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
    entry = _analyze_watchlist_symbol(
        session,
        symbol=symbol,
        stock_name=stock_name,
        source_kind=USER_SOURCE_KIND,
    )
    session.commit()
    session.refresh(entry)
    return _serialize_watchlist_entry(session, entry)


def refresh_watchlist_symbol(session: Session, symbol: str) -> dict[str, Any]:
    normalized_symbol = normalize_symbol(symbol)
    existing = session.scalar(select(WatchlistEntry).where(WatchlistEntry.symbol == normalized_symbol))
    if existing is None or existing.status != ACTIVE_STATUS:
        raise LookupError(f"{normalized_symbol} 不在当前自选池中。")
    entry = _analyze_watchlist_symbol(
        session,
        symbol=normalized_symbol,
        stock_name=existing.display_name,
        source_kind=existing.source_kind,
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


def reset_watchlist_to_defaults(session: Session) -> dict[str, Any]:
    default_symbols = {normalize_symbol(symbol) for symbol in WATCHLIST_SYMBOLS}
    existing_entries = session.scalars(select(WatchlistEntry)).all()
    for entry in existing_entries:
        entry.status = ACTIVE_STATUS if entry.symbol in default_symbols else REMOVED_STATUS
        entry.analysis_status = "ready" if entry.symbol in default_symbols else "removed"
        entry.last_error = None
    recommendation_count = 0
    for symbol in WATCHLIST_SYMBOLS:
        _analyze_watchlist_symbol(
            session,
            symbol=symbol,
            stock_name=None,
            source_kind=DEFAULT_SOURCE_KIND,
        )
        recommendation_count += 2
    session.commit()
    return {
        "symbols": list(WATCHLIST_SYMBOLS),
        "recommendation_count": recommendation_count,
        "candidate_count": len(active_watchlist_symbols(session)),
    }
