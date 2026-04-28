import {
  BarChartOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  LineChartOutlined,
  MoonOutlined,
  PlusOutlined,
  ReloadOutlined,
  SettingOutlined,
  StockOutlined,
  SunOutlined,
  SyncOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Col,
  Collapse,
  Descriptions,
  Empty,
  Form,
  Grid,
  Input,
  InputNumber,
  List,
  Modal,
  Popover,
  Row,
  Select,
  Skeleton,
  Space,
  Statistic,
  Switch,
  Table,
  Tabs,
  Tag,
  Timeline,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { init } from "echarts";
import type { MouseEvent, ReactNode } from "react";
import { startTransition, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import type {
  CandidateItemView,
  ClaimGateView,
  DataSourceInfo,
  DashboardRuntimeConfig,
  GlossaryEntryView,
  ManualResearchRequestView,
  ModelApiKeyView,
  ManualSimulationOrderRequest,
  OperationsDashboardResponse,
  OperationsLaunchReadinessView,
  OperationsResearchValidationView,
  PortfolioNavPointView,
  PortfolioHoldingView,
  PortfolioSummaryView,
  PricePointView,
  RecommendationReplayView,
  RuntimeFieldMappingView,
  SimulationModelAdviceView,
  RuntimeDataSourceView,
  RuntimeSettingsResponse,
  SimulationConfigRequest,
  SimulationTrackStateView,
  SimulationWorkspaceResponse,
  StockDashboardResponse,
  WatchlistItemView,
} from "./types";

const { Paragraph, Text, Title } = Typography;
const { TextArea } = Input;

type ViewMode = "candidates" | "stock" | "operations" | "settings";
type ThemeMode = "light" | "dark";

type CandidateWorkspaceRow = WatchlistItemView & {
  candidate: CandidateItemView | null;
};

type ViewCard = {
  key: ViewMode;
  label: string;
  description: string;
  icon: ReactNode;
};

const numberFormatter = new Intl.NumberFormat("zh-CN", {
  maximumFractionDigits: 2,
});

const signedNumberFormatter = new Intl.NumberFormat("zh-CN", {
  maximumFractionDigits: 2,
  signDisplay: "always",
});

const percentFormatter = new Intl.NumberFormat("zh-CN", {
  style: "percent",
  maximumFractionDigits: 1,
  signDisplay: "always",
});

const directionLabels: Record<string, string> = {
  buy: "偏积极",
  watch: "继续观察",
  reduce: "偏谨慎",
  risk_alert: "风险提示",
};

const factorLabels: Record<string, string> = {
  price_baseline: "价格基线",
  news_event: "新闻事件",
  manual_review_layer: "人工研究层",
  llm_assessment: "人工研究参考",
  fusion: "融合评分",
};

const manualResearchVerdictOptions = [
  { value: "supports_current_recommendation", label: "支持当前建议" },
  { value: "mixed", label: "部分支持 / 部分保留" },
  { value: "contradicts_current_recommendation", label: "与当前建议冲突" },
  { value: "insufficient_evidence", label: "证据不足" },
];

function formatDate(value?: string | null): string {
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

function formatNumber(value?: number | null): string {
  if (value === null || value === undefined) return "--";
  return numberFormatter.format(value);
}

function simulationAdviceActionLabel(advice?: SimulationModelAdviceView | null): string {
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

function simulationAdvicePolicyLabel(advice?: SimulationModelAdviceView | null): string {
  if (!advice?.policy_type) return "策略说明";
  if (advice.policy_type === "manual_review_preview_policy_v1") return "人工复核预览";
  if (advice.policy_type === "phase5_simulation_topk_equal_weight_v1") return "等权组合研究策略";
  return "策略说明";
}

function formatSignedNumber(value?: number | null): string {
  if (value === null || value === undefined) return "--";
  if (value === 0) return "0";
  return signedNumberFormatter.format(value);
}

function formatPercent(value?: number | null): string {
  if (value === null || value === undefined) return "--";
  return percentFormatter.format(value);
}

function normalizeDisplayText(value: string): string {
  return value
    .replace(/\s+/g, " ")
    .replace(/尚尚未/g, "尚未")
    .trim();
}

function valueTone(value?: number | null): "positive" | "negative" | "neutral" {
  if (value === null || value === undefined || value === 0) return "neutral";
  return value > 0 ? "positive" : "negative";
}

function directionColor(direction: string): string {
  if (direction === "buy") return "green";
  if (direction === "watch") return "blue";
  if (direction === "reduce") return "orange";
  if (direction === "risk_alert") return "red";
  return "default";
}

function statusColor(status: string): string {
  if (["pass", "hit", "closed_beta_ready", "online", "completed"].includes(status)) return "green";
  if (["warn", "hold", "pending", "offline", "queued", "in_progress", "stale"].includes(status)) return "gold";
  if (["fail", "miss", "risk_alert", "failed"].includes(status)) return "red";
  return "default";
}

function validationStatusLabel(status?: string | null): string {
  if (status === "verified") return "已验证";
  if (status === "synthetic_demo") return "参考样本";
  if (status === "manual_trigger_required") return "待补充人工研究";
  if (status === "approved_for_product") return "已批准接入产品";
  if (status === "pending_rebuild") return "口径校准中";
  if (status === "research_candidate") return "研究观察中";
  return status || "未提供";
}

function claimGateStatusLabel(status?: string | null): string {
  if (status === "claim_ready") return "可引用结论";
  if (status === "observe_only") return "仅观察";
  if (status === "insufficient_validation") return "验证不足";
  return status || "未提供";
}

function claimGateAlertType(status?: string | null): "success" | "warning" | "error" | "info" {
  if (status === "claim_ready") return "success";
  if (status === "observe_only") return "warning";
  if (status === "insufficient_validation") return "error";
  return "info";
}

function dedupeDisplaySentences(value?: string | null): string {
  if (!value) return "";
  const fragments = normalizeDisplayText(value)
    .split(/[。！？]/)
    .map((item) => item.trim())
    .filter(Boolean);
  const seen = new Set<string>();
  const unique = fragments.filter((item) => {
    const key = item.replace(/[，；、\s]/g, "");
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  return unique.length > 0 ? `${unique.join("。")}。` : "";
}

function compactValidationNote(
  note?: string | null,
  status?: string | null,
  fallback = "以最新研究验证为准",
): string {
  if (status === "research_candidate") {
    return "已有滚动验证产物，当前仍处于观察阶段，只用于复盘和模拟。";
  }
  if (status === "pending_rebuild") {
    return "历史样本仍在补齐，当前先作为辅助观察使用。";
  }
  const compacted = dedupeDisplaySentences(note ? sanitizeDisplayText(note) : "");
  return compacted || (status ? validationStatusLabel(status) : fallback);
}

function isChinaMarketTradingTimestamp(value?: string | null): boolean {
  if (!value) return false;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return false;
  const now = new Date();
  if (parsed.toDateString() !== now.toDateString()) return false;
  const minutes = parsed.getHours() * 60 + parsed.getMinutes();
  const morning = minutes >= 9 * 60 + 30 && minutes <= 11 * 60 + 30;
  const afternoon = minutes >= 13 * 60 && minutes <= 15 * 60;
  return morning || afternoon;
}

function formatMarketFreshness(
  latencySeconds?: number | null,
  latestMarketDataAt?: string | null,
  compact = false,
): string {
  if (latestMarketDataAt && !isChinaMarketTradingTimestamp(latestMarketDataAt)) {
    return compact ? `收盘 ${formatDate(latestMarketDataAt)}` : `截至 ${formatDate(latestMarketDataAt)}`;
  }
  if (latencySeconds === null || latencySeconds === undefined) {
    return latestMarketDataAt ? formatDate(latestMarketDataAt) : "--";
  }
  if (latencySeconds < 60) return `${latencySeconds} 秒`;
  if (latencySeconds < 3600) return `${Math.round(latencySeconds / 60)} 分钟`;
  return latestMarketDataAt ? `截至 ${formatDate(latestMarketDataAt)}` : `${Math.round(latencySeconds / 3600)} 小时`;
}

function portfolioTrackLabel(portfolio: PortfolioSummaryView): string {
  if (portfolio.mode === "manual") return "用户轨道";
  if (portfolio.mode === "auto_model") return "模型轨道";
  return sanitizeDisplayText(portfolio.mode_label || portfolio.name);
}

function portfolioTrackSummary(portfolio: PortfolioSummaryView): string {
  if (portfolio.mode === "manual") {
    return "记录手动下单结果，用来复盘人工执行是否跟上建议。";
  }
  if (portfolio.mode === "auto_model") {
    return "记录模型在模拟盘内的自动调仓结果，用来观察组合纪律与执行损耗。";
  }
  return sanitizeDisplayText(portfolio.strategy_summary);
}

function portfolioStatusNote(portfolio: PortfolioSummaryView): string | null {
  const parts: string[] = [];
  if (portfolio.mode === "manual") {
    parts.push("当前只复盘手动下单结果，不自动调仓。");
  }
  if (portfolio.mode === "auto_model") {
    parts.push("模型轨道仅在模拟盘自动调仓，不会触发真实交易。");
  }
  if (portfolio.validation_status !== "verified" || portfolio.performance.validation_mode === "migration_placeholder") {
    parts.push("组合指标已接入最新研究结果，正式验证仍在补样本。");
  }
  const summary = dedupeDisplaySentences(parts.join(" "));
  return summary || null;
}

function claimGateDescription(claimGate?: ClaimGateView | null): string {
  if (!claimGate) return "当前缺少结论门槛说明。";
  const parts = [claimGate.note, ...claimGate.blocking_reasons.slice(0, 2)].filter(
    (item): item is string => Boolean(item && item.trim()),
  );
  return parts.length > 0 ? parts.join(" ") : "当前缺少结论门槛说明。";
}

function projectionModeLabel(mode?: string | null): string {
  if (mode === "artifact_backed") return "已绑定研究产物";
  if (mode === "migration_placeholder") return "口径切换中";
  return mode || "未提供";
}

function sanitizeDisplayText(value?: string | null): string {
  if (!value) return "未提供";
  return normalizeDisplayText(value
    .replace(/manual-review:[A-Za-z0-9:_-]+/g, "人工研究记录")
    .replace(/validation-metrics:[A-Za-z0-9:_-]+/g, "验证指标记录")
    .replace(/rolling-validation:[A-Za-z0-9:_-]+/g, "滚动验证记录")
    .replace(/replay-alignment:[A-Za-z0-9:_-]+/g, "复盘记录")
    .replace(/portfolio-backtest:[A-Za-z0-9:_-]+/g, "组合回测记录")
    .replace(/pending_rebuild/g, "口径校准中")
    .replace(/research_rebuild_pending/g, "滚动验证口径校准中")
    .replace(/forward_excess_return_(\d+)d/g, "$1日超额收益")
    .replace(/2-8 周波段/g, "当前研究周期")
    .replace(/14-56 个交易日（研究窗口待批准）/g, "观察窗口以滚动验证结论为准")
    .replace(/14-56 个交易日/g, "观察窗口以滚动验证结论为准")
    .replace(/14-56 trade days/g, "the window under rolling validation")
    .replace(/14\/28\/56/g, "多窗口对比")
    .replace(/Phase 5 baseline/g, "等权组合研究策略")
    .replace(/Phase 5 constrained TopK baseline/g, "等权组合研究策略")
    .replace(/constrained TopK baseline/g, "等权组合研究策略")
    .replace(/Phase 2 规则基线已完成 walk-forward 产物生成，但尚未进入 verified 审批。?/g, "已有滚动验证产物，当前仍在观察阶段。")
    .replace(/研究验证中（历史窗口待重建）/g, "观察窗口以滚动验证结论为准")
    .replace(/LLM 因子历史增益有限，权重上限固定为 15%/g, "人工研究信号当前仅作为辅助参考，不单独主导建议")
    .replace(/历史验证仍处于迁移重建阶段。?/g, "历史样本仍在持续补齐，当前先结合最新证据观察。")
    .replace(/运营复盘口径仍在迁移/g, "复盘结论仍在持续更新")
    .replace(/No manual research request has been created for the current recommendation context\./g, "当前建议尚未发起人工研究请求。")
    .replace(/Manual Codex\/GPT 研究助手仍是解释层附属信息，未参与任何训练、评分或晋级。/g, "人工研究当前仅作为补充解释，不参与量化评分或自动晋级。")
    .replace(/Manual research workflow/g, "人工研究流程")
    .replace(/replay artifact/g, "复盘记录")
    .replace(/portfolio artifact/g, "组合记录")
    .replace(/backtest artifact/g, "组合回测记录")
    .replace(/research contract/g, "研究口径")
    .replace(/verified 量化验证结果/g, "正式量化验证结论")
    .replace(/validation metrics/g, "验证指标")
    .replace(/未进入 verified/g, "尚未完成正式验证")
    .replace(/手动触发占位/g, "手动触发")
    .replace(/迁移期/g, "当前版本")
    .replace(/迁移占位/g, "辅助参考")
    .replace(/研究重置中/g, "持续更新中")
    .replace(/待重建/g, "待补充")
    .replace(/当前基准与超额收益已切换到观察池真实价格构造的等权对照组合，但复盘记录与组合回测仍在持续补样本和校准，暂不作为正式量化验证结论。/g, "当前基准已切换到观察池等权对照，复盘与组合回测仍在补样本，先作为观察参考。")
    .replace(/模型轨道已切换到等权组合研究策略：只在模拟盘内运行，以当前自选池建议为输入，按最多 5 只、单票上限 20%、100 股整手和允许留现金的规则生成目标仓位。/g, "模型轨道仅在模拟盘按等权规则自动调仓，不会触发真实交易。")
    .replace(/当前仅 Web 模拟盘支持自动执行。开启后，系统会按等权组合研究策略自动生成目标仓位并记录模拟成交；不会触发任何真实下单或真实交易路由。/g, "自动执行仅作用于 Web 模拟盘，不会触发真实下单。")
    .replace(/当前 contract 仅可作为 paper track \/ research candidate 治理基线，不得视为正式组合策略。/g, "当前仅用于模拟复盘，不作为正式策略。")
    .replace(/missing_news_evidence/g, "近期缺少新增事件证据，当前更多依赖价格趋势观察")
    .replace(/event_conflict_high/g, "价格与事件方向冲突较高，系统已主动下调对外表达")
    .replace(/market_data_stale/g, "最新行情刷新偏旧，短线结论需要谨慎使用")
    .replace(/用于汇总价格、事件与降级状态的融合层。?/g, "价格与事件综合后，当前先看趋势是否得到新增证据确认")
  );
}

function displayWindowLabel(value?: string | null): string {
  if (!value) return "以滚动验证结论为准";
  if (
    value.includes("2-8 周")
    || value.includes("14-56")
    || value.includes("研究窗口待批准")
    || value.includes("历史窗口待重建")
  ) {
    return "以滚动验证结论为准";
  }
  return sanitizeDisplayText(value);
}

function displayBenchmarkLabel(value?: string | null): string {
  if (!value) return "未提供";
  if (value === "phase2_equal_weight_market_proxy") return "市场等权对照篮子";
  if (value === "active_watchlist_equal_weight_proxy") return "自选池等权对照篮子";
  if (value === "csi300" || value === "CSI300") return "沪深 300";
  if (value === "pending_rebuild") return "基准口径校准中";
  return sanitizeDisplayText(value);
}

function displayLabelDefinition(value?: string | null): string {
  if (!value) return "未提供";
  if (value === "phase5-validation-policy-contract-v1") return "滚动验证口径";
  if (value === "research_rebuild_pending") return "滚动验证口径校准中";
  return sanitizeDisplayText(value);
}

function horizonLabel(value?: string | null): string {
  if (value === "research_window_pending") return "研究窗口待锁定";
  const excessMatch = value?.match(/^forward_excess_return_(\d+)d$/);
  if (excessMatch) return `${excessMatch[1]}日超额收益`;
  const returnMatch = value?.match(/^forward_return_(\d+)d$/);
  if (returnMatch) return `${returnMatch[1]}日收益`;
  return sanitizeDisplayText(value);
}

function manualReviewModelLabel(value?: string | null): string {
  if (!value) return "未指定";
  if (value === "Manual research workflow") return "人工研究流程";
  return sanitizeDisplayText(value);
}

function deploymentModeLabel(value?: string | null): string {
  if (value === "self_hosted_server") return "本机服务端部署";
  return sanitizeDisplayText(value);
}

function providerSelectionModeLabel(value?: string | null): string {
  if (value === "runtime_policy") return "按运行策略自动选源";
  return sanitizeDisplayText(value);
}

function watchlistScopeLabel(value?: string | null): string {
  if (value === "global_shared_pool" || value === "shared_watchlist") return "共享自选池";
  return sanitizeDisplayText(value);
}

function fieldMappingLabel(item: RuntimeFieldMappingView): string {
  const key = `${item.dataset}.${item.canonical_field}`;
  if (key === "quote.last_price") return "最新价";
  if (key === "quote.turnover_rate_pct") return "换手率";
  if (key === "kline.trade_time") return "K 线时间";
  if (key === "kline.adjustment") return "复权口径";
  if (key === "financial_report.report_period") return "财报报告期";
  if (key === "financial_report.revenue") return "营业收入";
  return sanitizeDisplayText(item.canonical_field);
}

function operationsValidationMessage(status?: string | null): string {
  return `研究验证 · ${validationStatusLabel(status)}`;
}

function operationsValidationDescription(view?: OperationsResearchValidationView | null): string {
  if (!view) return "当前复盘和组合指标会随最新研究结果同步刷新。";
  if (view.status === "verified") {
    return compactValidationNote(view.note, view.status, "复盘与组合验证已同步最新研究结果。");
  }
  const sampleSummary = view.replay_sample_count > 0
    ? `已纳入 ${formatNumber(view.replay_sample_count)} 条复盘样本`
    : "历史样本仍在补齐";
  const verifiedSummary = view.verified_replay_count > 0
    ? `，其中 ${formatNumber(view.verified_replay_count)} 条完成正式验证`
    : "";
  return `${sampleSummary}${verifiedSummary}；当前结论先用于观察和模拟复盘。`;
}

function launchReadinessDescription(view?: OperationsLaunchReadinessView | null): string {
  if (!view) return "上线前仍需完成必要的稳定性与验证检查。";
  if (view.status === "closed_beta_ready") {
    return "当前已满足小范围内测所需的主要检查项。";
  }
  if (view.blocking_gate_count > 0) {
    return `上线前还有 ${formatNumber(view.blocking_gate_count)} 个关键检查项待完成。`;
  }
  if (view.warning_gate_count > 0) {
    return `上线前还有 ${formatNumber(view.warning_gate_count)} 个观察项需要继续跟踪。`;
  }
  return sanitizeDisplayText(view.note ?? "上线前仍需完成必要的稳定性与验证检查。");
}

function manualReviewStatusLabel(status?: string | null): string {
  if (status === "manual_trigger_required") return "等待人工触发";
  if (status === "queued") return "已排队";
  if (status === "in_progress") return "分析中";
  if (status === "completed") return "已完成";
  if (status === "failed") return "执行失败";
  if (status === "stale") return "结果过期";
  return status || "未提供";
}

function manualResearchActionStatusMessage(request: ManualResearchRequestView): string {
  if (request.status === "completed") {
    return "人工研究已完成并生成 artifact。";
  }
  if (request.status === "stale") {
    return "人工研究结果已过期，建议发起 retry。";
  }
  if (request.status === "failed") {
    return request.failure_reason || "人工研究执行失败。";
  }
  if (request.status === "in_progress") {
    return "人工研究请求已开始执行。";
  }
  return sanitizeDisplayText(request.status_note ?? "人工研究请求已入队。");
}

function parseMultilineItems(value: string): string[] {
  return value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

function canExecuteManualResearch(request: ManualResearchRequestView): boolean {
  return ["queued", "failed"].includes(request.status);
}

function canRetryManualResearch(request: ManualResearchRequestView): boolean {
  return ["completed", "stale", "failed"].includes(request.status);
}

function canCompleteManualResearch(request: ManualResearchRequestView): boolean {
  return !request.artifact_id && ["queued", "in_progress", "failed"].includes(request.status);
}

function canFailManualResearch(request: ManualResearchRequestView): boolean {
  return !request.artifact_id && ["queued", "in_progress"].includes(request.status);
}

function validationMetricSummary(
  sampleCount?: number | null,
  rankIcMean?: number | null,
  positiveExcessRate?: number | null,
): string {
  const parts: string[] = [];
  if (sampleCount !== null && sampleCount !== undefined) {
    parts.push(`样本 ${formatNumber(sampleCount)}`);
  }
  if (rankIcMean !== null && rankIcMean !== undefined) {
    parts.push(`RankIC ${formatSignedNumber(rankIcMean)}`);
  }
  if (positiveExcessRate !== null && positiveExcessRate !== undefined) {
    parts.push(`正超额 ${formatPercent(positiveExcessRate)}`);
  }
  return parts.length > 0 ? parts.join(" · ") : "验证样本待补充";
}

function candidateValidationSummary(candidate?: CandidateItemView | null): string {
  if (!candidate) return "验证样本待补充";
  return validationMetricSummary(
    candidate.validation_sample_count,
    candidate.validation_rank_ic_mean,
    candidate.validation_positive_excess_rate,
  );
}

function publicValidationSummary(
  note?: string | null,
  status?: string | null,
  fallback = "以最新研究验证为准",
): string {
  return compactValidationNote(note, status, fallback);
}

function dataSourceStatusColor(item: RuntimeDataSourceView): string {
  if (item.runtime_ready) return "green";
  if (!item.credential_required) return "default";
  return item.credential_configured ? "green" : "gold";
}

function buildPendingDetailMessage(item: WatchlistItemView | null): string | null {
  if (!item || item.analysis_status !== "pending_real_data") {
    return null;
  }
  return item.last_error || "真实行情待刷新，当前还没有可展示的单票分析面板。";
}

function buildInitialSourceInfo(): DataSourceInfo {
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

function mergeSourceInfo(primary: DataSourceInfo | null | undefined, secondary: DataSourceInfo | null | undefined): DataSourceInfo {
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

function inferExchangeFromSymbol(symbol: string): string {
  if (symbol.endsWith(".SH")) return "SSE";
  if (symbol.endsWith(".SZ")) return "SZSE";
  return "--";
}

function buildCandidateWorkspaceRows(
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

type TrackTableRow = {
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

function buildTrackTableRows(
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

function resolveSimulationFocusSymbol(workspace: SimulationWorkspaceResponse): string | null {
  return workspace.session.focus_symbol
    ?? workspace.configuration.focus_symbol
    ?? workspace.session.watch_symbols[0]
    ?? workspace.configuration.watch_symbols[0]
    ?? null;
}

function KlineChart({ points, compact = false }: { points: PricePointView[]; compact?: boolean }) {
  const chartRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!chartRef.current || points.length === 0) {
      return;
    }

    const container = chartRef.current;
    const chart = init(container, undefined, { renderer: "canvas" });
    const styles = getComputedStyle(container);
    const textColor = styles.getPropertyValue("--text-main").trim() || "#10233c";
    const mutedColor = styles.getPropertyValue("--text-muted").trim() || "#64748b";
    const lineColor = styles.getPropertyValue("--line").trim() || "rgba(16, 35, 60, 0.08)";
    const upColor = "#d14343";
    const downColor = "#0b8f63";
    const accentColor = styles.getPropertyValue("--brand").trim() || "#0a5bff";
    const goldColor = "#d48700";
    const dates = points.map((point) => {
      const parsed = new Date(point.observed_at);
      return Number.isNaN(parsed.getTime())
        ? point.observed_at
        : parsed.toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" });
    });
    const movingAverage = (windowSize: number): Array<number | "-"> =>
      points.map((_, index) => {
        if (index < windowSize - 1) {
          return "-";
        }
        const slice = points.slice(index - windowSize + 1, index + 1);
        const total = slice.reduce((sum, point) => sum + point.close_price, 0);
        return Number((total / slice.length).toFixed(2));
      });
    const ma5 = movingAverage(5);
    const ma10 = movingAverage(10);

    chart.setOption({
      animation: false,
      backgroundColor: "transparent",
      axisPointer: {
        link: [{ xAxisIndex: "all" }],
      },
      tooltip: {
        trigger: "axis",
        confine: true,
        axisPointer: {
          type: "cross",
          label: {
            backgroundColor: "rgba(15, 35, 64, 0.9)",
          },
        },
        backgroundColor: "rgba(15, 35, 64, 0.92)",
        borderWidth: 0,
        textStyle: { color: "#f8fbff" },
        extraCssText: "border-radius: 12px; box-shadow: 0 18px 36px rgba(10,24,42,0.24);",
        formatter: (rawParams: unknown) => {
          const params = Array.isArray(rawParams)
            ? rawParams as Array<{ dataIndex?: number }>
            : [rawParams as { dataIndex?: number }];
          const index = params[0]?.dataIndex ?? 0;
          const point = points[index];
          if (!point) {
            return "";
          }
          const previous = points[index - 1];
          const changePct = previous?.close_price
            ? point.close_price / previous.close_price - 1
            : null;
          return [
            `<div style="margin-bottom:6px;font-weight:700;">${dates[index] ?? point.observed_at}</div>`,
            `开盘 ${formatNumber(point.open_price)} / 收盘 ${formatNumber(point.close_price)}`,
            `最高 ${formatNumber(point.high_price)} / 最低 ${formatNumber(point.low_price)}`,
            `成交量 ${formatNumber(point.volume)}`,
            `日变化 ${formatPercent(changePct)}`,
          ].join("<br/>");
        },
      },
      grid: compact
        ? [
            { left: 10, right: 12, top: 10, height: "66%" },
            { left: 10, right: 12, top: "79%", height: "13%" },
          ]
        : [
            { left: 14, right: 16, top: 18, height: "64%" },
            { left: 14, right: 16, top: "80%", height: "12%" },
          ],
      xAxis: [
        {
          type: "category",
          data: dates,
          boundaryGap: true,
          axisLine: { lineStyle: { color: lineColor } },
          axisTick: { show: false },
          axisLabel: { color: mutedColor, showMaxLabel: true, showMinLabel: true },
          splitLine: { show: false },
        },
        {
          type: "category",
          gridIndex: 1,
          data: dates,
          boundaryGap: true,
          axisLine: { lineStyle: { color: lineColor } },
          axisTick: { show: false },
          axisLabel: { show: false },
          splitLine: { show: false },
        },
      ],
      yAxis: [
        {
          scale: true,
          splitNumber: 4,
          axisLine: { show: false },
          axisTick: { show: false },
          axisLabel: { color: mutedColor },
          splitLine: { lineStyle: { color: lineColor } },
        },
        {
          scale: true,
          gridIndex: 1,
          splitNumber: 2,
          axisLine: { show: false },
          axisTick: { show: false },
          axisLabel: {
            color: mutedColor,
            formatter: (value: number) => `${Math.round(value / 10000)}万`,
          },
          splitLine: { show: false },
        },
      ],
      dataZoom: [
        {
          type: "inside",
          xAxisIndex: [0, 1],
          start: points.length > 24 ? Math.max(0, 100 - (24 / points.length) * 100) : 0,
          end: 100,
        },
        ...(
          compact
            ? []
            : [{
                type: "slider",
                xAxisIndex: [0, 1],
                bottom: 8,
                height: 20,
                borderColor: "transparent",
                backgroundColor: "rgba(16, 35, 60, 0.06)",
                fillerColor: "rgba(10, 91, 255, 0.14)",
                dataBackground: {
                  lineStyle: { color: mutedColor, opacity: 0.45 },
                  areaStyle: { color: "rgba(10, 91, 255, 0.04)" },
                },
                handleStyle: {
                  color: accentColor,
                  borderColor: accentColor,
                },
                textStyle: { color: mutedColor },
              }]
        ),
      ],
      series: [
        {
          name: "K线",
          type: "candlestick",
          data: points.map((point) => [point.open_price, point.close_price, point.low_price, point.high_price]),
          itemStyle: {
            color: upColor,
            color0: downColor,
            borderColor: upColor,
            borderColor0: downColor,
          },
          emphasis: {
            itemStyle: {
              borderWidth: 2,
            },
          },
        },
        {
          name: "MA5",
          type: "line",
          data: ma5,
          showSymbol: false,
          smooth: true,
          lineStyle: {
            width: 1.5,
            color: accentColor,
            opacity: 0.9,
          },
        },
        {
          name: "MA10",
          type: "line",
          data: ma10,
          showSymbol: false,
          smooth: true,
          lineStyle: {
            width: 1.5,
            color: goldColor,
            opacity: 0.8,
          },
        },
        {
          name: "成交量",
          type: "bar",
          xAxisIndex: 1,
          yAxisIndex: 1,
          data: points.map((point) => ({
            value: point.volume,
            itemStyle: {
              color: point.close_price >= point.open_price ? "rgba(209, 67, 67, 0.75)" : "rgba(11, 143, 99, 0.72)",
            },
          })),
          barMaxWidth: 12,
        },
      ],
      textStyle: {
        color: textColor,
      },
    });

    const resize = () => chart.resize();
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      chart.dispose();
    };
  }, [compact, points]);

  if (points.length === 0) {
    return <Empty description="暂无价格轨迹" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  return <div ref={chartRef} className={`echarts-kline${compact ? " echarts-kline-compact" : ""}`} />;
}

function PnlStack({
  amount,
  percent,
}: {
  amount?: number | null;
  percent?: number | null;
}) {
  const tone = valueTone(amount ?? percent);
  return (
    <div className={`stacked-value stacked-value-${tone}`}>
      <strong>{formatSignedNumber(amount)}</strong>
      <span>{formatPercent(percent)}</span>
    </div>
  );
}

function KlinePanel({
  title,
  points,
  lastUpdated,
  stockName,
  isMobile = false,
}: {
  title: string;
  points: PricePointView[];
  lastUpdated?: string | null;
  stockName?: string | null;
  isMobile?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const latest = points[points.length - 1];
  const previous = points[points.length - 2];
  const changePct = latest && previous && previous.close_price
    ? latest.close_price / previous.close_price - 1
    : null;
  const periodHigh = points.length > 0 ? Math.max(...points.map((point) => point.high_price)) : null;
  const periodLow = points.length > 0 ? Math.min(...points.map((point) => point.low_price)) : null;
  const periodChange = latest && points[0]?.close_price
    ? latest.close_price / points[0].close_price - 1
    : null;
  const avgVolume = points.length > 0
    ? points.reduce((sum, point) => sum + point.volume, 0) / points.length
    : null;

  return (
    <>
      <div className="chart-shell compact-chart">
        <KlineChart points={points} compact />
      </div>
      <div className="chart-meta-row chart-meta-row-split">
        <div className="chart-meta-group">
          <span>{stockName ?? "--"}</span>
          <span>{`K 线刷新 ${formatDate(lastUpdated)}`}</span>
          {latest ? <span>{`最新 ${formatNumber(latest.close_price)}`}</span> : null}
        </div>
        <Button type="link" onClick={() => setOpen(true)}>
          弹窗查看
        </Button>
      </div>
      <Modal
        open={open}
        centered
        wrapClassName="workspace-modal workspace-modal-kline"
        width={isMobile ? "calc(100vw - 16px)" : 1280}
        footer={null}
        title={title}
        onCancel={() => setOpen(false)}
      >
        <div className="kline-modal-stack">
          <div className="kline-summary-grid">
            <div className="kline-summary-card">
              <span>最新价</span>
              <strong>{formatNumber(latest?.close_price)}</strong>
            </div>
            <div className="kline-summary-card">
              <span>日变化</span>
              <strong className={`value-${valueTone(changePct)}`}>{formatPercent(changePct)}</strong>
            </div>
            <div className="kline-summary-card">
              <span>日内区间</span>
              <strong>{latest ? `${formatNumber(latest.low_price)} - ${formatNumber(latest.high_price)}` : "--"}</strong>
            </div>
            <div className="kline-summary-card">
              <span>成交量</span>
              <strong>{formatNumber(latest?.volume)}</strong>
            </div>
            <div className="kline-summary-card">
              <span>区间涨跌</span>
              <strong className={`value-${valueTone(periodChange)}`}>{formatPercent(periodChange)}</strong>
            </div>
            <div className="kline-summary-card">
              <span>区间高低</span>
              <strong>{`${formatNumber(periodHigh)} / ${formatNumber(periodLow)}`}</strong>
            </div>
            <div className="kline-summary-card">
              <span>平均成交量</span>
              <strong>{formatNumber(avgVolume)}</strong>
            </div>
            <div className="kline-summary-card">
              <span>交互</span>
              <strong>悬浮 OHLC 与成交量</strong>
            </div>
          </div>
          <div className="chart-shell chart-shell-modal">
            <KlineChart points={points} />
          </div>
          {latest ? (
            <Descriptions size="small" column={{ xs: 1, md: 2, xl: 4 }} className="info-grid">
              <Descriptions.Item label="开盘">{formatNumber(latest.open_price)}</Descriptions.Item>
              <Descriptions.Item label="收盘">{formatNumber(latest.close_price)}</Descriptions.Item>
              <Descriptions.Item label="最高">{formatNumber(latest.high_price)}</Descriptions.Item>
              <Descriptions.Item label="最低">{formatNumber(latest.low_price)}</Descriptions.Item>
              <Descriptions.Item label="成交量">{formatNumber(latest.volume)}</Descriptions.Item>
              <Descriptions.Item label="均量">{formatNumber(avgVolume)}</Descriptions.Item>
              <Descriptions.Item label="区间涨跌">{formatPercent(periodChange)}</Descriptions.Item>
              <Descriptions.Item label="区间高低">{`${formatNumber(periodHigh)} / ${formatNumber(periodLow)}`}</Descriptions.Item>
              <Descriptions.Item label="刷新时间">{formatDate(lastUpdated)}</Descriptions.Item>
              <Descriptions.Item label="鼠标联动">价格与成交量联动十字准星</Descriptions.Item>
              <Descriptions.Item label="均线">保留现有配色并叠加 MA5 / MA10</Descriptions.Item>
              <Descriptions.Item label="交互">悬浮查看 OHLC、缩放区间、按轴联动</Descriptions.Item>
            </Descriptions>
          ) : null}
        </div>
      </Modal>
    </>
  );
}

function NavSparkline({ points }: { points: PortfolioNavPointView[] }) {
  if (points.length === 0) {
    return <Empty description="暂无净值轨迹" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  const width = 760;
  const height = 180;
  const navValues = points.map((point) => point.nav);
  const benchmarkValues = points.map((point) => point.benchmark_nav);
  const min = Math.min(...navValues, ...benchmarkValues);
  const max = Math.max(...navValues, ...benchmarkValues);
  const xStep = points.length > 1 ? width / (points.length - 1) : width;
  const scaleY = (value: number) =>
    max === min ? height / 2 : height - ((value - min) / (max - min)) * (height - 32) - 16;
  const navPath = points.map((point, index) => `${index === 0 ? "M" : "L"} ${index * xStep} ${scaleY(point.nav)}`).join(" ");
  const benchmarkPath = points
    .map((point, index) => `${index === 0 ? "M" : "L"} ${index * xStep} ${scaleY(point.benchmark_nav)}`)
    .join(" ");

  return (
    <svg className="sparkline nav-sparkline" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
      <path className="nav-benchmark-line" d={benchmarkPath} />
      <path className="nav-line" d={navPath} />
    </svg>
  );
}

function TrackHoldingsTable({
  track,
  watchSymbols,
  candidateRows,
  symbolNameMap,
  modelAdvices,
  activeSymbol,
  onViewKline,
  onOpenReport,
  onOpenOrder,
}: {
  track: SimulationTrackStateView;
  watchSymbols: string[];
  candidateRows: CandidateWorkspaceRow[];
  symbolNameMap: Map<string, string>;
  modelAdvices: SimulationModelAdviceView[];
  activeSymbol?: string | null;
  onViewKline: (symbol: string) => void;
  onOpenReport: (symbol: string) => void;
  onOpenOrder?: (symbol: string) => void;
}) {
  const isUserTrack = track.role === "manual";
  const rows = useMemo(
    () => buildTrackTableRows(track, watchSymbols, candidateRows, symbolNameMap, modelAdvices),
    [candidateRows, modelAdvices, symbolNameMap, track, watchSymbols],
  );

  return (
    <div className="track-holdings-shell">
      <Table
        className="track-holdings-table"
        size="small"
        pagination={false}
        rowKey={(record) => `${track.role}-${record.symbol}`}
        dataSource={rows}
        rowClassName={(record) => (record.symbol === activeSymbol ? "candidate-row-active" : "")}
        scroll={{ x: "max-content" }}
        onRow={(record) => ({
          onClick: () => onViewKline(record.symbol),
        })}
        columns={[
          {
            title: "标的",
            key: "stock",
            width: 168,
            render: (_, record) => (
              <div className="table-primary-cell">
                <strong>{record.name}</strong>
                <Text type="secondary">{record.symbol}</Text>
              </div>
            ),
          },
          {
            title: "持股",
            dataIndex: "quantity",
            width: 98,
            render: (value: number) => (
              <div className="stacked-value stacked-value-neutral">
                <strong>{formatNumber(value)}</strong>
                <span>股</span>
              </div>
            ),
          },
          {
            title: "现价 / 成本",
            key: "price",
            width: 118,
            render: (_, record) => (
              <div className="stacked-value stacked-value-neutral">
                <strong>{record.last_price > 0 ? formatNumber(record.last_price) : "--"}</strong>
                <span>{record.avg_cost > 0 ? formatNumber(record.avg_cost) : "--"}</span>
              </div>
            ),
          },
          {
            title: "持仓盈亏",
            key: "holdingPnl",
            width: 122,
            render: (_, record) => (
              <PnlStack amount={record.total_pnl} percent={record.holding_pnl_pct ?? 0} />
            ),
          },
          {
            title: "今日盈亏",
            key: "todayPnl",
            width: 122,
            render: (_, record) => (
              <PnlStack amount={record.today_pnl_amount} percent={record.today_pnl_pct ?? 0} />
            ),
          },
          {
            title: "仓位",
            dataIndex: "portfolio_weight",
            width: 96,
            render: (value: number) => (
              <div className="stacked-value stacked-value-neutral">
                <strong>{formatPercent(value)}</strong>
                <span>{value > 0 ? "已占用" : "未持仓"}</span>
              </div>
            ),
          },
          {
            title: "操作",
            key: "actions",
            width: isUserTrack ? 252 : 172,
            fixed: "right",
            render: (_, record) => (
              <div className="table-action-group table-action-group-tight">
                <Button
                  type="link"
                  onClick={(event: MouseEvent<HTMLElement>) => {
                    event.stopPropagation();
                    onViewKline(record.symbol);
                  }}
                >
                  查看K线
                </Button>
                <Button
                  type="link"
                  onClick={(event: MouseEvent<HTMLElement>) => {
                    event.stopPropagation();
                    onOpenReport(record.symbol);
                  }}
                >
                  分析报告
                </Button>
                {isUserTrack && onOpenOrder ? (
                  <Button
                    type="link"
                    onClick={(event: MouseEvent<HTMLElement>) => {
                      event.stopPropagation();
                      onOpenOrder(record.symbol);
                    }}
                  >
                    操作
                  </Button>
                ) : null}
              </div>
            ),
          },
        ]}
        locale={{ emptyText: "当前没有可展示的关注池标的" }}
      />
    </div>
  );
}

function SimulationTrackCard({
  track,
  watchSymbols,
  candidateRows,
  symbolNameMap,
  modelAdvices,
  activeSymbol,
  onViewKline,
  onOpenReport,
  onOpenOrder,
}: {
  track: SimulationTrackStateView;
  watchSymbols: string[];
  candidateRows: CandidateWorkspaceRow[];
  symbolNameMap: Map<string, string>;
  modelAdvices: SimulationModelAdviceView[];
  activeSymbol?: string | null;
  onViewKline: (symbol: string) => void;
  onOpenReport: (symbol: string) => void;
  onOpenOrder?: (symbol: string) => void;
}) {
  return (
    <Card
      className="panel-card simulation-track-card"
      title={track.label}
      extra={
        <Space wrap className="inline-tags">
          <Tag color="blue">{portfolioTrackLabel(track.portfolio)}</Tag>
          <Tag color={statusColor(track.portfolio.total_return >= 0 ? "pass" : "warn")}>
            {`收益 ${formatPercent(track.portfolio.total_return)}`}
          </Tag>
          <Tag color={statusColor(track.risk_exposure.max_position_weight <= 0.35 ? "pass" : "warn")}>
            {`单票 ${formatPercent(track.risk_exposure.max_position_weight)}`}
          </Tag>
        </Space>
      }
    >
      {track.latest_reason ? (
        <Alert
          className="sub-alert"
          type={track.role === "model" ? "info" : "success"}
          showIcon
          message="最近动作理由"
          description={track.latest_reason}
        />
      ) : null}
      <Descriptions size="small" column={{ xs: 1, md: 2 }} className="info-grid">
        <Descriptions.Item label="当前净值">{formatNumber(track.portfolio.net_asset_value)}</Descriptions.Item>
        <Descriptions.Item label="可用现金">{formatNumber(track.portfolio.available_cash)}</Descriptions.Item>
        <Descriptions.Item label="仓位">{formatPercent(track.risk_exposure.invested_ratio)}</Descriptions.Item>
        <Descriptions.Item label="回撤">{formatPercent(track.risk_exposure.drawdown)}</Descriptions.Item>
      </Descriptions>
      <TrackHoldingsTable
        track={track}
        watchSymbols={watchSymbols}
        candidateRows={candidateRows}
        symbolNameMap={symbolNameMap}
        modelAdvices={modelAdvices}
        activeSymbol={activeSymbol}
        onViewKline={onViewKline}
        onOpenReport={onOpenReport}
        onOpenOrder={onOpenOrder}
      />
    </Card>
  );
}

function CompactAnalysisReport({
  row,
  dashboard,
  loading,
  error,
  onOpenFullAnalysis,
}: {
  row: CandidateWorkspaceRow | null;
  dashboard: StockDashboardResponse | null;
  loading: boolean;
  error: string | null;
  onOpenFullAnalysis: () => void;
}) {
  if (loading) {
    return <Skeleton active paragraph={{ rows: 6 }} />;
  }
  if (error) {
    return (
      <Alert
        type="error"
        showIcon
        message="加载精简分析失败"
        description={sanitizeDisplayText(error)}
      />
    );
  }
  if (!row) {
    return <Empty description="未找到对应标的的分析摘要" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  const candidate = row.candidate;
  const validationMetrics = dashboard?.recommendation.historical_validation.metrics ?? {};
  const directionLabel = dashboard?.hero.direction_label ?? candidate?.display_direction_label ?? "等待分析";
  const confidenceLabel = dashboard?.recommendation.confidence_label ?? candidate?.confidence_label ?? "--";
  const claimGateStatus = dashboard?.recommendation.claim_gate.status ?? candidate?.claim_gate.status ?? "pending";
  const validationStatus = dashboard?.recommendation.validation_status ?? candidate?.validation_status ?? "pending_rebuild";
  const summary = dashboard?.recommendation.summary ?? candidate?.summary ?? buildPendingDetailMessage(row) ?? "等待服务端生成分析结果。";
  const triggerPoint = (
    dashboard?.recommendation.evidence.primary_drivers[0]
    ?? candidate?.why_now
    ?? "暂无明确触发点。"
  );
  const primaryRisk = (
    dashboard?.recommendation.risk.invalidators[0]
    ?? dashboard?.recommendation.risk.risk_flags[0]
    ?? dashboard?.recommendation.risk.coverage_gaps[0]
    ?? candidate?.primary_risk
    ?? "暂无额外风险提示。"
  );
  const changeSummary = dashboard?.change.summary ?? candidate?.change_summary ?? "暂无变化留痕。";
  const validationSummary = dashboard
    ? validationMetricSummary(
      validationMetrics.sample_count,
      validationMetrics.rank_ic_mean,
      validationMetrics.positive_excess_rate,
    )
    : candidateValidationSummary(candidate);
  const manualSummary = dashboard?.recommendation.manual_llm_review.summary ?? null;

  return (
    <div className="panel-stack">
      <Space wrap className="inline-tags">
        {candidate ? <Tag color={directionColor(candidate.display_direction)}>{directionLabel}</Tag> : null}
        <Tag>{`${confidenceLabel}置信`}</Tag>
        {candidate ? <Tag>{displayWindowLabel(candidate.window_definition)}</Tag> : null}
        {candidate ? <Tag>{horizonLabel(candidate.target_horizon_label)}</Tag> : null}
        <Tag color={claimGateAlertType(claimGateStatus)}>{claimGateStatusLabel(claimGateStatus)}</Tag>
        <Tag color={validationStatus === "verified" ? "green" : "gold"}>{validationStatusLabel(validationStatus)}</Tag>
        <Tag>{row.symbol}</Tag>
      </Space>

      <Paragraph className="panel-description">{sanitizeDisplayText(summary)}</Paragraph>

      <Descriptions size="small" column={1} className="info-grid">
        <Descriptions.Item label="当前触发点">{sanitizeDisplayText(triggerPoint)}</Descriptions.Item>
        <Descriptions.Item label="主要风险">{sanitizeDisplayText(primaryRisk)}</Descriptions.Item>
        <Descriptions.Item label="最近变化">{sanitizeDisplayText(changeSummary)}</Descriptions.Item>
        <Descriptions.Item label="验证摘要">{validationSummary}</Descriptions.Item>
        <Descriptions.Item label="最近分析">
          {formatDate(dashboard?.recommendation.generated_at ?? row.last_analyzed_at ?? row.updated_at)}
        </Descriptions.Item>
      </Descriptions>

      {manualSummary ? (
        <Alert
          className="sub-alert"
          type="info"
          showIcon
          message="人工研究摘要"
          description={sanitizeDisplayText(manualSummary)}
        />
      ) : null}

      <div className="deck-actions">
        <Button type="primary" onClick={onOpenFullAnalysis}>
          打开完整分析
        </Button>
      </div>
    </div>
  );
}

function PortfolioWorkspace({ portfolio }: { portfolio: PortfolioSummaryView }) {
  const benchmarkContext = portfolio.benchmark_context;
  const benchmarkVerified = benchmarkContext.status === "verified";
  const validationVerified = portfolio.validation_status === "verified";
  const performance = portfolio.performance;
  const executionPolicy = portfolio.execution_policy;
  const statusNote = portfolioStatusNote(portfolio);

  return (
    <div className="portfolio-workspace">
      <Space wrap className="portfolio-badges">
        <Tag color="blue">{portfolioTrackLabel(portfolio)}</Tag>
        <Tag color={statusColor(performance.total_return >= 0 ? "pass" : "warn")}>
          组合 {formatPercent(performance.total_return)}
        </Tag>
        {benchmarkVerified ? (
          <Tag color={statusColor(performance.excess_return >= 0 ? "pass" : "warn")}>
            超额 {formatPercent(performance.excess_return)}
          </Tag>
        ) : (
          <Tag color="gold">{validationStatusLabel(benchmarkContext.status)}</Tag>
        )}
        <Tag color={validationVerified ? "green" : "gold"}>
          {validationStatusLabel(portfolio.validation_status)}
        </Tag>
        <Tag color={statusColor(performance.max_drawdown > -0.12 ? "pass" : "warn")}>
          最大回撤 {formatPercent(performance.max_drawdown)}
        </Tag>
      </Space>

      <Paragraph className="panel-description">{portfolioTrackSummary(portfolio)}</Paragraph>
      {statusNote ? (
        <Alert
          className="sub-alert"
          type={validationVerified ? "info" : "warning"}
          showIcon
          message="当前说明"
          description={statusNote}
        />
      ) : null}

      <div className="chart-shell compact-chart">
        <NavSparkline points={portfolio.nav_history} />
      </div>

      <Descriptions size="small" column={{ xs: 1, md: 2, xl: 3 }} className="info-grid">
        <Descriptions.Item label="净值">{formatNumber(portfolio.net_asset_value)}</Descriptions.Item>
        <Descriptions.Item label="可用现金">{formatNumber(portfolio.available_cash)}</Descriptions.Item>
        <Descriptions.Item label="仓位">{formatPercent(portfolio.invested_ratio)}</Descriptions.Item>
        <Descriptions.Item label="基准">
          {benchmarkVerified
            ? `${benchmarkContext.benchmark_symbol ?? displayBenchmarkLabel(benchmarkContext.benchmark_label)} / ${formatPercent(performance.benchmark_return)}`
            : `${displayBenchmarkLabel(benchmarkContext.benchmark_label)} / ${validationStatusLabel(benchmarkContext.status)}`}
        </Descriptions.Item>
        <Descriptions.Item label="年化收益/超额">
          {`${formatPercent(performance.annualized_return)} / ${formatPercent(performance.annualized_excess_return)}`}
        </Descriptions.Item>
        <Descriptions.Item label="换手/胜率">
          {`${formatPercent(performance.turnover)} / ${formatPercent(performance.win_rate)}`}
        </Descriptions.Item>
        <Descriptions.Item label="已实现/未实现">{`${formatNumber(performance.realized_pnl)} / ${formatNumber(performance.unrealized_pnl)}`}</Descriptions.Item>
        <Descriptions.Item label="佣金/税费">{`${formatNumber(performance.fee_total)} / ${formatNumber(performance.tax_total)}`}</Descriptions.Item>
        <Descriptions.Item label="成本定义">{performance.cost_definition ?? "未提供"}</Descriptions.Item>
      </Descriptions>

      <Descriptions size="small" column={{ xs: 1, md: 2 }} className="info-grid">
        <Descriptions.Item label="策略状态">{validationStatusLabel(executionPolicy.status)}</Descriptions.Item>
        <Descriptions.Item label="执行策略">{executionPolicy.label}</Descriptions.Item>
        <Descriptions.Item label="基准口径">{displayBenchmarkLabel(benchmarkContext.benchmark_label)}</Descriptions.Item>
        <Descriptions.Item label="数据时间">{formatDate(benchmarkContext.as_of_time)}</Descriptions.Item>
      </Descriptions>

      {executionPolicy.constraints.length > 0 ? (
        <Card size="small" title="当前执行约束" className="sub-panel-card">
          <ul className="plain-list">
            {executionPolicy.constraints.map((item) => (
              <li key={`${portfolio.portfolio_key}-${item}`}>{item}</li>
            ))}
          </ul>
        </Card>
      ) : null}

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <Card size="small" title="当前持仓" className="sub-panel-card">
            <Table
              size="small"
              pagination={false}
              rowKey={(record) => `${portfolio.portfolio_key}-${record.symbol}`}
              dataSource={portfolio.holdings}
              columns={[
                {
                  title: "标的",
                  key: "stock",
                  render: (_, record) => (
                    <div className="table-primary-cell">
                      <strong>{record.name}</strong>
                      <Text type="secondary">{record.symbol}</Text>
                    </div>
                  ),
                },
                {
                  title: "权重",
                  dataIndex: "portfolio_weight",
                  render: (value: number) => formatPercent(value),
                },
                {
                  title: "总盈亏",
                  dataIndex: "total_pnl",
                  render: (value: number) => formatNumber(value),
                },
              ]}
              locale={{ emptyText: "暂无持仓" }}
            />
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card size="small" title="收益归因" className="sub-panel-card">
            <List
              size="small"
              dataSource={portfolio.attribution}
              renderItem={(item) => (
                <List.Item>
                  <div className="list-item-row">
                    <div>
                      <strong>{item.label}</strong>
                      <div className="muted-line">{item.detail}</div>
                    </div>
                    <Text>{formatNumber(item.amount)}</Text>
                  </div>
                </List.Item>
              )}
            />
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card size="small" title="最近订单" className="sub-panel-card">
            <List
              size="small"
              dataSource={portfolio.recent_orders}
              renderItem={(order) => (
                <List.Item>
                  <div className="order-entry">
                    <div className="list-item-row">
                      <div>
                        <strong>{order.stock_name}</strong>
                        <div className="muted-line">{`${order.symbol} · ${formatDate(order.requested_at)}`}</div>
                      </div>
                      <Tag color={order.side === "buy" ? "green" : "orange"}>{order.side}</Tag>
                    </div>
                    <div className="muted-line">{`${order.quantity} 股 · ${order.order_type} · 成交均价 ${formatNumber(order.avg_fill_price)}`}</div>
                    <Space wrap className="inline-tags">
                      {order.checks.map((check) => (
                        <Tag key={`${order.order_key}-${check.code}`} color={statusColor(check.status)}>
                          {check.title}
                        </Tag>
                      ))}
                    </Space>
                  </div>
                </List.Item>
              )}
              locale={{ emptyText: "暂无订单" }}
            />
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card size="small" title="规则与告警" className="sub-panel-card">
            <List
              size="small"
              dataSource={portfolio.rules}
              renderItem={(rule) => (
                <List.Item>
                  <div className="list-item-row">
                    <div>
                      <strong>{rule.title}</strong>
                      <div className="muted-line">{rule.detail}</div>
                    </div>
                    <Tag color={statusColor(rule.status)}>{rule.status}</Tag>
                  </div>
                </List.Item>
              )}
            />
            {portfolio.alerts.length > 0 ? (
              <Alert
                type="warning"
                showIcon
                className="sub-alert"
                message="当前告警"
                description={
                  <ul className="plain-list">
                    {portfolio.alerts.map((alert) => (
                      <li key={`${portfolio.portfolio_key}-${alert}`}>{alert}</li>
                    ))}
                  </ul>
                }
              />
            ) : (
              <Alert type="success" showIcon className="sub-alert" message="当前没有额外仓位或回撤告警。" />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
}

function App({ themeMode, onToggleTheme }: { themeMode: ThemeMode; onToggleTheme: () => void }) {
  const initialRuntimeConfig = api.getRuntimeConfig();
  const screens = Grid.useBreakpoint();
  const isMobile = !screens.md;
  const [messageApi, messageContextHolder] = message.useMessage();
  const [view, setView] = useState<ViewMode>("candidates");
  const [runtimeConfig, setRuntimeConfig] = useState<DashboardRuntimeConfig>(initialRuntimeConfig);
  const [sourceInfo, setSourceInfo] = useState<DataSourceInfo>(() => buildInitialSourceInfo());
  const [runtimeSettings, setRuntimeSettings] = useState<RuntimeSettingsResponse | null>(null);
  const [watchlist, setWatchlist] = useState<WatchlistItemView[]>([]);
  const [candidates, setCandidates] = useState<CandidateItemView[]>([]);
  const [generatedAt, setGeneratedAt] = useState<string | null>(null);
  const [glossary, setGlossary] = useState<GlossaryEntryView[]>([]);
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [stockActiveTab, setStockActiveTab] = useState("signals");
  const [dashboard, setDashboard] = useState<StockDashboardResponse | null>(null);
  const [operations, setOperations] = useState<OperationsDashboardResponse | null>(null);
  const [simulation, setSimulation] = useState<SimulationWorkspaceResponse | null>(null);
  const [simulationConfigDraft, setSimulationConfigDraft] = useState<SimulationConfigRequest | null>(null);
  const [operationsFocusSymbol, setOperationsFocusSymbol] = useState<string | null>(null);
  const [orderModalSymbol, setOrderModalSymbol] = useState<string | null>(null);
  const [analysisReportSymbol, setAnalysisReportSymbol] = useState<string | null>(null);
  const [analysisReportDashboard, setAnalysisReportDashboard] = useState<StockDashboardResponse | null>(null);
  const [analysisReportLoading, setAnalysisReportLoading] = useState(false);
  const [analysisReportError, setAnalysisReportError] = useState<string | null>(null);
  const [manualOrderDraft, setManualOrderDraft] = useState<ManualSimulationOrderRequest>({
    symbol: "",
    side: "buy",
    quantity: 100,
    reason: "",
    limit_price: null,
  });
  const [operationsLoading, setOperationsLoading] = useState(false);
  const [operationsError, setOperationsError] = useState<string | null>(null);
  const [simulationAction, setSimulationAction] = useState<string | null>(null);
  const [questionDraft, setQuestionDraft] = useState("");
  const [analysisAnswer, setAnalysisAnswer] = useState<ManualResearchRequestView | null>(null);
  const [analysisKeyId, setAnalysisKeyId] = useState<number | undefined>(undefined);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [manualResearchAction, setManualResearchAction] = useState<string | null>(null);
  const [completeResearchTarget, setCompleteResearchTarget] = useState<ManualResearchRequestView | null>(null);
  const [completeResearchSummary, setCompleteResearchSummary] = useState("");
  const [completeResearchVerdict, setCompleteResearchVerdict] = useState("mixed");
  const [completeResearchRisks, setCompleteResearchRisks] = useState("");
  const [completeResearchDisagreements, setCompleteResearchDisagreements] = useState("");
  const [completeResearchDecisionNote, setCompleteResearchDecisionNote] = useState("");
  const [completeResearchCitations, setCompleteResearchCitations] = useState("");
  const [completeResearchAnswer, setCompleteResearchAnswer] = useState("");
  const [failResearchTarget, setFailResearchTarget] = useState<ManualResearchRequestView | null>(null);
  const [failResearchReason, setFailResearchReason] = useState("");
  const [newKeyName, setNewKeyName] = useState("");
  const [newKeyProvider, setNewKeyProvider] = useState("openai");
  const [newKeyModel, setNewKeyModel] = useState("gpt-4.1-mini");
  const [newKeyBaseUrl, setNewKeyBaseUrl] = useState("https://api.openai.com/v1");
  const [newKeySecret, setNewKeySecret] = useState("");
  const [newKeyPriority, setNewKeyPriority] = useState("100");
  const [providerDrafts, setProviderDrafts] = useState<Record<string, { accessToken: string; baseUrl: string; enabled: boolean; notes: string }>>({});
  const [watchlistSymbolDraft, setWatchlistSymbolDraft] = useState("");
  const [watchlistNameDraft, setWatchlistNameDraft] = useState("");
  const [addPopoverOpen, setAddPopoverOpen] = useState(false);
  const [pendingRemoval, setPendingRemoval] = useState<CandidateWorkspaceRow | null>(null);
  const [loadingShell, setLoadingShell] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [mutatingWatchlist, setMutatingWatchlist] = useState(false);
  const [watchlistMutationSymbol, setWatchlistMutationSymbol] = useState<string | null>(null);
  const [savingConfig, setSavingConfig] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const canMutateWatchlist = true;

  const candidateRows = useMemo(
    () => buildCandidateWorkspaceRows(watchlist, candidates),
    [watchlist, candidates],
  );

  const activeRow = useMemo(
    () => candidateRows.find((item) => item.symbol === selectedSymbol) ?? candidateRows[0] ?? null,
    [candidateRows, selectedSymbol],
  );

  const activeCandidate = activeRow?.candidate ?? null;
  const analysisReportRow = useMemo(
    () => candidateRows.find((item) => item.symbol === analysisReportSymbol) ?? null,
    [analysisReportSymbol, candidateRows],
  );
  const pendingDetailMessage = useMemo(() => buildPendingDetailMessage(activeRow), [activeRow]);
  const symbolNameMap = useMemo(
    () => new Map(candidateRows.map((item) => [item.symbol, item.name] as const)),
    [candidateRows],
  );
  const manualOrderActiveHolding = useMemo(
    () => simulation?.manual_track.portfolio.holdings.find((item) => item.symbol === manualOrderDraft.symbol) ?? null,
    [manualOrderDraft.symbol, simulation],
  );
  const activeSimulationAdvice = useMemo(
    () => simulation?.model_advices.find((item) => item.symbol === manualOrderDraft.symbol) ?? null,
    [manualOrderDraft.symbol, simulation],
  );

  const mergedGlossary = useMemo(() => {
    const entries = [...glossary, ...(dashboard?.glossary ?? [])];
    return Array.from(new Map(entries.map((item) => [item.term, item])).values());
  }, [dashboard?.glossary, glossary]);

  const modelApiKeys = runtimeSettings?.model_api_keys ?? [];
  const providerCredentials = runtimeSettings?.provider_credentials ?? [];

  const navCards: ViewCard[] = [
    {
      key: "candidates",
      label: "候选与自选",
      description: "统一查看候选标的、自选维护与快捷操作。",
      icon: <StockOutlined />,
    },
    {
      key: "stock",
      label: "单票分析",
      description: "查看价格轨迹、证据、风险和追问结果。",
      icon: <LineChartOutlined />,
    },
    {
      key: "operations",
      label: "运营复盘",
      description: "检查组合表现、规则审计和命中复盘。",
      icon: <BarChartOutlined />,
    },
    {
      key: "settings",
      label: "设置",
      description: "集中查看说明、模型和数据源配置。",
      icon: <SettingOutlined />,
    },
  ];

  async function loadRuntimeSettings(): Promise<void> {
    const payload = await api.getRuntimeSettings();
    setRuntimeSettings(payload);
    setAnalysisKeyId((current) => {
      if (current && payload.model_api_keys.some((item) => item.id === current)) {
        return current;
      }
      return payload.default_model_api_key_id ?? payload.model_api_keys[0]?.id;
    });
    setProviderDrafts((current) => {
      const next: Record<string, { accessToken: string; baseUrl: string; enabled: boolean; notes: string }> = { ...current };
      payload.provider_credentials.forEach((credential) => {
        if (!next[credential.provider_name]) {
          next[credential.provider_name] = {
            accessToken: "",
            baseUrl: credential.base_url ?? "",
            enabled: credential.enabled,
            notes: credential.notes ?? "",
          };
        }
      });
      payload.data_sources.forEach((source) => {
        if (!next[source.provider_name]) {
          next[source.provider_name] = {
            accessToken: "",
            baseUrl: source.base_url ?? "",
            enabled: source.enabled,
            notes: "",
          };
        }
      });
      return next;
    });
  }

  function applySimulationWorkspace(workspace: SimulationWorkspaceResponse): void {
    const nextFocusSymbol = resolveSimulationFocusSymbol(workspace);
    setSimulation(workspace);
    setSimulationConfigDraft({
      initial_cash: workspace.configuration.initial_cash,
      watch_symbols: workspace.configuration.watch_symbols,
      focus_symbol: workspace.configuration.focus_symbol ?? null,
      step_interval_seconds: workspace.configuration.step_interval_seconds,
      auto_execute_model: workspace.configuration.auto_execute_model,
    });
    setOperationsFocusSymbol(nextFocusSymbol);
    setManualOrderDraft((current) => ({
      ...current,
      symbol: current.symbol || nextFocusSymbol || workspace.configuration.watch_symbols[0] || "",
      reason: current.reason,
    }));
  }

  async function loadShellData(preferredSymbol?: string | null): Promise<string | null> {
    setLoadingShell(true);
    setError(null);
    try {
      const { data, source } = await api.loadShellData();
      setRuntimeConfig(api.getRuntimeConfig());
      setWatchlist(data.watchlist.items);
      setCandidates(data.candidates.items);
      setGeneratedAt(data.candidates.generated_at);
      setGlossary(data.glossary);
      setSourceInfo(source);
      const nextSymbol = data.watchlist.items.find((item) => item.symbol === preferredSymbol)?.symbol
        ?? data.watchlist.items.find((item) => item.symbol === selectedSymbol)?.symbol
        ?? data.watchlist.items[0]?.symbol
        ?? data.candidates.items.find((item) => item.symbol === preferredSymbol)?.symbol
        ?? data.candidates.items.find((item) => item.symbol === selectedSymbol)?.symbol
        ?? data.candidates.items[0]?.symbol
        ?? null;
      setSelectedSymbol(nextSymbol);
      return nextSymbol;
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "加载候选股失败。");
      return null;
    } finally {
      setLoadingShell(false);
    }
  }

  async function loadDetailData(symbol: string): Promise<void> {
    setLoadingDetail(true);
    setError(null);
    try {
      const watchlistItem = candidateRows.find((item) => item.symbol === symbol) ?? null;
      if (watchlistItem?.analysis_status === "pending_real_data") {
        setDashboard(null);
        setQuestionDraft("");
        setAnalysisAnswer(null);
        return;
      }
      const stockResult = await api.getStockDashboard(symbol);
      setDashboard(stockResult.data);
      setQuestionDraft(stockResult.data.follow_up.suggested_questions[0] ?? "");
      setAnalysisAnswer(null);
      setSourceInfo(stockResult.source);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "加载单票分析失败。");
    } finally {
      setLoadingDetail(false);
    }
  }

  async function loadOperationsData(symbol: string): Promise<void> {
    setOperationsLoading(true);
    setOperationsError(null);

    const maxRetries = 2;
    let lastError: unknown;

    for (let attempt = 0; attempt <= maxRetries; attempt += 1) {
      try {
        const operationsResult = await api.getOperationsDashboard(symbol);
        setOperations(operationsResult.data);
        setSourceInfo(operationsResult.source);

        if (operationsResult.data.simulation_workspace) {
          applySimulationWorkspace(operationsResult.data.simulation_workspace);
        } else {
          setSimulation(null);
          setOperationsError("运营复盘接口未返回双轨模拟工作区数据。");
        }
        setOperationsLoading(false);
        return;
      } catch (loadError) {
        lastError = loadError;
        const message = loadError instanceof Error ? loadError.message : "";
        const isTimeout = message.includes("请求超时");

        if (isTimeout && attempt < maxRetries) {
          continue;
        }

        setOperations(null);
        setSimulation(null);
        setOperationsError(message || "加载运营复盘工作区失败。");
        setOperationsLoading(false);
        return;
      }
    }

    setOperations(null);
    setSimulation(null);
    const fallbackMessage = lastError instanceof Error ? lastError.message : "加载运营复盘工作区失败。";
    setOperationsError(fallbackMessage);
    setOperationsLoading(false);
  }

  useEffect(() => {
    void (async () => {
      try {
        await loadRuntimeSettings();
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "加载运行时配置失败。");
      }
      await loadShellData();
    })();
  }, []);

  useEffect(() => {
    if (!selectedSymbol) {
      setDashboard(null);
      setOperations(null);
      setSimulation(null);
      setOperationsFocusSymbol(null);
      setOperationsError(null);
      return;
    }
    let cancelled = false;
    setOperations(null);
    setSimulation(null);
    setOperationsError(null);
    void (async () => {
      await loadDetailData(selectedSymbol);
      if (cancelled) {
        setLoadingDetail(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedSymbol]);

  useEffect(() => {
    if (view !== "operations" || !selectedSymbol) {
      return;
    }
    void loadOperationsData(selectedSymbol);
  }, [selectedSymbol, view]);

  useEffect(() => {
    if (!simulation) return;
    const fallbackSymbol = selectedSymbol ?? simulation.configuration.focus_symbol ?? simulation.configuration.watch_symbols[0];
    if (!fallbackSymbol) return;
    setManualOrderDraft((current) => ({
      ...current,
      symbol: current.symbol || fallbackSymbol,
    }));
  }, [selectedSymbol, simulation]);

  async function reloadEverything(preferredSymbol?: string | null): Promise<void> {
    await loadRuntimeSettings();
    const initialSymbol = await loadShellData(preferredSymbol);
    const resolvedSymbol = preferredSymbol ?? initialSymbol ?? selectedSymbol;
    if (resolvedSymbol) {
      await loadDetailData(resolvedSymbol);
      if (view === "operations") {
        await loadOperationsData(resolvedSymbol);
      }
    }
  }

  async function handleRefresh() {
    await reloadEverything();
  }

  async function runSimulationAction(
    actionKey: string,
    runner: () => Promise<{ workspace: SimulationWorkspaceResponse; message: string }>,
  ) {
    setSimulationAction(actionKey);
    setError(null);
    try {
      const response = await runner();
      applySimulationWorkspace(response.workspace);
      setOperationsError(null);
      if (selectedSymbol) {
        try {
          const operationsResult = await api.getOperationsDashboard(selectedSymbol);
          setOperations(operationsResult.data);
          setSourceInfo((current) => mergeSourceInfo(current, operationsResult.source));
        } catch (operationsLoadError) {
          setOperationsError(
            operationsLoadError instanceof Error ? operationsLoadError.message : "刷新运营复盘概览失败。",
          );
        }
      }
      messageApi.success(response.message);
    } catch (actionError) {
      const messageText = actionError instanceof Error ? actionError.message : "双轨模拟操作失败。";
      setError(messageText);
      messageApi.error(messageText);
    } finally {
      setSimulationAction(null);
    }
  }

  async function handleSaveSimulationConfig() {
    if (!simulationConfigDraft) return;
    await runSimulationAction("config", () => api.updateSimulationConfig(simulationConfigDraft));
  }

  async function handleSimulationFocusChange(symbol: string) {
    const currentConfig = simulationConfigDraft ?? (
      simulation
        ? {
            initial_cash: simulation.configuration.initial_cash,
            watch_symbols: simulation.configuration.watch_symbols,
            focus_symbol: simulation.configuration.focus_symbol ?? null,
            step_interval_seconds: simulation.configuration.step_interval_seconds,
            auto_execute_model: simulation.configuration.auto_execute_model,
          }
        : null
    );
    if (!currentConfig) return;
    if (symbol === (currentConfig.focus_symbol ?? currentConfig.watch_symbols[0] ?? null)) {
      return;
    }

    setSimulationAction("focus");
    setError(null);
    try {
      const response = await api.updateSimulationConfig({
        ...currentConfig,
        focus_symbol: symbol,
      });
      applySimulationWorkspace(response.workspace);
      setOperationsError(null);
    } catch (actionError) {
      const messageText = actionError instanceof Error ? actionError.message : "切换焦点 K 线失败。";
      setError(messageText);
      messageApi.error(messageText);
    } finally {
      setSimulationAction(null);
    }
  }

  function openManualOrderModal(symbol: string) {
    setManualOrderDraft((current) => ({
      ...current,
      symbol,
      quantity: current.symbol === symbol ? current.quantity : 100,
      reason: current.symbol === symbol ? current.reason : "",
      limit_price: current.symbol === symbol ? current.limit_price : null,
    }));
    setOrderModalSymbol(symbol);
  }

  async function openAnalysisReportModal(symbol: string) {
    setAnalysisReportSymbol(symbol);
    setAnalysisReportError(null);
    if (symbol === selectedSymbol && dashboard) {
      setAnalysisReportDashboard(dashboard);
      setAnalysisReportLoading(false);
      return;
    }
    setAnalysisReportDashboard(null);
    setAnalysisReportLoading(true);
    try {
      const stockResult = await api.getStockDashboard(symbol);
      setAnalysisReportDashboard(stockResult.data);
      setSourceInfo((current) => mergeSourceInfo(current, stockResult.source));
    } catch (loadError) {
      setAnalysisReportError(loadError instanceof Error ? loadError.message : "加载精简分析失败。");
    } finally {
      setAnalysisReportLoading(false);
    }
  }

  function closeAnalysisReportModal() {
    setAnalysisReportSymbol(null);
    setAnalysisReportDashboard(null);
    setAnalysisReportLoading(false);
    setAnalysisReportError(null);
  }

  function openFullAnalysisFromReport(symbol: string) {
    closeAnalysisReportModal();
    handleCandidateSelect(symbol, "stock");
  }

  async function handleSubmitManualOrder() {
    if (!manualOrderDraft.symbol || !manualOrderDraft.reason.trim()) {
      messageApi.warning("请先补齐下单标的和交易理由。");
      return;
    }
    await runSimulationAction("manual-order", () => api.submitManualSimulationOrder({
      ...manualOrderDraft,
      reason: manualOrderDraft.reason.trim(),
      limit_price: manualOrderDraft.limit_price ?? null,
    }));
    setManualOrderDraft((current) => ({
      ...current,
      reason: "",
      limit_price: null,
    }));
    setOrderModalSymbol(null);
  }

  function handleEndSimulation() {
    Modal.confirm({
      title: "结束当前双轨模拟？",
      content: "结束后时间线会停止推进，但当前留痕会保留用于复盘。",
      okText: "确认结束",
      cancelText: "取消",
      okButtonProps: { danger: true },
      onOk: async () => {
        await runSimulationAction("end", () => api.endSimulation({ confirm: true }));
      },
    });
  }

  async function handleAddWatchlist() {
    if (!watchlistSymbolDraft.trim()) {
      messageApi.warning("请先输入股票代码");
      return;
    }
    setMutatingWatchlist(true);
    setWatchlistMutationSymbol(watchlistSymbolDraft.trim().toUpperCase());
    setError(null);
    try {
      const response = await api.addWatchlist(watchlistSymbolDraft, watchlistNameDraft);
      setWatchlistSymbolDraft("");
      setWatchlistNameDraft("");
      setAddPopoverOpen(false);
      messageApi.success(response.message);
      await reloadEverything(response.item.symbol);
      setView("candidates");
    } catch (mutationError) {
      const messageText = mutationError instanceof Error ? mutationError.message : "加入自选池失败。";
      setError(messageText);
      messageApi.error(messageText);
    } finally {
      setMutatingWatchlist(false);
      setWatchlistMutationSymbol(null);
    }
  }

  async function handleRefreshWatchlist(symbol: string) {
    setMutatingWatchlist(true);
    setWatchlistMutationSymbol(symbol);
    setError(null);
    try {
      const response = await api.refreshWatchlist(symbol);
      messageApi.success(response.message);
      await reloadEverything(response.item.symbol);
    } catch (mutationError) {
      const messageText = mutationError instanceof Error ? mutationError.message : "重新分析失败。";
      setError(messageText);
      messageApi.error(messageText);
    } finally {
      setMutatingWatchlist(false);
      setWatchlistMutationSymbol(null);
    }
  }

  async function handleConfirmRemoveWatchlist() {
    if (!pendingRemoval) return;
    const symbol = pendingRemoval.symbol;
    setMutatingWatchlist(true);
    setWatchlistMutationSymbol(symbol);
    setError(null);
    try {
      const response = await api.removeWatchlist(symbol);
      messageApi.success(`已移除 ${response.symbol}，当前剩余 ${response.active_count} 只自选股`);
      const nextSymbol = selectedSymbol === symbol
        ? candidateRows.find((item) => item.symbol !== symbol)?.symbol ?? null
        : selectedSymbol;
      setPendingRemoval(null);
      await reloadEverything(nextSymbol);
    } catch (mutationError) {
      const messageText = mutationError instanceof Error ? mutationError.message : "移除自选股失败。";
      setError(messageText);
      messageApi.error(messageText);
    } finally {
      setMutatingWatchlist(false);
      setWatchlistMutationSymbol(null);
    }
  }

  async function handleCreateModelApiKey() {
    if (!newKeyName.trim() || !newKeyModel.trim() || !newKeyBaseUrl.trim() || !newKeySecret.trim()) {
      messageApi.warning("请完整填写模型 Key 名称、模型名、Base URL 和 Key。");
      return;
    }
    setSavingConfig(true);
    setError(null);
    try {
      await api.createModelApiKey({
        name: newKeyName.trim(),
        provider_name: newKeyProvider.trim(),
        model_name: newKeyModel.trim(),
        base_url: newKeyBaseUrl.trim(),
        api_key: newKeySecret.trim(),
        enabled: true,
        priority: Number.parseInt(newKeyPriority, 10) || 100,
        make_default: modelApiKeys.length === 0,
      });
      setNewKeyName("");
      setNewKeySecret("");
      setNewKeyPriority("100");
      await loadRuntimeSettings();
      messageApi.success("模型 API Key 已保存。");
    } catch (saveError) {
      const messageText = saveError instanceof Error ? saveError.message : "保存模型 API Key 失败。";
      setError(messageText);
      messageApi.error(messageText);
    } finally {
      setSavingConfig(false);
    }
  }

  async function handleToggleModelApiKey(item: ModelApiKeyView) {
    setSavingConfig(true);
    setError(null);
    try {
      await api.updateModelApiKey(item.id, { enabled: !item.enabled });
      await loadRuntimeSettings();
      messageApi.success(`${item.name} 已${item.enabled ? "停用" : "启用"}。`);
    } catch (saveError) {
      const messageText = saveError instanceof Error ? saveError.message : "更新模型 API Key 状态失败。";
      setError(messageText);
      messageApi.error(messageText);
    } finally {
      setSavingConfig(false);
    }
  }

  async function handleSetDefaultModelApiKey(item: ModelApiKeyView) {
    setSavingConfig(true);
    setError(null);
    try {
      await api.setDefaultModelApiKey(item.id);
      await loadRuntimeSettings();
      setAnalysisKeyId(item.id);
      messageApi.success(`已将 ${item.name} 设为默认分析 Key。`);
    } catch (saveError) {
      const messageText = saveError instanceof Error ? saveError.message : "设置默认 Key 失败。";
      setError(messageText);
      messageApi.error(messageText);
    } finally {
      setSavingConfig(false);
    }
  }

  async function handleDeleteModelApiKey(item: ModelApiKeyView) {
    setSavingConfig(true);
    setError(null);
    try {
      await api.deleteModelApiKey(item.id);
      await loadRuntimeSettings();
      messageApi.success(`已删除 ${item.name}。`);
    } catch (saveError) {
      const messageText = saveError instanceof Error ? saveError.message : "删除模型 API Key 失败。";
      setError(messageText);
      messageApi.error(messageText);
    } finally {
      setSavingConfig(false);
    }
  }

  async function handleSaveProviderCredential(providerName: string) {
    const draft = providerDrafts[providerName];
    if (!draft) return;
    setSavingConfig(true);
    setError(null);
    try {
      await api.upsertProviderCredential(providerName, {
        access_token: draft.accessToken.trim() || null,
        base_url: draft.baseUrl.trim() || null,
        enabled: draft.enabled,
        notes: draft.notes.trim() || null,
      });
      setProviderDrafts((current) => ({
        ...current,
        [providerName]: {
          ...current[providerName],
          accessToken: "",
        },
      }));
      await loadRuntimeSettings();
      messageApi.success(`${providerName.toUpperCase()} 凭据已更新。`);
    } catch (saveError) {
      const messageText = saveError instanceof Error ? saveError.message : "保存数据源凭据失败。";
      setError(messageText);
      messageApi.error(messageText);
    } finally {
      setSavingConfig(false);
    }
  }

  async function refreshManualResearchContext(targetSymbol: string): Promise<void> {
    if (selectedSymbol === targetSymbol) {
      await loadDetailData(targetSymbol);
    }
    if ((view === "operations" || operations) && (selectedSymbol ?? targetSymbol)) {
      await loadOperationsData(selectedSymbol ?? targetSymbol);
    }
  }

  async function handleSubmitManualResearch() {
    if (!dashboard || !selectedSymbol) return;
    const normalizedQuestion = questionDraft.trim() || "请解释当前建议最容易失效的条件。";
    setAnalysisLoading(true);
    setError(null);
    try {
      const created = await api.createManualResearchRequest({
        symbol: selectedSymbol,
        question: normalizedQuestion,
        trigger_source: "manual_research_ui",
        executor_kind: analysisKeyId ? "configured_api_key" : "builtin_gpt",
        model_api_key_id: analysisKeyId,
      });
      const result = await api.executeManualResearchRequest(created.id, {
        failover_enabled: runtimeSettings?.llm_failover_enabled ?? true,
      });
      await refreshManualResearchContext(selectedSymbol);
      setQuestionDraft(normalizedQuestion);
      setAnalysisAnswer(result);
      messageApi.success(manualResearchActionStatusMessage(result));
    } catch (analysisError) {
      const messageText = analysisError instanceof Error ? analysisError.message : "人工研究请求提交失败。";
      setError(messageText);
      messageApi.error(messageText);
    } finally {
      setAnalysisLoading(false);
    }
  }

  async function handleExecuteManualResearch(item: ManualResearchRequestView) {
    setManualResearchAction(`execute:${item.id}`);
    setError(null);
    try {
      const result = await api.executeManualResearchRequest(item.id, {
        failover_enabled: runtimeSettings?.llm_failover_enabled ?? true,
      });
      await refreshManualResearchContext(item.symbol);
      messageApi.success(manualResearchActionStatusMessage(result));
      if (item.symbol === selectedSymbol) {
        setAnalysisAnswer(result);
      }
    } catch (actionError) {
      const messageText = actionError instanceof Error ? actionError.message : "执行人工研究请求失败。";
      setError(messageText);
      messageApi.error(messageText);
    } finally {
      setManualResearchAction(null);
    }
  }

  async function handleRetryManualResearch(item: ManualResearchRequestView) {
    setManualResearchAction(`retry:${item.id}`);
    setError(null);
    try {
      const created = await api.retryManualResearchRequest(item.id, {
        requested_by: "dashboard:operator",
      });
      await refreshManualResearchContext(item.symbol);
      messageApi.success("已创建新的人工研究请求。");
      if (item.symbol === selectedSymbol) {
        setAnalysisAnswer(created);
      }
    } catch (actionError) {
      const messageText = actionError instanceof Error ? actionError.message : "重试人工研究请求失败。";
      setError(messageText);
      messageApi.error(messageText);
    } finally {
      setManualResearchAction(null);
    }
  }

  function openCompleteManualResearchModal(item: ManualResearchRequestView) {
    const review = item.manual_llm_review;
    setCompleteResearchTarget(item);
    setCompleteResearchSummary((review.summary || review.raw_answer || "").trim());
    setCompleteResearchVerdict(review.review_verdict || "mixed");
    setCompleteResearchRisks((review.risks || []).join("\n"));
    setCompleteResearchDisagreements((review.disagreements || []).join("\n"));
    setCompleteResearchDecisionNote((review.decision_note || "").trim());
    setCompleteResearchCitations((review.citations || []).join("\n"));
    setCompleteResearchAnswer((review.raw_answer || "").trim());
  }

  function closeCompleteManualResearchModal() {
    setCompleteResearchTarget(null);
    setCompleteResearchSummary("");
    setCompleteResearchVerdict("mixed");
    setCompleteResearchRisks("");
    setCompleteResearchDisagreements("");
    setCompleteResearchDecisionNote("");
    setCompleteResearchCitations("");
    setCompleteResearchAnswer("");
  }

  async function handleConfirmCompleteManualResearch() {
    if (!completeResearchTarget) return;
    const normalizedSummary = completeResearchSummary.trim();
    if (!normalizedSummary) {
      messageApi.error("请先填写研究摘要。");
      return;
    }
    setManualResearchAction(`complete:${completeResearchTarget.id}`);
    setError(null);
    try {
      const result = await api.completeManualResearchRequest(completeResearchTarget.id, {
        summary: normalizedSummary,
        review_verdict: completeResearchVerdict,
        risks: parseMultilineItems(completeResearchRisks),
        disagreements: parseMultilineItems(completeResearchDisagreements),
        decision_note: completeResearchDecisionNote.trim() || null,
        citations: parseMultilineItems(completeResearchCitations),
        answer: completeResearchAnswer.trim() || null,
      });
      await refreshManualResearchContext(completeResearchTarget.symbol);
      if (completeResearchTarget.symbol === selectedSymbol) {
        setAnalysisAnswer(result);
      }
      closeCompleteManualResearchModal();
      messageApi.success(manualResearchActionStatusMessage(result));
    } catch (actionError) {
      const messageText = actionError instanceof Error ? actionError.message : "人工完成研究请求失败。";
      setError(messageText);
      messageApi.error(messageText);
    } finally {
      setManualResearchAction(null);
    }
  }

  function openFailManualResearchModal(item: ManualResearchRequestView) {
    setFailResearchTarget(item);
    setFailResearchReason((item.failure_reason || item.status_note || "").trim());
  }

  function closeFailManualResearchModal() {
    setFailResearchTarget(null);
    setFailResearchReason("");
  }

  async function handleConfirmFailManualResearch() {
    if (!failResearchTarget) return;
    const normalizedReason = failResearchReason.trim();
    if (!normalizedReason) {
      messageApi.error("请填写失败原因。");
      return;
    }
    setManualResearchAction(`fail:${failResearchTarget.id}`);
    setError(null);
    try {
      const result = await api.failManualResearchRequest(failResearchTarget.id, {
        failure_reason: normalizedReason,
      });
      await refreshManualResearchContext(failResearchTarget.symbol);
      if (failResearchTarget.symbol === selectedSymbol) {
        setAnalysisAnswer(result);
      }
      closeFailManualResearchModal();
      messageApi.success(manualResearchActionStatusMessage(result));
    } catch (actionError) {
      const messageText = actionError instanceof Error ? actionError.message : "标记人工研究失败时出错。";
      setError(messageText);
      messageApi.error(messageText);
    } finally {
      setManualResearchAction(null);
    }
  }

  function handleCandidateSelect(symbol: string, nextView?: ViewMode) {
    startTransition(() => {
      setSelectedSymbol(symbol);
      if (nextView) {
        setView(nextView);
      }
    });
  }

  function openManualResearchWorkspace() {
    setView("stock");
    setStockActiveTab("followup");
  }

  async function handleCopyPrompt() {
    if (!dashboard) return;
    const prompt = dashboard.follow_up.copy_prompt.replace(
      "<在这里替换成你的追问>",
      questionDraft.trim() || "请解释当前建议最容易失效的条件。",
    );
    try {
      await navigator.clipboard.writeText(prompt);
      messageApi.success("追问包已复制到剪贴板");
    } catch {
      messageApi.error("复制失败，请检查浏览器剪贴板权限");
    }
  }

  const candidateColumns: ColumnsType<CandidateWorkspaceRow> = [
    {
      title: "序",
      key: "rank",
      width: 56,
      render: (_, record) => record.candidate?.rank ?? "--",
    },
    {
      title: "标的",
      key: "stock",
      width: 180,
      render: (_, record) => (
        <div className="table-primary-cell">
          <strong>{record.name}</strong>
          <Text type="secondary">
            {record.candidate ? `${record.symbol} · ${record.candidate.sector}` : record.symbol}
          </Text>
        </div>
      ),
    },
    {
      title: "建议",
      key: "signal",
      width: 160,
      render: (_, record) => (
        record.candidate ? (
          <Space direction="vertical" size={2}>
            <Tag color={directionColor(record.candidate.display_direction)}>{record.candidate.display_direction_label}</Tag>
            <Text type="secondary">{`${record.candidate.confidence_label}置信 · ${displayWindowLabel(record.candidate.window_definition)}`}</Text>
            <Space size={4} wrap>
              <Tag>{horizonLabel(record.candidate.target_horizon_label)}</Tag>
              <Tag color={claimGateAlertType(record.candidate.claim_gate.status)}>
                {claimGateStatusLabel(record.candidate.claim_gate.status)}
              </Tag>
              <Tag color={record.candidate.validation_status === "verified" ? "green" : "gold"}>
                {validationStatusLabel(record.candidate.validation_status)}
              </Tag>
            </Space>
            <Text type="secondary">{candidateValidationSummary(record.candidate)}</Text>
          </Space>
        ) : (
          <Text type="secondary">等待分析结果</Text>
        )
      ),
    },
    {
      title: "价格 / 20日",
      key: "price",
      width: 120,
      render: (_, record) => (
        record.candidate ? (
          <Space direction="vertical" size={2}>
            <Text strong>{formatNumber(record.candidate.last_close)}</Text>
            <Text className={`value-${valueTone(record.candidate.price_return_20d)}`}>
              {formatPercent(record.candidate.price_return_20d)}
            </Text>
          </Space>
        ) : (
          <Text type="secondary">--</Text>
        )
      ),
    },
    {
      title: "当前触发点",
      key: "trigger",
      render: (_, record) => (
        <span className="truncate-cell">
          {record.candidate?.why_now ? sanitizeDisplayText(record.candidate.why_now) : "暂无候选信号，等待服务端重新分析。"}
        </span>
      ),
    },
    {
      title: "主要风险",
      key: "risk",
      width: 220,
      render: (_, record) => (
        <span className="truncate-cell">
          {record.candidate?.primary_risk
            ? sanitizeDisplayText(record.candidate.primary_risk)
            : record.last_error
              ? sanitizeDisplayText(record.last_error)
              : "暂无额外风险提示。"}
        </span>
      ),
    },
    {
      title: "操作",
      key: "action",
      width: 200,
      fixed: "right",
      render: (_, record) => {
        const managedByWatchlist = record.source_kind !== "candidate_only";
        return (
          <div className="table-action-group">
            <Button
              type="link"
              onClick={(event) => {
                event.stopPropagation();
                handleCandidateSelect(record.symbol, "stock");
              }}
            >
              打开
            </Button>
            <Button
              type="link"
              icon={<SyncOutlined />}
              disabled={!canMutateWatchlist || !managedByWatchlist}
              loading={mutatingWatchlist && watchlistMutationSymbol === record.symbol}
              onClick={(event) => {
                event.stopPropagation();
                void handleRefreshWatchlist(record.symbol);
              }}
            >
              重分析
            </Button>
            <Button
              type="link"
              danger
              icon={<DeleteOutlined />}
              disabled={!canMutateWatchlist || !managedByWatchlist}
              onClick={(event) => {
                event.stopPropagation();
                setPendingRemoval(record);
              }}
            >
              移除
            </Button>
          </div>
        );
      },
    },
  ];

  const replayColumns: ColumnsType<RecommendationReplayView> = [
    {
      title: "标的",
      key: "stock",
      render: (_, record) => (
        <div className="table-primary-cell">
          <strong>{record.stock_name}</strong>
          <Text type="secondary">
            {`${record.symbol} · ${displayWindowLabel(record.review_window_definition)}`}
          </Text>
          <Space wrap className="inline-tags">
            {record.benchmark_definition ? <Tag>{displayBenchmarkLabel(record.benchmark_definition)}</Tag> : null}
          </Space>
        </div>
      ),
    },
    {
      title: "方向",
      dataIndex: "direction",
      render: (value: string) => <Tag color={directionColor(value)}>{directionLabels[value] ?? value}</Tag>,
    },
    {
      title: "结果",
      dataIndex: "hit_status",
      render: (value: string, record) => (
        <Tag color={record.validation_status === "verified" ? statusColor(value) : "gold"}>
          {record.validation_status === "verified" ? value : validationStatusLabel(record.validation_status)}
        </Tag>
      ),
    },
    {
      title: "标的 / 基准 / 超额",
      key: "performance",
      render: (_, record) => (
        <Space direction="vertical" size={2}>
          <Text>{`标的 ${formatPercent(record.stock_return)}`}</Text>
          <Text type="secondary">
            {record.validation_status === "verified"
              ? `基准 ${formatPercent(record.benchmark_return)} / 超额 ${formatPercent(record.excess_return)}`
              : publicValidationSummary(record.validation_note, record.validation_status, "复盘口径仍在补齐")}
          </Text>
        </Space>
      ),
    },
    {
      title: "摘要",
      dataIndex: "summary",
      render: (value: string, record) => (
        <Space direction="vertical" size={2}>
          <span className="truncate-cell">{sanitizeDisplayText(value)}</span>
          <Text type="secondary">
            {record.validation_status === "verified"
              ? sanitizeDisplayText(record.hit_definition)
              : publicValidationSummary(record.validation_note, record.validation_status, sanitizeDisplayText(record.hit_definition))}
          </Text>
          {record.validation_status !== "verified" && record.source_classification === "artifact_backed" ? (
            <Text type="secondary">复盘结果已接入研究产物，补充验证完成前仅作辅助参考。</Text>
          ) : null}
        </Space>
      ),
    },
  ];

  const stockTabItems = dashboard
    ? [
        {
          key: "signals",
          label: "因子与变化",
          children: (
            <Row gutter={[16, 16]}>
              <Col xs={24} xl={12}>
                <Card size="small" title="建议为何成立" className="sub-panel-card">
                  <div className="factor-grid">
                    {dashboard.recommendation.evidence.factor_cards.map((card) => {
                      const showScore = !(
                        (card.factor_key === "manual_review_layer" || card.factor_key === "llm_assessment") &&
                        card.status === "manual_trigger_required"
                      );
                      return (
                        <Card key={card.factor_key} size="small" className="factor-card">
                          <div className="list-item-row">
                            <strong>{factorLabels[card.factor_key] ?? card.factor_key}</strong>
                            {card.direction ? <Tag color={directionColor(card.direction)}>{directionLabels[card.direction] ?? card.direction}</Tag> : null}
                          </div>
                          {showScore && card.score !== undefined && card.score !== null ? (
                            <div className="factor-score">{`分数 ${card.score.toFixed(2)}`}</div>
                          ) : null}
                          <Paragraph className="panel-description">{sanitizeDisplayText(card.headline)}</Paragraph>
                          {card.risk_note ? <Text type="secondary">{sanitizeDisplayText(card.risk_note)}</Text> : null}
                        </Card>
                      );
                    })}
                  </div>
                </Card>
              </Col>
              <Col xs={24} xl={12}>
                <Collapse
                  className="compact-collapse"
                  defaultActiveKey={["why_change", "manual_review"]}
                  items={[
                    {
                      key: "why_change",
                      label: "为什么这次不一样",
                      children: (
                        <div>
                          <Space wrap className="inline-tags">
                            <Tag>{dashboard.change.change_badge}</Tag>
                            <Tag color={directionColor(dashboard.recommendation.claim_gate.public_direction)}>{dashboard.hero.direction_label}</Tag>
                          </Space>
                          <Paragraph className="panel-description">{sanitizeDisplayText(dashboard.change.summary)}</Paragraph>
                          <Timeline
                            items={dashboard.change.reasons.map((reason) => ({
                              color: "blue",
                              children: reason,
                            }))}
                          />
                          <Descriptions size="small" column={1}>
                            <Descriptions.Item label="上一版方向">{dashboard.change.previous_direction ?? "无"}</Descriptions.Item>
                            <Descriptions.Item label="上一版时间">{formatDate(dashboard.change.previous_generated_at)}</Descriptions.Item>
                            <Descriptions.Item label="证据状态">
                              <Tag color={dashboard.recommendation.evidence_status === "sufficient" ? "green" : "gold"}>
                                {dashboard.recommendation.evidence_status === "sufficient" ? "证据充足" : "证据降级"}
                              </Tag>
                            </Descriptions.Item>
                          </Descriptions>
                          {dashboard.recommendation.evidence.supporting_context.length > 0 ? (
                            <>
                              <Title level={5}>补充上下文</Title>
                              <ul className="plain-list">
                                {dashboard.recommendation.evidence.supporting_context.map((item) => (
                                  <li key={item}>{sanitizeDisplayText(item)}</li>
                                ))}
                              </ul>
                            </>
                          ) : null}
                          {dashboard.recommendation.evidence.conflicts.length > 0 ? (
                            <>
                              <Title level={5}>冲突信号</Title>
                              <ul className="plain-list">
                                {dashboard.recommendation.evidence.conflicts.map((item) => (
                                  <li key={item}>{sanitizeDisplayText(item)}</li>
                                ))}
                              </ul>
                            </>
                          ) : null}
                        </div>
                      ),
                    },
                    {
                      key: "when_invalid",
                      label: "何时失效",
                      children: (
                        <div>
                          <Paragraph className="panel-description">{sanitizeDisplayText(dashboard.risk_panel.headline)}</Paragraph>
                          <ul className="plain-list">
                            {dashboard.recommendation.risk.downgrade_conditions.map((item) => (
                              <li key={item}>{sanitizeDisplayText(item)}</li>
                            ))}
                          </ul>
                          <Text type="secondary">{sanitizeDisplayText(dashboard.risk_panel.disclaimer)}</Text>
                        </div>
                      ),
                    },
                    {
                      key: "historical_validation",
                      label: "历史验证层",
                      children: (
                        <div>
                          <Alert
                            className="sub-alert"
                            type={claimGateAlertType(dashboard.recommendation.claim_gate.status)}
                            showIcon
                            message={dashboard.recommendation.claim_gate.headline}
                            description={sanitizeDisplayText(claimGateDescription(dashboard.recommendation.claim_gate))}
                          />
                          <Descriptions size="small" column={1}>
                            <Descriptions.Item label="对外表达">
                              {claimGateStatusLabel(dashboard.recommendation.claim_gate.status)}
                            </Descriptions.Item>
                            <Descriptions.Item label="状态">
                              {validationStatusLabel(dashboard.recommendation.historical_validation.status)}
                            </Descriptions.Item>
                            <Descriptions.Item label="标签定义">
                              {displayLabelDefinition(dashboard.recommendation.historical_validation.label_definition)}
                            </Descriptions.Item>
                            <Descriptions.Item label="基准定义">
                              {displayBenchmarkLabel(dashboard.recommendation.historical_validation.benchmark_definition)}
                            </Descriptions.Item>
                            <Descriptions.Item label="成本定义">
                              {sanitizeDisplayText(dashboard.recommendation.historical_validation.cost_definition)}
                            </Descriptions.Item>
                            <Descriptions.Item label="样本量">
                              {formatNumber(dashboard.recommendation.historical_validation.metrics?.sample_count)}
                            </Descriptions.Item>
                            <Descriptions.Item label="RankIC 均值">
                              {formatSignedNumber(dashboard.recommendation.historical_validation.metrics?.rank_ic_mean)}
                            </Descriptions.Item>
                            <Descriptions.Item label="正超额占比">
                              {formatPercent(dashboard.recommendation.historical_validation.metrics?.positive_excess_rate)}
                            </Descriptions.Item>
                            <Descriptions.Item label="覆盖率">
                              {formatPercent(dashboard.recommendation.historical_validation.metrics?.coverage_ratio)}
                            </Descriptions.Item>
                          </Descriptions>
                          {dashboard.recommendation.historical_validation.note ? (
                            <Alert
                              className="sub-alert"
                              type="warning"
                              showIcon
                              message="验证说明"
                              description={sanitizeDisplayText(dashboard.recommendation.historical_validation.note)}
                            />
                          ) : null}
                        </div>
                      ),
                    },
                    {
                      key: "manual_review",
                      label: "人工研究层",
                      children: (
                        <div>
                          <Space wrap className="inline-tags">
                            <Tag color={statusColor(dashboard.recommendation.manual_llm_review.status)}>
                              {manualReviewStatusLabel(dashboard.recommendation.manual_llm_review.status)}
                            </Tag>
                            {dashboard.recommendation.manual_llm_review.review_verdict ? (
                              <Tag color="blue">{sanitizeDisplayText(dashboard.recommendation.manual_llm_review.review_verdict)}</Tag>
                            ) : null}
                          </Space>
                          <Descriptions size="small" column={{ xs: 1, md: 2 }}>
                            <Descriptions.Item label="研究状态">
                              {manualReviewStatusLabel(dashboard.recommendation.manual_llm_review.status)}
                            </Descriptions.Item>
                            <Descriptions.Item label="产物时间">
                              {formatDate(dashboard.recommendation.manual_llm_review.generated_at)}
                            </Descriptions.Item>
                            <Descriptions.Item label="请求时间">
                              {formatDate(dashboard.recommendation.manual_llm_review.requested_at)}
                            </Descriptions.Item>
                            <Descriptions.Item label="模型标签">
                              {dashboard.recommendation.manual_llm_review.model_label
                                ? manualReviewModelLabel(dashboard.recommendation.manual_llm_review.model_label)
                                : "未指定"}
                            </Descriptions.Item>
                            <Descriptions.Item label="研究结论">
                              {dashboard.recommendation.manual_llm_review.review_verdict
                                ? sanitizeDisplayText(dashboard.recommendation.manual_llm_review.review_verdict)
                                : "未给出"}
                            </Descriptions.Item>
                            <Descriptions.Item label="研究问题">
                              {dashboard.recommendation.manual_llm_review.question
                                ? sanitizeDisplayText(dashboard.recommendation.manual_llm_review.question)
                                : "未提供"}
                            </Descriptions.Item>
                          </Descriptions>
                          {dashboard.recommendation.manual_llm_review.status_note ? (
                            <Alert
                              className="sub-alert"
                              type="info"
                              showIcon
                              message="状态说明"
                              description={sanitizeDisplayText(dashboard.recommendation.manual_llm_review.status_note)}
                            />
                          ) : null}
                          {dashboard.recommendation.manual_llm_review.stale_reason ? (
                            <Alert
                              className="sub-alert"
                              type="warning"
                              showIcon
                              message="结果过期"
                              description={sanitizeDisplayText(dashboard.recommendation.manual_llm_review.stale_reason)}
                            />
                          ) : null}
                          <Paragraph className="panel-description">
                            {dashboard.recommendation.manual_llm_review.summary
                              ? sanitizeDisplayText(dashboard.recommendation.manual_llm_review.summary)
                              : "当前没有额外的人工研究摘要。"}
                          </Paragraph>
                          <div className="manual-research-entry-actions">
                            <Button type="primary" size="small" onClick={openManualResearchWorkspace}>
                              发起人工研究
                            </Button>
                            <Button size="small" onClick={handleCopyPrompt}>
                              复制追问包
                            </Button>
                            <Text type="secondary">
                              入口在下方"追问与模拟"标签。留空不选模型 Key 时会直接调用本机 Codex，用 `gpt-5.5` 执行 builtin 研究；选择已配置 Key 时则走对应的外部模型 Key。
                            </Text>
                          </div>
                          {dashboard.recommendation.manual_llm_review.decision_note ? (
                            <Paragraph className="panel-description">
                              {sanitizeDisplayText(dashboard.recommendation.manual_llm_review.decision_note)}
                            </Paragraph>
                          ) : null}
                          {dashboard.recommendation.manual_llm_review.risks.length > 0 ? (
                            <>
                              <Title level={5}>研究层风险提示</Title>
                              <ul className="plain-list">
                                {dashboard.recommendation.manual_llm_review.risks.map((item) => (
                                  <li key={item}>{sanitizeDisplayText(item)}</li>
                                ))}
                              </ul>
                            </>
                          ) : null}
                          {dashboard.recommendation.manual_llm_review.disagreements.length > 0 ? (
                            <>
                              <Title level={5}>与量化层分歧</Title>
                              <ul className="plain-list">
                                {dashboard.recommendation.manual_llm_review.disagreements.map((item) => (
                                  <li key={item}>{sanitizeDisplayText(item)}</li>
                                ))}
                              </ul>
                            </>
                          ) : null}
                          {dashboard.recommendation.manual_llm_review.citations.length > 0 ? (
                            <>
                              <Title level={5}>引用与依据</Title>
                              <ul className="plain-list">
                                {dashboard.recommendation.manual_llm_review.citations.map((item) => (
                                  <li key={item}>{sanitizeDisplayText(item)}</li>
                                ))}
                              </ul>
                            </>
                          ) : null}
                          {dashboard.recommendation.manual_llm_review.source_packet.length > 0 ? (
                            <Alert
                              className="sub-alert"
                              type="info"
                              showIcon
                              message="研究材料"
                              description="当前建议已关联研究材料与验证记录，详情保留在内部台账中。"
                            />
                          ) : null}
                        </div>
                      ),
                    },
                  ]}
                />
              </Col>
              <Col xs={24}>
                <Card size="small" title="最近影响这条建议的事件" className="sub-panel-card">
                  <List
                    grid={{ gutter: 12, xs: 1, md: 2, xl: 3 }}
                    dataSource={dashboard.recent_news}
                    renderItem={(item) => (
                      <List.Item>
                        <Card size="small" className="news-card">
                          <Space wrap className="inline-tags">
                            <Tag color={statusColor(item.impact_direction === "positive" ? "pass" : item.impact_direction === "negative" ? "fail" : "warn")}>
                              {item.impact_direction === "positive" ? "正向" : item.impact_direction === "negative" ? "反向" : "中性"}
                            </Tag>
                            <Text type="secondary">{formatDate(item.published_at)}</Text>
                          </Space>
                          <Title level={5}>{item.headline}</Title>
                          <Paragraph className="panel-description">{item.summary}</Paragraph>
                          <Text type="secondary">{`${item.entity_scope} · ${item.source_uri}`}</Text>
                        </Card>
                      </List.Item>
                    )}
                  />
                </Card>
              </Col>
            </Row>
          ),
        },
        {
          key: "evidence",
          label: "证据与术语",
          children: (
            <Row gutter={[16, 16]}>
              <Col xs={24} xl={16}>
                <Card size="small" title="证据回溯" className="sub-panel-card">
                  <List
                    dataSource={dashboard.evidence}
                    renderItem={(item) => (
                      <List.Item>
                        <div className="evidence-entry">
                          <div className="list-item-row">
                            <div>
                              <strong>{item.label}</strong>
                              <div className="muted-line">{`${item.role} · #${item.rank} · ${formatDate(item.timestamp)}`}</div>
                            </div>
                            <Tag>{item.lineage.license_tag}</Tag>
                          </div>
                          <Paragraph className="panel-description">{item.snippet ?? "暂无摘要。"}</Paragraph>
                          <Text type="secondary">{item.lineage.source_uri}</Text>
                        </div>
                      </List.Item>
                    )}
                  />
                </Card>
              </Col>
              <Col xs={24} xl={8}>
                <Card size="small" title="术语解释" className="sub-panel-card">
                  <List
                    size="small"
                    dataSource={mergedGlossary}
                    renderItem={(item) => (
                      <List.Item>
                        <div>
                          <strong>{item.term}</strong>
                          <Paragraph className="panel-description">{item.plain_explanation}</Paragraph>
                          <Text type="secondary">{item.why_it_matters}</Text>
                        </div>
                      </List.Item>
                    )}
                  />
                </Card>
                <Card size="small" title="版本元数据" className="sub-panel-card">
                  <Descriptions size="small" column={1}>
                    <Descriptions.Item label="模型">{`${dashboard.model.name} ${dashboard.model.version}`}</Descriptions.Item>
                    <Descriptions.Item label="验证">{dashboard.model.validation_scheme}</Descriptions.Item>
                    <Descriptions.Item label="Prompt">{`${dashboard.prompt.name} ${dashboard.prompt.version}`}</Descriptions.Item>
                    <Descriptions.Item label="数据时间">{formatDate(dashboard.recommendation.as_of_data_time)}</Descriptions.Item>
                    <Descriptions.Item label="更新时间">{formatDate(dashboard.recommendation.generated_at)}</Descriptions.Item>
                  </Descriptions>
                </Card>
              </Col>
            </Row>
          ),
        },
        {
          key: "followup",
          label: "追问与模拟",
          children: (
            <Row gutter={[16, 16]}>
              <Col xs={24} xl={14}>
                <Card size="small" title="人工研究请求工作区" className="sub-panel-card">
                  <Space wrap className="question-chip-group">
                    {dashboard.follow_up.suggested_questions.map((question) => (
                      <Button key={question} size="small" onClick={() => setQuestionDraft(question)}>
                        {question}
                      </Button>
                    ))}
                  </Space>
                  <Select
                    className="full-width"
                    value={analysisKeyId}
                    allowClear
                    placeholder="可选：选择要执行的模型 Key；留空则使用本机 Codex builtin GPT"
                    options={modelApiKeys.map((item) => ({
                      value: item.id,
                      label: `${item.name} · ${item.model_name}${item.is_default ? " · 默认" : ""}`,
                    }))}
                    onChange={(value) => setAnalysisKeyId(value)}
                    onClear={() => setAnalysisKeyId(undefined)}
                  />
                  <TextArea
                    rows={5}
                    value={questionDraft}
                    onChange={(event) => setQuestionDraft(event.target.value)}
                    placeholder="输入你要提交给人工研究工作流的问题"
                  />
                  <div className="prompt-actions">
                    <Button type="primary" loading={analysisLoading} onClick={() => void handleSubmitManualResearch()}>
                      {analysisKeyId ? "提交并执行" : "使用 builtin GPT 执行"}
                    </Button>
                    <Button onClick={handleCopyPrompt}>
                      复制追问包
                    </Button>
                    <Text type="secondary">
                      这里的默认动作已经改成 durable manual research request。选择模型 Key 时会立即执行；不选时会直接调用本机 Codex 的 builtin `gpt-5.5` 执行。只有本机 Codex 不可用时，才会保留请求并提示当前环境尚未配置 builtin executor。
                    </Text>
                  </div>
                  {analysisAnswer ? (
                    <Card size="small" className="prompt-packet-card">
                      <Title level={5}>最近一次请求回执</Title>
                      <Descriptions size="small" column={1}>
                        <Descriptions.Item label="状态">
                          {manualReviewStatusLabel(analysisAnswer.status)}
                        </Descriptions.Item>
                        <Descriptions.Item label="问题">
                          {sanitizeDisplayText(analysisAnswer.question)}
                        </Descriptions.Item>
                      </Descriptions>
                      {analysisAnswer.manual_llm_review.summary ? (
                        <Paragraph className="panel-description">
                          {sanitizeDisplayText(analysisAnswer.manual_llm_review.summary)}
                        </Paragraph>
                      ) : null}
                      {analysisAnswer.manual_llm_review.raw_answer ? (
                        <Paragraph className="panel-description">
                          {sanitizeDisplayText(analysisAnswer.manual_llm_review.raw_answer)}
                        </Paragraph>
                      ) : null}
                      <Space wrap className="inline-tags">
                        {analysisAnswer.selected_key ? (
                          <Tag color="blue">{analysisAnswer.selected_key.name}</Tag>
                        ) : null}
                        {analysisAnswer.selected_key ? (
                          <Tag>{analysisAnswer.selected_key.model_name}</Tag>
                        ) : null}
                        <Tag color={statusColor(analysisAnswer.status)}>
                          {manualReviewStatusLabel(analysisAnswer.status)}
                        </Tag>
                        {analysisAnswer.failover_used ? <Tag color="orange">已故障切换</Tag> : null}
                        {analysisAnswer.artifact_id ? (
                          <Tag color="blue">已生成研究记录</Tag>
                        ) : null}
                      </Space>
                      <div className="deck-actions">
                        <Button
                          disabled={!canExecuteManualResearch(analysisAnswer)}
                          loading={manualResearchAction === `execute:${analysisAnswer.id}`}
                          onClick={() => void handleExecuteManualResearch(analysisAnswer)}
                        >
                          执行请求
                        </Button>
                        <Button
                          disabled={!canCompleteManualResearch(analysisAnswer)}
                          loading={manualResearchAction === `complete:${analysisAnswer.id}`}
                          onClick={() => openCompleteManualResearchModal(analysisAnswer)}
                        >
                          人工完成
                        </Button>
                        <Button
                          danger
                          disabled={!canFailManualResearch(analysisAnswer)}
                          loading={manualResearchAction === `fail:${analysisAnswer.id}`}
                          onClick={() => openFailManualResearchModal(analysisAnswer)}
                        >
                          标记失败
                        </Button>
                        <Button
                          disabled={!canRetryManualResearch(analysisAnswer)}
                          loading={manualResearchAction === `retry:${analysisAnswer.id}`}
                          onClick={() => void handleRetryManualResearch(analysisAnswer)}
                        >
                          Retry
                        </Button>
                      </div>
                      {analysisAnswer.status_note ? (
                        <Alert
                          className="sub-alert"
                          type="info"
                          showIcon
                          message="状态说明"
                          description={sanitizeDisplayText(analysisAnswer.status_note)}
                        />
                      ) : null}
                      {analysisAnswer.failure_reason && analysisAnswer.failure_reason !== analysisAnswer.status_note ? (
                        <Alert
                          className="sub-alert"
                          type="error"
                          showIcon
                          message="失败原因"
                          description={sanitizeDisplayText(analysisAnswer.failure_reason)}
                        />
                      ) : null}
                      {analysisAnswer.stale_reason ? (
                        <Alert
                          className="sub-alert"
                          type="warning"
                          showIcon
                          message="结果过期"
                          description={sanitizeDisplayText(analysisAnswer.stale_reason)}
                        />
                      ) : null}
                    </Card>
                  ) : null}
                  <Card size="small" className="prompt-packet-card">
                    <Title level={5}>证据包提示</Title>
                    <ul className="plain-list">
                      {dashboard.follow_up.evidence_packet.map((item) => (
                        <li key={item}>{sanitizeDisplayText(item)}</li>
                      ))}
                    </ul>
                  </Card>
                  <Card size="small" className="prompt-packet-card">
                    <Title level={5}>研究验证包</Title>
                    <Descriptions size="small" column={1}>
                      <Descriptions.Item label="验证状态">
                        {validationStatusLabel(dashboard.follow_up.research_packet.validation_status)}
                      </Descriptions.Item>
                      <Descriptions.Item label="验证样本量">
                        {formatNumber(dashboard.follow_up.research_packet.validation_sample_count)}
                      </Descriptions.Item>
                      <Descriptions.Item label="RankIC 均值">
                        {formatSignedNumber(dashboard.follow_up.research_packet.validation_rank_ic_mean)}
                      </Descriptions.Item>
                      <Descriptions.Item label="正超额占比">
                        {formatPercent(dashboard.follow_up.research_packet.validation_positive_excess_rate)}
                      </Descriptions.Item>
                      <Descriptions.Item label="人工研究">
                        {manualReviewStatusLabel(dashboard.follow_up.research_packet.manual_review_status)}
                      </Descriptions.Item>
                      <Descriptions.Item label="研究结论">
                        {dashboard.follow_up.research_packet.manual_review_review_verdict
                          ? sanitizeDisplayText(dashboard.follow_up.research_packet.manual_review_review_verdict)
                          : "未给出"}
                      </Descriptions.Item>
                      <Descriptions.Item label="人工研究时间">
                        {formatDate(dashboard.follow_up.research_packet.manual_review_generated_at)}
                      </Descriptions.Item>
                    </Descriptions>
                    {dashboard.follow_up.research_packet.manual_review_status_note ? (
                      <Alert
                        className="section-alert"
                        type="info"
                        showIcon
                        message="研究状态说明"
                        description={sanitizeDisplayText(dashboard.follow_up.research_packet.manual_review_status_note)}
                      />
                    ) : null}
                    {dashboard.follow_up.research_packet.manual_review_stale_reason ? (
                      <Alert
                        className="section-alert"
                        type="warning"
                        showIcon
                        message="研究结果过期"
                        description={sanitizeDisplayText(dashboard.follow_up.research_packet.manual_review_stale_reason)}
                      />
                    ) : null}
                    {dashboard.follow_up.research_packet.validation_note ? (
                      <Alert
                        className="section-alert"
                        type="warning"
                        showIcon
                        message="验证说明"
                        description={sanitizeDisplayText(dashboard.follow_up.research_packet.validation_note)}
                      />
                    ) : null}
                  </Card>
                </Card>
              </Col>
              <Col xs={24} xl={10}>
                <Card size="small" title="与模拟交易的衔接" className="sub-panel-card">
                  {dashboard.simulation_orders.length > 0 ? (
                    <List
                      dataSource={dashboard.simulation_orders}
                      renderItem={(order) => (
                        <List.Item>
                          <div className="order-entry">
                            <div className="list-item-row">
                              <div>
                                <strong>{order.order_source === "manual" ? "用户轨道" : "模型轨道"}</strong>
                                <div className="muted-line">{`${formatDate(order.requested_at)} · ${order.quantity} 股 · ${order.status}`}</div>
                              </div>
                              <Tag color={order.side === "buy" ? "green" : "orange"}>{order.side}</Tag>
                            </div>
                            <Text type="secondary">
                              {order.fills[0]
                                ? `首笔成交 ${formatNumber(order.fills[0].price)}，滑点 ${order.fills[0].slippage_bps.toFixed(1)} bps`
                                : "尚未成交"}
                            </Text>
                          </div>
                        </List.Item>
                      )}
                    />
                  ) : (
                    <Empty description="当前建议没有自动生成模拟订单" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                  )}
                </Card>
              </Col>
            </Row>
          ),
        },
      ]
    : [];

  const portfolioTabs = operations?.portfolios.map((portfolio) => ({
    key: portfolio.portfolio_key,
    label: portfolioTrackLabel(portfolio),
    children: <PortfolioWorkspace portfolio={portfolio} />,
  })) ?? [];
  const operationsTabItems = operations ? [
    {
      key: "execution",
      label: "模拟参数",
      children: (
        <Row gutter={[16, 16]}>
          <Col xs={24} xl={10}>
            <Card className="panel-card" title="模型轨道建议">
              <List
                dataSource={simulation?.model_advices ?? []}
                locale={{ emptyText: "当前没有新的模型动作建议" }}
                renderItem={(item) => (
                  <List.Item>
                    <div className="watchlist-entry">
                      <div className="list-item-row">
                        <div>
                          <strong>{item.stock_name}</strong>
                          <div className="muted-line">{`${item.symbol} · ${formatDate(item.generated_at)}`}</div>
                        </div>
                        <Space wrap>
                          <Tag color={directionColor(item.direction)}>{item.direction_label}</Tag>
                          <Tag>{item.confidence_label}</Tag>
                        </Space>
                      </div>
                      <Paragraph className="panel-description">{item.reason}</Paragraph>
                      {item.policy_note ? (
                        <Alert
                          type={item.policy_type === "manual_review_preview_policy_v1" ? "warning" : "info"}
                          showIcon
                          message={simulationAdvicePolicyLabel(item)}
                          description={sanitizeDisplayText(item.policy_note)}
                        />
                      ) : null}
                      <div className="watchlist-meta">
                        <Text type="secondary">
                          {item.policy_type === "manual_review_preview_policy_v1"
                            ? `人工复核预览 ${simulationAdviceActionLabel(item)} · 参考价 ${formatNumber(item.reference_price)}`
                            : `${simulationAdviceActionLabel(item)} · 参考价 ${formatNumber(item.reference_price)}${item.quantity ? ` · 数量 ${formatNumber(item.quantity)}` : ""}${item.target_weight !== null && item.target_weight !== undefined ? ` · 目标仓位 ${formatPercent(item.target_weight)}` : ""}`}
                        </Text>
                      </div>
                      <Space wrap className="inline-tags">
                        {item.risk_flags.map((risk) => (
                          <Tag key={`${item.symbol}-${risk}`}>{risk}</Tag>
                        ))}
                      </Space>
                    </div>
                  </List.Item>
                )}
              />
            </Card>
          </Col>
          <Col xs={24} xl={14}>
            <Card className="panel-card" title="模拟参数">
              <Form layout="vertical">
                <Row gutter={[16, 0]}>
                  <Col xs={24} md={12}>
                    <Form.Item label="初始资金">
                      <InputNumber
                        className="full-width"
                        min={1000}
                        step={10000}
                        value={simulationConfigDraft?.initial_cash}
                        onChange={(value) =>
                          setSimulationConfigDraft((current) => (
                            current
                              ? { ...current, initial_cash: Number(value ?? current.initial_cash) }
                              : current
                          ))
                        }
                      />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={12}>
                    <Form.Item label="刷新步长（秒）">
                      <InputNumber
                        className="full-width"
                        min={60}
                        max={86400}
                        step={60}
                        value={simulationConfigDraft?.step_interval_seconds}
                        onChange={(value) =>
                          setSimulationConfigDraft((current) => (
                            current
                              ? { ...current, step_interval_seconds: Number(value ?? current.step_interval_seconds) }
                              : current
                          ))
                        }
                      />
                    </Form.Item>
                  </Col>
                </Row>
                <Form.Item label="关注股票池">
                  <Select
                    mode="multiple"
                    value={simulationConfigDraft?.watch_symbols ?? []}
                    options={candidateRows.map((item) => ({
                      value: item.symbol,
                      label: `${item.name} · ${item.symbol}`,
                    }))}
                    onChange={(value) =>
                      setSimulationConfigDraft((current) => (
                        current
                          ? { ...current, watch_symbols: value }
                          : current
                      ))
                    }
                  />
                </Form.Item>
                <Row gutter={[16, 0]}>
                  <Col xs={24} md={12}>
                    <Form.Item label="焦点标的">
                      <Select
                        value={simulationConfigDraft?.focus_symbol ?? undefined}
                        options={(simulationConfigDraft?.watch_symbols ?? simulation?.session.watch_symbols ?? []).map((symbol) => ({
                          value: symbol,
                          label: `${symbolNameMap.get(symbol) ?? symbol} · ${symbol}`,
                        }))}
                        onChange={(value) =>
                          setSimulationConfigDraft((current) => (
                            current
                              ? { ...current, focus_symbol: value }
                              : current
                          ))
                        }
                      />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={12}>
                    <Form.Item label="模型轨道自动执行">
                      <Switch
                        checked={simulationConfigDraft?.auto_execute_model ?? false}
                        onChange={(checked) =>
                          setSimulationConfigDraft((current) => (
                            current
                              ? { ...current, auto_execute_model: checked }
                              : current
                          ))
                        }
                      />
                    </Form.Item>
                  </Col>
                </Row>
              </Form>
              {simulation?.configuration.auto_execute_note ? (
                <Alert
                  className="sub-alert"
                  type={simulation.configuration.auto_execute_model ? "success" : "info"}
                  showIcon
                  message={simulation.configuration.auto_execute_model ? "模型轨道自动执行已启用" : "模型轨道自动执行说明"}
                  description={sanitizeDisplayText(simulation.configuration.auto_execute_note)}
                />
              ) : null}
              <div className="deck-actions">
                <Button
                  type="primary"
                  loading={simulationAction === "config"}
                  onClick={() => void handleSaveSimulationConfig()}
                >
                  保存参数
                </Button>
              </div>
              <Alert
                className="sub-alert"
                type="info"
                showIcon
                message="手动下单入口已收口到用户轨道表格"
                description="点击用户轨道每一行的「操作」，会打开居中的大弹窗，保留当前持仓、参考价和模型建议作为下单上下文。"
              />
            </Card>
          </Col>
        </Row>
      ),
    },
    {
      key: "analysis",
      label: "差异复盘",
      children: (
        <div className="panel-stack">
          <Row gutter={[16, 16]}>
            <Col xs={24} xl={14}>
              <Card className="panel-card" title="双轨核心差异">
                <Table
                  rowKey="label"
                  size="small"
                  pagination={false}
                  dataSource={simulation?.comparison_metrics ?? []}
                  columns={[
                    { title: "指标", dataIndex: "label" },
                    {
                      title: "用户轨道",
                      dataIndex: "manual_value",
                      render: (value: number, record) => (record.unit === "pct" ? formatPercent(value) : formatNumber(value)),
                    },
                    {
                      title: "模型轨道",
                      dataIndex: "model_value",
                      render: (value: number, record) => (record.unit === "pct" ? formatPercent(value) : formatNumber(value)),
                    },
                    {
                      title: "差值",
                      dataIndex: "difference",
                      render: (value: number, record) => (record.unit === "pct" ? formatPercent(value) : formatNumber(value)),
                    },
                    {
                      title: "领先方",
                      dataIndex: "leader",
                      render: (value: string) => (
                        <Tag color={value === "manual" ? "green" : value === "model" ? "blue" : "default"}>
                          {value === "manual" ? "用户" : value === "model" ? "模型" : "持平"}
                        </Tag>
                      ),
                    },
                  ]}
                />
              </Card>
            </Col>
            <Col xs={24} xl={10}>
              <Card className="panel-card" title="时点决策差异">
                <List
                  dataSource={simulation?.decision_differences ?? []}
                  locale={{ emptyText: "还没有产生足够的双轨差异记录" }}
                  renderItem={(item) => (
                    <List.Item>
                      <div className="watchlist-entry">
                        <div className="list-item-row">
                          <div>
                            <strong>{`第 ${item.step_index} 步 · ${item.symbol ?? "未指定标的"}`}</strong>
                            <div className="muted-line">{formatDate(item.happened_at)}</div>
                          </div>
                        </div>
                        <Descriptions size="small" column={1}>
                          <Descriptions.Item label="用户动作">{`${item.manual_action} · ${item.manual_reason}`}</Descriptions.Item>
                          <Descriptions.Item label="模型动作">{`${item.model_action} · ${item.model_reason}`}</Descriptions.Item>
                        </Descriptions>
                        <Paragraph className="panel-description">{item.difference_summary}</Paragraph>
                        <Space wrap className="inline-tags">
                          {item.risk_focus.map((risk) => (
                            <Tag key={`${item.step_index}-${risk}`}>{risk}</Tag>
                          ))}
                        </Space>
                      </div>
                    </List.Item>
                  )}
                />
              </Card>
            </Col>
          </Row>
          <Card className="panel-card" title="共享时间线留痕">
            <Descriptions size="small" column={{ xs: 1, md: 2, xl: 4 }}>
              <Descriptions.Item label="启动时间">{formatDate(simulation?.session.started_at)}</Descriptions.Item>
              <Descriptions.Item label="最近恢复">{formatDate(simulation?.session.last_resumed_at)}</Descriptions.Item>
              <Descriptions.Item label="最近暂停">{formatDate(simulation?.session.paused_at)}</Descriptions.Item>
              <Descriptions.Item label="结束时间">{formatDate(simulation?.session.ended_at)}</Descriptions.Item>
            </Descriptions>
            <Timeline
              items={(simulation?.timeline ?? []).map((item) => ({
                color: statusColor(item.severity),
                children: (
                  <div className="watchlist-entry">
                    <div className="list-item-row">
                      <div>
                        <strong>{item.title}</strong>
                        <div className="muted-line">{`第 ${item.step_index} 步 · ${item.track_label} · ${formatDate(item.happened_at)}`}</div>
                      </div>
                      {item.symbol ? <Tag>{item.symbol}</Tag> : null}
                    </div>
                    <Paragraph className="panel-description">{item.detail}</Paragraph>
                    <Space wrap className="inline-tags">
                      {item.reason_tags.map((tag) => (
                        <Tag key={`${item.event_key}-${tag}`}>{tag}</Tag>
                      ))}
                    </Space>
                  </div>
                ),
              }))}
            />
          </Card>
        </div>
      ),
    },
    {
      key: "governance",
      label: "治理与验收",
      children: (
        <div className="panel-stack">
          <Row gutter={[16, 16]}>
            <Col xs={24} xl={16}>
              <Card
                className="panel-card"
                title="组合复盘与建议命中"
                extra={<Text type="secondary">{`生成时间 ${formatDate(operations.overview.generated_at)}`}</Text>}
              >
                <Descriptions size="small" column={{ xs: 1, md: 2 }}>
                  <Descriptions.Item label="用户轨道">{operations.overview.manual_portfolio_count}</Descriptions.Item>
                  <Descriptions.Item label="模型轨道">{operations.overview.auto_portfolio_count}</Descriptions.Item>
                  <Descriptions.Item label="上线状态">
                    <Tag color={statusColor(operations.overview.launch_readiness.status)}>
                      {operations.overview.launch_readiness.status}
                    </Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="研究验证">
                    {validationStatusLabel(operations.overview.research_validation.status)}
                  </Descriptions.Item>
                  <Descriptions.Item label="运行健康">
                    <Tag color={statusColor(operations.overview.run_health.status)}>
                      {operations.overview.run_health.status}
                    </Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="刷新冷却">
                    {`${operations.overview.run_health.refresh_cooldown_minutes} 分钟`}
                  </Descriptions.Item>
                </Descriptions>
                <Paragraph className="panel-description">
                  用户轨道看手动下单结果，模型轨道看模拟盘里的自动调仓结果。这里只保留结果、验证状态和门禁，不重复展开策略长说明。
                </Paragraph>
                {operations.overview.run_health.note && operations.overview.run_health.status !== "pass" ? (
                  <Alert
                    className="sub-alert"
                    type="warning"
                    showIcon
                    message="运行健康"
                    description={sanitizeDisplayText(operations.overview.run_health.note)}
                  />
                ) : null}
                {portfolioTabs.length > 0 ? (
                  <Tabs items={portfolioTabs} />
                ) : (
                  <Empty description="当前没有可展示的组合轨道" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                )}
              </Card>
            </Col>
            <Col xs={24} xl={8}>
              <Card className="panel-card" title="研究与运行摘要">
                <Descriptions size="small" column={1}>
                  <Descriptions.Item label="行情状态">
                    {sanitizeDisplayText(operations.overview.run_health.intraday_source_status)}
                  </Descriptions.Item>
                  <Descriptions.Item label="行情时间框架">
                    {sanitizeDisplayText(operations.overview.run_health.market_data_timeframe)}
                  </Descriptions.Item>
                  <Descriptions.Item label="最新行情">
                    {formatMarketFreshness(
                      operations.data_latency_seconds,
                      operations.overview.run_health.last_market_data_at,
                    )}
                  </Descriptions.Item>
                  <Descriptions.Item label="研究验证状态">
                    {validationStatusLabel(operations.overview.research_validation.status)}
                  </Descriptions.Item>
                  <Descriptions.Item label="复盘样本数">
                    {operations.overview.research_validation.replay_sample_count}
                  </Descriptions.Item>
                  <Descriptions.Item label="已验证复盘">
                    {operations.overview.research_validation.verified_replay_count}
                  </Descriptions.Item>
                  <Descriptions.Item label="组合轨道">
                    {operations.overview.manual_portfolio_count + operations.overview.auto_portfolio_count}
                  </Descriptions.Item>
                  <Descriptions.Item label="阻塞门禁">
                    {operations.overview.launch_readiness.blocking_gate_count}
                  </Descriptions.Item>
                  <Descriptions.Item label="警告门禁">
                    {operations.overview.launch_readiness.warning_gate_count}
                  </Descriptions.Item>
                </Descriptions>
              </Card>
              <Card className="panel-card" title="上线闸门">
                <List
                  dataSource={operations.launch_gates}
                  renderItem={(item) => (
                    <List.Item>
                      <div className="watchlist-entry">
                        <div className="list-item-row">
                          <strong>{item.gate}</strong>
                          <Tag color={statusColor(item.status)}>{item.status}</Tag>
                        </div>
                        <Paragraph className="panel-description">{item.threshold}</Paragraph>
                        <Text type="secondary">{`当前 ${item.current_value}`}</Text>
                      </div>
                    </List.Item>
                  )}
                />
              </Card>
            </Col>
          </Row>
          <Row gutter={[16, 16]}>
            <Col xs={24} xl={14}>
              <Card
                className="panel-card"
                title="人工研究队列"
                extra={<Text type="secondary">{`快照时间 ${formatDate(operations.manual_research_queue.generated_at)}`}</Text>}
              >
                <Space wrap className="inline-tags">
                  <Tag>{`排队 ${operations.manual_research_queue.counts.queued ?? 0}`}</Tag>
                  <Tag>{`执行中 ${operations.manual_research_queue.counts.in_progress ?? 0}`}</Tag>
                  <Tag>{`失败 ${operations.manual_research_queue.counts.failed ?? 0}`}</Tag>
                  <Tag>{`当前完成 ${operations.manual_research_queue.counts.completed_current ?? 0}`}</Tag>
                  <Tag>{`过期 ${operations.manual_research_queue.counts.completed_stale ?? 0}`}</Tag>
                </Space>
                <List
                  dataSource={operations.manual_research_queue.recent_items}
                  locale={{ emptyText: "当前关注池还没有人工研究请求" }}
                  renderItem={(item) => (
                    <List.Item
                      actions={[
                        <Button key="open" type="link" onClick={() => handleCandidateSelect(item.symbol, "stock")}>
                          打开
                        </Button>,
                        <Button
                          key="execute"
                          type="link"
                          disabled={!canExecuteManualResearch(item)}
                          loading={manualResearchAction === `execute:${item.id}`}
                          onClick={() => void handleExecuteManualResearch(item)}
                        >
                          执行
                        </Button>,
                        <Button
                          key="complete"
                          type="link"
                          disabled={!canCompleteManualResearch(item)}
                          loading={manualResearchAction === `complete:${item.id}`}
                          onClick={() => openCompleteManualResearchModal(item)}
                        >
                          完成
                        </Button>,
                        <Button
                          key="fail"
                          type="link"
                          danger
                          disabled={!canFailManualResearch(item)}
                          loading={manualResearchAction === `fail:${item.id}`}
                          onClick={() => openFailManualResearchModal(item)}
                        >
                          失败
                        </Button>,
                        <Button
                          key="retry"
                          type="link"
                          disabled={!canRetryManualResearch(item)}
                          loading={manualResearchAction === `retry:${item.id}`}
                          onClick={() => void handleRetryManualResearch(item)}
                        >
                          Retry
                        </Button>,
                      ]}
                    >
                      <div className="watchlist-entry">
                        <div className="list-item-row">
                          <div>
                            <strong>{item.symbol}</strong>
                            <div className="muted-line">{formatDate(item.requested_at)}</div>
                          </div>
                          <Tag color={statusColor(item.status)}>{manualReviewStatusLabel(item.status)}</Tag>
                        </div>
                        <Paragraph className="panel-description">{sanitizeDisplayText(item.question)}</Paragraph>
                        <Text type="secondary">
                          {item.status_note
                            ? sanitizeDisplayText(item.status_note)
                            : item.failure_reason
                              ? sanitizeDisplayText(item.failure_reason)
                              : item.stale_reason
                                ? sanitizeDisplayText(item.stale_reason)
                                : "等待处理。"}
                        </Text>
                      </div>
                    </List.Item>
                  )}
                />
              </Card>
            </Col>
            <Col xs={24} xl={10}>
              <Card
                className="panel-card"
                title="焦点标的研究工作区"
                extra={operations.manual_research_queue.focus_symbol ? <Tag>{operations.manual_research_queue.focus_symbol}</Tag> : null}
              >
                {operations.manual_research_queue.focus_request ? (
                  <>
                    <Descriptions size="small" column={1}>
                      <Descriptions.Item label="状态">
                        {manualReviewStatusLabel(operations.manual_research_queue.focus_request.status)}
                      </Descriptions.Item>
                      <Descriptions.Item label="研究问题">
                        {sanitizeDisplayText(operations.manual_research_queue.focus_request.question)}
                      </Descriptions.Item>
                      <Descriptions.Item label="研究结论">
                        {operations.manual_research_queue.focus_request.manual_llm_review.review_verdict
                          ? sanitizeDisplayText(operations.manual_research_queue.focus_request.manual_llm_review.review_verdict)
                          : "未给出"}
                      </Descriptions.Item>
                    </Descriptions>
                    {operations.manual_research_queue.focus_request.status_note ? (
                      <Alert
                        className="sub-alert"
                        type="info"
                        showIcon
                        message="状态说明"
                        description={sanitizeDisplayText(operations.manual_research_queue.focus_request.status_note)}
                      />
                    ) : null}
                    {operations.manual_research_queue.focus_request.failure_reason
                    && operations.manual_research_queue.focus_request.failure_reason !== operations.manual_research_queue.focus_request.status_note ? (
                      <Alert
                        className="sub-alert"
                        type="error"
                        showIcon
                        message="失败原因"
                        description={sanitizeDisplayText(operations.manual_research_queue.focus_request.failure_reason)}
                      />
                    ) : null}
                    {operations.manual_research_queue.focus_request.stale_reason ? (
                      <Alert
                        className="sub-alert"
                        type="warning"
                        showIcon
                        message="结果过期"
                        description={sanitizeDisplayText(operations.manual_research_queue.focus_request.stale_reason)}
                      />
                    ) : null}
                    {operations.manual_research_queue.focus_request.manual_llm_review.summary ? (
                      <Paragraph className="panel-description">
                        {sanitizeDisplayText(operations.manual_research_queue.focus_request.manual_llm_review.summary)}
                      </Paragraph>
                    ) : null}
                    {operations.manual_research_queue.focus_request.source_packet.length > 0 ? (
                      <Alert
                        className="sub-alert"
                        type="info"
                        showIcon
                        message="研究材料"
                        description="该焦点标的已关联研究材料与验证记录，详情保留在内部台账中。"
                      />
                    ) : null}
                    <div className="deck-actions">
                      <Button onClick={() => handleCandidateSelect(operations.manual_research_queue.focus_request!.symbol, "stock")}>
                        打开单票页
                      </Button>
                      <Button
                        loading={manualResearchAction === `execute:${operations.manual_research_queue.focus_request.id}`}
                        disabled={!canExecuteManualResearch(operations.manual_research_queue.focus_request)}
                        onClick={() => void handleExecuteManualResearch(operations.manual_research_queue.focus_request!)}
                      >
                        执行请求
                      </Button>
                      <Button
                        loading={manualResearchAction === `complete:${operations.manual_research_queue.focus_request.id}`}
                        disabled={!canCompleteManualResearch(operations.manual_research_queue.focus_request)}
                        onClick={() => openCompleteManualResearchModal(operations.manual_research_queue.focus_request!)}
                      >
                        人工完成
                      </Button>
                      <Button
                        danger
                        loading={manualResearchAction === `fail:${operations.manual_research_queue.focus_request.id}`}
                        disabled={!canFailManualResearch(operations.manual_research_queue.focus_request)}
                        onClick={() => openFailManualResearchModal(operations.manual_research_queue.focus_request!)}
                      >
                        标记失败
                      </Button>
                      <Button
                        loading={manualResearchAction === `retry:${operations.manual_research_queue.focus_request.id}`}
                        disabled={!canRetryManualResearch(operations.manual_research_queue.focus_request)}
                        onClick={() => void handleRetryManualResearch(operations.manual_research_queue.focus_request!)}
                      >
                        Retry
                      </Button>
                    </div>
                  </>
                ) : (
                  <Empty description="当前焦点标的还没有人工研究请求" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                )}
              </Card>
            </Col>
          </Row>
          <Row gutter={[16, 16]}>
            <Col xs={24} xl={14}>
              <Card className="panel-card" title="建议命中复盘">
                <Table
                  rowKey="recommendation_id"
                  size="small"
                  pagination={false}
                  dataSource={operations.recommendation_replay}
                  columns={replayColumns}
                />
              </Card>
            </Col>
            <Col xs={24} xl={10}>
              <Card className="panel-card" title="刷新与性能阈值">
                <Alert
                  className="sub-alert"
                  type="info"
                  showIcon
                  message="刷新策略"
                  description={`市场时区 ${operations.refresh_policy.market_timezone}，核心缓存 TTL ${operations.refresh_policy.cache_ttl_seconds} 秒。`}
                />
                <List
                  dataSource={operations.performance_thresholds}
                  renderItem={(item) => (
                    <List.Item>
                      <div className="watchlist-entry">
                        <div className="list-item-row">
                          <strong>{item.metric}</strong>
                          <Tag color={statusColor(item.status)}>{item.status}</Tag>
                        </div>
                        <Text>{`观测 ${formatNumber(item.observed)} ${item.unit} / 目标 ${formatNumber(item.target)} ${item.unit}`}</Text>
                        <Paragraph className="panel-description">{item.note}</Paragraph>
                      </div>
                    </List.Item>
                  )}
                />
              </Card>
            </Col>
          </Row>
        </div>
      ),
    },
  ] : [];

  const addWatchlistOverlay = (
    <div className="watchlist-add-popover">
      <Form layout="vertical" size="small">
        <Form.Item label="股票代码">
          <Input
            value={watchlistSymbolDraft}
            onChange={(event) => setWatchlistSymbolDraft(event.target.value)}
            placeholder="如 600519 或 300750.SZ"
          />
        </Form.Item>
        <Form.Item label="显示名称">
          <Input
            value={watchlistNameDraft}
            onChange={(event) => setWatchlistNameDraft(event.target.value)}
            placeholder="可选：自定义显示名称"
          />
        </Form.Item>
      </Form>
      <div className="watchlist-add-actions">
        <Button size="small" onClick={() => setAddPopoverOpen(false)}>
          取消
        </Button>
        <Button
          type="primary"
          size="small"
          icon={<PlusOutlined />}
          loading={mutatingWatchlist}
          onClick={() => void handleAddWatchlist()}
        >
          加入并分析
        </Button>
      </div>
    </div>
  );

  const settingsTabItems = [
    {
      key: "overview",
      label: "说明",
      children: (
        <Row gutter={[16, 16]}>
          <Col xs={24} xl={9}>
            <Card className="panel-card" title="运行方式概览">
              <Descriptions size="small" column={1}>
                <Descriptions.Item label="部署模式">
                  {deploymentModeLabel(runtimeSettings?.deployment_mode ?? "self_hosted_server")}
                </Descriptions.Item>
                <Descriptions.Item label="存储引擎">{runtimeSettings?.storage_engine ?? "SQLite"}</Descriptions.Item>
                <Descriptions.Item label="缓存后端">{runtimeSettings?.cache_backend ?? "Redis"}</Descriptions.Item>
                <Descriptions.Item label="选源策略">
                  {providerSelectionModeLabel(runtimeSettings?.provider_selection_mode ?? "runtime_policy")}
                </Descriptions.Item>
                <Descriptions.Item label="关注池范围">
                  {watchlistScopeLabel(runtimeSettings?.watchlist_scope ?? "shared_watchlist")}
                </Descriptions.Item>
                <Descriptions.Item label="LLM 故障切换">{runtimeSettings?.llm_failover_enabled ? "开启" : "关闭"}</Descriptions.Item>
              </Descriptions>
              <Paragraph className="panel-description settings-help-text">
                {sourceInfo.detail}
              </Paragraph>
              <Space wrap className="inline-tags">
                <Tag color="green">{sourceInfo.label}</Tag>
                <Tag icon={<DatabaseOutlined />}>{runtimeSettings?.storage_engine ?? "SQLite"}</Tag>
                <Tag>{runtimeSettings?.cache_backend ?? "Redis"}</Tag>
              </Space>
            </Card>
          </Col>
          <Col xs={24} xl={15}>
            <Card className="panel-card" title="缓存与运行说明">
              <List
                size="small"
                dataSource={runtimeSettings?.cache_policies ?? []}
                renderItem={(item) => (
                  <List.Item>
                    <div className="full-width">
                      <div className="list-item-row">
                        <strong>{item.label}</strong>
                        <Tag>{`${item.ttl_seconds}s`}</Tag>
                      </div>
                      <div className="muted-line">{`失败读旧值 ${item.stale_if_error_seconds}s · ${item.warm_on_watchlist ? "仅关注池预热" : "全量"}`}</div>
                    </div>
                  </List.Item>
                )}
              />
              <div className="settings-note-stack">
                {(runtimeSettings?.deployment_notes ?? []).map((note) => (
                  <Alert key={note} type="info" showIcon message={note} />
                ))}
              </div>
              <Card size="small" className="sub-panel-card">
                <Title level={5}>抗击穿策略</Title>
                <ul className="plain-list">
                  <li>{`单飞刷新：${runtimeSettings?.anti_stampede.singleflight ? "开启" : "关闭"}`}</li>
                  <li>{`失败读旧值：${runtimeSettings?.anti_stampede.serve_stale_on_error ? "开启" : "关闭"}`}</li>
                  <li>{`空结果 TTL：${runtimeSettings?.anti_stampede.empty_result_ttl_seconds ?? "--"} 秒`}</li>
                  <li>{`锁超时：${runtimeSettings?.anti_stampede.lock_timeout_seconds ?? "--"} 秒`}</li>
                </ul>
              </Card>
            </Card>
          </Col>
          <Col xs={24} xl={10}>
            <Card className="panel-card" title="数据源状态">
              <List
                size="small"
                dataSource={runtimeSettings?.data_sources ?? []}
                renderItem={(item) => (
                  <List.Item>
                    <div className="full-width">
                      <div className="list-item-row">
                        <div>
                          <strong>{item.provider_name.toUpperCase()}</strong>
                          <div className="muted-line">{item.role}</div>
                        </div>
                        <Tag color={dataSourceStatusColor(item)}>{item.status_label}</Tag>
                      </div>
                      <Paragraph className="panel-description">{item.freshness_note}</Paragraph>
                      {item.supports_intraday ? <div className="muted-line">{item.intraday_status_label ?? "盘中分钟链路未配置"}</div> : null}
                    </div>
                  </List.Item>
                )}
              />
            </Card>
          </Col>
          <Col xs={24} xl={14}>
            <Card className="panel-card" title="数据口径说明">
              <List
                size="small"
                dataSource={runtimeSettings?.field_mappings ?? []}
                renderItem={(item) => (
                  <List.Item>
                    <div>
                      <strong>{fieldMappingLabel(item)}</strong>
                      <div className="muted-line">{item.notes}</div>
                    </div>
                  </List.Item>
                )}
              />
            </Card>
          </Col>
        </Row>
      ),
    },
    {
      key: "models",
      label: "模型",
      children: (
        <Row gutter={[16, 16]}>
          <Col xs={24} xl={14}>
            <Card
              className="panel-card"
              title="模型 API Key"
              extra={<Text type="secondary">{`当前 ${modelApiKeys.length} 个`}</Text>}
            >
              <List
                dataSource={modelApiKeys}
                locale={{ emptyText: "尚未配置模型 API Key" }}
                renderItem={(item) => (
                  <List.Item>
                    <div className="watchlist-entry">
                      <div className="list-item-row">
                        <div>
                          <strong>{item.name}</strong>
                          <div className="muted-line">{`${item.provider_name} · ${item.model_name}`}</div>
                        </div>
                        <Space wrap>
                          {item.is_default ? <Tag color="blue">默认</Tag> : null}
                          <Tag color={item.enabled ? "green" : "default"}>{item.enabled ? "启用" : "停用"}</Tag>
                          <Tag>{`P${item.priority}`}</Tag>
                        </Space>
                      </div>
                      <div className="watchlist-meta">
                        <Text type="secondary">{item.base_url}</Text>
                        <Text type="secondary">{`最近状态 ${item.last_status}${item.last_error ? ` · ${item.last_error}` : ""}`}</Text>
                      </div>
                      <div className="watchlist-actions">
                        <Button type="link" disabled={item.is_default} onClick={() => void handleSetDefaultModelApiKey(item)}>
                          设为默认
                        </Button>
                        <Button type="link" onClick={() => void handleToggleModelApiKey(item)}>
                          {item.enabled ? "停用" : "启用"}
                        </Button>
                        <Button type="link" danger onClick={() => void handleDeleteModelApiKey(item)}>
                          删除
                        </Button>
                      </div>
                    </div>
                  </List.Item>
                )}
              />
            </Card>
          </Col>
          <Col xs={24} xl={10}>
            <Card className="panel-card" title="新增模型 Key">
              <Form layout="vertical">
                <Form.Item label="Key 名称" required>
                  <Input value={newKeyName} onChange={(event) => setNewKeyName(event.target.value)} placeholder="如：主 OpenAI" />
                </Form.Item>
                <Form.Item label="Provider" required>
                  <Input value={newKeyProvider} onChange={(event) => setNewKeyProvider(event.target.value)} placeholder="如：openai" />
                </Form.Item>
                <Form.Item label="模型名" required>
                  <Input value={newKeyModel} onChange={(event) => setNewKeyModel(event.target.value)} placeholder="如：gpt-4.1-mini" />
                </Form.Item>
                <Form.Item label="Base URL" required>
                  <Input value={newKeyBaseUrl} onChange={(event) => setNewKeyBaseUrl(event.target.value)} placeholder="如：https://api.openai.com/v1" />
                </Form.Item>
                <Form.Item label="API Key" required>
                  <Input.Password value={newKeySecret} onChange={(event) => setNewKeySecret(event.target.value)} placeholder="输入模型 API Key" />
                </Form.Item>
                <Form.Item label="优先级">
                  <Input value={newKeyPriority} onChange={(event) => setNewKeyPriority(event.target.value)} placeholder="数字越小优先级越高" />
                </Form.Item>
              </Form>
              <div className="deck-actions">
                <Button type="primary" loading={savingConfig} onClick={() => void handleCreateModelApiKey()}>
                  保存模型 Key
                </Button>
              </div>
            </Card>
          </Col>
        </Row>
      ),
    },
    {
      key: "providers",
      label: "数据源",
      children: (
        <Row gutter={[16, 16]}>
          {(runtimeSettings?.data_sources ?? []).map((item) => {
            const draft = providerDrafts[item.provider_name] ?? {
              accessToken: "",
              baseUrl: item.base_url ?? "",
              enabled: item.enabled,
              notes: "",
            };
            const saved = providerCredentials.find((credential) => credential.provider_name === item.provider_name);

            return (
              <Col key={item.provider_name} xs={24} xl={12}>
                <Card className="panel-card" title={item.provider_name.toUpperCase()}>
                  <div className="list-item-row">
                    <div>
                      <Tag color={dataSourceStatusColor(item)}>{item.status_label}</Tag>
                      <Paragraph className="panel-description">{item.freshness_note}</Paragraph>
                      {item.supports_intraday ? <Paragraph className="panel-description">{item.intraday_status_label ?? "盘中分钟链路未配置"}</Paragraph> : null}
                    </div>
                    <div className="settings-switch">
                      <Text type="secondary">启用</Text>
                      <Switch
                        checked={draft.enabled}
                        onChange={(checked) =>
                          setProviderDrafts((current) => ({
                            ...current,
                            [item.provider_name]: { ...draft, enabled: checked },
                          }))
                        }
                      />
                    </div>
                  </div>
                  <Form layout="vertical">
                    <Form.Item label="Base URL">
                      <Input
                        value={draft.baseUrl}
                        onChange={(event) =>
                          setProviderDrafts((current) => ({
                            ...current,
                            [item.provider_name]: { ...draft, baseUrl: event.target.value },
                          }))
                        }
                        placeholder="可选：覆盖默认 Base URL"
                      />
                    </Form.Item>
                    <Form.Item label={item.credential_required ? "Access Token" : "预留 Token"}>
                      <Input.Password
                        value={draft.accessToken}
                        onChange={(event) =>
                          setProviderDrafts((current) => ({
                            ...current,
                            [item.provider_name]: { ...draft, accessToken: event.target.value },
                          }))
                        }
                        placeholder={item.credential_required ? "输入服务端使用的 Token" : "可选：为未来代理层预留"}
                      />
                    </Form.Item>
                    <Form.Item label="备注">
                      <Input
                        value={draft.notes}
                        onChange={(event) =>
                          setProviderDrafts((current) => ({
                            ...current,
                            [item.provider_name]: { ...draft, notes: event.target.value },
                          }))
                        }
                        placeholder="记录接入说明、范围或限制"
                      />
                    </Form.Item>
                  </Form>
                  <div className="deck-actions">
                    <Button type="primary" loading={savingConfig} onClick={() => void handleSaveProviderCredential(item.provider_name)}>
                      保存数据源设置
                    </Button>
                  </div>
                  <Space wrap className="inline-tags">
                    <Tag>{saved?.masked_token ?? "未保存 Token"}</Tag>
                    <Tag>{item.docs_url}</Tag>
                  </Space>
                </Card>
              </Col>
            );
          })}
        </Row>
      ),
    },
  ];

  return (
    <>
      {messageContextHolder}
      <div className="app-theme-shell" data-theme={themeMode}>
        <div className="workspace-shell">
          <div className="workspace-hero panel-card">
            <div className="hero-header">
              <div className="hero-copy">
                <div className="topbar-kicker">A-Share Advisory Desk</div>
                <Title level={2}>自选股工作台</Title>
                <Paragraph className="topbar-note">
                  候选、自选、单票和运营复盘共用同一批关注标的，切换后工作区会同步联动。
                </Paragraph>
                <Space wrap className="header-meta">
                  <Tag color="cyan">{sourceInfo.label}</Tag>
                  <Tag icon={<DatabaseOutlined />}>{runtimeSettings?.storage_engine ?? "SQLite"}</Tag>
                  <Tag>{runtimeSettings?.cache_backend ?? "Redis"}</Tag>
                  <Tag>{runtimeConfig.apiBase || "同源 API"}</Tag>
                </Space>
              </div>

              <div className="hero-actions-panel">
                <div className="hero-refresh-note">{`最近刷新 ${formatDate(generatedAt)}`}</div>
                <div className="hero-action-row">
                  <Select
                    className="global-focus-select"
                    value={selectedSymbol ?? undefined}
                    placeholder="切换工作区标的"
                    options={candidateRows.map((item) => ({
                      value: item.symbol,
                      label: `${item.name} · ${item.symbol}`,
                    }))}
                    onChange={(value) => handleCandidateSelect(value)}
                  />
                  <Button icon={<ReloadOutlined />} onClick={() => void handleRefresh()}>
                    刷新
                  </Button>
                  <Button className="theme-toggle-button" icon={themeMode === "dark" ? <SunOutlined /> : <MoonOutlined />} onClick={onToggleTheme}>
                    {themeMode === "dark" ? "浅色模式" : "夜间模式"}
                  </Button>
                </div>
              </div>
            </div>
          </div>

          <div className="workspace-nav">
            {navCards.map((item) => (
              <button
                key={item.key}
                type="button"
                className={`workspace-nav-card${view === item.key ? " workspace-nav-card-active" : ""}`}
                onClick={() => setView(item.key)}
              >
                <div className="workspace-nav-icon">{item.icon}</div>
                <div className="workspace-nav-copy">
                  <strong>{item.label}</strong>
                  <span>{item.description}</span>
                </div>
              </button>
            ))}
          </div>

          {error ? (
            <Alert
              showIcon
              type="error"
              className="status-alert"
              message="面板加载失败"
              description={error}
            />
          ) : null}

          {loadingShell ? (
            <Card className="panel-card loading-card">
              <Skeleton active paragraph={{ rows: 6 }} />
            </Card>
          ) : null}

          {!loadingShell && view === "candidates" ? (
            <div className="panel-stack">
              <Card
                className="panel-card focus-summary-card"
                title={activeRow ? `当前焦点 · ${activeRow.name}` : "当前焦点"}
                extra={
                  activeRow ? (
                    <Space wrap>
                      <Button type="link" onClick={() => handleCandidateSelect(activeRow.symbol, "stock")}>
                        打开单票分析
                      </Button>
                      {activeRow.source_kind !== "candidate_only" ? (
                        <Button
                          type="link"
                          icon={<SyncOutlined />}
                          loading={mutatingWatchlist && watchlistMutationSymbol === activeRow.symbol}
                          onClick={() => void handleRefreshWatchlist(activeRow.symbol)}
                        >
                          重分析
                        </Button>
                      ) : null}
                    </Space>
                  ) : null
                }
              >
                {activeRow ? (
                  <>
                    <Space wrap className="inline-tags">
                      {activeCandidate ? <Tag color={directionColor(activeCandidate.display_direction)}>{activeCandidate.display_direction_label}</Tag> : null}
                      {activeCandidate ? <Tag>{`${activeCandidate.confidence_label}置信`}</Tag> : null}
                      {activeCandidate ? <Tag>{displayWindowLabel(activeCandidate.window_definition)}</Tag> : null}
                      {activeCandidate ? <Tag>{horizonLabel(activeCandidate.target_horizon_label)}</Tag> : null}
                      {activeCandidate ? (
                        <Tag color={claimGateAlertType(activeCandidate.claim_gate.status)}>
                          {claimGateStatusLabel(activeCandidate.claim_gate.status)}
                        </Tag>
                      ) : null}
                      {activeCandidate ? (
                        <Tag color={activeCandidate.validation_status === "verified" ? "green" : "gold"}>
                          {validationStatusLabel(activeCandidate.validation_status)}
                        </Tag>
                      ) : null}
                      <Tag>{activeRow.symbol}</Tag>
                      <Tag>
                        {activeRow.source_kind === "default_seed"
                          ? "默认样本"
                          : activeRow.source_kind === "candidate_only"
                            ? "候选补齐"
                            : "手动加入"}
                      </Tag>
                    </Space>
                    <Paragraph className="panel-description">
                      {activeCandidate?.summary
                        ? sanitizeDisplayText(activeCandidate.summary)
                        : "当前标的已经在关注池中，但还没有最新候选信号，可在右侧操作里触发重分析。"}
                    </Paragraph>
                    {activeCandidate ? (
                      <Alert
                        showIcon
                        className="sub-alert"
                        type={claimGateAlertType(activeCandidate.claim_gate.status)}
                        message={activeCandidate.claim_gate.headline}
                        description={sanitizeDisplayText(claimGateDescription(activeCandidate.claim_gate))}
                      />
                    ) : null}
                    <Descriptions size="small" column={{ xs: 1, md: 2, xl: 4 }}>
                      <Descriptions.Item label="当前触发点">
                        {activeCandidate?.why_now ? sanitizeDisplayText(activeCandidate.why_now) : "等待更新"}
                      </Descriptions.Item>
                      <Descriptions.Item label="主要风险">
                        {activeCandidate?.primary_risk
                          ? sanitizeDisplayText(activeCandidate.primary_risk)
                          : activeRow.last_error
                            ? sanitizeDisplayText(activeRow.last_error)
                            : "暂无额外风险提示"}
                      </Descriptions.Item>
                      <Descriptions.Item label="最近变化">
                        {activeCandidate?.change_summary
                          ? sanitizeDisplayText(activeCandidate.change_summary)
                          : sanitizeDisplayText(activeRow.analysis_status)}
                      </Descriptions.Item>
                      <Descriptions.Item label="验证说明">
                        {publicValidationSummary(activeCandidate?.validation_note, activeCandidate?.validation_status)}
                      </Descriptions.Item>
                      <Descriptions.Item label="验证摘要">
                        {candidateValidationSummary(activeCandidate)}
                      </Descriptions.Item>
                      <Descriptions.Item label="最近分析">{formatDate(activeRow.last_analyzed_at ?? activeRow.updated_at)}</Descriptions.Item>
                    </Descriptions>
                  </>
                ) : (
                  <Empty description="当前没有可展示的标的" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                )}
              </Card>

              <Card
                className="panel-card"
                title="候选股与自选池"
                extra={(
                  <Space wrap>
                    <Text type="secondary">{`共 ${candidateRows.length} 只`}</Text>
                    <Popover
                      open={addPopoverOpen}
                      onOpenChange={setAddPopoverOpen}
                      trigger="click"
                      placement={isMobile ? "bottom" : "bottomRight"}
                      content={addWatchlistOverlay}
                    >
                      <Button shape="circle" type="primary" icon={<PlusOutlined />} />
                    </Popover>
                  </Space>
                )}
              >
                {candidateRows.length === 0 ? (
                  <Empty description="当前自选池为空，请先添加股票代码" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                ) : isMobile ? (
                  <List
                    className="candidate-mobile-list"
                    dataSource={candidateRows}
                    renderItem={(item) => (
                      <List.Item>
                        <Card className={`candidate-mobile-card${item.symbol === activeRow?.symbol ? " candidate-mobile-card-active" : ""}`}>
                          <div className="candidate-mobile-head">
                            <div>
                              <div className="candidate-mobile-rank">{`#${item.candidate?.rank ?? "--"}`}</div>
                              <Title level={5}>{item.name}</Title>
                              <Text type="secondary">{item.symbol}</Text>
                            </div>
                            {item.candidate ? (
                              <Space direction="vertical" size={4} align="end">
                                <Tag color={directionColor(item.candidate.display_direction)}>{item.candidate.display_direction_label}</Tag>
                                <Tag color={claimGateAlertType(item.candidate.claim_gate.status)}>
                                  {claimGateStatusLabel(item.candidate.claim_gate.status)}
                                </Tag>
                              </Space>
                            ) : (
                              <Tag>{item.analysis_status}</Tag>
                            )}
                          </div>
                          <div className="candidate-mobile-metrics">
                            <div>
                              <span>价格</span>
                              <strong>{formatNumber(item.candidate?.last_close)}</strong>
                            </div>
                            <div>
                              <span>20日</span>
                              <strong className={`value-${valueTone(item.candidate?.price_return_20d)}`}>
                                {formatPercent(item.candidate?.price_return_20d)}
                              </strong>
                            </div>
                            <div>
                              <span>分析</span>
                              <strong>{formatDate(item.last_analyzed_at ?? item.updated_at)}</strong>
                            </div>
                          </div>
                          <Paragraph className="panel-description">
                            {item.candidate?.summary ? sanitizeDisplayText(item.candidate.summary) : "等待候选分析结果。"}
                          </Paragraph>
                          <Descriptions size="small" column={1}>
                            <Descriptions.Item label="当前触发点">
                              {item.candidate?.why_now ? sanitizeDisplayText(item.candidate.why_now) : "暂无"}
                            </Descriptions.Item>
                            <Descriptions.Item label="主要风险">
                              {item.candidate?.primary_risk
                                ? sanitizeDisplayText(item.candidate.primary_risk)
                                : item.last_error
                                  ? sanitizeDisplayText(item.last_error)
                                  : "暂无"}
                            </Descriptions.Item>
                            <Descriptions.Item label="验证摘要">{candidateValidationSummary(item.candidate)}</Descriptions.Item>
                          </Descriptions>
                          <div className="candidate-mobile-actions">
                            <Button type="default" onClick={() => handleCandidateSelect(item.symbol, "stock")}>
                              打开
                            </Button>
                            <Button
                              icon={<SyncOutlined />}
                              disabled={item.source_kind === "candidate_only"}
                              loading={mutatingWatchlist && watchlistMutationSymbol === item.symbol}
                              onClick={() => void handleRefreshWatchlist(item.symbol)}
                            >
                              重分析
                            </Button>
                            <Button danger disabled={item.source_kind === "candidate_only"} onClick={() => setPendingRemoval(item)}>
                              移除
                            </Button>
                          </div>
                        </Card>
                      </List.Item>
                    )}
                  />
                ) : (
                  <Table
                    rowKey="symbol"
                    size="middle"
                    pagination={false}
                    dataSource={candidateRows}
                    columns={candidateColumns}
                    scroll={{ x: 1240 }}
                    tableLayout="fixed"
                    onRow={(record) => ({
                      onClick: () => handleCandidateSelect(record.symbol),
                    })}
                    rowClassName={(record) => (record.symbol === activeRow?.symbol ? "candidate-row-active" : "")}
                    locale={{ emptyText: "当前没有候选股" }}
                  />
                )}
              </Card>
            </div>
          ) : null}

          {!loadingShell && view === "stock" ? (
            loadingDetail ? (
              <Card className="panel-card loading-card">
                <Skeleton active paragraph={{ rows: 10 }} />
              </Card>
            ) : !dashboard && pendingDetailMessage ? (
              <Card
                className="panel-card"
                title={activeRow ? `${activeRow.name} · ${activeRow.symbol}` : "单票分析"}
                extra={activeRow ? <Tag color="gold">等待真实行情</Tag> : null}
              >
                <Alert
                  showIcon
                  type="warning"
                  className="status-alert"
                  message="面板暂未生成"
                  description={pendingDetailMessage}
                />
                <Descriptions size="small" column={1} style={{ marginTop: 16 }}>
                  <Descriptions.Item label="当前状态">pending_real_data</Descriptions.Item>
                  <Descriptions.Item label="最近更新时间">{formatDate(activeRow?.updated_at)}</Descriptions.Item>
                  <Descriptions.Item label="建议操作">修复行情抓取后点击"重分析"重新生成面板。</Descriptions.Item>
                </Descriptions>
              </Card>
            ) : !dashboard ? (
              <Card className="panel-card">
                <Empty description="当前没有可展示的单票分析" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              </Card>
            ) : (
              <div className="panel-stack">
                <div className="metric-strip">
                  <div className="metric-strip-item">
                    <span>最新收盘</span>
                    <strong>{formatNumber(dashboard.hero.latest_close)}</strong>
                  </div>
                  <div className="metric-strip-item">
                    <span>日涨跌</span>
                    <strong className={`value-${valueTone(dashboard.hero.day_change_pct)}`}>{formatPercent(dashboard.hero.day_change_pct)}</strong>
                  </div>
                  <div className="metric-strip-item">
                    <span>置信表达</span>
                    <strong>{dashboard.recommendation.confidence_expression}</strong>
                  </div>
                  <div className="metric-strip-item">
                    <span>最近刷新</span>
                    <strong>{formatDate(dashboard.hero.last_updated)}</strong>
                  </div>
                </div>

                <Row gutter={[16, 16]} className="equal-height-row">
                  <Col xs={24} xl={16}>
                    <Card
                      className="panel-card"
                      title={`${dashboard.stock.name} · ${dashboard.stock.symbol}`}
                      extra={
                        <Space wrap className="inline-tags">
                          <Tag color={directionColor(dashboard.recommendation.claim_gate.public_direction)}>{dashboard.hero.direction_label}</Tag>
                          {dashboard.recommendation.claim_gate.public_direction !== dashboard.recommendation.direction ? (
                            <Tag>{`模型原始方向：${directionLabels[dashboard.recommendation.direction] ?? dashboard.recommendation.direction}`}</Tag>
                          ) : null}
                          <Tag color={claimGateAlertType(dashboard.recommendation.claim_gate.status)}>
                            {claimGateStatusLabel(dashboard.recommendation.claim_gate.status)}
                          </Tag>
                          <Tag>{`${dashboard.recommendation.confidence_label}置信`}</Tag>
                        </Space>
                      }
                    >
                      <Paragraph className="panel-description">{sanitizeDisplayText(dashboard.recommendation.summary)}</Paragraph>
                      <KlinePanel
                        title={`${dashboard.stock.name} · ${dashboard.stock.symbol} K 线`}
                        points={dashboard.price_chart}
                        lastUpdated={dashboard.hero.last_updated}
                        stockName={dashboard.stock.name}
                        isMobile={isMobile}
                      />
                      <div className="chart-meta-row">
                        <span>{`区间高点 ${formatNumber(dashboard.hero.high_price)}`}</span>
                        <span>{`区间低点 ${formatNumber(dashboard.hero.low_price)}`}</span>
                        <span>{`换手率 ${dashboard.hero.turnover_rate ? formatPercent(dashboard.hero.turnover_rate / 100) : "未提供"}`}</span>
                      </div>
                      <Space wrap className="inline-tags">
                        {dashboard.hero.sector_tags.map((tag) => (
                          <Tag key={tag} color="blue">
                            {tag}
                          </Tag>
                        ))}
                      </Space>
                    </Card>
                  </Col>
                  <Col xs={24} xl={8}>
                    <Card className="panel-card" title="当前建议摘要">
                      <Descriptions size="small" column={1}>
                        <Descriptions.Item label="观察窗口">
                          {displayWindowLabel(dashboard.recommendation.historical_validation.window_definition)}
                        </Descriptions.Item>
                        <Descriptions.Item label="目标 horizon">
                          {horizonLabel(dashboard.recommendation.core_quant.target_horizon_label)}
                        </Descriptions.Item>
                        <Descriptions.Item label="对外表达">
                          {claimGateStatusLabel(dashboard.recommendation.claim_gate.status)}
                        </Descriptions.Item>
                        <Descriptions.Item label="验证状态">
                          {validationStatusLabel(dashboard.recommendation.historical_validation.status)}
                        </Descriptions.Item>
                        <Descriptions.Item label="数据时间">{formatDate(dashboard.recommendation.core_quant.as_of_time)}</Descriptions.Item>
                        <Descriptions.Item label="生成时间">{formatDate(dashboard.recommendation.core_quant.available_time)}</Descriptions.Item>
                        <Descriptions.Item label="模型版本">{dashboard.recommendation.core_quant.model_version}</Descriptions.Item>
                      </Descriptions>
                      <Alert
                        className="sub-alert"
                        type={claimGateAlertType(dashboard.recommendation.claim_gate.status)}
                        showIcon
                        message={dashboard.recommendation.claim_gate.headline}
                        description={sanitizeDisplayText(claimGateDescription(dashboard.recommendation.claim_gate))}
                      />
                      {dashboard.recommendation.historical_validation.note ? (
                        <Alert
                          className="sub-alert"
                          type="warning"
                          showIcon
                          message="验证说明"
                          description={sanitizeDisplayText(dashboard.recommendation.historical_validation.note)}
                        />
                      ) : null}
                      <Collapse
                        ghost
                        className="summary-block-compact"
                        defaultActiveKey={["drivers"]}
                        items={[
                          {
                            key: "drivers",
                            label: <span style={{ fontWeight: 600 }}>核心驱动</span>,
                            children: (
                              <ul className="plain-list">
                                {dashboard.recommendation.evidence.primary_drivers.map((item) => (
                                  <li key={item}>{sanitizeDisplayText(item)}</li>
                                ))}
                              </ul>
                            ),
                          },
                          {
                            key: "risks",
                            label: <span style={{ fontWeight: 600 }}>反向风险</span>,
                            children: (
                              <ul className="plain-list">
                                {dashboard.recommendation.risk.risk_flags.map((item) => (
                                  <li key={item}>{sanitizeDisplayText(item)}</li>
                                ))}
                              </ul>
                            ),
                          },
                        ]}
                      />
                      {dashboard.recommendation.risk.coverage_gaps.length > 0 ? (
                        <Alert
                          className="sub-alert"
                          type="info"
                          showIcon
                          message="当前覆盖缺口"
                          description={dashboard.recommendation.risk.coverage_gaps.map((item) => sanitizeDisplayText(item)).join(" ")}
                        />
                      ) : null}
                    </Card>
                  </Col>
                </Row>

                <Card className="panel-card">
                  <Tabs activeKey={stockActiveTab} onChange={setStockActiveTab} items={stockTabItems} />
                </Card>
              </div>
            )
          ) : null}

          {!loadingShell && view === "operations" ? (
            operationsLoading && !operations && !simulation ? (
              <Card className="panel-card loading-card">
                <Skeleton active paragraph={{ rows: 10 }} />
              </Card>
            ) : (
              <div className="panel-stack">
                {operationsError ? (
                  <Alert
                    type="warning"
                    showIcon
                    className="panel-card"
                    message="运营复盘工作区加载失败"
                    description={operationsError}
                    action={selectedSymbol ? <Button size="small" onClick={() => void loadOperationsData(selectedSymbol)}>重试</Button> : undefined}
                  />
                ) : null}

                <Row gutter={[16, 16]}>
                  <Col xs={24} md={12} xl={6}>
                    <Card className="panel-card metric-card">
                      <Statistic title="当前状态" value={simulation?.session.status_label ?? "概览可用"} />
                    </Card>
                  </Col>
                  <Col xs={24} md={12} xl={6}>
                    <Card className="panel-card metric-card">
                      <Statistic title="当前步数" value={simulation?.session.current_step ?? 0} />
                    </Card>
                  </Col>
                  <Col xs={24} md={12} xl={6}>
                    <Card className="panel-card metric-card">
                      <Statistic
                        title="最新行情"
                        value={formatMarketFreshness(
                          operations?.data_latency_seconds ?? simulation?.session.data_latency_seconds,
                          simulation?.session.last_market_data_at ?? operations?.overview.run_health.last_market_data_at,
                          true,
                        )}
                      />
                    </Card>
                  </Col>
                  <Col xs={24} md={12} xl={6}>
                    <Card className="panel-card metric-card">
                      <Statistic
                        title="复盘状态"
                        value={operations ? validationStatusLabel(operations.overview.research_validation.status) : "--"}
                      />
                    </Card>
                  </Col>
                </Row>

                {simulation ? (
                  <>
                    {operations?.overview.research_validation.note ? (
                      <Alert
                        type="warning"
                        showIcon
                        className="panel-card"
                        message={operationsValidationMessage(operations.overview.research_validation.status)}
                        description={operationsValidationDescription(operations.overview.research_validation)}
                      />
                    ) : null}
                    <Row gutter={[16, 16]}>
                      <Col xs={24} xl={14}>
                        <Card
                          className="panel-card operations-command-card"
                          title="双轨同步模拟台"
                          extra={<Tag color={statusColor(simulation.session.status)}>{simulation.session.status_label}</Tag>}
                        >
                          <Paragraph className="panel-description">
                            用户轨道与模型轨道共享时间线推进，当前表格默认展示当前模拟股票池。默认会跟随关注池；如果你改过模拟配置，这里显示的是当前配置内的股票池。
                          </Paragraph>
                          <Space wrap className="inline-tags">
                            <Tag>{`模拟池 ${simulation.session.watch_symbols.length} 只`}</Tag>
                            <Tag>{`初始资金 ${formatNumber(simulation.session.initial_cash)}`}</Tag>
                            <Tag>{simulation.session.fill_rule_label}</Tag>
                            <Tag color="blue">{`行情 ${simulation.session.market_data_timeframe ?? "5min"}`}</Tag>
                            <Tag color="geekblue">{`决策 ${Math.round((simulation.session.step_interval_seconds ?? 1800) / 60)} 分钟`}</Tag>
                            <Tag>{`重启 ${simulation.session.restart_count} 次`}</Tag>
                          </Space>
                          <div className="deck-actions">
                            <Button
                              type="primary"
                              icon={<ThunderboltOutlined />}
                              disabled={!simulation.controls.can_start}
                              loading={simulationAction === "start"}
                              onClick={() => void runSimulationAction("start", () => api.startSimulation())}
                            >
                              启动
                            </Button>
                            <Button
                              icon={<SyncOutlined />}
                              disabled={!simulation.controls.can_pause}
                              loading={simulationAction === "pause"}
                              onClick={() => void runSimulationAction("pause", () => api.pauseSimulation())}
                            >
                              暂停
                            </Button>
                            <Button
                              icon={<ReloadOutlined />}
                              disabled={!simulation.controls.can_resume}
                              loading={simulationAction === "resume"}
                              onClick={() => void runSimulationAction("resume", () => api.resumeSimulation())}
                            >
                              恢复
                            </Button>
                            <Button
                              type="default"
                              disabled={!simulation.controls.can_step}
                              loading={simulationAction === "step"}
                              onClick={() => void runSimulationAction("step", () => api.stepSimulation())}
                            >
                              单步推进
                            </Button>
                            <Button
                              disabled={!simulation.controls.can_restart}
                              loading={simulationAction === "restart"}
                              onClick={() => void runSimulationAction("restart", () => api.restartSimulation())}
                            >
                              重启
                            </Button>
                            <Button
                              danger
                              disabled={!simulation.controls.can_end}
                              loading={simulationAction === "end"}
                              onClick={handleEndSimulation}
                            >
                              结束
                            </Button>
                          </div>
                          <Descriptions size="small" column={{ xs: 1, md: 2, xl: 3 }} className="info-grid">
                            <Descriptions.Item label="推进规则">{simulation.session.step_trigger_label}</Descriptions.Item>
                            <Descriptions.Item label="焦点标的">{operationsFocusSymbol ?? "--"}</Descriptions.Item>
                            <Descriptions.Item label="最近数据">{formatDate(simulation.session.last_data_time)}</Descriptions.Item>
                            <Descriptions.Item label="最近行情">{formatDate(simulation.session.last_market_data_at ?? simulation.session.last_data_time)}</Descriptions.Item>
                            <Descriptions.Item label="行情来源">{simulation.session.intraday_source_status?.provider_label ?? "未同步"}</Descriptions.Item>
                            <Descriptions.Item label="行情刷新">
                              {formatMarketFreshness(
                                simulation.session.data_latency_seconds,
                                simulation.session.last_market_data_at ?? simulation.session.last_data_time,
                              )}
                            </Descriptions.Item>
                            <Descriptions.Item label="启动时间">{formatDate(simulation.session.started_at)}</Descriptions.Item>
                            <Descriptions.Item label="最近恢复">{formatDate(simulation.session.last_resumed_at)}</Descriptions.Item>
                            <Descriptions.Item label="最近暂停">{formatDate(simulation.session.paused_at)}</Descriptions.Item>
                          </Descriptions>
                        </Card>
                      </Col>
                      <Col xs={24} xl={10}>
                        <Card
                          className="panel-card"
                          title="焦点 K 线"
                          extra={(
                            <Select
                              className="operations-focus-select"
                              value={operationsFocusSymbol ?? undefined}
                              options={simulation.session.watch_symbols.map((symbol) => ({
                                value: symbol,
                                label: `${symbolNameMap.get(symbol) ?? symbol} · ${symbol}`,
                              }))}
                              onChange={(value) => void handleSimulationFocusChange(value)}
                            />
                          )}
                        >
                          <KlinePanel
                            title={`${simulation.kline.stock_name ?? simulation.kline.symbol ?? "焦点标的"} K 线`}
                            points={simulation.kline.points}
                            lastUpdated={simulation.kline.last_updated}
                            stockName={simulation.kline.stock_name ?? simulation.kline.symbol}
                            isMobile={isMobile}
                          />
                        </Card>
                      </Col>
                    </Row>

                    <Row gutter={[16, 16]}>
                      <Col xs={24} xxl={12}>
                        <SimulationTrackCard
                          track={simulation.manual_track}
                          watchSymbols={simulationConfigDraft?.watch_symbols ?? simulation.session.watch_symbols}
                          candidateRows={candidateRows}
                          symbolNameMap={symbolNameMap}
                          modelAdvices={simulation.model_advices}
                          activeSymbol={operationsFocusSymbol}
                          onViewKline={(symbol) => void handleSimulationFocusChange(symbol)}
                          onOpenReport={(symbol) => void openAnalysisReportModal(symbol)}
                          onOpenOrder={openManualOrderModal}
                        />
                      </Col>
                      <Col xs={24} xxl={12}>
                        <SimulationTrackCard
                          track={simulation.model_track}
                          watchSymbols={simulationConfigDraft?.watch_symbols ?? simulation.session.watch_symbols}
                          candidateRows={candidateRows}
                          symbolNameMap={symbolNameMap}
                          modelAdvices={simulation.model_advices}
                          activeSymbol={operationsFocusSymbol}
                          onViewKline={(symbol) => void handleSimulationFocusChange(symbol)}
                          onOpenReport={(symbol) => void openAnalysisReportModal(symbol)}
                        />
                      </Col>
                    </Row>
                  </>
                ) : null}

                {operations ? (
                  <Card className="panel-card" title="运营复盘分析">
                    <Tabs items={operationsTabItems} />
                  </Card>
                ) : null}
              </div>
            )
          ) : null}

          {!loadingShell && view === "settings" ? (
            <div className="panel-stack">
              <Card className="panel-card" title="设置">
                <Tabs items={settingsTabItems} />
              </Card>
            </div>
          ) : null}
        </div>
      </div>

      <Modal
        open={Boolean(completeResearchTarget)}
        centered
        width={isMobile ? "calc(100vw - 20px)" : 760}
        title={completeResearchTarget ? `人工完成研究请求 · ${completeResearchTarget.symbol}` : "人工完成研究请求"}
        okText="确认完成"
        cancelText="取消"
        confirmLoading={manualResearchAction === `complete:${completeResearchTarget?.id}`}
        onCancel={closeCompleteManualResearchModal}
        onOk={() => void handleConfirmCompleteManualResearch()}
      >
        {completeResearchTarget ? (
          <Form layout="vertical">
            <Alert
              className="sub-alert"
              type="info"
              showIcon
              message={sanitizeDisplayText(completeResearchTarget.question)}
              description={`当前状态 ${manualReviewStatusLabel(completeResearchTarget.status)}`}
            />
            <Form.Item label="研究摘要" required>
              <TextArea
                rows={4}
                value={completeResearchSummary}
                onChange={(event) => setCompleteResearchSummary(event.target.value)}
                placeholder="给出这次人工研究的结论摘要。"
              />
            </Form.Item>
            <Form.Item label="研究结论">
              <Select
                value={completeResearchVerdict}
                options={manualResearchVerdictOptions}
                onChange={(value) => setCompleteResearchVerdict(value)}
              />
            </Form.Item>
            <Form.Item label="风险点">
              <TextArea
                rows={3}
                value={completeResearchRisks}
                onChange={(event) => setCompleteResearchRisks(event.target.value)}
                placeholder="每行一个风险点"
              />
            </Form.Item>
            <Form.Item label="与量化层分歧">
              <TextArea
                rows={3}
                value={completeResearchDisagreements}
                onChange={(event) => setCompleteResearchDisagreements(event.target.value)}
                placeholder="每行一个分歧点"
              />
            </Form.Item>
            <Form.Item label="治理说明">
              <TextArea
                rows={3}
                value={completeResearchDecisionNote}
                onChange={(event) => setCompleteResearchDecisionNote(event.target.value)}
                placeholder="说明这份人工研究应该如何影响当前建议。"
              />
            </Form.Item>
            <Form.Item label="引用 / 证据">
              <TextArea
                rows={3}
                value={completeResearchCitations}
                onChange={(event) => setCompleteResearchCitations(event.target.value)}
                placeholder="每行一条引用或证据来源"
              />
            </Form.Item>
            <Form.Item label="完整回答">
              <TextArea
                rows={5}
                value={completeResearchAnswer}
                onChange={(event) => setCompleteResearchAnswer(event.target.value)}
                placeholder="可选：保留完整人工结论文本；留空则回落到摘要。"
              />
            </Form.Item>
          </Form>
        ) : null}
      </Modal>

      <Modal
        open={Boolean(failResearchTarget)}
        centered
        width={isMobile ? "calc(100vw - 20px)" : 640}
        title={failResearchTarget ? `标记研究请求失败 · ${failResearchTarget.symbol}` : "标记研究请求失败"}
        okText="确认失败"
        cancelText="取消"
        okButtonProps={{ danger: true }}
        confirmLoading={manualResearchAction === `fail:${failResearchTarget?.id}`}
        onCancel={closeFailManualResearchModal}
        onOk={() => void handleConfirmFailManualResearch()}
      >
        {failResearchTarget ? (
          <>
            <Alert
              className="sub-alert"
              type="warning"
              showIcon
              message={sanitizeDisplayText(failResearchTarget.question)}
              description={`当前状态 ${manualReviewStatusLabel(failResearchTarget.status)}`}
            />
            <Form layout="vertical">
              <Form.Item label="失败原因" required>
                <TextArea
                  rows={5}
                  value={failResearchReason}
                  onChange={(event) => setFailResearchReason(event.target.value)}
                  placeholder="记录为什么无法继续完成这次人工研究。"
                />
              </Form.Item>
            </Form>
          </>
        ) : null}
      </Modal>

      <Modal
        open={Boolean(orderModalSymbol && simulation)}
        centered
        width={isMobile ? "calc(100vw - 20px)" : 880}
        footer={null}
        title={orderModalSymbol ? `用户轨道操作 · ${symbolNameMap.get(orderModalSymbol) ?? orderModalSymbol}` : "用户轨道操作"}
        onCancel={() => setOrderModalSymbol(null)}
      >
        {simulation ? (
          <div className="manual-order-modal">
            <div className="manual-order-summary-grid">
              <div className="kline-summary-card">
                <span>当前持股</span>
                <strong>{formatNumber(manualOrderActiveHolding?.quantity ?? 0)}</strong>
              </div>
              <div className="kline-summary-card">
                <span>现价 / 成本</span>
                <strong>{`${formatNumber(manualOrderActiveHolding?.last_price)} / ${manualOrderActiveHolding && manualOrderActiveHolding.avg_cost > 0 ? formatNumber(manualOrderActiveHolding.avg_cost) : "--"}`}</strong>
              </div>
              <div className="kline-summary-card">
                <span>持仓盈亏</span>
                <strong className={`value-${valueTone(manualOrderActiveHolding?.total_pnl)}`}>{formatSignedNumber(manualOrderActiveHolding?.total_pnl)}</strong>
              </div>
              <div className="kline-summary-card">
                <span>模型参考</span>
                <strong>
                  {activeSimulationAdvice
                    ? activeSimulationAdvice.policy_type === "manual_review_preview_policy_v1"
                      ? `预览 ${simulationAdviceActionLabel(activeSimulationAdvice)}`
                      : simulationAdviceActionLabel(activeSimulationAdvice)
                    : "暂无"}
                </strong>
              </div>
            </div>
            <Form layout="vertical">
              <Row gutter={[16, 0]}>
                <Col xs={24} md={12}>
                  <Form.Item label="标的">
                    <Select
                      value={manualOrderDraft.symbol || undefined}
                      options={simulation.session.watch_symbols.map((symbol) => ({
                        value: symbol,
                        label: `${symbolNameMap.get(symbol) ?? symbol} · ${symbol}`,
                      }))}
                      onChange={(value) => setManualOrderDraft((current) => ({ ...current, symbol: value }))}
                    />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item label="方向">
                    <Select
                      value={manualOrderDraft.side}
                      options={[
                        { value: "buy", label: "买入" },
                        { value: "sell", label: "卖出" },
                      ]}
                      onChange={(value) => setManualOrderDraft((current) => ({ ...current, side: value }))}
                    />
                  </Form.Item>
                </Col>
              </Row>
              <Row gutter={[16, 0]}>
                <Col xs={24} md={12}>
                  <Form.Item label="数量">
                    <InputNumber
                      className="full-width"
                      min={100}
                      step={100}
                      value={manualOrderDraft.quantity}
                      onChange={(value) =>
                        setManualOrderDraft((current) => ({ ...current, quantity: Number(value ?? current.quantity) }))
                      }
                    />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item label="限价（可选）">
                    <InputNumber
                      className="full-width"
                      min={0}
                      step={0.01}
                      value={manualOrderDraft.limit_price ?? undefined}
                      onChange={(value) =>
                        setManualOrderDraft((current) => ({ ...current, limit_price: value === null ? null : Number(value) }))
                      }
                    />
                  </Form.Item>
                </Col>
              </Row>
              <Form.Item label="交易理由">
                <TextArea
                  rows={5}
                  value={manualOrderDraft.reason}
                  onChange={(event) => setManualOrderDraft((current) => ({ ...current, reason: event.target.value }))}
                  placeholder="记录你基于轨道表现、K线和证据做出该笔交易的理由"
                />
              </Form.Item>
            </Form>
            {activeSimulationAdvice ? (
              <Alert
                className="sub-alert"
                type="info"
                showIcon
                message={`模型轨道当前建议：${activeSimulationAdvice.direction_label}`}
                description={`${activeSimulationAdvice.reason} · 参考价 ${formatNumber(activeSimulationAdvice.reference_price)}。`}
              />
            ) : null}
            <Alert
              className="sub-alert"
              type="info"
              showIcon
              message="一期成交规则"
              description="当前按最新价即时成交，用于快速对比用户和模型在同一步上的决策差异。"
            />
            <div className="deck-actions">
              <Button
                type="primary"
                loading={simulationAction === "manual-order"}
                onClick={() => void handleSubmitManualOrder()}
              >
                提交模拟单
              </Button>
            </div>
          </div>
        ) : null}
      </Modal>

      <Modal
        open={Boolean(analysisReportSymbol)}
        centered
        footer={null}
        width={isMobile ? "calc(100vw - 20px)" : 760}
        title={analysisReportRow ? `运营复盘分析报告 · ${analysisReportRow.name}` : "运营复盘分析报告"}
        onCancel={closeAnalysisReportModal}
      >
        <CompactAnalysisReport
          row={analysisReportRow}
          dashboard={analysisReportDashboard}
          loading={analysisReportLoading}
          error={analysisReportError}
          onOpenFullAnalysis={() => {
            if (analysisReportSymbol) {
              openFullAnalysisFromReport(analysisReportSymbol);
            }
          }}
        />
      </Modal>

      <Modal
        open={Boolean(pendingRemoval)}
        centered
        title={pendingRemoval ? `移除 ${pendingRemoval.name}` : "移除标的"}
        okText="确认移除"
        cancelText="取消"
        okButtonProps={{ danger: true }}
        confirmLoading={mutatingWatchlist && watchlistMutationSymbol === pendingRemoval?.symbol}
        onCancel={() => setPendingRemoval(null)}
        onOk={() => void handleConfirmRemoveWatchlist()}
      >
        <Paragraph className="panel-description">
          该标的会从共享自选池中移除，相关候选缓存也会失去预热资格。确认继续吗？
        </Paragraph>
      </Modal>
    </>
  );
}

export default App;
