from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import lru_cache
import json
from typing import Any
from urllib import error, request

from sqlalchemy import select
from sqlalchemy.orm import Session

from ashare_evidence.http_client import urlopen
from ashare_evidence.models import ProviderCredential

TUSHARE_STOCK_BASIC_FIELDS = "ts_code,symbol,name,industry,list_date"
DEFAULT_TUSHARE_BASE_URL = "http://api.tushare.pro"
DEFAULT_AKSHARE_TIMEOUT_SECONDS = 5


@dataclass(frozen=True)
class StockProfileResolution:
    symbol: str
    name: str | None
    industry: str | None
    listed_date: date | None
    template_key: str | None
    source: str


LOCAL_STOCK_MASTER_OVERRIDES: dict[str, dict[str, Any]] = {
    "002028.SZ": {
        "name": "思源电气",
        "industry": "电力设备",
        "listed_date": date(2004, 8, 5),
        "template_key": "power_equipment",
    },
    "688981.SH": {
        "name": "中芯国际",
        "industry": "半导体",
        "listed_date": date(2020, 7, 16),
        "template_key": "electronics",
    },
}

INDUSTRY_TEMPLATE_RULES: tuple[tuple[str, str], ...] = (
    ("白酒", "food_beverage"),
    ("食品饮料", "food_beverage"),
    ("消费", "food_beverage"),
    ("电力设备", "power_equipment"),
    ("电气设备", "power_equipment"),
    ("电源设备", "power_equipment"),
    ("储能", "power_equipment"),
    ("锂电", "power_equipment"),
    ("保险", "nonbank_finance"),
    ("证券", "nonbank_finance"),
    ("非银", "nonbank_finance"),
    ("金融", "nonbank_finance"),
    ("半导体", "electronics"),
    ("电子", "electronics"),
    ("芯片", "electronics"),
    ("汽车", "auto"),
    ("整车", "auto"),
    ("新能源车", "auto"),
    ("医药", "pharmaceutical"),
    ("生物", "pharmaceutical"),
    ("创新药", "pharmaceutical"),
)


def _normalize_text(raw: Any) -> str | None:
    if raw is None:
        return None
    value = str(raw).strip()
    if not value or value in {"-", "--", "nan", "None", "null"}:
        return None
    return value


def _parse_list_date(raw: Any) -> date | None:
    value = _normalize_text(raw)
    if value is None:
        return None
    digits = "".join(character for character in value if character.isdigit())
    if len(digits) != 8:
        return None
    value = digits
    return date(int(value[0:4]), int(value[4:6]), int(value[6:8]))


def _infer_template_key(industry: str | None) -> str | None:
    if not industry:
        return None
    normalized = industry.strip()
    for keyword, template_key in INDUSTRY_TEMPLATE_RULES:
        if keyword in normalized:
            return template_key
    return None


def _industry_needs_tushare_enrichment(industry: str | None) -> bool:
    if industry is None:
        return True
    normalized = industry.strip()
    if not normalized:
        return True
    if len(normalized) >= 2 and normalized[0].isalpha() and normalized[1] == " ":
        return True
    return normalized.endswith("行业")


def _tushare_credential(session: Session) -> ProviderCredential | None:
    return session.scalar(
        select(ProviderCredential).where(
            ProviderCredential.provider_name == "tushare",
            ProviderCredential.enabled.is_(True),
        )
    )


@lru_cache(maxsize=1)
def _load_akshare_module() -> Any:
    import akshare as akshare  # type: ignore[import-not-found]

    required_adapters = (
        "stock_info_sz_name_code",
        "stock_info_sh_name_code",
        "stock_info_a_code_name",
        "stock_individual_info_em",
    )
    if any(not callable(getattr(akshare, adapter, None)) for adapter in required_adapters):
        raise ImportError("Required AKShare stock adapters are unavailable")
    return akshare


def akshare_runtime_ready() -> bool:
    try:
        _load_akshare_module()
    except Exception:
        return False
    return True


