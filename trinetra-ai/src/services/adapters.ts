/**
 * Backend DTO -> domain model adapters.
 *
 * The FastAPI backend speaks snake_case and wraps collections in
 * `{ data: [...] }` / `{ items, total, page, size, pages }` envelopes.
 * The UI speaks the camelCase domain types in `@/types`.
 *
 * This module is the ONLY place that knows about that difference, so:
 *   - components never touch a raw DTO,
 *   - LIVE mode and DEMO mode hand the UI identically-shaped objects,
 *   - a backend field rename breaks one file, not thirty components.
 *
 * Rule: adapters never invent data. A value the backend did not send comes
 * back `undefined` and the UI renders its own "—"/empty state, so LIVE mode
 * can never display a fabricated plate, confidence or location.
 */
import type {
  Alert,
  AlertStatus,
  Camera,
  CameraStatus,
  RoutePoint,
  Severity,
  StreamType,
  VehicleClass,
  VehicleEvent,
  VehicleRoute,
  WatchlistCategory,
  WatchlistRecord,
} from '@/types';
import { haversineKm, minutesBetween } from '@/lib/utils';
import { config } from '@/lib/config';

/* ------------------------------- envelopes ------------------------------- */

export interface Envelope<T> {
  data?: T[];
  items?: T[];
  total?: number;
  page?: number;
  size?: number;
  pages?: number;
}

/** Unwrap `{data:[…]}` / `{items:[…]}` / a bare array into a plain array. */
export function unwrapList<T>(payload: unknown): T[] {
  if (Array.isArray(payload)) return payload as T[];
  if (payload && typeof payload === 'object') {
    const e = payload as Envelope<T>;
    if (Array.isArray(e.data)) return e.data;
    if (Array.isArray(e.items)) return e.items;
  }
  return [];
}

/* -------------------------------- helpers -------------------------------- */

/**
 * The backend stores naive UTC datetimes (no trailing `Z`). Parsing those in
 * the browser would silently shift every timestamp by the local offset, which
 * would corrupt the chronological cross-camera trace. Normalise to real ISO.
 */
export function toIso(value?: string | null): string | undefined {
  if (!value) return undefined;
  const hasZone = /(Z|[+-]\d{2}:?\d{2})$/.test(value);
  const iso = hasZone ? value : `${value}Z`;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? undefined : d.toISOString();
}

const num = (v: unknown): number | undefined =>
  typeof v === 'number' && Number.isFinite(v) ? v : undefined;

function upper(v?: string | null): string | undefined {
  return v ? v.trim().toUpperCase() : undefined;
}

const CAMERA_STATUSES: CameraStatus[] = ['ONLINE', 'OFFLINE', 'DEGRADED'];

/** Map backend stream states onto the three states the UI knows about. */
export function toCameraStatus(raw?: string | null): CameraStatus {
  const s = upper(raw);
  if (!s) return 'OFFLINE';
  if (CAMERA_STATUSES.includes(s as CameraStatus)) return s as CameraStatus;
  if (s === 'CONNECTING' || s === 'RECONNECTING' || s === 'DEMO') return 'DEGRADED';
  return 'OFFLINE'; // ERROR / STOPPED / anything unknown
}

const SEVERITIES: Severity[] = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'];
function toSeverity(raw?: string | null, fallback: Severity = 'MEDIUM'): Severity {
  const s = upper(raw);
  return s && SEVERITIES.includes(s as Severity) ? (s as Severity) : fallback;
}

const ALERT_STATUSES: AlertStatus[] = ['NEW', 'ACKNOWLEDGED', 'RESOLVED'];
function toAlertStatus(raw?: string | null): AlertStatus {
  const s = upper(raw);
  if (s && ALERT_STATUSES.includes(s as AlertStatus)) return s as AlertStatus;
  if (s === 'ACTIVE' || s === 'OPEN') return 'NEW';
  return 'NEW';
}

