from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ashare_evidence.research_artifact_store import (
    portfolio_backtest_artifact_id,
    read_backtest_artifact,
    read_phase5_holding_policy_experiment_artifact,
    read_phase5_holding_policy_study_artifact,
    read_manifest,
    read_phase5_horizon_study_artifact,
    read_phase5_producer_contract_study_artifact,
    read_replay_alignment_artifact,
    resolve_backtest_artifact,
    read_validation_metrics,
    write_backtest_artifact,
    write_phase5_holding_policy_experiment_artifact,
    write_phase5_holding_policy_study_artifact,
    write_manifest,
    write_phase5_horizon_study_artifact,
    write_phase5_producer_contract_study_artifact,
    write_replay_alignment_artifact,
    write_validation_metrics,
)
from ashare_evidence.research_artifacts import (
    ArtifactSplitView,
    BacktestArtifactView,
    Phase5HoldingPolicyExperimentArtifactView,
    Phase5HoldingPolicyStudyArtifactView,
    Phase5HorizonStudyArtifactView,
    Phase5ProducerContractStudyArtifactView,
    ReplayAlignmentArtifactView,
    ResearchArtifactManifestView,
    ValidationMetricsArtifactView,
)


class ResearchArtifactStoreTests(unittest.TestCase):
    def test_resolve_backtest_artifact_falls_back_to_canonical_portfolio_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifact = BacktestArtifactView(
                artifact_id="portfolio-backtest:sim-20260427122709-8da19b-model",
                manifest_id="rolling-validation:phase2-portfolio-backtests",
                strategy_definition="topk_drop",
                position_limit_definition="single_name_le_20pct",
                execution_assumptions="paper_fills_only",
                benchmark_definition="active_watchlist_equal_weight_proxy",
                cost_definition="35 bps",
                annualized_return=0.0,
                annualized_excess_return=0.0024,
                max_drawdown=0.0,
                sharpe_like_ratio=0.24,
                turnover=0.0,
                win_rate_definition="positive_excess_nav_point_ratio_against_phase2_proxy",
                win_rate=1.0,
                capacity_note="fixture",
            )
            write_backtest_artifact(artifact, root=root)

            resolved_id, resolved_artifact = resolve_backtest_artifact(
                configured_artifact_id="portfolio-backtest:portfolio-auto-live",
                portfolio_key="sim-20260427122709-8da19b-model",
                root=root,
            )

            self.assertEqual(
                resolved_id,
                portfolio_backtest_artifact_id("sim-20260427122709-8da19b-model"),
            )
            assert resolved_artifact is not None
            self.assertEqual(resolved_artifact.artifact_id, artifact.artifact_id)

    def test_artifact_store_uses_phase2_contract_layout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            generated_at = datetime(2026, 4, 25, 12, 0, tzinfo=timezone.utc)
            manifest = ResearchArtifactManifestView(
                artifact_id="rolling-validation-fixture",
                artifact_type="rolling_validation",
                generated_at=generated_at,
                experiment_version="exp-v1",
                model_version="lgbm-ranker-v1",
                policy_version="policy-v1",
                data_snapshot_id="snapshot-20260425",
                universe_definition="watchlist_plus_sector_peers",
                availability_rule="t_plus_1_disclosure_aligned",
                feature_set_version="features-v1",
                label_definition="forward_20d_excess_return",
                benchmark_definition="CSI300_total_return",
                cost_definition="12 bps",
                rebalance_definition="weekly_rebalance",
                split_plan=[
                    ArtifactSplitView(
                        slice_label="2024H1",
                        train_start=datetime(2021, 1, 1, tzinfo=timezone.utc),
                        train_end=datetime(2023, 12, 31, tzinfo=timezone.utc),
                        validation_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
                        validation_end=datetime(2024, 3, 31, tzinfo=timezone.utc),
                        test_start=datetime(2024, 4, 1, tzinfo=timezone.utc),
                        test_end=datetime(2024, 6, 30, tzinfo=timezone.utc),
                        market_regime_tag="risk_on",
                    )
                ],
            )
            validation = ValidationMetricsArtifactView(
                artifact_id="validation-fixture",
                manifest_id=manifest.artifact_id,
                status="research_candidate",
                sample_count=96,
                rank_ic_mean=0.041,
                rank_ic_std=0.09,
                rank_ic_ir=0.46,
                ic_mean=0.038,
                bucket_spread_mean=0.028,
                bucket_spread_std=0.071,
                positive_excess_rate=0.57,
                turnover_mean=0.18,
                coverage_ratio=0.92,
            )
            backtest = BacktestArtifactView(
                artifact_id="backtest-fixture",
                manifest_id=manifest.artifact_id,
                strategy_definition="topk_drop",
                position_limit_definition="single_name_le_15pct",
                execution_assumptions="T+1, 涨跌停, 停牌, 100-share lot, slippage, fees",
                benchmark_definition="CSI300_total_return",
                cost_definition="12 bps",
                annualized_return=0.18,
                annualized_excess_return=0.07,
                max_drawdown=-0.12,
                sharpe_like_ratio=1.1,
                turnover=0.23,
                win_rate_definition="monthly_excess_positive_rate",
                win_rate=0.61,
                capacity_note="watchlist-scoped demo",
            )
            replay = ReplayAlignmentArtifactView(
                artifact_id="replay-fixture",
                manifest_id=manifest.artifact_id,
                recommendation_id=1,
                recommendation_key="reco-fixture",
                label_definition="forward_20d_excess_return",
                review_window_definition="20_trade_days_post_signal",
                entry_rule="next_trade_day_close",
                exit_rule="20_trade_days_close",
                benchmark_definition="CSI300_total_return",
                hit_definition="excess_return_gt_0",
                stock_return=0.09,
                benchmark_return=0.03,
                excess_return=0.06,
                validation_status="research_candidate",
            )
            study = Phase5HorizonStudyArtifactView(
                artifact_id="phase5-horizon-study:latest:2026-04-25:3symbols",
                generated_at=generated_at,
                scope={"symbols": ["600519.SH", "300750.SZ", "601318.SH"], "include_history": False},
                contract_version="phase5-validation-policy-contract-v1",
                required_benchmark_definition="active_watchlist_equal_weight_proxy",
                primary_horizon_status="pending_phase5_selection",
                summary={"included_record_count": 3, "included_as_of_date_count": 1},
                decision={"approval_state": "split_leadership", "candidate_frontier": [10, 20], "lagging_horizons": [40]},
            )
            holding_policy = Phase5HoldingPolicyStudyArtifactView(
                artifact_id="phase5-holding-policy-study:auto_model:2026-04-25:1portfolios",
                generated_at=generated_at,
                scope={"portfolio_keys": ["portfolio-auto-live"], "mode": "auto_model"},
                contract_version="phase5-validation-policy-contract-v1",
                policy_type="phase5_simulation_topk_equal_weight_v1",
                action_definition="delta_to_constrained_target_weight_portfolio",
                quantity_definition="board_lot_delta_to_target_weight",
                required_benchmark_definition="active_watchlist_equal_weight_proxy",
                summary={"included_portfolio_count": 1, "mean_turnover": 0.23},
                cost_sensitivity={"baseline_round_trip_cost_bps": 35.0},
                holding_stability={"portfolio_count": 1, "mean_rebalance_day_ratio": 0.12},
                decision={"approval_state": "research_candidate_only"},
            )
            holding_policy_experiment = Phase5HoldingPolicyExperimentArtifactView(
                artifact_id="phase5-holding-policy-experiment:profitability_signal_threshold_sweep_v1:2026-04-01_to_2026-04-25:4symbols:3variants",
                generated_at=generated_at,
                scope={"symbols": ["600519.SH", "300750.SZ", "601318.SH", "002594.SZ"]},
                contract_version="phase5-validation-policy-contract-v1",
                policy_type="phase5_simulation_topk_equal_weight_v1",
                action_definition="delta_to_constrained_target_weight_portfolio",
                quantity_definition="board_lot_delta_to_target_weight",
                required_benchmark_definition="active_watchlist_equal_weight_proxy",
                experiment_id="profitability_signal_threshold_sweep_v1",
                experiment_version="phase5-holding-policy-experiment-v1",
                experiment_definition={"focus_area": "after_cost_profitability"},
                summary={"trade_day_count": 18, "variant_count": 3, "included_variant_count": 3},
                decision={"baseline_variant_id": "baseline_top5_weight20_conf0"},
                variants=[
                    {
                        "variant_id": "baseline_top5_weight20_conf0",
                        "summary": {"annualized_excess_return_after_baseline_cost": -0.02},
                    }
                ],
            )
            producer_contract_study = Phase5ProducerContractStudyArtifactView(
                artifact_id="phase5-producer-contract-study:history:2026-04-20_to_2026-04-25:3symbols",
                generated_at=generated_at,
                scope={"symbols": ["600519.SH", "300750.SZ", "601318.SH"], "include_history": True},
                contract_version="phase5-producer-contract-study-draft-v1",
                summary={"included_record_count": 6, "missing_news_only_record_count": 2},
                variants=[{"variant_id": "watch_ceiling_keep_penalty", "long_count": 4}],
                symbol_analysis=[{"symbol": "600519.SH", "record_count": 2}],
                focus_records=[{"symbol": "600519.SH", "as_of_date": "2026-04-25"}],
                decision={"recommended_variant_id": "watch_ceiling_keep_penalty"},
            )

            manifest_path = write_manifest(manifest, root=root)
            validation_path = write_validation_metrics(validation, root=root)
            backtest_path = write_backtest_artifact(backtest, root=root)
            replay_path = write_replay_alignment_artifact(replay, root=root)
            study_path = write_phase5_horizon_study_artifact(study, root=root)
            holding_policy_path = write_phase5_holding_policy_study_artifact(holding_policy, root=root)
            holding_policy_experiment_path = write_phase5_holding_policy_experiment_artifact(
                holding_policy_experiment,
                root=root,
            )
            producer_contract_study_path = write_phase5_producer_contract_study_artifact(
                producer_contract_study,
                root=root,
            )

            self.assertEqual(manifest_path, root / "manifests" / "rolling-validation-fixture.json")
            self.assertEqual(validation_path, root / "validation" / "validation-fixture.json")
            self.assertEqual(backtest_path, root / "backtests" / "backtest-fixture.json")
            self.assertEqual(replay_path, root / "replays" / "replay-fixture.json")
            self.assertEqual(study_path, root / "studies" / "phase5-horizon-study:latest:2026-04-25:3symbols.json")
            self.assertEqual(
                holding_policy_path,
                root / "studies" / "phase5-holding-policy-study:auto_model:2026-04-25:1portfolios.json",
            )
            self.assertEqual(
                holding_policy_experiment_path,
                root
                / "studies"
                / "phase5-holding-policy-experiment:profitability_signal_threshold_sweep_v1:2026-04-01_to_2026-04-25:4symbols:3variants.json",
            )
            self.assertEqual(
                producer_contract_study_path,
                root / "studies" / "phase5-producer-contract-study:history:2026-04-20_to_2026-04-25:3symbols.json",
            )

            self.assertEqual(read_manifest("rolling-validation-fixture", root=root).artifact_id, manifest.artifact_id)
            self.assertEqual(read_validation_metrics("validation-fixture", root=root).manifest_id, manifest.artifact_id)
            self.assertEqual(read_backtest_artifact("backtest-fixture", root=root).strategy_definition, "topk_drop")
            self.assertEqual(
                read_replay_alignment_artifact("replay-fixture", root=root).review_window_definition,
                "20_trade_days_post_signal",
            )
            self.assertEqual(
                read_phase5_horizon_study_artifact(study.artifact_id, root=root).decision["approval_state"],
                "split_leadership",
            )
            self.assertEqual(
                read_phase5_holding_policy_study_artifact(holding_policy.artifact_id, root=root).decision["approval_state"],
                "research_candidate_only",
            )
            self.assertEqual(
                read_phase5_holding_policy_experiment_artifact(
                    holding_policy_experiment.artifact_id,
                    root=root,
                ).experiment_id,
                "profitability_signal_threshold_sweep_v1",
            )
            self.assertEqual(
                read_phase5_producer_contract_study_artifact(
                    producer_contract_study.artifact_id,
                    root=root,
                ).decision["recommended_variant_id"],
                "watch_ceiling_keep_penalty",
            )


if __name__ == "__main__":
    unittest.main()
