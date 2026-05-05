export interface ShortpickRunCreateRequest {
  run_date?: string | null;
  rounds_per_model: number;
}

export interface ShortpickRunValidateRequest {
  horizons: number[];
}

export interface ShortpickSourceView {
  title?: string | null;
  url?: string | null;
  published_at?: string | null;
  why_it_matters?: string | null;
  credibility_status?: string | null;
  credibility_reason?: string | null;
  http_status?: number | null;
  checked_at?: string | null;
}

export interface ShortpickRoundView {
  id: number;
  round_key: string;
  provider_name: string;
  model_name: string;
  executor_kind: string;
  round_index: number;
  status: string;
  symbol?: string | null;
  stock_name?: string | null;
  theme?: string | null;
  thesis?: string | null;
  confidence?: number | null;
  sources: ShortpickSourceView[];
  artifact_id?: string | null;
  error_message?: string | null;
  raw_answer?: string | null;
  started_at: string;
  completed_at?: string | null;
}

export interface ShortpickValidationView {
  id: number;
  horizon_days: number;
  status: string;
  entry_at?: string | null;
  exit_at?: string | null;
  entry_close?: number | null;
  exit_close?: number | null;
  stock_return?: number | null;
  benchmark_return?: number | null;
  excess_return?: number | null;
  max_favorable_return?: number | null;
  max_drawdown?: number | null;
}

export interface ShortpickCandidateView {
  id: number;
  candidate_key: string;
  run_id: number;
  round_id?: number | null;
  symbol: string;
  name: string;
  normalized_theme?: string | null;
  horizon_trading_days?: number | null;
  confidence?: number | null;
  thesis?: string | null;
  catalysts: string[];
  invalidation: string[];
  risks: string[];
  sources: ShortpickSourceView[];
  novelty_note?: string | null;
  limitations: string[];
  convergence_group?: string | null;
  research_priority: string;
  parse_status: string;
  is_system_external: boolean;
  validations: ShortpickValidationView[];
  raw_round?: ShortpickRoundView | null;
}

export interface ShortpickConsensusView {
  id: number;
  snapshot_key: string;
  artifact_id?: string | null;
  generated_at: string;
  status: string;
  stock_convergence: number;
  theme_convergence: number;
  source_diversity: number;
  model_independence: number;
  novelty_score: number;
  research_priority: string;
  summary: Record<string, unknown>;
}

export interface ShortpickRunView {
  id: number;
  run_key: string;
  run_date: string;
  prompt_version: string;
  information_mode: string;
  status: string;
  trigger_source: string;
  triggered_by?: string | null;
  started_at: string;
  completed_at?: string | null;
  failed_at?: string | null;
  model_config: Record<string, unknown>;
  summary: Record<string, unknown>;
  rounds: ShortpickRoundView[];
  consensus?: ShortpickConsensusView | null;
  candidates: ShortpickCandidateView[];
}

export interface ShortpickRunListResponse {
  generated_at: string;
  items: ShortpickRunView[];
}

export interface ShortpickCandidateListResponse {
  generated_at: string;
  items: ShortpickCandidateView[];
}
