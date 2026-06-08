"use client";

import { useEffect, useMemo, useState } from "react";
import { Button, Modal, Space, Table, Tabs, Tag, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import { ReloadOutlined, SyncOutlined } from "@ant-design/icons";

import {
  getMartDataAssetSummary,
  getSourceUpdateTask,
  getStockDataAssetSummary,
  refreshMartDataAssets,
  requestStockDataAssetRefresh,
  stopSourceUpdateTask,
} from "@/lib/api/dataAssets";
import { getHealth } from "@/lib/api/health";
import type {
  DataAssetTask,
  MartDatasetOverview,
  StockDatasetOverview,
} from "@/types/dataAsset";
import type { HealthState } from "@/types/health";
import { formatDateTime } from "@/utils/format";

const tabs = [
  { key: "data-assets", label: "数据资产维护" },
  { key: "daily-signals", label: "当日信号" },
  { key: "backtest-stats", label: "回测统计" },
  { key: "strategies", label: "策略列表" },
] as const;

const subTabs: Record<(typeof tabs)[number]["key"], { key: string; label: string }[]> = {
  "backtest-stats": [{ key: "placeholder", label: "占位" }],
  "daily-signals": [{ key: "placeholder", label: "占位" }],
  "data-assets": [
    { key: "source", label: "源数据" },
    { key: "mart", label: "后处理数据" },
  ],
  strategies: [{ key: "placeholder", label: "占位" }],
};

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
  const sourceUpdateRunning = sourceUpdateTask?.status === "running";
  const [messageApi, contextHolder] = message.useMessage();

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

    try {
      const data = await requestStockDataAssetRefresh();
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
      render: (value: string | null) => formatDateTime(value),
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
      render: (value: string | null) => formatDateTime(value),
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
                    <Button
                      icon={<ReloadOutlined />}
                      loading={datasetsLoading}
                      onClick={fetchStockDataAssets}
                    >
                      刷新
                    </Button>
                    <Button
                      icon={<SyncOutlined />}
                      disabled={sourceUpdateRunning}
                      loading={sourceUpdateRunning}
                      onClick={requestRefresh}
                      type="primary"
                    >
                      更新
                    </Button>
                  </Space>
                </div>
                <Table
                  columns={dataAssetColumns}
                  dataSource={datasets}
                  loading={datasetsLoading}
                  pagination={false}
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
                  rowKey="dataset_name"
                  scroll={{ x: 1410 }}
                  size="middle"
                />
              </div>
            )}
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
