from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ashare_evidence.lineage import build_lineage


@dataclass(frozen=True)
class EvidenceBundle:
    provider_name: str
    symbol: str
    stock: dict[str, Any]
    sectors: list[dict[str, Any]]
    sector_memberships: list[dict[str, Any]]
    market_bars: list[dict[str, Any]]
    news_items: list[dict[str, Any]]
    news_links: list[dict[str, Any]]
    feature_snapshots: list[dict[str, Any]]
    model_registry: dict[str, Any]
    model_version: dict[str, Any]
    prompt_version: dict[str, Any]
    model_run: dict[str, Any]
    model_results: list[dict[str, Any]]
    recommendation: dict[str, Any]
    recommendation_evidence: list[dict[str, Any]]
    paper_portfolios: list[dict[str, Any]]
    paper_orders: list[dict[str, Any]]
    paper_fills: list[dict[str, Any]]


def with_lineage(
    record: dict[str, Any],
    *,
    payload_key: str,
    source_uri: str,
    license_tag: str,
    usage_scope: str = "internal_research",
    redistribution_scope: str = "none",
) -> dict[str, Any]:
    if payload_key not in record:
        raise KeyError(f"Expected payload key '{payload_key}' in record.")
    return {
        **record,
        **build_lineage(
            record,
            source_uri=source_uri,
            license_tag=license_tag,
            usage_scope=usage_scope,
            redistribution_scope=redistribution_scope,
        ),
    }
