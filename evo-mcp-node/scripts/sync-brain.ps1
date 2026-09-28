[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BrainSource = (Resolve-Path (Join-Path $Root "../brain")).Path
$Helper = "evo-mcp-brain-sync"

docker volume create evo_mcp_brain | Out-Null
docker rm -f $Helper *> $null
docker run -d --name $Helper -v evo_mcp_brain:/brain alpine:3.22 sleep 300 | Out-Null
try {
    docker cp "$BrainSource/." "${Helper}:/brain"
    if ($LASTEXITCODE -ne 0) { throw "docker cp failed" }
} finally {
    docker rm -f $Helper *> $null
}
Write-Host "Brain synchronized to Docker volume evo_mcp_brain."
