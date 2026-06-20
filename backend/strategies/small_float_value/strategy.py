from __future__ import annotations

import math
from datetime import date
from typing import Any

import pandas as pd

from app.entities.stock_data_context import SignalDecision
from app.services.strategy_lifecycle import (
    MarketViews,
    StrategyBuyDecision,
    StrategyContext,
    StrategySellDecision,
    StrategyWatchDecision,
)


SMALL_FLOAT_VALUE_TARGET_HOLDINGS = 10
SMALL_FLOAT_VALUE_LOW_PRICE_QUANTILE = 0.10
SMALL_FLOAT_VALUE_CIRC_MV_RANK_START = 1
SMALL_FLOAT_VALUE_CIRC_MV_RANK_END = 10
SMALL_FLOAT_VALUE_MIN_LIST_DAYS = 250
SMALL_FLOAT_VALUE_REQUIRED_COLUMNS: tuple[str, ...] = ()
SMALL_FLOAT_VALUE_REBALANCE_WEEKDAY = 0
SMALL_FLOAT_VALUE_MARKET_INDEX_CODE = "000905.SH"
SMALL_FLOAT_VALUE_MARKET_MA_WINDOW = 20
LIMIT_MOVE_PCT = 9.8
OPEN_LIMIT_MOVE_RATIO = 0.098


def small_float_value_code_filter(code: str) -> bool:
    """Keep common main-board A shares only; ST is filtered by daily row."""
    value = code.lower()
    if value.startswith(("sh.688", "sz.300", "sz.301", "bj.")):
        return False
    return value.startswith("sh.6") or value.startswith("sz.0")


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
        SMALL_FLOAT_VALUE_CIRC_MV_RANK_END,
    )
    low_price_pool = pool.sort_values(
        ["unadjusted_close", "code"],
        ascending=[True, True],
    ).head(low_price_count)
    ranked_by_circ_mv = low_price_pool.sort_values(
        ["selection_circ_mv", "code"],
        ascending=[True, True],
    ).copy()
    ranked_by_circ_mv["circ_mv_rank_in_low_price_pool"] = range(1, len(ranked_by_circ_mv) + 1)
    selected = ranked_by_circ_mv.iloc[
        SMALL_FLOAT_VALUE_CIRC_MV_RANK_START - 1 : SMALL_FLOAT_VALUE_CIRC_MV_RANK_END
    ]

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
                "circ_mv_rank_start": SMALL_FLOAT_VALUE_CIRC_MV_RANK_START,
                "circ_mv_rank_end": SMALL_FLOAT_VALUE_CIRC_MV_RANK_END,
                "circ_mv_rank_in_low_price_pool": int(row.circ_mv_rank_in_low_price_pool),
                "listed_days": int(row.listed_days),
                "eps": float(row.eps_value),
                "close": float(row.unadjusted_close),
                "qfq_close": qfq_close,
                "total_mv": _optional_float(getattr(row, "total_mv", None)),
                "circ_mv": float(row.selection_circ_mv),
                "selection_rule": (
                    "main-board non-ST; listed>=250d; eps>=0; "
                    "unadjusted close lowest 10%; select circ_mv ranks 1-5"
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
                    "circ_mv_rank_in_low_price_pool": int(row.circ_mv_rank_in_low_price_pool),
                    "target_rank": rank,
                },
                "signal": _decision_to_payload(signal),
            }
        )
    return items


