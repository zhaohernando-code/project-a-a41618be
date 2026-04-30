// portfolio domain types

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

