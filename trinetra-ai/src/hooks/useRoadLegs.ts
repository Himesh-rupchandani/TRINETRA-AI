import { useEffect, useMemo, useState } from 'react';
import type { RoutePoint } from '@/types';
import { estimateRoadLeg, getRoadLeg, type RoadLeg } from '@/services/routeService';

type Pair = Pick<RoutePoint, 'latitude' | 'longitude'>;
type GeoPair = Pair & { latitude: number; longitude: number };

function hasCoords(p: Pair | undefined): p is GeoPair {
  return p != null && p.latitude != null && p.longitude != null && !(p.latitude === 0 && p.longitude === 0);
}

/**
 * Road distance + typical drive time for every leg of a route, keyed by the
 * destination point's sequence. Synchronous estimates render immediately so
 * the UI never flashes a loading state; live routing upgrades each leg in
 * place when reachable (and is cached afterwards).
 */
export function useRoadLegs(points: RoutePoint[]): Record<number, RoadLeg> {
  const key = useMemo(
    () =>
      points
        .map((p) => {
          const lat = p.latitude != null ? p.latitude.toFixed(4) : '-';
          const lng = p.longitude != null ? p.longitude.toFixed(4) : '-';
          return `${p.sequence}:${lat},${lng}`;
        })
        .join('|'),
    [points],
  );
  const [legs, setLegs] = useState<Record<number, RoadLeg>>({});

  useEffect(() => {
    if (points.length < 2) {
      setLegs({});
      return;
    }
    let cancelled = false;
    const initial: Record<number, RoadLeg> = {};
    for (let i = 1; i < points.length; i++) {
      const prev = points[i - 1];
      const cur = points[i];
      if (hasCoords(prev) && hasCoords(cur)) {
        initial[cur.sequence] = estimateRoadLeg(prev, cur);
      }
    }
    setLegs(initial);
    (async () => {
      const upgraded: Record<number, RoadLeg> = {};
      await Promise.all(
        points.slice(1).map(async (p, idx) => {
          const prev = points[idx];
          if (hasCoords(prev) && hasCoords(p)) upgraded[p.sequence] = await getRoadLeg(prev, p);
        }),
      );
      if (!cancelled) setLegs({ ...initial, ...upgraded });
    })();
    return () => {
      cancelled = true;
    };
    // Keyed on the serialised coordinates, not the array identity.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return legs;
}

/** Single-leg variant for map popups, which render one point at a time. */
export function useRoadLeg(
  prev: Pick<RoutePoint, 'latitude' | 'longitude'> | undefined,
  point: Pick<RoutePoint, 'latitude' | 'longitude'>,
): RoadLeg | undefined {
  const [leg, setLeg] = useState<RoadLeg | undefined>(() =>
    hasCoords(prev) && hasCoords(point) ? estimateRoadLeg(prev, point) : undefined,
  );

  useEffect(() => {
    if (!hasCoords(prev) || !hasCoords(point)) {
      setLeg(undefined);
      return;
    }
    let cancelled = false;
    setLeg(estimateRoadLeg(prev, point));
    getRoadLeg(prev, point).then((live) => {
      if (!cancelled) setLeg(live);
    });
    return () => {
      cancelled = true;
    };
  }, [prev?.latitude, prev?.longitude, point.latitude, point.longitude]);

  return leg;
}
