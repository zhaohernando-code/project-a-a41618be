from __future__ import annotations

from math import ceil
from typing import Any

from ashare_evidence.contract_status import STATUS_RESEARCH_CANDIDATE
from ashare_evidence.phase2.constants import PHASE2_HORIZONS

PHASE5_CONTRACT_VERSION = "phase5-validation-policy-contract-v1"
PHASE5_RESEARCH_UNIVERSE_DEFINITION = "active_watchlist_full_history_research_universe"
PHASE5_RESEARCH_UNIVERSE_RULE = (
    "phase5_research_validation_uses_full_symbol_history_with_point_in_time_availability;"
    "watchlist_tracking_metrics_remain_join_date_forward_only"
)
PHASE5_PRIMARY_RESEARCH_BENCHMARK = "active_watchlist_equal_weight_proxy"
PHASE5_DIAGNOSTIC_RESEARCH_BENCHMARK = "active_watchlist_equal_weight_proxy"
PHASE5_EXTERNAL_RESEARCH_BENCHMARKS = ("CSI300", "CSI500", "CSI1000")
PHASE5_APPROVED_BENCHMARK_SELECTION_STATUS = "pending_external_index_bar_backfill"
PHASE5_PRIMARY_RESEARCH_BENCHMARK_WITH_SECTOR_PROXY = (
    f"{PHASE5_PRIMARY_RESEARCH_BENCHMARK} + primary_sector_equal_weight_proxy"
)
PHASE5_PRIMARY_RESEARCH_BENCHMARK_MEMBERSHIP_RULE = "expanding_active_watchlist_join_date_forward_only"
PHASE5_MARKET_REFERENCE_BENCHMARK = "CSI300"
PHASE5_PRIMARY_HORIZON_STATUS = "pending_phase5_selection"
PHASE5_ROLLING_WINDOW_BASELINE = {
    "train_days": 480,
    "validation_days": 120,
    "test_days": 60,
}
PHASE5_ROLLING_SPLIT_RULE = "walk_forward_train_480d_validation_120d_test_60d_daily_decision"
PHASE5_REQUIRED_OBSERVATION_COUNT = sum(PHASE5_ROLLING_WINDOW_BASELINE.values())
PHASE5_REQUIRED_BAR_COUNT = PHASE5_REQUIRED_OBSERVATION_COUNT + max(PHASE2_HORIZONS) * 2
PHASE5_MARKET_HISTORY_LOOKBACK_DAYS = ceil(PHASE5_REQUIRED_BAR_COUNT * 1.5)
PHASE5_LLM_ANALYSIS_SCOPE = "manual_triggered_structured_context_analysis_only"
PHASE5_SIMULATION_POLICY = "phase5_simulation_topk_equal_weight_v1"
PHASE5_SIMULATION_EXECUTION_SCOPE = "simulation_only_auto_execution_no_real_order_routing"
PHASE5_SIMULATION_POLICY_LABEL = "等权组合研究策略"
PHASE5_ACTION_DEFINITION = "delta_to_constrained_target_weight_portfolio"
PHASE5_QUANTITY_DEFINITION = "board_lot_delta_to_target_weight"
PHASE5_MAX_POSITION_COUNT = 5
PHASE5_MAX_SINGLE_WEIGHT = 0.20
PHASE5_BOARD_LOT = 100
PHASE5_LONG_DIRECTIONS = {"buy", "watch"}
PHASE5_SELL_DIRECTIONS = {"reduce", "risk_alert"}
PHASE5_POLICY_NOTE = (
    "模型轨道仅在模拟盘按等权规则自动调仓，不会触发真实交易。"
)
PHASE5_AUTO_EXECUTION_NOTE = (
    "自动执行仅作用于 Web 模拟盘，不会触发真实下单。"
)
PHASE5_HOLDING_POLICY_PROMOTION_GATE_VERSION = "phase5-holding-policy-promotion-gate-draft-v1"
PHASE5_HOLDING_POLICY_PROMOTION_GUARDRAILS = {
    "min_rebalance_date_count": 8,
    "min_included_portfolio_count": 3,
    "min_mean_active_position_count": 3,
    "min_mean_invested_ratio": 0.3,
    "min_mean_annualized_excess_return_after_baseline_cost": 0.0,
    "min_positive_after_baseline_cost_portfolio_ratio": 0.5,
    "min_sharpe_like_ratio": 0.0,
    "max_mean_turnover": 0.35,
    "min_mean_rebalance_interval_days": 5.0,
    "max_drawdown_floor": -0.15,
}
PHASE5_HOLDING_POLICY_GOVERNANCE_VERSION = "phase5-holding-policy-governance-draft-v1"
PHASE5_HOLDING_POLICY_REDESIGN_TRIGGER_GATE_IDS = (
    "after_cost_excess_non_negative",
    "positive_after_cost_portfolio_ratio",
)
PHASE5_HOLDING_POLICY_REDESIGN_DIAGNOSTIC_VERSION = (
    "phase5-holding-policy-redesign-diagnostics-draft-v2"
)
PHASE5_HOLDING_POLICY_REDESIGN_SIGNAL_RULES = {
    "after_cost_excess_non_negative": {
        "metric": "cost_sensitivity.mean_annualized_excess_return_after_baseline_cost",
        "comparison": ">=",
        "threshold": 0.0,
        "focus_area": "after_cost_profitability",
        "note": "after-cost excess return remains negative, so the current baseline is not investable enough to discuss promotion.",
    },
    "positive_after_cost_portfolio_ratio": {
        "metric": "cost_sensitivity.positive_after_baseline_cost_portfolio_ratio",
        "comparison": ">=",
        "threshold": 0.5,
        "focus_area": "after_cost_profitability",
        "note": "too few portfolios stay positive after baseline cost, so any apparent edge is not broad enough yet.",
    },
    "mean_invested_ratio_floor": {
        "metric": "summary.mean_invested_ratio",
        "comparison": ">=",
        "threshold": 0.4,
        "focus_area": "portfolio_construction",
        "note": "the portfolio stays under-invested too often, which points to weak capital deployment rather than a healthy top-k policy.",
    },
    "mean_active_position_count_floor": {
        "metric": "summary.mean_active_position_count",
        "comparison": ">=",
        "threshold": 2.0,
        "focus_area": "portfolio_construction",
        "note": "the baseline is not reaching enough active positions to behave like a credible diversified holding policy.",
    },
}
PHASE5_HOLDING_POLICY_REDESIGN_EXPERIMENT_MENU = {
    "profitability_signal_threshold_sweep_v1": {
        "focus_area": "after_cost_profitability",
        "priority": 1,
        "trigger_signal_ids": [
            "after_cost_excess_non_negative",
            "positive_after_cost_portfolio_ratio",
        ],
        "hypothesis": (
            "the current auto-model baseline is deploying on too many weak-ranked long candidates, "
            "so a stricter entry threshold may improve after-cost edge breadth."
        ),
        "proposed_policy_changes": [
            "sweep tighter entry thresholds on recommendation confidence / rank before a symbol can enter the target portfolio",
            "compare whether stronger-entry-only variants improve mean after-cost excess return and positive-after-cost portfolio ratio",
        ],
        "target_metrics": [
            "cost_sensitivity.mean_annualized_excess_return_after_baseline_cost",
            "cost_sensitivity.positive_after_baseline_cost_portfolio_ratio",
            "summary.mean_turnover",
        ],
    },
    "profitability_rebalance_hold_band_v1": {
        "focus_area": "after_cost_profitability",
        "priority": 2,
        "trigger_signal_ids": [
            "after_cost_excess_non_negative",
            "positive_after_cost_portfolio_ratio",
        ],
        "hypothesis": (
            "the equal-weight baseline may be giving up too much edge by rebalancing on small ranking changes, "
            "so a hold-band or minimum delta rule could preserve net returns after cost."
        ),
        "proposed_policy_changes": [
            "test a rebalance hold-band so small score or target-weight changes do not trigger trades",
            "compare whether turnover-adjusted variants preserve more after-cost excess without collapsing exposure",
        ],
        "target_metrics": [
            "cost_sensitivity.mean_annualized_excess_return_after_baseline_cost",
            "summary.mean_turnover",
            "holding_stability.mean_rebalance_interval_days",
        ],
    },
    "construction_max_position_count_sweep_v1": {
        "focus_area": "portfolio_construction",
        "priority": 1,
        "trigger_signal_ids": [
            "mean_invested_ratio_floor",
            "mean_active_position_count_floor",
        ],
        "hypothesis": (
            "the current top-k equal-weight cap may be too narrow for real watchlist coverage, "
            "so varying position count and per-name weight could improve deployed exposure."
        ),
        "proposed_policy_changes": [
            "compare broader max-position-count settings instead of fixing the research baseline at top-5 only",
            "pair each capacity setting with compatible single-name weight caps and observe whether exposure improves without collapsing returns",
        ],
        "target_metrics": [
            "summary.mean_invested_ratio",
            "summary.mean_active_position_count",
            "cost_sensitivity.mean_annualized_excess_return_after_baseline_cost",
        ],
    },
    "construction_deployment_floor_fallback_v1": {
        "focus_area": "portfolio_construction",
        "priority": 2,
        "trigger_signal_ids": [
            "mean_invested_ratio_floor",
            "mean_active_position_count_floor",
        ],
        "hypothesis": (
            "the baseline may be leaving too much cash undeployed when the ideal equal-weight target cannot fill naturally, "
            "so a deployment-floor fallback may convert valid signals into actual positions more reliably."
        ),
        "proposed_policy_changes": [
            "test a minimum deployment rule that fills additional eligible names when the target portfolio stays too sparse",
            "inspect board-lot and affordability-driven underdeployment rather than assuming cash drag is acceptable",
        ],
        "target_metrics": [
            "summary.mean_invested_ratio",
            "summary.mean_active_position_count",
            "cost_sensitivity.mean_annualized_excess_return_after_baseline_cost",
        ],
    },
}


