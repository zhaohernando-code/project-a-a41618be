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

const betaHeaderName = import.meta.env.VITE_BETA_ACCESS_HEADER ?? "X-Ashare-Beta-Key";
const betaStorageKey = "ashare-beta-access-key";
const requestTimeoutMs = 10000;
const htmlPrefixes = ["<!doctype", "<html", "<?xml"];
const notFoundSignatures = ["tool not found", "tool_not_found", "404 not found"];
const localApiBaseStorageKey = "ashare-api-base-url";

type ApiResult<T> = {
  data: T;
  source: DataSourceInfo;
};

function normalizeApiBase(value: string | null | undefined): string {
  return (value ?? "").trim().replace(/\/$/, "");
}

const envApiBase = normalizeApiBase(import.meta.env.VITE_API_BASE_URL ?? "");

function readApiBaseFromStorage(): string {
  if (typeof window === "undefined") {
    return "";
  }
  return normalizeApiBase(window.localStorage.getItem(localApiBaseStorageKey));
}

function inferAssetMountedBase(): string {
  const modulePath = new URL(import.meta.url).pathname;
  const markerIndex = modulePath.lastIndexOf("/assets/");
  if (markerIndex < 0) {
    return "";
  }
  return normalizeApiBase(modulePath.slice(0, markerIndex));
}

function inferLocationBasedBase(): string {
  const path = window.location.pathname;
  const segments = path.split("?")[0].split("/").filter(Boolean);
  const hasTrailingSlash = path.endsWith("/");
  if (segments.length <= 1) {
    return normalizeApiBase(hasTrailingSlash ? `/${segments.join("/")}` : "");
  }
  if (hasTrailingSlash) {
    return normalizeApiBase(`/${segments.join("/")}`);
  }
  return normalizeApiBase(`/${segments.slice(0, -1).join("/")}`);
}

function inferLocalBackendBase(): string {
  const host = window.location.hostname.toLowerCase();
  if (!host) {
    return "";
  }
  if (host === "localhost" || host === "127.0.0.1" || host === "::1") {
    return normalizeApiBase(`${window.location.protocol}//${host}:8000`);
  }
  return "";
}

function dedupe(values: string[]): string[] {
  const out: string[] = [];
  for (const value of values) {
    if (!out.includes(value)) {
      out.push(value);
    }
  }
  return out;
}

function getApiBases(): string[] {
  return dedupe([
    envApiBase,
    readApiBaseFromStorage(),
    inferAssetMountedBase(),
    inferLocationBasedBase(),
    inferLocalBackendBase(),
  ]).filter(Boolean);
}

function hasExplicitApiBase(): boolean {
  return Boolean(envApiBase || readApiBaseFromStorage());
}

function getApiBase(): string {
  const bases = getApiBases();
  return bases[0] ?? "";
}

function buildRequestUrls(path: string): string[] {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const bases = getApiBases();
  const explicitBase = hasExplicitApiBase();
  const urls: string[] = [];
  const basesToUse = [...bases];
  if (!explicitBase && !basesToUse.includes("")) {
    basesToUse.push("");
  }

  for (const base of basesToUse) {
    if (base) {
      if (base.endsWith("/api")) {
        const baseWithoutApi = base.slice(0, -4);
        urls.push(`${base}${normalizedPath}`);
        if (!baseWithoutApi) {
          urls.push(normalizedPath);
        } else {
          urls.push(`${baseWithoutApi}${normalizedPath}`);
        }
      } else {
        urls.push(`${base}/api${normalizedPath}`);
        urls.push(`${base}${normalizedPath}`);
      }
      continue;
    }

    urls.push(normalizedPath);
    if (!explicitBase) {
      urls.push(`/api${normalizedPath}`);
    }
  }
  return dedupe(urls);
}

type HtmlErrorContext = {
  kind: "html";
  endpoint: string;
  fullUrl: string;
  preview: string;
};

type ApiResponseError = Error & {
  apiErrorContext?: HtmlErrorContext;
};

function isHtmlResponseError(error: unknown): error is ApiResponseError {
  return (
    Boolean(error)
    && typeof error === "object"
    && (error as ApiResponseError).apiErrorContext?.kind === "html"
  );
}

function createHtmlError(endpoint: string, fullUrl: string, preview: string): ApiResponseError {
  const error = new Error(
    `接口返回 HTML（路径: ${endpoint}，请求地址: ${fullUrl}）。通常表示请求打到了前端页面或前端路由重定向而非 FastAPI 接口。请确认服务端已启动、路径正确，且页面未错误代理到静态站点。响应片段：${preview}`,
  ) as ApiResponseError;
  error.apiErrorContext = {
    kind: "html",
    endpoint,
    fullUrl,
    preview,
  };
  return error;
}

