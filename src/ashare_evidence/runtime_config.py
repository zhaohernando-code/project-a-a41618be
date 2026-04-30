from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import shutil
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ashare_evidence.db import utcnow
from ashare_evidence.intraday_market import get_intraday_market_status
from ashare_evidence.models import AppSetting, ModelApiKey, ProviderCredential
from ashare_evidence.stock_master import akshare_runtime_ready

DATA_SOURCE_DOCS = {
    "akshare": "https://akshare.akfamily.xyz/data/stock/stock.html",
    "tushare": "https://tushare.pro/document/2?doc_id=27",
}

DEFAULT_BUILTIN_LLM_BASE_URL = "https://api.openai.com/v1"
DEFAULT_BUILTIN_LLM_MODEL = "gpt-5.5"
DEFAULT_BUILTIN_LLM_TRANSPORT = "codex_cli"
DEFAULT_BUILTIN_CODEX_BASE_URL = "codex-cli://local"
DEFAULT_BUILTIN_CODEX_CANDIDATES = (
    "/Applications/Codex.app/Contents/Resources/codex",
)

PROVIDER_DISPLAY_NAMES = {
    "akshare": "AKShare",
    "tushare": "Tushare",
}

PROVIDER_RUNTIME_STATUS = {
    "akshare": {
        "credential_required": False,
        "ready_status_label": "已接入",
        "missing_status_label": "适配器未就绪",
    },
    "tushare": {
        "credential_required": True,
        "runtime_ready_if_credential_configured": True,
        "configured_status_label": "已配置",
        "missing_status_label": "需 Token",
    },
}

DEFAULT_SETTINGS: dict[str, dict[str, Any]] = {
    "deployment_profile": {
        "description": "Self-hosted deployment profile and storage selection.",
        "value": {
            "deployment_mode": "self_hosted_server",
            "storage_engine": "SQLite",
            "cache_backend": "Redis",
            "watchlist_scope": "global_shared_pool",
            "watchlist_cache_only": True,
            "llm_failover_enabled": True,
            "notes": [
                "前端不再暴露离线快照和在线 API 模式切换，统一走服务端真实数据链路。",
                "一期持久化以 SQLite 为主，后续通过仓储边界平滑切换到更重的 SQL 方案。",
            ],
        },
    },
    "provider_strategy": {
        "description": "Runtime provider selection and normalized domain model.",
        "value": {
            "selection_mode": "runtime_policy",
            "default_order": ["akshare", "tushare"],
            "fallback_on_error": True,
            "fallback_on_empty": True,
            "cooldown_seconds": 30,
            "fields": [
                {
                    "dataset": "quote",
                    "canonical_field": "last_price",
                    "akshare_field": "最新价",
                    "tushare_field": "close / price",
                    "notes": "实时行情统一为 latest price，盘后可回落到最新日线 close。",
                },
                {
                    "dataset": "quote",
                    "canonical_field": "turnover_rate_pct",
                    "akshare_field": "换手率",
                    "tushare_field": "turnover_rate",
                    "notes": "统一使用百分比口径，进入领域层前不再保留源端差异。",
                },
                {
                    "dataset": "kline",
                    "canonical_field": "trade_time",
                    "akshare_field": "日期 / 时间",
                    "tushare_field": "trade_date / time",
                    "notes": "统一写成 Asia/Shanghai 语义的观测时间戳。",
                },
                {
                    "dataset": "kline",
                    "canonical_field": "adjustment",
                    "akshare_field": "adjust",
                    "tushare_field": "pro_bar adj",
                    "notes": "统一为 none/qfq/hfq，禁止把 provider 原始枚举泄漏到业务层。",
                },
                {
                    "dataset": "financial_report",
                    "canonical_field": "report_period",
                    "akshare_field": "REPORT_DATE / 日期",
                    "tushare_field": "end_date",
                    "notes": "统一使用报告期，不直接依赖单个源的公告字段命名。",
                },
                {
                    "dataset": "financial_report",
                    "canonical_field": "revenue",
                    "akshare_field": "营业总收入 / 营业收入",
                    "tushare_field": "total_revenue / revenue",
                    "notes": "统一先落标准字段，再把源字段保存在 raw_payload。",
                },
            ],
            "providers": [
                {
                    "provider_name": "akshare",
                    "role": "实时行情与公开站点补缺",
                    "freshness_note": "A 股实时行情可直接抓取公开站点封装结果；部分历史/复权字段需注意口径差异。",
                    "docs_url": DATA_SOURCE_DOCS["akshare"],
                    "notes": [
                        "当前真实分析链已接入 `stock_zh_a_daily`（新浪日线）、`stock_zh_a_disclosure_report_cninfo`（巨潮公告）和东财财报/研报元数据适配。",
                        "AKShare 实时分钟 `stock_zh_a_hist_min_em` 继续保留为盘中链路兜底适配，但运行时是否可用要以当下网络与站点状态为准。",
                    ],
                },
                {
                    "provider_name": "tushare",
                    "role": "日线/K线、财报与结构化指标",
                    "freshness_note": "日线 `daily` 为交易日 15:00-16:00 入库；财务指标 `fina_indicator` 随财报实时更新。",
                    "docs_url": DATA_SOURCE_DOCS["tushare"],
                    "notes": [
                        "当前优先用 `daily + daily_basic` 生成低频真实分析，并用 `rt_min_daily` 支撑 5 分钟盘中链路。",
                        "Tushare `fina_indicator` 已作为财务快照主源适配；无 Token 或权限不足时会回落到公开财报摘要。",
                    ],
                },
            ],
        },
    },
    "cache_policy": {
        "description": "Watchlist-only cache strategy for market data.",
        "value": {
            "backend": "redis",
            "watchlist_only": True,
            "anti_stampede": {
                "singleflight": True,
                "serve_stale_on_error": True,
                "empty_result_ttl_seconds": 15,
                "lock_timeout_seconds": 8,
                "jitter_ratio": 0.2,
            },
            "datasets": [
                {
                    "dataset": "quote",
                    "label": "实时行情",
                    "ttl_seconds": 5,
                    "stale_if_error_seconds": 30,
                    "warm_on_watchlist": True,
                },
                {
                    "dataset": "kline",
                    "label": "K线数据",
                    "ttl_seconds": 60,
                    "stale_if_error_seconds": 300,
                    "warm_on_watchlist": True,
                },
                {
                    "dataset": "financial_report",
                    "label": "财报数据",
                    "ttl_seconds": 86400,
                    "stale_if_error_seconds": 172800,
                    "warm_on_watchlist": True,
                },
            ],
        },
    },
}


