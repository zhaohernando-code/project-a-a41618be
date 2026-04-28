from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime, time, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from sqlalchemy import select

from ashare_evidence.analysis_pipeline import (
    DailyMarketFetch,
    build_real_evidence_bundle,
    refresh_real_analysis,
    _fetch_research_metadata,
)
from ashare_evidence.db import init_database, session_scope
from ashare_evidence.lineage import build_lineage
from ashare_evidence.models import PaperFill, PaperOrder, PaperPortfolio, Recommendation, WatchlistEntry
from ashare_evidence.phase2 import rebuild_phase2_research_state
from ashare_evidence.phase2.common import build_expanding_equal_weight_proxy
from ashare_evidence.phase2.phase5_contract import (
    PHASE5_MARKET_HISTORY_LOOKBACK_DAYS,
    PHASE5_PRIMARY_RESEARCH_BENCHMARK_MEMBERSHIP_RULE,
    PHASE5_REQUIRED_OBSERVATION_COUNT,
)
from ashare_evidence.research_artifact_store import (
    artifact_root_from_database_url,
    read_backtest_artifact,
    read_manifest,
    read_replay_alignment_artifact,
    read_validation_metrics,
)
from ashare_evidence.services import get_latest_recommendation_summary
from ashare_evidence.stock_master import StockProfileResolution
from tests.fixtures import inject_market_data_stale_backfill

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def _lineaged_market_bar(symbol: str, trade_day: date, close_price: float, turnover_rate: float) -> dict[str, object]:
    ticker = symbol.partition(".")[0].lower()
    record = {
        "bar_key": f"bar-{ticker}-1d-{trade_day:%Y%m%d}",
        "timeframe": "1d",
        "observed_at": datetime.combine(trade_day, time(15, 0), tzinfo=SHANGHAI_TZ),
        "open_price": round(close_price * 0.994, 2),
        "high_price": round(close_price * 1.008, 2),
        "low_price": round(close_price * 0.989, 2),
        "close_price": round(close_price, 2),
        "volume": 1_000_000 + close_price * 500,
        "amount": close_price * 1_000_000,
        "turnover_rate": turnover_rate,
        "adj_factor": None,
        "raw_payload": {
            "provider_name": "test",
            "trade_day": trade_day.isoformat(),
        },
    }
    return {
        **record,
        **build_lineage(
            record,
            source_uri=f"test://daily/{symbol}/{trade_day:%Y%m%d}",
            license_tag="test-fixture",
            usage_scope="internal_research",
            redistribution_scope="none",
        ),
    }


def _lineaged_news_item(symbol: str, key: str, headline: str, published_at: datetime) -> dict[str, object]:
    record = {
        "news_key": key,
        "provider_name": "cninfo",
        "external_id": key,
        "headline": headline,
        "summary": headline,
        "content_excerpt": None,
        "published_at": published_at,
        "event_scope": "announcement",
        "dedupe_key": key,
        "raw_payload": {"provider_name": "cninfo"},
    }
    return {
        **record,
        **build_lineage(
            record,
            source_uri=f"test://news/{key}",
            license_tag="test-fixture",
            usage_scope="internal_research",
            redistribution_scope="none",
        ),
    }


