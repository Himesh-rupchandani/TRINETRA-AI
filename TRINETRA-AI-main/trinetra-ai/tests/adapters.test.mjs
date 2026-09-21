/**
 * Frontend regression tests — items 3, 8, 9, 13 (+ the frontend half of 17B).
 *
 * Item 3  — realtime frames carry display ids such as "AL-7". `Number('AL-7')`
 *           produced `NaN`, which the UI echoed into `/api/alerts/NaN/resolve`
 *           (422/404) and rendered as a literal "NaN" badge.
 * Item 8  — `prettyPlate` split ANY digit run, so the non-canonical
 *           "GJ011234" was rendered as the misleading "GJ 01 1234".
 * Item 9  — the UI plate pattern must stay byte-identical to the two Python
 *           layers, or a plate the UI refuses is already stored by the engine.
 * Item 13 — `NOT_CONFIGURED` is a distinct backend state; collapsing it into
 *           OFFLINE turned registry slots into red faults.
 * Item 17B — the officer's resolution note travels in `resolution_note`, not
 *           packed into `resolved_by`.
 */
import path from 'node:path';
import { FRONTEND_ROOT, deepEq, eq, excludes, includes, loadTs, matches, notOk, ok, readSource, suite, test } from './harness.mjs';

const STUBS = {
  // adapters.ts only calls `get` at runtime inside cameraDirectory(); the tests
  // never hit the network.
  './api': {
    backendUrl: (path) => path,
    apiAssetUrl: (path) => /^https?:\/\//.test(path) ? path : `/api${path}`,
    get: async () => {
      throw new Error('network access is disabled in frontend tests');
    },
    post: async () => {
      throw new Error('network access is disabled in frontend tests');
    },
  },
};

const { toId, toAlert, toCamera, asCameraStatus, toVehicleEvent } = loadTs('src/services/adapters.ts', STUBS);
const { prettyPlate, isValidPlate, normalisePlate, INDIAN_PLATE_PATTERN } = loadTs('src/lib/utils.ts');

/* ------------------------------- item 3: toId ------------------------------ */
suite('item 3 — alert/event ids never become NaN');

test('numeric ids round-trip as strings', () => {
  eq(toId(42), '42');
  eq(toId(0), '0');
  eq(toId(-7), '-7');
});

test('display refs contribute their numeric part', () => {
  eq(toId('AL-7'), '7');
  eq(toId('EVT-104'), '104');
  eq(toId('AL-12 '), '12');
  excludes(toId('AL-7'), 'NaN');
});

test('already-string ids pass through untouched', () => {
  eq(toId('7'), '7');
  eq(toId('  12 '), '12');
  eq(toId('CAM-2A'), 'CAM-2A', 'an id with no trailing digits stays usable as a key');
});

test('missing / non-finite ids become an empty string, never "NaN"', () => {
  eq(toId(null), '');
  eq(toId(undefined), '');
  eq(toId(Number.NaN), '');
  eq(toId(Number.POSITIVE_INFINITY), '');
  eq(toId(''), '');
  for (const value of [null, undefined, Number.NaN, 'AL-7', 42, 'weird']) {
    excludes(toId(value), 'NaN');
  }
});

test('mapped alerts expose an id safe for a URL path', () => {
  const alert = toAlert({
    id: 'AL-9',
    event_id: 12,
    camera_id: 'CAM01',
    alert_type: 'WATCHLIST_MATCH',
    severity: 'critical',
    message: 'Vehicle on watchlist',
    status: 'RESOLVED',
    timestamp: '2026-09-12T10:00:00Z',
  });
  eq(alert.id, '9');
  eq(alert.eventId, '12');
  ok(/^[0-9]+$/.test(alert.id), 'the id sent to /alerts/{id}/resolve must be numeric');
});

test('realtime frames with string ids map to real events', () => {
  const event = toVehicleEvent({
    id: 'EVT-31',
    camera_id: 'CAM02',
    plate_number: 'GJ01AB1234',
    plate_confidence: 0.91,
    vehicle_class: 'car',
    event_time: '2026-09-12T10:05:00Z',
  });
  eq(event.id, '31');
  excludes(event.id, 'NaN');
  eq(event.plate, 'GJ01AB1234');
});

/* -------------------------- item 17B: resolution note ---------------------- */
suite('item 17B — resolution note stays out of resolved_by');

