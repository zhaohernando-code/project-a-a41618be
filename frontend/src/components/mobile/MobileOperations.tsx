import { ArrowLeftOutlined, DownOutlined, ReloadOutlined, UpOutlined } from "@ant-design/icons";
import { Alert, Button, Empty, Skeleton, Tag } from "antd";
import { useMemo, useState, type ReactNode } from "react";
import type { PortfolioOrderAuditView, SimulationTimelineEventView } from "../../types";
import { buildTrackTableRows, type TrackTableRow } from "../../utils/data";
import {
  formatDate,
  formatNumber,
  formatPercent,
  formatSignedNumber,
  simulationAdviceActionLabel,
  valueTone,
} from "../../utils/format";
import { sanitizeDisplayText } from "../../utils/labels";
import type { MobileAppShellProps } from "./types";

type TrackKey = "manual" | "model";
type MobileOperationRecord = {
  key: string;
  happened_at: string;
  title: string;
  detail: string;
};

export function MobileOperations(props: MobileAppShellProps) {
  const simulation = props.simulation;
  const [trackKey, setTrackKey] = useState<TrackKey>("manual");
  const [adviceOpenSymbol, setAdviceOpenSymbol] = useState<string | null>(null);
  const [recordsOpenSymbol, setRecordsOpenSymbol] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const activeTrack = trackKey === "manual" ? simulation?.manual_track : simulation?.model_track;
  const isManualTrack = trackKey === "manual";

  const symbolNameMap = useMemo(() => {
    const map = new Map<string, string>();
    props.candidateRows.forEach((item) => map.set(item.symbol, item.name));
    simulation?.model_advices.forEach((item) => map.set(item.symbol, item.stock_name));
    simulation?.manual_track.portfolio.holdings.forEach((item) => map.set(item.symbol, item.name));
    simulation?.model_track.portfolio.holdings.forEach((item) => map.set(item.symbol, item.name));
    return map;
  }, [props.candidateRows, simulation]);

  const focusSymbols = useMemo(() => {
    const symbols: string[] = [];
    const push = (symbol?: string | null) => {
      if (symbol && !symbols.includes(symbol)) symbols.push(symbol);
    };
    props.candidateRows.forEach((item) => push(item.symbol));
    simulation?.session.watch_symbols.forEach(push);
    simulation?.configuration.watch_symbols.forEach(push);
    simulation?.manual_track.portfolio.holdings.forEach((item) => push(item.symbol));
    simulation?.model_track.portfolio.holdings.forEach((item) => push(item.symbol));
    return symbols;
  }, [props.candidateRows, simulation]);

  const rows = useMemo(() => {
    if (!activeTrack) return [];
    return buildTrackTableRows(
      activeTrack,
      focusSymbols,
      props.candidateRows,
      symbolNameMap,
      simulation?.model_advices ?? [],
    );
  }, [activeTrack, focusSymbols, props.candidateRows, simulation?.model_advices, symbolNameMap]);

  const historyEvents = useMemo(() => {
    if (!simulation || !activeTrack) return [];
    return buildTrackRecords({
      timeline: simulation.timeline,
      orders: activeTrack.portfolio.recent_orders,
      trackKey,
      trackLabel: activeTrack.label,
    });
  }, [activeTrack, simulation, trackKey]);

  if (props.operationsLoading && !props.operations && !simulation) {
    return (
      <main className="mobile-page">
        <Skeleton active paragraph={{ rows: 10 }} />
      </main>
    );
  }

  return (
    <main className="mobile-page mobile-page-operations">
      <header className="mobile-app-top-bar">
        <span aria-hidden="true" />
        <strong>复盘</strong>
        <Button className="mobile-icon-button" type="text" icon={<ReloadOutlined />} loading={props.operationsLoading} onClick={() => void props.onLoadOperations()} />
      </header>

      <div className="mobile-segmented mobile-track-switch mobile-track-switch-top">
        <button type="button" className={trackKey === "manual" ? "active" : ""} onClick={() => setTrackKey("manual")}>用户轨道</button>
        <button type="button" className={trackKey === "model" ? "active" : ""} onClick={() => setTrackKey("model")}>模型轨道</button>
      </div>

      {props.operationsError ? (
        <Alert
          className="mobile-inline-alert"
          type="warning"
          showIcon
          message="复盘数据加载失败"
          description={props.operationsError}
          action={<Button size="small" onClick={() => void props.onLoadOperations()}>重试</Button>}
        />
      ) : null}

      {simulation && activeTrack ? (
        <>
          <section className="mobile-review-summary mobile-review-summary-flat">
            <TrackMetric label="净值" value={formatNumber(activeTrack.portfolio.net_asset_value)} />
            <TrackMetric label="今日盈亏" value={formatSignedNumber(activeTrack.portfolio.unrealized_pnl)} tone={valueTone(activeTrack.portfolio.unrealized_pnl)} />
            <TrackMetric label="仓位" value={formatPercent(activeTrack.portfolio.invested_ratio)} />
          </section>

          <section className="mobile-operation-list" aria-label="关注股票复盘">
            {rows.length > 0 ? (
              rows.map((row) => {
                const advice = simulation.model_advices.find((item) => item.symbol === row.symbol) ?? null;
                const records = buildStockRecords({
                  symbol: row.symbol,
                  timeline: simulation.timeline,
                  orders: activeTrack.portfolio.recent_orders,
                  trackKey,
                  trackLabel: activeTrack.label,
                });
                const isAdviceOpen = adviceOpenSymbol === row.symbol;
                const areRecordsOpen = recordsOpenSymbol === row.symbol;
                return (
                  <OperationStockCard
                    key={`${trackKey}-${row.symbol}`}
                    row={row}
                    advice={advice}
                    records={records}
                    isManualTrack={isManualTrack}
                    isAdviceOpen={isAdviceOpen}
                    areRecordsOpen={areRecordsOpen}
                    onToggleAdvice={() => setAdviceOpenSymbol(isAdviceOpen ? null : row.symbol)}
                    onToggleRecords={() => setRecordsOpenSymbol(areRecordsOpen ? null : row.symbol)}
                    onOpenStock={() => props.onSelectSymbol(row.symbol, "stock")}
                    onOpenOrder={(side) => props.onOpenManualOrder?.(row.symbol, side)}
                  />
                );
              })
            ) : (
              <section className="mobile-panel-card">
                <Empty description="当前没有可展示的关注股票" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              </section>
            )}
          </section>

          <Button className="mobile-history-entry" type="primary" block onClick={() => setHistoryOpen(true)}>
            查看历史
          </Button>
        </>
      ) : (
        <section className="mobile-panel-card">
          <Empty description="当前没有双轨模拟数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        </section>
      )}

      {historyOpen ? (
        <HistoryOverlay
          title={trackKey === "manual" ? "用户记录" : "模型记录"}
          events={historyEvents}
          onBack={() => setHistoryOpen(false)}
        />
      ) : null}
    </main>
  );
}

