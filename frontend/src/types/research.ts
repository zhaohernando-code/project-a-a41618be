// research domain types
import type { ManualLlmReviewView } from "./stock";

export interface ManualResearchRequestCreateRequest {
  symbol: string;
  question: string;
  trigger_source?: string;
  executor_kind: string;
  model_api_key_id?: number | null;
}

export interface ManualResearchRequestExecuteRequest {
  failover_enabled: boolean;
}

export interface ManualResearchRequestCompleteRequest {
  summary: string;
  review_verdict: string;
  risks: string[];
  disagreements: string[];
  decision_note?: string | null;
  citations: string[];
  answer?: string | null;
}

export interface ManualResearchRequestFailRequest {
  failure_reason: string;
}

export interface ManualResearchRequestRetryRequest {
  requested_by?: string | null;
}

export interface ManualResearchRequestView {
  id: number;
  request_key: string;
  recommendation_key: string;
  symbol: string;
  question: string;
  trigger_source: string;
  executor_kind: string;
  model_api_key_id?: number | null;
  status: string;
  status_note?: string | null;
  requested_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  failed_at?: string | null;
  artifact_id?: string | null;
  failure_reason?: string | null;
  requested_by?: string | null;
  superseded_by_request_id?: number | null;
  stale_reason?: string | null;
  source_packet_hash: string;
  validation_artifact_id?: string | null;
  validation_manifest_id?: string | null;
  source_packet: string[];
  selected_key?: AnalysisKeySelectionView | null;
  attempted_keys: AnalysisAttemptView[];
  failover_used: boolean;
  manual_llm_review: ManualLlmReviewView;
}

export interface ManualResearchRequestListResponse {
  generated_at: string;
  counts: Record<string, number>;
  items: ManualResearchRequestView[];
}

export interface FollowUpAnalysisRequest {
  symbol: string;
  question: string;
  model_api_key_id?: number | null;
  failover_enabled: boolean;
}

export interface AnalysisAttemptView {
  key_id?: number | null;
  name: string;
  provider_name: string;
  model_name: string;
  status: string;
  error?: string | null;
}

export interface AnalysisKeySelectionView {
  id?: number | null;
  name: string;
  provider_name: string;
  model_name: string;
  base_url: string;
}

export interface FollowUpAnalysisResponse {
  symbol: string;
  question: string;
  request_id: number;
  request_key: string;
  status: string;
  executor_kind: string;
  status_note?: string | null;
  answer?: string | null;
  selected_key?: AnalysisKeySelectionView | null;
  failover_used: boolean;
  attempted_keys: AnalysisAttemptView[];
  manual_review_artifact_id?: string | null;
}

