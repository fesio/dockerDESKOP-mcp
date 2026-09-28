from __future__ import annotations

from app.knowledge.models import EvidencePack, SourceRecord
from app.knowledge.notion import NotionSource
from app.knowledge.obsidian import ObsidianSource


class KnowledgeService:
    def __init__(self, obsidian: ObsidianSource, notion: NotionSource | None = None) -> None:
        self.obsidian = obsidian
        self.notion = notion

    async def collect(
        self,
        question: str,
        *,
        sensitivity: str = "private",
        require_fresh: bool = False,
        provided_sources: list[SourceRecord] | None = None,
    ) -> EvidencePack:
        if sensitivity not in {"public", "private", "secret"}:
            raise ValueError("sensitivity must be public, private, or secret")
        sources = self.obsidian.search(question)
        policy = "local_only" if sensitivity in {"private", "secret"} else "source_first"
        if sensitivity == "public" and self.notion is not None:
            sources.extend(await self.notion.search(question))
        sources.extend(provided_sources or [])
        unique = {source.content_hash: source for source in sources}
        gaps: list[str] = []
        if not unique:
            gaps.append("no matching sources")
        if require_fresh and sensitivity == "public" and not any(
            source.connector in {"notion", "provided"} for source in unique.values()
        ):
            gaps.append("fresh external source required")
        return EvidencePack(question, list(unique.values()), policy, gaps=gaps)
