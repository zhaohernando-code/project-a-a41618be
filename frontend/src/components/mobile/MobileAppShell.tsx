import {
  BarChartOutlined,
  HomeOutlined,
  LineChartOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import { Alert, Button, Select, Skeleton, Tag } from "antd";
import { useEffect, useMemo, useState } from "react";
import type { MobileAppShellProps, MobileStockPanelKey, MobileTabKey } from "./types";
import { MobileHome } from "./MobileHome";
import { MobileStockDetail } from "./MobileStockDetail";
import { MobileOperations } from "./MobileOperations";
import { MobileSettings } from "./MobileSettings";

export function MobileAppShell(props: MobileAppShellProps) {
  const [activeTab, setActiveTab] = useState<MobileTabKey>("home");
  const [stockPanel, setStockPanel] = useState<MobileStockPanelKey>("advice");
  const navItems = useMemo(
    () => ([
      { key: "home", label: "首页", icon: <HomeOutlined /> },
      { key: "stock", label: "单票", icon: <LineChartOutlined /> },
      ...(props.canUseOperations ? [{ key: "operations", label: "复盘", icon: <BarChartOutlined /> }] : []),
      ...(props.canUseSettings ? [{ key: "settings", label: "设置", icon: <SettingOutlined /> }] : []),
    ] as Array<{ key: MobileTabKey; label: string; icon: React.ReactNode }>),
    [props.canUseOperations, props.canUseSettings],
  );

  useEffect(() => {
    if ((activeTab === "operations" && !props.canUseOperations) || (activeTab === "settings" && !props.canUseSettings)) {
      setActiveTab("home");
      props.onTabChange("home");
    }
  }, [activeTab, props.canUseOperations, props.canUseSettings, props.onTabChange]);

  function activate(tab: MobileTabKey) {
    if (tab === "operations" && !props.canUseOperations) {
      setActiveTab("home");
      props.onTabChange("home");
      return;
    }
    if (tab === "settings" && !props.canUseSettings) {
      setActiveTab("home");
      props.onTabChange("home");
      return;
    }
    setActiveTab(tab);
    props.onTabChange(tab);
    if (tab === "operations" && !props.operations && !props.simulation && !props.operationsLoading) {
      void props.onLoadOperations();
    }
  }

  function selectSymbol(symbol: string, target: MobileTabKey = "stock") {
    props.onSelectSymbol(symbol, target);
    activate(target);
  }

  const mobileProps = {
    ...props,
    onSelectSymbol: selectSymbol,
    onTabChange: activate,
    stockPanel,
    setStockPanel,
  };

  return (
    <div className="app-theme-shell mobile-theme-shell" data-theme={props.themeMode}>
      <div className="mobile-app-shell">
        {props.loadingShell ? (
          <main className="mobile-page mobile-page-centered">
            <Skeleton active paragraph={{ rows: 8 }} />
          </main>
        ) : (
          <>
            {props.error ? (
              <Alert
                showIcon
                type="error"
                className="mobile-global-alert"
                message="面板加载失败"
                description={props.error}
              />
            ) : null}
            {props.authContext?.can_act_as ? (
              <section className="mobile-section-plain" style={{ paddingBottom: 0 }}>
                <div className="mobile-settings-row">
                  <span className="mobile-settings-copy">
                    <strong>当前空间</strong>
                    <em>{`登录 ${props.authContext.actor_login} · 查看 ${props.authContext.target_login}`}</em>
                  </span>
                  <span className="mobile-settings-trailing" style={{ minWidth: 164 }}>
                    <Select
                      size="small"
                      style={{ width: "100%" }}
                      value={props.authContext.target_login}
                      options={props.authContext.visible_account_spaces.map((item) => ({
                        value: item.account_login,
                        label: item.account_login,
                      }))}
                      onChange={(value) => void props.onSwitchAccount?.(value)}
                    />
                  </span>
                </div>
                <div style={{ padding: "0 16px 8px" }}>
                  <Tag color="gold">root 可代看</Tag>
                </div>
                {props.authContext.target_login !== props.authContext.actor_login ? (
                  <div style={{ padding: "0 16px 8px" }}>
                    <Alert
                      showIcon
                      type="warning"
                      message={`当前正在代看 ${props.authContext.target_login} 空间`}
                      description="这里不会显示 root 自己的持仓和复盘。"
                      action={(
                        <Button
                          size="small"
                          onClick={() => void props.onSwitchAccount?.(props.authContext!.actor_login)}
                        >
                          回到 root
                        </Button>
                      )}
                    />
                  </div>
                ) : null}
              </section>
            ) : null}
            {activeTab === "home" ? <MobileHome {...mobileProps} /> : null}
            {activeTab === "stock" ? <MobileStockDetail {...mobileProps} /> : null}
            {activeTab === "operations" ? <MobileOperations {...mobileProps} /> : null}
            {activeTab === "settings" ? <MobileSettings {...mobileProps} /> : null}
          </>
        )}

        <nav className="mobile-bottom-nav" aria-label="移动端导航">
          {navItems.map((item) => (
            <button
              key={item.key}
              type="button"
              className={activeTab === item.key ? "active" : ""}
              onClick={() => activate(item.key)}
            >
              {item.icon}
              <span>{item.label}</span>
            </button>
          ))}
        </nav>
      </div>
    </div>
  );
}
