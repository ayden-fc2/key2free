from __future__ import annotations

import math
import random
from datetime import date
from typing import Any

import pandas as pd

from app.entities.stock_data_context import StockDailyFrame
from app.services.strategy_lifecycle import (
    MarketViews,
    StrategyBuyDecision,
    StrategyContext,
    StrategySellDecision,
    StrategyWatchDecision,
)


SIGNAL_LOOKBACK_BARS = 30
CONSOLIDATION_START_OFFSET = 15
CONSOLIDATION_END_OFFSET = 1
MAX_BODY_RANGE_PCT = 0.07
MAX_PREVIOUS_ATR_PCT_14 = 0.025
VOLUME_LOOKBACK_BARS = 5
VOLUME_MULTIPLE = 1.5
MIN_RSI_5 = 60.0
BREAKOUT_CLOSE_MULTIPLE = 1.01
BREAKOUT_CLOSE_MAX_MULTIPLE = 1.05
ENTRY_TRIGGER_SIGNAL_CLOSE_MULTIPLE = 1.03
WATCH_MAX_DAYS = 7
POSITION_FRACTION = 0.25
TRAILING_PROFIT_ENABLE = 1.04
TRAILING_DRAWDOWN = 0.96
EARLY_EXIT_CHECK_HOLD_DAYS = 3
EARLY_EXIT_MIN_CLOSE_RETURN = 0.04
TRIGGERED_WATCH_CODES_KEY = "volume_breakout_macd_triggered_watch_codes"

SIGNAL_COLUMNS = (
    "name",
    "qfq_open",
    "qfq_low",
    "qfq_close",
    "vol",
    "turnover_rate",
    "atr_pct_14",
    "ma_20",
    "macd_dea_12_26_9",
    "rsi_5",
    "is_st",
)

VOLUME_BREAKOUT_MACD_REQUIRED_COLUMNS: tuple[str, ...] = ()


def volume_breakout_macd_code_filter(code: str) -> bool:
    normalized = code.lower()
    return (
        normalized.startswith("sh.6")
        or normalized.startswith("sz.0")
        or normalized.startswith("sz.3")
    ) and not normalized.startswith("sh.688")


