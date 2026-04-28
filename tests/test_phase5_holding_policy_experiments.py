from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from datetime import date, datetime

from ashare_evidence.cli import main
from ashare_evidence.db import init_database, session_scope
from ashare_evidence.phase2.holding_policy_experiments import (
    AvailableRecommendation,
    PolicyVariant,
    _replay_variant,
    build_phase5_holding_policy_experiment,
    build_phase5_holding_policy_experiment_artifact,
    phase5_holding_policy_experiment_artifact_id,
)
from ashare_evidence.research_artifact_store import (
    artifact_root_from_database_url,
    read_phase5_holding_policy_experiment_artifact,
)
from tests.fixtures import DEFAULT_WATCHLIST_SYMBOLS, seed_watchlist_fixture


class Phase5HoldingPolicyExperimentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "phase5-holding-policy-experiments.db"
        self.database_url = f"sqlite:///{database_path}"
        init_database(self.database_url)
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_build_profitability_signal_threshold_experiment_returns_baseline_and_decision(self) -> None:
        with session_scope(self.database_url) as session:
            payload = build_phase5_holding_policy_experiment(
                session,
                experiment_id="profitability_signal_threshold_sweep_v1",
            )

        self.assertEqual(payload["experiment_id"], "profitability_signal_threshold_sweep_v1")
        self.assertEqual(payload["summary"]["variant_count"], 3)
        self.assertEqual(payload["decision"]["baseline_variant_id"], "baseline_top5_weight20_conf0")
        self.assertIn(
            payload["decision"]["recommendation_status"],
            {"baseline_still_best", "variant_outperforms_baseline"},
        )
        self.assertEqual(
            [item["variant_id"] for item in payload["variants"]],
            [
                "baseline_top5_weight20_conf0",
                "threshold_conf65_top5_weight20",
                "threshold_conf70_top5_weight20",
            ],
        )
        self.assertGreaterEqual(payload["summary"]["included_variant_count"], 1)

    def test_build_construction_max_position_count_experiment_with_expanded_scope_replays_multiple_variants(self) -> None:
        expanded_symbols = DEFAULT_WATCHLIST_SYMBOLS + ("688981.SH", "002028.SZ")
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session, symbols=("688981.SH", "002028.SZ"))
            payload = build_phase5_holding_policy_experiment(
                session,
                experiment_id="construction_max_position_count_sweep_v1",
                symbols=list(expanded_symbols),
            )

        self.assertEqual(payload["experiment_id"], "construction_max_position_count_sweep_v1")
        self.assertEqual(payload["summary"]["variant_count"], 3)
        self.assertEqual(payload["summary"]["included_variant_count"], 3)
        self.assertEqual(
            [item["variant_id"] for item in payload["variants"]],
            [
                "capacity_top3_weight33_conf0",
                "baseline_top5_weight20_conf0",
                "capacity_top7_weight14_conf0",
            ],
        )
        self.assertEqual(payload["decision"]["baseline_variant_id"], "baseline_top5_weight20_conf0")
        self.assertIsNotNone(payload["decision"]["recommended_variant_id"])
        self.assertIn("mean_invested_ratio", payload["decision"]["metric_deltas_vs_baseline"])

    def test_phase5_holding_policy_experiment_artifact_id_is_stable_for_same_evidence_set(self) -> None:
        with session_scope(self.database_url) as session:
            payload = build_phase5_holding_policy_experiment(
                session,
                experiment_id="profitability_signal_threshold_sweep_v1",
            )

        artifact = build_phase5_holding_policy_experiment_artifact(payload)
        self.assertEqual(artifact.artifact_id, phase5_holding_policy_experiment_artifact_id(payload))
        self.assertEqual(artifact.experiment_id, "profitability_signal_threshold_sweep_v1")

    def test_replay_variant_computes_mean_rebalance_interval_for_multiple_rebalances(self) -> None:
        trade_days = [
            date(2026, 1, 5),
            date(2026, 1, 6),
            date(2026, 1, 7),
            date(2026, 1, 8),
        ]
        close_maps = {
            "600519.SH": {trade_day: 100.0 for trade_day in trade_days},
            "000858.SZ": {trade_day: 100.0 for trade_day in trade_days},
        }
        benchmark_map = {trade_day: 100.0 for trade_day in trade_days}
        histories = {
            "600519.SH": [
                AvailableRecommendation(
                    symbol="600519.SH",
                    available_day=trade_days[0],
                    as_of_day=trade_days[0],
                    generated_at=datetime(2026, 1, 5, 15, 0, 0),
                    direction="buy",
                    confidence_score=0.8,
                    confidence_label="high",
                    score=100,
                    recommendation_key="a-1",
                ),
                AvailableRecommendation(
                    symbol="600519.SH",
                    available_day=trade_days[2],
                    as_of_day=trade_days[2],
                    generated_at=datetime(2026, 1, 7, 15, 0, 0),
                    direction="buy",
                    confidence_score=0.82,
                    confidence_label="high",
                    score=130,
                    recommendation_key="a-2",
                ),
            ],
            "000858.SZ": [
                AvailableRecommendation(
                    symbol="000858.SZ",
                    available_day=trade_days[1],
                    as_of_day=trade_days[1],
                    generated_at=datetime(2026, 1, 6, 15, 0, 0),
                    direction="buy",
                    confidence_score=0.81,
                    confidence_label="high",
                    score=120,
                    recommendation_key="b-1",
                ),
            ],
        }
        variant = PolicyVariant(
            variant_id="top1_full_weight",
            label="Top 1 full weight",
            max_position_count=1,
            max_single_weight=1.0,
            min_confidence_score=0.0,
            long_directions=frozenset({"buy"}),
            note="Switch between the top-ranked names on consecutive rebalance days.",
        )

        replay = _replay_variant(
            symbols=["600519.SH", "000858.SZ"],
            trade_days=trade_days,
            close_maps=close_maps,
            benchmark_map=benchmark_map,
            histories=histories,
            starting_cash=100_000.0,
            variant=variant,
        )

        self.assertEqual(replay["summary"]["rebalance_day_count"], 3)
        self.assertEqual(replay["summary"]["mean_rebalance_interval_days"], 1.0)

    def test_cli_phase5_holding_policy_experiment_can_write_artifact(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = main(
                [
                    "phase5-holding-policy-experiment",
                    "--database-url",
                    self.database_url,
                    "--experiment-id",
                    "profitability_signal_threshold_sweep_v1",
                    "--write-artifact",
                ]
            )

        self.assertEqual(exit_code, 0)
        rendered = stdout.getvalue()
        self.assertIn('"artifact_id": "phase5-holding-policy-experiment:profitability_signal_threshold_sweep_v1:', rendered)
        artifact_root = artifact_root_from_database_url(self.database_url)
        with session_scope(self.database_url) as session:
            payload = build_phase5_holding_policy_experiment(
                session,
                experiment_id="profitability_signal_threshold_sweep_v1",
            )
        artifact = read_phase5_holding_policy_experiment_artifact(
            phase5_holding_policy_experiment_artifact_id(payload),
            root=artifact_root,
        )
        self.assertEqual(artifact.experiment_id, "profitability_signal_threshold_sweep_v1")
        self.assertEqual(artifact.summary["variant_count"], 3)
        self.assertEqual(artifact.decision["baseline_variant_id"], "baseline_top5_weight20_conf0")


if __name__ == "__main__":
    unittest.main()
