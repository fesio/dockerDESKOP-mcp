[CmdletBinding()]
param(
    [string]$BaseUrl = "http://n8n:5678",
    [string]$McpUrl = "http://n8n:5678/mcp-server/http"
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root
if (-not (Test-Path ".env")) { throw "Missing .env. Run setup.ps1 first." }

function Read-SecretText([string]$Prompt) {
    $secure = Read-Host $Prompt -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}
function Set-EnvValue([string]$Key, [string]$Value) {
    if ($Value.Contains("`n") -or $Value.Contains("`r")) { throw "$Key contains a newline." }
    $lines = [Collections.Generic.List[string]](Get-Content ".env")
    $found = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match "^$([regex]::Escape($Key))=") {
            $lines[$i] = "$Key=$Value"
            $found = $true
            break
        }
    }
    if (-not $found) { $lines.Add("$Key=$Value") }
    [IO.File]::WriteAllLines((Join-Path $Root ".env"), $lines, [Text.UTF8Encoding]::new($false))
}

$apiKey = Read-SecretText "Paste n8n REST API key (press Enter to leave REST fallback disabled)"
$mcpToken = Read-SecretText "Paste n8n MCP API token from Settings -> MCP access"
if ([string]::IsNullOrWhiteSpace($mcpToken)) { throw "n8n MCP token is required for the native integration." }

Set-EnvValue "N8N_BASE_URL" $BaseUrl
Set-EnvValue "N8N_MCP_URL" $McpUrl
Set-EnvValue "N8N_API_KEY" $apiKey
Set-EnvValue "N8N_MCP_TOKEN" $mcpToken

docker compose up -d --force-recreate evo-mcp
if ($LASTEXITCODE -ne 0) { throw "Could not restart Evo MCP." }
Write-Host "n8n credentials saved locally in .env (not printed, .gitignored)."
Write-Host "Run .\scripts\verify-n8n.ps1 to check connectivity."