test('resolution_note is preferred over the raw message', () => {
  const alert = toAlert({
    id: 5,
    camera_id: 'CAM01',
    alert_type: 'WATCHLIST_MATCH',
    severity: 'HIGH',
    message: 'Vehicle on watchlist',
    status: 'RESOLVED',
    timestamp: '2026-09-12T10:00:00Z',
    resolved_by: 'Officer Rao',
    resolution_note: 'Driver verified and released',
  });
  eq(alert.note, 'Driver verified and released');
  eq(alert.acknowledgedBy, 'Officer Rao');
  excludes(alert.note, 'resolve:');
});

test('an unresolved alert still shows its message', () => {
  const alert = toAlert({
    id: 6,
    camera_id: 'CAM01',
    alert_type: 'SPEED',
    severity: 'MEDIUM',
    message: 'Overspeeding near SG Highway',
    status: 'NEW',
    timestamp: '2026-09-12T10:00:00Z',
  });
  eq(alert.note, 'Overspeeding near SG Highway');
  eq(alert.status, 'NEW');
  eq(alert.acknowledgedBy, undefined);
});

/* ------------------------- item 13: camera state mapping ------------------- */
suite('item 13 — camera states are not collapsed');

test('every backend state maps to its own UI state', () => {
  eq(asCameraStatus('ONLINE'), 'ONLINE');
  eq(asCameraStatus('DEGRADED'), 'DEGRADED');
  eq(asCameraStatus('NOT_CONFIGURED'), 'NOT_CONFIGURED');
  eq(asCameraStatus('NOT CONFIGURED'), 'NOT_CONFIGURED');
  eq(asCameraStatus('UNCONFIGURED'), 'NOT_CONFIGURED');
  eq(asCameraStatus('OFFLINE'), 'OFFLINE');
});

test('mapping is case/whitespace tolerant', () => {
  eq(asCameraStatus(' online '), 'ONLINE');
  eq(asCameraStatus('not_configured'), 'NOT_CONFIGURED');
  eq(asCameraStatus('degraded'), 'DEGRADED');
});

test('unknown or missing states fall back to OFFLINE (never invented)', () => {
  eq(asCameraStatus(undefined), 'OFFLINE');
  eq(asCameraStatus(''), 'OFFLINE');
  eq(asCameraStatus('CONNECTING'), 'OFFLINE');
  eq(asCameraStatus('WHATEVER'), 'OFFLINE');
});

test('a NOT_CONFIGURED camera keeps its state through toCamera', () => {
  const camera = toCamera({
    camera_id: 'CAM09',
    name: 'Registry slot 9',
    status: 'NOT_CONFIGURED',
    latitude: 0,
    longitude: 0,
  });
  eq(camera.status, 'NOT_CONFIGURED');
  eq(camera.id, 'cam09');
  eq(camera.latitude, 0, 'a real 0.0 coordinate must not be replaced');
  eq(camera.longitude, 0);
});

test('an ONLINE camera stays ONLINE — auto-request behaviour is untouched', () => {
  const camera = toCamera({ camera_id: 'CAM01', name: 'SG Highway', status: 'ONLINE', latitude: 23.03, longitude: 72.58 });
  eq(camera.status, 'ONLINE');
  const player = readSource('trinetra-ai/src/components/camera/CameraPlayer.tsx');
  includes(player, "if (autoRequest && camera.status !== 'OFFLINE') void requestStream();", 'automatic camera access must remain enabled');
  includes(player, 'autoRequest', 'the autoRequest prop is still honoured');
});

/* ------------------------ items 8 + 9: plate formatting -------------------- */
suite('items 8/9 — plate normalisation, pretty printing and validation');

test('normalisePlate strips separators and uppercases', () => {
  eq(normalisePlate('gj 01 ab-1234'), 'GJ01AB1234');
  eq(normalisePlate('GJ.01.AB.1234'), 'GJ01AB1234');
  eq(normalisePlate(''), '');
});

test('prettyPlate splits only canonical plates into 4 groups', () => {
  eq(prettyPlate('GJ01AB1234'), 'GJ 01 AB 1234');
  eq(prettyPlate('gj-01-ab-1234'), 'GJ 01 AB 1234');
  eq(prettyPlate('KA05XYZ999'), 'KA 05 XYZ 999');
  eq(prettyPlate('GJ1A234'), 'GJ 01 A 234', 'legacy single-digit RTO pads to two');
  matches(prettyPlate('GJ01AB1234'), /^[A-Z]{2} \d{2} [A-Z]{1,3} \d{3,4}$/);
});

