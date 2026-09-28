from pathlib import Path

import pytest

from app.tasks import TaskNotFound, TaskRunner, TaskStore


def make_store(tmp_path: Path) -> TaskStore:
    return TaskStore(tmp_path / "tasks.sqlite3", tmp_path / "artifacts")


def test_task_is_owner_isolated(tmp_path):
    store = make_store(tmp_path)
    task = store.create("owner-a", "programmer.test", {}, "key-1")
    assert store.get("owner-a", task.id).id == task.id
    with pytest.raises(TaskNotFound):
        store.get("owner-b", task.id)


def test_restart_marks_working_task_failed(tmp_path):
    store = make_store(tmp_path)
    task = store.create("local", "programmer.lint", {}, "key")
    store.recover_interrupted()
    recovered = store.get("local", task.id)
    assert recovered.state == "failed"
    assert "restart" in (recovered.error or "")


def test_idempotency_returns_original_task(tmp_path):
    store = make_store(tmp_path)
    first = store.create("local", "programmer.test", {"cwd": "."}, "same")
    second = store.create("local", "programmer.test", {"cwd": "."}, "same")
    assert second.id == first.id


def test_runner_completes_registered_operation(tmp_path):
    store = make_store(tmp_path)
    runner = TaskRunner(store, {"demo": lambda args, cancelled, log: {"value": args["value"]}})
    task = runner.start("local", "demo", {"value": 7}, "run-once")
    finished = runner.wait("local", task.id, timeout=5)
    assert finished.state == "completed"
    assert store.result("local", task.id) == {"value": 7}


def test_runner_rejects_unknown_operation(tmp_path):
    runner = TaskRunner(make_store(tmp_path), {})
    with pytest.raises(ValueError, match="not registered"):
        runner.start("local", "shell.anything", {}, "x")
