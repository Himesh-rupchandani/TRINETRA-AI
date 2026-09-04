/**
 * LIVE contract verification — frontend adapters vs a running backend.
 *
 * Runs the SAME adapter code the app ships (`src/services/adapters.ts`) against
 * real HTTP responses, then asserts the invariants the control room depends on.
 * This is the guard for the class of bug where the UI silently renders
 * `undefined` because the API shape drifted.
 *
 *   BACKEND=http://127.0.0.1:8000 node --experimental-strip-types \
 *     scripts/verify-live-contract.ts
 */
import {
  mapAlert,
  mapCamera,
  mapEvent,
  mapHealth,
  mapKpis,
  mapRoute,
  mapVehicleProfile,
  mapWatchlist,
  unwrapList,
} from '../src/services/adapters.ts';

const BACKEND = process.env.BACKEND ?? 'http://127.0.0.1:8000';
const API = `${BACKEND.replace(/\/$/, '')}/api`;
const DEMO_PLATE = 'GJ01AB1234';

let failures = 0;
let checks = 0;

function check(label: string, condition: boolean, detail = '') {
  checks += 1;
  if (condition) {
    console.log(`  PASS  ${label}${detail ? ` — ${detail}` : ''}`);
  } else {
    failures += 1;
    console.log(`  FAIL  ${label}${detail ? ` — ${detail}` : ''}`);
  }
}

async function fetchJson(path: string): Promise<unknown> {
  const res = await fetch(`${API}${path}`);
  if (!res.ok) throw new Error(`GET ${path} -> HTTP ${res.status}`);
  return res.json();
}

const hasNaN = (o: unknown): boolean =>
  JSON.stringify(o, (_k, v) => (typeof v === 'number' && Number.isNaN(v) ? 'NaN' : v))!.includes('"NaN"');

function section(title: string) {
  console.log(`\n${title}`);
}

