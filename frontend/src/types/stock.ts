// stock domain types
import type { LineageRecord, PricePointView, RecommendationDirection } from "./common";
import type { SimulationOrderView } from "./simulation";

export interface StockView {
  symbol: string;
  name: string;
  exchange: string;
  ticker: string;
}

export interface QuantCoreView {
  score?: number | null;
  score_scale: string;
  direction: string;
  confidence_bucket: string;
  target_horizon_label: string;
  horizon_min_days: number;
  horizon_max_days: number;
  as_of_time: string;
  available_time: string;
  model_version: string;
  policy_version: string;
}

export interface RecommendationEvidenceView {
  primary_drivers: string[];
  supporting_context: string[];
  conflicts: string[];
  degrade_flags: string[];
  data_freshness?: string | null;
  source_links: string[];
  factor_cards: {
    factor_key: string;
    score?: number | null;
    direction?: string | null;
    headline: string;
    risk_note?: string | null;
    status?: string | null;
  }[];
}

export interface RecommendationRiskView {
  risk_flags: string[];
  downgrade_conditions: string[];
  invalidators: string[];
  coverage_gaps: string[];
}

export interface HistoricalValidationView {
  status: string;
  note?: string | null;
  artifact_type?: string | null;
  artifact_id?: string | null;
  manifest_id?: string | null;
  artifact_generated_at?: string | null;
  label_definition?: string | null;
  window_definition?: string | null;
  benchmark_definition?: string | null;
  cost_definition?: string | null;
  metrics: Record<string, any>;
}

export interface ManualLlmReviewView {
  status: string;
  trigger_mode: string;
  model_label?: string | null;
  requested_at?: string | null;
  generated_at?: string | null;
  artifact_id?: string | null;
  question?: string | null;
  raw_answer?: string | null;
  summary?: string | null;
  risks: string[];
  disagreements: string[];
  source_packet: string[];
  request_id?: number | null;
  request_key?: string | null;
  executor_kind?: string | null;
  status_note?: string | null;
  review_verdict?: string | null;
  decision_note?: string | null;
  stale_reason?: string | null;
  citations: string[];
}

export interface ClaimGateView {
  status: string;
  headline: string;
  note?: string | null;
  public_direction: RecommendationDirection;
  blocking_reasons: string[];
  sample_count?: number | null;
  coverage_ratio?: number | null;
}

export interface RecommendationView {
  id: number;
  recommendation_key: string;
  direction: RecommendationDirection;
  confidence_label: string;
  confidence_score: number;
  confidence_expression: string;
  horizon_min_days: number;
  horizon_max_days: number;
  applicable_period?: string;
  summary: string;
  generated_at: string;
  updated_at: string;
  as_of_data_time: string;
  evidence_status: string;
  degrade_reason?: string | null;
  core_drivers?: string[];
  risk_flags?: string[];
  reverse_risks?: string[];
  downgrade_conditions?: string[];
  factor_breakdown?: Record<string, any>;
  validation_status?: string;
  validation_note?: string | null;
  validation_snapshot?: Record<string, any>;
  core_quant: QuantCoreView;
  evidence: RecommendationEvidenceView;
  risk: RecommendationRiskView;
  historical_validation: HistoricalValidationView;
  manual_llm_review: ManualLlmReviewView;
  claim_gate: ClaimGateView;
  lineage: LineageRecord;
}

export interface ModelView {
  name: string;
  family: string;
  version: string;
  validation_scheme: string;
  artifact_uri?: string | null;
  lineage: LineageRecord;
}

export interface PromptView {
  name: string;
  version: string;
  risk_disclaimer: string;
  lineage: LineageRecord;
}

export interface EvidenceArtifactView {
  evidence_type: string;
  record_id: number;
  role: string;
  rank: number;
  label: string;
  snippet?: string | null;
  timestamp?: string | null;
  lineage: LineageRecord;
  payload: Record<string, any>;
}

export interface HeroView {
  latest_close: number;
  day_change_pct: number;
  latest_volume: number;
  turnover_rate?: number | null;
  high_price: number;
  low_price: number;
  sector_tags: string[];
  direction_label: string;
  last_updated: string;
}

