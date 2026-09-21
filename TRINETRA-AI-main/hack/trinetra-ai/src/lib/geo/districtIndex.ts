/**
 * District spatial index for the bundled Gujarat polygons.
 *
 * Point-in-polygon (ray casting, holes respected) so cameras and sightings
 * can be attributed to their district without any server support: the basis
 * for density shading, district clustering bubbles and click-to-focus.
 */
import { gujaratDistricts } from './gujaratDistricts';

type Ring = [number, number][]; // GeoJSON order: [lng, lat]

interface DistrictGeom {
  name: string;
  polys: { outer: Ring; holes: Ring[] }[];
}

function toPolys(geom: { type: string; coordinates: unknown }): DistrictGeom['polys'] {
  const ringsToPoly = (rings: Ring[]) => ({ outer: rings[0], holes: rings.slice(1) });
  if (geom.type === 'Polygon') return [ringsToPoly(geom.coordinates as Ring[])];
  if (geom.type === 'MultiPolygon')
    return (geom.coordinates as Ring[][]).map((rings) => ringsToPoly(rings));
  return [];
}

const DISTRICTS: DistrictGeom[] = (
  gujaratDistricts as unknown as { features: { properties: { name: string }; geometry: never }[] }
).features.map((f) => ({ name: f.properties.name, polys: toPolys(f.geometry) }));

function inRing(lng: number, lat: number, ring: Ring): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    const intersects = yi > lat !== yj > lat && lng < ((xj - xi) * (lat - yi)) / (yj - yi + 1e-12) + xi;
    if (intersects) inside = !inside;
  }
  return inside;
}

/** District name containing the point, or null (outside Gujarat / enclaves). */
export function districtAt(lat: number, lng: number): string | null {
  for (const d of DISTRICTS) {
    for (const p of d.polys) {
      if (!inRing(lng, lat, p.outer)) continue;
      if (p.holes.some((h) => inRing(lng, lat, h))) continue;
      return d.name;
    }
  }
  return null;
}

export interface DistrictAgg {
  name: string;
  cameras: number;
  offlineCameras: number;
  events: number;
  /** [lat, lng] of every camera inside — drives the click-to-zoom fit. */
  bounds: [number, number][];
  /** Bubble anchor: centroid of the member cameras. */
  centroid: [number, number] | null;
}

/**
 * Bucket cameras and sightings into per-district aggregates.
 * Camera items need `status` (to count offline); events just need coordinates.
 */
export function aggregateByDistrict<
  C extends { latitude: number; longitude: number; status?: string },
  E extends { latitude: number; longitude: number },
>(cameras: C[], events: E[]): Map<string, DistrictAgg> {
  const out = new Map<string, DistrictAgg>();
  const touch = (lat: number, lng: number): DistrictAgg | null => {
    const name = districtAt(lat, lng);
    if (!name) return null;
    let agg = out.get(name);
    if (!agg) {
      agg = { name, cameras: 0, offlineCameras: 0, events: 0, bounds: [], centroid: null };
      out.set(name, agg);
    }
    return agg;
  };
  const sums = new Map<string, { sx: number; sy: number; n: number }>();

  for (const c of cameras) {
    const agg = touch(c.latitude, c.longitude);
    if (!agg) continue;
    agg.cameras += 1;
    if (c.status === 'OFFLINE') agg.offlineCameras += 1;
    agg.bounds.push([c.latitude, c.longitude]);
    const s = sums.get(agg.name) ?? { sx: 0, sy: 0, n: 0 };
    s.sx += c.longitude;
    s.sy += c.latitude;
    s.n += 1;
    sums.set(agg.name, s);
  }
  for (const e of events) {
    const agg = touch(e.latitude, e.longitude);
    if (agg) agg.events += 1;
  }
  for (const [name, s] of sums) {
    const agg = out.get(name);
    if (agg && s.n > 0) agg.centroid = [s.sy / s.n, s.sx / s.n];
  }
  return out;
}
