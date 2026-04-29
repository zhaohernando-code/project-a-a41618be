import tempfile
import unittest

from ashare_evidence.dashboard import list_candidate_recommendations
from ashare_evidence.db import init_database, session_scope
from tests.fixtures import seed_watchlist_fixture


class DashboardCandidatePriceChartTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_url = f"sqlite:///{self.temp_dir.name}/test.db"
        init_database(self.database_url)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_candidates_include_real_daily_price_chart(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)

        with session_scope(self.database_url) as session:
            candidates = list_candidate_recommendations(session, limit=8)

        self.assertTrue(candidates["items"])
        first_candidate = candidates["items"][0]
        self.assertGreaterEqual(len(first_candidate["price_chart"]), 2)
        self.assertIn("close_price", first_candidate["price_chart"][0])


if __name__ == "__main__":
    unittest.main()
