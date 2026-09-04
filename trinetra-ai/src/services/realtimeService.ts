import type { Alert, Camera, VehicleEvent } from '@/types';
import { config } from '@/lib/config';
import { isMockMode, realtimeUrl } from './api';
import { mockCameras } from '@/mocks/cameras';
import { watchlistByPlate } from '@/mocks/watchlist';
import { pushMockEvent, setMockCameraStatus } from '@/mocks/mockBackend';
import { syntheticFrame, syntheticPlateCrop } from '@/utils/syntheticEvidence';
import {
  getCameraIndex,
  mapAlert,
  mapVehicleEvent,
  type AlertDto,
  type CameraIndex,
  type VehicleEventDto,
} from './backendAdapter';

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
        severity: wl.severity ?? 'HIGH',
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
 * The backend broadcasts `{type: VEHICLE_DETECTED | WATCHLIST_MATCH |
 * ALERT_CREATED | CAMERA_STATUS_CHANGED, timestamp, payload}` (snake_case).
 * Translate to the app's realtime union; never fabricate fields.
 */
function mapBackendMessage(
  raw: unknown,
  cameras: CameraIndex,
): RealtimeMessage | null {
  if (typeof raw !== 'object' || raw === null) return null;
  const msg = raw as { type?: string; payload?: Record<string, unknown> };
  const p = (msg.payload ?? {}) as Record<string, unknown>;
  switch (msg.type) {
    case 'VEHICLE_DETECTED':
    case 'WATCHLIST_MATCH':
      return { type: 'EVENT', payload: mapVehicleEvent(p as unknown as VehicleEventDto, cameras) };
    case 'ALERT_CREATED':
      return { type: 'ALERT', payload: mapAlert(p as unknown as AlertDto, cameras) };
    case 'CAMERA_STATUS_CHANGED':
      if (typeof p.camera_id === 'string') {
        return {
          type: 'CAMERA_STATUS',
          payload: { cameraId: p.camera_id.toLowerCase(), status: toCameraStatus(p.status) },
        };
      }
      return null;
    default:
      return null; // CONNECTED / PONG / unknown — informational only
  }
}

const toCameraStatus = (s: unknown): Camera['status'] =>
  s === 'ONLINE' || s === 'DEGRADED' ? s : 'OFFLINE';

/** Camera index (best effort, 2s budget) so live payloads carry real names. */
async function camerasForRealtime(): Promise<CameraIndex> {
  try {
    return await Promise.race([
      getCameraIndex(),
      new Promise<CameraIndex>((resolve) => setTimeout(() => resolve(new Map()), 2000)),
    ]);
  } catch {
    return new Map();
  }
}

function connectSse(onMessage: Handler, onState: StateHandler): RealtimeChannel {
  onState('CONNECTING');
  let es: EventSource | null = null;
  let closed = false;
  void camerasForRealtime().then((cameras) => {
    if (closed) return;
    es = new EventSource(realtimeUrl('/stream'));
    es.onopen = () => onState('LIVE');
    es.onerror = () => onState('OFFLINE');
    es.onmessage = (e) => {
      try {
        const mapped = mapBackendMessage(JSON.parse(e.data), cameras);
        if (mapped) onMessage(mapped);
      } catch {
        /* ignore malformed frame */
      }
    };
  });
  return { close: () => { closed = true; es?.close(); } };
}

function connectWs(onMessage: Handler, onState: StateHandler): RealtimeChannel {
  onState('CONNECTING');
  let closed = false;
  let ws: WebSocket;
  let retry: number;
  let cameras = new Map() as CameraIndex;

  const open = () => {
    ws = new WebSocket(realtimeUrl('/ws/events', 'ws'));
    ws.onopen = () => onState('LIVE');
    ws.onmessage = (e) => {
      try {
        const mapped = mapBackendMessage(JSON.parse(e.data), cameras);
        if (mapped) onMessage(mapped);
      } catch {
        /* ignore malformed frame */
      }
    };
    ws.onclose = () => {
      onState('OFFLINE');
      if (!closed) retry = window.setTimeout(open, 4000); // simple backoff
    };
  };
  void camerasForRealtime().then((idx) => { cameras = idx; });
  open();

  return {
    close: () => {
      closed = true;
      window.clearTimeout(retry);
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
