/**
 * LIVE contract verification — frontend adapters vs a running backend.
 *
 * Runs the SAME adapter code the app ships (`src/services/adapters.ts`) against
 * real HTTP responses, then asserts the invariants the control room depends on.
 * This is the guard for the class of bug where the UI silently renders
 * `undefined` because the API shape drifted.
 *
 *   BACKEND=http://127.0.0.1:8000 npm run verify:live
 */
import {
  cameraDirectory,
  toAlert,
  toCamera,
  toKpis,
  toSystemSummary,
  toVehicleEvent,
  toVehicleProfile,
  toVehicleRoute,
  toWatchlistRecord,
  unwrapItems,
  type AlertDto,
  type CameraItemDto,
  type HealthDto,
  type KpiDto,
  type ProfileDto,
  type RouteDto,
  type VehicleEventDto,
  type WatchlistDto,
} from '@/services/adapters';
import { mapBackendMessages } from '@/services/realtimeService';
import { realCrops } from '@/utils/evidence';

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

const section = (title: string) => console.log(`\n${title}`);

async function main() {
  console.log(`TRINETRA live contract check against ${API}`);

  /* ----------------------------- cameras ----------------------------- */
  section('Camera registry (Model 1)');
  // GET /cameras wraps its payload as { data: [...] } — the same unwrap
  // cameraService performs.
  const cameraPayload = (await fetchJson('/cameras')) as { data?: CameraItemDto[] } | CameraItemDto[];
  const rawCameras = Array.isArray(cameraPayload) ? cameraPayload : (cameraPayload.data ?? []);
  const cameras = rawCameras.map(toCamera);
  check('cameras returned', cameras.length > 0, `${cameras.length} cameras`);
  check('every camera has id/name/location/status', cameras.every((c) => c.id && c.name && c.location && c.status));
  check(
    'status is within the 3-state contract',
    cameras.every((c) => ['ONLINE', 'OFFLINE', 'DEGRADED'].includes(c.status)),
    [...new Set(cameras.map((c) => c.status))].join('/'),
  );
  check(
    'coordinates present for GIS',
    cameras.every((c) => Number.isFinite(c.latitude) && Number.isFinite(c.longitude)),
  );
  check('no NaN in the camera payload', !hasNaN(cameras));

  const cam04 = cameras.find((c) => c.id === 'cam04');
  check('CAM04 exists', !!cam04);
  if (cam04) {
    check('CAM04 exposes department', !!cam04.department, `department=${cam04.department}`);
    check('CAM04 has a real location', cam04.location !== '—', cam04.location);

    // Single source of truth: list and detail must agree.
    const detail = toCamera((await fetchJson('/cameras/cam04')) as CameraItemDto);
    check(
      'GET /cameras/cam04 matches the list entry',
      detail.location === cam04.location &&
        detail.department === cam04.department &&
        detail.status === cam04.status,
      `${detail.name} @ ${detail.location}`,
    );
  }

  // The shared directory every screen resolves camera metadata through.
  const dir = await cameraDirectory();
  check('shared camera directory is populated', dir.size === cameras.length, `${dir.size} entries`);

  /* ------------------------------- KPIs ------------------------------ */
  section('Command Center KPIs');
  const kpis = toKpis((await fetchJson('/stats/kpis')) as KpiDto);
  check('totalCameras equals registry size', kpis.totalCameras === cameras.length, `${kpis.totalCameras}`);
  check(
    'online + degraded + offline reconciles',
    kpis.camerasOnline + kpis.camerasDegraded + kpis.camerasOffline === kpis.totalCameras,
  );
  check('no NaN in KPIs', !hasNaN(kpis));
  check('24h detections are non-zero (demo timeline is recent)', kpis.vehicleDetections24h > 0, `${kpis.vehicleDetections24h}`);

  /* --------------------------- vehicle trace ------------------------- */
  section(`Vehicle trace — ${DEMO_PLATE}`);
  const profile = toVehicleProfile((await fetchJson(`/vehicles/${DEMO_PLATE}`)) as ProfileDto);
  check('profile plate normalised', profile.plate === DEMO_PLATE, profile.plate);
  check('profile carries the watchlist record', profile.watchlist !== null, profile.watchlist?.category ?? 'none');
  check('profile sighting count > 0', profile.totalSightings > 0, `${profile.totalSightings}`);
  check('profile camerasTouched mapped', (profile.camerasTouched ?? 0) > 0, `${profile.camerasTouched}`);

  const rawEvents = unwrapItems(
    (await fetchJson(`/vehicles/${DEMO_PLATE}/events?size=100`)) as never,
  ) as VehicleEventDto[];
  const events = rawEvents.map((e) => toVehicleEvent(e, dir));
  check('sightings returned', events.length > 0, `${events.length} sightings`);
  check(
    'sightings are chronological',
    events.every((e, i) => i === 0 || new Date(events[i - 1].timestamp) <= new Date(e.timestamp)),
  );
  check(
    'every sighting has plate + confidence + camera',
    events.every((e) => e.plate && e.cameraId && Number.isFinite(e.plateConfidence)),
  );
  check('no NaN in events', !hasNaN(events));

  const route = toVehicleRoute((await fetchJson(`/vehicles/${DEMO_PLATE}/route`)) as RouteDto, dir);
  const seq = route.points.map((p) => p.cameraId).join(' -> ');
  check('route has points', route.points.length > 0, seq || 'none');
  // The canonical trace must appear in order — not be the only trace, since a
  // freshly ingested sighting is legitimately part of the same journey.
  const EXPECTED = ['cam04', 'cam08', 'cam12', 'cam17'];
  let cursor = 0;
  for (const cam of route.points.map((p) => p.cameraId.toLowerCase())) {
    if (cursor < EXPECTED.length && cam === EXPECTED[cursor]) cursor += 1;
  }
  check('route contains the cross-camera trace in chronological order', cursor === EXPECTED.length, seq);
  check(
    'route points carry a location',
    route.points.every((p) => !!p.location),
    route.points.map((p) => p.location).join(', '),
  );
  check('no NaN in route', !hasNaN(route));

  /* ----------------------------- alerts ------------------------------ */
  section('Alerts');
  const rawAlerts = unwrapItems((await fetchJson('/alerts?size=100')) as never) as AlertDto[];
  const alerts = rawAlerts.map((a) => toAlert(a, dir));
  check('alerts returned', alerts.length > 0, `${alerts.length} alerts`);
  check(
    'alert status within lifecycle',
    alerts.every((a) => ['NEW', 'ACKNOWLEDGED', 'RESOLVED'].includes(a.status)),
    [...new Set(alerts.map((a) => a.status))].join('/'),
  );
  check('alert severity valid', alerts.every((a) => ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'].includes(a.severity)));
  check('alerts resolve a location from the registry', alerts.every((a) => !!a.location), alerts[0]?.location ?? 'none');
  check('no NaN in alerts', !hasNaN(alerts));

  /* ---------------------------- watchlist ---------------------------- */
  section('Watchlist');
  const rawWatchlist = unwrapItems((await fetchJson('/watchlist?size=100')) as never) as WatchlistDto[];
  const watchlist = rawWatchlist.map(toWatchlistRecord);
  check('watchlist returned', watchlist.length > 0, `${watchlist.length} records`);
  const demo = watchlist.find((w) => w.plate === DEMO_PLATE);
  check(`${DEMO_PLATE} is on the watchlist`, !!demo);
  check('demo plate is a stolen vehicle', demo?.category === 'STOLEN VEHICLE', demo?.category ?? 'missing');
  check('demo plate is high priority', demo?.severity === 'CRITICAL' || demo?.severity === 'HIGH', demo?.severity ?? 'missing');

  /* ------------------------------ health ----------------------------- */
  section('System health');
  const health = toSystemSummary((await fetchJson('/health')) as HealthDto);
  check('health reports services', health.services.length > 0, `${health.services.length} services`);
  check(
    'service statuses valid',
    health.services.every((s) => ['HEALTHY', 'DEGRADED', 'OFFLINE'].includes(s.status)),
    health.services.map((s) => s.status).join('/'),
  );
  check('no NaN in health', !hasNaN(health));

  /* ----------------------------- realtime ---------------------------- */
  section('Realtime channel');
  for (const [label, path] of [
    ['SSE /api/stream', '/stream'],
    ['WebSocket /api/ws/events', '/ws/events'],
  ] as const) {
    if (path === '/stream') {
      const res = await fetch(`${API}${path}`, { headers: { Accept: 'text/event-stream' } });
      const type = res.headers.get('content-type') ?? '';
      check('SSE channel is served as text/event-stream', res.ok && type.includes('text/event-stream'), `HTTP ${res.status} ${type}`);
      // Do not hold the stream open.
      await res.body?.cancel();
    } else {
      const opened = await new Promise<boolean>((resolve) => {
        const ws = new WebSocket(`${API.replace(/^http/, 'ws')}${path}`);
        const t = setTimeout(() => { ws.close(); resolve(false); }, 5000);
        ws.onopen = () => { clearTimeout(t); ws.close(); resolve(true); };
        ws.onerror = () => { clearTimeout(t); resolve(false); };
      });
      check('WebSocket channel accepts a handshake', opened, label);
    }
  }

  // End-to-end: a fresh watchlist plate ingested over HTTP must be broadcast.
  // A new plate avoids alert deduplication, which would (correctly) suppress a
  // second alert for one that already raised one, keeping this repeatable.
  const probePlate = `GJ99ZZ${String(Date.now()).slice(-4)}`;
  const frames: Array<{ type?: string; payload?: Record<string, unknown> }> = [];
  const ws = new WebSocket(`${API.replace(/^http/, 'ws')}/ws/events`);
  const opened = await new Promise<boolean>((resolve) => {
    const t = setTimeout(() => resolve(false), 5000);
    ws.onopen = () => { clearTimeout(t); resolve(true); };
    ws.onerror = () => { clearTimeout(t); resolve(false); };
  });
  check('WebSocket connects for broadcast capture', opened);

  if (opened) {
    ws.onmessage = (e) => frames.push(JSON.parse(String(e.data)));
    await fetch(`${API}/watchlist`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plate_number: probePlate, category: 'stolen vehicle', description: 'Contract probe', active: true }),
    });
    await fetch(`${API}/events`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        camera_id: 'CAM08',
        vehicle_id: 900,
        plate_raw: probePlate,
        plate: probePlate,
        plate_confidence: 0.95,
        event_time: new Date().toISOString(),
        vehicle_class: 'car',
        evidence_ref: 'verify/realtime.jpg',
      }),
    });
    await new Promise((r) => setTimeout(r, 1500));

    const created = frames.find((f) => f.type === 'ALERT_CREATED');
    check('watchlist hit broadcast as ALERT_CREATED', !!created, frames.map((f) => f.type).join('/'));
    if (created?.payload) {
      const p = created.payload;
      check('broadcast carries the probe plate', String(p.plate_number ?? p.plate) === probePlate, String(p.plate_number ?? p.plate));
      check('broadcast carries camera + severity', !!p.camera_id && !!p.severity, `${p.camera_id} ${p.severity}`);
      // The UI derives both a sighting and an alert from this one frame, so it
      // must carry the event fields as well as the alert fields.
      check('broadcast carries event fields for the live feed', p.event_id != null && p.confidence != null, `event_id=${p.event_id}`);
      // The crop handle is what lets the live evidence panel show the image the
      // CV engine captured — a realtime frame without it has no real imagery.
      check('broadcast carries the crop reference', p.evidence_ref === 'verify/realtime.jpg', String(p.evidence_ref ?? 'missing'));

      // Run the shipped realtime mapper over the real wire frame: the event it
      // hands the UI must resolve to a real captured crop, not a stand-in.
      const mapped = mapBackendMessages(created).find((m) => m.type === 'EVENT');
      const crop = mapped?.type === 'EVENT' ? realCrops(mapped.payload.evidence) : null;
      check('live event maps to a real crop URL', !!crop?.frameUrl?.endsWith('verify/realtime.jpg'), crop?.frameUrl ?? 'none');
      check('live event is not flagged synthetic', mapped?.type === 'EVENT' ? mapped.payload.evidence?.synthetic !== true : false);
    }
    ws.close();
  }

  /* ------------------------------ result ----------------------------- */
  console.log(`\n${failures === 0 ? 'PASS' : 'FAIL'} — ${checks - failures}/${checks} checks passed`);
  process.exit(failures === 0 ? 0 : 1);
}

main().catch((err) => {
  console.error(`\nBLOCKED — ${err instanceof Error ? err.message : String(err)}`);
  process.exit(2);
});
