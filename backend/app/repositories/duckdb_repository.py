from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb


class DuckDBRepository:
    def __init__(self, db_path: Path | None = None) -> None:
        root_dir = Path(__file__).resolve().parents[3]
        self.db_path = db_path or root_dir / "data" / "data.duckdb"

    def connect(self, *, read_only: bool = True) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(self.db_path), read_only=read_only)

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
