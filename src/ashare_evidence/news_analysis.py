from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from ashare_evidence.llm_service import (
    route_model,
)

_MAX_WORKERS = 4

_ANNOUNCEMENT_SYSTEM_PROMPT = """\
You are a financial analyst specializing in Chinese A-share market announcements.
Analyze the given announcement and output ONLY a JSON object (no markdown, no extra text).

The JSON must have these fields:
- sentiment: "positive" | "negative" | "neutral" | "mixed"
- sentiment_confidence: number 0.0-1.0 (how confident you are in the sentiment)
- key_findings: array of strings, each a specific fact extracted from the announcement
- impact_areas: array of strings from: "profitability", "growth", "capital_structure", "governance", "operations", "market_sentiment", "none"
- summary_sentence: string, Chinese, under 100 chars, summarizing the announcement's impact on the stock
- reasoning: string, Chinese, under 200 chars, explaining your sentiment judgment

Rules:
- A meeting notice (说明会/董事会/监事会会议通知) without disclosed content is "neutral" with low confidence (<0.4)
- An earnings report with growing revenue/profit is "positive"
- An earnings report with declining revenue/profit is "negative"
- Insider selling (减持) is "negative"; insider buying (增持) is "positive"
- A buyback (回购) is "positive"
- Regulatory inquiry/penalty (问询/处罚) is "negative"
- A regular board resolution without material impact is "neutral"
- If the announcement title and body contain contradictory signals, use "mixed"
"""

_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}")


