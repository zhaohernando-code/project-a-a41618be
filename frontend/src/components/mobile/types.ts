import type { ReactNode } from "react";
import type {
  AuthContextResponse,
  CandidateWorkspaceRow,
  DataSourceInfo,
  ModelApiKeyView,
  OperationsDashboardResponse,
  RuntimeOverviewResponse,
  RuntimeSettingsResponse,
  SimulationWorkspaceResponse,
  StockDashboardResponse,
} from "../../types";

export type MobileTabKey = "home" | "stock" | "operations" | "settings";
export type MobileStockPanelKey = "advice" | "evidence" | "risk" | "question";

export interface MobileAppShellProps {
  themeMode: "light" | "dark";
  authContext: AuthContextResponse | null;
  isRootUser: boolean;
  canUseManualResearch: boolean;
  canUseOperations: boolean;
  canUseSettings: boolean;
  loadingShell: boolean;
  loadingDetail: boolean;
  operationsLoading: boolean;
  error: string | null;
  operationsError: string | null;
  candidateRows: CandidateWorkspaceRow[];
  activeRow: CandidateWorkspaceRow | null;
  selectedSymbol: string | null;
  dashboard: StockDashboardResponse | null;
  operations: OperationsDashboardResponse | null;
  simulation: SimulationWorkspaceResponse | null;
  sourceInfo: DataSourceInfo;
  runtimeSettings: RuntimeSettingsResponse | null;
  runtimeOverview: RuntimeOverviewResponse | null;
  modelApiKeys: ModelApiKeyView[];
  generatedAt: string | null;
  addWatchlistOverlay: ReactNode;
  addPopoverOpen: boolean;
  setAddPopoverOpen: (open: boolean) => void;
  mutatingWatchlist: boolean;
  watchlistMutationSymbol: string | null;
  questionDraft: string;
  setQuestionDraft: (value: string) => void;
  analysisKeyId: number | undefined;
  setAnalysisKeyId: (value: number | undefined) => void;
  analysisLoading: boolean;
  onToggleTheme: () => void;
  onSelectAnalysisModel: (keyId: number | undefined) => void | Promise<void>;
  onRefresh: () => void | Promise<void>;
  onRefreshWatchlist: (symbol: string) => void | Promise<void>;
  onSelectSymbol: (symbol: string, target?: MobileTabKey) => void;
  onRequestRemoveWatchlist?: (row: CandidateWorkspaceRow) => void;
  onOpenManualOrder?: (symbol: string, side: "buy" | "sell") => void;
  onTabChange: (tab: MobileTabKey) => void;
  onSubmitManualResearch: () => void | Promise<void>;
  onCopyPrompt: () => void | Promise<void>;
  onSwitchAccount?: (targetLogin: string) => void | Promise<void>;
  onLoadOperations: () => void | Promise<void>;
  stockPanel?: MobileStockPanelKey;
  setStockPanel?: (panel: MobileStockPanelKey) => void;
}
