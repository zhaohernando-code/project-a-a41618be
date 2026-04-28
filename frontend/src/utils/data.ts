// data helper functions
import type { CandidateItemView, CandidateWorkspaceRow, DataSourceInfo, SimulationModelAdviceView, SimulationTrackStateView, SimulationWorkspaceResponse, WatchlistItemView } from "../types";
import { api } from "../api";
import { formatNumber, formatPercent, formatSignedNumber, sanitizeDisplayText } from "./format";
import { compactValidationNote, validationStatusLabel } from "./labels";

export function buildInitialSourceInfo(): DataSourceInfo {
  const runtimeConfig = api.getRuntimeConfig();
  return {
    mode: "online",
    preferredMode: "online",
    label: "服务端实时数据",
    detail: "页面统一通过服务端读取真实行情、K 线和财报；缓存与上游切换由服务端负责。",
    apiBase: runtimeConfig.apiBase,
    betaHeaderName: runtimeConfig.betaHeaderName,
    betaKeyPresent: Boolean(api.getBetaAccessKey()),
    snapshotGeneratedAt: "",
    fallbackReason: null,
  };
}


export function mergeSourceInfo(primary: DataSourceInfo | null | undefined, secondary: DataSourceInfo | null | undefined): DataSourceInfo {
  if (!primary && !secondary) {
    return buildInitialSourceInfo();
  }
  if (!primary) {
    return secondary as DataSourceInfo;
  }
  if (!secondary) {
    return primary;
  }

  return {
    ...primary,
    ...secondary,
    fallbackReason: secondary.fallbackReason ?? primary.fallbackReason ?? null,
  };
}


export function inferExchangeFromSymbol(symbol: string): string {
  if (symbol.endsWith(".SH")) return "SSE";
  if (symbol.endsWith(".SZ")) return "SZSE";
  return "--";
}


export function buildCandidateWorkspaceRows(
  watchlist: WatchlistItemView[],
  candidates: CandidateItemView[],
): CandidateWorkspaceRow[] {
  const candidateBySymbol = new Map(candidates.map((item) => [item.symbol, item] as const));
  const seen = new Set<string>();
  const rows: CandidateWorkspaceRow[] = [];

  watchlist.forEach((item) => {
    seen.add(item.symbol);
    rows.push({
      ...item,
      candidate: candidateBySymbol.get(item.symbol) ?? null,
    });
  });

  candidates.forEach((candidate) => {
    if (seen.has(candidate.symbol)) {
      return;
    }
    rows.push({
      symbol: candidate.symbol,
      name: candidate.name,
      exchange: inferExchangeFromSymbol(candidate.symbol),
      ticker: candidate.symbol.split(".")[0] ?? candidate.symbol,
      status: "active",
      source_kind: "candidate_only",
      analysis_status: "ready",
      added_at: candidate.generated_at,
      updated_at: candidate.generated_at,
      last_analyzed_at: candidate.generated_at,
      last_error: null,
      latest_direction: candidate.direction,
      latest_confidence_label: candidate.confidence_label,
      latest_generated_at: candidate.generated_at,
      candidate,
    });
  });

  return rows.sort((left, right) => {
    const leftRank = left.candidate?.rank ?? Number.MAX_SAFE_INTEGER;
    const rightRank = right.candidate?.rank ?? Number.MAX_SAFE_INTEGER;
    if (leftRank !== rightRank) {
      return leftRank - rightRank;
    }
    return left.symbol.localeCompare(right.symbol);
  });
}


export type TrackTableRow = {
  symbol: string;
  name: string;
  quantity: number;
  avg_cost: number;
  last_price: number;
  total_pnl: number;
  holding_pnl_pct?: number | null;
  today_pnl_amount: number;
  today_pnl_pct?: number | null;
  portfolio_weight: number;
};


export function buildTrackTableRows(
  track: SimulationTrackStateView,
  watchSymbols: string[],
  candidateRows: CandidateWorkspaceRow[],
  symbolNameMap: Map<string, string>,
  modelAdvices: SimulationModelAdviceView[],
): TrackTableRow[] {
  const holdingBySymbol = new Map(track.portfolio.holdings.map((item) => [item.symbol, item] as const));
  const candidateBySymbol = new Map(candidateRows.map((item) => [item.symbol, item] as const));
  const adviceBySymbol = new Map(modelAdvices.map((item) => [item.symbol, item] as const));
  const sourceSymbols = watchSymbols.length > 0
    ? watchSymbols
    : track.portfolio.holdings.map((item) => item.symbol);

  return sourceSymbols.map((symbol) => {
    const holding = holdingBySymbol.get(symbol);
    const candidateRow = candidateBySymbol.get(symbol);
    const advice = adviceBySymbol.get(symbol);
    const resolvedName = symbolNameMap.get(symbol) ?? holding?.name ?? candidateRow?.name ?? advice?.stock_name ?? symbol;
    const fallbackLastPrice = candidateRow?.candidate?.last_close ?? advice?.reference_price ?? 0;

    if (holding) {
      return {
        symbol,
        name: holding.name || resolvedName,
        quantity: holding.quantity,
        avg_cost: holding.avg_cost,
        last_price: holding.last_price || fallbackLastPrice,
        total_pnl: holding.total_pnl,
        holding_pnl_pct: holding.holding_pnl_pct ?? 0,
        today_pnl_amount: holding.today_pnl_amount,
        today_pnl_pct: holding.today_pnl_pct ?? 0,
        portfolio_weight: holding.portfolio_weight,
      };
    }

    return {
      symbol,
      name: resolvedName,
      quantity: 0,
      avg_cost: 0,
      last_price: fallbackLastPrice,
      total_pnl: 0,
      holding_pnl_pct: 0,
      today_pnl_amount: 0,
      today_pnl_pct: 0,
      portfolio_weight: 0,
    };
  });
}


export function resolveSimulationFocusSymbol(workspace: SimulationWorkspaceResponse): string | null {
  return workspace.session.focus_symbol
    ?? workspace.configuration.focus_symbol
    ?? workspace.session.watch_symbols[0]
    ?? workspace.configuration.watch_symbols[0]
    ?? null;
}

