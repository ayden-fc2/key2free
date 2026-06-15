from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import Any

from app.dtos.signal_dto import (
    DailySignalItemDTO,
    DailySignalResultDTO,
    DailySignalTaskDTO,
    DailySignalTaskStartDTO,
    StockDataContextDTO,
    StockDataContextResultDTO,
)
from app.entities.stock_data_context import SignalDecision
from app.repositories.signal_repository import SignalRepository
from app.services.signal_window import SIGNAL_WINDOW_BARS
from app.services.strategy_registry import get_strategy


class SignalServiceError(ValueError):
    pass


class SignalService:
    SIGNAL_CODE_BATCH_SIZE = 400
    SIGNAL_WORKERS = 10
    DAILY_SIGNAL_PROGRESS_INTERVAL = 500

    def __init__(self) -> None:
        self.repository = SignalRepository()

    def request_daily_signal_task(
        self,
        *,
        trade_date: date,
        strategy_name: str,
    ) -> DailySignalTaskStartDTO:
        if get_strategy(strategy_name) is None:
            raise SignalServiceError(f"unknown strategy: {strategy_name}")

        latest_task = self.repository.get_latest_daily_signal_task(
            trade_date=trade_date,
            strategy_name=strategy_name,
        )
        if latest_task is not None and latest_task.status == "success":
            return DailySignalTaskStartDTO(
                task=latest_task,
                message="daily signal task already completed",
            )
        if latest_task is not None and latest_task.status == "running":
            return DailySignalTaskStartDTO(
                task=latest_task,
                message="daily signal task already running",
            )

        task = self.repository.create_daily_signal_task(
            trade_date=trade_date,
            strategy_name=strategy_name,
            initial_log=(
                f"创建当日信号任务: strategy={strategy_name}, trade_date={trade_date.isoformat()}, "
                f"workers={self.SIGNAL_WORKERS}"
            ),
        )
        thread = threading.Thread(
            target=self._run_daily_signal_task,
            kwargs={
                "task_id": task.id,
                "trade_date": trade_date,
                "strategy_name": strategy_name,
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
    ) -> DailySignalResultDTO:
        result_by_date = self.get_signals_for_dates_by_stock(
            trade_dates=[trade_date],
            strategy_name=strategy_name,
        )
        return result_by_date.get(
            trade_date,
            DailySignalResultDTO(
                trade_date=trade_date.isoformat(),
                strategy_name=strategy_name,
                universe_count=0,
                signal_count=0,
                signals=[],
            ),
        )

    def get_signals_for_dates_by_stock(
        self,
        *,
        trade_dates: list[date],
        strategy_name: str,
        progress_callback: Any | None = None,
        progress_interval: int = 500,
    ) -> dict[date, DailySignalResultDTO]:
        """逐股批量评估：每只股票的宽表历史只加载一次，区间内所有目标日共享。"""
        normalized_dates = sorted(set(trade_dates))
        if not normalized_dates:
            return {}

        strategy = get_strategy(strategy_name)
        if strategy is None:
            raise SignalServiceError(f"unknown strategy: {strategy_name}")

        start_date = normalized_dates[0]
        end_date = normalized_dates[-1]
        target_date_set = set(normalized_dates)
        result_items_by_date: dict[date, list[DailySignalItemDTO]] = {
            day: [] for day in normalized_dates
        }

        universe_counts = self.repository.get_universe_counts_by_date(
            start_date=start_date,
            end_date=end_date,
        )
        all_codes = self.repository.get_codes_in_range(
            start_date=start_date,
            end_date=end_date,
        )
        if strategy.code_filter is not None:
            all_codes = [code for code in all_codes if strategy.code_filter(code)]
        total_codes = len(all_codes)
        processed_codes = 0
        code_order = {code: index for index, code in enumerate(all_codes)}
        max_workers = min(self.SIGNAL_WORKERS, max(total_codes, 1))

        def evaluate_code(code: str) -> tuple[int, list[DailySignalItemDTO]]:
            frame = frames.get(code)
            if frame is None or len(frame) < SIGNAL_WINDOW_BARS:
                return code_order[code], []
            # 目标位置：日期在请求集合内，且该位置（含自身）至少有 400 根历史
            target_indices = [
                index
                for index, day in enumerate(frame.trade_dates)
                if index + 1 >= SIGNAL_WINDOW_BARS and day in target_date_set
            ]
            if not target_indices:
                return code_order[code], []
            decisions = strategy.batch_signal_strategy(frame, target_indices)
            items: list[DailySignalItemDTO] = []
            for index, decision in decisions.items():
                if not decision.triggered:
                    continue
                day = frame.trade_dates[index]
                name_value = frame.columns.get("name")
                code_name = (
                    str(name_value[index])
                    if name_value is not None and name_value[index] is not None
                    else None
                )
                items.append(
                    DailySignalItemDTO(
                        code=code,
                        code_name=code_name,
                        trade_date=day.isoformat(),
                        universe={
                            "trade_date": day.isoformat(),
                            "code": code,
                            "code_name": code_name,
                        },
                        signal=self._decision_to_payload(decision),
                    )
                )
            return code_order[code], items

        for code_batch in self._chunked(all_codes, self.SIGNAL_CODE_BATCH_SIZE):
            frames = self.repository.load_stock_frames(
                codes=code_batch,
                start_date=start_date,
                end_date=end_date,
                window=SIGNAL_WINDOW_BARS,
                extra_columns=strategy.required_columns,
            )
            batch_results: list[tuple[int, list[DailySignalItemDTO]]] = []
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(evaluate_code, code) for code in code_batch]
                for future in as_completed(futures):
                    batch_results.append(future.result())
                    processed_codes += 1
                    self._report_progress(
                        progress_callback=progress_callback,
                        processed_codes=processed_codes,
                        total_codes=total_codes,
                        progress_interval=progress_interval,
                    )
            for _order, items in sorted(batch_results, key=lambda item: item[0]):
                for item in items:
                    result_items_by_date[date.fromisoformat(item.trade_date)].append(item)

        return {
            day: DailySignalResultDTO(
                trade_date=day.isoformat(),
                strategy_name=strategy.name,
                universe_count=universe_counts.get(day, 0),
                signal_count=len(result_items_by_date[day]),
                signals=result_items_by_date[day],
            )
            for day in normalized_dates
        }

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

    def _decision_to_payload(self, decision: SignalDecision) -> dict[str, Any]:
        return {
            "triggered": bool(decision.triggered),
            "signal_close": decision.signal_close,
            "stop_losses": [float(value) for value in decision.stop_losses],
            "take_profits": [float(value) for value in decision.take_profits],
            "max_watch_days": decision.max_watch_days,
            "extras": decision.extras,
        }

    def _run_daily_signal_task(
        self,
        *,
        task_id: int | None,
        trade_date: date,
        strategy_name: str,
    ) -> None:
        if task_id is None:
            return
        try:
            started_at = time.monotonic()
            self.repository.ensure_tables()
            self.repository.clear_daily_signal_results(task_id)
            self.repository.append_daily_signal_task_log(
                task_id,
                "开始计算当日信号: 全市场逐股批量加载宽表窗口",
            )

            def report_progress(processed_codes: int, total_codes: int) -> None:
                self.repository.update_daily_signal_task_progress(
                    task_id=task_id,
                    universe_count=total_codes,
                    processed_count=processed_codes,
                )
                self.repository.append_daily_signal_task_log(
                    task_id,
                    f"信号扫描进度: processed={processed_codes}/{total_codes}",
                )

            result = self.get_signals_for_dates_by_stock(
                trade_dates=[trade_date],
                strategy_name=strategy_name,
                progress_callback=report_progress,
                progress_interval=self.DAILY_SIGNAL_PROGRESS_INTERVAL,
            ).get(
                trade_date,
                DailySignalResultDTO(
                    trade_date=trade_date.isoformat(),
                    strategy_name=strategy_name,
                    universe_count=0,
                    signal_count=0,
                    signals=[],
                ),
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
            task = self.repository.get_daily_signal_task(task_id)
            task_universe_count = (
                task.universe_count
                if task is not None and task.universe_count is not None
                else result.universe_count
            )
            self.repository.update_daily_signal_task_progress(
                task_id=task_id,
                universe_count=task_universe_count,
                processed_count=task_universe_count,
                signal_count=result.signal_count,
            )
            elapsed = time.monotonic() - started_at
            self.repository.finish_daily_signal_task(
                task_id=task_id,
                status="success",
                message=f"当日信号计算完成: signals={result.signal_count}, elapsed={elapsed:.2f}s",
            )
        except Exception as exc:
            self.repository.finish_daily_signal_task(
                task_id=task_id,
                status="error",
                message=f"当日信号计算失败: {exc}",
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

    def _chunked(self, values: list[str], size: int) -> list[list[str]]:
        return [
            values[index : index + size]
            for index in range(0, len(values), size)
        ]

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

    def _resolve_context_trade_date(self, bars: list[dict[str, Any]]) -> str:
        if not bars:
            return ""
        value = bars[-1].get("trade_date")
        return value if isinstance(value, str) else ""
