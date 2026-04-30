from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sqlalchemy import select

from ashare_evidence.db import init_database, session_scope
from ashare_evidence.phase2 import (
    PHASE2_LABEL_DEFINITION,
    PHASE2_WINDOW_DEFINITION,
    phase2_target_horizon_label,
)
from ashare_evidence.lineage import compute_lineage_hash
from ashare_evidence.models import FeatureSnapshot, IngestionRun, ModelResult, Recommendation, Stock
from ashare_evidence.services import get_latest_recommendation_summary, get_recommendation_trace
from tests.fixtures import inject_market_data_stale_backfill, seed_recommendation_fixture


class EvidenceFoundationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "test.db"
        self.database_url = f"sqlite:///{database_path}"
        init_database(self.database_url)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _latest_recommendation_record(self, session):
        recommendation = session.scalar(
            select(Recommendation)
            .where(Recommendation.recommendation_key.is_not(None))
            .order_by(Recommendation.generated_at.desc())
        )
        assert recommendation is not None
        return recommendation

    def test_seeded_fixture_creates_traceable_recommendation(self) -> None:
        with session_scope(self.database_url) as session:
            seed_recommendation_fixture(session, "600519.SH")

        with session_scope(self.database_url) as session:
            latest = get_latest_recommendation_summary(session, "600519.SH")
            self.assertIsNotNone(latest)
            assert latest is not None
            self.assertEqual(latest["stock"]["symbol"], "600519.SH")
            self.assertTrue(latest["recommendation"]["confidence_expression"])
            self.assertGreaterEqual(len(latest["recommendation"]["downgrade_conditions"]), 4)
            self.assertEqual(latest["recommendation"]["validation_status"], "pending_rebuild")
            self.assertEqual(latest["recommendation"]["core_quant"]["score_scale"], "phase2_rule_baseline_score")
            self.assertEqual(
                latest["recommendation"]["core_quant"]["target_horizon_label"],
                phase2_target_horizon_label(),
            )
            self.assertEqual(latest["recommendation"]["historical_validation"]["status"], "pending_rebuild")
            self.assertEqual(latest["recommendation"]["historical_validation"]["artifact_type"], "validation_metrics")
            self.assertTrue(latest["recommendation"]["historical_validation"]["manifest_id"])
            self.assertEqual(
                latest["recommendation"]["historical_validation"]["window_definition"],
                PHASE2_WINDOW_DEFINITION,
            )
            self.assertEqual(
                latest["recommendation"]["historical_validation"]["label_definition"],
                PHASE2_LABEL_DEFINITION,
            )
            self.assertEqual(latest["recommendation"]["historical_validation"]["metrics"]["sample_count"], 3)
            self.assertIn("rank_ic_mean", latest["recommendation"]["historical_validation"]["metrics"])
            self.assertEqual(latest["recommendation"]["manual_llm_review"]["trigger_mode"], "manual")
            self.assertEqual(latest["recommendation"]["manual_llm_review"]["risks"], [])
            self.assertTrue(latest["recommendation"]["evidence"]["primary_drivers"])
            self.assertGreaterEqual(len(latest["recommendation"]["evidence"]["factor_cards"]), 4)
            self.assertEqual(
                latest["recommendation"]["evidence"]["factor_cards"][0]["factor_key"],
                "price_baseline",
            )
            self.assertIsInstance(latest["recommendation"]["evidence"]["degrade_flags"], list)
            self.assertTrue(latest["recommendation"]["risk"]["coverage_gaps"])
            self.assertGreaterEqual(len(latest["recommendation"]["risk"]["invalidators"]), 1)

            trace = get_recommendation_trace(session, latest["recommendation"]["id"])
            self.assertGreaterEqual(len(trace["evidence"]), 7)
            evidence_types = {item["evidence_type"] for item in trace["evidence"]}
            self.assertEqual(
                evidence_types,
                {"market_bar", "news_item", "feature_snapshot", "model_result", "sector_membership"},
            )
            self.assertEqual(len(trace["simulation_orders"]), 2)
            for evidence in trace["evidence"]:
                self.assertTrue(evidence["lineage"]["license_tag"])
                self.assertTrue(evidence["lineage"]["source_uri"])
                self.assertTrue(evidence["lineage"]["lineage_hash"])

    def test_mandatory_lineage_fields_exist_on_persisted_entities(self) -> None:
        with session_scope(self.database_url) as session:
            seed_recommendation_fixture(session, "600519.SH")

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
            seed_recommendation_fixture(session, "600519.SH")

        with session_scope(self.database_url) as session:
            snapshots = session.scalars(select(FeatureSnapshot).order_by(FeatureSnapshot.feature_set_name.asc())).all()
            snapshot_names = {snapshot.feature_set_name for snapshot in snapshots}
            self.assertEqual(
                snapshot_names,
                {
                    "fusion_scorecard",
                    "manual_review_placeholder_layer",
                    "news_event_factor",
                    "price_baseline_factor",
                },
            )

            news_snapshot = next(snapshot for snapshot in snapshots if snapshot.feature_set_name == "news_event_factor")
            self.assertGreaterEqual(news_snapshot.feature_values["deduped_event_count"], 3)

            model_results = session.scalars(select(ModelResult).order_by(ModelResult.forecast_horizon_days.asc())).all()
            self.assertEqual(sorted({result.forecast_horizon_days for result in model_results}), [10, 20, 40])
            primary_result = next(result for result in reversed(model_results) if result.forecast_horizon_days == 20)
            self.assertEqual(primary_result.result_payload["validation_snapshot"]["status"], "pending_rebuild")
            self.assertIn("fusion", primary_result.result_payload["factor_scores"])
            recommendation = self._latest_recommendation_record(session)
            payload = dict(recommendation.recommendation_payload or {})
            self.assertNotIn("applicable_period", payload)
            self.assertNotIn("reverse_risks", payload)
            self.assertNotIn("validation_snapshot", payload)
            self.assertGreaterEqual(len(payload["evidence"]["factor_cards"]), 4)
            self.assertIsInstance(payload["evidence"]["degrade_flags"], list)
            self.assertTrue(payload["historical_validation"]["manifest_id"])
            self.assertEqual(payload["historical_validation"]["label_definition"], PHASE2_LABEL_DEFINITION)
            self.assertEqual(payload["core_quant"]["target_horizon_label"], phase2_target_horizon_label())
            self.assertEqual(payload["manual_llm_review"]["risks"], [])

    def test_legacy_projection_survives_missing_raw_compat_fields(self) -> None:
        with session_scope(self.database_url) as session:
            seed_recommendation_fixture(session, "600519.SH")
            recommendation = self._latest_recommendation_record(session)
            payload = dict(recommendation.recommendation_payload or {})
            payload.pop("factor_breakdown", None)
            payload.pop("applicable_period", None)
            payload.pop("reverse_risks", None)
            payload.pop("validation_snapshot", None)
            recommendation.recommendation_payload = payload
            session.flush()

        with session_scope(self.database_url) as session:
            latest = get_latest_recommendation_summary(session, "600519.SH")
            assert latest is not None
            self.assertEqual(latest["recommendation"]["applicable_period"], PHASE2_WINDOW_DEFINITION)
            self.assertIn("price_baseline", latest["recommendation"]["factor_breakdown"])
            self.assertEqual(latest["recommendation"]["factor_breakdown"]["llm_assessment"]["weight"], 0.0)
            self.assertIsNotNone(latest["recommendation"]["core_quant"]["score"])
            self.assertGreaterEqual(len(latest["recommendation"]["evidence"]["factor_cards"]), 4)
            self.assertEqual(
                latest["recommendation"]["evidence"]["factor_cards"][0]["factor_key"],
                "price_baseline",
            )
            self.assertEqual(
                latest["recommendation"]["validation_snapshot"]["artifact_id"],
                latest["recommendation"]["historical_validation"]["artifact_id"],
            )

    def test_verified_historical_validation_requires_manifest_binding(self) -> None:
        with session_scope(self.database_url) as session:
            seed_recommendation_fixture(session, "600519.SH")
            recommendation = self._latest_recommendation_record(session)
            payload = dict(recommendation.recommendation_payload or {})
            payload["validation_status"] = "verified"
            payload["validation_note"] = None
            payload["historical_validation"] = {
                "status": "verified",
                "artifact_type": "rolling_validation",
                "artifact_id": "rolling-validation:fixture",
                "manifest_id": None,
                "benchmark_definition": "CSI300_total_return",
                "cost_definition": "12 bps",
                "metrics": {"rank_ic_mean": 0.041},
            }
            recommendation.recommendation_payload = payload
            session.flush()

        with session_scope(self.database_url) as session:
            latest = get_latest_recommendation_summary(session, "600519.SH")
            assert latest is not None
            historical_validation = latest["recommendation"]["historical_validation"]
            self.assertEqual(historical_validation["status"], "pending_rebuild")
            self.assertTrue(historical_validation["note"])
            self.assertEqual(latest["recommendation"]["validation_status"], "pending_rebuild")

    def test_historical_validation_no_longer_backfills_from_legacy_validation_snapshot(self) -> None:
        with session_scope(self.database_url) as session:
            seed_recommendation_fixture(session, "600519.SH")
            recommendation = self._latest_recommendation_record(session)
            payload = dict(recommendation.recommendation_payload or {})
            payload.pop("historical_validation", None)
            payload["validation_snapshot"] = {
                "status": "verified",
                "validation_scheme": "LEGACY_VALIDATION_SCHEME_SHOULD_NOT_DRIVE",
                "transaction_cost_bps": 12,
            }
            recommendation.recommendation_payload = payload
            session.flush()

        with session_scope(self.database_url) as session:
            latest = get_latest_recommendation_summary(session, "600519.SH")
            assert latest is not None
            historical_validation = latest["recommendation"]["historical_validation"]
            self.assertNotEqual(historical_validation["label_definition"], "LEGACY_VALIDATION_SCHEME_SHOULD_NOT_DRIVE")
            self.assertTrue(historical_validation["manifest_id"])
            self.assertTrue(historical_validation["artifact_id"])
            self.assertNotEqual(historical_validation["cost_definition"], "12 bps")
            self.assertEqual(historical_validation["status"], "pending_rebuild")

    def test_manual_llm_review_no_longer_backfills_from_factor_breakdown(self) -> None:
        with session_scope(self.database_url) as session:
            seed_recommendation_fixture(session, "600519.SH")
            recommendation = self._latest_recommendation_record(session)
            payload = dict(recommendation.recommendation_payload or {})
            payload.pop("manual_llm_review", None)
            factor_breakdown = dict(payload.get("factor_breakdown") or {})
            llm_assessment = dict(factor_breakdown.get("llm_assessment") or {})
            llm_assessment["risks"] = ["LEGACY_LLM_RISK_SHOULD_NOT_DRIVE"]
            llm_assessment["contradictions"] = ["LEGACY_LLM_CONTRADICTION_SHOULD_NOT_DRIVE"]
            factor_breakdown["llm_assessment"] = llm_assessment
            payload["factor_breakdown"] = factor_breakdown
            recommendation.recommendation_payload = payload
            session.flush()

        with session_scope(self.database_url) as session:
            latest = get_latest_recommendation_summary(session, "600519.SH")
            assert latest is not None
            manual_review = latest["recommendation"]["manual_llm_review"]
            self.assertEqual(manual_review["status"], "manual_trigger_required")
            self.assertEqual(manual_review["risks"], [])
            self.assertNotIn("LEGACY_LLM_RISK_SHOULD_NOT_DRIVE", manual_review["risks"])
            self.assertEqual(manual_review["disagreements"], [])

    def test_latest_summary_prefers_non_stale_same_as_of_version(self) -> None:
        with session_scope(self.database_url) as session:
            seed_recommendation_fixture(session, "600519.SH")
            fresh, stale = inject_market_data_stale_backfill(session, "600519.SH")

        with session_scope(self.database_url) as session:
            latest = get_latest_recommendation_summary(session, "600519.SH")

        assert latest is not None
        self.assertEqual(latest["recommendation"]["id"], fresh.id)
        self.assertNotEqual(latest["recommendation"]["id"], stale.id)
        self.assertNotIn("market_data_stale", latest["recommendation"]["evidence"]["degrade_flags"])


if __name__ == "__main__":
    unittest.main()
