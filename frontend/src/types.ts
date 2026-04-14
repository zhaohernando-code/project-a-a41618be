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

export interface RecommendationView {
  id: number;
  recommendation_key: string;
  direction: RecommendationDirection;
  confidence_label: string;
  confidence_score: number;
  confidence_expression: string;
  horizon_min_days: number;
  horizon_max_days: number;
  applicable_period: string;
  summary: string;
  generated_at: string;
  updated_at: string;
  as_of_data_time: string;
  evidence_status: string;
  degrade_reason?: string | null;
  core_drivers: string[];
  risk_flags: string[];
  reverse_risks: string[];
  downgrade_conditions: string[];
  factor_breakdown: Record<string, any>;
  validation_snapshot: Record<string, any>;
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

export interface FollowUpView {
  suggested_questions: string[];
  copy_prompt: string;
  evidence_packet: string[];
}

export interface CandidateItemView {
  rank: number;
  symbol: string;
  name: string;
  sector: string;
  direction: RecommendationDirection;
  direction_label: string;
  confidence_label: string;
  confidence_score: number;
  summary: string;
  applicable_period: string;
  generated_at: string;
  as_of_data_time: string;
  last_close?: number | null;
  price_return_20d: number;
  why_now: string;
  primary_risk?: string | null;
  change_summary: string;
  change_badge: string;
  evidence_status: string;
}

export interface CandidateListResponse {
  generated_at: string;
  items: CandidateItemView[];
}

export interface DashboardBootstrapResponse {
  symbols: string[];
  recommendation_count: number;
  candidate_count: number;
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
  market_value: number;
  unrealized_pnl: number;
  realized_pnl: number;
  total_pnl: number;
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

export interface PortfolioSummaryView {
  portfolio_key: string;
  name: string;
  mode: string;
  mode_label: string;
  strategy_summary: string;
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
  realized_pnl: number;
  unrealized_pnl: number;
  fee_total: number;
  tax_total: number;
  max_drawdown: number;
  current_drawdown: number;
  order_count: number;
  active_position_count: number;
  rule_pass_rate: number;
  recommendation_hit_rate: number;
  alerts: string[];
  rules: TradingRuleCheckView[];
  holdings: PortfolioHoldingView[];
  attribution: PortfolioAttributionView[];
  nav_history: PortfolioNavPointView[];
  recent_orders: PortfolioOrderAuditView[];
}

export interface RecommendationReplayView {
  recommendation_id: number;
  symbol: string;
  stock_name: string;
  direction: string;
  generated_at: string;
  review_window_days: number;
  stock_return: number;
  benchmark_return: number;
  excess_return: number;
  max_favorable_excursion: number;
  max_adverse_excursion: number;
  hit_status: string;
  summary: string;
  followed_by_portfolios: string[];
}

export interface OperationsOverviewView {
  generated_at: string;
  beta_readiness: string;
  manual_portfolio_count: number;
  auto_portfolio_count: number;
  recommendation_replay_hit_rate: number;
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

export interface OperationsDashboardResponse {
  overview: OperationsOverviewView;
  portfolios: PortfolioSummaryView[];
  recommendation_replay: RecommendationReplayView[];
  access_control: AccessControlView;
  refresh_policy: RefreshPolicyView;
  performance_thresholds: PerformanceThresholdView[];
  launch_gates: LaunchGateView[];
}
