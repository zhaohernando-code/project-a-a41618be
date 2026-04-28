from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, object_session, selectinload

from ashare_evidence.contract_status import (
    STATUS_PENDING_REBUILD,
    STATUS_RESEARCH_CANDIDATE,
    STATUS_SYNTHETIC_DEMO,
    STATUS_VERIFIED,
)
from ashare_evidence.manual_research_contract import build_manual_llm_review_projection
from ashare_evidence.phase2 import PHASE2_MANUAL_REVIEW_NOTE, phase2_target_horizon_label
from ashare_evidence.lineage import REQUIRED_LINEAGE_FIELDS, build_lineage, compute_lineage_hash
from ashare_evidence.models import (
    FeatureSnapshot,
    IngestionRun,
    MarketBar,
    ModelRegistry,
    ModelResult,
    ModelRun,
    ModelVersion,
    NewsEntityLink,
    NewsItem,
    PaperFill,
    PaperOrder,
    PaperPortfolio,
    PromptVersion,
    Recommendation,
    RecommendationEvidence,
    Sector,
    SectorMembership,
    Stock,
)
from ashare_evidence.research_artifacts import normalize_product_validation_status
from ashare_evidence.research_artifact_store import (
    artifact_root_from_database_url,
    read_manifest_if_exists,
    read_validation_metrics_if_exists,
)
from ashare_evidence.recommendation_selection import (
    collapse_recommendation_history,
    recommendation_recency_ordering,
)
from ashare_evidence.providers import EvidenceBundle

TRACE_MODEL_MAP = {
    "market_bar": MarketBar,
    "news_item": NewsItem,
    "feature_snapshot": FeatureSnapshot,
    "model_result": ModelResult,
    "sector_membership": SectorMembership,
}


def _extract_lineage(record: Mapping[str, Any]) -> dict[str, str]:
    return {field: str(record[field]) for field in REQUIRED_LINEAGE_FIELDS}


def _upsert_one(session: Session, model: type[Any], lookup: dict[str, Any], values: dict[str, Any]) -> Any:
    instance = session.scalar(select(model).filter_by(**lookup))
    payload = {**lookup, **values}
    if instance is None:
        instance = model(**payload)
        session.add(instance)
    else:
        for key, value in payload.items():
            setattr(instance, key, value)
    session.flush()
    return instance


def _record_ingestion_run(
    session: Session,
    *,
    provider_name: str,
    dataset_name: str,
    symbol: str,
    record_count: int,
    source_refs: list[str],
) -> IngestionRun:
    params_payload = {
        "provider_name": provider_name,
        "dataset_name": dataset_name,
        "symbol": symbol,
        "source_refs": source_refs,
    }
    run_key = f"{provider_name}:{dataset_name}:{symbol}:{compute_lineage_hash(params_payload)[:12]}"
    lineage = build_lineage(
        params_payload,
        source_uri=f"pipeline://ingestion/{provider_name}/{dataset_name}/{symbol}",
        license_tag="internal-pipeline",
        usage_scope="internal_research",
        redistribution_scope="none",
    )
    return _upsert_one(
        session,
        IngestionRun,
        {"run_key": run_key},
        {
            "provider_name": provider_name,
            "dataset_name": dataset_name,
            "started_at": datetime.now().astimezone(),
            "finished_at": datetime.now().astimezone(),
            "status": "completed",
            "record_count": record_count,
            "error_message": None,
            "params_payload": params_payload,
            **lineage,
        },
    )


