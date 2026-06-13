from __future__ import annotations

from datetime import date
from typing import Any

from app.dtos.signal_dto import (
    DailySignalItemDTO,
    DailySignalResultDTO,
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

    def __init__(self) -> None:
        self.repository = SignalRepository()

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

        for code_batch in self._chunked(all_codes, self.SIGNAL_CODE_BATCH_SIZE):
            frames = self.repository.load_stock_frames(
                codes=code_batch,
                start_date=start_date,
                end_date=end_date,
                window=SIGNAL_WINDOW_BARS,
                extra_columns=strategy.required_columns,
            )
            for code in code_batch:
                processed_codes += 1
                frame = frames.get(code)
                if frame is not None and len(frame) >= SIGNAL_WINDOW_BARS:
                    # 目标位置：日期在请求集合内，且该位置（含自身）至少有 400 根历史
                    target_indices = [
                        index
                        for index, day in enumerate(frame.trade_dates)
                        if index + 1 >= SIGNAL_WINDOW_BARS and day in target_date_set
                    ]
                    if target_indices:
                        decisions = strategy.batch_signal_strategy(frame, target_indices)
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
                            result_items_by_date[day].append(
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
                self._report_progress(
                    progress_callback=progress_callback,
                    processed_codes=processed_codes,
                    total_codes=total_codes,
                    progress_interval=progress_interval,
                )

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
