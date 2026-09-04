import type {
  DashboardKpis,
  ServiceHealth,
  ServiceStatus,
  SystemSummary,
} from '@/types';
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
  status: ServiceStatus;
  latencyMs: number | null;
  error: string | null;
};

/** Health polls every few seconds; the gateway does not need that many probes. */
const PROBE_TTL_MS = 20_000;
let probeCache: { at: number; value: GridProbe } | null = null;
let probeInFlight: Promise<GridProbe> | null = null;

async function runProbe(): Promise<GridProbe> {
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
      error:
        e instanceof Error && e.name === 'AbortError'
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

/* ------------------------------ live health ------------------------------ */

interface HealthDto {
  status?: string;
  version?: string;
  database_connected?: boolean;
  active_cameras?: number;
  total_cameras?: number;
  components?: Record<string, string>;
  timestamp?: string;
}

/**
 * Subsystems the control room reports on (spec Phase 20), mapped onto the
 * component keys the backend actually publishes in GET /api/health.
 */
const SUBSYSTEMS: Array<{
  id: string;
  name: string;
  description: string;
  component: string;
}> = [
  {
    id: 'sentinel-grid',
    name: 'Sentinel Grid',
    description: 'Connection to the city camera network',
    component: 'sentinel_catalogue',
  },
  {
    id: 'camera-registry',
    name: 'Camera Registry',
    description: 'Master list of every camera and its location',
    component: 'database',
  },
  {
    id: 'ai-engine',
    name: 'AI Engine',
    description: 'Spots and follows vehicles in the video',
    component: 'event_ingestion',
  },
  {
    id: 'anpr-engine',
    name: 'ANPR Engine',
    description: 'Reads number plates from the video',
    component: 'event_ingestion',
  },
  {
    id: 'watchlist-db',
    name: 'Watchlist Database',
    description: 'The list of vehicles being watched for',
    component: 'watchlist',
  },
  {
    id: 'alert-engine',
    name: 'Alert Engine',
    description: 'Decides when to raise an alert for you',
    component: 'alert_engine',
  },
  {
    id: 'gis',
    name: 'GIS Service',
    description: 'Works out the route a vehicle took',
    component: 'database',
  },
  {
    id: 'api-gateway',
    name: 'API Gateway',
    description: 'Connects this website to the system',
    component: 'api',
  },
];

function toServiceStatus(raw?: string): ServiceStatus {
  const s = (raw ?? '').toUpperCase();
  if (s === 'HEALTHY' || s === 'OK' || s === 'UP') return 'HEALTHY';
  if (s === 'DEGRADED' || s === 'WARNING') return 'DEGRADED';
  if (!s) return 'OFFLINE';
  return 'OFFLINE';
}

/**
 * Build the health summary from real backend data.
 *
 * Fields the backend does not report (uptime %, versions, queue depth) are
 * deliberately omitted rather than filled with plausible-looking numbers —
 * LIVE mode must never show fabricated telemetry (spec Phase 4 / 35).
 */
function toSystemSummary(dto: HealthDto, kpis?: DashboardKpis): SystemSummary {
  const components = dto.components ?? {};
  const heartbeat = dto.timestamp ?? new Date().toISOString();
  const online = kpis?.camerasOnline ?? dto.active_cameras ?? 0;

  const services: ServiceHealth[] = SUBSYSTEMS.map((s) => ({
    id: s.id,
    name: s.name,
    description: s.description,
    status: toServiceStatus(components[s.component]),
    uptimePct: 0,
    uptimeSince: '',
    lastHeartbeat: heartbeat,
    activeConnections: s.id === 'sentinel-grid' || s.id === 'ai-engine' ? online : 0,
    processingState: toServiceStatus(components[s.component]) === 'HEALTHY' ? 'PROCESSING' : 'IDLE',
    latestError: null,
    version: s.id === 'api-gateway' ? dto.version : undefined,
  }));

  return {
    services,
    ingestFps: 0,
    eventsPerMinute: 0,
    anprPerMinute: 0,
    generatedAt: heartbeat,
  };
}

export const systemService = {
  async health(): Promise<SystemSummary> {
    const summary = isMockMode
      ? await mock.getHealth()
      : toSystemSummary(await get<HealthDto>('/health'));
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
