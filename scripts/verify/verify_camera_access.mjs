/**
 * ITEM 25 — explicit end-to-end verification that camera auto-access still works
 * after the credential scrub (items 21/22) and the streaming contract fixes.
 *
 * Nothing secret is printed: credentials are reduced to SHA-256 digests and
 * booleans.
 *
 * How to run (three processes, then this script):
 *
 *   # 1. local stub of the Sentinel gateway (so credential injection is
 *   #    observable without reaching the real host)
 *   node scripts/verify/stub_gateway.mjs                       # 127.0.0.1:8899
 *
 *   # 2. real backend against the real database
 *   cd TRINETRAAI/backend && uvicorn app.main:app --host 0.0.0.0 --port 8000
 *
 *   # 3. real vite dev server, with the gateway origin pointed at the stub
 *   cd trinetra-ai && SENTINEL_WHEP_ORIGIN=http://127.0.0.1:8899 \
 *     SENTINEL_HLS_ORIGIN=http://127.0.0.1:8899 ./node_modules/.bin/vite --port 5173
 *
 *   node scripts/verify/verify_camera_access.mjs               # 20/20 expected
 *
 * Credentials are read from the untracked trinetra-ai/.env (and .env.local, which
 * takes precedence) exactly the way vite's loadEnv() reads them; the real shell
 * environment would win, so this script deliberately does not export any.
 */
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// scripts/verify/ -> repository root
const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const FE = path.join(REPO_ROOT, 'trinetra-ai');
const BACKEND = process.env.BACKEND_URL || 'http://127.0.0.1:8000';
const FRONTEND = process.env.FRONTEND_URL || 'http://127.0.0.1:5173';

function readEnvFile(file) {
  if (!fs.existsSync(file)) return {};
  const out = {};
  for (const line of fs.readFileSync(file, 'utf8').split(/\r?\n/)) {
    const m = /^\s*([A-Z0-9_]+)\s*=(.*)$/.exec(line);
    if (m) out[m[1]] = m[2].trim();
  }
  return out;
}

// Vite precedence: .env.local overrides .env (and the real shell env would win,
// but this verification deliberately does not export credentials).
const env = { ...readEnvFile(path.join(FE, '.env')), ...readEnvFile(path.join(FE, '.env.local')) };
const email = env.SENTINEL_EMAIL || '';
const password = env.SENTINEL_PASSWORD || '';
const expectedBasic = email && password ? `Basic ${Buffer.from(`${email}:${password}`).toString('base64')}` : '';
const expectedDigest = expectedBasic ? crypto.createHash('sha256').update(expectedBasic).digest('hex') : '';

const results = [];
function record(name, pass, detail = '') {
  results.push({ name, pass, detail });
  console.log(`${pass ? 'PASS' : 'FAIL'}  ${name}${detail ? ` — ${detail}` : ''}`);
}

async function fetchJson(url, options = {}, timeoutMs = 8000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { ...options, signal: controller.signal });
    const text = await res.text();
    let json = null;
    try {
      json = JSON.parse(text);
    } catch {
      /* not JSON */
    }
    return { status: res.status, headers: res.headers, text, json };
  } finally {
    clearTimeout(timer);
  }
}

console.log('--- credential resolution (values never printed) ---');
console.log(`SENTINEL_EMAIL set in env files: ${Boolean(email)} (length ${email.length})`);
console.log(`SENTINEL_PASSWORD set in env files: ${Boolean(password)} (length ${password.length})`);
console.log(`expected Authorization sha256: ${expectedDigest.slice(0, 16)}…`);
record('credentials resolve from the untracked env files', Boolean(email && password));

