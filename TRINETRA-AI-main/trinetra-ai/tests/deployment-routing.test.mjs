import { eq, includes, loadTs, readSource, suite, test } from './harness.mjs';
const { apiUrl, backendRootUrl, sentinelHlsUrl } = loadTs('src/lib/backendUrls.ts');
const REMOTE = 'https://backend.example.test/api';

suite('Vercel + Render — every backend path uses one configured origin');
test('JSON/assets and backend-root tickets do not double the API prefix', () => {
  eq(apiUrl('/health', REMOTE), 'https://backend.example.test/api/health');
  eq(apiUrl('/evidence/live/cam1/frame.jpg', REMOTE), 'https://backend.example.test/api/evidence/live/cam1/frame.jpg');
  eq(backendRootUrl('/api/cameras/cam1/live/detect', REMOTE), 'https://backend.example.test/api/cameras/cam1/live/detect');
  eq(backendRootUrl('/sentinel/stream/cam1/whep', REMOTE), 'https://backend.example.test/sentinel/stream/cam1/whep');
  eq(backendRootUrl('/api/cameras/cam1/live', 'https://backend.example.test/proxy/api/v1'), 'https://backend.example.test/proxy/api/cameras/cam1/live');
});
test('same-origin deployments and empty/unplayable tickets remain unchanged', () => {
  eq(backendRootUrl('/api/cameras/cam1/live'), '/api/cameras/cam1/live');
  eq(backendRootUrl('/sentinel/stream/cam1/whep'), '/sentinel/stream/cam1/whep');
  eq(backendRootUrl('',REMOTE),'');
  eq(apiUrl('/health','/api/v1/'),'/api/v1/health');
  eq(backendRootUrl('https://cdn.example.test/stream.m3u8',REMOTE),'https://cdn.example.test/stream.m3u8');
});
test('credentials and non-browser schemes cannot be published as stream tickets', () => {
  for (const bad of ['rtsp://private/stream','javascript:alert(1)','//elsewhere.test/video','https://user:password@example.test/video']) {
    eq(backendRootUrl(bad,REMOTE),'');
  }
});
test('HLS fallback keeps the remote Sentinel proxy prefix and HTTPS origin', () => {
  eq(sentinelHlsUrl('https://backend.example.test/sentinel/stream/cam1/whep'), 'https://backend.example.test/sentinel/live/stream/cam1/index.m3u8');
  eq(sentinelHlsUrl('https://backend.example.test:8443/proxy/sentinel/stream/cam1/whep'), 'https://backend.example.test:8443/proxy/sentinel/live/stream/cam1/index.m3u8');
  eq(sentinelHlsUrl('/sentinel/stream/cam1/whep'),'/sentinel/live/stream/cam1/index.m3u8');
  eq(sentinelHlsUrl('http://gateway.test:8889/stream/cam1/whep'),'http://gateway.test/live/stream/cam1/index.m3u8');
  eq(sentinelHlsUrl('/api/cameras/cam1/live'),null);
});
test('camera tickets, upload chunks, health probes and widgets cannot fall back to Vercel API-only routes', () => {
  const adapters=readSource('trinetra-ai/src/services/adapters.ts');
  includes(adapters, 'streamUrl: backendUrl(dto.stream_url)');
  includes(adapters, 'backendUrl(dto.detection_url)');
  includes(readSource('trinetra-ai/src/services/chunkedUpload.ts'), 'fetch(apiAssetUrl(`/uploads/chunks/');
  includes(readSource('trinetra-ai/src/services/systemService.ts'), 'fetch(backendUrl(`${config.streamBasePath}');
  includes(readSource('trinetra-ai/src/components/camera/CameraPlayer.tsx'), 'crossOrigin="anonymous"');
  for(const file of ['BandwidthEngine','CommandCenterHero','AIInsightsDashboard']) {
    includes(readSource(`trinetra-ai/src/components/dashboard/${file}.tsx`), 'fetch(apiAssetUrl(');
  }
});
