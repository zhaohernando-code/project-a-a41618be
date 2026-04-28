from __future__ import annotations

from datetime import date, datetime
import unittest
from zoneinfo import ZoneInfo

from ashare_evidence.market_clock import is_market_session_open, latest_completed_trade_day


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

    def test_market_session_is_open_during_morning_and_afternoon(self) -> None:
        self.assertTrue(is_market_session_open(datetime(2026, 4, 24, 10, 15, tzinfo=ZoneInfo("Asia/Shanghai"))))
        self.assertTrue(is_market_session_open(datetime(2026, 4, 24, 14, 15, tzinfo=ZoneInfo("Asia/Shanghai"))))

    def test_market_session_is_closed_during_lunch_and_weekend(self) -> None:
        self.assertFalse(is_market_session_open(datetime(2026, 4, 24, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))))
        self.assertFalse(is_market_session_open(datetime(2026, 4, 25, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))))

if __name__ == "__main__":
    unittest.main()
