"use client";

import { useEffect, useMemo, useState } from "react";
import ReactECharts from "echarts-for-react";
import { Modal, Select, Space, Spin, Table, Tag, message } from "antd";
import type { ColumnsType } from "antd/es/table";

import {
  StockContextCharts,
  type TradeChartMarker,
  type TradeChartPriceLine,
} from "@/components/signals/StockContextCharts";
import { getBacktestDetail } from "@/lib/api/backtests";
import { getStockDataContexts } from "@/lib/api/signals";
import type { BacktestDetail, BacktestEquityCurves, BacktestTrade } from "@/types/backtest";
import type { StockDataContext } from "@/types/signal";

const SELL_REASON_LABELS: Record<string, string> = {
  stop_loss: "止损",
  take_profit_partial: "止盈减半",
  take_profit_final: "止盈清仓",
};

type Props = {
  taskId: number | null;
  open: boolean;
  onClose: () => void;
};

export function BacktestDetailModal({ taskId, open, onClose }: Props) {
  const [detail, setDetail] = useState<BacktestDetail | null>(null);
  const [curves, setCurves] = useState<BacktestEquityCurves | null>(null);
  const [runNo, setRunNo] = useState(1);
  const [loading, setLoading] = useState(false);
  const [selectedTradeKey, setSelectedTradeKey] = useState<string | null>(null);
  const [contextCache, setContextCache] = useState<Record<string, StockDataContext>>({});
  const [contextLoading, setContextLoading] = useState(false);
  const [messageApi, contextHolder] = message.useMessage();

  useEffect(() => {
    if (!open || taskId === null) {
      return;
    }
    setDetail(null);
    setCurves(null);
    setRunNo(1);
    setSelectedTradeKey(null);
    setContextCache({});
    setLoading(true);
    getBacktestDetail(taskId, 1, true)
      .then((data) => {
        setDetail(data);
        setCurves(data.equity_curves);
      })
      .catch((error) => messageApi.error(error instanceof Error ? error.message : "回测详情加载失败"))
      .finally(() => setLoading(false));
  }, [open, taskId, messageApi]);

  async function switchRun(nextRun: number) {
    if (taskId === null) {
      return;
    }
    setRunNo(nextRun);
    setSelectedTradeKey(null);
    setLoading(true);
    try {
      const data = await getBacktestDetail(taskId, nextRun, false);
      setDetail(data);
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "切换轮次失败");
    } finally {
      setLoading(false);
    }
  }

  const trades = detail?.trades ?? [];
  const selectedTrade = trades.find((item) => tradeKey(item) === selectedTradeKey) ?? null;

  useEffect(() => {
    if (selectedTrade === null || contextCache[selectedTrade.code] !== undefined) {
      return;
    }
    const code = selectedTrade.code;
    setContextLoading(true);
    getStockDataContexts({ codes: [code] })
      .then((result) => {
        const context = result.contexts.find((item) => item.code === code);
        if (context !== undefined) {
          setContextCache((cache) => ({ ...cache, [code]: context }));
        }
      })
      .catch((error) => messageApi.error(error instanceof Error ? error.message : "K线数据加载失败"))
      .finally(() => setContextLoading(false));
  }, [selectedTrade, contextCache, messageApi]);

  const curveOption = useMemo(() => buildCurveOption(curves, runNo), [curves, runNo]);
  const realizedPnl = trades.reduce((sum, item) => sum + (item.total_pnl ?? 0), 0);

  const tradeColumns: ColumnsType<BacktestTrade> = [
    { dataIndex: "buy_date", title: "买入日", width: 110 },
    { dataIndex: "code", title: "代码", width: 110 },
    { dataIndex: "code_name", render: (value: string | null) => value ?? "-", title: "名称", width: 110 },
    {
      render: (_value, record) => record.buy_price.toFixed(3),
      title: "买入价",
      width: 90,
    },
    { dataIndex: "quantity", title: "股数", width: 80 },
    {
      render: (_value, record) =>
        record.sells
          .map(
            (sell) =>
              `${sell.trade_date.slice(5)} ${SELL_REASON_LABELS[sell.reason ?? ""] ?? sell.reason ?? "卖出"} ${sell.quantity}股@${sell.sell_price.toFixed(2)}`,
          )
          .join("；") || "—",
      title: "卖出操作",
    },
    { dataIndex: "sell_count", title: "笔数", width: 60 },
    {
      render: (_value, record) =>
        record.total_pnl === null ? (
          "-"
        ) : (
          <span style={{ color: record.total_pnl >= 0 ? "#dc2626" : "#059669", fontWeight: 600 }}>
            {record.total_pnl >= 0 ? "+" : ""}
            {record.total_pnl.toFixed(0)}
          </span>
        ),
      sorter: (left, right) => (left.total_pnl ?? 0) - (right.total_pnl ?? 0),
      title: "盈亏",
      width: 90,
    },
    {
      render: (_value, record) => (record.holding_days === null ? "-" : `${record.holding_days} 天`),
      title: "持股时间",
      width: 90,
    },
    {
      render: (_value, record) =>
        record.closed ? <Tag color="default">已平仓</Tag> : <Tag color="blue">持有中</Tag>,
      title: "状态",
      width: 90,
    },
  ];

  const chartMarkers: TradeChartMarker[] = selectedTrade
    ? [
        {
          date: selectedTrade.buy_date,
          kind: "buy",
          label: `买 ${selectedTrade.buy_price.toFixed(2)}`,
          price: selectedTrade.buy_price,
        },
        ...selectedTrade.sells.map<TradeChartMarker>((sell) => ({
          date: sell.trade_date,
          kind: "sell",
          label: `${SELL_REASON_LABELS[sell.reason ?? ""] ?? "卖"} ${sell.sell_price.toFixed(2)}`,
          price: sell.sell_price,
        })),
      ]
    : [];

  const chartPriceLines: TradeChartPriceLine[] = selectedTrade
    ? [
        ...(selectedTrade.signal.stop_losses ?? []).map((price, index) => ({
          color: "#f97316",
          label: `止损${index + 1}`,
          price,
        })),
        ...(selectedTrade.signal.take_profits ?? []).map((price, index) => ({
          color: "#3b82f6",
          label: `止盈${index + 1}`,
          price,
        })),
      ]
    : [];

  const selectedContext = selectedTrade === null ? null : contextCache[selectedTrade.code] ?? null;

  return (
    <Modal
      footer={null}
      open={open}
      style={{ maxWidth: 1480, top: 16 }}
      title={`回测详情 - 任务 ${taskId ?? "-"}`}
      width="94vw"
      onCancel={onClose}
    >
      {contextHolder}
      <Spin spinning={loading}>
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <section>
            <div style={{ alignItems: "center", display: "flex", justifyContent: "space-between" }}>
              <div className="placeholder-title">随机回测收益率曲线（50 轮）</div>
              <Space>
                <span>查看轮次</span>
                <Select
                  options={(detail?.available_runs ?? [1]).map((value) => ({
                    label: `第 ${value} 轮`,
                    value,
                  }))}
                  size="small"
                  style={{ width: 110 }}
                  value={runNo}
                  onChange={switchRun}
                />
                <span>
                  本轮交易 {trades.length} 笔 / 已实现盈亏{" "}
                  <strong style={{ color: realizedPnl >= 0 ? "#dc2626" : "#059669" }}>
                    {realizedPnl >= 0 ? "+" : ""}
                    {realizedPnl.toFixed(0)}
                  </strong>
                </span>
              </Space>
            </div>
            {curves === null ? (
              <div className="empty-chart">暂无收益率曲线</div>
            ) : (
              <ReactECharts notMerge option={curveOption} style={{ height: 320, width: "100%" }} />
            )}
          </section>
          <section>
            <div className="placeholder-title" style={{ marginBottom: 8 }}>
              交易明细（第 {runNo} 轮，按买入时间排序，点击行查看K线）
            </div>
            <Table
              columns={tradeColumns}
              dataSource={trades}
              onRow={(record) => ({
                onClick: () => setSelectedTradeKey(tradeKey(record)),
                style: { cursor: "pointer" },
              })}
              pagination={{ pageSize: 10, showSizeChanger: true }}
              rowClassName={(record) => (tradeKey(record) === selectedTradeKey ? "selected-row" : "")}
              rowKey={tradeKey}
              scroll={{ x: 1200 }}
              size="small"
            />
          </section>
          <section>
            <div className="placeholder-title" style={{ marginBottom: 8 }}>
              {selectedTrade
                ? `${selectedTrade.code} ${selectedTrade.code_name ?? ""} 买卖区间 ±100 交易日`
                : "点击上方交易行查看买卖区间K线"}
            </div>
            {selectedTrade === null ? null : contextLoading && selectedContext === null ? (
              <div className="empty-chart">K线加载中...</div>
            ) : selectedContext === null ? (
              <div className="empty-chart">暂无可渲染的股票上下文</div>
            ) : (
              <StockContextCharts
                context={selectedContext}
                focus={{
                  endDate: selectedTrade.last_sell_date ?? selectedTrade.buy_date,
                  padBars: 100,
                  startDate: selectedTrade.buy_date,
                }}
                markers={chartMarkers}
                priceLines={chartPriceLines}
              />
            )}
          </section>
        </div>
      </Spin>
    </Modal>
  );
}

