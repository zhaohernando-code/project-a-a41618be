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
    const chartPoints = points
      .map((point) => ({
        close: Number(point.close_price),
        observedAt: point.observed_at,
      }))
      .filter((point) => Number.isFinite(point.close));
    const closes = chartPoints.map((point) => point.close);
    if (chartPoints.length < 2) {
      return;
    }
    const min = Math.min(...closes);
    const max = Math.max(...closes);
    const range = Math.max(max - min, Math.abs(max) * 0.01, 1);
    const padding = range * 0.08;
    const chart = init(chartRef.current, undefined, {
      renderer: "canvas",
      width: chartRef.current.clientWidth,
      height: chartRef.current.clientHeight,
    });
    const up = closes[closes.length - 1] >= closes[0];
    chart.setOption({
      animation: false,
      backgroundColor: "transparent",
      grid: { top: 0, right: 0, bottom: 0, left: 0, containLabel: false },
      tooltip: { show: false },
      xAxis: { type: "category", data: chartPoints.map((point) => point.observedAt), show: false, boundaryGap: false },
      yAxis: {
        type: "value",
        show: false,
        scale: true,
        min: min - padding,
        max: max + padding,
        boundaryGap: [0, 0],
      },
      series: [{
        type: "line",
        data: closes,
        smooth: true,
        showSymbol: false,
        silent: true,
        lineStyle: { width: 1.6, color: up ? "#e14f4f" : "#0b8f63" },
        areaStyle: { color: up ? "rgba(225,79,79,0.06)" : "rgba(11,143,99,0.06)" },
      }],
    });
    const resizeObserver = new ResizeObserver(() => {
      chart.resize({
        width: chartRef.current?.clientWidth,
        height: chartRef.current?.clientHeight,
      });
    });
    resizeObserver.observe(chartRef.current);
    return () => {
      resizeObserver.disconnect();
      chart.dispose();
    };
  }, [points]);

  if (points.length < 2) {
    return null;
  }

  return <div className="mobile-mini-trend" ref={chartRef} aria-hidden="true" />;
}
