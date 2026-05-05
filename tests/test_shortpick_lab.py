from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import select

from ashare_evidence.api import create_app
from ashare_evidence.db import init_database, session_scope
from ashare_evidence.lineage import compute_lineage_hash
from ashare_evidence.models import MarketBar, Recommendation, ShortpickCandidate, ShortpickExperimentRun, Stock, WatchlistFollow
from ashare_evidence.shortpick_lab import OpenAICompatibleShortpickExecutor, StaticShortpickExecutor, run_shortpick_experiment


def _answer(symbol: str, name: str, theme: str, url: str) -> str:
    return json.dumps(
        {
            "as_of_date": "2026-05-05",
            "information_mode": "native_web_open_discovery",
            "primary_pick": {
                "symbol": symbol,
                "name": name,
                "theme": theme,
                "horizon_trading_days": 5,
                "confidence": 0.66,
                "thesis": f"{theme} 催化下的短线研究候选。",
                "catalysts": [theme],
                "invalidation": ["题材热度回落"],
                "risks": ["短线拥挤"],
            },
            "sources_used": [
                {
                    "title": "公开新闻",
                    "url": url,
                    "published_at": "2026-05-05",
                    "why_it_matters": theme,
                }
            ],
            "alternative_picks": [],
            "novelty_note": "来自公开网络的旁路发现。",
            "limitations": ["只代表研究优先级"],
        },
        ensure_ascii=False,
    )


class ShortpickLabTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "shortpick.db"
        self.database_url = f"sqlite:///{database_path}"
        init_database(self.database_url)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _seed_daily_bars(self) -> None:
        with session_scope(self.database_url) as session:
            stock = Stock(
                symbol="688981.SH",
                ticker="688981",
                exchange="SH",
                name="中芯国际",
                provider_symbol="688981",
                listed_date=date(2020, 7, 16),
                status="active",
                profile_payload={},
                license_tag="test",
                usage_scope="internal-test",
                redistribution_scope="none",
                source_uri="test://stock/688981",
                lineage_hash=compute_lineage_hash({"symbol": "688981.SH"}),
            )
            session.add(stock)
            session.flush()
            start = datetime(2026, 5, 5, 7, 0, tzinfo=timezone.utc)
            for index in range(8):
                price = 100 + index * 2
                session.add(
                    MarketBar(
                        bar_key=f"bar-688981-{index}",
                        stock_id=stock.id,
                        timeframe="1d",
                        observed_at=start + timedelta(days=index),
                        open_price=price - 1,
                        high_price=price + 1,
                        low_price=price - 2,
                        close_price=price,
                        volume=1000,
                        amount=price * 1000,
                        raw_payload={},
                        license_tag="test",
                        usage_scope="internal-test",
                        redistribution_scope="none",
                        source_uri=f"test://bar/688981/{index}",
                        lineage_hash=compute_lineage_hash({"symbol": "688981.SH", "index": index}),
                    )
                )

    def test_run_builds_consensus_and_validation_without_polluting_main_pools(self) -> None:
        self._seed_daily_bars()
        executors = [
            StaticShortpickExecutor("openai", "gpt-test", "fake", _answer("688981.SH", "中芯国际", "半导体国产替代", "https://a.example/news")),
            StaticShortpickExecutor("deepseek", "deepseek-test", "fake", _answer("688981.SH", "中芯国际", "半导体国产替代", "https://b.example/news")),
        ]

        with session_scope(self.database_url) as session:
            payload = run_shortpick_experiment(
                session,
                run_date=date(2026, 5, 5),
                rounds_per_model=1,
                triggered_by="root",
                executors=executors,
            )

        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["summary"]["completed_round_count"], 2)
        self.assertEqual(payload["consensus"]["research_priority"], "high_convergence")
        self.assertEqual(payload["consensus"]["summary"]["leader_symbols"], ["688981.SH"])
        self.assertEqual(len(payload["candidates"]), 2)
        self.assertTrue(all(item["research_priority"] == "high_convergence" for item in payload["candidates"]))
        self.assertTrue(any(v["status"] == "completed" for v in payload["candidates"][0]["validations"]))

        with session_scope(self.database_url) as session:
            self.assertEqual(session.scalar(select(WatchlistFollow).where(WatchlistFollow.symbol == "688981.SH")), None)
            self.assertEqual(session.scalar(select(Recommendation).limit(1)), None)

    def test_parse_failure_keeps_research_lab_artifact_and_candidate_boundary(self) -> None:
        executors = [StaticShortpickExecutor("openai", "gpt-test", "fake", "not-json")]

        with session_scope(self.database_url) as session:
            payload = run_shortpick_experiment(
                session,
                run_date=date(2026, 5, 5),
                rounds_per_model=1,
                triggered_by="root",
                executors=executors,
            )
            candidate = session.scalar(select(ShortpickCandidate))

        self.assertEqual(payload["status"], "failed")
        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual(candidate.parse_status, "parse_failed")
        self.assertEqual(candidate.symbol, "PARSE_FAILED")

    def test_sources_are_credibility_marked(self) -> None:
        executors = [
            StaticShortpickExecutor(
                "deepseek",
                "deepseek-test",
                "fake",
                _answer("688981.SH", "中芯国际", "半导体国产替代", "https://finance.eastmoney.com/a/2026050523456789.html"),
            )
        ]

        with session_scope(self.database_url) as session:
            payload = run_shortpick_experiment(
                session,
                run_date=date(2026, 5, 5),
                rounds_per_model=1,
                triggered_by="root",
                executors=executors,
            )

        source = payload["rounds"][0]["sources"][0]
        self.assertEqual(source["credibility_status"], "suspicious")
        self.assertIn("placeholder-like", source["credibility_reason"])

    def test_openai_compatible_shortpick_executor_enables_search(self) -> None:
        captured: dict[str, object] = {}

        def fake_complete(self, **kwargs):
            captured.update(kwargs)
            return _answer("688981.SH", "中芯国际", "半导体国产替代", "https://a.example/news")

        executor = OpenAICompatibleShortpickExecutor(
            key_id=1,
            provider_name="deepseek",
            model_name="deepseek-v4-pro",
            base_url="https://api.deepseek.com",
            api_key="secret",
        )
        with patch("ashare_evidence.shortpick_lab.OpenAICompatibleTransport.complete", new=fake_complete):
            executor.complete("prompt")

        self.assertEqual(captured["enable_search"], True)
        self.assertEqual(executor.executor_kind, "configured_api_key_native_web_search")

    def test_run_is_committed_before_long_executor_work(self) -> None:
        observed_counts: list[int] = []

        class InspectingExecutor:
            provider_name = "openai"
            model_name = "gpt-test"
            executor_kind = "fake"

            def complete(self, prompt: str) -> str:
                with session_scope(self_database_url) as other_session:
                    observed_counts.append(other_session.query(ShortpickExperimentRun).count())
                return _answer("688981.SH", "中芯国际", "半导体国产替代", "https://a.example/news")

        self_database_url = self.database_url
        with session_scope(self.database_url) as session:
            run_shortpick_experiment(
                session,
                run_date=date(2026, 5, 5),
                rounds_per_model=1,
                triggered_by="root",
                executors=[InspectingExecutor()],
            )

        self.assertEqual(observed_counts, [1])

    def test_api_redacts_raw_output_for_member_and_blocks_mutation(self) -> None:
        executors = [StaticShortpickExecutor("openai", "gpt-test", "fake", _answer("688981.SH", "中芯国际", "半导体国产替代", "https://a.example/news"))]
        with session_scope(self.database_url) as session:
            run_shortpick_experiment(
                session,
                run_date=date(2026, 5, 5),
                rounds_per_model=1,
                triggered_by="root",
                executors=executors,
            )

        client = TestClient(create_app(self.database_url, enable_background_ops_tick=False))
        member_headers = {"X-HZ-User-Login": "member-a", "X-HZ-User-Role": "member"}
        list_response = client.get("/shortpick-lab/runs", headers=member_headers)
        self.assertEqual(list_response.status_code, 200)
        first_round = list_response.json()["items"][0]["rounds"][0]
        self.assertIsNone(first_round["raw_answer"])

        create_response = client.post(
            "/shortpick-lab/runs",
            headers=member_headers,
            json={"rounds_per_model": 1},
        )
        self.assertEqual(create_response.status_code, 403)
        self.assertIn("root role required", create_response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