function OperationStockCard({
  row,
  advice,
  records,
  isManualTrack,
  isAdviceOpen,
  areRecordsOpen,
  onToggleAdvice,
  onToggleRecords,
  onOpenStock,
  onOpenOrder,
}: {
  row: TrackTableRow;
  advice: NonNullable<MobileAppShellProps["simulation"]>["model_advices"][number] | null;
  records: MobileOperationRecord[];
  isManualTrack: boolean;
  isAdviceOpen: boolean;
  areRecordsOpen: boolean;
  onToggleAdvice: () => void;
  onToggleRecords: () => void;
  onOpenStock: () => void;
  onOpenOrder: (side: "buy" | "sell") => void;
}) {
  const todayTone = valueTone(row.today_pnl_amount || row.today_pnl_pct);
  const totalTone = valueTone(row.total_pnl || row.holding_pnl_pct);

  return (
    <article className="mobile-operation-card">
      <div className="mobile-operation-card-head">
        <button type="button" onClick={onOpenStock}>
          <strong>{row.name}</strong>
          <span>{row.symbol}</span>
        </button>
        <Tag className="mobile-operation-tag">{row.quantity > 0 ? "持仓中" : "观察中"}</Tag>
      </div>

      <div className="mobile-operation-metrics">
        <OperationMetric label="数量" value={`${formatNumber(row.quantity)} 股`} />
        <OperationMetric label="成本/现价" values={[formatNumber(row.avg_cost || null), formatNumber(row.last_price || null)]} />
        <OperationMetric label="当日盈亏" values={[formatSignedNumber(row.today_pnl_amount), formatPercent(row.today_pnl_pct)]} tone={todayTone} />
        <OperationMetric label="总盈亏" values={[formatSignedNumber(row.total_pnl), formatPercent(row.holding_pnl_pct)]} tone={totalTone} />
      </div>

      <div className="mobile-operation-actions">
        {isManualTrack ? (
          <>
            <Button onClick={() => onOpenOrder("buy")}>买入</Button>
            <Button onClick={() => onOpenOrder("sell")}>卖出</Button>
          </>
        ) : null}
        <Button onClick={onOpenStock}>详情</Button>
        <Button onClick={onToggleAdvice}>模型建议</Button>
      </div>

      {isAdviceOpen ? (
        <div className="mobile-operation-advice">
          {advice ? (
            <>
              <div className="mobile-operation-advice-head">
                <strong>{simulationAdviceActionLabel(advice)}</strong>
                <span>{advice.confidence_label}</span>
              </div>
              <p>{sanitizeDisplayText(advice.reason)}</p>
              <div className="mobile-operation-advice-meta">
                <span>参考价 {formatNumber(advice.reference_price)}</span>
                <span>目标 {formatPercent(advice.target_weight)}</span>
              </div>
            </>
          ) : (
            <p>暂无模型建议。</p>
          )}
        </div>
      ) : null}

      <button type="button" className="mobile-record-toggle" onClick={onToggleRecords}>
        <span>关键记录</span>
        {areRecordsOpen ? <UpOutlined /> : <DownOutlined />}
      </button>
      {areRecordsOpen ? <TimelineList events={records} emptyText="暂无关键记录" /> : null}
    </article>
  );
}