def phase5_benchmark_definition(*, market_proxy: bool, sector_proxy: bool) -> str:
    if market_proxy and sector_proxy:
        return PHASE5_PRIMARY_RESEARCH_BENCHMARK_WITH_SECTOR_PROXY
    if market_proxy:
        return PHASE5_PRIMARY_RESEARCH_BENCHMARK
    return "phase2_single_symbol_absolute_return_fallback"


def phase5_matches_primary_benchmark(benchmark_definition: str | None) -> bool:
    if benchmark_definition is None:
        return False
    normalized = str(benchmark_definition).strip()
    return normalized in {
        PHASE5_PRIMARY_RESEARCH_BENCHMARK,
        PHASE5_PRIMARY_RESEARCH_BENCHMARK_WITH_SECTOR_PROXY,
    }


def phase5_research_contract_context() -> dict[str, Any]:
    return {
        "contract_version": PHASE5_CONTRACT_VERSION,
        "research_validation_scope": "full_symbol_history",
        "watchlist_tracking_scope": "join_date_forward_only",
        "primary_research_benchmark": PHASE5_PRIMARY_RESEARCH_BENCHMARK,
        "primary_research_benchmark_membership_rule": PHASE5_PRIMARY_RESEARCH_BENCHMARK_MEMBERSHIP_RULE,
        "accepted_primary_benchmark_definitions": [
            PHASE5_PRIMARY_RESEARCH_BENCHMARK,
            PHASE5_PRIMARY_RESEARCH_BENCHMARK_WITH_SECTOR_PROXY,
        ],
        "market_reference_benchmark": PHASE5_MARKET_REFERENCE_BENCHMARK,
        "candidate_label_horizons": list(PHASE2_HORIZONS),
        "primary_horizon_status": PHASE5_PRIMARY_HORIZON_STATUS,
        "rolling_split_baseline": dict(PHASE5_ROLLING_WINDOW_BASELINE),
        "rolling_split_rule": PHASE5_ROLLING_SPLIT_RULE,
        "required_history": {
            "required_observation_count": PHASE5_REQUIRED_OBSERVATION_COUNT,
            "required_bar_count": PHASE5_REQUIRED_BAR_COUNT,
            "market_history_lookback_days": PHASE5_MARKET_HISTORY_LOOKBACK_DAYS,
        },
        "llm_analysis_scope": PHASE5_LLM_ANALYSIS_SCOPE,
        "simulation_execution_scope": PHASE5_SIMULATION_EXECUTION_SCOPE,
        "simulation_policy_type": PHASE5_SIMULATION_POLICY,
        "simulation_policy_constraints": {
            "max_position_count": PHASE5_MAX_POSITION_COUNT,
            "max_single_weight": PHASE5_MAX_SINGLE_WEIGHT,
            "board_lot": PHASE5_BOARD_LOT,
            "cash_allowed": True,
        },
    }


