import { ArrowLeftOutlined, CalendarOutlined, CopyOutlined, LineChartOutlined, QuestionCircleOutlined, ReloadOutlined, WarningOutlined } from "@ant-design/icons";
import { Button, Empty, Input, Select, Skeleton, Tag, Typography } from "antd";
import { useState } from "react";
import type { MobileAppShellProps, MobileStockPanelKey } from "./types";
import { MobilePriceLineChart } from "./MobilePriceLineChart";
import {
  claimGateDescription,
  claimGateStatusLabel,
  displayBenchmarkLabel,
  displayWindowLabel,
  eventDirectionLabel,
  eventDirectionStatus,
  eventEvidenceText,
  eventTriggerLabel,
  horizonLabel,
  manualReviewModelLabel,
  manualReviewStatusLabel,
  sanitizeDisplayText,
  validationStatusLabel,
} from "../../utils/labels";
import { directionColor, formatDate, formatNumber, formatPercent, formatSignedNumber, valueTone } from "../../utils/format";
import { directionLabels, factorLabels } from "../../utils/constants";

const { Text, Title } = Typography;
const { TextArea } = Input;

export function MobileStockDetail(props: MobileAppShellProps) {
  const [localPanel, setLocalPanel] = useState<MobileStockPanelKey>("advice");
  const panel = props.stockPanel ?? localPanel;
  const setPanel = props.setStockPanel ?? setLocalPanel;
  const dashboard = props.dashboard;

  if (props.loadingDetail) {
    return (
      <main className="mobile-page">
        <Skeleton active paragraph={{ rows: 10 }} />
      </main>
    );
  }

  if (!dashboard) {
    return (
      <main className="mobile-page mobile-page-centered">
        <Empty description="当前没有可展示的单票分析" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </main>
    );
  }

  const recommendation = dashboard.recommendation;
  const latestPoint = dashboard.price_chart[dashboard.price_chart.length - 1];
  const previousPoint = dashboard.price_chart[dashboard.price_chart.length - 2];
  const dayChangeValue = latestPoint && previousPoint ? latestPoint.close_price - previousPoint.close_price : null;
  const todayPriceChart = dashboard.today_price_chart ?? [];
  const visibleDrivers = recommendation.evidence.primary_drivers.slice(0, 3);
  const visibleRisks = [
    ...recommendation.risk.risk_flags,
    ...recommendation.risk.downgrade_conditions,
  ].slice(0, 4);
  const fallbackAdvice = [
    { title: "不追高", detail: sanitizeDisplayText(claimGateDescription(recommendation.claim_gate)), icon: <LineChartOutlined /> },
    { title: "观察中枢", detail: displayWindowLabel(recommendation.historical_validation.window_definition), icon: <CalendarOutlined /> },
    { title: "风险优先", detail: sanitizeDisplayText(dashboard.risk_panel.change_hint || dashboard.risk_panel.headline), icon: <WarningOutlined /> },
  ];
  const adviceItems = visibleDrivers.length > 0
    ? visibleDrivers.map((item, index) => ({
        title: index === 0 ? dashboard.hero.direction_label : index === 1 ? "观察中枢" : "风险优先",
        detail: sanitizeDisplayText(item),
        icon: index === 0 ? <LineChartOutlined /> : index === 1 ? <CalendarOutlined /> : <WarningOutlined />,
      }))
    : fallbackAdvice;
  const eventAnalyses = dashboard.event_analyses ?? [];
  const panelItems: Array<[MobileStockPanelKey, string]> = [
    ["advice", "建议"],
    ["evidence", "证据"],
    ["risk", "风险"],
    ...(props.canUseManualResearch ? [["question", "追问"] satisfies [MobileStockPanelKey, string]] : []),
  ];

  return (
    <main className="mobile-page mobile-stock-page">
      <header className="mobile-app-top-bar mobile-stock-top-bar">
        <Button className="mobile-icon-button" type="text" icon={<ArrowLeftOutlined />} onClick={() => props.onTabChange("home")} />
        <strong>单票分析</strong>
        <Button className="mobile-icon-button" type="text" icon={<ReloadOutlined />} onClick={() => void props.onRefresh()} />
      </header>

      <section className="mobile-stock-hero">
        <div>
          <Title level={2}>{dashboard.stock.name}</Title>
          <Text>{dashboard.stock.symbol} · {dashboard.hero.sector_tags[0] ?? dashboard.stock.exchange}</Text>
        </div>
        <div className="mobile-stock-quote">
          <strong>{formatNumber(dashboard.hero.latest_close)}</strong>
          <span className={`value-${valueTone(dashboard.hero.day_change_pct)}`}>
            {`${formatSignedNumber(dayChangeValue)}  ${formatPercent(dashboard.hero.day_change_pct)}`}
          </span>
        </div>
      </section>

      <section className="mobile-stock-card mobile-stock-conclusion">
        <div className="mobile-stock-card-head">
          <div>
            <Text>当前结论</Text>
            <Title level={3}>{dashboard.hero.direction_label}</Title>
          </div>
          <span className="mobile-target-badge"><QuestionCircleOutlined /></span>
        </div>
        <div className="mobile-stock-pill-row">
          <Tag color={directionColor(recommendation.claim_gate.public_direction)}>{dashboard.hero.direction_label}</Tag>
          <Tag>{`${recommendation.confidence_label}置信`}</Tag>
          <Tag>{claimGateStatusLabel(recommendation.claim_gate.status)}</Tag>
        </div>
        <p>{sanitizeDisplayText(recommendation.summary)}</p>
        <div className="mobile-stock-stat-strip">
          <div>
            <span>20日</span>
            <strong className={`value-${valueTone(dashboard.hero.day_change_pct)}`}>{formatPercent(dashboard.hero.day_change_pct)}</strong>
          </div>
          <div>
            <span>RankIC</span>
            <strong className={`value-${valueTone(recommendation.historical_validation.metrics?.rank_ic_mean)}`}>{formatSignedNumber(recommendation.historical_validation.metrics?.rank_ic_mean)}</strong>
          </div>
          <div>
            <span>样本数</span>
            <strong>{recommendation.claim_gate.sample_count ?? "--"}</strong>
          </div>
        </div>
      </section>

      <section className="mobile-stock-card mobile-stock-price-card">
        <div className="mobile-stock-section-head">
          <div>
            <Title level={4}>价格轨迹</Title>
            <Text>近60日</Text>
          </div>
          <span>{formatDate(dashboard.hero.last_updated)}</span>
        </div>
        <MobilePriceLineChart points={dashboard.price_chart} />
      </section>

      {todayPriceChart.length >= 2 ? (
        <section className="mobile-stock-card mobile-stock-price-card">
          <div className="mobile-stock-section-head">
            <div>
              <Title level={4}>今日价格轨迹</Title>
              <Text>5分钟</Text>
            </div>
            <span>{formatDate(todayPriceChart[todayPriceChart.length - 1]?.observed_at)}</span>
          </div>
          <MobilePriceLineChart points={todayPriceChart} />
        </section>
      ) : null}

      <section className="mobile-stock-card mobile-stock-analysis-card">
        <div className="mobile-stock-section-head">
          <div>
            <Title level={4}>事件深度分析</Title>
            <Text>{eventAnalyses.length > 0 ? `${eventAnalyses.length} 条记录` : "暂无记录"}</Text>
          </div>
          <QuestionCircleOutlined />
        </div>
        {eventAnalyses.length === 0 ? (
          <p>暂无事件深度分析记录。</p>
        ) : (
          <div className="mobile-stock-insight-list">
            {eventAnalyses.slice(0, 2).map((item) => (
              <article key={item.file || `${item.trigger_type}-${item.generated_at}`}>
                <span className={`mobile-stock-insight-icon ${eventDirectionStatus(item.independent_direction) === "fail" ? "warning" : ""}`}>
                  <WarningOutlined />
                </span>
                <div>
                  <strong>{eventTriggerLabel(item.trigger_type)}</strong>
                  <p>{sanitizeDisplayText(item.trigger_detail || item.correction_suggestion || item.next_checkpoint)}</p>
                  <p>{`${eventDirectionLabel(item.independent_direction)} · 置信 ${formatPercent(item.confidence)} · ${formatDate(item.generated_at)}`}</p>
                  {item.key_evidence[0] ? <p>{eventEvidenceText(item.key_evidence[0])}</p> : null}
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="mobile-stock-card mobile-stock-analysis-card">
        <div className="mobile-stock-tabs">
          {panelItems.map(([key, label]) => (
            <button key={key} type="button" className={panel === key ? "active" : ""} onClick={() => setPanel(key)}>
              {label}
            </button>
          ))}
        </div>

      {panel === "advice" ? (
        <div className="mobile-stock-insight-list">
          {adviceItems.map((item) => (
            <article key={`${item.title}-${item.detail}`}>
              <span className="mobile-stock-insight-icon">{item.icon}</span>
              <div>
                <strong>{item.title}</strong>
                <p>{item.detail}</p>
              </div>
            </article>
          ))}
        </div>
      ) : null}

      {panel === "evidence" ? (
        <div className="mobile-stock-insight-list">
            {recommendation.evidence.factor_cards.map((card) => (
              <article key={card.factor_key}>
                <span className="mobile-stock-insight-icon"><LineChartOutlined /></span>
                <div>
                  <strong>{factorLabels[card.factor_key] ?? card.factor_key}</strong>
                  <p>{sanitizeDisplayText(card.headline)}</p>
                  {card.score_contribution !== undefined && card.score_contribution !== null ? (
                    <p>{`贡献 ${card.score_contribution.toFixed(3)}${card.dynamic_weight !== undefined && card.dynamic_weight !== null ? ` · 权重 ${formatPercent(card.dynamic_weight)}` : ""}`}</p>
                  ) : null}
                  {card.direction ? <em>{directionLabels[card.direction] ?? card.direction}</em> : null}
                </div>
              </article>
            ))}
        </div>
      ) : null}

      {panel === "risk" ? (
        <div className="mobile-stock-insight-list">
          {(visibleRisks.length > 0 ? visibleRisks : [dashboard.risk_panel.headline]).map((item) => (
            <article key={item}>
              <span className="mobile-stock-insight-icon warning"><WarningOutlined /></span>
              <div>
                <strong>风险条件</strong>
                <p>{sanitizeDisplayText(item)}</p>
              </div>
            </article>
          ))}
          {recommendation.historical_validation.note ? (
            <article>
              <span className="mobile-stock-insight-icon"><CalendarOutlined /></span>
              <div>
                <strong>验证说明</strong>
                <p>{sanitizeDisplayText(recommendation.historical_validation.note)}</p>
              </div>
            </article>
          ) : null}
        </div>
      ) : null}

      {panel === "question" && props.canUseManualResearch ? (
        <div className="mobile-question-panel">
          <div className="mobile-stock-section-head">
            <div>
              <Title level={4}>追问与人工研究</Title>
              <Text>{manualReviewStatusLabel(recommendation.manual_llm_review.status)}</Text>
            </div>
            <QuestionCircleOutlined />
          </div>
          <div className="mobile-question-chips">
            {dashboard.follow_up.suggested_questions.map((question) => (
              <button key={question} type="button" onClick={() => props.setQuestionDraft(question)}>{question}</button>
            ))}
          </div>
          <Select
            className="mobile-full-width"
            value={props.analysisKeyId}
            allowClear
            placeholder="可选模型 Key；留空使用 builtin GPT"
            options={props.modelApiKeys.map((item) => ({
              value: item.id,
              label: `${item.name} · ${item.model_name}${item.is_default ? " · 默认" : ""}`,
            }))}
            onChange={(value) => props.setAnalysisKeyId(value)}
            onClear={() => props.setAnalysisKeyId(undefined)}
          />
          <TextArea
            rows={4}
            value={props.questionDraft}
            onChange={(event) => props.setQuestionDraft(event.target.value)}
            placeholder="输入你要提交给人工研究工作流的问题"
          />
          <div className="mobile-action-row">
            <Button type="primary" loading={props.analysisLoading} onClick={() => void props.onSubmitManualResearch()}>
              提交研究
            </Button>
            <Button icon={<CopyOutlined />} onClick={() => void props.onCopyPrompt()}>
              复制追问包
            </Button>
          </div>
          <div className="mobile-stock-meta-grid">
            <div><span>模型标签</span><strong>{recommendation.manual_llm_review.model_label ? manualReviewModelLabel(recommendation.manual_llm_review.model_label) : "未指定"}</strong></div>
            <div><span>产物时间</span><strong>{formatDate(recommendation.manual_llm_review.generated_at)}</strong></div>
          </div>
          <p>{recommendation.manual_llm_review.summary ? sanitizeDisplayText(recommendation.manual_llm_review.summary) : "当前没有额外的人工研究摘要。"}</p>
        </div>
      ) : null}
      </section>

      {props.canUseManualResearch ? (
        <Button className="mobile-stock-primary-cta" type="primary" size="large" onClick={() => setPanel("question")}>
          发起人工追问
        </Button>
      ) : null}
    </main>
  );
}
