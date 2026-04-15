from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import math
import random
from typing import Any

from ashare_evidence.providers import EvidenceBundle, with_lineage
from ashare_evidence.signal_engine import SignalArtifacts, build_signal_artifacts

UTC = timezone.utc
LATEST_TRADE_DAY = date(2026, 4, 14)
WATCHLIST_SYMBOLS = ("600519.SH", "300750.SZ", "601318.SH", "002594.SZ")
PREVIOUS_OFFSET = 5


@dataclass(frozen=True)
class SectorConfig:
    sector_code: str
    name: str
    level: str
    taxonomy: str
    is_primary: bool = False
    effective_from: date = date(2020, 1, 1)


@dataclass(frozen=True)
class ScenarioConfig:
    symbol: str
    ticker: str
    exchange: str
    name: str
    listed_date: date
    industry: str
    start_close: float
    base_volume: float
    volume_step: float
    volume_wave: float
    base_turnover_rate: float
    turnover_step: float
    late_volume_boost: float
    late_turnover_boost: float
    daily_returns: tuple[float, ...]
    sectors: tuple[SectorConfig, ...]
    news_events: tuple[dict[str, Any], ...]


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
    return datetime(trade_day.year, trade_day.month, trade_day.day, 7, 0, tzinfo=UTC)