export interface RecentNewsView {
  headline: string;
  summary: string;
  published_at: string;
  impact_direction: string;
  entity_scope: string;
  relevance_score: number;
  source_uri: string;
  license_tag: string;
}

export interface ChangeView {
  has_previous: boolean;
  change_badge: string;
  summary: string;
  reasons: string[];
  previous_direction?: string | null;
  previous_confidence_label?: string | null;
  previous_generated_at?: string | null;
}

export interface GlossaryEntryView {
  term: string;
  plain_explanation: string;
  why_it_matters: string;
}

export interface RiskPanelView {
  headline: string;
  items: string[];
  disclaimer: string;
  change_hint: string;
}

export interface FollowUpResearchPacketView {
  validation_status: string;
  validation_note?: string | null;
  validation_artifact_id?: string | null;
  validation_manifest_id?: string | null;
  validation_sample_count?: number | null;
  validation_rank_ic_mean?: number | null;
  validation_positive_excess_rate?: number | null;
  manual_request_id?: number | null;
  manual_request_key?: string | null;
  manual_review_executor_kind?: string | null;
  manual_review_status_note?: string | null;
  manual_review_review_verdict?: string | null;
  manual_review_stale_reason?: string | null;
  manual_review_status: string;
  manual_review_trigger_mode: string;
  manual_review_source_packet: string[];
  manual_review_artifact_id?: string | null;
  manual_review_generated_at?: string | null;
}

export interface FollowUpView {
  suggested_questions: string[];
  copy_prompt: string;
  evidence_packet: string[];
  research_packet: FollowUpResearchPacketView;
}

export interface CandidateItemView {
  rank: number;
  symbol: string;
  name: string;
  sector: string;
  direction: RecommendationDirection;
  direction_label: string;
  display_direction: RecommendationDirection;
  display_direction_label: string;
  confidence_label: string;
  confidence_score: number;
  summary: string;
  applicable_period?: string | null;
  window_definition: string;
  target_horizon_label: string;
  source_classification?: string | null;
  validation_mode?: string | null;
  validation_status: string;
  validation_note?: string | null;
  validation_artifact_id?: string | null;
  validation_manifest_id?: string | null;
  validation_sample_count?: number | null;
  validation_rank_ic_mean?: number | null;
  validation_positive_excess_rate?: number | null;
  generated_at: string;
  as_of_data_time: string;
  last_close?: number | null;
  price_return_20d: number;
  price_chart: PricePointView[];
  why_now: string;
  primary_risk?: string | null;
  change_summary: string;
  change_badge: string;
  evidence_status: string;
  claim_gate: ClaimGateView;
}

export interface CandidateListResponse {
  generated_at: string;
  items: CandidateItemView[];
}



/** View-model combining watchlist item with its candidate analysis data. */
export interface StockDashboardResponse {
  stock: StockView;
  recommendation: RecommendationView;
  model: ModelView;
  prompt: PromptView;
  evidence: EvidenceArtifactView[];
  simulation_orders: SimulationOrderView[];
  hero: HeroView;
  price_chart: PricePointView[];
  recent_news: RecentNewsView[];
  change: ChangeView;
  glossary: GlossaryEntryView[];
  risk_panel: RiskPanelView;
  follow_up: FollowUpView;
}

export interface RecommendationReplayView {
  source?: string | null;
  source_classification?: string | null;
  artifact_type?: string | null;
  artifact_id?: string | null;
  manifest_id?: string | null;
  recommendation_id: number;
  recommendation_key?: string | null;
  symbol: string;
  stock_name: string;
  direction: string;
  generated_at: string;
  label_definition: string;
  review_window_definition: string;
  entry_time: string;
  exit_time: string;
  review_window_days?: number;
  stock_return: number;
  benchmark_return: number;
  excess_return: number;
  max_favorable_excursion: number;
  max_adverse_excursion: number;
  benchmark_definition?: string | null;
  benchmark_source?: string | null;
  validation_mode?: string | null;
  hit_definition: string;
  hit_status: string;
  validation_status: string;
  validation_note?: string | null;
  summary: string;
  followed_by_portfolios: string[];
}
