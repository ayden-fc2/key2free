from __future__ import annotations

import threading
import time
import math
from bisect import bisect_left
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from app.dtos.signal_dto import (
    DailySignalItemDTO,
    DailySignalResultDTO,
    DailySignalTaskDTO,
    DailySignalTaskStartDTO,
    SignalReplayPoolItemDTO,
    SignalReplayResultDTO,
    StockDataContextDTO,
    StockDataContextResultDTO,
)
from app.entities.stock_data_context import StockDailyFrame
from app.repositories.backtest_repository import BacktestRepository
from app.repositories.signal_repository import SignalRepository
from app.services.strategy_data_view import SignalDataView
from app.services.signal_window import SIGNAL_WINDOW_BARS, TRADE_HISTORY_WINDOW_BARS
from app.services.strategy_registry import get_strategy
from app.services.strategy_lifecycle import MarketViews, StrategyContext
from app.services.trading_periods import build_trading_clocks


Bar = tuple[float, ...]


@dataclass
class SignalReplayWatchItem:
    code: str
    code_name: str | None
    added_date: date
    added_trade_index: int
    signal_close: float | None
    max_watch_days: int | None
    signal: dict[str, Any]


@dataclass
class SignalReplayHoldingItem:
    code: str
    code_name: str | None
    buy_date: date
    buy_trade_index: int
    buy_price: float
    quantity: int
    buy_fee: float = 0.0
    level: int = 0
    stop_losses: list[float] = field(default_factory=list)
    take_profits: list[float] = field(default_factory=list)
    max_high_since_buy: float = 0.0
    signal: dict[str, Any] = field(default_factory=dict)
    realized_pnl: float = 0.0


class SignalServiceError(ValueError):
    pass


