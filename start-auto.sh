#!/bin/bash
# TRINETRA AI — AUTO-START with live camera & auto-login
# No manual email/password needed — credentials auto-injected

set -e

echo "🚀 TRINETRA AI — Auto-starting with hackathon live cameras"
echo "   Credentials auto-injected, no manual login required"

# Root dir
ROOT="$(cd "$(dirname "$0")" && pwd)"
FRONTEND="$ROOT/trinetra-ai"
BACKEND="$ROOT/TRINETRAAI/backend"

# --- Ensure frontend .env has auto credentials ---
cat > "$FRONTEND/.env" <<'ENV'
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
ENV

cat > "$FRONTEND/.env.local" <<'ENV'
VITE_USE_MOCKS=false
VITE_API_BASE_URL=/api
BACKEND_ORIGIN=http://localhost:8000
VITE_REALTIME_TRANSPORT=sse
SENTINEL_WHEP_ORIGIN=http://103.250.160.189:8889
SENTINEL_HLS_ORIGIN=http://103.250.160.189:80
SENTINEL_EMAIL=himesh.rupchandani140850@marwadiuniversity.ac.in
SENTINEL_PASSWORD=A7UX-7TRC-BVS6
VITE_STREAM_BASE_PATH=/sentinel/stream
VITE_LIVE_STREAMS=true
VITE_AUTO_LOGIN=true
VITE_DEFAULT_LIVE_CAMERA=cam04
ENV

echo "✅ Frontend .env auto-configured"

# --- Ensure backend .env has auto credentials ---
cat > "$BACKEND/.env" <<'ENV'
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
ENV

echo "✅ Backend .env auto-configured"

# --- Install deps if needed ---
if [ ! -d "$FRONTEND/node_modules" ]; then
  echo "📦 Installing frontend deps..."
  (cd "$FRONTEND" && npm install)
fi

if [ ! -d "$BACKEND/.venv" ] && ! python3 -c "import fastapi" 2>/dev/null; then
  echo "📦 Installing backend deps..."
  (cd "$BACKEND" && pip install -r requirements.txt || pip3 install -r requirements.txt)
fi

# --- Seed DB if empty ---
if [ ! -f "$ROOT/TRINETRAAI/trinetra.db" ] && [ ! -f "$BACKEND/trinetra.db" ]; then
  echo "🌱 Seeding demo DB..."
  (cd "$BACKEND" && python -m scripts.seed_demo || python3 -m scripts.seed_demo || true)
fi

echo ""
echo "🎬 Starting backend (port 8000) and frontend (port 5173)..."
echo "   Live camera: auto-connected via Sentinel (no manual login)"
echo "   Open: http://localhost:5173"
echo ""

# Run backend in background
(cd "$BACKEND" && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload) &
BACKEND_PID=$!

# Wait a bit for backend
sleep 3

# Run frontend
(cd "$FRONTEND" && npm run dev) &
FRONTEND_PID=$!

# Trap Ctrl+C
trap "echo '🛑 Stopping...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM

wait
