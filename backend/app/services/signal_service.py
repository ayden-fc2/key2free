from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from typing import Any

from app.dtos.signal_dto import (
    DailySignalItemDTO,
    DailySignalResultDTO,
    DailySignalTaskDTO,
    DailySignalTaskStartDTO,
    StockDataContextDTO,
    StockDataContextResultDTO,
)
from app.repositories.signal_repository import SignalRepository
from app.services.strategy_data_view import SignalDataView
from app.services.signal_window import SIGNAL_WINDOW_BARS
from app.services.strategy_registry import get_strategy
from app.services.trading_periods import build_trading_clocks


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