function getBetaAccessKey(): string {
  const fromEnv = import.meta.env.VITE_BETA_ACCESS_KEY;
  if (fromEnv) return fromEnv;
  return window.localStorage.getItem(betaStorageKey) ?? "";
}

function getRuntimeConfig(): DashboardRuntimeConfig {
  const apiBase = getApiBase();
  const storageBase = readApiBaseFromStorage();
  return {
    apiBase,
    apiBaseDefault: envApiBase,
    apiBaseOverrideActive: Boolean(storageBase),
    betaHeaderName,
    onlineConfigured: true,
    preferredMode: "online",
    snapshotGeneratedAt: "",
  };
}

function isJsonContent(contentType: string | null): boolean {
  const normalized = (contentType ?? "").toLowerCase();
  return (
    normalized.includes("application/json")
    || normalized.includes("application/problem+json")
    || normalized.includes("text/json")
    || normalized.includes("+json")
  );
}

async function readTextPreview(response: Response, maxChars = 220): Promise<string> {
  const text = await response.clone().text();
  const compact = text.replace(/\s+/g, " ").trim();
  return compact.length > maxChars ? `${compact.slice(0, maxChars)}...` : compact;
}

function isLikelyHtmlText(text: string): boolean {
  const compact = text.trim().toLowerCase().slice(0, 64);
  return htmlPrefixes.some((prefix) => compact.startsWith(prefix));
}

function isLikelyServiceNotFoundText(text: string): boolean {
  const compact = text.trim().toLowerCase();
  return notFoundSignatures.some((signature) => compact.includes(signature));
}

function toPreview(text: string, maxChars = 220): string {
  const compact = text.replace(/\s+/g, " ").trim();
  return compact.length > maxChars ? `${compact.slice(0, maxChars)}...` : compact;
}

async function parseJsonResponse<T>(response: Response, endpoint: string): Promise<T> {
  const contentType = response.headers.get("content-type");
  const text = await response.text();

  if (isLikelyHtmlText(text)) {
    throw createHtmlError(endpoint, response.url, toPreview(text));
  }
  if (isLikelyServiceNotFoundText(text)) {
    throw createHtmlError(endpoint, response.url, toPreview(text));
  }

  if (!isJsonContent(contentType) && contentType !== null) {
    const preview = toPreview(text);
    throw new Error(
      `接口返回非 JSON 内容。content-type="${contentType}". 可能访问到了前端页面或重定向页。响应片段：${preview}`,
    );
  }

  try {
    return JSON.parse(text) as T;
  } catch {
    const preview = toPreview(text);
    throw new Error(`响应不是有效 JSON。响应片段：${preview}`);
  }
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
  const requestUrls = buildRequestUrls(path);

  try {
    for (let index = 0; index < requestUrls.length; index += 1) {
      const requestUrl = requestUrls[index];
      try {
        const response = await fetch(requestUrl, {
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
          const canTryNext = index < requestUrls.length - 1;
          try {
            const contentType = response.headers.get("content-type");
            if (isJsonContent(contentType)) {
              const payload = JSON.parse(await response.text()) as { detail?: string };
              if (payload.detail) {
                detail = payload.detail;
              }
              if (response.status === 404 && canTryNext) {
                continue;
              }
            } else {
              const preview = await readTextPreview(response);
              if (
                (response.status === 404 || isLikelyServiceNotFoundText(preview) || isLikelyHtmlText(preview))
                && canTryNext
              ) {
                continue;
              }
              if (preview) {
                detail = `${detail}（响应片段：${preview}）`;
              }
            }
          } catch (error) {
            if (isHtmlResponseError(error) && index < requestUrls.length - 1) {
              continue;
            }
            throw error;
          }

          throw new Error(detail);
        }

        try {
          return await parseJsonResponse<T>(response, path);
        } catch (error) {
          if (isHtmlResponseError(error) && index < requestUrls.length - 1) {
            continue;
          }
          throw error;
        }
      } catch (error) {
        if (isHtmlResponseError(error) && index < requestUrls.length - 1) {
          continue;
        }
        throw error;
      }
    }

    throw new Error(
      `接口请求失败（路径: ${path}）。已尝试 ${requestUrls.join(" / ")}，但均未返回可解析 JSON 的 API 响应。`,
    );
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
