/**
 * Deploy verifier — "is the TRINETRA AI backend actually live on THIS origin?"
 *
 * Written after a production deployment that looked healthy in the Vercel
 * dashboard but served `0/1` in the Command Center. The number was real: the
 * origin had a backend, but that backend was an OLD deployment whose demo seed
 * had rolled back, leaving the single env-configured `CAMLIVE` row in the
 * registry. Nothing in the UI could say that out loud, so this script does.
 *
 * It answers four questions per URL:
 *
 *   1. Does `/api/health` return JSON?  (No  -> the Vercel project has no
 *      backend service at all: `/api/*` is being answered by the SPA's own
 *      catch-all rewrite. Vercel only reads the root `vercel.json` `services`
 *      block when the project's Root Directory is the repo root.)
 *   2. Does the health payload contain `components.demo_data`?
 *      (No  -> the project is serving a commit from BEFORE the atomic-seed
 *      fix, i.e. a stale deployment still attached to the domain.)
 *   3. How many cameras does the API report, and how many are ONLINE?
 *      (31 / 30 is the expected demo grid: 30 registry cameras + CAMLIVE.)
 *   4. What does `/api/stats/kpis` say? This is the EXACT pair the dashboard
 *      renders as "Camera Network  <online>/<total>" — so `0/1` in a
 *      screenshot can be reproduced (or cleared) from the terminal.
 *
 * Usage
 * -----
 *   node scripts/verify/verify_deploy.mjs                       # prod + aliases
 *   node scripts/verify/verify_deploy.mjs https://foo.vercel.app
 *   node scripts/verify/verify_deploy.mjs --json                # machine output
 *   VERIFY_URLS=https://a,https://b node scripts/verify/verify_deploy.mjs
 *
 * Exit code is 1 when any probed URL is not OK, so CI can gate on it.
 */
import crypto from 'node:crypto';

const DEFAULT_TARGETS = [
  ['prod', 'https://trinetraai-sigma.vercel.app'],
  ['kmhx-prod', 'https://trinetra-ai-kmhx.vercel.app'],
  ['kmhx-main', 'https://trinetra-ai-kmhx-git-main-himesh15.vercel.app'],
];

const TIMEOUT_MS = Number(process.env.VERIFY_TIMEOUT_MS || 25_000);
const EXPECTED_CAMERAS = 31;
const EXPECTED_ONLINE = 30;

const args = process.argv.slice(2);
const asJson = args.includes('--json');
const explicit = args.filter((a) => !a.startsWith('--'));
const envUrls = (process.env.VERIFY_URLS || '')
  .split(',')
  .map((s) => s.trim())
  .filter(Boolean);

const targets = explicit.length
  ? explicit.map((url) => ['custom', url])
  : envUrls.length
    ? envUrls.map((url) => ['custom', url])
    : DEFAULT_TARGETS;

