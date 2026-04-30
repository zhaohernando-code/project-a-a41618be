from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ashare_evidence.market_clock import latest_completed_trade_day
from ashare_evidence.models import Recommendation
from ashare_evidence.providers import EvidenceBundle, with_lineage
from ashare_evidence.research_artifact_builders import (
    build_migration_portfolio_backtest_artifacts,
    build_migration_replay_alignment_artifacts,
    build_migration_validation_artifacts,
)
from ashare_evidence.research_artifact_store import (
    artifact_root_from_database_url,
    write_backtest_artifact,
    write_manifest,
    write_replay_alignment_artifact,
    write_validation_metrics,
)
from ashare_evidence.services import ingest_bundle
from ashare_evidence.signal_engine import build_signal_artifacts
from ashare_evidence.watchlist import add_watchlist_symbol

DEFAULT_WATCHLIST_SYMBOLS = ("600519.SH", "300750.SZ", "601318.SH", "002594.SZ")


@dataclass(frozen=True)
class FixtureSpec:
    symbol: str
    name: str
    exchange: str
    industry: str
    sector_code: str
    sector_name: str
    listed_date: date
    start_price: float
    tier: str


FIXTURE_SPECS: dict[str, FixtureSpec] = {
    "600519.SH": FixtureSpec("600519.SH", "贵州茅台", "SSE", "白酒", "sw-food-beverage", "食品饮料", date(2001, 8, 27), 1680.0, "buy"),
    "300750.SZ": FixtureSpec("300750.SZ", "宁德时代", "SZSE", "电力设备", "sw-power-equipment", "电力设备", date(2018, 6, 11), 185.0, "watch"),
    "601318.SH": FixtureSpec("601318.SH", "中国平安", "SSE", "保险", "sw-nonbank-finance", "非银金融", date(2007, 3, 1), 46.0, "reduce"),
    "002594.SZ": FixtureSpec("002594.SZ", "比亚迪", "SZSE", "汽车", "sw-auto", "汽车", date(2011, 6, 30), 228.0, "risk"),
    "688981.SH": FixtureSpec("688981.SH", "中芯国际", "SSE", "半导体", "sw-electronics", "电子", date(2020, 7, 16), 89.0, "watch"),
    "002028.SZ": FixtureSpec("002028.SZ", "思源电气", "SZSE", "电力设备", "sw-power-equipment", "电力设备", date(2004, 8, 5), 73.0, "buy"),
}


def _business_days(end_day: date, count: int) -> list[date]:
    cursor = end_day
    days: list[date] = []
    while len(days) < count:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor -= timedelta(days=1)
    days.reverse()
    return days


def _bar_timestamp(trade_day: date) -> datetime:
    return datetime(trade_day.year, trade_day.month, trade_day.day, 7, 0, tzinfo=timezone.utc)


def _intraday_timestamps(trade_day: date) -> list[datetime]:
    points: list[datetime] = []
    for hour, minute in ((9, 35), (13, 5)):
        cursor = datetime(trade_day.year, trade_day.month, trade_day.day, hour, minute, tzinfo=timezone.utc)
        for _ in range(24):
            points.append(cursor)
            cursor += timedelta(minutes=5)
    return points


def _returns_for_tier(tier: str, length: int) -> list[float]:
    if tier == "buy":
        pattern = [0.0042, 0.0035, 0.0028, -0.0006, 0.0040, 0.0032, 0.0025, 0.0012]
    elif tier == "watch":
        pattern = [0.0012, -0.0008, 0.0015, -0.0010, 0.0009, 0.0011, -0.0006, 0.0007]
    elif tier == "reduce":
        pattern = [-0.0022, -0.0018, 0.0005, -0.0026, -0.0015, -0.0012, 0.0003, -0.0017]
    else:
        pattern = [-0.0040, -0.0034, 0.0004, -0.0048, -0.0026, -0.0031, 0.0002, -0.0025]
    repeats = (length + len(pattern) - 1) // len(pattern)
    return (pattern * repeats)[:length]


