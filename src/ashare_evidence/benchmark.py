from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ashare_evidence.models import MarketBar, Stock

CSI_BENCHMARKS: dict[str, dict[str, str]] = {
    "CSI300": {"symbol": "000300.SH", "label": "沪深300"},
    "CSI500": {"symbol": "000905.SH", "label": "中证500"},
    "CSI1000": {"symbol": "000852.SH", "label": "中证1000"},
}

DEFAULT_BENCHMARK_ID = "CSI300"


def benchmark_symbols() -> list[str]:
    return [item["symbol"] for item in CSI_BENCHMARKS.values()]


def benchmark_close_maps(session: Session) -> dict[str, dict[Any, float]]:
    rows = session.execute(
        select(Stock.symbol, MarketBar.observed_at, MarketBar.close_price)
        .join(MarketBar, MarketBar.stock_id == Stock.id)
        .where(Stock.symbol.in_(benchmark_symbols()), MarketBar.timeframe == "1d")
        .order_by(Stock.symbol.asc(), MarketBar.observed_at.asc())
    ).all()
    by_symbol: dict[str, dict[Any, float]] = {symbol: {} for symbol in benchmark_symbols()}
    for symbol, observed_at, close_price in rows:
        by_symbol[str(symbol)][observed_at.date()] = float(close_price)
    return by_symbol


def benchmark_context_summary(session: Session) -> dict[str, Any]:
    close_maps = benchmark_close_maps(session)
    items: list[dict[str, Any]] = []
    available = 0
    for benchmark_id, definition in CSI_BENCHMARKS.items():
        symbol = definition["symbol"]
        series = close_maps.get(symbol, {})
        latest_day = max(series) if series else None
        if series:
            available += 1
        items.append(
            {
                "benchmark_id": benchmark_id,
                "symbol": symbol,
                "label": definition["label"],
                "bar_count": len(series),
                "latest_trade_day": latest_day.isoformat() if latest_day else None,
                "status": "available" if series else "missing",
            }
        )
    status = "available" if close_maps.get(CSI_BENCHMARKS[DEFAULT_BENCHMARK_ID]["symbol"]) else "pending_index_bars"
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "primary_benchmark": DEFAULT_BENCHMARK_ID,
        "primary_symbol": CSI_BENCHMARKS[DEFAULT_BENCHMARK_ID]["symbol"],
        "primary_label": CSI_BENCHMARKS[DEFAULT_BENCHMARK_ID]["label"],
        "research_benchmarks": items,
        "available_benchmark_count": available,
        "status": status,
        "note": (
            "主展示 benchmark 采用沪深300；研究 artifact 同时保留沪深300、中证500、中证1000。"
            if status == "available"
            else "CSI 指数日线尚未完整入库；研究结论不得只依赖旧的观察池等权 proxy。"
        ),
    }
