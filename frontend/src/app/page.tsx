"use client";

import { useEffect, useMemo, useState } from "react";
import { Button, DatePicker, InputNumber, Modal, Select, Space, Table, Tabs, Tag, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import { ReloadOutlined, SyncOutlined } from "@ant-design/icons";

import { StockContextCharts } from "@/components/signals/StockContextCharts";
import { getBacktestTask, runBacktest } from "@/lib/api/backtests";
import {
  getMartDataAssetSummary,
  getSourceUpdateTask,
  getStockDataAssetSummary,
  refreshMartDataAssets,
  requestStockDataAssetRefresh,
  stopSourceUpdateTask,
} from "@/lib/api/dataAssets";
import { getHealth } from "@/lib/api/health";
import { getDailySignals, getStockDataContexts } from "@/lib/api/signals";
import type {
  DataAssetTask,
  MartDatasetOverview,
  StockDatasetOverview,
} from "@/types/dataAsset";
import type { HealthState } from "@/types/health";
import type {
  DailySignalItem,
  DailySignalResult,
  StockDataContext,
} from "@/types/signal";
import { formatDateTime } from "@/utils/format";

const tabs = [
  { key: "data-assets", label: "数据资产维护" },
  { key: "daily-signals", label: "当日信号" },
  { key: "backtest-stats", label: "回测统计" },
  { key: "strategies", label: "策略列表" },
] as const;

const subTabs: Record<(typeof tabs)[number]["key"], { key: string; label: string }[]> = {
  "backtest-stats": [{ key: "run", label: "回测任务" }],
  "daily-signals": [{ key: "daily", label: "当日信号" }],
  "data-assets": [
    { key: "source", label: "源数据" },
    { key: "mart", label: "后处理数据" },
  ],
  strategies: [{ key: "placeholder", label: "占位" }],
};

const dailyRecommendedSourceTables = [
  "trade_calendar",
  "all_stock_snapshot",
  "bar_1d_raw",
  "adjust_factor",
];

const weeklyRecommendedSourceTables = [
  "security_master",
  "bar_5m_raw",
  "dividend",
  "profit",
  "operation",
  "growth",
  "balance",
  "cash_flow",
  "dupont",
  "deposit_rate",
  "loan_rate",
  "reserve_ratio",
  "money_supply_month",
  "money_supply_year",
  "industry_snapshot",
  "index_member_snapshot",
  "performance_express",
  "forecast",
];

const maintainedSourceTables = new Set(dailyRecommendedSourceTables);

const strategyOptions = [{ label: "demo", value: "demo" }];

function defaultTargetDate() {
  const day = new Date();
  day.setDate(day.getDate() - 1);
  const year = day.getFullYear();
  const month = String(day.getMonth() + 1).padStart(2, "0");
  const date = String(day.getDate()).padStart(2, "0");
  return `${year}-${month}-${date}`;
}

function parseLocalDateTime(value: string | null) {
  if (!value) {
    return null;
  }
  const match = value
    .trim()
    .match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}):(\d{2}))?/);
  if (!match) {
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  }
  const [, year, month, day, hour = "0", minute = "0", second = "0"] = match;
  return new Date(
    Number(year),
    Number(month) - 1,
    Number(day),
    Number(hour),
    Number(minute),
    Number(second),
  );
}

function dateKey(value: Date) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function recentUpdateClassName(value: string | null) {
  const updatedAt = parseLocalDateTime(value);
  if (updatedAt === null) {
    return undefined;
  }
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  const updatedKey = dateKey(updatedAt);
  if (updatedKey === dateKey(today)) {
    return "recent-update recent-update-today";
  }
  if (updatedKey === dateKey(yesterday)) {
    return "recent-update recent-update-yesterday";
  }
  return "recent-update recent-update-stale";
}

function formatSignalMetric(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "-";
  }
  return Number.isInteger(value) ? value.toString() : value.toFixed(3);
}

