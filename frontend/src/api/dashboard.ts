import { request, buildSourceInfo, operationsDashboardRequestBehavior } from "./core";
import type { DashboardShellPayload, WatchlistResponse, CandidateListResponse, GlossaryEntryView, OperationsDashboardResponse, StockDashboardResponse } from "../types";

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
