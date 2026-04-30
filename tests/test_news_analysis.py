"""Quick validation tests for Phase 1: news analysis pipeline."""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ashare_evidence.analysis_pipeline import _CNINFO_CONTENT_RE, _HTML_TAG
from ashare_evidence.news_analysis import (
    _parse_llm_json,
    llm_sentiment_to_impact_direction,
)
from ashare_evidence.signal_engine_parts.factors import _news_driver_texts


def test_html_extraction():
    html = """<html><body><div class="detail-content">
<p>公司2026年一季度实现营业收入15.2亿元，<strong>同比增长23.5%</strong>。</p>
<p>归属于上市公司股东的净利润3.1亿元，同比增长18.2%。</p>
</div></body></html>"""
    m = _CNINFO_CONTENT_RE.search(html)
    assert m is not None, "CNINFO content regex did not match"
    text = _HTML_TAG.sub(" ", m.group(1))
    text = re.sub(r"\s{3,}", "\n", text).strip()
    assert "23.5" in text
    assert "18.2" in text
    print("PASS: HTML extraction")


def test_json_parse_good():
    result = _parse_llm_json(
        '{"sentiment":"positive","sentiment_confidence":0.85,'
        '"key_findings":["revenue +23%"],"impact_areas":["growth"],'
        '"summary_sentence":"一季度业绩超预期","reasoning":"营收利润双增"}'
    )
    assert result["sentiment"] == "positive"
    assert result["sentiment_confidence"] == 0.85
    print("PASS: JSON parse (good)")


def test_json_parse_markdown():
    result = _parse_llm_json(
        '```json\n{"sentiment":"negative","sentiment_confidence":0.7,'
        '"key_findings":[],"impact_areas":[],'
        '"summary_sentence":"减持利空","reasoning":"大股东减持"}\n```'
    )
    assert result["sentiment"] == "negative"
    print("PASS: JSON parse (markdown-wrapped)")


def test_json_parse_bad():
    result = _parse_llm_json("sorry i cannot analyze this")
    assert result["sentiment"] == "neutral"
    assert result["sentiment_confidence"] == 0.3
    print("PASS: JSON parse (bad input)")


def test_sentiment_mapping():
    assert llm_sentiment_to_impact_direction({"sentiment": "positive", "sentiment_confidence": 0.8}) == "positive"
    assert llm_sentiment_to_impact_direction({"sentiment": "mixed", "sentiment_confidence": 0.3}) == "neutral"
    assert llm_sentiment_to_impact_direction({"sentiment": "mixed", "sentiment_confidence": 0.8}) is None
    assert llm_sentiment_to_impact_direction({"_fallback": True}) is None
    assert llm_sentiment_to_impact_direction(None) is None
    print("PASS: Sentiment mapping")


def test_news_driver_texts():
    item_by_key = {
        "key1": {
            "raw_payload": {
                "llm_analysis": {
                    "summary_sentence": "一季度营收增长23%，利润增长18%，业绩超预期。",
                    "sentiment": "positive",
                    "_fallback": False,
                }
            }
        },
        "key2": {"headline": "关于召开股东大会的通知", "raw_payload": {}},
    }
    events = [
        {"news_key": "key1", "headline": "old", "score": 0.4},
        {"news_key": "key2", "headline": "关于召开股东大会的通知", "score": 0.2},
    ]
    drivers = _news_driver_texts(events, item_by_key)
    assert "公告解读：一季度营收增长23%" in drivers[0], f"Unexpected: {drivers[0]}"
    assert "提供正向事件证据" in drivers[1], f"Unexpected: {drivers[1]}"
    print("PASS: News driver texts")


if __name__ == "__main__":
    test_html_extraction()
    test_json_parse_good()
    test_json_parse_markdown()
    test_json_parse_bad()
    test_sentiment_mapping()
    test_news_driver_texts()
    print("\nAll validation tests passed!")
