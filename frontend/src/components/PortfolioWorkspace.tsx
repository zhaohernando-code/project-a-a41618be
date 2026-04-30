import { Alert, Card, Col, Descriptions, Empty, List, Row, Space, Table, Tag, Typography } from "antd";
const { Paragraph, Text } = Typography;
import type { PortfolioSummaryView } from "../types";
import { NavSparkline } from "./NavSparkline";
import { formatNumber, formatPercent, formatSignedNumber, statusColor, simulationAdviceActionLabel, simulationAdvicePolicyLabel } from "../utils/format";
import { portfolioTrackLabel, portfolioTrackSummary, displayBenchmarkLabel, validationStatusLabel, sanitizeDisplayText, compactValidationNote, formatMarketFreshness } from "../utils/labels";
import { formatDate } from "../utils/format";



export function PortfolioWorkspace({ portfolio }: { portfolio: PortfolioSummaryView }) {
  const benchmarkContext = portfolio.benchmark_context;
  const benchmarkVerified = benchmarkContext.status === "verified";
  const validationVerified = portfolio.validation_status === "verified";
  const performance = portfolio.performance;
  const executionPolicy = portfolio.execution_policy;

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