def _market_bars(spec: FixtureSpec) -> list[dict[str, Any]]:
    trade_days = _business_days(latest_completed_trade_day(), 42)
    returns = _returns_for_tier(spec.tier, len(trade_days))
    open_price = spec.start_price
    closes: list[float] = []
    bars: list[dict[str, Any]] = []

    for index, trade_day in enumerate(trade_days):
        close_price = round(open_price * (1 + returns[index]), 2)
        closes.append(close_price)
        high_price = round(max(open_price, close_price) * 1.011, 2)
        low_price = round(min(open_price, close_price) * 0.989, 2)
        volume = 2_000_000 + index * 90_000
        amount = round(volume * (open_price + close_price) / 2, 2)
        bars.append(
            with_lineage(
                {
                    "bar_key": f"bar-{spec.symbol}-{trade_day:%Y%m%d}",
                    "stock_symbol": spec.symbol,
                    "timeframe": "1d",
                    "observed_at": _bar_timestamp(trade_day),
                    "open_price": round(open_price, 2),
                    "high_price": high_price,
                    "low_price": low_price,
                    "close_price": close_price,
                    "volume": volume,
                    "amount": amount,
                    "turnover_rate": round(0.011 + index * 0.0002, 4),
                    "adj_factor": 1.0,
                    "raw_payload": {"provider": "tushare", "trade_date": trade_day.strftime("%Y%m%d")},
                },
                payload_key="raw_payload",
                source_uri=f"tushare://daily/{spec.symbol}?trade_date={trade_day:%Y%m%d}",
                license_tag="tushare-pro",
                redistribution_scope="limited-display",
            )
        )
        open_price = close_price

    latest_trade_day = trade_days[-1]
    previous_close = closes[-2]
    latest_close = closes[-1]
    intraday_start = round(previous_close * 1.001, 2)
    intraday_step = (latest_close - intraday_start) / 48
    current_open = intraday_start
    for index, observed_at in enumerate(_intraday_timestamps(latest_trade_day)):
        close_price = round(intraday_start + intraday_step * (index + 1), 2)
        high_price = round(max(current_open, close_price) * 1.0015, 2)
        low_price = round(min(current_open, close_price) * 0.9985, 2)
        volume = 56_000 + index * 1_100
        amount = round(volume * (current_open + close_price) / 2, 2)
        bars.append(
            with_lineage(
                {
                    "bar_key": f"bar-{spec.symbol}-5min-{observed_at:%Y%m%d%H%M}",
                    "stock_symbol": spec.symbol,
                    "timeframe": "5min",
                    "observed_at": observed_at,
                    "open_price": round(current_open, 2),
                    "high_price": high_price,
                    "low_price": low_price,
                    "close_price": close_price,
                    "volume": volume,
                    "amount": amount,
                    "turnover_rate": None,
                    "adj_factor": 1.0,
                    "raw_payload": {"provider": "tushare", "frequency": "5min", "trade_time": observed_at.isoformat()},
                },
                payload_key="raw_payload",
                source_uri=f"tushare://rt_min_daily/{spec.symbol}?freq=5MIN&time={observed_at.isoformat()}",
                license_tag="tushare-pro",
                redistribution_scope="limited-display",
            )
        )
        current_open = close_price
    return bars