SCENARIOS: dict[str, ScenarioConfig] = {
    "600519.SH": ScenarioConfig(
        symbol="600519.SH",
        ticker="600519",
        exchange="SSE",
        name="贵州茅台",
        listed_date=date(2001, 8, 27),
        industry="白酒",
        start_close=1598.0,
        base_volume=21400.0,
        volume_step=240.0,
        volume_wave=680.0,
        base_turnover_rate=0.175,
        turnover_step=0.0014,
        late_volume_boost=3200.0,
        late_turnover_boost=0.012,
        daily_returns=(
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
        ),
        sectors=(
            SectorConfig("sw-food-beverage", "食品饮料", "industry", "申万一级", is_primary=True),
            SectorConfig("concept-core-consumption", "核心消费", "concept", "概念板块"),
        ),
        news_events=(
            {
                "news_key": "news-600519-annual-report-20260409",
                "provider_name": "cninfo",
                "external_id": "cninfo-600519-20260409-annual",
                "headline": "贵州茅台披露年报，经营质量和现金流继续改善",
                "summary": "年报显示高端产品结构优化，经营现金流保持稳健增长。",
                "content_excerpt": "公告提到渠道库存总体可控，直营投放保持克制。",
                "published_at": datetime(2026, 4, 9, 12, 0, tzinfo=UTC),
                "event_scope": "stock",
                "dedupe_key": "600519-annual-report-2026",
                "raw_payload": {"provider": "巨潮资讯", "announcement_type": "annual_report"},
                "source_uri": "cninfo://announcements/600519/20260409-annual",
                "license_tag": "cninfo-public-disclosure",
                "links": (
                    {
                        "entity_type": "stock",
                        "stock_symbol": "600519.SH",
                        "sector_code": None,
                        "market_tag": None,
                        "relevance_score": 0.94,
                        "impact_direction": "positive",
                        "effective_at": datetime(2026, 4, 9, 12, 0, tzinfo=UTC),
                        "decay_half_life_hours": 120.0,
                        "mapping_payload": {"layer": "stock", "dedupe_stage": "post-entity-map"},
                    },
                ),
            },
            {
                "news_key": "news-600519-annual-report-repost-20260409",
                "provider_name": "sse",
                "external_id": "sse-600519-20260409-annual-repost",
                "headline": "贵州茅台年报摘要转载：渠道库存平稳，直营效率继续优化",
                "summary": "交易所公告摘要重述年报要点，与主公告属于同一事件。",
                "content_excerpt": "重点仍是渠道库存和现金流质量改善。",
                "published_at": datetime(2026, 4, 9, 14, 30, tzinfo=UTC),
                "event_scope": "stock",
                "dedupe_key": "600519-annual-report-2026",
                "raw_payload": {"provider": "上交所", "announcement_type": "annual_report_summary"},
                "source_uri": "sse://announcements/600519/20260409-annual-summary",
                "license_tag": "exchange-public-disclosure",
                "links": (
                    {
                        "entity_type": "stock",
                        "stock_symbol": "600519.SH",
                        "sector_code": None,
                        "market_tag": None,
                        "relevance_score": 0.76,
                        "impact_direction": "positive",
                        "effective_at": datetime(2026, 4, 9, 14, 30, tzinfo=UTC),
                        "decay_half_life_hours": 120.0,
                        "mapping_payload": {"layer": "stock", "dedupe_stage": "pre-dedup"},
                    },
                ),
            },
            {
                "news_key": "news-600519-liquor-tax-20260411",
                "provider_name": "cninfo",
                "external_id": "cninfo-600519-20260411-liquor-tax",
                "headline": "消费税讨论升温，白酒板块短线情绪承压",
                "summary": "市场对消费税方向存在讨论，行业层面风险偏好短线回落。",
                "content_excerpt": "目前仍处于讨论阶段，但容易触发行业估值波动。",
                "published_at": datetime(2026, 4, 11, 3, 0, tzinfo=UTC),
                "event_scope": "sector",
                "dedupe_key": "liquor-tax-discussion-2026",
                "raw_payload": {"provider": "巨潮资讯", "announcement_type": "sector_news"},
                "source_uri": "cninfo://news/liquor-tax-discussion-20260411",
                "license_tag": "cninfo-public-disclosure",
                "links": (
                    {
                        "entity_type": "sector",
                        "stock_symbol": None,
                        "sector_code": "sw-food-beverage",
                        "market_tag": None,
                        "relevance_score": 0.52,
                        "impact_direction": "negative",
                        "effective_at": datetime(2026, 4, 11, 3, 0, tzinfo=UTC),
                        "decay_half_life_hours": 36.0,
                        "mapping_payload": {"layer": "sector", "dedupe_stage": "post-entity-map"},
                    },
                ),
            },
            {
                "news_key": "news-600519-channel-update-20260413",
                "provider_name": "cninfo",
                "external_id": "cninfo-600519-20260413-channel",
                "headline": "渠道跟踪显示节前动销维持平稳，批价未见异常波动",
                "summary": "渠道反馈显示节前动销正常，价格体系整体稳定。",
                "content_excerpt": "渠道健康度改善，有助于压低市场对去库存的担忧。",
                "published_at": datetime(2026, 4, 13, 11, 0, tzinfo=UTC),
                "event_scope": "stock",
                "dedupe_key": "600519-channel-check-20260413",
                "raw_payload": {"provider": "巨潮资讯", "announcement_type": "channel_update"},
                "source_uri": "cninfo://news/600519/20260413-channel-check",
                "license_tag": "cninfo-public-disclosure",
                "links": (
                    {
                        "entity_type": "stock",
                        "stock_symbol": "600519.SH",
                        "sector_code": None,
                        "market_tag": None,
                        "relevance_score": 0.84,
                        "impact_direction": "positive",
                        "effective_at": datetime(2026, 4, 13, 11, 0, tzinfo=UTC),
                        "decay_half_life_hours": 72.0,
                        "mapping_payload": {"layer": "stock", "dedupe_stage": "post-entity-map"},
                    },
                ),
            },
            {
                "news_key": "news-600519-roadshow-20260414",
                "provider_name": "cninfo",
                "external_id": "cninfo-600519-20260414-roadshow",
                "headline": "机构调研聚焦五一前动销与高端白酒提价节奏",
                "summary": "调研纪要显示市场更关注动销兑现和供需平衡延续。",
                "content_excerpt": "管理层强调渠道健康优先于短期放量，维持中长期品牌力建设。",
                "published_at": datetime(2026, 4, 14, 5, 30, tzinfo=UTC),
                "event_scope": "stock",
                "dedupe_key": "600519-roadshow-20260414",
                "raw_payload": {"provider": "巨潮资讯", "announcement_type": "investor_relation"},
                "source_uri": "cninfo://announcements/600519/20260414-roadshow",
                "license_tag": "cninfo-public-disclosure",
                "links": (
                    {
                        "entity_type": "stock",
                        "stock_symbol": "600519.SH",
                        "sector_code": None,
                        "market_tag": None,
                        "relevance_score": 0.88,
                        "impact_direction": "positive",
                        "effective_at": datetime(2026, 4, 14, 5, 30, tzinfo=UTC),
                        "decay_half_life_hours": 72.0,
                        "mapping_payload": {"layer": "stock", "dedupe_stage": "post-entity-map"},
                    },
                    {
                        "entity_type": "sector",
                        "stock_symbol": None,
                        "sector_code": "sw-food-beverage",
                        "market_tag": None,
                        "relevance_score": 0.61,
                        "impact_direction": "positive",
                        "effective_at": datetime(2026, 4, 14, 5, 30, tzinfo=UTC),
                        "decay_half_life_hours": 48.0,
                        "mapping_payload": {"layer": "sector", "dedupe_stage": "post-entity-map"},
                    },
                ),
            },
        ),
    ),
    "300750.SZ": ScenarioConfig(
        symbol="300750.SZ",
        ticker="300750",
        exchange="SZSE",
        name="宁德时代",
        listed_date=date(2018, 6, 11),
        industry="锂电池",
        start_close=212.0,
        base_volume=158000.0,
        volume_step=1600.0,
        volume_wave=5300.0,
        base_turnover_rate=0.92,
        turnover_step=0.006,
        late_volume_boost=26000.0,
        late_turnover_boost=0.08,
        daily_returns=(
            -0.0080,
            0.0120,
            0.0090,
            -0.0040,
            0.0070,
            0.0060,
            0.0050,
            -0.0060,
            0.0040,
            0.0090,
            -0.0110,
            0.0070,
            0.0060,
            -0.0050,
            0.0080,
            0.0040,
            -0.0060,
            0.0070,
            0.0100,
            -0.0040,
            0.0060,
            -0.0080,
            0.0050,
            0.0040,
            -0.0030,
            0.0060,
            -0.0020,
            0.0040,
        ),
        sectors=(
            SectorConfig("sw-power-equipment", "电力设备", "industry", "申万一级", is_primary=True),
            SectorConfig("concept-energy-storage", "储能", "concept", "概念板块"),
        ),
        news_events=(
            {
                "news_key": "news-300750-order-20260408",
                "provider_name": "cninfo",
                "external_id": "cninfo-300750-20260408-order",
                "headline": "宁德时代披露储能大单，海外项目进入交付阶段",
                "summary": "新增储能订单延续高景气，市场关注海外交付节奏。",
                "content_excerpt": "项目订单可见度提升，但兑现节奏仍需后续跟踪。",
                "published_at": datetime(2026, 4, 8, 8, 45, tzinfo=UTC),
                "event_scope": "stock",
                "dedupe_key": "300750-energy-storage-order-20260408",
                "raw_payload": {"provider": "巨潮资讯", "announcement_type": "major_contract"},
                "source_uri": "cninfo://announcements/300750/20260408-order",
                "license_tag": "cninfo-public-disclosure",
                "links": (
                    {
                        "entity_type": "stock",
                        "stock_symbol": "300750.SZ",
                        "sector_code": None,
                        "market_tag": None,
                        "relevance_score": 0.83,
                        "impact_direction": "positive",
                        "effective_at": datetime(2026, 4, 8, 8, 45, tzinfo=UTC),
                        "decay_half_life_hours": 96.0,
                        "mapping_payload": {"layer": "stock", "dedupe_stage": "post-entity-map"},
                    },
                ),
            },
            {
                "news_key": "news-300750-europe-policy-20260410",
                "provider_name": "cninfo",
                "external_id": "cninfo-300750-20260410-policy",
                "headline": "欧洲新能源政策审查升温，电池出口链短线承压",
                "summary": "海外政策预期扰动加大，出口链情绪有所降温。",
                "content_excerpt": "当前仍是政策讨论阶段，但会压制板块风险偏好。",
                "published_at": datetime(2026, 4, 10, 6, 20, tzinfo=UTC),
                "event_scope": "sector",
                "dedupe_key": "battery-export-policy-discussion-20260410",
                "raw_payload": {"provider": "巨潮资讯", "announcement_type": "sector_news"},
                "source_uri": "cninfo://news/battery-export-policy-20260410",
                "license_tag": "cninfo-public-disclosure",
                "links": (
                    {
                        "entity_type": "sector",
                        "stock_symbol": None,
                        "sector_code": "sw-power-equipment",
                        "market_tag": None,
                        "relevance_score": 0.68,
                        "impact_direction": "negative",
                        "effective_at": datetime(2026, 4, 10, 6, 20, tzinfo=UTC),
                        "decay_half_life_hours": 48.0,
                        "mapping_payload": {"layer": "sector", "dedupe_stage": "post-entity-map"},
                    },
                ),
            },
            {
                "news_key": "news-300750-margin-20260412",
                "provider_name": "cninfo",
                "external_id": "cninfo-300750-20260412-margin",
                "headline": "调研纪要显示动力电池盈利改善，但整车价格战仍在传导",
                "summary": "盈利端改善与下游价格竞争并存，市场对持续性仍有分歧。",
                "content_excerpt": "机构更关注利润弹性而非单月出货数据。",
                "published_at": datetime(2026, 4, 12, 10, 0, tzinfo=UTC),
                "event_scope": "stock",
                "dedupe_key": "300750-margin-roadshow-20260412",
                "raw_payload": {"provider": "巨潮资讯", "announcement_type": "investor_relation"},
                "source_uri": "cninfo://announcements/300750/20260412-roadshow",
                "license_tag": "cninfo-public-disclosure",
                "links": (
                    {
                        "entity_type": "stock",
                        "stock_symbol": "300750.SZ",
                        "sector_code": None,
                        "market_tag": None,
                        "relevance_score": 0.74,
                        "impact_direction": "positive",
                        "effective_at": datetime(2026, 4, 12, 10, 0, tzinfo=UTC),
                        "decay_half_life_hours": 60.0,
                        "mapping_payload": {"layer": "stock", "dedupe_stage": "post-entity-map"},
                    },
                    {
                        "entity_type": "sector",
                        "stock_symbol": None,
                        "sector_code": "sw-power-equipment",
                        "market_tag": None,
                        "relevance_score": 0.41,
                        "impact_direction": "negative",
                        "effective_at": datetime(2026, 4, 12, 10, 0, tzinfo=UTC),
                        "decay_half_life_hours": 36.0,
                        "mapping_payload": {"layer": "sector", "dedupe_stage": "post-entity-map"},
                    },
                ),
            },
            {
                "news_key": "news-300750-capex-20260414",
                "provider_name": "cninfo",
                "external_id": "cninfo-300750-20260414-capex",
                "headline": "宁德时代更新产能规划，储能和海外业务仍是主抓手",
                "summary": "最新投资者沟通强调高毛利储能业务和海外客户放量。",
                "content_excerpt": "管理层强调扩产节奏更趋审慎，避免低效资本开支。",
                "published_at": datetime(2026, 4, 14, 4, 40, tzinfo=UTC),
                "event_scope": "stock",
                "dedupe_key": "300750-capex-update-20260414",
                "raw_payload": {"provider": "巨潮资讯", "announcement_type": "investor_relation"},
                "source_uri": "cninfo://announcements/300750/20260414-capex",
                "license_tag": "cninfo-public-disclosure",
                "links": (
                    {
                        "entity_type": "stock",
                        "stock_symbol": "300750.SZ",
                        "sector_code": None,
                        "market_tag": None,
                        "relevance_score": 0.79,
                        "impact_direction": "positive",
                        "effective_at": datetime(2026, 4, 14, 4, 40, tzinfo=UTC),
                        "decay_half_life_hours": 72.0,
                        "mapping_payload": {"layer": "stock", "dedupe_stage": "post-entity-map"},
                    },
                ),
            },
        ),
    ),
    "601318.SH": ScenarioConfig(
        symbol="601318.SH",
        ticker="601318",
        exchange="SSE",
        name="中国平安",
        listed_date=date(2007, 3, 1),
        industry="保险",
        start_close=52.2,
        base_volume=366000.0,
        volume_step=2200.0,
        volume_wave=9200.0,
        base_turnover_rate=0.31,
        turnover_step=0.0021,
        late_volume_boost=18000.0,
        late_turnover_boost=0.018,
        daily_returns=(
            0.0020,
            0.0010,
            0.0000,
            -0.0010,
            0.0020,
            0.0030,
            -0.0020,
            0.0010,
            0.0020,
            0.0010,
            -0.0010,
            0.0020,
            0.0010,
            0.0000,
            0.0020,
            -0.0010,
            0.0010,
            0.0020,
            0.0010,
            -0.0020,
            0.0010,
            0.0020,
            0.0000,
            0.0010,
            0.0020,
            -0.0010,
            0.0010,
            0.0020,
        ),
        sectors=(
            SectorConfig("sw-nonbank-finance", "非银金融", "industry", "申万一级", is_primary=True),
            SectorConfig("concept-high-dividend", "高股息", "concept", "概念板块"),
        ),
        news_events=(
            {
                "news_key": "news-601318-dividend-20260409",
                "provider_name": "cninfo",
                "external_id": "cninfo-601318-20260409-dividend",
                "headline": "中国平安披露分红方案，高股息属性继续强化",
                "summary": "公司维持稳定分红预期，吸引中长期配置资金。",
                "content_excerpt": "管理层强调分红政策稳定和资本充足水平安全。",
                "published_at": datetime(2026, 4, 9, 9, 20, tzinfo=UTC),
                "event_scope": "stock",
                "dedupe_key": "601318-dividend-plan-20260409",
                "raw_payload": {"provider": "巨潮资讯", "announcement_type": "profit_distribution"},
                "source_uri": "cninfo://announcements/601318/20260409-dividend",
                "license_tag": "cninfo-public-disclosure",
                "links": (
                    {
                        "entity_type": "stock",
                        "stock_symbol": "601318.SH",
                        "sector_code": None,
                        "market_tag": None,
                        "relevance_score": 0.77,
                        "impact_direction": "positive",
                        "effective_at": datetime(2026, 4, 9, 9, 20, tzinfo=UTC),
                        "decay_half_life_hours": 120.0,
                        "mapping_payload": {"layer": "stock", "dedupe_stage": "post-entity-map"},
                    },
                ),
            },
            {
                "news_key": "news-601318-rate-cut-20260411",
                "provider_name": "cninfo",
                "external_id": "cninfo-601318-20260411-rate-cut",
                "headline": "市场讨论利率下行对保险投资收益率的扰动",
                "summary": "低利率环境仍会影响保险资金收益预期。",
                "content_excerpt": "情绪层面偏谨慎，但目前尚无增量负面披露。",
                "published_at": datetime(2026, 4, 11, 7, 15, tzinfo=UTC),
                "event_scope": "sector",
                "dedupe_key": "insurance-rate-cut-discussion-20260411",
                "raw_payload": {"provider": "巨潮资讯", "announcement_type": "sector_news"},
                "source_uri": "cninfo://news/insurance-rate-cut-20260411",
                "license_tag": "cninfo-public-disclosure",
                "links": (
                    {
                        "entity_type": "sector",
                        "stock_symbol": None,
                        "sector_code": "sw-nonbank-finance",
                        "market_tag": None,
                        "relevance_score": 0.49,
                        "impact_direction": "negative",
                        "effective_at": datetime(2026, 4, 11, 7, 15, tzinfo=UTC),
                        "decay_half_life_hours": 60.0,
                        "mapping_payload": {"layer": "sector", "dedupe_stage": "post-entity-map"},
                    },
                ),
            },
            {
                "news_key": "news-601318-channel-20260414",
                "provider_name": "cninfo",
                "external_id": "cninfo-601318-20260414-channel",
                "headline": "渠道跟踪显示保险代理人活动回暖，新业务价值改善预期升温",
                "summary": "渠道数据改善强化了新业务价值修复预期。",
                "content_excerpt": "最新渠道反馈显示优质代理人留存率稳定改善。",
                "published_at": datetime(2026, 4, 14, 3, 50, tzinfo=UTC),
                "event_scope": "stock",
                "dedupe_key": "601318-channel-update-20260414",
                "raw_payload": {"provider": "巨潮资讯", "announcement_type": "channel_update"},
                "source_uri": "cninfo://news/601318/20260414-channel-update",
                "license_tag": "cninfo-public-disclosure",
                "links": (
                    {
                        "entity_type": "stock",
                        "stock_symbol": "601318.SH",
                        "sector_code": None,
                        "market_tag": None,
                        "relevance_score": 0.72,
                        "impact_direction": "positive",
                        "effective_at": datetime(2026, 4, 14, 3, 50, tzinfo=UTC),
                        "decay_half_life_hours": 84.0,
                        "mapping_payload": {"layer": "stock", "dedupe_stage": "post-entity-map"},
                    },
                ),
            },
        ),
    ),
    "002594.SZ": ScenarioConfig(
        symbol="002594.SZ",
        ticker="002594",
        exchange="SZSE",
        name="比亚迪",
        listed_date=date(2011, 6, 30),
        industry="汽车整车",
        start_close=312.0,
        base_volume=222000.0,
        volume_step=2600.0,
        volume_wave=7200.0,
        base_turnover_rate=0.74,
        turnover_step=0.0055,
        late_volume_boost=12000.0,
        late_turnover_boost=0.02,
        daily_returns=(
            -0.0060,
            -0.0040,
            0.0020,
            -0.0080,
            -0.0050,
            -0.0030,
            -0.0070,
            0.0010,
            -0.0060,
            -0.0040,
            -0.0090,
            0.0030,
            -0.0060,
            -0.0050,
            -0.0040,
            -0.0070,
            0.0020,
            -0.0060,
            -0.0050,
            -0.0040,
            -0.0060,
            -0.0030,
            -0.0050,
            0.0010,
            -0.0070,
            -0.0040,
            -0.0060,
            -0.0050,
        ),
        sectors=(
            SectorConfig("sw-auto", "汽车", "industry", "申万一级", is_primary=True),
            SectorConfig("concept-new-energy-vehicle", "新能源车", "concept", "概念板块"),
        ),
        news_events=(
            {
                "news_key": "news-002594-price-war-20260409",
                "provider_name": "cninfo",
                "external_id": "cninfo-002594-20260409-price-war",
                "headline": "车市价格竞争再度加剧，整车板块盈利预期承压",
                "summary": "市场对整车价格战持续时间和盈利修复路径转谨慎。",
                "content_excerpt": "行业层面价格竞争仍在扩散，短线压制估值修复。",
                "published_at": datetime(2026, 4, 9, 6, 30, tzinfo=UTC),
                "event_scope": "sector",
                "dedupe_key": "auto-price-war-20260409",
                "raw_payload": {"provider": "巨潮资讯", "announcement_type": "sector_news"},
                "source_uri": "cninfo://news/auto-price-war-20260409",
                "license_tag": "cninfo-public-disclosure",
                "links": (
                    {
                        "entity_type": "sector",
                        "stock_symbol": None,
                        "sector_code": "sw-auto",
                        "market_tag": None,
                        "relevance_score": 0.83,
                        "impact_direction": "negative",
                        "effective_at": datetime(2026, 4, 9, 6, 30, tzinfo=UTC),
                        "decay_half_life_hours": 72.0,
                        "mapping_payload": {"layer": "sector", "dedupe_stage": "post-entity-map"},
                    },
                ),
            },
            {
                "news_key": "news-002594-sales-20260411",
                "provider_name": "cninfo",
                "external_id": "cninfo-002594-20260411-sales",
                "headline": "比亚迪披露月销数据，销量仍高但市场更关注单车盈利",
                "summary": "销量数据稳健，但资金更担心价格竞争下的利润弹性。",
                "content_excerpt": "销量并未明显转弱，但盈利预期仍在下修。",
                "published_at": datetime(2026, 4, 11, 9, 5, tzinfo=UTC),
                "event_scope": "stock",
                "dedupe_key": "002594-sales-update-20260411",
                "raw_payload": {"provider": "巨潮资讯", "announcement_type": "monthly_sales"},
                "source_uri": "cninfo://announcements/002594/20260411-sales",
                "license_tag": "cninfo-public-disclosure",
                "links": (
                    {
                        "entity_type": "stock",
                        "stock_symbol": "002594.SZ",
                        "sector_code": None,
                        "market_tag": None,
                        "relevance_score": 0.56,
                        "impact_direction": "positive",
                        "effective_at": datetime(2026, 4, 11, 9, 5, tzinfo=UTC),
                        "decay_half_life_hours": 48.0,
                        "mapping_payload": {"layer": "stock", "dedupe_stage": "post-entity-map"},
                    },
                ),
            },
            {
                "news_key": "news-002594-export-20260413",
                "provider_name": "cninfo",
                "external_id": "cninfo-002594-20260413-export",
                "headline": "出口市场监管扰动加大，新能源车链估值再受压制",
                "summary": "外部监管和贸易摩擦预期升温，板块情绪进一步转弱。",
                "content_excerpt": "海外渠道不确定性加大，情绪面明显弱于销量数据。",
                "published_at": datetime(2026, 4, 13, 5, 10, tzinfo=UTC),
                "event_scope": "sector",
                "dedupe_key": "nev-export-regulation-20260413",
                "raw_payload": {"provider": "巨潮资讯", "announcement_type": "sector_news"},
                "source_uri": "cninfo://news/nev-export-regulation-20260413",
                "license_tag": "cninfo-public-disclosure",
                "links": (
                    {
                        "entity_type": "sector",
                        "stock_symbol": None,
                        "sector_code": "sw-auto",
                        "market_tag": None,
                        "relevance_score": 0.74,
                        "impact_direction": "negative",
                        "effective_at": datetime(2026, 4, 13, 5, 10, tzinfo=UTC),
                        "decay_half_life_hours": 60.0,
                        "mapping_payload": {"layer": "sector", "dedupe_stage": "post-entity-map"},
                    },
                ),
            },
        ),
    ),
}

