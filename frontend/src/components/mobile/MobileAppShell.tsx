import {
  BarChartOutlined,
  HomeOutlined,
  LineChartOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import { Alert, Skeleton } from "antd";
import { useState } from "react";
import type { MobileAppShellProps, MobileTabKey } from "./types";
import { MobileHome } from "./MobileHome";
import { MobileStockDetail } from "./MobileStockDetail";
import { MobileOperations } from "./MobileOperations";
import { MobileSettings } from "./MobileSettings";

const navItems: Array<{ key: MobileTabKey; label: string; icon: React.ReactNode }> = [
  { key: "home", label: "首页", icon: <HomeOutlined /> },
  { key: "stock", label: "单票", icon: <LineChartOutlined /> },
  { key: "operations", label: "复盘", icon: <BarChartOutlined /> },
  { key: "settings", label: "设置", icon: <SettingOutlined /> },
];

export function MobileAppShell(props: MobileAppShellProps) {
  const [activeTab, setActiveTab] = useState<MobileTabKey>("home");

  function activate(tab: MobileTabKey) {
    setActiveTab(tab);
    props.onTabChange(tab);
    if (tab === "operations") {
      void props.onLoadOperations();
    }
  }

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
            {activeTab === "home" ? <MobileHome {...props} /> : null}
            {activeTab === "stock" ? <MobileStockDetail {...props} /> : null}
            {activeTab === "operations" ? <MobileOperations {...props} /> : null}
            {activeTab === "settings" ? <MobileSettings {...props} /> : null}
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