def _news_items(spec: FixtureSpec, generated_at: datetime) -> list[dict[str, Any]]:
    ticker = spec.symbol.split(".")[0]
    return [
        with_lineage(
            {
                "news_key": f"news-{ticker}-financial",
                "provider_name": "cninfo",
                "external_id": f"cninfo-{ticker}-financial",
                "headline": f"{spec.name} 最新公告披露经营进展",
                "summary": f"{spec.name} 最新披露强调主营业务进展与现金流质量。",
                "content_excerpt": f"{spec.name} 最新披露可作为当前推荐的重要结构化证据。",
                "published_at": generated_at - timedelta(days=4),
                "event_scope": "stock",
                "dedupe_key": f"{ticker}-financial",
                "raw_payload": {"provider": "巨潮资讯", "announcement_type": "announcement"},
            },
            payload_key="raw_payload",
            source_uri=f"cninfo://announcements/{ticker}/latest-financial",
            license_tag="cninfo-public-disclosure",
            redistribution_scope="source-link-only",
        ),
        with_lineage(
            {
                "news_key": f"news-{ticker}-roadshow",
                "provider_name": "cninfo",
                "external_id": f"cninfo-{ticker}-roadshow",
                "headline": f"{spec.name} 机构调研纪要更新",
                "summary": f"{spec.name} 机构调研围绕景气度、订单与风险约束展开。",
                "content_excerpt": f"{spec.industry} 行业景气与公司执行情况是调研焦点。",
                "published_at": generated_at - timedelta(days=2, hours=2),
                "event_scope": "stock",
                "dedupe_key": f"{ticker}-roadshow",
                "raw_payload": {"provider": "巨潮资讯", "announcement_type": "investor_relation"},
            },
            payload_key="raw_payload",
            source_uri=f"cninfo://announcements/{ticker}/roadshow",
            license_tag="cninfo-public-disclosure",
            redistribution_scope="source-link-only",
        ),
        with_lineage(
            {
                "news_key": f"news-{ticker}-sector",
                "provider_name": "cninfo",
                "external_id": f"cninfo-{ticker}-sector",
                "headline": f"{spec.sector_name} 板块行业跟踪更新",
                "summary": f"{spec.sector_name} 板块近期政策与景气变化进入观察窗口。",
                "content_excerpt": f"{spec.sector_name} 板块消息会传导到个股推荐置信度。",
                "published_at": generated_at - timedelta(days=1, hours=5),
                "event_scope": "sector",
                "dedupe_key": f"{spec.sector_code}-sector",
                "raw_payload": {"provider": "巨潮资讯", "announcement_type": "sector_news"},
            },
            payload_key="raw_payload",
            source_uri=f"cninfo://news/{spec.sector_code}/sector",
            license_tag="cninfo-public-disclosure",
            redistribution_scope="source-link-only",
        ),
    ]


def _news_links(spec: FixtureSpec, generated_at: datetime) -> list[dict[str, Any]]:
    polarity = "negative" if spec.tier in {"reduce", "risk"} else "positive"
    sector_polarity = "negative" if spec.tier == "risk" else "positive"
    ticker = spec.symbol.split(".")[0]
    return [
        with_lineage(
            {
                "news_key": f"news-{ticker}-financial",
                "entity_type": "stock",
                "stock_symbol": spec.symbol,
                "sector_code": None,
                "market_tag": None,
                "relevance_score": 0.92,
                "impact_direction": polarity,
                "effective_at": generated_at - timedelta(days=4),
                "decay_half_life_hours": 96.0,
                "mapping_payload": {"layer": "stock", "dedupe_stage": "post-entity-map"},
            },
            payload_key="mapping_payload",
            source_uri=f"pipeline://news-link/{ticker}/financial/stock",
            license_tag="internal-derived",
        ),
        with_lineage(
            {
                "news_key": f"news-{ticker}-roadshow",
                "entity_type": "stock",
                "stock_symbol": spec.symbol,
                "sector_code": None,
                "market_tag": None,
                "relevance_score": 0.84,
                "impact_direction": polarity,
                "effective_at": generated_at - timedelta(days=2, hours=2),
                "decay_half_life_hours": 72.0,
                "mapping_payload": {"layer": "stock", "dedupe_stage": "post-entity-map"},
            },
            payload_key="mapping_payload",
            source_uri=f"pipeline://news-link/{ticker}/roadshow/stock",
            license_tag="internal-derived",
        ),
        with_lineage(
            {
                "news_key": f"news-{ticker}-sector",
                "entity_type": "sector",
                "stock_symbol": None,
                "sector_code": spec.sector_code,
                "market_tag": None,
                "relevance_score": 0.58,
                "impact_direction": sector_polarity,
                "effective_at": generated_at - timedelta(days=1, hours=5),
                "decay_half_life_hours": 48.0,
                "mapping_payload": {"layer": "sector", "dedupe_stage": "post-entity-map"},
            },
            payload_key="mapping_payload",
            source_uri=f"pipeline://news-link/{spec.sector_code}/sector",
            license_tag="internal-derived",
        ),
    ]


