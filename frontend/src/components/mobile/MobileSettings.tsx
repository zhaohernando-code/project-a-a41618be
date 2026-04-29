import { DatabaseOutlined, MoonOutlined, ReloadOutlined, SettingOutlined, SunOutlined } from "@ant-design/icons";
import { Button, Empty, Space, Switch, Tag, Typography } from "antd";
import type { MobileAppShellProps } from "./types";
import { MobileMetric } from "./MobileMetric";
import { dataSourceStatusColor, deploymentModeLabel, providerSelectionModeLabel, sanitizeDisplayText, watchlistScopeLabel } from "../../utils/labels";
import { formatDate } from "../../utils/format";

const { Text, Title } = Typography;

export function MobileSettings(props: MobileAppShellProps) {
  const runtime = props.runtimeSettings;
  return (
    <main className="mobile-page">
      <header className="mobile-page-head">
        <div>
          <Text className="mobile-kicker">设置</Text>
          <Title level={2}>运行配置</Title>
          <Text>{props.sourceInfo.label}</Text>
        </div>
        <Button shape="circle" icon={<ReloadOutlined />} onClick={() => void props.onRefresh()} />
      </header>

      <section className="mobile-hero-card mobile-settings-hero">
        <div className="mobile-focus-title">
          <div>
            <Text className="mobile-card-kicker">当前模式</Text>
            <Title level={3}>{deploymentModeLabel(runtime?.deployment_mode ?? "self_hosted_server")}</Title>
          </div>
          <DatabaseOutlined />
        </div>
        <p>{sanitizeDisplayText(props.sourceInfo.detail)}</p>
        <div className="mobile-metric-grid">
          <MobileMetric label="存储" value={runtime?.storage_engine ?? "SQLite"} />
          <MobileMetric label="缓存" value={runtime?.cache_backend ?? "Redis"} />
          <MobileMetric label="刷新" value={formatDate(props.generatedAt)} />
        </div>
      </section>

      <section className="mobile-panel-card">
        <div className="mobile-section-head">
          <div>
            <Title level={4}>外观</Title>
            <Text>本地浏览器偏好</Text>
          </div>
          {props.themeMode === "dark" ? <MoonOutlined /> : <SunOutlined />}
        </div>
        <div className="mobile-setting-row">
          <div>
            <strong>深色模式</strong>
            <span>{props.themeMode === "dark" ? "当前为夜间模式" : "当前为浅色模式"}</span>
          </div>
          <Switch checked={props.themeMode === "dark"} onChange={props.onToggleTheme} />
        </div>
      </section>

      <section className="mobile-panel-card">
        <div className="mobile-section-head">
          <div>
            <Title level={4}>数据源</Title>
            <Text>{providerSelectionModeLabel(runtime?.provider_selection_mode ?? "runtime_policy")}</Text>
          </div>
          <SettingOutlined />
        </div>
        <Space wrap className="mobile-chip-row">
          <Tag>{watchlistScopeLabel(runtime?.watchlist_scope ?? "shared_watchlist")}</Tag>
          <Tag>{`LLM 故障切换 ${runtime?.llm_failover_enabled ? "开启" : "关闭"}`}</Tag>
        </Space>
        <div className="mobile-card-list">
          {(runtime?.data_sources ?? []).length > 0 ? runtime?.data_sources.map((source) => (
            <article key={source.provider_name} className="mobile-mini-card">
              <div className="mobile-mini-head">
                <div>
                  <strong>{source.provider_name}</strong>
                  <span>{source.provider_name}</span>
                </div>
                <Tag color={dataSourceStatusColor(source)}>{source.status_label}</Tag>
              </div>
              <p>{sanitizeDisplayText(source.notes.join(" ") || source.base_url || "当前数据源由运行时策略管理。")}</p>
            </article>
          )) : <Empty description="暂无数据源状态" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
        </div>
      </section>

      <section className="mobile-panel-card">
        <Title level={4}>模型 Key</Title>
        <div className="mobile-card-list">
          {props.modelApiKeys.length > 0 ? props.modelApiKeys.map((item) => (
            <article key={item.id} className="mobile-mini-card">
              <div className="mobile-mini-head">
                <div>
                  <strong>{item.name}</strong>
                  <span>{item.model_name}</span>
                </div>
                <Tag color={item.enabled ? "green" : "default"}>{item.enabled ? "启用" : "关闭"}</Tag>
              </div>
              <Space wrap className="mobile-chip-row">
                {item.is_default ? <Tag color="blue">默认</Tag> : null}
                <Tag>{item.provider_name}</Tag>
                <Tag>{`优先级 ${item.priority}`}</Tag>
              </Space>
            </article>
          )) : <Empty description="暂无模型 Key" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
        </div>
      </section>

      <section className="mobile-panel-card">
        <Title level={4}>缓存策略</Title>
        <div className="mobile-card-list">
          {(runtime?.cache_policies ?? []).slice(0, 5).map((item) => (
            <article key={`${item.dataset}-${item.ttl_seconds}`} className="mobile-mini-card mobile-cache-row">
              <strong>{item.label}</strong>
              <span>{`${item.ttl_seconds}s · 失败读旧 ${item.stale_if_error_seconds}s · ${item.warm_on_watchlist ? "关注池预热" : "全量"}`}</span>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
