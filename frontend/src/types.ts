export type RecommendationDirection = "buy" | "watch" | "reduce" | "risk_alert";

export interface LineageRecord {
  license_tag: string;
  usage_scope: string;
  redistribution_scope: string;
  source_uri: string;
  lineage_hash: string;
}

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

export interface SimulationFillView {
  filled_at: string;
  price: number;
  quantity: number;
  fee: number;
  tax: number;
  slippage_bps: number;
  lineage: LineageRecord;
}

export interface SimulationOrderView {
  id: number;
  order_source: string;
  side: string;
  status: string;
  requested_at: string;
  quantity: number;
  limit_price?: number | null;
  fills: SimulationFillView[];
  lineage: LineageRecord;
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

export interface PricePointView {
  observed_at: string;
  open_price: number;
  high_price: number;
  low_price: number;
  close_price: number;
  volume: number;
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
export type CandidateWorkspaceRow = WatchlistItemView & {
  candidate: CandidateItemView | null;
};

export interface WatchlistItemView {
  symbol: string;
  name: string;
  exchange: string;
  ticker: string;
  status: string;
  source_kind: string;
  analysis_status: string;
  added_at: string;
  updated_at: string;
  last_analyzed_at?: string | null;
  last_error?: string | null;
  latest_direction?: string | null;
  latest_confidence_label?: string | null;
  latest_generated_at?: string | null;
}

export interface WatchlistResponse {
  generated_at: string;
  items: WatchlistItemView[];
}

export interface WatchlistMutationResponse {
  item: WatchlistItemView;
  message: string;
}

export interface WatchlistDeleteResponse {
  symbol: string;
  removed: boolean;
  active_count: number;
  removed_at: string;
}

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

export interface TradingRuleCheckView {
  code: string;
  title: string;
  status: string;
  detail: string;
}

export interface PortfolioHoldingView {
  symbol: string;
  name: string;
  quantity: number;
  avg_cost: number;
  last_price: number;
  prev_close?: number | null;
  market_value: number;
  unrealized_pnl: number;
  realized_pnl: number;
  total_pnl: number;
  holding_pnl_pct?: number | null;
  today_pnl_amount: number;
  today_pnl_pct?: number | null;
  portfolio_weight: number;
  pnl_contribution: number;
}

export interface PortfolioAttributionView {
  label: string;
  amount: number;
  contribution_pct: number;
  detail: string;
}

export interface PortfolioNavPointView {
  trade_date: string;
  nav: number;
  benchmark_nav: number;
  drawdown: number;
  exposure: number;
  observed_at?: string | null;
}

export interface PortfolioOrderAuditView {
  order_key: string;
  symbol: string;
  stock_name: string;
  order_source: string;
  side: string;
  requested_at: string;
  status: string;
  quantity: number;
  order_type: string;
  avg_fill_price?: number | null;
  gross_amount: number;
  checks: TradingRuleCheckView[];
}

export interface BenchmarkContextView {
  benchmark_id: string;
  benchmark_type: string;
  benchmark_symbol?: string | null;
  benchmark_label: string;
  source: string;
  source_classification?: string | null;
  as_of_time?: string | null;
  available_time?: string | null;
  status: string;
  note?: string | null;
  artifact_id?: string | null;
  manifest_id?: string | null;
  benchmark_definition?: string | null;
}

export interface PortfolioPerformanceView {
  total_return: number;
  benchmark_return: number;
  excess_return: number;
  realized_pnl: number;
  unrealized_pnl: number;
  fee_total: number;
  tax_total: number;
  max_drawdown: number;
  current_drawdown: number;
  order_count: number;
  annualized_return?: number | null;
  annualized_excess_return?: number | null;
  sharpe_like_ratio?: number | null;
  turnover?: number | null;
  win_rate_definition?: string | null;
  win_rate?: number | null;
  capacity_note?: string | null;
  artifact_id?: string | null;
  validation_mode?: string | null;
  benchmark_definition?: string | null;
  cost_definition?: string | null;
  cost_source?: string | null;
}

export interface ExecutionPolicyView {
  status: string;
  label: string;
  summary: string;
  policy_type?: string | null;
  source?: string | null;
  note?: string | null;
  constraints: string[];
}

export interface PortfolioSummaryView {
  portfolio_key: string;
  name: string;
  mode: string;
  mode_label: string;
  strategy_summary: string;
  strategy_label: string;
  strategy_status?: string;
  benchmark_symbol?: string | null;
  status: string;
  starting_cash: number;
  available_cash: number;
  market_value: number;
  net_asset_value: number;
  invested_ratio: number;
  total_return: number;
  benchmark_return: number;
  excess_return: number;
  benchmark_status?: string;
  benchmark_note?: string | null;
  realized_pnl: number;
  unrealized_pnl: number;
  fee_total: number;
  tax_total: number;
  max_drawdown: number;
  current_drawdown: number;
  order_count: number;
  active_position_count: number;
  rule_pass_rate: number;
  recommendation_hit_rate?: number;
  market_data_timeframe: string;
  last_market_data_at?: string | null;
  benchmark_context: BenchmarkContextView;
  performance: PortfolioPerformanceView;
  execution_policy: ExecutionPolicyView;
  validation_status: string;
  validation_note?: string | null;
  validation_artifact_id?: string | null;
  validation_manifest_id?: string | null;
  alerts: string[];
  rules: TradingRuleCheckView[];
  holdings: PortfolioHoldingView[];
  attribution: PortfolioAttributionView[];
  nav_history: PortfolioNavPointView[];
  recent_orders: PortfolioOrderAuditView[];
}

export interface SimulationRiskExposureView {
  invested_ratio: number;
  cash_ratio: number;
  max_position_weight: number;
  drawdown: number;
  active_position_count: number;
}

export interface SimulationTrackStateView {
  role: string;
  label: string;
  portfolio: PortfolioSummaryView;
  risk_exposure: SimulationRiskExposureView;
  latest_reason?: string | null;
}

export interface SimulationSessionView {
  session_key: string;
  name: string;
  status: string;
  status_label: string;
  focus_symbol?: string | null;
  watch_symbols: string[];
  benchmark_symbol?: string | null;
  initial_cash: number;
  current_step: number;
  step_interval_seconds: number;
  step_trigger_label: string;
  fill_rule_label: string;
  auto_execute_model: boolean;
  auto_execute_model_requested: boolean;
  auto_execute_status: string;
  auto_execute_note?: string | null;
  restart_count: number;
  started_at?: string | null;
  last_resumed_at?: string | null;
  paused_at?: string | null;
  ended_at?: string | null;
  last_data_time?: string | null;
  market_data_timeframe: string;
  market_data_interval_seconds: number;
  last_market_data_at?: string | null;
  data_latency_seconds?: number | null;
  intraday_source_status: IntradaySourceStatusView;
  resumable: boolean;
}

export interface SimulationControlStateView {
  can_start: boolean;
  can_pause: boolean;
  can_resume: boolean;
  can_step: boolean;
  can_restart: boolean;
  can_end: boolean;
  end_requires_confirmation: boolean;
}

export interface SimulationConfigView {
  focus_symbol?: string | null;
  watch_symbols: string[];
  initial_cash: number;
  benchmark_symbol?: string | null;
  step_interval_seconds: number;
  market_data_interval_seconds: number;
  auto_execute_model: boolean;
  auto_execute_model_requested: boolean;
  auto_execute_status: string;
  auto_execute_note?: string | null;
  editable_fields: string[];
}

export interface SimulationTimelineEventView {
  event_key: string;
  step_index: number;
  track: string;
  track_label: string;
  event_type: string;
  happened_at: string;
  symbol?: string | null;
  title: string;
  detail: string;
  severity: string;
  reason_tags: string[];
  payload: Record<string, any>;
  lineage: LineageRecord;
}

export interface SimulationDecisionDiffView {
  step_index: number;
  happened_at: string;
  symbol?: string | null;
  manual_action: string;
  manual_reason: string;
  model_action: string;
  model_reason: string;
  difference_summary: string;
  risk_focus: string[];
}

export interface SimulationComparisonMetricView {
  label: string;
  unit: string;
  manual_value: number;
  model_value: number;
  difference: number;
  leader: string;
}

export interface SimulationModelAdviceView {
  symbol: string;
  stock_name: string;
  direction: string;
  direction_label: string;
  action: string;
  quantity?: number | null;
  current_weight?: number | null;
  target_weight?: number | null;
  trade_delta_weight?: number | null;
  rank?: number | null;
  reference_price: number;
  confidence_label: string;
  generated_at: string;
  reason: string;
  risk_flags: string[];
  policy_status: string;
  policy_type?: string | null;
  policy_note?: string | null;
  action_definition?: string | null;
  quantity_definition?: string | null;
  score: number;
}

export interface SimulationKlineView {
  symbol?: string | null;
  stock_name?: string | null;
  last_updated?: string | null;
  points: PricePointView[];
}

export interface IntradaySourceStatusView {
  status: string;
  provider_name?: string | null;
  provider_label?: string | null;
  source_kind: string;
  timeframe: string;
  decision_interval_seconds: number;
  market_data_interval_seconds: number;
  symbol_count: number;
  last_success_at?: string | null;
  latest_market_data_at?: string | null;
  data_latency_seconds?: number | null;
  fallback_used: boolean;
  stale: boolean;
  message?: string | null;
}

export interface SimulationWorkspaceResponse {
  session: SimulationSessionView;
  controls: SimulationControlStateView;
  configuration: SimulationConfigView;
  manual_track: SimulationTrackStateView;
  model_track: SimulationTrackStateView;
  comparison_metrics: SimulationComparisonMetricView[];
  model_advices: SimulationModelAdviceView[];
  timeline: SimulationTimelineEventView[];
  decision_differences: SimulationDecisionDiffView[];
  kline: SimulationKlineView;
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

export interface OperationsOverviewView {
  generated_at: string;
  beta_readiness?: string;
  manual_portfolio_count: number;
  auto_portfolio_count: number;
  recommendation_replay_hit_rate?: number;
  replay_validation_status?: string;
  replay_validation_note?: string | null;
  rule_pass_rate: number;
  run_health: OperationsRunHealthView;
  research_validation: OperationsResearchValidationView;
  launch_readiness: OperationsLaunchReadinessView;
}

export interface OperationsRunHealthView {
  status: string;
  note?: string | null;
  market_data_timeframe: string;
  last_market_data_at?: string | null;
  data_latency_seconds?: number | null;
  refresh_cooldown_minutes: number;
  intraday_source_status: string;
}

export interface OperationsResearchValidationView {
  status: string;
  note?: string | null;
  recommendation_contract_status: string;
  benchmark_status: string;
  benchmark_note?: string | null;
  replay_validation_status: string;
  replay_validation_note?: string | null;
  replay_sample_count: number;
  verified_replay_count: number;
  synthetic_replay_count: number;
  manifest_bound_count: number;
  metrics_artifact_count: number;
  artifact_sample_count: number;
  replay_artifact_bound_count: number;
  replay_artifact_manifest_count: number;
  replay_artifact_nonverified_count: number;
  replay_artifact_backed_projection_count: number;
  replay_migration_placeholder_count: number;
  portfolio_backtest_bound_count: number;
  portfolio_backtest_manifest_count: number;
  portfolio_backtest_verified_count: number;
  portfolio_backtest_pending_rebuild_count: number;
  portfolio_backtest_artifact_backed_projection_count: number;
  portfolio_backtest_migration_placeholder_count: number;
}

export interface OperationsLaunchReadinessView {
  status: string;
  note?: string | null;
  blocking_gate_count: number;
  warning_gate_count: number;
  synthetic_fields_present: boolean;
  recommended_next_gate?: string | null;
  rule_pass_rate: number;
}

export interface AccessControlView {
  beta_phase: string;
  auth_mode: string;
  required_header: string;
  allowlist_slots: number;
  active_users: number;
  roles: string[];
  session_ttl_minutes: number;
  audit_log_retention_days: number;
  export_policy: string;
  alerts: string[];
}

export interface RefreshScheduleView {
  scope: string;
  cadence_minutes: number;
  market_delay_minutes: number;
  stale_after_minutes: number;
  trigger: string;
}

export interface RefreshPolicyView {
  market_timezone: string;
  cache_ttl_seconds: number;
  manual_refresh_cooldown_minutes: number;
  schedules: RefreshScheduleView[];
}

export interface PerformanceThresholdView {
  metric: string;
  unit: string;
  target: number;
  observed: number;
  status: string;
  note: string;
}

export interface LaunchGateView {
  gate: string;
  threshold: string;
  current_value: string;
  status: string;
}

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

export interface ManualResearchQueueView {
  generated_at: string;
  focus_symbol?: string | null;
  counts: Record<string, number>;
  focus_request?: ManualResearchRequestView | null;
  recent_items: ManualResearchRequestView[];
}

export interface OperationsDashboardResponse {
  overview: OperationsOverviewView;
  market_data_timeframe: string;
  last_market_data_at?: string | null;
  data_latency_seconds?: number | null;
  intraday_source_status: IntradaySourceStatusView;
  portfolios: PortfolioSummaryView[];
  recommendation_replay: RecommendationReplayView[];
  access_control: AccessControlView;
  refresh_policy: RefreshPolicyView;
  performance_thresholds: PerformanceThresholdView[];
  launch_gates: LaunchGateView[];
  manual_research_queue: ManualResearchQueueView;
  simulation_workspace?: SimulationWorkspaceResponse | null;
}

export interface SimulationConfigRequest {
  initial_cash: number;
  watch_symbols: string[];
  focus_symbol?: string | null;
  step_interval_seconds: number;
  auto_execute_model: boolean;
}

export interface SimulationControlActionResponse {
  workspace: SimulationWorkspaceResponse;
  message: string;
}

export interface ManualSimulationOrderRequest {
  symbol: string;
  side: string;
  quantity: number;
  reason: string;
  limit_price?: number | null;
}

export interface SimulationEndRequest {
  confirm: boolean;
}

export type DataMode = "online" | "offline";

export interface DataSourceInfo {
  mode: DataMode;
  preferredMode: DataMode;
  label: string;
  detail: string;
  apiBase: string;
  betaHeaderName: string;
  betaKeyPresent: boolean;
  snapshotGeneratedAt: string;
  fallbackReason?: string | null;
}

export interface DashboardRuntimeConfig {
  apiBase: string;
  apiBaseDefault: string;
  apiBaseOverrideActive: boolean;
  betaHeaderName: string;
  onlineConfigured: boolean;
  preferredMode: DataMode;
  snapshotGeneratedAt: string;
}

export interface DashboardShellPayload {
  watchlist: WatchlistResponse;
  candidates: CandidateListResponse;
  glossary: GlossaryEntryView[];
}

export interface RuntimeDataSourceView {
  provider_name: string;
  role: string;
  freshness_note: string;
  docs_url: string;
  notes: string[];
  credential_configured: boolean;
  credential_required: boolean;
  runtime_ready: boolean;
  status_label: string;
  supports_intraday: boolean;
  intraday_runtime_ready: boolean;
  intraday_status_label?: string | null;
  base_url?: string | null;
  enabled: boolean;
}

export interface RuntimeFieldMappingView {
  dataset: string;
  canonical_field: string;
  akshare_field: string;
  tushare_field: string;
  notes: string;
}

export interface CacheDatasetPolicyView {
  dataset: string;
  label: string;
  ttl_seconds: number;
  stale_if_error_seconds: number;
  warm_on_watchlist: boolean;
}

export interface ProviderCredentialView {
  id: number;
  provider_name: string;
  display_name: string;
  base_url?: string | null;
  enabled: boolean;
  notes?: string | null;
  token_configured: boolean;
  masked_token?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ModelApiKeyView {
  id: number;
  name: string;
  provider_name: string;
  model_name: string;
  base_url: string;
  enabled: boolean;
  is_default: boolean;
  priority: number;
  masked_key?: string | null;
  last_status: string;
  last_error?: string | null;
  last_checked_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface RuntimeSettingsResponse {
  generated_at: string;
  deployment_mode: string;
  storage_engine: string;
  cache_backend: string;
  watchlist_scope: string;
  watchlist_cache_only: boolean;
  llm_failover_enabled: boolean;
  deployment_notes: string[];
  provider_selection_mode: string;
  provider_order: string[];
  provider_cooldown_seconds: number;
  field_mappings: RuntimeFieldMappingView[];
  data_sources: RuntimeDataSourceView[];
  cache_policies: CacheDatasetPolicyView[];
  anti_stampede: Record<string, any>;
  provider_credentials: ProviderCredentialView[];
  model_api_keys: ModelApiKeyView[];
  default_model_api_key_id?: number | null;
}

export interface ModelApiKeyCreateRequest {
  name: string;
  provider_name: string;
  model_name: string;
  base_url: string;
  api_key: string;
  enabled: boolean;
  priority: number;
  make_default: boolean;
}

export interface ModelApiKeyUpdateRequest {
  name?: string;
  provider_name?: string;
  model_name?: string;
  base_url?: string;
  api_key?: string;
  enabled?: boolean;
  priority?: number;
  make_default?: boolean;
}

export interface ProviderCredentialUpsertRequest {
  access_token?: string | null;
  base_url?: string | null;
  enabled: boolean;
  notes?: string | null;
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

export interface ModelApiKeyDeleteResponse {
  id: number;
  name: string;
  deleted: boolean;
  deleted_at: string;
}
