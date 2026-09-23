# Employability AI — Quick Start Script
$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

$python = Join-Path $scriptDir ".venv\Scripts\python.exe"
$webapp = Join-Path $scriptDir "src\agent-framework-agent-basic-responses\webapp.py"

if (-not (Test-Path $python)) {
    Write-Host "Virtual environment not found at $python. Please ensure .venv is configured." -ForegroundColor Red
    exit 1
}

Write-Host "Starting Employability AI on http://localhost:8080 ..." -ForegroundColor Cyan
& $python $webapp
