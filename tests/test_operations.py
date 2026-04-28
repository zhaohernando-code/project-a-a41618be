from __future__ import annotations

import unittest
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from ashare_evidence.operations import _portfolio_payload

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


class OperationsTests(unittest.TestCase):
    def test_portfolio_payload_tolerates_benchmark_starting_after_first_trade_day(self) -> None:
        portfolio = SimpleNamespace(
            portfolio_payload={"starting_cash": 1_000.0},
            cash_balance=1_000.0,
            orders=[],
            name="测试组合",
            mode="manual",
            portfolio_key="test-portfolio",
            benchmark_symbol="000300.SH",
            status="active",
        )
        timeline_points = [
            datetime(2026, 1, 2, 15, 0, tzinfo=SHANGHAI_TZ),
            datetime(2026, 1, 5, 15, 0, tzinfo=SHANGHAI_TZ),
            datetime(2026, 1, 6, 15, 0, tzinfo=SHANGHAI_TZ),
        ]
        payload = _portfolio_payload(
            portfolio,
            active_symbols={"600519.SH"},
            stock_names={"600519.SH": "贵州茅台"},
            price_history={
                "600519.SH": [
                    (timeline_points[0], 100.0),
                    (timeline_points[1], 101.0),
                    (timeline_points[2], 102.0),
                ]
            },
            timeline_points=timeline_points,
            benchmark_close_map={
                timeline_points[1].date(): 100.0,
                timeline_points[2].date(): 110.0,
            },
            recommendation_hit_rate=0.0,
            market_data_timeframe="1d",
        )

        benchmark_nav = [point["benchmark_nav"] for point in payload["nav_history"]]
        self.assertEqual(benchmark_nav, [1000.0, 1000.0, 1100.0])


if __name__ == "__main__":
    unittest.main()
