from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import select

from ashare_evidence.cli import main
from ashare_evidence.db import init_database, session_scope
from ashare_evidence.models import PaperPortfolio
from ashare_evidence.phase2.holding_policy_study import (
    build_phase5_holding_policy_study,
    build_phase5_holding_policy_study_artifact,
    evaluate_phase5_holding_policy_governance,
    evaluate_phase5_holding_policy_promotion_gate,
    evaluate_phase5_holding_policy_redesign_diagnostics,
    recommend_phase5_holding_policy_redesign_experiments,
    phase5_holding_policy_study_artifact_id,
)
from ashare_evidence.research_artifact_store import (
    artifact_root_from_database_url,
    read_backtest_artifact,
    read_phase5_holding_policy_study_artifact,
    write_backtest_artifact,
)
from tests.fixtures import seed_watchlist_fixture


class Phase5HoldingPolicyStudyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "phase5-holding-policy.db"
        self.database_url = f"sqlite:///{database_path}"
        init_database(self.database_url)
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_build_phase5_holding_policy_study_summarizes_auto_model_portfolios(self) -> None:
        with session_scope(self.database_url) as session:
            payload = build_phase5_holding_policy_study(session)

        self.assertEqual(payload["summary"]["selected_portfolio_count"], 1)
        self.assertEqual(payload["summary"]["included_portfolio_count"], 1)
        self.assertEqual(payload["decision"]["approval_state"], "research_candidate_only")
        self.assertEqual(payload["decision"]["gate_status"], "draft_gate_blocked")
        self.assertEqual(
            payload["decision"]["governance_status"],
            "maintain_non_promotion_until_gate_passes",
        )
        self.assertEqual(payload["decision"]["governance_action"], "continue_gate_research_without_promotion")
        self.assertEqual(payload["decision"]["redesign_status"], "no_structured_redesign_signal")
        self.assertEqual(payload["decision"]["redesign_focus_areas"], [])
        self.assertEqual(payload["decision"]["redesign_triggered_signal_ids"], [])
        self.assertEqual(payload["decision"]["redesign_primary_experiment_ids"], [])
        self.assertIn("included_portfolio_count", payload["decision"]["failing_gate_ids"])
        self.assertIsNotNone(payload["summary"]["mean_turnover"])
        self.assertIsNotNone(payload["cost_sensitivity"]["mean_annualized_excess_return_after_baseline_cost"])
        self.assertEqual(payload["holding_stability"]["portfolio_count"], 1)

    def test_phase5_holding_policy_study_artifact_id_is_stable_for_same_evidence_set(self) -> None:
        with session_scope(self.database_url) as session:
            payload = build_phase5_holding_policy_study(session)

        artifact = build_phase5_holding_policy_study_artifact(payload)
        self.assertEqual(artifact.artifact_id, phase5_holding_policy_study_artifact_id(payload))
        self.assertEqual(artifact.decision["approval_state"], "research_candidate_only")
        self.assertEqual(artifact.decision["gate_status"], "draft_gate_blocked")
        self.assertEqual(
            artifact.decision["governance_status"],
            "maintain_non_promotion_until_gate_passes",
        )
        self.assertEqual(artifact.decision["governance_action"], "continue_gate_research_without_promotion")
        self.assertEqual(artifact.decision["redesign_status"], "no_structured_redesign_signal")

    def test_build_phase5_holding_policy_study_falls_back_to_portfolio_key_backtest_artifact(self) -> None:
        artifact_root = artifact_root_from_database_url(self.database_url)
        with session_scope(self.database_url) as session:
            portfolio = session.scalars(
                select(PaperPortfolio).where(PaperPortfolio.mode == "auto_model")
            ).one()
            legacy_artifact = read_backtest_artifact("portfolio-backtest:portfolio-auto-live", root=artifact_root)
            runtime_portfolio_key = "sim-20260427115855-fd6666-model"
            portfolio.portfolio_key = runtime_portfolio_key
            portfolio.portfolio_payload = {
                **dict(portfolio.portfolio_payload or {}),
                "backtest_artifact_id": "portfolio-backtest:portfolio-auto-live",
            }
            runtime_artifact = legacy_artifact.model_copy(update={"artifact_id": f"portfolio-backtest:{runtime_portfolio_key}"})
            write_backtest_artifact(runtime_artifact, root=artifact_root)
            (artifact_root / "backtests" / "portfolio-backtest:portfolio-auto-live.json").unlink()
            session.flush()

        with session_scope(self.database_url) as session:
            payload = build_phase5_holding_policy_study(session)

        self.assertEqual(payload["summary"]["included_portfolio_count"], 1)
        self.assertEqual(payload["portfolios"][0]["portfolio_key"], "sim-20260427115855-fd6666-model")
        self.assertEqual(
            payload["portfolios"][0]["validation_artifact_id"],
            "portfolio-backtest:sim-20260427115855-fd6666-model",
        )
        self.assertIsNone(payload["portfolios"][0]["exclusion_reason"])

    def test_cli_phase5_holding_policy_study_can_write_artifact(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = main(["phase5-holding-policy-study", "--database-url", self.database_url, "--write-artifact"])

        self.assertEqual(exit_code, 0)
        rendered = stdout.getvalue()
        self.assertIn('"artifact_id": "phase5-holding-policy-study:auto_model:', rendered)
        artifact_root = artifact_root_from_database_url(self.database_url)
        with session_scope(self.database_url) as session:
            payload = build_phase5_holding_policy_study(session)
        artifact = read_phase5_holding_policy_study_artifact(
            phase5_holding_policy_study_artifact_id(payload),
            root=artifact_root,
        )
        self.assertEqual(artifact.decision["approval_state"], "research_candidate_only")
        self.assertEqual(artifact.decision["gate_status"], "draft_gate_blocked")
        self.assertEqual(artifact.decision["governance_action"], "continue_gate_research_without_promotion")
        self.assertEqual(artifact.decision["redesign_status"], "no_structured_redesign_signal")
        self.assertEqual(artifact.summary["included_portfolio_count"], 1)

    def test_evaluate_phase5_holding_policy_promotion_gate_can_report_pass(self) -> None:
        gate = evaluate_phase5_holding_policy_promotion_gate(
            summary={
                "included_portfolio_count": 3,
                "mean_turnover": 0.22,
            },
            cost_sensitivity={
                "mean_annualized_excess_return_after_baseline_cost": 0.08,
                "positive_after_baseline_cost_portfolio_count": 2,
            },
            holding_stability={
                "mean_rebalance_interval_days": 12.0,
            },
        )

        self.assertEqual(gate["gate_status"], "draft_gate_passed_pending_approval")
        self.assertEqual(gate["failing_gate_ids"], [])

    def test_evaluate_phase5_holding_policy_governance_recommends_redesign_for_profitability_blockers(self) -> None:
        governance = evaluate_phase5_holding_policy_governance(
            gate={
                "gate_status": "draft_gate_blocked",
                "failing_gate_ids": [
                    "after_cost_excess_non_negative",
                    "positive_after_cost_portfolio_ratio",
                ],
                "incomplete_gate_ids": [],
            }
        )

        self.assertEqual(
            governance["governance_status"],
            "maintain_non_promotion_prioritize_policy_redesign",
        )
        self.assertEqual(governance["governance_action"], "prioritize_policy_redesign")
        self.assertEqual(
            governance["redesign_trigger_gate_ids"],
            [
                "after_cost_excess_non_negative",
                "positive_after_cost_portfolio_ratio",
            ],
        )

    def test_evaluate_phase5_holding_policy_redesign_diagnostics_identifies_profitability_and_exposure_signals(self) -> None:
        diagnostics = evaluate_phase5_holding_policy_redesign_diagnostics(
            summary={
                "included_portfolio_count": 3,
                "mean_invested_ratio": 0.08,
                "mean_active_position_count": 1.0,
            },
            cost_sensitivity={
                "mean_annualized_excess_return_after_baseline_cost": -0.12,
                "positive_after_baseline_cost_portfolio_count": 0,
            },
            gate={
                "gate_status": "draft_gate_blocked",
                "failing_gate_ids": [
                    "after_cost_excess_non_negative",
                    "positive_after_cost_portfolio_ratio",
                ],
                "incomplete_gate_ids": [],
            },
            governance={
                "governance_action": "prioritize_policy_redesign",
            },
        )

        self.assertEqual(diagnostics["redesign_status"], "prioritize_policy_redesign")
        self.assertEqual(
            diagnostics["focus_areas"],
            ["after_cost_profitability", "portfolio_construction"],
        )
        self.assertIn("after_cost_excess_non_negative", diagnostics["triggered_signal_ids"])
        self.assertIn("mean_invested_ratio_floor", diagnostics["triggered_signal_ids"])
        self.assertIn("mean_active_position_count_floor", diagnostics["triggered_signal_ids"])

    def test_recommend_phase5_holding_policy_redesign_experiments_prioritizes_one_primary_per_focus_area(self) -> None:
        recommendations = recommend_phase5_holding_policy_redesign_experiments(
            redesign={
                "focus_areas": ["after_cost_profitability", "portfolio_construction"],
                "triggered_signal_ids": [
                    "after_cost_excess_non_negative",
                    "positive_after_cost_portfolio_ratio",
                    "mean_invested_ratio_floor",
                ],
            }
        )

        self.assertEqual(
            recommendations["primary_experiment_ids"],
            [
                "profitability_signal_threshold_sweep_v1",
                "construction_max_position_count_sweep_v1",
            ],
        )
        self.assertEqual(recommendations["candidate_count"], 4)
        self.assertEqual(
            recommendations["candidates"][0]["experiment_id"],
            "construction_max_position_count_sweep_v1",
        )
        self.assertEqual(
            recommendations["candidates"][1]["experiment_id"],
            "profitability_signal_threshold_sweep_v1",
        )


if __name__ == "__main__":
    unittest.main()
