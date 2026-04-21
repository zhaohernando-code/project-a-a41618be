from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ashare_evidence.dashboard import bootstrap_dashboard_demo
from ashare_evidence.db import init_database, session_scope
from ashare_evidence.simulation import (
    end_simulation_session,
    get_simulation_workspace,
    pause_simulation_session,
    place_manual_order,
    restart_simulation_session,
    resume_simulation_session,
    start_simulation_session,
    step_simulation_session,
)


class SimulationWorkspaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "simulation.db"
        self.database_url = f"sqlite:///{database_path}"
        init_database(self.database_url)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_workspace_bootstrap_exposes_dual_track_session(self) -> None:
        with session_scope(self.database_url) as session:
            bootstrap_dashboard_demo(session)

        with session_scope(self.database_url) as session:
            workspace = get_simulation_workspace(session)

        self.assertEqual(workspace["session"]["status"], "draft")
        self.assertTrue(workspace["controls"]["can_start"])
        self.assertGreaterEqual(len(workspace["session"]["watch_symbols"]), 4)
        self.assertTrue(workspace["kline"]["points"])
        self.assertEqual(workspace["manual_track"]["portfolio"]["starting_cash"], workspace["session"]["initial_cash"])
        self.assertEqual(workspace["model_track"]["portfolio"]["starting_cash"], workspace["session"]["initial_cash"])

    def test_session_can_start_step_trade_pause_resume_and_end(self) -> None:
        with session_scope(self.database_url) as session:
            bootstrap_dashboard_demo(session)

        with session_scope(self.database_url) as session:
            started = start_simulation_session(session)
            self.assertEqual(started["session"]["status"], "running")

            stepped = step_simulation_session(session)
            self.assertEqual(stepped["session"]["current_step"], 1)
            self.assertGreaterEqual(len(stepped["timeline"]), 3)

            traded = place_manual_order(
                session,
                symbol=stepped["session"]["focus_symbol"] or stepped["session"]["watch_symbols"][0],
                side="buy",
                quantity=100,
                reason="参考模型建议后做人工确认买入。",
            )
            self.assertEqual(traded["manual_track"]["portfolio"]["order_count"], 1)
            self.assertTrue(any(item["manual_action"] != "未操作" for item in traded["decision_differences"]))

            paused = pause_simulation_session(session)
            self.assertEqual(paused["session"]["status"], "paused")

            resumed = resume_simulation_session(session)
            self.assertEqual(resumed["session"]["status"], "running")

            ended = end_simulation_session(session, confirm=True)
            self.assertEqual(ended["session"]["status"], "ended")
            self.assertFalse(ended["controls"]["can_end"])

    def test_restart_creates_new_session_key(self) -> None:
        with session_scope(self.database_url) as session:
            bootstrap_dashboard_demo(session)
            initial = get_simulation_workspace(session)
            initial_key = initial["session"]["session_key"]
            restarted = restart_simulation_session(session)

        self.assertNotEqual(restarted["session"]["session_key"], initial_key)
        self.assertEqual(restarted["session"]["status"], "running")
        self.assertEqual(restarted["session"]["restart_count"], 1)


if __name__ == "__main__":
    unittest.main()
