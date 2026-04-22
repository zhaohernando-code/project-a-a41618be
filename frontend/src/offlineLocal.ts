import { offlineSnapshot } from "./offlineSnapshot";
import type {
  CandidateItemView,
  DashboardBootstrapResponse,
  DashboardShellPayload,
  EvidenceArtifactView,
  GlossaryEntryView,
  OperationsDashboardResponse,
  PricePointView,
  RecommendationDirection,
  SimulationOrderView,
  StockDashboardResponse,
  WatchlistDeleteResponse,
  WatchlistItemView,
  WatchlistMutationResponse,
  WatchlistResponse,
} from "./types";

const storageKey = "ashare-dashboard-offline-watchlist-v1";
const latestTradeDate = new Date(Date.UTC(2026, 3, 14, 7, 0, 0));
const generatedAtOffsetMs = 65 * 60 * 1000;
const defaultSymbols = offlineSnapshot.bootstrap.symbols;

type StoredWatchlistItem = {
  symbol: string;
  name: string;
  source_kind: "default_seed" | "user_input";
  added_at: string;
  updated_at: string;
  last_analyzed_at: string;
};

type StoredWatchlistState = {
  items: StoredWatchlistItem[];
};

type SectorTemplate = {
  industry: string;
  primarySectorName: string;
  secondarySectorName: string;
  positiveTopic: string;
  negativeTopic: string;
  sectorPositiveTopic: string;
  sectorNegativeTopic: string;
};

type DirectionProfile = {
  direction: RecommendationDirection;
  confidenceLabel: string;
  confidenceExpression: string;
  applicablePeriod: string;
  changeBadge: string;
  evidenceStatus: string;
  priceBase: number;
  newsBase: number;
  llmBase: number;
  fusionBase: number;
  previousDirection: RecommendationDirection;
};

type GeneratedSeries = {
  points: PricePointView[];
  latestClose: number;
  latestVolume: number;
  latestTurnoverRate: number;
  latestHigh: number;
  latestLow: number;
  dayChangePct: number;
  priceReturn20d: number;
  priceScore: number;
  volumeZScore5d: number;
  upDayRatio10d: number;
};

type GeneratedPayload = {
  watchlistItem: WatchlistItemView;
  candidate: CandidateItemView;
  stockDashboard: StockDashboardResponse;
};

const sectorTemplates: SectorTemplate[] = [
  {
    industry: "高端消费",
    primarySectorName: "食品饮料",
    secondarySectorName: "品牌消费",
    positiveTopic: "渠道动销与现金回款继续改善",
    negativeTopic: "终端动销恢复节奏仍需验证",
    sectorPositiveTopic: "内需复苏预期回暖",
    sectorNegativeTopic: "税费与渠道库存讨论升温",
  },
  {
    industry: "新能源设备",
    primarySectorName: "电力设备",
    secondarySectorName: "储能",
    positiveTopic: "新签订单与排产节奏同步改善",
    negativeTopic: "价格竞争和去库存压力仍在",
    sectorPositiveTopic: "新能源链补库预期回升",
    sectorNegativeTopic: "产业链价格下修压力扩大",
  },
  {
    industry: "保险金融",
    primarySectorName: "非银金融",
    secondarySectorName: "高股息资产",
    positiveTopic: "负债成本改善与权益弹性同步修复",
    negativeTopic: "权益波动和新单恢复仍需观察",
    sectorPositiveTopic: "低利率环境下高股息偏好抬升",
    sectorNegativeTopic: "利差与权益波动压制估值修复",
  },
  {
    industry: "半导体",
    primarySectorName: "电子",
    secondarySectorName: "半导体",
    positiveTopic: "客户拉货和产能利用率继续回升",
    negativeTopic: "验证进度与价格压力仍有反复",
    sectorPositiveTopic: "国产替代与景气改善继续演绎",
    sectorNegativeTopic: "终端需求反复压制估值修复",
  },
  {
    industry: "创新药",
    primarySectorName: "医药生物",
    secondarySectorName: "创新药",
    positiveTopic: "核心产品放量与临床进展形成共振",
    negativeTopic: "研发节奏与医保谈判仍存不确定性",
    sectorPositiveTopic: "创新药情绪修复与海外授权预期升温",
    sectorNegativeTopic: "集采与研发兑现节奏引发分歧",
  },
];

const directionProfiles: DirectionProfile[] = [
  {
    direction: "buy",
    confidenceLabel: "中高",
    confidenceExpression: "中高置信，适合 2-8 周波段分批跟踪。",
    applicablePeriod: "2-8 周，当前以 4 周信号最强",
    changeBadge: "方向切换",
    evidenceStatus: "sufficient",
    priceBase: 0.54,
    newsBase: 0.68,
    llmBase: 0.6,
    fusionBase: 0.58,
    previousDirection: "risk_alert",
  },
  {
    direction: "buy",
    confidenceLabel: "中等",
    confidenceExpression: "中等置信，适合 2-8 周波段继续跟踪。",
    applicablePeriod: "2-8 周，当前先看 2-4 周兑现节奏",
    changeBadge: "边际转强",
    evidenceStatus: "sufficient",
    priceBase: 0.32,
    newsBase: 0.28,
    llmBase: 0.36,
    fusionBase: 0.29,
    previousDirection: "watch",
  },
  {
    direction: "watch",
    confidenceLabel: "中等",
    confidenceExpression: "中等置信，当前更适合观察而非追价。",
    applicablePeriod: "2-8 周，当前先等 2-4 周证据继续收敛",
    changeBadge: "信号分歧",
    evidenceStatus: "degraded",
    priceBase: 0.08,
    newsBase: -0.06,
    llmBase: 0.05,
    fusionBase: 0.03,
    previousDirection: "buy",
  },
  {
    direction: "reduce",
    confidenceLabel: "中高",
    confidenceExpression: "中高置信，当前更适合先做风险控制。",
    applicablePeriod: "2-8 周，当前以 2-4 周风险监控优先",
    changeBadge: "方向转弱",
    evidenceStatus: "degraded",
    priceBase: -0.42,
    newsBase: -0.34,
    llmBase: -0.18,
    fusionBase: -0.31,
    previousDirection: "watch",
  },
];