function tradeKey(trade: BacktestTrade) {
  return `${trade.code}:${trade.buy_date}`;
}

function buildCurveOption(curves: BacktestEquityCurves | null, highlightRun: number) {
  if (curves === null) {
    return {};
  }
  return {
    animation: false,
    backgroundColor: "#ffffff",
    grid: { bottom: 40, left: 64, right: 24, top: 28 },
    series: curves.runs.map((run) => {
      const highlighted = run.run_no === highlightRun;
      return {
        data: run.returns.map((value) => Math.round(value * 10000) / 100),
        emphasis: { focus: "series" as const },
        lineStyle: {
          color: highlighted ? "#2563eb" : "rgba(148, 163, 184, 0.45)",
          width: highlighted ? 2.2 : 1,
        },
        name: `第${run.run_no}轮`,
        showSymbol: false,
        type: "line" as const,
        z: highlighted ? 10 : 1,
      };
    }),
    tooltip: {
      formatter: (params: { seriesName: string; value: number; name: string }[] | { seriesName: string; value: number; name: string }) => {
        const items = Array.isArray(params) ? params : [params];
        if (items.length === 0) {
          return "";
        }
        const shown = [...items].sort((left, right) => right.value - left.value).slice(0, 8);
        const rest = items.length - shown.length;
        return [
          items[0].name,
          ...shown.map((item) => `${item.seriesName}: ${item.value.toFixed(2)}%`),
          rest > 0 ? `…其余 ${rest} 轮` : "",
        ]
          .filter(Boolean)
          .join("<br/>");
      },
      trigger: "axis" as const,
    },
    xAxis: { boundaryGap: false, data: curves.dates, type: "category" as const },
    yAxis: {
      axisLabel: { formatter: "{value}%" },
      scale: true,
      type: "value" as const,
    },
  };
}
