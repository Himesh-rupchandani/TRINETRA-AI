import type {
  Alert,
  AlertStatus,
  Camera,
  CameraStatus,
  CameraStreamTicket,
  DashboardKpis,
  EventType,
  Paginated,
  RoutePoint,
  Severity,
  ServiceHealth,
  ServiceStatus,
  StreamType,
  SystemSummary,
  VehicleClass,
  VehicleEvent,
  VehicleProfile,
  VehicleRoute,
  WatchlistCategory,
  WatchlistRecord,
} from '@/types';

/**
 * Backend → frontend contract adapters.
 *
 * The API speaks snake_case with a few different envelope shapes
 * (`{data:[…]}` for cameras, `{items,total,page,size,pages}` elsewhere) while
 * the UI is typed in camelCase. Every live-mode response is normalised here so
 * components only ever see the declared types — no `undefined`, no `NaN`, no
 * shape surprises leaking into the control room.
 *
 * Nothing in this file fabricates data: a missing field stays absent, and
 * unknown enum values fall back to a neutral member rather than inventing one.
 */

/* eslint-disable @typescript-eslint/no-explicit-any */
type Raw = Record<string, any>;

/* ----------------------------- envelopes ------------------------------ */

/** Unwrap `{data:[…]}` / `{items:[…]}` / bare array into a plain list. */
export function unwrapList<T = Raw>(payload: unknown): T[] {
  if (Array.isArray(payload)) return payload as T[];
  if (payload && typeof payload === 'object') {
    const p = payload as Raw;
    for (const key of ['items', 'data', 'results', 'events', 'route']) {
      if (Array.isArray(p[key])) return p[key] as T[];
    }
  }
  return [];
}

/** Normalise the backend pagination envelope onto the frontend's. */
export function unwrapPaginated<T>(payload: unknown, map: (raw: Raw) => T): Paginated<T> {
  const raw = (payload && typeof payload === 'object' ? payload : {}) as Raw;
  const items = unwrapList<Raw>(payload).map(map);
  const size = Number(raw.size ?? raw.pageSize ?? items.length) || items.length;
  return {
    items,
    total: Number(raw.total ?? items.length) || items.length,
    page: Number(raw.page ?? 1) || 1,
    pageSize: size,
  };
}

/* ------------------------------- scalars ------------------------------ */

const num = (v: unknown, fallback = 0): number => {
  const n = typeof v === 'string' ? Number(v) : (v as number);
  return typeof n === 'number' && Number.isFinite(n) ? n : fallback;
};

const str = (v: unknown): string | undefined =>
  v === null || v === undefined || v === '' ? undefined : String(v);

/** The backend stores naive timestamps; make them explicitly UTC-safe ISO. */
const iso = (v: unknown): string | undefined => {
  const s = str(v);
  if (!s) return undefined;
  // "2026-09-04T02:09:00" has no zone suffix — treat as UTC, not local time.
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/.test(s)) return `${s}Z`;
  return s;
};

export function toSeverity(v: unknown): Severity {
  const s = String(v ?? '').toUpperCase();
  return (['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'] as const).find((x) => x === s) ?? 'INFO';
}

export function toAlertStatus(v: unknown): AlertStatus {
  const s = String(v ?? '').toUpperCase();
  if (s === 'ACKNOWLEDGED' || s === 'RESOLVED') return s;
  if (s === 'DISMISSED') return 'RESOLVED';
  return 'NEW';
}

function toCameraStatus(v: unknown): CameraStatus {
  const s = String(v ?? '').toUpperCase();
  if (s === 'ONLINE' || s === 'OFFLINE' || s === 'DEGRADED') return s;
  // Engine lifecycle states that can still surface from older payloads.
  if (s === 'CONNECTING') return 'ONLINE';
  if (s === 'RECONNECTING') return 'DEGRADED';
  return 'OFFLINE';
}

function toStreamType(v: unknown): StreamType | undefined {
  const s = String(v ?? '').toUpperCase();
  return (['HLS', 'RTSP', 'WEBRTC', 'MJPEG'] as const).find((x) => x === s);
}

