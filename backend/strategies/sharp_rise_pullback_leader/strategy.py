from __future__ import annotations

import math
import random
from datetime import date
from typing import Any

import pandas as pd

from app.services.strategy_lifecycle import (
    MarketViews,
    StrategyBuyDecision,
    StrategyContext,
    StrategySellDecision,
    StrategyWatchDecision,
)


MIN_PRICE = 15.0
MIN_TURNOVER_RATE = 8.0
SIGNAL_LOOKBACK_BARS = 200
TREND_WINDOW_BARS = 16
MA_STACK_MIN_DAYS = 15
PRE_MA_STACK_LOOKBACK_BARS = 100
LIMIT_UP_LOOKBACK_BARS = 20
LIMIT_UP_PCT_THRESHOLD = 9.8
MAX_LIMIT_UP_STREAK_20 = 3
TREND_HIGH_TO_T_MIN_BARS = 4
TREND_HIGH_TO_T_MAX_BARS = 8
HIGH_TO_CLOSE_PULLBACK_MIN = 0.04
HIGH_TO_CLOSE_PULLBACK_MAX = 0.20
PULLBACK_MA20_LOW = 0.98
PULLBACK_MA10_HIGH = 1.05
ENTRY_CLOSE_MULTIPLE = 1.03
ENTRY_MA10_MULTIPLE = 1.03
WATCH_MAX_DAYS = 5
TRAILING_PROFIT_ENABLE = 1.08
TRAILING_CLOSE_DRAWDOWN = 0.96
POSITION_FRACTION = 0.25

SHARP_RISE_PULLBACK_LEADER_REQUIRED_COLUMNS: tuple[str, ...] = ()

SIGNAL_COLUMNS = (
    "name",
    "close",
    "qfq_open",
    "qfq_high",
    "qfq_low",
    "qfq_close",
    "ma_10",
    "ma_20",
    "ma_30",
    "pct_chg",
    "is_st",
    "turnover_rate",
)


def sharp_rise_pullback_leader_code_filter(code: str) -> bool:
    """Keep main-board A shares only."""
    value = code.lower()
    if value.startswith(("sh.688", "sz.300", "sz.301", "bj.")):
        return False
    return value.startswith("sh.6") or value.startswith("sz.0")


