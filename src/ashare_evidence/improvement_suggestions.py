from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib import request
from urllib.error import HTTPError, URLError

from sqlalchemy import select
from sqlalchemy.orm import Session

from ashare_evidence.dashboard import get_stock_dashboard, list_candidate_recommendations
from ashare_evidence.data_quality import build_stock_data_quality
from ashare_evidence.db import utcnow
from ashare_evidence.http_client import urlopen
from ashare_evidence.llm_service import AnthropicCompatibleTransport, OpenAICompatibleTransport
from ashare_evidence.models import ManualResearchRequest, ModelApiKey, Stock
from ashare_evidence.research_artifact_store import (
    artifact_root_from_database_url,
    read_manual_research_artifact_if_exists,
)
from ashare_evidence.watchlist import active_watchlist_symbols

SUGGESTION_REVIEW_DIR = "suggestion_reviews"
LEDGER_SNAPSHOT_TYPE = "suggestion_ledger_snapshot"
REVIEW_SNAPSHOT_TYPE = "suggestion_review_snapshot"
PLAN_SNAPSHOT_TYPE = "suggestion_plan_snapshot"

SUGGESTION_CATEGORIES = {
    "ui_explanation",
    "risk_display",
    "data_quality",
    "research_validation",
    "factor_weight_experiment",
    "horizon_experiment",
    "operations_workflow",
}
SUGGESTION_STATUSES = {"new", "reviewed", "accepted_for_plan", "rejected", "monitoring"}
FINAL_CONFIDENCE = {"high", "moderate", "low", "reject"}
RECOMMENDED_ACTIONS = {"ignore", "monitor", "create_plan", "create_experiment"}
REVIEWER_NAMES = ("gpt", "deepseek")
DEFAULT_CONTROL_PLANE_API_BASE = "http://127.0.0.1:8787"
DEFAULT_CONTROL_PLANE_PROJECT_ID = "ashare-dashboard"
CONTROL_PLANE_TASK_MODELS = {
    "gpt-5.5",
    "gpt-5.4",
    "gpt-5.3-codex-spark",
    "deepseek-v4-pro[1m]",
    "deepseek-v4-flash",
}


def _artifact_root(session: Session) -> Path:
    bind = session.get_bind()
    return artifact_root_from_database_url(bind.url.render_as_string(hide_password=False) if bind else None)


def _review_dir(root: Path) -> Path:
    return Path(root) / SUGGESTION_REVIEW_DIR


def _event_analysis_dir(root: Path) -> Path:
    return Path(root) / "event_analysis"


