import { Button, Popover, Space, Table, Tag, Typography } from "antd";
import { DeleteOutlined, SyncOutlined } from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import type {
  CandidateItemView,
  CandidateWorkspaceRow,
  GlossaryEntryView,
  RecommendationReplayView,
  ViewMode,
} from "../types";
import {
  candidateValidationSummary,
  claimGateAlertType,
  claimGateStatusLabel,
  compactValidationNote,
  publicValidationSummary,
  sanitizeDisplayText,
  validationStatusLabel,
  displayWindowLabel,
  horizonLabel,
} from "../utils/labels";
import { directionColor, formatDate, formatNumber, formatPercent, formatSignedNumber, statusColor, valueTone } from "../utils/format";
import { directionLabels, factorLabels } from "../utils/constants";

const { Paragraph, Text } = Typography;

export interface CandidateColumnsInput {
  candidateRows: CandidateWorkspaceRow[];
  activeCandidate: CandidateItemView | null;
  glossary: GlossaryEntryView[];
  generatedAt: string | null;
  pendingRemoval: CandidateWorkspaceRow | null;
  setPendingRemoval: (row: CandidateWorkspaceRow | null) => void;
  handleCandidateSelect: (symbol: string, nextView?: ViewMode) => void;
  handleConfirmRemoveWatchlist: () => Promise<void>;
  mutatingWatchlist: boolean;
  addPopoverOpen: boolean;
  setAddPopoverOpen: (v: boolean) => void;
  setWatchlistSymbolDraft: (v: string) => void;
  setWatchlistNameDraft: (v: string) => void;
  handleAddWatchlist: (e: React.MouseEvent) => void;
  watchlistSymbolDraft: string;
  watchlistNameDraft: string;
  selectedSymbol: string | null;
  view: ViewMode;
  canMutateWatchlist: boolean;
  watchlistMutationSymbol: string | null;
  handleRefreshWatchlist: (symbol: string) => Promise<void>;
}

export function buildCandidateColumns(input: CandidateColumnsInput): ColumnsType<CandidateWorkspaceRow> {
  const {
    candidateRows, activeCandidate, glossary, generatedAt,
    pendingRemoval, setPendingRemoval, handleCandidateSelect,
    handleConfirmRemoveWatchlist, mutatingWatchlist,
    addPopoverOpen, setAddPopoverOpen, setWatchlistSymbolDraft,
    setWatchlistNameDraft, handleAddWatchlist,
    watchlistSymbolDraft, watchlistNameDraft,
    selectedSymbol, view, canMutateWatchlist, watchlistMutationSymbol, handleRefreshWatchlist,
  } = input;

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


  return [
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


}
