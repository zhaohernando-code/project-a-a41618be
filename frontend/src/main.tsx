import React, { useEffect, useMemo, useState } from "react";
import ReactDOM from "react-dom/client";
import { ConfigProvider, theme as antTheme } from "antd";
import "antd/dist/reset.css";
import App from "./App";
import "./styles.css";

type ThemeMode = "light" | "dark";

const themeStorageKey = "ashare-dashboard-theme";

function readInitialTheme(): ThemeMode {
  if (typeof window === "undefined") {
    return "light";
  }
  const stored = window.localStorage.getItem(themeStorageKey);
  if (stored === "light" || stored === "dark") {
    return stored;
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function Root() {
  const [themeMode, setThemeMode] = useState<ThemeMode>(() => readInitialTheme());

  useEffect(() => {
    document.documentElement.style.colorScheme = themeMode;
    window.localStorage.setItem(themeStorageKey, themeMode);
  }, [themeMode]);

  const themeConfig = useMemo(
    () => ({
      algorithm: themeMode === "dark" ? antTheme.darkAlgorithm : antTheme.defaultAlgorithm,
      token: {
        colorPrimary: "#0a5bff",
        colorSuccess: "#0b8f63",
        colorWarning: "#d48700",
        colorError: "#cc514b",
        colorInfo: "#0a5bff",
        borderRadius: 18,
        borderRadiusLG: 24,
        fontFamily:
          '"Avenir Next", "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif',
      },
      components: {
        Card: {
          headerFontSize: 16,
        },
        Table: themeMode === "dark"
          ? {
              headerBg: "#12233e",
              headerColor: "#f2f6fb",
            }
          : {
              headerBg: "#f4f8fc",
              headerColor: "#10233c",
            },
        Tabs: {
          itemSelectedColor: "#0a5bff",
          itemActiveColor: "#0a5bff",
        },
      },
    }),
    [themeMode],
  );

  return (
    <ConfigProvider theme={themeConfig}>
      <App
        themeMode={themeMode}
        onToggleTheme={() => setThemeMode((current) => (current === "dark" ? "light" : "dark"))}
      />
    </ConfigProvider>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>,
);
