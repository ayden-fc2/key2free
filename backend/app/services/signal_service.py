from __future__ import annotations

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
    def __init__(self) -> None:
        self.repository = SignalRepository()

    def get_daily_signals(
        self,
        *,
        trade_date: date,
        strategy_name: str,
    ) -> DailySignalResultDTO:
        strategy = get_strategy(strategy_name)
        if strategy is None:
            raise SignalServiceError(f"unknown strategy: {strategy_name}")

        universe_rows = self.repository.get_universe_daily(trade_date)
        universe_by_code = {
            str(row["code"]): row
            for row in universe_rows
            if isinstance(row.get("code"), str)
        }
        codes = list(universe_by_code)

        signal_items: list[DailySignalItemDTO] = []
        handled_codes: set[str] = set()
        for code, bars in self.repository.iter_bar_1d_qfq_history_groups(
            codes=codes,
            trade_date=trade_date,
        ):
            universe = universe_by_code.get(code)
            if universe is None:
                continue
            handled_codes.add(code)
            self._append_signal_if_triggered(
                signal_items=signal_items,
                code=code,
                trade_date=trade_date,
                universe=universe,
                bars=bars,
                signal_strategy=strategy.signal_strategy,
            )

        for code, universe in universe_by_code.items():
            if code in handled_codes:
                continue
            self._append_signal_if_triggered(
                signal_items=signal_items,
                code=code,
                trade_date=trade_date,
                universe=universe,
                bars=[],
                signal_strategy=strategy.signal_strategy,
            )

        return DailySignalResultDTO(
            trade_date=trade_date.isoformat(),
            strategy_name=strategy.name,
            universe_count=len(universe_rows),
            signal_count=len(signal_items),
            signals=signal_items,
        )

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
        if not signal_strategy(context):
            return
        signal_items.append(
            DailySignalItemDTO(
                code=code,
                code_name=self._optional_string(universe.get("code_name")),
                trade_date=trade_date.isoformat(),
                universe=universe,
            )
        )

    def _optional_string(self, value: Any) -> str | None:
        return value if isinstance(value, str) else None

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

    def _resolve_context_trade_date(self, bars: list[dict[str, Any]]) -> str:
        if not bars:
            return ""
        value = bars[-1].get("trade_date")
        return value if isinstance(value, str) else ""
