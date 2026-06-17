from __future__ import annotations

import math
from datetime import date
from typing import Any

import pandas as pd

from app.entities.stock_data_context import SignalDecision


SMALL_FLOAT_VALUE_TARGET_HOLDINGS = 10
SMALL_FLOAT_VALUE_LOW_PRICE_QUANTILE = 0.10
SMALL_FLOAT_VALUE_MIN_LIST_DAYS = 250
SMALL_FLOAT_VALUE_REQUIRED_COLUMNS: tuple[str, ...] = ()


def small_float_value_code_filter(code: str) -> bool:
    """Keep common main-board A shares only; ST is filtered by daily row."""
    value = code.lower()
    if value.startswith(("sh.688", "sz.300", "sz.301", "bj.")):
        return False
    return value.startswith("sh.6") or value.startswith("sz.0")


def small_float_value_portfolio_signal_builder(
    *,
    trade_dates: list[date],
    rows: pd.DataFrame,
) -> dict[date, list[dict[str, Any]]]:
    if rows.empty:
        return {day: [] for day in trade_dates}

    result: dict[date, list[dict[str, Any]]] = {}
    for day, group in rows.groupby("trade_date", sort=True):
        result[day] = _select_day(group)
    for day in trade_dates:
        result.setdefault(day, [])
    return result


def _select_day(group: pd.DataFrame) -> list[dict[str, Any]]:
    pool = group.copy()
    pool["unadjusted_close"] = _numeric_column(pool, "close")
    pool["selection_circ_mv"] = _numeric_column(pool, "circ_mv")
    pool["eps_value"] = _numeric_column(pool, "eps")
    pool["listed_days"] = _listed_days(pool)

    name = pool["name"].fillna("").astype(str).str.upper()
    mask = (
        pool["code"].fillna("").astype(str).apply(small_float_value_code_filter)
        & (pool["is_st"].fillna(0).astype(float) == 0.0)
        & ~name.str.contains("ST", regex=False)
        & (pool["listed_days"] >= SMALL_FLOAT_VALUE_MIN_LIST_DAYS)
        & (pool["eps_value"] >= 0)
        & pool["unadjusted_close"].apply(_positive)
        & pool["selection_circ_mv"].apply(_positive)
    )
    pool = pool[mask.fillna(False)]
    if pool.empty:
        return []

    low_price_count = max(
        int(math.ceil(len(pool) * SMALL_FLOAT_VALUE_LOW_PRICE_QUANTILE)),
        SMALL_FLOAT_VALUE_TARGET_HOLDINGS,
    )
    low_price_pool = pool.sort_values(
        ["unadjusted_close", "code"],
        ascending=[True, True],
    ).head(low_price_count)
    selected = low_price_pool.sort_values(
        ["selection_circ_mv", "code"],
        ascending=[True, True],
    ).head(SMALL_FLOAT_VALUE_TARGET_HOLDINGS)

    items: list[dict[str, Any]] = []
    for rank, row in enumerate(selected.itertuples(index=False), start=1):
        qfq_close = _optional_float(getattr(row, "qfq_close", None))
        signal = SignalDecision(
            triggered=True,
            signal_close=qfq_close,
            max_watch_days=1,
            extras={
                "pattern": "small_float_value_weekly_rebalance",
                "target_rank": rank,
                "target_holdings": SMALL_FLOAT_VALUE_TARGET_HOLDINGS,
                "low_price_quantile": SMALL_FLOAT_VALUE_LOW_PRICE_QUANTILE,
                "listed_days": int(row.listed_days),
                "eps": float(row.eps_value),
                "close": float(row.unadjusted_close),
                "qfq_close": qfq_close,
                "total_mv": _optional_float(getattr(row, "total_mv", None)),
                "circ_mv": float(row.selection_circ_mv),
                "selection_rule": (
                    "main-board non-ST; listed>=250d; eps>=0; "
                    "unadjusted close lowest 10%; select 10 smallest circ_mv"
                ),
                "entry_rule": "previous signal day target, next Monday open rebalance",
                "exit_rule": (
                    "weekly open rebalance when absent from latest target; "
                    "daily close exit after limit-up fails to continue"
                ),
            },
        )
        items.append(
            {
                "code": str(row.code),
                "code_name": None if row.name is None else str(row.name),
                "trade_date": row.trade_date,
                "universe": {
                    "trade_date": row.trade_date.isoformat(),
                    "code": str(row.code),
                    "code_name": None if row.name is None else str(row.name),
                    "listed_days": int(row.listed_days),
                    "eps": float(row.eps_value),
                    "close": float(row.unadjusted_close),
                    "qfq_close": qfq_close,
                    "total_mv": _optional_float(getattr(row, "total_mv", None)),
                    "circ_mv": float(row.selection_circ_mv),
                    "target_rank": rank,
                },
                "signal": _decision_to_payload(signal),
            }
        )
    return items


def _decision_to_payload(decision: SignalDecision) -> dict[str, Any]:
    return {
        "triggered": bool(decision.triggered),
        "signal_close": decision.signal_close,
        "stop_losses": [float(value) for value in decision.stop_losses],
        "take_profits": [float(value) for value in decision.take_profits],
        "max_watch_days": decision.max_watch_days,
        "extras": decision.extras,
    }


def _listed_days(pool: pd.DataFrame) -> pd.Series:
    if "list_date" not in pool.columns:
        return pd.Series(float("nan"), index=pool.index)
    return (pool["trade_date"] - pool["list_date"]).apply(
        lambda value: value.days if hasattr(value, "days") else float("nan")
    )


def _numeric_column(pool: pd.DataFrame, column: str) -> pd.Series:
    if column not in pool.columns:
        return pd.Series(float("nan"), index=pool.index, dtype=float)
    return pd.to_numeric(pool[column], errors="coerce")


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def _positive(value: Any) -> bool:
    return _finite(value) and float(value) > 0


def _optional_float(value: Any) -> float | None:
    return None if not _finite(value) else float(value)
