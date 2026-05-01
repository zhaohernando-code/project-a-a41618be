from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ashare_evidence.models import PaperOrder, PaperPortfolio
from ashare_evidence.phase2.common import safe_mean
from ashare_evidence.phase2.constants import PHASE2_COST_MODEL
from ashare_evidence.phase2.phase5_contract import (
    PHASE5_ACTION_DEFINITION,
    PHASE5_CONTRACT_VERSION,
    PHASE5_HOLDING_POLICY_PROMOTION_GATE_VERSION,
    PHASE5_HOLDING_POLICY_PROMOTION_GUARDRAILS,
    PHASE5_HOLDING_POLICY_REDESIGN_DIAGNOSTIC_VERSION,
    PHASE5_HOLDING_POLICY_REDESIGN_EXPERIMENT_MENU,
    PHASE5_HOLDING_POLICY_REDESIGN_SIGNAL_RULES,
    PHASE5_HOLDING_POLICY_REDESIGN_TRIGGER_GATE_IDS,
    PHASE5_PRIMARY_RESEARCH_BENCHMARK,
    PHASE5_QUANTITY_DEFINITION,
    PHASE5_SIMULATION_POLICY,
    phase5_holding_policy_governance_context,
    phase5_holding_policy_promotion_gate_context,
    phase5_holding_policy_redesign_diagnostic_context,
    phase5_matches_primary_benchmark,
)
from ashare_evidence.research_artifact_store import (
    artifact_root_from_database_url,
    resolve_backtest_artifact,
)
from ashare_evidence.research_artifacts import (
    Phase5HoldingPolicyStudyArtifactView,
    normalize_product_validation_status,
)


def _mean_or_none(values: list[float | None]) -> float | None:
    filtered = [float(item) for item in values if item is not None]
    if not filtered:
        return None
    return round(safe_mean(filtered), 6)


def _cost_drag(turnover: float | None, round_trip_cost_bps: float | None) -> float | None:
    if turnover is None or round_trip_cost_bps is None:
        return None
    return round(float(turnover) * float(round_trip_cost_bps) / 10000.0, 6)


def _after_cost_excess_return(
    annualized_excess_return: float | None,
    turnover: float | None,
    round_trip_cost_bps: float | None,
) -> float | None:
    if annualized_excess_return is None:
        return None
    drag = _cost_drag(turnover, round_trip_cost_bps)
    if drag is None:
        return None
    return round(float(annualized_excess_return) - drag, 6)


def _break_even_cost_bps(annualized_excess_return: float | None, turnover: float | None) -> float | None:
    if annualized_excess_return is None or turnover in {None, 0}:
        return None
    return round(float(annualized_excess_return) / float(turnover) * 10000.0, 6)


def _mean_rebalance_interval_days(rebalance_days: list[date]) -> float | None:
    ordered = sorted(set(rebalance_days))
    if len(ordered) < 2:
        return None
    gaps = [(right - left).days for left, right in zip(ordered, ordered[1:])]
    return round(safe_mean(gaps), 6) if gaps else None


def _positive_after_cost_portfolio_ratio(
    *,
    included_portfolio_count: int | None,
    positive_after_cost_count: int | None,
) -> float | None:
    if included_portfolio_count in {None, 0} or positive_after_cost_count is None:
        return None
    return round(float(positive_after_cost_count) / float(included_portfolio_count), 6)


def _artifact_root_for_session(session: Session, artifact_root: Path | None = None) -> Path:
    if artifact_root is not None:
        return Path(artifact_root)
    bind = session.get_bind()
    return artifact_root_from_database_url(bind.url.render_as_string(hide_password=False) if bind else None)


def _at_least_gate(
    gate_id: str,
    *,
    actual: float | int | None,
    threshold: float | int,
    metric: str,
) -> dict[str, Any]:
    if actual is None:
        return {
            "gate_id": gate_id,
            "metric": metric,
            "status": "insufficient_evidence",
            "comparison": ">=",
            "threshold": threshold,
            "actual": None,
        }
    actual_value = float(actual)
    threshold_value = float(threshold)
    return {
        "gate_id": gate_id,
        "metric": metric,
        "status": "pass" if actual_value >= threshold_value else "fail",
        "comparison": ">=",
        "threshold": threshold_value,
        "actual": round(actual_value, 6),
    }


