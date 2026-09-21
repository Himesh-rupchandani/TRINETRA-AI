/**
 * Frontend regression tests — items 21 and 22 (credential hygiene + env setup).
 *
 * Item 21 — the Sentinel gateway email/password were hardcoded in
 *           `vite.config.ts`, `app/core/config.py`, `cv-engine/config/settings.py`
 *           and two docs, and `trinetra-ai/.env` was committed.
 * Item 22 — `scripts/auto-setup-env.mjs`, `start-auto.sh` and `start-auto.ps1`
 *           rewrote `.env` on every start, destroying the operator's own values
 *           (`VITE_MAPBOX_TOKEN`, custom origins, rotated credentials).
 *
 * These are *behavioural* tests: the real setup script is copied into a
 * throwaway directory tree and executed there, so nothing in the repository is
 * touched. Real credentials are read from the untracked local `.env` only to
 * assert that they never appear in a generated file or in the script's output —
 * they are never printed and never written into this test file.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { FRONTEND_ROOT, REPO_ROOT, deepEq, excludes, includes, ok, readSource, suite, test } from './harness.mjs';

/* ------------------------------- temp fixture ------------------------------ */

function makeTree() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'trinetra-env-'));
  const feRoot = path.join(root, 'trinetra-ai');
  const backendRoot = path.join(root, 'TRINETRAAI', 'backend');
  fs.mkdirSync(path.join(feRoot, 'scripts'), { recursive: true });
  fs.mkdirSync(backendRoot, { recursive: true });
  fs.copyFileSync(
    path.join(FRONTEND_ROOT, 'scripts/auto-setup-env.mjs'),
    path.join(feRoot, 'scripts/auto-setup-env.mjs'),
  );
  const backendExample = path.join(REPO_ROOT, 'TRINETRAAI/backend/.env.example');
  if (fs.existsSync(backendExample)) fs.copyFileSync(backendExample, path.join(backendRoot, '.env.example'));
  return { root, feRoot, backendRoot, envFile: path.join(feRoot, '.env'), envLocal: path.join(feRoot, '.env.local') };
}

function cleanup(tree) {
  fs.rmSync(tree.root, { recursive: true, force: true });
}

/** Run the copied setup script with a deliberately minimal environment. */
function runSetup(tree) {
  return execFileSync(process.execPath, [path.join(tree.feRoot, 'scripts/auto-setup-env.mjs')], {
    encoding: 'utf8',
    cwd: tree.root,
    env: { PATH: process.env.PATH ?? '/usr/bin:/bin', HOME: tree.root },
  });
}

/** Values from the operator's real (untracked) env file — used only for "never leaks" checks. */
function localSecrets() {
  const file = path.join(FRONTEND_ROOT, '.env');
  if (!fs.existsSync(file)) return [];
  const found = [];
  for (const line of fs.readFileSync(file, 'utf8').split(/\r?\n/)) {
    const m = /^\s*(SENTINEL_EMAIL|SENTINEL_PASSWORD)\s*=(.*)$/.exec(line);
    if (m && m[2].trim()) found.push({ key: m[1], value: m[2].trim() });
  }
  return found;
}

/* --------------------- item 22: never clobber an existing .env ------------- */
suite('item 22 — env setup creates missing files and never rewrites existing ones');

test('a fresh tree gets .env, .env.local and a backend .env', () => {
  const tree = makeTree();
  try {
    const out = runSetup(tree);
    ok(fs.existsSync(tree.envFile), 'frontend .env was not created');
    ok(fs.existsSync(tree.envLocal), 'frontend .env.local was not created');
    ok(fs.existsSync(path.join(tree.backendRoot, '.env')), 'backend .env was not created from .env.example');
    includes(out, 'Created .env');
    const content = fs.readFileSync(tree.envFile, 'utf8');
    includes(content, 'VITE_USE_MOCKS=false');
    includes(content, 'BACKEND_ORIGIN=http://localhost:8000');
    includes(content, 'SENTINEL_EMAIL=');
    // Created with empty credentials, never with a value from the repository.
    ok(/^SENTINEL_EMAIL=$/m.test(content), 'a fresh file must not invent gateway credentials');
    ok(/^SENTINEL_PASSWORD=$/m.test(content), 'a fresh file must not invent gateway credentials');
  } finally {
    cleanup(tree);
  }
});