class VolumeBreakoutMacdLifecycle:
    """Volume breakout strategy using frozen T-day range levels."""

    def select_signals(
        self,
        *,
        trade_date: date,
        view: Any,
    ) -> list[dict[str, Any]]:
        latest = view.cross_section(columns=SIGNAL_COLUMNS)
        if latest.empty:
            return []

        candidate_codes = _candidate_codes_from_cross_section(latest)
        if not candidate_codes:
            return []

        signals: list[dict[str, Any]] = []
        for code, frame in view.iter_stock_history(
            columns=SIGNAL_COLUMNS,
            window=SIGNAL_LOOKBACK_BARS,
            codes=candidate_codes,
        ):
            item = _select_signal_for_frame(code=code, frame=frame, trade_date=trade_date)
            if item is not None:
                signals.append(item)
        return signals

    def select_signals_for_dates(
        self,
        *,
        trade_dates: list[date],
        source: Any,
        max_window: int,
        index_source: Any | None = None,
        params_by_date: dict[date, Any] | None = None,
    ) -> dict[date, list[dict[str, Any]]]:
        del index_source, params_by_date
        result: dict[date, list[dict[str, Any]]] = {day: [] for day in trade_dates}
        if source.empty or not trade_dates:
            return result

        target_dates = set(trade_dates)
        ordered = source.sort_values(["code", "trade_date"])
        for code, group in ordered.groupby("code", sort=False):
            normalized_code = str(code)
            if not volume_breakout_macd_code_filter(normalized_code):
                continue
            full_frame = _stock_frame_from_group(normalized_code, group)
            for index, trade_day in enumerate(full_frame.trade_dates):
                day = _as_date(trade_day)
                if day not in target_dates:
                    continue
                if not _passes_candidate_row(code=normalized_code, frame=full_frame, index=index):
                    continue
                start = max(0, index - max_window + 1)
                frame = _slice_stock_frame(full_frame, start, index + 1)
                item = _select_signal_for_frame(
                    code=normalized_code,
                    frame=frame,
                    trade_date=day,
                )
                if item is not None:
                    result[day].append(item)
        return result

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

            today_high = _bar_high(bar)
            today_close = _bar_close(bar)
            if today_high is None or today_close is None:
                continue

            known_high = _to_positive_float(getattr(holding, "max_high_since_buy", None)) or holding.buy_price
            running_high = max(known_high, today_high)
            holding.max_high_since_buy = running_high

            holding_days = context.trade_index - getattr(holding, "buy_trade_index", context.trade_index) + 1
            if (
                holding_days == EARLY_EXIT_CHECK_HOLD_DAYS
                and today_close / holding.buy_price - 1.0 < EARLY_EXIT_MIN_CLOSE_RETURN
            ):
                decisions.append(
                    StrategySellDecision(
                        code=code,
                        price=today_close,
                        quantity=int(holding.quantity),
                        reason="day3_close_gain_below_4pct",
                    )
                )
                continue

            trailing_price = running_high * TRAILING_DRAWDOWN
            if running_high >= holding.buy_price * TRAILING_PROFIT_ENABLE and today_close <= trailing_price:
                decisions.append(
                    StrategySellDecision(
                        code=code,
                        price=today_close,
                        quantity=int(holding.quantity),
                        reason="max_profit_close_drawdown_4pct",
                    )
                )
                continue

            close_stop_price = _signal_extra_float(getattr(holding, "signal", {}), "close_stop_price")
            if close_stop_price is not None and today_close < close_stop_price:
                decisions.append(
                    StrategySellDecision(
                        code=code,
                        price=today_close,
                        quantity=int(holding.quantity),
                        reason="close_break_body_midline",
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
        candidates: list[tuple[Any, float]] = []
        triggered_watch_codes = _triggered_watch_codes(context)
        for item in context.watch_pool.values():
            if item.code in context.holdings:
                continue
            age = context.trade_index - item.added_trade_index
            if age < 1 or age > WATCH_MAX_DAYS:
                continue
            bar = market.today_bars.get(item.code)
            if not _is_tradeable_bar(bar):
                continue
            trigger_price = _signal_extra_float(item.signal, "entry_trigger_price")
            if trigger_price is None:
                continue
            today_open = _bar_open(bar)
            today_high = _bar_high(bar)
            if today_open is None or today_high is None:
                continue
            close_stop_price = _signal_extra_float(item.signal, "close_stop_price")
            if close_stop_price is not None and today_open < close_stop_price:
                continue
            if today_open >= trigger_price:
                triggered_watch_codes.add(item.code)
                candidates.append((item, today_open))
            elif today_high >= trigger_price:
                triggered_watch_codes.add(item.code)
                candidates.append((item, trigger_price))

        decisions: list[StrategyBuyDecision] = []
        reserved_cash = 0.0
        for item, buy_price in _ordered_candidates(candidates, context=context):
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
                    signal=_with_entry_fields(
                        item.signal,
                        buy_trade_date=context.trade_date,
                        buy_price=buy_price,
                    ),
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
        triggered_watch_codes = _triggered_watch_codes(context)
        keep: set[str] = set()
        remove: set[str] = set()
        for code, item in context.watch_pool.items():
            if code in held:
                remove.add(code)
                continue
            if code in triggered_watch_codes:
                remove.add(code)
                continue
            age = context.trade_index - item.added_trade_index
            if age >= WATCH_MAX_DAYS:
                remove.add(code)
                continue
            if age >= 1 and market is not None:
                bar = market.today_bars.get(code)
                today_open = _bar_open(bar)
                today_close = _bar_close(bar)
                close_stop_price = _signal_extra_float(item.signal, "close_stop_price")
                if (
                    close_stop_price is not None
                    and (
                        (today_open is not None and today_open < close_stop_price)
                        or (today_close is not None and today_close < close_stop_price)
                    )
                ):
                    remove.add(code)
                    continue
            keep.add(code)
        return StrategyWatchDecision(
            add=[signal for signal in raw_signals if str(signal.get("code")) not in held],
            keep=keep,
            remove=remove,
        )


def _candidate_codes_from_cross_section(latest: Any) -> list[str]:
    if latest.empty:
        return []
    frame = latest.copy()
    if "is_st" in frame.columns:
        frame["is_st"] = pd.to_numeric(frame["is_st"], errors="coerce")
    names = frame.get("name", pd.Series("", index=frame.index)).fillna("").astype(str)
    mask = (
        frame["code"].astype(str).apply(volume_breakout_macd_code_filter)
        & ~names.str.upper().str.contains("ST", regex=False)
    )
    if "is_st" in frame.columns:
        mask = mask & (frame["is_st"].fillna(0.0) == 0.0)
    return [str(code) for code in frame.loc[mask.fillna(False), "code"].tolist()]


def _passes_candidate_row(*, code: str, frame: Any, index: int) -> bool:
    if not volume_breakout_macd_code_filter(code):
        return False
    name = _frame_text(frame, "name", index) or ""
    if "ST" in name.upper():
        return False
    is_st = _frame_float(frame, "is_st", index)
    if is_st is not None and is_st != 0:
        return False
    today_close = _frame_float(frame, "qfq_close", index)
    today_volume = _frame_float(frame, "vol", index)
    today_turnover_rate = _frame_float(frame, "turnover_rate", index)
    today_dea = _frame_float(frame, "macd_dea_12_26_9", index)
    today_ma20 = _frame_float(frame, "ma_20", index)
    today_rsi5 = _frame_float(frame, "rsi_5", index)
    return (
        today_close is not None
        and today_volume is not None
        and today_turnover_rate is not None
        and today_dea is not None
        and today_ma20 is not None
        and today_rsi5 is not None
        and today_rsi5 >= MIN_RSI_5
    )


def _select_signal_for_frame(*, code: str, frame: Any, trade_date: date) -> dict[str, Any] | None:
    if len(frame) < SIGNAL_LOOKBACK_BARS or not frame.trade_dates or _as_date(frame.trade_dates[-1]) != trade_date:
        return None

    today_index = len(frame) - 1
    previous_index = today_index - 1
    today_close = _frame_float(frame, "qfq_close", today_index)
    today_volume = _frame_float(frame, "vol", today_index)
    today_turnover_rate = _frame_float(frame, "turnover_rate", today_index)
    today_dea = _frame_float(frame, "macd_dea_12_26_9", today_index)
    previous_dea = _frame_float(frame, "macd_dea_12_26_9", previous_index)
    today_ma20 = _frame_float(frame, "ma_20", today_index)
    previous_ma20 = _frame_float(frame, "ma_20", previous_index)
    today_rsi5 = _frame_float(frame, "rsi_5", today_index)
    if (
        today_close is None
        or today_volume is None
        or today_turnover_rate is None
        or today_dea is None
        or previous_dea is None
        or today_ma20 is None
        or previous_ma20 is None
        or today_rsi5 is None
    ):
        return None
    if today_dea - previous_dea < 0:
        return None
    if today_ma20 - previous_ma20 < 0:
        return None
    if today_rsi5 < MIN_RSI_5:
        return None

    body_start = today_index - CONSOLIDATION_START_OFFSET
    body_end = today_index - CONSOLIDATION_END_OFFSET + 1
    body_range = _body_range(frame, body_start, body_end)
    if body_range is None:
        return None
    body_high_h, body_low_l = body_range
    if body_low_l <= 0 or (body_high_h - body_low_l) / body_low_l > MAX_BODY_RANGE_PCT:
        return None
    previous_atr_pct_14 = _frame_float(frame, "atr_pct_14", previous_index)
    if previous_atr_pct_14 is None or previous_atr_pct_14 <= 0:
        return None
    if previous_atr_pct_14 > MAX_PREVIOUS_ATR_PCT_14:
        return None

    avg_volume_5 = _avg_frame_float(frame, "vol", today_index - VOLUME_LOOKBACK_BARS, today_index)
    if avg_volume_5 is None or avg_volume_5 <= 0 or today_volume < avg_volume_5 * VOLUME_MULTIPLE:
        return None
    avg_turnover_5 = _avg_frame_float(
        frame,
        "turnover_rate",
        today_index - VOLUME_LOOKBACK_BARS,
        today_index,
    )
    if (
        avg_turnover_5 is None
        or avg_turnover_5 <= 0
        or today_turnover_rate < avg_turnover_5 * VOLUME_MULTIPLE
    ):
        return None

    if today_close < body_high_h * BREAKOUT_CLOSE_MULTIPLE:
        return None
    if today_close > body_high_h * BREAKOUT_CLOSE_MAX_MULTIPLE:
        return None

    code_name = _frame_text(frame, "name", today_index)
    entry_trigger_price = today_close * ENTRY_TRIGGER_SIGNAL_CLOSE_MULTIPLE
    close_stop_price = (body_high_h + body_low_l) / 2.0
    signal = {
        "triggered": True,
        "signal_close": float(today_close),
        "entry_trigger_price": float(entry_trigger_price),
        "max_watch_days": WATCH_MAX_DAYS,
        "sell_rules": [
            {
                "name": "第3日未启动退出",
                "rule_type": "time_stop",
                "timing": "close",
                "trigger_price": f"holding_day == {EARLY_EXIT_CHECK_HOLD_DAYS} and close / buy_price - 1 < {EARLY_EXIT_MIN_CLOSE_RETURN:.2%}",
                "sell_price": "current_close",
                "description": "买入后第 3 个交易日收盘涨幅未达到 4% 时，按收盘价卖出。",
            },
            {
                "name": "实体中线收盘止损",
                "rule_type": "static",
                "timing": "close",
                "trigger_price": float(close_stop_price),
                "sell_price": "current_close",
                "description": "持仓期间收盘价跌破 T-15 至 T-1 实体震荡区间中线时按收盘价卖出。",
            },
            {
                "name": "最大浮盈回撤止盈",
                "rule_type": "dynamic",
                "timing": "close",
                "trigger_price": "close <= highest_since_buy * 0.96 after highest_since_buy >= buy_price * 1.04",
                "sell_price": "current_close",
                "description": "买入后最高价相对买入价涨幅超过 4%，随后收盘价跌破最高价的 96% 时按收盘价卖出。",
            },
        ],
        "display": {
            "title": "缩量震荡放量突破",
            "signal_date": trade_date.isoformat(),
            "entry": f"T+1 起最多观察 {WATCH_MAX_DAYS} 个交易日，盘中触及 {entry_trigger_price:.3f} 买入；若开盘已达到则按开盘价买入。",
            "watch": (
                f"实体震荡区间 H={body_high_h:.3f}, L={body_low_l:.3f}，"
                f"T 收盘价需位于 H*{BREAKOUT_CLOSE_MULTIPLE:.2f} 到 H*{BREAKOUT_CLOSE_MAX_MULTIPLE:.2f}，"
                f"且 RSI5 不低于 {MIN_RSI_5:.0f}。"
            ),
            "sell": f"第 3 个交易日收盘未涨 4% 卖出；收盘跌破 {(close_stop_price):.3f} 卖出；浮盈超过 4% 后收盘回撤 4% 止盈。",
        },
        "extras": {
            "pattern": "volume_breakout_macd",
            "body_range_start_offset": CONSOLIDATION_START_OFFSET,
            "body_range_end_offset": CONSOLIDATION_END_OFFSET,
            "body_high_h": float(body_high_h),
            "body_low_l": float(body_low_l),
            "body_range_pct": float((body_high_h - body_low_l) / body_low_l),
            "t_minus_1_atr_pct_14": float(previous_atr_pct_14),
            "max_t_minus_1_atr_pct_14": MAX_PREVIOUS_ATR_PCT_14,
            "breakout_close_multiple": float(today_close / body_high_h),
            "breakout_close_min_multiple": BREAKOUT_CLOSE_MULTIPLE,
            "breakout_close_max_multiple": BREAKOUT_CLOSE_MAX_MULTIPLE,
            "entry_trigger_price": float(entry_trigger_price),
            "entry_trigger_signal_close_multiple": ENTRY_TRIGGER_SIGNAL_CLOSE_MULTIPLE,
            "close_stop_price": float(close_stop_price),
            "volume_multiple_5": float(today_volume / avg_volume_5),
            "turnover_multiple_5": float(today_turnover_rate / avg_turnover_5),
            "dea_slope": float(today_dea - previous_dea),
            "ma20_slope": float(today_ma20 - previous_ma20),
            "rsi_5": float(today_rsi5),
            "min_rsi_5": MIN_RSI_5,
        },
    }
    return {
        "code": code,
        "code_name": code_name,
        "trade_date": trade_date.isoformat(),
        "universe": {
            "strategy": "volume_breakout_macd",
            "body_high_h": float(body_high_h),
            "body_low_l": float(body_low_l),
            "volume_multiple_5": float(today_volume / avg_volume_5),
            "turnover_multiple_5": float(today_turnover_rate / avg_turnover_5),
        },
        "signal": signal,
    }


def _stock_frame_from_group(code: str, group: Any) -> StockDailyFrame:
    ordered = group.sort_values("trade_date")
    return StockDailyFrame(
        code=code,
        trade_dates=list(ordered["trade_date"]),
        columns={
            column: ordered[column].to_numpy()
            for column in ordered.columns
            if column not in {"trade_date", "code"}
        },
    )


def _slice_stock_frame(frame: StockDailyFrame, start: int, end: int) -> StockDailyFrame:
    return StockDailyFrame(
        code=frame.code,
        trade_dates=frame.trade_dates[start:end],
        columns={
            column: values[start:end]
            for column, values in frame.columns.items()
        },
    )


def _body_range(frame: Any, start: int, end: int) -> tuple[float, float] | None:
    highs: list[float] = []
    lows: list[float] = []
    for index in range(start, end):
        open_price = _frame_float(frame, "qfq_open", index)
        close_price = _frame_float(frame, "qfq_close", index)
        if open_price is None or close_price is None:
            return None
        highs.append(max(open_price, close_price))
        lows.append(min(open_price, close_price))
    if not highs or not lows:
        return None
    return max(highs), min(lows)


def _ordered_candidates(
    candidates: list[tuple[Any, float]],
    *,
    context: StrategyContext,
) -> list[tuple[Any, float]]:
    shuffled = list(candidates)
    seed = f"volume_breakout_macd:{context.params.get('run_no', 1)}:{context.trade_date.isoformat()}"
    random.Random(seed).shuffle(shuffled)
    return shuffled


def _triggered_watch_codes(context: StrategyContext) -> set[str]:
    existing = context.trade_records.get(TRIGGERED_WATCH_CODES_KEY)
    if isinstance(existing, set):
        return existing
    if isinstance(existing, list):
        codes = {str(code) for code in existing}
    else:
        codes = set()
    context.trade_records[TRIGGERED_WATCH_CODES_KEY] = codes
    return codes


def _buy_quantity(*, cash: float, price: float, max_amount: float) -> int:
    if price <= 0 or cash <= 0 or max_amount <= 0:
        return 0
    budget = min(cash / 1.0005, max_amount)
    return int(budget // (price * 100)) * 100


def _avg_frame_float(frame: Any, name: str, start: int, end: int) -> float | None:
    values = [
        value
        for index in range(start, end)
        for value in [_frame_float(frame, name, index)]
        if value is not None
    ]
    if len(values) != max(end - start, 0):
        return None
    return sum(values) / len(values) if values else None


def _frame_float(frame: Any, name: str, index: int) -> float | None:
    values = frame.columns.get(name)
    if values is None or index < 0 or index >= len(frame):
        return None
    return _to_float(values[index])


def _frame_text(frame: Any, name: str, index: int) -> str | None:
    values = frame.columns.get(name)
    if values is None or index < 0 or index >= len(frame):
        return None
    value = values[index]
    if value is None or pd.isna(value):
        return None
    return str(value)


def _bar_field(bar: tuple[float, ...] | None, index: int) -> float | None:
    if bar is None or len(bar) <= index:
        return None
    return _to_float(bar[index])


def _bar_open(bar: tuple[float, ...] | None) -> float | None:
    return _bar_field(bar, 0)


def _bar_high(bar: tuple[float, ...] | None) -> float | None:
    return _bar_field(bar, 1)


def _bar_low(bar: tuple[float, ...] | None) -> float | None:
    return _bar_field(bar, 2)


def _bar_close(bar: tuple[float, ...] | None) -> float | None:
    return _bar_field(bar, 3)


def _is_tradeable_bar(bar: tuple[float, ...] | None) -> bool:
    open_price = _bar_open(bar)
    high_price = _bar_high(bar)
    low_price = _bar_low(bar)
    close_price = _bar_close(bar)
    volume = _bar_field(bar, 4)
    return (
        open_price is not None
        and high_price is not None
        and low_price is not None
        and close_price is not None
        and volume is not None
        and open_price > 0
        and high_price >= low_price > 0
        and volume > 0
    )


def _signal_extra_float(signal: dict[str, Any], name: str) -> float | None:
    if name in signal:
        return _to_positive_float(signal.get(name))
    extras = signal.get("extras")
    if isinstance(extras, dict):
        return _to_positive_float(extras.get(name))
    return None


def _with_entry_fields(
    signal: dict[str, Any],
    *,
    buy_trade_date: date,
    buy_price: float,
) -> dict[str, Any]:
    copied = dict(signal)
    extras = dict(copied.get("extras") or {})
    extras["buy_trade_date"] = buy_trade_date.isoformat()
    extras["buy_price"] = float(buy_price)
    copied["extras"] = extras
    return copied


def _to_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        number = float(value)
        if math.isfinite(number):
            return number
    return None


def _to_positive_float(value: Any) -> float | None:
    number = _to_float(value)
    if number is None or number <= 0:
        return None
    return number


def _as_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp):
        return None
    return timestamp.date()


volume_breakout_macd_lifecycle = VolumeBreakoutMacdLifecycle()
