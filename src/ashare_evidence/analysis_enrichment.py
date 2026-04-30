from __future__ import annotations

import re
from math import tanh
from typing import Any
from urllib import request

from ashare_evidence.http_client import urlopen

ANNOUNCEMENT_BODY_TIMEOUT = 8
ANNOUNCEMENT_BODY_MAX_CHARS = 5000

_HTML_TAG = re.compile(r"<[^>]+>")
_HTML_ENTITY = re.compile(r"&[a-zA-Z]+;|&#\d+;")
_HTML_WHITESPACE = re.compile(r"\s{3,}")
_CNINFO_CONTENT_RE = re.compile(
    r'<div[^>]*class="[^"]*detail-content[^"]*"[^>]*>(.*?)</div>', re.DOTALL
)


def fetch_announcement_body(source_uri: str) -> str | None:
    if not source_uri:
        return None
    http_request = request.Request(source_uri, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(http_request, timeout=ANNOUNCEMENT_BODY_TIMEOUT, disable_proxies=True) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
    except Exception:
        return None
    if not raw or len(raw) < 200:
        return None
    content_match = _CNINFO_CONTENT_RE.search(raw)
    if content_match:
        raw = content_match.group(1)
    text = _HTML_TAG.sub(" ", raw)
    text = _HTML_ENTITY.sub(" ", text)
    text = _HTML_WHITESPACE.sub("\n", text).strip()
    if len(text) < 40:
        return None
    return text[:ANNOUNCEMENT_BODY_MAX_CHARS]


def compute_financial_trends(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    if not snapshot:
        return {"growth_quality": 0.0, "profitability_quality": 0.0,
                "cash_flow_quality": 0.0, "composite_score": 0.0, "available": False}

    def _safe(val: Any) -> float:
        return float(val) if val is not None else 0.0

    revenue_yoy = _safe(snapshot.get("revenue_yoy_pct"))
    netprofit_yoy = _safe(snapshot.get("netprofit_yoy_pct"))
    roe = _safe(snapshot.get("roe"))
    eps = _safe(snapshot.get("eps") or snapshot.get("basic_eps"))
    ocfps = _safe(snapshot.get("operating_cashflow_per_share") or snapshot.get("operating_cashflow"))

    # ---- Multi-quarter trend analysis (Piotroski-style) ----
    history = snapshot.get("quarterly_history") or []
    num_quarters = len(history)

    # Revenue growth trend: acceleration vs deceleration
    growth_accel = 0.0
    if num_quarters >= 3:
        recent_rev_growth = [_safe(q.get("revenue_yoy_pct")) for q in history[:2] if _safe(q.get("revenue_yoy_pct")) != 0]
        older_rev_growth = [_safe(q.get("revenue_yoy_pct")) for q in history[2:4] if _safe(q.get("revenue_yoy_pct")) != 0]
        if recent_rev_growth and older_rev_growth:
            avg_recent = sum(recent_rev_growth) / len(recent_rev_growth)
            avg_older = sum(older_rev_growth) / len(older_rev_growth)
            if avg_older != 0:
                growth_accel = max(-1.0, min(1.0, (avg_recent - avg_older) / max(abs(avg_older), 0.05)))

    # Profitability trend: ROE direction across quarters
    roe_trend = 0.0
    if num_quarters >= 3:
        roe_values = [_safe(q.get("roe")) for q in history[:4] if _safe(q.get("roe")) != 0 or True]
        if len(roe_values) >= 2:
            positive_count = sum(1 for r in roe_values if r > 0.05)
            roe_trend = max(-1.0, min(1.0, (positive_count / len(roe_values) - 0.4) * 2.0))

    # Cash flow quality: consistency of OCF/EPS across quarters
    cf_consistency = 0.0
    if num_quarters >= 2:
        cf_ratios = []
        for q in history[:4]:
            q_eps = _safe(q.get("eps"))
            q_ocf = _safe(q.get("operating_cashflow_per_share"))
            if q_eps and q_eps > 0:
                cf_ratios.append(q_ocf / q_eps)
        if cf_ratios:
            pos_count = sum(1 for r in cf_ratios if r > 0.5)
            cf_consistency = max(-1.0, min(1.0, (pos_count / len(cf_ratios) - 0.5) * 2.0))

    # ---- Single-period scores with smoothed thresholds ----
    growth_score = max(-1.0, min(1.0, tanh(revenue_yoy / 0.12) * 0.7
                                   + tanh(netprofit_yoy / 0.15) * 0.3
                                   + growth_accel * 0.25))

    profitability_score = max(-1.0, min(1.0, tanh(roe / 0.10) * 0.6
                                         + (0.15 if eps and eps > 0 else -0.15)
                                         + roe_trend * 0.25))

    cashflow_score = 0.0
    if ocfps and eps and eps > 0:
        cf_ratio = ocfps / eps
        cashflow_score = max(-1.0, min(1.0,
            tanh((cf_ratio - 0.5) / 0.5) * 0.7 + cf_consistency * 0.3))
    elif ocfps and ocfps < 0:
        cashflow_score = -0.5

    def _clip(v: float) -> float:
        return max(-1.0, min(1.0, v))

    composite = _clip(growth_score * 0.40 + profitability_score * 0.35 + cashflow_score * 0.25)
    return {
        "growth_quality": round(_clip(growth_score), 4),
        "profitability_quality": round(_clip(profitability_score), 4),
        "cash_flow_quality": round(_clip(cashflow_score), 4),
        "composite_score": round(composite, 4),
        "available": True,
        "report_period": snapshot.get("report_period"),
        "num_quarters": num_quarters,
        "growth_accel": round(growth_accel, 4),
    }


def enrich_with_llm_analysis(
    news_items: list[dict[str, Any]],
    news_links: list[dict[str, Any]],
) -> None:
    from ashare_evidence.news_analysis import (
        analyze_announcements_batch,
        llm_sentiment_to_impact_direction,
    )

    candidates = [item for item in news_items if item.get("summary") == item.get("headline")]
    if not candidates:
        return

    try:
        llm_results = analyze_announcements_batch(candidates)
    except Exception:
        return

    for item, llm in zip(candidates, llm_results):
        item["raw_payload"]["llm_analysis"] = llm
        summary = llm.get("summary_sentence", "").strip()
        if summary:
            item["summary"] = summary
        new_direction = llm_sentiment_to_impact_direction(llm)
        if new_direction:
            for link in news_links:
                if link.get("news_key") == item["news_key"]:
                    link["impact_direction"] = new_direction
                    link.setdefault("mapping_payload", {})["llm_override"] = True
