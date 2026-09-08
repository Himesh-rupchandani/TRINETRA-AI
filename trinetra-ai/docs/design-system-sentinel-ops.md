# TRINETRA AI — "Sentinel Ops" Design System

Dark command-room theme for the Sentinel police hackathon. Shipped as a restyle of the
existing token layer: **no component class was renamed or removed, no API/hook/service
was touched, no dependency was added.**

## Dark mode decision

**Option (a) — dark is the single always-on theme.** The `:root` token values in
`src/index.css` were swapped to the dark palette, `index.html` sets
`<meta name="color-scheme" content="dark">` + `theme-color #070C16`, and `src/main.tsx`
enforces `colorScheme = 'dark'` before first paint. There is no `darkMode` key in
`tailwind.config.js` and zero `dark:` variants — nothing is half-styled.

## Token table (`src/index.css` `:root`)

| Token          | Value     | Role                                        |
| -------------- | --------- | ------------------------------------------- |
| `--surface-0`  | `#070C16` | App canvas                                  |
| `--surface-1`  | `#0D1524` | Panels, header, sidebar                     |
| `--surface-2`  | `#131E30` | Table head, hover, tile wells               |
| `--surface-3`  | `#1B2A40` | Raised chips, skeletons                     |
| `--line`       | `#1E2532` | Hairline ≈ white/8%                         |
| `--line-strong`| `#333F53` | Emphasis hairline ≈ white/16%               |
| `--ink`        | `#E8EEF9` | Primary text — 15.2:1 on surface-1         |
| `--ink-muted`  | `#A2B0C6` | Secondary text — 8.9:1                     |
| `--ink-faint`  | `#7A8AA3` | Metadata / section labels — 5.2:1          |
| `--brand`      | `#22D3EE` | Trinetra cyan — the eye                    |
| `--brand-soft` | `#0E3A46` | Cyan well / selected wash                   |
| `--accent`     | `#F5A524` | Amber — accents only                        |
| `--on-brand`   | `#06121D` | Ink on cyan fills — 10.4:1                 |

> `--ink-faint` is one step lighter than the originally suggested `#6B7A93` because the
> suggested value measures **4.2:1** on panels — under the 4.5:1 body-text bar. The
> shipped value was verified with a WCAG contrast probe across every surface.

### Severity / status ramp (`tailwind.config.js`)

| Token       | Value     | Notes                                   |
| ----------- | --------- | --------------------------------------- |
| `critical`  | `#FF3B5C` | The only colour that competes with cyan |
| `high`      | `#FF8A3D` |                                         |
| `medium`    | `#FFC53D` |                                         |
| `low`       | `#38BDF8` |                                         |
| `info`      | `#94A3B8` |                                         |
| `online`    | `#34D399` |                                         |
| `offline`   | `#F87171` |                                         |
| `degraded`  | `#FBBF24` |                                         |
| `processing`| `#60A5FA` |                                         |

All values were contrast-checked against `#0D1524` (worst case ≥ 4.5:1 as text, ≥ 3:1 as UI).

## The eye motif

`src/components/common/EyeMark.tsx` — concentric radar rings, compass ticks, iris +
pupil and a slow vertical scan sweep (`eye-sweep`, CSS keyframes). Used in the sidebar
logo lockup, the Dashboard command strip, the 404 and the favicon
(`public/trinetra.svg`). Decorative ring backgrounds (`.eye-rings`) also sit behind
empty states — always low opacity, never behind body text.

## Motion budget (plain CSS only)

- `animate-pulse-ring` — critical NEW alerts (re-tuned to `#FF3B5C`)
- `animate-slide-in` — 160 ms fade + translateY on alert arrival / toasts
- `.scan-sweep` — 2 px radar sweep on camera tiles and the dashboard hero (3.8 s loop)
- `.live-dot` — soft green pulse for LIVE indicators
- `prefers-reduced-motion: reduce` disables **all** looping animation and hides the sweep

## Live state machine (Header)

`LIVE` (green pulse) · `CONNECTING` (amber) · `DEMO FEED` (cyan, mock mode) ·
`OFFLINE` → red **"BACKEND OFFLINE — RETRYING"** chip; the last known data stays on
screen, nothing white-screens.

## Map

Dark CARTO basemap (`dark_all` + `dark_only_labels`, keyless, attribution in the
config). Vehicle route renders as a **cyan → amber gradient polyline** with numbered
sighting markers; watchlist hits are **red pulse markers**; cameras are **small cyan
rings**. Leaflet chrome (zoom bar, popups, attribution) is themed via the
`.leaflet-*` overrides in `index.css`. If tiles are unreachable the map degrades to
the dark canvas.

## Fonts

Inter + JetBrains Mono are **self-hosted** (`public/fonts/*.woff2`, latin subsets,
~220 KB total) via `@font-face` in `index.css` — no external font CDN, identical
rendering offline. All plates, coordinates, confidences, timestamps and IDs use
JetBrains Mono with `tabular-nums`.

## Verification (run from `trinetra-ai/`)

```
npm run typecheck  # exit 0
npm run lint       # 24 warnings, 0 errors  (same warning set as the baseline)
npm run build      # ✓ built in ~1.3 s
```

Browser sweep (headless Chromium, 1440×900): all 14 routes render with mocks on
**and** with the backend down; no app-internal request failures, no unhandled promise
rejections, no horizontal scroll and **no page-level scroll on the Dashboard**;
WCAG contrast probe over rendered text passes; `:focus-visible` ring intact.
