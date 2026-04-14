from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ashare_evidence.dashboard import bootstrap_dashboard_demo, get_glossary_entries, get_stock_dashboard, list_candidate_recommendations
from ashare_evidence.db import init_database, session_scope
from ashare_evidence.operations import build_operations_dashboard


class DashboardViewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "dashboard.db"
        self.database_url = f"sqlite:///{database_path}"
        init_database(self.database_url)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_dashboard_bootstrap_builds_multi_stock_candidates(self) -> None:
        with session_scope(self.database_url) as session:
            payload = bootstrap_dashboard_demo(session)
            self.assertEqual(payload["candidate_count"], 4)
            self.assertEqual(payload["recommendation_count"], 8)

        with session_scope(self.database_url) as session:
            candidates = list_candidate_recommendations(session, limit=8)

        self.assertEqual(len(candidates["items"]), 4)
        self.assertEqual([item["rank"] for item in candidates["items"]], [1, 2, 3, 4])
        candidate_symbols = {item["symbol"] for item in candidates["items"]}
        self.assertEqual(candidate_symbols, {"600519.SH", "300750.SZ", "601318.SH", "002594.SZ"})
        directions = {item["direction"] for item in candidates["items"]}
        self.assertIn("buy", directions)
        self.assertTrue({"reduce", "risk_alert"} & directions)
        self.assertTrue(all(item["change_summary"] for item in candidates["items"]))

    def test_stock_dashboard_contains_change_trace_and_follow_up_context(self) -> None:
        with session_scope(self.database_url) as session:
            bootstrap_dashboard_demo(session)

        with session_scope(self.database_url) as session:
            dashboard = get_stock_dashboard(session, "600519.SH")

        self.assertEqual(dashboard["stock"]["symbol"], "600519.SH")
        self.assertTrue(dashboard["change"]["has_previous"])
        self.assertGreaterEqual(len(dashboard["price_chart"]), 24)
        self.assertGreaterEqual(len(dashboard["recent_news"]), 3)
        self.assertGreaterEqual(len(dashboard["glossary"]), 5)
        self.assertGreaterEqual(len(dashboard["follow_up"]["suggested_questions"]), 4)
        self.assertIn("请回答这个问题", dashboard["follow_up"]["copy_prompt"])
        self.assertTrue(dashboard["risk_panel"]["disclaimer"])
        self.assertGreaterEqual(len(dashboard["evidence"]), 6)
        self.assertEqual(len(dashboard["simulation_orders"]), 2)

    def test_operations_dashboard_contains_portfolios_replay_and_launch_gates(self) -> None:
        with session_scope(self.database_url) as session:
            bootstrap_dashboard_demo(session)

        with session_scope(self.database_url) as session:
            operations = build_operations_dashboard(session, sample_symbol="600519.SH")

        self.assertEqual(operations["overview"]["manual_portfolio_count"], 1)
        self.assertEqual(operations["overview"]["auto_portfolio_count"], 1)
        self.assertEqual(len(operations["portfolios"]), 2)
        self.assertGreaterEqual(len(operations["recommendation_replay"]), 4)
        self.assertGreaterEqual(len(operations["launch_gates"]), 5)
        self.assertTrue(all(portfolio["nav_history"] for portfolio in operations["portfolios"]))
        self.assertTrue(all(portfolio["recent_orders"] for portfolio in operations["portfolios"]))
        self.assertTrue(all(portfolio["rules"] for portfolio in operations["portfolios"]))
        first_gate = {gate["gate"] for gate in operations["launch_gates"]}
        self.assertIn("分离式模拟交易", first_gate)
        self.assertIn("A 股规则合规", first_gate)

    def test_glossary_entries_cover_key_user_terms(self) -> None:
        glossary = get_glossary_entries()
        terms = {item["term"] for item in glossary}
        self.assertIn("滚动验证", terms)
        self.assertIn("降级条件", terms)
        self.assertIn("LLM 因子上限", terms)


if __name__ == "__main__":
    unittest.main()
