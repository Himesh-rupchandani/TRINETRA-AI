/**
 * BACKEND ADAPTERS
 * ----------------
 * Single translation point between the FastAPI backend contract
 * (snake_case DTOs: camera_id, plate_number, event_time, …) and the
 * frontend domain types (camelCase). LIVE mode must never leak raw DTO
 * shapes into components — everything flows through here so every screen
 * shows the same canonical Camera / VehicleEvent / Alert objects.
 */
import type {
  Alert,
  ServiceHealth,
  AlertStatus,
  Camera,
  CameraStreamTicket,
  DashboardKpis,
  Paginated,
  RoutePoint,
  Severity,
  SystemSummary,
  VehicleClass,
  VehicleEvent,
  VehicleProfile,
  VehicleRoute,
  WatchlistRecord,
} from '@/types';
import { get } from './api';
import { config } from '@/lib/config';
import { haversineKm, minutesBetween } from '@/lib/utils';

/* ------------------------------ raw DTO types ------------------------------ */
/* Kept local + permissive: the backend owns the wire format, we only read it. */

export interface CameraItemDto {
  id?: string;
  camera_id?: string;
  name: string;
  location?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  /** Owning agency + operational zone, served by the CCTV Registry (Model 1). */
  department?: string | null;
  zone?: string | null;
  status?: string;
  codec?: string | null;
  width?: number | null;
  height?: number | null;
  fps?: number | null;
  stream_type?: string;
  stream_url?: string;
  last_seen?: string | null;
}

export interface VehicleEventDto {
  id: number;
  camera_id: string;
  vehicle_track_id?: number | null;
  plate_raw?: string | null;
  plate_number?: string | null;
  plate_confidence?: number | null;
  vehicle_class?: string | null;
  event_time: string;
  latitude?: number | null;
  longitude?: number | null;
  evidence_ref?: string | null;
  watchlist_match?: boolean;
  created_at?: string;
}

export interface AlertDto {
  id: number;
  event_id?: number | null;
  camera_id: string;
  plate_number?: string | null;
  alert_type: string;
  severity: string;
  message: string;
  status: string;
  confidence?: number | null;
  timestamp: string;
  acknowledged_at?: string | null;
  acknowledged_by?: string | null;
  resolved_at?: string | null;
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
    event_id?: number | null;
    event_time: string;
    latitude?: number | null;
    longitude?: number | null;
    confidence?: number | null;
  }>;
}

export interface ProfileDto {
  plate_number: string;
  vehicle_class?: string | null;
  first_seen?: string | null;
  last_seen?: string | null;
  total_sightings: number;
  cameras_touched: number;
  watchlist?: WatchlistDto | null;
}

interface PaginatedDto<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
  pages?: number;
}

export interface HealthDto {
  status: string;
  version?: string;
  environment?: string;
  database_connected?: boolean;
  total_cameras?: number;
  active_cameras?: number;
  demo_mode?: boolean;
  timestamp: string;
  components?: Record<string, string>;
}

export interface KpiDto {
  total_cameras: number;
  cameras_online: number;
  cameras_degraded: number;
  cameras_offline: number;
  active_alerts: number;
  vehicle_detections_24h: number;
  anpr_reads_24h: number;
  watchlist_matches_24h: number;
}

export interface StreamTicketDto {
  camera_id: string;
  stream_type: string;
  stream_url: string;
  expires_at: string;
  playable?: boolean;
  reason?: string | null;
}

/* --------------------------- camera directory ------------------------------ */
/**
 * One shared, cached index of the canonical Camera registry. Used to enrich
 * events/alerts/routes with camera names + locations so every screen agrees
 * (Phase 39: one source of truth for camera metadata).
 */
export interface CameraMeta {
  id: string;
  name: string;
  location: string;
  latitude: number;
  longitude: number;
}

let directoryPromise: Promise<Map<string, CameraMeta>> | null = null;

async function loadDirectory(): Promise<Map<string, CameraMeta>> {
  const list = await get<CameraItemDto[] | { data?: CameraItemDto[] }>('/cameras').then(
    (r) => (Array.isArray(r) ? r : (r?.data ?? [])),
  );
  const map = new Map<string, CameraMeta>();
  list.forEach((dto) => {
    const cam = toCamera(dto);
    map.set(cam.id, {
      id: cam.id,
      name: cam.name,
      location: cam.location,
      latitude: cam.latitude,
      longitude: cam.longitude,
    });
  });
  return map;
}

/** Await the shared camera directory (fetched at most once per session). */
export function cameraDirectory(): Promise<Map<string, CameraMeta>> {
  directoryPromise ??= loadDirectory().catch((e) => {
    directoryPromise = null; // allow a retry on the next call
    throw e;
  });
  return directoryPromise;
}

