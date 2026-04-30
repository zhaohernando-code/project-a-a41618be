// operations domain types
import type { IntradaySourceStatusView } from "./common";
import type { PortfolioSummaryView } from "./portfolio";
import type { SimulationWorkspaceResponse } from "./simulation";
import type { RecommendationReplayView } from "./stock";
import type { ManualResearchRequestView } from "./research";

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