def phase5_simulation_policy_context(*, policy_note: str | None = None) -> dict[str, Any]:
    return {
        "policy_status": STATUS_RESEARCH_CANDIDATE,
        "policy_type": PHASE5_SIMULATION_POLICY,
        "policy_label": PHASE5_SIMULATION_POLICY_LABEL,
        "policy_note": policy_note or PHASE5_POLICY_NOTE,
        "action_definition": PHASE5_ACTION_DEFINITION,
        "quantity_definition": PHASE5_QUANTITY_DEFINITION,
        "simulation_execution_scope": PHASE5_SIMULATION_EXECUTION_SCOPE,
        "simulation_policy_constraints": {
            "max_position_count": PHASE5_MAX_POSITION_COUNT,
            "max_single_weight": PHASE5_MAX_SINGLE_WEIGHT,
            "board_lot": PHASE5_BOARD_LOT,
            "cash_allowed": True,
        },
    }


def phase5_auto_execution_context() -> dict[str, Any]:
    return {
        "auto_execute_status": STATUS_RESEARCH_CANDIDATE,
        "auto_execute_note": PHASE5_AUTO_EXECUTION_NOTE,
        "simulation_execution_scope": PHASE5_SIMULATION_EXECUTION_SCOPE,
    }


def phase5_benchmark_context(
    *,
    market_proxy: bool,
    sector_proxy: bool,
    sector_code: str | None = None,
) -> dict[str, Any]:
    return {
        "contract_version": PHASE5_CONTRACT_VERSION,
        "primary_research_benchmark": PHASE5_PRIMARY_RESEARCH_BENCHMARK,
        "primary_research_benchmark_membership_rule": PHASE5_PRIMARY_RESEARCH_BENCHMARK_MEMBERSHIP_RULE,
        "accepted_primary_benchmark_definitions": [
            PHASE5_PRIMARY_RESEARCH_BENCHMARK,
            PHASE5_PRIMARY_RESEARCH_BENCHMARK_WITH_SECTOR_PROXY,
        ],
        "market_reference_benchmark": PHASE5_MARKET_REFERENCE_BENCHMARK,
        "market_proxy": market_proxy,
        "sector_proxy": sector_proxy,
        "sector_code": sector_code,
        "research_validation_scope": "full_symbol_history",
        "watchlist_tracking_scope": "join_date_forward_only",
    }


