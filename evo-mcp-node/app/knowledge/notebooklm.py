from __future__ import annotations

import json
from pathlib import Path

from app.knowledge.models import SourceRecord


class NotebookBundle:
    def __init__(self, root: str | Path, import_root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.import_root = Path(import_root).expanduser().resolve()

    def prepare(
        self,
        task_id: str,
        question: str,
        sources: list[SourceRecord],
        *,
        sensitivity: str = "private",
    ) -> dict[str, str]:
        if sensitivity == "secret":
            raise ValueError("secret content cannot be exported to personal NotebookLM")
        safe_id = "".join(ch for ch in task_id if ch.isalnum() or ch in "-_")
        if not safe_id:
            raise ValueError("invalid task id")
        destination = (self.root / safe_id).resolve()
        destination.relative_to(self.root)
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "question.md").write_text(f"# Question\n\n{question}\n", encoding="utf-8")
        (destination / "sources.json").write_text(
            json.dumps([source.to_dict() for source in sources], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        urls = [source.uri for source in sources if source.uri.startswith(("http://", "https://"))]
        (destination / "urls.txt").write_text("\n".join(urls), encoding="utf-8")
        for index, source in enumerate(sources, 1):
            (destination / f"source-{index:03d}.md").write_text(
                f"# {source.title}\n\nSource: {source.uri}\n\n{source.excerpt}\n", encoding="utf-8"
            )
        return {
            "state": "input_required",
            "bundle_path": str(destination),
            "instructions": (
                "Manual step: import this bundle into personal NotebookLM, ask the question, "
                "then export the answer into the configured NotebookLM imports folder."
            ),
        }

    def resume(self, filename: str) -> SourceRecord:
        path = (self.import_root / filename).resolve(strict=True)
        path.relative_to(self.import_root)
        if path.suffix.lower() not in {".md", ".txt"}:
            raise ValueError("NotebookLM result must be Markdown or text")
        return SourceRecord.from_text("notebooklm", f"notebooklm://{path.name}", path.stem, path.read_text(encoding="utf-8"))
