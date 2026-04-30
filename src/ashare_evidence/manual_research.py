from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ashare_evidence.contract_status import MANUAL_REVIEW_COMPLETED
from ashare_evidence.models import Recommendation
from ashare_evidence.research_artifact_store import artifact_root_from_database_url, write_manual_research_artifact
from ashare_evidence.research_artifacts import ManualResearchArtifactView


def persist_manual_research_result(
    session: Session,
    *,
    summary: dict[str, Any],
    question: str,
    prompt: str,
    answer: str,
    selected_key: dict[str, Any],
    attempted_keys: list[dict[str, Any]],
    failover_used: bool,
) -> ManualResearchArtifactView:
    generated_at = datetime.now().astimezone()
    recommendation_key = str(summary["recommendation"]["recommendation_key"])
    research_packet = dict(summary["follow_up"]["research_packet"])
    artifact = ManualResearchArtifactView(
        artifact_id=f"manual-review:{recommendation_key}:{generated_at:%Y%m%d%H%M%S}",
        recommendation_key=recommendation_key,
        stock_symbol=str(summary["stock"]["symbol"]),
        stock_name=str(summary["stock"]["name"]),
        generated_at=generated_at,
        question=question,
        prompt=prompt,
        answer=answer,
        selected_key=selected_key,
        attempted_keys=attempted_keys,
        failover_used=failover_used,
        validation_artifact_id=research_packet.get("validation_artifact_id"),
        validation_manifest_id=research_packet.get("validation_manifest_id"),
        target_horizon_label=summary["recommendation"].get("core_quant", {}).get("target_horizon_label"),
        source_packet=[str(item) for item in research_packet.get("manual_review_source_packet", []) if item],
    )
    bind = session.get_bind()
    artifact_root = artifact_root_from_database_url(bind.url.render_as_string(hide_password=False) if bind else None)
    write_manual_research_artifact(artifact, root=artifact_root)

    recommendation = session.scalar(
        select(Recommendation).where(Recommendation.recommendation_key == recommendation_key)
    )
    if recommendation is None:
        raise LookupError(f"Recommendation {recommendation_key} not found.")

    payload = dict(recommendation.recommendation_payload or {})
    manual_review = dict(payload.get("manual_llm_review") or {})
    manual_review.update(
        {
            "status": MANUAL_REVIEW_COMPLETED,
            "trigger_mode": "manual",
            "model_label": f"{selected_key.get('provider_name')}:{selected_key.get('model_name')}",
            "requested_at": generated_at.isoformat(),
            "generated_at": generated_at.isoformat(),
            "summary": answer,
            "risks": list(manual_review.get("risks") or []),
            "disagreements": list(manual_review.get("disagreements") or []),
            "source_packet": artifact.source_packet,
            "artifact_id": artifact.artifact_id,
            "question": question,
            "raw_answer": answer,
        }
    )
    payload["manual_llm_review"] = manual_review
    recommendation.recommendation_payload = payload
    session.flush()
    return artifact
