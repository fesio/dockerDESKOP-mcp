Set-Location (Resolve-Path (Join-Path $PSScriptRoot ".."))
docker compose logs -f --tail 100
