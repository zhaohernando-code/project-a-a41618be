from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from ashare_evidence.models import MarketBar, PaperOrder, PaperPortfolio, SectorMembership, Stock


def _latest_close_by_symbol(session: Session) -> dict[str, float]:
    rows = session.execute(
        select(Stock.symbol, MarketBar.observed_at, MarketBar.close_price)
        .join(MarketBar, MarketBar.stock_id == Stock.id)
        .where(MarketBar.timeframe == "1d")
        .order_by(Stock.symbol.asc(), MarketBar.observed_at.asc())
    ).all()
    result: dict[str, float] = {}
    for symbol, _observed_at, close_price in rows:
        result[str(symbol)] = float(close_price)
    return result


def _primary_sector_by_stock(session: Session) -> dict[int, str]:
    memberships = session.scalars(
        select(SectorMembership)
        .options(joinedload(SectorMembership.sector))
        .order_by(SectorMembership.is_primary.desc(), SectorMembership.effective_from.desc())
    ).all()
    result: dict[int, str] = {}
    for membership in memberships:
        if membership.stock_id not in result and membership.sector is not None:
            result[membership.stock_id] = membership.sector.name
    return result


def _portfolio_holdings_exposure(session: Session) -> dict[str, Any] | None:
    portfolios = session.scalars(
        select(PaperPortfolio)
        .options(
            selectinload(PaperPortfolio.orders)
            .selectinload(PaperOrder.fills),
            selectinload(PaperPortfolio.orders)
            .joinedload(PaperOrder.stock),
        )
        .where(PaperPortfolio.status == "active")
    ).all()
    if not portfolios:
        return None
    latest_close = _latest_close_by_symbol(session)
    primary_sector = _primary_sector_by_stock(session)
    exposure: dict[str, dict[str, Any]] = defaultdict(lambda: {"market_value": 0.0, "symbols": set(), "position_count": 0})
    total_market_value = 0.0
    unknown_market_value = 0.0
    holding_count = 0
    for portfolio in portfolios:
        quantities: dict[int, int] = defaultdict(int)
        stocks: dict[int, Stock] = {}
        for order in portfolio.orders:
            if order.stock is None:
                continue
            stocks[order.stock_id] = order.stock
            fill_quantity = sum(int(fill.quantity) for fill in order.fills)
            if order.side == "buy":
                quantities[order.stock_id] += fill_quantity
            else:
                quantities[order.stock_id] -= fill_quantity
        for stock_id, quantity in quantities.items():
            if quantity <= 0:
                continue
            stock = stocks.get(stock_id)
            if stock is None:
                continue
            close = latest_close.get(stock.symbol)
            if close is None:
                continue
            market_value = close * quantity
            sector = primary_sector.get(stock_id, "未知行业")
            bucket = exposure[sector]
            bucket["market_value"] += market_value
            bucket["symbols"].add(stock.symbol)
            bucket["position_count"] += 1
            total_market_value += market_value
            holding_count += 1
            if sector == "未知行业":
                unknown_market_value += market_value
    if total_market_value <= 0:
        return None
    sectors: dict[str, Any] = {}
    for sector, data in sorted(exposure.items(), key=lambda item: item[1]["market_value"], reverse=True):
        weight = float(data["market_value"]) / total_market_value
        sectors[sector] = {
            "market_value": round(float(data["market_value"]), 2),
            "portfolio_weight": round(weight, 4),
            "benchmark_weight": None,
            "active_weight": None,
            "position_count": int(data["position_count"]),
            "symbols": sorted(data["symbols"]),
        }
    return {
        "source": "portfolio_holdings",
        "total_market_value": round(total_market_value, 2),
        "holding_count": holding_count,
        "sector_count": len(sectors),
        "unknown_weight": round(unknown_market_value / total_market_value, 4),
        "sectors": sectors,
        "note": "行业暴露按模拟组合实际持仓市值权重计算；benchmark 行业权重待 CSI 成分行业映射后补齐。",
    }


def _candidate_fallback(session: Session) -> dict[str, Any]:
    from ashare_evidence.dashboard import list_candidate_recommendations

    candidates = list_candidate_recommendations(session, limit=20)
    items = candidates.get("items", [])
    sectors: dict[str, dict[str, Any]] = {}
    for item in items:
        sector_tags = item.get("sector_tags", [])
        if not sector_tags and item.get("sector"):
            sector_tags = [item["sector"]]
        for sector in sector_tags:
            entry = sectors.setdefault(sector, {"count": 0, "symbols": [], "directions": []})
            entry["count"] += 1
            entry["symbols"].append(item.get("symbol", "?"))
            entry["directions"].append(item.get("display_direction_label", item.get("direction_label", "?")))
    result: dict[str, Any] = {
        "source": "candidate_recommendation_fallback",
        "total_candidates": len(items),
        "sector_count": len(sectors),
        "unknown_weight": None,
        "sectors": {},
        "note": "当前没有可用持仓市值，临时展示候选池行业分布；不作为组合暴露结论。",
    }
    for sector, data in sorted(sectors.items(), key=lambda x: x[1]["count"], reverse=True):
        buy_count = sum(1 for d in data["directions"] if d in ("可建仓", "可加仓"))
        watch_count = sum(1 for d in data["directions"] if d == "继续观察")
        result["sectors"][sector] = {
            "count": data["count"],
            "buy_ratio": round(buy_count / data["count"], 3) if data["count"] else 0,
            "watch_ratio": round(watch_count / data["count"], 3) if data["count"] else 0,
            "symbols": data["symbols"],
        }
    return result


def build_sector_exposure(session: Session) -> dict[str, Any]:
    return _portfolio_holdings_exposure(session) or _candidate_fallback(session)
