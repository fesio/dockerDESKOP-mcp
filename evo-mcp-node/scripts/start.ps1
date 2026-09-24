$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path (Join-Path $PSScriptRoot ".."))
docker compose up -d
if ($LASTEXITCODE -ne 0) { throw "Could not start Evo MCP Node." }
docker compose ps
