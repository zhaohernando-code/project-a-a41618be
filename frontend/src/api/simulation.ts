import { request, buildSourceInfo } from "./core";
import type {
  SimulationWorkspaceResponse,
  SimulationConfigRequest,
  SimulationControlActionResponse,
  SimulationEndRequest,
  ManualSimulationOrderRequest,
} from "../types";

export function getSimulationWorkspace() {
  return (async () => ({
    data: await request<SimulationWorkspaceResponse>("/simulation/workspace"),
    source: buildSourceInfo(),
  }))();
}

export function updateSimulationConfig(payload: SimulationConfigRequest): Promise<SimulationControlActionResponse> {
  return request<SimulationControlActionResponse>("/simulation/config", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function startSimulation(): Promise<SimulationControlActionResponse> {
  return request<SimulationControlActionResponse>("/simulation/start", { method: "POST" });
}

export function pauseSimulation(): Promise<SimulationControlActionResponse> {
  return request<SimulationControlActionResponse>("/simulation/pause", { method: "POST" });
}

export function resumeSimulation(): Promise<SimulationControlActionResponse> {
  return request<SimulationControlActionResponse>("/simulation/resume", { method: "POST" });
}

export function stepSimulation(): Promise<SimulationControlActionResponse> {
  return request<SimulationControlActionResponse>("/simulation/step", { method: "POST" });
}

export function restartSimulation(): Promise<SimulationControlActionResponse> {
  return request<SimulationControlActionResponse>("/simulation/restart", { method: "POST" });
}

export function endSimulation(payload: SimulationEndRequest): Promise<SimulationControlActionResponse> {
  return request<SimulationControlActionResponse>("/simulation/end", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function submitManualSimulationOrder(payload: ManualSimulationOrderRequest): Promise<SimulationControlActionResponse> {
  return request<SimulationControlActionResponse>("/simulation/manual-order", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