def _at_most_gate(
    gate_id: str,
    *,
    actual: float | int | None,
    threshold: float | int,
    metric: str,
) -> dict[str, Any]:
    if actual is None:
        return {
            "gate_id": gate_id,
            "metric": metric,
            "status": "insufficient_evidence",
            "comparison": "<=",
            "threshold": threshold,
            "actual": None,
        }
    actual_value = float(actual)
    threshold_value = float(threshold)
    return {
        "gate_id": gate_id,
        "metric": metric,
        "status": "pass" if actual_value <= threshold_value else "fail",
        "comparison": "<=",
        "threshold": threshold_value,
        "actual": round(actual_value, 6),
    }


def evaluate_phase5_holding_policy_promotion_gate(
    *,
    summary: dict[str, Any],
    cost_sensitivity: dict[str, Any],
    holding_stability: dict[str, Any],
) -> dict[str, Any]:
    guardrails = dict(PHASE5_HOLDING_POLICY_PROMOTION_GUARDRAILS)
    included_portfolio_count = summary.get("included_portfolio_count")
    positive_after_cost_count = cost_sensitivity.get("positive_after_baseline_cost_portfolio_count")
    positive_ratio = _positive_after_cost_portfolio_ratio(
        included_portfolio_count=included_portfolio_count,
        positive_after_cost_count=positive_after_cost_count,
    )

    checks = [
        _at_least_gate(
            "included_portfolio_count",
            actual=included_portfolio_count,
            threshold=guardrails["min_included_portfolio_count"],
            metric="summary.included_portfolio_count",
        ),
        _at_least_gate(
            "after_cost_excess_non_negative",
            actual=cost_sensitivity.get("mean_annualized_excess_return_after_baseline_cost"),
            threshold=guardrails["min_mean_annualized_excess_return_after_baseline_cost"],
            metric="cost_sensitivity.mean_annualized_excess_return_after_baseline_cost",
        ),
        _at_least_gate(
            "positive_after_cost_portfolio_ratio",
            actual=positive_ratio,
            threshold=guardrails["min_positive_after_baseline_cost_portfolio_ratio"],
            metric="cost_sensitivity.positive_after_baseline_cost_portfolio_ratio",
        ),
        _at_most_gate(
            "mean_turnover_ceiling",
            actual=summary.get("mean_turnover"),
            threshold=guardrails["max_mean_turnover"],
            metric="summary.mean_turnover",
        ),
        _at_least_gate(
            "mean_rebalance_interval_days_floor",
            actual=holding_stability.get("mean_rebalance_interval_days"),
            threshold=guardrails["min_mean_rebalance_interval_days"],
            metric="holding_stability.mean_rebalance_interval_days",
        ),
    ]
    if any(
        key in summary
        for key in ("rebalance_day_count", "mean_active_position_count", "mean_invested_ratio", "mean_max_drawdown")
    ):
        checks.extend(
            [
                _at_least_gate(
                    "rebalance_date_count",
                    actual=summary.get("rebalance_day_count"),
                    threshold=guardrails["min_rebalance_date_count"],
                    metric="summary.rebalance_day_count",
                ),
                _at_least_gate(
                    "mean_active_position_count",
                    actual=summary.get("mean_active_position_count"),
                    threshold=guardrails["min_mean_active_position_count"],
                    metric="summary.mean_active_position_count",
                ),
                _at_least_gate(
                    "mean_invested_ratio",
                    actual=summary.get("mean_invested_ratio"),
                    threshold=guardrails["min_mean_invested_ratio"],
                    metric="summary.mean_invested_ratio",
                ),
                _at_least_gate(
                    "max_drawdown_floor",
                    actual=summary.get("mean_max_drawdown"),
                    threshold=guardrails["max_drawdown_floor"],
                    metric="summary.mean_max_drawdown",
                ),
            ]
        )
    failing_gate_ids = [str(item["gate_id"]) for item in checks if item["status"] == "fail"]
    incomplete_gate_ids = [str(item["gate_id"]) for item in checks if item["status"] == "insufficient_evidence"]
    if incomplete_gate_ids:
        gate_status = "draft_gate_insufficient_evidence"
    elif failing_gate_ids:
        gate_status = "draft_gate_blocked"
    else:
        gate_status = "draft_gate_passed_pending_approval"
    return {
        "gate_version": PHASE5_HOLDING_POLICY_PROMOTION_GATE_VERSION,
        "gate_status": gate_status,
        "guardrails": guardrails,
        "checks": checks,
        "failing_gate_ids": failing_gate_ids,
        "incomplete_gate_ids": incomplete_gate_ids,
        "positive_after_baseline_cost_portfolio_ratio": positive_ratio,
    }