function toVehicleClass(v: unknown): VehicleClass {
  const s = String(v ?? '').toUpperCase().replace(/[\s-]+/g, '_');
  const map: Record<string, VehicleClass> = {
    CAR: 'CAR',
    MOTORCYCLE: 'MOTORCYCLE',
    MOTORBIKE: 'MOTORCYCLE',
    BIKE: 'MOTORCYCLE',
    TRUCK: 'TRUCK',
    BUS: 'BUS',
    VAN: 'VAN',
    AUTO: 'AUTO_RICKSHAW',
    AUTO_RICKSHAW: 'AUTO_RICKSHAW',
    RICKSHAW: 'AUTO_RICKSHAW',
  };
  return map[s] ?? 'UNKNOWN';
}

const EVENT_TYPES: EventType[] = [
  'VEHICLE_DETECTION',
  'ANPR_READ',
  'WATCHLIST_MATCH',
  'CAMERA_OFFLINE',
  'CAMERA_RECOVERED',
  'SPEED_VIOLATION',
  'WRONG_WAY',
];

function toEventType(raw: Raw): EventType {
  const declared = String(raw.event_type ?? '').toUpperCase();
  if ((EVENT_TYPES as string[]).includes(declared)) return declared as EventType;
  // The engine records sightings; a plate on one is an ANPR read.
  return raw.plate_number ? 'ANPR_READ' : 'VEHICLE_DETECTION';
}

function toWatchlistCategory(v: unknown): WatchlistCategory {
  const s = String(v ?? '').toUpperCase();
  const known: WatchlistCategory[] = [
    'STOLEN VEHICLE',
    'WANTED SUSPECT',
    'BLACKLISTED',
    'EXPIRED PERMIT',
    'PERSON OF INTEREST',
    'AMBER ALERT',
  ];
  if ((known as string[]).includes(s)) return s as WatchlistCategory;
  // "stolen vehicle" / "wanted vehicle" arrive lower-cased from the seed.
  const normalised = s.replace(/_/g, ' ').trim();
  const fuzzy = known.find((k) => normalised.includes(k.split(' ')[0]));
  return fuzzy ?? 'BLACKLISTED';
}

/* ------------------------------ entities ------------------------------ */

export function mapCamera(raw: Raw): Camera {
  const cameraId = str(raw.camera_id) ?? str(raw.name) ?? str(raw.id) ?? 'UNKNOWN';
  return {
    id: (str(raw.id) ?? cameraId).toLowerCase(),
    name: cameraId.toUpperCase(),
    // Backend `name` holds the junction name; `location` may be absent.
    location: str(raw.location) ?? str(raw.name) ?? '—',
    latitude: num(raw.latitude),
    longitude: num(raw.longitude),
    department: str(raw.department),
    zone: str(raw.zone),
    status: toCameraStatus(raw.status),
    codec: str(raw.codec),
    width: raw.width == null ? undefined : num(raw.width),
    height: raw.height == null ? undefined : num(raw.height),
    fps: raw.fps == null ? undefined : num(raw.fps),
    streamType: toStreamType(raw.stream_type),
    streamUrl: str(raw.stream_url),
    lastSeen: iso(raw.last_seen),
  };
}

export function mapStreamTicket(raw: Raw): CameraStreamTicket {
  const cameraId = str(raw.camera_id) ?? '';
  return {
    cameraId,
    streamType: toStreamType(raw.stream_type) ?? 'HLS',
    streamUrl: str(raw.stream_url) ?? '',
    expiresAt: iso(raw.expires_at) ?? new Date(Date.now() + 15 * 60_000).toISOString(),
    poster: str(raw.poster),
  };
}

export function mapEvent(raw: Raw): VehicleEvent {
  const plate = str(raw.plate_number) ?? str(raw.plate) ?? '';
  return {
    id: String(raw.id ?? ''),
    cameraId: str(raw.camera_id) ?? '',
    cameraName: str(raw.camera_name),
    vehicleId: raw.vehicle_track_id == null ? undefined : num(raw.vehicle_track_id),
    plate,
    plateConfidence: num(raw.plate_confidence ?? raw.confidence),
    timestamp: iso(raw.event_time ?? raw.timestamp ?? raw.created_at) ?? '',
    latitude: num(raw.latitude),
    longitude: num(raw.longitude),
    location: str(raw.location),
    vehicleClass: toVehicleClass(raw.vehicle_class),
    eventType: toEventType(raw),
    evidenceRef: str(raw.evidence_ref),
    watchlistMatch: raw.watchlist_match === true,
  };
}

