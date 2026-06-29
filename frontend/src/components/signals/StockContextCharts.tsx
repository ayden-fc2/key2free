"use client";

import { useMemo } from "react";
import ReactECharts from "echarts-for-react";

import type { Bar1dQfq, StockDataContext } from "@/types/signal";

const MA_SERIES = [
  { color: "#ffffff", name: "MA5", window: 5 },
  { color: "#a855f7", name: "MA10", window: 10 },
  { color: "#facc15", name: "MA20", window: 20 },
  { color: "#60a5fa", name: "MA30", window: 30 },
] as const;

const CHART_DARK = {
  axis: "#9ca3af",
  background: "#05070d",
  gridLine: "rgba(148, 163, 184, 0.16)",
  muted: "#94a3b8",
  panelLine: "rgba(148, 163, 184, 0.28)",
  text: "#e5e7eb",
  tooltip: "rgba(8, 13, 23, 0.94)",
  tooltipBorder: "rgba(148, 163, 184, 0.28)",
};

export type TradeChartMarker = {
  date: string;
  price: number;
  kind: "buy" | "sell";
  label?: string;
};

export type TradeChartPriceLine = {
  label: string;
  price: number;
  color?: string;
};

type Props = {
  context: StockDataContext;
  /** 买卖点标记（按交易日定位，落在 K 线主图上） */
  markers?: TradeChartMarker[];
  /** 水平参考线（止损/止盈位等） */
  priceLines?: TradeChartPriceLine[];
  /** 聚焦区间：以 startDate~endDate 为核心，左右各扩展 padBars 个交易日并默认缩放到该范围 */
  focus?: { startDate: string; endDate: string; padBars?: number };
  height?: number;
};

export function StockContextCharts({ context, markers, priceLines, focus, height = 820 }: Props) {
  const chartBars = useMemo(() => {
    const renderable = context.bars_1d_qfq.filter(isRenderableBar);
    if (!focus) {
      return renderable;
    }
    const pad = focus.padBars ?? 100;
    const startIndex = findDateIndex(renderable, focus.startDate);
    const endIndex = findDateIndex(renderable, focus.endDate);
    if (startIndex === -1 || endIndex === -1) {
      return renderable;
    }
    return renderable.slice(Math.max(0, startIndex - pad), Math.min(renderable.length, endIndex + pad + 1));
  }, [context, focus]);

  const chartOption = useMemo(
    () => buildChartOption(chartBars, { markers, priceLines, zoomAll: Boolean(focus) }),
    [chartBars, markers, priceLines, focus],
  );

  return <ReactECharts notMerge option={chartOption} style={{ height, width: "100%" }} />;
}

