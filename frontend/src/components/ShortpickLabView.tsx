import {
  Alert,
  Button,
  Card,
  Collapse,
  Descriptions,
  Empty,
  List,
  Progress,
  Row,
  Col,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { ExperimentOutlined, ReloadOutlined, SafetyCertificateOutlined, SyncOutlined } from "@ant-design/icons";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { ShortpickCandidateView, ShortpickRunView, ShortpickRoundView, ShortpickValidationView } from "../types";
import { formatDate, formatPercent, valueTone } from "../utils/format";

const { Paragraph, Text, Title } = Typography;

function priorityLabel(value: string): string {
  if (value === "high_convergence") return "高收敛";
  if (value === "theme_convergence") return "题材收敛";
  if (value === "divergent_novel") return "发散新颖";
  if (value === "watch_only") return "观察";
  return "待聚合";
}

function priorityColor(value: string): string {
  if (value === "high_convergence") return "red";
  if (value === "theme_convergence") return "gold";
  if (value === "divergent_novel") return "blue";
  if (value === "watch_only") return "default";
  return "default";
}

function statusColor(value: string): string {
  if (value === "completed") return "green";
  if (value === "running") return "blue";
  if (value === "failed" || value === "parse_failed") return "red";
  if (value.startsWith("pending")) return "gold";
  return "default";
}

function statusLabel(value: string): string {
  const labels: Record<string, string> = {
    completed: "已完成",
    running: "运行中",
    failed: "失败",
    parsed: "已解析",
    parse_failed: "解析失败",
    pending_market_data: "待行情",
    pending_forward_window: "待窗口",
    pending_entry_bar: "待入场价",
  };
  return labels[value] ?? value;
}

function roundModelLabel(round: ShortpickRoundView): string {
  return `${round.provider_name}:${round.model_name} #${round.round_index}`;
}

function validationSummary(candidate: ShortpickCandidateView): string {
  const completed = candidate.validations.filter((item) => item.status === "completed");
  if (!completed.length) {
    return "待验证";
  }
  const shortest = completed[0];
  return `${shortest.horizon_days}日 ${formatPercent(shortest.stock_return)}`;
}

function sourceCredibilityLabel(value?: string | null): string {
  if (value === "verified") return "来源可达";
  if (value === "reachable_restricted") return "来源受限";
  if (value === "suspicious") return "疑似占位";
  if (value === "unreachable") return "不可达";
  if (value === "missing_url") return "缺 URL";
  return "未校验";
}

function sourceCredibilityColor(value?: string | null): string {
  if (value === "verified") return "green";
  if (value === "reachable_restricted") return "gold";
  if (value === "suspicious" || value === "unreachable" || value === "missing_url") return "red";
  return "default";
}

export function ShortpickLabView({ canTrigger }: { canTrigger: boolean }) {
  const [runs, setRuns] = useState<ShortpickRunView[]>([]);
  const [selectedRun, setSelectedRun] = useState<ShortpickRunView | null>(null);
  const [candidates, setCandidates] = useState<ShortpickCandidateView[]>([]);
  const [loading, setLoading] = useState(false);
  const [action, setAction] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const latestRun = selectedRun ?? runs[0] ?? null;
  const latestCandidates = useMemo(
    () => (latestRun ? candidates.filter((item) => item.run_id === latestRun.id) : candidates),
    [candidates, latestRun],
  );

  async function loadLab(runId?: number): Promise<void> {
    setLoading(true);
    setError(null);
    try {
      const [runList, candidateList] = await Promise.all([
        api.getShortpickRuns(20),
        api.getShortpickCandidates({ limit: 200 }),
      ]);
      setRuns(runList.data.items);
      setCandidates(candidateList.data.items);
      const targetRunId = runId ?? selectedRun?.id ?? runList.data.items[0]?.id;
      const target = runList.data.items.find((item) => item.id === targetRunId) ?? runList.data.items[0] ?? null;
      setSelectedRun(target);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "加载短投推荐试验田失败。");
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateRun(): Promise<void> {
    setAction("run");
    setError(null);
    try {
      const result = await api.createShortpickRun({ rounds_per_model: 5 });
      await loadLab(result.data.id);
    } catch (runError) {
      setError(runError instanceof Error ? runError.message : "触发短投推荐实验失败。");
    } finally {
      setAction(null);
    }
  }

  async function handleValidateRun(): Promise<void> {
    if (!latestRun) return;
    setAction("validate");
    setError(null);
    try {
      await api.validateShortpickRun(latestRun.id, { horizons: [1, 3, 5, 10, 20] });
      await loadLab(latestRun.id);
    } catch (validateError) {
      setError(validateError instanceof Error ? validateError.message : "补跑后验复盘失败。");
    } finally {
      setAction(null);
    }
  }

  useEffect(() => {
    void loadLab();
  }, []);

  const candidateColumns: ColumnsType<ShortpickCandidateView> = [
    {
      title: "研究标的",
      dataIndex: "symbol",
      key: "symbol",
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Text strong>{item.name} · {item.symbol}</Text>
          <Text type="secondary">{item.normalized_theme || "未归类题材"}</Text>
        </Space>
      ),
    },
    {
      title: "优先级",
      dataIndex: "research_priority",
      key: "research_priority",
      render: (value: string, item) => (
        <Space wrap>
          <Tag color={priorityColor(value)}>{priorityLabel(value)}</Tag>
          {item.is_system_external ? <Tag color="blue">系统外新视角</Tag> : <Tag>系统内已覆盖</Tag>}
        </Space>
      ),
    },
    {
      title: "模型理由",
      dataIndex: "thesis",
      key: "thesis",
      render: (value: string | null) => <Text>{value || "--"}</Text>,
    },
    {
      title: "验证",
      key: "validation",
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Text>{validationSummary(item)}</Text>
          <Text type="secondary">完成前不得显示为 verified</Text>
        </Space>
      ),
    },
  ];

  const roundColumns: ColumnsType<ShortpickRoundView> = [
    {
      title: "模型轮次",
      key: "model",
      render: (_, item) => <Text strong>{roundModelLabel(item)}</Text>,
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      render: (value: string) => <Tag color={statusColor(value)}>{statusLabel(value)}</Tag>,
    },
    {
      title: "推荐",
      key: "pick",
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Text>{item.stock_name && item.symbol ? `${item.stock_name} · ${item.symbol}` : "--"}</Text>
          <Text type="secondary">{item.theme || "未归类"}</Text>
        </Space>
      ),
    },
    {
      title: "理由",
      dataIndex: "thesis",
      key: "thesis",
      render: (value: string | null) => <Text>{value || "--"}</Text>,
    },
  ];

  return (
    <section className="shortpick-lab">
      <Card className="panel-card shortpick-lab-header">
        <div className="shortpick-lab-title">
          <div>
            <Paragraph className="topbar-kicker">Short Pick Lab</Paragraph>
            <Title level={3}>短投推荐试验田</Title>
            <Paragraph className="panel-description">
              独立研究课题，不进入主推荐评分；模型一致性只代表研究优先级，不代表交易建议；后验验证完成前不得显示为已验证能力。
            </Paragraph>
          </div>
          <Space wrap>
            <Button icon={<ReloadOutlined />} onClick={() => void loadLab()} loading={loading}>
              刷新
            </Button>
            {canTrigger ? (
              <>
                <Button
                  type="primary"
                  icon={<ExperimentOutlined />}
                  loading={action === "run"}
                  onClick={() => void handleCreateRun()}
                >
                  触发实验
                </Button>
                <Button
                  icon={<SyncOutlined />}
                  disabled={!latestRun}
                  loading={action === "validate"}
                  onClick={() => void handleValidateRun()}
                >
                  补跑复盘
                </Button>
              </>
            ) : null}
          </Space>
        </div>
        {error ? <Alert type="error" showIcon message={error} /> : null}
      </Card>

      {!latestRun && !loading ? (
        <Card className="panel-card">
          <Empty description="暂无短投推荐实验批次" />
        </Card>
      ) : null}

      {latestRun ? (
        <>
          <Row gutter={[16, 16]} className="shortpick-metrics">
            <Col xs={24} md={6}>
              <div className="shortpick-metric">
                <span>最近批次</span>
                <strong>{latestRun.run_date}</strong>
                <Text type="secondary">{statusLabel(latestRun.status)}</Text>
              </div>
            </Col>
            <Col xs={24} md={6}>
              <div className="shortpick-metric">
                <span>完成 / 失败轮次</span>
                <strong>{Number(latestRun.summary.completed_round_count ?? 0)} / {Number(latestRun.summary.failed_round_count ?? 0)}</strong>
                <Text type="secondary">{latestRun.prompt_version}</Text>
              </div>
            </Col>
            <Col xs={24} md={6}>
              <div className="shortpick-metric">
                <span>综合优先级</span>
                <strong>{priorityLabel(latestRun.consensus?.research_priority ?? "pending")}</strong>
                <Text type="secondary">研究池排序信号</Text>
              </div>
            </Col>
            <Col xs={24} md={6}>
              <div className="shortpick-metric">
                <span>研究边界</span>
                <strong>旁路</strong>
                <Text type="secondary">不污染量化池</Text>
              </div>
            </Col>
          </Row>

          <Card
            className="panel-card"
            title="今日收敛结果"
            extra={<Tag color={priorityColor(latestRun.consensus?.research_priority ?? "pending")}>{priorityLabel(latestRun.consensus?.research_priority ?? "pending")}</Tag>}
          >
            {latestRun.consensus ? (
              <>
                <Row gutter={[20, 16]}>
                  <Col xs={24} md={8}>
                    <Progress percent={Math.round(latestRun.consensus.stock_convergence * 100)} size="small" />
                    <Text>单票收敛</Text>
                  </Col>
                  <Col xs={24} md={8}>
                    <Progress percent={Math.round(latestRun.consensus.theme_convergence * 100)} size="small" />
                    <Text>题材收敛</Text>
                  </Col>
                  <Col xs={24} md={8}>
                    <Progress percent={Math.round(latestRun.consensus.source_diversity * 100)} size="small" />
                    <Text>来源多样性</Text>
                  </Col>
                </Row>
                <Descriptions className="shortpick-consensus-desc" size="small" column={{ xs: 1, md: 3 }}>
                  <Descriptions.Item label="领先股票">
                    {Array.isArray(latestRun.consensus.summary.leader_symbols)
                      ? (latestRun.consensus.summary.leader_symbols as string[]).join(" / ") || "--"
                      : "--"}
                  </Descriptions.Item>
                  <Descriptions.Item label="领先题材">
                    {Array.isArray(latestRun.consensus.summary.leader_themes)
                      ? (latestRun.consensus.summary.leader_themes as string[]).join(" / ") || "--"
                      : "--"}
                  </Descriptions.Item>
                  <Descriptions.Item label="解释">
                    {String(latestRun.consensus.summary.interpretation ?? "模型一致性只代表研究优先级。")}
                  </Descriptions.Item>
                </Descriptions>
              </>
            ) : (
              <Empty description="等待聚合结果" />
            )}
          </Card>

          <Card className="panel-card" title="研究池">
            <Table
              rowKey="id"
              size="middle"
              loading={loading}
              columns={candidateColumns}
              dataSource={latestCandidates}
              pagination={{ pageSize: 8 }}
              expandable={{
                expandedRowRender: (item) => (
                  <div className="shortpick-detail-grid">
                    <div>
                      <Title level={5}>催化与风险</Title>
                      <List size="small" dataSource={[...item.catalysts, ...item.risks]} renderItem={(text) => <List.Item>{text}</List.Item>} />
                    </div>
                    <div>
                      <Title level={5}>后验复盘</Title>
                      <ValidationList items={item.validations} />
                    </div>
                    <div>
                      <Title level={5}>来源与留痕</Title>
                      <List
                        size="small"
                        dataSource={item.sources}
                        renderItem={(source) => (
                          <List.Item>
                            <Space direction="vertical" size={0}>
                              <Space wrap>
                                <a href={source.url || undefined} target="_blank" rel="noreferrer">{source.title || source.url || "未命名来源"}</a>
                                <Tag color={sourceCredibilityColor(source.credibility_status)}>
                                  {sourceCredibilityLabel(source.credibility_status)}
                                  {source.http_status ? ` ${source.http_status}` : ""}
                                </Tag>
                              </Space>
                              <Text type="secondary">{source.published_at || "发布时间未声明"} · {source.why_it_matters || "未说明"}</Text>
                              {source.credibility_reason ? <Text type="secondary">校验：{source.credibility_reason}</Text> : null}
                            </Space>
                          </List.Item>
                        )}
                      />
                      {item.raw_round?.raw_answer ? (
                        <Collapse
                          className="shortpick-raw-collapse"
                          items={[{
                            key: "raw",
                            label: "原始模型输出",
                            children: <pre className="shortpick-raw-answer">{item.raw_round.raw_answer}</pre>,
                          }]}
                        />
                      ) : null}
                    </div>
                  </div>
                ),
              }}
            />
          </Card>

          <Card className="panel-card" title="模型原始推荐">
            <Table
              rowKey="id"
              size="middle"
              loading={loading}
              columns={roundColumns}
              dataSource={latestRun.rounds}
              pagination={{ pageSize: 10 }}
            />
          </Card>

          <Alert
            type="info"
            showIcon
            icon={<SafetyCertificateOutlined />}
            message="隔离规则"
            description="短投推荐实验只写入 shortpick_lab 数据域和 artifact，不写入现有候选池、自选池、量化推荐、模拟盘自动调仓或生产权重。"
          />
        </>
      ) : null}
    </section>
  );
}

function ValidationList({ items }: { items: ShortpickValidationView[] }) {
  if (!items.length) {
    return <Text type="secondary">暂无验证窗口。</Text>;
  }
  return (
    <List
      size="small"
      dataSource={items}
      renderItem={(item) => (
        <List.Item>
          <Space wrap>
            <Tag color={statusColor(item.status)}>{item.horizon_days}日 · {statusLabel(item.status)}</Tag>
            <Text className={`value-${valueTone(item.stock_return)}`}>{formatPercent(item.stock_return)}</Text>
            <Text type="secondary">{item.exit_at ? formatDate(item.exit_at) : "等待窗口"}</Text>
            <Text type="secondary">浮盈 {formatPercent(item.max_favorable_return)} / 回撤 {formatPercent(item.max_drawdown)}</Text>
          </Space>
        </List.Item>
      )}
    />
  );
}