def evaluate_phase5_holding_policy_governance(*, gate: dict[str, Any]) -> dict[str, Any]:
    gate_status = str(gate.get("gate_status") or "draft_gate_insufficient_evidence")
    failing_gate_ids = [str(item) for item in gate.get("failing_gate_ids") or []]
    incomplete_gate_ids = [str(item) for item in gate.get("incomplete_gate_ids") or []]
    redesign_trigger_gate_ids = [
        gate_id
        for gate_id in failing_gate_ids
        if gate_id in PHASE5_HOLDING_POLICY_REDESIGN_TRIGGER_GATE_IDS
    ]
    if gate_status == "draft_gate_passed_pending_approval":
        governance_status = "await_operator_promotion_decision"
        governance_action = "keep_simulation_only_pending_operator_approval"
        governance_note = (
            "当前 draft gate 已通过，但这仍不代表策略可以自动晋级；"
            "baseline 继续维持 simulation-only，等待 operator 明确批准。"
        )
    elif incomplete_gate_ids:
        governance_status = "maintain_non_promotion_collect_more_evidence"
        governance_action = "collect_more_evidence_before_promotion_review"
        governance_note = (
            "当前证据仍不足，默认治理动作是维持 non-promotion 并继续补充研究样本，"
            "而不是提前讨论 promotion。"
        )
    elif redesign_trigger_gate_ids:
        governance_status = "maintain_non_promotion_prioritize_policy_redesign"
        governance_action = "prioritize_policy_redesign"
        governance_note = (
            "当前 blocker 已触发 profitability/redesign 信号；默认治理动作是维持 non-promotion，"
            "并优先进入 policy redesign，而不是继续把 gate 形式化当成主要工作。"
        )
    else:
        governance_status = "maintain_non_promotion_until_gate_passes"
        governance_action = "continue_gate_research_without_promotion"
        governance_note = (
            "当前 draft gate 仍未通过，但 blocker 还没有强到直接指向 redesign；"
            "默认治理动作是继续 non-promotion 并迭代研究证据。"
        )
    return {
        "governance_status": governance_status,
        "governance_action": governance_action,
        "governance_note": governance_note,
        "redesign_trigger_gate_ids": redesign_trigger_gate_ids,
    }


def evaluate_phase5_holding_policy_redesign_diagnostics(
    *,
    summary: dict[str, Any],
    cost_sensitivity: dict[str, Any],
    gate: dict[str, Any],
    governance: dict[str, Any],
) -> dict[str, Any]:
    included_portfolio_count = summary.get("included_portfolio_count")
    positive_ratio = _positive_after_cost_portfolio_ratio(
        included_portfolio_count=included_portfolio_count,
        positive_after_cost_count=cost_sensitivity.get("positive_after_baseline_cost_portfolio_count"),
    )
    signal_actuals: dict[str, float | int | None] = {
        "after_cost_excess_non_negative": cost_sensitivity.get(
            "mean_annualized_excess_return_after_baseline_cost"
        ),
        "positive_after_cost_portfolio_ratio": positive_ratio,
        "mean_invested_ratio_floor": summary.get("mean_invested_ratio"),
        "mean_active_position_count_floor": summary.get("mean_active_position_count"),
    }
    diagnostics: list[dict[str, Any]] = []
    focus_areas: list[str] = []
    for signal_id, rule in PHASE5_HOLDING_POLICY_REDESIGN_SIGNAL_RULES.items():
        diagnostic = _at_least_gate(
            signal_id,
            actual=signal_actuals.get(signal_id),
            threshold=rule["threshold"],
            metric=rule["metric"],
        )
        diagnostic["focus_area"] = rule["focus_area"]
        diagnostic["note"] = rule["note"]
        diagnostics.append(diagnostic)
        if diagnostic["status"] == "fail" and rule["focus_area"] not in focus_areas:
            focus_areas.append(str(rule["focus_area"]))

    triggered_signal_ids = [str(item["gate_id"]) for item in diagnostics if item["status"] == "fail"]
    incomplete_signal_ids = [str(item["gate_id"]) for item in diagnostics if item["status"] == "insufficient_evidence"]
    governance_action = str(governance.get("governance_action") or "")
    if not triggered_signal_ids and not incomplete_signal_ids:
        redesign_status = "no_structured_redesign_signal"
        redesign_note = (
            "当前还没有结构化 redesign signal；若未来 gate 再次阻断，应重新审查 allocation 与 exposure 诊断。"
        )
    elif governance_action == "prioritize_policy_redesign":
        redesign_status = "prioritize_policy_redesign"
        redesign_note = (
            "当前 baseline 已同时暴露 after-cost profitability 与持仓暴露侧的结构化 redesign signals；"
            "下一步应优先重做 portfolio construction / exposure policy，而不是继续只补 gate 文案。"
        )
    elif triggered_signal_ids:
        redesign_status = "redesign_signals_present"
        redesign_note = (
            "当前已有结构化 redesign signal，但治理动作尚未提升到 prioritize_policy_redesign；"
            "后续应继续观察这些信号是否持续存在。"
        )
    else:
        redesign_status = "insufficient_redesign_evidence"
        redesign_note = (
            "当前 redesign 诊断证据仍不足，先补更多 artifact-backed sample，再判断是否要进入 redesign。"
        )
    return {
        "diagnostic_version": PHASE5_HOLDING_POLICY_REDESIGN_DIAGNOSTIC_VERSION,
        "redesign_status": redesign_status,
        "redesign_note": redesign_note,
        "diagnostics": diagnostics,
        "triggered_signal_ids": triggered_signal_ids,
        "incomplete_signal_ids": incomplete_signal_ids,
        "focus_areas": focus_areas,
        "positive_after_baseline_cost_portfolio_ratio": positive_ratio,
    }


