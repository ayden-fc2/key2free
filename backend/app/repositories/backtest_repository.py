from __future__ import annotations

import json
import math
from datetime import date, datetime
from typing import Any

from app.dtos.backtest_dto import BacktestTaskDTO
from app.repositories.duckdb_repository import DuckDBRepository


class BacktestRepository:
    MAX_LOG_LINES = 2000

    def __init__(self) -> None:
        self.duckdb = DuckDBRepository()

    def ensure_tables(self) -> None:
        with self.duckdb.connect(read_only=False) as connection:
            connection.execute("create schema if not exists meta")
            connection.execute("create sequence if not exists meta.backtest_task_id_seq")
            connection.execute(
                """
                create table if not exists meta.backtest_task (
                    id bigint primary key default nextval('meta.backtest_task_id_seq'),
                    status varchar not null,
                    strategy_name varchar not null,
                    start_date date not null,
                    end_date date not null,
                    initial_cash double not null,
                    simulation_runs bigint not null,
                    completed_runs bigint not null default 0,
                    trading_day_count bigint,
                    signal_count bigint,
                    final_asset_avg double,
                    final_asset_min double,
                    final_asset_max double,
                    final_return_avg double,
                    final_return_min double,
                    final_return_max double,
                    started_at timestamp,
                    finished_at timestamp,
                    created_at timestamp not null default current_timestamp,
                    updated_at timestamp not null default current_timestamp,
                    logs varchar not null default '',
                    annualized_return_avg double,
                    trades_per_year_avg double,
                    win_rate_avg double,
                    sharpe_ratio_avg double,
                    profit_loss_ratio_avg double,
                    excess_return_avg double,
                    max_drawdown_avg double
                )
                """
            )
            for statement in (
                "alter table meta.backtest_task add column if not exists completed_runs bigint default 0",
                "alter table meta.backtest_task add column if not exists trading_day_count bigint",
                "alter table meta.backtest_task add column if not exists signal_count bigint",
                "alter table meta.backtest_task add column if not exists final_asset_avg double",
                "alter table meta.backtest_task add column if not exists final_asset_min double",
                "alter table meta.backtest_task add column if not exists final_asset_max double",
                "alter table meta.backtest_task add column if not exists final_return_avg double",
                "alter table meta.backtest_task add column if not exists final_return_min double",
                "alter table meta.backtest_task add column if not exists final_return_max double",
                "alter table meta.backtest_task add column if not exists started_at timestamp",
                "alter table meta.backtest_task add column if not exists finished_at timestamp",
                "alter table meta.backtest_task add column if not exists logs varchar default ''",
                "alter table meta.backtest_task add column if not exists annualized_return_avg double",
                "alter table meta.backtest_task add column if not exists trades_per_year_avg double",
                "alter table meta.backtest_task add column if not exists win_rate_avg double",
                "alter table meta.backtest_task add column if not exists sharpe_ratio_avg double",
                "alter table meta.backtest_task add column if not exists profit_loss_ratio_avg double",
                "alter table meta.backtest_task add column if not exists excess_return_avg double",
                "alter table meta.backtest_task add column if not exists max_drawdown_avg double",
            ):
                connection.execute(statement)
            connection.execute(
                """
                create table if not exists meta.backtest_signal (
                    task_id bigint not null,
                    trade_date date not null,
                    strategy_name varchar not null,
                    code varchar not null,
                    code_name varchar,
                    universe_json varchar,
                    signal_json varchar not null,
                    created_at timestamp not null default current_timestamp
                )
                """
            )
            connection.execute(
                """
                create table if not exists meta.backtest_buy_order (
                    task_id bigint not null,
                    run_no bigint not null default 1,
                    trade_date date not null,
                    code varchar not null,
                    code_name varchar,
                    buy_price double not null,
                    quantity bigint not null,
                    amount double not null,
                    fee double not null,
                    cash_after double not null,
                    signal_json varchar,
                    created_at timestamp not null default current_timestamp
                )
                """
            )
            connection.execute(
                "alter table meta.backtest_signal add column if not exists universe_json varchar"
            )
            connection.execute(
                "alter table meta.backtest_buy_order add column if not exists run_no bigint default 1"
            )
            connection.execute(
                """
                create table if not exists meta.backtest_sell_order (
                    task_id bigint not null,
                    run_no bigint not null default 1,
                    trade_date date not null,
                    code varchar not null,
                    code_name varchar,
                    sell_price double not null,
                    quantity bigint not null,
                    amount double not null,
                    fee double not null,
                    cash_after double not null,
                    buy_date date,
                    buy_price double,
                    pnl double,
                    sell_reason varchar,
                    level bigint,
                    created_at timestamp not null default current_timestamp
                )
                """
            )
            connection.execute(
                "alter table meta.backtest_sell_order add column if not exists run_no bigint default 1"
            )
            connection.execute(
                "alter table meta.backtest_sell_order add column if not exists sell_reason varchar"
            )
            connection.execute(
                "alter table meta.backtest_sell_order add column if not exists level bigint"
            )
            connection.execute(
                """
                create table if not exists meta.backtest_daily_snapshot (
                    task_id bigint not null,
                    run_no bigint not null default 1,
                    trade_date date not null,
                    total_asset double not null,
                    cash double not null,
                    holding_market_value double not null,
                    holding_count bigint not null,
                    watch_count bigint not null,
                    holding_json varchar not null,
                    watch_json varchar not null,
                    created_at timestamp not null default current_timestamp
                )
                """
            )
            connection.execute(
                "alter table meta.backtest_daily_snapshot add column if not exists run_no bigint default 1"
            )

    def create_task(
        self,
        *,
        strategy_name: str,
        start_date: date,
        end_date: date,
        initial_cash: float,
        simulation_runs: int,
        initial_log: str,
    ) -> BacktestTaskDTO:
        self.ensure_tables()
        with self.duckdb.connect(read_only=False) as connection:
            # 历史任务存在显式 id，序列可能落后，统一用 max(id)+1 分配
            next_id = connection.execute(
                "select coalesce(max(id), 0) + 1 from meta.backtest_task"
            ).fetchone()[0]
            row = connection.execute(
                """
                insert into meta.backtest_task(
                    id, status, strategy_name, start_date, end_date, initial_cash,
                    simulation_runs, completed_runs, started_at, logs
                )
                values (?, 'running', ?, ?, ?, ?, ?, 0, current_timestamp, ?)
                returning *
                """,
                [
                    next_id,
                    strategy_name,
                    start_date,
                    end_date,
                    initial_cash,
                    simulation_runs,
                    self._format_log(initial_log),
                ],
            ).fetchone()
        task = self._to_backtest_task(row)
        if task is None:
            raise RuntimeError("failed to create backtest task")
        return task

    def append_task_log(self, task_id: int, message: str) -> None:
        with self.duckdb.connect(read_only=False) as connection:
            row = connection.execute(
                "select logs from meta.backtest_task where id = ?",
                [task_id],
            ).fetchone()
            logs = "" if row is None else row[0] or ""
            connection.execute(
                """
                update meta.backtest_task
                set logs = ?, updated_at = current_timestamp
                where id = ?
                """,
                [self._trim_logs(logs + self._format_log(message)), task_id],
            )

    def update_task_progress(
        self,
        *,
        task_id: int,
        completed_runs: int | None = None,
        trading_day_count: int | None = None,
        signal_count: int | None = None,
    ) -> None:
        assignments = ["updated_at = current_timestamp"]
        values: list[Any] = []
        if completed_runs is not None:
            assignments.append("completed_runs = ?")
            values.append(completed_runs)
        if trading_day_count is not None:
            assignments.append("trading_day_count = ?")
            values.append(trading_day_count)
        if signal_count is not None:
            assignments.append("signal_count = ?")
            values.append(signal_count)
        values.append(task_id)
        with self.duckdb.connect(read_only=False) as connection:
            connection.execute(
                f"update meta.backtest_task set {', '.join(assignments)} where id = ?",
                values,
            )

    def finish_task(
        self,
        *,
        task_id: int,
        status: str,
        message: str,
        completed_runs: int | None = None,
        final_assets: list[float] | None = None,
        initial_cash: float | None = None,
        annualized_return_avg: float | None = None,
        trades_per_year_avg: float | None = None,
        win_rate_avg: float | None = None,
        sharpe_ratio_avg: float | None = None,
        profit_loss_ratio_avg: float | None = None,
        excess_return_avg: float | None = None,
        max_drawdown_avg: float | None = None,
    ) -> None:
        if status not in {"success", "error"}:
            raise ValueError(f"invalid backtest task status: {status}")
        final_asset_avg = final_asset_min = final_asset_max = None
        final_return_avg = final_return_min = final_return_max = None
        if final_assets:
            final_asset_avg = sum(final_assets) / len(final_assets)
            final_asset_min = min(final_assets)
            final_asset_max = max(final_assets)
            if initial_cash is not None and initial_cash > 0:
                returns = [(value - initial_cash) / initial_cash for value in final_assets]
                final_return_avg = sum(returns) / len(returns)
                final_return_min = min(returns)
                final_return_max = max(returns)

        with self.duckdb.connect(read_only=False) as connection:
            row = connection.execute(
                "select logs from meta.backtest_task where id = ?",
                [task_id],
            ).fetchone()
            logs = "" if row is None else row[0] or ""
            connection.execute(
                """
                update meta.backtest_task
                set status = ?,
                    completed_runs = coalesce(?, completed_runs),
                    final_asset_avg = coalesce(?, final_asset_avg),
                    final_asset_min = coalesce(?, final_asset_min),
                    final_asset_max = coalesce(?, final_asset_max),
                    final_return_avg = coalesce(?, final_return_avg),
                    final_return_min = coalesce(?, final_return_min),
                    final_return_max = coalesce(?, final_return_max),
                    annualized_return_avg = coalesce(?, annualized_return_avg),
                    trades_per_year_avg = coalesce(?, trades_per_year_avg),
                    win_rate_avg = coalesce(?, win_rate_avg),
                    sharpe_ratio_avg = coalesce(?, sharpe_ratio_avg),
                    profit_loss_ratio_avg = coalesce(?, profit_loss_ratio_avg),
                    excess_return_avg = coalesce(?, excess_return_avg),
                    max_drawdown_avg = coalesce(?, max_drawdown_avg),
                    logs = ?,
                    finished_at = current_timestamp,
                    updated_at = current_timestamp
                where id = ?
                """,
                [
                    status,
                    completed_runs,
                    final_asset_avg,
                    final_asset_min,
                    final_asset_max,
                    final_return_avg,
                    final_return_min,
                    final_return_max,
                    annualized_return_avg,
                    trades_per_year_avg,
                    win_rate_avg,
                    sharpe_ratio_avg,
                    profit_loss_ratio_avg,
                    excess_return_avg,
                    max_drawdown_avg,
                    self._trim_logs(logs + self._format_log(message)),
                    task_id,
                ],
            )

    def finish_running_tasks(self, message: str) -> int:
        self.ensure_tables()
        with self.duckdb.connect(read_only=False) as connection:
            rows = connection.execute(
                """
                select id, logs
                from meta.backtest_task
                where status = 'running'
                order by id
                """
            ).fetchall()
            for task_id, logs in rows:
                connection.execute(
                    """
                    update meta.backtest_task
                    set status = 'error',
                        logs = ?,
                        finished_at = current_timestamp,
                        updated_at = current_timestamp
                    where id = ?
                    """,
                    [
                        self._trim_logs((logs or "") + self._format_log(message)),
                        task_id,
                    ],
                )
        return len(rows)

    def get_task(self, task_id: int) -> BacktestTaskDTO | None:
        self.ensure_tables()
        with self.duckdb.connect(read_only=True) as connection:
            row = connection.execute(
                """
                select *
                from meta.backtest_task
                where id = ?
                """,
                [task_id],
            ).fetchone()
        return self._to_backtest_task(row)

    def get_latest_task(self) -> BacktestTaskDTO | None:
        self.ensure_tables()
        with self.duckdb.connect(read_only=True) as connection:
            row = connection.execute(
                """
                select *
                from meta.backtest_task
                order by id desc
                limit 1
                """
            ).fetchone()
        return self._to_backtest_task(row)

    def list_tasks(
        self,
        limit: int = 100,
        *,
        latest_per_strategy: bool = True,
    ) -> list[BacktestTaskDTO]:
        """回测任务列表；默认每种策略只返回最新一条，latest_per_strategy=False 返回全量历史。"""
        self.ensure_tables()
        normalized_limit = max(1, min(limit, 500))
        with self.duckdb.connect(read_only=True) as connection:
            if latest_per_strategy:
                rows = connection.execute(
                    """
                    select * exclude (rn)
                    from (
                        select *,
                               row_number() over (
                                   partition by strategy_name
                                   order by id desc
                               ) as rn
                        from meta.backtest_task
                    )
                    where rn = 1
                    order by id desc
                    limit ?
                    """,
                    [normalized_limit],
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    select *
                    from meta.backtest_task
                    order by id desc
                    limit ?
                    """,
                    [normalized_limit],
                ).fetchall()
        return [task for row in rows for task in [self._to_backtest_task(row)] if task is not None]

    def clear_task_rows(self, task_id: int) -> None:
        with self.duckdb.connect(read_only=False) as connection:
            for table in (
                "meta.backtest_signal",
                "meta.backtest_buy_order",
                "meta.backtest_sell_order",
                "meta.backtest_daily_snapshot",
            ):
                connection.execute(f"delete from {table} where task_id = ?", [task_id])

    def get_trading_dates(self, *, start_date: date, end_date: date) -> list[date]:
        with self.duckdb.connect(read_only=True) as connection:
            rows = connection.execute(
                """
                select cal_date
                from tushare.trade_cal
                where cal_date between ? and ?
                  and is_open = 1
                order by cal_date
                """,
                [start_date, end_date],
            ).fetchall()
        return [row[0] for row in rows if isinstance(row[0], date)]

    def load_price_data(
        self,
        *,
        codes: list[str],
        start_date: date,
        end_date: date,
    ) -> dict[str, dict[date, tuple[float, ...]]]:
        """一次性装载撮合所需行情。

        tuple = (qfq_open, qfq_high, qfq_low, qfq_close, vol, pct_chg, prev_ma_10, qfq_pre_close)。
        价格为前复权口径；缺失值为 nan。撮合主循环禁止再查询数据库。
        """
        if not codes:
            return {}
        with self.duckdb.connect(read_only=True) as connection:
            frame = connection.execute(
                """
                with priced as (
                    select code, trade_date,
                           qfq_open, qfq_high, qfq_low, qfq_close, vol, pct_chg,
                           lag(ma_10) over(partition by code order by trade_date) as prev_ma_10,
                           qfq_pre_close
                    from tushare.stock_daily_technical
                    where trade_date <= ?
                      and code in (select unnest(?))
                )
                select *
                from priced
                where trade_date between ? and ?
                order by code, trade_date
                """,
                [end_date, codes, start_date, end_date],
            ).fetchdf()
        if frame.empty:
            return {}
        nan = float("nan")
        prices: dict[str, dict[date, tuple[float, ...]]] = {}
        code_values = frame["code"].tolist()
        date_values = frame["trade_date"].tolist()
        opens = frame["qfq_open"].tolist()
        highs = frame["qfq_high"].tolist()
        lows = frame["qfq_low"].tolist()
        closes = frame["qfq_close"].tolist()
        vols = frame["vol"].tolist()
        pct_chgs = frame["pct_chg"].tolist()
        prev_ma10s = frame["prev_ma_10"].tolist()
        qfq_pre_closes = frame["qfq_pre_close"].tolist()
        for index in range(len(code_values)):
            day = date_values[index]
            if isinstance(day, datetime):
                day = day.date()
            prices.setdefault(str(code_values[index]), {})[day] = (
                float(opens[index]) if opens[index] is not None else nan,
                float(highs[index]) if highs[index] is not None else nan,
                float(lows[index]) if lows[index] is not None else nan,
                float(closes[index]) if closes[index] is not None else nan,
                float(vols[index]) if vols[index] is not None else nan,
                float(pct_chgs[index]) if pct_chgs[index] is not None else nan,
                float(prev_ma10s[index]) if prev_ma10s[index] is not None else nan,
                float(qfq_pre_closes[index]) if qfq_pre_closes[index] is not None else nan,
            )
        return prices

    def get_task_detail(
        self,
        *,
        task_id: int,
        run_no: int,
        include_curves: bool = True,
    ) -> dict[str, Any]:
        """回测详情：各轮收益率曲线 + 指定轮次按持仓聚合的交易列表（时间顺序）。"""
        with self.duckdb.connect(read_only=True) as connection:
            task_row = connection.execute(
                "select initial_cash from meta.backtest_task where id = ?",
                [task_id],
            ).fetchone()
            if task_row is None:
                raise ValueError(f"unknown backtest task: {task_id}")
            initial_cash = float(task_row[0] or 0)

            run_rows = connection.execute(
                "select distinct run_no from meta.backtest_daily_snapshot where task_id = ? order by run_no",
                [task_id],
            ).fetchall()
            available_runs = [int(row[0]) for row in run_rows]

            curves: dict[str, Any] | None = None
            if include_curves and available_runs and initial_cash > 0:
                snapshot_rows = connection.execute(
                    """
                    select run_no, trade_date, total_asset
                    from meta.backtest_daily_snapshot
                    where task_id = ?
                    order by run_no, trade_date
                    """,
                    [task_id],
                ).fetchall()
                dates: list[str] = []
                returns_by_run: dict[int, list[float]] = {}
                first_run = available_runs[0]
                for row_run, trade_date, total_asset in snapshot_rows:
                    if int(row_run) == first_run:
                        dates.append(str(trade_date))
                    returns_by_run.setdefault(int(row_run), []).append(
                        round(float(total_asset) / initial_cash - 1.0, 6)
                    )
                curves = {
                    "dates": dates,
                    "runs": [
                        {"run_no": run, "returns": values}
                        for run, values in sorted(returns_by_run.items())
                    ],
                }

            buy_rows = connection.execute(
                """
                select trade_date, code, code_name, buy_price, quantity, amount, fee, signal_json
                from meta.backtest_buy_order
                where task_id = ? and run_no = ?
                order by trade_date, code
                """,
                [task_id, run_no],
            ).fetchall()
            sell_rows = connection.execute(
                """
                select trade_date, code, buy_date, sell_price, quantity, amount, fee,
                       pnl, sell_reason, level
                from meta.backtest_sell_order
                where task_id = ? and run_no = ?
                order by trade_date
                """,
                [task_id, run_no],
            ).fetchall()

        sells_by_position: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for trade_date, code, buy_date, sell_price, quantity, amount, fee, pnl, reason, level in sell_rows:
            sells_by_position.setdefault((str(code), str(buy_date)), []).append(
                {
                    "trade_date": str(trade_date),
                    "sell_price": float(sell_price),
                    "quantity": int(quantity),
                    "amount": float(amount),
                    "fee": float(fee),
                    "pnl": None if pnl is None else float(pnl),
                    "reason": reason,
                    "level": None if level is None else int(level),
                }
            )

        trades: list[dict[str, Any]] = []
        for trade_date, code, code_name, buy_price, quantity, amount, fee, signal_json in buy_rows:
            buy_date_text = str(trade_date)
            sells = sells_by_position.get((str(code), buy_date_text), [])
            sold_quantity = sum(item["quantity"] for item in sells)
            closed = sold_quantity >= int(quantity)
            total_pnl = sum(item["pnl"] for item in sells if item["pnl"] is not None)
            last_sell_date = sells[-1]["trade_date"] if sells else None
            holding_days = None
            if last_sell_date is not None:
                holding_days = (date.fromisoformat(last_sell_date) - date.fromisoformat(buy_date_text)).days
            try:
                signal = json.loads(signal_json) if signal_json else {}
            except json.JSONDecodeError:
                signal = {}
            trades.append(
                {
                    "code": str(code),
                    "code_name": code_name,
                    "buy_date": buy_date_text,
                    "buy_price": float(buy_price),
                    "quantity": int(quantity),
                    "buy_amount": float(amount),
                    "buy_fee": float(fee),
                    "sells": sells,
                    "sell_count": len(sells),
                    "total_pnl": total_pnl if sells else None,
                    "last_sell_date": last_sell_date,
                    "holding_days": holding_days,
                    "closed": closed,
                    "signal": signal,
                }
            )
        return {
            "task_id": task_id,
            "run_no": run_no,
            "available_runs": available_runs,
            "equity_curves": curves,
            "trades": trades,
        }

    def insert_signal_rows(self, rows: list[list[Any]]) -> None:
        """批量写入预计算信号；行格式见 BacktestService._precompute_signals。"""
        if not rows:
            return
        with self.duckdb.connect(read_only=False) as connection:
            connection.executemany(
                """
                insert into meta.backtest_signal(
                    task_id, trade_date, strategy_name, code, code_name,
                    universe_json, signal_json
                )
                values (?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def insert_buy_orders(self, rows: list[list[Any]]) -> None:
        if not rows:
            return
        with self.duckdb.connect(read_only=False) as connection:
            connection.executemany(
                """
                insert into meta.backtest_buy_order(
                    task_id, run_no, trade_date, code, code_name, buy_price, quantity,
                    amount, fee, cash_after, signal_json
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def insert_sell_orders(self, rows: list[list[Any]]) -> None:
        if not rows:
            return
        with self.duckdb.connect(read_only=False) as connection:
            connection.executemany(
                """
                insert into meta.backtest_sell_order(
                    task_id, run_no, trade_date, code, code_name, sell_price, quantity,
                    amount, fee, cash_after, buy_date, buy_price, pnl, sell_reason, level
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def insert_daily_snapshots(self, rows: list[list[Any]]) -> None:
        if not rows:
            return
        with self.duckdb.connect(read_only=False) as connection:
            connection.executemany(
                """
                insert into meta.backtest_daily_snapshot(
                    task_id, run_no, trade_date, total_asset, cash, holding_market_value,
                    holding_count, watch_count, holding_json, watch_json
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def to_json(self, value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, default=self._normalize_value)

    def _normalize_value(self, value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat(sep=" ")
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, float) and math.isnan(value):
            return None
        return value

    def _format_log(self, message: str) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"[{timestamp}] {message}\n"

    def _trim_logs(self, logs: str) -> str:
        lines = logs.splitlines()
        if len(lines) <= self.MAX_LOG_LINES:
            return logs
        return "\n".join(lines[-self.MAX_LOG_LINES :]) + "\n"

    def _to_backtest_task(self, row: tuple | None) -> BacktestTaskDTO | None:
        if row is None:
            return None
        (
            task_id,
            status,
            strategy_name,
            start_date,
            end_date,
            initial_cash,
            simulation_runs,
            completed_runs,
            trading_day_count,
            signal_count,
            final_asset_avg,
            final_asset_min,
            final_asset_max,
            final_return_avg,
            final_return_min,
            final_return_max,
            started_at,
            finished_at,
            created_at,
            updated_at,
            logs,
            annualized_return_avg,
            trades_per_year_avg,
            win_rate_avg,
            sharpe_ratio_avg,
            profit_loss_ratio_avg,
            excess_return_avg,
            max_drawdown_avg,
        ) = row
        return BacktestTaskDTO(
            id=None if task_id is None else int(task_id),
            status=status,
            strategy_name=strategy_name,
            start_date="" if start_date is None else str(start_date),
            end_date="" if end_date is None else str(end_date),
            initial_cash=float(initial_cash or 0),
            simulation_runs=int(simulation_runs or 0),
            completed_runs=int(completed_runs or 0),
            trading_day_count=None if trading_day_count is None else int(trading_day_count),
            signal_count=None if signal_count is None else int(signal_count),
            final_asset_avg=None if final_asset_avg is None else float(final_asset_avg),
            final_asset_min=None if final_asset_min is None else float(final_asset_min),
            final_asset_max=None if final_asset_max is None else float(final_asset_max),
            final_return_avg=None if final_return_avg is None else float(final_return_avg),
            final_return_min=None if final_return_min is None else float(final_return_min),
            final_return_max=None if final_return_max is None else float(final_return_max),
            annualized_return_avg=None if annualized_return_avg is None else float(annualized_return_avg),
            trades_per_year_avg=None if trades_per_year_avg is None else float(trades_per_year_avg),
            win_rate_avg=None if win_rate_avg is None else float(win_rate_avg),
            sharpe_ratio_avg=None if sharpe_ratio_avg is None else float(sharpe_ratio_avg),
            profit_loss_ratio_avg=None if profit_loss_ratio_avg is None else float(profit_loss_ratio_avg),
            excess_return_avg=None if excess_return_avg is None else float(excess_return_avg),
            max_drawdown_avg=None if max_drawdown_avg is None else float(max_drawdown_avg),
            started_at=None if started_at is None else str(started_at),
            finished_at=None if finished_at is None else str(finished_at),
            created_at=None if created_at is None else str(created_at),
            updated_at=None if updated_at is None else str(updated_at),
            logs=logs or "",
        )
