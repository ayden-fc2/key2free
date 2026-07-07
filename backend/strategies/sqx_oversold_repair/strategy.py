from __future__ import annotations

import math
import random
from datetime import date, time
from typing import Any

import pandas as pd

from app.entities.stock_data_context import StockDailyFrame
from app.repositories.duckdb_repository import DuckDBRepository
from app.services.strategy_lifecycle import (
    MarketViews,
    StrategyBuyDecision,
    StrategyContext,
    StrategySellDecision,
    StrategyWatchDecision,
)


MIN_LISTED_TRADING_DAYS = 250
MIN_PRICE = 10.0
MIN_MARKET_MV_WAN = 300000.0
SIGNAL_WINDOW_BARS = 260
BEAR_STACK_SEARCH_BARS = 100
MIN_OVERSOLD_DAYS = 5
LOW_RECENT_BARS = 4
LOW_CLOSE_MULTIPLE = 1.05
SHAKE_BOX_AMPLITUDE_MAX = 1.10
SHAKE_BOX_MIN_COVERAGE = 0.80
SHAKE_BOX_MIN_EXEMPT_DAYS = 2
VOLUME_LOOKBACK_BARS = 5
VOLUME_MULTIPLE = 1.5
LOWER_SHADOW_RATIO = 0.8
STOP_LOW_MULTIPLE = 0.95
TARGET_D_MULTIPLE = 0.99
MIN_REWARD_RISK = 1.7
WATCH_MAX_DAYS = 1
POSITION_FRACTION = 0.25
WEAK_REPAIR_CHECK_DAYS_AFTER_BUY = 3
MIN_HOLDING_HIGH_GAIN = 1.08
FIRST_30M_END = time(10, 0)

SQX_OVERSOLD_REPAIR_REQUIRED_COLUMNS: tuple[str, ...] = ()

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
    "vol",
    "eps",
    "total_mv",
    "circ_mv",
    "is_st",
)

_MINUTE_BARS_CACHE: dict[tuple[str, date], list[dict[str, Any]]] = {}


def sqx_oversold_repair_code_filter(code: str) -> bool:
    """Keep common A-share boards while excluding STAR Market and BSE."""
    value = code.lower()
    if value.startswith(("sh.688", "bj.")):
        return False
    return value.startswith(("sh.6", "sz.0", "sz.3"))


