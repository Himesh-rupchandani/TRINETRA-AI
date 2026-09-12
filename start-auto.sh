#!/bin/bash
# TRINETRA AI — AUTO-START with live camera support
#
# Credentials policy (important):
#   * this script contains NO credentials — nothing secret is committed here;
#   * env files are CREATED ONLY WHEN MISSING and are NEVER overwritten, so an
#     operator's own values (gateway login, VITE_MAPBOX_TOKEN, ports…) survive
#     every run;
#   * credentials are resolved from the environment or from an env file that
#     already exists on this machine (see trinetra-ai/scripts/auto-setup-env.mjs).

set -e

echo "🚀 TRINETRA AI — Auto-starting"
echo "   Env files are created only when missing; existing values are preserved"

# Root dir
ROOT="$(cd "$(dirname "$0")" && pwd)"
FRONTEND="$ROOT/trinetra-ai"
BACKEND="$ROOT/TRINETRAAI/backend"

# --- Env files: create-if-missing, never clobber -----------------------------
# The Node setup script is the single implementation of that policy; it also
# appends missing keys and resolves Sentinel credentials from this machine.
if command -v node >/dev/null 2>&1; then
  (cd "$FRONTEND" && node scripts/auto-setup-env.mjs)
else
  echo "⚠️  node not found — falling back to a plain .env.example copy"
  [ -f "$FRONTEND/.env" ] || cp "$FRONTEND/.env.example" "$FRONTEND/.env"
  if [ ! -f "$BACKEND/.env" ]; then
    # Copy the template and blank the credential lines: they must be filled in
    # locally (or exported), never shipped with a value from this script.
    sed -E 's/^(SENTINEL_EMAIL|SENTINEL_PASSWORD)=.*/\1=/' \
      "$BACKEND/.env.example" > "$BACKEND/.env"
  fi
fi

# --- Warn (never print) when the gateway credentials are still empty ---------
if ! grep -Eq '^SENTINEL_EMAIL=.+' "$FRONTEND/.env" 2>/dev/null \
   || ! grep -Eq '^SENTINEL_PASSWORD=.+' "$FRONTEND/.env" 2>/dev/null; then
  echo "⚠️  Sentinel gateway credentials are empty in $FRONTEND/.env"
  echo "   Live camera playback needs SENTINEL_EMAIL + SENTINEL_PASSWORD."
  echo "   Everything else (ANPR pipeline, alerts, evidence, analytics) works without them."
fi

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