def recommend_phase5_holding_policy_redesign_experiments(
    *,
    redesign: dict[str, Any],
) -> dict[str, Any]:
    focus_areas = [str(item) for item in redesign.get("focus_areas") or []]
    triggered_signal_ids = {str(item) for item in redesign.get("triggered_signal_ids") or []}
    candidates: list[dict[str, Any]] = []
    primary_ids: list[str] = []
    seen_primary_focus_areas: set[str] = set()

    for experiment_id, experiment in PHASE5_HOLDING_POLICY_REDESIGN_EXPERIMENT_MENU.items():
        experiment_focus = str(experiment["focus_area"])
        trigger_matches = sorted(triggered_signal_ids.intersection(experiment.get("trigger_signal_ids") or []))
        if experiment_focus not in focus_areas and not trigger_matches:
            continue
        candidate = {
            "experiment_id": experiment_id,
            "focus_area": experiment_focus,
            "priority": int(experiment["priority"]),
            "trigger_signal_ids": list(experiment.get("trigger_signal_ids") or []),
            "matched_trigger_signal_ids": trigger_matches,
            "hypothesis": experiment["hypothesis"],
            "proposed_policy_changes": list(experiment.get("proposed_policy_changes") or []),
            "target_metrics": list(experiment.get("target_metrics") or []),
            "selection_reason": (
                f"selected because {experiment_focus} is an active redesign focus and "
                f"the current signals include {', '.join(trigger_matches)}."
                if trigger_matches
                else f"selected because {experiment_focus} is an active redesign focus."
            ),
        }
        candidates.append(candidate)
        if experiment_focus not in seen_primary_focus_areas:
            primary_ids.append(experiment_id)
            seen_primary_focus_areas.add(experiment_focus)

    candidates.sort(key=lambda item: (int(item["priority"]), str(item["experiment_id"])))
    return {
        "candidate_count": len(candidates),
        "candidates": candidates,
        "primary_experiment_ids": primary_ids,
    }


