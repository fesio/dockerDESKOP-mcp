# Source-first Brain policy

Evo MCP is the shared brain for supported assistants. Every source-dependent answer starts with
`brain_answer_context`. The client must stop and ask for sources when `ready_to_answer=false`.

- Obsidian is the private local source of truth.
- Notion is optional and sees only pages explicitly shared with the integration.
- In the personal no-API profile, export Notion pages as Markdown into `brain/raw/notion/`; Evo indexes
  them locally and identifies citations as `notion-export://...`.
- Fresh web material can be supplied by the calling assistant and must retain URL/date provenance.
- Personal NotebookLM has no automated connector here. `brain_prepare_notebook` creates a safe local
  bundle and returns `input_required`; the user imports it manually and saves the exported result in
  `brain/imports/notebooklm/` before calling `brain_resume_notebook`.
- When Evo runs in Docker, `scripts/export-notebooklm-bundles.ps1` copies prepared bundles to the
  local Brain. After saving the NotebookLM result, run `scripts/sync-brain.ps1` before resuming.
- Secret material is never exported to NotebookLM, Notion, web tools, logs, or model-hosted memory.

The reusable agent policy is in `AGENTS.md`.
