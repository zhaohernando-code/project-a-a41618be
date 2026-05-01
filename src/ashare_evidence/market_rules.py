from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

BOARD_RULES: dict[str, dict[str, Any]] = {
    "main": {"lot": 100, "limit_pct": 0.10, "label": "主板"},
    "star": {"lot": 200, "limit_pct": 0.20, "label": "科创板"},
    "chnext": {"lot": 100, "limit_pct": 0.20, "label": "创业板"},
    "bse": {"lot": 100, "limit_pct": 0.30, "label": "北交所"},
    "st": {"lot": 100, "limit_pct": 0.05, "label": "ST/风险警示"},
}


def _profile_value(stock_profile: Any, key: str) -> Any:
    if stock_profile is None:
        return None
    if isinstance(stock_profile, dict):
        return stock_profile.get(key)
    return getattr(stock_profile, key, None)


def _payload_value(stock_profile: Any, *keys: str) -> Any:
    payload = _profile_value(stock_profile, "profile_payload")
    if not isinstance(payload, dict):
        payload = stock_profile if isinstance(stock_profile, dict) else {}
    for key in keys:
        if key in payload and payload[key] not in {None, ""}:
            return payload[key]
    return None


def _listed_date(stock_profile: Any) -> date | None:
    value = _profile_value(stock_profile, "listed_date") or _payload_value(stock_profile, "listed_date", "list_date")
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        cleaned = value.strip()
        for fmt in ("%Y-%m-%d", "%Y%m%d"):
            try:
                return datetime.strptime(cleaned, fmt).date()
            except ValueError:
                continue
    return None


def _business_day_distance(start: date, end: date) -> int:
    if start > end:
        return 0
    cursor = start
    count = 0
    while cursor <= end:
        if cursor.weekday() < 5:
            count += 1
        cursor += timedelta(days=1)
    return count


def _infer_board(symbol: str, stock_profile: Any = None) -> tuple[str, str]:
    ticker = symbol.split(".", 1)[0]
    raw_board = str(_payload_value(stock_profile, "board", "market_board", "board_name") or "").lower()
    raw_name = str(_profile_value(stock_profile, "name") or _payload_value(stock_profile, "name", "stock_name") or "")
    is_st = bool(_payload_value(stock_profile, "is_st", "st")) or "st" in raw_name.lower() or raw_name.startswith(("*ST", "ST"))
    if is_st:
        return "st", "profile_st_flag"
    if any(token in raw_board for token in ("科创", "star", "sse star")) or ticker.startswith("688"):
        return "star", "profile_or_prefix"
    if any(token in raw_board for token in ("创业", "chinext", "创业板")) or ticker.startswith(("300", "301")):
        return "chnext", "profile_or_prefix"
    if any(token in raw_board for token in ("北交", "bse", "北证")) or ticker.startswith(("8", "4")):
        return "bse", "profile_or_prefix"
    if raw_board or ticker.startswith(("000", "001", "002", "003", "600", "601", "603", "605")):
        return "main", "profile_or_prefix"
    return "main", "wip_unknown"


def board_rule(
    symbol: str,
    *,
    stock_profile: Any = None,
    as_of: date | datetime | None = None,
) -> dict[str, Any]:
    board_id, source = _infer_board(symbol, stock_profile)
    rule = dict(BOARD_RULES[board_id])
    rule["board"] = board_id
    rule["rule_source"] = source
    rule["rule_status"] = "verified" if source != "wip_unknown" else "wip_unknown"
    listed = _listed_date(stock_profile)
    as_of_day = as_of.date() if isinstance(as_of, datetime) else as_of
    if listed is not None and as_of_day is not None:
        trading_day_index = _business_day_distance(listed, as_of_day)
        if 1 <= trading_day_index <= 5:
            rule["limit_pct"] = None
            rule["new_listing_no_limit"] = True
            rule["new_listing_trading_day_index"] = trading_day_index
        else:
            rule["new_listing_no_limit"] = False
            rule["new_listing_trading_day_index"] = trading_day_index
    else:
        rule["new_listing_no_limit"] = False
        rule["new_listing_trading_day_index"] = None
    return rule
