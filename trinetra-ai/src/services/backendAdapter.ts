/**
 * Backend adapter — the ONLY place that knows the backend's wire format.
 *
 * The FastAPI backend speaks snake_case with paginated envelopes
 * (`{items,total,page,size,pages}`, `{data:[...]}`). The UI speaks the typed
 * camelCase model in `@/types`. Every live-mode call flows through these
 * mappers so there is exactly one translation layer and one source of truth.
 *
 * Rules (Phase 4 / Phase 35):
 *  - never invent values the backend did not send (missing data stays
 *    `undefined` and the UI renders an honest `—`);
 *  - confidence arrives 0..1 from OCR and is surfaced as a 0..100 percentage,
 *    matching the existing UI convention;
 *  - evidence references resolve to the backend-served `/api/evidence` files.
 */
import type {
  Alert,
  Camera,
  CameraStatus,
  Paginated,
  StreamType,
  VehicleClass,
  VehicleEvent,
  VehicleProfile,
  VehicleRoute,
  WatchlistRecord,
} from '@/types';
import { get } from './api';
import { config } from '@/lib/config';
import { haversineKm, minutesBetween } from '@/lib/utils';

/* ------------------------------ raw DTO shapes ----------------------------- */
/* Kept intentionally loose (unknown-key tolerant) — the backend owns these. */

export interface CameraItemDto {
  id: string;
  camera_id?: string;
  name: string;
  location?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  status?: string;
  codec?: string | null;
  width?: number | null;
  height?: number | null;
  stream_type?: string;
  stream_url?: string;
  last_seen?: string | null;
  last_event_at?: string | null;
  event_count_24h?: number | null;
}

export interface VehicleEventDto {
  id?: number;
  event_id?: number;
  camera_id: string;
  vehicle_track_id?: number | null;
  vehicle_id?: number | null;
  track_id?: number | null;
  plate_number?: string | null;
  plate?: string | null;
  plate_raw?: string | null;
  plate_confidence?: number | null;
  confidence?: number | null;
  vehicle_class?: string | null;
  event_time?: string;
  timestamp?: string;
  latitude?: number | null;
  longitude?: number | null;
  evidence_ref?: string | null;
  watchlist_match?: boolean;
}

export interface AlertDto {
  id?: number;
  alert_id?: string;
  event_id?: number | null;
  camera_id: string;
  plate_number?: string | null;
  plate?: string | null;
  alert_type?: string;
  severity?: string;
  status?: string;
  message?: string;
  timestamp?: string;
  event_time?: string;
  confidence?: number | null;
  acknowledged_at?: string | null;
  acknowledged_by?: string | null;
  resolved_at?: string | null;
  resolved_by?: string | null;
}

export interface WatchlistDto {
  id: number;
  plate_number: string;
  category: string;
  description?: string | null;
  active: boolean;
  created_at: string;
}

export interface RouteDto {
  plate_number: string;
  total_sightings: number;
  route: Array<{
    sequence: number;
    camera_id: string;
    event_time: string;
    latitude?: number | null;
    longitude?: number | null;
    confidence?: number | null;
  }>;
}

export interface PageDto<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

/* -------------------------------- helpers ---------------------------------- */

const toStatus = (s?: string): CameraStatus =>
  s === 'ONLINE' || s === 'OFFLINE' || s === 'DEGRADED' ? s : 'OFFLINE';

const toStreamType = (s?: string): StreamType => {
  const v = (s ?? '').toUpperCase();
  return v === 'RTSP' || v === 'WEBRTC' || v === 'MJPEG' ? v : 'HLS';
};

const CLASS_MAP: Record<string, VehicleClass> = {
  CAR: 'CAR',
  MOTORCYCLE: 'MOTORCYCLE',
  BIKE: 'MOTORCYCLE',
  BUS: 'BUS',
  TRUCK: 'TRUCK',
  VAN: 'VAN',
  'AUTO-RICKSHAW': 'AUTO_RICKSHAW',
  'AUTO RICKSHAW': 'AUTO_RICKSHAW',
  AUTORICKSHAW: 'AUTO_RICKSHAW',
};
const toVehicleClass = (s?: string | null): VehicleClass =>
  (s && CLASS_MAP[s.trim().toUpperCase()]) || 'UNKNOWN';

/** 0..1 (OCR convention) → 0..100 (UI convention). */
const toPercent = (v?: number | null): number =>
  v == null ? 0 : Math.round(Math.min(1, Math.max(0, v)) * 1000) / 10;

