"""黄金柱形态归因分析：放宽阈值生成候选样本，模拟交易结果，对比成功/失败的宽表特征。

直接运行（需独占 DuckDB）：.venv/Scripts/python.exe scripts/golden_pillar_analysis.py
"""
from __future__ import annotations

import math
from datetime import date

import numpy as np

from app.repositories.backtest_repository import BacktestRepository
from app.repositories.signal_repository import SignalRepository
from app.services.signal_service import SignalService
from app.services.signal_window import SIGNAL_WINDOW_BARS
import strategies.golden_pillar.strategy as G

START = date(2019, 1, 1)
END = date(2024, 12, 31)
FWD_END = date(2025, 6, 30)  # 留出出场窗口

RELAXED = {
    "BASE_MAX_ER_10": 0.40,
    "BASE_MAX_VOLUME_SHRINK_RATIO": 1.05,
    "PILLAR_MIN_BODY_RANGE_RATIO": 0.7,
    "PILLAR_MIN_BODY_ATR14_RATIO": 1.2,
    "PILLAR_MIN_PCT_CHG": 5.0,
    "PILLAR_MIN_VOLUME_MULTIPLE": 1.5,
    "TEST_MAX_BODY_ATR14_RATIO": 0.8,
    "TEST_MAX_VOLUME_VS_PILLAR": 1.0,
    "PILLAR_HOLD_RATIO": 0.7,
    "PRE_PILLAR_CLEAN_DAYS": 0,
    "ENABLE_HIGH_POSITION_FILTER": False,
}

ANALYSIS_COLUMNS = (
    "er_10", "er_20", "avg_volume_5", "avg_volume_10", "avg_volume_20",
    "body_atr14_ratio", "body_range_ratio", "volume_ratio_20", "pct_chg",
    "boll_percent_b_20_2", "roc_60", "roc_120", "bias_120", "atr_pct_30",
)


def main() -> None:
    saved = {key: getattr(G, key) for key in RELAXED}
    for key, value in RELAXED.items():
        setattr(G, key, value)
    try:
        repo = BacktestRepository()
        days = repo.get_trading_dates(start_date=START, end_date=END)
        results = SignalService().get_signals_for_dates_by_stock(
            trade_dates=days, strategy_name="golden_pillar",
        )
    finally:
        for key, value in saved.items():
            setattr(G, key, value)

    candidates: dict[str, list[date]] = {}
    for day, result in results.items():
        for item in result.signals:
            candidates.setdefault(item.code, []).append(day)
    total = sum(len(v) for v in candidates.values())
    print(f"候选样本: {total} 个 ({len(candidates)} 只股票)")

    signal_repo = SignalRepository()
    rows = []
    codes = sorted(candidates)
    for start in range(0, len(codes), 300):
        batch = codes[start : start + 300]
        frames = signal_repo.load_stock_frames(
            codes=batch, start_date=START, end_date=FWD_END,
            window=SIGNAL_WINDOW_BARS, extra_columns=ANALYSIS_COLUMNS,
        )
        for code in batch:
            frame = frames.get(code)
            if frame is None:
                continue
            index_by_date = {d: i for i, d in enumerate(frame.trade_dates)}
            c = frame.columns
            for day in candidates[code]:
                t = index_by_date.get(day)
                if t is None or t < 83:
                    continue
                row = analyze_one(code, day, t, c)
                if row is not None:
                    rows.append(row)

    print(f"有效样本(可入场+特征齐全): {len(rows)}")
    report(rows)


