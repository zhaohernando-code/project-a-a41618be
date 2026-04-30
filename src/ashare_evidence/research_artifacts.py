from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from ashare_evidence.contract_status import (
    STATUS_PENDING_REBUILD,
    STATUS_RESEARCH_CANDIDATE,
    STATUS_SYNTHETIC_DEMO,
    STATUS_VERIFIED,
)


ArtifactType = Literal[
    "rolling_validation",
    "validation_metrics",
    "portfolio_backtest",
    "replay_alignment",
    "manual_review",
    "phase5_horizon_study",
    "phase5_holding_policy_study",
    "phase5_holding_policy_experiment",
    "phase5_producer_contract_study",
]


class ArtifactSplitView(BaseModel):
    slice_label: str
    train_start: datetime
    train_end: datetime
    validation_start: datetime
    validation_end: datetime
    test_start: datetime
    test_end: datetime
    market_regime_tag: str | None = None


class ResearchArtifactManifestView(BaseModel):
    artifact_id: str
    artifact_type: ArtifactType
    generated_at: datetime
    created_at: datetime | None = None
    experiment_id: str | None = None
    experiment_version: str
    model_version: str
    policy_version: str
    data_snapshot_id: str
    data_snapshot_ids: list[str] = Field(default_factory=list)
    universe_definition: str
    universe_rule: str | None = None
    availability_rule: str
    feature_set_version: str
    feature_version: str | None = None
    label_definition: str
    benchmark_definition: str
    benchmark_context: dict[str, Any] = Field(default_factory=dict)
    research_contract: dict[str, Any] = Field(default_factory=dict)
    cost_definition: str
    cost_model: str | None = None
    rebalance_definition: str
    rolling_windows: list[dict[str, Any]] = Field(default_factory=list)
    leakage_checks: list[dict[str, Any]] = Field(default_factory=list)
    split_plan: list[ArtifactSplitView] = Field(default_factory=list)


class ValidationMetricsArtifactView(BaseModel):
    artifact_id: str
    manifest_id: str
    status: str
    status_note: str | None = None
    horizon: int | None = None
    sample_count: int
    rank_ic_mean: float | None = None
    rank_ic_std: float | None = None
    rank_ic_ir: float | None = None
    ic_mean: float | None = None
    bucket_returns: list[dict[str, Any]] = Field(default_factory=list)
    net_excess_return: float | None = None
    turnover: float | None = None
    coverage: float | None = None
    subperiod_stats: list[dict[str, Any]] = Field(default_factory=list)
    bucket_spread_mean: float | None = None
    bucket_spread_std: float | None = None
    positive_excess_rate: float | None = None
    turnover_mean: float | None = None
    coverage_ratio: float | None = None
    period_metrics: list[dict[str, Any]] = Field(default_factory=list)
    market_regime_metrics: list[dict[str, Any]] = Field(default_factory=list)
    industry_slice_metrics: list[dict[str, Any]] = Field(default_factory=list)
    feature_drift_summary: dict[str, Any] = Field(default_factory=dict)


class BacktestArtifactView(BaseModel):
    artifact_id: str
    artifact_type: Literal["portfolio_backtest"] = "portfolio_backtest"
    manifest_id: str
    status: str = STATUS_PENDING_REBUILD
    status_note: str | None = None
    strategy_definition: str
    rebalance_rule: str | None = None
    position_limit_definition: str
    position_constraints: dict[str, Any] = Field(default_factory=dict)
    execution_assumptions: str
    benchmark_definition: str
    benchmark: dict[str, Any] = Field(default_factory=dict)
    cost_definition: str
    cost_model: dict[str, Any] = Field(default_factory=dict)
    equity_curve: list[dict[str, Any]] = Field(default_factory=list)
    drawdown_stats: dict[str, Any] = Field(default_factory=dict)
    risk_stats: dict[str, Any] = Field(default_factory=dict)
    turnover_stats: dict[str, Any] = Field(default_factory=dict)
    annualized_return: float | None = None
    annualized_excess_return: float | None = None
    max_drawdown: float | None = None
    sharpe_like_ratio: float | None = None
    turnover: float | None = None
    win_rate_definition: str
    win_rate: float | None = None
    capacity_note: str | None = None
    nav_series_ref: str | None = None
    drawdown_series_ref: str | None = None
    trade_log_ref: str | None = None
    exposure_summary: dict[str, Any] = Field(default_factory=dict)
    stress_period_summary: list[dict[str, Any]] = Field(default_factory=list)


class ReplayAlignmentArtifactView(BaseModel):
    artifact_id: str
    artifact_type: Literal["replay_alignment"] = "replay_alignment"
    manifest_id: str
    recommendation_id: int
    recommendation_key: str
    label_definition: str
    review_window_definition: str
    entry_rule: str
    exit_rule: str
    benchmark_definition: str
    benchmark_context: dict[str, Any] = Field(default_factory=dict)
    hit_definition: str
    stock_return: float | None = None
    benchmark_return: float | None = None
    excess_return: float | None = None
    realized_outcome: dict[str, Any] = Field(default_factory=dict)
    alignment_status: str | None = None
    validation_status: str
    status_note: str | None = None