function OperationMetric({
  label,
  value,
  values,
  tone = "neutral",
}: {
  label: string;
  value?: string;
  values?: string[];
  tone?: "positive" | "negative" | "neutral";
}) {
  const content: ReactNode = values ? (
    values.map((item, index) => <em key={`${label}-${index}`}>{item}</em>)
  ) : value;

  return (
    <div className="mobile-operation-metric">
      <span>{label}</span>
      <strong className={`value-${tone}`}>{content}</strong>
    </div>
  );
}

function TrackMetric({ label, value, tone = "neutral" }: { label: string; value: string; tone?: "positive" | "negative" | "neutral" }) {
  return (
    <div>
      <span>{label}</span>
      <strong className={`value-${tone}`}>{value}</strong>
    </div>
  );
}

function HistoryOverlay({ title, events, onBack }: { title: string; events: MobileOperationRecord[]; onBack: () => void }) {
  return (
    <section className="mobile-history-overlay" aria-label={title}>
      <header className="mobile-app-top-bar">
        <Button className="mobile-icon-button" type="text" icon={<ArrowLeftOutlined />} onClick={onBack} />
        <strong>{title}</strong>
        <span aria-hidden="true" />
      </header>
      <TimelineList events={events} emptyText="当前轨道暂无历史记录" />
    </section>
  );
}

function TimelineList({ events, emptyText }: { events: MobileOperationRecord[]; emptyText: string }) {
  if (events.length === 0) {
    return <Empty className="mobile-empty-tight" description={emptyText} image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  return (
    <div className="mobile-timeline mobile-operation-timeline">
      {events.map((event) => (
        <article key={event.key}>
          <span>{formatDate(event.happened_at)}</span>
          <strong>{event.title}</strong>
          <p>{sanitizeDisplayText(event.detail)}</p>
        </article>
      ))}
    </div>
  );
}

function eventBelongsToTrack(event: SimulationTimelineEventView, trackKey: TrackKey, trackLabel: string) {
  return event.track === trackKey || event.track_label === trackLabel;
}

function isMeaningfulHistoryEvent(event: SimulationTimelineEventView) {
  const actionSummary = String(event.payload?.action_summary ?? "");
  if (event.event_type === "model_decision" && !event.symbol && (event.title.includes("观望") || actionSummary === "持有")) {
    return false;
  }
  return true;
}

function buildStockRecords({
  symbol,
  timeline,
  orders,
  trackKey,
  trackLabel,
}: {
  symbol: string;
  timeline: SimulationTimelineEventView[];
  orders: PortfolioOrderAuditView[];
  trackKey: TrackKey;
  trackLabel: string;
}): MobileOperationRecord[] {
  return sortRecords([
    ...orders.filter((order) => order.symbol === symbol).map((order) => orderToRecord(order, trackKey)),
    ...timeline
      .filter((event) => (
        event.symbol === symbol
        && event.event_type !== "order_filled"
        && eventBelongsToTrack(event, trackKey, trackLabel)
        && isMeaningfulHistoryEvent(event)
      ))
      .map(timelineToRecord),
  ]).slice(0, 4);
}

function buildTrackRecords({
  timeline,
  orders,
  trackKey,
  trackLabel,
}: {
  timeline: SimulationTimelineEventView[];
  orders: PortfolioOrderAuditView[];
  trackKey: TrackKey;
  trackLabel: string;
}): MobileOperationRecord[] {
  return sortRecords([
    ...orders.map((order) => orderToRecord(order, trackKey)),
    ...timeline
      .filter((event) => (
        event.event_type !== "order_filled"
        && eventBelongsToTrack(event, trackKey, trackLabel)
        && isMeaningfulHistoryEvent(event)
      ))
      .map(timelineToRecord),
  ]);
}

function sortRecords(records: MobileOperationRecord[]) {
  return [...records].sort((left, right) => new Date(right.happened_at).getTime() - new Date(left.happened_at).getTime());
}

function timelineToRecord(event: SimulationTimelineEventView): MobileOperationRecord {
  return {
    key: event.event_key,
    happened_at: event.happened_at,
    title: event.title,
    detail: sanitizeDisplayText(event.detail),
  };
}

function orderToRecord(order: PortfolioOrderAuditView, trackKey: TrackKey): MobileOperationRecord {
  const sideLabel = order.side === "sell" ? "卖出" : "买入";
  const trackLabel = trackKey === "manual" ? "用户" : "模型";
  const price = order.avg_fill_price ? `，成交价 ${formatNumber(order.avg_fill_price)}` : "";
  return {
    key: `order-${trackKey}-${order.order_key}`,
    happened_at: order.requested_at,
    title: `${trackLabel}${sideLabel}已成交`,
    detail: `${order.stock_name} ${sideLabel} ${formatNumber(order.quantity)} 股${price}。`,
  };
}
