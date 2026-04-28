from __future__ import annotations

from datetime import date, datetime
from typing import Any

from ashare_evidence.contract_status import STATUS_PENDING_REBUILD
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
    observed_at: datetime | None = None


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


class BenchmarkContextView(BaseModel):
    benchmark_id: str
    benchmark_type: str
    benchmark_symbol: str | None = None
    benchmark_label: str
    source: str
    source_classification: str | None = None
    as_of_time: datetime | None = None
    available_time: datetime | None = None
    status: str = STATUS_PENDING_REBUILD
    note: str | None = None
    artifact_id: str | None = None
    manifest_id: str | None = None
    benchmark_definition: str | None = None


class PortfolioPerformanceView(BaseModel):
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
    annualized_return: float | None = None
    annualized_excess_return: float | None = None
    sharpe_like_ratio: float | None = None
    turnover: float | None = None
    win_rate_definition: str | None = None
    win_rate: float | None = None
    capacity_note: str | None = None
    artifact_id: str | None = None
    validation_mode: str | None = None
    benchmark_definition: str | None = None
    cost_definition: str | None = None
    cost_source: str | None = None


class ExecutionPolicyView(BaseModel):
    status: str = STATUS_PENDING_REBUILD
    label: str
    summary: str
    policy_type: str | None = None
    source: str | None = None
    note: str | None = None
    constraints: list[str] = Field(default_factory=list)


class PortfolioSummaryView(BaseModel):
    portfolio_key: str
    name: str
    mode: str
    mode_label: str
    strategy_summary: str
    strategy_label: str
    strategy_status: str | None = STATUS_PENDING_REBUILD
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
    benchmark_status: str | None = STATUS_PENDING_REBUILD
    benchmark_note: str | None = None
    realized_pnl: float
    unrealized_pnl: float
    fee_total: float
    tax_total: float
    max_drawdown: float
    current_drawdown: float
    order_count: int
    active_position_count: int
    rule_pass_rate: float
    recommendation_hit_rate: float | None = None
    market_data_timeframe: str
    last_market_data_at: datetime | None = None
    benchmark_context: BenchmarkContextView
    performance: PortfolioPerformanceView
    execution_policy: ExecutionPolicyView
    validation_status: str = STATUS_PENDING_REBUILD
    validation_note: str | None = None
    validation_artifact_id: str | None = None
    validation_manifest_id: str | None = None
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
    auto_execute_model_requested: bool = False
    auto_execute_status: str = STATUS_PENDING_REBUILD
    auto_execute_note: str | None = None
    restart_count: int
    started_at: datetime | None = None
    last_resumed_at: datetime | None = None
    paused_at: datetime | None = None
    ended_at: datetime | None = None
    last_data_time: datetime | None = None
    market_data_timeframe: str
    market_data_interval_seconds: int
    last_market_data_at: datetime | None = None
    data_latency_seconds: int | None = None
    intraday_source_status: dict[str, Any] = Field(default_factory=dict)
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
    market_data_interval_seconds: int
    auto_execute_model: bool
    auto_execute_model_requested: bool = False
    auto_execute_status: str = STATUS_PENDING_REBUILD
    auto_execute_note: str | None = None
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
    quantity: int | None = None
    current_weight: float | None = None
    target_weight: float | None = None
    trade_delta_weight: float | None = None
    rank: int | None = None
    reference_price: float
    confidence_label: str
    generated_at: datetime
    reason: str
    risk_flags: list[str] = Field(default_factory=list)
    policy_status: str = STATUS_PENDING_REBUILD
    policy_type: str | None = None
    policy_note: str | None = None
    action_definition: str | None = None
    quantity_definition: str | None = None
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
    source: str | None = None
    source_classification: str | None = None
    artifact_type: str | None = None
    artifact_id: str | None = None
    manifest_id: str | None = None
    recommendation_id: int
    recommendation_key: str | None = None
    symbol: str
    stock_name: str
    direction: str
    generated_at: datetime
    label_definition: str
    review_window_definition: str
    entry_time: datetime
    exit_time: datetime
    review_window_days: int | None = None
    stock_return: float
    benchmark_return: float
    excess_return: float
    max_favorable_excursion: float
    max_adverse_excursion: float
    benchmark_definition: str | None = None
    benchmark_source: str | None = None
    validation_mode: str | None = None
    hit_definition: str
    hit_status: str
    validation_status: str = STATUS_PENDING_REBUILD
    validation_note: str | None = None
    summary: str
    followed_by_portfolios: list[str] = Field(default_factory=list)


