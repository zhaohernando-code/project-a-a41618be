from __future__ import annotations

from typing import Any

from ashare_evidence.signal_engine_parts.base import FUSION_WEIGHTS


def resolve_factor_conflict(
    price_dir: str,
    news_dir: str,
    fund_dir: str,
    price_conf: float,
    news_conf: float,
    fund_conf: float,
) -> tuple[str | None, list[str]]:
    directions = [price_dir, news_dir, fund_dir]
    confidences = [price_conf, news_conf, fund_conf]
    active_dirs = [(d, c) for d, c in zip(directions, confidences) if d != "neutral" and c > 0]
    if not active_dirs:
        return None, ["所有因子均为中性，缺乏方向性信号。"]
    positive_count = sum(1 for d, _ in active_dirs if d == "positive")
    negative_count = sum(1 for d, _ in active_dirs if d == "negative")
    total = len(active_dirs)
    if positive_count >= total * 0.66:
        return "positive", []
    if negative_count >= total * 0.66:
        return "negative", []
    if positive_count >= 2 or negative_count >= 2:
        majority = "positive" if positive_count >= 2 else "negative"
        return majority, ["多数因子方向一致，但存在分歧信号。"]
    max_item = max(active_dirs, key=lambda x: x[1])
    if max_item[1] > 0.55:
        return max_item[0], ["高置信度因子主导方向判断，但其他因子存在分歧。"]
    return None, ["因子方向分歧严重，建议等待更明确信号。"]


def dynamic_weights(
    price_factor: dict[str, Any],
    news_factor: dict[str, Any],
    fundamental_factor: dict[str, Any],
) -> dict[str, float]:
    base = dict(FUSION_WEIGHTS)
    fund_weight = fundamental_factor.get("weight", 0.20)
    if fund_weight == 0:
        base["price_baseline"] = 0.62
        base["news_event"] = 0.38
        base["fundamental"] = 0.0
        return base
    price_c = float(price_factor.get("confidence_score", 0.44))
    news_c = float(news_factor.get("confidence_score", 0.36))
    fund_c = float(fundamental_factor.get("confidence_score", 0.3))
    total_conf = price_c + news_c + fund_c
    if total_conf <= 0:
        return base
    effective = {}
    effective["price_baseline"] = round(
        base["price_baseline"] * (price_c / (total_conf / 3)) * (1 + (price_c - 0.5) * 0.3), 4
    )
    effective["news_event"] = round(
        base["news_event"] * (news_c / (total_conf / 3)) * (1 + (news_c - 0.5) * 0.3), 4
    )
    effective["fundamental"] = round(
        base["fundamental"] * (fund_c / (total_conf / 3)) * (1 + (fund_c - 0.3) * 0.3), 4
    )
    total_w = sum(effective.values())
    if total_w > 0:
        effective = {k: round(v / total_w, 4) for k, v in effective.items()}
    return effective


PLACEHOLDER_FUSION_HEADLINE = "用于汇总价格、事件与降级状态的融合层。"
DEGRADE_FLAG_DISPLAY = {
    "missing_news_evidence": "近期缺少新增事件证据，当前更多依赖价格趋势观察。",
    "event_conflict_high": "价格与事件方向冲突较高，系统已主动下调对外表达。",
    "market_data_stale": "最新行情刷新偏旧，短线结论需要谨慎使用。",
}


def display_ready_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text == PLACEHOLDER_FUSION_HEADLINE or "Phase 2 规则基线" in text:
        return None
    return text


def humanize_degrade_flag(flag: str) -> str:
    cleaned = str(flag).strip()
    if not cleaned:
        return ""
    return DEGRADE_FLAG_DISPLAY.get(cleaned, cleaned.replace("_", " "))


def factor_headline_fallback(
    factor_key: str,
    *,
    factor_payload: dict[str, Any],
    recommendation_direction_value: str,
    degrade_flags: list[str],
) -> str:
    direction = str(factor_payload.get("direction") or "")
    evidence_count = factor_payload.get("evidence_count")
    conflict_ratio = factor_payload.get("conflict_ratio")
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
    if factor_key == "fundamental":
        if isinstance(evidence_count, (int, float)) and evidence_count <= 0:
            return "基本面数据暂不可用，当前基于价格与新闻因子进行判断。"
        if direction == "positive":
            return "财务指标整体偏正面，营收、利润或ROE优于基准水平。"
        if direction == "negative":
            return "财务指标存在改善空间，关注营收增速与现金流质量。"
        return "财务指标未形成明确方向，需持续跟踪下一报告期。"
    if factor_key == "manual_review_layer":
        return "人工研究结论会单独展示，当前只作为补充解释，不直接进入量化评分。"
    if "market_data_stale" in degrade_flags:
        return "最新行情刷新偏旧，当前结论先保留在观察区间。"
    if "event_conflict_high" in degrade_flags:
        return "价格与事件信号分歧较大，系统先下调对外表达。"
    if "missing_news_evidence" in degrade_flags:
        return "近期缺少新增事件证据，当前主要依赖价格趋势延续。"
    if recommendation_direction_value == "buy":
        return "价格、事件与基本面多因子同向，综合后建议建仓。"
    if recommendation_direction_value == "add":
        return "多数因子偏正，可在现有基础上适当加仓。"
    if recommendation_direction_value == "sell":
        return "多因子方向偏空，建议离场规避风险。"
    if recommendation_direction_value == "reduce":
        return "综合信号偏弱，建议降低敞口，等待更明确信号。"
    if recommendation_direction_value == "risk_alert":
        return "当前证据不足以给出方向性建议，优先重视风险。"
    return "价格与事件综合后暂未形成可放大的单边结论。"