function metaFor(dir: Map<string, CameraMeta> | null | undefined, cameraId: string): CameraMeta | undefined {
  return dir?.get(cameraId.toLowerCase());
}

/* -------------------------------- converters ------------------------------- */

function asCameraStatus(raw?: string): Camera['status'] {
  const s = (raw ?? 'OFFLINE').toUpperCase();
  if (s === 'ONLINE') return 'ONLINE';
  if (s === 'DEGRADED') return 'DEGRADED';
  return 'OFFLINE';
}

function asSeverity(raw?: string | null): Severity {
  const s = (raw ?? 'INFO').toUpperCase();
  return (['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'] as const).includes(s as Severity)
    ? (s as Severity)
    : 'INFO';
}

function asAlertStatus(raw?: string): AlertStatus {
  const s = (raw ?? 'NEW').toUpperCase();
  if (s === 'ACKNOWLEDGED') return 'ACKNOWLEDGED';
  if (s === 'RESOLVED') return 'RESOLVED';
  return 'NEW';
}

const CLASS_MAP: Record<string, VehicleClass> = {
  CAR: 'CAR',
  MOTORCYCLE: 'MOTORCYCLE',
  BIKE: 'MOTORCYCLE',
  TRUCK: 'TRUCK',
  BUS: 'BUS',
  AUTO_RICKSHAW: 'AUTO_RICKSHAW',
  AUTO: 'AUTO_RICKSHAW',
  VAN: 'VAN',
};

function asVehicleClass(raw?: string | null): VehicleClass {
  return CLASS_MAP[(raw ?? '').toUpperCase()] ?? 'UNKNOWN';
}

/** Backend confidences are 0.0–1.0; the UI renders percentages. */
function pct(conf?: number | null): number {
  if (conf == null || Number.isNaN(conf)) return 0;
  return Math.round(Math.min(Math.max(conf, 0), 1) * 1000) / 10;
}

/* ------------------------------ evidence crops ----------------------------- */
/**
 * Same-origin path the backend serves captured crops from
 * (`GET /api/evidence/{ref}` → the CV engine's EvidenceWriter output). Built
 * from the configured API base so a deployment that points the UI at an
 * absolute API origin still resolves its imagery.
 */
export const EVIDENCE_BASE = `${config.apiBaseUrl.replace(/\/+$/, '')}/evidence`;

const PLATE_CROP_SUFFIX = /_plate\.(jpe?g|png)$/i;
const IMAGE_SUFFIX = /\.(jpe?g|png)$/i;

/**
 * Real crop URLs behind one `evidence_ref`.
 *
 * The CV engine stores `<stem>.jpg` (full frame) and `<stem>_plate.jpg` (the
 * ANPR crop). When full-frame capture is disabled it returns the *crop* as the
 * reference, so a ref that already ends in `_plate.*` is the plate crop — it
 * must not be suffixed a second time (`_plate_plate.jpg` would 404) and must
 * not be presented as a full frame.
 */
export function evidenceCropUrls(ref: string): { frameUrl?: string; plateCropUrl?: string } {
  const clean = ref.replace(/^\/+/, '');
  const url = `${EVIDENCE_BASE}/${clean}`;
  if (PLATE_CROP_SUFFIX.test(clean)) return { plateCropUrl: url };
  return {
    frameUrl: url,
    plateCropUrl: `${EVIDENCE_BASE}/${clean.replace(IMAGE_SUFFIX, '_plate.$1')}`,
  };
}

export function toCamera(dto: CameraItemDto): Camera {
  return {
    id: (dto.id ?? dto.camera_id ?? '').toLowerCase(),
    name: dto.name ?? dto.camera_id ?? 'Unknown camera',
    location: dto.location ?? dto.name ?? '—',
    latitude: dto.latitude ?? 0,
    longitude: dto.longitude ?? 0,
    department: dto.department ?? undefined,
    zone: dto.zone ?? undefined,
    status: asCameraStatus(dto.status),
    codec: dto.codec ?? undefined,
    width: dto.width ?? undefined,
    height: dto.height ?? undefined,
    fps: dto.fps ?? undefined,
    streamType: (dto.stream_type?.toUpperCase() as Camera['streamType']) ?? undefined,
    streamUrl: dto.stream_url,
    lastSeen: dto.last_seen ?? undefined,
  };
}

