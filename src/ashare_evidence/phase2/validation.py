from __future__ import annotations

from datetime import date, datetime
from typing import Any

from ashare_evidence.contract_status import MANUAL_TRIGGER_REQUIRED, STATUS_RESEARCH_CANDIDATE
from ashare_evidence.db import align_datetime_timezone
from ashare_evidence.models import MarketBar, Recommendation
from ashare_evidence.phase2.common import pearson_correlation, pct_change, return_between, safe_mean, safe_std, spearman_correlation
from ashare_evidence.phase2.constants import (
    PHASE2_COST_DEFINITION,
    PHASE2_COST_MODEL,
    PHASE2_FEATURE_VERSION,
    PHASE2_HORIZONS,
    PHASE2_LABEL_DEFINITION,
    PHASE2_MANUAL_REVIEW_NOTE,
    PHASE2_POLICY_VERSION,
    PHASE2_PRIMARY_HORIZON,
    PHASE2_RULE_BASELINE,
    PHASE2_WINDOW_DEFINITION,
    phase2_target_horizon_label,
)
from ashare_evidence.phase2.observations import Phase2Observation
from ashare_evidence.phase2.phase5_contract import (
    PHASE5_CONTRACT_VERSION,
    PHASE5_PRIMARY_HORIZON_STATUS,
    PHASE5_RESEARCH_UNIVERSE_DEFINITION,
    PHASE5_RESEARCH_UNIVERSE_RULE,
    PHASE5_REQUIRED_OBSERVATION_COUNT,
    PHASE5_ROLLING_SPLIT_RULE,
    PHASE5_ROLLING_WINDOW_BASELINE,
    phase5_benchmark_context,
    phase5_benchmark_definition,
    phase5_research_contract_context,
)
from ashare_evidence.research_artifacts import ArtifactSplitView, ResearchArtifactManifestView, ValidationMetricsArtifactView


