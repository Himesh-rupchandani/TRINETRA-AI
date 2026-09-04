import type { Alert, Camera, VehicleEvent } from '@/types';
import { config } from '@/lib/config';
import { isMockMode, realtimeUrl } from './api';
import { cameraService } from './cameraService';
import { toCameraStatus, toIso } from './adapters';
import { mockCameras } from '@/mocks/cameras';
import { watchlistByPlate } from '@/mocks/watchlist';
import { pushMockEvent, setMockCameraStatus } from '@/mocks/mockBackend';
import { syntheticFrame, syntheticPlateCrop } from '@/utils/syntheticEvidence';

/* ------------------------------ message model ------------------------------ */

export type RealtimeMessage =
  | { type: 'EVENT'; payload: VehicleEvent }
  | { type: 'ALERT'; payload: Alert }
  | { type: 'CAMERA_STATUS'; payload: { cameraId: string; status: Camera['status'] } };

export type ConnectionState = 'CONNECTING' | 'LIVE' | 'OFFLINE' | 'SIMULATED';

export interface RealtimeChannel {
  close(): void;
}

type Handler = (msg: RealtimeMessage) => void;
type StateHandler = (state: ConnectionState) => void;

/* --------------------------- mock event simulator --------------------------- */

const RTO = ['GJ01', 'GJ03', 'GJ05', 'GJ06', 'GJ09', 'GJ12', 'GJ16', 'GJ18', 'GJ21', 'GJ27'];
const LETTERS = 'ABCDEFGHJKLMNPQRSTUVWXYZ';
const CLASSES: NonNullable<VehicleEvent['vehicleClass']>[] = [
  'CAR',
  'CAR',
  'MOTORCYCLE',
  'AUTO_RICKSHAW',
  'TRUCK',
  'VAN',
  'BUS',
];
const WATCH_PLATES = ['GJ01AB1234', 'GJ05XY4321', 'GJ27CJ7788', 'GJ12PQ8899', 'GJ16TU9090'];

const rnd = <T,>(a: T[]): T => a[Math.floor(Math.random() * a.length)];
const randomPlate = () =>
  `${rnd(RTO)}${rnd([...LETTERS])}${rnd([...LETTERS])}${Math.floor(1000 + Math.random() * 9000)}`;

let seq = 0;

function makeEvent(): { event: VehicleEvent; alert?: Alert } {
  const cam = rnd(mockCameras.filter((c) => c.status === 'ONLINE'));
  const isWatch = Math.random() > 0.82;
  const plate = isWatch ? rnd(WATCH_PLATES) : randomPlate();
  const wl = isWatch ? watchlistByPlate(plate) : undefined;
  const confidence = Number((82 + Math.random() * 17).toFixed(1));
  const now = new Date().toISOString();
  const id = `evt-live-${Date.now()}-${seq++}`;
  const vehicleClass = rnd(CLASSES);
  const ref = `ev/${cam.id}/${id}`;

  const event: VehicleEvent = {
    id,
    cameraId: cam.id,
    cameraName: cam.name,
    plate,
    plateConfidence: confidence,
    timestamp: now,
    latitude: cam.latitude,
    longitude: cam.longitude,
    location: cam.location,
    vehicleClass,
    eventType: wl?.active ? 'WATCHLIST_MATCH' : 'ANPR_READ',
    severity: wl?.active ? wl.severity : 'INFO',
    watchlistMatch: Boolean(wl?.active),
    speedKmph: Math.round(20 + Math.random() * 45),
    evidenceRef: ref,
    evidence: {
      ref,
      capturedAt: now,
      synthetic: true,
      frameUrl: syntheticFrame({
        cameraName: cam.name,
        location: cam.location,
        plate,
        timestamp: now,
        vehicleClass,
      }),
      plateCropUrl: syntheticPlateCrop(plate, confidence),
    },
  };

  const alert: Alert | undefined = wl?.active
    ? {
        id: `alr-live-${Date.now()}`,
        eventId: id,
        plate,
        cameraId: cam.id,
        cameraName: cam.name,
        location: cam.location,
        latitude: cam.latitude,
        longitude: cam.longitude,
        severity: wl.severity,
        status: 'NEW',
        category: wl.category,
        createdAt: now,
        confidence,
        evidenceRef: ref,
      }
    : undefined;

  return { event, alert };
}