KNOWN_STOCK_NAMES = {
    symbol: config.name
    for symbol, config in SCENARIOS.items()
}

SECTOR_TEMPLATES: tuple[dict[str, str], ...] = (
    {
        "industry": "高端消费",
        "primary_sector_code": "sw-food-beverage",
        "primary_sector_name": "食品饮料",
        "secondary_sector_code": "concept-brand-consumption",
        "secondary_sector_name": "品牌消费",
        "positive_topic": "渠道动销与现金回款继续改善",
        "negative_topic": "终端动销恢复节奏仍需验证",
        "sector_positive_topic": "内需复苏预期回暖",
        "sector_negative_topic": "税费与渠道库存讨论升温",
    },
    {
        "industry": "新能源设备",
        "primary_sector_code": "sw-electric-equipment",
        "primary_sector_name": "电力设备",
        "secondary_sector_code": "concept-energy-storage",
        "secondary_sector_name": "储能",
        "positive_topic": "新签订单与排产节奏同步改善",
        "negative_topic": "价格竞争和去库存压力仍在",
        "sector_positive_topic": "新能源链补库预期回升",
        "sector_negative_topic": "产业链价格下修压力扩大",
    },
    {
        "industry": "保险金融",
        "primary_sector_code": "sw-non-bank-finance",
        "primary_sector_name": "非银金融",
        "secondary_sector_code": "concept-dividend-assets",
        "secondary_sector_name": "高股息资产",
        "positive_topic": "负债成本改善与权益弹性同步修复",
        "negative_topic": "权益波动和新单恢复仍需观察",
        "sector_positive_topic": "低利率环境下高股息偏好抬升",
        "sector_negative_topic": "利差与权益波动压制估值修复",
    },
    {
        "industry": "半导体",
        "primary_sector_code": "sw-electronics",
        "primary_sector_name": "电子",
        "secondary_sector_code": "concept-semiconductor",
        "secondary_sector_name": "半导体",
        "positive_topic": "客户拉货和产能利用率继续回升",
        "negative_topic": "验证进度与价格压力仍有反复",
        "sector_positive_topic": "国产替代与景气改善继续演绎",
        "sector_negative_topic": "终端需求反复压制估值修复",
    },
    {
        "industry": "创新药",
        "primary_sector_code": "sw-pharmaceutical-biological",
        "primary_sector_name": "医药生物",
        "secondary_sector_code": "concept-innovative-drug",
        "secondary_sector_name": "创新药",
        "positive_topic": "核心产品放量与临床进展形成共振",
        "negative_topic": "研发节奏与医保谈判仍存不确定性",
        "sector_positive_topic": "创新药情绪修复与海外授权预期升温",
        "sector_negative_topic": "集采与研发兑现节奏引发分歧",
    },
)


