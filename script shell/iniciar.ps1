param([switch]$Demo, [switch]$NoBrowser, [switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $projectRoot
$pythonPath = Join-Path $projectRoot 'server\.venv\Scripts\python.exe'
$requirementsPath = Join-Path $projectRoot 'robot\requirements.txt'
$port = if ($Demo) { 8001 } else { 8000 }
$dataPath = Join-Path $projectRoot $(if ($Demo) { 'server\data-demo' } else { 'server\data' })
if (-not (Test-Path -LiteralPath $pythonPath)) {
    python -m venv (Join-Path $projectRoot 'server\.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Instale Python 3.10 ou mais recente.' }
}
& $pythonPath -c "import fastapi, uvicorn, coppeliasim_zmqremoteapi_client, torch, torchvision, cv2, PIL, ultralytics"
if ($LASTEXITCODE -ne 0) {
    & $pythonPath -m pip install -r $requirementsPath
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar as dependencias.' }
}
if ($CheckOnly) {
    & $pythonPath -m robot.main --help
    exit $LASTEXITCODE
}
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'robot\simulation_photos\manifest.json'))) {
    & $pythonPath -m robot.prepare_photos
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao preparar fotos da simulacao.' }
}
try {
    $status = Invoke-RestMethod "http://127.0.0.1:$port/api/status" -TimeoutSec 2
    if ($status.version -eq 'inspection-1' -and $null -ne $status.robot_status) {
        if (-not $NoBrowser) { Start-Process "http://127.0.0.1:$port" }
        exit 0
    }
} catch { }
function Test-Simulator {
    $connection = New-Object System.Net.Sockets.TcpClient
    try { $connection.Connect('127.0.0.1', 23000); return $true }
    catch { return $false }
    finally { $connection.Dispose() }
}
if (-not $Demo -and -not (Test-Simulator)) {
    $simulatorPath = 'C:\Program Files\CoppeliaRobotics\CoppeliaSimEdu\coppeliaSim.exe'
    if (-not (Test-Path -LiteralPath $simulatorPath)) { throw 'Abra o CoppeliaSim e tente novamente.' }
    Start-Process -FilePath $simulatorPath -WorkingDirectory (Split-Path $simulatorPath) -WindowStyle Hidden
    $deadline = (Get-Date).AddSeconds(45)
    while (-not (Test-Simulator)) {
        if ((Get-Date) -gt $deadline) { throw 'O CoppeliaSim nao respondeu em 45 segundos.' }
        Start-Sleep -Milliseconds 500
    }
}
$launchArgs = @('-u', '-m', 'robot.main', '--web-port', "$port", '--data-dir', $dataPath)
if ($Demo) { $launchArgs += '--demo' }
if ($NoBrowser) { $launchArgs += '--no-browser' }
& $pythonPath @launchArgs
exit $LASTEXITCODE