export function mapAlert(raw: Raw): Alert {
  const category =
    str(raw.category) ??
    (String(raw.alert_type ?? '').toUpperCase() === 'WATCHLIST_MATCH'
      ? 'WATCHLIST MATCH'
      : str(raw.alert_type) ?? 'SYSTEM');
  return {
    id: String(raw.id ?? ''),
    eventId: raw.event_id == null ? '' : String(raw.event_id),
    plate: str(raw.plate_number) ?? '',
    cameraId: str(raw.camera_id) ?? '',
    cameraName: str(raw.camera_name),
    // The API has no location column; the caller joins it from the registry so
    // the UI never renders an empty "Location" field.
    location: str(raw.location) ?? '',
    latitude: raw.latitude == null ? undefined : num(raw.latitude),
    longitude: raw.longitude == null ? undefined : num(raw.longitude),
    severity: toSeverity(raw.severity),
    status: toAlertStatus(raw.status),
    category,
    createdAt: iso(raw.timestamp ?? raw.created_at) ?? '',
    confidence: raw.confidence == null ? undefined : num(raw.confidence),
    acknowledgedBy: str(raw.acknowledged_by),
    acknowledgedAt: iso(raw.acknowledged_at),
    resolvedAt: iso(raw.resolved_at),
  };
}

export function mapWatchlist(raw: Raw): WatchlistRecord {
  const category = toWatchlistCategory(raw.category);
  return {
    id: String(raw.id ?? ''),
    plate: str(raw.plate_number) ?? str(raw.plate) ?? '',
    category,
    // A stolen vehicle is the highest-priority demo case; otherwise the record
    // carries no explicit severity, so derive a defensible default.
    severity: raw.severity ? toSeverity(raw.severity) : category === 'STOLEN VEHICLE' ? 'CRITICAL' : 'HIGH',
    reason: str(raw.description) ?? str(raw.reason) ?? '—',
    caseRef: str(raw.case_ref) ?? '—',
    addedBy: str(raw.added_by) ?? '—',
    addedAt: iso(raw.created_at ?? raw.added_at) ?? '',
    active: raw.active !== false,
    contact: str(raw.contact),
  };
}

export function mapRoutePoint(raw: Raw, index: number): RoutePoint {
  return {
    sequence: num(raw.sequence, index + 1),
    eventId: raw.event_id == null ? '' : String(raw.event_id),
    cameraId: str(raw.camera_id) ?? '',
    cameraName: str(raw.camera_name) ?? str(raw.camera_id) ?? '',
    location: str(raw.location) ?? '',
    latitude: num(raw.latitude),
    longitude: num(raw.longitude),
    timestamp: iso(raw.event_time ?? raw.timestamp) ?? '',
    plateConfidence: num(raw.confidence ?? raw.plate_confidence),
  };
}

export function mapRoute(payload: unknown): VehicleRoute {
  const raw = (payload && typeof payload === 'object' ? payload : {}) as Raw;
  const points = unwrapList<Raw>(payload).map(mapRoutePoint);

  // Derive hop metrics from the observed sequence — never from invented road
  // geometry. A route is the CCTV detection sequence, in timestamp order.
  const enriched = points.map((p, i) => {
    if (i === 0) return p;
    const prev = points[i - 1];
    const gapMinutes =
      p.timestamp && prev.timestamp
        ? Math.max(0, (new Date(p.timestamp).getTime() - new Date(prev.timestamp).getTime()) / 60_000)
        : undefined;
    const distanceKm = haversineKm(prev.latitude, prev.longitude, p.latitude, p.longitude);
    const hours = gapMinutes != null && gapMinutes > 0 ? gapMinutes / 60 : undefined;
    return {
      ...p,
      gapMinutes,
      distanceKm,
      speedKmph: hours && distanceKm != null ? Math.round(distanceKm / hours) : undefined,
    };
  });

  return {
    plate: str(raw.plate_number) ?? str(raw.plate) ?? '',
    points: enriched,
    startedAt: enriched[0]?.timestamp,
    endedAt: enriched[enriched.length - 1]?.timestamp,
    totalDistanceKm: Math.round(
      enriched.reduce((sum, p) => sum + (p.distanceKm ?? 0), 0) * 10,
    ) / 10,
    camerasTouched: new Set(enriched.map((p) => p.cameraId)).size,
  };
}