def phase5_holding_policy_promotion_gate_context() -> dict[str, Any]:
    return {
        "gate_version": PHASE5_HOLDING_POLICY_PROMOTION_GATE_VERSION,
        "status": "draft_not_yet_operator_approved",
        "guardrails": dict(PHASE5_HOLDING_POLICY_PROMOTION_GUARDRAILS),
        "note": (
            "This draft gate is a research diagnostic for Phase 5 simulation-policy promotion. "
            "Passing it does not auto-promote the policy, and failing it should keep the policy "
            "at research_candidate_only or trigger redesign."
        ),
    }


def phase5_holding_policy_governance_context() -> dict[str, Any]:
    return {
        "governance_version": PHASE5_HOLDING_POLICY_GOVERNANCE_VERSION,
        "status": "draft_not_yet_operator_approved",
        "redesign_trigger_gate_ids": list(PHASE5_HOLDING_POLICY_REDESIGN_TRIGGER_GATE_IDS),
        "note": (
            "This draft governance readout translates gate results into the current default "
            "Phase 5 handling: keep the policy non-promoted, gather more evidence, or prioritize redesign. "
            "It is a research governance helper, not an operator-approved auto-promotion rule."
        ),
    }


def phase5_holding_policy_redesign_diagnostic_context() -> dict[str, Any]:
    return {
        "diagnostic_version": PHASE5_HOLDING_POLICY_REDESIGN_DIAGNOSTIC_VERSION,
        "status": "draft_not_yet_operator_approved",
        "signals": {
            signal_id: dict(rule)
            for signal_id, rule in PHASE5_HOLDING_POLICY_REDESIGN_SIGNAL_RULES.items()
        },
        "experiment_menu": {
            experiment_id: dict(experiment)
            for experiment_id, experiment in PHASE5_HOLDING_POLICY_REDESIGN_EXPERIMENT_MENU.items()
        },
        "note": (
            "This draft redesign diagnostic readout explains why the current Phase 5 simulation "
            "baseline should stay non-promoted, where redesign work should begin, and which draft "
            "research experiments should be prioritized first. "
            "It is a research prioritization helper, not an operator-approved policy spec."
        ),
    }
