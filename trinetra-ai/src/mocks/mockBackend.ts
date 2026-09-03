/**
 * MOCK BACKEND
 * ------------
 * An in-memory implementation of the exact API contract the real backend
 * exposes. Swapping `VITE_USE_MOCKS=false` routes the same service functions
 * to axios instead — no component or hook changes required.
 */
import type {
  Alert,
  AlertFilters,
  Camera,
  CameraStreamTicket,
  DashboardKpis,
  EventFilters,
  Paginated,
  RoutePoint,
  SystemSummary,
  VehicleEvent,
  VehicleProfile,
  VehicleRoute,
  WatchlistRecord,
} from '@/types';
import { mockCameras } from './cameras';
import { mockEvents } from './events';
import { mockAlerts } from './alerts';
import { mockWatchlist, watchlistByPlate } from './watchlist';
import { buildMockHealth } from './health';
import { haversineKm, minutesBetween, normalisePlate, sleep } from '@/lib/utils';
import { config } from '@/lib/config';
import { syntheticPoster } from '@/utils/syntheticEvidence';
import { cameraStill } from '@/utils/mediaAssets';

/* ------------------------------ mutable store ------------------------------ */

const store = {
  cameras: [...mockCameras] as Camera[],
  events: [...mockEvents] as VehicleEvent[],
  alerts: [...mockAlerts] as Alert[],
  watchlist: [...mockWatchlist] as WatchlistRecord[],
};

type Listener = () => void;
const listeners = new Set<Listener>();
export function subscribeToStore(fn: Listener): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
function emit() {
  listeners.forEach((l) => l());
}

/** Used by the live-event simulator to inject new detections/alerts. */
export function pushMockEvent(event: VehicleEvent, alert?: Alert): void {
  store.events = [event, ...store.events].slice(0, 1200);
  if (alert) store.alerts = [alert, ...store.alerts];
  emit();
}

export function setMockCameraStatus(cameraId: string, status: Camera['status']): void {
  store.cameras = store.cameras.map((c) =>
    c.id === cameraId ? { ...c, status, lastSeen: new Date().toISOString() } : c,
  );
  emit();
}

export const readStore = () => store;

/* --------------------------------- helpers --------------------------------- */

/** Simulated network latency so loading states are exercised in the demo. */
const latency = (ms = 140) => sleep(ms + Math.random() * 120);

function decorateCamera(c: Camera): Camera {
  const evts = store.events.filter((e) => e.cameraId === c.id);
  const last = evts[0];
  const dayAgo = Date.now() - 86400_000;
  return {
    ...c,
    lastSeen: c.status === 'OFFLINE' ? new Date(Date.now() - 42 * 60_000).toISOString() : new Date().toISOString(),
    lastEventAt: last?.timestamp,
    eventCount24h: evts.filter((e) => new Date(e.timestamp).getTime() > dayAgo).length,
  };
}

/* ------------------------------- CAMERAS API ------------------------------- */

export async function getCameras(): Promise<Camera[]> {
  await latency();
  return store.cameras.map(decorateCamera);
}

export async function getCamera(id: string): Promise<Camera> {
  await latency(90);
  const cam = store.cameras.find((c) => c.id === id.toLowerCase());
  if (!cam) throw new Error(`Camera ${id} not found`);
  return decorateCamera(cam);
}

/**
 * Issues the playback ticket for a camera.
 *
 * Even in mock mode the *video is real*: the ticket points at the same-origin
 * WHEP signalling path, which a server-side proxy forwards to the Sentinel
 * media gateway. RTSP cannot be played by a browser and the HLS host sits
 * behind the Sentinel access password, so WebRTC is the correct browser
 * transport. No password, key or token is ever handed to the client.
 *
 * Set VITE_LIVE_STREAMS=false to fall back to synthetic demo frames.
 */
