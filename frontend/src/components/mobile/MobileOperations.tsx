import { BarChartOutlined, ReloadOutlined } from "@ant-design/icons";
import { Alert, Button, Empty, Skeleton, Space, Tag, Typography } from "antd";
import type { MobileAppShellProps } from "./types";
import { MobileMetric } from "./MobileMetric";
import { KlinePanel } from "../KlinePanel";
import { formatDate, formatNumber, formatPercent, formatSignedNumber, simulationAdviceActionLabel, simulationAdvicePolicyLabel, valueTone } from "../../utils/format";
import { formatMarketFreshness, operationsValidationDescription, operationsValidationMessage, sanitizeDisplayText, validationStatusLabel } from "../../utils/labels";

const { Text, Title } = Typography;

export function MobileOperations(props: MobileAppShellProps) {
  const simulation = props.simulation;
  const operations = props.operations;

  if (props.operationsLoading && !operations && !simulation) {
    return (
      <main className="mobile-page">
        <Skeleton active paragraph={{ rows: 10 }} />
      </main>
    );
  }

  return (
    <main className="mobile-page">
      <header className="mobile-page-head">
        <div>
          <Text className="mobile-kicker">运营复盘</Text>
          <Title level={2}>双轨模拟</Title>
          <Text>{simulation?.session.status_label ?? "等待工作区数据"}</Text>
        </div>
        <Button shape="circle" icon={<ReloadOutlined />} loading={props.operationsLoading} onClick={() => void props.onLoadOperations()} />
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
          <section className="mobile-hero-card">
            <div className="mobile-focus-title">
              <div>
                <Text className="mobile-card-kicker">当前模拟</Text>
                <Title level={3}>{simulation.session.status_label}</Title>
              </div>
              <Tag color="blue">{simulation.session.market_data_timeframe}</Tag>
            </div>
            <div className="mobile-metric-grid">
              <MobileMetric label="步数" value={simulation.session.current_step} />
              <MobileMetric label="股票池" value={`${simulation.session.watch_symbols.length} 只`} />
              <MobileMetric label="最新行情" value={formatMarketFreshness(simulation.session.data_latency_seconds, simulation.session.last_market_data_at, true)} />
            </div>
            <Space wrap className="mobile-chip-row">
              <Tag>{`初始资金 ${formatNumber(simulation.session.initial_cash)}`}</Tag>
              <Tag>{simulation.session.fill_rule_label}</Tag>
              <Tag>{`重启 ${simulation.session.restart_count} 次`}</Tag>
            </Space>
          </section>

          <section className="mobile-panel-card">
            <div className="mobile-section-head">
              <div>
                <Title level={4}>焦点 K 线</Title>
                <Text>{simulation.kline.stock_name ?? simulation.kline.symbol ?? "--"}</Text>
              </div>
              <BarChartOutlined />
            </div>
            <KlinePanel
              title={`${simulation.kline.stock_name ?? simulation.kline.symbol ?? "焦点标的"} K 线`}
              points={simulation.kline.points}
              lastUpdated={simulation.kline.last_updated}
              stockName={simulation.kline.stock_name ?? simulation.kline.symbol}
              isMobile
            />
          </section>

          <TrackPanel title="用户轨道" track={simulation.manual_track} onOpenStock={props.onSelectSymbol} />
          <TrackPanel title="模型轨道" track={simulation.model_track} onOpenStock={props.onSelectSymbol} />

          <section className="mobile-panel-card">
            <Title level={4}>模型建议</Title>
            <div className="mobile-card-list">
              {simulation.model_advices.length > 0 ? simulation.model_advices.slice(0, 6).map((advice) => (
                <article key={advice.symbol} className="mobile-mini-card">
                  <div className="mobile-mini-head">
                    <div>
                      <strong>{advice.stock_name}</strong>
                      <span>{advice.symbol}</span>
                    </div>
                    <Tag>{simulationAdviceActionLabel(advice)}</Tag>
                  </div>
                  <p>{sanitizeDisplayText(advice.reason)}</p>
                  <div className="mobile-fact-list">
                    <MobileMetric label={simulationAdvicePolicyLabel(advice)} value={advice.confidence_label} />
                    <MobileMetric label="参考价" value={formatNumber(advice.reference_price)} />
                    <MobileMetric label="目标权重" value={formatPercent(advice.target_weight)} />
                  </div>
                </article>
              )) : <Empty description="暂无模型建议" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
            </div>
          </section>

          <section className="mobile-panel-card">
            <Title level={4}>最近事件</Title>
            <div className="mobile-timeline">
              {simulation.timeline.slice(0, 8).map((event) => (
                <article key={event.event_key}>
                  <span>{formatDate(event.happened_at)}</span>
                  <strong>{event.title}</strong>
                  <p>{sanitizeDisplayText(event.detail)}</p>
                </article>
              ))}
            </div>
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
  onOpenStock,
}: {
  title: string;
  track: NonNullable<MobileAppShellProps["simulation"]>["manual_track"];
  onOpenStock: MobileAppShellProps["onSelectSymbol"];
}) {
  const holdings = track.portfolio.holdings.filter((item) => item.quantity > 0);
  return (
    <section className="mobile-panel-card">
      <div className="mobile-section-head">
        <div>
          <Title level={4}>{title}</Title>
          <Text>{track.portfolio.strategy_label}</Text>
        </div>
        <strong className={`value-${valueTone(track.portfolio.total_return)}`}>{formatPercent(track.portfolio.total_return)}</strong>
      </div>
      <div className="mobile-metric-grid">
        <MobileMetric label="净值" value={formatNumber(track.portfolio.net_asset_value)} />
        <MobileMetric label="现金" value={formatNumber(track.portfolio.available_cash)} />
        <MobileMetric label="仓位" value={formatPercent(track.portfolio.invested_ratio)} />
      </div>
      <div className="mobile-card-list">
        {holdings.length > 0 ? holdings.map((holding) => (
          <button key={holding.symbol} type="button" className="mobile-holding-row" onClick={() => onOpenStock(holding.symbol, "stock")}>
            <div>
              <strong>{holding.name}</strong>
              <span>{`${holding.symbol} · ${formatNumber(holding.quantity)} 股`}</span>
            </div>
            <div>
              <strong>{formatNumber(holding.market_value)}</strong>
              <span className={`value-${valueTone(holding.total_pnl)}`}>{formatSignedNumber(holding.total_pnl)}</span>
            </div>
          </button>
        )) : <Empty description="暂无持仓" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
      </div>
    </section>
  );
}