def analyze_one(code: str, day: date, t: int, c: dict) -> dict | None:
    opens, highs, lows, closes, vols = (
        c["qfq_open"], c["qfq_high"], c["qfq_low"], c["qfq_close"], c["vol"],
    )
    p, b = t - 3, t - 4
    height = closes[p] - opens[p]
    if not height > 0:
        return None
    buy_i = t + 1
    if buy_i >= len(closes):
        return None
    if not (vols[buy_i] > 0 and np.isfinite(opens[buy_i]) and np.isfinite(closes[buy_i])):
        return None
    if opens[buy_i] == highs[buy_i] == lows[buy_i] == closes[buy_i]:
        return None
    buy = float(opens[buy_i])

    stops = [buy - 0.5 * height, buy + 0.5 * height]
    takes = [buy + height, buy + 1.5 * height]
    level, position, pnl = 0, 1.0, 0.0
    label = "timeout"
    last_close = buy
    for i in range(buy_i + 1, min(buy_i + 16, len(closes))):
        if not (vols[i] > 0 and np.isfinite(closes[i])):
            continue
        o, h, cl = float(opens[i]), float(highs[i]), float(closes[i])
        last_close = cl
        tp = takes[level]
        if o >= tp or h >= tp:
            price = o if o >= tp else tp
            if level == 0:
                pnl += 0.5 * (price - buy)
                position, level = 0.5, 1
                label = "tp"
            else:
                pnl += position * (price - buy)
                position = 0.0
                label = "tp"
                break
        if position > 0 and cl <= stops[level]:
            pnl += position * (cl - buy)
            position = 0.0
            if label != "tp":
                label = "stop"
            break
    if position > 0:
        pnl += position * (last_close - buy)
    ret = pnl / buy

    def val(col, i):
        v = c[col][i]
        return float(v) if np.isfinite(v) else math.nan

    hist_start = max(p - 60, 0)
    clean_start = max(p - 20, 0)
    feats = {
        "code": code, "date": str(day), "ret": ret, "label": label,
        "er10_t4": val("er_10", b),
        "volshrink": val("avg_volume_5", b) / val("avg_volume_20", b),
        "pillar_pct": val("pct_chg", p),
        "pillar_body_atr": val("body_atr14_ratio", p),
        "pillar_vr20": val("volume_ratio_20", p),
        "pillar_volmult": float(vols[p]) / val("avg_volume_10", b),
        "breakout": float(closes[p]) / float(np.nanmax(highs[hist_start:p])) - 1,
        "clean_max_body": float(np.nanmax(c["body_atr14_ratio"][clean_start:p])),
        "clean_max_vr": float(np.nanmax(c["volume_ratio_20"][clean_start:p])),
        "test_vol_ratio": float(np.nanmean(vols[t - 2 : t + 1])) / float(vols[p]),
        "hold_depth": (float(np.nanmin(closes[t - 2 : t + 1])) - float(opens[p])) / height,
        "t_close_vs_pillar": (float(closes[t]) - float(closes[p])) / height,
        "pb20_t": val("boll_percent_b_20_2", t),
        "roc60_t": val("roc_60", t),
        "roc120_t": val("roc_120", t),
        "bias120_t": val("bias_120", t),
        "atrp30_t": val("atr_pct_30", t),
        "er20_t": val("er_20", t),
    }
    return feats


def report(rows: list[dict]) -> None:
    import pandas as pd

    df = pd.DataFrame(rows)
    df["win"] = df.ret > 0
    print(f"\n总体: 胜率={df.win.mean():.1%} 平均收益={df.ret.mean():+.2%} 中位={df.ret.median():+.2%}")
    print("结局分布:", df.label.value_counts().to_dict())
    print("各结局平均收益:", df.groupby("label").ret.mean().round(4).to_dict())

    feature_cols = [
        "er10_t4", "volshrink", "pillar_pct", "pillar_body_atr", "pillar_vr20",
        "pillar_volmult", "breakout", "clean_max_body", "clean_max_vr",
        "test_vol_ratio", "hold_depth", "t_close_vs_pillar", "pb20_t",
        "roc60_t", "roc120_t", "bias120_t", "atrp30_t", "er20_t",
    ]
    print("\n=== 盈亏组特征中位数对比 ===")
    med = df.groupby("win")[feature_cols].median().T
    med.columns = ["亏", "盈"]
    med["差"] = med["盈"] - med["亏"]
    print(med.round(3).to_string())

    print("\n=== 单特征分桶胜率/平均收益（四分位） ===")
    for col in feature_cols:
        series = df[col].dropna()
        if series.nunique() < 8:
            continue
        try:
            buckets = pd.qcut(df[col], 4, duplicates="drop")
        except ValueError:
            continue
        grouped = df.groupby(buckets, observed=True).agg(n=("win", "size"), wr=("win", "mean"), avg=("ret", "mean"))
        spread = grouped.wr.max() - grouped.wr.min()
        if spread >= 0.08:
            print(f"\n[{col}] 胜率极差 {spread:.0%}")
            for interval, r in grouped.iterrows():
                print(f"  {interval}: n={r.n:.0f} 胜率={r.wr:.0%} 均收={r.avg:+.1%}")

    df.to_csv("scripts/golden_pillar_candidates.csv", index=False)
    print("\n明细已存 scripts/golden_pillar_candidates.csv")


if __name__ == "__main__":
    main()
