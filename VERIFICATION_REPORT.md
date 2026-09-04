# TRINETRA AI — Verification Report
**Intelligent Vision. Faster Response.**
Gujarat Police Innovation Hackathon 2026 · branch `arena/01a06a59-hack` · HEAD `1071d08`
Reported date: 2026-09-04 · everything below was executed in this sandbox, not inferred.

---

## 1. Headline

| Area | Verdict |
|---|---|
| Backend API (FastAPI) | **PASS** — 101 tests, all contract endpoints live |
| CV / AI engine | **PARTIAL** — pipeline + dedup + ingestion verified; detection & ANPR **BLOCKED** here |
| Frontend (React + Vite + TS) | **PASS** — typecheck clean, production build green, LIVE against real backend |
| Database | **PASS** — seeded, referentially consistent, reseedable |
| Live Sentinel cameras | **BLOCKED (environment)** — host unreachable from this sandbox |
| End-to-end evaluator scenario (`GJ01AB1234`) | **PASS** at the API/contract level; browser render **BLOCKED** (no browser installed) |

**The primary acceptance case works.** Plate `GJ01AB1234` resolves to `WATCHLIST MATCH /
STOLEN VEHICLE / HIGH PRIORITY` with four chronological sightings `CAM04 → CAM08 → CAM12 →
CAM17`, and every GIS route hop now carries the `event_id` of the sighting behind it, so the
map point deep-links to its own evidence.

---

## 2. Test evidence (all run on the merged tree)

| Suite | Command | Result |
|---|---|---|
| Backend | `pytest -q -p no:warnings` (`TRINETRAAI/backend`) | **101 passed** in 4.7s |
| CV engine | `pytest -q -p no:warnings` (`cv-engine`) | **79 passed, 3 deselected** (`-m "not live"`) |
| Frontend types | `npx tsc --noEmit -p tsconfig.app.json` | **exit 0**, no errors |
| Frontend lint | `npm run lint` | 0 errors, 17 warnings (pre-existing style) |
| Production build | `npm run build` | **✓ built in 4.2–4.9s** |
| Live contract | `BACKEND=… npm run verify:live` | **PASS — 45/45 checks** |

Note on the brief's "67/67 backend tests": the measured reality before my changes was **91
passed**; after integration it is **101**. No tests were deleted.

### What the 45 live checks assert
30 cameras with 3-state status + coordinates · `CAM04` registry record · KPIs
(`total_cameras=30`, `vehicle_detections_24h=22`) equal to the dashboard grid counts ·
`GJ01AB1234` profile with `cameras_touched=4` and watchlist attached · 4 chronological
sightings · route `cam04→cam08→cam12→cam17` at *Paldi Circle, Lal Darwaja Terminus, Kankaria
Lake Circle, Odhav Ring Road* · 5 alerts with valid lifecycle + severity · 10 watchlist
entries (`GJ01AB1234` = STOLEN / CRITICAL) · 7 health services HEALTHY · realtime SSE 200
`text/event-stream` · WebSocket upgrade 101 · `ALERT_CREATED` broadcast carrying
plate/CAM08/CRITICAL/`event_id`.

---

## 3. Phase-by-phase verdicts

Only claims I could execute are marked PASS.

