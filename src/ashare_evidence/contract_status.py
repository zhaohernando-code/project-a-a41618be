from __future__ import annotations

from typing import Literal

ValidationStatus = Literal[
    "pending_rebuild",
    "synthetic_demo",
    "research_candidate",
    "verified",
    "deprecated",
]

ManualReviewStatus = Literal[
    "manual_trigger_required",
    "queued",
    "in_progress",
    "completed",
    "failed",
    "stale",
]

STATUS_PENDING_REBUILD: ValidationStatus = "pending_rebuild"
STATUS_SYNTHETIC_DEMO: ValidationStatus = "synthetic_demo"
STATUS_RESEARCH_CANDIDATE: ValidationStatus = "research_candidate"
STATUS_VERIFIED: ValidationStatus = "verified"
STATUS_DEPRECATED: ValidationStatus = "deprecated"

MANUAL_TRIGGER_REQUIRED: ManualReviewStatus = "manual_trigger_required"
MANUAL_REVIEW_QUEUED: ManualReviewStatus = "queued"
MANUAL_REVIEW_IN_PROGRESS: ManualReviewStatus = "in_progress"
MANUAL_REVIEW_COMPLETED: ManualReviewStatus = "completed"
MANUAL_REVIEW_FAILED: ManualReviewStatus = "failed"
MANUAL_REVIEW_STALE: ManualReviewStatus = "stale"

PENDING_REBUILD_NOTE = "历史滚动验证与真实回测正在重建，当前不展示收益率、命中率或 lift 等验证指标。"
SYNTHETIC_DEMO_NOTE = "当前结果只来自演示级或合成逻辑，不能代表真实量化验证结果。"
MANUAL_TRIGGER_REQUIRED_NOTE = "LLM 研究链路将迁移为手动 Codex/GPT 流程，当前不参与核心量化评分。"


def pending_rebuild_payload(note: str | None = None) -> dict[str, str]:
    return {
        "status": STATUS_PENDING_REBUILD,
        "note": note or PENDING_REBUILD_NOTE,
    }


def manual_review_placeholder(note: str | None = None) -> dict[str, str]:
    return {
        "status": MANUAL_TRIGGER_REQUIRED,
        "note": note or MANUAL_TRIGGER_REQUIRED_NOTE,
    }