def _get_setting(session: Session, key: str) -> AppSetting | None:
    return session.scalar(select(AppSetting).where(AppSetting.setting_key == key))


def ensure_runtime_defaults(session: Session) -> None:
    changed = False
    for key, payload in DEFAULT_SETTINGS.items():
        record = _get_setting(session, key)
        if record is None:
            session.add(
                AppSetting(
                    setting_key=key,
                    description=payload["description"],
                    setting_value=payload["value"],
                )
            )
            changed = True
    if changed:
        session.flush()


def get_builtin_llm_executor_config() -> dict[str, Any]:
    configured_transport = (
        os.getenv("ASHARE_BUILTIN_LLM_TRANSPORT")
        or DEFAULT_BUILTIN_LLM_TRANSPORT
    ).strip().lower()
    api_key = (
        os.getenv("ASHARE_BUILTIN_LLM_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or ""
    ).strip()
    base_url = (
        os.getenv("ASHARE_BUILTIN_LLM_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or DEFAULT_BUILTIN_LLM_BASE_URL
    ).strip().rstrip("/")
    model_name = (
        os.getenv("ASHARE_BUILTIN_LLM_MODEL")
        or os.getenv("OPENAI_MODEL")
        or DEFAULT_BUILTIN_LLM_MODEL
    ).strip()
    provider_name = (os.getenv("ASHARE_BUILTIN_LLM_PROVIDER") or "openai").strip().lower()
    codex_bin = _resolve_builtin_codex_bin()
    openai_api_enabled = bool(api_key and base_url and model_name)
    transport_kind = "openai_api"
    if configured_transport == "codex_cli":
        if codex_bin:
            transport_kind = "codex_cli"
        elif openai_api_enabled:
            transport_kind = "openai_api"
    elif configured_transport == "openai_api" and openai_api_enabled:
        transport_kind = "openai_api"
    elif codex_bin:
        transport_kind = "codex_cli"
    enabled = bool(
        (transport_kind == "codex_cli" and codex_bin)
        or (transport_kind == "openai_api" and openai_api_enabled)
    )
    return {
        "id": None,
        "name": "builtin-gpt",
        "provider_name": provider_name,
        "model_name": model_name,
        "base_url": DEFAULT_BUILTIN_CODEX_BASE_URL if transport_kind == "codex_cli" else base_url,
        "api_key": api_key,
        "codex_bin": codex_bin,
        "transport_kind": transport_kind,
        "enabled": enabled,
    }


def _resolve_builtin_codex_bin() -> str | None:
    candidates: list[str] = []
    explicit = (os.getenv("ASHARE_BUILTIN_CODEX_BIN") or "").strip()
    if explicit:
        candidates.append(explicit)
    discovered = shutil.which("codex")
    if discovered:
        candidates.append(discovered)
    candidates.extend(DEFAULT_BUILTIN_CODEX_CANDIDATES)
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        path = Path(candidate).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    return None


def _mask_secret(value: str | None) -> str | None:
    if not value:
        return None
    stripped = value.strip()
    if len(stripped) <= 8:
        return "*" * len(stripped)
    return f"{stripped[:4]}...{stripped[-4:]}"


def _serialize_provider_credential(record: ProviderCredential) -> dict[str, Any]:
    return {
        "id": record.id,
        "provider_name": record.provider_name,
        "display_name": record.display_name,
        "base_url": record.base_url,
        "enabled": record.enabled,
        "notes": record.notes,
        "token_configured": bool(record.access_token),
        "masked_token": _mask_secret(record.access_token),
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _serialize_model_api_key(record: ModelApiKey) -> dict[str, Any]:
    return {
        "id": record.id,
        "name": record.name,
        "provider_name": record.provider_name,
        "model_name": record.model_name,
        "base_url": record.base_url,
        "enabled": record.enabled,
        "is_default": record.is_default,
        "priority": record.priority,
        "masked_key": _mask_secret(record.api_key),
        "last_status": record.last_status,
        "last_error": record.last_error,
        "last_checked_at": record.last_checked_at,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def list_provider_credentials(session: Session) -> list[dict[str, Any]]:
    return [
        _serialize_provider_credential(record)
        for record in session.scalars(select(ProviderCredential).order_by(ProviderCredential.provider_name.asc())).all()
    ]


def upsert_provider_credential(
    session: Session,
    provider_name: str,
    *,
    access_token: str | None,
    base_url: str | None,
    enabled: bool,
    notes: str | None,
) -> dict[str, Any]:
    normalized_name = provider_name.strip().lower()
    if normalized_name not in PROVIDER_DISPLAY_NAMES:
        raise ValueError(f"Unsupported provider credential target: {provider_name}")
    record = session.scalar(select(ProviderCredential).where(ProviderCredential.provider_name == normalized_name))
    if record is None:
        record = ProviderCredential(
            provider_name=normalized_name,
            display_name=PROVIDER_DISPLAY_NAMES[normalized_name],
            access_token=access_token.strip() if access_token else None,
            base_url=base_url.strip() if base_url else None,
            enabled=enabled,
            notes=notes.strip() if notes else None,
            config_payload={},
        )
        session.add(record)
    else:
        record.access_token = access_token.strip() if access_token else None
        record.base_url = base_url.strip() if base_url else None
        record.enabled = enabled
        record.notes = notes.strip() if notes else None
    session.flush()
    return _serialize_provider_credential(record)


def list_model_api_keys(session: Session) -> list[dict[str, Any]]:
    records = session.scalars(
        select(ModelApiKey).order_by(ModelApiKey.is_default.desc(), ModelApiKey.priority.asc(), ModelApiKey.id.asc())
    ).all()
    return [_serialize_model_api_key(record) for record in records]


def _ensure_single_default(session: Session, target_id: int) -> None:
    for record in session.scalars(select(ModelApiKey)).all():
        record.is_default = record.id == target_id
    session.flush()


def create_model_api_key(
    session: Session,
    *,
    name: str,
    provider_name: str,
    model_name: str,
    base_url: str,
    api_key: str,
    enabled: bool,
    priority: int,
    make_default: bool,
) -> dict[str, Any]:
    if not name.strip():
        raise ValueError("Model API key name is required.")
    if not api_key.strip():
        raise ValueError("Model API key value is required.")
    record = ModelApiKey(
        name=name.strip(),
        provider_name=provider_name.strip().lower(),
        model_name=model_name.strip(),
        base_url=base_url.strip().rstrip("/"),
        api_key=api_key.strip(),
        enabled=enabled,
        is_default=False,
        priority=priority,
        last_status="untested",
        last_error=None,
        last_checked_at=None,
        metadata_payload={},
    )
    session.add(record)
    session.flush()
    default_exists = session.scalar(select(ModelApiKey).where(ModelApiKey.is_default.is_(True)))
    if make_default or default_exists is None:
        _ensure_single_default(session, record.id)
    return _serialize_model_api_key(record)


def update_model_api_key(
    session: Session,
    key_id: int,
    *,
    name: str | None = None,
    provider_name: str | None = None,
    model_name: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    enabled: bool | None = None,
    priority: int | None = None,
    make_default: bool | None = None,
) -> dict[str, Any]:
    record = session.get(ModelApiKey, key_id)
    if record is None:
        raise LookupError(f"Model API key {key_id} not found.")
    if name is not None:
        record.name = name.strip()
    if provider_name is not None:
        record.provider_name = provider_name.strip().lower()
    if model_name is not None:
        record.model_name = model_name.strip()
    if base_url is not None:
        record.base_url = base_url.strip().rstrip("/")
    if api_key is not None:
        trimmed = api_key.strip()
        if trimmed:
            record.api_key = trimmed
            record.last_status = "untested"
            record.last_error = None
            record.last_checked_at = None
    if enabled is not None:
        record.enabled = enabled
    if priority is not None:
        record.priority = priority
    session.flush()
    if make_default:
        _ensure_single_default(session, record.id)
    elif record.is_default and not record.enabled:
        fallback = session.scalar(
            select(ModelApiKey)
            .where(ModelApiKey.id != record.id, ModelApiKey.enabled.is_(True))
            .order_by(ModelApiKey.priority.asc(), ModelApiKey.id.asc())
        )
        if fallback is not None:
            _ensure_single_default(session, fallback.id)
            record.is_default = False
    return _serialize_model_api_key(record)


def set_default_model_api_key(session: Session, key_id: int) -> dict[str, Any]:
    record = session.get(ModelApiKey, key_id)
    if record is None:
        raise LookupError(f"Model API key {key_id} not found.")
    _ensure_single_default(session, key_id)
    return _serialize_model_api_key(record)


def delete_model_api_key(session: Session, key_id: int) -> dict[str, Any]:
    record = session.get(ModelApiKey, key_id)
    if record is None:
        raise LookupError(f"Model API key {key_id} not found.")
    was_default = record.is_default
    name = record.name
    session.delete(record)
    session.flush()
    if was_default:
        fallback = session.scalar(
            select(ModelApiKey).where(ModelApiKey.enabled.is_(True)).order_by(ModelApiKey.priority.asc(), ModelApiKey.id.asc())
        )
        if fallback is not None:
            _ensure_single_default(session, fallback.id)
    return {
        "id": key_id,
        "name": name,
        "deleted": True,
        "deleted_at": utcnow(),
    }


def get_runtime_settings(session: Session) -> dict[str, Any]:
    ensure_runtime_defaults(session)
    deployment = _get_setting(session, "deployment_profile")
    provider_strategy = _get_setting(session, "provider_strategy")
    cache_policy = _get_setting(session, "cache_policy")
    provider_records = {
        item["provider_name"]: item
        for item in list_provider_credentials(session)
    }
    key_records = list_model_api_keys(session)
    deployment_value = deployment.setting_value if deployment is not None else {}
    provider_value = provider_strategy.setting_value if provider_strategy is not None else {}
    cache_value = cache_policy.setting_value if cache_policy is not None else {}

    data_sources = []
    for provider in provider_value.get("providers", []):
        provider_name = provider["provider_name"]
        credential = provider_records.get(provider_name)
        credential_configured = bool(
            credential and (credential["token_configured"] or credential["base_url"])
        )
        runtimeStatus = PROVIDER_RUNTIME_STATUS.get(provider_name, {})
        credential_required = bool(runtimeStatus.get("credential_required"))
        runtime_ready = bool(runtimeStatus.get("runtime_ready"))
        status_label = "未配置"
        if provider_name == "tushare":
            runtime_ready = credential_configured and bool(runtimeStatus.get("runtime_ready_if_credential_configured"))
            status_label = (
                runtimeStatus.get("configured_status_label", "已配置")
                if credential_configured
                else runtimeStatus.get("missing_status_label", "需 Token")
            )
        elif provider_name == "akshare":
            runtime_ready = akshare_runtime_ready()
            status_label = (
                runtimeStatus.get("ready_status_label", "已接入")
                if runtime_ready
                else runtimeStatus.get("missing_status_label", "适配器未就绪")
            )
        elif runtimeStatus:
            status_label = str(runtimeStatus.get("status_label") or status_label)
        intraday_status = get_intraday_market_status(session)
        supports_intraday = provider_name in {"tushare", "akshare"}
        intraday_runtime_ready = False
        intraday_status_label = None
        if supports_intraday:
            if provider_name == "tushare":
                intraday_runtime_ready = credential_configured
                intraday_status_label = "实时分钟已配置" if credential_configured else "实时分钟需权限"
            else:
                intraday_runtime_ready = runtime_ready
                intraday_status_label = "分钟兜底可用" if runtime_ready else "分钟兜底不可用"
            if intraday_status.get("provider_name") == provider_name and intraday_status.get("latest_market_data_at"):
                intraday_status_label = f"{intraday_status_label} · 最近同步 {intraday_status['latest_market_data_at']}"
        data_sources.append(
            {
                **provider,
                "credential_configured": credential_configured,
                "credential_required": credential_required,
                "runtime_ready": runtime_ready,
                "status_label": status_label,
                "supports_intraday": supports_intraday,
                "intraday_runtime_ready": intraday_runtime_ready,
                "intraday_status_label": intraday_status_label,
                "base_url": credential["base_url"] if credential else None,
                "enabled": credential["enabled"] if credential else True,
            }
        )

    return {
        "generated_at": utcnow(),
        "deployment_mode": deployment_value.get("deployment_mode", "self_hosted_server"),
        "storage_engine": deployment_value.get("storage_engine", "SQLite"),
        "cache_backend": deployment_value.get("cache_backend", "Redis"),
        "watchlist_scope": deployment_value.get("watchlist_scope", "global_shared_pool"),
        "watchlist_cache_only": deployment_value.get("watchlist_cache_only", True),
        "llm_failover_enabled": deployment_value.get("llm_failover_enabled", True),
        "deployment_notes": deployment_value.get("notes", []),
        "provider_selection_mode": provider_value.get("selection_mode", "runtime_policy"),
        "provider_order": provider_value.get("default_order", []),
        "provider_cooldown_seconds": provider_value.get("cooldown_seconds", 30),
        "field_mappings": provider_value.get("fields", []),
        "data_sources": data_sources,
        "cache_policies": cache_value.get("datasets", []),
        "anti_stampede": cache_value.get("anti_stampede", {}),
        "provider_credentials": list(provider_records.values()),
        "model_api_keys": key_records,
        "default_model_api_key_id": next((item["id"] for item in key_records if item["is_default"]), None),
    }


def get_runtime_overview(session: Session) -> dict[str, Any]:
    settings = get_runtime_settings(session)
    return {
        key: value
        for key, value in settings.items()
        if key not in {"provider_credentials", "model_api_keys", "default_model_api_key_id"}
    }


def record_model_api_key_result(
    session: Session,
    key_id: int,
    *,
    status: str,
    error_message: str | None,
    checked_at: datetime | None = None,
) -> None:
    record = session.get(ModelApiKey, key_id)
    if record is None:
        return
    record.last_status = status
    record.last_error = error_message
    record.last_checked_at = checked_at or utcnow()
    session.flush()


def resolve_llm_key_candidates(session: Session, preferred_key_id: int | None = None) -> list[ModelApiKey]:
    enabled_keys = session.scalars(
        select(ModelApiKey).where(ModelApiKey.enabled.is_(True)).order_by(ModelApiKey.is_default.desc(), ModelApiKey.priority.asc(), ModelApiKey.id.asc())
    ).all()
    if preferred_key_id is None:
        return enabled_keys
    preferred = [item for item in enabled_keys if item.id == preferred_key_id]
    remainder = [item for item in enabled_keys if item.id != preferred_key_id]
    return preferred + remainder