class ManualResearchArtifactView(BaseModel):
    artifact_id: str
    artifact_type: Literal["manual_review"] = "manual_review"
    recommendation_key: str
    stock_symbol: str
    stock_name: str
    generated_at: datetime
    question: str
    prompt: str
    answer: str
    selected_key: dict[str, Any] = Field(default_factory=dict)
    attempted_keys: list[dict[str, Any]] = Field(default_factory=list)
    failover_used: bool = False
    validation_artifact_id: str | None = None
    validation_manifest_id: str | None = None
    target_horizon_label: str | None = None
    source_packet: list[str] = Field(default_factory=list)
    review_verdict: str | None = None
    summary: str | None = None
    risks: list[str] = Field(default_factory=list)
    disagreements: list[str] = Field(default_factory=list)
    decision_note: str | None = None
    citations: list[str] = Field(default_factory=list)
    request_key: str | None = None
    executor_kind: str | None = None
    requested_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class Phase5HorizonStudyArtifactView(BaseModel):
    artifact_id: str
    artifact_type: Literal["phase5_horizon_study"] = "phase5_horizon_study"
    generated_at: datetime
    created_at: datetime | None = None
    scope: dict[str, Any] = Field(default_factory=dict)
    contract_version: str
    required_benchmark_definition: str
    primary_horizon_status: str
    summary: dict[str, Any] = Field(default_factory=dict)
    leaderboard: list[dict[str, Any]] = Field(default_factory=list)
    pairwise_net_excess: list[dict[str, Any]] = Field(default_factory=list)
    time_stability: dict[str, Any] = Field(default_factory=dict)
    decision: dict[str, Any] = Field(default_factory=dict)
    records: list[dict[str, Any]] = Field(default_factory=list)


class Phase5HoldingPolicyStudyArtifactView(BaseModel):
    artifact_id: str
    artifact_type: Literal["phase5_holding_policy_study"] = "phase5_holding_policy_study"
    generated_at: datetime
    created_at: datetime | None = None
    scope: dict[str, Any] = Field(default_factory=dict)
    contract_version: str
    policy_type: str
    action_definition: str
    quantity_definition: str
    required_benchmark_definition: str
    summary: dict[str, Any] = Field(default_factory=dict)
    cost_sensitivity: dict[str, Any] = Field(default_factory=dict)
    holding_stability: dict[str, Any] = Field(default_factory=dict)
    decision: dict[str, Any] = Field(default_factory=dict)
    portfolios: list[dict[str, Any]] = Field(default_factory=list)


class Phase5HoldingPolicyExperimentArtifactView(BaseModel):
    artifact_id: str
    artifact_type: Literal["phase5_holding_policy_experiment"] = "phase5_holding_policy_experiment"
    generated_at: datetime
    created_at: datetime | None = None
    scope: dict[str, Any] = Field(default_factory=dict)
    contract_version: str
    policy_type: str
    action_definition: str
    quantity_definition: str
    required_benchmark_definition: str
    experiment_id: str
    experiment_version: str
    experiment_definition: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)
    decision: dict[str, Any] = Field(default_factory=dict)
    variants: list[dict[str, Any]] = Field(default_factory=list)


class Phase5ProducerContractStudyArtifactView(BaseModel):
    artifact_id: str
    artifact_type: Literal["phase5_producer_contract_study"] = "phase5_producer_contract_study"
    generated_at: datetime
    created_at: datetime | None = None
    scope: dict[str, Any] = Field(default_factory=dict)
    contract_version: str
    summary: dict[str, Any] = Field(default_factory=dict)
    variants: list[dict[str, Any]] = Field(default_factory=list)
    symbol_analysis: list[dict[str, Any]] = Field(default_factory=list)
    focus_records: list[dict[str, Any]] = Field(default_factory=list)
    decision: dict[str, Any] = Field(default_factory=dict)


ARTIFACT_BACKED_STATUSES = {
    STATUS_RESEARCH_CANDIDATE,
    STATUS_VERIFIED,
}


def validation_status_is_artifact_backed(status: str | None) -> bool:
    return status in ARTIFACT_BACKED_STATUSES


def normalize_product_validation_status(
    *,
    artifact_type: ArtifactType,
    status: str | None,
    note: str | None,
    artifact_id: str | None,
    manifest_id: str | None,
    benchmark_definition: str | None = None,
    cost_definition: str | None = None,
    execution_assumptions: str | None = None,
    sample_count: int | None = None,
    coverage_ratio: float | None = None,
    turnover_mean: float | None = None,
) -> tuple[str, str | None]:
    normalized_status = status or STATUS_PENDING_REBUILD
    if normalized_status in {STATUS_PENDING_REBUILD, STATUS_SYNTHETIC_DEMO}:
        return normalized_status, note
    if normalized_status not in {STATUS_RESEARCH_CANDIDATE, STATUS_VERIFIED}:
        return normalized_status, note

    blockers: list[str] = []
    if not artifact_id:
        blockers.append("missing artifact_id")
    if not manifest_id:
        blockers.append("missing manifest_id")
    if benchmark_definition in {None, "", "pending_rebuild", "synthetic_demo"}:
        blockers.append("benchmark_definition not approved")
    if artifact_type in {"rolling_validation", "portfolio_backtest", "validation_metrics"} and not cost_definition:
        blockers.append("missing cost_definition")
    if artifact_type == "portfolio_backtest" and not execution_assumptions:
        blockers.append("missing execution_assumptions")
    if artifact_type == "validation_metrics":
        if sample_count is None:
            blockers.append("missing sample_count")
        if coverage_ratio is None:
            blockers.append("missing coverage_ratio")
        if turnover_mean is None:
            blockers.append("missing turnover_mean")

    if not blockers:
        return normalized_status, note

    blocker_text = ", ".join(blockers)
    downgraded_note = (
        note
        or f"validated projection downgraded to pending_rebuild: artifact contract incomplete ({blocker_text})."
    )
    return STATUS_PENDING_REBUILD, downgraded_note
