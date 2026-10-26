$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pidPath = Join-Path $projectRoot 'data\server.pid'
if (-not (Test-Path -LiteralPath $pidPath)) { Write-Host 'No saved XMahjong process.'; return }
$serverProcessId = [int](Get-Content -LiteralPath $pidPath -Raw)
$process = Get-CimInstance Win32_Process -Filter "ProcessId=$serverProcessId"
if ($process) {
    if ($process.ExecutablePath -ne (Join-Path $projectRoot '.venv\Scripts\python.exe') -or $process.CommandLine -notmatch 'uvicorn xmahjong\.app:app') { throw 'Saved PID does not identify this XMahjong server.' }
    Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $serverProcessId -and $_.CommandLine -match 'uvicorn xmahjong\.app:app' } | ForEach-Object { Stop-Process -Id $_.ProcessId }
    Stop-Process -Id $serverProcessId -ErrorAction SilentlyContinue
}
Remove-Item -LiteralPath $pidPath
Write-Host 'XMahjong stopped.'