const VEHICLE_CLASSES: VehicleClass[] = [
  'CAR',
  'MOTORCYCLE',
  'TRUCK',
  'BUS',
  'AUTO_RICKSHAW',
  'VAN',
  'UNKNOWN',
];
function toVehicleClass(raw?: string | null): VehicleClass | undefined {
  if (!raw) return undefined;
  const s = raw.trim().toUpperCase().replace(/[\s-]+/g, '_');
  return VEHICLE_CLASSES.includes(s as VehicleClass) ? (s as VehicleClass) : 'UNKNOWN';
}

const WATCHLIST_CATEGORIES: WatchlistCategory[] = [
  'STOLEN VEHICLE',
  'WANTED SUSPECT',
  'BLACKLISTED',
  'EXPIRED PERMIT',
  'PERSON OF INTEREST',
  'AMBER ALERT',
];
function toWatchlistCategory(raw?: string | null): WatchlistCategory {
  const s = raw ? raw.trim().toUpperCase() : '';
  return (WATCHLIST_CATEGORIES.includes(s as WatchlistCategory)
    ? s
    : 'BLACKLISTED') as WatchlistCategory;
}

/** Watchlist category -> operational severity. Keeps alerts and the watchlist consistent. */
export function severityForCategory(category: WatchlistCategory): Severity {
  switch (category) {
    case 'STOLEN VEHICLE':
    case 'AMBER ALERT':
      return 'CRITICAL';
    case 'WANTED SUSPECT':
      return 'HIGH';
    case 'PERSON OF INTEREST':
    case 'BLACKLISTED':
      return 'MEDIUM';
    default:
      return 'LOW';
  }
}

/* -------------------------------- camera --------------------------------- */

export interface CameraDto {
  id?: string;
  camera_id?: string;
  name?: string;
  location?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  department?: string | null;
  status?: string;
  codec?: string | null;
  width?: number | null;
  height?: number | null;
  stream_type?: string | null;
  stream_url?: string | null;
  last_seen?: string | null;
  is_demo_feed?: boolean;
  last_error?: string | null;
}

export function toCamera(dto: CameraDto): Camera {
  const id = dto.camera_id ?? dto.id ?? '';
  return {
    // The UI keys everything off the canonical upper-case registry ID (CAM04),
    // which is also what vehicle events reference.
    id: id.toUpperCase(),
    name: dto.name ?? id.toUpperCase(),
    location: dto.location ?? dto.name ?? '—',
    latitude: num(dto.latitude) ?? 0,
    longitude: num(dto.longitude) ?? 0,
    department: dto.department ?? undefined,
    status: toCameraStatus(dto.status),
    codec: dto.codec ?? undefined,
    width: num(dto.width),
    height: num(dto.height),
    streamType: (upper(dto.stream_type) as StreamType) ?? undefined,
    lastSeen: toIso(dto.last_seen),
    isDemoFeed: dto.is_demo_feed === true,
    lastError: dto.last_error ?? undefined,
  };
}

/* --------------------------------- event --------------------------------- */

export interface VehicleEventDto {
  id?: number | string;
  camera_id?: string;
  vehicle_track_id?: number | null;
  plate_raw?: string | null;
  plate_number?: string | null;
  plate_confidence?: number | null;
  vehicle_class?: string | null;
  event_time?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  evidence_ref?: string | null;
  watchlist_match?: boolean | null;
  created_at?: string | null;
}

/**
 * Real evidence URL for a backend `evidence_ref`.
 *
 * Points at our own API, so the browser never talks to the CV host directly
 * and no credential is involved. Returns undefined when the event carries no
 * reference — the UI then shows "Frame not retained" rather than a broken image.
 */
export function evidenceUrl(
  ref: string | undefined,
  variant: 'frame' | 'plate' = 'frame',
): string | undefined {
  if (!ref) return undefined;
  return `${config.apiBaseUrl}/evidence?ref=${encodeURIComponent(ref)}&variant=${variant}`;
}

