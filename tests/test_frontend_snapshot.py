from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ashare_evidence.dashboard_demo import WATCHLIST_SYMBOLS
from ashare_evidence.frontend_snapshot import build_frontend_snapshot, export_frontend_snapshot


class FrontendSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "frontend-snapshot.db"
        self.database_url = f"sqlite:///{database_path}"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_build_snapshot_contains_all_watchlist_views(self) -> None:
        snapshot = build_frontend_snapshot(self.database_url)

        self.assertEqual(set(snapshot["stock_dashboards"]), set(WATCHLIST_SYMBOLS))
        self.assertEqual(set(snapshot["operations_dashboards"]), set(WATCHLIST_SYMBOLS))
        self.assertEqual({item["symbol"] for item in snapshot["watchlist"]["items"]}, set(WATCHLIST_SYMBOLS))
        self.assertEqual(snapshot["bootstrap"]["candidate_count"], len(WATCHLIST_SYMBOLS))
        json.dumps(snapshot, ensure_ascii=False, default=str)

    def test_export_snapshot_writes_json_file(self) -> None:
        output_path = Path(self.temp_dir.name) / "offline-snapshot.json"

        export_frontend_snapshot(str(output_path), self.database_url)

        self.assertTrue(output_path.exists())
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertIn("watchlist", payload)
        self.assertIn("candidates", payload)
        self.assertIn("stock_dashboards", payload)


if __name__ == "__main__":
    unittest.main()
