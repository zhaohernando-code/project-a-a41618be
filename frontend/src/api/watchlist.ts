import { request } from "./core";
import type { WatchlistMutationResponse, WatchlistDeleteResponse } from "../types";

export function addWatchlist(symbol: string, name?: string): Promise<WatchlistMutationResponse> {
  return request<WatchlistMutationResponse>("/watchlist", {
    method: "POST",
    body: JSON.stringify({ symbol, name: name?.trim() || undefined }),
  });
}

export function refreshWatchlist(symbol: string): Promise<WatchlistMutationResponse> {
  return request<WatchlistMutationResponse>('/watchlist/' + encodeURIComponent(symbol) + '/refresh', {
    method: "POST",
  });
}

export function removeWatchlist(symbol: string): Promise<WatchlistDeleteResponse> {
  return request<WatchlistDeleteResponse>('/watchlist/' + encodeURIComponent(symbol), {
    method: "DELETE",
  });
}
