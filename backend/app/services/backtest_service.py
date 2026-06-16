from __future__ import annotations

import math
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.dtos.backtest_dto import BacktestStartDTO, BacktestTaskDTO
from app.repositories.backtest_repository import BacktestRepository
from app.services.signal_service import SignalService
from app.services.strategy_registry import StrategyRegistration, get_strategy


Bar = tuple[float, ...]
"""(qfq_open, qfq_high, qfq_low, qfq_close, vol, pct_chg)，缺失为 nan。"""


@dataclass
class WatchItem:
    code: str
    code_name: str | None
    added_date: date
    added_trade_index: int
    signal_close: float | None
    max_watch_days: int | None
    signal: dict[str, Any]


@dataclass
class HoldingItem:
    code: str
    code_name: str | None
    buy_date: date
    buy_trade_index: int
    buy_price: float
    quantity: int
    buy_fee: float
    level: int
    stop_losses: list[float]
    take_profits: list[float]
    max_high_since_buy: float
    signal: dict[str, Any] = field(default_factory=dict)
    realized_pnl: float = 0.0

    def to_snapshot(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "code_name": self.code_name,
            "buy_date": self.buy_date.isoformat(),
            "buy_price": self.buy_price,
            "quantity": self.quantity,
            "level": self.level,
            "stop_losses": self.stop_losses,
            "take_profits": self.take_profits,
            "max_high_since_buy": self.max_high_since_buy,
        }


@dataclass(frozen=True)
class SellAction:
    reason: str  # stop_loss / take_profit_partial / take_profit_final
    price: float
    quantity: int
    advance_level: bool


