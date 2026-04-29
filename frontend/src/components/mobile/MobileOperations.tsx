import { CalendarOutlined, FileTextOutlined, LineChartOutlined } from "@ant-design/icons";
import { Alert, Button, Empty, Skeleton, Tag, Typography } from "antd";
import { useState } from "react";
import type { MobileAppShellProps } from "./types";
import { MobileMetric } from "./MobileMetric";
import { formatDate, formatNumber, formatPercent, formatSignedNumber, simulationAdviceActionLabel, simulationAdvicePolicyLabel, valueTone } from "../../utils/format";
import { formatMarketFreshness, operationsValidationDescription, operationsValidationMessage, sanitizeDisplayText, validationStatusLabel } from "../../utils/labels";

const { Text, Title } = Typography;
type TrackKey = "manual" | "model";

export function MobileOperations(props: MobileAppShellProps) {
  const simulation = props.simulation;
  const operations = props.operations;
  const [trackKey, setTrackKey] = useState<TrackKey>("manual");
  const activeTrack = trackKey === "manual" ? simulation?.manual_track : simulation?.model_track;
  const activeHolding = activeTrack?.portfolio.holdings.find((item) => item.quantity > 0) ?? null;
  const activeAdvice = activeHolding
    ? simulation?.model_advices.find((item) => item.symbol === activeHolding.symbol) ?? simulation?.model_advices[0]
    : simulation?.model_advices[0];

  if (props.operationsLoading && !operations && !simulation) {
    return (
      <main className="mobile-page">
        <Skeleton active paragraph={{ rows: 10 }} />
      </main>
    );
  }

  return (
    <main className="mobile-page mobile-page-operations">
      <header className="mobile-page-head">
        <div>
          <Title level={2}>复盘</Title>
          <Text>
            <span className="mobile-live-dot" />
            {simulation ? `${simulation.session.status_label} · ${formatMarketFreshness(simulation.session.data_latency_seconds, simulation.session.last_market_data_at, true)}` : "等待工作区数据"}
          </Text>
        </div>
        <Button className="mobile-icon-button" shape="circle" icon={<CalendarOutlined />} loading={props.operationsLoading} onClick={() => void props.onLoadOperations()} />
      </header>

      {props.operationsError ? (
        <Alert
          className="mobile-inline-alert"
          type="warning"
          showIcon
          message="运营复盘工作区加载失败"
          description={props.operationsError}
          action={<Button size="small" onClick={() => void props.onLoadOperations()}>重试</Button>}
        />
      ) : null}

      {simulation ? (
        <>
          <section className="mobile-panel-card mobile-review-summary">
            <MobileMetric label="当前净值" value={formatNumber(activeTrack?.portfolio.net_asset_value)} />
            <MobileMetric label="今日盈亏" value={formatSignedNumber(activeTrack?.portfolio.unrealized_pnl)} tone={valueTone(activeTrack?.portfolio.unrealized_pnl)} />
            <MobileMetric label="仓位" value={formatPercent(activeTrack?.portfolio.invested_ratio)} />
          </section>

          <div className="mobile-segmented mobile-track-switch">
            <button type="button" className={trackKey === "manual" ? "active" : ""} onClick={() => setTrackKey("manual")}>用户轨道</button>
            <button type="button" className={trackKey === "model" ? "active" : ""} onClick={() => setTrackKey("model")}>模型轨道</button>
          </div>

          <TrackPanel title={activeTrack?.label ?? "轨道"} track={activeTrack} holding={activeHolding} onOpenStock={props.onSelectSymbol} />

          <section className="mobile-panel-card mobile-advice-card">
            <div className="mobile-section-head">
              <div>
                <Title level={4}>模型建议</Title>
                <Text>{activeAdvice ? `${activeAdvice.stock_name} · ${activeAdvice.symbol}` : "暂无建议"}</Text>
              </div>
              {activeAdvice ? <Tag>{simulationAdviceActionLabel(activeAdvice)}</Tag> : null}
            </div>
            <div className="mobile-card-list">
              {activeAdvice ? (
                <article className="mobile-mini-card mobile-flat-card">
                  <p>{sanitizeDisplayText(activeAdvice.reason)}</p>
                  <div className="mobile-fact-list mobile-fact-grid">
                    <MobileMetric label={simulationAdvicePolicyLabel(activeAdvice)} value={activeAdvice.confidence_label} />
                    <MobileMetric label="参考价" value={formatNumber(activeAdvice.reference_price)} />
                    <MobileMetric label="目标权重" value={formatPercent(activeAdvice.target_weight)} />
                  </div>
                </article>
              ) : <Empty description="暂无模型建议" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
            </div>
          </section>

          <section className="mobile-panel-card mobile-key-points">
            <Title level={4}>关键记录</Title>
            <div className="mobile-timeline">
              {simulation.timeline.slice(0, 4).map((event) => (
                <article key={event.event_key}>
                  <span>{formatDate(event.happened_at)}</span>
                  <strong>{event.title}</strong>
                  <p>{sanitizeDisplayText(event.detail)}</p>
                </article>
              ))}
            </div>
          </section>

          <section className="mobile-action-dock" aria-label="复盘快捷动作">
            <Button danger disabled={!activeHolding}>买入</Button>
            <Button disabled={!activeHolding}>卖出</Button>
            <Button type="primary" onClick={() => activeHolding && props.onSelectSymbol(activeHolding.symbol, "stock")} disabled={!activeHolding}>
              记录判断
            </Button>
          </section>
        </>
      ) : (
        <section className="mobile-panel-card">
          <Empty description="当前没有双轨模拟数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        </section>
      )}

      {operations?.overview.research_validation.note ? (
        <Alert
          className="mobile-inline-alert"
          type="warning"
          showIcon
          message={operationsValidationMessage(operations.overview.research_validation.status)}
          description={operationsValidationDescription(operations.overview.research_validation)}
        />
      ) : null}
      {operations ? (
        <section className="mobile-panel-card">
          <Title level={4}>复盘状态</Title>
          <div className="mobile-fact-list">
            <MobileMetric label="验证状态" value={validationStatusLabel(operations.overview.research_validation.status)} />
            <MobileMetric label="规则通过率" value={formatPercent(operations.overview.launch_readiness.rule_pass_rate)} />
            <MobileMetric label="刷新状态" value={formatMarketFreshness(operations.data_latency_seconds, operations.last_market_data_at, true)} />
          </div>
        </section>
      ) : null}
    </main>
  );
}

function TrackPanel({
  title,
  track,
  holding,
  onOpenStock,
}: {
  title: string;
  track: NonNullable<MobileAppShellProps["simulation"]>["manual_track"] | undefined;
  holding: NonNullable<MobileAppShellProps["simulation"]>["manual_track"]["portfolio"]["holdings"][number] | null;
  onOpenStock: MobileAppShellProps["onSelectSymbol"];
}) {
  return (
    <section className="mobile-panel-card mobile-holding-card">
      <div className="mobile-section-head">
        <div>
          <Title level={4}>{title}</Title>
          <Text>{track?.portfolio.strategy_label ?? "等待轨道数据"}</Text>
        </div>
        <strong className={`value-${valueTone(track?.portfolio.total_return)}`}>{formatPercent(track?.portfolio.total_return)}</strong>
      </div>
      {holding ? (
        <article className="mobile-position-card">
          <button type="button" className="mobile-position-head" onClick={() => onOpenStock(holding.symbol, "stock")}>
            <span className="mobile-position-avatar">{holding.name.slice(0, 1)}</span>
            <span>
              <strong>{holding.name}</strong>
              <em>{holding.symbol} · {formatNumber(holding.quantity)} 股</em>
            </span>
            <span className="mobile-position-price">
              <strong>{formatNumber(holding.last_price)}</strong>
              <em className={`value-${valueTone(holding.today_pnl_pct)}`}>{formatPercent(holding.today_pnl_pct)}</em>
            </span>
          </button>
          <div className="mobile-metric-grid">
            <MobileMetric label="数量" value={formatNumber(holding.quantity)} />
            <MobileMetric label="成本" value={formatNumber(holding.avg_cost)} />
            <MobileMetric label="浮动盈亏" value={formatSignedNumber(holding.total_pnl)} tone={valueTone(holding.total_pnl)} />
          </div>
          <div className="mobile-position-actions">
            <Button icon={<LineChartOutlined />} onClick={() => onOpenStock(holding.symbol, "stock")}>K线</Button>
            <Button icon={<FileTextOutlined />} onClick={() => onOpenStock(holding.symbol, "stock")}>报告</Button>
            <Button onClick={() => onOpenStock(holding.symbol, "stock")}>操作</Button>
          </div>
        </article>
      ) : <Empty description="暂无持仓" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
    </section>
  );
}