class SharpRisePullbackLeaderLifecycle:
    """MA trend pullback strategy using the generic backtest lifecycle."""

    def select_signals(
        self,
        *,
        trade_date: date,
        view: Any,
    ) -> list[dict[str, Any]]:
        rows = view.to_frame(columns=SIGNAL_COLUMNS, window=SIGNAL_LOOKBACK_BARS)
        if rows.empty:
            return []

        rows = rows.sort_values(["code", "trade_date"]).copy()
        rows["_trade_date"] = pd.to_datetime(rows["trade_date"], errors="coerce").dt.date
        rows["_window_position"] = rows.groupby("code", sort=False).cumcount()
        numeric_columns = (
            "close",
            "qfq_high",
            "qfq_low",
            "qfq_close",
            "ma_10",
            "ma_20",
            "ma_30",
            "pct_chg",
            "is_st",
            "turnover_rate",
        )
        for column in numeric_columns:
            rows[column] = pd.to_numeric(rows[column], errors="coerce")

        latest = rows.groupby("code", sort=False).tail(1).copy()
        latest = latest[latest["_trade_date"] == trade_date]
        if latest.empty:
            return []

        names = latest.get("name", pd.Series("", index=latest.index)).fillna("").astype(str)
        base_mask = (
            latest["code"].astype(str).apply(sharp_rise_pullback_leader_code_filter)
            & ~names.str.upper().str.contains("ST", regex=False)
            & (latest["is_st"].fillna(0.0) == 0.0)
            & (latest["close"] >= MIN_PRICE)
            & (latest["turnover_rate"] >= MIN_TURNOVER_RATE)
            & latest["qfq_low"].notna()
            & latest["qfq_close"].notna()
            & latest["ma_10"].notna()
            & latest["ma_20"].notna()
            & latest["ma_30"].notna()
        )
        latest = latest[base_mask.fillna(False)].copy()
        if latest.empty:
            return []

        candidate_codes = set(latest["code"].astype(str))
        candidate_rows = rows[rows["code"].astype(str).isin(candidate_codes)].copy()
        counts = candidate_rows.groupby("code", sort=False).size()
        full_window_codes = set(counts[counts >= SIGNAL_LOOKBACK_BARS].index.astype(str))
        if not full_window_codes:
            return []
        candidate_rows = candidate_rows[candidate_rows["code"].astype(str).isin(full_window_codes)]
        latest = latest[latest["code"].astype(str).isin(full_window_codes)]
        if latest.empty:
            return []

        signals: list[dict[str, Any]] = []
        rows_by_code = {
            str(code): group
            for code, group in candidate_rows.groupby("code", sort=False)
        }
        latest_by_code = latest.set_index("code")
        for code, row in latest_by_code.iterrows():
            code_rows = rows_by_code.get(str(code))
            if code_rows is None:
                continue
            trend_rows = code_rows.tail(TREND_WINDOW_BARS).copy()
            if len(trend_rows) < TREND_WINDOW_BARS:
                continue
            if not _has_bullish_ma_stack(trend_rows):
                continue

            limit_stats = _limit_up_stats_before_signal(
                code_rows,
                trade_date=trade_date,
            )
            if limit_stats["max_streak"] > MAX_LIMIT_UP_STREAK_20:
                continue

            today_low = _to_float(row.get("qfq_low"))
            today_high = _to_float(row.get("qfq_high"))
            today_close = _to_float(row.get("qfq_close"))
            ma10 = _to_float(row.get("ma_10"))
            ma20 = _to_float(row.get("ma_20"))
            close = _to_float(row.get("close"))
            turnover_rate = _to_float(row.get("turnover_rate"))
            if (
                today_low is None
                or today_high is None
                or today_close is None
                or ma10 is None
                or ma20 is None
                or close is None
                or turnover_rate is None
            ):
                continue
            if today_close < ma20 * PULLBACK_MA20_LOW or today_close > ma10 * PULLBACK_MA10_HIGH:
                continue

            high_row = _highest_row(trend_rows)
            high_date = _as_date(high_row.get("trade_date"))
            high_price = _to_float(high_row.get("qfq_high"))
            high_position = _to_int(high_row.get("_window_position"))
            today_position = _to_int(row.get("_window_position"))
            if high_date is None or high_price is None or high_price <= 0 or high_position is None or today_position is None:
                continue
            ma_stack_context = _ma_stack_context(
                code_rows,
                today_position=today_position,
                today_close=today_close,
            )
            if ma_stack_context is None:
                continue
            if ma_stack_context["stack_days"] < MA_STACK_MIN_DAYS:
                continue
            high_to_t_bars = today_position - high_position
            if high_to_t_bars < TREND_HIGH_TO_T_MIN_BARS or high_to_t_bars > TREND_HIGH_TO_T_MAX_BARS:
                continue
            high_to_close_pullback = (high_price - today_close) / high_price
            if high_to_close_pullback < HIGH_TO_CLOSE_PULLBACK_MIN or high_to_close_pullback > HIGH_TO_CLOSE_PULLBACK_MAX:
                continue
            after_high_before_t = code_rows[
                (code_rows["_window_position"] > high_position)
                & (code_rows["_window_position"] < today_position)
            ]
            if after_high_before_t.empty:
                continue
            prior_lower_lows = after_high_before_t["qfq_low"].dropna()
            if prior_lower_lows.empty or not bool((prior_lower_lows < today_low).any()):
                continue

            entry_trigger_price = min(today_close * ENTRY_CLOSE_MULTIPLE, ma10 * ENTRY_MA10_MULTIPLE)
            code_name = None if pd.isna(row.get("name")) else str(row.get("name"))
            extras = {
                "pattern": "sharp_rise_pullback_leader",
                "signal_lookback_bars": SIGNAL_LOOKBACK_BARS,
                "trend_window_bars": TREND_WINDOW_BARS,
                "ma_stack_min_days": MA_STACK_MIN_DAYS,
                "pre_ma_stack_lookback_bars": PRE_MA_STACK_LOOKBACK_BARS,
                "ma_stack_rule": f"ma10 > ma20 > ma30 for at least {MA_STACK_MIN_DAYS} consecutive trading days through T",
                "ma_stack_first_date": ma_stack_context["first_date"],
                "ma_stack_days": ma_stack_context["stack_days"],
                "pre_ma_stack_max_high": ma_stack_context["pre_max_high"],
                "pre_ma_stack_max_high_vs_signal_close": ma_stack_context["pre_max_high_vs_close"],
                "pre_ma_stack_no_price_reach_signal_close": True,
                "limit_up_pct_threshold": LIMIT_UP_PCT_THRESHOLD,
                "limit_up_days_20": limit_stats["limit_days"],
                "max_limit_up_streak_20": limit_stats["max_streak"],
                "max_allowed_limit_up_streak_20": MAX_LIMIT_UP_STREAK_20,
                "trend_high_date": high_date.isoformat(),
                "trend_high": float(high_price),
                "trend_high_to_t_bars": int(high_to_t_bars),
                "trend_high_to_t_min_bars": TREND_HIGH_TO_T_MIN_BARS,
                "trend_high_to_t_max_bars": TREND_HIGH_TO_T_MAX_BARS,
                "high_to_close_pullback": float(high_to_close_pullback),
                "high_to_close_pullback_min": HIGH_TO_CLOSE_PULLBACK_MIN,
                "high_to_close_pullback_max": HIGH_TO_CLOSE_PULLBACK_MAX,
                "signal_low": float(today_low),
                "signal_high": float(today_high),
                "signal_close": float(today_close),
                "signal_ma10": float(ma10),
                "signal_ma20": float(ma20),
                "pullback_ma20_low": PULLBACK_MA20_LOW,
                "pullback_ma10_high": PULLBACK_MA10_HIGH,
                "entry_close_multiple": ENTRY_CLOSE_MULTIPLE,
                "entry_ma10_multiple": ENTRY_MA10_MULTIPLE,
                "entry_trigger_price": float(entry_trigger_price),
                "watch_max_days": WATCH_MAX_DAYS,
                "turnover_rate": float(turnover_rate),
                "close": float(close),
                "entry_rule": "within 5 trading days, buy when intraday high reaches min(T close*1.03, T MA10*1.03)",
                "exit_rule": (
                    "intraday low below signal low; "
                    "max intraday profit since buy>=8% and close drawdown from max high>=4%"
                ),
            }
            signal_payload = {
                "triggered": True,
                "signal_close": float(today_close),
                "entry_trigger_price": float(entry_trigger_price),
                "sell_rules": [
                    {
                        "name": "T日低点静态止损",
                        "rule_type": "static",
                        "timing": "盘中",
                        "trigger_price": float(today_low),
                        "sell_price": float(today_low),
                        "description": "持仓后任一交易日盘中最低价跌破T日前复权盘中最低价，按T日低点卖出。",
                    },
                    {
                        "name": "最大浮盈回撤止盈",
                        "rule_type": "dynamic",
                        "timing": "收盘",
                        "trigger_price": None,
                        "sell_price": "当日收盘价",
                        "description": "买入后最大盘中浮盈达到8%后，若收盘价相对买入以来最高价回撤达到4%，按当日收盘价卖出。",
                    },
                ],
                "max_watch_days": WATCH_MAX_DAYS,
                "display": {
                    "title": "急涨回踩龙头战术",
                    "signal_date": trade_date.isoformat(),
                    "entry": f"T+1起最多观察{WATCH_MAX_DAYS}个交易日，盘中最高价达到 {entry_trigger_price:.3f} 时按该阈值买入。",
                    "watch": f"观察期间若盘中最低价跌破T日低点 {today_low:.3f}，收盘后移出观察池。",
                    "sell": [
                        f"静态止损：盘中跌破T日低点 {today_low:.3f}，按 {today_low:.3f} 卖出。",
                        "动态止盈：买入后最大盘中浮盈达到8%后，若收盘价相对买入以来最高价回撤达到4%，按当日收盘价卖出。",
                    ],
                },
                "extras": extras,
            }
            signals.append(
                {
                    "code": code,
                    "code_name": code_name,
                    "trade_date": trade_date,
                    "universe": {
                        "trade_date": trade_date.isoformat(),
                        "code": code,
                        "code_name": code_name,
                        **extras,
                    },
                    "signal": signal_payload,
                }
            )

        return signals

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
            bar = market.today_bars.get(code)
            if not _is_tradeable_bar(bar):
                continue

            signal_low = _signal_extra_float(getattr(holding, "signal", {}), "signal_low")
            today_high = _bar_high(bar)
            today_low = _bar_low(bar)
            today_close = _bar_close(bar)
            if today_high is None or today_low is None or today_close is None:
                continue

            max_high_since_buy = max(_to_positive_float(getattr(holding, "max_high_since_buy", None)) or holding.buy_price, today_high)
            holding.max_high_since_buy = max_high_since_buy

            if signal_low is not None and today_low < signal_low:
                decisions.append(
                    StrategySellDecision(
                        code=code,
                        price=signal_low,
                        quantity=int(holding.quantity),
                        reason="intraday_break_signal_low",
                    )
                )
                continue

            if (
                max_high_since_buy >= holding.buy_price * TRAILING_PROFIT_ENABLE
                and today_close <= max_high_since_buy * TRAILING_CLOSE_DRAWDOWN
            ):
                decisions.append(
                    StrategySellDecision(
                        code=code,
                        price=today_close,
                        quantity=int(holding.quantity),
                        reason="max_profit_close_drawdown_4pct",
                    )
                )
                continue

        return decisions

    def decide_buys(
        self,
        *,
        context: StrategyContext,
        market: MarketViews,
    ) -> list[StrategyBuyDecision]:
        decisions: list[StrategyBuyDecision] = []
        reserved_cash = 0.0
        candidates: list[tuple[Any, float, float]] = []

        for item in context.watch_pool.values():
            if item.code in context.holdings:
                continue
            bar = market.today_bars.get(item.code)
            if not _is_tradeable_bar(bar):
                continue
            entry_price = _signal_extra_float(item.signal, "entry_trigger_price")
            today_open = _bar_open(bar)
            today_high = _bar_high(bar)
            if entry_price is None or today_open is None or today_high is None:
                continue
            if today_high < entry_price:
                continue
            buy_price = entry_price
            candidates.append((item, buy_price, entry_price))

        for item, buy_price, entry_price in _randomized_candidates(candidates, context=context):
            signal = _with_entry_fields(
                item.signal,
                watch_trade_days=context.trade_index - item.added_trade_index,
                entry_trigger_price=entry_price,
            )
            quantity = _buy_quantity(
                cash=max(context.cash - reserved_cash, 0.0),
                price=buy_price,
                max_amount=max(context.total_asset * POSITION_FRACTION, 0.0),
            )
            if quantity <= 0:
                continue
            reserved_cash += buy_price * quantity * 1.0005
            decisions.append(
                StrategyBuyDecision(
                    code=item.code,
                    code_name=item.code_name,
                    price=buy_price,
                    quantity=quantity,
                    signal=signal,
                )
            )

        return decisions

    def update_watch_pool(
        self,
        *,
        context: StrategyContext,
        raw_signals: list[dict[str, Any]],
        market: MarketViews | None = None,
    ) -> StrategyWatchDecision:
        held = set(context.holdings)
        keep: set[str] = set()
        remove: set[str] = set()
        for code, item in context.watch_pool.items():
            if code in held:
                remove.add(code)
                continue
            if item.max_watch_days is None or context.trade_index - item.added_trade_index >= item.max_watch_days:
                remove.add(code)
                continue
            if _watch_breaks_signal_low(code=code, item=item, market=market):
                remove.add(code)
                continue
            keep.add(code)
        return StrategyWatchDecision(
            add=[signal for signal in raw_signals if str(signal.get("code")) not in held],
            keep=keep,
            remove=remove,
        )