def ingest_bundle(session: Session, bundle: EvidenceBundle) -> Recommendation:
    reference_ids: dict[tuple[str, str], int] = {}

    stock = _upsert_one(
        session,
        Stock,
        {"symbol": bundle.stock["symbol"]},
        {
            "ticker": bundle.stock["ticker"],
            "exchange": bundle.stock["exchange"],
            "name": bundle.stock["name"],
            "provider_symbol": bundle.stock["provider_symbol"],
            "listed_date": bundle.stock["listed_date"],
            "delisted_date": bundle.stock.get("delisted_date"),
            "status": bundle.stock["status"],
            "profile_payload": bundle.stock["profile_payload"],
            **_extract_lineage(bundle.stock),
        },
    )

    sectors_by_code: dict[str, Sector] = {}
    for sector_record in bundle.sectors:
        sector = _upsert_one(
            session,
            Sector,
            {"sector_code": sector_record["sector_code"]},
            {
                "name": sector_record["name"],
                "level": sector_record["level"],
                "definition_payload": sector_record["definition_payload"],
                **_extract_lineage(sector_record),
            },
        )
        sectors_by_code[sector.sector_code] = sector

    for membership_record in bundle.sector_memberships:
        membership = _upsert_one(
            session,
            SectorMembership,
            {"membership_key": membership_record["membership_key"]},
            {
                "stock_id": stock.id,
                "sector_id": sectors_by_code[membership_record["sector_code"]].id,
                "effective_from": membership_record["effective_from"],
                "effective_to": membership_record.get("effective_to"),
                "is_primary": membership_record["is_primary"],
                "membership_payload": membership_record["membership_payload"],
                **_extract_lineage(membership_record),
            },
        )
        reference_ids[("sector_membership", membership_record["membership_key"])] = membership.id

    for bar_record in bundle.market_bars:
        bar = _upsert_one(
            session,
            MarketBar,
            {"bar_key": bar_record["bar_key"]},
            {
                "stock_id": stock.id,
                "timeframe": bar_record["timeframe"],
                "observed_at": bar_record["observed_at"],
                "open_price": bar_record["open_price"],
                "high_price": bar_record["high_price"],
                "low_price": bar_record["low_price"],
                "close_price": bar_record["close_price"],
                "volume": bar_record["volume"],
                "amount": bar_record["amount"],
                "turnover_rate": bar_record.get("turnover_rate"),
                "adj_factor": bar_record.get("adj_factor"),
                "raw_payload": bar_record["raw_payload"],
                **_extract_lineage(bar_record),
            },
        )
        reference_ids[("market_bar", bar_record["bar_key"])] = bar.id

    news_by_key: dict[str, NewsItem] = {}
    for news_record in bundle.news_items:
        news = _upsert_one(
            session,
            NewsItem,
            {"news_key": news_record["news_key"]},
            {
                "provider_name": news_record["provider_name"],
                "external_id": news_record["external_id"],
                "headline": news_record["headline"],
                "summary": news_record["summary"],
                "content_excerpt": news_record.get("content_excerpt"),
                "published_at": news_record["published_at"],
                "event_scope": news_record["event_scope"],
                "dedupe_key": news_record["dedupe_key"],
                "raw_payload": news_record["raw_payload"],
                **_extract_lineage(news_record),
            },
        )
        news_by_key[news.news_key] = news
        reference_ids[("news_item", news_record["news_key"])] = news.id

    for link_record in bundle.news_links:
        _upsert_one(
            session,
            NewsEntityLink,
            {
                "news_id": news_by_key[link_record["news_key"]].id,
                "entity_type": link_record["entity_type"],
                "stock_id": stock.id if link_record.get("stock_symbol") else None,
                "sector_id": sectors_by_code[link_record["sector_code"]].id if link_record.get("sector_code") else None,
            },
            {
                "market_tag": link_record.get("market_tag"),
                "relevance_score": link_record["relevance_score"],
                "impact_direction": link_record["impact_direction"],
                "effective_at": link_record["effective_at"],
                "decay_half_life_hours": link_record["decay_half_life_hours"],
                "mapping_payload": link_record["mapping_payload"],
                **_extract_lineage(link_record),
            },
        )

    for snapshot_record in bundle.feature_snapshots:
        snapshot = _upsert_one(
            session,
            FeatureSnapshot,
            {"snapshot_key": snapshot_record["snapshot_key"]},
            {
                "stock_id": stock.id,
                "feature_set_name": snapshot_record["feature_set_name"],
                "feature_set_version": snapshot_record["feature_set_version"],
                "as_of": snapshot_record["as_of"],
                "window_start": snapshot_record.get("window_start"),
                "window_end": snapshot_record.get("window_end"),
                "feature_values": snapshot_record["feature_values"],
                "upstream_refs": snapshot_record["upstream_refs"],
                **_extract_lineage(snapshot_record),
            },
        )
        reference_ids[("feature_snapshot", snapshot_record["snapshot_key"])] = snapshot.id

    registry = _upsert_one(
        session,
        ModelRegistry,
        {"name": bundle.model_registry["name"]},
        {
            "family": bundle.model_registry["family"],
            "description": bundle.model_registry["description"],
            "registry_payload": bundle.model_registry["registry_payload"],
            **_extract_lineage(bundle.model_registry),
        },
    )

    model_version = _upsert_one(
        session,
        ModelVersion,
        {"registry_id": registry.id, "version": bundle.model_version["version"]},
        {
            "validation_scheme": bundle.model_version["validation_scheme"],
            "training_window_start": bundle.model_version.get("training_window_start"),
            "training_window_end": bundle.model_version.get("training_window_end"),
            "artifact_uri": bundle.model_version.get("artifact_uri"),
            "config_payload": bundle.model_version["config_payload"],
            **_extract_lineage(bundle.model_version),
        },
    )

    prompt_version = _upsert_one(
        session,
        PromptVersion,
        {"name": bundle.prompt_version["name"], "version": bundle.prompt_version["version"]},
        {
            "risk_disclaimer": bundle.prompt_version["risk_disclaimer"],
            "prompt_payload": bundle.prompt_version["prompt_payload"],
            **_extract_lineage(bundle.prompt_version),
        },
    )

    model_run = _upsert_one(
        session,
        ModelRun,
        {"run_key": bundle.model_run["run_key"]},
        {
            "model_version_id": model_version.id,
            "started_at": bundle.model_run["started_at"],
            "finished_at": bundle.model_run["finished_at"],
            "run_status": bundle.model_run["run_status"],
            "target_scope": bundle.model_run["target_scope"],
            "metrics_payload": bundle.model_run["metrics_payload"],
            "input_refs": bundle.model_run["input_refs"],
            **_extract_lineage(bundle.model_run),
        },
    )

    for result_record in bundle.model_results:
        result = _upsert_one(
            session,
            ModelResult,
            {"result_key": result_record["result_key"]},
            {
                "model_run_id": model_run.id,
                "stock_id": stock.id,
                "as_of_data_time": result_record["as_of_data_time"],
                "valid_until": result_record.get("valid_until"),
                "forecast_horizon_days": result_record["forecast_horizon_days"],
                "predicted_direction": result_record["predicted_direction"],
                "expected_return": result_record["expected_return"],
                "confidence_score": result_record["confidence_score"],
                "confidence_bucket": result_record["confidence_bucket"],
                "driver_factors": result_record["driver_factors"],
                "risk_factors": result_record["risk_factors"],
                "result_payload": result_record["result_payload"],
                **_extract_lineage(result_record),
            },
        )
        reference_ids[("model_result", result_record["result_key"])] = result.id

    recommendation = _upsert_one(
        session,
        Recommendation,
        {"recommendation_key": bundle.recommendation["recommendation_key"]},
        {
            "stock_id": stock.id,
            "model_version_id": model_version.id,
            "model_run_id": model_run.id,
            "prompt_version_id": prompt_version.id,
            "as_of_data_time": bundle.recommendation["as_of_data_time"],
            "generated_at": bundle.recommendation["generated_at"],
            "direction": bundle.recommendation["direction"],
            "confidence_score": bundle.recommendation["confidence_score"],
            "confidence_label": bundle.recommendation["confidence_label"],
            "horizon_min_days": bundle.recommendation["horizon_min_days"],
            "horizon_max_days": bundle.recommendation["horizon_max_days"],
            "evidence_status": bundle.recommendation["evidence_status"],
            "summary": bundle.recommendation["summary"],
            "core_drivers": bundle.recommendation["core_drivers"],
            "risk_flags": bundle.recommendation["risk_flags"],
            "degrade_reason": bundle.recommendation.get("degrade_reason"),
            "recommendation_payload": bundle.recommendation["recommendation_payload"],
            **_extract_lineage(bundle.recommendation),
        },
    )

    for evidence_record in bundle.recommendation_evidence:
        evidence_id = reference_ids[(evidence_record["evidence_type"], evidence_record["reference_key"])]
        _upsert_one(
            session,
            RecommendationEvidence,
            {
                "recommendation_id": recommendation.id,
                "evidence_type": evidence_record["evidence_type"],
                "evidence_id": evidence_id,
                "role": evidence_record["role"],
            },
            {
                "rank": evidence_record["rank"],
                "evidence_label": evidence_record["evidence_label"],
                "snippet": evidence_record.get("snippet"),
                "reference_payload": evidence_record["reference_payload"],
                **_extract_lineage(evidence_record),
            },
        )

    portfolios_by_key: dict[str, PaperPortfolio] = {}
    for portfolio_record in bundle.paper_portfolios:
        portfolio = _upsert_one(
            session,
            PaperPortfolio,
            {"portfolio_key": portfolio_record["portfolio_key"]},
            {
                "name": portfolio_record["name"],
                "mode": portfolio_record["mode"],
                "benchmark_symbol": portfolio_record.get("benchmark_symbol"),
                "base_currency": portfolio_record["base_currency"],
                "cash_balance": portfolio_record["cash_balance"],
                "status": portfolio_record["status"],
                "portfolio_payload": portfolio_record["portfolio_payload"],
                **_extract_lineage(portfolio_record),
            },
        )
        portfolios_by_key[portfolio.portfolio_key] = portfolio

    for order_record in bundle.paper_orders:
        order = _upsert_one(
            session,
            PaperOrder,
            {"order_key": order_record["order_key"]},
            {
                "portfolio_id": portfolios_by_key[order_record["portfolio_key"]].id,
                "stock_id": stock.id,
                "recommendation_id": (
                    recommendation.id
                    if order_record.get("recommendation_key") == bundle.recommendation["recommendation_key"]
                    else None
                ),
                "order_source": order_record["order_source"],
                "side": order_record["side"],
                "requested_at": order_record["requested_at"],
                "quantity": order_record["quantity"],
                "order_type": order_record["order_type"],
                "limit_price": order_record.get("limit_price"),
                "status": order_record["status"],
                "notes": order_record.get("notes"),
                "order_payload": order_record["order_payload"],
                **_extract_lineage(order_record),
            },
        )
        reference_ids[("paper_order", order_record["order_key"])] = order.id

    for fill_record in bundle.paper_fills:
        _upsert_one(
            session,
            PaperFill,
            {"fill_key": fill_record["fill_key"]},
            {
                "order_id": reference_ids[("paper_order", fill_record["order_key"])],
                "stock_id": stock.id,
                "filled_at": fill_record["filled_at"],
                "price": fill_record["price"],
                "quantity": fill_record["quantity"],
                "fee": fill_record["fee"],
                "tax": fill_record["tax"],
                "slippage_bps": fill_record["slippage_bps"],
                "fill_payload": fill_record["fill_payload"],
                **_extract_lineage(fill_record),
            },
        )

    _record_ingestion_run(
        session,
        provider_name=bundle.provider_name,
        dataset_name="market_and_master",
        symbol=bundle.symbol,
        record_count=1 + len(bundle.sectors) + len(bundle.sector_memberships) + len(bundle.market_bars),
        source_refs=[bundle.stock["source_uri"], *(record["source_uri"] for record in bundle.market_bars)],
    )
    _record_ingestion_run(
        session,
        provider_name=bundle.provider_name,
        dataset_name="news",
        symbol=bundle.symbol,
        record_count=len(bundle.news_items) + len(bundle.news_links),
        source_refs=[record["source_uri"] for record in bundle.news_items],
    )
    _record_ingestion_run(
        session,
        provider_name=bundle.provider_name,
        dataset_name="features_and_models",
        symbol=bundle.symbol,
        record_count=1 + 1 + 1 + len(bundle.model_results) + len(bundle.feature_snapshots),
        source_refs=[
            bundle.model_registry["source_uri"],
            bundle.model_version["source_uri"],
            bundle.model_run["source_uri"],
        ],
    )
    _record_ingestion_run(
        session,
        provider_name=bundle.provider_name,
        dataset_name="recommendations_and_simulation",
        symbol=bundle.symbol,
        record_count=1 + len(bundle.recommendation_evidence) + len(bundle.paper_orders) + len(bundle.paper_fills),
        source_refs=[
            bundle.recommendation["source_uri"],
            *(record["source_uri"] for record in bundle.paper_orders),
        ],
    )

    return recommendation
