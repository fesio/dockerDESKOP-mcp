[CmdletBinding()]
param(
    [string]$Destination = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $Destination) {
    $Destination = Join-Path $Root "../brain/raw/notebooklm-bundles"
}
New-Item -ItemType Directory -Path $Destination -Force | Out-Null
docker cp "evo-mcp-apps:/data/notebooklm/." $Destination
if ($LASTEXITCODE -ne 0) { throw "Could not export NotebookLM bundles from Evo MCP." }
Write-Host "NotebookLM bundles exported to $Destination"