def _has_bullish_ma_stack(rows: pd.DataFrame) -> bool:
    required = rows[["ma_10", "ma_20", "ma_30"]].dropna()
    if len(required) != len(rows):
        return False
    return bool(((required["ma_10"] > required["ma_20"]) & (required["ma_20"] > required["ma_30"])).all())


def _ma_stack_context(
    rows: pd.DataFrame,
    *,
    today_position: int,
    today_close: float,
) -> dict[str, Any] | None:
    ordered = rows.sort_values("trade_date").reset_index(drop=True)
    matches = ordered.index[ordered["_window_position"] == today_position].tolist()
    if not matches:
        return None
    today_index = int(matches[-1])
    first_index = today_index
    while first_index > 0 and _row_has_bullish_ma_stack(ordered.iloc[first_index - 1]):
        first_index -= 1
    previous_rows = ordered.iloc[max(0, first_index - PRE_MA_STACK_LOOKBACK_BARS):first_index]
    if len(previous_rows) < PRE_MA_STACK_LOOKBACK_BARS:
        return None
    pre_highs = previous_rows["qfq_high"].dropna()
    if len(pre_highs) < PRE_MA_STACK_LOOKBACK_BARS:
        return None
    pre_max_high = _to_float(pre_highs.max())
    first_row = ordered.iloc[first_index]
    first_date = _as_date(first_row.get("trade_date"))
    if pre_max_high is None or first_date is None:
        return None
    if pre_max_high >= today_close:
        return None
    return {
        "first_date": first_date.isoformat(),
        "stack_days": int(today_index - first_index + 1),
        "pre_max_high": float(pre_max_high),
        "pre_max_high_vs_close": float(pre_max_high / today_close - 1),
    }


