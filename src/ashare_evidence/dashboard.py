from __future__ import annotations

from collections import OrderedDict
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from ashare_evidence.models import MarketBar, ModelVersion, NewsEntityLink, Recommendation, SectorMembership, Stock
from ashare_evidence.services import (
    _serialize_recommendation,
    get_recommendation_trace,
)
from ashare_evidence.watchlist import active_watchlist_symbols, reset_watchlist_to_defaults

DIRECTION_LABELS = {
    "buy": "偏积极",
    "watch": "继续观察",
    "reduce": "偏谨慎",
    "risk_alert": "风险提示",
}

FACTOR_LABELS = {
    "price_baseline": "价格基线",
    "news_event": "新闻事件",
    "llm_assessment": "LLM 评估",
    "fusion": "融合评分",
}

GLOSSARY_ENTRIES: list[dict[str, str]] = [
    {
        "term": "滚动验证",
        "plain_explanation": "模型只用过去数据训练，再往未来时间窗口验证，避免把未来信息提前泄露进结果。",
        "why_it_matters": "这是判断建议是否真的经得起实盘时间顺序的核心约束。",
    },
    {
        "term": "价格基线",
        "plain_explanation": "把近 5/10/20 日价格、量能、换手和波动率压缩成一个波段强弱分数。",
        "why_it_matters": "它告诉你当前趋势是否还在延续，通常是最先翻弱的层。",
    },
    {
        "term": "新闻事件因子",
        "plain_explanation": "把公告、调研和行业事件做去重、映射和衰减后，转成正负方向分数。",
        "why_it_matters": "它用来解释建议为什么变化，以及为什么有些利好并没有被系统当真。",
    },
    {
        "term": "冲突度",
        "plain_explanation": "正向和负向事件同时存在时，系统会测算它们互相抵消的程度。",
        "why_it_matters": "冲突度高时，即使有利好，也不应该把建议说得太满。",
    },
    {
        "term": "降级条件",
        "plain_explanation": "当证据不足、数据过旧或冲突过大时，系统会从方向建议退回风险提示。",
        "why_it_matters": "这决定了建议何时失效，而不是只告诉你现在看起来好不好。",
    },
    {
        "term": "LLM 因子上限",
        "plain_explanation": "语言模型只能在结构化证据已经成立时做有限度整合，权重被封顶。",
        "why_it_matters": "这样可以避免用一段看起来流畅的话，把弱证据包装成强结论。",
    },
]


def get_glossary_entries() -> list[dict[str, str]]:
    return list(GLOSSARY_ENTRIES)


def bootstrap_dashboard_demo(session: Session) -> dict[str, Any]:
    return reset_watchlist_to_defaults(session)


def _all_recommendations(session: Session) -> list[Recommendation]:
    return session.scalars(
        select(Recommendation)
        .options(
            joinedload(Recommendation.stock),
            joinedload(Recommendation.model_version).joinedload(ModelVersion.registry),
            joinedload(Recommendation.prompt_version),
            joinedload(Recommendation.model_run),
        )
        .order_by(Recommendation.stock_id.asc(), Recommendation.generated_at.desc())
    ).all()


def _latest_recommendations(session: Session) -> list[Recommendation]:
    latest_by_stock: dict[int, Recommendation] = {}
    for recommendation in _all_recommendations(session):
        latest_by_stock.setdefault(recommendation.stock_id, recommendation)
    return list(latest_by_stock.values())


def _recommendation_history(session: Session, symbol: str, limit: int = 2) -> list[Recommendation]:
    return session.scalars(
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
        .limit(limit)
    ).all()


def _active_memberships(session: Session, stock_id: int, as_of: datetime) -> list[SectorMembership]:
    memberships = session.scalars(
        select(SectorMembership)
        .where(SectorMembership.stock_id == stock_id)
        .options(joinedload(SectorMembership.sector))
    ).all()
    active = [
        membership
        for membership in memberships
        if membership.effective_from <= as_of and (membership.effective_to is None or membership.effective_to >= as_of)
    ]
    active.sort(key=lambda item: (not item.is_primary, item.sector.name))
    return active


