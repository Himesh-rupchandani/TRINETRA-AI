# TRINETRA AI — AUTO-START with live camera support (Windows)
#
# Credentials policy (important):
#   * this script contains NO credentials — nothing secret is committed here;
#   * env files are CREATED ONLY WHEN MISSING and are NEVER overwritten, so an
#     operator's own values (gateway login, VITE_MAPBOX_TOKEN, ports…) survive
#     every run;
#   * credentials are resolved from the environment or from an env file that
#     already exists on this machine (see trinetra-ai\scripts\auto-setup-env.mjs).

Write-Host "🚀 TRINETRA AI — Auto-starting" -ForegroundColor Green
Write-Host "   Env files are created only when missing; existing values are preserved" -ForegroundColor Cyan

$Root = $PSScriptRoot
$Frontend = Join-Path $Root "trinetra-ai"
$Backend = Join-Path $Root "TRINETRAAI\backend"

# --- Env files: create-if-missing, never clobber -----------------------------
$nodeAvailable = $null -ne (Get-Command node -ErrorAction SilentlyContinue)
if ($nodeAvailable) {
    Push-Location $Frontend
    node scripts/auto-setup-env.mjs
    Pop-Location
} else {
    Write-Host "⚠️  node not found — falling back to a plain .env.example copy" -ForegroundColor Yellow
    $frontendEnvPath = Join-Path $Frontend ".env"
    if (-not (Test-Path $frontendEnvPath)) {
        Copy-Item (Join-Path $Frontend ".env.example") $frontendEnvPath
    }
    $backendEnvPath = Join-Path $Backend ".env"
    if (-not (Test-Path $backendEnvPath)) {
        # Copy the template and blank the credential lines: they must be filled
        # in locally (or set as environment variables), never shipped from here.
        (Get-Content (Join-Path $Backend ".env.example")) -replace '^(SENTINEL_EMAIL|SENTINEL_PASSWORD)=.*', '$1=' |
            Set-Content -Path $backendEnvPath -Encoding utf8
    }
}

# --- Warn (never print) when the gateway credentials are still empty ---------
$frontendEnvFile = Join-Path $Frontend ".env"
$hasEmail = (Test-Path $frontendEnvFile) -and (Select-String -Path $frontendEnvFile -Pattern '^SENTINEL_EMAIL=.+' -Quiet)
$hasPassword = (Test-Path $frontendEnvFile) -and (Select-String -Path $frontendEnvFile -Pattern '^SENTINEL_PASSWORD=.+' -Quiet)
if (-not ($hasEmail -and $hasPassword)) {
    Write-Host "⚠️  Sentinel gateway credentials are empty in $frontendEnvFile" -ForegroundColor Yellow
    Write-Host "   Live camera playback needs SENTINEL_EMAIL + SENTINEL_PASSWORD." -ForegroundColor Yellow
    Write-Host "   Everything else (ANPR pipeline, alerts, evidence, analytics) works without them." -ForegroundColor Yellow
}

# --- Check deps ---
if (-not (Test-Path (Join-Path $Frontend "node_modules"))) {
    Write-Host "📦 Installing frontend deps..." -ForegroundColor Yellow
    Push-Location $Frontend
    npm install
    Pop-Location
}

# Keep the server-side cv2 import on the headless build when ultralytics has
# also installed its GUI opencv dependency.
Write-Host "Ensuring headless OpenCV..." -ForegroundColor Yellow
python (Join-Path $Root "scripts\ensure_headless_opencv.py")

# --- Seed DB ---
$trinetraDb1 = Join-Path $Root "TRINETRAAI\trinetra.db"
$trinetraDb2 = Join-Path $Backend "trinetra.db"
if (-not (Test-Path $trinetraDb1) -and -not (Test-Path $trinetraDb2)) {
    Write-Host "🌱 Seeding demo DB..." -ForegroundColor Yellow
    Push-Location $Backend
    try { python -m scripts.seed_demo } catch { Write-Host "Seed skipped" }
    Pop-Location
}

Write-Host ""
Write-Host "🎬 Starting backend (8000) and frontend (5173)..." -ForegroundColor Green
Write-Host "   Open: http://localhost:5173" -ForegroundColor White
Write-Host ""

# Start backend in new window
Start-Process -FilePath "powershell" -ArgumentList "-NoExit", "-Command", "cd '$Backend'; uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
Start-Sleep -Seconds 3

# Start frontend
Push-Location $Frontend
npm run dev
Pop-Location
