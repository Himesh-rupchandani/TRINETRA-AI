# TRINETRA AI — Bug-Fix Report (all 27 findings)

**Scope:** every confirmed finding from the repo-wide bug hunt, fixed at root cause.
**Branch:** `arena/01a094a1-hack` · **Base:** `db39ae9`
**Diff:** 87 files changed, 2060 insertions(+), 781 deletions(−), plus 7 new files
(`app/core/paths.py`, 5 new backend test modules, `trinetra-ai/tests/`).

Everything below was executed in this workspace, not inferred.

---

## 1. Verification summary

| Gate | Command | Result |
|---|---|---|
| Backend suite | `cd TRINETRAAI/backend && pytest` | **200 passed** |
| CV engine suite | `cd cv-engine && pytest` | **84 passed, 3 deselected** (live-feed tests opt-in) |
| Frontend suite | `cd trinetra-ai && npm test` | **48/48 passed** (plain node, no runner installed) |
| Frontend typecheck | `npx tsc -b` | **clean** |
| Production build | `npx vite build` | **green** (6.6 s) |
| Bundle credential scan | 68 built files vs. local `.env` secrets | **0 leaks** (incl. the base64 Basic-auth form) |
| Dead code lint | `ruff check --select F401,F811,F841` on backend + cv-engine | **0 remaining** (66 unused imports + 8 dead locals removed) |
| Camera auto-access | `node scripts/verify/verify_camera_access.mjs` | **20/20 checks passed** |

New regression coverage added for this task: **64 backend tests** (28 bug-fix + 14 speed/insights +
11 evidence vault + 8 plate consistency + 3 frontend-suite driver), **48 frontend tests**, and
**1 cv-engine retry-contract test**.

---

## 2. Constraint compliance (the rules this work had to respect)

| Constraint | Status | Proof |
|---|---|---|
| Never disable/alter camera auto-access, permission prompts, auto camera init or reconnect | **Respected** | `CameraPlayer.tsx` still holds `if (autoRequest && camera.status !== 'OFFLINE') void requestStream();` and `}, [camera.id]);`; `AUTO_START_CAMERAS` default unchanged (`False`); reconnect/backoff untouched. Only the state *mapping* (13), the stale dep array (14) and the unknown-camera 404 (17E) changed. |
| Preserve MJPEG / live / SSE / WS / detection / tracking / streaming | **Respected** | All transports still wired (`useHlsStream`, `useWhepStream`, `useLiveEvents`, `whepClient`, `/sentinel`, `/cvfeed`, `/api` proxies) — asserted by `source-contracts.test.mjs`. Live SSE/WS/MJPEG endpoints re-verified against a running backend. |
| Preserve APIs unless a listed bug requires a contract correction | **Respected** | Only listed contract fixes applied (4, 5, 17A–G, 19). Legacy aliases (`PATCH …/acknowledge`, `/api/v1/*`) still present. |
| No unrelated UI/feature changes or refactors | **Respected** | Diff is confined to the 27 findings, their tests and the docs they invalidate. |
| Never print/expose credentials (terminal, logs, comments, files) | **Respected** | Verification scripts compare **SHA-256 digests and lengths only**; the stub gateway never echoes an `Authorization` value; the bundle scan prints counts, not values. |
| Never overwrite an existing `.env` (esp. `VITE_MAPBOX_TOKEN`) | **Respected** | 6 behavioural tests run the real `auto-setup-env.mjs` in a throwaway tree: existing bytes preserved, missing keys appended, second run a no-op, backend `.env` untouched. |
| docker-compose must not mount a volume over `/app` | **Respected** | Both compose files mount `trinetra-data:/app/data` with an explanatory comment. |
| Real hash chain for evidence — no faked verification | **Respected** | `hash` + `previous_hash` stored per record, recomputed from immutable fields; modified evidence, modified hash and broken chain are each detected (11 tests). Chain status is evaluated **before** record status so `CHAIN_BROKEN` is never masked as `TAMPERED`. |
| One canonical Indian plate rule across cv-engine / backend / frontend | **Respected** | `^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{3,4}$` identical in all three layers; 8 backend + 2 frontend tests fail on drift. |
| Remove stray root `package-lock.json` only if junk | **Confirmed junk, removed** | `name: zip-2`, empty `packages`, no root `package.json`. |

