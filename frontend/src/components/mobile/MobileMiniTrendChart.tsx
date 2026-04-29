import { useEffect, useRef } from "react";
import { init } from "echarts";
import type { CandidateWorkspaceRow } from "../../types";

export function MobileMiniTrendChart({ row }: { row: CandidateWorkspaceRow }) {
  const chartRef = useRef<HTMLDivElement | null>(null);
  const points = row.candidate?.price_chart ?? [];

  useEffect(() => {
    if (!chartRef.current || points.length < 2) {
      return;
    }
    const closes = points.map((point) => Number(point.close_price)).filter((value) => Number.isFinite(value));
    if (closes.length < 2) {
      return;
    }
    const chart = init(chartRef.current, undefined, { renderer: "canvas" });
    const up = closes[closes.length - 1] >= closes[0];
    chart.setOption({
      animation: false,
      backgroundColor: "transparent",
      grid: { top: 4, right: 2, bottom: 4, left: 2 },
      tooltip: { show: false },
      xAxis: { type: "category", data: points.map((point) => point.observed_at), show: false, boundaryGap: false },
      yAxis: { type: "value", show: false, scale: true },
      series: [{
        type: "line",
        data: closes,
        smooth: true,
        showSymbol: false,
        silent: true,
        lineStyle: { width: 3, color: up ? "#e14f4f" : "#0b8f63" },
        areaStyle: { color: up ? "rgba(225,79,79,0.12)" : "rgba(11,143,99,0.12)" },
      }],
    });
    return () => chart.dispose();
  }, [points]);

  if (points.length < 2) {
    return null;
  }

  return <div className="mobile-mini-trend" ref={chartRef} aria-hidden="true" />;
}
