import React, { useEffect, useMemo, useState } from "react";
import ReactDOM from "react-dom/client";
import { ConfigProvider, theme as antTheme } from "antd";
import "antd/dist/reset.css";
import App from "./App";
import "./styles.css";
import "./mobile.css";

type ThemeMode = "light" | "dark";

const themeStorageKey = "ashare-dashboard-theme";
const releaseReloadMarkerKey = "ashare-dashboard-release-reload";
const releaseAssetPattern = /assets\/index-[^"'?#\s]+\.(?:js|css)/g;
const releaseCheckIntervalMs = 60_000;

function extractReleaseAssets(html: string): string[] {
  return Array.from(new Set(html.match(releaseAssetPattern) ?? []));
}

function normalizeReleaseAsset(ref: string): string {
  if (typeof window === "undefined") {
    return ref;
  }
  return new URL(ref, window.location.origin).pathname;
}

function currentReleaseScript(): string | null {
  if (typeof import.meta.url !== "string") {
    return null;
  }
  const match = import.meta.url.match(/assets\/index-[^"'?#\s]+\.js/);
  return match?.[0] ?? null;
}

async function refreshWhenNewReleaseIsAvailable(): Promise<void> {
  if (typeof window === "undefined") {
    return;
  }
  const currentScript = currentReleaseScript();
  if (!currentScript) {
    return;
  }
  try {
    const response = await fetch(window.location.href, {
      cache: "no-store",
      headers: {
        "Cache-Control": "no-cache",
        Pragma: "no-cache",
      },
    });
    if (!response.ok) {
      return;
    }
    const latestHtml = await response.text();
    const latestScript = extractReleaseAssets(latestHtml).find((asset) => asset.endsWith(".js"));
    if (!latestScript) {
      return;
    }
    const currentAssetPath = normalizeReleaseAsset(currentScript);
    const latestAssetPath = normalizeReleaseAsset(latestScript);
    if (currentAssetPath === latestAssetPath) {
      window.sessionStorage.removeItem(releaseReloadMarkerKey);
      return;
    }
    const reloadMarker = `${currentAssetPath}->${latestAssetPath}`;
    if (window.sessionStorage.getItem(releaseReloadMarkerKey) === reloadMarker) {
      return;
    }
    window.sessionStorage.setItem(releaseReloadMarkerKey, reloadMarker);
    window.location.reload();
  } catch {
    // Ignore transient network/auth issues and retry on the next focus/interval.
  }
}

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
    document.documentElement.dataset.theme = themeMode;
    document.body.dataset.theme = themeMode;
    window.localStorage.setItem(themeStorageKey, themeMode);
  }, [themeMode]);

  useEffect(() => {
    void refreshWhenNewReleaseIsAvailable();

    const intervalId = window.setInterval(() => {
      void refreshWhenNewReleaseIsAvailable();
    }, releaseCheckIntervalMs);
    const handleFocus = () => {
      void refreshWhenNewReleaseIsAvailable();
    };
    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        void refreshWhenNewReleaseIsAvailable();
      }
    };

    window.addEventListener("focus", handleFocus);
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      window.clearInterval(intervalId);
      window.removeEventListener("focus", handleFocus);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, []);

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
