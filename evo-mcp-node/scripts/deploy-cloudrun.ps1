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

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    throw "Google Cloud CLI (gcloud) is not installed."
}

$account = (& gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>$null | Select-Object -First 1)
if (-not $account) {
    & gcloud auth login
    if ($LASTEXITCODE -ne 0) { throw "Google Cloud login failed." }
}

if (-not $ProjectId) {
    $configured = (& gcloud config get-value project 2>$null).Trim()
    if ($configured -and $configured -ne "(unset)") { $ProjectId = $configured }
}
if (-not $ProjectId) {
    $projects = @(& gcloud projects list --filter="lifecycleState:ACTIVE" --format="value(projectId)")
    if ($projects.Count -eq 1) { $ProjectId = $projects[0] }
    else { throw "Multiple/no projects found. Rerun with -ProjectId YOUR_PROJECT_ID." }
}

if (-not (Test-Path ".env")) {
    throw "Missing .env. Run .\\scripts\\setup.ps1 first."
}
$tokenLine = Get-Content .env | Where-Object { $_ -match '^MCP_API_KEY=' } | Select-Object -First 1
$token = if ($tokenLine) { ($tokenLine -split '=', 2)[1].Trim() } else { "" }
if ($token.Length -lt 32) { throw "MCP_API_KEY in .env is missing or too short." }

& gcloud config set project $ProjectId | Out-Null
& gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com --project $ProjectId
if ($LASTEXITCODE -ne 0) { throw "Could not enable required Google Cloud APIs." }

& gcloud secrets describe $SecretName --project $ProjectId *> $null
if ($LASTEXITCODE -ne 0) {
    & gcloud secrets create $SecretName --replication-policy=automatic --project $ProjectId
    if ($LASTEXITCODE -ne 0) { throw "Could not create Secret Manager secret." }
}
$tempSecret = [IO.Path]::GetTempFileName()
try {
    [IO.File]::WriteAllText($tempSecret, $token, [Text.UTF8Encoding]::new($false))
    & gcloud secrets versions add $SecretName --data-file=$tempSecret --project $ProjectId | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Could not add secret version." }
} finally {
    Remove-Item $tempSecret -Force -ErrorAction SilentlyContinue
}

$projectNumber = (& gcloud projects describe $ProjectId --format="value(projectNumber)").Trim()
$serviceAccount = "$projectNumber-compute@developer.gserviceaccount.com"
& gcloud secrets add-iam-policy-binding $SecretName --project $ProjectId --member="serviceAccount:$serviceAccount" --role="roles/secretmanager.secretAccessor" | Out-Null

& gcloud run deploy $ServiceName `
    --source . `
    --project $ProjectId `
    --region $Region `
    --port 8000 `
    --allow-unauthenticated `
    --min 0 `
    --max 1 `
    --cpu 1 `
    --memory 512Mi `
    --concurrency 20 `
    --timeout 300 `
    --set-env-vars="MCP_REQUIRE_AUTH=true,MCP_TRUST_PROXY=true,LOG_LEVEL=INFO" `
    --set-secrets="MCP_API_KEY=$SecretName:latest"
if ($LASTEXITCODE -ne 0) { throw "Cloud Run deployment failed." }

$url = (& gcloud run services describe $ServiceName --project $ProjectId --region $Region --format="value(status.url)").Trim()
Write-Host ""
Write-Host "Cloud deployment created/updated."
Write-Host "Health: $url/health"
Write-Host "MCP:    $url/mcp"
Write-Host "Bearer token remains in your local .env and in Google Secret Manager."
