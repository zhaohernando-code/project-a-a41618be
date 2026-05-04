import {
  Alert, Button, Card, Col, Collapse, Descriptions, Empty,
  Form, InputNumber, List, Modal, Row, Select, Skeleton, Space,
  Switch, Table, Tag, Tabs, Timeline, Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import {
  BarChartOutlined, ReloadOutlined, ThunderboltOutlined,
} from "@ant-design/icons";
import type {
  CandidateWorkspaceRow,
  ImprovementSuggestionView,
  OperationsDashboardResponse,
  RecommendationReplayView,
  SimulationConfigRequest,
  SimulationWorkspaceResponse,
} from "../types";
import {
  compactValidationNote,
  formatMarketFreshness,
  launchReadinessDescription,
  canCompleteManualResearch,
  canExecuteManualResearch,
  canFailManualResearch,
  canRetryManualResearch,
  manualResearchActionStatusMessage,
  manualReviewStatusLabel,
  operationsValidationDescription,
  operationsValidationMessage,
  sanitizeDisplayText,
  validationStatusLabel,
} from "../utils/labels";
import {
  directionColor,
  formatDate,
  formatNumber,
  formatPercent,
  formatSignedNumber,
  simulationAdviceActionLabel,
  simulationAdvicePolicyLabel,
  statusColor,
  valueTone,
} from "../utils/format";
import { PortfolioWorkspace } from "./PortfolioWorkspace";
import { KlinePanel } from "./KlinePanel";
import { CompactAnalysisReport } from "./CompactAnalysisReport";

const { Paragraph, Text, Title } = Typography;
type ModalApi = { confirm: typeof Modal.confirm };
const IMPROVEMENT_TASK_MODEL_OPTIONS = [
  { label: "GPT-5.5 高级审计 / 仲裁", value: "gpt-5.5" },
  { label: "GPT-5.4", value: "gpt-5.4" },
  { label: "GPT-5.3 Codex Spark", value: "gpt-5.3-codex-spark" },
  { label: "DeepSeek V4 Pro", value: "deepseek-v4-pro[1m]" },
  { label: "DeepSeek V4 Flash", value: "deepseek-v4-flash" },
];

export interface BuildOperationsTabsInput {
  operations: OperationsDashboardResponse | null;
  simulation: SimulationWorkspaceResponse | null;
  simulationConfigDraft: SimulationConfigRequest | null;
  setSimulationConfigDraft: (v: SimulationConfigRequest | null | ((prev: SimulationConfigRequest | null) => SimulationConfigRequest | null)) => void;
  candidateRows: CandidateWorkspaceRow[];
  symbolNameMap: Map<string, string>;
  replayColumns: ColumnsType<RecommendationReplayView>;
  portfolioTabs: { key: string; label: string; children: React.ReactNode }[];
  handleCandidateSelect: (symbol: string, nextView?: any) => void;
  handleSaveSimulationConfig: () => Promise<void>;
  handleExecuteManualResearch: (request: any) => Promise<void>;
  handleRetryManualResearch: (request: any) => Promise<void>;
  openCompleteManualResearchModal: (item: any) => void;
  openFailManualResearchModal: (item: any) => void;
  messageApi: { warning: (msg: string) => void; success: (msg: string) => void; error: (msg: string) => void };
  modalApi: ModalApi;
  simulationAction: string | null;
  setSimulationAction: (v: string | null) => void;
  operationsFocusSymbol: string | null;
  setOperationsFocusSymbol: (v: string | null) => void;
  loadingDetail: boolean;
  setLoadingDetail: (v: boolean) => void;
  setSelectedSymbol: (v: string | null) => void;
  setStockActiveTab: (v: string) => void;
  setView: (v: any) => void;
  setOperations: (v: OperationsDashboardResponse | null) => void;
  setOperationsLoading: (v: boolean) => void;
  setOperationsError: (v: string | null) => void;
  manualResearchAction: string | null;
  setManualResearchAction: (v: string | null) => void;
  handleRunImprovementSuggestionReview: () => Promise<void>;
  improvementSuggestionReviewNotice: {
    status: "idle" | "running" | "success" | "error";
    message: string;
    description?: string;
  };
  handleAcceptImprovementSuggestionForPlan: (suggestionId: string, model: string) => Promise<void>;
  handleUpdateImprovementSuggestionStatus: (suggestionId: string, status: string, reason: string) => Promise<void>;
  improvementSuggestionFilter: string | null;
  setImprovementSuggestionFilter: (v: string | null) => void;
  loadingSections: Set<string>;
}

function suggestionConfidenceLabel(value?: string | null): string {
  if (value === "high") return "高置信";
  if (value === "moderate") return "中置信";
  if (value === "low") return "低置信";
  if (value === "reject") return "拒绝";
  return value || "未审计";
}

function suggestionActionLabel(value?: string | null): string {
  if (value === "ignore") return "忽略";
  if (value === "monitor") return "继续观察";
  if (value === "create_plan") return "生成计划";
  if (value === "create_experiment") return "进入实验";
  return value || "未给出";
}

function improvementSuggestionStatusLabel(value?: string | null): string {
  if (value === "accepted_for_plan") return "计划执行中";
  if (value === "completed") return "已完成";
  if (value === "monitoring") return "观察中";
  if (value === "rejected") return "已拒绝";
  if (value === "reviewed") return "已审计";
  return value || "未处理";
}

function reviewerSummary(item: ImprovementSuggestionView, reviewer: string): string {
  const review = item.reviews?.[reviewer];
  if (!review) return "未返回审计";
  return `${review.stance} · ${formatPercent(review.confidence)} · ${sanitizeDisplayText(review.main_reason)}`;
}

function improvementSuggestionFilterLabel(value?: string | null): string {
  if (value === "completed") return "已完成";
  if (value === "reviewed") return "已审计";
  if (value === "high_confidence") return "高置信";
  if (value === "moderate_confidence") return "中置信";
  if (value === "low_confidence") return "低置信";
  if (value === "reject") return "拒绝";
  if (value === "model_split") return "模型分歧";
  if (value === "needs_more_data") return "缺证据";
  return "本周建议";
}
function filterImprovementSuggestions(items: ImprovementSuggestionView[], filter: string | null): ImprovementSuggestionView[] {
  if (!filter) return items.filter((item) => item.status !== "completed");
  if (filter === "completed") return items.filter((item) => item.status === "completed");
  if (filter === "reviewed") return items.filter((item) => item.status === "reviewed" || Boolean(item.reviews));
  if (filter === "high_confidence") return items.filter((item) => item.final_confidence === "high");
  if (filter === "moderate_confidence") return items.filter((item) => item.final_confidence === "moderate");
  if (filter === "low_confidence") return items.filter((item) => item.final_confidence === "low");
  if (filter === "reject") return items.filter((item) => item.final_confidence === "reject");
  if (filter === "model_split") return items.filter((item) => item.model_consensus === "split");
  if (filter === "needs_more_data") return items.filter((item) => item.evidence_status === "needs_more_data");
  return items;
}

function openImprovementPlanModelPicker(
  item: ImprovementSuggestionView,
  handleAcceptImprovementSuggestionForPlan: (suggestionId: string, model: string) => Promise<void>,
  modalApi: ModalApi,
) {
  let selectedModel = "gpt-5.4";
  modalApi.confirm({
    title: "选择执行模型",
    okText: "进入计划池并创建中台任务",
    cancelText: "取消",
    width: 560,
    content: (
      <div className="modal-form-stack">
        <Text type="secondary">
          中台任务会启用 Plan 模式。模型会先生成计划和待确认项，确认后才开始执行。
        </Text>
        <Select
          className="full-width-control"
          defaultValue={selectedModel}
          options={IMPROVEMENT_TASK_MODEL_OPTIONS}
          onChange={(value) => {
            selectedModel = value;
          }}
        />
        <Text type="secondary">{sanitizeDisplayText(item.claim)}</Text>
      </div>
    ),
    onOk: () => handleAcceptImprovementSuggestionForPlan(item.suggestion_id, selectedModel),
  });
}
export function buildOperationsTabs(input: BuildOperationsTabsInput) {
  const {
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
    messageApi, modalApi,
    simulationAction, setSimulationAction,
    operationsFocusSymbol, setOperationsFocusSymbol,
    loadingDetail, setLoadingDetail,
    setSelectedSymbol, setStockActiveTab, setView,
    setOperations, setOperationsLoading, setOperationsError,
    manualResearchAction, setManualResearchAction,
    handleRunImprovementSuggestionReview, improvementSuggestionReviewNotice, handleAcceptImprovementSuggestionForPlan, handleUpdateImprovementSuggestionStatus,
    improvementSuggestionFilter, setImprovementSuggestionFilter,
    loadingSections,
  } = input;
  if (!operations) return [];
  const improvementSuggestions = operations.improvement_suggestions;
  const improvementSuggestionReviewRunning = improvementSuggestionReviewNotice.status === "running";
  const improvementSuggestionReviewAlertType = improvementSuggestionReviewNotice.status === "error"
    ? "error"
    : improvementSuggestionReviewNotice.status === "success"
      ? "success"
      : "info";
  const improvementSuggestionItems = improvementSuggestions?.suggestions ?? improvementSuggestions?.top_suggestions ?? [];
  const filteredImprovementSuggestions = filterImprovementSuggestions(improvementSuggestionItems, improvementSuggestionFilter);
  const improvementSuggestionStatFilters = improvementSuggestions ? [
    { key: null, label: "本周建议", value: improvementSuggestions.summary.total ?? 0 },
    { key: "completed", label: "已完成", value: improvementSuggestions.summary.by_status?.completed ?? 0 },
    { key: "reviewed", label: "已审计", value: improvementSuggestions.summary.reviewed ?? 0 },
    { key: "high_confidence", label: "高置信", value: improvementSuggestions.summary.high_confidence ?? 0 },
    { key: "moderate_confidence", label: "中置信", value: improvementSuggestions.summary.moderate_confidence ?? 0 },
    { key: "low_confidence", label: "低置信", value: improvementSuggestions.summary.low_confidence ?? 0 },
    { key: "reject", label: "拒绝", value: improvementSuggestions.summary.reject ?? 0 },
    { key: "model_split", label: "模型分歧", value: improvementSuggestions.summary.model_split ?? 0 },
    { key: "needs_more_data", label: "缺证据", value: improvementSuggestions.summary.needs_more_data ?? 0 },
  ] : [];
  return [
    {
      key: "execution",
      label: "模拟参数",
      children: loadingSections.has("simulation_workspace") && !simulation ? (<Row gutter={[16, 16]}>
        <Col xs={24} xl={10}><Card className="panel-card" title="模型轨道建议"><Skeleton active paragraph={{ rows: 4 }}/></Card></Col>
        <Col xs={24} xl={14}><Card className="panel-card" title="模拟参数"><Skeleton.Input active style={{ width: 200, marginBottom: 16 }}/><Skeleton active paragraph={{ rows: 6 }}/></Card></Col>
      </Row>) : (<Row gutter={[16, 16]}>
          <Col xs={24} xl={10}>
            <Card className="panel-card" title="模型轨道建议">
              <List
                dataSource={simulation?.model_advices ?? []}
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
                      {item.policy_note ? (
                        <Alert
                          type={item.policy_type === "manual_review_preview_policy_v1" ? "warning" : "info"}
                          showIcon
                          message={simulationAdvicePolicyLabel(item)}
                          description={sanitizeDisplayText(item.policy_note)}
                        />
                      ) : null}
                      <div className="watchlist-meta">
                        <Text type="secondary">
                          {item.policy_type === "manual_review_preview_policy_v1"
                            ? `人工复核预览 ${simulationAdviceActionLabel(item)} · 参考价 ${formatNumber(item.reference_price)}`
                            : `${simulationAdviceActionLabel(item)} · 参考价 ${formatNumber(item.reference_price)}${item.quantity ? ` · 数量 ${formatNumber(item.quantity)}` : ""}${item.target_weight !== null && item.target_weight !== undefined ? ` · 目标仓位 ${formatPercent(item.target_weight)}` : ""}`}
                        </Text>
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
            <Card className="panel-card" title="模拟参数">
              <Form layout="vertical">
                <Row gutter={[16, 0]}>
                  <Col xs={24} md={12}>
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
                  </Col>
                  <Col xs={24} md={12}>
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
                  </Col>
                </Row>
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
                <Row gutter={[16, 0]}>
                  <Col xs={24} md={12}>
                    <Form.Item label="焦点标的">
                      <Select
                        value={simulationConfigDraft?.focus_symbol ?? undefined}
                        options={(simulationConfigDraft?.watch_symbols ?? simulation?.session.watch_symbols ?? []).map((symbol) => ({
                          value: symbol,
                          label: `${symbolNameMap.get(symbol) ?? symbol} · ${symbol}`,
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
                  </Col>
                  <Col xs={24} md={12}>
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
                  </Col>
                </Row>
              </Form>
              {simulation?.configuration.auto_execute_note ? (
                <Alert
                  className="sub-alert"
                  type={simulation.configuration.auto_execute_model ? "success" : "info"}
                  showIcon
                  message={simulation.configuration.auto_execute_model ? "模型轨道自动执行已启用" : "模型轨道自动执行说明"}
                  description={sanitizeDisplayText(simulation.configuration.auto_execute_note)}
                />
              ) : null}
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
        </Row>
      ),
    },
    {
      key: "analysis",
      label: "差异复盘",
      children: (
        <div className="panel-stack">
          <Card
            className="panel-card"
            title="改进建议审计台"
            extra={(
              <Button
                size="small"
                icon={<ReloadOutlined />}
                loading={improvementSuggestionReviewRunning}
                disabled={improvementSuggestionReviewRunning}
                onClick={() => void handleRunImprovementSuggestionReview()}
              >
                重新审计
              </Button>
            )}
          >
            {improvementSuggestionReviewNotice.status !== "idle" ? (
              <Alert
                showIcon
                type={improvementSuggestionReviewAlertType}
                message={improvementSuggestionReviewNotice.message}
                description={improvementSuggestionReviewNotice.description}
              />
            ) : null}
            {loadingSections.has("improvement_suggestions") && !operations.improvement_suggestions ? <Skeleton active paragraph={{ rows: 4 }}/> : operations.improvement_suggestions ? (
              <>
                <div className="suggestion-stat-grid">
                  {improvementSuggestionStatFilters.map((item) => (
                    <button
                      key={item.key ?? "all"}
                      type="button"
                      className={`suggestion-stat-button ${improvementSuggestionFilter === item.key ? "active" : ""}`}
                      onClick={() => setImprovementSuggestionFilter(item.key)}
                    >
                      <span>{item.label}</span>
                      <strong>{formatNumber(item.value)}</strong>
                    </button>
                  ))}
                </div>
                <Space wrap className="inline-tags">
                  <Tag color={statusColor(operations.improvement_suggestions.status ?? "pending")}>
                    {operations.improvement_suggestions.status ?? "pending"}
                  </Tag>
                  <Tag>{`GPT ${operations.improvement_suggestions.model_status?.gpt ?? "unknown"}`}</Tag>
                  <Tag>{`DeepSeek ${operations.improvement_suggestions.model_status?.deepseek ?? "unknown"}`}</Tag>
                  <Tag>{`窗口 ${operations.improvement_suggestions.window_days ?? 7} 天`}</Tag>
                  {improvementSuggestionFilter ? (
                    <>
                      <Tag color="blue">{`当前筛选：${improvementSuggestionFilterLabel(improvementSuggestionFilter)}`}</Tag>
                      <Button size="small" type="link" onClick={() => setImprovementSuggestionFilter(null)}>
                        清除筛选
                      </Button>
                    </>
                  ) : null}
                </Space>
                <List
                  dataSource={filteredImprovementSuggestions}
                  locale={{ emptyText: "暂无可审计建议" }}
                  renderItem={(item) => {
                    const isCompleted = item.status === "completed";
                    const actions = isCompleted ? [] : [
                      <Button
                        key="plan"
                        type="link"
                        disabled={item.status === "accepted_for_plan"}
                        onClick={() => openImprovementPlanModelPicker(item, handleAcceptImprovementSuggestionForPlan, modalApi)}
                      >
                        进入计划池
                      </Button>,
                      item.status === "accepted_for_plan" ? (
                        <Button
                          key="complete"
                          type="link"
                          onClick={() => void handleUpdateImprovementSuggestionStatus(item.suggestion_id, "completed", "计划已执行完毕")}
                        >
                          标记完成
                        </Button>
                      ) : null,
                      <Button
                        key="monitor"
                        type="link"
                        disabled={item.status === "monitoring"}
                        onClick={() => void handleUpdateImprovementSuggestionStatus(item.suggestion_id, "monitoring", "标记观察")}
                      >
                        标记观察
                      </Button>,
                      <Button
                        key="reject"
                        type="link"
                        danger
                        disabled={item.status === "rejected"}
                        onClick={() => void handleUpdateImprovementSuggestionStatus(item.suggestion_id, "rejected", "当前不采纳")}
                      >
                        拒绝
                      </Button>,
                    ].filter(Boolean);
                    return (
                    <List.Item
                      className={isCompleted ? "suggestion-list-item-completed" : undefined}
                      actions={actions}
                    >
                      <div className={`watchlist-entry suggestion-entry ${isCompleted ? "suggestion-entry-completed" : ""}`}>
                        <div className="list-item-row">
                          <div>
                            <strong>{sanitizeDisplayText(item.claim)}</strong>
                            <div className="muted-line">{`${item.source_type} · ${item.symbol ?? "全局"} · ${formatDate(item.created_at)}`}</div>
                          </div>
                          <Space wrap>
                            <Tag>{item.category}</Tag>
                            <Tag color={statusColor(item.status ?? "pending")}>
                              {improvementSuggestionStatusLabel(item.status)}
                            </Tag>
                            <Tag color={statusColor(item.final_confidence ?? "pending")}>
                              {suggestionConfidenceLabel(item.final_confidence)}
                            </Tag>
                            <Tag>{suggestionActionLabel(item.recommended_action)}</Tag>
                          </Space>
                        </div>
                        <Paragraph className="panel-description">{sanitizeDisplayText(item.proposed_change)}</Paragraph>
                        {item.control_plane_task?.id ? (
                          <Space wrap className="inline-tags">
                            <Tag color="blue">{`中台任务 ${item.control_plane_task.id}`}</Tag>
                            <Tag color={statusColor(item.control_plane_task.status ?? "pending")}>
                              {`任务状态 ${item.control_plane_task.status ?? "unknown"}`}
                            </Tag>
                            {item.control_plane_task.status_stale ? <Tag color="gold">任务状态未实时同步</Tag> : null}
                            {item.control_plane_task.publish_verified ? <Tag color="green">发布已验证</Tag> : null}
                            <Tag>{`模型 ${item.control_plane_task.model}`}</Tag>
                            <Tag>{item.control_plane_task.plan_mode ? "Plan 模式" : "直接执行"}</Tag>
                          </Space>
                        ) : null}
                        <Collapse
                          className="compact-collapse"
                          items={[
                            {
                              key: "reviews",
                              label: "双模型审计与分歧",
                              children: (
                                <Descriptions size="small" column={1}>
                                  <Descriptions.Item label="GPT">{reviewerSummary(item, "gpt")}</Descriptions.Item>
                                  <Descriptions.Item label="DeepSeek">{reviewerSummary(item, "deepseek")}</Descriptions.Item>
                                  <Descriptions.Item label="最终判断">{sanitizeDisplayText(item.decision_reason)}</Descriptions.Item>
                                  <Descriptions.Item label="证据状态">{item.evidence_status ?? "未给出"}</Descriptions.Item>
                                </Descriptions>
                              ),
                            },
                            {
                              key: "plan",
                              label: "生成的开发计划",
                              children: item.generated_plan ? (
                                <div>
                                  <Paragraph className="panel-description">{sanitizeDisplayText(item.generated_plan.summary)}</Paragraph>
                                  <Title level={5}>实施步骤</Title>
                                  <ul className="plain-list">
                                    {item.generated_plan.implementation_steps.map((step) => (
                                      <li key={`${item.suggestion_id}-${step}`}>{sanitizeDisplayText(step)}</li>
                                    ))}
                                  </ul>
                                  <Title level={5}>测试</Title>
                                  <ul className="plain-list">
                                    {item.generated_plan.tests.map((test) => (
                                      <li key={`${item.suggestion_id}-${test}`}>{sanitizeDisplayText(test)}</li>
                                    ))}
                                  </ul>
                                </div>
                              ) : (
                                <Text type="secondary">暂无计划。</Text>
                              ),
                            },
                          ]}
                        />
                      </div>
                    </List.Item>
                    );
                  }}
                />
              </>
            ) : (
              <Empty description="暂无可审计建议" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
          <Row gutter={[16, 16]}>
            <Col xs={24} xl={14}>
              <Card className="panel-card" title="双轨核心差异">
                <Table
                  rowKey="label"
                  size="small"
                  pagination={false}
                  dataSource={simulation?.comparison_metrics ?? []}
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
            <Col xs={24} xl={10}>
              <Card className="panel-card" title="时点决策差异">
                <List
                  dataSource={simulation?.decision_differences ?? []}
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
          </Row>
          <Card className="panel-card" title="共享时间线留痕">
            <Descriptions size="small" column={{ xs: 1, md: 2, xl: 4 }}>
              <Descriptions.Item label="启动时间">{formatDate(simulation?.session.started_at)}</Descriptions.Item>
              <Descriptions.Item label="最近恢复">{formatDate(simulation?.session.last_resumed_at)}</Descriptions.Item>
              <Descriptions.Item label="最近暂停">{formatDate(simulation?.session.paused_at)}</Descriptions.Item>
              <Descriptions.Item label="结束时间">{formatDate(simulation?.session.ended_at)}</Descriptions.Item>
            </Descriptions>
            <Timeline
              items={(simulation?.timeline ?? []).map((item) => ({
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
        </div>
      ),
    },
    {
      key: "governance",
      label: "治理与验收",
      children: (
        <div className="panel-stack">
          <Row gutter={[16, 16]}>
            <Col xs={24} xl={16}>
              <Card
                className="panel-card"
                title="组合复盘与建议命中"
                extra={<Text type="secondary">{`生成时间 ${formatDate(operations.overview.generated_at)}`}</Text>}
              >
                <Descriptions size="small" column={{ xs: 1, md: 2 }}>
                  <Descriptions.Item label="用户轨道">{operations.overview.manual_portfolio_count}</Descriptions.Item>
                  <Descriptions.Item label="模型轨道">{operations.overview.auto_portfolio_count}</Descriptions.Item>
                  <Descriptions.Item label="上线状态">
                    <Tag color={statusColor(operations.overview.launch_readiness.status)}>
                      {operations.overview.launch_readiness.status}
                    </Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="研究验证">
                    {validationStatusLabel(operations.overview.research_validation.status)}
                  </Descriptions.Item>
                  <Descriptions.Item label="运行健康">
                    <Tag color={statusColor(operations.overview.run_health.status)}>
                      {operations.overview.run_health.status}
                    </Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="刷新冷却">
                    {`${operations.overview.run_health.refresh_cooldown_minutes} 分钟`}
                  </Descriptions.Item>
                </Descriptions>
                <Paragraph className="panel-description">
                  用户轨道看手动下单结果，模型轨道看模拟盘里的自动调仓结果。这里只保留结果、验证状态和门禁，不重复展开策略长说明。
                </Paragraph>
                {operations.overview.run_health.note && operations.overview.run_health.status !== "pass" ? (
                  <Alert
                    className="sub-alert"
                    type="warning"
                    showIcon
                    message="运行健康"
                    description={sanitizeDisplayText(operations.overview.run_health.note)}
                  />
                ) : null}
                {loadingSections.has("portfolios") && portfolioTabs.length === 0 ? <Skeleton active paragraph={{ rows: 3 }}/> : portfolioTabs.length > 0 ? (
                  <Tabs items={portfolioTabs} />
                ) : (
                  <Empty description="当前没有可展示的组合轨道" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                )}
              </Card>
            </Col>
            <Col xs={24} xl={8}>
              <Card className="panel-card" title="研究与运行摘要">
                <Descriptions size="small" column={1}>
                  <Descriptions.Item label="行情状态">
                    {sanitizeDisplayText(operations.overview.run_health.intraday_source_status)}
                  </Descriptions.Item>
                  <Descriptions.Item label="行情时间框架">
                    {sanitizeDisplayText(operations.overview.run_health.market_data_timeframe)}
                  </Descriptions.Item>
                  <Descriptions.Item label="最新行情">
                    {formatMarketFreshness(
                      operations.data_latency_seconds,
                      operations.overview.run_health.last_market_data_at,
                    )}
                  </Descriptions.Item>
                  <Descriptions.Item label="研究验证状态">
                    {validationStatusLabel(operations.overview.research_validation.status)}
                  </Descriptions.Item>
                  <Descriptions.Item label="复盘样本数">
                    {operations.overview.research_validation.replay_sample_count}
                  </Descriptions.Item>
                  <Descriptions.Item label="已验证复盘">
                    {operations.overview.research_validation.verified_replay_count}
                  </Descriptions.Item>
                  <Descriptions.Item label="组合轨道">
                    {operations.overview.manual_portfolio_count + operations.overview.auto_portfolio_count}
                  </Descriptions.Item>
                  <Descriptions.Item label="阻塞门禁">
                    {operations.overview.launch_readiness.blocking_gate_count}
                  </Descriptions.Item>
                  <Descriptions.Item label="警告门禁">
                    {operations.overview.launch_readiness.warning_gate_count}
                  </Descriptions.Item>
                  <Descriptions.Item label="数据质量">
                    <Tag color={statusColor(operations.data_quality_summary?.status ?? "pending")}>
                      {operations.data_quality_summary?.status ?? "pending"}
                    </Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="异常股票">
                    {operations.today_at_a_glance?.abnormal_symbol_count ?? 0}
                  </Descriptions.Item>
                  <Descriptions.Item label="关注池进度">
                    {`${operations.today_at_a_glance?.active_watchlist_count ?? 0}/${operations.today_at_a_glance?.target_watchlist_count ?? 0}`}
                  </Descriptions.Item>
                  <Descriptions.Item label="主基准">
                    {operations.benchmark_context?.primary_label ?? operations.benchmark_context?.primary_benchmark ?? "沪深300"}
                  </Descriptions.Item>
                </Descriptions>
                {operations.today_at_a_glance?.top_warning_gate ? (
                  <Alert
                    className="sub-alert"
                    type="warning"
                    showIcon
                    message="今日重点"
                    description={sanitizeDisplayText(operations.today_at_a_glance.top_warning_gate)}
                  />
                ) : null}
              </Card>
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
              <Card
                className="panel-card"
                title="人工研究队列"
                extra={loadingSections.has("manual_queue") && !operations.manual_research_queue?.generated_at ? null : <Text type="secondary">{`快照时间 ${formatDate(operations.manual_research_queue.generated_at)}`}</Text>}
              >
                {loadingSections.has("manual_queue") && !operations.manual_research_queue?.generated_at ? <Skeleton active paragraph={{ rows: 4 }}/> : <Space wrap className="inline-tags">
                  <Tag>{`排队 ${operations.manual_research_queue.counts.queued ?? 0}`}</Tag>
                  <Tag>{`执行中 ${operations.manual_research_queue.counts.in_progress ?? 0}`}</Tag>
                  <Tag>{`失败 ${operations.manual_research_queue.counts.failed ?? 0}`}</Tag>
                  <Tag>{`当前完成 ${operations.manual_research_queue.counts.completed_current ?? 0}`}</Tag>
                  <Tag>{`过期 ${operations.manual_research_queue.counts.completed_stale ?? 0}`}</Tag>
                </Space>}
                <List
                  dataSource={operations.manual_research_queue.recent_items}
                  locale={{ emptyText: "当前关注池还没有人工研究请求" }}
                  renderItem={(item) => (
                    <List.Item
                      actions={[
                        <Button key="open" type="link" onClick={() => handleCandidateSelect(item.symbol, "stock")}>
                          打开
                        </Button>,
                        <Button
                          key="execute"
                          type="link"
                          disabled={!canExecuteManualResearch(item)}
                          loading={manualResearchAction === `execute:${item.id}`}
                          onClick={() => void handleExecuteManualResearch(item)}
                        >
                          执行
                        </Button>,
                        <Button
                          key="complete"
                          type="link"
                          disabled={!canCompleteManualResearch(item)}
                          loading={manualResearchAction === `complete:${item.id}`}
                          onClick={() => openCompleteManualResearchModal(item)}
                        >
                          完成
                        </Button>,
                        <Button
                          key="fail"
                          type="link"
                          danger
                          disabled={!canFailManualResearch(item)}
                          loading={manualResearchAction === `fail:${item.id}`}
                          onClick={() => openFailManualResearchModal(item)}
                        >
                          失败
                        </Button>,
                        <Button
                          key="retry"
                          type="link"
                          disabled={!canRetryManualResearch(item)}
                          loading={manualResearchAction === `retry:${item.id}`}
                          onClick={() => void handleRetryManualResearch(item)}
                        >
                          Retry
                        </Button>,
                      ]}
                    >
                      <div className="watchlist-entry">
                        <div className="list-item-row">
                          <div>
                            <strong>{item.symbol}</strong>
                            <div className="muted-line">{formatDate(item.requested_at)}</div>
                          </div>
                          <Tag color={statusColor(item.status)}>{manualReviewStatusLabel(item.status)}</Tag>
                        </div>
                        <Paragraph className="panel-description">{sanitizeDisplayText(item.question)}</Paragraph>
                        <Text type="secondary">
                          {item.status_note
                            ? sanitizeDisplayText(item.status_note)
                            : item.failure_reason
                              ? sanitizeDisplayText(item.failure_reason)
                              : item.stale_reason
                                ? sanitizeDisplayText(item.stale_reason)
                                : "等待处理。"}
                        </Text>
                      </div>
                    </List.Item>
                  )}
                />
              </Card>
            </Col>
            <Col xs={24} xl={10}>
              <Card
                className="panel-card"
                title="焦点标的研究工作区"
                extra={operations.manual_research_queue.focus_symbol ? <Tag>{operations.manual_research_queue.focus_symbol}</Tag> : null}
              >
                {operations.manual_research_queue.focus_request ? (
                  <>
                    <Descriptions size="small" column={1}>
                      <Descriptions.Item label="状态">
                        {manualReviewStatusLabel(operations.manual_research_queue.focus_request.status)}
                      </Descriptions.Item>
                      <Descriptions.Item label="研究问题">
                        {sanitizeDisplayText(operations.manual_research_queue.focus_request.question)}
                      </Descriptions.Item>
                      <Descriptions.Item label="研究结论">
                        {operations.manual_research_queue.focus_request.manual_llm_review.review_verdict
                          ? sanitizeDisplayText(operations.manual_research_queue.focus_request.manual_llm_review.review_verdict)
                          : "未给出"}
                      </Descriptions.Item>
                    </Descriptions>
                    {operations.manual_research_queue.focus_request.status_note ? (
                      <Alert
                        className="sub-alert"
                        type="info"
                        showIcon
                        message="状态说明"
                        description={sanitizeDisplayText(operations.manual_research_queue.focus_request.status_note)}
                      />
                    ) : null}
                    {operations.manual_research_queue.focus_request.failure_reason
                    && operations.manual_research_queue.focus_request.failure_reason !== operations.manual_research_queue.focus_request.status_note ? (
                      <Alert
                        className="sub-alert"
                        type="error"
                        showIcon
                        message="失败原因"
                        description={sanitizeDisplayText(operations.manual_research_queue.focus_request.failure_reason)}
                      />
                    ) : null}
                    {operations.manual_research_queue.focus_request.stale_reason ? (
                      <Alert
                        className="sub-alert"
                        type="warning"
                        showIcon
                        message="结果过期"
                        description={sanitizeDisplayText(operations.manual_research_queue.focus_request.stale_reason)}
                      />
                    ) : null}
                    {operations.manual_research_queue.focus_request.manual_llm_review.summary ? (
                      <Paragraph className="panel-description">
                        {sanitizeDisplayText(operations.manual_research_queue.focus_request.manual_llm_review.summary)}
                      </Paragraph>
                    ) : null}
                    {operations.manual_research_queue.focus_request.source_packet.length > 0 ? (
                      <Alert
                        className="sub-alert"
                        type="info"
                        showIcon
                        message="研究材料"
                        description="该焦点标的已关联研究材料与验证记录，详情保留在内部台账中。"
                      />
                    ) : null}
                    <div className="deck-actions">
                      <Button onClick={() => handleCandidateSelect(operations.manual_research_queue.focus_request!.symbol, "stock")}>
                        打开单票页
                      </Button>
                      <Button
                        loading={manualResearchAction === `execute:${operations.manual_research_queue.focus_request.id}`}
                        disabled={!canExecuteManualResearch(operations.manual_research_queue.focus_request)}
                        onClick={() => void handleExecuteManualResearch(operations.manual_research_queue.focus_request!)}
                      >
                        执行请求
                      </Button>
                      <Button
                        loading={manualResearchAction === `complete:${operations.manual_research_queue.focus_request.id}`}
                        disabled={!canCompleteManualResearch(operations.manual_research_queue.focus_request)}
                        onClick={() => openCompleteManualResearchModal(operations.manual_research_queue.focus_request!)}
                      >
                        人工完成
                      </Button>
                      <Button
                        danger
                        loading={manualResearchAction === `fail:${operations.manual_research_queue.focus_request.id}`}
                        disabled={!canFailManualResearch(operations.manual_research_queue.focus_request)}
                        onClick={() => openFailManualResearchModal(operations.manual_research_queue.focus_request!)}
                      >
                        标记失败
                      </Button>
                      <Button
                        loading={manualResearchAction === `retry:${operations.manual_research_queue.focus_request.id}`}
                        disabled={!canRetryManualResearch(operations.manual_research_queue.focus_request)}
                        onClick={() => void handleRetryManualResearch(operations.manual_research_queue.focus_request!)}
                      >
                        Retry
                      </Button>
                    </div>
                  </>
                ) : (
                  <Empty description="当前焦点标的还没有人工研究请求" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                )}
              </Card>
            </Col>
          </Row>
          <Row gutter={[16, 16]}>
            <Col xs={24} xl={14}>
              <Card className="panel-card" title="建议命中复盘">
                {loadingSections.has("replay") && !operations.recommendation_replay?.length ? <Skeleton active paragraph={{ rows: 3 }}/> : (<Table
                  rowKey="recommendation_id"
                  size="small"
                  pagination={false}
                  dataSource={operations.recommendation_replay}
                  columns={replayColumns}
                />
                )}
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
        </div>
      ),
    },
  ];
}
