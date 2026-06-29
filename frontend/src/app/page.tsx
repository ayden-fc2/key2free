"use client";

import { useEffect, useMemo, useState } from "react";
import { Button, Checkbox, DatePicker, InputNumber, Modal, Select, Space, Table, Tabs, Tag, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import { ReloadOutlined } from "@ant-design/icons";

import { BacktestDetailModal } from "@/components/backtests/BacktestDetailModal";
import { StockContextCharts } from "@/components/signals/StockContextCharts";
import { getBacktestTask, listBacktestTasks, runBacktest } from "@/lib/api/backtests";
import { getHealth } from "@/lib/api/health";
import {
  getDailySignalTask,
  getDailySignalTaskResult,
  getSignalStrategies,
  getStockDataContexts,
  startDailySignalTask,
} from "@/lib/api/signals";
import {
  getTushareRefreshTask,
  listTushareWatermarks,
  startTushareRefresh,
} from "@/lib/api/tushareAssets";
import type { BacktestTask } from "@/types/backtest";
import type { HealthState } from "@/types/health";
import type { DailySignalItem, DailySignalResult, DailySignalTask, StockDataContext } from "@/types/signal";
import type { TushareAssetWatermark, TushareRefreshTask } from "@/types/tushareAsset";
import { formatDateTime } from "@/utils/format";

const tabs = [
  { key: "data-assets", label: "数据资产维护" },
  { key: "daily-signals", label: "当日信号" },
  { key: "backtest-stats", label: "回测统计" },
] as const;

const subTabs: Record<(typeof tabs)[number]["key"], { key: string; label: string }[]> = {
  "data-assets": [{ key: "tushare", label: "Tushare 资产" }],
  "daily-signals": [{ key: "daily", label: "当日信号" }],
  "backtest-stats": [{ key: "run", label: "回测任务" }],
};

const DEFAULT_STRATEGY_OPTIONS = [{ label: "small_float_value", value: "small_float_value" }];

const TUSHARE_ASSET_META: Record<
  string,
  { api: string; purpose: string; refresh: string; note?: string }
> = {
  "tushare.trade_cal": {
    api: "trade_cal",
    purpose: "交易日历",
    refresh: "按年份窗口刷新",
  },
  "tushare.index_basic": {
    api: "index_basic",
    purpose: "核心指数静态白名单",
    refresh: "静态维护，不参与每日水位刷新",
    note: "仅保留上证指数、深证成指、创业板指、中证500",
  },
  "tushare.index_daily": {
    api: "index_daily",
    purpose: "核心指数日线行情",
    refresh: "依赖指数白名单，按指数代码和交易日区间刷新",
  },
  "tushare.bak_basic": {
    api: "bak_basic",
    purpose: "历史股票列表/基础信息",
    note: "股票资产层默认排除北交所 BJ；指数白名单仅维护 2014 年起日线和每日指标都完整的核心指数",
    refresh: "按交易日沪深股票刷新，默认排除北交所 BJ",
  },
  "tushare.adj_factor": {
    api: "adj_factor",
    purpose: "复权因子",
    note: "股票资产层默认排除北交所 BJ",
    refresh: "按交易日沪深股票刷新，默认排除北交所 BJ",
  },
  "tushare.daily": {
    api: "daily",
    purpose: "未复权日线行情",
    note: "股票资产层默认排除北交所 BJ",
    refresh: "按交易日沪深股票刷新，默认排除北交所 BJ",
  },
  "tushare.daily_basic": {
    api: "daily_basic",
    purpose: "估值/市值/股本/换手率",
    refresh: "按交易日沪深股票刷新，默认排除北交所 BJ",
    note: "最早可信 2016-12-06；股票资产层默认排除北交所 BJ",
  },
  "tushare.stk_mins_5min": {
    api: "stk_mins 5min",
    purpose: "5分钟线原始行情",
    refresh: "按交易日逐股刷新，默认排除北交所 BJ",
    note: "需单独分钟权限；北交所 BJ 不进入默认股票资产层",
  },
  "tushare.stock_daily_technical": {
    api: "派生表",
    purpose: "前复权日线/基础信息/技术指标宽表",
    refresh: "依赖沪深股票基础资产最小水位覆盖重建",
    note: "正式落表自 2017-06-01；默认排除北交所 BJ 股票",
  },
};

function defaultSimulationRunsForStrategy(strategyName: string) {
  return strategyName === "small_float_value" ? 1 : 50;
}

function formatNumber(value: number | null | undefined, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "-";
  }
  return value.toLocaleString(undefined, {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}

function formatReturn(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "-";
  }
  return `${(value * 100).toFixed(2)}%`;
}

function statusTag(status: string) {
  const color =
    status === "success" ? "green" : status === "error" ? "red" : status === "running" ? "blue" : "default";
  return <Tag color={color}>{status}</Tag>;
}

function formatSignalMetric(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "-";
  }
  return Number.isInteger(value) ? value.toString() : value.toFixed(3);
}

