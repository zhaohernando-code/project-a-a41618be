from __future__ import annotations

from typing import Any


def build_evidence_lines(evidence: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for item in evidence[:4]:
        label = str(item.get("label") or "")
        snippet = str(item.get("snippet") or "").strip()
        if snippet:
            lines.append(f"- {label}: {snippet}")
        else:
            lines.append(f"- {label}")
    if len(evidence) > 4:
        lines.append(f"- ...及其他 {len(evidence) - 4} 条证据")
    return lines


def build_news_lines(recent_news: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for item in recent_news:
        headline = str(item.get("headline") or "").strip()
        impact = str(item.get("impact_direction") or "")
        if not headline:
            continue
        tag = {"positive": "[利好]", "negative": "[利空]"}.get(impact, "")
        line = f"- {tag} {headline}" if tag else f"- {headline}"
        if line not in lines:
            lines.append(line)
        if len(lines) >= 4:
            break
    return lines


def build_validation_lines(
    validation_sample_count: float | int | None,
    validation_rank_ic_mean: float | int | None,
    validation_positive_excess_rate: float | int | None,
) -> list[str]:
    lines: list[str] = []
    if validation_sample_count is not None:
        lines.append(f"回测样本量：{validation_sample_count}")
    if validation_rank_ic_mean is not None:
        lines.append(f"RankIC 均值：{validation_rank_ic_mean}（>0.05 有一定区分能力，>0.10 较强）")
    if validation_positive_excess_rate is not None:
        lines.append(f"正超额占比：{validation_positive_excess_rate}（>55% 方向判断优于随机，>60% 较可靠）")
    return lines


def build_market_lines(hero: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    sector_tags: list[str] = hero.get("sector_tags", [])
    sector_text = "、".join(str(t) for t in sector_tags) if sector_tags else "未分类"
    latest_close = hero.get("latest_close")
    day_change_pct = hero.get("day_change_pct")
    if latest_close is not None:
        close_str = f"最新收盘：{latest_close}"
        if day_change_pct is not None:
            sign = "+" if day_change_pct >= 0 else ""
            close_str += f"（日涨跌 {sign}{day_change_pct:.2%}）"
        lines.append(close_str)
    lines.append(f"所属板块：{sector_text}")
    return lines
