# UI_PROMPT — SENTINEL / TRINETRA AI design specification

> **PROVENANCE:** the original `docs/UI_PROMPT.md` referenced by the loop engine was not
> present in this checkout. This is a reconstruction written from (a) the loop engine's
> rubric and anti-patterns, (b) the shipped "Sentinel Ops" design system
> (`trinetra-ai/docs/design-system-sentinel-ops.md`), and (c) the original restyle brief.
> It is the loop's source of truth for WHAT to build. Where the shipped code deviates from
> this spec, the spec wins and the loop converges the code toward it. If the original spec
> surfaces, diff and replace this file — then re-run the loop.

## 1. Product story (the 10-second test)

SENTINEL is the hackathon; **TRINETRA AI** is the product: a hybrid CCTV intelligence
platform for the Gujarat Police. Many cameras → one eye that never blinks → fast,
evidence-backed response. Flow that already works end to end: Sentinel CCTV feed →
YOLO11 vehicle detection → PTS-driven tracking → ANPR plate read → sighting event →
watchlist match → alert → operator triage → vehicle trace → GIS route reconstruction.

Every screen must let a cold judge answer in 10 seconds: what it is (police CCTV command
room), that it is AI/computer vision, that it runs on real cameras, what it detects
(vehicles + plates + watchlist hits), and who built it (sidebar badge: Sentinel
Hackathon · TRINETRA AI).

Primary user: a duty officer on 1920×1080/1440×900, projected in a bright room.
Demo: 4 minutes, live, backend optional (`VITE_USE_MOCKS=true`).

## 2. Design principles

1. **Operator density, not marketing whitespace** — tables and camera grids stay dense;
   section headers and settings rows stay spacious. One primary focal point per viewport.
2. **Hairlines over shadows** — dark UIs are separated by 1px borders and surface steps,
   not elevation. Shadows only on true floating layers (modals).
3. **Data is monospace** — plates, coordinates, confidences, timestamps, IDs: JetBrains
   Mono, tabular-nums, always.
4. **Cyan is the eye; red is the only competitor** — brand cyan marks live/vision/system
   chrome. Critical red is reserved for things that demand action. Amber appears rarely.
5. **Restraint reads as craft** — no gradients between hues, no glow, no neon. The
   command-room look comes from the palette and typography, not effects.

## 3. Palette (tokens in `trinetra-ai/src/index.css` `:root`)

| Token | Value | Role |
|---|---|---|
| `--surface-0` | `#070C16` | App canvas |
| `--surface-1` | `#0D1524` | Panels, header, sidebar |
| `--surface-2` | `#131E30` | Table head, hover, wells |
| `--surface-3` | `#1B2A40` | Raised chips, skeletons |
| `--line` / `--line-strong` | `#1E2532` / `#333F53` | Hairlines ≈ white 8% / 16% |
| `--ink` | `#E8EEF9` | Primary text (15.2:1 on surface-1) |
| `--ink-muted` | `#A2B0C6` | Secondary text (8.9:1) |
| `--ink-faint` | `#7A8AA3` | Metadata, section labels (5.2:1) |
| `--brand` | `#22D3EE` | Trinetra cyan — the eye |
| `--brand-soft` | `#0E3A46` | Cyan well / selected wash |
| `--accent` | `#F5A524` | Amber — accents only, once per view |
| `--on-brand` | `#06121D` | Ink on cyan fills (10.4:1) |

Severity/status (dark-tuned): critical `#FF3B5C` · high `#FF8A3D` · medium `#FFC53D` ·
low `#38BDF8` · info `#94A3B8` · online `#34D399` · offline `#F87171` · degraded
`#FBBF24` · processing `#60A5FA`. Contrast: body text ≥ 4.5:1, UI text ≥ 3:1 on their
actual surface — verified, not assumed. Severity is never colour-only: every severity
signal also carries a label and/or an icon and/or a rail.

## 4. Spacing scale

**Layout gaps and padding use only: 4 · 8 · 12 · 16 · 24 · 32 · 48 · 64 px**
(Tailwind `1 · 2 · 3 · 4 · 6 · 8 · 12 · 16`). Rules:

- Flex/grid `gap-*`, panel padding, page gutters and section rhythm MUST be on-scale.
  Hunt `gap-2.5` (10), `gap-3.5`/`px-3.5` (14), `gap-5`/`p-5` (20), `gap-1.5` (6) —
  normalize to the nearest step.
- Component-internal micro-padding (chip `py-0.5`, hairline offsets) is the one tolerated
  exception; if a value exceeds 4px it belongs on the scale.
- Base rhythm 8px. Panel padding 12–16px. Table rows ~36px with sticky headers.
- Heights are sizes, not gaps: `h-9` (36px controls), `h-11` (44px touch target) are
  correct and stay.

## 5. Typography — six levels only

| Level | Size | Weight / tracking | Used for |
|---|---|---|---|
| T1 Caption | 11px | 600, 0.08em, uppercase, `--ink-faint` | Section labels, panel titles, kv-labels, OSD micro-text |
| T2 Secondary | 13px (`2xs`) | 400–600 | Table body, hints, metadata rows |
| T3 Body | 14px (`xs`) | 400–600 | Default control text, body copy |
| T4 Body-strong | 15px (`sm`) | 500–700 | Emphasis body, subtitles |
| T5 Title | 21px (`xl`) | 600, tight tracking | Page titles |
| T6 Display | 24–30px | 700, mono where numeric | Hero plate, KPI numerals, clock — at most one per view |

