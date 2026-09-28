import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from app.approvals import create_approval_token
from app.audit import AuditLogger
from app.config import Settings
from app.programmer import ProgrammerError, ProgrammerWorkspace


def make_workspace(tmp_path: Path, profile: str = "standard") -> ProgrammerWorkspace:
    settings = replace(
        Settings.from_env(),
        programmer_workspace=str(tmp_path),
        programmer_profile=profile,
        audit_log_path=str(tmp_path / "audit.jsonl"),
    )
    return ProgrammerWorkspace(settings, AuditLogger(settings.audit_log_path))


def test_path_jail_blocks_parent_escape(tmp_path):
    ws = make_workspace(tmp_path)
    with pytest.raises(ProgrammerError, match="escapes"):
        ws.path("../outside.txt")


def test_read_profile_blocks_write(tmp_path):
    ws = make_workspace(tmp_path, "read")
    with pytest.raises(ProgrammerError, match="requires 'standard'"):
        ws.write("x.txt", "no")


def test_standard_profile_reads_and_writes(tmp_path):
    ws = make_workspace(tmp_path, "standard")
    ws.write("src/demo.py", "print('ok')\n")
    assert "print" in ws.read("src/demo.py")
    assert any(row["path"] == "src/demo.py" for row in ws.search("ok"))


def test_git_status_and_diff_are_allowed_in_read_profile(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "demo.txt").write_text("x\n", encoding="utf-8")
    ws = make_workspace(tmp_path, "read")
    assert ws.git_status()["returncode"] == 0
    assert ws.git_diff()["returncode"] == 0


@pytest.mark.parametrize(
    "argv",
    [
        ["git", "push", "origin", "main"],
        ["git", "clean", "-fdx"],
        ["python", "-c", "print('unsafe')"],
        ["node", "--eval", "process.exit()"],
        ["docker", "system", "prune", "-af"],
    ],
)
def test_generic_runner_rejects_destructive_bypasses(tmp_path, argv):
    ws = make_workspace(tmp_path, "standard")
    with pytest.raises(ProgrammerError, match="blocked"):
        ws.run(argv)


def test_search_skips_symlink_that_leaves_workspace(tmp_path):
    outside = tmp_path.parent / "outside-secret.txt"
    outside.write_text("outside-secret", encoding="utf-8")
    link = tmp_path / "linked.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is not permitted on this Windows host")
    assert make_workspace(tmp_path, "read").search("outside-secret") == []


def test_dedicated_git_push_accepts_scoped_approval(tmp_path, monkeypatch):
    secret = "x" * 32
    settings = replace(
        Settings.from_env(),
        programmer_workspace=str(tmp_path),
        programmer_profile="autonomous",
        programmer_approval_secret=secret,
        approval_db_path=str(tmp_path / "approvals.sqlite3"),
        audit_log_path=str(tmp_path / "audit.jsonl"),
    )
    ws = ProgrammerWorkspace(settings, AuditLogger(settings.audit_log_path))
    token = create_approval_token(secret, "git.push", "feature", 60)
    monkeypatch.setattr("app.programmer.shutil.which", lambda _: "git")
    monkeypatch.setattr(
        "app.programmer.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "ok", ""),
    )
    assert ws.git_push("feature", token)["returncode"] == 0


def test_dedicated_test_tool_uses_fixed_argv(tmp_path, monkeypatch):
    ws = make_workspace(tmp_path)
    calls = []
    monkeypatch.setattr(
        ProgrammerWorkspace,
        "_run",
        lambda self, argv, cwd=".", **kwargs: calls.append((argv, cwd)) or {},
    )
    ws.test("src")
    assert calls == [(["uv", "run", "pytest", "-q"], "src")]


def test_dedicated_docker_tool_has_fixed_action(tmp_path, monkeypatch):
    ws = make_workspace(tmp_path)
    calls = []
    monkeypatch.setattr(
        ProgrammerWorkspace, "_run", lambda self, argv, cwd=".", **kwargs: calls.append(argv) or {}
    )
    ws.docker_build("project:test")
    assert calls == [["docker", "build", "--tag", "project:test", "."]]
