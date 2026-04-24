from __future__ import annotations

from datetime import date, datetime
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from ashare_evidence.dashboard_demo import build_dashboard_bundle
from ashare_evidence.market_clock import latest_completed_trade_day


class MarketClockTests(unittest.TestCase):
    def test_before_close_uses_previous_business_day(self) -> None:
        reference = datetime(2026, 4, 24, 11, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
        self.assertEqual(latest_completed_trade_day(reference), date(2026, 4, 23))

    def test_after_close_uses_same_day(self) -> None:
        reference = datetime(2026, 4, 24, 15, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
        self.assertEqual(latest_completed_trade_day(reference), date(2026, 4, 24))

    def test_weekend_rolls_back_to_friday(self) -> None:
        reference = datetime(2026, 4, 25, 11, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
        self.assertEqual(latest_completed_trade_day(reference), date(2026, 4, 24))

    def test_dashboard_bundle_tracks_latest_trade_day(self) -> None:
        with patch("ashare_evidence.dashboard_demo.latest_completed_trade_day", return_value=date(2026, 4, 23)):
            bundle = build_dashboard_bundle("600519.SH")

        self.assertEqual(bundle.market_bars[-1]["observed_at"].date(), date(2026, 4, 23))
        self.assertEqual(bundle.recommendation["as_of_data_time"].date(), date(2026, 4, 23))
        self.assertEqual(bundle.news_items[-1]["published_at"].date(), date(2026, 4, 23))


if __name__ == "__main__":
    unittest.main()
