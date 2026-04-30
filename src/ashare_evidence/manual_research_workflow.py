from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
import subprocess
import tempfile
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ashare_evidence.contract_status import (
    MANUAL_REVIEW_COMPLETED,
    MANUAL_REVIEW_FAILED,
    MANUAL_REVIEW_IN_PROGRESS,
    MANUAL_REVIEW_QUEUED,
    STATUS_PENDING_REBUILD,
)
from ashare_evidence.dashboard import get_stock_dashboard
from ashare_evidence.db import utcnow
from ashare_evidence.llm_service import OpenAICompatibleTransport, _build_follow_up_prompt
from ashare_evidence.manual_research_contract import (
    EXECUTOR_KIND_BUILTIN_GPT,
    EXECUTOR_KIND_CONFIGURED_API_KEY,
    _build_request_projection,
    build_manual_review_source_packet,
    build_manual_llm_review_projection,
    compute_source_packet_hash,
    manual_research_stale_reason,
)
from ashare_evidence.models import ManualResearchRequest, ModelApiKey, Recommendation, Stock
from ashare_evidence.recommendation_selection import (
    collapse_recommendation_history,
    recommendation_recency_ordering,
)
from ashare_evidence.research_artifact_store import (
    artifact_root_from_database_url,
    write_manual_research_artifact,
)
from ashare_evidence.research_artifacts import ManualResearchArtifactView
from ashare_evidence.runtime_config import (
    get_builtin_llm_executor_config,
    record_model_api_key_result,
    resolve_llm_key_candidates,
)
from ashare_evidence.services import _build_historical_validation

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BUILTIN_CODEX_TIMEOUT_SECONDS = 180
BUILTIN_CODEX_QUEUED_STATUS_NOTE = "builtin_gpt request is queued for local Codex execution."


def _artifact_root(session: Session) -> Any:
    bind = session.get_bind()
    return artifact_root_from_database_url(bind.url.render_as_string(hide_password=False) if bind else None)


def _latest_recommendation(session: Session, symbol: str) -> Recommendation:
    recommendations = session.scalars(
        select(Recommendation)
        .join(Stock)
        .where(Stock.symbol == symbol)
        .options(joinedload(Recommendation.stock))
        .order_by(*recommendation_recency_ordering())
    ).all()
    history = collapse_recommendation_history(recommendations, limit=1)
    recommendation = history[0] if history else None
    if recommendation is None:
        raise LookupError(f"No recommendation found for {symbol}.")
    return recommendation


def _request_prompt(summary: dict[str, Any], question: str) -> str:
    base_prompt = _build_follow_up_prompt(summary, question)
    output_contract = """

请只输出一个 JSON 对象，不要加代码块。字段固定为：
- review_verdict: supports_current_recommendation | mixed | contradicts_current_recommendation | insufficient_evidence
- summary: 一段简洁总结
- risks: 字符串数组
- disagreements: 字符串数组
- decision_note: 一段解释这份人工研究应该如何使用
- citations: 字符串数组
- answer: 保留完整解释文本
"""
    return f"{base_prompt.rstrip()}\n{output_contract.strip()}"


def _latest_request(session: Session, request_id: int) -> ManualResearchRequest:
    request = session.scalar(
        select(ManualResearchRequest)
        .where(ManualResearchRequest.id == request_id)
        .options(joinedload(ManualResearchRequest.model_api_key))
    )
    if request is None:
        raise LookupError(f"Manual research request {request_id} not found.")
    return request


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
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {
        "review_verdict": "insufficient_evidence",
        "summary": text,
        "risks": [],
        "disagreements": [],
        "decision_note": "The executor returned unstructured text, so the product contract fell back to raw answer mode.",
        "citations": [],
        "answer": text,
    }


def _coerce_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]


