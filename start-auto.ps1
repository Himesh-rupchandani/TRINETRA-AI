# TRINETRA AI — AUTO-START with live camera & auto-login (Windows)
# No manual email/password needed — credentials auto-injected

Write-Host "🚀 TRINETRA AI — Auto-starting with hackathon live cameras" -ForegroundColor Green
Write-Host "   Credentials auto-injected, no manual login required" -ForegroundColor Cyan

$Root = $PSScriptRoot
$Frontend = Join-Path $Root "trinetra-ai"
$Backend = Join-Path $Root "TRINETRAAI\backend"

# --- Frontend .env ---
$frontendEnv = @"
# AUTO-CONFIGURED — no manual email/password needed
VITE_USE_MOCKS=false
VITE_API_BASE_URL=/api
BACKEND_ORIGIN=http://localhost:8000
VITE_REALTIME_TRANSPORT=sse
VITE_MAP_CENTER_LAT=22.3000
VITE_MAP_CENTER_LNG=71.6000
VITE_MAP_DEFAULT_ZOOM=7
SENTINEL_WHEP_ORIGIN=http://103.250.160.189:8889
SENTINEL_HLS_ORIGIN=http://103.250.160.189:80
SENTINEL_EMAIL=himesh.rupchandani140850@marwadiuniversity.ac.in
SENTINEL_PASSWORD=A7UX-7TRC-BVS6
VITE_STREAM_BASE_PATH=/sentinel/stream
VITE_LIVE_STREAMS=true
VITE_AUTO_LOGIN=true
VITE_DEFAULT_LIVE_CAMERA=cam04
"@

Set-Content -Path (Join-Path $Frontend ".env") -Value $frontendEnv -Encoding utf8
Set-Content -Path (Join-Path $Frontend ".env.local") -Value $frontendEnv -Encoding utf8
Write-Host "✅ Frontend .env auto-configured" -ForegroundColor Green

# --- Backend .env ---
$backendEnv = @"
PROJECT_NAME="TRINETRA AI - Intelligent CCTV Surveillance"
APP_ENV=development
DEBUG=true
PORT=8000
HOST=0.0.0.0
LIVE_CAMERA_ID=CAMLIVE
LIVE_CAMERA_NAME=SG Highway Junction, Ahmedabad - Live
LIVE_CAMERA_LOCATION=Ahmedabad, Gujarat
LIVE_CAMERA_STREAM_TYPE=rtsp
LIVE_CAMERA_STREAM_URL=
LIVE_CAMERA_STATUS=
AUTO_START_CAMERAS=true
EVIDENCE_ROOT=../../cv-engine/evidence
SENTINEL_EMAIL=himesh.rupchandani140850@marwadiuniversity.ac.in
SENTINEL_PASSWORD=A7UX-7TRC-BVS6
SENTINEL_CATALOGUE_URL=https://cctv.corp8.cloud/cameras.json
SENTINEL_HLS_BASE_URL=https://cctv.corp8.cloud
SENTINEL_RTSP_HOST=103.250.160.189
SENTINEL_RTSP_PORT=8554
DATABASE_URL=sqlite:///./trinetra.db
REDIS_URL=redis://localhost:6379/0
DEFAULT_CAMERA_STREAM_URL=https://cctv.corp8.cloud/cam04/index.m3u8
DEFAULT_CAMERA_STREAM_TYPE=hls
RTSP_TRANSPORT=tcp
YOLO_MODEL_PATH=models/yolo11s.pt
CONFIDENCE_THRESHOLD=0.45
PROCESS_EVERY_N_FRAMES=3
OCR_ENABLED=true
OCR_MIN_CONFIDENCE=0.60
DEMO_MODE=true
CORS_ORIGINS=["http://localhost:3000","http://localhost:5173","http://127.0.0.1:5173","http://127.0.0.1:3000"]
MAX_UPLOAD_SIZE_MB=250
UPLOAD_DIR=uploads
AUTO_LOGIN=true
"@

Set-Content -Path (Join-Path $Backend ".env") -Value $backendEnv -Encoding utf8
Write-Host "✅ Backend .env auto-configured" -ForegroundColor Green

# --- Check deps ---
if (-not (Test-Path (Join-Path $Frontend "node_modules"))) {
    Write-Host "📦 Installing frontend deps..." -ForegroundColor Yellow
    Push-Location $Frontend
    npm install
    Pop-Location
}

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
Write-Host "   Live camera: auto-connected via Sentinel (no manual login)" -ForegroundColor Cyan
Write-Host "   Open: http://localhost:5173" -ForegroundColor White
Write-Host ""

# Start backend in new window
Start-Process -FilePath "powershell" -ArgumentList "-NoExit", "-Command", "cd '$Backend'; uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
Start-Sleep -Seconds 3

# Start frontend
Push-Location $Frontend
npm run dev
Pop-Location
