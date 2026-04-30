from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ashare_evidence.contract_status import (
    MANUAL_REVIEW_COMPLETED,
    MANUAL_REVIEW_FAILED,
    MANUAL_REVIEW_STALE,
    MANUAL_TRIGGER_REQUIRED,
)
from ashare_evidence.models import ManualResearchRequest, Recommendation
from ashare_evidence.phase2 import PHASE2_MANUAL_REVIEW_NOTE
from ashare_evidence.research_artifact_store import read_manual_research_artifact_if_exists

EXECUTOR_KIND_BUILTIN_GPT = "builtin_gpt"
EXECUTOR_KIND_CONFIGURED_API_KEY = "configured_api_key"

_SANITIZE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"manual-review:[A-Za-z0-9:_-]+"), "人工研究记录"),
    (re.compile(r"validation-metrics:[A-Za-z0-9:_-]+"), "验证指标记录"),
    (re.compile(r"rolling-validation:[A-Za-z0-9:_-]+"), "滚动验证记录"),
    (re.compile(r"replay-alignment:[A-Za-z0-9:_-]+"), "复盘记录"),
    (re.compile(r"portfolio-backtest:[A-Za-z0-9:_-]+"), "组合回测记录"),
)
_SANITIZE_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("pending_rebuild", "口径校准中"),
    ("research_rebuild_pending", "滚动验证口径校准中"),
    ("forward_excess_return_20d", "20日超额收益"),
    ("14-56 个交易日（研究窗口待批准）", "观察窗口以滚动验证结论为准"),
    ("14-56 个交易日", "观察窗口以滚动验证结论为准"),
    ("14-56 trade days", "the window under rolling validation"),
    ("Phase 5 baseline", "等权组合研究策略"),
    ("research contract", "研究口径"),
)


def sanitize_manual_review_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    for pattern, replacement in _SANITIZE_PATTERNS:
        cleaned = pattern.sub(replacement, cleaned)
    for source, target in _SANITIZE_REPLACEMENTS:
        cleaned = cleaned.replace(source, target)
    return cleaned


def _sanitize_manual_review_list(items: list[str]) -> list[str]:
    sanitized: list[str] = []
    for item in items:
        cleaned = sanitize_manual_review_text(item)
        if cleaned:
            sanitized.append(cleaned)
    return sanitized


def build_manual_review_source_packet(
    recommendation: Recommendation,
    *,
    payload: dict[str, Any],
    historical_validation: dict[str, Any],
) -> list[str]:
    core_quant = dict(payload.get("core_quant") or {})
    target_horizon = (
        core_quant.get("target_horizon_label")
        or f"{recommendation.horizon_min_days}-{recommendation.horizon_max_days} trade days"
    )
    return [
        f"recommendation_key:{recommendation.recommendation_key}",
        f"direction:{recommendation.direction}",
        f"confidence_label:{recommendation.confidence_label}",
        f"target_horizon:{target_horizon}",
        f"primary_model_result_key:{payload.get('primary_model_result_key') or 'missing'}",
        f"validation_artifact_id:{historical_validation.get('artifact_id') or 'missing'}",
        f"validation_manifest_id:{historical_validation.get('manifest_id') or 'missing'}",
    ]


