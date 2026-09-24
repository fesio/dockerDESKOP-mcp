[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$ProjectId,
    [string]$GithubOwner = "fesio",
    [string]$GithubRepo = "dockerDESKOP-mcp",
    [string]$PoolId = "github-actions",
    [string]$ProviderId = "github",
    [string]$ServiceAccountName = "evo-mcp-github",
    [string]$SecretName = "evo-mcp-api-key"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    throw "Google Cloud CLI (gcloud) is not installed."
}

$activeAccount = (& gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>$null | Select-Object -First 1)
if (-not $activeAccount) {
    & gcloud auth login
    if ($LASTEXITCODE -ne 0) { throw "Google Cloud authentication failed." }
}

& gcloud config set project $ProjectId | Out-Null
& gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com iamcredentials.googleapis.com sts.googleapis.com --project $ProjectId
if ($LASTEXITCODE -ne 0) { throw "Could not enable required Google Cloud APIs." }

$ProjectNumber = (& gcloud projects describe $ProjectId --format="value(projectNumber)").Trim()
if (-not $ProjectNumber) { throw "Could not resolve project number." }
$ServiceAccount = "$ServiceAccountName@$ProjectId.iam.gserviceaccount.com"
$RuntimeServiceAccount = "$ProjectNumber-compute@developer.gserviceaccount.com"

& gcloud iam service-accounts describe $ServiceAccount --project $ProjectId *> $null
if ($LASTEXITCODE -ne 0) {
    & gcloud iam service-accounts create $ServiceAccountName --project $ProjectId --display-name="Evo MCP GitHub deployer"
}

foreach ($Role in @("roles/run.admin", "roles/run.sourceDeveloper", "roles/serviceusage.serviceUsageConsumer")) {
    & gcloud projects add-iam-policy-binding $ProjectId --member="serviceAccount:$ServiceAccount" --role=$Role --condition=None | Out-Null
}

# Source deployments use Cloud Build; Google currently uses the Compute Engine default
# service account unless another build account is explicitly selected.
& gcloud projects add-iam-policy-binding $ProjectId --member="serviceAccount:$RuntimeServiceAccount" --role="roles/run.builder" --condition=None | Out-Null
& gcloud iam service-accounts add-iam-policy-binding $RuntimeServiceAccount --project $ProjectId --member="serviceAccount:$ServiceAccount" --role="roles/iam.serviceAccountUser" | Out-Null

& gcloud iam workload-identity-pools describe $PoolId --location=global --project $ProjectId *> $null
if ($LASTEXITCODE -ne 0) {
    & gcloud iam workload-identity-pools create $PoolId --location=global --project $ProjectId --display-name="GitHub Actions"
}

& gcloud iam workload-identity-pools providers describe $ProviderId --workload-identity-pool=$PoolId --location=global --project $ProjectId *> $null
if ($LASTEXITCODE -ne 0) {
    & gcloud iam workload-identity-pools providers create-oidc $ProviderId `
        --project $ProjectId `
        --location global `
        --workload-identity-pool $PoolId `
        --display-name "GitHub $GithubOwner/$GithubRepo" `
        --issuer-uri "https://token.actions.githubusercontent.com" `
        --attribute-mapping "google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" `
        --attribute-condition "assertion.repository=='$GithubOwner/$GithubRepo'"
}

$PrincipalSet = "principalSet://iam.googleapis.com/projects/$ProjectNumber/locations/global/workloadIdentityPools/$PoolId/attribute.repository/$GithubOwner/$GithubRepo"
& gcloud iam service-accounts add-iam-policy-binding $ServiceAccount --project $ProjectId --member=$PrincipalSet --role="roles/iam.workloadIdentityUser" | Out-Null

$ProviderResource = (& gcloud iam workload-identity-pools providers describe $ProviderId --workload-identity-pool=$PoolId --location=global --project $ProjectId --format="value(name)").Trim()
if (-not $ProviderResource) { throw "Could not resolve WIF provider resource name." }

if (-not (Test-Path ".env")) { throw "Missing .env. Run .\scripts\setup.ps1 first." }
$TokenLine = Get-Content .env | Where-Object { $_ -match '^MCP_API_KEY=' } | Select-Object -First 1
$Token = if ($TokenLine) { ($TokenLine -split '=',2)[1].Trim() } else { "" }
if ($Token.Length -lt 32) { throw "MCP_API_KEY in .env is missing/too short." }

& gcloud secrets describe $SecretName --project $ProjectId *> $null
if ($LASTEXITCODE -ne 0) {
    & gcloud secrets create $SecretName --replication-policy=automatic --project $ProjectId
}
$TempSecret = [IO.Path]::GetTempFileName()
try {
    [IO.File]::WriteAllText($TempSecret, $Token, [Text.UTF8Encoding]::new($false))
    & gcloud secrets versions add $SecretName --data-file=$TempSecret --project $ProjectId | Out-Null
} finally {
    Remove-Item $TempSecret -Force -ErrorAction SilentlyContinue
}
& gcloud secrets add-iam-policy-binding $SecretName --project $ProjectId --member="serviceAccount:$RuntimeServiceAccount" --role="roles/secretmanager.secretAccessor" | Out-Null

Write-Host ""
Write-Host "Google Workload Identity Federation is configured."
Write-Host "Repository variables required by .github/workflows/evo-mcp-cloudrun.yml:"
Write-Host "GCP_PROJECT_ID=$ProjectId"
Write-Host "GCP_WIF_PROVIDER=$ProviderResource"
Write-Host "GCP_SERVICE_ACCOUNT=$ServiceAccount"

if (Get-Command gh -ErrorAction SilentlyContinue) {
    & gh auth status *> $null
    if ($LASTEXITCODE -eq 0) {
        & gh variable set GCP_PROJECT_ID --repo "$GithubOwner/$GithubRepo" --body $ProjectId
        & gh variable set GCP_WIF_PROVIDER --repo "$GithubOwner/$GithubRepo" --body $ProviderResource
        & gh variable set GCP_SERVICE_ACCOUNT --repo "$GithubOwner/$GithubRepo" --body $ServiceAccount
        Write-Host "GitHub repository variables were set automatically with gh CLI."
    } else {
        Write-Host "gh CLI exists but is not authenticated; set the three repository variables shown above."
    }
} else {
    Write-Host "gh CLI not found; set the three repository variables shown above in GitHub Settings -> Actions -> Variables."
}
