$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path (Join-Path $PSScriptRoot ".."))
docker compose up -d evo-mcp
if ($LASTEXITCODE -ne 0) { throw "Could not start Evo MCP." }
docker compose ps
