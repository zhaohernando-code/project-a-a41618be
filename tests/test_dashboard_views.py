from __future__ import annotations

from datetime import datetime, timezone
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from ashare_evidence.dashboard import bootstrap_dashboard_demo, get_glossary_entries, get_stock_dashboard, list_candidate_recommendations
from ashare_evidence.db import init_database, session_scope
from ashare_evidence.lineage import build_lineage
from ashare_evidence.models import Sector, SectorMembership, Stock
from ashare_evidence.operations import build_operations_dashboard
from ashare_evidence.watchlist import add_watchlist_symbol, list_watchlist_entries, refresh_watchlist_symbol, remove_watchlist_symbol


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

    def test_operations_dashboard_can_embed_simulation_workspace(self) -> None:
        with session_scope(self.database_url) as session:
            bootstrap_dashboard_demo(session)

        with session_scope(self.database_url) as session:
            operations = build_operations_dashboard(
                session,
                sample_symbol="600519.SH",
                include_simulation_workspace=True,
            )

        workspace = operations["simulation_workspace"]
        self.assertIsNotNone(workspace)
        assert workspace is not None
        self.assertEqual(workspace["session"]["status"], "draft")
        self.assertTrue(workspace["controls"]["can_start"])
        self.assertGreaterEqual(len(workspace["kline"]["points"]), 24)
        self.assertEqual(workspace["manual_track"]["portfolio"]["starting_cash"], workspace["session"]["initial_cash"])

    def test_operations_dashboard_scopes_simulation_to_active_watchlist(self) -> None:
        with session_scope(self.database_url) as session:
            bootstrap_dashboard_demo(session)
            add_watchlist_symbol(session, "688981", stock_name="中芯国际")
            remove_watchlist_symbol(session, "600519")

        with session_scope(self.database_url) as session:
            operations = build_operations_dashboard(session, sample_symbol="688981.SH")

        active_watchlist_symbols = {"300750.SZ", "601318.SH", "002594.SZ", "688981.SH"}
        replay_symbols = {item["symbol"] for item in operations["recommendation_replay"]}
        portfolio_symbols = {
            item["symbol"]
            for portfolio in operations["portfolios"]
            for item in [*portfolio["holdings"], *portfolio["recent_orders"]]
        }

        self.assertIn("688981.SH", replay_symbols)
        self.assertNotIn("600519.SH", replay_symbols)
        self.assertTrue(replay_symbols.issubset(active_watchlist_symbols))
        self.assertNotIn("600519.SH", portfolio_symbols)
        self.assertTrue(portfolio_symbols.issubset(active_watchlist_symbols))

    def test_operations_dashboard_tolerates_missing_sample_symbol(self) -> None:
        with session_scope(self.database_url) as session:
            bootstrap_dashboard_demo(session)
            add_watchlist_symbol(session, "688981", stock_name="中芯国际")
            remove_watchlist_symbol(session, "600519")

        with session_scope(self.database_url) as session:
            operations = build_operations_dashboard(session, sample_symbol="000001.SZ")

        replay_symbols = {item["symbol"] for item in operations["recommendation_replay"]}
        portfolio_symbols = {
            item["symbol"]
            for portfolio in operations["portfolios"]
            for item in [*portfolio["holdings"], *portfolio["recent_orders"]]
        }
        self.assertIn("688981.SH", replay_symbols)
        self.assertNotIn("600519.SH", replay_symbols)
        self.assertNotIn("600519.SH", portfolio_symbols)
        self.assertEqual(len(operations["portfolios"]), 2)

    def test_glossary_entries_cover_key_user_terms(self) -> None:
        glossary = get_glossary_entries()
        terms = {item["term"] for item in glossary}
        self.assertIn("滚动验证", terms)
        self.assertIn("降级条件", terms)
        self.assertIn("LLM 因子上限", terms)

    def test_watchlist_can_add_custom_symbol_and_remove_it(self) -> None:
        with session_scope(self.database_url) as session:
            bootstrap_dashboard_demo(session)
            item = add_watchlist_symbol(session, "688981", stock_name="中芯国际")

        self.assertEqual(item["symbol"], "688981.SH")
        self.assertEqual(item["name"], "中芯国际")

        with session_scope(self.database_url) as session:
            watchlist = list_watchlist_entries(session)
            candidates = list_candidate_recommendations(session, limit=10)
            dashboard = get_stock_dashboard(session, "688981.SH")

        self.assertIn("688981.SH", {entry["symbol"] for entry in watchlist["items"]})
        self.assertIn("688981.SH", {entry["symbol"] for entry in candidates["items"]})
        self.assertEqual(dashboard["stock"]["name"], "中芯国际")
        self.assertGreaterEqual(len(dashboard["price_chart"]), 24)

        with session_scope(self.database_url) as session:
            removal = remove_watchlist_symbol(session, "688981")

        self.assertTrue(removal["removed"])

        with session_scope(self.database_url) as session:
            candidates = list_candidate_recommendations(session, limit=10)

        self.assertNotIn("688981.SH", {entry["symbol"] for entry in candidates["items"]})

    def test_watchlist_resolves_known_stock_name_and_sector(self) -> None:
        with session_scope(self.database_url) as session:
            bootstrap_dashboard_demo(session)
            item = add_watchlist_symbol(session, "002028")

        self.assertEqual(item["symbol"], "002028.SZ")
        self.assertEqual(item["name"], "思源电气")

        with session_scope(self.database_url) as session:
            candidates = list_candidate_recommendations(session, limit=10)
            dashboard = get_stock_dashboard(session, "002028.SZ")

        candidate = next(entry for entry in candidates["items"] if entry["symbol"] == "002028.SZ")
        self.assertEqual(candidate["name"], "思源电气")
        self.assertEqual(candidate["sector"], "电力设备")
        self.assertEqual(dashboard["stock"]["name"], "思源电气")
        self.assertIn("电力设备", dashboard["hero"]["sector_tags"])
        self.assertNotIn("医药生物", dashboard["hero"]["sector_tags"])

    def test_refresh_watchlist_expires_wrong_legacy_sector_membership(self) -> None:
        with session_scope(self.database_url) as session:
            bootstrap_dashboard_demo(session)
            add_watchlist_symbol(session, "002028")

        with session_scope(self.database_url) as session:
            stock = session.scalar(select(Stock).where(Stock.symbol == "002028.SZ"))
            self.assertIsNotNone(stock)
            assert stock is not None

            sector_lineage = build_lineage(
                {"sector_code": "sw-pharmaceutical-biological", "name": "医药生物"},
                source_uri="test://sector/sw-pharmaceutical-biological",
                license_tag="internal-test",
                usage_scope="internal_research",
                redistribution_scope="none",
            )
            bad_sector = Sector(
                sector_code="sw-pharmaceutical-biological",
                name="医药生物",
                level="industry",
                definition_payload={"taxonomy": "申万一级", "provider": "test"},
                **sector_lineage,
            )
            session.add(bad_sector)
            session.flush()

            membership_lineage = build_lineage(
                {"symbol": "002028.SZ", "sector_code": bad_sector.sector_code},
                source_uri="test://membership/002028/sw-pharmaceutical-biological",
                license_tag="internal-test",
                usage_scope="internal_research",
                redistribution_scope="none",
            )
            session.add(
                SectorMembership(
                    membership_key="legacy-membership-002028-sw-pharmaceutical-biological",
                    stock_id=stock.id,
                    sector_id=bad_sector.id,
                    effective_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
                    effective_to=None,
                    is_primary=True,
                    membership_payload={"taxonomy": "申万一级", "weighting_hint": "legacy-wrong"},
                    **membership_lineage,
                )
            )
            session.commit()

        with session_scope(self.database_url) as session:
            refreshed = refresh_watchlist_symbol(session, "002028")
        self.assertEqual(refreshed["name"], "思源电气")

        with session_scope(self.database_url) as session:
            dashboard = get_stock_dashboard(session, "002028.SZ")
            as_of = dashboard["recommendation"]["as_of_data_time"]
            memberships = session.scalars(
                select(SectorMembership)
                .join(Stock)
                .where(Stock.symbol == "002028.SZ")
                .options(joinedload(SectorMembership.sector))
                .order_by(SectorMembership.effective_from.asc())
            ).all()
            active_at_latest = [
                membership
                for membership in memberships
                if membership.effective_from <= as_of and (membership.effective_to is None or membership.effective_to >= as_of)
            ]
        self.assertTrue(active_at_latest)
        self.assertNotIn("医药生物", {membership.sector.name for membership in active_at_latest})
        self.assertIn("电力设备", {membership.sector.name for membership in active_at_latest})


if __name__ == "__main__":
    unittest.main()
