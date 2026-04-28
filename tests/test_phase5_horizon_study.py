from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import select

from ashare_evidence.cli import main
from ashare_evidence.db import init_database, session_scope
from ashare_evidence.models import Recommendation, Stock
from ashare_evidence.phase2.horizon_study import (
    build_phase5_horizon_study,
    build_phase5_horizon_study_artifact,
    phase5_horizon_study_artifact_id,
)
from ashare_evidence.phase2.phase5_contract import PHASE5_CONTRACT_VERSION, PHASE5_PRIMARY_HORIZON_STATUS
from ashare_evidence.research_artifact_store import (
    artifact_root_from_database_url,
    read_phase5_horizon_study_artifact,
)
from tests.fixtures import seed_watchlist_fixture


def _comparison_payload(
    *,
    leader_horizon: int,
    horizon_values: dict[int, tuple[float, float, float]],
) -> dict[str, object]:
    ordered = sorted(
        horizon_values.items(),
        key=lambda item: (item[1][0], item[1][1], item[1][2]),
        reverse=True,
    )
    candidates = []
    for rank, (horizon, (net_excess, rank_ic_mean, positive_excess_rate)) in enumerate(ordered, start=1):
        candidates.append(
            {
                "rank": rank,
                "horizon": horizon,
                "artifact_id": f"validation-metrics:test:{horizon}d",
                "sample_count": 83,
                "net_excess_return": net_excess,
                "rank_ic_mean": rank_ic_mean,
                "positive_excess_rate": positive_excess_rate,
                "turnover_mean": 0.12,
            }
        )
    leader = next(item for item in candidates if item["horizon"] == leader_horizon)
    return {
        "contract_version": PHASE5_CONTRACT_VERSION,
        "primary_horizon_status": PHASE5_PRIMARY_HORIZON_STATUS,
        "selection_readiness": "comparison_ready",
        "selection_rule": "rank_by_net_excess_return_then_rank_ic_mean_then_positive_excess_rate",
        "recommended_research_leader": leader,
        "candidates": candidates,
        "walk_forward_window_count": 24,
        "coverage_status": "full_baseline",
    }