def _row_has_bullish_ma_stack(row: pd.Series) -> bool:
    ma10 = _to_float(row.get("ma_10"))
    ma20 = _to_float(row.get("ma_20"))
    ma30 = _to_float(row.get("ma_30"))
    return ma10 is not None and ma20 is not None and ma30 is not None and ma10 > ma20 > ma30


def _highest_row(rows: pd.DataFrame) -> pd.Series:
    # Use the latest occurrence when equal highs appear, so the post-high pullback check is strict.
    max_high = rows["qfq_high"].max()
    return rows[rows["qfq_high"] == max_high].tail(1).iloc[0]


def _history_last_float(frame: Any, name: str) -> float | None:
    if frame is None:
        return None
    values = frame.columns.get(name)
    if values is None or len(values) == 0:
        return None
    return _to_float(values[-1])


def _limit_up_stats_before_signal(
    rows: pd.DataFrame,
    *,
    trade_date: date,
) -> dict[str, int]:
    previous_rows = rows[rows["_trade_date"] < trade_date].tail(LIMIT_UP_LOOKBACK_BARS)
    max_streak = 0
    current_streak = 0
    limit_days = 0
    for value in previous_rows["pct_chg"].tolist():
        pct_chg = _to_float(value)
        if pct_chg is not None and pct_chg >= LIMIT_UP_PCT_THRESHOLD:
            limit_days += 1
            current_streak += 1
            max_streak = max(max_streak, current_streak)
        else:
            current_streak = 0
    return {"limit_days": limit_days, "max_streak": max_streak}