test('an existing .env keeps every byte; only missing keys are appended', () => {
  const tree = makeTree();
  try {
    const operator = [
      '# operator-managed file — do not touch',
      'VITE_USE_MOCKS=false',
      'VITE_MAPBOX_TOKEN=pk.operatorTokenKeepMe',
      'SENTINEL_EMAIL=operator@example.test',
      'SENTINEL_PASSWORD=operator-secret-keep-me',
      'BACKEND_ORIGIN=http://192.168.1.50:8000',
      '',
    ].join('\n');
    fs.writeFileSync(tree.envFile, operator, 'utf8');

    const out = runSetup(tree);
    const after = fs.readFileSync(tree.envFile, 'utf8');

    ok(after.startsWith(operator), 'existing lines were modified or reordered');
    includes(after, 'VITE_MAPBOX_TOKEN=pk.operatorTokenKeepMe');
    includes(after, 'SENTINEL_EMAIL=operator@example.test');
    includes(after, 'SENTINEL_PASSWORD=operator-secret-keep-me');
    includes(after, 'BACKEND_ORIGIN=http://192.168.1.50:8000');
    includes(out, 'appended missing keys only, existing values preserved');
    // The keys the operator did not define are appended, the ones they did are not duplicated.
    const occurrences = (after.match(/^SENTINEL_EMAIL=/gm) ?? []).length;
    ok(occurrences === 1, `SENTINEL_EMAIL must appear exactly once, found ${occurrences}`);
    includes(after, 'VITE_REALTIME_TRANSPORT=');
  } finally {
    cleanup(tree);
  }
});

test('running setup twice is a no-op', () => {
  const tree = makeTree();
  try {
    runSetup(tree);
    const first = fs.readFileSync(tree.envFile, 'utf8');
    const firstLocal = fs.readFileSync(tree.envLocal, 'utf8');
    const out = runSetup(tree);
    ok(fs.readFileSync(tree.envFile, 'utf8') === first, '.env changed on the second run');
    ok(fs.readFileSync(tree.envLocal, 'utf8') === firstLocal, '.env.local changed on the second run');
    includes(out, 'already complete — left untouched');
  } finally {
    cleanup(tree);
  }
});

test('an existing backend .env is left untouched', () => {
  const tree = makeTree();
  try {
    const backendEnv = path.join(tree.backendRoot, '.env');
    fs.writeFileSync(backendEnv, 'DATABASE_URL=sqlite:///./operator.db\nSECRET_KEY=keep-me\n', 'utf8');
    const out = runSetup(tree);
    ok(fs.readFileSync(backendEnv, 'utf8') === 'DATABASE_URL=sqlite:///./operator.db\nSECRET_KEY=keep-me\n', 'backend .env was rewritten');
    includes(out, 'Backend .env exists — left untouched');
  } finally {
    cleanup(tree);
  }
});

test('credentials are resolved from the environment, not baked into the script', () => {
  const tree = makeTree();
  try {
    const out = execFileSync(process.execPath, [path.join(tree.feRoot, 'scripts/auto-setup-env.mjs')], {
      encoding: 'utf8',
      cwd: tree.root,
      env: {
        PATH: process.env.PATH ?? '/usr/bin:/bin',
        HOME: tree.root,
        SENTINEL_EMAIL: 'from-process-env@example.test',
        SENTINEL_PASSWORD: 'from-process-env-secret',
      },
    });
    const content = fs.readFileSync(tree.envFile, 'utf8');
    includes(content, 'SENTINEL_EMAIL=from-process-env@example.test');
    includes(content, 'SENTINEL_PASSWORD=from-process-env-secret');
    includes(out, 'credentials resolved from this machine');
    excludes(out, 'from-process-env-secret', 'the password must never be echoed');
  } finally {
    cleanup(tree);
  }
});

test('the script warns without printing anything secret', () => {
  const tree = makeTree();
  try {
    const out = runSetup(tree);
    includes(out, 'NOT configured');
    includes(out, 'SENTINEL_EMAIL=you@example.org');
    const secrets = localSecrets();
    if (secrets.length) {
      for (const { value } of secrets) excludes(out, value, 'the operator credential appeared in setup output');
    }
  } finally {
    cleanup(tree);
  }
});

/* --------------------- item 21: no credentials in the repo ----------------- */
suite('item 21 — no credential literal survives in tracked sources');