class SmallFloatValueLifecycle:
    """Reference lifecycle implementation for portfolio-style strategies."""

    target_size = SMALL_FLOAT_VALUE_TARGET_HOLDINGS
    rebalance_weekday = SMALL_FLOAT_VALUE_REBALANCE_WEEKDAY

    def select_signals(
        self,
        *,
        trade_date: date,
        view: Any,
    ) -> list[dict[str, Any]]:
        if not _is_market_environment_favorable(
            view=view,
            index_code=SMALL_FLOAT_VALUE_MARKET_INDEX_CODE,
            ma_window=SMALL_FLOAT_VALUE_MARKET_MA_WINDOW,
        ):
            return []

        today_rows = view.cross_section(
            columns=(
                "name",
                "list_date",
                "close",
                "qfq_close",
                "is_st",
                "eps",
                "total_mv",
                "circ_mv",
            )
        )
        selected = _select_day(today_rows)
        self._probe_signal_history(
            trade_date=trade_date,
            view=view,
            codes=[item["code"] for item in selected],
        )
        return selected

    def _probe_signal_history(
        self,
        *,
        trade_date: date,
        view: Any,
        codes: list[str],
    ) -> None:
        for _code, frame in view.iter_stock_history(
            columns=("qfq_close",),
            window=200,
            codes=codes,
        ):
            if len(frame) == 0:
                continue
            if len(frame) > 200:
                raise ValueError(f"signal history has {len(frame)} rows, expected <= 200")
            if frame.trade_dates[-1] > trade_date:
                raise ValueError(
                    f"signal history includes {frame.trade_dates[-1]} after {trade_date}"
                )

    def decide_sells(
        self,
        *,
        context: StrategyContext,
        market: MarketViews,
    ) -> list[StrategySellDecision]:
        decisions: list[StrategySellDecision] = []

        for code, holding in context.holdings.items():
            if getattr(holding, "buy_trade_index", context.trade_index) >= context.trade_index:
                continue
            _history_snapshot(market.history_by_code.get(code), context.trade_date)
            bar = market.today_bars.get(code)
            previous_bar = market.previous_bars.get(code)
            if not _is_tradeable_bar(bar):
                continue

            # Daily close exit: yesterday limit-up, today not limit-up.
            if _is_limit_up_bar(previous_bar) and not _is_limit_up_bar(bar):
                close_price = _bar_close(bar)
                if close_price is not None:
                    decisions.append(
                        StrategySellDecision(
                            code=code,
                            price=close_price,
                            quantity=int(holding.quantity),
                            reason="limit_break_close",
                        )
                    )
                continue

            if context.trade_date.weekday() != self.rebalance_weekday:
                continue

            target_codes = set(context.watch_pool)
            if code not in target_codes:
                if _is_open_limit_up_bar(bar):
                    continue
                open_price = _bar_open(bar)
                if open_price is not None:
                    decisions.append(
                        StrategySellDecision(
                            code=code,
                            price=open_price,
                            quantity=int(holding.quantity),
                            reason="rebalance_open",
                        )
                    )
                continue

            if _is_open_limit_up_bar(bar):
                continue
            open_price = _bar_open(bar)
            if open_price is None:
                continue
            target_amount = context.total_asset / max(self.target_size, 1)
            current_amount = open_price * int(holding.quantity)
            excess_amount = current_amount - target_amount
            if excess_amount < open_price * 100:
                continue
            sell_quantity = int(excess_amount // (open_price * 100)) * 100
            if sell_quantity > 0:
                decisions.append(
                    StrategySellDecision(
                        code=code,
                        price=open_price,
                        quantity=sell_quantity,
                        reason="rebalance_trim_open",
                    )
                )

        return decisions

    def decide_buys(
        self,
        *,
        context: StrategyContext,
        market: MarketViews,
    ) -> list[StrategyBuyDecision]:
        if context.trade_date.weekday() != self.rebalance_weekday:
            return []

        target_items = sorted(
            context.watch_pool.values(),
            key=lambda item: (
                _positive_int(_signal_value(item.signal, "target_rank")) or 999999,
                item.code,
            ),
        )[: self.target_size]
        target_amount = context.total_asset / max(self.target_size, 1)
        decisions: list[StrategyBuyDecision] = []
        reserved_cash = 0.0

        for item in target_items:
            code = item.code
            history_snapshot = _history_snapshot(
                market.history_by_code.get(code),
                context.trade_date,
            )
            bar = market.today_bars.get(code)
            if not _is_tradeable_bar(bar):
                continue
            if code not in context.holdings and len(context.holdings) + len(decisions) >= self.target_size:
                continue
            if _is_open_limit_move_bar(bar):
                continue
            if _is_limit_move_bar(market.previous_bars.get(code)):
                continue
            buy_price = _bar_open(bar)
            if buy_price is None:
                continue
            existing = context.holdings.get(code)
            current_quantity = int(existing.quantity) if existing is not None else 0
            current_amount = current_quantity * buy_price
            missing_amount = target_amount - current_amount
            if missing_amount < buy_price * 100:
                continue
            available_cash = max(context.cash - reserved_cash, 0.0)
            quantity = _fixed_amount_quantity(
                cash=available_cash,
                buy_price=buy_price,
                amount=missing_amount,
            )
            if quantity <= 0:
                continue
            amount = buy_price * quantity
            reserved_cash += amount * 1.0005
            decisions.append(
                StrategyBuyDecision(
                    code=code,
                    code_name=item.code_name,
                    price=buy_price,
                    quantity=quantity,
                    signal=_with_history_snapshot(item.signal, history_snapshot),
                )
            )

        return decisions

    def update_watch_pool(
        self,
        *,
        context: StrategyContext,
        raw_signals: list[dict[str, Any]],
    ) -> StrategyWatchDecision:
        if context.trade_index == 0:
            return StrategyWatchDecision(
                add=raw_signals[: self.target_size],
                remove=set(context.watch_pool),
            )
        return StrategyWatchDecision(
            add=raw_signals[: self.target_size],
            remove=set(context.watch_pool),
        )


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
    trade_dates = pd.to_datetime(pool["trade_date"], errors="coerce")
    list_dates = pd.to_datetime(pool["list_date"], errors="coerce")
    return (trade_dates - list_dates).dt.days


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


def _history_snapshot(frame: Any, trade_date: date) -> dict[str, Any]:
    if frame is None or len(frame) == 0:
        return {"history_bars": 0}
    if frame.trade_dates[-1] >= trade_date:
        raise ValueError(
            f"history frame for {frame.code} includes {frame.trade_dates[-1]} at {trade_date}"
        )

    snapshot: dict[str, Any] = {
        "history_bars": int(len(frame)),
        "history_last_date": frame.trade_dates[-1].isoformat(),
    }
    qfq_close = frame.columns.get("qfq_close")
    if qfq_close is None or len(qfq_close) == 0:
        return snapshot

    last_close = _history_float(qfq_close[-1])
    snapshot["history_last_qfq_close"] = last_close
    if last_close is None or last_close <= 0:
        return snapshot

    for window in (5, 10):
        if len(qfq_close) < window:
            continue
        base_close = _history_float(qfq_close[-window])
        if base_close is not None and base_close > 0:
            snapshot[f"history_return_{window}"] = last_close / base_close - 1.0
    return snapshot


def _is_market_environment_favorable(
    *,
    view: Any,
    index_code: str,
    ma_window: int,
) -> bool:
    history = view.index_history(
        index_code,
        columns=("close",),
        window=ma_window,
    )
    if len(history) < ma_window:
        return False

    closes = pd.to_numeric(history["close"], errors="coerce").dropna()
    if len(closes) < ma_window:
        return False

    latest_close = float(closes.iloc[-1])
    moving_average = float(closes.tail(ma_window).mean())
    if not (math.isfinite(latest_close) and math.isfinite(moving_average)):
        return False

    return latest_close >= moving_average


def _with_history_snapshot(signal: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    copied = dict(signal)
    extras = dict(copied.get("extras") or {})
    extras["buy_history_probe"] = snapshot
    copied["extras"] = extras
    return copied


def _history_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _signal_value(signal: dict[str, Any], key: str) -> Any:
    if key in signal:
        return signal[key]
    extras = signal.get("extras")
    if isinstance(extras, dict):
        return extras.get(key)
    return None


def _positive_int(value: Any) -> int | None:
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, float) and value.is_integer() and value > 0:
        return int(value)
    return None


def _bar_open(bar: tuple[float, ...] | None) -> float | None:
    if bar is None or not math.isfinite(bar[0]) or bar[0] <= 0:
        return None
    return float(bar[0])


def _bar_close(bar: tuple[float, ...] | None) -> float | None:
    if bar is None or not math.isfinite(bar[3]) or bar[3] <= 0:
        return None
    return float(bar[3])


def _is_tradeable_bar(bar: tuple[float, ...] | None) -> bool:
    if bar is None:
        return False
    open_price, high, low, close, vol, _pct = bar[:6]
    if not (
        math.isfinite(open_price)
        and math.isfinite(high)
        and math.isfinite(low)
        and math.isfinite(close)
    ):
        return False
    if not math.isfinite(vol) or vol <= 0:
        return False
    return open_price != high or high != low or low != close


def _is_limit_up_bar(bar: tuple[float, ...] | None) -> bool:
    if bar is None or len(bar) < 6:
        return False
    pct_chg = bar[5]
    return math.isfinite(pct_chg) and pct_chg >= LIMIT_MOVE_PCT


def _is_limit_move_bar(bar: tuple[float, ...] | None) -> bool:
    if bar is None or len(bar) < 6:
        return False
    pct_chg = bar[5]
    return math.isfinite(pct_chg) and abs(pct_chg) >= LIMIT_MOVE_PCT


def _is_open_limit_move_bar(bar: tuple[float, ...] | None) -> bool:
    if bar is None or len(bar) < 8:
        return False
    open_price = bar[0]
    pre_close = bar[7]
    if not (math.isfinite(open_price) and math.isfinite(pre_close) and pre_close > 0):
        return False
    return abs(open_price / pre_close - 1.0) >= OPEN_LIMIT_MOVE_RATIO


def _is_open_limit_up_bar(bar: tuple[float, ...] | None) -> bool:
    if bar is None or len(bar) < 8:
        return False
    open_price = bar[0]
    pre_close = bar[7]
    if not (math.isfinite(open_price) and math.isfinite(pre_close) and pre_close > 0):
        return False
    return open_price / pre_close - 1.0 >= OPEN_LIMIT_MOVE_RATIO


def _fixed_amount_quantity(*, cash: float, buy_price: float, amount: float) -> int:
    if buy_price <= 0 or amount <= 0:
        return 0
    cost_per_lot = buy_price * 100 * 1.0005
    lots_by_amount = int(amount // (buy_price * 100))
    lots_by_cash = int(cash // cost_per_lot)
    return max(min(lots_by_amount, lots_by_cash), 0) * 100


small_float_value_lifecycle = SmallFloatValueLifecycle()
