from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import select

from ashare_evidence.cli import main
from ashare_evidence.dashboard import list_candidate_recommendations
from ashare_evidence.db import init_database, session_scope
from ashare_evidence.models import PaperPortfolio, SimulationSession
from ashare_evidence.research_artifact_store import (
    artifact_root_from_database_url,
    read_phase5_holding_policy_study_artifact,
    read_phase5_horizon_study_artifact,
)
from ashare_evidence.simulation import end_simulation_session, get_simulation_workspace
from tests.fixtures import seed_watchlist_fixture


class CliRuntimeRefreshTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "runtime.db"
        self.database_url = f"sqlite:///{database_path}"
        init_database(self.database_url)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_refresh_runtime_data_refreshes_existing_watchlist_and_simulation(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
            ended = end_simulation_session(session, confirm=True)
            ended_session_key = ended["session"]["session_key"]

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = main(["refresh-runtime-data", "--database-url", self.database_url])

        self.assertEqual(exit_code, 0)
        with session_scope(self.database_url) as session:
            candidates = list_candidate_recommendations(session, limit=8)
            workspace = get_simulation_workspace(session)

        self.assertTrue(candidates["items"])
        self.assertEqual(workspace["session"]["status"], "running")
        self.assertNotEqual(workspace["session"]["session_key"], ended_session_key)
        self.assertEqual(workspace["session"]["current_step"], 1)
        self.assertIn("intraday_market", stdout.getvalue())
        self.assertIn("refreshed_symbols", stdout.getvalue())
        self.assertIn('"simulation_current_step": 1', stdout.getvalue())

    def test_refresh_runtime_data_steps_auto_execute_model_session(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
            workspace = get_simulation_workspace(session)
            self.assertFalse(workspace["session"]["auto_execute_model"])
            simulation_session = session.scalar(select(SimulationSession))
            assert simulation_session is not None
            simulation_session.auto_execute_model = True
            simulation_session.session_payload = {
                **(simulation_session.session_payload or {}),
                "requested_auto_execute_model": True,
            }
            session.commit()

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = main(["refresh-runtime-data", "--database-url", self.database_url, "--analysis-only"])

        self.assertEqual(exit_code, 0)
        with session_scope(self.database_url) as session:
            workspace = get_simulation_workspace(session)

        self.assertEqual(workspace["session"]["status"], "running")
        self.assertEqual(workspace["session"]["current_step"], 1)
        self.assertTrue(workspace["session"]["auto_execute_model"])
        self.assertGreaterEqual(workspace["model_track"]["portfolio"]["order_count"], 1)
        self.assertTrue(
            any(item["track"] == "model" and item["event_type"] == "order_filled" for item in workspace["timeline"])
        )
        self.assertIn('"simulation_current_step": 1', stdout.getvalue())

    def test_phase5_daily_refresh_runs_refresh_and_writes_both_horizon_snapshots(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = main(["phase5-daily-refresh", "--database-url", self.database_url, "--skip-simulation"])

        self.assertEqual(exit_code, 0)
        rendered = stdout.getvalue()
        self.assertIn('"phase5_horizon_studies"', rendered)
        self.assertIn('"phase5_holding_policy_study"', rendered)
        self.assertIn('"latest"', rendered)
        self.assertIn('"history"', rendered)
        self.assertIn('"artifact_id": "phase5-horizon-study:latest:active_watchlist:', rendered)
        self.assertIn('"artifact_id": "phase5-horizon-study:history:active_watchlist:', rendered)
        self.assertIn('"artifact_id": "phase5-holding-policy-study:auto_model:', rendered)

        payload = json.loads(rendered)
        latest_artifact_id = payload["phase5_horizon_studies"]["latest"]["artifact"]["artifact_id"]
        history_artifact_id = payload["phase5_horizon_studies"]["history"]["artifact"]["artifact_id"]
        holding_policy_artifact_id = payload["phase5_holding_policy_study"]["artifact"]["artifact_id"]

        artifact_root = artifact_root_from_database_url(self.database_url)
        latest_artifact = read_phase5_horizon_study_artifact(
            latest_artifact_id,
            root=artifact_root,
        )
        history_artifact = read_phase5_horizon_study_artifact(
            history_artifact_id,
            root=artifact_root,
        )
        holding_policy_artifact = read_phase5_holding_policy_study_artifact(
            holding_policy_artifact_id,
            root=artifact_root,
        )
        self.assertEqual(
            latest_artifact.decision["approval_state"],
            payload["phase5_horizon_studies"]["latest"]["approval_state"],
        )
        self.assertEqual(
            history_artifact.decision["approval_state"],
            payload["phase5_horizon_studies"]["history"]["approval_state"],
        )
        self.assertEqual(
            latest_artifact.summary["included_as_of_date_count"],
            payload["phase5_horizon_studies"]["latest"]["included_as_of_date_count"],
        )
        self.assertEqual(
            history_artifact.summary["included_as_of_date_count"],
            payload["phase5_horizon_studies"]["history"]["included_as_of_date_count"],
        )
        self.assertEqual(
            holding_policy_artifact.decision["approval_state"],
            payload["phase5_holding_policy_study"]["approval_state"],
        )
        self.assertEqual(
            holding_policy_artifact.decision["gate_status"],
            payload["phase5_holding_policy_study"]["gate_status"],
        )
        self.assertEqual(
            holding_policy_artifact.decision["redesign_status"],
            payload["phase5_holding_policy_study"]["redesign_status"],
        )
        self.assertEqual(
            holding_policy_artifact.summary["included_portfolio_count"],
            payload["phase5_holding_policy_study"]["included_portfolio_count"],
        )
        self.assertIn(
            "after_cost_profitability",
            payload["phase5_holding_policy_study"]["redesign_focus_areas"],
        )
        self.assertEqual(
            payload["phase5_holding_policy_study"]["redesign_primary_experiment_ids"],
            ["profitability_signal_threshold_sweep_v1"],
        )
        with session_scope(self.database_url) as session:
            portfolios = session.scalars(select(PaperPortfolio).order_by(PaperPortfolio.portfolio_key.asc())).all()
        self.assertTrue(portfolios)
        for portfolio in portfolios:
            payload_view = dict(portfolio.portfolio_payload or {})
            self.assertEqual(
                payload_view.get("backtest_artifact_id"),
                f"portfolio-backtest:{portfolio.portfolio_key}",
            )
            self.assertEqual(
                payload_view.get("validation_manifest_id"),
                "rolling-validation:phase2-portfolio-backtests",
            )

    def test_phase5_daily_refresh_rebuilds_stepped_model_portfolio_in_same_run(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
            workspace = get_simulation_workspace(session)
            self.assertFalse(workspace["session"]["auto_execute_model"])
            simulation_session = session.scalar(select(SimulationSession))
            assert simulation_session is not None
            simulation_session.auto_execute_model = True
            simulation_session.session_payload = {
                **(simulation_session.session_payload or {}),
                "requested_auto_execute_model": True,
            }
            session.commit()

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = main(["phase5-daily-refresh", "--database-url", self.database_url, "--analysis-only"])

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["refresh"]["simulation_current_step"], 1)
        self.assertGreaterEqual(payload["phase5_holding_policy_study"]["included_portfolio_count"], 2)

        artifact_root = artifact_root_from_database_url(self.database_url)
        holding_policy_artifact = read_phase5_holding_policy_study_artifact(
            payload["phase5_holding_policy_study"]["artifact"]["artifact_id"],
            root=artifact_root,
        )
        self.assertGreaterEqual(holding_policy_artifact.summary["included_portfolio_count"], 2)
        self.assertGreaterEqual(holding_policy_artifact.summary["total_order_count"], 1)
        self.assertEqual(holding_policy_artifact.summary["excluded_reasons"], {})

        with session_scope(self.database_url) as session:
            portfolios = session.scalars(
                select(PaperPortfolio)
                .where(PaperPortfolio.mode == "auto_model")
                .order_by(PaperPortfolio.created_at.desc())
            ).all()
        self.assertTrue(portfolios)
        latest_payload = dict(portfolios[0].portfolio_payload or {})
        self.assertEqual(
            latest_payload.get("validation_manifest_id"),
            "rolling-validation:phase2-portfolio-backtests",
        )

    def test_phase5_horizon_study_write_artifact_marks_reused_snapshot(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)

        first_stdout = io.StringIO()
        with contextlib.redirect_stdout(first_stdout):
            first_exit = main(["phase5-horizon-study", "--database-url", self.database_url, "--write-artifact"])
        self.assertEqual(first_exit, 0)
        self.assertIn('"reused_existing_snapshot": false', first_stdout.getvalue())

        second_stdout = io.StringIO()
        with contextlib.redirect_stdout(second_stdout):
            second_exit = main(["phase5-horizon-study", "--database-url", self.database_url, "--write-artifact"])
        self.assertEqual(second_exit, 0)
        self.assertIn('"reused_existing_snapshot": true', second_stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
