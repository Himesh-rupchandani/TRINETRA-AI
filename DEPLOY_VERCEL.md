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
| `SENTINEL_EMAIL` | your Sentinel email | **required for live camera playback** — the same-origin `/sentinel` media proxy injects it as Basic auth toward the media gateway (see §5.1). Without it the live view answers 502 with a setup hint, never a fake feed. |
| `SENTINEL_PASSWORD` | your Sentinel access password | same as above. Server-side only — it never reaches the browser bundle or any API response. |
| `SENTINEL_WHEP_ORIGIN` | *(optional)* | default `http://103.250.160.189:8889` — WHEP signalling origin for the `/sentinel` proxy |
| `SENTINEL_HLS_ORIGIN` | *(optional)* | default: WHEP host on port 80 — HLS compatibility-stream origin for the `/sentinel` proxy |
| `DATABASE_URL` | *(optional)* | only needed if you attach a real Postgres (below) |

Frontend (build-time, `trinetra-ai/src/lib/config.ts`):

| Variable | Value | Effect |
|---|---|---|
| `VITE_USE_MOCKS` | `false` | exactly `false`. Anything else — `0`, `False`, empty — means mock mode (synthetic "demo" data). For the original product this **must** be `false`. |
| `VITE_API_BASE_URL` | `/api` | same-origin; the rewrite sends it to the backend service |
| `VITE_REALTIME_TRANSPORT` | `sse` | SSE streams work on the Python runtime; `ws` does not (no WebSocket upgrade on Vercel Functions) |
| `VITE_LIVE_STREAMS` | `true` | enables real live playback: the player takes backend tickets and plays the cameras over the same-origin `/sentinel` proxy (WHEP, with automatic HLS fallback). Set it `true` (or simply remove it — `true` is the default) now that the proxy runs on the deployment. Leave it `false` only when the deployment has no `SENTINEL_EMAIL`/`SENTINEL_PASSWORD`. |
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
| Full REST API: registry, events, alerts, watchlist, officers, vehicle investigation, GIS routes, speed analysis, bandwidth, predictive insights, BSA §63/§65B report + certificate | OpenCV live views: the MJPEG mirror `/api/cameras/<id>/live`, the annotated `/live/detect` and camera `start/stop` — no OpenCV in the function, those routes answer `503` with a message saying why, by design. Playback does not need them: the browser plays the gateway directly (§5.1) |
| **Live camera playback**: WHEP WebRTC + HLS compatibility stream over the same-origin `/sentinel` proxy — real gateway video in the browser, no demo frames (§5.1) | — |
| Realtime via `GET /api/stream` (SSE) | WebSocket `/api/ws/events` — Vercel Functions do not upgrade connections, so use `sse` |
| 30-camera grid + demo journey on a cold start | — |
| Writes (ack alert, add watchlist…) — **per instance, ephemeral** | Video upload/analysis: request bodies are capped (~4.5 MB) and cv2 is absent. Uploads belong on the Docker deployment |
| | |

### 5.1 Live camera playback on Vercel (the `/sentinel` proxy)

The Sentinel grid (CAM01–CAM30) plays in the browser over **two short,
serverless-friendly paths** — the heavy WebRTC media itself never transits
Vercel:

1. **WebRTC (WHEP) — primary.** The player asks the backend for a ticket
   (`GET /api/cameras/<id>/stream`) and gets a same-origin path:
   `/sentinel/stream/<id>/whep`. The **backend service** is the proxy (in
   development the Vite dev server is the same proxy): it forwards the small
   SDP-offer POST to the media gateway with `SENTINEL_EMAIL` /
   `SENTINEL_PASSWORD` injected as HTTP Basic auth, rewrites the reply's
   `Location` header back onto the same origin (so the session-teardown
   `DELETE` stays here too), and returns the SDP answer. From that point the
   video flows **browser ↔ gateway directly** (ICE) — Vercel only carried two
   kilobytes of signalling.
2. **HLS — automatic fallback.** If WebRTC cannot be negotiated, the player
   steps down to `/sentinel/live/stream/<id>/index.m3u8`. The proxy streams
   the playlist and each short segment from the gateway's HTTP port — plain
   GETs, which Vercel Functions handle fine.

Honesty rules built into this path:

- No `SENTINEL_EMAIL`/`SENTINEL_PASSWORD` → the proxy answers **502 with an
  actionable message** ("set the env vars and redeploy"). The player shows
  that state; a recorded clip is never substituted for the live source.
- The proxy only forwards published camera paths
  (`stream/<id>/…`, `live/stream/<id>/…`) and validates the camera id, so it
  cannot be turned into an open relay carrying your credentials.
- Grid cameras with a configured gateway source report **ONLINE** in
  `/api/cameras` and KPIs even though no local worker ingests them: the
  gateway publishes them continuously and the browser pull opens the feed.
  A camera with an *empty* source still reports `NOT_CONFIGURED`, and a
  private (non-grid) camera keeps its registry status — nothing is faked.

If the live view on the deployment says the gateway is **unreachable (502)**,
the media gateway's network may simply not allow this host's egress —
redeploy once the gateway side allows it, or run the full CV deployment
(Docker) behind a host that can reach it. If it says **refused (401)**, the
credentials in the project's environment variables are wrong or missing.

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

## 8. Troubleshooting: the dashboard renders `0/1` (or `0/0`)

