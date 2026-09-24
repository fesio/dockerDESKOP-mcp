[CmdletBinding()]
param(
    [string]$ProjectId = "",
    [string]$Region = "europe-west1",
    [string]$ServiceName = "evo-mcp-node",
    [string]$SecretName = "evo-mcp-api-key"
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root
if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) { throw "Google Cloud CLI (gcloud) is not installed." }
$account = (& gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>$null | Select-Object -First 1)
if (-not $account) {
    & gcloud auth login
    if ($LASTEXITCODE -ne 0) { throw "Google Cloud authentication failed." }
}
if (-not $ProjectId) {
    $configured = (& gcloud config get-value project 2>$null).Trim()
    if ($configured -and $configured -ne "(unset)") { $ProjectId = $configured }
}
if (-not $ProjectId) { throw "Provide -ProjectId or configure a default gcloud project." }
if (-not (Test-Path ".env")) { throw "Missing .env. Run setup.ps1 first." }
$token = ((Get-Content .env | Where-Object { $_ -match '^MCP_API_KEY=' } | Select-Object -First 1) -split '=', 2)[1]
if ($token.Length -lt 32) { throw "MCP_API_KEY is missing/too short." }

& gcloud config set project $ProjectId | Out-Null
& gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com --project $ProjectId
if ($LASTEXITCODE -ne 0) { throw "Could not enable Google Cloud APIs." }
& gcloud secrets describe $SecretName --project $ProjectId *> $null
if ($LASTEXITCODE -ne 0) {
    & gcloud secrets create $SecretName --replication-policy=automatic --project $ProjectId
}
$tmp = [IO.Path]::GetTempFileName()
try {
    [IO.File]::WriteAllText($tmp, $token, [Text.UTF8Encoding]::new($false))
    & gcloud secrets versions add $SecretName --data-file=$tmp --project $ProjectId | Out-Null
} finally { Remove-Item $tmp -Force -ErrorAction SilentlyContinue }

$number = (& gcloud projects describe $ProjectId --format="value(projectNumber)").Trim()
$runtimeSa = "$number-compute@developer.gserviceaccount.com"
& gcloud secrets add-iam-policy-binding $SecretName --project $ProjectId --member="serviceAccount:$runtimeSa" --role="roles/secretmanager.secretAccessor" | Out-Null

& gcloud run deploy $ServiceName `
    --source . `
    --project $ProjectId `
    --region $Region `
    --port 8000 `
    --allow-unauthenticated `
    --min 0 `
    --max 1 `
    --cpu 1 `
    --memory 768Mi `
    --concurrency 20 `
    --timeout 300 `
    --set-env-vars="MCP_REQUIRE_AUTH=true,MCP_TRUST_PROXY=true,PROGRAMMER_PROFILE=read,LOG_LEVEL=INFO" `
    --set-secrets="MCP_API_KEY=$SecretName:latest"
if ($LASTEXITCODE -ne 0) { throw "Cloud Run deployment failed." }
$url = (& gcloud run services describe $ServiceName --project $ProjectId --region $Region --format="value(status.url)").Trim()
Write-Host "Health: $url/health"
Write-Host "MCP:    $url/mcp"
Write-Host "Cloud /mcp requires the Bearer token stored in local .env and Secret Manager."