def _parse_llm_json(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    match = _JSON_BLOCK_RE.search(raw)
    if match:
        raw = match.group(0)
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        return {"sentiment": "neutral", "sentiment_confidence": 0.3, "key_findings": [],
                "impact_areas": [], "summary_sentence": "", "reasoning": "LLM response parse failed."}
    result.setdefault("sentiment", "neutral")
    result.setdefault("sentiment_confidence", 0.3)
    result.setdefault("key_findings", [])
    result.setdefault("impact_areas", [])
    result.setdefault("summary_sentence", "")
    result.setdefault("reasoning", "")
    valid_sentiments = {"positive", "negative", "neutral", "mixed"}
    if result["sentiment"] not in valid_sentiments:
        result["sentiment"] = "neutral"
    conf = result["sentiment_confidence"]
    if not isinstance(conf, (int, float)) or conf < 0 or conf > 1:
        result["sentiment_confidence"] = 0.3
    return result


def analyze_announcement(
    headline: str,
    content_excerpt: str | None,
    event_scope: str,
) -> dict[str, Any]:
    task = "announcement_general"
    if event_scope in ("earnings",):
        task = "announcement_earnings"
    elif event_scope in ("capital_action",):
        task = "announcement_capital_action"

    transport, base_url, api_key, model_name = route_model(task)

    prompt_parts = [f"公告标题：{headline}"]
    if content_excerpt:
        prompt_parts.append(f"公告正文（节选）：{content_excerpt}")
    else:
        prompt_parts.append("（公告正文不可用，请仅依据标题判断，降低置信度）")
    prompt = "\n\n".join(prompt_parts)

    try:
        raw_response = transport.complete(
            base_url=base_url,
            api_key=api_key,
            model_name=model_name,
            prompt=prompt,
            system=_ANNOUNCEMENT_SYSTEM_PROMPT,
        )
    except Exception:
        return {
            "sentiment": "neutral",
            "sentiment_confidence": 0.0,
            "key_findings": [],
            "impact_areas": [],
            "summary_sentence": "",
            "reasoning": f"LLM call failed: {model_name}",
            "_fallback": True,
        }

    result = _parse_llm_json(raw_response)
    result["_model"] = model_name
    return result


def analyze_announcements_batch(
    items: list[dict[str, Any]],
    *,
    max_workers: int = _MAX_WORKERS,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = [{} for _ in items]

    def _task(idx: int, item: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return idx, analyze_announcement(
            headline=item["headline"],
            content_excerpt=item.get("content_excerpt"),
            event_scope=item.get("event_scope", "announcement"),
        )

    with ThreadPoolExecutor(max_workers=min(max_workers, len(items))) as executor:
        futures = {executor.submit(_task, i, item): i for i, item in enumerate(items)}
        for future in as_completed(futures):
            try:
                idx, analysis = future.result()
                results[idx] = analysis
            except Exception:
                idx = futures[future]
                results[idx] = {
                    "sentiment": "neutral",
                    "sentiment_confidence": 0.0,
                    "key_findings": [],
                    "impact_areas": [],
                    "summary_sentence": "",
                    "reasoning": "Batch analysis failed.",
                    "_fallback": True,
                }

    return results


_FINANCIAL_SYSTEM_PROMPT = """\
You are a financial analyst evaluating Chinese A-share company fundamentals.
Analyze the given financial metrics and output ONLY a JSON object (no markdown, no extra text).

The JSON must have:
- verdict: "positive" | "negative" | "neutral" | "mixed"
- growth_assessment: string, Chinese, under 120 chars, evaluating revenue and profit growth quality
- profitability_assessment: string, Chinese, under 120 chars, evaluating ROE and earnings quality
- risk_assessment: string, Chinese, under 120 chars, key concerns from cash flow or margin pressure
- key_drivers: array of strings, each a specific fundamental strength
- key_risks: array of strings, each a specific fundamental concern
- summary_sentence: string, Chinese, under 120 chars, overall fundamental health verdict

Rules:
- Revenue growth > 15% with profit growth is bullish; profit declining while revenue grows is a warning sign
- ROE > 15% sustainable is excellent; ROE < 5% is weak
- Operating cash flow consistently below net profit signals earnings quality risk
- Be specific with numbers and trends, not generic
"""


def analyze_financials(
    snapshot: dict[str, Any],
    trends: dict[str, Any],
) -> dict[str, Any]:
    if not trends.get("available"):
        return {"verdict": "neutral", "growth_assessment": "", "profitability_assessment": "",
                "risk_assessment": "", "key_drivers": [], "key_risks": [],
                "summary_sentence": "", "_fallback": True}

    transport, base_url, api_key, model_name = route_model("financial_analysis")

    parts = ["以下为该公司最新一期财务指标："]
    for key, label in [
        ("revenue_yoy_pct", "营收同比增速(%)"),
        ("netprofit_yoy_pct", "净利润同比增速(%)"),
        ("roe", "ROE(%)"),
        ("eps", "每股收益"),
        ("operating_cashflow_per_share", "每股经营现金流"),
    ]:
        val = snapshot.get(key)
        if val is not None:
            parts.append(f"- {label}: {val}")
    parts.append(f"\n规则化趋势评分：增长质量 {trends.get('growth_quality', 0):.2f}, "
                 f"盈利能力 {trends.get('profitability_quality', 0):.2f}, "
                 f"现金流质量 {trends.get('cash_flow_quality', 0):.2f}")
    prompt = "\n".join(parts)

    try:
        raw = transport.complete(
            base_url=base_url, api_key=api_key, model_name=model_name,
            prompt=prompt, system=_FINANCIAL_SYSTEM_PROMPT,
        )
    except Exception:
        return {"verdict": "neutral", "growth_assessment": "", "profitability_assessment": "",
                "risk_assessment": "", "key_drivers": [], "key_risks": [],
                "summary_sentence": "", "_fallback": True, "_model": model_name}

    result = _parse_llm_json(raw)
    result.setdefault("verdict", "neutral")
    result.setdefault("growth_assessment", "")
    result.setdefault("profitability_assessment", "")
    result.setdefault("risk_assessment", "")
    result.setdefault("key_drivers", [])
    result.setdefault("key_risks", [])
    result.setdefault("summary_sentence", "")
    result["_model"] = model_name
    return result


def llm_sentiment_to_impact_direction(llm_analysis: dict[str, Any] | None) -> str | None:
    if not llm_analysis or llm_analysis.get("_fallback"):
        return None
    sentiment = llm_analysis.get("sentiment")
    if sentiment in ("positive", "negative", "neutral"):
        return sentiment
    if sentiment == "mixed":
        confidence = llm_analysis.get("sentiment_confidence", 0.3)
        if confidence < 0.5:
            return "neutral"
    return None