---

## 3. Findings and fixes

### CRITICAL

**1 — `app/api/bandwidth.py` shadow recursion** · FIXED
The module imported a name it also defined, so the endpoint recursed into itself (and the local
module shadowed the service import). Root cause: name collision between the router module and
`services/bandwidth_engine`. Fix: import the service explicitly and drop the shadowing local.
*Evidence:* `tests/test_bugfix_regressions.py` (recursion + module-shadowing tests); `GET /api/stats/bandwidth` returns engine output.

**2 — `timedelta` NameError in the upload pipeline** · FIXED
`app/api/uploads.py` / `uploaded_video_service.py` built timed events with `timedelta` that was never
imported, so every uploaded video 500'd at event-creation time. Fix: import `timedelta` at the point of
use and drive event timestamps from it.
*Evidence:* regression test uploads a 12-frame video through a stubbed detector/OCR and asserts real
`VehicleEvent` rows with the expected plate and ordered timestamps.

**3 — frontend alert ids became `NaN`** · FIXED (both ends)
Realtime frames carry display refs (`"AL-7"`); `Number('AL-7')` → `NaN`, which the UI rendered and then
sent back as `POST /api/alerts/NaN/resolve` (422/404). Fix: new `toId()` normalizer in
`src/services/adapters.ts` (numeric ids round-trip, prefixed refs contribute their numeric part,
anything else passes through verbatim — never `"NaN"`), DTO types widened to `number | string`, and
`alertService.ts` builds paths with `encodeURIComponent(id)`.
*Evidence:* 6 frontend tests (`adapters.test.mjs`) + backend resolve/ack tests.

### CONTRACT

**4 — duplicate `GET /events/{event_id}`** · FIXED
Two handlers were registered for the same path; the second silently shadowed the first, so the
documented response shape depended on import order. Fix: single handler.
*Evidence:* route enumeration over `app.api.events.router.routes` + the OpenAPI spec asserts exactly one
`GET /events/{event_id}` operation.

**5 — naive timestamps on the wire** · FIXED
Endpoints emitted local/naive ISO strings, so the browser and the evidence chain disagreed about time.
Fix: `app/utils/timestamps.py` (`utc_now`, `to_utc`, `iso_utc`, `format_timestamp`, `parse_timestamp`)
is now the single serializer; 7 endpoints + the schema serializer + DB round-trip all emit `…Z`.
*Evidence:* 5 timestamp tests (endpoint-level, DB round-trip, serializer) + `expires_at` verified live.

**6 — `EVIDENCE_ROOT` divergence** · FIXED
Backend and cv-engine resolved the evidence root differently (one CWD-dependent), so crops written by
the engine were 404 in the API. Fix: new `app/core/paths.py` — one resolver, CWD-independent, identical
for the same input (function identity), rejects traversal.
*Evidence:* 3 tests (CWD-independence, same-function identity, traversal rejection); live log shows
`Evidence root ensured at /home/user/hack/cv-engine/evidence`.

**7 — docker-compose volume shadowed `/app`** · FIXED
An empty named volume mounted at `/app` hid the application code (`No module named app.main`).
Fix: `trinetra-data:/app/data` in both `TRINETRAAI/docker-compose.yml` and `TRINETRAAI/backend/docker-compose.yml`.

**8 — `prettyPlate` half-split non-canonical plates** · FIXED
Any digit run was split, so `"GJ011234"` rendered as the misleading `"GJ 01 1234"`. Fix: only a fully
canonical plate is grouped (`GJ 01 AB 1234`, legacy `GJ1A234` → `GJ 01 A 234`); everything else is shown
normalized, never invented.
*Evidence:* 4 frontend tests + the backend `pretty_plate` equivalent.

