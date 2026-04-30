from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from ashare_evidence.dashboard import get_stock_dashboard

TRIGGER_PRICE_SHOCK = "price_shock"
TRIGGER_DIRECTION_SWITCH = "direction_switch"
TRIGGER_CONFIDENCE_COLLAPSE = "confidence_collapse"
TRIGGER_FACTOR_CONFLICT = "factor_conflict"
TRIGGER_MAJOR_ANNOUNCEMENT = "major_announcement"
TRIGGER_WEEKLY_REVIEW = "weekly_review"

PRICE_SHOCK_THRESHOLD = 0.05
CONFIDENCE_COLLAPSE_THRESHOLD = 0.10
FACTOR_CONFLICT_CONFIDENCE_THRESHOLD = 0.4
MAJOR_ANNOUNCEMENT_IMPORTANCE_THRESHOLD = 0.7
DAILY_MAX_PER_SYMBOL = 2
COOLDOWN_DAYS_PER_TYPE = 3


@dataclass
class TriggerEvent:
    trigger_type: str
    symbol: str
    triggered_at: datetime
    detail: str
    meta: dict[str, Any] = field(default_factory=dict)


def check_triggers(
    session: Session,
    *,
    symbol: str,
    artifact_root: str | None = None,
    now: datetime | None = None,
    existing_analyses: list[dict[str, Any]] | None = None,
) -> list[TriggerEvent]:
    triggered_at = now or datetime.now().astimezone()
    try:
        dashboard = get_stock_dashboard(session, symbol)
    except LookupError:
        return []

    triggers: list[TriggerEvent] = []

    triggers.extend(_detect_price_shock(dashboard, symbol, triggered_at))
    triggers.extend(_detect_direction_switch(dashboard, symbol, triggered_at))
    triggers.extend(_detect_confidence_collapse(dashboard, symbol, triggered_at))
    triggers.extend(_detect_factor_conflict(dashboard, symbol, triggered_at))
    triggers.extend(_detect_major_announcement(dashboard, symbol, triggered_at))
    if _is_weekly_review_window(triggered_at):
        triggers.append(_weekly_review_trigger(symbol, triggered_at))

    if not triggers:
        return []

    return _apply_throttle(triggers, existing_analyses or [])


def _detect_price_shock(dashboard: dict[str, Any], symbol: str, triggered_at: datetime) -> list[TriggerEvent]:
    hero = dashboard.get("hero", {})
    day_change = hero.get("day_change_pct")
    if day_change is None:
        return []
    if abs(float(day_change)) >= PRICE_SHOCK_THRESHOLD:
        direction = "上涨" if float(day_change) > 0 else "下跌"
        return [
            TriggerEvent(
                trigger_type=TRIGGER_PRICE_SHOCK,
                symbol=symbol,
                triggered_at=triggered_at,
                detail=f"日涨跌 {direction} {abs(float(day_change)):.1%}，触发价格冲击阈值 ±{PRICE_SHOCK_THRESHOLD:.0%}",
                meta={"day_change_pct": float(day_change), "latest_close": hero.get("latest_close")},
            )
        ]
    return []


def _detect_direction_switch(dashboard: dict[str, Any], symbol: str, triggered_at: datetime) -> list[TriggerEvent]:
    change = dashboard.get("change", {})
    if not change.get("has_previous"):
        return []
    if change.get("change_badge") != "方向切换":
        return []
    prev = change.get("previous_direction", "?")
    curr = dashboard["recommendation"]["direction"]
    return [
        TriggerEvent(
            trigger_type=TRIGGER_DIRECTION_SWITCH,
            symbol=symbol,
            triggered_at=triggered_at,
            detail=f"建议方向从 {prev} 切换到 {curr}",
            meta={"previous_direction": prev, "current_direction": curr},
        )
    ]


def _detect_confidence_collapse(dashboard: dict[str, Any], symbol: str, triggered_at: datetime) -> list[TriggerEvent]:
    change = dashboard.get("change", {})
    if not change.get("has_previous"):
        return []
    reasons = change.get("reasons", [])
    for reason in reasons:
        if "整体置信度较上一版回落" in reason:
            current_conf = float(dashboard["recommendation"]["confidence_score"])
            meta = {"current_confidence": current_conf}
            return [
                TriggerEvent(
                    trigger_type=TRIGGER_CONFIDENCE_COLLAPSE,
                    symbol=symbol,
                    triggered_at=triggered_at,
                    detail=f"置信度显著回落：{reason}",
                    meta=meta,
                )
            ]
    return []


