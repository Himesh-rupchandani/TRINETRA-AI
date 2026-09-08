import type { Alert, Camera, VehicleEvent } from '@/types';
import { config } from '@/lib/config';
import { isMockMode, realtimeUrl } from './api';
import { mockCameras } from '@/mocks/cameras';
import { watchlistByPlate } from '@/mocks/watchlist';
import { pushMockEvent, setMockCameraStatus } from '@/mocks/mockBackend';
import { syntheticFrame, syntheticPlateCrop } from '@/utils/syntheticEvidence';
import { cameraDirectory, toAlert, toVehicleEvent, type AlertDto, type CameraMeta, type VehicleEventDto } from './adapters';

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

/**
 * Watched plates are staked out: repeat sightings always come from the same
 * post (their last known camera), so the live feed never teleports a vehicle
 * across the state between ticks. Posts for new plates are picked once,
 * then sticky.
 */
const STAKEOUTS: Record<string, string> = {
  GJ01AB1234: 'cam07',
  GJ05XY4321: 'cam30',
  GJ12PQ8899: 'cam08',
  GJ16TU9090: 'cam09',
  GJ21RS3344: 'cam22',
  GJ06KL2211: 'cam24',
  GJ03DT5566: 'cam24',
};
const watchPosts = new Map<string, Camera>();
function watchCamera(plate: string): Camera {
  const known = watchPosts.get(plate);
  if (known) return known;
  const online = mockCameras.filter((c) => c.status === 'ONLINE');
  const fixed = STAKEOUTS[plate];
  const cam = (fixed && online.find((c) => c.id === fixed)) || rnd(online);
  watchPosts.set(plate, cam);
  return cam;
}

const rnd = <T,>(a: T[]): T => a[Math.floor(Math.random() * a.length)];
const randomPlate = () =>
  `${rnd(RTO)}${rnd([...LETTERS])}${rnd([...LETTERS])}${Math.floor(1000 + Math.random() * 9000)}`;

let seq = 0;

