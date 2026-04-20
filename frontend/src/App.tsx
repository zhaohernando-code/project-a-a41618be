import {
  BarChartOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  LineChartOutlined,
  PlusOutlined,
  ReloadOutlined,
  SettingOutlined,
  StockOutlined,
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
  DataSourceInfo,
  DashboardRuntimeConfig,
  FollowUpAnalysisResponse,
  GlossaryEntryView,
  ModelApiKeyView,
  OperationsDashboardResponse,
  PortfolioNavPointView,
  PortfolioSummaryView,
  PricePointView,
  ProviderCredentialView,
  RecommendationReplayView,
  RuntimeSettingsResponse,
  StockDashboardResponse,
  WatchlistItemView,
} from "./types";

const { Paragraph, Text, Title } = Typography;
const { TextArea } = Input;

type ViewMode = "candidates" | "stock" | "operations" | "config";

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

function mergeSourceInfo(primary: DataSourceInfo, secondary: DataSourceInfo): DataSourceInfo {
  return secondary ?? primary;
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
  const initialRuntimeConfig = api.getRuntimeConfig();
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
  const [loadingShell, setLoadingShell] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [mutatingWatchlist, setMutatingWatchlist] = useState(false);
  const [watchlistMutationSymbol, setWatchlistMutationSymbol] = useState<string | null>(null);
  const [savingConfig, setSavingConfig] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const canMutateWatchlist = true;

  const activeCandidate = useMemo(
    () => candidates.find((item) => item.symbol === selectedSymbol) ?? candidates[0] ?? null,
    [candidates, selectedSymbol],
  );

  const activeWatchlistItem = useMemo(
    () => watchlist.find((item) => item.symbol === selectedSymbol) ?? watchlist[0] ?? null,
    [watchlist, selectedSymbol],
  );

  const mergedGlossary = useMemo(() => {
    const entries = [...glossary, ...(dashboard?.glossary ?? [])];
    return Array.from(new Map(entries.map((item) => [item.term, item])).values());
  }, [dashboard?.glossary, glossary]);

  const modelApiKeys = runtimeSettings?.model_api_keys ?? [];
  const providerCredentials = runtimeSettings?.provider_credentials ?? [];

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
      const nextSymbol = data.candidates.items.find((item) => item.symbol === preferredSymbol)?.symbol
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
      const [stockResult, operationsResult] = await Promise.all([
        api.getStockDashboard(symbol),
        api.getOperationsDashboard(symbol),
      ]);
      setDashboard(stockResult.data);
      setOperations(operationsResult.data);
      setQuestionDraft(stockResult.data.follow_up.suggested_questions[0] ?? "");
      setAnalysisAnswer(null);
      setSourceInfo(mergeSourceInfo(stockResult.source, operationsResult.source));
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "加载单票与运营面板失败。");
    } finally {
      setLoadingDetail(false);
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
      return;
    }
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

  async function reloadEverything(preferredSymbol?: string | null): Promise<void> {
    await loadRuntimeSettings();
    const initialSymbol = await loadShellData(preferredSymbol);
    const resolvedSymbol = preferredSymbol ?? initialSymbol ?? selectedSymbol;
    if (resolvedSymbol) {
      await loadDetailData(resolvedSymbol);
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

  async function handleRemoveWatchlist(symbol: string) {
    setMutatingWatchlist(true);
    setWatchlistMutationSymbol(symbol);
    setError(null);
    try {
      const response = await api.removeWatchlist(symbol);
      messageApi.success(`已移除 ${response.symbol}，当前剩余 ${response.active_count} 只自选股`);
      const nextSymbol = selectedSymbol === symbol
        ? watchlist.find((item) => item.symbol !== symbol)?.symbol ?? null
        : selectedSymbol;
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
      messageApi.warning("请先在“模型配置”里至少保存一个模型 API Key。");
      setView("config");
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
    { label: "自选股", value: String(watchlist.length) },
    { label: "候选股", value: String(candidates.length) },
    { label: "当前焦点", value: activeCandidate?.name ?? activeWatchlistItem?.name ?? "--" },
    { label: "最近刷新", value: formatDate(generatedAt) },
  ];

  return (
    <>
      {messageContextHolder}
      <div className="workspace-shell">
        <div className="workspace-topbar panel-card">
          <div className="topbar-main">
            <div className="topbar-kicker">A-Share Advisory Desk</div>
            <Title level={3}>自选股操作台</Title>
            <Paragraph className="topbar-note">
              当前部署假设已经切到自托管服务器。前端不再使用离线快照，所有真实数据统一由服务端基于关注池、SQLite 和 Redis 策略管理。
            </Paragraph>
            <Space wrap className="header-meta">
              <Tag color="blue">全站共享关注池</Tag>
              <Tag color="cyan">2-8 周</Tag>
              <Tag color="green">{sourceInfo.label}</Tag>
              <Tag icon={<DatabaseOutlined />}>{runtimeSettings?.storage_engine ?? "SQLite"}</Tag>
              <Tag>{runtimeSettings?.cache_backend ?? "Redis"}</Tag>
            </Space>
          </div>
          <div className="topbar-stats">
            {topbarStats.map((item) => (
              <div key={item.label} className="topbar-stat-item">
                <div className="topbar-stat-label">{item.label}</div>
                <div className="topbar-stat-value" title={item.value}>
                  {item.value}
                </div>
              </div>
            ))}
          </div>
        </div>

        <Card className="command-deck panel-card">
          <Row gutter={[16, 16]}>
            <Col xs={24} xl={6}>
              <div className="deck-section-title">部署与存储</div>
              <Paragraph className="deck-note">{sourceInfo.detail}</Paragraph>
              <Space wrap className="inline-tags">
                <Tag color="green">{runtimeSettings?.deployment_mode ?? "self_hosted_server"}</Tag>
                <Tag>{runtimeSettings?.storage_engine ?? "SQLite"}</Tag>
                <Tag>{runtimeSettings?.cache_backend ?? "Redis"}</Tag>
                <Tag>{runtimeSettings?.provider_selection_mode ?? "runtime_policy"}</Tag>
              </Space>
              <Paragraph className="deck-note compact-note">
                {runtimeSettings?.deployment_notes[0] ?? "服务端负责上游 API 访问、缓存和失败回退，前端只消费统一 contract。"}
              </Paragraph>
            </Col>

            <Col xs={24} xl={6}>
              <div className="deck-section-title">当前焦点</div>
              <Select
                className="full-width"
                value={selectedSymbol ?? undefined}
                placeholder="选择一个自选股"
                options={watchlist.map((item) => ({
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
                  重建样本数据
                </Button>
              </div>
            </Col>

            <Col xs={24} xl={6}>
              <div className="deck-section-title">加入自选</div>
              <Space direction="vertical" size={10} className="full-width">
                <Input
                  value={watchlistSymbolDraft}
                  onChange={(event) => setWatchlistSymbolDraft(event.target.value)}
                  placeholder="输入股票代码，如 600519 或 300750.SZ"
                />
                <Input
                  value={watchlistNameDraft}
                  onChange={(event) => setWatchlistNameDraft(event.target.value)}
                  placeholder="可选：自定义显示名称"
                />
              </Space>
              <div className="deck-actions">
                <Button
                  type="primary"
                  icon={<PlusOutlined />}
                  loading={mutatingWatchlist}
                  onClick={() => void handleAddWatchlist()}
                >
                  加入并分析
                </Button>
              </div>
              <Paragraph className="deck-note compact-note">
                新股票会进入全站共享关注池，后续缓存只围绕这里的标的生效，用来降低 Redis 和上游 API 压力。
              </Paragraph>
            </Col>

            <Col xs={24} xl={6}>
              <div className="deck-section-title">数据源与缓存</div>
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
                      <div className="muted-line">{`失败兜底 ${item.stale_if_error_seconds}s · ${item.warm_on_watchlist ? "仅关注池预热" : "全量"}`}</div>
                    </div>
                  </List.Item>
                )}
              />
              <Paragraph className="deck-note compact-note">
                {runtimeSettings
                  ? `当前按 ${runtimeSettings.provider_order.join(" -> ")} 做运行时选源，失败后自动切换。`
                  : "服务端会根据 AKShare/Tushare 凭据和运行时策略决定实际数据源。"}
              </Paragraph>
              <Space wrap className="inline-tags">
                {(runtimeSettings?.data_sources ?? []).map((item) => (
                  <Tag key={item.provider_name} color={item.credential_configured ? "green" : "gold"}>
                    {`${item.provider_name.toUpperCase()} ${item.credential_configured ? "已配置" : "待配置"}`}
                  </Tag>
                ))}
              </Space>
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
            {
              label: (
                <Space>
                  <SettingOutlined />
                  模型配置
                </Space>
              ),
              value: "config",
            },
          ]}
          onChange={(value) => setView(value as ViewMode)}
        />

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
              <div className="panel-stack">
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
                    </>
                  ) : (
                    <Empty description="没有可展示的候选股" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                  )}
                </Card>

                <Card
                  className="panel-card"
                  title="自选池维护"
                  extra={<Text type="secondary">{`共 ${watchlist.length} 只`}</Text>}
                >
                  {watchlist.length > 0 ? (
                    <List
                      size="small"
                      dataSource={watchlist}
                      renderItem={(item) => (
                        <List.Item>
                          <div className="watchlist-entry">
                            <div className="list-item-row">
                              <div>
                                <strong>{item.name}</strong>
                                <div className="muted-line">{`${item.symbol} · ${item.source_kind === "default_seed" ? "默认样本" : "手动加入"}`}</div>
                              </div>
                              {item.latest_direction ? (
                                <Tag color={directionColor(item.latest_direction)}>
                                  {directionLabels[item.latest_direction] ?? item.latest_direction}
                                </Tag>
                              ) : (
                                <Tag>{item.analysis_status}</Tag>
                              )}
                            </div>
                            <div className="watchlist-meta">
                              <Text type="secondary">{`最近分析 ${formatDate(item.last_analyzed_at ?? item.updated_at)}`}</Text>
                              {item.latest_confidence_label ? <Text type="secondary">{`${item.latest_confidence_label}置信`}</Text> : null}
                            </div>
                            <div className="watchlist-actions">
                              <Button type="link" onClick={() => handleCandidateSelect(item.symbol)}>
                                打开
                              </Button>
                              <Button
                                type="link"
                                icon={<SyncOutlined />}
                                disabled={!canMutateWatchlist}
                                loading={mutatingWatchlist && watchlistMutationSymbol === item.symbol}
                                onClick={() => void handleRefreshWatchlist(item.symbol)}
                              >
                                重分析
                              </Button>
                              <Button
                                type="link"
                                danger
                                icon={<DeleteOutlined />}
                                disabled={!canMutateWatchlist}
                                onClick={() => void handleRemoveWatchlist(item.symbol)}
                              >
                                移除
                              </Button>
                            </div>
                          </div>
                        </List.Item>
                      )}
                    />
                  ) : (
                    <Empty description="当前自选池为空，请先添加股票代码" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                  )}
                </Card>
              </div>
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

        {!loadingShell && view === "config" ? (
          <div className="panel-stack">
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

                <Card className="panel-card" title="新增模型 Key">
                  <Row gutter={[12, 12]}>
                    <Col xs={24} md={12}>
                      <Input value={newKeyName} onChange={(event) => setNewKeyName(event.target.value)} placeholder="名称，如主 OpenAI" />
                    </Col>
                    <Col xs={24} md={12}>
                      <Input value={newKeyProvider} onChange={(event) => setNewKeyProvider(event.target.value)} placeholder="provider，如 openai" />
                    </Col>
                    <Col xs={24} md={12}>
                      <Input value={newKeyModel} onChange={(event) => setNewKeyModel(event.target.value)} placeholder="模型名，如 gpt-4.1-mini" />
                    </Col>
                    <Col xs={24} md={12}>
                      <Input value={newKeyBaseUrl} onChange={(event) => setNewKeyBaseUrl(event.target.value)} placeholder="Base URL，如 https://api.openai.com/v1" />
                    </Col>
                    <Col xs={24} md={12}>
                      <Input.Password value={newKeySecret} onChange={(event) => setNewKeySecret(event.target.value)} placeholder="API Key" />
                    </Col>
                    <Col xs={24} md={12}>
                      <Input value={newKeyPriority} onChange={(event) => setNewKeyPriority(event.target.value)} placeholder="优先级，越小越优先" />
                    </Col>
                  </Row>
                  <div className="deck-actions">
                    <Button type="primary" loading={savingConfig} onClick={() => void handleCreateModelApiKey()}>
                      保存模型 Key
                    </Button>
                  </div>
                </Card>
              </Col>

              <Col xs={24} xl={10}>
                <Card className="panel-card" title="数据源凭据">
                  <List
                    dataSource={runtimeSettings?.data_sources ?? []}
                    renderItem={(item) => {
                      const draft = providerDrafts[item.provider_name] ?? {
                        accessToken: "",
                        baseUrl: item.base_url ?? "",
                        enabled: item.enabled,
                        notes: "",
                      };
                      const saved = providerCredentials.find((credential) => credential.provider_name === item.provider_name);
                      return (
                        <List.Item>
                          <div className="full-width">
                            <div className="list-item-row">
                              <div>
                                <strong>{item.provider_name.toUpperCase()}</strong>
                                <div className="muted-line">{item.role}</div>
                              </div>
                              <Tag color={item.credential_configured ? "green" : "gold"}>
                                {item.credential_configured ? "已配置" : "待配置"}
                              </Tag>
                            </div>
                            <Paragraph className="panel-description">{item.freshness_note}</Paragraph>
                            <Space direction="vertical" size={8} className="full-width">
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
                              <Input.Password
                                value={draft.accessToken}
                                onChange={(event) =>
                                  setProviderDrafts((current) => ({
                                    ...current,
                                    [item.provider_name]: { ...draft, accessToken: event.target.value },
                                  }))
                                }
                                placeholder={item.provider_name === "akshare" ? "可选：接入层 Token / 代理凭据" : "输入 Tushare Token"}
                              />
                              <Input
                                value={draft.notes}
                                onChange={(event) =>
                                  setProviderDrafts((current) => ({
                                    ...current,
                                    [item.provider_name]: { ...draft, notes: event.target.value },
                                  }))
                                }
                                placeholder="备注"
                              />
                            </Space>
                            <div className="deck-actions">
                              <Button
                                onClick={() =>
                                  setProviderDrafts((current) => ({
                                    ...current,
                                    [item.provider_name]: { ...draft, enabled: !draft.enabled },
                                  }))
                                }
                              >
                                {draft.enabled ? "切换为停用" : "切换为启用"}
                              </Button>
                              <Button type="primary" loading={savingConfig} onClick={() => void handleSaveProviderCredential(item.provider_name)}>
                                保存凭据
                              </Button>
                            </div>
                            <Space wrap className="inline-tags">
                              <Tag>{saved?.masked_token ?? "未保存 Token"}</Tag>
                              <Tag>{item.docs_url}</Tag>
                            </Space>
                          </div>
                        </List.Item>
                      );
                    }}
                  />
                </Card>

                <Card className="panel-card" title="统一领域模型与缓存策略">
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
            </Row>
          </div>
        ) : null}
      </div>
    </>
  );
}

export default App;
