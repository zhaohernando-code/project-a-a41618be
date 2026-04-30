import { ApiOutlined, CheckCircleOutlined, CloudServerOutlined, DatabaseOutlined, KeyOutlined, LeftOutlined, MoonOutlined, ReloadOutlined, RightOutlined, SettingOutlined, SunOutlined } from "@ant-design/icons";
import { Button, Empty, Switch, Tag, Typography } from "antd";
import { useState, type ReactNode } from "react";
import type { MobileAppShellProps } from "./types";
import { dataSourceStatusColor, deploymentModeLabel, providerSelectionModeLabel, sanitizeDisplayText, watchlistScopeLabel } from "../../utils/labels";
import { formatDate } from "../../utils/format";

const { Title } = Typography;

type SettingsPanelKey = "model" | null;

export function MobileSettings(props: MobileAppShellProps) {
  const runtime = props.runtimeSettings ?? props.runtimeOverview;
  const [panel, setPanel] = useState<SettingsPanelKey>(null);
  const [savingModel, setSavingModel] = useState(false);
  const themeLabel = props.themeMode === "dark" ? "夜间模式" : "浅色模式";
  const activeModelKey = props.analysisKeyId ? props.modelApiKeys.find((item) => item.id === props.analysisKeyId) : null;
  const activeModelDetail = activeModelKey ? `${activeModelKey.name} · ${activeModelKey.model_name}` : "本机 Codex GPT";

  async function selectAnalysisModel(keyId: number | undefined) {
    setSavingModel(true);
    try {
      await props.onSelectAnalysisModel(keyId);
      setPanel(null);
    } finally {
      setSavingModel(false);
    }
  }

  if (panel === "model") {
    return (
      <main className="mobile-page">
        <header className="mobile-app-top-bar">
          <Button className="mobile-icon-button" type="text" icon={<LeftOutlined />} onClick={() => setPanel(null)} />
          <strong>默认模型</strong>
          <span aria-hidden="true" />
        </header>

        <section className="mobile-settings-group mobile-settings-panel">
          <Title level={4}>人工研究执行器</Title>
          <SettingsOption
            icon={<ApiOutlined />}
            title="本机 Codex GPT"
            detail="使用本机 Codex 启动 gpt-5.5 研究"
            value="builtin"
            active={!props.analysisKeyId}
            disabled={savingModel}
            onClick={() => void selectAnalysisModel(undefined)}
          />
          {props.modelApiKeys.length > 0 ? props.modelApiKeys.map((item) => (
            <SettingsOption
              key={item.id}
              icon={<KeyOutlined />}
              title={item.name}
              detail={`${item.provider_name} · ${item.model_name}${item.enabled ? "" : " · 已停用"}`}
              value={item.is_default ? "默认 Key" : item.enabled ? "可用" : "停用"}
              active={props.analysisKeyId === item.id}
              disabled={savingModel || !item.enabled}
              onClick={() => void selectAnalysisModel(item.id)}
            />
          )) : <Empty description="暂无外部模型 Key" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
        </section>
      </main>
    );
  }

  return (
    <main className="mobile-page">
      <header className="mobile-app-top-bar">
        <span aria-hidden="true" />
        <strong>设置</strong>
        <Button className="mobile-icon-button" type="text" icon={<ReloadOutlined />} onClick={() => void props.onRefresh()} />
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
        <SettingsRow
          icon={<KeyOutlined />}
          title="默认模型"
          detail={activeModelDetail}
          value={activeModelKey ? "Key" : "Codex"}
          tone={activeModelKey ? (activeModelKey.enabled ? "green" : undefined) : "blue"}
          onClick={() => setPanel("model")}
        />
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
          title="外观主题"
          detail={`当前为${themeLabel}`}
          trailing={<Switch size="small" checked={props.themeMode === "dark"} onChange={props.onToggleTheme} />}
        />
        <SettingsRow icon={<SettingOutlined />} title="紧凑列表" detail="移动端按设计稿使用高信息密度卡片" value="默认" />
        <SettingsRow icon={<CheckCircleOutlined />} title="风险优先提醒" detail="风险标签在候选和单票页前置展示" value="默认" />
      </section>

      <section className="mobile-settings-group">
        <Title level={4}>关于看板</Title>
        <SettingsRow icon={<CloudServerOutlined />} title="运行版本" detail={formatDate(runtime?.generated_at ?? props.generatedAt)} value="本机" />
      </section>
    </main>
  );
}

function SettingsOption({
  icon,
  title,
  detail,
  value,
  active,
  disabled,
  onClick,
}: {
  icon: ReactNode;
  title: string;
  detail: string;
  value: string;
  active: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button type="button" className={`mobile-settings-option${active ? " active" : ""}`} disabled={disabled} onClick={onClick}>
      <span className="mobile-settings-icon">{icon}</span>
      <span className="mobile-settings-copy">
        <strong>{title}</strong>
        <em>{detail}</em>
      </span>
      <span className="mobile-settings-trailing">
        <Tag color={active ? "blue" : undefined}>{value}</Tag>
      </span>
      {active ? <CheckCircleOutlined className="mobile-settings-check" /> : null}
    </button>
  );
}

function SettingsRow({
  icon,
  title,
  detail,
  value,
  tone,
  trailing,
  onClick,
}: {
  icon: ReactNode;
  title: string;
  detail: string;
  value?: string;
  tone?: string;
  trailing?: ReactNode;
  onClick?: () => void;
}) {
  const content = (
    <>
      <span className="mobile-settings-icon">{icon}</span>
      <span className="mobile-settings-copy">
        <strong>{title}</strong>
        <em>{detail}</em>
      </span>
      {trailing || value || onClick ? (
        <span className="mobile-settings-trailing">
          {trailing ?? (value ? <Tag color={tone}>{value}</Tag> : null)}
          {onClick ? <RightOutlined /> : null}
        </span>
      ) : null}
    </>
  );

  if (onClick) {
    return (
      <button type="button" className="mobile-settings-row mobile-settings-row-action" onClick={onClick}>
        {content}
      </button>
    );
  }

  return (
    <div className="mobile-settings-row">
      {content}
    </div>
  );
}
