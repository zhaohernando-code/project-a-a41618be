import type {
  CandidateListResponse,
  DashboardBootstrapResponse,
  DashboardRuntimeConfig,
  DashboardShellPayload,
  DataSourceInfo,
  FollowUpAnalysisRequest,
  FollowUpAnalysisResponse,
  GlossaryEntryView,
  ModelApiKeyCreateRequest,
  ModelApiKeyDeleteResponse,
  ModelApiKeyUpdateRequest,
  OperationsDashboardResponse,
  ProviderCredentialUpsertRequest,
  RuntimeSettingsResponse,
  StockDashboardResponse,
  WatchlistDeleteResponse,
  WatchlistMutationResponse,
  WatchlistResponse,
} from "./types";

const envApiBase = normalizeApiBase(import.meta.env.VITE_API_BASE_URL ?? "");
const betaHeaderName = import.meta.env.VITE_BETA_ACCESS_HEADER ?? "X-Ashare-Beta-Key";
const betaStorageKey = "ashare-beta-access-key";
const requestTimeoutMs = 10000;

type ApiResult<T> = {
  data: T;
  source: DataSourceInfo;
};

function normalizeApiBase(value: string | null | undefined): string {
  return (value ?? "").trim().replace(/\/$/, "");
}

function getApiBase(): string {
  return envApiBase;
}

function makeUrl(path: string): string {
  const apiBase = getApiBase();
  return apiBase ? `${apiBase}${path}` : path;
}

function getBetaAccessKey(): string {
  const fromEnv = import.meta.env.VITE_BETA_ACCESS_KEY;
  if (fromEnv) return fromEnv;
  return window.localStorage.getItem(betaStorageKey) ?? "";
}

function getRuntimeConfig(): DashboardRuntimeConfig {
  const apiBase = getApiBase();
  return {
    apiBase,
    apiBaseDefault: envApiBase,
    apiBaseOverrideActive: false,
    betaHeaderName,
    onlineConfigured: true,
    preferredMode: "online",
    snapshotGeneratedAt: "",
  };
}

function buildSourceInfo(): DataSourceInfo {
  const apiBase = getApiBase();
  return {
    mode: "online",
    preferredMode: "online",
    label: "服务端实时数据",
    detail: "前端统一通过服务端接口读取真实数据；行情、K 线和财报缓存由服务端负责。",
    apiBase,
    betaHeaderName,
    betaKeyPresent: Boolean(getBetaAccessKey()),
    snapshotGeneratedAt: "",
    fallbackReason: null,
  };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), requestTimeoutMs);
  const betaAccessKey = getBetaAccessKey();

  try {
    const response = await fetch(makeUrl(path), {
      headers: {
        "Content-Type": "application/json",
        ...(betaAccessKey ? { [betaHeaderName]: betaAccessKey } : {}),
        ...(init?.headers ?? {}),
      },
      ...init,
      signal: controller.signal,
    });

    if (!response.ok) {
      let detail = `${response.status} ${response.statusText}`;
      try {
        const payload = (await response.json()) as { detail?: string };
        if (payload.detail) detail = payload.detail;
      } catch {
        // Preserve fallback detail.
      }
      throw new Error(detail);
    }

    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error(`请求超时（>${requestTimeoutMs / 1000}s）`);
    }
    throw error;
  } finally {
    window.clearTimeout(timer);
  }
}

export const api = {
  getApiBase,
  getBetaAccessKey,
  setBetaAccessKey: (value: string) => {
    const trimmed = value.trim();
    if (trimmed) {
      window.localStorage.setItem(betaStorageKey, trimmed);
    } else {
      window.localStorage.removeItem(betaStorageKey);
    }
  },
  getRuntimeConfig,
  loadShellData: async (): Promise<ApiResult<DashboardShellPayload>> => {
    const [watchlist, candidates, glossary] = await Promise.all([
      request<WatchlistResponse>("/watchlist"),
      request<CandidateListResponse>("/dashboard/candidates?limit=8"),
      request<GlossaryEntryView[]>("/dashboard/glossary"),
    ]);
    return {
      data: { watchlist, candidates, glossary },
      source: buildSourceInfo(),
    };
  },
  bootstrapDemo: async (): Promise<ApiResult<DashboardBootstrapResponse>> => ({
    data: await request<DashboardBootstrapResponse>("/bootstrap/dashboard-demo", {
      method: "POST",
    }),
    source: buildSourceInfo(),
  }),
  addWatchlist: async (symbol: string, name?: string): Promise<WatchlistMutationResponse> =>
    request<WatchlistMutationResponse>("/watchlist", {
      method: "POST",
      body: JSON.stringify({
        symbol,
        name: name?.trim() || undefined,
      }),
    }),
  refreshWatchlist: async (symbol: string): Promise<WatchlistMutationResponse> =>
    request<WatchlistMutationResponse>(`/watchlist/${encodeURIComponent(symbol)}/refresh`, {
      method: "POST",
    }),
  removeWatchlist: async (symbol: string): Promise<WatchlistDeleteResponse> =>
    request<WatchlistDeleteResponse>(`/watchlist/${encodeURIComponent(symbol)}`, {
      method: "DELETE",
    }),
  getStockDashboard: async (symbol: string): Promise<ApiResult<StockDashboardResponse>> => ({
    data: await request<StockDashboardResponse>(`/stocks/${encodeURIComponent(symbol)}/dashboard`),
    source: buildSourceInfo(),
  }),
  getOperationsDashboard: async (sampleSymbol: string): Promise<ApiResult<OperationsDashboardResponse>> => ({
    data: await request<OperationsDashboardResponse>(
      `/dashboard/operations?sample_symbol=${encodeURIComponent(sampleSymbol)}`,
    ),
    source: buildSourceInfo(),
  }),
  getRuntimeSettings: async (): Promise<RuntimeSettingsResponse> =>
    request<RuntimeSettingsResponse>("/settings/runtime"),
  upsertProviderCredential: async (
    providerName: string,
    payload: ProviderCredentialUpsertRequest,
  ): Promise<void> => {
    await request(`/settings/provider-credentials/${encodeURIComponent(providerName)}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
  },
  createModelApiKey: async (payload: ModelApiKeyCreateRequest): Promise<void> => {
    await request("/settings/model-api-keys", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  updateModelApiKey: async (keyId: number, payload: ModelApiKeyUpdateRequest): Promise<void> => {
    await request(`/settings/model-api-keys/${keyId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },
  setDefaultModelApiKey: async (keyId: number): Promise<void> => {
    await request(`/settings/model-api-keys/${keyId}/default`, {
      method: "POST",
    });
  },
  deleteModelApiKey: async (keyId: number): Promise<ModelApiKeyDeleteResponse> =>
    request<ModelApiKeyDeleteResponse>(`/settings/model-api-keys/${keyId}`, {
      method: "DELETE",
    }),
  runFollowUpAnalysis: async (payload: FollowUpAnalysisRequest): Promise<FollowUpAnalysisResponse> =>
    request<FollowUpAnalysisResponse>("/analysis/follow-up", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};
