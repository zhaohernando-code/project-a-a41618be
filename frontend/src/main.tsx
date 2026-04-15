import React from "react";
import ReactDOM from "react-dom/client";
import { ConfigProvider } from "antd";
import "antd/dist/reset.css";
import App from "./App";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ConfigProvider
      theme={{
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
          Table: {
            headerBg: "#f4f8fc",
            headerColor: "#10233c",
          },
          Segmented: {
            trackBg: "#ebf1f7",
            itemSelectedBg: "#0f2340",
            itemSelectedColor: "#ffffff",
          },
        },
      }}
    >
      <App />
    </ConfigProvider>
  </React.StrictMode>,
);
