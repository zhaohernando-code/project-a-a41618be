from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from ashare_evidence.db import init_database, session_scope
from ashare_evidence.runtime_ops import run_operations_tick
from tests.fixtures import seed_watchlist_fixture


class RuntimeOpsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "runtime-ops.db"
        self.database_url = f"sqlite:///{database_path}"
        init_database(self.database_url)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_tick_skips_when_market_is_closed(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
            with patch("ashare_evidence.runtime_ops.sync_intraday_market") as sync_mock:
                result = run_operations_tick(
                    session,
                    now=datetime(2026, 4, 25, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
                )

        self.assertFalse(result["ran"])
        self.assertEqual(result["reason"], "market_closed")
        sync_mock.assert_not_called()

    def test_tick_refreshes_intraday_and_attempts_simulation_advance_during_market_hours(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
            with patch(
                "ashare_evidence.runtime_ops.sync_intraday_market",
                return_value={"latest_market_data_at": "2026-04-28T02:35:00+00:00"},
            ) as sync_mock, patch(
                "ashare_evidence.runtime_ops.advance_running_simulation_session",
                return_value=None,
            ) as advance_mock:
                result = run_operations_tick(
                    session,
                    now=datetime(2026, 4, 28, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
                )

        self.assertTrue(result["ran"])
        self.assertTrue(result["intraday_refreshed"])
        self.assertFalse(result["simulation_advanced"])
        sync_mock.assert_called_once()
        advance_mock.assert_called_once()
