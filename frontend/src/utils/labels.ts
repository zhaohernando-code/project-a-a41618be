// labels helper functions
import type { CandidateItemView, ClaimGateView, ManualResearchRequestView, OperationsLaunchReadinessView, OperationsResearchValidationView, PortfolioSummaryView, RuntimeDataSourceView, RuntimeFieldMappingView, WatchlistItemView } from "../types";
import { numberFormatter, percentFormatter, signedNumberFormatter } from "./constants";
import { directionColor, formatDate, formatNumber, formatPercent, formatSignedNumber, normalizeDisplayText, statusColor, valueTone } from "./format";

export function validationStatusLabel(status?: string | null): string {
  if (status === "verified") return "已验证";
  if (status === "synthetic_demo") return "参考样本";
  if (status === "manual_trigger_required") return "待补充人工研究";
  if (status === "approved_for_product") return "已批准接入产品";
  if (status === "pending_rebuild") return "口径校准中";
  if (status === "research_candidate") return "研究观察中";
  return status || "未提供";
}


export function claimGateStatusLabel(status?: string | null): string {
  if (status === "claim_ready") return "可引用结论";
  if (status === "observe_only") return "仅观察";
  if (status === "insufficient_validation") return "验证不足";
  return status || "未提供";
}


export function claimGateAlertType(status?: string | null): "success" | "warning" | "error" | "info" {
  if (status === "claim_ready") return "success";
  if (status === "observe_only") return "warning";
  if (status === "insufficient_validation") return "error";
  return "info";
}


