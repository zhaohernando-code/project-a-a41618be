from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ashare_evidence.db import Base, utcnow
from ashare_evidence.lineage import LineageMixin


class TimestampedMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )


class Stock(TimestampedMixin, LineageMixin, Base):
    __tablename__ = "stocks"
    __table_args__ = (UniqueConstraint("symbol", name="uq_stock_symbol"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True)
    exchange: Mapped[str] = mapped_column(String(16), index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    listed_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    delisted_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    profile_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    sector_memberships: Mapped[list["SectorMembership"]] = relationship(back_populates="stock")
    market_bars: Mapped[list["MarketBar"]] = relationship(back_populates="stock")
    news_links: Mapped[list["NewsEntityLink"]] = relationship(back_populates="stock")
    feature_snapshots: Mapped[list["FeatureSnapshot"]] = relationship(back_populates="stock")
    model_results: Mapped[list["ModelResult"]] = relationship(back_populates="stock")
    recommendations: Mapped[list["Recommendation"]] = relationship(back_populates="stock")
    paper_orders: Mapped[list["PaperOrder"]] = relationship(back_populates="stock")
    paper_fills: Mapped[list["PaperFill"]] = relationship(back_populates="stock")


class Sector(TimestampedMixin, LineageMixin, Base):
    __tablename__ = "sectors"
    __table_args__ = (UniqueConstraint("sector_code", name="uq_sector_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sector_code: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    level: Mapped[str] = mapped_column(String(32), nullable=False)
    parent_sector_id: Mapped[int | None] = mapped_column(ForeignKey("sectors.id"), nullable=True)
    definition_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    parent_sector: Mapped["Sector | None"] = relationship(remote_side=[id])
    memberships: Mapped[list["SectorMembership"]] = relationship(back_populates="sector")
    news_links: Mapped[list["NewsEntityLink"]] = relationship(back_populates="sector")


class SectorMembership(TimestampedMixin, LineageMixin, Base):
    __tablename__ = "sector_memberships"
    __table_args__ = (
        UniqueConstraint("membership_key", name="uq_membership_key"),
        UniqueConstraint("stock_id", "sector_id", "effective_from", name="uq_sector_membership_effective"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    membership_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False, index=True)
    sector_id: Mapped[int] = mapped_column(ForeignKey("sectors.id"), nullable=False, index=True)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_primary: Mapped[bool] = mapped_column(default=False, nullable=False)
    membership_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    stock: Mapped[Stock] = relationship(back_populates="sector_memberships")
    sector: Mapped[Sector] = relationship(back_populates="memberships")


class MarketBar(TimestampedMixin, LineageMixin, Base):
    __tablename__ = "market_bars"
    __table_args__ = (
        UniqueConstraint("bar_key", name="uq_bar_key"),
        UniqueConstraint("stock_id", "timeframe", "observed_at", name="uq_market_bar_observed"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bar_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    open_price: Mapped[float] = mapped_column(Float, nullable=False)
    high_price: Mapped[float] = mapped_column(Float, nullable=False)
    low_price: Mapped[float] = mapped_column(Float, nullable=False)
    close_price: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    turnover_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    adj_factor: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    stock: Mapped[Stock] = relationship(back_populates="market_bars")


class NewsItem(TimestampedMixin, LineageMixin, Base):
    __tablename__ = "news_items"
    __table_args__ = (
        UniqueConstraint("news_key", name="uq_news_key"),
        UniqueConstraint("provider_name", "external_id", name="uq_news_provider_external"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    news_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider_name: Mapped[str] = mapped_column(String(64), nullable=False)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    headline: Mapped[str] = mapped_column(String(512), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    content_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    event_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    entity_links: Mapped[list["NewsEntityLink"]] = relationship(back_populates="news_item")


class NewsEntityLink(TimestampedMixin, LineageMixin, Base):
    __tablename__ = "news_entity_links"
    __table_args__ = (
        UniqueConstraint("news_id", "entity_type", "stock_id", "sector_id", name="uq_news_entity_link"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    news_id: Mapped[int] = mapped_column(ForeignKey("news_items.id"), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(16), nullable=False)
    stock_id: Mapped[int | None] = mapped_column(ForeignKey("stocks.id"), nullable=True, index=True)
    sector_id: Mapped[int | None] = mapped_column(ForeignKey("sectors.id"), nullable=True, index=True)
    market_tag: Mapped[str | None] = mapped_column(String(32), nullable=True)
    relevance_score: Mapped[float] = mapped_column(Float, nullable=False)
    impact_direction: Mapped[str] = mapped_column(String(16), nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decay_half_life_hours: Mapped[float] = mapped_column(Float, nullable=False)
    mapping_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    news_item: Mapped[NewsItem] = relationship(back_populates="entity_links")
    stock: Mapped[Stock | None] = relationship(back_populates="news_links")
    sector: Mapped[Sector | None] = relationship(back_populates="news_links")


class FeatureSnapshot(TimestampedMixin, LineageMixin, Base):
    __tablename__ = "feature_snapshots"
    __table_args__ = (
        UniqueConstraint("snapshot_key", name="uq_snapshot_key"),
        UniqueConstraint("stock_id", "feature_set_name", "feature_set_version", "as_of", name="uq_feature_snapshot"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False, index=True)
    feature_set_name: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_set_version: Mapped[str] = mapped_column(String(64), nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    feature_values: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    upstream_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)

    stock: Mapped[Stock] = relationship(back_populates="feature_snapshots")


class ModelRegistry(TimestampedMixin, LineageMixin, Base):
    __tablename__ = "model_registries"
    __table_args__ = (UniqueConstraint("name", name="uq_model_registry_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    family: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    registry_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    versions: Mapped[list["ModelVersion"]] = relationship(back_populates="registry")


class ModelVersion(TimestampedMixin, LineageMixin, Base):
    __tablename__ = "model_versions"
    __table_args__ = (UniqueConstraint("registry_id", "version", name="uq_model_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    registry_id: Mapped[int] = mapped_column(ForeignKey("model_registries.id"), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    validation_scheme: Mapped[str] = mapped_column(String(128), nullable=False)
    training_window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    training_window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    artifact_uri: Mapped[str | None] = mapped_column(String(255), nullable=True)
    config_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    registry: Mapped[ModelRegistry] = relationship(back_populates="versions")
    runs: Mapped[list["ModelRun"]] = relationship(back_populates="model_version")
    recommendations: Mapped[list["Recommendation"]] = relationship(back_populates="model_version")


class PromptVersion(TimestampedMixin, LineageMixin, Base):
    __tablename__ = "prompt_versions"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_prompt_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    risk_disclaimer: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    recommendations: Mapped[list["Recommendation"]] = relationship(back_populates="prompt_version")


class ModelRun(TimestampedMixin, LineageMixin, Base):
    __tablename__ = "model_runs"
    __table_args__ = (UniqueConstraint("run_key", name="uq_model_run_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_version_id: Mapped[int] = mapped_column(ForeignKey("model_versions.id"), nullable=False, index=True)
    run_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    run_status: Mapped[str] = mapped_column(String(16), nullable=False)
    target_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    metrics_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    input_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)

    model_version: Mapped[ModelVersion] = relationship(back_populates="runs")
    results: Mapped[list["ModelResult"]] = relationship(back_populates="model_run")
    recommendations: Mapped[list["Recommendation"]] = relationship(back_populates="model_run")


class ModelResult(TimestampedMixin, LineageMixin, Base):
    __tablename__ = "model_results"
    __table_args__ = (
        UniqueConstraint("result_key", name="uq_model_result_key"),
        UniqueConstraint("model_run_id", "stock_id", "forecast_horizon_days", name="uq_model_result_run_stock_horizon"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    result_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    model_run_id: Mapped[int] = mapped_column(ForeignKey("model_runs.id"), nullable=False, index=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False, index=True)
    as_of_data_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    forecast_horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    predicted_direction: Mapped[str] = mapped_column(String(16), nullable=False)
    expected_return: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_bucket: Mapped[str] = mapped_column(String(16), nullable=False)
    driver_factors: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    risk_factors: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    result_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    model_run: Mapped[ModelRun] = relationship(back_populates="results")
    stock: Mapped[Stock] = relationship(back_populates="model_results")


class Recommendation(TimestampedMixin, LineageMixin, Base):
    __tablename__ = "recommendations"
    __table_args__ = (UniqueConstraint("recommendation_key", name="uq_recommendation_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recommendation_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False, index=True)
    model_version_id: Mapped[int] = mapped_column(ForeignKey("model_versions.id"), nullable=False, index=True)
    model_run_id: Mapped[int] = mapped_column(ForeignKey("model_runs.id"), nullable=False, index=True)
    prompt_version_id: Mapped[int] = mapped_column(ForeignKey("prompt_versions.id"), nullable=False, index=True)
    as_of_data_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_label: Mapped[str] = mapped_column(String(16), nullable=False)
    horizon_min_days: Mapped[int] = mapped_column(Integer, nullable=False)
    horizon_max_days: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_status: Mapped[str] = mapped_column(String(16), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    core_drivers: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    risk_flags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    degrade_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendation_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    stock: Mapped[Stock] = relationship(back_populates="recommendations")
    model_version: Mapped[ModelVersion] = relationship(back_populates="recommendations")
    model_run: Mapped[ModelRun] = relationship(back_populates="recommendations")
    prompt_version: Mapped[PromptVersion] = relationship(back_populates="recommendations")
    evidence_links: Mapped[list["RecommendationEvidence"]] = relationship(back_populates="recommendation")
    paper_orders: Mapped[list["PaperOrder"]] = relationship(back_populates="recommendation")


class RecommendationEvidence(TimestampedMixin, LineageMixin, Base):
    __tablename__ = "recommendation_evidence"
    __table_args__ = (
        UniqueConstraint("recommendation_id", "evidence_type", "evidence_id", "role", name="uq_recommendation_evidence"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recommendation_id: Mapped[int] = mapped_column(ForeignKey("recommendations.id"), nullable=False, index=True)
    evidence_type: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_id: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_label: Mapped[str] = mapped_column(String(255), nullable=False)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    recommendation: Mapped[Recommendation] = relationship(back_populates="evidence_links")


class PaperPortfolio(TimestampedMixin, LineageMixin, Base):
    __tablename__ = "paper_portfolios"
    __table_args__ = (UniqueConstraint("portfolio_key", name="uq_paper_portfolio_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    portfolio_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    benchmark_symbol: Mapped[str | None] = mapped_column(String(32), nullable=True)
    base_currency: Mapped[str] = mapped_column(String(8), default="CNY", nullable=False)
    cash_balance: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    portfolio_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    orders: Mapped[list["PaperOrder"]] = relationship(back_populates="portfolio")


class PaperOrder(TimestampedMixin, LineageMixin, Base):
    __tablename__ = "paper_orders"
    __table_args__ = (UniqueConstraint("order_key", name="uq_paper_order_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("paper_portfolios.id"), nullable=False, index=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False, index=True)
    recommendation_id: Mapped[int | None] = mapped_column(ForeignKey("recommendations.id"), nullable=True, index=True)
    order_source: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    order_type: Mapped[str] = mapped_column(String(16), nullable=False)
    limit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    order_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    portfolio: Mapped[PaperPortfolio] = relationship(back_populates="orders")
    stock: Mapped[Stock] = relationship(back_populates="paper_orders")
    recommendation: Mapped[Recommendation | None] = relationship(back_populates="paper_orders")
    fills: Mapped[list["PaperFill"]] = relationship(back_populates="order")


class PaperFill(TimestampedMixin, LineageMixin, Base):
    __tablename__ = "paper_fills"
    __table_args__ = (UniqueConstraint("fill_key", name="uq_paper_fill_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fill_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("paper_orders.id"), nullable=False, index=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False, index=True)
    filled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    fee: Mapped[float] = mapped_column(Float, nullable=False)
    tax: Mapped[float] = mapped_column(Float, nullable=False)
    slippage_bps: Mapped[float] = mapped_column(Float, nullable=False)
    fill_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    order: Mapped[PaperOrder] = relationship(back_populates="fills")
    stock: Mapped[Stock] = relationship(back_populates="paper_fills")


class IngestionRun(TimestampedMixin, LineageMixin, Base):
    __tablename__ = "ingestion_runs"
    __table_args__ = (UniqueConstraint("run_key", name="uq_ingestion_run_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    provider_name: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_name: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    params_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class WatchlistEntry(TimestampedMixin, LineageMixin, Base):
    __tablename__ = "watchlist_entries"
    __table_args__ = (UniqueConstraint("symbol", name="uq_watchlist_entry_symbol"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    exchange: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False, index=True)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    analysis_status: Mapped[str] = mapped_column(String(16), default="ready", nullable=False)
    last_analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    watchlist_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class AppSetting(TimestampedMixin, Base):
    __tablename__ = "app_settings"
    __table_args__ = (UniqueConstraint("setting_key", name="uq_app_setting_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    setting_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    setting_value: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class ProviderCredential(TimestampedMixin, Base):
    __tablename__ = "provider_credentials"
    __table_args__ = (UniqueConstraint("provider_name", name="uq_provider_credential_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_name: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class ModelApiKey(TimestampedMixin, Base):
    __tablename__ = "model_api_keys"
    __table_args__ = (UniqueConstraint("name", name="uq_model_api_key_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider_name: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    base_url: Mapped[str] = mapped_column(String(255), nullable=False)
    api_key: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    is_default: Mapped[bool] = mapped_column(default=False, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False, index=True)
    last_status: Mapped[str] = mapped_column(String(16), default="untested", nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