const glossaryByTerm = new Map(offlineSnapshot.glossary.map((item) => [item.term, item]));

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function hashString(value: string): number {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function hashHex(value: string): string {
  const base = hashString(value).toString(16).padStart(8, "0");
  return base.repeat(8).slice(0, 64);
}

function createRng(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    return state / 0xffffffff;
  };
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function round(value: number, digits = 2): number {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

function formatNoZone(date: Date): string {
  const year = date.getUTCFullYear();
  const month = String(date.getUTCMonth() + 1).padStart(2, "0");
  const day = String(date.getUTCDate()).padStart(2, "0");
  const hour = String(date.getUTCHours()).padStart(2, "0");
  const minute = String(date.getUTCMinutes()).padStart(2, "0");
  const second = String(date.getUTCSeconds()).padStart(2, "0");
  return `${year}-${month}-${day}T${hour}:${minute}:${second}`;
}

function parseNoZone(value: string): Date {
  return new Date(`${value}Z`);
}

function addMinutes(value: string, minutes: number): string {
  const date = parseNoZone(value);
  date.setUTCMinutes(date.getUTCMinutes() + minutes);
  return formatNoZone(date);
}

function subtractDays(date: Date, days: number): Date {
  const next = new Date(date.getTime());
  next.setUTCDate(next.getUTCDate() - days);
  return next;
}

function businessDays(count: number): Date[] {
  const dates: Date[] = [];
  let cursor = new Date(latestTradeDate.getTime());
  cursor.setUTCHours(7, 0, 0, 0);
  while (dates.length < count) {
    const weekday = cursor.getUTCDay();
    if (weekday !== 0 && weekday !== 6) {
      dates.push(new Date(cursor.getTime()));
    }
    cursor = subtractDays(cursor, 1);
  }
  return dates.reverse();
}

function nowNoZone(): string {
  return formatNoZone(new Date());
}

function inferMarketSuffix(ticker: string): "SH" | "SZ" | "BJ" {
  if (["5", "6", "9"].includes(ticker[0])) return "SH";
  if (["0", "2", "3"].includes(ticker[0])) return "SZ";
  if (["4", "8"].includes(ticker[0])) return "BJ";
  throw new Error("暂不支持该证券代码。请输入 6 位 A 股代码。");
}

function normalizeSymbol(symbol: string): string {
  const rawInput = symbol.trim().toUpperCase().replace(/\s+/g, "");
  if (!rawInput) {
    throw new Error("请输入股票代码。");
  }
  let raw = rawInput;
  if (/^(SH|SZ|BJ)\d{6}$/.test(raw)) {
    raw = `${raw.slice(2)}.${raw.slice(0, 2)}`;
  }
  if (!raw.includes(".")) {
    if (!/^\d{6}$/.test(raw)) {
      throw new Error("股票代码格式无效，请输入如 600519 或 300750.SZ。");
    }
    return `${raw}.${inferMarketSuffix(raw)}`;
  }
  const [ticker, suffix] = raw.split(".", 2);
  if (!/^\d{6}$/.test(ticker)) {
    throw new Error("股票代码格式无效，请输入 6 位数字代码。");
  }
  if (!["SH", "SZ", "BJ"].includes(suffix)) {
    throw new Error("股票代码后缀仅支持 .SH / .SZ / .BJ。");
  }
  return `${ticker}.${suffix}`;
}

function exchangeName(symbol: string): string {
  const suffix = symbol.split(".", 2)[1];
  if (suffix === "SH") return "SSE";
  if (suffix === "SZ") return "SZSE";
  return "BSE";
}

function localStorageAvailable(): boolean {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

function defaultState(): StoredWatchlistState {
  return {
    items: offlineSnapshot.watchlist.items.map((item) => ({
      symbol: item.symbol,
      name: item.name,
      source_kind: item.source_kind === "user_input" ? "user_input" : "default_seed",
      added_at: item.added_at,
      updated_at: item.updated_at,
      last_analyzed_at: item.last_analyzed_at ?? item.updated_at,
    })),
  };
}

function loadState(): StoredWatchlistState {
  if (!localStorageAvailable()) {
    return defaultState();
  }
  const raw = window.localStorage.getItem(storageKey);
  if (!raw) {
    return defaultState();
  }
  try {
    const parsed = JSON.parse(raw) as StoredWatchlistState;
    if (!Array.isArray(parsed.items)) {
      return defaultState();
    }
    return {
      items: parsed.items
        .filter((item) => item && typeof item.symbol === "string" && typeof item.name === "string")
        .map((item) => ({
          symbol: normalizeSymbol(item.symbol),
          name: item.name.trim() || `自选标的 ${item.symbol.slice(0, 6)}`,
          source_kind: item.source_kind === "user_input" ? "user_input" : "default_seed",
          added_at: item.added_at || nowNoZone(),
          updated_at: item.updated_at || item.added_at || nowNoZone(),
          last_analyzed_at: item.last_analyzed_at || item.updated_at || item.added_at || nowNoZone(),
        })),
    };
  } catch {
    return defaultState();
  }
}

function saveState(state: StoredWatchlistState): void {
  if (!localStorageAvailable()) {
    return;
  }
  window.localStorage.setItem(storageKey, JSON.stringify(state));
}

function resetState(): StoredWatchlistState {
  const state = defaultState();
  saveState(state);
  return state;
}

function directionLabel(direction: RecommendationDirection): string {
  if (direction === "buy") return "偏积极";
  if (direction === "watch") return "继续观察";
  if (direction === "reduce") return "偏谨慎";
  return "风险提示";
}

function deepReplaceTokens<T>(value: T, replacements: Array<[string, string]>): T {
  if (typeof value === "string") {
    let stringValue: string = value;
    replacements.forEach(([from, to]) => {
      stringValue = stringValue.split(from).join(to);
    });
    return stringValue as T;
  }
  if (Array.isArray(value)) {
    return value.map((item) => deepReplaceTokens(item, replacements)) as T;
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([key, entry]) => [key, deepReplaceTokens(entry, replacements)]),
    ) as T;
  }
  return value;
}

function buildLineage(sourceUri: string, token: string, licenseTag = "internal-derived") {
  return {
    license_tag: licenseTag,
    usage_scope: "internal_research",
    redistribution_scope: "none",
    source_uri: sourceUri,
    lineage_hash: hashHex(token),
  };
}

function startClose(ticker: string, seed: number): number {
  if (ticker.startsWith("688")) return round(42 + (seed % 1400) / 10, 2);
  if (ticker.startsWith("300")) return round(26 + (seed % 900) / 10, 2);
  if (/^(600|601|603|605)/.test(ticker)) return round(10 + (seed % 700) / 10, 2);
  if (/^(000|001|002)/.test(ticker)) return round(8 + (seed % 620) / 10, 2);
  return round(12 + (seed % 680) / 10, 2);
}

function generateSeries(symbol: string): GeneratedSeries {
  const seed = hashString(symbol);
  const tier = Math.floor(seed / sectorTemplates.length) % directionProfiles.length;
  const rng = createRng(seed || 1);
  const ticker = symbol.slice(0, 6);
  const phase = 0.25 + rng() * 2.6;
  const baseDrift = [0.0032, 0.0011, 0.0002, -0.0027][tier];
  const lateBias = [0.002, 0.0004, -0.0007, -0.002][tier];
  const volatility = [0.0018, 0.0022, 0.0025, 0.0033][tier];
  const days = businessDays(28);
  let previousClose = startClose(ticker, seed);
  const pricePoints: PricePointView[] = [];
  const returns: number[] = [];
  const volumes: number[] = [];
  let latestHigh = previousClose;
  let latestLow = previousClose;
  let latestTurnoverRate = 0.05;

  days.forEach((tradeDay, index) => {
    const cycle = Math.sin(index / 3.15 + phase) * volatility * 0.55;
    const noise = (rng() * 2 - 1) * volatility;
    let dailyReturn = baseDrift + cycle + noise + (index >= 23 ? lateBias : 0);
    if (tier === 1 && [6, 13, 20].includes(index)) dailyReturn -= 0.002;
    if (tier === 2 && index >= 20) dailyReturn -= 0.0008;
    if (tier === 3 && [9, 17, 25].includes(index)) dailyReturn -= 0.0038;
    dailyReturn = clamp(dailyReturn, -0.085, 0.085);
    const closePrice = round(previousClose * (1 + dailyReturn), 2);
    const spread = 0.006 + (index % 4) * 0.001;
    latestHigh = round(Math.max(previousClose, closePrice) * (1 + spread), 2);
    latestLow = round(Math.min(previousClose, closePrice) * (1 - spread * 0.82), 2);
    const volume = round(9800 + (seed % 22000) + index * (110 + (seed % 260)) + ((index % 5) - 2) * (280 + (seed % 900)), 2);
    latestTurnoverRate = round(0.038 + (seed % 80) / 1000 + index * (0.0007 + (seed % 25) / 10000), 4);
    pricePoints.push({
      observed_at: formatNoZone(tradeDay),
      open_price: previousClose,
      high_price: latestHigh,
      low_price: latestLow,
      close_price: closePrice,
      volume,
    });
    returns.push(dailyReturn);
    volumes.push(volume);
    previousClose = closePrice;
  });

  const latestClose = pricePoints[pricePoints.length - 1]?.close_price ?? previousClose;
  const latestVolume = pricePoints[pricePoints.length - 1]?.volume ?? volumes[volumes.length - 1] ?? 0;
  const price20dBase = pricePoints[Math.max(0, pricePoints.length - 21)]?.close_price ?? latestClose;
  const priceReturn20d = round(latestClose / price20dBase - 1, 4);
  const recentVolumes = volumes.slice(-5);
  const avgVolume20d = volumes.slice(-20).reduce((total, value) => total + value, 0) / Math.max(1, volumes.slice(-20).length);
  const volumeStd20d = Math.sqrt(
    volumes
      .slice(-20)
      .reduce((total, value) => total + (value - avgVolume20d) ** 2, 0) / Math.max(1, volumes.slice(-20).length),
  );
  const volumeZScore5d = volumeStd20d > 0
    ? round((recentVolumes.reduce((total, value) => total + value, 0) / recentVolumes.length - avgVolume20d) / volumeStd20d, 3)
    : 0;
  const upDayRatio10d = round(returns.slice(-10).filter((value) => value > 0).length / 10, 2);
  const priceScore = clamp(round(priceReturn20d * 4.2 + upDayRatio10d * 0.35 + volumeZScore5d * 0.06, 4), -1, 1);

  return {
    points: pricePoints,
    latestClose,
    latestVolume,
    latestTurnoverRate,
    latestHigh,
    latestLow,
    dayChangePct: round(returns[returns.length - 1] ?? 0, 4),
    priceReturn20d,
    priceScore,
    volumeZScore5d,
    upDayRatio10d,
  };
}

function buildRecentNews(
  symbol: string,
  stockName: string,
  template: SectorTemplate,
  profile: DirectionProfile,
  asOfDataTime: string,
) {
  const ticker = symbol.slice(0, 6);
  const positiveBias = profile.direction === "buy";
  const mixedBias = profile.direction === "watch";
  const newestTopic = positiveBias ? template.positiveTopic : template.negativeTopic;
  const sectorTopic = positiveBias ? template.sectorPositiveTopic : template.sectorNegativeTopic;
  const negativeTopic = mixedBias ? template.negativeTopic : template.sectorNegativeTopic;
  const timestamps = [
    addMinutes(asOfDataTime, -60 * 24 * 3),
    addMinutes(asOfDataTime, -60 * 24 * 2),
    addMinutes(asOfDataTime, -60 * 18),
    addMinutes(asOfDataTime, -70),
  ];

  return [
    {
      headline: `${template.primarySectorName}板块跟踪：${sectorTopic}`,
      summary: `行业层面最新跟踪显示，${sectorTopic}。`,
      published_at: timestamps[0],
      impact_direction: positiveBias ? "positive" : mixedBias ? "negative" : "negative",
      entity_scope: "行业层",
      relevance_score: mixedBias ? 0.56 : 0.64,
      source_uri: `cninfo://news/${ticker}/sector-${timestamps[0].slice(0, 10).replace(/-/g, "")}`,
      license_tag: "cninfo-public-disclosure",
    },
    {
      headline: `${stockName}披露经营更新，${newestTopic}`,
      summary: `公司层面最新经营信息显示，${newestTopic}。`,
      published_at: timestamps[1],
      impact_direction: positiveBias ? "positive" : mixedBias ? "neutral" : "negative",
      entity_scope: "个股层",
      relevance_score: 0.81,
      source_uri: `cninfo://announcements/${ticker}/ops-${timestamps[1].slice(0, 10).replace(/-/g, "")}`,
      license_tag: "cninfo-public-disclosure",
    },
    {
      headline: `机构调研聚焦${stockName}，${mixedBias ? template.positiveTopic : newestTopic}`,
      summary: `最新调研纪要显示，市场关注点集中在 ${mixedBias ? template.positiveTopic : newestTopic}。`,
      published_at: timestamps[2],
      impact_direction: mixedBias ? "positive" : positiveBias ? "positive" : "negative",
      entity_scope: "个股层",
      relevance_score: 0.88,
      source_uri: `cninfo://announcements/${ticker}/roadshow-${timestamps[2].slice(0, 10).replace(/-/g, "")}`,
      license_tag: "cninfo-public-disclosure",
    },
    {
      headline: `${stockName}短线风险跟踪：${negativeTopic}`,
      summary: `系统继续把 ${negativeTopic} 列为近期需要观察的反向证据。`,
      published_at: timestamps[3],
      impact_direction: "negative",
      entity_scope: mixedBias ? "行业层" : "个股层",
      relevance_score: 0.62,
      source_uri: `pipeline://news-monitor/${ticker}/risk-${timestamps[3].slice(0, 10).replace(/-/g, "")}`,
      license_tag: "internal-derived",
    },
  ];
}

function pickGlossary(): GlossaryEntryView[] {
  const terms = ["滚动时间验证", "证据降级", "融合评分", "LLM 因子"];
  return terms
    .map((term) => glossaryByTerm.get(term))
    .filter((item): item is GlossaryEntryView => Boolean(item));
}

function buildSimulationOrders(
  symbol: string,
  generatedAt: string,
  latestClose: number,
  direction: RecommendationDirection,
): SimulationOrderView[] {
  const ticker = symbol.slice(0, 6);
  const quantity = latestClose >= 100 ? 100 : 200;
  const side = direction === "reduce" || direction === "risk_alert" ? "sell" : "buy";
  const pendingOnly = direction === "watch";
  const firstPrice = round(latestClose * (side === "buy" ? 1.001 : 0.998), 2);
  const secondPrice = round(latestClose * (side === "buy" ? 1.002 : 0.997), 2);
  const sourceToken = generatedAt.slice(0, 10).replace(/-/g, "");

  const orders: SimulationOrderView[] = [
    {
      id: hashString(`${symbol}-manual`) % 100000,
      order_source: "manual",
      side,
      status: pendingOnly ? "pending" : "filled",
      requested_at: generatedAt,
      quantity,
      limit_price: pendingOnly ? firstPrice : firstPrice,
      fills: pendingOnly
        ? []
        : [
            {
              filled_at: generatedAt,
              price: firstPrice,
              quantity,
              fee: round(firstPrice * quantity * 0.0005, 2),
              tax: side === "sell" ? round(firstPrice * quantity * 0.001, 2) : 0,
              slippage_bps: 3.5,
              lineage: buildLineage(`simulation://fill/manual/${ticker}/${sourceToken}`, `${symbol}-manual-fill`),
            },
          ],
      lineage: buildLineage(`simulation://order/manual/${ticker}/${sourceToken}`, `${symbol}-manual-order`),
    },
    {
      id: hashString(`${symbol}-model`) % 100000 + 1,
      order_source: "model",
      side,
      status: pendingOnly ? "pending" : "filled",
      requested_at: generatedAt,
      quantity: quantity * 2,
      limit_price: pendingOnly ? null : null,
      fills: pendingOnly
        ? []
        : [
            {
              filled_at: generatedAt,
              price: secondPrice,
              quantity: quantity * 2,
              fee: round(secondPrice * quantity * 2 * 0.0005, 2),
              tax: side === "sell" ? round(secondPrice * quantity * 2 * 0.001, 2) : 0,
              slippage_bps: 4.3,
              lineage: buildLineage(`simulation://fill/auto/${ticker}/${sourceToken}`, `${symbol}-auto-fill`),
            },
          ],
      lineage: buildLineage(`simulation://order/auto/${ticker}/${sourceToken}`, `${symbol}-auto-order`),
    },
  ];
  return orders;
}

function buildGeneratedPayload(seedItem: StoredWatchlistItem): GeneratedPayload {
  const symbol = seedItem.symbol;
  const ticker = symbol.slice(0, 6);
  const name = seedItem.name.trim() || `自选标的 ${ticker}`;
  const seed = hashString(symbol);
  const template = sectorTemplates[seed % sectorTemplates.length];
  const profile = directionProfiles[Math.floor(seed / sectorTemplates.length) % directionProfiles.length];
  const series = generateSeries(symbol);
  const generatedAt = seedItem.last_analyzed_at;
  const asOfDataTime = formatNoZone(new Date(latestTradeDate.getTime()));
  const confidenceScore = clamp(
    round(0.53 + Math.abs(profile.fusionBase + series.priceReturn20d * 0.6) * 0.33 + (profile.direction === "buy" ? 0.05 : 0), 4),
    0.46,
    0.84,
  );
  const priceScore = clamp(round(profile.priceBase + series.priceScore * 0.35, 4), -1, 1);
  const newsScore = clamp(round(profile.newsBase + ((seed % 17) - 8) / 100, 4), -1, 1);
  const llmScore = clamp(round(profile.llmBase + ((seed % 11) - 5) / 100, 4), -1, 1);
  const fusionScore = clamp(round(priceScore * 0.58 + newsScore * 0.27 + llmScore * 0.15, 4), -1, 1);
  const positiveTopic = profile.direction === "buy" ? template.positiveTopic : template.sectorPositiveTopic;
  const negativeTopic = profile.direction === "reduce" ? template.negativeTopic : template.sectorNegativeTopic;
  const recommendationSummary = fusionScore >= 0.1
    ? `${name} 当前价格基线、新闻事件和 LLM 评估同向偏正，融合分数 ${fusionScore.toFixed(2)}，适用 2-8 周波段。`
    : fusionScore <= -0.1
      ? `${name} 当前证据仍偏弱，融合分数 ${fusionScore.toFixed(2)}，先以观察或风险控制为主。`
      : `${name} 当前证据仍有分歧，融合分数 ${fusionScore.toFixed(2)}，先以观察为主。`;
  const coreDrivers = [
    `20 日收益为 ${(series.priceReturn20d * 100).toFixed(1)}%，价格基线${priceScore >= 0 ? "继续偏多" : "仍偏弱"}。`,
    `近 5 日量能相对 20 日均值变化 ${series.volumeZScore5d.toFixed(2)}σ，成交活跃度${series.volumeZScore5d >= 0 ? "回升" : "回落"}。`,
    `${name} 当前主要围绕“${positiveTopic}”这一条主线被市场定价。`,
  ];
  const reverseRisks = [
    `${negativeTopic} 仍是当前最需要继续跟踪的反向证据。`,
    "LLM 因子仍仅作解释层辅助，权重上限固定为 15%。",
    "若 10 日动量重新跌回 0 以下，价格基线会先行降级。",
  ];
  const recentNews = buildRecentNews(symbol, name, template, profile, asOfDataTime);
  const whyNow = profile.direction === "buy"
    ? `${template.primarySectorName} 与个股证据同步改善，当前更适合按 2-8 周波段跟踪。`
    : profile.direction === "watch"
      ? `价格与事件证据尚未完全同向，先观察“${template.positiveTopic}”是否持续兑现。`
      : `最新价格与事件证据转弱，当前更适合把风险监控放在前面。`;
  const primaryRisk = reverseRisks[0];
  const changeSummary = profile.direction === "buy"
    ? `建议方向从“${directionLabel(profile.previousDirection)}”调整为“偏积极”。`
    : profile.direction === "watch"
      ? `建议已从“${directionLabel(profile.previousDirection)}”回到继续观察。`
      : `建议方向从“${directionLabel(profile.previousDirection)}”调整为“偏谨慎”。`;
  const recommendationIdBase = hashString(`${symbol}-recommendation`) % 900000;
  const evidence: EvidenceArtifactView[] = [
    {
      evidence_type: "model_result",
      record_id: recommendationIdBase + 1,
      role: "primary_driver",
      rank: 1,
      label: "28 日融合预测",
      snippet: fusionScore >= 0 ? "价格基线、新闻事件与 LLM 评估融合后仍偏正向。" : "价格基线与事件证据出现分歧，融合后建议先降一级解读。",
      timestamp: asOfDataTime,
      lineage: buildLineage(`pipeline://signal-engine/model-result/${symbol}/${asOfDataTime.slice(0, 10).replace(/-/g, "")}/28d`, `${symbol}-model-result`),
      payload: {
        predicted_direction: profile.direction,
        expected_return: round(fusionScore * 0.09, 4),
        confidence_score: confidenceScore,
        driver_factors: coreDrivers,
        risk_factors: reverseRisks,
      },
    },
    {
      evidence_type: "feature_snapshot",
      record_id: recommendationIdBase + 2,
      role: "primary_driver",
      rank: 2,
      label: "价格基线因子",
      snippet: "近 5/10/20 日动量、量能和换手率共同构成当前波段判断。",
      timestamp: asOfDataTime,
      lineage: buildLineage(`pipeline://signal-engine/price-baseline/${symbol}/${asOfDataTime.slice(0, 10).replace(/-/g, "")}`, `${symbol}-price-factor`),
      payload: {
        feature_set_name: "price_baseline_factor",
        feature_values: {
          ret_20d: series.priceReturn20d,
          volume_zscore_5d: series.volumeZScore5d,
          up_day_ratio_10d: series.upDayRatio10d,
          price_baseline_score: priceScore,
        },
      },
    },
    {
      evidence_type: "feature_snapshot",
      record_id: recommendationIdBase + 3,
      role: "primary_driver",
      rank: 3,
      label: "新闻事件因子",
      snippet: "最近公告和调研信息被折算为行业层与个股层的事件证据。",
      timestamp: asOfDataTime,
      lineage: buildLineage(`pipeline://signal-engine/news-event/${symbol}/${asOfDataTime.slice(0, 10).replace(/-/g, "")}`, `${symbol}-news-factor`),
      payload: {
        feature_set_name: "news_event_factor",
        feature_values: {
          news_event_score: newsScore,
          deduped_event_count: recentNews.length,
          event_keys: recentNews.map((item, index) => `${symbol}-event-${index + 1}`),
        },
      },
    },
    {
      evidence_type: "feature_snapshot",
      record_id: recommendationIdBase + 4,
      role: "supporting_context",
      rank: 4,
      label: "LLM 评估因子",
      snippet: "LLM 因子只做证据整合与解释，不主导最终方向。",
      timestamp: asOfDataTime,
      lineage: buildLineage(`pipeline://signal-engine/llm-assessment/${symbol}/${asOfDataTime.slice(0, 10).replace(/-/g, "")}`, `${symbol}-llm-factor`),
      payload: {
        feature_set_name: "llm_assessment_factor",
        feature_values: {
          llm_assessment_score: llmScore,
          evidence_coverage: 0.92,
          max_weight_cap: 0.15,
          status: fusionScore >= -0.2 ? "enabled" : "explain_only",
        },
      },
    },
  ];
  const followUpEvidencePacket = evidence.map((item) => `${item.label} | ${item.lineage.source_uri}`);
  const simulationOrders = buildSimulationOrders(symbol, generatedAt, series.latestClose, profile.direction);
  const watchlistItem: WatchlistItemView = {
    symbol,
    name,
    exchange: exchangeName(symbol),
    ticker,
    status: "active",
    source_kind: seedItem.source_kind,
    analysis_status: "ready",
    added_at: seedItem.added_at,
    updated_at: seedItem.updated_at,
    last_analyzed_at: seedItem.last_analyzed_at,
    last_error: null,
    latest_direction: profile.direction,
    latest_confidence_label: profile.confidenceLabel,
    latest_generated_at: generatedAt,
  };
  const candidate: CandidateItemView = {
    rank: 0,
    symbol,
    name,
    sector: template.primarySectorName,
    direction: profile.direction,
    direction_label: directionLabel(profile.direction),
    confidence_label: profile.confidenceLabel,
    confidence_score: confidenceScore,
    summary: recommendationSummary,
    applicable_period: profile.applicablePeriod,
    generated_at: generatedAt,
    as_of_data_time: asOfDataTime,
    last_close: series.latestClose,
    price_return_20d: series.priceReturn20d,
    why_now: whyNow,
    primary_risk: primaryRisk,
    change_summary: changeSummary,
    change_badge: profile.changeBadge,
    evidence_status: profile.evidenceStatus,
  };
  const baseModel = clone(offlineSnapshot.stock_dashboards[defaultSymbols[0]].model);
  const basePrompt = clone(offlineSnapshot.stock_dashboards[defaultSymbols[0]].prompt);
  const stockDashboard: StockDashboardResponse = {
    stock: {
      symbol,
      name,
      exchange: exchangeName(symbol),
      ticker,
    },
    recommendation: {
      id: recommendationIdBase,
      recommendation_key: `reco-${symbol}-${generatedAt.slice(0, 10).replace(/-/g, "")}-local`,
      direction: profile.direction,
      confidence_label: profile.confidenceLabel,
      confidence_score: confidenceScore,
      confidence_expression: profile.confidenceExpression,
      horizon_min_days: 14,
      horizon_max_days: 56,
      applicable_period: profile.applicablePeriod,
      summary: recommendationSummary,
      generated_at: generatedAt,
      updated_at: generatedAt,
      as_of_data_time: asOfDataTime,
      evidence_status: profile.evidenceStatus,
      degrade_reason: profile.evidenceStatus === "sufficient" ? null : "价格与事件证据仍有分歧，先降级为观察或风险控制。",
      core_drivers: coreDrivers,
      risk_flags: reverseRisks,
      reverse_risks: reverseRisks,
      downgrade_conditions: [
        "近 10 日动量跌回 0 以下且价格基线分数转负时降级。",
        "7 日内新增负向公告或监管事件并使新闻因子转负时降级。",
        "价格与新闻方向冲突且冲突度超过 45% 时降级为风险提示。",
        "最新行情距离建议生成超过 36 小时未刷新时降级。",
        "LLM 因子历史稳定性跌破阈值后自动退回解释层。",
      ],
      factor_breakdown: {
        price_baseline: {
          score: priceScore,
          weight: 0.58,
          direction: priceScore >= 0 ? "positive" : "negative",
          confidence_score: clamp(0.5 + Math.abs(priceScore) * 0.25, 0, 1),
          drivers: coreDrivers.slice(0, 2),
          risks: [reverseRisks[2]],
          evidence_count: series.points.length,
        },
        news_event: {
          score: newsScore,
          weight: 0.27,
          direction: newsScore >= 0 ? "positive" : "negative",
          confidence_score: clamp(0.46 + Math.abs(newsScore) * 0.22, 0, 1),
          drivers: recentNews.slice(0, 2).map((item) => `${item.headline} 提供${item.impact_direction === "negative" ? "反向" : "正向"}事件证据。`),
          risks: [reverseRisks[0]],
          evidence_count: recentNews.length,
          conflict_ratio: profile.direction === "watch" ? 0.38 : 0.14,
        },
        llm_assessment: {
          score: llmScore,
          weight: 0.15,
          direction: llmScore >= 0 ? "positive" : "negative",
          confidence_score: clamp(0.48 + Math.abs(llmScore) * 0.18, 0, 1),
          drivers: [
            "价格与事件证据已被统一收敛为结构化判断。",
            "LLM 评估只做证据整合，不单独给出交易结论。",
          ],
          risks: [reverseRisks[1]],
          status: fusionScore >= -0.2 ? "enabled" : "explain_only",
          calibration: {
            evaluation_window: "2024-01-01/2026-03-31",
            sample_count: 186,
            direction_hit_rate_lift_vs_baseline: 0.014,
            cost_adjusted_return_lift_vs_baseline: 0.019,
            stability_score: 0.62,
            brier_like_score: 0.184,
            max_weight_cap: 0.15,
            enabled_thresholds: {
              min_lift: 0.01,
              min_stability_score: 0.6,
            },
          },
        },
        fusion: {
          score: fusionScore,
          direction: profile.direction,
          confidence_score: confidenceScore,
          conflict_penalty: profile.direction === "watch" ? 0.08 : 0.02,
          stale_penalty: 0,
          evidence_gap_penalty: profile.evidenceStatus === "sufficient" ? 0 : 0.03,
          active_degrade_flags: profile.evidenceStatus === "sufficient" ? [] : ["evidence_conflict"],
        },
      },
      validation_snapshot: {
        validation_scheme: "rolling_time_window",
        transaction_cost_bps: 35,
        primary_horizon_days: 28,
        horizon_metrics: {
          14: {
            direction_hit_rate: round(clamp(0.54 + fusionScore * 0.06, 0.42, 0.67), 3),
            strategy_return: round(fusionScore * 0.18, 3),
            cost_adjusted_return: round(fusionScore * 0.15, 3),
            max_drawdown: round(-0.08 - Math.max(0, -fusionScore) * 0.12, 3),
            stability_score: round(clamp(0.6 + Math.abs(fusionScore) * 0.08, 0.54, 0.7), 3),
            evaluated_windows: 18,
            stage_distribution: { uptrend: 7, sideways: 6, downtrend: 5 },
            transaction_cost_bps: 35,
          },
          28: {
            direction_hit_rate: round(clamp(0.55 + fusionScore * 0.07, 0.43, 0.69), 3),
            strategy_return: round(fusionScore * 0.24, 3),
            cost_adjusted_return: round(fusionScore * 0.2, 3),
            max_drawdown: round(-0.11 - Math.max(0, -fusionScore) * 0.15, 3),
            stability_score: round(clamp(0.61 + Math.abs(fusionScore) * 0.09, 0.55, 0.72), 3),
            evaluated_windows: 16,
            stage_distribution: { uptrend: 6, sideways: 5, downtrend: 5 },
            transaction_cost_bps: 35,
          },
          56: {
            direction_hit_rate: round(clamp(0.53 + fusionScore * 0.05, 0.41, 0.66), 3),
            strategy_return: round(fusionScore * 0.29, 3),
            cost_adjusted_return: round(fusionScore * 0.22, 3),
            max_drawdown: round(-0.15 - Math.max(0, -fusionScore) * 0.18, 3),
            stability_score: round(clamp(0.58 + Math.abs(fusionScore) * 0.07, 0.52, 0.69), 3),
            evaluated_windows: 12,
            stage_distribution: { uptrend: 4, sideways: 4, downtrend: 4 },
            transaction_cost_bps: 35,
          },
        },
        llm_factor_evaluation: {
          evaluation_window: "2024-01-01/2026-03-31",
          sample_count: 186,
          direction_hit_rate_lift_vs_baseline: 0.014,
          cost_adjusted_return_lift_vs_baseline: 0.019,
          stability_score: 0.62,
          brier_like_score: 0.184,
          max_weight_cap: 0.15,
          enabled_thresholds: {
            min_lift: 0.01,
            min_stability_score: 0.6,
          },
        },
      },
      lineage: buildLineage(`pipeline://signal-engine/recommendation/${symbol}/${generatedAt.slice(0, 10).replace(/-/g, "")}`, `${symbol}-recommendation`),
    },
    model: baseModel,
    prompt: basePrompt,
    evidence,
    simulation_orders: simulationOrders,
    hero: {
      latest_close: series.latestClose,
      day_change_pct: series.dayChangePct,
      latest_volume: series.latestVolume,
      turnover_rate: series.latestTurnoverRate,
      high_price: series.latestHigh,
      low_price: series.latestLow,
      sector_tags: [template.primarySectorName, template.secondarySectorName],
      direction_label: directionLabel(profile.direction),
      last_updated: generatedAt,
    },
    price_chart: series.points,
    recent_news: recentNews,
    change: {
      has_previous: true,
      change_badge: profile.changeBadge,
      summary: changeSummary,
      reasons: [
        changeSummary,
        `整体置信度当前为 ${(confidenceScore * 100).toFixed(0)}%，需要继续跟踪事件兑现节奏。`,
        `价格基线分数当前为 ${priceScore.toFixed(2)}。`,
        `新闻事件分数当前为 ${newsScore.toFixed(2)}。`,
      ],
      previous_direction: profile.previousDirection,
      previous_confidence_label: profile.direction === "buy" ? "中等" : "中高",
      previous_generated_at: addMinutes(generatedAt, -7 * 24 * 60),
    },
    glossary: pickGlossary(),
    risk_panel: {
      headline: "当前建议只在证据继续收敛时成立",
      items: [...reverseRisks, `最近负向事件：${recentNews.find((item) => item.impact_direction === "negative")?.headline ?? negativeTopic}`],
      disclaimer: basePrompt.risk_disclaimer,
      change_hint: changeSummary,
    },
    follow_up: {
      suggested_questions: [
        "如果我只关注未来两周，哪些证据最值得盯？",
        "这条建议最可能因为什么条件而失效？",
        "最近一版建议为什么比上一版更强或更弱？",
        "如果只允许保守跟踪，应该先看哪些风险信号？",
      ],
      copy_prompt: [
        "请基于以下结构化证据回答我的追问，不要补充未给出的事实。",
        `股票：${name}（${symbol}）`,
        `当前建议：${directionLabel(profile.direction)}；${profile.confidenceExpression}`,
        `适用周期：${profile.applicablePeriod}`,
        "核心驱动：",
        ...coreDrivers.map((item) => `- ${item}`),
        "主要风险：",
        ...reverseRisks.map((item) => `- ${item}`),
        `最近变化：${changeSummary}`,
        "关键证据：",
        ...followUpEvidencePacket.map((item) => `- ${item}`),
        "请回答这个问题：<在这里替换成你的追问>",
        "回答要求：区分事实与推断，明确失效条件，并指出还需要继续观察的更新时间点。",
      ].join("\n"),
      evidence_packet: followUpEvidencePacket,
    },
  };

  return {
    watchlistItem,
    candidate,
    stockDashboard,
  };
}

function patchStaticPayload(seedItem: StoredWatchlistItem): GeneratedPayload {
  const baseWatchlist = offlineSnapshot.watchlist.items.find((item) => item.symbol === seedItem.symbol);
  const baseCandidate = offlineSnapshot.candidates.items.find((item) => item.symbol === seedItem.symbol);
  const baseDashboard = offlineSnapshot.stock_dashboards[seedItem.symbol];
  if (!baseWatchlist || !baseCandidate || !baseDashboard) {
    return buildGeneratedPayload(seedItem);
  }

  const replacements: Array<[string, string]> = [];
  if (seedItem.name && seedItem.name !== baseDashboard.stock.name) {
    replacements.push([baseDashboard.stock.name, seedItem.name]);
  }

  const watchlistItem = clone(baseWatchlist);
  watchlistItem.name = seedItem.name;
  watchlistItem.source_kind = seedItem.source_kind;
  watchlistItem.added_at = seedItem.added_at;
  watchlistItem.updated_at = seedItem.updated_at;
  watchlistItem.last_analyzed_at = seedItem.last_analyzed_at;
  watchlistItem.latest_generated_at = seedItem.last_analyzed_at;

  const candidate = deepReplaceTokens(clone(baseCandidate), replacements);
  candidate.name = seedItem.name;
  candidate.generated_at = seedItem.last_analyzed_at;
  candidate.change_summary = candidate.change_summary;

  const stockDashboard = deepReplaceTokens(clone(baseDashboard), replacements);
  stockDashboard.stock.name = seedItem.name;
  stockDashboard.recommendation.generated_at = seedItem.last_analyzed_at;
  stockDashboard.recommendation.updated_at = seedItem.last_analyzed_at;
  stockDashboard.hero.last_updated = seedItem.last_analyzed_at;
  stockDashboard.change.previous_generated_at = addMinutes(seedItem.last_analyzed_at, -7 * 24 * 60);

  return {
    watchlistItem,
    candidate,
    stockDashboard,
  };
}

function sortCandidates(items: CandidateItemView[]): CandidateItemView[] {
  const directionPriority: Record<RecommendationDirection, number> = {
    buy: 4,
    watch: 3,
    reduce: 2,
    risk_alert: 1,
  };
  return [...items]
    .sort((left, right) => {
      const directionGap = directionPriority[right.direction] - directionPriority[left.direction];
      if (directionGap !== 0) return directionGap;
      const confidenceGap = right.confidence_score - left.confidence_score;
      if (confidenceGap !== 0) return confidenceGap;
      return right.price_return_20d - left.price_return_20d;
    })
    .map((item, index) => ({
      ...item,
      rank: index + 1,
    }));
}

function buildPayloads(state: StoredWatchlistState): {
  watchlist: WatchlistResponse;
  candidates: DashboardShellPayload["candidates"];
  stockDashboards: Record<string, StockDashboardResponse>;
} {
  const entries = state.items
    .map((item) => (offlineSnapshot.stock_dashboards[item.symbol] ? patchStaticPayload(item) : buildGeneratedPayload(item)))
    .sort((left, right) => new Date(right.watchlistItem.updated_at).getTime() - new Date(left.watchlistItem.updated_at).getTime());

  const watchlistItems = entries.map((entry) => entry.watchlistItem);
  const candidates = sortCandidates(entries.map((entry) => entry.candidate));
  const stockDashboards = Object.fromEntries(entries.map((entry) => [entry.watchlistItem.symbol, entry.stockDashboard]));

  return {
    watchlist: {
      generated_at: nowNoZone(),
      items: watchlistItems,
    },
    candidates: {
      generated_at: nowNoZone(),
      items: candidates,
    },
    stockDashboards,
  };
}

function fallbackSymbol(state: StoredWatchlistState, requestedSymbol: string): string {
  if (state.items.some((item) => item.symbol === requestedSymbol)) {
    return requestedSymbol;
  }
  return state.items[0]?.symbol ?? defaultSymbols[0];
}

function buildMessage(symbol: string, name: string, action: "add" | "refresh"): string {
  if (action === "add") {
    return `已在离线本地自选池中加入 ${name}（${symbol}），并生成演示分析。`;
  }
  return `已在离线本地自选池中重新分析 ${name}（${symbol}）。`;
}

export const offlineLocal = {
  loadShellData(): DashboardShellPayload {
    const state = loadState();
    const payloads = buildPayloads(state);
    return {
      watchlist: payloads.watchlist,
      candidates: payloads.candidates,
      glossary: offlineSnapshot.glossary,
    };
  },

  getStockDashboard(symbol: string): StockDashboardResponse {
    const state = loadState();
    const payloads = buildPayloads(state);
    const resolvedSymbol = fallbackSymbol(state, normalizeSymbol(symbol));
    return payloads.stockDashboards[resolvedSymbol] ?? offlineSnapshot.stock_dashboards[defaultSymbols[0]];
  },

  getOperationsDashboard(symbol: string): OperationsDashboardResponse {
    if (offlineSnapshot.operations_dashboards[symbol]) {
      return clone(offlineSnapshot.operations_dashboards[symbol]);
    }
    const seed = hashString(symbol);
    const templateSymbol = defaultSymbols[seed % defaultSymbols.length];
    return clone(offlineSnapshot.operations_dashboards[templateSymbol]);
  },

  resetDemo(): DashboardBootstrapResponse {
    const state = resetState();
    return {
      symbols: state.items.map((item) => item.symbol),
      recommendation_count: state.items.length * 2,
      candidate_count: state.items.length,
    };
  },

  addWatchlist(symbolInput: string, nameInput?: string): WatchlistMutationResponse {
    const symbol = normalizeSymbol(symbolInput);
    const now = nowNoZone();
    const name = nameInput?.trim() || `自选标的 ${symbol.slice(0, 6)}`;
    const state = loadState();
    const existing = state.items.find((item) => item.symbol === symbol);
    if (existing) {
      existing.name = name;
      existing.source_kind = "user_input";
      existing.updated_at = now;
      existing.last_analyzed_at = now;
      saveState(state);
    } else {
      state.items.unshift({
        symbol,
        name,
        source_kind: "user_input",
        added_at: now,
        updated_at: now,
        last_analyzed_at: now,
      });
      saveState(state);
    }
    const payloads = buildPayloads(loadState());
    const item = payloads.watchlist.items.find((entry) => entry.symbol === symbol);
    if (!item) {
      throw new Error("离线自选池写入成功，但未能生成面板数据。");
    }
    return {
      item,
      message: buildMessage(item.symbol, item.name, "add"),
    };
  },

  refreshWatchlist(symbolInput: string): WatchlistMutationResponse {
    const symbol = normalizeSymbol(symbolInput);
    const state = loadState();
    const existing = state.items.find((item) => item.symbol === symbol);
    if (!existing) {
      throw new Error(`${symbol} 不在当前自选池中。`);
    }
    const now = nowNoZone();
    existing.updated_at = now;
    existing.last_analyzed_at = now;
    saveState(state);
    const payloads = buildPayloads(loadState());
    const item = payloads.watchlist.items.find((entry) => entry.symbol === symbol);
    if (!item) {
      throw new Error("离线自选池刷新成功，但未能生成面板数据。");
    }
    return {
      item,
      message: buildMessage(item.symbol, item.name, "refresh"),
    };
  },

  removeWatchlist(symbolInput: string): WatchlistDeleteResponse {
    const symbol = normalizeSymbol(symbolInput);
    const state = loadState();
    const nextItems = state.items.filter((item) => item.symbol !== symbol);
    if (nextItems.length === state.items.length) {
      throw new Error(`${symbol} 不在当前自选池中。`);
    }
    saveState({ items: nextItems });
    return {
      symbol,
      removed: true,
      active_count: nextItems.length,
      removed_at: nowNoZone(),
    };
  },
};