def _watch_breaks_signal_low(*, code: str, item: Any, market: MarketViews | None) -> bool:
    if market is None:
        return False
    bar = market.today_bars.get(code)
    today_low = _bar_low(bar)
    signal_low = _signal_extra_float(item.signal, "signal_low")
    if today_low is None or signal_low is None:
        return False
    return today_low < signal_low


def _to_float(value: Any) -> float | None:
    if isinstance(value, pd.Timestamp):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    return numeric


def _to_int(value: Any) -> int | None:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return None
    return numeric


def _as_date(value: Any) -> date | None:
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return None
        return value.date()
    if isinstance(value, date):
        return value
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(timestamp):
        return None
    return timestamp.date()


def _bar_field(bar: tuple[float, ...] | None, index: int) -> float | None:
    if bar is None or len(bar) <= index:
        return None
    return _to_positive_float(bar[index])


def _to_positive_float(value: Any) -> float | None:
    numeric = _to_float(value)
    if numeric is None or numeric <= 0:
        return None
    return numeric


def _bar_open(bar: tuple[float, ...] | None) -> float | None:
    return _bar_field(bar, 0)


def _bar_high(bar: tuple[float, ...] | None) -> float | None:
    return _bar_field(bar, 1)


def _bar_low(bar: tuple[float, ...] | None) -> float | None:
    return _bar_field(bar, 2)


def _bar_close(bar: tuple[float, ...] | None) -> float | None:
    return _bar_field(bar, 3)


def _is_tradeable_bar(bar: tuple[float, ...] | None) -> bool:
    if bar is None or len(bar) < 5:
        return False
    open_price, high, low, close, volume = bar[:5]
    return (
        _to_positive_float(open_price) is not None
        and _to_positive_float(high) is not None
        and _to_positive_float(low) is not None
        and _to_positive_float(close) is not None
        and _to_positive_float(volume) is not None
        and (open_price != high or high != low or low != close)
    )


def _buy_quantity(*, cash: float, price: float, max_amount: float) -> int:
    if cash <= 0 or price <= 0:
        return 0
    amount = min(cash, max_amount)
    lots = int(amount // (price * 100 * 1.0005))
    return lots * 100 if lots > 0 else 0


def _randomized_candidates(
    candidates: list[tuple[Any, float, float]],
    *,
    context: StrategyContext,
) -> list[tuple[Any, float, float]]:
    items = sorted(candidates, key=lambda item: (item[0].added_trade_index, item[0].code))
    seed = f"{context.params.get('run_no', 1)}:{context.trade_date.isoformat()}"
    rng = random.Random(seed)
    rng.shuffle(items)
    return items


def _signal_extra_float(signal: dict[str, Any], name: str) -> float | None:
    extras = signal.get("extras") if isinstance(signal, dict) else None
    if not isinstance(extras, dict):
        return None
    return _to_positive_float(extras.get(name))


def _with_entry_fields(
    signal: dict[str, Any],
    *,
    watch_trade_days: int,
    entry_trigger_price: float,
) -> dict[str, Any]:
    copied = dict(signal)
    extras = dict(copied.get("extras") or {})
    extras["watch_trade_days"] = watch_trade_days
    extras["actual_entry_trigger_price"] = entry_trigger_price
    copied["extras"] = extras
    return copied


sharp_rise_pullback_leader_lifecycle = SharpRisePullbackLeaderLifecycle()
