"""R u n t i m e domain schemas."""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class RuntimeDataSourceView(BaseModel):
    provider_name: str
    role: str
    freshness_note: str
    docs_url: str
    notes: list[str] = Field(default_factory=list)
    credential_configured: bool
    credential_required: bool
    runtime_ready: bool
    status_label: str
    supports_intraday: bool = False
    intraday_runtime_ready: bool = False
    intraday_status_label: str | None = None
    base_url: str | None = None
    enabled: bool


class RuntimeFieldMappingView(BaseModel):
    dataset: str
    canonical_field: str
    akshare_field: str
    tushare_field: str
    notes: str


class CacheDatasetPolicyView(BaseModel):
    dataset: str
    label: str
    ttl_seconds: int
    stale_if_error_seconds: int
    warm_on_watchlist: bool


class ProviderCredentialView(BaseModel):
    id: int
    provider_name: str
    display_name: str
    base_url: str | None = None
    enabled: bool
    notes: str | None = None
    token_configured: bool
    masked_token: str | None = None
    created_at: datetime
    updated_at: datetime


class ModelApiKeyView(BaseModel):
    id: int
    name: str
    provider_name: str
    model_name: str
    base_url: str
    enabled: bool
    is_default: bool
    priority: int
    masked_key: str | None = None
    last_status: str
    last_error: str | None = None
    last_checked_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class RuntimeSettingsResponse(BaseModel):
    generated_at: datetime
    deployment_mode: str
    storage_engine: str
    cache_backend: str
    watchlist_scope: str
    watchlist_cache_only: bool
    llm_failover_enabled: bool
    deployment_notes: list[str] = Field(default_factory=list)
    provider_selection_mode: str
    provider_order: list[str] = Field(default_factory=list)
    provider_cooldown_seconds: int
    field_mappings: list[RuntimeFieldMappingView] = Field(default_factory=list)
    data_sources: list[RuntimeDataSourceView] = Field(default_factory=list)
    cache_policies: list[CacheDatasetPolicyView] = Field(default_factory=list)
    anti_stampede: dict[str, Any] = Field(default_factory=dict)
    provider_credentials: list[ProviderCredentialView] = Field(default_factory=list)
    model_api_keys: list[ModelApiKeyView] = Field(default_factory=list)
    default_model_api_key_id: int | None = None


class ProviderCredentialUpsertRequest(BaseModel):
    access_token: str | None = None
    base_url: str | None = None
    enabled: bool = True
    notes: str | None = None


class ModelApiKeyCreateRequest(BaseModel):
    name: str
    provider_name: str = "openai"
    model_name: str
    base_url: str
    api_key: str
    enabled: bool = True
    priority: int = 100
    make_default: bool = False


class ModelApiKeyUpdateRequest(BaseModel):
    name: str | None = None
    provider_name: str | None = None
    model_name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    enabled: bool | None = None
    priority: int | None = None
    make_default: bool | None = None


class ModelApiKeyDeleteResponse(BaseModel):
    id: int
    name: str
    deleted: bool
    deleted_at: datetime


