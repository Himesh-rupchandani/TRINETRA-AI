import type { DashboardKpis, SystemSummary } from '@/types';
import { get, isMockMode } from './api';
import * as mock from '@/mocks/mockBackend';
import { config } from '@/lib/config';

/**
 * Live reachability probe against the Sentinel media gateway.
 *
 * A control room should not claim a service is HEALTHY because a fixture says
 * so. We issue a cheap OPTIONS preflight to a known camera path through our
 * own proxy and report what actually came back.
 */
type GridProbe = {
  status: 'HEALTHY' | 'DEGRADED' | 'OFFLINE';
  latencyMs: number | null;
  error: string | null;
};

/** Health polls every few seconds; the gateway does not need that many probes. */
const PROBE_TTL_MS = 20_000;
let probeCache: { at: number; value: GridProbe } | null = null;
let probeInFlight: Promise<GridProbe> | null = null;

async function runProbe(): Promise<{
  status: 'HEALTHY' | 'DEGRADED' | 'OFFLINE';
  latencyMs: number | null;
  error: string | null;
}> {
  const started = performance.now();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 6_000);
  try {
    const res = await fetch(`${config.streamBasePath}/cam01/whep`, {
      method: 'OPTIONS',
      signal: controller.signal,
    });
    const latencyMs = Math.round(performance.now() - started);
    if (res.ok || res.status === 204) {
      return {
        status: latencyMs > 1_500 ? 'DEGRADED' : 'HEALTHY',
        latencyMs,
        error: latencyMs > 1_500 ? `Signalling latency ${latencyMs} ms` : null,
      };
    }
    return {
      status: 'DEGRADED',
      latencyMs,
      error: `Gateway preflight returned HTTP ${res.status}`,
    };
  } catch (e) {
    return {
      status: 'OFFLINE',
      latencyMs: null,
      error: e instanceof Error && e.name === 'AbortError'
        ? 'Gateway preflight timed out after 6 s'
        : 'Media gateway unreachable from this client',
    };
  } finally {
    clearTimeout(timer);
  }
}

/** Cached, de-duplicated wrapper around the live gateway probe. */
async function probeSentinelGrid(): Promise<GridProbe> {
  if (probeCache && Date.now() - probeCache.at < PROBE_TTL_MS) return probeCache.value;
  if (probeInFlight) return probeInFlight;
  probeInFlight = runProbe()
    .then((value) => {
      probeCache = { at: Date.now(), value };
      return value;
    })
    .finally(() => {
      probeInFlight = null;
    });
  return probeInFlight;
}

export const systemService = {
  async health(): Promise<SystemSummary> {
    const summary = isMockMode ? await mock.getHealth() : await get<SystemSummary>('/health');
    if (!config.liveStreams) return summary;

    const probe = await probeSentinelGrid();
    const services = summary.services.map((svc) =>
      svc.name === 'Sentinel Grid'
        ? {
            ...svc,
            status: probe.status,
            latencyMs: probe.latencyMs ?? svc.latencyMs,
            lastHeartbeat: new Date().toISOString(),
            latestError: probe.error ?? svc.latestError,
            processingState: probe.status === 'OFFLINE' ? ('IDLE' as const) : svc.processingState,
          }
        : svc,
    );

    return { ...summary, services, generatedAt: new Date().toISOString() };
  },

  kpis(): Promise<DashboardKpis> {
    return isMockMode ? mock.getKpis() : get<DashboardKpis>('/stats/kpis');
  },
};