def _query_akshare_stock_basic(symbol: str) -> dict[str, Any] | None:
    try:
        akshare = _load_akshare_module()
    except Exception:
        return None

    ticker = symbol.partition(".")[0].strip()
    if not ticker:
        return None

    market = symbol.partition(".")[2].strip().upper()
    records: dict[str, Any] = {}
    try:
        if market == "SZ":
            frame = akshare.stock_info_sz_name_code(symbol="A股列表")
            row = frame.loc[frame["A股代码"].astype(str).str.zfill(6) == ticker]
            if not row.empty:
                first = row.iloc[0]
                records = {
                    "name": first.get("A股简称"),
                    "industry": first.get("所属行业"),
                    "list_date": first.get("A股上市日期"),
                }
        elif market == "SH":
            board = "科创板" if ticker.startswith("688") else "主板A股"
            frame = akshare.stock_info_sh_name_code(symbol=board)
            row = frame.loc[frame["证券代码"].astype(str).str.zfill(6) == ticker]
            if not row.empty:
                first = row.iloc[0]
                records = {
                    "name": first.get("证券简称"),
                    "industry": None,
                    "list_date": first.get("上市日期"),
                }
        elif market == "BJ":
            frame = akshare.stock_info_a_code_name()
            row = frame.loc[frame["code"].astype(str).str.zfill(6) == ticker]
            if not row.empty:
                first = row.iloc[0]
                records = {
                    "name": first.get("name"),
                    "industry": None,
                    "list_date": None,
                }
    except Exception:
        records = {}

    detail_records: dict[str, Any] = {}
    try:
        detail_frame = akshare.stock_individual_info_em(symbol=ticker, timeout=DEFAULT_AKSHARE_TIMEOUT_SECONDS)
        if detail_frame is not None and not getattr(detail_frame, "empty", False):
            detail_records = dict(zip(detail_frame["item"].tolist(), detail_frame["value"].tolist(), strict=False))
    except Exception:
        detail_records = {}

    name = _normalize_text(records.get("name")) or _normalize_text(detail_records.get("股票简称"))
    industry = _normalize_text(records.get("industry")) or _normalize_text(detail_records.get("行业"))
    listed_date = records.get("list_date") or detail_records.get("上市时间")
    if name is None and industry is None and _parse_list_date(listed_date) is None:
        return None
    return {
        "name": name,
        "industry": industry,
        "list_date": listed_date,
    }


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
        with urlopen(req, timeout=5) as response:
            body = response.read()
    except (error.URLError, TimeoutError, OSError, ValueError):
        return None

    try:
        parsed = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _first_row(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not payload or payload.get("code") not in {0, None}:
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    fields = data.get("fields")
    items = data.get("items")
    if not isinstance(fields, list) or not isinstance(items, list) or not items:
        return None
    first = items[0]
    if not isinstance(first, list) or len(first) != len(fields):
        return None
    return dict(zip(fields, first, strict=False))


def _query_tushare_stock_basic(session: Session, symbol: str) -> dict[str, Any] | None:
    credential = _tushare_credential(session)
    if credential is None or not credential.access_token:
        return None

    base_url = credential.base_url.strip() if credential.base_url else DEFAULT_TUSHARE_BASE_URL
    token = credential.access_token.strip()
    response = _post_tushare(
        base_url=base_url,
        token=token,
        api_name="stock_basic",
        params={"ts_code": symbol, "list_status": "L"},
        fields=TUSHARE_STOCK_BASIC_FIELDS,
    )
    row = _first_row(response)
    if row is not None:
        return row

    fallback = _post_tushare(
        base_url=base_url,
        token=token,
        api_name="stock_basic",
        params={"ts_code": symbol},
        fields=TUSHARE_STOCK_BASIC_FIELDS,
    )
    return _first_row(fallback)


def resolve_stock_profile(
    session: Session,
    *,
    symbol: str,
    preferred_name: str | None = None,
) -> StockProfileResolution:
    cleaned_name = preferred_name.strip() if preferred_name and preferred_name.strip() else None

    local = LOCAL_STOCK_MASTER_OVERRIDES.get(symbol)
    if local is not None:
        return StockProfileResolution(
            symbol=symbol,
            name=cleaned_name or local["name"],
            industry=local.get("industry"),
            listed_date=local.get("listed_date"),
            template_key=local.get("template_key"),
            source="local_override",
        )

    akshare_row = _query_akshare_stock_basic(symbol)
    akshare_industry = _normalize_text(akshare_row.get("industry")) if akshare_row is not None else None
    akshare_listed_date = _parse_list_date(akshare_row.get("list_date")) if akshare_row is not None else None

    tushare_row = None
    if akshare_row is None or _industry_needs_tushare_enrichment(akshare_industry) or akshare_listed_date is None:
        tushare_row = _query_tushare_stock_basic(session, symbol)

    if akshare_row is not None or tushare_row is not None:
        tushare_industry = _normalize_text(tushare_row.get("industry")) if tushare_row is not None else None
        tushare_name = _normalize_text(tushare_row.get("name")) if tushare_row is not None else None
        prefer_tushare_industry = _industry_needs_tushare_enrichment(akshare_industry)
        industry = tushare_industry if prefer_tushare_industry and tushare_industry is not None else (akshare_industry or tushare_industry)
        name = cleaned_name or _normalize_text(akshare_row.get("name")) if akshare_row is not None else None
        if name is None:
            name = tushare_name
        source = "tushare_stock_basic"
        if akshare_row is not None and tushare_row is not None:
            source = "akshare_stock_master+tushare_stock_basic"
        elif akshare_row is not None:
            source = "akshare_stock_master"
        return StockProfileResolution(
            symbol=symbol,
            name=_normalize_text(name),
            industry=industry,
            listed_date=akshare_listed_date or _parse_list_date(tushare_row.get("list_date") if tushare_row is not None else None),
            template_key=_infer_template_key(industry),
            source=source,
        )

    return StockProfileResolution(
        symbol=symbol,
        name=cleaned_name,
        industry=None,
        listed_date=None,
        template_key=None,
        source="user_input" if cleaned_name else "unresolved",
    )