/**
 * Mock realtime source. Emits detections on a jittered interval and
 * occasionally flips a camera offline/online, mirroring what the WebSocket
 * or SSE channel will deliver once the backend is live.
 */
function connectSimulator(onMessage: Handler, onState: StateHandler): RealtimeChannel {
  onState('SIMULATED');
  let timer: number;

  const tick = () => {
    const roll = Math.random();
    if (roll > 0.94) {
      const cam = rnd(mockCameras);
      const status: Camera['status'] = Math.random() > 0.5 ? 'OFFLINE' : 'ONLINE';
      setMockCameraStatus(cam.id, status);
      onMessage({ type: 'CAMERA_STATUS', payload: { cameraId: cam.id, status } });
    } else {
      const { event, alert } = makeEvent();
      pushMockEvent(event, alert);
      onMessage({ type: 'EVENT', payload: event });
      if (alert) onMessage({ type: 'ALERT', payload: alert });
    }
    timer = window.setTimeout(tick, 3200 + Math.random() * 3800);
  };

  timer = window.setTimeout(tick, 2200);
  return { close: () => window.clearTimeout(timer) };
}

/* ------------------------------- SSE / WS ------------------------------- */

/**
 * Wire contract published by the backend WebSocket
 * (`WS /api/ws/events`, see app/api/websocket.py):
 *
 *   { type: "VEHICLE_DETECTED" | "WATCHLIST_MATCH" | "ALERT_CREATED"
 *           | "CAMERA_STATUS_CHANGED" | "CONNECTED" | "PONG",
 *     timestamp: ISO8601,
 *     payload: {...}, data: {...} }
 *
 * Translating it here keeps the message model the UI consumes stable, and is
 * the only place that knows the backend's event names.
 */
interface WirePayload {
  event_id?: number | string;
  alert_id?: number | string;
  id?: number | string;
  camera_id?: string;
  plate?: string | null;
  plate_number?: string | null;
  vehicle_class?: string | null;
  confidence?: number | null;
  severity?: string | null;
  message?: string | null;
  event_time?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  watchlist_match?: boolean | null;
  status?: string | null;
}

interface WireMessage {
  type?: string;
  timestamp?: string;
  payload?: WirePayload;
  data?: WirePayload;
}

/**
 * Translate one backend frame into zero or more UI messages.
 * Camera metadata (name/location) is resolved from the registry cache, so a
 * live event never displays a fabricated location.
 */
function translate(raw: WireMessage, cameras: Map<string, Camera>): RealtimeMessage[] {
  const type = (raw.type ?? '').toUpperCase();
  const d = raw.payload ?? raw.data;
  if (!d) return [];

  if (type === 'CONNECTED' || type === 'PONG') return [];

  const cameraId = (d.camera_id ?? '').toUpperCase();
  const cam = cameras.get(cameraId);

  if (type === 'CAMERA_STATUS_CHANGED') {
    return [
      {
        type: 'CAMERA_STATUS',
        payload: { cameraId, status: toCameraStatus(d.status) },
      },
    ];
  }

  if (!['VEHICLE_DETECTED', 'WATCHLIST_MATCH', 'ALERT_CREATED'].includes(type)) return [];

  const timestamp = toIso(d.event_time) ?? toIso(raw.timestamp) ?? new Date().toISOString();
  const plate = d.plate ?? d.plate_number ?? '';
  const watchlistMatch = d.watchlist_match === true || type !== 'VEHICLE_DETECTED';
  const confidence = typeof d.confidence === 'number' ? d.confidence : 0;

  const event: VehicleEvent = {
    id: String(d.event_id ?? `${cameraId}-${timestamp}`),
    cameraId,
    cameraName: cam?.name,
    plate: plate || '—',
    plateConfidence: confidence,
    timestamp,
    latitude: d.latitude ?? cam?.latitude ?? 0,
    longitude: d.longitude ?? cam?.longitude ?? 0,
    location: cam?.location,
    vehicleClass: (d.vehicle_class?.toUpperCase() as VehicleEvent['vehicleClass']) ?? undefined,
    eventType: watchlistMatch ? 'WATCHLIST_MATCH' : plate ? 'ANPR_READ' : 'VEHICLE_DETECTION',
    severity: watchlistMatch ? 'CRITICAL' : 'INFO',
    watchlistMatch,
  };

  const out: RealtimeMessage[] = [{ type: 'EVENT', payload: event }];

  if (type === 'ALERT_CREATED') {
    out.push({
      type: 'ALERT',
      payload: {
        id: String(d.id ?? d.alert_id ?? ''),
        eventId: String(d.event_id ?? ''),
        plate: plate || '—',
        cameraId,
        cameraName: cam?.name,
        location: cam?.location ?? '—',
        latitude: cam?.latitude,
        longitude: cam?.longitude,
        severity: (d.severity?.toUpperCase() as Alert['severity']) ?? 'HIGH',
        status: 'NEW',
        category: 'WATCHLIST_MATCH',
        createdAt: timestamp,
        confidence,
        note: d.message ?? undefined,
      },
    });
  }

  return out;
}

