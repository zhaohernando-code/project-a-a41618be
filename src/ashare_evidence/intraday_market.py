from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, time, timedelta, timezone
import json
from typing import Any
from urllib import error, request
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from ashare_evidence.db import utcnow
from ashare_evidence.http_client import urlopen
from ashare_evidence.lineage import build_lineage
from ashare_evidence.models import AppSetting, MarketBar, ProviderCredential, Stock
from ashare_evidence.stock_master import akshare_runtime_ready

INTRADAY_MARKET_SETTING_KEY = "ops_intraday_market_status"
INTRADAY_MARKET_TIMEFRAME = "5min"
INTRADAY_MARKET_INTERVAL_SECONDS = 300
INTRADAY_DECISION_INTERVAL_SECONDS = 1800
INTRADAY_STALE_THRESHOLD_SECONDS = 300
DEFAULT_TUSHARE_BASE_URL = "http://api.tushare.pro"
MARKET_TIMEZONE = ZoneInfo("Asia/Shanghai")


def _normalize_symbols(symbols: Iterable[str] | None) -> list[str]:
    if not symbols:
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_symbol in symbols:
        symbol = str(raw_symbol or "").strip().upper()
        if not symbol or symbol in seen:
            continue
        normalized.append(symbol)
        seen.add(symbol)
    return normalized


def _get_setting(session: Session, key: str) -> AppSetting | None:
    return session.scalar(select(AppSetting).where(AppSetting.setting_key == key))


def _upsert_setting(session: Session, key: str, value: dict[str, Any], *, description: str) -> None:
    record = _get_setting(session, key)
    if record is None:
        record = AppSetting(setting_key=key, description=description, setting_value=value)
        session.add(record)
    else:
        record.description = description
        record.setting_value = value
    session.flush()


