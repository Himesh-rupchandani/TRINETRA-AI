# Deploying TRINETRA AI on Vercel (frontend + backend, one domain)

The whole product deploys as **one Vercel project**: the Vite SPA is served from
the CDN and the FastAPI backend runs as a Vercel Function under the same origin
at `/api`. The browser therefore needs no CORS exception, no mixed-content
exemption and no second URL to give judges.

This is done with [Vercel Services](https://vercel.com/docs/services) — the
beta feature built for exactly this shape (JS frontend + Python backend in one
repo). All of it is configured in the root [`vercel.json`](vercel.json):

```
"services": { "frontend": { root: trinetra-ai/ },  "backend": { root: TRINETRAAI/backend/, entrypoint: app.main:app } }
"rewrites": [ /api/** → backend,  /** → frontend ]
```

A service receives the **original** request path, so `/api/cameras` arrives at
FastAPI as `/api/cameras` — which is the prefix `app/main.py` already mounts its
routers under. Nothing in the app needed a path rewrite.

## 1. Project settings (once)

| Setting | Value | Why |
|---|---|---|
| Root Directory | **repo root** (`.`) | `vercel.json` with `services` lives here. If it is set to `trinetra-ai`, Vercel never sees the backend service. |
| Framework Preset | Vite | auto-detected, just don't pin something else |

## 2. Environment variables

Set all of these for **Production and Preview** (Settings → Environment
Variables). `VITE_*` are inlined into the JS bundle **at build time**, so after
changing any of them you must trigger a new build — editing the value alone
does not touch the live deployment.

Backend (`TRINETRAAI/backend/app/core/config.py` reads these):

| Variable | Value | Effect |
|---|---|---|
| `APP_ENV` | `production` | turns off dev conveniences (see `INTERNAL_API_KEY`) |
| `DEMO_MODE` | `false` | unreachable cameras stay honestly `OFFLINE` instead of a synthetic frame |
| `AUTO_SEED_DEMO` | *(optional, override only)* | leave unset: on a serverless/ephemeral host (Vercel, Cloud Run, Lambda) the demo grid seeds itself on a blank DB with no env var. Set `false` once a persistent DB (Postgres) is attached so boot never seeds over operator data. |
| `INTERNAL_API_KEY` | a random secret | authorizes `POST /api/internal/*`; unset = those endpoints are disabled, not open |
| `DATABASE_URL` | *(optional)* | only needed if you attach a real Postgres (below) |

Frontend (build-time, `trinetra-ai/src/lib/config.ts`):

| Variable | Value | Effect |
|---|---|---|
| `VITE_USE_MOCKS` | `false` | exactly `false`. Anything else — `0`, `False`, empty — means mock mode |
| `VITE_API_BASE_URL` | `/api` | same-origin; the rewrite sends it to the backend service |
| `VITE_REALTIME_TRANSPORT` | `sse` | SSE streams work on the Python runtime; `ws` does not (no WebSocket upgrade on Vercel Functions) |
| `VITE_LIVE_STREAMS` | `false` | no WHEP proxy in production; this makes the player show "source not configured" instead of spinning |
| `VITE_MAPBOX_TOKEN` | *(optional)* | public `pk.` token to switch the GIS basemap to Mapbox |

## 3. Deploy

```bash
git push origin main            # production  → https://<project>.vercel.app
# or push any branch for a preview URL such as
# https://<project>-<hash>-<user>.vercel.app
```

Every deployment gets its own URL, and because `VITE_API_BASE_URL=/api` the
backend is automatically reachable on whichever URL that deployment has — that
is the point of routing `/api` on the same origin.

## 4. Verify

```bash
U=https://<your-deployment-url>
curl -s $U/api/health | jq '.status, .total_cameras, .components'
curl -s "$U/api/cameras" | jq '.data | length'                      # 31 (30 grid + CAMLIVE)
curl -s "$U/api/vehicles/GJ01AB1234/route" | jq '.route | length'   # the 4-camera journey
curl -s "$U/api/stats/bandwidth" | jq 'keys'
```

Then open `$U` → the header must read **LIVE police backend** (System Health
page), not *Demo mode (made-up sample data)*.

## 5. What this deployment does and does not do

Honest list — the backend is a Vercel **Function**, not a server you own:

| Works | Not available on Vercel |
|---|---|
| Full REST API: registry, events, alerts, watchlist, officers, vehicle investigation, GIS routes, speed analysis, bandwidth, predictive insights, BSA §63/§65B report + certificate | Live video: MJPEG mirror, `/live/detect`, camera `start/stop`. No OpenCV in the function → those routes answer `503` with a message saying why, by design |
| Realtime via `GET /api/stream` (SSE) | WebSocket `/api/ws/events` — Vercel Functions do not upgrade connections, so use `sse` |
| 30-camera grid + demo journey on a cold start | — |
| Writes (ack alert, add watchlist…) — **per instance, ephemeral** | Video upload/analysis: request bodies are capped (~4.5 MB) and cv2 is absent. Uploads belong on the Docker deployment |
| | Reaching the Sentinel gateway: it is IP-restricted to the venue network; Vercel's egress is not on that list |

Two consequences worth stating out loud in a demo: the SQLite file lives in
`/tmp` of one instance, so data written in one request may not exist in the
next, and every cold start re-seeds the demo dataset. `/api/health` reports
this as `"storage": "EPHEMERAL"` rather than hiding it.

The CV pipeline itself (decode → YOLO11 → ANPR → events) is not squeezed into a
function: it wants a long-lived process. Run `cv-engine` against the container
deployment (`TRINETRAAI/backend/docker-compose.yml`) and point
`TRINETRA_CV_EVENTS_URL`/`api_base_url` at it.

## 6. Making the data durable (optional, ~5 minutes)

Attach Vercel Postgres / Neon and the app stops being read-mostly-demo:

1. Storage → Create Database (Neon or Vercel Postgres) → it injects
   `POSTGRES_URL`.
2. Add `DATABASE_URL` = `postgresql+psycopg://user:pass@host/db` (the psycopg 3
   driver already ships in `requirements.txt`).
3. Set `AUTO_SEED_DEMO=false` (explicit override — once a persistent DB is
   attached the boot path must be `SKIPPED`, never `SEEDED`; verify at
   `/api/health` → `components.demo_data` says `SKIPPED`), then seed once
   against the deployed API or run `python -m scripts.seed_demo` with that
   `DATABASE_URL`.

Schema is created by `Base.metadata.create_all` at boot — no migration step is
required for a fresh database.

## 7. Why the backend code changed for this

Three things had to be true for `app.main` to boot inside a function, and they
are worth knowing before you touch them again:

1. **`import cv2` at module scope made the API unimportable without the CV
   stack.** Installing it is not an option on Vercel: `ultralytics` pulls
   `torch`, which blows the 500 MB Python bundle limit and adds seconds to every
   cold start. So `app/core/vision.py` is now the single place that resolves
   `cv2`/`numpy`; the nine modules that used to import them directly import
   them from there. Real packages when installed, stubs that raise a clear
   `VisionUnavailable` when not, and `require_vision` turns the CV routes into a
   `503` with an explanation.
   Test the serverless path locally without uninstalling anything:
   `TRINETRA_API_ONLY=1 uvicorn app.main:app --port 8000`.
2. **Dependencies were split**: `requirements.txt` is the API set (what Vercel
   installs), `requirements-ml.txt` adds the CV extras and is what the Docker
   image, the Windows scripts and the local quick-start now install.
3. **A read-only / serverless host is detected and worked around** in
   `app/core/config.py` + `app/core/bootstrap.py`: if the code tree is not
   writable **or** the process is on Vercel / Cloud Run / Lambda
   (`VERCEL`/`VERCEL_ENV`/`VERCEL_REGION`, `AWS_LAMBDA_FUNCTION_NAME`,
   `FUNCTION_TARGET`, `K_SERVICE`), all writable paths move to a temp root
   (override with `RUNTIME_FALLBACK_DIR` or `TRINETRA_DATA_DIR`) and the
   storage is reported as `EPHEMERAL` even though Vercel's working dir is
   writable.  The demo grid then seeds on a blank install with **no env var**
   (`AUTO_SEED_DEMO` is an explicit override only) and `/api/health`
   surfaces it as `components.demo_data: "SEEDED 30/22/5"` (or
   `SKIPPED`/`FAILED`) so the state is debuggable from the browser.  Boot
   seeding is atomic — a failure rolls back to the savepoint and the 4
   `init_db` rows remain, so the registry is never left with 0 rows.
