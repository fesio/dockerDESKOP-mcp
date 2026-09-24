$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path (Join-Path $PSScriptRoot ".."))
docker compose ps
$portLine = Get-Content .env | Where-Object { $_ -match '^LOCAL_MCP_PORT=' } | Select-Object -First 1
$port = if ($portLine) { ($portLine -split '=', 2)[1] } else { "8765" }
try {
    Invoke-RestMethod -Uri "http://127.0.0.1:$port/health" -TimeoutSec 3 | ConvertTo-Json -Depth 5
} catch {
    Write-Warning "Health endpoint is not reachable."
}
