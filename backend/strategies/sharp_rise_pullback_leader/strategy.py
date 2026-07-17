from __future__ import annotations

import math
import random
from datetime import date
from functools import lru_cache
from typing import Any

import pandas as pd

from app.repositories.duckdb_repository import DuckDBRepository
from app.services.strategy_lifecycle import (
    MarketViews,
    StrategyBuyDecision,
    StrategyContext,
    StrategySellDecision,
    StrategyWatchDecision,
)


MIN_UNADJUSTED_CLOSE = 10.0
MIN_TURNOVER_RATE = 6.0
SIGNAL_LOOKBACK_BARS = 200
MIN_MA_STACK_DISTANCE = 17
HIGH_TO_T_MIN_BARS = 3
HIGH_TO_T_MAX_BARS = 10
MIN_HIGH_TO_LOW_DRAWDOWN = 0.07
L_MA20_MIN_MULTIPLE = 0.95
L_MA10_MAX_MULTIPLE = 1.02
T_CLOSE_MA10_MIN_MULTIPLE = 0.95
T_CLOSE_MA10_MAX_MULTIPLE = 1.02
BUY_T_CLOSE_CONFIRMATION_MULTIPLE = 1.02
T_CLOSE_STOP_MULTIPLE = 0.90
WATCH_MAX_DAYS = 5
PROFIT_ACTIVATION_GAIN = 0.06
PROFIT_ACTIVATION_MULTIPLE = 1.0 + PROFIT_ACTIVATION_GAIN
ENABLE_TRAILING_EXIT = True
ENABLE_CLOSE_WEAKNESS_EXIT = False
CLOSE_WEAKNESS_MAX_DAILY_RETURN = 0.015
TRAILING_DRAWDOWN = 0.04
TRAILING_REMAINING_MULTIPLE = 1.0 - TRAILING_DRAWDOWN
MAX_BUY_AMOUNT = 2_000.0

SHARP_RISE_PULLBACK_LEADER_REQUIRED_COLUMNS: tuple[str, ...] = ()

SIGNAL_COLUMNS = (
    "name",
    "close",
    "qfq_high",
    "qfq_low",
    "qfq_close",
    "ma_10",
    "ma_20",
    "ma_30",
    "is_st",
    "turnover_rate",
)