export function toVehicleEvent(
  dto: VehicleEventDto,
  dir?: Map<string, CameraMeta> | null,): VehicleEvent {
  const cameraId = dto.camera_id.toLowerCase();
  const meta = metaFor(dir, cameraId);
  const matched = Boolean(dto.watchlist_match);
  const evidenceRef = dto.evidence_ref ?? undefined;
  const plate = dto.plate_number ?? dto.plate_raw ?? undefined;
  return {
    id: String(dto.id),
    cameraId,
    cameraName: meta?.name ?? dto.camera_id.toUpperCase(),
    vehicleId: dto.vehicle_track_id ?? undefined,
    plate: plate ?? '',
    plateConfidence: pct(dto.plate_confidence),
    timestamp: dto.event_time,
    latitude: dto.latitude ?? meta?.latitude ?? 0,
    longitude: dto.longitude ?? meta?.longitude ?? 0,
    location: meta?.location ?? '—',
    vehicleClass: asVehicleClass(dto.vehicle_class),
    eventType: matched ? 'WATCHLIST_MATCH' : plate ? 'ANPR_READ' : 'VEHICLE_DETECTION',
    severity: matched ? 'CRITICAL' : 'INFO',
    evidenceRef,
    evidence: evidenceRef
      ? {
          ref: evidenceRef,
          // Real crops captured by the CV engine's evidence writer and served
          // by the backend. The derived plate crop is only requested when a
          // plate was actually read — the writer never stores one otherwise.
          ...(plate ? evidenceCropUrls(evidenceRef) : { frameUrl: `${EVIDENCE_BASE}/${evidenceRef.replace(/^\/+/, '')}` }),
          capturedAt: dto.event_time,
        }
      : undefined,
    watchlistMatch: matched,
  };
}

export function toAlert(
  dto: AlertDto,
  dir?: Map<string, CameraMeta> | null,
): Alert {
  const cameraId = dto.camera_id.toLowerCase();
  const meta = metaFor(dir, cameraId);
  return {
    id: String(dto.id),
    eventId: dto.event_id != null ? String(dto.event_id) : '',
    plate: dto.plate_number ?? '',
    cameraId,
    cameraName: meta?.name ?? dto.camera_id.toUpperCase(),
    location: meta?.location ?? '—',
    latitude: meta?.latitude,
    longitude: meta?.longitude,
    severity: asSeverity(dto.severity),
    status: asAlertStatus(dto.status),
    category: dto.alert_type,
    createdAt: dto.timestamp,
    confidence: dto.confidence != null ? pct(dto.confidence) : undefined,
    acknowledgedBy: dto.acknowledged_by ?? undefined,
    acknowledgedAt: dto.acknowledged_at ?? undefined,
    resolvedAt: dto.resolved_at ?? undefined,
    note: dto.message,
  };
}

/**
 * Watchlist severity mirrors the backend alert engine's own mapping
 * (event_service.create_watchlist_alert) so the UI never invents a priority
 * the alert engine would not produce.
 */
const WATCHLIST_SEVERITY: Record<string, Severity> = {
  'STOLEN VEHICLE': 'CRITICAL',
  'WANTED SUSPECT': 'CRITICAL',
  'WANTED VEHICLE': 'CRITICAL',
  'SUSPICIOUS VEHICLE': 'HIGH',
};

export function toWatchlistRecord(dto: WatchlistDto): WatchlistRecord {
  const category = dto.category.toUpperCase();
  return {
    id: String(dto.id),
    plate: dto.plate_number,
    category: category as WatchlistRecord['category'],
    severity: WATCHLIST_SEVERITY[category] ?? 'HIGH',
    reason: dto.description ?? '',
    caseRef: `WL-${dto.id}`,
    addedBy: 'Registry',
    addedAt: dto.created_at,
    active: dto.active,
  };
}

export function toVehicleProfile(dto: ProfileDto): VehicleProfile {
  const wl = dto.watchlist ? toWatchlistRecord(dto.watchlist) : null;
  return {
    plate: dto.plate_number,
    vehicleClass: asVehicleClass(dto.vehicle_class),
    firstSeen: dto.first_seen ?? undefined,
    lastSeen: dto.last_seen ?? undefined,
    totalSightings: dto.total_sightings,
    camerasTouched: dto.cameras_touched,
    registrationState: dto.plate_number.startsWith('GJ') ? 'Gujarat' : 'Other State',
    watchlist: wl ?? null,
  };
}

