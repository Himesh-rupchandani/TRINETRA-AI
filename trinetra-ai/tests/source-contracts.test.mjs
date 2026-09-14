/**
 * Frontend regression tests — items 12, 14, 15, 16, 23 and the frontend half
 * of item 3 / 17B (API path construction).
 *
 * The pieces asserted here are React components and Vite config, which cannot
 * be executed without a DOM/jsdom that this repository does not install. They
 * are pinned by source contract instead: each assertion names the exact line
 * whose removal would reintroduce the bug, so a well-meaning refactor that
 * drops a dependency, a cleanup call or an error branch fails the suite.
 */
import fs from 'node:fs';
import path from 'node:path';
import { FRONTEND_ROOT, REPO_ROOT, excludes, includes, notOk, ok, readSource, suite, test } from './harness.mjs';

/* ------------------------- item 12: bandwidth panel ------------------------ */
suite('item 12 — BandwidthEngine never invents projection numbers');

const bandwidth = readSource('trinetra-ai/src/components/dashboard/BandwidthEngine.tsx');

test('a missing key renders as zero through the EMPTY shape', () => {
  includes(bandwidth, 'const EMPTY: BandwidthData = {');
  includes(bandwidth, 'federation: { edge_nodes_required: 0, central_servers_required: 0, scalability: \'\' }');
  includes(bandwidth, 'federation: { ...EMPTY.federation, ...(json.federation ?? {}) }');
  includes(bandwidth, 'savings: { ...EMPTY.savings, ...(json.savings ?? {}) }');
  includes(bandwidth, 'gujarat_network: { ...EMPTY.gujarat_network, ...(json.gujarat_network ?? {}) }');
});

test('the federation block is read from the payload, not hardcoded', () => {
  includes(bandwidth, '{federation.edge_nodes_required ?? 0}');
  includes(bandwidth, '{federation.central_servers_required ?? 0} servers');
  includes(bandwidth, '{federation.scalability || \'Linear scaling\'}');
});

test('a failed fetch is surfaced instead of being papered over', () => {
  includes(bandwidth, 'if (!res.ok) throw new Error(`Bandwidth engine responded ${res.status}`);');
  includes(bandwidth, 'Bandwidth projection unavailable');
  includes(bandwidth, 'The bandwidth engine did not return data');
  // The old catch branch shipped a complete fake payload; none of its figures
  // may reappear as a literal fallback.
  excludes(bandwidth, 'total_cameras: 80000');
  excludes(bandwidth, 'centralized_gbps: 320');
  excludes(bandwidth, 'pb_per_month: 94.3');
  excludes(bandwidth, 'edge_nodes_required: 1600');
});

/* --------------------------- item 14: CameraPlayer ------------------------- */
suite('item 14 — the MJPEG effect depends on the transport it reads');

const player = readSource('trinetra-ai/src/components/camera/CameraPlayer.tsx');

test('isMjpeg is part of the dependency array', () => {
  includes(player, 'const isMjpeg = ticket?.streamType === \'MJPEG\';');
  includes(player, 'setMjpegSrc(isMjpeg ? (ticket?.streamUrl || `/cvfeed/${camera.id}`) : null);');
  includes(
    player,
    '}, [ticket?.cameraId, ticket?.streamUrl, ticket?.detectionUrl, detectionActive, camera.id, isMjpeg]);',
    'a stale dependency array leaves the player black after an MJPEG fallback',
  );
  excludes(player, "setMjpegSrc(ticket?.streamType === 'MJPEG' ? `/cvfeed/${camera.id}` : null);\n  }, [ticket?.cameraId, ticket?.streamUrl, ticket?.detectionUrl, detectionActive, camera.id]);");
});

test('automatic camera access is untouched', () => {
  includes(player, "if (autoRequest && camera.status !== 'OFFLINE') void requestStream();");
  includes(player, '// Switching camera always releases the previous feed first.');
  includes(player, '}, [camera.id]);');
  includes(player, 'const requestStream = async () => {');
  // The HLS/WHEP fallback chain that keeps live playback working must stay.
  includes(player, 'if ((!rtcOk || !decodable) && hls)');
});

/* ----------------------------- item 15: Dashboard -------------------------- */
suite('item 15 — the Command Center keeps ticking');

const dashboard = readSource('trinetra-ai/src/pages/Dashboard.tsx');

test('events and KPIs are polled, not fetched once per page load', () => {
  includes(dashboard, 'recent.refresh();');
  includes(dashboard, 'kpis.refresh();');
  includes(dashboard, 'window.setInterval(() => {');
  includes(dashboard, '}, KPI_REFRESH_MS);');
  includes(dashboard, '}, [recent.refresh, kpis.refresh]);');
});

test('every interval is cleaned up', () => {
  const intervals = (dashboard.match(/window\.setInterval/g) ?? []).length;
  const cleanups = (dashboard.match(/window\.clearInterval/g) ?? []).length;
  ok(intervals >= 2, `expected the polling + clock intervals, found ${intervals}`);
  ok(cleanups === intervals, `${intervals} intervals but ${cleanups} cleanups`);
  includes(dashboard, 'const [now, setNow] = useState(() => Date.now());');
  includes(dashboard, 'window.setInterval(() => setNow(Date.now()), CLOCK_TICK_MS)');
});