def _simulation_artifacts(
    *,
    spec: FixtureSpec,
    generated_at: datetime,
    recommendation_key: str,
    analysis_bars: list[dict[str, Any]],
    snapshot_tag: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    seed_bar = analysis_bars[-8]
    latest_close = float(analysis_bars[-1]["close_price"])
    seed_price = round(float(seed_bar["close_price"]) * 1.001, 2)
    ticker = spec.symbol.split(".")[0]
    paper_portfolios = [
        with_lineage(
            {
                "portfolio_key": "portfolio-manual-live",
                "name": "手动模拟仓",
                "mode": "manual",
                "benchmark_symbol": "000300.SH",
                "base_currency": "CNY",
                "cash_balance": 900000.0,
                "status": "active",
                "portfolio_payload": {
                    "purpose": "manual-paper-trade",
                    "starting_cash": 900000.0,
                    "backtest_artifact_id": "portfolio-backtest:portfolio-manual-live",
                },
            },
            payload_key="portfolio_payload",
            source_uri="simulation://portfolio/manual-live",
            license_tag="internal-derived",
        ),
        with_lineage(
            {
                "portfolio_key": "portfolio-auto-live",
                "name": "模型自动持仓模拟仓",
                "mode": "auto_model",
                "benchmark_symbol": "000300.SH",
                "base_currency": "CNY",
                "cash_balance": 1800000.0,
                "status": "active",
                "portfolio_payload": {
                    "purpose": "auto-model-portfolio",
                    "starting_cash": 1800000.0,
                    "backtest_artifact_id": "portfolio-backtest:portfolio-auto-live",
                },
            },
            payload_key="portfolio_payload",
            source_uri="simulation://portfolio/auto-live",
            license_tag="internal-derived",
        ),
    ]
    paper_orders = [
        with_lineage(
            {
                "order_key": f"order-manual-seed-{ticker}-{snapshot_tag}",
                "portfolio_key": "portfolio-manual-live",
                "stock_symbol": spec.symbol,
                "recommendation_key": None,
                "order_source": "manual",
                "side": "buy",
                "requested_at": seed_bar["observed_at"],
                "quantity": 100,
                "order_type": "limit",
                "limit_price": seed_price,
                "status": "filled",
                "notes": "历史真实样本仓位。",
                "order_payload": {"execution_mode": "manual", "intent": "historical_position"},
            },
            payload_key="order_payload",
            source_uri=f"simulation://order/manual/{ticker}/seed/{snapshot_tag}",
            license_tag="internal-derived",
        ),
        with_lineage(
            {
                "order_key": f"order-manual-{ticker}-{snapshot_tag}",
                "portfolio_key": "portfolio-manual-live",
                "stock_symbol": spec.symbol,
                "recommendation_key": recommendation_key,
                "order_source": "manual",
                "side": "buy",
                "requested_at": generated_at,
                "quantity": 100,
                "order_type": "limit",
                "limit_price": round(latest_close * 1.001, 2),
                "status": "filled",
                "notes": "研究员对真实建议做人工确认。",
                "order_payload": {"execution_mode": "manual"},
            },
            payload_key="order_payload",
            source_uri=f"simulation://order/manual/{ticker}/{snapshot_tag}",
            license_tag="internal-derived",
        ),
        with_lineage(
            {
                "order_key": f"order-auto-{ticker}-{snapshot_tag}",
                "portfolio_key": "portfolio-auto-live",
                "stock_symbol": spec.symbol,
                "recommendation_key": recommendation_key,
                "order_source": "model",
                "side": "buy",
                "requested_at": generated_at,
                "quantity": 200,
                "order_type": "market",
                "limit_price": None,
                "status": "filled",
                "notes": "模型组合按策略权重执行。",
                "order_payload": {"execution_mode": "auto_model"},
            },
            payload_key="order_payload",
            source_uri=f"simulation://order/auto/{ticker}/{snapshot_tag}",
            license_tag="internal-derived",
        ),
    ]
    paper_fills = [
        with_lineage(
            {
                "fill_key": f"fill-manual-seed-{ticker}-{snapshot_tag}",
                "order_key": f"order-manual-seed-{ticker}-{snapshot_tag}",
                "stock_symbol": spec.symbol,
                "filled_at": seed_bar["observed_at"],
                "price": seed_price,
                "quantity": 100,
                "fee": round(seed_price * 100 * 0.0005, 2),
                "tax": 0.0,
                "slippage_bps": 2.8,
                "fill_payload": {"matching_rule": "paper"},
            },
            payload_key="fill_payload",
            source_uri=f"simulation://fill/manual/{ticker}/seed/{snapshot_tag}",
            license_tag="internal-derived",
        ),
        with_lineage(
            {
                "fill_key": f"fill-manual-{ticker}-{snapshot_tag}",
                "order_key": f"order-manual-{ticker}-{snapshot_tag}",
                "stock_symbol": spec.symbol,
                "filled_at": generated_at,
                "price": round(latest_close * 1.001, 2),
                "quantity": 100,
                "fee": round(latest_close * 100 * 0.0005, 2),
                "tax": 0.0,
                "slippage_bps": 3.2,
                "fill_payload": {"matching_rule": "paper"},
            },
            payload_key="fill_payload",
            source_uri=f"simulation://fill/manual/{ticker}/{snapshot_tag}",
            license_tag="internal-derived",
        ),
        with_lineage(
            {
                "fill_key": f"fill-auto-{ticker}-{snapshot_tag}",
                "order_key": f"order-auto-{ticker}-{snapshot_tag}",
                "stock_symbol": spec.symbol,
                "filled_at": generated_at,
                "price": round(latest_close * 1.001, 2),
                "quantity": 200,
                "fee": round(latest_close * 200 * 0.0005, 2),
                "tax": 0.0,
                "slippage_bps": 3.6,
                "fill_payload": {"matching_rule": "paper"},
            },
            payload_key="fill_payload",
            source_uri=f"simulation://fill/auto/{ticker}/{snapshot_tag}",
            license_tag="internal-derived",
        ),
    ]
    return paper_portfolios, paper_orders, paper_fills


def _ingest_fixture_snapshot(session: Session, spec: FixtureSpec, *, analysis_bars: list[dict[str, Any]], snapshot_tag: str) -> None:
    full_market_bars = _market_bars(spec)
    stock = with_lineage(
        {
            "symbol": spec.symbol,
            "ticker": spec.symbol.split(".")[0],
            "exchange": spec.exchange,
            "name": spec.name,
            "provider_symbol": spec.symbol,
            "listed_date": spec.listed_date,
            "status": "active",
            "profile_payload": {"industry": spec.industry, "provider": "tushare"},
        },
        payload_key="profile_payload",
        source_uri=f"tushare://stock_basic/{spec.symbol}",
        license_tag="tushare-pro",
        redistribution_scope="limited-display",
    )
    sectors = [
        with_lineage(
            {
                "sector_code": spec.sector_code,
                "name": spec.sector_name,
                "level": "industry",
                "definition_payload": {"taxonomy": "申万一级", "provider": "tushare"},
            },
            payload_key="definition_payload",
            source_uri=f"tushare://index_member/{spec.sector_code}",
            license_tag="tushare-pro",
            redistribution_scope="limited-display",
        )
    ]
    sector_memberships = [
        with_lineage(
            {
                "membership_key": f"membership-{spec.symbol}-{spec.sector_code}",
                "stock_symbol": spec.symbol,
                "sector_code": spec.sector_code,
                "effective_from": datetime(2020, 1, 1, tzinfo=timezone.utc),
                "effective_to": None,
                "is_primary": True,
                "membership_payload": {"weighting_hint": "primary-industry"},
            },
            payload_key="membership_payload",
            source_uri=f"tushare://index_member/{spec.symbol}/{spec.sector_code}",
            license_tag="tushare-pro",
            redistribution_scope="limited-display",
        )
    ]
    generated_at = analysis_bars[-1]["observed_at"] + timedelta(hours=1, minutes=5)
    news_items = _news_items(spec, generated_at)
    news_links = _news_links(spec, generated_at)
    signal_artifacts = build_signal_artifacts(
        symbol=spec.symbol,
        stock_name=spec.name,
        market_bars=analysis_bars,
        news_items=news_items,
        news_links=news_links,
        sector_memberships=sector_memberships,
        generated_at=generated_at,
    )
    manifest_artifact, validation_metrics_artifact = build_migration_validation_artifacts(signal_artifacts)
    recommendation_payload = dict(signal_artifacts.recommendation["recommendation_payload"])
    historical_validation = dict(recommendation_payload.get("historical_validation") or {})
    historical_validation["artifact_type"] = "validation_metrics"
    historical_validation["artifact_id"] = validation_metrics_artifact.artifact_id
    historical_validation["manifest_id"] = manifest_artifact.artifact_id
    recommendation_payload["historical_validation"] = historical_validation
    recommendation_payload["validation_metrics_artifact_id"] = validation_metrics_artifact.artifact_id
    signal_artifacts.recommendation["recommendation_payload"] = recommendation_payload
    paper_portfolios, paper_orders, paper_fills = _simulation_artifacts(
        spec=spec,
        generated_at=generated_at,
        recommendation_key=signal_artifacts.recommendation["recommendation_key"],
        analysis_bars=analysis_bars,
        snapshot_tag=snapshot_tag,
    )
    bind = session.get_bind()
    artifact_root = artifact_root_from_database_url(bind.url.render_as_string(hide_password=False) if bind else None)
    write_manifest(manifest_artifact, root=artifact_root)
    write_validation_metrics(validation_metrics_artifact, root=artifact_root)
    ingest_bundle(
        session,
        EvidenceBundle(
            provider_name="fixture-real-data",
            symbol=spec.symbol,
            stock=stock,
            sectors=sectors,
            sector_memberships=sector_memberships,
            market_bars=full_market_bars,
            news_items=news_items,
            news_links=news_links,
            feature_snapshots=signal_artifacts.feature_snapshots,
            model_registry=signal_artifacts.model_registry,
            model_version=signal_artifacts.model_version,
            prompt_version=signal_artifacts.prompt_version,
            model_run=signal_artifacts.model_run,
            model_results=signal_artifacts.model_results,
            recommendation=signal_artifacts.recommendation,
            recommendation_evidence=signal_artifacts.recommendation_evidence,
            paper_portfolios=paper_portfolios,
            paper_orders=paper_orders,
            paper_fills=paper_fills,
        ),
    )


def seed_recommendation_fixture(session: Session, symbol: str) -> None:
    spec = FIXTURE_SPECS[symbol]
    market_bars = _market_bars(spec)
    analysis_bars = [item for item in market_bars if item["timeframe"] == "1d"]
    _ingest_fixture_snapshot(session, spec, analysis_bars=analysis_bars[:-1], snapshot_tag="previous")
    _ingest_fixture_snapshot(session, spec, analysis_bars=analysis_bars, snapshot_tag="latest")


def seed_watchlist_fixture(session: Session, symbols: tuple[str, ...] = DEFAULT_WATCHLIST_SYMBOLS) -> None:
    for symbol in symbols:
        seed_recommendation_fixture(session, symbol)
    session.commit()
    for symbol in symbols:
        add_watchlist_symbol(session, symbol, stock_name=FIXTURE_SPECS[symbol].name)
    session.commit()
    from ashare_evidence.operations import build_operations_dashboard

    operations = build_operations_dashboard(session)
    generated_at = operations["overview"]["generated_at"]
    manifest, backtests = build_migration_portfolio_backtest_artifacts(
        operations["portfolios"],
        generated_at=generated_at,
    )
    replay_artifacts = build_migration_replay_alignment_artifacts(operations["recommendation_replay"])
    bind = session.get_bind()
    artifact_root = artifact_root_from_database_url(bind.url.render_as_string(hide_password=False) if bind else None)
    write_manifest(manifest, root=artifact_root)
    for artifact in backtests:
        write_backtest_artifact(artifact, root=artifact_root)
    for artifact in replay_artifacts:
        write_replay_alignment_artifact(artifact, root=artifact_root)


def inject_market_data_stale_backfill(
    session: Session,
    symbol: str,
    *,
    stale_direction: str = "risk_alert",
    stale_summary: str = "滞后补跑版本不应覆盖同日正常 recommendation。",
) -> tuple[Recommendation, Recommendation]:
    recommendations = session.scalars(
        select(Recommendation)
        .join(Recommendation.stock)
        .where(Recommendation.stock.has(symbol=symbol))
        .order_by(Recommendation.as_of_data_time.desc(), Recommendation.generated_at.desc(), Recommendation.id.desc())
    ).all()
    if len(recommendations) < 2:
        raise ValueError(f"Not enough recommendations to inject a stale backfill for {symbol}.")

    fresh = recommendations[0]
    stale = recommendations[1]
    stale.as_of_data_time = fresh.as_of_data_time
    stale.generated_at = fresh.generated_at + timedelta(hours=58)
    stale.direction = stale_direction
    stale.summary = stale_summary
    payload = dict(stale.recommendation_payload or {})
    evidence = dict(payload.get("evidence") or {})
    degrade_flags = [str(item) for item in evidence.get("degrade_flags") or [] if item and str(item) != "market_data_stale"]
    degrade_flags.append("market_data_stale")
    evidence["degrade_flags"] = degrade_flags
    payload["evidence"] = evidence
    stale.recommendation_payload = payload
    session.flush()
    return fresh, stale