def _serialize_datetime(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat() if value is not None else None


def _latest_intraday_timestamp(session: Session, symbols: list[str]) -> datetime | None:
    if not symbols:
        return None
    bars = session.scalars(
        select(MarketBar)
        .join(Stock)
        .where(Stock.symbol.in_(symbols), MarketBar.timeframe == INTRADAY_MARKET_TIMEFRAME)
        .order_by(MarketBar.observed_at.desc())
        .limit(1)
    ).all()
    return bars[0].observed_at if bars else None


def _latest_intraday_timestamp_for_symbol(session: Session, symbol: str) -> datetime | None:
    bar = session.scalar(
        select(MarketBar)
        .join(Stock)
        .where(Stock.symbol == symbol, MarketBar.timeframe == INTRADAY_MARKET_TIMEFRAME)
        .order_by(MarketBar.observed_at.desc())
        .limit(1)
    )
    return None if bar is None else bar.observed_at


def _market_open_for_day(current_time: datetime) -> datetime:
    local_now = current_time.astimezone(MARKET_TIMEZONE)
    market_open = datetime.combine(local_now.date(), time(9, 30), tzinfo=MARKET_TIMEZONE)
    return market_open.astimezone(timezone.utc)


def _intraday_cache_is_fresh(current_time: datetime, latest_market_data_at: datetime | None) -> bool:
    if latest_market_data_at is None:
        return False
    aligned = latest_market_data_at
    if aligned.tzinfo is None:
        aligned = aligned.replace(tzinfo=timezone.utc)
    return (current_time - aligned).total_seconds() < INTRADAY_MARKET_INTERVAL_SECONDS


def get_intraday_market_status(
    session: Session,
    *,
    symbols: Iterable[str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    normalized_symbols = _normalize_symbols(symbols)
    latest_market_data_at = _latest_intraday_timestamp(session, normalized_symbols) if normalized_symbols else None
    current_time = now or utcnow()
    persisted = _get_setting(session, INTRADAY_MARKET_SETTING_KEY)
    payload = dict(persisted.setting_value) if persisted is not None else {}
    data_latency_seconds = None
    if latest_market_data_at is not None:
        if latest_market_data_at.tzinfo is None:
            latest_market_data_at = latest_market_data_at.replace(tzinfo=current_time.tzinfo)
        data_latency_seconds = max(int((current_time - latest_market_data_at).total_seconds()), 0)
    provider_label = payload.get("provider_label")
    provider_name = payload.get("provider_name")
    status = payload.get("status", "idle")
    source_kind = payload.get("source_kind", "none")
    if latest_market_data_at is not None and provider_label is None:
        provider_label = "已落库 5 分钟行情"
        status = "ready"
        source_kind = "persisted_5min"
    return {
        "status": status,
        "provider_name": provider_name,
        "provider_label": provider_label,
        "source_kind": source_kind,
        "timeframe": INTRADAY_MARKET_TIMEFRAME,
        "decision_interval_seconds": int(payload.get("decision_interval_seconds") or INTRADAY_DECISION_INTERVAL_SECONDS),
        "market_data_interval_seconds": int(payload.get("market_data_interval_seconds") or INTRADAY_MARKET_INTERVAL_SECONDS),
        "symbol_count": len(normalized_symbols),
        "last_success_at": payload.get("last_success_at"),
        "latest_market_data_at": _serialize_datetime(latest_market_data_at),
        "data_latency_seconds": data_latency_seconds,
        "fallback_used": bool(payload.get("fallback_used", False)),
        "stale": bool(data_latency_seconds is None or data_latency_seconds > INTRADAY_STALE_THRESHOLD_SECONDS),
        "message": payload.get("message"),
    }


def _tushare_credential(session: Session) -> ProviderCredential | None:
    return session.scalar(
        select(ProviderCredential).where(
            ProviderCredential.provider_name == "tushare",
            ProviderCredential.enabled.is_(True),
        )
    )


def _post_tushare(
    *,
    base_url: str,
    token: str,
    api_name: str,
    params: dict[str, Any],
    fields: str | None = None,
) -> dict[str, Any] | None:
    payload = {
        "api_name": api_name,
        "token": token,
        "params": params,
        "fields": fields or "",
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


def _tushare_rows(session: Session, symbol: str) -> list[dict[str, Any]]:
    credential = _tushare_credential(session)
    if credential is None or not credential.access_token:
        return []
    response = _post_tushare(
        base_url=credential.base_url or DEFAULT_TUSHARE_BASE_URL,
        token=credential.access_token,
        api_name="rt_min_daily",
        params={"ts_code": symbol, "freq": "5MIN"},
    )
    if not response or response.get("code") not in {0, None}:
        return []
    data = response.get("data")
    if not isinstance(data, dict):
        return []
    fields = data.get("fields")
    items = data.get("items")
    if not isinstance(fields, list) or not isinstance(items, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, list) and len(item) == len(fields):
            rows.append(dict(zip(fields, item, strict=False)))
    return rows


def _load_akshare_module() -> Any:
    import akshare as akshare  # type: ignore[import-not-found]

    return akshare


def _akshare_rows(symbol: str) -> list[dict[str, Any]]:
    if not akshare_runtime_ready():
        return []
    try:
        akshare = _load_akshare_module()
        frame = akshare.stock_zh_a_hist_min_em(symbol=symbol.split(".")[0], period="5", adjust="")
    except Exception:
        return []
    if frame is None or getattr(frame, "empty", False):
        return []
    rows: list[dict[str, Any]] = []
    for record in frame.to_dict(orient="records"):
        rows.append(record)
    return rows


def _parse_row_time(raw_value: Any) -> datetime | None:
    if raw_value is None:
        return None
    text = str(raw_value).strip()
    if not text:
        return None
    formats = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M")
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=MARKET_TIMEZONE).astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def _akshare_window(
    *,
    current_time: datetime,
    latest_cached_market_data_at: datetime | None,
) -> tuple[str, str] | None:
    end_time = current_time.astimezone(MARKET_TIMEZONE)
    if latest_cached_market_data_at is not None:
        start_time = latest_cached_market_data_at.astimezone(MARKET_TIMEZONE) - timedelta(
            seconds=INTRADAY_MARKET_INTERVAL_SECONDS
        )
    else:
        start_time = _market_open_for_day(current_time).astimezone(MARKET_TIMEZONE)
    if start_time >= end_time:
        return None
    return (
        start_time.strftime("%Y-%m-%d %H:%M:%S"),
        end_time.strftime("%Y-%m-%d %H:%M:%S"),
    )


def _akshare_rows_for_window(symbol: str, *, current_time: datetime, latest_cached_market_data_at: datetime | None) -> list[dict[str, Any]]:
    if not akshare_runtime_ready():
        return []
    try:
        akshare = _load_akshare_module()
        window = _akshare_window(current_time=current_time, latest_cached_market_data_at=latest_cached_market_data_at)
        kwargs: dict[str, Any] = {
            "symbol": symbol.split(".")[0],
            "period": "5",
            "adjust": "",
        }
        if window is not None:
            kwargs["start_date"], kwargs["end_date"] = window
        try:
            frame = akshare.stock_zh_a_hist_min_em(**kwargs)
        except TypeError:
            kwargs.pop("start_date", None)
            kwargs.pop("end_date", None)
            frame = akshare.stock_zh_a_hist_min_em(**kwargs)
    except Exception:
        return []
    if frame is None or getattr(frame, "empty", False):
        return []
    return list(frame.to_dict(orient="records"))


def _to_float(raw_value: Any) -> float | None:
    if raw_value is None:
        return None
    try:
        return float(str(raw_value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _canonical_rows(
    *,
    symbol: str,
    provider_name: str,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    canonical: list[dict[str, Any]] = []
    for row in rows:
        observed_at = _parse_row_time(row.get("time") or row.get("trade_time") or row.get("时间"))
        open_price = _to_float(row.get("open") or row.get("开盘"))
        close_price = _to_float(row.get("close") or row.get("收盘"))
        high_price = _to_float(row.get("high") or row.get("最高"))
        low_price = _to_float(row.get("low") or row.get("最低"))
        volume = _to_float(row.get("vol") or row.get("volume") or row.get("成交量"))
        amount = _to_float(row.get("amount") or row.get("成交额"))
        if observed_at is None or None in {open_price, close_price, high_price, low_price, volume, amount}:
            continue
        canonical.append(
            {
                "symbol": symbol,
                "timeframe": INTRADAY_MARKET_TIMEFRAME,
                "observed_at": observed_at,
                "open_price": float(open_price),
                "close_price": float(close_price),
                "high_price": float(high_price),
                "low_price": float(low_price),
                "volume": float(volume),
                "amount": float(amount),
                "provider_name": provider_name,
                "raw_payload": row,
            }
        )
    canonical.sort(key=lambda item: item["observed_at"])
    return canonical


def _filter_incremental_rows(
    rows: list[dict[str, Any]],
    *,
    latest_cached_market_data_at: datetime | None,
) -> list[dict[str, Any]]:
    if latest_cached_market_data_at is None:
        return rows
    if latest_cached_market_data_at.tzinfo is None:
        latest_cached_market_data_at = latest_cached_market_data_at.replace(tzinfo=timezone.utc)
    minimum_observed_at = latest_cached_market_data_at - timedelta(seconds=INTRADAY_MARKET_INTERVAL_SECONDS)
    return [row for row in rows if row["observed_at"] >= minimum_observed_at]


def _upsert_market_bar(session: Session, *, stock: Stock, bar: dict[str, Any], source_kind: str) -> None:
    observed_at = bar["observed_at"]
    record = session.scalar(
        select(MarketBar).where(
            MarketBar.stock_id == stock.id,
            MarketBar.timeframe == INTRADAY_MARKET_TIMEFRAME,
            MarketBar.observed_at == observed_at,
        )
    )
    payload = {
        "provider": bar["provider_name"],
        "source_kind": source_kind,
        "frequency": INTRADAY_MARKET_TIMEFRAME,
        "observed_at": observed_at.isoformat(),
        "symbol": stock.symbol,
    }
    lineage = build_lineage(
        payload,
        source_uri=(
            f"tushare://rt_min_daily/{stock.symbol}?freq=5MIN&time={observed_at.isoformat()}"
            if bar["provider_name"] == "tushare"
            else f"akshare://stock_zh_a_hist_min_em/{stock.symbol}?period=5&time={observed_at.isoformat()}"
        ),
        license_tag="tushare-pro" if bar["provider_name"] == "tushare" else "akshare-public-web",
        usage_scope="internal_research",
        redistribution_scope="limited-display",
    )
    values = {
        "bar_key": f"bar-{stock.ticker.lower()}-{INTRADAY_MARKET_TIMEFRAME}-{observed_at:%Y%m%d%H%M}",
        "stock_id": stock.id,
        "timeframe": INTRADAY_MARKET_TIMEFRAME,
        "observed_at": observed_at,
        "open_price": bar["open_price"],
        "high_price": bar["high_price"],
        "low_price": bar["low_price"],
        "close_price": bar["close_price"],
        "volume": bar["volume"],
        "amount": bar["amount"],
        "turnover_rate": None,
        "adj_factor": None,
        "raw_payload": {
            **bar["raw_payload"],
            "provider": bar["provider_name"],
            "source_kind": source_kind,
            "frequency": INTRADAY_MARKET_TIMEFRAME,
        },
        **lineage,
    }
    if record is None:
        session.add(MarketBar(**values))
    else:
        for key, value in values.items():
            setattr(record, key, value)
    session.flush()


def sync_intraday_market(
    session: Session,
    symbols: Iterable[str] | None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    normalized_symbols = _normalize_symbols(symbols)
    current_time = now or utcnow()
    if not normalized_symbols:
        status = {
            "status": "idle",
            "provider_name": None,
            "provider_label": None,
            "source_kind": "none",
            "decision_interval_seconds": INTRADAY_DECISION_INTERVAL_SECONDS,
            "market_data_interval_seconds": INTRADAY_MARKET_INTERVAL_SECONDS,
            "last_success_at": None,
            "message": "未提供需要同步的标的。",
            "fallback_used": False,
        }
        _upsert_setting(session, INTRADAY_MARKET_SETTING_KEY, status, description="High-frequency intraday market sync status.")
        return get_intraday_market_status(session, symbols=normalized_symbols, now=current_time)

    latest_cached_market_data_at = _latest_intraday_timestamp(session, normalized_symbols)
    if _intraday_cache_is_fresh(current_time, latest_cached_market_data_at):
        status = {
            "status": "ready",
            "provider_name": None,
            "provider_label": "本地已缓存 5 分钟数据",
            "source_kind": "cached_5min",
            "decision_interval_seconds": INTRADAY_DECISION_INTERVAL_SECONDS,
            "market_data_interval_seconds": INTRADAY_MARKET_INTERVAL_SECONDS,
            "last_success_at": _serialize_datetime(current_time),
            "message": "当前未获取新的实时分钟行情，继续使用本地已缓存的 5 分钟真实数据。",
            "fallback_used": False,
            "inserted_rows": 0,
        }
        _upsert_setting(session, INTRADAY_MARKET_SETTING_KEY, status, description="High-frequency intraday market sync status.")
        return get_intraday_market_status(session, symbols=normalized_symbols, now=current_time)

    stocks = {
        stock.symbol: stock
        for stock in session.scalars(select(Stock).where(Stock.symbol.in_(normalized_symbols))).all()
    }
    inserted_rows = 0
    provider_name: str | None = None
    source_kind = "cached_5min"
    fallback_used = False
    providers_used: set[str] = set()
    source_kinds_used: set[str] = set()

    for symbol in normalized_symbols:
        stock = stocks.get(symbol)
        if stock is None:
            continue
        latest_for_symbol = _latest_intraday_timestamp_for_symbol(session, symbol)
        rows = _canonical_rows(symbol=symbol, provider_name="tushare", rows=_tushare_rows(session, symbol))
        if rows:
            rows = _filter_incremental_rows(rows, latest_cached_market_data_at=latest_for_symbol)
            if rows:
                providers_used.add("tushare")
                source_kinds_used.add("tushare_rt_min_daily")
        else:
            rows = _canonical_rows(
                symbol=symbol,
                provider_name="akshare",
                rows=_akshare_rows_for_window(
                    symbol,
                    current_time=current_time,
                    latest_cached_market_data_at=latest_for_symbol,
                ),
            )
            if rows:
                rows = _filter_incremental_rows(rows, latest_cached_market_data_at=latest_for_symbol)
                if rows:
                    providers_used.add("akshare")
                    source_kinds_used.add("akshare_hist_min_em")
                    fallback_used = True
        for row in rows:
            row_source_kind = "tushare_rt_min_daily" if row["provider_name"] == "tushare" else "akshare_hist_min_em"
            _upsert_market_bar(session, stock=stock, bar=row, source_kind=row_source_kind)
            inserted_rows += 1

    latest_market_data_at = _latest_intraday_timestamp(session, normalized_symbols)
    if len(providers_used) == 1:
        provider_name = next(iter(providers_used))
    elif len(providers_used) > 1:
        provider_name = "mixed"
    if len(source_kinds_used) == 1:
        source_kind = next(iter(source_kinds_used))
    elif len(source_kinds_used) > 1:
        source_kind = "mixed_intraday"
    status = {
        "status": "ready" if latest_market_data_at is not None else "degraded",
        "provider_name": provider_name,
        "provider_label": {
            "tushare": "Tushare 实时分钟",
            "akshare": "AKShare 分钟兜底",
            "mixed": "混合来源（Tushare + AKShare）",
        }.get(provider_name) if provider_name else ("本地已缓存 5 分钟数据" if latest_market_data_at is not None else None),
        "source_kind": source_kind,
        "decision_interval_seconds": INTRADAY_DECISION_INTERVAL_SECONDS,
        "market_data_interval_seconds": INTRADAY_MARKET_INTERVAL_SECONDS,
        "last_success_at": _serialize_datetime(current_time if latest_market_data_at is not None else None),
        "message": (
            f"已同步 {len(normalized_symbols)} 只标的的 5 分钟行情，新增或更新 {inserted_rows} 根 K 线。"
            if inserted_rows > 0
            else ("当前未获取新的 5 分钟行情，继续使用本地已缓存数据。" if latest_market_data_at is not None else "未能获取新的 5 分钟行情。")
        ),
        "fallback_used": fallback_used,
        "inserted_rows": inserted_rows,
    }
    _upsert_setting(session, INTRADAY_MARKET_SETTING_KEY, status, description="High-frequency intraday market sync status.")
    return get_intraday_market_status(session, symbols=normalized_symbols, now=current_time)
