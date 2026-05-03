from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from typing import Any
from urllib import error, parse, request
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from ashare_evidence.analysis_enrichment import (
    _CNINFO_CONTENT_RE as _ANALYSIS_ENRICHMENT_CNINFO_CONTENT_RE,
)
from ashare_evidence.analysis_enrichment import (
    _HTML_TAG as _ANALYSIS_ENRICHMENT_HTML_TAG,
)
from ashare_evidence.analysis_enrichment import (
    compute_financial_trends,
    enrich_with_llm_analysis,
    fetch_announcement_body,
)
from ashare_evidence.http_client import urlopen
from ashare_evidence.lineage import build_lineage
from ashare_evidence.market_rules import board_rule
from ashare_evidence.models import ProviderCredential, Recommendation, Stock
from ashare_evidence.phase2 import rebuild_phase2_research_state
from ashare_evidence.phase2.phase5_contract import PHASE5_MARKET_HISTORY_LOOKBACK_DAYS
from ashare_evidence.providers import EvidenceBundle, with_lineage
from ashare_evidence.services import ingest_bundle
from ashare_evidence.signal_engine import build_signal_artifacts
from ashare_evidence.stock_master import DEFAULT_AKSHARE_TIMEOUT_SECONDS, StockProfileResolution, resolve_stock_profile
from ashare_evidence.symbols import normalize_symbol

DEFAULT_TUSHARE_BASE_URL = "http://api.tushare.pro"
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
DAILY_LOOKBACK_DAYS = PHASE5_MARKET_HISTORY_LOOKBACK_DAYS
ANNOUNCEMENT_LOOKBACK_DAYS = 30
ANNOUNCEMENT_LIMIT = 12
RESEARCH_METADATA_LIMIT = 5
MIN_EXISTING_RECOMMENDATION_DAYS_FOR_BACKFILL = 3

# Backward-compatible names for older tests and helper scripts. The implementation
# lives in analysis_enrichment.
_compute_financial_trends = compute_financial_trends
_CNINFO_CONTENT_RE = _ANALYSIS_ENRICHMENT_CNINFO_CONTENT_RE
_HTML_TAG = _ANALYSIS_ENRICHMENT_HTML_TAG

class RealDataRefreshError(RuntimeError):
    pass

@dataclass(frozen=True)
class DailyMarketFetch:
    provider_name: str
    bars: list[dict[str, Any]]

def _normalize_text(raw: Any) -> str | None:
    if raw is None:
        return None
    value = str(raw).strip()
    if not value or value in {"nan", "None", "null", "--", "-"}:
        return None
    return value

def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value

def _normalize_symbol_parts(symbol: str) -> tuple[str, str]:
    ticker, _, market = symbol.partition(".")
    market = market.upper()
    if market not in {"SH", "SZ", "BJ"}:
        raise ValueError(f"Unsupported symbol market: {symbol}")
    return ticker, market

def _exchange_name(market: str) -> str:
    return {
        "SH": "SSE",
        "SZ": "SZSE",
        "BJ": "BSE",
    }[market]

def _akshare_prefixed_symbol(symbol: str) -> str:
    ticker, market = _normalize_symbol_parts(symbol)
    return f"{market.lower()}{ticker}"

def _to_float(raw: Any) -> float | None:
    if raw is None:
        return None
    try:
        return float(str(raw).replace(",", ""))
    except (TypeError, ValueError):
        return None

def _parse_day(raw: Any) -> date | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    digits = "".join(character for character in str(raw) if character.isdigit())
    if len(digits) != 8:
        return None
    return date(int(digits[0:4]), int(digits[4:6]), int(digits[6:8]))

def _close_timestamp(trade_day: date) -> datetime:
    return datetime.combine(trade_day, time(15, 0), tzinfo=SHANGHAI_TZ)

def _announcement_timestamp(raw: Any) -> datetime | None:
    published_day = _parse_day(raw)
    if published_day is None:
        return None
    # CNInfo disclosure search returns a date without a reliable timestamp.
    # Use end-of-day to avoid leaking same-day after-close filings into earlier bars.
    return datetime.combine(published_day, time(23, 59), tzinfo=SHANGHAI_TZ)

def _trade_day_from_timestamp(raw: datetime) -> date:
    if raw.tzinfo is None:
        return raw.date()
    return raw.astimezone(SHANGHAI_TZ).date()

def _parse_query_id(source_uri: str) -> str | None:
    parsed = parse.urlparse(source_uri)
    values = parse.parse_qs(parsed.query)
    for key in ("announcementId", "id", "noticeId"):
        if key in values and values[key]:
            return values[key][0]
    path_parts = [part for part in parsed.path.split("/") if part]
    return path_parts[-1] if path_parts else None

