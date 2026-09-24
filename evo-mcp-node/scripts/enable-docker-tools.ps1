[CmdletBinding()]
param([int]$DockerGid = -1)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root
if ($DockerGid -lt 0) {
    $detected = docker run --rm -v /var/run/docker.sock:/var/run/docker.sock alpine:3.22 stat -c %g /var/run/docker.sock
    if ($LASTEXITCODE -ne 0) { throw "Could not detect Docker socket group ID." }
    $DockerGid = [int]$detected.Trim()
}
$content = Get-Content .env -Raw
if ($content -match '(?m)^DOCKER_GID=') { $content = $content -replace '(?m)^DOCKER_GID=.*$', "DOCKER_GID=$DockerGid" }
else { $content += "`nDOCKER_GID=$DockerGid`n" }
[IO.File]::WriteAllText((Join-Path $Root ".env"), $content, [Text.UTF8Encoding]::new($false))
Write-Warning "Docker socket access is equivalent to broad control over Docker Desktop. Enable only on a trusted local machine."
docker compose -f compose.yaml -f compose.host-tools.yaml up -d --build evo-mcp
