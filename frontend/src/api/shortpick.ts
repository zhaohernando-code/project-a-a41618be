import { request, buildSourceInfo, longRunningRequestBehavior, operationsDashboardRequestBehavior } from "./core";
import type {
  ShortpickCandidateListResponse,
  ShortpickCandidateView,
  ShortpickRunCreateRequest,
  ShortpickRunListResponse,
  ShortpickRunValidateRequest,
  ShortpickRunView,
} from "../types";

export function getShortpickRuns(limit = 20) {
  return (async () => ({
    data: await request<ShortpickRunListResponse>(
      `/shortpick-lab/runs?limit=${encodeURIComponent(String(limit))}`,
      undefined,
      operationsDashboardRequestBehavior,
    ),
    source: buildSourceInfo(),
  }))();
}

export function getShortpickRun(runId: number) {
  return (async () => ({
    data: await request<ShortpickRunView>(
      `/shortpick-lab/runs/${encodeURIComponent(String(runId))}`,
      undefined,
      operationsDashboardRequestBehavior,
    ),
    source: buildSourceInfo(),
  }))();
}

export function createShortpickRun(payload: ShortpickRunCreateRequest) {
  return (async () => ({
    data: await request<ShortpickRunView>(
      "/shortpick-lab/runs",
      { method: "POST", body: JSON.stringify(payload) },
      longRunningRequestBehavior,
    ),
    source: buildSourceInfo(),
  }))();
}

export function validateShortpickRun(runId: number, payload: ShortpickRunValidateRequest) {
  return (async () => ({
    data: await request<Record<string, unknown>>(
      `/shortpick-lab/runs/${encodeURIComponent(String(runId))}/validate`,
      { method: "POST", body: JSON.stringify(payload) },
      operationsDashboardRequestBehavior,
    ),
    source: buildSourceInfo(),
  }))();
}

export function getShortpickCandidates(params?: {
  runId?: number;
  priority?: string;
  validationStatus?: string;
  model?: string;
  limit?: number;
}) {
  const query = new URLSearchParams();
  if (params?.runId) query.set("run_id", String(params.runId));
  if (params?.priority) query.set("priority", params.priority);
  if (params?.validationStatus) query.set("validation_status", params.validationStatus);
  if (params?.model) query.set("model", params.model);
  if (params?.limit) query.set("limit", String(params.limit));
  const serialized = query.toString();
  return (async () => ({
    data: await request<ShortpickCandidateListResponse>(
      `/shortpick-lab/candidates${serialized ? `?${serialized}` : ""}`,
      undefined,
      operationsDashboardRequestBehavior,
    ),
    source: buildSourceInfo(),
  }))();
}

export function getShortpickCandidate(candidateId: number) {
  return (async () => ({
    data: await request<ShortpickCandidateView>(
      `/shortpick-lab/candidates/${encodeURIComponent(String(candidateId))}`,
      undefined,
      operationsDashboardRequestBehavior,
    ),
    source: buildSourceInfo(),
  }))();
}
