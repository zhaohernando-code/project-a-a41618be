import { ApiOutlined, CheckCircleOutlined, CloudServerOutlined, DatabaseOutlined, KeyOutlined, MoonOutlined, ReloadOutlined, RightOutlined, SettingOutlined, SunOutlined } from "@ant-design/icons";
import { Button, Empty, Switch, Tag, Typography } from "antd";
import type { ReactNode } from "react";
import type { MobileAppShellProps } from "./types";
import { dataSourceStatusColor, deploymentModeLabel, providerSelectionModeLabel, sanitizeDisplayText, watchlistScopeLabel } from "../../utils/labels";
import { formatDate } from "../../utils/format";

const { Text, Title } = Typography;

export function MobileSettings(props: MobileAppShellProps) {
  const runtime = props.runtimeSettings;
  const primarySource = runtime?.data_sources[0];
  const defaultKey = props.modelApiKeys.find((item) => item.is_default) ?? props.modelApiKeys[0];

  return (
    <main className="mobile-page">
      <header className="mobile-page-head">
        <div>
          <Title level={2}>设置</Title>
          <Text>
            <span className="mobile-live-dot" />
            {props.sourceInfo.label}
          </Text>
        </div>
        <Button className="mobile-icon-button" shape="circle" icon={<ReloadOutlined />} onClick={() => void props.onRefresh()} />
      </header>

      <section className="mobile-settings-group">
        <Title level={4}>运行状态</Title>
        <SettingsRow icon={<DatabaseOutlined />} title="SQLite" detail={runtime?.storage_engine ?? "本地存储"} value="可用" tone="green" />
        <SettingsRow icon={<CloudServerOutlined />} title="Redis" detail={runtime?.cache_backend ?? "缓存服务"} value="可用" tone="green" />
        <SettingsRow icon={<ReloadOutlined />} title="最近刷新" detail={formatDate(props.generatedAt)} value={deploymentModeLabel(runtime?.deployment_mode ?? "self_hosted_server")} />
        <SettingsRow icon={<CheckCircleOutlined />} title="健康状态" detail={sanitizeDisplayText(props.sourceInfo.detail)} value="正常" tone="green" />
      </section>

      <section className="mobile-settings-group">
        <Title level={4}>模型与研究</Title>
        <SettingsRow icon={<KeyOutlined />} title="默认模型" detail={defaultKey ? `${defaultKey.provider_name} · ${defaultKey.model_name}` : "未配置"} value={defaultKey?.enabled ? "启用" : "未启用"} tone={defaultKey?.enabled ? "green" : undefined} />
        <SettingsRow icon={<SettingOutlined />} title="自动降级" detail={runtime?.llm_failover_enabled ? "模型异常时自动切换可用 Key" : "模型异常时不自动切换"} value={runtime?.llm_failover_enabled ? "开启" : "关闭"} />
        <SettingsRow icon={<ApiOutlined />} title="人工研究模式" detail={providerSelectionModeLabel(runtime?.provider_selection_mode ?? "runtime_policy")} value={watchlistScopeLabel(runtime?.watchlist_scope ?? "shared_watchlist")} />
      </section>

      <section className="mobile-settings-group">
        <Title level={4}>数据源</Title>
        {(runtime?.data_sources ?? []).length > 0 ? runtime?.data_sources.slice(0, 4).map((source) => (
          <SettingsRow
            key={source.provider_name}
            icon={<ApiOutlined />}
            title={source.provider_name}
            detail={sanitizeDisplayText(source.freshness_note || source.notes.join(" ") || source.base_url || "运行时策略管理")}
            value={source.status_label}
            tone={dataSourceStatusColor(source)}
          />
        )) : <Empty description="暂无数据源状态" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
      </section>

      <section className="mobile-settings-group">
        <Title level={4}>偏好设置</Title>
        <SettingsRow
          icon={props.themeMode === "dark" ? <MoonOutlined /> : <SunOutlined />}
          title="夜间模式"
          detail={props.themeMode === "dark" ? "当前为夜间配色，移动端仍保持设计稿版式" : "当前为浅色配色"}
          trailing={<Switch checked={props.themeMode === "dark"} onChange={props.onToggleTheme} />}
        />
        <SettingsRow icon={<SettingOutlined />} title="紧凑列表" detail="移动端按设计稿使用高信息密度卡片" value="默认" />
        <SettingsRow icon={<CheckCircleOutlined />} title="风险优先提醒" detail="风险标签在候选和单票页前置展示" value="默认" />
      </section>

      <section className="mobile-settings-group">
        <Title level={4}>关于看板</Title>
        <SettingsRow icon={<CloudServerOutlined />} title="运行版本" detail={formatDate(runtime?.generated_at ?? props.generatedAt)} value="本机" />
        <SettingsRow icon={<ApiOutlined />} title="规范路由" detail={primarySource?.docs_url || "https://hernando-zhao.cn/projects/ashare-dashboard/"} value="可访问" tone="green" />
      </section>
    </main>
  );
}

function SettingsRow({
  icon,
  title,
  detail,
  value,
  tone,
  trailing,
}: {
  icon: ReactNode;
  title: string;
  detail: string;
  value?: string;
  tone?: string;
  trailing?: ReactNode;
}) {
  return (
    <div className="mobile-settings-row">
      <span className="mobile-settings-icon">{icon}</span>
      <span className="mobile-settings-copy">
        <strong>{title}</strong>
        <em>{detail}</em>
      </span>
      {trailing ?? (
        <span className="mobile-settings-trailing">
          {value ? <Tag color={tone}>{value}</Tag> : null}
          <RightOutlined />
        </span>
      )}
    </div>
  );
}
