# Evo MCP working policy

Use the `evo` MCP server as the project control plane.

Before answering a source-dependent question, call `brain_answer_context`. Continue only when
`ready_to_answer` is true and cite the returned source URIs for material claims. Private and secret
questions stay local to Obsidian. Notion may be used only for pages explicitly shared with its
integration. Personal NotebookLM is always a manual handoff: call `brain_prepare_notebook`, stop at
`input_required`, and resume with `brain_resume_notebook` after the user exports a result.

For code work, inspect before writing and prefer dedicated `programmer_*` tools. Use `task_start` for
tests, lint, type checking, Docker builds, or Compose startup that may take time. Never bypass approval
tokens through the generic command runner. Destructive filesystem actions and Git pushes require a
short-lived, exact-target approval generated locally by the user.
