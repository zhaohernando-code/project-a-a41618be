from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from ashare_evidence.contract_status import STATUS_PENDING_REBUILD
from ashare_evidence.phase2 import (
    PHASE2_COST_DEFINITION,
    PHASE2_LABEL_DEFINITION,
    PHASE2_WINDOW_DEFINITION,
)
from ashare_evidence.phase2.phase5_contract import phase5_benchmark_definition
from ashare_evidence.research_artifacts import (
    ArtifactSplitView,
    BacktestArtifactView,
    ReplayAlignmentArtifactView,
    ResearchArtifactManifestView,
    ValidationMetricsArtifactView,
)
from ashare_evidence.signal_engine import PRIMARY_HORIZON


def _primary_model_result(signal_artifacts: Any) -> dict[str, Any]:
    for item in signal_artifacts.model_results:
        if int(item["forecast_horizon_days"]) == PRIMARY_HORIZON:
            return item
    return signal_artifacts.model_results[0]


def build_migration_validation_artifacts(signal_artifacts: Any) -> tuple[ResearchArtifactManifestView, ValidationMetricsArtifactView]:
    recommendation = signal_artifacts.recommendation
    payload = recommendation["recommendation_payload"]
    historical_validation = payload.get("historical_validation") or {}
    primary_result = _primary_model_result(signal_artifacts)
    generated_at = recommendation["generated_at"]
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=datetime.now().astimezone().tzinfo)

    manifest_id = f"rolling-validation:{primary_result['result_key']}"
    validation_metrics_id = f"validation-metrics:{primary_result['result_key']}"
    train_end = recommendation["as_of_data_time"] - timedelta(days=120)
    validation_end = recommendation["as_of_data_time"] - timedelta(days=30)
    validation_start = train_end + timedelta(days=1)
    test_start = validation_end + timedelta(days=1)

    manifest = ResearchArtifactManifestView(
        artifact_id=manifest_id,
        artifact_type="rolling_validation",
        generated_at=generated_at,
        experiment_version=f"migration-{signal_artifacts.model_run['run_key']}",
        model_version=signal_artifacts.model_version["version"],
        policy_version=str(payload.get("policy", "evidence-first")),
        data_snapshot_id=f"snapshot:{recommendation['stock_symbol']}:{recommendation['as_of_data_time']:%Y%m%d}",
        universe_definition="migration_fixture_watchlist_relative_frame",
        availability_rule="migration_fixture_t_plus_1_placeholder",
        feature_set_version="signal-engine-fixture-v1",
        label_definition=str(historical_validation.get("label_definition") or PHASE2_LABEL_DEFINITION),
        benchmark_definition=str(
            historical_validation.get("benchmark_definition")
            or phase5_benchmark_definition(market_proxy=True, sector_proxy=True)
        ),
        cost_definition=str(historical_validation.get("cost_definition") or PHASE2_COST_DEFINITION),
        rebalance_definition="migration_fixture_placeholder",
        split_plan=[
            ArtifactSplitView(
                slice_label=f"{recommendation['stock_symbol']}-migration-slice",
                train_start=train_end - timedelta(days=720),
                train_end=train_end,
                validation_start=validation_start,
                validation_end=validation_end,
                test_start=test_start,
                test_end=recommendation["as_of_data_time"],
                market_regime_tag="migration_fixture",
            )
        ],
    )

    expected_return = float(primary_result.get("expected_return") or 0.0)
    confidence_score = float(primary_result.get("confidence_score") or 0.0)
    validation_metrics = ValidationMetricsArtifactView(
        artifact_id=validation_metrics_id,
        manifest_id=manifest.artifact_id,
        status=str(historical_validation.get("status") or STATUS_PENDING_REBUILD),
        sample_count=len(signal_artifacts.model_results),
        rank_ic_mean=round(expected_return, 4),
        rank_ic_std=round(max(0.01, abs(expected_return) / 2), 4),
        rank_ic_ir=round(expected_return / max(0.01, abs(expected_return) / 2), 4) if expected_return else 0.0,
        ic_mean=round(expected_return * 0.9, 4),
        bucket_spread_mean=round(expected_return, 4),
        bucket_spread_std=round(max(0.02, abs(expected_return) / 1.5), 4),
        positive_excess_rate=round(min(max(confidence_score, 0.0), 1.0), 4),
        turnover_mean=0.18,
        coverage_ratio=1.0,
        period_metrics=[
            {
                "slice_label": manifest.split_plan[0].slice_label,
                "rank_ic_mean": round(expected_return, 4),
                "positive_excess_rate": round(min(max(confidence_score, 0.0), 1.0), 4),
            }
        ],
        market_regime_metrics=[
            {
                "market_regime_tag": "migration_fixture",
                "rank_ic_mean": round(expected_return, 4),
            }
        ],
        industry_slice_metrics=[],
        feature_drift_summary={
            "status": PHASE2_WINDOW_DEFINITION,
            "feature_count": len(signal_artifacts.feature_snapshots),
        },
    )
    return manifest, validation_metrics


