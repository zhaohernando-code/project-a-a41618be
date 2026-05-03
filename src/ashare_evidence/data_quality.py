from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ashare_evidence.market_bar_qa import check_bar_unit_consistency, dedup_daily_bars
from ashare_evidence.market_rules import board_rule
from ashare_evidence.models import FeatureSnapshot, MarketBar, NewsEntityLink, NewsItem, Stock

QUALITY_WEIGHTS = {
    "daily_completeness": 0.40,
    "price_freshness": 0.15,
    "news_coverage": 0.20,
    "financial_freshness": 0.15,
    "profile_completeness": 0.10,
}

PASS_THRESHOLD = 0.85
WARN_THRESHOLD = 0.65


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _status_from_score(score: float) -> str:
    if score >= PASS_THRESHOLD:
        return "pass"
    if score >= WARN_THRESHOLD:
        return "warn"
    return "fail"


def _latest_daily_bars(session: Session, stock_id: int, *, limit: int = 80) -> list[MarketBar]:
    bars = session.scalars(
        select(MarketBar)
        .where(MarketBar.stock_id == stock_id, MarketBar.timeframe == "1d")
        .order_by(MarketBar.observed_at.desc())
        .limit(limit)
    ).all()
    return dedup_daily_bars(list(reversed(bars)))


def _trading_days_between(start: date, end: date) -> int:
    if start > end:
        return 0
    cursor = start
    count = 0
    while cursor <= end:
        if cursor.weekday() < 5:
            count += 1
        cursor += timedelta(days=1)
    return count


def _daily_completeness(bars: list[MarketBar], *, as_of: datetime) -> dict[str, Any]:
    recent = bars[-20:]
    latest_day = recent[-1].observed_at.date() if recent else None
    first_day = recent[0].observed_at.date() if recent else None
    expected = _trading_days_between(first_day, latest_day) if first_day and latest_day else 20
    expected = max(min(expected, 20), 1)
    score = min(len({bar.observed_at.date() for bar in recent}) / expected, 1.0)
    warnings = check_bar_unit_consistency(recent)
    if warnings:
        score = min(score, 0.75)
    return {
        "score": round(score, 4),
        "status": _status_from_score(score),
        "recent_day_count": len(recent),
        "expected_day_count": expected,
        "latest_trade_day": latest_day.isoformat() if latest_day else None,
        "warnings": warnings,
    }


def _price_freshness(bars: list[MarketBar], *, as_of: datetime) -> dict[str, Any]:
    latest = _as_utc(bars[-1].observed_at) if bars else None
    if latest is None:
        return {"score": 0.0, "status": "fail", "latest_observed_at": None, "age_days": None}
    age_days = max((as_of.date() - latest.date()).days, 0)
    if age_days <= 2:
        score = 1.0
    elif age_days <= 5:
        score = 0.7
    else:
        score = 0.25
    return {
        "score": score,
        "status": _status_from_score(score),
        "latest_observed_at": latest.isoformat(),
        "age_days": age_days,
    }


def _news_coverage(session: Session, stock_id: int, *, as_of: datetime) -> dict[str, Any]:
    cutoff = as_of - timedelta(days=30)
    latest = session.scalar(
        select(func.max(NewsItem.published_at))
        .join(NewsEntityLink, NewsEntityLink.news_id == NewsItem.id)
        .where(NewsEntityLink.stock_id == stock_id, NewsItem.published_at <= as_of)
    )
    recent_count = session.scalar(
        select(func.count(NewsItem.id))
        .join(NewsEntityLink, NewsEntityLink.news_id == NewsItem.id)
        .where(
            NewsEntityLink.stock_id == stock_id,
            NewsItem.published_at <= as_of,
            NewsItem.published_at >= cutoff,
        )
    ) or 0
    latest_at = _as_utc(latest)
    if recent_count >= 2:
        score = 1.0
    elif recent_count == 1:
        score = 0.8
    else:
        score = WARN_THRESHOLD
    return {
        "score": score,
        "status": _status_from_score(score),
        "recent_count": int(recent_count),
        "latest_published_at": latest_at.isoformat() if latest_at else None,
        "lookback_days": 30,
        "note": None if recent_count else "缺少近 30 天个股新闻；仅降置信度，不单独触发 hard cap。",
    }


