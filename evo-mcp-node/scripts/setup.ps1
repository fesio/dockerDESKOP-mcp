[CmdletBinding()]
param(
    [switch]$SkipTests,
    [switch]$RecreateEnv
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root

function New-RandomToken {
    $bytes = [Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
    return [Convert]::ToHexString($bytes).ToLowerInvariant()
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI not found. Install/start Docker Desktop first."
}

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker engine is not running. Start Docker Desktop and rerun this script."
}

if ($RecreateEnv -or -not (Test-Path ".env")) {
    $token = New-RandomToken
    $envText = @"
LOCAL_MCP_PORT=8765
LOG_LEVEL=INFO
MCP_REQUIRE_AUTH=false
MCP_API_KEY=$token
MCP_TRUST_PROXY=false
"@
    [IO.File]::WriteAllText((Join-Path $Root ".env"), $envText, [Text.UTF8Encoding]::new($false))
    Write-Host "Created local .env and a private token for future cloud deployment."
}

if (-not $SkipTests) {
    Write-Host "Building test image and running tests..."
    docker build --target test -t evo-mcp-node:test .
    if ($LASTEXITCODE -ne 0) { throw "Test image build failed." }
}

Write-Host "Building and starting Evo MCP Node..."
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { throw "docker compose up failed." }

$portLine = Get-Content .env | Where-Object { $_ -match '^LOCAL_MCP_PORT=' } | Select-Object -First 1
$port = if ($portLine) { ($portLine -split '=', 2)[1] } else { "8765" }
$healthUrl = "http://127.0.0.1:$port/health"
$healthy = $false
for ($i = 0; $i -lt 45; $i++) {
    try {
        $result = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 2
        if ($result.status -eq "ok") { $healthy = $true; break }
    } catch { Start-Sleep -Seconds 2 }
}
if (-not $healthy) {
    docker compose logs --tail 100
    throw "Container started but health check did not pass."
}

Write-Host ""
Write-Host "Evo MCP Node is running."
Write-Host "MCP URL:    http://127.0.0.1:$port/mcp"
Write-Host "Health URL: $healthUrl"
Write-Host "Docker restart policy: unless-stopped"
