"use client";

import { useEffect, useMemo, useState } from "react";
import { Button, Space, Table, Tabs, Tag, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import { ReloadOutlined, SyncOutlined } from "@ant-design/icons";

import {
  getStockDataAssetSummary,
  requestStockDataAssetRefresh,
} from "@/lib/api/dataAssets";
import { getHealth } from "@/lib/api/health";
import type { StockDatasetOverview } from "@/types/dataAsset";
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
  "data-assets": [{ key: "overview", label: "数据资产一览" }],
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

  async function requestRefresh() {
    try {
      const data = await requestStockDataAssetRefresh();
      messageApi.info(data.message);
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "更新请求失败");
    }
  }

  useEffect(() => {
    if (activeTab === "data-assets") {
      fetchStockDataAssets();
    }
  }, [activeTab]);

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
          status === "ok" ? "green" : status === "warning" ? "orange" : "red";
        return <Tag color={color}>{status}</Tag>;
      },
      title: "状态",
      width: 100,
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

  return (
    <main className="app-shell">
      {contextHolder}
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
              activeKey={activeSubTabs[0].key}
              className="header-tabs"
              items={activeSubTabs}
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
            <div className="table-panel">
              <div className="table-toolbar">
                <div className="placeholder-title">数据集总览</div>
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
                scroll={{ x: 1183 }}
                size="middle"
              />
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
