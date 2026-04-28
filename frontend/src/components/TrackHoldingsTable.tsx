import { Button, Table, Tag } from "antd";
const { Text } = Typography;
import type { ColumnsType } from "antd/es/table";
import type { CandidateWorkspaceRow, PortfolioHoldingView, SimulationModelAdviceView, SimulationTrackStateView } from "../types";
import { formatNumber, formatSignedNumber, formatPercent, directionColor, valueTone } from "../utils/format";
import { sanitizeDisplayText } from "../utils/labels";

export function TrackHoldingsTable({
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

