# TRINETRA AI — Frontend Only Starter (Windows PowerShell)
# Runs frontend in backend+frontend mode (VITE_USE_MOCKS=false)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$FrontendDir = Join-Path $Root "trinetra-ai"

Write-Host "== TRINETRA Frontend Starter ==" -ForegroundColor Cyan
Write-Host "Frontend dir: $FrontendDir"

Set-Location $FrontendDir

# Check Node
try {
    $node = Get-Command node -ErrorAction Stop
    Write-Host "Node found: $(node -v)" -ForegroundColor Green
} catch {
    Write-Host "Node.js not found. Install Node 20+ from https://nodejs.org" -ForegroundColor Red
    exit 1
}

# Check .env exists and has correct mode
$envPath = Join-Path $FrontendDir ".env"
if (-not (Test-Path $envPath)) {
    Write-Host ".env not found, copying from .env.example" -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
}

$envContent = Get-Content $envPath -Raw
if ($envContent -notmatch "VITE_USE_MOCKS=false") {
    Write-Host "WARNING: .env has VITE_USE_MOCKS=true — backend mode needs false" -ForegroundColor Yellow
    Write-Host "Fixing .env to backend+frontend mode..." -ForegroundColor Yellow
    $envContent = $envContent -replace "VITE_USE_MOCKS=true", "VITE_USE_MOCKS=false"
    if ($envContent -notmatch "BACKEND_ORIGIN") {
        $envContent += "`nBACKEND_ORIGIN=http://localhost:8000`n"
    }
    Set-Content -Path $envPath -Value $envContent
}

if ($envContent -notmatch "BACKEND_ORIGIN") {
    Write-Host "Adding BACKEND_ORIGIN to .env" -ForegroundColor Yellow
    Add-Content -Path $envPath -Value "`nBACKEND_ORIGIN=http://localhost:8000"
}

# Install deps if needed
if (-not (Test-Path "node_modules")) {
    Write-Host "Installing npm deps..." -ForegroundColor Yellow
    npm install
}

Write-Host ""
Write-Host "Starting frontend at http://localhost:5173" -ForegroundColor Green
Write-Host "Make sure backend is running at http://localhost:8000" -ForegroundColor Cyan
Write-Host "If you see OFFLINE, check backend health: http://localhost:8000/api/health" -ForegroundColor Cyan
Write-Host ""

npm run dev
