import type {
  CandidateListResponse,
  DashboardBootstrapResponse,
  GlossaryEntryView,
  OperationsDashboardResponse,
  StockDashboardResponse,
} from "./types";

const apiBase = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");
const betaHeaderName = import.meta.env.VITE_BETA_ACCESS_HEADER ?? "X-Ashare-Beta-Key";
const betaStorageKey = "ashare-beta-access-key";

function makeUrl(path: string): string {
  return apiBase ? `${apiBase}${path}` : path;
}

function getBetaAccessKey(): string {
  const fromEnv = import.meta.env.VITE_BETA_ACCESS_KEY;
  if (fromEnv) return fromEnv;
  return window.localStorage.getItem(betaStorageKey) ?? "";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const betaAccessKey = getBetaAccessKey();
  const response = await fetch(makeUrl(path), {
    headers: {
      "Content-Type": "application/json",
      ...(betaAccessKey ? { [betaHeaderName]: betaAccessKey } : {}),
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload.detail) {
        detail = payload.detail;
      }
    } catch {
      // ignore json parse failure and fall back to status
    }
    throw new Error(detail);
  }

  return (await response.json()) as T;
}

export const api = {
  getBetaAccessKey,
  setBetaAccessKey: (value: string) => {
    const trimmed = value.trim();
    if (trimmed) {
      window.localStorage.setItem(betaStorageKey, trimmed);
    } else {
      window.localStorage.removeItem(betaStorageKey);
    }
  },
  bootstrapDemo: () =>
    request<DashboardBootstrapResponse>("/bootstrap/dashboard-demo", {
      method: "POST",
    }),
  getCandidates: () => request<CandidateListResponse>("/dashboard/candidates?limit=8"),
  getGlossary: () => request<GlossaryEntryView[]>("/dashboard/glossary"),
  getStockDashboard: (symbol: string) =>
    request<StockDashboardResponse>(`/stocks/${encodeURIComponent(symbol)}/dashboard`),
  getOperationsDashboard: (sampleSymbol = "600519.SH") =>
    request<OperationsDashboardResponse>(`/dashboard/operations?sample_symbol=${encodeURIComponent(sampleSymbol)}`),
};
