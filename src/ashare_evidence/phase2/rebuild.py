from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ashare_evidence.models import PaperPortfolio, Recommendation, Stock, WatchlistEntry
from ashare_evidence.phase2.common import build_equal_weight_proxy, build_expanding_equal_weight_proxy
from ashare_evidence.phase2.constants import PHASE2_HORIZONS, PHASE2_PRIMARY_HORIZON
from ashare_evidence.phase2.data import daily_bar_maps, latest_sector_memberships, news_by_symbol
from ashare_evidence.phase2.observations import build_observation_context
from ashare_evidence.phase2.portfolio import build_portfolio_backtest_artifacts
from ashare_evidence.phase2.replay import build_replay_artifacts
from ashare_evidence.phase2.validation import build_validation_artifacts_for_recommendation, update_recommendation_payload
from ashare_evidence.research_artifact_store import (
    artifact_root_from_database_url,
    portfolio_backtest_artifact_id,
    write_backtest_artifact,
    write_manifest,
    write_replay_alignment_artifact,
    write_validation_metrics,
)


def _proxy_membership_start_dates(
    session: Session,
    *,
    proxy_symbols: list[str],
    close_maps: dict[str, dict[date, float]],
) -> tuple[dict[str, date], dict[str, Any]]:
    watchlist_entries = session.scalars(
        select(WatchlistEntry).where(
            WatchlistEntry.symbol.in_(proxy_symbols),
            WatchlistEntry.status == "active",
        )
    ).all()
    watchlist_starts = {entry.symbol: entry.created_at.date() for entry in watchlist_entries}

    membership_start_dates: dict[str, date] = {}
    defaulted_symbols: list[str] = []
    for symbol in proxy_symbols:
        if symbol in watchlist_starts:
            membership_start_dates[symbol] = watchlist_starts[symbol]
            continue
        series = close_maps.get(symbol, {})
        if not series:
            continue
        membership_start_dates[symbol] = min(series)
        defaulted_symbols.append(symbol)

    return membership_start_dates, {
        "defaulted_symbol_count": len(defaulted_symbols),
        "defaulted_symbols": sorted(defaulted_symbols),
    }


