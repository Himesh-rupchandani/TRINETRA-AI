import { deepEq, eq, excludes, includes, loadTs, ok, readSource, suite, test } from './harness.mjs';

const { PlateNotificationGate, canDrawSnapshot, containedBox, mergeLiveEvent, anprStatusLabel, matchesSceneSignature } = loadTs('src/lib/liveDetections.ts');
const event = (id, cameraId = 'cam1', extra = {}) => ({ id, cameraId, plate: 'GJ01AB1234', plateConfidence: 94, plateStatus: 'HIGH', ...extra });

suite('live ANPR — notifications are real, deduplicated and camera-scoped');
test('three plates in one batch produce three notifications', () => {
  const gate = new PlateNotificationGate();
  eq([event('1'), event('2', 'cam1', { plate: 'GJ02CD5678' }), event('3', 'cam1', { plate: 'GJ03EF9012' })]
    .filter((e) => gate.accept(e, 1000)).length, 3);
});
test('replayed events and repeated readings do not spam', () => {
  const gate = new PlateNotificationGate();
  ok(gate.accept(event('1'), 0));
  eq(gate.accept(event('1'), 1000), false);
  eq(gate.accept(event('2', 'CAM1', { plate: 'gj 01-ab-1234' }), 2000), false);
  ok(gate.accept(event('3', 'cam2'), 2000), 'another camera is a new sighting');
  ok(gate.accept(event('4'), 63_000), 'a later revisit is allowed');
  eq(gate.accept(event('1'), 400_000), false, 'an old item still in the notification buffer must not re-toast');
});
test('unknown/simulated/invalid readings cannot be presented as real plate notifications', () => {
  const gate = new PlateNotificationGate();
  for (const [i, extra] of [
    { plate: '' }, { plateStatus: 'UNKNOWN' }, { plateStatus: 'SIMULATED' },
    { plateConfidence: 45 }, { plateConfidence: NaN }, { watchlistMatch: true },
  ].entries()) eq(gate.accept(event(String(i), 'cam1', extra)), false);
  ok(gate.accept(event('verified-low', 'cam1', { plateStatus: 'LOW_CONFIDENCE', plateConfidence: 70 })));
});
test('event merge keeps latest data, deduplicates IDs and bounds memory', () => {
  const merged = mergeLiveEvent([event('1'), event('2')], event('1', 'cam1', { plateConfidence: 96 }), 2);
  deepEq(merged.map((e) => e.id), ['1', '2']);
  eq(merged[0].plateConfidence, 96);
  eq(mergeLiveEvent(merged, event('3'), 2).length, 2);
});

suite('live ANPR — overlay geometry and expiry');
test('letterboxing is included in the box transform', () => {
  deepEq(containedBox([64, 36, 320, 180], 640, 360, 400, 400), [40, 110, 160, 90]);
});
test('stale boxes, another viewer and a seek never paint over the wrong frame', () => {
  const snap = { source_id: 'browser:a', frame_width: 640, frame_height: 360,
    result_age_ms: 1000, overlay_ttl_ms: 3000, media_time: 10 };
  ok(canDrawSnapshot(snap, 'browser:a', 11));
  eq(canDrawSnapshot(snap, 'browser:b', 11), false);
  eq(canDrawSnapshot(snap, 'browser:a', 9), false);
  eq(canDrawSnapshot(snap, 'browser:a', 14), false);
  eq(canDrawSnapshot({ ...snap, result_age_ms: 4000 }, 'browser:a', 11), false);
  eq(canDrawSnapshot({ ...snap, frame_width: 0 }, 'browser:a', 11), false);
});

let simulated = 0;
const realtime = loadTs('src/services/realtimeService.ts', {
  '@/lib/config': { config: { realtimeTransport: 'sse' } },
  './api': { isMockMode: false, realtimeUrl: (p) => `/api${p}` },
  '@/mocks/cameras': { mockCameras: [] },
  '@/mocks/mockBackend': { pushMockEvent: () => simulated++, setMockCameraStatus: () => {} },
  '@/mocks/scheduledAlerts': { buildScheduledAlertPair: () => { simulated++; throw new Error('Synthetic fallback used'); } },
  '@/utils/syntheticEvidence': { syntheticFrame: () => '', syntheticPlateCrop: () => '' },
});

