// common domain types

export type RecommendationDirection = "buy" | "add" | "watch" | "reduce" | "sell" | "risk_alert";

export interface LineageRecord {
  license_tag: string;
  usage_scope: string;
  redistribution_scope: string;
  source_uri: string;
  lineage_hash: string;
}

export interface PricePointView {
  observed_at: string;
  open_price: number;
  high_price: number;
  low_price: number;
  close_price: number;
  volume: number;
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

export type ViewMode = "candidates" | "stock" | "operations" | "settings";
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

export interface AccountSpaceView {
  account_login: string;
  role_snapshot: string;
  first_seen_at: string;
  last_seen_at?: string | null;
  last_acted_at?: string | null;
  created_by_root: boolean;
}

export interface AuthContextResponse {
  actor_login: string;
  actor_role: string;
  target_login: string;
  can_act_as: boolean;
  auth_mode: string;
  visible_account_spaces: AccountSpaceView[];
}
