# UI_LOOP_LOG — SENTINEL UI rebuild loop

Engine: `docs/UI_PROMPT.md` loop prompt · Spec: `docs/UI_PROMPT.md` ·
Gate: `trinetra-ai/scripts/ui-loop-check.mjs` · Full gate = gate script + typecheck +
lint (0 errors, warnings must not increase) + build.

## Provenance (read this first)

- `docs/UI_PROMPT.md` and `trinetra-ai/scripts/ui-loop-check.mjs` were **not present in
  this checkout** (searched: repo tree, remote `arena/01a080bb-hack`, full git history,
  workspace zip). Both are **reconstructions** — the spec from the loop engine's rubric +
  the shipped Sentinel Ops system, the gate from the engine's description of its verified
  behaviour (GREEN baseline; RED on renamed route / purple→cyan gradient / neon glow /
  heavy shadow; Modal `shadow-2xl` exempt; useAsync loading accepted). If the originals
  surface, swap them in and re-run.
- Starting point of this loop = commit `22b2601` ("Sentinel Ops: dark command-center
  restyle"), already shipped and verified (typecheck 0 / lint 24-0 / build ~1.3s /
  14-route headless sweep passed in the prior session).
- Visual judgements in this log come from **reading rendered markup/CSS** (grep +
  computed-class evidence) — there is no headless browser in this environment. Pixel-level
  claims are never made.

## Baseline gate run (session start, before any loop change)

```
node scripts/ui-loop-check.mjs   → RED — 1 failure:
  FAIL R6 page GIS renders a collection but has no empty path
```

The GIS page showed `LoadingState` whenever `cameras.length === 0`, conflating "loading"
with "loaded but empty" (the pre-restyle code passed this check only because it misused
`EmptyState` as a loading label). **Fixed the page, not the rule**: GIS now distinguishes
loading from empty and offers a "Reload network" action. Gate → GREEN, exit 0.
`npm run typecheck` → exit 0 · `npm run lint` → 24 warnings / 0 errors ·
`npm run build` → ✓ built.

## Gate self-test (reconstruction validated against the engine's described behaviour)

| Injection | Gate result |
|---|---|
| Rename `vehicles/:plate` → `investigation/:plate` | `FAIL R1 route "vehicles/:plate" is missing or renamed` |
| `from-purple-500 to-cyan-400 shadow-2xl` (one string) | `FAIL R5 AI gradient` + `FAIL R5 heavy shadow` |
| `drop-shadow-2xl` alone | `FAIL R5 neon glow` (single, clean attribution) |
| Restored | GREEN — exit 0, `git status` clean |

One gate fix during self-test, disclosed: `shadow-2xl` inside `drop-shadow-2xl` was
double-reported; added a negative lookbehind so the glow rule and the heavy-shadow rule
attribute cleanly. No rule was weakened.

## Inner loop

| Iter | Surface | Criterion | Before | After | Change made | Gate |
|------|---------|-----------|--------|-------|-------------|------|
| 0 | setup | gate exists | — | — | reconstructed spec + gate; fixed real GIS empty-path gap it caught | GREEN |

### Surface 1 — Design tokens + primitives — Phase 1 (MEASURE, before any code change)

Evidence gathered by grepping the actual source (not memory):

