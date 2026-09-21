import { deepEq, eq, loadTs, suite, test } from './harness.mjs';

const { evidencePaths, latestCameraEvidence } = loadTs('src/lib/evidence.ts');
const config = { apiBaseUrl: '/api', useMocks: false };
const { apiAssetUrl } = loadTs('src/services/api.ts', {
  axios: { create: () => ({ interceptors: { request: { use() {} }, response: { use() {} } } }) },
  '@/lib/config': { config },
});

suite('Photo evidence — actual captured images and deployment-safe URLs');
test('relative references and already-prefixed API references resolve to the same photos', () => {
  const expected = { framePath: '/evidence/live/cam1/captured%20frame.jpg', platePath: '/evidence/live/cam1/captured%20frame_plate.jpg' };
  deepEq(evidencePaths('live/cam1/captured frame.jpg', true), expected);
  deepEq(evidencePaths('/api/evidence/live/cam1/captured frame.jpg', true), expected);
  deepEq(evidencePaths('/api/v1/evidence/live/cam1/captured frame.jpg', true), expected);
});
test('public image URLs are not percent-encoded into nonexistent local files', () => {
  const url = 'https://images.example.test/real-frame.jpg?signature=fixture';
  const paths = evidencePaths(url, true);
  eq(paths.framePath, url);
  eq(paths.platePath, undefined);
  eq(apiAssetUrl(paths.framePath), url);
});
test('images use the configured API origin and versioned prefix', () => {
  config.apiBaseUrl = 'https://api.example.test/api/v1/';
  eq(apiAssetUrl('/evidence/live/cam1/frame.jpg', config.apiBaseUrl), 'https://api.example.test/api/v1/evidence/live/cam1/frame.jpg');
  eq(apiAssetUrl('/cameras/cam1/anpr/photos/abc/1/vehicle.jpg', config.apiBaseUrl), 'https://api.example.test/api/v1/cameras/cam1/anpr/photos/abc/1/vehicle.jpg');
  config.apiBaseUrl = '/api';
});
test('missing, unsafe and credential-bearing references do not generate image requests', () => {
  for (const ref of ['', undefined, '../private.jpg', '/etc/private.jpg', 'live/../private.jpg', 'C:\\private.jpg', 'javascript:alert(1)', 'https://user:password@example.test/photo.jpg']) {
    eq(evidencePaths(ref, true), undefined);
  }
  eq(evidencePaths('uploads/cam1/file.jpg', true).platePath, undefined);
});
test('latest saved evidence is selected by camera and timestamp, not row order or a watchlist filter', () => {
  const event = (id, cameraId, timestamp, evidence = { frameUrl: '/actual.jpg' }) => ({ id, cameraId, timestamp, evidence });
  const older = event('1', 'cam1', '2026-09-20T08:00:00Z');
  const newest = event('2', 'CAM1', '2026-09-20T09:00:00Z');
  const missing = event('3', 'cam1', '2026-09-20T10:00:00Z', undefined);
  delete missing.evidence;
  const input = [older, event('4', 'cam2', '2026-09-20T11:00:00Z'), newest, missing];
  eq(latestCameraEvidence('cam1', input).id, '2');
  eq(latestCameraEvidence('unconfigured', input), null);
  deepEq(input.map(e => e.id), ['1', '4', '2', '3']);
});
