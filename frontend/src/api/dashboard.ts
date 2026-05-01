import { request, buildSourceInfo, operationsDashboardRequestBehavior } from "./core";
import type { DashboardShellPayload, WatchlistResponse, CandidateListResponse, GlossaryEntryView, ImprovementSuggestionView, ImprovementSuggestionsPayload, OperationsDashboardResponse, StockDashboardResponse } from "../types";

export function loadShellData(): Promise<{ data: DashboardShellPayload; source: ReturnType<typeof buildSourceInfo> }> {
  return (async () => {
    const [watchlist, candidates, glossary] = await Promise.all([
      request<WatchlistResponse>("/watchlist"),
      request<CandidateListResponse>("/dashboard/candidates?limit=8"),
      request<GlossaryEntryView[]>("/dashboard/glossary"),
    ]);
    return {
      data: { watchlist, candidates, glossary },
      source: buildSourceInfo(),
    };
  })();
}

export function getStockDashboard(symbol: string) {
  return (async () => ({
    data: await request<StockDashboardResponse>('/stocks/' + encodeURIComponent(symbol) + '/dashboard'),
    source: buildSourceInfo(),
  }))();
}

export function getOperationsDashboard(sampleSymbol: string) {
  return (async () => ({
    data: await request<OperationsDashboardResponse>(
      '/dashboard/operations?sample_symbol=' + encodeURIComponent(sampleSymbol),
      undefined,
      operationsDashboardRequestBehavior,
    ),
    source: buildSourceInfo(),
  }))();
}

export function getOperationsSummary(sampleSymbol: string) {
  return (async () => ({
    data: await request<OperationsDashboardResponse>(
      '/dashboard/operations/summary?sample_symbol=' + encodeURIComponent(sampleSymbol),
      undefined,
      operationsDashboardRequestBehavior,
    ),
    source: buildSourceInfo(),
  }))();
}

export function getOperationsDetails(section: string, sampleSymbol: string) {
  return (async () => ({
    data: await request<Record<string, any>>(
      '/dashboard/operations/details?section=' + encodeURIComponent(section) +
        '&sample_symbol=' + encodeURIComponent(sampleSymbol),
      undefined,
      operationsDashboardRequestBehavior,
    ),
    source: buildSourceInfo(),
  }))();
}

export function getImprovementSuggestionSummary() {
  return (async () => ({
    data: await request<ImprovementSuggestionsPayload>("/dashboard/improvement-suggestions/summary"),
    source: buildSourceInfo(),
  }))();
}

export function getImprovementSuggestionDetails(status?: string, category?: string) {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (category) params.set("category", category);
  const query = params.toString();
  return (async () => ({
    data: await request<ImprovementSuggestionsPayload>(
      `/dashboard/improvement-suggestions/details${query ? `?${query}` : ""}`,
      undefined,
      operationsDashboardRequestBehavior,
    ),
    source: buildSourceInfo(),
  }))();
}

export function runImprovementSuggestionReview(windowDays = 7) {
  return (async () => ({
    data: await request<ImprovementSuggestionsPayload>(
      `/dashboard/improvement-suggestions/run?window_days=${encodeURIComponent(String(windowDays))}`,
      { method: "POST" },
      operationsDashboardRequestBehavior,
    ),
    source: buildSourceInfo(),
  }))();
}

export function updateImprovementSuggestionStatus(suggestionId: string, status: string, reason: string) {
  return (async () => ({
    data: await request<ImprovementSuggestionView>(
      `/dashboard/improvement-suggestions/${encodeURIComponent(suggestionId)}/status`,
      {
        method: "POST",
        body: JSON.stringify({ status, reason }),
      },
      operationsDashboardRequestBehavior,
    ),
    source: buildSourceInfo(),
  }))();
}

export function acceptImprovementSuggestionForPlan(suggestionId: string, model: string, reason: string) {
  return (async () => ({
    data: await request<ImprovementSuggestionView>(
      `/dashboard/improvement-suggestions/${encodeURIComponent(suggestionId)}/accept-plan`,
      {
        method: "POST",
        body: JSON.stringify({ model, reason }),
      },
      operationsDashboardRequestBehavior,
    ),
    source: buildSourceInfo(),
  }))();
}