export function toVehicleRoute(dto: RouteDto, dir?: Map<string, CameraMeta> | null): VehicleRoute {
  const points: RoutePoint[] = dto.route.map((p, i) => {
    const cameraId = p.camera_id.toLowerCase();
    const meta = metaFor(dir, cameraId);
    const latitude = p.latitude ?? meta?.latitude ?? 0;
    const longitude = p.longitude ?? meta?.longitude ?? 0;
    const prev = dto.route[i - 1];
    const gapMinutes = prev ? minutesBetween(prev.event_time, p.event_time) : undefined;
    const distanceKm =
      prev && prev.latitude != null && prev.longitude != null && p.latitude != null && p.longitude != null
        ? haversineKm(
            { latitude: prev.latitude, longitude: prev.longitude },
            { latitude, longitude },
          )
        : undefined;
    return {
      sequence: p.sequence,
      // Backend now carries the sighting id; leave correlation to the hook only
      // for older payloads that omit it.
      eventId: p.event_id != null ? String(p.event_id) : '',
      cameraId,
      cameraName: meta?.name ?? p.camera_id.toUpperCase(),
      location: meta?.location ?? '—',
      latitude,
      longitude,
      timestamp: p.event_time,
      plateConfidence: pct(p.confidence),
      gapMinutes,
      distanceKm,
      speedKmph:
        gapMinutes && distanceKm != null && gapMinutes > 0
          ? Math.round((distanceKm / gapMinutes) * 60)
          : undefined,
    };
  });

  const distance = points.reduce((sum, p) => sum + (p.distanceKm ?? 0), 0);
  return {
    plate: dto.plate_number,
    points,
    startedAt: points[0]?.timestamp,
    endedAt: points[points.length - 1]?.timestamp,
    totalDistanceKm: Math.round(distance * 10) / 10,
    camerasTouched: new Set(points.map((p) => p.cameraId)).size,
  };
}

export function toKpis(dto: KpiDto): DashboardKpis {
  return {
    totalCameras: dto.total_cameras,
    camerasOnline: dto.cameras_online,
    camerasDegraded: dto.cameras_degraded,
    camerasOffline: dto.cameras_offline,
    activeAlerts: dto.active_alerts,
    vehicleDetections24h: dto.vehicle_detections_24h,
    anprReads24h: dto.anpr_reads_24h,
    watchlistMatches24h: dto.watchlist_matches_24h,
  };
}

export function toStreamTicket(dto: StreamTicketDto): CameraStreamTicket {
  return {
    cameraId: dto.camera_id.toLowerCase(),
    streamType: dto.stream_type as CameraStreamTicket['streamType'],
    streamUrl: dto.stream_url,
    expiresAt: dto.expires_at,
    poster: undefined, // resolved by the player (synthetic/registry still)
  };
}

/**
 * Health → SystemSummary. Backend reports component states only; throughput
 * counters stay at 0 until a metrics source exists — never fabricated.
 */
const SERVICE_META: Record<string, { name: string; description: string }> = {
  api: { name: 'API Server', description: 'FastAPI control plane' },
  database: { name: 'PostgreSQL / SQLite', description: 'Event & registry store' },
  watchlist: { name: 'Watchlist Engine', description: 'Plate matching service' },
  event_ingestion: { name: 'Event Ingestion', description: 'CV → backend pipeline' },
  alert_engine: { name: 'Alert Engine', description: 'Dedup + fan-out' },
  sentinel_catalogue: { name: 'Camera Registry', description: 'Sentinel catalogue sync' },
  realtime_channel: { name: 'Realtime Channel', description: 'WebSocket + SSE stream' },
};

export function toSystemSummary(dto: HealthDto): SystemSummary {
  const now = new Date().toISOString();
  const services = Object.entries(dto.components ?? {}).map(([key, raw]) => {
    const meta = SERVICE_META[key] ?? { name: key, description: key.replace(/_/g, ' ') };
    const rawUpper = raw.toUpperCase();
    const status: ServiceHealth['status'] =
      rawUpper === 'HEALTHY' ? 'HEALTHY' : rawUpper === 'DEGRADED' ? 'DEGRADED' : 'OFFLINE';
    return {
      id: key,
      name: meta.name,
      description: meta.description,
      status,
      uptimePct: 0,
      uptimeSince: now,
      lastHeartbeat: dto.timestamp ?? now,
      activeConnections: 0,
      processingState: status === 'HEALTHY' ? ('PROCESSING' as const) : ('IDLE' as const),
      latestError: status === 'HEALTHY' ? null : `Component reported ${raw}`,
      version: dto.version,
    };
  });
  return {
    services,
    ingestFps: 0,
    eventsPerMinute: 0,
    anprPerMinute: 0,
    generatedAt: dto.timestamp ?? now,
  };
}

export function toPaginated<T, R>(dto: PaginatedDto<T>, map: (item: T) => R): Paginated<R> {
  return {
    items: (dto.items ?? []).map(map),
    total: dto.total ?? 0,
    page: dto.page ?? 1,
    pageSize: dto.size ?? (dto.items ?? []).length,
  };
}

/** Unwrap list-or-paginated responses defensively. */
export function unwrapItems<T>(r: T[] | PaginatedDto<T>): T[] {
  return Array.isArray(r) ? r : (r.items ?? []);
}