/** Backend-relative evidence ref → same-origin URL. */
export function evidenceUrl(ref?: string | null): string | undefined {
  if (!ref) return undefined;
  if (/^https?:\/\//i.test(ref)) return ref;
  return `${config.apiBaseUrl.replace(/\/$/, '')}/evidence/${ref.replace(/^\/+/, '')}`;
}

/** Sibling plate-crop written by the CV engine (`…_plate.jpg`). */
export function plateCropUrl(ref?: string | null): string | undefined {
  if (!ref || /^https?:\/\//i.test(ref)) return undefined;
  return ref.replace(/\.jpe?g$/i, '_plate.jpg').replace(/^\/+/, '');
}

/* ------------------------------ camera index ------------------------------- */
/** Shared, cached camera lookup used to decorate events/alerts with names. */
export type CameraIndex = Map<string, Camera>;

let indexPromise: Promise<CameraIndex> | null = null;

export function getCameraIndex(refresh = false): Promise<CameraIndex> {
  if (!refresh && indexPromise) return indexPromise;
  indexPromise = get<{ data: CameraItemDto[] }>('/cameras')
    .then((r) => new Map(mapCameras(r.data).map((c) => [c.id, c])))
    .catch(() => new Map() as CameraIndex);
  return indexPromise;
}

/* -------------------------------- mappers ---------------------------------- */

export function mapCamera(raw: CameraItemDto): Camera {
  return {
    id: (raw.id ?? raw.camera_id ?? '').toLowerCase(),
    name: raw.name,
    location: raw.location ?? raw.name,
    latitude: raw.latitude ?? 0,
    longitude: raw.longitude ?? 0,
    // Sentinel does not publish department/zone — left absent on purpose so
    // live mode never displays fabricated ownership data.
    status: toStatus(raw.status),
    codec: raw.codec ?? undefined,
    width: raw.width ?? undefined,
    height: raw.height ?? undefined,
    streamType: toStreamType(raw.stream_type),
    lastSeen: raw.last_seen ?? undefined,
    lastEventAt: raw.last_event_at ?? undefined,
    eventCount24h: raw.event_count_24h ?? 0,
  };
}

export function mapCameras(raws: CameraItemDto[]): Camera[] {
  return raws.map(mapCamera);
}

export function mapVehicleEvent(raw: VehicleEventDto, cameras?: CameraIndex): VehicleEvent {
  const cameraId = (raw.camera_id ?? '').toLowerCase();
  const cam = cameras?.get(cameraId);
  const timestamp = raw.event_time ?? raw.timestamp ?? new Date().toISOString();
  const ref = raw.evidence_ref ?? undefined;
  return {
    id: String(raw.id ?? raw.event_id ?? `${cameraId}-${timestamp}`),
    cameraId,
    cameraName: cam?.name,
    vehicleId: raw.vehicle_track_id ?? raw.vehicle_id ?? raw.track_id ?? undefined,
    plate: raw.plate_number ?? raw.plate ?? '',
    plateConfidence: toPercent(raw.plate_confidence ?? raw.confidence),
    timestamp,
    latitude: raw.latitude ?? 0,
    longitude: raw.longitude ?? 0,
    location: cam?.location,
    vehicleClass: toVehicleClass(raw.vehicle_class),
    eventType: raw.watchlist_match ? 'WATCHLIST_MATCH' : raw.plate_number || raw.plate ? 'ANPR_READ' : 'VEHICLE_DETECTION',
    watchlistMatch: Boolean(raw.watchlist_match),
    evidenceRef: ref,
    evidence: ref
      ? {
          ref,
          frameUrl: evidenceUrl(ref),
          plateCropUrl: evidenceUrl(plateCropUrl(ref)),
          capturedAt: timestamp,
        }
      : undefined,
  };
}

export function mapAlert(raw: AlertDto, cameras?: CameraIndex): Alert {
  const cameraId = (raw.camera_id ?? '').toLowerCase();
  const cam = cameras?.get(cameraId);
  return {
    id: String(raw.id ?? (raw.alert_id ? raw.alert_id.replace(/^AL-/, '') : '')),
    eventId: raw.event_id != null ? String(raw.event_id) : '',
    plate: raw.plate_number ?? raw.plate ?? '—',
    cameraId,
    cameraName: cam?.name,
    location: cam?.location,
    severity: (raw.severity as Alert['severity']) ?? 'HIGH',
    status: (raw.status as Alert['status']) ?? 'NEW',
    category: raw.alert_type ?? 'WATCHLIST_MATCH',
    createdAt: raw.timestamp ?? raw.event_time ?? new Date().toISOString(),
    confidence: raw.confidence != null ? toPercent(raw.confidence) : undefined,
    acknowledgedAt: raw.acknowledged_at ?? undefined,
    acknowledgedBy: raw.acknowledged_by ?? undefined,
    resolvedAt: raw.resolved_at ?? undefined,
    note: raw.message,
  };
}

const CATEGORY_MAP: Record<string, WatchlistRecord['category']> = {
  'STOLEN VEHICLE': 'STOLEN VEHICLE',
  'WANTED VEHICLE': 'WANTED SUSPECT',
  'WANTED SUSPECT': 'WANTED SUSPECT',
  BLACKLISTED: 'BLACKLISTED',
  'EXPIRED PERMIT': 'EXPIRED PERMIT',
  'PERSON OF INTEREST': 'PERSON OF INTEREST',
  'AMBER ALERT': 'AMBER ALERT',
};

export function mapWatchlist(raw: WatchlistDto): WatchlistRecord {
  const upper = (raw.category ?? '').trim().toUpperCase();
  return {
    id: String(raw.id),
    plate: raw.plate_number,
    category: CATEGORY_MAP[upper] ?? (upper || 'OTHER'),
    reason: raw.description ?? '',
    addedAt: raw.created_at,
    active: raw.active,
  };
}

export function mapPage<T>(raw: { items: T[]; total: number; page: number; size: number }): Paginated<T> {
  return {
    items: raw.items,
    total: raw.total,
    page: raw.page,
    pageSize: raw.size,
  };
}

/* --------------------------- derived structures ---------------------------- */

/** Chronological GIS route from backend route points + full event list. */
export function mapVehicleRoute(
  raw: RouteDto,
  events: VehicleEvent[],
  cameras?: CameraIndex,
): VehicleRoute {
  const key = (cam: string, t: string) => `${cam.toLowerCase()}|${new Date(t).getTime()}`;
  const byKey = new Map(events.map((e) => [key(e.cameraId, e.timestamp), e]));

  const points = raw.route.map((p, i) => {
    const cameraId = p.camera_id.toLowerCase();
    const cam = cameras?.get(cameraId);
    const ev = byKey.get(key(p.camera_id, p.event_time));
    const prev = raw.route[i - 1];
    const gapMinutes = prev ? minutesBetween(prev.event_time, p.event_time) : undefined;
    const distanceKm =
      prev && prev.latitude != null && prev.longitude != null && p.latitude != null && p.longitude != null
        ? Number(
            haversineKm(
              { latitude: prev.latitude, longitude: prev.longitude },
              { latitude: p.latitude, longitude: p.longitude },
            ).toFixed(2),
          )
        : undefined;
    return {
      sequence: p.sequence ?? i + 1,
      eventId: ev?.id ?? '',
      cameraId,
      cameraName: cam?.name ?? cameraId.toUpperCase(),
      location: cam?.location ?? '—',
      latitude: p.latitude ?? 0,
      longitude: p.longitude ?? 0,
      timestamp: p.event_time,
      plateConfidence: toPercent(p.confidence ?? ev?.plateConfidence),
      gapMinutes,
      distanceKm,
      speedKmph:
        gapMinutes && distanceKm && gapMinutes > 0
          ? Number(((distanceKm / gapMinutes) * 60).toFixed(1))
          : undefined,
    };
  });

  return {
    plate: raw.plate_number,
    points,
    startedAt: points[0]?.timestamp,
    endedAt: points[points.length - 1]?.timestamp,
    totalDistanceKm: Number(points.reduce((s, p) => s + (p.distanceKm ?? 0), 0).toFixed(2)),
    camerasTouched: new Set(points.map((p) => p.cameraId)).size,
  };
}

/** Profile composed from real sightings + watchlist state (no extra endpoint). */
export function profileFromEvents(
  plate: string,
  events: VehicleEvent[],
  watchlist?: WatchlistRecord | null,
): VehicleProfile | null {
  if (!events.length) return null;
  const sorted = [...events].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
  );
  const first = sorted[0];
  const withClass = sorted.find((e) => e.vehicleClass && e.vehicleClass !== 'UNKNOWN');
  return {
    plate,
    vehicleClass: withClass?.vehicleClass ?? first.vehicleClass ?? 'UNKNOWN',
    colour: first.colour,
    registrationState: plate.startsWith('GJ') ? 'Gujarat' : 'Other State',
    firstSeen: first.timestamp,
    lastSeen: sorted[sorted.length - 1].timestamp,
    totalSightings: events.length,
    watchlist: watchlist ?? null,
  };
}