Rules: Inter for UI, JetBrains Mono (`tabular-nums`) for ALL plates, coordinates,
confidences, timestamps, IDs and counters. Hierarchy is carried by size and weight —
never by colour alone. Nothing oversized: no text above 30px anywhere. Consolidate
one-off sizes (`text-[10px]` → T1, `text-[22px]` → T5, `1.65rem` KPI → within T6 band).

## 6. Motion

- Transitions and entrances: **120–200ms**, `opacity`/`transform` (and colour for hover
  states) only. Nothing bounces, springs or parallaxes.
- Looping animation is a *state signal*, not decoration: LIVE pulse dot, critical alert
  `pulse-ring`, scan sweep on live camera surfaces. The eye-mark sweep is the single
  brand exception and must stay ≤ 5s cycle, low opacity.
- `prefers-reduced-motion: reduce` disables every loop and hides the sweeps (global rule
  in `index.css` — do not weaken it).

## 7. Anti-patterns (banned — also enforced by `scripts/ui-loop-check.mjs`)

- Purple/blue/cyan **gradient fills** between hues (`from-purple-500 to-cyan-400` & co).
- **Neon glow**: `drop-shadow-xl/2xl`, `text-shadow`, arbitrary shadows with blur ≥ 25px,
  glowing text or borders.
- **Heavy shadows** on in-page surfaces (`shadow-2xl`); shadow is allowed only on true
  floating layers (Modal).
- Equal-card walls where a table/list/timeline fits the data better.
- Colour-only severity. Lorem ipsum. Dead-end empty states. Blank/spinner-only loading.
- Off-scale spacing values (see §4) and a seventh type level.

## 8. Component primitives (`src/index.css` `@layer components`)

Class names are frozen — pages must never need rewriting to benefit from a primitive fix.

- `.btn` family (`-primary -solid -tint -ghost -danger -xs`): states complete —
  default / hover / **active (press)** / disabled / loading (spinner + disabled).
  Primary = cyan fill + `--on-brand` ink. Heights: 36px default, 28px xs, 44px on touch
  breakpoints.
- `.input` / `.select`: 36px, dark well (`--surface-0`), cyan focus ring (2px, 25%).
- `.chip` + severity/status chips: 2px micro-padding, always carries a text label.
- `.panel` / `.panel-header` / `.panel-title`: 12px radius, hairline border, 44px header.
- `.data-table`: sticky header, ~36px rows, hover lifts to `--surface-2`.
- `.plate` / `.plate-chip`: mono, uppercase, tabular-nums; hero plate on the HSRP-style
  light chip.
- `.skeleton` for every loading state. `.scanline` / `.scan-sweep` / `.hud-chip` /
  `.live-dot` for live surfaces. `.eye-rings` decorative backdrop, never behind body text.
- `.section-label`: T1 caption style.

## 9. Page-by-page requirements (the 14 routes)

1. **Dashboard** (`/`) — command strip (eye lockup, live IST clock in mono, cameras
   online X/Y, system-health pill), 4 KPI cards with sparkline + delta vs last hour,
   6-tile live camera mosaic (scanline + HUD: camera ID, location, FPS/latency, det/min),
   watchlist alert list with severity rails, live detection feed, 24h detections chart.
   No page-level scroll at 1440×900. Nothing below the fold matters.
2. **Cameras** (`/cameras`) — dense tile grid, filter bar, instant search, per-tile
   open-camera; tiles show the live state machine (LIVE/POOR/OFFLINE).
3. **CameraDetail** (`/cameras/:cameraId`) — opt-in stream, measured OSD, technical
   drawer, event history.
4. **Vehicles** (`/vehicles`) — trace-first search with demo-plate suggestions.
5. **VehicleInvestigation** (`/vehicles/:plate`) — plate hero card (huge mono plate,
   colour chip, make/model, best confidence), route map, movement timeline, evidence
   crops with detection boxes, case-officer assignment, detection history.
6. **VideoAnalysis** (`/video-analysis`) — multi-video upload + cross-video plate
   journeys; job status board.
7. **Alerts** (`/alerts`) — triage list: 3px severity rails, filters, one-click
   acknowledge, single primary action per row (Trace). Critical rows pulse.
8. **Events** (`/events`) — filterable detection log (the evidence backbone).
9. **GIS** (`/gis`) — dark map, gradient route polyline, numbered sighting markers,
   red-pulsing watchlist hits, cyan-ring cameras, legend.
10. **Registry** (`/registry`) — full camera table.
11. **Watchlist** (`/watchlist`) — wanted-vehicle records with severity.
12. **SystemHealth** (`/system`) — service board with heartbeats.
13. **Profile** (`/profile`) — officer dossier + challan figures.
14. **NotFound** (`*`) — on-brand 404 with the eye motif and a way back.

Global demo-day requirements: the app survives a dead backend (no white screen; header
shows BACKEND OFFLINE — RETRYING while keeping last data), every loading state is a
skeleton, every empty state has icon + one-line explanation + one action, realistic
Indian plates (GJ-01-AB-1234), real Gujarat locations, plausible officer names.

## 10. Accessibility

Contrast ≥ 4.5:1 body / ≥ 3:1 UI on actual surfaces · visible `:focus-visible` ring
everywhere · full keyboard operability · severity never colour-only · reduced-motion
respected · touch targets ≥ 44px at ≤ 834px.

## 11. Responsive

1920 / 1440 / 1280: full operator layout. 834: sidebar collapses to drawer, grids
re-flow, controls grow to 44px. 390: single column, no horizontal overflow ever,
search and primary actions remain reachable.

## 12. Frozen layers (loop rule, restated)

`src/services/`, `src/hooks/`, `src/features/`, `src/types/`, `src/mocks/` and
`vite.config.ts` are never edited by the loop. If a design need seems to require a
data-layer change, stop and report a spec problem instead.
