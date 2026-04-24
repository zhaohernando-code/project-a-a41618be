from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from ashare_evidence.cli import main
from ashare_evidence.dashboard import bootstrap_dashboard_demo, list_candidate_recommendations
from ashare_evidence.db import init_database, session_scope
from ashare_evidence.simulation import end_simulation_session, get_simulation_workspace


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
            bootstrap_dashboard_demo(session)
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
        self.assertTrue(all("2026-04-14" not in item["as_of_data_time"].isoformat() for item in candidates["items"]))
        self.assertEqual(workspace["session"]["status"], "running")
        self.assertNotEqual(workspace["session"]["session_key"], ended_session_key)
        self.assertNotIn("2026-04-14", workspace["session"]["last_data_time"].isoformat())
        self.assertIn("refreshed_symbols", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
