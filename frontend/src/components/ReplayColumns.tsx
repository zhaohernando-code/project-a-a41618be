import { Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { GlossaryEntryView, RecommendationReplayView } from "../types";
import {
  compactValidationNote,
  displayBenchmarkLabel,
  displayLabelDefinition,
  displayWindowLabel,
  publicValidationSummary,
  sanitizeDisplayText,
  validationStatusLabel,
} from "../utils/labels";
import { directionColor, formatDate, formatNumber, formatPercent, formatSignedNumber, statusColor } from "../utils/format";
import { directionLabels } from "../utils/constants";

const { Text } = Typography;

export interface BuildReplayColumnsInput {
  glossary: GlossaryEntryView[];
}

export function buildReplayColumns(_input: BuildReplayColumnsInput): ColumnsType<RecommendationReplayView> {
  return [
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

;
}
