from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ashare_evidence.dashboard import (
    DIRECTION_LABELS,
    FACTOR_LABELS,
    _candidate_window_definition,
    _historical_validation_metric,
    get_stock_dashboard,
    list_candidate_recommendations,
)
from ashare_evidence.event_triggers import TriggerEvent
from ashare_evidence.llm_service import AnthropicCompatibleTransport, OpenAICompatibleTransport, route_model
from ashare_evidence.phase2 import phase2_target_horizon_label

DEEP_ANALYSIS_TIMEOUT_SECONDS = 120
EVENT_ANALYSIS_DIR = "event_analysis"


def _artifact_dir(artifact_root: str) -> Path:
    return Path(artifact_root) / EVENT_ANALYSIS_DIR


def _nested_get(d: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(key, {})
    return d if d != {} else default


def _snapshot_hash(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:12]


def _price_summary(bars: list[dict[str, Any]], days: int = 20) -> str:
    if not bars:
        return "无价格数据"
    recent = bars[-days:] if len(bars) >= days else bars
    closes = [b["close_price"] for b in recent]
    volumes = [b["volume"] for b in recent]
    if not closes:
        return "无价格数据"
    ma5 = sum(closes[-5:]) / min(len(closes), 5)
    ma10 = sum(closes[-10:]) / min(len(closes), 10) if len(closes) >= 10 else ma5
    ma20 = sum(closes) / len(closes)
    avg_vol_20 = sum(volumes) / len(volumes) if volumes else 0
    recent_vol_5 = sum(volumes[-5:]) / min(len(volumes), 5) if volumes else 0
    vol_ratio = recent_vol_5 / avg_vol_20 if avg_vol_20 > 0 else 1.0

    alignment = []
    if ma5 > ma10:
        alignment.append("5日线在10日线上方")
    else:
        alignment.append("5日线在10日线下方")
    if ma10 > ma20:
        alignment.append("10日线在20日线上方")
    else:
        alignment.append("10日线在20日线下方")
    alignment_str = "；".join(alignment)

    first_close = closes[0] if closes else 0
    period_return = (closes[-1] / first_close - 1) if first_close and first_close != 0 else 0

    lines = [
        f"近 {len(closes)} 日价格区间：{min(closes):.2f} - {max(closes):.2f}",
        f"最新收盘：{closes[-1]:.2f}",
        f"5日均线：{ma5:.2f}  10日均线：{ma10:.2f}  20日均线：{ma20:.2f}",
        f"均线排列：{alignment_str}",
        f"期间涨跌幅：{period_return:+.2%}",
        f"近5日均量 / 20日均量：{vol_ratio:.2f}",
        f"最近5日成交量：{', '.join(f'{v:.0f}' for v in volumes[-5:])}",
    ]
    return "\n".join(lines)


def _factor_table(dashboard: dict[str, Any]) -> str:
    evidence = dashboard["recommendation"].get("evidence", {})
    factor_cards = evidence.get("factor_cards", [])
    if not factor_cards:
        return "无因子数据"
    rows = ["| 因子 | 分数 | 方向 | 置信度 |", "|------|------|------|--------|"]
    for card in factor_cards:
        key = card.get("factor_key", "?")
        label = FACTOR_LABELS.get(key, key)
        score = float(card.get("score") or 0)
        direction = card.get("direction", "neutral")
        confidence = float(card.get("confidence_score") or 0)
        rows.append(f"| {label} | {score:.2f} | {direction} | {confidence:.2f} |")
    return "\n".join(rows)


def _announcement_details(dashboard: dict[str, Any]) -> str:
    recent_news = dashboard.get("recent_news", [])
    if not recent_news:
        return "近期无公告"
    lines: list[str] = []
    for item in recent_news[:5]:
        headline = item.get("headline", "")
        summary = item.get("summary", "")
        impact = item.get("impact_direction", "")
        published = item.get("published_at", "")
        payload = item.get("payload") or item.get("raw_payload") or {}
        llm_analysis = payload.get("llm_analysis") if isinstance(payload, dict) else None

        tag = {"positive": "[利好]", "negative": "[利空]"}.get(str(impact), "")
        lines.append(f"\n### {tag} {headline}")
        if published:
            lines.append(f"发布时间：{published}")
        if summary:
            lines.append(f"摘要：{summary[:200]}")
        if isinstance(llm_analysis, dict):
            key_findings = llm_analysis.get("key_findings") or []
            if key_findings:
                lines.append("关键发现：")
                for kf in key_findings[:3]:
                    lines.append(f"  - {kf}")
            sentiment = llm_analysis.get("sentiment", "")
            importance = llm_analysis.get("importance_score", "")
            if sentiment:
                lines.append(f"LLM情绪：{sentiment}")
            if importance:
                lines.append(f"重要性：{float(importance):.0%}")
    return "\n".join(lines) if lines else "近期无公告"


def _peer_comparison(session: Session, symbol: str, dashboard: dict[str, Any]) -> str:
    candidates = list_candidate_recommendations(session, limit=8)
    items = candidates.get("items", [])
    if len(items) <= 1:
        return "无同板块对比数据"

    current_sector = dashboard.get("hero", {}).get("sector_tags", [])
    sector_set = set(current_sector)

    rows = ["| 股票 | 方向 | 置信度 | 20日涨跌 | 板块 |", "|------|------|--------|----------|------|"]
    count = 0
    for item in items:
        if count >= 6:
            break
        item_sectors = set(item.get("sector_tags", []) if "sector_tags" in item else [item.get("sector", "")])
        if not sector_set or not item_sectors or sector_set.isdisjoint(item_sectors):
            continue
        name = item.get("name", item.get("symbol", "?"))
        direction = item.get("display_direction_label", item.get("direction_label", "?"))
        confidence = item.get("confidence_label", "?")
        ret_20d = item.get("price_return_20d")
        ret_str = f"{ret_20d:+.1%}" if isinstance(ret_20d, (int, float)) else "?"
        sector = item.get("sector", "?")
        marker = " ← 当前" if item.get("symbol") == symbol else ""
        rows.append(f"| {name}{marker} | {direction} | {confidence} | {ret_str} | {sector} |")
        count += 1
    return "\n".join(rows) if len(rows) > 2 else "无同板块对比数据"


def _fetch_external_data(symbol: str) -> dict[str, Any]:
    result: dict[str, Any] = {"news_flow": [], "source": "无外部数据源"}
    try:
        import akshare as ak  # type: ignore[import-untyped]

        df = ak.stock_individual_info_flow(symbol=symbol)
        if df is not None and not df.empty:
            records = df.head(10).to_dict(orient="records")
            result["news_flow"] = [
                {"title": str(r.get("title", r.get("note", ""))), "time": str(r.get("time", r.get("datetime", "")))}
                for r in records
            ]
            result["source"] = "新浪/东方财富个股信息流（AKShare）"
    except Exception:
        try:
            import akshare as ak  # type: ignore[import-untyped]

            df = ak.stock_zh_a_spot_em()
            if df is not None and not df.empty:
                row = df[df["代码"] == symbol]
                if not row.empty:
                    result["spot"] = row.iloc[0].to_dict()
                    result["source"] = "东方财富实时行情（AKShare）"
        except Exception:
            pass
    return result


def _build_event_analysis_prompt(
    dashboard: dict[str, Any],
    trigger: TriggerEvent,
    internal_blocks: dict[str, str],
    external_data: dict[str, Any],
    peer_text: str,
) -> str:
    reco = dashboard["recommendation"]
    core_quant = reco.get("core_quant", {})
    validation_sample_count = _historical_validation_metric(reco, "sample_count")
    validation_rank_ic_mean = _historical_validation_metric(reco, "rank_ic_mean")
    validation_positive_excess_rate = _historical_validation_metric(reco, "positive_excess_rate")

    # External news
    external_lines: list[str] = []
    news_flow = external_data.get("news_flow", [])
    if news_flow:
        external_lines.append(f"来源：{external_data.get('source', '外部')}")
        for nf in news_flow[:8]:
            external_lines.append(f"- {nf.get('time', '')} {nf.get('title', '')}")
    external_text = "\n".join(external_lines) if external_lines else "暂无外部实时信息流数据"

    # Validation
    validation_parts: list[str] = []
    if validation_sample_count is not None:
        validation_parts.append(f"回测样本量：{validation_sample_count}")
    if validation_rank_ic_mean is not None:
        validation_parts.append(f"RankIC 均值：{validation_rank_ic_mean}（>0.05 有一定区分能力，>0.10 较强）")
    if validation_positive_excess_rate is not None:
        validation_parts.append(f"正超额占比：{validation_positive_excess_rate}（>55% 优于随机，>60% 较可靠）")
    validation_text = "\n".join(f"- {vp}" for vp in validation_parts) if validation_parts else "暂无验证数据"

    blocks = [
        "## 任务",
        "你是独立研究分析员。你的任务是基于以下全部证据，给出独立判断。",
        "不要复读系统已有结论。如果证据不足以形成判断，请直接说明，不要强行给结论。",
        f"触发原因：{trigger.detail}",
        "",
        "## 股票信息",
        internal_blocks.get("market", ""),
        "",
        "## 价格与量能（近 20 天）",
        internal_blocks.get("price", "无价格数据"),
        "",
        "## 各因子评分（内部量化模型）",
        internal_blocks.get("factors", "无因子数据"),
        "",
        "## 系统当前建议",
        f"方向：{DIRECTION_LABELS.get(reco['direction'], reco['direction'])}",
        f"置信度：{reco['confidence_expression']}",
        f"证据状态：{reco.get('evidence_status', '?')}",
        f"目标周期：{core_quant.get('target_horizon_label', phase2_target_horizon_label())}",
        f"观察窗口：{_candidate_window_definition(reco)}",
        "",
        "## 近期公告/新闻（全文摘要）",
        internal_blocks.get("announcements", "近期无公告"),
        "",
        "## 同板块对比",
        peer_text,
        "",
        "## 验证数据（用于评估建议可靠性）",
        validation_text,
        "",
        "## 外部实时信息",
        external_text,
        "",
        "## 输出要求",
        "请只输出一个 JSON 对象，不要加代码块。字段固定为：",
        "- independent_direction: agree | partial_agree | disagree | insufficient_evidence",
        "- confidence: 0.0 到 1.0 之间的浮点数",
        '- key_evidence: 对象数组，每个对象包含 source（"internal" 或 "external"）和 content（证据描述）',
        "- risks: 字符串数组（内部数据可能覆盖不到的风险尤其重要）",
        "- information_gaps: 字符串数组（当前所有数据源的覆盖盲区）",
        "- next_checkpoint: 下一次最值得观察的时间点或事件",
        "- correction_suggestion: 如有分歧，建议如何修正（无分歧时填空字符串）",
    ]
    return "\n".join(blocks)


def run_event_analysis(
    session: Session,
    *,
    symbol: str,
    trigger: TriggerEvent,
    artifact_root: str,
    transport: OpenAICompatibleTransport | AnthropicCompatibleTransport | None = None,
) -> dict[str, Any]:
    dashboard = get_stock_dashboard(session, symbol)

    # Gather internal data blocks
    price_chart = dashboard.get("price_chart", [])
    internal_blocks: dict[str, str] = {
        "market": (
            f"名称：{dashboard['stock']['name']}（{dashboard['stock']['symbol']}）\n"
            f"最新收盘：{dashboard['hero'].get('latest_close', '?')}"
            f"（日涨跌 {dashboard['hero'].get('day_change_pct', 0):+.2%}）\n"
            f"所属板块：{'、'.join(str(t) for t in dashboard['hero'].get('sector_tags', [])) or '未分类'}"
        ),
        "price": _price_summary(price_chart),
        "factors": _factor_table(dashboard),
        "announcements": _announcement_details(dashboard),
    }

    peer_text = _peer_comparison(session, symbol, dashboard)
    external_data = _fetch_external_data(symbol)
    prompt = _build_event_analysis_prompt(dashboard, trigger, internal_blocks, external_data, peer_text)

    # Data snapshot for staleness detection
    data_hash = _snapshot_hash(
        str(dashboard["hero"].get("latest_close") or ""),
        str(dashboard["hero"].get("day_change_pct") or ""),
        json.dumps(dashboard.get("price_chart", [])[-5:], default=str),
    )

    # Execute LLM
    llm_transport, base_url, api_key, model = route_model("event_analysis")
    if transport is not None:
        llm_transport = transport

    try:
        answer = llm_transport.complete(
            base_url=base_url,
            api_key=api_key,
            model_name=model,
            prompt=prompt,
        )
    except Exception as exc:
        return {
            "symbol": symbol,
            "trigger_type": trigger.trigger_type,
            "triggered_at": trigger.triggered_at.isoformat(),
            "status": "failed",
            "error": str(exc),
            "prompt": prompt,
            "model_used": model,
        }

    structured = _extract_structured_answer(answer)

    artifact = {
        "symbol": symbol,
        "trigger_type": trigger.trigger_type,
        "trigger_detail": trigger.detail,
        "triggered_at": trigger.triggered_at.isoformat(),
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "completed",
        "model_used": model,
        "data_snapshot_hash": data_hash,
        "prompt": prompt,
        "raw_answer": answer,
        "independent_direction": structured.get("independent_direction", "insufficient_evidence"),
        "confidence": float(structured.get("confidence") or 0),
        "key_evidence": structured.get("key_evidence") or [],
        "risks": structured.get("risks") or [],
        "information_gaps": structured.get("information_gaps") or [],
        "next_checkpoint": str(structured.get("next_checkpoint") or ""),
        "correction_suggestion": str(structured.get("correction_suggestion") or ""),
    }

    _save_artifact(artifact, artifact_root=artifact_root)
    return artifact


def _extract_structured_answer(answer: str) -> dict[str, Any]:
    text = answer.strip()
    candidates = [text]
    if "```" in text:
        for block in text.split("```"):
            block = block.strip()
            if not block or block.lower() == "json":
                continue
            candidates.append(block.removeprefix("json").strip())
    for candidate in candidates:
        try:
            result = json.loads(candidate)
            if isinstance(result, dict) and "independent_direction" in result:
                return result
        except (json.JSONDecodeError, TypeError):
            continue
    for candidate in candidates:
        try:
            result = json.loads(candidate)
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, TypeError):
            continue
    return {}


