"use client";

import { useMemo } from "react";
import ReactECharts from "echarts-for-react";

import type { Bar1dQfq, StockDataContext } from "@/types/signal";

const MA_SERIES = [
  { color: "#ffffff", name: "MA5", window: 5 },
  { color: "#a855f7", name: "MA10", window: 10 },
  { color: "#facc15", name: "MA20", window: 20 },
  { color: "#2563eb", name: "MA30", window: 30 },
] as const;

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
  const dif = subtractSeries(ema(closeValues, 12), ema(closeValues, 26));
  const dea = ema(dif, 9);
  const macd = subtractSeries(dif, dea).map((value) => value * 2);
  const dataZoom = buildSharedZoom(bars.length, extras.zoomAll ?? false);
  const dateSet = new Set(dates);
  const visibleMarkers = (extras.markers ?? []).filter((item) => dateSet.has(item.date));
  const buyMarkers = visibleMarkers.filter((item) => item.kind === "buy");
  const sellMarkers = visibleMarkers.filter((item) => item.kind === "sell");
  const priceLines = extras.priceLines ?? [];

  return {
    animation: false,
    axisPointer: { link: [{ xAxisIndex: "all" }] },
    backgroundColor: "#ffffff",
    dataZoom,
    grid: [
      { left: 58, right: 24, top: 44, height: 360 },
      { left: 58, right: 24, top: 460, height: 145 },
      { left: 58, right: 24, top: 650, height: 120 },
    ],
    legend: [
      { right: 12, top: 0 },
      { right: 12, top: 428 },
      { right: 12, top: 618 },
    ],
    title: [
      { left: 0, text: "日K", textStyle: { fontSize: 13 }, top: 0 },
      { left: 0, text: "MACD", textStyle: { fontSize: 13 }, top: 426 },
      { left: 0, text: "成交量", textStyle: { fontSize: 13 }, top: 616 },
    ],
    tooltip: {
      backgroundColor: "rgba(255, 255, 255, 0.72)",
      borderColor: "rgba(15, 23, 42, 0.14)",
      borderWidth: 1,
      extraCssText:
        "box-shadow: 0 10px 30px rgba(15, 23, 42, 0.14); backdrop-filter: blur(4px);",
      textStyle: { color: "#111827" },
      trigger: "axis",
    },
    xAxis: [
      { data: dates, gridIndex: 0, scale: true, type: "category" },
      { data: dates, gridIndex: 1, scale: true, type: "category" },
      { data: dates, gridIndex: 2, scale: true, type: "category" },
    ],
    yAxis: [
      { gridIndex: 0, scale: true, type: "value" },
      { gridIndex: 1, scale: true, type: "value" },
      { gridIndex: 2, scale: true, type: "value" },
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
                    formatter: `${line.label} ${line.price.toFixed(2)}`,
                    position: "insideEndTop",
                  },
                  lineStyle: { color: line.color ?? "#94a3b8", type: "dashed", width: 1.2 },
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
                  color: "#b91c1c",
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
                  color: "#047857",
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
          itemStyle: { color: value >= 0 ? "#ef4444" : "#10b981" },
          value,
        })),
        name: "MACD",
        type: "bar",
        xAxisIndex: 1,
        yAxisIndex: 1,
      },
      { data: dif, name: "DIF", showSymbol: false, type: "line", xAxisIndex: 1, yAxisIndex: 1 },
      { data: dea, name: "DEA", showSymbol: false, type: "line", xAxisIndex: 1, yAxisIndex: 1 },
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
    { bottom: 8, endValue, height: 18, startValue, xAxisIndex: [0, 1, 2] },
  ];
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

function ema(values: number[], window: number) {
  if (values.length === 0) {
    return [];
  }
  const alpha = 2 / (window + 1);
  const result = [values[0]];
  for (let index = 1; index < values.length; index += 1) {
    result.push(values[index] * alpha + result[index - 1] * (1 - alpha));
  }
  return result;
}

function subtractSeries(left: number[], right: number[]) {
  return left.map((value, index) => value - (right[index] ?? 0));
}
