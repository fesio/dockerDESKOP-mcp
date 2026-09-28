from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any


@dataclass(frozen=True, slots=True)
class SourceRecord:
    connector: str
    uri: str
    title: str
    excerpt: str
    retrieved_at: str
    content_hash: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_text(
        cls, connector: str, uri: str, title: str, text: str, metadata: dict[str, Any] | None = None
    ) -> SourceRecord:
        return cls(
            connector=connector,
            uri=uri,
            title=title,
            excerpt=text[:4000],
            retrieved_at=datetime.now(UTC).isoformat(),
            content_hash=sha256(text.encode("utf-8")).hexdigest(),
            metadata=metadata or {},
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class EvidencePack:
    question: str
    sources: list[SourceRecord]
    policy: str
    conflicts: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)

    @property
    def ready_to_answer(self) -> bool:
        return bool(self.sources) and not self.conflicts and not self.gaps

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "sources": [source.to_dict() for source in self.sources],
            "policy": self.policy,
            "conflicts": self.conflicts,
            "gaps": self.gaps,
            "ready_to_answer": self.ready_to_answer,
        }
