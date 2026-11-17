# Smart AI Gateway - Automated Production Deployment Script (PowerShell)
param(
    [string]$Mode = "auto",     # "auto", "docker", "native"
    [int]$Port = 8000,
    [switch]$Foreground = $false
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "       Smart AI Gateway - Production Deployment          " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Project Root: $ProjectRoot" -ForegroundColor Gray
Write-Host "Target Port : $Port" -ForegroundColor Gray
Write-Host ""

Set-Location $ProjectRoot

# Function to verify health endpoints
function Test-GatewayHealth {
    param([int]$TargetPort)
    $maxAttempts = 15
    $attempt = 1
    Write-Host "Verifying service health..." -ForegroundColor Yellow
    while ($attempt -le $maxAttempts) {
        try {
            $response = Invoke-RestMethod -Uri "http://localhost:$TargetPort/health/live" -Method Get -TimeoutSec 3 -ErrorAction Stop
            if ($response.status -eq "live" -or $response.status -eq "ok") {
                Write-Host "[✔] Liveness probe passed: http://localhost:$TargetPort/health/live" -ForegroundColor Green
                try {
                    $ready = Invoke-RestMethod -Uri "http://localhost:$TargetPort/health/ready" -Method Get -TimeoutSec 3 -ErrorAction SilentlyContinue
                    Write-Host "[✔] Readiness probe passed: http://localhost:$TargetPort/health/ready" -ForegroundColor Green
                } catch {
                    Write-Host "[!] Readiness probe returned pending (initializing DB)." -ForegroundColor Yellow
                }
                return $true
            }
        } catch {
            Start-Sleep -Seconds 1
            $attempt++
        }
    }
    return $false
}

# 1. Check Docker availability
$dockerAvailable = $false
if ($Mode -ne "native") {
    try {
        $dockerCheck = docker ps 2>&1
        if ($LASTEXITCODE -eq 0) {
            $dockerAvailable = $true
        }
    } catch {
        $dockerAvailable = $false
    }
}

if ($dockerAvailable -and $Mode -ne "native") {
    Write-Host "[INFO] Docker engine detected. Deploying via Docker Compose..." -ForegroundColor Green
    docker compose -f "$ScriptDir/docker-compose.yml" build
    docker compose -f "$ScriptDir/docker-compose.yml" up -d
    
    $healthy = Test-GatewayHealth -TargetPort $Port
    if ($healthy) {
        Write-Host ""
        Write-Host "==========================================================" -ForegroundColor Green
        Write-Host "       DEPLOYMENT SUCCESSFUL (Docker Container)           " -ForegroundColor Green
        Write-Host "==========================================================" -ForegroundColor Green
        Write-Host "Playground UI : http://localhost:$Port" -ForegroundColor Cyan
        Write-Host "Swagger Docs  : http://localhost:$Port/docs" -ForegroundColor Cyan
        Write-Host "Health Check  : http://localhost:$Port/health/live" -ForegroundColor Cyan
        Write-Host "==========================================================" -ForegroundColor Green
    } else {
        Write-Host "[ERROR] Health check timed out. Check container logs with: docker logs smart-ai-gateway" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "[INFO] Deploying native production server with Python/Uvicorn..." -ForegroundColor Yellow
    
    # Locate virtual environment Python
    $pythonExe = "$ProjectRoot\.venv\Scripts\python.exe"
    if (-not (Test-Path $pythonExe)) {
        $pythonExe = "python"
    }

    # Verify dependencies
    Write-Host "Checking runtime packages..." -ForegroundColor Gray
    & $pythonExe -m pip install -q -r "$ProjectRoot\requirements.txt"
    & $pythonExe -m pip install -q -e "$ProjectRoot"

    # Start production server process in background
    Write-Host "Starting Uvicorn production server on port $Port..." -ForegroundColor Green
    $env:APP_ENV = "production"
    $env:APP_PORT = "$Port"
    $env:APP_HOST = "0.0.0.0"
    $env:PYTHONPATH = "$ProjectRoot"

    if ($Foreground) {
        Write-Host "Running Uvicorn in foreground (Press Ctrl+C to terminate)..." -ForegroundColor Cyan
        & $pythonExe -m uvicorn app.main:app --host 0.0.0.0 --port $Port
        exit 0
    }

    # Start detached process
    $proc = Start-Process -FilePath $pythonExe -ArgumentList "-m uvicorn app.main:app --host 0.0.0.0 --port $Port" -WorkingDirectory $ProjectRoot -PassThru -WindowStyle Hidden

    $healthy = Test-GatewayHealth -TargetPort $Port
    if ($healthy) {
        Write-Host ""
        Write-Host "==========================================================" -ForegroundColor Green
        Write-Host "       DEPLOYMENT SUCCESSFUL (Native Production Server)   " -ForegroundColor Green
        Write-Host "==========================================================" -ForegroundColor Green
        Write-Host "Process ID    : $($proc.Id)" -ForegroundColor Gray
        Write-Host "Playground UI : http://localhost:$Port" -ForegroundColor Cyan
        Write-Host "Swagger Docs  : http://localhost:$Port/docs" -ForegroundColor Cyan
        Write-Host "Health Check  : http://localhost:$Port/health/live" -ForegroundColor Cyan
        Write-Host "==========================================================" -ForegroundColor Green
    } else {
        Write-Host "[ERROR] Service did not become ready within timeout." -ForegroundColor Red
        exit 1
    }
}