**9 — three different plate regexes** · FIXED
cv-engine, backend and frontend each carried their own pattern (the UI's allowed zero series letters and
a single number digit), so the same OCR string was canonical in one layer and invalid in another.
Fix: one canonical grammar in all three layers, documented as byte-identical at each definition site.
*Evidence:* `tests/test_plate_format_consistency.py` (8 tests, reads all three sources) + 2 frontend tests.

**10 — speed engine bugs** · FIXED
(a) optical velocity divided by `n / fps` instead of `(n − 1) / fps`, inflating every estimate by one
interval; (b) `calibration_factor` was accepted and ignored; (c) GPS segments were skipped with a
truthiness test, so a legitimate `0.0` latitude/longitude vanished (same bug in `app/api/speed.py`
when building `SpeedPoint`s); (d) `evidence_chain` sat behind `if 'hashlib' in locals() or True` with an
in-loop import — dead code that could never take the other branch.
*Evidence:* 8 tests in `tests/test_speed_and_insights_regressions.py`, incl. an end-to-end
`/api/vehicles/{plate}/speed-analysis` call over equator/prime-meridian sightings (11.1 km in 10 min →
66.7 km/h, no violation at 80, violation at 40).

**11 — fabricated "24h" insights** · FIXED
`/api/stats/insights` and `/api/stats/traffic-patterns` computed from the newest 500 rows regardless of
age and then labelled the result `time_range_hours: 24`; crowd density reported a raw count as
`vehicles_per_hour`. Fix: `period_hours()` parses the requested window, filters on `created_at`, reports
window metadata (`hours`, `since`, `truncated`), and density divides by the window.
*Evidence:* 6 tests — empty DB returns real zeros, 48 h-old rows are excluded from `24h` and included in
`7d`, 48 events over 24 h → `vehicles_per_hour ≈ 2.0`, `threat_level.counts` matches the dashboard contract.

**12 — BandwidthEngine invented figures on failure** · FIXED
The panel shipped a full fake payload in its `catch` (and repeated the numbers as `??` fallbacks), so a
failed `/api/stats/bandwidth` still "reported" 320 Gbps, 94.3 PB/month and 1600 edge nodes. Fix: shape
tolerance only (missing key → 0/empty), honest failure state, non-OK response throws.
*Evidence:* 3 frontend source-contract tests, incl. explicit absence of the old fabricated literals.

**13 — camera-state collapse** · FIXED
`NOT_CONFIGURED` was mapped to `OFFLINE`, turning every unprovisioned registry slot into a red
"Not working" fault and inflating outage counters. Fix: `asCameraStatus()` preserves
`NOT_CONFIGURED` (also accepts `NOT CONFIGURED` / `UNCONFIGURED`), trims/uppercases input, and still
falls back to `OFFLINE` for anything unrecognized; `CameraStatus` type + chips/colours updated.
*Evidence:* 5 frontend tests; **live registry proof** — `CAMLIVE | NOT_CONFIGURED` alongside
`CAM01–04 | OFFLINE`.

**14 — `CameraPlayer` stale `streamType` dependency** · FIXED
The MJPEG effect read `ticket.streamType` but omitted it from its dependency array, so a ticket that
changed transport left `mjpegSrc` null while the player was already in `<img>` mode — permanently black
with no fallback. Fix: `isMjpeg` added to the deps (with a comment explaining why it must stay).

**15 — Command Center fetched once per page load** · FIXED
Every counter, "last seen" and "last hour" figure froze for the session (only alerts moved, via
realtime). Fix: poll events + KPIs on `KPI_REFRESH_MS` and tick the clock on `CLOCK_TICK_MS`, both with
cleanup.
*Evidence:* 3 frontend tests, incl. an interval/cleanup balance check.

