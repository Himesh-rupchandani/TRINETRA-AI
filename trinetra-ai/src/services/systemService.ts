import type { DashboardKpis, ServiceHealth, SystemSummary } from '@/types';
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
    const summary = isMockMode ? await mock.getHealth() : await liveHealth();
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
    if (isMockMode) return mock.getKpis();
    // Aggregated by the backend from real rows (GET /api/stats/kpis).
    return get<DashboardKpis>('/stats/kpis');
  },
};

/* ------------------------- live health (GET /health) ------------------------ */

interface HealthDto {
  status?: string;
  version?: string;
  environment?: string;
  database_connected?: boolean;
  active_cameras?: number;
  total_cameras?: number;
  demo_mode?: boolean;
  timestamp?: string;
  components?: Record<string, string>;
}

const COMPONENT_LABELS: Array<{ key: string; name: string; description: string }> = [
  { key: 'api', name: 'API Gateway', description: 'FastAPI service exposing the registry, events and alerts.' },
  { key: 'sentinel_catalogue', name: 'Sentinel Catalogue', description: 'Government CCTV catalogue sync (cctv.corp8.cloud).' },
  { key: 'camera_registry', name: 'Camera Registry', description: 'Model 1 camera catalogue with GIS coordinates.' },
  { key: 'event_ingestion', name: 'AI Engine', description: 'YOLO detection + tracking + ANPR ingestion pipeline.' },
  { key: 'anpr', name: 'ANPR Engine', description: 'Plate detection, OCR confidence and normalisation.' },
  { key: 'database', name: 'PostgreSQL', description: 'Event, camera, watchlist and alert storage.' },
  { key: 'watchlist', name: 'Watchlist Service', description: 'Plate watchlist matching on ingest.' },
  { key: 'alert_engine', name: 'Alert Engine', description: 'Alert creation, deduplication and lifecycle.' },
  { key: 'realtime_channel', name: 'Realtime Channel', description: 'WebSocket + SSE broadcast of detections and alerts.' },
];

/**
 * Map the backend's `/health` components onto the control-room board.
 * Only reported facts are shown — uptime percentages and queue depths the
 * backend does not measure stay absent rather than fabricated.
 */
async function liveHealth(): Promise<SystemSummary> {
  const raw = await get<HealthDto>('/health');
  const components = raw.components ?? {};
  const heartbeat = raw.timestamp ?? new Date().toISOString();
  const mapStatus = (s?: string): ServiceHealth['status'] =>
    s === 'HEALTHY' ? 'HEALTHY' : s === 'DEGRADED' ? 'DEGRADED' : 'OFFLINE';

  const services: ServiceHealth[] = COMPONENT_LABELS.map((c) => {
    const svc: ServiceHealth = {
      id: c.key,
      name: c.name,
      description: c.description,
      status: mapStatus(components[c.key]),
      lastHeartbeat: heartbeat,
      version: raw.version,
    };
    if (c.key === 'database') svc.status = raw.database_connected ? 'HEALTHY' : 'OFFLINE';
    if (c.key === 'camera_registry') {
      svc.status = (raw.total_cameras ?? 0) > 0 && raw.database_connected ? 'HEALTHY' : 'DEGRADED';
      svc.activeConnections = raw.total_cameras;
    }
    return svc;
  });

  // The media gateway itself is probed separately (see probeSentinelGrid).
  services.splice(2, 0, {
    id: 'sentinel-grid',
    name: 'Sentinel Grid',
    description: 'Live CCTV media gateway (WebRTC/WHEP + HLS + RTSP).',
    status: 'HEALTHY', // replaced by the live probe result below
    lastHeartbeat: heartbeat,
  });

  return { services, generatedAt: heartbeat };
}
