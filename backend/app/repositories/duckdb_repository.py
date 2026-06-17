from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import Any
import os

import duckdb


class DuckDBRepository:
    _connections: dict[Path, duckdb.DuckDBPyConnection] = {}
    _lock = RLock()

    def __init__(self, db_path: Path | None = None) -> None:
        root_dir = Path(__file__).resolve().parents[3]
        self.db_path = (db_path or root_dir / "data" / "data.duckdb").resolve()

    @contextmanager
    def connect(self, *, read_only: bool = True) -> Iterator[duckdb.DuckDBPyConnection]:
        # DuckDB on Windows is strict about multiple open handles to the same
        # database file. The API polls while refresh jobs write, so reuse one
        # process-local connection and serialize access through this context.
        with self._lock:
            connection = self._connections.get(self.db_path)
            if connection is None:
                connection = duckdb.connect(str(self.db_path), read_only=False)
                connection.execute(
                    f"set threads={int(os.getenv('DUCKDB_THREADS', '2'))}"
                )
                connection.execute("set preserve_insertion_order=false")
                memory_limit = os.getenv("DUCKDB_MEMORY_LIMIT")
                if memory_limit:
                    connection.execute(f"set memory_limit='{memory_limit}'")
                self._connections[self.db_path] = connection
            yield connection

    def get_tables(self) -> list[dict[str, Any]]:
        with self.connect(read_only=True) as connection:
            rows = connection.execute(
                """
                select table_schema, table_name, table_type
                from information_schema.tables
                where table_schema not in ('information_schema', 'pg_catalog')
                order by table_schema, table_name
                """
            ).fetchall()
        return [
            {
                "schema_name": schema_name,
                "table_name": table_name,
                "table_type": table_type,
            }
            for schema_name, table_name, table_type in rows
        ]

    @classmethod
    def close_all(cls) -> None:
        with cls._lock:
            connections = list(cls._connections.values())
            cls._connections.clear()
        for connection in connections:
            connection.close()