**16 — stray root `package-lock.json`** · REMOVED
`name: zip-2`, empty `packages`, no root `package.json` — pure junk that confused tooling.
*Evidence:* frontend test asserts no root lockfile/package pair and that the frontend lockfile remains.

### ROBUSTNESS

**17A — `alerts.py` status shadowing + HTTP constants** · FIXED
A local `status` shadowed the module-level constant and `HTTPException`-adjacent names were re-bound, so
the status filter silently mis-behaved. Fix: distinct names, filter honoured.
*Evidence:* status-filter tests + constant-identity assertions.

**17B — resolve packed the note into the operator** · FIXED (both ends)
The UI sent `operator: "resolve: <note>"`, so the backend stored the whole string as `resolved_by` and
the note was unrecoverable. Fix: `POST /alerts/{id}/resolve` takes `operator` and `note` separately
(legacy `resolve:` prefix still parsed for old clients), persists `resolution_note`, and the frontend
maps `resolution_note ?? message` into `note`.
*Evidence:* backend resolve tests (separation + legacy prefix) + 2 frontend tests.

**17C — WS envelope carried both `payload` and `data`** · FIXED
Clients had to guess which key held the frame. Fix: single payload key, documented envelope.
*Evidence:* envelope test asserts exactly one payload key.

**17D — cross-loop broadcast** · FIXED
`ws_manager.broadcast` was called from worker threads without hopping to the event loop, so frames were
dropped. Fix: `broadcast_threadsafe` schedules onto the owning loop.
*Evidence:* test broadcasts from a non-loop thread and asserts delivery.

**17E — `/cameras/{id}/live` had no existence check** · FIXED
Any id produced a hanging/500 stream instead of a clean 404. Fix: existence check first.
*Evidence:* backend test + **live check** `GET /api/cameras/definitely-not-a-camera-999/live → 404`.

**17F — uploads read the whole file into memory** · FIXED
Fix: streamed upload with size enforcement; an oversized upload is rejected with **no partial file left
behind**.
*Evidence:* streaming size-enforcement tests + a source-level guard assertion.

**17G — cv-engine retry contract** · VERIFIED CORRECT + documented + tested
`_send_with_retries` already behaved correctly (`max_retries` counts retries *after* the first attempt;
2xx → `True`; 4xx → dead-lettered; 5xx/timeout → retry with exponential backoff). Added a docstring
pinning the contract and `test_retry_budget_is_initial_attempt_plus_max_retries` (asserts 4 calls and
sleeps `[1, 2, 4]` for `max_retries=3`). `cv-engine/tests/test_backend_client.py`: **7 tests**.

**18 — EvidenceVault dead code + fake verification** · FIXED
Verification returned success unconditionally and part of the chain code was unreachable. Fix: real
hash chain — `hash` + `previous_hash` per record, recomputed from immutable fields; detects modified
evidence, modified hash and broken chain; chain integrity evaluated **before** record integrity so
`CHAIN_BROKEN` is never masked as `TAMPERED`.
*Evidence:* `tests/test_evidence_vault.py` — **11 tests** (incl. tamper and chain-break cases with
try/finally DB restore for isolation).

**19 — BSA certificate pointed at the wrong URL** · FIXED
Fix: `CERTIFICATE_URL_TEMPLATE = "/api/reports/evidence/{event_id}/certificate"` and
`VERIFY_URL_TEMPLATE = "/api/reports/evidence/{event_id}/verify"`, matching the documented API and the
frontend `EvidenceVault.tsx` links.
*Evidence:* evidence-vault tests assert the emitted URLs resolve to real routes.

### SECURITY

