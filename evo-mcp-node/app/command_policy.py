from __future__ import annotations

from pathlib import Path


class CommandPolicyError(ValueError):
    pass


class CommandPolicy:
    _shells = frozenset({"sh", "bash", "zsh", "cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "pwsh.exe"})
    _inline_flags = frozenset({"-c", "-e", "--eval"})
    _blocked_git = frozenset({"push", "clean", "reset", "restore", "checkout", "rebase", "tag"})
    _blocked_docker = frozenset({"rm", "rmi", "prune", "kill", "stop", "restart"})

    def validate(self, argv: list[str], workspace: Path, docker_enabled: bool) -> None:
        if not argv:
            raise CommandPolicyError("empty command is blocked")
        command = Path(argv[0]).name.lower()
        args = [item.lower() for item in argv[1:]]
        if command in self._shells:
            raise CommandPolicyError("shell execution is blocked")
        if command in {"python", "python.exe", "python3", "node", "node.exe"} and any(
            item in self._inline_flags for item in args
        ):
            raise CommandPolicyError("inline code execution is blocked")
        if command in {"git", "git.exe"} and args and args[0] in self._blocked_git:
            raise CommandPolicyError(f"git {args[0]} is blocked in the generic runner")
        if command in {"docker", "docker.exe"}:
            if not docker_enabled:
                raise CommandPolicyError("docker access is blocked unless explicitly enabled")
            if any(item in self._blocked_docker for item in args):
                raise CommandPolicyError("destructive docker command is blocked in the generic runner")
            if args[:2] == ["compose", "down"] or "--volumes" in args or "-v" in args:
                raise CommandPolicyError("destructive docker compose command is blocked")
        for argument in argv[1:]:
            if argument.startswith("-") or "://" in argument:
                continue
            candidate = Path(argument)
            if candidate.is_absolute():
                try:
                    candidate.resolve(strict=False).relative_to(workspace)
                except ValueError as exc:
                    raise CommandPolicyError("absolute path outside workspace is blocked") from exc
