"""S i m u l a t i o n domain schemas."""
from __future__ import annotations

from ashare_evidence.lineage import LineageRecord
from ashare_evidence.contract_status import STATUS_PENDING_REBUILD
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from .portfolio import PortfolioSummaryView

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .operations import PricePointView


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


from .operations import PricePointView  # noqa: E402

SimulationTrackStateView.model_rebuild()
SimulationKlineView.model_rebuild()

