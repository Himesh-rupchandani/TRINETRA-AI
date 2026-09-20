# Keep Vercel for the UI; upgrade the existing Render backend

The screenshot's warning means the backend answering that request cannot import
its vision stack, or explicitly started with `TRINETRA_API_ONLY=1`. A running data
API is not the same as a running ML backend. Do not install Torch into a Vercel
Function to try to turn it into a continuous video worker.

## Target setup

```text
Vercel: React/Vite frontend
  ├─ JSON, JPEG samples, uploads, SSE → Render /api/...
  ├─ MJPEG + evidence               → Render /api/...
  └─ WHEP signalling / HLS          → Render /sentinel/... (credentials stay there)
                                      └─ authorized camera/media gateway
Render: one full ML backend + durable data storage
```

With an absolute `VITE_API_BASE_URL`, the app now resolves backend-issued stream
paths against that backend too. Otherwise a ticket such as `/api/cameras/X/live`
would still hit Vercel's API-only process even when JSON requests went to Render.
HLS fallback preserves Render's `/sentinel` prefix, and CORS exposes the WHEP
session `Location` header so browser teardown can release the gateway session.
Long-lived video/SSE and upload requests go directly to Render; they are not
silently routed through a Vercel Function.

**No Render/Vercel dashboard change or paid upgrade is performed by these files.**
Apply the matching settings below to the existing service. Do not create a second
service or change its database merely to follow this guide.

## 1. Deploy the updated code first

The Render service's selected Git branch/commit must contain the helper scripts
and frontend URL fixes. Changing the start command on an older deployment will
produce `scripts/render_start.sh: No such file or directory`.

Back up your existing database and evidence before changing storage paths or
redeploying an instance whose files are ephemeral. Keep an existing production
`DATABASE_URL`; the example SQLite path below is **not** a migration instruction.

## 2A. Existing Render **Python** Web Service

Render → service → Settings → Build & Deploy:

| Setting | Value |
| --- | --- |
| Root Directory | **Blank / repository root**, not `TRINETRAAI/backend` |
| Build Command | `bash scripts/render_build.sh` |
| Start Command | `bash scripts/render_start.sh` |
| Health Check Path | `/api/health` |
| Runtime | A supported Python 3.11 patch is recommended for this stack |

The build installs CPU Torch/torchvision plus `requirements-ml.txt`, repairs the
GUI/headless OpenCV overlap, and checks all ML imports plus torchvision CPU ops.
Startup checks local vehicle/plate weights and uses Render's `$PORT` with
**one** Uvicorn process. Keep the Render service at **one instance/replica** too: the current scheduler, photo cache and realtime fan-out are in-memory, not distributed. Build and start use the same `python` interpreter.

