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
  Collapse,
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
import type { MouseEvent, ReactNode } from "react";
import { startTransition, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import type {
  CandidateItemView,
  ClaimGateView,
  DataSourceInfo,
  DashboardRuntimeConfig,
  GlossaryEntryView,
  AuthContextResponse,
  ManualResearchRequestView,
  ModelApiKeyView,
  ManualSimulationOrderRequest,
  OperationsDashboardResponse,
  OperationsLaunchReadinessView,
  OperationsResearchValidationView,
  PortfolioNavPointView,
  PortfolioHoldingView,
  PortfolioSummaryView,
  PricePointView,
  RecommendationReplayView,
  RuntimeFieldMappingView,
  SimulationModelAdviceView,
  RuntimeDataSourceView,
  RuntimeOverviewResponse,
  RuntimeSettingsResponse,
  SimulationConfigRequest,
  SimulationTrackStateView,
  SimulationWorkspaceResponse,
  StockDashboardResponse,
  CandidateWorkspaceRow,
  WatchlistItemView,
} from "./types";
import { KlineChart } from "./components/KlineChart";
import { PnlStack } from "./components/PnlStack";
import { KlinePanel } from "./components/KlinePanel";
import { NavSparkline } from "./components/NavSparkline";
import { TrackHoldingsTable } from "./components/TrackHoldingsTable";
import { SimulationTrackCard } from "./components/SimulationTrackCard";
import { CompactAnalysisReport } from "./components/CompactAnalysisReport";
import { PortfolioWorkspace } from "./components/PortfolioWorkspace";
import { buildSettingsTabs } from "./components/SettingsView";
import { buildCandidateColumns } from "./components/CandidateColumns";
import { buildReplayColumns } from "./components/ReplayColumns";
import { buildAddWatchlistOverlay } from "./components/AddWatchlistOverlay";
import { buildOperationsTabs } from "./components/OperationsTabs";
import { MobileAppShell } from "./components/mobile/MobileAppShell";
import { MobileManualOrderModal } from "./components/mobile/MobileManualOrderModal";
import { readAnalysisModelPreference, selectMobileAnalysisModel } from "./components/mobile/modelSelection";
import type { MobileTabKey } from "./components/mobile/types";

import { buildCandidateWorkspaceRows, buildInitialSourceInfo, mergeSourceInfo, resolveSimulationFocusSymbol } from "./utils/data";
import { directionColor, formatDate, formatNumber, formatPercent, formatSignedNumber, simulationAdviceActionLabel, simulationAdvicePolicyLabel, statusColor, valueTone } from "./utils/format";
import { buildPendingDetailMessage, canCompleteManualResearch, canExecuteManualResearch, canFailManualResearch, canRetryManualResearch, candidateValidationSummary, claimGateAlertType, claimGateDescription, claimGateStatusLabel, dataSourceStatusColor, deploymentModeLabel, displayBenchmarkLabel, displayLabelDefinition, displayWindowLabel, fieldMappingLabel, formatMarketFreshness, horizonLabel, manualResearchActionStatusMessage, manualReviewModelLabel, manualReviewStatusLabel, operationsValidationDescription, operationsValidationMessage, parseMultilineItems, portfolioTrackLabel, providerSelectionModeLabel, publicValidationSummary, sanitizeDisplayText, validationStatusLabel, watchlistScopeLabel } from "./utils/labels";
import { directionLabels, factorLabels, manualResearchVerdictOptions } from "./utils/constants";


const { Paragraph, Text, Title } = Typography;
const { TextArea } = Input;

type ViewMode = "candidates" | "stock" | "operations" | "settings";
type ThemeMode = "light" | "dark";


type ViewCard = {
  key: ViewMode;
  label: string;
  description: string;
  icon: ReactNode;
};


function App({ themeMode, onToggleTheme }: { themeMode: ThemeMode; onToggleTheme: () => void }) {
  const initialRuntimeConfig = api.getRuntimeConfig();
  const screens = Grid.useBreakpoint();
  const isMobile = !screens.md;
  const [messageApi, messageContextHolder] = message.useMessage();
  const [view, setView] = useState<ViewMode>("candidates");
  const [runtimeConfig, setRuntimeConfig] = useState<DashboardRuntimeConfig>(initialRuntimeConfig);
  const [sourceInfo, setSourceInfo] = useState<DataSourceInfo>(() => buildInitialSourceInfo());
  const [authContext, setAuthContext] = useState<AuthContextResponse | null>(null);
  const [runtimeSettings, setRuntimeSettings] = useState<RuntimeSettingsResponse | null>(null);
  const [runtimeOverview, setRuntimeOverview] = useState<RuntimeOverviewResponse | null>(null);
  const [watchlist, setWatchlist] = useState<WatchlistItemView[]>([]);
  const [candidates, setCandidates] = useState<CandidateItemView[]>([]);
  const [generatedAt, setGeneratedAt] = useState<string | null>(null);
  const [glossary, setGlossary] = useState<GlossaryEntryView[]>([]);
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [stockActiveTab, setStockActiveTab] = useState("signals");
  const [dashboard, setDashboard] = useState<StockDashboardResponse | null>(null);
  const [operations, setOperations] = useState<OperationsDashboardResponse | null>(null);
  const [simulation, setSimulation] = useState<SimulationWorkspaceResponse | null>(null);
  const [simulationConfigDraft, setSimulationConfigDraft] = useState<SimulationConfigRequest | null>(null);
  const [operationsFocusSymbol, setOperationsFocusSymbol] = useState<string | null>(null);
  const [orderModalSymbol, setOrderModalSymbol] = useState<string | null>(null);
  const [analysisReportSymbol, setAnalysisReportSymbol] = useState<string | null>(null);
  const [analysisReportDashboard, setAnalysisReportDashboard] = useState<StockDashboardResponse | null>(null);
  const [analysisReportLoading, setAnalysisReportLoading] = useState(false);
  const [analysisReportError, setAnalysisReportError] = useState<string | null>(null);
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
  const [analysisAnswer, setAnalysisAnswer] = useState<ManualResearchRequestView | null>(null);
  const [analysisKeyId, setAnalysisKeyId] = useState<number | undefined>(undefined);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [manualResearchAction, setManualResearchAction] = useState<string | null>(null);
  const [completeResearchTarget, setCompleteResearchTarget] = useState<ManualResearchRequestView | null>(null);
  const [completeResearchSummary, setCompleteResearchSummary] = useState("");
  const [completeResearchVerdict, setCompleteResearchVerdict] = useState("mixed");
  const [completeResearchRisks, setCompleteResearchRisks] = useState("");
  const [completeResearchDisagreements, setCompleteResearchDisagreements] = useState("");
  const [completeResearchDecisionNote, setCompleteResearchDecisionNote] = useState("");
  const [completeResearchCitations, setCompleteResearchCitations] = useState("");
  const [completeResearchAnswer, setCompleteResearchAnswer] = useState("");
  const [failResearchTarget, setFailResearchTarget] = useState<ManualResearchRequestView | null>(null);
  const [failResearchReason, setFailResearchReason] = useState("");
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
  const isRootUser = authContext?.actor_role === "root";
  const canUseOperations = isRootUser;
  const canUseSettings = isRootUser;
  const canUseManualResearch = isRootUser;
  const runtimeView = runtimeSettings ?? runtimeOverview;

  const candidateRows = useMemo(
    () => buildCandidateWorkspaceRows(watchlist, candidates),
    [watchlist, candidates],
  );
  const watchlistRows = useMemo(
    () => candidateRows.filter((item) => item.source_kind !== "candidate_only"),
    [candidateRows],
  );
  const candidateOnlyRows = useMemo(
    () => candidateRows.filter((item) => item.source_kind === "candidate_only"),
    [candidateRows],
  );
  const candidateOnlyCount = candidateOnlyRows.length;

  const activeRow = useMemo(
    () => candidateRows.find((item) => item.symbol === selectedSymbol) ?? candidateRows[0] ?? null,
    [candidateRows, selectedSymbol],
  );

  const activeCandidate = activeRow?.candidate ?? null;
  const analysisReportRow = useMemo(
    () => candidateRows.find((item) => item.symbol === analysisReportSymbol) ?? null,
    [analysisReportSymbol, candidateRows],
  );
  const pendingDetailMessage = useMemo(() => buildPendingDetailMessage(activeRow), [activeRow]);
  const symbolNameMap = useMemo(
    () => new Map(candidateRows.map((item) => [item.symbol, item.name] as const)),
    [candidateRows],
  );
  const manualOrderActiveHolding = useMemo(
    () => simulation?.manual_track.portfolio.holdings.find((item) => item.symbol === manualOrderDraft.symbol) ?? null,
    [manualOrderDraft.symbol, simulation],
  );
  const activeSimulationAdvice = useMemo(
    () => simulation?.model_advices.find((item) => item.symbol === manualOrderDraft.symbol) ?? null,
    [manualOrderDraft.symbol, simulation],
  );

  const mergedGlossary = useMemo(() => {
    const entries = [...glossary, ...(dashboard?.glossary ?? [])];
    return Array.from(new Map(entries.map((item) => [item.term, item])).values());
  }, [dashboard?.glossary, glossary]);

  const modelApiKeys = runtimeSettings?.model_api_keys ?? [];
  const providerCredentials = runtimeSettings?.provider_credentials ?? [];

  const navCards: ViewCard[] = [
    {
      key: "candidates",
      label: "关注池",
      description: "查看关注标的、候选信号与快捷操作。",
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
  const availableNavCards = navCards.filter((item) => {
    if (item.key === "operations") return canUseOperations;
    if (item.key === "settings") return canUseSettings;
    return true;
  });

  async function loadAuthContext(retryWithoutActAs = true): Promise<AuthContextResponse> {
    try {
      const payload = await api.getAuthContext();
      setAuthContext(payload);
      return payload;
    } catch (error) {
      const staleActAs = api.getActAsLogin();
      if (retryWithoutActAs && staleActAs) {
        api.setActAsLogin("");
        const payload = await api.getAuthContext();
        setAuthContext(payload);
        return payload;
      }
      throw error;
    }
  }

  async function loadRuntimeSettings(): Promise<void> {
    const payload = await api.getRuntimeSettings();
    setRuntimeSettings(payload);
    setRuntimeOverview(null);
    setAnalysisKeyId((current) => {
      const storedPreference = readAnalysisModelPreference();
      if (storedPreference === "builtin") {
        return undefined;
      }
      if (typeof storedPreference === "number" && payload.model_api_keys.some((item) => item.id === storedPreference)) {
        return storedPreference;
      }
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

  async function loadRuntimeContext(nextAuth?: AuthContextResponse | null): Promise<void> {
    const access = nextAuth ?? authContext;
    if (access?.actor_role === "root") {
      await loadRuntimeSettings();
      return;
    }
    const payload = await api.getRuntimeOverview();
    setRuntimeOverview(payload);
    setRuntimeSettings(null);
    setProviderDrafts({});
    setAnalysisKeyId(undefined);
  }

  function applySimulationWorkspace(workspace: SimulationWorkspaceResponse): void {
    const nextFocusSymbol = resolveSimulationFocusSymbol(workspace);
    setSimulation(workspace);
    setSimulationConfigDraft({
      initial_cash: workspace.configuration.initial_cash,
      watch_symbols: workspace.configuration.watch_symbols,
      focus_symbol: workspace.configuration.focus_symbol ?? null,
      step_interval_seconds: workspace.configuration.step_interval_seconds,
      auto_execute_model: workspace.configuration.auto_execute_model,
    });
    setOperationsFocusSymbol(nextFocusSymbol);
    setManualOrderDraft((current) => ({
      ...current,
      symbol: current.symbol || nextFocusSymbol || workspace.configuration.watch_symbols[0] || "",
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
      const watchlistItem = candidateRows.find((item) => item.symbol === symbol) ?? null;
      if (watchlistItem?.analysis_status === "pending_real_data") {
        setDashboard(null);
        setQuestionDraft("");
        setAnalysisAnswer(null);
        return;
      }
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
    if (!canUseOperations) {
      setOperations(null);
      setSimulation(null);
      setOperationsError("当前账号无运营复盘权限。");
      return;
    }
    setOperationsLoading(true);
    setOperationsError(null);

    const maxRetries = 2;
    let lastError: unknown;

    for (let attempt = 0; attempt <= maxRetries; attempt += 1) {
      try {
        const operationsResult = await api.getOperationsDashboard(symbol);
        setOperations(operationsResult.data);
        setSourceInfo(operationsResult.source);

        if (operationsResult.data.simulation_workspace) {
          applySimulationWorkspace(operationsResult.data.simulation_workspace);
        } else {
          setSimulation(null);
          setOperationsError("运营复盘接口未返回双轨模拟工作区数据。");
        }
        setOperationsLoading(false);
        return;
      } catch (loadError) {
        lastError = loadError;
        const message = loadError instanceof Error ? loadError.message : "";
        const isTimeout = message.includes("请求超时");

        if (isTimeout && attempt < maxRetries) {
          continue;
        }

        setOperations(null);
        setSimulation(null);
        setOperationsError(message || "加载运营复盘工作区失败。");
        setOperationsLoading(false);
        return;
      }
    }

    setOperations(null);
    setSimulation(null);
    const fallbackMessage = lastError instanceof Error ? lastError.message : "加载运营复盘工作区失败。";
    setOperationsError(fallbackMessage);
    setOperationsLoading(false);
  }

  useEffect(() => {
    void (async () => {
      try {
        const access = await loadAuthContext();
        await loadRuntimeContext(access);
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "加载账号上下文失败。");
      }
      await loadShellData();
    })();
  }, []);

  useEffect(() => {
    if (!canUseOperations && view === "operations") {
      setView("candidates");
    }
    if (!canUseSettings && view === "settings") {
      setView("candidates");
    }
  }, [canUseOperations, canUseSettings, view]);

  useEffect(() => {
    if (!canUseManualResearch && stockActiveTab === "followup") {
      setStockActiveTab("signals");
    }
  }, [canUseManualResearch, stockActiveTab]);

  useEffect(() => {
    if (!selectedSymbol) {
      setDashboard(null);
      setOperations(null);
      setSimulation(null);
      setOperationsFocusSymbol(null);
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
    if (!canUseOperations || view !== "operations" || !selectedSymbol) {
      return;
    }
    void loadOperationsData(selectedSymbol);
  }, [canUseOperations, selectedSymbol, view]);

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
    const access = await loadAuthContext();
    await loadRuntimeContext(access);
    const initialSymbol = await loadShellData(preferredSymbol);
    const resolvedSymbol = preferredSymbol ?? initialSymbol ?? selectedSymbol;
    if (resolvedSymbol) {
      await loadDetailData(resolvedSymbol);
      if (access.actor_role === "root" && view === "operations") {
        await loadOperationsData(resolvedSymbol);
      }
    }
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
      if (selectedSymbol && canUseOperations) {
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

  async function handleSimulationFocusChange(symbol: string) {
    const currentConfig = simulationConfigDraft ?? (
      simulation
        ? {
            initial_cash: simulation.configuration.initial_cash,
            watch_symbols: simulation.configuration.watch_symbols,
            focus_symbol: simulation.configuration.focus_symbol ?? null,
            step_interval_seconds: simulation.configuration.step_interval_seconds,
            auto_execute_model: simulation.configuration.auto_execute_model,
          }
        : null
    );
    if (!currentConfig) return;
    if (symbol === (currentConfig.focus_symbol ?? currentConfig.watch_symbols[0] ?? null)) {
      return;
    }

    setSimulationAction("focus");
    setError(null);
    try {
      const response = await api.updateSimulationConfig({
        ...currentConfig,
        focus_symbol: symbol,
      });
      applySimulationWorkspace(response.workspace);
      setOperationsError(null);
    } catch (actionError) {
      const messageText = actionError instanceof Error ? actionError.message : "切换焦点 K 线失败。";
      setError(messageText);
      messageApi.error(messageText);
    } finally {
      setSimulationAction(null);
    }
  }

  function openManualOrderModal(symbol: string, side?: ManualSimulationOrderRequest["side"]) {
    setManualOrderDraft((current) => ({
      ...current,
      symbol,
      side: side ?? current.side,
      quantity: current.symbol === symbol ? current.quantity : 100,
      reason: current.symbol === symbol ? current.reason : "",
      limit_price: current.symbol === symbol ? current.limit_price : null,
    }));
    setOrderModalSymbol(symbol);
  }

  async function openAnalysisReportModal(symbol: string) {
    setAnalysisReportSymbol(symbol);
    setAnalysisReportError(null);
    if (symbol === selectedSymbol && dashboard) {
      setAnalysisReportDashboard(dashboard);
      setAnalysisReportLoading(false);
      return;
    }
    setAnalysisReportDashboard(null);
    setAnalysisReportLoading(true);
    try {
      const stockResult = await api.getStockDashboard(symbol);
      setAnalysisReportDashboard(stockResult.data);
      setSourceInfo((current) => mergeSourceInfo(current, stockResult.source));
    } catch (loadError) {
      setAnalysisReportError(loadError instanceof Error ? loadError.message : "加载精简分析失败。");
    } finally {
      setAnalysisReportLoading(false);
    }
  }

  function closeAnalysisReportModal() {
    setAnalysisReportSymbol(null);
    setAnalysisReportDashboard(null);
    setAnalysisReportLoading(false);
    setAnalysisReportError(null);
  }

  function openFullAnalysisFromReport(symbol: string) {
    closeAnalysisReportModal();
    handleCandidateSelect(symbol, "stock");
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
    setOrderModalSymbol(null);
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






  async function refreshManualResearchContext(targetSymbol: string): Promise<void> {
    if (selectedSymbol === targetSymbol) {
      await loadDetailData(targetSymbol);
    }
    if ((view === "operations" || operations) && (selectedSymbol ?? targetSymbol)) {
      await loadOperationsData(selectedSymbol ?? targetSymbol);
    }
  }

  async function handleSubmitManualResearch() {
    if (!dashboard || !selectedSymbol) return;
    const normalizedQuestion = questionDraft.trim() || "请解释当前建议最容易失效的条件。";
    setAnalysisLoading(true);
    setError(null);
    try {
      const created = await api.createManualResearchRequest({
        symbol: selectedSymbol,
        question: normalizedQuestion,
        trigger_source: "manual_research_ui",
        executor_kind: analysisKeyId ? "configured_api_key" : "builtin_gpt",
        model_api_key_id: analysisKeyId,
      });
      const result = await api.executeManualResearchRequest(created.id, {
        failover_enabled: runtimeSettings?.llm_failover_enabled ?? true,
      });
      await refreshManualResearchContext(selectedSymbol);
      setQuestionDraft(normalizedQuestion);
      setAnalysisAnswer(result);
      messageApi.success(manualResearchActionStatusMessage(result));
    } catch (analysisError) {
      const messageText = analysisError instanceof Error ? analysisError.message : "人工研究请求提交失败。";
      setError(messageText);
      messageApi.error(messageText);
    } finally {
      setAnalysisLoading(false);
    }
  }

  async function handleSelectAnalysisModel(keyId: number | undefined) {
    await selectMobileAnalysisModel({
      keyId, setSavingConfig, setError, loadRuntimeSettings, setAnalysisKeyId, messageApi,
    });
  }

  async function handleExecuteManualResearch(item: ManualResearchRequestView) {
    setManualResearchAction(`execute:${item.id}`);
    setError(null);
    try {
      const result = await api.executeManualResearchRequest(item.id, {
        failover_enabled: runtimeSettings?.llm_failover_enabled ?? true,
      });
      await refreshManualResearchContext(item.symbol);
      messageApi.success(manualResearchActionStatusMessage(result));
      if (item.symbol === selectedSymbol) {
        setAnalysisAnswer(result);
      }
    } catch (actionError) {
      const messageText = actionError instanceof Error ? actionError.message : "执行人工研究请求失败。";
      setError(messageText);
      messageApi.error(messageText);
    } finally {
      setManualResearchAction(null);
    }
  }

  async function handleRetryManualResearch(item: ManualResearchRequestView) {
    setManualResearchAction(`retry:${item.id}`);
    setError(null);
    try {
      const created = await api.retryManualResearchRequest(item.id, {
        requested_by: "dashboard:operator",
      });
      await refreshManualResearchContext(item.symbol);
      messageApi.success("已创建新的人工研究请求。");
      if (item.symbol === selectedSymbol) {
        setAnalysisAnswer(created);
      }
    } catch (actionError) {
      const messageText = actionError instanceof Error ? actionError.message : "重试人工研究请求失败。";
      setError(messageText);
      messageApi.error(messageText);
    } finally {
      setManualResearchAction(null);
    }
  }

  function openCompleteManualResearchModal(item: ManualResearchRequestView) {
    const review = item.manual_llm_review;
    setCompleteResearchTarget(item);
    setCompleteResearchSummary((review.summary || review.raw_answer || "").trim());
    setCompleteResearchVerdict(review.review_verdict || "mixed");
    setCompleteResearchRisks((review.risks || []).join("\n"));
    setCompleteResearchDisagreements((review.disagreements || []).join("\n"));
    setCompleteResearchDecisionNote((review.decision_note || "").trim());
    setCompleteResearchCitations((review.citations || []).join("\n"));
    setCompleteResearchAnswer((review.raw_answer || "").trim());
  }

  function closeCompleteManualResearchModal() {
    setCompleteResearchTarget(null);
    setCompleteResearchSummary("");
    setCompleteResearchVerdict("mixed");
    setCompleteResearchRisks("");
    setCompleteResearchDisagreements("");
    setCompleteResearchDecisionNote("");
    setCompleteResearchCitations("");
    setCompleteResearchAnswer("");
  }

  async function handleConfirmCompleteManualResearch() {
    if (!completeResearchTarget) return;
    const normalizedSummary = completeResearchSummary.trim();
    if (!normalizedSummary) {
      messageApi.error("请先填写研究摘要。");
      return;
    }
    setManualResearchAction(`complete:${completeResearchTarget.id}`);
    setError(null);
    try {
      const result = await api.completeManualResearchRequest(completeResearchTarget.id, {
        summary: normalizedSummary,
        review_verdict: completeResearchVerdict,
        risks: parseMultilineItems(completeResearchRisks),
        disagreements: parseMultilineItems(completeResearchDisagreements),
        decision_note: completeResearchDecisionNote.trim() || null,
        citations: parseMultilineItems(completeResearchCitations),
        answer: completeResearchAnswer.trim() || null,
      });
      await refreshManualResearchContext(completeResearchTarget.symbol);
      if (completeResearchTarget.symbol === selectedSymbol) {
        setAnalysisAnswer(result);
      }
      closeCompleteManualResearchModal();
      messageApi.success(manualResearchActionStatusMessage(result));
    } catch (actionError) {
      const messageText = actionError instanceof Error ? actionError.message : "人工完成研究请求失败。";
      setError(messageText);
      messageApi.error(messageText);
    } finally {
      setManualResearchAction(null);
    }
  }

  function openFailManualResearchModal(item: ManualResearchRequestView) {
    setFailResearchTarget(item);
    setFailResearchReason((item.failure_reason || item.status_note || "").trim());
  }

  function closeFailManualResearchModal() {
    setFailResearchTarget(null);
    setFailResearchReason("");
  }

  async function handleConfirmFailManualResearch() {
    if (!failResearchTarget) return;
    const normalizedReason = failResearchReason.trim();
    if (!normalizedReason) {
      messageApi.error("请填写失败原因。");
      return;
    }
    setManualResearchAction(`fail:${failResearchTarget.id}`);
    setError(null);
    try {
      const result = await api.failManualResearchRequest(failResearchTarget.id, {
        failure_reason: normalizedReason,
      });
      await refreshManualResearchContext(failResearchTarget.symbol);
      if (failResearchTarget.symbol === selectedSymbol) {
        setAnalysisAnswer(result);
      }
      closeFailManualResearchModal();
      messageApi.success(manualResearchActionStatusMessage(result));
    } catch (actionError) {
      const messageText = actionError instanceof Error ? actionError.message : "标记人工研究失败时出错。";
      setError(messageText);
      messageApi.error(messageText);
    } finally {
      setManualResearchAction(null);
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

  function handleMobileTabChange(tab: MobileTabKey) {
    if (tab === "home") {
      setView("candidates");
    } else if (tab === "stock") {
      setView("stock");
    } else if (tab === "operations") {
      setView(canUseOperations ? "operations" : "candidates");
    } else {
      setView(canUseSettings ? "settings" : "candidates");
    }
  }

  function handleMobileSelectSymbol(symbol: string, target: MobileTabKey = "stock") {
    startTransition(() => {
      setSelectedSymbol(symbol);
      handleMobileTabChange(target);
    });
  }

  function openManualResearchWorkspace() {
    if (!canUseManualResearch) {
      return;
    }
    setView("stock");
    setStockActiveTab("followup");
  }

  async function handleSwitchAccount(nextTargetLogin: string) {
    if (!authContext?.can_act_as) {
      return;
    }
    api.setActAsLogin(nextTargetLogin === authContext.actor_login ? "" : nextTargetLogin);
    setAnalysisAnswer(null);
    setDashboard(null);
    setOperations(null);
    setSimulation(null);
    await reloadEverything(selectedSymbol);
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

  const candidateColumns = buildCandidateColumns({
    candidateRows, activeCandidate, glossary, generatedAt,
    pendingRemoval, setPendingRemoval, handleCandidateSelect,
    handleConfirmRemoveWatchlist, mutatingWatchlist,
    addPopoverOpen, setAddPopoverOpen, setWatchlistSymbolDraft,
    setWatchlistNameDraft, handleAddWatchlist,
    watchlistSymbolDraft, watchlistNameDraft,
    selectedSymbol, view, canMutateWatchlist, watchlistMutationSymbol, handleRefreshWatchlist,
  });
  const replayColumns = buildReplayColumns({ glossary: mergedGlossary });

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
                    {dashboard.recommendation.evidence.factor_cards.map((card) => {
                      const showScore = !(
                        (card.factor_key === "manual_review_layer" || card.factor_key === "llm_assessment") &&
                        card.status === "manual_trigger_required"
                      );
                      return (
                        <Card key={card.factor_key} size="small" className="factor-card">
                          <div className="list-item-row">
                            <strong>{factorLabels[card.factor_key] ?? card.factor_key}</strong>
                            {card.direction ? <Tag color={directionColor(card.direction)}>{directionLabels[card.direction] ?? card.direction}</Tag> : null}
                          </div>
                          {showScore && card.score !== undefined && card.score !== null ? (
                            <div className="factor-score">{`分数 ${card.score.toFixed(2)}`}</div>
                          ) : null}
                          <Paragraph className="panel-description">{sanitizeDisplayText(card.headline)}</Paragraph>
                          {card.risk_note ? <Text type="secondary">{sanitizeDisplayText(card.risk_note)}</Text> : null}
                        </Card>
                      );
                    })}
                  </div>
                </Card>
              </Col>
              <Col xs={24} xl={12}>
                <Collapse
                  className="compact-collapse"
                  defaultActiveKey={["why_change", "manual_review"]}
                  items={[
                    {
                      key: "why_change",
                      label: "为什么这次不一样",
                      children: (
                        <div>
                          <Space wrap className="inline-tags">
                            <Tag>{dashboard.change.change_badge}</Tag>
                            <Tag color={directionColor(dashboard.recommendation.claim_gate.public_direction)}>{dashboard.hero.direction_label}</Tag>
                          </Space>
                          <Paragraph className="panel-description">{sanitizeDisplayText(dashboard.change.summary)}</Paragraph>
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
                          {dashboard.recommendation.evidence.supporting_context.length > 0 ? (
                            <>
                              <Title level={5}>补充上下文</Title>
                              <ul className="plain-list">
                                {dashboard.recommendation.evidence.supporting_context.map((item) => (
                                  <li key={item}>{sanitizeDisplayText(item)}</li>
                                ))}
                              </ul>
                            </>
                          ) : null}
                          {dashboard.recommendation.evidence.conflicts.length > 0 ? (
                            <>
                              <Title level={5}>冲突信号</Title>
                              <ul className="plain-list">
                                {dashboard.recommendation.evidence.conflicts.map((item) => (
                                  <li key={item}>{sanitizeDisplayText(item)}</li>
                                ))}
                              </ul>
                            </>
                          ) : null}
                        </div>
                      ),
                    },
                    {
                      key: "when_invalid",
                      label: "何时失效",
                      children: (
                        <div>
                          <Paragraph className="panel-description">{sanitizeDisplayText(dashboard.risk_panel.headline)}</Paragraph>
                          <ul className="plain-list">
                            {dashboard.recommendation.risk.downgrade_conditions.map((item) => (
                              <li key={item}>{sanitizeDisplayText(item)}</li>
                            ))}
                          </ul>
                          <Text type="secondary">{sanitizeDisplayText(dashboard.risk_panel.disclaimer)}</Text>
                        </div>
                      ),
                    },
                    {
                      key: "historical_validation",
                      label: "历史验证层",
                      children: (
                        <div>
                          <Alert
                            className="sub-alert"
                            type={claimGateAlertType(dashboard.recommendation.claim_gate.status)}
                            showIcon
                            message={dashboard.recommendation.claim_gate.headline}
                            description={sanitizeDisplayText(claimGateDescription(dashboard.recommendation.claim_gate))}
                          />
                          <Descriptions size="small" column={1}>
                            <Descriptions.Item label="对外表达">
                              {claimGateStatusLabel(dashboard.recommendation.claim_gate.status)}
                            </Descriptions.Item>
                            <Descriptions.Item label="状态">
                              {validationStatusLabel(dashboard.recommendation.historical_validation.status)}
                            </Descriptions.Item>
                            <Descriptions.Item label="标签定义">
                              {displayLabelDefinition(dashboard.recommendation.historical_validation.label_definition)}
                            </Descriptions.Item>
                            <Descriptions.Item label="基准定义">
                              {displayBenchmarkLabel(dashboard.recommendation.historical_validation.benchmark_definition)}
                            </Descriptions.Item>
                            <Descriptions.Item label="成本定义">
                              {sanitizeDisplayText(dashboard.recommendation.historical_validation.cost_definition)}
                            </Descriptions.Item>
                            <Descriptions.Item label="样本量">
                              {formatNumber(dashboard.recommendation.historical_validation.metrics?.sample_count)}
                            </Descriptions.Item>
                            <Descriptions.Item label="RankIC 均值">
                              {formatSignedNumber(dashboard.recommendation.historical_validation.metrics?.rank_ic_mean)}
                            </Descriptions.Item>
                            <Descriptions.Item label="正超额占比">
                              {formatPercent(dashboard.recommendation.historical_validation.metrics?.positive_excess_rate)}
                            </Descriptions.Item>
                            <Descriptions.Item label="覆盖率">
                              {formatPercent(dashboard.recommendation.historical_validation.metrics?.coverage_ratio)}
                            </Descriptions.Item>
                          </Descriptions>
                          {dashboard.recommendation.historical_validation.note ? (
                            <Alert
                              className="sub-alert"
                              type="warning"
                              showIcon
                              message="验证说明"
                              description={sanitizeDisplayText(dashboard.recommendation.historical_validation.note)}
                            />
                          ) : null}
                        </div>
                      ),
                    },
                    {
                      key: "manual_review",
                      label: "人工研究层",
                      children: (
                        <div>
                          <Space wrap className="inline-tags">
                            <Tag color={statusColor(dashboard.recommendation.manual_llm_review.status)}>
                              {manualReviewStatusLabel(dashboard.recommendation.manual_llm_review.status)}
                            </Tag>
                            {dashboard.recommendation.manual_llm_review.review_verdict ? (
                              <Tag color="blue">{sanitizeDisplayText(dashboard.recommendation.manual_llm_review.review_verdict)}</Tag>
                            ) : null}
                          </Space>
                          <Descriptions size="small" column={{ xs: 1, md: 2 }}>
                            <Descriptions.Item label="研究状态">
                              {manualReviewStatusLabel(dashboard.recommendation.manual_llm_review.status)}
                            </Descriptions.Item>
                            <Descriptions.Item label="产物时间">
                              {formatDate(dashboard.recommendation.manual_llm_review.generated_at)}
                            </Descriptions.Item>
                            <Descriptions.Item label="请求时间">
                              {formatDate(dashboard.recommendation.manual_llm_review.requested_at)}
                            </Descriptions.Item>
                            <Descriptions.Item label="模型标签">
                              {dashboard.recommendation.manual_llm_review.model_label
                                ? manualReviewModelLabel(dashboard.recommendation.manual_llm_review.model_label)
                                : "未指定"}
                            </Descriptions.Item>
                            <Descriptions.Item label="研究结论">
                              {dashboard.recommendation.manual_llm_review.review_verdict
                                ? sanitizeDisplayText(dashboard.recommendation.manual_llm_review.review_verdict)
                                : "未给出"}
                            </Descriptions.Item>
                            <Descriptions.Item label="研究问题">
                              {dashboard.recommendation.manual_llm_review.question
                                ? sanitizeDisplayText(dashboard.recommendation.manual_llm_review.question)
                                : "未提供"}
                            </Descriptions.Item>
                          </Descriptions>
                          {dashboard.recommendation.manual_llm_review.status_note ? (
                            <Alert
                              className="sub-alert"
                              type="info"
                              showIcon
                              message="状态说明"
                              description={sanitizeDisplayText(dashboard.recommendation.manual_llm_review.status_note)}
                            />
                          ) : null}
                          {dashboard.recommendation.manual_llm_review.stale_reason ? (
                            <Alert
                              className="sub-alert"
                              type="warning"
                              showIcon
                              message="结果过期"
                              description={sanitizeDisplayText(dashboard.recommendation.manual_llm_review.stale_reason)}
                            />
                          ) : null}
                          <Paragraph className="panel-description">
                            {dashboard.recommendation.manual_llm_review.summary
                              ? sanitizeDisplayText(dashboard.recommendation.manual_llm_review.summary)
                              : "当前没有额外的人工研究摘要。"}
                          </Paragraph>
                          <div className="manual-research-entry-actions">
                            {canUseManualResearch ? (
                              <>
                                <Button type="primary" size="small" onClick={openManualResearchWorkspace}>
                                  发起人工研究
                                </Button>
                                <Button size="small" onClick={handleCopyPrompt}>
                                  复制追问包
                                </Button>
                                <Text type="secondary">
                                  入口在下方"追问与模拟"标签。留空不选模型 Key 时会直接调用本机 Codex，用 `gpt-5.5` 执行 builtin 研究；选择已配置 Key 时则走对应的外部模型 Key。
                                </Text>
                              </>
                            ) : (
                              <Text type="secondary">
                                人工研究与追问工作流仅对 root 账号开放。
                              </Text>
                            )}
                          </div>
                          {dashboard.recommendation.manual_llm_review.decision_note ? (
                            <Paragraph className="panel-description">
                              {sanitizeDisplayText(dashboard.recommendation.manual_llm_review.decision_note)}
                            </Paragraph>
                          ) : null}
                          {dashboard.recommendation.manual_llm_review.risks.length > 0 ? (
                            <>
                              <Title level={5}>研究层风险提示</Title>
                              <ul className="plain-list">
                                {dashboard.recommendation.manual_llm_review.risks.map((item) => (
                                  <li key={item}>{sanitizeDisplayText(item)}</li>
                                ))}
                              </ul>
                            </>
                          ) : null}
                          {dashboard.recommendation.manual_llm_review.disagreements.length > 0 ? (
                            <>
                              <Title level={5}>与量化层分歧</Title>
                              <ul className="plain-list">
                                {dashboard.recommendation.manual_llm_review.disagreements.map((item) => (
                                  <li key={item}>{sanitizeDisplayText(item)}</li>
                                ))}
                              </ul>
                            </>
                          ) : null}
                          {dashboard.recommendation.manual_llm_review.citations.length > 0 ? (
                            <>
                              <Title level={5}>引用与依据</Title>
                              <ul className="plain-list">
                                {dashboard.recommendation.manual_llm_review.citations.map((item) => (
                                  <li key={item}>{sanitizeDisplayText(item)}</li>
                                ))}
                              </ul>
                            </>
                          ) : null}
                          {dashboard.recommendation.manual_llm_review.source_packet.length > 0 ? (
                            <Alert
                              className="sub-alert"
                              type="info"
                              showIcon
                              message="研究材料"
                              description="当前建议已关联研究材料与验证记录，详情保留在内部台账中。"
                            />
                          ) : null}
                        </div>
                      ),
                    },
                  ]}
                />
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
                <Card size="small" title="人工研究请求工作区" className="sub-panel-card">
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
                    allowClear
                    placeholder="可选：选择要执行的模型 Key；留空则使用本机 Codex builtin GPT"
                    options={modelApiKeys.map((item) => ({
                      value: item.id,
                      label: `${item.name} · ${item.model_name}${item.is_default ? " · 默认" : ""}`,
                    }))}
                    onChange={(value) => setAnalysisKeyId(value)}
                    onClear={() => setAnalysisKeyId(undefined)}
                  />
                  <TextArea
                    rows={5}
                    value={questionDraft}
                    onChange={(event) => setQuestionDraft(event.target.value)}
                    placeholder="输入你要提交给人工研究工作流的问题"
                  />
                  <div className="prompt-actions">
                    <Button type="primary" loading={analysisLoading} onClick={() => void handleSubmitManualResearch()}>
                      {analysisKeyId ? "提交并执行" : "使用 builtin GPT 执行"}
                    </Button>
                    <Button onClick={handleCopyPrompt}>
                      复制追问包
                    </Button>
                    <Text type="secondary">
                      这里的默认动作已经改成 durable manual research request。选择模型 Key 时会立即执行；不选时会直接调用本机 Codex 的 builtin `gpt-5.5` 执行。只有本机 Codex 不可用时，才会保留请求并提示当前环境尚未配置 builtin executor。
                    </Text>
                  </div>
                  {analysisAnswer ? (
                    <Card size="small" className="prompt-packet-card">
                      <Title level={5}>最近一次请求回执</Title>
                      <Descriptions size="small" column={1}>
                        <Descriptions.Item label="状态">
                          {manualReviewStatusLabel(analysisAnswer.status)}
                        </Descriptions.Item>
                        <Descriptions.Item label="问题">
                          {sanitizeDisplayText(analysisAnswer.question)}
                        </Descriptions.Item>
                      </Descriptions>
                      {analysisAnswer.manual_llm_review.summary ? (
                        <Paragraph className="panel-description">
                          {sanitizeDisplayText(analysisAnswer.manual_llm_review.summary)}
                        </Paragraph>
                      ) : null}
                      {analysisAnswer.manual_llm_review.raw_answer ? (
                        <Paragraph className="panel-description">
                          {sanitizeDisplayText(analysisAnswer.manual_llm_review.raw_answer)}
                        </Paragraph>
                      ) : null}
                      <Space wrap className="inline-tags">
                        {analysisAnswer.selected_key ? (
                          <Tag color="blue">{analysisAnswer.selected_key.name}</Tag>
                        ) : null}
                        {analysisAnswer.selected_key ? (
                          <Tag>{analysisAnswer.selected_key.model_name}</Tag>
                        ) : null}
                        <Tag color={statusColor(analysisAnswer.status)}>
                          {manualReviewStatusLabel(analysisAnswer.status)}
                        </Tag>
                        {analysisAnswer.failover_used ? <Tag color="orange">已故障切换</Tag> : null}
                        {analysisAnswer.artifact_id ? (
                          <Tag color="blue">已生成研究记录</Tag>
                        ) : null}
                      </Space>
                      <div className="deck-actions">
                        <Button
                          disabled={!canExecuteManualResearch(analysisAnswer)}
                          loading={manualResearchAction === `execute:${analysisAnswer.id}`}
                          onClick={() => void handleExecuteManualResearch(analysisAnswer)}
                        >
                          执行请求
                        </Button>
                        <Button
                          disabled={!canCompleteManualResearch(analysisAnswer)}
                          loading={manualResearchAction === `complete:${analysisAnswer.id}`}
                          onClick={() => openCompleteManualResearchModal(analysisAnswer)}
                        >
                          人工完成
                        </Button>
                        <Button
                          danger
                          disabled={!canFailManualResearch(analysisAnswer)}
                          loading={manualResearchAction === `fail:${analysisAnswer.id}`}
                          onClick={() => openFailManualResearchModal(analysisAnswer)}
                        >
                          标记失败
                        </Button>
                        <Button
                          disabled={!canRetryManualResearch(analysisAnswer)}
                          loading={manualResearchAction === `retry:${analysisAnswer.id}`}
                          onClick={() => void handleRetryManualResearch(analysisAnswer)}
                        >
                          Retry
                        </Button>
                      </div>
                      {analysisAnswer.status_note ? (
                        <Alert
                          className="sub-alert"
                          type="info"
                          showIcon
                          message="状态说明"
                          description={sanitizeDisplayText(analysisAnswer.status_note)}
                        />
                      ) : null}
                      {analysisAnswer.failure_reason && analysisAnswer.failure_reason !== analysisAnswer.status_note ? (
                        <Alert
                          className="sub-alert"
                          type="error"
                          showIcon
                          message="失败原因"
                          description={sanitizeDisplayText(analysisAnswer.failure_reason)}
                        />
                      ) : null}
                      {analysisAnswer.stale_reason ? (
                        <Alert
                          className="sub-alert"
                          type="warning"
                          showIcon
                          message="结果过期"
                          description={sanitizeDisplayText(analysisAnswer.stale_reason)}
                        />
                      ) : null}
                    </Card>
                  ) : null}
                  <Card size="small" className="prompt-packet-card">
                    <Title level={5}>证据包提示</Title>
                    <ul className="plain-list">
                      {dashboard.follow_up.evidence_packet.map((item) => (
                        <li key={item}>{sanitizeDisplayText(item)}</li>
                      ))}
                    </ul>
                  </Card>
                  <Card size="small" className="prompt-packet-card">
                    <Title level={5}>研究验证包</Title>
                    <Descriptions size="small" column={1}>
                      <Descriptions.Item label="验证状态">
                        {validationStatusLabel(dashboard.follow_up.research_packet.validation_status)}
                      </Descriptions.Item>
                      <Descriptions.Item label="验证样本量">
                        {formatNumber(dashboard.follow_up.research_packet.validation_sample_count)}
                      </Descriptions.Item>
                      <Descriptions.Item label="RankIC 均值">
                        {formatSignedNumber(dashboard.follow_up.research_packet.validation_rank_ic_mean)}
                      </Descriptions.Item>
                      <Descriptions.Item label="正超额占比">
                        {formatPercent(dashboard.follow_up.research_packet.validation_positive_excess_rate)}
                      </Descriptions.Item>
                      <Descriptions.Item label="人工研究">
                        {manualReviewStatusLabel(dashboard.follow_up.research_packet.manual_review_status)}
                      </Descriptions.Item>
                      <Descriptions.Item label="研究结论">
                        {dashboard.follow_up.research_packet.manual_review_review_verdict
                          ? sanitizeDisplayText(dashboard.follow_up.research_packet.manual_review_review_verdict)
                          : "未给出"}
                      </Descriptions.Item>
                      <Descriptions.Item label="人工研究时间">
                        {formatDate(dashboard.follow_up.research_packet.manual_review_generated_at)}
                      </Descriptions.Item>
                    </Descriptions>
                    {dashboard.follow_up.research_packet.manual_review_status_note ? (
                      <Alert
                        className="section-alert"
                        type="info"
                        showIcon
                        message="研究状态说明"
                        description={sanitizeDisplayText(dashboard.follow_up.research_packet.manual_review_status_note)}
                      />
                    ) : null}
                    {dashboard.follow_up.research_packet.manual_review_stale_reason ? (
                      <Alert
                        className="section-alert"
                        type="warning"
                        showIcon
                        message="研究结果过期"
                        description={sanitizeDisplayText(dashboard.follow_up.research_packet.manual_review_stale_reason)}
                      />
                    ) : null}
                    {dashboard.follow_up.research_packet.validation_note ? (
                      <Alert
                        className="section-alert"
                        type="warning"
                        showIcon
                        message="验证说明"
                        description={sanitizeDisplayText(dashboard.follow_up.research_packet.validation_note)}
                      />
                    ) : null}
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
                                <strong>{order.order_source === "manual" ? "用户轨道" : "模型轨道"}</strong>
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
  const visibleStockTabItems = canUseManualResearch
    ? stockTabItems
    : stockTabItems.filter((item) => item.key !== "followup");

  const portfolioTabs = operations?.portfolios.map((portfolio) => ({
    key: portfolio.portfolio_key,
    label: portfolioTrackLabel(portfolio),
    children: <PortfolioWorkspace portfolio={portfolio} />,
  })) ?? [];
  const operationsTabItems = buildOperationsTabs({
    operations,
    simulation,
    simulationConfigDraft, setSimulationConfigDraft,
    candidateRows,
    symbolNameMap,
    replayColumns,
    portfolioTabs,
    handleCandidateSelect, handleSaveSimulationConfig,
    handleExecuteManualResearch, handleRetryManualResearch,
    openCompleteManualResearchModal, openFailManualResearchModal,
    messageApi,
    simulationAction, setSimulationAction,
    operationsFocusSymbol, setOperationsFocusSymbol,
    loadingDetail, setLoadingDetail,
    setSelectedSymbol, setStockActiveTab, setView,
    setOperations, setOperationsLoading, setOperationsError,
    manualResearchAction, setManualResearchAction,
  });
  const addWatchlistOverlay = buildAddWatchlistOverlay({
    addPopoverOpen, setAddPopoverOpen,
    watchlistSymbolDraft, setWatchlistSymbolDraft,
    watchlistNameDraft, setWatchlistNameDraft,
    handleAddWatchlist, canMutateWatchlist, mutatingWatchlist,
  });
  const settingsTabItems = canUseSettings ? buildSettingsTabs({
    runtimeSettings,
    sourceInfo,
    generatedAt,
    modelApiKeys,
    providerCredentials,
    newKeyName, setNewKeyName,
    newKeyProvider, setNewKeyProvider,
    newKeyModel, setNewKeyModel,
    newKeyBaseUrl, setNewKeyBaseUrl,
    newKeySecret, setNewKeySecret,
    newKeyPriority, setNewKeyPriority,
    providerDrafts, setProviderDrafts,
    savingConfig, setSavingConfig,
    messageApi, loadRuntimeSettings, setError,
  }) : [];
  if (isMobile) {
    return (
      <>
        {messageContextHolder}
        <MobileAppShell
          themeMode={themeMode}
          loadingShell={loadingShell}
          loadingDetail={loadingDetail}
          operationsLoading={operationsLoading}
          error={error}
          operationsError={operationsError}
          candidateRows={candidateRows}
          activeRow={activeRow}
          selectedSymbol={selectedSymbol}
          dashboard={dashboard}
          operations={operations}
          simulation={simulation}
          sourceInfo={sourceInfo}
          authContext={authContext}
          isRootUser={isRootUser}
          canUseOperations={canUseOperations}
          canUseSettings={canUseSettings}
          canUseManualResearch={canUseManualResearch}
          runtimeSettings={runtimeSettings}
          runtimeOverview={runtimeOverview}
          modelApiKeys={modelApiKeys}
          generatedAt={generatedAt}
          addWatchlistOverlay={addWatchlistOverlay}
          addPopoverOpen={addPopoverOpen}
          setAddPopoverOpen={setAddPopoverOpen}
          mutatingWatchlist={mutatingWatchlist}
          watchlistMutationSymbol={watchlistMutationSymbol}
          questionDraft={questionDraft}
          setQuestionDraft={setQuestionDraft}
          analysisKeyId={analysisKeyId}
          setAnalysisKeyId={setAnalysisKeyId}
          analysisLoading={analysisLoading}
          onToggleTheme={onToggleTheme}
          onSelectAnalysisModel={handleSelectAnalysisModel}
          onRefresh={() => void handleRefresh()}
          onRefreshWatchlist={(symbol) => void handleRefreshWatchlist(symbol)}
          onSelectSymbol={handleMobileSelectSymbol}
          onRequestRemoveWatchlist={setPendingRemoval}
          onOpenManualOrder={openManualOrderModal}
          onTabChange={handleMobileTabChange}
          onSubmitManualResearch={() => void handleSubmitManualResearch()}
          onCopyPrompt={() => void handleCopyPrompt()}
          onSwitchAccount={(login) => void handleSwitchAccount(login)}
          onLoadOperations={() => {
            if (selectedSymbol) {
              void loadOperationsData(selectedSymbol);
            }
          }}
        />
        <MobileManualOrderModal
          open={Boolean(orderModalSymbol && simulation)}
          themeMode={themeMode}
          title={orderModalSymbol ? `用户轨道操作 · ${symbolNameMap.get(orderModalSymbol) ?? orderModalSymbol}` : "用户轨道操作"}
          watchSymbols={simulation?.session.watch_symbols ?? []}
          symbolNameMap={symbolNameMap}
          draft={manualOrderDraft}
          setDraft={setManualOrderDraft}
          activeHolding={manualOrderActiveHolding}
          activeAdvice={activeSimulationAdvice}
          submitting={simulationAction === "manual-order"}
          onCancel={() => setOrderModalSymbol(null)}
          onSubmit={() => void handleSubmitManualOrder()}
        />
        <Modal
          open={Boolean(pendingRemoval)}
          centered
          title={pendingRemoval ? `移除 ${pendingRemoval.name}` : "移除标的"}
          okText="确认移除"
          cancelText="取消"
          okButtonProps={{ danger: true }}
          confirmLoading={mutatingWatchlist && watchlistMutationSymbol === pendingRemoval?.symbol}
          onCancel={() => setPendingRemoval(null)}
          onOk={() => void handleConfirmRemoveWatchlist()}
        >
          <Paragraph className="panel-description">
            该标的会从当前账号自选中移除。若没有其他账号继续关注，它的主动刷新资格也会一并取消。确认继续吗？
          </Paragraph>
        </Modal>
      </>
    );
  }

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
                  {isRootUser
                    ? "当前为 root 运营视角，可切换账号空间查看独立自选与模拟盘。"
                    : "当前账号只展示自己的自选与模拟盘空间。"}
                </Paragraph>
                {authContext?.can_act_as && authContext.target_login !== authContext.actor_login ? (
                  <Alert
                    showIcon
                    type="warning"
                    className="sub-alert"
                    message={`当前正在代看 ${authContext.target_login} 空间`}
                    description="这里不会显示 root 自己的持仓、自选和复盘时间线。若要回到 root 自己的空间，请将上方账号切回 root。"
                  />
                ) : null}
                <Space wrap className="header-meta">
                  <Tag color="cyan">{sourceInfo.label}</Tag>
                  <Tag color={isRootUser ? "gold" : "blue"}>{`空间 ${authContext?.target_login ?? "--"}`}</Tag>
                  <Tag icon={<DatabaseOutlined />}>{runtimeView?.storage_engine ?? "SQLite"}</Tag>
                  <Tag>{runtimeView?.cache_backend ?? "Redis"}</Tag>
                  <Tag>{runtimeConfig.apiBase || "同源 API"}</Tag>
                </Space>
              </div>

              <div className="hero-actions-panel">
                <div className="hero-refresh-note">{`最近刷新 ${formatDate(generatedAt)}`}</div>
                <div className="hero-action-row">
                  {authContext?.can_act_as ? (
                    <Select
                      className="global-focus-select"
                      value={authContext.target_login}
                      placeholder="切换账号空间"
                      options={authContext.visible_account_spaces.map((item) => ({
                        value: item.account_login,
                        label: `${item.account_login}${item.account_login === authContext.actor_login ? " · 当前登录" : ""}`,
                      }))}
                      onChange={(value) => void handleSwitchAccount(value)}
                    />
                  ) : null}
                  <Select
                    className="global-focus-select"
                    value={selectedSymbol ?? undefined}
                    placeholder="切换工作区标的"
                    options={candidateRows.map((item) => ({
                      value: item.symbol,
                      label: `${item.name} · ${item.symbol}`,
                    }))}
                    onChange={(value) => handleCandidateSelect(value)}
                  />
                  <Button icon={<ReloadOutlined />} onClick={() => void handleRefresh()}>
                    刷新
                  </Button>
                  <Button className="theme-toggle-button" icon={themeMode === "dark" ? <SunOutlined /> : <MoonOutlined />} onClick={onToggleTheme}>
                    {themeMode === "dark" ? "浅色模式" : "夜间模式"}
                  </Button>
                </div>
              </div>
            </div>
          </div>

          <div className="workspace-nav">
            {availableNavCards.map((item) => (
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
                      {activeCandidate ? <Tag color={directionColor(activeCandidate.display_direction)}>{activeCandidate.display_direction_label}</Tag> : null}
                      {activeCandidate ? <Tag>{`${activeCandidate.confidence_label}置信`}</Tag> : null}
                      {activeCandidate ? <Tag>{displayWindowLabel(activeCandidate.window_definition)}</Tag> : null}
                      {activeCandidate ? <Tag>{horizonLabel(activeCandidate.target_horizon_label)}</Tag> : null}
                      {activeCandidate ? (
                        <Tag color={claimGateAlertType(activeCandidate.claim_gate.status)}>
                          {claimGateStatusLabel(activeCandidate.claim_gate.status)}
                        </Tag>
                      ) : null}
                      {activeCandidate ? (
                        <Tag color={activeCandidate.validation_status === "verified" ? "green" : "gold"}>
                          {validationStatusLabel(activeCandidate.validation_status)}
                        </Tag>
                      ) : null}
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
                      {activeCandidate?.summary
                        ? sanitizeDisplayText(activeCandidate.summary)
                        : "当前标的已经在关注池中，但还没有最新候选信号，可在右侧操作里触发重分析。"}
                    </Paragraph>
                    {activeCandidate ? (
                      <Alert
                        showIcon
                        className="sub-alert"
                        type={claimGateAlertType(activeCandidate.claim_gate.status)}
                        message={activeCandidate.claim_gate.headline}
                        description={sanitizeDisplayText(claimGateDescription(activeCandidate.claim_gate))}
                      />
                    ) : null}
                    <Descriptions size="small" column={{ xs: 1, md: 2, xl: 4 }}>
                      <Descriptions.Item label="当前触发点">
                        {activeCandidate?.why_now ? sanitizeDisplayText(activeCandidate.why_now) : "等待更新"}
                      </Descriptions.Item>
                      <Descriptions.Item label="主要风险">
                        {activeCandidate?.primary_risk
                          ? sanitizeDisplayText(activeCandidate.primary_risk)
                          : activeRow.last_error
                            ? sanitizeDisplayText(activeRow.last_error)
                            : "暂无额外风险提示"}
                      </Descriptions.Item>
                      <Descriptions.Item label="最近变化">
                        {activeCandidate?.change_summary
                          ? sanitizeDisplayText(activeCandidate.change_summary)
                          : sanitizeDisplayText(activeRow.analysis_status)}
                      </Descriptions.Item>
                      <Descriptions.Item label="验证说明">
                        {publicValidationSummary(activeCandidate?.validation_note, activeCandidate?.validation_status)}
                      </Descriptions.Item>
                      <Descriptions.Item label="验证摘要">
                        {candidateValidationSummary(activeCandidate)}
                      </Descriptions.Item>
                      <Descriptions.Item label="最近分析">{formatDate(activeRow.last_analyzed_at ?? activeRow.updated_at)}</Descriptions.Item>
                    </Descriptions>
                  </>
                ) : (
                  <Empty description="当前没有可展示的标的" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                )}
              </Card>

              <Card
                className="panel-card"
                title="当前账号自选"
                extra={(
                  <Space wrap>
                    <Text type="secondary">{`${watchlistRows.length} 只`}</Text>
                    <Popover
                      open={addPopoverOpen}
                      onOpenChange={setAddPopoverOpen}
                      trigger="click"
                      placement="bottomRight"
                      content={addWatchlistOverlay}
                    >
                      <Button shape="circle" type="primary" icon={<PlusOutlined />} />
                    </Popover>
                  </Space>
                )}
              >
                {watchlistRows.length === 0 ? (
                  <Alert
                    showIcon
                    type="info"
                    message="当前账号自选为空"
                    description={candidateOnlyCount > 0 ? "当前页下方会单独展示全局候选池，便于你挑选后加入自己的自选。" : "请先添加股票代码，建立当前账号自己的自选池。"}
                  />
                ) : (
                  <Table
                    rowKey="symbol"
                    size="middle"
                    pagination={false}
                    dataSource={watchlistRows}
                    columns={candidateColumns}
                    scroll={{ x: 1240 }}
                    tableLayout="fixed"
                    onRow={(record) => ({
                      onClick: () => handleCandidateSelect(record.symbol),
                    })}
                    rowClassName={(record) => (record.symbol === activeRow?.symbol ? "candidate-row-active" : "")}
                    locale={{ emptyText: "当前账号还没有自选股" }}
                  />
                )}
              </Card>

              <Card
                className="panel-card"
                title="全局候选池"
                extra={<Text type="secondary">{`${candidateOnlyCount} 只`}</Text>}
              >
                {candidateOnlyRows.length === 0 ? (
                  <Empty description="当前没有额外全局候选股" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                ) : (
                  <Table
                    rowKey="symbol"
                    size="middle"
                    pagination={false}
                    dataSource={candidateOnlyRows}
                    columns={candidateColumns}
                    scroll={{ x: 1240 }}
                    tableLayout="fixed"
                    onRow={(record) => ({
                      onClick: () => handleCandidateSelect(record.symbol),
                    })}
                    rowClassName={(record) => (record.symbol === activeRow?.symbol ? "candidate-row-active" : "")}
                    locale={{ emptyText: "当前没有额外候选股" }}
                  />
                )}
              </Card>
            </div>
          ) : null}

          {!loadingShell && view === "stock" ? (
            loadingDetail ? (
              <Card className="panel-card loading-card">
                <Skeleton active paragraph={{ rows: 10 }} />
              </Card>
            ) : !dashboard && pendingDetailMessage ? (
              <Card
                className="panel-card"
                title={activeRow ? `${activeRow.name} · ${activeRow.symbol}` : "单票分析"}
                extra={activeRow ? <Tag color="gold">等待真实行情</Tag> : null}
              >
                <Alert
                  showIcon
                  type="warning"
                  className="status-alert"
                  message="面板暂未生成"
                  description={pendingDetailMessage}
                />
                <Descriptions size="small" column={1} style={{ marginTop: 16 }}>
                  <Descriptions.Item label="当前状态">pending_real_data</Descriptions.Item>
                  <Descriptions.Item label="最近更新时间">{formatDate(activeRow?.updated_at)}</Descriptions.Item>
                  <Descriptions.Item label="建议操作">修复行情抓取后点击"重分析"重新生成面板。</Descriptions.Item>
                </Descriptions>
              </Card>
            ) : !dashboard ? (
              <Card className="panel-card">
                <Empty description="当前没有可展示的单票分析" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              </Card>
            ) : (
              <div className="panel-stack">
                <div className="metric-strip">
                  <div className="metric-strip-item">
                    <span>最新收盘</span>
                    <strong>{formatNumber(dashboard.hero.latest_close)}</strong>
                  </div>
                  <div className="metric-strip-item">
                    <span>日涨跌</span>
                    <strong className={`value-${valueTone(dashboard.hero.day_change_pct)}`}>{formatPercent(dashboard.hero.day_change_pct)}</strong>
                  </div>
                  <div className="metric-strip-item">
                    <span>置信表达</span>
                    <strong>{dashboard.recommendation.confidence_expression}</strong>
                  </div>
                  <div className="metric-strip-item">
                    <span>最近刷新</span>
                    <strong>{formatDate(dashboard.hero.last_updated)}</strong>
                  </div>
                </div>

                <Row gutter={[16, 16]} className="equal-height-row">
                  <Col xs={24} xl={16}>
                    <Card
                      className="panel-card"
                      title={`${dashboard.stock.name} · ${dashboard.stock.symbol}`}
                      extra={
                        <Space wrap className="inline-tags">
                          <Tag color={directionColor(dashboard.recommendation.claim_gate.public_direction)}>{dashboard.hero.direction_label}</Tag>
                          {dashboard.recommendation.claim_gate.public_direction !== dashboard.recommendation.direction ? (
                            <Tag>{`模型原始方向：${directionLabels[dashboard.recommendation.direction] ?? dashboard.recommendation.direction}`}</Tag>
                          ) : null}
                          <Tag color={claimGateAlertType(dashboard.recommendation.claim_gate.status)}>
                            {claimGateStatusLabel(dashboard.recommendation.claim_gate.status)}
                          </Tag>
                          <Tag>{`${dashboard.recommendation.confidence_label}置信`}</Tag>
                        </Space>
                      }
                    >
                      <Paragraph className="panel-description">{sanitizeDisplayText(dashboard.recommendation.summary)}</Paragraph>
                      <KlinePanel
                        title={`${dashboard.stock.name} · ${dashboard.stock.symbol} K 线`}
                        points={dashboard.price_chart}
                        lastUpdated={dashboard.hero.last_updated}
                        stockName={dashboard.stock.name}
                        isMobile={isMobile}
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
                        <Descriptions.Item label="观察窗口">
                          {displayWindowLabel(dashboard.recommendation.historical_validation.window_definition)}
                        </Descriptions.Item>
                        <Descriptions.Item label="目标 horizon">
                          {horizonLabel(dashboard.recommendation.core_quant.target_horizon_label)}
                        </Descriptions.Item>
                        <Descriptions.Item label="对外表达">
                          {claimGateStatusLabel(dashboard.recommendation.claim_gate.status)}
                        </Descriptions.Item>
                        <Descriptions.Item label="验证状态">
                          {validationStatusLabel(dashboard.recommendation.historical_validation.status)}
                        </Descriptions.Item>
                        <Descriptions.Item label="数据时间">{formatDate(dashboard.recommendation.core_quant.as_of_time)}</Descriptions.Item>
                        <Descriptions.Item label="生成时间">{formatDate(dashboard.recommendation.core_quant.available_time)}</Descriptions.Item>
                        <Descriptions.Item label="模型版本">{dashboard.recommendation.core_quant.model_version}</Descriptions.Item>
                      </Descriptions>
                      <Alert
                        className="sub-alert"
                        type={claimGateAlertType(dashboard.recommendation.claim_gate.status)}
                        showIcon
                        message={dashboard.recommendation.claim_gate.headline}
                        description={sanitizeDisplayText(claimGateDescription(dashboard.recommendation.claim_gate))}
                      />
                      {dashboard.recommendation.historical_validation.note ? (
                        <Alert
                          className="sub-alert"
                          type="warning"
                          showIcon
                          message="验证说明"
                          description={sanitizeDisplayText(dashboard.recommendation.historical_validation.note)}
                        />
                      ) : null}
                      <Collapse
                        ghost
                        className="summary-block-compact"
                        defaultActiveKey={["drivers"]}
                        items={[
                          {
                            key: "drivers",
                            label: <span style={{ fontWeight: 600 }}>核心驱动</span>,
                            children: (
                              <ul className="plain-list">
                                {dashboard.recommendation.evidence.primary_drivers.map((item) => (
                                  <li key={item}>{sanitizeDisplayText(item)}</li>
                                ))}
                              </ul>
                            ),
                          },
                          {
                            key: "risks",
                            label: <span style={{ fontWeight: 600 }}>反向风险</span>,
                            children: (
                              <ul className="plain-list">
                                {dashboard.recommendation.risk.risk_flags.map((item) => (
                                  <li key={item}>{sanitizeDisplayText(item)}</li>
                                ))}
                              </ul>
                            ),
                          },
                        ]}
                      />
                      {dashboard.recommendation.risk.coverage_gaps.length > 0 ? (
                        <Alert
                          className="sub-alert"
                          type="info"
                          showIcon
                          message="当前覆盖缺口"
                          description={dashboard.recommendation.risk.coverage_gaps.map((item) => sanitizeDisplayText(item)).join(" ")}
                        />
                      ) : null}
                    </Card>
                  </Col>
                </Row>

                <Card className="panel-card">
                  <Tabs activeKey={stockActiveTab} onChange={setStockActiveTab} items={visibleStockTabItems} />
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
                    message="运营复盘工作区加载失败"
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
                        title="最新行情"
                        value={formatMarketFreshness(
                          operations?.data_latency_seconds ?? simulation?.session.data_latency_seconds,
                          simulation?.session.last_market_data_at ?? operations?.overview.run_health.last_market_data_at,
                          true,
                        )}
                      />
                    </Card>
                  </Col>
                  <Col xs={24} md={12} xl={6}>
                    <Card className="panel-card metric-card">
                      <Statistic
                        title="复盘状态"
                        value={operations ? validationStatusLabel(operations.overview.research_validation.status) : "--"}
                      />
                    </Card>
                  </Col>
                </Row>

                {simulation ? (
                  <>
                    {operations?.overview.research_validation.note ? (
                      <Alert
                        type="warning"
                        showIcon
                        className="panel-card"
                        message={operationsValidationMessage(operations.overview.research_validation.status)}
                        description={operationsValidationDescription(operations.overview.research_validation)}
                      />
                    ) : null}
                    <Row gutter={[16, 16]}>
                      <Col xs={24} xl={14}>
                        <Card
                          className="panel-card operations-command-card"
                          title="双轨同步模拟台"
                          extra={<Tag color={statusColor(simulation.session.status)}>{simulation.session.status_label}</Tag>}
                        >
                          <Paragraph className="panel-description">
                            用户轨道与模型轨道共享时间线推进，当前表格默认展示当前模拟股票池。默认会跟随关注池；如果你改过模拟配置，这里显示的是当前配置内的股票池。
                          </Paragraph>
                          <Space wrap className="inline-tags">
                            <Tag>{`模拟池 ${simulation.session.watch_symbols.length} 只`}</Tag>
                            <Tag>{`初始资金 ${formatNumber(simulation.session.initial_cash)}`}</Tag>
                            <Tag>{simulation.session.fill_rule_label}</Tag>
                            <Tag color="blue">{`行情 ${simulation.session.market_data_timeframe ?? "5min"}`}</Tag>
                            <Tag color="geekblue">{`决策 ${Math.round((simulation.session.step_interval_seconds ?? 1800) / 60)} 分钟`}</Tag>
                            <Tag>{`重启 ${simulation.session.restart_count} 次`}</Tag>
                          </Space>
                          <div className="deck-actions">
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
                          </div>
                          <Descriptions size="small" column={{ xs: 1, md: 2, xl: 3 }} className="info-grid">
                            <Descriptions.Item label="推进规则">{simulation.session.step_trigger_label}</Descriptions.Item>
                            <Descriptions.Item label="焦点标的">{operationsFocusSymbol ?? "--"}</Descriptions.Item>
                            <Descriptions.Item label="最近数据">{formatDate(simulation.session.last_data_time)}</Descriptions.Item>
                            <Descriptions.Item label="最近行情">{formatDate(simulation.session.last_market_data_at ?? simulation.session.last_data_time)}</Descriptions.Item>
                            <Descriptions.Item label="行情来源">{simulation.session.intraday_source_status?.provider_label ?? "未同步"}</Descriptions.Item>
                            <Descriptions.Item label="行情刷新">
                              {formatMarketFreshness(
                                simulation.session.data_latency_seconds,
                                simulation.session.last_market_data_at ?? simulation.session.last_data_time,
                              )}
                            </Descriptions.Item>
                            <Descriptions.Item label="启动时间">{formatDate(simulation.session.started_at)}</Descriptions.Item>
                            <Descriptions.Item label="最近恢复">{formatDate(simulation.session.last_resumed_at)}</Descriptions.Item>
                            <Descriptions.Item label="最近暂停">{formatDate(simulation.session.paused_at)}</Descriptions.Item>
                          </Descriptions>
                        </Card>
                      </Col>
                      <Col xs={24} xl={10}>
                        <Card
                          className="panel-card"
                          title="焦点 K 线"
                          extra={(
                            <Select
                              className="operations-focus-select"
                              value={operationsFocusSymbol ?? undefined}
                              options={simulation.session.watch_symbols.map((symbol) => ({
                                value: symbol,
                                label: `${symbolNameMap.get(symbol) ?? symbol} · ${symbol}`,
                              }))}
                              onChange={(value) => void handleSimulationFocusChange(value)}
                            />
                          )}
                        >
                          <KlinePanel
                            title={`${simulation.kline.stock_name ?? simulation.kline.symbol ?? "焦点标的"} K 线`}
                            points={simulation.kline.points}
                            lastUpdated={simulation.kline.last_updated}
                            stockName={simulation.kline.stock_name ?? simulation.kline.symbol}
                            isMobile={isMobile}
                          />
                        </Card>
                      </Col>
                    </Row>

                    <Row gutter={[16, 16]}>
                      <Col xs={24} xxl={12}>
                        <SimulationTrackCard
                          track={simulation.manual_track}
                          watchSymbols={simulationConfigDraft?.watch_symbols ?? simulation.session.watch_symbols}
                          candidateRows={candidateRows}
                          symbolNameMap={symbolNameMap}
                          modelAdvices={simulation.model_advices}
                          activeSymbol={operationsFocusSymbol}
                          onViewKline={(symbol) => void handleSimulationFocusChange(symbol)}
                          onOpenReport={(symbol) => void openAnalysisReportModal(symbol)}
                          onOpenOrder={openManualOrderModal}
                        />
                      </Col>
                      <Col xs={24} xxl={12}>
                        <SimulationTrackCard
                          track={simulation.model_track}
                          watchSymbols={simulationConfigDraft?.watch_symbols ?? simulation.session.watch_symbols}
                          candidateRows={candidateRows}
                          symbolNameMap={symbolNameMap}
                          modelAdvices={simulation.model_advices}
                          activeSymbol={operationsFocusSymbol}
                          onViewKline={(symbol) => void handleSimulationFocusChange(symbol)}
                          onOpenReport={(symbol) => void openAnalysisReportModal(symbol)}
                        />
                      </Col>
                    </Row>
                  </>
                ) : null}

                {operations ? (
                  <Card className="panel-card" title="运营复盘分析">
                    <Tabs items={operationsTabItems} />
                  </Card>
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
        open={Boolean(completeResearchTarget)}
        centered
        width={isMobile ? "calc(100vw - 20px)" : 760}
        title={completeResearchTarget ? `人工完成研究请求 · ${completeResearchTarget.symbol}` : "人工完成研究请求"}
        okText="确认完成"
        cancelText="取消"
        confirmLoading={manualResearchAction === `complete:${completeResearchTarget?.id}`}
        onCancel={closeCompleteManualResearchModal}
        onOk={() => void handleConfirmCompleteManualResearch()}
      >
        {completeResearchTarget ? (
          <Form layout="vertical">
            <Alert
              className="sub-alert"
              type="info"
              showIcon
              message={sanitizeDisplayText(completeResearchTarget.question)}
              description={`当前状态 ${manualReviewStatusLabel(completeResearchTarget.status)}`}
            />
            <Form.Item label="研究摘要" required>
              <TextArea
                rows={4}
                value={completeResearchSummary}
                onChange={(event) => setCompleteResearchSummary(event.target.value)}
                placeholder="给出这次人工研究的结论摘要。"
              />
            </Form.Item>
            <Form.Item label="研究结论">
              <Select
                value={completeResearchVerdict}
                options={manualResearchVerdictOptions}
                onChange={(value) => setCompleteResearchVerdict(value)}
              />
            </Form.Item>
            <Form.Item label="风险点">
              <TextArea
                rows={3}
                value={completeResearchRisks}
                onChange={(event) => setCompleteResearchRisks(event.target.value)}
                placeholder="每行一个风险点"
              />
            </Form.Item>
            <Form.Item label="与量化层分歧">
              <TextArea
                rows={3}
                value={completeResearchDisagreements}
                onChange={(event) => setCompleteResearchDisagreements(event.target.value)}
                placeholder="每行一个分歧点"
              />
            </Form.Item>
            <Form.Item label="治理说明">
              <TextArea
                rows={3}
                value={completeResearchDecisionNote}
                onChange={(event) => setCompleteResearchDecisionNote(event.target.value)}
                placeholder="说明这份人工研究应该如何影响当前建议。"
              />
            </Form.Item>
            <Form.Item label="引用 / 证据">
              <TextArea
                rows={3}
                value={completeResearchCitations}
                onChange={(event) => setCompleteResearchCitations(event.target.value)}
                placeholder="每行一条引用或证据来源"
              />
            </Form.Item>
            <Form.Item label="完整回答">
              <TextArea
                rows={5}
                value={completeResearchAnswer}
                onChange={(event) => setCompleteResearchAnswer(event.target.value)}
                placeholder="可选：保留完整人工结论文本；留空则回落到摘要。"
              />
            </Form.Item>
          </Form>
        ) : null}
      </Modal>

      <Modal
        open={Boolean(failResearchTarget)}
        centered
        width={isMobile ? "calc(100vw - 20px)" : 640}
        title={failResearchTarget ? `标记研究请求失败 · ${failResearchTarget.symbol}` : "标记研究请求失败"}
        okText="确认失败"
        cancelText="取消"
        okButtonProps={{ danger: true }}
        confirmLoading={manualResearchAction === `fail:${failResearchTarget?.id}`}
        onCancel={closeFailManualResearchModal}
        onOk={() => void handleConfirmFailManualResearch()}
      >
        {failResearchTarget ? (
          <>
            <Alert
              className="sub-alert"
              type="warning"
              showIcon
              message={sanitizeDisplayText(failResearchTarget.question)}
              description={`当前状态 ${manualReviewStatusLabel(failResearchTarget.status)}`}
            />
            <Form layout="vertical">
              <Form.Item label="失败原因" required>
                <TextArea
                  rows={5}
                  value={failResearchReason}
                  onChange={(event) => setFailResearchReason(event.target.value)}
                  placeholder="记录为什么无法继续完成这次人工研究。"
                />
              </Form.Item>
            </Form>
          </>
        ) : null}
      </Modal>

      <Modal
        open={Boolean(orderModalSymbol && simulation)}
        centered
        width={isMobile ? "calc(100vw - 20px)" : 880}
        footer={null}
        title={orderModalSymbol ? `用户轨道操作 · ${symbolNameMap.get(orderModalSymbol) ?? orderModalSymbol}` : "用户轨道操作"}
        onCancel={() => setOrderModalSymbol(null)}
      >
        {simulation ? (
          <div className="manual-order-modal">
            <div className="manual-order-summary-grid">
              <div className="kline-summary-card">
                <span>当前持股</span>
                <strong>{formatNumber(manualOrderActiveHolding?.quantity ?? 0)}</strong>
              </div>
              <div className="kline-summary-card">
                <span>现价 / 成本</span>
                <strong>{`${formatNumber(manualOrderActiveHolding?.last_price)} / ${manualOrderActiveHolding && manualOrderActiveHolding.avg_cost > 0 ? formatNumber(manualOrderActiveHolding.avg_cost) : "--"}`}</strong>
              </div>
              <div className="kline-summary-card">
                <span>持仓盈亏</span>
                <strong className={`value-${valueTone(manualOrderActiveHolding?.total_pnl)}`}>{formatSignedNumber(manualOrderActiveHolding?.total_pnl)}</strong>
              </div>
              <div className="kline-summary-card">
                <span>模型参考</span>
                <strong>
                  {activeSimulationAdvice
                    ? activeSimulationAdvice.policy_type === "manual_review_preview_policy_v1"
                      ? `预览 ${simulationAdviceActionLabel(activeSimulationAdvice)}`
                      : simulationAdviceActionLabel(activeSimulationAdvice)
                    : "暂无"}
                </strong>
              </div>
            </div>
            <Form layout="vertical">
              <Row gutter={[16, 0]}>
                <Col xs={24} md={12}>
                  <Form.Item label="标的">
                    <Select
                      value={manualOrderDraft.symbol || undefined}
                      options={simulation.session.watch_symbols.map((symbol) => ({
                        value: symbol,
                        label: `${symbolNameMap.get(symbol) ?? symbol} · ${symbol}`,
                      }))}
                      onChange={(value) => setManualOrderDraft((current) => ({ ...current, symbol: value }))}
                    />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12}>
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
                </Col>
              </Row>
              <Row gutter={[16, 0]}>
                <Col xs={24} md={12}>
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
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item label="限价（可选）">
                    <InputNumber
                      className="full-width"
                      min={0}
                      step={0.01}
                      value={manualOrderDraft.limit_price ?? undefined}
                      onChange={(value) =>
                        setManualOrderDraft((current) => ({ ...current, limit_price: value === null ? null : Number(value) }))
                      }
                    />
                  </Form.Item>
                </Col>
              </Row>
              <Form.Item label="交易理由">
                <TextArea
                  rows={5}
                  value={manualOrderDraft.reason}
                  onChange={(event) => setManualOrderDraft((current) => ({ ...current, reason: event.target.value }))}
                  placeholder="记录你基于轨道表现、K线和证据做出该笔交易的理由"
                />
              </Form.Item>
            </Form>
            {activeSimulationAdvice ? (
              <Alert
                className="sub-alert"
                type="info"
                showIcon
                message={`模型轨道当前建议：${activeSimulationAdvice.direction_label}`}
                description={`${activeSimulationAdvice.reason} · 参考价 ${formatNumber(activeSimulationAdvice.reference_price)}。`}
              />
            ) : null}
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
          </div>
        ) : null}
      </Modal>

      <Modal
        open={Boolean(analysisReportSymbol)}
        centered
        footer={null}
        width={isMobile ? "calc(100vw - 20px)" : 760}
        title={analysisReportRow ? `运营复盘分析报告 · ${analysisReportRow.name}` : "运营复盘分析报告"}
        onCancel={closeAnalysisReportModal}
      >
        <CompactAnalysisReport
          row={analysisReportRow}
          dashboard={analysisReportDashboard}
          loading={analysisReportLoading}
          error={analysisReportError}
          onOpenFullAnalysis={() => {
            if (analysisReportSymbol) {
              openFullAnalysisFromReport(analysisReportSymbol);
            }
          }}
        />
      </Modal>

      <Modal
        open={Boolean(pendingRemoval)}
        centered
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
