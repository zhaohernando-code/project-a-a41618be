from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Protocol

from ashare_evidence.lineage import build_lineage
from ashare_evidence.signal_engine import SignalArtifacts, build_signal_artifacts


@dataclass(frozen=True)
class EvidenceBundle:
    provider_name: str
    symbol: str
    stock: dict[str, Any]
    sectors: list[dict[str, Any]]
    sector_memberships: list[dict[str, Any]]
    market_bars: list[dict[str, Any]]
    news_items: list[dict[str, Any]]
    news_links: list[dict[str, Any]]
    feature_snapshots: list[dict[str, Any]]
    model_registry: dict[str, Any]
    model_version: dict[str, Any]
    prompt_version: dict[str, Any]
    model_run: dict[str, Any]
    model_results: list[dict[str, Any]]
    recommendation: dict[str, Any]
    recommendation_evidence: list[dict[str, Any]]
    paper_portfolios: list[dict[str, Any]]
    paper_orders: list[dict[str, Any]]
    paper_fills: list[dict[str, Any]]


class EvidenceProvider(Protocol):
    provider_name: str

    def build_bundle(self, symbol: str) -> EvidenceBundle:
        ...


PLANNED_LOW_COST_ROUTE = {
    "market_and_master": "Tushare Pro",
    "news_and_disclosure": "巨潮资讯/交易所披露",
    "feature_and_model": "Qlib",
    "prototype_gap_fill": "AkShare",
    "upgrade_reserve": "商业行情/资讯授权接口通过同一适配层接入",
}