def build_migration_portfolio_backtest_artifacts(
    portfolio_payloads: list[dict[str, Any]],
    *,
    generated_at: datetime,
) -> tuple[ResearchArtifactManifestView, list[BacktestArtifactView]]:
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=datetime.now().astimezone().tzinfo)

    active_symbols = sorted(
        {
            str(item.get("symbol"))
            for payload in portfolio_payloads
            for item in payload.get("holdings") or []
            if item.get("symbol")
        }
    )
    benchmark_definition = phase5_benchmark_definition(market_proxy=True, sector_proxy=False)
    manifest = ResearchArtifactManifestView(
        artifact_id="rolling-validation:portfolio-migration-watchlist",
        artifact_type="rolling_validation",
        generated_at=generated_at,
        experiment_version="migration-portfolio-backtest-v1",
        model_version="migration-portfolio-layer",
        policy_version="migration-portfolio-policy",
        data_snapshot_id=f"portfolio-snapshot:{generated_at:%Y%m%d%H%M}",
        universe_definition="migration_fixture_watchlist_relative_frame",
        availability_rule="migration_fixture_t_plus_1_placeholder",
        feature_set_version="operations-portfolio-migration-v1",
        label_definition="portfolio_total_and_excess_return_vs_watchlist_equal_weight_proxy",
        benchmark_definition=benchmark_definition,
        benchmark_context={"symbol_scope": active_symbols},
        cost_definition="migration_fixture_commission_and_tax_placeholder",
        rebalance_definition="migration_portfolio_execution_placeholder",
        split_plan=[
            ArtifactSplitView(
                slice_label="portfolio-migration-watchlist",
                train_start=generated_at - timedelta(days=720),
                train_end=generated_at - timedelta(days=120),
                validation_start=generated_at - timedelta(days=119),
                validation_end=generated_at - timedelta(days=30),
                test_start=generated_at - timedelta(days=29),
                test_end=generated_at,
                market_regime_tag="migration_fixture",
            )
        ],
    )

    backtests: list[BacktestArtifactView] = []
    for payload in portfolio_payloads:
        portfolio_key = str(payload["portfolio_key"])
        performance = payload.get("performance") or {}
        payload_benchmark_definition = str(performance.get("benchmark_definition") or benchmark_definition)
        backtests.append(
            BacktestArtifactView(
                artifact_id=str(payload.get("validation_artifact_id") or f"portfolio-backtest:{portfolio_key}"),
                manifest_id=manifest.artifact_id,
                strategy_definition=str(payload.get("strategy_summary") or portfolio_key),
                position_limit_definition="manual=35% / auto=30%",
                execution_assumptions="paper_fills_on_observed_close + board_lot + T+1 + price_limit_checks",
                benchmark_definition=payload_benchmark_definition,
                benchmark={"definition": payload_benchmark_definition, "symbol_scope": active_symbols},
                cost_definition="migration_fixture_commission_and_tax_placeholder",
                annualized_return=float(performance.get("total_return") or payload.get("total_return") or 0.0),
                annualized_excess_return=float(
                    performance.get("excess_return") or payload.get("excess_return") or 0.0
                ),
                max_drawdown=float(performance.get("max_drawdown") or payload.get("max_drawdown") or 0.0),
                sharpe_like_ratio=round(
                    float(performance.get("excess_return") or payload.get("excess_return") or 0.0)
                    / max(abs(float(performance.get("max_drawdown") or payload.get("max_drawdown") or 0.0)), 0.01),
                    4,
                ),
                turnover=round(min(float(payload.get("order_count") or 0) / 12.0, 1.0), 4),
                win_rate_definition="positive_excess_nav_point_ratio_against_watchlist_equal_weight_proxy",
                win_rate=0.5,
                capacity_note="迁移期 paper track artifact；benchmark 已切换到观察池等权 proxy，正式晋级仍待后续 phase 批准。",
                nav_series_ref=f"ops-nav:{portfolio_key}",
                drawdown_series_ref=f"ops-drawdown:{portfolio_key}",
                trade_log_ref=f"ops-trades:{portfolio_key}",
                exposure_summary={
                    "invested_ratio": payload.get("invested_ratio"),
                    "active_position_count": payload.get("active_position_count"),
                },
                stress_period_summary=[
                    {
                        "period": "migration_fixture_window",
                        "max_drawdown": performance.get("max_drawdown") or payload.get("max_drawdown"),
                        "excess_return": performance.get("excess_return") or payload.get("excess_return"),
                    }
                ],
            )
        )
    return manifest, backtests


def build_migration_replay_alignment_artifacts(
    replay_payloads: list[dict[str, Any]],
) -> list[ReplayAlignmentArtifactView]:
    artifacts: list[ReplayAlignmentArtifactView] = []
    for payload in replay_payloads:
        recommendation_id = int(payload["recommendation_id"])
        recommendation_key = str(payload.get("recommendation_key") or f"migration-replay:{recommendation_id}")
        manifest_id = str(
            payload.get("manifest_id")
            or f"rolling-validation:replay-migration:{payload.get('symbol', recommendation_key)}"
        )
        artifacts.append(
            ReplayAlignmentArtifactView(
                artifact_id=str(payload.get("artifact_id") or f"replay-alignment:{recommendation_key}"),
                manifest_id=manifest_id,
                recommendation_id=recommendation_id,
                recommendation_key=recommendation_key,
                label_definition=str(payload.get("label_definition") or "migration_directional_replay_pending"),
                review_window_definition=str(
                    payload.get("review_window_definition")
                    or "migration_latest_available_close_vs_watchlist_equal_weight_proxy"
                ),
                entry_rule="migration_recommendation_asof_close_placeholder",
                exit_rule="migration_latest_available_close_placeholder",
                benchmark_definition=str(
                    payload.get("benchmark_definition")
                    or phase5_benchmark_definition(market_proxy=True, sector_proxy=False)
                ),
                benchmark_context=dict(payload.get("benchmark_context") or {}),
                hit_definition=str(
                    payload.get("hit_definition")
                    or "迁移期以最新可得收盘相对观察池等权 proxy 的方向一致性做研究候选判定，正式定义待重建。"
                ),
                stock_return=float(payload.get("stock_return") or 0.0),
                benchmark_return=float(payload.get("benchmark_return") or 0.0),
                excess_return=float(payload.get("excess_return") or 0.0),
                validation_status=str(payload.get("validation_status") or STATUS_PENDING_REBUILD),
            )
        )
    return artifacts