**21 — credentials hardcoded and committed** · FIXED
The Sentinel email/password were literals in `vite.config.ts` (`HACKATHON_DEFAULTS`),
`app/core/config.py`, `cv-engine/config/settings.py`, `AUTO_LIVE_SETUP.md`, `FOUR_APIS_USAGE.md` and
both `.env.example` files — and `trinetra-ai/.env` was tracked in git.
Fix: all literals removed (`SENTINEL_EMAIL: str = ""` etc.), docs replaced with placeholders, examples
blanked, `git rm --cached trinetra-ai/.env` (file kept on disk), and `.gitignore` updated at root,
frontend and backend (`.env`, `.env.*` ignored; `!.env.example` / `!**/.env.example` kept tracked).
*Evidence:* `git ls-files | grep .env` → only the two `.env.example` files; 5 frontend tests scan 10
sources plus the whole `src/` tree for the local secret values and for browser-exposed
`VITE_*` credential keys; production bundle scan → **0 leaks in 68 files**; live proof that the proxy
still authenticates (see §4). Across the whole staged change set, every line mentioning a credential
value is a **removal** (10 files, 33 removed lines, 0 added).

> ⚠️ **ROTATE THESE CREDENTIALS.** Untracking the file stops future exposure but the values remain in
> git history (`db39ae9` and earlier). Treat the Sentinel email/password as compromised: issue new ones,
> put them only in the gitignored `.env` files, and never re-commit them. Scrubbing history
> (`git filter-repo`) rewrites every commit sha and is a team decision, not something this change set does.

**22 — start scripts overwrote `.env` on every launch** · FIXED
`auto-setup-env.mjs`, `start-auto.sh` and `start-auto.ps1` rewrote the env files unconditionally with
hardcoded credentials, destroying operator values (`VITE_MAPBOX_TOKEN`, custom origins, rotated
credentials). Fix: rewritten — no literals; credentials resolved from `process.env` → existing
`.env` → `.env.local` → backend `.env`; files **created only when missing**; **only missing keys
appended**; existing lines left byte-for-byte alone; warns without printing when credentials are absent.
*Evidence:* 6 behavioural tests execute the real script in a throwaway tree (fresh create, byte-preservation,
idempotent second run, backend `.env` untouched, env-var resolution, no secret in output) + 4 source-contract
tests on the two shell launchers.

**23 — docs told operators to set a variable nothing reads** · FIXED
`VITE_BACKEND_ORIGIN` → `BACKEND_ORIGIN` in `README.md` and `trinetra-ai/README.md` (the root README keeps
one deliberate warning that the `VITE_` name is read by nothing). Stale `HACKATHON_DEFAULTS` references
removed from `AUTO_LIVE_SETUP.md` / `FOUR_APIS_USAGE.md`.
*Evidence:* frontend test asserts the documented name, the absence of any instruction to set the wrong one,
and that `BACKEND_ORIGIN` never reaches the browser bundle.

**24 — stale test counts in docs** · FIXED
`README.md` (112 → **197** backend, 80 → **81** cv-engine, + the new `npm test` line and a note that
pytest also drives the frontend suite), `TRINETRAAI/README.md` (91 → 197), `TRINETRAAI/backend/README.md`
(97 → 197, with the new suites named).
`VERIFICATION_REPORT.md` was **left unchanged on purpose**: it is a dated snapshot
("Reported date: 2026-09-04", pinned branch/HEAD) and rewriting its numbers would falsify history.

### MINOR

**20 — dead locals, unused imports, suspected path off-by-one** · DONE
`ruff --select F401,F811,F841` over backend + cv-engine: **66 unused imports removed** (auto-fix, safe
subset only) and **8 dead locals removed by hand**:
`ingest.py` `hls_base` / `whep_origin` / `rtsp_authenticated` (helpers build those URLs now),
`verify_system_integration.py` `original_lifespan` (never restored), `test_cctv_streaming.py` `cam_bad`
and `test_scene_reset.py` `p1`/`p2` (calls kept, bindings dropped), `vehicle_tracker.py` `sub`
(refactor leftover). Two dependency-probe imports were **kept and documented** with `# noqa: F401`
(`easyocr` availability in `ocr_service.py`, `numpy` in `fetch_models.py`) — removing them would change
control flow. No `__init__.py` re-export was touched.
The suspected `parents[3]` / `parents[2]` off-by-one in `database.py` / `alerts.py` was **verified
correct** for the `app/api/*.py` depth — no change.
*Evidence:* `ruff` now reports 0 for those rules; all three suites still green afterwards.

