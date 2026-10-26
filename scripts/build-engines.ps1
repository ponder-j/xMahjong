param([string]$Proxy = '')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
$proxyArgs = @()
if ($Proxy) { $proxyArgs = @('--build-arg', "HTTP_PROXY=$Proxy", '--build-arg', "HTTPS_PROXY=$Proxy") }
docker build @proxyArgs -f tools/convlog/Dockerfile -t xmahjong/convlog:local .
if ($LASTEXITCODE -ne 0) { throw 'convlog build failed' }
docker build @proxyArgs -f tools/akochan.Dockerfile --build-arg AKOCHAN_REF=53188a0b926fbab38177f88c3cd87d554cf412af -t xmahjong/akochan:local .
if ($LASTEXITCODE -ne 0) { throw 'Akochan build failed' }
if (-not (Test-Path config.local.json)) { Copy-Item config.example.json config.local.json }
Write-Host 'convlog and Akochan ready. To install the pinned community Mortal model, run scripts/setup-mortal.ps1.'