class SignalService:
    DAILY_SIGNAL_PROGRESS_INTERVAL = 20
    SIGNAL_BATCH_DAYS_WITH_HISTORY = 10
    SIGNAL_BATCH_DAYS_WITH_NARROW_HISTORY = 40
    SIGNAL_BATCH_DAYS_NO_HISTORY = 120
    SIGNAL_BATCH_WORKERS = 6

    def __init__(self) -> None:
        self.repository = SignalRepository()

    def request_daily_signal_task(
        self,
        *,
        trade_date: date,
        strategy_name: str,
        lookback_trade_days: int = 1,
    ) -> DailySignalTaskStartDTO:
        if get_strategy(strategy_name) is None:
            raise SignalServiceError(f"unknown strategy: {strategy_name}")
        lookback_trade_days = self._normalize_lookback_trade_days(lookback_trade_days)

        latest_task = self.repository.get_latest_daily_signal_task(
            trade_date=trade_date,
            strategy_name=strategy_name,
        )
        if (
            latest_task is not None
            and latest_task.lookback_trade_days == lookback_trade_days
            and latest_task.status == "success"
        ):
            return DailySignalTaskStartDTO(
                task=latest_task,
                message="daily signal task already completed",
            )
        if (
            latest_task is not None
            and latest_task.lookback_trade_days == lookback_trade_days
            and latest_task.status == "running"
        ):
            return DailySignalTaskStartDTO(
                task=latest_task,
                message="daily signal task already running",
            )

        task = self.repository.create_daily_signal_task(
            trade_date=trade_date,
            strategy_name=strategy_name,
            lookback_trade_days=lookback_trade_days,
            initial_log=(
                f"创建当日信号任务: strategy={strategy_name}, trade_date={trade_date.isoformat()}, "
                f"lookback_trade_days={lookback_trade_days}, mode=lifecycle"
            ),
        )
        thread = threading.Thread(
            target=self._run_daily_signal_task,
            kwargs={
                "task_id": task.id,
                "trade_date": trade_date,
                "strategy_name": strategy_name,
                "lookback_trade_days": lookback_trade_days,
            },
            daemon=True,
        )
        thread.start()
        return DailySignalTaskStartDTO(task=task, message="daily signal task created")

    def get_daily_signal_task(
        self,
        *,
        task_id: int | None = None,
        trade_date: date | None = None,
        strategy_name: str | None = None,
    ) -> DailySignalTaskDTO | None:
        if task_id is not None:
            return self.repository.get_daily_signal_task(task_id)
        return self.repository.get_latest_daily_signal_task(
            trade_date=trade_date,
            strategy_name=strategy_name,
        )

    def get_daily_signal_task_result(self, task_id: int) -> DailySignalResultDTO | None:
        return self.repository.get_daily_signal_result(task_id)

    def get_daily_signals(
        self,
        *,
        trade_date: date,
        strategy_name: str,
        lookback_trade_days: int = 1,
    ) -> DailySignalResultDTO:
        lookback_trade_days = self._normalize_lookback_trade_days(lookback_trade_days)
        trade_dates = self._resolve_signal_trade_dates(
            end_date=trade_date,
            lookback_trade_days=lookback_trade_days,
        )
        result_by_date = self.get_signals_for_dates_by_stock(
            trade_dates=trade_dates,
            strategy_name=strategy_name,
        )
        return self._merge_daily_signal_results(
            results=result_by_date,
            requested_dates=trade_dates,
            end_date=trade_date,
            strategy_name=strategy_name,
            lookback_trade_days=lookback_trade_days,
        )

    def get_signal_replay(
        self,
        *,
        trade_date: date,
        strategy_name: str,
        replay_trade_days: int = 10,
    ) -> SignalReplayResultDTO:
        replay_trade_days = self._normalize_lookback_trade_days(replay_trade_days)
        trade_dates = self._resolve_signal_trade_dates(
            end_date=trade_date,
            lookback_trade_days=replay_trade_days,
        )
        if not trade_dates:
            raise SignalServiceError("no trade dates for replay")
        strategy = get_strategy(strategy_name)
        if strategy is None:
            raise SignalServiceError(f"unknown strategy: {strategy_name}")
        lifecycle = strategy.lifecycle
        if lifecycle is None:
            raise SignalServiceError(f"strategy has no lifecycle: {strategy_name}")

        daily_results = self.get_signals_for_dates_by_stock(
            trade_dates=trade_dates,
            strategy_name=strategy_name,
        )
        signals_by_date: dict[date, list[dict[str, Any]]] = {}
        signal_count = 0
        signal_codes: set[str] = set()
        for day in trade_dates:
            result = daily_results.get(day)
            signals = [] if result is None else [
                {
                    "code": item.code,
                    "code_name": item.code_name,
                    "trade_date": date.fromisoformat(item.trade_date),
                    "universe": item.universe,
                    "signal": item.signal or {"triggered": True},
                }
                for item in result.signals
            ]
            signals_by_date[day] = signals
            signal_count += len(signals)
            signal_codes.update(str(item["code"]) for item in signals)

        if not signal_codes:
            return SignalReplayResultDTO(
                trade_date=trade_date.isoformat(),
                strategy_name=strategy.name,
                start_trade_date=trade_dates[0].isoformat(),
                end_trade_date=trade_dates[-1].isoformat(),
                replay_trade_days=len(trade_dates),
                signal_count=0,
                watch_count=0,
                holding_count=0,
                watch_pool=[],
                holdings=[],
            )

        backtest_repository = BacktestRepository()
        codes = sorted(signal_codes)
        prices = backtest_repository.load_price_data(
            codes=codes,
            start_date=trade_dates[0],
            end_date=trade_dates[-1],
        )
        history_frames = self.repository.load_stock_frames(
            codes=codes,
            start_date=trade_dates[0],
            end_date=trade_dates[-1],
            window=TRADE_HISTORY_WINDOW_BARS,
            extra_columns=strategy.required_columns,
        )
        index_history_wide = backtest_repository.load_index_history_wide(
            start_date=trade_dates[0],
            end_date=trade_dates[-1],
            window=SIGNAL_WINDOW_BARS,
        )
        trading_clocks = self._build_trading_clocks_for_dates(
            trading_dates=trade_dates,
            strategy=strategy,
        )

        cash = 1_000_000_000_000.0
        signal_total_asset = cash
        holdings: dict[str, SignalReplayHoldingItem] = {}
        watch_pool: dict[str, SignalReplayWatchItem] = {}
        trade_records: dict[str, Any] = {"buys": [], "sells": []}

        for trade_index, day in enumerate(trade_dates):
            market = self._build_replay_market_views(
                prices=prices,
                trade_date=day,
                previous_trade_date=trade_dates[trade_index - 1] if trade_index > 0 else None,
                history_frames=history_frames,
                index_history_wide=index_history_wide,
            )
            params = self._strategy_params_for_date(
                strategy=strategy,
                trade_date=day,
                trading_clocks=trading_clocks,
            )
            params["run_no"] = 1

            context = StrategyContext(
                trade_date=day,
                trade_index=trade_index,
                cash=cash,
                total_asset=signal_total_asset,
                holdings=holdings,
                watch_pool=watch_pool,
                trade_records=trade_records,
                params=params,
            )
            for decision in lifecycle.decide_sells(context=context, market=market):
                holding = holdings.get(decision.code)
                if holding is None:
                    continue
                if decision.price <= 0 or not math.isfinite(decision.price):
                    continue
                trade_records["sells"].append(
                    {
                        "trade_date": day.isoformat(),
                        "code": decision.code,
                        "price": decision.price,
                        "quantity": int(holding.quantity),
                        "reason": decision.reason,
                    }
                )
                holdings.pop(decision.code, None)

            context = StrategyContext(
                trade_date=day,
                trade_index=trade_index,
                cash=cash,
                total_asset=signal_total_asset,
                holdings=holdings,
                watch_pool=watch_pool,
                trade_records=trade_records,
                params=params,
            )
            for decision in lifecycle.decide_buys(context=context, market=market):
                if decision.code in holdings:
                    continue
                if decision.price <= 0 or not math.isfinite(decision.price):
                    continue
                quantity = 100
                signal = self._with_replay_buy_fields(
                    signal=decision.signal,
                    buy_price=decision.price,
                )
                holdings[decision.code] = SignalReplayHoldingItem(
                    code=decision.code,
                    code_name=decision.code_name,
                    buy_date=day,
                    buy_trade_index=trade_index,
                    buy_price=decision.price,
                    quantity=quantity,
                    max_high_since_buy=self._initial_max_high_since_buy(
                        bar=market.today_bars.get(decision.code),
                        buy_price=decision.price,
                    ),
                    signal=signal,
                )
                trade_records["buys"].append(
                    {
                        "trade_date": day.isoformat(),
                        "code": decision.code,
                        "price": decision.price,
                        "quantity": quantity,
                    }
                )
                watch_pool.pop(decision.code, None)

            context = StrategyContext(
                trade_date=day,
                trade_index=trade_index,
                cash=cash,
                total_asset=signal_total_asset,
                holdings=holdings,
                watch_pool=watch_pool,
                trade_records=trade_records,
                params=params,
            )
            watch_decision = lifecycle.update_watch_pool(
                context=context,
                raw_signals=signals_by_date.get(day, []),
                market=market,
            )
            for code in watch_decision.remove:
                watch_pool.pop(code, None)
            if watch_decision.keep:
                for code in list(watch_pool):
                    if code not in watch_decision.keep:
                        watch_pool.pop(code, None)
            for signal_item in watch_decision.add:
                code = str(signal_item["code"])
                signal = signal_item.get("signal") or {}
                watch_pool[code] = SignalReplayWatchItem(
                    code=code,
                    code_name=signal_item.get("code_name"),
                    added_date=day,
                    added_trade_index=trade_index,
                    signal_close=self._to_float(signal.get("signal_close")),
                    max_watch_days=signal.get("max_watch_days"),
                    signal=signal,
                )

        watch_items = [
            SignalReplayPoolItemDTO(
                code=item.code,
                code_name=item.code_name,
                pool_type="watch",
                signal_date=self._signal_date_from_signal(item.signal) or item.added_date.isoformat(),
                added_date=item.added_date.isoformat(),
                buy_date=None,
                buy_price=None,
                quantity=None,
                signal=item.signal,
            )
            for item in watch_pool.values()
        ]
        holding_items = [
            SignalReplayPoolItemDTO(
                code=item.code,
                code_name=item.code_name,
                pool_type="holding",
                signal_date=self._signal_date_from_signal(item.signal),
                added_date=None,
                buy_date=item.buy_date.isoformat(),
                buy_price=item.buy_price,
                quantity=item.quantity,
                signal=item.signal,
            )
            for item in holdings.values()
        ]
        watch_items.sort(key=lambda item: (item.signal_date or "", item.code), reverse=True)
        holding_items.sort(key=lambda item: (item.buy_date or "", item.code), reverse=True)
        return SignalReplayResultDTO(
            trade_date=trade_date.isoformat(),
            strategy_name=strategy.name,
            start_trade_date=trade_dates[0].isoformat(),
            end_trade_date=trade_dates[-1].isoformat(),
            replay_trade_days=len(trade_dates),
            signal_count=signal_count,
            watch_count=len(watch_items),
            holding_count=len(holding_items),
            watch_pool=watch_items,
            holdings=holding_items,
        )

    def get_signals_for_dates_by_stock(
        self,
        *,
        trade_dates: list[date],
        strategy_name: str,
        progress_callback: Any | None = None,
        progress_interval: int = 500,
    ) -> dict[date, DailySignalResultDTO]:
        """Evaluate signals from per-T visible wide-table windows."""
        requested_dates = sorted(set(trade_dates))
        if not requested_dates:
            return {}

        strategy = get_strategy(strategy_name)
        if strategy is None:
            raise SignalServiceError(f"unknown strategy: {strategy_name}")

        start_date = requested_dates[0]
        end_date = requested_dates[-1]
        universe_counts = self.repository.get_universe_counts_by_date(
            start_date=start_date,
            end_date=end_date,
        )
        normalized_dates = requested_dates
        trading_clocks: dict[date, Any] = {}
        if strategy.trading_clock_period is not None:
            open_dates = self.repository.get_open_trade_dates(
                start_date=start_date - timedelta(days=10),
                end_date=end_date + timedelta(days=10),
            )
            trading_clocks = build_trading_clocks(
                open_dates,
                period=strategy.trading_clock_period,
            )
            normalized_dates = [
                day
                for day in requested_dates
                if (clock := trading_clocks.get(day)) is not None and strategy.is_signal_day(clock)
            ]

        if progress_callback is not None:
            progress_callback(0, len(normalized_dates))

        if not normalized_dates:
            return {
                day: DailySignalResultDTO(
                    trade_date=day.isoformat(),
                    strategy_name=strategy.name,
                    universe_count=universe_counts.get(day, 0),
                    signal_count=0,
                    signals=[],
                )
                for day in requested_dates
            }

        window = min(strategy.signal_history_window, SIGNAL_WINDOW_BARS)
        batch_size = self._signal_batch_size(
            window=window,
            required_columns=strategy.signal_required_columns,
        )

        signal_items_by_date: dict[date, list[DailySignalItemDTO]] = {}
        processed_days = 0
        batches = self._date_batches(normalized_dates, batch_size)
        worker_count = min(self.SIGNAL_BATCH_WORKERS, len(batches))
        if worker_count <= 1:
            for batch_dates in batches:
                batch_items = self._process_signal_batch(
                    batch_dates=batch_dates,
                    strategy_name=strategy_name,
                    window=window,
                    trading_clocks=trading_clocks,
                )
                signal_items_by_date.update(batch_items)
                processed_days = self._report_batch_progress(
                    progress_callback=progress_callback,
                    processed_days=processed_days,
                    batch_dates=batch_dates,
                    total_days=len(normalized_dates),
                    progress_interval=progress_interval,
                )
        else:
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                future_by_index = {
                    executor.submit(
                        self._process_signal_batch,
                        batch_dates=batch_dates,
                        strategy_name=strategy_name,
                        window=window,
                        trading_clocks=trading_clocks,
                    ): index
                    for index, batch_dates in enumerate(batches)
                }
                completed_batches: dict[int, dict[date, list[DailySignalItemDTO]]] = {}
                next_report_index = 0
                for future in as_completed(future_by_index):
                    index = future_by_index[future]
                    completed_batches[index] = future.result()
                    while next_report_index in completed_batches:
                        batch_items = completed_batches.pop(next_report_index)
                        signal_items_by_date.update(batch_items)
                        processed_days = self._report_batch_progress(
                            progress_callback=progress_callback,
                            processed_days=processed_days,
                            batch_dates=batches[next_report_index],
                            total_days=len(normalized_dates),
                            progress_interval=progress_interval,
                        )
                        next_report_index += 1
        return {
            day: DailySignalResultDTO(
                trade_date=day.isoformat(),
                strategy_name=strategy.name,
                universe_count=universe_counts.get(day, 0),
                signal_count=len(signal_items_by_date.get(day, [])),
                signals=signal_items_by_date.get(day, []),
            )
            for day in requested_dates
        }

    def _process_signal_batch(
        self,
        *,
        batch_dates: list[date],
        strategy_name: str,
        window: int,
        trading_clocks: dict[date, Any],
    ) -> dict[date, list[DailySignalItemDTO]]:
        """Load and evaluate one signal date batch.

        This worker only performs read-only data loading and in-memory signal
        calculation. Backtest/task table writes remain in the caller thread.
        """
        strategy = get_strategy(strategy_name)
        if strategy is None:
            raise SignalServiceError(f"unknown strategy: {strategy_name}")
        repository = SignalRepository()
        batch_rows = repository.load_signal_selection_rows(
            start_date=batch_dates[0],
            end_date=batch_dates[-1],
            window=window,
            code_filter=strategy.code_filter,
            columns=strategy.signal_required_columns,
        )
        batch_index_rows = repository.load_signal_index_rows(
            ts_codes=strategy.signal_index_codes,
            start_date=batch_dates[0],
            end_date=batch_dates[-1],
        )
        batch_raw_items_by_date: dict[date, list[dict[str, Any]]] | None = None
        batch_selector = getattr(strategy.lifecycle, "select_signals_for_dates", None)
        if callable(batch_selector):
            batch_raw_items_by_date = batch_selector(
                trade_dates=batch_dates,
                source=batch_rows,
                max_window=window if window > 0 else SIGNAL_WINDOW_BARS,
                index_source=batch_index_rows,
                params_by_date={
                    day: self._strategy_params_for_date(
                        strategy=strategy,
                        trade_date=day,
                        trading_clocks=trading_clocks,
                    )
                    for day in batch_dates
                },
            )

        batch_items: dict[date, list[DailySignalItemDTO]] = {}
        for day in batch_dates:
            if batch_raw_items_by_date is None:
                view = SignalDataView(
                    trade_date=day,
                    source=batch_rows,
                    max_window=window if window > 0 else SIGNAL_WINDOW_BARS,
                    index_source=batch_index_rows,
                    params=self._strategy_params_for_date(
                        strategy=strategy,
                        trade_date=day,
                        trading_clocks=trading_clocks,
                    ),
                )
                raw_items = strategy.lifecycle.select_signals(
                    trade_date=day,
                    view=view,
                )
            else:
                raw_items = batch_raw_items_by_date.get(day, [])
            batch_items[day] = [
                DailySignalItemDTO(
                    code=str(item["code"]),
                    code_name=item.get("code_name"),
                    trade_date=str(item.get("trade_date") or day.isoformat()),
                    universe=item.get("universe") or {},
                    signal=item.get("signal"),
                )
                for item in raw_items
            ]
        return batch_items

    def get_stock_data_contexts(
        self,
        *,
        codes: list[str],
    ) -> StockDataContextResultDTO:
        normalized_codes = self._normalize_codes(codes)
        if not normalized_codes:
            return StockDataContextResultDTO(
                contexts=[],
            )

        universe_rows = self.repository.get_latest_universe_by_codes(codes=normalized_codes)
        universe_by_code = {
            str(row["code"]): row
            for row in universe_rows
            if isinstance(row.get("code"), str)
        }
        bars_by_code = self.repository.get_full_bar_1d_qfq_history(codes=normalized_codes)

        contexts = [
            StockDataContextDTO(
                code=code,
                trade_date=self._resolve_context_trade_date(bars_by_code.get(code, [])),
                universe=universe_by_code[code],
                bars_1d_qfq=bars_by_code.get(code, []),
            )
            for code in normalized_codes
            if code in universe_by_code
        ]
        return StockDataContextResultDTO(contexts=contexts)

    def _run_daily_signal_task(
        self,
        *,
        task_id: int | None,
        trade_date: date,
        strategy_name: str,
        lookback_trade_days: int,
    ) -> None:
        if task_id is None:
            return
        try:
            started_at = time.monotonic()
            self.repository.ensure_tables()
            self.repository.clear_daily_signal_results(task_id)
            self.repository.append_daily_signal_task_log(
                task_id,
                f"开始计算信号: 按交易日切片加载策略可见宽表窗口, batch_workers={self.SIGNAL_BATCH_WORKERS}",
            )
            trade_dates = self._resolve_signal_trade_dates(
                end_date=trade_date,
                lookback_trade_days=lookback_trade_days,
            )

            def report_progress(processed_codes: int, total_codes: int) -> None:
                self.repository.update_daily_signal_task_progress(
                    task_id=task_id,
                    universe_count=total_codes,
                    processed_count=processed_codes,
                )
                self.repository.append_daily_signal_task_log(
                    task_id,
                    f"信号扫描进度: processed_days={processed_codes}/{total_codes}",
                )

            daily_results = self.get_signals_for_dates_by_stock(
                trade_dates=trade_dates,
                strategy_name=strategy_name,
                progress_callback=report_progress,
                progress_interval=self.DAILY_SIGNAL_PROGRESS_INTERVAL,
            )
            result = self._merge_daily_signal_results(
                results=daily_results,
                requested_dates=trade_dates,
                end_date=trade_date,
                strategy_name=strategy_name,
                lookback_trade_days=lookback_trade_days,
            )
            rows = [
                [
                    task_id,
                    date.fromisoformat(item.trade_date),
                    strategy_name,
                    item.code,
                    item.code_name,
                    self.repository.to_json(item.universe),
                    self.repository.to_json(item.signal),
                ]
                for item in result.signals
            ]
            self.repository.insert_daily_signal_results(rows)
            self.repository.update_daily_signal_task_progress(
                task_id=task_id,
                universe_count=result.universe_count,
                processed_count=len(trade_dates),
                signal_count=result.signal_count,
            )
            elapsed = time.monotonic() - started_at
            self.repository.finish_daily_signal_task(
                task_id=task_id,
                status="success",
                message=f"信号计算完成: days={len(trade_dates)}, signals={result.signal_count}, elapsed={elapsed:.2f}s",
            )
        except Exception as exc:
            self.repository.finish_daily_signal_task(
                task_id=task_id,
                status="error",
                message=f"信号计算失败: {exc}",
            )

    def _build_trading_clocks_for_dates(
        self,
        *,
        trading_dates: list[date],
        strategy: Any,
    ) -> dict[date, Any]:
        if not trading_dates or strategy.trading_clock_period is None:
            return {}
        open_dates = self.repository.get_open_trade_dates(
            start_date=trading_dates[0] - timedelta(days=10),
            end_date=trading_dates[-1] + timedelta(days=10),
        )
        return build_trading_clocks(open_dates, period=strategy.trading_clock_period)

    def _build_replay_market_views(
        self,
        *,
        prices: dict[str, dict[date, Bar]],
        trade_date: date,
        previous_trade_date: date | None = None,
        history_frames: dict[str, StockDailyFrame] | None = None,
        index_history_wide: Any | None = None,
    ) -> MarketViews:
        today_bars: dict[str, Bar] = {}
        previous_bars: dict[str, Bar] = {}
        for code, code_prices in prices.items():
            bar = code_prices.get(trade_date)
            if bar is not None:
                today_bars[code] = bar
            previous_bar = (
                code_prices.get(previous_trade_date)
                if previous_trade_date is not None
                else None
            )
            if previous_bar is not None:
                previous_bars[code] = previous_bar
        return MarketViews(
            today_bars=today_bars,
            previous_bars=previous_bars,
            history_by_code=self._slice_history_frames(
                history_frames=history_frames or {},
                trade_date=trade_date,
            ),
            index_history=self._slice_index_history_wide(
                index_history_wide=index_history_wide,
                trade_date=trade_date,
            ),
        )

    def _slice_history_frames(
        self,
        *,
        history_frames: dict[str, StockDailyFrame],
        trade_date: date,
    ) -> dict[str, StockDailyFrame]:
        result: dict[str, StockDailyFrame] = {}
        for code, frame in history_frames.items():
            end = bisect_left(frame.trade_dates, trade_date)
            if end <= 0:
                continue
            start = max(0, end - TRADE_HISTORY_WINDOW_BARS)
            result[code] = StockDailyFrame(
                code=frame.code,
                trade_dates=frame.trade_dates[start:end],
                columns={
                    column: values[start:end]
                    for column, values in frame.columns.items()
                },
            )
        return result

    def _slice_index_history_wide(
        self,
        *,
        index_history_wide: Any | None,
        trade_date: date,
    ) -> Any:
        if index_history_wide is None or index_history_wide.empty:
            return index_history_wide
        trade_dates = index_history_wide["trade_date"].tolist()
        end = bisect_left(trade_dates, trade_date)
        if end <= 0:
            return index_history_wide.iloc[0:0].copy()
        start = max(0, end - SIGNAL_WINDOW_BARS)
        return index_history_wide.iloc[start:end].copy()

    def _with_replay_buy_fields(
        self,
        *,
        signal: dict[str, Any],
        buy_price: float,
    ) -> dict[str, Any]:
        copied = dict(signal)
        extras = dict(copied.get("extras") or {})
        signal_close = self._to_float(copied.get("signal_close"))
        if signal_close is not None and signal_close > 0 and math.isfinite(buy_price):
            extras["signal_replay_buy_price_to_signal_close"] = buy_price / signal_close - 1.0
        copied["extras"] = extras
        return copied

    def _initial_max_high_since_buy(self, *, bar: Bar | None, buy_price: float) -> float:
        if bar is not None and len(bar) > 1 and math.isfinite(bar[1]):
            return max(bar[1], buy_price)
        return buy_price

    def _signal_date_from_signal(self, signal: dict[str, Any] | None) -> str | None:
        if not signal:
            return None
        display = signal.get("display")
        if isinstance(display, dict):
            value = display.get("signal_date")
            if isinstance(value, str) and value:
                return value
        value = signal.get("trade_date")
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, str) and value:
            return value
        extras = signal.get("extras")
        if isinstance(extras, dict):
            for key in ("signal_date", "trade_date", "pattern_signal_date"):
                extra_value = extras.get(key)
                if isinstance(extra_value, date):
                    return extra_value.isoformat()
                if isinstance(extra_value, str) and extra_value:
                    return extra_value
        return None

    def _to_float(self, value: Any) -> float | None:
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            return float(value)
        return None

    def _normalize_codes(self, codes: list[str]) -> list[str]:
        seen: set[str] = set()
        normalized: list[str] = []
        for code in codes:
            item = code.strip().lower()
            if not item or item in seen:
                continue
            seen.add(item)
            normalized.append(item)
        return normalized

    def _normalize_lookback_trade_days(self, value: int) -> int:
        try:
            days = int(value)
        except (TypeError, ValueError):
            raise SignalServiceError("lookback_trade_days must be an integer") from None
        if days < 1:
            raise SignalServiceError("lookback_trade_days must be >= 1")
        return min(days, 120)

    def _resolve_signal_trade_dates(
        self,
        *,
        end_date: date,
        lookback_trade_days: int,
    ) -> list[date]:
        start_probe = end_date - timedelta(days=max(lookback_trade_days * 3, 30))
        open_dates = self.repository.get_open_trade_dates(
            start_date=start_probe,
            end_date=end_date,
        )
        selected = [day for day in open_dates if day <= end_date][-lookback_trade_days:]
        if not selected:
            return [end_date]
        return selected

    def _merge_daily_signal_results(
        self,
        *,
        results: dict[date, DailySignalResultDTO],
        requested_dates: list[date],
        end_date: date,
        strategy_name: str,
        lookback_trade_days: int,
    ) -> DailySignalResultDTO:
        signals: list[DailySignalItemDTO] = []
        universe_count = 0
        for day in requested_dates:
            result = results.get(day)
            if result is None:
                continue
            universe_count += int(result.universe_count or 0)
            signals.extend(result.signals)
        signals.sort(key=lambda item: (item.trade_date, item.code), reverse=True)
        start_date = requested_dates[0] if requested_dates else end_date
        return DailySignalResultDTO(
            trade_date=end_date.isoformat(),
            strategy_name=strategy_name,
            universe_count=universe_count,
            signal_count=len(signals),
            signals=signals,
            start_trade_date=start_date.isoformat(),
            end_trade_date=end_date.isoformat(),
            lookback_trade_days=lookback_trade_days,
        )

    def _chunked(self, values: list[str], size: int) -> list[list[str]]:
        return [
            values[index : index + size]
            for index in range(0, len(values), size)
        ]

    def _date_batches(self, values: list[date], size: int) -> list[list[date]]:
        return [
            values[index : index + size]
            for index in range(0, len(values), max(size, 1))
        ]

    def _signal_batch_size(
        self,
        *,
        window: int,
        required_columns: tuple[str, ...] | None,
    ) -> int:
        if window <= 0:
            return self.SIGNAL_BATCH_DAYS_NO_HISTORY
        if required_columns is not None and len(required_columns) <= 16:
            return self.SIGNAL_BATCH_DAYS_WITH_NARROW_HISTORY
        return self.SIGNAL_BATCH_DAYS_WITH_HISTORY

    def _strategy_params_for_date(
        self,
        *,
        strategy: Any,
        trade_date: date,
        trading_clocks: dict[date, Any],
    ) -> dict[str, Any]:
        clock = trading_clocks.get(trade_date)
        if clock is None:
            return {}
        params = {
            "trading_clock": clock.to_params(),
            "is_rebalance_period_start": strategy.is_rebalance_day(clock),
            "is_signal_period_end": strategy.is_signal_day(clock),
        }
        return params

    def _report_progress(
        self,
        *,
        progress_callback: Any | None,
        processed_codes: int,
        total_codes: int,
        progress_interval: int,
    ) -> None:
        if progress_callback is None:
            return
        if (
            processed_codes == 1
            or processed_codes % progress_interval == 0
            or processed_codes == total_codes
            ):
            progress_callback(processed_codes, total_codes)

    def _report_batch_progress(
        self,
        *,
        progress_callback: Any | None,
        processed_days: int,
        batch_dates: list[date],
        total_days: int,
        progress_interval: int,
    ) -> int:
        for _day in batch_dates:
            processed_days += 1
            self._report_progress(
                progress_callback=progress_callback,
                processed_codes=processed_days,
                total_codes=total_days,
                progress_interval=max(progress_interval, 1),
            )
        return processed_days

    def _resolve_context_trade_date(self, bars: list[dict[str, Any]]) -> str:
        if not bars:
            return ""
        value = bars[-1].get("trade_date")
        return value if isinstance(value, str) else ""
