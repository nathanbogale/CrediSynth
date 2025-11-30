Param(
    [ValidateSet('local','docker')]
    [string]$Mode = 'local',

    [ValidateSet('build','start','stop','restart','status','logs','test')]
    [string]$Action = 'start',

    [string]$EnvFile = '.env',
    [string]$Tag = 'credisynth-qaa:local',
    [string]$Container = 'credisynth-qaa',
    [int]$Port = 5000
)

$Root = (Resolve-Path "$PSScriptRoot/..").Path
$LogsDir = Join-Path $Root 'logs'
if (!(Test-Path $LogsDir)) { New-Item -ItemType Directory -Path $LogsDir | Out-Null }

function Ensure-Venv {
    $venvPath = Join-Path $Root '.venv'
    $uvicornExe = Join-Path $venvPath 'Scripts/uvicorn.exe'
    if (Test-Path $uvicornExe) { return $uvicornExe }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) { Write-Error "Python not found. Please install Python 3.11+ and re-run."; exit 1 }
    Write-Host "Creating virtual environment at $venvPath" -ForegroundColor Cyan
    python -m venv $venvPath
    if ($LASTEXITCODE -ne 0) { Write-Error "Failed to create venv"; exit 1 }

    $activate = Join-Path $venvPath 'Scripts/Activate.ps1'
    Write-Host "Installing dependencies" -ForegroundColor Cyan
    & $activate
    pip install -r (Join-Path $Root 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { Write-Error "pip install failed"; exit 1 }
    return $uvicornExe
}

function Start-Local {
    $uvicornExe = Ensure-Venv
    $logFile = Join-Path $LogsDir 'local_server.log'
    $pidFile = Join-Path $LogsDir '.local_api.pid'
    Write-Host "Starting local API on port $Port" -ForegroundColor Green
    $proc = Start-Process -FilePath $uvicornExe -ArgumentList "app.main:app --host 0.0.0.0 --port $Port --reload" -WorkingDirectory $Root -RedirectStandardOutput $logFile -RedirectStandardError $logFile -PassThru
    $proc.Id | Out-File -FilePath $pidFile -Encoding ascii
    Write-Host "Started. PID: $($proc.Id). Logs: $logFile" -ForegroundColor Green
}

function Stop-Local {
    $pidFile = Join-Path $LogsDir '.local_api.pid'
    if (!(Test-Path $pidFile)) { Write-Host "No local PID file found." -ForegroundColor Yellow; return }
    $pid = Get-Content $pidFile | Select-Object -First 1
    try {
        Stop-Process -Id [int]$pid -Force -ErrorAction Stop
        Remove-Item $pidFile -Force
        Write-Host "Stopped local API (PID $pid)." -ForegroundColor Green
    } catch {
        Write-Host "Failed to stop process $pid: $($_.Exception.Message)" -ForegroundColor Red
    }
}

function Status-Local {
    $pidFile = Join-Path $LogsDir '.local_api.pid'
    if (!(Test-Path $pidFile)) { Write-Host "Local API: not running" -ForegroundColor Yellow; return }
    $pid = Get-Content $pidFile | Select-Object -First 1
    $p = Get-Process -Id [int]$pid -ErrorAction SilentlyContinue
    if ($p) { Write-Host "Local API: running (PID $pid)" -ForegroundColor Green } else { Write-Host "Local API: not running" -ForegroundColor Yellow }
}

function Logs-Local {
    $logFile = Join-Path $LogsDir 'local_server.log'
    if (!(Test-Path $logFile)) { Write-Host "No log file yet: $logFile" -ForegroundColor Yellow; return }
    Write-Host "Tailing $logFile (Ctrl+C to stop)" -ForegroundColor Cyan
    Get-Content -Path $logFile -Wait
}

function Build-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Write-Error "Docker CLI not found"; exit 1 }
    Write-Host "Building Docker image $Tag" -ForegroundColor Cyan
    docker build -t $Tag $Root
    if ($LASTEXITCODE -ne 0) { Write-Error "Docker build failed"; exit 1 }
}

function Start-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Write-Error "Docker CLI not found"; exit 1 }
    Write-Host "Starting Docker container $Container on port $Port" -ForegroundColor Green
    docker run -d --name $Container -p "$Port:$Port" --env-file (Join-Path $Root $EnvFile) $Tag
    if ($LASTEXITCODE -ne 0) { Write-Error "Docker run failed"; exit 1 }
}

function Stop-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Write-Error "Docker CLI not found"; exit 1 }
    docker stop $Container | Out-Null
    docker rm $Container | Out-Null
    Write-Host "Stopped and removed container $Container" -ForegroundColor Green
}

function Status-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Write-Error "Docker CLI not found"; exit 1 }
    $info = docker ps -a --filter "name=$Container" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    if ($info) { Write-Output $info } else { Write-Host "No container named $Container" -ForegroundColor Yellow }
}

function Logs-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Write-Error "Docker CLI not found"; exit 1 }
    Write-Host "Streaming logs from $Container (Ctrl+C to stop)" -ForegroundColor Cyan
    docker logs -f $Container
}

function Test-API {
    $baseUrl = "http://127.0.0.1:$Port"
    Write-Host "Health: $baseUrl/health" -ForegroundColor Cyan
    try {
        $h = Invoke-RestMethod -Method GET -Uri "$baseUrl/health"
        Write-Output ($h | ConvertTo-Json)
    } catch { Write-Host "Health check failed: $($_.Exception.Message)" -ForegroundColor Red }

    Write-Host "Analyze: $baseUrl/v1/analyze" -ForegroundColor Cyan
    $sample = Join-Path $Root 'sample_request.json'
    if (!(Test-Path $sample)) { Write-Error "Missing sample_request.json"; exit 1 }
    $body = Get-Content $sample -Raw
    try {
        $resp = Invoke-RestMethod -Method POST -Uri "$baseUrl/v1/analyze" -ContentType 'application/json' -Body $body
        Write-Output ($resp | ConvertTo-Json -Depth 6)
    } catch { Write-Host "Analyze failed: $($_.Exception.Message)" -ForegroundColor Red }
}

switch ($Mode) {
    'local' {
        switch ($Action) {
            'build' { Ensure-Venv | Out-Null }
            'start' { Start-Local }
            'stop' { Stop-Local }
            'restart' { Stop-Local; Start-Local }
            'status' { Status-Local }
            'logs' { Logs-Local }
            'test' { Test-API }
        }
    }
    'docker' {
        switch ($Action) {
            'build' { Build-Docker }
            'start' { Start-Docker }
            'stop' { Stop-Docker }
            'restart' { Stop-Docker; Start-Docker }
            'status' { Status-Docker }
            'logs' { Logs-Docker }
            'test' { Test-API }
        }
    }
}