Both numbers are *real* — they are the Camera Network KPI
(`camerasOnline`/`totalCameras` from `GET /api/stats/kpis`) — but neither says
why the grid is empty. Read the number as a fingerprint first:

| On screen | What the origin is actually serving | Fix |
|---|---|---|
| `0/1` | A live API whose registry holds exactly one row: the env-configured `CAMLIVE` slot (`OFFLINE`, no source on Vercel). That is what a **pre-atomic-seed build** leaves behind when its seed rolled back — it deleted the 4 `init_db` rows and committed before inserting. | The **domain is attached to an old deployment**. Redeploy that project on the current commit (or promote a newer deployment to Production). |
| `0/0` or `—/—` | **No backend at all on this origin**: `/api/*` is answered by the SPA's own catch-all rewrite, so `GET /api/health` returns `200 text/html`. | The project serving this URL has **Root Directory = `trinetra-ai`**, so the root `vercel.json` `services` block never applies. See below. |
| `30/31` | Correct: 30 registry cameras + `CAMLIVE`, all reported by the API. | — |

### 8.1 Which Vercel project can even serve `/api`?

`services` (frontend + backend on one domain) is only read from the
**repository-root** `vercel.json`, and Vercel only reads that file when the
project's **Root Directory** is the repo root. A project pinned to
`trinetra-ai/` builds an SPA whose own rewrite answers `/api/*`.

Check the mapping before blaming the code — Vercel →
project → **Settings → Build & Deployment → Root Directory**, and
**Settings → Domains** to see which project owns the production URL:

| Project | Root Directory | Can serve `/api/*`? |
|---|---|---|
| `trinetra-ai-kmhx` | repo root | **yes** — the services project |
| `trinetra-ai`, `trinetra-ai-u8mp` | `trinetra-ai` | no — frontend only (SPA fallback for `/api/*`) |
| `trinetraai-sigma` | `trinetra-ai` | no — frontend only (SPA 404 page for `/api/health`) |

Any project name fits this diagnosis: open `https://<project>/api/health`.
JSON = a backend is attached; the SPA's *"Route not found"* screen = frontend
only. `trinetraai-sigma.vercel.app` is the classic case: a live URL that
served only the SPA — no API, no tickets, no `/sentinel` proxy — so the
live cameras had nothing to play against.

### 8.2 Two ways to fix it

* **Move the domain** (preferred, no rebuild): Vercel → the services project
  (`trinetra-ai-kmhx`) → **Settings → Domains → Add** the production domain, and
  remove it from whichever project currently holds it. Both projects must be in
  the same team for the domain to transfer.
* **Or keep the domain where it is** and set that project's **Root Directory**
  to `.` (repo root), keep Framework Preset = Vite, then **Deployments →
  Redeploy** (without cache). The root `vercel.json` then routes `/api` and
  `/sentinel` to the FastAPI service on the same origin.

  If the URL is the project's own `<project>.vercel.app` (e.g.
  `trinetraai-sigma.vercel.app`) there is no custom domain to move — this
  Root-Directory change **is** the fix for that URL. After the change, also
  make sure the project's environment variables include `VITE_USE_MOCKS=false`
  and `VITE_LIVE_STREAMS=true` (build-time: a new build must run) plus
  `SENTINEL_EMAIL` / `SENTINEL_PASSWORD` for live playback — see §2 and §5.1.

Pushing to `main` *does* trigger a production build on every connected project
(confirmed for `trinetra-ai`, `trinetra-ai-u8mp` and `trinetra-ai-kmhx` on
`5a8bf2e`, 07:16–07:17 UTC 2026-09-15). An empty "trigger commit" is therefore
never needed: if the domain did not move, the **domain**, not the build, is the
problem — fix it above.

### 8.3 Prove it in one command

```bash
node scripts/verify/verify_deploy.mjs                       # prod + kmhx aliases
node scripts/verify/verify_deploy.mjs https://your-url       # any origin
```

It classifies each origin (`OK`, `NO_BACKEND`, `STALE_DEPLOYMENT`,
`EMPTY_REGISTRY`, `UNREACHABLE`, `PROTECTED`) and prints the exact
`online/total` pair the dashboard will render. Exit code is 1 unless every
origin is `OK`. `docs/ci/deploy-probe.yml` runs the same check from GitHub
Actions — copy it to `.github/workflows/` (a token with the `workflows`
permission is required to push that path).

Where `curl` is blocked (corporate proxy, preview tunnel), the same answer comes
from the browser console on the page in question:

```js
fetch('/api/health', { headers: { accept: 'application/json' } })
  .then(async (r) => console.log(r.status, r.headers.get('content-type'), (await r.text()).slice(0, 200)));
```

`application/json` + `"total_cameras": 31` is a healthy origin; `text/html`
means there is no backend on that domain; valid JSON *without*
`components.demo_data` means the deployment is older than the atomic-seed fix.

### 8.4 The UI now says this out loud

`lib/backendStatus.ts` + `components/layout/BackendCheck.tsx` render a strip
under the header whenever the origin cannot serve the API, when the API is
older than the seed fix, when seeding failed, or when the registry lost rows
after seeding — and `services/api.ts` refuses to read an HTML shell as JSON, so
an unreachable API is an error instead of an empty grid. The strip is silent on
a healthy deployment and in mock mode; set `VITE_DEPLOY_CHECK=false` to disable
it entirely.
