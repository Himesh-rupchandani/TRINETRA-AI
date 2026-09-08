#!/usr/bin/env node
/**
 * SENTINEL UI loop gate — structural checks for trinetra-ai.
 *
 * PROVENANCE (be honest about this file): the original ui-loop-check.mjs described in the
 * loop engine was not present in this checkout (searched repo, remote branch, git history
 * and the workspace zip). This is a faithful RECONSTRUCTION from the loop engine's
 * description, preserving its verified behaviour:
 *   - GREEN (exit 0) on the untouched baseline
 *   - RED (exit 1) on: a renamed route, a purple→cyan gradient, a neon glow, a heavy shadow
 *   - known false positives already fixed upstream are preserved here:
 *       * shadow-2xl on src/components/common/Modal.tsx is allowed (floating layer)
 *       * Alerts.tsx loading path via useAsync is accepted (returns { data, loading, ... })
 *
 * RULES
 *  R1 routes          — all 14 original route paths must exist in src/app/router.tsx
 *  R2 dependencies    — runtime dependency set must exactly match the baseline (8 deps)
 *  R3 frozen layers   — src/{services,hooks,features,types,mocks} must match the manifest:
 *                       nothing added, removed or renamed
 *  R4 vite config     — host 0.0.0.0, allowedHosts, /api + /sentinel + /cvfeed proxies intact
 *  R5 banned visuals  — purple↔cyan AI gradients, neon glow, heavy shadow (Modal exempt)
 *  R6 data paths      — every page renders a loading path; collection pages render an
 *                       empty path (single-record screens exempt: Profile, SystemHealth,
 *                       NotFound)
 *
 * Exit 0 = GREEN, exit 1 = RED. Never fake this green: do not comment out rules, delete
 * the checker, or weaken a rule to pass. If a rule is wrong, fix the rule and say so.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

const ROOT = process.cwd();
const failures = [];
const notes = [];
const fail = (msg) => failures.push(msg);

/* ---------------------------------------------------------------- helpers */
function read(p) {
  try {
    return readFileSync(join(ROOT, p), 'utf8');
  } catch {
    return null;
  }
}

function walk(dir, out = []) {
  let entries;
  try {
    entries = readdirSync(join(ROOT, dir));
  } catch {
    return out;
  }
  for (const e of entries) {
    const p = `${dir}/${e}`;
    const st = statSync(join(ROOT, p));
    if (st.isDirectory()) walk(p, out);
    else out.push(p);
  }
  return out;
}

/* ------------------------------------------------- R1 — the 14 routes ---- */
const ROUTES = [
  "path: 'cameras'",
  "path: 'cameras/:cameraId'",
  "path: 'vehicles'",
  "path: 'vehicles/:plate'",
  "path: 'video-analysis'",
  "path: 'alerts'",
  "path: 'events'",
  "path: 'gis'",
  "path: 'registry'",
  "path: 'watchlist'",
  "path: 'system'",
  "path: 'profile'",
  "path: '*'",
];
const router = read('src/app/router.tsx');
if (!router) {
  fail('R1 src/app/router.tsx is missing');
} else {
  for (const r of ROUTES) {
    if (!router.includes(r)) {
      // Report in the engine's phrasing so a rename is obvious.
      const path = r.match(/'(.+)'/)[1];
      fail(`R1 route "${path}" is missing or renamed`);
    }
  }
  if (!/index:\s*true/.test(router)) fail('R1 dashboard index route is missing');
}

/* ------------------------------------------------- R2 — dependencies ---- */
const EXPECTED_DEPS = new Set([
  'axios',
  'leaflet',
  'lucide-react',
  'react',
  'react-dom',
  'react-leaflet',
  'react-router-dom',
  'recharts',
]);
const pkg = read('package.json');
if (!pkg) {
  fail('R2 package.json is missing');
} else {
  const deps = Object.keys(JSON.parse(pkg).dependencies ?? {});
  for (const d of deps) if (!EXPECTED_DEPS.has(d)) fail(`R2 unexpected dependency "${d}" — no new deps allowed`);
  for (const d of EXPECTED_DEPS) if (!deps.includes(d)) fail(`R2 baseline dependency "${d}" was removed`);
  notes.push(`dependencies: ${deps.length}/8`);
}

