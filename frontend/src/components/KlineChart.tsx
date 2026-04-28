import { useRef, useEffect } from "react";
import { Empty } from "antd";
import { init } from "echarts";
import type { PricePointView } from "../types";
import { formatNumber, formatPercent } from "../utils/format";



export function KlineChart({ points, compact = false }: { points: PricePointView[]; compact?: boolean }) {
  const chartRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!chartRef.current || points.length === 0) {
      return;
    }

    const container = chartRef.current;
    const chart = init(container, undefined, { renderer: "canvas" });
    const styles = getComputedStyle(container);
    const textColor = styles.getPropertyValue("--text-main").trim() || "#10233c";
    const mutedColor = styles.getPropertyValue("--text-muted").trim() || "#64748b";
    const lineColor = styles.getPropertyValue("--line").trim() || "rgba(16, 35, 60, 0.08)";
    const upColor = "#d14343";
    const downColor = "#0b8f63";
    const accentColor = styles.getPropertyValue("--brand").trim() || "#0a5bff";
    const goldColor = "#d48700";
    const dates = points.map((point) => {
      const parsed = new Date(point.observed_at);
      return Number.isNaN(parsed.getTime())
        ? point.observed_at
        : parsed.toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" });
    });
    const movingAverage = (windowSize: number): Array<number | "-"> =>
      points.map((_, index) => {
        if (index < windowSize - 1) {
          return "-";
        }
        const slice = points.slice(index - windowSize + 1, index + 1);
        const total = slice.reduce((sum, point) => sum + point.close_price, 0);
        return Number((total / slice.length).toFixed(2));
      });
    const ma5 = movingAverage(5);
    const ma10 = movingAverage(10);

    chart.setOption({
      animation: false,
      backgroundColor: "transparent",
      axisPointer: {
        link: [{ xAxisIndex: "all" }],
      },
      tooltip: {
        trigger: "axis",
        confine: true,
        axisPointer: {
          type: "cross",
          label: {
            backgroundColor: "rgba(15, 35, 64, 0.9)",
          },
        },
        backgroundColor: "rgba(15, 35, 64, 0.92)",
        borderWidth: 0,
        textStyle: { color: "#f8fbff" },
        extraCssText: "border-radius: 12px; box-shadow: 0 18px 36px rgba(10,24,42,0.24);",
        formatter: (rawParams: unknown) => {
          const params = Array.isArray(rawParams)
            ? rawParams as Array<{ dataIndex?: number }>
            : [rawParams as { dataIndex?: number }];
          const index = params[0]?.dataIndex ?? 0;
          const point = points[index];
          if (!point) {
            return "";
          }
          const previous = points[index - 1];
          const changePct = previous?.close_price
            ? point.close_price / previous.close_price - 1
            : null;
          return [
            `<div style="margin-bottom:6px;font-weight:700;">${dates[index] ?? point.observed_at}</div>`,
            `开盘 ${formatNumber(point.open_price)} / 收盘 ${formatNumber(point.close_price)}`,
            `最高 ${formatNumber(point.high_price)} / 最低 ${formatNumber(point.low_price)}`,
            `成交量 ${formatNumber(point.volume)}`,
            `日变化 ${formatPercent(changePct)}`,
          ].join("<br/>");
        },
      },
      grid: compact
        ? [
            { left: 10, right: 12, top: 10, height: "66%" },
            { left: 10, right: 12, top: "79%", height: "13%" },
          ]
        : [
            { left: 14, right: 16, top: 18, height: "64%" },
            { left: 14, right: 16, top: "80%", height: "12%" },
          ],
      xAxis: [
        {
          type: "category",
          data: dates,
          boundaryGap: true,
          axisLine: { lineStyle: { color: lineColor } },
          axisTick: { show: false },
          axisLabel: { color: mutedColor, showMaxLabel: true, showMinLabel: true },
          splitLine: { show: false },
        },
        {
          type: "category",
          gridIndex: 1,
          data: dates,
          boundaryGap: true,
          axisLine: { lineStyle: { color: lineColor } },
          axisTick: { show: false },
          axisLabel: { show: false },
          splitLine: { show: false },
        },
      ],
      yAxis: [
        {
          scale: true,
          splitNumber: 4,
          axisLine: { show: false },
          axisTick: { show: false },
          axisLabel: { color: mutedColor },
          splitLine: { lineStyle: { color: lineColor } },
        },
        {
          scale: true,
          gridIndex: 1,
          splitNumber: 2,
          axisLine: { show: false },
          axisTick: { show: false },
          axisLabel: {
            color: mutedColor,
            formatter: (value: number) => `${Math.round(value / 10000)}万`,
          },
          splitLine: { show: false },
        },
      ],
      dataZoom: [
        {
          type: "inside",
          xAxisIndex: [0, 1],
          start: points.length > 24 ? Math.max(0, 100 - (24 / points.length) * 100) : 0,
          end: 100,
        },
        ...(
          compact
            ? []
            : [{
                type: "slider",
                xAxisIndex: [0, 1],
                bottom: 8,
                height: 20,
                borderColor: "transparent",
                backgroundColor: "rgba(16, 35, 60, 0.06)",
                fillerColor: "rgba(10, 91, 255, 0.14)",
                dataBackground: {
                  lineStyle: { color: mutedColor, opacity: 0.45 },
                  areaStyle: { color: "rgba(10, 91, 255, 0.04)" },
                },
                handleStyle: {
                  color: accentColor,
                  borderColor: accentColor,
                },
                textStyle: { color: mutedColor },
              }]
        ),
      ],
      series: [
        {
          name: "K线",
          type: "candlestick",
          data: points.map((point) => [point.open_price, point.close_price, point.low_price, point.high_price]),
          itemStyle: {
            color: upColor,
            color0: downColor,
            borderColor: upColor,
            borderColor0: downColor,
          },
          emphasis: {
            itemStyle: {
              borderWidth: 2,
            },
          },
        },
        {
          name: "MA5",
          type: "line",
          data: ma5,
          showSymbol: false,
          smooth: true,
          lineStyle: {
            width: 1.5,
            color: accentColor,
            opacity: 0.9,
          },
        },
        {
          name: "MA10",
          type: "line",
          data: ma10,
          showSymbol: false,
          smooth: true,
          lineStyle: {
            width: 1.5,
            color: goldColor,
            opacity: 0.8,
          },
        },
        {
          name: "成交量",
          type: "bar",
          xAxisIndex: 1,
          yAxisIndex: 1,
          data: points.map((point) => ({
            value: point.volume,
            itemStyle: {
              color: point.close_price >= point.open_price ? "rgba(209, 67, 67, 0.75)" : "rgba(11, 143, 99, 0.72)",
            },
          })),
          barMaxWidth: 12,
        },
      ],
      textStyle: {
        color: textColor,
      },
    });

    const resize = () => chart.resize();
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      chart.dispose();
    };
  }, [compact, points]);

  if (points.length === 0) {
    return <Empty description="暂无价格轨迹" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  return <div ref={chartRef} className={`echarts-kline${compact ? " echarts-kline-compact" : ""}`} />;
}