export function toVehicleEvent(dto: VehicleEventDto): VehicleEvent {
  const plate = dto.plate_number ?? '';
  const watchlistMatch = dto.watchlist_match === true;
  const evidenceRef = dto.evidence_ref ?? undefined;
  const timestamp =
    toIso(dto.event_time) ?? toIso(dto.created_at) ?? new Date(0).toISOString();
  return {
    id: String(dto.id ?? ''),
    cameraId: (dto.camera_id ?? '').toUpperCase(),
    vehicleId: num(dto.vehicle_track_id),
    // No plate read -> em dash, never "undefined" or an invented value.
    plate: plate || '—',
    plateConfidence: num(dto.plate_confidence) ?? 0,
    timestamp,
    latitude: num(dto.latitude) ?? 0,
    longitude: num(dto.longitude) ?? 0,
    vehicleClass: toVehicleClass(dto.vehicle_class),
    eventType: watchlistMatch ? 'WATCHLIST_MATCH' : plate ? 'ANPR_READ' : 'VEHICLE_DETECTION',
    severity: watchlistMatch ? 'CRITICAL' : 'INFO',
    evidenceRef,
    // Real CV evidence: never flagged synthetic, so the UI shows no demo badge.
    evidence: evidenceRef
      ? {
          ref: evidenceRef,
          frameUrl: evidenceUrl(evidenceRef, 'frame'),
          plateCropUrl: evidenceUrl(evidenceRef, 'plate'),
          capturedAt: timestamp,
          synthetic: false,
        }
      : undefined,
    watchlistMatch,
  };
}

/** A coordinate the backend never actually supplied (null -> 0,0 in the DTO). */
export function hasPosition(lat?: number, lng?: number): boolean {
  return Boolean(lat && lng);
}

/**
 * Attach registry metadata (camera display name + location) to events.
 * The backend event row only stores `camera_id`, so the camera registry stays
 * the single source of truth for names and locations (spec Phase 3 / 39).
 *
 * Events ingested without coordinates inherit the camera's surveyed position
 * rather than plotting at 0,0 in the Atlantic (spec Phase 28 / 33).
 */
export function withCameraContext<T extends { cameraId: string; latitude?: number; longitude?: number }>(
  rows: T[],
  cameras: Map<string, Camera>,
): Array<T & { cameraName?: string; location?: string }> {
  return rows.map((r) => {
    const cam = cameras.get(r.cameraId.toUpperCase());
    const useCameraPos = !hasPosition(r.latitude, r.longitude) && cam;
    return {
      ...r,
      cameraName: cam?.name,
      location: cam?.location,
      ...(useCameraPos ? { latitude: cam.latitude, longitude: cam.longitude } : {}),
    };
  });
}

/* --------------------------------- alert --------------------------------- */

export interface AlertDto {
  id?: number | string;
  event_id?: number | string | null;
  watchlist_id?: number | string | null;
  camera_id?: string;
  track_id?: number | null;
  plate_number?: string | null;
  alert_type?: string | null;
  severity?: string | null;
  message?: string | null;
  status?: string | null;
  confidence?: number | null;
  timestamp?: string | null;
  acknowledged_at?: string | null;
  acknowledged_by?: string | null;
  resolved_at?: string | null;
  resolved_by?: string | null;
}

export function toAlert(dto: AlertDto, cameras?: Map<string, Camera>): Alert {
  const cameraId = (dto.camera_id ?? '').toUpperCase();
  const cam = cameras?.get(cameraId);
  return {
    id: String(dto.id ?? ''),
    eventId: dto.event_id != null ? String(dto.event_id) : '',
    plate: dto.plate_number ?? '—',
    cameraId,
    cameraName: cam?.name,
    location: cam?.location ?? '—',
    latitude: cam?.latitude,
    longitude: cam?.longitude,
    severity: toSeverity(dto.severity, 'HIGH'),
    status: toAlertStatus(dto.status),
    category: dto.alert_type ?? 'ALERT',
    createdAt: toIso(dto.timestamp) ?? new Date(0).toISOString(),
    confidence: num(dto.confidence),
    acknowledgedBy: dto.acknowledged_by ?? undefined,
    acknowledgedAt: toIso(dto.acknowledged_at),
    resolvedAt: toIso(dto.resolved_at),
    note: dto.message ?? undefined,
  };
}