class SharpRisePullbackLeaderLifecycle:
    """S-H-L-T pullback lifecycle using only information visible at each stage."""

    def select_signals(
        self,
        *,
        trade_date: date,
        view: Any,
    ) -> list[dict[str, Any]]:
        latest = view.cross_section(columns=SIGNAL_COLUMNS)
        if latest.empty:
            return []

        latest = latest.copy()
        for column in (
            "close",
            "qfq_high",
            "qfq_low",
            "qfq_close",
            "ma_10",
            "ma_20",
            "ma_30",
            "is_st",
            "turnover_rate",
        ):
            if column in latest.columns:
                latest[column] = pd.to_numeric(latest[column], errors="coerce")

        required = {
            "code",
            "close",
            "qfq_high",
            "qfq_low",
            "qfq_close",
            "ma_10",
            "ma_20",
            "ma_30",
            "is_st",
            "turnover_rate",
        }
        if not required.issubset(latest.columns):
            return []

        names = latest.get("name", pd.Series("", index=latest.index)).fillna("").astype(str)
        codes = latest["code"].fillna("").astype(str).str.lower()
        latest = latest[
            ~codes.str.startswith("sh.688")
            & ~names.str.upper().str.contains("ST", regex=False)
            & (latest["is_st"].fillna(0.0) == 0.0)
            & (latest["close"] >= MIN_UNADJUSTED_CLOSE)
            & (latest["turnover_rate"] >= MIN_TURNOVER_RATE)
            & (latest["ma_10"] > latest["ma_20"])
            & (latest["ma_20"] > latest["ma_30"])
            & (latest["qfq_close"] >= latest["ma_10"] * T_CLOSE_MA10_MIN_MULTIPLE)
            & (latest["qfq_close"] <= latest["ma_10"] * T_CLOSE_MA10_MAX_MULTIPLE)
            & latest[
                ["qfq_high", "qfq_low", "qfq_close", "ma_10", "ma_20", "ma_30"]
            ].notna().all(axis=1)
        ].copy()
        if latest.empty:
            return []

        latest_by_code = {
            str(row["code"]): row
            for row in latest.to_dict("records")
        }
        signals: list[dict[str, Any]] = []
        for code, frame in view.iter_stock_history(
            columns=SIGNAL_COLUMNS,
            window=SIGNAL_LOOKBACK_BARS,
            codes=latest_by_code,
        ):
            row = latest_by_code.get(code)
            if row is None:
                continue
            signal = self._select_signal_from_frame(
                code=code,
                row=row,
                frame=frame,
                trade_date=trade_date,
            )
            if signal is not None:
                signals.append(signal)
        return signals

    def _select_signal_from_frame(
        self,
        *,
        code: str,
        row: dict[str, Any],
        frame: Any,
        trade_date: date,
    ) -> dict[str, Any] | None:
        if len(frame) < MIN_MA_STACK_DISTANCE + 1 or not frame.trade_dates:
            return None
        if _as_date(frame.trade_dates[-1]) != trade_date:
            return None

        t_position = len(frame) - 1
        if not _frame_row_has_bullish_ma_stack(frame, t_position):
            return None

        t_close = _frame_float(frame, "qfq_close", t_position)
        t_ma10 = _frame_float(frame, "ma_10", t_position)
        t_ma20 = _frame_float(frame, "ma_20", t_position)
        t_ma30 = _frame_float(frame, "ma_30", t_position)
        unadjusted_close = _to_positive_float(row.get("close"))
        turnover_rate = _to_float(row.get("turnover_rate"))
        if None in (t_close, t_ma10, t_ma20, t_ma30, unadjusted_close, turnover_rate):
            return None
        assert t_close is not None
        assert t_ma10 is not None
        assert t_ma20 is not None
        assert t_ma30 is not None
        assert unadjusted_close is not None
        assert turnover_rate is not None
        if unadjusted_close < MIN_UNADJUSTED_CLOSE or turnover_rate < MIN_TURNOVER_RATE:
            return None
        if not (
            t_ma10 * T_CLOSE_MA10_MIN_MULTIPLE
            <= t_close
            <= t_ma10 * T_CLOSE_MA10_MAX_MULTIPLE
        ):
            return None

        s_position = _current_ma_stack_start(frame, t_position)
        s_to_t_bars = t_position - s_position
        if s_to_t_bars < MIN_MA_STACK_DISTANCE:
            return None

        h_position = _latest_extreme_index(
            frame,
            column="qfq_high",
            start=s_position,
            end=t_position,
            find_max=True,
        )
        if h_position is None:
            return None
        h_to_t_bars = t_position - h_position
        if h_to_t_bars < HIGH_TO_T_MIN_BARS or h_to_t_bars > HIGH_TO_T_MAX_BARS:
            return None
        h_high = _frame_float(frame, "qfq_high", h_position)
        if h_high is None or h_high <= 0:
            return None

        l_position = _latest_extreme_index(
            frame,
            column="qfq_low",
            start=h_position,
            end=t_position + 1,
            find_max=False,
        )
        if l_position is None:
            return None
        l_low = _frame_float(frame, "qfq_low", l_position)
        l_ma10 = _frame_float(frame, "ma_10", l_position)
        l_ma20 = _frame_float(frame, "ma_20", l_position)
        if l_low is None or l_ma10 is None or l_ma20 is None or l_low <= 0:
            return None
        if l_low < l_ma20 * L_MA20_MIN_MULTIPLE:
            return None
        if l_low > l_ma10 * L_MA10_MAX_MULTIPLE:
            return None

        high_to_low_drawdown = (h_high - l_low) / h_high
        if high_to_low_drawdown < MIN_HIGH_TO_LOW_DRAWDOWN:
            return None

        bug_price = _calculate_buy_price(
            t_close=t_close,
            t_ma10=t_ma10,
        )
        stop_loss_price = _calculate_stop_loss_price(l_low=l_low, t_close=t_close)

        s_date = _as_date(frame.trade_dates[s_position])
        h_date = _as_date(frame.trade_dates[h_position])
        l_date = _as_date(frame.trade_dates[l_position])
        if s_date is None or h_date is None or l_date is None:
            return None

        code_name = None if pd.isna(row.get("name")) else str(row.get("name"))
        extras = {
            "pattern": "sharp_rise_pullback_leader",
            "t_date": trade_date.isoformat(),
            "t_qfq_close": float(t_close),
            "t_ma10": float(t_ma10),
            "t_ma20": float(t_ma20),
            "t_ma30": float(t_ma30),
            "t_unadjusted_close": float(unadjusted_close),
            "t_turnover_rate": float(turnover_rate),
            "s_date": s_date.isoformat(),
            "s_to_t_bars": int(s_to_t_bars),
            "h_date": h_date.isoformat(),
            "h_high": float(h_high),
            "h_to_t_bars": int(h_to_t_bars),
            "l_date": l_date.isoformat(),
            "l_low": float(l_low),
            "l_ma10": float(l_ma10),
            "l_ma20": float(l_ma20),
            "h_to_l_drawdown": float(high_to_low_drawdown),
            "buy_price_branch": "max_t_ma10_or_t_close_1_02",
            "raw_buy_price": float(bug_price),
            "buy_price": float(bug_price),
            "bug_price": float(bug_price),
            "entry_trigger_price": float(bug_price),
            "stop_loss_price": float(stop_loss_price),
            "watch_max_days": WATCH_MAX_DAYS,
            "profit_activation_gain": PROFIT_ACTIVATION_GAIN,
            "trailing_activation_gain": PROFIT_ACTIVATION_GAIN,
            "trailing_drawdown": TRAILING_DRAWDOWN,
            "close_weakness_max_daily_return": CLOSE_WEAKNESS_MAX_DAILY_RETURN,
            "enable_trailing_exit": ENABLE_TRAILING_EXIT,
            "enable_close_weakness_exit": ENABLE_CLOSE_WEAKNESS_EXIT,
            "max_buy_amount": MAX_BUY_AMOUNT,
            "entry_rule": (
                "observe T+1 through T+5; invalidate if low<=L low; buy at bug_price only when the "
                "observation-day range covers it; remove a full-day gap above bug_price"
            ),
            "exit_rule": (
                "close<=max(L low, T close*0.90) at close; otherwise, after confirmed holding high "
                "reaches 106% of buy price, sell on a 4% drawdown from the confirmed holding high"
            ),
        }
        signal_payload = {
            "triggered": True,
            "signal_close": float(t_close),
            "entry_trigger_price": float(bug_price),
            "sell_rules": [
                {
                    "name": "结构与T日价格约束收盘止损",
                    "rule_type": "static",
                    "timing": "收盘",
                    "trigger_price": float(stop_loss_price),
                    "sell_price": "当日前复权收盘价",
                    "description": "持仓日收盘价小于等于 max(L_low, T_close × 0.90) 时，按当日收盘价卖出。",
                },
                {
                    "name": "浮盈 6% 后最高价回撤止盈",
                    "rule_type": "dynamic",
                    "timing": "盘中",
                    "trigger_price": "已确认最高价达到买入价 × 1.06 后，最高价 × 0.96",
                    "sell_price": "回撤 4% 触发价；跳空低于触发价时按当时开盘价",
                    "description": "买入后已确认最高价达到买入价的 106% 才激活；此后回撤达到 4% 时卖出。",
                },
            ],
            "max_watch_days": WATCH_MAX_DAYS,
            "display": {
                "title": "龙头冲高回踩策略",
                "signal_date": trade_date.isoformat(),
                "entry": (
                    f"T+1 起最多观察 {WATCH_MAX_DAYS} 个交易日，价格范围覆盖 {bug_price:.3f} 时按该价买入。"
                ),
                "watch": (
                    f"观察日最低价小于等于 L_low {l_low:.3f}，或全天持续位于买入价上方且未回踩，"
                    "则收盘后移出观察池。"
                ),
                "sell": [
                    f"收盘止损：持仓日收盘价小于等于 {stop_loss_price:.3f}"
                    "（L_low 与 T_close × 0.90 取高），按收盘价卖出。",
                    "动态止盈：买入后已确认最高价累计上涨达到 6% 后，冲高回落 4% 时卖出。",
                ],
            },
            "extras": extras,
        }
        return {
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

            today_close = _bar_close(bar)
            stop_loss_price = _signal_stop_loss_price(getattr(holding, "signal", {}))
            if today_close is None or stop_loss_price is None:
                continue

            known_high = _signal_extra_float(
                getattr(holding, "signal", {}),
                "highest_price_since_buy",
            )
            buy_price = _to_positive_float(getattr(holding, "buy_price", None))
            if known_high is None:
                known_high = buy_price
            if known_high is None or buy_price is None:
                continue

            trailing_price, updated_high = _trailing_exit_for_day(
                code=code,
                trade_date=context.trade_date,
                buy_price=buy_price,
                known_high=known_high,
                daily_bar=bar,
                trailing_enabled=ENABLE_TRAILING_EXIT,
            )
            if trailing_price is not None:
                decisions.append(
                    StrategySellDecision(
                        code=code,
                        price=trailing_price,
                        quantity=int(holding.quantity),
                        reason="profit_6pct_then_high_drawdown_4pct",
                    )
                )
                continue

            if today_close <= stop_loss_price:
                decisions.append(
                    StrategySellDecision(
                        code=code,
                        price=today_close,
                        quantity=int(holding.quantity),
                        reason="close_at_or_below_stop_loss_price",
                    )
                )
                continue

            if ENABLE_CLOSE_WEAKNESS_EXIT:
                previous_close = _bar_previous_close(bar)
                if previous_close is None:
                    previous_close = _bar_close(market.previous_bars.get(code))
                if (
                    updated_high >= buy_price * PROFIT_ACTIVATION_MULTIPLE
                    and previous_close is not None
                    and today_close / previous_close - 1.0 <= CLOSE_WEAKNESS_MAX_DAILY_RETURN
                ):
                    decisions.append(
                        StrategySellDecision(
                            code=code,
                            price=today_close,
                            quantity=int(holding.quantity),
                            reason="profit_6pct_then_daily_return_at_or_below_1_5pct",
                        )
                    )
                    continue

            _set_signal_extra(
                getattr(holding, "signal", {}),
                "highest_price_since_buy",
                updated_high,
            )
            holding.max_high_since_buy = updated_high
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
            bug_price = _signal_extra_float(item.signal, "bug_price")
            l_low = _signal_extra_float(item.signal, "l_low")
            today_open = _bar_open(bar)
            today_high = _bar_high(bar)
            today_low = _bar_low(bar)
            if None in (bug_price, l_low, today_open, today_high, today_low):
                continue
            assert bug_price is not None
            assert l_low is not None
            assert today_open is not None
            assert today_high is not None
            assert today_low is not None

            if today_low <= l_low:
                continue
            if today_open > bug_price and today_low > bug_price:
                continue
            if not (today_low <= bug_price <= today_high):
                continue

            entry_known_high = _known_high_after_entry(
                code=item.code,
                trade_date=context.trade_date,
                entry_price=bug_price,
            )
            candidates.append((item, bug_price, entry_known_high))

        for item, buy_price, entry_known_high in _randomized_candidates(candidates, context=context):
            signal = _with_entry_fields(
                item.signal,
                watch_trade_days=context.trade_index - item.added_trade_index,
                entry_trigger_price=buy_price,
                highest_price_since_buy=entry_known_high,
            )
            quantity = _buy_quantity(
                cash=max(context.cash - reserved_cash, 0.0),
                price=buy_price,
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
            if _watch_breaks_l_low(code=code, item=item, market=market):
                remove.add(code)
                continue
            if _watch_gaps_above_bug_price(code=code, item=item, market=market):
                remove.add(code)
                continue
            if _watch_covers_bug_price(code=code, item=item, market=market):
                remove.add(code)
                continue
            keep.add(code)
        return StrategyWatchDecision(
            add=[signal for signal in raw_signals if str(signal.get("code")) not in held],
            keep=keep,
            remove=remove,
        )


def _current_ma_stack_start(frame: Any, t_position: int) -> int:
    position = t_position
    while position > 0 and _frame_row_has_bullish_ma_stack(frame, position - 1):
        position -= 1
    return position


def _frame_row_has_bullish_ma_stack(frame: Any, index: int) -> bool:
    ma10 = _frame_float(frame, "ma_10", index)
    ma20 = _frame_float(frame, "ma_20", index)
    ma30 = _frame_float(frame, "ma_30", index)
    return ma10 is not None and ma20 is not None and ma30 is not None and ma10 > ma20 > ma30


def _latest_extreme_index(
    frame: Any,
    *,
    column: str,
    start: int,
    end: int,
    find_max: bool,
) -> int | None:
    if start < 0 or end > len(frame) or start >= end:
        return None
    best_index: int | None = None
    best_value: float | None = None
    for index in range(start, end):
        value = _frame_float(frame, column, index)
        if value is None:
            return None
        if find_max:
            is_better = best_value is None or value >= best_value
        else:
            is_better = best_value is None or value <= best_value
        if is_better:
            best_index = index
            best_value = value
    return best_index


def _calculate_buy_price(*, t_close: float, t_ma10: float) -> float:
    return max(t_ma10, t_close * BUY_T_CLOSE_CONFIRMATION_MULTIPLE)


def _calculate_stop_loss_price(*, l_low: float, t_close: float) -> float:
    return max(l_low, t_close * T_CLOSE_STOP_MULTIPLE)


def _signal_stop_loss_price(signal: dict[str, Any]) -> float | None:
    frozen_price = _signal_extra_float(signal, "stop_loss_price")
    if frozen_price is not None:
        return frozen_price
    l_low = _signal_extra_float(signal, "l_low")
    if l_low is None:
        return None
    t_close = _to_positive_float(signal.get("signal_close"))
    if t_close is None:
        return l_low
    return _calculate_stop_loss_price(l_low=l_low, t_close=t_close)


def _watch_breaks_l_low(*, code: str, item: Any, market: MarketViews | None) -> bool:
    bar = _tradeable_watch_bar(code=code, market=market)
    today_low = _bar_low(bar)
    l_low = _signal_extra_float(item.signal, "l_low")
    return today_low is not None and l_low is not None and today_low <= l_low


def _watch_gaps_above_bug_price(*, code: str, item: Any, market: MarketViews | None) -> bool:
    bar = _tradeable_watch_bar(code=code, market=market)
    today_open = _bar_open(bar)
    today_low = _bar_low(bar)
    bug_price = _signal_extra_float(item.signal, "bug_price")
    return (
        today_open is not None
        and today_low is not None
        and bug_price is not None
        and today_open > bug_price
        and today_low > bug_price
    )


def _watch_covers_bug_price(*, code: str, item: Any, market: MarketViews | None) -> bool:
    bar = _tradeable_watch_bar(code=code, market=market)
    today_high = _bar_high(bar)
    today_low = _bar_low(bar)
    bug_price = _signal_extra_float(item.signal, "bug_price")
    return (
        today_high is not None
        and today_low is not None
        and bug_price is not None
        and today_low <= bug_price <= today_high
    )


def _tradeable_watch_bar(*, code: str, market: MarketViews | None) -> tuple[float, ...] | None:
    if market is None:
        return None
    bar = market.today_bars.get(code)
    return bar if _is_tradeable_bar(bar) else None


def _known_high_after_entry(*, code: str, trade_date: date, entry_price: float) -> float:
    minute_bars = _load_qfq_5min_bars(code, trade_date)
    if not minute_bars:
        return entry_price
    entered = False
    known_high = entry_price
    for _, high, low, _ in minute_bars:
        if not entered:
            if low <= entry_price <= high:
                entered = True
            continue
        known_high = max(known_high, high)
    return known_high


def _trailing_exit_for_day(
    *,
    code: str,
    trade_date: date,
    buy_price: float,
    known_high: float,
    daily_bar: tuple[float, ...],
    trailing_enabled: bool = True,
) -> tuple[float | None, float]:
    activation_price = buy_price * PROFIT_ACTIVATION_MULTIPLE
    minute_bars = _load_qfq_5min_bars(code, trade_date)
    if minute_bars:
        running_high = known_high
        for open_price, high, low, _ in minute_bars:
            if trailing_enabled and running_high >= activation_price:
                stop_price = running_high * TRAILING_REMAINING_MULTIPLE
                if open_price <= stop_price:
                    return (open_price, running_high)
            running_high = max(running_high, open_price)
            if trailing_enabled and running_high >= activation_price:
                stop_price = running_high * TRAILING_REMAINING_MULTIPLE
                if low <= stop_price:
                    return (stop_price, running_high)
            running_high = max(running_high, high)
        return (None, running_high)

    today_open = _bar_open(daily_bar)
    today_high = _bar_high(daily_bar)
    today_low = _bar_low(daily_bar)
    if today_open is None or today_high is None or today_low is None:
        return (None, known_high)
    if trailing_enabled and known_high >= activation_price:
        stop_price = known_high * TRAILING_REMAINING_MULTIPLE
        if today_open <= stop_price:
            return (today_open, known_high)
    running_high = max(known_high, today_open)
    if trailing_enabled and running_high >= activation_price:
        stop_price = running_high * TRAILING_REMAINING_MULTIPLE
        if today_low <= stop_price:
            return (stop_price, running_high)
    return (None, max(running_high, today_high))


@lru_cache(maxsize=4096)
def _load_qfq_5min_bars(code: str, trade_date: date) -> tuple[tuple[float, float, float, float], ...]:
    ts_code = _to_ts_code(code)
    if ts_code is None:
        return ()
    with DuckDBRepository().connect(read_only=True) as connection:
        rows = connection.execute(
            """
            select
                minutes.open * technical.adj_factor / technical.latest_adj_factor as qfq_open,
                minutes.high * technical.adj_factor / technical.latest_adj_factor as qfq_high,
                minutes.low * technical.adj_factor / technical.latest_adj_factor as qfq_low,
                minutes.close * technical.adj_factor / technical.latest_adj_factor as qfq_close
            from tushare.stk_mins_5min minutes
            join tushare.stock_daily_technical technical
              on technical.ts_code = minutes.ts_code
             and technical.trade_date = minutes.trade_date
            where minutes.ts_code = ?
              and minutes.trade_date = ?
              and minutes.open is not null
              and minutes.high is not null
              and minutes.low is not null
              and minutes.close is not null
              and technical.adj_factor is not null
              and technical.latest_adj_factor is not null
              and technical.adj_factor > 0
              and technical.latest_adj_factor > 0
            order by minutes.trade_time
            """,
            [ts_code, trade_date],
        ).fetchall()
    bars: list[tuple[float, float, float, float]] = []
    for values in rows:
        converted = tuple(_to_positive_float(value) for value in values)
        if any(value is None for value in converted):
            continue
        open_price, high, low, close = converted
        assert open_price is not None and high is not None and low is not None and close is not None
        bars.append((open_price, high, low, close))
    return tuple(bars)


def _to_ts_code(code: str) -> str | None:
    value = str(code).strip().lower()
    if "." not in value:
        return None
    exchange, symbol = value.split(".", maxsplit=1)
    if exchange not in {"sh", "sz", "bj"} or not symbol:
        return None
    return f"{symbol}.{exchange.upper()}"


def _frame_float(frame: Any, name: str, index: int) -> float | None:
    values = frame.columns.get(name)
    if values is None:
        return None
    try:
        value = values[index]
    except (IndexError, TypeError):
        return None
    return _to_float(value)


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


def _to_positive_float(value: Any) -> float | None:
    numeric = _to_float(value)
    if numeric is None or numeric <= 0:
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


def _bar_open(bar: tuple[float, ...] | None) -> float | None:
    return _bar_field(bar, 0)


def _bar_high(bar: tuple[float, ...] | None) -> float | None:
    return _bar_field(bar, 1)


def _bar_low(bar: tuple[float, ...] | None) -> float | None:
    return _bar_field(bar, 2)


def _bar_close(bar: tuple[float, ...] | None) -> float | None:
    return _bar_field(bar, 3)


def _bar_previous_close(bar: tuple[float, ...] | None) -> float | None:
    return _bar_field(bar, 7)


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


def _buy_quantity(*, cash: float, price: float) -> int:
    if cash <= 0 or price <= 0:
        return 0
    amount = min(cash / 1.0005, MAX_BUY_AMOUNT)
    return max(int(amount // price), 0)


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


def _signal_extras(signal: dict[str, Any]) -> dict[str, Any] | None:
    extras = signal.get("extras") if isinstance(signal, dict) else None
    return extras if isinstance(extras, dict) else None


def _signal_extra_float(signal: dict[str, Any], name: str) -> float | None:
    extras = _signal_extras(signal)
    if extras is None:
        return None
    return _to_positive_float(extras.get(name))


def _set_signal_extra(signal: dict[str, Any], name: str, value: float) -> None:
    extras = _signal_extras(signal)
    if extras is not None:
        extras[name] = float(value)


def _with_entry_fields(
    signal: dict[str, Any],
    *,
    watch_trade_days: int,
    entry_trigger_price: float,
    highest_price_since_buy: float,
) -> dict[str, Any]:
    copied = dict(signal)
    extras = dict(copied.get("extras") or {})
    extras["watch_trade_days"] = watch_trade_days
    extras["actual_entry_trigger_price"] = entry_trigger_price
    extras["highest_price_since_buy"] = highest_price_since_buy
    copied["extras"] = extras
    return copied


sharp_rise_pullback_leader_lifecycle = SharpRisePullbackLeaderLifecycle()
