from __future__ import annotations

from datetime import date, datetime
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
    open_price: float
    high_price: float
    low_price: float
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


class TradingRuleCheckView(BaseModel):
    code: str
    title: str
    status: str
    detail: str


class PortfolioHoldingView(BaseModel):
    symbol: str
    name: str
    quantity: int
    avg_cost: float
    last_price: float
    prev_close: float | None = None
    market_value: float
    unrealized_pnl: float
    realized_pnl: float
    total_pnl: float
    holding_pnl_pct: float | None = None
    today_pnl_amount: float
    today_pnl_pct: float | None = None
    portfolio_weight: float
    pnl_contribution: float


class PortfolioAttributionView(BaseModel):
    label: str
    amount: float
    contribution_pct: float
    detail: str


class PortfolioNavPointView(BaseModel):
    trade_date: date
    nav: float
    benchmark_nav: float
    drawdown: float
    exposure: float


class PortfolioOrderAuditView(BaseModel):
    order_key: str
    symbol: str
    stock_name: str
    order_source: str
    side: str
    requested_at: datetime
    status: str
    quantity: int
    order_type: str
    avg_fill_price: float | None = None
    gross_amount: float
    checks: list[TradingRuleCheckView] = Field(default_factory=list)


class PortfolioSummaryView(BaseModel):
    portfolio_key: str
    name: str
    mode: str
    mode_label: str
    strategy_summary: str
    benchmark_symbol: str | None = None
    status: str
    starting_cash: float
    available_cash: float
    market_value: float
    net_asset_value: float
    invested_ratio: float
    total_return: float
    benchmark_return: float
    excess_return: float
    realized_pnl: float
    unrealized_pnl: float
    fee_total: float
    tax_total: float
    max_drawdown: float
    current_drawdown: float
    order_count: int
    active_position_count: int
    rule_pass_rate: float
    recommendation_hit_rate: float
    alerts: list[str] = Field(default_factory=list)
    rules: list[TradingRuleCheckView] = Field(default_factory=list)
    holdings: list[PortfolioHoldingView] = Field(default_factory=list)
    attribution: list[PortfolioAttributionView] = Field(default_factory=list)
    nav_history: list[PortfolioNavPointView] = Field(default_factory=list)
    recent_orders: list[PortfolioOrderAuditView] = Field(default_factory=list)


class SimulationRiskExposureView(BaseModel):
    invested_ratio: float
    cash_ratio: float
    max_position_weight: float
    drawdown: float
    active_position_count: int


class SimulationTrackStateView(BaseModel):
    role: str
    label: str
    portfolio: PortfolioSummaryView
    risk_exposure: SimulationRiskExposureView
    latest_reason: str | None = None


class SimulationSessionView(BaseModel):
    session_key: str
    name: str
    status: str
    status_label: str
    focus_symbol: str | None = None
    watch_symbols: list[str] = Field(default_factory=list)
    benchmark_symbol: str | None = None
    initial_cash: float
    current_step: int
    step_interval_seconds: int
    step_trigger_label: str
    fill_rule_label: str
    auto_execute_model: bool
    restart_count: int
    started_at: datetime | None = None
    last_resumed_at: datetime | None = None
    paused_at: datetime | None = None
    ended_at: datetime | None = None
    last_data_time: datetime | None = None
    resumable: bool


class SimulationControlStateView(BaseModel):
    can_start: bool
    can_pause: bool
    can_resume: bool
    can_step: bool
    can_restart: bool
    can_end: bool
    end_requires_confirmation: bool


class SimulationConfigView(BaseModel):
    focus_symbol: str | None = None
    watch_symbols: list[str] = Field(default_factory=list)
    initial_cash: float
    benchmark_symbol: str | None = None
    step_interval_seconds: int
    auto_execute_model: bool
    editable_fields: list[str] = Field(default_factory=list)


class SimulationTimelineEventView(BaseModel):
    event_key: str
    step_index: int
    track: str
    track_label: str
    event_type: str
    happened_at: datetime
    symbol: str | None = None
    title: str
    detail: str
    severity: str
    reason_tags: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    lineage: LineageRecord


