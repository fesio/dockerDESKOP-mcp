# Vercel Inspector MCP

Read-only MCP server for agent-driven Vercel diagnostics. It runs locally over
`stdio` or as a stateless Streamable HTTP endpoint in a Vercel Next.js Function.

## Tool surface

- `get_deployment_history` — up to 20 recent deployments with state, target,
  author and Git metadata.
- `get_deployment_logs` — deployment details plus bounded, redacted build
  events, a diagnosis and a concrete next action.
- `get_project_env_list` — names, targets and non-secret metadata only; it can
  report required variable names that are missing.

The implementation uses the current documented endpoints:

- `GET /v7/deployments`
- `GET /v13/deployments/{idOrUrl}`
- `GET /v3/deployments/{idOrUrl}/events`
- `GET /v10/projects/{idOrName}/env?decrypt=false`

## Security contract

- `VERCEL_TOKEN` and `MCP_API_KEY` are server-only secrets.
- The HTTP endpoint fails closed when `MCP_API_KEY` is absent and uses a
  constant-time digest comparison for bearer authentication.
- `VERCEL_PROJECT_ALLOWLIST` optionally constrains which projects the agent may
  inspect.
- Environment-variable values are never requested. The normalizer discards
  `value`, `decrypted` and all other unapproved fields.
- Build output is capped at 200 entries and common token, authorization,
  password, cookie, query-secret and JWT patterns are redacted.
- API errors are sanitized and never include headers, tokens or stack traces.
- All tools are read-only; this server cannot deploy, promote, roll back or
  mutate project configuration.

## Local setup (`stdio`)

```bash
cd vercel-inspector-mcp
npm ci
export VERCEL_TOKEN="set-this-outside-the-repository"
export VERCEL_TEAM_ID="team_optional"
npm run check
npm run stdio
```

Example client configuration:

```json
{
    "mcpServers": {
        "vercel-history": {
            "command": "npm",
            "args": [
                "--silent",
                "--prefix",
                "/absolute/path/to/vercel-inspector-mcp",
                "run",
                "stdio"
            ],
            "env": {
                "VERCEL_TOKEN": "provided-by-the-client-secret-store",
                "VERCEL_TEAM_ID": "optional-team-id"
            }
        }
    }
}
```

Use the MCP client's secret store or inherited process environment instead of
placing a real token in a tracked JSON file.

## Deploy to Vercel

1. Import this directory as a Vercel project or set it as the monorepo Root
   Directory.
2. Configure `VERCEL_TOKEN` and `MCP_API_KEY` as Sensitive values.
3. Optionally configure `VERCEL_TEAM_ID` and a comma-separated
   `VERCEL_PROJECT_ALLOWLIST`.
4. Deploy and check `GET /api/health`.
5. Connect the MCP client to `https://<deployment>/api/mcp` and send
   `Authorization: Bearer <MCP_API_KEY>` from its secret store.

CLI equivalent after `vercel link`:

```bash
vercel env add VERCEL_TOKEN --sensitive
vercel env add MCP_API_KEY --sensitive
vercel env add VERCEL_TEAM_ID
vercel env add VERCEL_PROJECT_ALLOWLIST
vercel deploy
```

`MCP_API_KEY` protects access to this custom endpoint. `VERCEL_TOKEN` is the
separate upstream credential used only by the server when it calls Vercel REST
API.

## Validation

```bash
npm run check
```

Unit tests mock network calls. A live read additionally requires a real
`VERCEL_TOKEN`, an accessible project and the correct optional team scope.