class BacktestService:
    BUY_FEE_BPS = 5
    SELL_FEE_BPS = 10
    SIMULATION_RUNS = 50
    SIMULATION_WORKERS = 10

    def __init__(self) -> None:
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

        task = self.repository.create_task(
            strategy_name=strategy_name,
            start_date=start_date,
            end_date=end_date,
            initial_cash=float(initial_cash),
            simulation_runs=self.SIMULATION_RUNS,
            initial_log=(
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

    def get_backtest_task(self, task_id: int | None = None) -> BacktestTaskDTO | None:
        if task_id is None:
            return self.repository.get_latest_task()
        return self.repository.get_task(task_id)

    def list_backtest_tasks(
        self,
        limit: int = 100,
        *,
        latest_per_strategy: bool = True,
    ) -> list[BacktestTaskDTO]:
        return self.repository.list_tasks(limit=limit, latest_per_strategy=latest_per_strategy)

    # ------------------------------------------------------------------
    # 任务流程：预计算信号（一次） → 行情装载（一次） → 50 轮纯内存撮合
    # ------------------------------------------------------------------

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
            started_at = time.monotonic()
            self.repository.ensure_tables()
            self.repository.clear_task_rows(task_id)
            trading_dates = self.repository.get_trading_dates(
                start_date=start_date,
                end_date=end_date,
            )
            if not trading_dates:
                raise RuntimeError("no trading dates in backtest range")
            self.repository.update_task_progress(
                task_id=task_id,
                trading_day_count=len(trading_dates),
            )
            self.repository.append_task_log(task_id, f"交易日数量: {len(trading_dates)}")

            strategy = get_strategy(strategy_name)
            if strategy is None:
                raise RuntimeError(f"unknown strategy: {strategy_name}")

            signals_by_date = self._precompute_signals(
                task_id=task_id,
                trading_dates=trading_dates,
                strategy_name=strategy_name,
            )
            signal_codes = sorted(
                {
                    item["code"]
                    for signals in signals_by_date.values()
                    for item in signals
                }
            )
            prices = self.repository.load_price_data(
                codes=signal_codes,
                start_date=trading_dates[0],
                end_date=trading_dates[-1],
            )
            self.repository.append_task_log(
                task_id,
                f"行情装载完成: codes={len(signal_codes)}, 撮合主循环零 SQL",
            )

            random_seed = time.time_ns()
            self.repository.append_task_log(
                task_id,
                (
                    f"开始 {self.SIMULATION_RUNS} 轮随机撮合: "
                    f"seed={random_seed}, workers={self.SIMULATION_WORKERS}"
                ),
            )
            final_assets_by_run: dict[int, float] = {}
            run_stats_by_run: dict[int, dict[str, int]] = {}
            max_workers = min(self.SIMULATION_WORKERS, self.SIMULATION_RUNS)
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(
                        self._simulate,
                        task_id=task_id,
                        run_no=run_no,
                        random_seed=random_seed,
                        trading_dates=trading_dates,
                        initial_cash=initial_cash,
                        strategy=strategy,
                        signals_by_date=signals_by_date,
                        prices=prices,
                    ): run_no
                    for run_no in range(1, self.SIMULATION_RUNS + 1)
                }
                completed_runs = 0
                for future in as_completed(futures):
                    run_no = futures[future]
                    final_asset, run_stats = future.result()
                    final_assets_by_run[run_no] = final_asset
                    run_stats_by_run[run_no] = run_stats
                    completed_runs += 1
                    if (
                        completed_runs == 1
                        or completed_runs % 10 == 0
                        or completed_runs == self.SIMULATION_RUNS
                    ):
                        self.repository.update_task_progress(
                            task_id=task_id,
                            completed_runs=completed_runs,
                        )
                        self.repository.append_task_log(
                            task_id,
                            (
                                f"随机撮合完成 {completed_runs}/{self.SIMULATION_RUNS}: "
                                f"run_no={run_no}, final_asset={final_asset:.2f}"
                            ),
                        )
            final_assets = [
                final_assets_by_run[run_no]
                for run_no in range(1, self.SIMULATION_RUNS + 1)
            ]
            run_stats_list = [
                run_stats_by_run[run_no]
                for run_no in range(1, self.SIMULATION_RUNS + 1)
            ]
            summary = self._summarize_runs(
                start_date=start_date,
                end_date=end_date,
                initial_cash=initial_cash,
                final_assets=final_assets,
                run_stats_list=run_stats_list,
            )
            elapsed = time.monotonic() - started_at
            self.repository.finish_task(
                task_id=task_id,
                status="success",
                message=f"回测完成，总耗时 {elapsed:.1f} 秒。",
                completed_runs=len(final_assets),
                final_assets=final_assets,
                initial_cash=initial_cash,
                annualized_return_avg=summary["annualized_return_avg"],
                trades_per_year_avg=summary["trades_per_year_avg"],
                win_rate_avg=summary["win_rate_avg"],
            )
        except Exception as exc:
            self.repository.finish_task(
                task_id=task_id,
                status="error",
                message=f"回测失败: {exc}",
            )

    def _precompute_signals(
        self,
        *,
        task_id: int,
        trading_dates: list[date],
        strategy_name: str,
    ) -> dict[date, list[dict[str, Any]]]:
        self.repository.append_task_log(task_id, f"开始按股票维度预计算信号: {strategy_name}")
        daily_results = SignalService().get_signals_for_dates_by_stock(
            trade_dates=trading_dates,
            strategy_name=strategy_name,
            progress_callback=lambda done, total: self.repository.append_task_log(
                task_id,
                f"股票维度信号预计算进度: {done}/{total}",
            ),
            progress_interval=100,
        )
        signals_by_date: dict[date, list[dict[str, Any]]] = {}
        signal_rows: list[list[Any]] = []
        total_signals = 0
        for day in trading_dates:
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
            total_signals += len(signals)
            for item in signals:
                signal_rows.append(
                    [
                        task_id,
                        day,
                        strategy_name,
                        item["code"],
                        item.get("code_name"),
                        self.repository.to_json(item.get("universe") or {}),
                        self.repository.to_json(item.get("signal") or {}),
                    ]
                )
        self.repository.insert_signal_rows(signal_rows)
        self.repository.update_task_progress(task_id=task_id, signal_count=total_signals)
        self.repository.append_task_log(
            task_id,
            f"信号预计算完成: days={len(trading_dates)}, signals={total_signals}",
        )
        return signals_by_date

    # ------------------------------------------------------------------
    # 单轮撮合（纯内存）
    # ------------------------------------------------------------------

    def _simulate(
        self,
        *,
        task_id: int,
        run_no: int,
        random_seed: int,
        trading_dates: list[date],
        initial_cash: float,
        strategy: StrategyRegistration,
        signals_by_date: dict[date, list[dict[str, Any]]],
        prices: dict[str, dict[date, Bar]],
    ) -> tuple[float, dict[str, int]]:
        cash = initial_cash
        holdings: dict[str, HoldingItem] = {}
        watch_pool: dict[str, WatchItem] = {}
        buy_rows: list[list[Any]] = []
        sell_rows: list[list[Any]] = []
        snapshot_rows: list[list[Any]] = []
        total_asset = initial_cash
        run_stats = {"buys": 0, "closed": 0, "wins": 0}

        for trade_index, trade_date in enumerate(trading_dates):
            # 1. 处理持仓池（跳过当日刚买入的，先止损后止盈的阶梯引擎）
            cash = self._process_sells(
                task_id=task_id,
                run_no=run_no,
                trade_date=trade_date,
                trade_index=trade_index,
                cash=cash,
                holdings=holdings,
                prices=prices,
                strategy=strategy,
                sell_rows=sell_rows,
                run_stats=run_stats,
            )
            # 2. 处理观望池（跳过当日刚加入的，signal_close 限价买入）
            cash = self._process_watches(
                task_id=task_id,
                run_no=run_no,
                random_seed=random_seed,
                trade_date=trade_date,
                trade_index=trade_index,
                cash=cash,
                holdings=holdings,
                watch_pool=watch_pool,
                prices=prices,
                strategy=strategy,
                buy_rows=buy_rows,
            )
            # 3. 当日新信号加入观望池（不允许当天买入）
            for signal_item in signals_by_date.get(trade_date, []):
                code = signal_item["code"]
                if code in holdings or code in watch_pool:
                    continue
                signal = signal_item.get("signal") or {}
                watch_pool[code] = WatchItem(
                    code=code,
                    code_name=signal_item.get("code_name"),
                    added_date=trade_date,
                    added_trade_index=trade_index,
                    signal_close=self._to_float(signal.get("signal_close")),
                    max_watch_days=signal.get("max_watch_days"),
                    signal=signal,
                )
            # 4. 每日快照（收盘价估值，内存累积）
            market_value = 0.0
            for holding in holdings.values():
                close_price = self._bar_close(prices.get(holding.code, {}).get(trade_date))
                price = close_price if close_price is not None else holding.buy_price
                market_value += price * holding.quantity
            total_asset = cash + market_value
            snapshot_rows.append(
                [
                    task_id,
                    run_no,
                    trade_date,
                    total_asset,
                    cash,
                    market_value,
                    len(holdings),
                    len(watch_pool),
                    self.repository.to_json([item.to_snapshot() for item in holdings.values()]),
                    self.repository.to_json(
                        [
                            {
                                "code": item.code,
                                "code_name": item.code_name,
                                "added_date": item.added_date.isoformat(),
                                "signal_close": item.signal_close,
                                "max_watch_days": item.max_watch_days,
                            }
                            for item in watch_pool.values()
                        ]
                    ),
                ]
            )

        self.repository.insert_buy_orders(buy_rows)
        self.repository.insert_sell_orders(sell_rows)
        self.repository.insert_daily_snapshots(snapshot_rows)
        run_stats["buys"] = len(buy_rows)
        return total_asset, run_stats

    def _process_sells(
        self,
        *,
        task_id: int,
        run_no: int,
        trade_date: date,
        trade_index: int,
        cash: float,
        holdings: dict[str, HoldingItem],
        prices: dict[str, dict[date, Bar]],
        strategy: StrategyRegistration,
        sell_rows: list[list[Any]],
        run_stats: dict[str, int],
    ) -> float:
        for code, holding in list(holdings.items()):
            if holding.buy_date >= trade_date:
                continue
            bar = prices.get(code, {}).get(trade_date)
            if not self._is_tradeable(bar):
                continue
            if strategy.exit_strategy is not None:
                actions = [
                    self._call_exit_strategy(
                        strategy=strategy,
                        bar=bar,
                        holding=holding,
                        trade_index=trade_index,
                    )
                ]
            else:
                actions = self._ladder_exit_actions(
                    bar=bar,
                    holding=holding,
                    trade_index=trade_index,
                    max_holding_days=strategy.max_holding_days,
                    time_exit_price=strategy.time_exit_price,
                )
            for action in actions:
                if action is None or code not in holdings:
                    continue
                sell_quantity = min(action.quantity, holding.quantity)
                if sell_quantity <= 0:
                    continue
                amount = action.price * sell_quantity
                fee = amount * self.SELL_FEE_BPS / 10000
                cash += amount - fee
                portion = sell_quantity / holding.quantity
                buy_fee_part = holding.buy_fee * portion
                pnl = (action.price - holding.buy_price) * sell_quantity - buy_fee_part - fee
                sell_rows.append(
                    [
                        task_id,
                        run_no,
                        trade_date,
                        code,
                        holding.code_name,
                        action.price,
                        sell_quantity,
                        amount,
                        fee,
                        cash,
                        holding.buy_date,
                        holding.buy_price,
                        pnl,
                        action.reason,
                        holding.level,
                    ]
                )
                holding.realized_pnl += pnl
                if sell_quantity >= holding.quantity:
                    run_stats["closed"] += 1
                    if holding.realized_pnl > 0:
                        run_stats["wins"] += 1
                    del holdings[code]
                else:
                    holding.quantity -= sell_quantity
                    holding.buy_fee -= buy_fee_part
                    if action.advance_level:
                        holding.level += 1
        return cash

    def _call_exit_strategy(
        self,
        *,
        strategy: StrategyRegistration,
        bar: Bar,
        holding: HoldingItem,
        trade_index: int,
    ) -> Any:
        if strategy.exit_strategy is None:
            return None
        try:
            return strategy.exit_strategy(
                bar=bar,
                holding=holding,
                trade_index=trade_index,
            )
        except TypeError as exc:
            if "trade_index" not in str(exc):
                raise
            return strategy.exit_strategy(bar=bar, holding=holding)

    def _ladder_exit_actions(
        self,
        *,
        bar: Bar,
        holding: HoldingItem,
        trade_index: int,
        max_holding_days: int | None,
        time_exit_price: str = "close",
    ) -> list[SellAction]:
        """Generic ladder exit engine for take profit, stop loss, and time stops."""
        open_price, high, _low, close, _vol, _pct = bar[:6]
        actions: list[SellAction] = []
        level = holding.level
        remaining = holding.quantity
        if math.isfinite(high):
            holding.max_high_since_buy = max(holding.max_high_since_buy, high)

        take = holding.take_profits[level] if level < len(holding.take_profits) else None
        if take is not None and math.isfinite(take) and (open_price >= take or high >= take):
            price = open_price if open_price >= take else take
            is_last_level = level >= len(holding.take_profits) - 1
            half = math.ceil(remaining / 2 / 100) * 100
            if is_last_level or half >= remaining:
                return [SellAction("take_profit_final", price, remaining, False)]
            actions.append(SellAction("take_profit_partial", price, half, True))
            remaining -= half
            level += 1

        stop = holding.stop_losses[level] if level < len(holding.stop_losses) else None
        if stop is not None and math.isfinite(stop) and close <= stop:
            actions.append(SellAction("stop_loss", close, remaining, False))
            return actions

        failed_start_days = self._positive_int(self._signal_value(holding.signal, "failed_start_days"))
        failed_start_close_return_ratio = self._to_float(
            self._signal_value(holding.signal, "failed_start_close_return_ratio")
        )
        if (
            failed_start_days is not None
            and failed_start_close_return_ratio is not None
            and failed_start_close_return_ratio > 0
            and trade_index - holding.buy_trade_index >= failed_start_days - 1
            and math.isfinite(close)
            and close < holding.buy_price * failed_start_close_return_ratio
        ):
            actions.append(SellAction("failed_start_time_stop", close, remaining, False))
            return actions

        failed_start_return_ratio = self._to_float(
            self._signal_value(holding.signal, "failed_start_return_ratio")
        )
        if (
            failed_start_days is not None
            and failed_start_return_ratio is not None
            and failed_start_return_ratio > 0
            and trade_index - holding.buy_trade_index >= failed_start_days - 1
            and holding.max_high_since_buy < holding.buy_price * failed_start_return_ratio
        ):
            actions.append(SellAction("failed_start_time_stop", close, remaining, False))
            return actions

        if (
            max_holding_days is not None
            and trade_index - holding.buy_trade_index >= max_holding_days
        ):
            price = open_price if time_exit_price == "open" else close
            actions.append(SellAction(f"time_stop_{time_exit_price}", price, remaining, False))
        return actions

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
        prices: dict[str, dict[date, Bar]],
        strategy: StrategyRegistration,
        buy_rows: list[list[Any]],
    ) -> float:
        items = list(watch_pool.values())
        random.Random(f"{random_seed}:{run_no}:{trade_date.isoformat()}").shuffle(items)
        for item in items:
            if item.added_date >= trade_date:
                continue
            # 超过最长观望时长（T+1、T+2 之外）直接移出，不再尝试买入
            if (
                item.max_watch_days is not None
                and trade_index - item.added_trade_index > item.max_watch_days
            ):
                watch_pool.pop(item.code, None)
                continue
            bar = prices.get(item.code, {}).get(trade_date)
            if not self._is_tradeable(bar):
                continue
            if strategy.entry_strategy is not None:
                buy_price = strategy.entry_strategy(bar=bar, watch=item)
            elif strategy.entry_mode == "next_open":
                buy_price = bar[0]  # 次日开盘市价买入
            else:
                buy_price = self._default_entry(bar=bar, watch=item)
            if buy_price is None or buy_price <= 0 or not math.isfinite(buy_price):
                continue
            # 成交时落定止损/止盈价位（依赖成交价的策略由 exit_plan_builder 填充）
            if strategy.exit_plan_builder is not None:
                exit_plan = strategy.exit_plan_builder(buy_price, item.signal)
                if exit_plan is None:
                    continue
                stop_losses, take_profits = exit_plan
            else:
                stop_losses = [
                    float(value)
                    for value in (item.signal.get("stop_losses") or [])
                    if isinstance(value, (int, float))
                ]
                take_profits = [
                    float(value)
                    for value in (item.signal.get("take_profits") or [])
                    if isinstance(value, (int, float))
                ]
            total_asset = cash
            for holding in holdings.values():
                open_price = self._bar_open(prices.get(holding.code, {}).get(trade_date))
                price = open_price if open_price is not None else holding.buy_price
                total_asset += price * holding.quantity
            if strategy.position_sizing == "fraction":
                quantity = self._resolve_fraction_quantity(
                    cash=cash,
                    total_asset=total_asset,
                    buy_price=buy_price,
                    fraction=strategy.position_fraction,
                )
            elif strategy.position_sizing == "fixed_amount":
                quantity = self._resolve_fixed_amount_quantity(
                    cash=cash,
                    buy_price=buy_price,
                    amount=strategy.position_amount,
                )
            else:
                risk_price = (
                    item.signal_close
                    if strategy.risk_price_basis == "signal_close"
                    else buy_price
                )
                quantity = self._resolve_buy_quantity(
                    cash=cash,
                    total_asset=total_asset,
                    buy_price=buy_price,
                    risk_price=risk_price,
                    first_stop=stop_losses[0] if stop_losses else None,
                    risk_per_trade=strategy.risk_per_trade,
                    position_cap_fraction=strategy.position_cap_fraction,
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
                buy_trade_index=trade_index,
                buy_price=buy_price,
                quantity=quantity,
                buy_fee=fee,
                level=0,
                stop_losses=[float(value) for value in stop_losses],
                take_profits=[float(value) for value in take_profits],
                max_high_since_buy=self._initial_max_high_since_buy(bar=bar, buy_price=buy_price),
                signal=item.signal,
            )
            watch_pool.pop(item.code, None)
            buy_rows.append(
                [
                    task_id,
                    run_no,
                    trade_date,
                    item.code,
                    item.code_name,
                    buy_price,
                    quantity,
                    amount,
                    fee,
                    cash,
                    self.repository.to_json(item.signal),
                ]
            )
        return cash

    def _summarize_runs(
        self,
        *,
        start_date: date,
        end_date: date,
        initial_cash: float,
        final_assets: list[float],
        run_stats_list: list[dict[str, int]],
    ) -> dict[str, float | None]:
        """跨轮平均的年化收益率、年均交易次数、胜率（按已平仓持仓计）。"""
        years = max((end_date - start_date).days, 1) / 365.25
        annualized_values = [
            (final / initial_cash) ** (1.0 / years) - 1.0
            for final in final_assets
            if final > 0 and initial_cash > 0
        ]
        win_rates = [
            stats["wins"] / stats["closed"]
            for stats in run_stats_list
            if stats["closed"] > 0
        ]
        trades_per_year = [stats["buys"] / years for stats in run_stats_list]
        return {
            "annualized_return_avg": (
                sum(annualized_values) / len(annualized_values) if annualized_values else None
            ),
            "trades_per_year_avg": (
                sum(trades_per_year) / len(trades_per_year) if trades_per_year else None
            ),
            "win_rate_avg": sum(win_rates) / len(win_rates) if win_rates else None,
        }

    def _resolve_buy_quantity(
        self,
        *,
        cash: float,
        total_asset: float,
        buy_price: float,
        risk_price: float | None,
        first_stop: float | None,
        risk_per_trade: float,
        position_cap_fraction: float | None,
    ) -> int:
        """风险敞口定仓：最坏止损亏损 <= 总资产 * risk_per_trade，取最大百股仓位。

        - 没有第一止损位、或买入价已不高于止损位（风险无法界定）时不买。
        - 可选叠加单笔市值上限 position_cap_fraction。
        - 同时受可用现金约束（含买入手续费）。
        """
        if buy_price <= 0 or risk_price is None or first_stop is None:
            return 0
        risk_per_share = risk_price - first_stop
        if risk_per_share <= 0:
            return 0
        max_risk_amount = total_asset * risk_per_trade
        lots_by_risk = int(max_risk_amount // (risk_per_share * 100))
        cost_per_lot = buy_price * 100 * (1 + self.BUY_FEE_BPS / 10000)
        lots_by_cash = int(cash // cost_per_lot)
        lot_limits = [lots_by_risk, lots_by_cash]
        if position_cap_fraction is not None:
            if position_cap_fraction <= 0:
                return 0
            lots_by_cap = int((total_asset * position_cap_fraction) // (buy_price * 100))
            lot_limits.append(lots_by_cap)
        return max(min(lot_limits), 0) * 100

    def _resolve_fraction_quantity(
        self,
        *,
        cash: float,
        total_asset: float,
        buy_price: float,
        fraction: float,
    ) -> int:
        """固定比例定仓：单笔股票市值 <= 总资产 * fraction，受可用现金（含手续费）约束。"""
        if buy_price <= 0 or fraction <= 0:
            return 0
        budget = total_asset * fraction
        cost_per_lot = buy_price * 100 * (1 + self.BUY_FEE_BPS / 10000)
        lots_by_budget = int(budget // (buy_price * 100))
        lots_by_cash = int(cash // cost_per_lot)
        return max(min(lots_by_budget, lots_by_cash), 0) * 100

    def _resolve_fixed_amount_quantity(
        self,
        *,
        cash: float,
        buy_price: float,
        amount: float | None,
    ) -> int:
        """固定金额定仓：单笔市值 <= amount，按 100 股一手尽可能多买。"""
        if buy_price <= 0 or amount is None or amount <= 0:
            return 0
        cost_per_lot = buy_price * 100 * (1 + self.BUY_FEE_BPS / 10000)
        lots_by_amount = int(amount // (buy_price * 100))
        lots_by_cash = int(cash // cost_per_lot)
        return max(min(lots_by_amount, lots_by_cash), 0) * 100

    def _initial_max_high_since_buy(self, *, bar: Bar, buy_price: float) -> float:
        high = bar[1]
        if math.isfinite(high):
            return max(high, buy_price)
        return buy_price

    def _default_entry(self, *, bar: Bar, watch: WatchItem) -> float | None:
        """框架默认入场：以 signal_close 为限价买单。

        开盘价 <= signal_close 时按开盘价成交（低开买得更便宜）；
        否则盘中触及 signal_close（low <= signal_close）按 signal_close 成交。
        """
        signal_close = watch.signal_close
        if signal_close is None or signal_close <= 0:
            return None
        open_price, _high, low, _close, _vol, _pct = bar[:6]
        if open_price <= signal_close:
            return open_price
        if low <= signal_close:
            return signal_close
        return None

    def _is_tradeable(self, bar: Bar | None) -> bool:
        """撮合边界：停牌（无行情/零量）与一字板（open==high==low==close）不可交易。"""
        if bar is None:
            return False
        open_price, high, low, close, vol, _pct = bar[:6]
        if not (
            math.isfinite(open_price)
            and math.isfinite(high)
            and math.isfinite(low)
            and math.isfinite(close)
        ):
            return False
        if not math.isfinite(vol) or vol <= 0:
            return False
        if open_price == high == low == close:
            return False
        return True

    def _bar_open(self, bar: Bar | None) -> float | None:
        if bar is None or not math.isfinite(bar[0]):
            return None
        return bar[0]

    def _bar_close(self, bar: Bar | None) -> float | None:
        if bar is None or not math.isfinite(bar[3]):
            return None
        return bar[3]

    def _to_float(self, value: Any) -> float | None:
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            return float(value)
        return None

    def _signal_value(self, signal: dict[str, Any], key: str) -> Any:
        if key in signal:
            return signal[key]
        extras = signal.get("extras")
        if isinstance(extras, dict):
            return extras.get(key)
        return None

    def _positive_int(self, value: Any) -> int | None:
        if isinstance(value, int) and value > 0:
            return value
        if isinstance(value, float) and value.is_integer() and value > 0:
            return int(value)
        return None