def _serialize_lineage(instance: Any) -> dict[str, str]:
    return {
        "license_tag": instance.license_tag,
        "usage_scope": instance.usage_scope,
        "redistribution_scope": instance.redistribution_scope,
        "source_uri": instance.source_uri,
        "lineage_hash": instance.lineage_hash,
    }


def _serialize_fill(fill: PaperFill) -> dict[str, Any]:
    return {
        "filled_at": fill.filled_at,
        "price": fill.price,
        "quantity": fill.quantity,
        "fee": fill.fee,
        "tax": fill.tax,
        "slippage_bps": fill.slippage_bps,
        "lineage": _serialize_lineage(fill),
    }


def _serialize_order(order: PaperOrder) -> dict[str, Any]:
    return {
        "id": order.id,
        "order_source": order.order_source,
        "side": order.side,
        "status": order.status,
        "requested_at": order.requested_at,
        "quantity": order.quantity,
        "limit_price": order.limit_price,
        "fills": [_serialize_fill(fill) for fill in sorted(order.fills, key=lambda value: value.filled_at)],
        "lineage": _serialize_lineage(order),
    }


def _artifact_timestamp(instance: Any) -> datetime | None:
    for attr_name in ("observed_at", "published_at", "as_of", "as_of_data_time", "effective_from"):
        value = getattr(instance, attr_name, None)
        if value is not None:
            return value
    return None


def _artifact_payload(evidence_type: str, instance: Any) -> dict[str, Any]:
    if evidence_type == "market_bar":
        return {
            "open_price": instance.open_price,
            "high_price": instance.high_price,
            "low_price": instance.low_price,
            "close_price": instance.close_price,
            "volume": instance.volume,
            "amount": instance.amount,
            "turnover_rate": instance.turnover_rate,
            "raw_payload": instance.raw_payload,
        }
    if evidence_type == "news_item":
        return {
            "headline": instance.headline,
            "summary": instance.summary,
            "published_at": instance.published_at,
            "raw_payload": instance.raw_payload,
        }
    if evidence_type == "feature_snapshot":
        return {
            "feature_set_name": instance.feature_set_name,
            "feature_set_version": instance.feature_set_version,
            "feature_values": instance.feature_values,
            "upstream_refs": instance.upstream_refs,
        }
    if evidence_type == "model_result":
        return {
            "predicted_direction": instance.predicted_direction,
            "expected_return": instance.expected_return,
            "confidence_score": instance.confidence_score,
            "driver_factors": instance.driver_factors,
            "risk_factors": instance.risk_factors,
            "result_payload": instance.result_payload,
        }
    if evidence_type == "sector_membership":
        return {
            "stock_symbol": instance.stock.symbol,
            "sector_code": instance.sector.sector_code,
            "sector_name": instance.sector.name,
            "effective_from": instance.effective_from,
            "effective_to": instance.effective_to,
            "is_primary": instance.is_primary,
            "membership_payload": instance.membership_payload,
        }
    return {}


def _artifact_label(evidence_type: str, instance: Any) -> str:
    if evidence_type == "market_bar":
        return f"{instance.stock.symbol} {instance.timeframe} {instance.observed_at.date()}"
    if evidence_type == "news_item":
        return instance.headline
    if evidence_type == "feature_snapshot":
        return f"{instance.feature_set_name}:{instance.feature_set_version}"
    if evidence_type == "model_result":
        return f"{instance.model_run.model_version.registry.name} {instance.forecast_horizon_days}d"
    if evidence_type == "sector_membership":
        return f"{instance.stock.symbol} -> {instance.sector.name}"
    return evidence_type


def _mapping_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]


PLACEHOLDER_FUSION_HEADLINE = "用于汇总价格、事件与降级状态的融合层。"
LEGACY_SUPPORTING_CONTEXT = "价格趋势、确认项和事件冲突共同构成当前 Phase 2 规则基线的结构化输入。"
DEGRADE_FLAG_DISPLAY = {
    "missing_news_evidence": "近期缺少新增事件证据，当前更多依赖价格趋势观察。",
    "event_conflict_high": "价格与事件方向冲突较高，系统已主动下调对外表达。",
    "market_data_stale": "最新行情刷新偏旧，短线结论需要谨慎使用。",
}


def _clean_display_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _is_internal_explanatory_text(value: Any) -> bool:
    text = _clean_display_text(value)
    if not text:
        return True
    return text == PLACEHOLDER_FUSION_HEADLINE or text == LEGACY_SUPPORTING_CONTEXT or "Phase 2 规则基线" in text


def _display_ready_text(value: Any) -> str | None:
    text = _clean_display_text(value)
    if not text or _is_internal_explanatory_text(text):
        return None
    return text


def _display_ready_list(value: Any) -> list[str]:
    return [text for item in _string_list(value) if (text := _display_ready_text(item))]


def _humanize_degrade_flag(flag: str) -> str:
    cleaned = _clean_display_text(flag)
    if not cleaned:
        return ""
    return DEGRADE_FLAG_DISPLAY.get(cleaned, cleaned.replace("_", " "))