class SimulationDecisionDiffView(BaseModel):
    step_index: int
    happened_at: datetime
    symbol: str | None = None
    manual_action: str
    manual_reason: str
    model_action: str
    model_reason: str
    difference_summary: str
    risk_focus: list[str] = Field(default_factory=list)


class SimulationComparisonMetricView(BaseModel):
    label: str
    unit: str
    manual_value: float
    model_value: float
    difference: float
    leader: str


class SimulationModelAdviceView(BaseModel):
    symbol: str
    stock_name: str
    direction: str
    direction_label: str
    action: str
    quantity: int
    reference_price: float
    confidence_label: str
    generated_at: datetime
    reason: str
    risk_flags: list[str] = Field(default_factory=list)
    score: int


class SimulationKlineView(BaseModel):
    symbol: str | None = None
    stock_name: str | None = None
    last_updated: datetime | None = None
    points: list[PricePointView] = Field(default_factory=list)


class SimulationWorkspaceResponse(BaseModel):
    session: SimulationSessionView
    controls: SimulationControlStateView
    configuration: SimulationConfigView
    manual_track: SimulationTrackStateView
    model_track: SimulationTrackStateView
    comparison_metrics: list[SimulationComparisonMetricView] = Field(default_factory=list)
    model_advices: list[SimulationModelAdviceView] = Field(default_factory=list)
    timeline: list[SimulationTimelineEventView] = Field(default_factory=list)
    decision_differences: list[SimulationDecisionDiffView] = Field(default_factory=list)
    kline: SimulationKlineView


class RecommendationReplayView(BaseModel):
    recommendation_id: int
    symbol: str
    stock_name: str
    direction: str
    generated_at: datetime
    review_window_days: int
    stock_return: float
    benchmark_return: float
    excess_return: float
    max_favorable_excursion: float
    max_adverse_excursion: float
    hit_status: str
    summary: str
    followed_by_portfolios: list[str] = Field(default_factory=list)


class OperationsOverviewView(BaseModel):
    generated_at: datetime
    beta_readiness: str
    manual_portfolio_count: int
    auto_portfolio_count: int
    recommendation_replay_hit_rate: float
    rule_pass_rate: float


class AccessControlView(BaseModel):
    beta_phase: str
    auth_mode: str
    required_header: str
    allowlist_slots: int
    active_users: int
    roles: list[str] = Field(default_factory=list)
    session_ttl_minutes: int
    audit_log_retention_days: int
    export_policy: str
    alerts: list[str] = Field(default_factory=list)


class RefreshScheduleView(BaseModel):
    scope: str
    cadence_minutes: int
    market_delay_minutes: int
    stale_after_minutes: int
    trigger: str


class RefreshPolicyView(BaseModel):
    market_timezone: str
    cache_ttl_seconds: int
    manual_refresh_cooldown_minutes: int
    schedules: list[RefreshScheduleView] = Field(default_factory=list)


class PerformanceThresholdView(BaseModel):
    metric: str
    unit: str
    target: float
    observed: float
    status: str
    note: str


class LaunchGateView(BaseModel):
    gate: str
    threshold: str
    current_value: str
    status: str


class OperationsDashboardResponse(BaseModel):
    overview: OperationsOverviewView
    portfolios: list[PortfolioSummaryView] = Field(default_factory=list)
    recommendation_replay: list[RecommendationReplayView] = Field(default_factory=list)
    access_control: AccessControlView
    refresh_policy: RefreshPolicyView
    performance_thresholds: list[PerformanceThresholdView] = Field(default_factory=list)
    launch_gates: list[LaunchGateView] = Field(default_factory=list)
    simulation_workspace: SimulationWorkspaceResponse | None = None


class SimulationConfigRequest(BaseModel):
    initial_cash: float = Field(gt=0)
    watch_symbols: list[str] = Field(default_factory=list)
    focus_symbol: str | None = None
    step_interval_seconds: int = Field(default=300, ge=60, le=86400)
    auto_execute_model: bool = True


