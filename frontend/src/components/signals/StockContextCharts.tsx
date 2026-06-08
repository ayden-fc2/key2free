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

type Props = {
  context: StockDataContext;
};

export function StockContextCharts({ context }: Props) {
  const chartBars = useMemo(
    () => context.bars_1d_qfq.filter(isRenderableBar),
    [context],
  );
  const chartOption = useMemo(() => buildChartOption(chartBars), [chartBars]);

  return <ReactECharts option={chartOption} style={{ height: 820, width: "100%" }} />;
}

function buildChartOption(bars: Bar1dQfq[]) {
  const dates = bars.map((item) => item.trade_date);
  const closeValues = bars.map((item) => item.close ?? 0);
  const dif = subtractSeries(ema(closeValues, 12), ema(closeValues, 26));
  const dea = ema(dif, 9);
  const macd = subtractSeries(dif, dea).map((value) => value * 2);
  const dataZoom = buildSharedZoom(bars.length);

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
    tooltip: { trigger: "axis" },
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

function buildSharedZoom(length: number) {
  const startValue = Math.max(0, length - 60);
  const endValue = Math.max(0, length - 1);
  return [
    { endValue, startValue, type: "inside", xAxisIndex: [0, 1, 2] },
    { bottom: 8, endValue, height: 18, startValue, xAxisIndex: [0, 1, 2] },
  ];
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
