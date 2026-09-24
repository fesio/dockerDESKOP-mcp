Set-Location (Resolve-Path (Join-Path $PSScriptRoot ".."))
docker compose --profile n8n logs -f --tail 150
