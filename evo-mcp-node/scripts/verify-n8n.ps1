$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path (Join-Path $PSScriptRoot ".."))
$portLine = Get-Content .env | Where-Object { $_ -match '^LOCAL_MCP_PORT=' } | Select-Object -First 1
$port = if ($portLine) { ($portLine -split '=', 2)[1] } else { "8765" }
$ready = Invoke-RestMethod -Uri "http://127.0.0.1:$port/ready" -TimeoutSec 5
$ready | ConvertTo-Json -Depth 5
try {
    $n8n = Invoke-WebRequest -Uri "http://127.0.0.1:5678/healthz" -UseBasicParsing -TimeoutSec 5
    Write-Host "n8n health HTTP $($n8n.StatusCode)"
} catch {
    Write-Warning "Local n8n health endpoint is unavailable. If you use remote n8n, this is expected."
}
if (-not $ready.n8nMcpConfigured) {
    throw "N8N_MCP_URL/token are not configured in Evo MCP. Run configure-n8n.ps1."
}
Write-Host "Evo MCP sees native n8n MCP configuration. Use n8n_native_tools from your MCP client for the protocol-level verification."
