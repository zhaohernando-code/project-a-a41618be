// settings domain types

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

export interface RuntimeOverviewResponse {
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

export interface ModelApiKeyDeleteResponse {
  id: number;
  name: string;
  deleted: boolean;
  deleted_at: string;
}