Keep Root Directory blank: the helper scripts and bundled models are outside
the backend subdirectory. Do not rely on `../../scripts` from a scoped Render
root. See [1](https://render-web.app.render.com/docs/monorepo-support).

## 2B. Existing Render **Docker** Web Service

Use the alternative image definition; native Python build commands do not apply
to a Docker runtime:

| Setting | Value |
| --- | --- |
| Root Directory | Blank / repository root |
| Dockerfile Path | `deploy/render.Dockerfile` |
| Docker Build Context | `.` |
| Docker Command | Leave blank to use the image CMD |
| Health Check Path | `/api/health` |

This image includes the existing bundled vehicle and plate weights, CPU ML
packages and headless OpenCV. `.dockerignore` excludes local credentials,
databases, uploaded videos and runtime evidence. The original local Dockerfile
and compose setup are not replaced.

The Docker definition requires an actual Render/Docker build to validate on that
host; editing it in Git alone does not deploy it.

## 3. Render environment

```dotenv
TRINETRA_API_ONLY=0
APP_ENV=production
DEBUG=false
DEMO_MODE=false
DEMO_ALERTS_ENABLED=false
AUTO_SEED_DEMO=false
AUTO_START_CAMERAS=false
LIVE_ANPR_ENABLED=true
LIVE_ANPR_MAX_VEHICLES=3
LIVE_ANPR_WORKERS=1
CV_CPU_THREADS=2
CORS_ORIGINS=["https://YOUR-FRONTEND.vercel.app"]
```

Replace the frontend placeholder with the exact HTTPS origin, no path/trailing
slash. Add only your trusted custom domain/preview origins as needed, not every
`*.vercel.app` site. **CORS is not authentication**; keep the API and camera
controls behind your deployment's authenticated/trusted operator boundary.

Keep authorized camera credentials such as `SENTINEL_EMAIL` and
`SENTINEL_PASSWORD` **only in Render's server environment**. Never put them in
`VITE_*`, Git, a screenshot, or chat. The backend must be able to reach the
camera gateway; an authorized IP allowlist/network rule may also be needed.

### Data and evidence retention

Render files are ephemeral unless covered by an attached persistent disk.
Free services cannot attach disks and can spin down; continuous CCTV needs an
appropriately sized, always-on service. See [2](https://render.com/docs/free).

For the current local-file evidence implementation, attach persistent storage
and place evidence/uploads there. Example **only after a disk is actually
mounted at `/var/data`**:

```dotenv
EVIDENCE_ROOT=/var/data/trinetra/evidence
UPLOAD_DIR=/var/data/trinetra/uploads
ANALYSIS_DIR=/var/data/trinetra/uploads/analysis
# Keep your existing Postgres URL if you already have one.
# Only for a new single-process SQLite setup, or after a deliberate migration:
# DATABASE_URL=sqlite:////var/data/trinetra/trinetra.db
```

Merely setting these paths does not attach a disk. Changing `EVIDENCE_ROOT`
without migrating old files makes existing evidence references return 404.
A successful health response is not proof of platform disk persistence.

Start with a few feeds and measure CPU/RAM; installing the ML stack does not
make a small API instance capable of processing an entire camera grid. No plan,
price or throughput guarantee is implied.

## 4. Vercel frontend environment, then rebuild/redeploy

```dotenv
VITE_USE_MOCKS=false
VITE_API_BASE_URL=https://YOUR-BACKEND.onrender.com/api
VITE_REALTIME_TRANSPORT=sse
VITE_LIVE_STREAMS=true
```

Use the **public HTTPS Render service URL**, not an internal hostname, localhost,
RTSP URL or a URL containing credentials. Include the `/api` suffix. These are
build-time values: redeploy the frontend after editing them.

`VITE_STREAM_BASE_PATH` can stay `/sentinel/stream`; the updated URL resolver
uses the configured backend origin for the health probe as well. Existing
same-origin development (`VITE_API_BASE_URL=/api`) still works unchanged.

The existing Vercel configs are not overwritten with an unknown/placeholder
Render URL. A frontend-only project may keep Root Directory `trinetra-ai`; a
repo-root services project can also use the external Render API, although its
old API-only function is then unused by these frontend paths.

**`BACKEND_ORIGIN` is a Vite development-server setting, not a production Vercel
routing switch.** Setting only that variable on Vercel does not connect the
production bundle to Render.

## 5. Verify the actual Render service

Open `https://YOUR-BACKEND.onrender.com/api/health`:

- `components.cv_pipeline` should be `HEALTHY`.
- `vision.available`, `vision.cv2`, `vision.numpy` should be `true`.
- `vision.forced_api_only` should be `false`.
- `vision.deployment` should identify Render when its environment markers exist.

The API can return HTTP 200 while CV is disabled; read these fields, not just the
HTTP status. `vision.import_error_types` helps distinguish missing modules from
native import failures without publishing filesystem paths or secrets.
These fields check decoder imports, not camera reachability or OCR accuracy.

Then inspect your Vercel site's browser Network panel: JSON, `/detect-frame`,
photo/evidence, streaming and upload requests should use the Render host.
Open one authorized camera and verify an actual frame/read/evidence response.
If imports are ready but playback still fails, inspect the gateway credentials,
network access and H.265/browser compatibility separately.

## What to share for diagnosis

Only the Render **public service URL** and a redacted Settings screenshot showing
runtime, Root Directory, Build Command, Start Command and instance type. Do not
share API keys, database passwords, camera passwords or environment-variable
secret values. Live dashboard edits require access to that Render account; no
such access is established by a GitHub connection alone.