def _parse_financial_snapshot_date(raw: Any) -> date | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return _as_utc(raw).date()
    if isinstance(raw, date):
        return raw
    value = str(raw).strip()
    if not value or value in {"-", "--", "nan", "None", "null"}:
        return None
    digits = "".join(character for character in value if character.isdigit())
    if len(digits) >= 8:
        try:
            return date(int(digits[0:4]), int(digits[4:6]), int(digits[6:8]))
        except ValueError:
            return None
    if len(digits) == 4:
        year = int(digits)
        if any(token in value for token in ("一季", "1季", "Q1")):
            return date(year, 3, 31)
        if any(token in value for token in ("中报", "半年", "半年度", "二季", "2季", "Q2")):
            return date(year, 6, 30)
        if any(token in value for token in ("三季", "3季", "Q3")):
            return date(year, 9, 30)
        if any(token in value for token in ("年报", "年度", "Q4")):
            return date(year, 12, 31)
    return None


def _profile_financial_snapshot_at(stock: Stock) -> datetime | None:
    payload = stock.profile_payload if isinstance(stock.profile_payload, dict) else {}
    snapshot = payload.get("financial_snapshot")
    if not isinstance(snapshot, dict):
        return None
    candidates: list[date] = []
    for key in ("latest_as_of", "as_of", "ann_date", "notice_date", "end_date", "report_period"):
        parsed = _parse_financial_snapshot_date(snapshot.get(key))
        if parsed is not None:
            candidates.append(parsed)
    history = snapshot.get("quarterly_history")
    if isinstance(history, list):
        for item in history[:4]:
            if not isinstance(item, dict):
                continue
            for key in ("ann_date", "notice_date", "end_date", "report_period"):
                parsed = _parse_financial_snapshot_date(item.get(key))
                if parsed is not None:
                    candidates.append(parsed)
    if not candidates:
        return None
    latest_day = max(candidates)
    return datetime(latest_day.year, latest_day.month, latest_day.day, tzinfo=UTC)


def _financial_freshness(session: Session, stock: Stock, *, as_of: datetime) -> dict[str, Any]:
    feature_latest = session.scalar(
        select(func.max(FeatureSnapshot.as_of)).where(
            FeatureSnapshot.stock_id == stock.id,
            FeatureSnapshot.feature_set_name.in_(("fundamental", "financial", "phase2_features")),
        )
    )
    candidates = [candidate for candidate in (_as_utc(feature_latest), _profile_financial_snapshot_at(stock)) if candidate is not None]
    latest_at = max(candidates) if candidates else None
    if latest_at is None:
        score = 0.0
        age_days = None
    else:
        age_days = max((as_of.date() - latest_at.date()).days, 0)
        if age_days <= 120:
            score = 1.0
        elif age_days <= 210:
            score = 0.7
        else:
            score = 0.25
    return {
        "score": score,
        "status": _status_from_score(score),
        "latest_as_of": latest_at.isoformat() if latest_at else None,
        "age_days": age_days,
    }


def _profile_completeness(stock: Stock, *, as_of: datetime) -> dict[str, Any]:
    profile = stock.profile_payload or {}
    missing: list[str] = []
    if not stock.listed_date:
        missing.append("listed_date")
    if not stock.name:
        missing.append("name")
    if not stock.provider_symbol:
        missing.append("provider_symbol")
    if not (profile.get("board") or profile.get("market_board") or profile.get("board_name")):
        missing.append("board")
    rule = board_rule(stock.symbol, stock_profile=stock, as_of=as_of.date())
    if rule.get("rule_status") == "wip_unknown":
        missing.append("board_rule")
    score = max(1.0 - len(set(missing)) * 0.2, 0.0)
    return {
        "score": round(score, 4),
        "status": _status_from_score(score),
        "missing": sorted(set(missing)),
        "board_rule": rule,
    }


