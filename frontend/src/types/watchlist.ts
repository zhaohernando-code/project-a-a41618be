// watchlist domain types
import type { CandidateItemView, CandidateListResponse, GlossaryEntryView } from "./stock";

export type CandidateWorkspaceRow = WatchlistItemView & {
  candidate: CandidateItemView | null;
};

export interface WatchlistItemView {
  symbol: string;
  name: string;
  exchange: string;
  ticker: string;
  status: string;
  source_kind: string;
  analysis_status: string;
  added_at: string;
  updated_at: string;
  last_analyzed_at?: string | null;
  last_error?: string | null;
  latest_direction?: string | null;
  latest_confidence_label?: string | null;
  latest_generated_at?: string | null;
}

export interface WatchlistResponse {
  generated_at: string;
  items: WatchlistItemView[];
}

export interface WatchlistMutationResponse {
  item: WatchlistItemView;
  message: string;
}

export interface WatchlistDeleteResponse {
  symbol: string;
  removed: boolean;
  active_count: number;
  removed_at: string;
}

export interface DashboardShellPayload {
  watchlist: WatchlistResponse;
  candidates: CandidateListResponse;
  glossary: GlossaryEntryView[];
}