export async function getCameraStream(id: string): Promise<CameraStreamTicket> {
  await latency(160);
  const cam = await getCamera(id);
  const live = config.liveStreams && cam.status !== 'OFFLINE';
  return {
    cameraId: cam.id,
    streamType: live ? 'WEBRTC' : (cam.streamType ?? 'HLS'),
    streamUrl: live ? `${config.streamBasePath}/${cam.id}/whep` : '',
    expiresAt: new Date(Date.now() + 5 * 60_000).toISOString(),
    poster: cam.status === 'OFFLINE' ? syntheticPoster(cam.name, cam.status) : cameraStill(cam.id),
  };
}

/* -------------------------------- EVENTS API -------------------------------- */

function matchesFilters(e: VehicleEvent, f: EventFilters): boolean {
  if (f.plate && !e.plate.includes(normalisePlate(f.plate))) return false;
  if (f.cameraId && f.cameraId !== 'ALL' && e.cameraId !== f.cameraId) return false;
  if (f.eventType && f.eventType !== 'ALL' && e.eventType !== f.eventType) return false;
  if (f.severity && f.severity !== 'ALL' && (e.severity ?? 'INFO') !== f.severity) return false;
  if (f.watchlistOnly && !e.watchlistMatch) return false;

  const t = new Date(e.timestamp);
  if (f.dateFrom && t < new Date(`${f.dateFrom}T00:00:00`)) return false;
  if (f.dateTo && t > new Date(`${f.dateTo}T23:59:59`)) return false;
  if (f.timeFrom || f.timeTo) {
    const hhmm = t.toTimeString().slice(0, 5);
    if (f.timeFrom && hhmm < f.timeFrom) return false;
    if (f.timeTo && hhmm > f.timeTo) return false;
  }
  return true;
}

export async function getEvents(
  filters: EventFilters = {},
  page = 1,
  pageSize = 25,
): Promise<Paginated<VehicleEvent>> {
  await latency();
  const all = store.events.filter((e) => matchesFilters(e, filters));
  const start = (page - 1) * pageSize;
  return { items: all.slice(start, start + pageSize), total: all.length, page, pageSize };
}

export async function getRecentEvents(limit = 20): Promise<VehicleEvent[]> {
  await latency(100);
  return store.events.slice(0, limit);
}

export async function getEventsByCamera(cameraId: string, limit = 25): Promise<VehicleEvent[]> {
  await latency(110);
  return store.events.filter((e) => e.cameraId === cameraId.toLowerCase()).slice(0, limit);
}

export async function getEvent(id: string): Promise<VehicleEvent> {
  await latency(80);
  const ev = store.events.find((e) => e.id === id);
  if (!ev) throw new Error(`Event ${id} not found`);
  return ev;
}

/* ------------------------------- VEHICLES API ------------------------------- */

export async function getVehicleEvents(plate: string): Promise<VehicleEvent[]> {
  await latency(240);
  const p = normalisePlate(plate);
  return store.events
    .filter((e) => e.plate === p)
    .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
}

export async function getVehicleRoute(plate: string): Promise<VehicleRoute> {
  await latency(200);
  const events = await getVehicleEvents(plate);
  const points: RoutePoint[] = events.map((e, i) => {
    const prev = events[i - 1];
    const gapMinutes = prev ? minutesBetween(prev.timestamp, e.timestamp) : undefined;
    const distanceKm = prev ? haversineKm(prev, e) : undefined;
    return {
      sequence: i + 1,
      eventId: e.id,
      cameraId: e.cameraId,
      cameraName: e.cameraName ?? e.cameraId.toUpperCase(),
      location: e.location ?? '—',
      latitude: e.latitude,
      longitude: e.longitude,
      timestamp: e.timestamp,
      plateConfidence: e.plateConfidence,
      gapMinutes,
      distanceKm,
      speedKmph:
        gapMinutes && distanceKm && gapMinutes > 0
          ? Number(((distanceKm / gapMinutes) * 60).toFixed(1))
          : undefined,
    };
  });

  return {
    plate: normalisePlate(plate),
    points,
    startedAt: points[0]?.timestamp,
    endedAt: points[points.length - 1]?.timestamp,
    totalDistanceKm: Number(points.reduce((s, p) => s + (p.distanceKm ?? 0), 0).toFixed(2)),
    camerasTouched: new Set(points.map((p) => p.cameraId)).size,
  };
}