/** One GET with a hard timeout; never throws — returns a result envelope. */
async function get(url, accept = 'application/json') {
  try {
    const res = await fetch(url, {
      headers: { accept, 'user-agent': 'trinetra-deploy-verifier' },
      redirect: 'follow',
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    const body = await res.text();
    return {
      ok: true,
      status: res.status,
      contentType: res.headers.get('content-type') || '',
      location: res.headers.get('x-vercel-id') ? res.headers.get('x-vercel-id') : null,
      body,
    };
  } catch (err) {
    return { ok: false, status: 0, contentType: '', error: err?.name === 'TimeoutError' ? `timeout after ${TIMEOUT_MS}ms` : String(err?.message || err), body: '' };
  }
}

/** JSON parse that tolerates a SPA fallback (HTML) instead of exploding. */
function tryJson(body) {
  const trimmed = body.trim();
  if (!trimmed.startsWith('{') && !trimmed.startsWith('[')) return null;
  try {
    return JSON.parse(trimmed);
  } catch {
    return null;
  }
}

async function probe(base) {
  const root = base.replace(/\/+$/, '');
  const report = { base: root, health: null, cameras: null, kpis: null, build: null, verdict: '', detail: [] };

  // 1. /api/health — the single most diagnostic endpoint.
  const health = await get(`${root}/api/health`);
  const healthJson = health.ok ? tryJson(health.body) : null;
  const isHtml = /text\/html/i.test(health.contentType) || /^\s*<!doctype html/i.test(health.body);
  const loginWall = /vercel\.com\/login|Protected Deployment|sso-api/i.test(health.body) && /text\/html/i.test(health.contentType);

  report.health = {
    httpStatus: health.ok ? health.status : 0,
    error: health.ok ? null : health.error,
    contentType: health.contentType,
    kind: healthJson ? 'json' : isHtml ? (loginWall ? 'login-wall' : 'html-spa') : health.ok ? 'other' : 'unreachable',
    status: healthJson?.status ?? null,
    totalCameras: healthJson?.total_cameras ?? healthJson?.totalCameras ?? null,
    demoData: healthJson?.components?.demo_data ?? null,
    storage: healthJson?.components?.storage ?? null,
    cvPipeline: healthJson?.components?.cv_pipeline ?? null,
    hasDemoDataKey: Boolean(healthJson && healthJson.components && 'demo_data' in healthJson.components),
  };

  if (healthJson) {
    for (const path of ['/api/cameras', '/api/stats/kpis']) {
      const res = await get(`${root}${path}`);
      const json = res.ok ? tryJson(res.body) : null;
      if (path === '/api/cameras') {
        const rows = Array.isArray(json) ? json : (json?.data ?? []);
        report.cameras = {
          httpStatus: res.ok ? res.status : 0,
          count: Array.isArray(rows) ? rows.length : null,
          online: Array.isArray(rows) ? rows.filter((c) => (c?.status || '').toUpperCase() === 'ONLINE').length : null,
        };
      } else {
        report.kpis = json
          ? { httpStatus: res.ok ? res.status : 0, totalCameras: json.total_cameras ?? null, camerasOnline: json.cameras_online ?? null }
          : { httpStatus: res.ok ? res.status : 0, totalCameras: null, camerasOnline: null };
      }
    }
  }

  // Build fingerprint: lets you tell two deployments of the same project apart
  // when both answer 200 (asset hashes change whenever the bundle changes).
  const page = await get(`${root}/`, 'text/html');
  const asset = /\/assets\/[A-Za-z0-9._-]+\.js/.exec(page.body)?.[0] || null;
  report.build = page.ok
    ? {
        httpStatus: page.status,
        indexSha: crypto.createHash('sha256').update(page.body).digest('hex').slice(0, 12),
        mainAsset: asset,
      }
    : { httpStatus: page.ok ? page.status : 0, indexSha: null, mainAsset: null };

  // ---- verdict -----------------------------------------------------------
  const h = report.health;
  const cams = report.cameras?.count;
  const kpis = report.kpis;

  if (h.kind === 'unreachable') {
    report.verdict = 'UNREACHABLE';
    report.detail.push(`no TCP/TLS answer: ${h.error}`);
  } else if (h.kind === 'login-wall') {
    report.verdict = 'PROTECTED';
    report.detail.push('Vercel Deployment Protection answered with the SSO login page — this URL is not public.');
  } else if (h.kind !== 'json') {
    report.verdict = 'NO_BACKEND';
    report.detail.push(
      `${h.httpStatus} ${h.contentType || '(no content-type)'} instead of JSON — /api/* is being answered by the`,
    );
    report.detail.push(
      "SPA's own rewrite, because this origin's Vercel project has Root Directory = trinetra-ai (frontend only).",
    );
    report.detail.push('The root vercel.json `services` block only applies when Root Directory = repo root.');
    report.detail.push('Fix: point the domain at the services project, or set this project Root Directory to `.` and redeploy.');
  } else if (!h.hasDemoDataKey) {
    report.verdict = 'STALE_DEPLOYMENT';
    report.detail.push('Backend is live but /api/health has no components.demo_data — this is a build from before the');
    report.detail.push('atomic demo-seed fix (PR #34). The domain is still serving an old deployment.');
    report.detail.push(
      `registry now: ${cams ?? '?'} cameras — a pre-#34 cold start whose seed rolled back keeps only CAMLIVE, which is why the dashboard reads 0/1.`,
    );
  } else if (cams !== null && cams < EXPECTED_CAMERAS) {
    report.verdict = 'EMPTY_REGISTRY';
    report.detail.push(`demo_data = ${h.demoData}; registry = ${cams} cameras (expected ${EXPECTED_CAMERAS}).`);
    report.detail.push('Cold-start seed did not complete — check the function logs for the boot trace.');
  } else if (kpis && kpis.camerasOnline !== EXPECTED_ONLINE) {
    report.verdict = 'DEGRADED';
    report.detail.push(`cameras = ${cams}, online = ${kpis.camerasOnline} (expected ${EXPECTED_ONLINE}/${EXPECTED_CAMERAS}).`);
  } else {
    report.verdict = 'OK';
    report.detail.push(`backend live — demo_data = ${h.demoData}, storage = ${h.storage}`);
  }
  return report;
}

const reports = [];
for (const [label, url] of targets) {
  reports.push({ label, ...(await probe(url)) });
}

const problems = reports.filter((r) => r.verdict !== 'OK');

if (asJson) {
  console.log(JSON.stringify({ generatedAt: new Date().toISOString(), reports }, null, 2));
} else {
  const pad = (s, n) => String(s ?? '-').padEnd(n).slice(0, n);
  console.log('\nTRINETRA AI — deploy verification');
  console.log(`checked ${new Date().toISOString()}  (expected: ${EXPECTED_CAMERAS} cameras, ${EXPECTED_ONLINE} ONLINE)\n`);
  console.log(`${pad('target', 12)} ${pad('url', 52)} ${pad('http', 5)} ${pad('backend', 8)} ${pad('cams', 5)} ${pad('KPI', 7)} verdict`);
  console.log('-'.repeat(110));
  for (const r of reports) {
    const http = r.health.httpStatus || '-';
    const backend = r.health.kind === 'json' ? 'JSON' : r.health.kind === 'unreachable' ? 'DEAD' : 'HTML';
    const cams = r.cameras?.count ?? '-';
    const kpi = r.kpis ? `${r.kpis.camerasOnline ?? '?'}/${r.kpis.totalCameras ?? '?'}` : '-';
    console.log(`${pad(r.label, 12)} ${pad(r.base, 52)} ${pad(http, 5)} ${pad(backend, 8)} ${pad(cams, 5)} ${pad(kpi, 7)} ${r.verdict}`);
  }
  for (const r of reports) {
    console.log(`\n${r.label} — ${r.base}  →  ${r.verdict}`);
    for (const line of r.detail) console.log(`  · ${line}`);
    if (r.health.kind === 'json') {
      console.log(`  · health: status=${r.health.status} total_cameras=${r.health.totalCameras} demo_data=${r.health.demoData} storage=${r.health.storage}`);
      console.log(`  · kpis (dashboard "Camera Network" reads this): ${r.kpis?.camerasOnline ?? '?'}/${r.kpis?.totalCameras ?? '?'}`);
    }
    console.log(`  · build: index.html sha256=${r.build?.indexSha ?? '-'} bundle=${r.build?.mainAsset ?? '-'}`);
  }
  console.log(`\n${reports.length - problems.length}/${reports.length} origin(s) OK${problems.length ? ` — not OK: ${problems.map((p) => p.label).join(', ')}` : ''}\n`);
}

process.exit(problems.length ? 1 : 0);