def _recent_bars(session: Session, stock_id: int, limit: int = 28) -> list[MarketBar]:
    bars = session.scalars(
        select(MarketBar)
        .where(MarketBar.stock_id == stock_id)
        .order_by(MarketBar.observed_at.desc())
        .limit(limit)
    ).all()
    return list(reversed(bars))


def _recent_news(
    session: Session,
    *,
    stock_id: int,
    sector_ids: list[int],
    as_of: datetime,
    limit: int = 6,
) -> list[dict[str, Any]]:
    links = session.scalars(
        select(NewsEntityLink)
        .options(joinedload(NewsEntityLink.news_item))
        .where(NewsEntityLink.effective_at <= as_of)
        .order_by(NewsEntityLink.effective_at.desc())
    ).all()
    deduped: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
    for link in links:
        if link.stock_id != stock_id and (link.sector_id is None or link.sector_id not in sector_ids):
            continue
        news_item = link.news_item
        dedupe_key = news_item.dedupe_key
        current = deduped.get(dedupe_key)
        payload = {
            "headline": news_item.headline,
            "summary": news_item.summary,
            "published_at": news_item.published_at,
            "impact_direction": link.impact_direction,
            "entity_scope": link.entity_type,
            "relevance_score": link.relevance_score,
            "source_uri": news_item.source_uri,
            "license_tag": news_item.license_tag,
        }
        if current is None or abs(payload["relevance_score"]) > abs(current["relevance_score"]):
            deduped[dedupe_key] = payload
        if len(deduped) >= limit:
            continue
    return list(deduped.values())[:limit]


def _direction_rank(direction: str) -> int:
    return {"buy": 3, "watch": 2, "reduce": 1, "risk_alert": 0}.get(direction, 0)


def _factor_score(summary: dict[str, Any], key: str) -> float:
    return float(summary["recommendation"]["factor_breakdown"].get(key, {}).get("score", 0.0))


def _change_payload(current_summary: dict[str, Any], previous_summary: dict[str, Any] | None) -> dict[str, Any]:
    if previous_summary is None:
        return {
            "has_previous": False,
            "change_badge": "首版",
            "summary": "暂无上一版建议，当前展示的是首个可回溯版本。",
            "reasons": ["后续版本将围绕价格基线、事件冲突和证据充分度来解释变化原因。"],
            "previous_direction": None,
            "previous_confidence_label": None,
            "previous_generated_at": None,
        }

    current_reco = current_summary["recommendation"]
    previous_reco = previous_summary["recommendation"]
    reasons: list[str] = []

    if current_reco["direction"] != previous_reco["direction"]:
        reasons.append(
            f"建议方向从“{DIRECTION_LABELS.get(previous_reco['direction'], previous_reco['direction'])}”调整为“{DIRECTION_LABELS.get(current_reco['direction'], current_reco['direction'])}”。"
        )

    confidence_delta = float(current_reco["confidence_score"]) - float(previous_reco["confidence_score"])
    if abs(confidence_delta) >= 0.05:
        trend = "提升" if confidence_delta > 0 else "回落"
        reasons.append(f"整体置信度较上一版{trend} {abs(confidence_delta):.0%}。")

    for factor_key in ("price_baseline", "news_event", "llm_assessment", "fusion"):
        current_score = _factor_score(current_summary, factor_key)
        previous_score = _factor_score(previous_summary, factor_key)
        delta = current_score - previous_score
        if abs(delta) >= 0.06:
            reasons.append(
                f"{FACTOR_LABELS[factor_key]}分数从 {previous_score:.2f} {'转强' if delta > 0 else '转弱'}到 {current_score:.2f}。"
            )

    current_flags = current_reco["factor_breakdown"].get("fusion", {}).get("active_degrade_flags", [])
    previous_flags = previous_reco["factor_breakdown"].get("fusion", {}).get("active_degrade_flags", [])
    if current_flags != previous_flags:
        if current_flags:
            reasons.append(f"当前新增降级标记：{', '.join(current_flags)}。")
        elif previous_flags:
            reasons.append("上一版的降级标记已经解除，证据重新收敛。")

    if not reasons:
        reasons.append("最新行情和事件更新后，建议仍维持原判断，但强弱细节已有刷新。")

    if current_reco["direction"] == previous_reco["direction"]:
        change_badge = "上修" if confidence_delta > 0.03 else "下修" if confidence_delta < -0.03 else "维持"
    else:
        change_badge = "方向切换"

    return {
        "has_previous": True,
        "change_badge": change_badge,
        "summary": reasons[0],
        "reasons": reasons[:4],
        "previous_direction": previous_reco["direction"],
        "previous_confidence_label": previous_reco["confidence_label"],
        "previous_generated_at": previous_reco["generated_at"],
    }


