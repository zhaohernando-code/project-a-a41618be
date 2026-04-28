// format helper functions
import type { SimulationModelAdviceView } from "../types";
import { numberFormatter, percentFormatter, signedNumberFormatter } from "./constants";

export function formatDate(value?: string | null): string {
  if (!value) return "未提供";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}


export function formatNumber(value?: number | null): string {
  if (value === null || value === undefined) return "--";
  return numberFormatter.format(value);
}


export function simulationAdviceActionLabel(advice?: SimulationModelAdviceView | null): string {
  if (!advice) return "继续观望";
  if (advice.policy_type === "manual_review_preview_policy_v1") {
    if (advice.action === "buy") return "买入候选";
    if (advice.action === "sell") return "卖出候选";
    return "继续观望";
  }
  if (advice.action === "buy") return "建议买入";
  if (advice.action === "sell") return "建议卖出";
  return "继续观望";
}


export function simulationAdvicePolicyLabel(advice?: SimulationModelAdviceView | null): string {
  if (!advice?.policy_type) return "策略说明";
  if (advice.policy_type === "manual_review_preview_policy_v1") return "人工复核预览";
  if (advice.policy_type === "phase5_simulation_topk_equal_weight_v1") return "等权组合研究策略";
  return "策略说明";
}


export function formatSignedNumber(value?: number | null): string {
  if (value === null || value === undefined) return "--";
  if (value === 0) return "0";
  return signedNumberFormatter.format(value);
}


export function formatPercent(value?: number | null): string {
  if (value === null || value === undefined) return "--";
  return percentFormatter.format(value);
}


export function normalizeDisplayText(value: string): string {
  return value
    .replace(/\s+/g, " ")
    .replace(/尚尚未/g, "尚未")
    .trim();
}


export function valueTone(value?: number | null): "positive" | "negative" | "neutral" {
  if (value === null || value === undefined || value === 0) return "neutral";
  return value > 0 ? "positive" : "negative";
}


export function directionColor(direction: string): string {
  if (direction === "buy") return "green";
  if (direction === "watch") return "blue";
  if (direction === "reduce") return "orange";
  if (direction === "risk_alert") return "red";
  return "default";
}


export function statusColor(status: string): string {
  if (["pass", "hit", "closed_beta_ready", "online", "completed"].includes(status)) return "green";
  if (["warn", "hold", "pending", "offline", "queued", "in_progress", "stale"].includes(status)) return "gold";
  if (["fail", "miss", "risk_alert", "failed"].includes(status)) return "red";
  return "default";
}

