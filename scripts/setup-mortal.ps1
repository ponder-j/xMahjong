param([string]$Proxy = '')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
uv sync --locked
if ($LASTEXITCODE -ne 0) { throw 'Dependency install failed' }
uv run python scripts/download-mortal.py
if ($LASTEXITCODE -ne 0) { throw 'Checkpoint download or SHA-256 verification failed' }
$proxyArgs = @()
if ($Proxy) { $proxyArgs = @('--build-arg', "HTTP_PROXY=$Proxy", '--build-arg', "HTTPS_PROXY=$Proxy") }
docker build @proxyArgs -f tools/mortal.Dockerfile -t xmahjong/mortal:local .
if ($LASTEXITCODE -ne 0) { throw 'Mortal runtime build failed' }
uv run python scripts/setup-mortal.py
if ($LASTEXITCODE -ne 0) { throw 'Mortal configuration failed' }