/* ------------------------------- watchlist -------------------------------- */

export interface WatchlistDto {
  id?: number | string;
  plate_number?: string;
  category?: string | null;
  description?: string | null;
  active?: boolean;
  created_at?: string | null;
}

export function toWatchlistRecord(dto: WatchlistDto): WatchlistRecord {
  const category = toWatchlistCategory(dto.category);
  return {
    id: String(dto.id ?? ''),
    plate: (dto.plate_number ?? '').toUpperCase(),
    category,
    severity: severityForCategory(category),
    reason: dto.description ?? '—',
    caseRef: '—',
    addedBy: 'System',
    addedAt: toIso(dto.created_at) ?? new Date(0).toISOString(),
    active: dto.active !== false,
  };
}

/* --------------------------------- route ---------------------------------- */

export interface RouteDto {
  plate_number?: string;
  total_sightings?: number;
  route?: Array<{
    sequence?: number;
    camera_id?: string;
    event_time?: string;
    latitude?: number | null;
    longitude?: number | null;
    confidence?: number | null;
    event_id?: number | string | null;
  }>;
}

/**
 * Build the chronological cross-camera route.
 *
 * `distanceKm` is straight-line between consecutive CCTV sightings — this is an
 * OBSERVED DETECTION SEQUENCE, not a guaranteed road path (spec Phase 14), so
 * we never synthesise road geometry here.
 */
export function toVehicleRoute(dto: RouteDto, cameras?: Map<string, Camera>): VehicleRoute {
  const raw = [...(dto.route ?? [])].sort((a, b) => {
    const ta = new Date(toIso(a.event_time) ?? 0).getTime();
    const tb = new Date(toIso(b.event_time) ?? 0).getTime();
    return ta - tb || (a.sequence ?? 0) - (b.sequence ?? 0);
  });

  const points: RoutePoint[] = raw.map((p, i) => {
    const cameraId = (p.camera_id ?? '').toUpperCase();
    const cam = cameras?.get(cameraId);
    const latitude = num(p.latitude) ?? cam?.latitude ?? 0;
    const longitude = num(p.longitude) ?? cam?.longitude ?? 0;
    const timestamp = toIso(p.event_time) ?? new Date(0).toISOString();

    const prev = raw[i - 1];
    const prevTime = prev ? toIso(prev.event_time) : undefined;
    const gapMinutes = prevTime ? minutesBetween(prevTime, timestamp) : undefined;
    const distanceKm =
      prev != null
        ? haversineKm(
            {
              latitude: num(prev.latitude) ?? cameras?.get((prev.camera_id ?? '').toUpperCase())?.latitude ?? 0,
              longitude: num(prev.longitude) ?? cameras?.get((prev.camera_id ?? '').toUpperCase())?.longitude ?? 0,
            },
            { latitude, longitude },
          )
        : undefined;

    return {
      sequence: i + 1,
      eventId: p.event_id != null ? String(p.event_id) : '',
      cameraId,
      cameraName: cam?.name ?? cameraId,
      location: cam?.location ?? '—',
      latitude,
      longitude,
      timestamp,
      plateConfidence: num(p.confidence) ?? 0,
      gapMinutes,
      distanceKm,
      speedKmph:
        gapMinutes && distanceKm && gapMinutes > 0
          ? Number(((distanceKm / gapMinutes) * 60).toFixed(1))
          : undefined,
    };
  });

  return {
    plate: (dto.plate_number ?? '').toUpperCase(),
    points,
    startedAt: points[0]?.timestamp,
    endedAt: points[points.length - 1]?.timestamp,
    totalDistanceKm: Number(points.reduce((s, p) => s + (p.distanceKm ?? 0), 0).toFixed(2)),
    camerasTouched: new Set(points.map((p) => p.cameraId)).size,
  };
}