def _symbol_seed(symbol: str) -> int:
    return int(sha256(symbol.encode("utf-8")).hexdigest()[:8], 16)


def _infer_market_suffix(ticker: str) -> str:
    if ticker[0] in {"5", "6", "9"}:
        return "SH"
    if ticker[0] in {"0", "2", "3"}:
        return "SZ"
    if ticker[0] in {"4", "8"}:
        return "BJ"
    raise ValueError("暂不支持该证券代码。请输入 6 位 A 股代码。")


def normalize_symbol(symbol: str) -> str:
    raw = symbol.strip().upper().replace(" ", "")
    if not raw:
        raise ValueError("请输入股票代码。")
    if raw.startswith(("SH", "SZ", "BJ")) and len(raw) == 8 and raw[2:].isdigit():
        raw = f"{raw[2:]}.{raw[:2]}"
    if "." not in raw:
        if not raw.isdigit() or len(raw) != 6:
            raise ValueError("股票代码格式无效，请输入如 600519 或 300750.SZ。")
        return f"{raw}.{_infer_market_suffix(raw)}"
    ticker, _, suffix = raw.partition(".")
    if not ticker.isdigit() or len(ticker) != 6:
        raise ValueError("股票代码格式无效，请输入 6 位数字代码。")
    if suffix not in {"SH", "SZ", "BJ"}:
        raise ValueError("股票代码后缀仅支持 .SH / .SZ / .BJ。")
    return f"{ticker}.{suffix}"


