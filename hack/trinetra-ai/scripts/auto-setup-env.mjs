#!/usr/bin/env node
/**
 * AUTO-SETUP — makes sure the local env files exist so `npm run dev` can proxy
 * the live Sentinel camera feeds.
 *
 * Called automatically on `npm run dev` via the predev hook, or manually:
 *   node scripts/auto-setup-env.mjs
 *
 * Rules this script lives by:
 *
 *  1. NO credentials are hardcoded here. They are resolved from the process
 *     environment first, then from an env file that already exists on this
 *     machine. A repository must never carry a live username/password.
 *  2. Files are CREATED ONLY WHEN MISSING. An existing .env / .env.local is
 *     never rewritten and no existing value is ever replaced — the operator's
 *     own settings (including VITE_MAPBOX_TOKEN and gateway credentials) win.
 *  3. Missing keys are APPENDED, existing lines are left byte-for-byte alone.
 *  4. Nothing secret is printed: only whether a value is set or missing.
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const frontendRoot = path.resolve(__dirname, '..');
const repoRoot = path.resolve(frontendRoot, '..');
const backendRoot = path.join(repoRoot, 'TRINETRAAI', 'backend');

/* -------------------------------------------------------------------------- */
/* Non-secret defaults (safe to commit)                                        */
/* -------------------------------------------------------------------------- */
const FRONTEND_TEMPLATE = `# LOCAL CONFIGURATION — created by scripts/auto-setup-env.mjs
# Only non-secret, browser-safe values are pre-filled. Gateway credentials
# below are EMPTY on purpose: fill them in locally, never commit them.
VITE_USE_MOCKS=false
VITE_API_BASE_URL=/api
BACKEND_ORIGIN=http://localhost:8000
VITE_REALTIME_TRANSPORT=sse
VITE_MAP_CENTER_LAT=22.3000
VITE_MAP_CENTER_LNG=71.6000
VITE_MAP_DEFAULT_ZOOM=7
VITE_STREAM_BASE_PATH=/sentinel/stream
VITE_LIVE_STREAMS=true
VITE_AUTO_LOGIN=true
VITE_DEFAULT_LIVE_CAMERA=cam04

# Server-side only (NO VITE_ prefix -> never compiled into the browser bundle).
# The dev proxy injects these as HTTP Basic auth on every /sentinel request.
SENTINEL_WHEP_ORIGIN=http://103.250.160.189:8889
SENTINEL_HLS_ORIGIN=http://103.250.160.189:80
SENTINEL_EMAIL=__SENTINEL_EMAIL__
SENTINEL_PASSWORD=__SENTINEL_PASSWORD__

# Optional public Mapbox token (pk.*) — leave empty to use keyless OSM tiles.
VITE_MAPBOX_TOKEN=
`;

/* Keys that must exist in the frontend env file (appended when absent). */
const REQUIRED_FRONTEND_KEYS = [
  'VITE_USE_MOCKS',
  'VITE_API_BASE_URL',
  'BACKEND_ORIGIN',
  'VITE_REALTIME_TRANSPORT',
  'SENTINEL_WHEP_ORIGIN',
  'SENTINEL_HLS_ORIGIN',
  'SENTINEL_EMAIL',
  'SENTINEL_PASSWORD',
  'VITE_STREAM_BASE_PATH',
  'VITE_LIVE_STREAMS',
];

/* -------------------------------------------------------------------------- */
/* Helpers                                                                     */
/* -------------------------------------------------------------------------- */

/** Parse `KEY=value` lines without ever logging the values. */
function readEnvFile(filePath) {
  if (!fs.existsSync(filePath)) return null;
  const out = {};
  for (const line of fs.readFileSync(filePath, 'utf8').split(/\r?\n/)) {
    const m = /^\s*([A-Z0-9_]+)\s*=(.*)$/.exec(line);
    if (m) out[m[1]] = m[2].trim();
  }
  return out;
}

function isSet(value) {
  return typeof value === 'string' && value.trim().length > 0;
}

/**
 * Resolve the Sentinel credentials for this machine.
 * Order: process environment -> existing frontend env files.
 * Returns '' when unknown; callers write an empty value and warn.
 */
function resolveCredentials() {
  const sources = [
    process.env,
    readEnvFile(path.join(frontendRoot, '.env')),
    readEnvFile(path.join(frontendRoot, '.env.local')),
    readEnvFile(path.join(backendRoot, '.env')),
  ];
  let email = '';
  let password = '';
  for (const src of sources) {
    if (!src) continue;
    if (!isSet(email) && isSet(src.SENTINEL_EMAIL)) email = src.SENTINEL_EMAIL.trim();
    if (!isSet(password) && isSet(src.SENTINEL_PASSWORD)) password = src.SENTINEL_PASSWORD.trim();
  }
  return { email, password };
}

