from __future__ import annotations

import re
from pathlib import Path

from app.knowledge.models import SourceRecord


class ObsidianSource:
    def __init__(self, vault: str | Path) -> None:
        self.vault = Path(vault).expanduser().resolve()

    def search(self, query: str, limit: int = 20) -> list[SourceRecord]:
        if not query.strip() or not self.vault.is_dir():
            return []
        terms = [term.lower() for term in re.findall(r"[\w-]+", query) if len(term) > 1]
        scored: list[tuple[int, SourceRecord]] = []
        for candidate in self.vault.rglob("*.md"):
            try:
                path = candidate.resolve(strict=True)
                path.relative_to(self.vault)
                if path.stat().st_size > 2_000_000:
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                continue
            haystack = f"{path.stem}\n{text}".lower()
            score = sum(haystack.count(term) for term in terms)
            if score:
                relative = path.relative_to(self.vault).as_posix()
                connector = "notion_export" if relative.startswith("raw/notion/") else "obsidian"
                scheme = "notion-export" if connector == "notion_export" else "obsidian"
                scored.append(
                    (
                        score,
                        SourceRecord.from_text(
                            connector,
                            f"{scheme}://{relative}",
                            path.stem,
                            text,
                            {"path": relative},
                        ),
                    )
                )
        scored.sort(key=lambda item: (-item[0], item[1].uri))
        return [record for _, record in scored[: max(1, min(limit, 100))]]
