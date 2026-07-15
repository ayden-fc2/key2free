from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4


class OperationLogStore:
    def __init__(self, path: Path | None = None) -> None:
        configured_path = os.getenv("OPERATION_LOG_PATH", "/app/logs/operations.jsonl")
        self.path = Path(path or configured_path)
        self._lock = RLock()

    def append(
        self,
        *,
        operation: str,
        status: str,
        source: str,
        message: str,
        details: dict[str, Any] | None = None,
        operation_id: str | None = None,
    ) -> dict[str, Any]:
        record = {
            "id": operation_id or uuid4().hex,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "operation": operation,
            "status": status,
            "source": source,
            "message": message,
            "details": details or {},
        }
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._rotate_if_needed()
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        return record

    def list(
        self,
        *,
        limit: int = 100,
        operation: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with self._lock:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        records: list[dict[str, Any]] = []
        for line in reversed(lines):
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if operation is not None and record.get("operation") != operation:
                continue
            if status is not None and record.get("status") != status:
                continue
            records.append(record)
            if len(records) >= limit:
                break
        return records

    def _rotate_if_needed(self) -> None:
        maximum_bytes = int(os.getenv("OPERATION_LOG_MAX_BYTES", str(20 * 1024 * 1024)))
        backup_count = max(1, int(os.getenv("OPERATION_LOG_BACKUP_COUNT", "5")))
        if not self.path.exists() or self.path.stat().st_size < maximum_bytes:
            return
        Path(f"{self.path}.{backup_count}").unlink(missing_ok=True)
        for index in range(backup_count - 1, 0, -1):
            source = Path(f"{self.path}.{index}")
            destination = Path(f"{self.path}.{index + 1}")
            if source.exists():
                source.replace(destination)
        self.path.replace(Path(f"{self.path}.1"))


operation_log_store = OperationLogStore()
