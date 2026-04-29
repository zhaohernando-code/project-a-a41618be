import { CopyOutlined, QuestionCircleOutlined, ReloadOutlined } from "@ant-design/icons";
import { Alert, Button, Empty, Input, Select, Skeleton, Space, Tag, Typography } from "antd";
import { useState } from "react";
import type { MobileAppShellProps } from "./types";
import { MobileMetric } from "./MobileMetric";
import { KlinePanel } from "../KlinePanel";
import {
  claimGateAlertType,
  claimGateDescription,
  claimGateStatusLabel,
  displayBenchmarkLabel,
  displayWindowLabel,
  horizonLabel,
  manualReviewModelLabel,
  manualReviewStatusLabel,
  sanitizeDisplayText,
  validationStatusLabel,
} from "../../utils/labels";
import { directionColor, formatDate, formatNumber, formatPercent, formatSignedNumber, valueTone } from "../../utils/format";
import { directionLabels, factorLabels } from "../../utils/constants";

const { Text, Title, Paragraph } = Typography;
const { TextArea } = Input;

type StockPanel = "advice" | "evidence" | "risk" | "question";

export function MobileStockDetail(props: MobileAppShellProps) {
  const [panel, setPanel] = useState<StockPanel>("advice");
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

  return (
    <main className="mobile-page">
      <header className="mobile-page-head">
        <div>
          <Text className="mobile-kicker">单票分析</Text>
          <Title level={2}>{dashboard.stock.name}</Title>
          <Text>{dashboard.stock.symbol}</Text>
        </div>
        <Button shape="circle" icon={<ReloadOutlined />} onClick={() => void props.onRefresh()} />
      </header>

      <section className="mobile-hero-card mobile-stock-hero">
        <div className="mobile-focus-title">
          <div>
            <Text className="mobile-card-kicker">当前建议</Text>
            <Title level={3}>{dashboard.hero.direction_label}</Title>
          </div>
          <div className="mobile-focus-price">
            <strong>{formatNumber(dashboard.hero.latest_close)}</strong>
            <span className={`value-${valueTone(dashboard.hero.day_change_pct)}`}>
              {formatPercent(dashboard.hero.day_change_pct)}
            </span>
          </div>
        </div>
        <Space wrap className="mobile-chip-row">
          <Tag color={directionColor(recommendation.claim_gate.public_direction)}>{dashboard.hero.direction_label}</Tag>
          {recommendation.claim_gate.public_direction !== recommendation.direction ? (
            <Tag>{`原始 ${directionLabels[recommendation.direction] ?? recommendation.direction}`}</Tag>
          ) : null}
          <Tag>{recommendation.confidence_expression}</Tag>
          <Tag>{claimGateStatusLabel(recommendation.claim_gate.status)}</Tag>
        </Space>
        <p>{sanitizeDisplayText(recommendation.summary)}</p>
        <div className="mobile-metric-grid">
          <MobileMetric label="高点" value={formatNumber(dashboard.hero.high_price)} />
          <MobileMetric label="低点" value={formatNumber(dashboard.hero.low_price)} />
          <MobileMetric label="刷新" value={formatDate(dashboard.hero.last_updated)} />
        </div>
      </section>

      <section className="mobile-panel-card">
        <div className="mobile-section-head">
          <div>
            <Title level={4}>走势</Title>
            <Text>{displayWindowLabel(recommendation.historical_validation.window_definition)}</Text>
          </div>
          <Tag color={claimGateAlertType(recommendation.claim_gate.status)}>
            {claimGateStatusLabel(recommendation.claim_gate.status)}
          </Tag>
        </div>
        <KlinePanel
          title={`${dashboard.stock.name} · ${dashboard.stock.symbol} K 线`}
          points={dashboard.price_chart}
          lastUpdated={dashboard.hero.last_updated}
          stockName={dashboard.stock.name}
          isMobile
        />
      </section>

      <div className="mobile-segmented mobile-sticky-segmented">
        {([
          ["advice", "建议"],
          ["evidence", "证据"],
          ["risk", "风险"],
          ["question", "追问"],
        ] as Array<[StockPanel, string]>).map(([key, label]) => (
          <button key={key} type="button" className={panel === key ? "active" : ""} onClick={() => setPanel(key)}>
            {label}
          </button>
        ))}
      </div>

      {panel === "advice" ? (
        <section className="mobile-panel-card">
          <Alert
            className="mobile-inline-alert"
            type={claimGateAlertType(recommendation.claim_gate.status)}
            showIcon
            message={recommendation.claim_gate.headline}
            description={sanitizeDisplayText(claimGateDescription(recommendation.claim_gate))}
          />
          <div className="mobile-fact-list">
            <MobileMetric label="目标 horizon" value={horizonLabel(recommendation.core_quant.target_horizon_label)} />
            <MobileMetric label="验证状态" value={validationStatusLabel(recommendation.historical_validation.status)} />
            <MobileMetric label="基准" value={displayBenchmarkLabel(recommendation.historical_validation.benchmark_definition)} />
            <MobileMetric label="RankIC" value={formatSignedNumber(recommendation.historical_validation.metrics?.rank_ic_mean)} />
            <MobileMetric label="正超额占比" value={formatPercent(recommendation.historical_validation.metrics?.positive_excess_rate)} />
          </div>
          <Title level={5}>核心驱动</Title>
          <ul className="mobile-plain-list">
            {recommendation.evidence.primary_drivers.map((item) => <li key={item}>{sanitizeDisplayText(item)}</li>)}
          </ul>
        </section>
      ) : null}

      {panel === "evidence" ? (
        <section className="mobile-panel-card">
          <Title level={4}>因子与证据</Title>
          <div className="mobile-card-list">
            {recommendation.evidence.factor_cards.map((card) => (
              <article key={card.factor_key} className="mobile-mini-card">
                <div className="mobile-mini-head">
                  <strong>{factorLabels[card.factor_key] ?? card.factor_key}</strong>
                  {card.direction ? <Tag color={directionColor(card.direction)}>{directionLabels[card.direction] ?? card.direction}</Tag> : null}
                </div>
                <p>{sanitizeDisplayText(card.headline)}</p>
                {card.risk_note ? <Text>{sanitizeDisplayText(card.risk_note)}</Text> : null}
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {panel === "risk" ? (
        <section className="mobile-panel-card">
          <Title level={4}>失效条件</Title>
          <Paragraph>{sanitizeDisplayText(dashboard.risk_panel.headline)}</Paragraph>
          <ul className="mobile-plain-list">
            {[...recommendation.risk.risk_flags, ...recommendation.risk.downgrade_conditions].map((item) => (
              <li key={item}>{sanitizeDisplayText(item)}</li>
            ))}
          </ul>
          {recommendation.historical_validation.note ? (
            <Alert
              className="mobile-inline-alert"
              type="warning"
              showIcon
              message="验证说明"
              description={sanitizeDisplayText(recommendation.historical_validation.note)}
            />
          ) : null}
        </section>
      ) : null}

      {panel === "question" ? (
        <section className="mobile-panel-card">
          <div className="mobile-section-head">
            <div>
              <Title level={4}>追问与人工研究</Title>
              <Text>{manualReviewStatusLabel(recommendation.manual_llm_review.status)}</Text>
            </div>
            <QuestionCircleOutlined />
          </div>
          <Space wrap className="mobile-chip-row">
            {dashboard.follow_up.suggested_questions.map((question) => (
              <Button key={question} size="small" onClick={() => props.setQuestionDraft(question)}>
                {question}
              </Button>
            ))}
          </Space>
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
          <div className="mobile-fact-list">
            <MobileMetric label="模型标签" value={recommendation.manual_llm_review.model_label ? manualReviewModelLabel(recommendation.manual_llm_review.model_label) : "未指定"} />
            <MobileMetric label="产物时间" value={formatDate(recommendation.manual_llm_review.generated_at)} />
          </div>
          <p>{recommendation.manual_llm_review.summary ? sanitizeDisplayText(recommendation.manual_llm_review.summary) : "当前没有额外的人工研究摘要。"}</p>
        </section>
      ) : null}
    </main>
  );
}
