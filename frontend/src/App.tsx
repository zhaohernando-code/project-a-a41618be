import {
  ApiOutlined,
  BarChartOutlined,
  BranchesOutlined,
  DatabaseOutlined,
  LineChartOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  StockOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Empty,
  Input,
  List,
  Row,
  Segmented,
  Select,
  Skeleton,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
  Timeline,
  Typography,
  message,
} from "antd";
import { startTransition, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import type {
  CandidateItemView,
  DataMode,
  DataSourceInfo,
  GlossaryEntryView,
  OperationsDashboardResponse,
  PortfolioNavPointView,
  PortfolioSummaryView,
  PricePointView,
  RecommendationReplayView,
  StockDashboardResponse,
} from "./types";

const { Paragraph, Text, Title } = Typography;
const { TextArea } = Input;

type ViewMode = "candidates" | "stock" | "operations";

const numberFormatter = new Intl.NumberFormat("zh-CN", {
  maximumFractionDigits: 2,
});

const percentFormatter = new Intl.NumberFormat("zh-CN", {
  style: "percent",
  maximumFractionDigits: 1,
  signDisplay: "always",
});

const directionLabels: Record<string, string> = {
  buy: "偏积极",
  watch: "继续观察",
  reduce: "偏谨慎",
  risk_alert: "风险提示",
};

const factorLabels: Record<string, string> = {
  price_baseline: "价格基线",
  news_event: "新闻事件",
  llm_assessment: "LLM 评估",
  fusion: "融合评分",
};

function formatDate(value?: string | null): string {
  if (!value) return "未提供";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatNumber(value?: number | null): string {
  if (value === null || value === undefined) return "--";
  return numberFormatter.format(value);
}

function formatPercent(value?: number | null): string {
  if (value === null || value === undefined) return "--";
  return percentFormatter.format(value);
}

function directionColor(direction: string): string {
  if (direction === "buy") return "green";
  if (direction === "watch") return "blue";
  if (direction === "reduce") return "orange";
  if (direction === "risk_alert") return "red";
  return "default";
}

function statusColor(status: string): string {
  if (["pass", "hit", "closed_beta_ready", "online"].includes(status)) return "green";
  if (["warn", "hold", "pending", "offline"].includes(status)) return "gold";
  if (["fail", "miss", "risk_alert"].includes(status)) return "red";
  return "default";
}

function buildInitialSourceInfo(): DataSourceInfo {
  const runtimeConfig = api.getRuntimeConfig();
  const preferredMode = runtimeConfig.preferredMode;
  return {
    mode: preferredMode,
    preferredMode,
    label: preferredMode === "online" ? "在线 API" : "离线快照",
    detail:
      preferredMode === "online"
        ? "正在尝试连接在线接口。"
        : "当前使用仓库内置离线快照，页面可在无 API 的静态部署环境直接运行。",
    apiBase: runtimeConfig.apiBase,
    betaHeaderName: runtimeConfig.betaHeaderName,
    betaKeyPresent: Boolean(api.getBetaAccessKey()),
    snapshotGeneratedAt: runtimeConfig.snapshotGeneratedAt,
    fallbackReason: null,
  };
}

function mergeSourceInfo(primary: DataSourceInfo, secondary: DataSourceInfo): DataSourceInfo {
  const preferOffline = primary.mode === "offline" || secondary.mode === "offline";
  const base = preferOffline
    ? (primary.mode === "offline" ? primary : secondary)
    : primary;
  const fallbackReasons = [primary.fallbackReason, secondary.fallbackReason].filter(Boolean).join("；");
  return {
    ...base,
    fallbackReason: fallbackReasons || null,
  };
}

function PriceSparkline({ points }: { points: PricePointView[] }) {
  if (points.length === 0) {
    return <Empty description="暂无价格轨迹" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  const width = 760;
  const height = 220;
  const values = points.map((point) => point.close_price);
  const volumes = points.map((point) => point.volume);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const volumeMax = Math.max(...volumes);
  const xStep = points.length > 1 ? width / (points.length - 1) : width;
  const scaleY = (value: number) =>
    max === min ? height / 2 : height - ((value - min) / (max - min)) * (height - 44) - 22;

  const linePath = points
    .map((point, index) => `${index === 0 ? "M" : "L"} ${index * xStep} ${scaleY(point.close_price)}`)
    .join(" ");
  const areaPath = `${linePath} L ${width} ${height} L 0 ${height} Z`;

  return (
    <svg className="sparkline" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
      <defs>
        <linearGradient id="price-area-fill" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="rgba(10, 91, 255, 0.26)" />
          <stop offset="100%" stopColor="rgba(10, 91, 255, 0.02)" />
        </linearGradient>
      </defs>
      {points.map((point, index) => {
        const barHeight = volumeMax === 0 ? 0 : (point.volume / volumeMax) * 44;
        return (
          <rect
            key={`${point.observed_at}-volume`}
            className="sparkline-volume"
            x={index * xStep - 3}
            y={height - barHeight}
            width={6}
            height={barHeight}
            rx={3}
          />
        );
      })}
      <path className="sparkline-area" d={areaPath} />
      <path className="sparkline-line" d={linePath} />
      <circle
        className="sparkline-dot"
        cx={(points.length - 1) * xStep}
        cy={scaleY(points[points.length - 1].close_price)}
        r={5}
      />
    </svg>
  );
}

function NavSparkline({ points }: { points: PortfolioNavPointView[] }) {
  if (points.length === 0) {
    return <Empty description="暂无净值轨迹" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  const width = 760;
  const height = 180;
  const navValues = points.map((point) => point.nav);
  const benchmarkValues = points.map((point) => point.benchmark_nav);
  const min = Math.min(...navValues, ...benchmarkValues);
  const max = Math.max(...navValues, ...benchmarkValues);
  const xStep = points.length > 1 ? width / (points.length - 1) : width;
  const scaleY = (value: number) =>
    max === min ? height / 2 : height - ((value - min) / (max - min)) * (height - 32) - 16;
  const navPath = points.map((point, index) => `${index === 0 ? "M" : "L"} ${index * xStep} ${scaleY(point.nav)}`).join(" ");
  const benchmarkPath = points
    .map((point, index) => `${index === 0 ? "M" : "L"} ${index * xStep} ${scaleY(point.benchmark_nav)}`)
    .join(" ");

  return (
    <svg className="sparkline nav-sparkline" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
      <path className="nav-benchmark-line" d={benchmarkPath} />
      <path className="nav-line" d={navPath} />
    </svg>
  );
}

function PortfolioWorkspace({ portfolio }: { portfolio: PortfolioSummaryView }) {
  return (
    <div className="portfolio-workspace">
      <Space wrap className="portfolio-badges">
        <Tag color="blue">{portfolio.mode_label}</Tag>
        <Tag color={statusColor(portfolio.total_return >= 0 ? "pass" : "warn")}>
          组合 {formatPercent(portfolio.total_return)}
        </Tag>
        <Tag color={statusColor(portfolio.excess_return >= 0 ? "pass" : "warn")}>
          超额 {formatPercent(portfolio.excess_return)}
        </Tag>
        <Tag color={statusColor(portfolio.max_drawdown > -0.12 ? "pass" : "warn")}>
          最大回撤 {formatPercent(portfolio.max_drawdown)}
        </Tag>
      </Space>

      <Paragraph className="panel-description">{portfolio.strategy_summary}</Paragraph>

      <div className="chart-shell compact-chart">
        <NavSparkline points={portfolio.nav_history} />
      </div>

      <Descriptions size="small" column={{ xs: 1, md: 2, xl: 3 }} className="info-grid">
        <Descriptions.Item label="净值">{formatNumber(portfolio.net_asset_value)}</Descriptions.Item>
        <Descriptions.Item label="可用现金">{formatNumber(portfolio.available_cash)}</Descriptions.Item>
        <Descriptions.Item label="仓位">{formatPercent(portfolio.invested_ratio)}</Descriptions.Item>
        <Descriptions.Item label="基准">{`${portfolio.benchmark_symbol ?? "未配置"} / ${formatPercent(portfolio.benchmark_return)}`}</Descriptions.Item>
        <Descriptions.Item label="已实现/未实现">{`${formatNumber(portfolio.realized_pnl)} / ${formatNumber(portfolio.unrealized_pnl)}`}</Descriptions.Item>
        <Descriptions.Item label="佣金/税费">{`${formatNumber(portfolio.fee_total)} / ${formatNumber(portfolio.tax_total)}`}</Descriptions.Item>
      </Descriptions>

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

function App() {
  const [messageApi, messageContextHolder] = message.useMessage();
  const [view, setView] = useState<ViewMode>("candidates");
  const [preferredMode, setPreferredMode] = useState<DataMode>(() => api.getPreferredMode());
  const [sourceInfo, setSourceInfo] = useState<DataSourceInfo>(() => buildInitialSourceInfo());
  const [candidates, setCandidates] = useState<CandidateItemView[]>([]);
  const [generatedAt, setGeneratedAt] = useState<string | null>(null);
  const [glossary, setGlossary] = useState<GlossaryEntryView[]>([]);
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [dashboard, setDashboard] = useState<StockDashboardResponse | null>(null);
  const [operations, setOperations] = useState<OperationsDashboardResponse | null>(null);
  const [questionDraft, setQuestionDraft] = useState("");
  const [betaKeyDraft, setBetaKeyDraft] = useState(() => api.getBetaAccessKey());
  const [loadingShell, setLoadingShell] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const activeCandidate = useMemo(
    () => candidates.find((item) => item.symbol === selectedSymbol) ?? candidates[0] ?? null,
    [candidates, selectedSymbol],
  );

  const mergedGlossary = useMemo(() => {
    const entries = [...glossary, ...(dashboard?.glossary ?? [])];
    return Array.from(new Map(entries.map((item) => [item.term, item])).values());
  }, [dashboard?.glossary, glossary]);

  async function loadShellData(): Promise<string | null> {
    setLoadingShell(true);
    setError(null);
    try {
      const { data, source } = await api.loadShellData();
      setCandidates(data.candidates.items);
      setGeneratedAt(data.candidates.generated_at);
      setGlossary(data.glossary);
      setSourceInfo(source);
      const nextSymbol = data.candidates.items.find((item) => item.symbol === selectedSymbol)?.symbol
        ?? data.candidates.items[0]?.symbol
        ?? null;
      setSelectedSymbol(nextSymbol);
      return nextSymbol;
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "加载候选股失败。");
      return null;
    } finally {
      setLoadingShell(false);
    }
  }

  async function loadDetailData(symbol: string): Promise<void> {
    setLoadingDetail(true);
    setError(null);
    try {
      const [stockResult, operationsResult] = await Promise.all([
        api.getStockDashboard(symbol),
        api.getOperationsDashboard(symbol),
      ]);
      setDashboard(stockResult.data);
      setOperations(operationsResult.data);
      setQuestionDraft(stockResult.data.follow_up.suggested_questions[0] ?? "");
      setSourceInfo(mergeSourceInfo(stockResult.source, operationsResult.source));
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "加载单票与运营面板失败。");
    } finally {
      setLoadingDetail(false);
    }
  }

  useEffect(() => {
    void loadShellData();
  }, []);

  useEffect(() => {
    if (!selectedSymbol) return;
    let cancelled = false;
    void (async () => {
      await loadDetailData(selectedSymbol);
      if (cancelled) {
        setLoadingDetail(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedSymbol]);

  async function reloadEverything(): Promise<void> {
    const initialSymbol = await loadShellData();
    const resolvedSymbol = initialSymbol ?? selectedSymbol;
    if (resolvedSymbol) {
      await loadDetailData(resolvedSymbol);
    }
  }

  async function handleModeChange(mode: DataMode) {
    api.setPreferredMode(mode);
    setPreferredMode(mode);
    await reloadEverything();
  }

  async function handleApplyBetaKey() {
    api.setBetaAccessKey(betaKeyDraft);
    await reloadEverything();
  }

  async function handleBootstrap() {
    setError(null);
    const { data, source } = await api.bootstrapDemo();
    setSourceInfo(source);
    messageApi.success(
      source.mode === "online"
        ? `已重新初始化 ${data.candidate_count} 条候选股演示数据`
        : `已切换到离线演示快照，当前包含 ${data.candidate_count} 条候选股`,
    );
    await reloadEverything();
  }

  async function handleRefresh() {
    await reloadEverything();
  }

  function handleCandidateSelect(symbol: string, nextView?: ViewMode) {
    startTransition(() => {
      setSelectedSymbol(symbol);
      if (nextView) {
        setView(nextView);
      }
    });
  }

  async function handleCopyPrompt() {
    if (!dashboard) return;
    const prompt = dashboard.follow_up.copy_prompt.replace(
      "<在这里替换成你的追问>",
      questionDraft.trim() || "请解释当前建议最容易失效的条件。",
    );
    try {
      await navigator.clipboard.writeText(prompt);
      messageApi.success("追问包已复制到剪贴板");
    } catch {
      messageApi.error("复制失败，请检查浏览器剪贴板权限");
    }
  }

  const candidateColumns = [
    {
      title: "#",
      dataIndex: "rank",
      width: 64,
    },
    {
      title: "标的",
      key: "stock",
      render: (_: unknown, record: CandidateItemView) => (
        <div className="table-primary-cell">
          <strong>{record.name}</strong>
          <Text type="secondary">{`${record.symbol} · ${record.sector}`}</Text>
        </div>
      ),
    },
    {
      title: "建议",
      key: "signal",
      render: (_: unknown, record: CandidateItemView) => (
        <Space direction="vertical" size={2}>
          <Tag color={directionColor(record.direction)}>{record.direction_label}</Tag>
          <Text type="secondary">{`${record.confidence_label}置信 · ${record.applicable_period}`}</Text>
        </Space>
      ),
    },
    {
      title: "价位/20日",
      key: "price",
      render: (_: unknown, record: CandidateItemView) => (
        <Space direction="vertical" size={2}>
          <Text strong>{formatNumber(record.last_close)}</Text>
          <Text type={record.price_return_20d >= 0 ? "success" : "danger"}>{formatPercent(record.price_return_20d)}</Text>
        </Space>
      ),
    },
    {
      title: "为什么现在",
      dataIndex: "why_now",
      render: (value: string) => <span className="truncate-cell">{value}</span>,
    },
    {
      title: "变化",
      key: "change",
      render: (_: unknown, record: CandidateItemView) => (
        <Space direction="vertical" size={2}>
          <Tag>{record.change_badge}</Tag>
          <Text type="secondary">{record.change_summary}</Text>
        </Space>
      ),
    },
    {
      title: "操作",
      key: "action",
      width: 110,
      render: (_: unknown, record: CandidateItemView) => (
        <Button
          type="link"
          onClick={(event) => {
            event.stopPropagation();
            handleCandidateSelect(record.symbol, "stock");
          }}
        >
          打开
        </Button>
      ),
    },
  ];

  const replayColumns = [
    {
      title: "标的",
      key: "stock",
      render: (_: unknown, record: RecommendationReplayView) => (
        <div className="table-primary-cell">
          <strong>{record.stock_name}</strong>
          <Text type="secondary">{`${record.symbol} · ${record.review_window_days} 交易日`}</Text>
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
      render: (value: string) => <Tag color={statusColor(value)}>{value}</Tag>,
    },
    {
      title: "标的/基准/超额",
      key: "performance",
      render: (_: unknown, record: RecommendationReplayView) => (
        <Space direction="vertical" size={2}>
          <Text>{`标的 ${formatPercent(record.stock_return)}`}</Text>
          <Text type="secondary">{`基准 ${formatPercent(record.benchmark_return)} / 超额 ${formatPercent(record.excess_return)}`}</Text>
        </Space>
      ),
    },
    {
      title: "摘要",
      dataIndex: "summary",
      render: (value: string) => <span className="truncate-cell">{value}</span>,
    },
  ];

  const stockTabItems = dashboard
    ? [
        {
          key: "signals",
          label: "因子与变化",
          children: (
            <Row gutter={[16, 16]}>
              <Col xs={24} xl={12}>
                <Card size="small" title="建议为何成立" className="sub-panel-card">
                  <div className="factor-grid">
                    {Object.entries(dashboard.recommendation.factor_breakdown).map(([key, rawValue]) => {
                      const value = rawValue as {
                        score?: number;
                        direction?: string;
                        drivers?: string[];
                        risks?: string[];
                      };
                      return (
                        <Card key={key} size="small" className="factor-card">
                          <div className="list-item-row">
                            <strong>{factorLabels[key] ?? key}</strong>
                            {value.direction ? <Tag color={directionColor(value.direction)}>{directionLabels[value.direction] ?? value.direction}</Tag> : null}
                          </div>
                          {value.score !== undefined ? (
                            <div className="factor-score">{`分数 ${value.score.toFixed(2)}`}</div>
                          ) : null}
                          <Paragraph className="panel-description">{value.drivers?.[0] ?? "用于汇总价格、事件与降级状态的融合层。"}</Paragraph>
                          {value.risks?.[0] ? <Text type="secondary">{value.risks[0]}</Text> : null}
                        </Card>
                      );
                    })}
                  </div>
                </Card>
              </Col>
              <Col xs={24} xl={12}>
                <Card size="small" title="为什么这次不一样" className="sub-panel-card">
                  <Space wrap className="inline-tags">
                    <Tag>{dashboard.change.change_badge}</Tag>
                    <Tag color={directionColor(dashboard.recommendation.direction)}>{dashboard.hero.direction_label}</Tag>
                  </Space>
                  <Paragraph className="panel-description">{dashboard.change.summary}</Paragraph>
                  <Timeline
                    items={dashboard.change.reasons.map((reason) => ({
                      color: "blue",
                      children: reason,
                    }))}
                  />
                  <Descriptions size="small" column={1}>
                    <Descriptions.Item label="上一版方向">{dashboard.change.previous_direction ?? "无"}</Descriptions.Item>
                    <Descriptions.Item label="上一版时间">{formatDate(dashboard.change.previous_generated_at)}</Descriptions.Item>
                    <Descriptions.Item label="证据状态">
                      <Tag color={dashboard.recommendation.evidence_status === "sufficient" ? "green" : "gold"}>
                        {dashboard.recommendation.evidence_status === "sufficient" ? "证据充足" : "证据降级"}
                      </Tag>
                    </Descriptions.Item>
                  </Descriptions>
                </Card>
                <Card size="small" title="何时失效" className="sub-panel-card">
                  <Paragraph className="panel-description">{dashboard.risk_panel.headline}</Paragraph>
                  <ul className="plain-list">
                    {dashboard.risk_panel.items.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                  <Text type="secondary">{dashboard.risk_panel.disclaimer}</Text>
                </Card>
              </Col>
              <Col xs={24}>
                <Card size="small" title="最近影响这条建议的事件" className="sub-panel-card">
                  <List
                    grid={{ gutter: 12, xs: 1, md: 2, xl: 3 }}
                    dataSource={dashboard.recent_news}
                    renderItem={(item) => (
                      <List.Item>
                        <Card size="small" className="news-card">
                          <Space wrap className="inline-tags">
                            <Tag color={statusColor(item.impact_direction === "positive" ? "pass" : item.impact_direction === "negative" ? "fail" : "warn")}>
                              {item.impact_direction === "positive" ? "正向" : item.impact_direction === "negative" ? "反向" : "中性"}
                            </Tag>
                            <Text type="secondary">{formatDate(item.published_at)}</Text>
                          </Space>
                          <Title level={5}>{item.headline}</Title>
                          <Paragraph className="panel-description">{item.summary}</Paragraph>
                          <Text type="secondary">{`${item.entity_scope} · ${item.source_uri}`}</Text>
                        </Card>
                      </List.Item>
                    )}
                  />
                </Card>
              </Col>
            </Row>
          ),
        },
        {
          key: "evidence",
          label: "证据与术语",
          children: (
            <Row gutter={[16, 16]}>
              <Col xs={24} xl={16}>
                <Card size="small" title="证据回溯" className="sub-panel-card">
                  <List
                    dataSource={dashboard.evidence}
                    renderItem={(item) => (
                      <List.Item>
                        <div className="evidence-entry">
                          <div className="list-item-row">
                            <div>
                              <strong>{item.label}</strong>
                              <div className="muted-line">{`${item.role} · #${item.rank} · ${formatDate(item.timestamp)}`}</div>
                            </div>
                            <Tag>{item.lineage.license_tag}</Tag>
                          </div>
                          <Paragraph className="panel-description">{item.snippet ?? "暂无摘要。"}</Paragraph>
                          <Text type="secondary">{item.lineage.source_uri}</Text>
                        </div>
                      </List.Item>
                    )}
                  />
                </Card>
              </Col>
              <Col xs={24} xl={8}>
                <Card size="small" title="术语解释" className="sub-panel-card">
                  <List
                    size="small"
                    dataSource={mergedGlossary}
                    renderItem={(item) => (
                      <List.Item>
                        <div>
                          <strong>{item.term}</strong>
                          <Paragraph className="panel-description">{item.plain_explanation}</Paragraph>
                          <Text type="secondary">{item.why_it_matters}</Text>
                        </div>
                      </List.Item>
                    )}
                  />
                </Card>
                <Card size="small" title="版本元数据" className="sub-panel-card">
                  <Descriptions size="small" column={1}>
                    <Descriptions.Item label="模型">{`${dashboard.model.name} ${dashboard.model.version}`}</Descriptions.Item>
                    <Descriptions.Item label="验证">{dashboard.model.validation_scheme}</Descriptions.Item>
                    <Descriptions.Item label="Prompt">{`${dashboard.prompt.name} ${dashboard.prompt.version}`}</Descriptions.Item>
                    <Descriptions.Item label="数据时间">{formatDate(dashboard.recommendation.as_of_data_time)}</Descriptions.Item>
                    <Descriptions.Item label="更新时间">{formatDate(dashboard.recommendation.generated_at)}</Descriptions.Item>
                  </Descriptions>
                </Card>
              </Col>
            </Row>
          ),
        },
        {
          key: "followup",
          label: "追问与模拟",
          children: (
            <Row gutter={[16, 16]}>
              <Col xs={24} xl={14}>
                <Card size="small" title="GPT 追问入口" className="sub-panel-card">
                  <Space wrap className="question-chip-group">
                    {dashboard.follow_up.suggested_questions.map((question) => (
                      <Button key={question} size="small" onClick={() => setQuestionDraft(question)}>
                        {question}
                      </Button>
                    ))}
                  </Space>
                  <TextArea
                    rows={5}
                    value={questionDraft}
                    onChange={(event) => setQuestionDraft(event.target.value)}
                    placeholder="输入你要继续追问的问题"
                  />
                  <div className="prompt-actions">
                    <Button type="primary" onClick={handleCopyPrompt}>
                      复制追问包
                    </Button>
                    <Text type="secondary">复制内容已带上当前建议、变化原因和关键证据。</Text>
                  </div>
                  <Card size="small" className="prompt-packet-card">
                    <Title level={5}>证据包提示</Title>
                    <ul className="plain-list">
                      {dashboard.follow_up.evidence_packet.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  </Card>
                </Card>
              </Col>
              <Col xs={24} xl={10}>
                <Card size="small" title="与模拟交易的衔接" className="sub-panel-card">
                  {dashboard.simulation_orders.length > 0 ? (
                    <List
                      dataSource={dashboard.simulation_orders}
                      renderItem={(order) => (
                        <List.Item>
                          <div className="order-entry">
                            <div className="list-item-row">
                              <div>
                                <strong>{order.order_source === "manual" ? "手动模拟" : "模型自动持仓"}</strong>
                                <div className="muted-line">{`${formatDate(order.requested_at)} · ${order.quantity} 股 · ${order.status}`}</div>
                              </div>
                              <Tag color={order.side === "buy" ? "green" : "orange"}>{order.side}</Tag>
                            </div>
                            <Text type="secondary">
                              {order.fills[0]
                                ? `首笔成交 ${formatNumber(order.fills[0].price)}，滑点 ${order.fills[0].slippage_bps.toFixed(1)} bps`
                                : "尚未成交"}
                            </Text>
                          </div>
                        </List.Item>
                      )}
                    />
                  ) : (
                    <Empty description="当前建议没有自动生成模拟订单" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                  )}
                </Card>
              </Col>
            </Row>
          ),
        },
      ]
    : [];

  const portfolioTabs = operations?.portfolios.map((portfolio) => ({
    key: portfolio.portfolio_key,
    label: `${portfolio.mode_label} · ${portfolio.name}`,
    children: <PortfolioWorkspace portfolio={portfolio} />,
  })) ?? [];

  return (
    <>
      {messageContextHolder}
      <div className="workspace-shell">
        <header className="command-header">
          <div>
            <div className="header-kicker">A-Share Advisory Console</div>
            <Title level={1}>A 股投资建议操作面板</Title>
            <Paragraph>
              自选股池、2-8 周波段、候选股推荐、单票解释与模拟交易运营闭环集中在同一控制台。页面默认支持离线快照，静态部署不再依赖在线 demo API 存活。
            </Paragraph>
            <Space wrap className="header-meta">
              <Tag color="blue">自选股池</Tag>
              <Tag color="cyan">2-8 周波段</Tag>
              <Tag color={sourceInfo.mode === "online" ? "green" : "gold"}>{sourceInfo.label}</Tag>
              <Tag icon={<DatabaseOutlined />}>{`快照时间 ${formatDate(sourceInfo.snapshotGeneratedAt)}`}</Tag>
            </Space>
          </div>
          <div className="header-summary">
            <Statistic title="候选股" value={candidates.length} />
            <Statistic title="当前焦点" value={activeCandidate?.name ?? "--"} />
            <Statistic title="最近刷新" value={formatDate(generatedAt)} />
          </div>
        </header>

        <Card className="command-deck panel-card">
          <Row gutter={[16, 16]}>
            <Col xs={24} xl={8}>
              <div className="deck-section-title">数据模式</div>
              <Segmented
                block
                value={preferredMode}
                options={[
                  {
                    label: (
                      <Space>
                        <DatabaseOutlined />
                        离线快照
                      </Space>
                    ),
                    value: "offline",
                  },
                  {
                    label: (
                      <Space>
                        <ApiOutlined />
                        在线 API
                      </Space>
                    ),
                    value: "online",
                  },
                ]}
                onChange={(value) => void handleModeChange(value as DataMode)}
              />
              <Paragraph className="deck-note">{sourceInfo.detail}</Paragraph>
              <Space wrap className="inline-tags">
                <Tag color={sourceInfo.mode === "online" ? "green" : "gold"}>{sourceInfo.label}</Tag>
                <Tag>{sourceInfo.apiBase || "未配置 API Base"}</Tag>
              </Space>
            </Col>

            <Col xs={24} xl={8}>
              <div className="deck-section-title">当前焦点</div>
              <Select
                className="full-width"
                value={selectedSymbol ?? undefined}
                placeholder="选择一个自选股"
                options={candidates.map((item) => ({
                  value: item.symbol,
                  label: `${item.name} · ${item.symbol}`,
                }))}
                onChange={(value) => handleCandidateSelect(value)}
              />
              <div className="deck-actions">
                <Button icon={<ReloadOutlined />} onClick={() => void handleRefresh()}>
                  刷新面板
                </Button>
                <Button type="primary" icon={<ThunderboltOutlined />} onClick={() => void handleBootstrap()}>
                  重置演示数据
                </Button>
              </div>
            </Col>

            <Col xs={24} xl={8}>
              <div className="deck-section-title">内测访问</div>
              <Input.Password
                value={betaKeyDraft}
                onChange={(event) => setBetaKeyDraft(event.target.value)}
                placeholder="输入在线 API 的 access key"
              />
              <div className="deck-actions">
                <Button onClick={() => void handleApplyBetaKey()} icon={<SafetyCertificateOutlined />}>
                  应用 access key
                </Button>
                <Text type="secondary">{`Header: ${sourceInfo.betaHeaderName}`}</Text>
              </div>
            </Col>
          </Row>
        </Card>

        <Segmented
          className="workspace-switch"
          value={view}
          options={[
            {
              label: (
                <Space>
                  <StockOutlined />
                  候选股
                </Space>
              ),
              value: "candidates",
            },
            {
              label: (
                <Space>
                  <LineChartOutlined />
                  单票分析
                </Space>
              ),
              value: "stock",
            },
            {
              label: (
                <Space>
                  <BarChartOutlined />
                  运营看板
                </Space>
              ),
              value: "operations",
            },
          ]}
          onChange={(value) => setView(value as ViewMode)}
        />

        {sourceInfo.fallbackReason ? (
          <Alert
            showIcon
            type="warning"
            className="status-alert"
            message="在线接口不可用，已切换到离线快照"
            description={sourceInfo.fallbackReason}
          />
        ) : null}

        {error ? (
          <Alert
            showIcon
            type="error"
            className="status-alert"
            message="面板加载失败"
            description={error}
          />
        ) : null}

        {loadingShell ? (
          <Card className="panel-card loading-card">
            <Skeleton active paragraph={{ rows: 6 }} />
          </Card>
        ) : null}

        {!loadingShell && view === "candidates" ? (
          <Row gutter={[16, 16]}>
            <Col xs={24} xl={16}>
              <Card
                className="panel-card"
                title="候选股操作台"
                extra={<Text type="secondary">{`更新时间 ${formatDate(generatedAt)}`}</Text>}
              >
                <Table
                  rowKey="symbol"
                  size="small"
                  pagination={false}
                  dataSource={candidates}
                  columns={candidateColumns}
                  onRow={(record) => ({
                    onClick: () => handleCandidateSelect(record.symbol),
                  })}
                  rowClassName={(record) => (record.symbol === activeCandidate?.symbol ? "candidate-row-active" : "")}
                  locale={{ emptyText: "当前没有候选股" }}
                />
              </Card>
            </Col>
            <Col xs={24} xl={8}>
              <Card
                className="panel-card"
                title={activeCandidate ? `当前入选标的 · ${activeCandidate.name}` : "当前入选标的"}
                extra={
                  activeCandidate ? (
                    <Button type="link" onClick={() => handleCandidateSelect(activeCandidate.symbol, "stock")}>
                      打开单票分析
                    </Button>
                  ) : null
                }
              >
                {activeCandidate ? (
                  <>
                    <Space wrap className="inline-tags">
                      <Tag color={directionColor(activeCandidate.direction)}>{activeCandidate.direction_label}</Tag>
                      <Tag>{`${activeCandidate.confidence_label}置信`}</Tag>
                      <Tag>{activeCandidate.applicable_period}</Tag>
                    </Space>
                    <Paragraph className="panel-description">{activeCandidate.summary}</Paragraph>
                    <Descriptions size="small" column={1}>
                      <Descriptions.Item label="当前读法">{activeCandidate.why_now}</Descriptions.Item>
                      <Descriptions.Item label="主要风险">{activeCandidate.primary_risk ?? "等待更多风险证据。"}</Descriptions.Item>
                      <Descriptions.Item label="最近变化">{activeCandidate.change_summary}</Descriptions.Item>
                      <Descriptions.Item label="数据时间">{formatDate(activeCandidate.as_of_data_time)}</Descriptions.Item>
                    </Descriptions>
                    <Card size="small" className="sub-panel-card">
                      <Title level={5}>Watchlist 快照</Title>
                      <List
                        size="small"
                        dataSource={candidates}
                        renderItem={(item) => (
                          <List.Item>
                            <div className="list-item-row">
                              <div>
                                <strong>{item.name}</strong>
                                <div className="muted-line">{item.symbol}</div>
                              </div>
                              <Tag color={directionColor(item.direction)}>{item.direction_label}</Tag>
                            </div>
                          </List.Item>
                        )}
                      />
                    </Card>
                  </>
                ) : (
                  <Empty description="没有可展示的候选股" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                )}
              </Card>
            </Col>
          </Row>
        ) : null}

        {!loadingShell && view === "stock" ? (
          loadingDetail || !dashboard ? (
            <Card className="panel-card loading-card">
              <Skeleton active paragraph={{ rows: 10 }} />
            </Card>
          ) : (
            <div className="panel-stack">
              <Row gutter={[16, 16]}>
                <Col xs={24} md={12} xl={6}>
                  <Card className="panel-card metric-card">
                    <Statistic title="最新收盘" value={formatNumber(dashboard.hero.latest_close)} />
                  </Card>
                </Col>
                <Col xs={24} md={12} xl={6}>
                  <Card className="panel-card metric-card">
                    <Statistic title="日涨跌" value={formatPercent(dashboard.hero.day_change_pct)} />
                  </Card>
                </Col>
                <Col xs={24} md={12} xl={6}>
                  <Card className="panel-card metric-card">
                    <Statistic title="置信表达" value={dashboard.recommendation.confidence_expression} />
                  </Card>
                </Col>
                <Col xs={24} md={12} xl={6}>
                  <Card className="panel-card metric-card">
                    <Statistic title="最近刷新" value={formatDate(dashboard.hero.last_updated)} />
                  </Card>
                </Col>
              </Row>

              <Row gutter={[16, 16]}>
                <Col xs={24} xl={16}>
                  <Card
                    className="panel-card"
                    title={`${dashboard.stock.name} · ${dashboard.stock.symbol}`}
                    extra={
                      <Space wrap className="inline-tags">
                        <Tag color={directionColor(dashboard.recommendation.direction)}>{dashboard.hero.direction_label}</Tag>
                        <Tag>{`${dashboard.recommendation.confidence_label}置信`}</Tag>
                      </Space>
                    }
                  >
                    <Paragraph className="panel-description">{dashboard.recommendation.summary}</Paragraph>
                    <div className="chart-shell">
                      <PriceSparkline points={dashboard.price_chart} />
                    </div>
                    <div className="chart-meta-row">
                      <span>{`区间高点 ${formatNumber(dashboard.hero.high_price)}`}</span>
                      <span>{`区间低点 ${formatNumber(dashboard.hero.low_price)}`}</span>
                      <span>{`换手率 ${dashboard.hero.turnover_rate ? formatPercent(dashboard.hero.turnover_rate / 100) : "未提供"}`}</span>
                    </div>
                    <Space wrap className="inline-tags">
                      {dashboard.hero.sector_tags.map((tag) => (
                        <Tag key={tag} color="blue">
                          {tag}
                        </Tag>
                      ))}
                    </Space>
                  </Card>
                </Col>
                <Col xs={24} xl={8}>
                  <Card className="panel-card" title="当前建议摘要">
                    <Descriptions size="small" column={1}>
                      <Descriptions.Item label="适用周期">{dashboard.recommendation.applicable_period}</Descriptions.Item>
                      <Descriptions.Item label="数据时间">{formatDate(dashboard.recommendation.as_of_data_time)}</Descriptions.Item>
                      <Descriptions.Item label="生成时间">{formatDate(dashboard.recommendation.generated_at)}</Descriptions.Item>
                      <Descriptions.Item label="模型版本">{dashboard.model.version}</Descriptions.Item>
                    </Descriptions>
                    <Card size="small" className="sub-panel-card">
                      <Title level={5}>核心驱动</Title>
                      <ul className="plain-list">
                        {dashboard.recommendation.core_drivers.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    </Card>
                    <Card size="small" className="sub-panel-card">
                      <Title level={5}>反向风险</Title>
                      <ul className="plain-list">
                        {dashboard.recommendation.reverse_risks.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    </Card>
                  </Card>
                </Col>
              </Row>

              <Card className="panel-card">
                <Tabs items={stockTabItems} />
              </Card>
            </div>
          )
        ) : null}

        {!loadingShell && view === "operations" ? (
          loadingDetail || !operations ? (
            <Card className="panel-card loading-card">
              <Skeleton active paragraph={{ rows: 10 }} />
            </Card>
          ) : (
            <div className="panel-stack">
              <Row gutter={[16, 16]}>
                <Col xs={24} md={12} xl={6}>
                  <Card className="panel-card metric-card">
                    <Statistic title="手动模拟仓" value={operations.overview.manual_portfolio_count} />
                  </Card>
                </Col>
                <Col xs={24} md={12} xl={6}>
                  <Card className="panel-card metric-card">
                    <Statistic title="自动持仓仓" value={operations.overview.auto_portfolio_count} />
                  </Card>
                </Col>
                <Col xs={24} md={12} xl={6}>
                  <Card className="panel-card metric-card">
                    <Statistic title="建议命中率" value={formatPercent(operations.overview.recommendation_replay_hit_rate)} />
                  </Card>
                </Col>
                <Col xs={24} md={12} xl={6}>
                  <Card className="panel-card metric-card">
                    <Statistic title="规则通过率" value={formatPercent(operations.overview.rule_pass_rate)} />
                  </Card>
                </Col>
              </Row>

              <Row gutter={[16, 16]}>
                <Col xs={24} xl={16}>
                  <Card
                    className="panel-card"
                    title="分离式模拟交易运营台"
                    extra={<Tag color={statusColor(operations.overview.beta_readiness)}>{operations.overview.beta_readiness}</Tag>}
                  >
                    <Paragraph className="panel-description">
                      手动模拟与模型自动持仓已分账运行，收益归因、回撤监控、规则审计与建议命中复盘在同一运营面板查看。
                    </Paragraph>
                    <Tabs items={portfolioTabs} />
                  </Card>
                </Col>
                <Col xs={24} xl={8}>
                  <Card className="panel-card" title="访问控制与刷新">
                    <Descriptions size="small" column={1}>
                      <Descriptions.Item label="内测阶段">{operations.access_control.beta_phase}</Descriptions.Item>
                      <Descriptions.Item label="鉴权模式">{operations.access_control.auth_mode}</Descriptions.Item>
                      <Descriptions.Item label="Header">{operations.access_control.required_header}</Descriptions.Item>
                      <Descriptions.Item label="活跃用户">{operations.access_control.active_users}</Descriptions.Item>
                    </Descriptions>
                    <Card size="small" className="sub-panel-card">
                      <Title level={5}>刷新策略</Title>
                      <List
                        size="small"
                        dataSource={operations.refresh_policy.schedules}
                        renderItem={(item) => (
                          <List.Item>
                            <div>
                              <div className="list-item-row">
                                <strong>{item.scope}</strong>
                                <Tag>{`${item.cadence_minutes} 分钟`}</Tag>
                              </div>
                              <div className="muted-line">{item.trigger}</div>
                            </div>
                          </List.Item>
                        )}
                      />
                    </Card>
                    <Card size="small" className="sub-panel-card">
                      <Title level={5}>上线门槛</Title>
                      <List
                        size="small"
                        dataSource={operations.launch_gates}
                        renderItem={(item) => (
                          <List.Item>
                            <div className="list-item-row">
                              <div>
                                <strong>{item.gate}</strong>
                                <div className="muted-line">{`${item.current_value} / ${item.threshold}`}</div>
                              </div>
                              <Tag color={statusColor(item.status)}>{item.status}</Tag>
                            </div>
                          </List.Item>
                        )}
                      />
                    </Card>
                  </Card>
                </Col>
              </Row>

              <Row gutter={[16, 16]}>
                <Col xs={24} xl={10}>
                  <Card className="panel-card" title="性能阈值">
                    <List
                      dataSource={operations.performance_thresholds}
                      renderItem={(item) => (
                        <List.Item>
                          <div className="list-item-row">
                            <div>
                              <strong>{item.metric}</strong>
                              <div className="muted-line">{item.note}</div>
                            </div>
                            <Tag color={statusColor(item.status)}>{`${item.observed}${item.unit}`}</Tag>
                          </div>
                        </List.Item>
                      )}
                    />
                  </Card>
                </Col>
                <Col xs={24} xl={14}>
                  <Card className="panel-card" title="建议命中复盘">
                    <Table
                      rowKey="recommendation_id"
                      size="small"
                      pagination={false}
                      dataSource={operations.recommendation_replay}
                      columns={replayColumns}
                      locale={{ emptyText: "暂无复盘数据" }}
                    />
                  </Card>
                </Col>
              </Row>
            </div>
          )
        ) : null}
      </div>
    </>
  );
}

export default App;