export function dedupeDisplaySentences(value?: string | null): string {
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


export function compactValidationNote(
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


export function isChinaMarketTradingTimestamp(value?: string | null): boolean {
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


export function formatMarketFreshness(
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


export function portfolioTrackLabel(portfolio: PortfolioSummaryView): string {
  if (portfolio.mode === "manual") return "用户轨道";
  if (portfolio.mode === "auto_model") return "模型轨道";
  return sanitizeDisplayText(portfolio.mode_label || portfolio.name);
}


export function portfolioTrackSummary(portfolio: PortfolioSummaryView): string {
  if (portfolio.mode === "manual") {
    return "记录手动下单结果，用来复盘人工执行是否跟上建议。";
  }
  if (portfolio.mode === "auto_model") {
    return "记录模型在模拟盘内的自动调仓结果，用来观察组合纪律与执行损耗。";
  }
  return sanitizeDisplayText(portfolio.strategy_summary);
}


export function claimGateDescription(claimGate?: ClaimGateView | null): string {
  if (!claimGate) return "当前缺少结论门槛说明。";
  const parts = [claimGate.note, ...claimGate.blocking_reasons.slice(0, 2)].filter(
    (item): item is string => Boolean(item && item.trim()),
  );
  return parts.length > 0 ? parts.join(" ") : "当前缺少结论门槛说明。";
}


export function projectionModeLabel(mode?: string | null): string {
  if (mode === "artifact_backed") return "已绑定研究产物";
  if (mode === "migration_placeholder") return "口径切换中";
  return mode || "未提供";
}


export function sanitizeDisplayText(value?: string | null): string {
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


export function eventTriggerLabel(trigger?: string | null): string {
  if (trigger === "price_shock") return "价格冲击";
  if (trigger === "direction_switch") return "方向切换";
  if (trigger === "confidence_collapse") return "置信回落";
  if (trigger === "factor_conflict") return "因子冲突";
  if (trigger === "major_announcement") return "重大公告";
  if (trigger === "weekly_review") return "周度例行复盘";
  return sanitizeDisplayText(trigger);
}


export function eventDirectionLabel(direction?: string | null): string {
  if (direction === "agree") return "独立判断一致";
  if (direction === "partial_agree") return "部分一致";
  if (direction === "disagree") return "独立判断不一致";
  if (direction === "insufficient_evidence") return "证据不足";
  return sanitizeDisplayText(direction);
}


export function eventDirectionStatus(direction?: string | null): string {
  if (direction === "agree") return "pass";
  if (direction === "partial_agree") return "warn";
  if (direction === "disagree") return "fail";
  if (direction === "insufficient_evidence") return "warn";
  return "pending";
}


export function eventEvidenceText(item: Record<string, any> | string): string {
  if (typeof item === "string") return sanitizeDisplayText(item);
  const content = item.content ?? item.finding ?? item.text ?? item.summary ?? item.evidence ?? "";
  const source = item.source ?? item.title ?? item.label ?? "";
  const joined = [source, content].filter(Boolean).join("：");
  return sanitizeDisplayText(joined || JSON.stringify(item));
}


export function displayWindowLabel(value?: string | null): string {
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


export function displayBenchmarkLabel(value?: string | null): string {
  if (!value) return "未提供";
  if (value === "phase2_equal_weight_market_proxy") return "市场等权对照篮子";
  if (value === "active_watchlist_equal_weight_proxy") return "自选池等权对照篮子";
  if (value === "csi300" || value === "CSI300") return "沪深 300";
  if (value === "pending_rebuild") return "基准口径校准中";
  return sanitizeDisplayText(value);
}


export function displayLabelDefinition(value?: string | null): string {
  if (!value) return "未提供";
  if (value === "phase5-validation-policy-contract-v1") return "滚动验证口径";
  if (value === "research_rebuild_pending") return "滚动验证口径校准中";
  return sanitizeDisplayText(value);
}


export function horizonLabel(value?: string | null): string {
  if (value === "research_window_pending") return "研究窗口待锁定";
  const excessMatch = value?.match(/^forward_excess_return_(\d+)d$/);
  if (excessMatch) return `${excessMatch[1]}日超额收益`;
  const returnMatch = value?.match(/^forward_return_(\d+)d$/);
  if (returnMatch) return `${returnMatch[1]}日收益`;
  return sanitizeDisplayText(value);
}


export function manualReviewModelLabel(value?: string | null): string {
  if (!value) return "未指定";
  if (value === "Manual research workflow") return "人工研究流程";
  return sanitizeDisplayText(value);
}


export function deploymentModeLabel(value?: string | null): string {
  if (value === "self_hosted_server") return "本机服务端部署";
  return sanitizeDisplayText(value);
}


export function providerSelectionModeLabel(value?: string | null): string {
  if (value === "runtime_policy") return "按运行策略自动选源";
  return sanitizeDisplayText(value);
}


export function watchlistScopeLabel(value?: string | null): string {
  if (value === "global_shared_pool" || value === "shared_watchlist") return "共享自选池";
  return sanitizeDisplayText(value);
}


export function fieldMappingLabel(item: RuntimeFieldMappingView): string {
  const key = `${item.dataset}.${item.canonical_field}`;
  if (key === "quote.last_price") return "最新价";
  if (key === "quote.turnover_rate_pct") return "换手率";
  if (key === "kline.trade_time") return "K 线时间";
  if (key === "kline.adjustment") return "复权口径";
  if (key === "financial_report.report_period") return "财报报告期";
  if (key === "financial_report.revenue") return "营业收入";
  return sanitizeDisplayText(item.canonical_field);
}


export function operationsValidationMessage(status?: string | null): string {
  return `研究验证 · ${validationStatusLabel(status)}`;
}


export function operationsValidationDescription(view?: OperationsResearchValidationView | null): string {
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


export function launchReadinessDescription(view?: OperationsLaunchReadinessView | null): string {
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


export function manualReviewStatusLabel(status?: string | null): string {
  if (status === "manual_trigger_required") return "等待人工触发";
  if (status === "queued") return "已排队";
  if (status === "in_progress") return "分析中";
  if (status === "completed") return "已完成";
  if (status === "failed") return "执行失败";
  if (status === "stale") return "结果过期";
  return status || "未提供";
}


export function manualResearchActionStatusMessage(request: ManualResearchRequestView): string {
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


export function parseMultilineItems(value: string): string[] {
  return value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}


export function canExecuteManualResearch(request: ManualResearchRequestView): boolean {
  return ["queued", "failed"].includes(request.status);
}


export function canRetryManualResearch(request: ManualResearchRequestView): boolean {
  return ["completed", "stale", "failed"].includes(request.status);
}


export function canCompleteManualResearch(request: ManualResearchRequestView): boolean {
  return !request.artifact_id && ["queued", "in_progress", "failed"].includes(request.status);
}


export function canFailManualResearch(request: ManualResearchRequestView): boolean {
  return !request.artifact_id && ["queued", "in_progress"].includes(request.status);
}


export function validationMetricSummary(
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


export function candidateValidationSummary(candidate?: CandidateItemView | null): string {
  if (!candidate) return "验证样本待补充";
  return validationMetricSummary(
    candidate.validation_sample_count,
    candidate.validation_rank_ic_mean,
    candidate.validation_positive_excess_rate,
  );
}


export function publicValidationSummary(
  note?: string | null,
  status?: string | null,
  fallback = "以最新研究验证为准",
): string {
  return compactValidationNote(note, status, fallback);
}


export function dataSourceStatusColor(item: RuntimeDataSourceView): string {
  if (item.runtime_ready) return "green";
  if (!item.credential_required) return "default";
  return item.credential_configured ? "green" : "gold";
}


export function buildPendingDetailMessage(item: WatchlistItemView | null): string | null {
  if (!item || item.analysis_status !== "pending_real_data") {
    return null;
  }
  return item.last_error || "真实行情待刷新，当前还没有可展示的单票分析面板。";
}