def _dedupe_text_items(items: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for item in items:
        normalized = _clean_display_text(item)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _factor_headline_fallback(
    factor_key: str,
    *,
    raw_value: Mapping[str, Any],
    recommendation_direction: str,
    degrade_flags: list[str],
) -> str:
    direction = str(raw_value.get("direction") or "")
    evidence_count = raw_value.get("evidence_count")
    conflict_ratio = raw_value.get("conflict_ratio")
    if factor_key == "price_baseline":
        if direction == "positive":
            return "近端价格趋势仍偏强，量价确认暂未转弱。"
        if direction == "negative":
            return "价格趋势已经转弱，短线确认项同步回落。"
        return "价格趋势暂未形成单边优势，仍需等待新的量价确认。"
    if factor_key == "news_event":
        if isinstance(evidence_count, (int, float)) and evidence_count <= 0:
            return "近期缺少新增高置信事件，当前更多依赖价格趋势观察。"
        if isinstance(conflict_ratio, (int, float)) and float(conflict_ratio) >= 0.45:
            return "近期事件正负并存且冲突较高，暂时不适合放大解读。"
        if direction == "positive":
            return "近期公告与行业催化偏正向，正在为价格趋势补充证据。"
        if direction == "negative":
            return "近期负向公告或行业扰动增多，事件层开始压制判断。"
        return "事件层暂未形成一致方向，更多用于验证风险是否扩大。"
    if factor_key in {"manual_review_layer", "llm_assessment"}:
        return "人工研究结论会单独展示，当前只作为补充解释，不直接进入量化评分。"
    if "market_data_stale" in degrade_flags:
        return "最新行情刷新偏旧，当前结论先保留在观察区间。"
    if "event_conflict_high" in degrade_flags:
        return "价格与事件信号分歧较大，系统先下调对外表达。"
    if "missing_news_evidence" in degrade_flags:
        return "近期缺少新增事件证据，当前主要依赖价格趋势延续。"
    if recommendation_direction == "buy":
        return "价格与事件暂时同向，综合后维持偏积极观察。"
    if recommendation_direction in {"reduce", "risk_alert"}:
        return "综合价格与事件后，当前更适合偏谨慎处理。"
    return "价格与事件综合后暂未形成可放大的单边结论。"


def _factor_risk_fallback(
    factor_key: str,
    *,
    raw_value: Mapping[str, Any],
    degrade_flags: list[str],
) -> str | None:
    conflict_ratio = raw_value.get("conflict_ratio")
    if factor_key == "price_baseline":
        return "若 10 日与 20 日动量继续下行，价格基线会优先转弱。"
    if factor_key == "news_event":
        if isinstance(conflict_ratio, (int, float)) and float(conflict_ratio) >= 0.35:
            return "事件冲突仍偏高，新增负面消息会更快触发降级。"
        return "若后续事件方向反转，事件层会率先削弱当前判断。"
    if factor_key in {"manual_review_layer", "llm_assessment"}:
        return "人工研究仍需补充正式记录后才能作为稳定参考。"
    if degrade_flags:
        return _humanize_degrade_flag(degrade_flags[0])
    return "如果价格与事件继续背离，综合层会优先收缩对外表达。"


def _build_display_factor_card(
    factor_key: str,
    *,
    payload_card: Mapping[str, Any],
    raw_value: Mapping[str, Any],
    recommendation_direction: str,
    degrade_flags: list[str],
) -> dict[str, Any]:
    return {
        "factor_key": factor_key,
        "score": payload_card.get("score", raw_value.get("score")),
        "direction": payload_card.get("direction", raw_value.get("direction")),
        "headline": (
            _display_ready_text(payload_card.get("headline"))
            or next(
                (text for item in raw_value.get("drivers") or [] if (text := _display_ready_text(item))),
                None,
            )
            or _factor_headline_fallback(
                factor_key,
                raw_value=raw_value,
                recommendation_direction=recommendation_direction,
                degrade_flags=degrade_flags,
            )
        ),
        "risk_note": (
            _display_ready_text(payload_card.get("risk_note"))
            or next(
                (text for item in raw_value.get("risks") or [] if (text := _display_ready_text(item))),
                None,
            )
            or _factor_risk_fallback(
                factor_key,
                raw_value=raw_value,
                degrade_flags=degrade_flags,
            )
        ),
        "status": payload_card.get("status", raw_value.get("status")),
    }


def _build_supporting_context(
    *,
    price_factor: Mapping[str, Any],
    news_factor: Mapping[str, Any],
    manual_review_factor: Mapping[str, Any],
) -> list[str]:
    supporting_context: list[str] = []
    if price_factor:
        supporting_context.append("价格层仍是当前判断的主轴，近期趋势和量价确认决定了大部分方向。")
    if news_factor:
        evidence_count = news_factor.get("evidence_count")
        conflict_ratio = news_factor.get("conflict_ratio")
        if isinstance(evidence_count, (int, float)) and evidence_count <= 0:
            supporting_context.append("近期没有新增高置信事件，当前更多依赖价格趋势是否延续。")
        elif isinstance(conflict_ratio, (int, float)) and float(conflict_ratio) >= 0.35:
            supporting_context.append("事件层存在正负并存的情况，需要继续观察冲突是否扩大。")
        else:
            supporting_context.append("事件层主要用于确认价格趋势是否得到新的公告或行业催化支撑。")
    if manual_review_factor.get("status"):
        supporting_context.append("人工研究结论单独展示，当前只作为补充解释，不直接改变量化评分。")
    return supporting_context


def _build_conflicts(
    *,
    payload_conflicts: list[str],
    news_factor: Mapping[str, Any],
    degrade_flags: list[str],
) -> list[str]:
    conflicts: list[str] = []
    conflict_ratio = news_factor.get("conflict_ratio")
    if isinstance(conflict_ratio, (float, int)) and conflict_ratio > 0:
        conflicts.append(f"新闻事件冲突度 {float(conflict_ratio):.0%}。")
    conflicts.extend(_humanize_degrade_flag(flag) for flag in degrade_flags if _humanize_degrade_flag(flag))
    for item in payload_conflicts:
        normalized = _display_ready_text(item)
        if normalized in DEGRADE_FLAG_DISPLAY:
            conflicts.append(DEGRADE_FLAG_DISPLAY[normalized])
        elif normalized:
            conflicts.append(normalized)
    return _dedupe_text_items(conflicts)


def _build_core_quant(
    recommendation: Recommendation,
    *,
    model_version: ModelVersion,
    payload: dict[str, Any],
    factor_breakdown: dict[str, Any],
) -> dict[str, Any]:
    evidence_layer = payload.get("evidence") if isinstance(payload.get("evidence"), Mapping) else {}
    factor_cards = _mapping_list(evidence_layer.get("factor_cards")) if isinstance(evidence_layer, Mapping) else []
    fusion_card = next(
        (
            card
            for card in factor_cards
            if isinstance(card, Mapping) and str(card.get("factor_key")) == "fusion"
        ),
        {},
    )
    fallback_score = fusion_card.get("score", factor_breakdown.get("fusion", {}).get("score"))
    if payload.get("core_quant"):
        core_quant = dict(payload["core_quant"])
        core_quant.setdefault("score", fallback_score)
        core_quant.setdefault("score_scale", "phase2_rule_baseline_score")
        core_quant.setdefault("direction", recommendation.direction)
        core_quant.setdefault("confidence_bucket", recommendation.confidence_label)
        core_quant.setdefault("target_horizon_label", phase2_target_horizon_label())
        core_quant.setdefault("horizon_min_days", recommendation.horizon_min_days)
        core_quant.setdefault("horizon_max_days", recommendation.horizon_max_days)
        core_quant.setdefault("as_of_time", recommendation.as_of_data_time)
        core_quant.setdefault("available_time", recommendation.generated_at)
        core_quant.setdefault("model_version", model_version.version)
        core_quant.setdefault("policy_version", str(payload.get("policy", "evidence-first")))
        return core_quant

    return {
        "score": fallback_score,
        "score_scale": "phase2_rule_baseline_score",
        "direction": recommendation.direction,
        "confidence_bucket": recommendation.confidence_label,
        "target_horizon_label": phase2_target_horizon_label(),
        "horizon_min_days": recommendation.horizon_min_days,
        "horizon_max_days": recommendation.horizon_max_days,
        "as_of_time": recommendation.as_of_data_time,
        "available_time": recommendation.generated_at,
        "model_version": model_version.version,
        "policy_version": str(payload.get("policy", "evidence-first")),
    }


def _build_evidence_layer(
    recommendation: Recommendation,
    *,
    model_version: ModelVersion,
    prompt_version: PromptVersion,
    payload: dict[str, Any],
    factor_breakdown: dict[str, Any],
) -> dict[str, Any]:
    payload_evidence = payload.get("evidence") if isinstance(payload.get("evidence"), Mapping) else {}
    degrade_flags = _string_list(
        payload_evidence.get("degrade_flags")
        or factor_breakdown.get("fusion", {}).get("active_degrade_flags", [])
    )
    payload_factor_card_map = {
        str(card.get("factor_key")): card
        for card in _mapping_list(payload_evidence.get("factor_cards"))
        if card.get("factor_key")
    }
    recommendation_direction = str(recommendation.direction or "")
    factor_keys = list(factor_breakdown.keys()) + [
        key for key in payload_factor_card_map if key not in factor_breakdown
    ]
    factor_cards = [
        _build_display_factor_card(
            str(key),
            payload_card=payload_factor_card_map.get(str(key), {}),
            raw_value=dict(factor_breakdown.get(str(key), {}))
            if isinstance(factor_breakdown.get(str(key)), Mapping)
            else {},
            recommendation_direction=recommendation_direction,
            degrade_flags=degrade_flags,
        )
        for key in factor_keys
    ]
    factor_card_map = {
        str(card.get("factor_key")): card
        for card in factor_cards
        if isinstance(card, Mapping) and card.get("factor_key")
    }
    price_factor = factor_breakdown.get("price_baseline", {})
    news_factor = factor_breakdown.get("news_event", {})
    manual_review_factor = factor_breakdown.get(
        "manual_review_layer",
        factor_breakdown.get("llm_assessment", {}),
    )
    supporting_context = _build_supporting_context(
        price_factor=price_factor if isinstance(price_factor, Mapping) else {},
        news_factor=news_factor if isinstance(news_factor, Mapping) else {},
        manual_review_factor=manual_review_factor if isinstance(manual_review_factor, Mapping) else {},
    )
    conflicts = _build_conflicts(
        payload_conflicts=_string_list(payload_evidence.get("conflicts")),
        news_factor=news_factor if isinstance(news_factor, Mapping) else {},
        degrade_flags=degrade_flags,
    )
    derived_primary_drivers = _dedupe_text_items(
        _display_ready_list(payload_evidence.get("primary_drivers"))
        + [
            str(card.get("headline"))
            for card in factor_cards
            if isinstance(card, Mapping)
            and str(card.get("factor_key")) in {"price_baseline", "news_event", "fusion"}
            and _display_ready_text(card.get("headline"))
        ]
    )[:3]

    source_links = [
        str(item)
        for item in (
            getattr(recommendation, "source_uri", None),
            getattr(model_version, "source_uri", None),
            getattr(prompt_version, "source_uri", None),
        )
        if item
    ]

    if payload.get("evidence"):
        evidence = dict(payload["evidence"])
        evidence["primary_drivers"] = derived_primary_drivers
        evidence["supporting_context"] = supporting_context
        evidence["conflicts"] = conflicts
        evidence["factor_cards"] = factor_cards
        evidence["degrade_flags"] = _string_list(evidence.get("degrade_flags")) or degrade_flags
        evidence.setdefault("data_freshness", f"当前分析基于 {recommendation.as_of_data_time.isoformat()} 的数据快照生成。")
        evidence.setdefault("source_links", source_links)
        return evidence

    return {
        "primary_drivers": derived_primary_drivers,
        "supporting_context": supporting_context,
        "conflicts": conflicts,
        "degrade_flags": degrade_flags,
        "data_freshness": f"当前分析基于 {recommendation.as_of_data_time.isoformat()} 的数据快照生成。",
        "source_links": source_links,
        "factor_cards": factor_cards,
    }


def _build_risk_layer(
    recommendation: Recommendation,
    *,
    payload: dict[str, Any],
    reverse_risks: list[str],
    downgrade_conditions: list[str],
    validation_status: str,
    validation_note: str | None,
) -> dict[str, Any]:
    if payload.get("risk"):
        risk = dict(payload["risk"])
        coverage_gaps = list(risk.get("coverage_gaps") or [])
        if recommendation.evidence_status != "sufficient" and not any("证据状态" in item for item in coverage_gaps):
            coverage_gaps.append("当前证据状态不是 fully sufficient，系统已保留降级或保守表达。")
        if validation_status != "verified" and not coverage_gaps:
            coverage_gaps.append(validation_note or "历史验证仍处于迁移重建阶段。")
        risk.setdefault("risk_flags", reverse_risks)
        risk.setdefault("downgrade_conditions", downgrade_conditions)
        risk.setdefault("invalidators", downgrade_conditions[:3])
        risk["coverage_gaps"] = coverage_gaps
        return risk

    coverage_gaps: list[str] = []
    if recommendation.evidence_status != "sufficient":
        coverage_gaps.append("当前证据状态不是 fully sufficient，系统已保留降级或保守表达。")
    if validation_status != "verified":
        coverage_gaps.append(validation_note or "历史验证仍处于迁移重建阶段。")

    return {
        "risk_flags": reverse_risks,
        "downgrade_conditions": downgrade_conditions,
        "invalidators": downgrade_conditions[:3],
        "coverage_gaps": coverage_gaps,
    }


def _build_historical_validation(
    recommendation: Recommendation,
    *,
    payload: dict[str, Any],
    validation_status: str,
    validation_note: str | None,
    artifact_root: Any = None,
) -> dict[str, Any]:
    primary_model_result_key = payload.get("primary_model_result_key")
    default_manifest_id = f"rolling-validation:{primary_model_result_key}" if primary_model_result_key else None
    default_metrics_artifact_id = f"validation-metrics:{primary_model_result_key}" if primary_model_result_key else None
    default_window_definition = f"{recommendation.horizon_min_days}-{recommendation.horizon_max_days} 个交易日（研究窗口待批准）"

    if payload.get("historical_validation"):
        historical_validation = dict(payload["historical_validation"])
        default_artifact_type = (
            "validation_metrics"
            if str(historical_validation.get("artifact_id") or default_metrics_artifact_id).startswith("validation-metrics:")
            else "rolling_validation"
        )
        historical_validation.setdefault("artifact_type", default_artifact_type)
        historical_validation.setdefault(
            "artifact_id",
            default_metrics_artifact_id if default_metrics_artifact_id else primary_model_result_key,
        )
        historical_validation.setdefault("manifest_id", default_manifest_id)
    else:
        historical_validation = {
            "status": validation_status,
            "note": validation_note,
            "artifact_type": "validation_metrics" if default_metrics_artifact_id else "rolling_validation",
            "artifact_id": default_metrics_artifact_id if default_metrics_artifact_id else primary_model_result_key,
            "manifest_id": default_manifest_id,
            "artifact_generated_at": recommendation.generated_at,
            "label_definition": "research_rebuild_pending",
            "window_definition": default_window_definition,
            "benchmark_definition": "pending_rebuild",
            "cost_definition": None,
            "metrics": {},
        }

    historical_validation.setdefault("artifact_generated_at", recommendation.generated_at)
    historical_validation.setdefault("window_definition", default_window_definition)
    historical_validation.setdefault("metrics", {})

    manifest = read_manifest_if_exists(historical_validation.get("manifest_id"), root=artifact_root)
    metrics_artifact_id = payload.get("validation_metrics_artifact_id")
    if historical_validation.get("artifact_type") == "validation_metrics":
        metrics_artifact_id = historical_validation.get("artifact_id") or metrics_artifact_id
    if metrics_artifact_id is None:
        metrics_artifact_id = default_metrics_artifact_id
    metrics_artifact = read_validation_metrics_if_exists(metrics_artifact_id, root=artifact_root)

    if manifest is not None:
        historical_validation.setdefault("artifact_generated_at", manifest.generated_at)
        historical_validation.setdefault("label_definition", manifest.label_definition)
        historical_validation.setdefault("benchmark_definition", manifest.benchmark_definition)
        historical_validation.setdefault("cost_definition", manifest.cost_definition)
        historical_validation.setdefault(
            "window_definition",
            f"{manifest.rebalance_definition} / {manifest.label_definition}",
        )
    if metrics_artifact is not None:
        historical_validation.setdefault("artifact_type", "validation_metrics")
        historical_validation.setdefault("artifact_id", metrics_artifact.artifact_id)
        historical_validation["metrics"] = {
            **historical_validation.get("metrics", {}),
            "sample_count": metrics_artifact.sample_count,
            "rank_ic_mean": metrics_artifact.rank_ic_mean,
            "rank_ic_std": metrics_artifact.rank_ic_std,
            "rank_ic_ir": metrics_artifact.rank_ic_ir,
            "ic_mean": metrics_artifact.ic_mean,
            "bucket_spread_mean": metrics_artifact.bucket_spread_mean,
            "bucket_spread_std": metrics_artifact.bucket_spread_std,
            "positive_excess_rate": metrics_artifact.positive_excess_rate,
            "turnover_mean": metrics_artifact.turnover_mean,
            "coverage_ratio": metrics_artifact.coverage_ratio,
        }
    metrics = historical_validation.get("metrics") or {}
    normalized_status, normalized_note = normalize_product_validation_status(
        artifact_type=str(historical_validation.get("artifact_type", "rolling_validation")),
        status=historical_validation.get("status", validation_status),
        note=historical_validation.get("note", validation_note),
        artifact_id=historical_validation.get("artifact_id"),
        manifest_id=historical_validation.get("manifest_id"),
        benchmark_definition=historical_validation.get("benchmark_definition"),
        cost_definition=historical_validation.get("cost_definition"),
        sample_count=metrics.get("sample_count"),
        coverage_ratio=metrics.get("coverage_ratio"),
        turnover_mean=metrics.get("turnover_mean"),
    )
    historical_validation["status"] = normalized_status
    historical_validation["note"] = normalized_note
    return historical_validation


def _metric_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _cap_direction(direction: str, *, ceiling: str) -> str:
    ranking = {
        "risk_alert": 0,
        "reduce": 1,
        "watch": 2,
        "buy": 3,
    }
    direction_rank = ranking.get(direction, ranking["risk_alert"])
    ceiling_rank = ranking.get(ceiling, ranking["risk_alert"])
    return ceiling if direction_rank > ceiling_rank else direction


def _build_claim_gate(
    recommendation: Recommendation,
    *,
    validation_status: str,
    validation_note: str | None,
    historical_validation: Mapping[str, Any],
) -> dict[str, Any]:
    metrics = historical_validation.get("metrics") if isinstance(historical_validation.get("metrics"), Mapping) else {}
    sample_count_value = _metric_number(metrics.get("sample_count"))
    sample_count = int(sample_count_value) if sample_count_value is not None else None
    coverage_ratio = _metric_number(metrics.get("coverage_ratio"))
    artifact_id = historical_validation.get("artifact_id")
    manifest_id = historical_validation.get("manifest_id")

    blockers: list[str] = []
    if validation_status != STATUS_VERIFIED:
        blockers.append(f"历史验证状态当前为 {validation_status}，尚未进入 verified。")
    if sample_count is None:
        blockers.append("历史验证缺少样本量口径。")
    elif sample_count < 20:
        blockers.append(f"历史验证样本量仅 {sample_count} 条，未达到 20 条样本的公开结论门槛。")
    if coverage_ratio is None:
        blockers.append("历史验证缺少覆盖率口径。")
    elif coverage_ratio < 0.6:
        blockers.append(f"历史验证覆盖率仅 {coverage_ratio:.0%}，未达到 60% 覆盖门槛。")
    if not artifact_id:
        blockers.append("当前缺少可追溯的验证 artifact。")
    if not manifest_id:
        blockers.append("当前缺少可追溯的验证 manifest。")

    ready_for_claim = (
        validation_status == STATUS_VERIFIED
        and sample_count is not None
        and sample_count >= 20
        and coverage_ratio is not None
        and coverage_ratio >= 0.6
        and bool(artifact_id)
        and bool(manifest_id)
    )
    has_observation_floor = (
        validation_status in {STATUS_PENDING_REBUILD, STATUS_RESEARCH_CANDIDATE, STATUS_VERIFIED}
        and bool(artifact_id)
        and bool(manifest_id)
        and sample_count is not None
        and sample_count >= 3
    )

    if ready_for_claim:
        status = "claim_ready"
        public_direction = recommendation.direction
        headline = "当前结论已达到可公开引用的验证门槛"
        note = "历史验证状态、样本量和覆盖率已满足当前展示门槛，可以保留方向性表述。"
    elif has_observation_floor and validation_status != STATUS_SYNTHETIC_DEMO:
        status = "observe_only"
        public_direction = _cap_direction(recommendation.direction, ceiling="watch")
        headline = "历史验证仍在补齐，当前结论只适合继续观察"
        note = (
            validation_note
            or "已有基础验证产物，但验证状态或样本充分度尚未达到公开给出强方向结论的门槛。"
        )
    else:
        status = "insufficient_validation"
        public_direction = _cap_direction(recommendation.direction, ceiling="risk_alert")
        headline = "验证证据不足，当前只应作为风险提示"
        note = validation_note or "缺少可引用的历史验证产物或基础覆盖信息，当前不应放大方向性结论。"

    return {
        "status": status,
        "headline": headline,
        "note": note,
        "public_direction": public_direction,
        "blocking_reasons": blockers,
        "sample_count": sample_count,
        "coverage_ratio": coverage_ratio,
    }


def _manual_llm_review_fallback(
    recommendation: Recommendation,
    *,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if payload.get("manual_llm_review"):
        manual_review = dict(payload["manual_llm_review"])
        manual_review_status = str(manual_review.get("status") or "manual_trigger_required")
        manual_review.setdefault("status", manual_review_status)
        manual_review.setdefault("trigger_mode", "manual")
        manual_review.setdefault("model_label", "Codex/GPT manual review")
        manual_review.setdefault("requested_at", None)
        manual_review.setdefault("generated_at", None)
        manual_review.setdefault("summary", PHASE2_MANUAL_REVIEW_NOTE)
        manual_review.setdefault("risks", [])
        manual_review.setdefault("disagreements", [])
        manual_review.setdefault("artifact_id", None)
        manual_review.setdefault("question", None)
        manual_review.setdefault("raw_answer", None)
        manual_review.setdefault("request_id", None)
        manual_review.setdefault("request_key", None)
        manual_review.setdefault("executor_kind", None)
        manual_review.setdefault("status_note", None)
        manual_review.setdefault("review_verdict", None)
        manual_review.setdefault("decision_note", None)
        manual_review.setdefault("stale_reason", None)
        manual_review.setdefault("citations", [])
        manual_review.setdefault(
            "source_packet",
            [str(payload.get("primary_model_result_key"))] if payload.get("primary_model_result_key") else [],
        )
        if manual_review_status == "manual_trigger_required" and manual_review.get("generated_at") is None:
            manual_review["risks"] = []
            manual_review["disagreements"] = []
        return manual_review

    return {
        "status": "manual_trigger_required",
        "trigger_mode": "manual",
        "model_label": "Codex/GPT manual review",
        "requested_at": None,
        "generated_at": None,
        "summary": PHASE2_MANUAL_REVIEW_NOTE,
        "risks": [],
        "disagreements": [],
        "source_packet": [str(payload.get("primary_model_result_key"))] if payload.get("primary_model_result_key") else [],
        "artifact_id": None,
        "question": None,
        "raw_answer": None,
        "request_id": None,
        "request_key": None,
        "executor_kind": None,
        "status_note": None,
        "review_verdict": None,
        "decision_note": None,
        "stale_reason": None,
        "citations": [],
    }


def _build_manual_llm_review(
    recommendation: Recommendation,
    *,
    payload: dict[str, Any],
    historical_validation: dict[str, Any],
    artifact_root: Any = None,
) -> dict[str, Any]:
    session = object_session(recommendation)
    if session is None:
        return _manual_llm_review_fallback(recommendation, payload=payload)
    return build_manual_llm_review_projection(
        session,
        recommendation,
        payload=payload,
        historical_validation=historical_validation,
        artifact_root=artifact_root,
    )


def _legacy_applicable_period(
    *,
    historical_validation: Mapping[str, Any],
    recommendation: Recommendation,
) -> str:
    return str(
        historical_validation.get("window_definition")
        or f"{recommendation.horizon_min_days}-{recommendation.horizon_max_days} 个交易日（研究窗口待批准）"
    )


def _legacy_core_drivers(
    *,
    evidence_layer: Mapping[str, Any],
    recommendation: Recommendation,
) -> list[str]:
    primary_drivers = [str(item) for item in evidence_layer.get("primary_drivers", []) if item]
    return primary_drivers or list(recommendation.core_drivers or [])


def _legacy_reverse_risks(
    *,
    risk_layer: Mapping[str, Any],
    recommendation: Recommendation,
) -> list[str]:
    risk_flags = [str(item) for item in risk_layer.get("risk_flags", []) if item]
    return risk_flags or list(recommendation.risk_flags or [])


def _legacy_downgrade_conditions(
    *,
    risk_layer: Mapping[str, Any],
    payload: dict[str, Any],
) -> list[str]:
    return [str(item) for item in (risk_layer.get("downgrade_conditions") or payload.get("downgrade_conditions") or []) if item]


def _legacy_factor_breakdown(
    *,
    evidence_layer: Mapping[str, Any],
    manual_llm_review: Mapping[str, Any],
    payload_factor_breakdown: Mapping[str, Any],
) -> dict[str, Any]:
    factor_cards = {
        str(card.get("factor_key")): card
        for card in _mapping_list(evidence_layer.get("factor_cards"))
        if card.get("factor_key")
    }
    degrade_flags = _string_list(evidence_layer.get("degrade_flags"))
    compat: dict[str, Any] = {}
    for factor_key in ("price_baseline", "news_event", "llm_assessment", "fusion"):
        payload_card = payload_factor_breakdown.get(factor_key)
        if not isinstance(payload_card, Mapping):
            payload_card = {}
        factor_card = factor_cards.get(
            factor_key,
            factor_cards.get("manual_review_layer", {}) if factor_key == "llm_assessment" else {},
        )
        compat_card: dict[str, Any] = {
            "score": factor_card.get("score", payload_card.get("score")),
            "direction": factor_card.get("direction", payload_card.get("direction")),
            "drivers": [factor_card["headline"]] if factor_card.get("headline") else list(payload_card.get("drivers") or []),
            "risks": [factor_card["risk_note"]] if factor_card.get("risk_note") else list(payload_card.get("risks") or []),
            "status": factor_card.get("status", payload_card.get("status")),
        }
        if factor_key != "fusion":
            compat_card["weight"] = payload_card.get("weight")
        if factor_key == "news_event":
            compat_card["conflict_ratio"] = payload_card.get("conflict_ratio")
        if factor_key == "llm_assessment":
            compat_card["weight"] = 0.0
            compat_card["status"] = manual_llm_review.get("status", compat_card.get("status"))
            compat_card["calibration"] = payload_card.get("calibration")
        if factor_key == "fusion":
            compat_card["active_degrade_flags"] = degrade_flags or list(payload_card.get("active_degrade_flags") or [])
            compat_card["confidence_score"] = payload_card.get("confidence_score")
            compat_card["conflict_penalty"] = payload_card.get("conflict_penalty")
            compat_card["stale_penalty"] = payload_card.get("stale_penalty")
            compat_card["evidence_gap_penalty"] = payload_card.get("evidence_gap_penalty")
        compat[factor_key] = compat_card
    return compat


def _legacy_validation_snapshot(
    *,
    historical_validation: Mapping[str, Any],
    validation_status: str,
    validation_note: str | None,
) -> dict[str, Any]:
    metrics = historical_validation.get("metrics")
    sample_count = None
    if isinstance(metrics, Mapping):
        sample_count = metrics.get("sample_count")
    return {
        "status": validation_status,
        "note": validation_note,
        "validation_scheme": historical_validation.get("label_definition"),
        "benchmark_definition": historical_validation.get("benchmark_definition"),
        "cost_definition": historical_validation.get("cost_definition"),
        "artifact_id": historical_validation.get("artifact_id"),
        "manifest_id": historical_validation.get("manifest_id"),
        "sample_count": sample_count,
    }


def _legacy_recommendation_projection(
    *,
    recommendation: Recommendation,
    payload: dict[str, Any],
    factor_breakdown: dict[str, Any],
    validation_status: str,
    validation_note: str | None,
    evidence_layer: Mapping[str, Any],
    risk_layer: Mapping[str, Any],
    historical_validation: Mapping[str, Any],
    manual_llm_review: Mapping[str, Any],
) -> dict[str, Any]:
    applicable_period = _legacy_applicable_period(
        historical_validation=historical_validation,
        recommendation=recommendation,
    )
    core_drivers = _legacy_core_drivers(
        evidence_layer=evidence_layer,
        recommendation=recommendation,
    )
    reverse_risks = _legacy_reverse_risks(
        risk_layer=risk_layer,
        recommendation=recommendation,
    )
    downgrade_conditions = _legacy_downgrade_conditions(
        risk_layer=risk_layer,
        payload=payload,
    )
    legacy_factor_breakdown = _legacy_factor_breakdown(
        evidence_layer=evidence_layer,
        manual_llm_review=manual_llm_review,
        payload_factor_breakdown=factor_breakdown,
    )
    legacy_validation_snapshot = _legacy_validation_snapshot(
        historical_validation=historical_validation,
        validation_status=validation_status,
        validation_note=validation_note,
    )
    return {
        "applicable_period": applicable_period,
        "core_drivers": core_drivers,
        "risk_flags": risk_layer["risk_flags"],
        "reverse_risks": reverse_risks,
        "downgrade_conditions": downgrade_conditions,
        "factor_breakdown": legacy_factor_breakdown,
        "validation_status": validation_status,
        "validation_note": validation_note,
        "validation_snapshot": legacy_validation_snapshot,
    }


def _serialize_recommendation(recommendation: Recommendation, *, artifact_root: Any = None) -> dict[str, Any]:
    model_version = recommendation.model_version
    registry = model_version.registry
    prompt_version = recommendation.prompt_version
    payload = recommendation.recommendation_payload or {}
    validation_status = payload.get("validation_status", STATUS_PENDING_REBUILD)
    validation_note = payload.get("validation_note")
    factor_breakdown = payload.get("factor_breakdown", {})
    confidence_expression = payload.get("confidence_expression", recommendation.confidence_label)
    reverse_risks = [
        str(item)
        for item in (
            payload.get("risk", {}).get("risk_flags")
            or recommendation.risk_flags
            or []
        )
        if item
    ]
    downgrade_conditions = [
        str(item)
        for item in (
            payload.get("risk", {}).get("downgrade_conditions")
            or payload.get("downgrade_conditions")
            or getattr(recommendation, "downgrade_conditions", [])
            or []
        )
        if item
    ]
    core_quant = _build_core_quant(
        recommendation,
        model_version=model_version,
        payload=payload,
        factor_breakdown=factor_breakdown,
    )
    evidence_layer = _build_evidence_layer(
        recommendation,
        model_version=model_version,
        prompt_version=prompt_version,
        payload=payload,
        factor_breakdown=factor_breakdown,
    )
    historical_validation = _build_historical_validation(
        recommendation,
        payload=payload,
        validation_status=validation_status,
        validation_note=validation_note,
        artifact_root=artifact_root,
    )
    validation_status = str(historical_validation.get("status", validation_status))
    validation_note = historical_validation.get("note", validation_note)
    risk_layer = _build_risk_layer(
        recommendation,
        payload=payload,
        reverse_risks=reverse_risks,
        downgrade_conditions=downgrade_conditions,
        validation_status=validation_status,
        validation_note=validation_note,
    )
    manual_llm_review = _build_manual_llm_review(
        recommendation,
        payload=payload,
        historical_validation=historical_validation,
        artifact_root=artifact_root,
    )
    claim_gate = _build_claim_gate(
        recommendation,
        validation_status=validation_status,
        validation_note=validation_note,
        historical_validation=historical_validation,
    )
    legacy_projection = _legacy_recommendation_projection(
        recommendation=recommendation,
        payload=payload,
        factor_breakdown=factor_breakdown,
        validation_status=validation_status,
        validation_note=validation_note,
        evidence_layer=evidence_layer,
        risk_layer=risk_layer,
        historical_validation=historical_validation,
        manual_llm_review=manual_llm_review,
    )

    return {
        "stock": {
            "symbol": recommendation.stock.symbol,
            "name": recommendation.stock.name,
            "exchange": recommendation.stock.exchange,
            "ticker": recommendation.stock.ticker,
        },
        "recommendation": {
            "id": recommendation.id,
            "recommendation_key": recommendation.recommendation_key,
            "direction": recommendation.direction,
            "confidence_label": recommendation.confidence_label,
            "confidence_score": recommendation.confidence_score,
            "confidence_expression": confidence_expression,
            "horizon_min_days": recommendation.horizon_min_days,
            "horizon_max_days": recommendation.horizon_max_days,
            "summary": recommendation.summary,
            "generated_at": recommendation.generated_at,
            "updated_at": recommendation.generated_at,
            "as_of_data_time": recommendation.as_of_data_time,
            "evidence_status": recommendation.evidence_status,
            "degrade_reason": recommendation.degrade_reason,
            "core_quant": core_quant,
            "evidence": evidence_layer,
            "risk": risk_layer,
            "historical_validation": historical_validation,
            "manual_llm_review": manual_llm_review,
            "claim_gate": claim_gate,
            **legacy_projection,
            "lineage": _serialize_lineage(recommendation),
        },
        "model": {
            "name": registry.name,
            "family": registry.family,
            "version": model_version.version,
            "validation_scheme": model_version.validation_scheme,
            "artifact_uri": model_version.artifact_uri,
            "lineage": _serialize_lineage(model_version),
        },
        "prompt": {
            "name": prompt_version.name,
            "version": prompt_version.version,
            "risk_disclaimer": prompt_version.risk_disclaimer,
            "lineage": _serialize_lineage(prompt_version),
        },
    }


def get_latest_recommendation_summary(session: Session, symbol: str) -> dict[str, Any] | None:
    recommendations = session.scalars(
        select(Recommendation)
        .join(Stock)
        .where(Stock.symbol == symbol)
        .options(
            joinedload(Recommendation.stock),
            joinedload(Recommendation.model_version).joinedload(ModelVersion.registry),
            joinedload(Recommendation.prompt_version),
            joinedload(Recommendation.model_run),
        )
        .order_by(*recommendation_recency_ordering())
    ).all()
    history = collapse_recommendation_history(recommendations, limit=1)
    recommendation = history[0] if history else None
    if recommendation is None:
        return None
    bind = session.get_bind()
    artifact_root = artifact_root_from_database_url(bind.url.render_as_string(hide_password=False) if bind else None)
    return _serialize_recommendation(recommendation, artifact_root=artifact_root)


def get_recommendation_trace(session: Session, recommendation_id: int) -> dict[str, Any]:
    recommendation = session.scalar(
        select(Recommendation)
        .where(Recommendation.id == recommendation_id)
        .options(
            joinedload(Recommendation.stock),
            joinedload(Recommendation.model_version).joinedload(ModelVersion.registry),
            joinedload(Recommendation.prompt_version),
            joinedload(Recommendation.model_run),
            selectinload(Recommendation.evidence_links),
            selectinload(Recommendation.paper_orders).selectinload(PaperOrder.fills),
        )
    )
    if recommendation is None:
        raise LookupError(f"Recommendation {recommendation_id} was not found.")

    bind = session.get_bind()
    artifact_root = artifact_root_from_database_url(bind.url.render_as_string(hide_password=False) if bind else None)
    payload = _serialize_recommendation(recommendation, artifact_root=artifact_root)
    evidence_items: list[dict[str, Any]] = []

    for evidence_link in sorted(recommendation.evidence_links, key=lambda item: item.rank):
        model = TRACE_MODEL_MAP[evidence_link.evidence_type]
        artifact = session.get(model, evidence_link.evidence_id)
        if artifact is None:
            continue
        evidence_items.append(
            {
                "evidence_type": evidence_link.evidence_type,
                "record_id": evidence_link.evidence_id,
                "role": evidence_link.role,
                "rank": evidence_link.rank,
                "label": evidence_link.evidence_label or _artifact_label(evidence_link.evidence_type, artifact),
                "snippet": evidence_link.snippet,
                "timestamp": _artifact_timestamp(artifact),
                "lineage": _serialize_lineage(artifact),
                "payload": _artifact_payload(evidence_link.evidence_type, artifact),
            }
        )

    payload["evidence"] = evidence_items
    payload["simulation_orders"] = [
        _serialize_order(order)
        for order in sorted(recommendation.paper_orders, key=lambda item: item.requested_at)
    ]
    return payload
