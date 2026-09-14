# TRINETRA AI — AUTO-START with live camera support (Windows PowerShell)
#
# Credentials policy (important):
#   * this script contains NO credentials — nothing secret is committed here;
#   * env files are CREATED ONLY WHEN MISSING and are NEVER overwritten, so an
#     operator's own values (gateway login, VITE_MAPBOX_TOKEN, ports…) survive
#     every run;
#   * credentials are resolved from the environment or from an env file that
#     already exists on this machine (see trinetra-ai/scripts/auto-setup-env.mjs).
#
# FILE FORMAT NOTE: this script MUST stay CRLF + UTF-8 BOM (see .gitattributes
# rule for *.ps1) — Windows PowerShell 5.1 reads emoji as garbage without the
# BOM and handles CRLF most reliably.

Write-Host "🚀 TRINETRA AI — Auto-starting" -ForegroundColor Green
Write-Host "   Env files are created only when missing; existing values are preserved" -ForegroundColor Cyan

$Root = $PSScriptRoot
$Frontend = Join-Path $Root "trinetra-ai"
$Backend = Join-Path $Root "TRINETRAAI\backend"
$frontendEnvPath = Join-Path $Frontend ".env"
$backendEnvPath = Join-Path $Backend ".env"

# --- Prerequisites ---
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Host "❌ npm (Node.js) not found. Install Node.js 18+ from nodejs.org, then re-run." -ForegroundColor Red
    exit 1
}

# --- Env files: create-if-missing, never clobber -----------------------------
# The Node setup script is the single implementation of that policy; it also
# appends missing keys and resolves Sentinel credentials from this machine.
if (Get-Command node -ErrorAction SilentlyContinue) {
    Push-Location $Frontend
    node scripts/auto-setup-env.mjs
    Pop-Location
} else {
    Write-Host "⚠️  node not found — falling back to a plain .env.example copy" -ForegroundColor Yellow
    if (-not (Test-Path $frontendEnvPath)) {
        Copy-Item (Join-Path $Frontend ".env.example") $frontendEnvPath
    }
    if (-not (Test-Path $backendEnvPath)) {
        # Copy the template and blank the credential lines: they must be filled
        # in locally (or exported), never shipped with a value from this script.
        $example = Get-Content (Join-Path $Backend ".env.example")
        $example -replace '^(SENTINEL_EMAIL|SENTINEL_PASSWORD)=.*', '$1=' |
            Set-Content -Path $backendEnvPath -Encoding utf8
    }
}

# --- Warn (never print) when the gateway credentials are still empty ---------
$envLines = Get-Content $frontendEnvPath -ErrorAction SilentlyContinue
if (($envLines | Where-Object { $_ -match '^SENTINEL_EMAIL=.' }).Count -eq 0 -or
    ($envLines | Where-Object { $_ -match '^SENTINEL_PASSWORD=.' }).Count -eq 0) {
    Write-Host "⚠️  Sentinel gateway credentials are empty in $frontendEnvPath" -ForegroundColor Yellow
    Write-Host "   Live camera playback needs SENTINEL_EMAIL + SENTINEL_PASSWORD." -ForegroundColor Yellow
    Write-Host "   Everything else (ANPR pipeline, alerts, evidence, analytics) works without them." -ForegroundColor Yellow
}

# --- Frontend deps ---
if (-not (Test-Path (Join-Path $Frontend "node_modules"))) {
    Write-Host "📦 Installing frontend deps..." -ForegroundColor Yellow
    Push-Location $Frontend
    npm install
    Pop-Location
}

# --- Backend Python env (created only when missing) --------------------------
$VenvPy = Join-Path $Backend ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPy)) {
    Write-Host "🐍 First run: creating Python environment + installing backend deps (a few minutes)..." -ForegroundColor Yellow
    Push-Location $Backend
    try { python -m venv .venv } catch {
        Write-Host "❌ Python not found (or venv failed). Install Python 3.10-3.12 from python.org (check 'Add to PATH'), then re-run." -ForegroundColor Red
        Pop-Location
        exit 1
    }
    & $VenvPy -m pip install --upgrade pip
    # CPU-only torch from the PyTorch index (small); fall back to PyPI if the
    # index is unreachable. requirements.txt documents the same order.
    & $VenvPy -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
    if ($LASTEXITCODE -ne 0) { & $VenvPy -m pip install torch torchvision }
    & $VenvPy -m pip install -r requirements.txt
    Pop-Location
    if (-not (Test-Path $VenvPy)) {
        Write-Host "❌ Python environment setup failed — see the errors above." -ForegroundColor Red
        exit 1
    }
    Write-Host "✅ Backend Python environment ready" -ForegroundColor Green
}

# ultralytics may pull GUI OpenCV after the headless wheel — repair cv2 with
# the same interpreter that will run the backend (never prints credentials).
if (Test-Path $VenvPy) {
    Push-Location $Root
    & $VenvPy (Join-Path "scripts" "ensure_headless_opencv.py")
    Pop-Location
}

# --- Seed DB if empty ---
$trinetraDb1 = Join-Path $Root "TRINETRAAI\trinetra.db"
$trinetraDb2 = Join-Path $Backend "trinetra.db"
if (-not (Test-Path $trinetraDb1) -and -not (Test-Path $trinetraDb2)) {
    Write-Host "🌱 Seeding demo DB..." -ForegroundColor Yellow
    Push-Location $Backend
    try { & $VenvPy -m scripts.seed_demo } catch { Write-Host "Seed skipped (run it manually from TRINETRAAI/backend)" }
    Pop-Location
}

Write-Host ""
Write-Host "🎬 Starting backend (8000) and frontend (5173)..." -ForegroundColor Green
Write-Host "   Live camera: auto-connected via Sentinel (no manual login)" -ForegroundColor Cyan
Write-Host "   Open: http://localhost:5173" -ForegroundColor White
Write-Host ""

# Start backend in new window (uses the venv uvicorn)
Start-Process -FilePath "powershell" -ArgumentList "-NoExit", "-Command", "cd '$Backend'; .\.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
Start-Sleep -Seconds 3

# Start frontend
Push-Location $Frontend
npm run dev
Pop-Location
