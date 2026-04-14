import type {
  CandidateListResponse,
  DashboardBootstrapResponse,
  GlossaryEntryView,
  StockDashboardResponse,
} from "./types";

const apiBase = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

function makeUrl(path: string): string {
  return apiBase ? `${apiBase}${path}` : path;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(makeUrl(path), {
    headers: {
      "Content-Type": "application/json",
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
  bootstrapDemo: () =>
    request<DashboardBootstrapResponse>("/bootstrap/dashboard-demo", {
      method: "POST",
    }),
  getCandidates: () => request<CandidateListResponse>("/dashboard/candidates?limit=8"),
  getGlossary: () => request<GlossaryEntryView[]>("/dashboard/glossary"),
  getStockDashboard: (symbol: string) =>
    request<StockDashboardResponse>(`/stocks/${encodeURIComponent(symbol)}/dashboard`),
};
