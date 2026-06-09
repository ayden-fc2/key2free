from __future__ import annotations

from bisect import bisect_right
from dataclasses import asdict, is_dataclass
from datetime import date
from typing import Any

from app.dtos.signal_dto import (
    DailySignalItemDTO,
    DailySignalResultDTO,
    StockDataContextDTO,
    StockDataContextResultDTO,
)
from app.entities.stock_data_context import StockDataContext
from app.repositories.signal_repository import SignalRepository
from app.services.strategy_registry import get_strategy


class SignalServiceError(ValueError):
    pass


class SignalService:
    SIGNAL_CODE_BATCH_SIZE = 300

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
        progress_interval: int = 200,
    ) -> dict[date, DailySignalResultDTO]:
        normalized_dates = sorted(set(trade_dates))
        if not normalized_dates:
            return {}

        strategy = get_strategy(strategy_name)
        if strategy is None:
            raise SignalServiceError(f"unknown strategy: {strategy_name}")

        start_date = normalized_dates[0]
        end_date = normalized_dates[-1]
        result_items_by_date: dict[date, list[DailySignalItemDTO]] = {
            day: []
            for day in normalized_dates
        }

        limit_per_code = getattr(strategy, "daily_signal_history_limit", None)
        universe_counts_by_date: dict[date, int] = {
            day: 0
            for day in normalized_dates
        }
        all_codes = self.repository.get_universe_codes_range(
            start_date=start_date,
            end_date=end_date,
        )
        total_codes = len(all_codes)
        processed_codes = 0

        for code_batch in self._chunked(all_codes, self.SIGNAL_CODE_BATCH_SIZE):
            universe_by_date = self.repository.get_universe_daily_range_by_codes(
                start_date=start_date,
                end_date=end_date,
                codes=code_batch,
            )
            eligible_by_date: dict[date, dict[str, dict[str, Any]]] = {}
            eligible_codes_in_batch: set[str] = set()
            for day in normalized_dates:
                universe_by_code = universe_by_date.get(day, {})
                universe_counts_by_date[day] += len(universe_by_code)
                eligible_codes = self._prefilter_universe_codes(
                    trade_date=day,
                    universe_by_code=universe_by_code,
                    universe_filter=getattr(strategy, "universe_filter", None),
                )
                eligible_by_date[day] = {
                    code: universe_by_code[code]
                    for code in eligible_codes
                    if code in universe_by_code
                }
                eligible_codes_in_batch.update(eligible_by_date[day])

            bars_by_code = self.repository.get_bar_1d_qfq_history_for_signal_range(
                codes=sorted(eligible_codes_in_batch),
                start_date=start_date,
                end_date=end_date,
                limit_before_start=limit_per_code,
            )
            for code in code_batch:
                processed_codes += 1
                bars = bars_by_code.get(code, [])
                if not bars:
                    self._report_progress(
                        progress_callback=progress_callback,
                        processed_codes=processed_codes,
                        total_codes=total_codes,
                        progress_interval=progress_interval,
                    )
                    continue
                bar_dates = [
                    trade_date_value
                    for item in bars
                    for trade_date_value in [self._coerce_date(item.get("trade_date"))]
                    if trade_date_value is not None
                ]
                if len(bar_dates) != len(bars):
                    self._report_progress(
                        progress_callback=progress_callback,
                        processed_codes=processed_codes,
                        total_codes=total_codes,
                        progress_interval=progress_interval,
                    )
                    continue
                active_dates = [
                    day
                    for day in normalized_dates
                    if code in eligible_by_date.get(day, {})
                ]
                batch_signal_strategy = getattr(strategy, "batch_signal_strategy", None)
                if batch_signal_strategy is not None:
                    signal_payloads = batch_signal_strategy(
                        code=code,
                        target_dates=active_dates,
                        universe_by_date={
                            day: eligible_by_date[day][code]
                            for day in active_dates
                        },
                        bars=bars,
                        history_limit=limit_per_code,
                    )
                    for day, signal_result in signal_payloads.items():
                        universe = eligible_by_date.get(day, {}).get(code)
                        if universe is None:
                            continue
                        signal_payload = self._normalize_signal_result(signal_result)
                        if signal_payload is None:
                            continue
                        result_items_by_date[day].append(
                            DailySignalItemDTO(
                                code=code,
                                code_name=self._optional_string(universe.get("code_name")),
                                trade_date=day.isoformat(),
                                universe=universe,
                                signal=signal_payload,
                            )
                        )
                else:
                    for day in active_dates:
                        end_index = bisect_right(bar_dates, day)
                        if end_index <= 0:
                            window_bars: list[dict[str, Any]] = []
                        elif limit_per_code is None:
                            window_bars = bars[:end_index]
                        else:
                            window_bars = bars[max(0, end_index - limit_per_code):end_index]
                        universe = eligible_by_date[day][code]
                        self._append_signal_if_triggered(
                            signal_items=result_items_by_date[day],
                            code=code,
                            trade_date=day,
                            universe=universe,
                            bars=window_bars,
                            signal_strategy=strategy.signal_strategy,
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
                universe_count=universe_counts_by_date.get(day, 0),
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

    def _append_signal_if_triggered(
        self,
        *,
        signal_items: list[DailySignalItemDTO],
        code: str,
        trade_date: date,
        universe: dict[str, Any],
        bars: list[dict[str, Any]],
        signal_strategy: Any,
    ) -> None:
        context = StockDataContext(
            code=code,
            trade_date=trade_date,
            universe=universe,
            bars_1d_qfq=bars,
        )
        signal_result = signal_strategy(context)
        signal_payload = self._normalize_signal_result(signal_result)
        if signal_payload is None:
            return
        signal_items.append(
            DailySignalItemDTO(
                code=code,
                code_name=self._optional_string(universe.get("code_name")),
                trade_date=trade_date.isoformat(),
                universe=universe,
                signal=signal_payload,
            )
        )

    def _prefilter_universe_codes(
        self,
        *,
        trade_date: date,
        universe_by_code: dict[str, dict[str, Any]],
        universe_filter: Any,
    ) -> list[str]:
        if universe_filter is None:
            return list(universe_by_code)

        codes: list[str] = []
        for code, universe in universe_by_code.items():
            context = StockDataContext(
                code=code,
                trade_date=trade_date,
                universe=universe,
                bars_1d_qfq=[],
            )
            if universe_filter(context):
                codes.append(code)
        return codes

    def _optional_string(self, value: Any) -> str | None:
        return value if isinstance(value, str) else None

    def _normalize_signal_result(self, value: Any) -> dict[str, Any] | None:
        if isinstance(value, bool):
            return {"triggered": True} if value else None
        if is_dataclass(value):
            payload = asdict(value)
        elif isinstance(value, dict):
            payload = dict(value)
        else:
            triggered = getattr(value, "triggered", None)
            if triggered is None:
                return None
            payload = {
                "triggered": triggered,
                "min_stop_loss": getattr(value, "min_stop_loss", None),
                "reference_take_profit": getattr(value, "reference_take_profit", None),
                "signal_atr30": getattr(value, "signal_atr30", None),
                "ideal_buy_price": getattr(value, "ideal_buy_price", None),
                "max_watch_days": getattr(value, "max_watch_days", None),
            }
        if not payload.get("triggered"):
            return None
        return payload

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

    def _coerce_date(self, value: Any) -> date | None:
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                return date.fromisoformat(value[:10])
            except ValueError:
                return None
        return None

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
