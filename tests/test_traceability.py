from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sqlalchemy import select

from ashare_evidence.db import init_database, session_scope
from ashare_evidence.lineage import compute_lineage_hash
from ashare_evidence.models import FeatureSnapshot, IngestionRun, ModelResult, Recommendation, Stock
from ashare_evidence.services import bootstrap_demo_data, get_latest_recommendation_summary, get_recommendation_trace


class EvidenceFoundationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "test.db"
        self.database_url = f"sqlite:///{database_path}"
        init_database(self.database_url)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_demo_seed_creates_traceable_recommendation(self) -> None:
        with session_scope(self.database_url) as session:
            summary = bootstrap_demo_data(session, "600519.SH")

        self.assertEqual(summary["symbol"], "600519.SH")
        self.assertGreaterEqual(summary["evidence_count"], 7)
        self.assertGreaterEqual(summary["simulation_order_count"], 2)

        with session_scope(self.database_url) as session:
            latest = get_latest_recommendation_summary(session, "600519.SH")
            self.assertIsNotNone(latest)
            self.assertEqual(latest["recommendation"]["direction"], "buy")
            self.assertEqual(latest["model"]["version"], "2026.04.14-r2")
            self.assertEqual(latest["prompt"]["version"], "v2")
            self.assertTrue(latest["recommendation"]["confidence_expression"])
            self.assertEqual(latest["recommendation"]["applicable_period"], "2-8 周，当前以 4 周信号最强")
            self.assertGreaterEqual(len(latest["recommendation"]["downgrade_conditions"]), 4)
            self.assertIn("price_baseline", latest["recommendation"]["factor_breakdown"])
            self.assertIn("validation_scheme", latest["recommendation"]["validation_snapshot"])
            self.assertLessEqual(
                latest["recommendation"]["factor_breakdown"]["llm_assessment"]["weight"],
                0.15,
            )

            recommendation_id = latest["recommendation"]["id"]
            trace = get_recommendation_trace(session, recommendation_id)

            evidence_types = {item["evidence_type"] for item in trace["evidence"]}
            self.assertEqual(
                evidence_types,
                {"market_bar", "news_item", "feature_snapshot", "model_result", "sector_membership"},
            )
            for evidence in trace["evidence"]:
                self.assertTrue(evidence["lineage"]["license_tag"])
                self.assertTrue(evidence["lineage"]["source_uri"])
                self.assertTrue(evidence["lineage"]["lineage_hash"])
            self.assertEqual(len(trace["simulation_orders"]), 2)
            first_fill_hash = trace["simulation_orders"][0]["fills"][0]["lineage"]["lineage_hash"]
            second_fill_hash = trace["simulation_orders"][1]["fills"][0]["lineage"]["lineage_hash"]
            self.assertNotEqual(first_fill_hash, second_fill_hash)
            feature_sets = {
                item["payload"]["feature_set_name"]
                for item in trace["evidence"]
                if item["evidence_type"] == "feature_snapshot"
            }
            self.assertIn("fusion_scorecard", feature_sets)
            self.assertIn("llm_assessment_factor", feature_sets)

    def test_mandatory_lineage_fields_exist_on_persisted_entities(self) -> None:
        with session_scope(self.database_url) as session:
            bootstrap_demo_data(session, "600519.SH")

        with session_scope(self.database_url) as session:
            stock = session.scalar(select(Stock).where(Stock.symbol == "600519.SH"))
            recommendation = session.scalar(select(Recommendation))
            ingestion_run = session.scalar(select(IngestionRun))

            self.assertIsNotNone(stock)
            self.assertIsNotNone(recommendation)
            self.assertIsNotNone(ingestion_run)

            for record in (stock, recommendation, ingestion_run):
                self.assertTrue(record.license_tag)
                self.assertTrue(record.usage_scope)
                self.assertTrue(record.redistribution_scope)
                self.assertTrue(record.source_uri)
                self.assertTrue(record.lineage_hash)

    def test_lineage_hash_changes_when_payload_changes(self) -> None:
        first = compute_lineage_hash({"a": 1, "b": 2})
        second = compute_lineage_hash({"a": 1, "b": 3})
        self.assertNotEqual(first, second)

    def test_signal_engine_persists_factor_snapshots_and_horizon_results(self) -> None:
        with session_scope(self.database_url) as session:
            bootstrap_demo_data(session, "600519.SH")

        with session_scope(self.database_url) as session:
            snapshots = session.scalars(
                select(FeatureSnapshot).order_by(FeatureSnapshot.feature_set_name.asc())
            ).all()
            snapshot_names = {snapshot.feature_set_name for snapshot in snapshots}
            self.assertEqual(
                snapshot_names,
                {
                    "fusion_scorecard",
                    "llm_assessment_factor",
                    "news_event_factor",
                    "price_baseline_factor",
                },
            )

            news_snapshot = next(snapshot for snapshot in snapshots if snapshot.feature_set_name == "news_event_factor")
            self.assertEqual(news_snapshot.feature_values["deduped_event_count"], 4)

            model_results = session.scalars(
                select(ModelResult).order_by(ModelResult.forecast_horizon_days.asc())
            ).all()
            self.assertEqual([result.forecast_horizon_days for result in model_results], [14, 28, 56])
            primary_result = next(result for result in model_results if result.forecast_horizon_days == 28)
            self.assertEqual(primary_result.result_payload["validation_snapshot"]["direction_hit_rate"], 0.59)
            self.assertIn("fusion", primary_result.result_payload["factor_scores"])


if __name__ == "__main__":
    unittest.main()
