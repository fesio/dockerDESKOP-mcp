from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from app.audit import AuditLogger
from app.config import Settings


class ProgrammerError(RuntimeError):
    pass


PROFILE_RANK = {"read": 0, "standard": 1, "autonomous": 2}


@dataclass(slots=True)
class ProgrammerWorkspace:
    settings: Settings
    audit: AuditLogger

    @property
    def root(self) -> Path:
        root = Path(self.settings.programmer_workspace).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _require(self, required: str) -> None:
        if PROFILE_RANK[self.settings.programmer_profile] < PROFILE_RANK[required]:
            raise ProgrammerError(
                f"PROGRAMMER_PROFILE={self.settings.programmer_profile!r} does not allow this action; "
                f"requires {required!r}"
            )

    def _approve(self, supplied: str) -> None:
        self._require("autonomous")
        expected = self.settings.programmer_approval_secret
        if len(expected) < 16 or supplied != expected:
            raise ProgrammerError("destructive action requires the local PROGRAMMER_APPROVAL_SECRET")

    def path(self, relative: str = ".") -> Path:
        candidate = Path(relative)
        if candidate.is_absolute():
            raise ProgrammerError("absolute paths are not allowed; paths are relative to /workspace")
        resolved = (self.root / candidate).resolve(strict=False)
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise ProgrammerError("path escapes the configured workspace") from exc
        return resolved

    def tree(self, relative: str = ".", max_depth: int = 3, max_entries: int = 250) -> list[dict[str, object]]:
        start = self.path(relative)
        if not start.exists():
            raise ProgrammerError("path does not exist")
        output: list[dict[str, object]] = []
        start_depth = len(start.parts)
        for current, dirs, files in os.walk(start):
            current_path = Path(current)
            depth = len(current_path.parts) - start_depth
            if depth >= max_depth:
                dirs[:] = []
            dirs[:] = sorted(d for d in dirs if d not in {".git", ".venv", "node_modules", "__pycache__"})
            for name, kind in [(d, "dir") for d in dirs] + [(f, "file") for f in sorted(files)]:
                p = current_path / name
                try:
                    rel = p.relative_to(self.root).as_posix()
                except ValueError:
                    continue
                entry: dict[str, object] = {"path": rel, "kind": kind}
                if kind == "file":
                    try:
                        entry["size"] = p.stat().st_size
                    except OSError:
                        entry["size"] = None
                output.append(entry)
                if len(output) >= max_entries:
                    return output
        return output

    def read(self, relative: str, max_chars: int = 120_000) -> str:
        path = self.path(relative)
        if not path.is_file():
            raise ProgrammerError("file does not exist")
        if path.stat().st_size > self.settings.programmer_max_file_bytes:
            raise ProgrammerError("file exceeds PROGRAMMER_MAX_FILE_BYTES")
        return path.read_text(encoding="utf-8", errors="replace")[:max_chars]

    def write(self, relative: str, content: str, overwrite: bool = True) -> dict[str, object]:
        self._require("standard")
        encoded = content.encode("utf-8")
        if len(encoded) > self.settings.programmer_max_file_bytes:
            raise ProgrammerError("content exceeds PROGRAMMER_MAX_FILE_BYTES")
        path = self.path(relative)
        if path.exists() and not overwrite:
            raise ProgrammerError("file exists and overwrite=false")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(encoded)
        self.audit.write("programmer.write", "ok", path=relative, bytes=len(encoded))
        return {"path": relative, "bytes": len(encoded)}

    def delete(self, relative: str, approval: str) -> dict[str, object]:
        self._approve(approval)
        path = self.path(relative)
        if not path.exists():
            return {"path": relative, "deleted": False}
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        self.audit.write("programmer.delete", "ok", path=relative)
        return {"path": relative, "deleted": True}

    def search(self, query: str, relative: str = ".", max_results: int = 50) -> list[dict[str, object]]:
        if not query:
            return []
        base = self.path(relative)
        results: list[dict[str, object]] = []
        candidates: Iterable[Path] = [base] if base.is_file() else base.rglob("*")
        for path in candidates:
            if not path.is_file() or any(part in {".git", ".venv", "node_modules", "__pycache__"} for part in path.parts):
                continue
            try:
                if path.stat().st_size > self.settings.programmer_max_file_bytes:
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for line_no, line in enumerate(text.splitlines(), 1):
                if query.lower() in line.lower():
                    results.append(
                        {
                            "path": path.relative_to(self.root).as_posix(),
                            "line": line_no,
                            "text": line[:500],
                        }
                    )
                    if len(results) >= max_results:
                        return results
        return results

    def _run(
        self,
        argv: list[str],
        cwd: str = ".",
        *,
        required_profile: str = "standard",
    ) -> dict[str, object]:
        self._require(required_profile)
        if not argv:
            raise ProgrammerError("argv must not be empty")
        command = Path(argv[0]).name
        if command not in self.settings.programmer_allowed_commands:
            raise ProgrammerError(f"command {command!r} is not in PROGRAMMER_ALLOWED_COMMANDS")
        if command == "docker" and not self.settings.programmer_allow_docker:
            raise ProgrammerError("docker access is disabled; use compose.host-tools.yaml explicitly")
        if shutil.which(argv[0]) is None:
            raise ProgrammerError(f"command {argv[0]!r} is not installed in the MCP container")
        run_cwd = self.path(cwd)
        if not run_cwd.is_dir():
            raise ProgrammerError("cwd is not a directory")
        safe_env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": "/tmp",
            "LANG": os.environ.get("LANG", "C.UTF-8"),
            "PYTHONUNBUFFERED": "1",
        }
        try:
            completed = subprocess.run(
                argv,
                cwd=run_cwd,
                env=safe_env,
                capture_output=True,
                text=True,
                timeout=self.settings.programmer_command_timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            self.audit.write("programmer.command", "timeout", command=command, cwd=cwd)
            raise ProgrammerError(f"command exceeded {self.settings.programmer_command_timeout}s timeout") from exc
        result = {
            "argv": argv,
            "cwd": cwd,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-80_000:],
            "stderr": completed.stderr[-40_000:],
        }
        self.audit.write("programmer.command", "ok", command=command, cwd=cwd, returncode=completed.returncode)
        return result

    def run(self, argv: list[str], cwd: str = ".") -> dict[str, object]:
        return self._run(argv, cwd, required_profile="standard")

    def git_status(self) -> dict[str, object]:
        return self._run(["git", "status", "--short", "--branch"], required_profile="read")

    def git_diff(self, staged: bool = False) -> dict[str, object]:
        argv = ["git", "diff"] + (["--cached"] if staged else [])
        return self._run(argv, required_profile="read")

    def git_branch(self, name: str) -> dict[str, object]:
        self._require("standard")
        if not name or any(ch.isspace() for ch in name):
            raise ProgrammerError("branch name must be non-empty and contain no whitespace")
        return self.run(["git", "switch", "-c", name])

    def git_commit(self, message: str, paths: list[str]) -> dict[str, object]:
        self._require("standard")
        if not message.strip():
            raise ProgrammerError("commit message is required")
        if not paths:
            raise ProgrammerError("explicit paths are required; blanket git add is disabled")
        safe = [self.path(p).relative_to(self.root).as_posix() for p in paths]
        add_result = self.run(["git", "add", "--", *safe])
        if add_result["returncode"] != 0:
            return add_result
        return self.run(["git", "commit", "-m", message])

    def git_push(self, branch: str, approval: str) -> dict[str, object]:
        self._approve(approval)
        if not branch or any(ch.isspace() for ch in branch):
            raise ProgrammerError("invalid branch name")
        return self.run(["git", "push", "origin", branch])