class SqxOversoldRepairLifecycle:
    """Individual-stock oversold repair strategy with T-close signal selection."""

    def select_signals(
        self,
        *,
        trade_date: date,
        view: Any,
    ) -> list[dict[str, Any]]:
        latest = view.cross_section(columns=SIGNAL_COLUMNS)
        candidate_codes = _candidate_codes_from_cross_section(latest)
        if not candidate_codes:
            return []

        signals: list[dict[str, Any]] = []
        for code, frame in view.iter_stock_history(
            columns=SIGNAL_COLUMNS,
            window=SIGNAL_WINDOW_BARS,
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
            full_frame = _stock_frame_from_group(str(code), group)
            for index, trade_day in enumerate(full_frame.trade_dates):
                day = _as_date(trade_day)
                if day not in target_dates:
                    continue
                if not _passes_candidate_row(code=str(code), frame=full_frame, index=index):
                    continue
                start = max(0, index - max_window + 1)
                frame = _slice_stock_frame(full_frame, start, index + 1)
                item = _select_signal_for_frame(code=str(code), frame=frame, trade_date=day)
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

            target_price = _signal_extra_float(getattr(holding, "signal", {}), "target_price")
            if target_price is not None and today_high >= target_price:
                decisions.append(
                    StrategySellDecision(
                        code=code,
                        price=target_price,
                        quantity=int(holding.quantity),
                        reason="repair_target_hit_intraday",
                    )
                )
                continue

            stop_price = _signal_extra_float(getattr(holding, "signal", {}), "stop_price")
            if stop_price is not None and today_close < stop_price:
                decisions.append(
                    StrategySellDecision(
                        code=code,
                        price=today_close,
                        quantity=int(holding.quantity),
                        reason="close_break_oversold_low_stop",
                    )
                )
                continue

            known_high = _to_positive_float(getattr(holding, "max_high_since_buy", None)) or holding.buy_price
            holding.max_high_since_buy = max(known_high, today_high)
            buy_trade_index = int(getattr(holding, "buy_trade_index", context.trade_index))
            if context.trade_index - buy_trade_index >= WEAK_REPAIR_CHECK_DAYS_AFTER_BUY:
                if holding.max_high_since_buy < holding.buy_price * MIN_HOLDING_HIGH_GAIN:
                    decisions.append(
                        StrategySellDecision(
                            code=code,
                            price=today_close,
                            quantity=int(holding.quantity),
                            reason="t4_no_8pct_high_close_exit",
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
            if context.trade_index - item.added_trade_index != 1:
                continue
            bar = market.today_bars.get(item.code)
            if not _is_tradeable_bar(bar):
                continue
            today_open = _bar_open(bar)
            signal_close = _signal_extra_float(item.signal, "signal_close")
            oversold_low_l = _signal_extra_float(item.signal, "oversold_low_l")
            if today_open is None or signal_close is None or today_open <= signal_close:
                continue
            if oversold_low_l is None:
                continue
            buy_price = _first_30m_confirmed_buy_price(
                code=item.code,
                trade_date=context.trade_date,
                floor_price=oversold_low_l,
            )
            if buy_price is None:
                continue
            reward_risk = _signal_extra_float(item.signal, "reward_risk")
            candidates.append((item, buy_price, reward_risk or 0.0))

        for item, buy_price, _reward_risk in _ordered_candidates(candidates, context=context):
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
        keep: set[str] = set()
        remove: set[str] = set()
        for code, item in context.watch_pool.items():
            if code in held:
                remove.add(code)
                continue
            if context.trade_index - item.added_trade_index >= WATCH_MAX_DAYS:
                remove.add(code)
                continue
            keep.add(code)
        return StrategyWatchDecision(
            add=[signal for signal in raw_signals if str(signal.get("code")) not in held],
            keep=keep,
            remove=remove,
        )


def _select_signal_for_frame(*, code: str, frame: Any, trade_date: date) -> dict[str, Any] | None:
    if len(frame) < MIN_LISTED_TRADING_DAYS + 1:
        return None
    today_index = len(frame) - 1
    if _as_date(frame.trade_dates[today_index]) != trade_date:
        return None
    if not _passes_base_filter(code=code, frame=frame, index=today_index):
        return None
    if not _has_bearish_ma_stack(frame, today_index):
        return None

    b_index = _bearish_stack_start(frame, today_index)
    if b_index is None or today_index - b_index > BEAR_STACK_SEARCH_BARS:
        return None
    oversold_days = today_index - b_index
    if oversold_days < MIN_OVERSOLD_DAYS:
        return None
    a_index = b_index - oversold_days * 2
    if a_index < 0:
        return None

    l_index = _latest_min_index(frame, "qfq_low", b_index, today_index + 1)
    if l_index is None or l_index < today_index - (LOW_RECENT_BARS - 1):
        return None
    oversold_low_l = _frame_float(frame, "qfq_low", l_index)
    signal_close = _frame_float(frame, "qfq_close", today_index)
    if oversold_low_l is None or signal_close is None or signal_close > oversold_low_l * LOW_CLOSE_MULTIPLE:
        return None

    shake_box = _shake_box_context(frame, a_index, b_index)
    if shake_box is None:
        return None
    shake_high_u = shake_box["full_high_u"]
    shake_low_d = shake_box["full_low_d"]

    volume_today = _frame_float(frame, "vol", today_index)
    avg_volume_5 = _avg_frame_float(frame, "vol", today_index - VOLUME_LOOKBACK_BARS, today_index)
    if volume_today is None or avg_volume_5 is None or volume_today < avg_volume_5 * VOLUME_MULTIPLE:
        return None

    candle = _candle_parts(frame, today_index)
    if candle is None:
        return None
    if candle["lower_shadow"] < (candle["body"] + candle["upper_shadow"]) * LOWER_SHADOW_RATIO:
        return None

    stop_price = oversold_low_l * STOP_LOW_MULTIPLE
    target_price = shake_low_d * TARGET_D_MULTIPLE
    risk = signal_close - stop_price
    reward = target_price - signal_close
    if risk <= 0 or reward <= 0 or risk * MIN_REWARD_RISK > reward:
        return None

    code_name = _frame_text(frame, "name", today_index)
    b_date = _as_date(frame.trade_dates[b_index])
    a_date = _as_date(frame.trade_dates[a_index])
    l_date = _as_date(frame.trade_dates[l_index])
    extras = {
        "pattern": "sqx_oversold_repair",
        "signal_close": float(signal_close),
        "stop_price": float(stop_price),
        "target_price": float(target_price),
        "oversold_low_l": float(oversold_low_l),
        "shake_low_d": float(shake_low_d),
        "shake_high_u": float(shake_high_u),
        "shake_box_low": float(shake_box["box_low"]),
        "shake_box_high": float(shake_box["box_high"]),
        "shake_box_covered_days": int(shake_box["covered_days"]),
        "shake_box_total_days": int(shake_box["total_days"]),
        "shake_box_coverage": float(shake_box["coverage"]),
        "shake_box_exempt_days": int(shake_box["exempt_days"]),
        "reward_risk": float(reward / risk),
        "risk_pct": float(risk / signal_close),
        "reward_pct": float(reward / signal_close),
        "a_date": a_date.isoformat() if a_date is not None else None,
        "b_date": b_date.isoformat() if b_date is not None else None,
        "l_date": l_date.isoformat() if l_date is not None else None,
        "oversold_days": int(oversold_days),
        "shake_days": int(b_index - a_index),
        "shake_amplitude": float(shake_high_u / shake_low_d - 1),
        "shake_box_amplitude": float(shake_box["box_high"] / shake_box["box_low"] - 1),
        "volume_multiple_5": float(volume_today / avg_volume_5),
        "lower_shadow_ratio": float(
            candle["lower_shadow"] / max(candle["body"] + candle["upper_shadow"], 1e-9)
        ),
        "eps": float(_frame_float(frame, "eps", today_index) or 0.0),
        "market_mv": float(_market_mv(frame, today_index) or 0.0),
        "total_mv": float(_frame_float(frame, "total_mv", today_index) or 0.0),
        "circ_mv": float(_frame_float(frame, "circ_mv", today_index) or 0.0),
        "listed_trading_days": int(len(frame)),
    }
    signal_payload = {
        "triggered": True,
        "signal_close": float(signal_close),
        "stop_losses": (float(stop_price),),
        "take_profits": (float(target_price),),
        "max_watch_days": WATCH_MAX_DAYS,
        "entry_rule": "T+1 open above T close and first 30 minutes do not break signal-day low L",
        "sell_rules": [
            {
                "name": "close_break_oversold_low_stop",
                "timing": "close",
                "trigger_price": float(stop_price),
                "sell_price": "same-day close",
            },
            {
                "name": "repair_target_hit_intraday",
                "timing": "intraday",
                "trigger_price": float(target_price),
                "sell_price": float(target_price),
            },
            {
                "name": "t4_no_8pct_high_close_exit",
                "timing": "T+4 close",
                "trigger_price": float(signal_close * MIN_HOLDING_HIGH_GAIN),
                "sell_price": "same-day close",
            },
        ],
        "display": {
            "title": "sqx 个股超跌修复",
            "signal_date": trade_date.isoformat(),
            "entry": "T+1 开盘价高于 T 收盘价，且开盘后 30 分钟内不破 T 日最低价 L，按 30 分钟确认后的市价买入。",
            "watch": "只观察 T+1 一个交易日；未满足盘中确认则移出观察池。",
            "sell": [
                "持仓收盘价跌破 L*0.95，按收盘价止损。",
                "盘中触及 D*0.99，按该价格止盈。",
                "T+4 收盘时若持仓最高价较买入价涨幅不足 8%，按收盘价退出。",
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


def _candidate_codes_from_cross_section(latest: Any) -> list[str]:
    if latest.empty:
        return []
    frame = latest.copy()
    for column in (
        "close",
        "qfq_open",
        "qfq_high",
        "qfq_low",
        "qfq_close",
        "ma_10",
        "ma_20",
        "ma_30",
        "vol",
        "eps",
        "total_mv",
        "circ_mv",
        "is_st",
    ):
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

    names = frame.get("name", pd.Series("", index=frame.index)).fillna("").astype(str)
    total_mv = frame["total_mv"] if "total_mv" in frame.columns else pd.Series(float("nan"), index=frame.index)
    circ_mv = frame["circ_mv"] if "circ_mv" in frame.columns else pd.Series(float("nan"), index=frame.index)
    market_mv = total_mv.where(total_mv.notna(), circ_mv)
    mask = (
        frame["code"].astype(str).apply(sqx_oversold_repair_code_filter)
        & ~names.str.upper().str.contains("ST", regex=False)
        & (frame["is_st"].fillna(0.0) == 0.0)
        & (frame["eps"] > 0)
        & (frame["close"] > MIN_PRICE)
        & (market_mv > MIN_MARKET_MV_WAN)
        & (frame["ma_10"] < frame["ma_20"])
        & (frame["ma_20"] < frame["ma_30"])
        & frame["qfq_open"].notna()
        & frame["qfq_high"].notna()
        & frame["qfq_low"].notna()
        & frame["qfq_close"].notna()
        & frame["vol"].notna()
    )
    return frame.loc[mask.fillna(False), "code"].astype(str).tolist()


def _passes_candidate_row(*, code: str, frame: Any, index: int) -> bool:
    return _passes_base_filter(code=code, frame=frame, index=index) and _has_bearish_ma_stack(frame, index)


def _stock_frame_from_group(code: str, group: Any) -> StockDailyFrame:
    ordered = group.sort_values("trade_date")
    trade_dates = [_as_date(value) or value for value in ordered["trade_date"].tolist()]
    columns = {
        column: ordered[column].to_numpy()
        for column in ordered.columns
        if column not in {"trade_date", "code"}
    }
    return StockDailyFrame(code=code, trade_dates=trade_dates, columns=columns)


def _slice_stock_frame(frame: StockDailyFrame, start: int, end: int) -> StockDailyFrame:
    return StockDailyFrame(
        code=frame.code,
        trade_dates=frame.trade_dates[start:end],
        columns={
            column: values[start:end]
            for column, values in frame.columns.items()
        },
    )


def _passes_base_filter(*, code: str, frame: Any, index: int) -> bool:
    if not sqx_oversold_repair_code_filter(code):
        return False
    name = (_frame_text(frame, "name", index) or "").upper()
    close = _frame_float(frame, "close", index)
    eps = _frame_float(frame, "eps", index)
    market_mv = _market_mv(frame, index)
    is_st = _frame_float(frame, "is_st", index)
    return (
        "ST" not in name
        and (is_st is None or is_st == 0.0)
        and eps is not None
        and eps > 0
        and close is not None
        and close > MIN_PRICE
        and market_mv is not None
        and market_mv > MIN_MARKET_MV_WAN
    )


def _market_mv(frame: Any, index: int) -> float | None:
    total_mv = _frame_float(frame, "total_mv", index)
    if total_mv is not None:
        return total_mv
    return _frame_float(frame, "circ_mv", index)


def _has_bearish_ma_stack(frame: Any, index: int) -> bool:
    ma10 = _frame_float(frame, "ma_10", index)
    ma20 = _frame_float(frame, "ma_20", index)
    ma30 = _frame_float(frame, "ma_30", index)
    return ma10 is not None and ma20 is not None and ma30 is not None and ma10 < ma20 < ma30


def _bearish_stack_start(frame: Any, today_index: int) -> int | None:
    if not _has_bearish_ma_stack(frame, today_index):
        return None
    start = today_index
    lower_bound = max(0, today_index - BEAR_STACK_SEARCH_BARS)
    while start > lower_bound and _has_bearish_ma_stack(frame, start - 1):
        start -= 1
    return start


def _candle_parts(frame: Any, index: int) -> dict[str, float] | None:
    open_price = _frame_float(frame, "qfq_open", index)
    high = _frame_float(frame, "qfq_high", index)
    low = _frame_float(frame, "qfq_low", index)
    close = _frame_float(frame, "qfq_close", index)
    if open_price is None or high is None or low is None or close is None:
        return None
    if high < max(open_price, close) or low > min(open_price, close):
        return None
    return {
        "body": abs(close - open_price),
        "upper_shadow": high - max(open_price, close),
        "lower_shadow": min(open_price, close) - low,
    }


def _shake_box_context(frame: Any, start: int, end: int) -> dict[str, float | int] | None:
    candles: list[tuple[float, float]] = []
    for index in range(max(start, 0), min(end, len(frame))):
        high = _frame_float(frame, "qfq_high", index)
        low = _frame_float(frame, "qfq_low", index)
        if high is None or low is None or high < low:
            return None
        candles.append((low, high))
    if not candles:
        return None

    total_days = len(candles)
    exempt_days = max(
        SHAKE_BOX_MIN_EXEMPT_DAYS,
        int(math.floor(total_days * (1.0 - SHAKE_BOX_MIN_COVERAGE))),
    )
    required_days = max(1, total_days - exempt_days)
    candidate_lows = sorted({low for low, _high in candles})
    best: tuple[int, float, float] | None = None
    for box_low in candidate_lows:
        box_high = box_low * SHAKE_BOX_AMPLITUDE_MAX
        covered_days = sum(1 for low, high in candles if low >= box_low and high <= box_high)
        if best is None or covered_days > best[0] or (
            covered_days == best[0] and box_high - box_low < best[2] - best[1]
        ):
            best = (covered_days, box_low, box_high)
    if best is None:
        return None
    covered_days, box_low, box_high = best
    if covered_days < required_days:
        return None
    return {
        "box_low": box_low,
        "box_high": box_high,
        "covered_days": covered_days,
        "total_days": total_days,
        "coverage": covered_days / total_days,
        "exempt_days": total_days - covered_days,
        "required_days": required_days,
        "full_high_u": max(high for _low, high in candles),
        "full_low_d": min(low for low, _high in candles),
    }


def _first_30m_confirmed_buy_price(*, code: str, trade_date: date, floor_price: float) -> float | None:
    bars = _load_qfq_5min_bars(code=code, trade_date=trade_date)
    first_30m = [bar for bar in bars if bar["trade_time"] <= FIRST_30M_END]
    if not first_30m:
        return None
    if any(bar["low"] < floor_price for bar in first_30m):
        return None
    return _to_positive_float(first_30m[-1]["close"])


def _load_qfq_5min_bars(*, code: str, trade_date: date) -> list[dict[str, Any]]:
    key = (code, trade_date)
    cached = _MINUTE_BARS_CACHE.get(key)
    if cached is not None:
        return cached
    ts_code = _to_ts_code(code)
    if ts_code is None:
        _MINUTE_BARS_CACHE[key] = []
        return []
    with DuckDBRepository().connect(read_only=True) as connection:
        rows = connection.execute(
            """
            select
                minutes.trade_time,
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
    bars: list[dict[str, Any]] = []
    for trade_time_value, open_price, high, low, close in rows:
        parsed_time = _as_time(trade_time_value)
        open_value = _to_positive_float(open_price)
        high_value = _to_positive_float(high)
        low_value = _to_positive_float(low)
        close_value = _to_positive_float(close)
        if (
            parsed_time is None
            or open_value is None
            or high_value is None
            or low_value is None
            or close_value is None
        ):
            continue
        bars.append(
            {
                "trade_time": parsed_time,
                "open": open_value,
                "high": high_value,
                "low": low_value,
                "close": close_value,
            }
        )
    _MINUTE_BARS_CACHE[key] = bars
    return bars


def _ordered_candidates(
    candidates: list[tuple[Any, float, float]],
    *,
    context: StrategyContext,
) -> list[tuple[Any, float, float]]:
    items = sorted(candidates, key=lambda item: (-item[2], item[0].added_trade_index, item[0].code))
    seed = f"{context.params.get('run_no', 1)}:{context.trade_date.isoformat()}"
    rng = random.Random(seed)
    grouped: dict[float, list[tuple[Any, float, float]]] = {}
    for item in items:
        grouped.setdefault(round(item[2], 6), []).append(item)
    result: list[tuple[Any, float, float]] = []
    for key in sorted(grouped, reverse=True):
        group = grouped[key]
        rng.shuffle(group)
        result.extend(group)
    return result


def _buy_quantity(*, cash: float, price: float, max_amount: float) -> int:
    if cash <= 0 or price <= 0:
        return 0
    amount = min(cash, max_amount)
    lots = int(amount // (price * 100 * 1.0005))
    return lots * 100 if lots > 0 else 0


def _latest_min_index(frame: Any, name: str, start: int, end: int) -> int | None:
    best_index: int | None = None
    best_value: float | None = None
    for index in range(max(start, 0), min(end, len(frame))):
        value = _frame_float(frame, name, index)
        if value is None:
            continue
        if best_value is None or value <= best_value:
            best_value = value
            best_index = index
    return best_index


def _max_frame_float(frame: Any, name: str, start: int, end: int) -> float | None:
    values = [_frame_float(frame, name, index) for index in range(max(start, 0), min(end, len(frame)))]
    if not values or any(value is None for value in values):
        return None
    return max(value for value in values if value is not None)


def _min_frame_float(frame: Any, name: str, start: int, end: int) -> float | None:
    values = [_frame_float(frame, name, index) for index in range(max(start, 0), min(end, len(frame)))]
    if not values or any(value is None for value in values):
        return None
    return min(value for value in values if value is not None)


def _avg_frame_float(frame: Any, name: str, start: int, end: int) -> float | None:
    values = [_frame_float(frame, name, index) for index in range(max(start, 0), min(end, len(frame)))]
    if not values or any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None) / len(values)


def _frame_float(frame: Any, name: str, index: int) -> float | None:
    values = frame.columns.get(name)
    if values is None:
        return None
    try:
        value = values[index]
    except (IndexError, TypeError):
        return None
    return _to_float(value)


def _frame_text(frame: Any, name: str, index: int) -> str | None:
    values = frame.columns.get(name)
    if values is None:
        return None
    try:
        value = values[index]
    except (IndexError, TypeError):
        return None
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return str(value)


def _bar_field(bar: tuple[float, ...] | None, index: int) -> float | None:
    if bar is None or len(bar) <= index:
        return None
    return _to_positive_float(bar[index])


def _bar_open(bar: tuple[float, ...] | None) -> float | None:
    return _bar_field(bar, 0)


def _bar_high(bar: tuple[float, ...] | None) -> float | None:
    return _bar_field(bar, 1)


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


def _signal_extra_float(signal: dict[str, Any], name: str) -> float | None:
    if name in signal:
        return _to_positive_float(signal.get(name))
    extras = signal.get("extras") if isinstance(signal, dict) else None
    if not isinstance(extras, dict):
        return None
    return _to_positive_float(extras.get(name))


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


def _to_ts_code(code: str) -> str | None:
    value = str(code).strip().lower()
    if "." not in value:
        return None
    exchange, symbol = value.split(".", maxsplit=1)
    if exchange not in {"sh", "sz"} or not symbol:
        return None
    return f"{symbol}.{exchange.upper()}"


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


def _as_time(value: Any) -> time | None:
    if isinstance(value, time):
        return value
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return None
        return value.time()
    text = str(value).strip()
    if not text:
        return None
    try:
        return pd.Timestamp(text).time()
    except (TypeError, ValueError):
        pass
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return pd.to_datetime(text, format=fmt).time()
        except (TypeError, ValueError):
            continue
    return None


sqx_oversold_repair_lifecycle = SqxOversoldRepairLifecycle()
