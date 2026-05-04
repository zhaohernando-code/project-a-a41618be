from __future__ import annotations

from collections import OrderedDict
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ashare_evidence.db import align_datetime_timezone
from ashare_evidence.follow_up_prompt import (
    build_evidence_lines,
    build_market_lines,
    build_news_lines,
    build_validation_lines,
)
from ashare_evidence.intraday_market import INTRADAY_MARKET_TIMEFRAME
from ashare_evidence.models import MarketBar, ModelVersion, NewsEntityLink, Recommendation, SectorMembership, Stock
from ashare_evidence.phase2 import phase2_target_horizon_label
from ashare_evidence.recommendation_selection import (
    collapse_recommendation_history,
    recommendation_recency_ordering,
)
from ashare_evidence.research_artifact_store import artifact_root_from_database_url
from ashare_evidence.services import _serialize_recommendation, get_recommendation_trace
from ashare_evidence.watchlist import active_watchlist_symbols

DIRECTION_LABELS = {"buy": "可建仓", "add": "可加仓", "watch": "继续观察", "reduce": "减仓",
    "sell": "建议离场", "risk_alert": "风险提示"}

FACTOR_LABELS = {"price_baseline": "价格基线", "news_event": "新闻事件", "fundamental": "基本面",
    "size_factor": "市值因子", "reversal": "短期反转", "liquidity": "流动性",
    "manual_review_layer": "人工研究层", "llm_assessment": "人工研究兼容壳",
    "fusion": "融合评分"}

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
        "term": "人工研究层",
        "plain_explanation": "语言模型研究结论会保留为独立层，当前需要手动触发，不直接进入主评分。",
        "why_it_matters": "这样可以避免把尚未验证的模型结论直接包装成量化因子。",
    },
]

def get_glossary_entries() -> list[dict[str, str]]:
    return list(GLOSSARY_ENTRIES)

def _artifact_source_classification(*, artifact_id: str | None) -> str:
    return "artifact_backed" if artifact_id else "migration_placeholder"

def _artifact_validation_mode(*, validation_status: str) -> str:
    return "artifact_backed" if validation_status == "verified" else "migration_placeholder"

def _candidate_compat_projection(*, window_definition: str) -> dict[str, str]:
    return {
        "applicable_period": window_definition,
    }

def _all_recommendations(session: Session) -> list[Recommendation]:
    return session.scalars(
        select(Recommendation)
        .options(
            joinedload(Recommendation.stock),
            joinedload(Recommendation.model_version).joinedload(ModelVersion.registry),
            joinedload(Recommendation.prompt_version),
            joinedload(Recommendation.model_run),
        )
        .order_by(*recommendation_recency_ordering(stock_id=True))
    ).all()

def _latest_recommendations(session: Session) -> list[Recommendation]:
    histories_by_stock: dict[int, list[Recommendation]] = {}
    for recommendation in _all_recommendations(session):
        histories_by_stock.setdefault(recommendation.stock_id, []).append(recommendation)
    return [
        collapsed[0]
        for collapsed in (
            collapse_recommendation_history(records, limit=1)
            for records in histories_by_stock.values()
        )
        if collapsed
    ]

def _recommendation_history(session: Session, symbol: str, limit: int = 2) -> list[Recommendation]:
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
    return collapse_recommendation_history(recommendations, limit=limit)

def _active_memberships(session: Session, stock_id: int, as_of: datetime) -> list[SectorMembership]:
    memberships = session.scalars(
        select(SectorMembership)
        .where(SectorMembership.stock_id == stock_id)
        .options(joinedload(SectorMembership.sector))
    ).all()
    active = [
        membership
        for membership in memberships
        if align_datetime_timezone(membership.effective_from, reference=as_of) <= as_of
        and (
            align_datetime_timezone(membership.effective_to, reference=as_of) is None
            or align_datetime_timezone(membership.effective_to, reference=as_of) >= as_of
        )
    ]
    active.sort(key=lambda item: (not item.is_primary, item.sector.name))
    return active

def _recent_bars(session: Session, stock_id: int, limit: int = 28) -> list[MarketBar]:
    from ashare_evidence.market_bar_qa import dedup_daily_bars

    bars = session.scalars(
        select(MarketBar)
        .where(MarketBar.stock_id == stock_id, MarketBar.timeframe == "1d")
        .order_by(MarketBar.observed_at.desc())
        .limit(limit)
    ).all()
    bars = list(reversed(bars))
    deduped = dedup_daily_bars(bars)
    return deduped if len(deduped) < len(bars) else bars