def with_lineage(
    record: dict[str, Any],
    *,
    payload_key: str,
    source_uri: str,
    license_tag: str,
    usage_scope: str = "internal_research",
    redistribution_scope: str = "none",
) -> dict[str, Any]:
    if payload_key not in record:
        raise KeyError(f"Expected payload key '{payload_key}' in record.")
    return {
        **record,
        **build_lineage(
            record,
            source_uri=source_uri,
            license_tag=license_tag,
            usage_scope=usage_scope,
            redistribution_scope=redistribution_scope,
        ),
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


def _bar_timestamp(trade_day: date, tz: timezone) -> datetime:
    return datetime(trade_day.year, trade_day.month, trade_day.day, 7, 0, tzinfo=tz)


def _build_demo_market_bars(symbol: str, tz: timezone) -> list[dict[str, Any]]:
    trade_days = _business_days(date(2026, 4, 14), 28)
    daily_returns = [
        -0.0040,
        0.0060,
        0.0030,
        -0.0015,
        0.0045,
        0.0035,
        0.0028,
        -0.0008,
        0.0020,
        0.0052,
        -0.0025,
        0.0040,
        0.0048,
        0.0018,
        0.0062,
        0.0012,
        -0.0010,
        0.0038,
        0.0055,
        0.0025,
        0.0046,
        0.0038,
        -0.0005,
        0.0055,
        0.0038,
        0.0048,
        0.0058,
        0.0065,
    ]

    previous_close = 1598.0
    market_bars: list[dict[str, Any]] = []
    for idx, trade_day in enumerate(trade_days):
        observed_at = _bar_timestamp(trade_day, tz)
        close_price = round(previous_close * (1 + daily_returns[idx]), 2)
        open_price = round(previous_close * (1 + daily_returns[idx] * 0.35), 2)
        spread = 0.0055 + (idx % 3) * 0.001
        high_price = round(max(open_price, close_price) * (1 + spread), 2)
        low_price = round(min(open_price, close_price) * (1 - spread * 0.8), 2)
        volume = round(21400 + idx * 240 + ((idx % 4) - 1.5) * 680 + (3200 if idx >= len(trade_days) - 5 else 0), 2)
        turnover_rate = round(0.175 + idx * 0.0014 + (0.012 if idx >= len(trade_days) - 5 else 0.0), 4)
        amount = round(close_price * volume * 100, 2)
        market_bars.append(
            with_lineage(
                {
                    "bar_key": f"bar-{symbol.replace('.', '').lower()}-{trade_day:%Y%m%d}",
                    "stock_symbol": symbol,
                    "timeframe": "1d",
                    "observed_at": observed_at,
                    "open_price": open_price,
                    "high_price": high_price,
                    "low_price": low_price,
                    "close_price": close_price,
                    "volume": volume,
                    "amount": amount,
                    "turnover_rate": turnover_rate,
                    "adj_factor": 1.0,
                    "raw_payload": {"trade_date": f"{trade_day:%Y%m%d}", "provider": "Tushare Pro"},
                },
                payload_key="raw_payload",
                source_uri=f"tushare://daily/{symbol}?trade_date={trade_day:%Y%m%d}",
                license_tag="tushare-pro",
                redistribution_scope="limited-display",
            )
        )
        previous_close = close_price
    return market_bars


def _build_demo_news_items(tz: timezone) -> list[dict[str, Any]]:
    return [
        with_lineage(
            {
                "news_key": "news-annual-report-20260409",
                "provider_name": "cninfo",
                "external_id": "cninfo-20260409-annual",
                "headline": "贵州茅台披露年报，经营质量和现金流继续改善",
                "summary": "年报显示高端产品结构优化，经营现金流保持稳健增长。",
                "content_excerpt": "公告提到渠道库存总体可控，直营投放保持克制。",
                "published_at": datetime(2026, 4, 9, 12, 0, tzinfo=tz),
                "event_scope": "stock",
                "dedupe_key": "600519-annual-report-2026",
                "raw_payload": {"provider": "巨潮资讯", "announcement_type": "annual_report"},
            },
            payload_key="raw_payload",
            source_uri="cninfo://announcements/600519/20260409-annual",
            license_tag="cninfo-public-disclosure",
            redistribution_scope="source-link-only",
        ),
        with_lineage(
            {
                "news_key": "news-annual-report-20260409-repost",
                "provider_name": "sse",
                "external_id": "sse-20260409-annual-repost",
                "headline": "贵州茅台年报摘要转载：渠道库存平稳，直营效率继续优化",
                "summary": "交易所公告摘要重述年报要点，与主公告属于同一事件。",
                "content_excerpt": "重点仍是渠道库存和现金流质量改善。",
                "published_at": datetime(2026, 4, 9, 14, 30, tzinfo=tz),
                "event_scope": "stock",
                "dedupe_key": "600519-annual-report-2026",
                "raw_payload": {"provider": "上交所", "announcement_type": "annual_report_summary"},
            },
            payload_key="raw_payload",
            source_uri="sse://announcements/600519/20260409-annual-summary",
            license_tag="exchange-public-disclosure",
            redistribution_scope="source-link-only",
        ),
        with_lineage(
            {
                "news_key": "news-industry-tax-20260411",
                "provider_name": "cninfo",
                "external_id": "cninfo-20260411-industry-tax",
                "headline": "消费税讨论升温，白酒板块短线情绪承压",
                "summary": "市场对消费税方向存在讨论，行业层面风险偏好短线回落。",
                "content_excerpt": "目前仍处于讨论阶段，但容易触发行业估值波动。",
                "published_at": datetime(2026, 4, 11, 3, 0, tzinfo=tz),
                "event_scope": "sector",
                "dedupe_key": "liquor-tax-discussion-2026",
                "raw_payload": {"provider": "巨潮资讯", "announcement_type": "sector_news"},
            },
            payload_key="raw_payload",
            source_uri="cninfo://news/liquor-tax-discussion-20260411",
            license_tag="cninfo-public-disclosure",
            redistribution_scope="source-link-only",
        ),
        with_lineage(
            {
                "news_key": "news-channel-update-20260413",
                "provider_name": "cninfo",
                "external_id": "cninfo-20260413-channel",
                "headline": "渠道跟踪显示节前动销维持平稳，批价未见异常波动",
                "summary": "渠道反馈显示节前动销正常，价格体系整体稳定。",
                "content_excerpt": "渠道健康度改善，有助于压低市场对去库存的担忧。",
                "published_at": datetime(2026, 4, 13, 11, 0, tzinfo=tz),
                "event_scope": "stock",
                "dedupe_key": "600519-channel-check-20260413",
                "raw_payload": {"provider": "巨潮资讯", "announcement_type": "channel_update"},
            },
            payload_key="raw_payload",
            source_uri="cninfo://news/600519/20260413-channel-check",
            license_tag="cninfo-public-disclosure",
            redistribution_scope="source-link-only",
        ),
        with_lineage(
            {
                "news_key": "news-roadshow-20260414",
                "provider_name": "cninfo",
                "external_id": "cninfo-20260414-roadshow",
                "headline": "机构调研聚焦五一前动销与高端白酒提价节奏",
                "summary": "调研纪要显示市场更关注动销兑现和供需平衡延续。",
                "content_excerpt": "管理层强调渠道健康优先于短期放量，维持中长期品牌力建设。",
                "published_at": datetime(2026, 4, 14, 5, 30, tzinfo=tz),
                "event_scope": "stock",
                "dedupe_key": "600519-roadshow-20260414",
                "raw_payload": {"provider": "巨潮资讯", "announcement_type": "investor_relation"},
            },
            payload_key="raw_payload",
            source_uri="cninfo://announcements/600519/20260414-roadshow",
            license_tag="cninfo-public-disclosure",
            redistribution_scope="source-link-only",
        ),
    ]


def _build_demo_news_links(symbol: str, tz: timezone) -> list[dict[str, Any]]:
    return [
        with_lineage(
            {
                "news_key": "news-annual-report-20260409",
                "entity_type": "stock",
                "stock_symbol": symbol,
                "sector_code": None,
                "market_tag": None,
                "relevance_score": 0.94,
                "impact_direction": "positive",
                "effective_at": datetime(2026, 4, 9, 12, 0, tzinfo=tz),
                "decay_half_life_hours": 120.0,
                "mapping_payload": {"layer": "stock", "dedupe_stage": "post-entity-map"},
            },
            payload_key="mapping_payload",
            source_uri=f"pipeline://news-link/news-annual-report-20260409/stock/{symbol}",
            license_tag="internal-derived",
        ),
        with_lineage(
            {
                "news_key": "news-annual-report-20260409-repost",
                "entity_type": "stock",
                "stock_symbol": symbol,
                "sector_code": None,
                "market_tag": None,
                "relevance_score": 0.76,
                "impact_direction": "positive",
                "effective_at": datetime(2026, 4, 9, 14, 30, tzinfo=tz),
                "decay_half_life_hours": 120.0,
                "mapping_payload": {"layer": "stock", "dedupe_stage": "pre-dedup"},
            },
            payload_key="mapping_payload",
            source_uri=f"pipeline://news-link/news-annual-report-20260409-repost/stock/{symbol}",
            license_tag="internal-derived",
        ),
        with_lineage(
            {
                "news_key": "news-industry-tax-20260411",
                "entity_type": "sector",
                "stock_symbol": None,
                "sector_code": "sw-food-beverage",
                "market_tag": None,
                "relevance_score": 0.52,
                "impact_direction": "negative",
                "effective_at": datetime(2026, 4, 11, 3, 0, tzinfo=tz),
                "decay_half_life_hours": 36.0,
                "mapping_payload": {"layer": "sector", "dedupe_stage": "post-entity-map"},
            },
            payload_key="mapping_payload",
            source_uri="pipeline://news-link/news-industry-tax-20260411/sector/sw-food-beverage",
            license_tag="internal-derived",
        ),
        with_lineage(
            {
                "news_key": "news-channel-update-20260413",
                "entity_type": "stock",
                "stock_symbol": symbol,
                "sector_code": None,
                "market_tag": None,
                "relevance_score": 0.84,
                "impact_direction": "positive",
                "effective_at": datetime(2026, 4, 13, 11, 0, tzinfo=tz),
                "decay_half_life_hours": 72.0,
                "mapping_payload": {"layer": "stock", "dedupe_stage": "post-entity-map"},
            },
            payload_key="mapping_payload",
            source_uri=f"pipeline://news-link/news-channel-update-20260413/stock/{symbol}",
            license_tag="internal-derived",
        ),
        with_lineage(
            {
                "news_key": "news-roadshow-20260414",
                "entity_type": "stock",
                "stock_symbol": symbol,
                "sector_code": None,
                "market_tag": None,
                "relevance_score": 0.88,
                "impact_direction": "positive",
                "effective_at": datetime(2026, 4, 14, 5, 30, tzinfo=tz),
                "decay_half_life_hours": 72.0,
                "mapping_payload": {"layer": "stock", "dedupe_stage": "post-entity-map"},
            },
            payload_key="mapping_payload",
            source_uri=f"pipeline://news-link/news-roadshow-20260414/stock/{symbol}",
            license_tag="internal-derived",
        ),
        with_lineage(
            {
                "news_key": "news-roadshow-20260414",
                "entity_type": "sector",
                "stock_symbol": None,
                "sector_code": "sw-food-beverage",
                "market_tag": None,
                "relevance_score": 0.61,
                "impact_direction": "positive",
                "effective_at": datetime(2026, 4, 14, 5, 30, tzinfo=tz),
                "decay_half_life_hours": 48.0,
                "mapping_payload": {"layer": "sector", "dedupe_stage": "post-entity-map"},
            },
            payload_key="mapping_payload",
            source_uri="pipeline://news-link/news-roadshow-20260414/sector/sw-food-beverage",
            license_tag="internal-derived",
        ),
    ]


def _build_demo_simulation_artifacts(
    *,
    symbol: str,
    generated_at: datetime,
    recommendation_key: str,
    latest_close: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    paper_portfolios = [
        with_lineage(
            {
                "portfolio_key": "portfolio-manual-sandbox",
                "name": "手动模拟仓",
                "mode": "manual",
                "benchmark_symbol": "000300.SH",
                "base_currency": "CNY",
                "cash_balance": 500000.0,
                "status": "active",
                "portfolio_payload": {"purpose": "manual-paper-trade"},
            },
            payload_key="portfolio_payload",
            source_uri="simulation://portfolio/manual-sandbox",
            license_tag="internal-derived",
        ),
        with_lineage(
            {
                "portfolio_key": "portfolio-auto-wave",
                "name": "模型自动持仓模拟仓",
                "mode": "auto_model",
                "benchmark_symbol": "000300.SH",
                "base_currency": "CNY",
                "cash_balance": 800000.0,
                "status": "active",
                "portfolio_payload": {"purpose": "auto-model-portfolio"},
            },
            payload_key="portfolio_payload",
            source_uri="simulation://portfolio/auto-wave",
            license_tag="internal-derived",
        ),
    ]

    manual_limit = round(latest_close * 1.001, 2)
    auto_fill = round(latest_close * 1.002, 2)
    paper_orders = [
        with_lineage(
            {
                "order_key": "order-manual-600519-20260414",
                "portfolio_key": "portfolio-manual-sandbox",
                "stock_symbol": symbol,
                "recommendation_key": recommendation_key,
                "order_source": "manual",
                "side": "buy",
                "requested_at": generated_at,
                "quantity": 100,
                "order_type": "limit",
                "limit_price": manual_limit,
                "status": "filled",
                "notes": "研究员手动跟随建议建仓。",
                "order_payload": {"execution_mode": "manual"},
            },
            payload_key="order_payload",
            source_uri="simulation://order/manual/600519/20260414",
            license_tag="internal-derived",
        ),
        with_lineage(
            {
                "order_key": "order-auto-600519-20260414",
                "portfolio_key": "portfolio-auto-wave",
                "stock_symbol": symbol,
                "recommendation_key": recommendation_key,
                "order_source": "model",
                "side": "buy",
                "requested_at": generated_at,
                "quantity": 200,
                "order_type": "market",
                "limit_price": None,
                "status": "filled",
                "notes": "模型组合按目标权重自动调仓。",
                "order_payload": {"execution_mode": "auto_model"},
            },
            payload_key="order_payload",
            source_uri="simulation://order/auto/600519/20260414",
            license_tag="internal-derived",
        ),
    ]
    paper_fills = [
        with_lineage(
            {
                "fill_key": "fill-manual-600519-20260414",
                "order_key": "order-manual-600519-20260414",
                "stock_symbol": symbol,
                "filled_at": generated_at,
                "price": manual_limit,
                "quantity": 100,
                "fee": round(manual_limit * 100 * 0.0005, 2),
                "tax": 0.0,
                "slippage_bps": 3.2,
                "fill_payload": {"matching_rule": "t+1-paper"},
            },
            payload_key="fill_payload",
            source_uri="simulation://fill/manual/600519/20260414",
            license_tag="internal-derived",
        ),
        with_lineage(
            {
                "fill_key": "fill-auto-600519-20260414",
                "order_key": "order-auto-600519-20260414",
                "stock_symbol": symbol,
                "filled_at": generated_at,
                "price": auto_fill,
                "quantity": 200,
                "fee": round(auto_fill * 200 * 0.0005, 2),
                "tax": 0.0,
                "slippage_bps": 4.1,
                "fill_payload": {"matching_rule": "t+1-paper"},
            },
            payload_key="fill_payload",
            source_uri="simulation://fill/auto/600519/20260414",
            license_tag="internal-derived",
        ),
    ]
    return paper_portfolios, paper_orders, paper_fills


class DemoLowCostRouteProvider:
    provider_name = "demo-low-cost-route"

    def build_bundle(self, symbol: str = "600519.SH") -> EvidenceBundle:
        if symbol != "600519.SH":
            raise ValueError("Demo provider currently only seeds 600519.SH.")

        tz = timezone.utc
        stock = with_lineage(
            {
                "symbol": symbol,
                "ticker": "600519",
                "exchange": "SSE",
                "name": "贵州茅台",
                "provider_symbol": symbol,
                "listed_date": date(2001, 8, 27),
                "status": "active",
                "profile_payload": {
                    "industry": "白酒",
                    "watchlist_scope": "一期自选股池",
                    "provider": "Tushare Pro",
                },
            },
            payload_key="profile_payload",
            source_uri=f"tushare://stock_basic/{symbol}",
            license_tag="tushare-pro",
            redistribution_scope="limited-display",
        )

        sectors = [
            with_lineage(
                {
                    "sector_code": "sw-food-beverage",
                    "name": "食品饮料",
                    "level": "industry",
                    "definition_payload": {"taxonomy": "申万一级", "provider": "Tushare Pro"},
                },
                payload_key="definition_payload",
                source_uri="tushare://index_member/sw-food-beverage",
                license_tag="tushare-pro",
                redistribution_scope="limited-display",
            ),
            with_lineage(
                {
                    "sector_code": "concept-core-consumption",
                    "name": "核心消费",
                    "level": "concept",
                    "definition_payload": {"taxonomy": "概念板块", "provider": "Tushare Pro"},
                },
                payload_key="definition_payload",
                source_uri="tushare://concept/core-consumption",
                license_tag="tushare-pro",
                redistribution_scope="limited-display",
            ),
        ]

        sector_memberships = [
            with_lineage(
                {
                    "membership_key": "membership-600519-sw-food-beverage",
                    "stock_symbol": symbol,
                    "sector_code": "sw-food-beverage",
                    "effective_from": datetime(2020, 1, 1, tzinfo=tz),
                    "effective_to": None,
                    "is_primary": True,
                    "membership_payload": {"weighting_hint": "primary-industry"},
                },
                payload_key="membership_payload",
                source_uri=f"tushare://index_member/{symbol}/sw-food-beverage",
                license_tag="tushare-pro",
                redistribution_scope="limited-display",
            ),
            with_lineage(
                {
                    "membership_key": "membership-600519-core-consumption",
                    "stock_symbol": symbol,
                    "sector_code": "concept-core-consumption",
                    "effective_from": datetime(2023, 1, 1, tzinfo=tz),
                    "effective_to": None,
                    "is_primary": False,
                    "membership_payload": {"weighting_hint": "theme"},
                },
                payload_key="membership_payload",
                source_uri=f"tushare://concept_member/{symbol}/core-consumption",
                license_tag="tushare-pro",
                redistribution_scope="limited-display",
            ),
        ]

        market_bars = _build_demo_market_bars(symbol, tz)
        news_items = _build_demo_news_items(tz)
        news_links = _build_demo_news_links(symbol, tz)

        generated_at = market_bars[-1]["observed_at"] + timedelta(hours=1, minutes=5)
        signal_artifacts: SignalArtifacts = build_signal_artifacts(
            symbol=symbol,
            stock_name=stock["name"],
            market_bars=market_bars,
            news_items=news_items,
            news_links=news_links,
            sector_memberships=sector_memberships,
            generated_at=generated_at,
        )
        paper_portfolios, paper_orders, paper_fills = _build_demo_simulation_artifacts(
            symbol=symbol,
            generated_at=generated_at,
            recommendation_key=signal_artifacts.recommendation["recommendation_key"],
            latest_close=float(market_bars[-1]["close_price"]),
        )

        return EvidenceBundle(
            provider_name=self.provider_name,
            symbol=symbol,
            stock=stock,
            sectors=sectors,
            sector_memberships=sector_memberships,
            market_bars=market_bars,
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
        )
