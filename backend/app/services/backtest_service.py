from __future__ import annotations

import random
import threading
import time
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from app.dtos.backtest_dto import BacktestStartDTO
from app.dtos.data_asset_dto import TaskDTO
from app.repositories.backtest_repository import BacktestRepository
from app.repositories.task_repository import TaskRepository
from app.services.signal_service import SignalService
from app.services.strategy_registry import get_strategy


@dataclass
class WatchItem:
    code: str
    code_name: str | None
    added_date: date
    added_trade_index: int
    min_stop_loss: float | None
    reference_take_profit: float | None
    signal_atr30: float | None
    ideal_buy_price: float | None
    max_watch_days: int | None
    signal: dict[str, Any]


@dataclass
class HoldingItem:
    code: str
    code_name: str | None
    buy_date: date
    buy_price: float
    quantity: int
    buy_fee: float
    min_stop_loss: float | None
    reference_take_profit: float | None
    signal_atr30: float | None


class BacktestService:
    TASK_TYPE = "backtest"
    BUY_FEE_BPS = 5
    SELL_FEE_BPS = 10
    SIMULATION_RUNS = 50

    def __init__(self) -> None:
        self.tasks = TaskRepository()
        self.repository = BacktestRepository()

    def request_backtest(
        self,
        *,
        start_date: date,
        end_date: date,
        initial_cash: float,
        strategy_name: str,
    ) -> BacktestStartDTO:
        if start_date > end_date:
            raise ValueError("start_date must be <= end_date")
        if initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if get_strategy(strategy_name) is None:
            raise ValueError(f"unknown strategy: {strategy_name}")

        task = self.tasks.create_task(
            self.TASK_TYPE,
            (
                f"创建回测任务: strategy={strategy_name}, "
                f"range={start_date.isoformat()}->{end_date.isoformat()}, "
                f"initial_cash={initial_cash:.2f}, simulation_runs={self.SIMULATION_RUNS}"
            ),
        )
        thread = threading.Thread(
            target=self._run_backtest_task,
            kwargs={
                "task_id": task.id,
                "start_date": start_date,
                "end_date": end_date,
                "initial_cash": float(initial_cash),
                "strategy_name": strategy_name,
            },
            daemon=True,
        )
        thread.start()
        return BacktestStartDTO(task=task, message="backtest task created")

    def get_backtest_task(self, task_id: int | None = None) -> TaskDTO | None:
        if task_id is None:
            return self.tasks.get_latest_task_by_type(self.TASK_TYPE)
        return self.tasks.get_task(task_id)

    def list_backtest_tasks(self, limit: int = 100) -> list[TaskDTO]:
        return self.tasks.list_tasks_by_type(self.TASK_TYPE, limit=limit)

    def _run_backtest_task(
        self,
        *,
        task_id: int,
        start_date: date,
        end_date: date,
        initial_cash: float,
        strategy_name: str,
    ) -> None:
        try:
            self.repository.ensure_tables()
            self.repository.clear_task_rows(task_id)
            trading_dates = self.repository.get_trading_dates(
                start_date=start_date,
                end_date=end_date,
            )
            if not trading_dates:
                raise RuntimeError("no trading dates in backtest range")
            self.tasks.append_log(task_id, f"交易日数量: {len(trading_dates)}")

            strategy = get_strategy(strategy_name)
            if strategy is None:
                raise RuntimeError(f"unknown strategy: {strategy_name}")

            signals_by_date = self._precompute_signals(
                task_id=task_id,
                trading_dates=trading_dates,
                strategy_name=strategy_name,
            )
            random_seed = time.time_ns()
            self.tasks.append_log(
                task_id,
                f"开始 {self.SIMULATION_RUNS} 轮随机撮合: seed={random_seed}",
            )
            for run_no in range(1, self.SIMULATION_RUNS + 1):
                final_asset = self._simulate(
                    task_id=task_id,
                    run_no=run_no,
                    random_seed=random_seed,
                    trading_dates=trading_dates,
                    initial_cash=initial_cash,
                    strategy=strategy,
                    signals_by_date=signals_by_date,
                )
                self.tasks.append_log(
                    task_id,
                    f"随机撮合完成 {run_no}/{self.SIMULATION_RUNS}: final_asset={final_asset:.2f}",
                )
            self.tasks.finish_task(task_id, "success", "回测完成。")
        except Exception as exc:
            self.tasks.finish_task(task_id, "error", f"回测失败: {exc}")

    def _precompute_signals(
        self,
        *,
        task_id: int,
        trading_dates: list[date],
        strategy_name: str,
    ) -> dict[date, list[dict[str, Any]]]:
        signals_by_date: dict[date, list[dict[str, Any]]] = {}
        self.tasks.append_log(task_id, f"开始按股票维度预计算信号: {strategy_name}")
        daily_results = SignalService().get_signals_for_dates_by_stock(
            trade_dates=trading_dates,
            strategy_name=strategy_name,
            progress_callback=lambda done, total: self.tasks.append_log(
                task_id,
                f"股票维度信号预计算进度: {done}/{total}",
            ),
            progress_interval=200,
        )
        for completed, day in enumerate(trading_dates, start=1):
            result = daily_results.get(day)
            signals = [] if result is None else [
                {
                    "code": item.code,
                    "code_name": item.code_name,
                    "trade_date": item.trade_date,
                    "universe": item.universe,
                    "signal": item.signal or {"triggered": True},
                }
                for item in result.signals
            ]
            signals_by_date[day] = signals
            self.repository.insert_signals(
                task_id=task_id,
                trade_date=day,
                strategy_name=strategy_name,
                signals=signals,
            )
            if completed == 1 or completed % 20 == 0 or completed == len(trading_dates):
                self.tasks.append_log(
                    task_id,
                    f"信号预计算 {completed}/{len(trading_dates)}: {day.isoformat()} signals={len(signals)}",
                )
        return signals_by_date

    def _simulate(
        self,
        *,
        task_id: int,
        run_no: int,
        random_seed: int,
        trading_dates: list[date],
        initial_cash: float,
        strategy: Any,
        signals_by_date: dict[date, list[dict[str, Any]]],
    ) -> float:
        cash = initial_cash
        holdings: dict[str, HoldingItem] = {}
        watch_pool: dict[str, WatchItem] = {}
        self.tasks.append_log(task_id, f"开始第 {run_no} 轮事件驱动撮合。")

        for trade_index, trade_date in enumerate(trading_dates):
            bar_codes = list(
                set(holdings)
                | set(watch_pool)
                | {signal["code"] for signal in signals_by_date.get(trade_date, [])}
            )
            bar_map = self.repository.get_bar_map(trade_date=trade_date, codes=bar_codes)

            cash = self._process_sells(
                task_id=task_id,
                run_no=run_no,
                trade_date=trade_date,
                cash=cash,
                holdings=holdings,
                bar_map=bar_map,
                exit_strategy=strategy.exit_strategy,
            )
            cash = self._process_watches(
                task_id=task_id,
                run_no=run_no,
                random_seed=random_seed,
                trade_date=trade_date,
                trade_index=trade_index,
                cash=cash,
                holdings=holdings,
                watch_pool=watch_pool,
                bar_map=bar_map,
                entry_strategy=strategy.entry_strategy,
            )
            self._add_new_signals_to_watch_pool(
                trade_date=trade_date,
                trade_index=trade_index,
                signals=signals_by_date.get(trade_date, []),
                holdings=holdings,
                watch_pool=watch_pool,
            )
            self._snapshot(
                task_id=task_id,
                run_no=run_no,
                trade_date=trade_date,
                cash=cash,
                holdings=holdings,
                watch_pool=watch_pool,
                bar_map=bar_map,
            )
            progress = trade_index + 1
            if run_no == 1 and (progress == 1 or progress % 50 == 0 or progress == len(trading_dates)):
                self.tasks.append_log(
                    task_id,
                    (
                        f"第 {run_no} 轮撮合进度 {progress}/{len(trading_dates)}: "
                        f"cash={cash:.2f}, holdings={len(holdings)}, watch={len(watch_pool)}"
                    ),
                )

        final_bar_map = self.repository.get_bar_map(
            trade_date=trading_dates[-1],
            codes=list(holdings),
        )
        return self._estimate_total_asset(
            cash=cash,
            holdings=holdings,
            bar_map=final_bar_map,
        )

    def _process_sells(
        self,
        *,
        task_id: int,
        run_no: int,
        trade_date: date,
        cash: float,
        holdings: dict[str, HoldingItem],
        bar_map: dict[str, dict[str, Any]],
        exit_strategy: Any,
    ) -> float:
        for code, holding in list(holdings.items()):
            if holding.buy_date >= trade_date:
                continue
            bar = bar_map.get(code)
            if not self._is_tradeable_bar(bar):
                continue
            sell_price = exit_strategy(
                open_price=bar["open"],
                close_price=bar["close"],
                high_price=bar["high"],
                low_price=bar["low"],
                buy_date=holding.buy_date,
                min_stop_loss=holding.min_stop_loss,
                reference_take_profit=holding.reference_take_profit,
                signal_atr30=holding.signal_atr30,
            )
            if sell_price == -1:
                continue
            sell_price = float(sell_price)
            amount = sell_price * holding.quantity
            fee = amount * self.SELL_FEE_BPS / 10000
            cash += amount - fee
            pnl = (sell_price - holding.buy_price) * holding.quantity - holding.buy_fee - fee
            self.repository.insert_sell_order(
                task_id=task_id,
                run_no=run_no,
                trade_date=trade_date,
                code=code,
                code_name=holding.code_name,
                sell_price=sell_price,
                quantity=holding.quantity,
                amount=amount,
                fee=fee,
                cash_after=cash,
                buy_date=holding.buy_date,
                buy_price=holding.buy_price,
                pnl=pnl,
            )
            del holdings[code]
        return cash

    def _process_watches(
        self,
        *,
        task_id: int,
        run_no: int,
        random_seed: int,
        trade_date: date,
        trade_index: int,
        cash: float,
        holdings: dict[str, HoldingItem],
        watch_pool: dict[str, WatchItem],
        bar_map: dict[str, dict[str, Any]],
        entry_strategy: Any,
    ) -> float:
        items = list(watch_pool.values())
        random.Random(f"{random_seed}:{run_no}:{trade_date.isoformat()}").shuffle(items)
        for item in items:
            if item.added_date >= trade_date:
                continue
            bar = bar_map.get(item.code)
            if not self._is_tradeable_bar(bar):
                if self._watch_expired(item, trade_index):
                    watch_pool.pop(item.code, None)
                continue
            buy_price = entry_strategy(
                open_price=bar["open"],
                close_price=bar["close"],
                high_price=bar["high"],
                low_price=bar["low"],
                min_stop_loss=item.min_stop_loss,
                reference_take_profit=item.reference_take_profit,
                signal_atr30=item.signal_atr30,
                ideal_buy_price=item.ideal_buy_price,
            )
            if buy_price == -1:
                if self._watch_expired(item, trade_index):
                    watch_pool.pop(item.code, None)
                continue
            buy_price = float(buy_price)
            total_asset = self._estimate_total_asset(
                cash=cash,
                holdings=holdings,
                bar_map=bar_map,
            )
            quantity = self._resolve_buy_quantity(
                cash=cash,
                total_asset=total_asset,
                buy_price=buy_price,
            )
            if quantity <= 0:
                continue
            amount = buy_price * quantity
            fee = amount * self.BUY_FEE_BPS / 10000
            if amount + fee > cash:
                continue
            cash -= amount + fee
            holdings[item.code] = HoldingItem(
                code=item.code,
                code_name=item.code_name,
                buy_date=trade_date,
                buy_price=buy_price,
                quantity=quantity,
                buy_fee=fee,
                min_stop_loss=item.min_stop_loss,
                reference_take_profit=item.reference_take_profit,
                signal_atr30=item.signal_atr30,
            )
            watch_pool.pop(item.code, None)
            self.repository.insert_buy_order(
                task_id=task_id,
                run_no=run_no,
                trade_date=trade_date,
                code=item.code,
                code_name=item.code_name,
                buy_price=buy_price,
                quantity=quantity,
                amount=amount,
                fee=fee,
                cash_after=cash,
                signal=item.signal,
            )
        return cash

    def _add_new_signals_to_watch_pool(
        self,
        *,
        trade_date: date,
        trade_index: int,
        signals: list[dict[str, Any]],
        holdings: dict[str, HoldingItem],
        watch_pool: dict[str, WatchItem],
    ) -> None:
        for signal_item in signals:
            code = signal_item["code"]
            if code in holdings or code in watch_pool:
                continue
            signal = signal_item.get("signal") or {}
            watch_pool[code] = WatchItem(
                code=code,
                code_name=signal_item.get("code_name"),
                added_date=trade_date,
                added_trade_index=trade_index,
                min_stop_loss=signal.get("min_stop_loss"),
                reference_take_profit=signal.get("reference_take_profit"),
                signal_atr30=signal.get("signal_atr30"),
                ideal_buy_price=signal.get("ideal_buy_price"),
                max_watch_days=signal.get("max_watch_days"),
                signal=signal,
            )

    def _snapshot(
        self,
        *,
        task_id: int,
        run_no: int,
        trade_date: date,
        cash: float,
        holdings: dict[str, HoldingItem],
        watch_pool: dict[str, WatchItem],
        bar_map: dict[str, dict[str, Any]],
    ) -> None:
        market_value = 0.0
        for holding in holdings.values():
            bar = bar_map.get(holding.code)
            close_price = None if bar is None else bar.get("close")
            market_value += (float(close_price) if close_price is not None else holding.buy_price) * holding.quantity
        self.repository.insert_daily_snapshot(
            task_id=task_id,
            run_no=run_no,
            trade_date=trade_date,
            total_asset=cash + market_value,
            cash=cash,
            holding_market_value=market_value,
            holding_count=len(holdings),
            watch_count=len(watch_pool),
            holdings=[asdict(item) for item in holdings.values()],
            watch_items=[asdict(item) for item in watch_pool.values()],
        )

    def _watch_expired(self, item: WatchItem, trade_index: int) -> bool:
        if item.max_watch_days is None:
            return False
        return trade_index - item.added_trade_index > item.max_watch_days

    def _estimate_total_asset(
        self,
        *,
        cash: float,
        holdings: dict[str, HoldingItem],
        bar_map: dict[str, dict[str, Any]],
    ) -> float:
        market_value = 0.0
        for holding in holdings.values():
            bar = bar_map.get(holding.code)
            open_price = None if bar is None else bar.get("open")
            market_value += (float(open_price) if open_price is not None else holding.buy_price) * holding.quantity
        return cash + market_value

    def _resolve_buy_quantity(self, *, cash: float, total_asset: float, buy_price: float) -> int:
        if buy_price <= 0:
            return 0
        budget = min(cash, total_asset / 3)
        quantity = int(budget // (buy_price * 100)) * 100
        return max(quantity, 0)

    def _is_tradeable_bar(self, bar: dict[str, Any] | None) -> bool:
        if bar is None:
            return False
        values = [bar.get("open"), bar.get("high"), bar.get("low"), bar.get("close")]
        if any(value is None for value in values):
            return False
        if bar.get("volume") is not None and float(bar["volume"]) <= 0:
            return False
        if bar.get("tradestatus") is not None and int(bar["tradestatus"]) != 1:
            return False
        return True