def _today_intraday_bars(session: Session, stock_id: int, daily_bars: list[MarketBar]) -> list[MarketBar]:
    latest_intraday = session.scalar(
        select(MarketBar)
        .where(MarketBar.stock_id == stock_id, MarketBar.timeframe == INTRADAY_MARKET_TIMEFRAME)
        .order_by(MarketBar.observed_at.desc())
        .limit(1)
    )
    if latest_intraday is None:
        return []

    intraday_day = latest_intraday.observed_at.date()
    latest_daily_day = daily_bars[-1].observed_at.date() if daily_bars else None
    if latest_daily_day is not None and intraday_day < latest_daily_day:
        return []

    intraday_bars = session.scalars(
        select(MarketBar)
        .where(
            MarketBar.stock_id == stock_id,
            MarketBar.timeframe == INTRADAY_MARKET_TIMEFRAME,
            MarketBar.observed_at >= datetime.combine(intraday_day, datetime.min.time()),
            MarketBar.observed_at <= latest_intraday.observed_at,
        )
        .order_by(MarketBar.observed_at.asc())
    ).all()
    return list(intraday_bars)

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
    deduped: OrderedDict[str, dict[str, Any]] = OrderedDict()
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

def _list_payload(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []

def _factor_score(summary: dict[str, Any], key: str) -> float:
    evidence = summary["recommendation"].get("evidence", {})
    for card in _list_payload(evidence.get("factor_cards")):
        if card.get("factor_key") == key and card.get("score") is not None:
            return float(card["score"])
    return 0.0


def _active_degrade_flags(recommendation: dict[str, Any]) -> list[str]:
    evidence = recommendation.get("evidence", {})
    return [str(item) for item in _list_payload(evidence.get("degrade_flags")) if item]


def _candidate_window_definition(recommendation: dict[str, Any]) -> str:
    return str(
        recommendation.get("historical_validation", {}).get("window_definition")
        or "研究验证中（历史窗口待重建）"
    )


def _candidate_primary_driver(recommendation: dict[str, Any]) -> str:
    evidence = recommendation.get("evidence", {})
    primary_drivers = evidence.get("primary_drivers") or []
    return str(primary_drivers[0]) if primary_drivers else str(recommendation.get("summary", ""))


def _candidate_primary_risk(recommendation: dict[str, Any]) -> str | None:
    historical_validation = recommendation.get("historical_validation", {})
    metrics = historical_validation.get("metrics", {})
    rank_ic = metrics.get("rank_ic_mean")
    positive_excess_rate = metrics.get("positive_excess_rate")
    if isinstance(rank_ic, (int, float)) and isinstance(positive_excess_rate, (int, float)):
        if float(rank_ic) < 0 and float(positive_excess_rate) > 0.55:
            return (
                f"验证冲突：RankIC {float(rank_ic):.3f} 为负，但正超额占比 "
                f"{float(positive_excess_rate):.1%} 偏高，当前信号更像方向受益，排序能力尚未成立。"
            )
    validation_conflict = historical_validation.get("validation_conflict")
    if validation_conflict:
        return str(validation_conflict)

    risk = recommendation.get("risk", {})
    risk_flags = [str(item) for item in (risk.get("risk_flags") or []) if item]
    coverage_gaps = [str(item) for item in (risk.get("coverage_gaps") or []) if item]
    if not risk_flags and coverage_gaps:
        return coverage_gaps[0]

    generic_news_risks = (
        "若 7 日内出现负向公告或行业监管扰动，新闻因子会优先转负。",
        "7 日内新增负向公告/监管事件并使新闻因子转负时降级。",
    )
    concrete_risks = [item for item in risk_flags if item not in generic_news_risks]
    priority_terms = (
        "风险公告",
        "验证冲突",
        "基本面风险",
        "现金流",
        "盈利",
        "价格已明显",
        "追价性价比",
        "趋势",
        "流动性",
    )
    for term in priority_terms:
        match = next((item for item in concrete_risks if term in item), None)
        if match:
            return match
    if concrete_risks:
        return concrete_risks[0]
    return risk_flags[0] if risk_flags else None


def _historical_validation_metric(
    recommendation: dict[str, Any],
    key: str,
) -> float | int | None:
    metrics = recommendation.get("historical_validation", {}).get("metrics", {})
    value = metrics.get(key)
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if key == "sample_count":
        return int(numeric)
    return numeric


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

    for factor_key in ("price_baseline", "news_event", "size_factor", "reversal", "liquidity", "fusion"):
        current_score = _factor_score(current_summary, factor_key)
        previous_score = _factor_score(previous_summary, factor_key)
        delta = current_score - previous_score
        if abs(delta) >= 0.06:
            reasons.append(
                f"{FACTOR_LABELS[factor_key]}分数从 {previous_score:.2f} {'转强' if delta > 0 else '转弱'}到 {current_score:.2f}。"
            )

    current_flags = _active_degrade_flags(current_reco)
    previous_flags = _active_degrade_flags(previous_reco)
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
    claim_gate = recommendation.get("claim_gate", {})
    public_direction = str(claim_gate.get("public_direction") or recommendation["direction"])
    return {
        "latest_close": latest_bar.close_price,
        "day_change_pct": round(day_change_pct, 4),
        "latest_volume": latest_bar.volume,
        "turnover_rate": latest_bar.turnover_rate,
        "high_price": latest_bar.high_price,
        "low_price": latest_bar.low_price,
        "sector_tags": [membership.sector.name for membership in memberships],
        "direction_label": DIRECTION_LABELS.get(public_direction, public_direction),
        "last_updated": recommendation["generated_at"],
    }


def _price_chart_payload(bars: list[MarketBar]) -> list[dict[str, Any]]:
    return [
        {
            "observed_at": bar.observed_at,
            "open_price": bar.open_price,
            "high_price": bar.high_price,
            "low_price": bar.low_price,
            "close_price": bar.close_price,
            "volume": bar.volume,
        }
        for bar in bars
    ]


def _risk_panel(summary: dict[str, Any], change: dict[str, Any], recent_news: list[dict[str, Any]]) -> dict[str, Any]:
    recommendation = summary["recommendation"]
    prompt = summary["prompt"]
    risk_layer = recommendation.get("risk", {})
    items: list[str] = []
    validation_conflict = recommendation.get("historical_validation", {}).get("validation_conflict")
    if validation_conflict:
        items.append(str(validation_conflict))
    items.extend(risk_layer.get("risk_flags", [])[:3])
    if recent_news:
        negative_event = next((item for item in recent_news if item["impact_direction"] == "negative"), None)
        if negative_event is not None:
            items.append(f"最近负向事件：{negative_event['headline']}")
    items.extend(risk_layer.get("downgrade_conditions", [])[:2])
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


def _event_analysis_payload(symbol: str, artifact_root: Any, *, limit: int = 3) -> list[dict[str, Any]]:
    if not artifact_root:
        return []

    from ashare_evidence.event_analyzer import list_event_analyses, read_event_analysis

    analyses: list[dict[str, Any]] = []
    for item in list_event_analyses(symbol, artifact_root=str(artifact_root), limit=limit):
        filename = str(item.get("file") or "")
        detail = read_event_analysis(symbol, filename, artifact_root=str(artifact_root)) if filename else None
        detail = detail if isinstance(detail, dict) else {}
        confidence = item.get("confidence")
        if confidence is None:
            confidence = detail.get("confidence")
        analyses.append(
            {
                "file": filename,
                "trigger_type": item.get("trigger_type") or detail.get("trigger_type") or "unknown",
                "triggered_at": item.get("triggered_at") or detail.get("triggered_at"),
                "generated_at": item.get("generated_at") or detail.get("generated_at"),
                "status": item.get("status") or detail.get("status") or "unknown",
                "independent_direction": item.get("independent_direction") or detail.get("independent_direction"),
                "confidence": confidence,
                "trigger_detail": detail.get("trigger_detail"),
                "key_evidence": detail.get("key_evidence") or [],
                "risks": detail.get("risks") or [],
                "information_gaps": detail.get("information_gaps") or [],
                "next_checkpoint": detail.get("next_checkpoint"),
                "correction_suggestion": detail.get("correction_suggestion"),
                "model_used": detail.get("model_used"),
            }
        )
    return analyses


def _follow_up_payload(summary: dict[str, Any], change: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    recommendation = summary["recommendation"]
    evidence_layer = recommendation.get("evidence", {})
    risk_layer = recommendation.get("risk", {})
    historical_validation = recommendation.get("historical_validation", {})
    core_quant = recommendation.get("core_quant", {})
    manual_llm_review = recommendation.get("manual_llm_review", {})
    hero, recent_news = summary.get("hero", {}), summary.get("recent_news", [])
    evidence_lines = build_evidence_lines(evidence)
    news_lines = build_news_lines(recent_news)
    v_sc, v_ric, v_per = (
        _historical_validation_metric(recommendation, k)
        for k in ("sample_count", "rank_ic_mean", "positive_excess_rate")
    )
    validation_lines = build_validation_lines(v_sc, v_ric, v_per)
    suggested_questions = [
        "如果我只关注未来两周，哪些证据最值得盯？",
        "这条建议最可能因为什么条件而失效？",
        "最近一版建议为什么比上一版更强/更弱？",
        "如果只允许保守跟踪，应该先看哪些风险信号？",
    ]
    prompt_blocks: list[str] = [
        "请基于以下结构化证据回答我的追问，不要补充未给出的事实。",
        "你的任务是做二次解释，不是重复包装已有结论；如果信息不足，请直接说明不足。",
        "先区分“已知事实”和“你的推断”。如果验证指标之间存在张力或冲突，必须先解释冲突，再决定是否能给方向性判断。",
        f"股票：{summary['stock']['name']}（{summary['stock']['symbol']}）",
        *build_market_lines(hero),
        f"观察窗口：{_candidate_window_definition(recommendation)}",
        f"目标周期：{core_quant.get('target_horizon_label', phase2_target_horizon_label())}",
        "核心驱动：",
        *[f"- {item}" for item in evidence_layer.get("primary_drivers", [])[:3]],
        "主要风险：",
        *[f"- {item}" for item in risk_layer.get("risk_flags", [])[:3]],
        f"系统当前建议（仅供参考，不是必须采纳）：{DIRECTION_LABELS.get(recommendation['direction'], recommendation['direction'])}；{recommendation['confidence_expression']}",
        f"最近变化：{change['summary']}",
        "关键证据：",
        *evidence_lines,
    ]
    if news_lines:
        prompt_blocks.extend(["近期事件：", *news_lines])
    if validation_lines:
        prompt_blocks.extend(["验证数据（用于评估建议可靠性）：", *validation_lines])
    prompt_blocks.extend([
        "请回答这个问题：<在这里替换成你的追问>",
        "回答要求：明确哪些是事实、哪些是推断；如果证据不足以支持买入/卖出/强化动作，要直接说明；写出失效条件，并指出下一次最值得更新观察的时间点或事件。",
    ])
    copy_prompt = "\n".join(prompt_blocks)
    return {
        "suggested_questions": suggested_questions,
        "copy_prompt": copy_prompt,
        "evidence_packet": evidence_lines,
        "research_packet": {
            "validation_status": historical_validation.get("status", "pending_rebuild"),
            "validation_note": historical_validation.get("note"),
            "validation_conflict": historical_validation.get("validation_conflict"),
            "validation_artifact_id": historical_validation.get("artifact_id"),
            "validation_manifest_id": historical_validation.get("manifest_id"),
            "validation_sample_count": v_sc,
            "validation_rank_ic_mean": v_ric,
            "validation_positive_excess_rate": v_per,
            "manual_request_id": manual_llm_review.get("request_id"),
            "manual_request_key": manual_llm_review.get("request_key"),
            "manual_review_executor_kind": manual_llm_review.get("executor_kind"),
            "manual_review_status_note": manual_llm_review.get("status_note"),
            "manual_review_review_verdict": manual_llm_review.get("review_verdict"),
            "manual_review_stale_reason": manual_llm_review.get("stale_reason"),
            "manual_review_status": manual_llm_review.get("status", "manual_trigger_required"),
            "manual_review_trigger_mode": manual_llm_review.get("trigger_mode", "manual"),
            "manual_review_source_packet": [str(item) for item in manual_llm_review.get("source_packet", []) if item],
            "manual_review_artifact_id": manual_llm_review.get("artifact_id"),
            "manual_review_generated_at": manual_llm_review.get("generated_at"),
        },
    }


def list_candidate_recommendations(session: Session, limit: int = 8) -> dict[str, Any]:
    active_symbols = set(active_watchlist_symbols(session))
    bind = session.get_bind()
    artifact_root = artifact_root_from_database_url(bind.url.render_as_string(hide_password=False) if bind else None)
    if not active_symbols:
        return {
            "generated_at": datetime.now().astimezone(),
            "items": [],
        }
    candidates: list[dict[str, Any]] = []
    for recommendation in _latest_recommendations(session):
        if recommendation.stock.symbol not in active_symbols:
            continue
        summary = _serialize_recommendation(recommendation, artifact_root=artifact_root)
        history = _recommendation_history(session, summary["stock"]["symbol"], limit=2)
        previous_summary = _serialize_recommendation(history[1], artifact_root=artifact_root) if len(history) > 1 else None
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
        claim_gate = reco.get("claim_gate", {})
        public_direction = str(claim_gate.get("public_direction") or reco["direction"])
        window_definition = _candidate_window_definition(reco)
        validation_artifact_id = reco["historical_validation"].get("artifact_id")
        validation_status = reco["historical_validation"]["status"]
        candidates.append(
            {
                "symbol": summary["stock"]["symbol"],
                "name": summary["stock"]["name"],
                "sector": primary_sector,
                "direction": reco["direction"],
                "direction_label": DIRECTION_LABELS.get(reco["direction"], reco["direction"]),
                "display_direction": public_direction,
                "display_direction_label": DIRECTION_LABELS.get(public_direction, public_direction),
                "confidence_label": reco["confidence_label"],
                "confidence_score": reco["confidence_score"],
                "summary": reco["summary"],
                "window_definition": window_definition,
                "target_horizon_label": reco["core_quant"]["target_horizon_label"],
                "source_classification": _artifact_source_classification(artifact_id=validation_artifact_id),
                "validation_mode": _artifact_validation_mode(validation_status=validation_status),
                "validation_status": validation_status,
                "validation_note": reco["historical_validation"]["note"],
                "validation_artifact_id": validation_artifact_id,
                "validation_manifest_id": reco["historical_validation"].get("manifest_id"),
                "validation_sample_count": _historical_validation_metric(reco, "sample_count"),
                "validation_rank_ic_mean": _historical_validation_metric(reco, "rank_ic_mean"),
                "validation_positive_excess_rate": _historical_validation_metric(reco, "positive_excess_rate"),
                "generated_at": reco["generated_at"],
                "as_of_data_time": reco["as_of_data_time"],
                "last_close": latest_bar.close_price if latest_bar is not None else None,
                "price_return_20d": round(twenty_day_return, 4),
                "price_chart": _price_chart_payload(bars),
                "why_now": _candidate_primary_driver(reco),
                "primary_risk": _candidate_primary_risk(reco),
                "change_summary": change["summary"],
                "change_badge": change["change_badge"],
                "evidence_status": reco["evidence_status"],
                "claim_gate": claim_gate,
                **_candidate_compat_projection(window_definition=window_definition),
            }
        )

    candidates.sort(
        key=lambda item: (
            _direction_rank(str(item.get("display_direction") or item["direction"])),
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

    bind = session.get_bind()
    artifact_root = artifact_root_from_database_url(bind.url.render_as_string(hide_password=False) if bind else None)
    latest = history[0]
    latest_summary = _serialize_recommendation(latest, artifact_root=artifact_root)
    previous_summary = _serialize_recommendation(history[1], artifact_root=artifact_root) if len(history) > 1 else None
    trace = get_recommendation_trace(session, latest.id)
    bars = _recent_bars(session, latest.stock_id, limit=28)
    today_intraday_bars = _today_intraday_bars(session, latest.stock_id, bars)
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
    trace["today_price_chart"] = _price_chart_payload(today_intraday_bars)
    trace["recent_news"] = recent_news
    trace["change"] = change
    trace["glossary"] = get_glossary_entries()
    trace["risk_panel"] = _risk_panel(trace, change, recent_news)
    trace["follow_up"] = _follow_up_payload(trace, change, trace["evidence"])
    from ashare_evidence.benchmark import benchmark_context_summary
    from ashare_evidence.data_quality import build_stock_data_quality
    from ashare_evidence.factor_observation import build_factor_observations

    trace["data_quality"] = build_stock_data_quality(
        session,
        latest.stock,
        as_of=latest.as_of_data_time,
    )
    try:
        factor_study = build_factor_observations(
            session,
            artifact_root=str(artifact_root or ""),
            persist=False,
        )
        trace["factor_validation"] = {
            "status": factor_study.get("status"),
            "note": factor_study.get("note"),
            "observation_count": factor_study.get("observation_count", 0),
            "distinct_as_of_date_count": factor_study.get("distinct_as_of_date_count", 0),
            "benchmark_context": factor_study.get("benchmark_context", {}),
        }
    except Exception as exc:
        trace["factor_validation"] = {
            "status": "unavailable",
            "note": f"因子验证摘要暂不可用：{exc}",
            "observation_count": 0,
            "distinct_as_of_date_count": 0,
            "benchmark_context": {},
        }
    trace["benchmark_context"] = benchmark_context_summary(session)
    from ashare_evidence.horizon_readout import build_horizon_readout
    trace["research_horizon_readout"] = build_horizon_readout(str(artifact_root) if artifact_root else "")
    trace["event_analyses"] = _event_analysis_payload(latest.stock.symbol, artifact_root)
    return trace
