from __future__ import annotations

from datetime import datetime

from app.dtos.data_asset_dto import TaskDTO
from app.repositories.duckdb_repository import DuckDBRepository


class TaskRepository:
    MAX_LOG_LINES = 2000

    def __init__(self) -> None:
        self.duckdb = DuckDBRepository()

    def get_running_task_by_type(self, task_type: str) -> TaskDTO | None:
        with self.duckdb.connect(read_only=True) as connection:
            row = connection.execute(
                """
                select id, type, logs, status
                from meta.my_task
                where type = ? and status = 'running'
                order by id desc
                limit 1
                """,
                [task_type],
            ).fetchone()
        return self._to_task(row)

    def get_latest_task_by_type(self, task_type: str) -> TaskDTO | None:
        with self.duckdb.connect(read_only=True) as connection:
            row = connection.execute(
                """
                select id, type, logs, status
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
                select id, type, logs, status
                from meta.my_task
                where id = ?
                """,
                [task_id],
            ).fetchone()
        return self._to_task(row)

    def create_task(self, task_type: str, initial_log: str) -> TaskDTO:
        with self.duckdb.connect(read_only=False) as connection:
            row = connection.execute(
                """
                insert into meta.my_task(type, logs, status)
                values (?, ?, 'running')
                returning id, type, logs, status
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
                    insert into meta.my_task(type, logs, status)
                    values (?, ?, 'running')
                    returning id, type, logs, status
                    """,
                    [task_type, self._format_log(initial_log)],
                ).fetchone()
            else:
                row = connection.execute(
                    """
                    update meta.my_task
                    set logs = ?, status = 'running'
                    where id = ?
                    returning id, type, logs, status
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
                set logs = ?
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
                set logs = ?, status = ?
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
        task_id, task_type, logs, status = row
        return TaskDTO(
            id=task_id,
            type=task_type,
            logs=logs or "",
            status=status,
        )