| # | Criterion | Score | Evidence |
|---|-----------|-------|----------|
| 1 | Spacing rhythm | 2 | Primitives use off-scale values: `.btn`/`.panel-header`/`.data-table` `px-3.5` (14px), `py-2.5` (10px), `.btn-xs px-2.5` (10px). 161 off-scale gap/padding instances across src (18× gap-2.5, 18× py-2.5, 10× px-3.5, 37× gap-1.5, 14× p-5…). Page-level instances are later surfaces/audit A; primitives are this surface. |
| 2 | Typography | 2 | 11 distinct sizes in use (10, 11, 13, 14, 15, 16, 18, 21, 22, 24, 30px + a 26.4px KPI rem size) vs the 6-level spec (11/13/14/15/21/24–30). Mono+tabular-nums for data is solid; the count is the problem. |
| 3 | Visual hierarchy | 3 | Clear ladder in primitives: solid cyan primary → tint → ghost → danger; panel header/title/body separation. |
| 4 | Layout composition | 3 | Right pattern per control: `.data-table` for rows, `.panel` for sections, `.chip` for metadata, `.plate-chip` for the hero plate. |
| 5 | Colour discipline | 2 | `shadow-glow` (18px cyan blur) on `.btn-primary`, `TILE_ACTIVE` (IconTile) and MovementTimeline active node — violates "no glow" (rubric 5 / spec §7). Amber accent otherwise restrained. |
| 6 | Component quality | 2 | `.btn` has default/hover/disabled(+opacity) but NO press state; loading handled at call sites (spinner + disabled), empty/error via Panel primitives. |
| 7 | Motion | 2 | Hover transitions 150ms colour-only ✓, pulse/sweep are state signals ✓, reduced-motion globally honoured ✓ — but the eye-mark sweep loops decoratively (brand exception, spec §6 allows ≤5s; keep under review in audit E). |
| 8 | Consistency | 3 | One `.btn` family, one `.chip`, one `.panel`, severity/status chips centralized in Chips.tsx/utils.ts. |
| 9 | Responsive | 2 | `.btn` is 36px (28px xs) — below the 44px touch target required at ≤834px (spec §10/§11). Needs a touch-breakpoint bump; deferred to audit F with this log entry as the record. |
| 10 | Accessibility | 3 | Contrast probe over rendered text passed in prior session (ink-faint was raised to #7A8AA3 to clear 4.5:1); `:focus-visible` ring verified; chips carry text labels, severity uses rail+label+colour. |
| 11 | Judge readability | 3 | Primitives carry the story: mono data, LIVE states, severity rails; badge + lockup live in the shell (surface 2's concern). |
| 12 | No AI-slop | 2 | Glow on primary buttons is the classic AI-dashboard tell; removing it (fix below) is the single biggest de-slop win available at this layer. |

### Surface 1 — Phase 2 (HYPOTHESES — the three lowest criteria)

1. **Criterion 1 (spacing)**: primitive padding uses 14px/10px off-scale values — change
   `.btn`/`.panel-header`/`.data-table` padding from `px-3.5`→`px-4` (14→16) and
   `py-2.5`→`py-2` (10→8, landing rows at ~35px ≈ the 36px spec) and `.btn-xs`
   `px-2.5`→`px-3` (10→12), so every primitive sits on the 4/8/12/16 scale.
2. **Criterion 5 (colour discipline)**: `shadow-glow` puts a cyan blur on primary
   buttons, the active sidebar tile and the active timeline node — delete the
   `boxShadow.glow` token and all three usages; hairline borders already carry the
   dark-UI separation.
3. **Criterion 6 (component quality)**: `.btn` has no press state — add `active:`
   background variants to each button class so default/hover/press/disabled are all
   expressed in the primitive itself.

## Known gaps

- **Typography level count (criterion 2, score 2)** — 11 distinct sizes vs the 6-level
  spec; consolidation (10→11, 22→21, 26.4→24, retiring 16/18 where a level neighbour
  fits) is planned as surface-1 iteration 2 or audit B.
- **Touch targets (criterion 9, score 2)** — 36px buttons at mobile breakpoints; fix
  planned in audit F (responsive) via a touch-breakpoint height bump.
- **Toast micro-padding** — `p-2.5` inside `src/features/system/ToastProvider.tsx` is
  off-scale but the file lives in a frozen layer; recorded, cannot touch without a spec
  decision.
- **No headless browser** — no pixel/rendered-contrast measurement in this environment;
  contrast figures cited come from the prior session's headless probe (before this
  session's token changes) plus static WCAG math on the token values.
