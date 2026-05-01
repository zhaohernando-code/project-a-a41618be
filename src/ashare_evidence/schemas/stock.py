"""S t o c k domain schemas."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from ashare_evidence.contract_status import STATUS_PENDING_REBUILD
from ashare_evidence.lineage import LineageRecord

if TYPE_CHECKING:
    from .operations import PricePointView
    from .simulation import SimulationOrderView


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


class QuantCoreView(BaseModel):
    score: float | None = None
    score_scale: str = "phase2_rule_baseline_score"
    direction: str
    confidence_bucket: str
    target_horizon_label: str
    horizon_min_days: int
    horizon_max_days: int
    as_of_time: datetime
    available_time: datetime
    model_version: str
    policy_version: str


class RecommendationEvidenceView(BaseModel):
    primary_drivers: list[str] = Field(default_factory=list)
    supporting_context: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    degrade_flags: list[str] = Field(default_factory=list)
    data_freshness: str | None = None
    source_links: list[str] = Field(default_factory=list)
    factor_cards: list[dict[str, Any]] = Field(default_factory=list)


class RecommendationRiskView(BaseModel):
    risk_flags: list[str] = Field(default_factory=list)
    downgrade_conditions: list[str] = Field(default_factory=list)
    invalidators: list[str] = Field(default_factory=list)
    coverage_gaps: list[str] = Field(default_factory=list)


class HistoricalValidationView(BaseModel):
    status: str = STATUS_PENDING_REBUILD
    note: str | None = None
    artifact_type: str | None = None
    artifact_id: str | None = None
    manifest_id: str | None = None
    artifact_generated_at: datetime | None = None
    label_definition: str | None = None
    window_definition: str | None = None
    benchmark_definition: str | None = None
    cost_definition: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)


class ManualLlmReviewView(BaseModel):
    status: str = "manual_trigger_required"
    trigger_mode: str = "manual"
    model_label: str | None = None
    requested_at: datetime | None = None
    generated_at: datetime | None = None
    summary: str | None = None
    risks: list[str] = Field(default_factory=list)
    disagreements: list[str] = Field(default_factory=list)
    source_packet: list[str] = Field(default_factory=list)
    artifact_id: str | None = None
    question: str | None = None
    raw_answer: str | None = None
    request_id: int | None = None
    request_key: str | None = None
    executor_kind: str | None = None
    status_note: str | None = None
    review_verdict: str | None = None
    decision_note: str | None = None
    stale_reason: str | None = None
    citations: list[str] = Field(default_factory=list)


class ClaimGateView(BaseModel):
    status: str
    headline: str
    note: str | None = None
    public_direction: str
    blocking_reasons: list[str] = Field(default_factory=list)
    sample_count: int | None = None
    coverage_ratio: float | None = None


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
    data_freshness: str | None = None
    degraded_sources: list[str] = Field(default_factory=list)
    confidence_ceiling_reasons: list[str] = Field(default_factory=list)
    core_drivers: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    reverse_risks: list[str] = Field(default_factory=list)
    downgrade_conditions: list[str] = Field(default_factory=list)
    factor_breakdown: dict[str, Any] = Field(default_factory=dict)
    validation_status: str = STATUS_PENDING_REBUILD
    validation_note: str | None = None
    validation_snapshot: dict[str, Any] = Field(default_factory=dict)
    core_quant: QuantCoreView
    evidence: RecommendationEvidenceView
    risk: RecommendationRiskView
    historical_validation: HistoricalValidationView
    manual_llm_review: ManualLlmReviewView
    claim_gate: ClaimGateView
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


class EventAnalysisView(BaseModel):
    file: str
    trigger_type: str
    triggered_at: datetime | None = None
    generated_at: datetime | None = None
    status: str = "unknown"
    independent_direction: str | None = None
    confidence: float | None = None
    trigger_detail: str | None = None
    key_evidence: list[dict[str, Any] | str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    information_gaps: list[str] = Field(default_factory=list)
    next_checkpoint: str | None = None
    correction_suggestion: str | None = None
    model_used: str | None = None


class FollowUpResearchPacketView(BaseModel):
    validation_status: str = STATUS_PENDING_REBUILD
    validation_note: str | None = None
    validation_artifact_id: str | None = None
    validation_manifest_id: str | None = None
    validation_sample_count: int | None = None
    validation_rank_ic_mean: float | None = None
    validation_positive_excess_rate: float | None = None
    manual_request_id: int | None = None
    manual_request_key: str | None = None
    manual_review_executor_kind: str | None = None
    manual_review_status_note: str | None = None
    manual_review_review_verdict: str | None = None
    manual_review_stale_reason: str | None = None
    manual_review_status: str
    manual_review_trigger_mode: str
    manual_review_source_packet: list[str] = Field(default_factory=list)
    manual_review_artifact_id: str | None = None
    manual_review_generated_at: datetime | None = None


class FollowUpView(BaseModel):
    suggested_questions: list[str] = Field(default_factory=list)
    copy_prompt: str
    evidence_packet: list[str] = Field(default_factory=list)
    research_packet: FollowUpResearchPacketView


class CandidateItemView(BaseModel):
    rank: int
    symbol: str
    name: str
    sector: str
    direction: str
    direction_label: str
    display_direction: str
    display_direction_label: str
    confidence_label: str
    confidence_score: float
    summary: str
    applicable_period: str | None = None
    window_definition: str
    target_horizon_label: str
    source_classification: str | None = None
    validation_mode: str | None = None
    validation_status: str = STATUS_PENDING_REBUILD
    validation_note: str | None = None
    validation_artifact_id: str | None = None
    validation_manifest_id: str | None = None
    validation_sample_count: int | None = None
    validation_rank_ic_mean: float | None = None
    validation_positive_excess_rate: float | None = None
    generated_at: datetime
    as_of_data_time: datetime
    last_close: float | None = None
    price_return_20d: float
    price_chart: list[dict[str, Any]] = Field(default_factory=list)
    why_now: str
    primary_risk: str | None = None
    change_summary: str
    change_badge: str
    evidence_status: str
    claim_gate: ClaimGateView


class CandidateListResponse(BaseModel):
    generated_at: datetime
    items: list[CandidateItemView] = Field(default_factory=list)


class WatchlistItemView(BaseModel):
    symbol: str
    name: str
    exchange: str
    ticker: str
    status: str
    source_kind: str
    analysis_status: str
    added_at: datetime
    updated_at: datetime
    last_analyzed_at: datetime | None = None
    last_error: str | None = None
    latest_direction: str | None = None
    latest_confidence_label: str | None = None
    latest_generated_at: datetime | None = None


class WatchlistResponse(BaseModel):
    generated_at: datetime
    items: list[WatchlistItemView] = Field(default_factory=list)


class WatchlistCreateRequest(BaseModel):
    symbol: str
    name: str | None = None


class WatchlistMutationResponse(BaseModel):
    item: WatchlistItemView
    message: str


class WatchlistDeleteResponse(BaseModel):
    symbol: str
    removed: bool
    active_count: int
    removed_at: datetime


class StockDashboardResponse(RecommendationTraceResponse):
    hero: HeroView
    price_chart: list[PricePointView] = Field(default_factory=list)
    today_price_chart: list[PricePointView] = Field(default_factory=list)
    recent_news: list[RecentNewsView] = Field(default_factory=list)
    change: ChangeView
    glossary: list[GlossaryEntryView] = Field(default_factory=list)
    risk_panel: RiskPanelView
    event_analyses: list[EventAnalysisView] = Field(default_factory=list)
    follow_up: FollowUpView
    data_quality: dict[str, Any] = Field(default_factory=dict)
    research_horizon_readout: str | dict[str, Any] | list[dict[str, Any]] | None = None
    factor_validation: dict[str, Any] = Field(default_factory=dict)
    benchmark_context: dict[str, Any] = Field(default_factory=dict)