def compute_source_packet_hash(source_packet: list[str]) -> str:
    encoded = json.dumps(source_packet, ensure_ascii=False, separators=(",", ":"), sort_keys=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def manual_research_stale_reason(
    request: ManualResearchRequest,
    *,
    recommendation_key: str,
    validation_artifact_id: str | None,
    validation_manifest_id: str | None,
    source_packet_hash: str,
) -> str | None:
    if request.recommendation_key != recommendation_key:
        return (
            "recommendation context changed: "
            f"{request.recommendation_key} -> {recommendation_key}"
        )
    if request.validation_artifact_id != validation_artifact_id:
        return "validation_artifact_id changed after the manual review completed."
    if request.validation_manifest_id != validation_manifest_id:
        return "validation_manifest_id changed after the manual review completed."
    if request.source_packet_hash != source_packet_hash:
        return "follow-up research packet hash changed after the manual review completed."
    return None


def _placeholder(source_packet: list[str]) -> dict[str, Any]:
    return {
        "status": MANUAL_TRIGGER_REQUIRED,
        "trigger_mode": "manual",
        "model_label": "Manual research workflow",
        "requested_at": None,
        "generated_at": None,
        "summary": PHASE2_MANUAL_REVIEW_NOTE,
        "risks": [],
        "disagreements": [],
        "source_packet": source_packet,
        "artifact_id": None,
        "question": None,
        "raw_answer": None,
        "request_id": None,
        "request_key": None,
        "executor_kind": None,
        "status_note": "No manual research request has been created for the current recommendation context.",
        "review_verdict": None,
        "decision_note": None,
        "stale_reason": None,
        "citations": [],
    }


def _model_label(request: ManualResearchRequest, artifact: Any | None) -> str:
    if artifact is not None and isinstance(getattr(artifact, "selected_key", None), dict):
        provider_name = artifact.selected_key.get("provider_name")
        model_name = artifact.selected_key.get("model_name")
        if provider_name and model_name:
            return f"{provider_name}:{model_name}"
    if request.executor_kind == EXECUTOR_KIND_BUILTIN_GPT:
        return "builtin_gpt"
    if request.model_api_key is not None:
        return f"{request.model_api_key.provider_name}:{request.model_api_key.model_name}"
    return request.executor_kind


def _build_request_projection(
    request: ManualResearchRequest,
    *,
    status: str,
    status_note: str | None,
    stale_reason: str | None,
    artifact_root: Any = None,
) -> dict[str, Any]:
    artifact = read_manual_research_artifact_if_exists(request.artifact_id, root=artifact_root)
    if status == MANUAL_REVIEW_COMPLETED and artifact is None:
        status = MANUAL_REVIEW_FAILED
        status_note = "Manual review request was marked completed, but the artifact is missing."

    summary = None
    risks: list[str] = []
    disagreements: list[str] = []
    question = request.question
    raw_answer = None
    generated_at = request.completed_at
    review_verdict = None
    decision_note = None
    citations: list[str] = []
    if artifact is not None:
        summary = sanitize_manual_review_text(artifact.summary)
        risks = _sanitize_manual_review_list([str(item) for item in artifact.risks if item])
        disagreements = _sanitize_manual_review_list([str(item) for item in artifact.disagreements if item])
        question = artifact.question
        raw_answer = sanitize_manual_review_text(artifact.answer)
        generated_at = artifact.generated_at
        review_verdict = artifact.review_verdict
        decision_note = sanitize_manual_review_text(artifact.decision_note)
        citations = _sanitize_manual_review_list([str(item) for item in artifact.citations if item])

    return {
        "status": status,
        "trigger_mode": "manual",
        "model_label": _model_label(request, artifact),
        "requested_at": request.requested_at,
        "generated_at": generated_at,
        "summary": summary,
        "risks": risks,
        "disagreements": disagreements,
        "source_packet": [str(item) for item in request.request_payload.get("source_packet", []) if item],
        "artifact_id": request.artifact_id,
        "question": question,
        "raw_answer": raw_answer,
        "request_id": request.id,
        "request_key": request.request_key,
        "executor_kind": request.executor_kind,
        "status_note": sanitize_manual_review_text(status_note),
        "review_verdict": review_verdict,
        "decision_note": decision_note,
        "stale_reason": sanitize_manual_review_text(stale_reason),
        "citations": citations,
    }


def build_manual_llm_review_projection(
    session: Session,
    recommendation: Recommendation,
    *,
    payload: dict[str, Any],
    historical_validation: dict[str, Any],
    artifact_root: Any = None,
) -> dict[str, Any]:
    source_packet = build_manual_review_source_packet(
        recommendation,
        payload=payload,
        historical_validation=historical_validation,
    )
    source_packet_hash = compute_source_packet_hash(source_packet)
    requests = session.scalars(
        select(ManualResearchRequest)
        .where(
            ManualResearchRequest.symbol == recommendation.stock.symbol,
            ManualResearchRequest.superseded_by_request_id.is_(None),
        )
        .options(joinedload(ManualResearchRequest.model_api_key))
        .order_by(ManualResearchRequest.requested_at.desc(), ManualResearchRequest.id.desc())
    ).all()

    current_requests = [item for item in requests if item.recommendation_key == recommendation.recommendation_key]
    if current_requests:
        current = current_requests[0]
        stale_reason = None
        status = current.status
        if current.status == MANUAL_REVIEW_COMPLETED:
            stale_reason = manual_research_stale_reason(
                current,
                recommendation_key=recommendation.recommendation_key,
                validation_artifact_id=historical_validation.get("artifact_id"),
                validation_manifest_id=historical_validation.get("manifest_id"),
                source_packet_hash=source_packet_hash,
            )
            if stale_reason:
                status = MANUAL_REVIEW_STALE
        return _build_request_projection(
            current,
            status=status,
            status_note=current.status_note,
            stale_reason=stale_reason,
            artifact_root=artifact_root,
        )

    latest_completed = next((item for item in requests if item.status == MANUAL_REVIEW_COMPLETED), None)
    if latest_completed is not None:
        stale_reason = manual_research_stale_reason(
            latest_completed,
            recommendation_key=recommendation.recommendation_key,
            validation_artifact_id=historical_validation.get("artifact_id"),
            validation_manifest_id=historical_validation.get("manifest_id"),
            source_packet_hash=source_packet_hash,
        )
        if stale_reason:
            return _build_request_projection(
                latest_completed,
                status=MANUAL_REVIEW_STALE,
                status_note=latest_completed.status_note,
                stale_reason=stale_reason,
                artifact_root=artifact_root,
            )

    return _placeholder(source_packet)