def rebuild_phase2_research_state(
    session: Session,
    *,
    symbols: set[str] | None = None,
    active_symbols: set[str] | None = None,
) -> dict[str, Any]:
    session.flush()
    update_scope = set(symbols or set())
    active_scope = set(active_symbols or set())
    data_scope = update_scope | active_scope

    daily_bars_by_symbol, close_maps = daily_bar_maps(session, data_scope or None)
    if not daily_bars_by_symbol:
        return {"recommendations": 0, "validation_artifacts": 0, "replay_artifacts": 0, "backtests": 0}

    update_symbols = sorted(update_scope or set(daily_bars_by_symbol))
    if not update_symbols:
        return {"recommendations": 0, "validation_artifacts": 0, "replay_artifacts": 0, "backtests": 0}

    proxy_symbols = sorted(active_scope or update_symbols)
    symbol_items, symbol_links = news_by_symbol(session, set(update_symbols))
    sector_map = latest_sector_memberships(session)
    market_proxy: dict[date, float] = {}
    market_proxy_context: dict[str, Any] = {}
    if len(proxy_symbols) > 1:
        membership_start_dates, proxy_membership_context = _proxy_membership_start_dates(
            session,
            proxy_symbols=proxy_symbols,
            close_maps=close_maps,
        )
        market_proxy, market_proxy_context = build_expanding_equal_weight_proxy(
            close_maps,
            membership_start_dates,
        )
        market_proxy_context = {
            **market_proxy_context,
            **proxy_membership_context,
        }
    sector_symbols: dict[str, list[str]] = defaultdict(list)
    for symbol in daily_bars_by_symbol:
        sector_code = sector_map.get(symbol)
        if sector_code:
            sector_symbols[sector_code].append(symbol)

    recommendations = session.scalars(
        select(Recommendation)
        .join(Stock)
        .options(joinedload(Recommendation.stock))
        .order_by(Stock.symbol.asc(), Recommendation.generated_at.asc())
    ).all()
    bind = session.get_bind()
    artifact_root = artifact_root_from_database_url(bind.url.render_as_string(hide_password=False) if bind else None)

    validation_artifact_count = 0
    updated_recommendations = 0
    for recommendation in recommendations:
        symbol = recommendation.stock.symbol
        if update_scope and symbol not in update_scope:
            continue
        bars = daily_bars_by_symbol.get(symbol, [])
        if len(bars) <= max(PHASE2_HORIZONS) * 2:
            continue
        sector_proxy: dict[date, float] | None = None
        sector_code = sector_map.get(symbol)
        if sector_code and len(sector_symbols.get(sector_code, [])) > 1:
            sector_proxy = build_equal_weight_proxy(close_maps, sorted(sector_symbols[sector_code]))
        observations = build_observation_context(
            session,
            symbol=symbol,
            bars=bars,
            items=symbol_items.get(symbol, []),
            links=symbol_links.get(symbol, []),
            market_proxy=market_proxy,
            sector_proxy=sector_proxy,
            stock_id=recommendation.stock_id,
        )
        manifest, metrics_artifacts = build_validation_artifacts_for_recommendation(
            recommendation,
            bars=bars,
            observations=observations,
            market_proxy=market_proxy,
            market_proxy_context=market_proxy_context,
            sector_proxy=sector_proxy,
        )
        write_manifest(manifest, root=artifact_root)
        for artifact in metrics_artifacts:
            write_validation_metrics(artifact, root=artifact_root)
        primary_metrics = next(artifact for artifact in metrics_artifacts if artifact.horizon == PHASE2_PRIMARY_HORIZON)
        update_recommendation_payload(
            recommendation,
            manifest=manifest,
            primary_metrics=primary_metrics,
            metrics_artifacts=metrics_artifacts,
        )
        validation_artifact_count += len(metrics_artifacts)
        updated_recommendations += 1

    active_scope = active_scope or set(update_symbols)
    replay_artifacts = build_replay_artifacts(
        session,
        active_symbols=active_scope,
        close_maps=close_maps,
        market_proxy=market_proxy,
        market_proxy_context=market_proxy_context,
        sector_map=sector_map,
    )
    for artifact in replay_artifacts:
        write_replay_alignment_artifact(artifact, root=artifact_root)

    all_trade_days = sorted({trade_day for series in close_maps.values() for trade_day in series})
    portfolio_proxy = market_proxy if market_proxy else {trade_day: 100.0 for trade_day in all_trade_days}
    portfolio_manifest, backtests = build_portfolio_backtest_artifacts(
        session,
        active_symbols=active_scope,
        market_proxy=portfolio_proxy,
        market_proxy_context=market_proxy_context,
    )
    write_manifest(portfolio_manifest, root=artifact_root)
    for artifact in backtests:
        write_backtest_artifact(artifact, root=artifact_root)
    backtest_ids_by_key = {
        artifact.artifact_id.removeprefix("portfolio-backtest:"): artifact.artifact_id
        for artifact in backtests
    }
    if backtest_ids_by_key:
        portfolios = session.scalars(
            select(PaperPortfolio).where(PaperPortfolio.portfolio_key.in_(sorted(backtest_ids_by_key)))
        ).all()
        for portfolio in portfolios:
            canonical_artifact_id = backtest_ids_by_key.get(portfolio.portfolio_key) or portfolio_backtest_artifact_id(
                portfolio.portfolio_key
            )
            if not canonical_artifact_id:
                continue
            payload = dict(portfolio.portfolio_payload or {})
            portfolio.portfolio_payload = {
                **payload,
                "backtest_artifact_id": canonical_artifact_id,
                "validation_manifest_id": portfolio_manifest.artifact_id,
            }

    session.flush()
    return {
        "recommendations": updated_recommendations,
        "validation_artifacts": validation_artifact_count,
        "replay_artifacts": len(replay_artifacts),
        "backtests": len(backtests),
    }