def _provider_credential(session: Session, provider_name: str) -> ProviderCredential | None:
    return session.scalar(
        select(ProviderCredential).where(
            ProviderCredential.provider_name == provider_name,
            ProviderCredential.enabled.is_(True),
        )
    )

def _post_tushare(
    *,
    base_url: str,
    token: str,
    api_name: str,
    params: dict[str, Any],
    fields: str,
) -> dict[str, Any] | None:
    payload = {
        "api_name": api_name,
        "token": token,
        "params": params,
        "fields": fields,
    }
    req = request.Request(
        url=base_url.rstrip("/"),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=8) as response:
            body = response.read()
    except (error.URLError, TimeoutError, OSError, ValueError):
        return None

    try:
        parsed = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None

def _tushare_rows(
    session: Session,
    *,
    api_name: str,
    params: dict[str, Any],
    fields: str,
) -> list[dict[str, Any]]:
    credential = _provider_credential(session, "tushare")
    if credential is None or not credential.access_token:
        return []
    response = _post_tushare(
        base_url=(credential.base_url or DEFAULT_TUSHARE_BASE_URL).strip(),
        token=credential.access_token.strip(),
        api_name=api_name,
        params=params,
        fields=fields,
    )
    if not response or response.get("code") not in {0, None}:
        return []
    data = response.get("data")
    if not isinstance(data, dict):
        return []
    field_names = data.get("fields")
    items = data.get("items")
    if not isinstance(field_names, list) or not isinstance(items, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, list) and len(item) == len(field_names):
            rows.append(dict(zip(field_names, item, strict=False)))
    return rows

def _akshare_module() -> Any:
    import akshare as akshare  # type: ignore[import-not-found]

    return akshare

def _fetch_daily_bars_tushare(session: Session, symbol: str) -> DailyMarketFetch | None:
    end_day = datetime.now(SHANGHAI_TZ).date()
    start_day = end_day - timedelta(days=DAILY_LOOKBACK_DAYS)
    market_rows = _tushare_rows(
        session,
        api_name="daily",
        params={
            "ts_code": symbol,
            "start_date": start_day.strftime("%Y%m%d"),
            "end_date": end_day.strftime("%Y%m%d"),
        },
        fields="ts_code,trade_date,open,high,low,close,vol,amount",
    )
    if not market_rows:
        return None
    turnover_rows = _tushare_rows(
        session,
        api_name="daily_basic",
        params={
            "ts_code": symbol,
            "start_date": start_day.strftime("%Y%m%d"),
            "end_date": end_day.strftime("%Y%m%d"),
        },
        fields="ts_code,trade_date,turnover_rate,total_mv,circ_mv,pe_ttm,pb",
    )
    turnover_by_day: dict[str, float] = {}
    basic_mv_by_day: dict[str, dict[str, float | None]] = {}
    for row in turnover_rows:
        day = str(row.get("trade_date"))
        if day is None:
            continue
        turnover_by_day[day] = (_to_float(row.get("turnover_rate")) or 0.0) / 100.0
        basic_mv_by_day[day] = {
            "total_mv": _to_float(row.get("total_mv")),
            "circ_mv": _to_float(row.get("circ_mv")),
            "pe_ttm": _to_float(row.get("pe_ttm")),
            "pb": _to_float(row.get("pb")),
        }
    ticker, _ = _normalize_symbol_parts(symbol)
    bars: list[dict[str, Any]] = []
    for row in market_rows:
        trade_day = _parse_day(row.get("trade_date"))
        if trade_day is None:
            continue
        open_price = _to_float(row.get("open"))
        high_price = _to_float(row.get("high"))
        low_price = _to_float(row.get("low"))
        close_price = _to_float(row.get("close"))
        volume = _to_float(row.get("vol"))
        amount = _to_float(row.get("amount"))
        if None in {open_price, high_price, low_price, close_price, volume, amount}:
            continue
        record = {
            "bar_key": f"bar-{ticker.lower()}-1d-{trade_day:%Y%m%d}",
            "timeframe": "1d",
            "observed_at": _close_timestamp(trade_day),
            "open_price": float(open_price),
            "high_price": float(high_price),
            "low_price": float(low_price),
            "close_price": float(close_price),
            "volume": float(volume),
            "amount": float(amount),
            "turnover_rate": turnover_by_day.get(trade_day.strftime("%Y%m%d")),
            "adj_factor": None,
            "total_mv": basic_mv_by_day.get(trade_day.strftime("%Y%m%d"), {}).get("total_mv"),
            "circ_mv": basic_mv_by_day.get(trade_day.strftime("%Y%m%d"), {}).get("circ_mv"),
            "pe_ttm": basic_mv_by_day.get(trade_day.strftime("%Y%m%d"), {}).get("pe_ttm"),
            "pb": basic_mv_by_day.get(trade_day.strftime("%Y%m%d"), {}).get("pb"),
            "raw_payload": {
                **_json_safe(row),
                "provider_name": "tushare",
                "dataset": "daily",
            },
        }
        bars.append(
            with_lineage(
                record,
                payload_key="raw_payload",
                source_uri=f"tushare://daily/{symbol}?trade_date={trade_day:%Y%m%d}",
                license_tag="tushare-pro",
                redistribution_scope="limited-display",
            )
        )
    bars.sort(key=lambda item: item["observed_at"])
    return DailyMarketFetch(provider_name="tushare_daily", bars=bars)