def _hero_payload(
    *,
    bars: list[MarketBar],
    memberships: list[SectorMembership],
    recommendation: dict[str, Any],
) -> dict[str, Any]:
    latest_bar = bars[-1]
    previous_bar = bars[-2] if len(bars) > 1 else None
    day_change_pct = (
        latest_bar.close_price / previous_bar.close_price - 1 if previous_bar and previous_bar.close_price else 0.0
    )
    return {
        "latest_close": latest_bar.close_price,
        "day_change_pct": round(day_change_pct, 4),
        "latest_volume": latest_bar.volume,
        "turnover_rate": latest_bar.turnover_rate,
        "high_price": latest_bar.high_price,
        "low_price": latest_bar.low_price,
        "sector_tags": [membership.sector.name for membership in memberships],
        "direction_label": DIRECTION_LABELS.get(recommendation["direction"], recommendation["direction"]),
        "last_updated": recommendation["generated_at"],
    }


def _price_chart_payload(bars: list[MarketBar]) -> list[dict[str, Any]]:
    return [
        {
            "observed_at": bar.observed_at,
            "close_price": bar.close_price,
            "volume": bar.volume,
        }
        for bar in bars
    ]


def _risk_panel(summary: dict[str, Any], change: dict[str, Any], recent_news: list[dict[str, Any]]) -> dict[str, Any]:
    recommendation = summary["recommendation"]
    prompt = summary["prompt"]
    items: list[str] = []
    items.extend(recommendation["reverse_risks"][:3])
    if recent_news:
        negative_event = next((item for item in recent_news if item["impact_direction"] == "negative"), None)
        if negative_event is not None:
            items.append(f"最近负向事件：{negative_event['headline']}")
    items.extend(recommendation["downgrade_conditions"][:2])
    deduped_items: list[str] = []
    for item in items:
        if item not in deduped_items:
            deduped_items.append(item)
    headline = (
        "当前建议只在证据继续收敛时成立"
        if recommendation["evidence_status"] == "sufficient"
        else "当前证据不足，优先把它当作风险提示"
    )
    return {
        "headline": headline,
        "items": deduped_items[:5],
        "disclaimer": prompt["risk_disclaimer"],
        "change_hint": change["summary"],
    }