/* ------------------------------------- R3 — frozen data-layer manifest --- */
const FROZEN = {
  'src/services': [
    'adapters.ts', 'alertService.ts', 'api.ts', 'cameraService.ts', 'eventService.ts',
    'officerService.ts', 'realtimeService.ts', 'systemService.ts', 'uploadService.ts',
    'vehicleService.ts', 'videoAnalysisService.ts', 'whepClient.ts',
  ],
  'src/hooks': [
    'useAlerts.ts', 'useAsync.ts', 'useCameras.ts', 'useEvents.ts', 'useLiveEvents.ts',
    'useUi.ts', 'useVehicleSearch.ts', 'useWhepStream.ts',
  ],
  'src/features': [
    'alerts/LiveProvider.tsx', 'officer/OfficerProvider.tsx', 'system/ToastProvider.tsx',
  ],
  'src/types': [
    'alert.ts', 'camera.ts', 'event.ts', 'index.ts', 'officer.ts', 'system.ts', 'vehicle.ts',
  ],
  'src/mocks': [
    'alerts.ts', 'cameras.ts', 'events.ts', 'health.ts', 'mockBackend.ts', 'officer.ts',
    'watchlist.ts',
  ],
};
for (const [dir, expected] of Object.entries(FROZEN)) {
  const actual = walk(dir)
    .map((p) => relative(dir, p))
    .sort();
  for (const f of actual) if (!expected.includes(f)) fail(`R3 frozen layer ${dir}/${f} was added — data layer must not change`);
  for (const f of expected) if (!actual.includes(f)) fail(`R3 frozen layer ${dir}/${f} was removed or renamed`);
}

/* ------------------------------------------------- R4 — vite config ----- */
const vite = read('vite.config.ts');
if (!vite) {
  fail('R4 vite.config.ts is missing');
} else {
  for (const needle of ["host: '0.0.0.0'", 'allowedHosts: true', "'/api'", "'/sentinel'", "'/cvfeed'"]) {
    if (!vite.includes(needle)) fail(`R4 vite.config.ts no longer contains ${needle}`);
  }
}

/* ------------------------------- R5 — banned visual patterns (AI-slop) -- */
const SOURCE_FILES = [...walk('src'), 'tailwind.config.js'].filter((p) =>
  /\.(tsx|ts|css|js)$/.test(p),
);
const MODAL_EXEMPT = 'src/components/common/Modal.tsx'; // floating layer — shadow allowed
const HOT_PAIRS = [
  ['from-(purple|violet|fuchsia|pink)-\\d+', 'to-(cyan|sky|blue|indigo|teal)-\\d+'],
  ['to-(purple|violet|fuchsia|pink)-\\d+', 'from-(cyan|sky|blue|indigo|teal)-\\d+'],
];
for (const p of SOURCE_FILES) {
  const src = read(p);
  if (!src) continue;
  const lines = src.split('\n');
  lines.forEach((line, i) => {
    for (const [a, b] of HOT_PAIRS) {
      if (new RegExp(a).test(line) && new RegExp(b).test(line)) {
        fail(`R5 AI gradient (purple↔cyan) at ${p}:${i + 1}`);
      }
    }
    if (/\bdrop-shadow-(xl|2xl)\b/.test(line)) fail(`R5 neon glow at ${p}:${i + 1}`);
    if (/text-shadow/.test(line)) fail(`R5 neon glow (text-shadow) at ${p}:${i + 1}`);
    const arb = line.match(/shadow-\[\s*['"]?0\s+0\s+(\d{2,})px/);
    if (arb && Number(arb[1]) >= 25) fail(`R5 neon glow (blur ${arb[1]}px) at ${p}:${i + 1}`);
    // Negative lookbehind: "drop-shadow-2xl" is the glow rule, not the heavy-shadow rule.
    if (p !== MODAL_EXEMPT && /(?<!drop-)\bshadow-2xl\b/.test(line)) fail(`R5 heavy shadow at ${p}:${i + 1}`);
  });
}

/* ------------------------------------- R6 — loading / empty data paths --- */
const LOADING_RE =
  /LoadingState|AsyncBoundary|useAsync|\.loading\b|isLoading|loading=|skeleton|busy|jobStatus/;
const EMPTY_RE = /EmptyState|emptyTitle|isEmpty/;
/** Pages that render collections and must show an empty path. */
const COLLECTION_PAGES = new Set([
  'Alerts', 'CameraDetail', 'Cameras', 'Dashboard', 'Events', 'GIS', 'Registry',
  'VehicleInvestigation', 'Vehicles', 'VideoAnalysis', 'Watchlist',
]);
/** Pages exempt from the empty-path requirement (single-record / static screens). */
const EMPTY_EXEMPT = new Set(['NotFound', 'Profile', 'SystemHealth']);
for (const p of walk('src/pages')) {
  const name = p.replace('src/pages/', '').replace('.tsx', '');
  const src = read(p) ?? '';
  if (name === 'NotFound') {
    if (LOADING_RE.test(src)) fail(`R6 ${name} should not fake a loading path`);
    continue;
  }
  if (!LOADING_RE.test(src)) fail(`R6 page ${name} has no loading path`);
  if (COLLECTION_PAGES.has(name) && !EMPTY_EXEMPT.has(name) && !EMPTY_RE.test(src)) {
    fail(`R6 page ${name} renders a collection but has no empty path`);
  }
}

/* ------------------------------------------------------------- report --- */
const scanned = SOURCE_FILES.length;
for (const f of failures) console.log(`FAIL ${f}`);
console.log('='.repeat(64));
console.log(`scanned ${scanned} source files · ${notes.join(' · ')}`);
if (failures.length) {
  console.log(`RED — ${failures.length} failure${failures.length > 1 ? 's' : ''}`);
  process.exit(1);
}
console.log('GREEN — all structural checks passed');
process.exit(0);
