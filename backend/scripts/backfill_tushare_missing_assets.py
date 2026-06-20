from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

import baostock as bs
import duckdb
import pandas as pd


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.repositories.duckdb_repository import DuckDBRepository
from app.repositories.tushare_repository import TushareRepository
from app.services.tushare_client import get_tushare_pro, reset_tushare_pro


DEFAULT_AUDIT_DIR = ROOT_DIR / "tmp" / "asset_audit_20260620_ex_bj"
DEFAULT_LOG_PATH = ROOT_DIR / "tmp" / "asset_audit_20260620_ex_bj_incremental_backfill.log"
DAILY_BASIC_FIELDS = (
    "ts_code,trade_date,close,turnover_rate,turnover_rate_f,volume_ratio,"
    "pe,pe_ttm,pb,ps,ps_ttm,dv_ratio,dv_ttm,total_share,float_share,"
    "free_share,total_mv,circ_mv"
)
INDEX_DAILY_FIELDS = (
    "ts_code,trade_date,close,open,high,low,pre_close,change,pct_chg,vol,amount"
)
TUSHARE_STK_MINS_MAX_ROWS = 8000
BAOSTOCK_STK_MINS_MAX_ROWS = 200000
MAX_5MIN_RUN_DAYS = 90


@dataclass(frozen=True)
class MissingFile:
    asset: str
    path: Path
    key_columns: tuple[str, ...]


class MissingCsv:
    def __init__(self, spec: MissingFile) -> None:
        self.spec = spec
        self.rows = self._read_rows()
        self._ensure_backup()

    def __len__(self) -> int:
        return len(self.rows)

    def _read_rows(self) -> list[dict[str, str]]:
        if not self.spec.path.exists():
            return []
        with self.spec.path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            return [dict(row) for row in reader]

    def _ensure_backup(self) -> None:
        if not self.spec.path.exists():
            return
        backup_path = self.spec.path.with_name(f"{self.spec.path.stem}.initial_backup.csv")
        if backup_path.exists():
            return
        backup_path.write_bytes(self.spec.path.read_bytes())

    def remove_keys(self, keys: set[tuple[str, ...]]) -> int:
        if not keys:
            return 0
        before = len(self.rows)
        self.rows = [row for row in self.rows if self.key_for(row) not in keys]
        removed = before - len(self.rows)
        if removed:
            self.save()
        return removed

    def key_for(self, row: dict[str, str]) -> tuple[str, ...]:
        return tuple(str(row.get(column, "")) for column in self.spec.key_columns)

    def save(self) -> None:
        fieldnames = self._fieldnames()
        temp_path = self.spec.path.with_suffix(".tmp")
        with temp_path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.rows)
        temp_path.replace(self.spec.path)

    def _fieldnames(self) -> list[str]:
        if self.rows:
            return list(self.rows[0].keys())
        if self.spec.path.exists():
            with self.spec.path.open("r", encoding="utf-8-sig", newline="") as file:
                reader = csv.DictReader(file)
                if reader.fieldnames:
                    return list(reader.fieldnames)
        return ["asset_table_name", *self.spec.key_columns]


class UnresolvedCsv:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.fieldnames = ["asset", "trade_date", "ts_code", "reason", "details", "updated_at"]
        self.rows_by_key = self._read_existing()

    def _read_existing(self) -> dict[tuple[str, str, str, str], dict[str, str]]:
        if not self.path.exists():
            return {}
        with self.path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            return {
                (row.get("asset", ""), row.get("trade_date", ""), row.get("ts_code", ""), row.get("reason", "")): dict(row)
                for row in reader
            }

    def upsert(self, *, asset: str, trade_date: str, ts_code: str, reason: str, details: str) -> None:
        self.rows_by_key[(asset, trade_date, ts_code, reason)] = {
            "asset": asset,
            "trade_date": trade_date,
            "ts_code": ts_code,
            "reason": reason,
            "details": details,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.save()

    def has_asset_day_code(self, asset: str, trade_date: str, ts_code: str) -> bool:
        return any(
            row.get("asset") == asset and row.get("trade_date") == trade_date and row.get("ts_code") == ts_code
            for row in self.rows_by_key.values()
        )

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(".tmp")
        with temp_path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=self.fieldnames)
            writer.writeheader()
            writer.writerows(sorted(self.rows_by_key.values(), key=lambda row: (row["asset"], row["trade_date"], row["ts_code"], row["reason"])))
        temp_path.replace(self.path)


class ProgressLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, message: str) -> None:
        line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}"
        print(line, flush=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(line + "\n")


class MissingBackfiller:
    def __init__(
        self,
        *,
        audit_dir: Path,
        log_path: Path,
        execute: bool,
        max_attempts: int,
        progress_every: int,
        max_records: int | None,
        min_date: date | None,
        max_date: date | None,
        retry_unresolved: bool,
    ) -> None:
        self.audit_dir = audit_dir
        self.log = ProgressLog(log_path)
        self.execute = execute
        self.max_attempts = max_attempts
        self.progress_every = max(1, progress_every)
        self.max_records = max_records
        self.min_date = min_date
        self.max_date = max_date
        self.retry_unresolved = retry_unresolved
        self.repository = TushareRepository()
        self.connection_owner = DuckDBRepository()
        self._baostock_logged_in = False
        self.unresolved = UnresolvedCsv(self.audit_dir / "unresolved_missing_backfill.csv")
        self.stats: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def run(self, assets: list[str]) -> None:
        self.repository.ensure_tables()
        self.log.write(
            "incremental missing backfill started "
            f"mode={'execute' if self.execute else 'dry-run'} audit_dir={self.audit_dir}"
        )
        for asset in assets:
            if asset == "daily_basic":
                self.backfill_daily_basic()
            elif asset == "bak_basic":
                self.backfill_bak_basic()
            elif asset == "index_daily":
                self.backfill_index_daily()
            elif asset == "stk_mins_5min":
                self.backfill_stk_mins_5min()
            else:
                raise ValueError(f"unsupported asset: {asset}")
        self.log.write("incremental missing backfill finished")
        self._write_summary()

    def backfill_daily_basic(self) -> None:
        missing = self._missing_file(
            "daily_basic",
            "missing_daily_basic_by_trade_date_ts_code.csv",
            ("trade_date", "ts_code"),
        )
        self._run_stock_daily_rows(
            asset="daily_basic",
            missing=missing,
            fetcher=lambda trade_day, ts_code: get_tushare_pro().daily_basic(
                ts_code=ts_code,
                trade_date=self._fmt_date(trade_day),
                fields=DAILY_BASIC_FIELDS,
            ),
            writer=self._partial_upsert_daily_basic,
            exists_query="""
                select trade_date, ts_code
                from tushare.daily_basic
                where trade_date = ? and ts_code = ?
            """,
        )

    def backfill_bak_basic(self) -> None:
        missing = self._missing_file(
            "bak_basic",
            "missing_bak_basic_by_trade_date_ts_code.csv",
            ("trade_date", "ts_code"),
        )
        self._run_stock_daily_rows(
            asset="bak_basic",
            missing=missing,
            fetcher=lambda trade_day, ts_code: get_tushare_pro().bak_basic(
                ts_code=ts_code,
                trade_date=self._fmt_date(trade_day),
            ),
            writer=self._partial_upsert_bak_basic,
            exists_query="""
                select trade_date, ts_code
                from tushare.bak_basic
                where trade_date = ? and ts_code = ?
            """,
        )

    def backfill_index_daily(self) -> None:
        missing = self._missing_file(
            "index_daily",
            "missing_index_daily_by_trade_date_ts_code.csv",
            ("trade_date", "ts_code"),
        )
        by_code: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in self._filter_rows_by_date(missing.rows):
            if self._should_skip_unresolved("index_daily", row):
                continue
            by_code[str(row["ts_code"])].append(row)
        work_items = list(by_code.items())
        if self.max_records is not None:
            work_items = work_items[: self.max_records]
        started = time.monotonic()
        self.log.write(f"index_daily pending codes={len(work_items)} missing_rows={len(missing)}")
        for index, (ts_code, rows) in enumerate(work_items, start=1):
            dates = sorted({date.fromisoformat(row["trade_date"]) for row in rows})
            if not dates:
                continue
            frame = self._call_with_retries(
                f"index_daily {ts_code} {dates[0]}->{dates[-1]}",
                lambda: get_tushare_pro().index_daily(
                    ts_code=ts_code,
                    start_date=self._fmt_date(dates[0]),
                    end_date=self._fmt_date(dates[-1]),
                    fields=INDEX_DAILY_FIELDS,
                ),
            )
            if frame is None:
                self.stats["index_daily"]["failed"] += len(rows)
                continue
            written = self.repository.upsert_index_daily(frame) if self.execute else 0
            filled = self._existing_index_keys(ts_code, dates)
            removed = missing.remove_keys(filled) if self.execute else 0
            if self.execute:
                unresolved = self._record_unresolved_rows(
                    asset="index_daily",
                    rows=rows,
                    filled=filled,
                    reason="source_returned_no_key",
                    details=f"source_rows={len(frame)} written_rows={written}",
                )
                removed += missing.remove_keys(unresolved)
            self.stats["index_daily"]["written_rows"] += written
            self.stats["index_daily"]["removed_missing"] += removed
            self._progress("index_daily", index, len(work_items), started, extra=f"rows={written} removed={removed}")

    def backfill_stk_mins_5min(self) -> None:
        missing = self._missing_file(
            "stk_mins_5min",
            "missing_stk_mins_5min_by_trade_date_ts_code.csv",
            ("trade_date", "ts_code"),
        )
        by_code: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in self._filter_rows_by_date(missing.rows):
            if self._should_skip_unresolved("stk_mins_5min", row):
                continue
            by_code[str(row["ts_code"])].append(row)
        work_items = self._stock_day_runs(by_code)
        if self.max_records is not None:
            work_items = work_items[: self.max_records]
        started = time.monotonic()
        self.log.write(f"stk_mins_5min pending runs={len(work_items)} missing_stock_days={len(missing)}")
        try:
            for index, (ts_code, start_date, end_date, rows) in enumerate(work_items, start=1):
                frame, source_name = self._call_5min_range_with_retries(
                    ts_code=ts_code,
                    start_date=start_date,
                    end_date=end_date,
                )
                if frame is None:
                    self.stats["stk_mins_5min"]["failed"] += len(rows)
                    continue
                written = self.repository.upsert_stk_mins_5min(frame) if self.execute else 0
                dates = sorted({date.fromisoformat(row["trade_date"]) for row in rows})
                filled = self._existing_5min_keys(ts_code, dates)
                removed = missing.remove_keys(filled) if self.execute else 0
                if self.execute:
                    unresolved = self._record_unresolved_rows(
                        asset="stk_mins_5min",
                        rows=rows,
                        filled=filled,
                        reason="source_returned_incomplete_bars",
                        details=f"source={source_name} source_rows={len(frame)} written_rows={written}",
                    )
                    removed += missing.remove_keys(unresolved)
                self.stats["stk_mins_5min"]["written_rows"] += written
                self.stats["stk_mins_5min"]["removed_missing"] += removed
                if source_name == "tushare":
                    self.stats["stk_mins_5min"]["fallback_runs"] += 1
                self._progress(
                    "stk_mins_5min",
                    index,
                    len(work_items),
                    started,
                    extra=f"source={source_name} rows={written} removed={removed}",
                )
        finally:
            self._logout_baostock()

    def _run_stock_daily_rows(
        self,
        *,
        asset: str,
        missing: MissingCsv,
        fetcher: Any,
        writer: Any,
        exists_query: str,
    ) -> None:
        rows = [
            row
            for row in self._filter_rows_by_date(missing.rows)
            if not self._should_skip_unresolved(asset, row)
        ]
        if self.max_records is not None:
            rows = rows[: self.max_records]
        started = time.monotonic()
        self.log.write(f"{asset} pending keyed_rows={len(rows)} missing_rows={len(missing)}")
        for index, row in enumerate(rows, start=1):
            trade_day = date.fromisoformat(row["trade_date"])
            ts_code = str(row["ts_code"])
            scope = f"{asset} {trade_day} {ts_code}"
            frame = self._call_with_retries(
                scope,
                lambda trade_day=trade_day, ts_code=ts_code: fetcher(trade_day, ts_code),
            )
            if frame is None:
                self.stats[asset]["failed"] += 1
                continue
            frame = self._filter_exact_stock_day_frame(frame, trade_day, ts_code)
            written = writer(frame) if self.execute else 0
            filled = self._existing_stock_day_key(trade_day, ts_code, exists_query)
            removed = missing.remove_keys(filled) if self.execute else 0
            if self.execute:
                unresolved = self._record_unresolved_rows(
                    asset=asset,
                    rows=[row],
                    filled=filled,
                    reason="source_returned_no_key",
                    details=f"source_rows={len(frame)} written_rows={written}",
                )
                removed += missing.remove_keys(unresolved)
            self.stats[asset]["written_rows"] += written
            self.stats[asset]["removed_missing"] += removed
            self._progress(asset, index, len(rows), started, extra=f"rows={written} removed={removed}")

    def _filter_exact_stock_day_frame(self, frame: pd.DataFrame, trade_day: date, ts_code: str) -> pd.DataFrame:
        if frame.empty or "ts_code" not in frame.columns or "trade_date" not in frame.columns:
            return frame.iloc[0:0].copy()
        normalized_dates = frame["trade_date"].astype(str).str.replace("-", "", regex=False)
        return frame[(frame["ts_code"].astype(str) == ts_code) & (normalized_dates == self._fmt_date(trade_day))].copy()

    def _partial_upsert_daily_basic(self, frame: pd.DataFrame) -> int:
        if frame.empty:
            return 0
        fields = [
            "ts_code",
            "trade_date",
            "close",
            "turnover_rate",
            "turnover_rate_f",
            "volume_ratio",
            "pe",
            "pe_ttm",
            "pb",
            "ps",
            "ps_ttm",
            "dv_ratio",
            "dv_ttm",
            "total_share",
            "float_share",
            "free_share",
            "total_mv",
            "circ_mv",
        ]
        rows = []
        for item in frame.to_dict("records"):
            row = [self.repository._none_if_blank(item.get(field)) for field in fields]
            row[1] = self.repository._parse_yyyymmdd(row[1])
            for index in range(2, len(row)):
                row[index] = self.repository._none_or_float(row[index])
            if self.repository.is_supported_stock_ts_code(row[0]) and row[1] is not None:
                rows.append(row)
        if not rows:
            return 0
        with self.connection_owner.connect(read_only=False) as connection:
            connection.executemany(
                "delete from tushare.daily_basic where ts_code = ? and trade_date = ?",
                [[row[0], row[1]] for row in rows],
            )
            connection.executemany(
                """
                insert into tushare.daily_basic(
                    ts_code, trade_date, close, turnover_rate, turnover_rate_f,
                    volume_ratio, pe, pe_ttm, pb, ps, ps_ttm, dv_ratio,
                    dv_ttm, total_share, float_share, free_share, total_mv, circ_mv
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        return len(rows)

    def _partial_upsert_bak_basic(self, frame: pd.DataFrame) -> int:
        if frame.empty:
            return 0
        fields = [
            "trade_date",
            "ts_code",
            "name",
            "industry",
            "area",
            "pe",
            "float_share",
            "total_share",
            "total_assets",
            "liquid_assets",
            "fixed_assets",
            "reserved",
            "reserved_pershare",
            "eps",
            "bvps",
            "pb",
            "list_date",
            "undp",
            "per_undp",
            "rev_yoy",
            "profit_yoy",
            "gpr",
            "npr",
            "holder_num",
        ]
        rows = []
        for item in frame.to_dict("records"):
            row = [self.repository._none_if_blank(item.get(field)) for field in fields]
            row[0] = self.repository._parse_yyyymmdd(row[0])
            row[16] = self.repository._parse_yyyymmdd(row[16])
            for index in range(5, 16):
                row[index] = self.repository._none_or_float(row[index])
            for index in range(17, 23):
                row[index] = self.repository._none_or_float(row[index])
            row[23] = self.repository._none_or_int(row[23])
            if self.repository.is_supported_stock_ts_code(row[1]) and row[0] is not None:
                rows.append(row)
        if not rows:
            return 0
        with self.connection_owner.connect(read_only=False) as connection:
            connection.executemany(
                "delete from tushare.bak_basic where trade_date = ? and ts_code = ?",
                [[row[0], row[1]] for row in rows],
            )
            connection.executemany(
                """
                insert into tushare.bak_basic(
                    trade_date, ts_code, name, industry, area, pe, float_share,
                    total_share, total_assets, liquid_assets, fixed_assets, reserved,
                    reserved_pershare, eps, bvps, pb, list_date, undp, per_undp,
                    rev_yoy, profit_yoy, gpr, npr, holder_num
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        return len(rows)

    def _call_with_retries(self, scope: str, fetcher: Any) -> pd.DataFrame | None:
        for attempt in range(1, self.max_attempts + 1):
            try:
                frame = fetcher()
                if not isinstance(frame, pd.DataFrame):
                    raise RuntimeError(f"unexpected response type: {type(frame).__name__}")
                return frame
            except Exception as exc:
                reset_tushare_pro()
                self.log.write(
                    f"{scope} failed attempt={attempt}/{self.max_attempts}: {type(exc).__name__}: {exc}"
                )
                if attempt < self.max_attempts:
                    time.sleep(min(2 ** (attempt - 1), 16))
        return None

    def _existing_stock_day_key(
        self,
        trade_day: date,
        ts_code: str,
        query: str,
    ) -> set[tuple[str, str]]:
        with self.connection_owner.connect(read_only=True) as connection:
            rows = connection.execute(query, [trade_day, ts_code]).fetchall()
        return {(row[0].isoformat(), str(row[1])) for row in rows}

    def _existing_index_keys(self, ts_code: str, dates: list[date]) -> set[tuple[str, str]]:
        if not dates:
            return set()
        with self.connection_owner.connect(read_only=True) as connection:
            rows = connection.execute(
                """
                select trade_date, ts_code
                from tushare.index_daily
                where ts_code = ?
                  and trade_date in (select unnest(?))
                """,
                [ts_code, dates],
            ).fetchall()
        return {(row[0].isoformat(), str(row[1])) for row in rows}

    def _existing_5min_keys(self, ts_code: str, dates: list[date]) -> set[tuple[str, str]]:
        if not dates:
            return set()
        with self.connection_owner.connect(read_only=True) as connection:
            rows = connection.execute(
                """
                select trade_date, ts_code
                from tushare.stk_mins_5min
                where ts_code = ?
                  and trade_date in (select unnest(?))
                group by trade_date, ts_code
                having count(*) >= 48
                """,
                [ts_code, dates],
            ).fetchall()
        return {(row[0].isoformat(), str(row[1])) for row in rows}

    def _record_unresolved_rows(
        self,
        *,
        asset: str,
        rows: list[dict[str, str]],
        filled: set[tuple[str, str]],
        reason: str,
        details: str,
    ) -> set[tuple[str, str]]:
        unresolved_keys: set[tuple[str, str]] = set()
        for row in rows:
            key = (row["trade_date"], row["ts_code"])
            if key in filled:
                continue
            self.unresolved.upsert(
                asset=asset,
                trade_date=row["trade_date"],
                ts_code=row["ts_code"],
                reason=reason,
                details=details,
            )
            unresolved_keys.add(key)
        return unresolved_keys

    def _call_5min_range_with_retries(
        self,
        *,
        ts_code: str,
        start_date: date,
        end_date: date,
    ) -> tuple[pd.DataFrame | None, str | None]:
        use_tushare_fallback = False
        scope = f"stk_mins_5min {ts_code} {start_date}->{end_date}"
        for attempt in range(1, self.max_attempts + 1):
            source_name = "tushare" if use_tushare_fallback else "baostock"
            try:
                if use_tushare_fallback:
                    frame = self._fetch_tushare_5min_range(ts_code=ts_code, start_date=start_date, end_date=end_date)
                else:
                    frame = self._fetch_baostock_5min_range(ts_code=ts_code, start_date=start_date, end_date=end_date)
                if not isinstance(frame, pd.DataFrame):
                    raise RuntimeError(f"unexpected {source_name} response type: {type(frame).__name__}")
                if frame.empty and not use_tushare_fallback:
                    use_tushare_fallback = True
                    self.log.write(f"{scope} source=baostock returned 0 rows; fallback to tushare")
                    continue
                return frame, source_name
            except Exception as exc:
                if use_tushare_fallback:
                    reset_tushare_pro()
                self.log.write(
                    f"{scope} source={source_name} failed attempt={attempt}/{self.max_attempts}: "
                    f"{type(exc).__name__}: {exc}"
                )
                if attempt >= self.max_attempts:
                    return None, source_name
                if not use_tushare_fallback and attempt >= 3:
                    use_tushare_fallback = True
                    self.log.write(f"{scope} fallback to tushare")
                    continue
                time.sleep(min(2 ** (attempt - 1), 16))
        return None, None

    def _fetch_tushare_5min_range(self, *, ts_code: str, start_date: date, end_date: date) -> pd.DataFrame:
        frame = get_tushare_pro().stk_mins(
            ts_code=ts_code,
            freq="5min",
            start_date=f"{start_date:%Y-%m-%d} 09:00:00",
            end_date=f"{end_date:%Y-%m-%d} 15:30:00",
        )
        if len(frame) >= TUSHARE_STK_MINS_MAX_ROWS:
            raise RuntimeError(f"tushare stk_mins returned {len(frame)} rows, reaches max limit {TUSHARE_STK_MINS_MAX_ROWS}")
        return frame

    def _fetch_baostock_5min_range(self, *, ts_code: str, start_date: date, end_date: date) -> pd.DataFrame:
        self._ensure_baostock_login()
        query = bs.query_history_k_data_plus(
            self._to_baostock_code(ts_code),
            "date,time,code,open,high,low,close,volume,amount,adjustflag",
            start_date=f"{start_date:%Y-%m-%d}",
            end_date=f"{end_date:%Y-%m-%d}",
            frequency="5",
            adjustflag="3",
        )
        if query.error_code != "0":
            raise RuntimeError(f"baostock query failed: {query.error_code} {query.error_msg}")
        frame = self._baostock_query_to_tushare_shape(query, ts_code)
        if len(frame) >= BAOSTOCK_STK_MINS_MAX_ROWS:
            raise RuntimeError(f"baostock stk_mins returned {len(frame)} rows, reaches max limit {BAOSTOCK_STK_MINS_MAX_ROWS}")
        return frame

    def _baostock_query_to_tushare_shape(self, query: Any, ts_code: str) -> pd.DataFrame:
        rows = []
        while query.next():
            rows.append(query.get_row_data())
        if not rows:
            return pd.DataFrame(columns=["ts_code", "trade_time", "open", "close", "high", "low", "vol", "amount"])
        frame = pd.DataFrame(rows, columns=query.fields)
        trade_time = pd.to_datetime(frame["time"].astype(str).str.slice(0, 14), format="%Y%m%d%H%M%S")
        return pd.DataFrame(
            {
                "ts_code": ts_code,
                "trade_time": trade_time.dt.strftime("%Y-%m-%d %H:%M:%S"),
                "open": pd.to_numeric(frame["open"], errors="coerce"),
                "close": pd.to_numeric(frame["close"], errors="coerce"),
                "high": pd.to_numeric(frame["high"], errors="coerce"),
                "low": pd.to_numeric(frame["low"], errors="coerce"),
                "vol": pd.to_numeric(frame["volume"], errors="coerce"),
                "amount": pd.to_numeric(frame["amount"], errors="coerce"),
            }
        )

    def _ensure_baostock_login(self) -> None:
        if self._baostock_logged_in:
            return
        login_result = bs.login()
        if login_result.error_code != "0":
            raise RuntimeError(f"baostock login failed: {login_result.error_code} {login_result.error_msg}")
        self._baostock_logged_in = True

    def _logout_baostock(self) -> None:
        if self._baostock_logged_in:
            bs.logout()
            self._baostock_logged_in = False

    def _to_baostock_code(self, ts_code: str) -> str:
        symbol, exchange = ts_code.split(".", maxsplit=1)
        prefix = {"SH": "sh", "SZ": "sz", "BJ": "bj"}.get(exchange.upper())
        if prefix is None:
            raise ValueError(f"unsupported Baostock exchange for ts_code: {ts_code}")
        return f"{prefix}.{symbol}"

    def _missing_file(self, asset: str, filename: str, key_columns: tuple[str, ...]) -> MissingCsv:
        missing = MissingCsv(MissingFile(asset, self.audit_dir / filename, key_columns))
        self.log.write(f"{asset} missing_csv={missing.spec.path} rows={len(missing)}")
        return missing

    def _filter_rows_by_date(self, rows: list[dict[str, str]]) -> list[dict[str, str]]:
        if self.min_date is None and self.max_date is None:
            return list(rows)
        filtered = []
        for row in rows:
            trade_day = date.fromisoformat(row["trade_date"])
            if self.min_date is not None and trade_day < self.min_date:
                continue
            if self.max_date is not None and trade_day > self.max_date:
                continue
            filtered.append(row)
        return filtered

    def _should_skip_unresolved(self, asset: str, row: dict[str, str]) -> bool:
        if self.retry_unresolved:
            return False
        return self.unresolved.has_asset_day_code(asset, row["trade_date"], row["ts_code"])

    def _group_by_date(self, rows: Iterable[dict[str, str]]) -> list[tuple[date, list[dict[str, str]]]]:
        grouped: dict[date, list[dict[str, str]]] = defaultdict(list)
        for row in rows:
            grouped[date.fromisoformat(row["trade_date"])].append(row)
        return sorted(grouped.items(), key=lambda item: item[0])

    def _stock_day_runs(
        self,
        by_code: dict[str, list[dict[str, str]]],
    ) -> list[tuple[str, date, date, list[dict[str, str]]]]:
        runs: list[tuple[str, date, date, list[dict[str, str]]]] = []
        for ts_code, rows in sorted(by_code.items()):
            dated_rows = sorted((date.fromisoformat(row["trade_date"]), row) for row in rows)
            current_dates: list[date] = []
            current_rows: list[dict[str, str]] = []
            previous_day: date | None = None
            for trade_day, row in dated_rows:
                contiguous = previous_day is not None and trade_day <= previous_day + timedelta(days=5)
                too_wide = current_dates and (trade_day - current_dates[0]).days >= MAX_5MIN_RUN_DAYS
                if current_dates and (not contiguous or too_wide):
                    runs.append((ts_code, current_dates[0], current_dates[-1], current_rows))
                    current_dates = []
                    current_rows = []
                current_dates.append(trade_day)
                current_rows.append(row)
                previous_day = trade_day
            if current_dates:
                runs.append((ts_code, current_dates[0], current_dates[-1], current_rows))
        return runs

    def _progress(self, asset: str, done: int, total: int, started: float, *, extra: str = "") -> None:
        self.stats[asset]["done_batches"] = done
        if done % self.progress_every != 0 and done != total:
            return
        elapsed = max(0.001, time.monotonic() - started)
        rate = done / elapsed
        remaining = max(0, total - done)
        eta_seconds = remaining / rate if rate > 0 else 0
        self.log.write(
            f"{asset} progress {done}/{total} elapsed={self._fmt_seconds(elapsed)} "
            f"eta={self._fmt_seconds(eta_seconds)} {extra}".rstrip()
        )

    def _write_summary(self) -> None:
        summary_path = self.audit_dir / "incremental_backfill_summary.json"
        with summary_path.open("w", encoding="utf-8") as file:
            json.dump(self.stats, file, ensure_ascii=False, indent=2)
        self.log.write(f"summary written {summary_path}")

    def _fmt_date(self, value: date) -> str:
        return value.strftime("%Y%m%d")

    def _fmt_seconds(self, seconds: float) -> str:
        seconds = int(seconds)
        hours, seconds = divmod(seconds, 3600)
        minutes, seconds = divmod(seconds, 60)
        if hours:
            return f"{hours}h{minutes:02d}m{seconds:02d}s"
        if minutes:
            return f"{minutes}m{seconds:02d}s"
        return f"{seconds}s"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill only rows listed in asset audit missing CSV files, updating those CSV files incrementally."
    )
    parser.add_argument("--audit-dir", type=Path, default=DEFAULT_AUDIT_DIR)
    parser.add_argument("--log-path", type=Path, default=DEFAULT_LOG_PATH)
    parser.add_argument(
        "--assets",
        type=str,
        default="daily_basic,bak_basic,index_daily,stk_mins_5min",
        help="Comma-separated: daily_basic,bak_basic,index_daily,stk_mins_5min",
    )
    parser.add_argument("--execute", action="store_true", help="Write database changes and shrink missing CSVs")
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--progress-every", type=int, default=1)
    parser.add_argument("--max-records", type=int, default=None, help="Limit batches/runs per asset for trial runs")
    parser.add_argument("--min-date", type=str, default=None, help="Only process missing rows on/after YYYY-MM-DD")
    parser.add_argument("--max-date", type=str, default=None, help="Only process missing rows on/before YYYY-MM-DD")
    parser.add_argument("--retry-unresolved", action="store_true", help="Retry rows already recorded in unresolved CSV")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    assets = [asset.strip() for asset in args.assets.split(",") if asset.strip()]
    backfiller = MissingBackfiller(
        audit_dir=args.audit_dir.resolve(),
        log_path=args.log_path.resolve(),
        execute=args.execute,
        max_attempts=args.max_attempts,
        progress_every=args.progress_every,
        max_records=args.max_records,
        min_date=None if args.min_date is None else date.fromisoformat(args.min_date),
        max_date=None if args.max_date is None else date.fromisoformat(args.max_date),
        retry_unresolved=args.retry_unresolved,
    )
    backfiller.run(assets)


if __name__ == "__main__":
    main()
