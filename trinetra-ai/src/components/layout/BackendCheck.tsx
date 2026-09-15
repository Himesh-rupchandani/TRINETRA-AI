import { useCallback, useEffect, useState } from 'react';
import { RefreshCcw, ServerCrash } from 'lucide-react';
import { config } from '@/lib/config';
import { classifyHealthProbe, type BackendState, type BackendVerdict } from '@/lib/backendStatus';
import { cn } from '@/lib/utils';

/**
 * Deployment self-diagnosis strip.
 *
 * Shown under the header ONLY when the origin this page was loaded from cannot
 * actually serve the API — or when the API is live but its demo seeding did not
 * finish. Both cases used to be indistinguishable from "no data": the Command
 * Center simply rendered `0/0` or `0/1` (see `lib/backendStatus.ts` for the two
 * deployment shapes behind those numbers).
 *
 * Silent when the deployment is healthy — a control room that cries wolf gets
 * ignored — and silent in mock mode, where the missing backend is intentional.
 * Set `VITE_DEPLOY_CHECK=false` to switch the strip off entirely.
 */
const LABELS: Record<Exclude<BackendState, 'OK'>, string> = {
  NO_BACKEND: 'No API backend on this deployment',
  UNREACHABLE: 'API unreachable',
  STALE_BUILD: 'Backend is older than this build',
  SEED_FAILED: 'Demo data failed to seed',
  EMPTY_REGISTRY: 'Camera registry lost its rows',
};

/** Red = the API is not answering at all; amber = it answers but is degraded. */
const TONES: Record<Exclude<BackendState, 'OK'>, string> = {
  NO_BACKEND: 'border-critical/40 bg-critical/10 text-critical',
  UNREACHABLE: 'border-critical/40 bg-critical/10 text-critical',
  STALE_BUILD: 'border-amber-300 bg-amber-50 text-amber-800',
  SEED_FAILED: 'border-amber-300 bg-amber-50 text-amber-800',
  EMPTY_REGISTRY: 'border-amber-300 bg-amber-50 text-amber-800',
};

function timeoutSignal(ms: number): AbortSignal | undefined {
  const hasTimeout = typeof AbortSignal !== 'undefined' && typeof AbortSignal.timeout === 'function';
  return hasTimeout ? AbortSignal.timeout(ms) : undefined;
}

export function BackendCheck() {
  const [verdict, setVerdict] = useState<BackendVerdict | null>(null);
  const [checking, setChecking] = useState(false);

  const probe = useCallback(async () => {
    setChecking(true);
    const path = `${config.apiBaseUrl.replace(/\/$/, '')}/health`;
    let status = 0;
    let contentType = '';
    let body = '';
    try {
      const res = await fetch(path, {
        headers: { accept: 'application/json' },
        signal: timeoutSignal(8_000),
      });
      status = res.status;
      contentType = res.headers.get('content-type') ?? '';
      body = await res.text();
    } catch {
      // No response at all (offline, DNS, CORS, timeout) — classified as
      // UNREACHABLE below rather than guessed at here.
      status = 0;
    }
    const origin = typeof window === 'undefined' ? config.apiBaseUrl : window.location.origin;
    setVerdict(classifyHealthProbe({ status, contentType, body, origin, path }));
    setChecking(false);
  }, []);

  useEffect(() => {
    if (config.useMocks) return;
    if ((import.meta.env.VITE_DEPLOY_CHECK ?? 'true') === 'false') return;
    void probe();
  }, [probe]);

  if (config.useMocks || !verdict || verdict.state === 'OK' || !verdict.message) return null;
  const state = verdict.state as Exclude<BackendState, 'OK'>;

  return (
    <div role="status" aria-live="polite" className={cn('border-b', TONES[state])}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 px-4 py-2">
        <ServerCrash size={15} className="shrink-0" aria-hidden />
        <span className="text-2xs font-bold uppercase tracking-widest">{LABELS[state]}</span>
        <span className="max-w-[110ch] text-2xs text-ink">{verdict.message}</span>
        <button
          type="button"
          className="btn-ghost btn-xs ml-auto shrink-0"
          onClick={() => void probe()}
          disabled={checking}
        >
          <RefreshCcw size={12} className={cn(checking && 'animate-spin')} aria-hidden />
          Re-check
        </button>
      </div>
    </div>
  );
}
