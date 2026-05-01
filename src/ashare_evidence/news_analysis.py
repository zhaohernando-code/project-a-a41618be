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
- sentiment_confidence: number 0.0-1.0
- importance_score: number 0.0-1.0 (how important is this for stock price? 0=irrelevant, 1=critical)
- key_findings: array of strings
- impact_areas: array of strings from: "profitability", "growth", "capital_structure", "governance", "operations", "market_sentiment", "none"
- summary_sentence: string, Chinese, under 100 chars
- reasoning: string, Chinese, under 200 chars
- needs_deeper_analysis: boolean (true if this requires a more powerful model to re-analyze)

Importance scoring guide:
- 0.9-1.0: Earnings reports, major M&A, regulatory penalties, large insider trades
- 0.7-0.9: Capital actions (buybacks, dividends), significant business developments
- 0.4-0.7: Board resolutions with material decisions, research/roadshow notices with content
- 0.1-0.4: Routine governance filings, meeting notices without content
- 0.0-0.1: Purely procedural notifications with no material impact

Rules:
- Meeting notices without disclosed content: sentiment="neutral", confidence<0.4, importance<0.2
- If the announcement body is webpage code/template, IGNORE it and use financial data instead
- Earnings with revenue growth>20% AND profit growth>15%: sentiment="positive", importance>=0.9
- Insider selling is "negative"; buying is "positive"; both are high importance
- Regulatory penalties are "negative" with high importance
"""

_ANNOUNCEMENT_PRO_SYSTEM_PROMPT = """\
You are a senior financial analyst. RE-ANALYZE this announcement that was flagged as important.
Output ONLY a JSON object (no markdown, no extra text) with the same fields as the initial analysis,
but provide deeper, more quantitative reasoning.

Fields: sentiment, sentiment_confidence, importance_score, key_findings, impact_areas,
summary_sentence, reasoning, needs_deeper_analysis (always false this time)
"""

def _parse_llm_json(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    # Try to find JSON block in various formats
    for pattern in [
        r'\{[\s\S]*\}',  # bare JSON
        r'```json\s*\{[\s\S]*?\}\s*```',  # ```json ... ```
        r'```\s*\{[\s\S]*?\}\s*```',  # ``` ... ```
    ]:
        match = re.search(pattern, raw)
        if match:
            extracted = match.group(0)
            # Remove markdown fences
            extracted = re.sub(r'^```(?:json)?\s*', '', extracted)
            extracted = re.sub(r'\s*```$', '', extracted)
            try:
                result = json.loads(extracted)
                # Fix common Pro model issues
                if not isinstance(result.get("key_findings"), list):
                    result["key_findings"] = []
                if not isinstance(result.get("impact_areas"), list):
                    result["impact_areas"] = []
                return result
            except json.JSONDecodeError:
                continue
    result = {
        "sentiment": "neutral",
        "sentiment_confidence": 0.3,
        "key_findings": [],
        "impact_areas": [],
        "summary_sentence": "",
        "reasoning": "LLM response parse failed.",
        "importance_score": 0.0,
    }
    return result


def _append_financial_data(parts: list[str], fs: dict[str, Any]) -> None:
    lines = ["以下为从财报数据系统获取的最新财务指标："]
    for key, label in [
        ("revenue_yoy_pct", "营业收入同比增长率(%)"),
        ("netprofit_yoy_pct", "净利润同比增长率(%)"),
        ("roe", "净资产收益率 ROE(%)"),
        ("eps", "每股收益 EPS"),
        ("operating_cashflow_per_share", "每股经营现金流"),
    ]:
        val = fs.get(key)
        if val is not None:
            lines.append(f"- {label}: {val}")
    cf = fs.get("operating_cashflow_per_share")
    if cf is not None and float(cf) < 0:
        lines.append("⚠ 经营现金流为负，盈利质量可能存在问题。")
    parts.append("\n".join(lines))


IMPORTANCE_THRESHOLD = 0.5


def _build_prompt(headline: str, content_excerpt: str | None, event_scope: str,
                  financial_snapshot: dict[str, Any] | None) -> str:
    prompt_parts = [f"公告标题：{headline}"]
    if content_excerpt:
        prompt_parts.append(f"公告正文（节选）：{content_excerpt}")
    elif financial_snapshot and event_scope == "earnings":
        _append_financial_data(prompt_parts, financial_snapshot)
    elif event_scope == "earnings":
        prompt_parts.append("（公告正文不可用，且无财务数据补充，请仅依据标题判断，降低置信度。）")
    else:
        prompt_parts.append("（公告正文不可用，请仅依据标题判断，降低置信度。）")
    if content_excerpt and event_scope == "earnings" and financial_snapshot:
        prompt_parts.append("补充财务数据（若公告正文为网页代码无实质内容，请以此为准）：")
        _append_financial_data(prompt_parts, financial_snapshot)
    return "\n\n".join(prompt_parts)


def _call_llm(transport, base_url, api_key, model_name, prompt, system) -> dict[str, Any]:
    try:
        raw = transport.complete(base_url=base_url, api_key=api_key,
                                 model_name=model_name, prompt=prompt, system=system)
    except Exception:
        return {"sentiment": "neutral", "sentiment_confidence": 0.0, "importance_score": 0.0,
                "key_findings": [], "impact_areas": [], "summary_sentence": "",
                "reasoning": f"LLM call failed: {model_name}", "_fallback": True}
    result = _parse_llm_json(raw)
    result["_model"] = model_name
    return result


def analyze_announcement(
    headline: str,
    content_excerpt: str | None,
    event_scope: str,
    *,
    financial_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    # Tier 1: Flash quick scan (all announcements)
    t1, base_url, api_key, flash_model = route_model("announcement_general")
    prompt = _build_prompt(headline, content_excerpt, event_scope, financial_snapshot)
    result = _call_llm(t1, base_url, api_key, flash_model, prompt, _ANNOUNCEMENT_SYSTEM_PROMPT)
    result["_tier"] = 1

    # Tier 2: Pro deep analysis for important announcements
    importance = result.get("importance_score", 0.0)
    needs_deeper = result.get("needs_deeper_analysis", False)
    if (importance >= IMPORTANCE_THRESHOLD or needs_deeper) and not result.get("_fallback"):
        t2, _, _, pro_model = route_model("financial_analysis")
        result2 = _call_llm(t2, base_url, api_key, pro_model, prompt, _ANNOUNCEMENT_PRO_SYSTEM_PROMPT)
        if not result2.get("_fallback"):
            result2["_tier"] = 2
            result2["_flash_model"] = flash_model
            result2["_flash_sentiment"] = result.get("sentiment")
            result2["_flash_importance"] = importance
            return result2
        result["_pro_attempted"] = True

    return result


def analyze_announcements_batch(
    items: list[dict[str, Any]],
    *,
    max_workers: int = _MAX_WORKERS,
    financial_snapshot: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = [{} for _ in items]

    def _task(idx: int, item: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        fs = financial_snapshot if item.get("event_scope") == "earnings" else None
        return idx, analyze_announcement(
            headline=item["headline"],
            content_excerpt=item.get("content_excerpt"),
            event_scope=item.get("event_scope", "announcement"),
            financial_snapshot=fs,
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
