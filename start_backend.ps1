# AI Arena Fight — Backend Startup Script
# Usage: .\start_backend.ps1

Write-Host "Starting AI Arena Fight Backend..." -ForegroundColor Cyan

# Activate venv if not already active
if (-not $env:VIRTUAL_ENV) {
    & ".\.venv\Scripts\Activate.ps1"
}

# Run uvicorn — watch only source dir, not .venv (avoids ghost path errors)
uvicorn backend_arena.src.main:app `
    --reload `
    --reload-dir backend_arena `
    --host 0.0.0.0 `
    --port 8000
