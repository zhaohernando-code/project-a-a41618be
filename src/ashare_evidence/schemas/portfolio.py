"""P o r t f o l i o domain schemas."""

from ashare_evidence.contract_status import STATUS_PENDING_REBUILD
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


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


