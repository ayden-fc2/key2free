from __future__ import annotations

from datetime import datetime

from app.dtos.data_asset_dto import TaskDTO
from app.repositories.duckdb_repository import DuckDBRepository


class TaskRepository:
    MAX_LOG_LINES = 2000

    def __init__(self) -> None:
        self.duckdb = DuckDBRepository()
        self._ensure_task_columns()

    def _ensure_task_columns(self) -> None:
        with self.duckdb.connect(read_only=False) as connection:
            connection.execute(
                "alter table meta.my_task add column if not exists created_at timestamp"
            )
            connection.execute(
                "alter table meta.my_task add column if not exists updated_at timestamp"
            )
            connection.execute(
                """
                update meta.my_task
                set created_at = coalesce(created_at, current_timestamp),
                    updated_at = coalesce(updated_at, current_timestamp)
                where created_at is null or updated_at is null
                """
            )

    def get_running_task_by_type(self, task_type: str) -> TaskDTO | None:
        with self.duckdb.connect(read_only=True) as connection:
            row = connection.execute(
                """
                select id, type, logs, status, created_at, updated_at
                from meta.my_task
                where type = ? and status = 'running'
                order by id desc
                limit 1
                """,
                [task_type],
            ).fetchone()
        return self._to_task(row)

    def finish_running_tasks_by_type(self, task_type: str, message: str) -> int:
        with self.duckdb.connect(read_only=False) as connection:
            rows = connection.execute(
                """
                select id, logs
                from meta.my_task
                where type = ? and status = 'running'
                order by id
                """,
                [task_type],
            ).fetchall()
            for task_id, logs in rows:
                connection.execute(
                    """
                    update meta.my_task
                    set logs = ?, status = 'error', updated_at = current_timestamp
                    where id = ?
                    """,
                    [
                        self._trim_logs((logs or "") + self._format_log(message)),
                        task_id,
                    ],
                )
        return len(rows)

    def get_latest_task_by_type(self, task_type: str) -> TaskDTO | None:
        with self.duckdb.connect(read_only=True) as connection:
            row = connection.execute(
                """
                select id, type, logs, status, created_at, updated_at
                from meta.my_task
                where type = ?
                order by id desc
                limit 1
                """,
                [task_type],
            ).fetchone()
        return self._to_task(row)

    def get_task(self, task_id: int) -> TaskDTO | None:
        with self.duckdb.connect(read_only=True) as connection:
            row = connection.execute(
                """
                select id, type, logs, status, created_at, updated_at
                from meta.my_task
                where id = ?
                """,
                [task_id],
            ).fetchone()
        return self._to_task(row)

    def list_tasks_by_type(self, task_type: str, limit: int = 100) -> list[TaskDTO]:
        normalized_limit = max(1, min(limit, 500))
        with self.duckdb.connect(read_only=True) as connection:
            rows = connection.execute(
                """
                select id, type, logs, status, created_at, updated_at
                from meta.my_task
                where type = ?
                order by id desc
                limit ?
                """,
                [task_type, normalized_limit],
            ).fetchall()
        return [task for row in rows for task in [self._to_task(row)] if task is not None]

    def create_task(self, task_type: str, initial_log: str) -> TaskDTO:
        with self.duckdb.connect(read_only=False) as connection:
            row = connection.execute(
                """
                insert into meta.my_task(type, logs, status, created_at, updated_at)
                values (?, ?, 'running', current_timestamp, current_timestamp)
                returning id, type, logs, status, created_at, updated_at
                """,
                [task_type, self._format_log(initial_log)],
            ).fetchone()
        task = self._to_task(row)
        if task is None:
            raise RuntimeError("failed to create task")
        return task

    def reset_latest_task(self, task_type: str, initial_log: str) -> TaskDTO:
        with self.duckdb.connect(read_only=False) as connection:
            existing = connection.execute(
                """
                select id
                from meta.my_task
                where type = ?
                order by id desc
                limit 1
                """,
                [task_type],
            ).fetchone()
            if existing is None:
                row = connection.execute(
                    """
                    insert into meta.my_task(type, logs, status, created_at, updated_at)
                    values (?, ?, 'running', current_timestamp, current_timestamp)
                    returning id, type, logs, status, created_at, updated_at
                    """,
                    [task_type, self._format_log(initial_log)],
                ).fetchone()
            else:
                row = connection.execute(
                    """
                    update meta.my_task
                    set logs = ?, status = 'running', updated_at = current_timestamp
                    where id = ?
                    returning id, type, logs, status, created_at, updated_at
                    """,
                    [self._format_log(initial_log), existing[0]],
                ).fetchone()
        task = self._to_task(row)
        if task is None:
            raise RuntimeError("failed to reset task")
        return task

    def append_log(self, task_id: int, message: str) -> None:
        with self.duckdb.connect(read_only=False) as connection:
            row = connection.execute(
                """
                select logs
                from meta.my_task
                where id = ?
                """,
                [task_id],
            ).fetchone()
            logs = "" if row is None else row[0] or ""
            connection.execute(
                """
                update meta.my_task
                set logs = ?, updated_at = current_timestamp
                where id = ?
                """,
                [self._trim_logs(logs + self._format_log(message)), task_id],
            )

    def finish_task(self, task_id: int, status: str, message: str) -> None:
        if status not in {"success", "error"}:
            raise ValueError(f"invalid task finish status: {status}")
        with self.duckdb.connect(read_only=False) as connection:
            row = connection.execute(
                """
                select logs
                from meta.my_task
                where id = ?
                """,
                [task_id],
            ).fetchone()
            logs = "" if row is None else row[0] or ""
            connection.execute(
                """
                update meta.my_task
                set logs = ?, status = ?, updated_at = current_timestamp
                where id = ?
                """,
                [self._trim_logs(logs + self._format_log(message)), status, task_id],
            )

    def _format_log(self, message: str) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"[{timestamp}] {message}\n"

    def _trim_logs(self, logs: str) -> str:
        lines = logs.splitlines()
        if len(lines) <= self.MAX_LOG_LINES:
            return logs
        return "\n".join(lines[-self.MAX_LOG_LINES :]) + "\n"

    def _to_task(self, row: tuple | None) -> TaskDTO | None:
        if row is None:
            return None
        task_id, task_type, logs, status, *timestamps = row
        created_at = timestamps[0] if len(timestamps) > 0 else None
        updated_at = timestamps[1] if len(timestamps) > 1 else None
        return TaskDTO(
            id=task_id,
            type=task_type,
            logs=logs or "",
            status=status,
            created_at=None if created_at is None else str(created_at),
            updated_at=None if updated_at is None else str(updated_at),
        )
