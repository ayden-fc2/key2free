"use client";

import { useEffect, useMemo, useState } from "react";

import { getHealth } from "@/lib/api/health";
import type { HealthState } from "@/types/health";

const tabs = [
  { key: "data-assets", label: "数据资产维护" },
  { key: "daily-signals", label: "当日信号" },
  { key: "backtest-stats", label: "回测统计" },
  { key: "strategies", label: "策略列表" },
] as const;

export default function Home() {
  const [activeTab, setActiveTab] = useState<(typeof tabs)[number]["key"]>(
    "data-assets",
  );
  const [health, setHealth] = useState<HealthState | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);

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

  const activeTabLabel = useMemo(
    () => tabs.find((tab) => tab.key === activeTab)?.label ?? "",
    [activeTab],
  );

  return (
    <main className="app-shell">
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
          <div>
            <div className="eyebrow">管理平台</div>
            <h1>{activeTabLabel}</h1>
          </div>
          <div
            className={health?.status === "ok" ? "health ok" : "health error"}
            title={health?.checked_at ?? healthError ?? "未连接"}
          >
            <span className="health-dot" />
            <span>{health?.status === "ok" ? "Backend OK" : "Backend Down"}</span>
          </div>
        </header>

        <section className="placeholder">
          <div className="placeholder-title">{activeTabLabel}</div>
          <p>该模块后续接入真实功能。</p>
        </section>
      </section>
    </main>
  );
}