| Phase | Verdict | Evidence |
|---|---|---|
| 0–1 Inspection & recorded baseline | **PASS** | Full read of frontend/backend/CV/DB before edits; baseline measured (91 backend tests, not 67) |
| 2 CV event contract | **PASS** | `plate_raw`/`plate`/`plate_confidence`/`timestamp_pts` preserved end-to-end; stored event round-tripped through `POST /api/events` |
| 3 CV → backend integration | **PARTIAL** | Frame loop → sighting dedup → event build → `POST /api/events` 201 verified (60 frames → 1 event). Detection/OCR stages **BLOCKED** — see §5 |
| 4 DEMO vs LIVE separation | **PASS** | `VITE_USE_MOCKS:"false"` baked into the shipped bundle; header shows *Live police backend* vs *Demo mode*; Demo Feed badge gated on `useMocks` |
| 5 Sentinel catalogue-driven integration | **PASS** (code) / **BLOCKED** (live) | Catalogue parser + tests pass; live host returns HTTP 000 — see §5 |
| 6 Watchlist → alert engine | **PASS** | 10 watchlist entries; watchlist hit raises CRITICAL alert; verified through ingestion |
| 7 Backend API contract | **PASS** | All required endpoints present; 3 response envelopes regression-tested (`test_system_integration.py`) |
| 8 Real camera playback | **BLOCKED** | Sentinel HLS/RTSP/WHEP all HTTP 000. Local-file MJPEG path exists but needs video assets + weights absent here |
| 9 Real ANPR on live frames | **BLOCKED** | No OCR engine, no weights, no reachable live source |
| 10 Frontend service layer | **PASS** | `grep` over `src/components` + `src/pages`: **zero** `fetch(`/`axios.`/`new WebSocket(`/`new EventSource(` — all network access is in `services/` + `hooks/` |
| 11 TypeScript type safety | **PASS** | `tsc --noEmit` exit 0 |
| 12 Dashboard / KPI integrity | **PASS** | KPI "Vehicles Detected (24h)" now labels the metric it shows; `/api/stats` counts equal the grid |
| 13 Vehicle plate search (hero case) | **PASS** | `GJ01AB1234` → profile, 4 sightings, route, watchlist; verified via live API and through the service/hook layer |
| 14 GIS route visualization | **PASS** | Chronological observed detections only, no invented road geometry; each hop now carries `event_id` → verified each id resolves to the same camera via `GET /api/events/{id}` |
| 15 Evidence panel | **PARTIAL** | Backend contract + adapter mapping verified; **browser rendering not verified** (no browser in sandbox) |
| 16 Alert lifecycle | **PASS** | NEW → ACKNOWLEDGED → RESOLVED exercised against the real backend via `POST /api/alerts/{id}/ack` |
| 17 Realtime without refresh | **PASS** | SSE 200 `text/event-stream`; WS handshake 101; broadcast carries event fields; client fan-out expands one frame to EVENT + ALERT |
| 18 Event explorer (filters + pagination) | **PASS** (contract) | Filters/pagination asserted by live checks; UI rendering unverified |
| 19 Watchlist page | **PASS** | Filter options now match the backend's real category set instead of a hardcoded list |
| 20 Camera registry | **PASS** | 30 cameras from `GET /api/cameras`; single status authority `_resolve_camera_status()` used by both `cameras.py` and `stats.py` — no per-component hardcoding |
| 21 System health from real backend | **PASS** | 7 services from `/api/health`; `grep` confirms **no** `Math.random`/`cpuUsage`/`ramUsage` in `SystemHealth.tsx` |
| 22 Routing & click paths | **PARTIAL** | Routes + deep-links implemented and built; actual click-through unverified (no browser) |
| 23 Demo mode preserved | **PASS** | Mocks intact; `VITE_USE_MOCKS=true` build works with no backend |
| 24 Error / empty / loading states | **PARTIAL** | States present in code; visual verification impossible here |
| 25 Security | **PASS** | Gateway IP `103.250.160.189`, `SENTINEL_WHEP_ORIGIN`, `api_key` **absent** from the built bundle; `password` hits are hls.js internals + a React input-type list + UI copy; CORS controlled |
| 26 DB referential consistency | **PASS** | Reseed clean (30 cameras / 10 watchlist / 22 events / 5 alerts); route `event_id`s all resolve |
| 27 Test coverage | **PASS** | 101 + 79 + 45 as above |
| 28 Documentation | **PASS** | README + inline rationale comments on non-obvious fixes |
| 29 Deployment readiness | **PARTIAL** | Production build served and verified; no container/CI artefacts |

---

## 4. Fixes made this session

| Commit | Change | Why it mattered |
|---|---|---|
| `f936fed` | One `_resolve_camera_status()` authority | Two independent camera-status computations had diverged, so the grid and the detail view could disagree |
| `6c876a5` | Removed duplicate schema/route definitions | A later `class` with the same name silently shadows the earlier one |
| `853c047` | Merged the parallel session; deduped 3 Pydantic models + 2 duplicate routes; dropped a dead service | Prevents the shadowing class of bug |
| `555f43b` | Header LIVE/DEMO + feed-state indicators; KPI label matched to its metric; watchlist filters matched to real backend categories; camera registry status aligned to `/api/cameras` | Phase 4 / 13 / 19 / 20 conformance |
| `788ed43` | Route points carry `event_id`; GIS popup shows the plate and links to vehicle + evidence | Removes client-side camera+timestamp guesswork; satisfies the map-point → event click path |
| `171ce95` | `/api` proxy in `vite preview` | Lets the verified production build run LIVE same-origin |
| `d81d1b3`, `1071d08` | Merges of remote work (local YOLO feed demo, AVI loop-seek fix, docs) | Re-verified after each merge: 101 / 79 / tsc 0 / build ✓ / 45-45 |