def _parse_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _normalize_claim(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _suggestion_id(*, source_type: str, source_ref: str, claim: str) -> str:
    raw = f"{source_type}|{source_ref}|{_normalize_claim(claim)}"
    return f"suggestion:{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def _coerce_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]


def _make_suggestion(
    *,
    source_type: str,
    source_ref: str,
    category: str,
    claim: str,
    proposed_change: str,
    evidence_refs: list[str],
    symbol: str | None = None,
    raw_source: dict[str, Any] | None = None,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    normalized_category = category if category in SUGGESTION_CATEGORIES else "operations_workflow"
    suggestion_id = _suggestion_id(source_type=source_type, source_ref=source_ref, claim=claim)
    return {
        "suggestion_id": suggestion_id,
        "source_type": source_type,
        "source_ref": source_ref,
        "symbol": symbol,
        "category": normalized_category,
        "claim": claim.strip(),
        "proposed_change": proposed_change.strip(),
        "evidence_refs": evidence_refs,
        "status": "new",
        "created_at": (created_at or utcnow()).isoformat(),
        "raw_source": raw_source or {},
    }


def _category_from_text(text: str) -> str:
    lowered = text.lower()
    if any(token in text for token in ("首页", "展示", "文案", "话术", "解释", "可视化")):
        return "risk_display" if "风险" in text else "ui_explanation"
    if any(token in text for token in ("数据", "缺失", "覆盖", "stale", "freshness", "新闻缺")):
        return "data_quality"
    if any(token in text for token in ("RankIC", "验证", "样本", "回测", "正超额")):
        return "research_validation"
    if any(token in text for token in ("权重", "weight", "因子权重")) or "factor_weight" in lowered:
        return "factor_weight_experiment"
    if "horizon" in lowered or "周期" in text:
        return "horizon_experiment"
    return "operations_workflow"


def _claim_from_text(text: str, *, fallback: str) -> str:
    cleaned = " ".join(text.strip().split())
    return cleaned[:180] if cleaned else fallback


def _collect_event_suggestions(root: Path, *, cutoff: datetime) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    base = _event_analysis_dir(root)
    if not base.exists():
        return suggestions
    for symbol_dir in sorted(path for path in base.iterdir() if path.is_dir()):
        symbol = symbol_dir.name
        for artifact_path in sorted(symbol_dir.glob("*.json")):
            if artifact_path.name == "index.json":
                continue
            try:
                artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            generated_at = _parse_dt(artifact.get("generated_at")) or _parse_dt(artifact.get("triggered_at"))
            if generated_at and generated_at < cutoff:
                continue
            suggestion = str(artifact.get("correction_suggestion") or "").strip()
            if not suggestion:
                continue
            ref = f"event_analysis/{symbol}/{artifact_path.name}"
            suggestions.append(
                _make_suggestion(
                    source_type="event_analysis",
                    source_ref=ref,
                    symbol=symbol,
                    category=_category_from_text(suggestion),
                    claim=_claim_from_text(suggestion, fallback=f"{symbol} 事件分析提出修正建议"),
                    proposed_change=suggestion,
                    evidence_refs=[ref],
                    raw_source={
                        "trigger_type": artifact.get("trigger_type"),
                        "independent_direction": artifact.get("independent_direction"),
                        "confidence": artifact.get("confidence"),
                    },
                    created_at=generated_at,
                )
            )
    return suggestions


def _collect_manual_research_suggestions(session: Session, root: Path, *, cutoff: datetime) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    requests = session.scalars(
        select(ManualResearchRequest)
        .where(ManualResearchRequest.artifact_id.is_not(None))
        .order_by(ManualResearchRequest.completed_at.desc().nullslast())
    ).all()
    for manual_request in requests:
        created_at = manual_request.completed_at or manual_request.requested_at
        if created_at and _parse_dt(created_at) and _parse_dt(created_at) < cutoff:
            continue
        artifact = read_manual_research_artifact_if_exists(manual_request.artifact_id, root=root)
        if artifact is None or not artifact.decision_note:
            continue
        note = str(artifact.decision_note).strip()
        if not note:
            continue
        ref = f"manual_review/{artifact.artifact_id}"
        suggestions.append(
            _make_suggestion(
                source_type="manual_review",
                source_ref=ref,
                symbol=manual_request.symbol,
                category=_category_from_text(note),
                claim=_claim_from_text(note, fallback=f"{manual_request.symbol} 人工研究提出改进建议"),
                proposed_change=note,
                evidence_refs=[ref, *(artifact.citations or [])],
                raw_source={"review_verdict": artifact.review_verdict, "summary": artifact.summary},
                created_at=_parse_dt(created_at),
            )
        )
    return suggestions


def _collect_validation_suggestions(session: Session) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    try:
        candidates = list_candidate_recommendations(session, limit=20)
    except Exception:
        return suggestions
    for item in candidates.get("items", []):
        rank_ic = item.get("validation_rank_ic_mean")
        pos_excess = item.get("validation_positive_excess_rate")
        symbol = item.get("symbol")
        if isinstance(rank_ic, (int, float)) and isinstance(pos_excess, (int, float)):
            if float(rank_ic) < 0 and float(pos_excess) > 0.55:
                claim = (
                    f"{symbol} 存在 RankIC 为负但正超额占比偏高的验证冲突，"
                    "需要在展示和研究验证中优先解释。"
                )
                suggestions.append(
                    _make_suggestion(
                        source_type="validation_conflict",
                        source_ref=f"validation_conflict/{symbol}/{item.get('validation_artifact_id') or 'latest'}",
                        symbol=str(symbol),
                        category="research_validation",
                        claim=claim,
                        proposed_change="将该冲突纳入候选风险、单票解释和后续实验计划，避免把方向受益误读为排序能力成立。",
                        evidence_refs=[
                            str(item.get("validation_artifact_id") or ""),
                            str(item.get("validation_manifest_id") or ""),
                        ],
                        raw_source={"rank_ic_mean": rank_ic, "positive_excess_rate": pos_excess},
                    )
                )
    return suggestions


def _collect_data_quality_suggestions(session: Session) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    for symbol in active_watchlist_symbols(session):
        stock = session.scalar(select(Stock).where(Stock.symbol == symbol))
        if stock is None:
            continue
        try:
            dashboard = get_stock_dashboard(session, symbol)
            as_of = _parse_dt(dashboard["recommendation"]["as_of_data_time"]) or utcnow()
            quality = build_stock_data_quality(session, stock, as_of=as_of)
        except Exception:
            continue
        if quality.get("status") == "pass":
            continue
        degraded_sources = _coerce_list(quality.get("degraded_sources"))
        if not degraded_sources:
            continue
        claim = f"{symbol} 数据质量为 {quality.get('status')}，降级来源：{', '.join(degraded_sources)}。"
        suggestions.append(
            _make_suggestion(
                source_type="data_quality",
                source_ref=f"data_quality/{symbol}/{quality.get('as_of') or 'latest'}",
                symbol=symbol,
                category="data_quality",
                claim=claim,
                proposed_change="优先补齐或突出该股票的数据覆盖缺口，避免低质量数据被误读为稳定建议。",
                evidence_refs=[f"data_quality/{symbol}"],
                raw_source=quality,
            )
        )
    return suggestions


def _collect_launch_gate_suggestions(session: Session) -> list[dict[str, Any]]:
    try:
        from ashare_evidence.operations import build_operations_summary

        operations = build_operations_summary(session)
    except Exception:
        return []
    suggestions: list[dict[str, Any]] = []
    for gate in operations.get("launch_gates", []):
        if gate.get("status") not in {"warn", "fail"}:
            continue
        gate_name = str(gate.get("gate") or "未命名门禁")
        suggestions.append(
            _make_suggestion(
                source_type="launch_gate",
                source_ref=f"launch_gate/{gate_name}",
                category="operations_workflow",
                claim=f"运营门禁 {gate_name} 当前为 {gate.get('status')}，需要形成改进计划。",
                proposed_change=str(gate.get("threshold") or gate.get("current_value") or "补齐运营门禁对应的验收项。"),
                evidence_refs=[f"launch_gate/{gate_name}"],
                raw_source=dict(gate),
            )
        )
    return suggestions


def collect_improvement_suggestions(session: Session, *, root: Path | None = None, window_days: int = 7) -> list[dict[str, Any]]:
    artifact_root = root or _artifact_root(session)
    cutoff = utcnow() - timedelta(days=window_days)
    collected: list[dict[str, Any]] = []
    collected.extend(_collect_event_suggestions(artifact_root, cutoff=cutoff))
    collected.extend(_collect_manual_research_suggestions(session, artifact_root, cutoff=cutoff))
    collected.extend(_collect_validation_suggestions(session))
    collected.extend(_collect_data_quality_suggestions(session))
    collected.extend(_collect_launch_gate_suggestions(session))

    deduped: dict[str, dict[str, Any]] = {}
    for item in collected:
        existing = deduped.get(item["suggestion_id"])
        if existing is None:
            deduped[item["suggestion_id"]] = item
            continue
        existing["evidence_refs"] = sorted(set(existing.get("evidence_refs", []) + item.get("evidence_refs", [])))
    return sorted(deduped.values(), key=lambda item: str(item.get("created_at", "")), reverse=True)


def _select_reviewer_key(session: Session, reviewer: str) -> ModelApiKey | None:
    keys = session.scalars(
        select(ModelApiKey)
        .where(ModelApiKey.enabled.is_(True))
        .order_by(ModelApiKey.is_default.desc(), ModelApiKey.priority.asc(), ModelApiKey.id.asc())
    ).all()
    if reviewer == "gpt":
        return next(
            (
                key for key in keys
                if "gpt" in key.model_name.lower()
                or "openai" in key.provider_name.lower()
                or "openai" in key.base_url.lower()
            ),
            None,
        )
    if reviewer == "deepseek":
        return next(
            (
                key for key in keys
                if "deepseek" in key.model_name.lower()
                or "deepseek" in key.provider_name.lower()
                or "deepseek" in key.base_url.lower()
            ),
            None,
        )
    return None


def _review_prompt(suggestion: dict[str, Any], reviewer: str) -> str:
    focus = (
        "工程实现可行性、产品清晰度、是否能转成明确开发任务"
        if reviewer == "gpt"
        else "A股语境、金融解释合理性、量化/验证口径风险"
    )
    return "\n".join(
        [
            "你是股票看板改进建议审计员。请只输出 JSON，不要加代码块。",
            f"你的审计重点：{focus}。",
            "不能建议自动改生产权重、horizon、claim gate、买卖方向或自动发布。",
            "字段固定为：reviewer, stance, confidence, main_reason, evidence_refs_used, missing_evidence, implementation_notes, red_flags, safe_to_plan, safe_to_auto_apply。",
            f"reviewer 必须是 {reviewer}。",
            "stance 只能是 support | conditional_support | oppose | insufficient_evidence。",
            json.dumps(suggestion, ensure_ascii=False, default=str),
        ]
    )


def parse_reviewer_json(answer: str, *, reviewer: str) -> dict[str, Any]:
    candidates = [answer.strip()]
    if "```" in answer:
        for block in answer.split("```"):
            block = block.strip()
            if not block or block.lower() == "json":
                continue
            candidates.append(block.removeprefix("json").strip())
    parsed: dict[str, Any] | None = None
    for candidate in candidates:
        try:
            maybe = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(maybe, dict):
            parsed = maybe
            break
    if parsed is None:
        return {
            "reviewer": reviewer,
            "stance": "insufficient_evidence",
            "confidence": 0.0,
            "main_reason": "review_failed: model returned non-json output",
            "evidence_refs_used": [],
            "missing_evidence": ["structured_json_review"],
            "implementation_notes": [],
            "red_flags": ["review_failed"],
            "safe_to_plan": False,
            "safe_to_auto_apply": False,
            "status": "review_failed",
        }
    stance = str(parsed.get("stance") or "insufficient_evidence")
    if stance not in {"support", "conditional_support", "oppose", "insufficient_evidence"}:
        stance = "insufficient_evidence"
    try:
        confidence = float(parsed.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "reviewer": reviewer,
        "stance": stance,
        "confidence": max(0.0, min(confidence, 1.0)),
        "main_reason": str(parsed.get("main_reason") or ""),
        "evidence_refs_used": _coerce_list(parsed.get("evidence_refs_used")),
        "missing_evidence": _coerce_list(parsed.get("missing_evidence")),
        "implementation_notes": _coerce_list(parsed.get("implementation_notes")),
        "red_flags": _coerce_list(parsed.get("red_flags")),
        "safe_to_plan": bool(parsed.get("safe_to_plan")),
        "safe_to_auto_apply": False,
        "status": "completed",
    }


def _fallback_review(suggestion: dict[str, Any], reviewer: str, *, reason: str) -> dict[str, Any]:
    return {
        "reviewer": reviewer,
        "stance": "insufficient_evidence",
        "confidence": 0.0,
        "main_reason": reason,
        "evidence_refs_used": [],
        "missing_evidence": ["reviewer_model_key"],
        "implementation_notes": [],
        "red_flags": ["degraded_missing_reviewer"],
        "safe_to_plan": False,
        "safe_to_auto_apply": False,
        "status": "missing_reviewer",
    }


def _transport_for_model_key(key: ModelApiKey) -> Any:
    provider_name = key.provider_name.lower()
    base_url = key.base_url.lower().rstrip("/")
    metadata = key.metadata_payload or {}
    transport_kind = str(metadata.get("transport_kind") or "").lower()
    if (
        transport_kind == "anthropic"
        or provider_name == "anthropic"
        or "/anthropic" in base_url
        or base_url.endswith("anthropic")
    ):
        return AnthropicCompatibleTransport()
    return OpenAICompatibleTransport()


def _run_builtin_gpt_reviewer(suggestion: dict[str, Any], reviewer: str) -> dict[str, Any]:
    from ashare_evidence.manual_research_workflow import _run_builtin_codex_completion
    from ashare_evidence.runtime_config import get_builtin_llm_executor_config

    builtin = get_builtin_llm_executor_config()
    if not builtin["enabled"]:
        return _fallback_review(
            suggestion,
            reviewer,
            reason=f"{reviewer} reviewer model key is not configured and builtin Codex GPT is unavailable.",
        )
    try:
        if builtin.get("transport_kind") == "codex_cli":
            answer = _run_builtin_codex_completion(
                codex_bin=str(builtin["codex_bin"]),
                model_name=str(builtin["model_name"]),
                prompt="\n".join(
                    [
                        "System: You are a strict structured reviewer. Return JSON only.",
                        _review_prompt(suggestion, reviewer),
                    ]
                ),
            )
        else:
            answer = OpenAICompatibleTransport().complete(
                base_url=str(builtin["base_url"]),
                api_key=str(builtin["api_key"]),
                model_name=str(builtin["model_name"]),
                prompt=_review_prompt(suggestion, reviewer),
                system="You are a strict structured reviewer. Return JSON only.",
            )
    except Exception as exc:
        return {
            **_fallback_review(suggestion, reviewer, reason=f"{reviewer} builtin Codex reviewer failed: {exc}"),
            "status": "review_failed",
            "red_flags": ["review_failed"],
        }
    parsed = parse_reviewer_json(answer, reviewer=reviewer)
    parsed["transport_source"] = "builtin_codex_gpt"
    return parsed


def _run_reviewer(session: Session, suggestion: dict[str, Any], reviewer: str) -> dict[str, Any]:
    key = _select_reviewer_key(session, reviewer)
    if key is None:
        if reviewer == "gpt":
            return _run_builtin_gpt_reviewer(suggestion, reviewer)
        return _fallback_review(suggestion, reviewer, reason=f"{reviewer} reviewer model key is not configured.")
    transport = _transport_for_model_key(key)
    try:
        answer = transport.complete(
            base_url=key.base_url,
            api_key=key.api_key,
            model_name=key.model_name,
            prompt=_review_prompt(suggestion, reviewer),
            system="You are a strict structured reviewer. Return JSON only.",
        )
    except Exception as exc:
        return {
            **_fallback_review(suggestion, reviewer, reason=f"{reviewer} reviewer failed: {exc}"),
            "status": "review_failed",
            "red_flags": ["review_failed"],
        }
    return parse_reviewer_json(answer, reviewer=reviewer)


def _consensus(reviews: dict[str, dict[str, Any]]) -> str:
    completed = [review for review in reviews.values() if review.get("status") == "completed"]
    if len(completed) == 0:
        return "unavailable"
    if len(completed) == 1:
        return "partially_aligned"
    stances = {review.get("stance") for review in completed}
    if stances <= {"support", "conditional_support"}:
        return "aligned"
    if "oppose" in stances and ("support" in stances or "conditional_support" in stances):
        return "split"
    return "partially_aligned"


def _evidence_status(suggestion: dict[str, Any], reviews: dict[str, dict[str, Any]]) -> str:
    refs = [ref for ref in suggestion.get("evidence_refs", []) if ref]
    if not refs:
        return "unsupported"
    if any(review.get("missing_evidence") for review in reviews.values() if review.get("status") == "completed"):
        return "needs_more_data"
    return "artifact_backed"


def _recommended_action(category: str, confidence: str, consensus: str) -> str:
    if confidence == "reject":
        return "ignore"
    if category in {"factor_weight_experiment", "horizon_experiment"}:
        return "create_experiment" if confidence in {"high", "moderate"} else "monitor"
    if consensus == "split":
        return "monitor"
    if confidence in {"high", "moderate"}:
        return "create_plan"
    return "monitor"


def summarize_suggestion_review(suggestion: dict[str, Any], reviews: dict[str, dict[str, Any]]) -> dict[str, Any]:
    consensus = _consensus(reviews)
    evidence = _evidence_status(suggestion, reviews)
    completed = [review for review in reviews.values() if review.get("status") == "completed"]
    category = str(suggestion.get("category") or "operations_workflow")
    avg_conf = sum(float(review.get("confidence") or 0.0) for review in completed) / len(completed) if completed else 0.0
    stances = {review.get("stance") for review in completed}
    missing_reviewer = any(review.get("status") != "completed" for review in reviews.values())

    if not completed or "oppose" in stances:
        final_confidence = "reject" if "oppose" in stances and consensus == "split" else "low"
    elif consensus == "aligned" and evidence == "artifact_backed" and avg_conf >= 0.75 and not missing_reviewer:
        final_confidence = "high"
    elif avg_conf >= 0.45 and consensus in {"aligned", "partially_aligned"}:
        final_confidence = "moderate"
    else:
        final_confidence = "low"
    if evidence != "artifact_backed" and final_confidence == "high":
        final_confidence = "moderate"
    if missing_reviewer and final_confidence == "high":
        final_confidence = "moderate"
    action = _recommended_action(category, final_confidence, consensus)
    if category in {"factor_weight_experiment", "horizon_experiment"} and action == "create_plan":
        action = "create_experiment"
    decision_reason = (
        f"模型共识 {consensus}，证据状态 {evidence}，"
        f"完成审计 {len(completed)}/{len(REVIEWER_NAMES)}，平均置信度 {avg_conf:.2f}。"
    )
    return {
        "suggestion_id": suggestion["suggestion_id"],
        "model_consensus": consensus,
        "evidence_status": evidence,
        "final_confidence": final_confidence,
        "recommended_action": action,
        "decision_reason": decision_reason,
        "generated_plan": {
            "title": suggestion["claim"][:80],
            "summary": suggestion["proposed_change"],
            "implementation_steps": [
                "确认来源 artifact 与当前页面/研究口径仍匹配。",
                "按建议类别修改展示、数据质量或研究实验入口。",
                "补充回归测试并在 Operations 页面验收。",
            ],
            "tests": [
                "建议抽取和去重单测",
                "Operations 审计台展示测试",
                "相关 API 权限和筛选测试",
            ],
            "blocked_by": [] if evidence == "artifact_backed" else ["需要补充真实证据或样本"],
        },
    }


def _snapshot_counts(items: list[dict[str, Any]]) -> dict[str, Any]:
    confidence = Counter(item.get("final_confidence", "low") for item in items)
    categories = Counter(item.get("category", "operations_workflow") for item in items)
    statuses = Counter(item.get("status", "new") for item in items)
    return {
        "total": len(items),
        "reviewed": sum(1 for item in items if item.get("reviews")),
        "high_confidence": int(confidence.get("high", 0)),
        "moderate_confidence": int(confidence.get("moderate", 0)),
        "low_confidence": int(confidence.get("low", 0)),
        "reject": int(confidence.get("reject", 0)),
        "model_split": sum(1 for item in items if item.get("model_consensus") == "split"),
        "needs_more_data": sum(1 for item in items if item.get("evidence_status") == "needs_more_data"),
        "by_category": dict(categories),
        "by_status": dict(statuses),
    }


def _write_snapshot(root: Path, snapshot: dict[str, Any]) -> Path:
    directory = _review_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{datetime.now(UTC):%Y%m%dT%H%M%S}_suggestion_review.json"
    path = directory / filename
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    index_path = directory / "index.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else []
    except (json.JSONDecodeError, OSError):
        index = []
    index.append(
        {
            "file": filename,
            "generated_at": snapshot["generated_at"],
            "status": snapshot["status"],
            "suggestion_count": snapshot["summary"]["total"],
            "reviewed_count": snapshot["summary"]["reviewed"],
        }
    )
    index.sort(key=lambda item: str(item.get("generated_at", "")), reverse=True)
    index_path.write_text(json.dumps(index[:20], ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


def latest_suggestion_review_snapshot(*, root: Path) -> dict[str, Any] | None:
    directory = _review_dir(root)
    index_path = directory / "index.json"
    if not index_path.exists():
        return None
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not index:
        return None
    index.sort(key=lambda item: str(item.get("generated_at", "")), reverse=True)
    path = directory / str(index[0].get("file", ""))
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    payload["_snapshot_file"] = path.name
    return payload


def empty_suggestion_review_snapshot() -> dict[str, Any]:
    return {
        "artifact_type": REVIEW_SNAPSHOT_TYPE,
        "generated_at": utcnow().isoformat(),
        "status": "empty",
        "window_days": 7,
        "model_status": {
            "gpt": "missing_reviewer",
            "deepseek": "missing_reviewer",
            "overall": "no_snapshot",
        },
        "summary": _snapshot_counts([]),
        "suggestions": [],
    }


def run_improvement_suggestion_review(
    session: Session,
    *,
    root: Path | None = None,
    window_days: int = 7,
    reviewer_overrides: dict[str, dict[str, Any]] | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    artifact_root = root or _artifact_root(session)
    suggestions = collect_improvement_suggestions(session, root=artifact_root, window_days=window_days)
    reviewed_items: list[dict[str, Any]] = []
    reviewer_overrides = reviewer_overrides or {}
    for suggestion in suggestions:
        reviews: dict[str, dict[str, Any]] = {}
        for reviewer in REVIEWER_NAMES:
            if reviewer in reviewer_overrides:
                override = dict(reviewer_overrides[reviewer])
                override.setdefault("reviewer", reviewer)
                override.setdefault("status", "completed")
                override.setdefault("safe_to_auto_apply", False)
                reviews[reviewer] = parse_reviewer_json(json.dumps(override, ensure_ascii=False), reviewer=reviewer)
            else:
                reviews[reviewer] = _run_reviewer(session, suggestion, reviewer)
        summary = summarize_suggestion_review(suggestion, reviews)
        reviewed_items.append(
            {
                **suggestion,
                **summary,
                "status": "reviewed",
                "reviews": reviews,
            }
        )
    missing = {
        reviewer: any(item.get("reviews", {}).get(reviewer, {}).get("status") != "completed" for item in reviewed_items)
        for reviewer in REVIEWER_NAMES
    }
    overall_status = "ok"
    if any(missing.values()):
        overall_status = "degraded_missing_reviewer"
    snapshot = {
        "artifact_type": REVIEW_SNAPSHOT_TYPE,
        "companion_artifact_types": [LEDGER_SNAPSHOT_TYPE, PLAN_SNAPSHOT_TYPE],
        "generated_at": utcnow().isoformat(),
        "status": overall_status,
        "window_days": window_days,
        "model_status": {
            "gpt": "missing_reviewer" if missing["gpt"] else "ok",
            "deepseek": "missing_reviewer" if missing["deepseek"] else "ok",
            "overall": overall_status,
        },
        "summary": _snapshot_counts(reviewed_items),
        "suggestions": reviewed_items,
    }
    if persist:
        path = _write_snapshot(artifact_root, snapshot)
        snapshot["_snapshot_file"] = path.name
    return snapshot


def suggestion_summary(session: Session) -> dict[str, Any]:
    root = _artifact_root(session)
    snapshot = latest_suggestion_review_snapshot(root=root) or empty_suggestion_review_snapshot()
    top_items = sorted(
        snapshot.get("suggestions", []),
        key=lambda item: (
            {"high": 3, "moderate": 2, "low": 1, "reject": 0}.get(str(item.get("final_confidence")), 0),
            str(item.get("created_at", "")),
        ),
        reverse=True,
    )[:5]
    return {
        "generated_at": snapshot.get("generated_at"),
        "status": snapshot.get("status"),
        "snapshot_file": snapshot.get("_snapshot_file"),
        "window_days": snapshot.get("window_days", 7),
        "model_status": snapshot.get("model_status", {}),
        "summary": snapshot.get("summary", _snapshot_counts([])),
        "top_suggestions": top_items,
    }


def suggestion_details(session: Session, *, status: str | None = None, category: str | None = None) -> dict[str, Any]:
    root = _artifact_root(session)
    snapshot = latest_suggestion_review_snapshot(root=root) or empty_suggestion_review_snapshot()
    items = list(snapshot.get("suggestions", []))
    if status:
        items = [item for item in items if item.get("status") == status]
    if category:
        items = [item for item in items if item.get("category") == category]
    return {
        "generated_at": snapshot.get("generated_at"),
        "status": snapshot.get("status"),
        "snapshot_file": snapshot.get("_snapshot_file"),
        "model_status": snapshot.get("model_status", {}),
        "summary": snapshot.get("summary", _snapshot_counts([])),
        "suggestions": items,
    }


def _latest_suggestion_item(session: Session, suggestion_id: str) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    root = _artifact_root(session)
    snapshot = latest_suggestion_review_snapshot(root=root)
    if snapshot is None or not snapshot.get("_snapshot_file"):
        raise LookupError("No suggestion review snapshot available.")
    for item in snapshot.get("suggestions", []):
        if item.get("suggestion_id") == suggestion_id:
            return root, snapshot, item
    raise LookupError(f"Suggestion {suggestion_id} not found.")


def _write_suggestion_snapshot(root: Path, snapshot: dict[str, Any]) -> None:
    path = _review_dir(root) / str(snapshot["_snapshot_file"])
    path.write_text(
        json.dumps({k: v for k, v in snapshot.items() if k != "_snapshot_file"}, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def _review_reason(item: dict[str, Any], reviewer: str) -> str:
    review = (item.get("reviews") or {}).get(reviewer) or {}
    if not review:
        return "未返回审计。"
    return "\n".join(
        part for part in [
            f"stance: {review.get('stance')}",
            f"confidence: {review.get('confidence')}",
            f"main_reason: {review.get('main_reason')}",
            "missing_evidence: " + "；".join(_coerce_list(review.get("missing_evidence"))),
            "implementation_notes: " + "；".join(_coerce_list(review.get("implementation_notes"))),
            "red_flags: " + "；".join(_coerce_list(review.get("red_flags"))),
        ] if part.strip()
    )


def _build_control_plane_task_description(item: dict[str, Any], *, selected_model: str) -> str:
    plan = item.get("generated_plan") or {}
    implementation_steps = _coerce_list(plan.get("implementation_steps"))
    tests = _coerce_list(plan.get("tests"))
    blocked_by = _coerce_list(plan.get("blocked_by"))
    evidence_refs = _coerce_list(item.get("evidence_refs"))
    return "\n".join(
        [
            "请根据股票看板改进建议审计台中已进入计划池的建议，先进入 Plan 模式生成可审视计划。",
            "",
            "关键约束：",
            "- 本任务必须启用 Plan 模式；在用户审视并确认 plan 前不得开始实现。",
            "- 不自动修改生产因子权重、horizon、claim gate、买卖方向或发布策略。",
            "- 若计划涉及股票看板 live-facing 改动，完成时必须发布到运行态并做真实页面验收。",
            "",
            f"建议 ID: {item.get('suggestion_id')}",
            f"来源: {item.get('source_type')} / {item.get('source_ref')}",
            f"标的: {item.get('symbol') or '全局'}",
            f"分类: {item.get('category')}",
            f"最终置信度: {item.get('final_confidence')}",
            f"推荐动作: {item.get('recommended_action')}",
            f"模型共识: {item.get('model_consensus')}",
            f"证据状态: {item.get('evidence_status')}",
            f"选择执行模型: {selected_model}",
            "",
            "页面中的建议标题：",
            str(item.get("claim") or ""),
            "",
            "页面中的建议内容：",
            str(item.get("proposed_change") or ""),
            "",
            "最终判断：",
            str(item.get("decision_reason") or ""),
            "",
            "证据引用：",
            *(f"- {ref}" for ref in evidence_refs),
            "",
            "GPT 审计：",
            _review_reason(item, "gpt"),
            "",
            "DeepSeek 审计：",
            _review_reason(item, "deepseek"),
            "",
            "生成的开发计划：",
            f"标题: {plan.get('title') or item.get('claim') or ''}",
            f"摘要: {plan.get('summary') or item.get('proposed_change') or ''}",
            "",
            "实施步骤：",
            *(f"{index + 1}. {step}" for index, step in enumerate(implementation_steps)),
            "",
            "测试：",
            *(f"- {test}" for test in tests),
            "",
            "阻塞项：",
            *(f"- {blocked}" for blocked in blocked_by),
        ]
    )


def _control_plane_api_base() -> str:
    return (os.getenv("ASHARE_CONTROL_PLANE_API_BASE") or DEFAULT_CONTROL_PLANE_API_BASE).strip().rstrip("/")


def _control_plane_project_id() -> str:
    return (os.getenv("ASHARE_CONTROL_PLANE_PROJECT_ID") or DEFAULT_CONTROL_PLANE_PROJECT_ID).strip()


def _post_control_plane_task(payload: dict[str, Any], *, api_base: str | None = None) -> dict[str, Any]:
    base = (api_base or _control_plane_api_base()).rstrip("/")
    endpoint = f"{base}/api/tasks"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    http_request = request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(http_request, timeout=30, disable_proxies=True) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore") or str(exc)
        raise RuntimeError(f"Control-plane task creation failed with HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Control-plane task creation failed: {exc.reason}") from exc


def accept_suggestion_for_plan(
    session: Session,
    *,
    suggestion_id: str,
    model: str,
    reason: str,
    api_base: str | None = None,
) -> dict[str, Any]:
    normalized_model = (model or "gpt-5.4").strip()
    if normalized_model not in CONTROL_PLANE_TASK_MODELS:
        raise ValueError(f"Unsupported task model: {model}")
    if not reason.strip():
        raise ValueError("reason is required.")
    root, snapshot, target = _latest_suggestion_item(session, suggestion_id)
    title = f"[股票看板计划池] {str(target.get('claim') or '改进建议')[:72]}"
    description = _build_control_plane_task_description(target, selected_model=normalized_model)
    provider = "deepseek" if "deepseek" in normalized_model.lower() else None
    task_payload = {
        "projectId": _control_plane_project_id(),
        "type": "task",
        "title": title,
        "description": description,
        "model": normalized_model,
        "requestedModel": normalized_model,
        "reasoningEffort": "high",
        "planMode": True,
        "approvalRequired": True,
        "decisionNotes": f"Created from stock-dashboard suggestion {suggestion_id}.",
        "acceptanceCriteria": [
            {"id": "plan-first", "text": "中台任务必须先生成 Plan，并等待用户确认后再执行。"},
            {"id": "source-preserved", "text": "任务描述必须保留建议、证据、双模型审计和生成计划。"},
            {"id": "stock-live-verified", "text": "如涉及股票看板 live-facing 改动，必须发布运行态并浏览器验收。"},
        ],
        "result": {
            "sourceSystem": "stock_dashboard",
            "sourceArtifactType": REVIEW_SNAPSHOT_TYPE,
            "sourceSnapshotFile": snapshot.get("_snapshot_file"),
            "suggestionId": suggestion_id,
        },
    }
    if provider:
        task_payload["provider"] = provider
    created = _post_control_plane_task(task_payload, api_base=api_base)
    task = created.get("task") if isinstance(created, dict) else {}
    target["status"] = "accepted_for_plan"
    target["control_plane_task"] = {
        "id": str((task or {}).get("id") or ""),
        "title": str((task or {}).get("title") or title),
        "status": str((task or {}).get("status") or ""),
        "model": normalized_model,
        "project_id": _control_plane_project_id(),
        "plan_mode": True,
        "api_base": api_base or _control_plane_api_base(),
    }
    history = list(target.get("status_history") or [])
    history.append(
        {
            "status": "accepted_for_plan",
            "reason": reason.strip(),
            "updated_at": utcnow().isoformat(),
            "control_plane_task_id": target["control_plane_task"]["id"],
            "model": normalized_model,
        }
    )
    target["status_history"] = history
    snapshot["summary"] = _snapshot_counts(snapshot.get("suggestions", []))
    _write_suggestion_snapshot(root, snapshot)
    return target


def update_suggestion_status(
    session: Session,
    *,
    suggestion_id: str,
    status: str,
    reason: str,
) -> dict[str, Any]:
    if status not in {"accepted_for_plan", "rejected", "monitoring"}:
        raise ValueError("status must be accepted_for_plan, rejected, or monitoring.")
    if not reason.strip():
        raise ValueError("reason is required.")
    root, snapshot, target = _latest_suggestion_item(session, suggestion_id)
    target["status"] = status
    history = list(target.get("status_history") or [])
    history.append({"status": status, "reason": reason.strip(), "updated_at": utcnow().isoformat()})
    target["status_history"] = history
    snapshot["summary"] = _snapshot_counts(snapshot.get("suggestions", []))
    _write_suggestion_snapshot(root, snapshot)
    return target
