import type { VehicleClass, VehicleEvent, EventType, Severity } from '@/types';
import { mockCameras, cameraByName } from './cameras';
import { atToday, watchlistByPlate } from './watchlist';
import { syntheticFrame, syntheticPlateCrop } from '@/utils/syntheticEvidence';

/* ------------------------------------------------------------------ *
 * Deterministic PRNG so every reload of the demo shows the same data. *
 * ------------------------------------------------------------------ */
function mulberry32(seed: number) {
  return function rand() {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const rand = mulberry32(20260902);
const pick = <T,>(arr: T[]): T => arr[Math.floor(rand() * arr.length)];
const between = (a: number, b: number) => a + rand() * (b - a);

const VEHICLE_CLASSES: VehicleClass[] = [
  'CAR',
  'CAR',
  'CAR',
  'MOTORCYCLE',
  'MOTORCYCLE',
  'AUTO_RICKSHAW',
  'TRUCK',
  'BUS',
  'VAN',
];
const COLOURS = ['White', 'Silver', 'Black', 'Red', 'Blue', 'Grey', 'Brown', 'Yellow'];
const RTO = ['GJ01', 'GJ03', 'GJ05', 'GJ06', 'GJ09', 'GJ12', 'GJ16', 'GJ18', 'GJ21', 'GJ27', 'MH12', 'RJ14'];
const LETTERS = 'ABCDEFGHJKLMNPQRSTUVWXYZ';

function randomPlate(): string {
  const s = pick(RTO);
  const a = LETTERS[Math.floor(rand() * LETTERS.length)] + LETTERS[Math.floor(rand() * LETTERS.length)];
  const n = String(Math.floor(between(1000, 9999)));
  return `${s}${a}${n}`;
}

function attachEvidence(e: VehicleEvent): VehicleEvent {
  const ref = `ev/${e.cameraId}/${e.id}`;
  return {
    ...e,
    evidenceRef: ref,
    evidence: {
      ref,
      capturedAt: e.timestamp,
      synthetic: true,
      frameUrl: syntheticFrame({
        cameraName: e.cameraName ?? e.cameraId.toUpperCase(),
        location: e.location ?? '',
        plate: e.plate,
        timestamp: e.timestamp,
        vehicleClass: e.vehicleClass,
      }),
      plateCropUrl: syntheticPlateCrop(e.plate, e.plateConfidence),
    },
  };
}

/* ------------------------------------------------------------------ *
 * Three tracked vehicle journeys (cross-camera movement histories).   *
 * Journey 1 is the primary demo trace referenced throughout the app.  *
 * ------------------------------------------------------------------ */
interface Hop {
  cam: string;
  h: number;
  m: number;
  s: number;
  conf: number;
}
interface JourneySeed {
  plate: string;
  vehicleClass: VehicleClass;
  colour: string;
  make: string;
  model: string;
  owner: string;
  hops: Hop[];
}

export const JOURNEY_SEEDS: JourneySeed[] = [
  {
    plate: 'GJ01AB1234',
    vehicleClass: 'CAR',
    colour: 'White',
    make: 'Maruti Suzuki',
    model: 'Swift VXI',
    owner: 'DEMO RECORD — H. Trivedi (Paldi)',
    hops: [
      { cam: 'CAM04', h: 14, m: 12, s: 8, conf: 96.4 },
      { cam: 'CAM08', h: 14, m: 27, s: 19, conf: 93.1 },
      { cam: 'CAM12', h: 14, m: 41, s: 5, conf: 97.8 },
      { cam: 'CAM17', h: 15, m: 3, s: 41, conf: 91.6 },
    ],
  },
  {
    plate: 'GJ05XY4321',
    vehicleClass: 'VAN',
    colour: 'Silver',
    make: 'Mahindra',
    model: 'Supro',
    owner: 'DEMO RECORD — Registered to commercial fleet',
    hops: [
      { cam: 'CAM27', h: 13, m: 48, s: 22, conf: 89.7 },
      { cam: 'CAM06', h: 13, m: 59, s: 44, conf: 94.2 },
      { cam: 'CAM05', h: 14, m: 12, s: 57, conf: 92.5 },
      { cam: 'CAM11', h: 14, m: 33, s: 9, conf: 88.4 },
      { cam: 'CAM09', h: 14, m: 46, s: 31, conf: 95.0 },
    ],
  },
  {
    plate: 'GJ18MH0099',
    vehicleClass: 'TRUCK',
    colour: 'Blue',
    make: 'Tata',
    model: 'LPT 1618',
    owner: 'DEMO RECORD — Goods carrier (permit revoked)',
    hops: [
      { cam: 'CAM29', h: 12, m: 5, s: 12, conf: 90.3 },
      { cam: 'CAM28', h: 12, m: 21, s: 40, conf: 87.9 },
      { cam: 'CAM30', h: 12, m: 44, s: 3, conf: 93.6 },
      { cam: 'CAM16', h: 13, m: 9, s: 55, conf: 91.2 },
    ],
  },
];

function buildJourneyEvents(): VehicleEvent[] {
  const out: VehicleEvent[] = [];
  JOURNEY_SEEDS.forEach((j, ji) => {
    const wl = watchlistByPlate(j.plate);
    j.hops.forEach((hop, hi) => {
      const cam = cameraByName(hop.cam)!;
      const id = `evt-j${ji + 1}-${hi + 1}`;
      out.push(
        attachEvidence({
          id,
          cameraId: cam.id,
          cameraName: cam.name,
          vehicleId: 4200 + ji,
          plate: j.plate,
          plateConfidence: hop.conf,
          timestamp: atToday(hop.h, hop.m, hop.s),
          latitude: cam.latitude,
          longitude: cam.longitude,
          location: cam.location,
          vehicleClass: j.vehicleClass,
          colour: j.colour,
          eventType: wl?.active ? 'WATCHLIST_MATCH' : 'ANPR_READ',
          severity: wl?.active ? wl.severity : 'INFO',
          watchlistMatch: Boolean(wl?.active),
          direction: pick(['N→S', 'S→N', 'E→W', 'W→E']),
          speedKmph: Math.round(between(24, 58)),
        }),
      );
    });
  });
  return out;
}

/* ------------------------------------------------------------------ *
 * Ambient traffic — a realistic 24h pool for the Event Explorer.      *
 * Deliberately bounded (~340 rows) so nothing renders thousands.      *
 * ------------------------------------------------------------------ */
function buildAmbientEvents(count = 340): VehicleEvent[] {
  const liveCams = mockCameras.filter((c) => c.status !== 'OFFLINE');
  const out: VehicleEvent[] = [];
  const now = Date.now();

  for (let i = 0; i < count; i++) {
    const cam = pick(liveCams);
    const minutesAgo = Math.floor(between(2, 24 * 60));
    const ts = new Date(now - minutesAgo * 60_000).toISOString();
    const vClass = pick(VEHICLE_CLASSES);
    const conf = Number(between(72, 99.4).toFixed(1));
    const roll = rand();
    let plate = randomPlate();
    let eventType: EventType = conf > 78 ? 'ANPR_READ' : 'VEHICLE_DETECTION';
    let severity: Severity = 'INFO';

    // A few ambient watchlist hits so the alert history is not empty.
    if (roll > 0.965) {
      plate = pick(['GJ12PQ8899', 'GJ16TU9090', 'GJ21RS3344', 'GJ06KL2211', 'GJ03DT5566']);
      eventType = 'WATCHLIST_MATCH';
      severity = watchlistByPlate(plate)?.severity ?? 'MEDIUM';
    } else if (roll > 0.94) {
      eventType = 'SPEED_VIOLATION';
      severity = 'MEDIUM';
    } else if (roll > 0.925) {
      eventType = 'WRONG_WAY';
      severity = 'HIGH';
    }

    out.push(
      attachEvidence({
        id: `evt-a-${String(i + 1).padStart(4, '0')}`,
        cameraId: cam.id,
        cameraName: cam.name,
        vehicleId: 1000 + i,
        plate,
        plateConfidence: conf,
        timestamp: ts,
        latitude: cam.latitude + between(-0.0006, 0.0006),
        longitude: cam.longitude + between(-0.0006, 0.0006),
        location: cam.location,
        vehicleClass: vClass,
        colour: pick(COLOURS),
        eventType,
        severity,
        watchlistMatch: eventType === 'WATCHLIST_MATCH',
        direction: pick(['N→S', 'S→N', 'E→W', 'W→E']),
        speedKmph: Math.round(between(18, eventType === 'SPEED_VIOLATION' ? 96 : 62)),
      }),
    );
  }

  // Camera health events for the offline/degraded units.
  mockCameras
    .filter((c) => c.status !== 'ONLINE')
    .forEach((c, i) => {
      out.push({
        id: `evt-h-${i + 1}`,
        cameraId: c.id,
        cameraName: c.name,
        plate: '—',
        plateConfidence: 0,
        timestamp: new Date(now - (40 + i * 37) * 60_000).toISOString(),
        latitude: c.latitude,
        longitude: c.longitude,
        location: c.location,
        eventType: c.status === 'OFFLINE' ? 'CAMERA_OFFLINE' : 'VEHICLE_DETECTION',
        severity: c.status === 'OFFLINE' ? 'HIGH' : 'MEDIUM',
        watchlistMatch: false,
      });
    });

  return out;
}

export const journeyEvents = buildJourneyEvents();

export const mockEvents: VehicleEvent[] = [...journeyEvents, ...buildAmbientEvents()].sort(
  (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime(),
);

export const eventsByPlate = (plate: string): VehicleEvent[] =>
  mockEvents
    .filter((e) => e.plate === plate.toUpperCase())
    .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());

export const eventsByCamera = (cameraId: string): VehicleEvent[] =>
  mockEvents.filter((e) => e.cameraId === cameraId.toLowerCase());