export async function getVehicleProfile(plate: string): Promise<VehicleProfile | null> {
  await latency(160);
  const p = normalisePlate(plate);
  const events = store.events.filter((e) => e.plate === p);
  if (!events.length) return null;
  const sorted = [...events].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
  );
  const first = sorted[0];
  return {
    plate: p,
    vehicleClass: first.vehicleClass ?? 'UNKNOWN',
    colour: first.colour,
    registrationState: p.startsWith('GJ') ? 'Gujarat' : 'Other State',
    firstSeen: first.timestamp,
    lastSeen: sorted[sorted.length - 1].timestamp,
    totalSightings: events.length,
    watchlist: watchlistByPlate(p) ?? null,
  };
}

/* ------------------------------- WATCHLIST API ------------------------------- */

export async function getWatchlist(): Promise<WatchlistRecord[]> {
  await latency();
  return store.watchlist;
}

/* --------------------------------- ALERTS API --------------------------------- */

export async function getAlerts(filters: AlertFilters = {}): Promise<Alert[]> {
  await latency();
  return store.alerts.filter((a) => {
    if (filters.status && filters.status !== 'ALL' && a.status !== filters.status) return false;
    if (filters.severity && filters.severity !== 'ALL' && a.severity !== filters.severity) return false;
    if (filters.query) {
      const q = filters.query.toUpperCase();
      const hay = `${a.plate} ${a.cameraId} ${a.location} ${a.category}`.toUpperCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

export async function acknowledgeAlert(id: string, by = 'Operator'): Promise<Alert> {
  await latency(150);
  let updated: Alert | undefined;
  store.alerts = store.alerts.map((a) => {
    if (a.id !== id) return a;
    updated = {
      ...a,
      status: 'ACKNOWLEDGED',
      acknowledgedBy: by,
      acknowledgedAt: new Date().toISOString(),
    };
    return updated;
  });
  if (!updated) throw new Error(`Alert ${id} not found`);
  emit();
  return updated;
}

export async function resolveAlert(id: string, note?: string): Promise<Alert> {
  await latency(150);
  let updated: Alert | undefined;
  store.alerts = store.alerts.map((a) => {
    if (a.id !== id) return a;
    updated = { ...a, status: 'RESOLVED', resolvedAt: new Date().toISOString(), note: note ?? a.note };
    return updated;
  });
  if (!updated) throw new Error(`Alert ${id} not found`);
  emit();
  return updated;
}

/* --------------------------------- HEALTH API --------------------------------- */

export async function getHealth(): Promise<SystemSummary> {
  await latency(180);
  return buildMockHealth();
}

export async function getKpis(): Promise<DashboardKpis> {
  await latency(120);
  const dayAgo = Date.now() - 86400_000;
  const recent = store.events.filter((e) => new Date(e.timestamp).getTime() > dayAgo);
  return {
    totalCameras: store.cameras.length,
    camerasOnline: store.cameras.filter((c) => c.status === 'ONLINE').length,
    camerasDegraded: store.cameras.filter((c) => c.status === 'DEGRADED').length,
    camerasOffline: store.cameras.filter((c) => c.status === 'OFFLINE').length,
    activeAlerts: store.alerts.filter((a) => a.status !== 'RESOLVED').length,
    vehicleDetections24h: recent.length,
    anprReads24h: recent.filter((e) => e.plate !== '—' && e.plateConfidence > 0).length,
    watchlistMatches24h: recent.filter((e) => e.watchlistMatch).length,
  };
}
