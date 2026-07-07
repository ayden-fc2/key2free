from __future__ import annotations

import math
import threading
import time
from bisect import bisect_left
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from app.entities.stock_data_context import StockDailyFrame
from app.dtos.backtest_dto import BacktestStartDTO, BacktestTaskDTO
from app.repositories.backtest_repository import BacktestRepository
from app.repositories.signal_repository import SignalRepository
from app.services.signal_service import SignalService
from app.services.signal_window import SIGNAL_WINDOW_BARS, TRADE_HISTORY_WINDOW_BARS
from app.services.strategy_registry import StrategyRegistration, get_strategy
from app.services.strategy_lifecycle import MarketViews, StrategyContext
from app.services.trading_periods import TradingPeriodClock, build_trading_clocks


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


class BacktestService:
    BUY_FEE_BPS = 5
    SELL_FEE_BPS = 5
    MIN_TRADE_FEE = 5.0
    DEFAULT_SIMULATION_RUNS = 50
    STRATEGY_DEFAULT_SIMULATION_RUNS = {
        "small_float_value": 1,
    }
    SIMULATION_WORKERS = 5

    def __init__(self) -> None:
        self.repository = BacktestRepository()

    def request_backtest(
        self,
        *,
        start_date: date,
        end_date: date,
        initial_cash: float,
        strategy_name: str,
        simulation_runs: int | None = None,
    ) -> BacktestStartDTO:
        if start_date > end_date:
            raise ValueError("start_date must be <= end_date")
        if initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if get_strategy(strategy_name) is None:
            raise ValueError(f"unknown strategy: {strategy_name}")
        requested_simulation_runs = simulation_runs
        resolved_simulation_runs = self._resolve_simulation_runs(
            strategy_name=strategy_name,
            simulation_runs=simulation_runs,
        )

        task = self.repository.create_task(
            strategy_name=strategy_name,
            start_date=start_date,
            end_date=end_date,
            initial_cash=float(initial_cash),
            simulation_runs=resolved_simulation_runs,
            initial_log=(
                f"创建回测任务: strategy={strategy_name}, "
                f"range={start_date.isoformat()}->{end_date.isoformat()}, "
                f"initial_cash={initial_cash:.2f}, "
                f"request_simulation_runs={requested_simulation_runs}, "
                f"simulation_runs={resolved_simulation_runs}"
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
                "simulation_runs": resolved_simulation_runs,
            },
            daemon=True,
        )
        thread.start()
        return BacktestStartDTO(task=task, message="backtest task created")

    def _resolve_simulation_runs(
        self,
        *,
        strategy_name: str,
        simulation_runs: int | None,
    ) -> int:
        if simulation_runs is None:
            return self.STRATEGY_DEFAULT_SIMULATION_RUNS.get(
                strategy_name,
                self.DEFAULT_SIMULATION_RUNS,
            )
        if (
            strategy_name in self.STRATEGY_DEFAULT_SIMULATION_RUNS
            and simulation_runs == self.DEFAULT_SIMULATION_RUNS
        ):
            return self.STRATEGY_DEFAULT_SIMULATION_RUNS[strategy_name]
        if simulation_runs < 1:
            raise ValueError("simulation_runs must be >= 1")
        if simulation_runs > 500:
            raise ValueError("simulation_runs must be <= 500")
        return int(simulation_runs)

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
        simulation_runs: int,
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
            index_history_wide = self.repository.load_index_history_wide(
                start_date=trading_dates[0],
                end_date=trading_dates[-1],
                window=SIGNAL_WINDOW_BARS,
            )
            history_frames = (
                SignalRepository().load_stock_frames(
                    codes=signal_codes,
                    start_date=trading_dates[0],
                    end_date=trading_dates[-1],
                    window=TRADE_HISTORY_WINDOW_BARS,
                    extra_columns=strategy.required_columns,
                )
                if strategy.lifecycle is not None
                else None
            )
            self.repository.append_task_log(
                task_id,
                f"行情装载完成: codes={len(signal_codes)}, 撮合主循环零 SQL",
            )

            self.repository.append_task_log(
                task_id,
                (
                    f"开始 {simulation_runs} 轮生命周期回测: "
                    f"workers={self.SIMULATION_WORKERS}"
                ),
            )
            final_assets_by_run: dict[int, float] = {}
            run_stats_by_run: dict[int, dict[str, int]] = {}
            max_workers = min(self.SIMULATION_WORKERS, simulation_runs)
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(
                        self._simulate,
                        task_id=task_id,
                        run_no=run_no,
                        trading_dates=trading_dates,
                        initial_cash=initial_cash,
                        strategy=strategy,
                        signals_by_date=signals_by_date,
                        prices=prices,
                        history_frames=history_frames,
                        index_history_wide=index_history_wide,
                    ): run_no
                    for run_no in range(1, simulation_runs + 1)
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
                        or completed_runs == simulation_runs
                    ):
                        self.repository.update_task_progress(
                            task_id=task_id,
                            completed_runs=completed_runs,
                        )
                        self.repository.append_task_log(
                            task_id,
                            (
                                f"生命周期回测完成 {completed_runs}/{simulation_runs}: "
                                f"run_no={run_no}, final_asset={final_asset:.2f}"
                            ),
                        )
            final_assets = [
                final_assets_by_run[run_no]
                for run_no in range(1, simulation_runs + 1)
            ]
            run_stats_list = [
                run_stats_by_run[run_no]
                for run_no in range(1, simulation_runs + 1)
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
                sharpe_ratio_avg=summary["sharpe_ratio_avg"],
                profit_loss_ratio_avg=summary["profit_loss_ratio_avg"],
                excess_return_avg=summary["excess_return_avg"],
                max_drawdown_avg=summary["max_drawdown_avg"],
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
        self.repository.append_task_log(task_id, f"开始按交易日预计算信号: {strategy_name}")
        self.repository.append_task_log(
            task_id,
            f"信号预计算配置: batch_workers={SignalService.SIGNAL_BATCH_WORKERS}",
        )
        daily_results = SignalService().get_signals_for_dates_by_stock(
            trade_dates=trading_dates,
            strategy_name=strategy_name,
            progress_callback=lambda done, total: self.repository.append_task_log(
                task_id,
                f"交易日信号预计算进度: {done}/{total}",
            ),
            progress_interval=100,
        )
        signals_by_date: dict[date, list[dict[str, Any]]] = {}
        signal_rows: list[list[Any]] = []
        total_signals = 0
        evaluated_signal_days = self._evaluated_signal_days(
            trading_dates=trading_dates,
            strategy_name=strategy_name,
        )
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
            f"信号预计算完成: days={len(evaluated_signal_days)}, signals={total_signals}",
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
        trading_dates: list[date],
        initial_cash: float,
        strategy: StrategyRegistration,
        signals_by_date: dict[date, list[dict[str, Any]]],
        prices: dict[str, dict[date, Bar]],
        history_frames: dict[str, StockDailyFrame] | None = None,
        index_history_wide: Any | None = None,
    ) -> tuple[float, dict[str, int]]:
        return self._simulate_lifecycle(
            task_id=task_id,
            run_no=run_no,
            trading_dates=trading_dates,
            initial_cash=initial_cash,
            strategy=strategy,
            signals_by_date=signals_by_date,
            prices=prices,
            history_frames=history_frames or {},
            index_history_wide=index_history_wide,
        )

    def _simulate_lifecycle(
        self,
        *,
        task_id: int,
        run_no: int,
        trading_dates: list[date],
        initial_cash: float,
        strategy: StrategyRegistration,
        signals_by_date: dict[date, list[dict[str, Any]]],
        prices: dict[str, dict[date, Bar]],
        history_frames: dict[str, StockDailyFrame] | None = None,
        index_history_wide: Any | None = None,
    ) -> tuple[float, dict[str, int]]:
        lifecycle = strategy.lifecycle
        if lifecycle is None:
            raise RuntimeError("strategy lifecycle is required")

        cash = initial_cash
        holdings: dict[str, HoldingItem] = {}
        watch_pool: dict[str, WatchItem] = {}
        buy_rows: list[list[Any]] = []
        sell_rows: list[list[Any]] = []
        snapshot_rows: list[list[Any]] = []
        run_stats = {"buys": 0, "closed": 0, "wins": 0}
        trade_records: dict[str, Any] = {"buys": buy_rows, "sells": sell_rows}
        total_asset = initial_cash
        trading_clocks = self._build_trading_clocks_for_dates(
            trading_dates=trading_dates,
            strategy=strategy,
        )
        for trade_index, trade_date in enumerate(trading_dates):
            strategy_params = self._strategy_params_for_date(
                strategy=strategy,
                trade_date=trade_date,
                trading_clocks=trading_clocks,
            )
            strategy_params["run_no"] = run_no
            market = self._build_market_views(
                prices=prices,
                trade_date=trade_date,
                previous_trade_date=trading_dates[trade_index - 1] if trade_index > 0 else None,
                history_frames=history_frames or {},
                index_history_wide=index_history_wide,
            )
            total_asset = self._mark_total_asset(
                cash=cash,
                holdings=holdings,
                prices=prices,
                trade_date=trade_date,
                prefer_open=True,
            )
            context = StrategyContext(
                trade_date=trade_date,
                trade_index=trade_index,
                cash=cash,
                total_asset=total_asset,
                holdings=holdings,
                watch_pool=watch_pool,
                trade_records=trade_records,
                params=strategy_params,
            )

            for decision in lifecycle.decide_sells(context=context, market=market):
                holding = holdings.get(decision.code)
                if holding is None:
                    continue
                if decision.price <= 0 or not math.isfinite(decision.price):
                    continue
                cash = self._sell_holding(
                    task_id=task_id,
                    run_no=run_no,
                    trade_date=trade_date,
                    cash=cash,
                    holdings=holdings,
                    code=decision.code,
                    holding=holding,
                    price=decision.price,
                    quantity=decision.quantity,
                    reason=decision.reason,
                    sell_rows=sell_rows,
                    run_stats=run_stats,
                )

            total_asset = self._mark_total_asset(
                cash=cash,
                holdings=holdings,
                prices=prices,
                trade_date=trade_date,
                prefer_open=True,
            )
            context = StrategyContext(
                trade_date=trade_date,
                trade_index=trade_index,
                cash=cash,
                total_asset=total_asset,
                holdings=holdings,
                watch_pool=watch_pool,
                trade_records=trade_records,
                params=strategy_params,
            )

            for decision in lifecycle.decide_buys(context=context, market=market):
                signal_for_order = self._with_buy_research_fields(
                    signal=decision.signal,
                    buy_price=decision.price,
                )
                if decision.code in holdings:
                    holding = holdings[decision.code]
                    quantity = decision.quantity
                    if quantity <= 0:
                        continue
                    amount = decision.price * quantity
                    fee = self._trade_fee(amount=amount, bps=self.BUY_FEE_BPS)
                    if amount + fee > cash:
                        continue
                    cash -= amount + fee
                    total_cost = holding.buy_price * holding.quantity + amount
                    holding.quantity += quantity
                    holding.buy_price = total_cost / holding.quantity
                    holding.buy_fee += fee
                    holding.signal = signal_for_order
                    holding.max_high_since_buy = max(
                        holding.max_high_since_buy,
                        self._initial_max_high_since_buy(
                            bar=market.today_bars.get(decision.code, (decision.price,) * 6),
                            buy_price=decision.price,
                        ),
                    )
                else:
                    if decision.quantity <= 0:
                        continue
                    amount = decision.price * decision.quantity
                    fee = self._trade_fee(amount=amount, bps=self.BUY_FEE_BPS)
                    if amount + fee > cash:
                        continue
                    cash -= amount + fee
                    holdings[decision.code] = HoldingItem(
                        code=decision.code,
                        code_name=decision.code_name,
                        buy_date=trade_date,
                        buy_trade_index=trade_index,
                        buy_price=decision.price,
                        quantity=decision.quantity,
                        buy_fee=fee,
                        level=0,
                        stop_losses=[],
                        take_profits=[],
                        max_high_since_buy=self._initial_max_high_since_buy(
                            bar=market.today_bars.get(decision.code, (decision.price,) * 6),
                            buy_price=decision.price,
                        ),
                        signal=signal_for_order,
                    )
                buy_rows.append(
                    [
                        task_id,
                        run_no,
                        trade_date,
                        decision.code,
                        decision.code_name,
                        decision.price,
                        decision.quantity,
                        decision.price * decision.quantity,
                        fee,
                        cash,
                        self.repository.to_json(signal_for_order),
                    ]
                )
                watch_pool.pop(decision.code, None)

            context = StrategyContext(
                trade_date=trade_date,
                trade_index=trade_index,
                cash=cash,
                total_asset=self._mark_total_asset(
                    cash=cash,
                    holdings=holdings,
                    prices=prices,
                    trade_date=trade_date,
                    prefer_open=False,
                ),
                holdings=holdings,
                watch_pool=watch_pool,
                trade_records=trade_records,
                params=strategy_params,
            )
            watch_decision = lifecycle.update_watch_pool(
                context=context,
                raw_signals=signals_by_date.get(trade_date, []),
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
                watch_pool[code] = WatchItem(
                    code=code,
                    code_name=signal_item.get("code_name"),
                    added_date=trade_date,
                    added_trade_index=trade_index,
                    signal_close=self._to_float(signal.get("signal_close")),
                    max_watch_days=signal.get("max_watch_days"),
                    signal=signal,
                )

            total_asset = self._mark_total_asset(
                cash=cash,
                holdings=holdings,
                prices=prices,
                trade_date=trade_date,
                prefer_open=False,
            )
            snapshot_rows.append(
                [
                    task_id,
                    run_no,
                    trade_date,
                    total_asset,
                    cash,
                    total_asset - cash,
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
        run_stats["sharpe_ratio"] = self._sharpe_ratio_from_assets(
            [float(row[3]) for row in snapshot_rows],
            initial_cash=initial_cash,
        )
        run_stats["max_drawdown"] = self._max_drawdown_from_assets(
            [float(row[3]) for row in snapshot_rows],
        )
        run_stats["profit_loss_ratio"] = self._profit_loss_ratio_from_sells(sell_rows)
        return total_asset, run_stats

    def _evaluated_signal_days(
        self,
        *,
        trading_dates: list[date],
        strategy_name: str,
    ) -> list[date]:
        strategy = get_strategy(strategy_name)
        if strategy is None or strategy.trading_clock_period is None:
            return trading_dates
        clocks = self._build_trading_clocks_for_dates(
            trading_dates=trading_dates,
            strategy=strategy,
        )
        return [
            trade_date
            for trade_date in trading_dates
            if (clock := clocks.get(trade_date)) is not None and strategy.is_signal_day(clock)
        ]

    def _build_trading_clocks_for_dates(
        self,
        *,
        trading_dates: list[date],
        strategy: StrategyRegistration,
    ) -> dict[date, TradingPeriodClock]:
        if not trading_dates or strategy.trading_clock_period is None:
            return {}
        open_dates = SignalRepository().get_open_trade_dates(
            start_date=trading_dates[0] - timedelta(days=10),
            end_date=trading_dates[-1] + timedelta(days=10),
        )
        return build_trading_clocks(
            open_dates,
            period=strategy.trading_clock_period,
        )

    def _strategy_params_for_date(
        self,
        *,
        strategy: StrategyRegistration,
        trade_date: date,
        trading_clocks: dict[date, TradingPeriodClock],
    ) -> dict[str, Any]:
        clock = trading_clocks.get(trade_date)
        if clock is None:
            return {}
        return {
            "trading_clock": clock.to_params(),
            "is_rebalance_period_start": strategy.is_rebalance_day(clock),
            "is_signal_period_end": strategy.is_signal_day(clock),
        }

    def _sell_holding(
        self,
        *,
        task_id: int,
        run_no: int,
        trade_date: date,
        cash: float,
        holdings: dict[str, HoldingItem],
        code: str,
        holding: HoldingItem,
        price: float,
        quantity: int,
        reason: str,
        sell_rows: list[list[Any]],
        run_stats: dict[str, int],
    ) -> float:
        if holding.buy_date >= trade_date:
            return cash
        sell_quantity = min(quantity, holding.quantity)
        if sell_quantity <= 0:
            return cash
        amount = price * sell_quantity
        fee = self._trade_fee(amount=amount, bps=self.SELL_FEE_BPS)
        cash += amount - fee
        portion = sell_quantity / holding.quantity
        buy_fee_part = holding.buy_fee * portion
        pnl = (price - holding.buy_price) * sell_quantity - buy_fee_part - fee
        sell_rows.append(
            [
                task_id,
                run_no,
                trade_date,
                code,
                holding.code_name,
                price,
                sell_quantity,
                amount,
                fee,
                cash,
                holding.buy_date,
                holding.buy_price,
                pnl,
                reason,
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
        return cash

    def _trade_fee(self, *, amount: float, bps: float) -> float:
        if amount <= 0 or not math.isfinite(amount):
            return 0.0
        return max(amount * bps / 10000, self.MIN_TRADE_FEE)

    def _build_market_views(
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

    def _mark_total_asset(
        self,
        *,
        cash: float,
        holdings: dict[str, HoldingItem],
        prices: dict[str, dict[date, Bar]],
        trade_date: date,
        prefer_open: bool,
    ) -> float:
        market_value = 0.0
        for holding in holdings.values():
            bar = prices.get(holding.code, {}).get(trade_date)
            if prefer_open:
                price = self._bar_open(bar)
            else:
                price = self._bar_close(bar)
            market_value += (price if price is not None else holding.buy_price) * holding.quantity
        return cash + market_value

    def _with_buy_research_fields(
        self,
        *,
        signal: dict[str, Any],
        buy_price: float,
    ) -> dict[str, Any]:
        """Attach post-fill research fields without affecting signal generation."""
        copied = dict(signal)
        extras = dict(copied.get("extras") or {})
        signal_close = self._to_float(copied.get("signal_close"))
        if signal_close is not None and signal_close > 0 and math.isfinite(buy_price):
            extras["open_t1_to_close_t"] = buy_price / signal_close - 1.0
        copied["extras"] = extras
        return copied

    def _summarize_runs(
        self,
        *,
        start_date: date,
        end_date: date,
        initial_cash: float,
        final_assets: list[float],
        run_stats_list: list[dict[str, int]],
    ) -> dict[str, float | None]:
        """Aggregate portfolio and trade metrics across simulation runs."""
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
        sharpe_ratios = [
            value
            for stats in run_stats_list
            for value in [self._to_float(stats.get("sharpe_ratio"))]
            if value is not None
        ]
        profit_loss_ratios = [
            value
            for stats in run_stats_list
            for value in [self._to_float(stats.get("profit_loss_ratio"))]
            if value is not None
        ]
        max_drawdowns = [
            value
            for stats in run_stats_list
            for value in [self._to_float(stats.get("max_drawdown"))]
            if value is not None
        ]
        return {
            "annualized_return_avg": (
                sum(annualized_values) / len(annualized_values) if annualized_values else None
            ),
            "trades_per_year_avg": (
                sum(trades_per_year) / len(trades_per_year) if trades_per_year else None
            ),
            "win_rate_avg": sum(win_rates) / len(win_rates) if win_rates else None,
            "sharpe_ratio_avg": (
                sum(sharpe_ratios) / len(sharpe_ratios) if sharpe_ratios else None
            ),
            "profit_loss_ratio_avg": (
                sum(profit_loss_ratios) / len(profit_loss_ratios)
                if profit_loss_ratios
                else None
            ),
            "excess_return_avg": None,
            "max_drawdown_avg": (
                sum(max_drawdowns) / len(max_drawdowns) if max_drawdowns else None
            ),
        }

    def _sharpe_ratio_from_assets(
        self,
        assets: list[float],
        *,
        initial_cash: float,
    ) -> float | None:
        if initial_cash <= 0 or not assets:
            return None
        values = [initial_cash, *assets]
        returns = [
            values[index] / values[index - 1] - 1.0
            for index in range(1, len(values))
            if values[index - 1] > 0 and values[index] > 0
        ]
        if len(returns) < 2:
            return None
        mean_return = sum(returns) / len(returns)
        variance = sum((value - mean_return) ** 2 for value in returns) / (len(returns) - 1)
        std_dev = math.sqrt(variance)
        if std_dev <= 0:
            return None
        return mean_return / std_dev * math.sqrt(252)

    def _max_drawdown_from_assets(self, assets: list[float]) -> float | None:
        peak: float | None = None
        max_drawdown = 0.0
        for asset in assets:
            if asset <= 0 or not math.isfinite(asset):
                continue
            if peak is None or asset > peak:
                peak = asset
            if peak and peak > 0:
                max_drawdown = max(max_drawdown, 1.0 - asset / peak)
        return max_drawdown if peak is not None else None

    def _profit_loss_ratio_from_sells(self, sell_rows: list[list[Any]]) -> float | None:
        profits: list[float] = []
        losses: list[float] = []
        for row in sell_rows:
            pnl = self._to_float(row[12] if len(row) > 12 else None)
            if pnl is None:
                continue
            if pnl > 0:
                profits.append(pnl)
            elif pnl < 0:
                losses.append(abs(pnl))
        if not profits or not losses:
            return None
        return (sum(profits) / len(profits)) / (sum(losses) / len(losses))

    def _initial_max_high_since_buy(self, *, bar: Bar, buy_price: float) -> float:
        high = bar[1]
        if math.isfinite(high):
            return max(high, buy_price)
        return buy_price

    def _previous_bar(
        self,
        code_prices: dict[date, Bar],
        trade_date: date,
    ) -> Bar | None:
        previous_bar = None
        previous_trade_date = None
        for candidate_date, candidate_bar in code_prices.items():
            if candidate_date < trade_date and (
                previous_trade_date is None or candidate_date > previous_trade_date
            ):
                previous_trade_date = candidate_date
                previous_bar = candidate_bar
        return previous_bar

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
