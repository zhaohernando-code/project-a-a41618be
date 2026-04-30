import { useEffect, useRef } from "react";
import { Button, Descriptions, Empty, Space, Table, Tag, Typography, Skeleton, Alert } from "antd";
const { Paragraph } = Typography;
import type { ColumnsType } from "antd/es/table";
import { init } from "echarts";
import type { CandidateItemView, CandidateWorkspaceRow, ClaimGateView, GlossaryEntryView, ManualResearchRequestView, RecommendationReplayView, StockDashboardResponse } from "../types";
import { formatDate, formatNumber, formatPercent, formatSignedNumber, statusColor } from "../utils/format";
import { compactValidationNote, sanitizeDisplayText, publicValidationSummary, candidateValidationSummary, claimGateDescription, claimGateAlertType, claimGateStatusLabel, displayBenchmarkLabel, displayLabelDefinition, displayWindowLabel, validationStatusLabel, manualReviewStatusLabel } from "../utils/labels";
import { manualResearchVerdictOptions } from "../utils/constants";
import { directionColor } from "../utils/format";

import { buildPendingDetailMessage, horizonLabel, validationMetricSummary } from "../utils/labels";



export function CompactAnalysisReport({
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