suite('live ANPR — realtime wire and failure behaviour');
test('SSE plate reads retain confidence tier, evidence, track and recording offset', () => {
  const messages = realtime.mapBackendMessages({ type: 'VEHICLE_DETECTED', payload: {
    event_id: 21, camera_id: 'CAM1', vehicle_track_id: 3,
    plate_number: 'GJ01AB1234', plate_confidence: .73, plate_status: 'LOW_CONFIDENCE',
    evidence_ref: 'live/cam1/frame.jpg', event_time: '2026-09-20T10:00:00Z',
    video_file: 'recording.mp4', video_offset_sec: 12.5,
  } });
  eq(messages.length, 1);
  const e = messages[0].payload;
  eq(e.plateStatus, 'LOW_CONFIDENCE');
  eq(e.plateConfidence, 73);
  eq(e.vehicleId, 3);
  eq(e.evidence.frameUrl, '/api/evidence/live/cam1/frame.jpg');
  eq(e.videoOffsetSec, 12.5);
});
test('watchlist alert shares the persisted event instead of inventing another sighting', () => {
  const messages = realtime.mapBackendMessages({ type: 'ALERT_CREATED', payload: {
    event_id: 21, alert_id: 8, camera_id: 'CAM1', plate_number: 'GJ01AB1234',
    plate_confidence: .94, plate_status: 'HIGH', watchlist_match: true,
  } });
  deepEq(messages.map((m) => m.type), ['EVENT', 'ALERT']);
  eq(messages[0].payload.id, '21');
  eq(messages[1].payload.eventId, '21');
  eq(messages[1].payload.id, '8');
});
test('a failed SSE connection goes offline and retries — zero synthetic messages', () => {
  const previousWindow = globalThis.window;
  const previousSse = globalThis.EventSource;
  let source;
  const scheduled = [];
  const messages = [];
  const states = [];
  globalThis.window = {
    setTimeout: (fn) => { scheduled.push(fn); return scheduled.length; },
    clearTimeout: () => {},
    setInterval: () => { throw new Error('Real transport must not start a simulation timer'); },
  };
  globalThis.EventSource = class {
    constructor() { source = this; }
    close() {}
  };
  try {
    const channel = realtime.connectRealtime((m) => messages.push(m), (s) => states.push(s));
    source.onerror();
    deepEq(states, ['CONNECTING', 'OFFLINE']);
    eq(scheduled.length, 1);
    eq(messages.length, 0);
    eq(simulated, 0);
    channel.close();
  } finally {
    globalThis.window = previousWindow;
    globalThis.EventSource = previousSse;
  }
});

suite('live ANPR — lifecycle wiring');
test('native playback is independent of inference and sample requests are cleaned up', () => {
  const player = readSource('trinetra-ai/src/components/camera/CameraPlayer.tsx');
  const overlay = readSource('trinetra-ai/src/components/camera/DetectionOverlay.tsx');
  includes(player, 'const detectionActive = isMjpeg && aiBoxes');
  includes(player, '<DetectionOverlay');
  includes(overlay, 'controller.abort()');
  includes(overlay, 'clearTimeout(timer)');
  includes(overlay, 'document.hidden');
  includes(overlay, 'video.currentTime === lastMediaTime');
  excludes(overlay, 'setInterval(');
});
test('the camera history and Vehicle Log subscribe to quiet live refreshes', () => {
  includes(readSource('trinetra-ai/src/pages/CameraDetail.tsx'), 'useEventSearch({ cameraId }, 1, 30)');
  includes(readSource('trinetra-ai/src/hooks/useEvents.ts'), '[eventsSeen, connection]');
  includes(readSource('trinetra-ai/src/hooks/useEvents.ts'), 'runRef.current(true)');
  includes(readSource('trinetra-ai/src/layouts/MainLayout.tsx'), '<LivePlateToaster />');
});


suite('live ANPR — honest playback status');
test('a failed detection stream cannot be labelled healthy after falling back to raw video', () => {
  eq(anprStatusLabel({ status: 'SCANNING', max_vehicles: 3 }, null, true), 'ANPR UNAVAILABLE');
  eq(anprStatusLabel({ status: 'SCANNING', max_vehicles: 3 }, 'Network failure'), 'ANPR UNAVAILABLE');
  eq(anprStatusLabel({ status: 'UNAVAILABLE' }, null), 'ANPR UNAVAILABLE');
  eq(anprStatusLabel({ status: 'DISABLED' }, null), 'ANPR OFF');
});
test('active rechecks do not flicker the scanning badge; shared and busy queues are explicit', () => {
  for (const status of ['SCANNING', 'PROCESSING']) {
    eq(anprStatusLabel({ status, max_vehicles: 3 }, null), 'ANPR · UP TO 3');
  }
  eq(anprStatusLabel({ status: 'SHARED' }, null), 'ANPR · SHARED');
  eq(anprStatusLabel({ status: 'BUSY' }, null), 'ANPR · BUSY');
  const player = readSource('trinetra-ai/src/components/camera/CameraPlayer.tsx');
  includes(player, 'anprStatusLabel(anprStatus, anprError, detectionFailed)');
  includes(player, "(phase === 'LIVE' || (useImg && mjpegAlive && mjpegSignal))");
});


suite('live ANPR — scene cut protection');
test('recent metadata alone is not enough to draw numbers over a different picture', () => {
  const signature = Array(144).fill(130);
  const pixels = (grey) => new Uint8ClampedArray(Array.from({ length: 144 }, () => [grey, grey, grey, 255]).flat());
  ok(matchesSceneSignature(signature, pixels(135)), 'small lighting changes stay readable');
  eq(matchesSceneSignature(signature, pixels(35)), false, 'hard cut hides old labels');
  eq(matchesSceneSignature([1, 2], pixels(130)), false);
  eq(matchesSceneSignature(Array(144).fill(NaN), pixels(130)), false);
  const overlay = readSource('trinetra-ai/src/components/camera/DetectionOverlay.tsx');
  includes(overlay, 'clearTimeout(paintTimer)');
  includes(overlay, 'video.seeking');
});
