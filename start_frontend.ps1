# AI Arena Fight — Frontend (Creator Dashboard) Startup Script
# Usage: .\start_frontend.ps1

Write-Host "Starting AI Arena Fight Creator Dashboard..." -ForegroundColor Magenta

# Activate venv if not already active
if (-not $env:VIRTUAL_ENV) {
    & ".\.venv\Scripts\Activate.ps1"
}

# Run Streamlit dashboard
streamlit run creator_dashboard/app.py
