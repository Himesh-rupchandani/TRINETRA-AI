# TRINETRA AI — Backend Only Starter (Windows PowerShell)
# Runs backend + seeds 30 cameras, fixes stale 4-camera OFFLINE DB

$ErrorActionPreference = "Stop"

# Resolve repo root from script location
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $Root "TRINETRAAI\backend"

Write-Host "== TRINETRA Backend Starter ==" -ForegroundColor Cyan
Write-Host "Backend dir: $BackendDir"

Set-Location $BackendDir

# Check Python
try {
    $py = Get-Command python -ErrorAction Stop
    Write-Host "Python found: $($py.Source)" -ForegroundColor Green
} catch {
    try {
        $py = Get-Command py -ErrorAction Stop
        Write-Host "Python launcher found: $($py.Source), using py -3" -ForegroundColor Green
        # Alias python to py -3 for this session via function
        function python { py -3 @args }
    } catch {
        Write-Host "Python not found. Install Python 3.10+ and add to PATH" -ForegroundColor Red
        exit 1
    }
}

# Create venv if missing
if (-not (Test-Path ".\.venv")) {
    Write-Host "Creating venv .venv..." -ForegroundColor Yellow
    python -m venv .venv
}

# Activate venv
Write-Host "Activating venv..." -ForegroundColor Yellow
& ".\.venv\Scripts\Activate.ps1"

# Install requirements
Write-Host "Installing requirements..." -ForegroundColor Yellow
pip install -r requirements.txt

# ultralytics may pull GUI OpenCV after the headless wheel. Repair cv2 with
# the active venv interpreter so the backend also works on headless systems.
Write-Host "Ensuring headless OpenCV..." -ForegroundColor Yellow
python (Join-Path $Root "scripts\ensure_headless_opencv.py")

# Ensure evidence dir exists (backend+frontend only may not have cv-engine/evidence)
$EvidenceRoot = Join-Path $Root "cv-engine\evidence"
if (-not (Test-Path $EvidenceRoot)) {
    Write-Host "Creating evidence dir at $EvidenceRoot" -ForegroundColor Yellow
    New-Item -ItemType Directory -Force -Path $EvidenceRoot | Out-Null
}

# Seed — now auto-fixes stale DB (4 cameras OFFLINE -> 30 ONLINE)
Write-Host "Seeding demo DB (30 cameras)..." -ForegroundColor Yellow
python -m scripts.seed_demo

# If still old DB exists, offer hard reset
$dbPath = Join-Path $BackendDir "trinetra.db"
if (Test-Path $dbPath) {
    # Quick check: count cameras via python
    $count = python -c "from app.database.database import SessionLocal; from app.database.models import Camera; db=SessionLocal(); print(db.query(Camera).count()); db.close()" 2>$null
    Write-Host "Current camera count in DB: $count" -ForegroundColor Cyan
    if ($count -ne "30") {
        Write-Host "DB still not 30 cameras, doing hard reset..." -ForegroundColor Yellow
        Remove-Item $dbPath -Force
        python -m scripts.seed_demo
    }
}

Write-Host ""
Write-Host "Starting backend at http://localhost:8000" -ForegroundColor Green
Write-Host "Health: http://localhost:8000/api/health  Docs: http://localhost:8000/docs" -ForegroundColor Green
Write-Host ""

# Run uvicorn
uvicorn app.main:app --host 0.0.0.0 --port 8000
