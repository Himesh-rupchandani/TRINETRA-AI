/**
 * Regression tests for the deploy self-diagnosis (lib/backendStatus.ts) and the
 * guard that feeds it (services/api.ts).
 *
 * The incident these pin down: production rendered `0/1` in the Command Center
 * and nothing in the UI said why. Two deployment shapes both look like "no
 * data":
 *
 *   * `/api/*` answered by the SPA's own catch-all rewrite (Vercel project Root
 *     Directory = `trinetra-ai/`) → `200 text/html`, axios handed callers a
 *     string, and every list read as empty → `0/0`;
 *   * a live function from a build older than the atomic demo-seed fix, whose
 *     registry kept only the `CAMLIVE` row → `0/1`.
 *
 * `classifyHealthProbe` must name each one, and `get()`/`post()` must not treat
 * an HTML body as valid JSON.
 */
import { eq, includes, loadTs, ok, suite, test } from './harness.mjs';

const { classifyHealthProbe, isSpaFallbackBody, backendMissingMessage } = loadTs('src/lib/backendStatus.ts');

const ORIGIN = 'https://trinetraai-sigma.vercel.app';
const SPA_SHELL = '<!doctype html><html lang="en"><head><title>TRINETRA AI</title></head><body></body></html>';
const HEALTH_OK = (extra = {}) =>
  JSON.stringify({
    status: 'healthy',
    total_cameras: 31,
    components: {
      database: 'HEALTHY',
      cv_pipeline: 'DISABLED (API-only: no cv2/numpy)',
      storage: 'EPHEMERAL',
      demo_data: 'SEEDED 30/22/5',
      ...extra,
    },
  });

/* ---------------------- the SPA fallback body ------------------------------ */

suite('deploy check — recognising the SPA fallback');

test('index.html served for /api/* is detected', () => {
  ok(isSpaFallbackBody(SPA_SHELL), 'doctype shell must be detected');
  ok(isSpaFallbackBody('\n  <html lang="en">'), 'leading whitespace must not hide it');
  eq(isSpaFallbackBody('{"status":"healthy"}'), false);
  eq(isSpaFallbackBody(undefined), false);
  eq(isSpaFallbackBody(null), false);
});

test('a JSON endpoint answering HTML is a hard error with the fix in it', () => {
  const message = backendMissingMessage(ORIGIN, '/health', 200);
  includes(message, 'No API backend');
  includes(message, ORIGIN);
  includes(message, '/health');
  includes(message, 'Root Directory = repository root');
});

/* ------------------------- health probe classification --------------------- */

suite('deploy check — one state per failure shape');

test('healthy payload with a full registry is OK', () => {
  const verdict = classifyHealthProbe({ status: 200, contentType: 'application/json', body: HEALTH_OK(), origin: ORIGIN });
  eq(verdict.state, 'OK');
  eq(verdict.message, null);
});

test('HTML body => NO_BACKEND (frontend-only project)', () => {
  const verdict = classifyHealthProbe({
    status: 200,
    contentType: 'text/html; charset=utf-8',
    body: SPA_SHELL,
    origin: ORIGIN,
  });
  eq(verdict.state, 'NO_BACKEND');
  includes(verdict.message, 'No API backend');
});

test('non-2xx => NO_BACKEND with the status shown', () => {
  const verdict = classifyHealthProbe({ status: 404, contentType: 'text/plain', body: 'Not Found', origin: ORIGIN });
  eq(verdict.state, 'NO_BACKEND');
  includes(verdict.message, '404');
});

test('no response at all => UNREACHABLE', () => {
  const verdict = classifyHealthProbe({ status: 0, contentType: '', body: '', origin: ORIGIN });
  eq(verdict.state, 'UNREACHABLE');
  includes(verdict.message, 'Could not reach');
});

test('live but pre-fix build (no components.demo_data) => STALE_BUILD', () => {
  const body = JSON.stringify({ status: 'healthy', total_cameras: 1, components: { storage: 'EPHEMERAL' } });
  const verdict = classifyHealthProbe({ status: 200, contentType: 'application/json', body, origin: ORIGIN });
  eq(verdict.state, 'STALE_BUILD');
  includes(verdict.message, '0/1');
});

test('seed failure is reported verbatim', () => {
  const verdict = classifyHealthProbe({
    status: 200,
    contentType: 'application/json',
    body: HEALTH_OK({ demo_data: 'FAILED: IntegrityError("UNIQUE constraint failed")' }),
    origin: ORIGIN,
  });
  eq(verdict.state, 'SEED_FAILED');
  includes(verdict.message, 'IntegrityError');
});

test('seed claims 30 cameras but the registry has 1 => EMPTY_REGISTRY (the 0/1 state)', () => {
  const verdict = classifyHealthProbe({
    status: 200,
    contentType: 'application/json',
    body: HEALTH_OK({}).replace('"total_cameras":31', '"total_cameras":1'),
    origin: ORIGIN,
  });
  eq(verdict.state, 'EMPTY_REGISTRY');
  includes(verdict.message, 'only 1');
});

// A real deployment with a real (non-demo) registry must never be flagged:
// demo_data SEEDED is the only thing compared against total_cameras.
test('a small non-demo registry is not flagged', () => {
  const verdict = classifyHealthProbe({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ status: 'healthy', total_cameras: 2, components: { demo_data: 'SKIPPED' } }),
    origin: ORIGIN,
  });
  eq(verdict.state, 'OK');
});

/* --------------------- the axios-facing guard in api.ts -------------------- */

suite('deploy check — get()/post() refuse the HTML shell');

let htmlResponses = true;
const axiosStub = {
  create: () => ({
    interceptors: { request: { use() {} }, response: { use() {} } },
    get: async () => ({ status: 200, data: htmlResponses ? SPA_SHELL : { ok: true } }),
    post: async () => ({ status: 200, data: htmlResponses ? SPA_SHELL : { ok: true } }),
  }),
};
const { get, post, ApiError } = loadTs('src/services/api.ts', {
  axios: axiosStub,
  '@/lib/config': { config: { apiBaseUrl: '/api', useMocks: false } },
});

test('get() rejects when the body is the SPA shell', async () => {
  htmlResponses = true;
  let error = null;
  try {
    await get('/health');
  } catch (e) {
    error = e;
  }
  ok(error, 'get() must reject on an HTML body');
  eq(error.name, 'ApiError');
  includes(error.message, 'No API backend');
});

test('post() rejects the same way', async () => {
  htmlResponses = true;
  let error = null;
  try {
    await post('/alerts/1/resolve');
  } catch (e) {
    error = e;
  }
  ok(error instanceof ApiError, 'post() must reject with an ApiError');
});

test('real JSON still passes through untouched', async () => {
  htmlResponses = false;
  eq((await get('/health')).ok, true);
  eq((await post('/alerts/1/resolve')).ok, true);
});