class SimulationControlActionResponse(BaseModel):
    workspace: SimulationWorkspaceResponse
    message: str


class ManualSimulationOrderRequest(BaseModel):
    symbol: str
    side: str
    quantity: int = Field(ge=100)
    reason: str
    limit_price: float | None = None


class SimulationEndRequest(BaseModel):
    confirm: bool


class RuntimeDataSourceView(BaseModel):
    provider_name: str
    role: str
    freshness_note: str
    docs_url: str
    notes: list[str] = Field(default_factory=list)
    credential_configured: bool
    credential_required: bool
    runtime_ready: bool
    status_label: str
    base_url: str | None = None
    enabled: bool


class RuntimeFieldMappingView(BaseModel):
    dataset: str
    canonical_field: str
    akshare_field: str
    tushare_field: str
    notes: str


class CacheDatasetPolicyView(BaseModel):
    dataset: str
    label: str
    ttl_seconds: int
    stale_if_error_seconds: int
    warm_on_watchlist: bool


class ProviderCredentialView(BaseModel):
    id: int
    provider_name: str
    display_name: str
    base_url: str | None = None
    enabled: bool
    notes: str | None = None
    token_configured: bool
    masked_token: str | None = None
    created_at: datetime
    updated_at: datetime


class ModelApiKeyView(BaseModel):
    id: int
    name: str
    provider_name: str
    model_name: str
    base_url: str
    enabled: bool
    is_default: bool
    priority: int
    masked_key: str | None = None
    last_status: str
    last_error: str | None = None
    last_checked_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class RuntimeSettingsResponse(BaseModel):
    generated_at: datetime
    deployment_mode: str
    storage_engine: str
    cache_backend: str
    watchlist_scope: str
    watchlist_cache_only: bool
    llm_failover_enabled: bool
    deployment_notes: list[str] = Field(default_factory=list)
    provider_selection_mode: str
    provider_order: list[str] = Field(default_factory=list)
    provider_cooldown_seconds: int
    field_mappings: list[RuntimeFieldMappingView] = Field(default_factory=list)
    data_sources: list[RuntimeDataSourceView] = Field(default_factory=list)
    cache_policies: list[CacheDatasetPolicyView] = Field(default_factory=list)
    anti_stampede: dict[str, Any] = Field(default_factory=dict)
    provider_credentials: list[ProviderCredentialView] = Field(default_factory=list)
    model_api_keys: list[ModelApiKeyView] = Field(default_factory=list)
    default_model_api_key_id: int | None = None


class ProviderCredentialUpsertRequest(BaseModel):
    access_token: str | None = None
    base_url: str | None = None
    enabled: bool = True
    notes: str | None = None


class ModelApiKeyCreateRequest(BaseModel):
    name: str
    provider_name: str = "openai"
    model_name: str
    base_url: str
    api_key: str
    enabled: bool = True
    priority: int = 100
    make_default: bool = False


class ModelApiKeyUpdateRequest(BaseModel):
    name: str | None = None
    provider_name: str | None = None
    model_name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    enabled: bool | None = None
    priority: int | None = None
    make_default: bool | None = None


class ModelApiKeyDeleteResponse(BaseModel):
    id: int
    name: str
    deleted: bool
    deleted_at: datetime


class AnalysisAttemptView(BaseModel):
    key_id: int
    name: str
    provider_name: str
    model_name: str
    status: str
    error: str | None = None


class AnalysisKeySelectionView(BaseModel):
    id: int
    name: str
    provider_name: str
    model_name: str
    base_url: str


class FollowUpAnalysisRequest(BaseModel):
    symbol: str
    question: str
    model_api_key_id: int | None = None
    failover_enabled: bool = True


class FollowUpAnalysisResponse(BaseModel):
    symbol: str
    question: str
    answer: str
    selected_key: AnalysisKeySelectionView
    failover_used: bool
    attempted_keys: list[AnalysisAttemptView] = Field(default_factory=list)