def factor_risk_fallback(
    factor_key: str,
    *,
    factor_payload: dict[str, Any],
    degrade_flags: list[str],
) -> str | None:
    conflict_ratio = factor_payload.get("conflict_ratio")
    if factor_key == "price_baseline":
        return "若 10 日与 20 日动量继续下行，价格基线会优先转弱。"
    if factor_key == "news_event":
        if isinstance(conflict_ratio, (int, float)) and float(conflict_ratio) >= 0.35:
            return "事件冲突仍偏高，新增负面消息会更快触发降级。"
        return "若后续事件方向反转，事件层会率先削弱当前判断。"
    if factor_key == "fundamental":
        return "若基本面数据持续恶化，将拉低综合评分。"
    if factor_key == "manual_review_layer":
        return "人工研究仍需补充正式记录后才能作为稳定参考。"
    if degrade_flags:
        return humanize_degrade_flag(degrade_flags[0])
    return "如果价格与事件继续背离，综合层会优先收缩对外表达。"


def factor_card(
    factor_key: str,
    *,
    factor_payload: dict[str, Any],
    recommendation_direction_value: str,
    degrade_flags: list[str],
) -> dict[str, Any]:
    return {
        "factor_key": factor_key,
        "score": factor_payload.get("score"),
        "direction": factor_payload.get("direction"),
        "headline": (
            next(
                (text for item in factor_payload.get("drivers") or [] if (text := display_ready_text(item))),
                None,
            )
            or factor_headline_fallback(
                factor_key,
                factor_payload=factor_payload,
                recommendation_direction_value=recommendation_direction_value,
                degrade_flags=degrade_flags,
            )
        ),
        "risk_note": (
            next(
                (text for item in factor_payload.get("risks") or [] if (text := display_ready_text(item))),
                None,
            )
            or factor_risk_fallback(
                factor_key,
                factor_payload=factor_payload,
                degrade_flags=degrade_flags,
            )
        ),
        "status": factor_payload.get("status"),
    }


def supporting_context(
    *,
    news_factor: dict[str, Any],
    manual_review_layer: dict[str, Any],
) -> list[str]:
    context = ["价格层仍是当前判断的主轴，近期趋势和量价确认决定了大部分方向。"]
    evidence_count = news_factor.get("evidence_count")
    conflict_ratio = news_factor.get("conflict_ratio")
    if isinstance(evidence_count, (int, float)) and evidence_count <= 0:
        context.append("近期没有新增高置信事件，当前更多依赖价格趋势是否延续。")
    elif isinstance(conflict_ratio, (int, float)) and float(conflict_ratio) >= 0.35:
        context.append("事件层存在正负并存的情况，需要继续观察冲突是否扩大。")
    else:
        context.append("事件层主要用于确认价格趋势是否得到新的公告或行业催化支撑。")
    if manual_review_layer.get("status"):
        context.append("人工研究结论单独展示，当前只作为补充解释，不直接改变量化评分。")
    return context


def display_conflicts(news_factor: dict[str, Any], active_degrade_flags: list[str]) -> list[str]:
    conflicts: list[str] = []
    if news_factor.get("conflict_ratio", 0) > 0:
        conflicts.append(f"新闻事件冲突度 {news_factor['conflict_ratio']:.0%}。")
    conflicts.extend(
        h for h in (humanize_degrade_flag(flag) for flag in active_degrade_flags) if h
    )
    return conflicts


def actionable_summary(
    stock_name: str,
    direction: str,
    price_factor: dict[str, Any],
    news_factor: dict[str, Any],
    fundamental_factor: dict[str, Any] | None,
) -> str:
    direction_labels = {
        "buy": "可建仓", "add": "可加仓", "watch": "继续观察",
        "reduce": "减仓", "sell": "建议离场", "risk_alert": "风险提示",
    }
    label = direction_labels.get(direction, direction)
    price_dir = price_factor.get("direction", "neutral")
    news_dir = news_factor.get("direction", "neutral")
    parts = [f"{stock_name}：建议「{label}」。"]

    if price_dir == "positive":
        parts.append("技术面偏多，价格趋势和量价确认均为正向。")
    elif price_dir == "negative":
        parts.append("技术面偏空，价格趋势转弱或确认项回落。")

    if news_dir == "positive":
        parts.append("消息面有正向事件支撑。")
    elif news_dir == "negative":
        parts.append("消息面存在负向公告或扰动。")

    if fundamental_factor and fundamental_factor.get("evidence_count", 0) > 0:
        fund_dir = fundamental_factor.get("direction", "neutral")
        if fund_dir == "positive":
            parts.append("基本面指标偏正面。")
        elif fund_dir == "negative":
            parts.append("基本面指标需关注。")

    return "".join(parts)