def _detect_factor_conflict(dashboard: dict[str, Any], symbol: str, triggered_at: datetime) -> list[TriggerEvent]:
    reco = dashboard["recommendation"]
    evidence = reco.get("evidence", {})
    factor_cards = evidence.get("factor_cards", [])
    if not factor_cards:
        return []

    positive: list[str] = []
    negative: list[str] = []
    for card in factor_cards:
        direction = str(card.get("direction") or "neutral")
        score = float(card.get("score") or 0)
        if direction == "neutral" or score == 0:
            continue
        if direction == "positive":
            positive.append(card["factor_key"])
        elif direction == "negative":
            negative.append(card["factor_key"])

    if len(positive) >= 1 and len(negative) >= 1 and (len(positive) + len(negative)) >= 2:
        return [
            TriggerEvent(
                trigger_type=TRIGGER_FACTOR_CONFLICT,
                symbol=symbol,
                triggered_at=triggered_at,
                detail=f"因子分歧：看多 {positive} vs 看空 {negative}",
                meta={"positive_factors": positive, "negative_factors": negative},
            )
        ]
    return []


def _detect_major_announcement(dashboard: dict[str, Any], symbol: str, triggered_at: datetime) -> list[TriggerEvent]:
    recent_news = dashboard.get("recent_news", [])
    triggers: list[TriggerEvent] = []
    for item in recent_news:
        payload = item.get("payload") or item.get("raw_payload") or {}
        llm_analysis = payload.get("llm_analysis") if isinstance(payload, dict) else None
        if not isinstance(llm_analysis, dict):
            continue
        importance = float(llm_analysis.get("importance_score") or 0)
        if importance >= MAJOR_ANNOUNCEMENT_IMPORTANCE_THRESHOLD:
            headline = str(item.get("headline") or "")
            triggers.append(
                TriggerEvent(
                    trigger_type=TRIGGER_MAJOR_ANNOUNCEMENT,
                    symbol=symbol,
                    triggered_at=triggered_at,
                    detail=f"重大公告（重要性 {importance:.0%}）：{headline[:80]}",
                    meta={"headline": headline, "importance_score": importance},
                )
            )
    return triggers


def _is_weekly_review_window(now: datetime) -> bool:
    return now.weekday() == 5 and 9 <= now.hour < 11


def _weekly_review_trigger(symbol: str, triggered_at: datetime) -> TriggerEvent:
    return TriggerEvent(
        trigger_type=TRIGGER_WEEKLY_REVIEW,
        symbol=symbol,
        triggered_at=triggered_at,
        detail="周六定时深度复盘",
    )


def _apply_throttle(triggers: list[TriggerEvent], existing: list[dict[str, Any]]) -> list[TriggerEvent]:
    type_counts: dict[str, int] = {}
    latest_by_type: dict[str, datetime] = {}
    for analysis in existing:
        trigger_type = str(analysis.get("trigger_type") or "")
        generated_at_val = analysis.get("generated_at")
        if isinstance(generated_at_val, str):
            generated_at_val = datetime.fromisoformat(generated_at_val)
        if isinstance(generated_at_val, datetime):
            current_latest = latest_by_type.get(trigger_type)
            if current_latest is None or generated_at_val > current_latest:
                latest_by_type[trigger_type] = generated_at_val
        type_counts[trigger_type] = type_counts.get(trigger_type, 0) + 1

    now = datetime.now().astimezone()
    allowed: list[TriggerEvent] = []
    symbol_daily_count = sum(
        1 for a in existing
        if isinstance(a.get("generated_at"), str)
        and datetime.fromisoformat(a["generated_at"]).date() == now.date()
    ) if existing else 0

    for trigger in triggers:
        if symbol_daily_count >= DAILY_MAX_PER_SYMBOL:
            break
        latest = latest_by_type.get(trigger.trigger_type)
        if latest is not None and (now - latest).days < COOLDOWN_DAYS_PER_TYPE:
            continue
        allowed.append(trigger)
        symbol_daily_count += 1
        type_counts[trigger.trigger_type] = type_counts.get(trigger.trigger_type, 0) + 1
        latest_by_type[trigger.trigger_type] = now

    return allowed
