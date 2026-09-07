# TRINETRA AI — Backend + Frontend Only (Windows / VS Code)

This guide runs **only backend + frontend** — no cv-engine, no heavy ML models, no torch.

## Prerequisites

- **Node.js 20+** → `node -v`
- **Python 3.10+** → `python --version` or `py -3 --version`
- VS Code with PowerShell terminal

## 1️⃣ Backend (Terminal 1)

Open VS Code → `Ctrl + Shift + `` ` → New PowerShell terminal.

```powershell
# From repo root — path has spaces/parens so use quotes:
cd "C:\Users\Lenovo\Downloads\hack-main (4)\hack-main\TRINETRAAI\backend"

# (once) create venv
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# If activation blocked:
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

# Install
pip install -r requirements.txt

# Seed 30 cameras (fixes stale DB with 4 OFFLINE cameras)
# If you have old trinetra.db with 4 cameras, this will now auto-clear and reseed 30
python -m scripts.seed_demo

# Optional: if still shows 4 cameras, delete DB and reseed:
# Remove-Item .\trinetra.db -Force
# python -m scripts.seed_demo

# Run backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Verify: open http://localhost:8000/api/health → should return JSON `{"status":"healthy"...}`

If it shows `"database_connected": true` and `total_cameras: 30` → backend OK.

## 2️⃣ Frontend (Terminal 2)

In VS Code → click `+` to open second PowerShell terminal:

```powershell
cd "C:\Users\Lenovo\Downloads\hack-main (4)\hack-main\trinetra-ai"

npm install

# .env is already set for backend+frontend only:
# VITE_USE_MOCKS=false
# BACKEND_ORIGIN=http://localhost:8000
# VITE_API_BASE_URL=/api

# If you edited .env, restart dev server after:
npm run dev
```

Open http://localhost:5173

You should see:
- Top-right badge **ONLINE** (not OFFLINE)
- **30 Cameras** in System (not 0)
- No "REQUEST FAILED 404"

## Fixing OFFLINE / 404

You had this because Vite only proxied `/api` when `BACKEND_ORIGIN` was set. Fixed now:

- `trinetra-ai/vite.config.ts` now defaults `/api` → `http://localhost:8000` even without env var
- `trinetra-ai/.env` now has `BACKEND_ORIGIN=http://localhost:8000` + `VITE_USE_MOCKS=false`

If you still see OFFLINE:
1. Is backend running? Check http://localhost:8000/api/health
2. Did you restart `npm run dev` after editing .env? (Vite reads .env only at startup — Ctrl+C then `npm run dev`)
3. Check .env has `VITE_USE_MOCKS=false` (not true) and `BACKEND_ORIGIN=http://localhost:8000` (no VITE_ prefix)

## Pure Mock Mode (no backend at all)

If you just want to see UI without Python:

```powershell
cd "C:\Users\Lenovo\Downloads\hack-main (4)\hack-main\trinetra-ai"
# Edit .env:
# VITE_USE_MOCKS=true
npm run dev
```

## Optional: Live Sentinel Feeds

For real WebRTC camera feeds, create `trinetra-ai/.env.local` (gitignored, never committed):

```
SENTINEL_EMAIL=your_registered_email
SENTINEL_PASSWORD=your_access_password
```

And `TRINETRAAI/backend/.env` from `.env.example`:

```
SENTINEL_EMAIL=your_email
SENTINEL_PASSWORD=your_password
```

Never put passwords in committed `.env` files — use `.env.local` for frontend and `.env` (gitignored) for backend.

## Scripts

- `.\start-backend.ps1` — one-click backend start (Windows)
- `.\start-frontend.ps1` — one-click frontend start (Windows)

Both scripts handle venv creation and auto-reseed if needed.