export default function Home() {
  const [activeTab, setActiveTab] = useState<(typeof tabs)[number]["key"]>(
    "data-assets",
  );
  const [health, setHealth] = useState<HealthState | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [datasets, setDatasets] = useState<StockDatasetOverview[]>([]);
  const [datasetsLoading, setDatasetsLoading] = useState(false);
  const [martDatasets, setMartDatasets] = useState<MartDatasetOverview[]>([]);
  const [martDatasetsLoading, setMartDatasetsLoading] = useState(false);
  const [martRefreshing, setMartRefreshing] = useState(false);
  const [activeDataAssetSubTab, setActiveDataAssetSubTab] = useState("source");
  const [sourceUpdateTask, setSourceUpdateTask] = useState<DataAssetTask | null>(
    null,
  );
  const [sourceUpdateModalOpen, setSourceUpdateModalOpen] = useState(false);
  const [sourceUpdateStopping, setSourceUpdateStopping] = useState(false);
  const [sourceUpdateTargetDate, setSourceUpdateTargetDate] = useState(
    defaultTargetDate,
  );
  const [selectedSourceTables, setSelectedSourceTables] = useState<string[]>(
    dailyRecommendedSourceTables,
  );
  const sourceUpdateRunning = sourceUpdateTask?.status === "running";
  const [dailySignalDate, setDailySignalDate] = useState<string | null>(null);
  const [dailySignalStrategy, setDailySignalStrategy] = useState("demo");
  const [dailySignalLoading, setDailySignalLoading] = useState(false);
  const [dailySignalResult, setDailySignalResult] =
    useState<DailySignalResult | null>(null);
  const [stockContexts, setStockContexts] = useState<Record<string, StockDataContext>>(
    {},
  );
  const [stockContextsLoading, setStockContextsLoading] = useState(false);
  const [selectedSignalCode, setSelectedSignalCode] = useState<string | null>(null);
  const [backtestStartDate, setBacktestStartDate] = useState("2018-01-01");
  const [backtestEndDate, setBacktestEndDate] = useState("2026-05-13");
  const [backtestInitialCash, setBacktestInitialCash] = useState(100000);
  const [backtestStrategy, setBacktestStrategy] = useState("demo");
  const [backtestTask, setBacktestTask] = useState<DataAssetTask | null>(null);
  const [backtestLoading, setBacktestLoading] = useState(false);
  const [backtestModalOpen, setBacktestModalOpen] = useState(false);
  const [messageApi, contextHolder] = message.useMessage();
  const backtestRunning = backtestTask?.status === "running";

  useEffect(() => {
    let cancelled = false;

    async function fetchHealth() {
      try {
        const data = await getHealth();
        if (!cancelled) {
          setHealth(data);
          setHealthError(null);
        }
      } catch (error) {
        if (!cancelled) {
          setHealth(null);
          setHealthError(error instanceof Error ? error.message : "unknown");
        }
      }
    }

    fetchHealth();
    const timer = window.setInterval(fetchHealth, 10000);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  async function fetchStockDataAssets() {
    setDatasetsLoading(true);
    try {
      const data = await getStockDataAssetSummary();
      setDatasets(data.datasets);
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "刷新失败");
    } finally {
      setDatasetsLoading(false);
    }
  }

  async function fetchMartDataAssets() {
    setMartDatasetsLoading(true);
    try {
      const data = await getMartDataAssetSummary();
      setMartDatasets(data.datasets);
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "刷新失败");
    } finally {
      setMartDatasetsLoading(false);
    }
  }

  async function refreshMartDatasets() {
    setMartRefreshing(true);
    try {
      const data = await refreshMartDataAssets();
      messageApi.success(data.message);
      await fetchMartDataAssets();
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "更新失败");
    } finally {
      setMartRefreshing(false);
    }
  }

  async function requestRefresh() {
    if (sourceUpdateRunning) {
      setSourceUpdateModalOpen(true);
      return;
    }
    const enabledSelectedSourceTables = selectedSourceTables.filter((datasetName) =>
      maintainedSourceTables.has(datasetName),
    );
    if (enabledSelectedSourceTables.length === 0) {
      messageApi.warning("请选择至少一个 source 表");
      return;
    }

    try {
      const data = await requestStockDataAssetRefresh(
        enabledSelectedSourceTables,
        sourceUpdateTargetDate,
      );
      messageApi.info(data.message);
      if (data.task_id !== null) {
        const task = await getSourceUpdateTask(data.task_id);
        setSourceUpdateTask(task);
        setSourceUpdateModalOpen(true);
      }
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "更新请求失败");
    }
  }

  function toggleSourceTable(datasetName: string, checked: boolean) {
    if (!maintainedSourceTables.has(datasetName)) {
      return;
    }
    setSelectedSourceTables((current) => {
      if (checked) {
        return current.includes(datasetName)
          ? current
          : [...current, datasetName];
      }
      return current.filter((name) => name !== datasetName);
    });
  }

  async function stopRefresh() {
    if (sourceUpdateTask?.id == null || !sourceUpdateRunning) {
      return;
    }

    setSourceUpdateStopping(true);
    try {
      const task = await stopSourceUpdateTask(sourceUpdateTask.id);
      setSourceUpdateTask(task);
      messageApi.warning("更新任务已停止");
      fetchStockDataAssets();
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "停止任务失败");
    } finally {
      setSourceUpdateStopping(false);
    }
  }

  async function fetchDailySignals() {
    if (dailySignalDate === null) {
      messageApi.warning("请选择交易日期");
      return;
    }

    setDailySignalLoading(true);
    setStockContexts({});
    setSelectedSignalCode(null);
    try {
      const data = await getDailySignals({
        strategy_name: dailySignalStrategy,
        trade_date: dailySignalDate,
      });
      setDailySignalResult(data);
      messageApi.success(`当日信号计算完成，共 ${data.signal_count} 只`);
      const codes = data.signals.map((item) => item.code);
      if (codes.length > 0) {
        setSelectedSignalCode(codes[0]);
        setStockContextsLoading(true);
        try {
          const contextResult = await getStockDataContexts({
            codes,
          });
          setStockContexts(
            Object.fromEntries(
              contextResult.contexts.map((context) => [context.code, context]),
            ),
          );
        } catch (error) {
          messageApi.error(
            error instanceof Error ? error.message : "股票上下文加载失败",
          );
        } finally {
          setStockContextsLoading(false);
        }
      }
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "信号查询失败");
    } finally {
      setDailySignalLoading(false);
    }
  }

  async function requestBacktest() {
    if (backtestRunning) {
      setBacktestModalOpen(true);
      return;
    }
    if (!backtestStartDate || !backtestEndDate) {
      messageApi.warning("请选择回测周期");
      return;
    }
    if (backtestInitialCash <= 0) {
      messageApi.warning("初始仓位必须大于 0");
      return;
    }

    setBacktestLoading(true);
    try {
      const data = await runBacktest({
        start_date: backtestStartDate,
        end_date: backtestEndDate,
        initial_cash: backtestInitialCash,
        strategy_name: backtestStrategy,
      });
      setBacktestTask(data.task);
      setBacktestModalOpen(true);
      messageApi.info("回测任务已创建");
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "回测任务创建失败");
    } finally {
      setBacktestLoading(false);
    }
  }

  useEffect(() => {
    let cancelled = false;

    async function fetchRunningSourceUpdateTask() {
      try {
        const task = await getSourceUpdateTask();
        if (!cancelled && task.status === "running") {
          setSourceUpdateTask(task);
          setSourceUpdateModalOpen(true);
        }
      } catch {
        // No previous source_update task exists yet.
      }
    }

    fetchRunningSourceUpdateTask();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (
      !sourceUpdateModalOpen ||
      sourceUpdateTask?.id == null ||
      !sourceUpdateRunning
    ) {
      return undefined;
    }

    let cancelled = false;
    const taskId = sourceUpdateTask.id;

    async function pollTask() {
      try {
        const task = await getSourceUpdateTask(taskId);
        if (!cancelled) {
          setSourceUpdateTask(task);
          if (task.status !== "running") {
            fetchStockDataAssets();
          }
        }
      } catch (error) {
        if (!cancelled) {
          messageApi.error(error instanceof Error ? error.message : "任务查询失败");
        }
      }
    }

    const timer = window.setInterval(pollTask, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [
    messageApi,
    sourceUpdateModalOpen,
    sourceUpdateTask?.id,
    sourceUpdateRunning,
  ]);

  useEffect(() => {
    let cancelled = false;

    async function fetchRunningBacktestTask() {
      try {
        const task = await getBacktestTask();
        if (!cancelled && task.status === "running") {
          setBacktestTask(task);
          setBacktestModalOpen(true);
        }
      } catch {
        // No previous backtest task exists yet.
      }
    }

    fetchRunningBacktestTask();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!backtestModalOpen || backtestTask?.id == null || !backtestRunning) {
      return undefined;
    }

    let cancelled = false;
    const taskId = backtestTask.id;

    async function pollBacktestTask() {
      try {
        const task = await getBacktestTask(taskId);
        if (!cancelled) {
          setBacktestTask(task);
        }
      } catch (error) {
        if (!cancelled) {
          messageApi.error(error instanceof Error ? error.message : "回测任务查询失败");
        }
      }
    }

    const timer = window.setInterval(pollBacktestTask, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [backtestModalOpen, backtestRunning, backtestTask?.id, messageApi]);

  useEffect(() => {
    if (activeTab === "data-assets" && activeDataAssetSubTab === "source") {
      fetchStockDataAssets();
    }
    if (activeTab === "data-assets" && activeDataAssetSubTab === "mart") {
      fetchMartDataAssets();
    }
  }, [activeTab, activeDataAssetSubTab]);

  const activeSubTabs = useMemo(() => subTabs[activeTab], [activeTab]);

  const dataAssetColumns: ColumnsType<StockDatasetOverview> = [
    {
      dataIndex: "dataset_name",
      fixed: "left",
      title: "数据集",
      width: 190,
    },
    {
      dataIndex: "enabled",
      fixed: "left",
      render: (enabled: boolean) =>
        enabled ? <Tag color="green">启用</Tag> : <Tag>停用</Tag>,
      title: "启用",
      width: 90,
    },
    {
      dataIndex: "status",
      fixed: "left",
      render: (status: string) => {
        const color =
          status === "ok"
            ? "green"
            : status === "warning"
              ? "orange"
              : status === "unknown" || status === "empty"
                ? "default"
                : "red";
        return <Tag color={color}>{status}</Tag>;
      },
      title: "状态",
      width: 140,
    },
    {
      dataIndex: "watermark",
      render: (value: string | null) => formatDateTime(value),
      title: "水位",
      width: 140,
    },
    {
      dataIndex: "actual_max_date",
      render: (value: string | null) => formatDateTime(value),
      title: "真实最大日期",
      width: 160,
    },
    {
      dataIndex: "updated_at",
      render: (value: string | null) => (
        <span className={recentUpdateClassName(value)}>{formatDateTime(value)}</span>
      ),
      title: "最近更新",
      width: 210,
    },
    {
      dataIndex: "latest_validation_at",
      render: (value: string | null) => formatDateTime(value),
      title: "最近校验",
      width: 210,
    },
    {
      dataIndex: "validation_failed_count",
      render: (value: number) =>
        value > 0 ? <Tag color="red">{value}</Tag> : <Tag>0</Tag>,
      title: "校验失败",
      width: 110,
    },
    {
      dataIndex: "latest_chunk_status",
      render: (value: string | null) => value ?? "-",
      title: "最近分片",
      width: 120,
    },
    {
      dataIndex: "chunk_failed_count",
      render: (value: number) =>
        value > 0 ? <Tag color="red">{value}</Tag> : <Tag>0</Tag>,
      title: "失败分片",
      width: 110,
    },
    {
      dataIndex: "open_repair_count",
      render: (value: number) =>
        value > 0 ? <Tag color="orange">{value}</Tag> : <Tag>0</Tag>,
      title: "待修复",
      width: 100,
    },
    {
      dataIndex: "endpoint",
      title: "接口",
      width: 173,
    },
    {
      align: "right",
      dataIndex: "row_count",
      render: (value: number | null) => value?.toLocaleString() ?? "-",
      title: "行数",
      width: 130,
    },
  ];

  const martDataAssetColumns: ColumnsType<MartDatasetOverview> = [
    {
      dataIndex: "dataset_name",
      fixed: "left",
      title: "数据集",
      width: 190,
    },
    {
      dataIndex: "table_type",
      render: (value: string) => (
        <Tag color={value === "BASE TABLE" ? "blue" : "purple"}>{value}</Tag>
      ),
      title: "类型",
      width: 120,
    },
    {
      dataIndex: "enabled",
      render: (enabled: boolean) =>
        enabled ? <Tag color="green">启用</Tag> : <Tag>停用</Tag>,
      title: "启用",
      width: 90,
    },
    {
      dataIndex: "status",
      render: (status: string) => {
        const color =
          status === "ok"
            ? "green"
            : status === "warning"
              ? "orange"
              : status === "unknown" || status === "empty"
                ? "default"
                : "red";
        return <Tag color={color}>{status}</Tag>;
      },
      title: "状态",
      width: 140,
    },
    {
      dataIndex: "watermark",
      render: (value: string | null) => formatDateTime(value),
      title: "水位",
      width: 140,
    },
    {
      dataIndex: "actual_max_date",
      render: (value: string | null) => formatDateTime(value),
      title: "真实最大日期",
      width: 160,
    },
    {
      dataIndex: "updated_at",
      render: (value: string | null) => (
        <span className={recentUpdateClassName(value)}>{formatDateTime(value)}</span>
      ),
      title: "最近更新",
      width: 210,
    },
    {
      dataIndex: "latest_validation_at",
      render: (value: string | null) => formatDateTime(value),
      title: "最近校验",
      width: 210,
    },
    {
      dataIndex: "validation_failed_count",
      render: (value: number) =>
        value > 0 ? <Tag color="red">{value}</Tag> : <Tag>0</Tag>,
      title: "校验失败",
      width: 110,
    },
    {
      align: "right",
      dataIndex: "row_count",
      render: (value: number | null) => value?.toLocaleString() ?? "-",
      title: "行数",
      width: 130,
    },
  ];

  const dailySignalColumns: ColumnsType<DailySignalItem> = [
    {
      dataIndex: "code",
      fixed: "left",
      title: "代码",
      width: 140,
    },
    {
      dataIndex: "code_name",
      render: (value: string | null) => value ?? "-",
      title: "名称",
      width: 160,
    },
    {
      dataIndex: "trade_date",
      title: "交易日",
      width: 140,
    },
  ];

  const selectedStockContext =
    selectedSignalCode === null ? null : stockContexts[selectedSignalCode] ?? null;
  const selectedSignal = dailySignalResult?.signals.find(
    (item) => item.code === selectedSignalCode,
  );
  const selectedSignalMetrics: [string, number | null | undefined][] = selectedSignal?.signal
    ? [
        ["最低止损", selectedSignal.signal.min_stop_loss],
        ["参考止盈", selectedSignal.signal.reference_take_profit],
        ["信号 ATR30", selectedSignal.signal.signal_atr30],
        ["理想买入价", selectedSignal.signal.ideal_buy_price],
        ["最长观望", selectedSignal.signal.max_watch_days],
      ]
    : [];
  return (
    <main className="app-shell">
      {contextHolder}
      <Modal
        footer={[
          <Button
            danger
            disabled={!sourceUpdateRunning}
            key="stop"
            loading={sourceUpdateStopping}
            onClick={stopRefresh}
          >
            停止
          </Button>,
          <Button
            key="close"
            onClick={() => setSourceUpdateModalOpen(false)}
            type="primary"
          >
            关闭
          </Button>,
        ]}
        open={sourceUpdateModalOpen}
        title="source_update 更新任务"
        width={760}
        onCancel={() => setSourceUpdateModalOpen(false)}
      >
        <div className="task-modal-header">
          <span>任务 ID: {sourceUpdateTask?.id ?? "-"}</span>
          <Tag
            color={
              sourceUpdateTask?.status === "success"
                ? "green"
                : sourceUpdateTask?.status === "error"
                  ? "red"
                  : "blue"
            }
          >
            {sourceUpdateTask?.status ?? "unknown"}
          </Tag>
        </div>
        <pre className="task-log">{sourceUpdateTask?.logs || "等待任务日志..."}</pre>
      </Modal>
      <Modal
        footer={[
          <Button
            key="close"
            onClick={() => setBacktestModalOpen(false)}
            type="primary"
          >
            关闭
          </Button>,
        ]}
        open={backtestModalOpen}
        title="backtest 回测任务"
        width={760}
        onCancel={() => setBacktestModalOpen(false)}
      >
        <div className="task-modal-header">
          <span>任务 ID: {backtestTask?.id ?? "-"}</span>
          <Tag
            color={
              backtestTask?.status === "success"
                ? "green"
                : backtestTask?.status === "error"
                  ? "red"
                  : "blue"
            }
          >
            {backtestTask?.status ?? "unknown"}
          </Tag>
        </div>
        <pre className="task-log">{backtestTask?.logs || "等待任务日志..."}</pre>
      </Modal>
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">A</div>
          <div>
            <div className="brand-title">Trading System</div>
            <div className="brand-subtitle">A股交易工作台</div>
          </div>
        </div>

        <nav className="nav">
          {tabs.map((tab) => (
            <button
              className={tab.key === activeTab ? "nav-item active" : "nav-item"}
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              type="button"
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div className="topbar-title">
            <Tabs
              activeKey={
                activeTab === "data-assets"
                  ? activeDataAssetSubTab
                  : activeSubTabs[0].key
              }
              className="header-tabs"
              items={activeSubTabs}
              onChange={(key) => {
                if (activeTab === "data-assets") {
                  setActiveDataAssetSubTab(key);
                }
              }}
            />
          </div>
          <div
            className={health?.status === "ok" ? "health ok" : "health error"}
            title={health?.checked_at ?? healthError ?? "未连接"}
          >
            <span className="health-dot" />
            <span>{health?.status === "ok" ? "Backend OK" : "Backend Down"}</span>
          </div>
        </header>

        {activeTab === "data-assets" ? (
          <section className="content-panel">
            {activeDataAssetSubTab === "source" ? (
              <div className="table-panel">
                <div className="table-toolbar">
                  <div className="placeholder-title">源数据总览</div>
                  <Space>
                    <input
                      className="target-date-input"
                      disabled={sourceUpdateRunning}
                      onChange={(event) => setSourceUpdateTargetDate(event.target.value)}
                      title="source_update target date"
                      type="date"
                      value={sourceUpdateTargetDate}
                    />
                    <Button
                      icon={<ReloadOutlined />}
                      loading={datasetsLoading}
                      onClick={fetchStockDataAssets}
                    >
                      刷新
                    </Button>
                    <Button
                      icon={<SyncOutlined />}
                      onClick={requestRefresh}
                      type="primary"
                    >
                      更新
                    </Button>
                  </Space>
                </div>
                <div className="source-table-picker">
                  <div className="source-table-group">
                    <span className="source-table-group-label">日频推荐</span>
                    {dailyRecommendedSourceTables.map((datasetName) => (
                      <label className="source-table-option" key={datasetName}>
                        <input
                          checked={selectedSourceTables.includes(datasetName)}
                          disabled={sourceUpdateRunning}
                          onChange={(event) =>
                            toggleSourceTable(datasetName, event.target.checked)
                          }
                          type="checkbox"
                        />
                        <span>{datasetName}</span>
                      </label>
                    ))}
                  </div>
                  <div className="source-table-group">
                    <span className="source-table-group-label">周频推荐</span>
                    {weeklyRecommendedSourceTables.map((datasetName) => (
                      <label
                        className="source-table-option source-table-option-disabled"
                        key={datasetName}
                      >
                        <input
                          checked={false}
                          disabled
                          onChange={(event) =>
                            toggleSourceTable(datasetName, event.target.checked)
                          }
                          type="checkbox"
                        />
                        <span>{datasetName}</span>
                      </label>
                    ))}
                  </div>
                </div>
                <Table
                  columns={dataAssetColumns}
                  dataSource={datasets}
                  loading={datasetsLoading}
                  pagination={false}
                  rowClassName={(record) =>
                    record.enabled ? "" : "disabled-asset-row"
                  }
                  rowKey="dataset_name"
                  scroll={{ x: 1733 }}
                  size="middle"
                />
              </div>
            ) : (
              <div className="table-panel">
                <div className="table-toolbar">
                  <div className="placeholder-title">后处理数据总览</div>
                  <Space>
                    <Button
                      icon={<ReloadOutlined />}
                      loading={martDatasetsLoading}
                      onClick={fetchMartDataAssets}
                    >
                      刷新
                    </Button>
                    <Button
                      icon={<SyncOutlined />}
                      loading={martRefreshing}
                      onClick={refreshMartDatasets}
                      type="primary"
                    >
                      更新
                    </Button>
                  </Space>
                </div>
                <Table
                  columns={martDataAssetColumns}
                  dataSource={martDatasets}
                  loading={martDatasetsLoading || martRefreshing}
                  pagination={false}
                  rowClassName={(record) =>
                    record.enabled ? "" : "disabled-asset-row"
                  }
                  rowKey="dataset_name"
                  scroll={{ x: 1410 }}
                  size="middle"
                />
              </div>
            )}
          </section>
        ) : activeTab === "daily-signals" ? (
          <section className="content-panel">
            <div className="signal-workbench">
              <div className="table-toolbar">
                <div>
                  <div className="placeholder-title">当日信号</div>
                  <div className="panel-subtitle">
                    universe: {dailySignalResult?.universe_count ?? "-"} / signals:{" "}
                    {dailySignalResult?.signal_count ?? "-"} / contexts:{" "}
                    {Object.keys(stockContexts).length || "-"}
                  </div>
                </div>
                <Space>
                  <DatePicker
                    onChange={(_, dateString) =>
                      setDailySignalDate(
                        typeof dateString === "string" && dateString.length > 0
                          ? dateString
                          : null,
                      )
                    }
                    placeholder="选择交易日"
                  />
                  <Select
                    options={strategyOptions}
                    value={dailySignalStrategy}
                    onChange={setDailySignalStrategy}
                    style={{ width: 140 }}
                  />
                  <Button
                    loading={dailySignalLoading || stockContextsLoading}
                    onClick={fetchDailySignals}
                    type="primary"
                  >
                    获取当日信号
                  </Button>
                </Space>
              </div>
              <div className="signal-layout">
                <div className="signal-list">
                  <Table
                    columns={dailySignalColumns}
                    dataSource={dailySignalResult?.signals ?? []}
                    loading={dailySignalLoading || stockContextsLoading}
                    onRow={(record) => ({
                      onClick: () => setSelectedSignalCode(record.code),
                    })}
                    pagination={{ pageSize: 30, showSizeChanger: true }}
                    rowClassName={(record) =>
                      record.code === selectedSignalCode ? "selected-row" : ""
                    }
                    rowKey="code"
                    scroll={{ x: 440, y: 560 }}
                    size="small"
                  />
                </div>
                <div className="signal-charts">
                  <div className="chart-header">
                    <div className="placeholder-title">
                      {selectedSignalCode ?? "未选择股票"}
                    </div>
                    <div className="panel-subtitle">
                      {selectedSignal?.code_name ?? "从左侧列表选择一只股票"}
                    </div>
                  </div>
                  {selectedSignalMetrics.length > 0 ? (
                    <div className="signal-metrics">
                      {selectedSignalMetrics.map(([label, value]) => (
                        <div className="signal-metric" key={label}>
                          <span>{label}</span>
                          <strong>{formatSignalMetric(value)}</strong>
                        </div>
                      ))}
                    </div>
                  ) : null}
                  {selectedStockContext === null ? (
                    <div className="empty-chart">暂无可渲染的股票上下文</div>
                  ) : (
                    <StockContextCharts context={selectedStockContext} />
                  )}
                </div>
              </div>
            </div>
          </section>
        ) : activeTab === "backtest-stats" ? (
          <section className="content-panel">
            <div className="backtest-panel">
              <div className="table-toolbar">
                <div>
                  <div className="placeholder-title">回测统计</div>
                  <div className="panel-subtitle">
                    创建允许重复的回测任务，预计算一次信号后固定执行 50 轮随机撮合，订单和快照用 run_no 区分。
                  </div>
                </div>
                <Button
                  loading={backtestLoading}
                  onClick={requestBacktest}
                  type="primary"
                >
                  {backtestRunning ? "查看任务" : "开始回测"}
                </Button>
              </div>
              <div className="backtest-form">
                <label className="form-field">
                  <span>开始日期</span>
                  <input
                    className="target-date-input"
                    disabled={backtestRunning || backtestLoading}
                    onChange={(event) => setBacktestStartDate(event.target.value)}
                    type="date"
                    value={backtestStartDate}
                  />
                </label>
                <label className="form-field">
                  <span>结束日期</span>
                  <input
                    className="target-date-input"
                    disabled={backtestRunning || backtestLoading}
                    onChange={(event) => setBacktestEndDate(event.target.value)}
                    type="date"
                    value={backtestEndDate}
                  />
                </label>
                <label className="form-field">
                  <span>初始仓位</span>
                  <InputNumber
                    disabled={backtestRunning || backtestLoading}
                    min={1}
                    onChange={(value) =>
                      setBacktestInitialCash(typeof value === "number" ? value : 100000)
                    }
                    precision={2}
                    style={{ width: "100%" }}
                    value={backtestInitialCash}
                  />
                </label>
                <label className="form-field">
                  <span>策略</span>
                  <Select
                    disabled={backtestRunning || backtestLoading}
                    options={strategyOptions}
                    value={backtestStrategy}
                    onChange={setBacktestStrategy}
                  />
                </label>
              </div>
              <div className="backtest-summary">
                <Tag
                  color={
                    backtestTask?.status === "success"
                      ? "green"
                      : backtestTask?.status === "error"
                        ? "red"
                        : backtestTask?.status === "running"
                          ? "blue"
                          : "default"
                  }
                >
                  {backtestTask?.status ?? "no task"}
                </Tag>
                <span>最近任务 ID: {backtestTask?.id ?? "-"}</span>
                {backtestTask?.id != null ? (
                  <Button size="small" onClick={() => setBacktestModalOpen(true)}>
                    查看日志
                  </Button>
                ) : null}
              </div>
            </div>
          </section>
        ) : (
          <section className="placeholder">
            <div className="placeholder-title">占位</div>
            <p>该模块后续接入真实功能。</p>
          </section>
        )}
      </section>
    </main>
  );
}