def _exchange_name(suffix: str) -> str:
    return {
        "SH": "SSE",
        "SZ": "SZSE",
        "BJ": "BSE",
    }[suffix]


def _generate_dynamic_returns(seed: int, tier: int) -> tuple[float, ...]:
    rng = random.Random(seed)
    phase = rng.uniform(0.25, math.pi)
    base_drift = {
        0: 0.0034,
        1: 0.0012,
        2: -0.0007,
        3: -0.0030,
    }[tier]
    late_bias = {
        0: 0.0022,
        1: 0.0004,
        2: -0.0018,
        3: -0.0027,
    }[tier]
    volatility = {
        0: 0.0016,
        1: 0.0021,
        2: 0.0026,
        3: 0.0032,
    }[tier]
    daily_returns: list[float] = []
    for index in range(28):
        cycle = math.sin(index / 3.15 + phase) * volatility * 0.55
        noise = rng.uniform(-volatility, volatility)
        value = base_drift + cycle + noise
        if index >= 23:
            value += late_bias
        if tier == 1 and index in {6, 13, 20}:
            value -= 0.0025
        if tier == 2 and index >= 20:
            value -= 0.0012
        if tier == 3 and index in {9, 17, 25}:
            value -= 0.0042
        daily_returns.append(round(max(min(value, 0.085), -0.085), 4))
    return tuple(daily_returns)


def _dynamic_start_close(ticker: str, seed: int) -> float:
    if ticker.startswith("688"):
        return round(42 + (seed % 1400) / 10, 2)
    if ticker.startswith("300"):
        return round(26 + (seed % 900) / 10, 2)
    if ticker.startswith(("600", "601", "603", "605")):
        return round(10 + (seed % 700) / 10, 2)
    if ticker.startswith(("000", "001", "002")):
        return round(8 + (seed % 620) / 10, 2)
    return round(12 + (seed % 680) / 10, 2)


def _dynamic_sector_configs(template: dict[str, str], seed: int) -> tuple[SectorConfig, ...]:
    concept_effective_year = 2020 + seed % 5
    return (
        SectorConfig(
            template["primary_sector_code"],
            template["primary_sector_name"],
            "industry",
            "申万一级",
            is_primary=True,
        ),
        SectorConfig(
            template["secondary_sector_code"],
            template["secondary_sector_name"],
            "concept",
            "概念板块",
            effective_from=date(concept_effective_year, 1, 1),
        ),
    )


def _news_timestamp(days_before_latest: int, hour: int, minute: int) -> datetime:
    return datetime(
        LATEST_TRADE_DAY.year,
        LATEST_TRADE_DAY.month,
        LATEST_TRADE_DAY.day,
        hour,
        minute,
        tzinfo=UTC,
    ) - timedelta(days=days_before_latest)