class OperationsRunHealthView(BaseModel):
    status: str
    note: str | None = None
    market_data_timeframe: str
    last_market_data_at: datetime | None = None
    data_latency_seconds: int | None = None
    refresh_cooldown_minutes: int
    intraday_source_status: str


class Phase5HorizonSelectionSummaryView(BaseModel):
    approval_state: str
    candidate_frontier: list[int] = Field(default_factory=list)
    lagging_horizons: list[int] = Field(default_factory=list)
    included_record_count: int = 0
    included_as_of_date_count: int = 0
    artifact_id: str | None = None
    artifact_available: bool = False
    note: str | None = None


class Phase5HoldingPolicyStudySummaryView(BaseModel):
    approval_state: str
    included_portfolio_count: int = 0
    mean_turnover: float | None = None
    mean_annualized_excess_return_after_baseline_cost: float | None = None
    gate_status: str | None = None
    governance_status: str | None = None
    governance_action: str | None = None
    redesign_status: str | None = None
    redesign_focus_areas: list[str] = Field(default_factory=list)
    redesign_triggered_signal_ids: list[str] = Field(default_factory=list)
    redesign_primary_experiment_ids: list[str] = Field(default_factory=list)
    failing_gate_ids: list[str] = Field(default_factory=list)
    artifact_id: str | None = None
    artifact_available: bool = False
    note: str | None = None


class OperationsResearchValidationView(BaseModel):
    status: str = STATUS_PENDING_REBUILD
    note: str | None = None
    recommendation_contract_status: str = STATUS_PENDING_REBUILD
    benchmark_status: str = STATUS_PENDING_REBUILD
    benchmark_note: str | None = None
    replay_validation_status: str = STATUS_PENDING_REBUILD
    replay_validation_note: str | None = None
    replay_sample_count: int = 0
    verified_replay_count: int = 0
    synthetic_replay_count: int = 0
    manifest_bound_count: int = 0
    metrics_artifact_count: int = 0
    artifact_sample_count: int = 0
    replay_artifact_bound_count: int = 0
    replay_artifact_manifest_count: int = 0
    replay_artifact_nonverified_count: int = 0
    replay_artifact_backed_projection_count: int = 0
    replay_migration_placeholder_count: int = 0
    portfolio_backtest_bound_count: int = 0
    portfolio_backtest_manifest_count: int = 0
    portfolio_backtest_verified_count: int = 0
    portfolio_backtest_pending_rebuild_count: int = 0
    portfolio_backtest_artifact_backed_projection_count: int = 0
    portfolio_backtest_migration_placeholder_count: int = 0
    phase5_horizon_selection: Phase5HorizonSelectionSummaryView | None = None
    phase5_holding_policy_study: Phase5HoldingPolicyStudySummaryView | None = None


class OperationsLaunchReadinessView(BaseModel):
    status: str
    note: str | None = None
    blocking_gate_count: int = 0
    warning_gate_count: int = 0
    synthetic_fields_present: bool = False
    recommended_next_gate: str | None = None
    rule_pass_rate: float = 0.0


class OperationsOverviewView(BaseModel):
    generated_at: datetime
    beta_readiness: str | None = None
    manual_portfolio_count: int
    auto_portfolio_count: int
    recommendation_replay_hit_rate: float | None = None
    replay_validation_status: str | None = STATUS_PENDING_REBUILD
    replay_validation_note: str | None = None
    rule_pass_rate: float
    run_health: OperationsRunHealthView
    research_validation: OperationsResearchValidationView
    launch_readiness: OperationsLaunchReadinessView


