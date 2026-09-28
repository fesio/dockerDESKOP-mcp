[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$SourcePath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Source = (Resolve-Path $SourcePath).Path
$Helper = "evo-mcp-workspace-sync"

docker volume create evo_mcp_workspace | Out-Null
docker rm -f $Helper *> $null
docker run -d --name $Helper -v evo_mcp_workspace:/workspace alpine:3.22 sleep 300 | Out-Null
try {
    docker cp "$Source/." "${Helper}:/workspace"
    if ($LASTEXITCODE -ne 0) { throw "docker cp failed" }
} finally {
    docker rm -f $Helper *> $null
}
Write-Host "Workspace synchronized to Docker volume evo_mcp_workspace."