def _fetch_daily_bars_akshare(symbol: str) -> DailyMarketFetch | None:
    akshare = _akshare_module()
    end_day = datetime.now(SHANGHAI_TZ).date()
    start_day = end_day - timedelta(days=DAILY_LOOKBACK_DAYS)
    frame = akshare.stock_zh_a_daily(
        symbol=_akshare_prefixed_symbol(symbol),
        start_date=start_day.strftime("%Y%m%d"),
        end_date=end_day.strftime("%Y%m%d"),
        adjust="",
    )
    if frame is None or getattr(frame, "empty", False):
        return None
    ticker, _ = _normalize_symbol_parts(symbol)
    bars: list[dict[str, Any]] = []
    for row in frame.to_dict(orient="records"):
        trade_day = _parse_day(row.get("date"))
        if trade_day is None:
            continue
        open_price = _to_float(row.get("open"))
        high_price = _to_float(row.get("high"))
        low_price = _to_float(row.get("low"))
        close_price = _to_float(row.get("close"))
        volume = _to_float(row.get("volume"))
        amount = _to_float(row.get("amount"))
        if None in {open_price, high_price, low_price, close_price, volume, amount}:
            continue
        record = {
            "bar_key": f"bar-{ticker.lower()}-1d-{trade_day:%Y%m%d}",
            "timeframe": "1d",
            "observed_at": _close_timestamp(trade_day),
            "open_price": float(open_price),
            "high_price": float(high_price),
            "low_price": float(low_price),
            "close_price": float(close_price),
            "volume": float(volume),
            "amount": float(amount),
            "turnover_rate": _to_float(row.get("turnover")),
            "adj_factor": None,
            "total_mv": None,
            "circ_mv": None,
            "pe_ttm": None,
            "pb": None,
            "raw_payload": {
                **_json_safe(row),
                "provider_name": "akshare",
                "dataset": "stock_zh_a_daily",
            },
        }
        bars.append(
            with_lineage(
                record,
                payload_key="raw_payload",
                source_uri=f"akshare://stock_zh_a_daily/{symbol}?trade_date={trade_day:%Y%m%d}",
                license_tag="akshare-public-web",
                redistribution_scope="limited-display",
            )
        )
    bars.sort(key=lambda item: item["observed_at"])
    return DailyMarketFetch(provider_name="akshare_sina_daily", bars=bars)

def _fetch_daily_market_data(session: Session, symbol: str) -> DailyMarketFetch:
    for fetcher in (_fetch_daily_bars_tushare, lambda active_session, active_symbol: _fetch_daily_bars_akshare(active_symbol)):
        try:
            result = fetcher(session, symbol)
        except Exception:
            result = None
        if result is not None and len(result.bars) >= 21:
            return result
    raise RealDataRefreshError(f"{symbol} 缺少足够的 21 个交易日日线行情，无法生成真实建议。")

def _announcement_impact(title: str) -> str:
    """Return 'pending_llm' for all announcements — keyword matching is disabled.

    News sentiment must come from LLM analysis only. If LLM analysis fails,
    the item stays as 'pending_llm' and is excluded from scoring.
    """
    return "pending_llm"

def _announcement_scope(title: str) -> str:
    # Roadshow/meeting check first: "说明会/路演/调研" about reports is still a roadshow, not earnings
    if any(keyword in title for keyword in ("说明会", "路演", "调研")):
        return "roadshow"
    if any(keyword in title for keyword in ("业绩", "年报", "年度报告", "季报", "季度", "中报", "快报")):
        return "earnings"
    if any(keyword in title for keyword in ("增持", "减持", "回购", "分红")):
        return "capital_action"
    return "announcement"

