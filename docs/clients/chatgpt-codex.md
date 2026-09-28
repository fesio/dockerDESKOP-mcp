# ChatGPT and Codex

## Codex on the same Windows computer

Add the running local server once:

```powershell
codex mcp add evo --url http://127.0.0.1:8765/mcp
codex mcp list
```

`AGENTS.md` tells Codex to collect evidence before answering and to use durable tasks for long work.

## ChatGPT personal use

Keep the server private and connect it through OpenAI Secure MCP Tunnel when that feature is available
for the account/workspace. This avoids exposing the local Obsidian vault or Docker-enabled profile to
the public internet. The public Cloud Run profile is read-only and has no Docker socket.

Never expose the local `standard` or `autonomous` profile directly to the Internet.