**Blank-preview root cause (found this session):** the dev server returned 200 for `/` and
`/src/main.tsx`, but the prebundled dependencies they import returned
**504 Outdated Optimize Dep** — a stale optimizer cache after repeated `vite.config.ts`
auto-restarts. Curling only the entry files hides this. The production build has no
optimizer, so the preview now serves that instead.

---

## 5. BLOCKED items — environment, with measurements

| Item | Measurement |
|---|---|
| Sentinel camera catalogue | `curl https://cctv.corp8.cloud/cameras.json` → **HTTP 000** in 0.086s |
| Sentinel HLS / RTSP / WHEP | **HTTP 000** (backend logs `[tls @ …] IO error: End of file` per camera) |
| YOLO weights | No `.pt` file anywhere on disk; GitHub releases → 302 then **fails**; `huggingface.co` → **000**; `download.pytorch.org` → **000** |
| ML runtime | `ultralytics`: **MISSING** · `torch`: **MISSING** · `pytesseract`: **MISSING** · `tesseract`: **not on PATH** (`cv2` and `numpy` are present) |
| Package mirror | `files.pythonhosted.org` → **200** (PyPI reachable; only the model hosts are blocked) |
| Browser | No chromium/chrome/firefox/playwright/puppeteer installed; `apt` mirrors connection-refused over HTTP and TLS-terminated over HTTPS |

**Consequence, stated plainly:** real vehicle detection and real ANPR have **never run in this
sandbox**. The 79 CV tests pass with the detector unavailable (they stub it), so they verify
the pipeline's frame loop, tracker, dedup, event contract and ingestion — not detection
quality. The parallel session's `run_feed_demo.py` (real YOLO11 + ByteTrack on local files)
cannot execute here either: it needs `cv-engine/feeds/*.mp4|avi` and YOLO weights, neither of
which exists and neither of which can be downloaded.

No plate, confidence, route or timestamp was fabricated to work around this. Demo-only data is
explicitly labelled and gated behind `VITE_USE_MOCKS`.

---

## 6. Remaining work before the hackathon demo

1. **Run on a network that can reach Sentinel** (or a venue network). This unblocks Phases 8
   and 9 — live video, live ANPR, live detection.
2. **Install the ML runtime there:** `pip install ultralytics torch` (PyPI works) and place
   `yolo11n.pt` in `cv-engine/weights/`, plus `tesseract` for ANPR.
3. **Drop demo videos into `cv-engine/feeds/`** to exercise `run_feed_demo.py` offline as a
   fallback if venue Wi-Fi fails.
4. **Reseed before the demo** — each `verify:live` run mints a probe plate `GJ99ZZ<ts>` and
   ingests a sighting, so counts drift (22 → 23 → 24).
5. **Click through the UI once on a real browser.** That is the one thing this sandbox
   structurally cannot do; every claim about rendering is marked PARTIAL for that reason.

---

## 7. Re-verify commands

```bash
# backend
cd TRINETRAAI/backend && /home/user/hack/.venv/bin/python -m pytest -q -p no:warnings
# CV engine
cd ../../cv-engine && /home/user/hack/.venv/bin/python -m pytest -q -p no:warnings
# frontend
cd ../trinetra-ai && npx tsc --noEmit -p tsconfig.app.json && npm run build
# live contract (needs the backend running)
BACKEND=http://127.0.0.1:8000 npm run verify:live

# reseed (model changes require deleting trinetra.db; there is no alembic)
rm -f trinetra.db && DATABASE_URL="sqlite:///./trinetra.db" \
  /home/user/hack/.venv/bin/python -m scripts.seed_demo
# backend
DATABASE_URL="sqlite:///./trinetra.db" AUTO_START_CAMERAS=false \
  /home/user/hack/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
# frontend, LIVE, production build (VITE_USE_MOCKS=false must be set at BUILD time)
VITE_USE_MOCKS=false npm run build
BACKEND_ORIGIN=http://127.0.0.1:8000 npx vite preview --host 0.0.0.0 --port 5173
```

### Currently running here
- Backend API `:8000` — process `trinetra-backend-api-3d0da6f2`
- Control Room production build `:5173` — process `trinetra-control-room-production-01a32b56`
- Verified live: index 200 · entry JS/CSS 200 · proxy `/api/health` 200 ·
  trace `CAM04 → CAM08 → CAM12 → CAM17` with `event_ids [1,2,3,4]`