function buildChartOption(
  bars: Bar1dQfq[],
  extras: { markers?: TradeChartMarker[]; priceLines?: TradeChartPriceLine[]; zoomAll?: boolean },
) {
  const dates = bars.map((item) => item.trade_date);
  const closeValues = bars.map((item) => item.close ?? 0);
  const dif = bars.map((item) => item.macd_dif_12_26_9);
  const dea = bars.map((item) => item.macd_dea_12_26_9);
  const macd = bars.map((item) => item.macd_hist_12_26_9);
  const dataZoom = buildSharedZoom(bars.length, extras.zoomAll ?? false);
  const dateSet = new Set(dates);
  const visibleMarkers = (extras.markers ?? []).filter((item) => dateSet.has(item.date));
  const buyMarkers = visibleMarkers.filter((item) => item.kind === "buy");
  const sellMarkers = visibleMarkers.filter((item) => item.kind === "sell");
  const priceLines = extras.priceLines ?? [];

  return {
    animation: false,
    axisPointer: {
      label: {
        backgroundColor: "#111827",
        borderColor: CHART_DARK.panelLine,
        color: CHART_DARK.text,
      },
      lineStyle: { color: "rgba(226, 232, 240, 0.55)" },
      link: [{ xAxisIndex: "all" }],
    },
    backgroundColor: CHART_DARK.background,
    dataZoom,
    grid: [
      { left: 58, right: 24, top: 44, height: 360 },
      { left: 58, right: 24, top: 460, height: 145 },
      { left: 58, right: 24, top: 650, height: 120 },
    ],
    legend: [
      { inactiveColor: "#475569", right: 12, textStyle: { color: CHART_DARK.text }, top: 0 },
      { inactiveColor: "#475569", right: 12, textStyle: { color: CHART_DARK.text }, top: 428 },
      { inactiveColor: "#475569", right: 12, textStyle: { color: CHART_DARK.text }, top: 618 },
    ],
    title: [
      { left: 0, text: "日K", textStyle: { color: CHART_DARK.text, fontSize: 13 }, top: 0 },
      { left: 0, text: "MACD", textStyle: { color: CHART_DARK.text, fontSize: 13 }, top: 426 },
      { left: 0, text: "成交量", textStyle: { color: CHART_DARK.text, fontSize: 13 }, top: 616 },
    ],
    tooltip: {
      backgroundColor: CHART_DARK.tooltip,
      borderColor: CHART_DARK.tooltipBorder,
      borderWidth: 1,
      extraCssText:
        "box-shadow: 0 18px 42px rgba(0, 0, 0, 0.42); backdrop-filter: blur(4px);",
      formatter: (params: unknown) => formatAxisTooltip(params, bars),
      textStyle: { color: CHART_DARK.text },
      trigger: "axis",
    },
    xAxis: [
      axisOption(dates, 0),
      axisOption(dates, 1),
      axisOption(dates, 2),
    ],
    yAxis: [
      valueAxisOption(0),
      valueAxisOption(1),
      valueAxisOption(2),
    ],
    series: [
      {
        data: bars.map((item) => [item.open, item.close, item.low, item.high]),
        itemStyle: {
          borderColor: "#ef4444",
          borderColor0: "#10b981",
          color: "#ef4444",
          color0: "#10b981",
        },
        markLine:
          priceLines.length === 0
            ? undefined
            : {
                data: priceLines.map((line) => ({
                  label: {
                    color: CHART_DARK.text,
                    formatter: `${line.label} ${line.price.toFixed(2)}`,
                    position: "insideEndTop",
                  },
                  lineStyle: { color: line.color ?? "#cbd5e1", type: "dashed", width: 1.2 },
                  yAxis: line.price,
                })),
                silent: true,
                symbol: "none",
              },
        name: "K线",
        type: "candlestick",
        xAxisIndex: 0,
        yAxisIndex: 0,
      },
      ...MA_SERIES.map((item) => ({
        data: movingAverage(closeValues, item.window),
        lineStyle: { color: item.color, width: 1.4 },
        name: item.name,
        showSymbol: false,
        smooth: true,
        type: "line",
        xAxisIndex: 0,
        yAxisIndex: 0,
      })),
      ...(buyMarkers.length > 0
        ? [
            {
              data: buyMarkers.map((item) => ({
                label: {
                  color: "#f87171",
                  fontWeight: "bold",
                  formatter: item.label ?? "B",
                  position: "bottom",
                  show: true,
                },
                value: [item.date, item.price],
              })),
              itemStyle: { color: "#ef4444" },
              name: "买入",
              symbol: "triangle",
              symbolSize: 13,
              type: "scatter",
              xAxisIndex: 0,
              yAxisIndex: 0,
              z: 10,
            },
          ]
        : []),
      ...(sellMarkers.length > 0
        ? [
            {
              data: sellMarkers.map((item) => ({
                label: {
                  color: "#34d399",
                  fontWeight: "bold",
                  formatter: item.label ?? "S",
                  position: "top",
                  show: true,
                },
                value: [item.date, item.price],
              })),
              itemStyle: { color: "#10b981" },
              name: "卖出",
              symbol: "triangle",
              symbolRotate: 180,
              symbolSize: 13,
              type: "scatter",
              xAxisIndex: 0,
              yAxisIndex: 0,
              z: 10,
            },
          ]
        : []),
      {
        data: macd.map((value) => ({
          itemStyle: { color: (value ?? 0) >= 0 ? "#ef4444" : "#10b981" },
          value,
        })),
        name: "MACD",
        type: "bar",
        xAxisIndex: 1,
        yAxisIndex: 1,
      },
      {
        data: dif,
        lineStyle: { color: "#38bdf8", width: 1.3 },
        name: "DIF",
        showSymbol: false,
        type: "line",
        xAxisIndex: 1,
        yAxisIndex: 1,
      },
      {
        data: dea,
        lineStyle: { color: "#f59e0b", width: 1.3 },
        name: "DEA",
        showSymbol: false,
        type: "line",
        xAxisIndex: 1,
        yAxisIndex: 1,
      },
      {
        data: bars.map((item) => ({
          itemStyle: {
            color: (item.close ?? 0) >= (item.open ?? 0) ? "#ef4444" : "#10b981",
          },
          value: item.volume ?? 0,
        })),
        name: "成交量",
        type: "bar",
        xAxisIndex: 2,
        yAxisIndex: 2,
      },
    ],
  };
}