function makeEvent(): { event: VehicleEvent; alert?: Alert } {
  const isWatch = Math.random() > 0.82;
  const plate = isWatch ? rnd(WATCH_PLATES) : randomPlate();
  const cam = isWatch ? watchCamera(plate) : rnd(mockCameras.filter((c) => c.status === 'ONLINE'));
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
 * The backend broadcasts a typed envelope:
 *   { type: 'VEHICLE_DETECTED'|'WATCHLIST_MATCH'|'ALERT_CREATED'
 *       |'CAMERA_STATUS_CHANGED'|'CONNECTED'|'PONG',
 *     timestamp, payload: { event_id, camera_id, plate_number, confidence, … } }
 *
 * This maps it onto the frontend message model, enriching with canonical
 * camera metadata from the shared registry directory.
 */
type CameraDir = Map<string, CameraMeta> | null;

let liveCameraDir: CameraDir = null;
let dirLoading = false;
function primeCameraDir(): void {
  if (dirLoading) return;
  dirLoading = true;
  cameraDirectory()
    .then((d) => {
      liveCameraDir = d;
    })
    .catch(() => undefined);
}

function mapBackendEventPayload(raw: Record<string, unknown>): VehicleEvent {
  const dto = {
    id: Number(raw.event_id ?? raw.id ?? 0),
    camera_id: String(raw.camera_id ?? ''),
    vehicle_track_id: raw.vehicle_track_id != null ? Number(raw.vehicle_track_id) : undefined,
    plate_raw: raw.plate_raw as string | undefined,
    plate_number: (raw.plate_number ?? raw.plate) as string | undefined,
    plate_confidence: raw.plate_confidence != null
      ? Number(raw.plate_confidence)
      : raw.confidence != null
        ? Number(raw.confidence)
        : undefined,
    vehicle_class: raw.vehicle_class as string | undefined,
    event_time: (raw.event_time ?? new Date().toISOString()) as string,
    latitude: raw.latitude as number | undefined,
    longitude: raw.longitude as number | undefined,
    watchlist_match: Boolean(raw.watchlist_match),
  } satisfies VehicleEventDto;
  return toVehicleEvent(dto, liveCameraDir);
}

/**
 * One wire frame can imply several UI updates.
 *
 * The backend broadcasts a single ALERT_CREATED for a watchlist hit, but the
 * operator needs it in two places at once — the alert list and the live event
 * feed. The payload already carries every event field, so both are derived
 * here instead of asking the backend to send the sighting twice.
 */
export function mapBackendMessages(raw: unknown): RealtimeMessage[] {
  if (!raw || typeof raw !== 'object') return [];
  const envelope = raw as { type?: string; payload?: Record<string, unknown>; data?: Record<string, unknown> };
  const body = (envelope.payload ?? envelope.data ?? {}) as Record<string, unknown>;

  switch (envelope.type) {
    case 'VEHICLE_DETECTED':
    case 'WATCHLIST_MATCH':
      return [{ type: 'EVENT', payload: mapBackendEventPayload(body) }];
    case 'ALERT_CREATED': {
      const event = mapBackendEventPayload(body);
      const dto = {
        id: Number(body.alert_id ?? body.id ?? body.event_id ?? 0),
        event_id: Number(body.event_id ?? 0) || null,
        camera_id: String(body.camera_id ?? ''),
        plate_number: (body.plate_number ?? body.plate) as string | null,
        alert_type: 'WATCHLIST_MATCH',
        severity: String(body.severity ?? 'CRITICAL'),
        message: String(body.message ?? `Watchlist match on ${body.camera_id ?? 'camera'}`),
        status: 'NEW',
        confidence:
          body.plate_confidence != null
            ? Number(body.plate_confidence)
            : body.confidence != null
              ? Number(body.confidence)
              : null,
        timestamp: new Date().toISOString(),
      } satisfies AlertDto;
      const alert = toAlert(dto, liveCameraDir);
      return [
        { type: 'EVENT', payload: event },
        { type: 'ALERT', payload: { ...alert, eventId: event.id } },
      ];
    }
    case 'CAMERA_STATUS_CHANGED':
      return [
        {
          type: 'CAMERA_STATUS',
          payload: {
            cameraId: String(body.camera_id ?? body.cameraId ?? '').toLowerCase(),
            status: String(body.status ?? 'OFFLINE').toUpperCase() as Camera['status'],
          },
        },
      ];
    default:
      return []; // CONNECTED / PONG / unknown — ignored
  }
}

function connectSse(onMessage: Handler, onState: StateHandler): RealtimeChannel {
  onState('CONNECTING');
  primeCameraDir();
  let closed = false;
  let es: EventSource | null = null;
  let retryTimer: number | undefined;

  const open = () => {
    if (closed) return;
    try {
      es = new EventSource(realtimeUrl('/stream'), { withCredentials: false });
      es.onopen = () => {
        onState('LIVE');
      };
      es.onerror = () => {
        es?.close();
        onState('OFFLINE');
        // Retry after 3s - SSE should reconnect automatically, but some proxies need explicit retry
        if (!closed) {
          retryTimer = window.setTimeout(() => {
            onState('CONNECTING');
            open();
          }, 3000) as unknown as number;
        }
      };
      es.onmessage = (e) => {
        try {
          // Backend sends ": connected" keepalive which is not JSON - ignore
          if (e.data.startsWith(':')) return;
          mapBackendMessages(JSON.parse(e.data)).forEach(onMessage);
        } catch {
          /* ignore malformed frame / keepalive */
        }
      };
    } catch {
      onState('OFFLINE');
      if (!closed) {
        retryTimer = window.setTimeout(open, 4000) as unknown as number;
      }
    }
  };

  open();

  return {
    close: () => {
      closed = true;
      if (retryTimer) window.clearTimeout(retryTimer);
      es?.close();
    },
  };
}

function connectWs(onMessage: Handler, onState: StateHandler): RealtimeChannel {
  onState('CONNECTING');
  primeCameraDir();
  let closed = false;
  let ws: WebSocket;
  let retry: number;

  const open = () => {
    ws = new WebSocket(realtimeUrl('/ws/events', 'ws'));
    ws.onopen = () => onState('LIVE');
    ws.onmessage = (e) => {
      try {
        mapBackendMessages(JSON.parse(e.data)).forEach(onMessage);
      } catch {
        /* ignore malformed frame */
      }
    };
    ws.onclose = () => {
      onState('OFFLINE');
      if (!closed) retry = window.setTimeout(open, 4000); // simple backoff
    };
  };
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