def _current_recommendation_context(
    recommendation: Recommendation,
    *,
    artifact_root: Any = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = dict(recommendation.recommendation_payload or {})
    historical_validation = _build_historical_validation(
        recommendation,
        payload=payload,
        validation_status=payload.get("validation_status", STATUS_PENDING_REBUILD),
        validation_note=payload.get("validation_note"),
        artifact_root=artifact_root,
    )
    return payload, historical_validation


def _serialize_request(
    session: Session,
    request: ManualResearchRequest,
    *,
    artifact_root: Any = None,
) -> dict[str, Any]:
    recommendation = _latest_recommendation(session, request.symbol)
    payload, historical_validation = _current_recommendation_context(
        recommendation,
        artifact_root=artifact_root,
    )
    current_packet = build_manual_review_source_packet(
        recommendation,
        payload=payload,
        historical_validation=historical_validation,
    )
    stale_reason = None
    status = request.status
    if request.status == MANUAL_REVIEW_COMPLETED:
        stale_reason = manual_research_stale_reason(
            request,
            recommendation_key=recommendation.recommendation_key,
            validation_artifact_id=historical_validation.get("artifact_id"),
            validation_manifest_id=historical_validation.get("manifest_id"),
            source_packet_hash=compute_source_packet_hash(current_packet),
        )
        if stale_reason:
            status = "stale"
    projection = build_manual_llm_review_projection(
        session,
        recommendation,
        payload=payload,
        historical_validation=historical_validation,
        artifact_root=artifact_root,
    )
    if projection.get("request_id") != request.id:
        projection = _build_request_projection(
            request,
            status=status,
            status_note=request.status_note,
            stale_reason=stale_reason,
            artifact_root=artifact_root,
        )
        projection = {
            **projection,
            "status": status,
            "stale_reason": stale_reason,
        }
    return {
        "id": request.id,
        "request_key": request.request_key,
        "recommendation_key": request.recommendation_key,
        "symbol": request.symbol,
        "question": request.question,
        "trigger_source": request.trigger_source,
        "executor_kind": request.executor_kind,
        "model_api_key_id": request.model_api_key_id,
        "status": status,
        "status_note": request.status_note,
        "requested_at": request.requested_at,
        "started_at": request.started_at,
        "completed_at": request.completed_at,
        "failed_at": request.failed_at,
        "artifact_id": request.artifact_id,
        "failure_reason": request.failure_reason,
        "requested_by": request.requested_by,
        "superseded_by_request_id": request.superseded_by_request_id,
        "stale_reason": stale_reason,
        "source_packet_hash": request.source_packet_hash,
        "validation_artifact_id": request.validation_artifact_id,
        "validation_manifest_id": request.validation_manifest_id,
        "source_packet": [str(item) for item in request.request_payload.get("source_packet", []) if item],
        "selected_key": dict(request.request_payload.get("selected_key") or {}) or None,
        "attempted_keys": list(request.request_payload.get("attempted_keys") or []),
        "failover_used": bool(request.request_payload.get("failover_used")),
        "manual_llm_review": projection,
    }


def create_manual_research_request(
    session: Session,
    *,
    symbol: str,
    question: str,
    trigger_source: str,
    requested_by: str | None,
    executor_kind: str,
    model_api_key_id: int | None = None,
) -> dict[str, Any]:
    normalized_question = question.strip() or "请解释当前建议最容易失效的条件。"
    if executor_kind == EXECUTOR_KIND_CONFIGURED_API_KEY and model_api_key_id is None:
        raise ValueError("configured_api_key executor requires model_api_key_id.")
    if model_api_key_id is not None and session.get(ModelApiKey, model_api_key_id) is None:
        raise LookupError(f"Model API key {model_api_key_id} not found.")

    summary = get_stock_dashboard(session, symbol)
    recommendation = _latest_recommendation(session, summary["stock"]["symbol"])
    historical_validation = dict(summary["recommendation"]["historical_validation"])
    source_packet = [str(item) for item in summary["follow_up"]["research_packet"]["manual_review_source_packet"] if item]
    if not source_packet:
        source_packet = build_manual_review_source_packet(
            recommendation,
            payload=dict(recommendation.recommendation_payload or {}),
            historical_validation=historical_validation,
        )
    requested_at = utcnow()
    request = ManualResearchRequest(
        request_key=f"manual-research:{recommendation.recommendation_key}:{requested_at:%Y%m%d%H%M%S%f}",
        recommendation_key=recommendation.recommendation_key,
        symbol=summary["stock"]["symbol"],
        question=normalized_question,
        trigger_source=trigger_source,
        executor_kind=executor_kind,
        model_api_key_id=model_api_key_id,
        status=MANUAL_REVIEW_QUEUED,
        status_note=None,
        requested_at=requested_at,
        started_at=None,
        completed_at=None,
        failed_at=None,
        artifact_id=None,
        failure_reason=None,
        requested_by=requested_by,
        superseded_by_request_id=None,
        stale_reason=None,
        source_packet_hash=compute_source_packet_hash(source_packet),
        validation_artifact_id=historical_validation.get("artifact_id"),
        validation_manifest_id=historical_validation.get("manifest_id"),
        request_payload={
            "source_packet": source_packet,
            "target_horizon_label": summary["recommendation"]["core_quant"]["target_horizon_label"],
            "stock_name": summary["stock"]["name"],
            "prompt": _request_prompt(summary, normalized_question),
        },
    )
    if executor_kind == EXECUTOR_KIND_BUILTIN_GPT:
        builtin = get_builtin_llm_executor_config()
        if builtin["enabled"]:
            request.status_note = BUILTIN_CODEX_QUEUED_STATUS_NOTE
        else:
            request.status_note = (
                "builtin_gpt executor is unavailable; install or configure local Codex CLI or set builtin LLM API credentials."
            )
    session.add(request)
    session.flush()
    return _serialize_request(session, request, artifact_root=_artifact_root(session))


def list_manual_research_requests(
    session: Session,
    *,
    symbol: str | None = None,
    status: str | None = None,
    executor_kind: str | None = None,
    include_superseded: bool = False,
) -> dict[str, Any]:
    query = select(ManualResearchRequest).options(joinedload(ManualResearchRequest.model_api_key))
    if symbol:
        query = query.where(ManualResearchRequest.symbol == symbol)
    if executor_kind:
        query = query.where(ManualResearchRequest.executor_kind == executor_kind)
    if not include_superseded:
        query = query.where(ManualResearchRequest.superseded_by_request_id.is_(None))
    query = query.order_by(ManualResearchRequest.requested_at.desc(), ManualResearchRequest.id.desc())
    records = session.scalars(query).all()
    items = [_serialize_request(session, record, artifact_root=_artifact_root(session)) for record in records]
    if status:
        items = [item for item in items if item["status"] == status]
    counts = {
        "queued": sum(1 for item in items if item["status"] == MANUAL_REVIEW_QUEUED),
        "in_progress": sum(1 for item in items if item["status"] == MANUAL_REVIEW_IN_PROGRESS),
        "failed": sum(1 for item in items if item["status"] == MANUAL_REVIEW_FAILED),
        "completed_current": sum(1 for item in items if item["status"] == MANUAL_REVIEW_COMPLETED),
        "completed_stale": sum(1 for item in items if item["status"] == "stale"),
    }
    return {"generated_at": utcnow(), "counts": counts, "items": items}


def get_manual_research_request(session: Session, request_id: int) -> dict[str, Any]:
    request = _latest_request(session, request_id)
    return _serialize_request(session, request, artifact_root=_artifact_root(session))


def complete_manual_research_request(
    session: Session,
    *,
    request_id: int,
    summary: str,
    review_verdict: str,
    risks: list[str] | None = None,
    disagreements: list[str] | None = None,
    decision_note: str | None = None,
    citations: list[str] | None = None,
    answer: str | None = None,
) -> dict[str, Any]:
    request = _latest_request(session, request_id)
    if request.artifact_id:
        return _serialize_request(session, request, artifact_root=_artifact_root(session))

    normalized_summary = summary.strip()
    normalized_review_verdict = review_verdict.strip()
    if not normalized_summary:
        raise ValueError("summary is required.")
    if not normalized_review_verdict:
        raise ValueError("review_verdict is required.")

    completed_at = utcnow()
    artifact = ManualResearchArtifactView(
        artifact_id=f"manual-review:{request.request_key}",
        recommendation_key=request.recommendation_key,
        stock_symbol=request.symbol,
        stock_name=str(request.request_payload.get("stock_name") or request.symbol),
        generated_at=completed_at,
        question=request.question,
        prompt=str(request.request_payload.get("prompt") or ""),
        answer=(answer or normalized_summary).strip(),
        selected_key=dict(request.request_payload.get("selected_key") or {}),
        attempted_keys=list(request.request_payload.get("attempted_keys") or []),
        failover_used=bool(request.request_payload.get("failover_used")),
        validation_artifact_id=request.validation_artifact_id,
        validation_manifest_id=request.validation_manifest_id,
        target_horizon_label=request.request_payload.get("target_horizon_label"),
        source_packet=[str(item) for item in request.request_payload.get("source_packet", []) if item],
        review_verdict=normalized_review_verdict,
        summary=normalized_summary,
        risks=_coerce_string_list(risks),
        disagreements=_coerce_string_list(disagreements),
        decision_note=(decision_note or "").strip() or None,
        citations=_coerce_string_list(citations),
        request_key=request.request_key,
        executor_kind=request.executor_kind,
        requested_at=request.requested_at,
        started_at=request.started_at or completed_at,
        completed_at=completed_at,
    )
    write_manual_research_artifact(artifact, root=_artifact_root(session))
    request.status = MANUAL_REVIEW_COMPLETED
    request.status_note = "Manual review artifact generated."
    request.started_at = request.started_at or completed_at
    request.completed_at = completed_at
    request.failed_at = None
    request.failure_reason = None
    request.stale_reason = None
    request.artifact_id = artifact.artifact_id
    session.flush()
    return _serialize_request(session, request, artifact_root=_artifact_root(session))


def fail_manual_research_request(
    session: Session,
    *,
    request_id: int,
    failure_reason: str,
) -> dict[str, Any]:
    request = _latest_request(session, request_id)
    if request.artifact_id:
        raise ValueError("Completed manual research requests with artifacts are immutable; use retry instead.")
    normalized_failure_reason = failure_reason.strip()
    if not normalized_failure_reason:
        raise ValueError("failure_reason is required.")
    failed_at = utcnow()
    request.status = MANUAL_REVIEW_FAILED
    request.status_note = normalized_failure_reason
    request.completed_at = None
    request.failure_reason = normalized_failure_reason
    request.failed_at = failed_at
    request.stale_reason = None
    session.flush()
    return _serialize_request(session, request, artifact_root=_artifact_root(session))


def execute_manual_research_request(
    session: Session,
    *,
    request_id: int,
    transport: OpenAICompatibleTransport | None = None,
    failover_enabled: bool = True,
) -> dict[str, Any]:
    request = _latest_request(session, request_id)
    if request.artifact_id:
        return _serialize_request(session, request, artifact_root=_artifact_root(session))

    transport = transport or OpenAICompatibleTransport()
    prompt = str(request.request_payload.get("prompt") or "")
    if request.executor_kind == EXECUTOR_KIND_BUILTIN_GPT:
        builtin = get_builtin_llm_executor_config()
        if not builtin["enabled"]:
            request.status = MANUAL_REVIEW_QUEUED
            request.status_note = (
                "builtin_gpt executor is unavailable; install or configure local Codex CLI or set builtin LLM API credentials."
            )
            session.flush()
            return _serialize_request(session, request, artifact_root=_artifact_root(session))
        candidates = [builtin]
    else:
        candidates = [
            {
                "id": key.id,
                "name": key.name,
                "provider_name": key.provider_name,
                "model_name": key.model_name,
                "base_url": key.base_url,
                "api_key": key.api_key,
            }
            for key in resolve_llm_key_candidates(session, request.model_api_key_id)
        ]
        if request.model_api_key_id is None:
            raise ValueError("configured_api_key executor requires model_api_key_id.")
        candidates = [item for item in candidates if item["id"] == request.model_api_key_id] + [
            item for item in candidates if item["id"] != request.model_api_key_id
        ]

    request.status = MANUAL_REVIEW_IN_PROGRESS
    request.status_note = "Manual research execution is running."
    request.started_at = request.started_at or utcnow()
    session.flush()

    attempted: list[dict[str, Any]] = []
    last_error = "manual research execution failed"
    for index, candidate in enumerate(candidates):
        try:
            if candidate.get("transport_kind") == "codex_cli":
                answer = _run_builtin_codex_completion(
                    codex_bin=str(candidate["codex_bin"]),
                    model_name=str(candidate["model_name"]),
                    prompt=prompt,
                )
            else:
                answer = transport.complete(
                    base_url=str(candidate["base_url"]),
                    api_key=str(candidate["api_key"]),
                    model_name=str(candidate["model_name"]),
                    prompt=prompt,
                )
            if request.executor_kind == EXECUTOR_KIND_CONFIGURED_API_KEY and candidate.get("id") is not None:
                record_model_api_key_result(session, int(candidate["id"]), status="healthy", error_message=None)
            attempted.append(
                {
                    "key_id": candidate.get("id"),
                    "name": candidate["name"],
                    "provider_name": candidate["provider_name"],
                    "model_name": candidate["model_name"],
                    "status": "success",
                    "error": None,
                }
            )
            structured = _extract_structured_answer(answer)
            request.request_payload = {
                **dict(request.request_payload or {}),
                "selected_key": {
                    "id": candidate.get("id"),
                    "name": candidate["name"],
                    "provider_name": candidate["provider_name"],
                    "model_name": candidate["model_name"],
                    "base_url": candidate["base_url"],
                },
                "attempted_keys": attempted,
                "failover_used": index > 0,
            }
            session.flush()
            return complete_manual_research_request(
                session,
                request_id=request.id,
                summary=str(structured.get("summary") or answer.strip()),
                review_verdict=str(structured.get("review_verdict") or "insufficient_evidence"),
                risks=_coerce_string_list(structured.get("risks")),
                disagreements=_coerce_string_list(structured.get("disagreements")),
                decision_note=str(structured.get("decision_note") or ""),
                citations=_coerce_string_list(structured.get("citations")),
                answer=str(structured.get("answer") or answer.strip()),
            )
        except Exception as exc:
            last_error = str(exc)
            if request.executor_kind == EXECUTOR_KIND_CONFIGURED_API_KEY and candidate.get("id") is not None:
                record_model_api_key_result(session, int(candidate["id"]), status="failed", error_message=last_error)
            attempted.append(
                {
                    "key_id": candidate.get("id"),
                    "name": candidate["name"],
                    "provider_name": candidate["provider_name"],
                    "model_name": candidate["model_name"],
                    "status": "failed",
                    "error": last_error,
                }
            )
            if not failover_enabled:
                break

    request.request_payload = {
        **dict(request.request_payload or {}),
        "attempted_keys": attempted,
        "failover_used": len(attempted) > 1,
    }
    session.flush()
    return fail_manual_research_request(session, request_id=request.id, failure_reason=last_error)


def _run_builtin_codex_completion(*, codex_bin: str, model_name: str, prompt: str) -> str:
    with tempfile.NamedTemporaryFile(prefix="ashare-manual-research-", suffix=".txt") as output_file:
        command = [
            codex_bin,
            "exec",
            "-C",
            str(PROJECT_ROOT),
            "--skip-git-repo-check",
            "-s",
            "read-only",
            "-m",
            model_name,
            "-o",
            output_file.name,
            "-",
        ]
        try:
            completed = subprocess.run(
                command,
                input=prompt,
                text=True,
                capture_output=True,
                check=False,
                timeout=BUILTIN_CODEX_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"builtin_gpt local Codex execution timed out after {BUILTIN_CODEX_TIMEOUT_SECONDS}s."
            ) from exc
        if completed.returncode != 0:
            detail = (
                (completed.stderr or "").strip()
                or (completed.stdout or "").strip()
                or "unknown codex execution error"
            )
            raise RuntimeError(f"builtin_gpt local Codex execution failed: {detail}")
        answer = Path(output_file.name).read_text(encoding="utf-8").strip()
    if not answer:
        raise RuntimeError("builtin_gpt local Codex execution returned an empty answer.")
    return answer


def retry_manual_research_request(
    session: Session,
    *,
    request_id: int,
    requested_by: str | None,
) -> dict[str, Any]:
    original = _latest_request(session, request_id)
    created = create_manual_research_request(
        session,
        symbol=original.symbol,
        question=original.question,
        trigger_source=f"{original.trigger_source}:retry",
        requested_by=requested_by,
        executor_kind=original.executor_kind,
        model_api_key_id=original.model_api_key_id,
    )
    original.superseded_by_request_id = int(created["id"])
    original.status_note = f"Superseded by request {created['request_key']}."
    session.flush()
    return created


def run_follow_up_analysis_compat(
    session: Session,
    *,
    symbol: str,
    question: str,
    model_api_key_id: int | None = None,
    failover_enabled: bool = True,
    requested_by: str | None = None,
    transport: OpenAICompatibleTransport | None = None,
) -> dict[str, Any]:
    executor_kind = (
        EXECUTOR_KIND_CONFIGURED_API_KEY
        if model_api_key_id is not None
        else EXECUTOR_KIND_BUILTIN_GPT
    )
    created = create_manual_research_request(
        session,
        symbol=symbol,
        question=question,
        trigger_source="analysis_follow_up_compat",
        requested_by=requested_by,
        executor_kind=executor_kind,
        model_api_key_id=model_api_key_id,
    )
    result = execute_manual_research_request(
        session,
        request_id=int(created["id"]),
        transport=transport,
        failover_enabled=failover_enabled,
    )
    selected_key = dict(result.get("selected_key") or {})
    manual_review = dict(result["manual_llm_review"])
    return {
        "symbol": result["symbol"],
        "question": result["question"],
        "request_id": result["id"],
        "request_key": result["request_key"],
        "status": result["status"],
        "executor_kind": result["executor_kind"],
        "status_note": result["status_note"],
        "answer": manual_review.get("raw_answer"),
        "selected_key": selected_key or None,
        "failover_used": bool(result.get("failover_used")),
        "attempted_keys": list(result.get("attempted_keys") or []),
        "manual_review_artifact_id": result["artifact_id"],
    }
