from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

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
from ashare_evidence.providers import DemoLowCostRouteProvider, EvidenceBundle

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
                "recommendation_id": recommendation.id,
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


def bootstrap_demo_data(session: Session, symbol: str = "600519.SH") -> dict[str, Any]:
    provider = DemoLowCostRouteProvider()
    recommendation = ingest_bundle(session, provider.build_bundle(symbol))
    session.commit()
    trace = get_recommendation_trace(session, recommendation.id)
    return {
        "symbol": symbol,
        "recommendation_id": recommendation.id,
        "evidence_count": len(trace["evidence"]),
        "simulation_order_count": len(trace["simulation_orders"]),
    }


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


def _serialize_recommendation(recommendation: Recommendation) -> dict[str, Any]:
    model_version = recommendation.model_version
    registry = model_version.registry
    prompt_version = recommendation.prompt_version
    payload = recommendation.recommendation_payload or {}
    validation_snapshot = payload.get("validation_snapshot")
    if not validation_snapshot and recommendation.model_run is not None:
        validation_snapshot = recommendation.model_run.metrics_payload
    factor_breakdown = payload.get("factor_breakdown", {})
    reverse_risks = payload.get("reverse_risks", recommendation.risk_flags)
    downgrade_conditions = payload.get("downgrade_conditions", [])
    confidence_expression = payload.get("confidence_expression", recommendation.confidence_label)
    applicable_period = payload.get(
        "applicable_period",
        f"{recommendation.horizon_min_days // 7}-{recommendation.horizon_max_days // 7} 周",
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
            "applicable_period": applicable_period,
            "summary": recommendation.summary,
            "generated_at": recommendation.generated_at,
            "updated_at": recommendation.generated_at,
            "as_of_data_time": recommendation.as_of_data_time,
            "evidence_status": recommendation.evidence_status,
            "degrade_reason": recommendation.degrade_reason,
            "core_drivers": recommendation.core_drivers,
            "risk_flags": recommendation.risk_flags,
            "reverse_risks": reverse_risks,
            "downgrade_conditions": downgrade_conditions,
            "factor_breakdown": factor_breakdown,
            "validation_snapshot": validation_snapshot or {},
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
    recommendation = session.scalar(
        select(Recommendation)
        .join(Stock)
        .where(Stock.symbol == symbol)
        .options(
            joinedload(Recommendation.stock),
            joinedload(Recommendation.model_version).joinedload(ModelVersion.registry),
            joinedload(Recommendation.prompt_version),
            joinedload(Recommendation.model_run),
        )
        .order_by(Recommendation.generated_at.desc())
    )
    if recommendation is None:
        return None
    return _serialize_recommendation(recommendation)


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

    payload = _serialize_recommendation(recommendation)
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
