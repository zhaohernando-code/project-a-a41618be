import { startTransition, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "./api";
import type {
  CandidateItemView,
  CandidateListResponse,
  GlossaryEntryView,
  OperationsDashboardResponse,
  PortfolioNavPointView,
  PricePointView,
  StockDashboardResponse,
} from "./types";

type ViewMode = "candidates" | "stock" | "operations";

const numberFormatter = new Intl.NumberFormat("zh-CN", {
  maximumFractionDigits: 2,
});

const percentFormatter = new Intl.NumberFormat("zh-CN", {
  style: "percent",
  maximumFractionDigits: 1,
  signDisplay: "always",
});

function formatDate(value?: string | null): string {
  if (!value) return "未提供";
  return new Date(value).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function directionTone(direction: string): "positive" | "negative" | "neutral" {
  if (direction === "buy") return "positive";
  if (direction === "reduce" || direction === "risk_alert") return "negative";
  return "neutral";
}

function statusTone(status: string): "positive" | "negative" | "neutral" {
  if (status === "pass" || status === "hit" || status === "closed_beta_ready") return "positive";
  if (status === "fail" || status === "miss" || status === "hold") return "negative";
  return "neutral";
}

function Sparkline({ points }: { points: PricePointView[] }) {
  if (points.length === 0) {
    return <div className="chart-empty">暂无价格轨迹</div>;
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
    max === min ? height / 2 : height - ((value - min) / (max - min)) * (height - 40) - 20;

  const linePath = points
    .map((point, index) => `${index === 0 ? "M" : "L"} ${index * xStep} ${scaleY(point.close_price)}`)
    .join(" ");

  const areaPath = `${linePath} L ${width} ${height} L 0 ${height} Z`;

  return (
    <svg className="sparkline" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
      <defs>
        <linearGradient id="chart-fill" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="rgba(10,101,255,0.28)" />
          <stop offset="100%" stopColor="rgba(10,101,255,0.02)" />
        </linearGradient>
      </defs>
      {points.map((point, index) => {
        const barHeight = volumeMax === 0 ? 0 : (point.volume / volumeMax) * 42;
        return (
          <rect
            key={`${point.observed_at}-volume`}
            className="sparkline-volume"
            x={index * xStep - 4}
            y={height - barHeight}
            width={8}
            height={barHeight}
            rx={4}
          />
        );
      })}
      <path className="sparkline-area" d={areaPath} />
      <path className="sparkline-line" d={linePath} />
      {points.length > 0 ? (
        <circle
          className="sparkline-dot"
          cx={(points.length - 1) * xStep}
          cy={scaleY(points[points.length - 1].close_price)}
          r={5}
        />
      ) : null}
    </svg>
  );
}

function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: "positive" | "negative" | "neutral" }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

function NavSparkline({ points }: { points: PortfolioNavPointView[] }) {
  if (points.length === 0) {
    return <div className="chart-empty">暂无净值轨迹</div>;
  }

  const width = 760;
  const height = 180;
  const navValues = points.map((point) => point.nav);
  const benchmarkValues = points.map((point) => point.benchmark_nav);
  const min = Math.min(...navValues, ...benchmarkValues);
  const max = Math.max(...navValues, ...benchmarkValues);
  const xStep = points.length > 1 ? width / (points.length - 1) : width;
  const scaleY = (value: number) =>
    max === min ? height / 2 : height - ((value - min) / (max - min)) * (height - 36) - 18;

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

function App() {
  const [view, setView] = useState<ViewMode>("candidates");
  const [candidates, setCandidates] = useState<CandidateListResponse | null>(null);
  const [glossary, setGlossary] = useState<GlossaryEntryView[]>([]);
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [dashboard, setDashboard] = useState<StockDashboardResponse | null>(null);
  const [operations, setOperations] = useState<OperationsDashboardResponse | null>(null);
  const [questionDraft, setQuestionDraft] = useState("");
  const [betaKeyDraft, setBetaKeyDraft] = useState(() => api.getBetaAccessKey());
  const [loading, setLoading] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [loadingOperations, setLoadingOperations] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const activeCandidate = useMemo(
    () => candidates?.items.find((item) => item.symbol === selectedSymbol) ?? candidates?.items[0] ?? null,
    [candidates, selectedSymbol],
  );

  async function loadShellData(): Promise<string | null> {
    setLoading(true);
    setError(null);
    try {
      const [candidatePayload, glossaryPayload] = await Promise.all([
        api.getCandidates(),
        api.getGlossary(),
      ]);
      setCandidates(candidatePayload);
      setGlossary(glossaryPayload);
      const initialSymbol = candidatePayload.items[0]?.symbol ?? null;
      setSelectedSymbol((current) => current ?? initialSymbol);
      return initialSymbol;
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "加载看板失败。");
      return null;
    } finally {
      setLoading(false);
    }
  }

  async function loadDetailData(symbol: string) {
    setLoadingDetail(true);
    setLoadingOperations(true);
    try {
      const [stockPayload, operationsPayload] = await Promise.all([
        api.getStockDashboard(symbol),
        api.getOperationsDashboard(symbol),
      ]);
      setDashboard(stockPayload);
      setOperations(operationsPayload);
      setQuestionDraft(stockPayload.follow_up.suggested_questions[0] ?? "");
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "加载单票解释页失败。");
    } finally {
      setLoadingDetail(false);
      setLoadingOperations(false);
    }
  }

  useEffect(() => {
    void loadShellData();
  }, []);

  useEffect(() => {
    if (!selectedSymbol) return;
    const symbol = selectedSymbol;
    let cancelled = false;
    async function loadDetail() {
      if (cancelled) return;
      await loadDetailData(symbol);
      if (cancelled) {
        setLoadingDetail(false);
        setLoadingOperations(false);
      }
    }
    void loadDetail();
    return () => {
      cancelled = true;
    };
  }, [selectedSymbol]);

  async function handleBootstrap() {
    setError(null);
    try {
      await api.bootstrapDemo();
      const initialSymbol = await loadShellData();
      if (initialSymbol) {
        await loadDetailData(initialSymbol);
      }
    } catch (bootstrapError) {
      setError(bootstrapError instanceof Error ? bootstrapError.message : "写入演示数据失败。");
    }
  }

  async function handleApplyBetaKey() {
    api.setBetaAccessKey(betaKeyDraft);
    setError(null);
    const initialSymbol = await loadShellData();
    const resolvedSymbol = selectedSymbol ?? initialSymbol;
    if (resolvedSymbol) {
      await loadDetailData(resolvedSymbol);
    }
  }

  async function handleCopyPrompt() {
    if (!dashboard) return;
    const prompt = dashboard.follow_up.copy_prompt.replace("<在这里替换成你的追问>", questionDraft.trim() || "请解释当前建议最容易失效的条件。");
    await navigator.clipboard.writeText(prompt);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  }

  function handleCandidateSelect(symbol: string, nextView?: ViewMode) {
    startTransition(() => {
      setSelectedSymbol(symbol);
      if (nextView) {
        setView(nextView);
      }
    });
  }

  const mergedGlossary = dashboard?.glossary?.length ? dashboard.glossary : glossary;
  const accessDenied = error?.includes("beta access denied") ?? false;

  return (
    <div className="app-shell">
      <header className="hero-strip">
        <div>
          <p className="eyebrow">Evidence-First Advisory Dashboard</p>
          <h1>让建议说清楚为什么成立、为什么变化、何时失效</h1>
          <p className="hero-copy">
            围绕 2-8 周波段，把结构化因子、证据回溯、风险提示和 GPT 追问入口压缩成一个能被非专业用户读懂的解释面板。
          </p>
        </div>
        <div className="hero-actions">
          <div className="mini-stat">
            <span>候选股</span>
            <strong>{candidates?.items.length ?? 0}</strong>
          </div>
          <div className="mini-stat">
            <span>最近刷新</span>
            <strong>{candidates ? formatDate(candidates.generated_at) : "--"}</strong>
          </div>
        </div>
      </header>

      <nav className="view-switch">
        <button className={view === "candidates" ? "active" : ""} onClick={() => setView("candidates")}>
          候选股推荐页
        </button>
        <button className={view === "stock" ? "active" : ""} onClick={() => setView("stock")} disabled={!selectedSymbol}>
          单票分析页
        </button>
        <button className={view === "operations" ? "active" : ""} onClick={() => setView("operations")}>
          模拟交易与内测
        </button>
      </nav>

      {error ? (
        <section className="empty-state">
          <h2>还没有可展示的数据</h2>
          <p>{error}</p>
          {accessDenied ? (
            <div className="access-gate">
              <input
                className="access-input"
                value={betaKeyDraft}
                onChange={(event) => setBetaKeyDraft(event.target.value)}
                placeholder="输入小范围内测 access key"
              />
              <button className="primary-button" onClick={handleApplyBetaKey}>
                保存并重试
              </button>
            </div>
          ) : (
            <button className="primary-button" onClick={handleBootstrap}>
              写入演示 watchlist
            </button>
          )}
        </section>
      ) : null}

      {loading ? (
        <section className="loading-panel">正在读取候选股和术语解释…</section>
      ) : null}

      {!loading && !error && candidates ? (
        <>
          {view === "candidates" ? (
            <section className="page-grid">
              <div className="candidate-panel panel">
                <div className="panel-header">
                  <div>
                    <p className="panel-label">Top Picks</p>
                    <h2>候选股推荐页</h2>
                  </div>
                  <span className="muted-text">按建议方向、置信度和近 20 日趋势综合排序</span>
                </div>

                <div className="candidate-list">
                  {candidates.items.map((item) => (
                    <article
                      key={item.symbol}
                      className={`candidate-card ${item.symbol === activeCandidate?.symbol ? "candidate-card-active" : ""}`}
                      onClick={() => handleCandidateSelect(item.symbol)}
                    >
                      <div className="candidate-card-top">
                        <div className="candidate-rank">#{item.rank}</div>
                        <Badge tone={directionTone(item.direction)}>{item.direction_label}</Badge>
                      </div>
                      <div className="candidate-title-row">
                        <div>
                          <h3>{item.name}</h3>
                          <p>{item.symbol}</p>
                        </div>
                        <div className="candidate-price">
                          <strong>{item.last_close ? numberFormatter.format(item.last_close) : "--"}</strong>
                          <span>{percentFormatter.format(item.price_return_20d)}</span>
                        </div>
                      </div>
                      <p className="candidate-sector">{item.sector} · {item.applicable_period}</p>
                      <p className="candidate-why">{item.why_now}</p>
                      <div className="candidate-footer">
                        <span>{item.change_badge}</span>
                        <span>{item.confidence_label}置信</span>
                        <span>{item.evidence_status === "sufficient" ? "证据充足" : "证据降级"}</span>
                      </div>
                      <p className="candidate-change">{item.change_summary}</p>
                      <button
                        className="ghost-button"
                        onClick={(event) => {
                          event.stopPropagation();
                          handleCandidateSelect(item.symbol, "stock");
                        }}
                      >
                        看单票解释
                      </button>
                    </article>
                  ))}
                </div>
              </div>

              <aside className="panel summary-panel">
                {activeCandidate ? (
                  <>
                    <div className="panel-header">
                      <div>
                        <p className="panel-label">Selected</p>
                        <h2>{activeCandidate.name}</h2>
                      </div>
                      <Badge tone={directionTone(activeCandidate.direction)}>{activeCandidate.direction_label}</Badge>
                    </div>
                    <p className="summary-copy">{activeCandidate.summary}</p>
                    <dl className="summary-grid">
                      <div>
                        <dt>当前读法</dt>
                        <dd>{activeCandidate.why_now}</dd>
                      </div>
                      <div>
                        <dt>主要风险</dt>
                        <dd>{activeCandidate.primary_risk ?? "等待更多风险证据。"}</dd>
                      </div>
                      <div>
                        <dt>最近变化</dt>
                        <dd>{activeCandidate.change_summary}</dd>
                      </div>
                      <div>
                        <dt>数据时间</dt>
                        <dd>{formatDate(activeCandidate.as_of_data_time)}</dd>
                      </div>
                    </dl>
                    <button className="primary-button" onClick={() => handleCandidateSelect(activeCandidate.symbol, "stock")}>
                      进入 {activeCandidate.name} 单票页
                    </button>
                  </>
                ) : null}
              </aside>
            </section>
          ) : null}

          {view === "stock" ? (
            <section className="stock-page">
              {loadingDetail || !dashboard ? (
                <div className="loading-panel">正在读取单票解释链路…</div>
              ) : (
                <>
                  <section className="stock-hero panel">
                    <div className="stock-hero-main">
                      <p className="panel-label">Single Stock</p>
                      <h2>{dashboard.stock.name} <span>{dashboard.stock.symbol}</span></h2>
                      <p className="stock-summary">{dashboard.recommendation.summary}</p>
                      <div className="stock-badges">
                        <Badge tone={directionTone(dashboard.recommendation.direction)}>{dashboard.hero.direction_label}</Badge>
                        <Badge>{`${dashboard.recommendation.confidence_label}置信`}</Badge>
                        <Badge>{dashboard.recommendation.applicable_period}</Badge>
                      </div>
                    </div>
                    <div className="stock-hero-metrics">
                      <div>
                        <span>最新收盘</span>
                        <strong>{numberFormatter.format(dashboard.hero.latest_close)}</strong>
                      </div>
                      <div>
                        <span>日涨跌</span>
                        <strong>{percentFormatter.format(dashboard.hero.day_change_pct)}</strong>
                      </div>
                      <div>
                        <span>最近刷新</span>
                        <strong>{formatDate(dashboard.hero.last_updated)}</strong>
                      </div>
                    </div>
                  </section>

                  <section className="panel chart-panel">
                    <div className="panel-header">
                      <div>
                        <p className="panel-label">Price Context</p>
                        <h3>近 28 个交易日走势与量能</h3>
                      </div>
                      <div className="metric-pills">
                        {dashboard.hero.sector_tags.map((tag) => (
                          <span key={tag} className="metric-pill">{tag}</span>
                        ))}
                      </div>
                    </div>
                    <Sparkline points={dashboard.price_chart} />
                    <div className="chart-meta">
                      <span>区间高点 {numberFormatter.format(dashboard.hero.high_price)}</span>
                      <span>区间低点 {numberFormatter.format(dashboard.hero.low_price)}</span>
                      <span>换手率 {dashboard.hero.turnover_rate ? percentFormatter.format(dashboard.hero.turnover_rate / 100) : "未提供"}</span>
                    </div>
                  </section>

                  <section className="split-grid">
                    <article className="panel">
                      <div className="panel-header">
                        <div>
                          <p className="panel-label">Why It Works</p>
                          <h3>建议为何成立</h3>
                        </div>
                      </div>
                      <div className="factor-list">
                        {Object.entries(dashboard.recommendation.factor_breakdown).map(([key, value]) => (
                          <div key={key} className="factor-card">
                            <div className="factor-card-top">
                              <h4>{key}</h4>
                              {"direction" in value ? <Badge tone={directionTone(String(value.direction))}>{String(value.direction)}</Badge> : null}
                            </div>
                            {"score" in value ? <p className="factor-score">分数 {Number(value.score).toFixed(2)}</p> : null}
                            {Array.isArray(value.drivers) ? (
                              <p className="factor-text">{value.drivers[0] ?? "暂无主驱动描述。"}</p>
                            ) : (
                              <p className="factor-text">系统用于汇总价格、事件和降级状态的融合层。</p>
                            )}
                            {Array.isArray(value.risks) && value.risks.length > 0 ? (
                              <p className="factor-risk">{value.risks[0]}</p>
                            ) : null}
                          </div>
                        ))}
                      </div>
                    </article>

                    <article className="panel">
                      <div className="panel-header">
                        <div>
                          <p className="panel-label">What Changed</p>
                          <h3>为什么这次不一样</h3>
                        </div>
                        <Badge>{dashboard.change.change_badge}</Badge>
                      </div>
                      <p className="summary-copy">{dashboard.change.summary}</p>
                      <ul className="flat-list">
                        {dashboard.change.reasons.map((reason) => (
                          <li key={reason}>{reason}</li>
                        ))}
                      </ul>
                      <div className="change-meta">
                        <span>上一版方向：{dashboard.change.previous_direction ?? "无"}</span>
                        <span>上一版时间：{formatDate(dashboard.change.previous_generated_at)}</span>
                      </div>
                    </article>
                  </section>

                  <section className="split-grid">
                    <article className="panel">
                      <div className="panel-header">
                        <div>
                          <p className="panel-label">Recent Events</p>
                          <h3>最近影响这条建议的事件</h3>
                        </div>
                      </div>
                      <div className="news-list">
                        {dashboard.recent_news.map((item) => (
                          <article key={`${item.headline}-${item.published_at}`} className="news-card">
                            <div className="news-card-top">
                              <Badge tone={item.impact_direction === "positive" ? "positive" : item.impact_direction === "negative" ? "negative" : "neutral"}>
                                {item.impact_direction === "positive" ? "正向" : item.impact_direction === "negative" ? "反向" : "中性"}
                              </Badge>
                              <span>{formatDate(item.published_at)}</span>
                            </div>
                            <h4>{item.headline}</h4>
                            <p>{item.summary}</p>
                            <small>{item.entity_scope} · {item.source_uri}</small>
                          </article>
                        ))}
                      </div>
                    </article>

                    <article className="panel">
                      <div className="panel-header">
                        <div>
                          <p className="panel-label">Risk</p>
                          <h3>何时失效，应该先看哪里</h3>
                        </div>
                      </div>
                      <p className="summary-copy">{dashboard.risk_panel.headline}</p>
                      <ul className="flat-list">
                        {dashboard.risk_panel.items.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                      <p className="risk-disclaimer">{dashboard.risk_panel.disclaimer}</p>
                    </article>
                  </section>

                  <section className="split-grid">
                    <article className="panel">
                      <div className="panel-header">
                        <div>
                          <p className="panel-label">Evidence Trace</p>
                          <h3>证据回溯</h3>
                        </div>
                      </div>
                      <div className="evidence-list">
                        {dashboard.evidence.map((item) => (
                          <article key={`${item.evidence_type}-${item.record_id}-${item.rank}`} className="evidence-card">
                            <div className="evidence-card-top">
                              <strong>{item.label}</strong>
                              <span>#{item.rank}</span>
                            </div>
                            <p>{item.snippet ?? "暂无摘要。"} </p>
                            <div className="evidence-meta">
                              <span>{item.role}</span>
                              <span>{formatDate(item.timestamp)}</span>
                              <span>{item.lineage.license_tag}</span>
                            </div>
                            <small>{item.lineage.source_uri}</small>
                          </article>
                        ))}
                      </div>
                    </article>

                    <article className="panel">
                      <div className="panel-header">
                        <div>
                          <p className="panel-label">Glossary</p>
                          <h3>术语解释</h3>
                        </div>
                      </div>
                      <div className="glossary-list">
                        {mergedGlossary.map((item) => (
                          <article key={item.term} className="glossary-card">
                            <h4>{item.term}</h4>
                            <p>{item.plain_explanation}</p>
                            <small>{item.why_it_matters}</small>
                          </article>
                        ))}
                      </div>
                    </article>
                  </section>

                  <section className="split-grid">
                    <article className="panel">
                      <div className="panel-header">
                        <div>
                          <p className="panel-label">Ask GPT</p>
                          <h3>GPT 追问入口</h3>
                        </div>
                        <button className="primary-button" onClick={handleCopyPrompt}>
                          {copied ? "已复制追问包" : "复制追问包"}
                        </button>
                      </div>
                      <div className="prompt-chips">
                        {dashboard.follow_up.suggested_questions.map((question) => (
                          <button key={question} className="chip-button" onClick={() => setQuestionDraft(question)}>
                            {question}
                          </button>
                        ))}
                      </div>
                      <textarea
                        className="prompt-editor"
                        value={questionDraft}
                        onChange={(event) => setQuestionDraft(event.target.value)}
                        placeholder="输入你真正想追问 GPT 的问题"
                      />
                      <div className="prompt-hint">
                        复制内容里已经带上当前建议、变化原因和关键证据，适合直接粘给后续 GPT 服务。
                      </div>
                    </article>

                    <article className="panel">
                      <div className="panel-header">
                        <div>
                          <p className="panel-label">Simulation Link</p>
                          <h3>与后续模拟交易的衔接</h3>
                        </div>
                      </div>
                      {dashboard.simulation_orders.length > 0 ? (
                        <div className="order-list">
                          {dashboard.simulation_orders.map((order) => (
                            <article key={order.id} className="order-card">
                              <div className="order-top">
                                <strong>{order.order_source === "manual" ? "手动模拟" : "模型自动持仓"}</strong>
                                <Badge tone={order.side === "buy" ? "positive" : "negative"}>{order.side}</Badge>
                              </div>
                              <p>{formatDate(order.requested_at)} · {order.quantity} 股 · {order.status}</p>
                              <small>
                                {order.fills[0]
                                  ? `首笔成交 ${numberFormatter.format(order.fills[0].price)}，滑点 ${order.fills[0].slippage_bps.toFixed(1)} bps`
                                  : "尚未成交"}
                              </small>
                            </article>
                          ))}
                        </div>
                      ) : (
                        <p className="summary-copy">当前建议没有自动生成模拟订单，但组合级收益、回撤和准入治理可在“模拟交易与内测”页统一查看。</p>
                      )}
                    </article>
                  </section>
                </>
              )}
            </section>
          ) : null}

          {view === "operations" ? (
            <section className="operations-page">
              {loadingOperations || !operations ? (
                <div className="loading-panel">正在读取模拟交易闭环与内测治理…</div>
              ) : (
                <>
                  <section className="split-grid">
                    <article className="panel">
                      <div className="panel-header">
                        <div>
                          <p className="panel-label">Closed Beta</p>
                          <h2>分离式模拟交易与内测准入</h2>
                        </div>
                        <Badge tone={statusTone(operations.overview.beta_readiness)}>{operations.overview.beta_readiness}</Badge>
                      </div>
                      <p className="summary-copy">
                        手动模拟与模型自动持仓已经分账运行，并将收益归因、回撤监控、建议命中复盘和访问治理收敛到同一运营面板。
                      </p>
                      <dl className="summary-grid">
                        <div>
                          <dt>手动仓数量</dt>
                          <dd>{operations.overview.manual_portfolio_count}</dd>
                        </div>
                        <div>
                          <dt>自动仓数量</dt>
                          <dd>{operations.overview.auto_portfolio_count}</dd>
                        </div>
                        <div>
                          <dt>建议复盘命中率</dt>
                          <dd>{percentFormatter.format(operations.overview.recommendation_replay_hit_rate)}</dd>
                        </div>
                        <div>
                          <dt>规则通过率</dt>
                          <dd>{percentFormatter.format(operations.overview.rule_pass_rate)}</dd>
                        </div>
                      </dl>
                    </article>

                    <article className="panel">
                      <div className="panel-header">
                        <div>
                          <p className="panel-label">Access</p>
                          <h3>访问控制与范围</h3>
                        </div>
                        <Badge tone={statusTone(operations.access_control.auth_mode === "open_demo" ? "warn" : "pass")}>
                          {operations.access_control.auth_mode}
                        </Badge>
                      </div>
                      <ul className="flat-list">
                        <li>Header: {operations.access_control.required_header}</li>
                        <li>Allowlist 槽位: {operations.access_control.allowlist_slots}</li>
                        <li>当前活跃用户: {operations.access_control.active_users}</li>
                        <li>Session TTL: {operations.access_control.session_ttl_minutes} 分钟</li>
                        <li>审计留档: {operations.access_control.audit_log_retention_days} 天</li>
                      </ul>
                      <p className="summary-copy">{operations.access_control.export_policy}</p>
                    </article>
                  </section>

                  <section className="portfolio-stack">
                    {operations.portfolios.map((portfolio) => (
                      <article key={portfolio.portfolio_key} className="panel portfolio-panel">
                        <div className="panel-header">
                          <div>
                            <p className="panel-label">{portfolio.mode_label}</p>
                            <h3>{portfolio.name}</h3>
                          </div>
                          <div className="stock-badges">
                            <Badge tone={statusTone(portfolio.total_return >= 0 ? "pass" : "fail")}>
                              总收益 {percentFormatter.format(portfolio.total_return)}
                            </Badge>
                            <Badge tone={statusTone(portfolio.excess_return >= 0 ? "pass" : "warn")}>
                              超额 {percentFormatter.format(portfolio.excess_return)}
                            </Badge>
                            <Badge tone={statusTone(portfolio.max_drawdown > -0.12 ? "pass" : "warn")}>
                              最大回撤 {percentFormatter.format(portfolio.max_drawdown)}
                            </Badge>
                          </div>
                        </div>
                        <p className="summary-copy">{portfolio.strategy_summary}</p>
                        <NavSparkline points={portfolio.nav_history} />
                        <dl className="summary-grid">
                          <div>
                            <dt>净值</dt>
                            <dd>{numberFormatter.format(portfolio.net_asset_value)}</dd>
                          </div>
                          <div>
                            <dt>基准</dt>
                            <dd>{portfolio.benchmark_symbol ?? "未配置"} / {percentFormatter.format(portfolio.benchmark_return)}</dd>
                          </div>
                          <div>
                            <dt>可用现金</dt>
                            <dd>{numberFormatter.format(portfolio.available_cash)}</dd>
                          </div>
                          <div>
                            <dt>仓位</dt>
                            <dd>{percentFormatter.format(portfolio.invested_ratio)}</dd>
                          </div>
                          <div>
                            <dt>已实现 / 未实现</dt>
                            <dd>{numberFormatter.format(portfolio.realized_pnl)} / {numberFormatter.format(portfolio.unrealized_pnl)}</dd>
                          </div>
                          <div>
                            <dt>佣金 / 税费</dt>
                            <dd>{numberFormatter.format(portfolio.fee_total)} / {numberFormatter.format(portfolio.tax_total)}</dd>
                          </div>
                        </dl>

                        <section className="portfolio-detail-grid">
                          <div className="mini-panel">
                            <h4>收益归因</h4>
                            <div className="metric-list">
                              {portfolio.attribution.map((item) => (
                                <div key={`${portfolio.portfolio_key}-${item.label}`} className="metric-row">
                                  <span>{item.label}</span>
                                  <strong>{numberFormatter.format(item.amount)}</strong>
                                </div>
                              ))}
                            </div>
                          </div>

                          <div className="mini-panel">
                            <h4>当前持仓</h4>
                            <div className="holding-list">
                              {portfolio.holdings.map((holding) => (
                                <article key={`${portfolio.portfolio_key}-${holding.symbol}`} className="holding-card">
                                  <div className="holding-top">
                                    <strong>{holding.name}</strong>
                                    <span>{percentFormatter.format(holding.portfolio_weight)}</span>
                                  </div>
                                  <p>{holding.symbol} · {holding.quantity} 股 · 成本 {numberFormatter.format(holding.avg_cost)}</p>
                                  <small>总盈亏 {numberFormatter.format(holding.total_pnl)} / 最新价 {numberFormatter.format(holding.last_price)}</small>
                                </article>
                              ))}
                            </div>
                          </div>

                          <div className="mini-panel">
                            <h4>A 股规则检查</h4>
                            <div className="rule-list">
                              {portfolio.rules.map((rule) => (
                                <article key={`${portfolio.portfolio_key}-${rule.code}`} className="rule-card">
                                  <div className="rule-top">
                                    <strong>{rule.title}</strong>
                                    <Badge tone={statusTone(rule.status)}>{rule.status}</Badge>
                                  </div>
                                  <p>{rule.detail}</p>
                                </article>
                              ))}
                            </div>
                          </div>
                        </section>

                        <section className="portfolio-detail-grid">
                          <div className="mini-panel">
                            <h4>最近订单</h4>
                            <div className="order-list">
                              {portfolio.recent_orders.map((order) => (
                                <article key={order.order_key} className="order-card">
                                  <div className="order-top">
                                    <strong>{order.stock_name}</strong>
                                    <Badge tone={order.side === "buy" ? "positive" : "negative"}>{order.side}</Badge>
                                  </div>
                                  <p>{formatDate(order.requested_at)} · {order.quantity} 股 · {order.order_type}</p>
                                  <small>成交均价 {order.avg_fill_price ? numberFormatter.format(order.avg_fill_price) : "--"} / 金额 {numberFormatter.format(order.gross_amount)}</small>
                                  <div className="inline-badges">
                                    {order.checks.map((check) => (
                                      <Badge key={`${order.order_key}-${check.code}`} tone={statusTone(check.status)}>
                                        {check.title}
                                      </Badge>
                                    ))}
                                  </div>
                                </article>
                              ))}
                            </div>
                          </div>

                          <div className="mini-panel">
                            <h4>当前告警</h4>
                            {portfolio.alerts.length > 0 ? (
                              <ul className="flat-list">
                                {portfolio.alerts.map((alert) => (
                                  <li key={`${portfolio.portfolio_key}-${alert}`}>{alert}</li>
                                ))}
                              </ul>
                            ) : (
                              <p className="summary-copy">当前没有触发额外的仓位或回撤告警。</p>
                            )}
                          </div>
                        </section>
                      </article>
                    ))}
                  </section>

                  <section className="split-grid">
                    <article className="panel">
                      <div className="panel-header">
                        <div>
                          <p className="panel-label">Replay</p>
                          <h3>建议命中复盘</h3>
                        </div>
                      </div>
                      <div className="replay-list">
                        {operations.recommendation_replay.map((item) => (
                          <article key={`replay-${item.recommendation_id}`} className="replay-card">
                            <div className="replay-top">
                              <div>
                                <strong>{item.stock_name}</strong>
                                <p>{item.symbol} · {item.review_window_days} 个交易日</p>
                              </div>
                              <Badge tone={statusTone(item.hit_status)}>{item.hit_status}</Badge>
                            </div>
                            <p>{item.summary}</p>
                            <div className="chart-meta">
                              <span>标的 {percentFormatter.format(item.stock_return)}</span>
                              <span>基准 {percentFormatter.format(item.benchmark_return)}</span>
                              <span>超额 {percentFormatter.format(item.excess_return)}</span>
                            </div>
                          </article>
                        ))}
                      </div>
                    </article>

                    <article className="panel">
                      <div className="panel-header">
                        <div>
                          <p className="panel-label">Refresh</p>
                          <h3>刷新策略</h3>
                        </div>
                      </div>
                      <div className="schedule-list">
                        {operations.refresh_policy.schedules.map((schedule) => (
                          <article key={schedule.scope} className="schedule-card">
                            <div className="schedule-top">
                              <strong>{schedule.scope}</strong>
                              <span>{schedule.cadence_minutes} 分钟</span>
                            </div>
                            <p>{schedule.trigger}</p>
                            <small>延迟 {schedule.market_delay_minutes} 分钟 / stale {schedule.stale_after_minutes} 分钟</small>
                          </article>
                        ))}
                      </div>
                    </article>
                  </section>

                  <section className="split-grid">
                    <article className="panel">
                      <div className="panel-header">
                        <div>
                          <p className="panel-label">Performance</p>
                          <h3>性能阈值</h3>
                        </div>
                      </div>
                      <div className="threshold-list">
                        {operations.performance_thresholds.map((item) => (
                          <article key={item.metric} className="threshold-card">
                            <div className="threshold-top">
                              <strong>{item.metric}</strong>
                              <Badge tone={statusTone(item.status)}>{item.status}</Badge>
                            </div>
                            <p>{item.note}</p>
                            <small>目标 {item.target} {item.unit} / 当前 {item.observed} {item.unit}</small>
                          </article>
                        ))}
                      </div>
                    </article>

                    <article className="panel">
                      <div className="panel-header">
                        <div>
                          <p className="panel-label">Launch Gates</p>
                          <h3>上线门槛</h3>
                        </div>
                      </div>
                      <div className="threshold-list">
                        {operations.launch_gates.map((item) => (
                          <article key={item.gate} className="threshold-card">
                            <div className="threshold-top">
                              <strong>{item.gate}</strong>
                              <Badge tone={statusTone(item.status)}>{item.status}</Badge>
                            </div>
                            <p>{item.threshold}</p>
                            <small>{item.current_value}</small>
                          </article>
                        ))}
                      </div>
                    </article>
                  </section>
                </>
              )}
            </section>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

export default App;
