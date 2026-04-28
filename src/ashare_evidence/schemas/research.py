"""R e s e a r c h domain schemas."""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from .stock import ManualLlmReviewView


class AnalysisAttemptView(BaseModel):
    key_id: int | None = None
    name: str
    provider_name: str
    model_name: str
    status: str
    error: str | None = None


class AnalysisKeySelectionView(BaseModel):
    id: int | None = None
    name: str
    provider_name: str
    model_name: str
    base_url: str


class FollowUpAnalysisRequest(BaseModel):
    symbol: str
    question: str
    model_api_key_id: int | None = None
    failover_enabled: bool = True


class FollowUpAnalysisResponse(BaseModel):
    symbol: str
    question: str
    request_id: int
    request_key: str
    status: str
    executor_kind: str
    status_note: str | None = None
    answer: str | None = None
    selected_key: AnalysisKeySelectionView | None = None
    failover_used: bool = False
    attempted_keys: list[AnalysisAttemptView] = Field(default_factory=list)
    manual_review_artifact_id: str | None = None


class ManualResearchRequestCreateRequest(BaseModel):
    symbol: str
    question: str
    trigger_source: str = "manual_research_ui"
    executor_kind: str = "builtin_gpt"
    model_api_key_id: int | None = None


class ManualResearchRequestExecuteRequest(BaseModel):
    failover_enabled: bool = True


class ManualResearchRequestCompleteRequest(BaseModel):
    summary: str
    review_verdict: str
    risks: list[str] = Field(default_factory=list)
    disagreements: list[str] = Field(default_factory=list)
    decision_note: str | None = None
    citations: list[str] = Field(default_factory=list)
    answer: str | None = None


class ManualResearchRequestFailRequest(BaseModel):
    failure_reason: str


class ManualResearchRequestRetryRequest(BaseModel):
    requested_by: str | None = None


class ManualResearchRequestView(BaseModel):
    id: int
    request_key: str
    recommendation_key: str
    symbol: str
    question: str
    trigger_source: str
    executor_kind: str
    model_api_key_id: int | None = None
    status: str
    status_note: str | None = None
    requested_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failed_at: datetime | None = None
    artifact_id: str | None = None
    failure_reason: str | None = None
    requested_by: str | None = None
    superseded_by_request_id: int | None = None
    stale_reason: str | None = None
    source_packet_hash: str
    validation_artifact_id: str | None = None
    validation_manifest_id: str | None = None
    source_packet: list[str] = Field(default_factory=list)
    selected_key: AnalysisKeySelectionView | None = None
    attempted_keys: list[AnalysisAttemptView] = Field(default_factory=list)
    failover_used: bool = False
    manual_llm_review: ManualLlmReviewView


class ManualResearchRequestListResponse(BaseModel):
    generated_at: datetime
    counts: dict[str, int] = Field(default_factory=dict)
    items: list[ManualResearchRequestView] = Field(default_factory=list)

