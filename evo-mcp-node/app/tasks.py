from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from time import time
from typing import Any


class TaskNotFound(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class TaskRecord:
    id: str
    owner: str
    operation: str
    arguments: dict[str, Any]
    state: str
    progress: int
    error: str | None
    cancel_requested: bool
    created_at: float
    updated_at: float

    def public(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("owner", None)
        value.pop("arguments", None)
        return value


Operation = Callable[[dict[str, Any], Callable[[], bool], Callable[[str], None]], Any]


class TaskStore:
    def __init__(self, database: str | Path, artifact_dir: str | Path, max_logs: int = 200) -> None:
        self.database = Path(database)
        self.artifact_dir = Path(artifact_dir)
        self.max_logs = max_logs
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, operation TEXT NOT NULL,
                    arguments TEXT NOT NULL, state TEXT NOT NULL, progress INTEGER NOT NULL,
                    result TEXT, error TEXT, cancel_requested INTEGER NOT NULL DEFAULT 0,
                    idempotency_key TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL,
                    UNIQUE(owner, operation, idempotency_key)
                );
                CREATE TABLE IF NOT EXISTS task_logs (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
                    created_at REAL NOT NULL, message TEXT NOT NULL
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _record(row: sqlite3.Row) -> TaskRecord:
        return TaskRecord(
            id=row["id"],
            owner=row["owner"],
            operation=row["operation"],
            arguments=json.loads(row["arguments"]),
            state=row["state"],
            progress=row["progress"],
            error=row["error"],
            cancel_requested=bool(row["cancel_requested"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create(
        self, owner: str, operation: str, arguments: dict[str, Any], idempotency_key: str
    ) -> TaskRecord:
        if not idempotency_key:
            raise ValueError("idempotency_key is required")
        now = time()
        task_id = str(uuid.uuid4())
        with self._connect() as connection:
            try:
                connection.execute(
                    "INSERT INTO tasks VALUES (?, ?, ?, ?, 'working', 0, NULL, NULL, 0, ?, ?, ?)",
                    (task_id, owner, operation, json.dumps(arguments), idempotency_key, now, now),
                )
            except sqlite3.IntegrityError:
                row = connection.execute(
                    "SELECT * FROM tasks WHERE owner=? AND operation=? AND idempotency_key=?",
                    (owner, operation, idempotency_key),
                ).fetchone()
                if row is None:
                    raise
                return self._record(row)
        return self.get(owner, task_id)

    def get(self, owner: str, task_id: str) -> TaskRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM tasks WHERE owner=? AND id=?", (owner, task_id)
            ).fetchone()
        if row is None:
            raise TaskNotFound("task was not found")
        return self._record(row)

    def list(self, owner: str, limit: int = 50) -> list[TaskRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM tasks WHERE owner=? ORDER BY created_at DESC LIMIT ?",
                (owner, max(1, min(limit, 200))),
            ).fetchall()
        return [self._record(row) for row in rows]

    def transition(
        self,
        owner: str,
        task_id: str,
        state: str,
        *,
        progress: int | None = None,
        result: Any = None,
        error: str | None = None,
    ) -> TaskRecord:
        current = self.get(owner, task_id)
        allowed = {
            "working": {"input_required", "completed", "failed", "cancelled"},
            "input_required": {"working", "failed", "cancelled"},
        }
        if state != current.state and state not in allowed.get(current.state, set()):
            raise ValueError(f"invalid task transition {current.state!r} -> {state!r}")
        encoded = None if result is None else json.dumps(result, ensure_ascii=False)
        with self._connect() as connection:
            connection.execute(
                "UPDATE tasks SET state=?, progress=?, result=?, error=?, updated_at=? WHERE owner=? AND id=?",
                (
                    state,
                    current.progress if progress is None else max(0, min(progress, 100)),
                    encoded,
                    error,
                    time(),
                    owner,
                    task_id,
                ),
            )
        return self.get(owner, task_id)

    def append_log(self, owner: str, task_id: str, message: str) -> None:
        self.get(owner, task_id)
        clean = message.replace("\x00", "")[:4000]
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO task_logs(task_id, created_at, message) VALUES (?, ?, ?)",
                (task_id, time(), clean),
            )
            connection.execute(
                "DELETE FROM task_logs WHERE task_id=? AND seq NOT IN "
                "(SELECT seq FROM task_logs WHERE task_id=? ORDER BY seq DESC LIMIT ?)",
                (task_id, task_id, self.max_logs),
            )

    def logs(self, owner: str, task_id: str) -> list[dict[str, Any]]:
        self.get(owner, task_id)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT created_at, message FROM task_logs WHERE task_id=? ORDER BY seq", (task_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    def result(self, owner: str, task_id: str) -> Any:
        self.get(owner, task_id)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT result FROM tasks WHERE owner=? AND id=?", (owner, task_id)
            ).fetchone()
        return None if row is None or row["result"] is None else json.loads(row["result"])

    def request_cancel(self, owner: str, task_id: str) -> TaskRecord:
        current = self.get(owner, task_id)
        if current.state not in {"working", "input_required"}:
            return current
        with self._connect() as connection:
            connection.execute(
                "UPDATE tasks SET cancel_requested=1, updated_at=? WHERE owner=? AND id=?",
                (time(), owner, task_id),
            )
        return self.get(owner, task_id)

    def recover_interrupted(self) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE tasks SET state='failed', error='server restart interrupted operation', "
                "updated_at=? WHERE state='working'",
                (time(),),
            )
            return cursor.rowcount


class TaskRunner:
    def __init__(self, store: TaskStore, operations: dict[str, Operation], workers: int = 2) -> None:
        self.store = store
        self.operations = dict(operations)
        self.executor = ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="evo-task")
        self._futures: dict[str, Future[Any]] = {}
        self._lock = threading.Lock()

    def start(
        self, owner: str, operation: str, arguments: dict[str, Any], idempotency_key: str
    ) -> TaskRecord:
        if operation not in self.operations:
            raise ValueError(f"operation {operation!r} is not registered")
        task = self.store.create(owner, operation, arguments, idempotency_key)
        with self._lock:
            if task.state == "working" and task.id not in self._futures:
                self._futures[task.id] = self.executor.submit(self._run, task)
        return task

    def _run(self, task: TaskRecord) -> None:
        cancelled = lambda: self.store.get(task.owner, task.id).cancel_requested
        log = lambda message: self.store.append_log(task.owner, task.id, message)
        try:
            result = self.operations[task.operation](task.arguments, cancelled, log)
            state = "cancelled" if cancelled() else "completed"
            self.store.transition(task.owner, task.id, state, progress=100, result=result)
        except Exception as exc:  # noqa: BLE001 - task boundary must persist every failure
            self.store.transition(task.owner, task.id, "failed", error=str(exc)[:4000])

    def wait(self, owner: str, task_id: str, timeout: float | None = None) -> TaskRecord:
        self.store.get(owner, task_id)
        with self._lock:
            future = self._futures.get(task_id)
        if future is not None:
            future.result(timeout=timeout)
        return self.store.get(owner, task_id)