test('useAsync exposes a stable refresh callback', () => {
  const useAsync = readSource('trinetra-ai/src/hooks/useAsync.ts');
  includes(useAsync, 'refresh');
  includes(useAsync, 'useCallback');
  // The hook reports errors as `string | null` — callers read `.error` directly.
  includes(useAsync, 'error');
});

/* ---------------------- item 3 / 17B: alert API paths ---------------------- */
suite('item 3/17B — alert endpoints are built from normalized ids');

const alertService = readSource('trinetra-ai/src/services/alertService.ts');

test('ack and resolve interpolate the id safely', () => {
  includes(alertService, '`/alerts/${encodeURIComponent(id)}/ack`');
  includes(alertService, '`/alerts/${encodeURIComponent(id)}/resolve`');
  excludes(alertService, '/alerts/NaN');
});

test('the operator and the note travel as separate fields', () => {
  includes(alertService, 'operator: by,');
  includes(alertService, 'note,');
  excludes(alertService, '`resolve: ${', 'the note must not be packed into the operator field');
  includes(alertService, 'resolve(id: string, note?: string, by?: string)');
});

/* ------------------------- item 16: stray lockfile ------------------------- */
suite('item 16 — the stray root package-lock.json is gone');

test('no root package-lock.json / package.json pair', () => {
  notOk(fs.existsSync(path.join(REPO_ROOT, 'package-lock.json')), 'root package-lock.json reappeared (name: zip-2, empty packages)');
  notOk(fs.existsSync(path.join(REPO_ROOT, 'package.json')), 'the root is not a node package');
  ok(fs.existsSync(path.join(FRONTEND_ROOT, 'package-lock.json')), 'the frontend lockfile must stay');
});

/* -------------------------- item 23: env var naming ------------------------ */
suite('item 23 — BACKEND_ORIGIN is the documented variable name');

test('READMEs document BACKEND_ORIGIN, not VITE_BACKEND_ORIGIN', () => {
  for (const rel of ['README.md', 'trinetra-ai/README.md']) {
    const doc = readSource(rel);
    includes(doc, 'BACKEND_ORIGIN', `${rel} no longer documents BACKEND_ORIGIN`);
    // The root README mentions the wrong name once, on purpose, to warn that it
    // is not read by anything. What must never come back is an instruction to
    // actually set it.
    notOk(/VITE_BACKEND_ORIGIN\s*=/.test(doc), `${rel} instructs the reader to set VITE_BACKEND_ORIGIN`);
    notOk(/export\s+VITE_BACKEND_ORIGIN/.test(doc), `${rel} exports the non-existent VITE_ variable`);
  }
  includes(readSource('README.md'), '`VITE_BACKEND_ORIGIN` is not read by', 'keep the warning about the trap');
  excludes(readSource('trinetra-ai/README.md'), 'VITE_BACKEND_ORIGIN', 'the frontend README must only use BACKEND_ORIGIN');
  const setup = readSource('trinetra-ai/scripts/auto-setup-env.mjs');
  includes(setup, "'BACKEND_ORIGIN'");
  excludes(setup, 'VITE_BACKEND_ORIGIN');
});

test('the docs no longer reference the removed defaults object', () => {
  for (const rel of ['AUTO_LIVE_SETUP.md', 'FOUR_APIS_USAGE.md']) {
    excludes(readSource(rel), 'HACKATHON_DEFAULTS', `${rel} still documents HACKATHON_DEFAULTS`);
  }
});

/* ------------------- cross-cutting: live plumbing preserved ---------------- */
suite('guardrails — the fixes did not remove live streaming plumbing');

test('the camera transports and realtime channels are all still wired', () => {
  const services = ['cameraService.ts', 'realtimeService.ts', 'whepClient.ts'];
  for (const file of services) {
    ok(fs.existsSync(path.join(FRONTEND_ROOT, 'src/services', file)), `${file} disappeared`);
  }
  for (const hook of ['useHlsStream.ts', 'useWhepStream.ts', 'useLiveEvents.ts', 'useCameras.ts']) {
    ok(fs.existsSync(path.join(FRONTEND_ROOT, 'src/hooks', hook)), `${hook} disappeared`);
  }
  const realtime = readSource('trinetra-ai/src/services/realtimeService.ts');
  includes(realtime, 'EventSource', 'the SSE realtime channel must stay');
  includes(realtime, 'asCameraStatus', 'realtime camera frames go through the shared status mapper');
  const vite = readSource('trinetra-ai/vite.config.ts');
  includes(vite, "'/sentinel'", 'the Sentinel proxy must stay');
  includes(vite, "'/api'", 'the backend proxy must stay');
  includes(vite, "'/cvfeed'", 'the MJPEG detection proxy must stay');
});

test('frontend tests are runnable with plain node', () => {
  const pkg = JSON.parse(readSource('trinetra-ai/package.json'));
  ok(pkg.scripts.test, 'package.json needs a "test" script');
  includes(pkg.scripts.test, 'tests/run-tests.mjs');
  ok(pkg.scripts.predev.includes('auto-setup-env.mjs'), 'predev must still auto-create env files');
  includes(pkg.scripts.build, 'tsc -b', 'the build must typecheck project references');
});