class Phase5HorizonStudyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "phase5-study.db"
        self.database_url = f"sqlite:///{database_path}"
        init_database(self.database_url)
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
            self._write_phase5_payloads(session)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_phase5_payloads(self, session) -> None:
        fixture_values = {
            "600519.SH": [
                (10, {10: (0.032, 0.11, 0.62), 20: (0.011, 0.07, 0.57), 40: (-0.18, -0.04, 0.41)}),
                (10, {10: (0.029, 0.10, 0.60), 20: (0.012, 0.06, 0.55), 40: (-0.16, -0.03, 0.40)}),
            ],
            "300750.SZ": [
                (10, {10: (0.018, 0.05, 0.54), 20: (0.006, 0.03, 0.52), 40: (-0.12, -0.02, 0.38)}),
                (10, {10: (0.017, 0.04, 0.53), 20: (0.005, 0.02, 0.51), 40: (-0.11, -0.02, 0.37)}),
            ],
            "601318.SH": [
                (20, {10: (0.012, 0.01, 0.49), 20: (0.026, 0.08, 0.58), 40: (-0.09, -0.01, 0.35)}),
                (20, {10: (0.011, 0.01, 0.48), 20: (0.025, 0.07, 0.57), 40: (-0.08, -0.01, 0.34)}),
            ],
        }
        for symbol, snapshots in fixture_values.items():
            recommendations = session.scalars(
                select(Recommendation)
                .join(Recommendation.stock)
                .where(Stock.symbol == symbol)
                .order_by(Recommendation.generated_at.desc())
            ).all()
            for recommendation, (leader_horizon, horizon_values) in zip(recommendations, snapshots, strict=True):
                payload = dict(recommendation.recommendation_payload or {})
                historical_validation = dict(payload.get("historical_validation") or {})
                metrics = dict(historical_validation.get("metrics") or {})
                metrics["walk_forward"] = {
                    "coverage_status": "full_baseline",
                    "window_count": 24,
                    "available_observation_count": 683,
                    "evaluation_observation_count": 83,
                }
                metrics["candidate_horizon_comparison"] = _comparison_payload(
                    leader_horizon=leader_horizon,
                    horizon_values=horizon_values,
                )
                historical_validation["benchmark_definition"] = (
                    "active_watchlist_equal_weight_proxy + primary_sector_equal_weight_proxy"
                    if symbol == "600519.SH"
                    else "active_watchlist_equal_weight_proxy"
                )
                historical_validation["metrics"] = metrics
                payload["historical_validation"] = historical_validation
                recommendation.recommendation_payload = payload
            session.flush()

    def test_build_phase5_horizon_study_latest_scope(self) -> None:
        with session_scope(self.database_url) as session:
            payload = build_phase5_horizon_study(session)

        self.assertEqual(payload["summary"]["included_record_count"], 3)
        self.assertEqual(payload["summary"]["excluded_record_count"], 1)
        self.assertEqual(payload["leaderboard"][0]["horizon"], 10)
        self.assertEqual(payload["leaderboard"][0]["leader_count"], 2)
        self.assertEqual(payload["leaderboard"][1]["horizon"], 20)
        self.assertEqual(payload["decision"]["candidate_frontier"], [10, 20])
        self.assertEqual(payload["decision"]["lagging_horizons"], [40])
        self.assertEqual(payload["decision"]["approval_state"], "split_leadership")

    def test_build_phase5_horizon_study_include_history_tracks_stability(self) -> None:
        with session_scope(self.database_url) as session:
            payload = build_phase5_horizon_study(session, include_history=True)

        self.assertEqual(payload["summary"]["included_record_count"], 6)
        self.assertEqual(payload["summary"]["included_as_of_date_count"], 2)
        self.assertEqual(payload["leaderboard"][0]["horizon"], 10)
        self.assertEqual(payload["leaderboard"][0]["leader_count"], 4)
        self.assertEqual(payload["leaderboard"][1]["horizon"], 20)
        self.assertEqual(payload["leaderboard"][1]["leader_count"], 2)
        self.assertEqual(payload["time_stability"]["stable_symbol_count"], 3)
        self.assertEqual(payload["time_stability"]["unstable_symbol_count"], 0)

    def test_phase5_horizon_study_artifact_id_is_stable_for_same_evidence_set(self) -> None:
        with session_scope(self.database_url) as session:
            payload = build_phase5_horizon_study(session)

        artifact = build_phase5_horizon_study_artifact(payload)
        self.assertEqual(
            artifact.artifact_id,
            phase5_horizon_study_artifact_id(payload),
        )
        self.assertEqual(artifact.decision["approval_state"], "split_leadership")

    def test_cli_phase5_horizon_study_outputs_json(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = main(["phase5-horizon-study", "--database-url", self.database_url])

        self.assertEqual(exit_code, 0)
        rendered = stdout.getvalue()
        self.assertIn('"approval_state": "split_leadership"', rendered)
        self.assertIn('"lagging_horizons": [', rendered)

    def test_cli_phase5_horizon_study_can_write_artifact(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = main(["phase5-horizon-study", "--database-url", self.database_url, "--write-artifact"])

        self.assertEqual(exit_code, 0)
        rendered = stdout.getvalue()
        self.assertIn('"artifact_id": "phase5-horizon-study:latest:active_watchlist:', rendered)
        artifact_root = artifact_root_from_database_url(self.database_url)
        with session_scope(self.database_url) as session:
            payload = build_phase5_horizon_study(session)
        artifact = read_phase5_horizon_study_artifact(
            phase5_horizon_study_artifact_id(payload),
            root=artifact_root,
        )
        self.assertEqual(artifact.summary["included_record_count"], 3)
        self.assertEqual(artifact.decision["approval_state"], "split_leadership")


if __name__ == "__main__":
    unittest.main()
