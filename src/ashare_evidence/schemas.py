from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from ashare_evidence.lineage import LineageRecord


class StockView(BaseModel):
    symbol: str
    name: str
    exchange: str
    ticker: str


class ModelView(BaseModel):
    name: str
    family: str
    version: str
    validation_scheme: str
    artifact_uri: str | None = None
    lineage: LineageRecord


class PromptView(BaseModel):
    name: str
    version: str
    risk_disclaimer: str
    lineage: LineageRecord


class RecommendationView(BaseModel):
    id: int
    recommendation_key: str
    direction: str
    confidence_label: str
    confidence_score: float
    confidence_expression: str | None = None
    horizon_min_days: int
    horizon_max_days: int
    applicable_period: str | None = None
    summary: str
    generated_at: datetime
    updated_at: datetime
    as_of_data_time: datetime
    evidence_status: str
    degrade_reason: str | None = None
    core_drivers: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    reverse_risks: list[str] = Field(default_factory=list)
    downgrade_conditions: list[str] = Field(default_factory=list)
    factor_breakdown: dict[str, Any] = Field(default_factory=dict)
    validation_snapshot: dict[str, Any] = Field(default_factory=dict)
    lineage: LineageRecord


class EvidenceArtifactView(BaseModel):
    evidence_type: str
    record_id: int
    role: str
    rank: int
    label: str
    snippet: str | None = None
    timestamp: datetime | None = None
    lineage: LineageRecord
    payload: dict[str, Any] = Field(default_factory=dict)


class SimulationFillView(BaseModel):
    filled_at: datetime
    price: float
    quantity: int
    fee: float
    tax: float
    slippage_bps: float
    lineage: LineageRecord


class SimulationOrderView(BaseModel):
    id: int
    order_source: str
    side: str
    status: str
    requested_at: datetime
    quantity: int
    limit_price: float | None = None
    fills: list[SimulationFillView] = Field(default_factory=list)
    lineage: LineageRecord


class LatestRecommendationResponse(BaseModel):
    stock: StockView
    recommendation: RecommendationView
    model: ModelView
    prompt: PromptView


class RecommendationTraceResponse(LatestRecommendationResponse):
    evidence: list[EvidenceArtifactView] = Field(default_factory=list)
    simulation_orders: list[SimulationOrderView] = Field(default_factory=list)


class HeroView(BaseModel):
    latest_close: float
    day_change_pct: float
    latest_volume: float
    turnover_rate: float | None = None
    high_price: float
    low_price: float
    sector_tags: list[str] = Field(default_factory=list)
    direction_label: str
    last_updated: datetime


class PricePointView(BaseModel):
    observed_at: datetime
    close_price: float
    volume: float


class RecentNewsView(BaseModel):
    headline: str
    summary: str
    published_at: datetime
    impact_direction: str
    entity_scope: str
    relevance_score: float
    source_uri: str
    license_tag: str


class ChangeView(BaseModel):
    has_previous: bool
    change_badge: str
    summary: str
    reasons: list[str] = Field(default_factory=list)
    previous_direction: str | None = None
    previous_confidence_label: str | None = None
    previous_generated_at: datetime | None = None


class GlossaryEntryView(BaseModel):
    term: str
    plain_explanation: str
    why_it_matters: str


class RiskPanelView(BaseModel):
    headline: str
    items: list[str] = Field(default_factory=list)
    disclaimer: str
    change_hint: str


class FollowUpView(BaseModel):
    suggested_questions: list[str] = Field(default_factory=list)
    copy_prompt: str
    evidence_packet: list[str] = Field(default_factory=list)


class CandidateItemView(BaseModel):
    rank: int
    symbol: str
    name: str
    sector: str
    direction: str
    direction_label: str
    confidence_label: str
    confidence_score: float
    summary: str
    applicable_period: str
    generated_at: datetime
    as_of_data_time: datetime
    last_close: float | None = None
    price_return_20d: float
    why_now: str
    primary_risk: str | None = None
    change_summary: str
    change_badge: str
    evidence_status: str


class CandidateListResponse(BaseModel):
    generated_at: datetime
    items: list[CandidateItemView] = Field(default_factory=list)


class DashboardBootstrapResponse(BaseModel):
    symbols: list[str] = Field(default_factory=list)
    recommendation_count: int
    candidate_count: int


class StockDashboardResponse(RecommendationTraceResponse):
    hero: HeroView
    price_chart: list[PricePointView] = Field(default_factory=list)
    recent_news: list[RecentNewsView] = Field(default_factory=list)
    change: ChangeView
    glossary: list[GlossaryEntryView] = Field(default_factory=list)
    risk_panel: RiskPanelView
    follow_up: FollowUpView