class IntradaySourceStatusView(BaseModel):
    status: str
    provider_name: str | None = None
    provider_label: str | None = None
    source_kind: str
    timeframe: str
    decision_interval_seconds: int
    market_data_interval_seconds: int
    symbol_count: int
    last_success_at: str | None = None
    latest_market_data_at: str | None = None
    data_latency_seconds: int | None = None
    fallback_used: bool = False
    stale: bool = False
    message: str | None = None


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


class ManualResearchQueueView(BaseModel):
    generated_at: datetime
    focus_symbol: str | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    focus_request: "ManualResearchRequestView | None" = None
    recent_items: list["ManualResearchRequestView"] = Field(default_factory=list)


class OperationsDashboardResponse(BaseModel):
    overview: OperationsOverviewView
    market_data_timeframe: str
    last_market_data_at: datetime | None = None
    data_latency_seconds: int | None = None
    intraday_source_status: IntradaySourceStatusView
    portfolios: list[PortfolioSummaryView] = Field(default_factory=list)
    recommendation_replay: list[RecommendationReplayView] = Field(default_factory=list)
    access_control: AccessControlView
    refresh_policy: RefreshPolicyView
    performance_thresholds: list[PerformanceThresholdView] = Field(default_factory=list)
    launch_gates: list[LaunchGateView] = Field(default_factory=list)
    manual_research_queue: ManualResearchQueueView
    simulation_workspace: SimulationWorkspaceResponse | None = None


class SimulationConfigRequest(BaseModel):
    initial_cash: float = Field(gt=0)
    watch_symbols: list[str] = Field(default_factory=list)
    focus_symbol: str | None = None
    step_interval_seconds: int = Field(default=1800, ge=300, le=86400)
    auto_execute_model: bool = False


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
    supports_intraday: bool = False
    intraday_runtime_ready: bool = False
    intraday_status_label: str | None = None
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
    key_id: int | None = None
    name: str
    provider_name: str
    model_name: str
    status: str
    error: str | None = None


class AnalysisKeySelectionView(BaseModel):
    id: int | None = None
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
    request_id: int
    request_key: str
    status: str
    executor_kind: str
    status_note: str | None = None
    answer: str | None = None
    selected_key: AnalysisKeySelectionView | None = None
    failover_used: bool = False
    attempted_keys: list[AnalysisAttemptView] = Field(default_factory=list)
    manual_review_artifact_id: str | None = None


class ManualResearchRequestCreateRequest(BaseModel):
    symbol: str
    question: str
    trigger_source: str = "manual_research_ui"
    executor_kind: str = "builtin_gpt"
    model_api_key_id: int | None = None


class ManualResearchRequestExecuteRequest(BaseModel):
    failover_enabled: bool = True


class ManualResearchRequestCompleteRequest(BaseModel):
    summary: str
    review_verdict: str
    risks: list[str] = Field(default_factory=list)
    disagreements: list[str] = Field(default_factory=list)
    decision_note: str | None = None
    citations: list[str] = Field(default_factory=list)
    answer: str | None = None


class ManualResearchRequestFailRequest(BaseModel):
    failure_reason: str


class ManualResearchRequestRetryRequest(BaseModel):
    requested_by: str | None = None


class ManualResearchRequestView(BaseModel):
    id: int
    request_key: str
    recommendation_key: str
    symbol: str
    question: str
    trigger_source: str
    executor_kind: str
    model_api_key_id: int | None = None
    status: str
    status_note: str | None = None
    requested_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failed_at: datetime | None = None
    artifact_id: str | None = None
    failure_reason: str | None = None
    requested_by: str | None = None
    superseded_by_request_id: int | None = None
    stale_reason: str | None = None
    source_packet_hash: str
    validation_artifact_id: str | None = None
    validation_manifest_id: str | None = None
    source_packet: list[str] = Field(default_factory=list)
    selected_key: AnalysisKeySelectionView | None = None
    attempted_keys: list[AnalysisAttemptView] = Field(default_factory=list)
    failover_used: bool = False
    manual_llm_review: ManualLlmReviewView


class ManualResearchRequestListResponse(BaseModel):
    generated_at: datetime
    counts: dict[str, int] = Field(default_factory=dict)
    items: list[ManualResearchRequestView] = Field(default_factory=list)
