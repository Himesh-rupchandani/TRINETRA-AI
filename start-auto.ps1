# TRINETRA AI — AUTO-START (frontend only, Windows)
#
# The FastAPI backend that used to live in TRINETRAAI\backend was removed from
# this repository. This script now only prepares and starts the frontend.
# To browse the UI without a backend, set VITE_USE_MOCKS=true in
# trinetra-ai\.env (the setup script below never overwrites existing values).
#
# Credentials policy (important):
#   * this script contains NO credentials — nothing secret is committed here;
#   * env files are CREATED ONLY WHEN MISSING and are NEVER overwritten, so an
#     operator's own values (gateway login, VITE_MAPBOX_TOKEN, ports…) survive
#     every run.

Write-Host "🚀 TRINETRA AI — Auto-starting (frontend)" -ForegroundColor Green
Write-Host "   Env files are created only when missing; existing values are preserved" -ForegroundColor Cyan

$Root = $PSScriptRoot
$Frontend = Join-Path $Root "trinetra-ai"

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
}

# --- Warn (never print) when the gateway credentials are still empty ---------
$frontendEnvFile = Join-Path $Frontend ".env"
$hasEmail = (Test-Path $frontendEnvFile) -and (Select-String -Path $frontendEnvFile -Pattern '^SENTINEL_EMAIL=.+' -Quiet)
$hasPassword = (Test-Path $frontendEnvFile) -and (Select-String -Path $frontendEnvFile -Pattern '^SENTINEL_PASSWORD=.+' -Quiet)
if (-not ($hasEmail -and $hasPassword)) {
    Write-Host "⚠️  Sentinel gateway credentials are empty in $frontendEnvFile" -ForegroundColor Yellow
    Write-Host "   Live camera playback needs SENTINEL_EMAIL + SENTINEL_PASSWORD." -ForegroundColor Yellow
}

# --- Check deps ---
if (-not (Test-Path (Join-Path $Frontend "node_modules"))) {
    Write-Host "📦 Installing frontend deps..." -ForegroundColor Yellow
    Push-Location $Frontend
    npm install
    Pop-Location
}

Write-Host ""
Write-Host "🎬 Starting frontend (5173)..." -ForegroundColor Green
Write-Host "   Open: http://localhost:5173" -ForegroundColor White
Write-Host ""

Push-Location $Frontend
npm run dev
Pop-Location