def build_stock_data_quality(
    session: Session,
    stock_or_symbol: Stock | str,
    *,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    as_of = _as_utc(as_of) or datetime.now(UTC)
    stock = (
        stock_or_symbol
        if isinstance(stock_or_symbol, Stock)
        else session.scalar(select(Stock).where(Stock.symbol == stock_or_symbol))
    )
    if stock is None:
        raise LookupError(f"Stock not found: {stock_or_symbol}")
    daily_bars = _latest_daily_bars(session, stock.id)
    daily = _daily_completeness(daily_bars, as_of=as_of)
    price = _price_freshness(daily_bars, as_of=as_of)
    news = _news_coverage(session, stock.id, as_of=as_of)
    financial = _financial_freshness(session, stock, as_of=as_of)
    profile = _profile_completeness(stock, as_of=as_of)
    components = {
        "daily_completeness": daily,
        "price_freshness": price,
        "news_coverage": news,
        "financial_freshness": financial,
        "profile_completeness": profile,
    }
    coverage_score = sum(float(components[key]["score"]) * weight for key, weight in QUALITY_WEIGHTS.items())
    degraded_sources: list[str] = []
    if daily["status"] != "pass":
        degraded_sources.append("daily_bar_completeness")
    if price["status"] != "pass":
        degraded_sources.append("market_data_stale")
    if news["status"] != "pass":
        degraded_sources.append("data_coverage_gap:news")
    if financial["status"] != "pass":
        degraded_sources.append("financial_data_stale")
    if profile["status"] != "pass":
        degraded_sources.append("profile_incomplete")
    return {
        "symbol": stock.symbol,
        "name": stock.name,
        "coverage_score": round(coverage_score, 4),
        "status": _status_from_score(coverage_score),
        "degraded_sources": degraded_sources,
        "bar_warnings": daily["warnings"],
        "news_coverage": news,
        "financial_freshness": financial,
        "profile_completeness": profile,
        "components": components,
        "computed_at": as_of.isoformat(),
    }


def build_data_quality_summary(
    session: Session,
    *,
    symbols: list[str] | tuple[str, ...] | set[str] | None = None,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    as_of = _as_utc(as_of) or datetime.now(UTC)
    query = select(Stock).order_by(Stock.symbol.asc())
    if symbols is not None:
        normalized_symbols = sorted({str(symbol) for symbol in symbols})
        if not normalized_symbols:
            return {
                "generated_at": as_of.isoformat(),
                "symbol_count": 0,
                "pass_count": 0,
                "warn_count": 0,
                "fail_count": 0,
                "status": "fail",
                "degraded_sources": [],
                "items": [],
                "scoring_weights": QUALITY_WEIGHTS,
                "thresholds": {"pass": PASS_THRESHOLD, "warn": WARN_THRESHOLD},
            }
        query = query.where(Stock.symbol.in_(normalized_symbols))
    items = [build_stock_data_quality(session, stock, as_of=as_of) for stock in session.scalars(query).all()]
    status_counts = Counter(item["status"] for item in items)
    degraded = sorted({source for item in items for source in item["degraded_sources"]})
    return {
        "generated_at": as_of.isoformat(),
        "symbol_count": len(items),
        "pass_count": int(status_counts.get("pass", 0)),
        "warn_count": int(status_counts.get("warn", 0)),
        "fail_count": int(status_counts.get("fail", 0)),
        "status": "fail" if status_counts.get("fail") else "warn" if status_counts.get("warn") else "pass",
        "degraded_sources": degraded,
        "items": items,
        "scoring_weights": QUALITY_WEIGHTS,
        "thresholds": {"pass": PASS_THRESHOLD, "warn": WARN_THRESHOLD},
    }