def _lineaged_news_link(
    key: str,
    *,
    symbol: str,
    sector_code: str,
    impact_direction: str,
    published_at: datetime,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for entity_type, stock_symbol, attached_sector_code, score in (
        ("stock", symbol, None, 0.92),
        ("sector", None, sector_code, 0.45),
    ):
        record = {
            "news_key": key,
            "entity_type": entity_type,
            "stock_symbol": stock_symbol,
            "sector_code": attached_sector_code,
            "market_tag": "A-share",
            "relevance_score": score,
            "impact_direction": impact_direction,
            "effective_at": published_at,
            "decay_half_life_hours": 96.0,
            "mapping_payload": {"from": "fixture"},
        }
        records.append(
            {
                **record,
                **build_lineage(
                    record,
                    source_uri=f"test://news-link/{key}/{entity_type}",
                    license_tag="test-fixture",
                    usage_scope="internal_research",
                    redistribution_scope="none",
                ),
            }
        )
    return records


class AnalysisPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "analysis-pipeline.db"
        self.database_url = f"sqlite:///{database_path}"
        init_database(self.database_url)
        self.symbol = "300750.SZ"
        self.profile = StockProfileResolution(
            symbol=self.symbol,
            name="宁德时代",
            industry="电力设备",
            listed_date=date(2018, 6, 11),
            template_key="power_equipment",
            source="test_profile",
        )
        trade_day = date(2026, 4, 24)
        self.market_bars = [
            _lineaged_market_bar(
                self.symbol,
                trade_day - timedelta(days=839 - index),
                close_price=180.0 + index * 1.35,
                turnover_rate=0.012 + index * 0.00008,
            )
            for index in range(840)
        ]
        positive_time = datetime(2026, 4, 22, 23, 59, tzinfo=SHANGHAI_TZ)
        negative_time = datetime(2026, 4, 19, 23, 59, tzinfo=SHANGHAI_TZ)
        self.news_items = [
            _lineaged_news_item(self.symbol, "cninfo-pos", "宁德时代回购方案进展公告", positive_time),
            _lineaged_news_item(self.symbol, "cninfo-neg", "宁德时代风险提示公告", negative_time),
        ]
        self.news_links = [
            *_lineaged_news_link("cninfo-pos", symbol=self.symbol, sector_code="industry:power_equipment", impact_direction="positive", published_at=positive_time),
            *_lineaged_news_link("cninfo-neg", symbol=self.symbol, sector_code="industry:power_equipment", impact_direction="negative", published_at=negative_time),
        ]

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _refresh_symbol(
        self,
        session,
        *,
        symbol: str,
        profile: StockProfileResolution,
        market_bars: list[dict[str, object]],
        news_items: list[dict[str, object]] | None = None,
        news_links: list[dict[str, object]] | None = None,
    ):
        with patch("ashare_evidence.analysis_pipeline.resolve_stock_profile", return_value=profile):
            with patch(
                "ashare_evidence.analysis_pipeline._fetch_daily_market_data",
                return_value=DailyMarketFetch(provider_name="akshare_sina_daily", bars=market_bars),
            ):
                with patch(
                    "ashare_evidence.analysis_pipeline._fetch_official_announcements",
                    return_value=(news_items or [], news_links or []),
                ):
                    with patch(
                        "ashare_evidence.analysis_pipeline._fetch_financial_snapshot",
                        return_value={"provider_name": "akshare_em_financials", "report_period": "2025年报"},
                    ):
                        with patch(
                            "ashare_evidence.analysis_pipeline._fetch_research_metadata",
                            return_value=[],
                        ):
                            return refresh_real_analysis(session, symbol=symbol)

    def _refresh_with_market_bars(self, session, market_bars: list[dict[str, object]]):
        return self._refresh_symbol(
            session,
            symbol=self.symbol,
            profile=self.profile,
            market_bars=market_bars,
            news_items=self.news_items,
            news_links=self.news_links,
        )

    def _recommendation_trade_days(self, session) -> list[date]:
        return [
            recommendation.as_of_data_time.astimezone(SHANGHAI_TZ).date()
            for recommendation in session.scalars(
                select(Recommendation)
                .join(Recommendation.stock)
                .where(Recommendation.stock.has(symbol=self.symbol))
                .order_by(Recommendation.as_of_data_time.asc())
            ).all()
        ]

    def _seed_portfolio_track(
        self,
        session,
        *,
        recommendation_id: int,
        stock_id: int,
        requested_at: datetime,
        fill_price: float,
    ) -> str:
        portfolio_payload = {"starting_cash": 200_000.0}
        portfolio = PaperPortfolio(
            portfolio_key="phase2-test-manual",
            name="Phase 2 手工测试组合",
            mode="manual",
            benchmark_symbol="000300.SH",
            base_currency="CNY",
            cash_balance=200_000.0,
            status="active",
            portfolio_payload=portfolio_payload,
            **build_lineage(
                portfolio_payload,
                source_uri="test://phase2/portfolio/manual",
                license_tag="test-fixture",
                usage_scope="internal_research",
                redistribution_scope="none",
            ),
        )
        session.add(portfolio)
        session.flush()

        order_payload = {"strategy": "phase2-test-buy"}
        order = PaperOrder(
            order_key="phase2-test-order-buy",
            portfolio_id=portfolio.id,
            stock_id=stock_id,
            recommendation_id=recommendation_id,
            order_source="manual_follow_up",
            side="buy",
            requested_at=requested_at,
            quantity=100,
            order_type="limit",
            limit_price=fill_price,
            status="filled",
            notes="Phase 2 producer coverage fixture",
            order_payload=order_payload,
            **build_lineage(
                order_payload,
                source_uri="test://phase2/order/manual-buy",
                license_tag="test-fixture",
                usage_scope="internal_research",
                redistribution_scope="none",
            ),
        )
        session.add(order)
        session.flush()

        fill_payload = {"execution": "phase2-test-fill"}
        fill = PaperFill(
            fill_key="phase2-test-fill-buy",
            order_id=order.id,
            stock_id=stock_id,
            filled_at=requested_at,
            price=fill_price,
            quantity=100,
            fee=5.0,
            tax=0.0,
            slippage_bps=8.0,
            fill_payload=fill_payload,
            **build_lineage(
                fill_payload,
                source_uri="test://phase2/fill/manual-buy",
                license_tag="test-fixture",
                usage_scope="internal_research",
                redistribution_scope="none",
            ),
        )
        session.add(fill)
        return portfolio.portfolio_key

    def test_build_real_bundle_contains_real_source_payloads(self) -> None:
        with session_scope(self.database_url) as session:
            with patch("ashare_evidence.analysis_pipeline.resolve_stock_profile", return_value=self.profile):
                with patch(
                    "ashare_evidence.analysis_pipeline._fetch_daily_market_data",
                    return_value=DailyMarketFetch(provider_name="akshare_sina_daily", bars=self.market_bars),
                ):
                    with patch(
                        "ashare_evidence.analysis_pipeline._fetch_official_announcements",
                        return_value=(self.news_items, self.news_links),
                    ):
                        with patch(
                            "ashare_evidence.analysis_pipeline._fetch_financial_snapshot",
                            return_value={"provider_name": "akshare_em_financials", "report_period": "2025年报", "parent_netprofit": 12_345_678.0},
                        ):
                            with patch(
                                "ashare_evidence.analysis_pipeline._fetch_research_metadata",
                                return_value=[{"title": "年报点评", "rating": "买入", "broker": "测试券商", "published_at": "2026-04-24", "pdf_url": "https://example.com/r.pdf", "industry": "电力设备"}],
                            ):
                                bundle = build_real_evidence_bundle(session, symbol=self.symbol)

        self.assertEqual(bundle.provider_name, "real_data_pipeline")
        self.assertEqual(bundle.stock["name"], "宁德时代")
        self.assertEqual(bundle.stock["profile_payload"]["industry"], "电力设备")
        self.assertEqual(bundle.stock["profile_payload"]["analysis_pipeline"]["daily_market_provider"], "akshare_sina_daily")
        self.assertEqual(bundle.stock["profile_payload"]["financial_snapshot"]["provider_name"], "akshare_em_financials")
        self.assertEqual(len(bundle.market_bars), len(self.market_bars))
        self.assertEqual(bundle.market_bars[-1]["timeframe"], "1d")
        self.assertGreaterEqual(len(bundle.news_items), 2)
        self.assertGreaterEqual(len(bundle.feature_snapshots), 4)

    def test_fetch_research_metadata_injects_default_requests_timeout(self) -> None:
        observed: dict[str, object] = {}

        class _EmptyFrame:
            empty = True

        class _FakeAkshare:
            def stock_research_report_em(self, symbol: str):
                import requests

                observed["symbol"] = symbol
                try:
                    requests.Session().request("GET", "https://example.com/research")
                except RuntimeError:
                    return _EmptyFrame()
                raise AssertionError("expected patched Session.request to be called")

        def _fake_request(self, method, url, **kwargs):
            observed["method"] = method
            observed["url"] = url
            observed["timeout"] = kwargs.get("timeout")
            raise RuntimeError("stop after timeout capture")

        with patch("ashare_evidence.analysis_pipeline._akshare_module", return_value=_FakeAkshare()):
            with patch("requests.sessions.Session.request", new=_fake_request):
                metadata = _fetch_research_metadata(self.symbol)

        self.assertEqual(metadata, [])
        self.assertEqual(observed["symbol"], self.symbol.partition(".")[0])
        self.assertEqual(observed["timeout"], 5)

    def test_refresh_real_analysis_ingests_latest_recommendation(self) -> None:
        with session_scope(self.database_url) as session:
            recommendation = self._refresh_with_market_bars(session, self.market_bars)
            session.commit()
            summary = get_latest_recommendation_summary(session, self.symbol)

        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertEqual(summary["stock"]["symbol"], self.symbol)
        self.assertEqual(summary["recommendation"]["id"], recommendation.id)
        self.assertIn(summary["recommendation"]["direction"], {"buy", "watch", "reduce", "risk_alert"})

    def test_refresh_real_analysis_passes_active_watchlist_scope_to_rebuild(self) -> None:
        captured: dict[str, object] = {}

        def _capture_rebuild(session, *, symbols=None, active_symbols=None):
            captured["symbols"] = symbols
            captured["active_symbols"] = active_symbols
            return {"recommendations": 0, "validation_artifacts": 0, "replay_artifacts": 0, "backtests": 0}

        with session_scope(self.database_url) as session:
            with patch(
                "ashare_evidence.watchlist.active_watchlist_symbols",
                return_value=[self.symbol, "000001.SZ"],
            ):
                with patch(
                    "ashare_evidence.analysis_pipeline.rebuild_phase2_research_state",
                    side_effect=_capture_rebuild,
                ):
                    self._refresh_with_market_bars(session, self.market_bars)

        self.assertEqual(captured["symbols"], {self.symbol})
        self.assertEqual(captured["active_symbols"], {self.symbol, "000001.SZ"})

    def test_refresh_real_analysis_backfills_missing_recommendation_days_after_established_history(self) -> None:
        seed_windows = (780, 783, 786)
        latest_window = 789
        expected_trade_days = [
            self.market_bars[index]["observed_at"].astimezone(SHANGHAI_TZ).date()
            for index in range(seed_windows[0] - 1, latest_window)
        ]

        with session_scope(self.database_url) as session:
            with patch(
                "ashare_evidence.analysis_pipeline.rebuild_phase2_research_state",
                return_value={"recommendations": 0, "validation_artifacts": 0, "replay_artifacts": 0, "backtests": 0},
            ):
                for window in seed_windows:
                    self._refresh_with_market_bars(session, self.market_bars[:window])
                recommendation = self._refresh_with_market_bars(session, self.market_bars[:latest_window])
                first_pass_trade_days = self._recommendation_trade_days(session)
                self._refresh_with_market_bars(session, self.market_bars[:latest_window])
                second_pass_trade_days = self._recommendation_trade_days(session)

        self.assertEqual(recommendation.as_of_data_time.astimezone(SHANGHAI_TZ).date(), expected_trade_days[-1])
        self.assertEqual(first_pass_trade_days, expected_trade_days)
        self.assertEqual(second_pass_trade_days, expected_trade_days)

    def test_phase2_single_symbol_rebuild_uses_active_scope_market_proxy(self) -> None:
        alt_symbol = "000001.SZ"
        alt_profile = StockProfileResolution(
            symbol=alt_symbol,
            name="平安银行",
            industry="银行",
            listed_date=date(1991, 4, 3),
            template_key="bank",
            source="test_profile",
        )
        trade_day = date(2026, 4, 24)
        alt_market_bars = [
            _lineaged_market_bar(
                alt_symbol,
                trade_day - timedelta(days=839 - index),
                close_price=12.0 + index * 0.08 + ((index % 9) - 4) * 0.03,
                turnover_rate=0.018 + index * 0.00003,
            )
            for index in range(840)
        ]

        with session_scope(self.database_url) as session:
            self._refresh_with_market_bars(session, self.market_bars)
            self._refresh_symbol(
                session,
                symbol=alt_symbol,
                profile=alt_profile,
                market_bars=alt_market_bars,
            )
            rebuild_phase2_research_state(
                session,
                symbols={self.symbol},
                active_symbols={self.symbol, alt_symbol},
            )
            session.commit()
            summary = get_latest_recommendation_summary(session, self.symbol)

        self.assertIsNotNone(summary)
        assert summary is not None
        latest_validation = summary["recommendation"]["historical_validation"]
        self.assertEqual(latest_validation["benchmark_definition"], "active_watchlist_equal_weight_proxy")
        candidates = latest_validation["metrics"]["candidate_horizon_comparison"]["candidates"]
        self.assertGreater(len({item["net_excess_return"] for item in candidates}), 1)

    def test_expanding_proxy_does_not_backfill_late_joiner(self) -> None:
        day_one = date(2026, 4, 1)
        day_two = day_one + timedelta(days=1)
        day_three = day_two + timedelta(days=1)

        benchmark, summary = build_expanding_equal_weight_proxy(
            {
                self.symbol: {
                    day_one: 100.0,
                    day_two: 110.0,
                    day_three: 121.0,
                },
                "000001.SZ": {
                    day_one: 100.0,
                    day_two: 200.0,
                    day_three: 200.0,
                },
            },
            {
                self.symbol: day_one,
                "000001.SZ": day_three,
            },
        )

        self.assertEqual(benchmark[day_one], 100.0)
        self.assertEqual(benchmark[day_two], 110.0)
        self.assertEqual(benchmark[day_three], 121.0)
        self.assertEqual(summary["proxy_membership_rule"], PHASE5_PRIMARY_RESEARCH_BENCHMARK_MEMBERSHIP_RULE)
        self.assertEqual(summary["min_constituent_count"], 1)
        self.assertEqual(summary["max_constituent_count"], 2)

    def test_phase2_rebuild_generates_validation_replay_and_backtest_artifacts(self) -> None:
        early_bars = self.market_bars[:780]
        latest_bars = self.market_bars
        with session_scope(self.database_url) as session:
            first_recommendation = self._refresh_with_market_bars(session, early_bars)
            second_recommendation = self._refresh_with_market_bars(session, latest_bars)
            fill_bar = latest_bars[-120]
            portfolio_key = self._seed_portfolio_track(
                session,
                recommendation_id=second_recommendation.id,
                stock_id=second_recommendation.stock_id,
                requested_at=fill_bar["observed_at"],
                fill_price=float(fill_bar["close_price"]),
            )
            rebuild_stats = rebuild_phase2_research_state(
                session,
                symbols={self.symbol},
                active_symbols={self.symbol},
            )
            session.commit()
            summary = get_latest_recommendation_summary(session, self.symbol)
            artifact_root = artifact_root_from_database_url(self.database_url)

        self.assertEqual(rebuild_stats["recommendations"], 2)
        self.assertEqual(rebuild_stats["validation_artifacts"], 6)
        self.assertEqual(rebuild_stats["replay_artifacts"], 1)
        self.assertEqual(rebuild_stats["backtests"], 1)
        self.assertIsNotNone(summary)
        assert summary is not None
        latest_validation = summary["recommendation"]["historical_validation"]
        latest_metrics_id = f"validation-metrics:{second_recommendation.recommendation_key}:20d"
        self.assertEqual(latest_validation["status"], "research_candidate")
        self.assertEqual(latest_validation["artifact_id"], latest_metrics_id)
        self.assertEqual(latest_validation["manifest_id"], f"rolling-validation:{second_recommendation.recommendation_key}")
        self.assertGreater(latest_validation["metrics"]["sample_count"], 0)
        self.assertEqual(latest_validation["metrics"]["walk_forward"]["coverage_status"], "full_baseline")
        self.assertGreater(latest_validation["metrics"]["walk_forward"]["window_count"], 0)
        self.assertEqual(
            latest_validation["metrics"]["candidate_horizon_comparison"]["selection_readiness"],
            "comparison_ready",
        )
        self.assertEqual(
            len(latest_validation["metrics"]["candidate_horizon_comparison"]["candidates"]),
            3,
        )
        self.assertIn(
            latest_validation["metrics"]["candidate_horizon_comparison"]["recommended_research_leader"]["horizon"],
            {10, 20, 40},
        )

        manifest = read_manifest(f"rolling-validation:{second_recommendation.recommendation_key}", root=artifact_root)
        self.assertEqual(manifest.experiment_version, "phase2-rule-baseline-v1")
        self.assertEqual(manifest.universe_definition, "active_watchlist_full_history_research_universe")
        self.assertEqual(manifest.research_contract["contract_version"], "phase5-validation-policy-contract-v1")
        self.assertEqual(manifest.research_contract["candidate_label_horizons"], [10, 20, 40])
        self.assertEqual(manifest.research_contract["primary_horizon_status"], "pending_phase5_selection")
        self.assertEqual(manifest.research_contract["rolling_split_baseline"]["train_days"], 480)
        self.assertEqual(manifest.research_contract["llm_analysis_scope"], "manual_triggered_structured_context_analysis_only")
        self.assertEqual(manifest.research_contract["simulation_execution_scope"], "simulation_only_auto_execution_no_real_order_routing")
        self.assertEqual(
            manifest.research_contract["required_history"]["market_history_lookback_days"],
            PHASE5_MARKET_HISTORY_LOOKBACK_DAYS,
        )
        self.assertEqual(manifest.benchmark_context["primary_research_benchmark"], "active_watchlist_equal_weight_proxy")
        self.assertEqual(manifest.benchmark_context["market_reference_benchmark"], "CSI300")
        self.assertEqual(manifest.benchmark_context["watchlist_tracking_scope"], "join_date_forward_only")
        self.assertEqual(manifest.rolling_windows[0]["coverage_status"], "full_baseline")
        self.assertEqual(
            manifest.rolling_windows[0]["required_observation_count"],
            PHASE5_REQUIRED_OBSERVATION_COUNT,
        )
        self.assertGreater(manifest.rolling_windows[0]["window_count"], 0)
        self.assertEqual(len(manifest.split_plan), manifest.rolling_windows[0]["window_count"])
        metrics_artifact = read_validation_metrics(latest_metrics_id, root=artifact_root)
        self.assertEqual(metrics_artifact.status, "research_candidate")
        self.assertGreater(metrics_artifact.sample_count, 0)
        self.assertEqual(metrics_artifact.feature_drift_summary["coverage_status"], "full_baseline")

        replay_artifact = read_replay_alignment_artifact(
            f"replay-alignment:{first_recommendation.recommendation_key}",
            root=artifact_root,
        )
        self.assertEqual(replay_artifact.recommendation_key, first_recommendation.recommendation_key)
        self.assertEqual(replay_artifact.validation_status, "research_candidate")
        self.assertEqual(replay_artifact.benchmark_context["contract_version"], "phase5-validation-policy-contract-v1")
        self.assertEqual(replay_artifact.benchmark_context["research_validation_scope"], "full_symbol_history")
        self.assertEqual(replay_artifact.benchmark_context["watchlist_tracking_scope"], "join_date_forward_only")

        backtest_artifact = read_backtest_artifact(
            f"portfolio-backtest:{portfolio_key}",
            root=artifact_root,
        )
        self.assertEqual(backtest_artifact.manifest_id, "rolling-validation:phase2-portfolio-backtests")
        self.assertEqual(backtest_artifact.status, "research_candidate")
        self.assertTrue((artifact_root / "validation" / f"{latest_metrics_id}.json").exists())
        self.assertTrue((artifact_root / "replays" / f"replay-alignment:{first_recommendation.recommendation_key}.json").exists())
        self.assertTrue((artifact_root / "backtests" / f"portfolio-backtest:{portfolio_key}.json").exists())

    def test_phase2_rebuild_records_expanding_watchlist_benchmark_context(self) -> None:
        alt_symbol = "000001.SZ"
        alt_profile = StockProfileResolution(
            symbol=alt_symbol,
            name="平安银行",
            industry="银行",
            listed_date=date(1991, 4, 3),
            template_key="bank",
            source="test_profile",
        )
        trade_day = date(2026, 4, 24)
        alt_market_bars = [
            _lineaged_market_bar(
                alt_symbol,
                trade_day - timedelta(days=839 - index),
                close_price=12.0 + index * 0.08 + ((index % 9) - 4) * 0.03,
                turnover_rate=0.018 + index * 0.00003,
            )
            for index in range(840)
        ]

        with session_scope(self.database_url) as session:
            recommendation = self._refresh_with_market_bars(session, self.market_bars)
            self._refresh_symbol(
                session,
                symbol=alt_symbol,
                profile=alt_profile,
                market_bars=alt_market_bars,
            )
            primary_join_day = self.market_bars[0]["observed_at"].date()
            late_join_day = self.market_bars[240]["observed_at"].date()
            session.add_all(
                [
                    WatchlistEntry(
                        symbol=self.symbol,
                        ticker="300750",
                        exchange="SZSE",
                        display_name="宁德时代",
                        status="active",
                        source_kind="test_fixture",
                        analysis_status="ready",
                        last_analyzed_at=recommendation.generated_at,
                        last_error=None,
                        watchlist_payload={"source_kind": "test_fixture"},
                        created_at=datetime.combine(primary_join_day, time(9, 0), tzinfo=SHANGHAI_TZ),
                        updated_at=datetime.combine(primary_join_day, time(9, 0), tzinfo=SHANGHAI_TZ),
                        **build_lineage(
                            {"symbol": self.symbol},
                            source_uri=f"test://watchlist/{self.symbol}",
                            license_tag="test-fixture",
                            usage_scope="internal_research",
                            redistribution_scope="none",
                        ),
                    ),
                    WatchlistEntry(
                        symbol=alt_symbol,
                        ticker="000001",
                        exchange="SZSE",
                        display_name="平安银行",
                        status="active",
                        source_kind="test_fixture",
                        analysis_status="ready",
                        last_analyzed_at=recommendation.generated_at,
                        last_error=None,
                        watchlist_payload={"source_kind": "test_fixture"},
                        created_at=datetime.combine(late_join_day, time(9, 0), tzinfo=SHANGHAI_TZ),
                        updated_at=datetime.combine(late_join_day, time(9, 0), tzinfo=SHANGHAI_TZ),
                        **build_lineage(
                            {"symbol": alt_symbol},
                            source_uri=f"test://watchlist/{alt_symbol}",
                            license_tag="test-fixture",
                            usage_scope="internal_research",
                            redistribution_scope="none",
                        ),
                    ),
                ]
            )
            rebuild_phase2_research_state(
                session,
                symbols={self.symbol},
                active_symbols={self.symbol, alt_symbol},
            )
            session.commit()
            artifact_root = artifact_root_from_database_url(self.database_url)

        manifest = read_manifest(f"rolling-validation:{recommendation.recommendation_key}", root=artifact_root)
        self.assertEqual(
            manifest.benchmark_context["primary_research_benchmark_membership_rule"],
            PHASE5_PRIMARY_RESEARCH_BENCHMARK_MEMBERSHIP_RULE,
        )
        self.assertEqual(manifest.benchmark_context["defaulted_symbol_count"], 0)
        self.assertEqual(manifest.benchmark_context["min_constituent_count"], 1)
        self.assertEqual(manifest.benchmark_context["max_constituent_count"], 2)
        self.assertEqual(manifest.benchmark_context["first_active_day"], primary_join_day.isoformat())

    def test_phase2_rebuild_replay_uses_latest_eligible_history_when_newer_same_day_versions_exist(self) -> None:
        early_bars = self.market_bars[:-120]
        latest_bars = self.market_bars

        with session_scope(self.database_url) as session:
            eligible_recommendation = self._refresh_with_market_bars(session, early_bars)
            same_day_prior_version = self._refresh_with_market_bars(session, latest_bars)
            self._refresh_with_market_bars(session, latest_bars)
            rebuild_stats = rebuild_phase2_research_state(
                session,
                symbols={self.symbol},
                active_symbols={self.symbol},
            )
            session.commit()
            artifact_root = artifact_root_from_database_url(self.database_url)

        self.assertEqual(rebuild_stats["replay_artifacts"], 1)
        replay_artifact = read_replay_alignment_artifact(
            f"replay-alignment:{eligible_recommendation.recommendation_key}",
            root=artifact_root,
        )
        self.assertEqual(replay_artifact.recommendation_key, eligible_recommendation.recommendation_key)
        self.assertNotEqual(replay_artifact.recommendation_key, same_day_prior_version.recommendation_key)
        self.assertEqual(replay_artifact.validation_status, "research_candidate")
        self.assertEqual(
            replay_artifact.benchmark_context["primary_research_benchmark_membership_rule"],
            PHASE5_PRIMARY_RESEARCH_BENCHMARK_MEMBERSHIP_RULE,
        )

    def test_phase2_rebuild_replay_prefers_non_stale_same_as_of_version(self) -> None:
        with session_scope(self.database_url) as session:
            self._refresh_with_market_bars(session, self.market_bars[:-120])
            self._refresh_with_market_bars(session, self.market_bars)
            fresh, stale = inject_market_data_stale_backfill(session, self.symbol)
            payload = dict(fresh.recommendation_payload or {})
            evidence = dict(payload.get("evidence") or {})
            evidence["degrade_flags"] = [
                str(item)
                for item in evidence.get("degrade_flags") or []
                if item and str(item) != "market_data_stale"
            ]
            payload["evidence"] = evidence
            fresh.recommendation_payload = payload
            rebuild_stats = rebuild_phase2_research_state(
                session,
                symbols={self.symbol},
                active_symbols={self.symbol},
            )
            session.commit()

        self.assertEqual(rebuild_stats["replay_artifacts"], 0)

        with session_scope(self.database_url) as session:
            latest = get_latest_recommendation_summary(session, self.symbol)

        self.assertIsNotNone(latest)
        self.assertEqual(latest["recommendation"]["recommendation_key"], fresh.recommendation_key)
        self.assertNotEqual(latest["recommendation"]["recommendation_key"], stale.recommendation_key)

    def test_phase2_rebuild_historical_validation_excludes_future_exit_bars(self) -> None:
        early_bars = self.market_bars[:780]
        latest_bars = self.market_bars

        with session_scope(self.database_url) as session:
            early_recommendation = self._refresh_with_market_bars(session, early_bars)
            latest_recommendation = self._refresh_with_market_bars(session, latest_bars)
            rebuild_phase2_research_state(
                session,
                symbols={self.symbol},
                active_symbols={self.symbol},
            )
            session.commit()
            artifact_root = artifact_root_from_database_url(self.database_url)

        early_metrics = read_validation_metrics(
            f"validation-metrics:{early_recommendation.recommendation_key}:40d",
            root=artifact_root,
        )
        latest_metrics = read_validation_metrics(
            f"validation-metrics:{latest_recommendation.recommendation_key}:40d",
            root=artifact_root,
        )

        self.assertLess(
            early_metrics.sample_count,
            latest_metrics.sample_count,
            "historical validation must not reuse future exit bars beyond the recommendation as_of",
        )


if __name__ == "__main__":
    unittest.main()
