import { request, buildManualResearchQuery, manualResearchRequestBehavior } from "./core";
import type {
  ManualResearchRequestCreateRequest,
  ManualResearchRequestExecuteRequest,
  ManualResearchRequestCompleteRequest,
  ManualResearchRequestFailRequest,
  ManualResearchRequestRetryRequest,
  ManualResearchRequestView,
  ManualResearchRequestListResponse,
  FollowUpAnalysisRequest,
  FollowUpAnalysisResponse,
} from "../types";

export function createManualResearchRequest(payload: ManualResearchRequestCreateRequest): Promise<ManualResearchRequestView> {
  return request<ManualResearchRequestView>("/manual-research/requests", {
    method: "POST",
    body: JSON.stringify(payload),
  }, manualResearchRequestBehavior);
}

export function listManualResearchRequests(params?: { symbol?: string; status?: string; executorKind?: string; includeSuperseded?: boolean }): Promise<ManualResearchRequestListResponse> {
  return request<ManualResearchRequestListResponse>('/manual-research/requests' + buildManualResearchQuery(params));
}

export function getManualResearchRequest(requestId: number): Promise<ManualResearchRequestView> {
  return request<ManualResearchRequestView>('/manual-research/requests/' + requestId);
}

export function executeManualResearchRequest(requestId: number, payload: ManualResearchRequestExecuteRequest): Promise<ManualResearchRequestView> {
  return request<ManualResearchRequestView>('/manual-research/requests/' + requestId + '/execute', {
    method: "POST",
    body: JSON.stringify(payload),
  }, manualResearchRequestBehavior);
}

export function completeManualResearchRequest(requestId: number, payload: ManualResearchRequestCompleteRequest): Promise<ManualResearchRequestView> {
  return request<ManualResearchRequestView>('/manual-research/requests/' + requestId + '/complete', {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function failManualResearchRequest(requestId: number, payload: ManualResearchRequestFailRequest): Promise<ManualResearchRequestView> {
  return request<ManualResearchRequestView>('/manual-research/requests/' + requestId + '/fail', {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function retryManualResearchRequest(requestId: number, payload: ManualResearchRequestRetryRequest): Promise<ManualResearchRequestView> {
  return request<ManualResearchRequestView>('/manual-research/requests/' + requestId + '/retry', {
    method: "POST",
    body: JSON.stringify(payload),
  }, manualResearchRequestBehavior);
}

export function runFollowUpAnalysis(payload: FollowUpAnalysisRequest): Promise<FollowUpAnalysisResponse> {
  return request<FollowUpAnalysisResponse>("/analysis/follow-up", {
    method: "POST",
    body: JSON.stringify(payload),
  }, manualResearchRequestBehavior);
}
