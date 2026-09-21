/**
 * Backend reachability — the ONE place that decides "does the origin this page
 * was loaded from actually serve the API, and did its boot seeding work?".
 *
 * Why this exists
 * ---------------
 * Two different deployments both rendered an empty Command Center without ever
 * saying why:
 *
 *   * a Vercel project whose Root Directory is `trinetra-ai/` (frontend only)
 *     answers `/api/*` from the SPA's own catch-all rewrite — a `200` carrying
 *     `index.html`. axios hands that HTML back as a string, every caller reads
 *     "zero rows", and the dashboard shows `0/0`;
 *   * a live function whose demo seed rolled back keeps one row — the
 *     env-configured `CAMLIVE` slot — which renders as `0/1`.
 *
 * Both are *deployment shapes*, not data. The strip in `MainLayout` and the
 * guard in `lib/api.ts` classify through the functions below, and
 * `tests/backend-status.test.mjs` pins the classification. Keep the hints
 * actionable: the reader is looking at a screen, not at a terminal.
 */

export type BackendState =
  | 'OK'
  | 'NO_BACKEND'
  | 'UNREACHABLE'
  | 'STALE_BUILD'
  | 'SEED_FAILED'
  | 'EMPTY_REGISTRY';

export interface BackendVerdict {
  state: BackendState;
  /** Operator-facing sentence; `null` when the state is OK. */
  message: string | null;
}

export interface HealthProbe {
  /** HTTP status, or 0 when the request never completed. */
  status: number;
  contentType: string;
  body: string;
  /** Origin shown to the operator, e.g. `https://trinetraai-sigma.vercel.app`. */
  origin: string;
  /** Requested path, e.g. `/api/health`. */
  path?: string;
}

/** Where the fix lives when the API is not reachable on this origin. */
export const BACKEND_HINT =
  'On Vercel the API is a `services.backend` entry in the repository-root vercel.json, so the project serving this URL must have Root Directory = repository root (see DEPLOY_VERCEL.md §4). For a Vercel frontend with a Render ML backend, set VITE_API_BASE_URL to the Render HTTPS URL plus /api and rebuild the frontend (see docs/RENDER_BACKEND.md).';

/** The Vite rewrite in action: `index.html` served for a path that must be JSON. */
export function isSpaFallbackBody(body: unknown): boolean {
  return typeof body === 'string' && /^\s*(?:<!doctype\s+html|<html[\s>])/i.test(body);
}

/** Sentence used by the API guard when a JSON endpoint returns the HTML shell. */
export function backendMissingMessage(origin: string, path?: string, status?: number): string {
  const code = status && status !== 200 ? ` (HTTP ${status})` : '';
  const what = path ? `\`${path}\`` : '`/api/*`';
  return `No API backend on ${origin}: ${what} answered with the app's HTML shell instead of JSON${code}. ${BACKEND_HINT}`;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

/**
 * Classify one `GET /api/health` probe.
 *
 * The states are deliberately distinguishable, because each one has a
 * different fix:
 *
 * | state            | what the deployment is                              | fix                          |
 * | ---------------- | --------------------------------------------------- | ---------------------------- |
 * | `NO_BACKEND`     | `/api/*` is the SPA fallback (root dir `trinetra-ai`) | move the domain / set root `.` |
 * | `STALE_BUILD`    | live function, build older than the seed fix          | redeploy the current commit  |
 * | `SEED_FAILED`    | live function, boot seeding raised                    | read the function logs       |
 * | `EMPTY_REGISTRY` | seeded N cameras, registry now holds fewer            | redeploy (pre-fix 0/1 state) |
 * | `OK`             | API answers and reports a filled registry              | —                            |
 */
export function classifyHealthProbe(probe: HealthProbe): BackendVerdict {
  const { status, contentType, body, origin, path = '/api/health' } = probe;

  if (status === 0) {
    return {
      state: 'UNREACHABLE',
      message: `Could not reach ${path} on ${origin} at all — the browser got no response from the server.`,
    };
  }

  if (status >= 300) {
    return { state: 'NO_BACKEND', message: backendMissingMessage(origin, path, status) };
  }

  if (isSpaFallbackBody(body) || /text\/html/i.test(contentType)) {
    return { state: 'NO_BACKEND', message: backendMissingMessage(origin, path, status) };
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(body);
  } catch {
    return {
      state: 'NO_BACKEND',
      message: `No API backend on ${origin}: ${path} answered a non-JSON body. ${BACKEND_HINT}`,
    };
  }

  const json = asRecord(parsed);
  const components = asRecord(json?.components) ?? {};
  const demoData = typeof components.demo_data === 'string' ? components.demo_data : null;
  const totalCameras = typeof json?.total_cameras === 'number' ? json.total_cameras : null;

  if (demoData === null) {
    return {
      state: 'STALE_BUILD',
      message:
        `The API on ${origin} is older than the atomic demo-seed fix: ${path} reports no ` +
        '`components.demo_data`. A cold start on that build can leave the registry holding only the ' +
        'CAMLIVE row, which the Command Center renders as `0/1`. Redeploy the project on the current commit.',
    };
  }

  if (/^FAILED/i.test(demoData)) {
    return {
      state: 'SEED_FAILED',
      message: `Boot seeding failed on ${origin}: ${demoData}. The registry holds whatever survived — check the function logs.`,
    };
  }

  const seeded = /^SEEDED\s+(\d+)/i.exec(demoData);
  if (seeded && totalCameras !== null && totalCameras < Number(seeded[1])) {
    return {
      state: 'EMPTY_REGISTRY',
      message:
        `The API on ${origin} seeded ${seeded[1]} cameras but reports only ${totalCameras} — the registry ` +
        'lost rows after seeding (the pre-fix `0/1` state). Redeploy on the current commit.',
    };
  }

  return { state: 'OK', message: null };
}
