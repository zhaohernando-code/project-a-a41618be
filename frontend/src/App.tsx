import {
  BarChartOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  LineChartOutlined,
  MoonOutlined,
  PlusOutlined,
  ReloadOutlined,
  SettingOutlined,
  StockOutlined,
  SunOutlined,
  SyncOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Empty,
  Form,
  Grid,
  Input,
  InputNumber,
  List,
  Modal,
  Popover,
  Row,
  Select,
  Skeleton,
  Space,
  Statistic,
  Switch,
  Table,
  Tabs,
  Tag,
  Timeline,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import type { ReactNode } from "react";
import { startTransition, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import type {
  CandidateItemView,
  DataSourceInfo,
  DashboardRuntimeConfig,
  FollowUpAnalysisResponse,
  GlossaryEntryView,
  ModelApiKeyView,
  ManualSimulationOrderRequest,
  OperationsDashboardResponse,
  PortfolioNavPointView,
  PortfolioSummaryView,
  PricePointView,
  RecommendationReplayView,
  RuntimeDataSourceView,
  RuntimeSettingsResponse,
  SimulationConfigRequest,
  SimulationTrackStateView,
  SimulationWorkspaceResponse,
  StockDashboardResponse,
  WatchlistItemView,
} from "./types";

const { Paragraph, Text, Title } = Typography;
const { TextArea } = Input;

type ViewMode = "candidates" | "stock" | "operations" | "settings";
type ThemeMode = "light" | "dark";

type CandidateWorkspaceRow = WatchlistItemView & {
  candidate: CandidateItemView | null;
};

type ViewCard = {
  key: ViewMode;
  label: string;
  description: string;
  icon: ReactNode;
};

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

function dataSourceStatusColor(item: RuntimeDataSourceView): string {
  if (item.runtime_ready) return "green";
  if (!item.credential_required) return "default";
  return item.credential_configured ? "green" : "gold";
}

function buildInitialSourceInfo(): DataSourceInfo {
  const runtimeConfig = api.getRuntimeConfig();
  return {
    mode: "online",
    preferredMode: "online",
    label: "服务端实时数据",
    detail: "页面统一通过服务端读取真实行情、K 线和财报；缓存与上游切换由服务端负责。",
    apiBase: runtimeConfig.apiBase,
    betaHeaderName: runtimeConfig.betaHeaderName,
    betaKeyPresent: Boolean(api.getBetaAccessKey()),
    snapshotGeneratedAt: "",
    fallbackReason: null,
  };
}

function mergeSourceInfo(primary: DataSourceInfo | null | undefined, secondary: DataSourceInfo | null | undefined): DataSourceInfo {
  if (!primary && !secondary) {
    return buildInitialSourceInfo();
  }
  if (!primary) {
    return secondary as DataSourceInfo;
  }
  if (!secondary) {
    return primary;
  }

  return {
    ...primary,
    ...secondary,
    fallbackReason: secondary.fallbackReason ?? primary.fallbackReason ?? null,
  };
}

function inferExchangeFromSymbol(symbol: string): string {
  if (symbol.endsWith(".SH")) return "SSE";
  if (symbol.endsWith(".SZ")) return "SZSE";
  return "--";
}

function buildCandidateWorkspaceRows(
  watchlist: WatchlistItemView[],
  candidates: CandidateItemView[],
): CandidateWorkspaceRow[] {
  const candidateBySymbol = new Map(candidates.map((item) => [item.symbol, item] as const));
  const seen = new Set<string>();
  const rows: CandidateWorkspaceRow[] = [];

  watchlist.forEach((item) => {
    seen.add(item.symbol);
    rows.push({
      ...item,
      candidate: candidateBySymbol.get(item.symbol) ?? null,
    });
  });

  candidates.forEach((candidate) => {
    if (seen.has(candidate.symbol)) {
      return;
    }
    rows.push({
      symbol: candidate.symbol,
      name: candidate.name,
      exchange: inferExchangeFromSymbol(candidate.symbol),
      ticker: candidate.symbol.split(".")[0] ?? candidate.symbol,
      status: "active",
      source_kind: "candidate_only",
      analysis_status: "ready",
      added_at: candidate.generated_at,
      updated_at: candidate.generated_at,
      last_analyzed_at: candidate.generated_at,
      last_error: null,
      latest_direction: candidate.direction,
      latest_confidence_label: candidate.confidence_label,
      latest_generated_at: candidate.generated_at,
      candidate,
    });
  });

  return rows.sort((left, right) => {
    const leftRank = left.candidate?.rank ?? Number.MAX_SAFE_INTEGER;
    const rightRank = right.candidate?.rank ?? Number.MAX_SAFE_INTEGER;
    if (leftRank !== rightRank) {
      return leftRank - rightRank;
    }
    return left.symbol.localeCompare(right.symbol);
  });
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

function KlinePanel({
  title,
  points,
  lastUpdated,
  stockName,
}: {
  title: string;
  points: PricePointView[];
  lastUpdated?: string | null;
  stockName?: string | null;
}) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <div className="chart-shell compact-chart">
        <PriceSparkline points={points} />
      </div>
      <div className="chart-meta-row">
        <span>{stockName ?? "--"}</span>
        <span>{`K 线刷新 ${formatDate(lastUpdated)}`}</span>
        <Button type="link" onClick={() => setOpen(true)}>
          弹窗查看
        </Button>
      </div>
      <Modal
        open={open}
        width={960}
        footer={null}
        title={title}
        onCancel={() => setOpen(false)}
      >
        <div className="chart-shell">
          <PriceSparkline points={points} />
        </div>
      </Modal>
    </>
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

function SimulationTrackCard({ track }: { track: SimulationTrackStateView }) {
  return (
    <Card
      className="panel-card"
      title={track.label}
      extra={
        <Space wrap className="inline-tags">
          <Tag color="blue">{track.portfolio.mode_label}</Tag>
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
      <PortfolioWorkspace portfolio={track.portfolio} />
    </Card>
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

function App({ themeMode, onToggleTheme }: { themeMode: ThemeMode; onToggleTheme: () => void }) {
  const initialRuntimeConfig = api.getRuntimeConfig();
  const screens = Grid.useBreakpoint();
  const isMobile = !screens.md;
  const [messageApi, messageContextHolder] = message.useMessage();
  const [view, setView] = useState<ViewMode>("candidates");
  const [runtimeConfig, setRuntimeConfig] = useState<DashboardRuntimeConfig>(initialRuntimeConfig);
  const [sourceInfo, setSourceInfo] = useState<DataSourceInfo>(() => buildInitialSourceInfo());
  const [runtimeSettings, setRuntimeSettings] = useState<RuntimeSettingsResponse | null>(null);
  const [watchlist, setWatchlist] = useState<WatchlistItemView[]>([]);
  const [candidates, setCandidates] = useState<CandidateItemView[]>([]);
  const [generatedAt, setGeneratedAt] = useState<string | null>(null);
  const [glossary, setGlossary] = useState<GlossaryEntryView[]>([]);
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [dashboard, setDashboard] = useState<StockDashboardResponse | null>(null);
  const [operations, setOperations] = useState<OperationsDashboardResponse | null>(null);
  const [simulation, setSimulation] = useState<SimulationWorkspaceResponse | null>(null);
  const [simulationConfigDraft, setSimulationConfigDraft] = useState<SimulationConfigRequest | null>(null);
  const [manualOrderDraft, setManualOrderDraft] = useState<ManualSimulationOrderRequest>({
    symbol: "",
    side: "buy",
    quantity: 100,
    reason: "",
    limit_price: null,
  });
  const [operationsLoading, setOperationsLoading] = useState(false);
  const [operationsError, setOperationsError] = useState<string | null>(null);
  const [simulationAction, setSimulationAction] = useState<string | null>(null);
  const [questionDraft, setQuestionDraft] = useState("");
  const [analysisAnswer, setAnalysisAnswer] = useState<FollowUpAnalysisResponse | null>(null);
  const [analysisKeyId, setAnalysisKeyId] = useState<number | undefined>(undefined);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [newKeyName, setNewKeyName] = useState("");
  const [newKeyProvider, setNewKeyProvider] = useState("openai");
  const [newKeyModel, setNewKeyModel] = useState("gpt-4.1-mini");
  const [newKeyBaseUrl, setNewKeyBaseUrl] = useState("https://api.openai.com/v1");
  const [newKeySecret, setNewKeySecret] = useState("");
  const [newKeyPriority, setNewKeyPriority] = useState("100");
  const [providerDrafts, setProviderDrafts] = useState<Record<string, { accessToken: string; baseUrl: string; enabled: boolean; notes: string }>>({});
  const [watchlistSymbolDraft, setWatchlistSymbolDraft] = useState("");
  const [watchlistNameDraft, setWatchlistNameDraft] = useState("");
  const [addPopoverOpen, setAddPopoverOpen] = useState(false);
  const [pendingRemoval, setPendingRemoval] = useState<CandidateWorkspaceRow | null>(null);
  const [loadingShell, setLoadingShell] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [mutatingWatchlist, setMutatingWatchlist] = useState(false);
  const [watchlistMutationSymbol, setWatchlistMutationSymbol] = useState<string | null>(null);
  const [savingConfig, setSavingConfig] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const canMutateWatchlist = true;

  const candidateRows = useMemo(
    () => buildCandidateWorkspaceRows(watchlist, candidates),
    [watchlist, candidates],
  );

  const activeRow = useMemo(
    () => candidateRows.find((item) => item.symbol === selectedSymbol) ?? candidateRows[0] ?? null,
    [candidateRows, selectedSymbol],
  );

  const activeCandidate = activeRow?.candidate ?? null;

  const mergedGlossary = useMemo(() => {
    const entries = [...glossary, ...(dashboard?.glossary ?? [])];
    return Array.from(new Map(entries.map((item) => [item.term, item])).values());
  }, [dashboard?.glossary, glossary]);

  const modelApiKeys = runtimeSettings?.model_api_keys ?? [];
  const providerCredentials = runtimeSettings?.provider_credentials ?? [];

  const navCards: ViewCard[] = [
    {
      key: "candidates",
      label: "候选与自选",
      description: "统一查看候选标的、自选维护与快捷操作。",
      icon: <StockOutlined />,
    },
    {
      key: "stock",
      label: "单票分析",
      description: "查看价格轨迹、证据、风险和追问结果。",
      icon: <LineChartOutlined />,
    },
    {
      key: "operations",
      label: "运营复盘",
      description: "检查组合表现、规则审计和命中复盘。",
      icon: <BarChartOutlined />,
    },
    {
      key: "settings",
      label: "设置",
      description: "集中查看说明、模型和数据源配置。",
      icon: <SettingOutlined />,
    },
  ];

  async function loadRuntimeSettings(): Promise<void> {
    const payload = await api.getRuntimeSettings();
    setRuntimeSettings(payload);
    setAnalysisKeyId((current) => {
      if (current && payload.model_api_keys.some((item) => item.id === current)) {
        return current;
      }
      return payload.default_model_api_key_id ?? payload.model_api_keys[0]?.id;
    });
    setProviderDrafts((current) => {
      const next: Record<string, { accessToken: string; baseUrl: string; enabled: boolean; notes: string }> = { ...current };
      payload.provider_credentials.forEach((credential) => {
        if (!next[credential.provider_name]) {
          next[credential.provider_name] = {
            accessToken: "",
            baseUrl: credential.base_url ?? "",
            enabled: credential.enabled,
            notes: credential.notes ?? "",
          };
        }
      });
      payload.data_sources.forEach((source) => {
        if (!next[source.provider_name]) {
          next[source.provider_name] = {
            accessToken: "",
            baseUrl: source.base_url ?? "",
            enabled: source.enabled,
            notes: "",
          };
        }
      });
      return next;
    });
  }

  function applySimulationWorkspace(workspace: SimulationWorkspaceResponse): void {
    setSimulation(workspace);
    setSimulationConfigDraft({
      initial_cash: workspace.configuration.initial_cash,
      watch_symbols: workspace.configuration.watch_symbols,
      focus_symbol: workspace.configuration.focus_symbol ?? null,
      step_interval_seconds: workspace.configuration.step_interval_seconds,
      auto_execute_model: workspace.configuration.auto_execute_model,
    });
    setManualOrderDraft((current) => ({
      ...current,
      symbol: current.symbol || workspace.configuration.focus_symbol || workspace.configuration.watch_symbols[0] || "",
      reason: current.reason,
    }));
  }

  async function loadShellData(preferredSymbol?: string | null): Promise<string | null> {
    setLoadingShell(true);
    setError(null);
    try {
      const { data, source } = await api.loadShellData();
      setRuntimeConfig(api.getRuntimeConfig());
      setWatchlist(data.watchlist.items);
      setCandidates(data.candidates.items);
      setGeneratedAt(data.candidates.generated_at);
      setGlossary(data.glossary);
      setSourceInfo(source);
      const nextSymbol = data.watchlist.items.find((item) => item.symbol === preferredSymbol)?.symbol
        ?? data.watchlist.items.find((item) => item.symbol === selectedSymbol)?.symbol
        ?? data.watchlist.items[0]?.symbol
        ?? data.candidates.items.find((item) => item.symbol === preferredSymbol)?.symbol
        ?? data.candidates.items.find((item) => item.symbol === selectedSymbol)?.symbol
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
      const stockResult = await api.getStockDashboard(symbol);
      setDashboard(stockResult.data);
      setQuestionDraft(stockResult.data.follow_up.suggested_questions[0] ?? "");
      setAnalysisAnswer(null);
      setSourceInfo(stockResult.source);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "加载单票分析失败。");
    } finally {
      setLoadingDetail(false);
    }
  }

  async function loadOperationsData(symbol: string): Promise<void> {
    setOperationsLoading(true);
    setOperationsError(null);
    try {
      const [operationsResult, simulationResult] = await Promise.allSettled([
        api.getOperationsDashboard(symbol),
        api.getSimulationWorkspace(),
      ]);

      let nextSource: DataSourceInfo | null = null;
      let nextError: string | null = null;

      if (operationsResult.status === "fulfilled") {
        setOperations(operationsResult.value.data);
        nextSource = operationsResult.value.source;
      } else {
        setOperations(null);
        nextError = operationsResult.reason instanceof Error ? operationsResult.reason.message : "加载运营复盘概览失败。";
      }

      if (simulationResult.status === "fulfilled") {
        applySimulationWorkspace(simulationResult.value.data);
        nextSource = nextSource ? mergeSourceInfo(nextSource, simulationResult.value.source) : simulationResult.value.source;
      } else {
        setSimulation(null);
        if (!nextError) {
          nextError = simulationResult.reason instanceof Error ? simulationResult.reason.message : "加载双轨模拟台失败。";
        }
      }

      if (nextSource) {
        setSourceInfo(nextSource);
      }
      if (nextError) {
        setOperationsError(nextError);
      }
    } finally {
      setOperationsLoading(false);
    }
  }

  useEffect(() => {
    void (async () => {
      try {
        await loadRuntimeSettings();
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "加载运行时配置失败。");
      }
      await loadShellData();
    })();
  }, []);

  useEffect(() => {
    if (!selectedSymbol) {
      setDashboard(null);
      setOperations(null);
      setSimulation(null);
      setOperationsError(null);
      return;
    }
    let cancelled = false;
    setOperations(null);
    setSimulation(null);
    setOperationsError(null);
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

  useEffect(() => {
    if (view !== "operations" || !selectedSymbol) {
      return;
    }
    void loadOperationsData(selectedSymbol);
  }, [selectedSymbol, view]);

  useEffect(() => {
    if (!simulation) return;
    const fallbackSymbol = selectedSymbol ?? simulation.configuration.focus_symbol ?? simulation.configuration.watch_symbols[0];
    if (!fallbackSymbol) return;
    setManualOrderDraft((current) => ({
      ...current,
      symbol: current.symbol || fallbackSymbol,
    }));
  }, [selectedSymbol, simulation]);

  async function reloadEverything(preferredSymbol?: string | null): Promise<void> {
    await loadRuntimeSettings();
    const initialSymbol = await loadShellData(preferredSymbol);
    const resolvedSymbol = preferredSymbol ?? initialSymbol ?? selectedSymbol;
    if (resolvedSymbol) {
      await loadDetailData(resolvedSymbol);
      if (view === "operations") {
        await loadOperationsData(resolvedSymbol);
      }
    }
  }

  async function handleBootstrap() {
    setError(null);
    const { data, source } = await api.bootstrapDemo();
    setSourceInfo(source);
    messageApi.success(`已重新初始化 ${data.candidate_count} 条候选股样本数据。`);
    await reloadEverything();
  }

  async function handleRefresh() {
    await reloadEverything();
  }

  async function runSimulationAction(
    actionKey: string,
    runner: () => Promise<{ workspace: SimulationWorkspaceResponse; message: string }>,
  ) {
    setSimulationAction(actionKey);
    setError(null);
    try {
      const response = await runner();
      applySimulationWorkspace(response.workspace);
      setOperationsError(null);
      if (selectedSymbol) {
        try {
          const operationsResult = await api.getOperationsDashboard(selectedSymbol);
          setOperations(operationsResult.data);
          setSourceInfo((current) => mergeSourceInfo(current, operationsResult.source));
        } catch (operationsLoadError) {
          setOperationsError(
            operationsLoadError instanceof Error ? operationsLoadError.message : "刷新运营复盘概览失败。",
          );
        }
      }
      messageApi.success(response.message);
    } catch (actionError) {
      const messageText = actionError instanceof Error ? actionError.message : "双轨模拟操作失败。";
      setError(messageText);
      messageApi.error(messageText);
    } finally {
      setSimulationAction(null);
    }
  }

  async function handleSaveSimulationConfig() {
    if (!simulationConfigDraft) return;
    await runSimulationAction("config", () => api.updateSimulationConfig(simulationConfigDraft));
  }

  async function handleSubmitManualOrder() {
    if (!manualOrderDraft.symbol || !manualOrderDraft.reason.trim()) {
      messageApi.warning("请先补齐下单标的和交易理由。");
      return;
    }
    await runSimulationAction("manual-order", () => api.submitManualSimulationOrder({
      ...manualOrderDraft,
      reason: manualOrderDraft.reason.trim(),
      limit_price: manualOrderDraft.limit_price ?? null,
    }));
    setManualOrderDraft((current) => ({
      ...current,
      reason: "",
      limit_price: null,
    }));
  }

  function handleEndSimulation() {
    Modal.confirm({
      title: "结束当前双轨模拟？",
      content: "结束后时间线会停止推进，但当前留痕会保留用于复盘。",
      okText: "确认结束",
      cancelText: "取消",
      okButtonProps: { danger: true },
      onOk: async () => {
        await runSimulationAction("end", () => api.endSimulation({ confirm: true }));
      },
    });
  }

  async function handleAddWatchlist() {
    if (!watchlistSymbolDraft.trim()) {
      messageApi.warning("请先输入股票代码");
      return;
    }
    setMutatingWatchlist(true);
    setWatchlistMutationSymbol(watchlistSymbolDraft.trim().toUpperCase());
    setError(null);
    try {
      const response = await api.addWatchlist(watchlistSymbolDraft, watchlistNameDraft);
      setWatchlistSymbolDraft("");
      setWatchlistNameDraft("");
      setAddPopoverOpen(false);
      messageApi.success(response.message);
      await reloadEverything(response.item.symbol);
      setView("candidates");
    } catch (mutationError) {
      const messageText = mutationError instanceof Error ? mutationError.message : "加入自选池失败。";
      setError(messageText);
      messageApi.error(messageText);
    } finally {
      setMutatingWatchlist(false);
      setWatchlistMutationSymbol(null);
    }
  }

  async function handleRefreshWatchlist(symbol: string) {
    setMutatingWatchlist(true);
    setWatchlistMutationSymbol(symbol);
    setError(null);
    try {
      const response = await api.refreshWatchlist(symbol);
      messageApi.success(response.message);
      await reloadEverything(response.item.symbol);
    } catch (mutationError) {
      const messageText = mutationError instanceof Error ? mutationError.message : "重新分析失败。";
      setError(messageText);
      messageApi.error(messageText);
    } finally {
      setMutatingWatchlist(false);
      setWatchlistMutationSymbol(null);
    }
  }

  async function handleConfirmRemoveWatchlist() {
    if (!pendingRemoval) return;
    const symbol = pendingRemoval.symbol;
    setMutatingWatchlist(true);
    setWatchlistMutationSymbol(symbol);
    setError(null);
    try {
      const response = await api.removeWatchlist(symbol);
      messageApi.success(`已移除 ${response.symbol}，当前剩余 ${response.active_count} 只自选股`);
      const nextSymbol = selectedSymbol === symbol
        ? candidateRows.find((item) => item.symbol !== symbol)?.symbol ?? null
        : selectedSymbol;
      setPendingRemoval(null);
      await reloadEverything(nextSymbol);
    } catch (mutationError) {
      const messageText = mutationError instanceof Error ? mutationError.message : "移除自选股失败。";
      setError(messageText);
      messageApi.error(messageText);
    } finally {
      setMutatingWatchlist(false);
      setWatchlistMutationSymbol(null);
    }
  }

  async function handleCreateModelApiKey() {
    if (!newKeyName.trim() || !newKeyModel.trim() || !newKeyBaseUrl.trim() || !newKeySecret.trim()) {
      messageApi.warning("请完整填写模型 Key 名称、模型名、Base URL 和 Key。");
      return;
    }
    setSavingConfig(true);
    setError(null);
    try {
      await api.createModelApiKey({
        name: newKeyName.trim(),
        provider_name: newKeyProvider.trim(),
        model_name: newKeyModel.trim(),
        base_url: newKeyBaseUrl.trim(),
        api_key: newKeySecret.trim(),
        enabled: true,
        priority: Number.parseInt(newKeyPriority, 10) || 100,
        make_default: modelApiKeys.length === 0,
      });
      setNewKeyName("");
      setNewKeySecret("");
      setNewKeyPriority("100");
      await loadRuntimeSettings();
      messageApi.success("模型 API Key 已保存。");
    } catch (saveError) {
      const messageText = saveError instanceof Error ? saveError.message : "保存模型 API Key 失败。";
      setError(messageText);
      messageApi.error(messageText);
    } finally {
      setSavingConfig(false);
    }
  }

  async function handleToggleModelApiKey(item: ModelApiKeyView) {
    setSavingConfig(true);
    setError(null);
    try {
      await api.updateModelApiKey(item.id, { enabled: !item.enabled });
      await loadRuntimeSettings();
      messageApi.success(`${item.name} 已${item.enabled ? "停用" : "启用"}。`);
    } catch (saveError) {
      const messageText = saveError instanceof Error ? saveError.message : "更新模型 API Key 状态失败。";
      setError(messageText);
      messageApi.error(messageText);
    } finally {
      setSavingConfig(false);
    }
  }

  async function handleSetDefaultModelApiKey(item: ModelApiKeyView) {
    setSavingConfig(true);
    setError(null);
    try {
      await api.setDefaultModelApiKey(item.id);
      await loadRuntimeSettings();
      setAnalysisKeyId(item.id);
      messageApi.success(`已将 ${item.name} 设为默认分析 Key。`);
    } catch (saveError) {
      const messageText = saveError instanceof Error ? saveError.message : "设置默认 Key 失败。";
      setError(messageText);
      messageApi.error(messageText);
    } finally {
      setSavingConfig(false);
    }
  }

  async function handleDeleteModelApiKey(item: ModelApiKeyView) {
    setSavingConfig(true);
    setError(null);
    try {
      await api.deleteModelApiKey(item.id);
      await loadRuntimeSettings();
      messageApi.success(`已删除 ${item.name}。`);
    } catch (saveError) {
      const messageText = saveError instanceof Error ? saveError.message : "删除模型 API Key 失败。";
      setError(messageText);
      messageApi.error(messageText);
    } finally {
      setSavingConfig(false);
    }
  }

  async function handleSaveProviderCredential(providerName: string) {
    const draft = providerDrafts[providerName];
    if (!draft) return;
    setSavingConfig(true);
    setError(null);
    try {
      await api.upsertProviderCredential(providerName, {
        access_token: draft.accessToken.trim() || null,
        base_url: draft.baseUrl.trim() || null,
        enabled: draft.enabled,
        notes: draft.notes.trim() || null,
      });
      setProviderDrafts((current) => ({
        ...current,
        [providerName]: {
          ...current[providerName],
          accessToken: "",
        },
      }));
      await loadRuntimeSettings();
      messageApi.success(`${providerName.toUpperCase()} 凭据已更新。`);
    } catch (saveError) {
      const messageText = saveError instanceof Error ? saveError.message : "保存数据源凭据失败。";
      setError(messageText);
      messageApi.error(messageText);
    } finally {
      setSavingConfig(false);
    }
  }

  async function handleRunAnalysis() {
    if (!dashboard || !selectedSymbol) return;
    if (modelApiKeys.length === 0) {
      messageApi.warning("请先在“设置 -> 模型”里至少保存一个模型 API Key。");
      setView("settings");
      return;
    }
    setAnalysisLoading(true);
    setError(null);
    try {
      const payload = await api.runFollowUpAnalysis({
        symbol: selectedSymbol,
        question: questionDraft,
        model_api_key_id: analysisKeyId,
        failover_enabled: runtimeSettings?.llm_failover_enabled ?? true,
      });
      setAnalysisAnswer(payload);
      messageApi.success(payload.failover_used ? "已完成分析，并触发故障切换。" : "已完成分析。");
    } catch (analysisError) {
      const messageText = analysisError instanceof Error ? analysisError.message : "服务端分析失败。";
      setError(messageText);
      messageApi.error(messageText);
    } finally {
      setAnalysisLoading(false);
    }
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
            <Tag color={directionColor(record.candidate.direction)}>{record.candidate.direction_label}</Tag>
            <Text type="secondary">{`${record.candidate.confidence_label}置信 · ${record.candidate.applicable_period}`}</Text>
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
            <Text type={record.candidate.price_return_20d >= 0 ? "success" : "danger"}>
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
          {record.candidate?.why_now ?? "暂无候选信号，等待服务端重新分析。"}
        </span>
      ),
    },
    {
      title: "主要风险",
      key: "risk",
      width: 220,
      render: (_, record) => (
        <span className="truncate-cell">
          {record.candidate?.primary_risk ?? record.last_error ?? "暂无额外风险提示。"}
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

  const replayColumns: ColumnsType<RecommendationReplayView> = [
    {
      title: "标的",
      key: "stock",
      render: (_, record) => (
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
      title: "标的 / 基准 / 超额",
      key: "performance",
      render: (_, record) => (
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
                  <Select
                    className="full-width"
                    value={analysisKeyId}
                    placeholder="选择用于分析的模型 Key"
                    options={modelApiKeys.map((item) => ({
                      value: item.id,
                      label: `${item.name} · ${item.model_name}${item.is_default ? " · 默认" : ""}`,
                    }))}
                    onChange={(value) => setAnalysisKeyId(value)}
                  />
                  <TextArea
                    rows={5}
                    value={questionDraft}
                    onChange={(event) => setQuestionDraft(event.target.value)}
                    placeholder="输入你要继续追问的问题"
                  />
                  <div className="prompt-actions">
                    <Button type="primary" loading={analysisLoading} onClick={() => void handleRunAnalysis()}>
                      服务端分析
                    </Button>
                    <Button onClick={handleCopyPrompt}>
                      复制追问包
                    </Button>
                    <Text type="secondary">可以显式选 Key；若默认 Key 失败，服务端会按优先级故障切换。</Text>
                  </div>
                  {analysisAnswer ? (
                    <Card size="small" className="prompt-packet-card">
                      <Title level={5}>分析结果</Title>
                      <Paragraph className="panel-description">{analysisAnswer.answer}</Paragraph>
                      <Space wrap className="inline-tags">
                        <Tag color="blue">{analysisAnswer.selected_key.name}</Tag>
                        <Tag>{analysisAnswer.selected_key.model_name}</Tag>
                        {analysisAnswer.failover_used ? <Tag color="orange">已故障切换</Tag> : null}
                      </Space>
                    </Card>
                  ) : null}
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

  const topbarStats = [
    { label: "自选池规模", value: `${watchlist.length} 只标的` },
    { label: "候选输出", value: `${candidates.length} 条信号` },
    { label: "当前焦点", value: activeRow ? `${activeRow.name} · ${activeRow.symbol}` : "--" },
    { label: "最近刷新", value: formatDate(generatedAt) },
  ];

  const addWatchlistOverlay = (
    <div className="watchlist-add-popover">
      <Form layout="vertical" size="small">
        <Form.Item label="股票代码">
          <Input
            value={watchlistSymbolDraft}
            onChange={(event) => setWatchlistSymbolDraft(event.target.value)}
            placeholder="如 600519 或 300750.SZ"
          />
        </Form.Item>
        <Form.Item label="显示名称">
          <Input
            value={watchlistNameDraft}
            onChange={(event) => setWatchlistNameDraft(event.target.value)}
            placeholder="可选：自定义显示名称"
          />
        </Form.Item>
      </Form>
      <div className="watchlist-add-actions">
        <Button size="small" onClick={() => setAddPopoverOpen(false)}>
          取消
        </Button>
        <Button
          type="primary"
          size="small"
          icon={<PlusOutlined />}
          loading={mutatingWatchlist}
          onClick={() => void handleAddWatchlist()}
        >
          加入并分析
        </Button>
      </div>
    </div>
  );

  const settingsTabItems = [
    {
      key: "overview",
      label: "说明",
      children: (
        <Row gutter={[16, 16]}>
          <Col xs={24} xl={9}>
            <Card className="panel-card" title="运行方式概览">
              <Descriptions size="small" column={1}>
                <Descriptions.Item label="部署模式">{runtimeSettings?.deployment_mode ?? "self_hosted_server"}</Descriptions.Item>
                <Descriptions.Item label="存储引擎">{runtimeSettings?.storage_engine ?? "SQLite"}</Descriptions.Item>
                <Descriptions.Item label="缓存后端">{runtimeSettings?.cache_backend ?? "Redis"}</Descriptions.Item>
                <Descriptions.Item label="选源策略">{runtimeSettings?.provider_selection_mode ?? "runtime_policy"}</Descriptions.Item>
                <Descriptions.Item label="关注池范围">{runtimeSettings?.watchlist_scope ?? "shared_watchlist"}</Descriptions.Item>
                <Descriptions.Item label="LLM 故障切换">{runtimeSettings?.llm_failover_enabled ? "开启" : "关闭"}</Descriptions.Item>
              </Descriptions>
              <Paragraph className="panel-description settings-help-text">
                {sourceInfo.detail}
              </Paragraph>
              <Space wrap className="inline-tags">
                <Tag color="green">{sourceInfo.label}</Tag>
                <Tag icon={<DatabaseOutlined />}>{runtimeSettings?.storage_engine ?? "SQLite"}</Tag>
                <Tag>{runtimeSettings?.cache_backend ?? "Redis"}</Tag>
              </Space>
            </Card>
          </Col>
          <Col xs={24} xl={15}>
            <Card className="panel-card" title="缓存与运行说明">
              <List
                size="small"
                dataSource={runtimeSettings?.cache_policies ?? []}
                renderItem={(item) => (
                  <List.Item>
                    <div className="full-width">
                      <div className="list-item-row">
                        <strong>{item.label}</strong>
                        <Tag>{`${item.ttl_seconds}s`}</Tag>
                      </div>
                      <div className="muted-line">{`失败读旧值 ${item.stale_if_error_seconds}s · ${item.warm_on_watchlist ? "仅关注池预热" : "全量"}`}</div>
                    </div>
                  </List.Item>
                )}
              />
              <div className="settings-note-stack">
                {(runtimeSettings?.deployment_notes ?? []).map((note) => (
                  <Alert key={note} type="info" showIcon message={note} />
                ))}
              </div>
              <Card size="small" className="sub-panel-card">
                <Title level={5}>抗击穿策略</Title>
                <ul className="plain-list">
                  <li>{`单飞刷新：${runtimeSettings?.anti_stampede.singleflight ? "开启" : "关闭"}`}</li>
                  <li>{`失败读旧值：${runtimeSettings?.anti_stampede.serve_stale_on_error ? "开启" : "关闭"}`}</li>
                  <li>{`空结果 TTL：${runtimeSettings?.anti_stampede.empty_result_ttl_seconds ?? "--"} 秒`}</li>
                  <li>{`锁超时：${runtimeSettings?.anti_stampede.lock_timeout_seconds ?? "--"} 秒`}</li>
                </ul>
              </Card>
            </Card>
          </Col>
          <Col xs={24} xl={10}>
            <Card className="panel-card" title="数据源状态">
              <List
                size="small"
                dataSource={runtimeSettings?.data_sources ?? []}
                renderItem={(item) => (
                  <List.Item>
                    <div className="full-width">
                      <div className="list-item-row">
                        <div>
                          <strong>{item.provider_name.toUpperCase()}</strong>
                          <div className="muted-line">{item.role}</div>
                        </div>
                        <Tag color={dataSourceStatusColor(item)}>{item.status_label}</Tag>
                      </div>
                      <Paragraph className="panel-description">{item.freshness_note}</Paragraph>
                    </div>
                  </List.Item>
                )}
              />
            </Card>
          </Col>
          <Col xs={24} xl={14}>
            <Card className="panel-card" title="统一字段说明">
              <List
                size="small"
                dataSource={runtimeSettings?.field_mappings ?? []}
                renderItem={(item) => (
                  <List.Item>
                    <div>
                      <strong>{`${item.dataset} · ${item.canonical_field}`}</strong>
                      <div className="muted-line">{`AKShare: ${item.akshare_field} / Tushare: ${item.tushare_field}`}</div>
                      <div className="muted-line">{item.notes}</div>
                    </div>
                  </List.Item>
                )}
              />
            </Card>
          </Col>
        </Row>
      ),
    },
    {
      key: "models",
      label: "模型",
      children: (
        <Row gutter={[16, 16]}>
          <Col xs={24} xl={14}>
            <Card
              className="panel-card"
              title="模型 API Key"
              extra={<Text type="secondary">{`当前 ${modelApiKeys.length} 个`}</Text>}
            >
              <List
                dataSource={modelApiKeys}
                locale={{ emptyText: "尚未配置模型 API Key" }}
                renderItem={(item) => (
                  <List.Item>
                    <div className="watchlist-entry">
                      <div className="list-item-row">
                        <div>
                          <strong>{item.name}</strong>
                          <div className="muted-line">{`${item.provider_name} · ${item.model_name}`}</div>
                        </div>
                        <Space wrap>
                          {item.is_default ? <Tag color="blue">默认</Tag> : null}
                          <Tag color={item.enabled ? "green" : "default"}>{item.enabled ? "启用" : "停用"}</Tag>
                          <Tag>{`P${item.priority}`}</Tag>
                        </Space>
                      </div>
                      <div className="watchlist-meta">
                        <Text type="secondary">{item.base_url}</Text>
                        <Text type="secondary">{`最近状态 ${item.last_status}${item.last_error ? ` · ${item.last_error}` : ""}`}</Text>
                      </div>
                      <div className="watchlist-actions">
                        <Button type="link" disabled={item.is_default} onClick={() => void handleSetDefaultModelApiKey(item)}>
                          设为默认
                        </Button>
                        <Button type="link" onClick={() => void handleToggleModelApiKey(item)}>
                          {item.enabled ? "停用" : "启用"}
                        </Button>
                        <Button type="link" danger onClick={() => void handleDeleteModelApiKey(item)}>
                          删除
                        </Button>
                      </div>
                    </div>
                  </List.Item>
                )}
              />
            </Card>
          </Col>
          <Col xs={24} xl={10}>
            <Card className="panel-card" title="新增模型 Key">
              <Form layout="vertical">
                <Form.Item label="Key 名称" required>
                  <Input value={newKeyName} onChange={(event) => setNewKeyName(event.target.value)} placeholder="如：主 OpenAI" />
                </Form.Item>
                <Form.Item label="Provider" required>
                  <Input value={newKeyProvider} onChange={(event) => setNewKeyProvider(event.target.value)} placeholder="如：openai" />
                </Form.Item>
                <Form.Item label="模型名" required>
                  <Input value={newKeyModel} onChange={(event) => setNewKeyModel(event.target.value)} placeholder="如：gpt-4.1-mini" />
                </Form.Item>
                <Form.Item label="Base URL" required>
                  <Input value={newKeyBaseUrl} onChange={(event) => setNewKeyBaseUrl(event.target.value)} placeholder="如：https://api.openai.com/v1" />
                </Form.Item>
                <Form.Item label="API Key" required>
                  <Input.Password value={newKeySecret} onChange={(event) => setNewKeySecret(event.target.value)} placeholder="输入模型 API Key" />
                </Form.Item>
                <Form.Item label="优先级">
                  <Input value={newKeyPriority} onChange={(event) => setNewKeyPriority(event.target.value)} placeholder="数字越小优先级越高" />
                </Form.Item>
              </Form>
              <div className="deck-actions">
                <Button type="primary" loading={savingConfig} onClick={() => void handleCreateModelApiKey()}>
                  保存模型 Key
                </Button>
              </div>
            </Card>
          </Col>
        </Row>
      ),
    },
    {
      key: "providers",
      label: "数据源",
      children: (
        <Row gutter={[16, 16]}>
          {(runtimeSettings?.data_sources ?? []).map((item) => {
            const draft = providerDrafts[item.provider_name] ?? {
              accessToken: "",
              baseUrl: item.base_url ?? "",
              enabled: item.enabled,
              notes: "",
            };
            const saved = providerCredentials.find((credential) => credential.provider_name === item.provider_name);

            return (
              <Col key={item.provider_name} xs={24} xl={12}>
                <Card className="panel-card" title={item.provider_name.toUpperCase()}>
                  <div className="list-item-row">
                    <div>
                      <Tag color={dataSourceStatusColor(item)}>{item.status_label}</Tag>
                      <Paragraph className="panel-description">{item.freshness_note}</Paragraph>
                    </div>
                    <div className="settings-switch">
                      <Text type="secondary">启用</Text>
                      <Switch
                        checked={draft.enabled}
                        onChange={(checked) =>
                          setProviderDrafts((current) => ({
                            ...current,
                            [item.provider_name]: { ...draft, enabled: checked },
                          }))
                        }
                      />
                    </div>
                  </div>
                  <Form layout="vertical">
                    <Form.Item label="Base URL">
                      <Input
                        value={draft.baseUrl}
                        onChange={(event) =>
                          setProviderDrafts((current) => ({
                            ...current,
                            [item.provider_name]: { ...draft, baseUrl: event.target.value },
                          }))
                        }
                        placeholder="可选：覆盖默认 Base URL"
                      />
                    </Form.Item>
                    <Form.Item label={item.credential_required ? "Access Token" : "预留 Token"}>
                      <Input.Password
                        value={draft.accessToken}
                        onChange={(event) =>
                          setProviderDrafts((current) => ({
                            ...current,
                            [item.provider_name]: { ...draft, accessToken: event.target.value },
                          }))
                        }
                        placeholder={item.credential_required ? "输入服务端使用的 Token" : "可选：为未来代理层预留"}
                      />
                    </Form.Item>
                    <Form.Item label="备注">
                      <Input
                        value={draft.notes}
                        onChange={(event) =>
                          setProviderDrafts((current) => ({
                            ...current,
                            [item.provider_name]: { ...draft, notes: event.target.value },
                          }))
                        }
                        placeholder="记录接入说明、范围或限制"
                      />
                    </Form.Item>
                  </Form>
                  <div className="deck-actions">
                    <Button type="primary" loading={savingConfig} onClick={() => void handleSaveProviderCredential(item.provider_name)}>
                      保存数据源设置
                    </Button>
                  </div>
                  <Space wrap className="inline-tags">
                    <Tag>{saved?.masked_token ?? "未保存 Token"}</Tag>
                    <Tag>{item.docs_url}</Tag>
                  </Space>
                </Card>
              </Col>
            );
          })}
        </Row>
      ),
    },
  ];

  return (
    <>
      {messageContextHolder}
      <div className="app-theme-shell" data-theme={themeMode}>
        <div className="workspace-shell">
          <div className="workspace-hero panel-card">
            <div className="hero-header">
              <div className="hero-copy">
                <div className="topbar-kicker">A-Share Advisory Desk</div>
                <Title level={2}>自选股工作台</Title>
                <Paragraph className="topbar-note">
                  页面收敛为一个工作区：候选信号、自选维护、单票分析、运营复盘和设置都围绕同一批标的展开。
                </Paragraph>
                <Space wrap className="header-meta">
                  <Tag color="blue">2-8 周</Tag>
                  <Tag color="cyan">{sourceInfo.label}</Tag>
                  <Tag icon={<DatabaseOutlined />}>{runtimeSettings?.storage_engine ?? "SQLite"}</Tag>
                  <Tag>{runtimeSettings?.cache_backend ?? "Redis"}</Tag>
                  <Tag>{runtimeConfig.apiBase || "同源 API"}</Tag>
                </Space>
              </div>

              <div className="hero-actions-panel">
                <div className="hero-action-block">
                  <Text type="secondary">当前焦点</Text>
                  <Select
                    className="global-focus-select"
                    value={selectedSymbol ?? undefined}
                    placeholder="选择一个标的"
                    options={candidateRows.map((item) => ({
                      value: item.symbol,
                      label: `${item.name} · ${item.symbol}`,
                    }))}
                    onChange={(value) => handleCandidateSelect(value)}
                  />
                </div>
                <div className="hero-action-row">
                  <Button icon={<ReloadOutlined />} onClick={() => void handleRefresh()}>
                    刷新
                  </Button>
                  <Button icon={<ThunderboltOutlined />} onClick={() => void handleBootstrap()}>
                    重建样本
                  </Button>
                  <Button className="theme-toggle-button" icon={themeMode === "dark" ? <SunOutlined /> : <MoonOutlined />} onClick={onToggleTheme}>
                    {themeMode === "dark" ? "浅色模式" : "夜间模式"}
                  </Button>
                </div>
              </div>
            </div>

            <div className="hero-stat-grid">
              {topbarStats.map((item) => (
                <div key={item.label} className="hero-stat-card">
                  <div className="topbar-stat-label">{item.label}</div>
                  <div className="topbar-stat-value" title={item.value}>
                    {item.value}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="workspace-nav">
            {navCards.map((item) => (
              <button
                key={item.key}
                type="button"
                className={`workspace-nav-card${view === item.key ? " workspace-nav-card-active" : ""}`}
                onClick={() => setView(item.key)}
              >
                <div className="workspace-nav-icon">{item.icon}</div>
                <div className="workspace-nav-copy">
                  <strong>{item.label}</strong>
                  <span>{item.description}</span>
                </div>
              </button>
            ))}
          </div>

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
            <div className="panel-stack">
              <Card
                className="panel-card focus-summary-card"
                title={activeRow ? `当前焦点 · ${activeRow.name}` : "当前焦点"}
                extra={
                  activeRow ? (
                    <Space wrap>
                      <Button type="link" onClick={() => handleCandidateSelect(activeRow.symbol, "stock")}>
                        打开单票分析
                      </Button>
                      {activeRow.source_kind !== "candidate_only" ? (
                        <Button
                          type="link"
                          icon={<SyncOutlined />}
                          loading={mutatingWatchlist && watchlistMutationSymbol === activeRow.symbol}
                          onClick={() => void handleRefreshWatchlist(activeRow.symbol)}
                        >
                          重分析
                        </Button>
                      ) : null}
                    </Space>
                  ) : null
                }
              >
                {activeRow ? (
                  <>
                    <Space wrap className="inline-tags">
                      {activeCandidate ? <Tag color={directionColor(activeCandidate.direction)}>{activeCandidate.direction_label}</Tag> : null}
                      {activeCandidate ? <Tag>{`${activeCandidate.confidence_label}置信`}</Tag> : null}
                      {activeCandidate ? <Tag>{activeCandidate.applicable_period}</Tag> : null}
                      <Tag>{activeRow.symbol}</Tag>
                      <Tag>
                        {activeRow.source_kind === "default_seed"
                          ? "默认样本"
                          : activeRow.source_kind === "candidate_only"
                            ? "候选补齐"
                            : "手动加入"}
                      </Tag>
                    </Space>
                    <Paragraph className="panel-description">
                      {activeCandidate?.summary ?? "当前标的已经在关注池中，但还没有最新候选信号，可在右侧操作里触发重分析。"}
                    </Paragraph>
                    <Descriptions size="small" column={{ xs: 1, md: 2, xl: 4 }}>
                      <Descriptions.Item label="当前触发点">{activeCandidate?.why_now ?? "等待更新"}</Descriptions.Item>
                      <Descriptions.Item label="主要风险">{activeCandidate?.primary_risk ?? activeRow.last_error ?? "暂无额外风险提示"}</Descriptions.Item>
                      <Descriptions.Item label="最近变化">{activeCandidate?.change_summary ?? activeRow.analysis_status}</Descriptions.Item>
                      <Descriptions.Item label="最近分析">{formatDate(activeRow.last_analyzed_at ?? activeRow.updated_at)}</Descriptions.Item>
                    </Descriptions>
                  </>
                ) : (
                  <Empty description="当前没有可展示的标的" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                )}
              </Card>

              <Card
                className="panel-card"
                title="候选股与自选池"
                extra={(
                  <Space wrap>
                    <Text type="secondary">{`共 ${candidateRows.length} 只`}</Text>
                    <Popover
                      open={addPopoverOpen}
                      onOpenChange={setAddPopoverOpen}
                      trigger="click"
                      placement={isMobile ? "bottom" : "bottomRight"}
                      content={addWatchlistOverlay}
                    >
                      <Button shape="circle" type="primary" icon={<PlusOutlined />} />
                    </Popover>
                  </Space>
                )}
              >
                {candidateRows.length === 0 ? (
                  <Empty description="当前自选池为空，请先添加股票代码" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                ) : isMobile ? (
                  <List
                    className="candidate-mobile-list"
                    dataSource={candidateRows}
                    renderItem={(item) => (
                      <List.Item>
                        <Card className={`candidate-mobile-card${item.symbol === activeRow?.symbol ? " candidate-mobile-card-active" : ""}`}>
                          <div className="candidate-mobile-head">
                            <div>
                              <div className="candidate-mobile-rank">{`#${item.candidate?.rank ?? "--"}`}</div>
                              <Title level={5}>{item.name}</Title>
                              <Text type="secondary">{item.symbol}</Text>
                            </div>
                            {item.candidate ? (
                              <Tag color={directionColor(item.candidate.direction)}>{item.candidate.direction_label}</Tag>
                            ) : (
                              <Tag>{item.analysis_status}</Tag>
                            )}
                          </div>
                          <div className="candidate-mobile-metrics">
                            <div>
                              <span>价格</span>
                              <strong>{formatNumber(item.candidate?.last_close)}</strong>
                            </div>
                            <div>
                              <span>20日</span>
                              <strong>{formatPercent(item.candidate?.price_return_20d)}</strong>
                            </div>
                            <div>
                              <span>分析</span>
                              <strong>{formatDate(item.last_analyzed_at ?? item.updated_at)}</strong>
                            </div>
                          </div>
                          <Paragraph className="panel-description">{item.candidate?.summary ?? "等待候选分析结果。"}</Paragraph>
                          <Descriptions size="small" column={1}>
                            <Descriptions.Item label="当前触发点">{item.candidate?.why_now ?? "暂无"}</Descriptions.Item>
                            <Descriptions.Item label="主要风险">{item.candidate?.primary_risk ?? item.last_error ?? "暂无"}</Descriptions.Item>
                          </Descriptions>
                          <div className="candidate-mobile-actions">
                            <Button type="default" onClick={() => handleCandidateSelect(item.symbol, "stock")}>
                              打开
                            </Button>
                            <Button
                              icon={<SyncOutlined />}
                              disabled={item.source_kind === "candidate_only"}
                              loading={mutatingWatchlist && watchlistMutationSymbol === item.symbol}
                              onClick={() => void handleRefreshWatchlist(item.symbol)}
                            >
                              重分析
                            </Button>
                            <Button danger disabled={item.source_kind === "candidate_only"} onClick={() => setPendingRemoval(item)}>
                              移除
                            </Button>
                          </div>
                        </Card>
                      </List.Item>
                    )}
                  />
                ) : (
                  <Table
                    rowKey="symbol"
                    size="middle"
                    pagination={false}
                    dataSource={candidateRows}
                    columns={candidateColumns}
                    scroll={{ x: 1240 }}
                    tableLayout="fixed"
                    onRow={(record) => ({
                      onClick: () => handleCandidateSelect(record.symbol),
                    })}
                    rowClassName={(record) => (record.symbol === activeRow?.symbol ? "candidate-row-active" : "")}
                    locale={{ emptyText: "当前没有候选股" }}
                  />
                )}
              </Card>
            </div>
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
                      <KlinePanel
                        title={`${dashboard.stock.name} · ${dashboard.stock.symbol} K 线`}
                        points={dashboard.price_chart}
                        lastUpdated={dashboard.hero.last_updated}
                        stockName={dashboard.stock.name}
                      />
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
            operationsLoading && !operations && !simulation ? (
              <Card className="panel-card loading-card">
                <Skeleton active paragraph={{ rows: 10 }} />
              </Card>
            ) : (
              <div className="panel-stack">
                {operationsError ? (
                  <Alert
                    type="warning"
                    showIcon
                    className="panel-card"
                    message="运营复盘工作区加载不完整"
                    description={operationsError}
                    action={selectedSymbol ? <Button size="small" onClick={() => void loadOperationsData(selectedSymbol)}>重试</Button> : undefined}
                  />
                ) : null}

                <Row gutter={[16, 16]}>
                  <Col xs={24} md={12} xl={6}>
                    <Card className="panel-card metric-card">
                      <Statistic title="当前状态" value={simulation?.session.status_label ?? "概览可用"} />
                    </Card>
                  </Col>
                  <Col xs={24} md={12} xl={6}>
                    <Card className="panel-card metric-card">
                      <Statistic title="当前步数" value={simulation?.session.current_step ?? 0} />
                    </Card>
                  </Col>
                  <Col xs={24} md={12} xl={6}>
                    <Card className="panel-card metric-card">
                      <Statistic
                        title="建议命中率"
                        value={operations ? formatPercent(operations.overview.recommendation_replay_hit_rate) : "--"}
                      />
                    </Card>
                  </Col>
                  <Col xs={24} md={12} xl={6}>
                    <Card className="panel-card metric-card">
                      <Statistic
                        title="规则通过率"
                        value={operations ? formatPercent(operations.overview.rule_pass_rate) : "--"}
                      />
                    </Card>
                  </Col>
                </Row>

                {simulation ? (
                  <>
                    <Row gutter={[16, 16]}>
                      <Col xs={24} xl={16}>
                        <Card
                          className="panel-card"
                          title="双轨同步模拟台"
                          extra={<Tag color={statusColor(simulation.session.status)}>{simulation.session.status_label}</Tag>}
                        >
                          <Paragraph className="panel-description">
                            从同一时间点、同一初始资金和同一股票池开始，用户轨道与模型轨道共享时间线推进。用户保留人工下单主导权，模型轨道按刷新步给出建议并可直接执行模拟单。
                          </Paragraph>
                          <Space wrap className="deck-actions">
                            <Button
                              type="primary"
                              icon={<ThunderboltOutlined />}
                              disabled={!simulation.controls.can_start}
                              loading={simulationAction === "start"}
                              onClick={() => void runSimulationAction("start", () => api.startSimulation())}
                            >
                              启动
                            </Button>
                            <Button
                              icon={<SyncOutlined />}
                              disabled={!simulation.controls.can_pause}
                              loading={simulationAction === "pause"}
                              onClick={() => void runSimulationAction("pause", () => api.pauseSimulation())}
                            >
                              暂停
                            </Button>
                            <Button
                              icon={<ReloadOutlined />}
                              disabled={!simulation.controls.can_resume}
                              loading={simulationAction === "resume"}
                              onClick={() => void runSimulationAction("resume", () => api.resumeSimulation())}
                            >
                              恢复
                            </Button>
                            <Button
                              type="default"
                              disabled={!simulation.controls.can_step}
                              loading={simulationAction === "step"}
                              onClick={() => void runSimulationAction("step", () => api.stepSimulation())}
                            >
                              单步推进
                            </Button>
                            <Button
                              disabled={!simulation.controls.can_restart}
                              loading={simulationAction === "restart"}
                              onClick={() => void runSimulationAction("restart", () => api.restartSimulation())}
                            >
                              重启
                            </Button>
                            <Button
                              danger
                              disabled={!simulation.controls.can_end}
                              loading={simulationAction === "end"}
                              onClick={handleEndSimulation}
                            >
                              结束
                            </Button>
                          </Space>
                          <Descriptions size="small" column={{ xs: 1, md: 2, xl: 3 }} className="info-grid">
                            <Descriptions.Item label="初始资金">{formatNumber(simulation.session.initial_cash)}</Descriptions.Item>
                            <Descriptions.Item label="股票池">{`${simulation.session.watch_symbols.length} 只`}</Descriptions.Item>
                            <Descriptions.Item label="焦点标的">{simulation.session.focus_symbol ?? "--"}</Descriptions.Item>
                            <Descriptions.Item label="推进规则">{simulation.session.step_trigger_label}</Descriptions.Item>
                            <Descriptions.Item label="成交口径">{simulation.session.fill_rule_label}</Descriptions.Item>
                            <Descriptions.Item label="重启次数">{simulation.session.restart_count}</Descriptions.Item>
                          </Descriptions>
                        </Card>
                      </Col>
                      <Col xs={24} xl={8}>
                        <Card className="panel-card" title="通用 K 线组件">
                          <KlinePanel
                            title={`${simulation.kline.stock_name ?? simulation.kline.symbol ?? "焦点标的"} K 线`}
                            points={simulation.kline.points}
                            lastUpdated={simulation.kline.last_updated}
                            stockName={simulation.kline.stock_name ?? simulation.kline.symbol}
                          />
                        </Card>
                      </Col>
                    </Row>

                    <Row gutter={[16, 16]}>
                      <Col xs={24} xl={12}>
                        <Card className="panel-card" title="模拟参数">
                          <Form layout="vertical">
                            <Form.Item label="初始资金">
                              <InputNumber
                                className="full-width"
                                min={1000}
                                step={10000}
                                value={simulationConfigDraft?.initial_cash}
                                onChange={(value) =>
                                  setSimulationConfigDraft((current) => (
                                    current
                                      ? { ...current, initial_cash: Number(value ?? current.initial_cash) }
                                      : current
                                  ))
                                }
                              />
                            </Form.Item>
                            <Form.Item label="关注股票池">
                              <Select
                                mode="multiple"
                                value={simulationConfigDraft?.watch_symbols ?? []}
                                options={candidateRows.map((item) => ({
                                  value: item.symbol,
                                  label: `${item.name} · ${item.symbol}`,
                                }))}
                                onChange={(value) =>
                                  setSimulationConfigDraft((current) => (
                                    current
                                      ? { ...current, watch_symbols: value }
                                      : current
                                  ))
                                }
                              />
                            </Form.Item>
                            <Form.Item label="焦点标的">
                              <Select
                                value={simulationConfigDraft?.focus_symbol ?? undefined}
                                options={(simulationConfigDraft?.watch_symbols ?? simulation.session.watch_symbols).map((symbol) => ({
                                  value: symbol,
                                  label: candidateRows.find((item) => item.symbol === symbol)
                                    ? `${candidateRows.find((item) => item.symbol === symbol)?.name} · ${symbol}`
                                    : symbol,
                                }))}
                                onChange={(value) =>
                                  setSimulationConfigDraft((current) => (
                                    current
                                      ? { ...current, focus_symbol: value }
                                      : current
                                  ))
                                }
                              />
                            </Form.Item>
                            <Form.Item label="刷新步长（秒）">
                              <InputNumber
                                className="full-width"
                                min={60}
                                max={86400}
                                step={60}
                                value={simulationConfigDraft?.step_interval_seconds}
                                onChange={(value) =>
                                  setSimulationConfigDraft((current) => (
                                    current
                                      ? { ...current, step_interval_seconds: Number(value ?? current.step_interval_seconds) }
                                      : current
                                  ))
                                }
                              />
                            </Form.Item>
                            <Form.Item label="模型轨道自动执行">
                              <Switch
                                checked={simulationConfigDraft?.auto_execute_model ?? false}
                                onChange={(checked) =>
                                  setSimulationConfigDraft((current) => (
                                    current
                                      ? { ...current, auto_execute_model: checked }
                                      : current
                                  ))
                                }
                              />
                            </Form.Item>
                          </Form>
                          <div className="deck-actions">
                            <Button
                              type="primary"
                              loading={simulationAction === "config"}
                              onClick={() => void handleSaveSimulationConfig()}
                            >
                              保存参数
                            </Button>
                          </div>
                        </Card>
                      </Col>
                      <Col xs={24} xl={12}>
                        <Card className="panel-card" title="用户轨道手动下单">
                          <Form layout="vertical">
                            <Form.Item label="标的">
                              <Select
                                value={manualOrderDraft.symbol || undefined}
                                options={simulation.session.watch_symbols.map((symbol) => ({
                                  value: symbol,
                                  label: candidateRows.find((item) => item.symbol === symbol)
                                    ? `${candidateRows.find((item) => item.symbol === symbol)?.name} · ${symbol}`
                                    : symbol,
                                }))}
                                onChange={(value) => setManualOrderDraft((current) => ({ ...current, symbol: value }))}
                              />
                            </Form.Item>
                            <Form.Item label="方向">
                              <Select
                                value={manualOrderDraft.side}
                                options={[
                                  { value: "buy", label: "买入" },
                                  { value: "sell", label: "卖出" },
                                ]}
                                onChange={(value) => setManualOrderDraft((current) => ({ ...current, side: value }))}
                              />
                            </Form.Item>
                            <Form.Item label="数量">
                              <InputNumber
                                className="full-width"
                                min={100}
                                step={100}
                                value={manualOrderDraft.quantity}
                                onChange={(value) =>
                                  setManualOrderDraft((current) => ({ ...current, quantity: Number(value ?? current.quantity) }))
                                }
                              />
                            </Form.Item>
                            <Form.Item label="交易理由">
                              <TextArea
                                rows={4}
                                value={manualOrderDraft.reason}
                                onChange={(event) => setManualOrderDraft((current) => ({ ...current, reason: event.target.value }))}
                                placeholder="记录你基于右侧建议、K 线和证据做出该笔交易的理由"
                              />
                            </Form.Item>
                          </Form>
                          <Alert
                            className="sub-alert"
                            type="info"
                            showIcon
                            message="一期成交规则"
                            description="当前按最新价即时成交，用于快速对比用户和模型在同一步上的决策差异。"
                          />
                          <div className="deck-actions">
                            <Button
                              type="primary"
                              loading={simulationAction === "manual-order"}
                              onClick={() => void handleSubmitManualOrder()}
                            >
                              提交模拟单
                            </Button>
                          </div>
                        </Card>
                      </Col>
                    </Row>

                    <Row gutter={[16, 16]}>
                      <Col xs={24} xl={10}>
                        <Card className="panel-card" title="模型轨道建议">
                          <List
                            dataSource={simulation.model_advices}
                            locale={{ emptyText: "当前没有新的模型动作建议" }}
                            renderItem={(item) => (
                              <List.Item>
                                <div className="watchlist-entry">
                                  <div className="list-item-row">
                                    <div>
                                      <strong>{item.stock_name}</strong>
                                      <div className="muted-line">{`${item.symbol} · ${formatDate(item.generated_at)}`}</div>
                                    </div>
                                    <Space wrap>
                                      <Tag color={directionColor(item.direction)}>{item.direction_label}</Tag>
                                      <Tag>{item.confidence_label}</Tag>
                                    </Space>
                                  </div>
                                  <Paragraph className="panel-description">{item.reason}</Paragraph>
                                  <div className="watchlist-meta">
                                    <Text type="secondary">{`建议动作 ${item.action} · ${item.quantity} 股 · 参考价 ${formatNumber(item.reference_price)}`}</Text>
                                  </div>
                                  <Space wrap className="inline-tags">
                                    {item.risk_flags.map((risk) => (
                                      <Tag key={`${item.symbol}-${risk}`}>{risk}</Tag>
                                    ))}
                                  </Space>
                                </div>
                              </List.Item>
                            )}
                          />
                        </Card>
                      </Col>
                      <Col xs={24} xl={14}>
                        <Card className="panel-card" title="双轨核心差异">
                          <Table
                            rowKey="label"
                            size="small"
                            pagination={false}
                            dataSource={simulation.comparison_metrics}
                            columns={[
                              { title: "指标", dataIndex: "label" },
                              {
                                title: "用户轨道",
                                dataIndex: "manual_value",
                                render: (value: number, record) => (record.unit === "pct" ? formatPercent(value) : formatNumber(value)),
                              },
                              {
                                title: "模型轨道",
                                dataIndex: "model_value",
                                render: (value: number, record) => (record.unit === "pct" ? formatPercent(value) : formatNumber(value)),
                              },
                              {
                                title: "差值",
                                dataIndex: "difference",
                                render: (value: number, record) => (record.unit === "pct" ? formatPercent(value) : formatNumber(value)),
                              },
                              {
                                title: "领先方",
                                dataIndex: "leader",
                                render: (value: string) => (
                                  <Tag color={value === "manual" ? "green" : value === "model" ? "blue" : "default"}>
                                    {value === "manual" ? "用户" : value === "model" ? "模型" : "持平"}
                                  </Tag>
                                ),
                              },
                            ]}
                          />
                        </Card>
                      </Col>
                    </Row>

                    <Row gutter={[16, 16]}>
                      <Col xs={24} xl={12}>
                        <SimulationTrackCard track={simulation.manual_track} />
                      </Col>
                      <Col xs={24} xl={12}>
                        <SimulationTrackCard track={simulation.model_track} />
                      </Col>
                    </Row>

                    <Row gutter={[16, 16]}>
                      <Col xs={24} xl={10}>
                        <Card className="panel-card" title="时点决策差异">
                          <List
                            dataSource={simulation.decision_differences}
                            locale={{ emptyText: "还没有产生足够的双轨差异记录" }}
                            renderItem={(item) => (
                              <List.Item>
                                <div className="watchlist-entry">
                                  <div className="list-item-row">
                                    <div>
                                      <strong>{`第 ${item.step_index} 步 · ${item.symbol ?? "未指定标的"}`}</strong>
                                      <div className="muted-line">{formatDate(item.happened_at)}</div>
                                    </div>
                                  </div>
                                  <Descriptions size="small" column={1}>
                                    <Descriptions.Item label="用户动作">{`${item.manual_action} · ${item.manual_reason}`}</Descriptions.Item>
                                    <Descriptions.Item label="模型动作">{`${item.model_action} · ${item.model_reason}`}</Descriptions.Item>
                                  </Descriptions>
                                  <Paragraph className="panel-description">{item.difference_summary}</Paragraph>
                                  <Space wrap className="inline-tags">
                                    {item.risk_focus.map((risk) => (
                                      <Tag key={`${item.step_index}-${risk}`}>{risk}</Tag>
                                    ))}
                                  </Space>
                                </div>
                              </List.Item>
                            )}
                          />
                        </Card>
                      </Col>
                      <Col xs={24} xl={14}>
                        <Card className="panel-card" title="共享时间线留痕">
                          <Descriptions size="small" column={1}>
                            <Descriptions.Item label="启动时间">{formatDate(simulation.session.started_at)}</Descriptions.Item>
                            <Descriptions.Item label="最近恢复">{formatDate(simulation.session.last_resumed_at)}</Descriptions.Item>
                            <Descriptions.Item label="最近暂停">{formatDate(simulation.session.paused_at)}</Descriptions.Item>
                            <Descriptions.Item label="结束时间">{formatDate(simulation.session.ended_at)}</Descriptions.Item>
                          </Descriptions>
                          <Timeline
                            items={simulation.timeline.map((item) => ({
                              color: statusColor(item.severity),
                              children: (
                                <div className="watchlist-entry">
                                  <div className="list-item-row">
                                    <div>
                                      <strong>{item.title}</strong>
                                      <div className="muted-line">{`第 ${item.step_index} 步 · ${item.track_label} · ${formatDate(item.happened_at)}`}</div>
                                    </div>
                                    {item.symbol ? <Tag>{item.symbol}</Tag> : null}
                                  </div>
                                  <Paragraph className="panel-description">{item.detail}</Paragraph>
                                  <Space wrap className="inline-tags">
                                    {item.reason_tags.map((tag) => (
                                      <Tag key={`${item.event_key}-${tag}`}>{tag}</Tag>
                                    ))}
                                  </Space>
                                </div>
                              ),
                            }))}
                          />
                        </Card>
                      </Col>
                    </Row>
                  </>
                ) : (
                  <Card className="panel-card">
                    <Alert
                      type="warning"
                      showIcon
                      message="双轨模拟台暂时不可用"
                      description="运营概览已经加载完成，但模拟工作区本次未返回。可以先查看组合复盘和命中率，再点击重试恢复模拟台。"
                      action={selectedSymbol ? <Button size="small" onClick={() => void loadOperationsData(selectedSymbol)}>重试</Button> : undefined}
                    />
                  </Card>
                )}

                {operations ? (
                  <>
                    <Row gutter={[16, 16]}>
                      <Col xs={24} xl={16}>
                        <Card
                          className="panel-card"
                          title="组合复盘与建议命中"
                          extra={<Text type="secondary">{`生成时间 ${formatDate(operations.overview.generated_at)}`}</Text>}
                        >
                          <Descriptions size="small" column={{ xs: 1, md: 2 }}>
                            <Descriptions.Item label="手动模拟仓">{operations.overview.manual_portfolio_count}</Descriptions.Item>
                            <Descriptions.Item label="模型自动仓">{operations.overview.auto_portfolio_count}</Descriptions.Item>
                            <Descriptions.Item label="Beta 就绪度">{operations.overview.beta_readiness}</Descriptions.Item>
                            <Descriptions.Item label="刷新冷却">{`${operations.refresh_policy.manual_refresh_cooldown_minutes} 分钟`}</Descriptions.Item>
                          </Descriptions>
                          {portfolioTabs.length > 0 ? (
                            <Tabs items={portfolioTabs} />
                          ) : (
                            <Empty description="当前没有可展示的组合轨道" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                          )}
                        </Card>
                      </Col>
                      <Col xs={24} xl={8}>
                        <Card className="panel-card" title="上线闸门">
                          <List
                            dataSource={operations.launch_gates}
                            renderItem={(item) => (
                              <List.Item>
                                <div className="watchlist-entry">
                                  <div className="list-item-row">
                                    <strong>{item.gate}</strong>
                                    <Tag color={statusColor(item.status)}>{item.status}</Tag>
                                  </div>
                                  <Paragraph className="panel-description">{item.threshold}</Paragraph>
                                  <Text type="secondary">{`当前 ${item.current_value}`}</Text>
                                </div>
                              </List.Item>
                            )}
                          />
                        </Card>
                      </Col>
                    </Row>

                    <Row gutter={[16, 16]}>
                      <Col xs={24} xl={14}>
                        <Card className="panel-card" title="建议命中复盘">
                          <Table
                            rowKey="recommendation_id"
                            size="small"
                            pagination={false}
                            dataSource={operations.recommendation_replay}
                            columns={replayColumns}
                          />
                        </Card>
                      </Col>
                      <Col xs={24} xl={10}>
                        <Card className="panel-card" title="刷新与性能阈值">
                          <Alert
                            className="sub-alert"
                            type="info"
                            showIcon
                            message="刷新策略"
                            description={`市场时区 ${operations.refresh_policy.market_timezone}，核心缓存 TTL ${operations.refresh_policy.cache_ttl_seconds} 秒。`}
                          />
                          <List
                            dataSource={operations.performance_thresholds}
                            renderItem={(item) => (
                              <List.Item>
                                <div className="watchlist-entry">
                                  <div className="list-item-row">
                                    <strong>{item.metric}</strong>
                                    <Tag color={statusColor(item.status)}>{item.status}</Tag>
                                  </div>
                                  <Text>{`观测 ${formatNumber(item.observed)} ${item.unit} / 目标 ${formatNumber(item.target)} ${item.unit}`}</Text>
                                  <Paragraph className="panel-description">{item.note}</Paragraph>
                                </div>
                              </List.Item>
                            )}
                          />
                        </Card>
                      </Col>
                    </Row>
                  </>
                ) : null}
              </div>
            )
          ) : null}

          {!loadingShell && view === "settings" ? (
            <div className="panel-stack">
              <Card className="panel-card" title="设置">
                <Tabs items={settingsTabItems} />
              </Card>
            </div>
          ) : null}
        </div>
      </div>

      <Modal
        open={Boolean(pendingRemoval)}
        title={pendingRemoval ? `移除 ${pendingRemoval.name}` : "移除标的"}
        okText="确认移除"
        cancelText="取消"
        okButtonProps={{ danger: true }}
        confirmLoading={mutatingWatchlist && watchlistMutationSymbol === pendingRemoval?.symbol}
        onCancel={() => setPendingRemoval(null)}
        onOk={() => void handleConfirmRemoveWatchlist()}
      >
        <Paragraph className="panel-description">
          该标的会从共享自选池中移除，相关候选缓存也会失去预热资格。确认继续吗？
        </Paragraph>
      </Modal>
    </>
  );
}

export default App;
