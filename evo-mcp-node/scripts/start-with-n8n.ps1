$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path (Join-Path $PSScriptRoot ".."))
docker compose --profile n8n up -d evo-mcp n8n
if ($LASTEXITCODE -ne 0) { throw "Could not start Evo MCP + n8n." }
docker compose --profile n8n ps