def _save_artifact(artifact: dict[str, Any], *, artifact_root: str) -> Path:
    directory = _artifact_dir(artifact_root) / artifact["symbol"]
    directory.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    filename = f"{ts}_{artifact['trigger_type']}.json"
    filepath = directory / filename
    filepath.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    _update_index(directory, artifact, filename)
    return filepath


def _update_index(directory: Path, artifact: dict[str, Any], filename: str) -> None:
    index_path = directory / "index.json"
    index: list[dict[str, Any]] = []
    if index_path.exists():
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, TypeError):
            index = []
    index.append({
        "file": filename,
        "trigger_type": artifact["trigger_type"],
        "triggered_at": artifact["triggered_at"],
        "generated_at": artifact["generated_at"],
        "status": artifact["status"],
        "independent_direction": artifact.get("independent_direction", ""),
        "confidence": artifact.get("confidence", 0),
    })
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def list_event_analyses(symbol: str, *, artifact_root: str, limit: int = 10) -> list[dict[str, Any]]:
    directory = _artifact_dir(artifact_root) / symbol
    index_path = directory / "index.json"
    if not index_path.exists():
        return []
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, TypeError):
        return []
    index.sort(key=lambda item: str(item.get("generated_at", "")), reverse=True)
    return index[:limit]


def read_event_analysis(symbol: str, filename: str, *, artifact_root: str) -> dict[str, Any] | None:
    filepath = _artifact_dir(artifact_root) / symbol / filename
    if not filepath.exists():
        return None
    try:
        return json.loads(filepath.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, TypeError):
        return None
