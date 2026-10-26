param([int]$Port = 8765, [switch]$Restart)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$dataPath = Join-Path $projectRoot 'data'
New-Item -ItemType Directory -Force -Path $dataPath | Out-Null
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run uv sync --locked before starting the service.' }
$listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
if ($listeners) {
    $allProcesses = @(Get-CimInstance Win32_Process)
    $processes = @($allProcesses | Where-Object { $_.ProcessId -in $listeners.OwningProcess })
    $owned = @($processes | Where-Object {
        $parent = $allProcesses | Where-Object ProcessId -eq $_.ParentProcessId
        $directOwned = $_.ExecutablePath -eq $pythonPath
        $parentOwned = $parent.ExecutablePath -eq $pythonPath -and $parent.CommandLine -match 'uvicorn xmahjong\.app:app'
        ($directOwned -or $parentOwned) -and $_.CommandLine -match 'uvicorn xmahjong\.app:app'
    })
    if ($owned.Count -ne $processes.Count -or $owned.Count -eq 0) { throw "Port $Port belongs to another application." }
    if (-not $Restart) {
        $health = Invoke-RestMethod "http://127.0.0.1:$Port/api/health" -TimeoutSec 3
        if ($health.status -ne 'ok') { throw 'Existing XMahjong server is not healthy.' }
        Write-Host "XMahjong already running at http://127.0.0.1:$Port"
        return
    }
    $owned | ForEach-Object { Stop-Process -Id $_.ProcessId -PassThru | Wait-Process -Timeout 10 -ErrorAction SilentlyContinue }
}
$process = Start-Process -FilePath $pythonPath -ArgumentList @('-m', 'uvicorn', 'xmahjong.app:app', '--app-dir', 'backend', '--host', '127.0.0.1', '--port', "$Port") -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $dataPath 'server.out.log') -RedirectStandardError (Join-Path $dataPath 'server.err.log') -PassThru
$process.Id | Set-Content -LiteralPath (Join-Path $dataPath 'server.pid') -Encoding ascii
$deadline = (Get-Date).AddSeconds(30)
while ((Get-Date) -lt $deadline) {
    $process.Refresh()
    if ($process.HasExited) { throw "XMahjong exited. Check $dataPath\server.err.log" }
    try {
        $health = Invoke-RestMethod "http://127.0.0.1:$Port/api/health" -TimeoutSec 2
        if ($health.status -eq 'ok') { Write-Host "XMahjong ready at http://127.0.0.1:$Port (PID $($process.Id))"; return }
    } catch { }
    Start-Sleep -Milliseconds 300
}
throw "XMahjong did not become healthy. Check $dataPath\server.err.log"