console.log('\n--- A. backend auto-access ---');
{
  const health = await fetchJson(`${BACKEND}/api/health`);
  record('GET /api/health', health.status === 200, `status ${health.status}`);

  const cams = await fetchJson(`${BACKEND}/api/cameras`);
  // The registry endpoint wraps its payload: {"data": [...]} (also accepts
  // {"items": [...]} / a bare array so the check survives a shape tweak).
  const list = cams.json?.data ?? cams.json?.items ?? cams.json ?? [];
  const cameras = Array.isArray(list) ? list : [];
  record('GET /api/cameras returns the registry', cams.status === 200 && cameras.length > 0, `${cameras.length} cameras`);

  const target = cameras.find((c) => (c.camera_id || c.id || '').toLowerCase() === 'cam04') ?? cameras[0];
  const cid = (target?.camera_id || target?.id || '').toLowerCase();

  // The Sentinel host is unreachable from this sandbox, so the registry cameras
  // are honestly OFFLINE. The contract that must hold either way: a ticket is
  // always issued (200), it states whether it is playable, it gives a reason when
  // it is not, it never invents a stream URL, and its expiry is UTC (Z).
  const ticket = await fetchJson(`${BACKEND}/api/cameras/${cid}/stream`);
  const t = ticket.json ?? {};
  record(
    `GET /api/cameras/${cid}/stream issues a ticket`,
    ticket.status === 200 && typeof t.playable === 'boolean' && String(t.expires_at ?? '').endsWith('Z'),
    `status ${ticket.status}, playable=${t.playable}, expires_at=${t.expires_at}`,
  );
  record(
    'an unreachable camera degrades honestly instead of inventing a URL',
    t.playable === true || (Boolean(t.reason) && !t.stream_url),
    `reason=${t.reason || '(none)'}, stream_url=${t.stream_url ? 'set' : 'empty'}`,
  );

  // Item 13 end-to-end against the real backend: the unprovisioned slot must be
  // reported as NOT_CONFIGURED, not folded into OFFLINE.
  const notConfigured = cameras.filter((c) => c.status === 'NOT_CONFIGURED');
  record(
    'the registry distinguishes NOT_CONFIGURED from OFFLINE (item 13)',
    notConfigured.length > 0 && cameras.some((c) => c.status === 'OFFLINE'),
    `NOT_CONFIGURED=${notConfigured.length}, OFFLINE=${cameras.filter((c) => c.status === 'OFFLINE').length}`,
  );

  const streams = await fetchJson(`${BACKEND}/api/ingest/streams/${cid}`);
  record(
    'GET /api/ingest/streams/{id} reports credentials_configured=true',
    streams.status === 200 && streams.json?.credentials_configured === true,
    `status ${streams.status}, credentials_configured=${streams.json?.credentials_configured}`,
  );
  record(
    'the authenticated RTSP URL is only exposed redacted',
    typeof streams.json?.streams?.ai_processing?.rtsp_authenticated_redacted === 'string' &&
      !streams.text.includes(password) &&
      !streams.text.includes(email),
    `rtsp_authenticated_exists=${streams.json?.streams?.ai_processing?.rtsp_authenticated_exists}`,
  );

  const live404 = await fetchJson(`${BACKEND}/api/cameras/definitely-not-a-camera-999/live`, {}, 5000);
  record('GET /api/cameras/{unknown}/live → 404 (item 17E)', live404.status === 404, `status ${live404.status}`);
}

console.log('\n--- B/C/D. vite dev proxy ---');
{
  const whep = await fetchJson(`${FRONTEND}/sentinel/stream/cam04/whep`, { method: 'POST' }, 8000);
  const digest = whep.headers.get('x-stub-auth-sha256') || '';
  record('vite proxy reached the gateway target', whep.status === 201 || whep.status === 200, `status ${whep.status}`);
  record(
    'the proxy injected HTTP Basic auth (digest matches the env credentials)',
    Boolean(digest) && digest === expectedDigest,
    `stub saw ${whep.headers.get('x-stub-has-authorization')} / sha ${digest.slice(0, 16)}…`,
  );
  const location = whep.headers.get('location') || '';
  record(
    'WHEP Location is rewritten onto our own origin',
    location.startsWith('/sentinel/'),
    `location ${location}`,
  );

  const hls = await fetchJson(`${FRONTEND}/sentinel/live/cam04/index.m3u8`, {}, 8000);
  record(
    'HLS proxy path also injects credentials',
    (hls.headers.get('x-stub-auth-sha256') || '') === expectedDigest && hls.status === 200,
    `status ${hls.status}, sha ${(hls.headers.get('x-stub-auth-sha256') || '').slice(0, 16)}…`,
  );

  const apiThroughProxy = await fetchJson(`${FRONTEND}/api/health`, {}, 8000);
  record(
    '/api is proxied to the backend (same-origin browser contract)',
    apiThroughProxy.status === 200,
    `status ${apiThroughProxy.status}`,
  );

  const camsThroughProxy = await fetchJson(`${FRONTEND}/api/cameras`, {}, 8000);
  record('camera registry reachable through the proxy', camsThroughProxy.status === 200, `status ${camsThroughProxy.status}`);
}

console.log('\n--- E. browser-visible bundle carries no credential ---');
{
  const configModule = await fetchJson(`${FRONTEND}/src/lib/config.ts`, {}, 8000);
  const leaks = [email, password].filter((v) => v && configModule.text.includes(v));
  record(
    'dev-served src/lib/config.ts contains no credential',
    configModule.status === 200 && leaks.length === 0,
    `status ${configModule.status}, leaks ${leaks.length}`,
  );

  const entry = await fetchJson(`${FRONTEND}/`, {}, 8000);
  record(
    'index.html served by the dev server contains no credential',
    entry.status === 200 && ![email, password].some((v) => v && entry.text.includes(v)),
    `status ${entry.status}`,
  );
}

console.log('\n--- F. auto-request contract in the player source ---');
{
  const player = fs.readFileSync(path.join(FE, 'src/components/camera/CameraPlayer.tsx'), 'utf8');
  record(
    'CameraPlayer still auto-requests a stream for any non-OFFLINE camera',
    player.includes("if (autoRequest && camera.status !== 'OFFLINE') void requestStream();"),
  );
  record('automatic camera switching still releases the previous feed', player.includes('}, [camera.id]);'));
  const settings = fs.readFileSync(path.join(REPO_ROOT, 'TRINETRAAI/backend/app/core/config.py'), 'utf8');
  record('AUTO_START_CAMERAS default is unchanged (False)', /AUTO_START_CAMERAS:\s*bool\s*=\s*False/.test(settings));
}

const failed = results.filter((r) => !r.pass);
console.log(`\n${results.length - failed.length}/${results.length} camera auto-access checks passed`);
if (failed.length) {
  console.log('failed: ' + failed.map((f) => f.name).join(' | '));
}
process.exit(failed.length ? 1 : 0);
