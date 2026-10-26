param([int]$Port = 8765)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw 'Install uv first: https://docs.astral.sh/uv/' }
uv sync --locked
if ($LASTEXITCODE -ne 0) { throw 'Dependency install failed' }
uv run uvicorn xmahjong.app:app --app-dir backend --host 127.0.0.1 --port $Port
