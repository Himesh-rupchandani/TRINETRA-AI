# TRINETRA AI — Vercel Production Deployment

Same codebase, environment-specific backend:

```
LOCAL            PRODUCTION
React/Vite dev   Vercel (static + functions)
  │                │
  ▼                ▼
Vite proxy ──►    VITE_API_BASE_URL=https://your-backend.example.com/api
  │                │        (browser calls the backend cross-origin)
  ▼                ▼
FastAPI :8000    deployed FastAPI (Fly.io / Railway / Render / ECS / …)
                       │
                       ▼
              PostgreSQL/PostGIS + persistent volume (uploads + evidence)
```

There is **no `localhost` in production**: the bundle contains no hardcoded
origins. Every browser-side URL is either

- built by the central axios client (`config.apiBaseUrl`), or
- built through `apiUrl()` (evidence images, MJPEG tickets, raw `fetch`
  stats endpoints) — same-origin in dev, deployed-backend origin in prod, or
- a same-origin `/sentinel/*` media path served by the Vercel function in
  `api/sentinel/[...path].ts` (production twin of the Vite dev proxy; WHEP
  credentials are injected server-side and never ship in the bundle).

## 1. Deploy the frontend to Vercel

1. Import the repo (team project) and point the root at **`trinetra-ai/`**.
2. Framework preset: **Vite** (`vercel.json` pins it). Build:
   `npm run build` (runs `tsc -b && vite build`, output `dist/`).
3. `vercel.json` already provides:
   - SPA fallback — `/:path* → /index.html`, so direct navigation to
     `/cameras`, `/video-analysis`, `/alerts`, `/gis`, `/system`, … works.
   - `/sentinel/* → /api/sentinel/*` function rewrite (live WebRTC/HLS).
4. **Environment variables (Vercel UI → Project → Settings → Environment
   Variables), for Production, Preview and Development:**

   | Variable | Required | Value |
   |---|---|---|
   | `VITE_API_BASE_URL` | **yes** | `https://your-backend.example.com/api` |
   | `VITE_USE_MOCKS` | yes | `false` |
   | `SENTINEL_WHEP_ORIGIN` | for live cameras | `http://103.250.160.189:8889` (default) |
   | `SENTINEL_EMAIL` | for live cameras | gateway access email (server-side, no `VITE_` prefix) |
   | `SENTINEL_PASSWORD` | for live cameras | gateway access password (server-side) |
   | `SENTINEL_HLS_ORIGIN` | optional | HLS host, defaults to WHEP host on port 80 |
   | `VITE_REALTIME_TRANSPORT` | optional | `sse` (default) or `ws` |
   | `VITE_MAPBOX_TOKEN` | optional | public `pk.*` token for Mapbox basemaps |

5. **Redeploy after changing env vars** — Vite bakes `VITE_*` values into
   the bundle at build time; a redeploy is mandatory for them to take effect.

## 2. Deploy the backend (FastAPI)

The React app does **not** run CV processing — YOLO/ANPR/video jobs stay on
the backend. Any hostable Python runtime works (Fly.io, Railway, Render,
ECS, …). The backend needs:

- `CORS_ORIGINS` including the Vercel frontend origin, e.g.
  `CORS_ORIGINS=https://your-project.vercel.app,http://localhost:5173`
  (comma-separated or JSON list; local dev origins are pre-seeded in code).
- **Persistent storage**: `UPLOAD_DIR` (uploaded CCTV videos) and the
  evidence vault root live on the backend filesystem — Vercel's frontend FS
  is NOT storage. Mount a volume (or point them at object storage) or files
  vanish on every redeploy.
- `GET https://your-backend.example.com/api/health` must return
  `{"status": "healthy", …, "database_connected": true}`.

## 3. Verify (after deploy)

1. Open the Vercel URL → DevTools → Network:
   - API calls hit **your backend domain** — never `localhost`/`127.0.0.1`.
   - Direct URL entry on `/cameras`, `/alerts`, `/video-analysis` loads (SPA fallback).
2. `GET /api/health`, `/api/cameras`, `/api/events`, `/api/alerts`,
   `/api/watchlist` → 200 from the backend.
3. Vehicle search with a real plate in the DB → detections, timestamp,
   camera, lat/lng, location — from the real backend, not mock data.
4. GIS → real camera markers (lat/lng from `/api/cameras`).
5. Evidence thumbnails → `https://your-backend…/api/evidence/…` loads.
6. Upload a video (`/video-analysis`) → multipart POST goes straight to the
   backend origin (no proxy size limits), job tracks to completion.

## 4. Production limits / known blockers

- **Live WebRTC (`/sentinel`)** works via the Vercel function only when
  `SENTINEL_EMAIL`/`SENTINEL_PASSWORD` are set; the WHEP gateway must be
  reachable from Vercel's network. Without them, playback falls back per
  camera (HLS needs the same proxy; file cameras stream MJPEG from the
  backend directly).
- **`/cvfeed`** (CV engine's local MJPEG preview on `:8555`) is a
  development-only convenience and has no production equivalent — the player
  automatically falls back to the backend view.
- Long-running YOLO/ANPR jobs belong to the backend worker, never to Vercel
  functions.