def _fetch_official_announcements(
    symbol: str,
    *,
    sector_code: str | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    akshare = _akshare_module()
    ticker, _ = _normalize_symbol_parts(symbol)
    end_day = datetime.now(SHANGHAI_TZ).date()
    start_day = end_day - timedelta(days=ANNOUNCEMENT_LOOKBACK_DAYS)
    frame = akshare.stock_zh_a_disclosure_report_cninfo(
        symbol=ticker,
        market="沪深京",
        start_date=start_day.strftime("%Y%m%d"),
        end_date=end_day.strftime("%Y%m%d"),
    )
    if frame is None or getattr(frame, "empty", False):
        return [], []
    rows = frame.to_dict(orient="records")
    rows.sort(key=lambda item: str(item.get("公告时间") or ""), reverse=True)
    news_items: list[dict[str, Any]] = []
    news_links: list[dict[str, Any]] = []
    for index, row in enumerate(rows[:ANNOUNCEMENT_LIMIT]):
        source_uri = str(row.get("公告链接") or "").strip()
        if not source_uri:
            continue
        headline = _normalize_text(row.get("公告标题"))
        published_at = _announcement_timestamp(row.get("公告时间"))
        if headline is None or published_at is None:
            continue
        external_id = _parse_query_id(source_uri) or f"{ticker}-{published_at:%Y%m%d}-{index}"
        news_key = f"cninfo-{ticker}-{external_id}"
        content_excerpt = fetch_announcement_body(source_uri)
        item = {
            "news_key": news_key,
            "provider_name": "cninfo",
            "external_id": external_id,
            "headline": headline,
            "summary": headline,
            "content_excerpt": content_excerpt,
            "published_at": published_at,
            "event_scope": _announcement_scope(headline),
            "dedupe_key": news_key,
            "raw_payload": {
                **_json_safe(row),
                "provider_name": "cninfo",
            },
        }
        news_items.append(
            with_lineage(
                item,
                payload_key="raw_payload",
                source_uri=source_uri,
                license_tag="cninfo-public-disclosure",
                redistribution_scope="limited-display",
            )
        )

        impact_direction = _announcement_impact(headline)
        stock_link = {
            "news_key": news_key,
            "entity_type": "stock",
            "stock_symbol": symbol,
            "sector_code": None,
            "market_tag": "A-share",
            "relevance_score": 0.92,
            "impact_direction": impact_direction,
            "effective_at": published_at,
            "decay_half_life_hours": 96.0,
            "mapping_payload": {
                "mapping_rule": "cninfo_stock_announcement",
                "matched_symbol": symbol,
            },
        }
        news_links.append(
            build_mapped_news_link(
                stock_link,
                source_uri=f"pipeline://news-link/stock/{news_key}",
            )
        )
        if sector_code is not None:
            sector_link = {
                "news_key": news_key,
                "entity_type": "sector",
                "stock_symbol": None,
                "sector_code": sector_code,
                "market_tag": "A-share",
                "relevance_score": 0.44,
                "impact_direction": impact_direction,
                "effective_at": published_at,
                "decay_half_life_hours": 120.0,
                "mapping_payload": {
                    "mapping_rule": "industry_sector_projection",
                    "matched_sector_code": sector_code,
                },
            }
            news_links.append(
                build_mapped_news_link(
                    sector_link,
                    source_uri=f"pipeline://news-link/sector/{news_key}",
                )
            )
    return news_items, news_links

def build_mapped_news_link(record: dict[str, Any], *, source_uri: str) -> dict[str, Any]:
    return {
        **record,
        **build_lineage(
            record,
            source_uri=source_uri,
            license_tag="internal-derived",
            usage_scope="internal_research",
            redistribution_scope="none",
        ),
    }

def _first_non_empty_row(frame: Any) -> dict[str, Any] | None:
    if frame is None or getattr(frame, "empty", False):
        return None
    records = frame.to_dict(orient="records")
    return records[0] if records else None

def _fetch_financial_snapshot_tushare(session: Session, symbol: str) -> dict[str, Any] | None:
    rows = _tushare_rows(
        session,
        api_name="fina_indicator",
        params={"ts_code": symbol},
        fields="ts_code,ann_date,end_date,eps,dt_eps,roe,roe_dt,or_yoy,netprofit_yoy,ocfps",
    )
    if not rows:
        return None
    rows.sort(key=lambda r: str(r.get("end_date") or ""), reverse=True)
    seen: set[str] = set()
    deduped = []
    for row in rows:
        period = str(row.get("end_date") or "")
        if period and period not in seen:
            seen.add(period)
            deduped.append(row)
    latest = deduped[0]
    history = []
    for row in deduped[:8]:
        history.append({
            "report_period": _normalize_text(row.get("end_date")),
            "eps": _to_float(row.get("eps")),
            "roe": _to_float(row.get("roe")),
            "revenue_yoy_pct": _to_float(row.get("or_yoy")),
            "netprofit_yoy_pct": _to_float(row.get("netprofit_yoy")),
            "operating_cashflow_per_share": _to_float(row.get("ocfps")),
        })
    return {
        "provider_name": "tushare_fina_indicator",
        "report_period": _normalize_text(latest.get("end_date")),
        "ann_date": _normalize_text(latest.get("ann_date")),
        "eps": _to_float(latest.get("eps")),
        "diluted_eps": _to_float(latest.get("dt_eps")),
        "roe": _to_float(latest.get("roe")),
        "roe_diluted": _to_float(latest.get("roe_dt")),
        "revenue_yoy_pct": _to_float(latest.get("or_yoy")),
        "netprofit_yoy_pct": _to_float(latest.get("netprofit_yoy")),
        "operating_cashflow_per_share": _to_float(latest.get("ocfps")),
        "quarterly_history": history,
    }

def _fetch_financial_snapshot_akshare(symbol: str) -> dict[str, Any] | None:
    akshare = _akshare_module()
    prefixed = _akshare_prefixed_symbol(symbol).upper()
    profit_row = _first_non_empty_row(akshare.stock_profit_sheet_by_report_em(symbol=prefixed))
    cashflow_row = _first_non_empty_row(akshare.stock_cash_flow_sheet_by_report_em(symbol=prefixed))
    if profit_row is None and cashflow_row is None:
        return None
    return {
        "provider_name": "akshare_em_financials",
        "report_period": _normalize_text(profit_row.get("REPORT_DATE_NAME") if profit_row else None),
        "notice_date": _normalize_text(profit_row.get("NOTICE_DATE") if profit_row else None),
        "revenue": _to_float(profit_row.get("TOTAL_OPERATE_INCOME") if profit_row else None),
        "revenue_yoy_pct": _to_float(profit_row.get("TOTAL_OPERATE_INCOME_YOY") if profit_row else None),
        "parent_netprofit": _to_float(profit_row.get("PARENT_NETPROFIT") if profit_row else None),
        "parent_netprofit_yoy_pct": _to_float(profit_row.get("PARENT_NETPROFIT_YOY") if profit_row else None),
        "basic_eps": _to_float(profit_row.get("BASIC_EPS") if profit_row else None),
        "operating_cashflow": _to_float(cashflow_row.get("NETCASH_OPERATE") if cashflow_row else None),
        "ending_cash": _to_float(cashflow_row.get("END_CCE") if cashflow_row else None),
    }

def _fetch_market_cap_akshare(symbol: str) -> dict[str, float | None] | None:
    """Fetch total market cap and circulating market cap from akshare."""
    import os
    try:
        # Bypass proxy for akshare calls (same issue as LLM API)
        saved = {k: os.environ.pop(k, None) for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")}
        akshare = _akshare_module()
        ticker, _ = _normalize_symbol_parts(symbol)
        df = akshare.stock_individual_info_em(symbol=ticker)
        record = {}
        for _, row in df.iterrows():
            key = str(row.iloc[0])
            val = row.iloc[1]
            if key == "总市值":
                record["total_mv"] = _to_float(val)
            elif key == "流通市值":
                record["circ_mv"] = _to_float(val)
        return record if record else None
    except Exception:
        return None
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


def _fetch_financial_snapshot(session: Session, symbol: str) -> dict[str, Any] | None:
    for fetcher in (
        lambda: _fetch_financial_snapshot_tushare(session, symbol),
        lambda: _fetch_financial_snapshot_akshare(symbol),
    ):
        try:
            snapshot = fetcher()
        except Exception:
            snapshot = None
        if snapshot:
            return snapshot
    return None

def _fetch_research_metadata(symbol: str) -> list[dict[str, Any]]:
    akshare = _akshare_module()
    ticker, _ = _normalize_symbol_parts(symbol)
    with _requests_default_timeout(DEFAULT_AKSHARE_TIMEOUT_SECONDS):
        frame = akshare.stock_research_report_em(symbol=ticker)
    if frame is None or getattr(frame, "empty", False):
        return []
    metadata: list[dict[str, Any]] = []
    for row in frame.head(RESEARCH_METADATA_LIMIT).to_dict(orient="records"):
        metadata.append(
            {
                "title": _normalize_text(row.get("报告名称")),
                "rating": _normalize_text(row.get("东财评级")),
                "broker": _normalize_text(row.get("机构")),
                "published_at": _normalize_text(row.get("日期")),
                "pdf_url": _normalize_text(row.get("报告PDF链接")),
                "industry": _normalize_text(row.get("行业")),
            }
        )
    return [item for item in metadata if item["title"]]

@contextmanager
def _requests_default_timeout(timeout_seconds: int):
    try:
        import requests
    except Exception:
        yield
        return

    original_request = requests.sessions.Session.request

    def _request_with_timeout(self, method, url, **kwargs):
        kwargs.setdefault("timeout", timeout_seconds)
        return original_request(self, method, url, **kwargs)

    requests.sessions.Session.request = _request_with_timeout
    try:
        yield
    finally:
        requests.sessions.Session.request = original_request

def _sector_payload(symbol: str, profile: StockProfileResolution) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str | None]:
    if not profile.industry:
        return [], [], None
    sector_code = f"industry:{profile.template_key or profile.industry}"
    sector = {
        "sector_code": sector_code,
        "name": profile.industry,
        "level": "industry",
        "definition_payload": {
            "source": profile.source,
            "template_key": profile.template_key,
            "taxonomy": "resolved_industry",
        },
    }
    sector_record = {
        **sector,
        **build_lineage(
            sector,
            source_uri=f"pipeline://sector/{sector_code}",
            license_tag="internal-derived",
            usage_scope="internal_research",
            redistribution_scope="none",
        ),
    }
    effective_from_day = profile.listed_date or date(2000, 1, 1)
    membership = {
        "membership_key": f"membership-{symbol}-{sector_code}",
        "sector_code": sector_code,
        "effective_from": datetime.combine(effective_from_day, time(0, 0), tzinfo=SHANGHAI_TZ),
        "effective_to": None,
        "is_primary": True,
        "membership_payload": {
            "industry_name": profile.industry,
            "source": profile.source,
        },
    }
    membership_record = {
        **membership,
        **build_lineage(
            membership,
            source_uri=f"pipeline://sector-membership/{symbol}/{sector_code}",
            license_tag="internal-derived",
            usage_scope="internal_research",
            redistribution_scope="none",
        ),
    }
    return [sector_record], [membership_record], sector_code

def build_real_evidence_bundle(
    session: Session,
    *,
    symbol: str,
    stock_name: str | None = None,
) -> EvidenceBundle:
    normalized_symbol = normalize_symbol(symbol)
    profile = resolve_stock_profile(session, symbol=normalized_symbol, preferred_name=stock_name)
    daily_market = _fetch_daily_market_data(session, normalized_symbol)
    sectors, sector_memberships, sector_code = _sector_payload(normalized_symbol, profile)
    news_items: list[dict[str, Any]]
    news_links: list[dict[str, Any]]
    try:
        news_items, news_links = _fetch_official_announcements(normalized_symbol, sector_code=sector_code)
    except Exception:
        news_items, news_links = [], []
    try:
        financial_snapshot = _fetch_financial_snapshot(session, normalized_symbol)
    except Exception:
        financial_snapshot = None
    try:
        research_metadata = _fetch_research_metadata(normalized_symbol)
    except Exception:
        research_metadata = []

    try:
        market_cap = _fetch_market_cap_akshare(normalized_symbol)
    except Exception:
        market_cap = None
    if market_cap is None:
        from ashare_evidence.signal_engine_parts.market_cap_seed import SEED_MARKET_CAP
        if normalized_symbol in SEED_MARKET_CAP:
            market_cap = {"total_mv": SEED_MARKET_CAP[normalized_symbol], "source": "seed"}
    enrich_with_llm_analysis(news_items, news_links, financial_snapshot=financial_snapshot)

    financial_trends = compute_financial_trends(financial_snapshot)
    financial_llm = None
    if financial_trends.get("available"):
        try:
            from ashare_evidence.news_analysis import analyze_financials
            financial_llm = analyze_financials(financial_snapshot, financial_trends)
        except Exception:
            financial_llm = None

    generated_at = datetime.now(SHANGHAI_TZ)
    resolved_board_rule = board_rule(
        normalized_symbol,
        stock_profile={
            "name": profile.name or stock_name or normalized_symbol,
            "listed_date": profile.listed_date,
        },
        as_of=generated_at.date(),
    )
    signal_artifacts = build_signal_artifacts(
        symbol=normalized_symbol,
        stock_name=profile.name or stock_name or normalized_symbol,
        market_bars=daily_market.bars,
        news_items=news_items,
        news_links=news_links,
        sector_memberships=sector_memberships,
        financial_snapshot=financial_snapshot,
        financial_trends=financial_trends,
        financial_llm=financial_llm,
        market_cap_data=market_cap,
        generated_at=generated_at,
    )

    ticker, market = _normalize_symbol_parts(normalized_symbol)
    stock_payload = {
        "symbol": normalized_symbol,
        "ticker": ticker,
        "exchange": _exchange_name(market),
        "name": profile.name or stock_name or normalized_symbol,
        "provider_symbol": normalized_symbol,
        "listed_date": profile.listed_date,
        "delisted_date": None,
        "status": "active",
        "profile_payload": {
            "industry": profile.industry,
            "template_key": profile.template_key,
            "profile_source": profile.source,
            "board": resolved_board_rule.get("board"),
            "board_name": resolved_board_rule.get("label"),
            "board_rule_source": resolved_board_rule.get("rule_source"),
            "analysis_pipeline": {
                "daily_market_provider": daily_market.provider_name,
                "news_provider": "cninfo_official" if news_items else None,
                "financial_provider": None if financial_snapshot is None else financial_snapshot["provider_name"],
                "research_provider": "eastmoney_research_metadata" if research_metadata else None,
            },
            "financial_snapshot": financial_snapshot,
            "financial_trends": financial_trends,
            "financial_llm_analysis": financial_llm,
            "market_cap": market_cap,
            "research_report_metadata": research_metadata,
        },
    }
    stock = {
        **stock_payload,
        **build_lineage(
            stock_payload,
            source_uri=f"pipeline://real-analysis/stock/{normalized_symbol}",
            license_tag="internal-derived",
            usage_scope="internal_research",
            redistribution_scope="none",
        ),
    }

    return EvidenceBundle(
        provider_name="real_data_pipeline",
        symbol=normalized_symbol,
        stock=stock,
        sectors=sectors,
        sector_memberships=sector_memberships,
        market_bars=daily_market.bars,
        news_items=news_items,
        news_links=news_links,
        feature_snapshots=signal_artifacts.feature_snapshots,
        model_registry=signal_artifacts.model_registry,
        model_version=signal_artifacts.model_version,
        prompt_version=signal_artifacts.prompt_version,
        model_run=signal_artifacts.model_run,
        model_results=signal_artifacts.model_results,
        recommendation=signal_artifacts.recommendation,
        recommendation_evidence=signal_artifacts.recommendation_evidence,
        paper_portfolios=[],
        paper_orders=[],
        paper_fills=[],
    )


def repair_stock_profile_snapshot(
    session: Session,
    *,
    symbol: str,
    stock_name: str | None = None,
) -> Stock | None:
    normalized_symbol = normalize_symbol(symbol)
    stock = session.scalar(select(Stock).where(Stock.symbol == normalized_symbol))
    if stock is None:
        return None

    profile = resolve_stock_profile(session, symbol=normalized_symbol, preferred_name=stock_name or stock.name)
    generated_at = datetime.now(SHANGHAI_TZ)
    resolved_board_rule = board_rule(
        normalized_symbol,
        stock_profile={
            "name": profile.name or stock.name or stock_name or normalized_symbol,
            "listed_date": profile.listed_date or stock.listed_date,
        },
        as_of=generated_at.date(),
    )
    try:
        financial_snapshot = _fetch_financial_snapshot(session, normalized_symbol)
    except Exception:
        financial_snapshot = None
    try:
        research_metadata = _fetch_research_metadata(normalized_symbol)
    except Exception:
        research_metadata = []

    profile_payload = dict(stock.profile_payload) if isinstance(stock.profile_payload, dict) else {}
    analysis_pipeline_payload = profile_payload.get("analysis_pipeline")
    if not isinstance(analysis_pipeline_payload, dict):
        analysis_pipeline_payload = {}
    if financial_snapshot is not None:
        analysis_pipeline_payload["financial_provider"] = financial_snapshot.get("provider_name")
    if research_metadata:
        analysis_pipeline_payload["research_provider"] = "eastmoney_research_metadata"

    profile_payload.update(
        {
            "industry": profile.industry or profile_payload.get("industry"),
            "template_key": profile.template_key or profile_payload.get("template_key"),
            "profile_source": profile.source,
            "board": resolved_board_rule.get("board"),
            "board_name": resolved_board_rule.get("label"),
            "board_rule_source": resolved_board_rule.get("rule_source"),
            "analysis_pipeline": analysis_pipeline_payload,
        }
    )
    if financial_snapshot is not None:
        profile_payload["financial_snapshot"] = financial_snapshot
    if research_metadata:
        profile_payload["research_report_metadata"] = research_metadata

    stock.name = profile.name or stock.name
    stock.provider_symbol = normalized_symbol
    stock.listed_date = profile.listed_date or stock.listed_date
    stock.profile_payload = profile_payload
    lineage = build_lineage(
        {
            "symbol": normalized_symbol,
            "name": stock.name,
            "listed_date": stock.listed_date,
            "profile_payload": profile_payload,
        },
        source_uri=f"pipeline://stock-profile-repair/{normalized_symbol}",
        license_tag="internal-derived",
        usage_scope="internal_research",
        redistribution_scope="none",
    )
    stock.source_uri = lineage["source_uri"]
    stock.license_tag = lineage["license_tag"]
    stock.usage_scope = lineage["usage_scope"]
    stock.redistribution_scope = lineage["redistribution_scope"]
    stock.lineage_hash = lineage["lineage_hash"]
    session.flush()
    return stock

def _recommendation_trade_days(session: Session, symbol: str) -> list[date]:
    rows = session.execute(
        select(Recommendation.as_of_data_time)
        .join(Stock, Recommendation.stock_id == Stock.id)
        .where(Stock.symbol == symbol)
        .order_by(Recommendation.as_of_data_time.asc())
    ).scalars()
    trade_days = {_trade_day_from_timestamp(as_of_data_time) for as_of_data_time in rows}
    return sorted(trade_days)

def _backfill_candidate_trade_days(
    session: Session,
    *,
    symbol: str,
    market_bars: list[dict[str, Any]],
) -> list[date]:
    existing_trade_days = _recommendation_trade_days(session, symbol)
    if len(existing_trade_days) < MIN_EXISTING_RECOMMENDATION_DAYS_FOR_BACKFILL:
        return []

    market_trade_days = sorted({_trade_day_from_timestamp(bar["observed_at"]) for bar in market_bars})
    market_trade_day_set = set(market_trade_days)
    existing_trade_days = [trade_day for trade_day in existing_trade_days if trade_day in market_trade_day_set]
    if len(existing_trade_days) < MIN_EXISTING_RECOMMENDATION_DAYS_FOR_BACKFILL:
        return []

    earliest_existing_trade_day = existing_trade_days[0]
    latest_market_trade_day = market_trade_days[-1]
    existing_trade_day_set = set(existing_trade_days)
    return [
        trade_day
        for trade_day in market_trade_days
        if earliest_existing_trade_day <= trade_day < latest_market_trade_day and trade_day not in existing_trade_day_set
    ]

def _historical_bundle(base_bundle: EvidenceBundle, *, as_of_day: date) -> EvidenceBundle:
    cutoff = _close_timestamp(as_of_day)
    market_bars = [
        bar
        for bar in base_bundle.market_bars
        if bar["observed_at"] <= cutoff
    ]
    news_items = [
        item
        for item in base_bundle.news_items
        if item["published_at"] <= cutoff
    ]
    retained_news_keys = {item["news_key"] for item in news_items}
    news_links = [
        link
        for link in base_bundle.news_links
        if link["effective_at"] <= cutoff and link["news_key"] in retained_news_keys
    ]
    signal_artifacts = build_signal_artifacts(
        symbol=base_bundle.symbol,
        stock_name=str(base_bundle.stock["name"]),
        market_bars=market_bars,
        news_items=news_items,
        news_links=news_links,
        sector_memberships=base_bundle.sector_memberships,
        generated_at=cutoff + timedelta(minutes=25),
    )
    return replace(
        base_bundle,
        market_bars=market_bars,
        news_items=news_items,
        news_links=news_links,
        feature_snapshots=signal_artifacts.feature_snapshots,
        model_registry=signal_artifacts.model_registry,
        model_version=signal_artifacts.model_version,
        prompt_version=signal_artifacts.prompt_version,
        model_run=signal_artifacts.model_run,
        model_results=signal_artifacts.model_results,
        recommendation=signal_artifacts.recommendation,
        recommendation_evidence=signal_artifacts.recommendation_evidence,
    )

def _backfill_missing_recommendation_history(
    session: Session,
    *,
    bundle: EvidenceBundle,
) -> None:
    for trade_day in _backfill_candidate_trade_days(
        session,
        symbol=bundle.symbol,
        market_bars=bundle.market_bars,
    ):
        ingest_bundle(session, _historical_bundle(bundle, as_of_day=trade_day))

def refresh_real_analysis(
    session: Session,
    *,
    symbol: str,
    stock_name: str | None = None,
) -> Recommendation:
    from ashare_evidence.watchlist import active_watchlist_symbols

    bundle = build_real_evidence_bundle(session, symbol=symbol, stock_name=stock_name)
    _backfill_missing_recommendation_history(session, bundle=bundle)
    recommendation = ingest_bundle(session, bundle)
    active_symbols = set(active_watchlist_symbols(session))
    active_symbols.add(recommendation.stock.symbol)
    rebuild_phase2_research_state(
        session,
        symbols={recommendation.stock.symbol},
        active_symbols=active_symbols,
    )
    return recommendation