function buildSharedZoom(length: number, zoomAll: boolean) {
  const startValue = zoomAll ? 0 : Math.max(0, length - 60);
  const endValue = Math.max(0, length - 1);
  return [
    { endValue, startValue, type: "inside", xAxisIndex: [0, 1, 2] },
    {
      backgroundColor: "rgba(15, 23, 42, 0.92)",
      borderColor: CHART_DARK.panelLine,
      bottom: 8,
      dataBackground: {
        areaStyle: { color: "rgba(148, 163, 184, 0.18)" },
        lineStyle: { color: "rgba(148, 163, 184, 0.45)" },
      },
      endValue,
      fillerColor: "rgba(56, 189, 248, 0.16)",
      handleStyle: { borderColor: "#cbd5e1", color: "#64748b" },
      height: 18,
      moveHandleStyle: { color: "#475569" },
      selectedDataBackground: {
        areaStyle: { color: "rgba(56, 189, 248, 0.22)" },
        lineStyle: { color: "rgba(56, 189, 248, 0.5)" },
      },
      startValue,
      textStyle: { color: CHART_DARK.axis },
      xAxisIndex: [0, 1, 2],
    },
  ];
}

function axisOption(dates: string[], gridIndex: number) {
  return {
    axisLabel: { color: CHART_DARK.axis },
    axisLine: { lineStyle: { color: CHART_DARK.panelLine } },
    axisTick: { lineStyle: { color: CHART_DARK.panelLine } },
    data: dates,
    gridIndex,
    scale: true,
    splitLine: { lineStyle: { color: CHART_DARK.gridLine }, show: false },
    type: "category",
  };
}

function valueAxisOption(gridIndex: number) {
  return {
    axisLabel: { color: CHART_DARK.axis },
    axisLine: { lineStyle: { color: CHART_DARK.panelLine } },
    axisTick: { lineStyle: { color: CHART_DARK.panelLine } },
    gridIndex,
    scale: true,
    splitLine: { lineStyle: { color: CHART_DARK.gridLine }, show: true },
    type: "value",
  };
}

type TooltipParam = {
  dataIndex?: number;
  marker?: string;
  seriesName?: string;
  value?: unknown;
};

