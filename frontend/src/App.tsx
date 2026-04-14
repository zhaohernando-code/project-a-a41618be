import { startTransition, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "./api";
import type {
  CandidateItemView,
  CandidateListResponse,
  GlossaryEntryView,
  PricePointView,
  StockDashboardResponse,
} from "./types";

type ViewMode = "candidates" | "stock";

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

function App() {
  const [view, setView] = useState<ViewMode>("candidates");
  const [candidates, setCandidates] = useState<CandidateListResponse | null>(null);
  const [glossary, setGlossary] = useState<GlossaryEntryView[]>([]);
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [dashboard, setDashboard] = useState<StockDashboardResponse | null>(null);
  const [questionDraft, setQuestionDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const activeCandidate = useMemo(
    () => candidates?.items.find((item) => item.symbol === selectedSymbol) ?? candidates?.items[0] ?? null,
    [candidates, selectedSymbol],
  );

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [candidatePayload, glossaryPayload] = await Promise.all([
          api.getCandidates(),
          api.getGlossary(),
        ]);
        if (cancelled) return;
        setCandidates(candidatePayload);
        setGlossary(glossaryPayload);
        const initialSymbol = candidatePayload.items[0]?.symbol ?? null;
        setSelectedSymbol(initialSymbol);
      } catch (loadError) {
        if (cancelled) return;
        setError(loadError instanceof Error ? loadError.message : "加载看板失败。");
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedSymbol) return;
    const symbol = selectedSymbol;
    let cancelled = false;
    async function loadDetail() {
      setLoadingDetail(true);
      try {
        const payload = await api.getStockDashboard(symbol);
        if (cancelled) return;
        setDashboard(payload);
        setQuestionDraft(payload.follow_up.suggested_questions[0] ?? "");
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "加载单票解释页失败。");
        }
      } finally {
        if (!cancelled) {
          setLoadingDetail(false);
        }
      }
    }
    loadDetail();
    return () => {
      cancelled = true;
    };
  }, [selectedSymbol]);

  async function handleBootstrap() {
    setLoading(true);
    setError(null);
    try {
      await api.bootstrapDemo();
      const [candidatePayload, glossaryPayload] = await Promise.all([
        api.getCandidates(),
        api.getGlossary(),
      ]);
      setCandidates(candidatePayload);
      setGlossary(glossaryPayload);
      setSelectedSymbol(candidatePayload.items[0]?.symbol ?? null);
    } catch (bootstrapError) {
      setError(bootstrapError instanceof Error ? bootstrapError.message : "写入演示数据失败。");
    } finally {
      setLoading(false);
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
      </nav>

      {error ? (
        <section className="empty-state">
          <h2>还没有可展示的数据</h2>
          <p>{error}</p>
          <button className="primary-button" onClick={handleBootstrap}>
            写入演示 watchlist
          </button>
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
                        <p className="summary-copy">当前建议没有自动生成模拟订单，下一步会在分离式模拟交易阶段补齐完整闭环。</p>
                      )}
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