/** Camera registry cache so each live frame does not trigger a refetch. */
function cameraCache(): { get: () => Map<string, Camera> } {
  let cameras = new Map<string, Camera>();
  cameraService
    .index()
    .then((m) => {
      cameras = m;
    })
    .catch(() => undefined);
  return { get: () => cameras };
}

function connectSse(onMessage: Handler, onState: StateHandler): RealtimeChannel {
  onState('CONNECTING');
  const cache = cameraCache();
  const es = new EventSource(realtimeUrl('/stream'));
  es.onopen = () => onState('LIVE');
  es.onerror = () => onState('OFFLINE');
  es.onmessage = (e) => {
    try {
      translate(JSON.parse(e.data) as WireMessage, cache.get()).forEach(onMessage);
    } catch {
      /* ignore malformed frame */
    }
  };
  return { close: () => es.close() };
}

function connectWs(onMessage: Handler, onState: StateHandler): RealtimeChannel {
  onState('CONNECTING');
  const cache = cameraCache();
  let closed = false;
  let ws: WebSocket | undefined;
  let retry: number;
  let keepAlive: number;
  let attempt = 0;

  const open = () => {
    ws = new WebSocket(realtimeUrl('/ws/events', 'ws'));

    ws.onopen = () => {
      attempt = 0;
      onState('LIVE');
      // The server keeps the socket alive off client traffic; ping periodically
      // so idle proxies do not drop the connection.
      keepAlive = window.setInterval(() => ws?.readyState === WebSocket.OPEN && ws.send('ping'), 25_000);
    };

    ws.onmessage = (e) => {
      try {
        translate(JSON.parse(e.data) as WireMessage, cache.get()).forEach(onMessage);
      } catch {
        /* ignore malformed frame */
      }
    };

    ws.onclose = () => {
      window.clearInterval(keepAlive);
      onState('OFFLINE');
      if (closed) return;
      // Exponential backoff, capped — survives a backend restart (spec Phase 38).
      const delay = Math.min(30_000, 1_000 * 2 ** attempt++);
      retry = window.setTimeout(open, delay);
    };

    ws.onerror = () => ws?.close();
  };
  open();

  return {
    close: () => {
      closed = true;
      window.clearTimeout(retry);
      window.clearInterval(keepAlive);
      ws?.close();
    },
  };
}

/**
 * Single entry point for the live channel.
 * Mock mode → simulator. Otherwise SSE or WebSocket per VITE_REALTIME_TRANSPORT.
 */
export function connectRealtime(onMessage: Handler, onState: StateHandler): RealtimeChannel {
  if (isMockMode) return connectSimulator(onMessage, onState);
  if (config.realtimeTransport === 'ws') return connectWs(onMessage, onState);
  if (config.realtimeTransport === 'sse') return connectSse(onMessage, onState);
  onState('OFFLINE');
  return { close: () => undefined };
}
