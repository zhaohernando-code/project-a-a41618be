import snapshotData from "./offline-snapshot.json";
import type {
  OperationsDashboardResponse,
  PricePointView,
  SimulationWorkspaceResponse,
  SnapshotPayload,
  StockDashboardResponse,
} from "./types";

type LegacyPricePoint = Partial<PricePointView> & {
  observed_at: string;
  close_price: number;
  volume: number;
};

function normalizePriceChart(points: LegacyPricePoint[]): PricePointView[] {
  let previousClose: number | null = null;
  return points.map((point) => {
    const openPrice = point.open_price ?? previousClose ?? point.close_price;
    const highPrice = point.high_price ?? Math.max(openPrice, point.close_price);
    const lowPrice = point.low_price ?? Math.min(openPrice, point.close_price);
    previousClose = point.close_price;
    return {
      observed_at: point.observed_at,
      open_price: openPrice,
      high_price: highPrice,
      low_price: lowPrice,
      close_price: point.close_price,
      volume: point.volume,
    };
  });
}

function normalizeStockDashboard(dashboard: StockDashboardResponse): StockDashboardResponse {
  return {
    ...dashboard,
    price_chart: normalizePriceChart(dashboard.price_chart as LegacyPricePoint[]),
  };
}

function normalizeSimulationWorkspace(workspace: SimulationWorkspaceResponse): SimulationWorkspaceResponse {
  return {
    ...workspace,
    kline: {
      ...workspace.kline,
      points: normalizePriceChart(workspace.kline.points as LegacyPricePoint[]),
    },
  };
}

function normalizeOperationsDashboard(dashboard: OperationsDashboardResponse): OperationsDashboardResponse {
  return {
    ...dashboard,
    simulation_workspace: dashboard.simulation_workspace
      ? normalizeSimulationWorkspace(dashboard.simulation_workspace)
      : dashboard.simulation_workspace,
  };
}

function normalizeSnapshot(snapshot: SnapshotPayload): SnapshotPayload {
  return {
    ...snapshot,
    stock_dashboards: Object.fromEntries(
      Object.entries(snapshot.stock_dashboards).map(([symbol, dashboard]) => [symbol, normalizeStockDashboard(dashboard)]),
    ),
    operations_dashboards: Object.fromEntries(
      Object.entries(snapshot.operations_dashboards).map(([symbol, dashboard]) => [symbol, normalizeOperationsDashboard(dashboard)]),
    ),
  };
}

export const offlineSnapshot = normalizeSnapshot(snapshotData as unknown as SnapshotPayload);
