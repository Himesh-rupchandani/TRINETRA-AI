import type { VehicleClass, VehicleEvent, EventType, Severity } from '@/types';
import { mockCameras, cameraByName } from './cameras';
import { atToday, watchlistByPlate } from './watchlist';
import { syntheticFrame, syntheticPlateCrop } from '@/utils/syntheticEvidence';
import { isProvidedPlate, providedFrameUrl, providedPlateCropUrl } from '@/utils/providedPlates';

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
  // User-provided plates use the EXACT photo (no AI substitute). Static URL
  // is browser-cached, lazy-loaded, and visible instantly in Vehicle Log.
  if (isProvidedPlate(e.plate)) {
    const frame = providedFrameUrl(e.plate)!;
    const crop = providedPlateCropUrl(e.plate)!;
    return {
      ...e,
      evidenceRef: ref,
      evidence: {
        ref,
        capturedAt: e.timestamp,
        synthetic: false,
        frameUrl: frame,
        plateCropUrl: crop,
      },
    };
  }
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
      { cam: 'CAM04', h: 0, m: 52, s: 8, conf: 96.4 },
      { cam: 'CAM17', h: 3, m: 57, s: 41, conf: 93.1 },
      { cam: 'CAM08', h: 5, m: 23, s: 12, conf: 97.8 },
      { cam: 'CAM07', h: 6, m: 28, s: 44, conf: 91.6 },
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
      { cam: 'CAM09', h: 1, m: 23, s: 15, conf: 89.7 },
      { cam: 'CAM17', h: 2, m: 48, s: 9, conf: 94.2 },
      { cam: 'CAM30', h: 4, m: 32, s: 27, conf: 92.5 },
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
      { cam: 'CAM24', h: 0, m: 38, s: 40, conf: 90.3 },
      { cam: 'CAM21', h: 2, m: 7, s: 53, conf: 87.9 },
      { cam: 'CAM22', h: 2, m: 34, s: 41, conf: 93.6 },
      { cam: 'CAM30', h: 5, m: 58, s: 19, conf: 91.2 },
    ],
  },
  // --- PROVIDED PLATES — exact user images, no AI substitute ---
  // Each plate has 3-4 cross-camera hops so Vehicle Log shows the provided
  // image multiple times (different cameras/times) and the gallery is populated
  // instantly when that plate is searched. All hops use isProvidedPlate → real photo.
  {
    plate: 'RJ19CL5074',
    vehicleClass: 'CAR',
    colour: 'White',
    make: 'Hyundai',
    model: 'i20',
    owner: 'PROVIDED EVIDENCE — RJ19CL5074 (white Hyundai)',
    hops: [
      { cam: 'CAM04', h: 1, m: 12, s: 8, conf: 98.2 },
      { cam: 'CAM17', h: 2, m: 14, s: 31, conf: 97.6 },
      { cam: 'CAM08', h: 3, m: 22, s: 12, conf: 98.9 },
      { cam: 'CAM07', h: 4, m: 18, s: 44, conf: 97.1 },
    ],
  },
  {
    plate: 'GJ03HK2595',
    vehicleClass: 'CAR',
    colour: 'Silver',
    make: 'Hyundai',
    model: 'i10 Sportz',
    owner: 'PROVIDED EVIDENCE — GJ03HK2595 (silver i10, damaged bumper)',
    hops: [
      { cam: 'CAM09', h: 0, m: 48, s: 15, conf: 97.4 },
      { cam: 'CAM17', h: 1, m: 52, s: 9, conf: 96.8 },
      { cam: 'CAM30', h: 2, m: 44, s: 27, conf: 97.9 },
    ],
  },
  {
    plate: 'GJ03NB2146',
    vehicleClass: 'CAR',
    colour: 'Grey',
    make: 'Maruti Suzuki',
    model: 'Alto K10',
    owner: 'PROVIDED EVIDENCE — GJ03NB2146 (dark grey Alto K10)',
    hops: [
      { cam: 'CAM24', h: 0, m: 22, s: 20, conf: 97.2 },
      { cam: 'CAM21', h: 1, m: 18, s: 11, conf: 96.5 },
      { cam: 'CAM22', h: 2, m: 8, s: 41, conf: 97.8 },
      { cam: 'CAM30', h: 3, m: 31, s: 19, conf: 96.9 },
    ],
  },
  {
    plate: 'GJ03JL5362',
    vehicleClass: 'CAR',
    colour: 'Grey',
    make: 'Maruti Suzuki',
    model: 'Baleno',
    owner: 'PROVIDED EVIDENCE — GJ03JL5362 (dark grey Baleno)',
    hops: [
      { cam: 'CAM04', h: 0, m: 33, s: 8, conf: 97.5 },
      { cam: 'CAM17', h: 1, m: 28, s: 31, conf: 96.9 },
      { cam: 'CAM08', h: 2, m: 41, s: 12, conf: 98.1 },
    ],
  },
  {
    plate: 'GJ03JL2801',
    vehicleClass: 'CAR',
    colour: 'Silver',
    make: 'Maruti Suzuki',
    model: 'Dzire',
    owner: 'PROVIDED EVIDENCE — GJ03JL2801 (grey Suzuki front)',
    hops: [
      { cam: 'CAM09', h: 0, m: 58, s: 15, conf: 97.7 },
      { cam: 'CAM17', h: 1, m: 48, s: 9, conf: 96.7 },
      { cam: 'CAM24', h: 2, m: 36, s: 27, conf: 97.6 },
      { cam: 'CAM30', h: 3, m: 48, s: 19, conf: 96.8 },
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

    // (Repeat watchlist sightings live in buildAmbientMiniJourneys below, as
    // coherent two-hop runs — never sprinkled at random cameras.)
    if (roll > 0.94) {
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
        watchlistMatch: false,
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

/* ------------------------------------------------------------------ *
 * Ambient repeat sightings — the recycled watchlist plates as         *
 * coherent two-hop runs at 63–66 km/h, never random sprinkles. Times  *
 * are minutes-ago so they always read as recent history.              *
 * ------------------------------------------------------------------ */
interface MiniHop {
  cam: string;
  agoMin: number;
  conf: number;
}

const AMBIENT_MINIS: Array<{
  plate: string;
  vehicleClass: NonNullable<VehicleEvent['vehicleClass']>;
  colour: string;
  hops: [MiniHop, MiniHop];
}> = [
  { plate: 'GJ03DT5566', vehicleClass: 'BUS', colour: 'White', hops: [{ cam: 'CAM04', agoMin: 46, conf: 93.5 }, { cam: 'CAM24', agoMin: 18, conf: 91.2 }] },
  { plate: 'GJ16TU9090', vehicleClass: 'TRUCK', colour: 'Blue', hops: [{ cam: 'CAM18', agoMin: 102, conf: 89.8 }, { cam: 'CAM09', agoMin: 16, conf: 94.4 }] },
  { plate: 'GJ21RS3344', vehicleClass: 'CAR', colour: 'Silver', hops: [{ cam: 'CAM24', agoMin: 118, conf: 90.6 }, { cam: 'CAM22', agoMin: 25, conf: 92.9 }] },
  { plate: 'GJ06KL2211', vehicleClass: 'VAN', colour: 'Grey', hops: [{ cam: 'CAM21', agoMin: 115, conf: 87.3 }, { cam: 'CAM24', agoMin: 27, conf: 95.1 }] },
  { plate: 'GJ12PQ8899', vehicleClass: 'CAR', colour: 'Red', hops: [{ cam: 'CAM07', agoMin: 88, conf: 91.7 }, { cam: 'CAM08', agoMin: 25, conf: 88.5 }] },
];

function buildAmbientMiniJourneys(): VehicleEvent[] {
  const now = Date.now();
  const out: VehicleEvent[] = [];
  AMBIENT_MINIS.forEach((m, mi) => {
    const severity = watchlistByPlate(m.plate)?.severity ?? 'MEDIUM';
    m.hops.forEach((hop, hi) => {
      const cam = cameraByName(hop.cam)!;
      out.push(
        attachEvidence({
          id: `evt-a-mini-${mi + 1}${hi + 1}`,
          cameraId: cam.id,
          cameraName: cam.name,
          vehicleId: 2000 + mi * 10 + hi,
          plate: m.plate,
          plateConfidence: hop.conf,
          timestamp: new Date(now - hop.agoMin * 60_000).toISOString(),
          latitude: cam.latitude,
          longitude: cam.longitude,
          location: cam.location,
          vehicleClass: m.vehicleClass,
          colour: m.colour,
          eventType: 'WATCHLIST_MATCH',
          severity,
          watchlistMatch: true,
          direction: pick(['N→S', 'S→N', 'E→W', 'W→E']),
          speedKmph: Math.round(between(58, 72)),
        }),
      );
    });
  });
  return out;
}

export const mockEvents: VehicleEvent[] = [...journeyEvents, ...buildAmbientMiniJourneys(), ...buildAmbientEvents()].sort(
  (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime(),
);

export const eventsByPlate = (plate: string): VehicleEvent[] =>
  mockEvents
    .filter((e) => e.plate === plate.toUpperCase())
    .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());

export const eventsByCamera = (cameraId: string): VehicleEvent[] =>
  mockEvents.filter((e) => e.cameraId === cameraId.toLowerCase());
