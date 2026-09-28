from pathlib import Path

import pytest

from app.knowledge.models import EvidencePack, SourceRecord
from app.knowledge.notebooklm import NotebookBundle
from app.knowledge.obsidian import ObsidianSource
from app.knowledge.service import KnowledgeService


@pytest.mark.asyncio
async def test_private_query_is_local_only(tmp_path):
    (tmp_path / "Architecture.md").write_text(
        "---\ntags: [private, evo]\n---\n# Architecture\nPrivate design uses local retrieval.",
        encoding="utf-8",
    )
    service = KnowledgeService(ObsidianSource(tmp_path))
    pack = await service.collect("private design", sensitivity="private", require_fresh=True)
    assert {source.connector for source in pack.sources} <= {"obsidian"}
    assert pack.policy == "local_only"
    assert pack.ready_to_answer is True


def test_evidence_pack_blocks_uncited_claims():
    pack = EvidencePack(question="q", sources=[], policy="source_first")
    assert pack.ready_to_answer is False


def test_obsidian_skips_symlink_outside_vault(tmp_path):
    outside = tmp_path.parent / "outside.md"
    outside.write_text("very-secret-marker", encoding="utf-8")
    try:
        (tmp_path / "linked.md").symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is not permitted on this Windows host")
    assert ObsidianSource(tmp_path).search("very-secret-marker") == []


def test_local_notion_markdown_export_is_identified(tmp_path):
    directory = tmp_path / "raw" / "notion"
    directory.mkdir(parents=True)
    (directory / "Roadmap.md").write_text("# Roadmap\nEvo launch plan", encoding="utf-8")
    result = ObsidianSource(tmp_path).search("launch plan")
    assert result[0].connector == "notion_export"
    assert result[0].uri.startswith("notion-export://")


def test_personal_notebook_bundle_never_calls_an_api(tmp_path):
    source = SourceRecord.from_text("obsidian", "obsidian://Note.md", "Note", "grounded text")
    bundle = NotebookBundle(tmp_path / "bundles", tmp_path / "imports")
    result = bundle.prepare("task-1", "What changed?", [source], sensitivity="private")
    assert result["state"] == "input_required"
    assert Path(result["bundle_path"]).joinpath("sources.json").is_file()
    assert "manual" in result["instructions"].lower()


def test_secret_notebook_bundle_is_blocked(tmp_path):
    bundle = NotebookBundle(tmp_path / "bundles", tmp_path / "imports")
    with pytest.raises(ValueError, match="secret"):
        bundle.prepare("task-1", "q", [], sensitivity="secret")