def build_phase5_holding_policy_study(
    session: Session,
    *,
    portfolio_keys: Sequence[str] | None = None,
    artifact_root: Path | None = None,
) -> dict[str, Any]:
    selected_keys = list(dict.fromkeys(portfolio_keys or []))
    portfolios = session.scalars(
        select(PaperPortfolio)
        .options(selectinload(PaperPortfolio.orders).selectinload(PaperOrder.fills))
        .where(PaperPortfolio.mode == "auto_model")
        .order_by(PaperPortfolio.name.asc(), PaperPortfolio.portfolio_key.asc())
    ).all()
    default_portfolio_keys = [portfolio.portfolio_key for portfolio in portfolios if portfolio.status != "archived"]
    scope_keys = selected_keys or default_portfolio_keys
    scope_set = set(scope_keys)
    scope_portfolios = [portfolio for portfolio in portfolios if portfolio.portfolio_key in scope_set]
    root = _artifact_root_for_session(session, artifact_root)

    if not scope_portfolios:
        gate = {
            "gate_status": "draft_gate_insufficient_evidence",
            "checks": [],
            "failing_gate_ids": [],
            "incomplete_gate_ids": ["included_portfolio_count"],
        }
        governance = evaluate_phase5_holding_policy_governance(gate=gate)
        redesign = evaluate_phase5_holding_policy_redesign_diagnostics(
            summary={
                "included_portfolio_count": 0,
                "mean_invested_ratio": None,
                "mean_active_position_count": None,
            },
            cost_sensitivity={
                "positive_after_baseline_cost_portfolio_count": None,
                "mean_annualized_excess_return_after_baseline_cost": None,
            },
            gate=gate,
            governance=governance,
        )
        redesign_experiments = recommend_phase5_holding_policy_redesign_experiments(redesign=redesign)
        return {
            "generated_at": datetime.now().astimezone().isoformat(),
            "scope": {
                "portfolio_keys": scope_keys,
                "default_portfolio_keys": default_portfolio_keys,
                "mode": "auto_model",
            },
            "contract_version": PHASE5_CONTRACT_VERSION,
            "policy_type": PHASE5_SIMULATION_POLICY,
            "action_definition": PHASE5_ACTION_DEFINITION,
            "quantity_definition": PHASE5_QUANTITY_DEFINITION,
            "required_benchmark_definition": PHASE5_PRIMARY_RESEARCH_BENCHMARK,
            "summary": {
                "selected_portfolio_count": 0,
                "included_portfolio_count": 0,
                "excluded_portfolio_count": 0,
                "excluded_reasons": {},
            },
            "cost_sensitivity": {
                "baseline_round_trip_cost_bps": float(PHASE2_COST_MODEL["round_trip_cost_bps"]),
            },
            "holding_stability": {
                "portfolio_count": 0,
                "mean_rebalance_day_ratio": None,
                "mean_rebalance_interval_days": None,
            },
            "decision": {
                "approval_state": "no_auto_model_portfolios",
                "note": "当前没有可用于 Phase 5 holding-policy study 的模型自动持仓组合。",
                "gate_status": gate["gate_status"],
                "gate_context": phase5_holding_policy_promotion_gate_context(),
                "gate_checks": list(gate["checks"]),
                "failing_gate_ids": list(gate["failing_gate_ids"]),
                "incomplete_gate_ids": list(gate["incomplete_gate_ids"]),
                "governance_status": governance["governance_status"],
                "governance_action": governance["governance_action"],
                "governance_note": governance["governance_note"],
                "redesign_trigger_gate_ids": governance["redesign_trigger_gate_ids"],
                "governance_context": phase5_holding_policy_governance_context(),
                "redesign_status": redesign["redesign_status"],
                "redesign_note": redesign["redesign_note"],
                "redesign_diagnostics": redesign["diagnostics"],
                "redesign_triggered_signal_ids": redesign["triggered_signal_ids"],
                "redesign_incomplete_signal_ids": redesign["incomplete_signal_ids"],
                "redesign_focus_areas": redesign["focus_areas"],
                "redesign_experiment_candidates": redesign_experiments["candidates"],
                "redesign_primary_experiment_ids": redesign_experiments["primary_experiment_ids"],
                "redesign_context": phase5_holding_policy_redesign_diagnostic_context(),
            },
            "portfolios": [],
        }

    portfolio_rows: list[dict[str, Any]] = []
    included_rows: list[dict[str, Any]] = []
    excluded_reasons: Counter[str] = Counter()
    baseline_cost_bps = float(PHASE2_COST_MODEL["round_trip_cost_bps"])

    for portfolio in scope_portfolios:
        artifact_id, backtest = resolve_backtest_artifact(
            configured_artifact_id=dict(portfolio.portfolio_payload or {}).get("backtest_artifact_id"),
            portfolio_key=portfolio.portfolio_key,
            root=root,
        )
        exclusion_reason: str | None = None
        validation_status = "pending_rebuild"
        validation_note: str | None = None
        validation_manifest_id: str | None = None
        round_trip_cost_bps = baseline_cost_bps
        benchmark_definition: str | None = None
        cost_definition: str | None = None
        annualized_return: float | None = None
        annualized_excess_return: float | None = None
        max_drawdown: float | None = None
        turnover: float | None = None
        win_rate: float | None = None
        invested_ratio: float | None = None
        active_position_count: int | None = None
        observation_day_count = 0
        latest_nav_date: str | None = None
        if backtest is None:
            exclusion_reason = "missing_backtest_artifact"
        else:
            benchmark_definition = backtest.benchmark_definition
            cost_definition = backtest.cost_definition
            validation_manifest_id = backtest.manifest_id
            validation_status, validation_note = normalize_product_validation_status(
                artifact_type="portfolio_backtest",
                status=backtest.status,
                note=backtest.status_note,
                artifact_id=backtest.artifact_id,
                manifest_id=backtest.manifest_id,
                benchmark_definition=backtest.benchmark_definition,
                cost_definition=backtest.cost_definition,
                execution_assumptions=backtest.execution_assumptions,
            )
            cost_model = dict(backtest.cost_model or {})
            round_trip_cost_bps = float(cost_model.get("round_trip_cost_bps") or baseline_cost_bps)
            annualized_return = backtest.annualized_return
            annualized_excess_return = backtest.annualized_excess_return
            max_drawdown = backtest.max_drawdown
            turnover = backtest.turnover
            win_rate = backtest.win_rate
            invested_ratio = float((backtest.exposure_summary or {}).get("invested_ratio")) if (backtest.exposure_summary or {}).get("invested_ratio") is not None else None
            active_position_count = (
                int((backtest.exposure_summary or {}).get("active_position_count"))
                if (backtest.exposure_summary or {}).get("active_position_count") is not None
                else None
            )
            observation_day_count = len(backtest.equity_curve or [])
            if backtest.equity_curve:
                latest_point = backtest.equity_curve[-1]
                trade_date = latest_point.get("trade_date")
                observed_at = latest_point.get("observed_at")
                latest_nav_date = str(trade_date or observed_at or "")
            if not phase5_matches_primary_benchmark(backtest.benchmark_definition):
                exclusion_reason = "benchmark_mismatch"
            elif turnover is None:
                exclusion_reason = "missing_turnover"
            elif annualized_excess_return is None:
                exclusion_reason = "missing_excess_return"

        rebalance_days = sorted({order.requested_at.date() for order in portfolio.orders})
        rebalance_day_count = len(rebalance_days)
        order_count = len(portfolio.orders)
        average_orders_per_rebalance_day = (
            round(order_count / rebalance_day_count, 6)
            if rebalance_day_count
            else None
        )
        rebalance_day_ratio = (
            round(rebalance_day_count / observation_day_count, 6)
            if observation_day_count
            else None
        )
        mean_rebalance_interval_days = _mean_rebalance_interval_days(rebalance_days)
        baseline_cost_drag = _cost_drag(turnover, round_trip_cost_bps)
        annualized_excess_after_cost = _after_cost_excess_return(
            annualized_excess_return,
            turnover,
            round_trip_cost_bps,
        )
        break_even_cost_bps = _break_even_cost_bps(annualized_excess_return, turnover)

        row = {
            "portfolio_key": portfolio.portfolio_key,
            "name": portfolio.name,
            "status": portfolio.status,
            "mode": portfolio.mode,
            "validation_artifact_id": artifact_id,
            "validation_manifest_id": validation_manifest_id,
            "validation_status": validation_status,
            "validation_note": validation_note,
            "benchmark_definition": benchmark_definition,
            "cost_definition": cost_definition,
            "round_trip_cost_bps": round_trip_cost_bps,
            "annualized_return": annualized_return,
            "annualized_excess_return": annualized_excess_return,
            "annualized_excess_return_after_baseline_cost": annualized_excess_after_cost,
            "baseline_cost_drag": baseline_cost_drag,
            "break_even_cost_bps": break_even_cost_bps,
            "max_drawdown": max_drawdown,
            "turnover": turnover,
            "win_rate": win_rate,
            "invested_ratio": invested_ratio,
            "active_position_count": active_position_count,
            "order_count": order_count,
            "rebalance_day_count": rebalance_day_count,
            "observation_day_count": observation_day_count,
            "rebalance_day_ratio": rebalance_day_ratio,
            "average_orders_per_rebalance_day": average_orders_per_rebalance_day,
            "mean_rebalance_interval_days": mean_rebalance_interval_days,
            "latest_nav_date": latest_nav_date,
            "include_in_aggregate": exclusion_reason is None,
            "exclusion_reason": exclusion_reason,
        }
        portfolio_rows.append(row)
        if exclusion_reason is None:
            included_rows.append(row)
        else:
            excluded_reasons[exclusion_reason] += 1

    cost_positive_count = sum(
        1
        for row in included_rows
        if row["annualized_excess_return_after_baseline_cost"] is not None
        and float(row["annualized_excess_return_after_baseline_cost"]) > 0
    )
    included_nav_dates = sorted(
        str(row["latest_nav_date"])
        for row in included_rows
        if row.get("latest_nav_date")
    )

    summary = {
        "selected_portfolio_count": len(portfolio_rows),
        "included_portfolio_count": len(included_rows),
        "excluded_portfolio_count": len(portfolio_rows) - len(included_rows),
        "total_order_count": sum(int(row["order_count"]) for row in included_rows),
        "rebalance_day_count": sum(int(row["rebalance_day_count"]) for row in included_rows),
        "mean_turnover": _mean_or_none([row["turnover"] for row in included_rows]),
        "mean_annualized_return": _mean_or_none([row["annualized_return"] for row in included_rows]),
        "mean_annualized_excess_return": _mean_or_none([row["annualized_excess_return"] for row in included_rows]),
        "mean_max_drawdown": _mean_or_none([row["max_drawdown"] for row in included_rows]),
        "mean_win_rate": _mean_or_none([row["win_rate"] for row in included_rows]),
        "mean_invested_ratio": _mean_or_none([row["invested_ratio"] for row in included_rows]),
        "mean_active_position_count": _mean_or_none([row["active_position_count"] for row in included_rows]),
        "latest_nav_date_count": len(set(included_nav_dates)),
        "excluded_reasons": dict(excluded_reasons),
    }
    cost_sensitivity = {
        "baseline_round_trip_cost_bps": baseline_cost_bps,
        "mean_baseline_cost_drag": _mean_or_none([row["baseline_cost_drag"] for row in included_rows]),
        "mean_annualized_excess_return_after_baseline_cost": _mean_or_none(
            [row["annualized_excess_return_after_baseline_cost"] for row in included_rows]
        ),
        "positive_after_baseline_cost_portfolio_count": cost_positive_count,
        "mean_break_even_cost_bps": _mean_or_none([row["break_even_cost_bps"] for row in included_rows]),
    }
    holding_stability = {
        "portfolio_count": len(included_rows),
        "mean_rebalance_day_ratio": _mean_or_none([row["rebalance_day_ratio"] for row in included_rows]),
        "mean_rebalance_interval_days": _mean_or_none(
            [row["mean_rebalance_interval_days"] for row in included_rows]
        ),
        "mean_orders_per_rebalance_day": _mean_or_none(
            [row["average_orders_per_rebalance_day"] for row in included_rows]
        ),
    }
    gate = evaluate_phase5_holding_policy_promotion_gate(
        summary=summary,
        cost_sensitivity=cost_sensitivity,
        holding_stability=holding_stability,
    )
    governance = evaluate_phase5_holding_policy_governance(gate=gate)
    redesign = evaluate_phase5_holding_policy_redesign_diagnostics(
        summary=summary,
        cost_sensitivity=cost_sensitivity,
        gate=gate,
        governance=governance,
    )
    redesign_experiments = recommend_phase5_holding_policy_redesign_experiments(redesign=redesign)

    if not included_rows:
        approval_state = "insufficient_policy_evidence"
        note = "当前 scope 内没有满足 Phase 5 benchmark 与 portfolio_backtest contract 的 auto-model 组合，暂时无法量化 holding-policy evidence。"
        pending_requirements = [
            "phase5 holding-policy study still lacks enough artifact-backed evidence to evaluate the draft promotion gate",
            "research_candidate policy remains simulation-only and must not be promoted to real trading",
        ]
    elif gate["gate_status"] == "draft_gate_passed_pending_approval":
        approval_state = "research_candidate_only"
        note = (
            "simulation-only 的 auto-model 组合已通过当前 draft promotion gate，"
            "但 operator 尚未批准 promotion，baseline 继续保持 research_candidate。"
        )
        pending_requirements = [
            "draft promotion gate has passed but explicit operator approval is still required",
            "research_candidate policy remains simulation-only and must not be promoted to real trading",
        ]
    else:
        approval_state = "research_candidate_only"
        gate_failures = ", ".join(gate["failing_gate_ids"] or gate["incomplete_gate_ids"])
        note = (
            "simulation-only 的 auto-model 组合已形成 turnover / 成本 / 持仓稳定性摘要，"
            f"但当前 draft promotion gate 仍未通过（{gate_failures}），baseline 继续保持 research_candidate。"
        )
        pending_requirements = [
            "draft promotion gate is still blocked by current turnover / cost / stability evidence",
            "research_candidate policy remains simulation-only and must not be promoted to real trading",
        ]
    return {
        "generated_at": datetime.now().astimezone().isoformat(),
        "scope": {
            "portfolio_keys": scope_keys,
            "default_portfolio_keys": default_portfolio_keys,
            "mode": "auto_model",
        },
        "contract_version": PHASE5_CONTRACT_VERSION,
        "policy_type": PHASE5_SIMULATION_POLICY,
        "action_definition": PHASE5_ACTION_DEFINITION,
        "quantity_definition": PHASE5_QUANTITY_DEFINITION,
        "required_benchmark_definition": PHASE5_PRIMARY_RESEARCH_BENCHMARK,
        "summary": summary,
        "cost_sensitivity": cost_sensitivity,
        "holding_stability": holding_stability,
        "decision": {
            "approval_state": approval_state,
            "note": note,
            "pending_requirements": pending_requirements,
            "gate_status": gate["gate_status"],
            "gate_context": phase5_holding_policy_promotion_gate_context(),
            "gate_checks": gate["checks"],
            "failing_gate_ids": gate["failing_gate_ids"],
            "incomplete_gate_ids": gate["incomplete_gate_ids"],
            "governance_status": governance["governance_status"],
            "governance_action": governance["governance_action"],
            "governance_note": governance["governance_note"],
            "redesign_trigger_gate_ids": governance["redesign_trigger_gate_ids"],
            "governance_context": phase5_holding_policy_governance_context(),
            "redesign_status": redesign["redesign_status"],
            "redesign_note": redesign["redesign_note"],
            "redesign_diagnostics": redesign["diagnostics"],
            "redesign_triggered_signal_ids": redesign["triggered_signal_ids"],
            "redesign_incomplete_signal_ids": redesign["incomplete_signal_ids"],
            "redesign_focus_areas": redesign["focus_areas"],
            "redesign_experiment_candidates": redesign_experiments["candidates"],
            "redesign_primary_experiment_ids": redesign_experiments["primary_experiment_ids"],
            "redesign_context": phase5_holding_policy_redesign_diagnostic_context(),
        },
        "portfolios": portfolio_rows,
    }