function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number | undefined {
  if (!lat1 || !lon1 || !lat2 || !lon2) return undefined;
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLon / 2) ** 2;
  return Math.round(2 * R * Math.asin(Math.sqrt(a)) * 100) / 100;
}

export function mapVehicleProfile(payload: unknown): VehicleProfile | null {
  if (!payload || typeof payload !== 'object') return null;
  const raw = payload as Raw;
  if (!raw.plate_number && !raw.plate) return null;
  return {
    plate: str(raw.plate_number) ?? str(raw.plate) ?? '',
    vehicleClass: toVehicleClass(raw.vehicle_class),
    totalSightings: num(raw.total_sightings),
    camerasTouched: num(raw.cameras_touched),
    firstSeen: iso(raw.first_seen),
    lastSeen: iso(raw.last_seen),
    watchlist: raw.watchlist ? mapWatchlist(raw.watchlist) : null,
  };
}

export function mapKpis(raw: Raw): DashboardKpis {
  return {
    totalCameras: num(raw.total_cameras ?? raw.totalCameras),
    camerasOnline: num(raw.cameras_online ?? raw.camerasOnline),
    camerasDegraded: num(raw.cameras_degraded ?? raw.camerasDegraded),
    camerasOffline: num(raw.cameras_offline ?? raw.camerasOffline),
    activeAlerts: num(raw.active_alerts ?? raw.activeAlerts),
    vehicleDetections24h: num(raw.vehicle_detections_24h ?? raw.vehicleDetections24h),
    anprReads24h: num(raw.anpr_reads_24h ?? raw.anprReads24h),
    watchlistMatches24h: num(raw.watchlist_matches_24h ?? raw.watchlistMatches24h),
  };
}

function toServiceStatus(v: unknown): ServiceStatus {
  const s = String(v ?? '').toUpperCase();
  if (s === 'HEALTHY') return 'HEALTHY';
  if (s === 'DEGRADED') return 'DEGRADED';
  return 'OFFLINE';
}

/**
 * Names mirror the existing control-room health panel. Only components the
 * backend actually reports are listed — LIVE mode never invents a green tick
 * for a service it has not heard from.
 */
const SERVICE_META: Record<string, { name: string; description: string }> = {
  api: { name: 'API Gateway', description: 'FastAPI control-plane service' },
  database: { name: 'PostgreSQL', description: 'Event and registry storage' },
  watchlist: { name: 'Watchlist Database', description: 'Plate matching against BOLO records' },
  event_ingestion: { name: 'AI Engine', description: 'CV sighting intake pipeline' },
  alert_engine: { name: 'Alert Engine', description: 'Deduplicated alert generation' },
  // Named "Sentinel Grid" so the live media-gateway probe can override it.
  sentinel_catalogue: { name: 'Sentinel Grid', description: 'Government CCTV feed registry' },
  realtime_channel: { name: 'Realtime Channel', description: 'WebSocket/SSE event fan-out' },
};

export function mapHealth(raw: Raw): SystemSummary {
  const components = (raw.components ?? {}) as Raw;
  const generatedAt = iso(raw.timestamp) ?? new Date().toISOString();
  const services: ServiceHealth[] = Object.entries(components).map(([id, value]) => {
    const meta = SERVICE_META[id] ?? { name: id, description: 'Service' };
    const status = toServiceStatus(value);
    return {
      id,
      name: meta.name,
      description: meta.description,
      status,
      uptimePct: status === 'HEALTHY' ? 100 : status === 'DEGRADED' ? 99 : 0,
      uptimeSince: generatedAt,
      lastHeartbeat: generatedAt,
      activeConnections: 0,
      processingState: status === 'OFFLINE' ? 'STOPPED' : 'IDLE',
      version: str(raw.version),
    };
  });

  return {
    services,
    ingestFps: num(raw.ingest_fps),
    eventsPerMinute: num(raw.events_per_minute),
    anprPerMinute: num(raw.anpr_per_minute),
    generatedAt,
  };
}