**25 — explicit camera auto-access verification** · DONE — **20/20 checks**
See §4.

**26 — regression tests for the required items** · DONE
Items 1, 2, 4, 5, 6, 17A–F → `tests/test_bugfix_regressions.py` (28). Items 10, 11 →
`tests/test_speed_and_insights_regressions.py` (14). Items 18, 19 → `tests/test_evidence_vault.py` (11).
Item 9 → `tests/test_plate_format_consistency.py` (8). Item 17G → `cv-engine/tests/test_backend_client.py` (7).
Items 3, 8, 9, 12, 13, 14, 15, 16, 21, 22, 23 → `trinetra-ai/tests/` (48), driven from pytest by
`tests/test_frontend_js_suite.py` (3) so one `pytest` run covers all three layers (skipped, never failed,
when node or `node_modules` are missing).

**27 — final report** · this document.

---

## 4. Item 25 — camera auto-access verification (20/20)

Run against **live processes**: real backend (uvicorn `0.0.0.0:8000`, real `trinetra.db`), real vite dev
server (`0.0.0.0:5173`), and a local stub of the Sentinel gateway on `127.0.0.1:8899` so credential
injection is observable without reaching the real host. Credentials appear only as SHA-256 digests.

Both scripts live in this repository and are re-runnable — `scripts/verify/stub_gateway.mjs` (the stub)
and `scripts/verify/verify_camera_access.mjs` (the 20 checks; its header documents the exact three-process
startup sequence).

| # | Check | Result |
|---|---|---|
| 1 | Credentials resolve from the untracked env files (email len 48, password len 14 — values never printed) | PASS |
| 2 | `GET /api/health` | PASS (200, `database_connected: true`) |
| 3 | `GET /api/cameras` returns the registry | PASS (5 cameras) |
| 4 | `GET /api/cameras/cam04/stream` issues a ticket | PASS (200, `expires_at` ends in `Z`) |
| 5 | Unreachable camera degrades honestly | PASS (`playable=false`, `reason="Camera is OFFLINE"`, no invented URL) |
| 6 | Registry distinguishes `NOT_CONFIGURED` from `OFFLINE` (item 13) | PASS (1 vs 4) |
| 7 | `GET /api/ingest/streams/{id}` → `credentials_configured` | PASS (`true`) |
| 8 | Authenticated RTSP URL only ever exposed redacted | PASS (`rtsp_authenticated_exists=true`, no secret in body) |
| 9 | `GET /api/cameras/{unknown}/live` → 404 (item 17E) | PASS |
| 10 | Vite proxy reaches the gateway target | PASS (201) |
| 11 | **Proxy injects HTTP Basic auth — digest matches the env credentials** | PASS (`b0ff32ce58a7045c…`) |
| 12 | WHEP `Location` rewritten onto our own origin | PASS (`/sentinel/stream/cam04/whep-session`) |
| 13 | HLS proxy path also injects credentials | PASS (same digest) |
| 14 | `/api` proxied to the backend (same-origin browser contract) | PASS |
| 15 | Camera registry reachable through the proxy | PASS |
| 16 | Dev-served `src/lib/config.ts` contains no credential | PASS (0 leaks) |
| 17 | Dev-served `index.html` contains no credential | PASS |
| 18 | `CameraPlayer` still auto-requests for any non-OFFLINE camera | PASS |
| 19 | Camera switching still releases the previous feed | PASS |
| 20 | `AUTO_START_CAMERAS` default unchanged (`False`) | PASS |

Supplementary positive-path proof (isolated DB, no network needed):
`pytest tests/test_frontend_contract.py::test_camera_stream_ticket` — an **ONLINE** camera yields a
playable ticket with a real stream URL.

