[CmdletBinding()]
param(
    [switch]$WithN8n,
    [switch]$SkipTests,
    [switch]$RecreateEnv
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root

function New-RandomHex([int]$Bytes = 32) {
    $buffer = [Security.Cryptography.RandomNumberGenerator]::GetBytes($Bytes)
    return [Convert]::ToHexString($buffer).ToLowerInvariant()
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI not found. Install/start Docker Desktop first."
}
docker info *> $null
if ($LASTEXITCODE -ne 0) { throw "Docker Engine is not running." }

if ($RecreateEnv -or -not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env" -Force
    $content = Get-Content ".env" -Raw
    $content = $content -replace '(?m)^MCP_API_KEY=.*$', "MCP_API_KEY=$(New-RandomHex 32)"
    $content = $content -replace '(?m)^PROGRAMMER_APPROVAL_SECRET=.*$', "PROGRAMMER_APPROVAL_SECRET=$(New-RandomHex 24)"
    $content = $content -replace '(?m)^N8N_ENCRYPTION_KEY=.*$', "N8N_ENCRYPTION_KEY=$(New-RandomHex 32)"
    [IO.File]::WriteAllText((Join-Path $Root ".env"), $content, [Text.UTF8Encoding]::new($false))
    Write-Host "Created .env with locally generated secrets. Secrets were not printed."
}

New-Item -ItemType Directory -Path "workspace" -Force | Out-Null

if (-not $SkipTests) {
    Write-Host "Building test target (Ruff + pytest)..."
    docker build --target test -t evo-mcp-node:test .
    if ($LASTEXITCODE -ne 0) { throw "Test image failed." }
}

Write-Host "Starting Evo MCP..."
docker compose up -d --build evo-mcp
if ($LASTEXITCODE -ne 0) { throw "Could not start Evo MCP." }

if ($WithN8n) {
    Write-Host "Starting local n8n 2.40.5..."
    docker compose --profile n8n up -d n8n
    if ($LASTEXITCODE -ne 0) { throw "Could not start n8n." }
}

$portLine = Get-Content .env | Where-Object { $_ -match '^LOCAL_MCP_PORT=' } | Select-Object -First 1
$port = if ($portLine) { ($portLine -split '=', 2)[1] } else { "8765" }
$health = "http://127.0.0.1:$port/health"
$ok = $false
for ($i = 0; $i -lt 60; $i++) {
    try {
        if ((Invoke-RestMethod -Uri $health -TimeoutSec 2).status -eq "ok") { $ok = $true; break }
    } catch { Start-Sleep -Seconds 2 }
}
if (-not $ok) {
    docker compose logs --tail 150 evo-mcp
    throw "Evo MCP health check did not pass."
}

Write-Host ""
Write-Host "Evo MCP: http://127.0.0.1:$port/mcp"
Write-Host "Health:  $health"
if ($WithN8n) {
    Write-Host "n8n UI:   http://127.0.0.1:5678"
    Write-Host "One-time n8n step: create the owner, enable Settings -> MCP access, create an MCP API token, and optionally create a REST API key."
    Write-Host "Then run: .\scripts\configure-n8n.ps1"
}
