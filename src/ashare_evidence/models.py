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
    total_mv: Mapped[float | None] = mapped_column(Float, nullable=True)
    circ_mv: Mapped[float | None] = mapped_column(Float, nullable=True)
    pe_ttm: Mapped[float | None] = mapped_column(Float, nullable=True)
    pb: Mapped[float | None] = mapped_column(Float, nullable=True)
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


class ManualResearchRequest(TimestampedMixin, Base):
    __tablename__ = "manual_research_requests"
    __table_args__ = (UniqueConstraint("request_key", name="uq_manual_research_request_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    recommendation_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    trigger_source: Mapped[str] = mapped_column(String(32), nullable=False)
    executor_kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    model_api_key_id: Mapped[int | None] = mapped_column(ForeignKey("model_api_keys.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    artifact_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    superseded_by_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("manual_research_requests.id"),
        nullable=True,
        index=True,
    )
    stale_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_packet_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    validation_artifact_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    validation_manifest_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    model_api_key: Mapped["ModelApiKey | None"] = relationship(back_populates="manual_research_requests")
    superseded_by: Mapped["ManualResearchRequest | None"] = relationship(remote_side=[id])


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
    owner_login: Mapped[str] = mapped_column(String(128), nullable=False, default="root", index=True)
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
    owner_login: Mapped[str] = mapped_column(String(128), nullable=False, default="root", index=True)
    actor_login: Mapped[str] = mapped_column(String(128), nullable=False, default="root", index=True)
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
    owner_login: Mapped[str] = mapped_column(String(128), nullable=False, default="root", index=True)
    actor_login: Mapped[str] = mapped_column(String(128), nullable=False, default="root", index=True)
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


class AccountSpace(TimestampedMixin, Base):
    __tablename__ = "account_spaces"

    account_login: Mapped[str] = mapped_column(String(128), primary_key=True)
    role_snapshot: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_acted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_root: Mapped[bool] = mapped_column(default=False, nullable=False)
    metadata_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class WatchlistFollow(TimestampedMixin, Base):
    __tablename__ = "watchlist_follows"
    __table_args__ = (UniqueConstraint("account_login", "symbol", name="uq_watchlist_follow_account_symbol"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_login: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False, index=True)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_actor_login: Mapped[str] = mapped_column(String(128), nullable=False, default="root", index=True)
    follow_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


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

    manual_research_requests: Mapped[list[ManualResearchRequest]] = relationship(back_populates="model_api_key")


class ShortpickExperimentRun(TimestampedMixin, Base):
    __tablename__ = "shortpick_experiment_runs"
    __table_args__ = (UniqueConstraint("run_key", name="uq_shortpick_experiment_run_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    run_date: Mapped[date] = mapped_column(Date(), nullable=False, index=True)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    information_mode: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    trigger_source: Mapped[str] = mapped_column(String(64), nullable=False)
    triggered_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    model_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    summary_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class ShortpickModelRound(TimestampedMixin, Base):
    __tablename__ = "shortpick_model_rounds"
    __table_args__ = (
        UniqueConstraint("round_key", name="uq_shortpick_model_round_key"),
        UniqueConstraint("run_id", "provider_name", "model_name", "round_index", name="uq_shortpick_round_run_model_index"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("shortpick_experiment_runs.id"), nullable=False, index=True)
    round_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    provider_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    executor_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    round_index: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    raw_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    sources_payload: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    artifact_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ShortpickCandidate(TimestampedMixin, Base):
    __tablename__ = "shortpick_candidates"
    __table_args__ = (UniqueConstraint("candidate_key", name="uq_shortpick_candidate_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("shortpick_experiment_runs.id"), nullable=False, index=True)
    round_id: Mapped[int | None] = mapped_column(ForeignKey("shortpick_model_rounds.id"), nullable=True, index=True)
    candidate_key: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_theme: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    horizon_trading_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    thesis: Mapped[str | None] = mapped_column(Text, nullable=True)
    catalysts: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    invalidation: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    risks: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    sources_payload: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    novelty_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    limitations: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    convergence_group: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    research_priority: Mapped[str] = mapped_column(String(32), default="pending_consensus", nullable=False, index=True)
    parse_status: Mapped[str] = mapped_column(String(24), default="parsed", nullable=False, index=True)
    is_system_external: Mapped[bool] = mapped_column(default=True, nullable=False, index=True)
    candidate_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class ShortpickConsensusSnapshot(TimestampedMixin, Base):
    __tablename__ = "shortpick_consensus_snapshots"
    __table_args__ = (UniqueConstraint("snapshot_key", name="uq_shortpick_consensus_snapshot_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("shortpick_experiment_runs.id"), nullable=False, index=True)
    snapshot_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    artifact_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    stock_convergence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    theme_convergence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    source_diversity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    model_independence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    novelty_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    research_priority: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    summary_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class ShortpickValidationSnapshot(TimestampedMixin, Base):
    __tablename__ = "shortpick_validation_snapshots"
    __table_args__ = (
        UniqueConstraint("candidate_id", "horizon_days", name="uq_shortpick_validation_candidate_horizon"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("shortpick_candidates.id"), nullable=False, index=True)
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    entry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    entry_close: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_close: Mapped[float | None] = mapped_column(Float, nullable=True)
    stock_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    benchmark_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    excess_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_favorable_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_drawdown: Mapped[float | None] = mapped_column(Float, nullable=True)
    validation_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class SimulationSession(TimestampedMixin, LineageMixin, Base):
    __tablename__ = "simulation_sessions"
    __table_args__ = (UniqueConstraint("session_key", name="uq_simulation_session_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    owner_login: Mapped[str] = mapped_column(String(128), nullable=False, default="root", index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    focus_symbol: Mapped[str | None] = mapped_column(String(32), nullable=True)
    benchmark_symbol: Mapped[str | None] = mapped_column(String(32), nullable=True)
    initial_cash: Mapped[float] = mapped_column(Float, nullable=False)
    current_step: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    step_interval_seconds: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    auto_execute_model: Mapped[bool] = mapped_column(default=True, nullable=False)
    restart_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_resumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_data_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    manual_portfolio_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_portfolio_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    session_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    events: Mapped[list["SimulationEvent"]] = relationship(back_populates="session")


class SimulationEvent(TimestampedMixin, LineageMixin, Base):
    __tablename__ = "simulation_events"
    __table_args__ = (UniqueConstraint("event_key", name="uq_simulation_event_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_key: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    owner_login: Mapped[str] = mapped_column(String(128), nullable=False, default="root", index=True)
    actor_login: Mapped[str] = mapped_column(String(128), nullable=False, default="root", index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("simulation_sessions.id"), nullable=False, index=True)
    step_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    track: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    happened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    symbol: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), default="info", nullable=False)
    event_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    session: Mapped[SimulationSession] = relationship(back_populates="events")
