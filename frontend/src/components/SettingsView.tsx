import { useState } from "react";
import {
  Alert, Button, Card, Col, Collapse, Descriptions, Empty,
  Form, Input, InputNumber, List, Modal, Row, Select, Space,
  Statistic, Switch, Table, Tag, Tabs, Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import {
  DatabaseOutlined, DeleteOutlined, PlusOutlined, ReloadOutlined,
  SettingOutlined, SyncOutlined, ThunderboltOutlined,
} from "@ant-design/icons";
import { api } from "../api";
import type {
  DataSourceInfo, ModelApiKeyView, ProviderCredentialView,
  RuntimeDataSourceView, RuntimeFieldMappingView, RuntimeSettingsResponse,
} from "../types";
import {
  dataSourceStatusColor, deploymentModeLabel, fieldMappingLabel,
  providerSelectionModeLabel, watchlistScopeLabel,
} from "../utils/labels";
import { formatDate } from "../utils/format";

const { Paragraph, Text, Title } = Typography;
const { TextArea } = Input;

export interface BuildSettingsTabsInput {
  runtimeSettings: RuntimeSettingsResponse | null;
  sourceInfo: DataSourceInfo;
  generatedAt: string | null;
  modelApiKeys: ModelApiKeyView[];
  providerCredentials: ProviderCredentialView[];
  newKeyName: string;
  setNewKeyName: (v: string) => void;
  newKeyProvider: string;
  setNewKeyProvider: (v: string) => void;
  newKeyModel: string;
  setNewKeyModel: (v: string) => void;
  newKeyBaseUrl: string;
  setNewKeyBaseUrl: (v: string) => void;
  newKeySecret: string;
  setNewKeySecret: (v: string) => void;
  newKeyPriority: string;
  setNewKeyPriority: (v: string) => void;
  providerDrafts: Record<string, { accessToken: string; baseUrl: string; enabled: boolean; notes: string }>;
  setProviderDrafts: React.Dispatch<React.SetStateAction<Record<string, { accessToken: string; baseUrl: string; enabled: boolean; notes: string }>>>;
  savingConfig: boolean;
  setSavingConfig: (v: boolean) => void;
  messageApi: { warning: (msg: string) => void; success: (msg: string) => void; error: (msg: string) => void };
  loadRuntimeSettings: () => Promise<void>;
  setError: (err: string | null) => void;
}

export function buildSettingsTabs(input: BuildSettingsTabsInput) {
  const {
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
  } = input;

  async function handleCreateModelApiKey() {
    if (!newKeyName.trim() || !newKeyModel.trim() || !newKeyBaseUrl.trim() || !newKeySecret.trim()) {
      messageApi.warning("请完整填写模型 Key 名称、模型名、Base URL 和 Key。");
      return;
    }
    setSavingConfig(true);
    setError(null);
    try {
      await api.createModelApiKey({
        name: newKeyName.trim(),
        provider_name: newKeyProvider.trim(),
        model_name: newKeyModel.trim(),
        base_url: newKeyBaseUrl.trim(),
        api_key: newKeySecret.trim(),
        enabled: true,
        priority: Number.parseInt(newKeyPriority, 10) || 100,
        make_default: modelApiKeys.length === 0,
      });
      setNewKeyName("");
      setNewKeySecret("");
      setNewKeyPriority("100");
      await loadRuntimeSettings();
      messageApi.success("模型 API Key 已保存。");
    } catch (saveError) {
      const messageText = saveError instanceof Error ? saveError.message : "保存模型 API Key 失败。";
      setError(messageText);
      messageApi.error(messageText);
    } finally {
      setSavingConfig(false);
    }
  }

  async function handleToggleModelApiKey(item: ModelApiKeyView) {
    setSavingConfig(true);
    setError(null);
    try {
      await api.updateModelApiKey(item.id, { enabled: !item.enabled });
      await loadRuntimeSettings();
      messageApi.success(item.enabled ? "Key 已关闭。" : "Key 已启用。");
    } catch (saveError) {
      const messageText = saveError instanceof Error ? saveError.message : "更新 Key 状态失败。";
      setError(messageText);
      messageApi.error(messageText);
    } finally {
      setSavingConfig(false);
    }
  }

  async function handleSetDefaultModelApiKey(item: ModelApiKeyView) {
    setSavingConfig(true);
    setError(null);
    try {
      await api.setDefaultModelApiKey(item.id);
      await loadRuntimeSettings();
      messageApi.success("默认 Key 已切换。");
    } catch (saveError) {
      const messageText = saveError instanceof Error ? saveError.message : "切换默认 Key 失败。";
      setError(messageText);
      messageApi.error(messageText);
    } finally {
      setSavingConfig(false);
    }
  }

  async function handleDeleteModelApiKey(item: ModelApiKeyView) {
    Modal.confirm({
      title: "确认删除",
      content: `确定要删除「${item.name}」吗？不可撤销。`,
      okText: "删除",
      okType: "danger",
      cancelText: "取消",
      onOk: async () => {
        setSavingConfig(true);
        try {
          await api.deleteModelApiKey(item.id);
          await loadRuntimeSettings();
          messageApi.success("Key 已删除。");
        } catch (saveError) {
          const messageText = saveError instanceof Error ? saveError.message : "删除 Key 失败。";
          setError(messageText);
          messageApi.error(messageText);
        } finally {
          setSavingConfig(false);
        }
      },
    });
  }

  async function handleSaveProviderCredential(providerName: string) {
    const draft = providerDrafts[providerName];
    if (!draft) return;
    setSavingConfig(true);
    setError(null);
    try {
      await api.upsertProviderCredential(providerName, {
        access_token: draft.accessToken.trim(),
        base_url: draft.baseUrl.trim() || undefined,
        enabled: draft.enabled,
        notes: draft.notes.trim(),
      });
      await loadRuntimeSettings();
      messageApi.success("数据源配置已更新。");
    } catch (saveError) {
      const messageText = saveError instanceof Error ? saveError.message : "保存数据源配置失败。";
      setError(messageText);
      messageApi.error(messageText);
    } finally {
      setSavingConfig(false);
    }
  }

  return [
    {
      key: "overview",
      label: "说明",
      children: (
        <Row gutter={[16, 16]}>
          <Col xs={24} xl={9}>
            <Card className="panel-card" title="运行方式概览">
              <Descriptions size="small" column={1}>
                <Descriptions.Item label="部署模式">
                  {deploymentModeLabel(runtimeSettings?.deployment_mode ?? "self_hosted_server")}
                </Descriptions.Item>
                <Descriptions.Item label="存储引擎">{runtimeSettings?.storage_engine ?? "SQLite"}</Descriptions.Item>
                <Descriptions.Item label="缓存后端">{runtimeSettings?.cache_backend ?? "Redis"}</Descriptions.Item>
                <Descriptions.Item label="选源策略">
                  {providerSelectionModeLabel(runtimeSettings?.provider_selection_mode ?? "runtime_policy")}
                </Descriptions.Item>
                <Descriptions.Item label="关注池范围">
                  {watchlistScopeLabel(runtimeSettings?.watchlist_scope ?? "shared_watchlist")}
                </Descriptions.Item>
                <Descriptions.Item label="LLM 故障切换">{runtimeSettings?.llm_failover_enabled ? "开启" : "关闭"}</Descriptions.Item>
              </Descriptions>
              <Paragraph className="panel-description settings-help-text">
                {sourceInfo.detail}
              </Paragraph>
              <Space wrap className="inline-tags">
                <Tag color="green">{sourceInfo.label}</Tag>
                <Tag icon={<DatabaseOutlined />}>{runtimeSettings?.storage_engine ?? "SQLite"}</Tag>
                <Tag>{runtimeSettings?.cache_backend ?? "Redis"}</Tag>
              </Space>
            </Card>
          </Col>
          <Col xs={24} xl={15}>
            <Card className="panel-card" title="缓存与运行说明">
              <List
                size="small"
                dataSource={runtimeSettings?.cache_policies ?? []}
                renderItem={(item) => (
                  <List.Item>
                    <div className="full-width">
                      <div className="list-item-row">
                        <strong>{item.label}</strong>
                        <Tag>{`${item.ttl_seconds}s`}</Tag>
                      </div>
                      <div className="muted-line">{`失败读旧值 ${item.stale_if_error_seconds}s · ${item.warm_on_watchlist ? "仅关注池预热" : "全量"}`}</div>
                    </div>
                  </List.Item>
                )}
              />
              <div className="settings-note-stack">
                {(runtimeSettings?.deployment_notes ?? []).map((note) => (
                  <Alert key={note} type="info" showIcon message={note} />
                ))}
              </div>
              <Card size="small" className="sub-panel-card">
                <Title level={5}>抗击穿策略</Title>
                <ul className="plain-list">
                  <li>{`单飞刷新：${runtimeSettings?.anti_stampede.singleflight ? "开启" : "关闭"}`}</li>
                  <li>{`失败读旧值：${runtimeSettings?.anti_stampede.serve_stale_on_error ? "开启" : "关闭"}`}</li>
                  <li>{`空结果 TTL：${runtimeSettings?.anti_stampede.empty_result_ttl_seconds ?? "--"} 秒`}</li>
                  <li>{`锁超时：${runtimeSettings?.anti_stampede.lock_timeout_seconds ?? "--"} 秒`}</li>
                </ul>
              </Card>
            </Card>
          </Col>
          <Col xs={24} xl={10}>
            <Card className="panel-card" title="数据源状态">
              <List
                size="small"
                dataSource={runtimeSettings?.data_sources ?? []}
                renderItem={(item) => (
                  <List.Item>
                    <div className="full-width">
                      <div className="list-item-row">
                        <div>
                          <strong>{item.provider_name.toUpperCase()}</strong>
                          <div className="muted-line">{item.role}</div>
                        </div>
                        <Tag color={dataSourceStatusColor(item)}>{item.status_label}</Tag>
                      </div>
                      <Paragraph className="panel-description">{item.freshness_note}</Paragraph>
                      {item.supports_intraday ? <div className="muted-line">{item.intraday_status_label ?? "盘中分钟链路未配置"}</div> : null}
                    </div>
                  </List.Item>
                )}
              />
            </Card>
          </Col>
          <Col xs={24} xl={14}>
            <Card className="panel-card" title="数据口径说明">
              <List
                size="small"
                dataSource={runtimeSettings?.field_mappings ?? []}
                renderItem={(item) => (
                  <List.Item>
                    <div>
                      <strong>{fieldMappingLabel(item)}</strong>
                      <div className="muted-line">{item.notes}</div>
                    </div>
                  </List.Item>
                )}
              />
            </Card>
          </Col>
        </Row>
      ),
    },
    {
      key: "models",
      label: "模型",
      children: (
        <Row gutter={[16, 16]}>
          <Col xs={24} xl={14}>
            <Card
              className="panel-card"
              title="模型 API Key"
              extra={<Text type="secondary">{`当前 ${modelApiKeys.length} 个`}</Text>}
            >
              <List
                dataSource={modelApiKeys}
                locale={{ emptyText: "尚未配置模型 API Key" }}
                renderItem={(item) => (
                  <List.Item>
                    <div className="watchlist-entry">
                      <div className="list-item-row">
                        <div>
                          <strong>{item.name}</strong>
                          <div className="muted-line">{`${item.provider_name} · ${item.model_name}`}</div>
                        </div>
                        <Space wrap>
                          {item.is_default ? <Tag color="blue">默认</Tag> : null}
                          <Tag color={item.enabled ? "green" : "default"}>{item.enabled ? "启用" : "停用"}</Tag>
                          <Tag>{`P${item.priority}`}</Tag>
                        </Space>
                      </div>
                      <div className="watchlist-meta">
                        <Text type="secondary">{item.base_url}</Text>
                        <Text type="secondary">{`最近状态 ${item.last_status}${item.last_error ? ` · ${item.last_error}` : ""}`}</Text>
                      </div>
                      <div className="watchlist-actions">
                        <Button type="link" disabled={item.is_default} onClick={() => void handleSetDefaultModelApiKey(item)}>
                          设为默认
                        </Button>
                        <Button type="link" onClick={() => void handleToggleModelApiKey(item)}>
                          {item.enabled ? "停用" : "启用"}
                        </Button>
                        <Button type="link" danger onClick={() => void handleDeleteModelApiKey(item)}>
                          删除
                        </Button>
                      </div>
                    </div>
                  </List.Item>
                )}
              />
            </Card>
          </Col>
          <Col xs={24} xl={10}>
            <Card className="panel-card" title="新增模型 Key">
              <Form layout="vertical">
                <Form.Item label="Key 名称" required>
                  <Input value={newKeyName} onChange={(event) => setNewKeyName(event.target.value)} placeholder="如：主 OpenAI" />
                </Form.Item>
                <Form.Item label="Provider" required>
                  <Input value={newKeyProvider} onChange={(event) => setNewKeyProvider(event.target.value)} placeholder="如：openai" />
                </Form.Item>
                <Form.Item label="模型名" required>
                  <Input value={newKeyModel} onChange={(event) => setNewKeyModel(event.target.value)} placeholder="如：gpt-4.1-mini" />
                </Form.Item>
                <Form.Item label="Base URL" required>
                  <Input value={newKeyBaseUrl} onChange={(event) => setNewKeyBaseUrl(event.target.value)} placeholder="如：https://api.openai.com/v1" />
                </Form.Item>
                <Form.Item label="API Key" required>
                  <Input.Password value={newKeySecret} onChange={(event) => setNewKeySecret(event.target.value)} placeholder="输入模型 API Key" />
                </Form.Item>
                <Form.Item label="优先级">
                  <Input value={newKeyPriority} onChange={(event) => setNewKeyPriority(event.target.value)} placeholder="数字越小优先级越高" />
                </Form.Item>
              </Form>
              <div className="deck-actions">
                <Button type="primary" loading={savingConfig} onClick={() => void handleCreateModelApiKey()}>
                  保存模型 Key
                </Button>
              </div>
            </Card>
          </Col>
        </Row>
      ),
    },
    {
      key: "providers",
      label: "数据源",
      children: (
        <Row gutter={[16, 16]}>
          {(runtimeSettings?.data_sources ?? []).map((item) => {
            const draft = providerDrafts[item.provider_name] ?? {
              accessToken: "",
              baseUrl: item.base_url ?? "",
              enabled: item.enabled,
              notes: "",
            };
            const saved = providerCredentials.find((credential) => credential.provider_name === item.provider_name);

            return (
              <Col key={item.provider_name} xs={24} xl={12}>
                <Card className="panel-card" title={item.provider_name.toUpperCase()}>
                  <div className="list-item-row">
                    <div>
                      <Tag color={dataSourceStatusColor(item)}>{item.status_label}</Tag>
                      <Paragraph className="panel-description">{item.freshness_note}</Paragraph>
                      {item.supports_intraday ? <Paragraph className="panel-description">{item.intraday_status_label ?? "盘中分钟链路未配置"}</Paragraph> : null}
                    </div>
                    <div className="settings-switch">
                      <Text type="secondary">启用</Text>
                      <Switch
                        checked={draft.enabled}
                        onChange={(checked) =>
                          setProviderDrafts((current) => ({
                            ...current,
                            [item.provider_name]: { ...draft, enabled: checked },
                          }))
                        }
                      />
                    </div>
                  </div>
                  <Form layout="vertical">
                    <Form.Item label="Base URL">
                      <Input
                        value={draft.baseUrl}
                        onChange={(event) =>
                          setProviderDrafts((current) => ({
                            ...current,
                            [item.provider_name]: { ...draft, baseUrl: event.target.value },
                          }))
                        }
                        placeholder="可选：覆盖默认 Base URL"
                      />
                    </Form.Item>
                    <Form.Item label={item.credential_required ? "Access Token" : "预留 Token"}>
                      <Input.Password
                        value={draft.accessToken}
                        onChange={(event) =>
                          setProviderDrafts((current) => ({
                            ...current,
                            [item.provider_name]: { ...draft, accessToken: event.target.value },
                          }))
                        }
                        placeholder={item.credential_required ? "输入服务端使用的 Token" : "可选：为未来代理层预留"}
                      />
                    </Form.Item>
                    <Form.Item label="备注">
                      <Input
                        value={draft.notes}
                        onChange={(event) =>
                          setProviderDrafts((current) => ({
                            ...current,
                            [item.provider_name]: { ...draft, notes: event.target.value },
                          }))
                        }
                        placeholder="记录接入说明、范围或限制"
                      />
                    </Form.Item>
                  </Form>
                  <div className="deck-actions">
                    <Button type="primary" loading={savingConfig} onClick={() => void handleSaveProviderCredential(item.provider_name)}>
                      保存数据源设置
                    </Button>
                  </div>
                  <Space wrap className="inline-tags">
                    <Tag>{saved?.masked_token ?? "未保存 Token"}</Tag>
                    <Tag>{item.docs_url}</Tag>
                  </Space>
                </Card>
              </Col>
            );
          })}
        </Row>
      ),
    },
  ];
;
}