Not verifiable in this sandbox (documented, not a regression): the real Sentinel host is unreachable
here, so registry cameras report honest `OFFLINE` statuses and no live frames arrive.

---

## 5. Investigated and confirmed **not** bugs

| Suspicion | Verdict |
|---|---|
| `reports.py` calling `generate_printable_report_data(report_data=…)` → TypeError | Calls are positional; no bug. |
| Sentinel credentials leaking through stream endpoints | URLs are built at connect time, redacted in every response, never stored in the DB. |
| MJPEG fallback path | Behaves as designed (and item 14 fixed its stale dependency). |
| cv-engine retry/queue behaviour | Correct; contract now documented + tested (17G). |
| Reconnect / backoff logic | Correct; untouched per the constraints. |
| Evidence path-traversal guard | Present and effective; now covered by a test. |
| `parents[3]` / `parents[2]` path depth in `database.py` / `alerts.py` | Correct for `app/api/*.py`. |

---

## 6. How to reproduce

```bash
# Backend (200 tests) — also runs the frontend suite when node is available
cd TRINETRAAI/backend && pytest

# CV engine (84 offline tests; 3 live-feed tests opt-in)
cd cv-engine && pytest
cd cv-engine && TRINETRA_LIVE=1 pytest -m live tests/test_live_sentinel.py -v

# Frontend (48 contract tests, zero dependencies beyond sucrase)
cd trinetra-ai && npm test

# Typecheck + production build
cd trinetra-ai && npx tsc -b && npx vite build

# Dead-code gate
ruff check --select F401,F811,F841 TRINETRAAI/backend cv-engine

# Item 25: camera auto-access verification (20 checks, needs the 3 processes
# described in the header of scripts/verify/verify_camera_access.mjs)
node scripts/verify/stub_gateway.mjs &
node scripts/verify/verify_camera_access.mjs
```

**Local credentials:** put `SENTINEL_EMAIL` / `SENTINEL_PASSWORD` in `TRINETRAAI/backend/.env` and
`trinetra-ai/.env` (both gitignored; see the `.env.example` placeholders). `npm run dev` creates those
files only if they are missing and only appends keys you have not set — it never rewrites your values.

---

## Addendum — post-review hardening (local Windows runs)

Two portability gaps surfaced while an operator ran the local demo chain on
Windows PowerShell; both fixed and verified on 2026-09-12:

| # | Issue | Fix | Tests |
|---|-------|-----|-------|
| A1 | `cv-engine/scripts/make_local_feeds.py` hard-coded the Linux font path `/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf`, so plate sprites crashed on Windows/macOS with an opaque `OSError: cannot open resource` before any feed was written. | `find_font()` picks the first **installed** candidate across Debian/Ubuntu, Fedora, Windows (`arialbd.ttf`, `segoeuib.ttf`, `consolab.ttf`) and macOS; actionable `SystemExit` if none exist. | `cv-engine/tests/test_make_local_feeds_font.py` (3) |
| A2 | The README registered the CAMD01/CAMD02 demo cameras with a **bash heredoc** — impossible to run on PowerShell, so Windows operators had no supported way to get the DEMO FEED cameras into the registry. | New `TRINETRAAI/backend/scripts/register_demo_cameras.py` (idempotent ORM upsert mirroring `run_feed_demo.py::FEEDS`); README now uses it. | `TRINETRAAI/backend/tests/test_register_demo_cameras.py` (3) |

Verified end-to-end after the fixes: `make_local_feeds.py` wrote both feeds
(675 frames each, watchlist plates `GJ 01 AB 1234` / `MH 02 CD 5678` pasted),
`register_demo_cameras` + `point_cameras_at_local_feeds` updated the registry,
and the demo runs with zero model downloads (`run_feed_demo.py` falls back to
the bundled `yolo11n.pt`; `--anpr` uses the offline RapidOCR wheel).

**Updated tallies:** backend **200 passed** (+3), cv-engine **84 passed, 3 deselected** (+3).