test('prettyPlate never half-splits a non-canonical plate', () => {
  eq(prettyPlate('GJ011234'), 'GJ011234', 'no series letters => shown normalized, not "GJ 01 1234"');
  eq(prettyPlate('GJ1A2'), 'GJ1A2');
  eq(prettyPlate('RANDOMTEXT'), 'RANDOMTEXT');
  eq(prettyPlate(''), '');
});

test('isValidPlate accepts exactly the canonical grammar', () => {
  for (const plate of ['GJ01AB1234', 'GJ 01 AB 1234', 'GJ-01-AB-1234', 'gj01ab1234', 'GJ1AB1234', 'KA05XYZ999', 'GJ01AB123']) {
    ok(isValidPlate(plate), `${plate} should be valid`);
  }
  for (const plate of ['GJ011234', 'GJ1A2', 'GJ01ABCD1234', 'GJ01AB12345', 'ABC12DE3456', 'GJAB1234', '12345', '']) {
    notOk(isValidPlate(plate), `${plate} should be rejected`);
  }
});

test('the UI pattern is byte-identical to both Python layers', () => {
  eq(INDIAN_PLATE_PATTERN, '^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{3,4}$');

  const backend = readSource('TRINETRAAI/backend/app/utils/plate_normalizer.py');
  const cv = readSource('cv-engine/anpr/normalizer.py');
  const pattern = /CANONICAL_PLATE_PATTERN\s*=\s*r?["']([^"']+)["']/;

  const backendMatch = pattern.exec(backend);
  const cvMatch = pattern.exec(cv);
  ok(backendMatch, 'backend CANONICAL_PLATE_PATTERN not found');
  ok(cvMatch, 'cv-engine CANONICAL_PLATE_PATTERN not found');
  eq(backendMatch[1], INDIAN_PLATE_PATTERN, 'backend pattern drifted from the UI');
  eq(cvMatch[1], INDIAN_PLATE_PATTERN, 'cv-engine pattern drifted from the UI');
});

test('the UI and the backend agree plate-by-plate on the shared samples', () => {
  // Same samples as backend tests/test_plate_format_consistency.py.
  const canonical = ['GJ01AB1234', 'GJ 01 AB-1234', 'mh-02 cd 5678', 'DL08EF9012', 'KA05XYZ999', 'GJ1AB1234', 'UP32BX7589'];
  const rejected = ['GJ011234', 'GJ1A2', 'GJ01ABCD1234', 'ABC', '1234567890', 'GJ01AB12345'];
  for (const plate of canonical) ok(isValidPlate(plate), `${plate} is canonical`);
  for (const plate of rejected) notOk(isValidPlate(plate), `${plate} must be rejected`);

  // And the pretty printer is stable: pretty(pretty(x)) === pretty(x).
  for (const plate of canonical) eq(prettyPlate(prettyPlate(plate)), prettyPlate(plate), plate);
});

/* --------------------------- camera/alert DTO shapes ----------------------- */
suite('adapter output shape stays stable for the components');

test('toAlert fills the fields the alert cards read', () => {
  const alert = toAlert({
    id: 11,
    event_id: null,
    camera_id: 'CAM03',
    plate_number: 'GJ01AB1234',
    alert_type: 'SPEED_VIOLATION',
    severity: 'weird-value',
    message: 'Overspeed',
    status: 'acknowledged',
    confidence: 0.874,
    timestamp: '2026-09-12T11:00:00Z',
    acknowledged_by: 'Officer Mehta',
  });
  deepEq(
    {
      id: alert.id,
      eventId: alert.eventId,
      plate: alert.plate,
      cameraId: alert.cameraId,
      severity: alert.severity,
      status: alert.status,
      confidence: alert.confidence,
      category: alert.category,
      createdAt: alert.createdAt,
      acknowledgedBy: alert.acknowledgedBy,
    },
    {
      id: '11',
      eventId: '',
      plate: 'GJ01AB1234',
      cameraId: 'cam03',
      severity: 'INFO',
      status: 'ACKNOWLEDGED',
      confidence: 87.4,
      category: 'SPEED_VIOLATION',
      createdAt: '2026-09-12T11:00:00Z',
      acknowledgedBy: 'Officer Mehta',
    },
  );
});

test('harness resolves the frontend source tree from the repo root', () => {
  ok(FRONTEND_ROOT.endsWith('trinetra-ai'));
  ok(readSource(path.join('trinetra-ai/src/services/adapters.ts')).includes('export function toId'));
});