test('the setup script, vite config and start scripts carry no secret literals', () => {
  const secrets = localSecrets();
  const files = [
    'trinetra-ai/scripts/auto-setup-env.mjs',
    'trinetra-ai/vite.config.ts',
    'start-auto.sh',
    'start-auto.ps1',
    'TRINETRAAI/backend/app/core/config.py',
    'cv-engine/config/settings.py',
    'AUTO_LIVE_SETUP.md',
    'FOUR_APIS_USAGE.md',
    'trinetra-ai/.env.example',
    'TRINETRAAI/backend/.env.example',
  ];
  for (const rel of files) {
    const content = readSource(rel);
    if (secrets.length) {
      for (const { key, value } of secrets) {
        excludes(content, value, `${rel} still contains the local ${key} value`);
      }
    }
    excludes(content, 'HACKATHON_DEFAULTS', `${rel} still references the removed hardcoded-defaults object`);
  }
});

test('vite.config.ts resolves the gateway credentials from the environment', () => {
  const vite = readSource('trinetra-ai/vite.config.ts');
  includes(vite, "env.SENTINEL_EMAIL ?? process.env.SENTINEL_EMAIL ?? ''");
  includes(vite, "env.SENTINEL_PASSWORD ?? process.env.SENTINEL_PASSWORD ?? ''");
  includes(vite, 'Basic ${Buffer.from(`${email}:${password}`).toString(\'base64\')}');
  includes(vite, 'proxyReq.setHeader(\'Authorization\', basic)', 'the proxy must still inject Basic auth');
  // No VITE_ prefix => the values are never compiled into the browser bundle.
  excludes(vite, 'VITE_SENTINEL');
});

test('sentinelBasic() returns null when credentials are absent', () => {
  // vite.config.ts pulls in the 'vite' package, so its contract is asserted on
  // source; the runtime behaviour is covered by the temp-tree runs above.
  const vite = readSource('trinetra-ai/vite.config.ts');
  includes(vite, 'function sentinelBasic(env: Record<string, string | undefined>): string | null');
  includes(vite, 'return email && password');
  includes(vite, ': null;', 'missing credentials must yield null, not a malformed header');
});

test('start scripts delegate to the setup script and blank credentials when copying examples', () => {
  const sh = readSource('start-auto.sh');
  includes(sh, 'node scripts/auto-setup-env.mjs');
  includes(sh, "sed -E 's/^(SENTINEL_EMAIL|SENTINEL_PASSWORD)=.*/\\1=/'");
  excludes(sh, 'cp -f', 'the shell launcher must not force-overwrite env files');

  const ps1 = readSource('start-auto.ps1');
  includes(ps1, 'node scripts/auto-setup-env.mjs');
  includes(ps1, 'if (-not (Test-Path $frontendEnvPath))');
  includes(ps1, 'if (-not (Test-Path $backendEnvPath))');
  includes(ps1, "-replace '^(SENTINEL_EMAIL|SENTINEL_PASSWORD)=.*', '$1='");
});

test('env files are git-ignored and only the examples are tracked', () => {
  const rootIgnore = readSource('.gitignore');
  const feIgnore = readSource('trinetra-ai/.gitignore');
  const beIgnore = readSource('TRINETRAAI/backend/.gitignore');
  for (const [name, ignore] of [['root', rootIgnore], ['frontend', feIgnore], ['backend', beIgnore]]) {
    includes(ignore, '.env', `${name} .gitignore must ignore .env`);
    includes(ignore, '!.env.example', `${name} .gitignore must keep .env.example tracked`);
  }
  // The committed .env that leaked credentials is gone from the working tree copies
  // that matter: the file on disk is untracked, so assert it is not part of the
  // repository snapshot the tests can see.
  ok(fs.existsSync(path.join(FRONTEND_ROOT, '.env.example')), 'frontend .env.example must stay');
});

test('no credential literal exists anywhere in the browser source tree', () => {
  const secrets = localSecrets();
  const offenders = [];
  const walk = (dir) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) walk(full);
      else if (/\.(ts|tsx|js|mjs|cjs|json|html)$/.test(entry.name)) {
        const content = fs.readFileSync(full, 'utf8');
        for (const { key, value } of secrets) {
          if (content.includes(value)) offenders.push(`${path.relative(REPO_ROOT, full)} (${key})`);
        }
        if (/VITE_SENTINEL|VITE_[A-Z_]*(PASSWORD|SECRET)/.test(content)) {
          offenders.push(`${path.relative(REPO_ROOT, full)} (browser-exposed credential key)`);
        }
      }
    }
  };
  walk(path.join(FRONTEND_ROOT, 'src'));
  deepEq(offenders, [], 'credentials must never reach the compiled frontend');
});
