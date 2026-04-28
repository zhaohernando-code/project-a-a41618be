from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import select

from ashare_evidence.cli import main
from ashare_evidence.db import init_database, session_scope
from ashare_evidence.models import Recommendation, Stock
from ashare_evidence.phase2.producer_contract_study import (
    build_phase5_producer_contract_study,
    build_phase5_producer_contract_study_artifact,
    phase5_producer_contract_study_artifact_id,
)
from ashare_evidence.research_artifact_store import (
    artifact_root_from_database_url,
    read_phase5_producer_contract_study_artifact,
)
from ashare_evidence.signal_engine_parts.base import confidence_expression, recommendation_direction_with_degrade_flags
from tests.fixtures import seed_watchlist_fixture

TEST_SYMBOLS = ["600519.SH", "300750.SZ", "601318.SH"]


def _set_latest_payload(
    session,
    symbol: str,
    *,
    fusion_score: float,
    evidence_gap_penalty: float,
    degrade_flags: list[str],
) -> None:
    recommendation = session.scalars(
        select(Recommendation)
        .join(Recommendation.stock)
        .where(Stock.symbol == symbol)
        .order_by(Recommendation.generated_at.desc(), Recommendation.id.desc())
    ).first()
    assert recommendation is not None
    payload = dict(recommendation.recommendation_payload or {})
    factor_breakdown = dict(payload.get("factor_breakdown") or {})
    fusion = dict(factor_breakdown.get("fusion") or {})
    fusion["score"] = fusion_score
    fusion["evidence_gap_penalty"] = evidence_gap_penalty
    fusion["active_degrade_flags"] = list(degrade_flags)
    factor_breakdown["fusion"] = fusion
    news_event = dict(factor_breakdown.get("news_event") or {})
    news_event["evidence_count"] = 0 if "missing_news_evidence" in degrade_flags else 2
    factor_breakdown["news_event"] = news_event
    payload["factor_breakdown"] = factor_breakdown
    evidence = dict(payload.get("evidence") or {})
    evidence["degrade_flags"] = list(degrade_flags)
    payload["evidence"] = evidence
    recommendation.recommendation_payload = payload
    session.flush()


class Phase5ProducerContractStudyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "phase5-producer-study.db"
        self.database_url = f"sqlite:///{database_path}"
        init_database(self.database_url)
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
            _set_latest_payload(
                session,
                "600519.SH",
                fusion_score=0.24,
                evidence_gap_penalty=0.12,
                degrade_flags=["missing_news_evidence"],
            )
            _set_latest_payload(
                session,
                "300750.SZ",
                fusion_score=0.21,
                evidence_gap_penalty=0.12,
                degrade_flags=["missing_news_evidence", "event_conflict_high"],
            )
            _set_latest_payload(
                session,
                "601318.SH",
                fusion_score=0.18,
                evidence_gap_penalty=0.0,
                degrade_flags=[],
            )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_build_phase5_producer_contract_study_compares_variants(self) -> None:
        with session_scope(self.database_url) as session:
            payload = build_phase5_producer_contract_study(session, symbols=TEST_SYMBOLS, include_history=False)

        self.assertEqual(payload["summary"]["included_record_count"], 3)
        variants = {item["variant_id"]: item for item in payload["variants"]}
        self.assertEqual(variants["current_hard_block"]["long_count"], 1)
        self.assertEqual(variants["remove_hard_override_keep_penalty"]["long_count"], 2)
        self.assertEqual(variants["watch_ceiling_keep_penalty"]["long_count"], 2)
        self.assertEqual(variants["watch_ceiling_keep_penalty"]["missing_news_only_buy_count"], 0)
        self.assertEqual(payload["decision"]["recommended_variant_id"], "watch_ceiling_keep_penalty")

    def test_missing_news_evidence_only_caps_positive_scores_to_watch(self) -> None:
        self.assertEqual(
            recommendation_direction_with_degrade_flags(0.24, ["missing_news_evidence"]),
            "watch",
        )
        self.assertEqual(
            recommendation_direction_with_degrade_flags(-0.24, ["missing_news_evidence"]),
            "reduce",
        )
        self.assertIn(
            "观察信号",
            confidence_expression("watch", 0.62, True, degrade_flags=["missing_news_evidence"]),
        )

    def test_phase5_producer_contract_study_artifact_id_is_stable(self) -> None:
        with session_scope(self.database_url) as session:
            payload = build_phase5_producer_contract_study(session, include_history=False)

        artifact = build_phase5_producer_contract_study_artifact(payload)
        self.assertEqual(artifact.artifact_id, phase5_producer_contract_study_artifact_id(payload))
        self.assertEqual(artifact.decision["recommended_variant_id"], "watch_ceiling_keep_penalty")

    def test_cli_phase5_producer_contract_study_can_write_artifact(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = main(
                [
                    "phase5-producer-contract-study",
                    "--database-url",
                    self.database_url,
                    "--latest-only",
                    "--symbol",
                    "600519.SH",
                    "--symbol",
                    "300750.SZ",
                    "--symbol",
                    "601318.SH",
                    "--write-artifact",
                ]
            )

        self.assertEqual(exit_code, 0)
        rendered = stdout.getvalue()
        self.assertIn('"recommended_variant_id": "watch_ceiling_keep_penalty"', rendered)
        self.assertIn('"artifact_id": "phase5-producer-contract-study:latest:', rendered)
        artifact_root = artifact_root_from_database_url(self.database_url)
        with session_scope(self.database_url) as session:
            payload = build_phase5_producer_contract_study(session, symbols=TEST_SYMBOLS, include_history=False)
        artifact = read_phase5_producer_contract_study_artifact(
            phase5_producer_contract_study_artifact_id(payload),
            root=artifact_root,
        )
        self.assertEqual(artifact.summary["included_record_count"], 3)
        self.assertEqual(artifact.decision["recommended_variant_id"], "watch_ceiling_keep_penalty")


if __name__ == "__main__":
    unittest.main()
