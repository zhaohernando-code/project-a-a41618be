from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ashare_evidence.models import MarketBar, NewsEntityLink, NewsItem, SectorMembership, Stock


def daily_bar_maps(session: Session, symbols: set[str] | None = None) -> tuple[dict[str, list[MarketBar]], dict[str, dict[date, float]]]:
    query = (
        select(MarketBar)
        .join(Stock)
        .where(MarketBar.timeframe == "1d")
        .options(joinedload(MarketBar.stock))
        .order_by(Stock.symbol.asc(), MarketBar.observed_at.asc())
    )
    if symbols:
        query = query.where(Stock.symbol.in_(sorted(symbols)))
    bars = session.scalars(query).all()
    grouped: dict[str, list[MarketBar]] = defaultdict(list)
    close_maps: dict[str, dict[date, float]] = defaultdict(dict)
    for bar in bars:
        grouped[bar.stock.symbol].append(bar)
        close_maps[bar.stock.symbol][bar.observed_at.date()] = float(bar.close_price)
    return grouped, close_maps


def latest_sector_memberships(session: Session) -> dict[str, str]:
    memberships = session.scalars(
        select(SectorMembership)
        .join(Stock)
        .options(joinedload(SectorMembership.stock), joinedload(SectorMembership.sector))
        .order_by(Stock.symbol.asc(), SectorMembership.effective_from.desc())
    ).all()
    latest: dict[str, str] = {}
    for membership in memberships:
        latest.setdefault(membership.stock.symbol, membership.sector.sector_code)
    return latest


def news_by_symbol(session: Session, symbols: set[str] | None = None) -> tuple[dict[str, list[NewsItem]], dict[str, list[NewsEntityLink]]]:
    items = session.scalars(select(NewsItem).order_by(NewsItem.published_at.asc())).all()
    links = session.scalars(
        select(NewsEntityLink)
        .options(joinedload(NewsEntityLink.news_item), joinedload(NewsEntityLink.stock), joinedload(NewsEntityLink.sector))
        .order_by(NewsEntityLink.effective_at.asc())
    ).all()
    sector_map = latest_sector_memberships(session)
    symbol_items: dict[str, list[NewsItem]] = defaultdict(list)
    symbol_links: dict[str, list[NewsEntityLink]] = defaultdict(list)
    for link in links:
        if link.stock is not None:
            symbol = link.stock.symbol
            if symbols and symbol not in symbols:
                continue
            symbol_links[symbol].append(link)
            symbol_items[symbol].append(link.news_item)
            continue
        if link.sector is None:
            continue
        for symbol, sector_code in sector_map.items():
            if sector_code != link.sector.sector_code:
                continue
            if symbols and symbol not in symbols:
                continue
            symbol_links[symbol].append(link)
            symbol_items[symbol].append(link.news_item)

    for symbol in list(symbol_items):
        deduped: dict[str, NewsItem] = {}
        for item in symbol_items[symbol]:
            deduped[item.news_key] = item
        symbol_items[symbol] = sorted(deduped.values(), key=lambda item: item.published_at)
    return symbol_items, symbol_links


def portfolio_price_history(
    session: Session,
    symbols: set[str],
) -> tuple[dict[str, list[tuple[datetime, float]]], dict[str, str], list[datetime]]:
    query = (
        select(MarketBar)
        .join(Stock)
        .where(MarketBar.timeframe == "1d", Stock.symbol.in_(sorted(symbols)))
        .options(joinedload(MarketBar.stock))
        .order_by(MarketBar.observed_at.asc())
    )
    bars = session.scalars(query).all()
    price_history: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
    stock_names: dict[str, str] = {}
    points: list[datetime] = []
    seen: set[datetime] = set()
    for bar in bars:
        symbol = bar.stock.symbol
        price_history[symbol].append((bar.observed_at, float(bar.close_price)))
        stock_names[symbol] = bar.stock.name
        if bar.observed_at not in seen:
            points.append(bar.observed_at)
            seen.add(bar.observed_at)
    return price_history, stock_names, sorted(points)