def _dynamic_news_events(
    *,
    symbol: str,
    stock_name: str,
    template: dict[str, str],
    tier: int,
) -> tuple[dict[str, Any], ...]:
    ticker = symbol.split(".", 1)[0]
    stock_direction = "positive" if tier in {0, 1} else "negative"
    sector_direction = "positive" if tier == 0 else "negative"
    latest_direction = "positive" if tier in {0, 1} else "negative"
    stock_topic = template["positive_topic"] if stock_direction == "positive" else template["negative_topic"]
    sector_topic = template["sector_positive_topic"] if sector_direction == "positive" else template["sector_negative_topic"]
    latest_topic = template["positive_topic"] if latest_direction == "positive" else template["negative_topic"]
    return (
        {
            "news_key": f"news-{ticker}-ops-{LATEST_TRADE_DAY:%Y%m%d}",
            "provider_name": "cninfo",
            "external_id": f"cninfo-{ticker}-{LATEST_TRADE_DAY:%Y%m%d}-ops",
            "headline": f"{stock_name}披露经营更新，{stock_topic}",
            "summary": f"公司层面最新经营信息显示，{stock_topic}。",
            "content_excerpt": f"系统将该事件映射为个股层证据，重点关注 {stock_name} 的经营节奏。",
            "published_at": _news_timestamp(5, 9, 20),
            "event_scope": "stock",
            "dedupe_key": f"{ticker}-ops-update-{LATEST_TRADE_DAY:%Y%m%d}",
            "raw_payload": {"provider": "巨潮资讯", "announcement_type": "operating_update"},
            "source_uri": f"cninfo://announcements/{ticker}/{LATEST_TRADE_DAY:%Y%m%d}-ops",
            "license_tag": "cninfo-public-disclosure",
            "links": (
                {
                    "entity_type": "stock",
                    "stock_symbol": symbol,
                    "sector_code": None,
                    "market_tag": None,
                    "relevance_score": 0.86,
                    "impact_direction": stock_direction,
                    "effective_at": _news_timestamp(5, 9, 20),
                    "decay_half_life_hours": 96.0,
                    "mapping_payload": {"layer": "stock", "dedupe_stage": "post-entity-map"},
                },
            ),
        },
        {
            "news_key": f"news-{ticker}-ops-repost-{LATEST_TRADE_DAY:%Y%m%d}",
            "provider_name": "exchange",
            "external_id": f"exchange-{ticker}-{LATEST_TRADE_DAY:%Y%m%d}-ops-repost",
            "headline": f"{stock_name}经营更新摘要转载：{stock_topic}",
            "summary": "交易所摘要重述经营更新要点，属于同一事件的重复传播。",
            "content_excerpt": "用于验证新闻事件去重是否生效。",
            "published_at": _news_timestamp(5, 13, 40),
            "event_scope": "stock",
            "dedupe_key": f"{ticker}-ops-update-{LATEST_TRADE_DAY:%Y%m%d}",
            "raw_payload": {"provider": "交易所披露", "announcement_type": "operating_update_summary"},
            "source_uri": f"exchange://announcements/{ticker}/{LATEST_TRADE_DAY:%Y%m%d}-ops-summary",
            "license_tag": "exchange-public-disclosure",
            "links": (
                {
                    "entity_type": "stock",
                    "stock_symbol": symbol,
                    "sector_code": None,
                    "market_tag": None,
                    "relevance_score": 0.71,
                    "impact_direction": stock_direction,
                    "effective_at": _news_timestamp(5, 13, 40),
                    "decay_half_life_hours": 96.0,
                    "mapping_payload": {"layer": "stock", "dedupe_stage": "pre-dedup"},
                },
            ),
        },
        {
            "news_key": f"news-{ticker}-sector-{LATEST_TRADE_DAY:%Y%m%d}",
            "provider_name": "cninfo",
            "external_id": f"cninfo-{ticker}-{LATEST_TRADE_DAY:%Y%m%d}-sector",
            "headline": f"{template['primary_sector_name']}板块跟踪：{sector_topic}",
            "summary": f"行业层面最新跟踪显示，{sector_topic}。",
            "content_excerpt": "系统会把行业事件按有效期衰减并映射回个股。",
            "published_at": _news_timestamp(3, 10, 10),
            "event_scope": "sector",
            "dedupe_key": f"{template['primary_sector_code']}-sector-{LATEST_TRADE_DAY:%Y%m%d}",
            "raw_payload": {"provider": "巨潮资讯", "announcement_type": "sector_news"},
            "source_uri": f"cninfo://news/{template['primary_sector_code']}/{LATEST_TRADE_DAY:%Y%m%d}-sector",
            "license_tag": "cninfo-public-disclosure",
            "links": (
                {
                    "entity_type": "sector",
                    "stock_symbol": None,
                    "sector_code": template["primary_sector_code"],
                    "market_tag": None,
                    "relevance_score": 0.63,
                    "impact_direction": sector_direction,
                    "effective_at": _news_timestamp(3, 10, 10),
                    "decay_half_life_hours": 48.0,
                    "mapping_payload": {"layer": "sector", "dedupe_stage": "post-entity-map"},
                },
            ),
        },
        {
            "news_key": f"news-{ticker}-roadshow-{LATEST_TRADE_DAY:%Y%m%d}",
            "provider_name": "cninfo",
            "external_id": f"cninfo-{ticker}-{LATEST_TRADE_DAY:%Y%m%d}-roadshow",
            "headline": f"机构调研聚焦{stock_name}，{latest_topic}",
            "summary": f"最新调研纪要显示，市场关注点集中在 {latest_topic}。",
            "content_excerpt": "该事件用于解释最新一版建议相较上一版为何变化。",
            "published_at": _news_timestamp(0, 11, 5),
            "event_scope": "stock",
            "dedupe_key": f"{ticker}-roadshow-{LATEST_TRADE_DAY:%Y%m%d}",
            "raw_payload": {"provider": "巨潮资讯", "announcement_type": "investor_relation"},
            "source_uri": f"cninfo://announcements/{ticker}/{LATEST_TRADE_DAY:%Y%m%d}-roadshow",
            "license_tag": "cninfo-public-disclosure",
            "links": (
                {
                    "entity_type": "stock",
                    "stock_symbol": symbol,
                    "sector_code": None,
                    "market_tag": None,
                    "relevance_score": 0.88,
                    "impact_direction": latest_direction,
                    "effective_at": _news_timestamp(0, 11, 5),
                    "decay_half_life_hours": 72.0,
                    "mapping_payload": {"layer": "stock", "dedupe_stage": "post-entity-map"},
                },
                {
                    "entity_type": "sector",
                    "stock_symbol": None,
                    "sector_code": template["primary_sector_code"],
                    "market_tag": None,
                    "relevance_score": 0.52,
                    "impact_direction": latest_direction,
                    "effective_at": _news_timestamp(0, 11, 5),
                    "decay_half_life_hours": 48.0,
                    "mapping_payload": {"layer": "sector", "dedupe_stage": "post-entity-map"},
                },
            ),
        },
    )


