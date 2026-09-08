import { haversineKm } from '@/lib/utils';

export interface LatLng {
  latitude: number;
  longitude: number;
}

export interface RoadLeg {
  /** Road distance in km (routed when live, circuity-adjusted estimate otherwise). */
  roadKm: number;
  /** Typical drive time in minutes (routed when live, speed-model estimate otherwise). */
  typicalMinutes: number;
  /** True when the numbers came from a live routing engine. */
  live: boolean;
}

const OSRM_URL = 'https://router.project-osrm.org/route/v1/driving';
const OSRM_TIMEOUT_MS = 6000;
const CACHE_KEY = 'trinetra.roadlegs.v1';
const CACHE_LIMIT = 300;

interface CacheEntry extends RoadLeg {
  t: number;
}

function legKey(a: LatLng, b: LatLng): string {
  const f = (n: number) => n.toFixed(4);
  return `${f(a.latitude)},${f(a.longitude)}>${f(b.latitude)},${f(b.longitude)}`;
}

/**
 * Calibrated offline estimate. Circuity (road vs straight-line) is checked
 * against real Gujarat routing data — e.g. Rajkot→Junagadh is ~94 km
 * straight-line vs ~103 km by road — and highway speed assumes a free-flow
 * car run (~60 km/h); live routing refines the duration when online.
 */
export function estimateRoadLeg(a: LatLng, b: LatLng): RoadLeg {
  const straight = haversineKm(a, b);
  const circuity = straight > 25 ? 1.15 : 1.35;
  const roadKm = straight * circuity;
  const speedKmph = straight <= 3 ? 24 : straight <= 25 ? 34 : 60;
  return { roadKm, typicalMinutes: (roadKm / speedKmph) * 60, live: false };
}

const memory = new Map<string, CacheEntry>();
let hydrated = false;

function hydrate(): void {
  if (hydrated) return;
  hydrated = true;
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (!raw) return;
    const parsed = JSON.parse(raw) as Record<string, CacheEntry>;
    for (const [k, v] of Object.entries(parsed)) {
      if (Number.isFinite(v?.roadKm) && Number.isFinite(v?.typicalMinutes)) memory.set(k, v);
    }
  } catch {
    /* Private browsing or corrupt cache: fall through to live/estimate. */
  }
}

function persist(): void {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify(Object.fromEntries(memory)));
  } catch {
    /* Storage full or unavailable: the in-memory cache still works. */
  }
}

function remember(key: string, leg: RoadLeg): void {
  memory.set(key, { ...leg, t: Date.now() });
  if (memory.size > CACHE_LIMIT) {
    const oldest = [...memory.entries()]
      .sort((x, y) => x[1].t - y[1].t)
      .slice(0, memory.size - CACHE_LIMIT);
    oldest.forEach(([k]) => memory.delete(k));
  }
  persist();
}

async function fetchOsrmLeg(a: LatLng, b: LatLng): Promise<RoadLeg | null> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), OSRM_TIMEOUT_MS);
  try {
    const res = await fetch(
      `${OSRM_URL}/${a.longitude},${a.latitude};${b.longitude},${b.latitude}?overview=false`,
      { signal: ctrl.signal },
    );
    if (!res.ok) return null;
    const json = (await res.json()) as {
      code?: string;
      routes?: Array<{ distance?: number; duration?: number }>;
    };
    const r = json?.code === 'Ok' ? json.routes?.[0] : undefined;
    const roadKm = r?.distance != null ? Number(r.distance) / 1000 : NaN;
    const typicalMinutes = r?.duration != null ? Number(r.duration) / 60 : NaN;
    if (!Number.isFinite(roadKm) || !Number.isFinite(typicalMinutes) || roadKm <= 0) return null;
    return { roadKm, typicalMinutes, live: true };
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Road distance + typical drive time between two points. Served from cache
 * when available, otherwise attempted against the public OSRM demo router
 * with a short timeout, falling back to the calibrated offline estimate.
 * Every outcome is cached, so repeated views never refetch.
 */
export async function getRoadLeg(a: LatLng, b: LatLng): Promise<RoadLeg> {
  const key = legKey(a, b);
  hydrate();
  const hit = memory.get(key);
  if (hit) return { roadKm: hit.roadKm, typicalMinutes: hit.typicalMinutes, live: hit.live };
  const leg = (await fetchOsrmLeg(a, b)) ?? estimateRoadLeg(a, b);
  remember(key, leg);
  return leg;
}
