"""O p e r a t i o n s domain schemas."""

from ashare_evidence.contract_status import STATUS_PENDING_REBUILD
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from .portfolio import PortfolioSummaryView
from .research import ManualResearchRequestView
from .simulation import SimulationWorkspaceResponse


class PricePointView(BaseModel):
    observed_at: datetime
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float


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
    focus_request: ManualResearchRequestView | None = None
    recent_items: list[ManualResearchRequestView] = Field(default_factory=list)


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