function formatAxisTooltip(params: unknown, bars: Bar1dQfq[]) {
  const items = Array.isArray(params) ? (params as TooltipParam[]) : [params as TooltipParam];
  const dataIndex = items.find((item) => typeof item?.dataIndex === "number")?.dataIndex;

  if (dataIndex === undefined) {
    return "";
  }

  const bar = bars[dataIndex];
  if (!bar) {
    return "";
  }

  const pctChange = resolvePctChange(bar);
  const pctColor = pctChange === null ? CHART_DARK.muted : pctChange >= 0 ? "#f87171" : "#34d399";
  const secondaryRows = items
    .filter((item) => item.seriesName && item.seriesName !== "K线" && item.seriesName !== "成交量")
    .map((item) => {
      const value = Array.isArray(item.value) ? item.value.at(-1) : item.value;
      return tooltipRow(item.marker ?? "", item.seriesName ?? "", formatNumber(value, 3));
    })
    .join("");

  return `
    <div style="min-width: 190px; padding: 2px 0;">
      <div style="font-weight: 700; margin-bottom: 8px;">${escapeHtml(bar.trade_date)}</div>
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 6px 14px; margin-bottom: 8px;">
        ${tooltipMetric("开", formatNumber(bar.open))}
        ${tooltipMetric("收", formatNumber(bar.close))}
        ${tooltipMetric("高", formatNumber(bar.high))}
        ${tooltipMetric("低", formatNumber(bar.low))}
      </div>
      <div style="display: flex; justify-content: space-between; gap: 16px; margin-bottom: 6px;">
        <span style="color: ${CHART_DARK.muted};">涨跌幅</span>
        <span style="color: ${pctColor}; font-weight: 700;">${formatPct(pctChange)}</span>
      </div>
      <div style="display: flex; justify-content: space-between; gap: 16px; margin-bottom: ${secondaryRows ? "8px" : "0"};">
        <span style="color: ${CHART_DARK.muted};">成交量</span>
        <span>${formatVolume(bar.volume)}</span>
      </div>
      ${secondaryRows ? `<div style="border-top: 1px solid rgba(148, 163, 184, 0.18); padding-top: 8px;">${secondaryRows}</div>` : ""}
    </div>
  `;
}

function tooltipMetric(label: string, value: string) {
  return `
    <div style="display: flex; justify-content: space-between; gap: 8px;">
      <span style="color: ${CHART_DARK.muted};">${label}</span>
      <span>${value}</span>
    </div>
  `;
}

function tooltipRow(marker: string, label: string, value: string) {
  return `
    <div style="display: flex; align-items: center; justify-content: space-between; gap: 16px; line-height: 1.8;">
      <span>${marker}${escapeHtml(label)}</span>
      <span>${value}</span>
    </div>
  `;
}

function resolvePctChange(bar: Bar1dQfq) {
  if (bar.pct_chg !== null) {
    return bar.pct_chg;
  }

  if (bar.preclose === null || bar.preclose === 0 || bar.close === null) {
    return null;
  }

  return ((bar.close - bar.preclose) / bar.preclose) * 100;
}

function formatPct(value: number | null) {
  if (value === null || !Number.isFinite(value)) {
    return "-";
  }

  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

function formatNumber(value: unknown, digits = 2) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "-";
  }

  return value.toFixed(digits);
}

function formatVolume(value: number | null) {
  if (value === null || !Number.isFinite(value)) {
    return "-";
  }

  if (Math.abs(value) >= 100_000_000) {
    return `${(value / 100_000_000).toFixed(2)}亿`;
  }

  if (Math.abs(value) >= 10_000) {
    return `${(value / 10_000).toFixed(2)}万`;
  }

  return value.toFixed(0);
}

function escapeHtml(value: string) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function findDateIndex(bars: Bar1dQfq[], target: string) {
  const exact = bars.findIndex((item) => item.trade_date === target);
  if (exact !== -1) {
    return exact;
  }
  // 目标日不在序列中（如停牌）时取其后最近的交易日
  return bars.findIndex((item) => item.trade_date > target);
}

function isRenderableBar(item: Bar1dQfq) {
  return (
    item.open !== null &&
    item.high !== null &&
    item.low !== null &&
    item.close !== null
  );
}

function movingAverage(values: number[], window: number) {
  return values.map((_, index) => {
    if (index + 1 < window) {
      return null;
    }
    const windowValues = values.slice(index + 1 - window, index + 1);
    return windowValues.reduce((sum, value) => sum + value, 0) / window;
  });
}
