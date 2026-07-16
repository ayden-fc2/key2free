"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Button,
  Checkbox,
  Input,
  InputNumber,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import {
  CloudSyncOutlined,
  LinkOutlined,
  ReloadOutlined,
  SaveOutlined,
} from "@ant-design/icons";

import {
  getNasConnection,
  getNasIncrementalSyncTask,
  getNasRefreshTask,
  getNasRemoteConfig,
  getNasStatus,
  listNasOperationLogs,
  listNasWatermarks,
  startNasIncrementalSync,
  startNasRefresh,
  updateNasConnection,
  updateNasRemoteConfig,
} from "@/lib/api/nasDataAssets";
import type {
  NasConnection,
  NasOperationLog,
  NasRefreshTask,
  NasRemoteConfig,
  NasServiceStatus,
  NasSyncTask,
  NasWatermarkComparison,
} from "@/types/nasDataAsset";
import { formatDateTime } from "@/utils/format";


function yesterdayText() {
  const value = new Date();
  value.setDate(value.getDate() - 1);
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function statusColor(status: string) {
  if (status === "success" || status === "ok" || status === "healthy") return "green";
  if (status === "running" || status === "started") return "blue";
  if (status === "skipped" || status === "rejected") return "gold";
  return "red";
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 * 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MB`;
  return `${(value / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

export function NasDataAssetsPanel() {
  const [messageApi, contextHolder] = message.useMessage();
  const [connection, setConnection] = useState<NasConnection>({
    scheme: "http",
    host: "192.168.1.62",
    port: 18080,
    base_url: "http://192.168.1.62:18080",
  });
  const [remoteConfig, setRemoteConfig] = useState<NasRemoteConfig | null>(null);
  const [status, setStatus] = useState<NasServiceStatus | null>(null);
  const [watermarks, setWatermarks] = useState<NasWatermarkComparison[]>([]);
  const [logs, setLogs] = useState<NasOperationLog[]>([]);
  const [syncTask, setSyncTask] = useState<NasSyncTask | null>(null);
  const [refreshTask, setRefreshTask] = useState<NasRefreshTask | null>(null);
  const [tokenInput, setTokenInput] = useState("");
  const [refreshEndDate, setRefreshEndDate] = useState(yesterdayText);
  const [skipMinutes, setSkipMinutes] = useState(false);
  const [syncMinutes, setSyncMinutes] = useState(true);
  const [loading, setLoading] = useState(false);
  const [savingConnection, setSavingConnection] = useState(false);
  const [savingRemoteConfig, setSavingRemoteConfig] = useState(false);

  async function loadAll(showError = true) {
    setLoading(true);
    try {
      const savedConnection = await getNasConnection();
      setConnection(savedConnection);
      const [nextStatus, nextConfig, nextWatermarks, nextLogs] = await Promise.all([
        getNasStatus(),
        getNasRemoteConfig(),
        listNasWatermarks(),
        listNasOperationLogs(),
      ]);
      setStatus(nextStatus);
      setRemoteConfig(nextConfig);
      setWatermarks(nextWatermarks);
      setLogs(nextLogs);
      try {
        setSyncTask(await getNasIncrementalSyncTask());
      } catch {
        setSyncTask(null);
      }
      try {
        setRefreshTask(await getNasRefreshTask());
      } catch {
        setRefreshTask(null);
      }
    } catch (error) {
      setStatus(null);
      if (showError) {
        messageApi.error(error instanceof Error ? error.message : "NAS 服务连接失败");
      }
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadAll(false);
  }, []);

  useEffect(() => {
    if (syncTask?.status !== "running") return;
    const timer = window.setInterval(() => {
      getNasIncrementalSyncTask()
        .then((task) => {
          setSyncTask(task);
          if (task.status !== "running") {
            void loadAll(false);
          }
        })
        .catch(() => undefined);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [syncTask?.status]);

  useEffect(() => {
    if (refreshTask?.status !== "running") return;
    const timer = window.setInterval(() => {
      getNasRefreshTask(refreshTask.id)
        .then((task) => {
          setRefreshTask(task);
          if (task.status !== "running") void loadAll(false);
        })
        .catch(() => undefined);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [refreshTask?.id, refreshTask?.status]);

  async function saveConnection() {
    setSavingConnection(true);
    try {
      const saved = await updateNasConnection({
        scheme: connection.scheme,
        host: connection.host,
        port: connection.port,
      });
      setConnection(saved);
      messageApi.success("NAS 连接已保存");
      await loadAll(false);
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "NAS 连接失败");
    } finally {
      setSavingConnection(false);
    }
  }

  async function saveRemoteConfig() {
    if (remoteConfig === null) return;
    setSavingRemoteConfig(true);
    try {
      const updated = await updateNasRemoteConfig({
        ...(tokenInput.trim() ? { tushare_token: tokenInput.trim() } : {}),
        tushare_http_url: remoteConfig.tushare_http_url,
        tushare_mcp_url: remoteConfig.tushare_mcp_url,
        tushare_timeout_seconds: remoteConfig.tushare_timeout_seconds,
        schedule_enabled: remoteConfig.schedule_enabled,
        schedule_hour: remoteConfig.schedule_hour,
        schedule_minute: remoteConfig.schedule_minute,
        advertised_host: connection.host,
        advertised_port: connection.port,
      });
      setRemoteConfig(updated);
      setTokenInput("");
      messageApi.success("NAS 配置已热更新");
      await loadAll(false);
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "NAS 配置更新失败");
    } finally {
      setSavingRemoteConfig(false);
    }
  }

  async function runRefresh() {
    try {
      const result = await startNasRefresh({
        end_date: refreshEndDate,
        skip_stk_mins_5min: skipMinutes,
      });
      messageApi.success(result.message);
      if (result.task_id !== null) setRefreshTask(await getNasRefreshTask(result.task_id));
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "NAS 资产更新启动失败");
    }
  }

  async function runSync() {
    try {
      const task = await startNasIncrementalSync(syncMinutes);
      setSyncTask(task);
      messageApi.success("本地增量同步已启动");
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "增量同步启动失败");
    }
  }

  const watermarkColumns: ColumnsType<NasWatermarkComparison> = useMemo(
    () => [
      { dataIndex: "asset_table_name", title: "资产表", width: 230 },
      { dataIndex: "local_trusted_watermark", title: "本地水位", width: 120 },
      { dataIndex: "nas_trusted_watermark", title: "NAS 水位", width: 120 },
      {
        key: "sync_status",
        render: (_, row) => {
          const pending = row.pending || row.metadata_pending;
          return <Tag color={pending ? "gold" : "green"}>{pending ? "待同步" : "一致"}</Tag>;
        },
        title: "同步状态",
        width: 100,
      },
      { dataIndex: "local_issue_count", title: "本地异常", width: 90 },
      { dataIndex: "nas_issue_count", title: "NAS 异常", width: 90 },
      { dataIndex: "nas_last_issue_message", ellipsis: true, title: "最近异常" },
    ],
    [],
  );

  const logColumns: ColumnsType<NasOperationLog> = useMemo(
    () => [
      { dataIndex: "timestamp", render: (value: string) => formatDateTime(value), title: "时间", width: 190 },
      { dataIndex: "operation", title: "操作", width: 150 },
      { dataIndex: "source", title: "来源", width: 90 },
      {
        dataIndex: "status",
        render: (value: string) => <Tag color={statusColor(value)}>{value}</Tag>,
        title: "状态",
        width: 100,
      },
      { dataIndex: "message", ellipsis: true, title: "日志" },
    ],
    [],
  );

  return (
    <section className="content-panel nas-panel">
      {contextHolder}
      <div className="table-toolbar">
        <div>
          <div className="placeholder-title">NAS 数据资产服务</div>
          <div className="panel-subtitle">
            {connection.base_url} / {status?.service ?? "未连接"} / v{status?.version ?? "-"}
          </div>
        </div>
        <Space>
          <Tag color={status?.status === "ok" ? "green" : "red"}>{status?.status === "ok" ? "Connected" : "Disconnected"}</Tag>
          <Button icon={<ReloadOutlined />} loading={loading} onClick={() => void loadAll()}>
            刷新
          </Button>
        </Space>
      </div>

      <div className="nas-config-grid">
        <section className="nas-section">
          <div className="nas-section-title">连接配置</div>
          <div className="nas-form-row">
            <Select
              options={[{ label: "HTTP", value: "http" }, { label: "HTTPS", value: "https" }]}
              value={connection.scheme}
              onChange={(scheme) => setConnection((current) => ({ ...current, scheme }))}
            />
            <Input
              prefix={<LinkOutlined />}
              value={connection.host}
              onChange={(event) => setConnection((current) => ({ ...current, host: event.target.value }))}
            />
            <InputNumber
              min={1}
              max={65535}
              value={connection.port}
              onChange={(port) => setConnection((current) => ({ ...current, port: port ?? 18080 }))}
            />
            <Button icon={<SaveOutlined />} loading={savingConnection} type="primary" onClick={saveConnection}>
              保存并连接
            </Button>
          </div>
        </section>

        <section className="nas-section">
          <div className="nas-section-title">Tushare 与调度</div>
          <div className="nas-form-grid">
            <label className="form-field">
              <span>代理 API</span>
              <Input
                disabled={remoteConfig === null}
                value={remoteConfig?.tushare_http_url ?? ""}
                onChange={(event) => setRemoteConfig((current) => current === null ? current : ({ ...current, tushare_http_url: event.target.value }))}
              />
            </label>
            <label className="form-field">
              <span>Token</span>
              <Input.Password
                disabled={remoteConfig === null}
                placeholder={remoteConfig?.tushare_token_masked || "未配置"}
                value={tokenInput}
                onChange={(event) => setTokenInput(event.target.value)}
              />
            </label>
            <label className="form-field">
              <span>超时秒数</span>
              <InputNumber
                disabled={remoteConfig === null}
                min={1}
                max={300}
                value={remoteConfig?.tushare_timeout_seconds}
                onChange={(value) => setRemoteConfig((current) => current === null ? current : ({ ...current, tushare_timeout_seconds: value ?? 30 }))}
              />
            </label>
            <label className="form-field">
              <span>每日调度</span>
              <Space>
                <Switch
                  checked={remoteConfig?.schedule_enabled ?? false}
                  disabled={remoteConfig === null}
                  onChange={(value) => setRemoteConfig((current) => current === null ? current : ({ ...current, schedule_enabled: value }))}
                />
                <InputNumber
                  disabled={remoteConfig === null}
                  min={0}
                  max={23}
                  value={remoteConfig?.schedule_hour}
                  onChange={(value) => setRemoteConfig((current) => current === null ? current : ({ ...current, schedule_hour: value ?? 2 }))}
                />
                <span>:</span>
                <InputNumber
                  disabled={remoteConfig === null}
                  min={0}
                  max={59}
                  value={remoteConfig?.schedule_minute}
                  onChange={(value) => setRemoteConfig((current) => current === null ? current : ({ ...current, schedule_minute: value ?? 30 }))}
                />
              </Space>
            </label>
          </div>
          <div className="nas-action-row">
            <span>下次执行：{status?.scheduler.next_run_at ? formatDateTime(status.scheduler.next_run_at) : "-"}</span>
            <Button icon={<SaveOutlined />} loading={savingRemoteConfig} disabled={remoteConfig === null} onClick={saveRemoteConfig}>
              热更新配置
            </Button>
          </div>
        </section>
      </div>

      <section className="nas-section nas-runtime-section">
        <div className="table-toolbar">
          <div>
            <div className="nas-section-title">运行与同步</div>
            <div className="panel-subtitle">
              DuckDB: {status?.database.ready ? "Ready" : status?.database.reason ?? "Unknown"} / {formatBytes(status?.database.size_bytes ?? 0)}
            </div>
          </div>
          <Space>
            <input className="target-date-input" type="date" value={refreshEndDate} onChange={(event) => setRefreshEndDate(event.target.value)} />
            <Checkbox checked={skipMinutes} onChange={(event) => setSkipMinutes(event.target.checked)}>更新时跳过5分钟线</Checkbox>
            <Button loading={refreshTask?.status === "running"} onClick={runRefresh}>更新 NAS 资产</Button>
            <Checkbox checked={syncMinutes} onChange={(event) => setSyncMinutes(event.target.checked)}>同步5分钟线</Checkbox>
            <Button icon={<CloudSyncOutlined />} loading={syncTask?.status === "running"} type="primary" onClick={runSync}>
              增量同步到本地
            </Button>
          </Space>
        </div>
        <div className="backtest-summary">
          <Tag color={statusColor(syncTask?.status ?? "idle")}>{syncTask?.status ?? "idle"}</Tag>
          <span>当前资产: {syncTask?.current_asset_table_name ?? "-"}</span>
          <span>进度: {syncTask?.completed_asset_count ?? 0}/{syncTask?.total_asset_count ?? 0}</span>
          <span>导入: {syncTask?.imported_rows ?? 0} 行</span>
          <span>下载: {formatBytes(syncTask?.downloaded_bytes ?? 0)}</span>
        </div>
        {syncTask?.logs ? <pre className="task-log nas-task-log">{syncTask.logs}</pre> : null}
      </section>

      <section className="nas-section nas-runtime-section">
        <div className="nas-section-title">资产水位</div>
        <Table
          columns={watermarkColumns}
          dataSource={watermarks}
          loading={loading}
          pagination={false}
          rowKey="asset_table_name"
          scroll={{ x: 900, y: 260 }}
          size="small"
        />
      </section>

      <section className="nas-section nas-runtime-section">
        <div className="nas-section-title">NAS 操作日志</div>
        <Table
          columns={logColumns}
          dataSource={logs}
          loading={loading}
          pagination={{ pageSize: 20, showSizeChanger: false }}
          rowKey="id"
          scroll={{ x: 850, y: 240 }}
          size="small"
        />
      </section>
    </section>
  );
}