function formatSignalMetricList(values: number[] | null | undefined) {
  if (!values || values.length === 0) {
    return "-";
  }
  return values.map((value) => formatSignalMetric(value)).join(" / ");
}

function formatSignalValue(value: unknown) {
  if (typeof value === "number") {
    return formatSignalMetric(value);
  }
  if (typeof value === "string") {
    return value;
  }
  if (value === null || value === undefined) {
    return "-";
  }
  return formatSignalExtra(value);
}

function signalRowKey(item: DailySignalItem) {
  return `${item.trade_date}:${item.code}`;
}

function formatSellRules(item: DailySignalItem) {
  const rules = item.signal?.sell_rules;
  if (rules && rules.length > 0) {
    return rules.map((rule) => rule.name ?? rule.description ?? "-").join(" / ");
  }
  const stopLosses = formatSignalMetricList(item.signal?.stop_losses);
  const takeProfits = formatSignalMetricList(item.signal?.take_profits);
  if (stopLosses !== "-" || takeProfits !== "-") {
    return `止损 ${stopLosses} / 止盈 ${takeProfits}`;
  }
  return "-";
}

function formatSignalExtra(value: unknown) {
  if (value === null || value === undefined) {
    return "-";
  }
  if (typeof value === "number") {
    return formatSignalMetric(value);
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  if (typeof value === "string") {
    return value;
  }
  return JSON.stringify(value);
}

function formatLocalDate(value: Date) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function resolveDefaultTushareEndDate() {
  const now = new Date();
  const endDate = new Date(now);
  if (now.getHours() < 19) {
    endDate.setDate(endDate.getDate() - 1);
  }
  return formatLocalDate(endDate);
}

export default function Home() {
  const [activeTab, setActiveTab] = useState<(typeof tabs)[number]["key"]>("data-assets");
  const [health, setHealth] = useState<HealthState | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [tushareWatermarks, setTushareWatermarks] = useState<TushareAssetWatermark[]>([]);
  const [tushareWatermarksLoading, setTushareWatermarksLoading] = useState(false);
  const [tushareRefreshTask, setTushareRefreshTask] = useState<TushareRefreshTask | null>(null);
  const [tushareRefreshStarting, setTushareRefreshStarting] = useState(false);
  const [tushareRefreshEndDate, setTushareRefreshEndDate] = useState(resolveDefaultTushareEndDate);
  const [skipStkMins5min, setSkipStkMins5min] = useState(true);
  const [dailySignalDate, setDailySignalDate] = useState<string | null>(null);
  const [dailySignalLookbackDays, setDailySignalLookbackDays] = useState(1);
  const [dailySignalStrategy, setDailySignalStrategy] = useState("small_float_value");
  const [dailySignalLoading, setDailySignalLoading] = useState(false);
  const [dailySignalTask, setDailySignalTask] = useState<DailySignalTask | null>(null);
  const [dailySignalTaskModalOpen, setDailySignalTaskModalOpen] = useState(false);
  const [dailySignalResult, setDailySignalResult] = useState<DailySignalResult | null>(null);
  const [stockContexts, setStockContexts] = useState<Record<string, StockDataContext>>({});
  const [stockContextsLoading, setStockContextsLoading] = useState(false);
  const [selectedSignalKey, setSelectedSignalKey] = useState<string | null>(null);
  const [backtestStartDate, setBacktestStartDate] = useState("2018-01-01");
  const [backtestEndDate, setBacktestEndDate] = useState("2026-06-08");
  const [backtestInitialCash, setBacktestInitialCash] = useState(10000000);
  const [backtestStrategy, setBacktestStrategy] = useState("small_float_value");
  const [backtestSimulationRuns, setBacktestSimulationRuns] = useState(
    defaultSimulationRunsForStrategy("small_float_value"),
  );
  const [backtestTask, setBacktestTask] = useState<BacktestTask | null>(null);
  const [backtestTasks, setBacktestTasks] = useState<BacktestTask[]>([]);
  const [backtestTasksLoading, setBacktestTasksLoading] = useState(false);
  const [backtestLoading, setBacktestLoading] = useState(false);
  const [backtestModalOpen, setBacktestModalOpen] = useState(false);
  const [backtestCreateModalOpen, setBacktestCreateModalOpen] = useState(false);
  const [backtestDetailTaskId, setBacktestDetailTaskId] = useState<number | null>(null);
  const [backtestDetailOpen, setBacktestDetailOpen] = useState(false);
  const [strategyOptions, setStrategyOptions] = useState(DEFAULT_STRATEGY_OPTIONS);

  useEffect(() => {
    getSignalStrategies()
      .then((data) =>
        setStrategyOptions(data.strategies.map((name) => ({ label: name, value: name }))),
      )
      .catch(() => undefined);
  }, []);
  const [messageApi, contextHolder] = message.useMessage();
  const backtestRunning = backtestTask?.status === "running";
  const dailySignalRunning = dailySignalTask?.status === "running";

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const tab = params.get("tab");
    const taskId = params.get("task_id");
    if (tab === "backtest-stats") {
      setActiveTab("backtest-stats");
    }
    if (taskId !== null) {
      const parsedTaskId = Number(taskId);
      if (Number.isFinite(parsedTaskId)) {
        getBacktestTask(parsedTaskId).then(setBacktestTask).catch(() => undefined);
        setBacktestDetailTaskId(parsedTaskId);
        setBacktestDetailOpen(true);
      }
    }
  }, []);

  async function fetchTushareWatermarks() {
    setTushareWatermarksLoading(true);
    try {
      setTushareWatermarks(await listTushareWatermarks());
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "水位查询失败");
    } finally {
      setTushareWatermarksLoading(false);
    }
  }

  async function fetchLatestTushareRefreshTask() {
    try {
      setTushareRefreshTask(await getTushareRefreshTask());
    } catch {
      setTushareRefreshTask(null);
    }
  }

  async function requestTushareRefresh() {
    if (!tushareRefreshEndDate) {
      messageApi.warning("请选择截止日期");
      return;
    }
    setTushareRefreshStarting(true);
    try {
      const result = await startTushareRefresh({
        end_date: tushareRefreshEndDate,
        skip_stk_mins_5min: skipStkMins5min,
      });
      messageApi.info(result.message);
      if (result.task_id !== null) {
        setTushareRefreshTask(await getTushareRefreshTask(result.task_id));
      }
      await fetchTushareWatermarks();
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "启动刷新失败");
    } finally {
      setTushareRefreshStarting(false);
    }
  }

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

  async function loadDailySignalResult(taskId: number) {
    const data = await getDailySignalTaskResult(taskId);
    setDailySignalResult(data);
    const codes = data.signals.map((item) => item.code);
    if (codes.length === 0) {
      return;
    }
    setSelectedSignalKey((current) => current ?? signalRowKey(data.signals[0]));
    setStockContextsLoading(true);
    try {
      const contextResult = await getStockDataContexts({ codes });
      setStockContexts(Object.fromEntries(contextResult.contexts.map((context) => [context.code, context])));
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "股票上下文加载失败");
    } finally {
      setStockContextsLoading(false);
    }
  }

  async function fetchDailySignals() {
    if (dailySignalDate === null) {
      messageApi.warning("请选择交易日期");
      return;
    }
    setDailySignalLoading(true);
    setStockContexts({});
    setSelectedSignalKey(null);
    setDailySignalResult(null);
    try {
      const data = await startDailySignalTask({
        strategy_name: dailySignalStrategy,
        trade_date: dailySignalDate,
        lookback_trade_days: dailySignalLookbackDays,
      });
      setDailySignalTask(data.task);
      setDailySignalTaskModalOpen(true);
      messageApi.info(data.message);
      if (data.task.status === "success" && data.task.id !== null) {
        await loadDailySignalResult(data.task.id);
        messageApi.success(`当日信号已加载，共 ${data.task.signal_count ?? 0} 只`);
      }
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "信号任务创建失败");
    } finally {
      setDailySignalLoading(false);
    }
  }

  async function fetchBacktestTasks() {
    setBacktestTasksLoading(true);
    try {
      const tasks = await listBacktestTasks();
      setBacktestTasks(tasks);
      const runningTask = tasks.find((task) => task.status === "running");
      if (runningTask) {
        setBacktestTask((current) => current ?? runningTask);
      }
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "backtest tasks load failed");
    } finally {
      setBacktestTasksLoading(false);
    }
  }

  async function requestBacktest() {
    if (!backtestStartDate || !backtestEndDate) {
      messageApi.warning("请选择回测周期");
      return;
    }
    if (backtestInitialCash <= 0) {
      messageApi.warning("初始资金必须大于 0");
      return;
    }
    if (backtestSimulationRuns < 1) {
      messageApi.warning("撮合次数必须大于等于 1");
      return;
    }
    setBacktestLoading(true);
    try {
      const data = await runBacktest({
        start_date: backtestStartDate,
        end_date: backtestEndDate,
        initial_cash: backtestInitialCash,
        strategy_name: backtestStrategy,
        simulation_runs: backtestSimulationRuns,
      });
      setBacktestTask(data.task);
      setBacktestCreateModalOpen(false);
      setBacktestModalOpen(true);
      fetchBacktestTasks();
      messageApi.info("回测任务已创建");
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "回测任务创建失败");
    } finally {
      setBacktestLoading(false);
    }
  }

  useEffect(() => {
    fetchBacktestTasks();
  }, []);

  useEffect(() => {
    fetchTushareWatermarks();
    fetchLatestTushareRefreshTask();
  }, []);

  useEffect(() => {
    if (tushareRefreshTask?.status !== "running") {
      return undefined;
    }
    const taskId = tushareRefreshTask.id;
    let cancelled = false;
    async function pollTushareRefresh() {
      try {
        const task = await getTushareRefreshTask(taskId);
        if (!cancelled) {
          setTushareRefreshTask(task);
          await fetchTushareWatermarks();
        }
      } catch (error) {
        if (!cancelled) {
          messageApi.error(error instanceof Error ? error.message : "刷新任务查询失败");
        }
      }
    }
    const timer = window.setInterval(pollTushareRefresh, 3000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [messageApi, tushareRefreshTask?.id, tushareRefreshTask?.status]);

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
          setBacktestTasks((tasks) => tasks.map((item) => (item.id === task.id ? task : item)));
          if (task.status !== "running") {
            fetchBacktestTasks();
          }
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
    if (dailySignalTask?.id == null || dailySignalTask.status !== "running") {
      return undefined;
    }
    let cancelled = false;
    const taskId = dailySignalTask.id;
    async function pollDailySignalTask() {
      try {
        const task = await getDailySignalTask({ task_id: taskId });
        if (cancelled) {
          return;
        }
        setDailySignalTask(task);
        if (task.status === "success") {
          await loadDailySignalResult(taskId);
          messageApi.success(`当日信号已加载，共 ${task.signal_count ?? 0} 只`);
        } else if (task.status === "error") {
          messageApi.error("当日信号任务失败");
        }
      } catch (error) {
        if (!cancelled) {
          messageApi.error(error instanceof Error ? error.message : "当日信号任务查询失败");
        }
      }
    }
    const timer = window.setInterval(pollDailySignalTask, 2000);
    pollDailySignalTask();
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [dailySignalTask?.id, dailySignalTask?.status, messageApi]);

  const activeSubTabs = useMemo(() => subTabs[activeTab], [activeTab]);

  const tushareWatermarkColumns: ColumnsType<TushareAssetWatermark> = [
    {
      dataIndex: "asset_table_name",
      title: "资产表名",
      width: 220,
    },
    {
      render: (_value, record) => TUSHARE_ASSET_META[record.asset_table_name]?.api ?? "-",
      title: "接口",
      width: 130,
    },
    {
      render: (_value, record) => TUSHARE_ASSET_META[record.asset_table_name]?.purpose ?? "-",
      title: "用途",
      width: 220,
    },
    {
      render: (_value, record) => TUSHARE_ASSET_META[record.asset_table_name]?.refresh ?? "-",
      title: "刷新方式",
      width: 210,
    },
    {
      dataIndex: "earliest_trusted_watermark",
      title: "Earliest Trusted",
      width: 170,
      render: (value: string | null) => value ?? "-",
    },
    {
      dataIndex: "trusted_watermark",
      title: "最新可信水位",
      width: 180,
      render: (value: string | null) => value ?? <Tag>未初始化</Tag>,
    },
    {
      dataIndex: "issue_count",
      title: "Issues",
      width: 90,
    },
    {
      dataIndex: "last_issue_scope",
      title: "Last Scope",
      width: 160,
      render: (value: string | null) => value ?? "-",
    },
    {
      dataIndex: "last_issue_message",
      title: "Last Issue",
      width: 280,
      render: (value: string | null, record) => value ?? TUSHARE_ASSET_META[record.asset_table_name]?.note ?? "-",
    },
  ];

  const backtestTaskColumns: ColumnsType<BacktestTask> = [
    { dataIndex: "id", title: "任务 ID", width: 90 },
    { dataIndex: "strategy_name", title: "策略", width: 120 },
    {
      render: (_value, record) => `${record.start_date} -> ${record.end_date}`,
      title: "周期",
      width: 220,
    },
    {
      dataIndex: "status",
      render: (status: string) => statusTag(status),
      title: "状态",
      width: 100,
    },
    {
      render: (_value, record) => `${record.completed_runs}/${record.simulation_runs}`,
      title: "完成轮次",
      width: 110,
    },
    {
      dataIndex: "trading_day_count",
      render: (value: number | null) => value ?? "-",
      title: "交易日",
      width: 90,
    },
    {
      dataIndex: "signal_count",
      render: (value: number | null) => value ?? "-",
      title: "信号数",
      width: 90,
    },
    {
      dataIndex: "final_return_avg",
      render: (value: number | null) => formatReturn(value),
      title: "平均最终收益率",
      width: 140,
    },
    {
      dataIndex: "annualized_return_avg",
      render: (value: number | null) => formatReturn(value),
      title: "平均年化收益率",
      width: 140,
    },
    {
      dataIndex: "sharpe_ratio_avg",
      render: (value: number | null) => formatNumber(value, 2),
      title: "夏普比率",
      width: 110,
    },
    {
      dataIndex: "profit_loss_ratio_avg",
      render: (value: number | null) => formatNumber(value, 2),
      title: "盈亏比",
      width: 100,
    },
    {
      dataIndex: "excess_return_avg",
      render: (value: number | null) => formatReturn(value),
      title: "超额收益",
      width: 110,
    },
    {
      dataIndex: "max_drawdown_avg",
      render: (value: number | null) => formatReturn(value),
      title: "最大回撤",
      width: 110,
    },
    {
      dataIndex: "trades_per_year_avg",
      render: (value: number | null) => (value === null ? "-" : value.toFixed(1)),
      title: "平均年交易次数",
      width: 130,
    },
    {
      dataIndex: "win_rate_avg",
      render: (value: number | null) => formatReturn(value),
      title: "平均胜率",
      width: 100,
    },
    {
      dataIndex: "final_asset_avg",
      render: (value: number | null) => formatNumber(value),
      title: "平均最终资产",
      width: 140,
    },
    {
      dataIndex: "updated_at",
      render: (value: string | null) => formatDateTime(value),
      title: "更新时间",
      width: 180,
    },
    {
      fixed: "right",
      render: (_value, record) => (
        <Space>
          <Button
            size="small"
            onClick={() => {
              setBacktestTask(record);
              setBacktestModalOpen(true);
            }}
          >
            查看日志
          </Button>
          <Button
            disabled={record.status === "running"}
            size="small"
            type="primary"
            onClick={() => {
              if (record.id != null) {
                setBacktestDetailTaskId(record.id);
                setBacktestDetailOpen(true);
              }
            }}
          >
            查看详情
          </Button>
        </Space>
      ),
      title: "操作",
      width: 190,
    },
  ];

  const dailySignalColumns: ColumnsType<DailySignalItem> = [
    { dataIndex: "trade_date", title: "日期", width: 115 },
    { dataIndex: "code", title: "代码", width: 120 },
    { dataIndex: "code_name", title: "名称", width: 120 },
    {
      render: (_value, record) => formatSignalMetric(record.signal?.signal_close),
      title: "T日收盘",
      width: 120,
    },
    {
      render: (_value, record) => formatSignalValue(record.signal?.entry_trigger_price ?? record.signal?.extras?.entry_trigger_price),
      title: "买入触发",
      width: 150,
    },
    {
      render: (_value, record) => formatSignalMetric(record.signal?.max_watch_days),
      title: "观察期",
      width: 100,
    },
    {
      ellipsis: true,
      render: (_value, record) => formatSellRules(record),
      title: "卖出规则",
      width: 260,
    },
  ];

  const selectedSignal = dailySignalResult?.signals.find((item) => signalRowKey(item) === selectedSignalKey) ?? null;
  const selectedStockContext = selectedSignal === null ? null : stockContexts[selectedSignal.code] ?? null;
  const selectedDisplay = selectedSignal?.signal?.display ?? null;
  const selectedSignalMetrics: [string, unknown][] =
    selectedSignal === null
      ? []
      : [
          ["信号日期", selectedSignal.trade_date],
          ["T日收盘", selectedSignal.signal?.signal_close],
          ["买入触发价", selectedSignal.signal?.entry_trigger_price ?? selectedSignal.signal?.extras?.entry_trigger_price],
          ["最长观察期", selectedSignal.signal?.max_watch_days],
          ...Object.entries(selectedSignal.signal?.extras ?? {}),
        ];

  return (
    <main className="app-shell">
      {contextHolder}
      <BacktestDetailModal
        open={backtestDetailOpen}
        taskId={backtestDetailTaskId}
        onClose={() => setBacktestDetailOpen(false)}
      />
      <Modal
        footer={[
          <Button key="close" onClick={() => setBacktestModalOpen(false)} type="primary">
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
          {statusTag(backtestTask?.status ?? "unknown")}
        </div>
        <pre className="task-log">{backtestTask?.logs || "等待任务日志..."}</pre>
      </Modal>
      <Modal
        footer={[
          <Button key="close" onClick={() => setDailySignalTaskModalOpen(false)} type="primary">
            关闭
          </Button>,
        ]}
        open={dailySignalTaskModalOpen}
        title="当日信号任务"
        width={760}
        onCancel={() => setDailySignalTaskModalOpen(false)}
      >
        <div className="task-modal-header">
          <span>任务 ID: {dailySignalTask?.id ?? "-"}</span>
          {statusTag(dailySignalTask?.status ?? "unknown")}
        </div>
        <pre className="task-log">{dailySignalTask?.logs || "等待任务日志..."}</pre>
      </Modal>
      <Modal
        confirmLoading={backtestLoading}
        okText="新建回测"
        open={backtestCreateModalOpen}
        title="新建回测"
        width={760}
        onCancel={() => setBacktestCreateModalOpen(false)}
        onOk={requestBacktest}
      >
        <div className="backtest-form">
          <label className="form-field">
            <span>开始日期</span>
            <input
              className="target-date-input"
              disabled={backtestLoading}
              onChange={(event) => setBacktestStartDate(event.target.value)}
              type="date"
              value={backtestStartDate}
            />
          </label>
          <label className="form-field">
            <span>结束日期</span>
            <input
              className="target-date-input"
              disabled={backtestLoading}
              onChange={(event) => setBacktestEndDate(event.target.value)}
              type="date"
              value={backtestEndDate}
            />
          </label>
          <label className="form-field">
            <span>初始资金</span>
            <InputNumber
              disabled={backtestLoading}
              min={1}
              onChange={(value) => setBacktestInitialCash(typeof value === "number" ? value : 10000000)}
              precision={2}
              style={{ width: "100%" }}
              value={backtestInitialCash}
            />
          </label>
          <label className="form-field">
            <span>撮合次数</span>
            <InputNumber
              disabled={backtestLoading}
              min={1}
              max={500}
              onChange={(value) => setBacktestSimulationRuns(typeof value === "number" ? value : 1)}
              precision={0}
              style={{ width: "100%" }}
              value={backtestSimulationRuns}
            />
          </label>
          <label className="form-field">
            <span>策略</span>
            <Select
              disabled={backtestLoading}
              options={strategyOptions}
              value={backtestStrategy}
              onChange={(value) => {
                setBacktestStrategy(value);
                setBacktestSimulationRuns(defaultSimulationRunsForStrategy(value));
              }}
            />
          </label>
        </div>
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
            <button className={tab.key === activeTab ? "nav-item active" : "nav-item"} key={tab.key} onClick={() => setActiveTab(tab.key)} type="button">
              {tab.label}
            </button>
          ))}
        </nav>
      </aside>
      <section className="workspace">
        <header className="topbar">
          <div className="topbar-title">
            <Tabs activeKey={activeSubTabs[0].key} className="header-tabs" items={activeSubTabs} />
          </div>
          <div className={health?.status === "ok" ? "health ok" : "health error"} title={health?.checked_at ?? healthError ?? "未连接"}>
            <span className="health-dot" />
            <span>{health?.status === "ok" ? "Backend OK" : "Backend Down"}</span>
          </div>
        </header>

        {activeTab === "data-assets" ? (
          <section className="content-panel">
            <div className="table-panel">
              <div className="table-toolbar">
                <div>
                  <div className="placeholder-title">Tushare 数据资产</div>
                  <div className="panel-subtitle">
                    当前资产刷新按水位顺序轮转；后端运行时每天 03:00 自动刷新到昨日，自动任务包含 5 分钟线。
                  </div>
                </div>
                <Space>
                  <input
                    className="target-date-input"
                    disabled={tushareRefreshStarting || tushareRefreshTask?.status === "running"}
                    onChange={(event) => setTushareRefreshEndDate(event.target.value)}
                    type="date"
                    value={tushareRefreshEndDate}
                  />
                  <Checkbox
                    checked={skipStkMins5min}
                    disabled={tushareRefreshStarting || tushareRefreshTask?.status === "running"}
                    onChange={(event) => setSkipStkMins5min(event.target.checked)}
                  >
                    跳过5分钟线
                  </Checkbox>
                  <Button icon={<ReloadOutlined />} loading={tushareWatermarksLoading} onClick={fetchTushareWatermarks}>
                    刷新水位
                  </Button>
                  <Button
                    loading={tushareRefreshStarting || tushareRefreshTask?.status === "running"}
                    onClick={requestTushareRefresh}
                    type="primary"
                  >
                    启动更新
                  </Button>
                </Space>
              </div>
              <Table
                columns={tushareWatermarkColumns}
                dataSource={tushareWatermarks}
                loading={tushareWatermarksLoading}
                pagination={false}
                rowKey="asset_table_name"
                scroll={{ x: 1490 }}
                size="middle"
              />
              <div className="backtest-summary">
                {tushareRefreshTask ? statusTag(tushareRefreshTask.status) : <Tag>no task</Tag>}
                <span>任务 ID: {tushareRefreshTask?.id ?? "-"}</span>
                <span>当前资产: {tushareRefreshTask?.current_asset_table_name ?? "-"}</span>
                <span>当前水位: {tushareRefreshTask?.current_watermark ?? "-"}</span>
              </div>
              <pre className="task-log">{tushareRefreshTask?.logs || "暂无刷新日志"}</pre>
            </div>
          </section>
        ) : activeTab === "daily-signals" ? (
          <section className="content-panel">
            <div className="signal-workbench">
              <div className="table-toolbar">
                <div>
                  <div className="placeholder-title">当日信号</div>
                  <div className="panel-subtitle">
                    task: {dailySignalTask?.id ?? "-"} / status: {dailySignalTask?.status ?? "-"} / days:{" "}
                    {dailySignalResult?.start_trade_date ?? "-"}~{dailySignalResult?.end_trade_date ?? dailySignalResult?.trade_date ?? "-"} / processed:{" "}
                    {dailySignalTask?.processed_count ?? "-"} / universe:{" "}
                    {dailySignalTask?.universe_count ?? dailySignalResult?.universe_count ?? "-"} / signals:{" "}
                    {dailySignalTask?.signal_count ?? dailySignalResult?.signal_count ?? "-"} / contexts: {Object.keys(stockContexts).length || "-"}
                  </div>
                </div>
                <Space>
                  <DatePicker onChange={(_, dateString) => setDailySignalDate(typeof dateString === "string" && dateString.length > 0 ? dateString : null)} placeholder="选择交易日" />
                  <InputNumber
                    min={1}
                    max={120}
                    onChange={(value) => setDailySignalLookbackDays(typeof value === "number" ? value : 1)}
                    precision={0}
                    style={{ width: 120 }}
                    value={dailySignalLookbackDays}
                    addonBefore="过去"
                    addonAfter="日"
                  />
                  <Select options={strategyOptions} value={dailySignalStrategy} onChange={setDailySignalStrategy} style={{ width: 140 }} />
                  <Button disabled={dailySignalTask === null} onClick={() => setDailySignalTaskModalOpen(true)}>
                    查看任务
                  </Button>
                  <Button loading={dailySignalLoading || dailySignalRunning || stockContextsLoading} onClick={fetchDailySignals} type="primary">
                    启动/加载信号
                  </Button>
                </Space>
              </div>
              <div className="signal-layout">
                <div className="signal-list">
                  <Table
                    columns={dailySignalColumns}
                    dataSource={dailySignalResult?.signals ?? []}
                    loading={dailySignalLoading || dailySignalRunning || stockContextsLoading}
                    onRow={(record) => ({ onClick: () => setSelectedSignalKey(signalRowKey(record)) })}
                    pagination={{ pageSize: 30, showSizeChanger: true }}
                    rowClassName={(record) => (signalRowKey(record) === selectedSignalKey ? "selected-row" : "")}
                    rowKey={signalRowKey}
                    scroll={{ x: 865, y: 560 }}
                    size="small"
                  />
                </div>
                <div className="signal-charts">
                  <div className="chart-header">
                    <div className="placeholder-title">{selectedSignal?.code ?? "未选择股票"}</div>
                    <div className="panel-subtitle">{selectedSignal?.code_name ?? "从左侧列表选择一只股票"}</div>
                  </div>
                  {selectedDisplay !== null ? (
                    <div className="signal-plan">
                      <div className="signal-plan-title">{selectedDisplay.title ?? "操作计划"}</div>
                      {selectedDisplay.entry ? <div>{selectedDisplay.entry}</div> : null}
                      {selectedDisplay.watch ? <div>{selectedDisplay.watch}</div> : null}
                      {(selectedDisplay.sell ?? []).map((item) => (
                        <div key={item}>{item}</div>
                      ))}
                    </div>
                  ) : null}
                  {selectedSignalMetrics.length > 0 ? (
                    <div className="signal-metrics">
                      {selectedSignalMetrics.map(([label, value]) => (
                        <div className="signal-metric" key={label}>
                          <span>{label}</span>
                          <strong>{formatSignalExtra(value)}</strong>
                        </div>
                      ))}
                    </div>
                  ) : null}
                  {selectedStockContext === null ? <div className="empty-chart">暂无可渲染的股票上下文</div> : <StockContextCharts context={selectedStockContext} />}
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
                  <div className="panel-subtitle">回测任务已使用独立任务表，列表直接展示结构化统计字段。</div>
                </div>
                <Space>
                  <Button icon={<ReloadOutlined />} onClick={fetchBacktestTasks}>
                    刷新
                  </Button>
                  <Button loading={backtestLoading} onClick={() => setBacktestCreateModalOpen(true)} type="primary">
                    新建回测
                  </Button>
                </Space>
              </div>
              <Table
                columns={backtestTaskColumns}
                dataSource={backtestTasks}
                loading={backtestTasksLoading}
                pagination={{ pageSize: 20, showSizeChanger: true }}
                rowKey={(record) => String(record.id)}
                scroll={{ x: 1900, y: "calc(100vh - 270px)" }}
                size="middle"
              />
            </div>
          </section>
        ) : (
          <section className="placeholder" />
        )}
      </section>
    </main>
  );
}