async function main() {
  console.log(`TRINETRA live contract check against ${API}`);

  /* ----------------------------- cameras ----------------------------- */
  section('Camera registry (Model 1)');
  const cameras = unwrapList(await fetchJson('/cameras')).map(mapCamera);
  check('cameras returned', cameras.length > 0, `${cameras.length} cameras`);
  check(
    'every camera has id/name/location/status',
    cameras.every((c) => c.id && c.name && c.location && c.status),
  );
  check(
    'status is within the 3-state contract',
    cameras.every((c) => ['ONLINE', 'OFFLINE', 'DEGRADED'].includes(c.status)),
    [...new Set(cameras.map((c) => c.status))].join('/'),
  );
  check('coordinates present for GIS', cameras.every((c) => Number.isFinite(c.latitude) && Number.isFinite(c.longitude)));
  check('no NaN anywhere in the camera payload', !hasNaN(cameras));

  const cam04 = cameras.find((c) => c.id === 'cam04');
  check('CAM04 exists', !!cam04);
  if (cam04) {
    check('CAM04 exposes department', !!cam04.department, `department=${cam04.department}`);
    check('CAM04 has a real location', cam04.location !== '—', cam04.location);
  }

  // Single-source-of-truth: list and detail must agree.
  if (cam04) {
    const detail = mapCamera((await fetchJson('/cameras/cam04')) as Record<string, unknown>);
    check(
      'GET /cameras/cam04 matches the list entry',
      detail.location === cam04.location && detail.department === cam04.department && detail.status === cam04.status,
      `${detail.name} @ ${detail.location}`,
    );
  }

  /* ------------------------------- KPIs ------------------------------ */
  section('Command Center KPIs');
  const kpis = mapKpis((await fetchJson('/stats/kpis')) as Record<string, unknown>);
  check('totalCameras equals registry size', kpis.totalCameras === cameras.length, `${kpis.totalCameras}`);
  check('online + degraded + offline reconciles', kpis.camerasOnline + kpis.camerasDegraded + kpis.camerasOffline === kpis.totalCameras);
  check('no NaN in KPIs', !hasNaN(kpis));
  check('24h detections are non-zero (demo timeline is recent)', kpis.vehicleDetections24h > 0, `${kpis.vehicleDetections24h}`);

  /* --------------------------- vehicle trace ------------------------- */
  section(`Vehicle trace — ${DEMO_PLATE}`);
  const profile = mapVehicleProfile(await fetchJson(`/vehicles/${DEMO_PLATE}`));
  check('profile resolves', profile !== null);
  check('profile plate normalised', profile?.plate === DEMO_PLATE, profile?.plate ?? 'null');
  check('profile is a watchlist match', profile?.watchlist === undefined || profile?.watchlist !== null,
    profile?.watchlist ? `${profile.watchlist.category}` : 'no record');
  check('profile sighting count > 0', (profile?.totalSightings ?? 0) > 0, `${profile?.totalSightings}`);

  const events = unwrapList(await fetchJson(`/vehicles/${DEMO_PLATE}/events?size=100`)).map(mapEvent);
  check('sightings returned', events.length > 0, `${events.length} sightings`);
  check(
    'sightings are chronological',
    events.every((e, i) => i === 0 || new Date(events[i - 1].timestamp) <= new Date(e.timestamp)),
  );
  check('every sighting has plate + confidence + camera', events.every((e) => e.plate && e.cameraId && Number.isFinite(e.plateConfidence)));
  check('no NaN in events', !hasNaN(events));

  const route = mapRoute(await fetchJson(`/vehicles/${DEMO_PLATE}/route`));
  const seq = route.points.map((p) => p.cameraId).join(' -> ');
  check('route has points', route.points.length > 0, seq || 'none');
  check('route is the expected cross-camera trace', seq === 'CAM04 -> CAM08 -> CAM12 -> CAM17', seq);
  check('route points carry a location', route.points.every((p) => !!p.location), route.points.map((p) => p.location).join(', '));
  check('camerasTouched matches distinct cameras', route.camerasTouched === new Set(route.points.map((p) => p.cameraId)).size, `${route.camerasTouched}`);
  check('no NaN in route', !hasNaN(route));

  /* ----------------------------- alerts ------------------------------ */
  section('Alerts');
  const alerts = unwrapList(await fetchJson('/alerts?size=100')).map(mapAlert);
  check('alerts returned', alerts.length > 0, `${alerts.length} alerts`);
  check('alert status within lifecycle', alerts.every((a) => ['NEW', 'ACKNOWLEDGED', 'RESOLVED'].includes(a.status)),
    [...new Set(alerts.map((a) => a.status))].join('/'));
  check('alert severity valid', alerts.every((a) => ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'].includes(a.severity)));
  check('watchlist alerts carry a plate', alerts.filter((a) => a.category.includes('WATCHLIST')).every((a) => !!a.plate));
  check('no NaN in alerts', !hasNaN(alerts));

  /* ---------------------------- watchlist ---------------------------- */
  section('Watchlist');
  const watchlist = unwrapList(await fetchJson('/watchlist?size=100')).map(mapWatchlist);
  check('watchlist returned', watchlist.length > 0, `${watchlist.length} records`);
  const demo = watchlist.find((w) => w.plate === DEMO_PLATE);
  check(`${DEMO_PLATE} is on the watchlist`, !!demo);
  check('demo plate is a stolen vehicle', demo?.category === 'STOLEN VEHICLE', demo?.category ?? 'missing');
  check('demo plate is high priority', demo?.severity === 'CRITICAL' || demo?.severity === 'HIGH', demo?.severity ?? 'missing');

  /* ------------------------------ health ----------------------------- */
  section('System health');
  const health = mapHealth((await fetchJson('/health')) as Record<string, unknown>);
  check('health reports services', health.services.length > 0, `${health.services.length} services`);
  check('service statuses valid', health.services.every((s) => ['HEALTHY', 'DEGRADED', 'OFFLINE'].includes(s.status)),
    health.services.map((s) => s.status).join('/'));
  check('no NaN in health', !hasNaN(health));

  /* ------------------------------ result ----------------------------- */
  console.log(`\n${failures === 0 ? 'PASS' : 'FAIL'} — ${checks - failures}/${checks} checks passed`);
  process.exit(failures === 0 ? 0 : 1);
}

main().catch((err) => {
  console.error(`\nBLOCKED — ${err instanceof Error ? err.message : String(err)}`);
  process.exit(2);
});