def build_dynamic_scenario(symbol: str, *, stock_name: str | None = None) -> ScenarioConfig:
    normalized_symbol = normalize_symbol(symbol)
    if normalized_symbol in SCENARIOS:
        return SCENARIOS[normalized_symbol]

    ticker, _, suffix = normalized_symbol.partition(".")
    seed = _symbol_seed(normalized_symbol)
    template = SECTOR_TEMPLATES[seed % len(SECTOR_TEMPLATES)]
    tier = (seed // len(SECTOR_TEMPLATES)) % 4
    listed_year = 2004 + seed % 18
    listed_month = 1 + (seed // 17) % 12
    listed_day = 1 + (seed // 37) % 27
    exchange = _exchange_name(suffix)
    name = stock_name.strip() if stock_name and stock_name.strip() else KNOWN_STOCK_NAMES.get(normalized_symbol, f"自选标的 {ticker}")
    return ScenarioConfig(
        symbol=normalized_symbol,
        ticker=ticker,
        exchange=exchange,
        name=name,
        listed_date=date(listed_year, listed_month, listed_day),
        industry=template["industry"],
        start_close=_dynamic_start_close(ticker, seed),
        base_volume=round(9800 + seed % 22000, 2),
        volume_step=round(110 + seed % 260, 2),
        volume_wave=round(280 + seed % 900, 2),
        base_turnover_rate=round(0.038 + (seed % 80) / 1000, 4),
        turnover_step=round(0.0007 + (seed % 25) / 10000, 4),
        late_volume_boost=round(1400 + seed % 6200, 2),
        late_turnover_boost=round(0.004 + (seed % 25) / 1000, 4),
        daily_returns=_generate_dynamic_returns(seed, tier),
        sectors=_dynamic_sector_configs(template, seed),
        news_events=_dynamic_news_events(
            symbol=normalized_symbol,
            stock_name=name,
            template=template,
            tier=tier,
        ),
    )


def resolve_scenario(symbol: str, *, stock_name: str | None = None) -> ScenarioConfig:
    normalized_symbol = normalize_symbol(symbol)
    if normalized_symbol in SCENARIOS:
        return SCENARIOS[normalized_symbol]
    return build_dynamic_scenario(normalized_symbol, stock_name=stock_name)


def _stock_record(config: ScenarioConfig) -> dict[str, Any]:
    return with_lineage(
        {
            "symbol": config.symbol,
            "ticker": config.ticker,
            "exchange": config.exchange,
            "name": config.name,
            "provider_symbol": config.symbol,
            "listed_date": config.listed_date,
            "status": "active",
            "profile_payload": {
                "industry": config.industry,
                "watchlist_scope": "一期自选股池",
                "provider": "Tushare Pro",
            },
        },
        payload_key="profile_payload",
        source_uri=f"tushare://stock_basic/{config.symbol}",
        license_tag="tushare-pro",
        redistribution_scope="limited-display",
    )


def _sector_records(config: ScenarioConfig) -> list[dict[str, Any]]:
    return [
        with_lineage(
            {
                "sector_code": sector.sector_code,
                "name": sector.name,
                "level": sector.level,
                "definition_payload": {"taxonomy": sector.taxonomy, "provider": "Tushare Pro"},
            },
            payload_key="definition_payload",
            source_uri=f"tushare://taxonomy/{sector.sector_code}",
            license_tag="tushare-pro",
            redistribution_scope="limited-display",
        )
        for sector in config.sectors
    ]


def _membership_records(config: ScenarioConfig) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for sector in config.sectors:
        records.append(
            with_lineage(
                {
                    "membership_key": f"membership-{config.ticker}-{sector.sector_code}",
                    "stock_symbol": config.symbol,
                    "sector_code": sector.sector_code,
                    "effective_from": datetime(
                        sector.effective_from.year,
                        sector.effective_from.month,
                        sector.effective_from.day,
                        tzinfo=UTC,
                    ),
                    "effective_to": None,
                    "is_primary": sector.is_primary,
                    "membership_payload": {"taxonomy": sector.taxonomy, "weighting_hint": "primary" if sector.is_primary else "theme"},
                },
                payload_key="membership_payload",
                source_uri=f"tushare://membership/{config.symbol}/{sector.sector_code}",
                license_tag="tushare-pro",
                redistribution_scope="limited-display",
            )
        )
    return records


def _market_bars(config: ScenarioConfig) -> list[dict[str, Any]]:
    trade_days = _business_days(LATEST_TRADE_DAY, len(config.daily_returns))
    previous_close = config.start_close
    bars: list[dict[str, Any]] = []
    for idx, trade_day in enumerate(trade_days):
        daily_return = config.daily_returns[idx]
        observed_at = _bar_timestamp(trade_day)
        close_price = round(previous_close * (1 + daily_return), 2)
        open_price = round(previous_close * (1 + daily_return * 0.35), 2)
        spread = 0.006 + (idx % 4) * 0.001
        high_price = round(max(open_price, close_price) * (1 + spread), 2)
        low_price = round(min(open_price, close_price) * (1 - spread * 0.82), 2)
        volume = round(
            config.base_volume
            + idx * config.volume_step
            + ((idx % 5) - 2) * config.volume_wave
            + (config.late_volume_boost if idx >= len(trade_days) - 5 else 0.0),
            2,
        )
        turnover_rate = round(
            config.base_turnover_rate
            + idx * config.turnover_step
            + (config.late_turnover_boost if idx >= len(trade_days) - 5 else 0.0),
            4,
        )
        amount = round(close_price * volume * 100, 2)
        bars.append(
            with_lineage(
                {
                    "bar_key": f"bar-{config.ticker.lower()}-{trade_day:%Y%m%d}",
                    "stock_symbol": config.symbol,
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
                source_uri=f"tushare://daily/{config.symbol}?trade_date={trade_day:%Y%m%d}",
                license_tag="tushare-pro",
                redistribution_scope="limited-display",
            )
        )
        previous_close = close_price
    return bars


def _news_records(config: ScenarioConfig) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    items: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    for event in config.news_events:
        item = with_lineage(
            {
                "news_key": event["news_key"],
                "provider_name": event["provider_name"],
                "external_id": event["external_id"],
                "headline": event["headline"],
                "summary": event["summary"],
                "content_excerpt": event["content_excerpt"],
                "published_at": event["published_at"],
                "event_scope": event["event_scope"],
                "dedupe_key": event["dedupe_key"],
                "raw_payload": event["raw_payload"],
            },
            payload_key="raw_payload",
            source_uri=event["source_uri"],
            license_tag=event["license_tag"],
            redistribution_scope=event.get("redistribution_scope", "source-link-only"),
        )
        items.append(item)
        for index, link in enumerate(event["links"]):
            links.append(
                with_lineage(
                    {
                        "news_key": event["news_key"],
                        "entity_type": link["entity_type"],
                        "stock_symbol": link.get("stock_symbol"),
                        "sector_code": link.get("sector_code"),
                        "market_tag": link.get("market_tag"),
                        "relevance_score": link["relevance_score"],
                        "impact_direction": link["impact_direction"],
                        "effective_at": link["effective_at"],
                        "decay_half_life_hours": link["decay_half_life_hours"],
                        "mapping_payload": link["mapping_payload"],
                    },
                    payload_key="mapping_payload",
                    source_uri=f"pipeline://news-link/{event['news_key']}/{index}",
                    license_tag="internal-derived",
                )
            )
    return items, links


def _simulation_artifacts(
    *,
    config: ScenarioConfig,
    market_bars: list[dict[str, Any]],
    generated_at: datetime,
    recommendation_key: str,
    latest_close: float,
    direction: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    symbol_token = config.ticker.lower()
    trade_token = generated_at.strftime("%Y%m%d")
    side = "buy" if direction == "buy" else "sell"
    limit_price = round(latest_close * (1.001 if direction == "buy" else 0.998), 2)
    market_fill = round(latest_close * (1.002 if direction == "buy" else 0.997), 2)
    manual_quantity = 100 if latest_close >= 100 else 500
    auto_quantity = manual_quantity * 2
    seed_bar = market_bars[-11] if len(market_bars) >= 11 else market_bars[0]
    seed_at = seed_bar["observed_at"]
    seed_token = seed_at.strftime("%Y%m%d")
    seed_limit = round(float(seed_bar["close_price"]) * 1.001, 2)
    seed_manual_quantity = 100 if float(seed_bar["close_price"]) >= 100 else 300
    seed_auto_quantity = seed_manual_quantity * 2

    paper_portfolios = [
        with_lineage(
            {
                "portfolio_key": "portfolio-manual-sandbox",
                "name": "手动模拟仓",
                "mode": "manual",
                "benchmark_symbol": "000300.SH",
                "base_currency": "CNY",
                "cash_balance": 900000.0,
                "status": "active",
                "portfolio_payload": {
                    "purpose": "manual-paper-trade",
                    "starting_cash": 900000.0,
                    "separation_policy": "independent-ledger",
                },
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
                "cash_balance": 1800000.0,
                "status": "active",
                "portfolio_payload": {
                    "purpose": "auto-model-portfolio",
                    "starting_cash": 1800000.0,
                    "separation_policy": "independent-ledger",
                },
            },
            payload_key="portfolio_payload",
            source_uri="simulation://portfolio/auto-wave",
            license_tag="internal-derived",
        ),
    ]
    paper_orders = [
        with_lineage(
            {
                "order_key": f"order-manual-seed-{symbol_token}-{seed_token}",
                "portfolio_key": "portfolio-manual-sandbox",
                "stock_symbol": config.symbol,
                "recommendation_key": None,
                "order_source": "manual",
                "side": "buy",
                "requested_at": seed_at,
                "quantity": seed_manual_quantity,
                "order_type": "limit",
                "limit_price": seed_limit,
                "status": "filled",
                "notes": "历史种子仓位，用于组合收益和回撤计算。",
                "order_payload": {"execution_mode": "manual", "intent": "historical_seed"},
            },
            payload_key="order_payload",
            source_uri=f"simulation://order/manual/seed/{symbol_token}/{seed_token}",
            license_tag="internal-derived",
        ),
        with_lineage(
            {
                "order_key": f"order-auto-seed-{symbol_token}-{seed_token}",
                "portfolio_key": "portfolio-auto-wave",
                "stock_symbol": config.symbol,
                "recommendation_key": None,
                "order_source": "model",
                "side": "buy",
                "requested_at": seed_at,
                "quantity": seed_auto_quantity,
                "order_type": "market",
                "limit_price": None,
                "status": "filled",
                "notes": "模型组合历史种子仓位，用于验证自动持仓纪律。",
                "order_payload": {"execution_mode": "auto_model", "intent": "historical_seed"},
            },
            payload_key="order_payload",
            source_uri=f"simulation://order/auto/seed/{symbol_token}/{seed_token}",
            license_tag="internal-derived",
        ),
        with_lineage(
            {
                "order_key": f"order-manual-{symbol_token}-{trade_token}",
                "portfolio_key": "portfolio-manual-sandbox",
                "stock_symbol": config.symbol,
                "recommendation_key": recommendation_key,
                "order_source": "manual",
                "side": side,
                "requested_at": generated_at,
                "quantity": manual_quantity,
                "order_type": "limit",
                "limit_price": limit_price,
                "status": "filled",
                "notes": "研究员基于建议摘要手动下单。",
                "order_payload": {"execution_mode": "manual"},
            },
            payload_key="order_payload",
            source_uri=f"simulation://order/manual/{symbol_token}/{trade_token}",
            license_tag="internal-derived",
        ),
        with_lineage(
            {
                "order_key": f"order-auto-{symbol_token}-{trade_token}",
                "portfolio_key": "portfolio-auto-wave",
                "stock_symbol": config.symbol,
                "recommendation_key": recommendation_key,
                "order_source": "model",
                "side": side,
                "requested_at": generated_at,
                "quantity": auto_quantity,
                "order_type": "market",
                "limit_price": None,
                "status": "filled",
                "notes": "模型组合按目标权重自动调仓。",
                "order_payload": {"execution_mode": "auto_model"},
            },
            payload_key="order_payload",
            source_uri=f"simulation://order/auto/{symbol_token}/{trade_token}",
            license_tag="internal-derived",
        ),
    ]
    if direction not in {"buy", "reduce"}:
        paper_orders = paper_orders[:2]
    paper_fills = [
        with_lineage(
            {
                "fill_key": f"fill-manual-seed-{symbol_token}-{seed_token}",
                "order_key": f"order-manual-seed-{symbol_token}-{seed_token}",
                "stock_symbol": config.symbol,
                "filled_at": seed_at,
                "price": seed_limit,
                "quantity": seed_manual_quantity,
                "fee": round(seed_limit * seed_manual_quantity * 0.0005, 2),
                "tax": 0.0,
                "slippage_bps": 2.9,
                "fill_payload": {"matching_rule": "t+1-paper", "intent": "historical_seed"},
            },
            payload_key="fill_payload",
            source_uri=f"simulation://fill/manual/seed/{symbol_token}/{seed_token}",
            license_tag="internal-derived",
        ),
        with_lineage(
            {
                "fill_key": f"fill-auto-seed-{symbol_token}-{seed_token}",
                "order_key": f"order-auto-seed-{symbol_token}-{seed_token}",
                "stock_symbol": config.symbol,
                "filled_at": seed_at,
                "price": round(seed_limit * 1.001, 2),
                "quantity": seed_auto_quantity,
                "fee": round(seed_limit * 1.001 * seed_auto_quantity * 0.0005, 2),
                "tax": 0.0,
                "slippage_bps": 3.6,
                "fill_payload": {"matching_rule": "t+1-paper", "intent": "historical_seed"},
            },
            payload_key="fill_payload",
            source_uri=f"simulation://fill/auto/seed/{symbol_token}/{seed_token}",
            license_tag="internal-derived",
        ),
        with_lineage(
            {
                "fill_key": f"fill-manual-{symbol_token}-{trade_token}",
                "order_key": f"order-manual-{symbol_token}-{trade_token}",
                "stock_symbol": config.symbol,
                "filled_at": generated_at,
                "price": limit_price,
                "quantity": manual_quantity,
                "fee": round(limit_price * manual_quantity * 0.0005, 2),
                "tax": round(limit_price * manual_quantity * 0.001, 2) if direction == "reduce" else 0.0,
                "slippage_bps": 3.4,
                "fill_payload": {"matching_rule": "t+1-paper"},
            },
            payload_key="fill_payload",
            source_uri=f"simulation://fill/manual/{symbol_token}/{trade_token}",
            license_tag="internal-derived",
        ),
        with_lineage(
            {
                "fill_key": f"fill-auto-{symbol_token}-{trade_token}",
                "order_key": f"order-auto-{symbol_token}-{trade_token}",
                "stock_symbol": config.symbol,
                "filled_at": generated_at,
                "price": market_fill,
                "quantity": auto_quantity,
                "fee": round(market_fill * auto_quantity * 0.0005, 2),
                "tax": round(market_fill * auto_quantity * 0.001, 2) if direction == "reduce" else 0.0,
                "slippage_bps": 4.2,
                "fill_payload": {"matching_rule": "t+1-paper"},
            },
            payload_key="fill_payload",
            source_uri=f"simulation://fill/auto/{symbol_token}/{trade_token}",
            license_tag="internal-derived",
        ),
    ]
    if direction not in {"buy", "reduce"}:
        paper_fills = paper_fills[:2]
    return paper_portfolios, paper_orders, paper_fills


def _slice_inputs(
    *,
    config: ScenarioConfig,
    as_of_index: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    bars = _market_bars(config)[: as_of_index + 1]
    as_of_data_time = bars[-1]["observed_at"]
    news_items, news_links = _news_records(config)
    visible_news_keys = {
        item["news_key"]
        for item in news_items
        if item["published_at"] <= as_of_data_time
    }
    sliced_items = [item for item in news_items if item["news_key"] in visible_news_keys]
    sliced_links = [
        link
        for link in news_links
        if link["news_key"] in visible_news_keys and link["effective_at"] <= as_of_data_time
    ]
    return bars, sliced_items, sliced_links


def build_dashboard_bundle(symbol: str, *, snapshot: str = "latest", stock_name: str | None = None) -> EvidenceBundle:
    config = resolve_scenario(symbol, stock_name=stock_name)
    full_length = len(config.daily_returns)
    if snapshot == "latest":
        as_of_index = full_length - 1
    elif snapshot == "previous":
        as_of_index = full_length - 1 - PREVIOUS_OFFSET
    else:
        raise ValueError(f"Unsupported snapshot '{snapshot}'.")
    if as_of_index < 20:
        raise ValueError("Dashboard demo requires at least 21 market bars.")

    stock = _stock_record(config)
    sectors = _sector_records(config)
    sector_memberships = _membership_records(config)
    market_bars, news_items, news_links = _slice_inputs(config=config, as_of_index=as_of_index)
    generated_at = market_bars[-1]["observed_at"] + timedelta(hours=1, minutes=5)
    signal_artifacts: SignalArtifacts = build_signal_artifacts(
        symbol=config.symbol,
        stock_name=config.name,
        market_bars=market_bars,
        news_items=news_items,
        news_links=news_links,
        sector_memberships=sector_memberships,
        generated_at=generated_at,
    )
    paper_portfolios, paper_orders, paper_fills = _simulation_artifacts(
        config=config,
        market_bars=market_bars,
        generated_at=generated_at,
        recommendation_key=signal_artifacts.recommendation["recommendation_key"],
        latest_close=float(market_bars[-1]["close_price"]),
        direction=signal_artifacts.recommendation["direction"],
    )
    return EvidenceBundle(
        provider_name="dashboard-demo-route",
        symbol=config.symbol,
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


def build_dashboard_watchlist_bundles() -> list[EvidenceBundle]:
    bundles: list[EvidenceBundle] = []
    for symbol in WATCHLIST_SYMBOLS:
        bundles.append(build_dashboard_bundle(symbol, snapshot="previous"))
        bundles.append(build_dashboard_bundle(symbol, snapshot="latest"))
    return bundles