/** Append only the keys that are entirely missing; never touch existing ones. */
function appendMissingKeys(filePath, content, defaults) {
  const existing = readEnvFile(filePath) ?? {};
  const missing = REQUIRED_FRONTEND_KEYS.filter((key) => !(key in existing));
  if (!missing.length) return content;
  const additions = missing
    .map((key) => `${key}=${defaults[key] ?? ''}`)
    .join('\n');
  const separator = content.endsWith('\n') || content.length === 0 ? '' : '\n';
  return `${content}${separator}\n# Added by scripts/auto-setup-env.mjs (keys that were missing)\n${additions}\n`;
}

function ensureFrontendEnv(filePath, creds) {
  const name = path.basename(filePath);
  const defaults = {
    VITE_USE_MOCKS: 'false',
    VITE_API_BASE_URL: '/api',
    BACKEND_ORIGIN: 'http://localhost:8000',
    VITE_REALTIME_TRANSPORT: 'sse',
    SENTINEL_WHEP_ORIGIN: 'http://103.250.160.189:8889',
    SENTINEL_HLS_ORIGIN: 'http://103.250.160.189:80',
    SENTINEL_EMAIL: creds.email,
    SENTINEL_PASSWORD: creds.password,
    VITE_STREAM_BASE_PATH: '/sentinel/stream',
    VITE_LIVE_STREAMS: 'true',
  };

  if (!fs.existsSync(filePath)) {
    const content = FRONTEND_TEMPLATE.replace('__SENTINEL_EMAIL__', creds.email).replace(
      '__SENTINEL_PASSWORD__',
      creds.password,
    );
    fs.writeFileSync(filePath, content, 'utf8');
    console.log(`✅ Created ${name} (existing values were never at risk — the file did not exist)`);
    return;
  }

  // Existing file: preserve every byte, only append keys that are absent.
  const before = fs.readFileSync(filePath, 'utf8');
  const after = appendMissingKeys(filePath, before, defaults);
  if (after === before) {
    console.log(`✅ ${name} already complete — left untouched`);
  } else {
    fs.writeFileSync(filePath, after, 'utf8');
    console.log(`✅ ${name} — appended missing keys only, existing values preserved`);
  }
}

function ensureBackendEnv(creds) {
  const backendEnv = path.join(backendRoot, '.env');
  const examplePath = path.join(backendRoot, '.env.example');
  if (fs.existsSync(backendEnv)) {
    console.log('✅ Backend .env exists — left untouched');
    return;
  }
  if (!fs.existsSync(examplePath)) {
    console.log('⚠️  No backend .env and no .env.example to copy — skipping');
    return;
  }
  const lines = fs.readFileSync(examplePath, 'utf8').split(/\r?\n/).map((line) => {
    if (/^\s*SENTINEL_EMAIL\s*=/.test(line)) return `SENTINEL_EMAIL=${creds.email}`;
    if (/^\s*SENTINEL_PASSWORD\s*=/.test(line)) return `SENTINEL_PASSWORD=${creds.password}`;
    return line;
  });
  fs.writeFileSync(
    backendEnv,
    `# LOCAL CONFIGURATION — created by trinetra-ai/scripts/auto-setup-env.mjs\n` +
      `# Untracked: never commit credentials. Edit freely; this file is yours.\n` +
      lines.join('\n'),
    'utf8',
  );
  console.log(`✅ Created backend .env at ${backendEnv}`);
}

/* -------------------------------------------------------------------------- */
/* Run                                                                         */
/* -------------------------------------------------------------------------- */
const creds = resolveCredentials();

ensureFrontendEnv(path.join(frontendRoot, '.env'), creds);
ensureFrontendEnv(path.join(frontendRoot, '.env.local'), creds);
ensureBackendEnv(creds);

if (!isSet(creds.email) || !isSet(creds.password)) {
  console.log('');
  console.log('⚠️  Sentinel gateway credentials are NOT configured.');
  console.log('   Set them in trinetra-ai/.env (server-side keys, no VITE_ prefix):');
  console.log('     SENTINEL_EMAIL=you@example.org');
  console.log('     SENTINEL_PASSWORD=your-access-password');
  console.log('   or export them before starting the dev server. Live camera');
  console.log('   playback needs them; everything else works without them.');
} else {
  console.log('');
  console.log('🎬 Auto-setup complete — live camera credentials resolved from this machine.');
}
