from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

MARKET_TIMEZONE = ZoneInfo("Asia/Shanghai")
MARKET_OPEN_TIME = time(9, 30)
MARKET_MORNING_CLOSE_TIME = time(11, 30)
MARKET_AFTERNOON_OPEN_TIME = time(13, 0)
MARKET_CLOSE_TIME = time(15, 0)


def _market_now(reference: datetime | None = None) -> datetime:
    if reference is None:
        return datetime.now(MARKET_TIMEZONE)
    if reference.tzinfo is None:
        return reference.replace(tzinfo=MARKET_TIMEZONE)
    return reference.astimezone(MARKET_TIMEZONE)


def latest_completed_trade_day(reference: datetime | None = None) -> date:
    current = _market_now(reference)
    trade_day = current.date()
    if trade_day.weekday() >= 5 or current.time() < MARKET_CLOSE_TIME:
        trade_day -= timedelta(days=1)
    while trade_day.weekday() >= 5:
        trade_day -= timedelta(days=1)
    return trade_day


def is_market_session_open(reference: datetime | None = None) -> bool:
    current = _market_now(reference)
    if current.weekday() >= 5:
        return False
    current_time = current.time()
    return (
        MARKET_OPEN_TIME <= current_time < MARKET_MORNING_CLOSE_TIME
        or MARKET_AFTERNOON_OPEN_TIME <= current_time < MARKET_CLOSE_TIME
    )
