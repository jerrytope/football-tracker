<#
.SYNOPSIS
    Bring the football-tracker stack up locally on Windows or macOS.

.DESCRIPTION
    Starts Docker (if needed), the Postgres and Redis containers, applies migrations, and
    launches the Django dev server and the Celery worker. Creates backend/.venv automatically
    on first run if it doesn't exist yet.

    On Windows, Django and Celery each launch in their own console window, and the Celery
    worker MUST use --pool=solo: the default prefork pool relies on fork() and will hang.
    On macOS/Linux, prefork works fine, so the worker runs with Celery's normal defaults;
    both processes run in the background with output redirected to logs/*.log, since there
    is no cross-platform way to pop open a new terminal window from a script.

    Run this with Windows PowerShell (powershell.exe) on Windows, or with PowerShell 7+
    (pwsh) on macOS - install it with `brew install --cask powershell` if you don't have it.

.PARAMETER Restart
    Kill the running Celery worker and start a fresh one, then exit. Use this after editing
    anything under cv_engine/ or backend/matches/ - Celery does not reload changed code, and
    a stale worker will keep producing pre-edit behaviour.

.PARAMETER Stop
    Stop the Django dev server and the Celery worker, then exit. Mainly useful on
    macOS/Linux, where both run in the background with no window to just close.

.PARAMETER Adminer
    Also start the Adminer database inspector on http://localhost:8080.

.EXAMPLE
    .\start-local.ps1
    .\start-local.ps1 -Restart
    .\start-local.ps1 -Stop
    .\start-local.ps1 -Adminer
#>
[CmdletBinding()]
param(
    [switch]$Restart,
    [switch]$Stop,
    [switch]$Adminer
)

$ErrorActionPreference = 'Stop'

# $IsWindows / $IsMacOS only exist in PowerShell Core (pwsh, 6+). Windows PowerShell 5.1 has
# neither, so their absence itself means Windows.
$IsWin = if (Test-Path Variable:IsWindows) { $IsWindows } else { $true }
$IsMac = if (Test-Path Variable:IsMacOS) { $IsMacOS } else { $false }

$root = $PSScriptRoot
$backend = Join-Path $root 'backend'
$logDir = Join-Path $root 'logs'

if ($IsWin) {
    $python = Join-Path $backend '.venv\Scripts\python.exe'
    $pip = Join-Path $backend '.venv\Scripts\pip.exe'
    $celery = Join-Path $backend '.venv\Scripts\celery.exe'
    $systemPython = 'python'
} else {
    $python = Join-Path $backend '.venv/bin/python'
    $pip = Join-Path $backend '.venv/bin/pip'
    $celery = Join-Path $backend '.venv/bin/celery'
    $systemPython = 'python3'
}

function Write-Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "    $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "    $msg" -ForegroundColor Yellow }

function Get-MatchingProcessIds($commandLineFragments) {
    # Returns PIDs of processes whose command line contains every fragment given.
    if ($IsWin) {
        $procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
                 Where-Object {
                     $cmd = $_.CommandLine
                     if (-not $cmd) { return $false }
                     foreach ($f in $commandLineFragments) { if ($cmd -notlike "*$f*") { return $false } }
                     return $true
                 }
        return $procs | ForEach-Object { $_.ProcessId }
    } else {
        $pattern = $commandLineFragments -join '.*'
        $found = & pgrep -f $pattern 2>$null
        if (-not $found) { return @() }
        return $found
    }
}

function Stop-ProcessesByPattern($commandLineFragments, $label) {
    $ids = Get-MatchingProcessIds $commandLineFragments
    if (-not $ids) {
        Write-Warn "No running $label found."
        return
    }
    foreach ($procId in $ids) {
        Write-Ok "Stopping $label (pid $procId)"
        if ($IsWin) {
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        } else {
            & kill -TERM $procId 2>$null
        }
    }
}

function Stop-CeleryWorker { Stop-ProcessesByPattern @('celery', 'worker') 'Celery worker' }
function Stop-DjangoServer { Stop-ProcessesByPattern @('manage.py', 'runserver') 'Django dev server' }

function Start-CeleryWorker {
    if ($IsWin) {
        # --pool=solo is mandatory on Windows: the default prefork pool relies on fork(),
        # which Windows doesn't have, and the worker just hangs.
        Start-Process -FilePath $celery `
            -ArgumentList '-A','config','worker','--loglevel=info','--pool=solo','--concurrency=1','-Q','default,gpu' `
            -WorkingDirectory $backend
        Write-Ok 'Celery worker starting in a new window (--pool=solo, queues: default,gpu)'
    } else {
        New-Item -ItemType Directory -Force -Path $logDir | Out-Null
        Start-Process -FilePath $celery `
            -ArgumentList '-A','config','worker','--loglevel=info','-Q','default,gpu' `
            -WorkingDirectory $backend -NoNewWindow `
            -RedirectStandardOutput (Join-Path $logDir 'celery.log') `
            -RedirectStandardError (Join-Path $logDir 'celery.err.log')
        Write-Ok 'Celery worker starting in background (prefork, queues: default,gpu; logs: logs/celery.log)'
    }
}

function Test-Or-CreateVenv {
    if (Test-Path $python) { return }
    Write-Step 'No virtual environment found at backend/.venv - creating one'

    $sysPythonCmd = Get-Command $systemPython -ErrorAction SilentlyContinue
    if (-not $sysPythonCmd) {
        throw "'$systemPython' was not found on PATH. Install Python 3 first" + $(if ($IsMac) { " (e.g. 'brew install python')." } else { '.' })
    }

    & $systemPython -m venv (Join-Path $backend '.venv')
    if ($LASTEXITCODE -ne 0) { throw "'$systemPython -m venv' failed." }

    Write-Step 'Installing backend dependencies (first run only, this can take a few minutes)'
    & $pip install --upgrade pip | Out-Null
    & $pip install -r (Join-Path $backend 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'pip install -r requirements.txt failed.' }
    Write-Ok 'Virtual environment ready'
}

# ── -Stop: stop both long-running processes and exit ─────────────────────────
if ($Stop) {
    Write-Step 'Stopping Django and Celery'
    Stop-DjangoServer
    Stop-CeleryWorker
    return
}

# ── -Restart: swap the worker and exit ────────────────────────────────────────
if ($Restart) {
    Write-Step 'Restarting the Celery worker'
    Stop-CeleryWorker
    Start-Sleep -Seconds 2
    Start-CeleryWorker
    Write-Host ''
    Write-Host 'Worker restarted. It now holds the current code on disk.' -ForegroundColor Green
    return
}

# ── 0. Virtual environment ────────────────────────────────────────────────────
Test-Or-CreateVenv

# ── 1. Docker engine ─────────────────────────────────────────────────────────
Write-Step 'Checking Docker engine'
docker info --format '{{.ServerVersion}}' 2>$null | Out-Null
if (-not $?) {
    Write-Warn 'Engine not reachable - launching Docker Desktop (this takes 1-2 minutes from cold)'
    if ($IsWin) {
        $dd = 'C:\Program Files\Docker\Docker\Docker Desktop.exe'
        if (-not (Test-Path $dd)) { throw "Docker Desktop not found at $dd" }
        Start-Process $dd
    } else {
        $dockerApp = '/Applications/Docker.app'
        if (-not (Test-Path $dockerApp)) {
            throw "Docker Desktop not found at $dockerApp. Install it from https://www.docker.com/products/docker-desktop"
        }
        & open -a Docker
    }

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

# ── 5. Long-running processes ─────────────────────────────────────────────────
Write-Step 'Launching Django and Celery'
if ($IsWin) {
    Start-Process -FilePath $python -ArgumentList 'manage.py','runserver' -WorkingDirectory $backend
    Write-Ok 'Django dev server starting in a new window'
} else {
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    Start-Process -FilePath $python -ArgumentList 'manage.py','runserver' -WorkingDirectory $backend -NoNewWindow `
        -RedirectStandardOutput (Join-Path $logDir 'django.log') `
        -RedirectStandardError (Join-Path $logDir 'django.err.log')
    Write-Ok 'Django dev server starting in background (logs: logs/django.log)'
}
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
if (-not $IsWin) {
    Write-Host '  Logs:         tail -f logs/django.log logs/celery.log' -ForegroundColor Cyan
    Write-Host '  Stop:         .\start-local.ps1 -Stop' -ForegroundColor Cyan
    Write-Host ''
}
Write-Host 'Reminder: after editing cv_engine/ or backend/matches/, run' -ForegroundColor Yellow
Write-Host '  .\start-local.ps1 -Restart' -ForegroundColor Yellow
Write-Host 'Celery does not reload changed code.' -ForegroundColor Yellow
