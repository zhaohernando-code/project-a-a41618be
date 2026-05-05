from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
import tempfile
from types import SimpleNamespace
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import select

from ashare_evidence.api import create_app
from ashare_evidence.db import init_database, session_scope
from ashare_evidence.lineage import compute_lineage_hash
from ashare_evidence.models import MarketBar, ModelApiKey, ModelResult, Recommendation, ShortpickCandidate, ShortpickExperimentRun, Stock, WatchlistFollow
from ashare_evidence.shortpick_lab import (
    DeepseekLobeChatSearchShortpickExecutor,
    OpenAICompatibleShortpickExecutor,
    StaticShortpickExecutor,
    default_shortpick_executors,
    run_shortpick_experiment,
)


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

    def _seed_stock_bars(self, symbol: str, name: str, prices: list[float]) -> None:
        with session_scope(self.database_url) as session:
            ticker, _, market = symbol.partition(".")
            stock = Stock(
                symbol=symbol,
                ticker=ticker,
                exchange=market or "SH",
                name=name,
                provider_symbol=symbol,
                listed_date=date(2020, 7, 16),
                status="active",
                profile_payload={},
                license_tag="test",
                usage_scope="internal-test",
                redistribution_scope="none",
                source_uri=f"test://stock/{symbol}",
                lineage_hash=compute_lineage_hash({"symbol": symbol}),
            )
            session.add(stock)
            session.flush()
            start = datetime(2026, 5, 5, 7, 0, tzinfo=timezone.utc)
            for index, price in enumerate(prices):
                session.add(
                    MarketBar(
                        bar_key=f"bar-{symbol.lower().replace('.', '-')}-{index}",
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
                        source_uri=f"test://bar/{symbol}/{index}",
                        lineage_hash=compute_lineage_hash({"symbol": symbol, "index": index}),
                    )
                )

    def _seed_daily_bars(self) -> None:
        self._seed_stock_bars("688981.SH", "中芯国际", [100 + index * 2 for index in range(8)])
        self._seed_stock_bars("000300.SH", "沪深300", [200 + index for index in range(8)])
        self._seed_stock_bars("000852.SH", "中证1000", [300 + index * 1.5 for index in range(8)])

    def _fake_daily_fetch(self, symbol: str, prices: list[float]) -> SimpleNamespace:
        start = datetime(2026, 5, 5, 7, 0, tzinfo=timezone.utc)
        bars = []
        for index, price in enumerate(prices):
            bars.append(
                {
                    "bar_key": f"bar-{symbol.lower().replace('.', '-')}-shortpick-{index}",
                    "timeframe": "1d",
                    "observed_at": start + timedelta(days=index),
                    "open_price": price - 1,
                    "high_price": price + 1,
                    "low_price": price - 2,
                    "close_price": price,
                    "volume": 1000,
                    "amount": price * 1000,
                    "turnover_rate": None,
                    "adj_factor": None,
                    "total_mv": None,
                    "circ_mv": None,
                    "pe_ttm": None,
                    "pb": None,
                    "raw_payload": {"provider_name": "test"},
                    "source_uri": f"test://shortpick-bar/{symbol}/{index}",
                    "license_tag": "test",
                    "usage_scope": "internal-test",
                    "redistribution_scope": "none",
                    "lineage_hash": compute_lineage_hash({"symbol": symbol, "index": index}),
                }
            )
        return SimpleNamespace(provider_name="test_daily", bars=bars)

    def test_run_builds_consensus_and_validation_without_polluting_main_pools(self) -> None:
        self._seed_daily_bars()
        executors = [
            StaticShortpickExecutor("openai", "gpt-test", "fake", _answer("688981.SH", "中芯国际", "半导体国产替代", "https://a.example/news")),
            StaticShortpickExecutor("deepseek", "deepseek-test", "fake", _answer("688981.SH", "中芯国际", "半导体国产替代", "https://b.example/news")),
        ]

        with patch("ashare_evidence.shortpick_lab._sync_shortpick_benchmarks", return_value={"status": "skipped"}):
            with patch("ashare_evidence.shortpick_lab._sync_shortpick_candidate_market_data", return_value={"status": "skipped"}):
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

        with patch("ashare_evidence.shortpick_lab._sync_shortpick_benchmarks", return_value={"status": "skipped"}):
            with patch("ashare_evidence.shortpick_lab._sync_shortpick_candidate_market_data", return_value={"status": "skipped"}):
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

    def test_openai_compatible_shortpick_executor_is_blocked_for_shortpick_web_search(self) -> None:
        executor = OpenAICompatibleShortpickExecutor(
            key_id=1,
            provider_name="deepseek",
            model_name="deepseek-v4-pro",
            base_url="https://api.deepseek.com",
            api_key="secret",
        )

        with self.assertRaisesRegex(RuntimeError, "does not provide web search"):
            executor.complete("prompt")

    def test_deepseek_executor_uses_lobechat_searxng_search_results(self) -> None:
        calls: list[dict[str, object]] = []

        def fake_complete(self, **kwargs):
            calls.append(kwargs)
            prompt = str(kwargs["prompt"])
            if "只生成搜索计划" in prompt:
                return json.dumps(
                    {
                        "search_queries": ["A股 半导体 国产替代 短线 新闻"],
                        "search_intent": "寻找公开热点和催化。",
                    },
                    ensure_ascii=False,
                )
            return _answer("688981.SH", "中芯国际", "半导体国产替代", "https://news.cn/finance/test")

        class FakeSearchClient:
            def search(self, query: str):
                return [
                    {
                        "title": "半导体公开新闻",
                        "url": "https://news.cn/finance/test",
                        "published_at": "2026-05-05",
                        "why_it_matters": query,
                    }
                ]

        executor = DeepseekLobeChatSearchShortpickExecutor(
            key_id=1,
            provider_name="deepseek",
            model_name="deepseek-v4-pro",
            base_url="https://api.deepseek.com",
            api_key="secret",
            search_client=FakeSearchClient(),
        )
        with patch("ashare_evidence.shortpick_lab.OpenAICompatibleTransport.complete", new=fake_complete):
            with patch("ashare_evidence.shortpick_lab._source_credibility", return_value={"credibility_status": "verified", "credibility_reason": "test"}):
                raw = executor.complete("prompt")

        parsed = json.loads(raw)
        self.assertEqual(parsed["_executor_trace"]["search_backend"], "lobechat_searxng")
        self.assertEqual(parsed["_executor_trace"]["search_queries"], ["A股 半导体 国产替代 短线 新闻"])
        self.assertEqual(parsed["sources_used"][0]["url"], "https://news.cn/finance/test")
        self.assertEqual([item.get("enable_search") for item in calls], [None, None])
        self.assertEqual(executor.executor_kind, "deepseek_tool_search_lobechat_searxng_v1")

    def test_default_deepseek_executor_uses_lobechat_search_not_official_native_api(self) -> None:
        with session_scope(self.database_url) as session:
            session.add(
                ModelApiKey(
                    name="deepseek",
                    provider_name="deepseek",
                    model_name="deepseek-v4-pro",
                    base_url="https://api.deepseek.com",
                    api_key="secret",
                    enabled=True,
                    is_default=True,
                    priority=1,
                )
            )
            session.flush()
            executors = default_shortpick_executors(session)

        deepseek_executor = next(item for item in executors if item.provider_name == "deepseek")
        self.assertEqual(deepseek_executor.executor_kind, "deepseek_tool_search_lobechat_searxng_v1")

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
        with patch("ashare_evidence.shortpick_lab._sync_shortpick_benchmarks", return_value={"status": "skipped"}):
            with patch("ashare_evidence.shortpick_lab._sync_shortpick_candidate_market_data", return_value={"status": "skipped"}):
                with session_scope(self.database_url) as session:
                    run_shortpick_experiment(
                        session,
                        run_date=date(2026, 5, 5),
                        rounds_per_model=1,
                        triggered_by="root",
                        executors=[InspectingExecutor()],
                    )

        self.assertEqual(observed_counts, [1])

    def test_validation_uses_hs300_excess_return_and_updates_summary(self) -> None:
        self._seed_daily_bars()
        executors = [StaticShortpickExecutor("openai", "gpt-test", "fake", _answer("688981.SH", "中芯国际", "半导体国产替代", "https://a.example/news"))]

        with patch("ashare_evidence.shortpick_lab._sync_shortpick_benchmarks", return_value={"status": "skipped"}):
            with patch("ashare_evidence.shortpick_lab._sync_shortpick_candidate_market_data", return_value={"status": "skipped"}):
                with session_scope(self.database_url) as session:
                    payload = run_shortpick_experiment(
                        session,
                        run_date=date(2026, 5, 5),
                        rounds_per_model=1,
                        triggered_by="root",
                        executors=executors,
                    )

        first_validation = payload["candidates"][0]["validations"][0]
        self.assertEqual(first_validation["status"], "completed")
        self.assertEqual(first_validation["benchmark_symbol"], "000300.SH")
        self.assertEqual(first_validation["benchmark_label"], "沪深300")
        self.assertAlmostEqual(first_validation["stock_return"], 0.02)
        self.assertAlmostEqual(first_validation["benchmark_return"], 0.005)
        self.assertAlmostEqual(first_validation["excess_return"], 0.015)
        self.assertIn("000852.SH", first_validation["benchmark_returns"])
        self.assertGreater(payload["summary"]["completed_validation_count"], 0)
        self.assertEqual(payload["summary"]["measured_candidate_count"], 1)
        self.assertIn("1", payload["summary"]["validation_by_horizon"])

    def test_candidate_market_sync_creates_only_stock_and_market_bars(self) -> None:
        self._seed_stock_bars("000300.SH", "沪深300", [200 + index for index in range(8)])
        self._seed_stock_bars("000852.SH", "中证1000", [300 + index for index in range(8)])
        symbol = "001234.SZ"
        executors = [StaticShortpickExecutor("openai", "gpt-test", "fake", _answer(symbol, "测试股份", "短投题材", "https://a.example/news"))]
        profile = SimpleNamespace(name="测试股份", industry="测试行业", listed_date=date(2020, 1, 1), template_key=None, source="test")

        with patch("ashare_evidence.shortpick_lab._sync_shortpick_benchmarks", return_value={"status": "skipped"}):
            with patch("ashare_evidence.shortpick_lab.resolve_stock_profile", return_value=profile):
                with patch("ashare_evidence.shortpick_lab._fetch_shortpick_daily_market_data", return_value=self._fake_daily_fetch(symbol, [10 + index for index in range(8)])):
                    with session_scope(self.database_url) as session:
                        payload = run_shortpick_experiment(
                            session,
                            run_date=date(2026, 5, 5),
                            rounds_per_model=1,
                            triggered_by="root",
                            executors=executors,
                        )

        self.assertEqual(payload["candidates"][0]["validations"][0]["status"], "completed")
        with session_scope(self.database_url) as session:
            stock = session.scalar(select(Stock).where(Stock.symbol == symbol))
            self.assertIsNotNone(stock)
            assert stock is not None
            self.assertEqual(
                session.scalar(select(MarketBar).where(MarketBar.stock_id == stock.id).limit(1)).raw_payload["shortpick_lab_only"],
                True,
            )
            self.assertEqual(session.scalar(select(Recommendation).limit(1)), None)
            self.assertEqual(session.scalar(select(ModelResult).limit(1)), None)
            self.assertEqual(session.scalar(select(WatchlistFollow).where(WatchlistFollow.symbol == symbol)), None)

    def test_validation_pending_forward_window_records_entry(self) -> None:
        self._seed_stock_bars("688981.SH", "中芯国际", [100])
        self._seed_stock_bars("000300.SH", "沪深300", [200])
        self._seed_stock_bars("000852.SH", "中证1000", [300])
        executors = [StaticShortpickExecutor("openai", "gpt-test", "fake", _answer("688981.SH", "中芯国际", "半导体国产替代", "https://a.example/news"))]

        with patch("ashare_evidence.shortpick_lab._sync_shortpick_benchmarks", return_value={"status": "skipped"}):
            with patch("ashare_evidence.shortpick_lab._sync_shortpick_candidate_market_data", return_value={"status": "skipped"}):
                with session_scope(self.database_url) as session:
                    payload = run_shortpick_experiment(
                        session,
                        run_date=date(2026, 5, 5),
                        rounds_per_model=1,
                        triggered_by="root",
                        executors=executors,
                    )

        first_validation = payload["candidates"][0]["validations"][0]
        self.assertEqual(first_validation["status"], "pending_forward_window")
        self.assertEqual(first_validation["entry_close"], 100)

    def test_validation_pending_benchmark_when_primary_window_missing(self) -> None:
        self._seed_stock_bars("688981.SH", "中芯国际", [100 + index * 2 for index in range(8)])
        executors = [StaticShortpickExecutor("openai", "gpt-test", "fake", _answer("688981.SH", "中芯国际", "半导体国产替代", "https://a.example/news"))]

        with patch("ashare_evidence.shortpick_lab._sync_shortpick_benchmarks", return_value={"status": "skipped"}):
            with patch("ashare_evidence.shortpick_lab._sync_shortpick_candidate_market_data", return_value={"status": "skipped"}):
                with session_scope(self.database_url) as session:
                    payload = run_shortpick_experiment(
                        session,
                        run_date=date(2026, 5, 5),
                        rounds_per_model=1,
                        triggered_by="root",
                        executors=executors,
                    )

        statuses = {item["status"] for item in payload["candidates"][0]["validations"]}
        self.assertIn("pending_benchmark_data", statuses)

    def test_api_redacts_raw_output_for_member_and_blocks_mutation(self) -> None:
        executors = [StaticShortpickExecutor("openai", "gpt-test", "fake", _answer("688981.SH", "中芯国际", "半导体国产替代", "https://a.example/news"))]
        with patch("ashare_evidence.shortpick_lab._sync_shortpick_benchmarks", return_value={"status": "skipped"}):
            with patch("ashare_evidence.shortpick_lab._sync_shortpick_candidate_market_data", return_value={"status": "skipped"}):
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
