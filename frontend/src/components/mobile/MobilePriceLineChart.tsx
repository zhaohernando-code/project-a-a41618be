import { useEffect, useRef } from "react";
import { init } from "echarts";
import type { PricePointView } from "../../types";

function formatAxisPrice(value: number): string {
  if (Math.abs(value) >= 100) return value.toFixed(0);
  if (Math.abs(value) >= 10) return value.toFixed(1);
  return value.toFixed(2);
}

export function MobilePriceLineChart({ points }: { points: PricePointView[] }) {
  const chartRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!chartRef.current || points.length < 2) {
      return;
    }
    const chartPoints = points
      .slice(-60)
      .map((point) => ({
        close: Number(point.close_price),
        observedAt: point.observed_at,
      }))
      .filter((point) => Number.isFinite(point.close));
    if (chartPoints.length < 2) {
      return;
    }
    const closes = chartPoints.map((point) => point.close);
    const min = Math.min(...closes);
    const max = Math.max(...closes);
    const range = Math.max(max - min, Math.abs(max) * 0.02, 1);
    const padding = range * 0.12;
    const dayCounts = chartPoints.reduce((counts, point) => {
      const parsed = new Date(point.observedAt);
      if (!Number.isNaN(parsed.getTime())) {
        const dayKey = parsed.toLocaleDateString("zh-CN");
        counts.set(dayKey, (counts.get(dayKey) ?? 0) + 1);
      }
      return counts;
    }, new Map<string, number>());
    const dates = chartPoints.map((point) => {
      const parsed = new Date(point.observedAt);
      if (Number.isNaN(parsed.getTime())) return point.observedAt;
      const dayKey = parsed.toLocaleDateString("zh-CN");
      if ((dayCounts.get(dayKey) ?? 0) > 1) {
        return parsed.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
      }
      return parsed.toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" });
    });
    const styles = getComputedStyle(chartRef.current);
    const accentColor = styles.getPropertyValue("--mobile-color-accent").trim() || "#0a63ff";
    const mutedColor = styles.getPropertyValue("--mobile-color-muted").trim() || "#667794";
    const gridColor = styles.getPropertyValue("--mobile-chart-grid").trim() || "rgba(103, 121, 148, 0.14)";
    const chart = init(chartRef.current, undefined, {
      renderer: "canvas",
      width: chartRef.current.clientWidth,
      height: chartRef.current.clientHeight,
    });
    chart.setOption({
      animation: false,
      backgroundColor: "transparent",
      grid: { top: 6, right: 4, bottom: 18, left: 28, containLabel: false },
      tooltip: { show: false },
      xAxis: {
        type: "category",
        data: dates,
        boundaryGap: false,
        axisTick: { show: false },
        axisLine: { lineStyle: { color: gridColor } },
        axisLabel: {
          color: mutedColor,
          fontSize: 10,
          hideOverlap: true,
          interval: Math.max(0, Math.floor(dates.length / 4) - 1),
        },
        splitLine: { show: false },
      },
      yAxis: {
        type: "value",
        min: min - padding,
        max: max + padding,
        splitNumber: 3,
        axisTick: { show: false },
        axisLine: { show: false },
        axisLabel: {
          color: mutedColor,
          fontSize: 9,
          formatter: (value: number) => formatAxisPrice(value),
        },
        splitLine: { lineStyle: { color: gridColor } },
      },
      series: [{
        type: "line",
        data: closes,
        smooth: true,
        showSymbol: false,
        symbol: "circle",
        symbolSize: 7,
        emphasis: { disabled: true },
        lineStyle: { width: 1.8, color: accentColor },
        areaStyle: { color: "rgba(10, 99, 255, 0.05)" },
        markPoint: {
          symbol: "circle",
          symbolSize: 9,
          label: { show: false },
          data: [
            { coord: [dates[dates.length - 1], closes[closes.length - 1]] },
          ],
          itemStyle: { color: accentColor },
        },
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

  return <div className="mobile-price-line-chart" ref={chartRef} aria-hidden="true" />;
}
