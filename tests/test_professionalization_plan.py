from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy import select

from ashare_evidence.dashboard import get_stock_dashboard
from ashare_evidence.data_quality import build_data_quality_summary
from ashare_evidence.db import init_database, session_scope
from ashare_evidence.factor_observation import build_factor_observations, sweep_weights
from ashare_evidence.market_rules import board_rule
from ashare_evidence.models import FeatureSnapshot, NewsEntityLink, NewsItem, Stock
from ashare_evidence.operations import build_operations_detail, build_operations_summary
from ashare_evidence.schemas import StockDashboardResponse
from tests.fixtures import seed_watchlist_fixture


class ProfessionalizationPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_url = f"sqlite:///{Path(self.temp_dir.name) / 'professionalization.db'}"
        init_database(self.database_url)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_data_quality_snapshot_scores_and_missing_news_is_soft_gap(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session, symbols=("600519.SH",))
            session.execute(delete(NewsEntityLink))
            session.execute(delete(NewsItem))
            session.commit()

        with session_scope(self.database_url) as session:
            summary = build_data_quality_summary(session, symbols=["600519.SH"])

        self.assertEqual(summary["symbol_count"], 1)
        item = summary["items"][0]
        self.assertIn(item["status"], {"pass", "warn"})
        self.assertIn("data_coverage_gap:news", item["degraded_sources"])
        self.assertEqual(item["news_coverage"]["status"], "warn")
        self.assertGreaterEqual(item["news_coverage"]["score"], 0.6)
        self.assertNotEqual(item["status"], "fail")

    def test_market_rules_cover_board_st_new_listing_and_unknown_status(self) -> None:
        self.assertEqual(board_rule("688981.SH")["board"], "star")
        self.assertEqual(board_rule("688981.SH")["lot"], 200)
        self.assertEqual(board_rule("300750.SZ")["limit_pct"], 0.20)
        st_rule = board_rule("600000.SH", stock_profile={"name": "ST测试", "is_st": True})
        self.assertEqual(st_rule["board"], "st")
        self.assertEqual(st_rule["limit_pct"], 0.05)
        new_rule = board_rule(
            "600000.SH",
            stock_profile={"listed_date": "20260427", "board": "main"},
            as_of=date(2026, 4, 30),
        )
        self.assertTrue(new_rule["new_listing_no_limit"])
        self.assertIsNone(new_rule["limit_pct"])
        self.assertEqual(board_rule("123456.SH")["rule_status"], "wip_unknown")

    def test_data_quality_uses_profile_financial_snapshot_and_board_payload_fallbacks(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session, symbols=("600519.SH",))
            stock = session.scalar(select(Stock).where(Stock.symbol == "600519.SH"))
            assert stock is not None
            session.execute(delete(FeatureSnapshot).where(FeatureSnapshot.stock_id == stock.id))
            stock.profile_payload = {
                **stock.profile_payload,
                "board": "main",
                "board_name": "主板",
                "financial_snapshot": {
                    "provider_name": "tushare_fina_indicator",
                    "ann_date": "20260425",
                    "report_period": "2026一季报",
                },
            }
            session.commit()

        with session_scope(self.database_url) as session:
            summary = build_data_quality_summary(session, symbols=["600519.SH"])

        item = summary["items"][0]
        self.assertEqual(item["financial_freshness"]["status"], "pass")
        self.assertEqual(item["financial_freshness"]["latest_as_of"], "2026-04-25T00:00:00+00:00")
        self.assertEqual(item["profile_completeness"]["status"], "pass")
        self.assertNotIn("financial_data_stale", item["degraded_sources"])
        self.assertNotIn("profile_incomplete", item["degraded_sources"])

    def test_factor_ic_and_weight_sweep_emit_insufficient_sample_not_fake_precision(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session, symbols=("600519.SH", "300750.SZ", "601318.SH", "002594.SZ"))
            study = build_factor_observations(session, artifact_root=self.temp_dir.name, persist=False)
            sweep = sweep_weights(session, artifact_root=self.temp_dir.name, persist=False)

        self.assertEqual(study["artifact_type"], "factor_ic_study")
        self.assertEqual(study["status"], "insufficient_sample")
        self.assertEqual(study["benchmark_context"]["primary_benchmark"], "CSI300")
        self.assertEqual(sweep["artifact_type"], "weight_sweep_study")
        self.assertEqual(sweep["status"], "insufficient_sample")
        self.assertIn("不自动修改生产权重", sweep["note"])

    def test_operations_summary_is_light_and_details_are_sectioned(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)

        with session_scope(self.database_url) as session:
            summary = build_operations_summary(session, sample_symbol="600519.SH")
            portfolios = build_operations_detail(session, section="portfolios", sample_symbol="600519.SH")
            factor_detail = build_operations_detail(session, section="factor_observation", sample_symbol="600519.SH")

        payload_kb = len(json.dumps(summary, ensure_ascii=False, default=str).encode("utf-8")) / 1024
        self.assertLessEqual(payload_kb, 250)
        self.assertEqual(summary["portfolios"], [])
        self.assertEqual(summary["recommendation_replay"], [])
        self.assertIn("today_at_a_glance", summary)
        self.assertIn("data_quality_summary", summary)
        self.assertGreaterEqual(len(portfolios["portfolios"]), 1)
        self.assertIn("factor_observation_summary", factor_detail)

    def test_stock_dashboard_schema_accepts_string_horizon_readout_and_new_fields(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session, symbols=("600519.SH",))

        with session_scope(self.database_url) as session:
            payload = get_stock_dashboard(session, "600519.SH")
        payload["research_horizon_readout"] = payload.get("research_horizon_readout") or "主周期尚未批准。"

        parsed = StockDashboardResponse.model_validate(payload)
        self.assertIsNotNone(parsed.research_horizon_readout)
        self.assertEqual(parsed.data_quality["symbol"], "600519.SH")
        self.assertIn("benchmark_context", parsed.factor_validation)


if __name__ == "__main__":
    unittest.main()
