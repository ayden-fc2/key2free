from __future__ import annotations

from datetime import date
from dataclasses import asdict, is_dataclass
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
        codes = self._prefilter_universe_codes(
            trade_date=trade_date,
            universe_by_code=universe_by_code,
            universe_filter=getattr(strategy, "universe_filter", None),
        )
        skipped_codes = set(universe_by_code) - set(codes)

        signal_items: list[DailySignalItemDTO] = []
        handled_codes: set[str] = set(skipped_codes)
        for code, bars in self.repository.iter_bar_1d_qfq_history_groups(
            codes=codes,
            trade_date=trade_date,
            limit_per_code=getattr(strategy, "daily_signal_history_limit", None),
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

    def _resolve_context_trade_date(self, bars: list[dict[str, Any]]) -> str:
        if not bars:
            return ""
        value = bars[-1].get("trade_date")
        return value if isinstance(value, str) else ""
