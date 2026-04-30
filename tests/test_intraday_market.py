from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import select

from ashare_evidence.db import init_database, session_scope
from ashare_evidence.intraday_market import _parse_row_time, sync_intraday_market
from ashare_evidence.lineage import build_lineage
from ashare_evidence.models import MarketBar, Stock


def _seed_stock(session, *, symbol: str = "600519.SH") -> Stock:
    payload = {
        "symbol": symbol,
        "ticker": "600519",
        "exchange": "SSE",
        "name": "贵州茅台",
    }
    stock = Stock(
        symbol=symbol,
        ticker="600519",
        exchange="SSE",
        name="贵州茅台",
        provider_symbol=symbol,
        status="active",
        listed_date=None,
        delisted_date=None,
        profile_payload={"provider": "fixture"},
        **build_lineage(
            payload,
            source_uri=f"fixture://stock/{symbol}",
            license_tag="internal-derived",
            usage_scope="internal_research",
            redistribution_scope="none",
        ),
    )
    session.add(stock)
    session.flush()
    return stock


def _seed_intraday_bar(session, *, stock: Stock, observed_at: datetime) -> None:
    payload = {
        "symbol": stock.symbol,
        "observed_at": observed_at.isoformat(),
        "timeframe": "5min",
    }
    session.add(
        MarketBar(
            bar_key=f"bar-{stock.ticker}-5min-{observed_at:%Y%m%d%H%M}",
            stock_id=stock.id,
            timeframe="5min",
            observed_at=observed_at,
            open_price=100.0,
            high_price=100.5,
            low_price=99.8,
            close_price=100.2,
            volume=10_000.0,
            amount=1_002_000.0,
            turnover_rate=None,
            adj_factor=None,
            raw_payload={"provider": "fixture"},
            **build_lineage(
                payload,
                source_uri=f"fixture://market-bar/{stock.symbol}/{observed_at.isoformat()}",
                license_tag="internal-derived",
                usage_scope="internal_research",
                redistribution_scope="none",
            ),
        )
    )
    session.flush()


class IntradayMarketTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "intraday.db"
        self.database_url = f"sqlite:///{database_path}"
        init_database(self.database_url)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_parse_row_time_interprets_market_clock_as_asia_shanghai(self) -> None:
        parsed = _parse_row_time("2026-04-24 09:35:00")
        self.assertEqual(parsed, datetime(2026, 4, 24, 1, 35, tzinfo=timezone.utc))

    def test_sync_intraday_market_reuses_recent_cached_bars_without_hitting_upstream(self) -> None:
        observed_at = datetime(2026, 4, 24, 1, 35, tzinfo=timezone.utc)
        with session_scope(self.database_url) as session:
            stock = _seed_stock(session)
            _seed_intraday_bar(session, stock=stock, observed_at=observed_at)

        with session_scope(self.database_url) as session:
            with patch("ashare_evidence.intraday_market._tushare_rows", side_effect=AssertionError("unexpected tushare call")):
                with patch(
                    "ashare_evidence.intraday_market._akshare_rows_for_window",
                    side_effect=AssertionError("unexpected akshare call"),
                ):
                    status = sync_intraday_market(
                        session,
                        ["600519.SH"],
                        now=datetime(2026, 4, 24, 1, 36, tzinfo=timezone.utc),
                    )

        self.assertEqual(status["source_kind"], "cached_5min")
        self.assertEqual(status["provider_label"], "本地已缓存 5 分钟数据")
        self.assertFalse(status["stale"])

    def test_sync_intraday_market_uses_akshare_fallback_after_cache_turns_stale(self) -> None:
        observed_at = datetime(2026, 4, 24, 1, 35, tzinfo=timezone.utc)
        with session_scope(self.database_url) as session:
            stock = _seed_stock(session)
            _seed_intraday_bar(session, stock=stock, observed_at=observed_at)

        akshare_rows = [
            {
                "时间": "2026-04-24 09:45:00",
                "开盘": "100.3",
                "收盘": "100.6",
                "最高": "100.8",
                "最低": "100.1",
                "成交量": "12345",
                "成交额": "1240000",
            }
        ]

        with session_scope(self.database_url) as session:
            with patch("ashare_evidence.intraday_market._tushare_rows", return_value=[]):
                with patch("ashare_evidence.intraday_market._akshare_rows_for_window", return_value=akshare_rows):
                    status = sync_intraday_market(
                        session,
                        ["600519.SH"],
                        now=datetime(2026, 4, 24, 1, 46, tzinfo=timezone.utc),
                    )
            latest = session.scalar(
                select(MarketBar)
                .join(Stock)
                .where(Stock.symbol == "600519.SH", MarketBar.timeframe == "5min")
                .order_by(MarketBar.observed_at.desc())
                .limit(1)
            )

        self.assertEqual(status["provider_name"], "akshare")
        self.assertTrue(status["fallback_used"])
        self.assertFalse(status["stale"])
        self.assertIsNotNone(latest)
        assert latest is not None
        latest_observed_at = latest.observed_at.replace(tzinfo=timezone.utc) if latest.observed_at.tzinfo is None else latest.observed_at
        self.assertEqual(latest_observed_at, datetime(2026, 4, 24, 1, 45, tzinfo=timezone.utc))
        self.assertAlmostEqual(latest.close_price, 100.6)


if __name__ == "__main__":
    unittest.main()