def _follow_up_payload(summary: dict[str, Any], change: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    recommendation = summary["recommendation"]
    evidence_lines = [
        f"{item['label']} | {item['lineage']['source_uri']}"
        for item in evidence[:4]
    ]
    suggested_questions = [
        "如果我只关注未来两周，哪些证据最值得盯？",
        "这条建议最可能因为什么条件而失效？",
        "最近一版建议为什么比上一版更强/更弱？",
        "如果只允许保守跟踪，应该先看哪些风险信号？",
    ]
    copy_prompt = "\n".join(
        [
            "请基于以下结构化证据回答我的追问，不要补充未给出的事实。",
            f"股票：{summary['stock']['name']}（{summary['stock']['symbol']}）",
            f"当前建议：{DIRECTION_LABELS.get(recommendation['direction'], recommendation['direction'])}；{recommendation['confidence_expression']}",
            f"适用周期：{recommendation['applicable_period']}",
            "核心驱动：",
            *[f"- {item}" for item in recommendation["core_drivers"][:3]],
            "主要风险：",
            *[f"- {item}" for item in recommendation["reverse_risks"][:3]],
            f"最近变化：{change['summary']}",
            "关键证据：",
            *[f"- {line}" for line in evidence_lines],
            "请回答这个问题：<在这里替换成你的追问>",
            "回答要求：区分事实与推断，明确失效条件，并指出还需要继续观察的更新时间点。",
        ]
    )
    return {
        "suggested_questions": suggested_questions,
        "copy_prompt": copy_prompt,
        "evidence_packet": evidence_lines,
    }


def list_candidate_recommendations(session: Session, limit: int = 8) -> dict[str, Any]:
    active_symbols = set(active_watchlist_symbols(session))
    if not active_symbols:
        return {
            "generated_at": datetime.now().astimezone(),
            "items": [],
        }
    candidates: list[dict[str, Any]] = []
    for recommendation in _latest_recommendations(session):
        if recommendation.stock.symbol not in active_symbols:
            continue
        summary = _serialize_recommendation(recommendation)
        history = _recommendation_history(session, summary["stock"]["symbol"], limit=2)
        previous_summary = _serialize_recommendation(history[1]) if len(history) > 1 else None
        bars = _recent_bars(session, recommendation.stock_id, limit=21)
        memberships = _active_memberships(session, recommendation.stock_id, recommendation.as_of_data_time)
        latest_bar = bars[-1] if bars else None
        twenty_day_return = (
            latest_bar.close_price / bars[0].close_price - 1
            if latest_bar is not None and len(bars) >= 2 and bars[0].close_price
            else 0.0
        )
        change = _change_payload(summary, previous_summary)
        primary_sector = memberships[0].sector.name if memberships else "未映射"
        reco = summary["recommendation"]
        candidates.append(
            {
                "symbol": summary["stock"]["symbol"],
                "name": summary["stock"]["name"],
                "sector": primary_sector,
                "direction": reco["direction"],
                "direction_label": DIRECTION_LABELS.get(reco["direction"], reco["direction"]),
                "confidence_label": reco["confidence_label"],
                "confidence_score": reco["confidence_score"],
                "summary": reco["summary"],
                "applicable_period": reco["applicable_period"],
                "generated_at": reco["generated_at"],
                "as_of_data_time": reco["as_of_data_time"],
                "last_close": latest_bar.close_price if latest_bar is not None else None,
                "price_return_20d": round(twenty_day_return, 4),
                "why_now": reco["core_drivers"][0] if reco["core_drivers"] else reco["summary"],
                "primary_risk": reco["reverse_risks"][0] if reco["reverse_risks"] else None,
                "change_summary": change["summary"],
                "change_badge": change["change_badge"],
                "evidence_status": reco["evidence_status"],
            }
        )

    candidates.sort(
        key=lambda item: (
            _direction_rank(item["direction"]),
            float(item["confidence_score"]),
            float(item["price_return_20d"]),
        ),
        reverse=True,
    )
    for index, item in enumerate(candidates[:limit], start=1):
        item["rank"] = index
    return {
        "generated_at": datetime.now().astimezone(),
        "items": candidates[:limit],
    }


def get_stock_dashboard(session: Session, symbol: str) -> dict[str, Any]:
    history = _recommendation_history(session, symbol, limit=2)
    if not history:
        raise LookupError(f"No recommendation found for {symbol}.")

    latest = history[0]
    latest_summary = _serialize_recommendation(latest)
    previous_summary = _serialize_recommendation(history[1]) if len(history) > 1 else None
    trace = get_recommendation_trace(session, latest.id)
    bars = _recent_bars(session, latest.stock_id, limit=28)
    memberships = _active_memberships(session, latest.stock_id, latest.as_of_data_time)
    recent_news = _recent_news(
        session,
        stock_id=latest.stock_id,
        sector_ids=[membership.sector_id for membership in memberships],
        as_of=latest.as_of_data_time,
    )
    change = _change_payload(latest_summary, previous_summary)
    trace["hero"] = _hero_payload(
        bars=bars,
        memberships=memberships,
        recommendation=trace["recommendation"],
    )
    trace["price_chart"] = _price_chart_payload(bars)
    trace["recent_news"] = recent_news
    trace["change"] = change
    trace["glossary"] = get_glossary_entries()
    trace["risk_panel"] = _risk_panel(trace, change, recent_news)
    trace["follow_up"] = _follow_up_payload(trace, change, trace["evidence"])
    return trace