def phase5_holding_policy_study_artifact_id(payload: dict[str, Any]) -> str:
    scope = dict(payload.get("scope") or {})
    portfolios = list(payload.get("portfolios") or [])
    included_dates = sorted(
        {
            str(item.get("latest_nav_date"))
            for item in portfolios
            if item.get("include_in_aggregate") and item.get("latest_nav_date")
        }
    )
    if included_dates:
        date_key = included_dates[0] if len(included_dates) == 1 else f"{included_dates[0]}_to_{included_dates[-1]}"
    else:
        date_key = "no_included_dates"
    scope_kind = "custom" if scope.get("portfolio_keys") != scope.get("default_portfolio_keys") else "auto_model"
    included_count = sum(1 for item in portfolios if item.get("include_in_aggregate"))
    return f"phase5-holding-policy-study:{scope_kind}:{date_key}:{included_count}portfolios"


def build_phase5_holding_policy_study_artifact(payload: dict[str, Any]) -> Phase5HoldingPolicyStudyArtifactView:
    return Phase5HoldingPolicyStudyArtifactView(
        artifact_id=phase5_holding_policy_study_artifact_id(payload),
        generated_at=datetime.fromisoformat(str(payload["generated_at"])),
        created_at=datetime.fromisoformat(str(payload["generated_at"])),
        scope=dict(payload.get("scope") or {}),
        contract_version=str(payload.get("contract_version") or PHASE5_CONTRACT_VERSION),
        policy_type=str(payload.get("policy_type") or PHASE5_SIMULATION_POLICY),
        action_definition=str(payload.get("action_definition") or PHASE5_ACTION_DEFINITION),
        quantity_definition=str(payload.get("quantity_definition") or PHASE5_QUANTITY_DEFINITION),
        required_benchmark_definition=str(
            payload.get("required_benchmark_definition") or PHASE5_PRIMARY_RESEARCH_BENCHMARK
        ),
        summary=dict(payload.get("summary") or {}),
        cost_sensitivity=dict(payload.get("cost_sensitivity") or {}),
        holding_stability=dict(payload.get("holding_stability") or {}),
        decision=dict(payload.get("decision") or {}),
        portfolios=[dict(item) for item in payload.get("portfolios") or []],
    )
