<#
.SYNOPSIS
    Bring the football-tracker stack up locally on Windows.

.DESCRIPTION
    Starts Docker (if needed), the Postgres and Redis containers, applies migrations, and
    launches the Django dev server and the Celery worker in their own windows.

    The Celery worker MUST use --pool=solo on Windows: the default prefork pool relies on
    fork() and will hang. Getting that flag right automatically is the main reason this
    script exists.

.PARAMETER Restart
    Kill the running Celery worker and start a fresh one, then exit. Use this after editing
    anything under cv_engine/ or backend/matches/ - Celery does not reload changed code, and
    a stale worker will keep producing pre-edit behaviour.

.PARAMETER Adminer
    Also start the Adminer database inspector on http://localhost:8080.

.EXAMPLE
    .\start-local.ps1
    .\start-local.ps1 -Restart
    .\start-local.ps1 -Adminer
#>
[CmdletBinding()]
param(
    [switch]$Restart,
    [switch]$Adminer
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$backend = Join-Path $root 'backend'
$python = Join-Path $backend '.venv\Scripts\python.exe'
$celery = Join-Path $backend '.venv\Scripts\celery.exe'

function Write-Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "    $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "    $msg" -ForegroundColor Yellow }

function Stop-CeleryWorker {
    # The worker runs as python.exe, so Get-Process celery never finds it - match on the
    # command line instead.
    $procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
             Where-Object { $_.CommandLine -like '*celery*' -and $_.CommandLine -like '*worker*' }
    if (-not $procs) {
        Write-Warn 'No running Celery worker found.'
        return
    }
    foreach ($p in $procs) {
        Write-Ok "Stopping worker (pid $($p.ProcessId))"
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

function Start-CeleryWorker {
    Start-Process -FilePath $celery `
        -ArgumentList '-A','config','worker','--loglevel=info','--pool=solo','--concurrency=1','-Q','default,gpu' `
        -WorkingDirectory $backend
    Write-Ok 'Celery worker starting in a new window (--pool=solo, queues: default,gpu)'
}

if (-not (Test-Path $python)) {
    throw "Python venv not found at $python. Expected backend\.venv to already exist."
}

# ── -Restart: swap the worker and stop ───────────────────────────────────────
if ($Restart) {
    Write-Step 'Restarting the Celery worker'
    Stop-CeleryWorker
    Start-Sleep -Seconds 2
    Start-CeleryWorker
    Write-Host ''
    Write-Host 'Worker restarted. It now holds the current code on disk.' -ForegroundColor Green
    return
}

# ── 1. Docker engine ─────────────────────────────────────────────────────────
Write-Step 'Checking Docker engine'
docker info --format '{{.ServerVersion}}' 2>$null | Out-Null
if (-not $?) {
    Write-Warn 'Engine not reachable - launching Docker Desktop (this takes 1-2 minutes from cold)'
    $dd = 'C:\Program Files\Docker\Docker\Docker Desktop.exe'
    if (-not (Test-Path $dd)) { throw "Docker Desktop not found at $dd" }
    Start-Process $dd

    $deadline = (Get-Date).AddMinutes(5)
    $ready = $false
    while ((Get-Date) -lt $deadline) {
        docker info --format '{{.ServerVersion}}' 2>$null | Out-Null
        if ($?) { $ready = $true; break }
        Start-Sleep -Seconds 5
    }
    if (-not $ready) { throw 'Docker engine did not become ready within 5 minutes.' }
}
Write-Ok "Docker engine ready ($(docker info --format '{{.ServerVersion}}'))"

# ── 2. Containers ────────────────────────────────────────────────────────────
# Note: the cv_engine service is deliberately excluded - it sits behind the "cv" compose
# profile and is not part of this flow.
Write-Step 'Starting Postgres and Redis'
Push-Location $root
try {
    $services = @('db','redis')
    if ($Adminer) { $services += 'adminer' }
    docker compose up -d @services | Out-Null
} finally {
    Pop-Location
}

# ── 3. Wait for Postgres to pass its healthcheck ─────────────────────────────
# Without this the migrate below races the container and fails on connection refused.
Write-Step 'Waiting for Postgres to become healthy'
$deadline = (Get-Date).AddMinutes(2)
$status = ''
while ((Get-Date) -lt $deadline) {
    $status = docker inspect --format '{{.State.Health.Status}}' ft_postgres 2>$null
    if ($status -eq 'healthy') { break }
    Start-Sleep -Seconds 3
}
if ($status -ne 'healthy') { throw "Postgres did not become healthy (last status: $status)" }
Write-Ok 'Postgres healthy on localhost:5434'

# ── 4. Migrations ────────────────────────────────────────────────────────────
Write-Step 'Applying migrations'
Push-Location $backend
try {
    & $python manage.py migrate
    if ($LASTEXITCODE -ne 0) { throw 'migrate failed' }
} finally {
    Pop-Location
}

# ── 5. Long-running processes, each in its own window ────────────────────────
# Separate windows on purpose: both are long-lived, and their logs are what you read when
# something breaks.
Write-Step 'Launching Django and Celery'
Start-Process -FilePath $python -ArgumentList 'manage.py','runserver' -WorkingDirectory $backend
Write-Ok 'Django dev server starting in a new window'
Start-CeleryWorker

# ── 6. Where things live ─────────────────────────────────────────────────────
Write-Host ''
Write-Host 'Stack is up:' -ForegroundColor Green
Write-Host '  API           http://localhost:8000'
Write-Host '  Django admin  http://localhost:8000/admin'
Write-Host '  Postgres      localhost:5434  (ft_user / ft_password / football_tracker)'
Write-Host '  Redis         localhost:6379'
if ($Adminer) { Write-Host '  Adminer       http://localhost:8080  (Server: db)' }
Write-Host ''
Write-Host '  Frontend:     cd frontend; npm run dev   ->  http://localhost:5173'
Write-Host ''
Write-Host 'Reminder: after editing cv_engine/ or backend/matches/, run' -ForegroundColor Yellow
Write-Host '  .\start-local.ps1 -Restart' -ForegroundColor Yellow
Write-Host 'Celery does not reload changed code.' -ForegroundColor Yellow
