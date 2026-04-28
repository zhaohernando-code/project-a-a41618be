import { Button, Descriptions, Space, Tag } from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import type { CandidateWorkspaceRow, SimulationModelAdviceView, SimulationTrackStateView } from "../types";
import { KlinePanel } from "./KlinePanel";
import { TrackHoldingsTable } from "./TrackHoldingsTable";
import { formatNumber, formatPercent, formatSignedNumber, statusColor, simulationAdviceActionLabel, simulationAdvicePolicyLabel } from "../utils/format";
import { sanitizeDisplayText } from "../utils/labels";

export function SimulationTrackCard({
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

