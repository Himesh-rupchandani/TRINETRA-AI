#!/bin/bash
# TRINETRA AI — AUTO-START (frontend only)
#
# The FastAPI backend that used to live in TRINETRAAI/backend was removed from
# this repository. This script now only prepares and starts the frontend.
# To browse the UI without a backend, set VITE_USE_MOCKS=true in
# trinetra-ai/.env (the setup script below never overwrites existing values).
#
# Credentials policy (important):
#   * this script contains NO credentials — nothing secret is committed here;
#   * env files are CREATED ONLY WHEN MISSING and are NEVER overwritten, so an
#     operator's own values (gateway login, VITE_MAPBOX_TOKEN, ports…) survive
#     every run.

set -e

echo "🚀 TRINETRA AI — Auto-starting (frontend)"
echo "   Env files are created only when missing; existing values are preserved"

# Root dir
ROOT="$(cd "$(dirname "$0")" && pwd)"
FRONTEND="$ROOT/trinetra-ai"

# --- Env files: create-if-missing, never clobber -----------------------------
if command -v node >/dev/null 2>&1; then
  (cd "$FRONTEND" && node scripts/auto-setup-env.mjs)
else
  echo "⚠️  node not found — falling back to a plain .env.example copy"
  [ -f "$FRONTEND/.env" ] || cp "$FRONTEND/.env.example" "$FRONTEND/.env"
fi

# --- Warn (never print) when the gateway credentials are still empty ---------
if ! grep -Eq '^SENTINEL_EMAIL=.+' "$FRONTEND/.env" 2>/dev/null \
   || ! grep -Eq '^SENTINEL_PASSWORD=.+' "$FRONTEND/.env" 2>/dev/null; then
  echo "⚠️  Sentinel gateway credentials are empty in $FRONTEND/.env"
  echo "   Live camera playback needs SENTINEL_EMAIL + SENTINEL_PASSWORD."
fi

# --- Install deps if needed ---
if [ ! -d "$FRONTEND/node_modules" ]; then
  echo "📦 Installing frontend deps..."
  (cd "$FRONTEND" && npm install)
fi

echo ""
echo "🎬 Starting frontend (port 5173)..."
echo "   Open: http://localhost:5173"
echo ""

cd "$FRONTEND" && npm run dev
