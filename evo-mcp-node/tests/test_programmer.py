import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

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
    assert ws.search("ok")[0]["path"] == "src/demo.py"


def test_git_status_and_diff_are_allowed_in_read_profile(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "demo.txt").write_text("x\n", encoding="utf-8")
    ws = make_workspace(tmp_path, "read")
    assert ws.git_status()["returncode"] == 0
    assert ws.git_diff()["returncode"] == 0
