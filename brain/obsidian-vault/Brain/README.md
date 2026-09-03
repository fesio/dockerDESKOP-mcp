# Brain vault structure

This directory is a safe seed for an Obsidian vault. User notes and secrets are
not committed to Git.

Recommended folders:

- `decision/` — approved architectural and business decisions.
- `lesson/` — reusable lessons learned from completed work.
- `project/` — current project state and constraints.
- `reference/` — curated technical references.
- `task_result/` — verified execution outcomes.
- `preference/` — stable user preferences.
- `Programming/Languages/` — one profile per programming language.
- `Programming/Frameworks/` — framework and library profiles.
- `Programming/Gaps/` — coverage audits and missing topics.

Only the Obsidian bridge may write prepared memory records. It must resolve the
target path below the configured vault root and reject traversal outside it.

