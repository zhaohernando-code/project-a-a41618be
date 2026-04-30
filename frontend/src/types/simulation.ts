// simulation domain types
import type { IntradaySourceStatusView, LineageRecord, PricePointView } from "./common";
import type { PortfolioSummaryView } from "./portfolio";

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

