from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any

from ashare_evidence.models import Recommendation, Stock


def recommendation_recency_ordering(
    *,
    stock_symbol: bool = False,
    stock_id: bool = False,
) -> tuple[Any, ...]:
    ordering: list[Any] = []
    if stock_symbol:
        ordering.append(Stock.symbol.asc())
    if stock_id:
        ordering.append(Recommendation.stock_id.asc())
    ordering.extend(
        [
            Recommendation.as_of_data_time.desc(),
            Recommendation.generated_at.desc(),
            Recommendation.id.desc(),
        ]
    )
    return tuple(ordering)


def recommendation_is_market_data_stale(recommendation: Recommendation) -> bool:
    payload = recommendation.recommendation_payload or {}
    evidence = payload.get("evidence") or {}
    degrade_flags = evidence.get("degrade_flags") or []
    return "market_data_stale" in {str(item) for item in degrade_flags if item}


def _comparable_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def preferred_recommendation_version(records: Iterable[Recommendation]) -> Recommendation | None:
    candidates = list(records)
    if not candidates:
        return None
    non_stale = [item for item in candidates if not recommendation_is_market_data_stale(item)]
    pool = non_stale or candidates
    return max(pool, key=lambda item: (_comparable_datetime(item.generated_at), item.id))


def collapse_recommendation_history(
    records: Iterable[Recommendation],
    *,
    limit: int | None = None,
) -> list[Recommendation]:
    versions_by_as_of: dict[Any, list[Recommendation]] = defaultdict(list)
    for recommendation in records:
        versions_by_as_of[recommendation.as_of_data_time].append(recommendation)

    collapsed = [
        preferred
        for preferred in (
            preferred_recommendation_version(versions)
            for versions in versions_by_as_of.values()
        )
        if preferred is not None
    ]
    collapsed.sort(
        key=lambda item: (
            _comparable_datetime(item.as_of_data_time),
            _comparable_datetime(item.generated_at),
            item.id,
        ),
        reverse=True,
    )
    if limit is not None:
        return collapsed[:limit]
    return collapsed