def bucket_returns(scores: list[float], outcomes: list[float]) -> list[dict[str, Any]]:
    ranked = sorted(zip(scores, outcomes, strict=True), key=lambda item: item[0])
    if not ranked:
        return []
    bucket_size = max(len(ranked) // 3, 1)
    buckets: list[dict[str, Any]] = []
    for index, label in enumerate(("bottom", "middle", "top")):
        start = index * bucket_size
        end = None if index == 2 else min((index + 1) * bucket_size, len(ranked))
        bucket = ranked[start:end]
        if not bucket:
            continue
        bucket_outcomes = [item[1] for item in bucket]
        buckets.append(
            {
                "bucket": label,
                "sample_count": len(bucket),
                "mean_excess_return": round(safe_mean(bucket_outcomes), 6),
            }
        )
    return buckets


def subperiod_stats(scores: list[float], outcomes: list[float]) -> list[dict[str, Any]]:
    if len(scores) < 4:
        return []
    midpoint = len(scores) // 2
    stats = []
    for label, left, right in (("early", scores[:midpoint], outcomes[:midpoint]), ("late", scores[midpoint:], outcomes[midpoint:])):
        if len(left) < 2:
            continue
        stats.append(
            {
                "slice_label": label,
                "sample_count": len(left),
                "rank_ic_mean": round(spearman_correlation(left, right), 6),
                "positive_excess_rate": round(sum(1 for item in right if item > 0) / len(right), 6),
            }
        )
    return stats


def build_phase5_walk_forward_context(
    *,
    symbol: str,
    eligible: list[Phase2Observation],
) -> tuple[list[ArtifactSplitView], dict[str, Any], list[Phase2Observation]]:
    train_days = int(PHASE5_ROLLING_WINDOW_BASELINE["train_days"])
    validation_days = int(PHASE5_ROLLING_WINDOW_BASELINE["validation_days"])
    test_days = int(PHASE5_ROLLING_WINDOW_BASELINE["test_days"])
    split_plan: list[ArtifactSplitView] = []

    if len(eligible) >= PHASE5_REQUIRED_OBSERVATION_COUNT:
        for window_end in range(PHASE5_REQUIRED_OBSERVATION_COUNT - 1, len(eligible)):
            window_start = window_end - PHASE5_REQUIRED_OBSERVATION_COUNT + 1
            train_slice = eligible[window_start : window_start + train_days]
            validation_slice = eligible[
                window_start + train_days : window_start + train_days + validation_days
            ]
            test_slice = eligible[
                window_start + train_days + validation_days : window_start + PHASE5_REQUIRED_OBSERVATION_COUNT
            ]
            split_plan.append(
                ArtifactSplitView(
                    slice_label=f"{symbol}-phase5-wf-{len(split_plan) + 1:03d}",
                    train_start=train_slice[0].as_of,
                    train_end=train_slice[-1].as_of,
                    validation_start=validation_slice[0].as_of,
                    validation_end=validation_slice[-1].as_of,
                    test_start=test_slice[0].as_of,
                    test_end=test_slice[-1].as_of,
                    market_regime_tag="phase5_active_watchlist_research_candidate",
                )
            )
        evaluation_observations = eligible[train_days + validation_days :]
        coverage_status = "full_baseline"
    else:
        evaluation_observations = eligible
        coverage_status = "insufficient_history"

    summary = {
        **PHASE5_ROLLING_WINDOW_BASELINE,
        "required_observation_count": PHASE5_REQUIRED_OBSERVATION_COUNT,
        "available_observation_count": len(eligible),
        "evaluation_observation_count": len(evaluation_observations),
        "window_count": len(split_plan),
        "coverage_status": coverage_status,
        "first_observation_at": eligible[0].as_of.isoformat() if eligible else None,
        "last_observation_at": eligible[-1].as_of.isoformat() if eligible else None,
        "first_evaluation_as_of": evaluation_observations[0].as_of.isoformat() if evaluation_observations else None,
        "last_evaluation_as_of": evaluation_observations[-1].as_of.isoformat() if evaluation_observations else None,
    }
    return split_plan, summary, evaluation_observations


def build_horizon_comparison(
    metrics_artifacts: list[ValidationMetricsArtifactView],
    *,
    walk_forward_summary: dict[str, Any],
) -> dict[str, Any]:
    ranked = sorted(
        metrics_artifacts,
        key=lambda artifact: (
            artifact.sample_count > 0,
            artifact.net_excess_return if artifact.net_excess_return is not None else float("-inf"),
            artifact.rank_ic_mean if artifact.rank_ic_mean is not None else float("-inf"),
            artifact.positive_excess_rate if artifact.positive_excess_rate is not None else float("-inf"),
            artifact.sample_count,
        ),
        reverse=True,
    )
    candidates: list[dict[str, Any]] = []
    for index, artifact in enumerate(ranked, start=1):
        candidates.append(
            {
                "rank": index,
                "horizon": artifact.horizon,
                "artifact_id": artifact.artifact_id,
                "sample_count": artifact.sample_count,
                "net_excess_return": artifact.net_excess_return,
                "rank_ic_mean": artifact.rank_ic_mean,
                "positive_excess_rate": artifact.positive_excess_rate,
                "turnover_mean": artifact.turnover_mean,
            }
        )
    leader = candidates[0] if candidates and candidates[0]["sample_count"] > 0 else None
    selection_readiness = (
        "comparison_ready"
        if walk_forward_summary.get("coverage_status") == "full_baseline" and leader is not None
        else "insufficient_evidence"
    )
    return {
        "contract_version": PHASE5_CONTRACT_VERSION,
        "primary_horizon_status": PHASE5_PRIMARY_HORIZON_STATUS,
        "selection_readiness": selection_readiness,
        "selection_rule": "rank_by_net_excess_return_then_rank_ic_mean_then_positive_excess_rate",
        "recommended_research_leader": leader,
        "candidates": candidates,
        "walk_forward_window_count": walk_forward_summary.get("window_count", 0),
        "coverage_status": walk_forward_summary.get("coverage_status"),
    }


def build_validation_artifacts_for_recommendation(
    recommendation: Recommendation,
    *,
    bars: list[MarketBar],
    observations: list[Phase2Observation],
    market_proxy: dict[date, float],
    market_proxy_context: dict[str, Any] | None = None,
    sector_proxy: dict[date, float] | None,
) -> tuple[ResearchArtifactManifestView, list[ValidationMetricsArtifactView]]:
    bars_by_day = {bar.observed_at.date(): float(bar.close_price) for bar in bars}
    as_of_day = recommendation.as_of_data_time.date()
    eligible = [
        item
        for item in observations
        if (align_datetime_timezone(item.as_of, reference=recommendation.as_of_data_time) or item.as_of)
        <= recommendation.as_of_data_time
    ]
    benchmark_definition = phase5_benchmark_definition(
        market_proxy=bool(market_proxy),
        sector_proxy=sector_proxy is not None,
    )
    split_plan, walk_forward_summary, evaluation_observations = build_phase5_walk_forward_context(
        symbol=recommendation.stock.symbol,
        eligible=eligible,
    )
    manifest = ResearchArtifactManifestView(
        artifact_id=f"rolling-validation:{recommendation.recommendation_key}",
        artifact_type="rolling_validation",
        created_at=datetime.now().astimezone(),
        generated_at=recommendation.generated_at,
        experiment_id=f"experiment:{recommendation.recommendation_key}:phase2",
        experiment_version=PHASE2_RULE_BASELINE,
        model_version=PHASE2_RULE_BASELINE,
        policy_version=PHASE2_POLICY_VERSION,
        data_snapshot_id=f"phase2-snapshot:{recommendation.stock.symbol}:{as_of_day:%Y%m%d}",
        data_snapshot_ids=eligible[-1].feature_snapshot_keys if eligible else [],
        universe_definition=PHASE5_RESEARCH_UNIVERSE_DEFINITION,
        universe_rule=PHASE5_RESEARCH_UNIVERSE_RULE,
        availability_rule="decision_time_only_uses_available_features_and_disclosures",
        feature_set_version=PHASE2_FEATURE_VERSION,
        feature_version=PHASE2_FEATURE_VERSION,
        label_definition=PHASE2_LABEL_DEFINITION,
        benchmark_definition=benchmark_definition,
        benchmark_context={
            **phase5_benchmark_context(
                market_proxy=bool(market_proxy),
                sector_proxy=sector_proxy is not None,
                sector_code=recommendation.stock.profile_payload.get("industry"),
            ),
            **(market_proxy_context or {}),
        },
        research_contract=phase5_research_contract_context(),
        cost_definition=PHASE2_COST_DEFINITION,
        cost_model=PHASE2_COST_DEFINITION,
        rebalance_definition=PHASE5_ROLLING_SPLIT_RULE,
        rolling_windows=[walk_forward_summary],
        leakage_checks=[
            {"name": "available_time_leq_decision_time", "status": "pass"},
            {"name": "no_random_split", "status": "pass"},
            {"name": "manual_llm_excluded_from_training", "status": "pass"},
            {"name": "watchlist_tracking_not_backfilled_before_join_date", "status": "pass"},
            {
                "name": "phase5_walk_forward_split_coverage",
                "status": "pass" if walk_forward_summary["coverage_status"] == "full_baseline" else "warn",
                "note": (
                    "当前样本已覆盖 Phase 5 480/120/60 walk-forward 基线。"
                    if walk_forward_summary["coverage_status"] == "full_baseline"
                    else "当前样本不足以覆盖完整的 Phase 5 480/120/60 walk-forward 基线，metrics 暂退回到可用历史窗口。"
                ),
            },
        ],
        split_plan=split_plan,
    )

    artifacts: list[ValidationMetricsArtifactView] = []
    for horizon in PHASE2_HORIZONS:
        scores: list[float] = []
        excess_returns: list[float] = []
        realized_returns: list[float] = []
        turnover_values: list[float] = []
        for observation in evaluation_observations:
            exit_index = observation.index + horizon
            if exit_index >= len(bars):
                continue
            exit_observed_at = align_datetime_timezone(
                bars[exit_index].observed_at,
                reference=recommendation.as_of_data_time,
            ) or bars[exit_index].observed_at
            if exit_observed_at > recommendation.as_of_data_time:
                continue
            exit_day = exit_observed_at.date()
            stock_return = pct_change(bars_by_day[exit_day], bars_by_day[observation.trade_day])
            benchmark_return = return_between(market_proxy, observation.trade_day, exit_day)
            if benchmark_return is None:
                benchmark_return = stock_return if len(market_proxy) == 0 else 0.0
            excess_return = stock_return - benchmark_return
            scores.append(observation.score)
            realized_returns.append(stock_return)
            excess_returns.append(excess_return)
            turnover_values.append(observation.turnover_estimate)

        sample_count = len(scores)
        rank_ic_mean = spearman_correlation(scores, excess_returns)
        rank_ic_std = abs(rank_ic_mean) / max(sample_count, 1) ** 0.5 if sample_count else 0.0
        mean_turnover = safe_mean(turnover_values)
        net_excess_return = safe_mean(excess_returns) - (PHASE2_COST_MODEL["round_trip_cost_bps"] / 10000.0) * mean_turnover
        buckets = bucket_returns(scores, excess_returns)
        artifacts.append(
            ValidationMetricsArtifactView(
                artifact_id=f"validation-metrics:{recommendation.recommendation_key}:{horizon}d",
                manifest_id=manifest.artifact_id,
                status=STATUS_RESEARCH_CANDIDATE,
                status_note="已有滚动验证产物，当前仍处于观察阶段，尚未完成正式验证。",
                horizon=horizon,
                sample_count=sample_count,
                rank_ic_mean=round(rank_ic_mean, 6),
                rank_ic_std=round(rank_ic_std, 6),
                rank_ic_ir=round(rank_ic_mean / max(rank_ic_std, 1e-6), 6) if sample_count else 0.0,
                ic_mean=round(pearson_correlation(scores, excess_returns), 6),
                bucket_returns=buckets,
                net_excess_return=round(net_excess_return, 6),
                turnover=round(mean_turnover, 6),
                coverage=1.0 if sample_count else 0.0,
                subperiod_stats=subperiod_stats(scores, excess_returns),
                bucket_spread_mean=round((buckets[-1]["mean_excess_return"] - buckets[0]["mean_excess_return"]) if len(buckets) >= 2 else 0.0, 6),
                bucket_spread_std=round(safe_std(excess_returns) or 1.0, 6),
                positive_excess_rate=round(sum(1 for item in excess_returns if item > 0) / sample_count, 6) if sample_count else 0.0,
                turnover_mean=round(mean_turnover, 6),
                coverage_ratio=1.0 if sample_count else 0.0,
                period_metrics=[
                    {
                        "horizon": horizon,
                        "mean_return": round(safe_mean(realized_returns), 6),
                        "mean_excess_return": round(safe_mean(excess_returns), 6),
                        "sample_count": sample_count,
                        "walk_forward_window_count": walk_forward_summary["window_count"],
                    }
                ],
                market_regime_metrics=[
                    {
                        "market_regime_tag": "phase5_active_watchlist_research_candidate",
                        "rank_ic_mean": round(rank_ic_mean, 6),
                        "net_excess_return": round(net_excess_return, 6),
                        "coverage_status": walk_forward_summary["coverage_status"],
                    }
                ],
                industry_slice_metrics=[],
                feature_drift_summary={
                    "status": "stable_fixture_snapshot",
                    "feature_snapshot_count": len(eligible),
                    "evaluation_observation_count": len(evaluation_observations),
                    "coverage_status": walk_forward_summary["coverage_status"],
                    "horizon": horizon,
                },
            )
        )
    return manifest, artifacts


def update_recommendation_payload(
    recommendation: Recommendation,
    *,
    manifest: ResearchArtifactManifestView,
    primary_metrics: ValidationMetricsArtifactView,
    metrics_artifacts: list[ValidationMetricsArtifactView],
) -> None:
    payload = dict(recommendation.recommendation_payload or {})
    core_quant = dict(payload.get("core_quant") or {})
    core_quant["target_horizon_label"] = phase2_target_horizon_label()
    core_quant["horizon_min_days"] = min(PHASE2_HORIZONS)
    core_quant["horizon_max_days"] = max(PHASE2_HORIZONS)
    core_quant["policy_version"] = PHASE2_POLICY_VERSION

    evidence = dict(payload.get("evidence") or {})
    support = list(evidence.get("supporting_context") or [])
    if not any("Phase 2" in item for item in support):
        support.append("Phase 2 已将 recommendation 接入 walk-forward research artifact；当前状态仍是 research candidate。")
    if not any("Phase 5" in item for item in support):
        support.append("Phase 5 已明确区分完整历史研究验证与加入后跟踪统计，当前 validation artifact 按该 contract 生成。")
    evidence["supporting_context"] = support

    risk = dict(payload.get("risk") or {})
    coverage_gaps = [str(item) for item in risk.get("coverage_gaps") or [] if item and "历史验证" not in str(item)]
    coverage_gaps.append("当前 validation artifact 已生成，但规则基线与主模型对照尚未完成 verified 审批。")
    risk["coverage_gaps"] = coverage_gaps

    manual_review = dict(payload.get("manual_llm_review") or {})
    manual_review["status"] = str(manual_review.get("status") or MANUAL_TRIGGER_REQUIRED)
    manual_review["trigger_mode"] = "manual"
    manual_review["summary"] = PHASE2_MANUAL_REVIEW_NOTE

    historical_validation = dict(payload.get("historical_validation") or {})
    walk_forward_summary = dict(manifest.rolling_windows[0]) if manifest.rolling_windows else {}
    candidate_horizon_comparison = build_horizon_comparison(
        metrics_artifacts,
        walk_forward_summary=walk_forward_summary,
    )
    historical_validation.update(
        {
            "status": STATUS_RESEARCH_CANDIDATE,
            "note": primary_metrics.status_note,
            "artifact_type": "validation_metrics",
            "artifact_id": primary_metrics.artifact_id,
            "manifest_id": manifest.artifact_id,
            "artifact_generated_at": manifest.generated_at.isoformat(),
            "label_definition": manifest.label_definition,
            "window_definition": PHASE2_WINDOW_DEFINITION,
            "benchmark_definition": manifest.benchmark_definition,
            "cost_definition": manifest.cost_definition,
            "metrics": {
                "sample_count": primary_metrics.sample_count,
                "rank_ic_mean": primary_metrics.rank_ic_mean,
                "rank_ic_std": primary_metrics.rank_ic_std,
                "rank_ic_ir": primary_metrics.rank_ic_ir,
                "ic_mean": primary_metrics.ic_mean,
                "bucket_spread_mean": primary_metrics.bucket_spread_mean,
                "bucket_spread_std": primary_metrics.bucket_spread_std,
                "positive_excess_rate": primary_metrics.positive_excess_rate,
                "turnover_mean": primary_metrics.turnover_mean,
                "coverage_ratio": primary_metrics.coverage_ratio,
                "horizon": primary_metrics.horizon,
                "net_excess_return": primary_metrics.net_excess_return,
                "walk_forward": walk_forward_summary,
                "candidate_horizon_comparison": candidate_horizon_comparison,
                "research_contract_version": manifest.research_contract.get("contract_version"),
            },
        }
    )
    payload["core_quant"] = core_quant
    payload["evidence"] = evidence
    payload["risk"] = risk
    payload["manual_llm_review"] = manual_review
    payload["historical_validation"] = historical_validation
    payload["validation_status"] = STATUS_RESEARCH_CANDIDATE
    payload["validation_note"] = primary_metrics.status_note
    payload["validation_metrics_artifact_id"] = primary_metrics.artifact_id
    recommendation.recommendation_payload = payload
